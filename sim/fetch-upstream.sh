#!/usr/bin/env sh
# Pinned checkouts of upstream (never vendored, never forked), revisions from docs/upstream-notes.md:
#   sim/upstream      pollen-robotics/microduck     (daemons, scripts/duck-sim)
#   sim/upstream-rl   pollen-robotics/microduck_rl  (duck-body = MuJoCo, libonnxruntime)
# Then `uv sync` in the RL checkout, which is what provides `duck-body`.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
MICRODUCK_REV="${MICRODUCK_REV:-344925c9f8fa031f85428a305b1e8ec2eaae29c1}"   # 0.14.1, API 31
RL_REV="${RL_REV:-cb70b792312d559a4da09064d92009079671815f}"                # develop 2026-09-14

pin() {  # pin <url> <rev> <dest>
  if [ ! -d "$3/.git" ]; then
    git clone --quiet --no-checkout "$1" "$3"
  fi
  git -C "$3" fetch --quiet --depth 1 origin "$2"
  git -C "$3" checkout --quiet --detach FETCH_HEAD
  echo "$(basename "$3") at $(git -C "$3" rev-parse --short HEAD)"
}

pin https://github.com/pollen-robotics/microduck.git    "$MICRODUCK_REV" "$HERE/upstream"
pin https://github.com/pollen-robotics/microduck_rl.git "$RL_REV"        "$HERE/upstream-rl"

command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/)" >&2; exit 1; }
(cd "$HERE/upstream-rl" && uv sync --quiet) && echo "microduck_rl venv ready (duck-body, onnxruntime)"
command -v cargo >/dev/null || echo "note: cargo not found — duck-sim needs a Rust toolchain (rust-version 1.89+)" >&2
