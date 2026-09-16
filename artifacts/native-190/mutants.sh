#!/usr/bin/env bash
# native/190 (#6544) — mutation battery for HeroSaysTheCountdownOnce6544Tests.
#
# Built on native/189's PASS 2 rig, which is the corrected one: pass 1 there
# scored 8 killed when only 7 were real, because `xcodebuild` exits 65 for a
# compile error and for a test failure alike, and because a run killed on a hang
# (rc 143) left a partial log containing a per-class "Executed N tests" line that
# read exactly like a kill. So, unchanged from that pass and load-bearing here:
#
#   * a verdict is taken from rc AND the log — a kill needs the build to have
#     succeeded and a test to have failed (gotcha #124: only 0 and 65 are
#     xcodebuild answering the question asked);
#   * every run is bounded, and a run that outlives the bound reports
#     REFUSED-HUNG, never a kill;
#   * a mutant whose needle does not apply reports REFUSED, because a mutation
#     that never landed reads exactly like a mutation the suite caught;
#   * INT/TERM restore the tree, because pass 1 left a mutant in the working
#     copy when it was interrupted and `git status` was the only thing that
#     noticed.
#
# This battery touches THREE files, so the restore is a loop rather than one cp.
set -uo pipefail
cd "$(dirname "$0")/../.."

HERO="ios/Bain Luck/Bain Luck/Views/EventDetailView.swift"
BADGE="ios/Bain Luck/Bain Luck/Components/StatusBadge.swift"
STATE="ios/Bain Luck/Bain Luck/Utilities/EventState.swift"
FMT="ios/Bain Luck/Bain Luck/Utilities/FormattingUtilities.swift"
FILES=("$HERO" "$BADGE" "$STATE" "$FMT")

TMP=$(mktemp -d)
for i in "${!FILES[@]}"; do cp "${FILES[$i]}" "$TMP/pre.$i"; done
restore() { for i in "${!FILES[@]}"; do cp "$TMP/pre.$i" "${FILES[$i]}"; done; }
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

run_suite() {
  xcodebuild test -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    > "$TMP/out.txt" 2>&1 &
  local pid=$! waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10; waited=$((waited+10))
    if [ "$waited" -ge 900 ]; then kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; echo 9999; return; fi
  done
  wait "$pid"; echo $?
}

classify() {
  local rc=$1
  [ "$rc" = 9999 ] && { echo REFUSED-HUNG; return; }
  if /usr/bin/grep -qE "^.*\.swift:[0-9]+:[0-9]+: error: " "$TMP/out.txt"; then
    echo REFUSED-DID-NOT-COMPILE; return
  fi
  case "$rc" in
    0)  echo SURVIVED ;;
    65) if /usr/bin/grep -q "Executed .* tests, with" "$TMP/out.txt"; then echo KILLED
        else echo REFUSED-SUITE-NEVER-RAN; fi ;;
    *)  echo "REFUSED-RC-$rc-IS-NOT-A-VERDICT" ;;
  esac
}

# Which of MY tests FAILED. `'` + "failed" is load-bearing: xcodebuild prints the
# same `-[Class testName]` shape for `started` and `passed` too, so the obvious
# grep for the class name reports every test in the file on every mutant and
# reads like a rout. M1's first run said exactly that before this was corrected.
#
# `outsiders` is the other half: a mutant killed only by a pre-existing test
# elsewhere in the suite is not evidence about THIS guard, and it looks
# identical in the verdict column.
killers() {
  /usr/bin/grep -oE "HeroSaysTheCountdownOnce6544Tests test[A-Za-z]+\]' failed" "$TMP/out.txt" \
    | /usr/bin/sed "s/.*\(test[A-Za-z]*\)\]' failed/\1/" | sort -u | tr '\n' ' '
}

outsiders() {
  /usr/bin/grep -oE "Test Case '-\[[A-Za-z_.]+ test[A-Za-z]+\]' failed" "$TMP/out.txt" \
    | /usr/bin/grep -v HeroSaysTheCountdownOnce6544Tests | sort -u | wc -l | tr -d ' '
}

mutant() {
  local name=$1 file=$2 needle=$3 repl=$4
  restore
  if ! apply "$file" "$needle" "$repl"; then
    echo "$name"; echo "    REFUSED — needle not found in $(basename "$file")"; restore; return
  fi
  local rc verdict by
  rc=$(run_suite); verdict=$(classify "$rc")
  if [ "$verdict" = KILLED ]; then
    by=$(killers)
    local out; out=$(outsiders)
    [ -z "$by" ] && by="!! NOT killed by this file's tests — "
    [ "$out" != 0 ] && by="$by(+$out failing test(s) outside this file)"
  else
    by=$(/usr/bin/grep -oE "\.swift:[0-9]+:[0-9]+: error: .*" "$TMP/out.txt" | head -1)
  fi
  echo "$name"
  echo "    rc=$rc  $verdict  ${by:0:200}"
  restore
  for i in "${!FILES[@]}"; do
    cmp -s "$TMP/pre.$i" "${FILES[$i]}" || echo "    ^^^ TREE NOT RESTORED: ${FILES[$i]}"
  done
}

echo "=== native/190 #6544 — 10 mutants + a clean-head control ==="
echo

# ── The defect itself, put back two different ways ───────────────────────────
# M1 is the faithful reintroduction: what a reader restoring the deleted block
# would actually type. M2 is the same defect written WITHOUT formatCountdown, so
# the `"In\(` ban is proved to stand on its own rather than riding the second
# ban's coat-tails.
mutant "M1  the centre column prints the countdown again, via formatCountdown" "$HERO" \
'                    // Opening odds below probability for live games' \
'                    if let c = event.commenceTime?.asDate, let t = formatCountdown(from: c),
                       !isLive, !isFinished {
                        Text("In \(t)")
                            .font(.caption)
                            .foregroundStyle(.blue)
                    }
                    // Opening odds below probability for live games'

mutant "M2  the same duplicate, hand-rolled so it never calls formatCountdown" "$HERO" \
'                    // Opening odds below probability for live games' \
'                    if let c = event.commenceTime?.asDate, !isLive, !isFinished {
                        let mins = Int(c.timeIntervalSinceNow / 60)
                        Text("In \(mins / 1440)d \((mins % 1440) / 60)h")
                            .font(.caption)
                            .foregroundStyle(.blue)
                    }
                    // Opening odds below probability for live games'

# ── The tick: the regression the deletion could have shipped ─────────────────
mutant "M3  the TimelineView is removed as a pointless wrapper — the chip freezes" "$HERO" \
'                TimelineView(.periodic(from: .now, by: 60)) { _ in
                    heroStatusBadge(event)
                }' \
'                heroStatusBadge(event)'

mutant "M4  the tick is coarsened to ten minutes" "$HERO" \
'TimelineView(.periodic(from: .now, by: 60))' \
'TimelineView(.periodic(from: .now, by: 600))'

# ── The omission a ban cannot see: the surviving copy deleted or reworded ────
mutant "M5  StatusBadge stops saying \"In\" — the chip becomes a bare duration" "$BADGE" \
'                    Text("In \(countdown)")' \
'                    Text(countdown)'

mutant "M6  the chip is dropped from the hero entirely" "$HERO" \
'                TimelineView(.periodic(from: .now, by: 60)) { _ in
                    heroStatusBadge(event)
                }' \
'                TimelineView(.periodic(from: .now, by: 60)) { _ in
                    EmptyView()
                }'

mutant "M7  the scheduled arm stops being handed a commence time" "$HERO" \
'            StatusBadge(
                status: "scheduled",
                commenceTime: event.commenceTime,
                venueSettled: event.venueSettled == true)' \
'            StatusBadge(
                status: "scheduled",
                venueSettled: event.venueSettled == true)'

# ── The predicates the safety argument rests on ──────────────────────────────
# If either of these stops consulting the clock, a fixture that has not kicked
# off takes a badge arm ABOVE the countdown and the hero loses the number
# outright — the exact harm the deleted duplicate used to mask.
mutant "M8  isSuspendedAndStarted forgets the clock" "$STATE" \
'        isSuspended(status) && hasStarted(commenceTime: commenceTime, now: now)' \
'        isSuspended(status)'

mutant "M9  showsVenueSettledVerdict forgets the clock" "$STATE" \
'        guard !isFinished(status) else { return false }
        return hasStarted(commenceTime: commenceTime, now: now)' \
'        guard !isFinished(status) else { return false }
        return true'

mutant "M10 formatCountdown loses its minute resolution" "$FMT" \
'    let totalMinutes = Int(interval / 60)' \
'    let totalMinutes = Int(interval / 3600) * 60'

# ── Control, run LAST so the tree it grades is the restored one ──────────────
echo "C   clean head — MUST survive"
restore
rc=$(run_suite); echo "    rc=$rc  $(classify "$rc")"

echo
restore
ok=1
for i in "${!FILES[@]}"; do
  cmp -s "$TMP/pre.$i" "${FILES[$i]}" || { echo "TREE NOT RESTORED: ${FILES[$i]}"; ok=0; }
done
[ "$ok" = 1 ] && echo "tree restored byte-identical (4 files)"
