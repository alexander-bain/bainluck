#!/usr/bin/env bash
# native/192 — mutation battery for #6574 ("Final · Final" on every settled game).
#
# WHAT THIS SHIP IS, AND THEREFORE WHAT IS WORTH MUTATING
#
# The fix is one line — the card's `timeDisplay` delegates to
# `PeriodLabel.liveStatusText` instead of joining the pair itself. A one-line fix
# is exactly where a battery earns its place, because the danger is not that the
# line is wrong, it is that the tests around it would pass without it:
#
#   * The SWIFT arms (M1-M6) ask whether `GamePlayCardTimeDisplayTests` and the
#     two rewritten `PeriodColumnLabelTests` cases actually constrain the
#     rendered string, or merely re-state today's output. M2 and M3 are the ones
#     that matter: a fix that simply DROPPED one of the two strings kills the
#     defect and is worse than the defect, and a battery that cannot tell those
#     apart has not tested anything.
#
#   * The JEST arms (M7-M9) ask whether the widened discovery tell can fail.
#     A scan that cannot fire is this whole guard file's own stated failure mode
#     ("an empty scan reads as a clean pass"), and the tell is new here, so it is
#     the half with no track record.
#
# VERDICT RULES (inherited from native/189 pass 2, native/190, native/191):
#   * rc AND the log both decide — a partial log's per-arm line reads like a pass
#   * every run is bounded; a mutant that hangs reports REFUSED-HUNG
#   * a needle that does not apply reports REFUSED, never a silent kill
#   * the CONTROL runs LAST and an unmutated tree must pass, or every verdict
#     above it is void
#   * INT/TERM restore every file
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CARD="$ROOT/ios/Bain Luck/Bain Luck/Components/GamePlayCardView.swift"
LABEL="$ROOT/ios/Bain Luck/Bain Luck/Utilities/PeriodLabel.swift"
JEST="$ROOT/frontend/__tests__/ios/periodLabelSingleSource.test.ts"
OUT="${1:-/dev/stdout}"
BOUND=${MUTANT_BOUND:-600}

BAK="$(mktemp -d)"
cp "$CARD" "$BAK/GamePlayCardView.swift"
cp "$LABEL" "$BAK/PeriodLabel.swift"
cp "$JEST" "$BAK/periodLabelSingleSource.test.ts"

restore () {
  cp "$BAK/GamePlayCardView.swift" "$CARD"
  cp "$BAK/PeriodLabel.swift" "$LABEL"
  cp "$BAK/periodLabelSingleSource.test.ts" "$JEST"
}
trap 'echo "  [interrupted — restoring]"; restore; exit 130' INT TERM

KILLED=0; SURVIVED=0; REFUSED=0

# Bash has no `timeout` on macOS. RUN_RC / TIMED_OUT are two different facts: a
# bounded kill is not a test result.
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

run_swift_suite () { # <logfile>
  ( cd "$ROOT" && xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" \
      -scheme "Bain Luck" \
      -destination 'platform=iOS Simulator,name=iPhone 17' \
      -disableAutomaticPackageResolution \
      OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
      test > "$1" 2>&1 )
}

mutate_swift () { # <id> <desc> <file> <needle> <replacement>
  printf '\n%s  %s\n' "$1" "$2" >> "$OUT"
  if ! apply "$3" "$4" "$5"; then
    printf '   REFUSED — NEEDLE NOT FOUND (mutant did not apply; NOT a kill)\n' >> "$OUT"
    REFUSED=$((REFUSED + 1)); restore; return
  fi
  local log; log="$(mktemp)"
  timeout_run "$BOUND" run_swift_suite "$log" || true
  if [ "$TIMED_OUT" = "1" ]; then
    printf '   REFUSED-HUNG — the suite did not finish in %ss\n' "$BOUND" >> "$OUT"
    REFUSED=$((REFUSED + 1)); restore; rm -f "$log"; return
  fi
  # BOTH facts. A compile failure has rc!=0 and no "Executed" line at all, and
  # that is a kill of a different kind — said so rather than counted silently.
  local rc=$RUN_RC
  local executed; executed="$(/usr/bin/grep -cE 'Executed [0-9]+ tests' "$log")"
  local failures; failures="$(/usr/bin/grep -cE 'error: -\[' "$log")"
  if [ "$executed" -eq 0 ]; then
    printf '   KILLED-BY-COMPILER (rc=%s, suite never ran)\n' "$rc" >> "$OUT"
    /usr/bin/grep -E 'error:' "$log" | head -2 | sed 's/^/     /' >> "$OUT"
    KILLED=$((KILLED + 1))
  elif [ "$rc" -ne 0 ] || [ "$failures" -gt 0 ]; then
    printf '   KILLED   (rc=%s, %s failing assertion(s))\n' "$rc" "$failures" >> "$OUT"
    /usr/bin/grep -E 'error: -\[' "$log" | head -4 | sed 's/^/     /' >> "$OUT"
    KILLED=$((KILLED + 1))
  else
    printf '   *** SURVIVED *** (rc=0, no failing assertion)\n' >> "$OUT"
    SURVIVED=$((SURVIVED + 1))
  fi
  rm -f "$log"
  restore
}

run_jest () { # <logfile>
  ( cd "$ROOT/frontend" && npx jest --testPathPatterns=periodLabelSingleSource > "$1" 2>&1 )
}

mutate_jest () { # <id> <desc> <file> <needle> <replacement>
  printf '\n%s  %s\n' "$1" "$2" >> "$OUT"
  if ! apply "$3" "$4" "$5"; then
    printf '   REFUSED — NEEDLE NOT FOUND (mutant did not apply; NOT a kill)\n' >> "$OUT"
    REFUSED=$((REFUSED + 1)); restore; return
  fi
  local log; log="$(mktemp)"
  timeout_run 240 run_jest "$log" || true
  if [ "$TIMED_OUT" = "1" ]; then
    printf '   REFUSED-HUNG — jest did not finish in 240s\n' >> "$OUT"
    REFUSED=$((REFUSED + 1)); restore; rm -f "$log"; return
  fi
  local rc=$RUN_RC
  local failed; failed="$(/usr/bin/grep -cE '✕|Tests:.*failed' "$log")"
  if [ "$rc" -ne 0 ] || [ "$failed" -gt 0 ]; then
    printf '   KILLED   (jest rc=%s)\n' "$rc" >> "$OUT"
    /usr/bin/grep -E '✕' "$log" | head -4 | sed 's/^/     /' >> "$OUT"
    KILLED=$((KILLED + 1))
  else
    printf '   *** SURVIVED *** (jest rc=0)\n' >> "$OUT"
    SURVIVED=$((SURVIVED + 1))
  fi
  rm -f "$log"
  restore
}

{
  echo "native/192 — #6574 mutation battery"
  echo "started $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "bound per swift run: ${BOUND}s"
} >> "$OUT"

# ── M1: the defect itself, put straight back ─────────────────────────────────
mutate_swift "M1" "the card joins the pair itself again — the exact 'Final · Final' line" \
  "$CARD" \
  '        PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""' \
  '        let parts = [PeriodLabel.normalize(period ?? ""), clock ?? ""]
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")'

# ── M2/M3: the two fixes that are WORSE than the defect ──────────────────────
# Both make "Final · Final" go away. Neither is the ship. If the suite cannot
# tell these from the fix, it is pinning the specimen and nothing else.
mutate_swift "M2" "the clock is dropped entirely (period only) — kills the defect, deletes the game clock" \
  "$CARD" \
  '        PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""' \
  '        PeriodLabel.normalize(period ?? "")'

mutate_swift "M3" "the period is dropped entirely (clock only) — kills the defect, deletes the state" \
  "$CARD" \
  '        PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""' \
  '        clock ?? ""'

# ── M4-M6: the shared rule this card now leans on ────────────────────────────
# The card cannot be correct if the rule underneath it is not, and these three
# arms are the parts of that rule the card's own cases exercise.
mutate_swift "M4" "the collision test becomes case-SENSITIVE (Final vs FINAL prints twice)" \
  "$LABEL" \
  'let parts = label.caseInsensitiveCompare(clock) == .orderedSame' \
  'let parts = label == clock'

mutate_swift "M5" "a 0:00 clock is printed again (the interval reads 'HT 0:00')" \
  "$LABEL" \
  'if clock == "0:00" || clock == "0" { clock = "" }' \
  'if clock == "0" { clock = "" }'

mutate_swift "M6" "on a collision the CLOCK is dropped instead of the label" \
  "$LABEL" \
  '        let parts = label.caseInsensitiveCompare(clock) == .orderedSame
            ? [clock]
            : [label, clock]' \
  '        let parts = label.caseInsensitiveCompare(clock) == .orderedSame
            ? [label]
            : [label, clock]'

# ── M7-M9: the widened discovery tell, which is new and has no track record ──
mutate_jest "M7" "the renamed-join tell is deleted from the scan (only the old gameClock tell remains)" \
  "$JEST" \
  '        if (RAW_JOIN_RENAMED.some((re) => re.test(code))) {' \
  '        if (false && RAW_JOIN_RENAMED.some((re) => re.test(code))) {'

mutate_jest "M8" "the tell goes back to requiring the literal identifier gameClock" \
  "$JEST" \
  '  /\[[^\]\n]*\bperiod\w*\b[^\]\n]*\b\w*[Cc]lock\w*\b[^\]\n]*\]/,' \
  '  /\[[^\]\n]*\bperiod\w*\b[^\]\n]*\bgameClock\b[^\]\n]*\]/,'

mutate_jest "M9" "GamePlayCardView drops off the named pair-printer list" \
  "$JEST" \
  '  [join(IOS_ROOT, "Components/GamePlayCardView.swift"), "the play card under the chart"],' \
  ''

# ── the control, LAST ────────────────────────────────────────────────────────
printf '\nCONTROL  clean head, no mutant applied\n' >> "$OUT"
CLOG="$(mktemp)"
timeout_run "$BOUND" run_swift_suite "$CLOG" || true
CRC=$RUN_RC
CEXEC="$(/usr/bin/grep -cE 'error: -\[' "$CLOG")"
if [ "$CRC" -eq 0 ] && [ "$CEXEC" -eq 0 ]; then
  printf '   SURVIVED (correct — clean tree, rc=0, 0 failing assertions)\n' >> "$OUT"
  /usr/bin/grep -E 'Executed [0-9]+ tests, with' "$CLOG" | tail -1 | sed 's/^/     /' >> "$OUT"
else
  printf '   *** CONTROL FAILED *** rc=%s — every verdict above is void\n' "$CRC" >> "$OUT"
  /usr/bin/grep -E 'error: -\[' "$CLOG" | head -4 | sed 's/^/     /' >> "$OUT"
fi
rm -f "$CLOG"

CJLOG="$(mktemp)"
timeout_run 240 run_jest "$CJLOG" || true
if [ "$RUN_RC" -eq 0 ]; then
  printf '   jest control SURVIVED (correct — rc=0)\n' >> "$OUT"
  /usr/bin/grep -E '^Tests:' "$CJLOG" | sed 's/^/     /' >> "$OUT"
else
  printf '   *** JEST CONTROL FAILED *** rc=%s — the jest verdicts above are void\n' "$RUN_RC" >> "$OUT"
fi
rm -f "$CJLOG"

restore
{
  echo
  echo "killed=$KILLED  survived=$SURVIVED  refused=$REFUSED"
  echo "tree restored:"
  diff -q "$BAK/GamePlayCardView.swift" "$CARD" >/dev/null && echo "  GamePlayCardView.swift  IDENTICAL" || echo "  GamePlayCardView.swift  *** DIFFERS ***"
  diff -q "$BAK/PeriodLabel.swift" "$LABEL" >/dev/null && echo "  PeriodLabel.swift  IDENTICAL" || echo "  PeriodLabel.swift  *** DIFFERS ***"
  diff -q "$BAK/periodLabelSingleSource.test.ts" "$JEST" >/dev/null && echo "  periodLabelSingleSource.test.ts  IDENTICAL" || echo "  periodLabelSingleSource.test.ts  *** DIFFERS ***"
  echo "finished $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
} >> "$OUT"
rm -rf "$BAK"
