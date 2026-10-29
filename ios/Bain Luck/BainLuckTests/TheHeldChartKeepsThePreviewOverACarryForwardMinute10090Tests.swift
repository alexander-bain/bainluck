import XCTest
@testable import Bain_Luck

/// #10090 — the iPhone twin of web PR #11753: the held chart's end follows the
/// headline's preview for the preview's whole lifetime.
///
/// Specimen: calibration's matched lab pair, 2026-10-29 20:20Z, base arm
/// (`artifacts/calibration-10090-11742-pair-20261029`). The headline showed the
/// 71% preview for its 60 s lifetime. At +52.4 s the page's history poll read a
/// payload whose sources had been quiet for 30 s, so the backend carried each
/// one to the read time (`_extend_win_prob_history_to_live_edge`, `live_edge`)
/// and the minute bucket of that read (20:03:00) landed on the blend line after
/// the preview's observation (20:02:43.7). `chartFrames` and the drawn chart
/// both took that bucket for a committed point newer than the preview, and the
/// chart fell back to 63% while the headline still printed 71%.
///
/// The web's other fall, at +20.4 s, is the page rewriting the pinned edge in
/// place (#8749); the app never rewrites a served value, so here it is only a
/// control that already held.
@MainActor
final class TheHeldChartKeepsThePreviewOverACarryForwardMinute10090Tests: XCTestCase {
    private static let id = 1
    private static let previewAt = "2026-10-29T20:02:43.715334+00:00"
    private static let carriedMinute = "2026-10-29T20:03:00+00:00"
    private static let readAt52 = "2026-10-29T20:03:36.081995+00:00"

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private static func date(_ stamp: String) -> Date { stamp.asDate! }

    // MARK: - Specimen

    /// The page's committed event: 63% at the second prime, folded from this
    /// row (rev 2) and a duplicate (rev 5). The app's folded wire needs two
    /// rows; the specimen's v3 frame folded one.
    private static func event(hero: Double = 0.63, rev: Int = 2, fold: [String: Int]? = nil, status: String = "live",
                              observed: String = "2026-10-29T20:02:37.742159+00:00") throws -> EventDetail {
        try decoder.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: [
            "id": id, "home_team": "Home", "away_team": "Away", "sport": "tennis_atp", "status": status,
            "current_odds": ["home_probability": hero, "away_probability": 1 - hero],
            "hero_probability": hero, "hero_probability_away": 1 - hero, "hero_probability_source": "blend",
            "hero_probability_observed_at": observed, "blend_fold_revision": fold ?? ["1": rev, "2": 5]]))
    }

    /// The two committed frames the stream pushed before the target (rev 1, rev 2).
    private static let primes = [
        LiveBlendPoint(date: date("2026-10-29T20:02:37.727545+00:00"), homeProbability: 0.48875),
        LiveBlendPoint(date: date("2026-10-29T20:02:37.742159+00:00"), homeProbability: 0.63),
    ]

    private static func foldedFrame(_ p: Double = 0.71, seq: Int = 5, observed: String? = previewAt) throws
        -> BlendPreviewFrame {
        var wire: [String: Any] = [
            "event_id": id, "p": p, "p_away": 1 - p, "sport": "tennis_atp", "status": "live",
            "preview": ["kind": "blend", "epoch": 3, "seq": seq, "base_rev": 2, "ttl_ms": 60_000,
                        "folded_version": 1, "origin_event_id": id, "base_fold_revision": ["1": 2, "2": 5],
                        "pending_entries_version": 2, "pending_entries_authority": "event-ledger-v1"]]
        if let observed { wire["display_observed_at"] = observed }
        let raw = String(data: try JSONSerialization.data(withJSONObject: wire), encoding: .utf8)!
        return try XCTUnwrap(BlendPreviewFrame.decode(raw))
    }

    /// The preview as the page holds it: received at +116 ms, gone at its 60 s lifetime.
    private static func held(observed: String? = previewAt) throws -> BlendPreviewState? {
        BlendPreview.readerAfter(.empty, try foldedFrame(observed: observed), eventId: id, now: 0.116).held
    }

    private static let realSources: [String: [[String: Any]]] = [
        "kalshi": [["timestamp": "2026-10-29T20:01:10+00:00", "home_probability": 0.465],
                   ["timestamp": "2026-10-29T20:02:37.727545+00:00", "home_probability": 0.6]],
        "polymarket": [["timestamp": "2026-10-29T20:01:10+00:00", "home_probability": 0.3775],
                       ["timestamp": "2026-10-29T20:02:37.742159+00:00", "home_probability": 0.66]],
    ]

    private static func served(_ line: [(String, Double)], observed: String, rev: Int,
                               sources: [String: [[String: Any]]], eventId: Int = id,
                               status: String = "live", pinned: Bool = true, history: [[String: Any]] = [],
                               bookmakers: [String: [[String: Any]]]? = nil) throws -> EventHistoryResponse {
        var payload: [String: Any] = [
            "event_id": eventId, "home_team": "Home", "away_team": "Away", "status": status,
            "history": history,
            "aggregate_line": line.map { ["timestamp": $0.0, "home_probability": $0.1] },
            "blend_edge_pinned": pinned, "blend_edge_observed_at": observed,
            "blend_edge_fold_revision": ["1": rev, "2": 5], "win_prob_history": sources]
        if let bookmakers { payload["bookmaker_history"] = bookmakers }
        return try decoder.decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    /// The boot read at 20:02:36, before the primes and the target.
    private static func bootRead() throws -> EventHistoryResponse {
        try served([("2026-10-29T20:01:00+00:00", 0.42125), ("2026-10-29T20:02:36.425768+00:00", 0.42125)],
                   observed: "2026-10-29T20:02:23.834954+00:00", rev: 0,
                   sources: realSources.mapValues { [$0[0]] })
    }

    /// The 20:03:04 read (+20.4 s): edge pinned from the cached detail hero, no carry yet.
    private static func pollAt20() throws -> EventHistoryResponse {
        try served([("2026-10-29T20:01:00+00:00", 0.42125), ("2026-10-29T20:02:00+00:00", 0.63),
                    ("2026-10-29T20:03:04.064256+00:00", 0.42125)],
                   observed: "2026-10-29T20:02:23.834954+00:00", rev: 0, sources: realSources)
    }

    /// The 20:03:36 read (+52.4 s): a fresh edge, and both sources carried to the read time.
    private static func pollAt52(edgeRev: Int = 2, edgeValue: Double = 0.63, eventId: Int = id,
                                 status: String = "live", pinned: Bool = true,
                                 edgeObserved: String = "2026-10-29T20:02:37.742159+00:00",
                                 extraReadings: [String: [[String: Any]]] = [:],
                                 carriedBy: (String) -> [String: Any] = { _ in ["live_edge": true] },
                                 history: [[String: Any]] = [],
                                 bookmakers: [String: [[String: Any]]]? = nil) throws -> EventHistoryResponse {
        var sources = realSources
        for (name, carry) in [("kalshi", 0.6), ("polymarket", 0.66)] {
            sources[name]?.append(["timestamp": "2026-10-29T20:03:36+00:00", "home_probability": carry]
                .merging(carriedBy(name)) { $1 })
        }
        for (name, points) in extraReadings { sources[name, default: []].append(contentsOf: points) }
        return try served([("2026-10-29T20:01:00+00:00", 0.42125), ("2026-10-29T20:02:00+00:00", 0.63),
                           (carriedMinute, 0.63), (readAt52, edgeValue)],
                          observed: edgeObserved, rev: edgeRev, sources: sources,
                          eventId: eventId, status: status, pinned: pinned, history: history, bookmakers: bookmakers)
    }

    // MARK: - Reading what the page prints

    /// The hero's number (`EventDetailViewModel.headline`).
    private static func headline(_ event: EventDetail, _ state: BlendPreviewState?, now: TimeInterval) -> Double? {
        BlendPreview.overlay(event, state, now: now).heroProbability
    }

    /// The frames the page hands its chart (`EventDetailViewModel.chartFrames`).
    private static func frames(_ served: EventHistoryResponse, _ event: EventDetail, _ state: BlendPreviewState?,
                               now: TimeInterval, pushed: [LiveBlendPoint] = primes) -> [LiveBlendPoint] {
        BlendPreview.chartFrames(pushed, history: served, state: state, held: event, now: now)
    }

    /// The blend line the chart draws for those frames.
    private static func drawnBlend(_ served: EventHistoryResponse, _ frames: [LiveBlendPoint]) -> [ChartDataPoint] {
        OddsChartView.chartPoints(from: served, liveFrames: frames)
            .filter { $0.source == "aggregate" }
            .sorted { $0.date < $1.date }
    }

    private static func drawnEnd(_ served: EventHistoryResponse, _ event: EventDetail,
                                 _ state: BlendPreviewState?, now: TimeInterval,
                                 pushed: [LiveBlendPoint] = primes) -> ChartDataPoint? {
        drawnBlend(served, frames(served, event, state, now: now, pushed: pushed)).last
    }

    // MARK: - The class

    func testTheCarryForwardMinuteAfterThePreviewDoesNotEndItEarly() throws {
        let event = try Self.event(), state = try Self.held(), served = try Self.pollAt52()
        XCTAssertEqual(Self.headline(event, state, now: 52.415), 0.71)
        let chart = Self.frames(served, event, state, now: 52.415)
        XCTAssertEqual(chart.last?.date, Self.date(Self.previewAt), "the frames the page hands its chart")
        XCTAssertEqual(chart.last?.homeProbability, 0.71)
        let end = try XCTUnwrap(Self.drawnEnd(served, event, state, now: 52.415))
        XCTAssertEqual(end.date, Self.date(Self.previewAt), "the line the chart draws")
        XCTAssertEqual(end.probability, 0.71)
    }

    func testTheReadThatCarriesThroughAnEvidenceKindIsTheSameMinute() throws {
        let event = try Self.event(), state = try Self.held()
        let served = try Self.pollAt52(carriedBy: { _ in ["evidence": ["kind": "live_edge"]] })
        XCTAssertEqual(Self.drawnEnd(served, event, state, now: 52.415)?.probability, 0.71)
        XCTAssertEqual(Self.frames(served, event, state, now: 52.415).last?.homeProbability, 0.71)
    }

    func testTheProjectionRemovesOnlyTheEdgeAndItsCarriedMinute() throws {
        let event = try Self.event(), state = try Self.held(), served = try Self.pollAt52()
        let copy = served
        let all = OddsChartView.chartPoints(from: served, liveFrames: Self.primes)
        let shown = OddsChartView.chartPoints(from: served, liveFrames: Self.frames(served, event, state, now: 52.415))
        // Every venue series is untouched; the blend loses only the two read-time points.
        func venue(_ points: [ChartDataPoint]) -> [String] {
            points.filter { $0.source != "aggregate" }.map { "\($0.source)@\($0.date.timeIntervalSince1970)=\($0.probability)" }
        }
        XCTAssertEqual(venue(shown), venue(all))
        XCTAssertFalse(venue(all).isEmpty)
        let blend = shown.filter { $0.source == "aggregate" }
        XCTAssertFalse(blend.contains { $0.date >= Self.date(Self.carriedMinute) })
        XCTAssertEqual(blend.filter { $0.date < Self.date(Self.previewAt) }.map(\.probability).first, 0.42125,
                       "the readings before the preview stay")
        XCTAssertTrue(blend.contains { $0.probability == 0.63 && $0.date < Self.date(Self.previewAt) },
                      "the 20:02 minute stays")
        XCTAssertEqual(served, copy, "the served history is never written")
        XCTAssertEqual(served.aggregateLine?.count, 4)
    }

    /// The +20.4 s read: the app never rewrites the pinned value, so its
    /// synthetic edge already yielded. A control, not the defect.
    func testThe20sReadsPinnedEdgeYieldsToThePreview() throws {
        let event = try Self.event(), state = try Self.held(), served = try Self.pollAt20()
        XCTAssertEqual(Self.frames(served, event, state, now: 20.416).last?.homeProbability, 0.71)
        let end = try XCTUnwrap(Self.drawnEnd(served, event, state, now: 20.416))
        XCTAssertEqual(end.date, Self.date(Self.previewAt))
        XCTAssertEqual(end.probability, 0.71)
    }

    /// The page over 0–70 s with no commit: each history poll arrives at its
    /// specimen time, and every 100 ms the chart's end must be the number the
    /// headline shows — both the frames the page hands its chart and the line
    /// the chart draws.
    func testHeadlineAndChartAgreeEvery100msFrom0To70sWithNoCommit() throws {
        let event = try Self.event(), held = try Self.held()
        let polls: [(TimeInterval, EventHistoryResponse)] = [
            (-6, try Self.bootRead()), (20.416, try Self.pollAt20()), (52.415, try Self.pollAt52()),
        ]
        var previewShown = 0
        var disagreements: [String] = []
        for tick in 0...700 {
            let now = Double(tick) / 10
            let served = try XCTUnwrap(polls.last { $0.0 <= now }?.1)
            let state = now >= 0.116 ? held : nil
            let headline = try XCTUnwrap(Self.headline(event, state, now: now))
            if headline == 0.71 { previewShown += 1 }
            let frames = Self.frames(served, event, state, now: now)
            let drawn = Self.drawnBlend(served, frames).last?.probability
            if frames.last?.homeProbability != headline || drawn != headline {
                disagreements.append("\(now) s: headline \(headline), frames \(frames.last?.homeProbability ?? -1), drawn \(drawn ?? -1)")
            }
        }
        // The first tick where they part, and how many; none on a correct page.
        XCTAssertEqual(disagreements.first, nil, "\(disagreements.count) of 701 ticks disagree")
        XCTAssertEqual(previewShown, 600, "the preview shows from 0.2 s through 60.1 s")
        XCTAssertNil(BlendPreview.displayed(held, held: event, now: 60.116), "the lifetime still ends both")
    }

    func testACommitAt30sReplacesThePreviewOnBothWithTheCommittedValue() throws {
        let commit = LiveBlendPoint(date: Self.date("2026-10-29T20:03:13.700000+00:00"), homeProbability: 0.71)
        let committed = try Self.event(hero: 0.71, rev: 3, observed: "2026-10-29T20:03:13.700000+00:00")
        let state = try Self.held()
        XCTAssertNil(BlendPreview.displayed(state, held: committed, now: 30))
        let pushed = Self.primes + [commit]
        let poll20 = try Self.pollAt20()
        XCTAssertEqual(Self.frames(poll20, committed, state, now: 30, pushed: pushed), pushed)
        XCTAssertEqual(Self.drawnEnd(poll20, committed, state, now: 30, pushed: pushed)?.probability, 0.71)
        // A later fresh read that holds the commit ends on it.
        let fresh = try Self.pollAt52(edgeRev: 3, edgeValue: 0.71)
        XCTAssertEqual(Self.frames(fresh, committed, state, now: 52.415, pushed: pushed), pushed)
        XCTAssertEqual(Self.drawnEnd(fresh, committed, state, now: 52.415, pushed: pushed)?.probability, 0.71)
    }

    // MARK: - Every guard still refuses

    /// A minute that also holds a reading is not a carry-forward minute; the
    /// preview yields to the committed line, exactly as before.
    func testAMinuteWithARealReadingIsNeverDropped() throws {
        let event = try Self.event(), state = try Self.held()
        let authority = BlendPreviewChartAuthority(eventId: Self.id, base: try XCTUnwrap(state?.baseFoldRevision))
        let reading: [String: Any] = ["timestamp": "2026-10-29T20:03:20+00:00", "home_probability": 0.64]
        let cases: [(String, EventHistoryResponse)] = [
            ("a source reading", try Self.pollAt52(extraReadings: ["kalshi": [reading]])),
            ("a reading from a source with no carry", try Self.pollAt52(extraReadings: ["espn": [reading]])),
            ("a sportsbook consensus reading", try Self.pollAt52(history: [reading])),
            ("a single sportsbook's reading", try Self.pollAt52(bookmakers: ["draftkings": [reading]])),
            ("no carried point at all", try Self.pollAt52(carriedBy: { _ in [:] })),
        ]
        for (name, served) in cases {
            XCTAssertNil(BlendPreview.syntheticEdgeToReplace(served, authority: authority,
                                                             at: Self.date(Self.previewAt)), name)
            XCTAssertEqual(Self.frames(served, event, state, now: 52.415), Self.primes, name)
            let end = try XCTUnwrap(Self.drawnEnd(served, event, state, now: 52.415), name)
            XCTAssertEqual(end.date, Self.date(Self.readAt52), name)
            XCTAssertEqual(end.probability, 0.63, name)
        }
    }

    func testTheOtherGuardsStillReturnCommittedTruth() throws {
        let event = try Self.event(), state = try Self.held()
        // A newer revision on the edge, another event's history, an edge that
        // is no pin, or a pin observed after the preview: the edge stays, so
        // its carry-forward minute stays too.
        for (name, served) in [("newer edge revision", try Self.pollAt52(edgeRev: 3)),
                               ("another event", try Self.pollAt52(eventId: 9)),
                               ("unpinned edge", try Self.pollAt52(pinned: false)),
                               ("pin observed after the preview",
                                try Self.pollAt52(edgeObserved: "2026-10-29T20:02:50+00:00"))] {
            XCTAssertEqual(Self.frames(served, event, state, now: 52.415), Self.primes, name)
            XCTAssertEqual(Self.drawnEnd(served, event, state, now: 52.415)?.probability, 0.63, name)
        }
        let served = try Self.pollAt52()
        // A pushed frame after the preview's observation.
        let later = Self.primes + [LiveBlendPoint(date: Self.date("2026-10-29T20:02:50+00:00"), homeProbability: 0.6)]
        XCTAssertEqual(Self.frames(served, event, state, now: 52.415, pushed: later), later)
        // No observation clock; expiry; a settled page; a settled payload.
        XCTAssertEqual(Self.frames(served, event, try Self.held(observed: nil), now: 52.415), Self.primes)
        XCTAssertEqual(Self.frames(served, event, state, now: 60.116), Self.primes)
        XCTAssertEqual(Self.frames(served, try Self.event(status: "completed"), state, now: 52.415), Self.primes)
        let settled = try Self.pollAt52(status: "completed")
        let settledFrames = Self.frames(settled, event, state, now: 52.415)
        XCTAssertEqual(OddsChartView.chartPoints(from: settled, liveFrames: settledFrames).map(\.date),
                       OddsChartView.chartPoints(from: settled).map(\.date), "settled means settled")
    }

    /// Only a folded preview replaces the edge on this client; a singleton's
    /// chart keeps master's rule.
    func testASingletonPreviewIsUnchanged() throws {
        let event = try Self.event(fold: ["1": 2]), served = try Self.pollAt52()
        let raw = """
        {"event_id":1,"p":0.71,"status":"live","display_observed_at":"\(Self.previewAt)",
         "preview":{"kind":"blend","epoch":3,"seq":5,"base_rev":2,"ttl_ms":60000}}
        """
        let singleton = BlendPreview.readerAfter(.empty, try XCTUnwrap(BlendPreviewFrame.decode(raw)),
                                                 eventId: Self.id, now: 0.116).held
        XCTAssertEqual(Self.headline(event, singleton, now: 52.415), 0.71)
        XCTAssertEqual(Self.frames(served, event, singleton, now: 52.415), Self.primes)
    }
}
