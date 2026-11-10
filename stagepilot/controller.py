"""Convert synthetic detections into simulated motion; never connects to hardware."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Detection:
    x: float  # normalized center, left to right
    y: float  # normalized center, top to bottom
    height: float  # fraction of frame
    confidence: float


@dataclass(frozen=True)
class Motion:
    pan: float = 0.0  # positive means subject is right
    tilt: float = 0.0  # positive means subject is above target
    zoom: float = 0.0  # positive means subject is too small
    reason: str = "tracking"


def _axis(error: float, deadband: float, gain: float, limit: float) -> float:
    if abs(error) <= deadband:
        return 0.0
    return max(-limit, min(limit, error * gain))


def recommend(detection: Detection | None) -> Motion:
    """Fail closed on missing/invalid observations. Values are illustrative only."""
    if detection is None:
        return Motion(reason="target_lost")
    values = (detection.x, detection.y, detection.height, detection.confidence)
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in values) or detection.height == 0:
        return Motion(reason="invalid_detection")
    if detection.confidence < 0.6:
        return Motion(reason="low_confidence")
    return Motion(
        pan=_axis(detection.x - 0.5, 0.08, 0.8, 0.3),
        tilt=_axis(0.45 - detection.y, 0.08, 0.8, 0.3),
        zoom=_axis(0.45 - detection.height, 0.08, 0.5, 0.15),
    )
