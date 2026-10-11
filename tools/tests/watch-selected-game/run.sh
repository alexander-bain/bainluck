#!/bin/sh
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
TEST_BINARY=$(mktemp -d /tmp/watch-selected-game.XXXXXX)
trap 'rm -rf "$TEST_BINARY"' EXIT
swiftc -parse-as-library -swift-version 5 -D DEBUG \
  "$ROOT/ios/Bain Luck/Bain Luck/Utilities/GameContinuation.swift" \
  "$ROOT/ios/Bain Luck/Bain Luck/Utilities/PeriodLabel.swift" \
  "$ROOT/ios/Bain Luck/Bain Luck/Utilities/RenderedPercent.swift" \
  "$ROOT/ios/Bain Luck/Bain Luck/Utilities/DrawPricedWinner.swift" \
  "$ROOT/ios/Bain Luck/Bain Luck/Utilities/SportVocab.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchLaunchRoute.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchComplicationSnapshot.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchComplicationPublisher.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchSelectedGameModels.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchSelectedGameStore.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchFeedModels.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchGamePickerStore.swift" \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchUIFixture.swift" \
  "$ROOT/tools/tests/watch-selected-game/LaunchRouteChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/ComplicationChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/ContinuationChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/FlowChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/IdentityChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/PickerChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/HTTPChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/ProbabilityChecks.swift" \
  "$ROOT/tools/tests/watch-selected-game/main.swift" \
  -o "$TEST_BINARY/checks"
"$TEST_BINARY/checks"
