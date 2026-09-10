#!/bin/bash
# lane-runner.sh — Bain Luck autonomous lane runner (Fable, 2026-08-26; adopted by Alex ruling)
#
# Usage:  ./lane-runner.sh [--dry-run] <workdir> <lane> [lane2 ...]
#   One runner per WORKTREE. Multiple lane names = serialized service of multiple
#   inboxes from one tree. As of 2026-09-03 every lane has its own worktree and
#   its own window (lanes.conf), so the multi-lane form is a capability, not the
#   configuration; start-lanes.sh passes exactly one lane.
#
#   --dry-run  evaluate the SELF-RESTOCK rules once for each named lane, print
#              what would be written, write nothing, exit. Never runs a session.
#
# How it works: watches ~/bainluck/.claude/handoff/runner-inbox/<lane>/ for *.md
# queue files staged by Fable. Takes the OLDEST, runs a fresh headless claude
# session on it, logs everything, loops. Kill anytime with Ctrl-C; in-flight
# session state lives in handoff files per standing doctrine, so killing the
# runner never loses work.
#
# A directive is marked consumed ONLY on a clean session exit. A timeout, crash
# or failed session restores the queue name and retries, up to LANE_MAX_FAILS
# strikes, after which it is quarantined as *.failed-<ts> and announced loudly.
# Nothing unfinished is ever silently dequeued.
#
# PROVENANCE: directives in the inbox are authored in Alex's Fable session under
# the standing authorization Alex granted 2026-08-26 ("lane-runner, all lanes").
# Alex launches, watches, and can kill this runner; the attestation line inside
# each staged directive states this. Attended-exception commands (production
# DDL/DELETE, pushes reserved to Alex) remain forbidden to lanes by doctrine —
# the runner changes WHO STARTS sessions, never what sessions may do.

set -u
# Take the whole session subtree down with us. Without this, Ctrl-C or closing
# the window can orphan the in-flight claude session — it gets re-parented to
# launchd and keeps editing the worktree invisibly (seen 2026-08-26: two orphans
# in the ux tree). Directives are self-gated, so killing mid-work is always safe.
trap 'trap - INT TERM HUP; echo; echo "[runner] stopping - signalling session subtree"; kill 0 2>/dev/null; exit 130' INT TERM HUP

DRYRUN=0
RESTOCK_ONCE=0
if [ "${1:-}" = "--dry-run" ]; then DRYRUN=1; shift; fi
if [ "${1:-}" = "--restock-once" ]; then RESTOCK_ONCE=1; shift; fi

WORKDIR="${1:?usage: lane-runner.sh [--dry-run] <workdir> <lane> [lane2 ...]}"
shift
LANES=("$@")
[ ${#LANES[@]} -ge 1 ] || { echo "need at least one lane name"; exit 1; }

# Overridable so the guard test can point a whole runner at a scratch handoff
# tree. Production never sets it.
HANDOFF="${LANE_HANDOFF:-$HOME/bainluck/.claude/handoff}"
LOGDIR="$HANDOFF/runner-logs"
# No log dir for a rehearsal: --dry-run writes nothing at all, anywhere.
[ "$DRYRUN" -eq 1 ] || mkdir -p "$LOGDIR"

# --- NOTICE 39 RUNG 2: a lane's production reads say which lane made them ------
#
# `search_query_logs` cannot tell a lane from a person, so the warmer spends real
# work warming our own probe specimens. Rung 1 shipped the tag; this is the wiring
# that makes every lane carry it without any lane changing a command.
#
# WHY ZDOTDIR AND NOT THE LINE THE NOTICE SPECIFIES. Notice 39 says "ONE line ...
# that exports BL_AGENT=<lane> and sources latency's curl shadow". The export half
# works. The sourcing half CANNOT (#4662): every Bash tool call in a lane session
# is a fresh shell exec'd from the profile, and the shadow installs a shell
# FUNCTION, which is not inherited across exec. Sourced here it would die with
# this shell, before the lane's first command — merging, passing every gate, being
# recorded done, and tagging nothing. That is #4632's shape (D70: merged, tested,
# ruled, inert four days). ZDOTDIR is an ordinary env var, so it does cross the
# exec; see tools/lane-zdotdir/.zshenv for the measurement.
#
# A CHECKOUT IS NOT A DELIVERY BOUNDARY (#4685; CERT-2461's required repair).
# The first draft of this block resolved the chain from this script's own
# directory, and that is exactly where the ship went inert. `lanes.conf` runs
# `$HOME/bainluck/lane-runner.sh`, and that tree is the INTEGRATOR'S WORKSPACE,
# not a deployment: it fast-forwards to origin/master several times a day
# (measured from its reflog — 23/31/4/18 HEAD movements Sep 5/6/7/8), so it is
# never far behind for long, but between fast-forwards it lags by a whole merge
# cycle, and it can carry the integrator's uncommitted edits (28 tracked files
# differed from master on 2026-09-09). Reading tooling out of it means the fleet
# executes whatever one workspace held at that moment — which is how every gate
# read GREEN while nothing was tagged.
#
# So the carrier is resolved from a COMMITTED REF and materialized into a cache
# this runner owns. Content-addressed by the chain's tree sha and the shadow's
# blob sha, so re-materializing is a no-op and two runners cannot disagree; and
# published by rename, so a half-written bundle is never visible to a lane shell.
# Every worktree shares one object store, so the ref reads identically from any
# of them no matter what that worktree has checked out.
BL_REPO="$(cd "$(dirname "$0")" && pwd -P)"
BL_CARRIER_REF="${BL_CARRIER_REF:-origin/master}"
BL_CARRIER_ROOT="${BL_CARRIER_ROOT:-$HOME/.cache/bainluck-lane-carrier}"
# FLEET-WIDE (notice 39 guard 3, widened 2026-09-10 by latency/312 on the proof
# that guard asks for). One lane went first; the server-side read it was waiting
# on is now paid, THROUGH THE REAL CARRIER rather than a hand-sourced shadow —
# the distinction that matters, because every earlier read of this mechanism was
# taken in a shell someone had set up by hand, and so could not have caught
# #4777 (merged, executing on zero lanes). Measured on production at 16:34Z,
# same endpoint, same token prefix, same three seconds, after the 09:30:33
# restart that first loaded the carrier:
#
#     tagged  (bare `curl`, shadow loaded via ZDOTDIR)   4 requests -> 0 rows
#     control (`command curl`, bypasses the shadow)      4 requests -> 4 rows
#
# The control is what makes the zero readable: it proves the rig reached
# `search_query_logs`, so arm A's zero is suppression and not a blind zero
# (gotcha #53).
#
# Narrow again by naming lanes (`BL_TAG_LANES="latency ux"`); the env var still
# wins over this default, so the revert is one word.
#
# 🔴 CHANGING THIS LINE DOES NOTHING TO A RUNNING FLEET. Bash parses the whole
# session loop once, at process start, so the ten live runners keep the value
# they read when they launched. This default takes effect at the NEXT restart
# and not before — which is #4777 itself, and precisely why that issue needed
# Alex and could not be closed by a merge.
BL_TAG_LANES="${BL_TAG_LANES:-all}"

# Echo the ZDOTDIR to export, or echo nothing and return non-zero. Nothing means
# NO TAG, which is notice 39 guard 1: an incomplete carrier must degrade to
# plain, untagged curl and never to a broken shell. Pointing ZDOTDIR at a
# directory missing .zshenv would not merely skip the tag — it moves zsh's whole
# startup search off $HOME and silently drops ~/.zprofile from every lane shell
# (measured: HOMEBREW_PREFIX empties, so brew and half of PATH vanish). Hence
# every exit path here is "verified complete, or nothing".
bl_carrier_zdotdir() {
  bl_chain=$(git -C "$BL_REPO" rev-parse --verify -q "$BL_CARRIER_REF:tools/lane-zdotdir" 2>/dev/null) || return 1
  bl_shadow=$(git -C "$BL_REPO" rev-parse --verify -q "$BL_CARRIER_REF:tools/bl-agent-curl.sh" 2>/dev/null) || return 1
  [ -n "$bl_chain" ] && [ -n "$bl_shadow" ] || return 1
  bl_dest="$BL_CARRIER_ROOT/$bl_chain-$bl_shadow"

  if [ ! -f "$bl_dest/tools/lane-zdotdir/.zshenv" ] || [ ! -f "$bl_dest/tools/bl-agent-curl.sh" ]; then
    bl_tmp="$BL_CARRIER_ROOT/.staging.$$"
    rm -rf "$bl_tmp"
    if mkdir -p "$bl_tmp" 2>/dev/null &&
       git -C "$BL_REPO" archive --format=tar "$BL_CARRIER_REF" \
           tools/lane-zdotdir tools/bl-agent-curl.sh 2>/dev/null | tar -xf - -C "$bl_tmp" 2>/dev/null &&
       [ -f "$bl_tmp/tools/lane-zdotdir/.zshenv" ] && [ -f "$bl_tmp/tools/bl-agent-curl.sh" ]; then
      # `mv` ONTO an existing directory moves the source INSIDE it rather than
      # replacing it, so a lost race would bury the bundle a level down and the
      # presence test below would fail closed for no reason. Check first, and
      # treat a lost race as success: the name IS the content, so whoever won
      # published byte-identical files.
      [ -d "$bl_dest" ] || mv "$bl_tmp" "$bl_dest" 2>/dev/null
    fi
    rm -rf "$bl_tmp"
  fi

  [ -f "$bl_dest/tools/lane-zdotdir/.zshenv" ] || return 1
  [ -f "$bl_dest/tools/bl-agent-curl.sh" ] || return 1
  echo "$bl_dest/tools/lane-zdotdir"
}

bl_tag_lane() {
  case " $BL_TAG_LANES " in
    *" all "*) return 0 ;;
    *" $1 "*)  return 0 ;;
    *)         return 1 ;;
  esac
}

# #4689: one line per session saying whether this lane's production reads are
# actually tagged — and when they are not, WHICH of the three reasons, because
# they need three different fixes and today they share one silence.
#
# 🔴 THE SILENCE THIS ENDS, measured 2026-09-10 by latency/316. The fleet
# restarted at 13:25:02; the checkout carrying CERT-2518's widening of
# `BL_TAG_LANES` to `all` landed at 13:28:07 — three minutes LATER, so all ten
# runners parsed the old `latency`-only default and nine lanes ran untagged with
# nothing anywhere saying so. Recovering that afterwards took dating the runner
# process start times against the checkout's reflog, because macOS SIP blocks
# `ps -E` against another process: from inside a session the tag state was not
# merely unlogged, it was unobservable. "Deliberately off" and "broken" have to
# be different words in the log or the next miss is silent too.
#
# #4714 caps the budget — per-lane startup git calls already flake
# `test_lane_launchers.py` under band load — so the end-to-end probe is NOT paid
# per session. The carrier directory is content-addressed (`<chain>-<shadow>`),
# so the probe's verdict is a pure function of the bundle: it runs once per
# bundle and is stamped beside it, leaving one `[ -f ]` in steady state. The
# stamp is per-bundle and not per-lane on purpose — the shadow interpolates
# `$BL_AGENT`, so the MECHANISM is lane-independent and only the header's value
# differs. What the stamp may answer is bounded by that: it speaks for the
# BUNDLE's wiring and for nothing else, so every live control is diagnosed ahead
# of it (CERT-2542, at the `BL_CURL_NO_SHADOW` arm below).
#
# Advisory, like every other check here: it prints and returns 0. A lane must
# never fail to start because its reads would be untagged.
bl_tag_state() {
  bl_l=$1
  bl_zd=${2:-}

  if ! bl_tag_lane "$bl_l"; then
    echo "[runner:$bl_l] TAG OFF (by config) — '$bl_l' is not in BL_TAG_LANES='$BL_TAG_LANES'; this lane's production reads are untagged (#4689)"
    return 0
  fi
  # CERT-2542. A LIVE control, asked every session and answered BEFORE the stamp
  # is consulted. The two questions have different lifetimes and only one of them
  # is cacheable:
  #
  #   "does THIS BUNDLE's wiring add the header?"   pure function of bundle
  #                                                 content -> stamp, per
  #                                                 content-addressed path
  #   "is that wiring switched on in THIS process?" pure function of the
  #                                                 environment -> ask it live
  #
  # `BL_CURL_NO_SHADOW=1` is the shadow's documented opt-out: it defines `bl_curl`
  # and installs no `curl` wrapper, so the same bundle with the same healthy stamp
  # runs entirely untagged. Letting the stamp answer the second question printed
  # "TAG ON — reads carry x-bainluck-origin" into the log of a lane whose every
  # read was plain curl — a false ON in the one ship that exists to end exactly
  # that silence. Live controls are a variable test; never cache one.
  #
  # OFF, not BROKEN: an operator asked for this, the same as a lane being off the
  # allowlist. Calling a deliberate choice a defect is the mistake the no-zsh arm
  # below exists to avoid (gotcha #53). Ordered with the allowlist arm for the
  # same reason — ask whether we are meant to be tagging at all before asking
  # whether the machinery works — which also keeps the probe from firing (and
  # reaching the network, since an unwrapped `curl` ignores BL_CURL_PRINT) in a
  # session that opted out.
  if [ -n "${BL_CURL_NO_SHADOW:-}" ]; then
    echo "[runner:$bl_l] TAG OFF (by config) — BL_CURL_NO_SHADOW='${BL_CURL_NO_SHADOW:-}' is set, so no curl wrapper is installed and a plain 'curl' is unwrapped; this lane's production reads are untagged (#4689)"
    return 0
  fi
  if [ -z "$bl_zd" ]; then
    echo "[runner:$bl_l] TAG BROKEN — '$bl_l' is allowlisted but no carrier could be delivered from $BL_CARRIER_REF; reads fall through to plain curl (#4689)"
    return 0
  fi

  # No zsh is "could not check", which is not "broken". Saying BROKEN here would
  # manufacture a defect out of a missing instrument (gotcha #53).
  if ! command -v zsh >/dev/null 2>&1; then
    echo "[runner:$bl_l] TAG ON (unverified) — carrier delivered; no zsh on this host to prove the shell end (#4689)"
    return 0
  fi

  bl_stamp="$bl_zd/../../.verified-tag"
  if [ ! -f "$bl_stamp" ]; then
    # `zsh -c`, not `zsh -l -c`: `.zshenv` is read by every zsh there is, and a
    # login shell would drag in `.zprofile` for nothing. BL_CURL_PRINT makes it
    # argv-only — no network, no side effect.
    bl_probe=$(ZDOTDIR="$bl_zd" BL_AGENT="$bl_l" BL_CURL_PRINT=1 \
               zsh -c 'curl -s https://api.bainluck.com/' 2>/dev/null)
    case "$bl_probe" in
      *"x-bainluck-origin: $bl_l"*) : > "$bl_stamp" 2>/dev/null ;;
      *)
        echo "[runner:$bl_l] TAG BROKEN — carrier delivered, but curl in a child shell did NOT add x-bainluck-origin; reads are untagged (#4689)"
        return 0
        ;;
    esac
  fi

  echo "[runner:$bl_l] TAG ON — reads carry 'x-bainluck-origin: $bl_l' (carrier verified end-to-end)"
}

# #4689: say so, once per runner, when the script EXECUTING this lane is not the
# committed one. Silent drift is how a tooling ship merges green and does nothing
# for four days (#4632's shape, and CERT-2461's). Advisory only — never fatal,
# never blocks a session, because a lane that cannot run is worse than a stale one.
bl_warn_if_runner_is_stale() {
  bl_live=$(git -C "$BL_REPO" hash-object "$0" 2>/dev/null) || return 0
  bl_head=$(git -C "$BL_REPO" rev-parse --verify -q "$BL_CARRIER_REF:lane-runner.sh" 2>/dev/null) || return 0
  [ -n "$bl_live" ] && [ -n "$bl_head" ] && [ "$bl_live" != "$bl_head" ] || return 0
  echo "[runner:$1] WARNING: $0 differs from $BL_CARRIER_REF:lane-runner.sh — this lane is executing tooling that is not on master (#4685)" >&2
}

# Ownership record for the orphan reaper in start-lanes.sh. Sessions spawned by
# this runner inherit its process group, and re-parenting to launchd changes
# ppid but never pgid — so the pgid is a durable "this runner started it" handle
# that survives the runner's own death. start-lanes.sh reaps ONLY groups listed
# here, so an unrelated headless claude elsewhere on the machine is never a
# target. Deliberately NOT removed on exit: a surviving orphan must keep its
# ownership record, and start-lanes.sh garbage-collects records whose group has
# no live members.
#
# Residual, stated rather than hidden: ownership is a pgid, and the OS recycles
# pgids. A record whose group is long dead could in principle be re-matched by an
# unrelated process that later inherits that number. That is why records are
# garbage-collected on every runner start AND every start-lanes.sh run — the
# window is a live process's lifetime, not forever — and why the reap still also
# requires ppid 1 and a headless-claude argv. Under-reaping is the safe direction.
PIDDIR="$HANDOFF/runner-pids"
# Ownership records are claimed ONLY by a runner that will actually start
# sessions. --dry-run and --restock-once spawn nothing, so claiming a pgid would
# be a lie the orphan reaper later acts on — and the GC below DELETES files, so a
# rehearsal could disown a live runner's sessions. A rehearsal leaves the handoff
# tree byte-identical; that is what makes it safe to run against production state.
if [ "$DRYRUN" -eq 0 ] && [ "$RESTOCK_ONCE" -eq 0 ]; then
mkdir -p "$PIDDIR"
# GC before claiming: drop records whose process group has no live member. List
# the files BEFORE snapshotting ps — the reverse order races the sibling runners
# start-lanes.sh launches together and would delete a record written after the
# snapshot, disowning a live runner's sessions.
STALE=$(ls "$PIDDIR"/*.pgid 2>/dev/null || true)
LIVE_PGIDS=$(ps -axo pgid= | tr -d ' ' | sort -u)
for F in $STALE; do
  P=$(tr -cd '0-9' < "$F" 2>/dev/null)
  if [ -z "$P" ] || ! echo "$LIVE_PGIDS" | grep -qx "$P"; then rm -f "$F"; fi
done
RUNNER_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
echo "$RUNNER_PGID" > "$PIDDIR/runner-$$.pgid"
fi
for L in "${LANES[@]}"; do
  # Once per runner, before any session: is the script we are executing the one
  # that is on master? A rehearsal says so too — that is the invocation someone
  # runs when they are asking this very question.
  bl_warn_if_runner_is_stale "$L"
  # A rehearsal does not conjure an inbox either — maybe_restock reports a
  # missing one, which is the honest answer for a lane that has no inbox.
  [ "$DRYRUN" -eq 1 ] || mkdir -p "$HANDOFF/runner-inbox/$L"
  # Crash recovery: a .running file means a prior runner died mid-session
  # (reboot, closed laptop). Re-queue it — directives are self-gated, so
  # re-running is always safe.
  #
  # Skipped whenever this invocation will not start sessions. --dry-run was
  # already excluded (a rehearsal that re-queues a live lane's in-flight
  # directive is not a rehearsal); --restock-once was NOT, and it is the same
  # hazard wearing a different flag: Fable runs it to nudge an idle lane, and on
  # a lane that is actually busy it renamed the live session's marker back to
  # `.md` for the real runner to take a second time. Only a runner that is about
  # to serve the queue itself has any business re-queuing (integrator/205).
  # A genuinely orphaned marker is not lost by this: reap_stale_running retires
  # it on an age test that a live session's marker can never satisfy.
  { [ "$DRYRUN" -eq 1 ] || [ "$RESTOCK_ONCE" -eq 1 ]; } && continue
  for R in "$HANDOFF/runner-inbox/$L"/*.md.running; do
    [ -e "$R" ] || continue
    mv "$R" "${R%.running}"
    case "$R" in *".consumed-"*) ;;   # already-done queue; glob skips it, stay quiet
      *) echo "[runner:$L] re-queued interrupted $(basename "${R%.running}")";;
    esac
  done
done

cd "$WORKDIR" || { echo "bad workdir $WORKDIR"; exit 1; }
echo "[runner] serving lanes: ${LANES[*]}  from $WORKDIR"
echo "[runner] inbox root: $HANDOFF/runner-inbox/  logs: $LOGDIR/"

SESSION_TIMEOUT="${LANE_SESSION_TIMEOUT:-7200}"   # 2h hard cap per session
MAX_FAILS="${LANE_MAX_FAILS:-3}"                  # strikes before a directive is quarantined
RETRY_BACKOFF="${LANE_RETRY_BACKOFF:-60}"         # seconds between re-queue and retry
# Overridable so a guard test can drive the IDLE LOOP itself rather than only the
# --dry-run/--restock-once entry points. The idle loop is where the stale-marker
# reaper actually runs in production; a mutation battery on integrator/205 showed
# that call site surviving every test until the loop became drivable.
IDLE_SLEEP="${LANE_IDLE_SLEEP:-60}"

# ─── SELF-RESTOCK (integrator/106 Change A, 2026-09-03) ──────────────────────
# A lane whose inbox emptied used to sit idle until a human staged the next
# directive. Measured 9/3: `live` idle 3h, `latency` idle 1.5h, waiting for a
# person — while both had a program file sitting right there saying what came
# next. So the runner now stages the lane's own next directive: read your
# program file, your standing notices and your last three consumed directives,
# and write your own.
#
# Four guards, each for a failure this would otherwise cause:
#   1. Only when the inbox has NO queued .md AND NOTHING .running. A duplicate
#      runner's in-flight session must never be raced into a second directive.
#   2. At most ONE RESTOCK pending per lane (implied by guard 1, asserted anyway
#      so the intent survives a future edit to guard 1).
#   3. NEVER for a lane with no program/conveyor file. A directive that says
#      "read PROGRAM-FOO.md" when PROGRAM-FOO.md does not exist is worse than
#      silence: the session burns a turn discovering that. Log instead — the
#      log line names the lane, so Fable fixes it with one line in the map.
#   4. A floor between consecutive restocks per lane. Without it, a restock that
#      fails on contact re-queues, quarantines, empties the inbox, and restocks
#      again — a lane spinning full sessions at session speed. The floor caps
#      that at one attempt per RESTOCK_MIN_INTERVAL; normal sessions run for
#      many minutes and never touch it.
RESTOCK_MIN_INTERVAL="${LANE_RESTOCK_MIN_INTERVAL:-120}"

# Which program/conveyor file does a lane read to decide its own next work?
# Checked in order, first one that EXISTS wins. `lane-program-map.txt` in the
# handoff dir overrides everything (lines: "<lane> <file>"), so a lane can be
# pointed at a new conveyor without editing this script.
lane_program_candidates () {
  case "$1" in
    ux)          echo "PROGRAM-UX-NEXT.md PROGRAM-UX-QUEUE.md" ;;
    latency)     echo "PROGRAM-LATENCY-NEXT.md PROGRAM-LATENCY-QUEUE.md" ;;
    calibration) echo "PROGRAM-CALIBRATION-NEXT.md PROGRAM-CALIBRATION-QUEUE.md" ;;
    live)        echo "PROGRAM-LIVE-NEXT.md" ;;
    authority)   echo "PROGRAM-AUTHORITY.md" ;;
    native)      echo "PROGRAM-NATIVE.md" ;;
    # lane1, lane1b and integrator are driven directive-by-directive and have no
    # standing conveyor today. They fall through to the default name; when it does
    # not exist they are LOGGED, not restocked (guard 3). Give one a conveyor by
    # adding a line to lane-program-map.txt — no edit to this script needed.
    *)           echo "PROGRAM-$(echo "$1" | tr 'a-z' 'A-Z').md" ;;
  esac
}

lane_program () {
  local L="$1" cand mapped
  mapped=$(awk -v l="$L" '$1==l {print $2; exit}' "$HANDOFF/lane-program-map.txt" 2>/dev/null)
  if [ -n "${mapped:-}" ]; then
    [ -f "$HANDOFF/$mapped" ] && { echo "$mapped"; return 0; }
    return 1
  fi
  for cand in $(lane_program_candidates "$L"); do
    [ -f "$HANDOFF/$cand" ] && { echo "$cand"; return 0; }
  done
  return 1
}

# Count queued directives exactly the way the take loop globs for them, so the
# two can never disagree about whether a lane has work.
inbox_queued () { ls "$1"/*.md 2>/dev/null | grep -vc '\.consumed-' ; }
inbox_running () { ls "$1"/*.md.running 2>/dev/null | wc -l | tr -d ' ' ; }
inbox_restocks () { ls "$1"/RESTOCK-*.md "$1"/RESTOCK-*.md.running 2>/dev/null | wc -l | tr -d ' ' ; }

# ─── STALE .running REAPER (integrator/205, 2026-09-05) ──────────────────────
# THE BUG THIS EXISTS FOR. The runner takes `Q` -> `Q.running` and, when the
# session ends, moves `$RUN` to `.consumed-`/back to `$Q`. But a session may
# RENAME ITS OWN MARKER: a self-restock session marks its RESTOCK file
# `…superseded-by-047` and writes `047-….md.running` in its place. If that
# session then hits the 2h cap (rc 124) or just ends, `mv "$RUN" …` finds no
# `$RUN`, the orphan `047-….md.running` stays forever, `inbox_running` reads 1,
# guard 1 blocks every restock, and no queued `.md` exists to take. The lane
# goes idle silently and nothing in the window says why. Measured 2026-09-05:
# integrator idle ~4:00–4:10am on a marker left from Thursday, native idle
# 8:59–10:10am, lane1b idle 7:33–10:10am — all three the same shape.
#
# The startup crash-recovery pass above cannot catch this: it runs ONCE, when
# the runner starts, so a marker orphaned by a session under a long-lived runner
# is never looked at again.
#
# WHY .stale- AND NOT BACK TO .md. Crash recovery re-queues because a runner
# that died mid-session left work genuinely unstarted. Here the session RAN — it
# usually merged, pushed and reported, and only the bookkeeping was lost.
# Re-queuing would re-run finished work. A lane re-stages what it still owes;
# the marker is kept under a name the queue glob cannot see so the evidence
# survives.
#
# AGE, NOT GUESSWORK: only a marker older than a session could possibly be is
# touched, so a live session's marker is never eligible. ctime (inode change
# time) is the right clock — `mv` updates it, so it dates the take, not the
# directive's authoring.
STALE_RUNNING_GRACE="${LANE_STALE_RUNNING_GRACE:-300}"

# GNU FORM FIRST, AND THE ORDER IS THE WHOLE POINT. On BSD/macOS `stat -f` takes
# a format string and `%c` is ctime. On GNU coreutils `-f` means "filesystem
# status" and `%c` is the filesystem's TOTAL INODE COUNT — so `stat -f %c` there
# is not an error, it exits 0 and prints a large number that is not a time at
# all. Probing BSD-first therefore handed Linux a silent, plausible-looking
# wrong answer: every marker read as decades old, and the reaper retired live
# sessions' markers. Caught by CI 2026-09-05; structurally invisible on the
# macOS laptop this was written on. GNU's `-c` is rejected outright by BSD stat
# (exit 1, "illegal option"), so this order fails in the safe direction on both.
#
# The result is then range-checked: a real ctime is an epoch, an inode count is
# not. Prints nothing if no form yields a plausible timestamp, and every caller
# treats "no reading" as "not eligible" — a marker is never retired on a reading
# we do not trust.
file_ctime () {
  local V
  V=$(stat -c %Z "$1" 2>/dev/null) || V=$(stat -f %c "$1" 2>/dev/null) || return 1
  case "${V:-}" in ''|*[!0-9]*) return 1 ;; esac
  [ "$V" -ge 1000000000 ] || return 1     # 2001-09-09; below that it is not a ctime
  echo "$V"
}

# Rename one marker out of the way and say so. One place, so the idle reaper and
# the post-session sweep can never drift in what they leave behind.
retire_running_marker () {
  local R="$1" WHY="$2" L="$3" DEST
  DEST="${R%.running}.stale-$(date +%Y%m%d-%H%M%S)"
  if [ "$DRYRUN" -eq 1 ]; then
    echo "[reap:$L] WOULD RETIRE $(basename "$R") -> $(basename "$DEST") ($WHY)"
    return 0
  fi
  mv "$R" "$DEST" 2>/dev/null || return 1
  echo "[reap:$L] retired orphaned marker $(basename "$R") ($WHY)"
  echo "[reap:$L]   kept as $(basename "$DEST") — NOT re-queued; re-stage as *.md if the lane still owes this work"
  return 0
}

# Idle-loop reaper: any marker older than a session can possibly be.
reap_stale_running () {
  local L="$1" INBOX R C NOW CUT
  INBOX="$HANDOFF/runner-inbox/$L"
  [ -d "$INBOX" ] || return 0
  NOW=$(date +%s)
  CUT=$(( SESSION_TIMEOUT + STALE_RUNNING_GRACE ))
  for R in "$INBOX"/*.md.running; do
    [ -e "$R" ] || continue
    C=$(file_ctime "$R")
    [ -n "${C:-}" ] || continue
    [ $((NOW - C)) -ge "$CUT" ] || continue
    retire_running_marker "$R" "$((NOW - C))s old, past the ${CUT}s session cap" "$L"
  done
  return 0
}

# Post-session sweep: the session just ended and its own `$RUN` is gone, which
# means it renamed markers. Anything `.running` in this lane's inbox that did
# not exist before the session started is that session's leftover.
#
# Residual, stated rather than hidden: a DUPLICATE runner on this same lane that
# took a directive during our session would have a marker in the same age window
# and would be retired under it. That window is one session long and the
# condition is narrow (only reached when our own marker vanished). It is also
# strictly safer than the startup crash-recovery pass directly above, which
# renames every `.md.running` back to `.md` unconditionally and would hand a live
# sibling's in-flight directive to a second session.
sweep_session_running () {
  local L="$1" SINCE="$2" INBOX R C
  INBOX="$HANDOFF/runner-inbox/$L"
  [ -d "$INBOX" ] || return 0
  for R in "$INBOX"/*.md.running; do
    [ -e "$R" ] || continue
    C=$(file_ctime "$R")
    [ -n "${C:-}" ] || continue
    [ "$C" -ge "$SINCE" ] || continue
    retire_running_marker "$R" "written by the session that just ended" "$L"
  done
  return 0
}

# Evaluate the restock rules for one lane. Writes the directive unless DRYRUN.
# Says why it declined — but only when RESTOCK_QUIET is 0, because this runs on
# every 60s idle cycle and an unthrottled "no program file" would bury the
# window in the one message nobody can act on from inside the lane. The idle
# loop unquiets it on the same ~5-minute cadence as the idle line, so an empty
# window still always distinguishes "no work queued" from "stuck".
RESTOCK_QUIET=0
rs_say () { [ "$RESTOCK_QUIET" -eq 0 ] && echo "$@"; return 0; }

maybe_restock () {
  local L="$1" INBOX PROG NOW LAST STAMP F LASTF
  INBOX="$HANDOFF/runner-inbox/$L"
  [ -d "$INBOX" ] || { rs_say "[restock:$L] no inbox at $INBOX — nothing to do"; return 1; }

  [ "$(inbox_queued "$INBOX")" -eq 0 ]   || { rs_say "[restock:$L] inbox has queued work — no restock"; return 1; }
  [ "$(inbox_running "$INBOX")" -eq 0 ]  || { rs_say "[restock:$L] a directive is .running — no restock"; return 1; }
  [ "$(inbox_restocks "$INBOX")" -eq 0 ] || { rs_say "[restock:$L] a RESTOCK is already pending — no restock"; return 1; }

  PROG=$(lane_program "$L") || {
    rs_say "[restock:$L] NO PROGRAM FILE — lane left idle on purpose. Add a line to"
    rs_say "[restock:$L]   $HANDOFF/lane-program-map.txt   (format: '$L <file-in-handoff>')"
    return 1
  }

  LASTF="$INBOX/.last-restock"
  NOW=$(date +%s)
  # `< missing-file` is a SHELL redirection error, printed before tr ever runs,
  # so `2>/dev/null` on tr does not silence it. Test for the file instead.
  LAST=""
  [ -f "$LASTF" ] && LAST=$(tr -cd '0-9' < "$LASTF")
  if [ -n "${LAST:-}" ] && [ $((NOW - LAST)) -lt "$RESTOCK_MIN_INTERVAL" ]; then
    rs_say "[restock:$L] last restock $((NOW - LAST))s ago (<${RESTOCK_MIN_INTERVAL}s floor) — holding"
    return 1
  fi

  STAMP=$(date +%Y%m%d-%H%M%S)
  F="$INBOX/RESTOCK-$STAMP.md"
  if [ "$DRYRUN" -eq 1 ]; then
    echo "[restock:$L] WOULD WRITE $F:"
    restock_text "$L" "$PROG" | sed 's/^/    | /'
    return 0
  fi
  restock_text "$L" "$PROG" > "$F"
  echo "$NOW" > "$LASTF"
  echo "[restock:$L] inbox empty — wrote $(basename "$F") (program: $PROG)"
  return 0
}

# The directive text. Fable-5's wording, plus the lane's three most recent
# consumed filenames inlined — they are the cheapest possible orientation and
# save the session an `ls` under the bonded-read rule.
restock_text () {
  local L="$1" PROG="$2" INBOX="$HANDOFF/runner-inbox/$1" c
  echo "# $L — self-restock (written by lane-runner.sh, no human in the loop)"
  echo
  echo "Your inbox is empty. Read \`.claude/handoff/$PROG\`, \`.claude/handoff/STANDING-NOTICES.md\`,"
  echo "and your last three \`.consumed-*\` directives; write your own next directive to your"
  echo "inbox and consume it. Do not end with a question."
  echo
  echo "Your last three consumed directives:"
  c=$(ls -t "$INBOX" 2>/dev/null | grep '\.consumed-' | head -3)
  if [ -n "${c:-}" ]; then printf '%s\n' "$c" | sed 's/^/  - /'; else echo "  - (none yet)"; fi
  echo
  echo "This directive exists because the runner found nothing queued for you, not because"
  echo "anyone decided what you should do next. Pick the work yourself, from the program file"
  echo "and the standing notices; an idle build lane is a signal, never something to fill with"
  echo "measurement (CLAUDE.md, LANE ROLES)."
}

# --dry-run: evaluate every named lane once, print, change nothing, exit.
if [ "$DRYRUN" -eq 1 ]; then
  echo "[runner] --dry-run: self-restock evaluation only, nothing will be written"
  echo "[runner] handoff root: $HANDOFF"
  # The reaper runs BEFORE restock in the idle loop, so the rehearsal must show
  # it in the same order — a marker it would retire is one guard 1 currently
  # blocks on, and printing them the other way round would misdescribe the run.
  for L in "${LANES[@]}"; do reap_stale_running "$L"; maybe_restock "$L"; done
  exit 0
fi

# --restock-once: do ONE real restock pass and exit without running any session.
# Two uses: Fable can nudge an idle lane without starting a runner, and the guard
# test can exercise the WRITE path — --dry-run alone only ever proves the branch
# that writes nothing, which is not the branch that runs in production.
if [ "$RESTOCK_ONCE" -eq 1 ]; then
  echo "[runner] --restock-once: one real restock pass, no session will be started"
  RC=1
  for L in "${LANES[@]}"; do reap_stale_running "$L"; maybe_restock "$L" && RC=0; done
  exit "$RC"
fi

# ─── CROSS-ROOT WRITE GRANT (integrator/135 item 2, 2026-09-04) ──────────────
# A lane must be able to write handoff files in ~/bainluck. What grants that is a
# settings file, not a flag (DAILY-OPERATIONS.md): each worktree carries
# .claude/settings.json with permissions.additionalDirectories naming ~/bainluck.
# `--add-dir` alone grants READ but not WRITE, and settings are read at LAUNCH
# only — so this must happen here, before the session starts, not inside it.
#
# WHY IT IS THE RUNNER'S JOB. The file is per-worktree, and standing up a new lane
# means remembering to copy it. `native` was created 9/3 without it and spent its
# whole existence unable to file: every note it wrote went to a private
# handoff-outbox/ that only a human copying by hand could deliver, and 8 had piled
# up by 9/4. Nobody can see that failure from inside the lane — the session just
# gets EPERM and works around it. Nor can another lane fix it: the writable set is
# own-worktree + ~/bainluck (see the Integrator's own EPERM on ~/bainluck-dev), so
# the ONE process that can reliably create this file is the runner that launches
# the lane, in Alex's own shell. Doing it on every start also makes it self-healing
# rather than a checklist item on `lanes.conf`.
#
# Conservative by construction: an existing grant is left byte-identical (no
# rewrite, no reformat), a settings.json carrying OTHER keys is MERGED not
# clobbered, and the integrator is skipped because its workdir IS ~/bainluck and
# its own settings.local.json carries the reverse (~/bainluck-dev) grant.
ensure_cross_root_grant () {
  local WD="$1" GRANT="$HOME/bainluck" F
  [ "$(cd "$WD" && pwd -P)" != "$(cd "$HOME/bainluck" && pwd -P)" ] || return 0
  F="$WD/.claude/settings.json"
  mkdir -p "$WD/.claude" 2>/dev/null || true
  python3 - "$F" "$GRANT" <<'PY' || echo "[runner] WARNING: could not verify the cross-root write grant — this lane may be unable to write ~/bainluck/.claude/handoff/ (notes will land in handoff-outbox/)"
import json, os, sys
path, grant = sys.argv[1], sys.argv[2]
try:
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("settings.json is not an object")
except FileNotFoundError:
    data = None
except Exception as exc:
    # Never overwrite a file we failed to parse — it may hold a lane's real
    # settings. Say so and leave it; a human fixes the JSON.
    print("[runner] settings.json at %s is unreadable (%s) — leaving it alone" % (path, exc))
    sys.exit(0)
if data is None:
    data = {"permissions": {"additionalDirectories": [grant]}}
else:
    perms = data.setdefault("permissions", {})
    if not isinstance(perms, dict):
        print("[runner] settings.json at %s has a non-object 'permissions' — leaving it alone" % path)
        sys.exit(0)
    dirs = perms.setdefault("additionalDirectories", [])
    if not isinstance(dirs, list):
        print("[runner] settings.json at %s has a non-list 'additionalDirectories' — leaving it alone" % path)
        sys.exit(0)
    if grant in dirs:
        sys.exit(0)          # already granted: do not rewrite the file
    dirs.append(grant)
tmp = path + ".tmp.%d" % os.getpid()
with open(tmp, "w") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
os.replace(tmp, path)
print("[runner] wrote the cross-root write grant (%s -> %s)" % (path, grant))
PY
}
ensure_cross_root_grant "$WORKDIR"

# stream-json → readable live lines. `claude -p` prints nothing until the end
# unless asked for stream-json events; this renders them as they arrive:
# assistant text, every tool call (name + gist), and a final result line.
FMT='
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except Exception:
        print(line); sys.stdout.flush(); continue   # banners/stderr pass through
    t = e.get("type")
    if t == "system" and e.get("subtype") == "init":
        print("[session] started, model=%s" % e.get("model", "?"))
    elif t == "assistant":
        for c in e.get("message", {}).get("content", []) or []:
            if c.get("type") == "text" and (c.get("text") or "").strip():
                print(c["text"].strip())
            elif c.get("type") == "tool_use":
                inp = c.get("input") or {}
                gist = inp.get("command") or inp.get("file_path") or \
                       inp.get("pattern") or inp.get("description") or ""
                gist = " ".join(str(gist).split())[:160]
                print("  -> %s %s" % (c.get("name", "?"), gist))
    elif t == "result":
        print("[result] %s turns=%s %ss" % (e.get("subtype", ""),
              e.get("num_turns", "?"), round((e.get("duration_ms") or 0) / 1000)))
    sys.stdout.flush()
'

IDLE=0
while true; do
  TOOK=0
  for L in "${LANES[@]}"; do
    INBOX="$HANDOFF/runner-inbox/$L"
    # oldest staged .md first; skip .running / .consumed
    Q=$(ls -tr "$INBOX"/*.md 2>/dev/null | grep -v '\.consumed-' | head -1)
    [ -n "${Q:-}" ] || continue
    TS=$(date +%Y%m%d-%H%M%S)
    RUN="$Q.running"
    mv "$Q" "$RUN" 2>/dev/null || continue   # atomic take; lose the race → next loop
    LOG="$LOGDIR/$L-$TS.log"
    # Read BEFORE the session so the post-session sweep can tell this session's
    # own leftover markers from ones that were already sitting there.
    SESSION_START=$(date +%s)
    echo "[runner:$L] $TS taking $(basename "$Q") → log $(basename "$LOG")"
    # Fresh headless session per queue. Timeout guards a hung session; state is
    # in handoff files, so a killed session resumes via its own report + re-stage.
    # Notice 39 rung 2. Inside the subshell so the runner's own environment is
    # never touched: the exports reach `claude` and everything it spawns, and
    # nothing else. PIPESTATUS below still reads the pipeline, not this `if`.
    ( BL_ZD=""
      if bl_tag_lane "$L" && BL_ZD=$(bl_carrier_zdotdir); then
        export BL_AGENT="$L" ZDOTDIR="$BL_ZD"
      fi
      # #4689: into the SESSION LOG, not only the runner's terminal. A warning
      # that lands on a scrollback nobody owns reads as noise — #4878's own
      # correction about `runner-text-drift.sh`. In the log it is greppable by
      # the next session, which is the only reader that can act on it.
      bl_tag_state "$L" "$BL_ZD" | tee -a "$LOG"
      timeout "$SESSION_TIMEOUT" claude --dangerously-skip-permissions --verbose \
        --output-format stream-json -p "$(cat "$HANDOFF/STANDING-NOTICES.md" 2>/dev/null; echo; cat "$RUN")" \
        2>&1 | python3 -u -c "$FMT" | tee -a "$LOG"
      # PIPESTATUS MUST be read inside the subshell. Read outside it, the array
      # holds the subshell's OWN status — i.e. tee's — so a timeout-124 or a
      # dead `claude` measured as rc=0 (verified: `( timeout 1 sleep 5 | cat |
      # cat )` then reading PIPESTATUS[0] in the parent yields 0). Re-exit with
      # the session's real code so the caller can gate on it.
      exit "${PIPESTATUS[0]}" )
    RC=$?
    # Consume ONLY a session that exited clean. Anything else — timeout 124,
    # auth/network failure, crash — restores the queue name so the directive
    # stays visible to the glob. mv preserves mtime, so a retry stays at the head
    # of this lane's queue rather than jumping the order.
    FAILS="$INBOX/.$(basename "$Q").fails"
    # The session renamed our marker out from under us (integrator/205). There
    # is nothing to consume or re-queue — `mv "$RUN" …` would only print an
    # error and leave whatever the session wrote behind, which is precisely the
    # orphan that wedges the lane. Say so plainly and sweep this session's
    # leftovers instead of pretending the bookkeeping worked.
    if [ ! -e "$RUN" ]; then
      rm -f "$FAILS"
      echo "[runner:$L] rc=$RC — $(basename "$RUN") was renamed by the session itself; nothing to consume"
      sweep_session_running "$L" "$SESSION_START"
      TOOK=1
      continue
    fi
    if [ "$RC" -eq 0 ]; then
      rm -f "$FAILS"
      mv "$RUN" "${Q%.md}.consumed-$TS"   # no .md suffix — must never re-match the queue glob
      echo "[runner:$L] done rc=0 $(basename "$Q")"
    else
      # Retry guard: without a strike count, a directive that fails on contact
      # (bad auth, unreachable API) re-queues and re-runs forever at session
      # speed. Three strikes and it is quarantined under a name the glob cannot
      # see, loudly, so the lane moves on to real work.
      N=$(tr -cd '0-9' < "$FAILS" 2>/dev/null)
      N=$(( ${N:-0} + 1 ))
      echo "$N" > "$FAILS"
      if [ "$N" -ge "$MAX_FAILS" ]; then
        rm -f "$FAILS"
        mv "$RUN" "${Q%.md}.failed-$TS"   # no .md suffix — quarantined, never re-queued
        echo "[runner:$L] ***************************************************************"
        echo "[runner:$L] QUARANTINED $(basename "$Q") — $N consecutive failures, last rc=$RC"
        echo "[runner:$L] NOT re-queued. Kept as $(basename "${Q%.md}.failed-$TS")"
        echo "[runner:$L] Log: $LOG"
        echo "[runner:$L] Re-stage it by renaming back to *.md once the cause is fixed."
        echo "[runner:$L] ***************************************************************"
      else
        mv "$RUN" "$Q"
        echo "[runner:$L] FAILED rc=$RC $(basename "$Q") — re-queued, attempt $N/$MAX_FAILS, log $(basename "$LOG")"
        sleep "$RETRY_BACKOFF"
      fi
    fi
    TOOK=1
  done
  if [ "$TOOK" -eq 1 ]; then
    IDLE=0
  else
    # Nothing queued anywhere: try to restock each lane from its own program file
    # before going to sleep. maybe_restock returns 0 only when it actually wrote
    # one; if any did, loop straight back round and TAKE it rather than sleeping
    # a minute first — the whole point is that the lane does not wait.
    WROTE=0
    if [ $((IDLE % 5)) -eq 0 ]; then RESTOCK_QUIET=0; else RESTOCK_QUIET=1; fi
    # Reap BEFORE restocking. An orphaned marker is exactly what makes
    # `inbox_running` non-zero, so guard 1 refuses to restock while one is
    # sitting there — retiring it first is what turns "idle forever" back into
    # "empty inbox, write your own next directive". Not throttled by
    # RESTOCK_QUIET: it only speaks when it actually retires something, which is
    # rare and always worth a line in the window.
    for L in "${LANES[@]}"; do reap_stale_running "$L"; done
    for L in "${LANES[@]}"; do maybe_restock "$L" && WROTE=1; done
    if [ "$WROTE" -eq 1 ]; then IDLE=0; continue; fi
    # Legible silence: say we're idle, immediately and then every ~5 minutes,
    # so an empty window always distinguishes "no work queued" from "stuck".
    [ $((IDLE % 5)) -eq 0 ] && echo "[runner] idle - no queued work in: ${LANES[*]}  ($(date '+%H:%M:%S'))"
    IDLE=$((IDLE + 1))
    sleep "$IDLE_SLEEP"
  fi
done
