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

DRYRUN=0
[ "${1:-}" = "--dry-run" ] && DRYRUN=1

launch () {
  if [ "$DRYRUN" -eq 1 ]; then echo "[dry-run] would relaunch: $1"; return 0; fi
  osascript -e "tell application \"Terminal\" to do script \"$1\"" >/dev/null
}

# How many processes are running EXACTLY this command line? ($1 = full argv, no args)
# A WHOLE-LINE match against a ps snapshot, and every word of that matters:
#
#  1. NOT pgrep: pgrep EXCLUDES ITS OWN ANCESTORS. Run this supervisor from a
#     lane's Terminal window and pgrep cannot see that lane's runner, so it
#     reports "no runner" and opens a duplicate window every 5 minutes forever.
#     Observed 9/3 the first time --dry-run was run from the integrator window.
#  2. NOT `ps | grep pattern`: that catches GREP ITSELF — grep's argv holds the
#     pattern and grep is alive while ps walks the table. Snapshot first, match
#     after, and the matcher is never in the data.
#  3. WHOLE LINE, not substring: any unrelated process that merely mentions the
#     path — an editor, another agent's shell, a heredoc — inflates a substring
#     count, and an inflated count means a DEAD grader is never relaunched.
#     That is the unsafe direction, so the match is anchored at both ends.
#     (Measured while testing: a substring count read "3 of 5" graders when two
#     were running, because the testing shell's own argv quoted the path.)
#  4. `-ww`: without it macOS truncates argv to the terminal width and every
#     lane under a narrow window reads as missing.
#
# Terminal's `do script` runs the command under bash, so the live argv is
# "/bin/bash <path> [args]"; a hand-run script is just "<path> [args]". Both count.
count_running () {
  printf '%s\n' "$PS_SNAP" | grep -c -e "^/bin/bash $1\$" -e "^$1\$"
}

while true; do
  PS_SNAP=$(ps -axww -o command= 2>/dev/null)
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
  [ "$DRYRUN" -eq 1 ] && { echo "[dry-run] one pass done, exiting"; exit 0; }
  sleep 300
done
