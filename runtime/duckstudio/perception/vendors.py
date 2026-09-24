"""AI vendors a person can bring a key for, and the router that picks one per question (ADR-0009).

A behavior names the vendor it may send frames to (`vlm: { provider: google }`, ADR-0004). The
router answers "who looks at this frame?": that vendor, if a key for it is there — else the
local stub, which sends nothing anywhere and says in the log that it stood in.

The catalogue is data the Studio renders its settings page from: names, where to get a key,
what it costs, which models make sense for "where is the thing". Facts in it were read from
the vendors' own pages on the date in `CHECKED` — they change, so they are dated, and the
links go to the page that is right, not to a copy of it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..keys import KeyStore
from .vlm import AnthropicVlm, StubVlm, VlmError, VlmProvider
from .vlm_rest import GEMINI_BASE, OPENAI_BASE, GeminiVlm, OpenAiVlm

log = logging.getLogger(__name__)

CHECKED = "2026-09-24"


class KeyCheckError(VlmError):
    """Why a key was not accepted. Never carries the key."""

    reason = "failed"


class KeyRejected(KeyCheckError):
    reason = "rejected"  # the vendor said no: wrong, revoked, or no access


class ModelUnavailable(KeyCheckError):
    reason = "model"  # the key works, this model is not available to it


class VendorUnreachable(KeyCheckError):
    reason = "unreachable"  # network or rate limit: try again, the key may be fine


@dataclass(frozen=True)
class ModelChoice:
    id: str
    note: dict[str, str]  # {de, en}: one line on why you would pick it


@dataclass(frozen=True)
class Vendor:
    id: str
    label: str
    env_var: str
    key_url: str
    docs_url: str
    pricing_url: str
    models: tuple[ModelChoice, ...]
    free_tier: bool
    recommended: bool
    note: dict[str, str]  # {de, en}: what to know before typing a key in
    make: Callable[[str, str], VlmProvider]  # (key, model) → provider
    check: Callable[[str, str], Awaitable[None]]  # (key, model); raises a KeyCheckError
    # Drafting behaviors from a sentence (ADR-0011): text only, a model good at structure.
    text_model: str = ""
    make_text: Callable[[str, str], Any] | None = None  # (key, model) → planner.TextModel
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def default_model(self) -> str:
        return self.models[0].id


def _planner() -> Any:
    from .. import planner  # late: the planner imports perception, perception imports this

    return planner


# -- Anthropic -------------------------------------------------------------------------------


async def _check_anthropic(key: str, model: str) -> None:
    """Does this key reach this model? `models.retrieve` costs nothing and checks both."""
    from anthropic import (
        APIConnectionError,
        AsyncAnthropic,
        AuthenticationError,
        NotFoundError,
        PermissionDeniedError,
        RateLimitError,
    )

    client = AsyncAnthropic(api_key=key, timeout=10.0, max_retries=0)
    try:
        await client.models.retrieve(model)
    except (AuthenticationError, PermissionDeniedError) as e:
        raise KeyRejected() from e
    except NotFoundError as e:
        raise ModelUnavailable(model) from e
    except (RateLimitError, APIConnectionError) as e:
        raise VendorUnreachable(type(e).__name__) from e
    finally:
        await client.close()


ANTHROPIC = Vendor(
    id="anthropic",
    label="Anthropic (Claude)",
    env_var="ANTHROPIC_API_KEY",
    key_url="https://platform.claude.com/settings/keys",
    docs_url="https://platform.claude.com/docs/en/build-with-claude/vision",
    pricing_url="https://platform.claude.com/docs/en/about-claude/pricing",
    models=(
        ModelChoice(
            "claude-opus-5",
            {"de": "Am gründlichsten.", "en": "The most thorough."},
        ),
        ModelChoice(
            "claude-sonnet-5",
            {"de": "Schneller und günstiger.", "en": "Faster and cheaper."},
        ),
        ModelChoice(
            "claude-haiku-4-5",
            {"de": "Am schnellsten und günstigsten.", "en": "Fastest and cheapest."},
        ),
    ),
    free_tier=False,
    recommended=False,
    note={
        "de": "Bezahlt nach Nutzung; eine Frage ans Bild kostet Bruchteile eines Cents.",
        "en": "Pay as you go; one question about a picture costs a fraction of a cent.",
    },
    make=lambda key, model: AnthropicVlm(api_key=key, model=model),
    check=_check_anthropic,
    text_model="claude-opus-5",
    make_text=lambda key, model: _planner().AnthropicText(api_key=key, model=model),
)

# -- Google, OpenAI: one GET on the model says whether the key reaches it ---------------------


async def _check_http(url: str, headers: dict[str, str]) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise VendorUnreachable(type(e).__name__) from e
    if response.status_code in (400, 401, 403):
        raise KeyRejected()
    if response.status_code == 404:
        raise ModelUnavailable(url.rsplit("/", 1)[-1])
    if response.status_code != 200:
        raise VendorUnreachable(f"HTTP {response.status_code}")


async def _check_google(key: str, model: str) -> None:
    await _check_http(f"{GEMINI_BASE}/models/{model}", {"x-goog-api-key": key})


async def _check_openai(key: str, model: str) -> None:
    await _check_http(f"{OPENAI_BASE}/models/{model}", {"Authorization": f"Bearer {key}"})


GOOGLE = Vendor(
    id="google",
    label="Google (Gemini)",
    env_var="GEMINI_API_KEY",
    key_url="https://aistudio.google.com/apikey",
    docs_url="https://ai.google.dev/gemini-api/docs/robotics-overview",
    pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
    models=(
        ModelChoice(
            "gemini-robotics-er-2-preview",
            {
                "de": "Für Roboter gebaut: zeigt auf Dinge im Bild. Vorschau.",
                "en": "Built for robots: points at things in the picture. Preview.",
            },
        ),
        ModelChoice(
            "gemini-3.5-flash-lite",
            {"de": "Schnell und sehr günstig.", "en": "Fast and very cheap."},
        ),
        ModelChoice(
            "gemini-3.8-flash",
            {"de": "Gründlicher, etwas langsamer.", "en": "More thorough, a little slower."},
        ),
    ),
    free_tier=True,
    recommended=True,
    note={
        "de": (
            "Zum Ausprobieren gibt es ein Gratis-Kontingent. Dann dürfen bei Google aber "
            "Menschen die Bilder ansehen, und Google nutzt sie für seine Produkte — also keine "
            "Bilder aus deiner Wohnung, auf denen Menschen zu sehen sind. Mit Abrechnung "
            "(bezahlt) gilt das nicht. Wer Duck Studio für andere in der EU anbietet, darf "
            "nur den bezahlten Dienst nutzen."
        ),
        "en": (
            "There is a free tier to try it. On it, people at Google may look at the pictures "
            "and Google uses them for its products — so no pictures from your home with people "
            "in them. With billing (paid) that does not apply. Offering Duck Studio to others "
            "in the EU requires the paid service."
        ),
    },
    make=lambda key, model: GeminiVlm(api_key=key, model=model),
    check=_check_google,
    text_model="gemini-3.8-flash",
    make_text=lambda key, model: _planner().GeminiText(api_key=key, model=model),
    extra={"terms_url": "https://ai.google.dev/gemini-api/terms"},
)

OPENAI = Vendor(
    id="openai",
    label="OpenAI (ChatGPT)",
    env_var="OPENAI_API_KEY",
    key_url="https://platform.openai.com/api-keys",
    docs_url="https://developers.openai.com/api/docs/guides/images-vision",
    pricing_url="https://developers.openai.com/api/docs/pricing",
    models=(
        ModelChoice(
            "gpt-6-luna",
            {"de": "Schnell und sehr günstig.", "en": "Fast and very cheap."},
        ),
        ModelChoice(
            "gpt-6-sol",
            {"de": "Gründlicher, teurer.", "en": "More thorough, more expensive."},
        ),
    ),
    free_tier=False,
    recommended=False,
    note={
        "de": (
            "Bezahlt nach Nutzung, kein Gratis-Kontingent. OpenAI schreibt selbst, dass seine "
            "Modelle Dinge im Bild nicht genau verorten — gut für Fragen ans Bild, weniger "
            "fürs Hinlaufen."
        ),
        "en": (
            "Pay as you go, no free tier. OpenAI itself says its models do not locate things "
            "in a picture precisely — good for questions about the picture, less so for "
            "walking to things."
        ),
    },
    make=lambda key, model: OpenAiVlm(api_key=key, model=model),
    check=_check_openai,
    text_model="gpt-6-sol",
    make_text=lambda key, model: _planner().OpenAiText(api_key=key, model=model),
)

# Order is the Studio's order: the recommended one first.
VENDORS: dict[str, Vendor] = {v.id: v for v in (GOOGLE, ANTHROPIC, OPENAI)}


def env_names() -> dict[str, str]:
    return {v.id: v.env_var for v in VENDORS.values()}


# -- the router ------------------------------------------------------------------------------


class VlmRouter:
    """Which provider answers a question for a behavior that named `vendor`."""

    def __init__(
        self,
        keys: KeyStore,
        stub: StubVlm,
        *,
        models: dict[str, str] | None = None,
        vendors: dict[str, Vendor] | None = None,
    ) -> None:
        self.keys = keys
        self.stub = stub
        self.models = dict(models or {})  # vendor → chosen model id
        self.vendors = vendors if vendors is not None else VENDORS
        self._cache: dict[str, tuple[str, str, VlmProvider]] = {}

    def model_for(self, vendor: str) -> str:
        v = self.vendors[vendor]
        chosen = self.models.get(vendor)
        return chosen or v.default_model

    def provider(self, vendor: str) -> VlmProvider | None:
        """The vendor's provider if a key is there, built once per key and model."""
        v = self.vendors.get(vendor)
        if v is None:
            return None
        key = self.keys.get(vendor)
        if not key:
            self._cache.pop(vendor, None)
            return None
        model = self.model_for(vendor)
        cached = self._cache.get(vendor)
        if cached is not None and cached[0] == key and cached[1] == model:
            return cached[2]
        made = v.make(key, model)
        self._cache[vendor] = (key, model, made)
        return made

    def resolve(self, vendor: str) -> VlmProvider:
        """The named vendor if it can answer, else the stub (which the log names as a stand-in)."""
        return self.provider(vendor) or self.stub

    def configured(self) -> list[str]:
        return [vid for vid in self.vendors if self.keys.get(vid)]
