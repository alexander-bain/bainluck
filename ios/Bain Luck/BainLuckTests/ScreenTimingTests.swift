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
        var now: () -> Date { { Date(timeIntervalSince1970: self.seconds) } }
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
        let p = ScreenTimingPacket.bridged(surface: "discover", firstCardMs: 812, cardCount: 20)
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
        let p = ScreenTimingPacket.bridged(surface: "sports", firstCardMs: 640, cardCount: 12)
        XCTAssertEqual(p.foldMs, screenTimingNotMeasured)
        XCTAssertEqual(p.interactiveMs, screenTimingNotMeasured)
        XCTAssertEqual(p.shellMs, screenTimingNotMeasured)
    }

    func testBridgedPacketWithNoItemsIsEmptyNotOk() {
        ScreenTimingSession.resetForTesting()
        let p = ScreenTimingPacket.bridged(surface: "my_stuff", firstCardMs: 300, cardCount: 0)
        XCTAssertEqual(p.outcomeClass, "empty")
    }

    func testBridgedPacketKeysMatchTheRecorderPacketExactly() {
        // The bridge and the recorder must produce the SAME columns, or the table
        // has holes that depend on which code path a screen happened to use.
        ScreenTimingSession.resetForTesting()
        let bridged = ScreenTimingPacket.bridged(surface: "discover", firstCardMs: 1, cardCount: 1)
        let full = ScreenTimingPacket(
            surface: "discover", entry: "cold", shellMs: 1, firstCardMs: 1, foldMs: 1,
            interactiveMs: 1, cardCount: 1, deviceClass: "phone", networkClass: "wifi",
            appBuild: "x", outcomeClass: "ok"
        )
        XCTAssertEqual(Set(bridged.parameters.keys), Set(full.parameters.keys))
    }

    func testDeviceClassIsOneOfTheFiveDeclaredBuckets() {
        XCTAssertTrue(
            ["phone", "tablet", "desktop", "watch", "unknown"].contains(ScreenTimingEnvironment.deviceClass)
        )
    }
}
