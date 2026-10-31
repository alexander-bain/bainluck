import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game screen composed from the accepted leaves.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition only: which actual leaf Views the page mounts at each game
/// phase, that each receives the owner's input unchanged, the matrix as laid
/// out (away first, its lead column, every provenance line, its spoken words
/// and the compact score), the story stream's card-to-leaf wiring, the
/// activation hook before each leaf action and binding write, the full-size
/// history without its expand control, the arrangement candidates, All props,
/// and that nothing fires passively. Each leaf's own rules stay with its own
/// tests; nothing here claims a rendered fit, a native runtime, VoiceOver
/// behaviour, a stream hold qualification or a production binding.
///
/// RETAINED values, Chicago White Sox at Houston Astros, September 30, 2026
/// (event 15321836; `BaseballRetained10868` names every source and sha256):
/// - the four final stories are the production deal (`MLBFinalDeck11284`) on
///   the retained `/game-markets` and `/related-futures` with the final 3–7;
/// - the matrix figures: pre-match Kalshi 0.585 / 0.415 served as 59 / 41;
///   the served current pair 0.001 / 0.999 (0 / 100) at 00:15:57Z; the final
///   runs 3 and 7; the served verdict "away";
/// - the history points: the last pregame blend row 20:58Z 0.589, then 21:00Z
///   0.5755, 21:09Z 0.592895 and the last real row 00:18Z 0.010558 — a REDUCED
///   SUBSET, one run per span consecutive in it; never one run across an
///   omitted span;
/// - the run lines 9+ / 10+ by their served option keys;
/// - the fifth story, extra innings, on the retained live Kalshi row
///   (`BaseballRetained10868.liveExtraRow`) with the owner's admission of its
///   own served values — the final body serves no such row, so the final deal
///   above has four stories.
///
/// CONSTRUCTED owner input (this layer resolves none of it): every display
/// word, figure text, clock line, colour, tick, scope, story link, copy and
/// phase; and the before-first-pitch and during-play inputs, which are
/// same-game phase-safety checks built from the retained values and earn no
/// route credit of their own.
@MainActor
final class BaseballEventPagePresentation10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias Page = BaseballEventPagePresentation10868
    private typealias Model = BaseballEventPageModel10868

    // MARK: Owner input

    /// CONSTRUCTED tints.
    private static let homeTint = Color(red: 0.0, green: 0.18, blue: 0.38)
    private static let awayTint = Color(red: 0.1, green: 0.1, blue: 0.1)
    private static let astros = BaseballTeam10868(name: "Houston Astros", short: "Astros", tint: homeTint)
    private static let whiteSox = BaseballTeam10868(name: "Chicago White Sox", short: "White Sox", tint: awayTint)

    private static func value(_ text: String, _ spoken: String) -> BaseballSlot10868 { .value(text, spoken: spoken) }

    private static let pregameColumn = BaseballColumn10868(title: "Pregame chance", provenance: "Pre-match · Kalshi")

    private static func matrix(_ phase: BaseballEventPagePhase10868) -> BaseballMatrix10868 {
        switch phase {
        case .before:
            return .before(BaseballBeforeMatrix10868(
                chance: BaseballColumn10868(title: "Current chance", provenance: "Recorded Sep 30, 1:58 PM"),
                home: BaseballBeforeRow10868(chance: value("59%", "59 percent")),
                away: BaseballBeforeRow10868(chance: value("41%", "41 percent"))))
        case .live:
            return .live(BaseballLiveMatrix10868(
                pregameChance: pregameColumn,
                currentChance: BaseballColumn10868(title: "Current chance", provenance: "Recorded Sep 30, 5:15 PM"),
                runs: BaseballColumn10868(title: "Runs", provenance: nil),
                home: BaseballLiveRow10868(pregameChance: value("59%", "59 percent"),
                                           currentChance: value("<1%", "under 1 percent"), runs: value("3", "3 runs")),
                away: BaseballLiveRow10868(pregameChance: value("41%", "41 percent"),
                                           currentChance: value(">99%", "over 99 percent"), runs: value("7", "7 runs"))))
        case .final:
            return .final(BaseballFinalMatrix10868(
                pregameChance: pregameColumn,
                finalRuns: BaseballColumn10868(title: "Final runs", provenance: "Final score"),
                home: BaseballFinalRow10868(pregameChance: value("59%", "59 percent"), finalRuns: value("3", "3 runs"),
                                            result: "Lost"),
                away: BaseballFinalRow10868(pregameChance: value("41%", "41 percent"), finalRuns: value("7", "7 runs"),
                                            result: "Won")))
        }
    }

    private static func headline(_ phase: BaseballEventPagePhase10868,
                                 matrix: BaseballMatrix10868? = nil) -> BaseballHeadlineInput10868 {
        let state: (String, String?) = switch phase {
        case .before: ("Before first pitch", "Wed, Sep 30 · First pitch 2:00 PM")
        case .live: ("Live", "Inning unavailable")
        case .final: ("Final", "Wed, Sep 30")
        }
        return BaseballHeadlineInput10868(
            eyebrow: "MLB", state: state.0, stateContext: state.1, home: astros, away: whiteSox,
            matrix: matrix ?? Self.matrix(phase),
            projection: BaseballProjection10868(title: "Projected final",
                                                reading: .unavailable("Projected final unavailable")),
            spokenLabel: "Baseball win chances and runs")
    }

    // MARK: History — the real home blend points only

    private static let seriesID = "blend:15321836:home"
    private static let pregameX = 1_790_801_880.0               // 2026-09-30T20:58:00Z
    private static let firstPitchX = 1_790_802_000.0            // 2026-09-30T21:00:00Z
    private static let ninthMinuteX = 1_790_802_540.0           // 2026-09-30T21:09:00Z
    private static let lastRowX = 1_790_813_880.0               // 2026-10-01T00:18:00Z

    private static func point(_ stamp: String, _ x: Double, _ probability: Double,
                              _ style: FieldHistoryMarkStyle10868 = .filled) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: "\(seriesID)#\(stamp)", x: x, probability: probability, style: style)
    }

    private static func history(_ phase: BaseballEventPagePhase10868) -> FieldHistoryInput10868 {
        let pregame = point("2026-09-30T20:58:00+00:00", pregameX, 0.589, .hollow)
        let opening = FieldHistoryRun10868(id: "\(seriesID)#run-1", points: [
            pregame, point("2026-09-30T21:00:00+00:00", firstPitchX, 0.5755),
            point("2026-09-30T21:09:00+00:00", ninthMinuteX, 0.592895),
        ])
        let runs: [FieldHistoryRun10868] = switch phase {
        case .before: [FieldHistoryRun10868(id: "\(seriesID)#run-1", points: [pregame])]
        case .live: [opening]
        case .final: [opening, FieldHistoryRun10868(id: "\(seriesID)#run-2", points: [
            point("2026-10-01T00:18:00+00:00", lastRowX, 0.010558)])]
        }
        let series = FieldHistorySeries10868(
            id: seriesID, name: "Houston Astros", shape: .circle, tint: homeTint, runs: runs, links: [],
            labelPointID: nil,
            before: .observation(pointID: pregame.id, figure: "59%", provenance: "Last pregame · Sep 30, 1:58 PM"),
            recorded: .absent(words: "Not recorded"), absentWords: "No recorded history", choose: nil)
        let upper: Double = switch phase {
        case .before: firstPitchX
        case .live: ninthMinuteX
        case .final: lastRowX
        }
        return FieldHistoryInput10868(
            title: "Win probability", caption: phase == .before ? "Before game" : "Game history",
            series: [series], selection: .none,
            domain: FieldHistoryDomain10868(lower: pregameX, upper: upper), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: "Pregame"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow · last pregame", filled: nil),
            comparisonExplanation: nil, notes: ["Gaps remain blank."],
            summary: "Houston Astros win probability, recorded observations only.", plotHeight: 230,
            unboundReadingWords: "Not recorded", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: FieldHistoryAction10868(id: "history.details", label: "History & source details",
                                             spokenLabel: nil, isAvailable: false),
            expand: FieldHistoryAction10868(id: "history.expand", label: "Full chart",
                                            spokenLabel: "Expand baseball win probability history", isAvailable: true),
            inspect: nil, previous: nil, next: nil, inspection: nil)
    }

    // MARK: Stories — the production deal on the retained bodies

    private struct Stories {
        let homeRuns: BaseballHomeRunsStory10868
        let strikeouts: BaseballStrikeoutsStory10868
        let finalTotals: BaseballFinalTotals10868
        let series: BaseballSeriesStory10868
    }

    private static func stories() throws -> Stories {
        let deck = MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: F.eventID, sportKey: "baseball_mlb", status: "completed",
            homeTeam: "Houston Astros", awayTeam: "Chicago White Sox", homeScore: 3, awayScore: 7,
            gameMarkets: try F.markets(), relatedFutures: try F.related()))
        var homeRuns: MLBHomeRunCard11284?
        var strikeouts: MLBMilestoneCard11284?
        var totals: MLBTotalsCard11284?
        var series: MLBSeriesCard11284?
        for card in deck {
            switch card {
            case .homeRuns(let found): homeRuns = found
            case .strikeouts(let found): strikeouts = found
            case .totals(let found): totals = found
            case .series(let found): series = found
            case .extraInnings: break
            }
        }
        let ladder = try XCTUnwrap(strikeouts)
        let lines = try XCTUnwrap(totals)
        let markets = try XCTUnwrap(series)
        return Stories(
            homeRuns: BaseballHomeRunsStory10868(card: try XCTUnwrap(homeRuns), awayColor: awayTint, homeColor: homeTint),
            strikeouts: BaseballStrikeoutsStory10868(card: ladder, selectedRowID: ladder.targets[1].rowID,
                                                     color: homeTint),
            finalTotals: BaseballFinalTotals10868(card: lines, selectedOptionKey: "o:244311417",
                                                  homeName: "Astros", awayName: "White Sox",
                                                  homeColor: homeTint, awayColor: awayTint,
                                                  homeScore: 3, awayScore: 7),
            series: BaseballSeriesStory10868(card: markets, selectedQuestionKey: markets.questions.first?.questionKey,
                                             selectedOptionKey: nil, color: homeTint))
    }

    /// CONSTRUCTED run milestones on the served 9+ and 10+ option keys, every
    /// chance unavailable as the retained bodies leave them.
    private static func milestones(_ phase: TotalMilestonePhase10868) -> TotalMilestoneInput10868 {
        let rows = [(9, "o:244311410"), (10, "o:244311417")].map { count, id in
            TotalMilestoneRow10868(
                id: id, quantity: Double(count), quantityLabel: "\(count)+", title: "\(count)+ runs",
                before: nil, beforeMissing: "Pregame chance unavailable",
                current: .unavailable("In-game chance unavailable"), performance: nil,
                result: .unconfirmed("Result unavailable"))
        }
        return TotalMilestoneInput10868(
            phase: phase, eyebrow: "TOTAL RUNS · BOTH TEAMS",
            title: phase == .before ? "How many runs?" : "Runs so far against the milestones",
            chartTitle: "Chance of reaching each total", quantityAxisTitle: "Total runs in the game",
            milestones: rows, selectedMilestoneID: "o:244311417", actual: nil, projection: nil,
            quantityDomain: TotalMilestoneDomain10868(lower: 0, upper: 11),
            quantityTicks: [TotalMilestoneTick10868(value: 0, text: "0")],
            chanceTicks: [TotalMilestoneTick10868(value: 0, text: "0%"), TotalMilestoneTick10868(value: 1, text: "100%")],
            timing: TotalMilestoneTiming10868(milestoneID: "o:244311417", title: "10+ runs · chance timing",
                                              lines: ["Pregame chance: Pregame chance unavailable"]),
            markStyle: .stems)
    }

    /// The fifth story on the retained live row with the owner's admission of
    /// its own served values (`BaseballRetained10868.liveExtraAdmission`), at
    /// the CONSTRUCTED reader time `extraNow`.
    private static func extraStory(selected: String? = nil) throws -> BaseballExtraInningsStory10868 {
        try XCTUnwrap(BaseballExtraInningsAdapter10868.story(
            try F.liveEvent(), markets: try F.liveExtraMarkets(), admissions: [try F.liveExtraAdmission()],
            selected: selected, host: F.milestoneHost(F.extraNow)))
    }

    // MARK: Stream and page

    private static func scope(_ phase: BaseballEventPagePhase10868) -> String { "mlb:15321836:\(phase)" }

    private static func name(_ card: BaseballEventPageCard10868) -> String {
        switch card {
        case .history: "Win probability"
        case .homeRuns: "Home runs"
        case .strikeouts: "Hunter Brown · Strikeouts"
        case .totals: "Run totals"
        case .extraInnings: "Extra innings"
        case .series: "The series"
        }
    }

    private static func offered(_ phase: BaseballEventPagePhase10868) -> [BaseballEventPageCard10868] {
        phase == .final ? [.homeRuns, .strikeouts, .totals, .series] : [.totals, .series]
    }

    private static func stream(_ phase: BaseballEventPagePhase10868, cards: [BaseballEventPageCard10868],
                               wide: Bool) -> StoryStreamPresentation10868 {
        let scope = Self.scope(phase)
        func ref(_ card: BaseballEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let second = cards.count > 1 ? cards[1] : nil
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Explore the game",
            cards: cards.map { StoryStreamPresentation10868.Card(id: $0.rawValue, name: name($0)) },
            primary: cards.first.map(ref), companion: second.map(ref),
            companionLabel: second == nil ? nil : "Next", wide: wide,
            position: cards.isEmpty ? nil : "1 of \(cards.count)",
            status: cards.count > 1 ? "Use Previous or Next to see each story" : nil,
            dwellFraction: nil, playback: nil,
            previous: cards.count > 1 ? cards.last.map(ref) : nil, next: second.map(ref))
    }

    private static let copy = BaseballEventPageCopy10868(
        storiesLabel: "Game stories",
        storyUnavailable: "This story isn’t available for this game state. Every original is still in All props.",
        matrixUnavailable: "Comparison unavailable for this game state",
        allPropsLabel: "All props · 623")

    private static func page(_ phase: BaseballEventPagePhase10868, stories: Stories,
                             totals: BaseballTotalsStory10868?? = nil,
                             links: [BaseballEventPageStory10868]? = nil,
                             matrix: BaseballMatrix10868? = nil,
                             allProps: String?? = nil,
                             extra: BaseballExtraInningsStory10868? = nil,
                             wide: Bool = false) -> BaseballEventPageInput10868 {
        let cards = offered(phase)
        let defaultTotals: BaseballTotalsStory10868 = switch phase {
        case .before: .milestones(milestones(.before))
        case .live: .milestones(milestones(.during))
        case .final: .finalTargets(stories.finalTotals)
        }
        let words = BaseballEventPageCopy10868(
            storiesLabel: copy.storiesLabel, storyUnavailable: copy.storyUnavailable,
            matrixUnavailable: copy.matrixUnavailable, allPropsLabel: allProps ?? copy.allPropsLabel)
        // Every phase is handed the final stories too: the page must hide them
        // outside their own phase.
        return BaseballEventPageInput10868(
            phase: phase, headline: headline(phase, matrix: matrix), history: history(phase),
            homeRuns: stories.homeRuns, strikeouts: stories.strikeouts,
            totals: totals ?? defaultTotals, extraInnings: extra, series: stories.series,
            stream: stream(phase, cards: cards, wide: wide),
            stories: links ?? cards.map { BaseballEventPageStory10868(cardID: $0.rawValue, card: $0) },
            copy: words)
    }

    /// Every host callback, each writing its exact value to `log`.
    private static func connected(_ input: BaseballEventPageInput10868, log: @escaping (String) -> Void,
                                  mode: BaseballEventPageMode10868 = .page,
                                  timing: Binding<Bool>? = nil) -> Page {
        Page(
            input: input, mode: mode,
            onAllProps: { log("allProps") },
            onOriginalSelect: { _ in log("originalSelect") },
            onOriginalHistory: { _ in log("originalHistory") },
            onStoryIntent: { _ in log("stream") },
            onHistoryAction: { log("history:\($0)") },
            onHistoryInspectionChoice: { log("inspect:\($0)") },
            onHistoryPlotPosition: { log("plot:\($0)") },
            onHomeRunDetails: { log("homeRunDetails:\($0)") },
            onStrikeoutSelect: { log("strikeoutSelect:\($0)") },
            onStrikeoutDetails: { log("strikeoutDetails:\($0)") },
            onTotalSelect: { log("totalSelect:\($0)") },
            onTotalMilestoneDetails: { log("milestoneDetails:\($0)") },
            onTotalLineDetails: { log("lineDetails:\($0)") },
            onSeriesMarket: { log("seriesMarket:\($0)") },
            onSeriesOption: { log("seriesOption:\($0):\($1)") },
            onSeriesDetails: { log("seriesDetails:\($0)") },
            onExtraInningsSelect: { log("extraSelect:\($0)") },
            onExtraInningsDetails: { log("extraDetails:\($0)") },
            totalTimingExpanded: timing)
    }

    /// The activation the stream hands a displayed card, recording its request.
    private static func activation(_ input: BaseballEventPageInput10868, _ card: BaseballEventPageCard10868,
                                   log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let ref = StoryStreamPresentation10868.CardRef(scope: input.stream.scope, id: card.rawValue)
        return StoryStreamCardActivation10868(card: ref, intents: [.interaction(scope: input.stream.scope, card: ref)]) {
            if case .interaction(_, let held) = $0 { log("hold:\(held?.id ?? "-")") } else { log("other") }
        }
    }

    // MARK: Phases

    func testBeforeAndDuringPlayMountOnlyRunMilestonesAndTheSeriesAndHideEveryFinalStory() throws {
        let stories = try Self.stories()
        let phases: [(BaseballEventPagePhase10868, TotalMilestonePhase10868)] = [(.before, .before), (.live, .during)]
        for (phase, totalPhase) in phases {
            let input = Self.page(phase, stories: stories)
            let model = Model(input)
            let view = Self.connected(input, log: { _ in })

            XCTAssertNil(model.homeRuns, "\(phase)")
            XCTAssertNil(model.strikeouts, "\(phase)")
            XCTAssertEqual(model.totals, .milestones(Self.milestones(totalPhase)), "\(phase)")
            XCTAssertEqual(model.series, stories.series, "\(phase)")
            XCTAssertEqual(BaseballEventPageCard10868.allCases.filter(model.isMounted), [.history, .totals, .series])

            XCTAssertNil(view.homeRunsContent(), "\(phase)")
            XCTAssertNil(view.strikeoutsContent(), "\(phase)")
            XCTAssertNil(view.finalTotalsContent(), "\(phase)")
            XCTAssertEqual(view.totalMilestonesContent()?.input, Self.milestones(totalPhase))
            XCTAssertEqual(view.seriesContent()?.card, stories.series.card)
            XCTAssertFalse(view.shows(.homeRuns))
            XCTAssertTrue(view.shows(.totals))
        }
    }

    func testAfterTheFinalTheActualLeavesReceiveTheOwnersStoriesUnchanged() throws {
        let stories = try Self.stories()
        let input = Self.page(.final, stories: stories)
        let model = Model(input)
        let view = Self.connected(input, log: { _ in })

        XCTAssertEqual(BaseballEventPageCard10868.allCases.filter(model.isMounted),
                       [.history, .homeRuns, .strikeouts, .totals, .series])
        XCTAssertEqual(model.totals, .finalTargets(stories.finalTotals))

        let homeRuns = try XCTUnwrap(view.homeRunsContent())
        XCTAssertEqual(homeRuns.card, stories.homeRuns.card)
        XCTAssertEqual(homeRuns.card.entries.map(\.player), ["Yordan Alvarez", "Christian Walker", "Munetaka Murakami"])
        XCTAssertEqual(homeRuns.awayColor, Self.awayTint)
        XCTAssertEqual(homeRuns.homeColor, Self.homeTint)

        let strikeouts = try XCTUnwrap(view.strikeoutsContent())
        XCTAssertEqual(strikeouts.card.player, "Hunter Brown")
        XCTAssertEqual(strikeouts.selectedRowID, "Hunter Brown: Strikeouts O/U 6.5-Over")
        XCTAssertFalse(strikeouts.expanded)
        XCTAssertEqual(view.strikeoutsContent(expanded: true)?.expanded, true)

        let totals = try XCTUnwrap(view.finalTotalsContent())
        XCTAssertEqual(totals.card, stories.finalTotals.card)
        XCTAssertEqual(totals.card.actualTotal, 10)
        XCTAssertEqual(totals.selectedOptionKey, "o:244311417")
        XCTAssertEqual([totals.awayName, totals.homeName], ["White Sox", "Astros"])
        XCTAssertEqual(totals.homeScore, 3)
        XCTAssertEqual(totals.awayScore, 7)
        XCTAssertNil(view.totalMilestonesContent(), "the milestones form never draws after the final")

        let series = try XCTUnwrap(view.seriesContent())
        XCTAssertEqual(series.card.questions.count, 4)
        XCTAssertEqual(series.selectedQuestionKey, stories.series.card.questions.first?.questionKey)
        XCTAssertNil(series.selectedOptionKey)
    }

    func testARunTotalsFormOutsideItsOwnPhaseIsNeverDrawn() throws {
        let stories = try Self.stories()
        let cases: [(BaseballEventPagePhase10868, BaseballTotalsStory10868)] = [
            (.before, .milestones(Self.milestones(.during))),
            (.before, .finalTargets(stories.finalTotals)),
            (.live, .milestones(Self.milestones(.before))),
            (.live, .finalTargets(stories.finalTotals)),
            (.final, .milestones(Self.milestones(.final))),
            (.final, .milestones(Self.milestones(.during))),
        ]
        for (phase, totals) in cases {
            let model = Model(Self.page(phase, stories: stories, totals: totals))
            XCTAssertNil(model.totals, "\(phase)")
            XCTAssertFalse(model.isMounted(.totals), "\(phase)")
            XCTAssertNil(model.storyCard("totals"), "\(phase)")
        }
        XCTAssertNil(Model(Self.page(.final, stories: stories, totals: .some(nil))).totals)
    }

    // MARK: Story links

    func testAStreamCardShowsOnlyTheOneStoryItsExactLinkNamesThisPhaseMountsAndTheHostCanDrive() throws {
        let stories = try Self.stories()
        let input = Self.page(.final, stories: stories)
        let model = Model(input)
        for card in [BaseballEventPageCard10868.homeRuns, .strikeouts, .totals, .series] {
            XCTAssertEqual(model.storyCard(card.rawValue), card)
        }
        XCTAssertNil(model.storyCard("history"), "the anchor is never a stream card")
        XCTAssertNil(model.storyCard("extraInnings"), "an id with no link is the unavailable cell")

        // The owner's link decides, never a same-named neighbour.
        let renamed = Model(Self.page(.final, stories: stories, links: [
            BaseballEventPageStory10868(cardID: "totals", card: .series),
        ]))
        XCTAssertEqual(renamed.storyCard("totals"), .series)
        XCTAssertNil(renamed.storyCard("series"))
        let doubled = Model(Self.page(.final, stories: stories, links: [
            BaseballEventPageStory10868(cardID: "homeRuns", card: .homeRuns),
            BaseballEventPageStory10868(cardID: "homeRuns", card: .strikeouts),
        ]))
        XCTAssertNil(doubled.storyCard("homeRuns"), "two links for one id name no single story")
        let anchored = Model(Self.page(.final, stories: stories, links: [
            BaseballEventPageStory10868(cardID: "chart", card: .history),
        ]))
        XCTAssertNil(anchored.storyCard("chart"))

        // A linked final story during play is not mounted, so not shown.
        let live = Model(Self.page(.live, stories: stories, links: [
            BaseballEventPageStory10868(cardID: "homeRuns", card: .homeRuns),
        ]))
        XCTAssertNil(live.storyCard("homeRuns"))

        // The host must supply every control a leaf always draws.
        let quiet = Page(input: input)
        XCTAssertEqual(quiet.storyKind("homeRuns"), .homeRuns, "its Details control is optional")
        XCTAssertNil(quiet.storyKind("strikeouts"))
        XCTAssertNil(quiet.storyKind("totals"))
        XCTAssertNil(quiet.storyKind("series"))
        XCTAssertFalse(Page(input: input, onTotalSelect: { _ in }).shows(.totals), "Details is required too")
        XCTAssertFalse(Page(input: input, onSeriesMarket: { _ in }).shows(.series), "the outcome tile is required too")
        XCTAssertTrue(Page(input: input, onSeriesMarket: { _ in }, onSeriesOption: { _, _ in }).shows(.series))
        let connected = Self.connected(input, log: { _ in })
        for card in [BaseballEventPageCard10868.homeRuns, .strikeouts, .totals, .series] {
            XCTAssertEqual(connected.storyKind(card.rawValue), card)
        }
        XCTAssertTrue(quiet.shows(.history))
        // Before the final the milestones need no callback: they draw no inert control.
        XCTAssertEqual(Page(input: Self.page(.live, stories: stories)).storyKind("totals"), .totals)
    }

    // MARK: Activation before every action

    func testAStoryActionInTheStreamRequestsTheHoldBeforeTheExactCallbackAndNothingFiresPassively() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let stories = try Self.stories()
        let input = Self.page(.final, stories: stories, wide: true)
        let view = Self.connected(input, log: record)
        func activation(_ card: BaseballEventPageCard10868) -> StoryStreamCardActivation10868 {
            Self.activation(input, card, log: record)
        }

        // The hook is the one the real stream hands its displayed primary card.
        let resolved = input.stream.resolve(reduceMotion: false, actionable: true)
        let primary = StoryStreamPresentation10868.CardRef(scope: input.stream.scope, id: "homeRuns")
        XCTAssertEqual(input.stream.activationIntents(for: primary, resolved: resolved),
                       [.interaction(scope: input.stream.scope, card: primary)])

        // Building every leaf, in stream and full-size form, acts on nothing.
        let homeRuns = try XCTUnwrap(view.homeRunsContent(activation: activation(.homeRuns)))
        let strikeouts = try XCTUnwrap(view.strikeoutsContent(activation: activation(.strikeouts)))
        let totals = try XCTUnwrap(view.finalTotalsContent(activation: activation(.totals)))
        let series = try XCTUnwrap(view.seriesContent(activation: activation(.series)))
        _ = view.historyContent(reader: false)
        _ = view.historyContent(reader: true)
        _ = view.homeRunsContent()
        _ = view.catalogueContent()
        _ = view.originalDetailsContent()
        XCTAssertEqual(log, [])

        let homeRun = stories.homeRuns.card.entries[0].original.id
        let target = stories.strikeouts.card.targets[2].rowID
        let ladderOriginal = stories.strikeouts.card.targets[1].original.id
        let line = stories.finalTotals.card.lines[0].optionKey
        let lineOriginal = stories.finalTotals.card.lines[7].original.id
        let market = stories.series.card.questions[1].questionKey
        let outcome = stories.series.card.questions[1].options[0].optionKey
        let seriesOriginal = stories.series.card.questions[0].options[0].original.id

        // In the stream: the hold first, then the exact owner action.
        homeRuns.onDetails?(homeRun)
        strikeouts.onSelect(target)
        strikeouts.onDetails?(ladderOriginal)
        totals.onSelect(line)
        totals.onDetails(lineOriginal)
        series.onSelectMarket(market)
        series.onSelectOption(market, outcome)
        series.onDetails?(seriesOriginal)
        XCTAssertEqual(log, [
            "hold:homeRuns", "homeRunDetails:\(homeRun)",
            "hold:strikeouts", "strikeoutSelect:\(target)", "hold:strikeouts", "strikeoutDetails:\(ladderOriginal)",
            "hold:totals", "totalSelect:\(line)", "hold:totals", "lineDetails:\(lineOriginal)",
            "hold:series", "seriesMarket:\(market)", "hold:series", "seriesOption:\(market):\(outcome)",
            "hold:series", "seriesDetails:\(seriesOriginal)",
        ])

        // Full-size content and the anchor: the exact callback, no hold.
        log = []
        let reader = Self.connected(input, log: record, mode: .reader(.strikeouts))
        reader.strikeoutsContent(expanded: true)?.onSelect(target)
        view.finalTotalsContent(expanded: true)?.onDetails(lineOriginal)
        view.seriesContent()?.onSelectOption(market, outcome)
        view.homeRunsContent()?.onDetails?(homeRun)
        view.historyContent(reader: false).onAction?("history.expand")
        view.historyContent(reader: true).onInspectionChoice?("choice.0018")
        view.historyContent(reader: false).onPlotPosition?(Self.lastRowX)
        view.openAllProps()
        XCTAssertEqual(log, ["strikeoutSelect:\(target)", "lineDetails:\(lineOriginal)",
                             "seriesOption:\(market):\(outcome)", "homeRunDetails:\(homeRun)",
                             "history:history.expand", "inspect:choice.0018", "plot:\(Self.lastRowX)", "allProps"])

        // Without host callbacks nothing acts, even inside the stream.
        log = []
        let quiet = Page(input: input)
        XCTAssertNil(quiet.strikeoutsContent(activation: activation(.strikeouts)))
        XCTAssertNil(quiet.finalTotalsContent(activation: activation(.totals)))
        XCTAssertNil(quiet.seriesContent(activation: activation(.series)))
        XCTAssertNil(quiet.homeRunsContent(activation: activation(.homeRuns))?.onDetails)
        XCTAssertNil(quiet.historyContent(reader: false).onAction)
        XCTAssertNil(Page(input: input, onStrikeoutSelect: { _ in }).strikeoutsContent()?.onDetails)
        XCTAssertNil(Page(input: input, onSeriesMarket: { _ in }, onSeriesOption: { _, _ in }).seriesContent()?.onDetails)
        quiet.openAllProps()
        XCTAssertEqual(log, [])
    }

    func testRunMilestoneActionsAndTheTimingDisclosureInTheStreamRequestTheHoldFirstAndReadersPassThrough() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        var expanded = false
        let owner = Binding<Bool>(get: { expanded }, set: { record("timing:\($0)"); expanded = $0 })
        let input = Self.page(.live, stories: try Self.stories())
        let view = Self.connected(input, log: record, timing: owner)

        let milestones = try XCTUnwrap(view.totalMilestonesContent(activation: Self.activation(input, .totals, log: record)))
        XCTAssertEqual(milestones.input, Self.milestones(.during))
        XCTAssertEqual(milestones.timingExpanded?.wrappedValue, false)
        XCTAssertEqual(log, [], "building and reading the disclosure asks for nothing")

        milestones.onSelect?("o:244311410")
        milestones.onDetails?("o:244311410")
        milestones.timingExpanded!.wrappedValue = true
        XCTAssertEqual(log, ["hold:totals", "totalSelect:o:244311410", "hold:totals", "milestoneDetails:o:244311410",
                             "hold:totals", "timing:true"])
        XCTAssertTrue(expanded)

        log = []
        let full = try XCTUnwrap(view.totalMilestonesContent())
        full.timingExpanded!.wrappedValue = false
        full.onSelect?("o:244311417")
        XCTAssertEqual(log, ["timing:false", "totalSelect:o:244311417"])

        let quiet = Page(input: input)
        XCTAssertNil(quiet.totalMilestonesContent(activation: Self.activation(input, .totals, log: record))?.timingExpanded)
        XCTAssertNil(quiet.totalMilestonesContent()?.onSelect)
        XCTAssertNil(quiet.totalMilestonesContent()?.onDetails)
    }

    func testTheRelaysCallTheHookFirstPassTheExactValueAndNeverInventAnAction() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let input = Self.page(.final, stories: try Self.stories())
        let hook = Self.activation(input, .series, log: record)

        let action: (String) -> Void = { record("action:\($0)") }
        let none: ((String) -> Void)? = nil
        XCTAssertNil(Page.relay(none, through: hook))
        Page.relay(action, through: nil)?("a")
        Page.relay(action, through: hook)?("b")
        XCTAssertEqual(log, ["action:a", "hold:series", "action:b"])

        log = []
        let pair: (String, String) -> Void = { record("pair:\($0):\($1)") }
        let noPair: ((String, String) -> Void)? = nil
        XCTAssertNil(Page.relayPair(noPair, through: hook))
        Page.relayPair(pair, through: nil)?("m", "o")
        Page.relayPair(pair, through: hook)?("m", "p")
        XCTAssertEqual(log, ["pair:m:o", "hold:series", "pair:m:p"])

        log = []
        var open = false
        let owner = Binding<Bool>(get: { open }, set: { record("owner:\($0)"); open = $0 })
        let noBinding: Binding<Bool>? = nil
        XCTAssertNil(Page.relay(noBinding, through: hook))
        let relayed = try XCTUnwrap(Page.relay(owner, through: hook))
        XCTAssertFalse(relayed.wrappedValue)
        XCTAssertEqual(log, [])
        relayed.wrappedValue = true
        let direct = try XCTUnwrap(Page.relay(owner, through: nil))
        direct.wrappedValue = false
        XCTAssertEqual(log, ["hold:series", "owner:true", "owner:false"])
        XCTAssertFalse(open)
    }

    // MARK: Full-size history

    func testTheFullSizeHistoryDropsOnlyItsExpandControlAndKeepsEveryOtherOwnerField() throws {
        let input = Self.page(.final, stories: try Self.stories())
        let model = Model(input)
        let reader = model.readerHistory
        let anchor = input.history

        XCTAssertEqual(anchor.expand?.id, "history.expand")
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertEqual(reader.series, anchor.series)
        XCTAssertEqual(reader.domain, anchor.domain)
        XCTAssertEqual(reader.readout, anchor.readout)
        XCTAssertEqual(reader.notes, anchor.notes)
        XCTAssertEqual(reader.summary, anchor.summary)
        XCTAssertEqual(reader.details, anchor.details)
        XCTAssertEqual(reader.inspect, anchor.inspect)
        XCTAssertEqual(reader.markKey, anchor.markKey)
        XCTAssertEqual(reader.plotAbsence, anchor.plotAbsence)
        XCTAssertEqual(reader.unboundReadingWords, anchor.unboundReadingWords)
        // Never one run across an omitted span: the subset's two runs stay two.
        XCTAssertEqual(reader.series.first?.runs.map { $0.points.count }, [3, 1])

        let view = Page(input: input)
        XCTAssertEqual(view.historyContent(reader: false).input, anchor)
        XCTAssertEqual(view.historyContent(reader: true).input, reader)
    }

    // MARK: Matrix

    func testTheFinalMatrixLeadsWithFinalRunsAwayFirstWithEveryProvenanceAndItsWords() throws {
        let model = Model(Self.page(.final, stories: try Self.stories()))
        let layout = model.layout

        XCTAssertTrue(model.headlineShows)
        XCTAssertEqual(layout.columns.map(\.title), ["Pregame chance", "Final runs"])
        XCTAssertEqual(layout.lead, 1)
        XCTAssertEqual(layout.runsColumn, 1)
        XCTAssertEqual(layout.rows.map(\.team.name), ["Chicago White Sox", "Houston Astros"])
        XCTAssertEqual(layout.rows.map(\.result), ["Won", "Lost"])
        XCTAssertEqual(layout.rows[0].cells, [Self.value("41%", "41 percent"), Self.value("7", "7 runs")])
        XCTAssertEqual(layout.values(layout.rows[1]).map(\.lead), [false, true])
        XCTAssertEqual(layout.support, ["Pregame chance: Pre-match · Kalshi", "Final runs: Final score"])
        XCTAssertEqual(layout.spoken,
                       "Chicago White Sox: Pregame chance 41 percent, Final runs 7 runs, Won. "
                       + "Houston Astros: Pregame chance 59 percent, Final runs 3 runs, Lost")
        XCTAssertEqual(model.compactScore, "White Sox 7 – 3 Astros")
    }

    func testDuringPlayTheCurrentChanceLeadsAndBeforeFirstPitchTheOnlyColumnIsTheChance() throws {
        let stories = try Self.stories()
        let live = Model(Self.page(.live, stories: stories))
        XCTAssertEqual(live.layout.columns.map(\.title), ["Pregame chance", "Current chance", "Runs"])
        XCTAssertEqual(live.layout.lead, 1)
        XCTAssertEqual(live.layout.runsColumn, 2)
        XCTAssertEqual(live.layout.rows.map { $0.cells[1].text }, [">99%", "<1%"])
        XCTAssertEqual(live.layout.support,
                       ["Pregame chance: Pre-match · Kalshi", "Current chance: Recorded Sep 30, 5:15 PM"],
                       "a column with no provenance says none")
        XCTAssertEqual(live.compactScore, "White Sox 7 – 3 Astros")

        let before = Model(Self.page(.before, stories: stories))
        XCTAssertEqual(before.layout.columns.map(\.title), ["Current chance"])
        XCTAssertEqual(before.layout.lead, 0)
        XCTAssertNil(before.layout.runsColumn)
        XCTAssertNil(before.compactScore, "no runs before first pitch")

        // A missing score is its own words and never a compact score.
        let missing = BaseballSlot10868.unavailable("Score unavailable")
        let noScore = Model(Self.page(.live, stories: stories, matrix: .live(BaseballLiveMatrix10868(
            pregameChance: Self.pregameColumn,
            currentChance: BaseballColumn10868(title: "Current chance", provenance: nil),
            runs: BaseballColumn10868(title: "Runs", provenance: nil),
            home: BaseballLiveRow10868(pregameChance: Self.value("59%", "59 percent"),
                                       currentChance: .unavailable("Win chance unavailable"), runs: missing),
            away: BaseballLiveRow10868(pregameChance: Self.value("41%", "41 percent"),
                                       currentChance: .unavailable("Win chance unavailable"), runs: missing)))))
        XCTAssertNil(noScore.compactScore)
        XCTAssertEqual(noScore.layout.rows.map { $0.cells[2].text }, ["Score unavailable", "Score unavailable"])
        XCTAssertFalse(noScore.layout.rows[0].cells[1].isValue)
    }

    func testAMatrixFromAnotherPhaseIsNeverDrawn() throws {
        let stories = try Self.stories()
        let pairs: [(BaseballEventPagePhase10868, BaseballEventPagePhase10868)] = [(.live, .final), (.final, .live),
                                                                                  (.before, .final)]
        for (phase, other) in pairs {
            let model = Model(Self.page(phase, stories: stories, matrix: Self.matrix(other)))
            XCTAssertFalse(model.headlineShows, "\(phase) page, \(other) matrix")
            XCTAssertNil(model.compactScore)
        }
    }

    // MARK: Arrangement

    func testCompactWideAndAccessibilitySizesChooseTheirArrangements() {
        XCTAssertEqual(Model.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])
    }

    // MARK: All props and Details

    func testAllPropsOpensOnlyWithReadableWordsAndAHostRouteAndTheOriginalLeavesGetTheOwnersFields() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let stories = try Self.stories()
        let input = Self.page(.final, stories: stories)
        let model = Model(input)
        XCTAssertTrue(model.allPropsAvailable(canOpen: true))
        XCTAssertFalse(model.allPropsAvailable(canOpen: false))
        XCTAssertFalse(Model(Self.page(.final, stories: stories, allProps: .some(" "))).allPropsAvailable(canOpen: true))
        XCTAssertFalse(Model(Self.page(.final, stories: stories, allProps: .some(nil))).allPropsAvailable(canOpen: true))
        Self.connected(Self.page(.final, stories: stories, allProps: .some(nil)), log: record).openAllProps()
        XCTAssertEqual(log, [])

        let originals = BaseballEventPageOriginals10868(
            catalogue: nil, selection: nil, heading: "All props", context: "623 originals",
            emptyWords: "No original props recorded for this game", unavailableChoice: "Unnamed original",
            tint: Self.homeTint)
        let view = Page(input: input, mode: .catalogue, originals: originals,
                        onOriginalSelect: { _ in record("select") }, onOriginalHistory: { _ in record("history") })
        let catalogue = try XCTUnwrap(view.catalogueContent())
        XCTAssertNil(catalogue.catalogue)
        XCTAssertEqual(catalogue.heading, "All props")
        XCTAssertEqual(catalogue.context, "623 originals")
        XCTAssertEqual(catalogue.emptyWords, "No original props recorded for this game")
        XCTAssertEqual(catalogue.unavailableChoice, "Unnamed original")
        XCTAssertEqual(catalogue.tint, Self.homeTint)
        XCTAssertNotNil(catalogue.onSelect)
        let details = try XCTUnwrap(view.originalDetailsContent())
        XCTAssertNil(details.selection)
        XCTAssertNil(details.recorded)
        XCTAssertNotNil(details.onHistory)

        XCTAssertNil(Page(input: input).catalogueContent(), "no originals, no catalogue")
        XCTAssertNil(Page(input: input).originalDetailsContent())
        XCTAssertNil(Page(input: input, originals: originals).catalogueContent()?.onSelect)
        XCTAssertNil(Page(input: input, originals: originals).originalDetailsContent()?.onHistory)
        XCTAssertEqual(log, [], "building the modes acts on nothing")
        XCTAssertEqual(BaseballEventPageAccessibilityID10868.card(.series), "baseballEventPage10868.card.series")
    }

    // MARK: Extra innings — the fifth story

    func testExtraInningsIsMountedInEveryPhaseItIsSuppliedAndItsLeafGetsTheStoryUnchanged() throws {
        let stories = try Self.stories()
        let extra = try Self.extraStory()
        for phase in [BaseballEventPagePhase10868.before, .live, .final] {
            let links = (Self.offered(phase) + [.extraInnings]).map {
                BaseballEventPageStory10868(cardID: $0.rawValue, card: $0)
            }
            let input = Self.page(phase, stories: stories, links: links, extra: extra)
            let model = Model(input)
            XCTAssertEqual(model.extraInnings, extra, "\(phase)")
            XCTAssertTrue(model.isMounted(.extraInnings), "\(phase)")
            XCTAssertEqual(model.storyCard("extraInnings"), .extraInnings, "\(phase)")
            let quiet = Page(input: input)
            XCTAssertEqual(quiet.storyKind("extraInnings"), .extraInnings, "its chooser and Details are optional")
            XCTAssertTrue(quiet.shows(.extraInnings))
            XCTAssertEqual(quiet.extraInningsContent()?.story, extra)
            XCTAssertEqual(quiet.extraInningsContent()?.expanded, false)
            XCTAssertEqual(quiet.extraInningsContent(expanded: true)?.expanded, true)
        }
        // Not supplied: not mounted, and its link is the unavailable cell.
        let none = Model(Self.page(.final, stories: stories, links: [
            BaseballEventPageStory10868(cardID: "extraInnings", card: .extraInnings),
        ]))
        XCTAssertFalse(none.isMounted(.extraInnings))
        XCTAssertNil(none.storyCard("extraInnings"))
        XCTAssertNil(Page(input: Self.page(.final, stories: stories)).extraInningsContent())
    }

    func testAnExtraInningsActionInTheStreamRequestsTheHoldBeforeTheExactCallbackAndReadersPassThrough() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let extra = try Self.extraStory()
        let outcome = try XCTUnwrap(extra.options.first?.id)
        let input = Self.page(.live, stories: try Self.stories(), extra: extra)
        let view = Self.connected(input, log: record)

        let leaf = try XCTUnwrap(view.extraInningsContent(activation: Self.activation(input, .extraInnings, log: record)))
        XCTAssertEqual(log, [], "building the leaf asks for nothing")
        leaf.onSelect?(outcome)
        leaf.onDetails?(outcome)
        XCTAssertEqual(log, ["hold:extraInnings", "extraSelect:\(outcome)", "hold:extraInnings", "extraDetails:\(outcome)"])

        log = []
        let reader = Self.connected(input, log: record, mode: .reader(.extraInnings))
        reader.extraInningsContent(expanded: true)?.onDetails?(outcome)
        reader.extraInningsContent(expanded: true)?.onSelect?(outcome)
        XCTAssertEqual(log, ["extraDetails:\(outcome)", "extraSelect:\(outcome)"])

        let quiet = Page(input: input)
        XCTAssertNil(quiet.extraInningsContent(activation: Self.activation(input, .extraInnings, log: record))?.onSelect)
        XCTAssertNil(quiet.extraInningsContent()?.onDetails)
    }
}
