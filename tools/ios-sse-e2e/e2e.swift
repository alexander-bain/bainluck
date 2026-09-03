import Foundation
// End-to-end over a REAL socket: the real URLSession transport, the real SSE
// parser and the real lifecycle controller, against a server emitting exactly
// what `event_stream.py` writes. Production itself is unreadable from this
// sandbox — its egress proxy buffers streaming bodies, so no SSE body ever
// arrives — so this is the closest honest end-to-end available here.
var failures = 0, checks = 0
func check(_ ok: Bool, _ n: String) { checks += 1; if !ok { failures += 1; print("  FAIL  \(n)") } else { print("  ok    \(n)") } }

@main struct E2E {
    @MainActor static func main() async {
        // The port is passed in, not assumed: a stale server still holding a fixed
        // port answers with the WRONG half of the script and the run reports a
        // failure that is not the code's.
        let port = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "8791"
        var frames: [LiveStreamFrame] = []
        var delivering: [Bool] = []
        let controller = LiveStreamController(
            open: {
                let t = try LiveEventStreamTransport(eventId: 1, baseURL: "http://127.0.0.1:\(port)")
                t.connect()
                return t
            },
            now: { Date().timeIntervalSince1970 },
            onFrame: { f in frames.append(f); print("  FRAME p=\(f.p ?? -1) status=\(f.status ?? "-")") },
            onDeliveringChange: { d in delivering.append(d); print("  DELIVERING -> \(d)") }
        )
        controller.start()
        // Tick faster than production so the 1s rollover backoff is observed
        // inside the harness's lifetime; the controller's own constants are
        // untouched.
        for _ in 0..<60 {
            try? await Task.sleep(nanoseconds: 200_000_000)
            controller.tick()
            if controller.state.stopped { break }
        }

        print("\nframes: \(frames.map { $0.p ?? -1 })")
        check(frames.count == 3, "three frames across two connections (got \(frames.count))")
        check(frames.first?.p == 0.62, "first price parsed off the wire")
        check(frames.count > 1 && frames[1].p == 0.71, "second price, after a heartbeat")
        check(frames.last?.p == 0.88, "a price from the REOPENED connection")
        check(frames.last?.status == "completed", "the terminal status came through")
        check(controller.state.connections == 2, "reconnect reopened (connections=\(controller.state.connections))")
        check(controller.state.stopped, "closed was terminal")
        check(delivering.first == true, "delivering went true on open")
        check(delivering.last == false, "and false at the end, so the caller polls")
        print("\n\(checks - failures)/\(checks) checks passed, \(failures) failed")
        exit(failures == 0 ? 0 : 1)
    }
}
