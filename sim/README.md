# sim — upstream duck-sim, wrapped (ADR-0002)

The real daemons (`robotd --sim`, `tofd --sim`, `configd`, `updaterd`, optionally `mediad`)
against a MuJoCo body from `microduck_rl`. Nothing here is ours except two shell wrappers.

```bash
./sim/fetch-upstream.sh        # pinned checkouts into sim/upstream + sim/upstream-rl, uv sync
./sim/up.sh                    # build (first time: minutes) and start, headless, camera on duck-a
./sim/up.sh status             # health, standing?
./sim/up.sh ctl health         # anything robotctl does
./sim/up.sh drive 0.1 0        # walk forward for a few seconds
./sim/up.sh down
```

Requirements: `cargo` (Rust ≥ 1.89, e.g. `brew install rust`), `uv`, Python 3.12 (uv fetches
it), and for the camera off Linux `brew install gstreamer libnice-gstreamer` (duck-sim checks
for the elements `nice`, `webrtcsink`, `x264enc` and builds `mediad --features gstreamer`
itself; that build takes a few minutes once). Without the camera set `DUCK_SIM_CAMERAS=`
(empty) and the duck runs blind: `frame()` then raises `NoCamera` and the Live panel shows
"Diese Ente hat gerade keine Kamera".

Verified on macOS with duck-sim 0.14.1: `GET http://127.0.0.1:8080/frame` answers a 360×640
PNG (portrait: the head camera is mounted a quarter turn off, like the real one), `mediad`
captures the rendered 640×360 UYVY at ~30 fps. First build of the daemons ≈ 5 min, `mediad`
with gstreamer another few.

Where things land (`DUCK_SIM_STATE`, default `~/.cache/duck-sim`):

| Path | What |
| --- | --- |
| `duck-a.sock` | robotd JSON-RPC (`duck.sock` links here) |
| `duck-a-tof.sock` | tofd `tof.stream` |
| `duck-a-frame.sock` | mediad `media.frame` (raw UYVY) |
| `http://127.0.0.1:8080` | mediad console, `GET /frame` → PNG |
| `duck-a.log`, `body.log` | robotd and MuJoCo logs |

Then, from the repo root:

```bash
cd runtime && uv run python -m duckstudio          # DUCKSTUDIO_BACKEND defaults to sim
DUCKSTUDIO_SIM=1 uv run pytest tests/backends -q   # contract tests against the real thing
```

Knobs passed through to upstream: `DUCK_SIM_VIEWER=1` (MuJoCo window, macOS via mjpython),
`DUCK_SIM_SCENE=apartment`, `DUCK_SIM_DUCKS=2`, `DUCK_SIM_KEYFRAME=STAND`.

The default scene (`sim/make-scene.py`) puts a magenta "person" 1.5 m ahead for the follow-me
detector.

Fall drill — knock the duck over mid-walk and check it gets up and carries on:

```bash
./sim/up.sh                                             # fresh duck, person ahead
cd runtime && uv run python -m duckstudio               # sim backend, :8000
python3 sim/fall-drill.py                               # exit 0 = passed
```

The push is `robot.pose` far outside its trained range, sent straight to robotd — a hand,
not the runtime. What it showed: `docs/upstream-notes.md`, "Falling over in duck-sim".
