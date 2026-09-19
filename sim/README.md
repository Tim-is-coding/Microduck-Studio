# sim — duck-sim wrapper (M1)

Upstream `scripts/duck-sim` runs the real daemons (`robotd --sim`, `tofd --sim`, `configd`,
`updaterd`, optionally `mediad`) against a MuJoCo body served by `microduck_rl`. We never
vendor or fork upstream (`CLAUDE.md` §10); `fetch-upstream.sh` checks out the pinned revision
from `docs/upstream-notes.md` into `sim/upstream/` (git-ignored).

Verified facts that shape M1 (`docs/upstream-notes.md`, section "duck-sim"):

- Upstream ships **no docker-compose**; `boot` mode needs systemd-nspawn (Linux). On macOS
  the supported path is `scripts/duck-sim` (`up` mode) with `DUCK_SIM_VIEWER=0` for headless.
- Requirements: Rust toolchain, a `microduck_rl` checkout with `uv sync` (Python 3.12,
  `mjlab==1.3.0`, CPU is enough), optionally gstreamer for the camera.
- Sockets land under `~/.cache/duck-sim/` (`duck-a.sock`, `duck-a-tof.sock`,
  `duck-a-frame.sock`, ...); the `sim` backend dials them directly.

Plan for M1: `sim/up.sh` wrapping `scripts/duck-sim` with our env defaults, a scene with a
marked "person" object for the follow-me detector (M2), and an ADR replacing the
docker-compose wording in `CLAUDE.md` §8.

```bash
./sim/fetch-upstream.sh                 # pinned checkout into sim/upstream/
DUCK_SIM_VIEWER=0 sim/upstream/scripts/duck-sim   # M1: wrapped by sim/up.sh
```
