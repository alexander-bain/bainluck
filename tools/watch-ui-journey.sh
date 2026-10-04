#!/bin/bash
# Hosted Watch UI journey: never select or touch a shared local simulator.
set -euo pipefail
WARM_PID=""
cleanup_warm() {
  if [[ -n "$WARM_PID" ]]; then
    kill "$WARM_PID" 2>/dev/null || true
    wait "$WARM_PID" 2>/dev/null || true
    WARM_PID=""
  fi
}
trap cleanup_warm EXIT
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
# watchOS Simulator rejects simctl content_size (POSIX45). The suite separately
# verifies default layout and a DEBUG-only accessibility5 layout stress override.
printf '%s\n' 'Default layout plus forced accessibility5 layout stress; system preference unsupported' > "$OUT/text-size.txt"
# The watch-only app and tests supply their own launch environment. Never pair
# with an existing iPhone or inject fixtures through simulator shell commands.
PHASE='warm URL delivery watcher'
python3 "$ROOT/tools/watch_ui_warm_delivery.py" --log "$OUT/tests.log" \
  --receipt "$OUT/warm-delivery.json" --sha "$SHA" --udid "$TEST_UDID" &
WARM_PID=$!
PHASE='BainLuckWatchUITests full suite'
if xcodebuild test -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme BainLuckWatchUITests -configuration Debug \
  -destination "platform=watchOS Simulator,id=$TEST_UDID" \
  -derivedDataPath "$DERIVED" -resultBundlePath "$RESULT" \
  -parallel-testing-enabled NO -jobs 2 -collect-test-diagnostics never \
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
PHASE='warm URL delivery receipt verification'
if [[ "$TEST_EXIT" -eq 0 ]] && grep -qx 'WATCH_UI_LAUNCHER_WARM=PASS' "$OUT/tests.log"; then
  wait "$WARM_PID"
  WARM_PID=""
  python3 "$ROOT/tools/watch_ui_warm_delivery.py" --verify \
    --receipt "$OUT/warm-delivery.json" --sha "$SHA" --udid "$TEST_UDID"
else
  cleanup_warm
fi
PHASE='effective layout stress size verification'
if [[ "$TEST_EXIT" -eq 0 ]]; then
  python3 - "$OUT/tests.log" <<'PYVERIFY'
import sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text().splitlines()
if 'WATCH_UI_STRESS_TYPE=accessibility5' not in lines:
    raise SystemExit('App did not confirm accessibility5 layout stress; gate unpaid')
if not any(line.startswith('WATCH_UI_STANDARD_TYPE=') for line in lines):
    raise SystemExit('Default text-size journey did not report its actual size; gate unpaid')
for marker in ('WATCH_UI_ROUNDING_PAIR=45', 'WATCH_UI_ROUNDING_DRAW=46', 'WATCH_UI_LAUNCHER_COLD=PASS', 'WATCH_UI_COMPLICATION_CONTENT=PASS', 'WATCH_UI_LAUNCHER_WARM=PASS'):
    if marker not in lines:
        raise SystemExit(f'Watch journey did not confirm {marker}; gate unpaid')
PYVERIFY
fi
PHASE='full-suite receipt verification'
python3 "$ROOT/tools/watch_iphone_receipt.py" --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" --sha "$SHA" --output "$OUT/receipt.json"
