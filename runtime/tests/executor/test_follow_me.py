"""Follow-me end to end against the mock duck (M2 vertical slice, CLAUDE.md §8)."""

from __future__ import annotations

import math

from duckstudio import upstream

from .conftest import Harness


async def test_full_run_person_visible(h: Harness) -> None:
    h.see_person(bearing=0.0, distance=1.5)
    await h.start()
    assert h.executor.state == "running" and h.executor.step_index == 0
    await h.tick()  # perceive succeeds
    assert h.executor.step_index == 1
    assert "perceive.found" in h.kinds()

    # walking: one robot.move per tick, toward the person, vx from tempo `easy`
    await h.tick(5)
    moves = [c for c in h.mock.intents_sent() if c.name == upstream.ROBOT_MOVE.name]
    assert len(moves) == 5
    assert moves[-1].params == {"vx": 0.08, "vy": 0.0, "vyaw": 0.0}

    # the person is reached: distance drops to 0.5 m ≤ 60 cm target → step 2 ends
    h.see_person(distance=0.5)
    await h.tick()
    assert h.executor.step_index == 2, h.texts()
    assert any("Ziel erreicht" in t for t in h.texts())

    # quack is a named behavior sent once, then its 1.5 s budget runs out
    await h.tick()
    assert h.mock.calls[-1].kind == "behavior" and h.mock.calls[-1].name == "quack"
    await h.tick(16)
    assert h.executor.state == "done", h.texts()
    assert h.texts()[-1] == "„Folge mir“ fertig."


async def test_steers_toward_person(h: Harness) -> None:
    h.see_person(bearing=0.6, distance=2.0)  # 34° to the left → turn first
    await h.start()
    await h.tick(2)
    move = h.mock.intents_sent()[-1].params
    assert math.isclose(move["vyaw"], 0.9)  # TURN_GAIN 1.5 * 0.6
    assert 0 <= move["vx"] < 0.08  # slowed down while turning
    h.see_person(bearing=-0.1, distance=2.0)
    await h.tick()
    move = h.mock.intents_sent()[-1].params
    assert move["vyaw"] < 0 and move["vx"] == 0.08


async def test_holds_still_when_person_lost_but_keeps_heartbeat(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(2)
    h.see_nobody()
    await h.tick(3)
    last = h.mock.intents_sent()[-1]
    assert last.name == upstream.ROBOT_MOVE.name
    assert last.params == {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
    assert h.executor.state == "running"


async def test_nobody_found_sweeps_then_retries(h: Harness) -> None:
    h.see_nobody()
    await h.start()
    await h.tick()
    assert "perceive.none" in h.kinds()
    looks = [c for c in h.mock.intents_sent() if c.name == upstream.ROBOT_LOOK.name]
    assert len(looks) == 1 and looks[0].params["x"] == 1.0
    await h.tick(10)  # 1 s at rate_hz 5 → ~5 more look intents, not 10
    looks = [c for c in h.mock.intents_sent() if c.name == upstream.ROBOT_LOOK.name]
    assert 5 <= len(looks) <= 7
    await h.tick(45)  # past the 5 s sweep → retry → sweep again
    assert h.executor.state == "running" and h.executor.step_index == 0
    looks_after_retry = [c for c in h.mock.intents_sent() if c.name == upstream.ROBOT_LOOK.name]
    assert len(looks_after_retry) > len(looks)  # it really is still sweeping
    assert h.kinds().count("perceive.none") == 1  # said once, not once per sweep
    h.see_person(distance=1.0)
    await h.tick(2)
    assert h.executor.step_index == 1


async def test_stop_word_ends_the_walk(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(3)
    assert h.executor.step_index == 1
    assert h.executor.say("Stopp!") is None  # while running: fed to `until`, not a trigger
    await h.tick()
    assert h.executor.step_index == 2
    assert any("„Stopp“ gesagt" in t for t in h.texts())


async def test_elapsed_ends_the_walk(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(2)
    h.clock.tick(600.0)  # 10 minutes
    h.see_person(distance=2.0)  # keep the detection fresh
    await h.tick()
    assert h.executor.step_index == 2
    assert any("Zeit vorbei" in t for t in h.texts())


async def test_speech_trigger_when_idle(h: Harness) -> None:
    assert h.executor.say("Folge mir") == "follow-me"
    assert h.executor.say("komm mit.") == "follow-me"
    assert h.executor.say("Sitz!") is None


async def test_fall_triggers_getup_and_resumes(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(2)
    moves_before = len(h.mock.intents_sent())
    h.mock.push_over()
    await h.tick()  # interrupt starts, getup sent
    assert "interrupt.started" in h.kinds()
    assert h.mock.calls[-1].kind == "behavior" and h.mock.calls[-1].name == "getup"
    assert len(h.mock.intents_sent()) == moves_before, "no walking while down"
    await h.tick()  # mock is standing again → getup done → resume
    assert "interrupt.resumed" in h.kinds()
    assert h.executor.interrupt is None and h.executor.step_index == 1
    await h.tick()
    assert h.mock.intents_sent()[-1].name == upstream.ROBOT_MOVE.name
    assert h.executor.state == "running"


async def test_gamepad_preempts_and_stops(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(2)
    h.executor.preempt("gamepad")
    await h.tick()
    assert h.executor.state == "preempted"
    assert h.mock.calls[-1].kind == "stop"
    assert any("Gamepad übernimmt" in t for t in h.texts())
    await h.tick(3)
    assert h.mock.calls[-1].kind == "stop", "nothing goes out after preemption"


async def test_low_battery_fails_the_behavior_and_stops(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick()
    h.mock.set_battery(0.05)
    await h.tick()
    assert h.executor.state == "failed"
    assert h.mock.calls[-1].kind == "stop"
    assert any("Akku" in t for t in h.texts())


async def test_abort_from_studio(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(2)
    await h.executor.abort("studio")
    assert h.executor.state == "aborted" and h.mock.calls[-1].kind == "stop"


async def test_status_is_reportable(h: Harness) -> None:
    assert h.executor.status()["state"] == "idle"
    h.see_person(distance=2.0)
    await h.start()
    await h.tick(2)
    s = h.executor.status()
    assert s == {
        "state": "running",
        "behavior": "follow-me",
        "step_index": 1,
        "step_count": 3,
        "active_skill": "walk",
        "interrupt": None,
        "reason": None,
        "ticks": 2,
        "intents_sent": s["intents_sent"],
        "runs_recorded": 0,
    }
    assert math.isclose(s["intents_sent"], 1)


async def test_every_event_speaks_both_languages(h: Harness) -> None:
    """§3.7: the runtime sends German and English; the Studio picks. A missing translation
    would leave an English user reading German in the log."""
    h.see_person(bearing=0.3, distance=2.0)
    await h.start()
    await h.tick(6)
    h.see_nobody()
    await h.tick(4)
    h.executor.say("Stopp")
    await h.tick(3)
    assert len(h.bus.history) > 6
    missing = [e.kind for e in h.bus.history if not e.text.en]
    assert missing == [], f"events without an English text: {missing}"
    started = next(e for e in h.bus.history if e.kind == "behavior.started")
    assert started.text.de == "„Folge mir“ gestartet." and started.text.en == "“Follow me” started."


async def test_an_english_trigger_phrase_starts_the_behavior(h: Harness) -> None:
    assert h.executor.say("Follow me") == "follow-me"  # phrases.en, not just phrases.de
    assert h.executor.say("Folge mir") == "follow-me"
    assert h.executor.say("Tanz") is None
