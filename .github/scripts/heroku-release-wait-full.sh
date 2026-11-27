#!/usr/bin/env bash
# Ruling 394 — should a Heroku release wait for the full test suite?
#
# Usage:  heroku-release-wait-full.sh <BASE_SHA> <HEAD_SHA> [BASE_STATUS]
# Prints: "true" (wait for full run via deploy-after-full) or
#         "false" (release on merge via fast deploy; full run executes beside it).
#
# THIS SCRIPT FAILS CLOSED ("true") ON EVERY UNCERTAIN BRANCH:
# - Unresolved release base (`BASE_STATUS` != "resolved" when passed, or missing/null/invalid git SHAs)
# - `ci-change-scope.sh` fails, exits non-zero, or cannot classify the diff
# - Any database migration change (`alembic/`, `*alembic.ini`, `migrations/`)
# - Any change under `.github/` (workflows, actions, scripts, CI config) or `tools/release/`
# - Any dependency/runtime/packaging file or path outside the reviewed classified allowlist
#
# Passing `--no-renames` to git diff is load-bearing so moving a migration or
# `.github/` file cannot disguise the vanished path as safe.

set -uo pipefail

BASE="${1:-}"
HEAD_SHA="${2:-}"
BASE_STATUS="${3:-resolved}"

SCOPE_SCRIPT="${CI_CHANGE_SCOPE_SCRIPT:-$(dirname "$0")/ci-change-scope.sh}"

say () { echo "$*" >&2; }
emit () { echo "$1"; say "WAIT_FULL: $1 ($2)"; exit 0; }

case "$BASE_STATUS" in
  resolved) ;;
  *) emit true "release base status is '$BASE_STATUS' (unresolved) — failing closed to full run" ;;
esac

case "$BASE" in
  ""|0000000000000000000000000000000000000000)
    emit true "no usable base commit — cannot verify release safety without full run" ;;
esac
[ -n "$HEAD_SHA" ] || emit true "no head commit given — failing closed to full run"

git cat-file -e "${BASE}^{commit}" 2>/dev/null \
  || emit true "base commit ${BASE} not present — failing closed to full run"
git cat-file -e "${HEAD_SHA}^{commit}" 2>/dev/null \
  || emit true "head commit ${HEAD_SHA} not present — failing closed to full run"

if ! git merge-base --is-ancestor "$BASE" "$HEAD_SHA" 2>/dev/null; then
  emit true "base ${BASE} is not an ancestor of ${HEAD_SHA} — failing closed to full run"
fi

[ -r "$SCOPE_SCRIPT" ] || emit true "change-scope script ${SCOPE_SCRIPT} unreadable — failing closed to full run"

_scope_err="$(mktemp)"
cleanup_tmp () { rm -f "$_scope_err"; }
trap cleanup_tmp EXIT

SCOPE_OUT="$(bash "$SCOPE_SCRIPT" "$BASE" "$HEAD_SHA" 2>"$_scope_err")" || {
  say "$(cat "$_scope_err" 2>/dev/null || true)"
  emit true "ci-change-scope.sh exited non-zero — cannot classify candidate"
}
SCOPE_ERR="$(cat "$_scope_err" 2>/dev/null || true)"

case "$SCOPE_OUT" in
  full|frontend|native) ;;
  *)
    say "$SCOPE_ERR"
    emit true "ci-change-scope.sh returned unparseable scope '${SCOPE_OUT}' — failing closed"
    ;;
esac

# Verify ci-change-scope.sh actually classified files rather than falling back to
# "full" because of missing inputs, unreadable manifest, git diff failure, or empty diff.
DECISION_LINE="$(printf '%s\n' "$SCOPE_ERR" | grep '^DECISION:' | tail -1 || true)"
case "$DECISION_LINE" in
  *"is outside frontend/ and ios/"*|*"is under "*|*"is read by a backend test"*|*"every changed path is"*|*"mixed frontend/native candidate"*)
    ;;
  *)
    say "$SCOPE_ERR"
    emit true "ci-change-scope.sh fell back without classifying paths (${DECISION_LINE:-<missing decision>})"
    ;;
esac

CHANGED="$(git diff --name-only --no-renames "$BASE" "$HEAD_SHA")" \
  || emit true "git diff failed — failing closed to full run"
[ -n "$CHANGED" ] || emit true "empty diff — failing closed to full run"

is_wait_full_only_path () {
  case "$1" in
    .github/*) return 0 ;;
    tools/release/*) return 0 ;;
    backend/alembic/*|alembic/*|*/alembic/*) return 0 ;;
    backend/alembic.ini|alembic.ini|*/alembic.ini) return 0 ;;
    */migrations/*|migrations/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_classified_fast_release_path () {
  case "$1" in
    backend/app/*|backend/tests/*|backend/scripts/*|backend/data/*) return 0 ;;
    backend/pytest.ini|backend/conftest.py|backend/pyproject.toml) return 0 ;;
    backend/run_kalshi_ws.py|backend/run_pm_open_receiver.py) return 0 ;;
    # Non-Heroku companion dirs (can ride in widened deploy-base range beside server edits)
    frontend/*|ios/*|docs/*|.claude/*|alex-inbox/*) return 0 ;;
    # Non-release tooling scripts
    tools/*)
      case "$1" in
        tools/release/*) return 1 ;;
        *) return 0 ;;
      esac ;;
    # Unknown nested paths (e.g. requirements, Procfile, Dockerfile, configs, scripts/*) wait full
    */*) return 1 ;;
    *.md) return 0 ;;
    *) return 1 ;;
  esac
}

say "release wait-full changed files:"
while IFS= read -r f; do
  [ -z "$f" ] && continue
  say "  $f"
  if is_wait_full_only_path "$f"; then
    emit true "gated path '$f' must wait for full suite before releasing"
  fi
  if ! is_classified_fast_release_path "$f"; then
    emit true "path '$f' is outside classified fast-release scope — failing closed to full run"
  fi
done <<< "$CHANGED"

emit false "resolved base and classified non-migration/non-.github changes may release on merge"
