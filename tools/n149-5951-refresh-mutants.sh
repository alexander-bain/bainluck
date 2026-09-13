#!/bin/bash
# native/149 — mutation battery for the #5951 client half (a pull-to-refresh
# handed back every card the reader had just swiped away).
#
# Same classifier as n147/n148's batteries, for the same reason: a mutant that
# does not COMPILE exits 65 exactly like a failing test, so the exit code alone
# cannot tell you whether a guard fired. Every verdict is read off the log.
set -u
cd "$(dirname "$0")/.." || exit 2

VIEW="ios/Bain Luck/Bain Luck/Views/DiscoverView.swift"
SUITES=(
  -only-testing:BainLuckTests/ARefreshDoesNotUndoASwipe5951Tests
  -only-testing:BainLuckTests/DiscoverClientFilterFloorTests
  -only-testing:BainLuckTests/DiscoverPresentationTests
)

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n149-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n149-mutant-backup.swift
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
  cp /tmp/n149-mutant-backup.swift "$file"
  if /usr/bin/grep -q "BUILD FAILED\|Testing cancelled because the build failed" /tmp/n149-mutant.log; then
    echo "$name: DID NOT COMPILE — not graded, rewrite the mutant"
  elif [ "$code" = "0" ]; then
    echo "$name: SURVIVED  <-- the guard does not see this"
  else
    echo "$name: killed by a test ($(/usr/bin/grep -cE "error: -\[BainLuck" /tmp/n149-mutant.log) failing assertions)"
  fi
}

echo "=== base ==="
base=$(run_suite)
echo "base exit: $base"
[ "$base" = "0" ] || { echo "BASE IS RED — battery meaningless"; exit 1; }
/usr/bin/grep -E "Executed [0-9]+ tests" /tmp/n149-mutant.log | tail -1

# M1 — THE DEFECT, RESTORED AT THE CALL SITE. The helper stays correct and
# perfectly tested; `refreshFeed` simply stops using it. This is the mutant the
# reach arm exists for, and the only thing that can kill it is that arm.
mutate "M1 refresh-empties-the-store-again" "$VIEW" \
  '        dismissedAt = Self.dismissStoreAfterRefresh(dismissedAt)' \
  '        dismissedAt.removeAll()'

# M2 — the defect moved inside the helper: the call site is right, the helper
# returns nothing. Kills the two 🔴 arms.
mutate "M2 helper-returns-empty" "$VIEW" \
  '        let cutoff = now - dismissTTL
        return store.filter { $0.value >= cutoff }' \
  '        _ = now
        return [:]'

# M3 — the helper never ages anything, so a session that is never relaunched
# holds a swipe past its 14 days. Kills the TTL arm only.
mutate "M3 no-prune" "$VIEW" \
  '        let cutoff = now - dismissTTL
        return store.filter { $0.value >= cutoff }' \
  '        _ = now
        return store'

# M4 — the cutoff points the wrong way, which keeps the dead and drops the live.
mutate "M4 cutoff-sign-flipped" "$VIEW" \
  '        let cutoff = now - dismissTTL' \
  '        let cutoff = now + dismissTTL'

# M5 — the prune becomes an exclusive comparison at the boundary. Equivalent
# UNLESS a test sits exactly on the cutoff, so one does: `loadDismissed` and
# `saveDismissed` both keep `value >= cutoff`, and three prunes of one store
# disagreeing about the boundary is a real defect, not a rounding taste.
mutate "M5 boundary-exclusive" "$VIEW" \
  '        return store.filter { $0.value >= cutoff }' \
  '        return store.filter { $0.value > cutoff }'

# M6 — #5453's grace window is removed, so the floor rebuilds a short page out of
# this sitting's rejects. Composed with the refresh, that is the defect wearing
# the other sign: the store survives and the floor hands the cards back anyway.
mutate "M6 grace-window-removed" "$VIEW" \
  '        return now - dismissedAt < backfillGraceWindow' \
  '        return false'

# M7 — the floor stops flooring. Control on the #1221 half: the refresh fix must
# not be what keeps a healthy page populated.
mutate "M7 floor-of-zero" "$VIEW" \
  '    static let feedFloor = 28' \
  '    static let feedFloor = 0'
