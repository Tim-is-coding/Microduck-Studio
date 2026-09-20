"""Finding policies on the Hugging Face Hub, and turning one into a building block.

What is actually on the Hub (verified 2026-09-20 against the live API, `docs/upstream-notes.md`
§Hub): repos tagged `microduck-policy`, each with `policy.onnx` and usually a `manifest.json`
of its own. Those manifests are a community convention, not a standard — `schema_version`
runs 1…5, `model_api` 1…2, and the `command` block is a string in one repo, a list of
free-text lines in the next and missing in a third. One repo of twenty-five states its
velocity ranges in a form a machine can read.

So this module reads what is there and refuses to invent the rest:

  * search and provenance (author, downloads, likes, tags, preview, status) are shown as
    they come, as text, so a person can judge a policy;
  * an import never takes limits from the Hub unless they are machine-readable *and*
    tighter than ours — a policy that describes its commands in prose gets the bounds of the
    builtin skill it replaces (§7: our clamps are the only clamps);
  * which slot a policy replaces is a person's choice, pre-filled with a guess. Driving a
    "stand on one foot" policy as if its commands were walking speeds is exactly the kind of
    mistake that ends with a duck in a wall.

Loading the policy onto a duck (`robot.loadPolicy {slot, path}`) is M4 work; what we write
here is the manifest that says which policy a behavior means.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from .common import Strict, Text

log = logging.getLogger(__name__)

HUB_API = "https://huggingface.co/api"
HUB_WEB = "https://huggingface.co"
POLICY_TAG = "microduck-policy"
TIMEOUT_S = 10.0
MAX_RESULTS = 24
TEXT_LIMIT = 280  # Hub text is data (§10): shown, never trusted, never unbounded


class HubError(RuntimeError):
    """The Hub could not be reached or answered with something we cannot use."""


class HubPolicy(Strict):
    """One policy repo, as the Studio shows it."""

    repo: str  # <author>/<name>
    name: str
    author: str
    summary: str = ""
    tags: list[str] = []
    downloads: int = 0
    likes: int = 0
    updated: str | None = None
    url: str
    preview: str | None = None  # a picture the repo published for itself
    # from the repo's own manifest.json, when it has one
    status: str | None = None
    hardware_tested: bool | None = None
    commands: str | None = None  # what the policy says it is driven by, in its own words
    control_hz: int | None = None
    policy_file: str | None = None
    revision: str | None = None
    slot_guess: str | None = None  # which builtin skill it most likely replaces


def _clean(value: Any, limit: int = TEXT_LIMIT) -> str:
    """Hub text as text: one line, bounded, no markup games."""
    if not isinstance(value, str):
        return ""
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value)).strip()
    return flat[:limit].rstrip()


def _commands_text(command: Any) -> str | None:
    """`command.twist` is a sentence in one repo and a list of lines in the next."""
    if isinstance(command, dict):
        twist = command.get("twist")
        if isinstance(twist, str):
            return _clean(twist)
        if isinstance(twist, list):
            return _clean(" · ".join(str(t) for t in twist))
        layout = command.get("layout")
        if isinstance(layout, str):
            return _clean(layout)
    return None


# Which builtin skill a policy most likely replaces. A guess from the repo's own words, shown
# to a person to confirm — never applied on its own.
SLOT_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("walk", ("walk", "gait", "locomotion", "run", "stroll", "move-base-walk", "velstand")),
    ("kick", ("kick", "ball-kick", "shoot")),
    ("pickup", ("pick", "ground_pick", "grasp", "beak-throw")),
    ("sit", ("sit", "sitstand")),
    ("stand", ("stand", "balance", "flamingo", "stilts", "basketball")),
]


def guess_slot(*texts: str | None) -> str | None:
    haystack = " ".join(t.lower() for t in texts if t)
    for slot, words in SLOT_HINTS:
        if any(word in haystack for word in words):
            return slot
    return None


def _policy_file(siblings: list[dict[str, Any]]) -> str | None:
    names = [s.get("rfilename", "") for s in siblings]
    for candidate in ("policy.onnx", "model.onnx"):
        if candidate in names:
            return candidate
    return next((n for n in names if n.endswith(".onnx")), None)


class HubClient:
    """Read-only client for the public Hub API. No token, no uploads, no downloads."""

    def __init__(
        self, *, base: str = HUB_API, web: str = HUB_WEB, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base = base.rstrip("/")
        self.web = web.rstrip("/")
        self._client = client
        self._own_client = client is None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None and self._own_client:
            await self._client.aclose()
            self._client = None

    async def _get_json(self, url: str) -> Any:
        client = await self._http()
        try:
            response = await client.get(url, headers={"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise HubError(f"{type(e).__name__}: {e}") from e
        if response.status_code == 404:
            raise HubError(f"not found: {url}")
        if response.status_code >= 400:
            raise HubError(f"HTTP {response.status_code} from the Hub")
        try:
            return response.json()
        except ValueError as e:
            raise HubError("the Hub did not answer with JSON") from e

    async def search(self, query: str = "", limit: int = 12) -> list[HubPolicy]:
        """Policies tagged `microduck-policy`, most downloaded first."""
        limit = max(1, min(MAX_RESULTS, limit))
        url = f"{self.base}/models?filter={POLICY_TAG}&sort=downloads&direction=-1&limit={limit}"
        if query.strip():
            url += f"&search={httpx.QueryParams({'q': query.strip()})['q']}"
        models = await self._get_json(url)
        if not isinstance(models, list):
            raise HubError("the Hub's answer was not a list of models")
        return [p for p in (self._from_model(m) for m in models) if p is not None]

    def _from_model(self, model: Any) -> HubPolicy | None:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            return None
        repo = model["id"]
        author, _, name = repo.partition("/")
        card = model.get("cardData") if isinstance(model.get("cardData"), dict) else {}
        tags = [_clean(t, 40) for t in model.get("tags", []) if isinstance(t, str)]
        return HubPolicy(
            repo=repo,
            name=_clean(name, 80) or repo,
            author=_clean(author, 80),
            tags=[t for t in tags if t and not t.startswith(("license:", "region:"))][:8],
            downloads=int(model.get("downloads") or 0),
            likes=int(model.get("likes") or 0),
            updated=_clean(model.get("lastModified"), 40) or None,
            url=f"{self.web}/{repo}",
            preview=_clean(card.get("thumbnail"), 300) or None if isinstance(card, dict) else None,
            revision=_clean(model.get("sha"), 40) or None,
            slot_guess=guess_slot(name, " ".join(tags)),
        )

    async def details(self, repo: str) -> HubPolicy:
        """One repo, enriched with whatever its own `manifest.json` is willing to say."""
        model = await self._get_json(f"{self.base}/models/{repo}")
        policy = self._from_model(model)
        if policy is None:
            raise HubError(f"{repo}: the Hub returned no usable model")
        siblings = model.get("siblings") if isinstance(model.get("siblings"), list) else []
        policy.policy_file = _policy_file(siblings)
        manifest = await self._manifest(repo, siblings)
        if manifest:
            policy.summary = _clean(manifest.get("description")) or policy.summary
            policy.status = _clean(manifest.get("status"), 80) or None
            tested = manifest.get("hardware_tested")
            policy.hardware_tested = tested if isinstance(tested, bool) else None
            policy.commands = _commands_text(manifest.get("command"))
            robot = manifest.get("robot") if isinstance(manifest.get("robot"), dict) else {}
            hz = robot.get("control_hz") if isinstance(robot, dict) else None
            policy.control_hz = int(hz) if isinstance(hz, int) else None
            policy.slot_guess = guess_slot(
                policy.name,
                _clean(manifest.get("name"), 80),
                policy.commands,
                " ".join(policy.tags),
            )
        return policy

    async def _manifest(self, repo: str, siblings: list[dict[str, Any]]) -> dict[str, Any] | None:
        names = {s.get("rfilename") for s in siblings}
        if "manifest.json" not in names:
            return None
        try:
            data = await self._get_json(f"{self.web}/{repo}/resolve/main/manifest.json")
        except HubError as e:
            log.info("%s: no readable manifest.json (%s)", repo, e)
            return None
        return data if isinstance(data, dict) else None


# -- turning a policy into a building block ------------------------------------------------

# "±0.15 m/s, ±0.10 m/s, ±0.50 rad/s" — the one machine-readable form seen in the wild.
_RANGES = re.compile(
    r"±\s*(?P<vx>\d+(?:\.\d+)?)\s*m/s[^±]*±\s*(?P<vy>\d+(?:\.\d+)?)\s*m/s[^±]*±\s*(?P<vyaw>\d+(?:\.\d+)?)\s*rad/s"
)


def twist_limits(commands: str | None) -> dict[str, float] | None:
    """The policy's own velocity limits, when it states them in a form we can read."""
    if not commands:
        return None
    m = _RANGES.search(commands)
    if not m:
        return None
    return {k: float(v) for k, v in m.groupdict().items()}


def skill_id_for(repo: str, taken: set[str]) -> str:
    """`HannesVonEssen/microduck-basketball` → `basketball`, without colliding."""
    name = repo.partition("/")[2] or repo
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    while (stripped := re.sub(r"^(microduck|duckwing|move_base)_", "", slug)) != slug:
        slug = stripped
    slug = slug or "policy"
    if not slug[0].isalpha():
        slug = f"policy_{slug}"
    slug = slug[:48]
    candidate = slug
    n = 2
    while candidate in taken:
        candidate = f"{slug}_{n}"
        n += 1
    return candidate


def display_name(repo_name: str) -> str:
    """`microduck-rough-walk-e` → `Rough walk e`: a card title, not a repo path."""
    words = re.sub(r"^(microduck|duckwing|move[-_]base)[-_]", "", repo_name.strip())
    words = re.sub(r"[-_]+", " ", words).strip()
    return (words[:1].upper() + words[1:])[:60] or repo_name[:60]


def summary_for(policy: HubPolicy) -> Text:
    """What the card says under the name: the policy's own words plus where it stands."""
    de = [policy.summary] if policy.summary else []
    en = list(de)
    de.append(f"Policy von {policy.repo} (Hugging Face).")
    en.append(f"Policy from {policy.repo} (Hugging Face).")
    if policy.hardware_tested is False:
        de.append("Laut Repo nicht auf Hardware getestet.")
        en.append("The repo says it is not hardware-tested.")
    return Text(de=" ".join(de)[:400], en=" ".join(en)[:400])


def tighten(params: dict[str, Any], limits: dict[str, float] | None) -> dict[str, Any]:
    """Our bounds, narrowed by the policy's own if it states tighter ones.

    Never widened: §7 says the manifest's `params` are the only limits a movement intent
    has, and a repo on the internet does not get to raise them.
    """
    if not limits:
        return params
    out = {}
    for key, spec in params.items():
        limit = limits.get(key)
        if limit is None or spec.min is None or spec.max is None:
            out[key] = spec
            continue
        out[key] = spec.model_copy(
            update={"min": max(spec.min, -limit), "max": min(spec.max, limit)}
        )
    return out


def skill_from_policy(policy: HubPolicy, template: Any, skill_id: str) -> Any:
    """A building block that means "this policy, in the slot `template` drives".

    Everything that decides what the duck does — intent, param bounds, preconditions, end
    conditions, tick rate — is copied from the builtin skill a person picked. From the Hub
    come the name, the description and the provenance, as text.
    """
    from .skills.manifest import SkillManifest

    limits = twist_limits(policy.commands)
    name = display_name(_clean(policy.name, 80)) or skill_id
    data = template.model_dump(by_alias=True, mode="python")
    data.update(
        {
            "id": skill_id,
            "name": {"de": name, "en": name},
            "summary": summary_for(policy).model_dump(),
            "source": {
                "kind": "hub",
                "repo": policy.repo,
                "file": policy.policy_file or "policy.onnx",
                "version": policy.revision,
            },
        }
    )
    manifest = SkillManifest.model_validate(data)
    return manifest.model_copy(update={"params": tighten(manifest.params, limits)})
