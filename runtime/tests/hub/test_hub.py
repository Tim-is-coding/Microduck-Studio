"""What we take from a Hub policy, and what we refuse to take (ADR-0005)."""

from __future__ import annotations

import pytest

from duckstudio.hub import (
    HubClient,
    HubError,
    display_name,
    guess_slot,
    skill_from_policy,
    skill_id_for,
    tighten,
    twist_limits,
)
from duckstudio.skills import SkillRegistry

from .fake_hub import client as fake_client


@pytest.fixture
async def hub():
    hub = HubClient(
        base="https://huggingface.co/api", web="https://huggingface.co", client=fake_client()
    )
    yield hub
    await hub.close()


async def test_search_returns_what_a_person_needs_to_judge_a_policy(hub: HubClient) -> None:
    found = await hub.search()
    assert {p.repo for p in found} == {
        "HannesVonEssen/microduck-basketball",
        "RemiFabre/microduck-flamingo-cycle",
        "cdeplanne/microduck-walk",
    }
    basketball = next(p for p in found if "basketball" in p.repo)
    assert basketball.author == "HannesVonEssen" and basketball.downloads == 172
    assert "license:apache-2.0" not in basketball.tags  # noise, not information
    assert basketball.url == "https://huggingface.co/HannesVonEssen/microduck-basketball"


async def test_details_read_the_repo_s_own_manifest(hub: HubClient) -> None:
    policy = await hub.details("HannesVonEssen/microduck-basketball")
    assert policy.hardware_tested is False
    assert policy.status == "experimental-hardware-test-candidate"
    assert policy.control_hz == 50 and policy.policy_file == "policy.onnx"
    assert "±0.15 m/s" in (policy.commands or "")
    assert policy.revision == "6d8f74b97c75b1597efead1754ff54ca2af4900c"


async def test_a_repo_without_a_manifest_is_still_usable_just_quieter(hub: HubClient) -> None:
    policy = await hub.details("cdeplanne/microduck-walk")
    assert policy.commands is None and policy.hardware_tested is None
    assert policy.policy_file == "policy.onnx"
    assert policy.slot_guess == "walk"  # from the repo's name, for a person to confirm


async def test_an_unreachable_hub_is_an_error_not_an_empty_list() -> None:
    hub = HubClient(client=fake_client())
    with pytest.raises(HubError):
        await hub.details("nobody/nothing")
    await hub.close()


def test_limits_are_only_read_when_a_machine_can_read_them() -> None:
    assert twist_limits(
        "Forward/lateral velocity and yaw rate; ranges ±0.15 m/s, ±0.10 m/s, ±0.50 rad/s"
    ) == {
        "vx": 0.15,
        "vy": 0.10,
        "vyaw": 0.50,
    }
    assert twist_limits("the walk's twist (vx, vy, yaw rate)") is None  # prose: no numbers
    assert twist_limits(None) is None


def test_our_clamps_are_never_widened_by_a_repo(registry: SkillRegistry) -> None:
    walk = registry.get("walk")
    tighter = tighten(walk.params, {"vx": 0.15, "vy": 0.10, "vyaw": 0.5})
    assert (tighter["vyaw"].min, tighter["vyaw"].max) == (-0.5, 0.5)  # narrower than ours
    wider = tighten(walk.params, {"vx": 9.0, "vy": 9.0, "vyaw": 9.0})
    assert (wider["vx"].min, wider["vx"].max) == (walk.params["vx"].min, walk.params["vx"].max)


def test_names_and_ids_read_like_a_studio_not_like_a_repo_path() -> None:
    assert display_name("microduck-rough-walk-e") == "Rough walk e"
    assert display_name("duckwing-v80-roller-skating") == "V80 roller skating"
    assert skill_id_for("HannesVonEssen/microduck-basketball", set()) == "basketball"
    assert skill_id_for("x/microduck-walk", {"walk"}) == "walk_2"  # no collisions


def test_the_slot_guess_is_a_guess_and_says_so_when_it_has_none() -> None:
    assert guess_slot("microduck-rough-walk-e") == "walk"
    assert guess_slot("microduck-beak-throw", "pick grasp") == "pickup"
    assert guess_slot("mystery-policy") is None


async def test_import_takes_behaviour_from_the_builtin_and_words_from_the_hub(
    hub: HubClient, registry: SkillRegistry
) -> None:
    policy = await hub.details("HannesVonEssen/microduck-basketball")
    skill = skill_from_policy(policy, registry.get("walk"), "basketball")

    assert skill.id == "basketball" and skill.name.de == "Basketball"
    assert skill.intent == registry.get("walk").intent  # what it does is ours
    assert skill.preconditions == registry.get("walk").preconditions
    assert skill.rate_hz == registry.get("walk").rate_hz
    assert (skill.params["vyaw"].min, skill.params["vyaw"].max) == (-0.5, 0.5)  # theirs, tighter
    assert skill.source.kind == "hub" and skill.source.repo == policy.repo
    assert skill.source.file == "policy.onnx" and skill.source.version == policy.revision
    assert "nicht auf Hardware getestet" in (skill.summary.de if skill.summary else "")
    assert "not hardware-tested" in (skill.summary.en or "" if skill.summary else "")


async def test_a_policy_driven_by_something_else_entirely_keeps_our_limits(
    hub: HubClient, registry: SkillRegistry
) -> None:
    """The flamingo's "twist" is a flag and a side, not a velocity. Nothing of it is read as
    a limit; the person picked `stand`, so `stand` is what it stands in for."""
    policy = await hub.details("RemiFabre/microduck-flamingo-cycle")
    assert twist_limits(policy.commands) is None
    skill = skill_from_policy(policy, registry.get("stand"), "flamingo_cycle")
    assert skill.behavior == registry.get("stand").behavior and not skill.params
