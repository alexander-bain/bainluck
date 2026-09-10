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
