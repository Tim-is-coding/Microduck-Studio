"""Executor: behaviour tree at 10 Hz (§6.4) and the safety layer (§7)."""

from .conditions import MOTOR_HOT_C, Snapshot, evaluate, signal_value
from .safety import GateDecision, IntentGate
from .tree import Executor, ExecutorBusy, Status
from .watchdog import Watchdog

__all__ = [
    "MOTOR_HOT_C",
    "Executor",
    "ExecutorBusy",
    "GateDecision",
    "IntentGate",
    "Snapshot",
    "Status",
    "Watchdog",
    "evaluate",
    "signal_value",
]
