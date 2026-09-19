from __future__ import annotations

import asyncio

from duckstudio.backends.mock import MockBackend
from duckstudio.executor.conditions import Snapshot
from duckstudio.perception import MockBarDetector, PerceptionService


async def test_service_fills_the_snapshot_from_the_mock() -> None:
    mock = MockBackend()
    await mock.connect()
    snap = Snapshot()
    svc = PerceptionService(mock, snap, detector=MockBarDetector(), frame_hz=20, state_hz=20)
    svc.start()
    try:
        for _ in range(50):
            await asyncio.sleep(0.02)
            if snap.person is not None and snap.tof_rows is not None and snap.state is not None:
                break
        assert snap.state is not None and snap.health is not None
        assert snap.tof_rows is not None and snap.tof_min_m is not None
        assert snap.person is not None
        # the mock's bar sits mid-frame, slightly right of centre → small negative bearing
        assert abs(snap.person.bearing_rad) < 0.2
        assert svc.camera_available is True
    finally:
        await svc.close()
