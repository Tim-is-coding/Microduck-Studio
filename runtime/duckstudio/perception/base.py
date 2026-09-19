"""Perception value types. Detectors write these into the executor's Snapshot at their own
rate (10–30 Hz local, 0.5–2 Hz VLM); the executor reads last-value-wins (§4, §6.4)."""

from __future__ import annotations

from ..common import Strict


class PersonDetection(Strict):
    """Where the nearest person is, in the duck's trunk frame."""

    timestamp: float
    bearing_rad: float  # positive = left (matches robot.move vyaw)
    distance_m: float | None  # None when no range source agreed with the bearing
    pixel_x: float  # in the upright camera image (360 wide, 640 tall on the duck)
    pixel_y: float
    frame_width: int
    frame_height: int
    area_px: int
    confidence: float  # 0..1
