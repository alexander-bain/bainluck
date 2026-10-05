#!/bin/bash
# An unsigned archive on a disposable runner; never signs, exports or uploads apps.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'Companion archive gate requires a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/watch-companion-archive"
mkdir -p "$OUT"
RUN="$(mktemp -d "$OUT/run.XXXXXX")"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
python3 - "$OUT/receipt.json" "$SHA" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'sha':sys.argv[2], 'verdict':'UNPAID', 'reason':'Archive has not passed packaging inspection', 'physical_install':'UNVERIFIED', 'distribution':'UNVERIFIED'})+'\n')
PY
xcodebuild -version > "$OUT/toolchain.txt"
echo 'Unsigned only: CODE_SIGNING_ALLOWED=NO; Crashlytics upload phase must skip.' > "$OUT/mode.txt"
# No provisioning updates, export, credentials, simulator or Apple service action.
if xcodebuild archive -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
  -scheme 'Bain Luck' -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$RUN/BainLuck.xcarchive" -derivedDataPath "$RUN/DerivedData" \
  -jobs 2 CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
  > "$OUT/archive.log" 2>&1; then
  python3 "$ROOT/tools/watch_companion_archive.py" "$RUN/BainLuck.xcarchive" \
    --sha "$SHA" --output "$OUT/receipt.json"
else
  RESULT=$?
  tail -60 "$OUT/archive.log"
  echo "Archive failed: $RESULT; package acceptance remains unpaid." >&2
  exit "$RESULT"
fi
