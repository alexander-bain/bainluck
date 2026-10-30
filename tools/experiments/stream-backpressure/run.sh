#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
NODE_BIN="${NODE_BIN:-node}"
if ! command -v "$NODE_BIN" >/dev/null 2>&1; then
  printf 'ERROR: Node.js runtime missing (%s). Install Node.js >=22 from the official vendor or set NODE_BIN to its executable path. No server was started.\n' "$NODE_BIN" >&2
  exit 127
fi
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<22){console.error("ERROR: Node.js >=22 required; found "+process.versions.node);process.exit(2)}'
MODE="${1:-test}"
mkdir -p results
case "$MODE" in
  pressure)
    "$NODE_BIN" src/run-bounded.mjs tests/baseline-failures.mjs | tee results/baseline-failures.txt
    "$NODE_BIN" src/run-bounded.mjs --test tests/backpressure-unit.mjs | tee results/backpressure-unit.txt
    "$NODE_BIN" src/run-bounded.mjs tests/backpressure-wire.mjs | tee results/backpressure-wire.txt
    ;;
  test)
    "$NODE_BIN" src/run-bounded.mjs --test tests/renewal-events.test.mjs tests/renewal-independent.test.mjs | tee results/renewal-test.txt
    "$NODE_BIN" src/run-bounded.mjs tests/baseline-failures.mjs | tee results/baseline-failures.txt
    "$NODE_BIN" src/run-bounded.mjs --test tests/backpressure-unit.mjs | tee results/backpressure-unit.txt
    "$NODE_BIN" src/run-bounded.mjs tests/backpressure-wire.mjs | tee results/backpressure-wire.txt
    MODEL_OUT="$(mktemp -d "${TMPDIR:-/tmp}/stream-model.XXXXXX")"
    trap 'rm -rf "$MODEL_OUT"' EXIT
    OUT="$MODEL_OUT" "$NODE_BIN" src/run-bounded.mjs --test tests/inherited-model.mjs | tee results/model-test.txt
    "$NODE_BIN" src/run-bounded.mjs --test tests/transport-unit.mjs | tee results/transport-unit.txt
    "$NODE_BIN" src/run-bounded.mjs tests/wire-test.mjs | tee results/wire-test.txt
    "$NODE_BIN" tests/audit-receipt.mjs | tee results/receipt-audit.json
    ;;
  serve) exec "$NODE_BIN" src/stream-server.mjs ;;
  model)
    MODEL_OUT="$(mktemp -d "${TMPDIR:-/tmp}/stream-model.XXXXXX")"
    trap 'rm -rf "$MODEL_OUT"' EXIT
    OUT="$MODEL_OUT" "$NODE_BIN" src/run-bounded.mjs --test tests/inherited-model.mjs | tee results/model-test.txt
    ;;
  *) echo 'Usage: ./run.sh [test|pressure|model|serve] (NODE_BIN configurable; server max 30 minutes)' >&2;exit 2;;
esac
