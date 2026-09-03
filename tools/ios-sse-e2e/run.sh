#!/usr/bin/env bash
# #2687 — prove the native SSE client without Xcode.
#
# WHY THIS EXISTS. `BainLuckTests/LiveStreamControllerTests.swift` and
# `SSEFrameParserTests.swift` are the durable guards and they run in Xcode. They
# cannot run in this repo's agent sandbox: `xcodebuild` cannot resolve the app
# target's Firebase SPM binary artifacts (dl.google.com is unreachable), so the
# test target never builds. A lane that ships native code and can prove nothing
# about it is a lane shipping on hope.
#
# So these three runners compile the REAL shipped source files — not copies —
# and exercise them:
#
#   lifecycle-harness.swift  the same cases as LiveStreamControllerTests
#   parser-harness.swift     the same cases as SSEFrameParserTests
#   e2e.swift + server.py    the whole stack over a REAL SOCKET, against a server
#                            emitting exactly what event_stream.py writes
#
# THE THIRD ONE IS NOT A LUXURY. It is what caught the defect that shipped in the
# first draft: `URLSession.AsyncBytes.lines` DROPS EMPTY LINES, and the blank line
# is the only thing that terminates an SSE frame. The parser was correct, its unit
# tests passed, and the client would have delivered nothing for an entire match
# while reporting a healthy connection. Only bytes on a socket could see it.
#
# Production itself is NOT usable for this from the sandbox: the egress proxy
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
