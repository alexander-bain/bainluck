#!/bin/bash
# start-lanes.sh — open every lane runner in its own macOS Terminal window.
# Run after any reboot, or anytime:   ~/bainluck/start-lanes.sh
# Each lane gets a visible window streaming its work live.
# Stop a lane: Ctrl-C in its window (always safe — state lives in files;
# interrupted queues re-queue automatically on next start).

#
# --dry-run: print the windows this WOULD open (and skip the orphan reap
# entirely — the reap kills processes and has no business running in a rehearsal).
# Use it to check the lane list without opening a dozen Terminal windows.

set -u
# The lane list, the worktree mapping and the runner paths live in ONE file,
# sourced by this script and by lanes-supervisor.sh. See lanes.conf for why.
# Found NEXT TO THIS SCRIPT first: lanes.conf is a tracked sibling, so any
# checkout of the repo is self-contained (CI has no ~/bainluck, and neither does
# a throwaway worktree). $HOME is the fallback for a copy of this script that got
# separated from its conf. LANES_CONF overrides both.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="${LANES_CONF:-$SELF_DIR/lanes.conf}"
[ -f "$CONF" ] || CONF="$HOME/bainluck/lanes.conf"
[ -f "$CONF" ] || { echo "missing $CONF — cannot know which lanes to start"; exit 1; }
. "$CONF"
R="$LANE_RUNNER"
[ -x "$R" ] || chmod +x "$R"

DRYRUN=0
[ "${1:-}" = "--dry-run" ] && DRYRUN=1

# Reap orphaned headless sessions before launching — but only Bain Luck ones.
# A runner killed by Ctrl-C or a closed window can leave its claude session alive
# under launchd (ppid 1), invisibly editing a worktree and colliding with fresh
# runner sessions. Directives are self-gated, so reaping mid-work is always safe.
#
# An orphan is killed only if it is (a) orphaned — ppid 1, (b) a headless claude
# session, AND (c) demonstrably ours by ONE of two independent ownership signals:
#
#   pgid  — lane-runner.sh records its process group in runner-pids/. A session
#           inherits its runner's pgid, and re-parenting to launchd changes ppid
#           but never pgid, so the record survives the runner's own death.
#   cwd   — the process is working inside a Bain Luck tree. This is what catches
#           orphans left by runners that predate the pgid records (right now that
#           is every one of them), and it is why adoption is not a flag day.
#
# Either alone is sufficient and both are narrow; a bare command-line match is
# NOT, and that was the defect: this machine can run headless claude sessions for
# other repos and the old reap killed those too. Anything unmatched is reported,
# never killed — the safe direction here is under-reaping.
PIDDIR="$HOME/bainluck/.claude/handoff/runner-pids"
if [ "$DRYRUN" -eq 1 ]; then
  echo "[dry-run] skipping orphan reap and pgid garbage collection (both kill/delete)"
else
PS_SNAP=$(ps -axo pid=,ppid=,pgid=,command=)
OWNED_PGIDS=$(cat "$PIDDIR"/*.pgid 2>/dev/null | tr -cd '0-9\n' | grep -v '^$' | sort -u | tr '\n' ',')

# pids of every orphaned headless claude session, with its pgid: "pid pgid"
candidates () {
  echo "$PS_SNAP" | awk '$2 == 1 && /claude --dangerously-skip-permissions/ { print $1, $3 }'
}

# Bain Luck roots, resolved with `pwd -P`. lsof reports a process's REAL cwd, so
# comparing against an unresolved prefix silently never matches if any component
# is a symlink — the reap would go quiet instead of wrong, which is worse to spot.
BL_ROOTS=""
for D in "$HOME/bainluck" "$HOME/bainluck-dev"; do
  [ -d "$D" ] && BL_ROOTS="$BL_ROOTS
$(cd "$D" && pwd -P)"
done

# Is $1 (a pid) working inside a Bain Luck tree? lsof, never a ps-grep: the
# command line says nothing about where a session is editing.
in_bainluck_tree () {
  local cwd root oldifs rc=1
  cwd=$(lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
  [ -n "${cwd:-}" ] || return 1
  oldifs=$IFS
  IFS='
'
  for root in $BL_ROOTS; do          # newline-split: a root may contain spaces
    case "$cwd" in "$root"|"$root"/*) rc=0; break;; esac
  done
  IFS=$oldifs
  return "$rc"
}

classify () {   # $1 = "owned" | "unowned"; prints matching pids
  local pid pgid mine
  while read -r pid pgid; do
    [ -n "${pid:-}" ] || continue
    mine=no
    case ",$OWNED_PGIDS," in *",$pgid,"*) mine=yes;; esac
    [ "$mine" = yes ] || { in_bainluck_tree "$pid" && mine=yes; }
    if [ "$mine" = yes ] && [ "$1" = owned ]; then echo "$pid"; fi
    if [ "$mine" = no  ] && [ "$1" = unowned ]; then echo "$pid"; fi
  done <<EOF
$(candidates)
EOF
}

REAP=$(classify owned)
if [ -n "${REAP:-}" ]; then
  echo "Reaping orphaned Bain Luck runner sessions (recorded process group, or cwd in a Bain Luck tree): $(echo $REAP | tr '\n' ' ')"
  kill $REAP 2>/dev/null
  sleep 2
  kill -9 $REAP 2>/dev/null
fi

FOREIGN=$(classify unowned)
if [ -n "${FOREIGN:-}" ]; then
  echo "NOTE: orphaned headless claude sessions that are not ours: $(echo $FOREIGN | tr '\n' ' ')"
  echo "      No runner ownership record and not working in a Bain Luck tree."
  echo "      Left running on purpose — they may belong to another repo or another tool."
  echo "      If one is a stale Bain Luck session, kill it by pid yourself."
fi

# Garbage-collect ownership records whose process group has no live members.
# Re-snapshot: PS_SNAP predates the reap above and would still show killed groups.
LIVE_PGIDS=$(ps -axo pgid= | tr -d ' ' | sort -u)
for F in "$PIDDIR"/*.pgid; do
  [ -e "$F" ] || continue
  P=$(tr -cd '0-9' < "$F")
  if [ -z "$P" ] || ! echo "$LIVE_PGIDS" | grep -qx "$P"; then rm -f "$F"; fi
done
fi   # end of the reap/GC block skipped by --dry-run

launch () {
  if [ "$DRYRUN" -eq 1 ]; then echo "[dry-run] would open Terminal window: $1"; return 0; fi
  osascript -e "tell application \"Terminal\" to do script \"$1\"" >/dev/null
}

# ONE WINDOW PER LANE, 2026-09-03 (Alex). The previous line here was
# `launch "$R $HOME/bainluck integrator lane1"` — one runner serving two inboxes
# from the master tree, because lane1 used to work in ~/bainluck too. lane1 has
# had its own worktree since 9/2, so that pairing was stale: it made lane1 wait
# on the integrator's sessions for no reason, and it is not what the supervisor
# relaunches, so a supervisor restart silently changed the topology.
#
# Lanes are independent now. Each gets its own runner, its own window, and its
# own worktree (the integrator alone works in the master tree). The list and the
# worktree mapping are in lanes.conf so this script and lanes-supervisor.sh
# cannot disagree about which lanes exist.
N=0
for L in $LANES_ALL; do
  D="$(lane_dir "$L")"
  if [ ! -d "$D" ]; then
    # Loud, never silent: a missing worktree is why a lane vanishes after a
    # reboot, and an unopened window looks exactly like a lane with no work.
    echo "SKIPPED lane '$L' — no worktree at $D. Create it, then re-run this script."
    continue
  fi
  launch "$R $D $L"
  N=$((N + 1))
done

# The cert bus: LANE4_GRADERS identical headless graders (lanes.conf).
G=0
while [ "$G" -lt "$LANE4_GRADERS" ]; do
  launch "$LANE4_RUNNER"
  G=$((G + 1))
done

# The measurement bus: ONE window (see lanes.conf for why not two). Tolerated
# missing rather than fatal — an older checkout without the script should still
# bring up every lane and both graders, the same way a missing worktree only
# skips its own lane.
BUS=0
if [ -n "${BUS_RUNNER:-}" ] && [ -f "$BUS_RUNNER" ]; then
  launch "$BUS_RUNNER"
  BUS=1
else
  echo "SKIPPED the measurement bus — no script at ${BUS_RUNNER:-<unset>}."
  echo "  The recurring M-R set will only run when someone drives it by hand."
fi

echo "$((N + LANE4_GRADERS + BUS)) Terminal windows opened — $N lanes, $LANE4_GRADERS cert graders and $BUS measurement bus, streaming live."
echo "Also run the supervisor once, in its own window, so a lane that dies comes back:"
echo "  caffeinate -i ~/bainluck/lanes-supervisor.sh"
echo "If a lane is already running in another window, close the duplicate:"
echo "the runners take queues atomically, so duplicates waste nothing but a window."
