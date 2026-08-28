#!/bin/bash
# test-lane-runner.sh — behavioural guard for the two INT-137 cert findings.
#
#   usage: tools/lane-runner/test-lane-runner.sh [path-to-lane-runner.sh] [path-to-start-lanes.sh]
#
# Defaults to the repo-root copies. Point it at a checkout of the PRE-fix scripts
# to see the red-first proof: T1/T2/T3 and R2 fail there and pass here.
#
# Everything runs under a throwaway $HOME, because both scripts hardcode
# $HOME/bainluck/.claude/handoff — without the override this test would stage
# directives into the REAL inbox and reap the REAL lanes.
#
# `claude` and `osascript` are shimmed onto PATH: no session is ever started and
# no Terminal window is ever opened.

set -u

RUNNER="${1:-$(cd "$(dirname "$0")/../.." && pwd)/lane-runner.sh}"
STARTER="${2:-$(cd "$(dirname "$0")/../.." && pwd)/start-lanes.sh}"

PASS=0
FAIL=0
ok   () { PASS=$((PASS + 1)); echo "  PASS  $1"; }
bad  () { FAIL=$((FAIL + 1)); echo "  FAIL  $1"; }

SANDBOX=$(mktemp -d /tmp/lane-runner-test.XXXXXX)
trap 'rm -rf "$SANDBOX"' EXIT

BIN="$SANDBOX/bin"
mkdir -p "$BIN"

# Fake session. FAKE_RC = exit code; FAKE_HANG=1 = never return (timeout path).
cat > "$BIN/claude" <<'SHIM'
#!/bin/bash
echo '{"type":"system","subtype":"init","model":"fake"}'
[ "${FAKE_HANG:-0}" = "1" ] && sleep 600
exit "${FAKE_RC:-0}"
SHIM
# Fake Terminal launcher, so start-lanes.sh opens nothing.
cat > "$BIN/osascript" <<'SHIM'
#!/bin/bash
exit 0
SHIM
chmod +x "$BIN/claude" "$BIN/osascript"
export PATH="$BIN:$PATH"

FAKEHOME="$SANDBOX/home"
INBOX="$FAKEHOME/bainluck/.claude/handoff/runner-inbox/testlane"
PIDDIR="$FAKEHOME/bainluck/.claude/handoff/runner-pids"

reset_inbox () {
  rm -rf "$FAKEHOME"
  mkdir -p "$INBOX" "$FAKEHOME/work"
  printf 'test directive\n' > "$INBOX/q-test.md"
}

# Run the runner until PREDICATE holds or DEADLINE seconds pass. Killed by pid
# (never by pattern — a -f pattern kill would hit every real lane on this box).
run_until () {
  local deadline="$1"; shift
  local predicate="$1"; shift
  HOME="$FAKEHOME" "$@" "$RUNNER" "$FAKEHOME/work" testlane > "$SANDBOX/runner.log" 2>&1 &
  local pid=$!
  local i=0
  while [ "$i" -lt "$deadline" ]; do
    if eval "$predicate"; then break; fi
    sleep 1
    i=$((i + 1))
  done
  kill -9 "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
}

# `find -name`, not `ls "$INBOX"/$1`: the strike counter is dot-prefixed
# (.q-test.md.fails) and a shell glob cannot match a leading dot. With `ls`,
# every *.fails check silently reads 0 — T1/T2 would wait out their full
# deadline instead of their predicate, and T3's cleanup assertion would pass
# without ever looking at anything.
count () { find "$INBOX" -maxdepth 1 -name "$1" 2>/dev/null | wc -l | tr -d ' '; }

echo "runner:  $RUNNER"
echo "starter: $STARTER"
echo

# ---------------------------------------------------------------- T1 --------
# A session that exits nonzero must NOT be consumed — the .md name comes back.
echo "T1  failed session re-queues instead of consuming"
reset_inbox
run_until 25 '[ "$(count "*.fails")" -ge 1 ]' \
  env FAKE_RC=1 LANE_MAX_FAILS=3 LANE_RETRY_BACKOFF=30
[ "$(count 'q-test.md')" -eq 1 ]   && ok "directive restored to q-test.md" \
                                   || bad "directive is NOT back in the queue"
[ "$(count '*.consumed-*')" -eq 0 ] && ok "no .consumed-* written" \
                                   || bad "failed session was marked consumed"
grep -q 'FAILED rc=1' "$SANDBOX/runner.log" && ok "exit code logged" \
                                   || bad "exit code not logged"

# ---------------------------------------------------------------- T2 --------
# The timeout path. This is the one the old PIPESTATUS read got wrong: read
# outside the subshell it reports tee's status, so a 124 measured as success.
echo "T2  timed-out session re-queues (rc=124 is seen at all)"
reset_inbox
run_until 30 '[ "$(count "*.fails")" -ge 1 ]' \
  env FAKE_HANG=1 LANE_SESSION_TIMEOUT=3 LANE_MAX_FAILS=3 LANE_RETRY_BACKOFF=30
[ "$(count 'q-test.md')" -eq 1 ]   && ok "directive restored to q-test.md" \
                                   || bad "timed-out directive is NOT back in the queue"
[ "$(count '*.consumed-*')" -eq 0 ] && ok "no .consumed-* written" \
                                   || bad "timed-out session was marked consumed"
grep -q 'FAILED rc=124' "$SANDBOX/runner.log" && ok "rc=124 observed" \
                                   || bad "timeout exit code not observed (PIPESTATUS read outside the subshell?)"

# ---------------------------------------------------------------- T3 --------
# The retry guard: a directive that always fails must stop, not hot-loop.
echo "T3  three strikes quarantines, loudly, and stops retrying"
reset_inbox
run_until 40 '[ "$(count "*.failed-*")" -ge 1 ]' \
  env FAKE_RC=1 LANE_MAX_FAILS=3 LANE_RETRY_BACKOFF=1
[ "$(count '*.failed-*')" -eq 1 ]  && ok "quarantined as *.failed-<ts>" \
                                   || bad "never quarantined — it can hot-loop"
[ "$(count 'q-test.md')" -eq 0 ]   && ok "removed from the queue glob" \
                                   || bad "still queued after quarantine"
[ "$(count '*.consumed-*')" -eq 0 ] && ok "not recorded as consumed" \
                                   || bad "quarantined directive marked consumed"
grep -q 'QUARANTINED' "$SANDBOX/runner.log" && ok "announced loudly" \
                                   || bad "quarantine was silent"
[ "$(count '*.fails')" -eq 0 ]     && ok "strike counter cleaned up" \
                                   || bad "strike counter left behind"

# ---------------------------------------------------------------- T4 --------
# Must-not-regress: the happy path still consumes exactly as before.
echo "T4  clean session still consumes (must-not-regress)"
reset_inbox
run_until 25 '[ "$(count "*.consumed-*")" -ge 1 ]' env FAKE_RC=0
[ "$(count '*.consumed-*')" -eq 1 ] && ok "consumed on rc=0" \
                                   || bad "clean session was NOT consumed"
[ "$(count 'q-test.md')" -eq 0 ]   && ok "removed from the queue glob" \
                                   || bad "consumed directive still queued"
grep -q 'done rc=0' "$SANDBOX/runner.log" && ok "logged done rc=0" \
                                   || bad "clean completion not logged"

# ---------------------------------------------------------------- R1..R3 ----
# The reaper. Three orphans with IDENTICAL command lines — so a ps-grep alone
# cannot tell them apart — differing only in the two ownership signals:
#
#   R1  recorded process group, cwd outside a Bain Luck tree  -> must die
#   R2  no record,              cwd outside a Bain Luck tree  -> must LIVE
#   R3  no record,              cwd inside  a Bain Luck tree  -> must die
#
# R3 is the transition case: orphans left by runners that predate the pgid
# records have no record at all, and a record-only reaper would never clear them.
# Each orphan is re-parented to launchd by exiting its parent.
echo "R1/R2/R3  orphan reaper is scoped to Bain Luck runners, by record or by cwd"
reset_inbox
mkdir -p "$PIDDIR" "$FAKEHOME/bainluck/tree" "$SANDBOX/elsewhere"
# Prints "pid pgid" for a fake headless session that is orphaned and sits in its
# OWN process group (`set -m` gives background jobs their own pgid even
# non-interactively). $2 is the cwd it runs in — pinned explicitly, because
# inheriting the harness's cwd would silently decide the cwd-signal tests.
spawn_orphan () {
  local out="$SANDBOX/orphan.$1"
  # The orphan's stdout MUST go to /dev/null: inherited, it holds this function's
  # command substitution open for the full sleep.
  bash -c 'set -m
           cd "'"$2"'" || exit 1
           ( exec -a "claude --dangerously-skip-permissions --verbose stub" sleep 300 ) >/dev/null 2>&1 &
           echo "$! $(ps -o pgid= -p $! | tr -d " ")" > "'"$out"'"'
  cat "$out"
}
read -r OWNED_PID OWNED_PGID     <<< "$(spawn_orphan owned   "$SANDBOX/elsewhere")"
read -r FOREIGN_PID FOREIGN_PGID <<< "$(spawn_orphan foreign "$SANDBOX/elsewhere")"
read -r INTREE_PID INTREE_PGID   <<< "$(spawn_orphan intree  "$FAKEHOME/bainluck/tree")"
sleep 1
echo "$OWNED_PGID" > "$PIDDIR/runner-test.pgid"     # only this group is claimed

HOME="$FAKEHOME" bash "$STARTER" > "$SANDBOX/starter.log" 2>&1
sleep 2

kill -0 "$OWNED_PID" 2>/dev/null   && bad "R1 recorded-group orphan survived the reap" \
                                   || ok "R1 recorded-group orphan reaped"
kill -0 "$FOREIGN_PID" 2>/dev/null && ok "R2 unowned foreign orphan left alone" \
                                   || bad "R2 unowned foreign orphan was killed — reap is machine-wide"
kill -0 "$INTREE_PID" 2>/dev/null  && bad "R3 in-tree orphan survived — pre-record orphans can never be cleared" \
                                   || ok "R3 in-tree orphan reaped on the cwd signal"
kill -9 "$OWNED_PID" "$FOREIGN_PID" "$INTREE_PID" 2>/dev/null

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
