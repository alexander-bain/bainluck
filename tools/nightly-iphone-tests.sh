#!/bin/bash
# Run the complete iPhone unit/UI test scheme (`BainLuckTests`) once on a disposable
# iPhone simulator on a hosted macOS runner without any test-selection subset filters.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${NIGHTLY_IPHONE_OUT:-$ROOT/build/nightly-iphone-tests}"
DERIVED="$OUT/DerivedData"
RESULT_BUNDLE="$OUT/BainLuckTests.xcresult"
mkdir -p "$OUT"
rm -rf "$RESULT_BUNDLE"

if [[ -z "${DEVELOPER_DIR:-}" ]]; then
  if [[ -d /Applications/Xcode_27.2.app/Contents/Developer ]]; then
    export DEVELOPER_DIR=/Applications/Xcode_27.2.app/Contents/Developer
  elif [[ -d /Applications/Xcode_27.0.app/Contents/Developer ]]; then
    export DEVELOPER_DIR=/Applications/Xcode_27.0.app/Contents/Developer
  fi
fi

SIM_UDID=""
cleanup() {
  if [[ -n "$SIM_UDID" ]]; then
    xcrun simctl shutdown "$SIM_UDID" >/dev/null 2>&1 || true
    xcrun simctl delete "$SIM_UDID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

SHA="$(git -C "$ROOT" rev-parse HEAD)"
printf '%s\n' "$SHA" > "$OUT/source.txt"
xcodebuild -version > "$OUT/toolchain.txt"
xcrun simctl list --json > "$OUT/simulators.json"
SDK_VERSION="$(xcrun --sdk iphonesimulator --show-sdk-version)"

python3 - "$OUT/simulators.json" "$SDK_VERSION" > "$OUT/destination-spec.txt" <<'PY'
import json
import sys
from pathlib import Path

info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
target_major_minor = sys.argv[2].split(".")[:2]
runtimes = sorted(
    (
        r
        for r in info.get("runtimes", [])
        if r.get("isAvailable")
        and ".iOS-" in r.get("identifier", "")
        and r.get("version", "").split(".")[:2] == target_major_minor
    ),
    key=lambda r: tuple(int(v) for v in r["version"].split(".")),
    reverse=True,
)
for runtime in runtimes:
    for device in info.get("devices", {}).get(runtime["identifier"], []):
        kind = device.get("deviceTypeIdentifier", "")
        if device.get("isAvailable") and "iPhone" in kind:
            print(kind)
            print(runtime["identifier"])
            raise SystemExit(0)
raise SystemExit(f"No available iPhone simulator matching SDK {sys.argv[2]}")
PY

DEVICE_TYPE="$(sed -n '1p' "$OUT/destination-spec.txt")"
RUNTIME="$(sed -n '2p' "$OUT/destination-spec.txt")"
SIM_UDID="$(xcrun simctl create "nightly-iphone-tests-$$" "$DEVICE_TYPE" "$RUNTIME")"
printf '%s\n' "$SIM_UDID" > "$OUT/destination.txt"
xcrun simctl boot "$SIM_UDID"
xcrun simctl bootstatus "$SIM_UDID" -b

# Resolve packages once before timing tests.
xcodebuild -resolvePackageDependencies \
  -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme BainLuckTests \
  -derivedDataPath "$DERIVED" \
  > "$OUT/resolve.log" 2>&1

set +e
xcodebuild test \
  -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme BainLuckTests \
  -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIM_UDID" \
  -derivedDataPath "$DERIVED" \
  -resultBundlePath "$RESULT_BUNDLE" \
  -parallel-testing-enabled NO \
  -jobs 2 \
  -collect-test-diagnostics never \
  -test-timeouts-enabled YES \
  -maximum-test-execution-time-allowance 180 \
  CODE_SIGNING_ALLOWED=NO \
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
  > "$OUT/tests.log" 2>&1
TEST_EXIT=$?
set -e

printf '%s\n' "$TEST_EXIT" > "$OUT/test-exit.txt"
if [[ "$TEST_EXIT" -ne 0 ]]; then
  tail -100 "$OUT/tests.log" >&2 || true
fi

python3 "$ROOT/tools/watch_iphone_receipt.py" \
  --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" \
  --sha "$SHA" \
  --output "$OUT/receipt.json" \
  --suite-name "All tests" \
  --min-tests 1
