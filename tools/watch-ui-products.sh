#!/bin/bash
# Hosted build-only producer: runtime metadata is read; devices belong to consumers.
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
PHONE_SDK_VERSION="$(xcrun --sdk iphonesimulator --show-sdk-version 2>> "$OUT/preflight.log")"
printf '%s\n' "$PHONE_SDK_VERSION" > "$OUT/phone-sdk-version.txt"
# Building products needs installed SDK-compatible runtime metadata, not devices.
python3 - "$OUT/simulators.json" "$SDK_VERSION" "$PHONE_SDK_VERSION" > "$OUT/destination-spec.txt" 2>> "$OUT/preflight.log" <<'BUILD_RUNTIMES'
import json, sys
from pathlib import Path
info = json.loads(Path(sys.argv[1]).read_text())
def version(value):
    return tuple((value.split(".") + ["0", "0"])[:3])
for platform, sdk in (("watchOS", sys.argv[2]), ("iOS", sys.argv[3])):
    matches = [r for r in info["runtimes"] if r.get("isAvailable")
               and r.get("platform") == platform and version(r["version"]) == version(sdk)]
    if len(matches) != 1:
        raise SystemExit(f"Expected one exact available {platform} SDK runtime; producer unpaid")
    print(matches[0]["identifier"])
BUILD_RUNTIMES
RUNTIME="$(sed -n '1p' "$OUT/destination-spec.txt")"
PHONE_RUNTIME="$(sed -n '2p' "$OUT/destination-spec.txt")"
# Resolve the pinned dependency graph before building products. Both independent
# build-product directories reuse this run's downloads; no shared/global cache.
PHASE='resolve pinned packages before simulator product construction'
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
# The producer only builds/attests products. Device creation, pairing, boot and
# exact destination readiness remain required once per execution consumer.
# Derive a single explicit build architecture from both exact SDK-compatible
# available runtimes; the consumer separately proves its real pair supports it.
PHASE='select exact available simulator runtime build architecture'
python3 "$ROOT/tools/watch_ui_stage.py" phase --output-dir "$OUT" --phase "$PHASE"
python3 - "$OUT/simulators.json" "$RUNTIME" "$PHONE_RUNTIME" "$SDK_VERSION" "$PHONE_SDK_VERSION" "$OUT/simulator-architecture.json" <<'BUILD_ARCH'
import json, sys
from pathlib import Path
from tools.watch_simulator_architecture import select_build_runtime_pair
result = select_build_runtime_pair(json.loads(Path(sys.argv[1]).read_text()), *sys.argv[2:6])
Path(sys.argv[6]).write_text(json.dumps(result, indent=2) + "\n")
BUILD_ARCH
SIM_ARCH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["architecture"])' "$OUT/simulator-architecture.json")"
XCODE_ARGS=(
  -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
  -scheme BainLuckWatchUITests -configuration Debug
  -destination "generic/platform=watchOS Simulator"
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
  -destination "generic/platform=iOS Simulator" \
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
