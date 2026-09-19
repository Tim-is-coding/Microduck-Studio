"""Local person detector for the simulation (M2): finds the magenta marker that
`sim/make-scene.py` puts into the scene and turns it into a bearing.

Runs on every frame from `DuckBackend.frame()` (PNG or JPEG), 5–10 Hz, pure numpy — well
inside the 10–30 Hz budget for local detectors (§4) and never on the network. A real-person
detector (YOLO, `pngwn/microduck-detector`) plugs in behind the same `PersonDetection`.

Geometry: mediad reports the sensor as 640x360 with fx = fy ≈ 434.6 (logged at start-up,
docs/upstream-notes.md). The head camera is mounted a quarter turn off and `GET /frame`
already delivers the picture upright: 360 px wide, 640 px tall, floor at the bottom, so the
duck sees a tall, narrow slice of the world (≈45° wide, ≈72° high). Bearings come from the
horizontal pixel offset against the image centre with that focal length; the mock backend's
64x48 frame with a dark bar goes through the same code (`MockBarDetector`).
"""

from __future__ import annotations

import io
import math
import time

import numpy as np
from PIL import Image

from .base import PersonDetection

# mediad's reported focal length in pixels (upstream-notes: "camera geometry"); the same
# value holds after the quarter-turn because rotation does not change pixel size.
FX = 434.56
UPRIGHT_WIDTH = 360

MIN_AREA_PX = 40


def decode_upright(data: bytes) -> np.ndarray:
    """Decode an encoded frame to an RGB array (H, W, 3). Frames arrive upright already."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.asarray(img)


# The marker renders as (≈230, 0, ≈230); its reflection on the floor as (≈99, 84, 165) and the
# floor itself as (50, 83, 115). Tight thresholds keep the reflection out (sampled live).
def magenta_mask(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    return (r > 200) & (b > 200) & (g < 60)


# Width of what we call a person, for the range estimate from apparent width when the ToF has
# nothing in that column: the sim marker is a 0.24 m cylinder; a real person is wider.
PERSON_WIDTH_M = 0.24


def blob_to_detection(
    mask: np.ndarray,
    *,
    fx: float = FX,
    cx: float | None = None,
    timestamp: float | None = None,
) -> PersonDetection | None:
    ys, xs = np.nonzero(mask)
    area = int(xs.size)
    if area < MIN_AREA_PX:
        return None
    height, width = mask.shape
    cx = width / 2.0 if cx is None else cx
    px = float(xs.mean())
    py = float(ys.mean())
    # Pixel right of centre = target to the right = negative bearing (yaw positive is left).
    bearing = -math.atan2(px - cx, fx)
    # Confidence: how much of the blob's bounding box is filled (a cylinder is ~solid).
    blob_w = int(xs.max() - xs.min() + 1)
    bbox = blob_w * int(ys.max() - ys.min() + 1)
    confidence = min(1.0, area / bbox) if bbox else 0.0
    # Range from apparent width: 0.24 m at 1.5 m is ≈70 px with fx 434.6 (checked live).
    width_distance = PERSON_WIDTH_M * fx / blob_w if blob_w >= 4 else None
    return PersonDetection(
        timestamp=time.time() if timestamp is None else timestamp,
        bearing_rad=bearing,
        distance_m=width_distance,
        pixel_x=px,
        pixel_y=py,
        frame_width=int(width),
        frame_height=int(height),
        area_px=area,
        confidence=confidence,
    )


class MagentaPersonDetector:
    """Colour-blob detector for the simulated person marker."""

    def detect(self, frame: bytes, timestamp: float | None = None) -> PersonDetection | None:
        rgb = decode_upright(frame)
        return blob_to_detection(magenta_mask(rgb), timestamp=timestamp)


class MockBarDetector:
    """The mock backend's frame has one dark vertical bar; treat it as the person."""

    def detect(self, frame: bytes, timestamp: float | None = None) -> PersonDetection | None:
        rgb = decode_upright(frame)
        mask = rgb.sum(axis=2) < 150
        # 64 px wide mock frame: scale the focal length with the width so bearings are sane.
        return blob_to_detection(mask, fx=FX * rgb.shape[1] / UPRIGHT_WIDTH, timestamp=timestamp)


TOF_HALF_FOV_RAD = math.radians(22.5)  # 45° square field of view, 8x8 zones
TOF_RANGE_M = 3.9  # zones at the sensor's limit mean "nothing there"


def fuse_distance(
    detection: PersonDetection, tof_rows: list[list[float]] | None
) -> PersonDetection:
    """Prefer a ToF range over the width estimate — from the zone the person's image position
    points at, not the nearest zone in the column: the lower rows of an 8x8 sensor mounted
    ~0.2 m above the ground see the floor at 0.5–1.4 m, which used to win every time.

    Camera and ToF are assumed co-aligned (both in the head, both looking forward); the
    elevation of the blob's centre picks the ToF row, its bearing the column. The row above is
    tried too, because a person's centre often sits at or beyond the top of the ToF's view.
    """
    if tof_rows is None or not tof_rows:
        return detection
    if abs(detection.bearing_rad) > TOF_HALF_FOV_RAD:
        return detection
    rows, cols = len(tof_rows), len(tof_rows[0])
    col = int(round((0.5 - detection.bearing_rad / (2 * TOF_HALF_FOV_RAD)) * (cols - 1)))
    col = max(0, min(cols - 1, col))
    elevation = math.atan2(detection.frame_height / 2.0 - detection.pixel_y, FX)
    row = int(round((0.5 - elevation / (2 * TOF_HALF_FOV_RAD)) * (rows - 1)))
    candidates = [
        tof_rows[r][col]
        for r in (row, row - 1)
        if 0 <= r < rows and 0.05 < tof_rows[r][col] < TOF_RANGE_M
    ]
    if not candidates:
        return detection
    return detection.model_copy(update={"distance_m": min(candidates)})
