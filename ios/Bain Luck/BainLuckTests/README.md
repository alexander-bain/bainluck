# BainLuckTests

Unit tests for the native app. **These are not yet wired into an Xcode target** —
the project (`Bain Luck.xcodeproj`) currently ships with *no* unit-test bundle, and
this folder sits **outside** the app target's file-system-synchronized group on
purpose so `import XCTest` cannot leak into the app and break archiving.

## To run these tests

1. In Xcode: File ▸ New ▸ Target… ▸ **Unit Testing Bundle**, name it `Bain LuckTests`,
   host application = `Bain Luck`.
2. Add this folder (`BainLuckTests/`) to the new target (Xcode 16 default:
   create it as a synchronized group so files auto-register).
3. `xcodebuild test -project "Bain Luck.xcodeproj" -scheme "Bain Luck" \
      -destination 'platform=iOS Simulator,name=iPhone 16'`

Module under test: `Bain_Luck` (derived from the `Bain Luck` product name; the
space becomes an underscore). `ENABLE_TESTABILITY = YES` is already set on the
app's Debug config, so `@testable import Bain_Luck` works.

## Files

- `CalibrationMathTests.swift` — #894/L2-82: proves `CalibrationMath` reproduces the
  web page's ECE/MCE/Brier numbers exactly and that payload v2 decodes (sample
  gate, held-out categories, corrections, nullable fields). Expected values were
  cross-computed from `frontend/lib/calibrationMath.ts` on the same fixture.
- `CalibrationPayloadV2.sample.json` — a trimmed **real** `/api/calibration`
  payload-v2 capture (structure-preserving), for reference and future bundle-based
  decode tests.

## Verified without a test target

Because there is no test bundle yet, the load-bearing logic was verified with the
command-line Swift compiler on the pure-Foundation sources:

```
swiftc "Bain Luck/Models/CalibrationModels.swift" \
       "Bain Luck/Utilities/CalibrationMath.swift" main.swift
```

decoding this fixture and asserting the same expected values this XCTest asserts.
