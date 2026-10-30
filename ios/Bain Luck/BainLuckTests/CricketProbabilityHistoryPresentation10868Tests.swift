import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket-live "Win probability" history plot as a stateless
/// presentation leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it draws from: every original drawn independently on one 0–100%
/// scale, hollow marks only for explicitly admitted pregame points, owner
/// segments never bridged, invalid and out-of-domain points breaking the path
/// (never clamped, never clipped toward), the exact owner inspection with no
/// substitute, the actions it hands back, the measured axis lanes and the
/// spoken text. Nothing here claims a rendered fit, a native runtime, an
/// interaction qualification or a production binding.
///
/// ARCHIVED raw values come from South Africa–Australia, first Test,
/// October 9–13, 2026 (route cricket-live, original event
/// KXTESTMATCH-26OCT090330AUSSA), as retained in
/// `shipping-adoption-20261027/CRICKET-HISTORY-RETAINED-CASES.json`
/// (sha256 0f216a8b…f521f). Three original Kalshi Yes contracts:
///   SA  KXTESTMATCH-26OCT090330AUSSA-SA   pregame 0.48
///   AUS KXTESTMATCH-26OCT090330AUSSA-AUS  pregame 0.47
///   TIE KXTESTMATCH-26OCT090330AUSSA-TIE  pregame 0.09   (sum 1.04)
///   Pregame: each contract's own hourly bar ending 2026-10-09T00:00Z.
///   Four Day-5 report frames, each original with its own minute bar end:
///     09:11:34Z report  SA 0.03 @09:11  AUS 0.64 @09:11  TIE 0.35 @09:11
///     09:49:56Z lunch   SA 0.01 @09:46  AUS 0.87 @09:48  TIE 0.17 @09:45
///     11:03:34Z report  SA 0.02 @11:03  AUS 0.79 @11:03  TIE 0.20 @11:02
///     11:11:58Z report  SA 0.01 @11:09  AUS 0.95 @11:11  TIE 0.03 @11:11
///   Final score report 11:24:20Z (a publication time, not the last ball).
///   Market settlement 12:35:49Z (AUS yes, SA no, TIE no) is a separate
///   clock and never a chart point. Bar ends are not exact trade or
///   app-arrival clocks (both null). No internal app id is retained.
///
/// The retained hourly/minute arrays (153/369, 153/512, 149/356 bars) are
/// source material, not admitted product history, and are not inputs here.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// series/segment/point ids (the retained source + ticker + side carried as
/// opaque strings), the split of each original into a pregame segment and a
/// Day-5 segment, the pregame flags, every domain, tick, caption, context and
/// summary word, every selection, action and window choice, and every gap,
/// invalid, out-of-domain, duplicate, empty, extra-series, long-text and
/// measured-size case. A constructed gap is not a captured outage.
final class CricketProbabilityHistoryPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let sa = "kalshi:KXTESTMATCH-26OCT090330AUSSA-SA:yes"
    private static let aus = "kalshi:KXTESTMATCH-26OCT090330AUSSA-AUS:yes"
    private static let tie = "kalshi:KXTESTMATCH-26OCT090330AUSSA-TIE:yes"
    private static let order = [sa, aus, tie]

    private static let names: [String: String] = [sa: "South Africa", aus: "Australia", tie: "Draw / tie"]
    private static let shapes: [String: CricketHistoryShape10868] = [sa: .circle, aus: .diamond, tie: .square]
    private static let tints: [String: Color] = [sa: .blue, aus: .orange, tie: .gray]

    /// ARCHIVED: 2026-10-09T00:00:00Z, the pregame hourly bar end.
    private static let pregameEnd: Double = 1_791_504_000
    /// ARCHIVED.
    private static let pregame: [String: Double] = [sa: 0.48, aus: 0.47, tie: 0.09]

    private struct Bar {
        /// ARCHIVED minute bar end, seconds since 1970 (UTC).
        let x: Double
        /// ARCHIVED.
        let probability: Double
    }

    private struct Frame {
        /// ARCHIVED report label and publication time.
        let label: String
        let reportedAt: Double
        let bars: [String: Bar]
    }

    /// ARCHIVED.
    private static let frames: [Frame] = [
        Frame(label: "Day 5 · 64 overs", reportedAt: 1_791_882_694, bars: [
            sa: Bar(x: 1_791_882_660, probability: 0.03),
            aus: Bar(x: 1_791_882_660, probability: 0.64),
            tie: Bar(x: 1_791_882_660, probability: 0.35),
        ]),
        Frame(label: "Day 5 · lunch", reportedAt: 1_791_884_996, bars: [
            sa: Bar(x: 1_791_884_760, probability: 0.01),
            aus: Bar(x: 1_791_884_880, probability: 0.87),
            tie: Bar(x: 1_791_884_700, probability: 0.17),
        ]),
        Frame(label: "Day 5 · 84 overs", reportedAt: 1_791_889_414, bars: [
            sa: Bar(x: 1_791_889_380, probability: 0.02),
            aus: Bar(x: 1_791_889_380, probability: 0.79),
            tie: Bar(x: 1_791_889_320, probability: 0.20),
        ]),
        Frame(label: "Day 5 · 85 overs", reportedAt: 1_791_889_918, bars: [
            sa: Bar(x: 1_791_889_740, probability: 0.01),
            aus: Bar(x: 1_791_889_860, probability: 0.95),
            tie: Bar(x: 1_791_889_860, probability: 0.03),
        ]),
    ]

    /// ARCHIVED: final score report 11:24:20Z and contract settlement 12:35:49Z.
    private static let finalReportAt: Double = 1_791_890_660
    private static let settlementAt: Double = 1_791_894_949

    /// CONSTRUCTED owner domains.
    private static let beforeDomain = CricketHistoryDomain10868(lower: 1_791_500_400, upper: pregameEnd)
    private static let matchDomain = CricketHistoryDomain10868(lower: 1_791_500_400, upper: finalReportAt)

    /// CONSTRUCTED owner ticks.
    private static let percentTicks = [
        CricketHistoryTick10868(value: 0, lines: ["0%"]),
        CricketHistoryTick10868(value: 0.5, lines: ["50%"]),
        CricketHistoryTick10868(value: 1, lines: ["100%"]),
    ]
    private static let calendarTicks = [
        CricketHistoryTick10868(value: 1_791_500_400, lines: ["Oct 8", "7:00 PM"]),
        CricketHistoryTick10868(value: 1_791_695_530, lines: ["Oct 11", "1:12 AM"]),
        CricketHistoryTick10868(value: finalReportAt, lines: ["Oct 13", "7:24 AM"]),
    ]

    private static func pregamePoint(_ id: String) -> CricketHistoryPoint10868 {
        CricketHistoryPoint10868(id: "\(id)#pregame", x: pregameEnd, probability: pregame[id]!, isPregame: true)
    }

    private static func dayFivePoints(_ id: String, through count: Int? = nil) -> [CricketHistoryPoint10868] {
        frames.prefix(count ?? frames.count).enumerated().map { (index, frame) -> CricketHistoryPoint10868 in
            let bar = frame.bars[id]!
            return CricketHistoryPoint10868(id: "\(id)#day5-\(index)", x: bar.x, probability: bar.probability, isPregame: false)
        }
    }

    private static func series(_ id: String,
                               segments: [CricketHistorySegment10868],
                               absentWords: String? = nil) -> CricketHistorySeries10868 {
        CricketHistorySeries10868(id: id, name: names[id]!, shape: shapes[id]!, tint: tints[id]!,
                                  segments: segments, absentWords: absentWords)
    }

    /// Pregame only (CONSTRUCTED one-point segment per original).
    private static func beforeSeries(_ id: String) -> CricketHistorySeries10868 {
        series(id, segments: [CricketHistorySegment10868(id: "\(id)#before", points: [pregamePoint(id)])])
    }

    /// Pregame, then the Day-5 frames, as two CONSTRUCTED owner segments.
    private static func matchSeries(_ id: String, through count: Int? = nil) -> CricketHistorySeries10868 {
        series(id, segments: [
            CricketHistorySegment10868(id: "\(id)#before", points: [pregamePoint(id)]),
            CricketHistorySegment10868(id: "\(id)#day5", points: dayFivePoints(id, through: count)),
        ])
    }

    private static func input(series: [CricketHistorySeries10868],
                              domain: CricketHistoryDomain10868 = matchDomain,
                              yTicks: [CricketHistoryTick10868] = percentTicks,
                              xTicks: [CricketHistoryTick10868] = calendarTicks,
                              context: String? = "Kalshi Yes contracts · times in your time zone (EDT)",
                              pregameKey: String? = "Pregame",
                              summary: String = "South Africa circles, Australia diamonds and draw or tie squares. Solid probability histories. Hollow marks are pregame. Zero to 100 percent.",
                              plotHeight: CGFloat = 302,
                              window: CricketHistoryWindow10868? = nil,
                              inspection: CricketHistoryInspection10868? = nil,
                              previous: CricketHistoryControl10868? = nil,
                              next: CricketHistoryControl10868? = nil,
                              expand: CricketHistoryControl10868? = nil) -> CricketHistoryInput10868 {
        CricketHistoryInput10868(title: "Win probability", series: series, domain: domain,
                                 yTicks: yTicks, xTicks: xTicks, context: context, pregameKey: pregameKey,
                                 summary: summary, plotHeight: plotHeight, window: window,
                                 inspection: inspection, previous: previous, next: next, expand: expand)
    }

    private static func point(_ id: String, _ x: Double, _ probability: Double,
                              pregame: Bool = false) -> CricketHistoryPoint10868 {
        CricketHistoryPoint10868(id: id, x: x, probability: probability, isPregame: pregame)
    }

    private static func segment(_ id: String, _ points: [CricketHistoryPoint10868]) -> CricketHistorySegment10868 {
        CricketHistorySegment10868(id: id, points: points)
    }

    private static let unit = CricketHistoryDomain10868(lower: 0, upper: 100)
    private static let rect = CGRect(x: 10, y: 10, width: 200, height: 100)

    private func ids(_ runs: [[CricketHistoryPoint10868]]) -> [[String]] {
        runs.map { $0.map(\.id) }
    }

    // MARK: Retained cases

    func testRetainedEpochConstantsEqualTheArchivedUTCClocks() {
        let iso = ISO8601DateFormatter()
        let expected: [(String, Double)] = [
            ("2026-10-09T00:00:00Z", Self.pregameEnd),
            ("2026-10-13T09:11:00Z", 1_791_882_660), ("2026-10-13T09:46:00Z", 1_791_884_760),
            ("2026-10-13T09:48:00Z", 1_791_884_880), ("2026-10-13T09:45:00Z", 1_791_884_700),
            ("2026-10-13T11:03:00Z", 1_791_889_380), ("2026-10-13T11:02:00Z", 1_791_889_320),
            ("2026-10-13T11:09:00Z", 1_791_889_740), ("2026-10-13T11:11:00Z", 1_791_889_860),
            ("2026-10-13T11:24:20Z", Self.finalReportAt), ("2026-10-13T12:35:49Z", Self.settlementAt),
        ]
        for (text, value) in expected {
            XCTAssertEqual(iso.date(from: text)?.timeIntervalSince1970, value, text)
        }
    }

    func testRetainedPregameIsThreeIndependentHollowMarksSumming104WithoutNormalization() {
        let input = Self.input(series: Self.order.map(Self.beforeSeries), domain: Self.beforeDomain)
        let marks = input.series.flatMap { CricketHistoryGeometry10868.marks($0, in: input.domain) }
        XCTAssertEqual(marks.map(\.probability), [0.48, 0.47, 0.09])
        XCTAssertEqual(marks.map(\.probability).reduce(0, +), 1.04, accuracy: 1e-9)
        XCTAssertTrue(marks.allSatisfy(\.isPregame))
        XCTAssertTrue(marks.allSatisfy { $0.x == Self.pregameEnd })
        for series in input.series {
            XCTAssertTrue(CricketHistoryGeometry10868.lines(series, in: input.domain).isEmpty, series.name)
        }
        let ys = marks.map { CricketHistoryGeometry10868.yPosition($0.probability, in: Self.rect) }
        XCTAssertEqual(ys[0], Self.rect.maxY - 48, accuracy: 1e-9)
        XCTAssertEqual(ys[1], Self.rect.maxY - 47, accuracy: 1e-9)
        XCTAssertEqual(ys[2], Self.rect.maxY - 9, accuracy: 1e-9)
    }

    func testEveryRetainedFrameKeepsEachOriginalsOwnValueAndBarClock() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) })
        for (index, series) in input.series.enumerated() {
            let id = Self.order[index]
            let playMarks = CricketHistoryGeometry10868.marks(series, in: input.domain).filter { !$0.isPregame }
            XCTAssertEqual(playMarks.map(\.x), Self.frames.map { $0.bars[id]!.x }, series.name)
            XCTAssertEqual(playMarks.map(\.probability), Self.frames.map { $0.bars[id]!.probability }, series.name)
        }
    }

    func testLunchFrameKeepsThreeDifferentBarClocksNeverOneSharedTime() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) })
        let lunch = input.series.map { series in
            CricketHistoryGeometry10868.marks(series, in: input.domain).first { $0.id.hasSuffix("#day5-1") }!
        }
        XCTAssertEqual(Set(lunch.map(\.x)).count, 3)
        XCTAssertTrue(lunch.allSatisfy { $0.x < Self.frames[1].reportedAt }, "each bar precedes its report")
        let xs = lunch.map { CricketHistoryGeometry10868.position($0, domain: input.domain, in: Self.rect).x }
        XCTAssertEqual(Set(xs).count, 3)
    }

    func testDuringFramesPrefixDrawsOnlyWhatTheOwnerSupplied() {
        for count in 1...Self.frames.count {
            let input = Self.input(series: Self.order.map { Self.matchSeries($0, through: count) })
            for series in input.series {
                let lines = CricketHistoryGeometry10868.lines(series, in: input.domain)
                XCTAssertEqual(lines.count, count >= 2 ? 1 : 0, "\(series.name) \(count)")
                XCTAssertEqual(CricketHistoryGeometry10868.marks(series, in: input.domain).count, count + 1)
                XCTAssertEqual(lines.first?.last?.id, count >= 2 ? "\(series.id)#day5-\(count - 1)" : nil)
            }
        }
    }

    func testPregameSegmentIsNeverJoinedToPlay() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) })
        for series in input.series {
            let lines = CricketHistoryGeometry10868.lines(series, in: input.domain)
            XCTAssertFalse(lines.flatMap { $0 }.contains(where: \.isPregame), series.name)
        }
    }

    func testCompletedPlayNeverDrawsASettlementAsAPointOrAFinalChance() {
        // CONSTRUCTED misuse: the owner's segment carries the settlement
        // extremes at the settlement clock, after its own domain ends at the
        // final score report.
        let settled: [String: Double] = [Self.sa: 0, Self.aus: 1, Self.tie: 0]
        let series = Self.order.map { id in
            Self.series(id, segments: [
                Self.segment("\(id)#before", [Self.pregamePoint(id)]),
                Self.segment("\(id)#day5", Self.dayFivePoints(id) + [Self.point("\(id)#settled", Self.settlementAt, settled[id]!)]),
            ])
        }
        let input = Self.input(series: series)
        for item in input.series {
            let marks = CricketHistoryGeometry10868.marks(item, in: input.domain)
            XCTAssertFalse(marks.contains { $0.id.hasSuffix("#settled") }, item.name)
            XCTAssertTrue(marks.allSatisfy { $0.x <= Self.finalReportAt }, item.name)
            let lines = CricketHistoryGeometry10868.lines(item, in: input.domain)
            XCTAssertEqual(lines.count, 1)
            XCTAssertEqual(lines[0].last?.id, "\(item.id)#day5-3", "no line runs toward the settlement")
        }
        let aus = CricketHistoryGeometry10868.marks(input.series[1], in: input.domain)
        XCTAssertFalse(aus.contains { $0.probability == 1 })
        XCTAssertEqual(aus.last?.probability, 0.95)
    }

    // MARK: Hollow and filled marks

    func testHollowOnlyForTheExplicitPregameFlagNeverForAnEqualValueOrTime() {
        // CONSTRUCTED: a filled point at the pregame's own clock and value.
        let echo = Self.point("sa#echo", Self.pregameEnd, 0.48)
        let series = Self.series(Self.sa, segments: [
            Self.segment("a", [Self.pregamePoint(Self.sa)]),
            Self.segment("b", [echo]),
        ])
        let marks = CricketHistoryGeometry10868.marks(series, in: Self.matchDomain)
        XCTAssertEqual(marks.map(\.isPregame), [true, false])
        // CONSTRUCTED: the first point of play is never promoted by position.
        let first = CricketHistoryGeometry10868.marks(Self.matchSeries(Self.aus), in: Self.matchDomain)
            .first { !$0.id.hasSuffix("#pregame") }
        XCTAssertEqual(first?.isPregame, false)
    }

    func testEqualValuesAtDistinctObservationsStayTwoMarksOnOneLine() {
        let sa = Self.matchSeries(Self.sa)
        let ones = CricketHistoryGeometry10868.marks(sa, in: Self.matchDomain).filter { $0.probability == 0.01 }
        XCTAssertEqual(ones.map(\.x), [1_791_884_760, 1_791_889_740])
        let line = CricketHistoryGeometry10868.lines(sa, in: Self.matchDomain)
        XCTAssertEqual(line.count, 1)
        XCTAssertEqual(line[0].filter { $0.probability == 0.01 }.count, 2)
    }

    func testShowsPregameKeyOnlyWhenAHollowMarkIsDrawn() {
        XCTAssertTrue(CricketHistoryGeometry10868.showsPregameKey(
            Self.input(series: Self.order.map { Self.matchSeries($0) })))
        XCTAssertFalse(CricketHistoryGeometry10868.showsPregameKey(
            Self.input(series: Self.order.map { Self.matchSeries($0) }, pregameKey: nil)))
        let playOnly = Self.order.map { id in
            Self.series(id, segments: [Self.segment("\(id)#day5", Self.dayFivePoints(id))])
        }
        XCTAssertFalse(CricketHistoryGeometry10868.showsPregameKey(Self.input(series: playOnly)))
        // A pregame point outside the owner's domain draws nothing, so no key.
        let dayFive = CricketHistoryDomain10868(lower: 1_791_882_000, upper: Self.finalReportAt)
        XCTAssertFalse(CricketHistoryGeometry10868.showsPregameKey(
            Self.input(series: Self.order.map { Self.matchSeries($0) }, domain: dayFive)))
    }

    // MARK: Zero, invalid and out-of-domain

    func testRealZeroIsAValueAtTheBottomAndNotAnAbsence() {
        let series = Self.series(Self.sa, segments: [Self.segment("a", [Self.point("z", 50, 0)])],
                                 absentWords: "No recorded trades")
        XCTAssertEqual(CricketHistoryGeometry10868.marks(series, in: Self.unit).map(\.id), ["z"])
        XCTAssertNil(CricketHistoryGeometry10868.absentWords(series, in: Self.unit))
        XCTAssertEqual(CricketHistoryGeometry10868.yPosition(0, in: Self.rect), Self.rect.maxY)
        XCTAssertEqual(CricketHistoryGeometry10868.yPosition(1, in: Self.rect), Self.rect.minY)
    }

    func testNonfiniteOrOutOfRangeProbabilityBreaksThePathAndIsNeverClamped() {
        let points = [
            Self.point("a", 10, 0.2), Self.point("nan", 20, .nan), Self.point("b", 30, 0.3),
            Self.point("over", 40, 1.2), Self.point("c", 50, 0.4), Self.point("under", 60, -0.1),
            Self.point("d", 70, 0.5), Self.point("inf", 80, .infinity), Self.point("e", 90, 0.6),
            Self.point("f", 95, 0.7),
        ]
        let segment = Self.segment("s", points)
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(segment, in: Self.unit)),
                       [["a"], ["b"], ["c"], ["d"], ["e", "f"]])
        let series = Self.series(Self.sa, segments: [segment])
        let marks = CricketHistoryGeometry10868.marks(series, in: Self.unit)
        XCTAssertEqual(marks.map(\.id), ["a", "b", "c", "d", "e", "f"])
        XCTAssertFalse(marks.contains { $0.probability == 0 || $0.probability == 1 })
        XCTAssertEqual(ids(CricketHistoryGeometry10868.lines(series, in: Self.unit)), [["e", "f"]])
    }

    func testNonfiniteXBreaksThePath() {
        let segment = Self.segment("s", [
            Self.point("a", 10, 0.2), Self.point("b", 20, 0.3), Self.point("nan", .nan, 0.4),
            Self.point("c", 30, 0.5), Self.point("inf", .infinity, 0.5), Self.point("d", 40, 0.6),
        ])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(segment, in: Self.unit)), [["a", "b"], ["c"], ["d"]])
    }

    func testPointsOutsideTheDomainBreakThePathAndNoLineIsClippedTowardThem() {
        let future = Self.segment("future", [Self.point("a", 80, 0.2), Self.point("b", 95, 0.3),
                                             Self.point("later", 140, 0.9)])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(future, in: Self.unit)), [["a", "b"]])
        let past = Self.segment("past", [Self.point("earlier", -40, 0.9), Self.point("a", 5, 0.2),
                                         Self.point("b", 10, 0.3)])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(past, in: Self.unit)), [["a", "b"]])
        let through = Self.segment("through", [Self.point("a", 20, 0.2), Self.point("out", 150, 0.5),
                                               Self.point("b", 30, 0.3)])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(through, in: Self.unit)), [["a"], ["b"]])
        // The domain bounds themselves are inside.
        let edges = Self.segment("edges", [Self.point("lo", 0, 0.1), Self.point("hi", 100, 0.2)])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(edges, in: Self.unit)), [["lo", "hi"]])
    }

    func testXThatDoesNotAdvanceBreaksThePathInTheOwnersOrder() {
        let segment = Self.segment("s", [
            Self.point("a", 10, 0.2), Self.point("same", 10, 0.3), Self.point("back", 5, 0.4),
            Self.point("on", 20, 0.5),
        ])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.runs(segment, in: Self.unit)),
                       [["a"], ["same"], ["back", "on"]])
    }

    func testInvalidDomainPlacesNothing() {
        let series = Self.matchSeries(Self.sa)
        for domain in [CricketHistoryDomain10868(lower: 5, upper: 5),
                       CricketHistoryDomain10868(lower: 9, upper: 1),
                       CricketHistoryDomain10868(lower: .nan, upper: 1),
                       CricketHistoryDomain10868(lower: 0, upper: .infinity)] {
            XCTAssertFalse(domain.isValid)
            XCTAssertTrue(CricketHistoryGeometry10868.marks(series, in: domain).isEmpty)
            XCTAssertTrue(CricketHistoryGeometry10868.placedXTicks(Self.calendarTicks, domain: domain).isEmpty)
            XCTAssertNil(CricketHistoryGeometry10868.domainValue(atX: 50, domain: domain, in: Self.rect))
        }
    }

    // MARK: Segments and isolated points

    func testOwnerSegmentsAreNeverBridgedAcrossAConstructedGap() {
        // CONSTRUCTED gap: not a captured outage.
        let series = Self.series(Self.aus, segments: [
            Self.segment("first", [Self.point("a", 10, 0.6), Self.point("b", 20, 0.64)]),
            Self.segment("second", [Self.point("c", 60, 0.87), Self.point("d", 70, 0.79)]),
        ])
        XCTAssertEqual(ids(CricketHistoryGeometry10868.lines(series, in: Self.unit)), [["a", "b"], ["c", "d"]])
    }

    func testIsolatedPointsAreMarksWithoutLines() {
        let series = Self.series(Self.tie, segments: [
            Self.segment("one", [Self.point("a", 10, 0.35)]),
            Self.segment("two", [Self.point("b", 50, 0.17)]),
            Self.segment("empty", []),
        ])
        XCTAssertTrue(CricketHistoryGeometry10868.lines(series, in: Self.unit).isEmpty)
        XCTAssertEqual(CricketHistoryGeometry10868.marks(series, in: Self.unit).map(\.id), ["a", "b"])
    }

    func testMissingOneSeriesKeepsItsNameAndOwnWordsAndBorrowsNothing() {
        let tie = Self.series(Self.tie, segments: [], absentWords: "No recorded trades")
        let input = Self.input(series: [Self.matchSeries(Self.sa), Self.matchSeries(Self.aus), tie])
        XCTAssertEqual(input.series.map(\.name), ["South Africa", "Australia", "Draw / tie"])
        XCTAssertTrue(CricketHistoryGeometry10868.marks(tie, in: input.domain).isEmpty)
        XCTAssertEqual(CricketHistoryGeometry10868.absentWords(tie, in: input.domain), "No recorded trades")
        XCTAssertEqual(CricketHistoryGeometry10868.marks(input.series[1], in: input.domain).map(\.probability),
                       [0.47, 0.64, 0.87, 0.79, 0.95])
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "Draw / tie: No recorded trades")
        XCTAssertNil(CricketHistoryGeometry10868.absentWords(input.series[0], in: input.domain))
    }

    func testEmptyInputDrawsNothingAndInventsNoWords() {
        let input = Self.input(series: [], xTicks: [], pregameKey: "Pregame")
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "")
        XCTAssertFalse(CricketHistoryGeometry10868.showsPregameKey(input))
        XCTAssertNil(CricketHistoryGeometry10868.cursor(input.inspection, domain: input.domain))
        let arrangement = CricketHistoryGeometry10868.plotArrangement(
            width: 320, plotHeight: input.plotHeight, inset: 8.5, yValues: [], ySizes: [], xFractions: [],
            xSizes: [], labelGap: 6, axisGap: 6, laneSpacing: 4)
        XCTAssertEqual(arrangement.plot, CGRect(x: 0, y: 0, width: 320, height: 302))
        XCTAssertEqual(arrangement.height, 302)
    }

    func testEverySuppliedSeriesAndPointIsDrawnWithNoSeriesOrSamplingCap() {
        // CONSTRUCTED five series of 600 points each.
        let shapes = CricketHistoryShape10868.allCases
        let series = (0..<5).map { index in
            CricketHistorySeries10868(
                id: "s\(index)", name: "Series \(index)", shape: shapes[index % shapes.count], tint: .blue,
                segments: [Self.segment("s\(index)", (0..<600).map {
                    Self.point("s\(index)-\($0)", Double($0) / 6, Double(($0 * 7 + index) % 101) / 100)
                })],
                absentWords: nil)
        }
        let input = Self.input(series: series, domain: Self.unit)
        XCTAssertEqual(input.series.count, 5)
        for item in input.series {
            XCTAssertEqual(CricketHistoryGeometry10868.marks(item, in: input.domain).count, 600)
            XCTAssertEqual(CricketHistoryGeometry10868.lines(item, in: input.domain).map(\.count), [600])
        }
    }

    // MARK: Inspection

    private static func firstFrameInspection(absentTie: Bool = false) -> CricketHistoryInspection10868 {
        var selections: [String: CricketHistorySelection10868] = [
            sa: .point(id: "\(sa)#day5-0", spoken: "3%"),
            aus: .point(id: "\(aus)#day5-0", spoken: "64%"),
        ]
        selections[tie] = absentTie ? .absent(words: "Not recorded") : .point(id: "\(tie)#day5-0", spoken: "35%")
        return CricketHistoryInspection10868(x: 1_791_882_660, caption: "Selected · Oct 13, 5:11 AM", selections: selections)
    }

    func testInspectionDrawsOnlyTheOwnersExactPointsAndCursor() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) }, inspection: Self.firstFrameInspection())
        XCTAssertEqual(CricketHistoryGeometry10868.cursor(input.inspection, domain: input.domain), 1_791_882_660)
        let selected = input.series.map {
            CricketHistoryGeometry10868.selectedPoint($0, inspection: input.inspection, domain: input.domain)
        }
        XCTAssertEqual(selected.map { $0?.probability }, [0.03, 0.64, 0.35])
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input),
                       "Selected · Oct 13, 5:11 AM; South Africa: 3%; Australia: 64%; Draw / tie: 35%")
    }

    func testAnOwnerSelectionInAGapDrawsNoSubstituteForThatSeries() {
        // CONSTRUCTED: the owner holds a position where the draw/tie original
        // has no observation.
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) },
                               inspection: Self.firstFrameInspection(absentTie: true))
        XCTAssertNil(CricketHistoryGeometry10868.selectedPoint(input.series[2], inspection: input.inspection,
                                                               domain: input.domain))
        XCTAssertEqual(CricketHistoryGeometry10868.selectionAbsentWords(input.series[2], inspection: input.inspection),
                       "Not recorded")
        XCTAssertNil(CricketHistoryGeometry10868.selectionAbsentWords(input.series[1], inspection: input.inspection))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input),
                       "Selected · Oct 13, 5:11 AM; South Africa: 3%; Australia: 64%; Draw / tie: Not recorded")
    }

    func testUnresolvedDuplicateOrUnplaceableSelectedIdsDrawAndSpeakNothing() {
        let duplicate = Self.series(Self.aus, segments: [
            Self.segment("a", [Self.point("dup", 1_791_882_660, 0.64)]),
            Self.segment("b", [Self.point("dup", 1_791_884_880, 0.87)]),
        ])
        let outside = Self.series(Self.tie, segments: [Self.segment("a", [Self.point("late", Self.settlementAt, 0)])])
        let inspection = CricketHistoryInspection10868(x: 1_791_882_660, caption: "Selected", selections: [
            Self.sa: .point(id: "no-such-point", spoken: "3%"),
            Self.aus: .point(id: "dup", spoken: "64%"),
            Self.tie: .point(id: "late", spoken: "0%"),
        ])
        let input = Self.input(series: [Self.matchSeries(Self.sa), duplicate, outside], inspection: inspection)
        for series in input.series {
            XCTAssertNil(CricketHistoryGeometry10868.selectedPoint(series, inspection: inspection, domain: input.domain),
                         series.name)
        }
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "Selected")
    }

    func testNoInspectionMeansNoDefaultSelectionOrLatestObservation() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) })
        XCTAssertNil(CricketHistoryGeometry10868.cursor(nil, domain: input.domain))
        for series in input.series {
            XCTAssertNil(CricketHistoryGeometry10868.selectedPoint(series, inspection: nil, domain: input.domain))
        }
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "")
    }

    func testCursorIsDrawnOnlyInsideTheDomain() {
        let inside = CricketHistoryInspection10868(x: 50, caption: "c", selections: [:])
        let outside = CricketHistoryInspection10868(x: 101, caption: "c", selections: [:])
        let missing = CricketHistoryInspection10868(x: nil, caption: "c", selections: [:])
        let nan = CricketHistoryInspection10868(x: .nan, caption: "c", selections: [:])
        XCTAssertEqual(CricketHistoryGeometry10868.cursor(inside, domain: Self.unit), 50)
        XCTAssertNil(CricketHistoryGeometry10868.cursor(outside, domain: Self.unit))
        XCTAssertNil(CricketHistoryGeometry10868.cursor(missing, domain: Self.unit))
        XCTAssertNil(CricketHistoryGeometry10868.cursor(nan, domain: Self.unit))
    }

    // MARK: Actions

    func testControlsAreOfferedOnlyWithBothAnOwnerActionAndACallback() {
        let available = CricketHistoryControl10868(label: "Previous cricket trade interval", isAvailable: true)
        let unavailable = CricketHistoryControl10868(label: "Next cricket trade interval", isAvailable: false)
        XCTAssertNil(CricketHistoryGeometry10868.offered(available, hasCallback: false))
        XCTAssertNil(CricketHistoryGeometry10868.offered(nil, hasCallback: true))
        XCTAssertEqual(CricketHistoryGeometry10868.offered(available, hasCallback: true), available)
        XCTAssertEqual(CricketHistoryGeometry10868.offered(unavailable, hasCallback: true)?.isAvailable, false)
    }

    func testWindowChoicesAreHandedBackOnlyWithACallbackAndACaptionIsNeverAChoice() {
        let choices = [CricketHistoryWindowChoice10868(id: "match", label: "Match", isSelected: false),
                       CricketHistoryWindowChoice10868(id: "day5", label: "Day 5", isSelected: true)]
        let window = CricketHistoryWindow10868.choices(groupLabel: "Cricket history window", choices: choices)
        XCTAssertEqual(CricketHistoryGeometry10868.offeredChoices(window, hasCallback: true), choices)
        XCTAssertTrue(CricketHistoryGeometry10868.offeredChoices(window, hasCallback: false).isEmpty)
        XCTAssertTrue(CricketHistoryGeometry10868.offeredChoices(.caption("Hourly history"), hasCallback: true).isEmpty)
        XCTAssertTrue(CricketHistoryGeometry10868.offeredChoices(nil, hasCallback: true).isEmpty)
    }

    func testPlotPositionReportsTheDomainValueUnderTheTapAndNothingOutside() {
        let domain = CricketHistoryDomain10868(lower: 1_000, upper: 2_000)
        XCTAssertEqual(CricketHistoryGeometry10868.domainValue(atX: Self.rect.minX, domain: domain, in: Self.rect), 1_000)
        XCTAssertEqual(CricketHistoryGeometry10868.domainValue(atX: Self.rect.maxX, domain: domain, in: Self.rect), 2_000)
        XCTAssertEqual(CricketHistoryGeometry10868.domainValue(atX: Self.rect.midX, domain: domain, in: Self.rect)!,
                       1_500, accuracy: 1e-9)
        XCTAssertNil(CricketHistoryGeometry10868.domainValue(atX: Self.rect.minX - 1, domain: domain, in: Self.rect))
        XCTAssertNil(CricketHistoryGeometry10868.domainValue(atX: Self.rect.maxX + 1, domain: domain, in: Self.rect))
        XCTAssertNil(CricketHistoryGeometry10868.domainValue(atX: .nan, domain: domain, in: Self.rect))
        XCTAssertNil(CricketHistoryGeometry10868.domainValue(atX: 50, domain: domain, in: .zero))
    }

    func testStaticViewNeedsNoCallback() {
        let view = CricketProbabilityHistoryPresentation10868(input: Self.input(series: Self.order.map { Self.matchSeries($0) }))
        XCTAssertNil(view.onPrevious)
        XCTAssertNil(view.onNext)
        XCTAssertNil(view.onExpand)
        XCTAssertNil(view.onWindowChoice)
        XCTAssertNil(view.onPlotPosition)
        XCTAssertFalse(view.input.summary.isEmpty)
    }

    // MARK: Coordinates and marks

    func testCoordinatesPlaceTheCommonScaleAndTheDomainInsideTheDrawingFrame() {
        let drawing = CricketHistoryGeometry10868.drawingRect(in: CGSize(width: 300, height: 302), inset: 8.5)
        XCTAssertEqual(drawing, CGRect(x: 8.5, y: 8.5, width: 283, height: 285))
        let p = Self.point("p", 25, 0.5)
        let position = CricketHistoryGeometry10868.position(p, domain: Self.unit, in: drawing)
        XCTAssertEqual(position.x, 8.5 + 283 * 0.25, accuracy: 1e-9)
        XCTAssertEqual(position.y, 8.5 + 285 * 0.5, accuracy: 1e-9)
        XCTAssertEqual(CricketHistoryGeometry10868.drawingRect(in: CGSize(width: 4, height: 4), inset: 8.5).size, .zero)
    }

    func testMarkPathsKeepThreeDistinctShapesAtTheApprovedProportions() {
        let center = CGPoint(x: 50, y: 50)
        let circle = CricketHistoryGeometry10868.markPath(.circle, at: center, radius: 5).boundingRect
        let diamond = CricketHistoryGeometry10868.markPath(.diamond, at: center, radius: 5).boundingRect
        let square = CricketHistoryGeometry10868.markPath(.square, at: center, radius: 5).boundingRect
        XCTAssertEqual(circle.width, 10, accuracy: 1e-9)
        XCTAssertEqual(diamond.width, 12, accuracy: 1e-9)
        XCTAssertEqual(square.width, 8, accuracy: 1e-9)
        for rect in [circle, diamond, square] {
            XCTAssertEqual(rect.midX, 50, accuracy: 1e-9)
            XCTAssertEqual(rect.midY, 50, accuracy: 1e-9)
        }
        XCTAssertEqual(CricketHistoryShape10868.allCases, [.circle, .diamond, .square])
    }

    func testTicksArePlacedOnlyOnTheScaleAndInsideTheDomainWithWordsVerbatim() {
        let y = CricketHistoryGeometry10868.placedYTicks(Self.percentTicks + [
            CricketHistoryTick10868(value: 1.5, lines: ["150%"]),
            CricketHistoryTick10868(value: .nan, lines: ["?"]),
        ])
        XCTAssertEqual(y.map(\.lines), [["0%"], ["50%"], ["100%"]])
        let x = CricketHistoryGeometry10868.placedXTicks(Self.calendarTicks + [
            CricketHistoryTick10868(value: Self.settlementAt, lines: ["Oct 13", "8:35 AM"]),
        ], domain: Self.matchDomain)
        XCTAssertEqual(x.map(\.lines), [["Oct 8", "7:00 PM"], ["Oct 11", "1:12 AM"], ["Oct 13", "7:24 AM"]])
    }

    // MARK: Axis and key geometry (CONSTRUCTED measured sizes)

    /// CONSTRUCTED standard-size measurements: "100%" and a two-line date/time.
    private static let standardY = CGSize(width: 30, height: 16)
    private static let standardX = CGSize(width: 46, height: 32)
    /// CONSTRUCTED accessibility-size measurements.
    private static let axY = CGSize(width: 74, height: 44)
    private static let axX = CGSize(width: 150, height: 88)

    private func arrangement(width: CGFloat, plotHeight: CGFloat = 302, y: CGSize, x: CGSize,
                             xFractions: [Double] = [0, 0.5, 1],
                             yValues: [Double] = [0, 0.5, 1]) -> CricketHistoryPlotArrangement10868 {
        CricketHistoryGeometry10868.plotArrangement(
            width: width, plotHeight: plotHeight, inset: 8.5,
            yValues: yValues, ySizes: yValues.map { _ in y },
            xFractions: xFractions, xSizes: xFractions.map { _ in x },
            labelGap: 6, axisGap: 6, laneSpacing: 4)
    }

    private func assertNoOverlapWithinLanes(_ frames: [CGRect], file: StaticString = #filePath, line: UInt = #line) {
        for i in frames.indices {
            for j in frames.indices where j > i {
                XCTAssertFalse(frames[i].intersects(frames[j]), "\(frames[i]) vs \(frames[j])", file: file, line: line)
            }
        }
    }

    func testStandardTextAtPhoneAndWideWidthsKeepsOneRowAndTheOwnersHeight() {
        for width: CGFloat in [320, 375, 393, 768, 1024] {
            let a = arrangement(width: width, y: Self.standardY, x: Self.standardX)
            XCTAssertEqual(a.plot.height, 302, "\(width)")
            XCTAssertEqual(a.plot.minX, 36, "\(width)")
            XCTAssertEqual(a.plot.width, width - 36, "\(width)")
            XCTAssertEqual(a.yColumns, 1)
            XCTAssertEqual(a.xRows, 1, "\(width)")
            XCTAssertEqual(a.height, 302 + 6 + 32, "\(width)")
            XCTAssertTrue(a.xLabels.allSatisfy { $0.minX >= 0 && $0.maxX <= width && $0.width == 46 })
            XCTAssertTrue(a.yLabels.allSatisfy { $0.maxX == 30 && $0.width == 30 })
            assertNoOverlapWithinLanes(a.xLabels)
            assertNoOverlapWithinLanes(a.yLabels)
        }
    }

    func testCalendarLabelsStayCentredOnTheirTicksUntilTheEdge() {
        let a = arrangement(width: 393, y: Self.standardY, x: Self.standardX)
        let drawing = CGRect(x: a.plot.minX + 8.5, y: 0, width: a.plot.width - 17, height: 1)
        XCTAssertEqual(a.xLabels[1].midX, drawing.midX, accuracy: 1e-9)
        XCTAssertEqual(a.xLabels[0].minX, 36 + 8.5 - 23, accuracy: 1e-9)
        XCTAssertEqual(a.xLabels[2].maxX, 393, accuracy: 1e-9, "slid inward, never cut")
    }

    func testAccessibilitySizeLabelsReflowIntoMoreRowsInsteadOfShrinking() {
        for width: CGFloat in [320, 375, 393] {
            let a = arrangement(width: width, plotHeight: 370, y: Self.axY, x: Self.axX)
            XCTAssertEqual(a.plot.height, 370)
            XCTAssertGreaterThanOrEqual(a.xRows, 2, "\(width)")
            XCTAssertTrue(a.xLabels.allSatisfy { $0.width == 150 && $0.height == 88 }, "never shrunk")
            XCTAssertTrue(a.xLabels.allSatisfy { $0.minX >= 0 && $0.maxX <= width })
            XCTAssertTrue(a.xLabels.allSatisfy { $0.minY >= 370 })
            assertNoOverlapWithinLanes(a.xLabels)
            XCTAssertEqual(a.yLabels.map(\.width), [74, 74, 74])
        }
        let wide = arrangement(width: 1024, plotHeight: 370, y: Self.axY, x: Self.axX)
        XCTAssertEqual(wide.xRows, 1)
    }

    func testCrowdedPercentageLabelsMoveToAnotherGutterColumn() {
        let a = arrangement(width: 320, plotHeight: 120, y: Self.axY, x: Self.standardX,
                            yValues: [0, 0.25, 0.5, 0.75, 1])
        XCTAssertGreaterThan(a.yColumns, 1)
        XCTAssertEqual(a.plot.minX, CGFloat(a.yColumns) * (74 + 6))
        assertNoOverlapWithinLanes(a.yLabels)
        XCTAssertTrue(a.yLabels.allSatisfy { $0.minX >= 0 && $0.width == 74 })
    }

    func testALabelWiderThanTheWholeWidthStartsAtTheEdgeAndKeepsTheWidth() {
        // CONSTRUCTED: the layout re-measures such a label at the full width,
        // where it wraps; the arrangement never narrows it further.
        let a = arrangement(width: 320, y: Self.standardY, x: CGSize(width: 320, height: 64), xFractions: [0.5])
        XCTAssertEqual(a.xLabels, [CGRect(x: 0, y: 308, width: 320, height: 64)])
    }

    func testLabelSlotsKeepTicksAndMoveOnlyTouchingLabels() {
        let roomy = CricketHistoryGeometry10868.labelSlots(centers: [0, 160, 320], lengths: [60, 60, 60],
                                                           extent: 320, gap: 6)
        XCTAssertEqual(roomy, [CricketHistoryLabelSlot10868(start: 0, lane: 0),
                               CricketHistoryLabelSlot10868(start: 130, lane: 0),
                               CricketHistoryLabelSlot10868(start: 260, lane: 0)])
        let tight = CricketHistoryGeometry10868.labelSlots(centers: [0, 60, 200], lengths: [60, 60, 60],
                                                           extent: 260, gap: 6)
        XCTAssertEqual(tight.map(\.lane), [0, 1, 0])
        XCTAssertEqual(tight.map(\.start), [0, 30, 170])
        let crowded = CricketHistoryGeometry10868.labelSlots(centers: [0, 60, 120], lengths: [60, 60, 60],
                                                             extent: 120, gap: 6)
        XCTAssertEqual(crowded.map(\.lane), [0, 1, 2])
        XCTAssertEqual(crowded.map(\.start), [0, 30, 60])
        XCTAssertTrue(CricketHistoryGeometry10868.labelSlots(centers: [], lengths: [], extent: 100, gap: 6).isEmpty)
    }

    func testInvalidOwnerHeightUsesTheReferenceHeightAndAnOwnerHeightIsNeverShrunk() {
        XCTAssertEqual(CricketHistoryGeometry10868.plotHeight(0), 302)
        XCTAssertEqual(CricketHistoryGeometry10868.plotHeight(-10), 302)
        XCTAssertEqual(CricketHistoryGeometry10868.plotHeight(.nan), 302)
        XCTAssertEqual(CricketHistoryGeometry10868.plotHeight(.infinity), 302)
        XCTAssertEqual(CricketHistoryGeometry10868.plotHeight(350), 350)
        XCTAssertEqual(CricketHistoryGeometry10868.plotHeight(370), 370)
        XCTAssertEqual(arrangement(width: 320, plotHeight: 370, y: Self.standardY, x: Self.standardX).plot.height, 370)
    }

    // MARK: Words and identity

    func testLongNamesContextAndCalendarWordsStayVerbatim() {
        // CONSTRUCTED long owner words.
        let long = "Draw or tie — the original match contract, settled separately by the venue"
        let tie = CricketHistorySeries10868(id: Self.tie, name: long, shape: .square, tint: .gray,
                                            segments: [], absentWords: "No qualifying trade in this window")
        let context = "Kalshi Yes contracts, each traded separately · dates and times in your device time zone (Eastern Daylight Time)"
        let ticks = [CricketHistoryTick10868(value: Self.pregameEnd, lines: ["Thursday, October 8, 2026", "8:00 PM Eastern Daylight Time"])]
        let input = Self.input(series: [tie], xTicks: ticks, context: context)
        XCTAssertEqual(input.context, context)
        XCTAssertEqual(CricketHistoryGeometry10868.placedXTicks(input.xTicks, domain: input.domain).first?.lines,
                       ["Thursday, October 8, 2026", "8:00 PM Eastern Daylight Time"])
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "\(long): No qualifying trade in this window")
    }

    func testInputsTakeOnlyOwnerWordsAndCarryNoClockScoreOrNavigationTarget() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) })
        XCTAssertEqual(Set(Mirror(reflecting: input).children.compactMap(\.label)), [
            "title", "series", "domain", "yTicks", "xTicks", "context", "pregameKey", "summary",
            "plotHeight", "window", "inspection", "previous", "next", "expand",
        ])
        XCTAssertEqual(Set(Mirror(reflecting: input.series[0]).children.compactMap(\.label)),
                       ["id", "name", "shape", "tint", "segments", "absentWords"])
        XCTAssertEqual(Set(Mirror(reflecting: Self.pregamePoint(Self.sa)).children.compactMap(\.label)),
                       ["id", "x", "probability", "isPregame"])
        XCTAssertEqual(Set(Mirror(reflecting: Self.firstFrameInspection()).children.compactMap(\.label)),
                       ["x", "caption", "selections"])
    }

    func testSeriesKeepTheOwnersOrderNamesShapesAndDistinctIds() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) })
        XCTAssertEqual(input.series.map(\.id), Self.order)
        XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond, .square])
        let pointIds = input.series.flatMap { $0.segments.flatMap(\.points) }.map(\.id)
        XCTAssertEqual(Set(pointIds).count, pointIds.count)
        XCTAssertEqual(pointIds.count, 15)
    }

    // MARK: Series and window-choice identity (CONSTRUCTED identity/choice fixtures)

    /// CONSTRUCTED: an id two series share. Not a retained identity.
    private static let sharedId = "constructed:shared-series-id"
    /// CONSTRUCTED: a position inside `matchDomain` (the first Day-5 bar end).
    private static let heldX: Double = 1_791_882_660

    private static func constructedSeries(id: String, name: String, shape: CricketHistoryShape10868,
                                          points: [CricketHistoryPoint10868],
                                          absentWords: String? = nil) -> CricketHistorySeries10868 {
        CricketHistorySeries10868(id: id, name: name, shape: shape, tint: .gray,
                                  segments: points.isEmpty ? [] : [segment("\(name)#constructed", points)],
                                  absentWords: absentWords)
    }

    func testTwoSeriesSharingAnIdAndTheSelectedPointIdAttributeTheSelectionToNeither() {
        let first = Self.constructedSeries(id: Self.sharedId, name: "Australia", shape: .diamond,
                                           points: [Self.point("p", Self.heldX, 0.64)])
        let second = Self.constructedSeries(id: Self.sharedId, name: "Draw / tie", shape: .square,
                                            points: [Self.point("p", Self.heldX, 0.35)])
        let inspection = CricketHistoryInspection10868(x: Self.heldX, caption: "Selected", selections: [
            Self.sa: .point(id: "\(Self.sa)#day5-0", spoken: "3%"),
            Self.sharedId: .point(id: "p", spoken: "64%"),
        ])
        let input = Self.input(series: [Self.matchSeries(Self.sa), first, second], inspection: inspection)
        // The per-series helper alone resolves the point in BOTH series.
        XCTAssertNotNil(CricketHistoryGeometry10868.selectedPoint(first, inspection: inspection, domain: input.domain))
        XCTAssertNotNil(CricketHistoryGeometry10868.selectedPoint(second, inspection: inspection, domain: input.domain))
        for series in [first, second] {
            XCTAssertFalse(CricketHistoryGeometry10868.isExactlyIdentified(series, in: input), series.name)
            XCTAssertNil(CricketHistoryGeometry10868.inspectedPoint(series, in: input), series.name)
            XCTAssertNil(CricketHistoryGeometry10868.keyNote(series, in: input), series.name)
        }
        XCTAssertEqual(CricketHistoryGeometry10868.inspectedPoint(input.series[0], in: input)?.probability, 0.03)
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "Selected; South Africa: 3%")
        // Lines, marks and names are all kept.
        XCTAssertEqual(input.series.map(\.name), ["South Africa", "Australia", "Draw / tie"])
        XCTAssertEqual(CricketHistoryGeometry10868.marks(first, in: input.domain).map(\.probability), [0.64])
        XCTAssertEqual(CricketHistoryGeometry10868.marks(second, in: input.domain).map(\.probability), [0.35])
        XCTAssertEqual(CricketHistoryGeometry10868.marks(input.series[0], in: input.domain).count, 5)
    }

    func testTwoSeriesSharingAnIdWithDifferentPointIdsAttributeTheSelectionToNeither() {
        let first = Self.constructedSeries(id: Self.sharedId, name: "Australia", shape: .diamond,
                                           points: [Self.point("p1", Self.heldX, 0.64)])
        let second = Self.constructedSeries(id: Self.sharedId, name: "Draw / tie", shape: .square,
                                            points: [Self.point("p2", Self.heldX, 0.35)])
        let inspection = CricketHistoryInspection10868(x: Self.heldX, caption: "Selected", selections: [
            Self.sa: .point(id: "\(Self.sa)#day5-0", spoken: "3%"),
            Self.sharedId: .point(id: "p1", spoken: "64%"),
        ])
        let input = Self.input(series: [Self.matchSeries(Self.sa), first, second], inspection: inspection)
        // Alone, the per-series helper would ring the first and say its name.
        XCTAssertEqual(CricketHistoryGeometry10868.selectedPoint(first, inspection: inspection,
                                                                 domain: input.domain)?.id, "p1")
        XCTAssertNil(CricketHistoryGeometry10868.inspectedPoint(first, in: input))
        XCTAssertNil(CricketHistoryGeometry10868.inspectedPoint(second, in: input))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "Selected; South Africa: 3%")
        XCTAssertEqual(CricketHistoryGeometry10868.marks(first, in: input.domain).map(\.id), ["p1"])
        XCTAssertEqual(CricketHistoryGeometry10868.marks(second, in: input.domain).map(\.id), ["p2"])
    }

    func testAnEmptySeriesIdReceivesNoInspectionEvenWhenItIsTheOnlyOne() {
        let unnamed = Self.constructedSeries(id: "", name: "Draw / tie", shape: .square,
                                             points: [Self.point("t0", Self.heldX, 0.35)])
        let series = [Self.matchSeries(Self.sa), Self.matchSeries(Self.aus), unnamed]
        let pointHeld = Self.input(series: series, inspection: CricketHistoryInspection10868(
            x: Self.heldX, caption: "Selected", selections: ["": .point(id: "t0", spoken: "35%")]))
        XCTAssertNotNil(CricketHistoryGeometry10868.selectedPoint(unnamed, inspection: pointHeld.inspection,
                                                                  domain: pointHeld.domain))
        XCTAssertFalse(CricketHistoryGeometry10868.isExactlyIdentified(unnamed, in: pointHeld))
        XCTAssertNil(CricketHistoryGeometry10868.inspectedPoint(unnamed, in: pointHeld))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(pointHeld), "Selected")

        let absenceHeld = Self.input(series: series, inspection: CricketHistoryInspection10868(
            x: Self.heldX, caption: "Selected", selections: ["": .absent(words: "Not recorded")]))
        XCTAssertNil(CricketHistoryGeometry10868.inspectedAbsentWords(unnamed, in: absenceHeld))
        XCTAssertNil(CricketHistoryGeometry10868.keyNote(unnamed, in: absenceHeld))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(absenceHeld), "Selected")
        XCTAssertEqual(CricketHistoryGeometry10868.marks(unnamed, in: absenceHeld.domain).map(\.id), ["t0"])
    }

    func testAnAmbiguousInspectedAbsenceIsNotNotedButEachSeriesKeepsItsOwnAbsenceWords() {
        let drawn = Self.constructedSeries(id: Self.sharedId, name: "Australia", shape: .diamond,
                                           points: [Self.point("a0", Self.heldX, 0.64)],
                                           absentWords: "No recorded trades")
        let undrawn = Self.constructedSeries(id: Self.sharedId, name: "Draw / tie", shape: .square,
                                             points: [], absentWords: "No recorded trades")
        let inspection = CricketHistoryInspection10868(x: Self.heldX, caption: "Selected", selections: [
            Self.sa: .absent(words: "Not recorded"),
            Self.sharedId: .absent(words: "Not recorded"),
        ])
        let input = Self.input(series: [Self.matchSeries(Self.sa), drawn, undrawn], inspection: inspection)
        XCTAssertEqual(CricketHistoryGeometry10868.selectionAbsentWords(drawn, inspection: inspection), "Not recorded")
        XCTAssertNil(CricketHistoryGeometry10868.inspectedAbsentWords(drawn, in: input))
        XCTAssertNil(CricketHistoryGeometry10868.inspectedAbsentWords(undrawn, in: input))
        XCTAssertNil(CricketHistoryGeometry10868.keyNote(drawn, in: input))
        XCTAssertEqual(CricketHistoryGeometry10868.keyNote(undrawn, in: input), "No recorded trades")
        XCTAssertEqual(CricketHistoryGeometry10868.keyNote(input.series[0], in: input), "Not recorded")
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input),
                       "Selected; South Africa: Not recorded; Draw / tie: No recorded trades")
    }

    func testExactlyIdentifiedRetainedSeriesKeepTheirInspectionUnchanged() {
        let input = Self.input(series: Self.order.map { Self.matchSeries($0) },
                               inspection: Self.firstFrameInspection(absentTie: true))
        for series in input.series {
            XCTAssertTrue(CricketHistoryGeometry10868.isExactlyIdentified(series, in: input), series.name)
            XCTAssertEqual(CricketHistoryGeometry10868.inspectedPoint(series, in: input),
                           CricketHistoryGeometry10868.selectedPoint(series, inspection: input.inspection,
                                                                     domain: input.domain), series.name)
            XCTAssertEqual(CricketHistoryGeometry10868.inspectedAbsentWords(series, in: input),
                           CricketHistoryGeometry10868.selectionAbsentWords(series, inspection: input.inspection),
                           series.name)
        }
        XCTAssertEqual(input.series.map { CricketHistoryGeometry10868.inspectedPoint($0, in: input)?.probability },
                       [0.03, 0.64, nil])
        XCTAssertNil(CricketHistoryGeometry10868.keyNote(input.series[0], in: input))
        XCTAssertEqual(CricketHistoryGeometry10868.keyNote(input.series[2], in: input), "Not recorded")
        // A series not in the input is not identified by it.
        let twoOnly = Self.input(series: [Self.matchSeries(Self.sa), Self.matchSeries(Self.aus)])
        XCTAssertFalse(CricketHistoryGeometry10868.isExactlyIdentified(Self.matchSeries(Self.tie), in: twoOnly))
    }

    func testDuplicateOrEmptyWindowChoiceIdsStayVisibleButStaticAndUniqueNeighboursStayActionable() {
        let choices = [
            CricketHistoryWindowChoice10868(id: "day5", label: "Day 5", isSelected: true),
            CricketHistoryWindowChoice10868(id: "match", label: "Match", isSelected: false),
            CricketHistoryWindowChoice10868(id: "day5", label: "Day 5 again", isSelected: false),
            CricketHistoryWindowChoice10868(id: "", label: "Hourly", isSelected: false),
            CricketHistoryWindowChoice10868(id: "day4", label: "Day 4", isSelected: false),
        ]
        let window = CricketHistoryWindow10868.choices(groupLabel: "Cricket history window", choices: choices)
        let offered = CricketHistoryGeometry10868.offeredChoices(window, hasCallback: true)
        XCTAssertEqual(offered, choices)
        XCTAssertEqual(offered.map(\.label), ["Day 5", "Match", "Day 5 again", "Hourly", "Day 4"])
        XCTAssertEqual(offered.map { CricketHistoryGeometry10868.windowChoiceAction($0, among: offered) },
                       [nil, "match", nil, nil, "day4"])
        // The selected choice keeps its selected look even though it is static.
        XCTAssertEqual(offered.filter(\.isSelected).map(\.label), ["Day 5"])
        XCTAssertNil(CricketHistoryGeometry10868.windowChoiceAction(offered[0], among: offered))
    }

    func testNoCallbackOrNoChoicesOffersNothingAndAChoiceOutsideTheListSendsNothing() {
        let duplicate = CricketHistoryWindow10868.choices(groupLabel: "Cricket history window", choices: [
            CricketHistoryWindowChoice10868(id: "day5", label: "Day 5", isSelected: true),
            CricketHistoryWindowChoice10868(id: "day5", label: "Day 5 again", isSelected: false),
        ])
        XCTAssertTrue(CricketHistoryGeometry10868.offeredChoices(duplicate, hasCallback: false).isEmpty)
        XCTAssertTrue(CricketHistoryGeometry10868.offeredChoices(
            .choices(groupLabel: "Cricket history window", choices: []), hasCallback: true).isEmpty)
        let match = CricketHistoryWindowChoice10868(id: "match", label: "Match", isSelected: false)
        XCTAssertNil(CricketHistoryGeometry10868.windowChoiceAction(match, among: []))
        XCTAssertEqual(CricketHistoryGeometry10868.windowChoiceAction(match, among: [match]), "match")
        let view = CricketProbabilityHistoryPresentation10868(
            input: Self.input(series: Self.order.map { Self.matchSeries($0) }, window: duplicate))
        XCTAssertNil(view.onWindowChoice)

        let empty = Self.input(series: [], xTicks: [], inspection: CricketHistoryInspection10868(
            x: nil, caption: "Selected", selections: ["": .absent(words: "Not recorded")]))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(empty), "Selected")
        XCTAssertFalse(CricketHistoryGeometry10868.isExactlyIdentified(Self.matchSeries(Self.sa), in: empty))
    }

    // MARK: T20 match-progress markers

    // ARCHIVED raw values come from India–West Indies, second T20I, Ranchi,
    // October 9, 2026, as retained in
    // `shipping-adoption-20261027/T20-HISTORY-MARKERS-RETAINED-CASES.json`
    // (sha256 2828f0f0…fdf44a) and `T20-CHASE-REUSE-RETAINED-CASES.json`
    // (sha256 c7ef73fb…3003cb). Rediff report publication times:
    //   innings report 15:24:19Z (India 249/5; not the exact innings end)
    //   score reports 16:46:44Z (13 overs), 16:57:47Z (15), 17:06:58Z (17),
    //   17:12:01Z (18) — publication times, not exact ball times.
    // Two original Kalshi Yes contracts, each with its own minute bar end:
    //   pregame  12:57:00Z  IND 0.78  WI 0.23
    //   13 overs 16:46:00Z  IND 0.44  WI 0.57
    //   15 overs 16:57:00Z  IND 0.67  WI 0.34
    //   17 overs 17:06:00Z  IND 0.12  WI 0.89
    //   18 overs 17:12:00Z  IND 0.01  WI 0.99
    // Bar ends are not report, ball, trade or app-arrival clocks.
    //
    // CONSTRUCTED owner inputs (this leaf resolves none of them): the marker
    // ids, emphasis, labels, spoken and key words, every phase frame, the epoch
    // domain, the series/segment/point ids, one segment per archived bar (the
    // sparse checkpoints are not a connected history and are never joined
    // here), and every off-window, nonfinite, held-without-a-time, empty-label,
    // coincident, close, long-label and measured-size case.

    private static let ind = "kalshi:KXT20MATCH-26OCT090930WIIND-IND:yes"
    private static let wi = "kalshi:KXT20MATCH-26OCT090930WIIND-WI:yes"

    /// CONSTRUCTED owner domain: 12:00Z to 17:30Z.
    private static let t20Domain = CricketHistoryDomain10868(lower: 1_791_547_200, upper: 1_791_567_000)

    /// ARCHIVED report publication times.
    private static let inningsReportAt: Double = 1_791_559_459
    private static let scoreReportsAt: [Double] = [1_791_564_404, 1_791_565_067, 1_791_565_618, 1_791_565_921]

    private struct T20Bar {
        /// ARCHIVED minute bar end, seconds since 1970 (UTC).
        let x: Double
        /// ARCHIVED.
        let ind: Double
        let wi: Double
    }

    /// ARCHIVED: pregame, then the bars before the 13/15/17/18-over reports.
    private static let t20Bars: [T20Bar] = [
        T20Bar(x: 1_791_550_620, ind: 0.78, wi: 0.23),
        T20Bar(x: 1_791_564_360, ind: 0.44, wi: 0.57),
        T20Bar(x: 1_791_565_020, ind: 0.67, wi: 0.34),
        T20Bar(x: 1_791_565_560, ind: 0.12, wi: 0.89),
        T20Bar(x: 1_791_565_920, ind: 0.01, wi: 0.99),
    ]

    private static func t20Original(_ id: String, _ name: String, _ shape: CricketHistoryShape10868,
                                    through checkpoints: Int,
                                    value: (T20Bar) -> Double) -> CricketHistorySeries10868 {
        let segments = t20Bars.prefix(1 + checkpoints).enumerated().map { index, bar in
            segment("\(id)#bar-\(index)", [point("\(id)#bar-\(index)", bar.x, value(bar), pregame: index == 0)])
        }
        return CricketHistorySeries10868(id: id, name: name, shape: shape, tint: .gray,
                                         segments: segments, absentWords: nil)
    }

    /// The two originals through `checkpoints` score reports.
    private static func t20Series(through checkpoints: Int) -> [CricketHistorySeries10868] {
        [t20Original(ind, "India", .circle, through: checkpoints) { $0.ind },
         t20Original(wi, "West Indies", .diamond, through: checkpoints) { $0.wi }]
    }

    private static let t20Summary = "India circles and West Indies diamonds. Solid probability histories, zero to 100 percent. Hollow marks are pregame."

    private static func t20Input(through checkpoints: Int,
                                 inspection: CricketHistoryInspection10868? = nil) -> CricketHistoryInput10868 {
        input(series: t20Series(through: checkpoints), domain: t20Domain, xTicks: [],
              context: "Kalshi Yes contracts · times in your time zone (PDT)", summary: t20Summary,
              inspection: inspection,
              previous: CricketHistoryControl10868(label: "Previous T20 minute", isAvailable: true),
              next: CricketHistoryControl10868(label: "Next T20 minute", isAvailable: false))
    }

    /// CONSTRUCTED owner inspection at the 15-over bars.
    private static let t20Held = CricketHistoryInspection10868(x: 1_791_565_020, caption: "Selected · 9:57 AM", selections: [
        ind: .point(id: "\(ind)#bar-2", spoken: "67%"),
        wi: .point(id: "\(wi)#bar-2", spoken: "34%"),
    ])

    private static let t20Key = "Score-report publication times; not exact ball, innings-boundary or app-arrival times."

    private static let inningsMarker = CricketHistoryMarker10868(
        id: "constructed:innings-report", x: inningsReportAt, emphasis: .prominent, label: "Innings report",
        spoken: "India 249/5 after 20 overs. Score report published 8:24:19 AM PDT, October 9, 2026; not the exact innings end.",
        absentWords: nil)

    private static func scoreMarker(_ overs: String, _ x: Double, _ spoken: String) -> CricketHistoryMarker10868 {
        CricketHistoryMarker10868(id: "constructed:score-report:\(overs).0", x: x, emphasis: .subtle, label: nil,
                                  spoken: spoken, absentWords: nil)
    }

    private static let scoreMarkers = [
        scoreMarker("13", scoreReportsAt[0], "West Indies 170/3 after 13 overs. Score report published 9:46:44 AM PDT, October 9, 2026; not the exact ball time."),
        scoreMarker("15", scoreReportsAt[1], "West Indies 187/4 after 15 overs. Score report published 9:57:47 AM PDT, October 9, 2026; not the exact ball time."),
        scoreMarker("17", scoreReportsAt[2], "West Indies 223/4 after 17 overs. Score report published 10:06:58 AM PDT, October 9, 2026; not the exact ball time."),
        scoreMarker("18", scoreReportsAt[3], "West Indies 240/4 after 18 overs. Score report published 10:12:01 AM PDT, October 9, 2026; not the exact ball time."),
    ]

    private static let t20Markers = [inningsMarker] + scoreMarkers

    private static func t20Context(_ phase: CricketHistoryMarkerPhase10868,
                                   _ markers: [CricketHistoryMarker10868]) -> CricketHistoryMarkerContext10868 {
        CricketHistoryMarkerContext10868(phase: phase, markers: markers, key: t20Key)
    }

    private func markedArrangement(width: CGFloat, plotHeight: CGFloat = 302, y: CGSize, x: CGSize,
                                   markerFractions: [Double], markerSizes: [CGSize]) -> CricketHistoryMarkedArrangement10868 {
        CricketHistoryGeometry10868.markedPlotArrangement(
            width: width, plotHeight: plotHeight, inset: 8.5,
            yValues: [0, 0.5, 1], ySizes: [y, y, y],
            xFractions: [0, 0.5, 1], xSizes: [x, x, x],
            markerFractions: markerFractions, markerSizes: markerSizes,
            labelGap: 6, axisGap: 6, laneSpacing: 4, markerGap: 4)
    }

    func testRetainedT20ReportBarAndDomainEpochsEqualTheArchivedUTCClocks() {
        let iso = ISO8601DateFormatter()
        let expected: [(String, Double)] = [
            ("2026-10-09T15:24:19Z", Self.inningsReportAt),
            ("2026-10-09T16:46:44Z", Self.scoreReportsAt[0]), ("2026-10-09T16:57:47Z", Self.scoreReportsAt[1]),
            ("2026-10-09T17:06:58Z", Self.scoreReportsAt[2]), ("2026-10-09T17:12:01Z", Self.scoreReportsAt[3]),
            ("2026-10-09T12:57:00Z", Self.t20Bars[0].x), ("2026-10-09T16:46:00Z", Self.t20Bars[1].x),
            ("2026-10-09T16:57:00Z", Self.t20Bars[2].x), ("2026-10-09T17:06:00Z", Self.t20Bars[3].x),
            ("2026-10-09T17:12:00Z", Self.t20Bars[4].x),
            ("2026-10-09T12:00:00Z", Self.t20Domain.lower), ("2026-10-09T17:30:00Z", Self.t20Domain.upper),
        ]
        for (text, value) in expected {
            XCTAssertEqual(iso.date(from: text)?.timeIntervalSince1970, value, text)
        }
        XCTAssertEqual(Self.t20Markers.compactMap(\.x), [Self.inningsReportAt] + Self.scoreReportsAt)
    }

    func testNilOrEmptyMarkerContextKeepsTheHistoryItsLabelAndItsArrangementExactlyAsBefore() {
        let input = Self.t20Input(through: 2)
        let empty = CricketHistoryMarkerContext10868(phase: .completed, markers: [], key: Self.t20Key)
        for context in [nil, empty] {
            XCTAssertTrue(CricketHistoryGeometry10868.visibleMarkers(context, domain: input.domain).isEmpty)
            XCTAssertNil(CricketHistoryGeometry10868.markerKeyWords(context, domain: input.domain))
            XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: context,
                                                                   domain: input.domain), input.summary)
        }
        for width: CGFloat in [320, 375, 393, 768, 1024] {
            let plain = arrangement(width: width, y: Self.standardY, x: Self.standardX)
            let marked = markedArrangement(width: width, y: Self.standardY, x: Self.standardX,
                                           markerFractions: [], markerSizes: [])
            XCTAssertEqual(marked.base, plain, "\(width)")
            XCTAssertEqual(marked.frames, plain.frames, "\(width)")
            XCTAssertEqual(marked.band, 0)
            XCTAssertEqual(marked.markerRows, 0)
            XCTAssertTrue(marked.markerLabels.isEmpty)
        }
        XCTAssertNil(CricketProbabilityHistoryPresentation10868(input: input).markers)
    }

    func testBeforePlaySuppressesEverySuppliedLaterMarkerItsKeyAndItsSpeech() {
        let input = Self.t20Input(through: 0)
        let held = CricketHistoryMarker10868(id: "constructed:held", x: nil, emphasis: .subtle, label: "Held",
                                             spoken: "Held.", absentWords: "Time not recorded")
        let before = Self.t20Context(.before, Self.t20Markers + [held])
        // Every supplied marker lies inside the domain: the phase alone suppresses them.
        XCTAssertTrue(Self.t20Markers.allSatisfy { input.domain.contains($0.x!) })
        XCTAssertTrue(CricketHistoryGeometry10868.visibleMarkers(before, domain: input.domain).isEmpty)
        XCTAssertTrue(CricketHistoryGeometry10868.labelledMarkers(before, domain: input.domain).isEmpty)
        XCTAssertTrue(CricketHistoryGeometry10868.unavailableMarkerWords(before).isEmpty)
        XCTAssertNil(CricketHistoryGeometry10868.markerKeyWords(before, domain: input.domain))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: before,
                                                               domain: input.domain), Self.t20Summary)
        // The pregame marks are drawn as before.
        for series in input.series {
            let marks = CricketHistoryGeometry10868.marks(series, in: input.domain)
            XCTAssertEqual(marks.count, 1, series.name)
            XCTAssertTrue(marks.allSatisfy(\.isPregame), series.name)
        }
    }

    func testDuringFifteenOversDrawsTheOwnersThreeMarkersInTheOwnersOrder() {
        let input = Self.t20Input(through: 2)
        let during = Self.t20Context(.during, Array(Self.t20Markers.prefix(3)))
        let visible = CricketHistoryGeometry10868.visibleMarkers(during, domain: input.domain)
        XCTAssertEqual(visible.map(\.id), ["constructed:innings-report", "constructed:score-report:13.0",
                                           "constructed:score-report:15.0"])
        XCTAssertEqual(visible.compactMap(\.x), [Self.inningsReportAt, Self.scoreReportsAt[0], Self.scoreReportsAt[1]])
        XCTAssertEqual(visible.map(\.emphasis), [.prominent, .subtle, .subtle])
        XCTAssertEqual(CricketHistoryGeometry10868.labelledMarkers(during, domain: input.domain).compactMap(\.label),
                       ["Innings report"])
        XCTAssertEqual(CricketHistoryGeometry10868.markerKeyWords(during, domain: input.domain), Self.t20Key)
        // The owner's list is the membership: no clock cutoff is applied here.
        let allFive = Self.t20Context(.during, Self.t20Markers)
        XCTAssertEqual(CricketHistoryGeometry10868.visibleMarkers(allFive, domain: input.domain).count, 5)
    }

    func testCompletedDrawsTheInningsReportAndFourCheckpointsWithNoFinishMarker() {
        let input = Self.t20Input(through: 4)
        let final = Self.t20Context(.completed, Self.t20Markers)
        let visible = CricketHistoryGeometry10868.visibleMarkers(final, domain: input.domain)
        XCTAssertEqual(visible.map(\.id), Self.t20Markers.map(\.id))
        XCTAssertEqual(visible.count, 5)
        XCTAssertEqual(visible.filter { $0.emphasis == .prominent }.map(\.id), ["constructed:innings-report"])
        XCTAssertEqual(visible.compactMap(\.x).max(), Self.scoreReportsAt[3])
        XCTAssertFalse(visible.contains { $0.x == input.domain.upper })
        XCTAssertEqual(CricketHistoryGeometry10868.labelledMarkers(final, domain: input.domain).count, 1)
    }

    func testTwoIndependentOriginalsKeepTheirOwnValuesWithNoComplementOrBridge() {
        let before = Self.t20Input(through: 0)
        let pregame = before.series.map { CricketHistoryGeometry10868.marks($0, in: before.domain).map(\.probability) }
        XCTAssertEqual(pregame, [[0.78], [0.23]])
        XCTAssertEqual(pregame.flatMap { $0 }.reduce(0, +), 1.01, accuracy: 1e-9)
        let during = Self.t20Input(through: 2)
        let values = during.series.map { CricketHistoryGeometry10868.marks($0, in: during.domain).map(\.probability) }
        XCTAssertEqual(values, [[0.78, 0.44, 0.67], [0.23, 0.57, 0.34]])
        XCTAssertEqual(values[0][2] + values[1][2], 1.01, accuracy: 1e-9)
        for series in during.series {
            // One CONSTRUCTED segment per archived bar: marks, never a joined trace.
            XCTAssertTrue(CricketHistoryGeometry10868.lines(series, in: during.domain).isEmpty, series.name)
            XCTAssertEqual(CricketHistoryGeometry10868.marks(series, in: during.domain).count, 3, series.name)
        }
        XCTAssertTrue(CricketHistoryGeometry10868.showsPregameKey(during))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(during), "")
    }

    func testReportPublicationTimesStayApartFromTheQuoteBarEnds() {
        let input = Self.t20Input(through: 4)
        let visible = CricketHistoryGeometry10868.visibleMarkers(Self.t20Context(.completed, Self.t20Markers),
                                                                 domain: input.domain)
        let pointXs = Set(input.series.flatMap { $0.segments.flatMap(\.points) }.map(\.x))
        for marker in visible {
            XCTAssertFalse(pointXs.contains(marker.x!), "no observation is placed at \(marker.id)")
        }
        let rect = CricketHistoryGeometry10868.drawingRect(in: CGSize(width: 357, height: 302), inset: 8.5)
        for (index, reportAt) in Self.scoreReportsAt.enumerated() {
            let barEnd = Self.t20Bars[index + 1].x
            XCTAssertGreaterThan(reportAt, barEnd)
            XCTAssertLessThan(reportAt - barEnd, 60)
            XCTAssertNotEqual(CricketHistoryGeometry10868.xPosition(reportAt, domain: input.domain, in: rect),
                              CricketHistoryGeometry10868.xPosition(barEnd, domain: input.domain, in: rect))
        }
    }

    func testMarkersAtTheDomainEndsAreDrawnAndOffWindowOrNonfiniteMarkersAreNot() {
        func marker(_ id: String, _ x: Double?) -> CricketHistoryMarker10868 {
            CricketHistoryMarker10868(id: id, x: x, emphasis: .subtle, label: id, spoken: "spoken \(id)", absentWords: nil)
        }
        let context = CricketHistoryMarkerContext10868(phase: .completed, markers: [
            marker("lo", 0), marker("early", -1), marker("hi", 100), marker("late", 100.5),
            marker("nan", Double.nan), marker("inf", Double.infinity), marker("mid", 50),
        ], key: "Key.")
        XCTAssertEqual(CricketHistoryGeometry10868.visibleMarkers(context, domain: Self.unit).map(\.id), ["lo", "hi", "mid"])
        XCTAssertEqual(CricketHistoryGeometry10868.labelledMarkers(context, domain: Self.unit).compactMap(\.label),
                       ["lo", "hi", "mid"])
        XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: "Summary.", markers: context, domain: Self.unit),
                       "Summary. Key. spoken lo spoken hi spoken mid")
        // Endpoint guides sit inside the inset drawing frame, so their strokes stay whole.
        let drawing = CricketHistoryGeometry10868.drawingRect(in: CGSize(width: 300, height: 302), inset: 8.5)
        XCTAssertEqual(CricketHistoryGeometry10868.xPosition(0, domain: Self.unit, in: drawing), 8.5)
        XCTAssertEqual(CricketHistoryGeometry10868.xPosition(100, domain: Self.unit, in: drawing), 291.5)
        XCTAssertTrue(CricketHistoryGeometry10868.visibleMarkers(
            context, domain: CricketHistoryDomain10868(lower: 5, upper: 5)).isEmpty)
    }

    func testAMarkerHeldWithoutATimeKeepsOnlyItsOwnerWords() {
        let input = Self.t20Input(through: 1)
        let held = CricketHistoryMarker10868(id: "constructed:innings-report", x: nil, emphasis: .prominent,
                                             label: "Innings report", spoken: Self.inningsMarker.spoken,
                                             absentWords: "Innings report time not recorded")
        let during = Self.t20Context(.during, [held, Self.scoreMarkers[0]])
        XCTAssertEqual(CricketHistoryGeometry10868.visibleMarkers(during, domain: input.domain).map(\.id),
                       ["constructed:score-report:13.0"])
        XCTAssertTrue(CricketHistoryGeometry10868.labelledMarkers(during, domain: input.domain).isEmpty)
        XCTAssertEqual(CricketHistoryGeometry10868.unavailableMarkerWords(during), ["Innings report time not recorded"])
        XCTAssertEqual(CricketHistoryGeometry10868.markerKeyWords(during, domain: input.domain),
                       "\(Self.t20Key) · Innings report time not recorded")
        XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: during, domain: input.domain),
                       [Self.t20Summary, Self.t20Key, Self.scoreMarkers[0].spoken, "Innings report time not recorded"]
                        .joined(separator: " "))
        // With no guide drawn the key words stay out; the absence stays.
        let only = Self.t20Context(.completed, [held])
        XCTAssertEqual(CricketHistoryGeometry10868.markerKeyWords(only, domain: input.domain),
                       "Innings report time not recorded")
        XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: only, domain: input.domain),
                       "\(Self.t20Summary) Innings report time not recorded")
        // A position outside the window is not an absence: nothing is drawn or said.
        let offWindow = CricketHistoryMarker10868(id: "late", x: input.domain.upper + 60, emphasis: .subtle, label: "Late",
                                                  spoken: "Late.", absentWords: "Late time not recorded")
        let late = Self.t20Context(.completed, [offWindow])
        XCTAssertTrue(CricketHistoryGeometry10868.unavailableMarkerWords(late).isEmpty)
        XCTAssertNil(CricketHistoryGeometry10868.markerKeyWords(late, domain: input.domain))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: late, domain: input.domain),
                       Self.t20Summary)
    }

    func testUnlabelledAndEmptyLabelGuidesAreDrawnWithoutALabelSlot() {
        let input = Self.t20Input(through: 2)
        let blank = CricketHistoryMarker10868(id: "constructed:blank", x: Self.scoreReportsAt[1], emphasis: .subtle,
                                              label: "", spoken: Self.scoreMarkers[1].spoken, absentWords: nil)
        let context = Self.t20Context(.completed, [Self.inningsMarker, Self.scoreMarkers[0], blank])
        XCTAssertEqual(CricketHistoryGeometry10868.visibleMarkers(context, domain: input.domain).count, 3)
        XCTAssertEqual(CricketHistoryGeometry10868.labelledMarkers(context, domain: input.domain).map(\.id),
                       ["constructed:innings-report"])
        // Their meaning stays in the key and the spoken words.
        XCTAssertEqual(CricketHistoryGeometry10868.markerKeyWords(context, domain: input.domain), Self.t20Key)
        let spoken = CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: context, domain: input.domain)
        XCTAssertTrue(spoken.contains(Self.scoreMarkers[0].spoken))
        XCTAssertTrue(spoken.contains(Self.scoreMarkers[1].spoken))
    }

    func testCoincidentAndCloseMarkerLabelsTakeFurtherRowsAboveTheUnchangedPlot() {
        // CONSTRUCTED measured size.
        let size = CGSize(width: 90, height: 16)
        let a = markedArrangement(width: 393, y: Self.standardY, x: Self.standardX,
                                  markerFractions: [0.5, 0.5, 0.52, 0.9], markerSizes: [size, size, size, size])
        XCTAssertEqual(a.markerRows, 3)
        XCTAssertEqual(a.band, 16 * 3 + 4 * 2 + 4)
        XCTAssertEqual(a.base.plot, CGRect(x: 36, y: 60, width: 357, height: 302))
        XCTAssertEqual(a.base.height, 60 + 302 + 6 + 32)
        XCTAssertEqual(a.markerLabels.map(\.minY), [40, 20, 0, 40])
        XCTAssertTrue(a.markerLabels.allSatisfy { $0.maxY <= a.base.plot.minY })
        XCTAssertTrue(a.markerLabels.allSatisfy { $0.minX >= 0 && $0.maxX <= 393 && $0.width == 90 && $0.height == 16 })
        assertNoOverlapWithinLanes(a.markerLabels)
        XCTAssertEqual(a.markerLabels[0].midX, 36 + 8.5 + 170, accuracy: 1e-9)
        XCTAssertEqual(a.markerLabels[0].midX, a.markerLabels[1].midX, accuracy: 1e-9)
        XCTAssertEqual(a.markerLabels[3].maxX, 393, accuracy: 1e-9, "slid inward, never cut")
        let plain = arrangement(width: 393, y: Self.standardY, x: Self.standardX)
        XCTAssertEqual(a.base.xLabels, plain.xLabels.map { $0.offsetBy(dx: 0, dy: 60) })
        XCTAssertEqual(a.base.yLabels, plain.yLabels.map { $0.offsetBy(dx: 0, dy: 60) })
    }

    func testALongMarkerLabelKeepsItsWidthAndGrowsTheBandInsteadOfThePlot() {
        // CONSTRUCTED: the layout re-measures a label wider than the whole
        // width at that width, where it wraps onto more lines.
        let long = markedArrangement(width: 320, y: Self.standardY, x: Self.standardX,
                                     markerFractions: [0.1], markerSizes: [CGSize(width: 320, height: 48)])
        XCTAssertEqual(long.markerLabels, [CGRect(x: 0, y: 0, width: 320, height: 48)])
        XCTAssertEqual(long.band, 52)
        XCTAssertEqual(long.base.plot.height, 302)
        XCTAssertEqual(long.base.plot.minY, 52)
        // CONSTRUCTED accessibility sizes keep the owner's taller plot at every width.
        let label = CGSize(width: 140, height: 44)
        for width: CGFloat in [320, 375, 393, 768, 1024] {
            let ax = markedArrangement(width: width, plotHeight: 370, y: Self.axY, x: Self.axX,
                                       markerFractions: [0.2, 0.25, 0.9], markerSizes: [label, label, label])
            let plain = arrangement(width: width, plotHeight: 370, y: Self.axY, x: Self.axX)
            XCTAssertEqual(ax.base.plot.height, 370, "\(width)")
            XCTAssertEqual(ax.base.height, plain.height + ax.band, "\(width)")
            XCTAssertGreaterThanOrEqual(ax.markerRows, 2, "\(width)")
            XCTAssertTrue(ax.markerLabels.allSatisfy { $0.width == 140 && $0.height == 44 }, "never shrunk")
            XCTAssertTrue(ax.markerLabels.allSatisfy { $0.minX >= 0 && $0.maxX <= width && $0.maxY <= ax.base.plot.minY })
            assertNoOverlapWithinLanes(ax.markerLabels)
        }
    }

    func testSpokenMarkersFollowTheSummaryInTheOwnersOrderAndTheHeldValueIsUnchanged() {
        let input = Self.t20Input(through: 2, inspection: Self.t20Held)
        let during = Self.t20Context(.during, Array(Self.t20Markers.prefix(3)))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenLabel(summary: input.summary, markers: during, domain: input.domain),
                       [Self.t20Summary, Self.t20Key, Self.inningsMarker.spoken,
                        Self.scoreMarkers[0].spoken, Self.scoreMarkers[1].spoken].joined(separator: " "))
        XCTAssertEqual(CricketHistoryGeometry10868.spokenValue(input), "Selected · 9:57 AM; India: 67%; West Indies: 34%")
        XCTAssertNotEqual(CricketHistoryGeometry10868.cursorDash, CricketHistoryGeometry10868.markerDash)
    }

    func testMarkersLeaveThePlotPositionInspectionAndActionsExactlyAsHanded() {
        let input = Self.t20Input(through: 2, inspection: Self.t20Held)
        let during = Self.t20Context(.during, Array(Self.t20Markers.prefix(3)))
        let rect = CricketHistoryGeometry10868.drawingRect(in: CGSize(width: 357, height: 302), inset: 8.5)
        // A tap beside a guide reports the position under the finger; nothing snaps to the report.
        let guideX = CricketHistoryGeometry10868.xPosition(Self.scoreReportsAt[1], domain: input.domain, in: rect)
        let tapped = CricketHistoryGeometry10868.domainValue(atX: guideX - 3, domain: input.domain, in: rect)
        XCTAssertNotNil(tapped)
        XCTAssertLessThan(tapped!, Self.scoreReportsAt[1])
        // The held reading stays on the owner's exact bars, not the report.
        XCTAssertEqual(CricketHistoryGeometry10868.cursor(input.inspection, domain: input.domain), Self.t20Bars[2].x)
        for series in input.series {
            XCTAssertEqual(CricketHistoryGeometry10868.inspectedPoint(series, in: input)?.x, Self.t20Bars[2].x, series.name)
        }
        var reported: [Double] = []
        let view = CricketProbabilityHistoryPresentation10868(input: input, markers: during,
                                                              onPlotPosition: { reported.append($0) })
        XCTAssertEqual(view.markers, during)
        XCTAssertEqual(view.input, input)
        view.onPlotPosition?(1_791_565_000)
        XCTAssertEqual(reported, [1_791_565_000])
        XCTAssertNil(view.onPrevious)
        XCTAssertNil(view.onNext)
        XCTAssertNil(view.onExpand)
        XCTAssertNil(view.onWindowChoice)
        XCTAssertEqual(CricketHistoryGeometry10868.offered(input.previous, hasCallback: true), input.previous)
    }

    func testMarkerInputsCarryOnlyOwnerWordsAndGeometryAndTheHistoryInputIsUnchanged() {
        XCTAssertEqual(Set(Mirror(reflecting: Self.inningsMarker).children.compactMap(\.label)),
                       ["id", "x", "emphasis", "label", "spoken", "absentWords"])
        XCTAssertEqual(Set(Mirror(reflecting: Self.t20Context(.during, Self.t20Markers)).children.compactMap(\.label)),
                       ["phase", "markers", "key"])
        XCTAssertEqual(Set(Mirror(reflecting: Self.t20Input(through: 2)).children.compactMap(\.label)), [
            "title", "series", "domain", "yTicks", "xTicks", "context", "pregameKey", "summary",
            "plotHeight", "window", "inspection", "previous", "next", "expand",
        ])
    }
}
