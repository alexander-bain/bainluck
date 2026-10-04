#!/bin/bash
# #4932: full iPhone compatibility test for Watch changes, hosted runner only.
# Never selects or touches a simulator on Native's shared local Mac.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'This gate runs only on a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/watch-iphone-compatibility"
mkdir -p "$OUT"
# Fresh per-run output prevents testing an old compiled bundle.
DERIVED="$(mktemp -d "$OUT/DerivedData.XXXXXX")"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
printf '%s\n' "$SHA" > "$OUT/source.txt"
xcodebuild -version > "$OUT/toolchain.txt"
xcrun swiftc --version >> "$OUT/toolchain.txt"
xcodebuild -showsdks > "$OUT/sdks.txt"
xcrun simctl list --json > "$OUT/simulators.json"
python3 - "$OUT/simulators.json" > "$OUT/destination-spec.txt" <<'PY'
import json, sys
info = json.load(open(sys.argv[1]))
runtimes = sorted((r for r in info['runtimes']
                   if r.get('isAvailable') and 'iOS' in r['identifier']),
                  key=lambda r: tuple(int(v) for v in r['version'].split('.')), reverse=True)
for runtime in runtimes:
    for device in info['devices'].get(runtime['identifier'], []):
        kind = device.get('deviceTypeIdentifier', '')
        if device.get('isAvailable') and 'iPhone' in kind:
            print(kind)
            print(runtime['identifier'])
            raise SystemExit(0)
raise SystemExit('No available iPhone simulator runtime; test gate is unpaid')
PY
DEVICE_TYPE="$(sed -n '1p' "$OUT/destination-spec.txt")"
RUNTIME="$(sed -n '2p' "$OUT/destination-spec.txt")"
TEST_UDID="$(xcrun simctl create "codex-watch-4932-compatibility" "$DEVICE_TYPE" "$RUNTIME")"
printf '%s\n' "$TEST_UDID" > "$OUT/destination.txt"
xcrun simctl boot "$TEST_UDID"
xcrun simctl bootstatus "$TEST_UDID" -b
# This simulator and all build files disappear when GitHub disposes the runner.
set +e
xcodebuild test -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme BainLuckTests -configuration Debug \
  -destination "platform=iOS Simulator,id=$TEST_UDID" \
  -derivedDataPath "$DERIVED" -resultBundlePath "$OUT/BainLuckTests.xcresult" \
  -parallel-testing-enabled NO -jobs 2 \
  -test-timeouts-enabled YES -maximum-test-execution-time-allowance 180 \
  CODE_SIGNING_ALLOWED=NO \
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
  > "$OUT/tests.log" 2>&1
TEST_EXIT=$?
set -e
printf 'xcodebuild exit: %s\n' "$TEST_EXIT"
if [[ "$TEST_EXIT" -ne 0 ]]; then tail -80 "$OUT/tests.log"; fi
python3 "$ROOT/tools/watch_iphone_receipt.py" --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" --sha "$SHA" --output "$OUT/receipt.json"
