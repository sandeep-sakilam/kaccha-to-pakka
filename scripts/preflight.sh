#!/usr/bin/env bash
# Checks required before every push and merge.
#   bash scripts/preflight.sh [base]      commit identity and wording on this branch
#   bash scripts/preflight.sh --pr N      PR title and body read back from GitHub
set -euo pipefail
repo="sandeep-sakilam/kaccha-to-pakka"
if [ "${1:-}" = "--pr" ]; then
  text=$(gh api "repos/$repo/pulls/$2" --jq '.title + "\n" + (.body // "")')
  if printf '%s' "$text" | grep -qi claude; then
    echo "PR #$2 mentions a forbidden word in its title or body"; exit 1
  fi
  echo "pr #$2 text ok"
  exit 0
fi
base="${1:-main}"
bad_id=$(git log --format='%an <%ae> | %cn <%ce>' "$base"..HEAD | grep -v '^Sandeep Sakilam <sakilamsandeep@gmail.com> | Sandeep Sakilam <sakilamsandeep@gmail.com>$' || true)
if [ -n "$bad_id" ]; then echo "Wrong commit identity:"; echo "$bad_id"; exit 1; fi
if git log --format='%B' "$base"..HEAD | grep -i claude; then echo "Forbidden word in commit messages"; exit 1; fi
echo "preflight ok"
