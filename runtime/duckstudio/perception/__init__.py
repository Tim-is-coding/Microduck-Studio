"""Perception (§4): local detectors at 10–30 Hz, VLM at 0.5–2 Hz, never in the braking loop."""

from .base import PersonDetection, Sighting, TargetSighting
from .person_local import MagentaPersonDetector, MockBarDetector, fuse_distance
from .service import PerceptionService
from .vlm import (
    AnthropicVlm,
    StubVlm,
    VlmAnswer,
    VlmError,
    VlmNotConfigured,
    VlmProvider,
    make_vlm,
    sighting_from_answer,
    vlm_hz,
)

__all__ = [
    "AnthropicVlm",
    "MagentaPersonDetector",
    "MockBarDetector",
    "PerceptionService",
    "PersonDetection",
    "Sighting",
    "StubVlm",
    "TargetSighting",
    "VlmAnswer",
    "VlmError",
    "VlmNotConfigured",
    "VlmProvider",
    "detector_for",
    "fuse_distance",
    "make_vlm",
    "sighting_from_answer",
    "vlm_hz",
]


def detector_for(backend_kind: str) -> MagentaPersonDetector | MockBarDetector:
    return MockBarDetector() if backend_kind == "mock" else MagentaPersonDetector()
