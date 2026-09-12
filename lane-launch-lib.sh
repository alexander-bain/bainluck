#!/bin/bash
# lane-launch-lib.sh — the code both launchers share. Sourced by start-lanes.sh
# and lanes-supervisor.sh; never run on its own.
#
# WHY IT IS NOT IN lanes.conf: that file is the TOPOLOGY (which lanes exist,
# which worktree each uses, how many graders). The launcher tests synthesize a
# lanes.conf to drive each script against a roster of their own — so a function
# living there would have to be copied into every synthetic conf, which is the
# drift lanes.conf exists to prevent, wearing a different hat.
#
# WHY IT IS NOT IN EITHER LAUNCHER: it was, in lanes-supervisor.sh, until
# 2026-09-10 — and then start-lanes.sh needed the same answer for the
# measurement bus. The matcher below has four non-obvious rules compressed into
# one line; a second hand-written copy would lose at least one of them.

# How many processes are running EXACTLY this command line? ($1 = full argv)
# A WHOLE-LINE match against a ps snapshot, and every word of that matters:
#
#  1. NOT pgrep: pgrep EXCLUDES ITS OWN ANCESTORS. Run a launcher from a lane's
#     Terminal window and pgrep cannot see that lane's runner, so it reports
#     "no runner" and opens a duplicate window — every 5 minutes forever, in the
#     supervisor's case. Observed 9/3 the first time --dry-run was run from the
#     integrator window.
#  2. NOT `ps | grep pattern`: that catches GREP ITSELF — grep's argv holds the
#     pattern and grep is alive while ps walks the table. Snapshot first, match
#     after, and the matcher is never in the data.
#  3. WHOLE LINE, not substring: any unrelated process that merely mentions the
#     path — an editor, another agent's shell, a heredoc — inflates a substring
#     count, and an inflated count means a DEAD grader is never relaunched.
#     That is the unsafe direction, so the match is anchored at both ends.
#     (Measured while testing: a substring count read "3 of 5" graders when two
#     were running, because the testing shell's own argv quoted the path.)
#     A whole-line match also means "lane4-runner-v3.sh" is correctly NOT
#     counted: scratch versions are a DIFFERENT cert bus, and the fix for one
#     running is to stop it, never to teach this to accept it.
#  4. `-ww`: without it macOS truncates argv to the terminal width and every
#     lane under a narrow window reads as missing.
#
# Terminal's `do script` runs the command under bash, so the live argv is
# "/bin/bash <path> [args]"; a hand-run script is just "<path> [args]". Both count.
#
# LAUNCH_PS_SNAP, not PS_SNAP: the supervisor takes ONE snapshot per pass and
# lets every call in that pass share it, but start-lanes.sh already has a
# `PS_SNAP` of its own in a DIFFERENT ps format (the orphan reap's
# pid/ppid/pgid/command). Sharing the name there would silently anchor
# `^/bin/bash …$` against lines that begin with a pid — never matching, so every
# count reads 0 and every guard built on it opens a duplicate. A caller that does
# not set LAUNCH_PS_SNAP gets its own fresh snapshot, which is what a one-shot
# guard wants anyway.
#
# Always prints a number: `grep -c` exits 1 on no match, and both callers compare
# the result with `[ ... -lt ]` / `[ ... -gt ]`, which is an error on empty.
count_running () {
  printf '%s\n' "${LAUNCH_PS_SNAP:-$(ps -axww -o command= 2>/dev/null)}" \
    | grep -c -e "^/bin/bash $1\$" -e "^$1\$"
}

# --- The measurement-bus start claim (#4956) --------------------------------
#
# WHAT IT FIXES, AND WHY THE OBVIOUS FIX DOES NOT. #4941 guarded the bus launch
# on `count_running`, which is check-then-act: two start-lanes.sh runs can both
# read 0 and both launch. The issue proposed a mutex around the check and the
# launch. That is INERT here, and the reason is `launch`:
#
#   osascript -e 'tell application "Terminal" to do script "…"'
#
# returns as soon as Terminal has been TOLD. Terminal then opens a window, the
# window starts a shell, and the shell execs the runner. Only at that last step
# does the bus appear in the `ps` snapshot `count_running` reads. So the interval
# in which a second invocation reads 0 does not end when `launch` returns — it
# ends when the bus becomes VISIBLE, which is strictly later and is not bounded
# by anything this script controls. A mutex released after `launch` covers the
# short half of the window and leaves the long half open.
#
# The existing test already carries the evidence: the synthetic bus in
# `test_start_lanes_does_not_open_a_SECOND_measurement_bus` is started with
# `subprocess.Popen` and then slept on for 0.5s before the launcher runs, because
# a just-started process is not immediately matchable. Terminal's path to `exec`
# is longer than Popen's, not shorter.
#
# So the claim must OUTLIVE the launch: take it, check, launch, then keep holding
# until the new bus is visible or a bounded wait expires. A caller that cannot
# take the claim SKIPS — it never waits, because the only thing it would be
# waiting for is permission to do nothing.
#
# `mkdir` and not `flock`: `flock(1)` is not installed on macOS, which is where
# the fleet runs. `mkdir` is atomic on every filesystem we use and needs nothing.
# Not `scripts/claim_lane_lock.py` either — that would couple the launcher to the
# lane-lock semantics, including #4104, to save four lines of `kill -0`.
#
# 🔴 IT FAILS OPEN, DELIBERATELY. If the claim cannot be taken for any reason
# other than "another live invocation holds it" — a read-only tree, a full disk,
# a missing parent directory (CI has no ~/bainluck) — this returns SUCCESS and
# the caller proceeds unguarded. A guard that failed closed would turn a
# duplicate-bus nuisance into a fleet that boots with NO bus at all, and nobody
# is watching at the hour that would happen. Duplicate bus: recoverable, visible
# in runner-logs. No bus: a silent hole in the M-R record, which is the failure
# #4941 was filed for in the first place.
#
# Staleness is decided by the PID-ALIVE TEST AND NOTHING ELSE (ruling 008): a
# holder killed mid-launch must not make the bus permanently unstartable, and an
# mtime is not evidence about a process. A claim directory with no readable pid
# is treated as stale for the same reason — it means the holder died between
# `mkdir` and the pid write.

# Take the bus-start claim. 0 = held by us (or failed open: proceed), 1 = another
# LIVE invocation holds it and this caller must skip.  $1 = claim directory.
claim_bus_start () {
  _cbs_dir="$1"
  if mkdir "$_cbs_dir" 2>/dev/null; then
    echo $$ > "$_cbs_dir/pid" 2>/dev/null
    return 0
  fi
  # mkdir failed. Only ONE of the reasons is a live holder.
  [ -d "$_cbs_dir" ] || return 0            # fail open: unwritable/missing parent
  _cbs_pid=$(tr -cd '0-9' < "$_cbs_dir/pid" 2>/dev/null)
  if [ -n "$_cbs_pid" ] && kill -0 "$_cbs_pid" 2>/dev/null; then
    return 1                                 # a live start-lanes.sh is mid-launch
  fi
  # Stale: the holder is gone (or never got as far as writing its pid).
  rm -rf "$_cbs_dir" 2>/dev/null
  mkdir "$_cbs_dir" 2>/dev/null && echo $$ > "$_cbs_dir/pid" 2>/dev/null
  return 0                                   # fail open even if the retry lost
}

release_bus_start () {
  [ -n "${1:-}" ] && rm -rf "$1" 2>/dev/null
  return 0
}

# Hold the claim until the just-launched bus is MATCHABLE, or the wait expires.
# $1 = the runner argv count_running matches, $2 = max seconds.
#
# Always returns 0: a bus that has not appeared within the wait is not a reason to
# fail the launcher — every other window is already open by this point, and the
# caller's next act is to release the claim either way. The bound exists so a bus
# that never starts cannot wedge the claim (and with it every future run) for ever.
hold_until_bus_visible () {
  _hub_i=0
  while [ "$_hub_i" -lt "$2" ]; do
    [ "$(count_running "$1")" -gt 0 ] && return 0
    sleep 1
    _hub_i=$((_hub_i + 1))
  done
  return 0
}
