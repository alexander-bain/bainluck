#!/usr/bin/env bash
# #4456 — does this master push need a HEROKU release?
#
# Usage:  heroku-release-required.sh <BEFORE_SHA> <AFTER_SHA>
# Prints: "true" or "false" on stdout (plus reasoning on stderr).
#
# WHY: every master merge cycled the dynos, and a dyno cycle kills whatever the
# workers are mid-way through — the matcher, and the ~2h calibration rebuild that
# has been killed repeatedly at ~110/128 by a release landing under it. A
# frontend-only merge changes nothing Heroku serves, so it should cost the
# backend nothing.
#
# THIS SCRIPT FAILS TOWARD RELEASING. Every uncertain path prints "true".
# A missed release is a silent production/master skew nobody notices for hours;
# a redundant release costs one dyno cycle. Not symmetric — the tie goes to
# releasing.
#
# It lives in a file, not inline in ci.yml, so it can be executed by a guard
# test. An inline heredoc in a workflow is unreachable by every gate we own,
# which is how a deploy-path decision would rot unnoticed.

set -uo pipefail

BEFORE="${1:-}"
AFTER="${2:-}"

say () { echo "$*" >&2; }
emit () { echo "$1"; say "DECISION: $1 ($2)"; exit 0; }

# Paths that CANNOT change what the Heroku dynos serve.
# Anything NOT matched here — backend/, Procfile, requirements*.txt, runtime.txt,
# app.json, alembic, and .github/ itself — forces a release.
#
# THE SAFE LIST IS ABOUT DIRECTORIES, NOT EXTENSIONS. The first draft ended
# `|*.md)` and its own guard test caught it: that glob matches at ANY depth, so
# `backend/docs/notes.md` read as frontend-only. The bug is not that a markdown
# file is dangerous — it is that "safe because of how it is spelled" lets a path
# under a backend directory into the safe set, and the next extension added to
# that list may not be inert. Only a ROOT-level .md (no slash at all) is safe;
# markdown under backend/ releases like anything else under backend/.
is_frontend_only_path () {
  case "$1" in
    frontend/*|ios/*|docs/*|tools/*|.claude/*|alex-inbox/*) return 0 ;;
    */*) return 1 ;;          # any other nested path: not safe
    *.md) return 0 ;;         # root-level markdown only (README.md, CLAUDE.md)
    *) return 1 ;;
  esac
}

case "$BEFORE" in
  ""|0000000000000000000000000000000000000000)
    emit true "no usable base commit — cannot prove frontend-only" ;;
esac
[ -n "$AFTER" ] || emit true "no head commit given — cannot prove frontend-only"

git cat-file -e "${BEFORE}^{commit}" 2>/dev/null \
  || emit true "base commit ${BEFORE} not present — cannot prove frontend-only"
git cat-file -e "${AFTER}^{commit}" 2>/dev/null \
  || emit true "head commit ${AFTER} not present — cannot prove frontend-only"

CHANGED="$(git diff --name-only "$BEFORE" "$AFTER")" \
  || emit true "git diff failed — cannot prove frontend-only"

[ -n "$CHANGED" ] || emit true "empty diff — cannot prove frontend-only"

say "changed files:"
while IFS= read -r f; do
  [ -z "$f" ] && continue
  say "  $f"
  is_frontend_only_path "$f" || emit true "$f is not frontend-only"
done <<< "$CHANGED"

emit false "every changed path is frontend/app/docs-only"
