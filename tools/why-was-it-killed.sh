#!/usr/bin/env bash
# why-was-it-killed.sh — LAT-P329 (#4950), population + two-app fix LAT-P389
#
# WHAT: for every task whose last run reads `terminal: interrupted`, name the
# Heroku release that tore it down — or say plainly that nothing was deployed in
# the window, so the cause is elsewhere (dyno cycle, memory quota, manual
# restart).
#
# WHY THIS EXISTS. The summary a dying worker writes cannot answer the question
# on its own. `HEROKU_RELEASE_VERSION` is baked into a dyno at boot, so a worker
# being torn down names the release it is RUNNING — during a deploy, by
# construction the one being REPLACED. The killer is the NEW release, and the
# dying process has never heard of it. The old note in `task_verdict.py` told
# readers to judge by the age of the running release, which is large in every
# ordinary deploy kill; it exonerated a deploy in exactly the case where a deploy
# was the cause. Both halves are here in one command instead of two tools and a
# subtraction that reads backwards.
#
# WHAT CHANGED (LAT-P389, measured on production 2026-09-14 04:1xZ). This script
# used to read its task population from `/api/admin/ops-snapshot`'s `coverage`
# block — TWO tasks, out of a fleet of 120 — and one app's release list. At
# 04:12Z it therefore printed "2 tasks in coverage, 0 interrupted / Nothing to
# attribute" and exited 0 while `futures_price_refresh` (torn down 03:51:03Z by
# bainluck-heavy v18, 17s lead) and `polymarket_winners` (torn down 23:47:35Z by
# bainluck v4508, 16s lead) both sat on production reading `interrupted`. It now
# reads `/api/admin/celery/dashboard` (every task) and BOTH apps' release lists,
# because since the heavy split each task's killer lives in only one of them and
# a single list exonerates the other app's teardowns by construction.
#
# USAGE:   bash tools/why-was-it-killed.sh
#          bash tools/why-was-it-killed.sh --window 300
#          bash tools/why-was-it-killed.sh --app bainluck-heavy   # restrict
#          bash tools/why-was-it-killed.sh --self-check           # no network
#
# NEEDS:   `source ~/.claude/.env` for BAINLUCK_API + ADMIN_TOKEN (this script
#          does it itself), and the `heroku` CLI authenticated for the release
#          lists. Read-only: one admin GET and one `heroku releases` per app.

set -uo pipefail

WINDOW=180
APPS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --window) WINDOW="${2:-180}"; shift 2 ;;
        --app) APPS+=("${2:-bainluck}"); shift 2 ;;
        --self-check)
            exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/teardown_attribution.py" --self-check ;;
        -h|--help) sed -n '2,38p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# Default is BOTH apps, not one. A default of `bainluck` is what made a
# heavy-worker teardown read as "cause is elsewhere".
if [ ${#APPS[@]} -eq 0 ]; then
    APPS=(bainluck bainluck-heavy)
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1090
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
: "${BAINLUCK_API:?BAINLUCK_API is unset — source ~/.claude/.env}"
: "${ADMIN_TOKEN:?ADMIN_TOKEN is unset — source ~/.claude/.env}"

TASKS=$(mktemp -t lat389-tasks)
TMPDIR_RELS=$(mktemp -d -t lat389-rels)
trap 'rm -rf "$TASKS" "$TMPDIR_RELS"' EXIT

# The task population. `celery/dashboard` serves every tracked task with its
# `last_result_summary`; `ops-snapshot`'s `coverage` block serves two of them.
code=$(curl -s -o "$TASKS" -w '%{http_code}' \
    -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API/api/admin/celery/dashboard")
if [ "$code" != "200" ]; then
    echo "celery/dashboard returned HTTP $code — cannot read task summaries" >&2
    exit 1
fi

# `heroku releases` prints a table, not JSON, and its `created_at` is in the
# caller's LOCAL timezone with a UTC offset on the end. Parsed in the module
# rather than reformatted here, so the offset survives to the comparison.
SPECS=()
for app in "${APPS[@]}"; do
    out="$TMPDIR_RELS/$app.txt"
    if ! heroku releases -a "$app" -n 40 >"$out" 2>/dev/null; then
        echo "could not read 'heroku releases -a $app' — is the CLI authenticated?" >&2
        exit 1
    fi
    SPECS+=("$app=$out")
done

PYTHONPATH="$REPO_ROOT/backend" python3 \
    "$REPO_ROOT/tools/teardown_attribution.py" "$TASKS" "$WINDOW" "${SPECS[@]}"
