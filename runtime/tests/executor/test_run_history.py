"""What the Studio lists under „Letzte Läufe": every run that ended, newest first."""

from __future__ import annotations

from duckstudio.executor.tree import HISTORY_DEPTH

from .conftest import Harness


async def finish_follow_me(h: Harness) -> None:
    """The M2 run, start to „fertig"."""
    h.see_person(distance=0.5)
    await h.start()
    await h.tick()  # perceive
    await h.tick()  # walk: target already reached
    await h.tick(18)  # quack and its budget
    assert h.executor.state == "done", h.texts()


async def test_a_finished_run_is_remembered(h: Harness) -> None:
    await finish_follow_me(h)

    (run,) = h.executor.runs()
    assert run["behavior"] == "follow-me"
    assert run["name"]["de"] == "Folge mir"
    assert run["state"] == "done"
    assert run["steps_done"] == run["step_count"] == 3
    assert run["duration_s"] > 0
    assert run["started_at"] > 0
    assert run["reason"] is None


async def test_an_aborted_run_keeps_its_reason_and_where_it_stopped(h: Harness) -> None:
    h.see_person(distance=1.5)
    await h.start()
    await h.tick(3)  # into the walk
    await h.executor.abort("studio")

    (run,) = h.executor.runs()
    assert run["state"] == "aborted"
    assert run["steps_done"] == 1 and run["step_count"] == 3
    assert run["reason"] == {"de": "vom Studio gestoppt", "en": "stopped from the Studio"}


async def test_newest_first_and_bounded(h: Harness) -> None:
    for _ in range(HISTORY_DEPTH + 2):
        h.see_person(distance=1.5)
        await h.start()
        await h.tick(2)
        await h.executor.abort("studio")
    await finish_follow_me(h)

    runs = h.executor.runs()
    assert len(runs) == HISTORY_DEPTH
    assert runs[0]["state"] == "done"  # the newest is the one that finished
    assert all(r["state"] == "aborted" for r in runs[1:])


async def test_a_run_that_never_started_leaves_no_trace(h: Harness) -> None:
    await h.executor.abort("studio")  # nothing is running
    assert h.executor.runs() == []
