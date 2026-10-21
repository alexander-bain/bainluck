# Reproduce the selected isolated tests

From this directory, with the repository's frontend/backend dependencies already installed:

```sh
ln -s ../.. source                       # ignored local test alias, not app wiring
npm ci --prefix harness                 # only the pinned esbuild test dependency
export PYTHON=/path/to/backend-test-python
export LUA51=/path/to/official/redis/deps/lua/src/lua
bash run-focused.sh
```

The original run used Python 3.12, redis-py 8.1.0 and the standalone Lua 5.1.5 interpreter compiled from official Redis 7.2.16 commit 335554f18caf7bbf6b0ac2b3548133d750f00a1b. This is NOT Redis command execution. Do not start a server for these tests. Lua 5.3 can run the model tests but does not reproduce Lua 5.1's old tostring collision.

The selected client suite omits only the historical executable old-reader negative control. Its failure is retained as evidence; no old client reader is selectable. The unsafe numeric baseline is a `.txt` negative-control fixture read only by the explicit paired regression probe, never by an adapter. The command-composition tests all use the sole corrected Lua.

Tests run against this checkout's dependencies. The saved producer modules are current b2b92fe; prior frozen receipts used pinned a439 dependencies with those two current modules overlaid. Fresh results below are distinct from those receipts. No network or SQL is required by the focused producer fixtures.

Repository publication gates, run separately from frontend/backend as required:

```sh
cd source/backend
/path/to/backend-test-python -m pytest tests/test_startup.py -v
cd ../frontend
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run typecheck
```

Capture each exit status directly, without piping a gate to tail. `GATES.md` records actual results. A full app build does not typecheck an unwired prototype; the separate scoped tsc step in run-focused.sh covers its dependency closure.

The additive producer patch uses zero context to avoid whitespace-only context lines in the evidence diff. For inspection only, `git apply --check --unidiff-zero producer-chain-metadata/producer-chain.patch` must be run from the matching b2b92fe checkout with the correct patch path. This PR does not apply it.

The separate real-redis-unexecuted/test_selection.py checks corrected artifact hashes and Commands dispatch without opening a socket. Its23 real-engine cases have NOT run. Historical blocked runtime used the older Lua and cannot validate the numeric correction.
