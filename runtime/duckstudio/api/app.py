"""HTTP + WebSocket API for the Studio (§4: the Studio talks only to the runtime)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, ValidationError

from .. import __version__, behaviors_dir, skills_dir, texts, upstream
from ..backends import make_backend
from ..backends.base import BackendError, DuckBackend, NoCamera
from ..behaviors import (
    BehaviorPack,
    delete_behavior_pack,
    load_behavior_packs,
    pack_to_yaml,
    save_behavior_pack,
    validate_against_registry,
)
from ..events import EventBus
from ..executor import Executor, ExecutorBusy
from ..executor.safety import IntentGate
from ..perception import PerceptionService, detector_for, make_vlm, vlm_hz
from ..skills import SkillRegistry

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RECONNECT_EVERY_S = 3.0


class SayBody(BaseModel):
    """Module level on purpose: FastAPI resolves the annotation through module globals."""

    text: str


def create_app(
    backend: DuckBackend | None = None,
    *,
    skills_path: Path | None = None,
    behaviors_path: Path | None = None,
    auto_connect: bool = True,
) -> FastAPI:
    registry = SkillRegistry.load(skills_path or skills_dir())
    behaviors_root = Path(behaviors_path or behaviors_dir())
    packs = load_behavior_packs(behaviors_root)
    bus = EventBus()
    duck = backend or make_backend()
    gate = IntentGate(duck, bus=bus)
    executor = Executor(registry, gate, bus, packs=packs)
    detector = detector_for(duck.kind)
    # The VLM is the local stub unless DUCKSTUDIO_VLM says otherwise (ADR-0004): asking a
    # paid service to look at camera frames is a switch you flip, not a default.
    vlm = make_vlm(detector=detector)
    perception = PerceptionService(
        duck,
        gate.snapshot,
        detector=detector,
        on_pad_activity=lambda _frame: executor.preempt("gamepad"),
        vlm=vlm,
        vlm_hz=vlm_hz(),
        bus=bus,
    )

    def is_connected() -> bool:
        return bool(getattr(duck, "connected", False))

    async def try_connect() -> str | None:
        """One connection attempt. Returns an error string, or None when connected."""
        try:
            await duck.connect()
        except NotImplementedError as e:
            return f"not implemented: {e}"
        except BackendError as e:
            return str(e)
        bus.emit("backend.connected", *texts.backend_connected(duck.kind), backend=duck.kind)
        return None

    async def reconnect_loop() -> None:
        last_error: str | None = ""
        while True:
            if not is_connected():
                error = await try_connect()
                if error is not None and error != last_error:
                    bus.emit(
                        "backend.unavailable",
                        *texts.backend_unavailable(duck.kind),
                        level="warn",
                        backend=duck.kind,
                        error=error,
                    )
                last_error = error
                if error is not None and error.startswith("not implemented"):
                    return
            await asyncio.sleep(RECONNECT_EVERY_S)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if auto_connect:
            task = asyncio.create_task(reconnect_loop(), name="backend-reconnect")
            perception.start()
        yield
        await executor.close()
        await perception.close()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await duck.close()

    app = FastAPI(title="Duck Studio Runtime", version=__version__, lifespan=lifespan)
    app.state.registry = registry
    app.state.packs = packs
    app.state.backend = duck
    app.state.gate = gate
    app.state.bus = bus
    app.state.executor = executor
    app.state.perception = perception

    def lost(e: Exception) -> None:
        bus.emit(
            "backend.lost", *texts.backend_lost(duck.kind, str(e)), level="error", backend=duck.kind
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": __version__,
            "backend": duck.kind,
            "connected": is_connected(),
            "health": None,
            "unverified_upstream_methods": [m.name for m in upstream.unverified()],
            "vlm": {
                "provider": vlm.name,
                "model": vlm.model,
                "configured": vlm.configured,
                "sends_frames": vlm.sends_frames,
                "hz": perception.vlm_hz,
            },
        }
        if payload["connected"]:
            try:
                h = await duck.health()
            except BackendError as e:
                lost(e)
                payload["connected"] = is_connected()
            else:
                gate.observe(health=h)
                payload["health"] = h.model_dump()
        return payload

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        if not is_connected():
            raise HTTPException(503, "backend not connected")
        try:
            s = await duck.state()
        except BackendError as e:
            raise HTTPException(503, str(e)) from e
        gate.observe(state=s)
        return s.model_dump()

    @app.get("/api/skills")
    async def skills() -> list[dict[str, Any]]:
        return [m.model_dump(by_alias=True, mode="json") for m in registry]

    @app.get("/api/behaviors")
    async def behaviors() -> list[dict[str, Any]]:
        return [_pack_payload(p, registry) for p in packs.values()]

    @app.get("/api/behaviors/{behavior_id}")
    async def behavior(behavior_id: str) -> dict[str, Any]:
        pack = packs.get(behavior_id)
        if pack is None:
            raise HTTPException(404, f"unknown behavior {behavior_id!r}")
        return _pack_payload(pack, registry)

    def parse_pack(body: dict[str, Any]) -> BehaviorPack:
        try:
            return BehaviorPack.model_validate(body)
        except ValidationError as e:
            raise HTTPException(422, {"problems": _format_validation_error(e)}) from e

    @app.post("/api/behaviors/validate")
    async def validate_behavior(body: dict[str, Any]) -> dict[str, Any]:
        """Live check while editing: schema errors and registry problems in one list."""
        try:
            pack = BehaviorPack.model_validate(body)
        except ValidationError as e:
            return {"valid": False, "problems": _format_validation_error(e)}
        problems = validate_against_registry(pack, registry)
        return {"valid": not problems, "problems": problems}

    @app.put("/api/behaviors/{behavior_id}")
    async def save_behavior(behavior_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Ändern → Speichern (§3.1): writes behaviors/<id>.behavior.yaml and reloads it."""
        pack = parse_pack(body)
        if pack.id != behavior_id:
            raise HTTPException(400, f"id in path ({behavior_id!r}) and body ({pack.id!r}) differ")
        if (
            executor.state == "running"
            and executor.pack is not None
            and executor.pack.id == pack.id
        ):
            raise HTTPException(409, "this behavior is running; stop it before saving")
        path = save_behavior_pack(pack, behaviors_root)
        packs[pack.id] = pack
        bus.emit(
            "behavior.saved", *texts.behavior_saved(pack.name), behavior=pack.id, path=str(path)
        )
        return _pack_payload(pack, registry)

    @app.delete("/api/behaviors/{behavior_id}")
    async def remove_behavior(behavior_id: str) -> dict[str, bool]:
        pack = packs.get(behavior_id)
        if pack is None:
            raise HTTPException(404, f"unknown behavior {behavior_id!r}")
        if (
            executor.state == "running"
            and executor.pack is not None
            and executor.pack.id == behavior_id
        ):
            raise HTTPException(409, "this behavior is running; stop it before deleting")
        delete_behavior_pack(behavior_id, behaviors_root)
        del packs[behavior_id]
        bus.emit(
            "behavior.deleted",
            *texts.behavior_deleted(pack.name),
            level="warn",
            behavior=behavior_id,
        )
        return {"ok": True}

    @app.get("/api/behaviors/{behavior_id}/yaml")
    async def behavior_yaml(behavior_id: str) -> PlainTextResponse:
        """The developer view next to the cards (§3.1: beside, never in front)."""
        pack = packs.get(behavior_id)
        if pack is None:
            raise HTTPException(404, f"unknown behavior {behavior_id!r}")
        return PlainTextResponse(pack_to_yaml(pack), media_type="text/yaml; charset=utf-8")

    @app.get("/api/frame")
    async def frame() -> Response:
        if not is_connected():
            raise HTTPException(503, "backend not connected")
        try:
            data = await duck.frame()
        except NoCamera as e:
            raise HTTPException(503, f"no camera: {e}") from e
        except BackendError as e:
            raise HTTPException(502, str(e)) from e
        media_type = "image/png" if data[:8] == PNG_SIGNATURE else "image/jpeg"
        return Response(content=data, media_type=media_type, headers={"Cache-Control": "no-store"})

    @app.post("/api/stop")
    async def stop() -> dict[str, bool]:
        """Notstopp: aborts the executor and stops the duck, no checks anywhere (§7)."""
        await executor.abort("notstopp")
        await gate.stop()
        return {"ok": True}

    def executor_payload() -> dict[str, Any]:
        snap = gate.snapshot
        person = snap.person_fresh if snap.now else snap.person
        target = snap.target_fresh if snap.now else snap.target
        return {
            **executor.status(),
            "camera": perception.camera_available,
            "person": person.model_dump() if person is not None else None,
            "target": target.model_dump() if target is not None else None,
            "tof_min_m": snap.tof_min_m,
            "tof_rows": snap.tof_rows,  # 8x8 metres, for the Studio's proximity grid
            "vlm": {
                "provider": vlm.name,
                "sends_frames": vlm.sends_frames,
                "question": snap.vlm_request.text.model_dump() if snap.vlm_request else None,
                "asked": perception.vlm_calls,
                "answer": snap.vlm.model_dump() if snap.vlm is not None else None,
            },
        }

    @app.get("/api/executor")
    async def executor_status() -> dict[str, Any]:
        return executor_payload()

    async def start_behavior(behavior_id: str) -> dict[str, Any]:
        pack = packs.get(behavior_id)
        if pack is None:
            raise HTTPException(404, f"unknown behavior {behavior_id!r}")
        if not is_connected():
            raise HTTPException(503, "backend not connected")
        problems = validate_against_registry(pack, registry)
        if problems:
            raise HTTPException(422, {"problems": problems})
        try:
            await executor.start(pack)
        except ExecutorBusy as e:
            raise HTTPException(409, str(e)) from e
        return executor_payload()

    @app.post("/api/behaviors/{behavior_id}/run")
    async def run_behavior(behavior_id: str) -> dict[str, Any]:
        return await start_behavior(behavior_id)

    @app.post("/api/executor/abort")
    async def abort_behavior() -> dict[str, Any]:
        await executor.abort("studio")
        return executor_payload()

    @app.post("/api/say")
    async def say(body: SayBody) -> dict[str, Any]:
        """v1 stand-in for speech recognition (CLAUDE.md §9): the Studio's „Ich sage: …“."""
        matched = executor.say(body.text)
        started = None
        if matched is not None and executor.state != "running":
            await start_behavior(matched)
            started = matched
        return {"heard": body.text, "started": started, **executor_payload()}

    @app.get("/api/events")
    async def events() -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in bus.history]

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        await ws.accept()
        q = bus.subscribe()
        try:
            for e in list(bus.history):
                await ws.send_text(e.model_dump_json())
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=5.0)
                except TimeoutError:
                    await ws.send_text(json.dumps({"kind": "ping"}))
                    continue
                await ws.send_text(e.model_dump_json())
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe(q)

    return app


def _pack_payload(pack: Any, registry: SkillRegistry) -> dict[str, Any]:
    data = pack.model_dump(by_alias=True, mode="json")
    data["problems"] = validate_against_registry(pack, registry)
    return data


def _format_validation_error(error: ValidationError) -> list[str]:
    out = []
    for err in error.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "pack"
        out.append(f"{loc}: {err['msg']}")
    return out
