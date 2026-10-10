#!/bin/bash
# Hosted Watch UI journey: never select or touch a shared local simulator.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'This gate runs only on a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/build/watch-ui-products"
mkdir -p "$OUT"
PHASE=preflight
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
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
PHONE_DERIVED="$RUN/CompanionDerivedData"
PACKAGES="$RUN/SourcePackages"
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
phone_runtimes = sorted((r for r in info['runtimes']
                         if r.get('isAvailable') and '.iOS-' in r['identifier']
                         and r['version'].split('.')[:2] == sys.argv[2].split('.')[:2]),
                        key=lambda r: tuple(int(v) for v in r['version'].split('.')), reverse=True)
phones = [(device['deviceTypeIdentifier'], runtime['identifier'])
          for runtime in phone_runtimes
          for device in info['devices'].get(runtime['identifier'], [])
          if device.get('isAvailable') and 'iPhone' in device.get('deviceTypeIdentifier', '')]
if not phones:
    raise SystemExit(f'No available iPhone/runtime matching SDK {sys.argv[2]}; paired Watch gate unpaid')
for runtime in runtimes:
    # Pick a type already advertised by this runtime, but never its device UDID.
    for device in info['devices'].get(runtime['identifier'], []):
        kind = device.get('deviceTypeIdentifier', '')
        if device.get('isAvailable') and 'Apple-Watch' in kind:
            print(kind)
            print(runtime['identifier'])
            print(phones[0][0])
            print(phones[0][1])
            raise SystemExit(0)
raise SystemExit(f'No available Watch device/runtime matching watchsimulator SDK {sys.argv[2]}; hosted UI gate is unpaid')
PY
DEVICE_TYPE="$(sed -n '1p' "$OUT/destination-spec.txt")"
RUNTIME="$(sed -n '2p' "$OUT/destination-spec.txt")"
PHONE_TYPE="$(sed -n '3p' "$OUT/destination-spec.txt")"
PHONE_RUNTIME="$(sed -n '4p' "$OUT/destination-spec.txt")"
# Resolve the pinned dependency graph before booting devices. Both independent
# build-product directories reuse this run's downloads; no shared/global cache.
PHASE='resolve pinned packages before simulator preparation'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
PINNED_PACKAGES="$ROOT/ios/Bain Luck/Bain Luck.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
cp "$PINNED_PACKAGES" "$OUT/package-resolved-before.json"
python3 "$ROOT/tools/watch_resolve_packages.py" --output-dir "$OUT/package-resolution" -- \
  xcodebuild -resolvePackageDependencies \
  -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" -scheme 'Bain Luck' \
  -derivedDataPath "$PHONE_DERIVED" -clonedSourcePackagesDirPath "$PACKAGES" \
  -onlyUsePackageVersionsFromResolvedFile
python3 - "$PINNED_PACKAGES" "$OUT/package-resolved-before.json" <<'PINS'
from pathlib import Path
import sys
if Path(sys.argv[1]).read_bytes() != Path(sys.argv[2]).read_bytes():
    raise SystemExit('Package resolution changed the committed pins; gate unpaid')
PINS
PHASE='disposable companion phone and Watch simulator creation'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
TEST_UDID="$(xcrun simctl create "codex-watch-ui-journey" "$DEVICE_TYPE" "$RUNTIME" 2>> "$OUT/preflight.log")"
PHONE_UDID="$(xcrun simctl create "codex-watch-ui-companion" "$PHONE_TYPE" "$PHONE_RUNTIME" 2>> "$OUT/preflight.log")"
printf '%s\n' "$TEST_UDID" > "$OUT/destination.txt"
printf '%s\n' "$PHONE_UDID" > "$OUT/phone-destination.txt"
python3 - "$OUT/simulators.json" "$TEST_UDID" "$PHONE_UDID" <<'NEW_DEVICES'
import json, sys
from pathlib import Path
existing = {d['udid'] for devices in json.loads(Path(sys.argv[1]).read_text())['devices'].values() for d in devices}
watch, phone = sys.argv[2:]
if watch == phone or watch in existing or phone in existing:
    raise SystemExit('Refusing to pair anything except two newly created distinct devices')
NEW_DEVICES
PAIR_ID="$(xcrun simctl pair "$TEST_UDID" "$PHONE_UDID" 2>> "$OUT/preflight.log")"
xcrun simctl list pairs --json > "$OUT/pairs.json" 2>> "$OUT/preflight.log"
python3 - "$OUT/simulators.json" "$OUT/pairs.json" "$TEST_UDID" "$PHONE_UDID" "$PAIR_ID" <<'PAIR'
import json, sys
from pathlib import Path
existing = {d['udid'] for devices in json.loads(Path(sys.argv[1]).read_text())['devices'].values() for d in devices}
watch, phone, pair_id = sys.argv[3:]
if watch == phone or watch in existing or phone in existing:
    raise SystemExit('Paired gate may only use two newly created distinct devices')
pair = json.loads(Path(sys.argv[2]).read_text())['pairs'][pair_id]
if pair['watch']['udid'] != watch or pair['phone']['udid'] != phone or not pair['state'].startswith('(active,'):
    raise SystemExit('Created pair must bind exactly the new Watch and iPhone and be active')
PAIR
# bootstatus -b starts an unbooted device and waits for it. Prepare each new
# member serially; the pair-wide boot RPC timed out before reaching readiness.
PHASE='boot and await only the new disposable companion phone'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcrun simctl bootstatus "$PHONE_UDID" -b >> "$OUT/preflight.log" 2>&1
PHASE='boot and await only the new disposable Watch'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcrun simctl bootstatus "$TEST_UDID" -b >> "$OUT/preflight.log" 2>&1
# watchOS Simulator rejects simctl content_size (POSIX45). The suite separately
# verifies default layout and a DEBUG-only accessibility5 layout stress override.
printf '%s\n' 'Default layout plus forced accessibility5 layout stress; system preference unsupported' > "$OUT/text-size.txt"
# The Watch app and tests supply their own launch environment. Never pair
# with an existing iPhone or inject fixtures through simulator shell commands.
# Simulator-only ad-hoc signing uses generated simulated App Group xcent. No Apple
# identity, provisioning profile, account access or upload is requested; Debug
# also leaves the existing Release Crashlytics upload path unexecuted.
# Select the architecture from these actual newly owned destinations. Watch
# build-for-testing forces ONLY_ACTIVE_ARCH=NO, so setting that flag alone still
# compiles both simulator architectures. Device/archive gates remain separate.
PHASE='resolve the architecture shared by the selected simulator destinations'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
for scheme in BainLuckWatchUITests 'Bain Luck'; do
  if [[ "$scheme" == BainLuckWatchUITests ]]; then destination_log=watch; else destination_log=phone; fi
  xcodebuild -showdestinations -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
    -scheme "$scheme" -clonedSourcePackagesDirPath "$PACKAGES" \
    -disableAutomaticPackageResolution > "$OUT/$destination_log-destinations.log" 2>&1
done
SIM_ARCH="$(python3 "$ROOT/tools/watch_simulator_architecture.py" \
  --watch-destinations "$OUT/watch-destinations.log" --watch-id "$TEST_UDID" \
  --phone-destinations "$OUT/phone-destinations.log" --phone-id "$PHONE_UDID" \
  --output "$OUT/simulator-architecture.json")"
XCODE_ARGS=(
  -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
  -scheme BainLuckWatchUITests -configuration Debug
  -destination "platform=watchOS Simulator,id=$TEST_UDID"
  -derivedDataPath "$DERIVED" -parallel-testing-enabled NO -jobs 2
  -clonedSourcePackagesDirPath "$PACKAGES" -disableAutomaticPackageResolution
  "ARCHS=$SIM_ARCH"
  CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual PROVISIONING_PROFILE_SPECIFIER=
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox'
)
BUILD_SOURCE_FINGERPRINT="$(python3 -c 'from pathlib import Path; from tools.watch_ui_products import source_fingerprint; print(source_fingerprint(Path(".")))')"
PHASE='build exact Watch app, embedded Widget and UI test products'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcodebuild build-for-testing "${XCODE_ARGS[@]}" > "$OUT/build-for-testing.log" 2>&1
PHASE='build the exact Debug simulator companion without launching it'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcodebuild build -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme 'Bain Luck' -configuration Debug \
  -destination "platform=iOS Simulator,id=$PHONE_UDID" \
  -derivedDataPath "$PHONE_DERIVED" -jobs 2 \
  -clonedSourcePackagesDirPath "$PACKAGES" -disableAutomaticPackageResolution \
  "ARCHS=$SIM_ARCH" \
  CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES \
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual PROVISIONING_PROFILE_SPECIFIER= \
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
  > "$OUT/companion-build.log" 2>&1
[[ "$BUILD_SOURCE_FINGERPRINT" == "$(python3 -c 'from pathlib import Path; from tools.watch_ui_products import source_fingerprint; print(source_fingerprint(Path(".")))')" ]]
PHASE='package immutable simulator products'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
python3 "$ROOT/tools/watch_ui_products.py" pack --repo "$ROOT" --sha "$SHA" \
  --watch "$DERIVED" --phone "$PHONE_DERIVED" --architecture "$SIM_ARCH" \
  --output "$RUN/package" --archive "$OUT/products.tar.gz" \
  --simulators "$OUT/simulators.json" --watch-runtime "$RUNTIME"
cp "$RUN/package/manifest.json" "$OUT/manifest.json"
