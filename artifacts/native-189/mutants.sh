#!/usr/bin/env bash
# native/189 (#6528) — mutation battery for SuspendedCardSaysItOnce6528Tests.
#
# Each mutant is applied to the REAL file (exact-substring replace, refusing
# loudly if the needle is not found exactly once), the suite is run, and the
# file is restored byte-for-byte from a pre-image.
#
# 🔴 TWO WAYS A MUTANT LIES ABOUT BEING KILLED, and both bit the first run of
# this battery (2026-09-16, native/189):
#
#   1. NEEDLE NOT FOUND. The edit never landed, the suite passes on clean code,
#      and a battery that only reads the exit code records a kill.
#   2. THE MUTANT DID NOT COMPILE. `xcodebuild` exits 65 for a compile error and
#      for a test failure alike, so a MALFORMED mutant — mine put `_ = (away,
#      home)` between a `let` and its own `.compactMap` continuation — scores as
#      a kill while the guard never ran. Two of ten mutants were this.
#
# So the verdict is taken from the LOG, not the exit code: a kill requires the
# build to have succeeded AND a test to have failed. `error:` inside a compile
# phase is a REFUSAL — rewrite the mutant.
#
# The tree is restored on INT/TERM as well as on the happy path: the first run
# was interrupted mid-mutant and left `StatusBadge.swift` carrying M10.
set -uo pipefail
cd "$(dirname "$0")/../.."

ES="ios/Bain Luck/Bain Luck/Utilities/EventState.swift"
CARD="ios/Bain Luck/Bain Luck/Components/EventCardView.swift"
BADGE="ios/Bain Luck/Bain Luck/Components/StatusBadge.swift"
TMP=$(mktemp -d)
cp "$ES" "$TMP/es.pre"; cp "$CARD" "$TMP/card.pre"; cp "$BADGE" "$TMP/badge.pre"

restore() {
  cp "$TMP/es.pre" "$ES"; cp "$TMP/card.pre" "$CARD"; cp "$TMP/badge.pre" "$BADGE"
}
trap 'echo; echo "interrupted — restoring the tree"; restore; exit 130' INT TERM

apply() {  # file needle replacement
  python3 - "$1" "$2" "$3" <<'PY'
import sys
path, needle, repl = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path, encoding='utf-8').read()
n = src.count(needle)
if n != 1:
    print(f"NEEDLE NOT FOUND (count={n})"); sys.exit(2)
open(path, 'w', encoding='utf-8').write(src.replace(needle, repl))
PY
}

run_suite() {
  xcodebuild test -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    > "$TMP/out.txt" 2>&1
  echo $?
}

# KILLED   — it built and a test failed (the guard fired)
# REFUSED  — it did not build (malformed mutant), or the needle was absent
# SURVIVED — it built and every test passed
classify() {
  local rc=$1
  if /usr/bin/grep -qE "^.*\.swift:[0-9]+:[0-9]+: error: " "$TMP/out.txt"; then
    echo REFUSED-DID-NOT-COMPILE; return
  fi
  if ! /usr/bin/grep -q "Executed .* tests, with" "$TMP/out.txt"; then
    echo REFUSED-SUITE-NEVER-RAN; return
  fi
  if [ "$rc" -eq 0 ]; then echo SURVIVED; else echo KILLED; fi
}

KILLED=0; SURVIVED=0; REFUSED=0
mutant() {  # name file needle replacement
  local name=$1 file=$2 needle=$3 repl=$4
  restore
  if ! apply "$file" "$needle" "$repl"; then
    echo "$name  REFUSED — needle not found"; REFUSED=$((REFUSED+1)); restore; return
  fi
  local rc verdict by
  rc=$(run_suite)
  verdict=$(classify "$rc")
  case "$verdict" in
    KILLED)
      KILLED=$((KILLED+1))
      by=$(/usr/bin/grep -oE "test[A-Za-z]+\]' failed|-\[SuspendedCardSaysItOnce6528Tests test[A-Za-z]+\] : " "$TMP/out.txt" \
           | /usr/bin/sed 's/.*\(test[A-Za-z]*\).*/\1/' | sort -u | tr '\n' ' ')
      ;;
    SURVIVED) SURVIVED=$((SURVIVED+1)); by="" ;;
    *)        REFUSED=$((REFUSED+1))
              by=$(/usr/bin/grep -oE "\.swift:[0-9]+:[0-9]+: error: .*" "$TMP/out.txt" | head -1) ;;
  esac
  echo "$name"
  echo "    rc=$rc  $verdict  ${by:0:150}"
  restore
  cmp -s "$TMP/es.pre" "$ES" && cmp -s "$TMP/card.pre" "$CARD" && cmp -s "$TMP/badge.pre" "$BADGE" \
    || echo "    ^^^ TREE NOT RESTORED"
}

echo "=== 10 mutants — a kill requires BUILD SUCCEEDED and a failing test ==="

mutant "M1  the defect restored: the slot prints the full summary again" "$ES" \
'        let parts = [lastScoreFragment(away: away, home: home), date]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")' \
'        _ = date
        return suspendedSummary(away: away, home: home)'

mutant "M2  nil unconditionally — the tidy-looking deletion that loses the date" "$ES" \
'        let parts = [lastScoreFragment(away: away, home: home), date]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")' \
'        _ = (away, home, date)
        return nil'

mutant "M3  the date is dropped from the slot (#6361 left unbuilt on native)" "$ES" \
'        let parts = [lastScoreFragment(away: away, home: home), date]
            .compactMap { $0 }' \
'        let parts: [String?] = [lastScoreFragment(away: away, home: home)]
            .compactMap { $0 }'

mutant "M4  the score tail is dropped" "$ES" \
'        let parts = [lastScoreFragment(away: away, home: home), date]
            .compactMap { $0 }' \
'        let parts: [String?] = [date]
            .compactMap { $0 }'

mutant "M5  empty joins to \"\" — an empty Text that still costs its 6pt of spacing" "$ES" \
'        return parts.isEmpty ? nil : parts.joined(separator: " · ")' \
'        return parts.joined(separator: " · ")'

mutant "M6  a partial score reaches the card (CERT-752's trap)" "$ES" \
'        guard let away, let home else { return nil }
        return "last score \(away)-\(home)"' \
'        if away == nil && home == nil { return nil }
        return "last score \(away.map(String.init) ?? "")-\(home.map(String.init) ?? "")"'

mutant "M7  the Discover summary loses its label (the sibling must not move)" "$ES" \
'        guard let fragment = lastScoreFragment(away: away, home: home) else { return suspendedLabel }
        return "\(suspendedLabel) · \(fragment)"' \
'        guard let fragment = lastScoreFragment(away: away, home: home) else { return suspendedLabel }
        return fragment'

mutant "M8  the card reverts to the summary" "$CARD" \
'            } else if isSuspended, let detail = EventState.suspendedCardDetail(
                away: event.awayScore, home: event.homeScore, date: formattedDateString) {' \
'            } else if isSuspended, let detail = Optional(
                EventState.suspendedSummary(away: event.awayScore, home: event.homeScore)) {'

mutant "M9  the card advertises a start time again (live/048)" "$CARD" \
'                away: event.awayScore, home: event.homeScore, date: formattedDateString) {' \
'                away: event.awayScore, home: event.homeScore, date: formattedDateTimeString) {'

mutant "M10 the badge stops saying the words the slot gave up (the omission)" "$BADGE" \
'                Text(EventState.suspendedLabel)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .foregroundStyle(.orange)' \
'                Text("Paused")
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .foregroundStyle(.orange)'

echo
echo "=== clean-head control, run LAST (expect SURVIVED) ==="
restore
rc=$(run_suite)
echo "M0  clean head  rc=$rc  $(classify "$rc")"

echo
echo "killed=$KILLED survived=$SURVIVED refused=$REFUSED (of 10)"
restore
cmp -s "$TMP/es.pre" "$ES" && cmp -s "$TMP/card.pre" "$CARD" && cmp -s "$TMP/badge.pre" "$BADGE" \
  && echo "tree restored byte-identical" || echo "TREE NOT RESTORED"
