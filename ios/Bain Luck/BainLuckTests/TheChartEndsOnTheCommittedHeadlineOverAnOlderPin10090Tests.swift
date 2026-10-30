import XCTest
@testable import Bain_Luck

/// #10090 — the iPhone twin of web's #8749 rule (`appendHeroObservation`,
/// `frontend/lib/liveChartHistory.ts`): after a real commit, a later history
/// read whose pinned edge still carries an OLDER observed value must not end
/// the chart on that value while the headline prints the commit.
///
/// The history route pins its blend edge at the SERVE minute, and the price
/// there can be a detail hero cached a TTL earlier (`blend_edge_observed_at`
/// dates it). Specimen: the same lab pair as
/// `TheHeldChartKeepsThePreviewOverACarryForwardMinute10090Tests`
/// (`artifacts/calibration-10090-11742-pair-20261029`), with the 71% commit
/// landing at +30 s and the +52.4 s read still pinned from the 63% hero
/// observed at 20:02:37.7. The app drew the commit at its own time and then
/// went back to 63% at the read's pin, so the chart ended on 63% under a 71%
/// headline until a fresh read arrived.
@MainActor
final class TheChartEndsOnTheCommittedHeadlineOverAnOlderPin10090Tests: XCTestCase {
    private static let id = 1
    private static let previewAt = "2026-10-29T20:02:43.715334+00:00"
    private static let commitAt = "2026-10-29T20:03:13.700000+00:00"
    private static let olderObserved = "2026-10-29T20:02:37.742159+00:00"
    private static let carriedMinute = "2026-10-29T20:03:00+00:00"
    private static let readAt52 = "2026-10-29T20:03:36.081995+00:00"

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private static func date(_ stamp: String) -> Date { stamp.asDate! }

    // MARK: - Specimen

    private static func event(hero: Double = 0.63, rev: Int = 2, status: String = "live",
                              source: String = "blend",
                              observed: String? = olderObserved) throws -> EventDetail {
        var wire: [String: Any] = [
            "id": id, "home_team": "Home", "away_team": "Away", "sport": "tennis_atp", "status": status,
            "current_odds": ["home_probability": hero, "away_probability": 1 - hero],
            "hero_probability": hero, "hero_probability_away": 1 - hero, "hero_probability_source": source,
            "blend_fold_revision": ["1": rev, "2": 5]]
        if let observed { wire["hero_probability_observed_at"] = observed }
        return try decoder.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: wire))
    }

    /// The page after the commit: 71% at rev 3, dated by the frame that carried it.
    private static func committed(status: String = "live", source: String = "blend",
                                  observed: String? = commitAt) throws -> EventDetail {
        try event(hero: 0.71, rev: 3, status: status, source: source, observed: observed)
    }

    private static let primes = [
        LiveBlendPoint(date: date("2026-10-29T20:02:37.727545+00:00"), homeProbability: 0.48875),
        LiveBlendPoint(date: date(olderObserved), homeProbability: 0.63),
    ]
    private static let commit = LiveBlendPoint(date: date(commitAt), homeProbability: 0.71)
    private static let pushed = primes + [commit]

    private static func held() throws -> BlendPreviewState? {
        let raw = String(data: try JSONSerialization.data(withJSONObject: [
            "event_id": id, "p": 0.71, "p_away": 0.29, "sport": "tennis_atp", "status": "live",
            "display_observed_at": previewAt,
            "preview": ["kind": "blend", "epoch": 3, "seq": 5, "base_rev": 2, "ttl_ms": 60_000,
                        "folded_version": 1, "origin_event_id": id, "base_fold_revision": ["1": 2, "2": 5],
                        "pending_entries_version": 2, "pending_entries_authority": "event-ledger-v1"],
        ] as [String: Any]), encoding: .utf8)!
        return BlendPreview.readerAfter(.empty, try XCTUnwrap(BlendPreviewFrame.decode(raw)), eventId: id, now: 0.116).held
    }

    private static let realSources: [String: [[String: Any]]] = [
        "kalshi": [["timestamp": "2026-10-29T20:01:10+00:00", "home_probability": 0.465],
                   ["timestamp": "2026-10-29T20:02:37.727545+00:00", "home_probability": 0.6]],
        "polymarket": [["timestamp": "2026-10-29T20:01:10+00:00", "home_probability": 0.3775],
                       ["timestamp": "2026-10-29T20:02:37.742159+00:00", "home_probability": 0.66]],
    ]

    private static func served(_ line: [(String, Double)], observed: String?, rev: Int?,
                               sources: [String: [[String: Any]]], eventId: Int = id,
                               status: String = "live", pinned: Bool = true) throws -> EventHistoryResponse {
        var payload: [String: Any] = [
            "event_id": eventId, "home_team": "Home", "away_team": "Away", "status": status, "history": [],
            "aggregate_line": line.map { ["timestamp": $0.0, "home_probability": $0.1] },
            "blend_edge_pinned": pinned, "win_prob_history": sources]
        if let observed { payload["blend_edge_observed_at"] = observed }
        if let rev { payload["blend_edge_fold_revision"] = ["1": rev, "2": 5] }
        return try decoder.decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    private static func bootRead() throws -> EventHistoryResponse {
        try served([("2026-10-29T20:01:00+00:00", 0.42125), ("2026-10-29T20:02:36.425768+00:00", 0.42125)],
                   observed: "2026-10-29T20:02:23.834954+00:00", rev: 0,
                   sources: realSources.mapValues { [$0[0]] })
    }

    private static func pollAt20() throws -> EventHistoryResponse {
        try served([("2026-10-29T20:01:00+00:00", 0.42125), ("2026-10-29T20:02:00+00:00", 0.63),
                    ("2026-10-29T20:03:04.064256+00:00", 0.42125)],
                   observed: "2026-10-29T20:02:23.834954+00:00", rev: 0, sources: realSources)
    }

    /// The +52.4 s read after the commit: its pin still carries the 63% hero
    /// observed at 20:02:37.7 (rev 2), and both sources are carried to the read.
    private static func staleAt52(edgeRev: Int? = 2, edgeValue: Double = 0.63, eventId: Int = id,
                                  status: String = "live", pinned: Bool = true,
                                  edgeObserved: String? = olderObserved,
                                  lateReading: Bool = false) throws -> EventHistoryResponse {
        var sources = realSources
        for (name, carry) in [("kalshi", 0.6), ("polymarket", 0.66)] {
            sources[name]?.append(["timestamp": "2026-10-29T20:03:36+00:00", "home_probability": carry,
                                   "live_edge": true])
        }
        var line: [(String, Double)] = [("2026-10-29T20:01:00+00:00", 0.42125), ("2026-10-29T20:02:00+00:00", 0.63),
                                        (carriedMinute, 0.63)]
        if lateReading {
            // A real reading the read holds after the commit: the line knows something newer.
            sources["kalshi"]?.append(["timestamp": "2026-10-29T20:03:20+00:00", "home_probability": 0.64])
            line.append(("2026-10-29T20:03:20+00:00", 0.64))
        }
        line.append((readAt52, edgeValue))
        return try served(line, observed: edgeObserved, rev: edgeRev, sources: sources,
                          eventId: eventId, status: status, pinned: pinned)
    }

    // MARK: - Reading what the page prints

    private static func headline(_ event: EventDetail, _ state: BlendPreviewState?, now: TimeInterval) -> Double? {
        BlendPreview.overlay(event, state, now: now).heroProbability
    }

    private static func frames(_ served: EventHistoryResponse, _ event: EventDetail, _ state: BlendPreviewState?,
                               now: TimeInterval, pushed: [LiveBlendPoint] = pushed) -> [LiveBlendPoint] {
        BlendPreview.chartFrames(pushed, history: served, state: state, held: event, now: now)
    }

    private static func drawnBlend(_ served: EventHistoryResponse, _ frames: [LiveBlendPoint]) -> [ChartDataPoint] {
        OddsChartView.chartPoints(from: served, liveFrames: frames)
            .filter { $0.source == "aggregate" }
            .sorted { $0.date < $1.date }
    }

    private static func drawnEnd(_ served: EventHistoryResponse, _ event: EventDetail,
                                 _ state: BlendPreviewState?, now: TimeInterval,
                                 pushed: [LiveBlendPoint] = pushed) -> ChartDataPoint? {
        drawnBlend(served, frames(served, event, state, now: now, pushed: pushed)).last
    }

    // MARK: - The class

    func testAReadWhosePinPredatesTheCommitDoesNotEndTheChartOnIt() throws {
        let event = try Self.committed(), state = try Self.held(), served = try Self.staleAt52()
        XCTAssertNil(BlendPreview.displayed(state, held: event, now: 52.415), "the commit retired the preview")
        XCTAssertEqual(Self.headline(event, state, now: 52.415), 0.71)
        XCTAssertEqual(Self.frames(served, event, state, now: 52.415).last?.homeProbability, 0.71,
                       "the frames the page hands its chart")
        let end = try XCTUnwrap(Self.drawnEnd(served, event, state, now: 52.415))
        XCTAssertEqual(end.date, Self.date(Self.readAt52), "the line still ends at the read's pin")
        XCTAssertEqual(end.probability, 0.71, "the line the chart draws")
    }

    /// Whichever payload carried the headline: a commit adopted from a poll,
    /// with no frame of its own, ends the line the same way.
    func testAHeadlineWithNoFrameOfItsOwnStillEndsTheLine() throws {
        let event = try Self.committed(), served = try Self.staleAt52()
        XCTAssertEqual(Self.drawnEnd(served, event, nil, now: 52.415, pushed: Self.primes)?.probability, 0.71)
        XCTAssertEqual(Self.drawnEnd(served, event, nil, now: 52.415, pushed: [])?.probability, 0.71)
    }

    func testTheProjectionRevaluesOnlyThePin() throws {
        let event = try Self.committed(), served = try Self.staleAt52()
        let copy = served
        let before = OddsChartView.chartPoints(from: served, liveFrames: Self.pushed)
        let shown = OddsChartView.chartPoints(from: served, liveFrames: Self.frames(served, event, nil, now: 52.415))
        func venue(_ points: [ChartDataPoint]) -> [String] {
            points.filter { $0.source != "aggregate" }.map { "\($0.source)@\($0.date.timeIntervalSince1970)=\($0.probability)" }
        }
        XCTAssertEqual(venue(shown), venue(before), "every venue series is untouched")
        XCTAssertFalse(venue(before).isEmpty)
        let blend = shown.filter { $0.source == "aggregate" }.sorted { $0.date < $1.date }
        XCTAssertEqual(blend.filter { $0.date == Self.date(Self.readAt52) }.map(\.probability), [0.71],
                       "one point at the pin, carrying the headline")
        XCTAssertTrue(blend.contains { $0.date == Self.date(Self.commitAt) && $0.probability == 0.71 },
                      "the commit stays at its own time")
        // Before the commit the line is master's, plus the read's 20:03:00
        // bucket, which stays at its minute instead of moving onto the pin past
        // the value that replaced it (`servedBlendAtEvidenceTime`).
        func early(_ points: [ChartDataPoint]) -> [String] {
            points.filter { $0.source == "aggregate" && $0.date < Self.date(Self.commitAt) }
                .map { "\($0.date.timeIntervalSince1970)=\($0.probability)" }.sorted()
        }
        XCTAssertEqual(early(shown),
                       (early(before) + ["\(Self.date(Self.carriedMinute).timeIntervalSince1970)=0.63"]).sorted(),
                       "the readings before the commit stay")
        XCTAssertEqual(blend.filter { $0.date < Self.date(Self.commitAt) }.map(\.probability),
                       [0.42125, 0.48875, 0.63, 0.63, 0.63])
        XCTAssertEqual(served, copy, "the served history is never written")
    }

    /// A commit observed before the read's carry-forward minute: that minute
    /// carried the older value too, so it goes with the pin's value. Kept, the
    /// line would dip back to 63% between the commit and the pin.
    func testTheCarryForwardMinuteAfterTheHeadlineGoesWithTheOlderValue() throws {
        let early = "2026-10-29T20:02:50+00:00"
        let event = try Self.committed(observed: early), served = try Self.staleAt52()
        let pushed = Self.primes + [LiveBlendPoint(date: Self.date(early), homeProbability: 0.71)]
        let blend = Self.drawnBlend(served, Self.frames(served, event, nil, now: 52.415, pushed: pushed))
        XCTAssertEqual(blend.last?.probability, 0.71)
        XCTAssertEqual(blend.filter { $0.date >= Self.date(early) }.map(\.probability), [0.71, 0.71],
                       "the commit, then the pin; no dip through the carried minute")
    }

    /// The page over 0–70 s: the preview, its commit at +30 s, and each history
    /// poll at its specimen time. Every 100 ms the chart's end must be the
    /// number the headline shows.
    func testHeadlineAndChartAgreeEvery100msFrom0To70sThroughTheCommit() throws {
        let before = try Self.event(), after = try Self.committed(), held = try Self.held()
        let polls: [(TimeInterval, EventHistoryResponse)] = [
            (-6, try Self.bootRead()), (20.416, try Self.pollAt20()), (52.415, try Self.staleAt52()),
        ]
        var disagreements: [String] = []
        for tick in 0...700 {
            let now = Double(tick) / 10
            let served = try XCTUnwrap(polls.last { $0.0 <= now }?.1)
            let state = now >= 0.116 ? held : nil
            let event = now >= 30 ? after : before
            let pushed = now >= 30 ? Self.pushed : Self.primes
            let headline = try XCTUnwrap(Self.headline(event, state, now: now))
            let frames = Self.frames(served, event, state, now: now, pushed: pushed)
            let drawn = Self.drawnBlend(served, frames).last?.probability
            if frames.last?.homeProbability != headline || drawn != headline {
                disagreements.append("\(now) s: headline \(headline), frames \(frames.last?.homeProbability ?? -1), drawn \(drawn ?? -1)")
            }
        }
        XCTAssertEqual(disagreements.first, nil, "\(disagreements.count) of 701 ticks disagree")
    }

    /// A fresh read that already holds the commit needs nothing: the frames are
    /// exactly what the stream pushed.
    func testAFreshReadThatHoldsTheCommitIsUntouched() throws {
        let event = try Self.committed()
        let fresh = try Self.staleAt52(edgeRev: 3, edgeValue: 0.71, edgeObserved: Self.commitAt)
        XCTAssertEqual(Self.frames(fresh, event, nil, now: 52.415), Self.pushed)
        XCTAssertEqual(Self.drawnEnd(fresh, event, nil, now: 52.415)?.probability, 0.71)
    }

    // MARK: - Every guard still refuses

    /// Each of these leaves the pin as served: the frames are exactly what was
    /// pushed and the line ends on the read's 63%.
    func testEveryGuardLeavesThePinAsServed() throws {
        let event = try Self.committed()
        let cases: [(String, EventHistoryResponse, EventDetail)] = [
            ("pin observed at the commit's own clock", try Self.staleAt52(edgeObserved: Self.commitAt), event),
            ("pin observed after the commit",
             try Self.staleAt52(edgeObserved: "2026-10-29T20:03:20+00:00"), event),
            ("pin with no observation clock", try Self.staleAt52(edgeObserved: nil), event),
            ("pin at a newer revision than the headline", try Self.staleAt52(edgeRev: 4), event),
            ("pin with no revision", try Self.staleAt52(edgeRev: nil), event),
            ("unpinned edge", try Self.staleAt52(pinned: false), event),
            ("another event's read", try Self.staleAt52(eventId: 9), event),
            ("a real reading after the commit", try Self.staleAt52(lateReading: true), event),
            ("headline with no observation clock", try Self.staleAt52(), try Self.committed(observed: nil)),
            ("headline that is not the blend", try Self.staleAt52(), try Self.committed(source: "kalshi")),
            ("headline observed after the read",
             try Self.staleAt52(), try Self.committed(observed: "2026-10-29T20:03:40+00:00")),
        ]
        for (name, served, held) in cases {
            XCTAssertEqual(Self.frames(served, held, nil, now: 52.415), Self.pushed, name)
            let end = try XCTUnwrap(Self.drawnEnd(served, held, nil, now: 52.415), name)
            XCTAssertEqual(end.date, Self.date(Self.readAt52), name)
            XCTAssertEqual(end.probability, 0.63, name)
        }
    }

    func testASettledPageOrPayloadIsNeverRevalued() throws {
        let served = try Self.staleAt52()
        XCTAssertEqual(Self.frames(served, try Self.committed(status: "completed"), nil, now: 52.415), Self.pushed)
        let settled = try Self.staleAt52(status: "completed")
        let frames = Self.frames(settled, try Self.committed(), nil, now: 52.415)
        XCTAssertEqual(OddsChartView.chartPoints(from: settled, liveFrames: frames).map(\.probability),
                       OddsChartView.chartPoints(from: settled).map(\.probability), "settled means settled")
    }

    /// A headline equal to the pin has nothing to replace.
    func testAHeadlineEqualToThePinAddsNothing() throws {
        let served = try Self.staleAt52(edgeValue: 0.71)
        XCTAssertEqual(Self.frames(served, try Self.committed(), nil, now: 52.415), Self.pushed)
    }

    /// The chart re-checks against ITS payload: a projection made for one read
    /// does nothing to another.
    func testTheChartRechecksTheProjectionAgainstItsOwnPayload() throws {
        let event = try Self.committed()
        let projected = Self.frames(try Self.staleAt52(), event, nil, now: 52.415)
        XCTAssertNotEqual(projected, Self.pushed, "a projection was made")
        for (name, other) in [("newer revision", try Self.staleAt52(edgeRev: 4)),
                              ("another event", try Self.staleAt52(eventId: 9)),
                              ("pin observed after the commit",
                               try Self.staleAt52(edgeObserved: "2026-10-29T20:03:20+00:00")),
                              ("a real reading after the commit", try Self.staleAt52(lateReading: true))] {
            XCTAssertEqual(Self.drawnBlend(other, projected).map(\.probability),
                           Self.drawnBlend(other, Self.pushed).map(\.probability), name)
        }
    }
}
