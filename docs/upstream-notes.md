# Upstream notes — what we have verified about the Microduck API

Rule (`CLAUDE.md` §10): no JSON-RPC method name is used in code from memory. Every name in
`runtime/duckstudio/upstream.py` points back to an entry here. `duck-ipc-proto/src/lib.rs`
is the contract; `docs/design/architecture.md` upstream is a draft from 2026-07-22 and lags
the code.

## Revisions read (2026-09-19)

| Repo | Branch | Commit | Date | Notes |
| --- | --- | --- | --- | --- |
| pollen-robotics/microduck | main | `344925c9f8fa031f85428a305b1e8ec2eaae29c1` | 2026-09-17 | workspace 0.14.1, `API_VERSION = 31`, Apache-2.0 |
| pollen-robotics/microduck | main | `ac7531a77adae5e9c49d1a3f5d23f72f9af7fee1` | 2026-09-22 | 0.14.4, `API_VERSION = 34`, re-check below |
| pollen-robotics/microduck | `daemon-v0.15.0` | `a9ec4b2079ef8ee7904014089c885bb07d57d63c` | 2026-09-23 | 0.15.0, `API_VERSION = 37`; **current pin**, re-check below |
| pollen-robotics/microduck_rl | develop | `cb70b792312d559a4da09064d92009079671815f` | 2026-09-14 | Apache-2.0 |
| joeynyc/microduck-mcp | main | `0080a854fd1c200efb570ada37d9af38bf3554a1` | 2026-09-16 | Apache-2.0, pinned to API 16/28 |
| joeynyc/awesome-microduck | main | `a3815e7b73fb1e95cbb3811d80023ed619c375ab` | 2026-09-19 | CC0-1.0 |
| huggingface.co/pollen-robotics/microduck-policies | main | `manifest.json`, schema 2 | read 2026-09-19 | official policy set, tag ≥ v5 |

File references below are `path:line` in microduck@344925c unless stated otherwise. The code
(`runtime/duckstudio/upstream.py`) names symbols instead of lines since the 0.14.4 re-check —
lines drift with every release, `grep -n 'pub struct MoveParams'` does not.

## Re-check against 0.15.0 (2026-09-24)

Pin moved `ac7531a` → `a9ec4b2` (`sim/fetch-upstream.sh`); `microduck_rl` develop is still
`cb70b79`. Read as a diff of `duck-ipc-proto/src/lib.rs`, `robotd`, `mediad` and the design
docs, then run live.

- **Nothing we send or read changed.** The `method::*` constants are identical (same set,
  byte for byte), still 40 `deny_unknown_fields`, `mediad/src/route.rs` untouched. We parse
  replies as dicts, so new fields pass through.
- What v35–v37 add, all optional and absent from older daemons:
  - v35 `ComponentStatus.last_checked`, v37 `ComponentStatus.last_check_attempt {at, error?}`
    (`update.status`): when the update source last answered, and why the last check did not.
    We do not call `update.status`.
  - v36 `RobotState.{velocities, currents_ma}`: measured joint velocity (rad/s) and load (mA,
    magnitude) per joint, on every `robot.state` frame. Empty means *not reported* (older
    daemon, a backend with no servos, or `[control] publish_velocity_and_load = false`),
    never zero. We do not read them yet. `currents_ma` is the duck's only measure of external
    force — worth a look for "someone is holding/pushing the duck" in M4.
- `/run/mediad/remote.json` (`RemoteStatus`): whether mediad is signed in to the rendezvous
  and under which account. A file, not a method; `robotctl health` prints it.
- **The agent transport is decided upstream, and it is not the WebSocket.**
  `architecture.md` and `remote-access-design.md` §3.8 (#323): a server-side program drives a
  duck over the **rendezvous control lane** — JSON-RPC in a `peer` envelope, `POST /send` out,
  SSE back, through the HF rendezvous Space the mini fleet uses; no ICE/DTLS/TURN, authenticated
  by the account at both ends. No pixels on it (frames from WebRTC or `media.stream`), and a
  budget of 1200 requests per 60 s per peer, overrun = `429` on the whole peer, the robot's
  own lease included. Client halves live in upstream `spaces/shared/` (`rendezvous.py`,
  `wire.py`, `control.py`); the roadmap packages them as the Python SDK. For us: ADR-0006
  (`ssh -L`) stands and nothing changes before M4. But this lane needs no terminal on either
  end, which fits §3.1 better than ssh — and 20 req/s is enough for our 10 Hz `robot.move`
  only if state comes as a subscription, not as polls. A candidate for revisiting ADR-0006
  once a duck is here.
- **Perception next to the sensor exists, for ducks only.** `mediad/src/detect.rs` runs the
  *duck detector* (`duck-detect` crate; model trained in `pollen-robotics/duck_detector`, one
  class, 320×320 letterboxed RGB, INT8 `.rknn` on the NPU or `.onnx` on the CPU, 2 looks/s for
  thermal reasons). Its sightings (`{width, height, found: [{score, box_}], took_ms}`) go as
  notifications **only to WebRTC datachannel peers**, not to any Unix socket we use; installed
  and updated through `detector.check` / `detector.install` (v28). There is no person class
  and no person detector upstream, so finding people stays ours (`perception/person_local.py`
  today; a real detector is open). Worth reading the socket side again when a duck-to-duck
  behavior comes up.
- `duck-sim`: the #320 heredoc fix (#321), plus CI lint. Checked live: no `command not found`
  at startup, and the comment in `updater-duck-a.toml` reads as written.
- Live on duck-sim 0.15.0 (macOS, camera on duck-a): robotd `hello` → `{api_version: 37,
  daemon_version: "0.15.0"}`; the contract suite passes against it (`DUCKSTUDIO_SIM=1 pytest
  tests/backends`: 101 passed, 1 skipped). `GET :8080/frame` still a 360×640 PNG.
- `microduck_rl#46` (walking policies step in place): still open, no maintainer answer, nothing
  new on `develop` — the simulated duck still does not walk. **It barely turns either**
  (2026-09-24, measured from standing, `robot.move {vx 0.08, vyaw −0.245}` at 10 Hz for 60 s,
  `policy: walk`, never fallen): the position moves ~2 mm (4.8 m commanded); yaw drops 0.10 rad
  in the first 10 s, around the stand → walk switch, then 0.011 rad in the next 50 s (~12 rad
  commanded). Posted as a comment on #46. The executor now says so (`executor/progress.py`:
  „Die Ente tritt auf der Stelle“).
  The Studio's duck menu says it under „Simulation“ (`backend.sim.caveat`); **remove that
  line when #46 is fixed** and the pin moves to a policy set that walks.
- Start pose, five starts on 0.15.0: the duck settles at a heading of +18…+22° (IMU yaw, odom at
  the origin), so the marker 1.5 m "ahead" shows at −20…−22°, on the right of the frame — the
  same offset follow-me steered against on 0.14.4 (`vyaw ≈ −0.23`). Once of three `SIT` starts
  (upstream's default keyframe) the sitstand rise fell over (`fall verdict changed
  fallen=true`) and the duck came up at −81°, 0.6 m off, with the marker out of view; then
  follow-me starts with its `look_around`. `DUCK_SIM_KEYFRAME=STAND` does not change the
  heading. Restarting the sim (`sim/up.sh`) is the fix; not reported upstream — a random
  outcome of a learned rise in simulation, not a daemon bug.

## Re-check against 0.14.4 (2026-09-22)

Pin moved `344925c` → `ac7531a` (`sim/fetch-upstream.sh`); `microduck_rl` develop is still
`cb70b79`. Read as a diff of `duck-ipc-proto/src/lib.rs`, then run live.

- **Nothing we send or read changed.** Compared struct by struct (fields, serde attributes):
  `MoveParams`, `HeadParams`, `LookParams`, `PoseParams`, `SoundParams`/`SoundTag`,
  `SubscribeParams`, `DoParams`, `EnableParams`, `PoliciesResult`, `RobotState`, `MoveState`,
  `SafetyState`, `ImuState`, `TofFrame`, `TofStreamResult`, `PadReport`, `MediaFrameHeader`,
  `HelloParams`/`HelloResult` are identical; no `method::*` constant added or removed; still
  40 `deny_unknown_fields`.
- What v32–v34 add, all optional and absent from older daemons:
  - v32 `ComponentStatus.{degraded, reason}` (updaterd's `update.status`) — a board fault
    (bench board, servo supply off) is no longer indistinguishable from a broken release. We
    do not call `update.status`.
  - v33 `HealthResult.cpu_throttle {level, max_level, khz, max_khz}` — "reported, never
    judged". Our `health()` adds the warning `cpu_throttled` by upstream's own rule
    (`CpuThrottle::throttled`: level > 0, or ceiling below the board maximum). duck-sim sends
    none on macOS.
  - v34 `PolicySearchHit.{description, preview}` — the publisher's sentence (untrusted) and a
    clip URL, on `policy.search`. We search the Hub over HTTP ourselves (`hub.py`): the
    description already comes from `manifest.json`, our preview is the model card's
    thumbnail. Upstream's video convention (`docs/policy-manifest.md`) is not read — worth
    adopting when the building-blocks panel wants to play a clip.
- robotd behaviour changes that do **not** touch our paths: a mode switch (`robot.setMode`)
  now waits for a policy load and never stands a limp robot up (#195, #228, #319); padd drops
  a hold, not the shutdown, when the pad disconnects (#273). `getup` stays `robot.enable
  {on: true}`.
- Live on duck-sim 0.14.4 (macOS, camera on duck-a): robotd `hello` → `{api_version: 34,
  daemon_version: "0.14.4"}`; tofd still answers `hello` with -32601; the contract suite
  passes against it (`DUCKSTUDIO_SIM=1 pytest tests/backends`: 92 passed, 1 skipped).
- Upstream glitch, harmless for us: `scripts/duck-sim` writes `updater-duck-a.toml` from an
  unquoted heredoc whose comment carries backticks (`` `policy.fetch` ``, `` `Permission
  denied ...` ``), so `sh` runs them and prints `policy.fetch: command not found` at startup.
  Only the comment text in the generated file is affected. Reported 2026-09-22 as
  `pollen-robotics/microduck#320` (introduced in 2581a38); fixed 2026-09-23 by #321
  (e5bd7ae, which also lints `scripts/duck-sim` in CI), shipped in `daemon-v0.15.0`.
- `microduck_rl#46` (walking policies step in place): still open, no maintainer answer. One
  community comment (2026-09-18) with a plausible cause — the `feet_air_time` reward is
  gated on the *command*, not on achieved motion, so stepping in place is paid — and a
  tracking-error metric that overstates the steady-state error about 3×. Nothing on
  `develop` yet, so the simulated duck still does not walk.

### Roll and pitch

`SafetyState.gravity` is projected gravity in the trunk frame; `ImuState` documents that frame
as x forward, y left, z up, and `quat` as trunk → world `[w, x, y, z]`. Our `Imu.roll =
atan2(-gy, -gz)`, `pitch = atan2(gx, hypot(gy, gz))` is REP-103 in that frame: roll > 0 right
side down, pitch > 0 nose down.

Checked on duck-sim 0.14.4, standing (`policy: stand`), each `robot.pose` held 3 s at 10 Hz:

| `robot.pose` | gravity | roll from gravity | pitch from gravity | from IMU quat |
| --- | --- | --- | --- | --- |
| nominal | `[+0.003, -0.002, -1.000]` | +0.1° | +0.2° | same |
| roll +0.25 | `[+0.009, -0.240, -0.971]` | **+13.9°** | +0.5° | same |
| roll −0.25 | `[+0.008, +0.229, -0.973]` | **−13.3°** | +0.4° | same |
| pitch +0.25 | `[+0.240, -0.004, -0.971]` | +0.2° | **+13.9°** | same |
| pitch −0.25 | `[-0.236, -0.002, -0.972]` | +0.1° | **−13.7°** | same |
| sitting | `[-0.894, -0.005, -0.449]` | +0.6° | −63.3° | same |

So our signs agree with the quat to the decimal and with `robot.pose`'s own roll/pitch
(0.25 rad commanded ≈ 14.3°, 13.3–13.9° reached). A sitting duck leans back, nose up, which is
negative pitch as it should be. The rows are pinned in
`tests/backends/test_sim_backend.py::test_roll_and_pitch_signs_follow_robot_pose`. Still open:
whether the real duck's IMU is mounted the way the sim assumes — a hand tilt on day one
(`docs/m4-hardware-checklist.md` §3). Aside: `robot.pose` on a *sitting* duck does not tilt it
the way it tilts a standing one; stand it up first.

## Wire format

- JSON-RPC 2.0, one object per line (NDJSON), one newline = one frame, over Unix sockets
  (`duck-ipc-proto/src/lib.rs` header; `architecture.md` §2.2).
- Request `{jsonrpc, id?, method, params?}`; no `id` = notification. Continuous intents are
  sent as notifications, server pushes (`robot.state`, `tof.frame`, `pad.report`) are
  notifications too.
- `hello {api_version}` → `{api_version, daemon_version?, revision?}` on every daemon.
  Version skew is logged, never refused (`lib.rs:59`). Unknown method → `-32601`, unknown
  params member → `-32602`. **All params structs are `deny_unknown_fields`**: never send
  extra keys.
- One connection serves one request at a time; a stream (`robot.subscribe`, `tof.stream`,
  `pad.input`) owns its connection for good. Use separate sockets for streams and calls
  (`enum Lane`, `lib.rs` ~1060).

## Sockets and ports

| Daemon | Socket / port | Namespaces |
| --- | --- | --- |
| robotd | `/run/robotd.sock` | `robot.*`, `pad.bindings`, `pad.bind` |
| configd | `/run/configd.sock` | `net.*`, `system.*`, `pad.status/pair/forget` |
| updaterd | `/run/updaterd.sock` | `update.*`, `policy.*`, `detector.*`, `account.*` |
| padd | `/run/padd/pad.sock` | `pad.input` only |
| tofd | `/run/tofd/tof.sock` | `tof.stream`, `head_imu.stream` |
| mediad | `/run/mediad/media.sock`; TCP `:8080` console + `GET /frame`; TCP `:8443` WebRTC signalling | `media.frame`; `media.video`, `media.stream` over the datachannel |

Source: `lib.rs:393–422`, `architecture.md:80–89`, `mediad/src/main.rs:37,79`. Every daemon
takes `--socket`; root overridable via `DUCK_RUNTIME_DIR`.

## robotd methods we use

Units (`lib.rs` ~2030): radians and rad/s, trunk frame, right-handed, `x` forward, `y` left,
`z` up, positive `vyaw` turns left.

| Method | Params → result | Source | Notes |
| --- | --- | --- | --- |
| `robot.move` | `{vx, vy, vyaw}` (all default 0) | `lib.rs:2044 MoveParams` | Notification, 20–50 Hz recommended; duck-sim resends at 10 Hz. Last-writer-wins. **No velocity clamp anywhere upstream** (`duck-control/src/safety.rs:84` limits are Deadman/Range/NotFinite only). |
| `robot.head` | `{neck_pitch, head_pitch, head_yaw, head_roll}` | `lib.rs:2060` | Does not refresh the deadman (`robotd/src/intents.rs:662`). |
| `robot.look` | `{x, y, z, neck_pitch}` m → `LookResult{head, clamped}` | `lib.rs:2074–2094` | Floor ≈ 0.12 m below trunk origin. Resend to hold gaze. |
| `robot.pose` | `{z, roll, pitch, active}` | `lib.rs:2248` | Trained ranges z −0.025..+0.010 m, roll/pitch ±0.26 rad, unclamped. |
| `robot.stop` | none → `IntentResult{accepted: true}` | `robotd/src/main.rs:4478` | Zero velocity. Always accepted, no gate. "Still not a physical e-stop" (`mediad/src/route.rs` ~95). |
| `robot.relax` | none | `lib.rs` | Cut joint power; the robot collapses. |
| `robot.init` | none | `lib.rs` | Power joints, ramp to home pose. |
| `robot.enable` | `{on, toggle=false}` | `lib.rs EnableParams` | Hand robot to / take from the policy. |
| `robot.do` | `{skill}` → `IntentResult` | `lib.rs DoParams` | One-shot skills: `ground_pick`, `sit_toggle` (built in), `kick_left`, `kick_right`, `roulade` (config). Refused while not `homed`. |
| `robot.sound` | `{tag: alarm\|greet\|inquire\|peck\|chirp\|coo\|wheee, hold?}` | `lib.rs:2098–2143` | `robotctl quack` plays `chirp`. |
| `robot.health` | none → `{healthy, degraded, reason?, battery?: {volts, percent}, ...}` | `lib.rs:3259` | `percent` is 0–100. Battery absent = not known yet. Reported, never judged. |
| `robot.subscribe` | `{hz?}` → `SubscribeResult`, then `robot.state` notifications | `lib.rs:2638–2680` | Absent `hz` = 50 Hz. |
| `robot.state` | notification `{t, move{requested, applied, limited_by[]}, head[4], policy, safety{fallen, limp, gravity, gain?}, loop{hz, missed}, joints[15], targets[15], odom, imu?, ...}` | `lib.rs:3487` | Joint order `JOINT_NAMES` (`lib.rs:456`): left leg 5, neck/head/mouth 5, right leg 5. `limited_by` contains `"deadman"` when expired. |
| `robot.policies` | none → `{mode, enabled, slots[], skills[], homed?, sitting?}` | `lib.rs:2329–2400` | Use `sitting` before `sit_toggle`. |
| `robot.mode` / `robot.setMode` | `{mode: walk\|roller}` | `lib.rs` | `setMode` refused over WebRTC. |
| `robot.loadPolicy` | `{slot?, path?}` | `lib.rs:2311` | Slots: walk, stand, sitstand, ground_pick, kick_left, kick_right, roulade. Persists to robotd.toml. |

Not present as methods: `robot.walk`, `robot.velocity`, `robot.sit`, `robot.stand`,
`robot.getup`, `robot.pickup`, `robot.kick`, `robot.quack`, `robot.estop`, `get_frame`.

## Deadman / heartbeat

- No heartbeat method exists. The deadman is the age of the last `robot.move`:
  `SafetyParams.deadman_ms`, default **500** (`robotd-params/src/lib.rs:1685,1768`;
  `pad_link::DEADMAN_MS = 500` in `lib.rs:4190`).
- Expiry zeroes the twist only; head targets are kept (`duck-control/src/safety.rs:230`).
  Losing comms makes the robot stand still (`robotd-design.md` §2.4).
- Consequence for us: the executor's heartbeat *is* resending `robot.move` (or `robot.stop`)
  inside 500 ms. `upstream.DEADMAN_MS` / `MOVE_RESEND_HZ` encode this.

## Camera

- `media.frame` on `/run/mediad/media.sock` (`lib.rs:483`, `mediad/src/frame.rs`): one JSON
  line `{width, height, format: "UYVY", bytes, captured_at_unix_us, rotate}` followed by raw
  UYVY pixels (~1.8 MiB). Not JPEG, local only, 16 clients, 5 s timeout.
- HTTP `GET :8080/frame` → **PNG** (`mediad/src/web.rs:97`), `Cache-Control: no-store`,
  503 while capture is down. This is what microduck-mcp uses.
- `media.stream` (`mediad/src/session.rs:255`): over the WebRTC control datachannel only;
  the robot dials **our** `wss://` and pushes JPEG or H.264, `fps` 0.2–15 (default 5).
- `get_frame` exists only in doc comments pointing at architecture.md §5.3.

## Remote transport for agents

- The inbound WebSocket surface for server-side programs is **design only**:
  `docs/design/remote-webrtc.md` §12 lists it under "Deferred"; roadmap M5 "in progress".
  In `mediad`, `tokio-tungstenite` is used only as a client. **Superseded in 0.15.0:** the
  WebSocket is gone from the design; agents use the rendezvous control lane (re-check
  against 0.15.0 above).
- Real remote paths today: WebRTC `control` datachannel via mediad (LAN signalling `:8443`
  or HF rendezvous after `account.login`; routing table `mediad/src/route.rs` allows
  `robot.move/head/look/pose/mouth/do/sound/stop/enable/init/relax/subscribe/policies/
  loadPolicy/skills`, refuses `robot.setMode`), or `ssh -L` to the Unix sockets
  (`robotd-design.md` §4.3; microduck-mcp does exactly this).
- For the simulation: plain Unix sockets, no tunnel needed.

## ToF

- `tof.stream` on `/run/tofd/tof.sock` (`lib.rs:811`), no params →
  `{accepted, sensor?: "VL53L8CX", unavailable?, rows, cols, hz}` (`lib.rs:4479`), then
  `tof.frame` notifications `{seq, at_us, t_ns, rows, cols, distance_mm: [i16], status: [u8]}`
  row-major (`lib.rs:828,4507`). **Millimetres**, raw ST status. ~15 Hz.
- Our `TofFrame.distances_m` is the normalised metres view; the backend converts.

## Gamepad and authority

- `pad.input` on `/run/padd/pad.sock` (`lib.rs:795`) → `pad.report` notifications
  (`Attached | Frame{events[]} | Detached | ImuAttached | Imu | ImuDetached`,
  `lib.rs:4280–4470`). A raw evdev diagnostic tap.
- **robotd has no authority arbitration.** padd is an ordinary client writing `robot.move` at
  50 Hz into the same last-writer-wins slot (`robotd/src/intents.rs` header;
  `robotd-design.md` §4.3; `architecture.md` §9 lists it as open). The order in `CLAUDE.md`
  §4 (e-stop > gamepad > executor > planner) must be implemented in our runtime: subscribe to
  `pad.input`, treat any `Frame` as takeover, stop sending `robot.move`.

## Policies and skills

- Official set `pollen-robotics/microduck-policies` ≥ v5 (`Cargo.toml:58–59`), ten ONNX
  files: `alpha_walking`, `velstand` (slot walk, walking + fall recovery), `alpha_stand`,
  `roller`, `alpha_sitstand` (→ `sitstand`), `alpha_ground_pick` (→ `ground_pick`, 2.8 s),
  `roller_crouch`, `roulade` (1.0 s), `ball_kick_left`/`_right` (→ `kick_left`/`kick_right`,
  0.5 s). Obs 61, actions 14.
- Defaults in walk mode (`robotd-params/src/lib.rs:1579–1599`): walk = `velstand.onnx`,
  sitstand = `alpha_sitstand.onnx`, ground_pick = `alpha_ground_pick.onnx`; **no stand policy
  loaded** since v5. Gait choice (stand vs. walk) is by command magnitude inside robotd.
- No get-up skill upstream; velstand recovers by itself while enabled. Community episodic
  get-up: `QingMuLYL/microduck-standup`.
- Mapping used by our backends (`upstream.BEHAVIOR_CALLS`): sit/stand → `robot.do sit_toggle`,
  pickup → `robot.do ground_pick`, kick → `robot.do kick_right`, quack → `robot.sound chirp`,
  getup → `robot.enable {on: true}`; recovery measured in M2, see "Falling over in duck-sim".
- microduck_rl: Python `>=3.12,<3.13`, `mjlab==1.3.0`; training needs CUDA, the sim body
  runs on CPU.

## duck-sim

- `scripts/duck-sim` (POSIX sh) = `up`: builds daemons with cargo, starts `duck-body`
  (MuJoCo, from the microduck_rl venv at `~/Pollen/microduck_rl` or `DUCK_SIM_RL`), `tofd
  --sim`, `configd --fake-net --fake-pads`, `updaterd`, `robotd --sim 127.0.0.1:7801`.
  `boot N` uses systemd-nspawn (Linux only). **No docker-compose upstream.**
- Headless: `DUCK_SIM_VIEWER=0`. macOS viewer needs `mjpython`; camera off Linux needs
  `cargo build -p mediad --features gstreamer` plus gstreamer via Homebrew.
- Sockets under `DUCK_SIM_STATE` (default `~/.cache/duck-sim`): `duck-a.sock` (robotd,
  `duck.sock` symlink), `duck-a-tof.sock`, `duck-a-config.sock`, `duck-a-updater.sock`,
  `duck-a-frame.sock` (with `DUCK_SIM_CAMERAS=a`). Console `http://127.0.0.1:8080`.
- Knobs: `DUCK_SIM_DUCKS`, `DUCK_SIM_SCENE` (`apartment`), `DUCK_SIM_KEYFRAME`
  (`SIT|HOME|STAND|FOLD`). Realtime factor below 1.0× → policies cannot balance.

## Details read for the `sim` backend (2026-09-19, same revision)

- `robot.state.policy` labels (`robotd/src/control.rs`, `robotd/src/main.rs:2822–2881`):
  `walk`, `stand`, `sitstand`, `sit` (holding the sit), `rise` (standing up from the sit,
  seen live), `ground_pick`, skill labels while a one-shot runs (`kick_left`, `roulade`, ...),
  `held` (no policy driving), `homing`, `limp_fall`, `limp_pose`. Our `Flags.sitting` is
  `policy == "sit"`; `standing` is "not fallen, not limp, not in {sit, limp_fall, limp_pose}
  and not mid-transition {sitstand, rise, homing}".
- `RobotState.move` is `{requested[3], applied[3], limited_by[]}`; `safety` is
  `{fallen, limp, gravity[3], gain?}`; `odom` is `{position[3], yaw}`; `imu?` is
  `{gyro[3], quat[4]}`. Roll/pitch in our `Imu` are derived from `safety.gravity`; the sign
  convention was checked against a tilted sim duck on 2026-09-22 ("Roll and pitch" above).
- `DoParams.skill` is a plain `String` (`lib.rs:2226`), refused with the known list.
- `HealthResult.motors` is `{hottest, max_c, mean_c}` (`lib.rs:3419`); our
  `temperatures_c` carries `servo_max` and `servo_mean`.
- `scripts/duck-sim` writes its own `robotd.toml` naming **`alpha_walking.onnx` as walk and
  `alpha_stand.onnx` as stand** (`scripts/duck-sim:236–246`), so the simulated duck runs
  alpha_walking, not robotd's velstand default. Policies come from
  `scripts/seed-policies.sh` into `$DUCK_SIM_STATE/policies/current` (needs network once).
- **tofd does not answer `hello`.** Against duck-sim 0.14.1 it replies -32601 "tofd serves
  tof.stream and head_imu.stream and nothing else". The "every daemon answers hello" line
  above holds for robotd/configd/updaterd/mediad only; our tof connection skips the handshake.
- `robotd --sim` reports a constant battery of 50 % (`robot.health.battery.percent = 50`),
  servo temperatures 32 °C. Good enough to pass our 15 % floor; not a simulation of drain.
- **Deadman observed live** (duck-sim 0.14.1, our `robot.move` at 10 Hz then silence):
  ~0.5 s after the last message `robot.state.move.limited_by == ["deadman"]`, `policy`
  drops from `walk` to `stand`, `requested` keeps the stale value and `applied` ramps down
  0.1 → 0.017 → 0.001 → 0.0 over roughly half a second. So "stopped" is `applied ≈ 0`, not
  `requested == 0`; our `Flags.moving` reads `applied`.
- `robot.subscribe` on duck-sim answers `walk: alpha_walking.onnx, stand: alpha_stand.onnx`
  (the script's params file, see above). Odometry moved only a few millimetres during a 3 s
  0.1 m/s walk through our backend **and** under upstream's own `duck-sim drive 0.1 0` for
  8 s (bare-floor scene, 1.01× realtime). Whether alpha_walking walks in place at 0.1 m/s or
  odometry lags is unverified and belongs to M2 (follow-me needs real progress).
- **Simulated camera observed live** (macOS, gstreamer 1.28.7 via Homebrew, duck-sim
  0.14.1 with `DUCK_SIM_CAMERAS=a`): `mediad --sim-camera 127.0.0.1:7901` comes up, logs
  "capture rate fps=32 target=30", registers itself as WebRTC producer on `:8443` with
  `simulated: true`; `GET :8080/frame` returns `image/png`, **360×640 portrait** (~64 KB),
  `Cache-Control: no-store`. Our backend's `frame()` returns exactly those bytes; the API
  sniffs the PNG signature for the content type. 2 fps polling from the Studio is fine.
- **`sit_toggle` is not instant.** Running our contract suite against duck-sim left the duck
  sitting: `sit` then `stand` within a second — `robot.policies.sitting` was still `false`
  while the scripted sit was in progress (`policy == "sitstand"`), so our "already standing"
  guard skipped the second toggle. For M2 the executor must treat `sitstand` as "in
  transition" and wait before deciding; the backend guard alone is not enough.
- **Camera geometry, checked against frames**: `GET /frame` is already upright — 360 px wide,
  640 px tall, floor at the bottom — i.e. the duck sees a tall, narrow slice (≈45° × 72°).
  mediad's logged intrinsics (`fx = fy = 434.56`, `cx = 320`, `cy = 180`) describe the sensor's
  640×360 frame; after the quarter turn the optical centre is at (180, 320) and `fx` is
  unchanged. Our detector: `bearing = -atan2(px - 180, 434.56)`, positive = left like `vyaw`.
  A 0.24 m cylinder 1.5 m ahead spans ≈70 px, so range from apparent width works as a
  fallback for the ToF.
- **Simulated ToF sends `distance_mm = 0` with `status = 255` for zones without a target**
  (empty sky), `status = 5` for valid ones (`microduck_rl` `sim/tof.py`). Reading zeros as
  0 m tripped every "too close" rule; the backend maps non-valid zones to the sensor's
  4 m range instead. With the head level, the lower rows see the floor at ~1.2 m.
- **A live `tof.frame` from duck-sim** (`sensor: "sim"`, 15 Hz): rows 0–1 are mostly
  `0/255` (sky, no target), row 2 reads ≈2.3 m, rows 3–7 read the floor at 1.16 / 0.78 /
  0.60 / 0.48 / 0.41 m — the sensor looks slightly down. A 1.2 m marker 1.26 m ahead-right
  showed up as ≈1.25–1.32 m in rows 0–2 of columns 5–6, exactly where the camera put it.
  Hence the fusion picks the zone the blob's image position points at, never the row minimum.
- **Follow-me observed live** (2026-09-19): „Folge mir“ → person found at −15°, 1.26 m
  (ToF-fused) → `robot.move` at 10 Hz with `vx 0.08`, `vyaw ≈ −0.23` → „Stopp“ ends the step
  → `robot.sound chirp` → done. The duck turned a few degrees toward the marker and did not
  advance (next item).
- **The simulated duck does not walk.** With `alpha_walking.onnx` or `velstand.onnx` in the
  walk slot, `policy = walk`, `applied = [0.15, 0, 0]` at 50 Hz, the leg joints move by
  < 0.02 rad peak-to-peak, odometry and the camera agree that nothing advances — also under
  upstream's own `duck-sim drive 0.15 0`. Turning yields a few degrees. This matches the open
  upstream issue pollen-robotics/microduck_rl#46 (2026-09-10): velocity-family policies
  "converge to standing / stepping-in-place"; the official `alpha_walking.onnx` "drifts
  0.66 m / 20 s — also does not walk" in their MuJoCo, with an observation-convention mismatch
  suspected. StandUp/SitStand work (we see `sit`/`rise` fine). Consequence for M2: perception,
  steering and the step logic are verified live in the sim; forward progress is verified
  against the mock only, until upstream's sim gait or the hardware arrives.
- Python 3.12's `asyncio.Server.wait_closed()` waits for accepted connections; anything
  faking a daemon must close them first (bit us in tests, not upstream).

## Falling over in duck-sim (2026-09-22/23, 0.14.4)

Needed for M2 ("Sturz-Recovery getestet durch simulierten Stoß"). Measured through our runtime
and straight on the sockets; the drill is `sim/fall-drill.py`.

- **No push in duck-body.** `body_server.py` answers `hello/read/write/gain/torque/slow/tof`
  and nothing else, and we do not fork it. The push is upstream's own API instead:
  `robot.pose {pitch: 2.5, active: true}`, ten times the trained ±0.26 rad, held 2.5 s.
  `PoseParams` clamps nothing, so the stand policy leans into it and tips. Pitch 0.9 is not
  enough (36° lean, stays up); 2.5 lays it down (`fallen`, trunk 4 cm instead of 11.6 cm).
- **It gets up by itself.** Once the push lets go, `alpha_stand` rights the duck from 72–90°
  to upright in ~0.8 s. It never goes limp (`safety.gain` stays 160; `safety.limp_fall` is
  off in duck-sim's `robotd.toml`, and the cheatsheet's `fall_limp`/`fall_recover` names do not
  exist in the code). Our `getup` → `robot.enable {on: true}` is answered `"enabled —
  driving"`: harmless and redundant in the sim, which drives anyway.
- **`fallen` clears early.** robotd's verdict is projected gravity z above `fall_gravity_z`,
  about 60° of tilt. On the way up it drops at ~60°, so "not fallen" is not "standing": our
  `standing` flag therefore also requires `gravity z ≤ -0.90` (≈26°, upstream's
  `FallPredictorConfig::tilt_z`, "which ordinary walking does not reach").
- **The head comes back last.** When the trunk is level again the neck is still curled at
  about -90° (`joints[5]`, `neck_pitch`) and needs another 1.1–1.3 s back to its rest pose
  (+12°, head_pitch +26°). All that time the head ToF looks at the floor at the duck's feet:
  0.03–0.14 m in the centre columns, against ~0.5 m of floor ahead when standing normally.
- **What that did to follow-me.** Before the fix: getup counted as done at 60° (`fallen`
  false → `standing` true), the walk resumed at 37° of tilt, read ToF 0.03 m and ended on
  „Hindernis zu nah“ a tick later — follow-me finished after every fall. Now `getup` ends on
  `steady` (standing without a break for `STEADY_S` = 2 s); the walk resumes with the head up
  and ToF at 0.49 m and carries on toward the person. While the duck tips, walk intents are
  refused by the precondition (`standing`) instead of pushing a falling duck forward.
- The real duck runs velstand and may set `safety.limp_fall` (limp while falling, land, pose
  back, hand to standing); both the timings and whether our upright threshold fits are M4
  measurements (`docs/m4-hardware-checklist.md`).

## microduck-mcp (community reference)

Transports `unix | ssh | sim | mock`; `ssh` = `ssh -N -L` tunnels for robotd/configd/updaterd
sockets plus `:8080` for `/frame`. Its `sim` is its own Python re-implementation, not
upstream duck-sim. Calls `robot.health/move/head/stop/init/do/sound/subscribe/policies/
loadPolicy`, `policy.fetch/search`. Resends `robot.move` every 200 ms, refuses motion under
15 % battery, 250 ms between motion tool calls, clamps 0.25 m/s / 1.0 rad/s. Pinned to
API 16/28, behind current 31.

## Discrepancies vs. the handover (`CLAUDE.md`)

1. `robot.walk` → **`robot.move`** `{vx, vy, vyaw}` (not `yaw`). Notification, not request.
2. `get_frame` **does not exist**. Sim/duck frames come from `GET :8080/frame` (PNG) or
   `media.frame` (UYVY). `DuckBackend.frame()` therefore returns JPEG *or* PNG.
3. WebSocket for agents is **not implemented** upstream. Real duck = `ssh -L` tunnels or
   WebRTC datachannel (M4 ADR). Sim = local Unix sockets.
4. Heartbeat = keep sending `robot.move`; deadman 500 ms; no dedicated method.
5. `tof.stream` correct, but frames are `tof.frame` notifications in **millimetres** from
   tofd's own socket.
6. `pad.input` correct, but it is a raw evdev tap; **robotd has no arbitration**. Gamepad
   preemption is our job.
7. `pad.*` is split: `pad.input` → padd, `pad.bindings/bind` → robotd, rest → configd.
8. Named behaviors map to `robot.do` / `robot.sound` / `robot.enable`; there is **no getup**
   skill. `roller` is a mode (`robot.setMode`), not a per-behavior policy.
9. Default walk policy is **`velstand`**, not `alpha_walking`; no stand policy by default.
10. Battery is `percent` 0–100; our `Health.battery` is `percent / 100`.
11. Ports 8080/8443 and `/run/robotd.sock` correct; the other five sockets added above.
12. Upstream ships **no docker-compose** for duck-sim; M1 wraps `scripts/duck-sim` instead
    (needs an ADR when M1 starts).
13. Velocity limits do not exist upstream; the manifest clamps in our `IntentGate` are the
    only ones. Never disable them.

## Hugging Face Hub — community policies (read live 2026-09-20)

Not upstream code, but the other thing we read without being able to run it. Method: the
public API (`https://huggingface.co/api/models?filter=microduck-policy`) plus each repo's
`resolve/main/manifest.json`; 25 repos at the time of reading.

| What | Finding |
| --- | --- |
| Tag | `microduck-policy` (all 25); most also carry `microduck`, `mjlab`, `onnx` |
| Files | `policy.onnx` everywhere; usually `config.json`, often `manifest.json`, sometimes `checkpoint.pt`, `params/*.yaml`, `media/preview.*`, `SHA256SUMS` |
| `manifest.json` | a community convention, not a standard: `schema_version` 1, 2, 4, 5; `model_api` 1 or 2 |
| `command` block | **a sentence** (`HannesVonEssen/microduck-basketball`), **a list of free-text lines** (`RemiFabre/microduck-flamingo-cycle`: flag / side, not a velocity), or **absent** (`cdeplanne/*`, `HannesVonEssen/microduck-swing`) |
| Machine-readable ranges | 1 of 25: `"… continuation ranges ±0.15 m/s, ±0.10 m/s, ±0.50 rad/s"` |
| Provenance worth showing | `status`, `hardware_tested` (false where stated), `robot.control_hz` (50 everywhere), `description`, downloads/likes, commit `sha` |
| Loading a policy | not ours: `robot.loadPolicy {slot?, path?}` on the duck, slots `walk, stand, sitstand, ground_pick, kick_left, kick_right, roulade`; fetching is `policy.fetch` on `updaterd` (seen in microduck-mcp, **unverified against upstream code**) |

Consequence, recorded as ADR-0005: the Studio browses and records provenance, a person picks
which builtin block a policy stands in for, and limits are only ever narrowed by what a repo
states. `runtime/tests/hub/fake_hub.py` keeps these shapes as fixtures; the live check is
`DUCKSTUDIO_HUB=1 uv run pytest tests/hub/test_hub_live.py`.
