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
SDK_VERSION="$(xcrun --sdk iphonesimulator --show-sdk-version)"
python3 - "$OUT/simulators.json" "$SDK_VERSION" > "$OUT/destination-spec.txt" <<'PY'
import json, re, sys
info = json.load(open(sys.argv[1]))
# Prefer canonical slab-iPhone runtimes (`com.apple.CoreSimulator.SimRuntime.iOS-27-2`)
# and single-screen iPhone types over Xcode 27.2's split `iOS-27-2-iPhone19-4` / `iPhone-Duo`.
runtimes = sorted((r for r in info['runtimes']
                   if r.get('isAvailable') and 'iOS' in r['identifier']
                   and r['version'].split('.')[:2] == sys.argv[2].split('.')[:2]),
                  key=lambda r: (
                      tuple(int(v) for v in r['version'].split('.')),
                      1 if re.fullmatch(r'.*\.iOS-\d+-\d+', r['identifier']) else 0,
                  ), reverse=True)
candidates = []
for runtime in runtimes:
    for device in info['devices'].get(runtime['identifier'], []):
        kind = device.get('deviceTypeIdentifier', '')
        if device.get('isAvailable') and 'iPhone' in kind:
            candidates.append((0 if 'Duo' in kind else 1, kind, runtime['identifier']))
candidates.sort(key=lambda item: item[0], reverse=True)
if candidates:
    print(candidates[0][1])
    print(candidates[0][2])
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
  -parallel-testing-enabled NO -jobs 2 -collect-test-diagnostics never \
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
