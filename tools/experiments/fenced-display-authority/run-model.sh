#!/usr/bin/env bash
# No PostgreSQL or network listener; independent model/schedule/crash tests only.
set -euo pipefail
cd "$(dirname "$0")"
NODE_BIN="${NODE_BIN:-node}"
mkdir -p runtime
OUT="$(mktemp -d "$PWD/runtime/model-XXXXXX")"; export OUT
"$NODE_BIN" --test --test-concurrency=1 src/test.mjs
"$NODE_BIN" src/schedule-matrix.mjs
"$NODE_BIN" src/crash-matrix.mjs
"$NODE_BIN" --test --test-concurrency=1 review/test_*.mjs
printf 'Model checks passed; receipts: %s\n' "$OUT"
