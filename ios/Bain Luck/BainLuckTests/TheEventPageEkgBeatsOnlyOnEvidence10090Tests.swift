import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #10090 (Alex 67, "can you add the ekg to the app too") — **the iPhone's
/// heartbeat beats only when the markets report in, shows only on a live game,
/// keeps still under Reduce Motion, and a tap opens the page's own details.**
///
/// The rule is the web's (`frontend/lib/event/ekgHeartbeat.ts`): a beat is
/// decision J's `confirmed_at` or the printed number's clock ADVANCING, to a
/// recent time, while the stream delivers. A re-render repeats its inputs and a
/// reconnect moves neither clock, so neither can beat.
@MainActor
final class TheEventPageEkgBeatsOnlyOnEvidence10090Tests: XCTestCase {
    private static let t0 = Date(timeIntervalSince1970: 1_793_000_000)
    private static let event = 10_090

    private func at(_ s: TimeInterval) -> Date { Self.t0.addingTimeInterval(s) }

    private func obs(confirmed: TimeInterval? = nil, price: TimeInterval? = nil, open: Bool = true,
                     event: Int = 10_090) -> EkgTracker.Observation {
        EkgTracker.Observation(eventId: event, transportOpen: open,
                               confirmedAt: confirmed.map(at), priceObservedAt: price.map(at))
    }

    /// The page opened holding confirmed 0 and price 0.
    private func opened() -> EkgTracker {
        EkgTracker.empty.stepped(obs(confirmed: 0, price: 0), now: at(1))
    }

    // MARK: - The tracker

    func testOpeningThePageIsABaselineNotABeat() {
        let t = opened()
        XCTAssertEqual(t.beats, 0)
        XCTAssertNil(t.lastSignalAt)
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(1)).mode, .flat)
    }

    func testAConfirmedAtAdvanceBeats() {
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6.2))
        XCTAssertEqual(t.beats, 1)
        XCTAssertEqual(t.lastSignalAt, at(6.2))
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(7)).mode, .beating)
    }

    /// Web parity: the printed number's clock is the other report. Without it
    /// the line would go flat while prices land, since J is withheld whenever
    /// a newer price is owed.
    func testAnAdvanceOfThePrintedNumbersClockBeats() {
        let t = opened().stepped(obs(confirmed: nil, price: 5), now: at(5.5))
        XCTAssertEqual(t.beats, 1)
    }

    // MARK: - Every venue report pulses it (Alex 2026-11-01)

    private func activity(_ a: TimeInterval?, open: Bool = true) -> EkgTracker.Observation {
        EkgTracker.Observation(eventId: Self.event, transportOpen: open, confirmedAt: at(0),
                               priceObservedAt: at(0), activityAt: a.map(at))
    }

    func testAnActivityAdvanceBeatsWhileThePriceAndAgreementHoldStill() {
        var t = EkgTracker.empty.stepped(activity(0), now: at(1))
        XCTAssertEqual(t.beats, 0, "the activity it opens with is a baseline")
        t = t.stepped(activity(3), now: at(3.2))
        XCTAssertEqual(t.beats, 1)
        t = t.stepped(activity(5), now: at(5.2))
        XCTAssertEqual(t.beats, 2)
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(6)).mode, .beating)
    }

    func testTheSameActivityAgainIsNoBeatAndBurstsCoalesce() {
        var t = EkgTracker.empty.stepped(activity(0), now: at(1)).stepped(activity(3), now: at(3.2))
        t = t.stepped(activity(3), now: at(4))
        XCTAssertEqual(t.beats, 1)
        t = t.stepped(activity(3.5), now: at(3.6))
        XCTAssertEqual(t.beats, 1, "inside the beat gap")
        XCTAssertEqual(t.lastSignalAt, at(3.6))
    }

    func testActivityHeardWhileTheStreamIsDownIsRecordedSilently() {
        let t = EkgTracker.empty.stepped(activity(0), now: at(1)).stepped(activity(3, open: false), now: at(3.2))
        XCTAssertEqual(t.beats, 0)
        XCTAssertEqual(t.activityAt, at(3))
    }

    func testTheHeartbeatsActivityAtIsReadAndNothingElse() {
        XCTAssertEqual(LiveStreamController.heartbeatActivityAt(
            #"{"t":"x","confirmed_at":null,"activity_at":"2026-11-01T21:25:02.583+00:00"}"#),
            "2026-11-01T21:25:02.583+00:00".asDate)
        XCTAssertNil(LiveStreamController.heartbeatActivityAt(#"{"confirmed_at":"2026-11-01T21:25:02Z"}"#))
        XCTAssertNil(LiveStreamController.heartbeatActivityAt(#"{"activity_at":"soon"}"#))
        XCTAssertNil(LiveStreamController.heartbeatActivityAt("not json"))
    }

    // MARK: - The EKG's update list (Alex 2026-11-01)

    func testTheHeartbeatsUpdatesAreReadSkippingRowsThatAreNotAVenueAndATime() {
        let got = LiveStreamController.heartbeatUpdates(
            #"{"t":"x","updates":[["kalshi","2026-11-01T22:57:03.420+00:00"],["polymarket","soon"],["","2026-11-01T22:57:03Z"],["polymarket","2026-11-01T22:57:03.610+00:00"]]}"#)
        XCTAssertEqual(got.map(\.source), ["kalshi", "polymarket"])
        XCTAssertEqual(got.first?.at, "2026-11-01T22:57:03.420+00:00".asDate)
        XCTAssertEqual(LiveStreamController.heartbeatUpdates(#"{"t":"x"}"#), [])
        XCTAssertEqual(LiveStreamController.heartbeatUpdates("junk"), [])
    }

    // Alex 2026-11-01: "just shows the source and timestamp, but not a
    // probability. that was kinda the whole point. it's also not a scrolling
    // stream. it just arrives in batches".
    func testEachUpdateReadsItsProbabilityBesideTheTwoItemRows() {
        let got = LiveStreamController.heartbeatUpdates(
            #"{"updates":[["kalshi","2026-11-01T22:57:03.420+00:00"],["polymarket","2026-11-01T22:57:03.610+00:00"]],"update_p":[0.065,1.7]}"#)
        XCTAssertEqual(got.map(\.p), [0.065, nil], "a value outside 0-1 is unknown")
        let misaligned = LiveStreamController.heartbeatUpdates(
            #"{"updates":[["kalshi","2026-11-01T22:57:03.420+00:00"]],"update_p":[0.4,0.5]}"#)
        XCTAssertEqual(misaligned.map(\.p), [nil])
        let nulls = LiveStreamController.heartbeatUpdates(
            #"{"updates":[["kalshi","2026-11-01T22:57:03.420+00:00"]],"update_p":[null]}"#)
        XCTAssertEqual(nulls.count, 1)
        XCTAssertNil(nulls.first?.p)
        XCTAssertEqual(LiveUpdateStream.probabilityText(0.8125), "81.3%")
        XCTAssertEqual(LiveUpdateStream.probabilityText(0.065), "6.5%")
        XCTAssertEqual(LiveUpdateStream.probabilityText(nil), "—")
    }

    func testABatchStreamsByItsOwnReceiptGapsAndTheListNeverShrinks() {
        var list = LiveUpdateStream()
        list.add((0..<120).map { LiveUpdateStream.Update(source: "kalshi", at: at(Double($0) / 100)) })
        var screen = LiveUpdateScreen(opening: list.updates)
        XCTAssertEqual(screen.rows.count, LiveUpdateScreen.capacity, "what is listed shows at once")
        list.add([LiveUpdateStream.Update(source: "kalshi", at: at(5), p: 0.4),
                  LiveUpdateStream.Update(source: "polymarket", at: at(5.3), p: 0.41)])
        screen.advance(list.updates, now: 100)
        XCTAssertEqual(screen.rows.first?.at, at(5), "the batch's first row is due on arrival")
        XCTAssertEqual(screen.rows.count, LiveUpdateScreen.capacity)
        screen.advance(list.updates, now: 100.2)
        XCTAssertEqual(screen.rows.first?.at, at(5), "the second waits for its own 0.3 s gap")
        screen.advance(list.updates, now: 100.3)
        XCTAssertEqual(screen.rows.first?.source, "polymarket")
        XCTAssertEqual(screen.rows.first?.p, 0.41)
        XCTAssertFalse(screen.waiting)
    }

    func testANewBatchFirstShowsWhatTheLastHasNot() {
        var list = LiveUpdateStream()
        list.add([LiveUpdateStream.Update(source: "kalshi", at: at(0)),
                  LiveUpdateStream.Update(source: "kalshi", at: at(9))])
        var screen = LiveUpdateScreen()
        screen.advance(list.updates, now: 0)
        XCTAssertEqual(screen.queue.last?.at, LiveUpdateScreen.spread, "a long batch is squeezed into one spread")
        list.add([LiveUpdateStream.Update(source: "kalshi", at: at(10))])
        screen.advance(list.updates, now: 0.01)
        XCTAssertEqual(screen.rows.map(\.at), [at(10), at(9), at(0)])
    }

    func testTheListIsNewestFirstKeepsSameTimeDuplicatesDropsARepeatedBatchAndIsBounded() {
        var list = LiveUpdateStream()
        let a = LiveUpdateStream.Update(source: "kalshi", at: at(1))
        let b = LiveUpdateStream.Update(source: "polymarket", at: at(2))
        list.add([a, a, b])                   // one book priced two legs at once
        XCTAssertEqual(list.updates.map(\.source), ["polymarket", "kalshi", "kalshi"])
        list.add([a, b])                      // a reconnect repeats the last heartbeat
        XCTAssertEqual(list.updates.count, 3)
        XCTAssertEqual(Set(list.updates.map(\.id)).count, 3, "every row has its own identity")
        list.add((0..<400).map { LiveUpdateStream.Update(source: "kalshi", at: at(10 + Double($0))) })
        XCTAssertEqual(list.updates.count, LiveUpdateStream.capacity)
        XCTAssertEqual(list.updates.first?.at, at(409))
        list.clear()
        XCTAssertTrue(list.updates.isEmpty)
        list.add([a])
        XCTAssertEqual(list.updates.count, 1, "a cleared list takes the venue's rows again")
    }

    func testEachRowNamesItsVenueAndItsTimeToTheHundredth() {
        let utc = TimeZone(identifier: "UTC")!
        let time = Date(timeIntervalSince1970: 1_793_573_823.427)   // 2026-11-01 22:57:03.427Z
        XCTAssertEqual(LiveUpdateStream.timeText(time, timeZone: utc), "10:57:03.42 PM")
        XCTAssertEqual(LiveUpdateStream.timeText(Date(timeIntervalSince1970: 1_793_491_200.055), timeZone: utc),
                       "12:00:00.05 AM")
        XCTAssertEqual(LiveUpdateStream.venueName("kalshi"), "Kalshi")
        XCTAssertEqual(LiveUpdateStream.venueName("polymarket"), "Polymarket")
        XCTAssertEqual(LiveUpdateStream.venueName("new_venue"), "Another venue", "#4135: never a title-cased key")
    }

    func testARenderThatRepeatsItsInputsNeverBeatsAgain() {
        let once = opened().stepped(obs(confirmed: 6, price: 0), now: at(6.2))
        let again = once.stepped(obs(confirmed: 6, price: 0), now: at(9))
        XCTAssertEqual(again, once, "a repeated observation is idempotent")
    }

    func testAReconnectWithTheSameClocksDoesNotBeat() {
        let t = opened()
            .stepped(obs(confirmed: 0, price: 0, open: false), now: at(3))
            .stepped(obs(confirmed: 0, price: 0, open: true), now: at(4))
        XCTAssertEqual(t.beats, 0)
        XCTAssertNil(t.lastSignalAt)
    }

    /// The catch-up a reconnect delivers was recorded while the stream was
    /// down; reopening repeats it, so it never beats on its own.
    func testAnAdvanceWhileTheStreamIsDownIsRecordedSilently() {
        let down = opened().stepped(obs(confirmed: 8, price: 0, open: false), now: at(8.5))
        XCTAssertEqual(down.beats, 0)
        XCTAssertEqual(down.confirmedAt, at(8))
        let reopened = down.stepped(obs(confirmed: 8, price: 0, open: true), now: at(9))
        XCTAssertEqual(reopened.beats, 0)
    }

    /// The first confirmation after a connect, on a market that went quiet
    /// minutes ago, is minutes old: newer than nothing, but not a report now.
    func testAnAdvanceToAnOldClockIsNotABeat() {
        let t = EkgTracker.empty.stepped(obs(confirmed: nil, price: nil), now: at(0))
            .stepped(obs(confirmed: 0, price: nil), now: at(EkgTracker.flatAfter))
        XCTAssertEqual(t.beats, 0)
        XCTAssertEqual(t.confirmedAt, at(0))
    }

    func testAnOlderOrMissingConfirmationNeitherBeatsNorErases() {
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6.2))
        let older = t.stepped(obs(confirmed: 3, price: 0), now: at(7))
        XCTAssertEqual(older, t)
        let missing = t.stepped(obs(confirmed: nil, price: 0), now: at(7))
        XCTAssertEqual(missing.confirmedAt, at(6))
        XCTAssertEqual(missing.beats, 1)
    }

    func testABurstDrawsOneBeatButKeepsTheLineAlive() {
        let first = opened().stepped(obs(confirmed: 6, price: 0), now: at(6))
        let coalesced = first.stepped(obs(confirmed: 7, price: 0), now: at(7))
        XCTAssertEqual(coalesced.beats, 1, "under 1.5 s: coalesced into the drawn beat")
        XCTAssertEqual(coalesced.lastSignalAt, at(7))
        let next = coalesced.stepped(obs(confirmed: 7.5, price: 0), now: at(7.5))
        XCTAssertEqual(next.beats, 2, "1.5 s after the drawn beat: a new one")
    }

    func testAnotherEventStartsFromItsOwnBaseline() {
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6))
            .stepped(obs(confirmed: 9, price: 9, event: 11_000), now: at(9))
        XCTAssertEqual(t.eventId, 11_000)
        XCTAssertEqual(t.beats, 0)
        XCTAssertNil(t.lastSignalAt)
    }

    // MARK: - Presentation

    func testItGoesFlatFifteenSecondsAfterTheLastReport() {
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6))
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(6 + 14.9)).mode, .beating)
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(6 + 15)).mode, .flat)
    }

    func testOnlyADeliveringStreamBeatsAndInterruptionSaysSo() {
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6))
        XCTAssertEqual(EkgHeartbeat.present(t, status: .awaitingUpdate, now: at(7)).mode, .beating)
        XCTAssertEqual(EkgHeartbeat.present(t, status: .autoRefresh, now: at(7)).mode, .flat)
        let cut = EkgHeartbeat.present(t, status: .interrupted, now: at(7))
        XCTAssertEqual(cut.mode, .interrupted)
        XCTAssertEqual(cut.label, "Markets reporting: updates interrupted")
        XCTAssertTrue(EkgHeartbeat.transportOpen(.live))
        XCTAssertFalse(EkgHeartbeat.transportOpen(.autoRefresh))
        XCTAssertFalse(EkgHeartbeat.transportOpen(.interrupted))
    }

    func testTheLabelSaysHowLongAgo() {
        XCTAssertEqual(EkgHeartbeat.present(opened(), status: .live, now: at(2)).label,
                       "Markets reporting: no update yet")
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6))
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(7.9)).label,
                       "Markets reporting: last update 1 second ago")
        XCTAssertEqual(EkgHeartbeat.present(t, status: .live, now: at(10)).label,
                       "Markets reporting: last update 4 seconds ago")
    }

    // MARK: - The visibility gate

    func testItShowsOnlyOnALiveGame() {
        func visible(_ status: String?, finished: Bool = false, settled: Bool = false, opening: Bool = false) -> Bool {
            EkgHeartbeat.isVisible(eventStatus: status, finished: finished,
                                   venueSettledVerdict: settled, isOpeningLine: opening)
        }
        XCTAssertTrue(visible("live"))
        XCTAssertFalse(visible("scheduled"), "not before the off")
        XCTAssertFalse(visible("suspended"), "a stoppage is a terminal connection label on the web")
        XCTAssertFalse(visible("final"))
        XCTAssertFalse(visible(nil))
        XCTAssertFalse(visible("live", finished: true), "the stream said it is over")
        XCTAssertFalse(visible("live", settled: true), "the venue's verdict, not a live quote")
        XCTAssertFalse(visible("live", opening: true), "an opening line has no stream to report")
    }

    // MARK: - Reduce Motion

    func testReduceMotionDrawsAStillMarkAndTheAgeInWords() {
        let t = opened().stepped(obs(confirmed: 6, price: 0), now: at(6))
        let p = EkgHeartbeat.present(t, status: .live, now: at(10))
        XCTAssertEqual(EkgHeartbeat.drawing(p, reduceMotion: true), .still(.beating, text: "Updated 4s ago"))
        XCTAssertEqual(EkgHeartbeat.drawing(p, reduceMotion: false), .trace(.beating, beats: 1))
        let never = EkgHeartbeat.present(opened(), status: .live, now: at(2))
        XCTAssertEqual(EkgHeartbeat.drawing(never, reduceMotion: true), .still(.flat, text: nil))
    }

    // MARK: - On the page: on by default, and a tap opens the details

    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let status: String
        init(status: String) { self.status = status }
        func fetchEvent(id: Int) async throws -> EventDetail {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            var event = try decoder.decode(EventDetail.self, from: Data(#"{"id":\#(id),"home_team":"Dallas Cowboys","away_team":"Baltimore Ravens","sport":"americanfootball_nfl","status":"\#(status)","home_score":24,"away_score":27,"current_odds":{"home_probability":0.45,"away_probability":0.55,"home_rendered_percent":45,"away_rendered_percent":55},"hero_probability":0.45,"hero_probability_source":"blend","blend_fold_revision":{"\#(id)":20},"win_probability_sources":{"kalshi":{"value":0.45,"updated_at":"2026-09-27T23:44:48Z"}}}"#.utf8))
            event.heroProbabilityObservedAt = ISO8601DateFormatter().string(from: Date())
            return event
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class PageHandle: LiveStreamHandle, @unchecked Sendable {
        var callbacks: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        var isConnecting = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            callbacks[event, default: []].append(handler)
        }
        func close() {}
        func open() { for handler in callbacks["open"] ?? [] { handler("") } }
    }

    private func model(status: String) async -> EventDetailViewModel {
        let handle = PageHandle()
        let vm = EventDetailViewModel(eventId: Self.event, client: PageClient(status: status),
                                      makeStreamHandle: { _ in handle })
        await vm.load(); handle.open()
        return vm
    }

    /// A popover needs a window on a foreground-active scene (#11703's mount).
    private func mount<V: View>(_ view: V) async throws -> (UIViewController, UIWindow, UIWindow?) {
        let deadline = Date().addingTimeInterval(10)
        func activeScene() -> UIWindowScene? {
            UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive }
        }
        while activeScene() == nil && Date() < deadline { try await Task.sleep(nanoseconds: 50_000_000) }
        let scene = try XCTUnwrap(activeScene(), "a popover needs a foreground-active window scene")
        let previous = scene.windows.first { $0.isKeyWindow }
        let host = hostForMeasurement(NavigationStack { view }.environmentObject(PinManager())
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light))
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(windowScene: scene)
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        return (host, window, previous)
    }

    @discardableResult
    private func settle(_ host: UIViewController, timeout: TimeInterval,
                        until condition: () -> Bool = { false }) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            if condition() { return true }
            try? await Task.sleep(nanoseconds: 20_000_000)
        } while Date() < deadline
        return condition()
    }

    /// An element found the way VoiceOver finds it, by its label's prefix.
    private func element(_ prefix: String, in root: NSObject) -> NSObject? {
        if let label = root.accessibilityLabel, label.hasPrefix(prefix) { return root }
        var children: [NSObject] = []
        if let elements = root.accessibilityElements as? [NSObject] { children += elements }
        let count = root.accessibilityElementCount()
        if count != NSNotFound, count > 0 {
            children += (0..<count).compactMap { root.accessibilityElement(at: $0) as? NSObject }
        }
        if let view = root as? UIView { children += view.subviews }
        for child in children {
            if let found = element(prefix, in: child) { return found }
        }
        return nil
    }

    /// See #11703: automation mode builds the accessibility tree a test
    /// process otherwise never gets.
    override class func setUp() { super.setUp(); setAutomation(true) }
    override class func tearDown() { setAutomation(false); super.tearDown() }
    private static func setAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let symbol = dlsym(lib, "_AXSSetAutomationEnabled") else { return }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(symbol, to: SetEnabled.self)(enabled ? 1 : 0)
    }

    func testALiveGameShowsTheHeartbeatByDefaultAndATapOpensTheDetails() async throws {
        let vm = await model(status: "live")
        defer { vm.stopRefresh() }
        let (host, window, previous) = try await mount(EventDetailView(eventId: Self.event, viewModel: vm))
        defer { host.dismiss(animated: false); window.isHidden = true; previous?.makeKey() }

        var ekg: NSObject?
        await settle(host, timeout: 5) { ekg = self.element("Markets reporting", in: host.view); return ekg != nil }
        let control = try XCTUnwrap(ekg, "a live game shows the heartbeat with no setting turned on")
        // Alex 69 — beside the EKG the (i) is gone: no VoiceOver stop of its
        // own, and the heartbeat says what its tap opens. The tap below then
        // opens the popover from the collapsed control's anchor.
        XCTAssertNil(element("Probability confidence and update details", in: host.view),
                     "the (i) beside the EKG is still a VoiceOver stop")
        // Alex 2026-11-01: the tap opens the scrolling list of venue updates.
        XCTAssertEqual(control.accessibilityHint, "Shows the venue updates feeding this number")
        XCTAssertEqual(host.presentedViewController, nil)
        XCTAssertTrue(control.accessibilityActivate(), "the heartbeat takes a tap")
        let opened = await settle(host, timeout: 3) { host.presentedViewController != nil }
        XCTAssertTrue(opened, "a tap on the heartbeat opens its update list")
    }

    func testAFinishedGameShowsNoHeartbeat() async throws {
        let vm = await model(status: "final")
        defer { vm.stopRefresh() }
        let (host, window, previous) = try await mount(EventDetailView(eventId: Self.event, viewModel: vm))
        defer { window.isHidden = true; previous?.makeKey() }
        // Control: the page itself rendered (its share control is always there).
        let rendered = await settle(host, timeout: 5) { self.element("Share", in: host.view) != nil
            || self.element("Dallas", in: host.view) != nil || self.element("Baltimore", in: host.view) != nil }
        XCTAssertTrue(rendered, "control: the finished page rendered")
        XCTAssertNil(element("Markets reporting", in: host.view))
    }
}
