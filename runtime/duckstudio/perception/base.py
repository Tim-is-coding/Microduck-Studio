"""Perception value types. Detectors write these into the executor's Snapshot at their own
rate (10–30 Hz local, 0.5–2 Hz VLM); the executor reads last-value-wins (§4, §6.4)."""

from __future__ import annotations

import math

from ..common import Strict, Text


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
    # Where the duck stood when the frame was taken — odometry (x, y, heading), None if the
    # backend has none. A model answers a second or two late; `seen_now` makes up for it.
    seen_from: tuple[float, float, float] | None = None

    def seen_now(self, x: float, y: float, heading: float) -> Sighting:
        """This sighting from where the duck is now: moved and turned since the frame.

        Turning 20° left since the picture puts the thing 20° further right; walking 50 cm
        towards it brings it 50 cm closer. Without a range only the turn is made up for.
        """
        if self.seen_from is None:
            return self
        x0, y0, h0 = self.seen_from
        if self.distance_m is None:
            bearing = _wrap(self.bearing_rad - (heading - h0))
            return self.model_copy(update={"bearing_rad": bearing})
        # the thing in the world, as seen from the old pose
        wx = x0 + self.distance_m * math.cos(h0 + self.bearing_rad)
        wy = y0 + self.distance_m * math.sin(h0 + self.bearing_rad)
        dx, dy = wx - x, wy - y
        return self.model_copy(
            update={
                "bearing_rad": _wrap(math.atan2(dy, dx) - heading),
                "distance_m": math.hypot(dx, dy),
            }
        )


class PersonDetection(Sighting):
    """Where the nearest person is — local detector, every frame (§4: 10–30 Hz)."""


class TargetSighting(Sighting):
    """What a VLM was asked to find — 0.5–2 Hz, never in the braking loop (§4)."""

    label: Text  # the question, in the languages the behavior wrote it in (§3.7)
    source: str  # which provider answered, e.g. "anthropic" or "stub"


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
