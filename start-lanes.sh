#!/bin/bash
# start-lanes.sh — open every lane runner in its own macOS Terminal window.
# Run after any reboot, or anytime:   ~/bainluck/start-lanes.sh
# Each lane gets a visible window streaming its work live.
# Stop a lane: Ctrl-C in its window (always safe — state lives in files;
# interrupted queues re-queue automatically on next start).

set -u
R="$HOME/bainluck/lane-runner.sh"
[ -x "$R" ] || chmod +x "$R"

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
