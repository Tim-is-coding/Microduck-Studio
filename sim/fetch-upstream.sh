#!/usr/bin/env sh
# Pinned checkout of pollen-robotics/microduck into sim/upstream/ (never vendored, never forked).
set -eu
UPSTREAM_REPO="${UPSTREAM_REPO:-https://github.com/pollen-robotics/microduck.git}"
UPSTREAM_REV="${UPSTREAM_REV:-344925c9f8fa031f85428a305b1e8ec2eaae29c1}"   # 0.14.1, see docs/upstream-notes.md
DEST="$(cd "$(dirname "$0")" && pwd)/upstream"

if [ -z "$UPSTREAM_REV" ]; then
  echo "UPSTREAM_REV is empty: record a verified commit in docs/upstream-notes.md first." >&2
  exit 1
fi
if [ ! -d "$DEST/.git" ]; then
  git clone --no-checkout "$UPSTREAM_REPO" "$DEST"
fi
git -C "$DEST" fetch --depth 1 origin "$UPSTREAM_REV"
git -C "$DEST" checkout --detach FETCH_HEAD
echo "upstream at $(git -C "$DEST" rev-parse --short HEAD) in $DEST"
