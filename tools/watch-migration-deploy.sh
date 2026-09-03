#!/bin/bash
# watch-migration-deploy.sh — the ONLY thing allowed to re-measure #2724.
#
# WHY. #2724 (the blank page is a migration-lock convoy) was fixed by arming `lock_timeout` on the
# MIGRATION's connection. LAT-P216 measured 40/40 clean cold loads after the 790 release and had to
# throw the result away: that release carried no Alembic migration, so it never touched the code path
# the fix arms. A clean run over an unexercised path is a negative control, not a pass.
#
# So the verdict on #2724 belongs to THE FIRST DEPLOY THAT CARRIES A MIGRATION, whenever that is, and
# nobody knows when that will be. A session cannot wait for it; a background job dies with its session
# (standing notice 17). This script is `setsid nohup`'d so it outlives every session, and it reports by
# WRITING A RUNNER-INBOX DIRECTIVE rather than by trying to wake anyone.
#
# WHAT IT DOES
#   every POLL_S seconds: GET /api/health -> {"commit": "<sha>"}
#   commit changed  -> fetch origin, diff the two shas over backend/alembic/versions/
#     no new migration file -> log it as a negative control, keep watching (this is the common case)
#     new migration file    -> THE deploy: read the ring, run 40 cold loads, read the ring again,
#                              write runner-inbox/latency/129-2724-<sha>.md, and EXIT (job done)
#
# POLL CADENCE. The directive said five minutes; this polls every 60 s on purpose. A Heroku release
# window is ~2-3 minutes, and the convoy #2724 describes is inside it — a five-minute poll can put the
# whole event between two samples. The ring would still hold the convoy, but the blank-load count (the
# reader-facing half, and the only half a shopper feels) would be measured after the window closed. One
# trivial GET per minute is a cheap way not to miss the thing being watched. Detection is on COMMIT
# CHANGE only, never on a health error or an uptime reset, so a routine dyno cycle cannot fire a burst.
#
# Usage:  setsid nohup bash tools/watch-migration-deploy.sh >/tmp/lat-2724-watch/stdout.log 2>&1 &

REPO="${REPO:-/Users/bain/bainluck-dev/latency}"
INBOX="${INBOX:-/Users/bain/bainluck/.claude/handoff/runner-inbox/latency}"
WORK="${WORK:-/tmp/lat-2724-watch}"
POLL_S="${POLL_S:-60}"
MAX_DAYS="${MAX_DAYS:-7}"
API="${API:-https://api.bainluck.com}"
NODE="${NODE:-/opt/homebrew/bin/node}"

mkdir -p "$WORK"
# Single-instance guard. mkdir is the atomic primitive here: macOS has no flock (memory:
# r_flock_absent_macos_use_mkdir), and two watchers would double every burst and race the report file.
if ! mkdir "$WORK/lock" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) another watcher holds $WORK/lock — exiting"; exit 3
fi
trap 'rmdir "$WORK/lock" 2>/dev/null' EXIT

LOG="$WORK/watch.log"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

# ADMIN_TOKEN / BAINLUCK_API live only in the untracked env file (credential standing rule).
# shellcheck disable=SC1090
source "$HOME/.claude/.env" 2>/dev/null

health_commit() { curl -s --max-time 20 "$API/api/health" | "$NODE" -e \
  'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(String(JSON.parse(s).commit||""))}catch(e){}})'; }

ring() { curl -s --max-time 45 -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/api/admin/latency-slow-events?limit=500" ; }

START_EPOCH=$(date +%s)
LAST=$(health_commit)
say "armed. poll=${POLL_S}s api=$API baseline_commit=${LAST:-UNREADABLE} inbox=$INBOX"

while true; do
  sleep "$POLL_S"
  NOW_EPOCH=$(date +%s)
  if [ $(( (NOW_EPOCH - START_EPOCH) / 86400 )) -ge "$MAX_DAYS" ]; then
    say "max lifetime ${MAX_DAYS}d reached with no migration-carrying deploy — exiting"
    printf '# latency/129 — the #2724 watcher expired unfired\n\nArmed %s, exited %s after %s days with NO migration-carrying deploy.\n#2724 is still unmeasured against an exercised code path. Re-arm `tools/watch-migration-deploy.sh` or force the condition with a no-op migration.\n' \
      "$(date -u -r "$START_EPOCH" +%FT%TZ)" "$(date -u +%FT%TZ)" "$MAX_DAYS" > "$INBOX/129-2724-EXPIRED.md"
    exit 0
  fi

  CUR=$(health_commit)
  [ -z "$CUR" ] && { say "health unreadable (release window or egress) — will retry"; continue; }

  # THE SECOND SHAPE, added after the first real event walked straight past the first one.
  #
  # This watcher was built to fire when the deployed COMMIT CHANGES. On the night it was armed, the
  # migration-carrying deploy arrived and the commit never changed: four consecutive Heroku releases
  # (v4016-v4019) failed at the release command because `ALTER TABLE futures_markets` could not take
  # ACCESS EXCLUSIVE behind a two-hour `idle in transaction` platform session. Production sat on the
  # old sha, `/api/health` never moved, and a commit-change watcher is blind to the whole event —
  # while CI's own `deploy` job reported success on both shas.
  #
  # So a stuck deploy is also a #2724 verdict condition, and it is reported ONCE without exiting: the
  # eventual successful release is still the verdict this watcher is waiting for.
  if [ "$CUR" = "$LAST" ]; then
    [ -n "$STUCK_REPORTED" ] && continue
    git -C "$REPO" fetch origin --quiet 2>>"$LOG"
    HEAD_SHA=$(git -C "$REPO" rev-parse --short=8 origin/master 2>>"$LOG")
    if [ -z "$HEAD_SHA" ] || [ "$HEAD_SHA" = "$CUR" ]; then continue; fi
    PENDING_MIGS=$(git -C "$REPO" diff --name-only "$CUR" "$HEAD_SHA" -- backend/alembic/versions/ 2>>"$LOG")
    if [ -z "$PENDING_MIGS" ]; then continue; fi
    # Master carries a migration production has not taken. Give it a grace window — a normal release
    # takes minutes, and calling that "stuck" would fire on every healthy deploy.
    if [ -z "$STUCK_SINCE" ]; then STUCK_SINCE=$NOW_EPOCH; say "  master $HEAD_SHA is ahead with a migration; starting stuck-deploy grace window"; continue; fi
    if [ $(( NOW_EPOCH - STUCK_SINCE )) -lt "${STUCK_GRACE_S:-900}" ]; then continue; fi

    say "  🔴 STUCK MIGRATION DEPLOY: prod $CUR, master $HEAD_SHA, pending: $PENDING_MIGS"
    ring > "$WORK/ring-stuck-$CUR.json" 2>/dev/null
    heroku releases -n 8 -a bainluck > "$WORK/releases-stuck-$CUR.txt" 2>&1
    OUT="$WORK/burst-stuck-$CUR"; mkdir -p "$OUT"
    for s in discover sports usopen event; do
      ( cd "$REPO" && FELT_MODE=cold "$NODE" tools/felt-load.mjs "$s" 10 "$OUT/cold-$s.json" \
          > /dev/null 2>>"$OUT/log.txt" )
      say "  stuck-burst $s exit=$?"
    done
    REPORT="$INBOX/129-2724-stuck-$CUR.md"
    MIGS="$PENDING_MIGS" CUR="$CUR" LAST="$HEAD_SHA" OUT="$OUT" WORK="$WORK" \
      REPORT_STUCK=1 RING_PATH="$WORK/ring-stuck-$CUR.json" REPORT_PATH="$REPORT" \
      "$NODE" "$REPO/tools/watch-2724-report.mjs" >>"$LOG" 2>&1
    [ -s "$REPORT" ] || printf '# latency/129 — stuck migration deploy at %s (report failed to render)\n\nPending: %s\nRaw: %s\n' "$CUR" "$PENDING_MIGS" "$OUT" > "$REPORT"
    say "  wrote $REPORT — still watching for the release that lands"
    STUCK_REPORTED=1
    continue
  fi
  STUCK_SINCE=""

  say "COMMIT CHANGED $LAST -> $CUR"
  # Ring FIRST: the convoy is already over by the time a poll notices, and the ring is where it lives.
  ring > "$WORK/ring-at-$CUR.json" 2>/dev/null

  git -C "$REPO" fetch origin --quiet 2>>"$LOG"
  MIGS=$(git -C "$REPO" diff --name-only "$LAST" "$CUR" -- backend/alembic/versions/ 2>>"$LOG")
  if [ -z "$MIGS" ]; then
    # Was the diff empty because there is no migration, or because a sha is unknown to us?
    if ! git -C "$REPO" cat-file -e "${CUR}^{commit}" 2>/dev/null; then
      say "  sha $CUR not on origin after fetch — recording UNKNOWN, will re-check on next change"
      LAST="$CUR"; continue
    fi
    say "  no migration in $LAST..$CUR — negative control, still watching"
    echo "$(date -u +%FT%TZ) $LAST..$CUR NO-MIGRATION" >> "$WORK/negative-controls.log"
    LAST="$CUR"; continue
  fi

  say "  🔴 MIGRATION-CARRYING DEPLOY: $MIGS — bursting 40 cold loads"
  OUT="$WORK/burst-$CUR"; mkdir -p "$OUT"
  for s in discover sports usopen event; do
    ( cd "$REPO" && FELT_MODE=cold "$NODE" tools/felt-load.mjs "$s" 10 "$OUT/cold-$s.json" \
        > /dev/null 2>>"$OUT/log.txt" )
    say "  burst $s exit=$?"
  done
  ring > "$WORK/ring-after-$CUR.json" 2>/dev/null

  REPORT="$INBOX/129-2724-$CUR.md"
  MIGS="$MIGS" CUR="$CUR" LAST="$LAST" OUT="$OUT" WORK="$WORK" REPORT_PATH="$REPORT" \
    "$NODE" "$REPO/tools/watch-2724-report.mjs" >>"$LOG" 2>&1
  # Fallback: a report that failed to render must still leave a trace in the inbox.
  [ -s "$REPORT" ] || printf '# latency/129 — #2724 deploy %s fired but the report failed to render\n\nMigrations: %s\nRaw: %s\n' "$CUR" "$MIGS" "$OUT" > "$REPORT"
  say "  wrote $REPORT — job done, exiting"
  exit 0
done
