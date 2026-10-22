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
        var resyncs = 0
        /// Frames and delivery edges in the order the owner saw them (#10468).
        var log: [String] = []
        var openFailure: Error?
        /// What the OWNER does with a frame (#10468): the page acknowledges only
        /// a price it actually adopted. Defaults to adopting every frame, which
        /// is what the cases written before #10468 describe.
        var adopts: (LiveStreamFrame) -> Bool = { _ in true }
        /// #10090 — reopen deadlines the controller armed, fired on THIS clock.
        final class Deadline {
            let at: TimeInterval
            let action: @MainActor () -> Void
            var cancelled = false
            init(at: TimeInterval, action: @escaping @MainActor () -> Void) {
                self.at = at
                self.action = action
            }
        }
        var deadlines: [Deadline] = []
        /// The healthy-rollover jitter, pinned so `reopenAt` is exact.
        var healthyDelay: TimeInterval = 0.3
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
                onFrame: { [self] f in
                    frames.append(f)
                    log.append("frame")
                    if adopts(f) { controller.acknowledgeAcceptedPrice() }
                },
                onDeliveringChange: { [self] d in
                    deliveringChanges.append(d)
                    log.append("delivering:\(d)")
                },
                onResync: { [self] in resyncs += 1 },
                schedule: { [self] delay, action in
                    let deadline = Deadline(at: clock + delay, action: action)
                    deadlines.append(deadline)
                    return { deadline.cancelled = true }
                },
                healthyRolloverDelay: { [self] in healthyDelay }
            )
        }

        /// Advance the clock and let the controller observe it, the way its
        /// owner's timer does. Armed deadlines that fall due fire first, as
        /// they would in production, where they are not waiting on the tick.
        @MainActor
        func advance(_ seconds: TimeInterval) {
            elapse(seconds)
            controller.tick()
        }

        /// Advance the clock WITHOUT a tick: only the armed deadlines run.
        @MainActor
        func elapse(_ seconds: TimeInterval) {
            clock += seconds
            for deadline in deadlines where !deadline.cancelled && deadline.at <= clock {
                deadline.cancelled = true
                deadline.action()
            }
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

        // The Rig's owner adopts this frame and acknowledges it (#10468).
        rig.current?.fire("probability", frameJSON())
        XCTAssertTrue(rig.controller.state.delivering, "an adopted frame must take push back over")
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
            rig.controller.state.reopenAt, rig.clock + rig.healthyDelay,
            "a healthy stream's rollover must not inherit the backoff"
        )
        rig.elapse(rig.healthyDelay)
        rig.current?.fire("open")

        rig.current?.fire("reconnect")                     // fast again: starts at 1 s
        XCTAssertEqual(rig.controller.state.reopenAt, rig.clock + 1)
    }

    // MARK: - #10090: a rollover reopens at its deadline, not at the next tick

    func testAHealthyRolloverReopensAtItsDeadlineWithoutATick10090() {
        // The server rolls a healthy stream at its age ceiling (or every
        // stream when its hub fails) and replays only the latest frame on the
        // new one. The owner ticks every 5 s; a reopen left to the tick held
        // the page on a number no socket was updating for 1–6 s.
        let rig = Rig()
        rig.startDelivering()
        rig.clock += 120
        rig.current?.fire("reconnect")
        XCTAssertEqual(rig.controller.state.reopenAt, rig.clock + 0.3)

        rig.elapse(0.29)
        XCTAssertEqual(rig.controller.state.connections, 1, "reopened before its own deadline")
        rig.elapse(0.01)
        XCTAssertEqual(rig.controller.state.connections, 2, "the deadline did not reopen without a tick")
        XCTAssertNil(rig.controller.state.reopenAt)
        rig.current?.fire("open")
        rig.current?.fire("probability", frameJSON(p: 0.7))
        XCTAssertTrue(rig.controller.state.delivering)
        XCTAssertEqual(rig.frames.last?.p, 0.7, "the new socket's replay reached the owner")
    }

    func testTheShippedHealthyDelayIsAQuickJitteredRetry10090() {
        // Not zero (a hub failure rolls every stream at once), and under the
        // old 1 s floor.
        XCTAssertEqual(LiveStreamTiming.healthyRolloverDelay.lowerBound, 0.25)
        XCTAssertEqual(LiveStreamTiming.healthyRolloverDelay.upperBound, 0.5)
        XCTAssertLessThan(LiveStreamTiming.healthyRolloverDelay.upperBound, LiveStreamTiming.reconnectBaseDelay)
    }

    func testAFastRolloverStillWaitsItsWholeBackoff10090() {
        // A server rolling streams over at once is in trouble. The deadline
        // replaces the tick, never the backoff: no reopen before 1 s, 2 s.
        let rig = Rig()
        rig.startDelivering()
        rig.current?.fire("reconnect")
        rig.elapse(0.99)
        XCTAssertEqual(rig.controller.state.connections, 1, "a fast rollover reopened early")
        rig.elapse(0.01)
        XCTAssertEqual(rig.controller.state.connections, 2)
        rig.current?.fire("open")

        rig.current?.fire("reconnect")
        rig.elapse(1.99)
        XCTAssertEqual(rig.controller.state.connections, 2, "the second fast rollover lost its backoff")
        rig.elapse(0.01)
        XCTAssertEqual(rig.controller.state.connections, 3)
    }

    func testALateDeadlineAfterATickReopenedOpensNothing10090() {
        // Whichever of the tick and the deadline gets there first reopens;
        // the second must find nothing to do, or one rollover is two sockets.
        let rig = Rig()
        rig.startDelivering()
        rig.clock += 120
        rig.current?.fire("reconnect")
        let armed = rig.deadlines.last
        rig.clock += 1
        rig.controller.tick()                              // the tick wins
        XCTAssertEqual(rig.controller.state.connections, 2)
        XCTAssertEqual(armed?.cancelled, true, "the reopen did not retire its own deadline")

        armed?.action()                                    // a timer that ran anyway
        XCTAssertEqual(rig.controller.state.connections, 2, "a late deadline opened a second socket")
        XCTAssertEqual(rig.handles.first?.closeCount, 1)
        XCTAssertEqual(rig.handles.last?.closeCount, 0, "the live socket was disturbed")
    }

    func testAStaleDeadlineCannotOpenTheNextRolloverEarly10090() {
        // A deadline from the PREVIOUS rollover firing late must not stand in
        // for the next one's backoff.
        let rig = Rig()
        rig.startDelivering()
        rig.clock += 120
        rig.current?.fire("reconnect")
        let first = rig.deadlines.last
        rig.elapse(rig.healthyDelay)
        rig.current?.fire("open")
        rig.current?.fire("reconnect")                     // fast: 1 s backoff
        XCTAssertEqual(rig.controller.state.connections, 2)

        first?.action()
        XCTAssertEqual(rig.controller.state.connections, 2, "an old deadline opened the next rollover early")
        rig.elapse(1)
        XCTAssertEqual(rig.controller.state.connections, 3)
    }

    func testStopCancelsAnArmedReopen10090() {
        // Leaving the page (or `closed`) between a rollover and its reopen.
        let rig = Rig()
        rig.startDelivering()
        rig.clock += 120
        rig.current?.fire("reconnect")
        let armed = rig.deadlines.last
        rig.controller.stop()
        XCTAssertEqual(armed?.cancelled, true, "stop left the reopen armed")

        armed?.action()
        rig.advance(60)
        XCTAssertEqual(rig.controller.state.connections, 1, "a stopped stream reopened")
        XCTAssertTrue(rig.controller.state.stopped)
    }

    func testARefusedReopenAtTheDeadlineIsStillTerminal10090() {
        // The deadline reopens through the same `connect()`: an open that
        // throws there is a refusal, and nothing retries it.
        let rig = Rig()
        rig.startDelivering()
        rig.clock += 120
        rig.current?.fire("reconnect")
        rig.openFailure = URLError(.badServerResponse)
        rig.elapse(rig.healthyDelay)
        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertFalse(rig.controller.state.delivering)
        rig.openFailure = nil
        rig.advance(60)
        XCTAssertEqual(rig.controller.state.connections, 1, "a refused reopen was retried")
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

    // MARK: - #10468: A FRAME THE OWNER REFUSED IS NOT A DELIVERY

    func testResyncKeepsTransportAliveWithoutRenewingPriceDelivery10090() {
        let rig = Rig()
        rig.startDelivering()
        for generation in 1...5 {
            rig.clock += 20
            rig.current?.fire("resync", "{\"generation\":\(generation)}")
            rig.controller.tick()
        }
        XCTAssertEqual(rig.resyncs, 5)
        XCTAssertTrue(rig.frames.isEmpty, "an invalidation is not a probability")
        XCTAssertFalse(rig.controller.state.delivering, "resync renewed the price budget")
        XCTAssertFalse(rig.controller.state.stopped, "resync proves transport activity")
        XCTAssertEqual(rig.controller.state.connections, 1, "resync never reopens the stream")
    }

    func testResyncInvalidatesOncePerIncreasingValidGeneration10090() {
        let rig = Rig()
        rig.startDelivering()
        for raw in [#"{"generation":1}"#, #"{"generation":1}"#, #"{"generation":0}"#,
                    #"{"generation":-1}"#, #"{"generation":"2"}"#, #"{"generation":true}"#,
                    #"{}"#, "not json", #"{"generation":2}"#, #"{"generation":1}"#] {
            rig.current?.fire("resync", raw)
        }
        XCTAssertEqual(rig.resyncs, 2, "duplicates, older and malformed generations cannot multiply reads")
        rig.current?.fire("open")
        rig.current?.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(rig.resyncs, 3, "a transport reopen can connect to a new hub on the same handle")
    }

    func testRetiredResyncIsIgnoredAndSuccessorGenerationStartsAgain10090() {
        let rig = Rig()
        rig.startDelivering()
        let retired = rig.current
        retired?.fire("resync", #"{"generation":9}"#)
        retired?.fire("reconnect")
        rig.advance(2)
        XCTAssertEqual(rig.controller.state.connections, 2)
        retired?.fire("resync", #"{"generation":10}"#)
        XCTAssertEqual(rig.resyncs, 1, "a retired socket invalidated its successor")
        rig.current?.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(rig.resyncs, 2, "the successor has its own recovery generation")
        rig.controller.stop()
        rig.current?.fire("resync", #"{"generation":2}"#)
        XCTAssertEqual(rig.resyncs, 2, "a stopped controller invalidated the page")
    }

    func testRefusedFramesAndHeartbeatsDoNotRenewTheDataBudget() {
        // THE DEFECT. Every decoded frame used to rearm the delivery clock, so
        // a stream of frames the page refused (old/equal revision, wrong event,
        // no usable price) kept polling off forever behind an unmoving price.
        let rig = Rig()
        rig.adopts = { _ in false }
        rig.startDelivering()

        for _ in 0..<5 {                                   // 100 seconds
            rig.clock += 20
            rig.current?.fire("heartbeat")
            rig.current?.fire("probability", frameJSON())
            rig.controller.tick()
        }

        XCTAssertEqual(rig.frames.count, 5, "refused frames are still handed to the owner")
        XCTAssertFalse(rig.controller.state.delivering, "refused frames were treated as delivery")
        XCTAssertFalse(rig.controller.state.stopped, "frames and heartbeats keep the TRANSPORT alive")
        XCTAssertEqual(rig.current?.closeCount, 0)
        XCTAssertEqual(rig.controller.state.connections, 1)
        XCTAssertEqual(rig.deliveringChanges, [true, false])
    }

    func testOnlyAnAcknowledgedFrameRenewsTheDataBudget() {
        // Both directions, one clock: the adopted frame at +60 renews the
        // budget to +150; refused frames after it do not extend it further.
        let rig = Rig()
        var adoptNext = false
        rig.adopts = { _ in defer { adoptNext = false }; return adoptNext }
        rig.startDelivering()

        rig.clock += 60
        adoptNext = true
        rig.current?.fire("probability", frameJSON(p: 0.63))
        for _ in 0..<4 {                                   // +80 … +140
            rig.clock += 20
            rig.current?.fire("heartbeat")
            rig.current?.fire("probability", frameJSON(p: 0.63))
            rig.controller.tick()
        }
        XCTAssertTrue(rig.controller.state.delivering, "an adopted price renews the data budget")

        rig.clock += 11                                    // +151: 91s after the adopted frame
        rig.current?.fire("heartbeat")
        rig.current?.fire("probability", frameJSON(p: 0.63))
        rig.controller.tick()
        XCTAssertFalse(rig.controller.state.delivering, "refused frames extended the budget")
        XCTAssertFalse(rig.controller.state.stopped)
    }

    func testAnAcknowledgedFrameTakesPushBackAfterTheDataDeadline() {
        let rig = Rig()
        rig.adopts = { $0.p == 0.70 }
        rig.startDelivering()
        rig.clock += 91
        rig.current?.fire("heartbeat")
        rig.controller.tick()
        XCTAssertFalse(rig.controller.state.delivering)

        rig.current?.fire("probability", frameJSON(p: 0.62))  // refused
        XCTAssertFalse(rig.controller.state.delivering, "a refused frame took push back over")
        rig.current?.fire("probability", frameJSON(p: 0.70))  // adopted
        XCTAssertTrue(rig.controller.state.delivering, "an adopted frame must take push back over")
        XCTAssertEqual(rig.controller.state.connections, 1, "recovery must not need a reconnect")
        XCTAssertEqual(rig.deliveringChanges, [true, false, true])
    }

    func testTheAcknowledgementEdgeFollowsTheFrameItAcknowledges() {
        // The owner acknowledges from INSIDE its frame callback, after it has
        // committed the price, so the delivering edge it causes is observed
        // after the frame — never before it.
        let rig = Rig()
        rig.controller.start()                             // no `open`: not delivering yet
        rig.current?.fire("probability", frameJSON())
        XCTAssertEqual(rig.log, ["frame", "delivering:true"])
    }

    func testAnAcknowledgementIsRefusedWithoutALiveSocket() {
        // Between a rollover and its reopen there is no socket, and after stop
        // there never will be: an acknowledgement (e.g. a late authoritative
        // re-read) cannot claim delivery for either.
        let rig = Rig()
        rig.startDelivering()
        rig.current?.fire("reconnect")
        XCTAssertNotNil(rig.controller.state.reopenAt)
        rig.controller.acknowledgeAcceptedPrice()
        XCTAssertFalse(rig.controller.state.delivering, "a rolled-over stream must push again")

        rig.advance(1.5)
        rig.current?.fire("open")
        XCTAssertTrue(rig.controller.state.delivering)

        rig.controller.stop()
        rig.controller.acknowledgeAcceptedPrice()
        XCTAssertFalse(rig.controller.state.delivering, "a stopped stream acknowledged a price")
        XCTAssertEqual(rig.deliveringChanges, [true, false, true, false])
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
    func testFoldedPreviewFloorAndResyncDoNotCreateDelivery() {
        let handle = FakeHandle()
        var floors: [String] = []
        var callbacks: [String] = []
        var clock: TimeInterval = 100
        let controller = LiveStreamController(
            open: { handle }, now: { clock }, onFrame: { _ in XCTFail("control is not a price") },
            onDeliveringChange: { _ in }, onResync: { callbacks.append("resync") },
            onPreviewFloor: { floors.append($0) }, onPreviewReset: { callbacks.append("reset") },
            schedule: { _, _ in {} })
        controller.start()
        handle.fire("open")
        callbacks.removeAll()
        let floor = #"{"event_id":4242,"floor":{"4243":21}}"#
        handle.fire("fold_preview_floor", floor)
        XCTAssertEqual(floors, [floor])
        XCTAssertEqual(callbacks, [])
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(callbacks, ["reset", "resync"], "withdraw before requesting the new quote")
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(callbacks, ["reset", "resync"], "dedup is retained")
        clock += LiveStreamTiming.dataSilenceTimeout + 1
        handle.fire("fold_preview_floor", floor)
        controller.tick()
        XCTAssertFalse(controller.state.delivering, "floor controls cannot renew data freshness")
        controller.stop()
    }

}
