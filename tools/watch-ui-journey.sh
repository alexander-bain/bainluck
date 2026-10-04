#!/bin/bash
# Hosted Watch UI journey: never select or touch a shared local simulator.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'This gate runs only on a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/watch-ui-journey"
mkdir -p "$OUT"
PHASE=preflight
failure() {
  local status=$?
  echo "Watch UI journey unpaid: $PHASE failed (exit $status)." >&2
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
Path(sys.argv[2]).write_text(json.dumps({'sha': sys.argv[1], 'verdict': 'UNPAID', 'reason': 'Hosted Watch UI journey has not completed'}, indent=2) + '\n')
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
TEST_UDID="$(xcrun simctl create "codex-watch-ui-journey" "$DEVICE_TYPE" "$RUNTIME" 2>> "$OUT/preflight.log")"
printf '%s\n' "$TEST_UDID" > "$OUT/destination.txt"
PHASE='disposable unpaired Watch simulator boot (pairing, if required, is an unpaid gate)'
xcrun simctl boot "$TEST_UDID" >> "$OUT/preflight.log" 2>&1
xcrun simctl bootstatus "$TEST_UDID" -b >> "$OUT/preflight.log" 2>&1
# Verify a real simulator preference, never force SwiftUI's environment in source.
case "${WATCH_UI_TEXT_SIZE:-standard}" in
  standard) TEXT_CATEGORY=large; EXPECTED_TYPE=large ;;
  accessibility) TEXT_CATEGORY=accessibility-extra-extra-extra-large; EXPECTED_TYPE=accessibility5 ;;
  *) echo 'Unknown Watch text-size test mode' >&2; exit 2 ;;
esac
PHASE='simulator text size setting and readback'
xcrun simctl ui "$TEST_UDID" content_size "$TEXT_CATEGORY" >> "$OUT/preflight.log" 2>&1
xcrun simctl ui "$TEST_UDID" content_size > "$OUT/text-size.txt" 2>> "$OUT/preflight.log"
# The watch-only app and tests supply their own launch environment. Never pair
# with an existing iPhone or inject fixtures through simulator shell commands.
PHASE='BainLuckWatchUITests full suite'
if xcodebuild test -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme BainLuckWatchUITests -configuration Debug \
  -destination "platform=watchOS Simulator,id=$TEST_UDID" \
  -derivedDataPath "$DERIVED" -resultBundlePath "$RESULT" \
  -parallel-testing-enabled NO -jobs 2 \
  -test-timeouts-enabled YES -maximum-test-execution-time-allowance 180 \
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
  echo 'Watch UI journey unpaid; if this toolchain requires pairing, no existing iPhone has been touched.' >&2
  tail -80 "$OUT/tests.log" >&2
fi
PHASE='effective SwiftUI text size verification'
if [[ "$TEST_EXIT" -eq 0 ]]; then
  python3 - "$OUT/tests.log" "$OUT/text-size.txt" "$TEXT_CATEGORY" "$EXPECTED_TYPE" <<'PYVERIFY'
import sys
from pathlib import Path
log, readback = (Path(p).read_text() for p in sys.argv[1:3])
if readback.strip() != sys.argv[3]:
    raise SystemExit(f'Simulator text size readback mismatch: {readback.strip()}')
if f'WATCH_UI_DYNAMIC_TYPE={sys.argv[4]}' not in log.splitlines():
    raise SystemExit('App did not confirm expected effective text size; accessibility gate unpaid')
PYVERIFY
fi
PHASE='full-suite receipt verification'
python3 "$ROOT/tools/watch_iphone_receipt.py" --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" --sha "$SHA" --output "$OUT/receipt.json"
