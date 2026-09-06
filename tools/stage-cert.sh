#!/bin/bash
# stage-cert.sh — append a correctly-formed cert block with an atomic, verified-unused id.
# usage: stage-cert.sh <SUBJECT-SLUG> <lane> <branch> <sha> <pr-url> <issue> [<repairs CERT-N>] < body.md
set -u
# Overridable so the guards below are testable against a fixture queue; every lane
# and every runner uses the defaults and is unaffected.
Q="${CERT_QUEUE:-$HOME/bainluck/.claude/handoff/CERT-QUEUE.md}"
LOG="${CERT_LOG:-$HOME/bainluck/.claude/handoff/CODEX-CERT-LOG.md}"
SUBJ="$1"; LANE="$2"; BR="$3"; SHA="$4"; PR="$5"; ISSUE="$6"; REPAIRS="${7:-}"
# MUTUAL EXCLUSION, and it must be REAL on this host.
#
# This was `exec 9>"$Q.lock"; flock 9 2>/dev/null || true`, which reads as a lock
# and is not one: macOS ships no `flock`, so `|| true` swallowed the "command not
# found" and every invocation ran the id scan, the duplicate-sha check and the
# append COMPLETELY UNLOCKED. Measured on this host: of 8 isolated parallel trials
# of two same-sha invocations, 3 let BOTH exit 0 and append the same sha under the
# same fresh id. The duplicate-sha guard below cannot see a block that has not been
# written yet, so without a lock it is defeated by the race it exists to prevent.
#
# `mkdir` is the portable atomic test-and-set: it is a single filesystem operation
# that succeeds for exactly one caller and fails with EEXIST for every other, on
# macOS and Linux alike, with no external binary. The lock is held across the id
# scan, the duplicate check AND the append, because those three steps are only
# correct as one unit.
#
# FAIL CLOSED, and DELIBERATELY DO NOT self-heal. Auto-reclaiming a lock whose
# holder looks dead re-introduces the race in a worse form: two waiters can both
# judge the holder dead, and the second one's rmdir then deletes a lock the first
# has already legitimately re-acquired, so two writers proceed believing they are
# exclusive. Instead we wait a bounded time and then refuse, having mutated
# nothing, printing the one command that clears a genuinely orphaned lock. The
# trap releases on every ordinary exit path — including the refusal below and a
# Ctrl-C — so an orphan requires a hard kill, and a human is the right person to
# adjudicate that.
LOCKD="$Q.lockd"
LOCK_WAIT_S="${STAGE_CERT_LOCK_WAIT:-15}"
_LOCK_HELD=""
_release_lock() {
  [ -n "$_LOCK_HELD" ] || return 0
  rm -f "$LOCKD/pid" 2>/dev/null
  rmdir "$LOCKD" 2>/dev/null
}
_deadline=$(( $(date +%s) + LOCK_WAIT_S ))
while :; do
  if mkdir "$LOCKD" 2>/dev/null; then
    _LOCK_HELD=1
    trap _release_lock EXIT INT TERM HUP
    echo $$ > "$LOCKD/pid"
    break
  fi
  if [ "$(date +%s)" -ge "$_deadline" ]; then
    _holder=$(cat "$LOCKD/pid" 2>/dev/null || true)
    {
      echo "stage-cert.sh: REFUSING — could not take the queue lock after ${LOCK_WAIT_S}s."
      echo "  lock: $LOCKD${_holder:+  (held by pid $_holder)}"
      echo
      echo "Another stage is in flight; staging without the lock is how one sha gets"
      echo "two ids. Nothing was written. Retry in a moment — or, if you have"
      echo "confirmed no stage-cert.sh is running, clear the orphaned lock with:"
      echo "        rm -rf '$LOCKD'"
    } >&2
    exit 3
  fi
  sleep 0.1
done
# The id scan must not match a DIFFERENT id space that merely ends in "CERT-N".
# CERT-QUEUE.md:23965 carries the prose "C-CERT-1852 finding 5", which the bare
# `CERT-[0-9]+` pattern read as CERT-1852 and which pushed the next id to 1853
# (CERT-1853, staged 2026-09-05 09:35Z, is that bug wearing a four-digit number).
# So require a non-word, non-hyphen character before the C — start of line, a
# space, a backtick, a bracket, a pipe. `[^-[:alnum:]_]` excludes the hyphen that
# makes "C-CERT-" a different name, and `(^|...)` keeps a heading line matching.
MAX=$( { grep -oE '(^|[^-[:alnum:]_])CERT-[0-9]+' "$Q" "$LOG" 2>/dev/null | sed 's/.*CERT-//'; echo 0; } | sort -n | tail -1 )
ID=$((MAX+1))

# An unused ID is not the same thing as an unstaged SHA. This tool guarantees the
# first and never checked the second, so re-running it after CI turns green stages
# the same commit twice — and because the runner-side bus claims blocks by id, two
# graders can claim the two blocks in the same minute and grade one commit twice.
# CERT-2020/CERT-2021 (lane1b/054, sha 1ff738bc, both claimed 2026-09-06 05:42Z) is
# that bug wearing two four-digit numbers.
#
# Deliberately narrow, because this tool is on every lane's critical path: refuse
# ONLY when a block for the same sha is still LIVE (staged/running/claimed). A prior
# block that is done/superseded/withdrawn/blocked is a legitimate re-stage — a repair
# normally carries a NEW sha, but a re-arm or a second opinion on the same one is
# real, and this must never wedge the bus for it.
if [ "${ALLOW_DUPLICATE_SHA:-0}" != "1" ]; then
  DUPE=$(awk -v sha="$SHA" '
    /^# CERT-[0-9]+ / { id = $2; st = ""; found = 0 }
    /^status:[[:space:]]*/ { if (st == "") { st = $2 } }
    /^sha:[[:space:]]*/ {
      # match either direction so a short sha and a full sha still collide
      if ($2 == sha || index(sha, $2) == 1 || index($2, sha) == 1) { found = 1 }
    }
    /^$/ {
      if (found && (st == "staged" || st == "running" || st == "claimed")) {
        print id " (" st ")"
      }
      found = 0
    }
    END { if (found && (st == "staged" || st == "running" || st == "claimed")) print id " (" st ")" }
  ' "$Q" | sort -u)
  if [ -n "$DUPE" ]; then
    {
      echo "stage-cert.sh: REFUSING — sha $SHA is already staged and still live:"
      echo "$DUPE" | sed 's/^/  /'
      echo
      echo "Grading one commit twice produces two verdicts on one sha, which is the"
      echo "state notices 12/17 exist to prevent. Options:"
      echo "  * the block above IS your presentation — append to it, do not re-stage;"
      echo "  * it is stale and its owner is >90min silent — re-arm it (notice 25);"
      echo "  * you really do want a second block on this sha —"
      echo "        ALLOW_DUPLICATE_SHA=1 stage-cert.sh ... < body.md"
    } >&2
    exit 2
  fi
fi
{
  printf '\n# CERT-%s -- %s\n\nqueue_id: %s\nstatus: staged\n' "$ID" "$SUBJ" "$SUBJ"
  [ -n "$REPAIRS" ] && printf 'repairs: %s   # REPAIRS GRADE FIRST (standing notice 8b)\n' "$REPAIRS"
  printf 'lane: %s\nissue: %s\npr: %s\nbranch: %s\nsha: %s\n\n' "$LANE" "$ISSUE" "$PR" "$BR" "$SHA"
  cat
} >> "$Q"
echo "CERT-$ID"
