"""Read the curated ESP32 CSI-Bench manifest and canonical amplitude arrays."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from .decoder import FEATURE_COUNT, USABLE_SUBCARRIER_INDICES


_ALLOWED_SPLITS = ("train", "validation", "test", "excluded")
_EVALUATION_SPLITS = ("train", "validation", "test")


@dataclass(frozen=True)
class ManifestRow:
    sample_id: str
    source_path: str
    label: str
    label_id: int
    subject_id: str
    session_id: str
    split: str


def manifest_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_manifest(path: str | Path) -> list[ManifestRow]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "source_path", "label", "label_id", "subject_id", "session_id", "device", "feature_count", "split"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("manifest does not contain the curated ESP32 schema")
        rows: list[ManifestRow] = []
        for raw in reader:
            identity = {name: (raw.get(name) or "").strip() for name in ("sample_id", "source_path", "subject_id", "session_id", "split")}
            if not all(identity.values()):
                raise ValueError("manifest identifiers, source paths, and splits must not be empty")
            if identity["split"] not in _ALLOWED_SPLITS:
                raise ValueError(f"invalid split in {identity['sample_id']}")
            try:
                feature_count = int(raw["feature_count"])
                label_id = int(raw["label_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid numeric field in {identity['sample_id']}") from exc
            if (raw.get("device") or "").strip() != "ESP32" or feature_count != FEATURE_COUNT:
                raise ValueError(f"invalid curated row {identity['sample_id']}")
            if not identity["source_path"].startswith("csi-bench/FallDetection/") or "/device_ESP32/" not in identity["source_path"] or Path(identity["source_path"]).suffix.lower() not in {".h5", ".hdf5"}:
                raise ValueError(f"non-primary source in {identity['sample_id']}")
            if (raw["label"], label_id) not in {("nonfall", 0), ("fall", 1)}:
                raise ValueError(f"invalid label in {identity['sample_id']}")
            rows.append(ManifestRow(identity["sample_id"], identity["source_path"], raw["label"], label_id, identity["subject_id"], identity["session_id"], identity["split"]))
    if not rows:
        raise ValueError("manifest is empty")
    for name, values in (("sample identifier", [row.sample_id for row in rows]), ("source path", [row.source_path for row in rows])):
        if len(set(values)) != len(values):
            raise ValueError(f"manifest has duplicate {name}s")
    assert_split_disjoint(rows)
    return rows


def assert_split_disjoint(rows: list[ManifestRow]) -> None:
    if any(row.split not in _ALLOWED_SPLITS or not row.subject_id.strip() or not row.session_id.strip() or not row.source_path.strip() for row in rows):
        raise ValueError("split rows contain an invalid split or empty identifier")
    if len({row.sample_id for row in rows}) != len(rows) or len({row.source_path for row in rows}) != len(rows):
        raise ValueError("split rows contain duplicate sample identifiers or source paths")
    subjects = {split: {row.subject_id for row in rows if row.split == split} for split in _EVALUATION_SPLITS}
    # CSI-Bench reuses numeric session IDs across subjects, so a recording
    # session is namespaced by subject rather than treated as a global ID.
    sessions = {split: {(row.subject_id, row.session_id) for row in rows if row.split == split} for split in _EVALUATION_SPLITS}
    sources = {split: {row.source_path for row in rows if row.split == split} for split in _EVALUATION_SPLITS}
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if subjects[left] & subjects[right]:
            raise ValueError(f"subject leakage between {left} and {right}")
        if sessions[left] & sessions[right]:
            raise ValueError(f"session leakage between {left} and {right}")
        if sources[left] & sources[right]:
            raise ValueError(f"source leakage between {left} and {right}")


def split_report(rows: list[ManifestRow]) -> dict[str, object]:
    result: dict[str, object] = {
        "validated_before_windowing": True,
        "overlap_checks": {"subject": "passed", "session": "passed", "source_path": "passed"},
    }
    for split in _ALLOWED_SPLITS:
        selected = [row for row in rows if row.split == split]
        result[split] = {
            "subjects": sorted({row.subject_id for row in selected}),
            "sessions": sorted({row.session_id for row in selected}),
            "subject_count": len({row.subject_id for row in selected}),
            "session_count": len({row.session_id for row in selected}),
            "sample_count": len(selected),
            "source_count": len({row.source_path for row in selected}),
            "class_counts": dict(sorted(Counter(row.label for row in selected).items())),
        }
    return result


def resolve_source_path(row: ManifestRow, data_root: str | Path) -> Path:
    root = Path(data_root).resolve()
    relative = Path(row.source_path)
    if relative.is_absolute() or relative.parts[:1] != ("csi-bench",):
        raise ValueError("source path escapes the curated csi-bench root")
    target = (root / relative).resolve()
    if root not in target.parents:
        raise ValueError("source path escapes the data root")
    return target


def read_h5_amplitude(path: str | Path) -> np.ndarray:
    with h5py.File(path, "r") as handle:
        if "CSI_amps" not in handle:
            raise ValueError("CSI_amps dataset not found")
        raw = np.asarray(handle["CSI_amps"], dtype=np.float32)
    if raw.ndim != 3 or raw.shape[0] != 64 or raw.shape[2] != 1:
        raise ValueError(f"expected CSI_amps [64,time,1], got {raw.shape}")
    values = raw[:, :, 0].T[:, USABLE_SUBCARRIER_INDICES]
    if values.ndim != 2 or values.shape[1] != FEATURE_COUNT:
        raise ValueError("H5 conversion did not create [time,52]")
    return values


def timestamps(frame_count: int, sample_rate_hz: float = 100.0) -> np.ndarray:
    if not isinstance(frame_count, (int, np.integer)) or isinstance(frame_count, bool) or frame_count < 2 or sample_rate_hz <= 0 or not np.isfinite(sample_rate_hz):
        raise ValueError("at least two frames and a finite positive sample rate are required")
    return np.arange(frame_count, dtype=np.float64) / sample_rate_hz


def centered_window(values: np.ndarray, length: int = 250) -> np.ndarray:
    values = np.asarray(values)
    if values.ndim != 2 or values.shape[1] != FEATURE_COUNT or len(values) < length:
        raise ValueError("recording cannot provide the requested [time,52] window")
    start = (len(values) - length) // 2
    return values[start : start + length]


def read_replay(path: str | Path, sample_rate_hz: float = 100.0) -> tuple[np.ndarray, np.ndarray]:
    replay = Path(path)
    if replay.suffix.lower() in {".h5", ".hdf5"}:
        values = read_h5_amplitude(replay)
        return values, timestamps(len(values), sample_rate_hz)
    if replay.suffix.lower() == ".npz":
        with np.load(replay) as archive:
            if "amplitude" not in archive:
                raise ValueError("NPZ replay is missing amplitude")
            values = np.asarray(archive["amplitude"], dtype=np.float32)
            times = np.asarray(archive["timestamps_s"] if "timestamps_s" in archive else timestamps(len(values), sample_rate_hz), dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != FEATURE_COUNT or times.shape != (len(values),):
            raise ValueError("NPZ replay requires amplitude [time,52] and matching timestamps_s")
        return values, times
    raise ValueError("replay must be H5/HDF5 or NPZ")
