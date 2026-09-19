"""The single place for upstream (pollen-robotics/microduck) JSON-RPC method names.

Rule from CLAUDE.md §10: never write API names from memory. Every entry below carries the
upstream revision and source location it was read from; `verified=False` entries are
assumptions and block `sim`/`duck` from connecting (`require_verified`).

Verified 2026-09-19 against pollen-robotics/microduck@344925c9f8fa031f85428a305b1e8ec2eaae29c1
(workspace 0.14.1, `API_VERSION = 31` in duck-ipc-proto/src/lib.rs). Details and the
discrepancies against the handover: docs/upstream-notes.md.
"""

from __future__ import annotations

from dataclasses import dataclass

UPSTREAM_REPO = "pollen-robotics/microduck"
UPSTREAM_REV = "344925c9f8fa031f85428a305b1e8ec2eaae29c1"
UPSTREAM_VERSION = "0.14.1"
API_VERSION = (
    31  # duck-ipc-proto/src/lib.rs; sent in `hello {api_version}`; skew is logged, never refused
)

# robotd zeroes the velocity when no `robot.move` arrived for this long (safety.deadman_ms).
# There is no heartbeat method: keeping the duck moving means resending `robot.move`.
DEADMAN_MS = 500
# duck-sim resends `robot.move` at 10 Hz; that is the cadence our executor uses too.
MOVE_RESEND_HZ = 10


@dataclass(frozen=True)
class Method:
    name: str
    verified: bool = False
    source: str = ""  # file:line in UPSTREAM_REV
    note: str = ""


_PROTO = "duck-ipc-proto/src/lib.rs"

# -- robotd (`/run/robotd.sock`, `robot.*`) --------------------------------------------------
ROBOT_MOVE = Method(
    "robot.move",
    True,
    f"{_PROTO}:2044 MoveParams",
    "continuous velocity intent {vx m/s fwd, vy m/s left, vyaw rad/s +left}; send as "
    "notification (no id) at 10–50 Hz; last-writer-wins; NO clamp upstream — ours is the only one",
)
ROBOT_HEAD = Method(
    "robot.head",
    True,
    f"{_PROTO}:2060 HeadParams",
    "{neck_pitch, head_pitch, head_yaw, head_roll} rad; does not refresh the deadman",
)
ROBOT_LOOK = Method(
    "robot.look",
    True,
    f"{_PROTO}:2074 LookParams",
    "{x, y, z} metres in trunk frame (floor ≈ 0.12 m below origin), neck_pitch "
    "→ LookResult{head, clamped}",
)
ROBOT_POSE = Method("robot.pose", True, f"{_PROTO}:2248 PoseParams", "{z, roll, pitch, active}")
ROBOT_STOP = Method(
    "robot.stop",
    True,
    f"{_PROTO}; robotd/src/main.rs:4478",
    "zero the velocity; always accepted, no gate. Not a physical e-stop (mediad/src/route.rs)",
)
ROBOT_RELAX = Method("robot.relax", True, _PROTO, "cut joint power; the robot collapses")
ROBOT_INIT = Method("robot.init", True, _PROTO, "power joints, ramp to home pose")
ROBOT_ENABLE = Method(
    "robot.enable",
    True,
    f"{_PROTO} EnableParams",
    "{on: bool, toggle: bool} hand robot to/from policy",
)
ROBOT_DO = Method(
    "robot.do",
    True,
    f"{_PROTO} DoParams",
    "{skill: str} one-shot skill: ground_pick, sit_toggle (built in), kick_left, kick_right, "
    "roulade (config); unknown name refused with the known list",
)
ROBOT_SOUND = Method(
    "robot.sound",
    True,
    f"{_PROTO}:2098 SoundParams",
    "{tag: alarm|greet|inquire|peck|chirp|coo|wheee, hold?}; `robotctl quack` plays chirp",
)
ROBOT_HEALTH = Method(
    "robot.health",
    True,
    f"{_PROTO}:3259 HealthResult",
    "{healthy, degraded, reason?, battery?: {volts, percent 0–100}, ...}; battery absent = unknown",
)
ROBOT_SUBSCRIBE = Method(
    "robot.subscribe",
    True,
    f"{_PROTO}:2638 SubscribeParams",
    "{hz?} → SubscribeResult, then `robot.state` notifications on this connection",
)
ROBOT_STATE = Method(
    "robot.state",
    True,
    f"{_PROTO}:3487 RobotState (notification)",
    "{t, move{requested, applied, limited_by[]}, head[4], policy, safety{fallen, limp, ...}, "
    "joints[15], targets[15], odom, imu?, ...}",
)
ROBOT_POLICIES = Method(
    "robot.policies",
    True,
    f"{_PROTO}:2329 PoliciesResult",
    "{mode, enabled, slots, skills, homed?, sitting?}",
)
HELLO = Method(
    "hello", True, f"{_PROTO}:59 HelloResult", "{api_version} → {api_version, daemon_version?}"
)

# -- other daemons ---------------------------------------------------------------------------
MEDIA_FRAME = Method(
    "media.frame",
    True,
    f"{_PROTO}:2947 MediaFrameHeader; mediad/src/frame.rs",
    "on /run/mediad/media.sock: JSON header {width, height, format: UYVY, bytes, ...} followed "
    "by raw UYVY pixels. Not JPEG. HTTP alternative: GET :8080/frame → PNG (mediad/src/web.rs:97)",
)
MEDIA_STREAM = Method(
    "media.stream",
    True,
    "mediad/src/session.rs:255",
    "WebRTC datachannel only: robot dials OUR wss:// and pushes JPEG/H.264 at 0.2–15 fps",
)
TOF_STREAM = Method(
    "tof.stream",
    True,
    f"{_PROTO}:811; TofStreamResult :4479",
    "on /run/tofd/tof.sock (tofd, not robotd): → {accepted, sensor?, rows, cols, hz}, then "
    "`tof.frame` notifications {seq, at_us, rows, cols, distance_mm: [i16], status: [u8]} (mm!)",
)
TOF_FRAME = Method("tof.frame", True, f"{_PROTO}:828,4507 TofFrame", "row-major, millimetres")
PAD_REPORT = Method(
    "pad.report",
    True,
    f"{_PROTO}:4279 PadReport (notification)",
    'internally tagged: {"report": "attached"|"frame"|"detached"|...}; frame carries '
    "{seq, at_us, since_us?, events: [{kind, code, value, name}], ...}",
)
PAD_INPUT = Method(
    "pad.input",
    True,
    f"{_PROTO}:795; PadReport :4280",
    "on /run/padd/pad.sock: raw evdev tap → `pad.report` notifications (Attached|Frame|Detached). "
    "NOT an authority signal: robotd has no arbitration, padd is just another `robot.move` writer",
)

# Names the handover assumed that do NOT exist upstream. Kept so nobody re-introduces them.
NOT_UPSTREAM: frozenset[str] = frozenset(
    {"robot.walk", "get_frame", "robot.sit", "robot.stand", "robot.getup", "robot.quack"}
)

INTENTS: dict[str, Method] = {m.name: m for m in (ROBOT_MOVE, ROBOT_HEAD, ROBOT_LOOK, ROBOT_POSE)}
QUERIES: dict[str, Method] = {
    m.name: m
    for m in (
        HELLO,
        ROBOT_HEALTH,
        ROBOT_SUBSCRIBE,
        ROBOT_STATE,
        ROBOT_POLICIES,
        ROBOT_STOP,
        ROBOT_RELAX,
        ROBOT_INIT,
        ROBOT_ENABLE,
        ROBOT_DO,
        ROBOT_SOUND,
        MEDIA_FRAME,
        MEDIA_STREAM,
        TOF_STREAM,
        TOF_FRAME,
        PAD_INPUT,
        PAD_REPORT,
    )
}

# Our named behaviors (`DuckBackend.behavior(name)`, §6.3) and the upstream call each maps to.
# `getup` has no upstream skill: the default walk policy (velstand.onnx, set v5) recovers from
# falls itself once enabled; the exact recovery sequence is an M2 decision.
BEHAVIOR_CALLS: dict[str, tuple[Method, dict[str, object]]] = {
    "sit": (ROBOT_DO, {"skill": "sit_toggle"}),  # check robot.policies.sitting first
    "stand": (ROBOT_DO, {"skill": "sit_toggle"}),
    "getup": (ROBOT_ENABLE, {"on": True}),
    "pickup": (ROBOT_DO, {"skill": "ground_pick"}),
    "kick": (ROBOT_DO, {"skill": "kick_right"}),
    "quack": (ROBOT_SOUND, {"tag": "chirp"}),
}
BEHAVIORS: frozenset[str] = frozenset(BEHAVIOR_CALLS)

# Official policy set (huggingface.co/pollen-robotics/microduck-policies, tag >= v5): defaults
# in walk mode are velstand.onnx (slot walk), alpha_sitstand.onnx, alpha_ground_pick.onnx.
DEFAULT_WALK_POLICY = "velstand"

# duck-sim socket layout (scripts/duck-sim; docs/robot/simulation.md). State dir default
# ~/.cache/duck-sim, overridable with DUCK_SIM_STATE.
SIM_STATE_DIR = "~/.cache/duck-sim"
SIM_DEFAULT_DUCK = "duck-a"
SIM_SOCKETS = {  # `{duck}` is duck-a, duck-b, ... (DUCK_SIM_DUCKS)
    "robot": "{duck}.sock",
    "tof": "{duck}-tof.sock",
    "config": "{duck}-config.sock",
    "updater": "{duck}-updater.sock",
    "frame": "{duck}-frame.sock",
}
SIM_CONSOLE_URL = "http://127.0.0.1:8080"  # mediad console of duck-a; 8080 + index for others

# `robot.state.policy` labels seen in robotd/src/{control,main}.rs @344925c and live on duck-sim.
# Skill labels (kick_left, roulade, ...) appear while a one-shot runs.
POLICY_LABELS = frozenset(
    {
        "walk",
        "stand",
        "sitstand",
        "sit",
        "rise",
        "ground_pick",
        "roulade",
        "kick_left",
        "kick_right",
        "held",
        "homing",
        "limp_fall",
        "limp_pose",
    }
)
# Labels during which the duck is neither standing nor fallen: mid-transition. `sit` is the
# held sit, `rise` the way back up (observed live), `sitstand` the scripted move between.
TRANSITION_LABELS = frozenset({"sitstand", "rise", "homing"})

# Real duck socket paths (duck-ipc-proto/src/lib.rs:393–422) and ports (architecture.md:80–89).
DUCK_SOCKETS = {
    "robot": "/run/robotd.sock",
    "config": "/run/configd.sock",
    "updater": "/run/updaterd.sock",
    "pad": "/run/padd/pad.sock",
    "tof": "/run/tofd/tof.sock",
    "media": "/run/mediad/media.sock",
}
DUCK_CONSOLE_PORT = 8080
DUCK_SIGNALLING_PORT = 8443


def unverified() -> list[Method]:
    return [m for m in (*INTENTS.values(), *QUERIES.values()) if not m.verified]


def require_verified(*methods: Method) -> None:
    """Raise if any of the given methods is still unverified against upstream."""
    missing = [m.name for m in methods if not m.verified]
    if missing:
        raise RuntimeError(
            "upstream method names not verified: "
            + ", ".join(missing)
            + " — read duck-ipc-proto and update docs/upstream-notes.md first (CLAUDE.md §10)"
        )
