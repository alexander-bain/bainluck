import Foundation
import XCTest

@testable import Bain_Luck

/// latency/121 — the felt number on native.
///
/// These pin the three ways a screen-timing rail lies in the FLATTERING
/// direction, because those are the ones nobody notices:
///   1. a skeleton wearing `.firstRealCard()` reports a broken screen as instant;
///   2. a screen that never renders reports nothing, so the worst rows are
///      missing from the table exactly when they are worst;
///   3. `-1` collapsing into `0` turns "did not happen" into "happened instantly".
///
/// Plus the one that makes the whole queue worth doing: the native packet and
/// the web packet must be the SAME packet, or the promised single table is two
/// tables that have to be reconciled by hand.
@MainActor
final class ScreenTimingTests: XCTestCase {
    /// Collects packets instead of shipping them to Firebase.
    final class SpySink: ScreenTimingSink, @unchecked Sendable {
        private(set) var packets: [ScreenTimingPacket] = []
        func send(_ packet: ScreenTimingPacket) { packets.append(packet) }
    }

    /// A clock the test drives, so no assertion depends on wall time.
    final class FakeClock: @unchecked Sendable {
        var seconds: TimeInterval = 0
        var now: @Sendable () -> Date { { Date(timeIntervalSince1970: self.seconds) } }
    }

    private func recorder(
        _ sink: SpySink,
        _ clock: FakeClock,
        surface: String = "discover",
        entry: String = "cold"
    ) -> ScreenTimingRecorder {
        // `autoFinish: false` keeps the 30 s budget task out of the unit tests;
        // the budget itself is asserted separately by driving `finish()` directly.
        ScreenTimingRecorder(surface: surface, entry: entry, sink: sink, now: clock.now, autoFinish: false)
    }

    // MARK: - The number itself

    func testFirstCardMsIsMeasuredFromScreenAppearance() {
        let sink = SpySink(); let clock = FakeClock()
        let r = recorder(sink, clock)

        clock.seconds = 0.85
        r.markFirstCard()
        r.finish()

        XCTAssertEqual(sink.packets.count, 1)
        XCTAssertEqual(sink.packets[0].firstCardMs, 850)
        XCTAssertEqual(sink.packets[0].outcomeClass, "ok")
    }

    func testOnlyTheFirstCardSetsTheNumberButEveryCardCounts() {
        let sink = SpySink(); let clock = FakeClock()
        let r = recorder(sink, clock)

        clock.seconds = 0.4; r.markFirstCard()
        clock.seconds = 0.6; r.markFirstCard()
        clock.seconds = 0.9; r.markFirstCard()
        r.finish()

        XCTAssertEqual(sink.packets[0].firstCardMs, 400, "a SwiftUI body runs many times; only the first mark is the measurement")
        XCTAssertEqual(sink.packets[0].cardCount, 3)
        XCTAssertEqual(sink.packets[0].foldMs, 900, "the first screen settles at the LAST card, not the first")
    }

    // MARK: - The three flattering lies

    func testSkeletonMarkIsIgnored() {
        // 🔴 A placeholder wearing the marker would report the app as instant —
        // strictly worse than having no rail, because it would be believed.
        let sink = SpySink(); let clock = FakeClock()
        let r = recorder(sink, clock)

        r.markLoading(true)
        clock.seconds = 0.05
        r.markFirstCard()          // this is the shimmering placeholder
        clock.seconds = 1.7
        r.markLoading(false)
        r.markFirstCard()          // this is the real card
        r.finish()

        XCTAssertEqual(sink.packets[0].firstCardMs, 1700)
    }

    func testScreenThatNeverRendersReportsNoCardRatherThanNothing() {
        let sink = SpySink(); let clock = FakeClock()
        let r = recorder(sink, clock)

        clock.seconds = 30
        r.finish()

        XCTAssertEqual(sink.packets.count, 1, "silence is the expensive case: a screen that renders nothing renders FAST")
        XCTAssertEqual(sink.packets[0].outcomeClass, "no_card")
    }

    func testNotMeasuredIsMinusOneNeverZero() {
        let sink = SpySink(); let clock = FakeClock()
        recorder(sink, clock).finish()

        XCTAssertEqual(sink.packets[0].firstCardMs, screenTimingNotMeasured)
        XCTAssertEqual(sink.packets[0].firstCardMs, -1)
        XCTAssertNotEqual(sink.packets[0].firstCardMs, 0, "0 ms and 'did not happen' are different claims")
        XCTAssertEqual(sink.packets[0].foldMs, -1)
    }

    // MARK: - Emission discipline

    func testFinishIsIdempotentUnderRacingTimers() {
        // The quiet timer, the budget timer and an explicit finish all race.
        let sink = SpySink(); let clock = FakeClock()
        let r = recorder(sink, clock)
        r.markFirstCard()
        r.finish(); r.finish(); r.finish()
        XCTAssertEqual(sink.packets.count, 1)
    }

    func testCancelEmitsNothing() {
        // An abandoned screen is reader impatience, not a slow screen. Reporting
        // it would poison the p95 with people who changed their mind.
        let sink = SpySink(); let clock = FakeClock()
        let r = recorder(sink, clock)
        r.markFirstCard()
        r.cancel()
        r.finish()
        XCTAssertTrue(sink.packets.isEmpty)
    }

    func testEmptyAndErrorAreDistinctFromNoCard() {
        // "nothing to show" is a product state; "nothing appeared" is a defect.
        // Collapsing them hides the defect inside a legitimate empty state.
        let clock = FakeClock()

        let emptySink = SpySink()
        recorder(emptySink, clock).markEmpty()
        XCTAssertEqual(emptySink.packets[0].outcomeClass, "empty")

        let errorSink = SpySink()
        recorder(errorSink, clock).markError()
        XCTAssertEqual(errorSink.packets[0].outcomeClass, "error")
    }

    // MARK: - Cold vs warm

    func testFirstScreenAfterLaunchIsColdAndTheRestAreWarm() {
        ScreenTimingSession.resetForTesting()
        XCTAssertEqual(ScreenTimingSession.nextEntry(launchElapsed: 0.3), "cold")
        XCTAssertEqual(ScreenTimingSession.nextEntry(launchElapsed: 1.2), "warm")
        XCTAssertEqual(ScreenTimingSession.nextEntry(launchElapsed: 9.0), "warm")
    }

    func testAScreenLongAfterLaunchIsNotAColdLaunchEvenIfItIsTheFirstMeasured() {
        // A reader who sat on a launch screen for a minute before the first
        // measured screen appeared did not experience a cold launch of THAT
        // screen. Without the window the slowest warm rows would be filed as cold.
        ScreenTimingSession.resetForTesting()
        XCTAssertEqual(ScreenTimingSession.nextEntry(launchElapsed: 45), "warm")
    }

    // MARK: - The packet crosses the privacy boundary intact

    func testEveryPacketKeyIsOnThePrivacyAllowlist() {
        // `AnalyticsPrivacy` fails CLOSED: an unregistered key is dropped
        // silently, so a typo here is a permanently missing column that nothing
        // else would ever go red about. Exactly how `my_stuff_load` shipped
        // broken for its whole first life.
        let packet = ScreenTimingPacket(
            surface: "discover", entry: "cold", shellMs: 128, firstCardMs: 434,
            foldMs: 814, interactiveMs: 814, cardCount: 8, deviceClass: "phone",
            networkClass: "wifi", appBuild: "1.2+340", outcomeClass: "ok"
        )
        for key in packet.parameters.keys {
            XCTAssertTrue(
                AnalyticsPrivacy.allowedParameterKeys.contains(key),
                "\(key) is not on the allowlist and would be dropped before Firebase"
            )
        }
        XCTAssertTrue(AnalyticsPrivacy.allowedEventNames.contains("screen_timing"))
    }

    func testSanitizerKeepsTheWholePacket() {
        let packet = ScreenTimingPacket(
            surface: "events/:id", entry: "warm", shellMs: -1, firstCardMs: 620,
            foldMs: 980, interactiveMs: 980, cardCount: 4, deviceClass: "tablet",
            networkClass: "cell", appBuild: "1.2+340", outcomeClass: "ok"
        )
        let sanitized = AnalyticsPrivacy.sanitize(event: "screen_timing", parameters: packet.parameters)
        let params = try! XCTUnwrap(sanitized)
        XCTAssertEqual(params.count, packet.parameters.count)
        XCTAssertEqual(params["first_card_ms"] as? Int, 620)
        XCTAssertEqual(params["surface"] as? String, "events/:id")
    }

    // MARK: - The bridge from the three shipped native rails

    func testBridgedPacketCarriesTheFirstRenderMomentAsTheFeltNumber() {
        ScreenTimingSession.resetForTesting()
        let p = ScreenTimingPacket.bridged(surface: "discover", firstCardMs: 812, cardCount: 20, entry: "cold")
        XCTAssertEqual(p.firstCardMs, 812)
        XCTAssertEqual(p.cardCount, 20)
        XCTAssertEqual(p.surface, "discover")
        XCTAssertEqual(p.outcomeClass, "ok")
    }

    func testBridgedPacketDoesNotInventTheColumnsItCannotKnow() {
        // 🔴 Copying `firstCardMs` into `foldMs`/`interactiveMs` would put a
        // fabricated number in two columns the <3s / <1s target is judged on, and
        // it would look entirely plausible. -1 keeps the gap visible.
        ScreenTimingSession.resetForTesting()
        let p = ScreenTimingPacket.bridged(surface: "sports", firstCardMs: 640, cardCount: 12, entry: "cold")
        XCTAssertEqual(p.foldMs, screenTimingNotMeasured)
        XCTAssertEqual(p.interactiveMs, screenTimingNotMeasured)
        XCTAssertEqual(p.shellMs, screenTimingNotMeasured)
    }

    func testBridgedPacketWithNoItemsIsEmptyNotOk() {
        ScreenTimingSession.resetForTesting()
        let p = ScreenTimingPacket.bridged(surface: "my_stuff", firstCardMs: 300, cardCount: 0, entry: "warm")
        XCTAssertEqual(p.outcomeClass, "empty")
    }

    func testBridgedPacketKeysMatchTheRecorderPacketExactly() {
        // The bridge and the recorder must produce the SAME columns, or the table
        // has holes that depend on which code path a screen happened to use.
        ScreenTimingSession.resetForTesting()
        let bridged = ScreenTimingPacket.bridged(surface: "discover", firstCardMs: 1, cardCount: 1, entry: "cold")
        let full = ScreenTimingPacket(
            surface: "discover", entry: "cold", shellMs: 1, firstCardMs: 1, foldMs: 1,
            interactiveMs: 1, cardCount: 1, deviceClass: "phone", networkClass: "wifi",
            appBuild: "x", outcomeClass: "ok"
        )
        XCTAssertEqual(Set(bridged.parameters.keys), Set(full.parameters.keys))
    }

    func testWithoutCardPacketKeysMatchTheBridgedPacketExactly() {
        // The failure row and the success row must be the same shape, or the
        // no_card rows land in a table with different columns and cannot be
        // counted beside the rows they are supposed to qualify.
        let blank = ScreenTimingPacket.withoutCard(surface: "discover", entry: "cold", outcome: "no_card")
        let ok = ScreenTimingPacket.bridged(surface: "discover", firstCardMs: 1, cardCount: 1, entry: "cold")
        XCTAssertEqual(Set(blank.parameters.keys), Set(ok.parameters.keys))
        XCTAssertEqual(blank.firstCardMs, screenTimingNotMeasured)
        XCTAssertEqual(blank.foldMs, screenTimingNotMeasured)
        XCTAssertEqual(blank.interactiveMs, screenTimingNotMeasured)
        XCTAssertEqual(blank.cardCount, 0)
    }

    func testDeviceClassIsOneOfTheFiveDeclaredBuckets() {
        XCTAssertTrue(
            ["phone", "tablet", "desktop", "watch", "unknown"].contains(ScreenTimingEnvironment.deviceClass)
        )
    }

    // MARK: - The arm (CERT-782)
    //
    // Both repaired defects are pinned here, plus the two false-FAILURE classes
    // the repair could have introduced. An instrument that invents failures is
    // as useless as one that hides them; it is just less flattering.

    /// A hand-fired deadline, so no test in this file sleeps for ten seconds.
    /// `fire(surface:)` is the ten-second mark arriving.
    final class FakeDeadlines: @unchecked Sendable {
        private let lock = NSLock()
        private var pending: [(seconds: TimeInterval, work: @Sendable () -> Void, cancelled: Bool)] = []

        var scheduler: ScreenTimingSession.DeadlineScheduler {
            { [self] seconds, work in
                lock.lock()
                let index = pending.count
                pending.append((seconds, work, false))
                lock.unlock()
                return { [self] in
                    lock.lock()
                    if index < pending.count { pending[index].cancelled = true }
                    lock.unlock()
                }
            }
        }

        /// The scheduled interval of the most recent arm, so a test can assert the
        /// deadline is the ten seconds the queue promised rather than any timer.
        var lastInterval: TimeInterval? {
            lock.lock(); defer { lock.unlock() }
            return pending.last?.seconds
        }

        /// Fire every live deadline. A cancelled one does nothing, exactly as a
        /// cancelled `Task` would.
        func fireAll() {
            lock.lock()
            let live = pending.filter { !$0.cancelled }.map(\.work)
            lock.unlock()
            for work in live { work() }
        }
    }

    /// 🔴 Reads the one packet an arm is allowed to produce, and FAILS rather
    /// than traps when there is none. `sink.packets[0]` on an empty array is a
    /// `Fatal error: Index out of range`, which kills the whole test target and
    /// takes every sibling's verdict with it — and "no packet at all" is the
    /// exact regression these tests exist to catch, so the crashing path is the
    /// likely one. Measured: it truncates a 771-test run to 2.
    private func onlyPacket(
        _ sink: SpySink,
        file: StaticString = #filePath,
        line: UInt = #line
    ) -> ScreenTimingPacket? {
        XCTAssertEqual(sink.packets.count, 1, "expected exactly one packet", file: file, line: line)
        guard let packet = sink.packets.first else {
            XCTFail("no packet was emitted", file: file, line: line)
            return nil
        }
        return packet
    }

    private func armHarness(_ clock: FakeClock) -> (SpySink, FakeDeadlines) {
        let sink = SpySink()
        let deadlines = FakeDeadlines()
        ScreenTimingSession.installTestHarness(
            sink: sink,
            now: clock.now,
            schedule: deadlines.scheduler
        )
        return (sink, deadlines)
    }

    nonisolated override func tearDown() {
        ScreenTimingSession.resetForTesting()
        super.tearDown()
    }

    // --- Defect 1: the label was taken at the wrong moment ---

    func testASlowColdLaunchStaysColdEvenWhenItsFirstCardArrivesAfterTheColdWindow() {
        // 🔴 THE CERT-782 DEFECT, pinned. The label used to be claimed when the
        // first card rendered, so a 21-second cold launch fell outside the 20 s
        // cold window and was filed as `warm`. The slowest cold rows deleted
        // themselves from the cold cohort — in the flattering direction, with
        // nothing going red.
        let clock = FakeClock()
        let (sink, _) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        clock.seconds = 21
        ScreenTimingSession.reportBridged(surface: "discover", firstCardMs: 21_000, cardCount: 14)

        guard let packet = onlyPacket(sink) else { return }
        XCTAssertEqual(packet.entry, "cold", "the reader launched the app; a slow first card does not make it a warm navigation")
        XCTAssertEqual(packet.firstCardMs, 21_000)
    }

    func testTheColdWindowStillAppliesButAtArmTime() {
        // The window is not abandoned, it is moved to the moment it means
        // something. A screen ENTERED 45 s after launch is a warm navigation no
        // matter how fast it then is.
        let clock = FakeClock()
        let (sink, _) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 45)
        ScreenTimingSession.reportBridged(surface: "discover", firstCardMs: 90, cardCount: 9)

        XCTAssertEqual(onlyPacket(sink)?.entry, "warm")
    }

    func testOnlyTheFirstArmedScreenIsCold() {
        _ = armHarness(FakeClock())

        XCTAssertEqual(ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2), "cold")
        XCTAssertEqual(ScreenTimingSession.armScreen(surface: "sports", launchElapsed: 0.9), "warm")
    }

    // --- Defect 2: a screen that never rendered reported nothing ---

    func testABlankTabEmitsAMeasuredFailureInsteadOfDisappearing() {
        // 🔴 THE OTHER CERT-782 DEFECT. The bridge only fires from a real first
        // render, so the three cold loads in the 2026-09-02 battery that rendered
        // NOTHING could not have appeared in this table at all — the worst rows
        // were structurally invisible.
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        XCTAssertEqual(deadlines.lastInterval, 10, "the promised bar is ten seconds, not whatever timer happened to be handy")

        clock.seconds = 10
        deadlines.fireAll()

        guard let packet = onlyPacket(sink) else {
            return XCTFail("a screen that showed nothing must still be a row")
        }
        XCTAssertEqual(packet.outcomeClass, "no_card")
        XCTAssertEqual(packet.surface, "discover")
        XCTAssertEqual(packet.firstCardMs, -1, "0 ms would report the worst load on the board as the fastest")
    }

    func testTheBlankRowIsLabelledColdWhenTheAppHadJustLaunched() {
        // The row is only useful if it lands in the right cohort: a blank COLD
        // launch is the failure Alex cares about, and labelling it warm would
        // bury it among tab switches.
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "sports", launchElapsed: 0.4)
        clock.seconds = 10
        deadlines.fireAll()

        XCTAssertEqual(onlyPacket(sink)?.entry, "cold")
    }

    func testAReaderWhoWaitedAndSawNothingIsReportedOnLeaving() {
        let clock = FakeClock()
        let (sink, _) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        clock.seconds = 6
        ScreenTimingSession.disarmScreen(surface: "discover")

        XCTAssertEqual(onlyPacket(sink)?.outcomeClass, "no_card")
    }

    func testATabFlickIsNotAFailure() {
        // A reader who touched a tab for under three seconds did not give the
        // screen a chance. Counting that would manufacture failures faster than
        // the real ones arrive and drown them.
        let clock = FakeClock()
        let (sink, _) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        clock.seconds = 1.2
        ScreenTimingSession.disarmScreen(surface: "discover")

        XCTAssertTrue(sink.packets.isEmpty)
    }

    // --- The false-failure classes the repair could have introduced ---

    func testALoadThatArrivesInTimeStandsTheDeadlineDown() {
        // 🔴 Without the cancel, every healthy load would ALSO emit a `no_card`
        // row ten seconds later and the table would read as ~50% broken.
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        clock.seconds = 0.4
        ScreenTimingSession.reportBridged(surface: "discover", firstCardMs: 400, cardCount: 18)
        clock.seconds = 10
        deadlines.fireAll()

        XCTAssertEqual(onlyPacket(sink)?.outcomeClass, "ok")
    }

    func testALegitimatelyEmptyScreenIsNotAFailure() {
        // My Stuff with no upcoming games renders no card on purpose. Collapsing
        // that into `no_card` would hide every real failure inside a product
        // state — the exact confusion the outcome vocabulary exists to prevent.
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "my_stuff", launchElapsed: 0.3)
        clock.seconds = 0.8
        ScreenTimingSession.reportOutcome(surface: "my_stuff", outcome: "empty")
        clock.seconds = 10
        deadlines.fireAll()

        XCTAssertEqual(onlyPacket(sink)?.outcomeClass, "empty")
    }

    func testAFailedLoadIsAnErrorNotASilentNoCard() {
        let clock = FakeClock()
        let (sink, _) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "sports", launchElapsed: 0.3)
        ScreenTimingSession.reportOutcome(surface: "sports", outcome: "error")

        XCTAssertEqual(onlyPacket(sink)?.outcomeClass, "error")
    }

    func testAnUnarmedSurfaceIsNeverReportedAsBlank() {
        // Arming a tab that already has its cards on screen would report a
        // working screen as broken, because a tab switch back to a populated tab
        // stamps no new render generation to settle the arm with. The call sites
        // guard on `items.isEmpty`; this pins that an unarmed surface has no
        // deadline at all rather than relying on the guard alone.
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        clock.seconds = 10
        deadlines.fireAll()
        ScreenTimingSession.disarmScreen(surface: "discover")

        XCTAssertTrue(sink.packets.isEmpty)
    }

    // --- One arm, one row ---

    func testALateArrivalAfterTheFailureRowIsNotASecondRow() {
        // The screen entry has already been counted as a failure. A second row
        // for the same entry would inflate the denominator of every rate computed
        // off this table. The uncensored number is not lost: the bespoke
        // `*_first_render` rails still carry it beside this one.
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        clock.seconds = 10
        deadlines.fireAll()
        clock.seconds = 31
        ScreenTimingSession.reportBridged(surface: "discover", firstCardMs: 30_900, cardCount: 12)

        XCTAssertEqual(onlyPacket(sink)?.outcomeClass, "no_card")
    }

    func testARefreshAfterASuccessfulArrivalIsAWarmRow() {
        // A pull-to-refresh is a real, separate measurement — and by definition
        // not a launch, whatever the arm said.
        let clock = FakeClock()
        let (sink, _) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        ScreenTimingSession.reportBridged(surface: "discover", firstCardMs: 420, cardCount: 18)
        clock.seconds = 60
        ScreenTimingSession.reportBridged(surface: "discover", firstCardMs: 260, cardCount: 20)

        XCTAssertEqual(sink.packets.count, 2)
        XCTAssertEqual(sink.packets.map(\.entry), ["cold", "warm"])
    }

    func testReArmingASurfaceCannotLeaveTwoDeadlinesRunning() {
        let clock = FakeClock()
        let (sink, deadlines) = armHarness(clock)

        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 0.2)
        ScreenTimingSession.armScreen(surface: "discover", launchElapsed: 2.0)
        clock.seconds = 10
        deadlines.fireAll()

        XCTAssertEqual(sink.packets.count, 1, "two arms of one surface must not both emit")
    }

    // --- The surface slugs the arm and the report have to agree on ---

    func testTheArmedSurfacesAreExactlyTheOnesTheBridgeReports() {
        // The arm lives in a view file and the report lives in AnalyticsService.
        // A mismatch would not fail to build and would produce a permanent stream
        // of `no_card` rows for tabs that work.
        XCTAssertEqual(
            Set(ScreenTimingSurface.bridged),
            ["discover", "sports", "my_stuff"]
        )
    }
}
