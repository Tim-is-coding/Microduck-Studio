"""Is the duck getting anywhere? Commanded motion against what odometry reports.

In duck-sim the walking policies step in place (`microduck_rl#46`): robotd accepts and applies
`robot.move`, the policy steps, and the body stays where it is. The Studio said „Die Ente
läuft" and nothing on screen changed, which looked like a frozen Studio. A real duck against a
wall or on a rug would look the same. So the executor watches in windows of `WINDOW_S`: when
the commands of a window should have carried the duck `MIN_EXPECTED_M` or turned it
`MIN_EXPECTED_RAD`, and it covered less than `PROGRESS_SHARE` of either, it is stuck.

Only a hint: nothing here stops or fails a step. Being stuck is said once, and getting going
again is said once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..backends.base import Pose2D

WINDOW_S = 3.0
MIN_EXPECTED_M = 0.06
MIN_EXPECTED_RAD = 0.3
PROGRESS_SHARE = 0.3

Change = Literal["stuck", "moving"]


@dataclass
class _Window:
    t: float
    pose: Pose2D
    last_t: float
    expected_m: float = 0.0
    expected_rad: float = 0.0


class ProgressWatch:
    def __init__(self) -> None:
        self.stuck = False
        self._window: _Window | None = None

    def reset(self) -> None:
        self.stuck = False
        self._window = None

    def observe(
        self, now: float, pose: Pose2D | None, command: dict[str, float] | None
    ) -> Change | None:
        """One tick. `command` is the movement being sent right now (vx, vy, vyaw), or None."""
        if pose is None or not command or not _moving(command):
            # Standing still on purpose (or nothing to measure): no verdict, and no stale one.
            self._window = None
            if self.stuck:
                self.stuck = False
            return None
        w = self._window
        if w is None:
            self._window = _Window(t=now, pose=pose, last_t=now)
            return None
        dt = max(0.0, now - w.last_t)
        w.last_t = now
        w.expected_m += math.hypot(command.get("vx", 0.0), command.get("vy", 0.0)) * dt
        w.expected_rad += abs(command.get("vyaw", 0.0)) * dt
        if now - w.t < WINDOW_S:
            return None
        moved = math.hypot(pose.x - w.pose.x, pose.y - w.pose.y)
        turned = abs(_wrap(pose.heading - w.pose.heading))
        judged = w.expected_m >= MIN_EXPECTED_M or w.expected_rad >= MIN_EXPECTED_RAD
        progress = (w.expected_m >= MIN_EXPECTED_M and moved >= PROGRESS_SHARE * w.expected_m) or (
            w.expected_rad >= MIN_EXPECTED_RAD and turned >= PROGRESS_SHARE * w.expected_rad
        )
        self._window = _Window(t=now, pose=pose, last_t=now)
        if not judged:
            return None
        if not progress and not self.stuck:
            self.stuck = True
            return "stuck"
        if progress and self.stuck:
            self.stuck = False
            return "moving"
        return None


def _moving(command: dict[str, float]) -> bool:
    return any(abs(v) > 1e-6 for v in command.values())


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
