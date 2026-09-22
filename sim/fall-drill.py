#!/usr/bin/env python3
"""Fall drill: run a behavior in a sim-backed runtime, knock the duck over mid-walk, check it
gets up and carries on (M2: "Sturz-Recovery getestet durch simulierten Stoß").

    ./sim/up.sh                                         # a fresh duck, person 1.5 m ahead
    DUCKSTUDIO_BACKEND=sim uv --directory runtime run python -m duckstudio
    python3 sim/fall-drill.py                           # exit 0 = passed

The "hand" is upstream's own API, not ours: `robot.pose` held far outside its trained range
(±0.26 rad) straight on duck-sim's robotd socket, the way a person pushes a duck — the runtime
does not know it is coming. robotd clamps nothing here (duck-ipc-proto `PoseParams`), which is
why it tips. Standard library only. Findings: docs/upstream-notes.md, "Falling over in duck-sim".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
import urllib.request

SOCKET = os.path.join(
    os.path.expanduser(os.environ.get("DUCK_SIM_STATE", "~/.cache/duck-sim")), "duck-a.sock"
)


def api(base: str, path: str, method: str = "GET") -> dict:
    data = b"" if method == "POST" else None
    req = urllib.request.Request(base + path, method=method, data=data)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


async def push(pitch: float, seconds: float) -> None:
    _, w = await asyncio.open_unix_connection(SOCKET)

    def pose(p: float, active: bool) -> bytes:
        params = {"z": 0.0, "roll": 0.0, "pitch": p, "active": active}
        return (
            json.dumps({"jsonrpc": "2.0", "method": "robot.pose", "params": params}) + "\n"
        ).encode()

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        w.write(pose(pitch, True))
        await asyncio.sleep(0.1)
    w.write(pose(0.0, False))
    await w.drain()
    w.close()


def tilt_deg(state: dict) -> float:
    imu = state["imu"]
    return math.degrees(
        math.acos(max(-1.0, min(1.0, math.cos(imu["roll"]) * math.cos(imu["pitch"]))))
    )


async def drill(args: argparse.Namespace) -> int:
    base = args.runtime.rstrip("/")
    first_event = len(api(base, "/api/events"))
    t0 = time.monotonic()
    api(base, f"/api/behaviors/{args.behavior}/run", "POST")
    walking_since = pushed_at = resumed_at = None
    interrupted = False
    last = None
    while time.monotonic() - t0 < args.budget:
        ex = api(base, "/api/executor")
        now = time.monotonic() - t0
        key = (ex["state"], ex["step_index"], ex["active_skill"], ex["interrupt"])
        if key != last:
            st = api(base, "/api/state")
            skill, interrupt = ex["active_skill"] or "-", ex["interrupt"] or "-"
            print(
                f"{now:5.1f}s  {ex['state']:8s} step {ex['step_index']}  {skill:12s}"
                f" interrupt={interrupt:7s} tilt {tilt_deg(st):5.1f}°  ToF {ex['tof_min_m']}"
            )
            last = key
        if ex["state"] != "running":
            break
        if ex["active_skill"] == args.skill and walking_since is None and pushed_at is None:
            walking_since = now
        if pushed_at is None and walking_since is not None and now - walking_since > 2.0:
            print(f"{now:5.1f}s  push: robot.pose pitch {args.pitch} for {args.hold} s")
            asyncio.create_task(push(args.pitch, args.hold))
            pushed_at = now
        if pushed_at is not None and ex["interrupt"] is not None:
            interrupted = True
        if interrupted and resumed_at is None and ex["interrupt"] is None:
            if ex["active_skill"] == args.skill:
                resumed_at = now
        if resumed_at is not None and now - resumed_at > args.after:
            break
        await asyncio.sleep(0.1)

    ex = api(base, "/api/executor")
    if ex["state"] == "running":
        api(base, "/api/executor/abort", "POST")
    events = api(base, "/api/events")[first_event:]
    print()
    for e in events:
        if e["kind"] not in ("intent.sent", "intent.refused"):
            print(f"  {e['kind']:20s} {e['text']['de']}")
    kinds = [e["kind"] for e in events]
    checks = {
        "the duck was knocked over": "interrupt.started" in kinds,
        "getup was sent": any(e["kind"] == "behavior.sent" for e in events),
        "the behavior resumed": "interrupt.resumed" in kinds,
        f"{args.skill} ran on for {args.after:.0f} s after resuming": resumed_at is not None
        and ex["state"] == "running",
    }
    print()
    for name, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--runtime", default="http://127.0.0.1:8000")
    p.add_argument("--behavior", default="follow-me")
    p.add_argument("--skill", default="walk", help="the step that has to carry on")
    p.add_argument("--pitch", type=float, default=2.5, help="rad; the trained range is ±0.26")
    p.add_argument("--hold", type=float, default=2.5, help="seconds the push is held")
    p.add_argument("--after", type=float, default=5.0, help="seconds the step must run on")
    p.add_argument("--budget", type=float, default=60.0)
    sys.exit(asyncio.run(drill(p.parse_args())))


if __name__ == "__main__":
    main()
