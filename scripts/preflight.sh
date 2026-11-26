#!/usr/bin/env bash
# Checks required before every push: identity and wording of commits on this branch.
set -euo pipefail
base="${1:-main}"
bad_id=$(git log --format='%an <%ae> | %cn <%ce>' "$base"..HEAD | grep -v '^Sandeep Sakilam <sakilamsandeep@gmail.com> | Sandeep Sakilam <sakilamsandeep@gmail.com>$' || true)
if [ -n "$bad_id" ]; then echo "Wrong commit identity:"; echo "$bad_id"; exit 1; fi
if git log --format='%B' "$base"..HEAD | grep -i claude; then echo "Forbidden word in commit messages"; exit 1; fi
echo "preflight ok"
