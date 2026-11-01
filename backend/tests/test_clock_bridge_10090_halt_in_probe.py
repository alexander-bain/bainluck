"""lane1 scratch: a cap reached while P's probe is in flight (not inside markers.wait)."""
import time
from tests.test_clock_marker_10090 import (MarkerConn, make_bridge, marker_env, wait_for,
                                           finish, cb)


def test_received_cap_during_probe():
    conn = MarkerConn()
    bridge, lines, _ = make_bridge([conn], marker_env(), period_s=0.1)
    bridge.armed("kalshi", 0.8)
    assert wait_for(lambda: "bind" in conn.kinds())
    bind = conn.bind()
    conn.probe_delay = 0.03
    fired = []

    def flood(c):
        if fired:
            return
        fired.append(1)
        cbk = c.listeners[bind["ch"]]
        for _ in range(cb.MARKER_MAX_RECEIVED + 1):
            c.loop.call_soon(cbk, c, 1, bind["ch"], "{}")
    conn.on_probe = flood
    assert wait_for(lambda: fired, timeout=1.0)
    finish(bridge)
    calls = [c[0] for c in conn.calls]
    print("calls after flood:", calls[calls.index("fetchval", 3):])
    print("sent kinds:", conn.kinds(), "last:", conn.sent[-1][2])
    unlistened = ("unlisten", bind["ch"]) in conn.calls
    print("unlisten called:", unlistened, "probes after flood:",
          calls[calls.index("fetchval", 3):].count("fetchval"))
    assert unlistened, "listener stayed attached after RECEIVED_CAP halt"
    assert conn.sent[-1][2].get("why") == "RECEIVED_CAP", "end misreports the halt"
