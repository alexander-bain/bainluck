import Foundation

// Standalone runner for the SAME scenarios as BainLuckTests/LiveStreamControllerTests.swift,
// compiled against the REAL Bain Luck/Services/LiveStreamController.swift. It exists only
// because this sandbox cannot resolve the app target's Firebase SPM binaries, so XCTest
// cannot be executed here. It is not a substitute for that file — it is evidence that the
// lifecycle in the shipped source behaves as the guard asserts.

var failures = 0
var checks = 0
func check(_ ok: Bool, _ name: String) {
    checks += 1
    if !ok { failures += 1; print("  FAIL  \(name)") } else { print("  ok    \(name)") }
}

@MainActor final class FakeHandle: LiveStreamHandle {
    private var handlers: [String: [@MainActor (String) -> Void]] = [:]
    var closeCount = 0
    var isClosed = false
    func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
        handlers[event, default: []].append(handler)
    }
    func close() { closeCount += 1; isClosed = true }
    func fire(_ event: String, _ data: String = "") {
        for h in handlers[event] ?? [] { h(data) }
    }
}

@MainActor final class Rig {
    var clock: TimeInterval = 1000
    var handles: [FakeHandle] = []
    var frames: [LiveStreamFrame] = []
    var deliveringChanges: [Bool] = []
    var openFailure: Error?
    var controller: LiveStreamController!
    var current: FakeHandle? { handles.last }
    init() {
        controller = LiveStreamController(
            open: { [self] in
                if let openFailure { throw openFailure }
                let h = FakeHandle(); handles.append(h); return h
            },
            now: { [self] in clock },
            onFrame: { [self] f in frames.append(f) },
            onDeliveringChange: { [self] d in deliveringChanges.append(d) }
        )
    }
    func advance(_ s: TimeInterval) { clock += s; controller.tick() }
    func startDelivering() { controller.start(); current?.fire("open") }
}

func frameJSON(eventId: Int = 15293206, p: Double = 0.62, status: String = "live") -> String {
    "{\"event_id\":\(eventId),\"p\":\(p),\"source\":\"blend\",\"source_value\":\(p),\"updated_at\":\"2026-09-03T09:00:00Z\",\"status\":\"\(status)\"}"
}

@main struct Harness {
    @MainActor static func main() {
        print("open starts delivering")
        do { let r = Rig(); r.startDelivering()
            check(r.controller.state.delivering, "delivering")
            check(r.deliveringChanges == [true], "one edge")
            check(r.controller.state.connections == 1, "one connection") }

        print("a probability frame is decoded and handed on")
        do { let r = Rig(); r.startDelivering(); r.current?.fire("probability", frameJSON(p: 0.62))
            check(r.frames.count == 1, "one frame")
            check(r.frames.first?.eventId == 15293206, "eventId decoded")
            check(r.frames.first?.p == 0.62, "p decoded")
            check(r.frames.first?.status == "live", "status decoded") }

        print("a malformed frame does not abandon the stream")
        do { let r = Rig(); r.startDelivering()
            r.current?.fire("probability", "{not json")
            r.current?.fire("probability", "{\"p\":0.5}")
            check(r.frames.isEmpty, "no frame handed on")
            check(r.controller.state.delivering, "still delivering")
            check(!r.controller.state.stopped, "not stopped") }

        print("CERT-717 #2 — heartbeats alone stop counting as delivery")
        do { let r = Rig(); r.startDelivering()
            for _ in 0..<5 { r.clock += 20; r.current?.fire("heartbeat"); r.controller.tick() }
            check(!r.controller.state.delivering, "degraded to polling")
            check(!r.controller.state.stopped, "stream kept open")
            check(r.current?.closeCount == 0, "not closed") }

        print("CERT-717 #2 control — heartbeats keep the transport watchdog alive")
        do { let r = Rig(); r.startDelivering()
            for _ in 0..<5 { r.clock += 20; r.current?.fire("heartbeat"); r.controller.tick() }
            check(!r.controller.state.stopped, "not stopped")
            r.current?.fire("probability", frameJSON())
            check(r.controller.state.delivering, "a frame takes push back over")
            check(r.controller.state.connections == 1, "no reconnect needed") }

        print("transport silence is terminal")
        do { let r = Rig(); r.startDelivering(); r.advance(61)
            check(r.controller.state.stopped, "stopped")
            check(!r.controller.state.delivering, "not delivering")
            check(r.current?.closeCount == 1, "closed once") }

        print("transport watchdog does not fire early")
        do { let r = Rig(); r.startDelivering(); r.advance(59)
            check(!r.controller.state.stopped, "still open at 59s")
            check(r.controller.state.delivering, "still delivering at 59s") }

        print("CERT-717 #1 — reconnect reopens after its backoff")
        do { let r = Rig(); r.startDelivering(); r.clock += 120
            r.current?.fire("probability", frameJSON())
            r.current?.fire("reconnect")
            check(!r.controller.state.delivering, "gap is polled")
            check(!r.controller.state.stopped, "rollover is not a death")
            check(r.controller.state.reopenAt != nil, "reopen scheduled")
            r.advance(1.5)
            check(r.controller.state.connections == 2, "reopened")
            r.current?.fire("open")
            check(r.controller.state.delivering, "delivering again") }

        print("fast rollovers back off; a healthy one resets it")
        do { let r = Rig(); r.startDelivering()
            r.current?.fire("reconnect")
            check(r.controller.state.reopenAt == r.clock + 1, "1s after first fast rollover")
            r.advance(1); r.current?.fire("open")
            r.current?.fire("reconnect")
            check(r.controller.state.reopenAt == r.clock + 2, "2s after second")
            r.advance(2); r.current?.fire("open")
            r.clock += 120
            r.current?.fire("reconnect")
            check(r.controller.state.reopenAt == r.clock + 1, "healthy stream resets backoff") }

        print("closed is terminal and never reopens")
        do { let r = Rig(); r.startDelivering(); r.current?.fire("closed")
            check(r.controller.state.stopped, "stopped")
            r.advance(60); r.advance(60)
            check(r.controller.state.connections == 1, "never reopened") }

        print("an open that throws is a refusal, not a retry loop")
        do { let r = Rig(); r.openFailure = URLError(.cannotConnectToHost); r.controller.start()
            check(r.controller.state.stopped, "stopped")
            check(r.controller.state.connections == 0, "no connection")
            r.advance(60)
            check(r.controller.state.connections == 0, "still no retry") }

        print("an error from a CLOSED transport stops")
        do { let r = Rig(); r.startDelivering(); r.current?.isClosed = true; r.current?.fire("error")
            check(r.controller.state.stopped, "stopped")
            check(!r.controller.state.delivering, "not delivering") }

        print("an error from a transport still trying only stands down")
        do { let r = Rig(); r.startDelivering(); r.current?.isClosed = false; r.current?.fire("error")
            check(!r.controller.state.delivering, "stood down")
            check(!r.controller.state.stopped, "not stopped") }

        print("stop() closes the transport and is final")
        do { let r = Rig(); r.startDelivering(); r.controller.stop()
            check(r.current?.closeCount == 1, "closed")
            check(r.controller.state.stopped, "stopped")
            r.controller.start()
            check(r.controller.state.connections == 1, "no reconnect after stop") }

        print("delivering changes are edges, not repeats")
        do { let r = Rig(); r.startDelivering()
            r.current?.fire("probability", frameJSON())
            r.current?.fire("probability", frameJSON(p: 0.63))
            r.current?.fire("probability", frameJSON(p: 0.64))
            check(r.deliveringChanges == [true], "one edge only") }

        print("\n\(checks - failures)/\(checks) checks passed, \(failures) failed")
        exit(failures == 0 ? 0 : 1)
    }
}
