#!/bin/bash
# #4932: compile the actual Watch app, independently of iPhone-only native gates.
# No simulator boot, signing, provisioning, archive, upload or Apple account writes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${WATCH_BUILD_OUTPUT:-$(mktemp -d /tmp/bainluck-watch-build.XXXXXX)}"
mkdir -p "$OUT"
echo "Source: $(git -C "$ROOT" rev-parse HEAD)"
echo "Evidence: $OUT"
for PLATFORM in watchsimulator watchos; do
  if [[ "$PLATFORM" == watchsimulator ]]; then
    DESTINATION='generic/platform=watchOS Simulator'
  else
    DESTINATION='generic/platform=watchOS'
  fi
  LOG="$OUT/$PLATFORM.log"
  if xcodebuild -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
    -scheme BainLuckWatch -configuration Debug -destination "$DESTINATION" \
    -derivedDataPath "$OUT/$PLATFORM" CODE_SIGNING_ALLOWED=NO \
    'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' build > "$LOG" 2>&1; then
    grep -F '** BUILD SUCCEEDED **' "$LOG"
  else
    RESULT=$?
    tail -60 "$LOG"
    echo "$PLATFORM BUILD EXIT: $RESULT; full log: $LOG" >&2
    exit "$RESULT"
  fi
  # A successful command alone is insufficient: require an executable app bundle.
  APP="$OUT/$PLATFORM/Build/Products/Debug-$PLATFORM/BainLuckWatch Watch App.app"
  python3 - "$APP" "$PLATFORM" <<'PY'
import pathlib, plistlib, subprocess, sys
app = pathlib.Path(sys.argv[1])
with (app / 'Info.plist').open('rb') as stream:
    info = plistlib.load(stream)
binary = app / info['CFBundleExecutable']
assert binary.is_file(), f'Missing app executable: {binary}'
description = subprocess.check_output(['file', str(binary)], text=True)
assert 'Mach-O' in description, description
assert not list((app / 'PlugIns').glob('*.appex')), 'Deferred complication unexpectedly embedded'
print(f"{sys.argv[2]}: executable verified, {info['CFBundleIdentifier']}")
PY
done
echo 'PASS: Watch simulator/device SDK builds. Runtime, signing and distribution NOT verified.'
