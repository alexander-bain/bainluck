import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf named-field "Chance to win" history as a stateless
/// presentation leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it draws from: every original kept in the owner's order on one
/// shared domain and one owner ceiling, explicit runs never joined, invalid,
/// above-ceiling and out-of-domain points breaking the run (never clamped),
/// dashed comparisons only between explicit owner endpoints and only beside
/// their explanation, readouts bound to exact ids with their own reasons, the
/// identity and action guards, the inspection it draws and hands back, the
/// measured label lanes and the key fallback, and the spoken text. Nothing
/// here claims a rendered fit, a native runtime, an interaction or
/// accessibility qualification, or a production binding.
///
/// ARCHIVED raw values come from the Baycurrent Classic, October 8–11, 2026
/// (routes golf-reading / golf-journey; market 64266833 "Baycurrent Classic -
/// Winner", source datagolf, external id datagolf:pga:527:win), as retained
/// in `shipping-adoption-20261027/FIELD-HISTORY-RETAINED-CASES.json`
/// (sha256 2ef025c5…6158). Four real originals:
///   Michael Brennan       outcome 241857512  335 raw records
///   Xander Schauffele     outcome 242242520  321 raw records
///   Keith Mitchell        outcome 242242559  336 raw records
///   Michael Thorbjornsen  outcome 242242545  no history in this capture
/// Each record below is (raw index, UTC seconds, probability 0...1) exactly
/// as retained. They are a SAMPLED source receipt chosen by raw index, not
/// admitted continuous history and not a gap or freshness measurement.
/// Round boundaries R1–R4 are recorded-source clocks, not tee times. The
/// first 100% record (Brennan, raw 333, 2026-10-11T06:41:26.165769Z) is the
/// specimen's terminal OBSERVATION clock, not the official finish; later
/// records (raw 334/320/335) are original details, not current. The final
/// leaderboard (Brennan 1, Mitchell T2, Schauffele T4, Thorbjornsen T33) and
/// its percentage-valued win_prob fields are separate and never enter a plot.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// series/point/link/run/action/choice id, tint and shape assignment; the
/// split of records into before estimates and per-round runs; which before
/// estimates are linked and the link explanation; mark styles; every domain,
/// ceiling, tick, guide, break, caption, note, readout label, figure and
/// provenance string, summary and selection; the compressed coordinate; and
/// every invalid, duplicate, empty, ambiguous and measured-size case.
final class FieldProbabilityHistoryPresentation10868Tests: XCTestCase {

    // MARK: Retained records

    private struct Record {
        let index: Int
        /// ARCHIVED UTC timestamp, seconds since 1970.
        let x: Double
        /// ARCHIVED.
        let probability: Double
    }

    private static let brennan = "datagolf:64266833:241857512"
    private static let schauffele = "datagolf:64266833:242242520"
    private static let mitchell = "datagolf:64266833:242242559"
    private static let thorbjornsen = "datagolf:64266833:242242545"
    private static let order = [brennan, schauffele, mitchell, thorbjornsen]

    private static let names: [String: String] = [
        brennan: "Michael Brennan", schauffele: "Xander Schauffele",
        mitchell: "Keith Mitchell", thorbjornsen: "Michael Thorbjornsen",
    ]
    private static let shapes: [String: FieldHistoryShape10868] = [
        brennan: .circle, schauffele: .square, mitchell: .diamond, thorbjornsen: .circle,
    ]
    private static let tints: [String: Color] = [
        brennan: .blue, schauffele: .orange, mitchell: .pink, thorbjornsen: .teal,
    ]

    /// ARCHIVED.
    private static let records: [String: [Record]] = [
        brennan: [
            Record(index: 0, x: 1_791_162_518.821032, probability: 0.043067),
            Record(index: 1, x: 1_791_221_954.507306, probability: 0.026167),
            Record(index: 2, x: 1_791_292_120.644152, probability: 0.026017),
            Record(index: 3, x: 1_791_417_723.231914, probability: 0.024326),
            Record(index: 4, x: 1_791_418_273.058928, probability: 0.026065),
            Record(index: 44, x: 1_791_431_198.504366, probability: 0.027172),
            Record(index: 84, x: 1_791_504_114.271593, probability: 0.019567),
            Record(index: 85, x: 1_791_504_384.569832, probability: 0.020507),
            Record(index: 86, x: 1_791_504_676.020101, probability: 0.019935),
            Record(index: 128, x: 1_791_517_613.727811, probability: 0.023996),
            Record(index: 170, x: 1_791_590_492.1217, probability: 0.033625),
            Record(index: 171, x: 1_791_590_852.296237, probability: 0.030661),
            Record(index: 212, x: 1_791_603_722.599933, probability: 0.02315),
            Record(index: 254, x: 1_791_676_957.53247, probability: 0.161117),
            Record(index: 255, x: 1_791_677_227.544047, probability: 0.16231),
            Record(index: 294, x: 1_791_689_277.81553, probability: 0.137681),
            Record(index: 333, x: 1_791_700_886.165769, probability: 1.0),
            Record(index: 334, x: 1_791_756_535.891004, probability: 0.026017),
        ],
        schauffele: [
            Record(index: 0, x: 1_791_221_954.507306, probability: 0.089),
            Record(index: 1, x: 1_791_292_120.644152, probability: 0.086583),
            Record(index: 2, x: 1_791_417_723.231914, probability: 0.084473),
            Record(index: 3, x: 1_791_417_993.172825, probability: 0.090287),
            Record(index: 45, x: 1_791_430_568.436708, probability: 0.067438),
            Record(index: 87, x: 1_791_504_114.271593, probability: 0.022474),
            Record(index: 88, x: 1_791_504_384.569832, probability: 0.021344),
            Record(index: 89, x: 1_791_504_676.020101, probability: 0.023106),
            Record(index: 128, x: 1_791_516_714.901607, probability: 0.031027),
            Record(index: 167, x: 1_791_590_492.1217, probability: 0.002314),
            Record(index: 168, x: 1_791_590_852.296237, probability: 0.004669),
            Record(index: 207, x: 1_791_603_992.528698, probability: 0.063779),
            Record(index: 247, x: 1_791_676_957.53247, probability: 0.019508),
            Record(index: 248, x: 1_791_677_227.544047, probability: 0.020276),
            Record(index: 283, x: 1_791_687_746.039667, probability: 0.025383),
            Record(index: 319, x: 1_791_698_815.965994, probability: 0.0),
            Record(index: 320, x: 1_791_756_535.891004, probability: 0.086583),
        ],
        mitchell: [
            Record(index: 0, x: 1_791_221_954.507306, probability: 0.012467),
            Record(index: 1, x: 1_791_292_120.644152, probability: 0.012733),
            Record(index: 2, x: 1_791_417_723.231914, probability: 0.020489),
            Record(index: 3, x: 1_791_417_993.172825, probability: 0.019386),
            Record(index: 44, x: 1_791_430_568.436708, probability: 0.045702),
            Record(index: 86, x: 1_791_504_114.271593, probability: 0.030854),
            Record(index: 87, x: 1_791_504_384.569832, probability: 0.030558),
            Record(index: 88, x: 1_791_504_676.020101, probability: 0.031816),
            Record(index: 130, x: 1_791_517_884.732031, probability: 0.110319),
            Record(index: 172, x: 1_791_590_492.1217, probability: 0.167576),
            Record(index: 173, x: 1_791_590_852.296237, probability: 0.165373),
            Record(index: 214, x: 1_791_603_444.925694, probability: 0.117003),
            Record(index: 256, x: 1_791_676_957.53247, probability: 0.074947),
            Record(index: 257, x: 1_791_677_227.544047, probability: 0.073789),
            Record(index: 295, x: 1_791_689_277.81553, probability: 0.469608),
            Record(index: 334, x: 1_791_700_886.165769, probability: 0.0),
            Record(index: 335, x: 1_791_756_535.891004, probability: 0.012733),
        ],
        thorbjornsen: [],
    ]

    /// ARCHIVED raw_start, round boundary clocks and the terminal observation.
    private static let rawStart: Double = 1_791_417_600
    private static let roundClocks: [(String, Double)] = [
        ("R1", 1_791_417_723.231914), ("R2", 1_791_504_121.806162),
        ("R3", 1_791_590_492.1217), ("R4", 1_791_676_957.53247),
    ]
    private static let terminal: Double = 1_791_700_886.165769

    /// CONSTRUCTED split of the retained raw indexes into before estimates and
    /// one owner run per round.
    private static let beforeIndexes: [String: [Int]] = [
        brennan: [0, 1, 2], schauffele: [0, 1], mitchell: [0, 1], thorbjornsen: [],
    ]
    private static let roundIndexes: [String: [[Int]]] = [
        brennan: [[3, 4, 44], [84, 85, 86, 128], [170, 171, 212], [254, 255, 294, 333]],
        schauffele: [[2, 3, 45], [87, 88, 89, 128], [167, 168, 207], [247, 248, 283, 319]],
        mitchell: [[2, 3, 44], [86, 87, 88, 130], [172, 173, 214], [256, 257, 295, 334]],
        thorbjornsen: [],
    ]
    /// ARCHIVED later records, outside the terminal observation clock.
    private static let laterIndex: [String: Int] = [brennan: 334, schauffele: 320, mitchell: 335]

    // MARK: Constructed owner inputs

    /// CONSTRUCTED: Oct 5 00:00Z to raw_start (before the tournament).
    private static let beforeDomain = FieldHistoryDomain10868(lower: 1_791_158_400, upper: rawStart)
    /// CONSTRUCTED: raw_start to the terminal observation clock.
    private static let weekDomain = FieldHistoryDomain10868(lower: rawStart, upper: terminal)

    private static func percentTicks(_ ceiling: Double, _ words: [String]) -> [FieldHistoryTick10868] {
        [FieldHistoryTick10868(value: 0, lines: [words[0]]),
         FieldHistoryTick10868(value: ceiling / 2, lines: [words[1]]),
         FieldHistoryTick10868(value: ceiling, lines: [words[2]])]
    }

    private static let autoBeforeTicks = percentTicks(0.10, ["0%", "5%", "10%"])
    private static let fullTicks = percentTicks(1.0, ["0%", "50%", "100%"])
    private static let weekTicks = percentTicks(0.5, ["0%", "25%", "50%"])

    private static let roundGuides = roundClocks.map { FieldHistoryGuide10868(id: "guide:\($0.0)", x: $0.1, label: $0.0) }

    private static func record(_ series: String, _ index: Int) -> Record {
        records[series]!.first { $0.index == index }!
    }

    private static func pid(_ series: String, _ index: Int) -> String { "\(series)#\(index)" }

    private static func point(_ series: String, _ index: Int,
                              style: FieldHistoryMarkStyle10868 = .filled) -> FieldHistoryPoint10868 {
        let r = record(series, index)
        return FieldHistoryPoint10868(id: pid(series, index), x: r.x, probability: r.probability, style: style)
    }

    private static func run(_ id: String, _ points: [FieldHistoryPoint10868]) -> FieldHistoryRun10868 {
        FieldHistoryRun10868(id: id, points: points)
    }

    private static func action(_ id: String, _ label: String, available: Bool = true,
                               spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: available)
    }

    private static func series(_ id: String,
                               runs: [FieldHistoryRun10868],
                               links: [FieldHistoryComparisonLink10868] = [],
                               labelPointID: String? = nil,
                               before: FieldHistoryReading10868 = .absent(words: "No before-event estimate"),
                               recorded: FieldHistoryReading10868 = .absent(words: "Not recorded"),
                               absentWords: String? = "No captured history",
                               choose: FieldHistoryAction10868? = nil,
                               overrideID: String? = nil) -> FieldHistorySeries10868 {
        FieldHistorySeries10868(id: overrideID ?? id, name: names[id]!, shape: shapes[id]!, tint: tints[id]!,
                                runs: runs, links: links, labelPointID: labelPointID,
                                before: before, recorded: recorded, absentWords: absentWords, choose: choose)
    }

    /// Before estimates as one single-point owner run each (hollow earlier,
    /// filled last), with explicit comparison links between neighbours.
    private static func beforeSeries(_ id: String, linked: Bool = true) -> FieldHistorySeries10868 {
        let indexes = beforeIndexes[id]!
        let points = indexes.enumerated().map { offset, index in
            point(id, index, style: offset == indexes.count - 1 ? .filled : .hollow)
        }
        let links: [FieldHistoryComparisonLink10868] = linked
            ? zip(indexes, indexes.dropFirst()).map {
                FieldHistoryComparisonLink10868(id: "\(id)#link-\($0)-\($1)",
                                                fromPointID: pid(id, $0), toPointID: pid(id, $1))
            }
            : []
        let last = indexes.last.map { pid(id, $0) }
        return series(id,
                      runs: points.map { run("\($0.id)#run", [$0]) },
                      links: links,
                      labelPointID: last,
                      before: last.map { FieldHistoryReading10868.observation(pointID: $0, figure: "figure", provenance: "Oct 6 · DataGolf") }
                          ?? .absent(words: "No before-event estimate"),
                      choose: action("choose:\(id)", "Choose \(names[id]!)"))
    }

    /// One owner run per round, labelled at the owner's chosen point.
    private static func weekSeries(_ id: String, rounds: Int = 4, labelAt: Int? = nil) -> FieldHistorySeries10868 {
        let runs = roundIndexes[id]!.prefix(rounds).enumerated().map { offset, indexes in
            run("\(id)#R\(offset + 1)", indexes.map { point(id, $0) })
        }
        return series(id, runs: Array(runs), labelPointID: labelAt.map { pid(id, $0) },
                      choose: action("choose:\(id)", "Choose \(names[id]!)"))
    }

    private static func input(series: [FieldHistorySeries10868],
                              selection: FieldHistoryOriginalSelection10868 = .none,
                              domain: FieldHistoryDomain10868 = weekDomain,
                              ceiling: Double = 0.5,
                              yTicks: [FieldHistoryTick10868] = weekTicks,
                              xTicks: [FieldHistoryTick10868] = [],
                              guides: [FieldHistoryGuide10868] = roundGuides,
                              breaks: [FieldHistoryBreak10868] = [],
                              readout: FieldHistoryReadoutIntent10868 = .beforeAndRecorded(
                                  beforeLabel: "Before tournament", recordedLabel: "Recorded"),
                              markKey: FieldHistoryMarkKey10868 = FieldHistoryMarkKey10868(hollow: nil, filled: nil),
                              comparisonExplanation: String? = nil,
                              windows: FieldHistoryWindows10868? = nil,
                              scale: FieldHistoryAction10868? = nil,
                              moreOriginals: FieldHistoryAction10868? = nil,
                              details: FieldHistoryAction10868? = nil,
                              expand: FieldHistoryAction10868? = nil,
                              inspect: FieldHistoryAction10868? = nil,
                              previous: FieldHistoryAction10868? = nil,
                              next: FieldHistoryAction10868? = nil,
                              inspection: FieldHistoryInspection10868? = nil) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: "Chance to win", caption: "Recorded · Week", series: series, selection: selection,
            domain: domain, ceiling: ceiling, yTicks: yTicks, xTicks: xTicks, guides: guides, breaks: breaks,
            readout: readout, markKey: markKey, comparisonExplanation: comparisonExplanation,
            notes: ["DataGolf model history · times in your time zone (EDT)"],
            summary: "Win probability for the chosen golfers on one shared tournament clock.",
            plotHeight: 240, unboundReadingWords: "Not recorded",
            plotUnavailableWords: "History unavailable", windows: windows, scale: scale,
            moreOriginals: moreOriginals, details: details, expand: expand, inspect: inspect,
            previous: previous, next: next, inspection: inspection)
    }

    private static func beforeInput(ceiling: Double = 0.10,
                                    yTicks: [FieldHistoryTick10868] = autoBeforeTicks,
                                    explanation: String? = "Dashed links compare recorded estimates, not a continuous history.")
        -> FieldHistoryInput10868 {
        input(series: order.map { beforeSeries($0) }, domain: beforeDomain, ceiling: ceiling, yTicks: yTicks,
              guides: [], readout: .singleBefore(label: "Before tournament · last estimate"),
              markKey: FieldHistoryMarkKey10868(hollow: "Earlier estimates", filled: "Latest estimate"),
              comparisonExplanation: explanation)
    }

    private static let rect = CGRect(x: 10, y: 10, width: 200, height: 100)

    private func ids(_ runs: [[FieldHistoryPoint10868]]) -> [[String]] { runs.map { $0.map(\.id) } }
    private func ids(_ points: [FieldHistoryPoint10868]) -> [String] { points.map(\.id) }
    private func pairIDs(_ links: [(FieldHistoryPoint10868, FieldHistoryPoint10868)]) -> [[String]] {
        links.map { [$0.0.id, $0.1.id] }
    }

    // MARK: Retained cases

    func testRetainedEpochConstantsEqualTheArchivedUTCClocks() {
        let iso = ISO8601DateFormatter()
        let expected: [(String, Double)] = [
            ("2026-10-05T01:08:38Z", Self.record(Self.brennan, 0).x),
            ("2026-10-06T13:08:40Z", Self.record(Self.brennan, 2).x),
            ("2026-10-08T00:00:00Z", Self.rawStart),
            ("2026-10-08T00:02:03Z", Self.roundClocks[0].1), ("2026-10-09T00:02:01Z", Self.roundClocks[1].1),
            ("2026-10-10T00:01:32Z", Self.roundClocks[2].1), ("2026-10-11T00:02:37Z", Self.roundClocks[3].1),
            ("2026-10-11T06:06:55Z", Self.record(Self.schauffele, 319).x),
            ("2026-10-11T06:41:26Z", Self.terminal),
            ("2026-10-11T22:08:55Z", Self.record(Self.brennan, 334).x),
        ]
        for (text, value) in expected {
            XCTAssertEqual(iso.date(from: text)!.timeIntervalSince1970, value.rounded(.down), text)
        }
        XCTAssertEqual(Self.record(Self.brennan, 333).x, Self.terminal)
        XCTAssertEqual(Self.record(Self.mitchell, 334).x, Self.terminal)
    }

    func testEveryRetainedOriginalIsKeptInTheOwnersOrderWithItsOwnIdentity() {
        let input = Self.input(series: Self.order.map { Self.weekSeries($0) })
        XCTAssertEqual(input.series.map(\.id), Self.order)
        XCTAssertEqual(input.series.map(\.name),
                       ["Michael Brennan", "Xander Schauffele", "Keith Mitchell", "Michael Thorbjornsen"])
        XCTAssertEqual(Set(input.series.prefix(3).map(\.shape)), Set([FieldHistoryShape10868.circle, .square, .diamond]))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(input.series[3], in: input).count, 2)
        // Reversed cohort order is drawn reversed; nothing is re-sorted.
        let reversed = Self.input(series: Self.order.reversed().map { Self.weekSeries($0) })
        XCTAssertEqual(reversed.series.map(\.id), Self.order.reversed())
    }

    // MARK: Scale

    func testLowProbabilityBeforeScaleDrawsEveryRetainedEstimate() {
        let input = Self.beforeInput()
        let marks = input.series.map { FieldHistoryGeometry10868.marks($0, in: input) }
        XCTAssertEqual(marks.map { $0.count }, [3, 2, 2, 0])
        let top = FieldHistoryGeometry10868.position(marks[1][0], in: input, rect: Self.rect)
        XCTAssertEqual(top.y, 110 - 0.89 * 100, accuracy: 1e-9) // 0.089 of a 0.10 ceiling
        XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(input).map(\.lines), [["0%"], ["5%"], ["10%"]])
    }

    func testFullScaleDrawsTheSameProbabilitiesUnchangedAtTheSameTimes() {
        let auto = Self.beforeInput()
        let full = Self.beforeInput(ceiling: 1.0, yTicks: Self.fullTicks)
        for index in 0..<3 {
            let a = FieldHistoryGeometry10868.marks(auto.series[index], in: auto)
            let f = FieldHistoryGeometry10868.marks(full.series[index], in: full)
            XCTAssertEqual(a, f)
            for (pa, pf) in zip(a, f) {
                let ca = FieldHistoryGeometry10868.position(pa, in: auto, rect: Self.rect)
                let cf = FieldHistoryGeometry10868.position(pf, in: full, rect: Self.rect)
                XCTAssertEqual(ca.x, cf.x, accuracy: 1e-9)
                XCTAssertEqual(cf.y, 110 - CGFloat(pf.probability) * 100, accuracy: 1e-9)
            }
        }
        XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(full).map(\.lines), [["0%"], ["50%"], ["100%"]])
    }

    func testAboveCeilingPointBreaksTheRunWithoutClamping() {
        // Brennan's R4 run at a CONSTRUCTED 0–10% scale: 16.1%, 16.2%, 13.8%
        // and 100% are not drawn, and nothing runs toward the top edge.
        let r4 = Self.run("r4", [Self.point(Self.brennan, 212), Self.point(Self.brennan, 254),
                                 Self.point(Self.brennan, 255), Self.point(Self.brennan, 294),
                                 Self.point(Self.brennan, 333)])
        let input = Self.input(series: [Self.series(Self.brennan, runs: [r4])], ceiling: 0.10,
                               yTicks: Self.autoBeforeTicks)
        XCTAssertEqual(ids(FieldHistoryGeometry10868.marks(input.series[0], in: input)), [Self.pid(Self.brennan, 212)])
        XCTAssertTrue(FieldHistoryGeometry10868.lines(input.series[0], in: input).isEmpty)
    }

    func testYTicksOutsideTheCeilingAreNotPlaced() {
        let input = Self.input(series: [], ceiling: 0.10, yTicks: Self.fullTicks)
        XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(input).map(\.lines), [["0%"]])
    }

    func testInvalidDomainOrCeilingDrawsNoNumericMarks() {
        let week = Self.weekSeries(Self.mitchell)
        for ceiling in [0, -0.1, 1.5, Double.nan, Double.infinity] {
            let input = Self.input(series: [week], ceiling: ceiling)
            XCTAssertFalse(FieldHistoryGeometry10868.isDrawable(input), "\(ceiling)")
            XCTAssertTrue(FieldHistoryGeometry10868.marks(week, in: input).isEmpty)
            XCTAssertTrue(FieldHistoryGeometry10868.placedYTicks(input).isEmpty)
            XCTAssertTrue(FieldHistoryGeometry10868.placedGuides(input).isEmpty)
        }
        for domain in [FieldHistoryDomain10868(lower: Self.terminal, upper: Self.rawStart),
                       FieldHistoryDomain10868(lower: Self.rawStart, upper: Self.rawStart),
                       FieldHistoryDomain10868(lower: .nan, upper: Self.terminal)] {
            let input = Self.input(series: [week], domain: domain)
            XCTAssertFalse(FieldHistoryGeometry10868.isDrawable(input))
            XCTAssertTrue(FieldHistoryGeometry10868.lines(week, in: input).isEmpty)
            XCTAssertNil(FieldHistoryGeometry10868.domainValue(atX: 50, domain: domain, in: Self.rect))
        }
        XCTAssertTrue(FieldHistoryGeometry10868.isValidCeiling(1))
        XCTAssertTrue(FieldHistoryGeometry10868.isValidCeiling(0.10))
    }

    // MARK: Before estimates and comparison links

    func testBeforeSingletonIsOneMarkWithNoLine() {
        let single = Self.series(Self.mitchell, runs: [Self.run("before", [Self.point(Self.mitchell, 1)])])
        let input = Self.input(series: [single], domain: Self.beforeDomain, ceiling: 0.10, yTicks: Self.autoBeforeTicks)
        XCTAssertEqual(ids(FieldHistoryGeometry10868.marks(single, in: input)), [Self.pid(Self.mitchell, 1)])
        XCTAssertTrue(FieldHistoryGeometry10868.lines(single, in: input).isEmpty)
    }

    func testSparseComparisonLinksJoinOnlyTheOwnersExplicitEndpoints() {
        let input = Self.beforeInput()
        let brennan = input.series[0]
        XCTAssertEqual(pairIDs(FieldHistoryGeometry10868.comparisonLinks(brennan, in: input)),
                       [[Self.pid(Self.brennan, 0), Self.pid(Self.brennan, 1)],
                        [Self.pid(Self.brennan, 1), Self.pid(Self.brennan, 2)]])
        // Comparisons, not history: no solid line and no invented observation.
        XCTAssertTrue(FieldHistoryGeometry10868.lines(brennan, in: input).isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.marks(brennan, in: input).count, 3)
        XCTAssertTrue(FieldHistoryGeometry10868.drawsComparisonLink(input))
        XCTAssertTrue(FieldHistoryGeometry10868.comparisonLinks(input.series[3], in: input).isEmpty)
    }

    func testComparisonLinksNeedTheirVisibleExplanation() {
        for explanation in [nil, ""] as [String?] {
            let input = Self.beforeInput(explanation: explanation)
            XCTAssertFalse(FieldHistoryGeometry10868.showsComparisonExplanation(input))
            XCTAssertTrue(input.series.allSatisfy { FieldHistoryGeometry10868.comparisonLinks($0, in: input).isEmpty })
            XCTAssertFalse(FieldHistoryGeometry10868.drawsComparisonLink(input))
        }
    }

    func testLinksAreNeverBuiltFromDatesOrArrayOrder() {
        let unlinked = Self.beforeSeries(Self.brennan, linked: false)
        let input = Self.input(series: [unlinked], domain: Self.beforeDomain, ceiling: 0.10,
                               yTicks: Self.autoBeforeTicks, comparisonExplanation: "Dashed links compare estimates.")
        XCTAssertTrue(FieldHistoryGeometry10868.comparisonLinks(unlinked, in: input).isEmpty)
        XCTAssertTrue(FieldHistoryGeometry10868.lines(unlinked, in: input).isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.marks(unlinked, in: input).count, 3)
    }

    func testUnknownDuplicateSameOrUnplaceableLinkEndpointsDrawNoLink() {
        let a = Self.point(Self.brennan, 1), b = Self.point(Self.brennan, 2)
        let twin = FieldHistoryPoint10868(id: b.id, x: b.x - 60, probability: b.probability, style: .hollow)
        let high = FieldHistoryPoint10868(id: "high", x: b.x + 60, probability: 0.2, style: .hollow)
        let links = [
            FieldHistoryComparisonLink10868(id: "unknown", fromPointID: a.id, toPointID: "missing"),
            FieldHistoryComparisonLink10868(id: "same", fromPointID: a.id, toPointID: a.id),
            FieldHistoryComparisonLink10868(id: "twin", fromPointID: a.id, toPointID: b.id),
            FieldHistoryComparisonLink10868(id: "empty", fromPointID: "", toPointID: a.id),
            FieldHistoryComparisonLink10868(id: "high", fromPointID: a.id, toPointID: "high"),
        ]
        let series = Self.series(Self.brennan, runs: [Self.run("a", [a]), Self.run("b", [b]),
                                                      Self.run("t", [twin]), Self.run("h", [high])],
                                 links: links)
        let input = Self.input(series: [series], domain: Self.beforeDomain, ceiling: 0.10,
                               yTicks: Self.autoBeforeTicks, comparisonExplanation: "Dashed links compare estimates.")
        XCTAssertTrue(FieldHistoryGeometry10868.comparisonLinks(series, in: input).isEmpty)
    }

    func testMarkStyleKeyAppearsOnlyForStylesThatAreDrawn() {
        let before = Self.beforeInput()
        XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.hollow, in: before))
        XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.filled, in: before))
        let week = Self.input(series: [Self.weekSeries(Self.brennan)])
        XCTAssertFalse(FieldHistoryGeometry10868.drawsStyle(.hollow, in: week))
        // A style is never inferred from equal values: Brennan's before
        // 0.026017 and later 0.026017 keep the styles the owner gave them.
        let equal = Self.series(Self.brennan, runs: [Self.run("a", [Self.point(Self.brennan, 2, style: .hollow)]),
                                                     Self.run("b", [Self.point(Self.brennan, 334)])])
        let wide = Self.input(series: [equal], domain: FieldHistoryDomain10868(lower: 1_791_158_400, upper: 1_791_760_000),
                              ceiling: 0.10, yTicks: Self.autoBeforeTicks)
        XCTAssertEqual(FieldHistoryGeometry10868.marks(equal, in: wide).map(\.style), [.hollow, .filled])
    }

    // MARK: Recorded and final history

    func testRecordedRunsDrawSolidLinesOnlyInsideOwnerRuns() {
        let mitchell = Self.weekSeries(Self.mitchell)
        let input = Self.input(series: [mitchell])
        let lines = FieldHistoryGeometry10868.lines(mitchell, in: input)
        XCTAssertEqual(lines.count, 4)
        XCTAssertEqual(ids(lines).map { $0.first! }, ["2", "86", "172", "256"].map { "\(Self.mitchell)#\($0)" })
        // R4 includes the real 46.96% under a CONSTRUCTED 0–50% ceiling, and
        // the real 0% at the terminal observation clock.
        XCTAssertEqual(lines[3].map(\.probability), [0.074947, 0.073789, 0.469608, 0.0])
    }

    func testFinalHistoryKeepsAGenuineOneAtFullScale() {
        let brennan = Self.weekSeries(Self.brennan)
        let input = Self.input(series: [brennan], ceiling: 1.0, yTicks: Self.fullTicks)
        let marks = FieldHistoryGeometry10868.marks(brennan, in: input)
        XCTAssertEqual(marks.last?.id, Self.pid(Self.brennan, 333))
        XCTAssertEqual(marks.last?.probability, 1.0)
        XCTAssertEqual(FieldHistoryGeometry10868.position(marks.last!, in: input, rect: Self.rect).y, Self.rect.minY)
        XCTAssertEqual(FieldHistoryGeometry10868.lines(brennan, in: input).last?.count, 4)
    }

    func testAGenuineOneIsNotDrawnUnderACroppedCeilingAndNeverClamped() {
        let brennan = Self.weekSeries(Self.brennan)
        let input = Self.input(series: [brennan], ceiling: 0.5)
        let r4 = FieldHistoryGeometry10868.lines(brennan, in: input).last!
        XCTAssertEqual(ids(r4), [254, 255, 294].map { Self.pid(Self.brennan, $0) })
        XCTAssertFalse(FieldHistoryGeometry10868.marks(brennan, in: input).contains { $0.probability > 0.5 })
    }

    func testRealZeroIsAValue() {
        let input = Self.input(series: [Self.weekSeries(Self.schauffele), Self.weekSeries(Self.mitchell)])
        let zeros = input.series.flatMap { FieldHistoryGeometry10868.marks($0, in: input) }.filter { $0.probability == 0 }
        XCTAssertEqual(ids(zeros), [Self.pid(Self.schauffele, 319), Self.pid(Self.mitchell, 334)])
        XCTAssertEqual(FieldHistoryGeometry10868.position(zeros[0], in: input, rect: Self.rect).y, Self.rect.maxY)
    }

    func testNothingIsSynthesizedFromAWinnerOrAFinish() {
        // Mitchell finished T2 and Schauffele T4 with win_prob 0.0 (percent)
        // in the final record; Brennan won. The leaf takes no result, so its
        // marks are exactly the supplied placeable observations.
        let input = Self.input(series: Self.order.map { Self.weekSeries($0) }, ceiling: 1.0, yTicks: Self.fullTicks)
        for series in input.series {
            let supplied = series.runs.flatMap(\.points)
            XCTAssertEqual(FieldHistoryGeometry10868.marks(series, in: input), supplied)
        }
        XCTAssertFalse(FieldHistoryGeometry10868.marks(input.series[2], in: input).contains { $0.probability == 1 })
        XCTAssertTrue(FieldHistoryGeometry10868.marks(input.series[3], in: input).isEmpty)
    }

    func testLaterRecordsOutsideTheTerminalObservationClockAreNotDrawn() {
        for (id, later) in Self.laterIndex {
            let run = Self.run("tail", [Self.point(id, Self.roundIndexes[id]![3].last!), Self.point(id, later)])
            let series = Self.series(id, runs: [run])
            let input = Self.input(series: [series], ceiling: 1.0, yTicks: Self.fullTicks)
            XCTAssertEqual(ids(FieldHistoryGeometry10868.marks(series, in: input)),
                           [Self.pid(id, Self.roundIndexes[id]![3].last!)], id)
            XCTAssertTrue(FieldHistoryGeometry10868.lines(series, in: input).isEmpty, id)
        }
    }

    // MARK: Path breaks

    func testNonfiniteFutureAndOutOfRangePointsBreakTheRun() {
        let base = Self.record(Self.schauffele, 87).x
        let points = [
            FieldHistoryPoint10868(id: "a", x: base, probability: 0.02, style: .filled),
            FieldHistoryPoint10868(id: "b", x: base + 60, probability: .nan, style: .filled),
            FieldHistoryPoint10868(id: "c", x: base + 120, probability: 0.03, style: .filled),
            FieldHistoryPoint10868(id: "d", x: base + 180, probability: 0.04, style: .filled),
            FieldHistoryPoint10868(id: "e", x: base + 240, probability: -0.01, style: .filled),
            FieldHistoryPoint10868(id: "f", x: base + 300, probability: 0.05, style: .filled),
            FieldHistoryPoint10868(id: "g", x: .infinity, probability: 0.05, style: .filled),
            FieldHistoryPoint10868(id: "h", x: base + 360, probability: 0.06, style: .filled),
            FieldHistoryPoint10868(id: "i", x: Self.terminal + 1, probability: 0.06, style: .filled),
            FieldHistoryPoint10868(id: "j", x: base + 420, probability: 0.07, style: .filled),
        ]
        let series = Self.series(Self.schauffele, runs: [Self.run("r", points)])
        let input = Self.input(series: [series])
        XCTAssertEqual(ids(FieldHistoryGeometry10868.drawnRuns(series.runs[0], in: input)),
                       [["a"], ["c", "d"], ["f"], ["h"], ["j"]])
        XCTAssertEqual(ids(FieldHistoryGeometry10868.lines(series, in: input)), [["c", "d"]])
    }

    func testAnXThatDoesNotAdvanceBreaksTheRun() {
        let base = Self.record(Self.mitchell, 86).x
        let points = [
            FieldHistoryPoint10868(id: "a", x: base, probability: 0.03, style: .filled),
            FieldHistoryPoint10868(id: "b", x: base + 60, probability: 0.04, style: .filled),
            FieldHistoryPoint10868(id: "c", x: base + 60, probability: 0.05, style: .filled),
            FieldHistoryPoint10868(id: "d", x: base + 30, probability: 0.06, style: .filled),
        ]
        let series = Self.series(Self.mitchell, runs: [Self.run("r", points)])
        XCTAssertEqual(ids(FieldHistoryGeometry10868.drawnRuns(series.runs[0], in: Self.input(series: [series]))),
                       [["a", "b"], ["c"], ["d"]])
    }

    func testAnExplicitBreakSplitsARunAndNeverGetsAJoiningLine() {
        // One CONSTRUCTED owner run across R1 and R2 with a break between
        // Brennan's last R1 record (03:46Z Oct 8) and first R2 record.
        let points = [3, 4, 44, 84, 85].map { Self.point(Self.brennan, $0) }
        let series = Self.series(Self.brennan, runs: [Self.run("r1-r2", points)])
        let gap = FieldHistoryBreak10868(id: "night-1", lower: Self.record(Self.brennan, 44).x + 600,
                                         upper: Self.record(Self.brennan, 84).x - 600, mark: "//")
        let input = Self.input(series: [series], breaks: [gap])
        XCTAssertEqual(ids(FieldHistoryGeometry10868.lines(series, in: input)),
                       [[3, 4, 44].map { Self.pid(Self.brennan, $0) }, [84, 85].map { Self.pid(Self.brennan, $0) }])
        XCTAssertEqual(ids(FieldHistoryGeometry10868.lines(series, in: Self.input(series: [series]))).count, 1)
    }

    func testBreakMarksSitAtTheVisibleBandMiddleAndInvalidBreaksAreIgnored() {
        let inside = FieldHistoryBreak10868(id: "a", lower: 1_791_440_000, upper: 1_791_500_000, mark: "//")
        let clipped = FieldHistoryBreak10868(id: "b", lower: Self.terminal - 100, upper: Self.terminal + 900, mark: "//")
        let reversed = FieldHistoryBreak10868(id: "c", lower: 1_791_600_000, upper: 1_791_590_000, mark: "//")
        let outside = FieldHistoryBreak10868(id: "d", lower: Self.terminal + 10, upper: Self.terminal + 20, mark: "//")
        let input = Self.input(series: [], breaks: [inside, clipped, reversed, outside])
        let marks = FieldHistoryGeometry10868.breakMarks(input)
        XCTAssertEqual(marks.count, 2)
        XCTAssertEqual(marks[0].value, 1_791_470_000, accuracy: 1e-3)
        XCTAssertEqual(marks[1].value, Self.terminal - 50, accuracy: 1e-3)
        XCTAssertEqual(FieldHistoryGeometry10868.breakMarks(input).map(\.lines), [["//"], ["//"]])
        XCTAssertNil(FieldHistoryGeometry10868.visibleBreak(reversed, domain: Self.weekDomain))
    }

    // MARK: Shared clock

    func testGuidesAreOwnerWordsInsideTheDomainOnly() {
        var guides = Self.roundGuides
        guides.append(FieldHistoryGuide10868(id: "late", x: Self.terminal + 3_600, label: "Later"))
        let input = Self.input(series: [], guides: guides)
        XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(input).map(\.label), ["R1", "R2", "R3", "R4"])
        XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(input).map(\.x), Self.roundClocks.map { $0.1 })
    }

    func testSharedXIsUnchangedWhenTheCohortOrScaleChanges() {
        let three = Self.input(series: [Self.weekSeries(Self.brennan), Self.weekSeries(Self.schauffele),
                                        Self.weekSeries(Self.mitchell)])
        let other = Self.input(series: [Self.weekSeries(Self.mitchell), Self.weekSeries(Self.brennan)],
                               ceiling: 1.0, yTicks: Self.fullTicks)
        let a = FieldHistoryGeometry10868.marks(three.series[0], in: three)
        let b = FieldHistoryGeometry10868.marks(other.series[1], in: other).filter { $0.probability <= 0.5 }
        XCTAssertEqual(ids(a), ids(b))
        for (pa, pb) in zip(a, b) {
            XCTAssertEqual(FieldHistoryGeometry10868.position(pa, in: three, rect: Self.rect).x,
                           FieldHistoryGeometry10868.position(pb, in: other, rect: Self.rect).x, accuracy: 1e-9)
        }
    }

    func testAnOwnerTransformedCoordinateIsUsedVerbatim() {
        // CONSTRUCTED compressed coordinate: rounds on 0...4, the owner's
        // choice; the leaf never re-times it.
        let points = [FieldHistoryPoint10868(id: "a", x: 0.25, probability: 0.0245, style: .filled),
                      FieldHistoryPoint10868(id: "b", x: 3.5, probability: 0.1377, style: .filled)]
        let series = Self.series(Self.brennan, runs: [Self.run("r", points)])
        let input = Self.input(series: [series], domain: FieldHistoryDomain10868(lower: 0, upper: 4), guides: [])
        let positions = points.map { FieldHistoryGeometry10868.position($0, in: input, rect: Self.rect).x }
        XCTAssertEqual(positions[0], 10 + 0.0625 * 200, accuracy: 1e-9)
        XCTAssertEqual(positions[1], 10 + 0.875 * 200, accuracy: 1e-9)
    }

    func testAPlotTapReportsTheDomainPositionWithoutSnapping() {
        let value = FieldHistoryGeometry10868.domainValue(atX: 60, domain: Self.weekDomain, in: Self.rect)
        XCTAssertEqual(value!, Self.rawStart + 0.25 * (Self.terminal - Self.rawStart), accuracy: 1e-3)
        XCTAssertNil(FieldHistoryGeometry10868.domainValue(atX: 9, domain: Self.weekDomain, in: Self.rect))
        XCTAssertNil(FieldHistoryGeometry10868.domainValue(atX: .nan, domain: Self.weekDomain, in: Self.rect))
    }

    // MARK: Readouts

    func testSingleBeforeReadoutShowsOneDatedEstimate() {
        let brennan = Self.series(Self.brennan, runs: [Self.run("b", [Self.point(Self.brennan, 2)])],
                                  before: .observation(pointID: Self.pid(Self.brennan, 2), figure: "2.6%",
                                                       provenance: "Oct 6, 9:08 AM EDT · DataGolf"),
                                  recorded: .observation(pointID: Self.pid(Self.brennan, 2), figure: "2.6%",
                                                         provenance: "duplicate slot"))
        let input = Self.input(series: [brennan], domain: Self.beforeDomain, ceiling: 0.10,
                               yTicks: Self.autoBeforeTicks, readout: .singleBefore(label: "Before tournament"))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(brennan, in: input), [
            FieldHistoryReadoutSlot10868(label: "Before tournament",
                                         display: .figure("2.6%", provenance: "Oct 6, 9:08 AM EDT · DataGolf")),
        ])
    }

    func testBeforeAndRecordedAreTwoIndependentlyLabelledSlots() {
        let brennan = Self.series(Self.brennan, runs: Self.weekSeries(Self.brennan).runs,
                                  before: .independent(figure: "2.6%", provenance: "Oct 6, 9:08 AM EDT"),
                                  recorded: .observation(pointID: Self.pid(Self.brennan, 333), figure: "100%",
                                                         provenance: "Recorded Oct 11, 2:41 AM EDT"))
        let input = Self.input(series: [brennan], ceiling: 1.0, yTicks: Self.fullTicks)
        let slots = FieldHistoryGeometry10868.readoutSlots(brennan, in: input)
        XCTAssertEqual(slots.map(\.label), ["Before tournament", "Recorded"])
        XCTAssertEqual(slots.map(\.display), [.figure("2.6%", provenance: "Oct 6, 9:08 AM EDT"),
                                              .figure("100%", provenance: "Recorded Oct 11, 2:41 AM EDT")])
        XCTAssertEqual(FieldHistoryGeometry10868.spokenSlot(slots[1]), "Recorded 100%, Recorded Oct 11, 2:41 AM EDT")
    }

    func testABeforeReadingOutsideTheWindowIsNotADrawnPoint() {
        let brennan = Self.series(Self.brennan, runs: Self.weekSeries(Self.brennan).runs,
                                  before: .independent(figure: "2.6%", provenance: "Oct 6, 9:08 AM EDT"))
        let input = Self.input(series: [brennan])
        XCTAssertFalse(FieldHistoryGeometry10868.marks(brennan, in: input)
            .contains { $0.x == Self.record(Self.brennan, 2).x })
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(brennan, in: input)[0].display,
                       .figure("2.6%", provenance: "Oct 6, 9:08 AM EDT"))
    }

    func testEqualValuesAtDifferentObservationsStayDistinct() {
        // ARCHIVED: Brennan 0.026017 before (raw 2, Oct 6) and again later
        // (raw 334, Oct 11 22:08Z). Bound by id, both shown, each with its own
        // provenance.
        let points = [Self.point(Self.brennan, 2, style: .hollow), Self.point(Self.brennan, 334)]
        let brennan = Self.series(Self.brennan, runs: points.map { Self.run($0.id, [$0]) },
                                  before: .observation(pointID: points[0].id, figure: "2.6%", provenance: "Oct 6"),
                                  recorded: .observation(pointID: points[1].id, figure: "2.6%", provenance: "Oct 11"))
        let input = Self.input(series: [brennan], ceiling: 1.0, yTicks: Self.fullTicks)
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(brennan, in: input).map(\.display),
                       [.figure("2.6%", provenance: "Oct 6"), .figure("2.6%", provenance: "Oct 11")])
    }

    func testAnObservationReadingBindsByExactUniqueIDNeverByValue() {
        let p = Self.point(Self.schauffele, 319)
        let twin = FieldHistoryPoint10868(id: p.id, x: p.x - 60, probability: 0, style: .filled)
        let cases: [(FieldHistorySeries10868, FieldHistoryReadingDisplay10868)] = [
            (Self.series(Self.schauffele, runs: [Self.run("r", [p])],
                         recorded: .observation(pointID: p.id, figure: "0%", provenance: "Oct 11, 2:06 AM EDT")),
             .figure("0%", provenance: "Oct 11, 2:06 AM EDT")),
            (Self.series(Self.schauffele, runs: [Self.run("r", [p])],
                         recorded: .observation(pointID: "missing", figure: "0%", provenance: "x")),
             .words("Not recorded")),
            (Self.series(Self.schauffele, runs: [Self.run("r", [twin, p])],
                         recorded: .observation(pointID: p.id, figure: "0%", provenance: "x")),
             .words("Not recorded")),
            (Self.series(Self.schauffele, runs: [Self.run("r", [p])],
                         recorded: .observation(pointID: "", figure: "0%", provenance: "x")),
             .words("Not recorded")),
        ]
        for (series, expected) in cases {
            let input = Self.input(series: [series])
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: input)[1].display, expected)
        }
    }

    func testMissingHistoryAndReadingsKeepTheirOwnReasons() {
        let thorbjornsen = Self.series(Self.thorbjornsen, runs: [],
                                       before: .absent(words: "No before-event estimate captured"),
                                       recorded: .absent(words: "No captured history"),
                                       absentWords: "No captured history in this capture")
        let input = Self.input(series: [Self.weekSeries(Self.brennan), thorbjornsen])
        XCTAssertEqual(FieldHistoryGeometry10868.keyNote(thorbjornsen, in: input), "No captured history in this capture")
        XCTAssertNil(FieldHistoryGeometry10868.keyNote(input.series[0], in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(thorbjornsen, in: input).map(\.display),
                       [.words("No before-event estimate captured"), .words("No captured history")])
        XCTAssertTrue(FieldHistoryGeometry10868.spokenValue(input)
            .contains("Michael Thorbjornsen: No captured history in this capture"))
    }

    // MARK: Identity and selection

    func testAnAmbiguousOriginalKeepsItsLineButGetsNoLabelRingSelectionOrBoundReading() {
        let reading = FieldHistoryReading10868.observation(pointID: Self.pid(Self.brennan, 294), figure: "13.8%",
                                                           provenance: "x")
        let one = Self.series(Self.brennan, runs: Self.weekSeries(Self.brennan).runs,
                              labelPointID: Self.pid(Self.brennan, 294), recorded: reading)
        let twin = Self.series(Self.mitchell, runs: Self.weekSeries(Self.mitchell).runs,
                               labelPointID: Self.pid(Self.mitchell, 295), overrideID: Self.brennan)
        let empty = Self.series(Self.schauffele, runs: Self.weekSeries(Self.schauffele).runs,
                                labelPointID: Self.pid(Self.schauffele, 283), overrideID: "")
        let inspection = FieldHistoryInspection10868(
            x: Self.record(Self.brennan, 294).x, caption: "Recorded Oct 10, 11:27 PM EDT",
            selections: [Self.brennan: .point(id: Self.pid(Self.brennan, 294), spoken: "13.8%"),
                         "": .absent(words: "Not recorded")],
            choices: [], choicePresentation: .buttons(groupLabel: "Moments"), note: nil)
        let input = Self.input(series: [one, twin, empty], selection: .series(id: Self.brennan, missingWords: "Golfer unavailable"),
                               inspection: inspection)
        for series in input.series {
            XCTAssertFalse(FieldHistoryGeometry10868.isExactlyIdentified(series, in: input))
            XCTAssertNil(FieldHistoryGeometry10868.labelAnchor(series, in: input))
            XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series, in: input))
            XCTAssertNil(FieldHistoryGeometry10868.inspectedAbsentWords(series, in: input))
            XCTAssertFalse(FieldHistoryGeometry10868.isSelected(series, in: input))
            XCTAssertFalse(FieldHistoryGeometry10868.lines(series, in: input).isEmpty)
        }
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(one, in: input)[1].display, .words("Not recorded"))
        XCTAssertEqual(FieldHistoryGeometry10868.selectionWords(input), "Golfer unavailable")
        XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(input), "Recorded Oct 10, 11:27 PM EDT")
    }

    func testTheSelectedOriginalIsExactOrExplicitlyUnavailableNeverANeighbour() {
        let cohort = [Self.weekSeries(Self.brennan), Self.weekSeries(Self.schauffele)]
        let chosen = Self.input(series: cohort, selection: .series(id: Self.schauffele, missingWords: "Unavailable"))
        XCTAssertEqual(cohort.map { FieldHistoryGeometry10868.isSelected($0, in: chosen) }, [false, true])
        XCTAssertNil(FieldHistoryGeometry10868.selectionWords(chosen))

        let missing = Self.input(series: cohort, selection: .series(id: Self.mitchell,
                                                                    missingWords: "Keith Mitchell isn't in this chart"))
        XCTAssertEqual(cohort.map { FieldHistoryGeometry10868.isSelected($0, in: missing) }, [false, false])
        XCTAssertEqual(FieldHistoryGeometry10868.selectionWords(missing), "Keith Mitchell isn't in this chart")

        let withdrawn = Self.input(series: cohort, selection: .unavailable(words: "Selected golfer withdrew"))
        XCTAssertEqual(cohort.map { FieldHistoryGeometry10868.isSelected($0, in: withdrawn) }, [false, false])
        XCTAssertEqual(FieldHistoryGeometry10868.selectionWords(withdrawn), "Selected golfer withdrew")
        XCTAssertNil(FieldHistoryGeometry10868.selectionWords(Self.input(series: cohort)))
    }

    func testADirectLabelAttachesToTheOwnersExactPointNotTheLast() {
        let labelled = Self.weekSeries(Self.mitchell, labelAt: 130)
        let input = Self.input(series: [labelled, Self.weekSeries(Self.brennan)])
        XCTAssertEqual(FieldHistoryGeometry10868.labelAnchor(labelled, in: input)?.id, Self.pid(Self.mitchell, 130))
        XCTAssertNil(FieldHistoryGeometry10868.labelAnchor(input.series[1], in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.labelledSeries(input).map { $0.0.id }, [Self.mitchell])
        let target = FieldHistoryGeometry10868.labelTarget(Self.point(Self.mitchell, 130), in: input)
        XCTAssertEqual(target.yFraction, 0.110319 / 0.5, accuracy: 1e-12)
        // An unplaceable anchor (100% under 0–50%) gives no label.
        let high = Self.weekSeries(Self.brennan, labelAt: 333)
        XCTAssertNil(FieldHistoryGeometry10868.labelAnchor(high, in: Self.input(series: [high])))
    }

    // MARK: Label lanes and key

    private static let phoneY = [CGSize(width: 24, height: 16), CGSize(width: 24, height: 16), CGSize(width: 30, height: 16)]
    private static let guideSizes = Array(repeating: CGSize(width: 18, height: 16), count: 4)
    /// CONSTRUCTED measured name sizes at standard type.
    private static let standardNames = [CGSize(width: 96, height: 16), CGSize(width: 104, height: 16),
                                        CGSize(width: 80, height: 16)]
    /// CONSTRUCTED before targets: Brennan 2.6%, Schauffele 8.66%, Mitchell
    /// 1.27% of a 0–10% scale, each at the last before estimate.
    private static let beforeTargets = [
        FieldHistoryLabelTarget10868(xFraction: 0.5244, yFraction: 0.26017),
        FieldHistoryLabelTarget10868(xFraction: 0.5244, yFraction: 0.86583),
        FieldHistoryLabelTarget10868(xFraction: 0.5244, yFraction: 0.12733),
    ]

    private static func arrangement(width: CGFloat, ySizes: [CGSize] = phoneY, names: [CGSize] = standardNames,
                             lineHeight: CGFloat = 16, plotHeight: CGFloat = 240,
                             targets: [FieldHistoryLabelTarget10868] = beforeTargets,
                             guides: Int = 4) -> FieldHistoryPlotArrangement10868 {
        FieldHistoryGeometry10868.plotArrangement(
            width: width, plotHeight: plotHeight, inset: 8.5, markClearance: 5.6,
            yFractions: [0, 0.5, 1], ySizes: ySizes,
            xFractions: [0, 1], xSizes: [CGSize(width: 40, height: 32), CGSize(width: 40, height: 32)],
            guideFractions: Array([0.0004, 0.305, 0.61, 0.9156].prefix(guides)),
            guideSizes: Array(guideSizes.prefix(guides)),
            labelTargets: targets, labelNaturalSizes: names,
            labelHeights: { column in names.map { ($0.width / column).rounded(.up) * lineHeight } }
        )
    }

    private func assertNoOverlap(_ frames: [CGRect], file: StaticString = #filePath, line: UInt = #line) {
        for (i, a) in frames.enumerated() {
            for b in frames[(i + 1)...] {
                XCTAssertFalse(a.intersects(b), "\(a) overlaps \(b)", file: file, line: line)
            }
        }
    }

    func testDirectLabelsFitBesideTheirPointsAtPhoneWidth() {
        let a = Self.arrangement(width: 343)
        XCTAssertTrue(a.usesDirectLabels)
        XCTAssertEqual(a.plot.height, 240)
        XCTAssertEqual(a.plot.minX, 36)                     // 30 pt label + 6 pt gap
        XCTAssertEqual(a.directLabels.map(\.width), [104, 104, 104])
        XCTAssertEqual(a.plot.width, 343 - 36 - 14 - 104)
        XCTAssertGreaterThanOrEqual(a.plot.width, 140)
        assertNoOverlap(a.directLabels)
        for (frame, target) in zip(a.directLabels, Self.beforeTargets) {
            XCTAssertGreaterThanOrEqual(frame.minX, a.plot.maxX)  // never over marks or ticks
            let pointY = a.plot.minY + 8.5 + CGFloat(1 - target.yFraction) * (240 - 17)
            XCTAssertEqual(frame.midY, pointY, accuracy: 1e-9)   // room to centre each on its point
        }
        for (leader, frame) in zip(a.leaders, a.directLabels) {
            XCTAssertEqual(leader.frame.maxX, frame.minX - 2, accuracy: 1e-9)
        }
        XCTAssertEqual(a.guideRows, 1)
        XCTAssertEqual(a.plot.minY, 16 + 6)
    }

    func testCrowdedEndpointsStackInPointOrderWithoutOverlap() {
        let close = [FieldHistoryLabelTarget10868(xFraction: 1, yFraction: 0.040),
                     FieldHistoryLabelTarget10868(xFraction: 1, yFraction: 0.050),
                     FieldHistoryLabelTarget10868(xFraction: 1, yFraction: 0.045)]
        let a = Self.arrangement(width: 343, targets: close)
        XCTAssertTrue(a.usesDirectLabels)
        assertNoOverlap(a.directLabels)
        // Highest point (0.050) on top, then 0.045, then 0.040.
        XCTAssertLessThan(a.directLabels[1].minY, a.directLabels[2].minY)
        XCTAssertLessThan(a.directLabels[2].minY, a.directLabels[0].minY)
        XCTAssertLessThanOrEqual(a.directLabels.map(\.maxY).max()!, a.plot.maxY)
        for (leader, frame) in zip(a.leaders, a.directLabels) {
            XCTAssertEqual(leader.rising ? leader.frame.minY : leader.frame.maxY, frame.midY, accuracy: 1e-9)
        }
    }

    func testLabelsThatCannotFitAtAccessibilitySizesMoveToTheKey() {
        let ax = Self.arrangement(width: 288, ySizes: Array(repeating: CGSize(width: 40, height: 28), count: 3),
                             names: [CGSize(width: 260, height: 28), CGSize(width: 280, height: 28),
                                     CGSize(width: 240, height: 28)], lineHeight: 28)
        XCTAssertFalse(ax.usesDirectLabels)
        XCTAssertTrue(ax.leaders.isEmpty)
        XCTAssertEqual(ax.plot.width, 288 - 46)              // the plot takes the whole width
        XCTAssertEqual(ax.plot.height, 240)
    }

    func testANarrowPlotGivesUpDirectLabelsRatherThanShrinking() {
        let narrow = Self.arrangement(width: 250)
        XCTAssertFalse(narrow.usesDirectLabels)
        XCTAssertEqual(narrow.plot.width, 250 - 36)
        XCTAssertTrue(Self.arrangement(width: 288).usesDirectLabels) // 320 phone, standard type
    }

    func testWideWidthLeadsWithThePlotAndKeepsLabelsDirect() {
        let a = Self.arrangement(width: 700)
        XCTAssertTrue(a.usesDirectLabels)
        XCTAssertEqual(a.plot.width, 700 - 36 - 14 - 104)
        XCTAssertGreaterThan(a.plot.width, a.directLabels[0].width * 4)
    }

    func testThePlotKeepsTheOwnersHeightAndFallsBackOnlyWhenUnusable() {
        XCTAssertEqual(Self.arrangement(width: 343, plotHeight: 320).plot.height, 320)
        XCTAssertEqual(Self.arrangement(width: 343, plotHeight: 0).plot.height, 240)
        XCTAssertEqual(Self.arrangement(width: 343, plotHeight: .nan).plot.height, 240)
        XCTAssertEqual(FieldHistoryGeometry10868.plotHeight(-5), FieldHistoryGeometry10868.referencePlotHeight)
        let noGuides = Self.arrangement(width: 343, guides: 0)
        XCTAssertEqual(noGuides.plot.minY, 0)
        XCTAssertEqual(noGuides.height, 240 + 6 + 32)
    }

    func testDirectLabelTopsRejectInvalidOrOverfullInput() {
        XCTAssertEqual(FieldHistoryGeometry10868.directLabelTops(centers: [], heights: [], extent: 100, gap: 4), [])
        XCTAssertNil(FieldHistoryGeometry10868.directLabelTops(centers: [10, 20], heights: [50, 50], extent: 100, gap: 4))
        XCTAssertNil(FieldHistoryGeometry10868.directLabelTops(centers: [.nan], heights: [10], extent: 100, gap: 4))
        XCTAssertNil(FieldHistoryGeometry10868.directLabelTops(centers: [10], heights: [10], extent: .infinity, gap: 4))
        XCTAssertEqual(FieldHistoryGeometry10868.directLabelTops(centers: [5, 95], heights: [20, 20], extent: 100, gap: 4),
                       [0, 80])
    }

    func testKeyColumnsFollowWidthAndUseOneColumnAtAccessibilitySizes() {
        XCTAssertEqual(FieldHistoryGeometry10868.keyColumns(width: 343, minimum: 150, spacing: 10, count: 4, singleColumn: false), 2)
        XCTAssertEqual(FieldHistoryGeometry10868.keyColumns(width: 288, minimum: 150, spacing: 10, count: 4, singleColumn: false), 1)
        XCTAssertEqual(FieldHistoryGeometry10868.keyColumns(width: 700, minimum: 150, spacing: 10, count: 4, singleColumn: false), 4)
        XCTAssertEqual(FieldHistoryGeometry10868.keyColumns(width: 700, minimum: 150, spacing: 10, count: 2, singleColumn: false), 2)
        XCTAssertEqual(FieldHistoryGeometry10868.keyColumns(width: 700, minimum: 150, spacing: 10, count: 4, singleColumn: true), 1)
        XCTAssertEqual(FieldHistoryGeometry10868.keyColumns(width: 700, minimum: 0, spacing: 10, count: 4, singleColumn: false), 1)
    }

    // MARK: Calendar label density (CONSTRUCTED measured sizes)

    /// CONSTRUCTED: six owner calendar ticks a fifth of the domain apart.
    private static let sixTicks: [Double] = [0, 0.2, 0.4, 0.6, 0.8, 1]
    /// CONSTRUCTED measured tick sizes: standard type ("Wed 6 PM"), a larger
    /// text size, and an accessibility text size.
    private static let standardTick = CGSize(width: 52, height: 16)
    private static let largerTick = CGSize(width: 80, height: 24)
    private static let accessibilityTick = CGSize(width: 118, height: 40)

    /// Only the calendar row: no percentage gutter, guides or direct labels,
    /// so the plot takes the whole width. Break marks follow the ticks.
    private static func calendarRow(width: CGFloat, tick: CGSize, fractions: [Double] = sixTicks,
                                    marks: [Double] = [], thinned: Bool = true) -> FieldHistoryPlotArrangement10868 {
        FieldHistoryGeometry10868.plotArrangement(
            width: width, plotHeight: 240, inset: 8.5, markClearance: 5.6,
            yFractions: [], ySizes: [],
            xFractions: fractions + marks,
            xSizes: Array(repeating: tick, count: fractions.count)
                + Array(repeating: CGSize(width: 14, height: 16), count: marks.count),
            calendarLabelCount: thinned ? fractions.count : 0,
            guideFractions: [], guideSizes: [],
            labelTargets: [], labelNaturalSizes: [], labelHeights: { _ in [] }
        )
    }

    /// The x labels given a size, by index; every other one draws nothing.
    private func shownXLabels(_ a: FieldHistoryPlotArrangement10868) -> [Int] {
        a.xLabels.indices.filter { a.xLabels[$0].width > 0 && a.xLabels[$0].height > 0 }
    }

    /// No two shown x labels overlap, and two on one row keep the 6 pt gap.
    private func assertClearRows(_ a: FieldHistoryPlotArrangement10868,
                                 file: StaticString = #filePath, line: UInt = #line) {
        let frames = shownXLabels(a).map { a.xLabels[$0] }
        assertNoOverlap(frames, file: file, line: line)
        for (i, f) in frames.enumerated() {
            for g in frames[(i + 1)...] where f.minY == g.minY {
                XCTAssertGreaterThan(max(f.minX, g.minX) - min(f.maxX, g.maxX), 6, "\(f) crowds \(g)",
                                     file: file, line: line)
            }
        }
    }

    func testAtStandardTypeOnAPhoneOnlyTicksThatFitClearlyShowOnOneRow() {
        XCTAssertEqual(Self.calendarRow(width: 343, tick: Self.standardTick, thinned: false).xRows, 2) // the staircase
        let a = Self.calendarRow(width: 343, tick: Self.standardTick)
        XCTAssertEqual(shownXLabels(a), [0, 2, 3, 5])        // 0.2 crowds the first tick, 0.8 the last
        XCTAssertEqual(a.xRows, 1)
        XCTAssertEqual(a.height, 240 + 6 + 16)
        assertClearRows(a)
    }

    func testAtAnAccessibilitySizeTwoClearEndpointsReplaceTheStaircase() {
        XCTAssertEqual(Self.calendarRow(width: 343, tick: Self.accessibilityTick, thinned: false).xRows, 3)
        let a = Self.calendarRow(width: 343, tick: Self.accessibilityTick)
        XCTAssertEqual(shownXLabels(a), [0, 5])
        XCTAssertEqual(a.xRows, 1)
        XCTAssertEqual(a.xLabels[0], CGRect(x: 0, y: 246, width: 118, height: 40))
        XCTAssertEqual(a.xLabels[5], CGRect(x: 225, y: 246, width: 118, height: 40))
        XCTAssertEqual(a.height, 240 + 6 + 40)
        assertClearRows(a)
    }

    func testEndpointsThatCannotShareARowTakeTwoRowsAtFullSize() {
        XCTAssertEqual(Self.calendarRow(width: 200, tick: Self.accessibilityTick, thinned: false).xRows, 6)
        let a = Self.calendarRow(width: 200, tick: Self.accessibilityTick)
        XCTAssertEqual(shownXLabels(a), [0, 5])
        XCTAssertEqual(a.xRows, 2)
        XCTAssertEqual(a.xLabels[0], CGRect(x: 0, y: 246, width: 118, height: 40))
        XCTAssertEqual(a.xLabels[5], CGRect(x: 82, y: 246 + 40 + 4, width: 118, height: 40)) // never shrunk
        XCTAssertEqual(a.height, 240 + 6 + 40 + 4 + 40)
        assertClearRows(a)
    }

    func testChangingWidthOrTextSizeChangesTheShownTicksDeterministically() {
        // Text size at one phone width.
        XCTAssertEqual(shownXLabels(Self.calendarRow(width: 343, tick: Self.standardTick)), [0, 2, 3, 5])
        XCTAssertEqual(shownXLabels(Self.calendarRow(width: 343, tick: Self.largerTick)), [0, 2, 5])
        XCTAssertEqual(shownXLabels(Self.calendarRow(width: 343, tick: Self.accessibilityTick)), [0, 5])
        // Width at standard type.
        XCTAssertEqual(shownXLabels(Self.calendarRow(width: 200, tick: Self.standardTick)), [0, 5])
        XCTAssertEqual(shownXLabels(Self.calendarRow(width: 700, tick: Self.standardTick)), [0, 1, 2, 3, 4, 5])
        // The same measurements always give the same row.
        XCTAssertEqual(Self.calendarRow(width: 343, tick: Self.largerTick),
                       Self.calendarRow(width: 343, tick: Self.largerTick))
    }

    func testEndpointsAlwaysShowAndNoShownTicksCollideAtAnyWidthOrSize() {
        for width in stride(from: CGFloat(120), through: 800, by: 13) {
            for tickWidth in stride(from: CGFloat(20), through: 240, by: 17) {
                for count in 1...8 {
                    let fractions = (0..<count).map { count == 1 ? 0.5 : Double($0) / Double(count - 1) }
                    let a = Self.calendarRow(width: width, tick: CGSize(width: tickWidth, height: 16),
                                             fractions: fractions)
                    let shown = shownXLabels(a)
                    XCTAssertEqual(a.xLabels.count, count)               // every owner tick keeps its slot
                    XCTAssertEqual(shown.first, 0)
                    XCTAssertEqual(shown.last, count - 1)
                    XCTAssertLessThanOrEqual(a.xRows, 2)
                    if a.xRows == 2 { XCTAssertEqual(shown, [0, count - 1]) } // only the ends ever need two rows
                    for index in shown { XCTAssertEqual(a.xLabels[index].width, min(tickWidth, width)) }
                    assertClearRows(a)
                }
            }
        }
    }

    func testBreakMarksAlwaysShowAndATickThatWouldTouchOneIsLeftOut() {
        let a = Self.calendarRow(width: 343, tick: Self.standardTick, marks: [0.3])
        XCTAssertEqual(shownXLabels(a), [0, 3, 5, 6])        // 0.4 would touch the mark (index 6)
        XCTAssertEqual(a.xRows, 1)
        assertClearRows(a)
        XCTAssertEqual(Self.calendarRow(width: 343, tick: Self.standardTick, marks: [0.3], thinned: false).xRows, 3)
        let crowded = Self.calendarRow(width: 343, tick: Self.accessibilityTick, marks: [0])
        XCTAssertEqual(shownXLabels(crowded), [0, 5, 6])     // a mark on the first tick takes a lane, never dropped
        XCTAssertEqual(crowded.xRows, 2)
        assertClearRows(crowded)
    }

    func testShownLabelsKeepTheEndsAndOnlyClearLabelsBetween() {
        // Explicit spans on a 100 pt row: [0,20] [25,45] [50,70] [80,100].
        let centers: [CGFloat] = [10, 35, 60, 90], lengths: [CGFloat] = [20, 20, 20, 20]
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: centers, lengths: lengths, extent: 100, gap: 4),
                       [true, true, true, true])
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: centers, lengths: lengths, extent: 100, gap: 6),
                       [true, false, true, true])
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: centers, lengths: lengths, extent: 100, gap: 4,
                                                             beside: [46...54]),
                       [true, false, false, true])
        // The ends are kept even when they overlap; one or none is itself.
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: [10, 50, 90], lengths: [80, 10, 80],
                                                             extent: 100, gap: 6), [true, false, true])
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: [50], lengths: [20], extent: 100, gap: 6), [true])
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: [], lengths: [], extent: 100, gap: 6), [])
        XCTAssertEqual(FieldHistoryGeometry10868.shownLabels(centers: [.nan, 50, .infinity], lengths: [10, 10, .nan],
                                                             extent: 100, gap: 6), [true, true, true])
        // Each span is the one labelSlots places, so shown labels share its row.
        let cases: [(CGFloat, CGFloat)] = [(50, 20), (-5, 20), (99, 20), (50, 140), (.nan, 10), (40, -3)]
        for (center, length) in cases {
            let span = FieldHistoryGeometry10868.labelSpan(center: center, length: length, extent: 100)
            let slot = FieldHistoryGeometry10868.labelSlots(centers: [center], lengths: [length], extent: 100, gap: 6)
            XCTAssertEqual(span.lowerBound, slot[0].start)
        }
    }

    func testThinningKeepsEveryTicksOwnPlaceAndSizeAndChangesNothingAboveTheRow() {
        func arranged(thinned: Bool) -> FieldHistoryPlotArrangement10868 {
            FieldHistoryGeometry10868.plotArrangement(
                width: 343, plotHeight: 240, inset: 8.5, markClearance: 5.6,
                yFractions: [0, 0.5, 1], ySizes: Self.phoneY,
                xFractions: Self.sixTicks, xSizes: Array(repeating: Self.accessibilityTick, count: 6),
                calendarLabelCount: thinned ? 6 : 0,
                guideFractions: [0.0004, 0.305, 0.61, 0.9156], guideSizes: Self.guideSizes,
                labelTargets: Self.beforeTargets, labelNaturalSizes: Self.standardNames,
                labelHeights: { column in Self.standardNames.map { ($0.width / column).rounded(.up) * 16 } }
            )
        }
        let thinned = arranged(thinned: true), unthinned = arranged(thinned: false)
        XCTAssertEqual(thinned.plot, unthinned.plot)
        XCTAssertEqual(thinned.yLabels, unthinned.yLabels)
        XCTAssertEqual(thinned.guideLabels, unthinned.guideLabels)
        XCTAssertEqual(thinned.guideRows, unthinned.guideRows)
        XCTAssertEqual(thinned.directLabels, unthinned.directLabels)
        XCTAssertEqual(thinned.leaders, unthinned.leaders)
        XCTAssertEqual(thinned.xLabels.count, 6)
        XCTAssertEqual(shownXLabels(thinned), [0, 5])
        XCTAssertEqual(thinned.xRows, 1)
        XCTAssertEqual(unthinned.xRows, 5)
        for index in shownXLabels(thinned) {
            XCTAssertEqual(thinned.xLabels[index].minX, unthinned.xLabels[index].minX) // its own place
            XCTAssertEqual(thinned.xLabels[index].size, unthinned.xLabels[index].size) // its measured size
        }
    }

    func testThePlacedTicksPointsAndSelectionAreTheOwnersWhateverTheRowShows() {
        // CONSTRUCTED owner calendar ticks across the week domain.
        let span = Self.terminal - Self.rawStart
        let ticks = Self.sixTicks.enumerated().map { index, fraction in
            FieldHistoryTick10868(value: fraction == 1 ? Self.terminal : Self.rawStart + fraction * span,
                                  lines: ["T\(index)"])
        }
        let brennan = Self.weekSeries(Self.brennan)
        let inspection = FieldHistoryInspection10868(
            x: Self.record(Self.brennan, 128).x, caption: "Recorded Oct 8, 11:46 PM EDT",
            selections: [Self.brennan: .point(id: Self.pid(Self.brennan, 128), spoken: "2.4%")],
            choices: [], choicePresentation: .slider(label: "Recorded history moment"), note: nil)
        let selection = FieldHistoryOriginalSelection10868.series(id: Self.brennan, missingWords: "Not shown")
        let ticked = Self.input(series: [brennan], selection: selection, xTicks: ticks, inspection: inspection)
        let plain = Self.input(series: [brennan], selection: selection, inspection: inspection)
        // Thinning is chosen only from measured sizes in the layout: the
        // placed list keeps every owner tick verbatim, whatever the row shows.
        XCTAssertNotEqual(shownXLabels(Self.calendarRow(width: 200, tick: Self.accessibilityTick)),
                          shownXLabels(Self.calendarRow(width: 700, tick: Self.standardTick)))
        XCTAssertEqual(FieldHistoryGeometry10868.placedXTicks(ticked), ticks)
        XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(ticked), FieldHistoryGeometry10868.placedGuides(plain))
        XCTAssertEqual(FieldHistoryGeometry10868.marks(brennan, in: ticked), FieldHistoryGeometry10868.marks(brennan, in: plain))
        XCTAssertEqual(ids(FieldHistoryGeometry10868.lines(brennan, in: ticked)),
                       ids(FieldHistoryGeometry10868.lines(brennan, in: plain)))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(brennan, in: ticked)?.id, Self.pid(Self.brennan, 128))
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(ticked), FieldHistoryGeometry10868.selectedSummary(plain))
        XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(ticked), FieldHistoryGeometry10868.spokenValue(plain))
    }

    // MARK: Controls

    private static func controlled(more: String = "more", choose: String = "choose:brennan") -> FieldHistoryInput10868 {
        let windows = FieldHistoryWindows10868(groupLabel: "Probability history period", choices: [
            FieldHistoryWindowChoice10868(action: action("window:before", "Before"), isSelected: false),
            FieldHistoryWindowChoice10868(action: action("window:week", "Week"), isSelected: true),
        ])
        let brennan = series(Self.brennan, runs: weekSeries(Self.brennan).runs, choose: action(choose, "Choose"))
        return input(series: [brennan, weekSeries(Self.schauffele)], windows: windows,
                     scale: action("scale", "Auto scale · 0–50%", spoken: "Show full zero to 100 percent scale"),
                     moreOriginals: action(more, "Golfers"), details: action("details", "History & source details"),
                     expand: action("expand", "Expand", spoken: "Expand win probability chart"),
                     inspect: action("inspect", "Inspect history"),
                     previous: action("previous", "Previous recorded moment", available: false),
                     next: action("next", "Next recorded moment"))
    }

    func testControlsHandBackOnlyNonemptyUniqueOwnerIDs() {
        let input = Self.controlled()
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.scale, informative: true, hasCallback: true, in: input),
                       .live(id: "scale"))
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.windows!.choices[1].action, informative: true,
                                                              hasCallback: true, in: input), .live(id: "window:week"))
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(input.series[0], hasCallback: true, in: input),
                       .live(id: "choose:brennan"))
        // A shared id ("scale" twice) makes both static; neighbours still work.
        let shared = Self.controlled(more: "scale")
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(shared.scale, informative: true, hasCallback: true, in: shared),
                       .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(shared.moreOriginals, informative: false, hasCallback: true,
                                                              in: shared), .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(shared.details, informative: false, hasCallback: true,
                                                              in: shared), .live(id: "details"))
        let empty = Self.controlled(choose: "")
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(empty.series[0], hasCallback: true, in: empty), .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(nil, informative: true, hasCallback: true, in: input), .hidden)
    }

    func testAStaticViewKeepsInformativeControlsAndHidesPureActions() {
        let input = Self.controlled()
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.scale, informative: true, hasCallback: false, in: input),
                       .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.windows!.choices[0].action, informative: true,
                                                              hasCallback: false, in: input), .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(input.series[0], hasCallback: false, in: input), .shownStatic)
        for pure in [input.moreOriginals, input.details, input.expand, input.inspect, input.previous, input.next] {
            XCTAssertEqual(FieldHistoryGeometry10868.controlState(pure, informative: false, hasCallback: false, in: input),
                           .hidden)
        }
    }

    func testChoosingAnOriginalNeedsAnExactlyIdentifiedOriginal() {
        var cohort = Self.controlled().series
        cohort.append(Self.series(Self.mitchell, runs: [], choose: Self.action("choose:twin", "Choose"),
                                  overrideID: Self.brennan))
        let input = Self.input(series: cohort)
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(cohort[0], hasCallback: true, in: input), .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(cohort[2], hasCallback: true, in: input), .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(cohort[1], hasCallback: true, in: input),
                       .live(id: "choose:\(Self.schauffele)"))
    }

    func testPreviousAndNextAreAdjustableOnlyWhenLiveAndAvailable() {
        let input = Self.controlled()
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(input.previous, hasCallback: true, in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: true, in: input), "next")
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: false, in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.previous, informative: false, hasCallback: true,
                                                              in: input), .live(id: "previous"))
    }

    // MARK: Inspection

    private static func choices(selected: [Int], ids: [String] = ["c0", "c1", "c2"]) -> [FieldHistoryInspectionChoice10868] {
        // CONSTRUCTED: Brennan's three before estimate times.
        let words = [("Oct 4", "9:08 PM"), ("Oct 5", "1:39 PM"), ("Oct 6", "9:08 AM")]
        return ids.enumerated().map { index, id in
            FieldHistoryInspectionChoice10868(id: id, lines: [words[index].0, words[index].1],
                                              spoken: "Estimate from \(words[index].0), \(words[index].1)",
                                              isSelected: selected.contains(index))
        }
    }

    func testInspectionRingsOnlyTheExactSelectedPoint() {
        let brennan = Self.weekSeries(Self.brennan)
        let schauffele = Self.weekSeries(Self.schauffele)
        let mitchell = Self.weekSeries(Self.mitchell)
        let inspection = FieldHistoryInspection10868(
            x: Self.record(Self.brennan, 128).x, caption: "Recorded Oct 8, 11:46 PM EDT",
            selections: [Self.brennan: .point(id: Self.pid(Self.brennan, 128), spoken: "2.4%"),
                         Self.schauffele: .point(id: "\(Self.schauffele)#999", spoken: "3.1%"),
                         Self.mitchell: .absent(words: "Not recorded")],
            choices: [], choicePresentation: .slider(label: "Recorded history moment"), note: nil)
        let input = Self.input(series: [brennan, schauffele, mitchell], inspection: inspection)
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(brennan, in: input)?.id, Self.pid(Self.brennan, 128))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(schauffele, in: input)) // no nearest stand-in
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(mitchell, in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.keyNote(mitchell, in: input), "Not recorded")
        XCTAssertEqual(FieldHistoryGeometry10868.cursor(input), Self.record(Self.brennan, 128).x)
        XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(input),
                       "Recorded Oct 8, 11:46 PM EDT; Michael Brennan: 2.4%; Keith Mitchell: Not recorded")
    }

    func testACursorOutsideTheDomainIsNotDrawn() {
        let inspection = FieldHistoryInspection10868(x: Self.terminal + 60, caption: "Later", selections: [:],
                                                     choices: [], choicePresentation: .buttons(groupLabel: "x"), note: nil)
        XCTAssertNil(FieldHistoryGeometry10868.cursor(Self.input(series: [], inspection: inspection)))
    }

    func testTheDiscreteSliderNeedsOneSelectedChoiceAndHandsBackExactIDs() {
        let held = Self.choices(selected: [1])
        XCTAssertEqual(FieldHistoryGeometry10868.sliderIndex(held), 1)
        XCTAssertEqual(FieldHistoryGeometry10868.sliderChoiceID(at: 2, choices: held), "c2")
        XCTAssertEqual(FieldHistoryGeometry10868.sliderChoiceID(at: 0.4, choices: held), "c0")
        XCTAssertNil(FieldHistoryGeometry10868.sliderChoiceID(at: 1, choices: held))
        XCTAssertNil(FieldHistoryGeometry10868.sliderChoiceID(at: .nan, choices: held))
        XCTAssertNil(FieldHistoryGeometry10868.sliderChoiceID(at: 5, choices: held))
        XCTAssertNil(FieldHistoryGeometry10868.sliderIndex(Self.choices(selected: [])))
        XCTAssertNil(FieldHistoryGeometry10868.sliderIndex(Self.choices(selected: [0, 2])))
        XCTAssertNil(FieldHistoryGeometry10868.sliderIndex(Array(held.prefix(1))))
        let twins = Self.choices(selected: [0], ids: ["c0", "dup", "dup"])
        XCTAssertNil(FieldHistoryGeometry10868.sliderChoiceID(at: 2, choices: twins))
    }

    func testChoiceButtonsWithEmptyOrSharedIDsStayStatic() {
        let mixed = Self.choices(selected: [2], ids: ["", "same", "same"]) + [
            FieldHistoryInspectionChoice10868(id: "c3", lines: ["Oct 7"], spoken: "Oct 7", isSelected: false),
        ]
        XCTAssertEqual(mixed.map { FieldHistoryGeometry10868.liveChoiceID($0, among: mixed) }, [nil, nil, nil, "c3"])
    }

    // MARK: Drawing primitives

    func testMarkPathsAreThreeDistinctShapesAtTheApprovedProportions() {
        let center = CGPoint(x: 50, y: 50)
        let circle = FieldHistoryGeometry10868.markPath(.circle, at: center, radius: 4).boundingRect
        let square = FieldHistoryGeometry10868.markPath(.square, at: center, radius: 4).boundingRect
        let diamond = FieldHistoryGeometry10868.markPath(.diamond, at: center, radius: 4).boundingRect
        XCTAssertEqual(circle.width, 8, accuracy: 1e-9)
        XCTAssertEqual(square.width, 6.8, accuracy: 1e-9)
        XCTAssertEqual(diamond.width, 9.6, accuracy: 1e-9)
        XCTAssertFalse(FieldHistoryGeometry10868.markPath(.square, at: center, radius: 4)
            .contains(CGPoint(x: 50 + 4.6, y: 50)))
        XCTAssertTrue(FieldHistoryGeometry10868.markPath(.diamond, at: center, radius: 4)
            .contains(CGPoint(x: 50 + 4.6, y: 50)))
    }

    func testLeaderShapesRunCornerToCorner() {
        let rect = CGRect(x: 0, y: 0, width: 20, height: 10)
        let falling = FieldHistoryLeaderShape10868(rising: false).path(in: rect).boundingRect
        let rising = FieldHistoryLeaderShape10868(rising: true).path(in: rect).boundingRect
        XCTAssertEqual(falling, rect)
        XCTAssertEqual(rising, rect)
        XCTAssertTrue(FieldHistoryLeaderShape10868(rising: false).path(in: .zero).boundingRect.isEmpty)
    }

    // MARK: Correction F1 — compositions (CONSTRUCTED layouts and selections)

    private static func laidOut(_ input: FieldHistoryInput10868,
                                _ layout: FieldHistoryLayout10868) -> FieldHistoryInput10868 {
        var copy = input
        copy.layout = layout
        return copy
    }

    private static func blocks(_ input: FieldHistoryInput10868) -> [FieldHistoryReadoutBlock10868] {
        FieldHistoryGeometry10868.blocksAbovePlot(input) + FieldHistoryGeometry10868.blocksBelowPlot(input)
    }

    func testTheDefaultCompositionIsProbabilityFirstWithTheKeyOnceAboveThePlot() {
        let input = Self.input(series: Self.order.map { Self.weekSeries($0) })
        XCTAssertEqual(input.layout, .cohortAbove)
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(input), [.selectionWords, .key])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksBelowPlot(input), [])
        XCTAssertEqual(Self.blocks(input).filter { $0 == .key }.count, 1)
    }

    func testFocusedCompositionLeadsWithOnlyTheExactSelectedOriginal() {
        let brennan = Self.series(Self.brennan, runs: Self.weekSeries(Self.brennan).runs,
                                  before: .independent(figure: "2.6%", provenance: "Oct 6, 9:08 AM EDT"),
                                  recorded: .observation(pointID: Self.pid(Self.brennan, 294), figure: "13.8%",
                                                         provenance: "Recorded Oct 10, 11:27 PM EDT"))
        let mitchell = Self.series(Self.mitchell, runs: Self.weekSeries(Self.mitchell).runs,
                                   before: .independent(figure: "1.3%", provenance: "Oct 6, 9:08 AM EDT"),
                                   recorded: .observation(pointID: Self.pid(Self.mitchell, 295), figure: "47.0%",
                                                          provenance: "Recorded Oct 10, 11:27 PM EDT"))
        let input = Self.laidOut(Self.input(series: [brennan, mitchell],
                                            selection: .series(id: Self.mitchell, missingWords: "Golfer unavailable")),
                                 .focused)
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(input), [.selectedSummary])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksBelowPlot(input), [.key])
        guard case .original(let chosen, let slots) = FieldHistoryGeometry10868.selectedSummary(input) else {
            return XCTFail("the exact selected original leads")
        }
        XCTAssertEqual(chosen.id, Self.mitchell)
        XCTAssertEqual(chosen.name, "Keith Mitchell")
        XCTAssertEqual(chosen.shape, .diamond)
        // The headline uses the very slots the key resolves for that original.
        XCTAssertEqual(slots, FieldHistoryGeometry10868.readoutSlots(mitchell, in: input))
        XCTAssertEqual(slots.map(\.display), [.figure("1.3%", provenance: "Oct 6, 9:08 AM EDT"),
                                              .figure("47.0%", provenance: "Recorded Oct 10, 11:27 PM EDT")])
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.isSelected($0, in: input) }, [false, true])
    }

    func testFocusedSelectionAbsenceShowsTheOwnersWordsAndNeverANeighboursFigure() {
        let cohort = [Self.weekSeries(Self.brennan), Self.weekSeries(Self.schauffele)]
        let twin = Self.series(Self.mitchell, runs: Self.weekSeries(Self.mitchell).runs, overrideID: Self.brennan)
        let blank = Self.series(Self.mitchell, runs: Self.weekSeries(Self.mitchell).runs, overrideID: "")
        let cases: [([FieldHistorySeries10868], FieldHistoryOriginalSelection10868, String)] = [
            (cohort, .series(id: Self.mitchell, missingWords: "Keith Mitchell isn't in this chart"),
             "Keith Mitchell isn't in this chart"),
            (cohort, .unavailable(words: "Selected golfer withdrew"), "Selected golfer withdrew"),
            (cohort + [blank], .series(id: "", missingWords: "Golfer unknown"), "Golfer unknown"),
            (cohort + [twin], .series(id: Self.brennan, missingWords: "Golfer ambiguous"), "Golfer ambiguous"),
            ([], .series(id: Self.brennan, missingWords: "No golfers drawn"), "No golfers drawn"),
        ]
        for (series, selection, words) in cases {
            let input = Self.laidOut(Self.input(series: series, selection: selection), .focused)
            XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(input), .words(words), words)
        }
        let unselected = Self.laidOut(Self.input(series: cohort), .focused)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(unselected), FieldHistorySelectedSummary10868.none)
    }

    func testExpandedCompositionKeepsThePlotFirstWithTheFullKeyBelow() {
        let input = Self.laidOut(Self.input(series: Self.order.map { Self.weekSeries($0) }), .expanded)
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(input), [])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksBelowPlot(input), [.selectionWords, .key])
    }

    func testSelectionAbsenceIsVisibleOnceInEveryComposition() {
        let base = Self.input(series: [Self.weekSeries(Self.brennan)],
                              selection: .unavailable(words: "Selected golfer withdrew"))
        for layout in FieldHistoryLayout10868.allCases {
            let input = Self.laidOut(base, layout)
            let carriers = Self.blocks(input).filter { $0 == .selectionWords || $0 == .selectedSummary }
            XCTAssertEqual(carriers.count, 1, "\(layout)")
            XCTAssertEqual(Self.blocks(input).filter { $0 == .key }.count, 1, "\(layout)")
            XCTAssertEqual(FieldHistoryGeometry10868.selectionWords(input), "Selected golfer withdrew")
            if carriers == [.selectedSummary] {
                XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(input), .words("Selected golfer withdrew"))
            }
        }
    }

    // MARK: Correction F2 — inspected readout binding (CONSTRUCTED intents)

    private static let inspectedReadout = FieldHistoryReadoutIntent10868.beforeAndInspected(
        beforeLabel: "Before tournament", inspectedLabel: "At this moment")
    private static let unboundWords = "Not bound to this moment"
    private static let reminder = FieldHistoryReading10868.independent(figure: "2.6%", provenance: "Oct 6, 9:08 AM EDT")

    /// The same input with distinct unbound words, so they cannot be confused
    /// with an absence reading's own words.
    private static func unbound(_ i: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: i.title, caption: i.caption, series: i.series, selection: i.selection, domain: i.domain,
            ceiling: i.ceiling, yTicks: i.yTicks, xTicks: i.xTicks, guides: i.guides, breaks: i.breaks,
            readout: i.readout, markKey: i.markKey, comparisonExplanation: i.comparisonExplanation, notes: i.notes,
            summary: i.summary, plotHeight: i.plotHeight, unboundReadingWords: unboundWords,
            plotUnavailableWords: i.plotUnavailableWords, windows: i.windows, scale: i.scale,
            moreOriginals: i.moreOriginals, details: i.details, expand: i.expand, inspect: i.inspect,
            previous: i.previous, next: i.next, inspection: i.inspection, layout: i.layout)
    }

    private static func inspected(_ series: [FieldHistorySeries10868],
                                  _ selections: [String: FieldHistorySelection10868]?,
                                  readout: FieldHistoryReadoutIntent10868 = inspectedReadout,
                                  selection: FieldHistoryOriginalSelection10868 = .none,
                                  domain: FieldHistoryDomain10868 = weekDomain,
                                  ceiling: Double = 0.5,
                                  yTicks: [FieldHistoryTick10868] = weekTicks) -> FieldHistoryInput10868 {
        let inspection = selections.map {
            FieldHistoryInspection10868(x: nil, caption: "Recorded Oct 8, 11:46 PM EDT", selections: $0, choices: [],
                                        choicePresentation: .slider(label: "Recorded history moment"), note: nil)
        }
        return unbound(input(series: series, selection: selection, domain: domain, ceiling: ceiling, yTicks: yTicks, readout: readout,
                             inspection: inspection))
    }

    private static func brennanWeek(recorded: FieldHistoryReading10868,
                                    extra: [FieldHistoryRun10868] = []) -> FieldHistorySeries10868 {
        series(brennan, runs: weekSeries(brennan).runs + extra, before: reminder, recorded: recorded)
    }

    private func second(_ input: FieldHistoryInput10868, _ index: Int = 0) -> FieldHistoryReadingDisplay10868 {
        FieldHistoryGeometry10868.readoutSlots(input.series[index], in: input)[1].display
    }

    func testAnInspectedReadoutShowsTheFigureBoundToTheExactInspectedObservation() {
        let id = Self.pid(Self.brennan, 128)
        let brennan = Self.brennanWeek(recorded: .observation(pointID: id, figure: "2.4%",
                                                              provenance: "Recorded Oct 8, 11:46 PM EDT"))
        let input = Self.inspected([brennan], [Self.brennan: .point(id: id, spoken: "2.4%")])
        let slots = FieldHistoryGeometry10868.readoutSlots(brennan, in: input)
        XCTAssertEqual(slots.map(\.label), ["Before tournament", "At this moment"])
        XCTAssertEqual(slots.map(\.display), [.figure("2.6%", provenance: "Oct 6, 9:08 AM EDT"),
                                              .figure("2.4%", provenance: "Recorded Oct 8, 11:46 PM EDT")])
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(brennan, in: input)?.id, id)
        XCTAssertEqual(FieldHistoryGeometry10868.spokenSlot(slots[1]), "At this moment 2.4%, Recorded Oct 8, 11:46 PM EDT")
    }

    func testAMismatchedRecordedIDNeverStandsInForTheInspectedPoint() {
        // ARCHIVED equal values: Brennan raw 2 and raw 334 are both 0.026017.
        let early = Self.point(Self.brennan, 2, style: .hollow), late = Self.point(Self.brennan, 334)
        let equal = Self.series(Self.brennan, runs: [Self.run("a", [early]), Self.run("b", [late])], before: Self.reminder,
                                recorded: .observation(pointID: early.id, figure: "2.6%", provenance: "Oct 6"))
        let wide = FieldHistoryDomain10868(lower: 1_791_158_400, upper: 1_791_760_000)
        let same = Self.inspected([equal], [Self.brennan: .point(id: late.id, spoken: "2.6%")], domain: wide,
                                  ceiling: 0.10, yTicks: Self.autoBeforeTicks)
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(equal, in: same)?.id, late.id)
        XCTAssertEqual(second(same), .words(Self.unboundWords))
        // Different probability: inspected raw 128, recorded bound to raw 294.
        let other = Self.brennanWeek(recorded: .observation(pointID: Self.pid(Self.brennan, 294), figure: "13.8%",
                                                            provenance: "Recorded Oct 10, 11:27 PM EDT"))
        let differs = Self.inspected([other], [Self.brennan: .point(id: Self.pid(Self.brennan, 128), spoken: "2.4%")])
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(other, in: differs)?.id, Self.pid(Self.brennan, 128))
        XCTAssertEqual(second(differs), .words(Self.unboundWords))
    }

    func testAnExplicitInspectionAbsenceShowsItsOwnWordsAndNoFigure() {
        let brennan = Self.brennanWeek(recorded: .observation(pointID: Self.pid(Self.brennan, 128), figure: "2.4%",
                                                              provenance: "Recorded Oct 8, 11:46 PM EDT"))
        let selections: [String: FieldHistorySelection10868] = [Self.brennan: .absent(words: "No observation at this moment")]
        let input = Self.inspected([brennan], selections)
        XCTAssertEqual(second(input), .words("No observation at this moment"))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(brennan, in: input))
        // The slot carries the absence, so the key note does not repeat it;
        // the ordinary intent keeps its note.
        XCTAssertNil(FieldHistoryGeometry10868.keyNote(brennan, in: input))
        let ordinary = Self.inspected([brennan], selections,
                                      readout: .beforeAndRecorded(beforeLabel: "Before tournament", recordedLabel: "Recorded"))
        XCTAssertEqual(FieldHistoryGeometry10868.keyNote(brennan, in: ordinary), "No observation at this moment")
    }

    func testAMissingInspectionOrSelectionNeverPrintsTheRecordedFigure() {
        let id = Self.pid(Self.brennan, 128)
        let brennan = Self.brennanWeek(recorded: .observation(pointID: id, figure: "2.4%",
                                                              provenance: "Recorded Oct 8, 11:46 PM EDT"))
        XCTAssertEqual(second(Self.inspected([brennan], nil)), .words(Self.unboundWords))
        XCTAssertEqual(second(Self.inspected([brennan], [:])), .words(Self.unboundWords))
        XCTAssertEqual(second(Self.inspected([brennan], [Self.mitchell: .point(id: id, spoken: "2.4%")])),
                       .words(Self.unboundWords))
        // The before reminder keeps its own figure and provenance throughout.
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(brennan, in: Self.inspected([brennan], nil))[0].display,
                       .figure("2.6%", provenance: "Oct 6, 9:08 AM EDT"))
    }

    func testUnknownDuplicateOrEmptySeriesAndPointIDsAreUnbound() {
        let p = Self.point(Self.brennan, 128)
        let twin = FieldHistoryPoint10868(id: p.id, x: p.x - 60, probability: p.probability, style: .filled)
        let blankPoint = FieldHistoryPoint10868(id: "", x: p.x + 60, probability: 0.03, style: .filled)
        func bound(_ id: String) -> FieldHistoryReading10868 {
            .observation(pointID: id, figure: "2.4%", provenance: "Recorded Oct 8, 11:46 PM EDT")
        }
        // Unknown, duplicate and empty point ids.
        let unknown = Self.brennanWeek(recorded: bound("\(Self.brennan)#999"))
        XCTAssertEqual(second(Self.inspected([unknown], [Self.brennan: .point(id: "\(Self.brennan)#999", spoken: "x")])),
                       .words(Self.unboundWords))
        let duplicate = Self.brennanWeek(recorded: bound(p.id), extra: [Self.run("twin", [twin])])
        XCTAssertEqual(second(Self.inspected([duplicate], [Self.brennan: .point(id: p.id, spoken: "2.4%")])),
                       .words(Self.unboundWords))
        let blank = Self.brennanWeek(recorded: bound(""), extra: [Self.run("blank", [blankPoint])])
        XCTAssertEqual(second(Self.inspected([blank], [Self.brennan: .point(id: "", spoken: "3%")])),
                       .words(Self.unboundWords))
        // Duplicate and empty series ids: neither a figure nor the absence words.
        let one = Self.brennanWeek(recorded: bound(p.id))
        let shared = Self.series(Self.mitchell, runs: Self.weekSeries(Self.mitchell).runs, overrideID: Self.brennan)
        let both = Self.inspected([one, shared], [Self.brennan: .point(id: p.id, spoken: "2.4%")])
        XCTAssertEqual([second(both, 0), second(both, 1)], [.words(Self.unboundWords), .words(Self.unboundWords)])
        let nameless = Self.series(Self.brennan, runs: Self.weekSeries(Self.brennan).runs, before: Self.reminder,
                                   recorded: bound(p.id), overrideID: "")
        XCTAssertEqual(second(Self.inspected([nameless], ["": .point(id: p.id, spoken: "2.4%")])),
                       .words(Self.unboundWords))
        XCTAssertEqual(second(Self.inspected([nameless], ["": .absent(words: "No observation at this moment")])),
                       .words(Self.unboundWords))
    }

    func testAnUnplaceableInspectedPointIsUnboundWhileTheOrdinaryRecordedSlotIsUnchanged() {
        // ARCHIVED 100% (raw 333) under a CONSTRUCTED 0–50% ceiling, and the
        // later raw 334 outside the week domain.
        let ordinaryIntent = FieldHistoryReadoutIntent10868.beforeAndRecorded(beforeLabel: "Before tournament",
                                                                             recordedLabel: "Recorded")
        for index in [333, 334] {
            let id = Self.pid(Self.brennan, index)
            let extra: [FieldHistoryRun10868] = index == 334 ? [Self.run("later", [Self.point(Self.brennan, 334)])] : []
            let brennan = Self.brennanWeek(recorded: .observation(pointID: id, figure: "figure \(index)",
                                                                  provenance: "provenance \(index)"), extra: extra)
            let selections: [String: FieldHistorySelection10868] = [Self.brennan: .point(id: id, spoken: "x")]
            let inspected = Self.inspected([brennan], selections)
            XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(brennan, in: inspected), "\(index)")
            XCTAssertEqual(second(inspected), .words(Self.unboundWords), "\(index)")
            let ordinary = Self.inspected([brennan], selections, readout: ordinaryIntent)
            XCTAssertEqual(second(ordinary), .figure("figure \(index)", provenance: "provenance \(index)"), "\(index)")
        }
    }

    func testAnIndependentRecordedReadingIsRejectedOnlyInTheInspectedIntent() {
        let id = Self.pid(Self.brennan, 128)
        let brennan = Self.brennanWeek(recorded: .independent(figure: "2.4%", provenance: "Owner-admitted reading"))
        let selections: [String: FieldHistorySelection10868] = [Self.brennan: .point(id: id, spoken: "2.4%")]
        XCTAssertEqual(second(Self.inspected([brennan], selections)), .words(Self.unboundWords))
        let ordinary = Self.inspected([brennan], selections,
                                      readout: .beforeAndRecorded(beforeLabel: "Before tournament", recordedLabel: "Recorded"))
        XCTAssertEqual(second(ordinary), .figure("2.4%", provenance: "Owner-admitted reading"))
        // A single-before intent shows only the reminder, inspection or not.
        let single = Self.inspected([brennan], selections, readout: .singleBefore(label: "Before tournament"))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(brennan, in: single),
                       [FieldHistoryReadoutSlot10868(label: "Before tournament",
                                                     display: .figure("2.6%", provenance: "Oct 6, 9:08 AM EDT"))])
    }

    func testAnOffWindowBeforeReminderKeepsItsOwnProvenanceBesideTheInspectedSlot() {
        let id = Self.pid(Self.brennan, 128)
        let brennan = Self.brennanWeek(recorded: .observation(pointID: id, figure: "2.4%",
                                                              provenance: "Recorded Oct 8, 11:46 PM EDT"))
        let input = Self.inspected([brennan], [Self.brennan: .point(id: id, spoken: "2.4%")])
        XCTAssertFalse(FieldHistoryGeometry10868.marks(brennan, in: input)
            .contains { $0.x == Self.record(Self.brennan, 2).x })
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(brennan, in: input)[0].display,
                       .figure("2.6%", provenance: "Oct 6, 9:08 AM EDT"))
    }

    func testTheFocusedHeadlineAndTheKeyShowTheSameInspectedSlots() {
        let brennan = Self.brennanWeek(recorded: .observation(pointID: Self.pid(Self.brennan, 294), figure: "13.8%",
                                                              provenance: "Recorded Oct 10, 11:27 PM EDT"))
        let mitchell = Self.series(Self.mitchell, runs: Self.weekSeries(Self.mitchell).runs)
        let input = Self.laidOut(Self.inspected([brennan, mitchell],
                                                [Self.brennan: .point(id: Self.pid(Self.brennan, 128), spoken: "2.4%")],
                                                selection: .series(id: Self.brennan, missingWords: "Golfer unavailable")),
                                 .focused)
        guard case .original(let chosen, let slots) = FieldHistoryGeometry10868.selectedSummary(input) else {
            return XCTFail("the exact selected original leads")
        }
        XCTAssertEqual(chosen.id, Self.brennan)
        XCTAssertEqual(slots, FieldHistoryGeometry10868.readoutSlots(brennan, in: input))
        XCTAssertEqual(slots[1].display, .words(Self.unboundWords))
        XCTAssertEqual(FieldHistoryGeometry10868.spokenSlot(slots[1]), "At this moment: \(Self.unboundWords)")
    }

    // MARK: Correction F3 — visible link explanation (CONSTRUCTED words)

    func testWhitespaceOnlyExplanationsDrawNoDashedLinkAndNonblankWordsStayVerbatim() {
        for explanation in [" ", "   ", "\t", "\n", "\n\n", " \t\n "] {
            let input = Self.beforeInput(explanation: explanation)
            XCTAssertFalse(FieldHistoryGeometry10868.showsComparisonExplanation(input), explanation.debugDescription)
            XCTAssertTrue(input.series.allSatisfy { FieldHistoryGeometry10868.comparisonLinks($0, in: input).isEmpty })
            XCTAssertFalse(FieldHistoryGeometry10868.drawsComparisonLink(input))
            XCTAssertNil(FieldHistoryGeometry10868.comparisonKeyWords(input))
        }
        let multiline = "  Dashed links compare recorded estimates,\n\tnot a continuous history.  "
        let input = Self.beforeInput(explanation: multiline)
        XCTAssertTrue(FieldHistoryGeometry10868.showsComparisonExplanation(input))
        XCTAssertEqual(FieldHistoryGeometry10868.comparisonLinks(input.series[0], in: input).count, 2)
        XCTAssertEqual(FieldHistoryGeometry10868.comparisonKeyWords(input), multiline)
        XCTAssertNil(FieldHistoryGeometry10868.comparisonKeyWords(Self.beforeInput(explanation: nil)))
    }
}

/// The weather reference's 76–77°F range uses an upright triangle, alongside
/// the existing circle and diamond identities. This checks the shared mark
/// primitive only; no weather binding, rendered fit or native test execution
/// is established by preparing these assertions.
final class FieldHistoryWeatherTriangle10868Tests: XCTestCase {
    func testTriangleKeepsTheApprovedUprightIdentityAndOpenUpperCorners() {
        let center = CGPoint(x: 50, y: 50)
        let triangle = FieldHistoryGeometry10868.markPath(.triangle, at: center, radius: 4)
        XCTAssertEqual(triangle.boundingRect.minX, 45.6, accuracy: 1e-9)
        XCTAssertEqual(triangle.boundingRect.maxX, 54.4, accuracy: 1e-9)
        XCTAssertEqual(triangle.boundingRect.minY, 45, accuracy: 1e-9)
        XCTAssertEqual(triangle.boundingRect.maxY, 54, accuracy: 1e-9)
        XCTAssertTrue(triangle.contains(CGPoint(x: 50, y: 50)))
        XCTAssertTrue(triangle.contains(CGPoint(x: 50, y: 45.1)))
        XCTAssertTrue(triangle.contains(CGPoint(x: 46, y: 53.8)))
        XCTAssertFalse(triangle.contains(CGPoint(x: 46, y: 46)))
        XCTAssertFalse(triangle.contains(CGPoint(x: 54, y: 46)))
    }

    func testObservationKeyAndInspectionRadiiKeepTheSameTriangleIdentity() {
        let center = CGPoint(x: 37, y: 61)
        // The real view's observed mark, identity glyph and inspection ring
        // all call markPath with these relative radii.
        for multiplier in [CGFloat(1), CGFloat(1.3), CGFloat(2)] {
            let radius = 3 * multiplier
            let path = FieldHistoryGeometry10868.markPath(.triangle, at: center, radius: radius)
            XCTAssertEqual(path.boundingRect.midX, center.x, accuracy: 1e-9)
            XCTAssertEqual(path.boundingRect.minY, center.y - radius * 1.25, accuracy: 1e-9)
            XCTAssertEqual(path.boundingRect.maxY, center.y + radius, accuracy: 1e-9)
            XCTAssertTrue(path.contains(center))
            XCTAssertFalse(path.contains(CGPoint(x: center.x + radius, y: center.y - radius)))
        }
    }
}

// MARK: Explicit owner probability crop — PREPARED, NOT_RUN

/// ARCHIVED: Sweden .48 at 1771754400 and Switzerland .57 at 1771754640,
/// independent Kalshi trade minutes before listed start 1771754700. The
/// approved curling reference shows a 35–70% before-match range. Its actual
/// start and finish are unknown. CONSTRUCTED: opaque point/run ids, frame,
/// labels, invalid/out-of-frame controls and inspection state. This prepares
/// shared-chart guards; it establishes no rendered or production acceptance.
extension FieldProbabilityHistoryPresentation10868Tests {
    private static let curlingIDs = ["KXWOCURLGAME-26FEB22SWECHE-SWE", "KXWOCURLGAME-26FEB22SWECHE-CHE"]

    private static func curlingSeries(_ index: Int, points: [FieldHistoryPoint10868]? = nil) -> FieldHistorySeries10868 {
        let point = FieldHistoryPoint10868(id: "constructed:before:\(curlingIDs[index])",
                                          x: index == 0 ? 1771754400 : 1771754640,
                                          probability: index == 0 ? 0.48 : 0.57, style: .hollow)
        let figure = index == 0 ? "48%" : "57%"
        let provenance = index == 0 ? "Feb 22, 2:00 AM PT · Kalshi · before listed start" : "Feb 22, 2:04 AM PT · Kalshi · before listed start"
        return FieldHistorySeries10868(
            id: curlingIDs[index], name: index == 0 ? "Sweden" : "Switzerland",
            shape: index == 0 ? .circle : .diamond, tint: index == 0 ? .blue : .orange,
            runs: [FieldHistoryRun10868(id: "constructed:run:\(index)", points: points ?? [point])],
            links: [], labelPointID: point.id,
            before: .independent(figure: figure, provenance: provenance),
            recorded: .absent(words: "No inspected observation"), absentWords: "No history in this view", choose: nil)
    }

    private static func curlingInput(series: [FieldHistorySeries10868]? = nil,
                                     lower: Double = 0.35, ceiling: Double = 0.7,
                                     readout: FieldHistoryReadoutIntent10868 = .singleBefore(label: "Before listed start"),
                                     inspection: FieldHistoryInspection10868? = nil,
                                     rangeWords: String? = "Zoomed probability range · 35–70%") -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: "Win probability history", caption: "Before listed start · independent trade minutes",
            series: series ?? [curlingSeries(0), curlingSeries(1)], selection: .none,
            domain: FieldHistoryDomain10868(lower: 1771754000, upper: 1771754700), ceiling: ceiling,
            yTicks: [FieldHistoryTick10868(value: 0.35, lines: ["35%"]),
                     FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 0.7, lines: ["70%"])],
            xTicks: [], guides: [], breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Earlier trade", filled: nil), comparisonExplanation: nil,
            notes: ["Independent Kalshi minutes; actual start is unknown."],
            summary: "Sweden 48% and Switzerland 57%, each at its own earlier minute; independent observations.",
            plotHeight: 240, unboundReadingWords: "Not visible in this view", plotUnavailableWords: "History unavailable",
            windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: nil, inspect: nil,
            previous: nil, next: nil, inspection: inspection, probabilityLowerBound: lower,
            probabilityRangeExplanation: rangeWords)
    }

    func testTheRealCurlingBaselinesKeepOwnChancesOnTheExplicitReferenceRange() {
        let input = Self.curlingInput()
        XCTAssertTrue(FieldHistoryGeometry10868.isDrawable(input))
        XCTAssertEqual(input.series.map(\.name), ["Sweden", "Switzerland"])
        let points = input.series.map { FieldHistoryGeometry10868.marks($0, in: input)[0] }
        XCTAssertEqual(points.map(\.probability), [0.48, 0.57])
        XCTAssertEqual(points.map(\.x), [1771754400, 1771754640])
        XCTAssertEqual(points.map(\.probability).reduce(0, +), 1.05, accuracy: 1e-12)
        XCTAssertEqual(FieldHistoryGeometry10868.labelTarget(points[0], in: input).yFraction,
                       (0.48 - 0.35) / 0.35, accuracy: 1e-12)
        XCTAssertEqual(FieldHistoryGeometry10868.labelTarget(points[1], in: input).yFraction,
                       (0.57 - 0.35) / 0.35, accuracy: 1e-12)
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(input.series[0], in: input)[0].display,
                       .figure("48%", provenance: "Feb 22, 2:00 AM PT · Kalshi · before listed start"))
    }

    func testTicksMarksAndDirectLabelsUseTheSameExplicitProbabilityCoordinate() {
        let input = Self.curlingInput()
        let rect = CGRect(x: 10, y: 20, width: 260, height: 140)
        XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(input).map(\.value), [0.35, 0.5, 0.7])
        for value in [0.35, 0.5, 0.7] {
            let point = FieldHistoryPoint10868(id: "constructed:edge", x: 1771754400, probability: value, style: .hollow)
            let fraction = FieldHistoryGeometry10868.probabilityFraction(value, lower: 0.35, ceiling: 0.7)
            let placed = FieldHistoryGeometry10868.position(point, in: input, rect: rect)
            XCTAssertEqual(placed.y, rect.maxY - CGFloat(fraction) * rect.height, accuracy: 1e-9)
            XCTAssertEqual(FieldHistoryGeometry10868.labelTarget(point, in: input).yFraction, fraction)
        }
        XCTAssertEqual(FieldHistoryGeometry10868.yPosition(0.35, ceiling: 0.7, lower: 0.35, in: rect), rect.maxY)
        XCTAssertEqual(FieldHistoryGeometry10868.yPosition(0.7, ceiling: 0.7, lower: 0.35, in: rect), rect.minY)
    }

    func testBelowCropObservationsBreakRunsAndNeverClampToTheLowerEdge() {
        let points = [FieldHistoryPoint10868(id: "a", x: 1771754400, probability: 0.48, style: .hollow),
                      FieldHistoryPoint10868(id: "outside", x: 1771754450, probability: 0.34, style: .hollow),
                      FieldHistoryPoint10868(id: "b", x: 1771754500, probability: 0.57, style: .hollow)]
        let original = Self.curlingSeries(0, points: points)
        let series = FieldHistorySeries10868(
            id: original.id, name: original.name, shape: original.shape, tint: original.tint,
            runs: original.runs, links: [], labelPointID: "outside", before: original.before,
            recorded: original.recorded, absentWords: original.absentWords, choose: nil)
        let input = Self.curlingInput(series: [series])
        XCTAssertEqual(FieldHistoryGeometry10868.drawnRuns(series.runs[0], in: input).map { $0.map(\.id) }, [["a"], ["b"]])
        XCTAssertEqual(FieldHistoryGeometry10868.marks(series, in: input).map(\.probability), [0.48, 0.57])
        XCTAssertFalse(FieldHistoryGeometry10868.isPlaceable(points[1], in: input))
        XCTAssertNil(FieldHistoryGeometry10868.labelAnchor(series, in: input), "a cropped explicit anchor gets no replacement")
        XCTAssertEqual(series.runs[0].points[1].probability, 0.34, "raw observation stays unchanged")
    }

    func testInvalidLowerBoundsDrawNoNumericContentAndBorrowNoRange() {
        for lower in [-0.1, 0.7, 0.8, Double.nan, .infinity] {
            let input = Self.curlingInput(lower: lower)
            XCTAssertFalse(FieldHistoryGeometry10868.isDrawable(input))
            XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(input), [])
            XCTAssertTrue(input.series.allSatisfy { FieldHistoryGeometry10868.marks($0, in: input).isEmpty })
            XCTAssertEqual(input.series[0].before,
                           .independent(figure: "48%", provenance: "Feb 22, 2:00 AM PT · Kalshi · before listed start"))
        }
    }

    func testInspectionBelowTheExplicitRangeGetsNoEdgeRingOrBorrowedFigure() {
        let outside = FieldHistoryPoint10868(id: "constructed:below", x: 1771754400, probability: 0.34, style: .hollow)
        let original = Self.curlingSeries(0, points: [outside])
        let series = FieldHistorySeries10868(
            id: original.id, name: original.name, shape: original.shape, tint: original.tint,
            runs: original.runs, links: [], labelPointID: outside.id, before: original.before,
            recorded: .observation(pointID: outside.id, figure: "Constructed 34%", provenance: "Constructed control"),
            absentWords: original.absentWords, choose: nil)
        let inspection = FieldHistoryInspection10868(
            x: outside.x, caption: "Constructed inspected point",
            selections: [series.id: .point(id: outside.id, spoken: "Constructed 34%")], choices: [],
            choicePresentation: .buttons(groupLabel: "Inspect point"), note: nil)
        let input = Self.curlingInput(series: [series],
                                     readout: .beforeAndInspected(beforeLabel: "Before listed start", inspectedLabel: "Inspected"),
                                     inspection: inspection)
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series, in: input))
        XCTAssertNil(FieldHistoryGeometry10868.labelAnchor(series, in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedDisplay(series, in: input), .words("Not visible in this view"))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: input)[0].display,
                       .figure("48%", provenance: "Feb 22, 2:00 AM PT · Kalshi · before listed start"))
        XCTAssertEqual(series.runs[0].points[0].probability, 0.34)
    }

    func testDefaultZeroBasedCoordinatesAndGenuineZeroArePreserved() {
        let original = Self.input(series: [Self.weekSeries(Self.brennan)])
        XCTAssertEqual(original.probabilityLowerBound, 0)
        let rect = CGRect(x: 0, y: 0, width: 260, height: 140)
        XCTAssertEqual(FieldHistoryGeometry10868.yPosition(0.25, ceiling: 0.5, in: rect), 70)
        XCTAssertEqual(FieldHistoryGeometry10868.probabilityFraction(0.25, ceiling: 0.5), 0.5)
        let zero = FieldHistoryPoint10868(id: "constructed:zero", x: 1771754400, probability: 0, style: .filled)
        XCTAssertTrue(FieldHistoryGeometry10868.isPlaceable(zero, domain: Self.curlingInput().domain, ceiling: 0.7))
        XCTAssertFalse(FieldHistoryGeometry10868.isPlaceable(zero, in: Self.curlingInput()))
        XCTAssertEqual(zero.probability, 0)
    }

    func testANonzeroProbabilityCropRequiresTheVisibleOwnerExplanation() {
        let missingWords: [String?] = [nil, "", " ", "\n\t"]
        for words in missingWords {
            let input = Self.curlingInput(rangeWords: words)
            XCTAssertFalse(FieldHistoryGeometry10868.isDrawable(input))
            XCTAssertTrue(input.series.allSatisfy { FieldHistoryGeometry10868.marks($0, in: input).isEmpty })
            XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(input), [])
            XCTAssertNil(FieldHistoryGeometry10868.probabilityRangeExplanation(input))
        }
        let words = "Zoomed probability range · 35–70%"
        let explained = Self.curlingInput(rangeWords: words)
        XCTAssertTrue(FieldHistoryGeometry10868.isDrawable(explained))
        XCTAssertEqual(FieldHistoryGeometry10868.probabilityRangeExplanation(explained), words)
        // A caller that never opted into a lower crop needs no new explanation.
        XCTAssertTrue(FieldHistoryGeometry10868.isDrawable(Self.curlingInput(lower: 0, rangeWords: nil)))
    }
}

/// Real Singapore racing observations exercised through the existing shared
/// FieldHistory contract. This is test preparation, not a new view, replay host,
/// production adapter or route-readiness claim. All native tests are NOT_RUN.
///
/// The pinned racingLifecycle/racingLiveEvidence helpers supplied the exact
/// five reference windows and explicit runs: before, laps46/52/58, and final.
/// The 450 distinct retained observations, three exact market/outcome identities,
/// own clocks, quotes and lap-report clocks are in
/// RACING-HISTORY-REUSE-REFERENCE.json. The fixture generator ran the actual
/// probabilityLabel and eventReaderTime helpers in America/Los_Angeles.
///
/// Constructed owner ports: opaque point/run IDs, shape/tint/style assignment,
/// labels and source words, readout intent, selection and inspection. The
/// reference's trade eligibility, five-minute run splitting and last-quote
/// election are NOT native policies; the tests pass their resolved outputs.
/// Classification and settled0/1results never enter the history input.
/// The final domain ends at the last-lap report's publication, not a finish time.
final class RacingSharedHistoryContract10868Tests: XCTestCase {
    private struct Sample {
        let x: Double
        let probability: Double
        let figure: String
        let clock: String
    }

    private struct Driver {
        let id: String
        let name: String
        let shape: FieldHistoryShape10868
        let beforeIndex: Int
        let samples: [Sample]

        func pointID(_ index: Int) -> String { "constructed-point:\(id):\(index)" }
        func provenance(_ index: Int) -> String { "\(samples[index].clock) PT · Polymarket historical trade" }
        func reading(_ index: Int) -> FieldHistoryReading10868 {
            .observation(pointID: pointID(index), figure: samples[index].figure, provenance: provenance(index))
        }
    }

    private struct Moment {
        let stage: Int
        let domain: FieldHistoryDomain10868
        let caption: String
        /// Owner-resolved run indexes into each driver's own observation bank.
        let runs: [[[Int]]]
        let headlineIndexes: [Int?]
        let expectedCounts: [Int]
        let expectedLineSizes: [[Int]]
    }

    // Retained observations from pinned reference helpers; owner fixture ports only.
    private static let drivers: [Driver] = [
        Driver(id: "polymarket:5229406:105026689771335810478914327541724319323338915766526076386906176141135574302746", name: "Max Verstappen", shape: .circle, beforeIndex: 46, samples: [
            Sample(x: 1791713032000, probability: 0.6599999992, figure: "66%", clock: "Oct 11, 3:03:52 AM"),
            Sample(x: 1791713122000, probability: 0.66, figure: "66%", clock: "Oct 11, 3:05:22 AM"),
            Sample(x: 1791713385000, probability: 0.6599999461, figure: "66%", clock: "Oct 11, 3:09:45 AM"),
            Sample(x: 1791713957000, probability: 0.66, figure: "66%", clock: "Oct 11, 3:19:17 AM"),
            Sample(x: 1791714372000, probability: 0.6599999955, figure: "66%", clock: "Oct 11, 3:26:12 AM"),
            Sample(x: 1791714944000, probability: 0.6599999576, figure: "66%", clock: "Oct 11, 3:35:44 AM"),
            Sample(x: 1791715224000, probability: 0.649999805, figure: "65%", clock: "Oct 11, 3:40:24 AM"),
            Sample(x: 1791715229000, probability: 0.649999974, figure: "65%", clock: "Oct 11, 3:40:29 AM"),
            Sample(x: 1791715310000, probability: 0.6499999998, figure: "65%", clock: "Oct 11, 3:41:50 AM"),
            Sample(x: 1791715332000, probability: 0.6499999951, figure: "65%", clock: "Oct 11, 3:42:12 AM"),
            Sample(x: 1791715956000, probability: 0.65, figure: "65%", clock: "Oct 11, 3:52:36 AM"),
            Sample(x: 1791715994000, probability: 0.6499999944, figure: "65%", clock: "Oct 11, 3:53:14 AM"),
            Sample(x: 1791716295000, probability: 0.65, figure: "65%", clock: "Oct 11, 3:58:15 AM"),
            Sample(x: 1791716300000, probability: 0.65, figure: "65%", clock: "Oct 11, 3:58:20 AM"),
            Sample(x: 1791716694000, probability: 0.6499999994, figure: "65%", clock: "Oct 11, 4:04:54 AM"),
            Sample(x: 1791717032000, probability: 0.6499999928, figure: "65%", clock: "Oct 11, 4:10:32 AM"),
            Sample(x: 1791717045000, probability: 0.6499999976, figure: "65%", clock: "Oct 11, 4:10:45 AM"),
            Sample(x: 1791717438000, probability: 0.6499999935, figure: "65%", clock: "Oct 11, 4:17:18 AM"),
            Sample(x: 1791717744000, probability: 0.65, figure: "65%", clock: "Oct 11, 4:22:24 AM"),
            Sample(x: 1791717794000, probability: 0.6499999025, figure: "65%", clock: "Oct 11, 4:23:14 AM"),
            Sample(x: 1791717906000, probability: 0.649999805, figure: "65%", clock: "Oct 11, 4:25:06 AM"),
            Sample(x: 1791718122000, probability: 0.6499999951, figure: "65%", clock: "Oct 11, 4:28:42 AM"),
            Sample(x: 1791718344000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:32:24 AM"),
            Sample(x: 1791718491000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:34:51 AM"),
            Sample(x: 1791718668000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:37:48 AM"),
            Sample(x: 1791718676000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:37:56 AM"),
            Sample(x: 1791718724000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:38:44 AM"),
            Sample(x: 1791718730000, probability: 0.6429897399, figure: "64.3%", clock: "Oct 11, 4:38:50 AM"),
            Sample(x: 1791718803000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:40:03 AM"),
            Sample(x: 1791719160000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:46:00 AM"),
            Sample(x: 1791719529000, probability: 0.6401223186, figure: "64%", clock: "Oct 11, 4:52:09 AM"),
            Sample(x: 1791719556000, probability: 0.629999995, figure: "63%", clock: "Oct 11, 4:52:36 AM"),
            Sample(x: 1791719566000, probability: 0.6299999989, figure: "63%", clock: "Oct 11, 4:52:46 AM"),
            Sample(x: 1791719617000, probability: 0.6301637723, figure: "63%", clock: "Oct 11, 4:53:37 AM"),
            Sample(x: 1791719649000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:54:09 AM"),
            Sample(x: 1791719686000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:54:46 AM"),
            Sample(x: 1791719725000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:55:25 AM"),
            Sample(x: 1791719749000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:55:49 AM"),
            Sample(x: 1791719800000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:56:40 AM"),
            Sample(x: 1791719809000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:56:49 AM"),
            Sample(x: 1791719842000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:57:22 AM"),
            Sample(x: 1791719844000, probability: 0.63, figure: "63%", clock: "Oct 11, 4:57:24 AM"),
            Sample(x: 1791719845000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:57:25 AM"),
            Sample(x: 1791719862000, probability: 0.6499999935, figure: "65%", clock: "Oct 11, 4:57:42 AM"),
            Sample(x: 1791719913000, probability: 0.649999999, figure: "65%", clock: "Oct 11, 4:58:33 AM"),
            Sample(x: 1791719959000, probability: 0.64, figure: "64%", clock: "Oct 11, 4:59:19 AM"),
            Sample(x: 1791719971000, probability: 0.6499999935, figure: "65%", clock: "Oct 11, 4:59:31 AM"),
            Sample(x: 1791720055000, probability: 0.6599999843, figure: "66%", clock: "Oct 11, 5:00:55 AM"),
            Sample(x: 1791720079000, probability: 0.65, figure: "65%", clock: "Oct 11, 5:01:19 AM"),
            Sample(x: 1791720151000, probability: 0.649999805, figure: "65%", clock: "Oct 11, 5:02:31 AM"),
            Sample(x: 1791720153000, probability: 0.649999805, figure: "65%", clock: "Oct 11, 5:02:33 AM"),
            Sample(x: 1791720160000, probability: 0.65, figure: "65%", clock: "Oct 11, 5:02:40 AM"),
            Sample(x: 1791720235000, probability: 0.649999805, figure: "65%", clock: "Oct 11, 5:03:55 AM"),
            Sample(x: 1791720237000, probability: 0.6510541282, figure: "65.1%", clock: "Oct 11, 5:03:57 AM"),
            Sample(x: 1791720243000, probability: 0.58, figure: "58%", clock: "Oct 11, 5:04:03 AM"),
            Sample(x: 1791720244000, probability: 0.58, figure: "58%", clock: "Oct 11, 5:04:04 AM"),
            Sample(x: 1791720277000, probability: 0.65, figure: "65%", clock: "Oct 11, 5:04:37 AM"),
            Sample(x: 1791720285000, probability: 0.7599999764, figure: "76%", clock: "Oct 11, 5:04:45 AM"),
            Sample(x: 1791720322000, probability: 0.7699999795, figure: "77%", clock: "Oct 11, 5:05:22 AM"),
            Sample(x: 1791720345000, probability: 0.77, figure: "77%", clock: "Oct 11, 5:05:45 AM"),
            Sample(x: 1791720348000, probability: 0.75, figure: "75%", clock: "Oct 11, 5:05:48 AM"),
            Sample(x: 1791720363000, probability: 0.7699999992, figure: "77%", clock: "Oct 11, 5:06:03 AM"),
            Sample(x: 1791720409000, probability: 0.71, figure: "71%", clock: "Oct 11, 5:06:49 AM"),
            Sample(x: 1791720526000, probability: 0.7, figure: "70%", clock: "Oct 11, 5:08:46 AM"),
            Sample(x: 1791720529000, probability: 0.7, figure: "70%", clock: "Oct 11, 5:08:49 AM"),
            Sample(x: 1791720552000, probability: 0.69999972, figure: "70%", clock: "Oct 11, 5:09:12 AM"),
            Sample(x: 1791720553000, probability: 0.69999972, figure: "70%", clock: "Oct 11, 5:09:13 AM"),
            Sample(x: 1791720556000, probability: 0.7, figure: "70%", clock: "Oct 11, 5:09:16 AM"),
            Sample(x: 1791720561000, probability: 0.7, figure: "70%", clock: "Oct 11, 5:09:21 AM"),
            Sample(x: 1791720766000, probability: 0.66, figure: "66%", clock: "Oct 11, 5:12:46 AM"),
            Sample(x: 1791720768000, probability: 0.66, figure: "66%", clock: "Oct 11, 5:12:48 AM"),
            Sample(x: 1791720789000, probability: 0.66, figure: "66%", clock: "Oct 11, 5:13:09 AM"),
            Sample(x: 1791720843000, probability: 0.69, figure: "69%", clock: "Oct 11, 5:14:03 AM"),
            Sample(x: 1791720879000, probability: 0.72, figure: "72%", clock: "Oct 11, 5:14:39 AM"),
            Sample(x: 1791720892000, probability: 0.7299999807, figure: "73%", clock: "Oct 11, 5:14:52 AM"),
            Sample(x: 1791720984000, probability: 0.7, figure: "70%", clock: "Oct 11, 5:16:24 AM"),
            Sample(x: 1791720993000, probability: 0.7399999997, figure: "74%", clock: "Oct 11, 5:16:33 AM"),
            Sample(x: 1791721026000, probability: 0.746, figure: "74.6%", clock: "Oct 11, 5:17:06 AM"),
            Sample(x: 1791721083000, probability: 0.7299999679, figure: "73%", clock: "Oct 11, 5:18:03 AM"),
            Sample(x: 1791721155000, probability: 0.7384699732, figure: "73.8%", clock: "Oct 11, 5:19:15 AM"),
            Sample(x: 1791721177000, probability: 0.74, figure: "74%", clock: "Oct 11, 5:19:37 AM"),
            Sample(x: 1791721186000, probability: 0.74, figure: "74%", clock: "Oct 11, 5:19:46 AM"),
            Sample(x: 1791721227000, probability: 0.73, figure: "73%", clock: "Oct 11, 5:20:27 AM"),
            Sample(x: 1791721255000, probability: 0.7399999896, figure: "74%", clock: "Oct 11, 5:20:55 AM"),
            Sample(x: 1791721329000, probability: 0.7399999896, figure: "74%", clock: "Oct 11, 5:22:09 AM"),
            Sample(x: 1791721345000, probability: 0.75, figure: "75%", clock: "Oct 11, 5:22:25 AM"),
            Sample(x: 1791721384000, probability: 0.7799999813, figure: "78%", clock: "Oct 11, 5:23:04 AM"),
            Sample(x: 1791721387000, probability: 0.7799999919, figure: "78%", clock: "Oct 11, 5:23:07 AM"),
            Sample(x: 1791721446000, probability: 0.78, figure: "78%", clock: "Oct 11, 5:24:06 AM"),
            Sample(x: 1791721447000, probability: 0.7877756358, figure: "78.8%", clock: "Oct 11, 5:24:07 AM"),
            Sample(x: 1791721476000, probability: 0.79, figure: "79%", clock: "Oct 11, 5:24:36 AM"),
            Sample(x: 1791721482000, probability: 0.8, figure: "80%", clock: "Oct 11, 5:24:42 AM"),
            Sample(x: 1791721504000, probability: 0.8, figure: "80%", clock: "Oct 11, 5:25:04 AM"),
            Sample(x: 1791721530000, probability: 0.8, figure: "80%", clock: "Oct 11, 5:25:30 AM"),
            Sample(x: 1791721579000, probability: 0.8, figure: "80%", clock: "Oct 11, 5:26:19 AM"),
            Sample(x: 1791721588000, probability: 0.8, figure: "80%", clock: "Oct 11, 5:26:28 AM"),
            Sample(x: 1791721672000, probability: 0.8099999966, figure: "81%", clock: "Oct 11, 5:27:52 AM"),
            Sample(x: 1791721752000, probability: 0.7940106952, figure: "79.4%", clock: "Oct 11, 5:29:12 AM"),
            Sample(x: 1791721782000, probability: 0.8099999741, figure: "81%", clock: "Oct 11, 5:29:42 AM"),
            Sample(x: 1791721831000, probability: 0.8199994588, figure: "82%", clock: "Oct 11, 5:30:31 AM"),
            Sample(x: 1791721849000, probability: 0.82, figure: "82%", clock: "Oct 11, 5:30:49 AM"),
            Sample(x: 1791721885000, probability: 0.86, figure: "86%", clock: "Oct 11, 5:31:25 AM"),
            Sample(x: 1791721893000, probability: 0.8599999772, figure: "86%", clock: "Oct 11, 5:31:33 AM"),
            Sample(x: 1791721902000, probability: 0.88, figure: "88%", clock: "Oct 11, 5:31:42 AM"),
            Sample(x: 1791722074000, probability: 0.87, figure: "87%", clock: "Oct 11, 5:34:34 AM"),
            Sample(x: 1791722194000, probability: 0.85, figure: "85%", clock: "Oct 11, 5:36:34 AM"),
            Sample(x: 1791722262000, probability: 0.8878779708, figure: "88.8%", clock: "Oct 11, 5:37:42 AM"),
            Sample(x: 1791722280000, probability: 0.8499999887, figure: "85%", clock: "Oct 11, 5:38:00 AM"),
            Sample(x: 1791722292000, probability: 0.85, figure: "85%", clock: "Oct 11, 5:38:12 AM"),
            Sample(x: 1791722307000, probability: 0.84, figure: "84%", clock: "Oct 11, 5:38:27 AM"),
            Sample(x: 1791722349000, probability: 0.84905, figure: "84.9%", clock: "Oct 11, 5:39:09 AM"),
            Sample(x: 1791722394000, probability: 0.84, figure: "84%", clock: "Oct 11, 5:39:54 AM"),
            Sample(x: 1791722407000, probability: 0.8499999996, figure: "85%", clock: "Oct 11, 5:40:07 AM"),
            Sample(x: 1791722410000, probability: 0.85, figure: "85%", clock: "Oct 11, 5:40:10 AM"),
            Sample(x: 1791722427000, probability: 0.83, figure: "83%", clock: "Oct 11, 5:40:27 AM"),
            Sample(x: 1791722428000, probability: 0.8793931324, figure: "87.9%", clock: "Oct 11, 5:40:28 AM"),
            Sample(x: 1791722439000, probability: 0.88, figure: "88%", clock: "Oct 11, 5:40:39 AM"),
            Sample(x: 1791722682000, probability: 0.879999912, figure: "88%", clock: "Oct 11, 5:44:42 AM"),
            Sample(x: 1791722754000, probability: 0.86, figure: "86%", clock: "Oct 11, 5:45:54 AM"),
            Sample(x: 1791722788000, probability: 0.87, figure: "87%", clock: "Oct 11, 5:46:28 AM"),
            Sample(x: 1791722803000, probability: 0.8833004684, figure: "88.3%", clock: "Oct 11, 5:46:43 AM"),
            Sample(x: 1791722815000, probability: 0.9, figure: "90%", clock: "Oct 11, 5:46:55 AM"),
            Sample(x: 1791722863000, probability: 0.88, figure: "88%", clock: "Oct 11, 5:47:43 AM"),
            Sample(x: 1791722875000, probability: 0.9, figure: "90%", clock: "Oct 11, 5:47:55 AM"),
            Sample(x: 1791722935000, probability: 0.88, figure: "88%", clock: "Oct 11, 5:48:55 AM"),
            Sample(x: 1791722952000, probability: 0.91, figure: "91%", clock: "Oct 11, 5:49:12 AM"),
            Sample(x: 1791722985000, probability: 0.91, figure: "91%", clock: "Oct 11, 5:49:45 AM"),
            Sample(x: 1791722997000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:49:57 AM"),
            Sample(x: 1791723016000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:50:16 AM"),
            Sample(x: 1791723178000, probability: 0.91973, figure: "92%", clock: "Oct 11, 5:52:58 AM"),
            Sample(x: 1791723205000, probability: 0.9099999994, figure: "91%", clock: "Oct 11, 5:53:25 AM"),
            Sample(x: 1791723249000, probability: 0.8754312115, figure: "87.5%", clock: "Oct 11, 5:54:09 AM"),
            Sample(x: 1791723367000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:56:07 AM"),
            Sample(x: 1791723489000, probability: 0.93, figure: "93%", clock: "Oct 11, 5:58:09 AM"),
            Sample(x: 1791723490000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:58:10 AM"),
            Sample(x: 1791723508000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:58:28 AM"),
            Sample(x: 1791723516000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:58:36 AM"),
            Sample(x: 1791723538000, probability: 0.9299999861, figure: "93%", clock: "Oct 11, 5:58:58 AM"),
            Sample(x: 1791723544000, probability: 0.92, figure: "92%", clock: "Oct 11, 5:59:04 AM"),
            Sample(x: 1791723621000, probability: 0.9299999716, figure: "93%", clock: "Oct 11, 6:00:21 AM"),
            Sample(x: 1791723721000, probability: 0.9399999996, figure: "94%", clock: "Oct 11, 6:02:01 AM"),
            Sample(x: 1791723732000, probability: 0.93, figure: "93%", clock: "Oct 11, 6:02:12 AM"),
            Sample(x: 1791723769000, probability: 0.9399999981, figure: "94%", clock: "Oct 11, 6:02:49 AM"),
            Sample(x: 1791723790000, probability: 0.929999938, figure: "93%", clock: "Oct 11, 6:03:10 AM"),
            Sample(x: 1791723811000, probability: 0.9399999994, figure: "94%", clock: "Oct 11, 6:03:31 AM"),
            Sample(x: 1791723846000, probability: 0.92, figure: "92%", clock: "Oct 11, 6:04:06 AM"),
            Sample(x: 1791723871000, probability: 0.959563125, figure: "96%", clock: "Oct 11, 6:04:31 AM"),
            Sample(x: 1791723922000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:05:22 AM"),
            Sample(x: 1791723964000, probability: 0.9399999991, figure: "94%", clock: "Oct 11, 6:06:04 AM"),
            Sample(x: 1791723972000, probability: 0.92, figure: "92%", clock: "Oct 11, 6:06:12 AM"),
            Sample(x: 1791723994000, probability: 0.92, figure: "92%", clock: "Oct 11, 6:06:34 AM"),
            Sample(x: 1791724002000, probability: 0.94, figure: "94%", clock: "Oct 11, 6:06:42 AM"),
            Sample(x: 1791724033000, probability: 0.94, figure: "94%", clock: "Oct 11, 6:07:13 AM"),
            Sample(x: 1791724047000, probability: 0.94, figure: "94%", clock: "Oct 11, 6:07:27 AM"),
            Sample(x: 1791724074000, probability: 0.9399999937, figure: "94%", clock: "Oct 11, 6:07:54 AM"),
            Sample(x: 1791724113000, probability: 0.92, figure: "92%", clock: "Oct 11, 6:08:33 AM"),
            Sample(x: 1791724120000, probability: 0.9399999994, figure: "94%", clock: "Oct 11, 6:08:40 AM"),
            Sample(x: 1791724128000, probability: 0.96, figure: "96%", clock: "Oct 11, 6:08:48 AM"),
            Sample(x: 1791724176000, probability: 0.93, figure: "93%", clock: "Oct 11, 6:09:36 AM"),
            Sample(x: 1791724179000, probability: 0.9499999884, figure: "95%", clock: "Oct 11, 6:09:39 AM"),
            Sample(x: 1791724225000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:10:25 AM"),
            Sample(x: 1791724252000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:10:52 AM"),
            Sample(x: 1791724257000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:10:57 AM"),
            Sample(x: 1791724338000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:12:18 AM"),
            Sample(x: 1791724477000, probability: 0.91, figure: "91%", clock: "Oct 11, 6:14:37 AM"),
            Sample(x: 1791724537000, probability: 0.9199999761, figure: "92%", clock: "Oct 11, 6:15:37 AM"),
            Sample(x: 1791724603000, probability: 0.93, figure: "93%", clock: "Oct 11, 6:16:43 AM"),
            Sample(x: 1791724654000, probability: 0.9399999958, figure: "94%", clock: "Oct 11, 6:17:34 AM"),
            Sample(x: 1791724795000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:19:55 AM"),
            Sample(x: 1791724798000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:19:58 AM"),
            Sample(x: 1791724896000, probability: 0.9684520332, figure: "96.8%", clock: "Oct 11, 6:21:36 AM"),
            Sample(x: 1791724929000, probability: 0.96, figure: "96%", clock: "Oct 11, 6:22:09 AM"),
            Sample(x: 1791724939000, probability: 0.9602090681, figure: "96%", clock: "Oct 11, 6:22:19 AM"),
            Sample(x: 1791724941000, probability: 0.94, figure: "94%", clock: "Oct 11, 6:22:21 AM"),
            Sample(x: 1791724944000, probability: 0.97, figure: "97%", clock: "Oct 11, 6:22:24 AM"),
            Sample(x: 1791724951000, probability: 0.9700829387, figure: "97%", clock: "Oct 11, 6:22:31 AM"),
            Sample(x: 1791724989000, probability: 0.94, figure: "94%", clock: "Oct 11, 6:23:09 AM"),
            Sample(x: 1791724996000, probability: 0.9599996928, figure: "96%", clock: "Oct 11, 6:23:16 AM"),
            Sample(x: 1791725077000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:24:37 AM"),
            Sample(x: 1791725113000, probability: 0.9699999998, figure: "97%", clock: "Oct 11, 6:25:13 AM"),
            Sample(x: 1791725199000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:26:39 AM"),
            Sample(x: 1791725208000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:26:48 AM"),
            Sample(x: 1791725220000, probability: 0.96, figure: "96%", clock: "Oct 11, 6:27:00 AM"),
            Sample(x: 1791725223000, probability: 0.97, figure: "97%", clock: "Oct 11, 6:27:03 AM"),
            Sample(x: 1791725227000, probability: 0.94, figure: "94%", clock: "Oct 11, 6:27:07 AM"),
            Sample(x: 1791725230000, probability: 0.95, figure: "95%", clock: "Oct 11, 6:27:10 AM"),
            Sample(x: 1791725281000, probability: 0.88, figure: "88%", clock: "Oct 11, 6:28:01 AM"),
            Sample(x: 1791725287000, probability: 0.8699999913, figure: "87%", clock: "Oct 11, 6:28:07 AM"),
            Sample(x: 1791725290000, probability: 0.846, figure: "84.6%", clock: "Oct 11, 6:28:10 AM"),
            Sample(x: 1791725332000, probability: 0.8340046976, figure: "83.4%", clock: "Oct 11, 6:28:52 AM"),
            Sample(x: 1791725346000, probability: 0.8899999858, figure: "89%", clock: "Oct 11, 6:29:06 AM"),
            Sample(x: 1791725359000, probability: 0.8829999249, figure: "88.3%", clock: "Oct 11, 6:29:19 AM"),
            Sample(x: 1791725364000, probability: 0.909, figure: "90.9%", clock: "Oct 11, 6:29:24 AM"),
            Sample(x: 1791725388000, probability: 0.909, figure: "90.9%", clock: "Oct 11, 6:29:48 AM"),
            Sample(x: 1791725442000, probability: 0.934, figure: "93.4%", clock: "Oct 11, 6:30:42 AM"),
            Sample(x: 1791725500000, probability: 0.9311997559, figure: "93.1%", clock: "Oct 11, 6:31:40 AM"),
            Sample(x: 1791725656000, probability: 0.939, figure: "93.9%", clock: "Oct 11, 6:34:16 AM"),
            Sample(x: 1791725704000, probability: 0.9694377261, figure: "96.9%", clock: "Oct 11, 6:35:04 AM"),
            Sample(x: 1791725719000, probability: 0.97, figure: "97%", clock: "Oct 11, 6:35:19 AM"),
            Sample(x: 1791725721000, probability: 0.96, figure: "96%", clock: "Oct 11, 6:35:21 AM"),
            Sample(x: 1791725730000, probability: 0.97, figure: "97%", clock: "Oct 11, 6:35:30 AM"),
            Sample(x: 1791725808000, probability: 0.9869999996, figure: "98.7%", clock: "Oct 11, 6:36:48 AM"),
            Sample(x: 1791725823000, probability: 0.99, figure: "99%", clock: "Oct 11, 6:37:03 AM"),
            Sample(x: 1791725826000, probability: 0.99, figure: "99%", clock: "Oct 11, 6:37:06 AM"),
            Sample(x: 1791725919000, probability: 0.99, figure: "99%", clock: "Oct 11, 6:38:39 AM"),
            Sample(x: 1791725947000, probability: 0.98, figure: "98%", clock: "Oct 11, 6:39:07 AM"),
            Sample(x: 1791726016000, probability: 0.999, figure: "99.9%", clock: "Oct 11, 6:40:16 AM"),
            Sample(x: 1791726019000, probability: 0.999, figure: "99.9%", clock: "Oct 11, 6:40:19 AM"),
            Sample(x: 1791726087000, probability: 0.998, figure: "99.8%", clock: "Oct 11, 6:41:27 AM"),
            Sample(x: 1791726105000, probability: 0.99, figure: "99%", clock: "Oct 11, 6:41:45 AM"),
            Sample(x: 1791726108000, probability: 0.999, figure: "99.9%", clock: "Oct 11, 6:41:48 AM"),
            Sample(x: 1791726193000, probability: 0.99, figure: "99%", clock: "Oct 11, 6:43:13 AM"),
            Sample(x: 1791726229000, probability: 0.991, figure: "99.1%", clock: "Oct 11, 6:43:49 AM"),
            Sample(x: 1791726325000, probability: 0.999, figure: "99.9%", clock: "Oct 11, 6:45:25 AM"),
            Sample(x: 1791726354000, probability: 0.999, figure: "99.9%", clock: "Oct 11, 6:45:54 AM"),
            Sample(x: 1791726366000, probability: 0.999, figure: "99.9%", clock: "Oct 11, 6:46:06 AM"),
        ]),
        Driver(id: "polymarket:5229402:92443082174901362958213182894863948289679800011664028904195269564952495193793", name: "Charles Leclerc", shape: .diamond, beforeIndex: 26, samples: [
            Sample(x: 1791714552000, probability: 0.13, figure: "13%", clock: "Oct 11, 3:29:12 AM"),
            Sample(x: 1791714558000, probability: 0.1409359397, figure: "14.1%", clock: "Oct 11, 3:29:18 AM"),
            Sample(x: 1791714563000, probability: 0.13, figure: "13%", clock: "Oct 11, 3:29:23 AM"),
            Sample(x: 1791714596000, probability: 0.1299999948, figure: "13%", clock: "Oct 11, 3:29:56 AM"),
            Sample(x: 1791714954000, probability: 0.1299999978, figure: "13%", clock: "Oct 11, 3:35:54 AM"),
            Sample(x: 1791715347000, probability: 0.13, figure: "13%", clock: "Oct 11, 3:42:27 AM"),
            Sample(x: 1791715574000, probability: 0.13, figure: "13%", clock: "Oct 11, 3:46:14 AM"),
            Sample(x: 1791716882000, probability: 0.1299999999, figure: "13%", clock: "Oct 11, 4:08:02 AM"),
            Sample(x: 1791717518000, probability: 0.1299999948, figure: "13%", clock: "Oct 11, 4:18:38 AM"),
            Sample(x: 1791717803000, probability: 0.13, figure: "13%", clock: "Oct 11, 4:23:23 AM"),
            Sample(x: 1791717816000, probability: 0.13, figure: "13%", clock: "Oct 11, 4:23:36 AM"),
            Sample(x: 1791718217000, probability: 0.1399999999, figure: "14%", clock: "Oct 11, 4:30:17 AM"),
            Sample(x: 1791718352000, probability: 0.1399999997, figure: "14%", clock: "Oct 11, 4:32:32 AM"),
            Sample(x: 1791718449000, probability: 0.1299999986, figure: "13%", clock: "Oct 11, 4:34:09 AM"),
            Sample(x: 1791718503000, probability: 0.1399999963, figure: "14%", clock: "Oct 11, 4:35:03 AM"),
            Sample(x: 1791718626000, probability: 0.14, figure: "14%", clock: "Oct 11, 4:37:06 AM"),
            Sample(x: 1791719473000, probability: 0.1399999997, figure: "14%", clock: "Oct 11, 4:51:13 AM"),
            Sample(x: 1791719526000, probability: 0.1399999997, figure: "14%", clock: "Oct 11, 4:52:06 AM"),
            Sample(x: 1791719538000, probability: 0.1399999989, figure: "14%", clock: "Oct 11, 4:52:18 AM"),
            Sample(x: 1791719574000, probability: 0.14, figure: "14%", clock: "Oct 11, 4:52:54 AM"),
            Sample(x: 1791719595000, probability: 0.1399999982, figure: "14%", clock: "Oct 11, 4:53:15 AM"),
            Sample(x: 1791719653000, probability: 0.1399999999, figure: "14%", clock: "Oct 11, 4:54:13 AM"),
            Sample(x: 1791719796000, probability: 0.14, figure: "14%", clock: "Oct 11, 4:56:36 AM"),
            Sample(x: 1791719943000, probability: 0.129999999, figure: "13%", clock: "Oct 11, 4:59:03 AM"),
            Sample(x: 1791719955000, probability: 0.1299999948, figure: "13%", clock: "Oct 11, 4:59:15 AM"),
            Sample(x: 1791719968000, probability: 0.1318851082, figure: "13.2%", clock: "Oct 11, 4:59:28 AM"),
            Sample(x: 1791719986000, probability: 0.1399999999, figure: "14%", clock: "Oct 11, 4:59:46 AM"),
            Sample(x: 1791720060000, probability: 0.149999997, figure: "15%", clock: "Oct 11, 5:01:00 AM"),
            Sample(x: 1791720084000, probability: 0.15, figure: "15%", clock: "Oct 11, 5:01:24 AM"),
            Sample(x: 1791720097000, probability: 0.1499999925, figure: "15%", clock: "Oct 11, 5:01:37 AM"),
            Sample(x: 1791720258000, probability: 0.11, figure: "11%", clock: "Oct 11, 5:04:18 AM"),
            Sample(x: 1791720282000, probability: 0.0902074469, figure: "9%", clock: "Oct 11, 5:04:42 AM"),
            Sample(x: 1791720417000, probability: 0.1, figure: "10%", clock: "Oct 11, 5:06:57 AM"),
            Sample(x: 1791720453000, probability: 0.1299999999, figure: "13%", clock: "Oct 11, 5:07:33 AM"),
            Sample(x: 1791720517000, probability: 0.13, figure: "13%", clock: "Oct 11, 5:08:37 AM"),
            Sample(x: 1791720537000, probability: 0.1299999982, figure: "13%", clock: "Oct 11, 5:08:57 AM"),
            Sample(x: 1791720589000, probability: 0.119999999, figure: "12%", clock: "Oct 11, 5:09:49 AM"),
            Sample(x: 1791720801000, probability: 0.109999989, figure: "11%", clock: "Oct 11, 5:13:21 AM"),
            Sample(x: 1791720828000, probability: 0.1037735831, figure: "10.4%", clock: "Oct 11, 5:13:48 AM"),
            Sample(x: 1791720867000, probability: 0.07, figure: "7%", clock: "Oct 11, 5:14:27 AM"),
            Sample(x: 1791720979000, probability: 0.1, figure: "10%", clock: "Oct 11, 5:16:19 AM"),
            Sample(x: 1791720982000, probability: 0.13, figure: "13%", clock: "Oct 11, 5:16:22 AM"),
            Sample(x: 1791721125000, probability: 0.1099999971, figure: "11%", clock: "Oct 11, 5:18:45 AM"),
            Sample(x: 1791721138000, probability: 0.109999989, figure: "11%", clock: "Oct 11, 5:18:58 AM"),
            Sample(x: 1791721215000, probability: 0.13, figure: "13%", clock: "Oct 11, 5:20:15 AM"),
            Sample(x: 1791721234000, probability: 0.12, figure: "12%", clock: "Oct 11, 5:20:34 AM"),
            Sample(x: 1791721297000, probability: 0.1399999979, figure: "14%", clock: "Oct 11, 5:21:37 AM"),
            Sample(x: 1791721333000, probability: 0.13, figure: "13%", clock: "Oct 11, 5:22:13 AM"),
            Sample(x: 1791721366000, probability: 0.1395812561, figure: "14%", clock: "Oct 11, 5:22:46 AM"),
            Sample(x: 1791721446000, probability: 0.13, figure: "13%", clock: "Oct 11, 5:24:06 AM"),
            Sample(x: 1791721683000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:28:03 AM"),
            Sample(x: 1791721734000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:28:54 AM"),
            Sample(x: 1791722200000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:36:40 AM"),
            Sample(x: 1791722317000, probability: 0.0748051948, figure: "7.5%", clock: "Oct 11, 5:38:37 AM"),
            Sample(x: 1791722386000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:39:46 AM"),
            Sample(x: 1791722524000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:42:04 AM"),
            Sample(x: 1791722538000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:42:18 AM"),
            Sample(x: 1791722565000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:42:45 AM"),
            Sample(x: 1791722830000, probability: 0.0699999998, figure: "7%", clock: "Oct 11, 5:47:10 AM"),
            Sample(x: 1791722853000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:47:33 AM"),
            Sample(x: 1791723022000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:50:22 AM"),
            Sample(x: 1791723054000, probability: 0.0434933397, figure: "4.3%", clock: "Oct 11, 5:50:54 AM"),
            Sample(x: 1791723105000, probability: 0.07, figure: "7%", clock: "Oct 11, 5:51:45 AM"),
            Sample(x: 1791723135000, probability: 0.0599999988, figure: "6%", clock: "Oct 11, 5:52:15 AM"),
            Sample(x: 1791723210000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:53:30 AM"),
            Sample(x: 1791723388000, probability: 0.07, figure: "7%", clock: "Oct 11, 5:56:28 AM"),
            Sample(x: 1791723423000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:57:03 AM"),
            Sample(x: 1791723448000, probability: 0.0358142857, figure: "3.6%", clock: "Oct 11, 5:57:28 AM"),
            Sample(x: 1791723799000, probability: 0.05, figure: "5%", clock: "Oct 11, 6:03:19 AM"),
            Sample(x: 1791724011000, probability: 0.051, figure: "5.1%", clock: "Oct 11, 6:06:51 AM"),
            Sample(x: 1791724174000, probability: 0.0610323177, figure: "6.1%", clock: "Oct 11, 6:09:34 AM"),
            Sample(x: 1791724306000, probability: 0.065764023, figure: "6.6%", clock: "Oct 11, 6:11:46 AM"),
            Sample(x: 1791724393000, probability: 0.0899792875, figure: "9%", clock: "Oct 11, 6:13:13 AM"),
            Sample(x: 1791724536000, probability: 0.1096866094, figure: "11%", clock: "Oct 11, 6:15:36 AM"),
            Sample(x: 1791724663000, probability: 0.0849999992, figure: "8.5%", clock: "Oct 11, 6:17:43 AM"),
            Sample(x: 1791724765000, probability: 0.0829999984, figure: "8.3%", clock: "Oct 11, 6:19:25 AM"),
            Sample(x: 1791724828000, probability: 0.0829999984, figure: "8.3%", clock: "Oct 11, 6:20:28 AM"),
            Sample(x: 1791724882000, probability: 0.0885190759, figure: "8.9%", clock: "Oct 11, 6:21:22 AM"),
            Sample(x: 1791725152000, probability: 0.0689282371, figure: "6.9%", clock: "Oct 11, 6:25:52 AM"),
            Sample(x: 1791725236000, probability: 0.0951829787, figure: "9.5%", clock: "Oct 11, 6:27:16 AM"),
            Sample(x: 1791725254000, probability: 0.1018333333, figure: "10.2%", clock: "Oct 11, 6:27:34 AM"),
            Sample(x: 1791725271000, probability: 0.12, figure: "12%", clock: "Oct 11, 6:27:51 AM"),
            Sample(x: 1791725301000, probability: 0.1368448147, figure: "13.7%", clock: "Oct 11, 6:28:21 AM"),
            Sample(x: 1791725302000, probability: 0.139, figure: "13.9%", clock: "Oct 11, 6:28:22 AM"),
            Sample(x: 1791725304000, probability: 0.1397730953, figure: "14%", clock: "Oct 11, 6:28:24 AM"),
            Sample(x: 1791725338000, probability: 0.09, figure: "9%", clock: "Oct 11, 6:28:58 AM"),
            Sample(x: 1791725341000, probability: 0.081, figure: "8.1%", clock: "Oct 11, 6:29:01 AM"),
            Sample(x: 1791725365000, probability: 0.1199999976, figure: "12%", clock: "Oct 11, 6:29:25 AM"),
            Sample(x: 1791725412000, probability: 0.1612595359, figure: "16.1%", clock: "Oct 11, 6:30:12 AM"),
            Sample(x: 1791725491000, probability: 0.106999993, figure: "10.7%", clock: "Oct 11, 6:31:31 AM"),
            Sample(x: 1791725506000, probability: 0.1070877483, figure: "10.7%", clock: "Oct 11, 6:31:46 AM"),
            Sample(x: 1791725511000, probability: 0.109999989, figure: "11%", clock: "Oct 11, 6:31:51 AM"),
            Sample(x: 1791725541000, probability: 0.0859770372, figure: "8.6%", clock: "Oct 11, 6:32:21 AM"),
            Sample(x: 1791725640000, probability: 0.0954329595, figure: "9.5%", clock: "Oct 11, 6:34:00 AM"),
            Sample(x: 1791725653000, probability: 0.053, figure: "5.3%", clock: "Oct 11, 6:34:13 AM"),
            Sample(x: 1791725692000, probability: 0.031, figure: "3.1%", clock: "Oct 11, 6:34:52 AM"),
            Sample(x: 1791725763000, probability: 0.02, figure: "2%", clock: "Oct 11, 6:36:03 AM"),
            Sample(x: 1791725794000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:36:34 AM"),
            Sample(x: 1791725854000, probability: 0.0157635468, figure: "1.6%", clock: "Oct 11, 6:37:34 AM"),
            Sample(x: 1791725970000, probability: 0.0015100306, figure: "0.2%", clock: "Oct 11, 6:39:30 AM"),
            Sample(x: 1791726033000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:40:33 AM"),
            Sample(x: 1791726058000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:40:58 AM"),
            Sample(x: 1791726225000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:43:45 AM"),
        ]),
        Driver(id: "polymarket:5229411:9518453683994039663103190001640433279731056992400699084747973794695685716810", name: "Lewis Hamilton", shape: .square, beforeIndex: 40, samples: [
            Sample(x: 1791713070000, probability: 0.1399999832, figure: "14%", clock: "Oct 11, 3:04:30 AM"),
            Sample(x: 1791713109000, probability: 0.1417635384, figure: "14.2%", clock: "Oct 11, 3:05:09 AM"),
            Sample(x: 1791713406000, probability: 0.1399999965, figure: "14%", clock: "Oct 11, 3:10:06 AM"),
            Sample(x: 1791713873000, probability: 0.1499999986, figure: "15%", clock: "Oct 11, 3:17:53 AM"),
            Sample(x: 1791714099000, probability: 0.15, figure: "15%", clock: "Oct 11, 3:21:39 AM"),
            Sample(x: 1791714552000, probability: 0.15, figure: "15%", clock: "Oct 11, 3:29:12 AM"),
            Sample(x: 1791714588000, probability: 0.149999997, figure: "15%", clock: "Oct 11, 3:29:48 AM"),
            Sample(x: 1791714590000, probability: 0.1499999925, figure: "15%", clock: "Oct 11, 3:29:50 AM"),
            Sample(x: 1791714944000, probability: 0.15, figure: "15%", clock: "Oct 11, 3:35:44 AM"),
            Sample(x: 1791715034000, probability: 0.1499999925, figure: "15%", clock: "Oct 11, 3:37:14 AM"),
            Sample(x: 1791715359000, probability: 0.1499999993, figure: "15%", clock: "Oct 11, 3:42:39 AM"),
            Sample(x: 1791715809000, probability: 0.15, figure: "15%", clock: "Oct 11, 3:50:09 AM"),
            Sample(x: 1791715994000, probability: 0.1499999958, figure: "15%", clock: "Oct 11, 3:53:14 AM"),
            Sample(x: 1791716742000, probability: 0.1399999991, figure: "14%", clock: "Oct 11, 4:05:42 AM"),
            Sample(x: 1791717063000, probability: 0.1499999993, figure: "15%", clock: "Oct 11, 4:11:03 AM"),
            Sample(x: 1791717159000, probability: 0.1499999994, figure: "15%", clock: "Oct 11, 4:12:39 AM"),
            Sample(x: 1791717377000, probability: 0.1499999993, figure: "15%", clock: "Oct 11, 4:16:17 AM"),
            Sample(x: 1791717524000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:18:44 AM"),
            Sample(x: 1791717759000, probability: 0.149999997, figure: "15%", clock: "Oct 11, 4:22:39 AM"),
            Sample(x: 1791717843000, probability: 0.1499999997, figure: "15%", clock: "Oct 11, 4:24:03 AM"),
            Sample(x: 1791718017000, probability: 0.15, figure: "15%", clock: "Oct 11, 4:26:57 AM"),
            Sample(x: 1791718224000, probability: 0.15, figure: "15%", clock: "Oct 11, 4:30:24 AM"),
            Sample(x: 1791718364000, probability: 0.1504749365, figure: "15%", clock: "Oct 11, 4:32:44 AM"),
            Sample(x: 1791718457000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:34:17 AM"),
            Sample(x: 1791718569000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:36:09 AM"),
            Sample(x: 1791718757000, probability: 0.15, figure: "15%", clock: "Oct 11, 4:39:17 AM"),
            Sample(x: 1791718769000, probability: 0.1501656515, figure: "15%", clock: "Oct 11, 4:39:29 AM"),
            Sample(x: 1791719237000, probability: 0.15, figure: "15%", clock: "Oct 11, 4:47:17 AM"),
            Sample(x: 1791719382000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:49:42 AM"),
            Sample(x: 1791719464000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:51:04 AM"),
            Sample(x: 1791719650000, probability: 0.15, figure: "15%", clock: "Oct 11, 4:54:10 AM"),
            Sample(x: 1791719685000, probability: 0.1499999993, figure: "15%", clock: "Oct 11, 4:54:45 AM"),
            Sample(x: 1791719698000, probability: 0.14, figure: "14%", clock: "Oct 11, 4:54:58 AM"),
            Sample(x: 1791719709000, probability: 0.14, figure: "14%", clock: "Oct 11, 4:55:09 AM"),
            Sample(x: 1791719713000, probability: 0.14, figure: "14%", clock: "Oct 11, 4:55:13 AM"),
            Sample(x: 1791719731000, probability: 0.1499999925, figure: "15%", clock: "Oct 11, 4:55:31 AM"),
            Sample(x: 1791719776000, probability: 0.1556967368, figure: "15.6%", clock: "Oct 11, 4:56:16 AM"),
            Sample(x: 1791719856000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:57:36 AM"),
            Sample(x: 1791719887000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:58:07 AM"),
            Sample(x: 1791719941000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:59:01 AM"),
            Sample(x: 1791719959000, probability: 0.16, figure: "16%", clock: "Oct 11, 4:59:19 AM"),
            Sample(x: 1791720039000, probability: 0.1831325281, figure: "18.3%", clock: "Oct 11, 5:00:39 AM"),
            Sample(x: 1791720052000, probability: 0.1899999962, figure: "19%", clock: "Oct 11, 5:00:52 AM"),
            Sample(x: 1791720055000, probability: 0.1899999998, figure: "19%", clock: "Oct 11, 5:00:55 AM"),
            Sample(x: 1791720112000, probability: 0.19, figure: "19%", clock: "Oct 11, 5:01:52 AM"),
            Sample(x: 1791720159000, probability: 0.1899999962, figure: "19%", clock: "Oct 11, 5:02:39 AM"),
            Sample(x: 1791720165000, probability: 0.1799999856, figure: "18%", clock: "Oct 11, 5:02:45 AM"),
            Sample(x: 1791720186000, probability: 0.1799999856, figure: "18%", clock: "Oct 11, 5:03:06 AM"),
            Sample(x: 1791720210000, probability: 0.1799999988, figure: "18%", clock: "Oct 11, 5:03:30 AM"),
            Sample(x: 1791720211000, probability: 0.1799999999, figure: "18%", clock: "Oct 11, 5:03:31 AM"),
            Sample(x: 1791720252000, probability: 0.1799999937, figure: "18%", clock: "Oct 11, 5:04:12 AM"),
            Sample(x: 1791720279000, probability: 0.1699999983, figure: "17%", clock: "Oct 11, 5:04:39 AM"),
            Sample(x: 1791720382000, probability: 0.1199999904, figure: "12%", clock: "Oct 11, 5:06:22 AM"),
            Sample(x: 1791720420000, probability: 0.11, figure: "11%", clock: "Oct 11, 5:07:00 AM"),
            Sample(x: 1791720430000, probability: 0.12, figure: "12%", clock: "Oct 11, 5:07:10 AM"),
            Sample(x: 1791720436000, probability: 0.14, figure: "14%", clock: "Oct 11, 5:07:16 AM"),
            Sample(x: 1791720496000, probability: 0.139999993, figure: "14%", clock: "Oct 11, 5:08:16 AM"),
            Sample(x: 1791720607000, probability: 0.14, figure: "14%", clock: "Oct 11, 5:10:07 AM"),
            Sample(x: 1791720645000, probability: 0.14, figure: "14%", clock: "Oct 11, 5:10:45 AM"),
            Sample(x: 1791720667000, probability: 0.14, figure: "14%", clock: "Oct 11, 5:11:07 AM"),
            Sample(x: 1791720712000, probability: 0.1499999993, figure: "15%", clock: "Oct 11, 5:11:52 AM"),
            Sample(x: 1791720717000, probability: 0.1499999994, figure: "15%", clock: "Oct 11, 5:11:57 AM"),
            Sample(x: 1791720759000, probability: 0.15, figure: "15%", clock: "Oct 11, 5:12:39 AM"),
            Sample(x: 1791720820000, probability: 0.1699999937, figure: "17%", clock: "Oct 11, 5:13:40 AM"),
            Sample(x: 1791721113000, probability: 0.1699999983, figure: "17%", clock: "Oct 11, 5:18:33 AM"),
            Sample(x: 1791721125000, probability: 0.1699999983, figure: "17%", clock: "Oct 11, 5:18:45 AM"),
            Sample(x: 1791721263000, probability: 0.136109, figure: "13.6%", clock: "Oct 11, 5:21:03 AM"),
            Sample(x: 1791721362000, probability: 0.1399999956, figure: "14%", clock: "Oct 11, 5:22:42 AM"),
            Sample(x: 1791721419000, probability: 0.1176470588, figure: "11.8%", clock: "Oct 11, 5:23:39 AM"),
            Sample(x: 1791721444000, probability: 0.0441666667, figure: "4.4%", clock: "Oct 11, 5:24:04 AM"),
            Sample(x: 1791721446000, probability: 0.0726080337, figure: "7.3%", clock: "Oct 11, 5:24:06 AM"),
            Sample(x: 1791721462000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:24:22 AM"),
            Sample(x: 1791721470000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:24:30 AM"),
            Sample(x: 1791721480000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:24:40 AM"),
            Sample(x: 1791721524000, probability: 0.12, figure: "12%", clock: "Oct 11, 5:25:24 AM"),
            Sample(x: 1791721593000, probability: 0.1399999998, figure: "14%", clock: "Oct 11, 5:26:33 AM"),
            Sample(x: 1791721774000, probability: 0.11, figure: "11%", clock: "Oct 11, 5:29:34 AM"),
            Sample(x: 1791721855000, probability: 0.09, figure: "9%", clock: "Oct 11, 5:30:55 AM"),
            Sample(x: 1791721870000, probability: 0.09, figure: "9%", clock: "Oct 11, 5:31:10 AM"),
            Sample(x: 1791722047000, probability: 0.069999999, figure: "7%", clock: "Oct 11, 5:34:07 AM"),
            Sample(x: 1791722128000, probability: 0.0599999999, figure: "6%", clock: "Oct 11, 5:35:28 AM"),
            Sample(x: 1791722145000, probability: 0.07, figure: "7%", clock: "Oct 11, 5:35:45 AM"),
            Sample(x: 1791722218000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:36:58 AM"),
            Sample(x: 1791722277000, probability: 0.07925, figure: "7.9%", clock: "Oct 11, 5:37:57 AM"),
            Sample(x: 1791722299000, probability: 0.0332989691, figure: "3.3%", clock: "Oct 11, 5:38:19 AM"),
            Sample(x: 1791722317000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:38:37 AM"),
            Sample(x: 1791722331000, probability: 0.0699999978, figure: "7%", clock: "Oct 11, 5:38:51 AM"),
            Sample(x: 1791722335000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:38:55 AM"),
            Sample(x: 1791722487000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:41:27 AM"),
            Sample(x: 1791722541000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:42:21 AM"),
            Sample(x: 1791722542000, probability: 0.07, figure: "7%", clock: "Oct 11, 5:42:22 AM"),
            Sample(x: 1791722544000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:42:24 AM"),
            Sample(x: 1791722571000, probability: 0.07, figure: "7%", clock: "Oct 11, 5:42:51 AM"),
            Sample(x: 1791722640000, probability: 0.0882352936, figure: "8.8%", clock: "Oct 11, 5:44:00 AM"),
            Sample(x: 1791722680000, probability: 0.08, figure: "8%", clock: "Oct 11, 5:44:40 AM"),
            Sample(x: 1791722805000, probability: 0.0389525515, figure: "3.9%", clock: "Oct 11, 5:46:45 AM"),
            Sample(x: 1791722842000, probability: 0.0599999999, figure: "6%", clock: "Oct 11, 5:47:22 AM"),
            Sample(x: 1791722884000, probability: 0.06, figure: "6%", clock: "Oct 11, 5:48:04 AM"),
            Sample(x: 1791723090000, probability: 0.0433333333, figure: "4.3%", clock: "Oct 11, 5:51:30 AM"),
            Sample(x: 1791723124000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:52:04 AM"),
            Sample(x: 1791723147000, probability: 0.05, figure: "5%", clock: "Oct 11, 5:52:27 AM"),
            Sample(x: 1791723211000, probability: 0.0583082075, figure: "5.8%", clock: "Oct 11, 5:53:31 AM"),
            Sample(x: 1791723483000, probability: 0.013, figure: "1.3%", clock: "Oct 11, 5:58:03 AM"),
            Sample(x: 1791723580000, probability: 0.033, figure: "3.3%", clock: "Oct 11, 5:59:40 AM"),
            Sample(x: 1791724009000, probability: 0.0099585949, figure: "1%", clock: "Oct 11, 6:06:49 AM"),
            Sample(x: 1791724059000, probability: 0.0052, figure: "0.5%", clock: "Oct 11, 6:07:39 AM"),
            Sample(x: 1791724060000, probability: 0.00992, figure: "1%", clock: "Oct 11, 6:07:40 AM"),
            Sample(x: 1791724069000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:07:49 AM"),
            Sample(x: 1791724089000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:08:09 AM"),
            Sample(x: 1791724104000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:08:24 AM"),
            Sample(x: 1791724266000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:11:06 AM"),
            Sample(x: 1791724272000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:11:12 AM"),
            Sample(x: 1791724365000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:12:45 AM"),
            Sample(x: 1791724396000, probability: 0.01, figure: "1%", clock: "Oct 11, 6:13:16 AM"),
            Sample(x: 1791724464000, probability: 0.0057220217, figure: "0.6%", clock: "Oct 11, 6:14:24 AM"),
            Sample(x: 1791724549000, probability: 0.005, figure: "0.5%", clock: "Oct 11, 6:15:49 AM"),
            Sample(x: 1791724623000, probability: 0.005, figure: "0.5%", clock: "Oct 11, 6:17:03 AM"),
            Sample(x: 1791724686000, probability: 0.0027849631, figure: "0.3%", clock: "Oct 11, 6:18:06 AM"),
            Sample(x: 1791724780000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:19:40 AM"),
            Sample(x: 1791724986000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:23:06 AM"),
            Sample(x: 1791725008000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:23:28 AM"),
            Sample(x: 1791725124000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:25:24 AM"),
            Sample(x: 1791725224000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:27:04 AM"),
            Sample(x: 1791725245000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:27:25 AM"),
            Sample(x: 1791725274000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:27:54 AM"),
            Sample(x: 1791725293000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:28:13 AM"),
            Sample(x: 1791725403000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:30:03 AM"),
            Sample(x: 1791725509000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:31:49 AM"),
            Sample(x: 1791725548000, probability: 0.002, figure: "0.2%", clock: "Oct 11, 6:32:28 AM"),
            Sample(x: 1791725694000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:34:54 AM"),
            Sample(x: 1791725712000, probability: 0.001, figure: "0.1%", clock: "Oct 11, 6:35:12 AM"),
        ]),
    ]

    private static let moments: [Moment] = [
        Moment(stage: -1, domain: FieldHistoryDomain10868(lower: 1791712800000, upper: 1791719999999), caption: "Final 2 hours before the start", runs: [[[0,1,2],[3],[4],[5,6,7,8,9],[10,11],[12,13],[14],[15,16],[17],[18,19,20,21,22,23,24,25,26,27,28],[29],[30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46]],[[0,1,2,3],[4],[5,6],[7],[8,9,10],[11,12,13,14,15],[16,17,18,19,20,21,22,23,24,25,26]],[[0,1,2],[3,4],[5,6,7],[8,9],[10],[11,12],[13],[14,15,16,17,18,19,20,21,22,23,24,25,26],[27,28,29,30,31,32,33,34,35,36,37,38,39,40]]], headlineIndexes: [46, 26, 40], expectedCounts: [47,27,41], expectedLineSizes: [[3,5,2,2,2,11,17],[4,2,3,5,11],[3,2,3,2,2,13,14]]),
        Moment(stage: 0, domain: FieldHistoryDomain10868(lower: 1791720000000, upper: 1791724849000), caption: "Race start to lap 46 report", runs: [[[47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169]],[[27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51],[52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67],[68,69,70,71,72,73,74,75,76]],[[41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103],[104,105,106,107,108,109,110,111,112,113,114,115,116,117,118]]], headlineIndexes: [169, 76, 118], expectedCounts: [123,50,78], expectedLineSizes: [[123],[25,16,9],[63,15]]),
        Moment(stage: 1, domain: FieldHistoryDomain10868(lower: 1791720000000, upper: 1791725426000), caption: "Race start to lap 52 report", runs: [[[47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193]],[[27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51],[52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67],[68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88]],[[41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103],[104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126]]], headlineIndexes: [193, 88, 126], expectedCounts: [147,62,86], expectedLineSizes: [[147],[25,16,21],[63,23]]),
        Moment(stage: 2, domain: FieldHistoryDomain10868(lower: 1791720000000, upper: 1791726053000), caption: "Race start to lap 58 report", runs: [[[47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207]],[[27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51],[52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67],[68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100]],[[41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103],[104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130]]], headlineIndexes: [207, 100, nil], expectedCounts: [161,74,90], expectedLineSizes: [[161],[25,16,33],[63,27]]),
        Moment(stage: 3, domain: FieldHistoryDomain10868(lower: 1791720000000, upper: 1791726378000), caption: "Race start to last-lap report", runs: [[[47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215]],[[27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51],[52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67],[68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102]],[[41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103],[104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130]]], headlineIndexes: [nil, nil, nil], expectedCounts: [169,76,90], expectedLineSizes: [[169],[25,16,35],[63,27]]),
    ]

    private static let reportGuides: [FieldHistoryGuide10868] = [
        FieldHistoryGuide10868(id: "report:0", x: 1791724849000, label: "Lap 46 report"),
        FieldHistoryGuide10868(id: "report:1", x: 1791725426000, label: "Lap 52 report"),
        FieldHistoryGuide10868(id: "report:2", x: 1791726053000, label: "Lap 58 report"),
        FieldHistoryGuide10868(id: "report:3", x: 1791726378000, label: "Lap 62 report"),
    ]


    private static func series(_ moment: Moment, index: Int,
                               recorded: FieldHistoryReading10868? = nil) -> FieldHistorySeries10868 {
        let driver = drivers[index]
        let baseline = driver.samples[driver.beforeIndex]
        let before: FieldHistoryReading10868 = moment.stage == -1
            ? driver.reading(driver.beforeIndex)
            : .independent(figure: baseline.figure, provenance: driver.provenance(driver.beforeIndex))
        let admittedRecorded: FieldHistoryReading10868
        if let recorded {
            admittedRecorded = recorded
        } else if moment.stage == -1 {
            admittedRecorded = .absent(words: "Before the start")
        } else if moment.stage == 3 {
            admittedRecorded = .absent(words: "No current probability after the final")
        } else if let point = moment.headlineIndexes[index] {
            admittedRecorded = driver.reading(point)
        } else {
            admittedRecorded = .absent(words: "No recent probability")
        }
        let runs = moment.runs[index].enumerated().map { runIndex, indexes in
            FieldHistoryRun10868(id: "constructed-run:\(driver.id):\(moment.stage):\(runIndex)", points: indexes.map { i in
                let sample = driver.samples[i]
                return FieldHistoryPoint10868(id: driver.pointID(i), x: sample.x, probability: sample.probability,
                                              style: moment.stage == -1 ? .hollow : .filled)
            })
        }
        return FieldHistorySeries10868(
            id: driver.id, name: driver.name, shape: driver.shape, tint: [Color.blue, Color.orange, Color.pink][index],
            runs: runs, links: [], labelPointID: nil, before: before, recorded: admittedRecorded,
            absentWords: "No retained history for this driver", choose: nil)
    }

    private static func input(_ moment: Moment, series: [FieldHistorySeries10868]? = nil,
                              inspection: FieldHistoryInspection10868? = nil,
                              readout: FieldHistoryReadoutIntent10868? = nil,
                              selection: FieldHistoryOriginalSelection10868 = .series(id: RacingSharedHistoryContract10868Tests.drivers[0].id, missingWords: "Driver unavailable")) -> FieldHistoryInput10868 {
        let intent: FieldHistoryReadoutIntent10868 = moment.stage == -1
            ? .singleBefore(label: "Pre-race win")
            : moment.stage == 3
                ? .beforeAndInspected(beforeLabel: "Pre-race win", inspectedLabel: "Historical trade")
                : .beforeAndRecorded(beforeLabel: "Pre-race win", recordedLabel: "Recorded win")
        return FieldHistoryInput10868(
            title: "Win probability", caption: moment.caption,
            series: series ?? drivers.indices.map { Self.series(moment, index: $0) }, selection: selection,
            domain: moment.domain, ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [], guides: reportGuides, breaks: [], readout: readout ?? intent,
            markKey: FieldHistoryMarkKey10868(hollow: "Pre-race trade", filled: "Recorded trade"),
            comparisonExplanation: nil,
            notes: ["Historical trades have independent clocks. Lap reports are publication times, not exact lap crossings or finish times."],
            summary: "Three drivers on the same time axis; circle Verstappen, diamond Leclerc, square Hamilton.",
            plotHeight: 240, unboundReadingWords: "Not recorded at this selected observation",
            plotUnavailableWords: "History unavailable", windows: nil, scale: nil, moreOriginals: nil,
            details: nil, expand: nil, inspect: nil, previous: nil, next: nil, inspection: inspection,
            layout: .focused)
    }

    private static func inspection(_ driver: Driver, sample index: Int) -> FieldHistoryInspection10868 {
        FieldHistoryInspection10868(
            x: driver.samples[index].x, caption: "Historical trade · \(driver.provenance(index))",
            selections: [driver.id: .point(id: driver.pointID(index), spoken: "\(driver.name): \(driver.samples[index].figure), \(driver.provenance(index))")],
            choices: [], choicePresentation: .slider(label: "Recorded race time"),
            note: "Exact own retained observation; never the nearest driver's trade")
    }

    func testTheFiveRealWindowsKeepEveryOwnObservationShapeAndExplicitRun() {
        XCTAssertEqual(Self.drivers.map { $0.samples.count }, [216, 103, 131])
        XCTAssertEqual(Self.moments.map { $0.expectedCounts }, [[47, 27, 41], [123, 50, 78], [147, 62, 86], [161, 74, 90], [169, 76, 90]])
        for moment in Self.moments {
            let input = Self.input(moment)
            XCTAssertEqual(input.series.map(\.name), ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])
            XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond, .square])
            XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.marks($0, in: input).count }, moment.expectedCounts)
            for (index, series) in input.series.enumerated() {
                let driver = Self.drivers[index]
                let marks = FieldHistoryGeometry10868.marks(series, in: input)
                let expected = moment.runs[index].flatMap { $0 }.map { driver.samples[$0] }
                XCTAssertEqual(marks.map(\.x), expected.map(\.x))
                XCTAssertEqual(marks.map(\.probability), expected.map(\.probability))
                XCTAssertEqual(Set(marks.map(\.id)).count, marks.count)
                XCTAssertTrue(marks.allSatisfy { $0.style == (moment.stage == -1 ? .hollow : .filled) })
                XCTAssertEqual(FieldHistoryGeometry10868.lines(series, in: input).map(\.count), moment.expectedLineSizes[index])
                XCTAssertTrue(series.links.isEmpty)
            }
        }
        // The retained pre-race gaps are real explicit run boundaries, not synthetic connecting segments.
        XCTAssertEqual(Self.moments[0].runs.map(\.count), [12, 7, 9])
        let pre = Self.input(Self.moments[0])
        for series in pre.series {
            for line in FieldHistoryGeometry10868.lines(series, in: pre) {
                XCTAssertTrue(series.runs.contains { run in line.allSatisfy { point in run.points.contains(point) } })
            }
        }
    }

    func testBeforeShowsOneOwnBaselineAndLaterWindowsKeepThatSameOffPlotReminder() {
        let figures = ["65%", "14%", "16%"]
        for moment in Self.moments {
            let input = Self.input(moment)
            for (index, series) in input.series.enumerated() {
                let driver = Self.drivers[index]
                let slots = FieldHistoryGeometry10868.readoutSlots(series, in: input)
                XCTAssertEqual(slots[0].label, "Pre-race win")
                XCTAssertEqual(slots[0].display, .figure(figures[index], provenance: driver.provenance(driver.beforeIndex)))
                XCTAssertEqual(slots.count, moment.stage == -1 ? 1 : 2)
                let baselineX = driver.samples[driver.beforeIndex].x
                if moment.stage != -1 {
                    XCTAssertLessThan(baselineX, input.domain.lower)
                    XCTAssertFalse(FieldHistoryGeometry10868.marks(series, in: input).contains { $0.x == baselineX })
                }
            }
        }
    }

    func testLapReportGuidesNeverMoveTheIndependentlyTimedTradesOntoTheirClock() {
        let expectedGuides = [0, 1, 2, 3, 4]
        for (index, moment) in Self.moments.enumerated() {
            let input = Self.input(moment)
            XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(input).count, expectedGuides[index])
            XCTAssertTrue(FieldHistoryGeometry10868.placedGuides(input).allSatisfy { $0.label.contains("report") })
        }
        let lap46 = Self.input(Self.moments[1])
        let ownQuotes: [Double] = [1_791_724_798_000, 1_791_724_828_000, 1_791_724_780_000]
        let report: Double = 1_791_724_849_000
        XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(lap46).first?.x, report)
        let rect = CGRect(x: 0, y: 0, width: 100, height: 100)
        for (index, series) in lap46.series.enumerated() {
            guard let point = FieldHistoryGeometry10868.marks(series, in: lap46).last else { XCTFail(series.name); continue }
            XCTAssertEqual(point.x, ownQuotes[index])
            XCTAssertLessThan(point.x, report)
            let position = FieldHistoryGeometry10868.position(point, in: lap46, rect: rect)
            XCTAssertLessThan(position.x, FieldHistoryGeometry10868.xPosition(report, domain: lap46.domain, in: rect))
        }
        XCTAssertEqual(FieldHistoryGeometry10868.marks(lap46.series[0], in: lap46).last?.probability, 0.95)
        guard let leaderPoint = FieldHistoryGeometry10868.marks(lap46.series[0], in: lap46).last else { return XCTFail("Leader history") }
        XCTAssertEqual(FieldHistoryGeometry10868.position(leaderPoint, in: lap46, rect: rect).y, 5, accuracy: 1e-8)
    }

    func testHamiltonHasNoCurrentChanceAtLap58ButHisExactHistoricalTradeRemainsInspectable() {
        let moment = Self.moments[3]
        let input = Self.input(moment)
        let driver = Self.drivers[2]
        let series = input.series[2]
        XCTAssertNil(moment.headlineIndexes[2])
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: input)[1].display, .words("No recent probability"))
        XCTAssertEqual(FieldHistoryGeometry10868.marks(series, in: input).count, 90)
        guard let last = moment.runs[2].last?.last else { return XCTFail("Hamilton history") }
        XCTAssertEqual(driver.samples[last].x, 1_791_725_712_000)
        XCTAssertEqual(driver.samples[last].probability, 0.001)
        var shown = input.series
        shown[2] = Self.series(moment, index: 2, recorded: driver.reading(last))
        let inspected = Self.input(moment, series: shown, inspection: Self.inspection(driver, sample: last),
                                   readout: .beforeAndInspected(beforeLabel: "Pre-race win", inspectedLabel: "Historical trade"),
                                   selection: .series(id: driver.id, missingWords: "Driver unavailable"))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(shown[2], in: inspected)?.id, driver.pointID(last))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(shown[2], in: inspected).map(\.display), [
            .figure("16%", provenance: driver.provenance(driver.beforeIndex)),
            .figure("0.1%", provenance: driver.provenance(last)),
        ])
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(shown[2], in: inspected)[1].label, "Historical trade")
        XCTAssertEqual(FieldHistoryGeometry10868.marks(shown[2], in: inspected), FieldHistoryGeometry10868.marks(series, in: input))
    }

    func testAHeldOwnObservationSurvivesANewerWindowAndNeverBorrowsAnotherOriginal() {
        let earlier = Self.moments[2], newer = Self.moments[3], driver = Self.drivers[1]
        guard let oldIndex = earlier.headlineIndexes[1] else { return XCTFail("Leclerc lap52 quote") }
        XCTAssertEqual(driver.samples[oldIndex].x, 1_791_725_412_000)
        XCTAssertEqual(driver.samples[oldIndex].figure, "16.1%")
        var series = Self.input(newer).series
        series[1] = Self.series(newer, index: 1, recorded: driver.reading(oldIndex))
        let input = Self.input(newer, series: series, inspection: Self.inspection(driver, sample: oldIndex),
                               readout: .beforeAndInspected(beforeLabel: "Pre-race win", inspectedLabel: "Historical trade"),
                               selection: .series(id: driver.id, missingWords: "Driver unavailable"))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(series[1], in: input)?.x, driver.samples[oldIndex].x)
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series[1], in: input)[1].display,
                       .figure("16.1%", provenance: driver.provenance(oldIndex)))
        if case .original(let selected, let slots) = FieldHistoryGeometry10868.selectedSummary(input) {
            XCTAssertEqual(selected.id, driver.id)
            XCTAssertEqual(slots[1].display, .figure("16.1%", provenance: driver.provenance(oldIndex)))
        } else { XCTFail("Held driver must remain the focused reader summary") }
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series[0], in: input))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series[2], in: input))
        // A mismatched newer reading cannot silently replace the held one.
        let mismatched = Self.input(newer, inspection: Self.inspection(driver, sample: oldIndex),
                                    readout: .beforeAndInspected(beforeLabel: "Pre-race win", inspectedLabel: "Historical trade"))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(mismatched.series[1], in: mismatched)[1].display,
                       .words("Not recorded at this selected observation"))
    }

    func testTheFinalStopsAtTheLastLapReportWithoutAppendingASyntheticWinnerPoint() {
        let moment = Self.moments[4], input = Self.input(Self.moments[4])
        XCTAssertEqual(moment.domain.upper, 1_791_726_378_000)
        XCTAssertEqual(input.caption, "Race start to last-lap report")
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.marks($0, in: input).count }, [169, 76, 90])
        XCTAssertEqual(input.series.compactMap { FieldHistoryGeometry10868.marks($0, in: input).last?.x },
                       [1_791_726_366_000, 1_791_726_225_000, 1_791_725_712_000])
        XCTAssertEqual(input.series.compactMap { FieldHistoryGeometry10868.marks($0, in: input).last?.probability }, [0.999, 0.001, 0.001])
        for series in input.series {
            XCTAssertTrue(FieldHistoryGeometry10868.marks(series, in: input).allSatisfy { $0.x <= moment.domain.upper })
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: input)[1].display,
                           .words("Not recorded at this selected observation"))
        }
        XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(input).last?.label, "Lap 62 report")
    }
}

// MARK: Player-duel game-winner history reuse — PREPARED, NOT_RUN

/// #10868 reuse — the approved player-duel page's main game-winner chart
/// (New York at San Antonio, Game 1, June 3, 2026) drawn by the SAME shared
/// `FieldHistoryGeometry10868` helpers the golf and racing cases above
/// consume. No product code, adapter, loader, formatter or policy is added;
/// everything below is an owner-resolved fixture.
///
/// ARCHIVED raw values come from
/// `shipping-adoption-20261027/PLAYER-DUEL-GAME-HISTORY-RETAINED-CASES.json`
/// (sha256 2c96ec2a…49e478f9), exported by the pinned reference helpers
/// `playerDuelEvidence.ts` / `rugbyMatchEvidence.ts` over `playerDuel.json`
/// (sha256 b77fef58…3a44ae0a). Two real Kalshi game-winner originals:
///   KXNBAGAME-26JUN03NYKSAS-NYK  Knicks  227 around-game minute closes
///   KXNBAGAME-26JUN03NYKSAS-SAS  Spurs   227 around-game minute closes
/// Each trade is (minute-end UTC seconds, probability, volume, exported
/// figure, exported Pacific clock) exactly as retained; no Date is built and
/// nothing is reformatted. The before frame is the packet's first 60 of them.
/// Each before-game reminder (37% / 64%, minute ending Jun 3, 5:29 PM PT) is
/// the last trade strictly before the LISTED start 1780533000 — not actual
/// tipoff — and the two total 101%; nothing is normalized or complemented.
/// The final frame stops at the last real trades, 99% / 1% at 8:16 PM PT,
/// never a synthetic 0% / 100% settlement. The half-payout player originals
/// (KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-*) and their cents never enter
/// this chart. The full captured histories (before 2607 / 2568 points, final
/// 2774 / 2735, 77 / 101 runs) stay in the pinned playerDuel.json and are
/// deliberately NOT reproduced here.
///
/// The early inspection control is CONSTRUCTED: a five-minute domain
/// 1780374960…1780375200 over real early trades (5 Knicks, 4 Spurs). At
/// 1780375080 only the Knicks recorded a trade (37%); the Spurs did not.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// point, run, guide, action and choice id (series ids reuse the real tickers
/// as fixture identities only — production canonical pairing and admission
/// stay Native-owned); the shape and tint assignment; the hollow (before the
/// listed start) / filled (from the listed start) split and its key words;
/// every domain, tick, guide label, caption, note, readout label, provenance
/// and absence string, summary, window, control and inspection choice.
/// Nothing here claims a rendered fit, an interaction, accessibility,
/// full-range rendering or performance, live delivery or a production
/// binding. The actual score, headline and forecast are composed elsewhere
/// and are not chart input.
final class PlayerDuelGameHistoryReuse10868Tests: XCTestCase {
    private struct Trade {
        let at: Double
        let probability: Double
        let volume: Double
        let figure: String
        let clock: String
    }

    private struct Winner {
        let ticker: String
        let name: String
        let shape: FieldHistoryShape10868
        let tint: Color
        let baseline: Trade
        /// The final frame's around-game minute closes; the before frame is its packet prefix.
        let around: [Trade]
        /// The constructed control's real early trades and the packet's own runs over them.
        let early: [Trade]
        let earlyRuns: [[Int]]

        func pointID(_ trade: Trade) -> String { "constructed-point:\(ticker):\(Int(trade.at))" }
        func provenance(_ trade: Trade) -> String { "\(trade.clock) PT · Kalshi minute close" }
        var baselineProvenance: String { "\(baseline.clock) PT · last trade before listed start" }
        func reading(_ trade: Trade) -> FieldHistoryReading10868 {
            .observation(pointID: pointID(trade), figure: trade.figure, provenance: provenance(trade))
        }
    }

    private enum Frame { case before, final, control }

    private static let listedStart: Double = 1_780_533_000
    private static let beforeCount = 60
    private static let excludedValueOriginals = [
        "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30",
        "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8",
    ]
    private static let listedStartGuide = FieldHistoryGuide10868(id: "constructed-guide:listed-start", x: 1_780_533_000,
                                                                 label: "Listed start")
    private static let unboundWords = "No trade at the selected minute"

    // Retained trades from the pinned packet; owner fixture ports only.
    private static let winners: [Winner] = [
        Winner(ticker: "KXNBAGAME-26JUN03NYKSAS-NYK", name: "Knicks", shape: .circle, tint: .blue,
               baseline: Trade(at: 1780532940, probability: 0.37, volume: 72814.64, figure: "37%", clock: "Jun 3, 5:29 PM"),
               around: [
                   Trade(at: 1780529400, probability: 0.37, volume: 32275.41, figure: "37%", clock: "Jun 3, 4:30 PM"),
                   Trade(at: 1780529460, probability: 0.37, volume: 33632.42, figure: "37%", clock: "Jun 3, 4:31 PM"),
                   Trade(at: 1780529520, probability: 0.37, volume: 30144.75, figure: "37%", clock: "Jun 3, 4:32 PM"),
                   Trade(at: 1780529580, probability: 0.37, volume: 16014.97, figure: "37%", clock: "Jun 3, 4:33 PM"),
                   Trade(at: 1780529640, probability: 0.37, volume: 17755.79, figure: "37%", clock: "Jun 3, 4:34 PM"),
                   Trade(at: 1780529700, probability: 0.37, volume: 33491.65, figure: "37%", clock: "Jun 3, 4:35 PM"),
                   Trade(at: 1780529760, probability: 0.37, volume: 55290.73, figure: "37%", clock: "Jun 3, 4:36 PM"),
                   Trade(at: 1780529820, probability: 0.37, volume: 22523.71, figure: "37%", clock: "Jun 3, 4:37 PM"),
                   Trade(at: 1780529880, probability: 0.37, volume: 28434.48, figure: "37%", clock: "Jun 3, 4:38 PM"),
                   Trade(at: 1780529940, probability: 0.37, volume: 20351.76, figure: "37%", clock: "Jun 3, 4:39 PM"),
                   Trade(at: 1780530000, probability: 0.37, volume: 27249.28, figure: "37%", clock: "Jun 3, 4:40 PM"),
                   Trade(at: 1780530060, probability: 0.37, volume: 38147.63, figure: "37%", clock: "Jun 3, 4:41 PM"),
                   Trade(at: 1780530120, probability: 0.37, volume: 20051.55, figure: "37%", clock: "Jun 3, 4:42 PM"),
                   Trade(at: 1780530180, probability: 0.37, volume: 24369.74, figure: "37%", clock: "Jun 3, 4:43 PM"),
                   Trade(at: 1780530240, probability: 0.37, volume: 34381.28, figure: "37%", clock: "Jun 3, 4:44 PM"),
                   Trade(at: 1780530300, probability: 0.37, volume: 40055.47, figure: "37%", clock: "Jun 3, 4:45 PM"),
                   Trade(at: 1780530360, probability: 0.37, volume: 43586.95, figure: "37%", clock: "Jun 3, 4:46 PM"),
                   Trade(at: 1780530420, probability: 0.37, volume: 23278.48, figure: "37%", clock: "Jun 3, 4:47 PM"),
                   Trade(at: 1780530480, probability: 0.37, volume: 36945.94, figure: "37%", clock: "Jun 3, 4:48 PM"),
                   Trade(at: 1780530540, probability: 0.37, volume: 21166.96, figure: "37%", clock: "Jun 3, 4:49 PM"),
                   Trade(at: 1780530600, probability: 0.37, volume: 38540.89, figure: "37%", clock: "Jun 3, 4:50 PM"),
                   Trade(at: 1780530660, probability: 0.37, volume: 20038.33, figure: "37%", clock: "Jun 3, 4:51 PM"),
                   Trade(at: 1780530720, probability: 0.37, volume: 21872.33, figure: "37%", clock: "Jun 3, 4:52 PM"),
                   Trade(at: 1780530780, probability: 0.37, volume: 48370.45, figure: "37%", clock: "Jun 3, 4:53 PM"),
                   Trade(at: 1780530840, probability: 0.37, volume: 47381.43, figure: "37%", clock: "Jun 3, 4:54 PM"),
                   Trade(at: 1780530900, probability: 0.37, volume: 31448.66, figure: "37%", clock: "Jun 3, 4:55 PM"),
                   Trade(at: 1780530960, probability: 0.37, volume: 50726.41, figure: "37%", clock: "Jun 3, 4:56 PM"),
                   Trade(at: 1780531020, probability: 0.37, volume: 36341.59, figure: "37%", clock: "Jun 3, 4:57 PM"),
                   Trade(at: 1780531080, probability: 0.37, volume: 32191.7, figure: "37%", clock: "Jun 3, 4:58 PM"),
                   Trade(at: 1780531140, probability: 0.37, volume: 27589.34, figure: "37%", clock: "Jun 3, 4:59 PM"),
                   Trade(at: 1780531200, probability: 0.37, volume: 41246.69, figure: "37%", clock: "Jun 3, 5:00 PM"),
                   Trade(at: 1780531260, probability: 0.37, volume: 53254.64, figure: "37%", clock: "Jun 3, 5:01 PM"),
                   Trade(at: 1780531320, probability: 0.37, volume: 57689.29, figure: "37%", clock: "Jun 3, 5:02 PM"),
                   Trade(at: 1780531380, probability: 0.37, volume: 53766.42, figure: "37%", clock: "Jun 3, 5:03 PM"),
                   Trade(at: 1780531440, probability: 0.37, volume: 56534.21, figure: "37%", clock: "Jun 3, 5:04 PM"),
                   Trade(at: 1780531500, probability: 0.37, volume: 60709.13, figure: "37%", clock: "Jun 3, 5:05 PM"),
                   Trade(at: 1780531560, probability: 0.37, volume: 54558.64, figure: "37%", clock: "Jun 3, 5:06 PM"),
                   Trade(at: 1780531620, probability: 0.37, volume: 52620.06, figure: "37%", clock: "Jun 3, 5:07 PM"),
                   Trade(at: 1780531680, probability: 0.37, volume: 99138.16, figure: "37%", clock: "Jun 3, 5:08 PM"),
                   Trade(at: 1780531740, probability: 0.37, volume: 29978.89, figure: "37%", clock: "Jun 3, 5:09 PM"),
                   Trade(at: 1780531800, probability: 0.37, volume: 37301.41, figure: "37%", clock: "Jun 3, 5:10 PM"),
                   Trade(at: 1780531860, probability: 0.37, volume: 61643.47, figure: "37%", clock: "Jun 3, 5:11 PM"),
                   Trade(at: 1780531920, probability: 0.37, volume: 36946.01, figure: "37%", clock: "Jun 3, 5:12 PM"),
                   Trade(at: 1780531980, probability: 0.37, volume: 44138.02, figure: "37%", clock: "Jun 3, 5:13 PM"),
                   Trade(at: 1780532040, probability: 0.37, volume: 46153.78, figure: "37%", clock: "Jun 3, 5:14 PM"),
                   Trade(at: 1780532100, probability: 0.37, volume: 40769.74, figure: "37%", clock: "Jun 3, 5:15 PM"),
                   Trade(at: 1780532160, probability: 0.37, volume: 81671.74, figure: "37%", clock: "Jun 3, 5:16 PM"),
                   Trade(at: 1780532220, probability: 0.37, volume: 64873.37, figure: "37%", clock: "Jun 3, 5:17 PM"),
                   Trade(at: 1780532280, probability: 0.37, volume: 32382.71, figure: "37%", clock: "Jun 3, 5:18 PM"),
                   Trade(at: 1780532340, probability: 0.37, volume: 57475.58, figure: "37%", clock: "Jun 3, 5:19 PM"),
                   Trade(at: 1780532400, probability: 0.37, volume: 62065.16, figure: "37%", clock: "Jun 3, 5:20 PM"),
                   Trade(at: 1780532460, probability: 0.37, volume: 49403.62, figure: "37%", clock: "Jun 3, 5:21 PM"),
                   Trade(at: 1780532520, probability: 0.37, volume: 68000.6, figure: "37%", clock: "Jun 3, 5:22 PM"),
                   Trade(at: 1780532580, probability: 0.37, volume: 76175.65, figure: "37%", clock: "Jun 3, 5:23 PM"),
                   Trade(at: 1780532640, probability: 0.37, volume: 451583.79, figure: "37%", clock: "Jun 3, 5:24 PM"),
                   Trade(at: 1780532700, probability: 0.37, volume: 66518.49, figure: "37%", clock: "Jun 3, 5:25 PM"),
                   Trade(at: 1780532760, probability: 0.37, volume: 91199.56, figure: "37%", clock: "Jun 3, 5:26 PM"),
                   Trade(at: 1780532820, probability: 0.37, volume: 80697.74, figure: "37%", clock: "Jun 3, 5:27 PM"),
                   Trade(at: 1780532880, probability: 0.37, volume: 145468.17, figure: "37%", clock: "Jun 3, 5:28 PM"),
                   Trade(at: 1780532940, probability: 0.37, volume: 72814.64, figure: "37%", clock: "Jun 3, 5:29 PM"),
                   Trade(at: 1780533000, probability: 0.37, volume: 144635.5, figure: "37%", clock: "Jun 3, 5:30 PM"),
                   Trade(at: 1780533060, probability: 0.37, volume: 90398.56, figure: "37%", clock: "Jun 3, 5:31 PM"),
                   Trade(at: 1780533120, probability: 0.37, volume: 130091.08, figure: "37%", clock: "Jun 3, 5:32 PM"),
                   Trade(at: 1780533180, probability: 0.37, volume: 82007.55, figure: "37%", clock: "Jun 3, 5:33 PM"),
                   Trade(at: 1780533240, probability: 0.37, volume: 119808.14, figure: "37%", clock: "Jun 3, 5:34 PM"),
                   Trade(at: 1780533300, probability: 0.37, volume: 85673.3, figure: "37%", clock: "Jun 3, 5:35 PM"),
                   Trade(at: 1780533360, probability: 0.37, volume: 103314.55, figure: "37%", clock: "Jun 3, 5:36 PM"),
                   Trade(at: 1780533420, probability: 0.37, volume: 64128.73, figure: "37%", clock: "Jun 3, 5:37 PM"),
                   Trade(at: 1780533480, probability: 0.37, volume: 72191.03, figure: "37%", clock: "Jun 3, 5:38 PM"),
                   Trade(at: 1780533540, probability: 0.37, volume: 53149.89, figure: "37%", clock: "Jun 3, 5:39 PM"),
                   Trade(at: 1780533600, probability: 0.37, volume: 80140.31, figure: "37%", clock: "Jun 3, 5:40 PM"),
                   Trade(at: 1780533660, probability: 0.37, volume: 93074.01, figure: "37%", clock: "Jun 3, 5:41 PM"),
                   Trade(at: 1780533720, probability: 0.37, volume: 85054.06, figure: "37%", clock: "Jun 3, 5:42 PM"),
                   Trade(at: 1780533780, probability: 0.37, volume: 82976.47, figure: "37%", clock: "Jun 3, 5:43 PM"),
                   Trade(at: 1780533840, probability: 0.37, volume: 68913.83, figure: "37%", clock: "Jun 3, 5:44 PM"),
                   Trade(at: 1780533900, probability: 0.4, volume: 98667.93, figure: "40%", clock: "Jun 3, 5:45 PM"),
                   Trade(at: 1780533960, probability: 0.42, volume: 242797.34, figure: "42%", clock: "Jun 3, 5:46 PM"),
                   Trade(at: 1780534020, probability: 0.46, volume: 295008.39, figure: "46%", clock: "Jun 3, 5:47 PM"),
                   Trade(at: 1780534080, probability: 0.47, volume: 295349.26, figure: "47%", clock: "Jun 3, 5:48 PM"),
                   Trade(at: 1780534140, probability: 0.42, volume: 254469.83, figure: "42%", clock: "Jun 3, 5:49 PM"),
                   Trade(at: 1780534200, probability: 0.45, volume: 129560.88, figure: "45%", clock: "Jun 3, 5:50 PM"),
                   Trade(at: 1780534260, probability: 0.44, volume: 160185.57, figure: "44%", clock: "Jun 3, 5:51 PM"),
                   Trade(at: 1780534320, probability: 0.44, volume: 133690.82, figure: "44%", clock: "Jun 3, 5:52 PM"),
                   Trade(at: 1780534380, probability: 0.44, volume: 101913.61, figure: "44%", clock: "Jun 3, 5:53 PM"),
                   Trade(at: 1780534440, probability: 0.48, volume: 201608.07, figure: "48%", clock: "Jun 3, 5:54 PM"),
                   Trade(at: 1780534500, probability: 0.48, volume: 247238.04, figure: "48%", clock: "Jun 3, 5:55 PM"),
                   Trade(at: 1780534560, probability: 0.45, volume: 166953.4, figure: "45%", clock: "Jun 3, 5:56 PM"),
                   Trade(at: 1780534620, probability: 0.43, volume: 171316.94, figure: "43%", clock: "Jun 3, 5:57 PM"),
                   Trade(at: 1780534680, probability: 0.42, volume: 98523.75, figure: "42%", clock: "Jun 3, 5:58 PM"),
                   Trade(at: 1780534740, probability: 0.41, volume: 102677.72, figure: "41%", clock: "Jun 3, 5:59 PM"),
                   Trade(at: 1780534800, probability: 0.39, volume: 151570.79, figure: "39%", clock: "Jun 3, 6:00 PM"),
                   Trade(at: 1780534860, probability: 0.36, volume: 114648.98, figure: "36%", clock: "Jun 3, 6:01 PM"),
                   Trade(at: 1780534920, probability: 0.31, volume: 302057.74, figure: "31%", clock: "Jun 3, 6:02 PM"),
                   Trade(at: 1780534980, probability: 0.32, volume: 158439.72, figure: "32%", clock: "Jun 3, 6:03 PM"),
                   Trade(at: 1780535040, probability: 0.31, volume: 135898.82, figure: "31%", clock: "Jun 3, 6:04 PM"),
                   Trade(at: 1780535100, probability: 0.31, volume: 109006.4, figure: "31%", clock: "Jun 3, 6:05 PM"),
                   Trade(at: 1780535160, probability: 0.31, volume: 72600.94, figure: "31%", clock: "Jun 3, 6:06 PM"),
                   Trade(at: 1780535220, probability: 0.26, volume: 119575.34, figure: "26%", clock: "Jun 3, 6:07 PM"),
                   Trade(at: 1780535280, probability: 0.21, volume: 314994.28, figure: "21%", clock: "Jun 3, 6:08 PM"),
                   Trade(at: 1780535340, probability: 0.21, volume: 324755.44, figure: "21%", clock: "Jun 3, 6:09 PM"),
                   Trade(at: 1780535400, probability: 0.21, volume: 287183.8, figure: "21%", clock: "Jun 3, 6:10 PM"),
                   Trade(at: 1780535460, probability: 0.23, volume: 154091.2, figure: "23%", clock: "Jun 3, 6:11 PM"),
                   Trade(at: 1780535520, probability: 0.22, volume: 177507.41, figure: "22%", clock: "Jun 3, 6:12 PM"),
                   Trade(at: 1780535580, probability: 0.2, volume: 219210.45, figure: "20%", clock: "Jun 3, 6:13 PM"),
                   Trade(at: 1780535640, probability: 0.2, volume: 164788.65, figure: "20%", clock: "Jun 3, 6:14 PM"),
                   Trade(at: 1780535700, probability: 0.21, volume: 129342.16, figure: "21%", clock: "Jun 3, 6:15 PM"),
                   Trade(at: 1780535760, probability: 0.2, volume: 114742.04, figure: "20%", clock: "Jun 3, 6:16 PM"),
                   Trade(at: 1780535820, probability: 0.23, volume: 510773.44, figure: "23%", clock: "Jun 3, 6:17 PM"),
                   Trade(at: 1780535880, probability: 0.29, volume: 125534.24, figure: "29%", clock: "Jun 3, 6:18 PM"),
                   Trade(at: 1780535940, probability: 0.29, volume: 160651.48, figure: "29%", clock: "Jun 3, 6:19 PM"),
                   Trade(at: 1780536000, probability: 0.3, volume: 145999.41, figure: "30%", clock: "Jun 3, 6:20 PM"),
                   Trade(at: 1780536060, probability: 0.29, volume: 85125.13, figure: "29%", clock: "Jun 3, 6:21 PM"),
                   Trade(at: 1780536120, probability: 0.31, volume: 94500.47, figure: "31%", clock: "Jun 3, 6:22 PM"),
                   Trade(at: 1780536180, probability: 0.33, volume: 109451.97, figure: "33%", clock: "Jun 3, 6:23 PM"),
                   Trade(at: 1780536240, probability: 0.33, volume: 86329.64, figure: "33%", clock: "Jun 3, 6:24 PM"),
                   Trade(at: 1780536300, probability: 0.32, volume: 47142.12, figure: "32%", clock: "Jun 3, 6:25 PM"),
                   Trade(at: 1780536360, probability: 0.32, volume: 62977.04, figure: "32%", clock: "Jun 3, 6:26 PM"),
                   Trade(at: 1780536420, probability: 0.3, volume: 62575.47, figure: "30%", clock: "Jun 3, 6:27 PM"),
                   Trade(at: 1780536480, probability: 0.34, volume: 145297.24, figure: "34%", clock: "Jun 3, 6:28 PM"),
                   Trade(at: 1780536540, probability: 0.34, volume: 100929.63, figure: "34%", clock: "Jun 3, 6:29 PM"),
                   Trade(at: 1780536600, probability: 0.31, volume: 87459.39, figure: "31%", clock: "Jun 3, 6:30 PM"),
                   Trade(at: 1780536660, probability: 0.27, volume: 209835.8, figure: "27%", clock: "Jun 3, 6:31 PM"),
                   Trade(at: 1780536720, probability: 0.27, volume: 91433.95, figure: "27%", clock: "Jun 3, 6:32 PM"),
                   Trade(at: 1780536780, probability: 0.26, volume: 116564.37, figure: "26%", clock: "Jun 3, 6:33 PM"),
                   Trade(at: 1780536840, probability: 0.26, volume: 65276.48, figure: "26%", clock: "Jun 3, 6:34 PM"),
                   Trade(at: 1780536900, probability: 0.31, volume: 431650.16, figure: "31%", clock: "Jun 3, 6:35 PM"),
                   Trade(at: 1780536960, probability: 0.39, volume: 82309.92, figure: "39%", clock: "Jun 3, 6:36 PM"),
                   Trade(at: 1780537020, probability: 0.41, volume: 216587.46, figure: "41%", clock: "Jun 3, 6:37 PM"),
                   Trade(at: 1780537080, probability: 0.35, volume: 177655.03, figure: "35%", clock: "Jun 3, 6:38 PM"),
                   Trade(at: 1780537140, probability: 0.39, volume: 143431.85, figure: "39%", clock: "Jun 3, 6:39 PM"),
                   Trade(at: 1780537200, probability: 0.38, volume: 135971.91, figure: "38%", clock: "Jun 3, 6:40 PM"),
                   Trade(at: 1780537260, probability: 0.32, volume: 146393.95, figure: "32%", clock: "Jun 3, 6:41 PM"),
                   Trade(at: 1780537320, probability: 0.31, volume: 116342, figure: "31%", clock: "Jun 3, 6:42 PM"),
                   Trade(at: 1780537380, probability: 0.33, volume: 74503.31, figure: "33%", clock: "Jun 3, 6:43 PM"),
                   Trade(at: 1780537440, probability: 0.29, volume: 120792.68, figure: "29%", clock: "Jun 3, 6:44 PM"),
                   Trade(at: 1780537500, probability: 0.24, volume: 235901.81, figure: "24%", clock: "Jun 3, 6:45 PM"),
                   Trade(at: 1780537560, probability: 0.24, volume: 154877.97, figure: "24%", clock: "Jun 3, 6:46 PM"),
                   Trade(at: 1780537620, probability: 0.23, volume: 171427.88, figure: "23%", clock: "Jun 3, 6:47 PM"),
                   Trade(at: 1780537680, probability: 0.23, volume: 111576.04, figure: "23%", clock: "Jun 3, 6:48 PM"),
                   Trade(at: 1780537740, probability: 0.23, volume: 95540.06, figure: "23%", clock: "Jun 3, 6:49 PM"),
                   Trade(at: 1780537800, probability: 0.24, volume: 143247.05, figure: "24%", clock: "Jun 3, 6:50 PM"),
                   Trade(at: 1780537860, probability: 0.24, volume: 107128.53, figure: "24%", clock: "Jun 3, 6:51 PM"),
                   Trade(at: 1780537920, probability: 0.24, volume: 112621.29, figure: "24%", clock: "Jun 3, 6:52 PM"),
                   Trade(at: 1780537980, probability: 0.24, volume: 100330.85, figure: "24%", clock: "Jun 3, 6:53 PM"),
                   Trade(at: 1780538040, probability: 0.24, volume: 70222.16, figure: "24%", clock: "Jun 3, 6:54 PM"),
                   Trade(at: 1780538100, probability: 0.24, volume: 116723.11, figure: "24%", clock: "Jun 3, 6:55 PM"),
                   Trade(at: 1780538160, probability: 0.24, volume: 59339, figure: "24%", clock: "Jun 3, 6:56 PM"),
                   Trade(at: 1780538220, probability: 0.24, volume: 47676.82, figure: "24%", clock: "Jun 3, 6:57 PM"),
                   Trade(at: 1780538280, probability: 0.24, volume: 107208.28, figure: "24%", clock: "Jun 3, 6:58 PM"),
                   Trade(at: 1780538340, probability: 0.24, volume: 57605.61, figure: "24%", clock: "Jun 3, 6:59 PM"),
                   Trade(at: 1780538400, probability: 0.24, volume: 113720.89, figure: "24%", clock: "Jun 3, 7:00 PM"),
                   Trade(at: 1780538460, probability: 0.24, volume: 58499.81, figure: "24%", clock: "Jun 3, 7:01 PM"),
                   Trade(at: 1780538520, probability: 0.25, volume: 110115.24, figure: "25%", clock: "Jun 3, 7:02 PM"),
                   Trade(at: 1780538580, probability: 0.27, volume: 81555.53, figure: "27%", clock: "Jun 3, 7:03 PM"),
                   Trade(at: 1780538640, probability: 0.24, volume: 104631.78, figure: "24%", clock: "Jun 3, 7:04 PM"),
                   Trade(at: 1780538700, probability: 0.21, volume: 109264.4, figure: "21%", clock: "Jun 3, 7:05 PM"),
                   Trade(at: 1780538760, probability: 0.17, volume: 165499.57, figure: "17%", clock: "Jun 3, 7:06 PM"),
                   Trade(at: 1780538820, probability: 0.2, volume: 331350.93, figure: "20%", clock: "Jun 3, 7:07 PM"),
                   Trade(at: 1780538880, probability: 0.17, volume: 229359.66, figure: "17%", clock: "Jun 3, 7:08 PM"),
                   Trade(at: 1780538940, probability: 0.16, volume: 169027.79, figure: "16%", clock: "Jun 3, 7:09 PM"),
                   Trade(at: 1780539000, probability: 0.11, volume: 311083.88, figure: "11%", clock: "Jun 3, 7:10 PM"),
                   Trade(at: 1780539060, probability: 0.11, volume: 373707.23, figure: "11%", clock: "Jun 3, 7:11 PM"),
                   Trade(at: 1780539120, probability: 0.14, volume: 337972.26, figure: "14%", clock: "Jun 3, 7:12 PM"),
                   Trade(at: 1780539180, probability: 0.14, volume: 187272.87, figure: "14%", clock: "Jun 3, 7:13 PM"),
                   Trade(at: 1780539240, probability: 0.14, volume: 135003.57, figure: "14%", clock: "Jun 3, 7:14 PM"),
                   Trade(at: 1780539300, probability: 0.14, volume: 131554.47, figure: "14%", clock: "Jun 3, 7:15 PM"),
                   Trade(at: 1780539360, probability: 0.13, volume: 166972.88, figure: "13%", clock: "Jun 3, 7:16 PM"),
                   Trade(at: 1780539420, probability: 0.13, volume: 260368.14, figure: "13%", clock: "Jun 3, 7:17 PM"),
                   Trade(at: 1780539480, probability: 0.14, volume: 257280.12, figure: "14%", clock: "Jun 3, 7:18 PM"),
                   Trade(at: 1780539540, probability: 0.19, volume: 308282.41, figure: "19%", clock: "Jun 3, 7:19 PM"),
                   Trade(at: 1780539600, probability: 0.25, volume: 227995.55, figure: "25%", clock: "Jun 3, 7:20 PM"),
                   Trade(at: 1780539660, probability: 0.24, volume: 216089.76, figure: "24%", clock: "Jun 3, 7:21 PM"),
                   Trade(at: 1780539720, probability: 0.24, volume: 141814.51, figure: "24%", clock: "Jun 3, 7:22 PM"),
                   Trade(at: 1780539780, probability: 0.24, volume: 102848.1, figure: "24%", clock: "Jun 3, 7:23 PM"),
                   Trade(at: 1780539840, probability: 0.2, volume: 114800.5, figure: "20%", clock: "Jun 3, 7:24 PM"),
                   Trade(at: 1780539900, probability: 0.27, volume: 336610.22, figure: "27%", clock: "Jun 3, 7:25 PM"),
                   Trade(at: 1780539960, probability: 0.32, volume: 244738.85, figure: "32%", clock: "Jun 3, 7:26 PM"),
                   Trade(at: 1780540020, probability: 0.36, volume: 191166.88, figure: "36%", clock: "Jun 3, 7:27 PM"),
                   Trade(at: 1780540080, probability: 0.38, volume: 457599.78, figure: "38%", clock: "Jun 3, 7:28 PM"),
                   Trade(at: 1780540140, probability: 0.37, volume: 365279.07, figure: "37%", clock: "Jun 3, 7:29 PM"),
                   Trade(at: 1780540200, probability: 0.39, volume: 248727.82, figure: "39%", clock: "Jun 3, 7:30 PM"),
                   Trade(at: 1780540260, probability: 0.39, volume: 136710.96, figure: "39%", clock: "Jun 3, 7:31 PM"),
                   Trade(at: 1780540320, probability: 0.34, volume: 140809.48, figure: "34%", clock: "Jun 3, 7:32 PM"),
                   Trade(at: 1780540380, probability: 0.41, volume: 287395.48, figure: "41%", clock: "Jun 3, 7:33 PM"),
                   Trade(at: 1780540440, probability: 0.41, volume: 275283, figure: "41%", clock: "Jun 3, 7:34 PM"),
                   Trade(at: 1780540500, probability: 0.42, volume: 173597.18, figure: "42%", clock: "Jun 3, 7:35 PM"),
                   Trade(at: 1780540560, probability: 0.42, volume: 285350.32, figure: "42%", clock: "Jun 3, 7:36 PM"),
                   Trade(at: 1780540620, probability: 0.43, volume: 266866.81, figure: "43%", clock: "Jun 3, 7:37 PM"),
                   Trade(at: 1780540680, probability: 0.45, volume: 175688.27, figure: "45%", clock: "Jun 3, 7:38 PM"),
                   Trade(at: 1780540740, probability: 0.45, volume: 137615.39, figure: "45%", clock: "Jun 3, 7:39 PM"),
                   Trade(at: 1780540800, probability: 0.49, volume: 196263.43, figure: "49%", clock: "Jun 3, 7:40 PM"),
                   Trade(at: 1780540860, probability: 0.56, volume: 403152.67, figure: "56%", clock: "Jun 3, 7:41 PM"),
                   Trade(at: 1780540920, probability: 0.45, volume: 239103.89, figure: "45%", clock: "Jun 3, 7:42 PM"),
                   Trade(at: 1780540980, probability: 0.43, volume: 169471.88, figure: "43%", clock: "Jun 3, 7:43 PM"),
                   Trade(at: 1780541040, probability: 0.43, volume: 123492.52, figure: "43%", clock: "Jun 3, 7:44 PM"),
                   Trade(at: 1780541100, probability: 0.43, volume: 134446.84, figure: "43%", clock: "Jun 3, 7:45 PM"),
                   Trade(at: 1780541160, probability: 0.43, volume: 82325.21, figure: "43%", clock: "Jun 3, 7:46 PM"),
                   Trade(at: 1780541220, probability: 0.42, volume: 90441.22, figure: "42%", clock: "Jun 3, 7:47 PM"),
                   Trade(at: 1780541280, probability: 0.56, volume: 220868.31, figure: "56%", clock: "Jun 3, 7:48 PM"),
                   Trade(at: 1780541340, probability: 0.68, volume: 296148.65, figure: "68%", clock: "Jun 3, 7:49 PM"),
                   Trade(at: 1780541400, probability: 0.7, volume: 547903.89, figure: "70%", clock: "Jun 3, 7:50 PM"),
                   Trade(at: 1780541460, probability: 0.69, volume: 399797.43, figure: "69%", clock: "Jun 3, 7:51 PM"),
                   Trade(at: 1780541520, probability: 0.7, volume: 459875.6, figure: "70%", clock: "Jun 3, 7:52 PM"),
                   Trade(at: 1780541580, probability: 0.69, volume: 239017.36, figure: "69%", clock: "Jun 3, 7:53 PM"),
                   Trade(at: 1780541640, probability: 0.7, volume: 122939.55, figure: "70%", clock: "Jun 3, 7:54 PM"),
                   Trade(at: 1780541700, probability: 0.78, volume: 237072.23, figure: "78%", clock: "Jun 3, 7:55 PM"),
                   Trade(at: 1780541760, probability: 0.85, volume: 595596.15, figure: "85%", clock: "Jun 3, 7:56 PM"),
                   Trade(at: 1780541820, probability: 0.78, volume: 490936.49, figure: "78%", clock: "Jun 3, 7:57 PM"),
                   Trade(at: 1780541880, probability: 0.74, volume: 309020.62, figure: "74%", clock: "Jun 3, 7:58 PM"),
                   Trade(at: 1780541940, probability: 0.74, volume: 403964.76, figure: "74%", clock: "Jun 3, 7:59 PM"),
                   Trade(at: 1780542000, probability: 0.66, volume: 176644.14, figure: "66%", clock: "Jun 3, 8:00 PM"),
                   Trade(at: 1780542060, probability: 0.7, volume: 218228.62, figure: "70%", clock: "Jun 3, 8:01 PM"),
                   Trade(at: 1780542120, probability: 0.53, volume: 231599.11, figure: "53%", clock: "Jun 3, 8:02 PM"),
                   Trade(at: 1780542180, probability: 0.53, volume: 229025.17, figure: "53%", clock: "Jun 3, 8:03 PM"),
                   Trade(at: 1780542240, probability: 0.4, volume: 246396.82, figure: "40%", clock: "Jun 3, 8:04 PM"),
                   Trade(at: 1780542300, probability: 0.37, volume: 317029.46, figure: "37%", clock: "Jun 3, 8:05 PM"),
                   Trade(at: 1780542360, probability: 0.73, volume: 222889.55, figure: "73%", clock: "Jun 3, 8:06 PM"),
                   Trade(at: 1780542420, probability: 0.83, volume: 510999.35, figure: "83%", clock: "Jun 3, 8:07 PM"),
                   Trade(at: 1780542480, probability: 0.98, volume: 1241510.7, figure: "98%", clock: "Jun 3, 8:08 PM"),
                   Trade(at: 1780542540, probability: 0.99, volume: 887826.34, figure: "99%", clock: "Jun 3, 8:09 PM"),
                   Trade(at: 1780542600, probability: 0.99, volume: 229364.29, figure: "99%", clock: "Jun 3, 8:10 PM"),
                   Trade(at: 1780542660, probability: 0.99, volume: 255688.99, figure: "99%", clock: "Jun 3, 8:11 PM"),
                   Trade(at: 1780542720, probability: 0.99, volume: 99378.92, figure: "99%", clock: "Jun 3, 8:12 PM"),
                   Trade(at: 1780542780, probability: 0.99, volume: 96341.49, figure: "99%", clock: "Jun 3, 8:13 PM"),
                   Trade(at: 1780542840, probability: 0.99, volume: 43161.7, figure: "99%", clock: "Jun 3, 8:14 PM"),
                   Trade(at: 1780542900, probability: 0.99, volume: 27119.94, figure: "99%", clock: "Jun 3, 8:15 PM"),
                   Trade(at: 1780542960, probability: 0.99, volume: 113602.18, figure: "99%", clock: "Jun 3, 8:16 PM"),
               ],
               early: [
                   Trade(at: 1780374960, probability: 0.38, volume: 328.28, figure: "38%", clock: "Jun 1, 9:36 PM"),
                   Trade(at: 1780375020, probability: 0.38, volume: 1143.89, figure: "38%", clock: "Jun 1, 9:37 PM"),
                   Trade(at: 1780375080, probability: 0.37, volume: 120.02, figure: "37%", clock: "Jun 1, 9:38 PM"),
                   Trade(at: 1780375140, probability: 0.38, volume: 12.47, figure: "38%", clock: "Jun 1, 9:39 PM"),
                   Trade(at: 1780375200, probability: 0.38, volume: 198.22, figure: "38%", clock: "Jun 1, 9:40 PM"),
               ],
               earlyRuns: [[0,1,2,3,4]]),
        Winner(ticker: "KXNBAGAME-26JUN03NYKSAS-SAS", name: "Spurs", shape: .diamond, tint: .teal,
               baseline: Trade(at: 1780532940, probability: 0.64, volume: 70479.48, figure: "64%", clock: "Jun 3, 5:29 PM"),
               around: [
                   Trade(at: 1780529400, probability: 0.64, volume: 7934.48, figure: "64%", clock: "Jun 3, 4:30 PM"),
                   Trade(at: 1780529460, probability: 0.64, volume: 13615.65, figure: "64%", clock: "Jun 3, 4:31 PM"),
                   Trade(at: 1780529520, probability: 0.64, volume: 10461.15, figure: "64%", clock: "Jun 3, 4:32 PM"),
                   Trade(at: 1780529580, probability: 0.64, volume: 13319.79, figure: "64%", clock: "Jun 3, 4:33 PM"),
                   Trade(at: 1780529640, probability: 0.64, volume: 8199.69, figure: "64%", clock: "Jun 3, 4:34 PM"),
                   Trade(at: 1780529700, probability: 0.64, volume: 19252.17, figure: "64%", clock: "Jun 3, 4:35 PM"),
                   Trade(at: 1780529760, probability: 0.64, volume: 17036.83, figure: "64%", clock: "Jun 3, 4:36 PM"),
                   Trade(at: 1780529820, probability: 0.64, volume: 16581.4, figure: "64%", clock: "Jun 3, 4:37 PM"),
                   Trade(at: 1780529880, probability: 0.64, volume: 9558.49, figure: "64%", clock: "Jun 3, 4:38 PM"),
                   Trade(at: 1780529940, probability: 0.63, volume: 20201.3, figure: "63%", clock: "Jun 3, 4:39 PM"),
                   Trade(at: 1780530000, probability: 0.64, volume: 11201.35, figure: "64%", clock: "Jun 3, 4:40 PM"),
                   Trade(at: 1780530060, probability: 0.64, volume: 11910.12, figure: "64%", clock: "Jun 3, 4:41 PM"),
                   Trade(at: 1780530120, probability: 0.64, volume: 17717.67, figure: "64%", clock: "Jun 3, 4:42 PM"),
                   Trade(at: 1780530180, probability: 0.64, volume: 23581.04, figure: "64%", clock: "Jun 3, 4:43 PM"),
                   Trade(at: 1780530240, probability: 0.64, volume: 24027.92, figure: "64%", clock: "Jun 3, 4:44 PM"),
                   Trade(at: 1780530300, probability: 0.64, volume: 19218.19, figure: "64%", clock: "Jun 3, 4:45 PM"),
                   Trade(at: 1780530360, probability: 0.64, volume: 13762.24, figure: "64%", clock: "Jun 3, 4:46 PM"),
                   Trade(at: 1780530420, probability: 0.64, volume: 23444.86, figure: "64%", clock: "Jun 3, 4:47 PM"),
                   Trade(at: 1780530480, probability: 0.64, volume: 20177.3, figure: "64%", clock: "Jun 3, 4:48 PM"),
                   Trade(at: 1780530540, probability: 0.64, volume: 22338.62, figure: "64%", clock: "Jun 3, 4:49 PM"),
                   Trade(at: 1780530600, probability: 0.64, volume: 33910.41, figure: "64%", clock: "Jun 3, 4:50 PM"),
                   Trade(at: 1780530660, probability: 0.64, volume: 10591.34, figure: "64%", clock: "Jun 3, 4:51 PM"),
                   Trade(at: 1780530720, probability: 0.64, volume: 15963.72, figure: "64%", clock: "Jun 3, 4:52 PM"),
                   Trade(at: 1780530780, probability: 0.64, volume: 19448.38, figure: "64%", clock: "Jun 3, 4:53 PM"),
                   Trade(at: 1780530840, probability: 0.64, volume: 16513.01, figure: "64%", clock: "Jun 3, 4:54 PM"),
                   Trade(at: 1780530900, probability: 0.64, volume: 11225.85, figure: "64%", clock: "Jun 3, 4:55 PM"),
                   Trade(at: 1780530960, probability: 0.64, volume: 20520.31, figure: "64%", clock: "Jun 3, 4:56 PM"),
                   Trade(at: 1780531020, probability: 0.64, volume: 22748.59, figure: "64%", clock: "Jun 3, 4:57 PM"),
                   Trade(at: 1780531080, probability: 0.64, volume: 16290.2, figure: "64%", clock: "Jun 3, 4:58 PM"),
                   Trade(at: 1780531140, probability: 0.64, volume: 21667.83, figure: "64%", clock: "Jun 3, 4:59 PM"),
                   Trade(at: 1780531200, probability: 0.64, volume: 27046.49, figure: "64%", clock: "Jun 3, 5:00 PM"),
                   Trade(at: 1780531260, probability: 0.64, volume: 13892.24, figure: "64%", clock: "Jun 3, 5:01 PM"),
                   Trade(at: 1780531320, probability: 0.64, volume: 35381.31, figure: "64%", clock: "Jun 3, 5:02 PM"),
                   Trade(at: 1780531380, probability: 0.64, volume: 20635.5, figure: "64%", clock: "Jun 3, 5:03 PM"),
                   Trade(at: 1780531440, probability: 0.64, volume: 36556.91, figure: "64%", clock: "Jun 3, 5:04 PM"),
                   Trade(at: 1780531500, probability: 0.64, volume: 21541.05, figure: "64%", clock: "Jun 3, 5:05 PM"),
                   Trade(at: 1780531560, probability: 0.64, volume: 12426.64, figure: "64%", clock: "Jun 3, 5:06 PM"),
                   Trade(at: 1780531620, probability: 0.64, volume: 31491.97, figure: "64%", clock: "Jun 3, 5:07 PM"),
                   Trade(at: 1780531680, probability: 0.64, volume: 32505.18, figure: "64%", clock: "Jun 3, 5:08 PM"),
                   Trade(at: 1780531740, probability: 0.64, volume: 24736.88, figure: "64%", clock: "Jun 3, 5:09 PM"),
                   Trade(at: 1780531800, probability: 0.64, volume: 29956.15, figure: "64%", clock: "Jun 3, 5:10 PM"),
                   Trade(at: 1780531860, probability: 0.64, volume: 38389.49, figure: "64%", clock: "Jun 3, 5:11 PM"),
                   Trade(at: 1780531920, probability: 0.64, volume: 17146.52, figure: "64%", clock: "Jun 3, 5:12 PM"),
                   Trade(at: 1780531980, probability: 0.64, volume: 25448.61, figure: "64%", clock: "Jun 3, 5:13 PM"),
                   Trade(at: 1780532040, probability: 0.64, volume: 17943.14, figure: "64%", clock: "Jun 3, 5:14 PM"),
                   Trade(at: 1780532100, probability: 0.64, volume: 31616.55, figure: "64%", clock: "Jun 3, 5:15 PM"),
                   Trade(at: 1780532160, probability: 0.64, volume: 57941.45, figure: "64%", clock: "Jun 3, 5:16 PM"),
                   Trade(at: 1780532220, probability: 0.64, volume: 16957.24, figure: "64%", clock: "Jun 3, 5:17 PM"),
                   Trade(at: 1780532280, probability: 0.64, volume: 33061.04, figure: "64%", clock: "Jun 3, 5:18 PM"),
                   Trade(at: 1780532340, probability: 0.64, volume: 49334.36, figure: "64%", clock: "Jun 3, 5:19 PM"),
                   Trade(at: 1780532400, probability: 0.64, volume: 30543.55, figure: "64%", clock: "Jun 3, 5:20 PM"),
                   Trade(at: 1780532460, probability: 0.64, volume: 35001.17, figure: "64%", clock: "Jun 3, 5:21 PM"),
                   Trade(at: 1780532520, probability: 0.64, volume: 32300.83, figure: "64%", clock: "Jun 3, 5:22 PM"),
                   Trade(at: 1780532580, probability: 0.64, volume: 81224.54, figure: "64%", clock: "Jun 3, 5:23 PM"),
                   Trade(at: 1780532640, probability: 0.64, volume: 84695.04, figure: "64%", clock: "Jun 3, 5:24 PM"),
                   Trade(at: 1780532700, probability: 0.64, volume: 48065.93, figure: "64%", clock: "Jun 3, 5:25 PM"),
                   Trade(at: 1780532760, probability: 0.64, volume: 52457.4, figure: "64%", clock: "Jun 3, 5:26 PM"),
                   Trade(at: 1780532820, probability: 0.64, volume: 32614.86, figure: "64%", clock: "Jun 3, 5:27 PM"),
                   Trade(at: 1780532880, probability: 0.64, volume: 134992.58, figure: "64%", clock: "Jun 3, 5:28 PM"),
                   Trade(at: 1780532940, probability: 0.64, volume: 70479.48, figure: "64%", clock: "Jun 3, 5:29 PM"),
                   Trade(at: 1780533000, probability: 0.64, volume: 59303.66, figure: "64%", clock: "Jun 3, 5:30 PM"),
                   Trade(at: 1780533060, probability: 0.64, volume: 112036.16, figure: "64%", clock: "Jun 3, 5:31 PM"),
                   Trade(at: 1780533120, probability: 0.64, volume: 84077.52, figure: "64%", clock: "Jun 3, 5:32 PM"),
                   Trade(at: 1780533180, probability: 0.64, volume: 45187.7, figure: "64%", clock: "Jun 3, 5:33 PM"),
                   Trade(at: 1780533240, probability: 0.64, volume: 60368.09, figure: "64%", clock: "Jun 3, 5:34 PM"),
                   Trade(at: 1780533300, probability: 0.64, volume: 44306.6, figure: "64%", clock: "Jun 3, 5:35 PM"),
                   Trade(at: 1780533360, probability: 0.64, volume: 94855.15, figure: "64%", clock: "Jun 3, 5:36 PM"),
                   Trade(at: 1780533420, probability: 0.64, volume: 21243.91, figure: "64%", clock: "Jun 3, 5:37 PM"),
                   Trade(at: 1780533480, probability: 0.64, volume: 46861.91, figure: "64%", clock: "Jun 3, 5:38 PM"),
                   Trade(at: 1780533540, probability: 0.64, volume: 114766.69, figure: "64%", clock: "Jun 3, 5:39 PM"),
                   Trade(at: 1780533600, probability: 0.64, volume: 53659.68, figure: "64%", clock: "Jun 3, 5:40 PM"),
                   Trade(at: 1780533660, probability: 0.64, volume: 42739.87, figure: "64%", clock: "Jun 3, 5:41 PM"),
                   Trade(at: 1780533720, probability: 0.64, volume: 34739.07, figure: "64%", clock: "Jun 3, 5:42 PM"),
                   Trade(at: 1780533780, probability: 0.64, volume: 46842.2, figure: "64%", clock: "Jun 3, 5:43 PM"),
                   Trade(at: 1780533840, probability: 0.64, volume: 48210.1, figure: "64%", clock: "Jun 3, 5:44 PM"),
                   Trade(at: 1780533900, probability: 0.63, volume: 119796.74, figure: "63%", clock: "Jun 3, 5:45 PM"),
                   Trade(at: 1780533960, probability: 0.6, volume: 87925.71, figure: "60%", clock: "Jun 3, 5:46 PM"),
                   Trade(at: 1780534020, probability: 0.54, volume: 158264.32, figure: "54%", clock: "Jun 3, 5:47 PM"),
                   Trade(at: 1780534080, probability: 0.54, volume: 194109.37, figure: "54%", clock: "Jun 3, 5:48 PM"),
                   Trade(at: 1780534140, probability: 0.59, volume: 132466.69, figure: "59%", clock: "Jun 3, 5:49 PM"),
                   Trade(at: 1780534200, probability: 0.56, volume: 156832.32, figure: "56%", clock: "Jun 3, 5:50 PM"),
                   Trade(at: 1780534260, probability: 0.57, volume: 138288.53, figure: "57%", clock: "Jun 3, 5:51 PM"),
                   Trade(at: 1780534320, probability: 0.57, volume: 77293.02, figure: "57%", clock: "Jun 3, 5:52 PM"),
                   Trade(at: 1780534380, probability: 0.57, volume: 64388.67, figure: "57%", clock: "Jun 3, 5:53 PM"),
                   Trade(at: 1780534440, probability: 0.55, volume: 41806.99, figure: "55%", clock: "Jun 3, 5:54 PM"),
                   Trade(at: 1780534500, probability: 0.52, volume: 112502.06, figure: "52%", clock: "Jun 3, 5:55 PM"),
                   Trade(at: 1780534560, probability: 0.56, volume: 86335.7, figure: "56%", clock: "Jun 3, 5:56 PM"),
                   Trade(at: 1780534620, probability: 0.58, volume: 70080.06, figure: "58%", clock: "Jun 3, 5:57 PM"),
                   Trade(at: 1780534680, probability: 0.58, volume: 71838.07, figure: "58%", clock: "Jun 3, 5:58 PM"),
                   Trade(at: 1780534740, probability: 0.6, volume: 47532.54, figure: "60%", clock: "Jun 3, 5:59 PM"),
                   Trade(at: 1780534800, probability: 0.62, volume: 59178.54, figure: "62%", clock: "Jun 3, 6:00 PM"),
                   Trade(at: 1780534860, probability: 0.66, volume: 98977.14, figure: "66%", clock: "Jun 3, 6:01 PM"),
                   Trade(at: 1780534920, probability: 0.7, volume: 165168.01, figure: "70%", clock: "Jun 3, 6:02 PM"),
                   Trade(at: 1780534980, probability: 0.68, volume: 100108.19, figure: "68%", clock: "Jun 3, 6:03 PM"),
                   Trade(at: 1780535040, probability: 0.7, volume: 150647.68, figure: "70%", clock: "Jun 3, 6:04 PM"),
                   Trade(at: 1780535100, probability: 0.7, volume: 72589.5, figure: "70%", clock: "Jun 3, 6:05 PM"),
                   Trade(at: 1780535160, probability: 0.7, volume: 25843.81, figure: "70%", clock: "Jun 3, 6:06 PM"),
                   Trade(at: 1780535220, probability: 0.75, volume: 50672.93, figure: "75%", clock: "Jun 3, 6:07 PM"),
                   Trade(at: 1780535280, probability: 0.8, volume: 388671.46, figure: "80%", clock: "Jun 3, 6:08 PM"),
                   Trade(at: 1780535340, probability: 0.79, volume: 305592.67, figure: "79%", clock: "Jun 3, 6:09 PM"),
                   Trade(at: 1780535400, probability: 0.78, volume: 262468.73, figure: "78%", clock: "Jun 3, 6:10 PM"),
                   Trade(at: 1780535460, probability: 0.77, volume: 142835.39, figure: "77%", clock: "Jun 3, 6:11 PM"),
                   Trade(at: 1780535520, probability: 0.79, volume: 79595.14, figure: "79%", clock: "Jun 3, 6:12 PM"),
                   Trade(at: 1780535580, probability: 0.8, volume: 142892.95, figure: "80%", clock: "Jun 3, 6:13 PM"),
                   Trade(at: 1780535640, probability: 0.8, volume: 100081.86, figure: "80%", clock: "Jun 3, 6:14 PM"),
                   Trade(at: 1780535700, probability: 0.8, volume: 73420.53, figure: "80%", clock: "Jun 3, 6:15 PM"),
                   Trade(at: 1780535760, probability: 0.81, volume: 116680.05, figure: "81%", clock: "Jun 3, 6:16 PM"),
                   Trade(at: 1780535820, probability: 0.77, volume: 130539.76, figure: "77%", clock: "Jun 3, 6:17 PM"),
                   Trade(at: 1780535880, probability: 0.72, volume: 121069.86, figure: "72%", clock: "Jun 3, 6:18 PM"),
                   Trade(at: 1780535940, probability: 0.7, volume: 93125.35, figure: "70%", clock: "Jun 3, 6:19 PM"),
                   Trade(at: 1780536000, probability: 0.71, volume: 112993.68, figure: "71%", clock: "Jun 3, 6:20 PM"),
                   Trade(at: 1780536060, probability: 0.71, volume: 113474.22, figure: "71%", clock: "Jun 3, 6:21 PM"),
                   Trade(at: 1780536120, probability: 0.69, volume: 52013.51, figure: "69%", clock: "Jun 3, 6:22 PM"),
                   Trade(at: 1780536180, probability: 0.68, volume: 80609.53, figure: "68%", clock: "Jun 3, 6:23 PM"),
                   Trade(at: 1780536240, probability: 0.68, volume: 47225.02, figure: "68%", clock: "Jun 3, 6:24 PM"),
                   Trade(at: 1780536300, probability: 0.69, volume: 45759.62, figure: "69%", clock: "Jun 3, 6:25 PM"),
                   Trade(at: 1780536360, probability: 0.69, volume: 27267.37, figure: "69%", clock: "Jun 3, 6:26 PM"),
                   Trade(at: 1780536420, probability: 0.71, volume: 16175.86, figure: "71%", clock: "Jun 3, 6:27 PM"),
                   Trade(at: 1780536480, probability: 0.67, volume: 49146.5, figure: "67%", clock: "Jun 3, 6:28 PM"),
                   Trade(at: 1780536540, probability: 0.67, volume: 53524.24, figure: "67%", clock: "Jun 3, 6:29 PM"),
                   Trade(at: 1780536600, probability: 0.7, volume: 69911.65, figure: "70%", clock: "Jun 3, 6:30 PM"),
                   Trade(at: 1780536660, probability: 0.74, volume: 39400.44, figure: "74%", clock: "Jun 3, 6:31 PM"),
                   Trade(at: 1780536720, probability: 0.74, volume: 66701.9, figure: "74%", clock: "Jun 3, 6:32 PM"),
                   Trade(at: 1780536780, probability: 0.75, volume: 83896.66, figure: "75%", clock: "Jun 3, 6:33 PM"),
                   Trade(at: 1780536840, probability: 0.75, volume: 43340.55, figure: "75%", clock: "Jun 3, 6:34 PM"),
                   Trade(at: 1780536900, probability: 0.71, volume: 120182.26, figure: "71%", clock: "Jun 3, 6:35 PM"),
                   Trade(at: 1780536960, probability: 0.62, volume: 64408.53, figure: "62%", clock: "Jun 3, 6:36 PM"),
                   Trade(at: 1780537020, probability: 0.6, volume: 156881.19, figure: "60%", clock: "Jun 3, 6:37 PM"),
                   Trade(at: 1780537080, probability: 0.66, volume: 100707.15, figure: "66%", clock: "Jun 3, 6:38 PM"),
                   Trade(at: 1780537140, probability: 0.62, volume: 67533.57, figure: "62%", clock: "Jun 3, 6:39 PM"),
                   Trade(at: 1780537200, probability: 0.63, volume: 89023.74, figure: "63%", clock: "Jun 3, 6:40 PM"),
                   Trade(at: 1780537260, probability: 0.7, volume: 91748.75, figure: "70%", clock: "Jun 3, 6:41 PM"),
                   Trade(at: 1780537320, probability: 0.7, volume: 54249.05, figure: "70%", clock: "Jun 3, 6:42 PM"),
                   Trade(at: 1780537380, probability: 0.68, volume: 134786.78, figure: "68%", clock: "Jun 3, 6:43 PM"),
                   Trade(at: 1780537440, probability: 0.71, volume: 97637.27, figure: "71%", clock: "Jun 3, 6:44 PM"),
                   Trade(at: 1780537500, probability: 0.77, volume: 164174.66, figure: "77%", clock: "Jun 3, 6:45 PM"),
                   Trade(at: 1780537560, probability: 0.77, volume: 157961.87, figure: "77%", clock: "Jun 3, 6:46 PM"),
                   Trade(at: 1780537620, probability: 0.76, volume: 252136.74, figure: "76%", clock: "Jun 3, 6:47 PM"),
                   Trade(at: 1780537680, probability: 0.78, volume: 28188.76, figure: "78%", clock: "Jun 3, 6:48 PM"),
                   Trade(at: 1780537740, probability: 0.78, volume: 32208.07, figure: "78%", clock: "Jun 3, 6:49 PM"),
                   Trade(at: 1780537800, probability: 0.77, volume: 29965.02, figure: "77%", clock: "Jun 3, 6:50 PM"),
                   Trade(at: 1780537860, probability: 0.77, volume: 143331.73, figure: "77%", clock: "Jun 3, 6:51 PM"),
                   Trade(at: 1780537920, probability: 0.77, volume: 26956.61, figure: "77%", clock: "Jun 3, 6:52 PM"),
                   Trade(at: 1780537980, probability: 0.77, volume: 15163.04, figure: "77%", clock: "Jun 3, 6:53 PM"),
                   Trade(at: 1780538040, probability: 0.77, volume: 31434.42, figure: "77%", clock: "Jun 3, 6:54 PM"),
                   Trade(at: 1780538100, probability: 0.77, volume: 16190.44, figure: "77%", clock: "Jun 3, 6:55 PM"),
                   Trade(at: 1780538160, probability: 0.77, volume: 23518.97, figure: "77%", clock: "Jun 3, 6:56 PM"),
                   Trade(at: 1780538220, probability: 0.77, volume: 31242.11, figure: "77%", clock: "Jun 3, 6:57 PM"),
                   Trade(at: 1780538280, probability: 0.77, volume: 20021.01, figure: "77%", clock: "Jun 3, 6:58 PM"),
                   Trade(at: 1780538340, probability: 0.77, volume: 23506.68, figure: "77%", clock: "Jun 3, 6:59 PM"),
                   Trade(at: 1780538400, probability: 0.77, volume: 23188.22, figure: "77%", clock: "Jun 3, 7:00 PM"),
                   Trade(at: 1780538460, probability: 0.77, volume: 25811.71, figure: "77%", clock: "Jun 3, 7:01 PM"),
                   Trade(at: 1780538520, probability: 0.76, volume: 66457.55, figure: "76%", clock: "Jun 3, 7:02 PM"),
                   Trade(at: 1780538580, probability: 0.74, volume: 61051.01, figure: "74%", clock: "Jun 3, 7:03 PM"),
                   Trade(at: 1780538640, probability: 0.78, volume: 77449.82, figure: "78%", clock: "Jun 3, 7:04 PM"),
                   Trade(at: 1780538700, probability: 0.8, volume: 63548.73, figure: "80%", clock: "Jun 3, 7:05 PM"),
                   Trade(at: 1780538760, probability: 0.83, volume: 131835.27, figure: "83%", clock: "Jun 3, 7:06 PM"),
                   Trade(at: 1780538820, probability: 0.81, volume: 333880.96, figure: "81%", clock: "Jun 3, 7:07 PM"),
                   Trade(at: 1780538880, probability: 0.83, volume: 109607.43, figure: "83%", clock: "Jun 3, 7:08 PM"),
                   Trade(at: 1780538940, probability: 0.85, volume: 127059.45, figure: "85%", clock: "Jun 3, 7:09 PM"),
                   Trade(at: 1780539000, probability: 0.9, volume: 221240.24, figure: "90%", clock: "Jun 3, 7:10 PM"),
                   Trade(at: 1780539060, probability: 0.9, volume: 383048.64, figure: "90%", clock: "Jun 3, 7:11 PM"),
                   Trade(at: 1780539120, probability: 0.87, volume: 196110.84, figure: "87%", clock: "Jun 3, 7:12 PM"),
                   Trade(at: 1780539180, probability: 0.87, volume: 115104.47, figure: "87%", clock: "Jun 3, 7:13 PM"),
                   Trade(at: 1780539240, probability: 0.87, volume: 53588.73, figure: "87%", clock: "Jun 3, 7:14 PM"),
                   Trade(at: 1780539300, probability: 0.87, volume: 67285.87, figure: "87%", clock: "Jun 3, 7:15 PM"),
                   Trade(at: 1780539360, probability: 0.88, volume: 150446.08, figure: "88%", clock: "Jun 3, 7:16 PM"),
                   Trade(at: 1780539420, probability: 0.87, volume: 133389.3, figure: "87%", clock: "Jun 3, 7:17 PM"),
                   Trade(at: 1780539480, probability: 0.87, volume: 68436.01, figure: "87%", clock: "Jun 3, 7:18 PM"),
                   Trade(at: 1780539540, probability: 0.82, volume: 216104.33, figure: "82%", clock: "Jun 3, 7:19 PM"),
                   Trade(at: 1780539600, probability: 0.77, volume: 181913.17, figure: "77%", clock: "Jun 3, 7:20 PM"),
                   Trade(at: 1780539660, probability: 0.77, volume: 82605.61, figure: "77%", clock: "Jun 3, 7:21 PM"),
                   Trade(at: 1780539720, probability: 0.76, volume: 65090.84, figure: "76%", clock: "Jun 3, 7:22 PM"),
                   Trade(at: 1780539780, probability: 0.77, volume: 29654.53, figure: "77%", clock: "Jun 3, 7:23 PM"),
                   Trade(at: 1780539840, probability: 0.8, volume: 146175.22, figure: "80%", clock: "Jun 3, 7:24 PM"),
                   Trade(at: 1780539900, probability: 0.73, volume: 202872.36, figure: "73%", clock: "Jun 3, 7:25 PM"),
                   Trade(at: 1780539960, probability: 0.68, volume: 92615.7, figure: "68%", clock: "Jun 3, 7:26 PM"),
                   Trade(at: 1780540020, probability: 0.64, volume: 169338.19, figure: "64%", clock: "Jun 3, 7:27 PM"),
                   Trade(at: 1780540080, probability: 0.62, volume: 155612.64, figure: "62%", clock: "Jun 3, 7:28 PM"),
                   Trade(at: 1780540140, probability: 0.64, volume: 248285.15, figure: "64%", clock: "Jun 3, 7:29 PM"),
                   Trade(at: 1780540200, probability: 0.61, volume: 165237.12, figure: "61%", clock: "Jun 3, 7:30 PM"),
                   Trade(at: 1780540260, probability: 0.61, volume: 66512.75, figure: "61%", clock: "Jun 3, 7:31 PM"),
                   Trade(at: 1780540320, probability: 0.68, volume: 50570.96, figure: "68%", clock: "Jun 3, 7:32 PM"),
                   Trade(at: 1780540380, probability: 0.6, volume: 133208.06, figure: "60%", clock: "Jun 3, 7:33 PM"),
                   Trade(at: 1780540440, probability: 0.59, volume: 251470.42, figure: "59%", clock: "Jun 3, 7:34 PM"),
                   Trade(at: 1780540500, probability: 0.58, volume: 222007.08, figure: "58%", clock: "Jun 3, 7:35 PM"),
                   Trade(at: 1780540560, probability: 0.59, volume: 134403.19, figure: "59%", clock: "Jun 3, 7:36 PM"),
                   Trade(at: 1780540620, probability: 0.56, volume: 205034.05, figure: "56%", clock: "Jun 3, 7:37 PM"),
                   Trade(at: 1780540680, probability: 0.56, volume: 105026.21, figure: "56%", clock: "Jun 3, 7:38 PM"),
                   Trade(at: 1780540740, probability: 0.56, volume: 154506.62, figure: "56%", clock: "Jun 3, 7:39 PM"),
                   Trade(at: 1780540800, probability: 0.51, volume: 194435.86, figure: "51%", clock: "Jun 3, 7:40 PM"),
                   Trade(at: 1780540860, probability: 0.4, volume: 252601.48, figure: "40%", clock: "Jun 3, 7:41 PM"),
                   Trade(at: 1780540920, probability: 0.56, volume: 226049.78, figure: "56%", clock: "Jun 3, 7:42 PM"),
                   Trade(at: 1780540980, probability: 0.58, volume: 166927, figure: "58%", clock: "Jun 3, 7:43 PM"),
                   Trade(at: 1780541040, probability: 0.58, volume: 147028.24, figure: "58%", clock: "Jun 3, 7:44 PM"),
                   Trade(at: 1780541100, probability: 0.58, volume: 108758.93, figure: "58%", clock: "Jun 3, 7:45 PM"),
                   Trade(at: 1780541160, probability: 0.58, volume: 75419.29, figure: "58%", clock: "Jun 3, 7:46 PM"),
                   Trade(at: 1780541220, probability: 0.57, volume: 64109.49, figure: "57%", clock: "Jun 3, 7:47 PM"),
                   Trade(at: 1780541280, probability: 0.44, volume: 234289.6, figure: "44%", clock: "Jun 3, 7:48 PM"),
                   Trade(at: 1780541340, probability: 0.31, volume: 364021.49, figure: "31%", clock: "Jun 3, 7:49 PM"),
                   Trade(at: 1780541400, probability: 0.3, volume: 841160.1, figure: "30%", clock: "Jun 3, 7:50 PM"),
                   Trade(at: 1780541460, probability: 0.31, volume: 664475.38, figure: "31%", clock: "Jun 3, 7:51 PM"),
                   Trade(at: 1780541520, probability: 0.31, volume: 506901.51, figure: "31%", clock: "Jun 3, 7:52 PM"),
                   Trade(at: 1780541580, probability: 0.32, volume: 336015.05, figure: "32%", clock: "Jun 3, 7:53 PM"),
                   Trade(at: 1780541640, probability: 0.3, volume: 188796.66, figure: "30%", clock: "Jun 3, 7:54 PM"),
                   Trade(at: 1780541700, probability: 0.2, volume: 238295.3, figure: "20%", clock: "Jun 3, 7:55 PM"),
                   Trade(at: 1780541760, probability: 0.15, volume: 637759.84, figure: "15%", clock: "Jun 3, 7:56 PM"),
                   Trade(at: 1780541820, probability: 0.2, volume: 478404.93, figure: "20%", clock: "Jun 3, 7:57 PM"),
                   Trade(at: 1780541880, probability: 0.26, volume: 390755.79, figure: "26%", clock: "Jun 3, 7:58 PM"),
                   Trade(at: 1780541940, probability: 0.26, volume: 357102.6, figure: "26%", clock: "Jun 3, 7:59 PM"),
                   Trade(at: 1780542000, probability: 0.35, volume: 429880.82, figure: "35%", clock: "Jun 3, 8:00 PM"),
                   Trade(at: 1780542060, probability: 0.32, volume: 220355.01, figure: "32%", clock: "Jun 3, 8:01 PM"),
                   Trade(at: 1780542120, probability: 0.48, volume: 428155.01, figure: "48%", clock: "Jun 3, 8:02 PM"),
                   Trade(at: 1780542180, probability: 0.48, volume: 391256.81, figure: "48%", clock: "Jun 3, 8:03 PM"),
                   Trade(at: 1780542240, probability: 0.6, volume: 314170.01, figure: "60%", clock: "Jun 3, 8:04 PM"),
                   Trade(at: 1780542300, probability: 0.63, volume: 313692.45, figure: "63%", clock: "Jun 3, 8:05 PM"),
                   Trade(at: 1780542360, probability: 0.3, volume: 313264.7, figure: "30%", clock: "Jun 3, 8:06 PM"),
                   Trade(at: 1780542420, probability: 0.17, volume: 675946.25, figure: "17%", clock: "Jun 3, 8:07 PM"),
                   Trade(at: 1780542480, probability: 0.01, volume: 1261114.22, figure: "1%", clock: "Jun 3, 8:08 PM"),
                   Trade(at: 1780542540, probability: 0.01, volume: 709862.34, figure: "1%", clock: "Jun 3, 8:09 PM"),
                   Trade(at: 1780542600, probability: 0.01, volume: 168247.62, figure: "1%", clock: "Jun 3, 8:10 PM"),
                   Trade(at: 1780542660, probability: 0.01, volume: 97713.8, figure: "1%", clock: "Jun 3, 8:11 PM"),
                   Trade(at: 1780542720, probability: 0.01, volume: 79636.34, figure: "1%", clock: "Jun 3, 8:12 PM"),
                   Trade(at: 1780542780, probability: 0.01, volume: 50136.11, figure: "1%", clock: "Jun 3, 8:13 PM"),
                   Trade(at: 1780542840, probability: 0.01, volume: 49308.51, figure: "1%", clock: "Jun 3, 8:14 PM"),
                   Trade(at: 1780542900, probability: 0.01, volume: 35585.29, figure: "1%", clock: "Jun 3, 8:15 PM"),
                   Trade(at: 1780542960, probability: 0.01, volume: 9919.55, figure: "1%", clock: "Jun 3, 8:16 PM"),
               ],
               early: [
                   Trade(at: 1780374960, probability: 0.64, volume: 1012.32, figure: "64%", clock: "Jun 1, 9:36 PM"),
                   Trade(at: 1780375020, probability: 0.63, volume: 240.96, figure: "63%", clock: "Jun 1, 9:37 PM"),
                   Trade(at: 1780375140, probability: 0.64, volume: 135.96, figure: "64%", clock: "Jun 1, 9:39 PM"),
                   Trade(at: 1780375200, probability: 0.63, volume: 136.1, figure: "63%", clock: "Jun 1, 9:40 PM"),
               ],
               earlyRuns: [[0,1],[2,3]]),
    ]

    private static func domain(_ frame: Frame) -> FieldHistoryDomain10868 {
        switch frame {
        case .before: return FieldHistoryDomain10868(lower: 1_780_529_400, upper: 1_780_532_940)
        case .final: return FieldHistoryDomain10868(lower: 1_780_529_400, upper: 1_780_542_960)
        case .control: return FieldHistoryDomain10868(lower: 1_780_374_960, upper: 1_780_375_200)
        }
    }

    /// The packet's own runs: one unbroken minute run per around-game frame, two Spurs runs in the control.
    private static func runs(_ winner: Winner, _ frame: Frame) -> [[Trade]] {
        switch frame {
        case .before: return [Array(winner.around.prefix(beforeCount))]
        case .final: return [winner.around]
        case .control: return winner.earlyRuns.map { $0.map { winner.early[$0] } }
        }
    }

    private static func series(_ winner: Winner, _ frame: Frame,
                               recorded: FieldHistoryReading10868? = nil,
                               controls: Bool = false) -> FieldHistorySeries10868 {
        let ownerRuns = Self.runs(winner, frame).enumerated().map { index, trades in
            FieldHistoryRun10868(id: "constructed-run:\(winner.ticker):\(frame):\(index)", points: trades.map { trade in
                FieldHistoryPoint10868(id: winner.pointID(trade), x: trade.at, probability: trade.probability,
                                       style: trade.at < listedStart ? .hollow : .filled)
            })
        }
        let before: FieldHistoryReading10868 = frame == .control
            ? .independent(figure: winner.baseline.figure, provenance: winner.baselineProvenance)
            : .observation(pointID: winner.pointID(winner.baseline), figure: winner.baseline.figure,
                           provenance: winner.baselineProvenance)
        let absent: String
        switch frame {
        case .before: absent = "Before the game"
        case .final: absent = "No current probability after the final"
        case .control: absent = "No trade this minute"
        }
        return FieldHistorySeries10868(
            id: winner.ticker, name: winner.name, shape: winner.shape, tint: winner.tint,
            runs: ownerRuns, links: [], labelPointID: nil, before: before, recorded: recorded ?? .absent(words: absent),
            absentWords: "No retained game-winner history",
            choose: controls ? FieldHistoryAction10868(id: "constructed-choose:\(winner.ticker)", label: winner.name,
                                                       spokenLabel: "Show the \(winner.name) original", isAvailable: true) : nil)
    }

    private static func action(_ id: String, _ label: String) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: true)
    }

    private static let windows = FieldHistoryWindows10868(groupLabel: "Game history window", choices: [
        FieldHistoryWindowChoice10868(action: action("constructed-window:match", "Around the game"), isSelected: true),
        FieldHistoryWindowChoice10868(action: action("constructed-window:all", "All captured trades"), isSelected: false),
    ])

    private static func input(_ frame: Frame, series: [FieldHistorySeries10868]? = nil,
                              domain: FieldHistoryDomain10868? = nil,
                              guides: [FieldHistoryGuide10868]? = nil,
                              inspection: FieldHistoryInspection10868? = nil,
                              controls: Bool = false) -> FieldHistoryInput10868 {
        let shown = Self.runs(winners[0], frame).flatMap { $0 }
        let readout: FieldHistoryReadoutIntent10868 = frame == .before
            ? .singleBefore(label: "Before game")
            : .beforeAndInspected(beforeLabel: "Before game", inspectedLabel: "Trade at selected minute")
        let caption: String
        switch frame {
        case .before: caption = "Final hour before the listed start"
        case .final: caption = "Around the game"
        case .control: caption = "Constructed five-minute inspection control"
        }
        return FieldHistoryInput10868(
            title: "Game winner", caption: caption,
            series: series ?? winners.map { Self.series($0, frame, controls: controls) }, selection: .none,
            domain: domain ?? Self.domain(frame), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.25, lines: ["25%"]),
                     FieldHistoryTick10868(value: 0.5, lines: ["50%"]), FieldHistoryTick10868(value: 0.75, lines: ["75%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [shown.first, shown.last].compactMap { $0 }.map { FieldHistoryTick10868(value: $0.at, lines: [$0.clock]) },
            guides: guides ?? [listedStartGuide], breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Trade before listed start", filled: "Trade from listed start"),
            comparisonExplanation: nil,
            notes: ["Each line is its own Kalshi market's minute closes; only adjacent traded minutes connect. Listed start is the schedule, not actual tipoff."],
            summary: "Two game-winner originals on one time axis; circle Knicks, diamond Spurs.",
            plotHeight: 240, unboundReadingWords: unboundWords,
            plotUnavailableWords: "History unavailable", windows: controls ? Self.windows : nil, scale: nil, moreOriginals: nil,
            details: controls ? action("constructed-details", "Original Kalshi markets") : nil, expand: nil,
            inspect: controls ? action("constructed-inspect", "Inspect a trade minute") : nil,
            previous: controls ? action("constructed-previous", "Previous game trade minute") : nil,
            next: controls ? action("constructed-next", "Next game trade minute") : nil,
            inspection: inspection)
    }

    private static func selected(_ winner: Winner, _ trade: Trade) -> FieldHistorySelection10868 {
        .point(id: winner.pointID(trade), spoken: "\(trade.figure), \(winner.provenance(trade))")
    }

    private static func inspection(at x: Double, caption: String,
                                   _ selections: [String: FieldHistorySelection10868],
                                   choices: [FieldHistoryInspectionChoice10868] = []) -> FieldHistoryInspection10868 {
        FieldHistoryInspection10868(x: x, caption: caption, selections: selections, choices: choices,
                                    choicePresentation: .slider(label: "Game trade minute"),
                                    note: "Each original's own trade in this minute; never a neighbouring minute or the other team")
    }

    private static func trade(_ winner: Winner, _ frame: Frame, at x: Double) -> Trade? {
        Self.runs(winner, frame).flatMap { $0 }.first { $0.at == x }
    }

    func testBothWinnerOriginalsKeepEveryAroundGameMinuteInOwnerOrderOnOneMinuteRuns() {
        XCTAssertEqual(Self.winners.map(\.ticker), ["KXNBAGAME-26JUN03NYKSAS-NYK", "KXNBAGAME-26JUN03NYKSAS-SAS"])
        XCTAssertEqual(Self.winners.map { $0.around.count }, [227, 227])
        XCTAssertEqual(Self.winners.map { $0.early.count }, [5, 4])
        let frames: [(Frame, [Int])] = [(.before, [60, 60]), (.final, [227, 227])]
        for (frame, counts) in frames {
            let input = Self.input(frame)
            XCTAssertEqual(input.series.map(\.id), Self.winners.map(\.ticker))
            XCTAssertEqual(input.series.map(\.name), ["Knicks", "Spurs"])
            XCTAssertEqual(input.series.map(\.shape), [.circle, .diamond])
            XCTAssertNotEqual(input.series[0].tint, input.series[1].tint)
            XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.marks($0, in: input).count }, counts)
            for (index, series) in input.series.enumerated() {
                let expected = Self.runs(Self.winners[index], frame).flatMap { $0 }
                let marks = FieldHistoryGeometry10868.marks(series, in: input)
                XCTAssertEqual(marks.map(\.x), expected.map(\.at))
                XCTAssertEqual(marks.map(\.probability), expected.map(\.probability))
                XCTAssertEqual(Set(marks.map(\.id)).count, marks.count)
                XCTAssertTrue(series.links.isEmpty)
                let lines = FieldHistoryGeometry10868.lines(series, in: input)
                XCTAssertEqual(lines.map(\.count), [counts[index]])
                for line in lines {
                    XCTAssertTrue(zip(line, line.dropFirst()).allSatisfy { $1.x - $0.x == 60 })
                }
                XCTAssertEqual(marks.filter { $0.style == .hollow }.count, Self.beforeCount)
                XCTAssertEqual(marks.filter { $0.style == .filled }.count, counts[index] - Self.beforeCount)
            }
            // Solid owner runs only: no dashed comparison is drawn or keyed.
            XCTAssertFalse(FieldHistoryGeometry10868.drawsComparisonLink(input))
            XCTAssertNil(FieldHistoryGeometry10868.comparisonKeyWords(input))
            XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.hollow, in: input))
            XCTAssertEqual(FieldHistoryGeometry10868.drawsStyle(.filled, in: input), frame == .final)
        }
    }

    func testEachWinnerKeepsItsOwnBeforeGameReminderWithNoComplementOrCents() {
        let knicks = Self.winners[0], spurs = Self.winners[1]
        XCTAssertEqual([knicks.baseline.at, spurs.baseline.at], [1_780_532_940, 1_780_532_940])
        XCTAssertLessThan(knicks.baseline.at, Self.listedStart)
        XCTAssertEqual([knicks.baseline.probability, spurs.baseline.probability], [0.37, 0.64])
        XCTAssertEqual([knicks.baseline.clock, spurs.baseline.clock], ["Jun 3, 5:29 PM", "Jun 3, 5:29 PM"])
        XCTAssertEqual(knicks.baseline.probability + spurs.baseline.probability, 1.01, accuracy: 1e-9)
        for winner in Self.winners {
            let last = winner.around[Self.beforeCount - 1]
            XCTAssertEqual([last.at, last.probability], [winner.baseline.at, winner.baseline.probability])
            XCTAssertEqual(last.figure, winner.baseline.figure)
            XCTAssertTrue(winner.around[Self.beforeCount...].allSatisfy { $0.at >= Self.listedStart })
        }
        for frame in [Frame.before, .final, .control] {
            let input = Self.input(frame)
            XCTAssertTrue(input.series.allSatisfy { !Self.excludedValueOriginals.contains($0.id) })
            for (index, series) in input.series.enumerated() {
                let winner = Self.winners[index]
                let slots = FieldHistoryGeometry10868.readoutSlots(series, in: input)
                XCTAssertEqual(slots.count, frame == .before ? 1 : 2)
                XCTAssertEqual(slots[0].label, "Before game")
                XCTAssertEqual(slots[0].display, .figure(winner.baseline.figure, provenance: winner.baselineProvenance))
                let drawsReminder = FieldHistoryGeometry10868.marks(series, in: input).contains { $0.x == winner.baseline.at }
                XCTAssertEqual(drawsReminder, frame != .control)
            }
        }
        // Outside the control window the reminder is independently admitted with its real clock, never a drawn point.
        XCTAssertGreaterThan(knicks.baseline.at, Self.domain(.control).upper)
        // Spurs is never derived as 1 − Knicks: the retained minute pairs keep their own sums.
        XCTAssertNotEqual(spurs.baseline.probability, 1 - knicks.baseline.probability)
        let unpaired = zip(knicks.around, spurs.around).filter { abs($0.probability + $1.probability - 1) > 1e-9 }
        XCTAssertEqual(unpaired.count, 182)
        XCTAssertTrue(zip(knicks.around, spurs.around).allSatisfy { $0.at == $1.at })
        let figures = Self.winners.flatMap { $0.around + $0.early + [$0.baseline] }.map(\.figure)
        XCTAssertTrue(figures.allSatisfy { $0.hasSuffix("%") && !$0.contains("¢") })
    }

    func testTheListedStartGuideShowsOnlyInTheFinalFrameAndRetimesNoTrade() {
        let before = Self.input(.before), final = Self.input(.final)
        XCTAssertEqual(Self.listedStartGuide.x, Self.listedStart)
        XCTAssertTrue(FieldHistoryGeometry10868.placedGuides(before).isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.placedGuides(final), [Self.listedStartGuide])
        // The before frame ends at its own last trade strictly before the listed start, not at the start.
        XCTAssertEqual(before.domain.upper, 1_780_532_940)
        XCTAssertLessThan(before.domain.upper, Self.listedStart)
        let unguided = Self.input(.final, guides: [])
        for (guided, plain) in zip(final.series, unguided.series) {
            XCTAssertEqual(FieldHistoryGeometry10868.marks(guided, in: final), FieldHistoryGeometry10868.marks(plain, in: unguided))
            XCTAssertEqual(FieldHistoryGeometry10868.lines(guided, in: final), FieldHistoryGeometry10868.lines(plain, in: unguided))
        }
        let rect = CGRect(x: 0, y: 0, width: 1356, height: 100)
        let guideX = FieldHistoryGeometry10868.xPosition(Self.listedStart, domain: final.domain, in: rect)
        for (index, series) in final.series.enumerated() {
            let winner = Self.winners[index]
            let marks = FieldHistoryGeometry10868.marks(series, in: final)
            XCTAssertEqual(marks.filter { $0.x < Self.listedStart }.count, Self.beforeCount)
            guard let atStart = marks.first(where: { $0.x == Self.listedStart }),
                  let reminder = marks.first(where: { $0.x == winner.baseline.at }) else { XCTFail(winner.name); continue }
            XCTAssertEqual(atStart.id, winner.pointID(winner.around[Self.beforeCount]))
            XCTAssertEqual(atStart.probability, winner.around[Self.beforeCount].probability)
            XCTAssertEqual(FieldHistoryGeometry10868.position(atStart, in: final, rect: rect).x, guideX, accuracy: 1e-9)
            XCTAssertLessThan(FieldHistoryGeometry10868.position(reminder, in: final, rect: rect).x, guideX)
        }
    }

    func testTheRealEarlyGapStaysOpenAndOnlyTheKnicksTradeIsReadAt1780375080() {
        let knicks = Self.winners[0], spurs = Self.winners[1], at: Double = 1_780_375_080
        guard let knicksTrade = Self.trade(knicks, .control, at: at) else { return XCTFail("Knicks 9:38 PM trade") }
        XCTAssertNil(Self.trade(spurs, .control, at: at))
        XCTAssertEqual([knicksTrade.figure, knicksTrade.clock], ["37%", "Jun 1, 9:38 PM"])
        let caption = "Jun 1, 9:38 PM PT minute"
        let series = [Self.series(knicks, .control, recorded: knicks.reading(knicksTrade)), Self.series(spurs, .control)]
        let input = Self.input(.control, series: series, inspection: Self.inspection(at: at, caption: caption, [
            knicks.ticker: Self.selected(knicks, knicksTrade), spurs.ticker: .absent(words: "No trade this minute"),
        ]))
        XCTAssertEqual(series.map { FieldHistoryGeometry10868.marks($0, in: input).count }, [5, 4])
        XCTAssertEqual(FieldHistoryGeometry10868.lines(series[0], in: input).map(\.count), [5])
        XCTAssertEqual(FieldHistoryGeometry10868.lines(series[1], in: input).map(\.count), [2, 2])
        XCTAssertFalse(FieldHistoryGeometry10868.lines(series[1], in: input).contains { line in
            line.contains { $0.x < at } && line.contains { $0.x > at }
        })
        XCTAssertEqual(FieldHistoryGeometry10868.cursor(input), at)
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(series[0], in: input)?.id, knicks.pointID(knicksTrade))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series[1], in: input))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series[0], in: input).map(\.display), [
            .figure("37%", provenance: knicks.baselineProvenance),
            .figure("37%", provenance: "Jun 1, 9:38 PM PT · Kalshi minute close"),
        ])
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series[1], in: input).map(\.display), [
            .figure("64%", provenance: spurs.baselineProvenance), .words("No trade this minute"),
        ])
        XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(input),
                       "\(caption); Knicks: 37%, Jun 1, 9:38 PM PT · Kalshi minute close; Spurs: No trade this minute")
        // Neither a neighbouring Spurs minute (63% at 9:37 PM) nor the Knicks trade ever stands in.
        let neighbour = spurs.early[1]
        XCTAssertEqual([neighbour.figure, neighbour.clock], ["63%", "Jun 1, 9:37 PM"])
        let borrowed = [series[0], Self.series(spurs, .control, recorded: spurs.reading(neighbour))]
        let strayIDs: [FieldHistorySelection10868] = [
            .point(id: "constructed-point:\(spurs.ticker):\(Int(at))", spoken: "63%"),
            .point(id: knicks.pointID(knicksTrade), spoken: "37%"),
        ]
        for stray in strayIDs {
            let probe = Self.input(.control, series: borrowed, inspection: Self.inspection(at: at, caption: caption, [
                knicks.ticker: Self.selected(knicks, knicksTrade), spurs.ticker: stray,
            ]))
            XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(borrowed[1], in: probe))
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(borrowed[1], in: probe)[1].display, .words(Self.unboundWords))
            XCTAssertEqual(FieldHistoryGeometry10868.marks(borrowed[1], in: probe).count, 4)
        }
    }

    func testAHeldTradeMinuteSurvivesAChangedWindowWithoutABorrowedOrReplacedReading() {
        let knicks = Self.winners[0], spurs = Self.winners[1], held: Double = 1_780_532_940
        guard let knicksHeld = Self.trade(knicks, .before, at: held), let spursHeld = Self.trade(spurs, .before, at: held),
              let knicksLast = knicks.around.last else { return XCTFail("Held 5:29 PM trades") }
        let caption = "Jun 3, 5:29 PM PT minute"
        let selections: [String: FieldHistorySelection10868] = [
            knicks.ticker: Self.selected(knicks, knicksHeld), spurs.ticker: Self.selected(spurs, spursHeld),
        ]
        // The ring stays on the same own minute when the window grows from before to final.
        for frame in [Frame.before, .final] {
            let input = Self.input(frame, inspection: Self.inspection(at: held, caption: caption, selections))
            XCTAssertEqual(FieldHistoryGeometry10868.cursor(input), held)
            XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.inspectedPoint($0, in: input)?.id },
                           [knicks.pointID(knicksHeld), spurs.pointID(spursHeld)])
            XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.inspectedPoint($0, in: input)?.probability }, [0.37, 0.64])
        }
        let shown = [Self.series(knicks, .final, recorded: knicks.reading(knicksHeld)),
                     Self.series(spurs, .final, recorded: spurs.reading(spursHeld))]
        let final = Self.input(.final, series: shown, inspection: Self.inspection(at: held, caption: caption, selections))
        XCTAssertEqual(shown.map { FieldHistoryGeometry10868.readoutSlots($0, in: final)[1].display }, [
            .figure("37%", provenance: "Jun 3, 5:29 PM PT · Kalshi minute close"),
            .figure("64%", provenance: "Jun 3, 5:29 PM PT · Kalshi minute close"),
        ])
        // The chart never turns the cursor into a headline; the score and forecast are not its input.
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(final), FieldHistorySelectedSummary10868.none)
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(final), [.selectionWords, .key])
        XCTAssertEqual([final.title, final.caption], ["Game winner", "Around the game"])
        // A newer reading (the 8:16 PM last trade) never replaces the held minute.
        var replaced = shown
        replaced[0] = Self.series(knicks, .final, recorded: knicks.reading(knicksLast))
        let newer = Self.input(.final, series: replaced, inspection: Self.inspection(at: held, caption: caption, selections))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(replaced[0], in: newer)[1].display, .words(Self.unboundWords))
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(replaced[1], in: newer)[1].display,
                       .figure("64%", provenance: "Jun 3, 5:29 PM PT · Kalshi minute close"))
        // Moved to a window without that minute, it is not drawn and not borrowed from the Knicks' early 37% trade.
        let elsewhere = Self.input(.control, series: [Self.series(knicks, .control, recorded: knicks.reading(knicksHeld)),
                                                      Self.series(spurs, .control, recorded: spurs.reading(spursHeld))],
                                   inspection: Self.inspection(at: held, caption: caption, selections))
        XCTAssertNil(FieldHistoryGeometry10868.cursor(elsewhere))
        for series in elsewhere.series {
            XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series, in: elsewhere))
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: elsewhere)[1].display, .words(Self.unboundWords))
        }
    }

    func testTheFinalStopsAtTheLastRealTradeWithNoSettlementExtensionOrCurrentProbability() {
        let knicks = Self.winners[0], spurs = Self.winners[1]
        guard let knicksLast = knicks.around.last, let spursLast = spurs.around.last else { return XCTFail("Final trades") }
        XCTAssertEqual([knicksLast.at, spursLast.at], [1_780_542_960, 1_780_542_960])
        XCTAssertEqual([knicksLast.probability, spursLast.probability], [0.99, 0.01])
        XCTAssertEqual([knicksLast.figure, spursLast.figure, knicksLast.clock], ["99%", "1%", "Jun 3, 8:16 PM"])
        let input = Self.input(.final)
        XCTAssertEqual(input.domain.upper, knicksLast.at)
        for series in input.series {
            let marks = FieldHistoryGeometry10868.marks(series, in: input)
            XCTAssertEqual(marks.last?.x, knicksLast.at)
            XCTAssertTrue(marks.allSatisfy { $0.probability > 0 && $0.probability < 1 && $0.x <= input.domain.upper })
            XCTAssertEqual(series.recorded, .absent(words: "No current probability after the final"))
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: input)[1].display, .words(Self.unboundWords))
        }
        XCTAssertEqual(input.series.compactMap { FieldHistoryGeometry10868.marks($0, in: input).last?.probability }, [0.99, 0.01])
        // An owner domain reaching past the last trade (toward a schedule or "now") draws nothing new.
        let widened = Self.input(.final, domain: FieldHistoryDomain10868(lower: 1_780_529_400, upper: 1_780_546_560))
        for (series, plain) in zip(widened.series, input.series) {
            XCTAssertEqual(FieldHistoryGeometry10868.marks(series, in: widened).map(\.x),
                           FieldHistoryGeometry10868.marks(plain, in: input).map(\.x))
            XCTAssertEqual(FieldHistoryGeometry10868.lines(series, in: widened).map(\.count), [227])
        }
        // The last trade is still exactly inspectable as a historical minute, never as a current chance.
        let shown = [Self.series(knicks, .final, recorded: knicks.reading(knicksLast)),
                     Self.series(spurs, .final, recorded: spurs.reading(spursLast))]
        let inspected = Self.input(.final, series: shown, inspection: Self.inspection(at: knicksLast.at, caption: "Jun 3, 8:16 PM PT minute", [
            knicks.ticker: Self.selected(knicks, knicksLast), spurs.ticker: Self.selected(spurs, spursLast),
        ]))
        XCTAssertEqual(shown.map { FieldHistoryGeometry10868.readoutSlots($0, in: inspected)[1].label },
                       ["Trade at selected minute", "Trade at selected minute"])
        XCTAssertEqual(shown.map { FieldHistoryGeometry10868.readoutSlots($0, in: inspected)[1].display }, [
            .figure("99%", provenance: "Jun 3, 8:16 PM PT · Kalshi minute close"),
            .figure("1%", provenance: "Jun 3, 8:16 PM PT · Kalshi minute close"),
        ])
    }

    func testWindowOriginalAndInspectionControlsHandBackExactOwnerIDsAndStayStaticWithoutCallbacks() {
        let knicks = Self.winners[0], at: Double = 1_780_375_080
        guard let knicksTrade = Self.trade(knicks, .control, at: at) else { return XCTFail("Knicks 9:38 PM trade") }
        // Knicks traded in every control minute, so its own clocks name the constructed choices.
        let choices = knicks.early.map { trade in
            FieldHistoryInspectionChoice10868(id: "constructed-choice:\(Int(trade.at))", lines: [trade.clock],
                                              spoken: "Trade minute \(trade.clock) PT", isSelected: trade.at == at)
        }
        let input = Self.input(.control, inspection: Self.inspection(at: at, caption: "Jun 1, 9:38 PM PT minute", [
            knicks.ticker: Self.selected(knicks, knicksTrade),
        ], choices: choices), controls: true)
        guard let windows = input.windows else { return XCTFail("Window choices") }
        let ids = FieldHistoryGeometry10868.actions(input).map(\.id)
        XCTAssertEqual(ids.count, 8)
        XCTAssertEqual(Set(ids).count, ids.count)
        // With a callback every exact owner id is handed back.
        XCTAssertEqual(windows.choices.map { FieldHistoryGeometry10868.controlState($0.action, informative: true, hasCallback: true, in: input) },
                       [.live(id: "constructed-window:match"), .live(id: "constructed-window:all")])
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.chooseState($0, hasCallback: true, in: input) },
                       Self.winners.map { FieldHistoryControlState10868.live(id: "constructed-choose:\($0.ticker)") })
        for (pure, id) in [(input.details, "constructed-details"), (input.inspect, "constructed-inspect"),
                           (input.previous, "constructed-previous"), (input.next, "constructed-next")] {
            XCTAssertEqual(FieldHistoryGeometry10868.controlState(pure, informative: false, hasCallback: true, in: input), .live(id: id))
        }
        XCTAssertEqual(FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: true, in: input), "constructed-next")
        XCTAssertEqual(FieldHistoryGeometry10868.sliderIndex(choices), 2)
        XCTAssertEqual(FieldHistoryGeometry10868.sliderChoiceID(at: 3, choices: choices), "constructed-choice:1780375140")
        XCTAssertNil(FieldHistoryGeometry10868.sliderChoiceID(at: 2, choices: choices))
        XCTAssertEqual(choices.map { FieldHistoryGeometry10868.liveChoiceID($0, among: choices) },
                       knicks.early.map { "constructed-choice:\(Int($0.at))" })
        // A callback-free static view keeps the informative window and original choices, hides pure actions.
        XCTAssertEqual(windows.choices.map { FieldHistoryGeometry10868.controlState($0.action, informative: true, hasCallback: false, in: input) },
                       [.shownStatic, .shownStatic])
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.chooseState($0, hasCallback: false, in: input) },
                       [.shownStatic, .shownStatic])
        for pure in [input.details, input.inspect, input.previous, input.next] {
            XCTAssertEqual(FieldHistoryGeometry10868.controlState(pure, informative: false, hasCallback: false, in: input), .hidden)
        }
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: false, in: input))
        let view = FieldProbabilityHistoryPresentation10868(input: input)
        XCTAssertNil(view.onAction)
        XCTAssertNil(view.onInspectionChoice)
        XCTAssertNil(view.onPlotPosition)
        XCTAssertEqual(view.input, input)
    }
}
