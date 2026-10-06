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
xcrun simctl bootstatus "$PHONE_UDID" -b >> "$OUT/preflight.log" 2>&1
PHASE='boot and await only the new disposable Watch'
xcrun simctl bootstatus "$TEST_UDID" -b >> "$OUT/preflight.log" 2>&1
# watchOS Simulator rejects simctl content_size (POSIX45). The suite separately
# verifies default layout and a DEBUG-only accessibility5 layout stress override.
printf '%s\n' 'Default layout plus forced accessibility5 layout stress; system preference unsupported' > "$OUT/text-size.txt"
# The Watch app and tests supply their own launch environment. Never pair
# with an existing iPhone or inject fixtures through simulator shell commands.
# Simulator-only ad-hoc signing uses generated simulated App Group xcent. No Apple
# identity, provisioning profile, account access or upload is requested; Debug
# also leaves the existing Release Crashlytics upload path unexecuted.
XCODE_ARGS=(
  -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
  -scheme BainLuckWatchUITests -configuration Debug
  -destination "platform=watchOS Simulator,id=$TEST_UDID"
  -derivedDataPath "$DERIVED" -parallel-testing-enabled NO -jobs 2
  -clonedSourcePackagesDirPath "$PACKAGES" -disableAutomaticPackageResolution
  CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual PROVISIONING_PROFILE_SPECIFIER=
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox'
)
PHASE='build exact Watch app, embedded Widget and UI test products'
xcodebuild build-for-testing "${XCODE_ARGS[@]}" > "$OUT/build-for-testing.log" 2>&1
PHASE='build the exact Debug simulator companion without launching it'
xcodebuild build -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme 'Bain Luck' -configuration Debug \
  -destination "platform=iOS Simulator,id=$PHONE_UDID" \
  -derivedDataPath "$PHONE_DERIVED" -jobs 2 \
  -clonedSourcePackagesDirPath "$PACKAGES" -disableAutomaticPackageResolution \
  CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES \
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual PROVISIONING_PROFILE_SPECIFIER= \
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
  > "$OUT/companion-build.log" 2>&1
# Give the system host a cold startup with the installed extension available.
# This is preparation for one full suite, never a retry after a failed suite.
# XCTest may still reinstall products; retain the lifecycle without claiming
# that preinstallation alone proves WidgetKit discovery.
BUILT_PHONE="$PHONE_DERIVED/Build/Products/Debug-iphonesimulator/Bain Luck.app"
BUILT_APP="$BUILT_PHONE/Watch/BainLuckWatch Watch App.app"
PHASE='explicitly install companion and nested Watch app on the new pair'
date -u '+%Y-%m-%dT%H:%M:%SZ preinstall' >> "$OUT/install-lifecycle.txt"
xcrun simctl install "$PHONE_UDID" "$BUILT_PHONE" >> "$OUT/preflight.log" 2>&1
xcrun simctl install "$TEST_UDID" "$BUILT_APP" >> "$OUT/preflight.log" 2>&1
xcrun simctl get_app_container "$PHONE_UDID" com.bainluck.Bain-Luck app >> "$OUT/install-lifecycle.txt"
xcrun simctl get_app_container "$TEST_UDID" com.bainluck.Bain-Luck.watchkitapp app >> "$OUT/install-lifecycle.txt"
PHASE='restart only this run disposable simulator after installation'
xcrun simctl shutdown "$TEST_UDID" >> "$OUT/preflight.log" 2>&1
xcrun simctl boot "$TEST_UDID" >> "$OUT/preflight.log" 2>&1
xcrun simctl bootstatus "$TEST_UDID" -b >> "$OUT/preflight.log" 2>&1
date -u '+%Y-%m-%dT%H:%M:%SZ boot-ready' >> "$OUT/install-lifecycle.txt"
xcrun simctl get_app_container "$PHONE_UDID" com.bainluck.Bain-Luck app >> "$OUT/install-lifecycle.txt"
xcrun simctl get_app_container "$TEST_UDID" com.bainluck.Bain-Luck.watchkitapp app >> "$OUT/install-lifecycle.txt"
PHASE='BainLuckWatchUITests full suite from the same built products'
if xcodebuild test-without-building "${XCODE_ARGS[@]}" \
  -resultBundlePath "$RESULT" -collect-test-diagnostics never \
  -test-timeouts-enabled YES -default-test-execution-time-allowance 180 \
  -maximum-test-execution-time-allowance 300 \
  > "$OUT/tests.log" 2>&1; then
  TEST_EXIT=0
else
  TEST_EXIT=$?
fi
printf '%s\n' "$TEST_EXIT" > "$OUT/test-exit.txt"
printf 'xcodebuild exit: %s\n' "$TEST_EXIT"
# Read the app actually installed by this Debug UI run before judging system URL delivery.
# Diagnostic failure never replaces the real XCTest result or becomes an acceptance pass.
python3 - "$TEST_UDID" "$OUT/installed-watch-registration.json" "$SHA" <<'REGISTRATION'
import json, plistlib, subprocess, sys
from pathlib import Path
bundle = "com.bainluck.Bain-Luck.watchkitapp"
receipt = {"sha": sys.argv[3], "udid": sys.argv[1], "bundle_id": bundle}
try:
    result = subprocess.run(["xcrun", "simctl", "get_app_container", sys.argv[1], bundle, "app"],
                            capture_output=True, text=True, timeout=15, check=True)
    installed = Path(result.stdout.strip())
    info = plistlib.loads((installed / "Info.plist").read_bytes())
    keys = ["CFBundleIdentifier", "CFBundleDisplayName", "CFBundleName", "CFBundleExecutable", "CFBundleURLTypes", "CFBundleSupportedPlatforms", "MinimumOSVersion",
            "WKCompanionAppBundleIdentifier", "WKRunsIndependentlyOfCompanionApp"]
    receipt["installed_info"] = {key: info.get(key) for key in keys}
    receipt["embedded_extensions"] = []
    for extension in sorted((installed / "PlugIns").glob("*.appex")):
        extension_info = plistlib.loads((extension / "Info.plist").read_bytes())
        receipt["embedded_extensions"].append({key: extension_info.get(key) for key in keys + ["NSExtension"]})
    listing = subprocess.run(["xcrun", "simctl", "listapps", sys.argv[1]],
                             capture_output=True, timeout=15, check=True)
    converted = subprocess.run(["plutil", "-convert", "json", "-o", "-", "-"],
                               input=listing.stdout, capture_output=True, timeout=15, check=True)
    app = json.loads(converted.stdout).get(bundle)
    receipt["system_listing"] = app
except Exception as error:
    receipt["diagnostic_error"] = str(error)
Path(sys.argv[2]).write_text(json.dumps(receipt, indent=2) + "\n")
REGISTRATION
if [[ "$TEST_EXIT" -ne 0 ]]; then
  echo 'Watch UI journey unpaid; only this run disposable phone and Watch have been touched.' >&2
  tail -80 "$OUT/tests.log" >&2
  # Failure-only, bundle-scoped runtime evidence distinguishes an absent
  # WidgetKit offering from a gallery traversal failure. No daemon restart,
  # registration mutation, pairing, or test retry is performed.
  python3 - "$TEST_UDID" "$OUT/widget-runtime.log" "$OUT/widget-runtime.json" <<'RUNTIME'
import json, subprocess, sys
from pathlib import Path
output = Path(sys.argv[2])
receipt = {"scope": "failed Watch UI gate; bundle-filtered last 25 minutes"}
predicate = 'eventMessage CONTAINS[c] "com.bainluck" OR eventMessage CONTAINS[c] "BainLuckComplication"'
try:
    with output.open("wb") as log:
        result = subprocess.run(["xcrun", "simctl", "spawn", sys.argv[1], "log", "show",
                                 "--last", "25m", "--style", "compact", "--info", "--predicate", predicate],
                                stdout=log, stderr=subprocess.STDOUT, timeout=20)
    receipt["exit_code"] = result.returncode
except Exception as error:
    receipt["diagnostic_error"] = str(error)
if output.exists():
    size = output.stat().st_size
    receipt["original_bytes"] = size
    limit = 2 * 1024 * 1024
    if size > limit:
        with output.open("rb") as log:
            log.seek(-limit, 2)
            tail = log.read()
        output.write_bytes(tail)
        receipt["truncated_to_last_bytes"] = limit
Path(sys.argv[3]).write_text(json.dumps(receipt, indent=2) + "\n")
RUNTIME
fi
PHASE='installed simulator WidgetKit entitlement verification'
# Retain installation/signing evidence even when gallery navigation fails.
# A diagnostic error must not hide the original test failure; on a passing
# suite the same signing checks remain mandatory.
if python3 - "$TEST_UDID" "$OUT/simulator-widget-signing.json" "$SHA" "$DERIVED" <<'SIMSIGN'
import json, plistlib, subprocess, sys
from pathlib import Path
bundle_id = "com.bainluck.Bain-Luck.watchkitapp"
receipt = {"sha": sys.argv[3], "verdict": "UNPAID", "scope": "simulator ad-hoc signatures, generated simulated xcent and installed group container"}
try:
    app = Path(subprocess.check_output(["xcrun", "simctl", "get_app_container", sys.argv[1], bundle_id, "app"], text=True, timeout=15).strip())
    extensions = list((app / "PlugIns").glob("*.appex"))
    if len(extensions) != 1:
        raise ValueError("Expected one installed WidgetKit extension")
    observed = []
    for product, expected in [(app, bundle_id), (extensions[0], bundle_id + ".SavedGlance")]:
        info = plistlib.loads((product / "Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != expected:
            raise ValueError("Installed simulator bundle identity mismatch")
        subprocess.run(["codesign", "--verify", "--strict", str(product)], capture_output=True, check=True, timeout=15)
        signature = subprocess.run(["codesign", "-dv", str(product)], capture_output=True, text=True, check=True, timeout=15)
        if "Signature=adhoc" not in signature.stderr:
            raise ValueError("Simulator signature must be ad-hoc")
        target = "BainLuckWatch Watch App" if product == app else "BainLuckComplication"
        suffix = "BainLuckWatch Watch App.app-Simulated.xcent" if product == app else "BainLuckComplication.appex-Simulated.xcent"
        candidates = list((Path(sys.argv[4]) / "Build" / "Intermediates.noindex" / "Bain Luck.build" / "Debug-watchsimulator" / (target + ".build")).glob(suffix))
        if len(candidates) != 1:
            raise ValueError("Expected one generated simulated xcent for " + expected)
        entitlements = plistlib.loads(candidates[0].read_bytes())
        if "group.com.bainluck.watch" not in entitlements.get("com.apple.security.application-groups", []):
            raise ValueError("Generated simulated xcent lacks the shared Watch group")
        observed.append({"bundle_id": expected, "signature": "ad-hoc", "simulated_xcent": str(candidates[0]), "simulated_watch_group": True})
    group = Path(subprocess.check_output(["xcrun", "simctl", "get_app_container", sys.argv[1], bundle_id, "group.com.bainluck.watch"], text=True, timeout=15).strip())
    if not group.is_dir():
        raise ValueError("Installed simulator shared group container is missing")
    receipt["installed_simulator_group_container"] = str(group)
    receipt["signature_entitlements_note"] = "Simulator ad-hoc signature entitlements may be empty; device archive signature entitlements require separate evidence"
    receipt.update(verdict="PASS", bundles=observed, physical_install="UNVERIFIED", physical_shared_reads="UNVERIFIED")
except Exception as error:
    receipt["reason"] = str(error)
    Path(sys.argv[2]).write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit("Installed WidgetKit signing gate unpaid: " + str(error))
Path(sys.argv[2]).write_text(json.dumps(receipt, indent=2) + "\n")
SIMSIGN
then
  :
else
  if [[ "$TEST_EXIT" -eq 0 ]]; then exit 1; fi
fi
PHASE='effective layout stress size verification'
if [[ "$TEST_EXIT" -eq 0 ]]; then
  python3 - "$OUT/tests.log" <<'PYVERIFY'
import sys
from pathlib import Path
import re
log = Path(sys.argv[1]).read_text()
lines = log.splitlines()
if 'WATCH_UI_STRESS_TYPE=accessibility5' not in lines:
    raise SystemExit('App did not confirm accessibility5 layout stress; gate unpaid')
if not any(line.startswith('WATCH_UI_STANDARD_TYPE=') for line in lines):
    raise SystemExit('Default text-size journey did not report its actual size; gate unpaid')
for marker in ('WATCH_UI_ROUNDING_PAIR=45', 'WATCH_UI_ROUNDING_DRAW=46', 'WATCH_UI_LAUNCHER_COLD=PASS', 'WATCH_UI_COMPLICATION_CONTENT=PASS', 'WATCH_UI_ACTUAL_WIDGET_WARM=PASS', 'WATCH_UI_ACTUAL_WIDGET_COLD=PASS', 'WATCH_UI_ACTUAL_WIDGET_EMPTY=PASS', 'WATCH_UI_FRESH_FACE_ACTIVATION=PASS', 'WATCH_RECTANGULAR_INSTALLED_DETAIL=Saved · 64% · Live', 'WATCH_UI_CLEAR_SELECTION=PASS', 'WATCH_UI_PICKER_RETURN=PASS', 'WATCH_UI_PICKER_NETWORK_OFFLINE=PASS', 'WATCH_UI_PICKER_NETWORK_INTERRUPTED=PASS', 'WATCH_UI_PICKER_NETWORK_TIMEOUT=PASS', 'WATCH_UI_DISCOVERIES_SAVED=PASS', 'WATCH_UI_DISCOVERIES_LARGE=PASS', 'WATCH_UI_DISCOVERIES_UNSELECTED=PASS', 'WATCH_UI_DISCOVERIES_CONTINUATION=PASS', 'WATCH_UI_DISCOVERIES_RETURN_STANDARD=PASS', 'WATCH_UI_DISCOVERIES_RETURN_LARGE=PASS', 'WATCH_UI_DISCOVERIES_HEADING_STANDARD=PASS', 'WATCH_UI_DISCOVERIES_HEADING_LARGE=PASS', 'WATCH_UI_CIRCULAR_CONTENT=PASS', 'WATCH_UI_CIRCULAR_FALLBACK=PASS', 'WATCH_UI_ACTUAL_CIRCULAR_SAVED=PASS', 'WATCH_UI_PICKER_SELECTED_STANDARD=PASS', 'WATCH_UI_PICKER_SELECTED_LARGE=PASS', 'WATCH_UI_GAME_UPDATING_STANDARD=PASS', 'WATCH_UI_GAME_UPDATING_LARGE=PASS'):
    if marker not in lines:
        raise SystemExit(f'Watch journey did not confirm {marker}; gate unpaid')
if not re.search(r"^Test Case '-\[BainLuckWatchUITests\.WidgetTapJourneyTests testFreshConfiguredFaceIsActiveBeforeActualLauncherTap\]' passed \([0-9.]+ seconds\)\.$", log, re.MULTILINE):
    raise SystemExit('Fresh-face activation regression did not pass; gate unpaid')
if not re.search(r"^Test Case '-\[BainLuckWatchUITests\.PickerReturnJourneyTests testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection\]' passed \([0-9.]+ seconds\)\.$", log, re.MULTILINE):
    raise SystemExit('Picker network recovery did not complete its visible retained-choice journey; gate unpaid')
for case in ('testSelectedGameIsMarkedInPickerAndCanChange', 'testSelectedGameIsMarkedAtAccessibilitySize'):
    pattern = rf"^Test Case '-\[BainLuckWatchUITests\.PickerSelectedStateJourneyTests {case}\]' (passed|failed|skipped) \([0-9.]+ seconds\)\.$"
    if re.findall(pattern, log, re.MULTILINE) != ['passed']:
        raise SystemExit(f'Selected picker case {case} did not pass exactly once; gate unpaid')
for case in ('testUpdatingIsVisibleUntilRequestFinishes', 'testUpdatingIsVisibleAtAccessibilitySize'):
    pattern = rf"^Test Case '-\[BainLuckWatchUITests\.SelectedGameUpdatingJourneyTests {case}\]' (passed|failed|skipped) \([0-9.]+ seconds\)\.$"
    if re.findall(pattern, log, re.MULTILINE) != ['passed']:
        raise SystemExit(f'Updating case {case} did not pass exactly once; gate unpaid')
PYVERIFY
  python3 "$ROOT/tools/watch_discovery_polish_receipt.py" "$OUT/tests.log"
fi
PHASE='rendered diagnostics consent verification'
if [[ "$TEST_EXIT" -eq 0 ]]; then
  python3 "$ROOT/tools/watch_diagnostics_receipt.py" --log "$OUT/tests.log"
fi
PHASE='full-suite receipt verification'
python3 "$ROOT/tools/watch_iphone_receipt.py" --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" --sha "$SHA" --output "$OUT/receipt.json"
