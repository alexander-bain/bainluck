#!/usr/bin/env bash
# why-was-it-killed.sh — LAT-P329 (#4950)
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
# USAGE:   bash tools/why-was-it-killed.sh
#          bash tools/why-was-it-killed.sh --window 300
#
# NEEDS:   `source ~/.claude/.env` for BAINLUCK_API + ADMIN_TOKEN (this script
#          does it itself), and the `heroku` CLI authenticated for the release
#          list. Read-only: one admin GET and one `heroku releases`.

set -uo pipefail

WINDOW=180
APP=bainluck
while [ $# -gt 0 ]; do
    case "$1" in
        --window) WINDOW="${2:-180}"; shift 2 ;;
        --app) APP="${2:-bainluck}"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1090
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
: "${BAINLUCK_API:?BAINLUCK_API is unset — source ~/.claude/.env}"
: "${ADMIN_TOKEN:?ADMIN_TOKEN is unset — source ~/.claude/.env}"

SNAP=$(mktemp -t lat329-ops)
RELS=$(mktemp -t lat329-rels)
trap 'rm -f "$SNAP" "$RELS"' EXIT

code=$(curl -s -o "$SNAP" -w '%{http_code}' \
    -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API/api/admin/ops-snapshot")
if [ "$code" != "200" ]; then
    echo "ops-snapshot returned HTTP $code — cannot read task summaries" >&2
    exit 1
fi

# `heroku releases` prints a table, not JSON, and its `created_at` is in the
# caller's LOCAL timezone with a UTC offset on the end. Parsed below rather than
# reformatted here, so the offset survives to the comparison.
if ! heroku releases -a "$APP" -n 40 >"$RELS" 2>/dev/null; then
    echo "could not read 'heroku releases -a $APP' — is the CLI authenticated?" >&2
    exit 1
fi

PYTHONPATH="$REPO_ROOT/backend" python3 - "$SNAP" "$RELS" "$WINDOW" <<'PY'
import json
import re
import sys
from datetime import datetime

from app.utils.task_verdict import attribute_teardown

snap_path, rel_path, window = sys.argv[1], sys.argv[2], int(sys.argv[3])

releases = []
# e.g. "  v4427   Deploy ef337836   alex@…   2026/09/11 01:47:28 -0700 (~ 53m ago)"
row = re.compile(r"^\s*(v\d+)\s+.*?(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})")
for line in open(rel_path, encoding="utf-8", errors="replace"):
    m = row.match(line)
    if not m:
        continue
    stamp = datetime.strptime(m.group(2), "%Y/%m/%d %H:%M:%S %z")
    releases.append({"version": m.group(1), "created_at": stamp})

if not releases:
    print("!! parsed 0 releases from the CLI output — the table format changed.")
    print("   Refusing to report 'cause is elsewhere' off an empty list: with no")
    print("   releases to compare against, every teardown would read as innocent.")
    sys.exit(1)

coverage = (json.load(open(snap_path)).get("coverage") or {})
interrupted = {
    name: (meta or {}).get("last_result_summary") or {}
    for name, meta in coverage.items()
    if isinstance((meta or {}).get("last_result_summary"), dict)
    and ((meta or {}).get("last_result_summary") or {}).get("terminal") == "interrupted"
}

print(f"{len(releases)} releases read · window {window}s · "
      f"{len(coverage)} tasks in coverage, {len(interrupted)} interrupted\n")

if not interrupted:
    print("No task's last run was interrupted. Nothing to attribute.")
    sys.exit(0)

for name, summary in sorted(interrupted.items()):
    verdict = attribute_teardown(summary, releases, window_s=window)
    killer = verdict.get("killed_by_release")
    print(f"── {name}")
    print(f"   running release   {summary.get('release_version')} "
          f"(live {summary.get('running_release_age_s', summary.get('release_age_s'))}s "
          f"at teardown — NOT the killer's age)")
    print(f"   interrupted at    {verdict.get('interrupted_at', '(unknown)')}")
    if killer:
        print(f"   KILLED BY         {killer}, created {verdict['killer_created_at']} "
              f"({verdict['lead_s']}s before the teardown)")
    else:
        print(f"   NOT A DEPLOY      {verdict['basis']}")
        print(f"                     {verdict.get('detail', '')}")
    print()
PY
