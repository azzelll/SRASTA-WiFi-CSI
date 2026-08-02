# SRASTA AI and Edge Backend Context

## Product context

The Google Docs proposal is SRASTA's **immutable product source of truth**:

<https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit>

No local file, schema, test, existing model, or agent may dispute, narrow,
replace, defer, or reinterpret the product scope, features, priorities,
terminology, user experience, or claims in that proposal. This file is an
implementation companion: it defines the current CSI data contract and audit,
not a competing product brief.

The current CSI fall-detection implementation workstream is:

- One indoor room, controlled configuration, one person at a time.
- Primary output: `normal`, `suspected_fall`, `confirmed_fall`, and
  `no_person` when supported by data.
- Edge inference runs on Raspberry Pi; ESP32-S3 is the CSI capture device.
- The fall/non-fall model is an initial component, not a limit on the
  proposal-defined multi-purpose monitoring product. Any capability outside
  this component remains a product requirement; record its evidence and
  implementation gap without de-scoping it.

## Important current audit

Do not reuse the existing trained artifact as evidence of performance:

- `code/runs/srasta_fall/training_summary.json` has one class only: `fall`.
- The old training loader assumes axis 0 is time. CSI-Bench ESP32 H5 data is
  `[64 subcarrier positions, 500 frames, 1 stream]`.
- The old runtime feeds raw I/Q bytes to a 232-feature model instead of
  amplitude features. This is a train/inference mismatch.

## ESP32-S3 CSI input contract

The ESP32 receives ordinary WiFi packets from a controlled sender. Its WiFi
driver exposes CSI alongside every received packet.

Logical frame schema:

```text
version, sequence, local_timestamp_us,
sender_mac, rssi, noise_floor, channel, bandwidth, sig_mode, mcs,
rx_state, len, first_word_invalid,
iq_bytes[]
```

For the V1 fixed capture contract:

```text
LTF:       LLTF only
bandwidth: HT20
length:    128 signed int8 bytes
payload:   [imag_0, real_0, imag_1, real_1, ..., imag_63, real_63]
```

Transform it as follows:

```python
iq = np.asarray(iq_bytes, dtype=np.float32).reshape(64, 2)
amplitude_64 = np.hypot(iq[:, 0], iq[:, 1])
usable_indices = list(range(6, 32)) + list(range(33, 59))
amplitude_52 = amplitude_64[usable_indices]
```

The valid mask is based on the ESP32-S3 CSI-Bench records in this workspace:
they store 64 positions but only indices `6..31` and `33..58` are non-zero;
index 32 is DC and the edges are unused. Do not delete invalid values and
shift indices. Keep a fixed mask. When `first_word_invalid` is true, retain
the 52-feature shape and mask the affected unusable/invalid positions.

For each capture session, save all raw metadata and a config hash. Train and
infer only when the config hash matches the configured capture profile.

References:

- ESP-IDF explains CSI bytes are `[imaginary, real]`, and warns that the first
  four bytes may be invalid on ESP32-S3:
  <https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32s3/api-guides/wifi.html>
- Espressif's `esp-csi` two-board example and raw serial layout:
  <https://github.com/espressif/esp-csi/tree/master/examples/get-started>
- CSI-Bench documents ESP32-S3 as a 1x1, 2.4 GHz, 64-subcarrier device:
  <https://proceedings.neurips.cc/paper_files/paper/2025/file/f7c68372b3d39e8d7a093eb2edaaad87-Paper-Datasets_and_Benchmarks_Track.pdf>

## Dataset layout

Raw public corpus: `data/csi-bench/` (CC BY-NC-ND research use only).

The curated index is generated at:

```text
data/curated/esp32_s3_fall_v1/
├── manifest.csv
├── dataset_info.json
├── README.md
└── splits/
    ├── train.csv
    ├── validation.csv
    ├── test.csv
    └── excluded.csv
```

It points to the unmodified raw recordings instead of duplicating them. It
contains only `device_ESP32` FallDetection recordings and excludes subjects
without both fall and non-fall labels from validation. In the present corpus
there are 472 ESP32 recordings: 277 fall and 195 non-fall.

Additional downloaded corpora live separately under `data/external/`:

- `wifall/`: 928 ESP32-S3 recordings (464 fall, 464 non-fall), CSV frames
  with 104 raw I/Q bytes = 52 complex values. The public dataset card does not
  state a license, so keep it local and research-only. Its continuous records
  lack a verified fall-event timestamp; use only for representation learning or
  a separately reported ablation.
- `esp_fi_har/`: the downloaded repository subset has 560 ESP32-C3 amplitude
  recordings of shape `[950, 52]`, across eight people in one room. It is
  CC BY 4.0 and includes fall plus six other actions. It may be used for
  supervised multi-class pretraining.

Neither source can enter the SRASTA main test split or be used to claim final
performance. Hardware, room, collection pipeline, and labels differ. Fine-tune
on `esp32_s3_fall_v1` and evaluate only on its untouched held-out subjects,
then on a separately held-out local ESP32-S3 capture set. See
`data/external/README.md` and each source README for provenance and use rules.

## Recommended software architecture

```text
serial reader / recorded replay
        |
frame validator -> bounded queue -> amplitude decoder -> preprocessor
        |                                           |
   packet quality metrics                         ring buffer
                                                        |
                                              trigger + classifier
                                                        |
                                  state machine + SQLite event store
                                                        |
                                      FastAPI / WebSocket / Blynk adapter
```

Preprocessing order for V1:

1. Validate sender, config hash, `len`, receiver state, timestamp monotonicity
   and packet sequence.
2. Decode I/Q into 52 amplitude channels.
3. Resample using actual packet timestamps. Capture target is 100 Hz but do
   not assume it was achieved.
4. Apply a causal Hampel/outlier filter and low-pass filter. Tune cut-off with
   validation; start near 10 Hz for 100 Hz sampling.
5. Use room-baseline calibration to remove common gain drift. Do not apply
   arbitrary zero-padding or per-file feature resizing.
6. Compute a motion-energy trigger from amplitude differences.

## Model decision

For the submission, use **one final learned model: TCN-Lite INT8**. It consumes
a fixed `[T, 52]` amplitude sequence after the shared preprocessing and runs on
Raspberry Pi. Start with three residual 1-D temporal-convolution blocks
(kernel 3, 24 channels, dilations 1/2/4), global average pooling, and a
two-class head; train FP32 and export with a representative ESP32-S3 dataset to
full INT8 TensorFlow Lite. Tune window duration (`T`, initially 250 frames at
the 100 Hz capture target) only on grouped validation.

A motion trigger plus Random Forest is still useful as an internal debugging
baseline: derive peak derivative, temporal energy, variance, duration,
spectral entropy, and pre/post energy ratio. Do not present it as a competing
submission model unless the task explicitly asks for an ablation.

Do not start with LSTM/Transformer: this project has limited ESP32-specific
data, a small compute target, and an event that needs explainable debugging.
Use phase only as a future research experiment; raw ESP32-S3 1x1 phase is not
the V1 feature source.

`suspected_fall` may be emitted quickly after a motion trigger. Only emit
`confirmed_fall` after a separate inactivity timer. Do not claim that a
post-fall-inactivity decision has sub-500 ms end-to-end latency.

## First implementation milestones

1. Add a shared `csi_pipeline` module with decoder, validator, mask,
   preprocessing-config serializer, and H5/replay reader.
2. Add tests using one curated ESP32 recording.
3. Implement a group-aware Random Forest baseline from `manifest.csv` as a
   sanity check.
4. Implement the submission TCN-Lite, starting from reproducible grouped
   baseline/split results. Optional external pretraining must never modify the
   main test partition.
5. Replace the runtime CSI parsing path with a binary-frame parser plus replay
   mode; retain Blynk only as a notification adapter.
