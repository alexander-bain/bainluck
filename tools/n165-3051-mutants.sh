#!/bin/bash
# native/165 — mutation battery for #3051 (the hero's since-open caption that
# disagreed with the two numbers it sits between). Same classifier as
# n147b-5949-mutants.sh: a mutant that fails to COMPILE exits 65 exactly like a
# failing test and is reported as ungraded, never counted as a kill.
set -u
cd "$(dirname "$0")/.." || exit 2

CAP="ios/Bain Luck/Bain Luck/Utilities/SinceOpenCaption.swift"
SUITES=(
  -only-testing:BainLuckTests/SinceOpenCaptionTests
  -only-testing:BainLuckTests/DrawPricedWinnerTests
  -only-testing:BainLuckTests/RenderedPercentContractTests
)

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n165-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n165-mutant-backup.swift
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
  cp /tmp/n165-mutant-backup.swift "$file"
  if /usr/bin/grep -q "BUILD FAILED\|Testing cancelled because the build failed" /tmp/n165-mutant.log; then
    echo "$name: DID NOT COMPILE — not graded, rewrite the mutant"
  elif [ "$code" = "0" ]; then
    echo "$name: SURVIVED  <-- the guard does not see this"
  else
    echo "$name: killed by a test"
  fi
}

echo "=== base ==="
base=$(run_suite)
echo "base exit: $base"
[ "$base" = "0" ] || { echo "BASE IS RED — battery meaningless"; exit 1; }
/usr/bin/grep -E "Executed [0-9]+ tests" /tmp/n165-mutant.log | tail -1

# M1 — THE DEFECT, restored in its new clothes: the journey runs backwards, so
#      the caption still quotes two printed integers and still lies.
mutate "M1 journey-runs-backwards" "$CAP" \
  'return (text: "\(subject) \(from) \u{2192} \(to) since open", isHome: trend.isHome)' \
  'return (text: "\(subject) \(to) \u{2192} \(from) since open", isHome: trend.isHome)'

# M2 — #1830 undone: the caption always names home, so a home FALL prints under
#      a name that rose. This is the exact frame Alex misread.
mutate "M2 always-names-home" "$CAP" \
  'let subject = trend.isHome ? names.home : names.away' \
  'let subject = names.home'

# M3 — the away subject keeps its name and quotes HOME's two levels.
mutate "M3 away-subject-quotes-home" "$CAP" \
  'to = formatProbability(awayNow, renderedPercent: nowPcts[0])' \
  'to = formatProbability(pair.home, renderedPercent: nowPcts[1])'

# M4 — the away branch reads the pair at the wrong index: `[away, home]` is
#      positional and index 1 is home's.
mutate "M4 away-branch-off-by-one-index" "$CAP" \
  'from = formatProbability(awayOpen, renderedPercent: openPcts[0])' \
  'from = formatProbability(awayOpen, renderedPercent: openPcts[1])'

# M5 — the current end stops taking the SERVER's integer and re-rounds locally,
#      so the caption prints a number the hero above it did not.
mutate "M5 current-end-ignores-the-served-pair" "$CAP" \
  'servedAway: servedAwayPercent, servedHome: servedHomePercent)' \
  'servedAway: nil, servedHome: nil)'

# M6 — the trap `duelPercents` documents, from the other side: `current_odds`'
#      rounding handed to `opening_odds`' probabilities. The pair still sums to
#      100, so no sum guard can see it.
mutate "M6 served-pair-leaks-onto-the-opening-line" "$CAP" \
  'away: opened.away, home: opened.home,
            servedAway: nil, servedHome: nil)' \
  'away: opened.away, home: opened.home,
            servedAway: servedAwayPercent, servedHome: servedHomePercent)'

# M7 — #5271's withheld slot forgotten: a draw-priced sport rounds home through
#      the duel contract, whose answer for one side can be `100 − other`.
mutate "M7 draw-priced-uses-the-complements-rounding" "$CAP" \
  'to = pair.away == nil
                ? formatProbability(pair.home)
                : formatProbability(pair.home, renderedPercent: nowPcts[1])' \
  'to = formatProbability(pair.home, renderedPercent: nowPcts[1])'

# M8 — the marker rule dropped at the current end: the integer is interpolated
#      raw, so a 0.996 prints `100%` under a hero that says `>99%`. This is the
#      web arm's #6064 arriving in Swift.
mutate "M8 current-end-loses-the-marker-rule" "$CAP" \
  'to = pair.away == nil
                ? formatProbability(pair.home)
                : formatProbability(pair.home, renderedPercent: nowPcts[1])' \
  'to = "\(nowPcts[1] ?? 0)%"'

# M9 — the marker rule dropped at the OPENING end only, which is the asymmetric
#      form: one formatter per end, the thing the test exists to forbid.
mutate "M9 opening-end-loses-the-marker-rule" "$CAP" \
  'from = opened.away == nil
                ? formatProbability(opened.home)
                : formatProbability(opened.home, renderedPercent: openPcts[1])' \
  'from = "\(openPcts[1] ?? 0)%"'

# M10 — the 2pp gate opened to every flicker.
mutate "M10 gate-fires-on-any-move" "$CAP" \
  'guard abs(pair.home - openingHome) > 0.02 else { return nil }' \
  'guard abs(pair.home - openingHome) > 0.0 else { return nil }'

# M11 — the absence the tests pin as deliberate, filled in by re-derivation: a
#      two-way sport with no served away opening invents `1 − home`.
mutate "M11 opening-away-re-derived-from-the-complement" "$CAP" \
  'away: openingAway, home: openingHome, sport: sport) else { return nil }' \
  'away: openingAway ?? (1 - openingHome), home: openingHome, sport: sport) else { return nil }'

# M12 — the colour stops following the subject, so a named riser is painted in
#       the other team's colour. #1830's fix has two halves and this is the
#       second one.
mutate "M12 colour-detaches-from-the-subject" "$CAP" \
  'isHome: trend.isHome)' \
  'isHome: true)'

echo "=== done; tree restored ==="
git -C . diff --stat -- "$CAP"
