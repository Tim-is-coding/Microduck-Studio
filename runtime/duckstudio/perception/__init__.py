"""Perception (§4): local detectors at 10–30 Hz, VLM at 0.5–2 Hz, never in the braking loop."""

from . import person_yolox
from .base import PersonDetection, Sighting, TargetSighting
from .person_local import MagentaPersonDetector, MockBarDetector, fuse_distance
from .person_yolox import YoloxPersonDetector, model_ready
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
    "YoloxPersonDetector",
    "detector_for",
    "fuse_distance",
    "make_vlm",
    "person_yolox",
    "sighting_from_answer",
    "vlm_hz",
]


PersonDetectorMode = str  # "auto" | "people"


def detector_for(
    backend_kind: str, mode: PersonDetectorMode = "auto"
) -> MagentaPersonDetector | MockBarDetector | YoloxPersonDetector:
    """Who finds the person (ADR-0010).

    `auto`: the practice duck's drawn legs, the simulation's magenta marker, and real people on
    the real duck — if the model is there; without it the marker detector stands in and the
    Studio says what to load. `people`: the model on every backend, for trying it out.
    """
    wants_people = mode == "people" or backend_kind == "duck"
    if wants_people and model_ready():
        return YoloxPersonDetector()
    return MockBarDetector() if backend_kind == "mock" else MagentaPersonDetector()
