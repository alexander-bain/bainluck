#!/usr/bin/env bash
# native/191 — mutation battery for #2975.
#
# WHAT IS WORTH MUTATING HERE, AND WHAT IS NOT
#
# This ship has two halves and they are not equally provable, so the battery does
# not pretend they are.
#
#   The WATCHDOG (tools/native-gates.sh) is deterministic. Its five --selftest
#   arms drive the real function against real children, so a mutant either makes
#   an arm fail or it does not, every time. Those are M1-M5 and they are the
#   whole point of this file.
#
#   The SWIFT half is a race, and I expected its mutant to survive: the defect
#   had fired only twice in twelve days, so reinstating it should pass the suite
#   almost always. RUN 1 KILLED IT INSTEAD, on the assertion rather than on the
#   watchdog — `XCTAssertEqual failed: ("0") is not equal to ("1")`. At this
#   machine's load the `async let` child does not reach the client at all, so the
#   race is not rare here, it is nearly always lost; what made it look rare was
#   that losing it produced SILENCE rather than a failure. The guard converts it
#   to a red test before the deadlock can form, because it runs before the second
#   load is issued. The prediction is left in this comment on purpose: it was
#   wrong, and the reason it was wrong is the ship.
#
# VERDICT RULES (inherited from native/189 pass 2, native/190):
#   * rc AND the log both decide — a partial log's per-arm line reads like a pass
#   * every run is bounded; a mutant that hangs reports REFUSED-HUNG
#   * a needle that does not apply reports REFUSED, never a silent kill
#   * INT/TERM restore every file
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATES="$ROOT/tools/native-gates.sh"
SWIFT="$ROOT/ios/Bain Luck/BainLuckTests/FeedViewModelSportsLoadTests.swift"
OUT="${1:-/dev/stdout}"
BOUND=${MUTANT_BOUND:-420}

BAK="$(mktemp -d)"
cp "$GATES" "$BAK/native-gates.sh"
cp "$SWIFT" "$BAK/FeedViewModelSportsLoadTests.swift"

restore () {
  cp "$BAK/native-gates.sh" "$GATES"
  cp "$BAK/FeedViewModelSportsLoadTests.swift" "$SWIFT"
}
trap 'echo "  [interrupted — restoring]"; restore; exit 130' INT TERM

KILLED=0; SURVIVED=0; REFUSED=0

# Apply a literal substitution. Refuses loudly when the needle is absent: a
# mutant that did not apply reads exactly like a kill, which is the failure mode
# this battery had to be taught to report (native/189).
apply () { # <file> <needle> <replacement>
  if ! /usr/bin/grep -qF "$2" "$1"; then return 1; fi
  python3 - "$1" "$2" "$3" <<'PY'
import sys
p, needle, repl = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p).read()
open(p, "w").write(s.replace(needle, repl, 1))
PY
  return 0
}

# --- the watchdog arms: the killer is --selftest, which needs no Xcode --------
mutate_selftest () { # <id> <desc> <needle> <replacement>
  printf '\n%s  %s\n' "$1" "$2" >> "$OUT"
  if ! apply "$GATES" "$3" "$4"; then
    printf '   REFUSED — NEEDLE NOT FOUND (mutant did not apply; NOT a kill)\n' >> "$OUT"
    REFUSED=$((REFUSED + 1)); restore; return
  fi
  local log; log="$(mktemp)"
  if ! timeout_run "$BOUND" bash "$GATES" --selftest > "$log" 2>&1; then
    if [ "$TIMED_OUT" = "1" ]; then
      printf '   REFUSED-HUNG — the selftest itself did not finish in %ss\n' "$BOUND" >> "$OUT"
      REFUSED=$((REFUSED + 1)); restore; rm -f "$log"; return
    fi
  fi
  local rc=$RUN_RC
  local failing; failing="$(/usr/bin/grep -c '^  FAIL' "$log")"
  if [ "$rc" -ne 0 ] || [ "$failing" -gt 0 ]; then
    printf '   KILLED   (--selftest rc=%s, %s failing arm(s))\n' "$rc" "$failing" >> "$OUT"
    /usr/bin/grep '^  FAIL' "$log" | sed 's/^/     /' >> "$OUT"
    KILLED=$((KILLED + 1))
  else
    printf '   *** SURVIVED *** (--selftest rc=0, every arm ok)\n' >> "$OUT"
    SURVIVED=$((SURVIVED + 1))
  fi
  rm -f "$log"
  restore
}

# Bash has no `timeout` on macOS. RUN_RC / TIMED_OUT are the two facts a verdict
# needs and they are different facts: a bounded kill is not a test result.
TIMED_OUT=0; RUN_RC=0
timeout_run () { # <seconds> <cmd...>
  local limit=$1; shift
  TIMED_OUT=0
  "$@" & local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 2; waited=$((waited + 2))
    if [ "$waited" -ge "$limit" ]; then
      TIMED_OUT=1; kill -KILL "$pid" 2>/dev/null; break
    fi
  done
  wait "$pid" 2>/dev/null; RUN_RC=$?
  [ "$TIMED_OUT" = "0" ] && return $RUN_RC || return 1
}

{
  echo "native/191 — #2975 mutation battery"
  echo "started $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "bound per run: ${BOUND}s"
} >> "$OUT"

mutate_selftest "M1" "a stalled child is reported as HEALTHY (return 1 -> return 0)" \
  '      return 1
    fi
  done
  return 0' \
  '      return 0
    fi
  done
  return 0'

mutate_selftest "M2" "the stall is REPORTED but the child is never killed" \
  '      kill -TERM -"$_ws_pid" 2>/dev/null || kill -TERM "$_ws_pid" 2>/dev/null
      sleep 5
      kill -KILL -"$_ws_pid" 2>/dev/null || kill -KILL "$_ws_pid" 2>/dev/null' \
  '      : # mutant: report the stall, leave the process running'

mutate_selftest "M3" "the watchdog trips on EVERY poll (growth never resets the clock)" \
  '    if [ "$_ws_size" != "$_ws_last_size" ]; then
      _ws_last_size=$_ws_size
      _ws_last_growth=$_ws_now' \
  '    if false; then
      _ws_last_size=$_ws_size
      _ws_last_growth=$_ws_now'

mutate_selftest "M4" "the limit is ignored — any quiet poll is a stall" \
  'elif [ $((_ws_now - _ws_last_growth)) -ge "$_ws_limit" ]; then' \
  'elif true; then'

mutate_selftest "M5" "the watchdog never loops (the child is never watched at all)" \
  '  while kill -0 "$_ws_pid" 2>/dev/null; do' \
  '  while false; do'

# --- the Swift arm: the regression itself, run against the real suite ---------
printf '\nM6  the test goes back to `await Task.yield()` — the exact #2975 regression\n' >> "$OUT"
if ! apply "$SWIFT" '        await fake.firstCallArrived.wait()' '        await Task.yield()'; then
  printf '   REFUSED — NEEDLE NOT FOUND (mutant did not apply; NOT a kill)\n' >> "$OUT"
  REFUSED=$((REFUSED + 1))
else
  MLOG="$(mktemp)"
  touch "$SWIFT"
  if ! timeout_run "$BOUND" bash "$GATES" > "$MLOG" 2>&1; then :; fi
  if [ "$TIMED_OUT" = "1" ]; then
    printf '   KILLED-BY-WATCHDOG — the suite hung and the bound cut it (this is the pairing)\n' >> "$OUT"
    KILLED=$((KILLED + 1))
  elif /usr/bin/grep -q 'STALLED' "$MLOG"; then
    printf '   KILLED-BY-WATCHDOG — native-gates.sh reported STALLED\n' >> "$OUT"
    KILLED=$((KILLED + 1))
  elif /usr/bin/grep -q 'BainLuckTests: PASS' "$MLOG"; then
    printf '   *** SURVIVED *** — the suite passed, i.e. the scheduler won the race\n' >> "$OUT"
    printf '     this time. Not a green: it means the guard did not get to fire, and\n' >> "$OUT"
    printf '     the watchdog in the same ship is what stands behind it.\n' >> "$OUT"
    SURVIVED=$((SURVIVED + 1))
  else
    printf '   KILLED   (suite did not pass; see log)\n' >> "$OUT"
    /usr/bin/grep -E 'FAIL|failed' "$MLOG" | head -3 | sed 's/^/     /' >> "$OUT"
    KILLED=$((KILLED + 1))
  fi
  rm -f "$MLOG"
fi
restore

# --- the control: an unmutated tree must pass, and it runs LAST --------------
printf '\nCONTROL  clean head, no mutant applied\n' >> "$OUT"
CLOG="$(mktemp)"
if timeout_run "$BOUND" bash "$GATES" --selftest > "$CLOG" 2>&1; then
  printf '   SURVIVED (correct — --selftest rc=0 on the clean tree)\n' >> "$OUT"
else
  printf '   *** CONTROL FAILED *** rc=%s — every verdict above is void\n' "$RUN_RC" >> "$OUT"
  /usr/bin/grep '^  FAIL' "$CLOG" | sed 's/^/     /' >> "$OUT"
fi
rm -f "$CLOG"

restore
{
  echo
  echo "killed=$KILLED  survived=$SURVIVED  refused=$REFUSED"
  echo "tree restored:"
  diff -q "$BAK/native-gates.sh" "$GATES" >/dev/null && echo "  native-gates.sh  IDENTICAL" || echo "  native-gates.sh  *** DIFFERS ***"
  diff -q "$BAK/FeedViewModelSportsLoadTests.swift" "$SWIFT" >/dev/null && echo "  FeedViewModelSportsLoadTests.swift  IDENTICAL" || echo "  FeedViewModelSportsLoadTests.swift  *** DIFFERS ***"
  echo "finished $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
} >> "$OUT"
rm -rf "$BAK"
