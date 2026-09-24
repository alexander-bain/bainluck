import Foundation
// #920 — the release cut, over a REAL socket. `server.py PORT drop` ends the
// first connection with no `reconnect` and no `closed` frame, which is what a
// dyno restart leaves the phone. Before the fix the real transport called that
// closed-for-good and the page polled for the rest of the match; after it, the
// transport reopens after the server's `retry:` delay and push comes back on
// the SAME controller connection. Run against master's sources this fails —
// that is the control.
var failures = 0, checks = 0
func check(_ ok: Bool, _ n: String) { checks += 1; if !ok { failures += 1; print("  FAIL  \(n)") } else { print("  ok    \(n)") } }

@main struct E2EDrop {
    @MainActor static func main() async {
        let port = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "8792"
        var frames: [LiveStreamFrame] = []
        var delivering: [Bool] = []
        let controller = LiveStreamController(
            open: {
                // The production retry delay, not a test one: this is the wait a
                // reader actually sits through.
                let t = try LiveEventStreamTransport(eventId: 1, baseURL: "http://127.0.0.1:\(port)")
                t.connect()
                return t
            },
            now: { Date().timeIntervalSince1970 },
            onFrame: { f in frames.append(f); print("  FRAME p=\(f.p ?? -1)") },
            onDeliveringChange: { d in delivering.append(d); print("  DELIVERING -> \(d)") }
        )
        controller.start()
        for _ in 0..<60 {
            try? await Task.sleep(nanoseconds: 200_000_000)
            controller.tick()
            if controller.state.stopped { break }
        }

        print("\nframes: \(frames.map { $0.p ?? -1 })  delivering: \(delivering)")
        check(frames.first?.p == 0.55, "a price before the cut")
        check(frames.count == 2 && frames.last?.p == 0.46, "a price AFTER the cut — push came back (got \(frames.count))")
        check(delivering.starts(with: [true, false, true]), "push → polling at the cut → push again")
        check(controller.state.connections == 1, "the transport reconnected itself (controller connections=\(controller.state.connections))")
        print("\n\(checks - failures)/\(checks) checks passed, \(failures) failed")
        exit(failures == 0 ? 0 : 1)
    }
}
