#!/usr/bin/env bash
# #2687 — prove the native SSE client without Xcode.
#
# WHY THIS EXISTS. `BainLuckTests/LiveStreamControllerTests.swift` and
# `SSEFrameParserTests.swift` are the durable guards, they run under `xcodebuild`,
# and they DO run in this sandbox — 796 tests / 0 failures via the cloned-SPM-store
# recipe, which takes a simulator and about two minutes. These runners are not a
# substitute for that and no longer claim to be. They earn their place twice:
#
#   1. THE END-TO-END ONE SEES WHAT XCTEST CANNOT. It is what caught the defect
#      that shipped in the first draft: `URLSession.AsyncBytes.lines` DROPS EMPTY
#      LINES, and the blank line is the only thing that terminates an SSE frame.
#      The parser was correct, every unit test passed, and the client would have
#      delivered nothing for an entire match while reporting a healthy connection.
#      Only bytes on a real socket could see it, and nothing in the XCTest suite
#      opens one.
#   2. They compile the REAL shipped source in about five seconds with no
#      simulator, so the lifecycle can be re-proved — or mutated and disproved —
#      between edits at a cost that makes it worth doing.
#
#   lifecycle-harness.swift  the same cases as LiveStreamControllerTests
#   parser-harness.swift     the same cases as SSEFrameParserTests
#   e2e.swift + server.py    the whole stack over a REAL SOCKET, against a server
#                            emitting exactly what event_stream.py writes
#
# PRODUCTION IS NOT USABLE for the end-to-end from the sandbox: the egress proxy
# buffers streaming response bodies, so no SSE body ever arrives (verified with
# `curl -N`: 200 + `content-type: text/event-stream`, zero body lines in 30s).
#
#   tools/ios-sse-e2e/run.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
SRC="../../ios/Bain Luck/Bain Luck/Services"
OUT="$(mktemp -d)"
fail=0

echo "== lifecycle =="
xcrun swiftc -O -o "$OUT/lifecycle" "$SRC/LiveStreamController.swift" lifecycle-harness.swift || exit 2
"$OUT/lifecycle" || fail=1

echo
echo "== wire parser =="
xcrun swiftc -O -o "$OUT/parser" "$SRC/LiveStreamController.swift" "$SRC/LiveEventStreamTransport.swift" parser-harness.swift || exit 2
"$OUT/parser" || fail=1

echo
echo "== end to end over a real socket =="
PORT="${SSE_PORT:-$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')}"
python3 server.py "$PORT" > "$OUT/server.log" 2>&1 &
server=$!
trap 'kill $server 2>/dev/null' EXIT
sleep 1.5
xcrun swiftc -O -o "$OUT/e2e" "$SRC/LiveStreamController.swift" "$SRC/LiveEventStreamTransport.swift" e2e.swift || exit 2
"$OUT/e2e" "$PORT" || fail=1

echo
[ $fail -eq 0 ] && echo "ALL GREEN" || echo "FAILURES ABOVE"
exit $fail
