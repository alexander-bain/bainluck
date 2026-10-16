import XCTest
import Foundation
@testable import Bain_Luck

/// #683 (Root ruling B) — the Evolution chart's widest chip asked for a fixed
/// `hours=4320`. Root's d58 control: a settled question whose recovered Kalshi
/// intervals are 189 days old serves them at 4800h and draws NOTHING at 4320h.
/// The widest chip now adds `range=full` (calibration PR #11083, web PR #11089);
/// every shorter chip's request is unchanged, and an older server ignores it.
///
/// Real APIClient + real URLSession dispatch; only the HTTP server is stubbed.
/// It records every request and answers each path with the body the test set,
/// so the request half and the decode half are the ones the chart uses.
final class TheWidestChartAsksForTheWholeRecoveredHistory683Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var captured: [URLRequest] = []
        nonisolated(unsafe) private static var bodies: [String: String] = [:]

        static func reset(bodies: [String: String] = [:]) {
            lock.lock(); defer { lock.unlock() }
            captured = []; self.bodies = bodies
        }
        static var requests: [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.lock.lock()
            Self.captured.append(request)
            let body = Self.bodies[request.url?.path ?? ""]
            Self.lock.unlock()
            let response = HTTPURLResponse(
                url: request.url!, statusCode: body == nil ? 404 : 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data((body ?? "{}").utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    override func setUp() {
        super.setUp()
        Origin.reset()
    }

    private func client() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = nil
        return APIClient(session: URLSession(configuration: configuration))
    }

    private func query(_ request: URLRequest) -> [String: String] {
        let items = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
        return Dictionary(items.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { first, _ in first })
    }

    /// 10/15 22:00Z — the reading time every specimen below is dated against.
    private let now = "2026-10-15T22:00:00Z".asDate!
    private var hoursFloor: Date { now.addingTimeInterval(-4320 * 3600) }

    private func timeline(marketId: Int, hours: Int, first: String, block: String?) -> String {
        """
        {"market_id": \(marketId), "market_name": "Specimen", "sport_category": "politics",
         "source": "kalshi", "hours": \(hours), "top": 50, "bucket_seconds": 3600,
         "coverage_hours": 4600.0, "observation_times": 240,
         "timeline": [
           {"timestamp": "\(first)", "outcomes": {"Yes": 31.0}},
           {"timestamp": "2026-10-14T22:00:00+00:00", "outcomes": {"Yes": 64.0}}],
         "outcomes": [{"id": 9001, "name": "Yes", "current_probability": 64.0}]
         \(block.map { ", \"history_range\": \($0)" } ?? "")}
        """
    }

    // MARK: - The request half

    func testOnlyTheWidestChipAsksForTheWholeHistory() {
        XCTAssertTrue(EvolutionFullRange.asksForFullHistory(.season))
        for range in [EvolutionTimeRange.week, .tournament, .day, .today] {
            XCTAssertFalse(EvolutionFullRange.asksForFullHistory(range),
                           "\(range.rawValue) is an explicit short window and stays one")
        }
    }

    /// The actual client request for Root's 189-day specimen, on both reads the
    /// widest chip makes: the timeline, and a verified chart's `/history` (#10244).
    func testTheWidestChipSendsRangeFullOnBothReadsAndKeepsItsHours() async throws {
        let api = client()
        _ = try? await api.fetchProbabilityTimeline(marketId: 68301, top: 50, hours: 4320, fullRange: true)
        _ = try? await api.fetchFuturesHistory(marketId: 68301, hours: 4320, fullRange: true)
        let sent = Origin.requests.map(query)
        XCTAssertEqual(sent.count, 2)
        XCTAssertEqual(sent.first, ["top": "50", "hours": "4320", "range": "full", "fresh": "true"])
        XCTAssertEqual(sent.last, ["hours": "4320", "top_n": "50", "range": "full", "fresh": "true"])
    }

    /// Every other request is byte-for-byte what it was: no `range` key at all.
    /// (`fresh=true` is the client's existing revalidation key on every futures
    /// read, on master before #683.)
    func testAShorterChipsRequestIsUnchanged() async throws {
        let api = client()
        _ = try? await api.fetchProbabilityTimeline(marketId: 68302, top: 50, hours: 168)
        _ = try? await api.fetchProbabilityTimeline(
            marketId: 68302, top: 50, hours: 24, representation: .verifiedTitle)
        _ = try? await api.fetchFuturesHistory(marketId: 68302, hours: 168)
        let sent = Origin.requests.map(query)
        XCTAssertEqual(sent, [
            ["top": "50", "hours": "168", "fresh": "true"],
            ["top": "50", "hours": "24", "representation": "verified_title", "fresh": "true"],
            ["hours": "168", "top_n": "50", "fresh": "true"],
        ])
    }

    // MARK: - The served half

    /// Root's specimen as the chart receives it: the first archive interval is 189
    /// days old, past the 4320h floor. It decodes, its block is read, and the widest
    /// chip's client cutoff keeps it — while `7d` still trims it.
    func testThe189DaySpecimenReachesTheChartPastTheHoursFloor() async throws {
        let first = "2026-04-09T22:00:00+00:00"
        Origin.reset(bodies: ["/api/futures/68303/probability-timeline": timeline(
            marketId: 68303, hours: 4320, first: first, block: """
            {"requested": "full", "window_start": "\(first)",
             "window_start_basis": "archive_first_interval", "archive_coverage": "incomplete",
             "archive_venue_open": "2026-03-02T15:00:00+00:00", "thinned_outcomes": [],
             "live_thinned": false}
            """)])
        let payload = try await client().fetchProbabilityTimeline(
            marketId: 68303, top: 50, hours: 4320, fullRange: true)

        let block = try XCTUnwrap(EvolutionFullRange.served(payload.historyRange))
        XCTAssertEqual(block.windowStartBasis, "archive_first_interval")
        XCTAssertEqual(block.archiveCoverage, "incomplete")
        XCTAssertEqual(payload.hours, 4320, "the server echoes the requested hours")

        let oldest = try XCTUnwrap(payload.timeline.first?.timestamp.asDate)
        XCTAssertLessThan(oldest, hoursFloor, "the specimen must lie past the floor to testify")
        XCTAssertNil(
            EvolutionChartView.timeCutoff(for: .season, tournamentStart: nil, now: now),
            "the widest chip draws every instant served")
        let week = try XCTUnwrap(EvolutionChartView.timeCutoff(for: .week, tournamentStart: nil, now: now))
        XCTAssertLessThan(oldest, week, "an ordinary range still trims to its own window")
    }

    /// The lifetime control: a question we first ingested long after the venue
    /// listed it, whose outcome carries more than the 5000-interval read cap. The
    /// server span-samples (`thinned_outcomes`, `live_thinned`) and keeps the first
    /// interval; the client must draw that oldest instant, not a tail.
    func testAnOlderThanIngestionThinnedLifetimeKeepsItsOldestInstant() async throws {
        let venueFirst = "2025-06-01T14:00:00+00:00"   // ingestion began 2025-11-01
        Origin.reset(bodies: ["/api/futures/68304/probability-timeline": timeline(
            marketId: 68304, hours: 4320, first: venueFirst, block: """
            {"requested": "full", "window_start": "\(venueFirst)",
             "window_start_basis": "archive_first_interval", "archive_coverage": "complete",
             "archive_venue_open": "\(venueFirst)", "thinned_outcomes": [9001],
             "live_thinned": true}
            """)])
        let payload = try await client().fetchProbabilityTimeline(
            marketId: 68304, top: 50, hours: 4320, fullRange: true)
        let block = try XCTUnwrap(EvolutionFullRange.served(payload.historyRange))
        XCTAssertEqual(block.thinnedOutcomes, [9001])
        XCTAssertEqual(block.liveThinned, true)
        XCTAssertEqual(payload.timeline.first?.timestamp, venueFirst,
                       "a thinned lifetime still begins at its first interval")
        XCTAssertLessThan(try XCTUnwrap(payload.timeline.first?.timestamp.asDate),
                          "2025-11-01T00:00:00Z".asDate!)
    }

    /// The server has grown basis words twice already; an unknown one decodes and
    /// reads as "starts at window_start". A non-full or malformed block is absent,
    /// and never fails the chart's decode.
    func testUnknownBasisAndMalformedBlocksNeverFailTheChart() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        func decode(_ block: String?) throws -> ProbabilityTimelineResponse {
            try decoder.decode(ProbabilityTimelineResponse.self, from: Data(timeline(
                marketId: 1, hours: 4320, first: "2026-04-09T22:00:00+00:00", block: block).utf8))
        }
        let unknown = try decode(#"{"requested": "full", "window_start_basis": "a_future_word"}"#)
        XCTAssertEqual(EvolutionFullRange.served(unknown.historyRange)?.windowStartBasis, "a_future_word")
        XCTAssertFalse(EvolutionFullRange.earliestPointIsUnproven(unknown.historyRange))

        XCTAssertNil(try decode(nil).historyRange, "an older server sends no block")
        XCTAssertNil(try decode(#""full""#).historyRange)
        XCTAssertNil(EvolutionFullRange.served(
            try decode(#"{"requested": "since_start"}"#).historyRange))
        XCTAssertNil(try decode(#"{"requested": "full", "thinned_outcomes": "x"}"#)
            .historyRange?.thinnedOutcomes, "one bad key drops that key, not the block")
    }

    /// A verified chart draws `/history`'s lines; the block describing them comes too.
    func testAVerifiedChartCarriesTheHistoryReadsBlock() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let timelinePayload = try decoder.decode(ProbabilityTimelineResponse.self, from: Data(timeline(
            marketId: 2, hours: 4320, first: "2026-05-01T00:00:00+00:00", block: nil).utf8))
        let history = try decoder.decode(FuturesHistoryResponse.self, from: Data("""
            {"market_id": 2, "coverage_hours": 4600.0, "observation_times": 120,
             "outcomes": [{"outcome_id": 9001, "name": "Yes", "history": [
               {"timestamp": "2026-04-09T22:00:00+00:00", "probability": 30.0}]}],
             "history_range": {"requested": "full", "window_start_basis": "live_first_capture",
               "archive_coverage": null, "thinned_outcomes": [], "live_thinned": false}}
            """.utf8))
        let drawn = VerifiedTitleHistory.drawing(history, over: timelinePayload)
        XCTAssertEqual(drawn.historyRange, history.historyRange)
        XCTAssertEqual(drawn.historyRange?.windowStartBasis, "live_first_capture")
        XCTAssertEqual(drawn.timeline.first?.timestamp, "2026-04-09T22:00:00+00:00")
    }

    // MARK: - The earliest drawn point is not the question's open

    func testASpanSentenceIsWithheldOnlyWhenTheRecordsEdgeIsUnproven() {
        func block(_ basis: String?, _ coverage: String?) -> FuturesHistoryRange {
            FuturesHistoryRange(requested: "full", windowStartBasis: basis, archiveCoverage: coverage)
        }
        func note(_ range: FuturesHistoryRange?) -> String? {
            EvolutionChartView.coverageNote(
                coverageHours: 720, observationTimes: 200, requestedHours: 4320, historyRange: range)
        }
        let today = "Prices only go back 30d"
        XCTAssertEqual(note(nil), today, "no block = today's sentence")
        XCTAssertNil(note(block("archive_first_interval", "incomplete")),
                     "an incomplete import's first interval is not the question's open")
        XCTAssertNil(note(block("venue_first_observation", nil)))
        XCTAssertEqual(note(block("archive_first_interval", "complete")), today,
                       "a complete import did recover the venue's lifetime")
        XCTAssertEqual(note(block("live_first_capture", "incomplete")), today)
        XCTAssertEqual(note(block("hours", nil)), today)
        XCTAssertEqual(
            note(FuturesHistoryRange(requested: "since_start", windowStartBasis: "archive_first_interval")),
            today, "only a served full read changes anything")
        XCTAssertEqual(
            EvolutionChartView.coverageNote(
                coverageHours: 720, observationTimes: 2, requestedHours: 4320,
                historyRange: block("archive_first_interval", "incomplete")),
            "Only 2 prices seen so far", "the count sentence is about what is drawn, and stays")
    }

    // MARK: - A partial read says so

    /// calibration's reader rule (PR #11083 @ 616d0c0a6b): when the server withheld
    /// older archive intervals it could not place against our thinned captures, it
    /// serves `served_history: "partial"`, and the Full chart adds one plain caption.
    /// The served payload, decoded by the real client, drives the caption.
    func testAPartialFullReadSaysSomeOlderPricesArentShown() async throws {
        let first = "2025-06-01T14:00:00+00:00"
        Origin.reset(bodies: ["/api/futures/68305/probability-timeline": timeline(
            marketId: 68305, hours: 4320, first: first, block: """
            {"requested": "full", "window_start": "\(first)",
             "window_start_basis": "live_first_capture", "archive_coverage": "complete",
             "thinned_outcomes": [], "live_thinned": true, "served_history": "partial",
             "unresolved_withheld": {"archive_intervals": 3, "venue_points": 0}}
            """)])
        let payload = try await client().fetchProbabilityTimeline(
            marketId: 68305, top: 50, hours: 4320, fullRange: true)
        XCTAssertTrue(EvolutionFullRange.servedPartially(payload.historyRange))
        XCTAssertEqual(payload.timeline.count, 2, "every served point is still drawn")
        let note = EvolutionChartView.coverageNote(
            coverageHours: payload.coverageHours, observationTimes: payload.observationTimes,
            requestedHours: 4320, historyRange: payload.historyRange)
        XCTAssertEqual(note, "Some older prices aren't shown")
        XCTAssertFalse(try XCTUnwrap(note).contains(where: \.isNumber), "no counts on the reader's screen")
    }

    /// `complete`, absent, an unknown word or a non-full block: no caption, no change.
    func testOnlyAServedPartialFullReadEarnsTheCaption() {
        func note(_ range: FuturesHistoryRange?, seen: Int = 200) -> String? {
            EvolutionChartView.coverageNote(
                coverageHours: 4600, observationTimes: seen, requestedHours: 4320, historyRange: range)
        }
        let partial = "Some older prices aren't shown"
        XCTAssertEqual(note(FuturesHistoryRange(requested: "full", servedHistory: "partial")), partial)
        XCTAssertNil(note(FuturesHistoryRange(requested: "full", servedHistory: "complete")))
        XCTAssertNil(note(FuturesHistoryRange(requested: "full")), "an older server = complete")
        XCTAssertNil(note(FuturesHistoryRange(requested: "full", servedHistory: "a_future_word")))
        XCTAssertNil(note(FuturesHistoryRange(requested: "since_start", servedHistory: "partial")),
                     "only a served full read changes anything")
        XCTAssertNil(note(nil))
        XCTAssertEqual(
            note(FuturesHistoryRange(requested: "full", servedHistory: "partial"), seen: 2), partial,
            "withheld older prices make 'only 2 prices seen' untrue too")
        XCTAssertEqual(
            EvolutionChartView.coverageNote(
                coverageHours: 720, observationTimes: 200, requestedHours: 4320,
                historyRange: FuturesHistoryRange(
                    requested: "full", windowStartBasis: "archive_first_interval",
                    archiveCoverage: "complete", servedHistory: "partial")),
            partial, "the span sentence would claim the drawn edge is the record's edge")
    }

    // MARK: - A partial read says so with too few prices to draw (CERT-4158)

    private func sparse(_ timeline: String, block: String) -> String {
        """
        {"market_id": 68306, "market_name": "Specimen", "sport_category": "politics",
         "source": "kalshi", "hours": 4320, "top": 50, "bucket_seconds": 3600,
         "timeline": \(timeline),
         "outcomes": [{"id": 9001, "name": "Yes", "current_probability": 64.0}],
         "history_range": \(block)}
        """
    }

    private let partialBlock = """
        {"requested": "full", "window_start_basis": "archive_first_interval",
         "archive_coverage": "incomplete", "served_history": "partial",
         "unresolved_withheld": {"archive_intervals": 3, "venue_points": 0}}
        """

    /// The card the decoded payload draws, decided exactly as the body decides it:
    /// the widest chip has no cutoff, so the window holds every served instant, and
    /// the payload's own block rides in.
    private func card(_ payload: ProbabilityTimelineResponse, points: Int) -> EvolutionChartView.CardBody {
        let instants = payload.timeline.filter { $0.timestamp.asDate != nil }.count
        return EvolutionChartView.cardBody(
            windowPoints: points, windowInstants: instants, totalInstants: instants,
            windowWord: EvolutionChartView.windowWord(for: .season),
            historyRange: payload.historyRange)
    }

    /// CERT-4158: an EMPTY Full read the server served `partial` fell to the sparse
    /// branch, which never read the block, and printed "No price history yet" over
    /// prices the server withheld. Real client, real decode, the body's own rule.
    func testAnEmptyPartialFullReadSaysPricesAreWithheldNotThatThereAreNone() async throws {
        Origin.reset(bodies: ["/api/futures/68306/probability-timeline": sparse("[]", block: partialBlock)])
        let payload = try await client().fetchProbabilityTimeline(
            marketId: 68306, top: 50, hours: 4320, fullRange: true)
        XCTAssertTrue(payload.timeline.isEmpty, "nothing is drawn, nothing is invented")
        XCTAssertEqual(
            card(payload, points: 0),
            .sparse(.init(note: "Some older prices aren't shown", hint: nil)))
    }

    /// One served price: still too few to draw, and "Only one price seen so far" is
    /// untrue when the server withheld older ones.
    func testAOneValuePartialFullReadSaysPricesAreWithheld() async throws {
        Origin.reset(bodies: ["/api/futures/68306/probability-timeline": sparse(
            #"[{"timestamp": "2026-10-14T22:00:00+00:00", "outcomes": {"Yes": 64.0}}]"#,
            block: partialBlock)])
        let payload = try await client().fetchProbabilityTimeline(
            marketId: 68306, top: 50, hours: 4320, fullRange: true)
        XCTAssertEqual(payload.timeline.count, 1)
        XCTAssertEqual(
            card(payload, points: 1),
            .sparse(.init(note: "Some older prices aren't shown", hint: nil)))
    }

    /// The instant/point split #7350 pinned: two served instants that draw one point
    /// (the other carries only an undisplayed outcome) are still the sparse card.
    func testTwoInstantsDrawingOnePointStillSayPricesAreWithheld() {
        let partial = FuturesHistoryRange(requested: "full", servedHistory: "partial")
        XCTAssertEqual(
            EvolutionChartView.cardBody(
                windowPoints: 1, windowInstants: 2, totalInstants: 2,
                windowWord: EvolutionChartView.windowWord(for: .season), historyRange: partial),
            .sparse(.init(note: "Some older prices aren't shown", hint: nil)))
    }

    /// Controls: everything that is not a served partial full read keeps today's words.
    func testOnlyAServedPartialFullReadChangesTheSparseCard() {
        let word = EvolutionChartView.windowWord(for: .season)
        func copy(_ range: FuturesHistoryRange?, window: Int, total: Int,
                  word: String = word) -> EvolutionChartView.SparseCopy {
            EvolutionChartView.sparseCopy(
                windowInstants: window, totalInstants: total, windowWord: word, historyRange: range)
        }
        let none = EvolutionChartView.SparseCopy(note: "No price history yet", hint: nil)
        let one = EvolutionChartView.SparseCopy(note: "Only one price seen so far", hint: nil)
        for range in [
            FuturesHistoryRange(requested: "full", servedHistory: "complete"),
            FuturesHistoryRange(requested: "full"),                               // older server
            FuturesHistoryRange(requested: "full", servedHistory: "a_future_word"),
            FuturesHistoryRange(requested: "since_start", servedHistory: "partial"), // non-full
            nil,                                                                  // short chip / no block
        ] as [FuturesHistoryRange?] {
            XCTAssertEqual(copy(range, window: 0, total: 0), none, "a genuinely empty history: \(String(describing: range))")
            XCTAssertEqual(copy(range, window: 1, total: 1), one, "\(String(describing: range))")
        }

        // A window with earlier prices outside it keeps its own sentence and its way
        // out: the sentence is about the window, and the widest chip says the rest.
        let partial = FuturesHistoryRange(requested: "full", servedHistory: "partial")
        XCTAssertEqual(
            copy(partial, window: 0, total: 3, word: "in the last 7 days"),
            .init(note: "No prices in the last 7 days — 3 earlier prices", hint: "Try a longer range"))
        // Two points still plot — the partial caption there is `coverageNote`'s.
        XCTAssertEqual(
            EvolutionChartView.cardBody(
                windowPoints: 2, windowInstants: 2, totalInstants: 2, windowWord: word,
                historyRange: partial),
            .plot)
    }

    /// The rule above is only the reader's if the body hands it the payload's block —
    /// the opaque `body` cannot be called, so the call site is scanned (comments
    /// stripped, whitespace collapsed), as #7350's seam test does.
    func testTheSparseCardIsDecidedWithThePayloadsBlockAndKeepsArchiveProvenance() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let source = try String(
            contentsOf: root.appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift"),
            encoding: .utf8)
        let flat = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
            .split(whereSeparator: \.isWhitespace).joined(separator: " ")
        XCTAssertTrue(flat.contains("struct EvolutionChartView"))
        XCTAssertTrue(
            flat.contains("windowWord: windowWord, historyRange: data?.historyRange ) { case .sparse(let copy):"),
            "the body must decide the card with the served block")
        XCTAssertTrue(
            flat.contains("emptyState(copy.note, hint: copy.hint) if let note = archiveNote {"),
            "a counted archived price keeps its provenance line on the sparse card")
    }
}
