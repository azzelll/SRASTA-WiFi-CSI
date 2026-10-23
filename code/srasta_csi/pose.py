"""Bounded camera-pose summary: COCO-17 [y, x, score], never image pixels."""
from __future__ import annotations

import math
from numbers import Real

POSE_FORMAT = "movenet-coco17"


def validate_pose(value):
    """Validate and copy the only pose representation allowed off the edge."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"format", "keypoints"} or value["format"] != POSE_FORMAT:
        raise ValueError("Expected a MoveNet COCO-17 pose summary")
    points = value["keypoints"]
    if not isinstance(points, list) or len(points) != 17:
        raise ValueError("Pose must contain exactly 17 keypoints")
    normalized = []
    for point in points:
        if not isinstance(point, list) or len(point) != 3:
            raise ValueError("Each keypoint must contain [y, x, score]")
        if any(isinstance(number, bool) or not isinstance(number, Real) or
               not math.isfinite(number) or not 0 <= number <= 1 for number in point):
            raise ValueError("Pose coordinates and scores must be finite numbers in [0,1]")
        normalized.append([round(float(number), 4) for number in point])
    return {"format": POSE_FORMAT, "keypoints": normalized}
