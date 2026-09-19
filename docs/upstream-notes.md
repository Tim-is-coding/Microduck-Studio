# Upstream notes — what we have verified about the Microduck API

Rule (`CLAUDE.md` §10): no JSON-RPC method name is used in code from memory. Every name in
`runtime/duckstudio/upstream.py` points back to an entry here. `duck-ipc-proto/src/lib.rs`
is the contract; `docs/design/architecture.md` upstream is a draft from 2026-07-22 and lags
the code.

## Revisions read (2026-09-19)

| Repo | Branch | Commit | Date | Notes |
| --- | --- | --- | --- | --- |
| pollen-robotics/microduck | main | `344925c9f8fa031f85428a305b1e8ec2eaae29c1` | 2026-09-17 | workspace 0.14.1, `API_VERSION = 31`, Apache-2.0 |
| pollen-robotics/microduck_rl | develop | `cb70b792312d559a4da09064d92009079671815f` | 2026-09-14 | Apache-2.0 |
| joeynyc/microduck-mcp | main | `0080a854fd1c200efb570ada37d9af38bf3554a1` | 2026-09-16 | Apache-2.0, pinned to API 16/28 |
| joeynyc/awesome-microduck | main | `a3815e7b73fb1e95cbb3811d80023ed619c375ab` | 2026-09-19 | CC0-1.0 |
| huggingface.co/pollen-robotics/microduck-policies | main | `manifest.json`, schema 2 | read 2026-09-19 | official policy set, tag ≥ v5 |

File references below are `path:line` in microduck@344925c unless stated otherwise.

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
  In `mediad`, `tokio-tungstenite` is used only as a client.
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
  getup → `robot.enable {on: true}` (recovery sequence to be decided in M2).
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
  convention is **not yet checked** against a tilted sim duck.
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
