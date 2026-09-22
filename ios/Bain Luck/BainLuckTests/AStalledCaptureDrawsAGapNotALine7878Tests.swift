import SwiftUI
import XCTest
@testable import Bain_Luck

/// #7878 — the chart stops drawing a line across an interval nobody observed.
///
/// Photographed 2026-09-21 on the live tennis match `15316479` (Dodin vs
/// Bandecchi), frame `artifacts-native-020/n288-920-live-tennis.png`: badged
/// LIVE, "Since Start" selected, and ONE continuous flat green line across
/// 2h15m. It reads as "we watched for two and a quarter hours and nothing
/// happened."
///
/// The payload said otherwise. `win_prob_history.kalshi` held 337 points and
/// only SIX at or after commence — five clustered 18:02–18:10Z, then nothing
/// for 3h17m. The line was flat because capture stopped ten minutes in, and
/// the renderer drew the silence as a line.
///
/// **That is the general defect, and it is why this file exists: a flat line
/// and no line are the same picture, and so are "nothing happened" and "we
/// weren't looking."** Linear interpolation cannot distinguish them, so the
/// chart has to refuse to join instead.
///
/// The thresholds are measured, not chosen — see ``OddsChartView/gapFloor``
/// for the production table behind them. The two controls below are the load-
/// bearing half of this suite: a healthy dense series and a sleepy PRE-MATCH
/// series must both come back as ONE segment, because the cheap way to pass
/// the headline test is to break every line on the page.
@MainActor
final class AStalledCaptureDrawsAGapNotALine7878Tests: XCTestCase {

    private static let commence = Date(timeIntervalSince1970: 1_758_477_600)

    private func points(
        offsetsFromCommence: [TimeInterval],
        probability: Double = 0.4,
        source: String = "kalshi"
    ) -> [ChartDataPoint] {
        offsetsFromCommence.map {
            ChartDataPoint(
                date: Self.commence.addingTimeInterval($0),
                probability: probability,
                source: source
            )
        }
    }

    // MARK: - The defect

    /// The specimen's own shape: a dense in-game run, then the hole.
    ///
    /// Five observations two minutes apart, then 3h17m of nothing, then the one
    /// point anchoring the right-hand edge. Two segments, and the reader sees
    /// the hole.
    func testTheThreeHourHoleBreaksTheLine() {
        let observed = points(offsetsFromCommence: [141, 260, 380, 500, 619, 12_437])

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(segments.count, 2, "the 3h17m hole must break the series")
        XCTAssertEqual(segments[0].count, 5, "the dense run stays joined")
        XCTAssertEqual(segments[1].count, 1, "the far-side observation is its own run")
    }

    /// The lone observation on the far side of a hole survives as a run of one.
    ///
    /// A `LineMark` needs two points, so a segment of one draws nothing unless
    /// the caller marks it. Dropping it would lose real data to a fix meant to
    /// stop losing real data — this pins that the helper still returns it.
    func testTheObservationAfterTheHoleIsNotDiscarded() {
        let observed = points(offsetsFromCommence: [141, 260, 380, 500, 619, 12_437])

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(
            segments.last?.first?.date,
            Self.commence.addingTimeInterval(12_437),
            "the point past the hole is still drawn, as its own run"
        )
        XCTAssertEqual(
            segments.flatMap { $0 }.count, observed.count,
            "segmenting partitions the points — it never drops one"
        )
    }

    // MARK: - Controls: the lines that must NOT break

    /// A healthy dense in-game series is ONE line.
    ///
    /// Polymarket's real behaviour: 90 observations at the measured 33s median.
    /// If this ever splits, the fix has started inventing holes.
    func testAHealthyDenseSeriesStaysOneLine() {
        let observed = points(offsetsFromCommence: (0..<90).map { Double($0) * 33 })

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1, "a continuously captured match is one unbroken line")
    }

    /// A PRE-MATCH series sleeps for hours and stays one line.
    ///
    /// Measured pre-commence p99 is 2.2 hours and the longest is 5.6 days, so
    /// these holes are the norm, not a defect. This is the control that would
    /// catch a rule applied to the whole domain — it would shatter every
    /// pre-match line on the site into confetti.
    func testOvernightPreMatchHolesNeverBreakTheLine() {
        let observed = points(offsetsFromCommence: [-172_800, -86_400, -43_200, -3_600, -600])

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1, "a market sleeping overnight is not a capture gap")
    }

    /// A hole that STRADDLES the scheduled start is left joined.
    ///
    /// Only intervals with both ends in game are candidates. Deliberately the
    /// cheap direction to be wrong in (a scheduled kickoff is not an evidenced
    /// start, Alex 2026-09-14), and pinned so the choice is visible rather than
    /// accidental.
    func testAHoleSpanningTheStartIsNotBroken() {
        let observed = points(offsetsFromCommence: [-7_200, -3_600, 14_400, 14_520, 14_640])

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1, "the rule only judges intervals wholly in game")
    }

    /// With no known start, nothing is broken at all.
    func testAnUnknownStartBreaksNothing() {
        let observed = points(offsetsFromCommence: [0, 12_437, 24_874])

        let segments = OddsChartView.observationSegments(observed, gameStart: nil)

        XCTAssertEqual(segments.count, 1, "no start means no in-game domain to judge")
    }

    // MARK: - The two thresholds are both load-bearing

    /// Long in absolute terms but ordinary for THIS series ⇒ no break.
    ///
    /// A series whose own median is 20 minutes is not stalling when it takes 21.
    /// The floor alone would break this line; the cadence multiple is what saves
    /// it, so this test fails if the ratio test is ever dropped.
    func testASlowButSteadySeriesIsJudgedOnItsOwnRhythm() {
        let observed = points(offsetsFromCommence: (0..<10).map { Double($0) * 1_200 })

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1, "a 20-minute cadence is a cadence, not a gap")
    }

    /// A big MULTIPLE that is still a short absolute wait ⇒ no break.
    ///
    /// A 10-second series pausing 200 seconds is 20× its median but nothing a
    /// reader could call a hole. The ratio alone would break this line; the
    /// floor is what saves it, so this fails if the floor is ever dropped.
    func testABriefPauseInAFastSeriesIsNotAGap() {
        var offsets = (0..<20).map { Double($0) * 10 }
        offsets.append(offsets.last! + 200)

        let segments = OddsChartView.observationSegments(
            points(offsetsFromCommence: offsets), gameStart: Self.commence
        )

        XCTAssertEqual(segments.count, 1, "200s is 20x a 10s cadence and still not a hole")
    }

    /// Both conditions met ⇒ break. The positive twin of the two tests above.
    func testAnIntervalFailingBothTestsBreaks() {
        var offsets = (0..<20).map { Double($0) * 60 }
        offsets.append(offsets.last! + 5_400)

        let segments = OddsChartView.observationSegments(
            points(offsetsFromCommence: offsets), gameStart: Self.commence
        )

        XCTAssertEqual(segments.count, 2, "90 minutes against a 60s cadence is a hole")
    }

    // MARK: - Degenerate input

    func testEmptyAndSinglePointSeries() {
        XCTAssertEqual(
            OddsChartView.observationSegments([], gameStart: Self.commence).count, 0
        )
        XCTAssertEqual(
            OddsChartView.observationSegments(
                points(offsetsFromCommence: [60]), gameStart: Self.commence
            ).count,
            1
        )
    }

    /// Out-of-order input is sorted before it is judged.
    func testPointsAreOrderedBeforeSegmenting() {
        let observed = points(offsetsFromCommence: [12_437, 141, 500, 260, 380, 619])

        let segments = OddsChartView.observationSegments(observed, gameStart: Self.commence)

        XCTAssertEqual(segments.count, 2)
        XCTAssertEqual(segments[0].count, 5, "arrival order must not decide where the hole is")
    }
}
