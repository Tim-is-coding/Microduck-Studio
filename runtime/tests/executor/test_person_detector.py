from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

from duckstudio.perception.base import PersonDetection
from duckstudio.perception.person_local import (
    FX,
    MagentaPersonDetector,
    blob_to_detection,
    fuse_distance,
)


def synthetic_frame(x0: int, x1: int) -> bytes:
    """A 360x640 upright frame with a magenta column between x0 and x1."""
    img = np.zeros((640, 360, 3), dtype=np.uint8)
    img[..., 2] = 110  # bluish background like the sim
    img[100:400, x0:x1] = (230, 0, 230)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def test_bearing_sign_and_range_from_width() -> None:
    det = MagentaPersonDetector()
    centred = det.detect(synthetic_frame(145, 215), timestamp=1.0)  # 70 px wide, centred
    assert centred is not None
    assert abs(centred.bearing_rad) < 0.01
    assert centred.distance_m is not None and math.isclose(
        centred.distance_m, 0.24 * FX / 70, rel_tol=0.02
    )
    left = det.detect(synthetic_frame(40, 110), timestamp=1.0)  # on the image's left
    assert left is not None and left.bearing_rad > 0.15  # left = positive, like vyaw
    right = det.detect(synthetic_frame(250, 320), timestamp=1.0)
    assert right is not None and right.bearing_rad < -0.15


def test_tiny_blobs_are_ignored() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:7, 5:8] = True
    assert blob_to_detection(mask, timestamp=0.0) is None


def test_tof_zone_at_the_blob_beats_the_floor_and_the_width_estimate() -> None:
    # blob centre 200 px above the image middle → elevation ≈ 24.7° → the ToF's top row
    d = PersonDetection(
        timestamp=0,
        bearing_rad=0.0,
        distance_m=1.4,
        pixel_x=180,
        pixel_y=120,
        frame_width=360,
        frame_height=640,
        area_px=999,
        confidence=0.9,
    )
    rows = [[4.0] * 8 for _ in range(8)]
    for r in range(3, 8):
        rows[r][3] = rows[r][4] = 0.4 + 0.2 * (7 - r)  # the floor, nearer in the lower rows
    rows[0][3] = rows[0][4] = 1.21  # the person, where the camera sees it
    assert fuse_distance(d, rows).distance_m == 1.21
    # nothing valid in that zone: keep the width estimate
    assert fuse_distance(d, [[4.0] * 8 for _ in range(8)]).distance_m == 1.4
    # out of the sensor's field of view: untouched
    wide = d.model_copy(update={"bearing_rad": 0.6})
    assert fuse_distance(wide, rows).distance_m == 1.4
