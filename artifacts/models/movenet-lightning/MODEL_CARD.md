# MoveNet Lightning INT8 v4 — SRASTA camera adapter

Downloaded on 9 October 2026 from the official Google URL in the
[TensorFlow MoveNet tutorial](https://www.tensorflow.org/hub/tutorials/movenet):
`https://tfhub.dev/google/lite-model/movenet/singlepose/lightning/tflite/int8/4?lite-format=tflite`.

- SHA256: `cd7cc22fa946e5d146a7b98d496853e1923e22828d3972d579973f27f91bb105`
- Size: 2,894,840 bytes.
- Input: `[1,192,192,3]`, uint8 RGB pixels.
- Output: `[1,1,17,3]`, float32 `[y,x,confidence]` in normalized image coordinates.
- The RGB image is letterboxed from the full 640×480 camera view.
- The model estimates pose; it is not a trained fall classifier.
- Torso geometry gives supporting evidence (`horizontal`, `not_horizontal`,
  `uncertain`). Low-confidence, malformed or collapsed keypoints remain uncertain.
- No fall recall/specificity claim is derived from this model or a single picture.
- Source frames are transient local memory. The bounded measured COCO17 pose,
  outcome and timing can persist in SQLite/cloud for the matching event UID.
  The caregiver sees event evidence, not continuous video or current sleep.
- This reviewed snapshot is included in the 21 October handoff at user request.
- Google MoveNet model license: Apache-2.0; see `LICENSE` beside this card and
  the [Google model card](https://www.kaggle.com/models/google/movenet/tensorFlow2/singlepose-lightning/4).
