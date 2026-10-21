#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${PYTHON:?Set PYTHON to the backend-test Python executable}"
: "${LUA51:?Set LUA51 to the standalone official vendored Lua 5.1 executable}"
export PYTHONDONTWRITEBYTECODE=1
export PRODUCER_DEPENDENCY_SOURCE="$(cd source && pwd -P)"
node --test monotonic-review/test_request_start_lease.cjs monotonic-review/test_hook_monotonic_lease.cjs
node --test review/monotonic-get/test_mounted_get_expiry.cjs
"$PYTHON" -m pytest -q -p no:cacheprovider monotonic-review/test_server_remaining.py
source/frontend/node_modules/.bin/tsc --project monotonic-review/tsconfig.json --noEmit
"$LUA51" atomic-numeric-encoding/tests/test_numeric.lua
"$LUA51" atomic-numeric-encoding/test_authority.lua atomic-numeric-encoding/
"$LUA51" atomic-numeric-encoding/test_races.lua atomic-numeric-encoding/
PYTHONPATH=atomic-numeric-encoding "$PYTHON" -m unittest discover -s atomic-numeric-encoding -p test_adapter.py -v
"$LUA51" review/atomic-numeric/test_independent.lua
"$LUA51" review/atomic-numeric/probe_ordering_regression.lua
"$PYTHON" review/atomic-numeric/test_adapter_boundary.py
"$PYTHON" -m pytest -q -p no:cacheprovider --asyncio-mode=auto --confcutdir=producer-chain-metadata producer-chain-metadata/tests
"$LUA51" producer-chain-metadata/tests/test_composition.lua producer-chain-metadata/
"$PYTHON" -m pytest -q -p no:cacheprovider --asyncio-mode=auto --confcutdir=review/producer-chain review/producer-chain/test_integration.py
"$PYTHON" real-redis-unexecuted/test_selection.py
