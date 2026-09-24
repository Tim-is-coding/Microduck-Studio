"""The local person detector (ADR-0010), without the model: its maths, download and wiring."""

from __future__ import annotations

import asyncio
import hashlib
import math
import threading
from pathlib import Path

import httpx
import numpy as np
import pytest

from duckstudio.perception import (
    MagentaPersonDetector,
    MockBarDetector,
    PerceptionService,
    YoloxPersonDetector,
    detector_for,
    person_yolox,
)
from duckstudio.perception.person_yolox import (
    INPUT,
    ModelDownloadError,
    ensure_model,
    letterbox,
    nearest,
    people,
)

CELLS = sum((INPUT // s) ** 2 for s in (8, 16, 32))  # 3549


def output_with(*cells: tuple[int, float, float, float, float, float]) -> np.ndarray:
    """(1, 3549, 85) with the given stride-8 cells: (index, dx, dy, log_w, log_h, score)."""
    out = np.zeros((1, CELLS, 85), dtype=np.float32)
    for i, dx, dy, lw, lh, score in cells:
        out[0, i, :4] = (dx, dy, lw, lh)
        out[0, i, 4] = 1.0
        out[0, i, 5] = score  # class 0: person
    return out


def test_grid_decode_puts_the_box_where_the_cell_is() -> None:
    n = INPUT // 8  # 52 cells a row at stride 8
    i = 10 * n + 20  # row 10, column 20
    (box,) = people(output_with((i, 0.5, 0.5, math.log(10), math.log(20), 0.9)), scale=1.0)
    x0, y0, x1, y1, score = box
    assert (round((x0 + x1) / 2), round((y0 + y1) / 2)) == (164, 84)  # (20.5*8, 10.5*8)
    assert round(x1 - x0) == 80 and round(y1 - y0) == 160 and score == pytest.approx(0.9)
    (half,) = people(output_with((i, 0.5, 0.5, math.log(10), math.log(20), 0.9)), scale=0.5)
    assert round((half[0] + half[2]) / 2) == 328, "model pixels are scaled back to the frame"


def test_weak_scores_and_duplicates_are_dropped() -> None:
    n = INPUT // 8
    same = [
        (10 * n + 20, 0.5, 0.5, math.log(10), math.log(20), 0.9),
        (10 * n + 21, -0.5, 0.5, math.log(10), math.log(20), 0.8),  # the same person
        (30 * n + 5, 0.5, 0.5, math.log(5), math.log(5), 0.2),
    ]  # too unsure
    assert len(people(output_with(*same), 1.0)) == 1


def test_the_biggest_person_is_the_nearest_and_bearings_follow_the_other_detectors() -> None:
    small = (300.0, 100.0, 340.0, 200.0, 0.9)  # right of centre
    big = (40.0, 50.0, 200.0, 350.0, 0.6)  # left of centre, bigger
    p = nearest([small, big], width=480, height=360, timestamp=1.0)
    assert p is not None and p.pixel_x == 120.0 and p.bearing_rad > 0, "left is positive"
    assert p.confidence == 0.6 and p.distance_m and p.distance_m > 0
    assert nearest([], 480, 360, 1.0) is None


def test_letterbox_is_416_bgr_top_left() -> None:
    rgb = np.zeros((360, 480, 3), dtype=np.uint8)
    rgb[..., 0] = 200  # red
    x, scale = letterbox(rgb)
    assert x.shape == (1, 3, INPUT, INPUT) and x.dtype == np.float32
    assert scale == pytest.approx(INPUT / 480)
    assert x[0, 2, 0, 0] == pytest.approx(200) and x[0, 0, 0, 0] == 0, "channel 2 is red: BGR"
    assert x[0, 0, INPUT - 1, 0] == 114, "padding below the picture is grey 114"


async def test_the_model_is_kept_only_with_the_right_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = b"not really an onnx file, but it is the one we pinned"
    monkeypatch.setattr(person_yolox, "MODEL_SHA256", hashlib.sha256(good).hexdigest())
    monkeypatch.setattr(person_yolox, "MODEL_BYTES", len(good))
    served = {"body": b"something else entirely"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == person_yolox.MODEL_URL
        return httpx.Response(200, content=served["body"])

    target = tmp_path / "models" / "yolox_nano.onnx"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelDownloadError):
            await ensure_model(target, client=client)
        assert not target.exists() and not list(target.parent.glob("*.part"))
        served["body"] = good
        assert await ensure_model(target, client=client) == target
    assert target.read_bytes() == good and person_yolox.model_ready(target)


def test_who_finds_the_person(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("duckstudio.perception.model_ready", lambda: False)
    assert isinstance(detector_for("duck"), MagentaPersonDetector), "no model: the marker stands in"
    monkeypatch.setattr("duckstudio.perception.model_ready", lambda: True)
    assert isinstance(detector_for("duck"), YoloxPersonDetector)
    assert isinstance(detector_for("sim"), MagentaPersonDetector), "auto: the sim has a marker"
    assert isinstance(detector_for("mock"), MockBarDetector)
    assert isinstance(detector_for("sim", "people"), YoloxPersonDetector)


async def test_a_net_runs_off_the_event_loop(mock) -> None:
    from duckstudio.executor.conditions import Snapshot

    seen: list[int] = []

    class Slow:
        runs_in_thread = True

        def detect(self, frame: bytes, timestamp: float | None = None):
            seen.append(threading.get_ident())
            return None

    svc = PerceptionService(mock, Snapshot(), detector=Slow(), frame_hz=50)
    svc.start()
    try:
        for _ in range(100):
            await asyncio.sleep(0.01)
            if seen:
                break
    finally:
        await svc.close()
    assert seen and threading.get_ident() not in seen
