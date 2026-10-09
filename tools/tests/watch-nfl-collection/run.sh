#!/bin/sh
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
TEST_BINARY=$(mktemp -d /tmp/watch-nfl-collection.XXXXXX)
trap 'rm -rf "$TEST_BINARY"' EXIT
swiftc -parse-as-library -swift-version 5 \
  "$ROOT/ios/Bain Luck/BainLuckWatch Watch App/WatchNFLCollectionModels.swift" \
  "$ROOT/tools/tests/watch-nfl-collection/main.swift" \
  -o "$TEST_BINARY/checks"
"$TEST_BINARY/checks" "$ROOT/tools/tests/watch-nfl-collection/fixtures"
