# Fall engineering — 23 October 2026

## Scope and decision

Owner requested autonomous engineering until physical data collection is
needed, in this order: fall, local dataset, presence, validation, user
experience. Owner reports resilience acceptance passed. This checkpoint runs
software regressions, not another physical resilience acceptance.

No new candidate was promoted. The new raw-history Hampel ablation loses to
the grouped filtered-history comparison. Selected v8 model bytes/config and
production services are unchanged. New reports/plots/experiment checkpoints
remain local under ignored `artifacts/research/`.

## Reproduced baseline

Command:

```bash
PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 \
.venv/bin/python code/tools/diagnose_fall.py \
  --out-dir artifacts/research/20261023-fall-diagnostics
```

Selected INT8 SHA-256:
`ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.
Manifest SHA-256:
`088477e193c9ea5e1571cd6f36a2450ca888d7c075403cc8f403bc8f64129e29`.
Classifier cutoff 0.4500000000000001; motion floor 0.0003443831083131954.

Rows are truth nonfall/fall, columns predicted nonfall/fall:

| Split | N | After-gate confusion | Classifier-only FN | Additional gate FN |
| --- | ---: | --- | ---: | ---: |
| train, in-sample | 288 | `[[90,28],[53,117]]` | 51 | 2 |
| historical U19 development | 77 | `[[24,13],[15,25]]` | 15 | 0 |

Train predictions are from weights already fitted on those six people and
are **not OOF**. U19 is historically reused and only diagnoses the frozen
baseline here. No candidate selection/threshold search used U19 in the new
comparison. U21 test payloads were not opened.

Maximum rounded INT8 input saturation fraction is zero across all 365 rows.
Median normalized-clipping fraction is zero in both splits. Median Hampel
element-replacement fraction per recording is 20.32% train, 11.53% U19.
Replacement fraction alone is not proof of lost fall information; the
ablation tests that hypothesis. Plot derivative peaks are not annotated
onsets. H5 timing is nominal 100 Hz and establishes no live/event latency.

Outputs: `baseline_predictions.csv`, `report.json`, `protocol.json` and one
local SVG per TP/TN/FP/FN in each split. Source raw files are not modified.

## Bounded grouped ablation

Command (new output directory; a matching completed protocol can resume):

```bash
PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 \
.venv/bin/python code/train_fall_ablation.py \
  --out-dir artifacts/research/20261023-fall-hampel-ablation
```

Hypothesis: raw past Hampel samples may restore sustained changes suppressed
by recursive filtered history. Prior RF raw-history OOF improved, whereas the
prior TCN grid had no raw-history arm. Only this input-pipeline option changes.

Protocol is written before fitting. Six outer subject folds, three seeds
42/43/44, four fit subjects, cyclic next calibration subject, one evaluation
subject. Same v8 **architecture**, Adam 3e-4, batch 16, balanced fit class
weights, max35 epochs, patience6. This is a new comparison protocol, not
reproduction of v8's original training/selection procedure. Thresholds use
calibration only, targeting proposal 88%/80%; motion floor uses positive fit
rows only. All 288 primary train recordings receive exactly one outer-fold
prediction per seed. No validation/test payload is loaded by `compare`.

| Pipeline | Recall mean ± population SD | Specificity mean ± SD | Macro F1 mean |
| --- | ---: | ---: | ---: |
| filtered | 56.86% ± 4.08 pp | 51.41% ± 1.06 pp | 0.53897 |
| raw | 54.90% ± 4.30 pp | 50.56% ± 2.43 pp | 0.52446 |

| Held-out subject | Filtered recall/spec | Raw recall/spec |
| --- | --- | --- |
| U08 | 61.9 / 45.6% | 52.4 / 50.9% |
| U09 | 51.6 / 53.8% | 39.8 / 64.1% |
| U11 | 57.8 / 51.2% | 65.2 / 35.7% |
| U12 | 41.2 / 53.6% | 47.1 / 47.8% |
| U17 | 68.6 / 28.2% | 54.9 / 41.0% |
| U18 | 46.7 / 66.7% | 68.9 / 69.7% |

Total measured fit/calibrate/evaluate time: filtered 92.15 s, raw 93.03 s;
excludes imports and preprocessing. Fold/seed JSON preserves labels, IDs,
probabilities, thresholds, fit/calibration/evaluation provenance, epochs and
history. Exact fitting sources are copied under the local run's `source/` and
verified against the preregistered hashes. `stage_attribution.json` shows
classifier errors dominate: filtered adds 2/3/2 gate FN; raw adds 0/0/0, but its
classifier misses 87/72/71 falls across the three seeds.

Protocol SHA-256:
`feb3ffd4fd130b34cf7f847dac86a824a7bd823630876ecacb251ce110cf054c`.
Comparison SHA-256:
`ef0c53b85a7e0945ec5a5548ffbc0770beb87f59667cf7de5cff6071c5a3e615`.

Rule frozen before fitting: candidate must improve minimum normalized target
ratio without reducing either mean recall or specificity. It failed. The
`finalize` stage returned `No candidate eligible for refit/export`; no refit,
INT8 export or new U19 evaluation was performed. These OOF development results
do not establish event recall, FAR, camera validity or local generalization.

## Engineering prepared for local data

- `--protocol basic` preserves the original three-condition default.
- `adl` records one observed nonfall interval for the chosen duration.
- `motion` records normal → ≥61 s stationary preparation → inactive → normal.
- `fall-observer` checks an actual procedure reference and human readiness
  before opening serial, then saves four RX-clock marks with explicit
  `observer_keyboard_receiver_clock` provenance and reaction-time limitation.
- Independent-review CLI displays both post-event stillness bounds. Raw and
  original events are never rewritten by review.
- QA now treats the complete post-fall stillness interval as occupied by the
  fall; contradictory nonfall overlap is rejected.
- `evaluate_local_alerts.py --fall-events` performs one-to-one episode matching
  in a fixed 8 s local detection interval, rejects missing packet/inference
  coverage from the denominator with explicit counts, reports an exact 95%
  binomial interval and separates confirmation after ≥10 s stillness. Early
  confirmation is flagged. It does not measure cloud/phone delivery latency.
  The nominal binomial interval assumes independent events; it does not model
  repeated-event correlation within a person/session or replace cohort-level
  uncertainty on an independent local evaluation.
- `local_capture_readiness.py` reads split metadata before QA and skips
  test/pilot payloads. Reports accepted class/subject/profile coverage;
  readiness never claims achieved performance.

Readiness report: no accepted train or validation subjects, no eligible
negative duration. One train session pending independent review/provenance;
three test/pilot sessions skipped. Existing local-presence trainer preflight
also returns `ready_to_train=false`, 0/0 windows and test unopened. No pending
labels were fitted or relabelled. Local raw archive remains private.

## Fresh verification

Backend command:

```bash
PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 \
.venv/bin/python -m unittest discover -s code/tests -v
```

140 tests run, 139 passed, one Linux-only B1000000 test skipped on macOS.
New tests cover stage fidelity, miss attribution, quantization saturation,
candidate tradeoff rejection, test/pilot payload exclusion, procedure gate,
nonfall protocol routing, observer marks, post-fall overlap, detection
coverage, matching, uncertainty and premature confirmation. Log:
`/private/tmp/srasta-fall-engineering-tests-20261023.log`.
Handoff asset verifier: 32 checked, 0 failures. Recorder help exposes the new
protocols. Both evaluator modes return unavailable/exit1 on the actual pending
train archive. 62 relative documentation targets exist; `git diff --check`
passes. No frontend/cloud changes; no new web
build or deployment was needed. No real capture, physical acceptance or
production event was generated in this work.

The owner handoff is [FALL_ENGINEERING_HANDOFF.md](../FALL_ENGINEERING_HANDOFF.md).
