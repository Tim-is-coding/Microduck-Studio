"""HTTP + WebSocket API for the Studio (§4: the Studio talks only to the runtime)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from .. import __version__, behaviors_dir, skills_dir, upstream
from ..backends import make_backend
from ..backends.base import DuckBackend
from ..behaviors import load_behavior_packs, validate_against_registry
from ..events import EventBus
from ..executor.safety import IntentGate
from ..skills import SkillRegistry

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def create_app(
    backend: DuckBackend | None = None,
    *,
    skills_path: Path | None = None,
    behaviors_path: Path | None = None,
    connect_on_startup: bool = True,
) -> FastAPI:
    registry = SkillRegistry.load(skills_path or skills_dir())
    packs = load_behavior_packs(behaviors_path or behaviors_dir())
    bus = EventBus()
    duck = backend or make_backend()
    gate = IntentGate(duck, bus=bus)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if connect_on_startup:
            try:
                await duck.connect()
                bus.emit(
                    "backend.connected", f"Backend „{duck.kind}“ verbunden.", backend=duck.kind
                )
            except NotImplementedError as e:
                bus.emit(
                    "backend.unavailable",
                    f"Backend „{duck.kind}“ nicht verfügbar: {e}",
                    level="error",
                    backend=duck.kind,
                )
        yield
        await duck.close()

    app = FastAPI(title="Duck Studio Runtime", version=__version__, lifespan=lifespan)
    app.state.registry = registry
    app.state.packs = packs
    app.state.backend = duck
    app.state.gate = gate
    app.state.bus = bus

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        connected = bool(getattr(duck, "connected", False))
        payload: dict[str, Any] = {
            "version": __version__,
            "backend": duck.kind,
            "connected": connected,
            "health": None,
            "unverified_upstream_methods": [m.name for m in upstream.unverified()],
        }
        if connected:
            h = await duck.health()
            gate.observe(health=h)
            payload["health"] = h.model_dump()
        return payload

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

    @app.get("/api/frame")
    async def frame() -> Response:
        if not getattr(duck, "connected", False):
            raise HTTPException(503, "backend not connected")
        return Response(
            content=await duck.frame(),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/stop")
    async def stop() -> dict[str, bool]:
        await gate.stop()
        return {"ok": True}

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
