#!/bin/bash
# start-lanes.sh — open every lane runner in its own macOS Terminal window.
# Run after any reboot, or anytime:   ~/bainluck/start-lanes.sh
# Each lane gets a visible window streaming its work live.
# Stop a lane: Ctrl-C in its window (always safe — state lives in files;
# interrupted queues re-queue automatically on next start).

set -u
R="$HOME/bainluck/lane-runner.sh"
[ -x "$R" ] || chmod +x "$R"

# Reap orphaned headless sessions before launching. A runner killed by Ctrl-C or
# a closed window can leave its claude session alive under launchd (ppid 1),
# invisibly editing a worktree and colliding with fresh runner sessions.
# Directives are self-gated, so reaping mid-work is always safe.
ORPHANS=$(ps -axo pid=,ppid=,command= | awk '$2==1 && /claude --dangerously-skip-permissions/ {print $1}')
if [ -n "${ORPHANS:-}" ]; then
  echo "Reaping orphaned claude sessions: $(echo $ORPHANS | tr '\n' ' ')"
  kill $ORPHANS 2>/dev/null
  sleep 2
  kill -9 $ORPHANS 2>/dev/null
fi

launch () {
  osascript -e "tell application \"Terminal\" to do script \"$1\"" >/dev/null
}

launch "$R $HOME/bainluck lane1 integrator"
launch "$R $HOME/bainluck-dev/ux ux"
launch "$R $HOME/bainluck-dev/latency latency"
launch "$R $HOME/bainluck-dev/calibration calibration"

echo "Four Terminal windows opened — one per lane, streaming live."
echo "If a lane is already running in another window, close the duplicate:"
echo "the runners take queues atomically, so duplicates waste nothing but a window."
