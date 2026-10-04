#!/bin/bash
# Companion safety gate: build unsigned non-iOS products and inspect the dependency graph.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
  echo 'Non-iOS plan gate requires a disposable GitHub-hosted runner.' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/watch-non-ios-plan"
mkdir -p "$OUT"
RUN="$(mktemp -d "$OUT/run.XXXXXX")"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
PLATFORM="${1:?Specify macOS}"
case "$PLATFORM" in macOS) ;; *) exit 2 ;; esac
  python3 - "$OUT/$PLATFORM-receipt.json" "$SHA" "$PLATFORM" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'sha': sys.argv[2], 'platform': sys.argv[3], 'verdict': 'UNPAID', 'reason': 'Unsigned build and packaging exclusion have not passed inspection'}, indent=2) + '\n')
PY
xcodebuild -version > "$OUT/toolchain.txt"
FAILED=0
  if xcodebuild build -project "$ROOT/ios/Bain Luck/Bain Luck.xcodeproj" \
    -scheme 'Bain Luck' -configuration Release -destination "generic/platform=$PLATFORM" \
    -derivedDataPath "$RUN/$PLATFORM-DerivedData" -jobs 2 \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
    'OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox' \
    > "$OUT/$PLATFORM-plan.log" 2>&1; then
    RESULT=0
  else
    RESULT=$?
  fi
  printf '%s\n' "$RESULT" > "$OUT/$PLATFORM-exit.txt"
  if ! python3 "$ROOT/tools/watch_non_ios_plan.py" --log "$OUT/$PLATFORM-plan.log" \
    --products "$RUN/$PLATFORM-DerivedData/Build/Products" \
    --platform "$PLATFORM" --exit-code "$RESULT" --sha "$SHA" \
    --output "$OUT/$PLATFORM-receipt.json"; then
    FAILED=1
  fi
exit "$FAILED"
