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
mkdir -p "$LOGDIR"

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
for L in "${LANES[@]}"; do
  mkdir -p "$HANDOFF/runner-inbox/$L"
  # Crash recovery: a .running file means a prior runner died mid-session
  # (reboot, closed laptop). Re-queue it — directives are self-gated, so
  # re-running is always safe.
  # Skipped under --dry-run: this RENAMES files, and a rehearsal that re-queues
  # a live lane's in-flight directive is not a rehearsal.
  [ "$DRYRUN" -eq 1 ] && continue
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
  for L in "${LANES[@]}"; do maybe_restock "$L"; done
  exit 0
fi

# --restock-once: do ONE real restock pass and exit without running any session.
# Two uses: Fable can nudge an idle lane without starting a runner, and the guard
# test can exercise the WRITE path — --dry-run alone only ever proves the branch
# that writes nothing, which is not the branch that runs in production.
if [ "$RESTOCK_ONCE" -eq 1 ]; then
  echo "[runner] --restock-once: one real restock pass, no session will be started"
  RC=1
  for L in "${LANES[@]}"; do maybe_restock "$L" && RC=0; done
  exit "$RC"
fi

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
    echo "[runner:$L] $TS taking $(basename "$Q") → log $(basename "$LOG")"
    # Fresh headless session per queue. Timeout guards a hung session; state is
    # in handoff files, so a killed session resumes via its own report + re-stage.
    ( timeout "$SESSION_TIMEOUT" claude --dangerously-skip-permissions --verbose \
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
    for L in "${LANES[@]}"; do maybe_restock "$L" && WROTE=1; done
    if [ "$WROTE" -eq 1 ]; then IDLE=0; continue; fi
    # Legible silence: say we're idle, immediately and then every ~5 minutes,
    # so an empty window always distinguishes "no work queued" from "stuck".
    [ $((IDLE % 5)) -eq 0 ] && echo "[runner] idle - no queued work in: ${LANES[*]}  ($(date '+%H:%M:%S'))"
    IDLE=$((IDLE + 1))
    sleep 60
  fi
done
