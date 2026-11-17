#!/bin/bash
# Hosted Watch UI journey: never select or touch a shared local simulator.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'This gate runs only on a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/build/watch-ui-journey"
mkdir -p "$OUT"
SHARD="${WATCH_UI_SHARD:-full}"
TEST_SELECTION=()
if [[ "$SHARD" != full ]]; then
  python3 "$ROOT/tools/watch_ui_shards.py" select --shard "$SHARD" > "$OUT/selected-cases.txt"
  while IFS= read -r selector; do TEST_SELECTION+=("$selector"); done < "$OUT/selected-cases.txt"
fi
STAGE="${1:?Expected prepare or execute}"
if [[ "$STAGE" != prepare && "$STAGE" != execute ]]; then exit 2; fi
# True only while this device's state is "Booted".
is_booted() {
  xcrun simctl list devices --json 2>> "$OUT/preflight.log" | python3 -c '
import json, sys
target = sys.argv[1]
for devs in json.load(sys.stdin).get("devices", {}).values():
    for d in devs:
        if d.get("udid") == target and d.get("state") == "Booted":
            raise SystemExit(0)
raise SystemExit(1)
' "$1"
}
boot_until_ready() {
  local udid="$1"
  local attempt
  for attempt in 1 2 3; do
    xcrun simctl bootstatus "$udid" -b >> "$OUT/preflight.log" 2>&1
    if is_booted "$udid"; then
      return 0
    fi
    echo "bootstatus exited 0 with $udid not Booted (attempt $attempt); retrying..." >> "$OUT/preflight.log"
    sleep 2
  done
  return 1
}
# #12513: "Booted" is not "ready". Run 43867918866 lost the companion phone's
# instruments lockdown service 92 s into a test. Wait until each device runs a
# process, its home app has a pid, and the instruments device service is loaded.
wait_services_ready() {
  local udid="$1" home="$2" listing
  local i
  for i in $(seq 1 60); do
    if listing="$(xcrun simctl spawn "$udid" launchctl list 2>> "$OUT/preflight.log")" \
      && printf '%s\n' "$listing" | awk -v h="$home" '$3 == h && $1 ~ /^[0-9]+$/ {f=1} END {exit !f}' \
      && printf '%s\n' "$listing" | grep -q 'com\.apple\.instruments\.deviceservice'; then
      echo "$udid ready: $home running, instruments device service loaded (check $i)" >> "$OUT/preflight.log"
      return 0
    fi
    # A device that has left Booted will not come back by waiting (run
    # 43990443905 spent 120 s on "device is not booted"); say so now.
    if ! is_booted "$udid"; then
      echo "$udid is no longer Booted (check $i)" >> "$OUT/preflight.log"
      return 1
    fi
    sleep 2
  done
  echo "$udid not ready after 120 s: $home or the instruments device service missing" >> "$OUT/preflight.log"
  return 1
}
# A device whose home app never came up gets ONE shutdown and boot, then must be ready.
# (Run 43892482800: the Watch boot sat on "Waiting on System App" for 4 min.)
ready_or_reboot_once() {
  local udid="$1" home="$2"
  if wait_services_ready "$udid" "$home"; then return 0; fi
  echo "$udid: one shutdown and boot after it was not ready" >> "$OUT/preflight.log"
  xcrun simctl shutdown "$udid" >> "$OUT/preflight.log" 2>&1 || true
  boot_until_ready "$udid"
  wait_services_ready "$udid" "$home"
}
# Shut down and boot this run's own pair, then wait for both to be ready.
reboot_pair_until_ready() {
  local udid
  for udid in "$TEST_UDID" "$PHONE_UDID"; do
    xcrun simctl shutdown "$udid" >> "$OUT/preflight.log" 2>&1 || true
  done
  boot_until_ready "$PHONE_UDID"
  boot_until_ready "$TEST_UDID"
  wait_services_ready "$PHONE_UDID" com.apple.SpringBoard
  wait_services_ready "$TEST_UDID" com.apple.Carousel
}
if [[ "$STAGE" == prepare ]]; then
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
# Fresh extraction and result paths prevent old bundles or receipts passing.
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
import json, re, sys
from pathlib import Path
info = json.loads(Path(sys.argv[1]).read_text())
runtimes = sorted((r for r in info['runtimes']
                   if r.get('isAvailable') and '.watchOS-' in r['identifier']
                   and r['version'].split('.')[:2] == sys.argv[2].split('.')[:2]),
                  key=lambda r: tuple(int(v) for v in r['version'].split('.')), reverse=True)
phone_runtimes = sorted((r for r in info['runtimes']
                         if r.get('isAvailable') and '.iOS-' in r['identifier']
                         and r['version'].split('.')[:2] == sys.argv[2].split('.')[:2]),
                        key=lambda r: (
                            tuple(int(v) for v in r['version'].split('.')),
                            1 if re.fullmatch(r'.*\.iOS-\d+-\d+', r['identifier']) else 0,
                        ), reverse=True)
phones = sorted(
    [(device['deviceTypeIdentifier'], runtime['identifier'])
     for runtime in phone_runtimes
     for device in info['devices'].get(runtime['identifier'], [])
     if device.get('isAvailable') and 'iPhone' in device.get('deviceTypeIdentifier', '')],
    key=lambda pair: 1 if 'Duo' in pair[0] else 0
)
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
PHASE='verify exact immutable simulator products'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
python3 "$ROOT/tools/watch_ui_products.py" unpack --repo "$ROOT" \
  --archive "$ROOT/build/watch-ui-products/products.tar.gz" --output "$RUN/package"
python3 "$ROOT/tools/watch_ui_products.py" verify --repo "$ROOT" --sha "$SHA" \
  --output "$RUN/package" > "$OUT/products-verification.json"
DERIVED="$RUN/package/payload/watch"
printf '%s\n' "$DERIVED" > "$OUT/derived-data.txt"
XCTESTRUN="$RUN/package/payload/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["xctestrun"])' "$OUT/products-verification.json")"
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
boot_until_ready "$PHONE_UDID"
PHASE='boot and await only the new disposable Watch'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
boot_until_ready "$TEST_UDID"
boot_until_ready "$PHONE_UDID"
ready_or_reboot_once "$PHONE_UDID" com.apple.SpringBoard
ready_or_reboot_once "$TEST_UDID" com.apple.Carousel
# Run 43990443905 (corner): the Watch left Booted right after its boot, and while
# it was rebooted the companion phone shut down too, so the runtime check below
# found a Shutdown phone. After set-up both members must still be Booted and
# ready; if either is not, the pair gets one shutdown and boot.
if ! is_booted "$PHONE_UDID" || ! is_booted "$TEST_UDID"; then
  echo 'a pair member left Booted during set-up; one shutdown and boot of this pair' >> "$OUT/preflight.log"
  reboot_pair_until_ready
fi
# Resolve the exact devices through their available booted runtime metadata.
# uname inside a simulator can report x86_64 on an arm64-only runtime.
PHASE='verify exact paired simulator runtime architecture'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcrun simctl list --json > "$OUT/prepared-simulators.json" 2>> "$OUT/preflight.log"
xcrun simctl list pairs --json > "$OUT/prepared-pairs.json" 2>> "$OUT/preflight.log"
python3 "$ROOT/tools/watch_simulator_architecture.py" --runtime-pair \
  --watch-id "$TEST_UDID" --phone-id "$PHONE_UDID" \
  --simulators "$OUT/prepared-simulators.json" --pairs "$OUT/prepared-pairs.json" \
  --products "$RUN/package/manifest.json" --output "$OUT/simulator-architecture.json"
printf '%s\n' 'Default layout plus forced accessibility5 layout stress; system preference unsupported' > "$OUT/text-size.txt"
# Give the system host a cold startup with the installed extension available.
# This is preparation for one full suite, never a retry after a failed suite.
# XCTest may still reinstall products; retain the lifecycle without claiming
# that preinstallation alone proves WidgetKit discovery.
BUILT_PHONE="$RUN/package/payload/phone/Bain Luck.app"
BUILT_APP="$BUILT_PHONE/Watch/BainLuckWatch Watch App.app"
PHASE='explicitly install companion and nested Watch app on the new pair'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
date -u '+%Y-%m-%dT%H:%M:%SZ preinstall' >> "$OUT/install-lifecycle.txt"
install_pair() {
  xcrun simctl install "$PHONE_UDID" "$BUILT_PHONE" >> "$OUT/preflight.log" 2>&1 \
    && xcrun simctl install "$TEST_UDID" "$BUILT_APP" >> "$OUT/preflight.log" 2>&1
}
# Install once more, after rebooting both, only if the first install failed
# (run 43892482800: "CoreSimulatorService: Connection interrupted" mid-install).
if ! install_pair; then
  echo 'install failed; one shutdown, boot and reinstall of this pair' >> "$OUT/preflight.log"
  date -u '+%Y-%m-%dT%H:%M:%SZ install-retry' >> "$OUT/install-lifecycle.txt"
  reboot_pair_until_ready
  install_pair
fi
xcrun simctl get_app_container "$PHONE_UDID" com.bainluck.Bain-Luck app >> "$OUT/install-lifecycle.txt"
xcrun simctl get_app_container "$TEST_UDID" com.bainluck.Bain-Luck.watchkitapp app >> "$OUT/install-lifecycle.txt"
PHASE='post-install shutdown of only this run disposable Watch'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcrun simctl shutdown "$TEST_UDID" >> "$OUT/preflight.log" 2>&1
PHASE='post-install boot of only this run disposable Watch'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcrun simctl boot "$TEST_UDID" >> "$OUT/preflight.log" 2>&1
PHASE='post-install boot readiness of only this run disposable Watch'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
xcrun simctl bootstatus "$TEST_UDID" -b >> "$OUT/preflight.log" 2>&1
PHASE='post-install Watch ready; verify installed containers'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
date -u '+%Y-%m-%dT%H:%M:%SZ boot-ready' >> "$OUT/install-lifecycle.txt"
xcrun simctl get_app_container "$PHONE_UDID" com.bainluck.Bain-Luck app >> "$OUT/install-lifecycle.txt"
xcrun simctl get_app_container "$TEST_UDID" com.bainluck.Bain-Luck.watchkitapp app >> "$OUT/install-lifecycle.txt"
python3 - "$OUT/prepared.json" "$RUN" "$DERIVED" "$RESULT" "$SHA" "$TEST_UDID" "$PHONE_UDID" "$XCTESTRUN" <<'STATE'
import json, sys
from pathlib import Path
keys = ['run', 'derived', 'result', 'sha', 'watch', 'phone', 'xctestrun']
Path(sys.argv[1]).write_text(json.dumps(dict(zip(keys, sys.argv[2:])), indent=2) + '\n')
STATE
exit 0
fi
# Execute stage reuses only this job's verified immutable package and fresh pair.
read_state() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$OUT/prepared.json" "$1"; }
RUN="$(read_state run)"
DERIVED="$(read_state derived)"
RESULT="$(read_state result)"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$SHA" == "$(read_state sha)" ]]
TEST_UDID="$(read_state watch)"
PHONE_UDID="$(read_state phone)"
XCTESTRUN="$(read_state xctestrun)"
python3 "$ROOT/tools/watch_ui_products.py" verify --repo "$ROOT" --sha "$SHA" \
  --output "$RUN/package" > "$OUT/products-verification.json"
boot_until_ready "$PHONE_UDID"
boot_until_ready "$TEST_UDID"
wait_services_ready "$PHONE_UDID" com.apple.SpringBoard
wait_services_ready "$TEST_UDID" com.apple.Carousel
XCODE_ARGS=(-xctestrun "$XCTESTRUN" -destination "platform=watchOS Simulator,id=$TEST_UDID" -parallel-testing-enabled NO)
# Warm-up, never counted: xcodebuild installs the runner and re-installs the app,
# and the first launch plus first pick afterwards (first complication reload) can
# stall accessibility for minutes (run 43941807365, readings: the first test hung at
# 31 s per element query; the 10 after it passed). One launch-and-pick here absorbs
# that cold start. Its result is kept in tests-warmup.log and judges nothing; the
# measured suite below still runs every selected test, this one included.
WARMUP_CASE='BainLuckWatchUITests/PickerCurrentGameJourneyTests/testUnknownCurrentGameDoesNotInventProbabilityOrAge'
xcodebuild test-without-building "${XCODE_ARGS[@]}" "-only-testing:$WARMUP_CASE" \
  -resultBundlePath "$RUN/warmup.xcresult" -collect-test-diagnostics never \
  -test-timeouts-enabled YES -default-test-execution-time-allowance 240 \
  -maximum-test-execution-time-allowance 240 \
  > "$OUT/tests-warmup.log" 2>&1 || echo "warm-up exit $? (not judged)" >> "$OUT/preflight.log"
PHASE='BainLuckWatchUITests full suite from the same built products'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
# The hang watchdog stops xcodebuild only when a test has overrun and the log then
# stays silent (run 44094233390: a launch the simulator never accepted held xcodebuild
# for 38 minutes). It judges nothing; the retry decision below reads the log alone.
run_xctest_suite() {
  xcodebuild test-without-building "${XCODE_ARGS[@]}" ${TEST_SELECTION[@]+"${TEST_SELECTION[@]}"} \
    -resultBundlePath "$RESULT" -collect-test-diagnostics never \
    -test-timeouts-enabled YES -default-test-execution-time-allowance 300 \
    -maximum-test-execution-time-allowance 540 \
    > "$OUT/tests.log" 2>&1 &
  local xcodebuild_pid=$!
  python3 "$ROOT/tools/watch_ui_hang_watchdog.py" "$OUT/tests.log" "$xcodebuild_pid" "$OUT/hang-watchdog.json" &
  local watchdog_pid=$!
  if wait "$xcodebuild_pid"; then
    TEST_EXIT=0
  else
    TEST_EXIT=$?
  fi
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
}
run_xctest_suite
# Retry ONCE, only when the run died on a dropped simulator or runner connection,
# or a launch the simulator never accepted, and no test failed a check or ran out of
# time in its own steps (tools/watch_ui_infra_retry.py).
# The first log is kept beside the retry's; infra-retry.json records the reason.
if [[ "$TEST_EXIT" -ne 0 ]] \
  && python3 "$ROOT/tools/watch_ui_infra_retry.py" "$OUT/tests.log" "$OUT/infra-retry.json"; then
  cp "$OUT/tests.log" "$OUT/tests-infra-abort.log"
  [[ ! -f "$OUT/hang-watchdog.json" ]] || mv "$OUT/hang-watchdog.json" "$OUT/hang-watchdog-infra-abort.json"
  rm -rf "$RESULT"
  reboot_pair_until_ready
  run_xctest_suite
fi
printf '%s\n' "$TEST_EXIT" > "$OUT/test-exit.txt"
printf 'xcodebuild exit: %s\n' "$TEST_EXIT"
# Read the app actually installed by this Debug UI run before judging system URL delivery.
# Diagnostic failure never replaces the real XCTest result or becomes an acceptance pass.
python3 - "$TEST_UDID" "$OUT/installed-watch-registration.json" "$SHA" <<'REGISTRATION'
import json, plistlib, subprocess, sys, time
from pathlib import Path
bundle = "com.bainluck.Bain-Luck.watchkitapp"
receipt = {"sha": sys.argv[3], "udid": sys.argv[1], "bundle_id": bundle}
def get_container(udid, bundle_id, kind):
    for attempt in range(2):
        try:
            return subprocess.run(["xcrun", "simctl", "get_app_container", udid, bundle_id, kind],
                                  capture_output=True, text=True, timeout=60, check=True)
        except subprocess.TimeoutExpired:
            if attempt == 0:
                time.sleep(5)
                continue
            raise
try:
    result = get_container(sys.argv[1], bundle, "app")
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
                             capture_output=True, timeout=60, check=True)
    converted = subprocess.run(["plutil", "-convert", "json", "-o", "-", "-"],
                               input=listing.stdout, capture_output=True, timeout=60, check=True)
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
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
# Retain installation/signing evidence even when gallery navigation fails.
# A diagnostic error must not hide the original test failure; on a passing
# suite the same signing checks remain mandatory.
if python3 - "$TEST_UDID" "$OUT/simulator-widget-signing.json" "$SHA" "$DERIVED" <<'SIMSIGN'
import json, plistlib, subprocess, sys, time
from pathlib import Path
bundle_id = "com.bainluck.Bain-Luck.watchkitapp"
receipt = {"sha": sys.argv[3], "verdict": "UNPAID", "scope": "simulator ad-hoc signatures, generated simulated xcent and installed group container"}
def get_container_path(udid, bid, kind):
    for attempt in range(2):
        try:
            return Path(subprocess.check_output(["xcrun", "simctl", "get_app_container", udid, bid, kind], text=True, timeout=60).strip())
        except subprocess.TimeoutExpired:
            if attempt == 0:
                time.sleep(5)
                continue
            raise
try:
    app = get_container_path(sys.argv[1], bundle_id, "app")
    extensions = list((app / "PlugIns").glob("*.appex"))
    if len(extensions) != 1:
        raise ValueError("Expected one installed WidgetKit extension")
    observed = []
    for product, expected in [(app, bundle_id), (extensions[0], bundle_id + ".SavedGlance")]:
        info = plistlib.loads((product / "Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != expected:
            raise ValueError("Installed simulator bundle identity mismatch")
        subprocess.run(["codesign", "--verify", "--strict", str(product)], capture_output=True, check=True, timeout=60)
        signature = subprocess.run(["codesign", "-dv", str(product)], capture_output=True, text=True, check=True, timeout=60)
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
    group = get_container_path(sys.argv[1], bundle_id, "group.com.bainluck.watch")
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
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
if [[ "$TEST_EXIT" -eq 0 && "$SHARD" == full ]]; then
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
for marker in ('WATCH_UI_ROUNDING_PAIR=45', 'WATCH_UI_ROUNDING_DRAW=46', 'WATCH_UI_LAUNCHER_COLD=PASS', 'WATCH_UI_ACTUAL_WIDGET_WARM=PASS', 'WATCH_UI_ACTUAL_WIDGET_COLD=PASS', 'WATCH_UI_ACTUAL_WIDGET_EMPTY=PASS', 'WATCH_UI_FRESH_FACE_ACTIVATION=PASS', 'WATCH_UI_CLEAR_SELECTION=PASS', 'WATCH_UI_PICKER_RETURN=PASS', 'WATCH_UI_PICKER_NETWORK_OFFLINE=PASS', 'WATCH_UI_PICKER_NETWORK_INTERRUPTED=PASS', 'WATCH_UI_PICKER_NETWORK_TIMEOUT=PASS', 'WATCH_UI_PICKER_SELECTED_STANDARD=PASS', 'WATCH_UI_PICKER_SELECTED_LARGE=PASS', 'WATCH_UI_GAME_UPDATING_STANDARD=PASS', 'WATCH_UI_GAME_UPDATING_LARGE=PASS', 'WATCH_UI_ACTUAL_CIRCULAR_LAUNCHER=PASS', 'WATCH_UI_ACTUAL_RECTANGULAR_LAUNCHER=PASS'):
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
  python3 - "$OUT/tests.log" <<'PYALIAS'
import re
import sys
from pathlib import Path
log = Path(sys.argv[1]).read_text()
lines = log.splitlines()
for marker in (
    'WATCH_UI_PICKER_ALIAS_STANDARD=PASS',
    'WATCH_UI_PICKER_ALIAS_LARGE=PASS',
    'WATCH_UI_PICKER_ALIAS_UNPROVEN_CONTROL=PASS',
    'WATCH_UI_PICKER_ALIAS_SAVED_BANNER_LARGE=PASS',
):
    if lines.count(marker) != 1:
        raise SystemExit(f'Picker alias marker {marker} did not occur exactly once; gate unpaid')
for case in (
    'testResolvedAliasRetainsReadingOfflineAndAfterRestart',
    'testResolvedAliasRetainsReadingAtAccessibilitySize',
    'testUnprovenSameNameChoiceDoesNotReuseSavedReading',
    'testRestoredSavedBannerIsReadableAtAccessibilitySize',
):
    pattern = rf"^Test Case '-\[BainLuckWatchUITests\.PickerAliasJourneyTests {case}\]' (passed|failed|skipped) \([0-9.]+ seconds\)\.$"
    if re.findall(pattern, log, re.MULTILINE) != ['passed']:
        raise SystemExit(f'Picker alias case {case} did not pass exactly once; gate unpaid')
PYALIAS
fi
PHASE='rendered diagnostics consent verification'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
if [[ "$TEST_EXIT" -eq 0 && "$SHARD" == full ]]; then
  python3 "$ROOT/tools/watch_diagnostics_receipt.py" --log "$OUT/tests.log"
fi
PHASE='configured launcher host and tap verification'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
if [[ "$TEST_EXIT" -eq 0 && "$SHARD" == full ]]; then
  python3 - "$OUT/tests.log" <<'PYCORNER'
import sys
from pathlib import Path
import re
log = Path(sys.argv[1]).read_text()
for suite, case, marker in [
    ('WidgetTapJourneyTests', 'testActualCornerLauncherAndTap', 'WATCH_UI_ACTUAL_CORNER_LAUNCHER=PASS'),
    ('WidgetTapJourneyTests', 'testActualCircularLauncherAndTap', 'WATCH_UI_ACTUAL_CIRCULAR_LAUNCHER=PASS'),
    ('RectangularWidgetHostJourneyTests', 'testActualRectangularLauncherAndTap', 'WATCH_UI_ACTUAL_RECTANGULAR_LAUNCHER=PASS'),
]:
    if log.splitlines().count(marker) != 1:
        raise SystemExit(f'Launcher marker {marker} missing or duplicated; gate unpaid')
    pattern = rf"^Test Case '-\[BainLuckWatchUITests\.{suite} {case}\]' (passed|failed|skipped) \([0-9.]+ seconds\)\.$"
    if re.findall(pattern, log, re.MULTILINE) != ['passed']:
        raise SystemExit(f'Actual launcher host/tap {case} did not pass exactly once; gate unpaid')

PYCORNER
fi
PHASE='full-suite receipt verification'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
if [[ "$SHARD" != full ]]; then
  python3 "$ROOT/tools/watch_ui_shards.py" receipt --shard "$SHARD" --directory "$OUT" --sha "$SHA" --exit-code "$TEST_EXIT"
  exit 0
fi


python3 "$ROOT/tools/watch_iphone_receipt.py" --log "$OUT/tests.log" \
  --exit-code "$TEST_EXIT" --sha "$SHA" --output "$OUT/receipt.json"
