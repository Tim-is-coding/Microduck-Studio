#!/usr/bin/env bash
# Forward a real duck's sockets to this machine, so the `duck` backend can speak to it
# (ADR-0006). The duck's daemons listen on Unix sockets and mediad's console on :8080;
# OpenSSH forwards both, and nothing on the duck changes.
#
#   scripts/duck-tunnel.sh duck.local            # ssh user is the current one
#   DUCK_USER=pollen scripts/duck-tunnel.sh 192.168.1.42
#
# Leave it running; Ctrl-C closes the tunnel and removes the local sockets.
set -euo pipefail

host="${1:-${DUCKSTUDIO_DUCK_HOST:-}}"
if [[ -z "$host" ]]; then
  echo "usage: $0 <duck-host>   (or set DUCKSTUDIO_DUCK_HOST)" >&2
  exit 2
fi

user="${DUCK_USER:-}"
target="${user:+$user@}$host"
dir="${DUCKSTUDIO_DUCK_TUNNEL:-$HOME/.cache/duckstudio/tunnel}"
console_port="${DUCKSTUDIO_DUCK_CONSOLE_PORT:-8080}"

# Remote paths, verified against microduck@344925c (docs/upstream-notes.md).
remote_robot="/run/robotd.sock"
remote_tof="/run/tofd/tof.sock"
remote_pad="/run/padd/pad.sock"

mkdir -p "$dir"
for name in robotd.sock tof.sock pad.sock; do
  rm -f "$dir/$name"   # a leftover socket file makes ssh refuse the forward
done

cleanup() {
  echo
  echo "closing the tunnel to $host"
  rm -f "$dir"/robotd.sock "$dir"/tof.sock "$dir"/pad.sock
}
trap cleanup EXIT INT TERM

echo "tunnelling $target → $dir (console on :$console_port)"
echo "  $dir/robotd.sock → $remote_robot"
echo "  $dir/tof.sock    → $remote_tof"
echo "  $dir/pad.sock    → $remote_pad"
echo
echo "then, in another terminal:"
echo "  DUCKSTUDIO_BACKEND=duck DUCKSTUDIO_DUCK_HOST=$host uv run python -m duckstudio"
echo

exec ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=5 \
  -o ServerAliveCountMax=3 \
  -L "$dir/robotd.sock:$remote_robot" \
  -L "$dir/tof.sock:$remote_tof" \
  -L "$dir/pad.sock:$remote_pad" \
  -L "127.0.0.1:$console_port:127.0.0.1:8080" \
  "$target"
