#!/bin/sh
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(mktemp -d /tmp/watch-telemetry.XXXXXX)
trap 'rm -rf "$OUT"' EXIT
swiftc -parse-as-library -swift-version 5 \
  "$ROOT/ios/Bain Luck/Bain Luck/Utilities/WatchTelemetryProtocol.swift" \
  "$ROOT/tools/tests/watch-telemetry/main.swift" -o "$OUT/checks"
"$OUT/checks"
