#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
NODE_BIN="${NODE_BIN:-node}"
if ! command -v "$NODE_BIN" >/dev/null 2>&1; then
  printf 'Node.js >=22 is required. Set NODE_BIN to its executable. Nothing was started.\n' >&2
  exit 127
fi
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<22){console.error("Node.js >=22 required; found "+process.versions.node);process.exit(2)}'
exec "$NODE_BIN" run-review.mjs
