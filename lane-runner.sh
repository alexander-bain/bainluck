#!/bin/bash
# lane-runner.sh — Bain Luck autonomous lane runner (Fable, 2026-08-26; adopted by Alex ruling)
#
# Usage:  ./lane-runner.sh <workdir> <lane> [lane2 ...]
#   One runner per WORKTREE. Multiple lane names = serialized service of multiple
#   inboxes from one tree (e.g. lane1 + integrator share ~/bainluck and must never
#   run concurrently there).
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

WORKDIR="${1:?usage: lane-runner.sh <workdir> <lane> [lane2 ...]}"
shift
LANES=("$@")
[ ${#LANES[@]} -ge 1 ] || { echo "need at least one lane name"; exit 1; }

HANDOFF="$HOME/bainluck/.claude/handoff"
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
        --output-format stream-json -p "$(cat "$RUN")" \
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
    # Legible silence: say we're idle, immediately and then every ~5 minutes,
    # so an empty window always distinguishes "no work queued" from "stuck".
    [ $((IDLE % 5)) -eq 0 ] && echo "[runner] idle - no queued work in: ${LANES[*]}  ($(date '+%H:%M:%S'))"
    IDLE=$((IDLE + 1))
    sleep 60
  fi
done
