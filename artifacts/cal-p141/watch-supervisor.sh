#!/bin/bash
# CAL-P141 — keep exactly one re-baseline watcher alive for the whole window.
#
# WHY THIS EXISTS, and why it is not just "restart it first thing":
# CAL-P140's watcher did NOT die with its session — it orphaned to init (PPID 1)
# and was still polling at 06:34Z, 45 minutes after its session ended. Blindly
# restarting would have put a SECOND writer on an append-only log whose only
# de-dup is "have I already logged beat n?", evaluated at poll time. Two watchers
# waking inside the same 7-minute poll both see beat n unlogged and both append
# it. The log is the half of the window that survives the session; corrupting it
# to satisfy a "restart it first thing" instruction is the worse failure.
#
# So: never start a second one. Only replace a dead one. The pattern below is
# matched against argv, which carries the relative script path (the invocation
# is `python3 artifacts/cal-p140/rebaseline.py ...`), so pgrep -f finds it even
# though argv has no cwd.
set -u

REPO=/Users/bain/bainluck-dev/calibration
PATTERN="rebaseline.py --baseline-at"
BASELINE=2026-08-29T23:35:53Z
LOG=artifacts/cal-p140/window-log.jsonl
WATCHLOG=artifacts/cal-p140/watch.log
SUPLOG=$REPO/artifacts/cal-p141/supervisor.log

cd "$REPO" || exit 1

while true; do
    if ! pgrep -f "$PATTERN" > /dev/null 2>&1; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] watcher ABSENT — restarting" >> "$SUPLOG"
        nohup python3 -u artifacts/cal-p140/rebaseline.py \
            --baseline-at "$BASELINE" --watch --log "$LOG" --interval 420 \
            >> "$WATCHLOG" 2>&1 &
        sleep 5
        if pgrep -f "$PATTERN" > /dev/null 2>&1; then
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] restarted, pid $(pgrep -f "$PATTERN" | tr '\n' ' ')" >> "$SUPLOG"
        else
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] 🔴 RESTART FAILED" >> "$SUPLOG"
        fi
    fi
    sleep 60
done
