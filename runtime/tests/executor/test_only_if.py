"""`only_if` (ADR-0012): a step runs only if its check holds, and says so when it does not."""

from __future__ import annotations

from typing import Any

import pytest

from duckstudio.behaviors import BehaviorPack
from duckstudio.executor.tree import CHECK_ASK_BUDGET_S, CHECK_PATIENCE_S
from duckstudio.perception.vlm import VlmAnswer
from duckstudio.skills import SkillRegistry

from .conftest import Harness


def pack(*steps: dict[str, Any], vlm: bool = False) -> BehaviorPack:
    data: dict[str, Any] = {
        "schema": "duckstudio.behavior/v0",
        "id": "t",
        "name": {"de": "Test", "en": "Test"},
        "trigger": {"kind": "manual"},
        "steps": list(steps),
    }
    if vlm:
        data["vlm"] = {"provider": "anthropic"}
    return BehaviorPack.model_validate(data)


QUACK = {"skill": "quack", "with": {"style": "short"}}


@pytest.fixture
async def make(registry: SkillRegistry):
    made: list[Harness] = []

    async def _make(p: BehaviorPack) -> Harness:
        h = Harness(registry, {p.id: p})
        await h.connect()
        made.append(h)
        return h

    yield _make
    for h in made:
        await h.executor.close()


def quacks(h: Harness) -> int:
    return sum(1 for c in h.mock.calls if c.kind == "behavior" and c.name == "quack")


def answer(h: Harness, found: bool, *, at: float | None = None) -> None:
    """What the perception service writes once the model answered the standing question."""
    h.executor.snapshot.vlm = VlmAnswer(
        timestamp=h.clock() if at is None else at,
        question="…",
        found=found,
        provider="anthropic",
        model="test",
        latency_s=1.0,
    )


async def test_runs_the_step_when_the_signal_holds(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"signal": "person_found"}}))
    h.see_person()
    await h.start("t")
    await h.tick(3)
    assert quacks(h) == 1
    assert h.executor.skipped == []


async def test_skips_the_step_and_says_why(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"signal": "person_found"}}, {"wait": "1s"}))
    h.see_nobody()
    await h.start("t")
    await h.tick()
    assert quacks(h) == 0
    assert h.executor.skipped == [0]
    assert h.executor.step_index == 1
    assert "Schritt 1 übersprungen: nur wenn jemand zu sehen ist." in h.texts()
    assert h.executor.status()["skipped"] == [0]


async def test_a_negated_check_reads_as_its_opposite(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"signal": "person_found == 0"}}))
    h.see_person()
    await h.start("t")
    await h.tick()
    assert "Schritt 1 übersprungen: nur wenn niemand zu sehen ist." in h.texts()
    assert h.executor.state == "done"


async def test_an_unknown_signal_gets_a_moment_then_the_step_is_skipped(make) -> None:
    """The ToF has not reported yet: wait a little rather than decide on nothing."""
    h = await make(pack({**QUACK, "only_if": {"signal": "tof_distance >= 0.5"}}))
    h.executor.snapshot.tof_min_m = None
    await h.start("t")
    await h.tick(int(CHECK_PATIENCE_S / 0.1) - 2)
    assert h.executor.skipped == [] and h.executor.status()["checking"] is True
    h.executor.snapshot.tof_min_m = 0.9
    await h.tick()
    assert h.executor.skipped == [] and h.executor.status()["checking"] is False
    await h.tick(2)
    assert quacks(h) == 1


async def test_unknown_for_too_long_skips(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"signal": "tof_distance >= 0.5"}}))
    h.executor.snapshot.tof_min_m = None
    await h.start("t")
    await h.tick(int(CHECK_PATIENCE_S / 0.1) + 2)
    assert h.executor.skipped == [0] and quacks(h) == 0
    assert any("nicht zu sagen, ob vorne 50 cm frei sind" in t for t in h.texts())


async def test_skipping_leaves_the_next_step_unchecked(make) -> None:
    """A skipped check must not carry over to a step that has none."""
    h = await make(pack({**QUACK, "only_if": {"signal": "person_found"}}, QUACK))
    h.see_nobody()
    await h.start("t")
    await h.tick(3)
    assert h.executor.skipped == [0]
    assert quacks(h) == 1


async def test_the_step_clock_starts_after_the_check(make) -> None:
    """A wait behind a slow check still waits its full time."""
    h = await make(pack({"wait": "1s", "only_if": {"signal": "tof_distance >= 0.5"}}))
    h.executor.snapshot.tof_min_m = None
    await h.start("t")
    await h.tick(10)  # one second spent checking
    h.executor.snapshot.tof_min_m = 2.0
    await h.tick(5)
    assert h.executor.state == "running"
    await h.tick(6)
    assert h.executor.state == "done"


# -- asking the model --------------------------------------------------------------------


async def test_ask_puts_a_yes_no_question_and_waits_for_the_answer(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"ask": {"de": "Liegt da ein Ball?"}}}, vlm=True))
    await h.start("t")
    asked = h.standing_question()
    assert asked is not None and asked.kind == "check" and asked.question == "Liegt da ein Ball?"
    assert asked.provider == "anthropic"
    assert any("Erst prüfen, ob die KI auf „Liegt da ein Ball?“ ja sagt" in t for t in h.texts())
    await h.tick(5)
    assert quacks(h) == 0 and h.executor.status()["checking"] is True
    answer(h, True)
    await h.tick(3)
    assert quacks(h) == 1
    assert "Die KI sagt ja." in h.texts()
    assert h.standing_question() is None, "the question is withdrawn once answered"


async def test_ask_no_skips(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"ask": {"de": "Liegt da ein Ball?"}}}, vlm=True))
    await h.start("t")
    await h.tick()
    answer(h, False)
    await h.tick()
    assert h.executor.skipped == [0] and quacks(h) == 0
    assert "Die KI sagt nein." in h.texts()


async def test_expect_no_turns_the_answer_around(make) -> None:
    step = {**QUACK, "only_if": {"ask": {"de": "Ist die Tür zu?"}, "expect": "no"}}
    h = await make(pack(step, vlm=True))
    await h.start("t")
    await h.tick()
    answer(h, False)
    await h.tick(3)
    assert quacks(h) == 1


async def test_an_answer_from_before_the_question_does_not_count(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"ask": {"de": "Liegt da ein Ball?"}}}, vlm=True))
    answer(h, True, at=h.clock() - 5.0)
    await h.start("t")
    await h.tick(3)
    assert quacks(h) == 0 and h.executor.status()["checking"] is True


async def test_no_answer_in_time_skips_and_warns(make) -> None:
    h = await make(pack({**QUACK, "only_if": {"ask": {"de": "Liegt da ein Ball?"}}}, vlm=True))
    await h.start("t")
    await h.tick(int(CHECK_ASK_BUDGET_S / 0.1) + 1)
    assert h.executor.skipped == [0]
    skipped = [e for e in h.bus.history if e.kind == "step.skipped"]
    assert skipped and skipped[0].level == "warn"
    assert "keine Antwort der KI" in skipped[0].text.de
    assert h.standing_question() is None


async def test_a_target_asked_for_earlier_comes_back_after_the_check(make) -> None:
    """Find the ball, then — only if it is on the floor — walk to it: the walk still needs
    the target question after the yes/no one."""
    h = await make(
        pack(
            {"perceive": "vlm.target", "question": {"de": "Wo ist der rote Ball?"}},
            {
                "skill": "walk",
                "with": {"direction": "toward_target", "tempo": "easy", "distance": 40},
                "only_if": {"ask": {"de": "Liegt der Ball auf dem Boden?"}},
            },
            vlm=True,
        )
    )
    await h.start("t")
    h.see_target(distance=2.0)
    await h.tick()
    assert h.executor.step_index == 1
    assert h.standing_question().kind == "check"
    answer(h, True)
    await h.tick()
    back = h.standing_question()
    assert back is not None and back.kind == "target" and back.question == "Wo ist der rote Ball?"


async def test_every_check_sentence_speaks_both_languages(make) -> None:
    h = await make(
        pack(
            {**QUACK, "only_if": {"signal": "person_found"}},
            {**QUACK, "only_if": {"ask": {"de": "Ball?", "en": "Ball?"}}},
            vlm=True,
        )
    )
    h.see_nobody()
    await h.start("t")
    await h.tick(int(CHECK_ASK_BUDGET_S / 0.1) + 3)
    for e in h.bus.history:
        if e.kind.startswith("step."):
            assert e.text.de and e.text.get("en") and e.text.de != e.text.get("en"), e.kind


def test_only_if_cannot_check_what_only_a_running_step_knows() -> None:
    with pytest.raises(ValueError, match="cannot check 'timeout'"):
        pack({**QUACK, "only_if": {"signal": "timeout"}})


def test_asking_needs_the_opt_in() -> None:
    with pytest.raises(ValueError, match="opt-in"):
        pack({**QUACK, "only_if": {"ask": {"de": "Ball?"}}})
