#!/usr/bin/env bash
# Merge a feature branch locally with --no-ff, push main, delete the local branch.
set -euo pipefail
branch="$1"; title="$2"
git checkout main
git pull --ff-only origin main
git merge --no-ff "$branch" -m "Merge $branch: $title"
bash scripts/preflight.sh origin/main
git push origin main
git branch -d "$branch"
