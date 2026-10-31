import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the postponed match screen (`void`), arrangement only, over
/// CONSTRUCTED owner inputs.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// THE SPECIMEN. Levante–Bilbao, event 15312871: an official heavy-rain
/// postponement on September 16; three separate Kalshi winner contracts
/// closed at fair value on September 17; no score, no exact kickoff and no
/// captured reschedule date. The three hourly series below are the retained
/// provider candles' qualifying hours, copied here as numbers: from
/// `artifacts/discovery-containers-release-plan/event-page-design-20261011/totals-final-forecast-binding-20261024/prototype/src/postponedCapture.json`
/// (sha256 944075e4b3ae90d756154ded63361cc660a180d27547916e649f5fc3e8a1e772),
/// an hour kept only with positive traded volume and a valid close in
/// 0...1, from 2026-09-12T00:00Z up to the declared cutoff
/// 2026-09-16T00:00Z, no duplicate hour conflicting. Empty hours are absent
/// and break the runs. That selection was made outside the app (the rule is
/// the approved `postponedEvidence.ts` `tradedHours`); nothing in the
/// component or in this file re-derives it, and it is evidence for these
/// CONSTRUCTED owner inputs, not production membership proof. The app's own
/// 411-row Kalshi history for this event is rejected (two complementary
/// sides, no draw) and is not used. The settlement amounts $0.29 / $0.43 /
/// $0.28 are dollars: they appear only as Details About rows, never as a
/// chance or a mark.
///
/// Every other owner value here — the clock and provenance words, the state,
/// timeline, reader and About words, identities, scope, labels, tints, plot
/// heights and control ids — is CONSTRUCTED and named where used. Variants
/// (an observed 0, an absent series, mixed original states, duplicated and
/// foreign identities, an owner update, omission and restore) are labelled
/// CONSTRUCTED and change only what they name.
@MainActor
final class PostponedEventPagePresentation10868Tests: XCTestCase {
    private typealias Page = PostponedEventPagePresentation10868
    private typealias Model = PostponedEventPageModel10868
    private typealias Details = OriginalMarketDetails9483

    // MARK: - Retained hours (copied numbers; see the file note)

    struct Hour {
        /// The hour's end, UTC seconds.
        let t: Int
        let value: Double
        /// CONSTRUCTED owner clock words for that hour end.
        let words: String
    }

    static let levante: [Hour] = [
        .init(t: 1789243200, value: 0.3, words: "Sep 12, 20:00 UTC"),
        .init(t: 1789336800, value: 0.27, words: "Sep 13, 22:00 UTC"),
        .init(t: 1789340400, value: 0.28, words: "Sep 13, 23:00 UTC"),
        .init(t: 1789347600, value: 0.27, words: "Sep 14, 01:00 UTC"),
        .init(t: 1789351200, value: 0.27, words: "Sep 14, 02:00 UTC"),
        .init(t: 1789358400, value: 0.27, words: "Sep 14, 04:00 UTC"),
        .init(t: 1789412400, value: 0.28, words: "Sep 14, 19:00 UTC"),
        .init(t: 1789416000, value: 0.28, words: "Sep 14, 20:00 UTC"),
        .init(t: 1789419600, value: 0.28, words: "Sep 14, 21:00 UTC"),
        .init(t: 1789423200, value: 0.28, words: "Sep 14, 22:00 UTC"),
        .init(t: 1789426800, value: 0.28, words: "Sep 14, 23:00 UTC"),
        .init(t: 1789430400, value: 0.28, words: "Sep 15, 00:00 UTC"),
        .init(t: 1789441200, value: 0.28, words: "Sep 15, 03:00 UTC"),
        .init(t: 1789444800, value: 0.28, words: "Sep 15, 04:00 UTC"),
        .init(t: 1789448400, value: 0.28, words: "Sep 15, 05:00 UTC"),
        .init(t: 1789452000, value: 0.28, words: "Sep 15, 06:00 UTC"),
        .init(t: 1789455600, value: 0.28, words: "Sep 15, 07:00 UTC"),
        .init(t: 1789459200, value: 0.28, words: "Sep 15, 08:00 UTC"),
        .init(t: 1789462800, value: 0.28, words: "Sep 15, 09:00 UTC"),
        .init(t: 1789466400, value: 0.28, words: "Sep 15, 10:00 UTC"),
        .init(t: 1789480800, value: 0.28, words: "Sep 15, 14:00 UTC"),
        .init(t: 1789484400, value: 0.28, words: "Sep 15, 15:00 UTC"),
        .init(t: 1789488000, value: 0.28, words: "Sep 15, 16:00 UTC"),
        .init(t: 1789491600, value: 0.27, words: "Sep 15, 17:00 UTC"),
        .init(t: 1789495200, value: 0.27, words: "Sep 15, 18:00 UTC"),
        .init(t: 1789502400, value: 0.27, words: "Sep 15, 20:00 UTC"),
        .init(t: 1789506000, value: 0.28, words: "Sep 15, 21:00 UTC"),
        .init(t: 1789509600, value: 0.28, words: "Sep 15, 22:00 UTC"),
        .init(t: 1789513200, value: 0.28, words: "Sep 15, 23:00 UTC"),
        .init(t: 1789516800, value: 0.28, words: "Sep 16, 00:00 UTC"),
    ]

    static let bilbao: [Hour] = [
        .init(t: 1789282800, value: 0.44, words: "Sep 13, 07:00 UTC"),
        .init(t: 1789293600, value: 0.43, words: "Sep 13, 10:00 UTC"),
        .init(t: 1789308000, value: 0.45, words: "Sep 13, 14:00 UTC"),
        .init(t: 1789322400, value: 0.44, words: "Sep 13, 18:00 UTC"),
        .init(t: 1789326000, value: 0.44, words: "Sep 13, 19:00 UTC"),
        .init(t: 1789329600, value: 0.45, words: "Sep 13, 20:00 UTC"),
        .init(t: 1789333200, value: 0.45, words: "Sep 13, 21:00 UTC"),
        .init(t: 1789336800, value: 0.45, words: "Sep 13, 22:00 UTC"),
        .init(t: 1789340400, value: 0.46, words: "Sep 13, 23:00 UTC"),
        .init(t: 1789344000, value: 0.46, words: "Sep 14, 00:00 UTC"),
        .init(t: 1789351200, value: 0.46, words: "Sep 14, 02:00 UTC"),
        .init(t: 1789354800, value: 0.46, words: "Sep 14, 03:00 UTC"),
        .init(t: 1789358400, value: 0.47, words: "Sep 14, 04:00 UTC"),
        .init(t: 1789362000, value: 0.47, words: "Sep 14, 05:00 UTC"),
        .init(t: 1789372800, value: 0.47, words: "Sep 14, 08:00 UTC"),
        .init(t: 1789387200, value: 0.46, words: "Sep 14, 12:00 UTC"),
        .init(t: 1789398000, value: 0.46, words: "Sep 14, 15:00 UTC"),
        .init(t: 1789401600, value: 0.46, words: "Sep 14, 16:00 UTC"),
        .init(t: 1789405200, value: 0.46, words: "Sep 14, 17:00 UTC"),
        .init(t: 1789408800, value: 0.46, words: "Sep 14, 18:00 UTC"),
        .init(t: 1789412400, value: 0.46, words: "Sep 14, 19:00 UTC"),
        .init(t: 1789416000, value: 0.46, words: "Sep 14, 20:00 UTC"),
        .init(t: 1789419600, value: 0.46, words: "Sep 14, 21:00 UTC"),
        .init(t: 1789423200, value: 0.46, words: "Sep 14, 22:00 UTC"),
        .init(t: 1789426800, value: 0.46, words: "Sep 14, 23:00 UTC"),
        .init(t: 1789430400, value: 0.46, words: "Sep 15, 00:00 UTC"),
        .init(t: 1789434000, value: 0.46, words: "Sep 15, 01:00 UTC"),
        .init(t: 1789437600, value: 0.46, words: "Sep 15, 02:00 UTC"),
        .init(t: 1789441200, value: 0.46, words: "Sep 15, 03:00 UTC"),
        .init(t: 1789444800, value: 0.46, words: "Sep 15, 04:00 UTC"),
        .init(t: 1789448400, value: 0.46, words: "Sep 15, 05:00 UTC"),
        .init(t: 1789452000, value: 0.46, words: "Sep 15, 06:00 UTC"),
        .init(t: 1789455600, value: 0.46, words: "Sep 15, 07:00 UTC"),
        .init(t: 1789459200, value: 0.46, words: "Sep 15, 08:00 UTC"),
        .init(t: 1789462800, value: 0.46, words: "Sep 15, 09:00 UTC"),
        .init(t: 1789470000, value: 0.46, words: "Sep 15, 11:00 UTC"),
        .init(t: 1789473600, value: 0.45, words: "Sep 15, 12:00 UTC"),
        .init(t: 1789477200, value: 0.46, words: "Sep 15, 13:00 UTC"),
        .init(t: 1789480800, value: 0.45, words: "Sep 15, 14:00 UTC"),
        .init(t: 1789484400, value: 0.44, words: "Sep 15, 15:00 UTC"),
        .init(t: 1789488000, value: 0.45, words: "Sep 15, 16:00 UTC"),
        .init(t: 1789491600, value: 0.45, words: "Sep 15, 17:00 UTC"),
        .init(t: 1789495200, value: 0.46, words: "Sep 15, 18:00 UTC"),
        .init(t: 1789498800, value: 0.46, words: "Sep 15, 19:00 UTC"),
        .init(t: 1789502400, value: 0.46, words: "Sep 15, 20:00 UTC"),
        .init(t: 1789506000, value: 0.46, words: "Sep 15, 21:00 UTC"),
        .init(t: 1789509600, value: 0.46, words: "Sep 15, 22:00 UTC"),
        .init(t: 1789513200, value: 0.46, words: "Sep 15, 23:00 UTC"),
        .init(t: 1789516800, value: 0.46, words: "Sep 16, 00:00 UTC"),
    ]

    static let draw: [Hour] = [
        .init(t: 1789340400, value: 0.28, words: "Sep 13, 23:00 UTC"),
        .init(t: 1789362000, value: 0.27, words: "Sep 14, 05:00 UTC"),
        .init(t: 1789398000, value: 0.28, words: "Sep 14, 15:00 UTC"),
        .init(t: 1789416000, value: 0.27, words: "Sep 14, 20:00 UTC"),
        .init(t: 1789423200, value: 0.27, words: "Sep 14, 22:00 UTC"),
        .init(t: 1789426800, value: 0.27, words: "Sep 14, 23:00 UTC"),
        .init(t: 1789437600, value: 0.28, words: "Sep 15, 02:00 UTC"),
        .init(t: 1789448400, value: 0.28, words: "Sep 15, 05:00 UTC"),
        .init(t: 1789477200, value: 0.28, words: "Sep 15, 13:00 UTC"),
        .init(t: 1789480800, value: 0.28, words: "Sep 15, 14:00 UTC"),
        .init(t: 1789495200, value: 0.28, words: "Sep 15, 18:00 UTC"),
        .init(t: 1789506000, value: 0.28, words: "Sep 15, 21:00 UTC"),
        .init(t: 1789509600, value: 0.27, words: "Sep 15, 22:00 UTC"),
        .init(t: 1789513200, value: 0.27, words: "Sep 15, 23:00 UTC"),
        .init(t: 1789516800, value: 0.27, words: "Sep 16, 00:00 UTC"),
    ]

    /// 2026-09-12T00:00Z and the declared cutoff 2026-09-16T00:00Z.
    static let start = 1789171200
    static let cutoff = 1789516800
    /// 2026-09-15T20:00Z: Levante and Bilbao traded, the draw did not.
    static let missingDrawHour = 1789502400

    // MARK: - CONSTRUCTED owner inputs

    static let scope = "postponed:15312871:originals"
    static let lastProvenance = "Hour ending Sep 16, 00:00 UTC · Kalshi last trade"
    static let notRecorded = "Not recorded"

    static func figure(_ value: Double) -> String { String(format: "%.0f%%", value * 100) }

    static func pointID(_ series: String, _ hour: Hour) -> String { "\(series)#\(hour.t)" }

    /// The owner's runs: consecutive hours together, an empty hour a break.
    static func runs(_ series: String, _ hours: [Hour]) -> [FieldHistoryRun10868] {
        var groups: [[Hour]] = []
        for hour in hours {
            if let previous = groups.last?.last, hour.t - previous.t == 3600 {
                groups[groups.count - 1].append(hour)
            } else {
                groups.append([hour])
            }
        }
        return groups.enumerated().map { index, group in
            FieldHistoryRun10868(id: "\(series)#run-\(index + 1)", points: group.map {
                FieldHistoryPoint10868(id: pointID(series, $0), x: Double($0.t), probability: $0.value, style: .filled)
            })
        }
    }

    static func series(_ id: String, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color,
                       _ hours: [Hour], selected: Int?) -> FieldHistorySeries10868 {
        let last = hours[hours.count - 1]
        let before = FieldHistoryReading10868.observation(pointID: pointID(id, last), figure: figure(last.value),
                                                          provenance: lastProvenance)
        var recorded = FieldHistoryReading10868.absent(words: notRecorded)
        if let selected, let hour = hours.first(where: { $0.t == selected }) {
            recorded = .observation(pointID: pointID(id, hour), figure: figure(hour.value),
                                    provenance: "Hour ending \(hour.words) · Kalshi last trade")
        }
        return FieldHistorySeries10868(id: id, name: name, shape: shape, tint: tint, runs: runs(id, hours), links: [],
                                       labelPointID: nil, before: before, recorded: recorded,
                                       absentWords: "No qualifying trade", choose: nil)
    }

    static let specimen: [(id: String, name: String, shape: FieldHistoryShape10868, tint: Color, hours: [Hour])] = [
        ("LEV", "Levante", .circle, .blue, levante),
        ("ATH", "Bilbao", .square, .green, bilbao),
        ("TIE", "Draw", .diamond, .gray, draw),
    ]

    /// The owner's inspection at `selected`: each series' exact point there,
    /// or the owner's absence words. Choices are every observed hour.
    static func inspection(_ selected: Int, among all: [(id: String, hours: [Hour])]) -> FieldHistoryInspection10868 {
        var selections: [String: FieldHistorySelection10868] = [:]
        for entry in all {
            if let hour = entry.hours.first(where: { $0.t == selected }) {
                selections[entry.id] = .point(id: pointID(entry.id, hour), spoken: figure(hour.value))
            } else {
                selections[entry.id] = .absent(words: notRecorded)
            }
        }
        let hours = Dictionary(all.flatMap { $0.hours }.map { ($0.t, $0) }, uniquingKeysWith: { first, _ in first })
        let choices = hours.keys.sorted().map { t in
            FieldHistoryInspectionChoice10868(id: "hour-\(t)", lines: [hours[t]!.words], spoken: hours[t]!.words,
                                              isSelected: t == selected)
        }
        return FieldHistoryInspection10868(
            x: Double(selected), caption: "Hour ending \(hours[selected]?.words ?? "")", selections: selections,
            choices: choices, choicePresentation: .slider(label: "Inspect pregame trading hour"),
            note: "Only positively traded hours are shown; empty hours stay blank.")
    }

    static func history(selected: Int? = nil,
                        series replacement: [FieldHistorySeries10868]? = nil) -> FieldHistoryInput10868 {
        let built = replacement ?? specimen.map { series($0.id, $0.name, $0.shape, $0.tint, $0.hours, selected: selected) }
        let held = selected.map { inspection($0, among: specimen.map { (id: $0.id, hours: $0.hours) }) }
        return FieldHistoryInput10868(
            title: "Pregame win chances",
            caption: "Recorded before the original match date",
            series: built,
            selection: .none,
            domain: FieldHistoryDomain10868(lower: Double(start), upper: Double(cutoff)),
            ceiling: 1,
            yTicks: [0, 0.5, 1].map { FieldHistoryTick10868(value: $0, lines: [figure($0)]) },
            xTicks: [(start, "Sep 12"), (start + 172_800, "Sep 14"), (cutoff, "Sep 16")].map {
                FieldHistoryTick10868(value: Double($0.0), lines: [$0.1])
            },
            guides: [],
            breaks: [],
            readout: selected == nil
                ? .singleBefore(label: "Last recorded pregame")
                : .beforeAndInspected(beforeLabel: "Last recorded pregame", inspectedLabel: "Selected hour"),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: ["Each series is its own Kalshi contract’s last trade in a positively traded hour.",
                    "Values are independent and may not sum to 100%.",
                    "Times in UTC; hour ends label buckets, not exact trade times."],
            summary: "Three independent pregame histories: Levante circles, Bilbao squares, Draw diamonds. Hours without a qualifying trade stay blank.",
            plotHeight: 240,
            unboundReadingWords: notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil, details: nil,
            expand: FieldHistoryAction10868(id: "history.expand", label: "Full chart",
                                            spokenLabel: "Expand pregame win probability chart", isAvailable: true),
            inspect: nil,
            previous: FieldHistoryAction10868(id: "history.previous", label: "Previous hour", spokenLabel: nil,
                                              isAvailable: selected != nil),
            next: FieldHistoryAction10868(id: "history.next", label: "Next hour", spokenLabel: nil,
                                          isAvailable: selected != nil),
            inspection: held)
    }

    static let source = PostponedEventPageSource10868(
        id: "levante-official", label: "Levante’s official announcement",
        url: URL(string: "https://www.levanteud.com/en/news/the-match-between-levante-ud-and-athletic-club-has-been-suspended")!)

    static let about = PostponedEventPageAbout10868(title: "About this match", sections: [
        PostponedEventPageAboutSection10868(
            title: "Match postponed · original markets closed",
            paragraphs: ["Levante’s September 16 announcement says heavy rain flooded the pitch and prevented the match from being played. A rescheduled date is not captured here.",
                         "The three original Kalshi winner contracts settled at fair value on September 17. This does not declare a sporting winner or a draw. Each contract’s dollar settlement remains in its details."],
            source: source),
        PostponedEventPageAboutSection10868(
            title: "Pregame history",
            paragraphs: ["Each series uses its own Kalshi contract’s last trade in a positively traded hour. Values are independent and may not sum to 100%. Empty hours stay blank; no carried-forward probabilities, complements or settlement values are plotted.",
                         "An exact kickoff is not established in this capture, so no kickoff marker is shown. No score or projected final is supplied."]),
        PostponedEventPageAboutSection10868(title: "Original history cutoff", paragraphs: ["2026-09-16T00:00:00Z"]),
    ])

    static let timeline = PostponedEventPageTimeline10868(label: "Match and market status", facts: [
        PostponedEventPageFact10868(id: "postponed", kind: .match, date: "Sep 16", title: "Match postponed",
                                    detail: "Heavy rain · no sporting result"),
        PostponedEventPageFact10868(id: "closed", kind: .market, date: "Sep 17", title: "Original markets closed",
                                    detail: "Fair-value settlement · no winner"),
    ], reschedule: .unknown("Rescheduled date not captured"))

    static func input(history: FieldHistoryInput10868 = PostponedEventPagePresentation10868Tests.history(),
                      timeline: PostponedEventPageTimeline10868? = PostponedEventPagePresentation10868Tests.timeline,
                      about: PostponedEventPageAbout10868? = PostponedEventPagePresentation10868Tests.about,
                      allProps: String? = "All 3 original markets") -> PostponedEventPageInput10868 {
        PostponedEventPageInput10868(
            title: PostponedEventPageTitle10868(eyebrow: "La Liga · Sep 16, 2026", competitors: ["Levante", "Bilbao"],
                                                joiner: "vs", spoken: "Levante versus Bilbao"),
            status: PostponedEventPageStatus10868(state: "Postponed", reason: "Rain · match not played"),
            timeline: timeline,
            history: history,
            readerPlotHeight: 320,
            reader: PostponedEventPageReaderHeader10868(title: "Levante · Bilbao", state: "Postponed · no match result"),
            about: about,
            copy: PostponedEventPageCopy10868(aboutLabel: "About this match",
                                              aboutHint: "Opens the postponement, market and history sources",
                                              allPropsLabel: allProps))
    }

    // MARK: Originals (CONSTRUCTED from the specimen)

    static func identity(_ side: String) -> Details.Identity {
        Details.Identity(source: "kalshi", market: "KXLALIGAGAME-26SEP16LEVATH-\(side)", side: side)
    }

    /// One fair-value-closed winner contract: its own pregame reading (the
    /// chart's baseline words), its own grade and its settlement dollars as an
    /// About row only.
    static func fairValue(_ side: String, _ outcome: String, pregame value: Double, dollars: String) -> Details.Original {
        Details.Original(
            identity: identity(side), title: "Levante vs Bilbao winner", outcome: outcome, mode: .result,
            pregame: .value(figure(value), placement: value, provenance: lastProvenance),
            later: nil,
            grade: Details.Grade(words: "Closed at fair value · no winner declared", provenance: "Kalshi settlement · Sep 17"),
            about: Details.About(source: "Kalshi", rules: .unavailable("Rules unavailable"),
                                 provenance: [Details.Row(label: "Settlement amount", value: dollars)],
                                 historicalQuote: nil),
            beforeLabel: "Last recorded pregame")
    }

    static let specimenOriginals: [Details.Original] = [
        fairValue("LEV", "Levante", pregame: 0.28, dollars: "$0.29"),
        fairValue("ATH", "Bilbao", pregame: 0.46, dollars: "$0.43"),
        fairValue("TIE", "Tie", pregame: 0.27, dollars: "$0.28"),
    ]

    static func originals(_ list: [Details.Original] = PostponedEventPagePresentation10868Tests.specimenOriginals,
                          scope: String = PostponedEventPagePresentation10868Tests.scope,
                          selection: Details.Selection? = nil) -> PostponedEventPageOriginals10868 {
        PostponedEventPageOriginals10868(
            catalogue: Details.Catalogue(scope: scope, originals: list), selection: selection,
            heading: "Original markets", context: "\(list.count) retained originals",
            emptyWords: "No retained originals for this match", unavailableChoice: "Unnamed original", tint: .blue)
    }

    static func held(_ side: String, scope: String = PostponedEventPagePresentation10868Tests.scope) -> Details.Selection {
        Details.Selection(scope: scope, identity: identity(side))
    }

    // MARK: - The specimen numbers

    func testTheCopiedHoursAreTheRetainedQualifyingHoursAndDoNotSumTo100() {
        XCTAssertEqual([Self.levante.count, Self.bilbao.count, Self.draw.count], [30, 49, 15])
        XCTAssertEqual([Self.levante, Self.bilbao, Self.draw].map { $0.last?.t }, [Self.cutoff, Self.cutoff, Self.cutoff],
                       "every series stops at the declared pregame cutoff")
        XCTAssertTrue([Self.levante, Self.bilbao, Self.draw].allSatisfy { $0.allSatisfy { $0.t >= Self.start && $0.t <= Self.cutoff } })
        let last = [Self.levante, Self.bilbao, Self.draw].map { $0[$0.count - 1].value }
        XCTAssertEqual(last, [0.28, 0.46, 0.27])
        XCTAssertEqual(last.reduce(0, +), 1.01, accuracy: 1e-9, "independent chances, never normalized")
        XCTAssertEqual([Self.runs("LEV", Self.levante).count, Self.runs("ATH", Self.bilbao).count,
                        Self.runs("TIE", Self.draw).count], [8, 9, 10], "empty hours break every series")
    }

    // MARK: - The same history on the page and in the full-size chart

    func testThePageAndTheFullSizeChartCarryTheExactSameHistoryAndSelectedHour() {
        let history = Self.history(selected: Self.missingDrawHour)
        let page = Page(input: Self.input(history: history))
        XCTAssertEqual(page.historyContent(reader: false).input, history, "the page's chart is the owner's input, unchanged")

        let reader = page.historyContent(reader: true).input
        XCTAssertNil(reader.expand, "the full-size chart is already open")
        XCTAssertEqual(reader.plotHeight, 320, "the owner's taller reader height")
        XCTAssertEqual(reader.series, history.series)
        XCTAssertEqual(reader.inspection, history.inspection, "the held hour survives into full size")
        XCTAssertEqual(reader.readout, history.readout)
        XCTAssertEqual(reader.selection, history.selection)
        XCTAssertEqual(reader.domain, history.domain)
        XCTAssertEqual(reader.xTicks, history.xTicks)
        XCTAssertEqual(reader.yTicks, history.yTicks)
        XCTAssertEqual(reader.notes, history.notes)
        XCTAssertEqual(reader.summary, history.summary)
        XCTAssertEqual(reader.layout, history.layout)
        XCTAssertEqual(reader.previous, history.previous)
        XCTAssertEqual(reader.next, history.next)
        XCTAssertEqual(reader.unboundReadingWords, history.unboundReadingWords)

        // CONSTRUCTED: a shorter reader height never shrinks the chart.
        var short = Self.input(history: history)
        short.readerPlotHeight = 180
        XCTAssertEqual(Model(short).readerHistory.plotHeight, 240)
    }

    func testThreeIndependentOriginalsKeepTheirOwnDatedValuesEverywhere() {
        let input = Self.input()
        let history = input.history
        let shown = history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: history) }
        XCTAssertEqual(shown.map { $0.map(\.display) }, [
            [.figure("28%", provenance: Self.lastProvenance)],
            [.figure("46%", provenance: Self.lastProvenance)],
            [.figure("27%", provenance: Self.lastProvenance)],
        ])
        let catalogue = Details.Catalogue(scope: Self.scope, originals: Self.specimenOriginals)
        let details = ["LEV", "ATH", "TIE"].map { Details.content(catalogue: catalogue, selection: Self.held($0)) }
        XCTAssertEqual(details.map { $0?.readings.first?.text }, ["28%", "46%", "27%"])
        XCTAssertEqual(details.map { $0?.readings.first?.provenance }, [String?](repeating: Self.lastProvenance, count: 3),
                       "the chart and Details print one provenance for each baseline")
        XCTAssertEqual(details.map { $0?.readings.first?.label }, [String?](repeating: "Last recorded pregame", count: 3))
    }

    func testTheCompactHeadingBaselinesAreTheChartsOwnReadings() {
        let model = Model(Self.input())
        XCTAssertEqual(model.baselineLabel, "Last recorded pregame")
        XCTAssertEqual(model.baselines, [
            PostponedEventPageBaseline10868(seriesID: "LEV", name: "Levante", display: .figure("28%", provenance: Self.lastProvenance)),
            PostponedEventPageBaseline10868(seriesID: "ATH", name: "Bilbao", display: .figure("46%", provenance: Self.lastProvenance)),
            PostponedEventPageBaseline10868(seriesID: "TIE", name: "Draw", display: .figure("27%", provenance: Self.lastProvenance)),
        ])
        XCTAssertEqual(model.sharedBaselineProvenance, Self.lastProvenance, "one shared line, shown once")
        XCTAssertEqual(model.baselines.map { Model.spokenBaseline($0, sharedProvenance: model.sharedBaselineProvenance) },
                       ["Levante 28%", "Bilbao 46%", "Draw 27%"])
        XCTAssertEqual(PostponedEventPageMode10868.allModes.filter(Model.headerShowsBaselines), [.catalogue, .original],
                       "expanded props keep the baselines; the full chart has its own key")
    }

    // MARK: - Observed 0, absent and a selected missing hour

    func testAnObservedZeroIsAValueAndAnAbsentSeriesKeepsItsOwnWords() {
        // CONSTRUCTED: the draw's last hour admitted as an observed 0, and a
        // fourth original with no qualifying trade at all.
        var zeroDraw = Self.draw
        zeroDraw[zeroDraw.count - 1] = Hour(t: Self.cutoff, value: 0, words: "Sep 16, 00:00 UTC")
        let draw = Self.series("TIE", "Draw", .diamond, .gray, zeroDraw, selected: nil)
        let untraded = FieldHistorySeries10868(id: "OTHER", name: "Other outcome", shape: .triangle, tint: .orange, runs: [],
                                           links: [], labelPointID: nil, before: .absent(words: "No qualifying trade"),
                                           recorded: .absent(words: "No qualifying trade"),
                                           absentWords: "No qualifying trade", choose: nil)
        let base = Self.history().series
        let history = Self.history(series: [base[0], base[1], draw, untraded])
        let model = Model(Self.input(history: history))
        XCTAssertEqual(model.baselines[2].display, .figure("0%", provenance: Self.lastProvenance), "a real 0 is a value")
        XCTAssertEqual(model.baselines[3].display, .words("No qualifying trade"), "absent is words, never 0%")
        XCTAssertNil(model.sharedBaselineProvenance, "words in the set: each figure keeps its own provenance")
        XCTAssertEqual(Model.spokenBaseline(model.baselines[3], sharedProvenance: nil), "Other outcome: No qualifying trade")
        XCTAssertEqual(model.readerHistory.series[2].runs.last?.points.last?.probability, 0)
        XCTAssertTrue(model.readerHistory.series[3].runs.isEmpty, "no line is made for the absent original")

        let zero = Details.Original(identity: Self.identity("TIE"), title: "Levante vs Bilbao winner", outcome: "Tie",
                                    mode: .pregame, pregame: .value("0%", placement: 0, provenance: Self.lastProvenance),
                                    later: nil, grade: nil,
                                    about: Details.About(source: "Kalshi", rules: .omitted, provenance: [], historicalQuote: nil))
        let missing = Details.Original(identity: Self.identity("OTHER"), title: "Other outcome", outcome: "Yes",
                                       mode: .pregame, pregame: .missing("No qualifying trade"), later: nil, grade: nil,
                                       about: Details.About(source: "Kalshi", rules: .omitted, provenance: [], historicalQuote: nil))
        let catalogue = Details.Catalogue(scope: Self.scope, originals: [zero, missing])
        let zeroShown = Details.content(catalogue: catalogue, selection: Self.held("TIE"))?.readings.first
        XCTAssertEqual(zeroShown?.text, "0%")
        XCTAssertEqual(zeroShown?.isValue, true)
        XCTAssertEqual(zeroShown?.placement, 0)
        let missingShown = Details.content(catalogue: catalogue, selection: Self.held("OTHER"))?.readings.first
        XCTAssertEqual(missingShown?.text, "No qualifying trade")
        XCTAssertEqual(missingShown?.isValue, false)
        XCTAssertNil(missingShown?.placement)
    }

    func testASelectedHourWithOneMissingValueKeepsItsValidNeighboursOnPageAndFullSize() {
        let history = Self.history(selected: Self.missingDrawHour)
        let page = Page(input: Self.input(history: history))
        for input in [page.historyContent(reader: false).input, page.historyContent(reader: true).input] {
            let inspected = input.series.map { FieldHistoryGeometry10868.inspectedDisplay($0, in: input) }
            XCTAssertEqual(inspected, [
                .figure("27%", provenance: "Hour ending Sep 15, 20:00 UTC · Kalshi last trade"),
                .figure("46%", provenance: "Hour ending Sep 15, 20:00 UTC · Kalshi last trade"),
                .words(Self.notRecorded),
            ], "the draw's 18:00 and 21:00 trades are never borrowed")
            XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(input),
                           "Hour ending Sep 15, 20:00 UTC; Levante: 27%; Bilbao: 46%; Draw: Not recorded")
            XCTAssertEqual(input.inspection?.choices.filter(\.isSelected).map(\.id), ["hour-\(Self.missingDrawHour)"])
        }
    }

    func testBrokenRunsHourlyProvenanceAndThePointSetAreUnchanged() {
        let model = Model(Self.input(history: Self.history(selected: Self.missingDrawHour)))
        let reader = model.readerHistory
        XCTAssertEqual(reader.series.map(\.runs.count), [8, 9, 10])
        XCTAssertEqual(reader.series.flatMap(\.runs).flatMap(\.points).count, 94, "no point added or dropped")
        XCTAssertTrue(reader.series.flatMap(\.runs).flatMap(\.points).allSatisfy { $0.x <= Double(Self.cutoff) },
                      "nothing after the pregame cutoff: no closure, settlement or announcement point")
        XCTAssertEqual(reader.guides, [], "no kickoff, postponement or closure marker is added")
        XCTAssertEqual(reader.breaks, [])
        XCTAssertEqual(reader.series.map(\.before), model.input.history.series.map(\.before))
        XCTAssertEqual(reader.series.map(\.recorded), model.input.history.series.map(\.recorded))
    }

    // MARK: - State, timeline and nothing invented

    func testTheStateAndTimelineAreTheOwnersWordsWithDistinctKindsAndNoInventedResult() {
        let model = Model(Self.input())
        XCTAssertEqual(model.titleWords, "Levante vs Bilbao")
        XCTAssertEqual(model.spokenTitle, "Levante versus Bilbao")
        XCTAssertEqual(model.spokenStatus, "Postponed, Rain · match not played")
        XCTAssertEqual(model.facts.map(\.id), ["postponed", "closed"])
        XCTAssertEqual(model.facts.map { Model.spokenFact($0) }, [
            "Sep 16, Match postponed, Heavy rain · no sporting result",
            "Sep 17, Original markets closed, Fair-value settlement · no winner",
        ])
        XCTAssertEqual(model.reschedule, .unknown("Rescheduled date not captured"), "the owner's absence words, never a date")
        XCTAssertEqual(Set(PostponedEventPageFactKind10868.allCases.map(Model.marker)).count, 3,
                       "match, market and result facts keep distinct markers")
        XCTAssertEqual(Model.marker(.match), .ring)
        XCTAssertEqual(Model.marker(.market), .closedSquare)
        XCTAssertEqual(Model.marker(.result), .bar)

        // CONSTRUCTED: an owner sporting-result fact and a captured reschedule.
        let other = PostponedEventPageTimeline10868(label: "Match and market status", facts: [
            PostponedEventPageFact10868(id: "result", kind: .result, date: nil, title: "No sporting result", detail: nil),
            PostponedEventPageFact10868(id: "blank", kind: .market, date: "Sep 17", title: "  ", detail: "dropped"),
        ], reschedule: .scheduled("Rescheduled for Oct 2"))
        let custom = Model(Self.input(timeline: other))
        XCTAssertEqual(custom.facts.map(\.id), ["result"], "a fact without readable words is not drawn")
        XCTAssertEqual(custom.facts.map { Model.spokenFact($0) }, ["No sporting result"])
        XCTAssertEqual(custom.reschedule?.words, "Rescheduled for Oct 2")
        XCTAssertFalse(Model(Self.input(timeline: nil)).showsTimeline)
        XCTAssertNil(Page(input: Self.input(timeline: nil)).timelineContent())
    }

    func testSettlementDollarsStayDetailsRowsAndNeverBecomeChancesOrMarks() {
        let catalogue = Details.Catalogue(scope: Self.scope, originals: Self.specimenOriginals)
        let levante = Details.content(catalogue: catalogue, selection: Self.held("LEV"))
        XCTAssertEqual(levante?.marks.map(\.placement), [0.28], "the only rail mark is the pregame baseline")
        XCTAssertEqual(levante?.result, Details.ShownResult(words: "Closed at fair value · no winner declared",
                                                            provenance: "Kalshi settlement · Sep 17"))
        XCTAssertTrue(levante?.about.contains(Details.Row(label: "Settlement amount", value: "$0.29")) ?? false)
        XCTAssertFalse(levante?.readings.contains { $0.text == "$0.29" || $0.text == "29%" } ?? true)
        let reader = Model(Self.input()).readerHistory
        XCTAssertEqual(reader.series.map { $0.runs.last?.points.last?.probability }, [0.28, 0.46, 0.27],
                       "each series ends on its last pregame trade, not its settlement dollars")
        XCTAssertEqual(reader.series.map { $0.runs.last?.points.last?.x }, [Double?](repeating: Double(Self.cutoff), count: 3))
    }

    // MARK: - Originals

    func testMixedOriginalStatesStayExactlyAsSuppliedWithNoBlanketClosure() {
        // CONSTRUCTED, not the specimen: one fair-value close, one still-open
        // original, one independently resolved original and one unconfirmed.
        let open = Details.Original(
            identity: Self.identity("ATH"), title: "Levante vs Bilbao winner", outcome: "Bilbao",
            mode: .comparison(.current), pregame: .value("46%", placement: 0.46, provenance: Self.lastProvenance),
            later: .value("41%", placement: 0.41, provenance: "Kalshi · Sep 18, 09:00 UTC"), grade: nil,
            about: Details.About(source: "Kalshi", rules: .omitted, provenance: [], historicalQuote: nil))
        let resolved = Details.Original(
            identity: Details.Identity(source: "kalshi", market: "KXPOSTPONE-LEVATH", side: "YES"),
            title: "Will the match be postponed?", outcome: "Yes", mode: .result,
            pregame: .missing("No pregame trade"), later: nil,
            grade: Details.Grade(words: "Won", provenance: "Settled by Kalshi · Sep 16"),
            about: Details.About(source: "Kalshi", rules: .omitted, provenance: [], historicalQuote: nil))
        let unconfirmed = Details.Original(
            identity: Self.identity("TIE"), title: "Levante vs Bilbao winner", outcome: "Tie", mode: .result,
            pregame: .value("27%", placement: 0.27, provenance: Self.lastProvenance), later: nil, grade: nil,
            about: Details.About(source: "Kalshi", rules: .omitted, provenance: [], historicalQuote: nil))
        let list = [Self.specimenOriginals[0], open, resolved, unconfirmed]
        let page = Page(input: Self.input(), mode: .catalogue, originals: Self.originals(list))
        let catalogue = page.catalogueContent()
        XCTAssertEqual(catalogue?.catalogue?.originals, list, "every original reaches the leaf unchanged, in order")
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue?.catalogue, selection: nil,
                                                      labels: [:], unavailableChoice: "Unnamed original")
        XCTAssertEqual(cards.map { $0.content?.result?.words }, [
            "Closed at fair value · no winner declared", nil, "Won", Details.resultUnavailable,
        ])
        XCTAssertEqual(cards[1].content?.readings.map(\.text), ["46%", "41%"], "the open original keeps its current chance")
        XCTAssertEqual(cards.filter { $0.content?.result?.words == "Closed at fair value · no winner declared" }.count, 1,
                       "the closure words stay on the one original that carries them")
    }

    func testWrongOrAmbiguousIdentitiesFailClosedAndValidNeighboursStayUsable() {
        // CONSTRUCTED: the draw's identity supplied twice.
        let duplicated = Self.specimenOriginals + [Self.specimenOriginals[2]]
        let page = Page(input: Self.input(), originals: Self.originals(duplicated, selection: Self.held("TIE")),
                        onOriginalSelect: { _ in })
        let chooser = page.chooserContent()
        let choices = OriginalMarketChooser9483.choices(catalogue: chooser?.catalogue, selection: chooser?.selection,
                                                        labels: [:], unavailableChoice: "Unnamed original")
        XCTAssertEqual(choices.map { $0.selection != nil }, [true, true, false, false])
        XCTAssertFalse(choices.contains(where: \.isSelected), "an ambiguous held identity opens nothing")
        XCTAssertNil(Details.content(catalogue: chooser?.catalogue, selection: chooser?.selection))

        // CONSTRUCTED: a held identity from another scope.
        let foreign = Page(input: Self.input(), originals: Self.originals(selection: Self.held("ATH", scope: "postponed:other:originals")))
        XCTAssertNil(Details.content(catalogue: foreign.originalDetailsContent()?.catalogue,
                                     selection: foreign.originalDetailsContent()?.selection))
        let neighbours = OriginalMarketChooser9483.choices(catalogue: foreign.chooserContent()?.catalogue,
                                                           selection: foreign.chooserContent()?.selection,
                                                           labels: [:], unavailableChoice: "Unnamed original")
        XCTAssertEqual(neighbours.map { $0.selection != nil }, [true, true, true], "every valid neighbour still opens")
        XCTAssertFalse(neighbours.contains(where: \.isSelected))
    }

    func testTheHeldOriginalAndHourSurviveAnUpdateAnOmissionARestoreAndEveryMode() {
        let held = Self.held("ATH")
        func resolves(_ originals: PostponedEventPageOriginals10868) -> Details.Content? {
            Details.content(catalogue: originals.catalogue, selection: originals.selection)
        }
        // The specimen.
        XCTAssertEqual(resolves(Self.originals(selection: held))?.outcome, "Bilbao")
        // CONSTRUCTED owner update: Bilbao's grade provenance revised.
        var updated = Self.specimenOriginals
        updated[1] = Details.Original(identity: updated[1].identity, title: updated[1].title, outcome: updated[1].outcome,
                                      mode: .result, pregame: updated[1].pregame, later: nil,
                                      grade: Details.Grade(words: "Closed at fair value · no winner declared",
                                                           provenance: "Kalshi settlement · Sep 17, 17:53 UTC"),
                                      about: updated[1].about, beforeLabel: updated[1].beforeLabel)
        XCTAssertEqual(resolves(Self.originals(updated, selection: held))?.result?.provenance,
                       "Kalshi settlement · Sep 17, 17:53 UTC")
        // CONSTRUCTED omission: Bilbao withdrawn — nothing opens, no neighbour stands in.
        let omitted = [Self.specimenOriginals[0], Self.specimenOriginals[2]]
        XCTAssertNil(resolves(Self.originals(omitted, selection: held)))
        // Restore: the same held identity opens again.
        XCTAssertEqual(resolves(Self.originals(selection: held))?.outcome, "Bilbao")

        // Every mode reads the same held original and the same held hour.
        let history = Self.history(selected: Self.missingDrawHour)
        for mode in PostponedEventPageMode10868.allModes {
            let page = Page(input: Self.input(history: history), mode: mode, originals: Self.originals(selection: held))
            XCTAssertEqual(page.chooserContent()?.selection, held)
            XCTAssertEqual(page.catalogueContent()?.selection, held)
            XCTAssertEqual(page.originalDetailsContent()?.selection, held)
            XCTAssertEqual(page.historyContent(reader: false).input.inspection, history.inspection)
            XCTAssertEqual(page.historyContent(reader: true).input.inspection, history.inspection)
        }
        // Width changes rearrange blocks only: every arrangement holds every hero block once.
        for arrangement in [PostponedEventPageArrangement10868.stacked, .sideBySide] {
            XCTAssertEqual(Model.heroColumns(arrangement).flatMap { $0 }.sorted { $0.rawValue < $1.rawValue },
                           [.anchor, .status, .timeline, .title])
        }
    }

    // MARK: - Callbacks and holds

    func testThePageHoldsOnceBeforeEachActionTheFullSizeContentNeverAndBuildingNothing() throws {
        var log: [String] = []
        func page(_ mode: PostponedEventPageMode10868) -> Page {
            Page(input: Self.input(history: Self.history(selected: Self.missingDrawHour)), mode: mode,
                 originals: Self.originals(selection: Self.held("LEV")),
                 onAbout: { log.append("about") },
                 onAboutSource: { log.append("source:\($0.id)") },
                 onAllProps: { log.append("allProps") },
                 onOriginalSelect: { log.append("select:\($0.identity.side)") },
                 onOriginalHistory: { log.append("history:\($0.actionID)") },
                 onHistoryAction: { log.append("action:\($0)") },
                 onHistoryInspectionChoice: { log.append("choice:\($0)") },
                 onHistoryPlotPosition: { log.append("plot:\(Int($0))") },
                 onInteraction: { log.append("hold") })
        }
        // Passive construction and reading call nothing.
        let onPage = page(.page)
        _ = onPage.model
        _ = onPage.historyContent(reader: false)
        _ = onPage.historyContent(reader: true)
        _ = onPage.chooserContent()
        _ = onPage.catalogueContent()
        _ = onPage.originalDetailsContent()
        _ = onPage.aboutContent()
        _ = onPage.timelineContent()
        XCTAssertEqual(log, [])

        // The page: one hold, then the exact callback.
        let chart = onPage.historyContent(reader: false)
        try XCTUnwrap(chart.onAction)("history.expand")
        try XCTUnwrap(chart.onInspectionChoice)("hour-\(Self.missingDrawHour)")
        try XCTUnwrap(chart.onPlotPosition)(Double(Self.cutoff))
        try XCTUnwrap(onPage.chooserContent()?.onSelect)(Self.held("ATH"))
        onPage.openAllProps()
        onPage.openPageAbout()
        XCTAssertEqual(log, ["hold", "action:history.expand",
                             "hold", "choice:hour-\(Self.missingDrawHour)",
                             "hold", "plot:\(Self.cutoff)",
                             "hold", "select:ATH",
                             "hold", "allProps",
                             "hold", "about"])

        // Catalogue and Details content: one hold, like the page.
        log = []
        try XCTUnwrap(page(.catalogue).catalogueContent()?.onSelect)(Self.held("TIE"))
        let intent = Details.HistoryIntent(selection: Self.held("LEV"), entry: .explore, actionID: "lev.explore")
        try XCTUnwrap(page(.original).originalDetailsContent()?.onHistory)(intent)
        XCTAssertEqual(log, ["hold", "select:TIE", "hold", "history:lev.explore"])

        // Full-size content: the exact callback, no second hold.
        log = []
        let reader = page(.history)
        let full = reader.historyContent(reader: true)
        try XCTUnwrap(full.onAction)("history.next")
        try XCTUnwrap(full.onInspectionChoice)("hour-\(Self.cutoff)")
        reader.openReaderAbout()
        try XCTUnwrap(page(.about).aboutContent()?.sourceAction(Self.source))()
        XCTAssertEqual(log, ["action:history.next", "choice:hour-\(Self.cutoff)", "about", "source:levante-official"])
    }

    func testAbsentCallbacksOfferNoActionAndTheHookAloneDoesNothing() {
        var log: [String] = []
        let quiet = Page(input: Self.input(), originals: Self.originals(selection: Self.held("LEV")),
                         onInteraction: { log.append("hold") })
        let chart = quiet.historyContent(reader: false)
        XCTAssertNil(chart.onAction)
        XCTAssertNil(chart.onInspectionChoice)
        XCTAssertNil(chart.onPlotPosition)
        XCTAssertNil(quiet.historyContent(reader: true).onAction)
        XCTAssertNil(quiet.chooserContent()?.onSelect)
        XCTAssertNil(quiet.catalogueContent()?.onSelect)
        XCTAssertNil(quiet.originalDetailsContent()?.onHistory)
        XCTAssertNil(quiet.aboutContent()?.sourceAction(Self.source))
        XCTAssertFalse(quiet.model.aboutAvailable(canOpen: quiet.onAbout != nil))
        XCTAssertFalse(quiet.model.allPropsAvailable(canOpen: quiet.onAllProps != nil))
        quiet.openAllProps()
        quiet.openPageAbout()
        quiet.openReaderAbout()
        XCTAssertEqual(log, [], "no callback: no hold and no action")

        // CONSTRUCTED: no About words or no All props words — no control even with callbacks.
        let wordless = Page(input: Self.input(about: nil, allProps: nil), onAbout: { log.append("about") },
                            onAllProps: { log.append("allProps") })
        XCTAssertFalse(wordless.model.aboutAvailable(canOpen: true))
        XCTAssertFalse(wordless.model.allPropsAvailable(canOpen: true))
        wordless.openPageAbout()
        wordless.openAllProps()
        XCTAssertEqual(log, [])
    }

    // MARK: - Source / About, VoiceOver and layout

    func testTheAboutKeepsTheOwnersFullWordsAndOneLiveSourceEntry() {
        let page = Page(input: Self.input(), mode: .about, onAbout: {}, onAboutSource: { _ in })
        let about = page.aboutContent()?.about
        XCTAssertEqual(about, Self.about, "verbatim: every section and paragraph")
        XCTAssertEqual(about?.sections.map(\.title), ["Match postponed · original markets closed", "Pregame history",
                                                      "Original history cutoff"])
        XCTAssertTrue(Model.sourceIsLive(Self.source, canOpen: true))
        XCTAssertFalse(Model.sourceIsLive(Self.source, canOpen: false))
        XCTAssertFalse(Model.sourceIsLive(PostponedEventPageSource10868(id: "x", label: " ", url: Self.source.url), canOpen: true))
        XCTAssertEqual(PostponedEventPageMode10868.allModes.filter { page.model.aboutEntry(mode: $0, canOpen: true) },
                       [.history], "only the full-size chart's heading carries the About entry; the page has the title's")
        // CONSTRUCTED: an About of blank words is no About.
        let blank = PostponedEventPageAbout10868(title: " ", sections: [PostponedEventPageAboutSection10868(title: "", paragraphs: [" "])])
        XCTAssertNil(Model(Self.input(about: blank)).about)
    }

    func testVoiceOverReadsOneOrderInEveryArrangementAndTheLayoutPlans() {
        XCTAssertEqual(Model.readingOrder, [.title, .status, .anchor, .timeline, .originals])
        let priorities = Model.readingOrder.map(Model.sortPriority)
        XCTAssertEqual(priorities, priorities.sorted(by: >), "earlier blocks read first")
        XCTAssertEqual(Set(priorities).count, priorities.count)

        // Phone and accessibility sizes stack; a regular or unspecified width tries side by side first.
        XCTAssertEqual(Model.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.heroColumns(.stacked), [[.title, .status, .anchor, .timeline]])
        XCTAssertEqual(Model.heroColumns(.sideBySide), [[.title, .status, .timeline], [.anchor]],
                       "wide: the summary and status timeline in one column, the chart in the other")
        XCTAssertEqual(Model(Self.input()).input.history.plotHeight, 240, "the owner's height; never shrunk here")
    }
}

private extension PostponedEventPageMode10868 {
    static let allModes: [PostponedEventPageMode10868] = [.page, .history, .catalogue, .original, .about]
}
