#!/bin/bash
# stage-cert.sh — append a correctly-formed cert block with an atomic, verified-unused id.
# usage: stage-cert.sh <SUBJECT-SLUG> <lane> <branch> <sha> <pr-url> <issue> [<repairs CERT-N>] < body.md
set -u
Q="$HOME/bainluck/.claude/handoff/CERT-QUEUE.md"; LOG="$HOME/bainluck/.claude/handoff/CODEX-CERT-LOG.md"
SUBJ="$1"; LANE="$2"; BR="$3"; SHA="$4"; PR="$5"; ISSUE="$6"; REPAIRS="${7:-}"
LOCK="$Q.lock"; exec 9>"$LOCK"; flock 9 2>/dev/null || true
# The id scan must not match a DIFFERENT id space that merely ends in "CERT-N".
# CERT-QUEUE.md:23965 carries the prose "C-CERT-1852 finding 5", which the bare
# `CERT-[0-9]+` pattern read as CERT-1852 and which pushed the next id to 1853
# (CERT-1853, staged 2026-09-05 09:35Z, is that bug wearing a four-digit number).
# So require a non-word, non-hyphen character before the C — start of line, a
# space, a backtick, a bracket, a pipe. `[^-[:alnum:]_]` excludes the hyphen that
# makes "C-CERT-" a different name, and `(^|...)` keeps a heading line matching.
MAX=$( { grep -oE '(^|[^-[:alnum:]_])CERT-[0-9]+' "$Q" "$LOG" 2>/dev/null | sed 's/.*CERT-//'; echo 0; } | sort -n | tail -1 )
ID=$((MAX+1))
{
  printf '\n# CERT-%s -- %s\n\nqueue_id: %s\nstatus: staged\n' "$ID" "$SUBJ" "$SUBJ"
  [ -n "$REPAIRS" ] && printf 'repairs: %s   # REPAIRS GRADE FIRST (standing notice 8b)\n' "$REPAIRS"
  printf 'lane: %s\nissue: %s\npr: %s\nbranch: %s\nsha: %s\n\n' "$LANE" "$ISSUE" "$PR" "$BR" "$SHA"
  cat
} >> "$Q"
echo "CERT-$ID"
