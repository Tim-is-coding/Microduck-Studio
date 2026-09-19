"""JSON-RPC 2.0 as NDJSON over a Unix socket: the upstream wire format.

Verified against pollen-robotics/microduck@344925c (docs/upstream-notes.md, "Wire format"):
one JSON object per line; a request without `id` is a notification; every daemon answers
`hello {api_version}`; version skew is logged, never refused; unknown method → -32601,
unknown params member → -32602. One connection serves one request at a time, and a stream
(`robot.subscribe`, `tof.stream`, `pad.input`) owns its connection for good — so callers
open one `Connection` per stream plus one for request/response calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from .. import upstream
from .base import BackendError

log = logging.getLogger(__name__)

JSONRPC = "2.0"


class RpcError(BackendError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class Connection:
    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, path: str
    ) -> None:
        self._reader = reader
        self._writer = writer
        self.path = path
        self._next_id = 1
        self._lock = asyncio.Lock()
        self.hello: dict[str, Any] | None = None
        self.closed = False

    @classmethod
    async def open(cls, path: str, *, hello: bool = True, timeout: float = 5.0) -> Connection:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(path), timeout)
        except (OSError, TimeoutError) as e:
            raise BackendError(f"cannot connect to {path}: {e}") from e
        conn = cls(reader, writer, path)
        if hello:
            result = await conn.call(upstream.HELLO.name, {"api_version": upstream.API_VERSION})
            conn.hello = result if isinstance(result, dict) else {}
            got = conn.hello.get("api_version")
            if got != upstream.API_VERSION:
                log.warning(
                    "%s: API version skew (ours %s, daemon %s) — upstream logs, never refuses",
                    path,
                    upstream.API_VERSION,
                    got,
                )
        return conn

    async def call(
        self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 5.0
    ) -> Any:
        """Request/response. Notifications that arrive in between are logged and skipped."""
        async with self._lock:
            req_id = self._next_id
            self._next_id += 1
            msg: dict[str, Any] = {"jsonrpc": JSONRPC, "id": req_id, "method": method}
            if params is not None:
                msg["params"] = params
            await self._send(msg)
            while True:
                reply = await self._recv(timeout)
                if reply.get("id") == req_id:
                    error = reply.get("error")
                    if error is not None:
                        raise RpcError(
                            int(error.get("code", -32603)),
                            str(error.get("message", "")),
                            error.get("data"),
                        )
                    return reply.get("result")
                log.debug(
                    "%s: skipping %s while waiting for #%s", self.path, reply.get("method"), req_id
                )

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Fire and forget (no `id`): how continuous intents like robot.move travel."""
        async with self._lock:
            await self._send({"jsonrpc": JSONRPC, "method": method, "params": params or {}})

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        """Yield incoming notifications until the daemon closes the socket."""
        while not self.closed:
            try:
                msg = await self._recv(None)
            except BackendError:
                return
            if msg.get("id") is None and "method" in msg:
                yield msg

    async def close(self) -> None:
        self.closed = True
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass

    async def _send(self, obj: dict[str, Any]) -> None:
        if self.closed:
            raise BackendError(f"{self.path}: connection closed")
        self._writer.write(json.dumps(obj, separators=(",", ":")).encode() + b"\n")
        try:
            await self._writer.drain()
        except (ConnectionError, OSError) as e:
            self.closed = True
            raise BackendError(f"{self.path}: {e}") from e

    async def _recv(self, timeout: float | None) -> dict[str, Any]:
        try:
            if timeout is None:
                line = await self._reader.readline()
            else:
                line = await asyncio.wait_for(self._reader.readline(), timeout)
        except TimeoutError as e:
            raise BackendError(f"{self.path}: no answer within {timeout}s") from e
        except (ConnectionError, OSError) as e:
            self.closed = True
            raise BackendError(f"{self.path}: {e}") from e
        if not line:
            self.closed = True
            raise BackendError(f"{self.path}: connection closed by daemon")
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            raise BackendError(f"{self.path}: not NDJSON: {line[:80]!r}") from e
        if not isinstance(msg, dict):
            raise BackendError(
                f"{self.path}: expected an object per line, got {type(msg).__name__}"
            )
        return msg
