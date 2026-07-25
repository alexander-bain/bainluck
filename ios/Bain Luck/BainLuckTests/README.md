# BainLuckTests

Unit tests for the native app. **This folder is wired into a real Xcode unit-test
bundle** — the `BainLuckTests` target (host application = `Bain Luck`, added in
L2-181). The folder is a file-system-synchronized group, so new `.swift` files
here auto-register into the target; pure-Foundation sources from other targets
(the watch guess flow, the widget decoder) are compiled in via per-file target
membership exceptions in `project.pbxproj`.

## To run these tests

```
xcodebuild test -project "Bain Luck.xcodeproj" -scheme "BainLuckTests" \
    -destination 'platform=iOS Simulator,name=iPhone 16'
```

(There is also a shared `BainLuckTests.xcscheme`.) Add
`OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'` when building
headless in a sandbox — see CLAUDE.md gotcha #50.

Module under test: `Bain_Luck` (derived from the `Bain Luck` product name; the
space becomes an underscore). `ENABLE_TESTABILITY = YES` is set on the app's
Debug config, so `@testable import Bain_Luck` works for main-app types. Sources
compiled directly into the bundle (e.g. `WatchGuessPool`, `WatchGuessViewModel`,
`WidgetFeedDecoding`) are referenced without an import.

## Files

- `CalibrationMathTests.swift` — #894/L2-82: proves `CalibrationMath` reproduces the
  web page's ECE/MCE/Brier numbers exactly and that payload v2 decodes (sample
  gate, held-out categories, corrections, nullable fields). Expected values were
  cross-computed from `frontend/lib/calibrationMath.ts` on the same fixture.
- `CalibrationPayloadV2.sample.json` — a trimmed **real** `/api/calibration`
  payload-v2 capture (structure-preserving), for reference and future bundle-based
  decode tests.
- `FeedConfidenceTests.swift` — #490/L2-172: confidence signal decode + native math parity.
- `FeedConceptDecodeTests.swift` — L2-179: concept card survives the full feed decode.
- `WatchGuessPoolTests.swift` — L2-180: the Watch Higher/Lower deck is futures-only
  (no event id ever submitted as `market_id`).
- `WatchGuessViewModelTests.swift` — L2-182: a failed Watch guess is honest and
  retryable (no premature result reveal, no advance, no double-submit), driven by
  an injected `WatchGuessBackend` mock.
- `WidgetFeedDecodeTests.swift` — L2-182: the widget's production tolerant decoder
  (`WidgetFeedResponse`/`WidgetDiscoverFeedResponse`) skips malformed
  concept/tournament/outcome items instead of blanking the whole widget.
- `MorningDigestPreferenceTests.swift` — #1159: Morning Digest push preference decode
  defaults (no silent opt-in) + optimistic-update-with-rollback.
