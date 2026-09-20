"""A Hub that answers from fixtures: the shapes really seen on huggingface.co on 2026-09-20,
including the ones we refuse (a manifest whose `command.twist` is prose, and one with no
command block at all)."""

from __future__ import annotations

import json
from typing import Any

import httpx

BASKETBALL = {
    "id": "HannesVonEssen/microduck-basketball",
    "author": "HannesVonEssen",
    "sha": "6d8f74b97c75b1597efead1754ff54ca2af4900c",
    "downloads": 172,
    "likes": 5,
    "lastModified": "2026-09-11T09:41:07.000Z",
    "tags": [
        "onnx",
        "microduck",
        "microduck-policy",
        "balance",
        "basketball",
        "license:apache-2.0",
    ],
    "cardData": {"thumbnail": "https://huggingface.co/x/media/social-preview.png"},
    "siblings": [{"rfilename": f} for f in ("policy.onnx", "manifest.json", "README.md")],
}

BASKETBALL_MANIFEST = {
    "schema_version": 2,
    "model_api": 2,
    "name": "microduck-basketball",
    "kind": "perpetual",
    "status": "experimental-hardware-test-candidate",
    "hardware_tested": False,
    "description": (
        "b11_6999 blind LSTM basketball balance; simulation validated, real robot untested."
    ),
    "command": {
        "layout": "twist(3), head_pose(4), body_pose(6)",
        "twist": (
            "Forward/lateral velocity and yaw rate; continuation ranges "
            "±0.15 m/s, ±0.10 m/s, ±0.50 rad/s"
        ),
    },
    "robot": {"model": "microduck", "control_hz": 50},
}

FLAMINGO = {
    "id": "RemiFabre/microduck-flamingo-cycle",
    "author": "RemiFabre",
    "sha": "aaaa1111",
    "downloads": 0,
    "likes": 28,
    "tags": ["onnx", "microduck-policy"],
    "siblings": [{"rfilename": f} for f in ("policy.onnx", "manifest.json")],
}

FLAMINGO_MANIFEST = {
    "schema_version": 2,
    "model_api": 1,
    "name": "flamingo-cycle",
    "entry_pose": "standing",
    "command": {
        "twist": [
            "flag: 0 = stand on two feet (HOME), 1 = stand on one foot",
            "side: +1 = right foot down, -1 = left foot down",
            "unused (0)",
        ]
    },
    "robot": {"model": "microduck", "control_hz": 50},
}

BARE = {
    "id": "cdeplanne/microduck-walk",
    "author": "cdeplanne",
    "sha": "bbbb2222",
    "downloads": 3,
    "likes": 0,
    "tags": ["onnx", "microduck-policy"],
    "siblings": [{"rfilename": "policy.onnx"}],  # no manifest.json at all
}

MODELS = {m["id"]: m for m in (BASKETBALL, FLAMINGO, BARE)}
MANIFESTS = {
    BASKETBALL["id"]: BASKETBALL_MANIFEST,
    FLAMINGO["id"]: FLAMINGO_MANIFEST,
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/models":
        search = request.url.params.get("search", "").lower()
        hits = [m for m in MODELS.values() if search in m["id"].lower()]
        return httpx.Response(200, json=hits)
    if path.startswith("/api/models/"):
        repo = path[len("/api/models/") :]
        model = MODELS.get(repo)
        return httpx.Response(200, json=model) if model else httpx.Response(404, json={})
    if path.endswith("/resolve/main/manifest.json"):
        repo = path[1 : -len("/resolve/main/manifest.json")]
        manifest = MANIFESTS.get(repo)
        return httpx.Response(200, json=manifest) if manifest else httpx.Response(404, text="nope")
    return httpx.Response(404, text=json.dumps({"path": path}))


def client(**kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
