#!/bin/bash
# native/148 — mutation battery for the #5951 cooldown sink (Discover stopped
# handing the reader a page of the categories he has never touched).
#
# Same classifier as n147's battery, for the same reason: a mutant that does not
# COMPILE exits 65 exactly like a failing test, so the exit code alone cannot
# tell you whether a guard fired. Every verdict is read off the log.
set -u
cd "$(dirname "$0")/.." || exit 2

VIEW="ios/Bain Luck/Bain Luck/Views/DiscoverView.swift"
SUITES=(
  -only-testing:BainLuckTests/DiscoverCooldownMonoculture5951Tests
  -only-testing:BainLuckTests/DiscoverClientFilterFloorTests
  -only-testing:BainLuckTests/DiscoverSwipeTests
  -only-testing:BainLuckTests/DiscoverPresentationTests
)

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n148-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n148-mutant-backup.swift
  python3 - "$file" "$needle" "$replacement" <<'PY'
import sys
path, needle, replacement = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
if needle not in s:
    sys.exit(7)
open(path, 'w').write(s.replace(needle, replacement, 1))
PY
  if [ $? -eq 7 ]; then
    echo "$name: NEEDLE NOT FOUND — not graded"
    return
  fi
  local code
  code=$(run_suite)
  cp /tmp/n148-mutant-backup.swift "$file"
  if /usr/bin/grep -q "BUILD FAILED\|Testing cancelled because the build failed" /tmp/n148-mutant.log; then
    echo "$name: DID NOT COMPILE — not graded, rewrite the mutant"
  elif [ "$code" = "0" ]; then
    echo "$name: SURVIVED  <-- the guard does not see this"
  else
    echo "$name: killed by a test ($(/usr/bin/grep -cE "error: -\[BainLuck" /tmp/n148-mutant.log) failing assertions)"
  fi
}

echo "=== base ==="
base=$(run_suite)
echo "base exit: $base"
[ "$base" = "0" ] || { echo "BASE IS RED — battery meaningless"; exit 1; }
/usr/bin/grep -E "Executed [0-9]+ tests" /tmp/n148-mutant.log | tail -1

# M1 — the stage is turned off entirely: no sink, no personalization.
mutate "M1 sink-of-zero" "$VIEW" \
  'static let cooldownSinkPositions = 10' \
  'static let cooldownSinkPositions = 0'

# M2 — the partition comes back. This is the #5951 defect, restored.
mutate "M2 partition-restored" "$VIEW" \
  '        return Self.personalize(
            staleBase,
            dismissedAt: dismissedAt,
            now: Date().timeIntervalSince1970,
            isCooled: { interactionProfile.suppresses(category: itemCategory($0)) }
        )' \
  '        return Self.applyFloor(
            to: Self.applyDismissFloor(to: staleBase, dismissedAt: dismissedAt,
                                       now: Date().timeIntervalSince1970),
            keeping: { !interactionProfile.suppresses(category: itemCategory($0)) },
            backfillPriority: { interactionProfile.score(for: itemCategory($0)) },
            neverBackfill: { _ in false }
        )'

# M3 — the two personalization stages are wired in the wrong order.
#      MEASURED EQUIVALENT (first run of this battery): it survived, and it
#      should — `applyDismissFloor` removes by id whatever order it is handed,
#      so reversing the pair changes the running order of the kept cards and
#      nothing a reader can name. Kept in the battery as the record of that,
#      not as a hole; the doc comment on `personalize` was corrected to stop
#      claiming the safety property this mutant refutes.
mutate "M3 stages-reversed" "$VIEW" \
  '        applyCooldownSink(
            to: applyDismissFloor(to: base, dismissedAt: dismissedAt, now: now),
            isCooled: isCooled
        )' \
  '        applyDismissFloor(
            to: applyCooldownSink(to: base, isCooled: isCooled),
            dismissedAt: dismissedAt, now: now
        )'

# M4 — the dismiss stage is wired out of the composition altogether.
mutate "M4 dismiss-stage-dropped" "$VIEW" \
  'applyCooldownSink(
            to: applyDismissFloor(to: base, dismissedAt: dismissedAt, now: now),
            isCooled: isCooled
        )' \
  'applyCooldownSink(to: base, isCooled: isCooled)'

# M5 — the sink becomes a lift: cooled cards move UP.
mutate "M5 sink-is-a-lift" "$VIEW" \
  'rank: $0.served + ($0.cooled ? cooldownSinkPositions : 0))' \
  'rank: $0.served - ($0.cooled ? cooldownSinkPositions : 0))'

# M6 — the cooled-loses-ties rule goes, and the bound is off by one.
mutate "M6 ties-no-longer-favour-the-uncooled" "$VIEW" \
  'if $0.cooled != $1.cooled { return !$0.cooled }' \
  ''

# M7 — the served-position tiebreak goes.
#      MEASURED EQUIVALENT (first run): two cards can share a rank only if they
#      differ in `cooled` (rank = served + sink, and served is unique), so the
#      comparison is unreachable — it exists to make the comparator a total
#      order. Recorded here rather than "fixed" by a test that would have to
#      assert an unreachable branch.
mutate "M7 unstable-sort" "$VIEW" \
  'return $0.served < $1.served' \
  'return false'

# M8 — the sink starts removing again, which is the starvation #1221 fixed.
mutate "M8 sink-drops-the-cooled-tail" "$VIEW" \
  '            .map(\.item)
    }' \
  '            .map(\.item)
            .enumerated().filter { $0.offset < 28 }.map(\.element)
    }'

echo "=== done; tree restored ==="
git -C . diff --stat -- "$VIEW"
