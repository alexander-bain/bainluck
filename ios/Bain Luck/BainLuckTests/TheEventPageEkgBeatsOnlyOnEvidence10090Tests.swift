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
        XCTAssertEqual(host.presentedViewController, nil)
        XCTAssertTrue(control.accessibilityActivate(), "the heartbeat takes a tap")
        let opened = await settle(host, timeout: 3) { host.presentedViewController != nil }
        XCTAssertTrue(opened, "a tap on the heartbeat opens the page's details popover")
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
