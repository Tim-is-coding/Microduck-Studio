"""Finding real people on this machine: YOLOX-nano through onnxruntime (ADR-0010).

The magenta detector finds the simulation's marker and nothing else; upstream's detectors find
ducks. This one finds people — COCO class 0 — in any frame, locally, at the rate §4 wants for
local detectors, and no picture leaves the runtime.

The model is Megvii's `yolox_nano.onnx` from YOLOX release 0.1.1rc0 (Apache-2.0), 3.66 MB. It
is not in the repository: the Studio fetches it once, on a click (`ensure_model`), into
`~/.cache/duckstudio/models/` and checks its SHA-256 before it is ever loaded.

Post-processing is the one in the YOLOX source at that tag (`yolox/utils/demo_utils.py`,
`demo/ONNXRuntime/onnx_inference.py`). Pre-processing is **not** the one at that tag: its
`preproc` normalises with ImageNet mean/std, and the released file then scores nothing above
0.01. It answers to what later YOLOX versions feed it, checked on the repo's own
`assets/sunjian.png` (person 0.93) and `assets/dog.jpg` (dog 0.83, car 0.81, bicycle 0.81):

- letterbox into 416×416, top-left, padded with grey 114; **BGR, raw 0–255**, no
  normalisation; NCHW float32;
- the output (1, 3549, 85) is `[cx, cy, w, h, objectness, 80 class scores]` per grid cell and
  still needs the grid decode (strides 8, 16, 32); score = objectness × class score; NMS.

Inference takes tens of milliseconds, so `runs_in_thread` tells the perception service to call
it off the event loop that also ticks the executor.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image

from .base import PersonDetection
from .person_local import FX, UPRIGHT_WIDTH, decode_upright

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
)
MODEL_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
MODEL_BYTES = 3_659_407
MODEL_LICENSE = "Apache-2.0"
MODEL_NAME = "YOLOX-nano"

INPUT = 416
STRIDES = (8, 16, 32)
PERSON = 0  # COCO class index
SCORE_MIN = 0.35
NMS_IOU = 0.45
# Shoulder width, for a range from apparent width when the ToF has nothing there. Rough on
# purpose: the ToF is the range that counts (fuse_distance).
PERSON_WIDTH_M = 0.45


def model_path() -> Path:
    default = Path.home() / ".cache" / "duckstudio" / "models"
    base = os.environ.get("DUCKSTUDIO_MODELS") or str(default)
    return Path(base).expanduser() / "yolox_nano.onnx"


def model_ready(path: Path | None = None) -> bool:
    path = path or model_path()
    return path.is_file() and path.stat().st_size == MODEL_BYTES


class ModelDownloadError(RuntimeError):
    pass


async def ensure_model(
    path: Path | None = None, *, client: httpx.AsyncClient | None = None
) -> Path:
    """Fetch the model once, check it, and only then put it where it will be loaded from."""
    path = path or model_path()
    if model_ready(path) and _sha256(path) == MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    own = client is None
    client = client or httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    try:
        response = await client.get(MODEL_URL)
    except httpx.HTTPError as e:
        raise ModelDownloadError(f"unreachable: {type(e).__name__}") from e
    finally:
        if own:
            await client.aclose()
    if response.status_code != 200:
        raise ModelDownloadError(f"HTTP {response.status_code}")
    data = response.content
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise ModelDownloadError("checksum mismatch; the file was not kept")
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -- the maths, pure numpy (tested without a model) ------------------------------------------


def letterbox(rgb: np.ndarray) -> tuple[np.ndarray, float]:
    """(1, 3, 416, 416) float32 input and the scale that maps model pixels back to the frame."""
    h, w = rgb.shape[:2]
    r = min(INPUT / h, INPUT / w)
    nh, nw = int(h * r), int(w * r)
    resized = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.Resampling.BILINEAR))
    padded = np.full((INPUT, INPUT, 3), 114.0, dtype=np.float32)
    padded[:nh, :nw] = resized[:, :, ::-1]  # RGB → BGR, as the model was trained (cv2)
    return np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32), r


def _grids() -> tuple[np.ndarray, np.ndarray]:
    grids, strides = [], []
    for s in STRIDES:
        n = INPUT // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    return np.concatenate(grids).astype(np.float32), np.concatenate(strides).astype(np.float32)


GRID, GRID_STRIDE = _grids()


def people(output: np.ndarray, scale: float) -> list[tuple[float, float, float, float, float]]:
    """Decode (1, 3549, 85) into person boxes `(x0, y0, x1, y1, score)` in frame pixels."""
    pred = np.array(output[0], dtype=np.float32, copy=True)
    pred[:, :2] = (pred[:, :2] + GRID) * GRID_STRIDE
    pred[:, 2:4] = np.exp(pred[:, 2:4]) * GRID_STRIDE
    scores = pred[:, 4] * pred[:, 5 + PERSON]
    keep = scores > SCORE_MIN
    if not keep.any():
        return []
    b, s = pred[keep, :4], scores[keep]
    half_w, half_h = b[:, 2] / 2, b[:, 3] / 2
    corners = [b[:, 0] - half_w, b[:, 1] - half_h, b[:, 0] + half_w, b[:, 1] + half_h]
    boxes = np.stack(corners, axis=1) / scale
    out = []
    for i in _nms(boxes, s):
        x0, y0, x1, y1 = (float(v) for v in boxes[i])
        out.append((x0, y0, x1, y1, float(s[i])))
    return out


def _nms(boxes: np.ndarray, scores: np.ndarray) -> list[int]:
    x0, y0, x1, y1 = boxes.T
    areas = (x1 - x0 + 1) * (y1 - y0 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        w = np.maximum(0.0, np.minimum(x1[i], x1[order[1:]]) - np.maximum(x0[i], x0[order[1:]]) + 1)
        h = np.maximum(0.0, np.minimum(y1[i], y1[order[1:]]) - np.maximum(y0[i], y0[order[1:]]) + 1)
        iou = w * h / (areas[i] + areas[order[1:]] - w * h)
        order = order[1:][iou <= NMS_IOU]
    return keep


def nearest(
    boxes: list[tuple[float, float, float, float, float]], width: int, height: int, timestamp: float
) -> PersonDetection | None:
    """The biggest person is the nearest one; the same optics as the other detectors."""
    if not boxes:
        return None
    x0, y0, x1, y1, score = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    x0, x1 = max(0.0, x0), min(float(width), x1)
    y0, y1 = max(0.0, y0), min(float(height), y1)
    px, py = (x0 + x1) / 2, (y0 + y1) / 2
    fx = FX * width / UPRIGHT_WIDTH
    blob_w = max(1.0, x1 - x0)
    return PersonDetection(
        timestamp=timestamp,
        bearing_rad=-math.atan2(px - width / 2.0, fx),
        distance_m=PERSON_WIDTH_M * fx / blob_w,
        pixel_x=px,
        pixel_y=py,
        frame_width=int(width),
        frame_height=int(height),
        area_px=int(blob_w * max(1.0, y1 - y0)),
        confidence=score,
    )


class YoloxPersonDetector:
    """People, on this machine. Needs the model (`ensure_model`) and onnxruntime."""

    runs_in_thread = True
    name = "yolox"

    def __init__(self, path: Path | None = None, *, session: Any | None = None) -> None:
        self.path = path or model_path()
        self._session = session

    def _ensure_session(self) -> Any:
        if self._session is None:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = 2  # leave the rest of the machine to the rest
            self._session = ort.InferenceSession(
                str(self.path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            self._input = self._session.get_inputs()[0].name
        return self._session

    def detect(self, frame: bytes, timestamp: float | None = None) -> PersonDetection | None:
        session = self._ensure_session()
        rgb = decode_upright(frame)
        x, scale = letterbox(rgb)
        name = getattr(self, "_input", None) or session.get_inputs()[0].name
        (output,) = session.run(None, {name: x})
        h, w = rgb.shape[:2]
        return nearest(people(output, scale), w, h, time.time() if timestamp is None else timestamp)
