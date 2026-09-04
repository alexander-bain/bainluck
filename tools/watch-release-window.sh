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
# Banked where, though, is two different places (latency/132): every window appends ONE row to
# `ARTIFACT-LAT-2724-RELEASE-WINDOWS.md` and renders its full report into its own window dir, and only
# a release that FAILED or a window that actually ran a migration also writes a runner-inbox directive.
# See the ARTIFACT comment below for why.
#
# ── THE REQUEST BUDGET IS PART OF THE INSTRUMENT ───────────────────────────────────────────────────
# Production caps a client at 60 requests/minute. An unpaced burst measures its own 429s and renders
# `Rate limit exceeded` — 673 body chars, indistinguishable from a blank page in every column the felt
# rig used to have (that is how #2783 was filed). So the sampling budget is spent deliberately.
#
# How many requests a load costs is NOT settled: live/054 counted ~22 for an event page while hunting
# #2783; this rig counts 7 against api.bainluck.com on the settled fixture (`apiStatus {"200":7}`,
# measured 2026-09-03). The budget below uses the WORSE figure, because being wrong the other way is
# what poisons a verdict.
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
# 🔴 THE ARTIFACT IS THE DEFAULT SINK; THE INBOX IS THE EXCEPTION (latency/132, 2026-09-03).
# The first armed run banked ten windows in six hours and wrote ten inbox directives, one per release.
# Every one of them was a NEGATIVE CONTROL — no migration, clean prober, clean loads — and every one
# opened a lane session that read it, had nothing to do, and exited. Ten sessions to learn nothing
# happened ten times. A negative control is a LOG ROW, not a correspondent: every window now appends
# one line here, and only the two states a person can act on — a release that FAILED, or a window that
# actually EXERCISED the migration path — also become a directive. The full report is rendered for
# every window either way and lives beside its raw data in the window dir; the artifact row names it.
ARTIFACT="${ARTIFACT:-/Users/bain/bainluck/.claude/handoff/ARTIFACT-LAT-2724-RELEASE-WINDOWS.md}"
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
# What "exercised" looks like in a release log. Overridable so a dry run can point it at a string a
# NORMAL release prints and drive the fire arm end to end — the fire path would otherwise only ever
# execute on the one release nobody can schedule, which is how the old blind spot got built.
UPGRADE_MARKER="${UPGRADE_MARKER:-Running upgrade}"

mkdir -p "$WORK"
# Single-instance guard. mkdir is the atomic primitive here: macOS has no flock (memory:
# r_flock_absent_macos_use_mkdir), and two watchers would double every burst — which on a 60/min cap
# does not just duplicate the data, it invalidates it.
#
# 🔴 THE SELFTESTS TAKE NO LOCK AND CLEAR NONE. They fire nothing and sample nothing, so the guard has
# nothing to protect them from — but the guard's EXIT trap would `rmdir` a LIVE watcher's lock on the
# way out, which is the one way a read-only selftest could let a second watcher in behind it.
if [ -z "$WATCH_SELFTEST$WATCH_SINK_SELFTEST" ]; then
  if ! mkdir "$WORK/lock" 2>/dev/null; then
    echo "$(date -u +%FT%TZ) another watcher holds $WORK/lock — exiting"; exit 3
  fi
  trap 'rm -f "$WORK/active-window"; rmdir "$WORK/lock" 2>/dev/null' EXIT
fi

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
# One request per PROBE_S, writing TSV: epoch, http_code, total_seconds, rc=<curl exit code>.
# `%{http_code}` is 000 when the connection never completed, which is a distinct and important outcome
# from a slow 200 — during last night's convoy the reader-facing symptom was requests that never
# returned, not requests that were slow. curl's own timeout is deliberately longer than the probe
# cadence so a parked request is recorded as parked rather than as a gap in the file.
#
# 🔴 A `000` IS NOT BY ITSELF EVIDENCE ABOUT PRODUCTION. This sampler runs behind a sandbox egress
# proxy that fails independently of the site, and on 2026-09-03 it did: the v4037 window banked six
# `000` rows — two of them claiming 838 s and 337 s under `--max-time 60`, which no request can — while
# `watch.log` logged `tunneling socket could not be established, statusCode=503` over the same stretch
# and the next window came back 21/21 HTTP 200. The report read `🔴 re-opens #2724` off those rows.
# The 4th column exists so the reporter can tell a transport failure (rc 5/6/7/35/45/56/97 — never
# reached a Heroku router that could have parked it) from a genuine hang (rc 28, timed out waiting on
# a response). Never widen the classifier without widening this column first.
PROBE_MAX_TIME="${PROBE_MAX_TIME:-60}"
prober() {
  local out="$1" line rc
  while :; do
    line=$(curl -s -o /dev/null --max-time "$PROBE_MAX_TIME" \
      -w "%{http_code}\t%{time_total}" "$API$PROBE_PATH_URL" 2>/dev/null); rc=$?
    echo -e "$(date +%s)\t${line:-000\tcurl-failed}\trc=$rc" >> "$out"
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

# ── WHO GETS WOKEN UP ──────────────────────────────────────────────────────────────────────────────
# Echoes the reason a window deserves a runner-inbox directive, or nothing at all if the artifact row
# is the whole story. Two reasons, and only two:
#
#   (a) the release did not succeed — `failed`, or still `pending` when MAX_WINDOW_S ran out, which is
#       exactly the wedged v4016-v4019 shape this whole instrument exists to catch. `superseded` is
#       deliberately NOT a fire: it means a newer release started while we sampled, and that release
#       gets its own window, so firing here would report one retry twice.
#   (b) the window EXERCISED the migration path — the verdict window #2724 has been waiting for.
#
# It is a function so the sink selftest can drive every combination without a live release; the
# decision that runs unattended and the decision the selftest checks are the same six lines.
directive_reason() {
  local status="$1" exercised="$2" ver="$3" fire=""
  case "$status" in
    succeeded|superseded) ;;
    *) fire="release v$ver did not succeed (status=$status)" ;;
  esac
  [ "$exercised" = yes ] && fire="${fire:+$fire; }release v$ver EXERCISED the migration path"
  printf '%s' "$fire"
}

# ── ONE WINDOW ─────────────────────────────────────────────────────────────────────────────────────
sample_window() {
  local ver="$1" sha="$2" prev_sha="$3" created="$4"
  local tag="v${ver}-${sha}"
  local out="$WORK/window-$tag"
  mkdir -p "$out"
  local t0; t0=$(date +%s)

  say "🟢 WINDOW OPEN v$ver ($sha), prev $prev_sha — sampling"
  # 🔴 THE BUDGET IS SHARED, SO THE WINDOW IS ANNOUNCED. Production caps a client at 60 req/min for
  # the whole machine, not per process. An attended felt-table run alongside a window would push both
  # over the cap and BOTH readings would be about the throttling — and the attended one would silently
  # corrupt the unattended #2724 verdict, which is the one nobody can re-take. This marker exists so an
  # attended battery can wait; `tools/felt-table.sh` does. The watcher never waits for anyone: the
  # verdict outranks the table.
  echo "v$ver $sha $(date -u +%FT%TZ)" > "$WORK/active-window"

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
  rm -f "$WORK/active-window"
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

  # CARRIED IS NOT EXERCISED. The git diff above says the release SHIPPED a migration file; only the
  # release log says Alembic RAN one. `alembic upgrade heads` prints `Running upgrade <a> -> <b>` per
  # step and prints nothing at all when the database is already at head — so a release can carry a
  # migration file that a previous release already applied, and that window exercises nothing. This is
  # the line that decides whether a window is worth a human, so it reads the log, not the diff.
  local exercised=no
  grep -q "$UPGRADE_MARKER" "$out/release-output.txt" 2>/dev/null && exercised=yes

  # The report is rendered for EVERY window and always lands beside its own raw data. Whether it also
  # becomes an inbox directive is decided below; the rendering never is, because the artifact row
  # quotes the report's machine-read line and a row with no report behind it is not evidence.
  local report="$out/report.md"
  MIGS="$migs" CUR="$sha" LAST="$prev_sha" OUT="$out" WORK="$WORK" \
    RING_BEFORE="$out/ring-before.json" RING_PATH="$out/ring-after.json" \
    PROBE_PATH="$out/probe.tsv" PROBE_MAX_TIME="$PROBE_MAX_TIME" PROBE_S="$PROBE_S" \
    RELEASE_VERSION="$ver" RELEASE_STATUS="$status" \
    RELEASE_CREATED="$created" WINDOW_S="$elapsed" QUEUE="$QUEUE" \
    RELEASE_OUTPUT="$out/release-output.txt" REPORT_PATH="$report" \
    "$NODE" "$TOOLS/tools/watch-2724-report.mjs" >>"$LOG" 2>&1
  # A report that failed to render must still leave a trace — the raw data is banked either way and
  # whatever reads this must be told where it is.
  [ -s "$report" ] || printf '# latency/%s — release v%s (%s) sampled, report failed to render\n\nsha: %s\nmigrations: %s\nraw: %s\n' \
    "$QUEUE" "$ver" "$status" "$sha" "$migs" "$out" > "$report"

  local machine
  machine=$(grep -m1 '^\*\*Machine read:' "$report" 2>/dev/null \
            | sed -e 's/^\*\*Machine read: //' -e 's/\.\*\*[[:space:]]*$//' -e 's/|/⎮/g')
  [ -n "$machine" ] || machine='NO VERDICT — the report did not render'

  # ── ONE LINE PER WINDOW, ALWAYS ──────────────────────────────────────────────────────────────────
  if [ ! -s "$ARTIFACT" ]; then
    printf '# ARTIFACT-LAT-2724-RELEASE-WINDOWS — every release window the #2724 watcher sampled\n\nOne row per Heroku release observed by `tools/watch-release-window.sh`. **A row is the whole record of\na quiet window** — the watcher only writes a runner-inbox directive when a release FAILED or a window\nactually exercised the migration path (a `Running upgrade` line in the release log). Negative controls\nlive here and nowhere else. Every row names the window dir holding its full report and raw samples.\n\n| window closed (UTC) | release | status | sha range | migration carried | exercised | window | machine read | raw |\n|---|---|---|---|---|---|---|---|---|\n' \
      > "$ARTIFACT"
  fi
  printf '| %s | v%s | %s | `%s..%s` | %s | %s | %ss | %s | `%s` |\n' \
    "$(date -u +%FT%TZ)" "$ver" "$status" "${prev_sha:-?}" "${sha:-?}" \
    "$([ -n "$migs" ] && echo yes || echo no)" "$exercised" "$elapsed" "$machine" "$out" \
    >> "$ARTIFACT"

  # ── AND A DIRECTIVE ONLY WHEN A PERSON HAS SOMETHING TO DO ───────────────────────────────────────
  local fire; fire=$(directive_reason "$status" "$exercised" "$ver")

  if [ -n "$fire" ]; then
    local directive="$INBOX/${QUEUE}-2724-v${ver}-${status}.md"
    cp "$report" "$directive"
    say "  🔔 DIRECTIVE $directive — $fire"
  else
    say "  logged to artifact, no directive (window ${elapsed}s, status=$status, migration=$([ -n "$migs" ] && echo carried || echo none), exercised=$exercised)"
  fi

  # Exit only on the condition this watcher was armed for: a migration that actually LANDED. A failed
  # migration release is banked and then waited past, because the retry is still the verdict #2724 is
  # waiting for.
  if [ -n "$migs" ] && [ "$status" = "succeeded" ]; then
    say "  migration-carrying release SUCCEEDED and is banked — job done, exiting"
    return 10
  fi
  return 0
}

# ── SINK SELF-TEST ─────────────────────────────────────────────────────────────────────────────────
# The routing rule added in latency/132 has one job: never wake a person for a negative control, and
# always wake one for the two states that matter. Both arms are asserted — a rule that only proves it
# stays quiet is satisfied by a rule that is quiet about everything.
#   WATCH_SINK_SELFTEST=1 bash tools/watch-release-window.sh
if [ -n "$WATCH_SINK_SELFTEST" ]; then
  fails=0
  check() { # status exercised expect(fire|quiet)
    local got; got=$(directive_reason "$1" "$2" 4242)
    local verdict; [ -n "$got" ] && verdict=fire || verdict=quiet
    if [ "$verdict" = "$3" ]; then
      printf '  ok    status=%-10s exercised=%-3s -> %-5s %s\n' "$1" "$2" "$verdict" "$got"
    else
      printf '  FAIL  status=%-10s exercised=%-3s -> %-5s (expected %s) %s\n' "$1" "$2" "$verdict" "$3" "$got"
      fails=$(( fails + 1 ))
    fi
  }
  echo "sink selftest: directive_reason"
  check succeeded  no  quiet   # the negative control that burned ten sessions
  check superseded no  quiet   # the retry is reported by its own window, not twice
  check succeeded  yes fire    # THE verdict window
  check failed     no  fire    # the v4016-v4019 shape
  check failed     yes fire    # a migration that tried and could not land
  check pending    no  fire    # wedged past MAX_WINDOW_S
  [ "$fails" = 0 ] && { echo "sink selftest: ok"; exit 0; }
  echo "sink selftest: $fails FAILED"; exit 1
fi

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
    PROBE_MAX_TIME="$PROBE_MAX_TIME" PROBE_S="$PROBE_S" \
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
say "  baseline release v$LAST_VER ($LAST_SHA). artifact=$ARTIFACT inbox=$INBOX work=$WORK"
say "  every window -> one artifact row; directive ONLY on a non-succeeded release or a 'Running upgrade' window"

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
    printf '# latency/%s — the #2724 release-window watcher expired\n\nArmed %s, exited %s after %s days.\nEvery release window it did see has a row in `%s` and a full report under `%s` (one `window-*` directory each).\nNo migration-carrying release SUCCEEDED in that time, so #2724 still has no verdict against an exercised code path.\nRe-arm `tools/watch-release-window.sh` behind the next real migration. **Do NOT force the condition with a\nno-op migration** — ruled out by D42 (Alex, 2026-09-02): a migration that alters nothing takes no lock worth\ncontending, so it proves nothing about the mechanism #2724 is about.\n' \
      "$QUEUE" "$(date -u -r "$START_EPOCH" +%FT%TZ)" "$(date -u +%FT%TZ)" "$MAX_DAYS" "$ARTIFACT" "$WORK" \
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
