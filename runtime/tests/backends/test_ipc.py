"""The JSON-RPC/NDJSON connection against the fake daemon."""

from __future__ import annotations

import asyncio
import shutil

import pytest

from duckstudio import upstream
from duckstudio.backends.base import BackendError
from duckstudio.backends.ipc import Connection, RpcError

from .fake_robotd import FakeDuck, short_tmp_dir


@pytest.fixture
async def fake():
    duck = FakeDuck(short_tmp_dir())
    await duck.start()
    try:
        yield duck
    finally:
        await duck.stop()
        shutil.rmtree(duck.dir, ignore_errors=True)


async def test_hello_handshake(fake: FakeDuck) -> None:
    conn = await Connection.open(str(fake.robot_socket))
    assert conn.hello == {
        "api_version": upstream.API_VERSION,
        "daemon_version": "0.14.4",
        "revision": None,
    }
    assert fake.received[0] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hello",
        "params": {"api_version": upstream.API_VERSION},
    }
    await conn.close()


async def test_unknown_method_is_32601(fake: FakeDuck) -> None:
    conn = await Connection.open(str(fake.robot_socket))
    with pytest.raises(RpcError) as e:
        await conn.call("robot.walk")
    assert e.value.code == -32601
    await conn.close()


async def test_unknown_param_is_32602(fake: FakeDuck) -> None:
    conn = await Connection.open(str(fake.robot_socket))
    with pytest.raises(RpcError) as e:
        await conn.call("robot.look", {"x": 1.0, "yaw": 0.0})
    assert e.value.code == -32602 and "yaw" in e.value.message
    await conn.close()


async def test_notification_has_no_id(fake: FakeDuck) -> None:
    conn = await Connection.open(str(fake.robot_socket))
    await conn.notify("robot.move", {"vx": 0.1, "vy": 0.0, "vyaw": 0.0})
    await conn.call("robot.health")  # round trip guarantees the notification was read
    sent = [m for m in fake.received if m.get("method") == "robot.move"]
    assert sent and "id" not in sent[0]
    assert fake.twist == [0.1, 0.0, 0.0]
    await conn.close()


async def test_stream_owns_its_connection(fake: FakeDuck) -> None:
    conn = await Connection.open(str(fake.robot_socket))
    result = await conn.call("robot.subscribe", {"hz": 50})
    assert result["accepted"] is True
    stream = conn.notifications()
    first = await asyncio.wait_for(anext(stream), 2.0)
    assert first["method"] == "robot.state" and len(first["params"]["joints"]) == 15
    await stream.aclose()
    await conn.close()


async def test_missing_socket_is_a_backend_error() -> None:
    with pytest.raises(BackendError, match="cannot connect"):
        await Connection.open("/tmp/ds-nope/duck-a.sock")


async def test_daemon_going_away(fake: FakeDuck) -> None:
    conn = await Connection.open(str(fake.robot_socket))
    await fake.stop()
    with pytest.raises(BackendError):
        await conn.call("robot.health", timeout=1.0)
