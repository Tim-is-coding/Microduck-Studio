"""„Geh zu dem Ding“ end to end against the mock duck: the VLM points, the duck walks there.

The VLM itself is not in this test — the perception service answers questions in its own
task (tests/executor/test_vlm_service.py); here the executor does what the executor does
with whatever sighting is in the snapshot.
"""

from __future__ import annotations

import math

from duckstudio import upstream

from .conftest import Harness


async def test_a_target_from_an_earlier_run_never_steers_a_new_one(h: Harness) -> None:
    h.see_target(bearing=0.6, distance=1.0)
    await h.start("go-to-thing")
    assert h.executor.snapshot.target is None
    await h.tick(2)
    assert h.executor.step_index == 0  # still looking, the old sighting is gone
    moves = [c for c in h.mock.intents_sent() if c.name == upstream.ROBOT_MOVE.name]
    assert moves == []


async def test_the_question_is_published_and_withdrawn_with_the_run(h: Harness) -> None:
    h.see_nothing()
    assert h.standing_question() is None
    await h.start("go-to-thing")
    await h.tick()
    request = h.standing_question()
    assert request is not None
    assert request.question == "Wo ist der rote Ball?"
    assert request.provider == "anthropic"  # what the behavior opted into, by name
    assert request.behavior_id == "go-to-thing"

    await h.executor.abort("studio")
    assert h.standing_question() is None  # nobody is asking any more, so nobody asks


async def test_the_question_keeps_standing_while_the_duck_walks_to_the_target(h: Harness) -> None:
    await h.start("go-to-thing")
    h.see_target(bearing=0.0, distance=2.0)  # the answer comes back
    await h.tick()
    assert h.executor.step_index == 1  # found it
    assert any("Ziel „Wo ist der rote Ball?“ gefunden" in t for t in h.texts()), h.texts()
    await h.tick(3)
    assert h.standing_question() is not None, "the walk needs fresh bearings, keep asking"
    moves = [c for c in h.mock.intents_sent() if c.name == upstream.ROBOT_MOVE.name]
    assert moves and moves[-1].params == {"vx": 0.08, "vy": 0.0, "vyaw": 0.0}


async def test_it_steers_by_the_vlm_target_not_by_a_person(h: Harness) -> None:
    await h.start("go-to-thing")
    h.see_target(bearing=0.6, distance=2.0)
    h.see_person(bearing=-0.6, distance=1.0)  # somebody stands the other way; ignore them
    await h.tick(2)
    move = h.mock.intents_sent()[-1].params
    assert math.isclose(move["vyaw"], 0.9)  # TURN_GAIN 1.5 * 0.6, towards the target
    assert 0 <= move["vx"] < 0.08


async def test_a_stale_target_stops_the_duck_but_keeps_the_heartbeat(h: Harness) -> None:
    await h.start("go-to-thing")
    h.see_target(bearing=0.0, distance=2.0)
    await h.tick(2)
    h.see_nothing()
    await h.tick(3)
    last = h.mock.intents_sent()[-1]
    assert last.name == upstream.ROBOT_MOVE.name
    assert last.params == {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
    assert h.executor.state == "running"


async def test_a_target_answer_older_than_three_asks_counts_as_gone(h: Harness) -> None:
    await h.start("go-to-thing")
    h.see_target(bearing=0.0, distance=2.0)
    await h.tick()
    await h.tick(70)  # 7 s without a new answer at 0.5 Hz → too old to steer by
    last = h.mock.intents_sent()[-1]
    assert last.params == {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}


async def test_nothing_in_sight_sweeps_then_finds_and_walks(h: Harness) -> None:
    h.see_nothing()
    await h.start("go-to-thing")
    await h.tick()
    assert "perceive.none" in h.kinds()
    assert any(t.startswith("Nichts gefunden: Umschauen") for t in h.texts()), h.texts()
    h.see_target(distance=1.0)
    await h.tick(2)
    assert h.executor.step_index == 1


async def test_reaching_the_thing_ends_the_walk_and_quacks(h: Harness) -> None:
    await h.start("go-to-thing")
    h.see_target(bearing=0.0, distance=2.0)
    await h.tick(3)
    h.see_target(bearing=0.0, distance=0.4)  # inside the 50 cm the card asks for
    await h.tick()
    assert h.executor.step_index == 2, h.texts()
    assert any("Ziel erreicht" in t for t in h.texts())
    await h.tick()
    assert h.mock.calls[-1].kind == "behavior" and h.mock.calls[-1].name == "quack"
    await h.tick(16)
    assert h.executor.state == "done"
    assert h.standing_question() is None  # done means the asking stops


async def test_stopp_ends_the_walk(h: Harness) -> None:
    await h.start("go-to-thing")
    h.see_target(distance=2.0)
    await h.tick(2)
    h.executor.say("Stopp")
    await h.tick()
    assert h.executor.step_index == 2
    assert any("du hast „Stopp“ gesagt" in t for t in h.texts())
