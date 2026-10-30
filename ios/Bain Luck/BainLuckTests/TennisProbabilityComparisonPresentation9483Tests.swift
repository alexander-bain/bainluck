import XCTest
@testable import Bain_Luck

/// #9483 tennis — **a tennis reader compares both players' earlier and
/// selected recorded chances at equal weight, each with its own mark, without
/// hunting for a small baseline.**
///
/// `TennisProbabilityComparisonPresentation9483` re-presents what
/// `TennisReadingPanel9483` already prints. These tests pin that it prints
/// the same things: the pairs `panelParts` chooses, the figures `labels(for:)`
/// prints, the marks `home` / `awayValue(for:)` place and the headings the
/// dating helpers write. The fixture is `TennisRecordedChanceBeforeScheduled
/// Start9483Tests`'s (Zverev v Shelton, scheduled 2026-09-13 18:00Z, a 160-min
/// break); cases marked CONTROL are synthetic edges.
///
/// What these cannot show: pixel fit, mark overlap on screen, or what
/// VoiceOver actually reads. Those are Native's renders and device checks.
/// Prepared with the view; NOT_RUN until Native's Apple run.
@MainActor
final class TennisProbabilityComparisonPresentation9483Tests: XCTestCase {
    private typealias R = TennisChartReading9483
    private typealias P = TennisProbabilityComparisonPresentation9483

    /// 2026-09-13T18:00:00Z — the scheduled start.
    private let start = Date(timeIntervalSince1970: 1_789_322_400)
    private let utc = TimeZone(identifier: "UTC")!
    private let us = Locale(identifier: "en_US")

    private func at(_ minutes: Double) -> Date { start.addingTimeInterval(minutes * 60) }

    private func point(_ minutes: Double, _ p: Double, source: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: at(minutes), probability: p, source: source)
    }

    private func stamp(_ minutes: Double) -> String {
        at(minutes).ISO8601Format()
    }

    /// Opening −180 min, baseline −60, a run from the start, the break, a
    /// second run. The third value is the away side a consensus row supplies.
    private let rows: [(Double, Double, Double)] = [
        (-180, 0.5758, 0.4242), (-60, 0.5599, 0.4401), (0, 0.60, 0.35),
        (10, 0.62, 0.38), (20, 0.64, 0.36), (180, 0.90, 0.10), (190, 0.9772, 0.0227),
    ]

    private func decode(eventId: Int, history: String, aggregateLine: String?) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let line = aggregateLine.map { #","aggregate_line":[\#($0)]"# } ?? ""
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(eventId),"home_team":"Alexander Zverev","away_team":"Ben Shelton",
         "status":"live","history":[\(history)]\(line)}
        """.utf8))
    }

    private func history() throws -> EventHistoryResponse {
        let line = rows.map { #"{"timestamp":"\#(stamp($0.0))","home_probability":\#($0.1)}"# }
            .joined(separator: ",")
        return try decode(eventId: 4242, history: "", aggregateLine: line)
    }

    private func consensusHistory(rows: [(Double, Double, Double?)]) throws -> EventHistoryResponse {
        let served = rows.map { row -> String in
            let away = row.2.map { "\($0)" } ?? "null"
            return #"{"timestamp":"\#(stamp(row.0))","home_probability":\#(row.1),"away_probability":\#(away),"bookmaker_count":7}"#
        }.joined(separator: ",")
        return try decode(eventId: 4242, history: served, aggregateLine: nil)
    }

    private func series(source: String = "aggregate", history: EventHistoryResponse? = nil) throws -> R.Series {
        try XCTUnwrap(R.series(
            eventId: 4242, points: rows.map { point($0.0, $0.1, source: source) }, source: source,
            scheduledStart: start, gameStart: start, finished: false, history: try history ?? self.history()))
    }

    private func consensus() throws -> R.Series {
        try series(source: "consensus", history: try consensusHistory(rows: rows.map { ($0.0, $0.1, $0.2) }))
    }

    private func reading(_ shown: R.Shown) -> R.Reading? {
        if case .reading(let reading, _) = shown { return reading }
        return nil
    }

    private func held(_ s: R.Series, _ minutes: Double) throws -> R.Reading {
        try XCTUnwrap(reading(s.resolve(s.inspect(at: at(minutes)))))
    }

    private func plain(_ s: String) -> String {
        s.replacingOccurrences(of: "\u{202F}", with: " ").replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    private func model(_ shown: R.Shown, baseline: R.Reading?, offersLatest: Bool = false,
                       now: Date? = nil) -> P.Model {
        P.model(shown: shown, baseline: baseline, scheduledStart: start,
                homeName: "Alexander Zverev", awayName: "Ben Shelton", offersLatest: offersLatest,
                dating: P.Dating(now: now ?? start, timeZone: utc, locale: us))
    }

    // MARK: - Both players, both phases, the existing figures

    func testTheBlendPairPrintsBothPlayersEarlierAndRecordedFigures() throws {
        let s = try series()
        let baseline = try XCTUnwrap(s.baseline)
        let recorded = try held(s, 0)
        let m = model(.reading(recorded, held: true), baseline: baseline)
        XCTAssertEqual(m.lines.map(\.phase), [.earlier, .recorded])
        XCTAssertEqual(m.lines.map { plain($0.text) },
                       ["Before scheduled start · 5:00 PM", "Recorded chance · 6:00 PM"])
        XCTAssertEqual(m.sides.map(\.name), ["Alexander Zverev", "Ben Shelton"], "full names, home first")
        XCTAssertEqual(m.sides.map { $0.figures.map(\.phase) }, [[.earlier, .recorded], [.earlier, .recorded]])
        XCTAssertEqual(m.sides[0].figures.map(\.printed), ["56%", "60%"])
        XCTAssertEqual(m.sides[1].figures.map(\.printed), ["44%", "40%"])
        // Every figure is `labels(for:)`'s string, never re-rounded here.
        for (i, r) in [baseline, recorded].enumerated() {
            XCTAssertEqual(m.sides[0].figures[i].printed, R.labels(for: r).home)
            XCTAssertEqual(m.sides[1].figures[i].printed, R.labels(for: r).away)
        }
        // Marks sit at the readings' own values: home, and the blend's complement.
        XCTAssertEqual(m.sides[0].figures.map(\.position), [0.5599, 0.60])
        XCTAssertEqual(try XCTUnwrap(m.sides[1].figures[0].position), 0.4401, accuracy: 1e-12)
        XCTAssertEqual(try XCTUnwrap(m.sides[1].figures[1].position), 0.40, accuracy: 1e-12)
        XCTAssertFalse(m.showsLatest)
    }

    /// The consensus aggregates away apart from home, so its away figures are
    /// the supplied 44% / 35%, not 1 − home.
    func testTheConsensusAwaySidePrintsAndSitsAsSuppliedNotAsAComplement() throws {
        let s = try consensus()
        let baseline = try XCTUnwrap(s.baseline)
        let recorded = try held(s, 0)
        XCTAssertEqual(recorded.away, 0.35, "fixture: the consensus row supplies its own away side")
        let away = model(.reading(recorded, held: true), baseline: baseline).sides[1]
        XCTAssertEqual(away.figures.map(\.printed), ["44%", "35%"], "the supplied away side was rewritten as 1 − home")
        XCTAssertEqual(away.figures.map(\.position), [0.4401, 0.35])
        // CONTROL — the blend at the same minute prints its complement, so the
        // difference above is the source contract, not the presentation.
        let blend = try series()
        let blended = model(.reading(try held(blend, 0), held: true), baseline: blend.baseline).sides[1]
        XCTAssertEqual(blended.figures.map(\.printed), ["44%", "40%"])
    }

    func testAnAwaySideTheSourceNeverSuppliedStaysAbsentAndIsSpokenAsUnavailable() throws {
        // A venue line supplies no away side at all.
        let venue = try series(source: "kalshi")
        let m = model(.reading(try held(venue, 0), held: true), baseline: try XCTUnwrap(venue.baseline))
        XCTAssertEqual(m.sides[1].figures, [], "a venue line's away side was manufactured from home")
        XCTAssertEqual(plain(m.sides[1].spoken),
                       "Ben Shelton: Before scheduled start · 5:00 PM, unavailable; Recorded chance · 6:00 PM, unavailable")
        XCTAssertEqual(m.sides[0].figures.map(\.printed), ["56%", "60%"], "control: home still prints both")
        // A consensus time with no served row: its supplied baseline stays,
        // the recorded away side is absent, never a neighbour's.
        let books = try consensus()
        let pushed = books.reading(for: point(21, 0.63, source: "consensus"))
        XCTAssertNil(pushed.away, "fixture: no row is served at 6:21")
        let partial = model(.reading(pushed, held: true), baseline: try XCTUnwrap(books.baseline)).sides[1]
        XCTAssertEqual(partial.figures.map(\.phase), [.earlier])
        XCTAssertEqual(partial.figures.map(\.printed), ["44%"])
        XCTAssertTrue(plain(partial.spoken).hasSuffix("Recorded chance · 6:21 PM, unavailable"), partial.spoken)
    }

    /// Wherever a figure prints, its mark is placed; wherever none prints,
    /// no mark is — the existing printed/plotted agreement, per side.
    func testAFigureAndItsMarkAppearTogetherForEverySource() throws {
        let books = try consensus()
        let cases: [(R.Series, R.Reading)] = [
            (try series(), try held(try series(), 190)),
            (books, try held(books, 0)),
            (books, books.reading(for: point(21, 0.63, source: "consensus"))),
            (try series(source: "kalshi"), try held(try series(source: "kalshi"), 10)),
        ]
        for (s, r) in cases {
            for side in model(.reading(r, held: true), baseline: s.baseline).sides {
                for figure in side.figures {
                    XCTAssertFalse(figure.printed.isEmpty, "\(r.source) printed an empty figure")
                    XCTAssertNotNil(figure.position, "\(r.source) printed \(figure.printed) with no mark")
                }
            }
        }
    }

    // MARK: - The existing pair semantics

    func testTheSameReadingNeverPrintsAsBothEarlierAndRecorded() throws {
        let s = try series()
        let baseline = try XCTUnwrap(s.baseline)
        let m = model(.reading(baseline, held: true), baseline: baseline)
        XCTAssertEqual(m.lines.map(\.phase), [.recorded])
        XCTAssertEqual(plain(m.lines[0].text), "Recorded chance before scheduled start · 5:00 PM")
        XCTAssertEqual(m.sides.map { $0.figures.map(\.phase) }, [[.recorded], [.recorded]],
                       "the same pair printed twice")
        // CONTROL — any other reading keeps the baseline as its own figure.
        let later = model(.reading(try held(s, 10), held: true), baseline: baseline)
        XCTAssertEqual(later.lines.map(\.phase), [.earlier, .recorded])
    }

    func testABreakOrAnUnavailableSelectionKeepsTheSeparatelyAdmittedBaseline() throws {
        let s = try series()
        let baseline = try XCTUnwrap(s.baseline)
        let gap = model(s.resolve(s.inspect(at: at(100))), baseline: baseline, offersLatest: true)
        XCTAssertEqual(gap.lines.map(\.phase), [.earlier, nil])
        XCTAssertEqual(plain(gap.lines[1].text), "No recorded chance at 7:40 PM")
        XCTAssertEqual(gap.sides.map { $0.figures.map(\.phase) }, [[.earlier], [.earlier]],
                       "a neighbour filled the break")
        XCTAssertEqual(gap.sides.map { $0.figures.map(\.printed) }, [["56%"], ["44%"]])
        XCTAssertTrue(plain(gap.sides[0].spoken).hasSuffix("No recorded chance at 7:40 PM"))
        XCTAssertTrue(gap.showsLatest)

        let unavailable = model(.unavailable, baseline: baseline, offersLatest: true)
        XCTAssertEqual(unavailable.lines.last, P.Line(phase: nil, text: R.unavailableText))
        XCTAssertEqual(unavailable.sides.map { $0.figures.map(\.phase) }, [[.earlier], [.earlier]])
        XCTAssertTrue(unavailable.sides[1].spoken.hasSuffix(R.unavailableText))

        // CONTROL — with no baseline either, no names head an empty comparison.
        let bare = model(.unavailable, baseline: nil, offersLatest: true)
        XCTAssertEqual(bare.sides, [])
        XCTAssertEqual(bare.lines, [P.Line(phase: nil, text: R.unavailableText)])
        XCTAssertTrue(bare.showsLatest)
    }

    // MARK: - Qualified, dated, and claims nothing more

    func testEveryHeadingIsTheExistingHelpersQualifiedAndDated() throws {
        let s = try series()
        let baseline = try XCTUnwrap(s.baseline)
        let late = try held(s, 190)
        let later = start.addingTimeInterval(3 * 86_400)
        let archived = model(.reading(late, held: true), baseline: baseline, now: later)
        XCTAssertEqual(archived.lines.map(\.text), [
            R.baselineHeading(for: baseline, now: later, timeZone: utc, locale: us),
            R.heading(for: late, scheduledStart: start, now: later, timeZone: utc, locale: us),
        ])
        XCTAssertTrue(plain(archived.lines[1].text).hasPrefix("Recorded chance · Sep 13"), archived.lines[1].text)
        // A recorded chance before the scheduled start says so; the earlier
        // figure keeps its own heading beside it.
        let opening = model(.reading(try held(s, -180), held: true), baseline: baseline)
        XCTAssertEqual(opening.lines.map { plain($0.text) },
                       ["Before scheduled start · 5:00 PM", "Recorded chance before scheduled start · 3:00 PM"])

        let gap = model(.gap(at(100)), baseline: baseline)
        let printed = [archived, opening, gap].flatMap { $0.lines.map(\.text) + $0.sides.map(\.spoken) }
        for claim in ["in game", "In game", "pre-match", "Pre-match", "regame", "Live", "live",
                      "Current", "current", "first serve", "Final"] {
            XCTAssertFalse(printed.contains { $0.contains(claim) }, claim)
        }
    }

    /// VoiceOver hears the player, each dated basis and exactly the figure
    /// printed under it — never the unrounded value.
    func testEachPlayersSpokenLineIsThePrintedFiguresUnderTheirHeadings() throws {
        let s = try series()
        let baseline = try XCTUnwrap(s.baseline)
        let late = try held(s, 190)
        let m = model(.reading(late, held: true), baseline: baseline)
        XCTAssertEqual(plain(m.sides[0].spoken),
                       plain("Alexander Zverev: Before scheduled start · 5:00 PM, 56%; Recorded chance · 9:10 PM, \(R.labels(for: late).home)"))
        XCTAssertEqual(plain(m.sides[1].spoken),
                       plain("Ben Shelton: Before scheduled start · 5:00 PM, 44%; Recorded chance · 9:10 PM, \(R.labels(for: late).away)"))
        for raw in ["0.9772", "97.7", "0.5599", "55.99"] {
            XCTAssertFalse(m.sides.contains { $0.spoken.contains(raw) }, raw)
        }
    }

    // MARK: - Marks: equal and endpoint values stay distinguishable

    /// CONTROL (synthetic): an equal earlier and recorded pair, and the two
    /// ends of the rail. Arithmetic only — not a claim about pixels on screen.
    func testEqualAndEndpointProbabilitiesKeepDistinguishableUnclippedMarks() {
        let width: CGFloat = 150
        XCTAssertEqual(P.markX(0, width: width) - P.ringDiameter / 2, 0, accuracy: 1e-9, "a 0% mark leaves the track")
        XCTAssertEqual(P.markX(1, width: width) + P.ringDiameter / 2, width, accuracy: 1e-9, "a 100% mark leaves the track")
        XCTAssertEqual(P.markX(0.5, width: width), width / 2, accuracy: 1e-9)
        XCTAssertLessThan(P.dotDiameter, P.ringDiameter - 2 * P.ringLine,
                          "an equal recorded dot must sit inside the ring's stroke, not cover it")

        let earlier = R.Reading(eventId: 1, source: "aggregate", date: at(-60), home: 0.5, away: nil)
        let recorded = R.Reading(eventId: 1, source: "aggregate", date: at(10), home: 0.5, away: nil)
        let equal = model(.reading(recorded, held: true), baseline: earlier)
        XCTAssertEqual(equal.sides.map { $0.figures.map(\.phase) }, [[.earlier, .recorded], [.earlier, .recorded]],
                       "an equal value is a second reading, not a duplicate")
        XCTAssertEqual(equal.sides[0].figures.map(\.position), [0.5, 0.5])

        let certain = R.Reading(eventId: 1, source: "aggregate", date: at(20), home: 1.0, away: nil)
        let end = model(.reading(certain, held: true), baseline: earlier)
        XCTAssertEqual(end.sides[0].figures.last?.printed, R.labels(for: certain).home)
        XCTAssertEqual(end.sides[1].figures.last?.printed, R.labels(for: certain).away)
        XCTAssertEqual(end.sides[0].figures.last?.position, 1.0)
        XCTAssertEqual(end.sides[1].figures.last?.position, 0.0)
    }

    // MARK: - Show latest stays the host's

    func testShowLatestIsTheHostsOfferAndItsActionIsTheHostsClosure() throws {
        let s = try series()
        let baseline = try XCTUnwrap(s.baseline)
        let shown = R.Shown.reading(try held(s, 10), held: true)
        XCTAssertTrue(model(shown, baseline: baseline, offersLatest: true).showsLatest)
        XCTAssertFalse(model(shown, baseline: baseline, offersLatest: false).showsLatest,
                       "the presentation offered Show latest on its own")
        var asked = 0
        let view = P(shown: shown, baseline: baseline, scheduledStart: start, homeName: "Alexander Zverev",
                     awayName: "Ben Shelton", colors: nil, expanded: true, offersLatest: true,
                     onShowLatest: { asked += 1 })
        view.onShowLatest()
        XCTAssertEqual(asked, 1)
        XCTAssertEqual(view.shown, shown, "control: the view holds no selection of its own to move")
    }

    // MARK: - Source scans (the view's code, comments removed)

    private let componentPath = "Bain Luck/Components/TennisProbabilityComparisonPresentation9483.swift"

    private func codeOnly(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false).map { line -> String in
                guard let comment = line.range(of: "//") else { return String(line) }
                return String(line[..<comment.lowerBound])
            }.joined(separator: "\n")
    }

    /// Both phases render through one figure view at one type. A source
    /// scan: it shows equal styling was written, not how it renders.
    func testBothFiguresShareOneRendererAndOneType() throws {
        let code = try codeOnly(componentPath)
        let flat = code.filter { !$0.isWhitespace }
        XCTAssertEqual(flat.components(separatedBy: "Text(figure.printed)").count - 1, 1)
        XCTAssertTrue(flat.contains(
            "Text(figure.printed).font(.system(size:expanded?expandedFigureSize:figureSize,weight:.bold)).monospacedDigit()"))
        XCTAssertTrue(flat.contains("@ScaledMetric(relativeTo:.callout)varfigureSize:CGFloat=18"))
        for shrink in [".subheadline.bold()", ".title3.bold()", "minimumScaleFactor", ".lineLimit(", "truncationMode"] {
            XCTAssertFalse(code.contains(shrink), shrink)
        }
    }

    func testShowLatestKeepsItsTargetAndFollowsTheComparison() throws {
        let flat = try codeOnly(componentPath).filter { !$0.isWhitespace }
        XCTAssertTrue(flat.contains(
            "ifmodel.showsLatest{Button(TennisChartReading9483.showLatestText,action:onShowLatest).font(.caption).frame(minHeight:44,alignment:.leading)}"))
        let panels = try XCTUnwrap(flat.range(of: "if!model.sides.isEmpty{players(model.sides)}"))
        let latest = try XCTUnwrap(flat.range(of: "ifmodel.showsLatest{"))
        XCTAssertLessThan(panels.lowerBound, latest.lowerBound, "Show latest moved above the comparison")
    }

    /// The view owns no pin, selection, subscription, clock, formatter or
    /// gesture, and extends nothing it consumes.
    func testTheViewOwnsNoStateClockFormatterOrExtension() throws {
        let code = try codeOnly(componentPath)
        for owned in ["TennisReadingPin9483", "holdLatest", "OddsChartSelection", "@State", "@ObservedObject",
                      "@StateObject", "@Published", "ObservableObject", "import Combine", "onReceive", "URLSession",
                      "Timer", "Date()", "DispatchQueue", ".task", "Gesture", "extension ",
                      "formatted(", "NumberFormatter", "DateFormatter", "printedLabels(", "formatProbability(",
                      "* 100", "1 - ", "1.0 - ", "UIKit", "UIColor", "Series"] {
            XCTAssertFalse(code.contains(owned), owned)
        }
        for delegated in ["TennisChartReading9483.panelParts(", "TennisChartReading9483.labels(for:",
                          "TennisChartReading9483.awayValue(for:", "TennisChartReading9483.heading(for:",
                          "TennisChartReading9483.baselineHeading(for:", "TennisChartReading9483.time("] {
            XCTAssertTrue(code.contains(delegated), delegated)
        }
    }
}
