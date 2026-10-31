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
        // the value that replaced it: a carry-forward minute holds no reading
        // (`servedBlendAtEvidenceTime`).
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

    /// The timing seam's chart mark names the point the chart DRAWS (b94:
    /// committed chart marks named the buffer's last frame, under `-`, while
    /// the line ended on this pin). The re-valued pin at its own time, with
    /// the headline's value under the revision the marker carries, observed
    /// at the headline's clock; the commit at +30 s is not the end.
    func testTheTimingSeamNamesTheRevaluedPinUnderTheMarkersOwnRevision() throws {
        let event = try Self.committed(), served = try Self.staleAt52()
        let frames = Self.frames(served, event, nil, now: 52.415)
        let drawn = try XCTUnwrap(Self.drawnBlend(served, frames).last)
        let shown = LiveTimingSeam.presented(committed: event, headline: event, observed: Self.date(Self.commitAt),
                                             chartEnd: frames.last, projected: false, preview: nil, history: served)
        XCTAssertEqual(shown.chartEdge, drawn.date, "the pin's time, where the line ends")
        XCTAssertEqual(shown.chartEdge, Self.date(Self.readAt52))
        XCTAssertEqual(shown.chartProbability, drawn.probability)
        XCTAssertEqual(shown.chartBasis, "rev:1=3;2=5", "the revision that authorized the value drawn there")
        XCTAssertEqual(shown.chartBasis, shown.headlineBasis, "the marker is the headline's own value")
        XCTAssertEqual(shown.chartObserved, Self.date(Self.commitAt), "observed at the headline's clock, not the pin's")

        // A read that no longer re-values that pin (it already prints 71%)
        // draws no marker value, so the seam names no end at the marker's time.
        let printed = try Self.staleAt52(edgeValue: 0.71)
        XCTAssertNil(LiveTimingSeam.drawnChartEnd(frames.last, projected: false, preview: nil, history: printed).edge)
        XCTAssertNil(LiveTimingSeam.drawnChartEnd(frames.last, projected: false, preview: nil, history: nil).edge)
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

    /// Latency's case A on 58729fb2 (#11105's out-and-back, in the headline's
    /// own minute): the read's 20:03:00 bucket is a REAL minute that already
    /// holds the 71% commit, and the stream pushed 62% and 66% inside that
    /// minute before the commit at +52.5 s; the pin at 20:04:15 still carries
    /// the 63% observed before it. Left at its minute start, the bucket drew
    /// 71% 52.5 s early and the line dipped back through 62/66%, with the
    /// 20:02:00 bucket's end on the same instant. It moves to the headline's
    /// clock instead, which its evidence cannot be later than: the pin's
    /// revision is covered by the headline's (`olderPinUnderHeadline`).
    func testARealBucketInTheHeadlinesMinuteMeetsTheHeadlineAtItsClock() throws {
        let blend = try Self.inMinute(bucket: 0.71)
        XCTAssertEqual(blend.map(\.text), ["0.0=0.6", "10.0=0.62", "30.0=0.66", "52.5=0.71", "75.0=0.71"],
                       "no 71% before the commit, no dip back, one point per instant")
        XCTAssertFalse(blend.contains { $0.point.probability == 0.71 && $0.offset < 52.5 },
                       "the line never shows the commit before the headline did")
    }

    /// The same minute when the read's bucket holds 66%, a value the stream
    /// pushed at +30 s before the commit: it meets that frame. At its minute
    /// start it drew the out-and-back 66 → 62 → 66; at the headline's clock it
    /// would win the tie and draw the commit 22.5 s late.
    func testABucketThatPredatesTheCommitMeetsTheFrameThatPrintedIt() throws {
        let blend = try Self.inMinute(bucket: 0.66)
        XCTAssertEqual(blend.map(\.text), ["0.0=0.6", "10.0=0.62", "30.0=0.66", "52.5=0.71", "75.0=0.71"])
    }

    private static func inMinute(bucket: Double) throws -> [(offset: TimeInterval, text: String, point: ChartDataPoint)] {
        let minute = date("2026-10-29T20:03:00+00:00")
        func at(_ seconds: TimeInterval) -> String {
            [-60: "20:02:00", -30: "20:02:30", -20: "20:02:40", 0: "20:03:00", 30: "20:03:30",
             52.5: "20:03:52.500000", 75: "20:04:15"].mapValues { "2026-10-29T\($0)+00:00" }[seconds]!
        }
        // The bucket's own reading: the commit's input, or the 66% pushed at +30 s.
        let reading = at(bucket == 0.71 ? 52.5 : 30)
        let sources = ["kalshi", "polymarket"].reduce(into: [String: [[String: Any]]]()) {
            $0[$1] = [["timestamp": at(-30), "home_probability": 0.6],
                      ["timestamp": reading, "home_probability": bucket],
                      ["timestamp": at(75), "home_probability": bucket, "live_edge": true]]
        }
        let read = try served([(at(-60), 0.60), (at(0), bucket), (at(75), 0.63)],
                              observed: at(-20), rev: 2, sources: sources)
        let event = try committed(observed: at(52.5))
        let pushed = [LiveBlendPoint(date: minute.addingTimeInterval(10), homeProbability: 0.62),
                      LiveBlendPoint(date: minute.addingTimeInterval(30), homeProbability: 0.66),
                      LiveBlendPoint(date: minute.addingTimeInterval(52.5), homeProbability: 0.71)]
        return drawnBlend(read, frames(read, event, nil, now: 52.415, pushed: pushed)).map {
            let offset = $0.date.timeIntervalSince(minute)
            return (offset, "\(offset)=\($0.probability)", $0)
        }
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
