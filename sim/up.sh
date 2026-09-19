#!/usr/bin/env sh
# Start upstream duck-sim with Duck Studio defaults. Everything is the upstream script; this only
# sets the environment it wants (docs/upstream-notes.md, "duck-sim"):
#   DUCK_SIM_RL       the microduck_rl checkout with its venv   (sim/upstream-rl)
#   DUCK_SIM_VIEWER   0 = headless (default here; 1 opens the MuJoCo window, macOS uses mjpython)
#   DUCK_SIM_CAMERAS  a = duck-a gets a camera + mediad console on :8080 (needs gstreamer off Linux)
#   DUCK_SIM_STATE    where sockets and logs land (default ~/.cache/duck-sim)
# Any arguments go to duck-sim: `sim/up.sh status`, `sim/up.sh ctl health`, `sim/up.sh down`.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
DUCK_SIM="$HERE/upstream/scripts/duck-sim"
[ -x "$DUCK_SIM" ] || { echo "no upstream checkout at $HERE/upstream — run sim/fetch-upstream.sh" >&2; exit 1; }
[ -x "$HERE/upstream-rl/.venv/bin/python" ] || { echo "no microduck_rl venv — run sim/fetch-upstream.sh" >&2; exit 1; }

export DUCK_SIM_RL="${DUCK_SIM_RL:-$HERE/upstream-rl}"
export DUCK_SIM_VIEWER="${DUCK_SIM_VIEWER:-0}"
export DUCK_SIM_CAMERAS="${DUCK_SIM_CAMERAS-a}"
export DUCK_SIM_STATE="${DUCK_SIM_STATE:-$HOME/.cache/duck-sim}"
exec "$DUCK_SIM" "$@"
