"""Perception (§4): local detectors at 10–30 Hz, VLM at 0.5–2 Hz, never in the braking loop."""

from .base import PersonDetection
from .person_local import MagentaPersonDetector, MockBarDetector, fuse_distance
from .service import PerceptionService

__all__ = [
    "MagentaPersonDetector",
    "MockBarDetector",
    "PerceptionService",
    "PersonDetection",
    "fuse_distance",
]


def detector_for(backend_kind: str) -> MagentaPersonDetector | MockBarDetector:
    return MockBarDetector() if backend_kind == "mock" else MagentaPersonDetector()
