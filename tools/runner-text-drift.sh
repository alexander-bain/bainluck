#!/bin/bash
# Is each long-running launcher executing the tooling that is on disk? (#4777)
#
# WHY THIS EXISTS, AND WHY IT CANNOT LIVE INSIDE lane-runner.sh
# -------------------------------------------------------------
# Bash reads a compound command into memory in full before executing it. The lane
# runner's body is one `while true; do … done`, so a runner executes the AST it
# parsed at process start, forever: rewriting the file on disk changes nothing for
# a runner that is already looping, and there is no `exec "$0"` refresh.
#
# On 2026-09-10 that cost us a whole ship. Notice 39 rung 2 (the lane-attribution
# export) merged at 11:19Z into a file that ten runners — all started Wed 12:43pm
# PT, ~13h before the code was written — will never re-read. Every gate was green.
# Nothing was tagged. It was the third such ship in a week (#4632 inert four days,
# #4685 stale checkout, then this).
#
# `lane-runner.sh` already carries a staleness guard, and it could not see this:
# `bl_warn_if_runner_is_stale` hashes `git hash-object "$0"` — the bytes ON DISK —
# against master. Those were byte-identical. Disk and master agreed; the running
# process disagreed with both. A file comparison is structurally incapable of
# seeing a process that parsed an earlier version of that file, and any guard
# written INSIDE the runner has the same defect twice over: it also only reaches
# a lane after the restart that would have fixed the problem anyway.
#
# So this check is deliberately OUT OF PROCESS. It asks a question the runner
# cannot ask about itself — "did you start before your own script last changed?" —
# and it answers it today, with no restart, from any lane session or the bus.
#
# THE SAFE DIRECTION IS OVER-REPORTING. A false STALE costs a restart nobody
# needed. A false CURRENT is how a ship sits inert for four days. So a runner
# whose start time and file mtime land in the same second is reported STALE, and
# anything this cannot measure is reported UNKNOWN and counted as a finding —
# never quietly skipped.
#
#   tools/runner-text-drift.sh              # every tracked launcher
#   tools/runner-text-drift.sh --quiet      # print only what needs a restart
#
# Exit: 0 every running launcher is current · 1 at least one is stale or unknown
#       · 2 the check itself could not run. 1 is a RESULT; 2 is a story about the
#       harness (gotcha #124) — the caller is meant to be able to tell them apart.
set -u

PATTERNS=(lane-runner.sh lane4-runner.sh bus-runner.sh lanes-supervisor.sh)
QUIET=0
REF="${BL_CARRIER_REF:-origin/master}"

while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    # Single-pattern mode exists so the guard tests can drive this against a
    # synthetic long-running script instead of the live fleet. A test that had to
    # start a real lane runner would not be a test.
    --pattern) [ $# -ge 2 ] || { echo "runner-text-drift: --pattern needs a value" >&2; exit 2; }
               PATTERNS=("$2"); shift 2 ;;
    --ref) [ $# -ge 2 ] || { echo "runner-text-drift: --ref needs a value" >&2; exit 2; }
           REF="$2"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "runner-text-drift: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

# 🔴 EVERY BSD/GNU PROBE GOES THROUGH THIS. The obvious dialect chain —
#
#     stat -f %m "$1" 2>/dev/null && return 0    # BSD
#     stat -c %Y "$1" 2>/dev/null && return 0    # GNU
#
# is broken, and it broke this tool on Linux for three CI runs while every arm
# passed on macOS. GNU `stat -f` is not "unknown flag", it is *filesystem status*:
# it PRINTS a multi-line block about the filesystem, then exits non-zero because
# `%m` was taken as a filename. The `&&` correctly declines to return, but the
# block has already gone to stdout, so `mtime=$(file_mtime_epoch …)` captures the
# garbage AND the real answer. `[ "$mtime" -ge "$start" ]` then errors on a
# non-integer, the `if` takes its else branch, and every launcher on Linux reports
# **current** — a false CLEAN fleet, silently, in the one direction that matters.
#
# So: capture, then accept ONLY a pure integer. A probe that fails is not allowed
# to contribute a single byte to the answer.
first_integer_of() {
  local out
  while [ $# -gt 0 ]; do
    out=$(eval "$1" 2>/dev/null)
    case "$out" in
      "" | *[!0-9]* ) ;;                 # empty, or carries anything non-digit
      * ) printf '%s\n' "$out"; return 0 ;;
    esac
    shift
  done
  return 1
}

# Epoch of a process's start. `ps -o etimes=` would be one call, but it is
# procps-only and this machine's BSD ps rejects it, so parse lstart and accept
# either date dialect — the guard tests run on Linux CI, the fleet runs on macOS.
pid_start_epoch() {
  local ls
  # `-ww` on every ps read, without exception. lstart is a short fixed-width field
  # so it is not at risk today, but the rule is cheaper to keep than to re-derive
  # per call site — and the two places that skipped it both shipped a bug.
  ls=$(ps -ww -o lstart= -p "$1" 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  [ -n "$ls" ] || return 1
  BL_LS="$ls" first_integer_of \
    'date -j -f "%a %b %d %T %Y" "$BL_LS" +%s' \
    'date -d "$BL_LS" +%s'
}

file_mtime_epoch() {
  BL_F="$1" first_integer_of 'stat -f %m "$BL_F"' 'stat -c %Y "$BL_F"'
}

# The script a process is running, taken from its own argv rather than guessed
# from the pattern: two checkouts can hold the same filename, and the whole point
# of this tool is to be exact about WHICH file the process is behind.
pid_script_path() {
  # `-ww` for the same reason as the snapshot below: without it procps truncates
  # the command to 80 columns when stdout is not a terminal, so a launcher under a
  # long path resolves to no script at all. Measured in CI, where the runner's own
  # path pushed the script name past the cut and every live-process arm reported
  # UNKNOWN. Safe direction (UNKNOWN is counted as a finding, not skipped) but wrong.
  ps -ww -o command= -p "$1" 2>/dev/null | tr ' ' '\n' | grep -m1 -- "/$2\$"
}

matched_pids() {
  # 🔴 NOT `pgrep -f`. Measured while building this: `pgrep -f lane-runner.sh` run
  # from inside a lane session returns every lane's runner EXCEPT that lane's own,
  # because macOS pgrep excludes "the current pgrep or pkill process and all of its
  # ancestors" by default (man pgrep, -a). A lane's runner is its session's
  # ancestor, so the one tool most likely to be run from a lane session was blind
  # to precisely the lane asking — the same shape as the bug this file exists for.
  # `-a` lifts it on BSD but means "print the full command line" on Linux/procps,
  # so it is not portable and the guard tests run on Linux CI.
  #
  # A `ps | grep <pattern>` pipeline has the opposite failure (the grep child's own
  # argv contains the pattern and matches itself), so the filtering happens in-shell
  # against one snapshot instead. Echoes "pid ppid" per match.
  local pat="$1" pid ppid rest
  while read -r pid ppid rest; do
    [ "$pid" = "$$" ] && continue
    case " $rest " in *"/$pat "*) echo "$pid $ppid" ;; esac
  done <<< "$PS_SNAP"
}

STALE=0; UNKNOWN=0; CURRENT=0; ROWS=""

# One snapshot, read before anything else forks: taking it per pattern would let
# the process table change between patterns and report a pid that has since gone.
PS_SNAP=$(ps -axww -o pid=,ppid=,command= 2>/dev/null)
# 🔴 An unreadable process table must NEVER reach the "nothing to check" exit.
# If `ps` fails or is throttled, PS_SNAP is empty, every pattern matches nothing,
# and the tool cheerfully reports a clean fleet at exit 0 — a false CURRENT, the
# one direction this whole file exists to prevent. Any machine running this has
# hundreds of processes, so a handful of lines is not a small answer, it is a
# broken read: exit 2 (the check could not run), never 0.
if [ "$(printf '%s\n' "$PS_SNAP" | grep -c .)" -lt 10 ]; then
  echo "runner-text-drift: could not read the process table (ps returned nothing usable) — NOT reporting a clean fleet" >&2
  exit 2
fi

for pat in "${PATTERNS[@]}"; do
  matches=$(matched_pids "$pat")
  [ -n "$matches" ] || continue
  pids=$(printf '%s\n' "$matches" | awk '{print $1}')

  while read -r pid ppid; do
    [ -n "$pid" ] || continue
    # A lane's session subshell is a fork of its runner and shares argv, so it
    # reports the same staleness twice. It also shares the parsed AST — forking
    # copies memory — so the parent's verdict already covers it. Skip children
    # whose parent is in the same matched set.
    if [ -n "$ppid" ] && printf '%s\n' "$pids" | grep -q -x "$ppid"; then continue; fi

    script=$(pid_script_path "$pid" "$pat")
    start=$(pid_start_epoch "$pid")
    label="pid $pid  $pat"

    if [ -z "$script" ] || [ ! -f "$script" ]; then
      ROWS="$ROWS
UNKNOWN  $label  — cannot resolve the script it is running"
      UNKNOWN=$((UNKNOWN+1)); continue
    fi
    mtime=$(file_mtime_epoch "$script")
    if [ -z "$start" ] || [ -z "$mtime" ]; then
      ROWS="$ROWS
UNKNOWN  $label  — cannot read start time or file mtime"
      UNKNOWN=$((UNKNOWN+1)); continue
    fi

    # Same-second is ambiguous, so it counts as stale (see "safe direction").
    if [ "$mtime" -ge "$start" ]; then
      age=$(( (mtime - start) / 60 ))
      # Distinguish the two repairs: if the file on disk already matches the
      # committed one, a restart is the whole fix; if it does not, the checkout
      # is behind too (#4685) and a restart alone would load the wrong text.
      repo=$(cd "$(dirname "$script")" && git rev-parse --show-toplevel 2>/dev/null)
      hint="restart it"
      if [ -n "$repo" ]; then
        live=$(git -C "$repo" hash-object "$script" 2>/dev/null)
        head=$(git -C "$repo" rev-parse --verify -q "$REF:$(basename "$script")" 2>/dev/null)
        if [ -n "$live" ] && [ -n "$head" ] && [ "$live" != "$head" ]; then
          hint="the CHECKOUT is behind $REF too — update it, THEN restart"
        fi
      fi
      ROWS="$ROWS
STALE    $label  — started ${age}m before $(basename "$script") last changed; $hint"
      STALE=$((STALE+1))
    else
      ROWS="$ROWS
current  $label  — $(basename "$script") unchanged since it started"
      CURRENT=$((CURRENT+1))
    fi
    # A here-string, NOT a pipe: `printf … | while read` runs the loop in a
    # subshell, so every count above would be discarded at `done` and the tool
    # would report "0 current, 0 stale" however many runners it just examined.
  done <<< "$matches"
done

TOTAL=$((STALE + UNKNOWN + CURRENT))
if [ "$TOTAL" -eq 0 ]; then
  # No launcher running is the normal state in CI and on a laptop between
  # sessions. Say so out loud: silence here must not read as "all current".
  echo "runner-text-drift: no launcher processes running — nothing to check"
  exit 0
fi

if [ "$QUIET" -eq 1 ]; then
  printf '%s\n' "$ROWS" | grep -E '^(STALE|UNKNOWN)' || true
else
  printf '%s\n' "$ROWS" | sed '/^$/d'
fi

echo "runner-text-drift: $CURRENT current, $STALE stale, $UNKNOWN unknown"
[ $((STALE + UNKNOWN)) -eq 0 ] || exit 1
exit 0
