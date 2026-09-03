#!/bin/bash
# watch-release-window.sh — the ONLY thing allowed to re-measure #2724.
#
# ── WHY IT WAS REWRITTEN (LAT-P218) ────────────────────────────────────────────────────────────────
# Its predecessor, `watch-migration-deploy.sh`, fired on "the sha at /api/health changed". On the one
# night a real migration-carrying deploy arrived, that trigger saw nothing: four consecutive Heroku
# releases (v4016-v4019) FAILED at the release command because `ALTER TABLE futures_markets` could not
# take ACCESS EXCLUSIVE behind a two-hour `idle in transaction` session. Production sat on the old sha
# the whole time. `/api/health` never moved, so the watcher's only trigger never fired, and the deploys
# that hurt readers most — the ones that never land — were the exact deploys it could not see. A
# bolted-on second trigger caught the *stuck* state fifteen minutes late, after the convoy was over.
#
# A commit-change watcher can only ever sample the release that succeeded. Succeeding is correlated
# with the table being free, which is correlated with there being no convoy. So the old instrument was
# selecting for the quiet case: it could confirm health and could never observe the failure.
#
# ── WHAT THIS ONE DOES ─────────────────────────────────────────────────────────────────────────────
# It fires on RELEASE START. Heroku creates a release object the moment a deploy begins, with
# `status: pending`, and flips it to `succeeded` or `failed` when the release phase terminates. A new
# `version` number IS the start of the window, whatever happens afterwards.
#
#   poll `heroku releases -n 1 --json` every POLL_S seconds
#   version increased  -> WINDOW OPEN
#       ring BEFORE  ·  start a cheap HTTP prober  ·  start paced cold browser loads
#       keep sampling until status leaves `pending`, then TAIL_S more (the convoy releases when the
#       lock frees, which is after the release object flips)
#       ring AFTER  ·  release log  ·  BANK THE RUN — succeeded or failed, migration or not
#
# **Every window is banked.** A failed release is not a missing measurement, it is the measurement.
#
# ── THE REQUEST BUDGET IS PART OF THE INSTRUMENT ───────────────────────────────────────────────────
# Production caps a client at 60 requests/minute and one `/events/{id}` cold load fires ~22 of them.
# An unpaced burst measures its own 429s and renders `Rate limit exceeded` — 673 body chars, which is
# indistinguishable from a blank page in every column the felt rig used to have (that is how #2783 was
# filed). So the sampling budget is spent deliberately:
#
#   prober        1 request  / PROBE_S (6 s default)   =  10 /min
#   browser load ~22 requests / LOAD_S (45 s default)  = ~29 /min
#                                                        ~39 /min, against a 60 cap
#
# `felt-load.mjs` now reports `api429` per run and `throttledRuns` per summary, so if this budget is
# ever wrong the report says so instead of banking the throttling as a regression.
#
# ── WHY BOTH A PROBER AND A BROWSER ────────────────────────────────────────────────────────────────
# They answer different questions and neither substitutes for the other. #2724 has two halves: the
# pipeline half (requests parked behind a lock, seconds to minutes, invisible to a reader who has
# already given up) and the reader half (a blank page). The prober samples every 6 s and is what can
# actually resolve a 25-second release window; the browser is the only thing that can say what a
# reader saw. A window with a clean prober and a blank browser load means something other than the
# convoy, and that distinction is the whole point of measuring at all.
#
# Usage:
#   python3 tools/detach-run.py /tmp/lat-2724-watch/stdout.log bash tools/watch-release-window.sh
#   (macOS has no `setsid`, so standing notice 17's line cannot be typed literally; detach-run.py is
#   the repo's double-fork stand-in and prints the detached pid.)
#
# Self-test before arming (renders a report from banked data, fires nothing):
#   WATCH_SELFTEST=1 bash tools/watch-release-window.sh

set -o pipefail

REPO="${REPO:-/Users/bain/bainluck-dev/latency}"
# 🔴 TOOLS IS SEPARATE FROM REPO ON PURPOSE. This script runs for days while its own worktree is
# rebased, merged and checked out under it — and bash reads a script INCREMENTALLY, so editing the file
# a live shell is executing corrupts that shell mid-run. So the watcher is launched from a SNAPSHOT of
# `tools/` (rsync it somewhere stable and point TOOLS at that copy's parent), while REPO stays the real
# worktree because the migration diff needs a git dir. Leaving TOOLS defaulted to REPO is fine for a
# short attended run and wrong for an armed one.
TOOLS="${TOOLS:-$REPO}"
INBOX="${INBOX:-/Users/bain/bainluck/.claude/handoff/runner-inbox/latency}"
WORK="${WORK:-/tmp/lat-2724-watch}"
APP="${APP:-bainluck}"
API="${API:-https://api.bainluck.com}"
NODE="${NODE:-/opt/homebrew/bin/node}"
QUEUE="${QUEUE:-130}"            # the directive number this watcher reports under

POLL_S="${POLL_S:-5}"            # release-status poll. A healthy no-migration window is ~25 s.
PROBE_S="${PROBE_S:-6}"          # cheap HTTP probe cadence
LOAD_S="${LOAD_S:-45}"           # browser cold-load cadence (~22 requests each)
TAIL_S="${TAIL_S:-120}"          # keep sampling after the release object goes terminal
MAX_WINDOW_S="${MAX_WINDOW_S:-2700}"   # a wedged release must not sample forever
MAX_DAYS="${MAX_DAYS:-7}"
PROBE_PATH_URL="${PROBE_PATH_URL:-/api/health}"

mkdir -p "$WORK"
# Single-instance guard. mkdir is the atomic primitive here: macOS has no flock (memory:
# r_flock_absent_macos_use_mkdir), and two watchers would double every burst — which on a 60/min cap
# does not just duplicate the data, it invalidates it.
if ! mkdir "$WORK/lock" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) another watcher holds $WORK/lock — exiting"; exit 3
fi
trap 'rmdir "$WORK/lock" 2>/dev/null' EXIT

LOG="$WORK/watch.log"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

# ADMIN_TOKEN / BAINLUCK_API live only in the untracked env file (credential standing rule).
# shellcheck disable=SC1090
source "$HOME/.claude/.env" 2>/dev/null

ring() { curl -s --max-time 45 -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/api/admin/latency-slow-events?limit=500" ; }

# One line of JSON for the newest release. The CLI rather than the Platform API on purpose: it costs
# ~0.4 s, and it keeps this script from ever holding a Heroku token in a variable.
latest_release() {
  heroku releases -n 1 -a "$APP" --json 2>>"$LOG" | "$NODE" -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      try{const r=JSON.parse(s)[0];
        const m=/Deploy\s+([0-9a-f]{7,40})/.exec(r.description||"");
        process.stdout.write([r.version,r.status,m?m[1]:"",r.created_at].join("\t"));
      }catch(e){}});'
}

# ── THE PROBER ─────────────────────────────────────────────────────────────────────────────────────
# One request per PROBE_S, writing TSV: epoch, http_code, total_seconds. `%{http_code}` is 000 when the
# connection never completed, which is a distinct and important outcome from a slow 200 — during last
# night's convoy the reader-facing symptom was requests that never returned, not requests that were
# slow. curl's own timeout is deliberately longer than the probe cadence so a parked request is
# recorded as parked rather than as a gap in the file.
prober() {
  local out="$1"
  while :; do
    curl -s -o /dev/null --max-time 60 \
      -w "$(date +%s)\t%{http_code}\t%{time_total}\n" "$API$PROBE_PATH_URL" >> "$out" 2>/dev/null \
      || echo -e "$(date +%s)\t000\tcurl-failed" >> "$out"
    sleep "$PROBE_S"
  done
}

# ── THE BROWSER LOOP ───────────────────────────────────────────────────────────────────────────────
# Rotates the four surfaces so a window of any length gets a spread rather than 30 samples of one page,
# and paces itself to the budget above. Each run is its own JSON file; the reporter merges them, so a
# window that is cut short still banks everything that completed.
browser_loop() {
  local out="$1" i=0
  local surfaces=(event discover sports usopen)
  while :; do
    local s="${surfaces[$(( i % 4 ))]}"
    ( cd "$TOOLS" && FELT_MODE=cold FELT_PACE_MS=0 "$NODE" tools/felt-load.mjs "$s" 1 \
        "$out/load-$(printf '%03d' "$i")-$s.json" >/dev/null 2>>"$out/loads.log" )
    i=$(( i + 1 ))
    sleep "$LOAD_S"
  done
}

# ── ONE WINDOW ─────────────────────────────────────────────────────────────────────────────────────
sample_window() {
  local ver="$1" sha="$2" prev_sha="$3" created="$4"
  local tag="v${ver}-${sha}"
  local out="$WORK/window-$tag"
  mkdir -p "$out"
  local t0; t0=$(date +%s)

  say "🟢 WINDOW OPEN v$ver ($sha), prev $prev_sha — sampling"

  # The ring BEFORE anything else: the convoy is what we are here for and it starts with the release,
  # not with our first browser load.
  ring > "$out/ring-before.json" 2>/dev/null

  prober "$out/probe.tsv" & local pp=$!
  browser_loop "$out" & local bp=$!
  # Kill the samplers on ANY exit path, including a SIGTERM to the watcher. Two orphaned loops on a
  # 60/min budget would poison every later window, not just this one.
  trap 'kill '"$pp"' '"$bp"' 2>/dev/null' RETURN

  local status="pending" terminal_at="" now
  while :; do
    sleep "$POLL_S"
    now=$(date +%s)
    local line; line=$(latest_release)
    local s; s=$(echo "$line" | cut -f2)
    local v; v=$(echo "$line" | cut -f1)
    # A NEWER release started while we were sampling this one — CI serialises deploys, but a failed
    # release is often retried within the minute. Close this window so the next one gets its own file
    # rather than silently folding two deploys into one reading.
    if [ -n "$v" ] && [ "$v" != "$ver" ]; then
      say "  v$v started while sampling v$ver — closing this window early"
      status="superseded"; terminal_at=$now; break
    fi
    [ -n "$s" ] && status="$s"
    if [ "$status" != "pending" ] && [ -z "$terminal_at" ]; then
      terminal_at=$now
      say "  v$ver -> $status after $(( now - t0 ))s; sampling ${TAIL_S}s of tail"
    fi
    [ -n "$terminal_at" ] && [ $(( now - terminal_at )) -ge "$TAIL_S" ] && break
    if [ $(( now - t0 )) -ge "$MAX_WINDOW_S" ]; then
      say "  🔴 v$ver still $status after ${MAX_WINDOW_S}s — banking what we have and moving on"
      break
    fi
  done

  kill "$pp" "$bp" 2>/dev/null
  wait "$pp" "$bp" 2>/dev/null
  ring > "$out/ring-after.json" 2>/dev/null
  heroku releases -n 8 -a "$APP" > "$out/releases.txt" 2>&1
  # The release log is the only place the release phase speaks, and the Procfile's
  # `alembic upgrade heads || echo` can swallow a failure (#2741) — a migration that silently did not
  # apply produces the same clean loads as one that applied safely.
  #
  # 🔴 `heroku releases:output` returns `Code: EPERM` in this sandbox (the CLI's own log fetch is
  # blocked, same as `heroku logs`). The release JSON carries a pre-signed `output_stream_url` on
  # release-output.heroku.com which plain curl CAN reach — measured 200. Silence here would read as a
  # clean release, so the fallback records WHY it is empty rather than leaving an empty file.
  local ourl
  ourl=$(heroku releases -n 8 -a "$APP" --json 2>/dev/null | "$NODE" -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      try{const r=JSON.parse(s).find(x=>String(x.version)===process.argv[1]);
        process.stdout.write((r&&r.output_stream_url)||"");}catch(e){}});' "$ver")
  if [ -n "$ourl" ]; then
    curl -s --max-time 60 "$ourl" > "$out/release-output.txt" 2>/dev/null
  fi
  [ -s "$out/release-output.txt" ] || \
    echo "NO RELEASE OUTPUT BANKED — output_stream_url ${ourl:+unreachable}${ourl:-absent from the release JSON}. Read it by hand: heroku releases:output $ver -a $APP" \
      > "$out/release-output.txt"

  # WHAT THE RELEASE CARRIED. Computed from the two release DESCRIPTIONS, not from /api/health — the
  # whole reason this rewrite exists is that health does not move when the release fails.
  # `backend/alembic/` and not `backend/alembic/versions/`: CERT-807 changes `env.py`, and a filter
  # that only looks at versions/ would classify a migration-behaviour change as "no migration".
  git -C "$REPO" fetch origin --quiet 2>>"$LOG"
  local migs=""
  if [ -n "$prev_sha" ] && git -C "$REPO" cat-file -e "${sha}^{commit}" 2>/dev/null \
                        && git -C "$REPO" cat-file -e "${prev_sha}^{commit}" 2>/dev/null; then
    migs=$(git -C "$REPO" diff --name-only "$prev_sha" "$sha" -- backend/alembic/ 2>>"$LOG")
  else
    migs="UNKNOWN — one of $prev_sha..$sha is not on origin after fetch"
  fi

  local elapsed=$(( $(date +%s) - t0 ))
  local report="$INBOX/${QUEUE}-2724-v${ver}-${status}.md"
  MIGS="$migs" CUR="$sha" LAST="$prev_sha" OUT="$out" WORK="$WORK" \
    RING_BEFORE="$out/ring-before.json" RING_PATH="$out/ring-after.json" \
    PROBE_PATH="$out/probe.tsv" RELEASE_VERSION="$ver" RELEASE_STATUS="$status" \
    RELEASE_CREATED="$created" WINDOW_S="$elapsed" QUEUE="$QUEUE" \
    RELEASE_OUTPUT="$out/release-output.txt" REPORT_PATH="$report" \
    "$NODE" "$TOOLS/tools/watch-2724-report.mjs" >>"$LOG" 2>&1
  # A report that failed to render must still leave a trace in the inbox — the raw data is banked
  # either way and the directive must say where it is.
  [ -s "$report" ] || printf '# latency/%s — release v%s (%s) sampled, report failed to render\n\nsha: %s\nmigrations: %s\nraw: %s\n' \
    "$QUEUE" "$ver" "$status" "$sha" "$migs" "$out" > "$report"
  say "  banked $report  (window ${elapsed}s, status=$status, migrations=$([ -n "$migs" ] && echo yes || echo no))"

  # Exit only on the condition this watcher was armed for: a migration that actually LANDED. A failed
  # migration release is banked and then waited past, because the retry is still the verdict #2724 is
  # waiting for.
  if [ -n "$migs" ] && [ "$status" = "succeeded" ]; then
    say "  migration-carrying release SUCCEEDED and is banked — job done, exiting"
    return 10
  fi
  return 0
}

# ── SELF-TEST ──────────────────────────────────────────────────────────────────────────────────────
# Renders a report from whatever is already banked, fires nothing, touches no inbox. A reporting step
# that has only ever run inside an unattended watcher, on a condition that happens once, is a step
# nobody has tested.
if [ -n "$WATCH_SELFTEST" ]; then
  ST_OUT="${SELFTEST_OUT:-$(ls -dt "$WORK"/window-* "$WORK"/burst-* 2>/dev/null | head -1)}"
  [ -z "$ST_OUT" ] && { echo "selftest: nothing banked under $WORK to render from"; exit 2; }
  ST_REPORT="${SELFTEST_REPORT:-$WORK/selftest-report.md}"
  echo "selftest: rendering $ST_OUT -> $ST_REPORT"
  MIGS="${SELFTEST_MIGS:-backend/alembic/versions/selftest_fixture.py}" CUR=selftest LAST=selftest0 \
    OUT="$ST_OUT" WORK="$WORK" RING_BEFORE="$ST_OUT/ring-before.json" \
    RING_PATH="$ST_OUT/ring-after.json" PROBE_PATH="$ST_OUT/probe.tsv" \
    RELEASE_VERSION=0000 RELEASE_STATUS="${SELFTEST_STATUS:-succeeded}" RELEASE_CREATED="selftest" \
    WINDOW_S=0 QUEUE="$QUEUE" RELEASE_OUTPUT="$ST_OUT/release-output.txt" REPORT_PATH="$ST_REPORT" \
    "$NODE" "$TOOLS/tools/watch-2724-report.mjs" || exit 1
  echo "selftest: ok"; exit 0
fi

# ── ARM ────────────────────────────────────────────────────────────────────────────────────────────
START_EPOCH=$(date +%s)
LINE=$(latest_release)
LAST_VER=$(echo "$LINE" | cut -f1)
LAST_SHA=$(echo "$LINE" | cut -f3)
if [ -z "$LAST_VER" ]; then
  say "🔴 cannot read $APP releases — refusing to arm blind"; exit 2
fi
say "armed. app=$APP poll=${POLL_S}s probe=${PROBE_S}s load=${LOAD_S}s tail=${TAIL_S}s"
say "  baseline release v$LAST_VER ($LAST_SHA). inbox=$INBOX work=$WORK"

# DRY RUN. The hard part of this instrument is that its live path executes on a condition nobody can
# schedule, so it would otherwise be armed having never run. FORCE_FIRST_WINDOW backdates the baseline
# by one so the CURRENT release is treated as new: the whole path runs — prober, browser loop, status
# poll, ring diff, release log, migration diff, report — against a release that has already finished,
# which is harmless and proves every step. Point INBOX at a scratch directory when using it.
if [ -n "$FORCE_FIRST_WINDOW" ]; then
  LAST_VER=$(( LAST_VER - 1 ))
  LAST_SHA="${FORCE_PREV_SHA:-$(git -C "$REPO" rev-parse --short=8 "${LAST_SHA}~1" 2>/dev/null)}"
  say "  🧪 FORCE_FIRST_WINDOW — baseline backdated to v$LAST_VER ($LAST_SHA); the next poll will sample the current release"
fi

while :; do
  sleep "$POLL_S"
  NOW_EPOCH=$(date +%s)
  if [ $(( (NOW_EPOCH - START_EPOCH) / 86400 )) -ge "$MAX_DAYS" ]; then
    say "max lifetime ${MAX_DAYS}d reached with no migration-carrying release that landed — exiting"
    printf '# latency/%s — the #2724 release-window watcher expired\n\nArmed %s, exited %s after %s days.\nEvery release window it did see is banked under `%s` (one `window-*` directory each).\nNo migration-carrying release SUCCEEDED in that time, so #2724 still has no verdict against an exercised code path.\nRe-arm `tools/watch-release-window.sh`, or force the condition with a no-op migration.\n' \
      "$QUEUE" "$(date -u -r "$START_EPOCH" +%FT%TZ)" "$(date -u +%FT%TZ)" "$MAX_DAYS" "$WORK" \
      > "$INBOX/${QUEUE}-2724-EXPIRED.md"
    exit 0
  fi

  LINE=$(latest_release)
  VER=$(echo "$LINE" | cut -f1)
  STATUS=$(echo "$LINE" | cut -f2)
  SHA=$(echo "$LINE" | cut -f3)
  CREATED=$(echo "$LINE" | cut -f4)
  # Unreadable is NOT a signal. Heroku's API returning nothing looks identical to "no new release",
  # and treating it as either would be a guess; the next poll is 5 s away.
  [ -z "$VER" ] && { say "releases unreadable — retrying"; continue; }
  [ "$VER" = "$LAST_VER" ] && continue

  sample_window "$VER" "$SHA" "$LAST_SHA" "$CREATED"
  rc=$?
  LAST_VER="$VER"; LAST_SHA="$SHA"
  [ "$rc" = "10" ] && exit 0
done
