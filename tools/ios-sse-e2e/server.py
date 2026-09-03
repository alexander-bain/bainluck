"""Port comes from argv[1]: a hardcoded one makes the proof flaky the moment a
stale run is still holding it, which it did on the first attempt.

A stand-in for /api/events/{id}/stream that emits EXACTLY what
backend/app/routes/event_stream.py writes — same field order, same event names,
same `retry:` preamble. Two connections, scripted, so the client's rollover is
exercised end to end rather than faked."""
import http.server, threading, time, json, sys

CONN = {"n": 0}

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def do_GET(self):
        if not self.path.endswith("/stream"):
            self.send_response(404); self.end_headers(); return
        CONN["n"] += 1
        n = CONN["n"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()

        def w(s):
            self.wfile.write(s.encode()); self.wfile.flush()

        def enc(payload, event):
            return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

        w("retry: 3000\n\n")
        w(enc({"event_id": 1}, "open"))
        time.sleep(0.3)
        if n == 1:
            w(enc({"event_id": 1, "p": 0.62, "source": "blend",
                   "source_value": 0.62, "updated_at": "2026-09-03T09:00:00Z",
                   "status": "live"}, "probability"))
            time.sleep(0.3)
            w(enc({"t": "2026-09-03T09:00:20Z"}, "heartbeat"))
            time.sleep(0.3)
            w(enc({"event_id": 1, "p": 0.71, "source": "blend",
                   "source_value": 0.71, "updated_at": "2026-09-03T09:00:40Z",
                   "status": "live"}, "probability"))
            time.sleep(0.3)
            # The 900s ceiling, told in words. NOT a death.
            w(enc({"reason": "max_age"}, "reconnect"))
        else:
            w(enc({"event_id": 1, "p": 0.88, "source": "blend",
                   "source_value": 0.88, "updated_at": "2026-09-03T09:15:00Z",
                   "status": "completed"}, "probability"))
            time.sleep(0.2)
            w(enc({"reason": "not_live"}, "closed"))
        time.sleep(0.2)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
print("READY", flush=True)
srv.serve_forever()
