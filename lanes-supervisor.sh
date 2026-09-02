#!/bin/bash
# lanes-supervisor.sh — keeps every lane runner alive. Run once in its own Terminal:
#   caffeinate -i ~/bainluck/lanes-supervisor.sh
# Every 5 minutes: for each lane, if no lane-runner.sh process is serving it, relaunch it
# in a new Terminal window (same launch as start-lanes.sh). Ctrl-C to stop the supervisor
# (lanes keep running). Duplicates are harmless: runners take queues atomically.
set -u
R="$HOME/bainluck/lane-runner.sh"
# bash-3.2 safe (macOS /bin/bash has no associative arrays): lane -> dir / args via case.
lane_dir () { case "$1" in integrator) echo "$HOME/bainluck";; *) echo "$HOME/bainluck-dev/$1";; esac; }
lane_args () { case "$1" in integrator) echo "integrator lane1";; *) echo "$1";; esac; }
launch () { osascript -e "tell application \"Terminal\" to do script \"$1\"" >/dev/null; }
while true; do
  for L in integrator ux latency calibration live; do
    D="$(lane_dir "$L")"; A="$(lane_args "$L")"; [ -d "$D" ] || continue
    if ! pgrep -f "lane-runner.sh $D $A" >/dev/null 2>&1; then
      echo "[supervisor] $(date '+%H:%M:%S') lane '$L' has no runner — relaunching"
      launch "$R $D $A"
    fi
  done
  # lane4 cert bus. The pattern is a REGEX and `.` matches any character, so the
  # dot is escaped: an unescaped "lane4-runner.sh" still fails to match a running
  # "lane4-runner-v3.sh" (different infix, not a one-char difference), which is how
  # this supervisor could relaunch the canonical runner alongside a live scratch
  # version and end up with two cert buses. Scratch versions are not tracked; if one
  # is running, stop it rather than teaching this pattern to accept it.
  if ! pgrep -f "lane4-runner\.sh" >/dev/null 2>&1; then
    echo "[supervisor] $(date '+%H:%M:%S') lane4 runner missing — relaunching"; launch "$HOME/bainluck/lane4-runner.sh"
  fi
  sleep 300
done
