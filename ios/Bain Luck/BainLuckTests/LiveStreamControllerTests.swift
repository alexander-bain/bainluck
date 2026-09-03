import XCTest
@testable import Bain_Luck

/// #2687 — the native SSE lifecycle, driven by a fake transport and a fake clock.
///
/// WHY THESE PARTICULAR CASES. This is a port of `frontend/lib/liveStreamController.ts`,
/// which is itself the SECOND attempt: CERT-717 blocked the first web version on
/// two P1 lifecycle defects that 51/51 backend and 27/27 frontend tests passed
/// straight over, because no test exercised either path. The two defects have a
/// case each here, named after them, and they are the reason this file exists at
/// all rather than a smoke test that a frame decodes.
///
/// NOTHING HERE TOUCHES A SOCKET OR THE WALL CLOCK. The transport is a fake the
/// test fires events into, and `now` is a variable the test advances — so every
/// timeout is exercised in microseconds and no case can flake on timing or
/// branch on the real clock (gotcha #44).
///
/// BOTH DIRECTIONS PER GOTCHA #43. Every "it degrades to polling" case has a
/// sibling proving push is NOT torn down when it should not be — a controller
/// that reported `delivering == false` unconditionally would satisfy the whole
/// degradation half and deliver nothing.
@MainActor
final class LiveStreamControllerTests: XCTestCase {

    // MARK: - Fakes

    /// A transport the test drives. `fire` is what the server would have sent.
    private final class FakeHandle: LiveStreamHandle {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        private(set) var closeCount = 0
        var isClosed = false

        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }

        func close() {
            closeCount += 1
            isClosed = true
        }

        @MainActor
        func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    /// Builds the controller over a fake clock the test owns.
    private final class Rig {
        var clock: TimeInterval = 1_000
        var handles: [FakeHandle] = []
        var frames: [LiveStreamFrame] = []
        var deliveringChanges: [Bool] = []
        var openFailure: Error?
        private(set) var controller: LiveStreamController!

        var current: FakeHandle? { handles.last }

        @MainActor
        init() {
            controller = LiveStreamController(
                open: { [self] in
                    if let openFailure { throw openFailure }
                    let h = FakeHandle()
                    handles.append(h)
                    return h
                },
                now: { [self] in clock },
                onFrame: { [self] f in frames.append(f) },
                onDeliveringChange: { [self] d in deliveringChanges.append(d) }
            )
        }

        /// Advance the clock and let the controller observe it, the way its
        /// owner's timer does.
        @MainActor
        func advance(_ seconds: TimeInterval) {
            clock += seconds
            controller.tick()
        }

        /// The happy path every case that is not about connecting starts from.
        @MainActor
        func startDelivering() {
            controller.start()
            current?.fire("open")
        }
    }

    private func frameJSON(
        eventId: Int = 15_293_206,
        p: Double = 0.62,
        status: String = "live"
    ) -> String {
        """
        {"event_id":\(eventId),"p":\(p),"source":"blend","source_value":\(p),\
        "updated_at":"2026-09-03T09:00:00Z","status":"\(status)"}
        """
    }

    // MARK: - The happy path, and the controls everything else depends on

    func testOpenStartsDelivering() {
        let rig = Rig()
        rig.startDelivering()
        XCTAssertTrue(rig.controller.state.delivering)
        XCTAssertEqual(rig.deliveringChanges, [true])
        XCTAssertEqual(rig.controller.state.connections, 1)
    }

    func testAProbabilityFrameIsDecodedAndHandedOn() {
        let rig = Rig()
        rig.startDelivering()
        rig.current?.fire("probability", frameJSON(p: 0.62))

        XCTAssertEqual(rig.frames.count, 1)
        XCTAssertEqual(rig.frames.first?.eventId, 15_293_206)
        XCTAssertEqual(rig.frames.first?.p, 0.62)
        XCTAssertEqual(rig.frames.first?.status, "live")
    }

    func testAMalformedFrameDoesNotAbandonTheStream() {
        // One bad frame is not a reason to stop pushing — and it must not reach
        // the caller, because a frame missing `event_id` handed on as-is is what
        // would blank a working hero.
        let rig = Rig()
        rig.startDelivering()
        rig.current?.fire("probability", "{not json")
        rig.current?.fire("probability", #"{"p":0.5}"#)

        XCTAssertTrue(rig.frames.isEmpty)
        XCTAssertTrue(rig.controller.state.delivering)
        XCTAssertFalse(rig.controller.state.stopped)
    }

    // MARK: - CERT-717 defect 2: A HEARTBEAT IS NOT A DELIVERY

    func testHeartbeatsAloneStopCountingAsDelivery() {
        // The exact silent failure: `worker-ws` dies, this server's socket stays
        // healthy, and heartbeats arrive forever. Polling must come back.
        let rig = Rig()
        rig.startDelivering()

        // 100 seconds of perfect transport health and not one price.
        for _ in 0..<5 {
            rig.clock += 20
            rig.current?.fire("heartbeat")
            rig.controller.tick()
        }

        XCTAssertFalse(rig.controller.state.delivering, "heartbeats were treated as delivery")
        XCTAssertFalse(rig.controller.state.stopped, "a quiet publisher must not tear down the stream")
        XCTAssertEqual(rig.current?.closeCount, 0)
    }

    func testHeartbeatsKeepTheTransportWatchdogAlive() {
        // The other direction, and the reason the heartbeat exists at all: with
        // heartbeats arriving, the 60s TRANSPORT timeout must never fire, so the
        // stream is still open and can recover the instant a price lands.
        let rig = Rig()
        rig.startDelivering()
        for _ in 0..<5 {
            rig.clock += 20
            rig.current?.fire("heartbeat")
            rig.controller.tick()
        }
        XCTAssertFalse(rig.controller.state.stopped)

        rig.current?.fire("probability", frameJSON())
        XCTAssertTrue(rig.controller.state.delivering, "a frame must take push back over")
        XCTAssertEqual(rig.controller.state.connections, 1, "recovery must not need a reconnect")
    }

    func testTransportSilenceIsTerminal() {
        // No frames AND no heartbeats AND no error callback. Nothing will ever
        // tell us; give up so the caller polls.
        let rig = Rig()
        rig.startDelivering()
        rig.advance(61)

        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertFalse(rig.controller.state.delivering)
        XCTAssertEqual(rig.current?.closeCount, 1)
    }

    func testTheTransportWatchdogDoesNotFireEarly() {
        // Both directions: 59 seconds of silence is inside the budget.
        let rig = Rig()
        rig.startDelivering()
        rig.advance(59)
        XCTAssertFalse(rig.controller.state.stopped)
        XCTAssertTrue(rig.controller.state.delivering)
    }

    // MARK: - CERT-717 defect 1: RECONNECT IS A ROLLOVER, NOT A DEATH

    func testReconnectReopensAfterItsBackoff() {
        // The server closes every stream at its 900s ceiling and says so. A
        // client that treats that as failure gives a fan push for fifteen
        // minutes and then silently polls for the rest of the match.
        let rig = Rig()
        rig.startDelivering()
        rig.clock += 120                       // a healthy stream
        rig.current?.fire("probability", frameJSON())

        rig.current?.fire("reconnect")
        XCTAssertFalse(rig.controller.state.delivering, "the gap must be polled, not frozen")
        XCTAssertFalse(rig.controller.state.stopped, "a rollover is not a death")
        XCTAssertNotNil(rig.controller.state.reopenAt)

        rig.advance(1.5)
        XCTAssertEqual(rig.controller.state.connections, 2, "the stream did not reopen")
        rig.current?.fire("open")
        XCTAssertTrue(rig.controller.state.delivering)
    }

    func testFastRolloversBackOffAndAHealthyOneResetsIt() {
        // A server rolling a stream over immediately is a server in trouble;
        // reopening on a 1s timer forever would hammer it. A stream that lived
        // past `healthyStream` was fine and its rollover starts from scratch.
        let rig = Rig()
        rig.startDelivering()

        rig.current?.fire("reconnect")                     // fast rollover 1
        XCTAssertEqual(rig.controller.state.reopenAt, rig.clock + 1)
        rig.advance(1)
        rig.current?.fire("open")

        rig.current?.fire("reconnect")                     // fast rollover 2
        XCTAssertEqual(rig.controller.state.reopenAt, rig.clock + 2)
        rig.advance(2)
        rig.current?.fire("open")

        rig.clock += 120                                   // a HEALTHY stream
        rig.current?.fire("reconnect")
        XCTAssertEqual(
            rig.controller.state.reopenAt, rig.clock + 1,
            "a healthy stream's rollover must not inherit the backoff"
        )
    }

    func testClosedIsTerminalAndNeverReopens() {
        // The match ended. The caller refetches once and settles the page on the
        // final number; a stream held open on a decided event is pure cost.
        let rig = Rig()
        rig.startDelivering()
        rig.current?.fire("closed")

        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertFalse(rig.controller.state.delivering)

        rig.advance(60)
        rig.advance(60)
        XCTAssertEqual(rig.controller.state.connections, 1, "a closed stream reopened")
    }

    // MARK: - Refusals must not become retry loops

    func testAnOpenThatThrowsIsARefusalAndStops() {
        // 409 non-live, 503 at capacity, 404. The server has said no; retrying
        // against it is the failure this avoids.
        let rig = Rig()
        rig.openFailure = URLError(.cannotConnectToHost)
        rig.controller.start()

        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertFalse(rig.controller.state.delivering)
        XCTAssertEqual(rig.controller.state.connections, 0)

        rig.advance(60)
        XCTAssertEqual(rig.controller.state.connections, 0)
    }

    func testAnErrorFromAClosedTransportStops() {
        let rig = Rig()
        rig.startDelivering()
        rig.current?.isClosed = true
        rig.current?.fire("error")

        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertFalse(rig.controller.state.delivering)
    }

    func testAnErrorFromATransportStillTryingOnlyStandsDown() {
        // The blip. Report not-delivering so the caller polls, but do not tear
        // the stream down — a transport that retries itself may well come back.
        let rig = Rig()
        rig.startDelivering()
        rig.current?.isClosed = false
        rig.current?.fire("error")

        XCTAssertFalse(rig.controller.state.delivering)
        XCTAssertFalse(rig.controller.state.stopped)
    }

    // MARK: - stop()

    func testStopClosesTheTransportAndIsFinal() {
        let rig = Rig()
        rig.startDelivering()
        rig.controller.stop()

        XCTAssertEqual(rig.current?.closeCount, 1)
        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertFalse(rig.controller.state.delivering)

        rig.controller.start()
        XCTAssertEqual(rig.controller.state.connections, 1, "a stopped controller reconnected")
    }

    func testDeliveringChangesAreEdgesNotRepeats() {
        // The caller reconfigures its poll on every change. Emitting `true` on
        // every frame would rebuild the timer dozens of times a minute.
        let rig = Rig()
        rig.startDelivering()
        rig.current?.fire("probability", frameJSON())
        rig.current?.fire("probability", frameJSON(p: 0.63))
        rig.current?.fire("probability", frameJSON(p: 0.64))

        XCTAssertEqual(rig.deliveringChanges, [true])
    }
}
