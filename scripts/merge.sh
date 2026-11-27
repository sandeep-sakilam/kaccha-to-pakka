#!/usr/bin/env bash
# Re-check the PR text, merge the feature branch locally with --no-ff, push main, delete the
# local branch. Usage: bash scripts/merge.sh <branch> "<title>"
set -euo pipefail
branch="$1"; title="$2"
repo="sandeep-sakilam/kaccha-to-pakka"
pr=$(gh api "repos/$repo/pulls?state=open&head=sandeep-sakilam:$branch" --jq '.[0].number')
if [ -z "$pr" ] || [ "$pr" = "null" ]; then echo "no open PR for $branch"; exit 1; fi
bash scripts/preflight.sh --pr "$pr"
git checkout main
git pull --ff-only origin main
git merge --no-ff "$branch" -m "Merge $branch: $title"
bash scripts/preflight.sh origin/main
git push origin main
git branch -d "$branch"
