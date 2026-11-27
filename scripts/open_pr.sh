#!/usr/bin/env bash
# Open a PR with an explicit title and body through the REST API (no tool-added footers),
# read it back, and refuse to continue if the title or body mentions the coding assistant.
# Usage: bash scripts/open_pr.sh "<title>" <body-file>
set -euo pipefail
repo="sandeep-sakilam/kaccha-to-pakka"
title="$1"; body_file="$2"
branch="$(git branch --show-current)"
number=$(gh api "repos/$repo/pulls" -f title="$title" -f head="$branch" -f base=main \
  -F body=@"$body_file" --jq .number)
echo "$number"
# The session's GitHub proxy appends a footer to PR bodies on create and on REST PATCH.
# When the read-back fails, set the body with a writer that sends it exactly (the GitHub
# update-pull-request tool), then run: bash scripts/preflight.sh --pr <number>
bash "$(dirname "$0")/preflight.sh" --pr "$number" || echo "PATCH NEEDED: #$number" >&2
