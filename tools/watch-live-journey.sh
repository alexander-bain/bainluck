#!/bin/bash
# Hosted Watch live journey: never select or touch a shared local simulator.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'This gate runs only on a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/watch-live-journey"
mkdir -p "$OUT"
PHASE=preflight
failure() {
  local status=$?
  echo "Watch live journey unpaid: $PHASE failed (exit $status)." >&2
  if [[ -f "$OUT/preflight.log" ]]; then tail -80 "$OUT/preflight.log" >&2; fi
  if [[ -f "$OUT/tests.log" ]]; then tail -80 "$OUT/tests.log" >&2; fi
  exit "$status"
}
trap failure ERR
: > "$OUT/preflight.log"
: > "$OUT/tests.log"
# Fresh build and result paths prevent old compiled bundles or receipts passing.
RUN="$(mktemp -d "$OUT/run.XXXXXX")"
DERIVED="$RUN/DerivedData"
RESULT="$RUN/BainLuckWatchUITests.xcresult"
printf '%s\n' "$DERIVED" > "$OUT/derived-data.txt"
printf '%s\n' "$RESULT" > "$OUT/result-bundle.txt"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
printf '%s\n' "$SHA" > "$OUT/source.txt"
python3 - "$SHA" "$OUT/receipt.json" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[2]).write_text(json.dumps({'sha': sys.argv[1], 'verdict': 'UNPAID', 'reason': 'Hosted Watch live journey has not completed'}, indent=2) + '\n')
PY
xcodebuild -version > "$OUT/toolchain.txt" 2>> "$OUT/preflight.log"
xcrun swiftc --version >> "$OUT/toolchain.txt" 2>> "$OUT/preflight.log"
xcodebuild -showsdks > "$OUT/sdks.txt" 2>> "$OUT/preflight.log"
xcrun simctl list --json > "$OUT/simulators.json" 2>> "$OUT/preflight.log"
SDK_VERSION="$(xcrun --sdk watchsimulator --show-sdk-version 2>> "$OUT/preflight.log")"
printf '%s\n' "$SDK_VERSION" > "$OUT/sdk-version.txt"
python3 - "$OUT/simulators.json" "$SDK_VERSION" > "$OUT/destination-spec.txt" 2>> "$OUT/preflight.log" <<'PY'
import json, sys
from pathlib import Path
info = json.loads(Path(sys.argv[1]).read_text())
runtimes = sorted((r for r in info['runtimes']
                   if r.get('isAvailable') and '.watchOS-' in r['identifier']
                   and r['version'].split('.')[:2] == sys.argv[2].split('.')[:2]),
                  key=lambda r: tuple(int(v) for v in r['version'].split('.')), reverse=True)
for runtime in runtimes:
    # Pick a type already advertised by this runtime, but never its device UDID.
    for device in info['devices'].get(runtime['identifier'], []):
        kind = device.get('deviceTypeIdentifier', '')
        if device.get('isAvailable') and 'Apple-Watch' in kind:
            print(kind)
            print(runtime['identifier'])
            raise SystemExit(0)
raise SystemExit(f'No available Watch device/runtime matching watchsimulator SDK {sys.argv[2]}; hosted UI gate is unpaid')
PY
DEVICE_TYPE="$(sed -n '1p' "$OUT/destination-spec.txt")"
RUNTIME="$(sed -n '2p' "$OUT/destination-spec.txt")"
PHASE='disposable Watch simulator creation'
TEST_UDID="$(xcrun simctl create "codex-watch-live-journey" "$DEVICE_TYPE" "$RUNTIME" 2>> "$OUT/preflight.log")"
printf '%s\n' "$TEST_UDID" > "$OUT/destination.txt"
PHASE='disposable unpaired Watch simulator boot (pairing, if required, is an unpaid gate)'
xcrun simctl boot "$TEST_UDID" >> "$OUT/preflight.log" 2>&1
xcrun simctl bootstatus "$TEST_UDID" -b >> "$OUT/preflight.log" 2>&1
# Release compiles out WatchUIFixture. Select only the real-data test class;
# existing fixture journeys remain confined to their ordinary Debug workflow.
PHASE='Release production picker and relaunch'
if xcodebuild test -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme BainLuckWatchUITests -configuration Release \
  -only-testing:BainLuckWatchUITests/LiveSelectedGameJourneyTests \
  -destination "platform=watchOS Simulator,id=$TEST_UDID" \
  -derivedDataPath "$DERIVED" -resultBundlePath "$RESULT" \
  -parallel-testing-enabled NO -jobs 2 -collect-test-diagnostics never \
  -test-timeouts-enabled YES -maximum-test-execution-time-allowance 300 \
  CODE_SIGNING_ALLOWED=NO \
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
  > "$OUT/tests.log" 2>&1; then
  TEST_EXIT=0
else
  TEST_EXIT=$?
fi
printf '%s\n' "$TEST_EXIT" > "$OUT/test-exit.txt"
printf 'xcodebuild exit: %s\n' "$TEST_EXIT"
if [[ "$TEST_EXIT" -ne 0 ]]; then
  echo 'Watch live journey unpaid; if this toolchain requires pairing, no existing iPhone has been touched.' >&2
  tail -80 "$OUT/tests.log" >&2
fi
PHASE='read-only selected identity and refreshed snapshot evidence'
# Read only this newly created simulator's app container; never seed defaults.
# simctl may run tests in a clone: disable cloning via parallel-testing NO above
# and fail closed if the selected app is absent on our recorded destination.
if [[ "$TEST_EXIT" -eq 0 ]]; then
  APP_DATA="$(xcrun simctl get_app_container "$TEST_UDID" com.bainluck.BainLuckWatch.watchkitapp data)"
  cp "$APP_DATA/Library/Preferences/com.bainluck.BainLuckWatch.watchkitapp.plist" "$OUT/preferences.plist"
fi
PHASE='live journey evidence receipt'
python3 "$ROOT/tools/watch_live_receipt.py" --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" --sha "$SHA" --preferences "$OUT/preferences.plist" \
  --output "$OUT/receipt.json"
