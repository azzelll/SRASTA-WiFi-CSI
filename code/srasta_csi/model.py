"""Compact TCN-Lite, full-INT8 conversion, and inference helpers."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .decoder import FEATURE_COUNT


PARITY_MEAN_ABS_ERROR_MAX = 0.02
PARITY_MAX_ABS_ERROR_MAX = 0.10
PARITY_ARGMAX_AGREEMENT_MIN = 0.95


def build_tcn_lite(window_length: int, seed: int = 42):
    if window_length <= 0:
        raise ValueError("window length must be positive")
    import tensorflow as tf

    tf.keras.utils.set_random_seed(seed)
    inputs = tf.keras.Input((window_length, FEATURE_COUNT), name="amplitude_52")
    values = tf.keras.layers.Conv1D(24, 1, padding="causal", activation="relu", name="projection")(inputs)
    for dilation in (1, 2, 4):
        residual = values
        values = tf.keras.layers.Conv1D(24, 3, padding="causal", dilation_rate=dilation, activation="relu", name=f"d{dilation}_a")(values)
        values = tf.keras.layers.Conv1D(24, 3, padding="causal", dilation_rate=dilation, activation="relu", name=f"d{dilation}_b")(values)
        values = tf.keras.layers.Add(name=f"d{dilation}_add")([residual, values])
        values = tf.keras.layers.Activation("relu", name=f"d{dilation}_residual")(values)
    values = tf.keras.layers.GlobalAveragePooling1D(name="temporal_average")(values)
    outputs = tf.keras.layers.Dense(2, activation="softmax", name="fall_probability")(values)
    return tf.keras.Model(inputs, outputs, name="srasta_tcn_lite")


def export_full_int8(model, representative_windows: np.ndarray, output: str | Path) -> Path:
    import tensorflow as tf

    representative = np.asarray(representative_windows, dtype=np.float32)
    expected = tuple(model.input_shape[1:])
    if representative.ndim != 3 or tuple(representative.shape[1:]) != expected or len(representative) == 0:
        raise ValueError(f"representative windows must have nonempty shape [n,{expected[0]},{expected[1]}]")
    if not np.isfinite(representative).all():
        raise ValueError("representative windows must be finite")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: ([representative[index : index + 1]] for index in range(len(representative)))
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    target = Path(output)
    target.write_bytes(converter.convert())
    runtime = TFLiteModel(target)
    if runtime.input_detail["dtype"] != np.int8 or runtime.output_detail["dtype"] != np.int8:
        target.unlink(missing_ok=True)
        raise ValueError("TFLite conversion did not produce full INT8 I/O")
    return target


class TFLiteModel:
    def __init__(self, path: str | Path):
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            try:
                from ai_edge_litert.interpreter import Interpreter
            except ImportError:
                import tensorflow as tf
                Interpreter = tf.lite.Interpreter

        self.interpreter = Interpreter(model_path=str(path))
        self.interpreter.allocate_tensors()
        self.input_detail = self.interpreter.get_input_details()[0]
        self.output_detail = self.interpreter.get_output_details()[0]
        self.window_length = int(self.input_detail["shape"][1])
        if tuple(self.input_detail["shape"][1:]) != (self.window_length, FEATURE_COUNT):
            raise ValueError("TFLite input must be [1,time,52]")
        if self.input_detail["dtype"] != np.int8 or self.output_detail["dtype"] != np.int8:
            raise ValueError("TFLite model must use full INT8 input and output")
        if self.input_detail["quantization"][0] <= 0 or self.output_detail["quantization"][0] <= 0:
            raise ValueError("TFLite model has invalid quantization scales")

    def predict(self, window: np.ndarray) -> np.ndarray:
        values = np.asarray(window, dtype=np.float32)
        if values.shape != (self.window_length, FEATURE_COUNT) or not np.isfinite(values).all():
            raise ValueError(f"TFLite input must be finite [{self.window_length},52]")
        values = values[None, ...]
        scale, zero = self.input_detail["quantization"]
        values = np.clip(np.round(values / scale + zero), -128, 127).astype(np.int8)
        self.interpreter.set_tensor(self.input_detail["index"], values)
        self.interpreter.invoke()
        output = self.interpreter.get_tensor(self.output_detail["index"])[0]
        scale, zero = self.output_detail["quantization"]
        return (output.astype(np.float32) - zero) * scale

    def probability(self, window: np.ndarray) -> float:
        return float(self.predict(window)[1])


def parity_report(model, tflite: TFLiteModel, windows: np.ndarray) -> dict[str, object]:
    windows = np.asarray(windows, dtype=np.float32)
    if windows.ndim != 3 or len(windows) == 0 or tuple(windows.shape[1:]) != tuple(model.input_shape[1:]):
        raise ValueError("parity windows do not match the FP32 model input")
    fp32 = np.asarray(model.predict(windows, verbose=0), dtype=np.float32)
    started = time.perf_counter()
    quantized = np.stack([tflite.predict(window) for window in windows])
    elapsed = time.perf_counter() - started
    errors = np.abs(fp32 - quantized)
    result = {
        "windows_compared": len(windows),
        "mean_absolute_error": float(errors.mean()),
        "max_absolute_error": float(errors.max()),
        "argmax_agreement": float(np.mean(np.argmax(fp32, axis=1) == np.argmax(quantized, axis=1))),
        "mean_tflite_inference_ms": float(elapsed * 1000 / len(windows)),
        "thresholds": {
            "mean_absolute_error_max": PARITY_MEAN_ABS_ERROR_MAX,
            "max_absolute_error_max": PARITY_MAX_ABS_ERROR_MAX,
            "argmax_agreement_min": PARITY_ARGMAX_AGREEMENT_MIN,
        },
    }
    result["status"] = "passed" if (
        result["mean_absolute_error"] <= PARITY_MEAN_ABS_ERROR_MAX
        and result["max_absolute_error"] <= PARITY_MAX_ABS_ERROR_MAX
        and result["argmax_agreement"] >= PARITY_ARGMAX_AGREEMENT_MIN
    ) else "failed"
    return result
