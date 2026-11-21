#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GIT="$ROOT/scripts/repo-git"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: scripts/publish-github.sh <git-remote-url> [branch]" >&2
  echo "Example: scripts/publish-github.sh git@github.com:USER/auto-branch.git main" >&2
  exit 2
fi

REMOTE_URL="$1"
BRANCH="${2:-main}"

"$GIT" rev-parse --is-inside-work-tree >/dev/null
if ! "$GIT" config user.name >/dev/null; then
  "$GIT" config user.name "Auto-Branch Contributors"
fi
if ! "$GIT" config user.email >/dev/null; then
  "$GIT" config user.email "auto-branch@users.noreply.github.com"
fi

if [[ -z "$($GIT remote 2>/dev/null || true)" ]]; then
  "$GIT" remote add origin "$REMOTE_URL"
else
  "$GIT" remote set-url origin "$REMOTE_URL"
fi

"$GIT" push -u origin "$BRANCH"
echo "Published branch '$BRANCH' to '$REMOTE_URL'."
