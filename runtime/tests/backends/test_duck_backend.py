"""The `duck` backend's own bits: where it looks for the tunnel, and what it says when the
tunnel is not there (ADR-0006). The wire behaviour itself is the shared contract suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckstudio.backends import make_backend
from duckstudio.backends.base import BackendError
from duckstudio.backends.duck import DEFAULT_CONSOLE_URL, LOCAL_SOCKETS, RealDuckBackend

from .fake_robotd import FakeDuck, short_tmp_dir


def test_it_looks_where_the_tunnel_script_puts_the_sockets(tmp_path: Path) -> None:
    duck = RealDuckBackend(tunnel_dir=str(tmp_path))
    assert duck.kind == "duck"
    assert duck.robot_socket == str(tmp_path / LOCAL_SOCKETS["robot"])
    assert duck.tof_socket == str(tmp_path / LOCAL_SOCKETS["tof"])
    assert duck.pad_socket == str(tmp_path / LOCAL_SOCKETS["pad"])
    assert duck.console_url == DEFAULT_CONSOLE_URL


async def test_without_a_tunnel_it_names_the_script_not_the_errno(tmp_path: Path) -> None:
    duck = RealDuckBackend(tunnel_dir=str(tmp_path), url="duck.local")
    assert duck.tunnel_is_up() is False
    with pytest.raises(BackendError, match="duck-tunnel.sh duck.local"):
        await duck.connect()
    assert duck.connected is False


async def test_with_the_tunnel_up_it_is_just_an_ipc_backend(tmp_path: Path) -> None:
    fake = FakeDuck(short_tmp_dir(), duck="tunnel")
    await fake.start()
    (fake.dir / LOCAL_SOCKETS["robot"]).symlink_to(fake.robot_socket)
    (fake.dir / LOCAL_SOCKETS["tof"]).symlink_to(fake.tof_socket)
    duck = RealDuckBackend(tunnel_dir=str(fake.dir), console_url=None)
    try:
        await duck.connect()
        assert duck.connected is True
        health = await duck.health()
        assert 0.0 <= health.battery <= 1.0
    finally:
        await duck.close()
        await fake.stop()


def test_the_environment_configures_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUCKSTUDIO_DUCK_TUNNEL", str(tmp_path))
    monkeypatch.setenv("DUCKSTUDIO_DUCK_CONSOLE", "http://127.0.0.1:9100")
    monkeypatch.setenv("DUCKSTUDIO_DUCK_HOST", "duck.local")
    duck = make_backend("duck")
    assert isinstance(duck, RealDuckBackend)
    assert duck.tunnel_dir == str(tmp_path)
    assert duck.console_url == "http://127.0.0.1:9100"
    assert duck.host == "duck.local"


def test_a_console_can_be_switched_off(tmp_path: Path) -> None:
    """A duck without a camera, or a tunnel without the console port forwarded."""
    duck = RealDuckBackend(tunnel_dir=str(tmp_path), console_url=None)
    assert duck.console_url is None
