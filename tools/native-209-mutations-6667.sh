#!/usr/bin/env bash
# native-209-mutations-6667.sh — is the #6667 test battery load-bearing?
#
# Each mutant REINSTATES a defect this ship removed, or breaks a rule it added,
# and must be KILLED (the suite goes red). A mutant that survives means the test
# naming that behaviour is decorative.
#
# 🪤 A mutant that does not COMPILE is a BATTERY FAILURE, not a kill — xcodebuild
# exits 65 and a script that only checks "non-zero = killed" scores a clean sheet
# having tested nothing (native/207's lesson). So the two are told apart by the
# `** TEST BUILD FAILED **` banner in the same run, which costs no extra build.
set -uo pipefail
cd "$(dirname "$0")/.."

MODELS="ios/Bain Luck/Bain Luck/Models/ConceptCardModels.swift"
SIM="${SIM:-D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05}"
BACKUP="$(mktemp)"; cp "$MODELS" "$BACKUP"
restore() { cp "$BACKUP" "$MODELS"; }
trap restore EXIT

run_suite() {
  xcodebuild test -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination "platform=iOS Simulator,id=$SIM" -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    -only-testing:BainLuckTests/AUFCCardOpensThatFightCard6667Tests 2>&1
}

KILLED=0; SURVIVED=0; BROKEN=0
mutate() {
  local name="$1" from="$2" to="$3"
  restore
  if ! /usr/bin/grep -qF "$from" "$MODELS"; then
    echo "  ⚠️  BATTERY FAILURE  $name — anchor text not found, mutant never applied"
    BROKEN=$((BROKEN+1)); return
  fi
  python3 - "$MODELS" "$from" "$to" <<'PY'
import sys
p,f,t = sys.argv[1],sys.argv[2],sys.argv[3]
s=open(p).read()
assert s.count(f)==1, f"anchor appears {s.count(f)} times"
open(p,'w').write(s.replace(f,t))
PY
  local out; out="$(run_suite)"
  if echo "$out" | /usr/bin/grep -q "TEST BUILD FAILED"; then
    echo "  ⚠️  BATTERY FAILURE  $name — mutant did not COMPILE, so nothing was tested"
    BROKEN=$((BROKEN+1))
  elif echo "$out" | /usr/bin/grep -q "TEST SUCCEEDED"; then
    echo "  ❌ SURVIVED         $name"
    SURVIVED=$((SURVIVED+1))
  else
    echo "  ✅ killed           $name  ($(echo "$out" | /usr/bin/grep -cE "^Test Case.*failed") failing case(s))"
    KILLED=$((KILLED+1))
  fi
}

echo "=== #6667 mutation battery"

# 1. THE DEFECT THIS SESSION FOUND. Pre-fix behaviour: a bout is drawn as decided
#    on `child.settled` alone, so an upcoming card's 0.98 favourite reads "Final"
#    with no price.
mutate "boutIsDecided ignores the card's assigned status (the shipped defect)" \
  'guard childSettled == true else { return false }
        return cardStatus?.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() != "upcoming"' \
  'return childSettled == true'

# 2. The opposite over-correction: never draw a bout as decided at all. Kills any
#    test that only ever asserts the FALSE direction of the new rule.
mutate "boutIsDecided always refuses (no bout is ever Final)" \
  'guard childSettled == true else { return false }' \
  'guard childSettled == true else { return false }
        if true { return false }'

# 3. The winner floor calibration removed — a price crowned as a result.
mutate "settledWinner reinstates the >=0.97 price floor" \
  'return (child.outcomes ?? fightersFavouriteFirst).first { $0.won == true }?.name' \
  'if let top = fightersFavouriteFirst.first, (top.probability ?? 0) >= 0.97 { return top.name }
        return (child.outcomes ?? fightersFavouriteFirst).first { $0.won == true }?.name'

# 4. The id-space guess: an unknown/absent source opens as a futures market.
mutate "boutTarget defaults an unknown source to .market (guesses an id space)" \
  'if futuresSources.contains(source) { return .market(id: id) }
        return .none' \
  'return .market(id: id)'

# 5. Main-event ordering: the server sends the headline fight LAST.
mutate "the card is not reversed (headline fight goes last)" \
  'bouts = fights.reversed().enumerated().map' \
  'bouts = fights.enumerated().map'

restore
echo
echo "=== $KILLED killed · $SURVIVED survived · $BROKEN battery failures"
[ "$SURVIVED" -eq 0 ] && [ "$BROKEN" -eq 0 ]
