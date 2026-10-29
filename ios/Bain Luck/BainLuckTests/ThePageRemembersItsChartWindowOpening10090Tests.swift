import XCTest
import SwiftUI
import UIKit
@testable import Bain_Luck

/// #10090 follow-up B — the event page works out its shared chart window's
/// opening once per payload, not on every page body.
///
/// Both chart mounts take `sharedChartDomain` (and, for a mounted journey,
/// `legacyChartDataDomain`) on every body of the page. Each one ran
/// `SharedChartWindow.domain`, whose opening scans the whole payload: on the
/// week-shaped live NFL payload `ObservedPlayStart.cut` is ~25 ms a call under
/// Since Start (~4 ms under All, `earliestReading`), so a score, a price or a
/// markets reread paid ~50 ms before either chart's body ran. The opening is now
/// remembered in the view model (`SharedChartWindow.OpeningMemo`), keyed on what
/// it reads; the end — status, clock, last readings — is worked out every call.
///
/// FIXTURE: #6158's White Sox @ Astros specimen (a late start, so Since Start,
/// All and a sport-less read all open at different instants), plus the same
/// payload stripped of every period reading (a new payload that opens elsewhere).
@MainActor
final class ThePageRemembersItsChartWindowOpening10090Tests: XCTestCase {

    private static var testsDir: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent() }
    private static let commence = "2026-09-30T21:00:00+00:00"
    private static let now = "2026-09-30T22:13:00Z".asDate!

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func specimenObject() throws -> [String: Any] {
        let data = try Data(contentsOf: testsDir.appendingPathComponent(
            "Fixtures/history-15321836-late-start.20260930T2213Z.json"))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private static func history(_ object: [String: Any]) throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    static func specimen() throws -> EventHistoryResponse { try history(specimenObject()) }

    /// The same payload with no period reading anywhere: Since Start keeps the
    /// scheduled start instead of the observed first pitch.
    static func noPeriods() throws -> EventHistoryResponse {
        var object = try specimenObject()
        object["espn_history"] = nil
        object["win_prob_history"] = nil
        object["period_markers"] = nil
        return try history(object)
    }

    static func event(commence: String? = commence, sport: String? = "baseball_mlb",
                      status: String = "live") throws -> EventDetail {
        var object: [String: Any] = ["id": 15321836, "home_team": "Houston Astros",
                                     "away_team": "Chicago White Sox", "status": status]
        if let commence { object["commence_time"] = commence }
        if let sport { object["sport"] = sport }
        return try decoder().decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        let response: EventDetail
        var history: EventHistoryResponse
        init(_ response: EventDetail, history: EventHistoryResponse) { self.response = response; self.history = history }
        func fetchEvent(id: Int) async throws -> EventDetail { response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private struct NoStream: Error {}

    private func model(_ client: Client) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 15321836, client: client,
                             makeStreamHandle: { _ in throw NoStream() },
                             sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
    }

    private func key(_ event: EventDetail) -> PublicationTaskKey4974 {
        PublicationTaskKey4974(pageEventId: 15321836, vmEventId: 15321836, event: event,
                               caller: PublicationCaller4974())
    }

    /// Every input the page varies, one at a time, so each step differs from
    /// the one before in a single input.
    private func events() throws -> [EventDetail] {
        [try Self.event(),
         try Self.event(status: "completed"),
         try Self.event(status: "scheduled"),
         try Self.event(sport: nil),
         try Self.event(sport: "americanfootball_nfl"),
         try Self.event(commence: "2026-09-30T21:12:00+00:00"),
         try Self.event(commence: nil),
         try Self.event()]
    }

    private static let clocks = [now, now.addingTimeInterval(1), now.addingTimeInterval(45)]

    // MARK: - Equivalence: the remembered window is the plain window

    /// At every payload the page can hold (none yet, the specimen, a new one),
    /// for every event input, range and clock, the page's window with the memo
    /// equals the plain builder's — the axis AND the legacy ink window.
    func testTheRememberedWindowIsThePlainWindowAcrossEveryInput() async throws {
        let client = Client(try Self.event(status: "completed"), history: try Self.specimen())
        let vm = model(client)
        defer { vm.stopRefresh() }
        let journeyless: PublicationJourney4974.Journey? = nil

        func compare(_ label: String) throws {
            for event in try events() {
                for range in [OddsTimeRange.sinceStart, .all, .sinceStart] {
                    for clock in Self.clocks {
                        let plain = EventDetailView.pageLegacyChartDomain(
                            event: event, history: vm.history, range: range, now: clock)
                        XCTAssertEqual(EventDetailView.pageLegacyChartDomain(
                            event: event, history: vm.history, range: range, remembering: vm, now: clock),
                                       plain, "\(label) \(event.status ?? "-") \(event.sport ?? "-") "
                                       + "\(event.commenceTime ?? "-") \(range) \(clock)")
                        XCTAssertEqual(EventDetailView.pageSharedChartDomain(
                            event: event, history: vm.history, range: range, journey: journeyless,
                            key: key(event), remembering: vm, now: clock),
                                       EventDetailView.pageSharedChartDomain(
                            event: event, history: vm.history, range: range, journey: journeyless,
                            key: key(event), now: clock))
                    }
                }
            }
        }

        XCTAssertNil(vm.history)
        try compare("no payload")
        await vm.load()
        XCTAssertNotNil(vm.history, "fixture: the load took the specimen")
        try compare("specimen")
        client.history = try Self.noPeriods()
        await vm.load()
        XCTAssertEqual(vm.history, try Self.noPeriods(), "fixture: the reload took the new payload")
        try compare("new payload")
    }

    /// The fixture really separates every input the memo is keyed on: each
    /// neighbouring pair opens at a different instant, so a memo that ignored
    /// one of them would serve a wrong window, not just a redundant build.
    func testEveryKeyedInputMovesTheOpening() throws {
        let specimen = try Self.specimen()
        func opening(_ history: EventHistoryResponse? = nil, commence: String? = Self.commence,
                     range: OddsTimeRange = .sinceStart, sport: String? = "baseball_mlb") throws -> Date? {
            SharedChartWindow.opening(commenceTime: commence, history: history ?? specimen,
                                      range: range, sportKey: sport)
        }
        let base = try opening()
        XCTAssertNotNil(base)
        XCTAssertNotEqual(base, try opening(range: .all), "range")
        XCTAssertNotEqual(base, try opening(sport: nil), "sport")
        XCTAssertNotEqual(base, try opening(commence: "2026-09-30T21:12:00+00:00"), "scheduled start")
        XCTAssertNotEqual(base, try opening(Self.noPeriods()), "payload")
    }

    // MARK: - The memo itself

    /// One entry, keyed on exactly what `opening` reads. A repeat reuses it; a
    /// change to any one keyed input rebuilds once, and the value it serves is
    /// always the plain opening for the inputs it was handed.
    func testTheMemoRebuildsOnlyWhenAKeyedInputMoves() throws {
        let specimen = try Self.specimen()
        let other = try Self.noPeriods()
        let memo = SharedChartWindow.OpeningMemo()
        struct Step { let history: EventHistoryResponse?; let generation: Int; let commence: String?
                      let range: OddsTimeRange; let sport: String?; let builds: Int }
        let c = Self.commence, late = "2026-09-30T21:12:00+00:00", mlb = "baseball_mlb"
        let steps = [
            Step(history: specimen, generation: 1, commence: c, range: .sinceStart, sport: mlb, builds: 1),
            Step(history: specimen, generation: 1, commence: c, range: .sinceStart, sport: mlb, builds: 1),
            Step(history: specimen, generation: 1, commence: c, range: .all, sport: mlb, builds: 2),
            Step(history: specimen, generation: 1, commence: c, range: .sinceStart, sport: mlb, builds: 3),
            Step(history: specimen, generation: 1, commence: c, range: .sinceStart, sport: nil, builds: 4),
            Step(history: specimen, generation: 1, commence: c, range: .sinceStart, sport: mlb, builds: 5),
            Step(history: specimen, generation: 1, commence: late, range: .sinceStart, sport: mlb, builds: 6),
            Step(history: specimen, generation: 1, commence: c, range: .sinceStart, sport: mlb, builds: 7),
            Step(history: other, generation: 2, commence: c, range: .sinceStart, sport: mlb, builds: 8),
            Step(history: other, generation: 2, commence: c, range: .sinceStart, sport: mlb, builds: 8),
            Step(history: nil, generation: 3, commence: c, range: .sinceStart, sport: mlb, builds: 9),
            Step(history: specimen, generation: 4, commence: c, range: .sinceStart, sport: mlb, builds: 10),
            Step(history: specimen, generation: 4, commence: c, range: .sinceStart, sport: mlb, builds: 10),
        ]
        for (i, step) in steps.enumerated() {
            let served = memo.opening(history: step.history, historyGeneration: step.generation,
                                      commenceTime: step.commence, range: step.range, sportKey: step.sport)
            XCTAssertEqual(served, SharedChartWindow.opening(commenceTime: step.commence, history: step.history,
                                                             range: step.range, sportKey: step.sport), "step \(i)")
            XCTAssertEqual(memo.buildCount, step.builds, "step \(i)")
        }
        XCTAssertEqual(Mirror(reflecting: memo).children.filter { $0.label == "entry" }.count, 1,
                       "one entry, never a history of keys")
    }

    /// The end is never remembered: the live window follows the clock it is
    /// handed and a status change moves it to the last reading, with no rebuild.
    func testTheEndFollowsStatusAndClockWithoutARebuild() async throws {
        let client = Client(try Self.event(status: "completed"), history: try Self.specimen())
        let vm = model(client)
        defer { vm.stopRefresh() }
        await vm.load()
        let live = try Self.event()
        let first = try XCTUnwrap(EventDetailView.pageLegacyChartDomain(
            event: live, history: vm.history, range: .sinceStart, remembering: vm, now: Self.now))
        let builds = vm.chartWindowOpenings.buildCount
        let later = try XCTUnwrap(EventDetailView.pageLegacyChartDomain(
            event: live, history: vm.history, range: .sinceStart, remembering: vm,
            now: Self.now.addingTimeInterval(45)))
        XCTAssertEqual(later.upperBound, first.upperBound.addingTimeInterval(45), "the live end moves with the clock")
        XCTAssertEqual(later.lowerBound, first.lowerBound)
        let final = EventDetailView.pageLegacyChartDomain(
            event: try Self.event(status: "completed"), history: vm.history, range: .sinceStart,
            remembering: vm, now: Self.now)
        XCTAssertEqual(final, SharedChartWindow.domain(status: "completed", commenceTime: Self.commence,
                                                       history: vm.history, range: .sinceStart,
                                                       sportKey: "baseball_mlb", now: Self.now))
        XCTAssertNotEqual(final?.upperBound, first.upperBound, "fixture: the finished end is the last reading")
        XCTAssertEqual(vm.chartWindowOpenings.buildCount, builds, "neither the clock nor the status is a key")
    }

    /// A new payload in the view model is a new opening, even with every other
    /// input unchanged: the key's generation is the model's own.
    func testANewPayloadInTheModelIsANewOpening() async throws {
        let client = Client(try Self.event(status: "completed"), history: try Self.specimen())
        let vm = model(client)
        defer { vm.stopRefresh() }
        await vm.load()
        let live = try Self.event()
        let before = vm.chartWindowOpening(commenceTime: live.commenceTime, range: .sinceStart, sportKey: live.sport)
        client.history = try Self.noPeriods()
        await vm.load()
        let after = vm.chartWindowOpening(commenceTime: live.commenceTime, range: .sinceStart, sportKey: live.sport)
        XCTAssertNotEqual(before, after)
        XCTAssertEqual(after, SharedChartWindow.opening(commenceTime: live.commenceTime, history: try Self.noPeriods(),
                                                        range: .sinceStart, sportKey: live.sport))
        XCTAssertEqual(vm.chartWindowOpenings.buildCount, 2)
    }

    // MARK: - The page reads it

    /// The real page on the real view model: after it has drawn, unrelated
    /// updates (a game-markets body whose score moved) re-run the page body —
    /// the memo is read on each — and none of them works the opening out again.
    func testUnrelatedPageUpdatesReadTheOpeningWithoutRebuildingIt() async throws {
        let client = Client(try Self.event(), history: try Self.specimen())
        let vm = model(client)
        let page = NavigationStack { EventDetailView(eventId: 15321836, viewModel: vm) }
            .environmentObject(PinManager())
            .environment(\.colorScheme, .light)
        let host = hostForMeasurement(page, at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true; vm.stopRefresh() }
        let deadline = ProcessInfo.processInfo.systemUptime + 15
        while (vm.event == nil || vm.history == nil) && ProcessInfo.processInfo.systemUptime < deadline {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        XCTAssertNotNil(vm.history, "fixture: the page loaded the specimen")
        for _ in 0..<6 {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        let builds = vm.chartWindowOpenings.buildCount
        let reads = vm.chartWindowOpenings.readCount
        XCTAssertGreaterThanOrEqual(builds, 1, "the page worked its opening out")
        for score in 1...5 {
            let body = try Self.decoder().decode(GameMarketsResponse.self, from: Data(
                #"{"event_id":15321836,"home_score":\#(score),"away_score":0}"#.utf8))
            vm.receiveGameMarkets(body)
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertGreaterThanOrEqual(vm.chartWindowOpenings.readCount - reads, 10,
                                    "five page bodies, both chart mounts each, read the memo")
        XCTAssertEqual(vm.chartWindowOpenings.buildCount, builds, "no unrelated update rebuilt the opening")
    }

    /// Both window reads on the page hand the memo; nothing else changed in
    /// what the page passes.
    func testThePageHandsItsModelToBothWindowReads() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let text = try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/EventDetailView.swift"),
                              encoding: .utf8)
        let flat = text.filter { !$0.isWhitespace }
        XCTAssertTrue(flat.contains(
            "privatevarsharedChartDomain:ClosedRange<Date>?{Self.pageSharedChartDomain(event:vm.event,history:vm.history,range:chartRange,journey:vm.publicationJourney,key:publicationTaskKey,remembering:vm,now:displayNow())}"))
        XCTAssertTrue(flat.contains(
            "privatevarlegacyChartDataDomain:ClosedRange<Date>?{Self.pageLegacyChartDataDomain(event:vm.event,history:vm.history,range:chartRange,journey:vm.publicationJourney,key:publicationTaskKey,remembering:vm,now:displayNow())}"))
        XCTAssertTrue(flat.contains(
            "opening:vm.chartWindowOpening(commenceTime:event.commenceTime,range:range,sportKey:event.sport),status:event.status,history:history,now:now)"),
                      "the remembered path takes the same three end inputs as the plain one")
    }
}
