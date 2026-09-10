#!/bin/bash
# lanes-supervisor.sh — keeps every lane runner alive. Run once in its own Terminal:
#   caffeinate -i ~/bainluck/lanes-supervisor.sh
# Every 5 minutes: for each lane, if no lane-runner.sh process is serving it, relaunch it
# in a new Terminal window (same launch as start-lanes.sh). Ctrl-C to stop the supervisor
# (lanes keep running). Duplicates are harmless: runners take queues atomically.
#
#   --dry-run   run ONE pass, print what would be relaunched, relaunch nothing, exit.
#
# The lane list and worktree mapping are NOT here. They live in lanes.conf, which
# start-lanes.sh sources too — this file and that one carried separate copies until
# 2026-09-03 and drifted six lanes against seven against nine actual.
set -u
# Next to this script first, $HOME as fallback, LANES_CONF overrides both — see
# the same block in start-lanes.sh for why.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="${LANES_CONF:-$SELF_DIR/lanes.conf}"
[ -f "$CONF" ] || CONF="$HOME/bainluck/lanes.conf"
[ -f "$CONF" ] || { echo "missing $CONF — cannot know which lanes to supervise"; exit 1; }
. "$CONF"
R="$LANE_RUNNER"

# The shared launcher code (`count_running`). A tracked sibling, found the same
# way lanes.conf is and for the same reason. Not in lanes.conf: that file is the
# topology, and the tests synthesize one.
LIB="${LAUNCH_LIB:-$SELF_DIR/lane-launch-lib.sh}"
[ -f "$LIB" ] || LIB="$HOME/bainluck/lane-launch-lib.sh"
[ -f "$LIB" ] || { echo "missing $LIB — the shared launcher library"; exit 1; }
. "$LIB"

DRYRUN=0
[ "${1:-}" = "--dry-run" ] && DRYRUN=1

launch () {
  if [ "$DRYRUN" -eq 1 ]; then echo "[dry-run] would relaunch: $1"; return 0; fi
  osascript -e "tell application \"Terminal\" to do script \"$1\"" >/dev/null
}

# `count_running` — how many processes are running EXACTLY this command line —
# now lives in lane-launch-lib.sh, sourced above, because start-lanes.sh needs
# the same answer for the measurement bus and a second copy of a matcher is the
# drift this whole arrangement exists to prevent. The reasoning (why not pgrep,
# why not `ps | grep`, why whole-line, why -ww) is beside it there.
#
# One snapshot per pass, shared by every call in it via LAUNCH_PS_SNAP.

while true; do
  LAUNCH_PS_SNAP=$(ps -axww -o command= 2>/dev/null)
  for L in $LANES_ALL; do
    D="$(lane_dir "$L")"; [ -d "$D" ] || continue
    # One runner per lane, one lane per runner (9/3): the argv is exactly the one
    # start-lanes.sh launches. It must stay in step with that script, which is
    # why both take the lane list from lanes.conf.
    if [ "$(count_running "$R $D $L")" -eq 0 ]; then
      echo "[supervisor] $(date '+%H:%M:%S') lane '$L' has no runner — relaunching"
      launch "$R $D $L"
    fi
  done
  # lane4 cert bus — LANE4_GRADERS of them, all running the same script, so this
  # counts instances rather than asking "is one alive". Counting is the point: a
  # single surviving grader looks healthy to a presence check while the bus runs
  # at half rate, which is how one grader can sit dead for a day unnoticed.
  #
  # A whole-line match also means "lane4-runner-v3.sh" is correctly NOT counted:
  # scratch versions are a DIFFERENT cert bus, and the fix for one running is to
  # stop it, never to teach this to accept it.
  ALIVE=$(count_running "$LANE4_RUNNER")
  if [ "${ALIVE:-0}" -lt "$LANE4_GRADERS" ]; then
    echo "[supervisor] $(date '+%H:%M:%S') lane4 graders: $ALIVE of $LANE4_GRADERS — relaunching $((LANE4_GRADERS - ALIVE))"
    G="$ALIVE"
    while [ "$G" -lt "$LANE4_GRADERS" ]; do launch "$LANE4_RUNNER"; G=$((G + 1)); done
  fi
  # The measurement bus — exactly one (lanes.conf). Supervised for the same
  # reason the graders are, and it matters more over a weekend than on a weekday:
  # the bus is the instrument the heartbeats read, so a bus that dies unattended
  # on Saturday is a hole in the record nobody notices until Monday. Guarded on
  # existence so an older checkout without the script supervises everything else
  # normally instead of looping on a relaunch that cannot work.
  if [ -n "${BUS_RUNNER:-}" ] && [ -f "$BUS_RUNNER" ]; then
    if [ "$(count_running "$BUS_RUNNER")" -eq 0 ]; then
      echo "[supervisor] $(date '+%H:%M:%S') measurement bus is not running — relaunching"
      launch "$BUS_RUNNER"
    fi
  fi
  [ "$DRYRUN" -eq 1 ] && { echo "[dry-run] one pass done, exiting"; exit 0; }
  sleep 300
done
