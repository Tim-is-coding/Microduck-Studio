"""Perception value types. Detectors write these into the executor's Snapshot at their own
rate (10–30 Hz local, 0.5–2 Hz VLM); the executor reads last-value-wins (§4, §6.4)."""

from __future__ import annotations

from ..common import Strict


class Sighting(Strict):
    """Something perception has seen, in the duck's trunk frame.

    Geometry is the same whoever looked: a bearing the executor can steer by, a range when
    a source agreed with it, and where it sat in the camera image.
    """

    timestamp: float
    bearing_rad: float  # positive = left (matches robot.move vyaw)
    distance_m: float | None  # None when no range source agreed with the bearing
    pixel_x: float  # in the upright camera image (360 wide, 640 tall on the duck)
    pixel_y: float
    frame_width: int
    frame_height: int
    area_px: int = 0  # 0 when the source pointed at a spot instead of outlining a blob
    confidence: float = 1.0  # 0..1


class PersonDetection(Sighting):
    """Where the nearest person is — local detector, every frame (§4: 10–30 Hz)."""


class TargetSighting(Sighting):
    """What a VLM was asked to find — 0.5–2 Hz, never in the braking loop (§4)."""

    label: str  # what was asked for, in the user's words
    source: str  # which provider answered, e.g. "anthropic" or "stub"
