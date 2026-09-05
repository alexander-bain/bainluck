import XCTest
@testable import Bain_Luck

/// #3196 (child of #1168, Moments Engine consumer 3) — the win-probability chart draws
/// the moments the server already computed, so a leap in the line says what caused it.
///
/// These pin the pure transforms (SwiftUI bodies aren't rendered in tests), and each
/// one exists because the opposite behaviour is a defect somebody would otherwise
/// ship:
///
///  1. **A bad moment must not blank the chart.** `moments` lives inside
///     `EventHistoryResponse`; a row that throws costs the reader the whole curve to
///     gain nothing (gotcha #42).
///  2. **A moment outside the drawn range must not be clamped onto the edge**, which
///     would report a pregame swing as something that happened at first pitch.
///  3. **A marker's y is a real snapshot**, never interpolated (C43 P1).
///  4. **There is exactly one confidence gate and it is the server's.**
final class OddsChartMomentsTests: XCTestCase {

    private func history(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private let base = Date(timeIntervalSince1970: 1_757_000_000)

    /// A primary ("aggregate") line: one point per `minute`, probability from `probs`.
    private func line(_ probs: [Double], startMinute: Int = 0) -> [ChartDataPoint] {
        probs.enumerated().map { i, p in
            ChartDataPoint(
                date: base.addingTimeInterval(TimeInterval((startMinute + i) * 60)),
                probability: p,
                source: "aggregate"
            )
        }
    }

    private func moment(minute: Int, label: String? = "Team score — win prob +20.0 pts",
                        delta: Double? = 0.2, period: String? = "Bottom 3rd",
                        confidence: Double? = 0.9) -> GameMomentPoint {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        // Assembled as named locals rather than inline in the literal: the
        // type-checker cannot solve a multi-line interpolation with this many
        // optional maps in it ("failed to produce diagnostic for expression").
        let ts: String = iso.string(from: base.addingTimeInterval(TimeInterval(minute * 60)))
        let labelJSON: String = label.map { "\"\($0)\"" } ?? "null"
        let confidenceJSON: String = confidence.map { "\($0)" } ?? "null"
        let deltaJSON: String = delta.map { "\($0)" } ?? "null"
        let periodJSON: String = period.map { "\"\($0)\"" } ?? "null"
        return decoded("""
        {
          "ts": "\(ts)",
          "label": \(labelJSON),
          "confidence": \(confidenceJSON),
          "moment_type": "score",
          "actor_team": "Team",
          "prob_delta": \(deltaJSON),
          "period": \(periodJSON)
        }
        """)
    }

    private func decoded(_ json: String) -> GameMomentPoint {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        // Force-try is deliberate: a fixture that cannot decode is a broken test, and
        // a nil-returning helper would let a typo silently produce "0 moments" —
        // which is also what several of these tests assert, so it would pass.
        return try! dec.decode(GameMomentPoint.self, from: Data(json.utf8))
    }

    // MARK: - 1. A bad row is dropped, never thrown

    /// The whole reason `GameMomentPoint` is all-optional. A history payload carrying
    /// a moment with a null `ts` and a moment with a null `label` must still decode,
    /// and must still draw its line.
    func testNullFieldsInAMomentDoNotFailTheHistoryDecode() throws {
        let h = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-09-05T02:10:00Z", "home_probability": 0.6}],
          "win_prob_history": {
            "espn": [{"timestamp": "2026-09-05T02:10:00Z", "home_probability": 0.61}]
          },
          "aggregate_line": [
            {"timestamp": "2026-09-05T02:10:00Z", "home_probability": 0.6},
            {"timestamp": "2026-09-05T02:20:00Z", "home_probability": 0.9}
          ],
          "moments": [
            {"ts": null, "label": "no timestamp", "confidence": 0.9},
            {"ts": "2026-09-05T02:20:00Z", "label": null, "confidence": 0.9},
            {"ts": "2026-09-05T02:20:00Z", "label": "   ", "confidence": 0.9},
            {"ts": "not a date", "label": "unparseable", "confidence": 0.9},
            {"ts": "2026-09-05T02:20:00Z", "label": "Real — win prob +30.0 pts",
             "prob_delta": 0.3, "period": "Top 2nd", "confidence": 0.9}
          ]
        }
        """)
        XCTAssertEqual(h.moments?.count, 5, "every row decodes; the drop happens later")

        let points = OddsChartView.chartPoints(from: h)
        XCTAssertFalse(points.isEmpty, "a bad moment must never cost the reader the curve")

        let drawn = OddsChartView.chartMoments(from: h.moments, points: points)
        XCTAssertEqual(drawn.map(\.label), ["Real — win prob +30.0 pts"],
                       "four unusable rows dropped, the usable one kept")
    }

    /// Absent key (an older cached payload) is not an error and not a moment.
    func testMissingMomentsKeyDrawsNothing() throws {
        let h = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-09-05T02:10:00Z", "home_probability": 0.6}]
        }
        """)
        XCTAssertNil(h.moments)
        XCTAssertTrue(OddsChartView.chartMoments(from: h.moments,
                                                 points: OddsChartView.chartPoints(from: h)).isEmpty)
    }

    func testNoPointsDrawsNoMoments() {
        XCTAssertTrue(OddsChartView.chartMoments(from: [moment(minute: 1)], points: []).isEmpty,
                      "a moment with no line to sit on has no y and is not drawable")
    }

    // MARK: - 2. Out of range is dropped, not clamped

    /// `filterPoints` narrows the line under "Since Start". A pregame moment then has
    /// no in-range anchor, and drawing it at the left edge would say the swing
    /// happened at first pitch.
    func testMomentBeforeTheDrawnRangeIsDroppedNotClamped() {
        let points = line([0.5, 0.6, 0.7], startMinute: 10)   // minutes 10, 11, 12
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 2, label: "Pregame line move"),
                   moment(minute: 11, label: "In range")],
            points: points
        )
        XCTAssertEqual(drawn.map(\.label), ["In range"])
    }

    func testMomentAfterTheDrawnRangeIsDropped() {
        let points = line([0.5, 0.6])                          // minutes 0, 1
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 90, label: "After the last snapshot")],
            points: points
        )
        XCTAssertTrue(drawn.isEmpty)
    }

    func testMomentsExactlyOnTheBoundsAreKept() {
        let points = line([0.5, 0.6, 0.7])                     // minutes 0, 1, 2
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 0, label: "first"), moment(minute: 2, label: "last")],
            points: points
        )
        XCTAssertEqual(drawn.map(\.label), ["first", "last"],
                       "an inclusive range — the first and last snapshots are drawn points")
    }

    // MARK: - 3. The y is a real snapshot

    /// The payload carries no y for a moment. Placing it between two snapshots would
    /// invent a probability nobody observed — the same rule that makes the line
    /// `.linear` rather than smoothed.
    func testMomentSitsOnTheNearestRealSnapshotNeverBetweenTwo() {
        let points = line([0.30, 0.80])                        // minutes 0 and 1
        // 40s past minute 0 — nearer to minute 1 (20s) than to minute 0 (40s).
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        let raw = decoded("""
        {"ts": "\(iso.string(from: base.addingTimeInterval(40)))",
         "label": "Score — win prob +50.0 pts", "prob_delta": 0.5, "confidence": 1.0}
        """)
        let drawn = OddsChartView.chartMoments(from: [raw], points: points)
        XCTAssertEqual(drawn.count, 1)
        XCTAssertEqual(drawn[0].probability, 0.80, accuracy: 1e-9,
                       "0.55 would be an interpolation the chart never observed")
    }

    /// The anchor is on the PRIMARY line. A non-primary source's snapshot must not
    /// pull the marker off the curve the reader is looking at.
    func testAnchorIgnoresNonPrimarySources() throws {
        var points = line([0.30, 0.80])
        points.append(ChartDataPoint(date: base.addingTimeInterval(40),
                                     probability: 0.05, source: "espn"))
        let drawn = OddsChartView.chartMoments(from: [moment(minute: 1)], points: points)
        XCTAssertEqual(try XCTUnwrap(drawn.first).probability, 0.80, accuracy: 1e-9)
    }

    /// The in-range test is scoped to the primary line too. ESPN polling that runs
    /// past our blend must not admit a late moment which then anchors to the blend's
    /// final point — an out-of-range clamp dressed up as an in-range hit.
    func testAMomentPastThePrimaryLineIsDroppedEvenWhenAnotherSourceCoversIt() {
        var points = line([0.30, 0.80])                       // aggregate: minutes 0–1
        points.append(ChartDataPoint(date: base.addingTimeInterval(20 * 60),
                                     probability: 0.9, source: "espn"))
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 19, label: "after our last blend snapshot")],
            points: points
        )
        XCTAssertTrue(drawn.isEmpty)
    }

    // MARK: - 4. One confidence gate, and it is the server's

    /// `routes/events.py` selects `confidence >= 0.5` and honours the
    /// `moments:surface_enabled` kill switch. A second client threshold would narrow a
    /// decision the server owns and would need an App Store release to widen again.
    func testALowButServerApprovedConfidenceStillDraws() {
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 1, label: "Barely confident", confidence: 0.51)],
            points: line([0.4, 0.5, 0.6])
        )
        XCTAssertEqual(drawn.map(\.label), ["Barely confident"],
                       "the client draws what it is sent — do not add a second gate here")
    }

    /// A moment with no confidence at all was still gated by the server before it was
    /// serialised; the client has no basis to second-guess it.
    func testAbsentConfidenceStillDraws() {
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 1, confidence: nil)],
            points: line([0.4, 0.5, 0.6])
        )
        XCTAssertEqual(drawn.count, 1)
    }

    /// The kill switch works by construction: server sends [], client draws nothing.
    func testEmptyMomentsArrayDrawsNothing() {
        XCTAssertTrue(OddsChartView.chartMoments(from: [], points: line([0.4, 0.5])).isEmpty)
    }

    // MARK: - Ordering and the legibility ceiling

    func testDrawnMomentsAreChronological() {
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 3, label: "third"),
                   moment(minute: 1, label: "first"),
                   moment(minute: 2, label: "second")],
            points: line([0.1, 0.2, 0.3, 0.4])
        )
        XCTAssertEqual(drawn.map(\.label), ["first", "second", "third"])
    }

    /// The cap is a legibility ceiling, not a guard against a measured defect (the
    /// most seen on an MLB game is 9). It must not fire below its own bound —
    /// a cap that trims a normal game is a data-loss defect wearing a tidy number.
    func testTheCapDoesNotFireAtOrBelowItsBound() {
        let n = MomentMarkerGeometry.maxMarkers
        XCTAssertGreaterThan(n, 9, "must clear the largest measured real game (9 on 2026-09-05)")
        let raws = (1...n).map { moment(minute: $0, label: "m\($0)", delta: 0.01 * Double($0)) }
        let drawn = OddsChartView.chartMoments(from: raws, points: line(Array(repeating: 0.5, count: n + 2)))
        XCTAssertEqual(drawn.count, n)
    }

    /// Past the ceiling the SMALLEST swings go, and the survivors stay in game order.
    func testOverTheCapKeepsTheBiggestSwingsInChronologicalOrder() {
        let n = MomentMarkerGeometry.maxMarkers
        // n+1 moments; the one at minute 1 has the smallest swing, so it is the drop.
        var raws = [moment(minute: 1, label: "tiny", delta: 0.001)]
        raws += (2...(n + 1)).map { moment(minute: $0, label: "m\($0)", delta: 0.5) }
        let drawn = OddsChartView.chartMoments(from: raws,
                                               points: line(Array(repeating: 0.5, count: n + 3)))
        XCTAssertEqual(drawn.count, n)
        XCTAssertFalse(drawn.contains { $0.label == "tiny" })
        XCTAssertEqual(drawn.map(\.date), drawn.map(\.date).sorted())
    }

    /// `prob_delta` is optional. A moment without one must not be treated as the
    /// biggest swing, and must not crash the comparison.
    func testMomentWithoutADeltaIsNeverTheHeadline() {
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 1, label: "no delta", delta: nil),
                   moment(minute: 2, label: "real swing", delta: 0.4)],
            points: line([0.1, 0.2, 0.3, 0.4])
        )
        XCTAssertEqual(OddsChartView.headlineMoment(in: drawn)?.label, "real swing")
    }

    // MARK: - The caption

    func testHeadlineIsTheLargestAbsoluteSwingInEitherDirection() {
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 1, label: "up small", delta: 0.12),
                   moment(minute: 2, label: "down big", delta: -0.62),
                   moment(minute: 3, label: "up medium", delta: 0.30)],
            points: line([0.1, 0.2, 0.3, 0.4])
        )
        XCTAssertEqual(OddsChartView.headlineMoment(in: drawn)?.label, "down big",
                       "a collapse is as much the story as a surge")
    }

    /// One moment is not a comparison — calling it the "biggest" overstates what the
    /// chart knows.
    func testKickerWordingByCount() {
        XCTAssertNil(OddsChartView.momentCaptionKicker(count: 0))
        XCTAssertEqual(OddsChartView.momentCaptionKicker(count: 1), "Key moment")
        XCTAssertEqual(OddsChartView.momentCaptionKicker(count: 2), "Biggest swing")
        XCTAssertEqual(OddsChartView.momentCaptionKicker(count: 9), "Biggest swing")
    }

    func testNoMomentsMeansNoHeadlineAndNoKicker() {
        XCTAssertNil(OddsChartView.headlineMoment(in: []))
        XCTAssertNil(OddsChartView.momentCaptionKicker(count: 0),
                     "the caption renders no row at all — nothing beats unhelpful (#871)")
    }

    /// The server already wrote the sentence, swing included. The client prefixes the
    /// period and changes nothing else — no recomputed percentage that could disagree
    /// with the label beside it.
    func testCaptionTextIsThePeriodThenTheServersOwnLabel() {
        let m = ChartMoment(date: base, label: "San Diego Padres score — win prob +93.5 pts",
                            probability: 0.99, probDelta: 0.935, period: "Bottom 10th")
        XCTAssertEqual(OddsChartView.momentCaptionText(for: m),
                       "Bottom 10th · San Diego Padres score — win prob +93.5 pts")
    }

    func testCaptionTextOmitsTheSeparatorWhenThereIsNoPeriod() {
        for period in [nil, ""] as [String?] {
            let m = ChartMoment(date: base, label: "Team score — win prob +20.0 pts",
                                probability: 0.7, probDelta: 0.2, period: period)
            XCTAssertEqual(OddsChartView.momentCaptionText(for: m),
                           "Team score — win prob +20.0 pts",
                           "a dangling ' · ' is a visible bug")
        }
    }

    // MARK: - The scrub read-out

    func testScrubbingOntoAMomentNamesItAfterTheNumbers() {
        let points = line([0.4, 0.9])
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 1, label: "Team score — win prob +50.0 pts")],
            points: points
        )
        let value = OddsChartView.accessibilityValue(
            dataPoints: points, selectedDate: base.addingTimeInterval(60),
            homeShort: "LAD", awayShort: "WSH", moments: drawn
        )
        XCTAssertTrue(value.hasPrefix("LAD 90%, WSH 10%"), "the number leads: \(value)")
        XCTAssertTrue(value.hasSuffix("Team score — win prob +50.0 pts"),
                      "the cause trails: \(value)")
    }

    /// Beyond the match window the reader is on ordinary line. Naming a moment from
    /// elsewhere in the game would be worse than saying nothing.
    func testScrubbingAwayFromAMomentNamesNothing() {
        let points = line([0.4, 0.5, 0.6, 0.7, 0.8])
        let drawn = OddsChartView.chartMoments(from: [moment(minute: 0, label: "early")],
                                               points: points)
        let far = base.addingTimeInterval(4 * 60)
        let value = OddsChartView.accessibilityValue(
            dataPoints: points, selectedDate: far,
            homeShort: "H", awayShort: "A", moments: drawn
        )
        XCTAssertFalse(value.contains("early"), value)
    }

    func testTheMatchWindowIsTheOneUsedForScoringPlays() {
        XCTAssertEqual(OddsChartView.momentMatchWindowSeconds, 60,
                       "one definition of 'at this point in the game', not two")
    }

    func testNearestMomentPrefersTheCloserOfTwoInsideTheWindow() {
        let points = line([0.3, 0.5, 0.7])
        let drawn = OddsChartView.chartMoments(
            from: [moment(minute: 0, label: "earlier"), moment(minute: 1, label: "later")],
            points: points
        )
        let at = base.addingTimeInterval(50)   // 50s from "earlier", 10s from "later"
        XCTAssertEqual(OddsChartView.nearestMoment(to: at, in: drawn)?.label, "later")
    }

    /// The resting read-out (nothing scrubbed) is unchanged — it reports the latest
    /// snapshot, not a moment. Pinned because adding the headline here would make
    /// VoiceOver announce a mid-game swing as the current state.
    func testRestingReadoutDoesNotNameAMoment() {
        let points = line([0.4, 0.9])
        let drawn = OddsChartView.chartMoments(from: [moment(minute: 1, label: "swing")],
                                               points: points)
        let value = OddsChartView.accessibilityValue(
            dataPoints: points, selectedDate: nil,
            homeShort: "H", awayShort: "A", moments: drawn
        )
        XCTAssertFalse(value.contains("swing"), value)
    }

    // MARK: - The measured production shape

    /// The 2026-09-05 Padres–Yankees payload (event 15302915), trimmed: four moments,
    /// zero scoring plays. This is the specimen #3196 was filed on — the walk-off the
    /// phone used to draw as an unexplained vertical wall.
    func testTheWalkOffSpecimenDrawsFourMarkersAndNamesTheWalkOff() throws {
        let h = try history("""
        {
          "event_id": 15302915, "home_team": "San Diego Padres", "away_team": "New York Yankees",
          "status": "completed",
          "history": [{"timestamp": "2026-09-05T02:10:00Z", "home_probability": 0.5}],
          "scoring_plays": [],
          "win_prob_history": {
            "espn": [{"timestamp": "2026-09-05T02:13:55Z", "home_probability": 0.66}],
            "mlb": [{"timestamp": "2026-09-05T02:13:55Z", "home_probability": 0.64}]
          },
          "aggregate_line": [
            {"timestamp": "2026-09-05T02:10:00Z", "home_probability": 0.50},
            {"timestamp": "2026-09-05T02:13:55Z", "home_probability": 0.65},
            {"timestamp": "2026-09-05T02:20:55Z", "home_probability": 0.49},
            {"timestamp": "2026-09-05T04:02:55Z", "home_probability": 0.06},
            {"timestamp": "2026-09-05T04:12:55Z", "home_probability": 1.00}
          ],
          "moments": [
            {"ts": "2026-09-05T02:13:55Z", "label": "San Diego Padres score — win prob +14.6 pts",
             "confidence": 0.987, "moment_type": "score", "actor_team": "San Diego Padres",
             "prob_delta": 0.1461, "period": "Bottom 2nd"},
            {"ts": "2026-09-05T02:20:55Z", "label": "New York Yankees score — win prob +15.2 pts",
             "confidence": 1.0, "moment_type": "score", "actor_team": "New York Yankees",
             "prob_delta": 0.1517, "period": "Top 3rd"},
            {"ts": "2026-09-05T04:02:55Z", "label": "New York Yankees score — win prob +27.7 pts",
             "confidence": 1.0, "moment_type": "score", "actor_team": "New York Yankees",
             "prob_delta": 0.2773, "period": "Top 10th"},
            {"ts": "2026-09-05T04:12:55Z", "label": "San Diego Padres score — win prob +93.5 pts",
             "confidence": 1.0, "moment_type": "score", "actor_team": "San Diego Padres",
             "prob_delta": 0.9348, "period": "Bottom 10th"}
          ]
        }
        """)
        XCTAssertEqual(h.scoringPlays?.count, 0,
                       "the array the app used to read — empty, which is why nothing was annotated")

        let points = OddsChartView.chartPoints(from: h)
        let drawn = OddsChartView.chartMoments(from: h.moments, points: points)
        XCTAssertEqual(drawn.count, 4)

        // The last marker sits on the settled 100%, not somewhere between.
        XCTAssertEqual(try XCTUnwrap(drawn.last).probability, 1.0, accuracy: 1e-9)

        let headline = try XCTUnwrap(OddsChartView.headlineMoment(in: drawn))
        XCTAssertEqual(OddsChartView.momentCaptionText(for: headline),
                       "Bottom 10th · San Diego Padres score — win prob +93.5 pts")
        XCTAssertEqual(OddsChartView.momentCaptionKicker(count: drawn.count), "Biggest swing")
    }
}
