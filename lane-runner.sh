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
# session on it, logs everything, marks it consumed, loops. Kill anytime with
# Ctrl-C; in-flight session state lives in handoff files per standing doctrine,
# so killing the runner never loses work.
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
        2>&1 | python3 -u -c "$FMT" | tee -a "$LOG" )
    RC=${PIPESTATUS[0]:-$?}
    mv "$RUN" "${Q%.md}.consumed-$TS"   # no .md suffix — must never re-match the queue glob
    echo "[runner:$L] done rc=$RC $(basename "$Q")"
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
