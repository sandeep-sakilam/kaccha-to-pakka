#!/usr/bin/env bash
# Tick the backlog item, run the quality gate, commit, preflight, push the branch.
# Usage: bash scripts/ship.sh F03 "commit message (multi-line ok)"
set -euo pipefail
fid="$1"; msg="$2"
python3 scripts/tick.py "$fid"
make fix >/dev/null 2>&1 || true
make check
git add -A
git commit -q -m "$msg"
bash scripts/preflight.sh
git push -q -u origin "$(git branch --show-current)" 2>&1 | grep -v '^remote:' || true
echo "shipped $(git branch --show-current)"
