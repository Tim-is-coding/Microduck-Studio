"""The executor: runs a behavior pack as a vertical step list with side branches (§3.2).

One tick (10 Hz, §6.4):
  1. refresh step context in the shared Snapshot (elapsed, budget, target distance),
  2. gamepad preemption → stop and hand over,
  3. `always` rules (interrupts) are checked before the active node; while one runs, the
     step waits; `resume` returns to it,
  4. the active step: perceive / skill / wait — each skill run checks its end conditions
     (`until`, manifest `terminates_on`) first and only then sends at most one intent or
     behavior through the IntentGate, honouring the manifest's `rate_hz`,
  5. speech heard this tick is consumed, the watchdog is petted.

Movement intents are resent every tick while a walk step is active: that IS the heartbeat
robotd's 500 ms deadman wants (docs/upstream-notes.md). Every transition emits an Event with
German text for the Studio log.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .. import texts, upstream
from ..backends.base import BackendError, BehaviorRefused
from ..behaviors.schema import (
    RESERVED_ACTIONS,
    AlwaysRule,
    BehaviorPack,
    ElapsedCondition,
    PerceiveStep,
    SignalCondition,
    SkillStep,
    SpeechCondition,
    SpeechTrigger,
    StopCondition,
    Until,
    WaitStep,
)
from ..common import Condition, Text, parse_duration
from ..events import EventBus
from ..perception.base import Sighting
from ..skills import SkillManifest, SkillRegistry
from .conditions import Snapshot, VlmRequest, evaluate
from .safety import GateDecision, IntentGate
from .watchdog import Watchdog


class Status(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


class ExecutorBusy(RuntimeError):
    pass


HISTORY_DEPTH = 10  # what the Studio lists under „Letzte Läufe"
DEFAULT_INTENT_BUDGET_S = 120.0
DEFAULT_BEHAVIOR_BUDGET_S = 10.0
QUICK_BEHAVIOR_BUDGET_S = 1.5  # behaviors whose only end is `timeout` (quack)
PERCEIVE_BUDGET_S = 30.0
PRECONDITION_PATIENCE_S = 5.0  # how long a step may wait for e.g. `standing`
MAX_SAME_INTERRUPT = 3
TURN_GAIN = 1.5
TURN_FIRST_RAD = 0.35
SLOWDOWN_ZONE_M = 0.3
FAILING_SIGNALS = frozenset({"fallen", "motor_hot"})
# `direction` in a skill card → which sighting the step steers by (§6.1 walk.ui.direction)
STEERING = {"toward_person": "person", "toward_target": "target"}


def normalize_phrase(text: str) -> str:
    return " ".join(text.casefold().strip().strip(".!?,;:").split())


@dataclass
class RunRecord:
    """What a finished run looked like, for the Studio's „Letzte Läufe" (§6.4: a run is only
    useful if you can tell afterwards what it did)."""

    behavior: str
    name: Text
    started_at: float  # wall clock, for the Studio's list
    duration_s: float  # monotonic, so a clock change cannot bend it
    state: str
    steps_done: int
    step_count: int
    reason: texts.Bilingual | None

    def payload(self) -> dict[str, Any]:
        return {
            "behavior": self.behavior,
            "name": self.name.model_dump(mode="json"),
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "state": self.state,
            "steps_done": self.steps_done,
            "step_count": self.step_count,
            "reason": {"de": self.reason[0], "en": self.reason[1]} if self.reason else None,
        }


@dataclass
class SkillRun:
    skill: SkillManifest
    params: dict[str, float]
    extras: dict[str, Any]
    until: Until | None
    budget_s: float | None
    started: float
    last_sent: float | None = None
    sent_behavior: bool = False
    refused_since: float | None = None
    last_decision: GateDecision | None = None
    end_reason: texts.Bilingual | None = None


@dataclass
class InterruptRun:
    rule: AlwaysRule
    actions: list[str]
    started: float
    index: int = 0
    run: SkillRun | None = None


@dataclass
class _Counters:
    same_interrupt: int = 0
    last_interrupt_signal: str | None = None
    ticks: int = 0
    intents_sent: int = 0


class Executor:
    def __init__(
        self,
        registry: SkillRegistry,
        gate: IntentGate,
        bus: EventBus,
        *,
        packs: dict[str, BehaviorPack] | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], float] = time.time,
        tick_hz: float = 10.0,
        watchdog: Watchdog | None = None,
    ) -> None:
        self.registry = registry
        self.gate = gate
        self.bus = bus
        self.packs = packs or {}
        self.clock = clock
        self.tick_hz = tick_hz
        self.snapshot: Snapshot = gate.snapshot
        self.watchdog = watchdog or Watchdog(gate.stop, bus, clock=clock, on_trip=self._on_watchdog)
        self.state = "idle"  # idle | running | done | failed | aborted | preempted
        self.pack: BehaviorPack | None = None
        self.step_index = -1
        self.step_started = 0.0
        self.run: SkillRun | None = None
        self.on_none_run: SkillRun | None = None
        self.interrupt: InterruptRun | None = None
        self.reason: texts.Bilingual | None = None
        self._announced_none = False  # "nothing found" is worth saying once, not every sweep
        self.counters = _Counters()
        self.history: deque[RunRecord] = deque(maxlen=HISTORY_DEPTH)
        self.runs_recorded = 0  # ever, so the Studio can tell a new record from a poll it missed
        self._started_at = 0.0
        self._started_mono = 0.0
        self.now = now
        self._preempt_source: str | None = None
        self._driving_this_tick = False
        self._task: asyncio.Task[None] | None = None

    # -- control -------------------------------------------------------------------------

    async def start(self, pack: BehaviorPack) -> None:
        if self.state == "running":
            raise ExecutorBusy(f"{self.pack.id if self.pack else '?'} is running")
        self.pack = pack
        self.state = "running"
        self.reason = None
        self.step_index = 0
        self.step_started = self.clock()
        self.run = self.on_none_run = None
        self.interrupt = None
        self._announced_none = False
        self.counters = _Counters()
        self._started_at = self.now()
        self._started_mono = self.clock()
        self._preempt_source = None
        self.snapshot.speech.clear()
        self._clear_vlm_request()
        self.snapshot.target = self.snapshot.vlm = None
        self.bus.emit("behavior.started", *texts.behavior_started(pack.name), behavior=pack.id)
        self._announce_step()
        self.watchdog.start()
        self._task = asyncio.create_task(self._loop(), name=f"executor-{pack.id}")

    async def abort(self, reason: str = "studio") -> None:
        if self.state != "running":
            return
        self.state = "aborted"
        self._clear_vlm_request()
        self.reason = texts.stopped_from(reason)
        self._record_run()
        self.watchdog.disarm()
        await self.gate.stop()
        self.bus.emit("behavior.aborted", *texts.behavior_aborted(), level="warn", reason=reason)
        await self._cancel_loop()

    def preempt(self, source: str = "gamepad") -> None:
        """Physical controller wins (§4). Takes effect on the next tick, at most 100 ms away."""
        if self.state == "running":
            self._preempt_source = source

    def say(self, text: str) -> str | None:
        """Speech heard. While running it feeds `until: speech` conditions; when idle it may
        trigger a behavior and returns that behavior's id."""
        phrase = normalize_phrase(text)
        if not phrase:
            return None
        if self.state == "running":
            self.snapshot.speech.add(phrase)
            self.bus.emit("speech.heard", *texts.speech_heard(text), text=text)
            return None
        for pack in self.packs.values():
            if isinstance(pack.trigger, SpeechTrigger) and any(
                normalize_phrase(p) == phrase for p in pack.trigger.phrases.all()
            ):
                return pack.id
        return None

    def _record_run(self) -> None:
        """Called wherever a run leaves `running` — done, failed, aborted, preempted."""
        if self.pack is None:
            return
        self.runs_recorded += 1
        self.history.appendleft(
            RunRecord(
                behavior=self.pack.id,
                name=self.pack.name,
                started_at=self._started_at,
                duration_s=max(0.0, self.clock() - self._started_mono),
                state=self.state,
                steps_done=min(max(self.step_index, 0), len(self.pack.steps)),
                step_count=len(self.pack.steps),
                reason=self.reason,
            )
        )

    def runs(self) -> list[dict[str, Any]]:
        """Newest first."""
        return [r.payload() for r in self.history]

    def status(self) -> dict[str, Any]:
        active = self.run or self.on_none_run
        interrupt_run = self.interrupt.run if self.interrupt else None
        return {
            "state": self.state,
            "behavior": self.pack.id if self.pack else None,
            "step_index": self.step_index if self.state == "running" else None,
            "step_count": len(self.pack.steps) if self.pack else 0,
            "active_skill": (interrupt_run or active).skill.id
            if (interrupt_run or active)
            else None,
            "interrupt": self.interrupt.rule.on if self.interrupt else None,
            "reason": {"de": self.reason[0], "en": self.reason[1]} if self.reason else None,
            "ticks": self.counters.ticks,
            "intents_sent": self.counters.intents_sent,
            "runs_recorded": self.runs_recorded,
        }

    async def close(self) -> None:
        await self._cancel_loop()
        await self.watchdog.close()

    # -- loop ------------------------------------------------------------------------------

    async def _loop(self) -> None:
        period = 1.0 / self.tick_hz
        while self.state == "running":
            t0 = self.clock()
            try:
                await self.tick()
            except BackendError as e:
                await self._fail(texts.connection_lost(str(e)), stop=True)
                break
            except Exception as e:  # noqa: BLE001 - the loop must not die silently
                await self._fail(texts.executor_crashed(repr(e)), stop=True)
                break
            await asyncio.sleep(max(0.0, period - (self.clock() - t0)))

    async def _cancel_loop(self) -> None:
        task, self._task = self._task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def tick(self) -> None:
        """One executor tick. Public so tests can drive it with a manual clock."""
        if self.state != "running" or self.pack is None:
            return
        snap = self.snapshot
        snap.now = self.clock()
        self._driving_this_tick = False
        self.counters.ticks += 1
        try:
            if self._preempt_source:
                await self._preempted(self._preempt_source)
                return
            if self.interrupt is None:
                self._check_interrupts()
            if self.interrupt is not None:
                await self._tick_interrupt()
                return
            step = self.pack.steps[self.step_index]
            status = await self._tick_step(step)
            if status == Status.SUCCESS:
                await self._advance()
            elif status == Status.FAILURE:
                await self._fail(self.reason or texts.step_failed_plain(), stop=True)
        finally:
            snap.speech.clear()
            self.watchdog.pet(driving=self._driving_this_tick)

    # -- transitions -----------------------------------------------------------------------

    def _announce_step(self) -> None:
        assert self.pack is not None
        step = self.pack.steps[self.step_index]
        n = self.step_index + 1
        if isinstance(step, PerceiveStep):
            text = (
                texts.step_ask(n, step.question)
                if step.question is not None
                else texts.step_look_for(n, step.perceive)
            )
        elif isinstance(step, SkillStep):
            opts = ", ".join(f"{k}: {v}" for k, v in step.with_.items())
            text = texts.step_skill(n, self.registry.get(step.skill).name, opts)
        else:
            text = texts.step_wait(n, step.wait)
        self.bus.emit("step.started", *text, step=self.step_index, behavior=self.pack.id)

    async def _advance(self) -> None:
        assert self.pack is not None
        self.run = self.on_none_run = None
        self._announced_none = False
        self.step_index += 1
        self.step_started = self.clock()
        if self.step_index >= len(self.pack.steps):
            self.state = "done"
            self._clear_vlm_request()
            self._record_run()
            self.watchdog.disarm()
            self.bus.emit(
                "behavior.done", *texts.behavior_done(self.pack.name), behavior=self.pack.id
            )
            return
        self._announce_step()

    async def _fail(self, reason: texts.Bilingual, *, stop: bool) -> None:
        if self.state != "running":
            return
        self.state = "failed"
        self.reason = reason
        self._record_run()
        self._clear_vlm_request()
        self.watchdog.disarm()
        if stop:
            await self.gate.stop()
        name = self.pack.name if self.pack else Text(de="Ablauf", en="Behavior")
        self.bus.emit(
            "behavior.failed",
            *texts.behavior_failed(name, reason),
            level="error",
            reason=reason[1],
        )

    async def _on_watchdog(self, silent_s: float) -> None:
        """The watchdog already stopped the duck; end the behavior so nothing resumes."""
        await self._fail(texts.went_quiet(silent_s), stop=False)

    async def _preempted(self, source: str) -> None:
        self.state = "preempted"
        self.reason = texts.preempted_reason(source)
        self._record_run()
        self._clear_vlm_request()
        self.watchdog.disarm()
        await self.gate.stop()
        self.bus.emit(
            "executor.preempted", *texts.preempted_by(source), level="warn", source=source
        )

    # -- interrupts (always rules) ---------------------------------------------------------

    def _check_interrupts(self) -> None:
        assert self.pack is not None
        for rule in self.pack.always:
            if evaluate(rule.on, self.snapshot) is True:
                signal = Condition.parse(rule.on).signal
                if self.counters.last_interrupt_signal == signal:
                    self.counters.same_interrupt += 1
                else:
                    self.counters.same_interrupt = 1
                    self.counters.last_interrupt_signal = signal
                self.interrupt = InterruptRun(
                    rule=rule, actions=list(rule.do), started=self.clock()
                )
                self.bus.emit(
                    "interrupt.started",
                    *texts.interrupt_started(signal, [self._action_name(a) for a in rule.do]),
                    level="warn",
                    on=rule.on,
                    do=list(rule.do),
                )
                return

    async def _tick_interrupt(self) -> None:
        it = self.interrupt
        assert it is not None
        if self.counters.same_interrupt > MAX_SAME_INTERRUPT:
            self.interrupt = None
            await self._fail(texts.recovery_failed(it.rule.on), stop=True)
            return
        while it.index < len(it.actions):
            action = it.actions[it.index]
            if action in RESERVED_ACTIONS:
                self.interrupt = None
                if action in ("resume", "retry", "continue"):
                    if self.run is not None:
                        self.run.last_sent = None
                    self.bus.emit(
                        "interrupt.resumed",
                        *texts.resumed(self.step_index + 1),
                        step=self.step_index,
                    )
                elif action == "abort":
                    await self._fail(texts.aborted_by_rule(), stop=True)
                elif action == "stop":
                    self.state = "aborted"
                    self.reason = texts.behavior_aborted(by_rule=True)
                    self._clear_vlm_request()
                    self.watchdog.disarm()
                    await self.gate.stop()
                    self.bus.emit(
                        "behavior.aborted", *texts.behavior_aborted(by_rule=True), level="warn"
                    )
                return
            if it.run is None:
                it.run = self._make_run(action, {}, None)
            status = await self._tick_run(it.run)
            if status == Status.RUNNING:
                return
            if status == Status.FAILURE:
                dec = it.run.last_decision
                if dec is not None and dec.reason == "precondition_failed":
                    pass  # e.g. `getup` while already standing: skip the action
                else:
                    self.interrupt = None
                    await self._fail(
                        self.reason or texts.action_failed(self._action_name(action)), stop=True
                    )
                    return
            it.run = None
            it.index += 1
        self.interrupt = None  # exhausted without a reserved word: carry on with the step

    def _action_name(self, action: str) -> texts.Bilingual:
        if action in RESERVED_ACTIONS:
            return texts.action(action)
        if action in self.registry:
            return texts.name_of(self.registry.get(action).name)
        return action, action

    # -- steps -----------------------------------------------------------------------------

    async def _tick_step(self, step: Any) -> Status:
        snap = self.snapshot
        if isinstance(step, WaitStep):
            snap.elapsed_s = snap.now - self.step_started
            return Status.SUCCESS if snap.elapsed_s >= parse_duration(step.wait) else Status.RUNNING
        if isinstance(step, PerceiveStep):
            return await self._tick_perceive(step)
        if isinstance(step, SkillStep):
            if self.run is None:
                self.run = self._make_run(step.skill, dict(step.with_), step.until)
            status = await self._tick_run(self.run)
            if status != Status.RUNNING and self.run.end_reason:
                ok = status == Status.SUCCESS
                self.bus.emit(
                    "step.done" if ok else "step.failed",
                    *texts.step_ended(self.step_index + 1, ok, self.run.end_reason),
                    level="info" if ok else "warn",
                    step=self.step_index,
                )
            return status
        return Status.FAILURE

    def _set_vlm_request(self, step: PerceiveStep) -> None:
        """Publish the standing question; the perception service asks it (§4), we read answers.

        It stays published after the step succeeds, so a `toward_target` walk keeps getting
        fresh bearings, and is cleared when the behavior ends or another perceive step takes
        over.
        """
        assert self.pack is not None
        if step.question is None or self.pack.vlm is None:
            return
        request = VlmRequest(
            question=step.question.de,
            text=step.question,
            provider=self.pack.vlm.provider,
            behavior_id=self.pack.id,
        )
        if self.snapshot.vlm_request != request:
            self.snapshot.vlm_request = request

    def _clear_vlm_request(self) -> None:
        """Nobody is asking any more: the service stops asking and the sighting goes with it.

        A target only ever exists for the run that asked for it — leaving it in the snapshot
        would show the Studio a thing the duck stopped looking for minutes ago.
        """
        self.snapshot.vlm_request = None
        self.snapshot.target = None

    def _seen(self, step: PerceiveStep) -> Sighting | None:
        return self.snapshot.target_fresh if step.uses_vlm else self.snapshot.person_fresh

    async def _tick_perceive(self, step: PerceiveStep) -> Status:
        snap = self.snapshot
        if step.uses_vlm:
            if self.pack is not None and self.pack.vlm is None:  # schema forbids it; be sure
                self.reason = texts.vlm_not_allowed()
                return Status.FAILURE
            self._set_vlm_request(step)
        else:
            self._clear_vlm_request()
        seen = self._seen(step)
        if seen is not None:
            self._announced_none = False
            what = (
                texts.target_label(step.question)
                if step.question is not None
                else texts.person_label()
            )
            self.bus.emit(
                "perceive.found",
                *texts.perceive_found(
                    what,
                    seen.distance_m,
                    abs(math.degrees(seen.bearing_rad)),
                    left=seen.bearing_rad >= 0,
                ),
                bearing_rad=seen.bearing_rad,
                distance_m=seen.distance_m,
                query=step.perceive,
            )
            self.on_none_run = None
            return Status.SUCCESS
        nothing = texts.nothing_found(step.uses_vlm)
        if step.on_none is None:
            snap.elapsed_s = snap.now - self.step_started
            if snap.elapsed_s >= PERCEIVE_BUDGET_S:
                self.reason = (nothing[0].lower(), nothing[1].lower())
                return Status.FAILURE
            return Status.RUNNING
        if self.on_none_run is None:
            self.on_none_run = self._make_run(
                step.on_none.do, {}, None, budget_s=step.on_none.seconds
            )
            if not self._announced_none:  # `retry` sweeps again and again; say it once
                self._announced_none = True
                self.bus.emit(
                    "perceive.none",
                    *texts.searching(nothing, self.on_none_run.skill.name, step.on_none.seconds),
                    do=step.on_none.do,
                )
        status = await self._tick_run(self.on_none_run)
        if status == Status.RUNNING:
            return Status.RUNNING
        self.on_none_run = None
        if self._seen(step) is not None:
            return Status.RUNNING  # found during the sweep; next tick reports it
        if status == Status.FAILURE:
            return Status.FAILURE
        match step.on_none.then:
            case "retry":
                self.step_started = snap.now
                return Status.RUNNING
            case "abort":
                self.reason = (nothing[0].lower(), nothing[1].lower())
                return Status.FAILURE
            case _:
                return Status.SUCCESS

    # -- skill runs ------------------------------------------------------------------------

    def _make_run(
        self,
        skill_id: str,
        with_: dict[str, Any],
        until: Until | None,
        *,
        budget_s: float | None = None,
    ) -> SkillRun:
        skill = self.registry.get(skill_id)
        chosen = dict(with_)
        for key, control in skill.ui.items():
            default = getattr(control, "default", None)
            if key not in chosen and default is not None:
                chosen[key] = default
        params, extras = self.registry.resolve_ui(skill_id, chosen)
        if budget_s is None:
            if until is not None:
                budget_s = _shortest_elapsed(until)
            if budget_s is None:
                if skill.behavior is not None:
                    ends = set(skill.terminates_on)
                    budget_s = (
                        QUICK_BEHAVIOR_BUDGET_S
                        if ends <= {"timeout"}
                        else DEFAULT_BEHAVIOR_BUDGET_S
                    )
                else:
                    budget_s = DEFAULT_INTENT_BUDGET_S
        return SkillRun(
            skill=skill,
            params=params,
            extras=extras,
            until=until,
            budget_s=budget_s,
            started=self.clock(),
        )

    async def _tick_run(self, run: SkillRun) -> Status:
        snap = self.snapshot
        snap.elapsed_s = snap.now - run.started
        snap.budget_s = run.budget_s
        distance_cm = run.extras.get("distance")
        snap.stop_distance_m = float(distance_cm) / 100.0 if distance_cm is not None else None
        snap.steering = STEERING.get(str(run.extras.get("direction", "")))

        # 1. end conditions before acting (§6.4)
        if run.until is not None:
            reason = self._until_reason(run.until)
            if reason is not None:
                run.end_reason = reason
                return Status.SUCCESS
        for text in run.skill.terminates_on:
            if evaluate(text, snap) is True:
                signal = Condition.parse(text).signal
                run.end_reason = texts.signal(signal)
                return Status.FAILURE if signal in FAILING_SIGNALS else Status.SUCCESS

        # 2. act: at most one intent or behavior
        try:
            if run.skill.behavior is not None:
                if not run.sent_behavior:
                    decision = await self.gate.send_behavior(run.skill)
                    run.last_decision = decision
                    if not decision.accepted:
                        return self._refused(run, decision)
                    run.sent_behavior = True
                    run.refused_since = None
                    self.counters.intents_sent += 1
                return Status.RUNNING
            if run.last_sent is None or snap.now - run.last_sent >= 1.0 / run.skill.rate_hz:
                decision = await self.gate.send(run.skill, self._intent_params(run))
                run.last_decision = decision
                if not decision.accepted:
                    return self._refused(run, decision)
                run.last_sent = snap.now
                run.refused_since = None
                self.counters.intents_sent += 1
                if run.skill.is_movement:
                    self._driving_this_tick = True
        except BehaviorRefused as e:
            run.end_reason = texts.duck_refused(str(e))
            self.reason = run.end_reason
            return Status.FAILURE
        return Status.RUNNING

    def _refused(self, run: SkillRun, decision: GateDecision) -> Status:
        snap = self.snapshot
        if decision.reason in (
            "battery_low",
            "unknown_param",
            "skill_has_no_intent",
            "skill_has_no_behavior",
        ):
            refused = decision.reason or "refused"
            run.end_reason = texts.battery_low() if refused == "battery_low" else (refused, refused)
            self.reason = run.end_reason
            return Status.FAILURE
        if decision.reason == "rate_limited":
            return Status.RUNNING
        if run.refused_since is None:
            run.refused_since = snap.now
        if snap.now - run.refused_since > PRECONDITION_PATIENCE_S:
            run.end_reason = texts.precondition_failed(decision.failed)
            self.reason = run.end_reason
            return Status.FAILURE
        return Status.RUNNING

    def _intent_params(self, run: SkillRun) -> dict[str, float]:
        snap = self.snapshot
        skill = run.skill
        p = dict(run.params)
        if skill.intent == upstream.ROBOT_MOVE.name:
            vx = p.get("vx", 0.0)
            direction = str(run.extras.get("direction", "straight"))
            if direction in STEERING:
                subject = snap.subject
                if subject is None:
                    return {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}  # hold still, keep the heartbeat
                return steer_toward(subject, vx, snap.stop_distance_m)
            return {"vx": vx, "vy": p.get("vy", 0.0), "vyaw": p.get("vyaw", 0.0)}
        if skill.intent == upstream.ROBOT_LOOK.name:
            pattern = run.extras.get("pattern", "sweep")
            y = {"left": 0.8, "right": -0.8}.get(
                str(pattern), 0.8 * math.sin(2 * math.pi * snap.elapsed_s / 4.0)
            )
            return {"x": 1.0, "y": y, "z": 0.1}
        return p

    def _until_reason(self, until: Until) -> texts.Bilingual | None:
        conds = until.any if until.any is not None else (until.all or [])
        reasons = [self._stop_condition(c) for c in conds]
        if until.any is not None:
            return next((r for r in reasons if r is not None), None)
        if reasons and all(r is not None for r in reasons):
            return texts.joined([r for r in reasons if r], separator=(" und ", " and "))
        return None

    def _stop_condition(self, c: StopCondition) -> texts.Bilingual | None:
        snap = self.snapshot
        if isinstance(c, SpeechCondition):
            for phrase in c.speech.all():
                if normalize_phrase(phrase) in snap.speech:
                    return f"du hast „{phrase}“ gesagt", f"you said “{phrase}”"
            return None
        if isinstance(c, ElapsedCondition):
            if snap.elapsed_s >= parse_duration(c.elapsed):
                return "Zeit vorbei", "time is up"
            return None
        if isinstance(c, SignalCondition):
            if evaluate(c.signal, snap) is True:
                return texts.signal(Condition.parse(c.signal).signal)
        return None


def steer_toward(subject: Sighting, vx: float, stop_distance_m: float | None) -> dict[str, float]:
    """Turn towards what we are following, walk slower the further off the nose it is, and
    ease off as the gap closes. Whether a local detector or a VLM saw it makes no difference
    here — both hand over a bearing and maybe a range."""
    bearing = subject.bearing_rad
    vyaw = max(-1.0, min(1.0, TURN_GAIN * bearing))
    if abs(bearing) > TURN_FIRST_RAD:
        vx *= max(0.0, 1.0 - (abs(bearing) - TURN_FIRST_RAD) / 0.5)
    if subject.distance_m is not None and stop_distance_m is not None:
        gap = subject.distance_m - stop_distance_m
        if gap < SLOWDOWN_ZONE_M:
            vx *= max(0.3, gap / SLOWDOWN_ZONE_M)
    return {"vx": vx, "vy": 0.0, "vyaw": vyaw}


def _shortest_elapsed(until: Until) -> float | None:
    conds = (until.any or []) + (until.all or [])
    durations = [parse_duration(c.elapsed) for c in conds if isinstance(c, ElapsedCondition)]
    return min(durations) if durations else None
