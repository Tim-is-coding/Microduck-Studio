"""The same client against the real Hub. Skipped unless DUCKSTUDIO_HUB=1, like the sim
tests: it needs the network, and what it asserts is what we verified on 2026-09-20 —
`docs/upstream-notes.md` §Hub."""

from __future__ import annotations

import os

import pytest

from duckstudio.hub import HubClient, twist_limits

pytestmark = pytest.mark.skipif(
    os.environ.get("DUCKSTUDIO_HUB") != "1", reason="set DUCKSTUDIO_HUB=1 to talk to the Hub"
)


async def test_the_tag_still_finds_policies() -> None:
    hub = HubClient()
    try:
        found = await hub.search(limit=10)
        assert len(found) >= 5, "nobody tags microduck-policy any more?"
        assert all(p.repo.count("/") == 1 and p.url.startswith("https://") for p in found)
    finally:
        await hub.close()


async def test_a_known_repo_still_states_its_ranges() -> None:
    hub = HubClient()
    try:
        policy = await hub.details("HannesVonEssen/microduck-basketball")
        assert policy.policy_file == "policy.onnx"
        assert policy.hardware_tested is False
        assert twist_limits(policy.commands) == {"vx": 0.15, "vy": 0.10, "vyaw": 0.50}
    finally:
        await hub.close()
