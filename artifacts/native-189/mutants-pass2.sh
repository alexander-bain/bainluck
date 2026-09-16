#!/usr/bin/env bash
# native/189 (#6528) — supplementary pass for the three mutants pass 1 did not grade.
#
# Pass 1 scored killed=8 survived=0 refused=2, and only SEVEN of those eight are
# real. Three failures of the RIG, none of the fix:
#
#   M3, M4  REFUSED-DID-NOT-COMPILE. Annotating the array `[String?]` made
#           `.compactMap` a no-op, so `joined` had no overload. Rewritten to keep
#           the literal's shape and drop one ELEMENT, which is the mutation
#           actually intended.
#   M5      rc=143. The suite wedged on a live network read inside the app under
#           test (log froze at 02:52:50 on `nw_read_request_report … Operation
#           timed out`) and I killed it. 143 is SIGTERM — gotcha #124: only 0 and
#           65 are xcodebuild answering; everything else is a story about the
#           harness. Pass 1's classifier read the partial log, found a per-class
#           "Executed N tests" line and called it a kill.
#
# So this pass bounds the run and refuses any rc outside {0,65}.
set -uo pipefail
cd "$(dirname "$0")/../.."

ES="ios/Bain Luck/Bain Luck/Utilities/EventState.swift"
TMP=$(mktemp -d)
cp "$ES" "$TMP/es.pre"
restore() { cp "$TMP/es.pre" "$ES"; }
trap 'echo; echo "interrupted — restoring"; restore; exit 130' INT TERM

apply() {
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

# Bounded: a suite that has not finished in 12 minutes is hung, not slow (a
# healthy run is ~2 min). Reported as HUNG, never as a kill.
run_suite() {
  xcodebuild test -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    > "$TMP/out.txt" 2>&1 &
  local pid=$! waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10; waited=$((waited+10))
    if [ "$waited" -ge 720 ]; then kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; echo 9999; return; fi
  done
  wait "$pid"; echo $?
}

classify() {
  local rc=$1
  [ "$rc" = 9999 ] && { echo REFUSED-HUNG; return; }
  if /usr/bin/grep -qE "^.*\.swift:[0-9]+:[0-9]+: error: " "$TMP/out.txt"; then
    echo REFUSED-DID-NOT-COMPILE; return
  fi
  # gotcha #124: only 0 and 65 are xcodebuild answering the question asked.
  case "$rc" in
    0)  echo SURVIVED ;;
    65) if /usr/bin/grep -q "Executed .* tests, with" "$TMP/out.txt"; then echo KILLED
        else echo REFUSED-SUITE-NEVER-RAN; fi ;;
    *)  echo "REFUSED-RC-$rc-IS-NOT-A-VERDICT" ;;
  esac
}

mutant() {
  local name=$1 needle=$2 repl=$3
  restore
  if ! apply "$ES" "$needle" "$repl"; then
    echo "$name  REFUSED — needle not found"; restore; return
  fi
  local rc verdict by
  rc=$(run_suite); verdict=$(classify "$rc")
  by=$(/usr/bin/grep -oE "test[A-Za-z]+\]' failed|-\[SuspendedCardSaysItOnce6528Tests test[A-Za-z]+\] : " "$TMP/out.txt" \
       | /usr/bin/sed 's/.*\(test[A-Za-z]*\).*/\1/' | sort -u | tr '\n' ' ')
  [ "$verdict" = KILLED ] || by=$(/usr/bin/grep -oE "\.swift:[0-9]+:[0-9]+: error: .*" "$TMP/out.txt" | head -1)
  echo "$name"
  echo "    rc=$rc  $verdict  ${by:0:150}"
  restore
  cmp -s "$TMP/es.pre" "$ES" || echo "    ^^^ TREE NOT RESTORED"
}

echo "=== pass 2 — the three mutants pass 1 could not grade ==="

mutant "M3  the date is dropped from the slot (#6361 left unbuilt on native)" \
'[lastScoreFragment(away: away, home: home), date]' \
'[lastScoreFragment(away: away, home: home), String?.none]'

mutant "M4  the score tail is dropped" \
'[lastScoreFragment(away: away, home: home), date]' \
'[String?.none, date]'

mutant "M5  empty joins to \"\" — an empty Text that still costs its 6pt of spacing" \
'        return parts.isEmpty ? nil : parts.joined(separator: " · ")' \
'        return parts.joined(separator: " · ")'

echo
restore
cmp -s "$TMP/es.pre" "$ES" && echo "tree restored byte-identical" || echo "TREE NOT RESTORED"
