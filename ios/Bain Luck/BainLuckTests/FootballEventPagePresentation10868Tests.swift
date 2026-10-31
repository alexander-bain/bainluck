import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the football event screen composed from the accepted leaves, for
/// all six NFL routes.
///
/// What is asserted is the composition only: which route shows which card
/// families in each phase, which phase headline the page mounts (or the
/// owner's unavailable words when that headline's owner declines), that the
/// production deck's cards are picked out by their own ids only at their own
/// phase and basis, the story stream's card-to-leaf wiring, the activation
/// hook before a paired card's action, the full-size history without its
/// expand control, the forecast control's one destination, the arrangement
/// candidates and a phone-width fit. Each leaf's own rules stay with its own
/// tests; nothing here claims a native runtime, VoiceOver behaviour, a stream
/// hold qualification or a production binding (the adapters' tests decode the
/// retained real bodies).
///
/// Raw values are taken from the retained Eagles at Jaguars bodies (event
/// 14639175, `soccer-next-preview-v306/raw/` under the event-page design
/// directory): `nfl-14639175-detail.json` (live, sha256 031d8150…78ae — Q3,
/// Eagles 14–7, hero 0.54412 / 0.45588 with 54 / 46 rendered, sportsbook
/// projection 20.9 / 20.2, opening 0.2381 / 0.7619) and
/// `nfl-latest-game-markets.json` (final, sha256 af0fe782…cd45 — "Philadelphia
/// vs Jacksonville: Team Field Goals", market 65113446: Jacksonville 1+ 78.5%
/// reached, 2+ 54.5% reached, 3+ 27.5% missed; Philadelphia 1+ 78% reached,
/// 2+ 51% missed, 3+ 27% missed, each a served `pregame_mark`).
///
/// CONSTRUCTED owner input (this layer resolves none of it): every display
/// word, colour, tick, scope, story link, copy and phase; the pregame Rams-style
/// headline pair; the projected-finish pregame halves; the milestone ladder; and
/// the combined-yards card (its figures follow the design's retained Swift
/// 84 + 4 = 88 case, prototype-derived, not a server body).
@MainActor
final class FootballEventPagePresentation10868Tests: XCTestCase {
    private typealias P = FootballEventPagePresentation10868
    private typealias M = FootballEventPageModel10868

    // MARK: Constructed owner input

    private static let teams = FootballEventPageTeams10868(
        away: "Philadelphia Eagles", home: "Jacksonville Jaguars", awayShort: "Eagles", homeShort: "Jaguars",
        awayColor: Color(red: 0, green: 0.30, blue: 0.33), homeColor: Color(red: 0, green: 0.40, blue: 0.47))

    private static let kickoff = "2026-10-11T13:30:00Z".asDate!

    private static func history(expand: Bool = true) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: "Win probability", caption: "Game history", series: [], selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1), ceiling: 1,
            yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: "Pregame"),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil, notes: ["Gaps remain blank."], summary: "No recorded history",
            plotHeight: 230, unboundReadingWords: "Not recorded", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: FieldHistoryAction10868(id: "history.details", label: "History & source details",
                                             spokenLabel: nil, isAvailable: false),
            expand: expand
                ? FieldHistoryAction10868(id: "history.expand", label: "Full chart",
                                          spokenLabel: "Expand football probability history", isAvailable: true)
                : nil,
            inspect: FieldHistoryAction10868(id: "history.inspect", label: "Inspect history",
                                             spokenLabel: nil, isAvailable: false),
            previous: nil, next: nil, inspection: nil,
            plotAbsence: FieldHistoryPlotAbsence10868(title: "No recorded history", words: nil))
    }

    private static func finish(_ phase: NFLFinishCard9483.Phase) -> NFLFinishCard9483 {
        let pregame = NFLFinishCard9483.Pair(away: 17.5, home: 25, at: kickoff.addingTimeInterval(-600))
        switch phase {
        case .before:
            return NFLFinishCard9483(phase: .before, pregame: pregame, projectedNow: nil, final: nil)
        case .during:
            return NFLFinishCard9483(
                phase: .during, pregame: pregame,
                projectedNow: NFLFinishCard9483.Pair(away: 20.9, home: 20.2, at: "2026-10-11T15:34:32Z".asDate),
                final: nil)
        case .after:
            return NFLFinishCard9483(
                phase: .after, pregame: pregame, projectedNow: nil,
                final: NFLFinishCard9483.Pair(away: 17, home: 19, at: "2026-10-11T17:15:37Z".asDate))
        }
    }

    private static func milestone(_ basis: NFLMilestoneCard9483.Basis, id: String = "Jalen Hurts|completions")
        -> NFLMilestoneCard9483 {
        let rungs = [(14.0, 0.82), (18.0, 0.55), (22.0, 0.21)].map { threshold, chance in
            NFLMilestoneCard9483.Rung(threshold: threshold, chance: chance, observedAt: nil,
                                      rowID: "Passing Completions-Jalen Hurts: \(Int(threshold))+", hit: nil)
        }
        return NFLMilestoneCard9483(id: id, player: "Jalen Hurts", stat: "Passing Completions", side: .away,
                                    basis: basis, rungs: rungs, actual: nil)
    }

    private static func deck(_ phase: FootballEventPagePhase10868) -> [NFLEventCard9483] {
        [.finish(finish(phase.finishPhase)), .milestone(milestone(phase.milestoneBasis))]
    }

    private static func fieldGoalGroup(_ target: String, eagles: Double, jaguars: Double,
                                       eaglesReached: Bool, jaguarsReached: Bool) -> PairedMilestoneGroup10868 {
        func original(_ team: String, _ chance: Double, _ reached: Bool) -> PairedMilestoneEntry10868 {
            .original(PairedMilestoneOriginal10868(
                id: "fg:\(team):\(target)", title: "\(team) \(target) field goals",
                before: PlayerContributionObservation10868(probability: chance, text: formatProbability(chance),
                                                           accessibilityDetail: "saved before the start · Kalshi"),
                beforeMissing: "Unavailable",
                current: .unavailable("No in-game reading"),
                result: reached ? .reached("Reached") : .missed("Missed")))
        }
        return PairedMilestoneGroup10868(
            id: "fg:\(target)", target: target, title: "\(target) field goals",
            first: original("Philadelphia", eagles, eaglesReached),
            second: original("Jacksonville", jaguars, jaguarsReached))
    }

    private static func paired(_ phase: PlayerContributionPhase10868,
                               orientation: PlayerContributionOrientation10868,
                               cardID: String) -> PairedMilestoneInput10868 {
        PairedMilestoneInput10868(
            phase: phase, orientation: orientation, cardID: cardID, eyebrow: "TEAM MILESTONES",
            title: orientation == .columns ? "Field goals" : "Pressure on the passer",
            definition: "Each team’s chance belongs to its own contract. The two do not add to 100%.",
            first: PairedMilestoneSubject10868(id: "subject:Philadelphia", name: "Philadelphia", detail: nil,
                                               countSoFar: nil, finalCount: nil, countMissing: "Count unavailable"),
            second: PairedMilestoneSubject10868(id: "subject:Jacksonville", name: "Jacksonville", detail: nil,
                                                countSoFar: nil, finalCount: nil, countMissing: "Count unavailable"),
            groups: [
                fieldGoalGroup("1+", eagles: 0.78, jaguars: 0.785, eaglesReached: true, jaguarsReached: true),
                fieldGoalGroup("2+", eagles: 0.51, jaguars: 0.545, eaglesReached: false, jaguarsReached: true),
                fieldGoalGroup("3+", eagles: 0.27, jaguars: 0.275, eaglesReached: false, jaguarsReached: false),
            ],
            selectedGroupID: "fg:2+", chartTitle: "Pregame chances · at least this many",
            ticks: [PlayerContributionTick10868(value: 0, text: "0%"),
                    PlayerContributionTick10868(value: 1, text: "100%")])
    }

    private static func combined(_ phase: FootballEventPagePhase10868) -> FootballCombinedStory10868 {
        let card = NFLMilestoneCard9483(
            id: "D'Andre Swift|combined", player: "D'Andre Swift", stat: "Rushing + Receiving Yards", side: .home,
            basis: phase.milestoneBasis,
            rungs: [(70.0, 0.645), (95.0, 0.38), (120.0, 0.185)].map {
                NFLMilestoneCard9483.Rung(threshold: $0.0, chance: $0.1, observedAt: nil,
                                          rowID: "combined-\(Int($0.0))", hit: nil)
            },
            actual: phase == .final ? 88 : nil)
        let split = AdditiveStatSplitInput10868(
            subject: "D'Andre Swift", totalName: "Combined", phase: phase.splitPhase,
            actual: phase == .final
                ? .final(AdditiveStatSplitReading10868(
                    total: .value(AdditiveStatSplitFigure10868(text: "88", unit: "yards", provenance: nil)),
                    split: .unavailable("Ground and air split unavailable")))
                : .absent("Actual so far unavailable"),
            axis: AdditiveStatSplitAxis10868(lower: 0, upper: 100, ticks: [], unit: "yards"),
            detailsID: nil)
        return FootballCombinedStory10868(card: card, split: split)
    }

    private static func headline(_ phase: FootballEventPagePhase10868, decided: Bool = true) -> FootballEventPageHeadline10868 {
        let opened = PrematchReading(awayProbability: 0.2381, homeProbability: 0.7619, percents: [24, 76],
                                     source: PrematchReading.booksSource, isServed: false, awayIsComplement: false)
        let arm: FootballHeadlineArm10868
        switch phase {
        case .before:
            arm = .before(FootballPregameHeadline10868(
                status: "scheduled", hasStarted: false, isOpeningLine: false,
                paired: NFLPairedHeadline9483.priced(awayText: "38%", homeText: "62%", live: false,
                                                     score: nil, pregame: nil),
                chancePhase: .current, projected: FootballPointsPair10868(away: 25, home: 29),
                forecastLabel: "Projected final", pregameContext: "ESPN, ABC · Oct 12, 5:15 PM"))
        case .live:
            arm = .live(FootballLiveHeadline10868(
                status: "live",
                paired: NFLPairedHeadline9483.priced(awayText: "54%", homeText: "46%", live: true,
                                                     score: (away: 14, home: 7), pregame: opened),
                chancePhase: .current, baseline: opened, score: .score(away: 14, home: 7, final: false),
                forecast: nil, gameState: "Q3 13:31"))
        case .final:
            arm = .final(FootballFinalHeadline10868(
                status: "completed",
                paired: NFLPairedHeadline9483.final(homeWon: decided ? true : nil, score: (away: 17, home: 19),
                                                    pregame: opened),
                baseline: opened, score: .score(away: 17, home: 19, final: true), forecast: nil,
                finalContext: "Final · Sun, Oct 11"))
        }
        return FootballEventPageHeadline10868(sportKey: "americanfootball_nfl", arm: arm)
    }

    private static func scope(_ phase: FootballEventPagePhase10868) -> String { "nfl:14639175:\(phase)" }

    private static let allStories: [FootballEventPageStory10868] = [
        FootballEventPageStory10868(cardID: "finish", card: .finish),
        FootballEventPageStory10868(cardID: "milestone", card: .milestone("Jalen Hurts|completions")),
        FootballEventPageStory10868(cardID: "sacks", card: .teamSacks),
        FootballEventPageStory10868(cardID: "fieldGoals", card: .teamFieldGoals),
        FootballEventPageStory10868(cardID: "combined", card: .combined("D'Andre Swift|combined")),
    ]

    private static func stream(_ phase: FootballEventPagePhase10868, primary: String = "fieldGoals",
                               companion: String? = nil) -> StoryStreamPresentation10868 {
        let scope = scope(phase)
        let ids = allStories.map(\.cardID)
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Expectations and performance",
            cards: ids.map { StoryStreamPresentation10868.Card(id: $0, name: "Story \($0)") },
            primary: .init(scope: scope, id: primary),
            companion: companion.map { .init(scope: scope, id: $0) },
            companionLabel: companion == nil ? nil : "Next",
            wide: companion != nil,
            position: "1 of \(ids.count)", status: "Use Previous or Next to see each story",
            dwellFraction: nil, playback: nil,
            previous: nil, next: .init(scope: scope, id: "combined"),
            readerOpen: false)
    }

    private static func page(_ route: FootballRoute10868, _ phase: FootballEventPagePhase10868,
                             headline: FootballEventPageHeadline10868? = nil,
                             deck: [NFLEventCard9483]? = nil,
                             stories: [FootballEventPageStory10868] = allStories,
                             companion: String? = nil) -> FootballEventPageInput10868 {
        let score: FootballEventPageScore10868? = switch phase {
        case .before: nil
        case .live: .actual(away: "14", home: "7", spoken: "Eagles 14, Jaguars 7")
        case .final: .actual(away: "17", home: "19", spoken: "Final: Eagles 17, Jaguars 19")
        }
        let state: String = switch phase {
        case .before: "Before game · 6:30 AM start"
        case .live: "Q3 13:31"
        case .final: "Final"
        }
        return FootballEventPageInput10868(
            route: route, phase: phase, teams: teams,
            header: FootballEventPageHeader10868(state: state, score: score, aboutLabel: "About this game"),
            headline: headline ?? Self.headline(phase),
            history: history(),
            deck: deck ?? Self.deck(phase),
            teamSacks: paired(phase.contributionPhase, orientation: .bars, cardID: "sacks"),
            teamFieldGoals: paired(phase.contributionPhase, orientation: .columns, cardID: "fieldGoals"),
            combined: [combined(phase)],
            stream: stream(phase, companion: companion),
            stories: stories,
            copy: FootballEventPageCopy10868(
                storiesLabel: "Game stories",
                storyUnavailable: "This story isn’t available for this game state. Every original is still in All props.",
                headlineUnavailable: "Win chance unavailable",
                allPropsLabel: "All 715 original outcomes"))
    }

    // MARK: Route card sets

    func testEveryRouteShowsExactlyItsTrackerCardGroupsInEveryPhase() {
        let all: [FootballCardFamily10868] = [.totalAndMargin, .playerMilestones, .teamMilestones, .combinedYards]
        let expected: [FootballRoute10868: [FootballCardFamily10868]] = [
            .nfl: all, .stories: all, .replay: all,
            .live: [.totalAndMargin, .playerMilestones],
            .teamStats: [.teamMilestones],
            .combined: [.combinedYards],
        ]
        for route in FootballRoute10868.allCases {
            for phase in [FootballEventPagePhase10868.before, .live, .final] {
                // Design 2026-10-31: the completed nfl-live page restores the
                // approved period-winner story, directly before the players.
                let wanted: [FootballCardFamily10868]? = route == .live && phase == .final
                    ? [.totalAndMargin, .periodWinners, .playerMilestones] : expected[route]
                XCTAssertEqual(FootballRouteCardSet10868.families(route, phase: phase), wanted,
                               "\(route.rawValue) \(phase)")
            }
            XCTAssertEqual(FootballRouteCardSet10868.route(id: route.rawValue), route)
        }
        XCTAssertNil(FootballRouteCardSet10868.route(id: "nfl-pregame"),
                     "nfl-pregame is an unadmitted branch, not a route this screen serves")
    }

    // MARK: Headline

    func testEachPhaseMountsItsOwnHeadlineAndAnArmOfAnotherPhaseShowsTheOwnersUnavailableWords() {
        for phase in [FootballEventPagePhase10868.before, .live, .final] {
            XCTAssertTrue(M(Self.page(.nfl, phase)).headlineResolves, "\(phase)")
        }
        // A live arm handed to a final page is not coerced to appear.
        let mismatched = M(Self.page(.nfl, .final, headline: Self.headline(.live)))
        XCTAssertFalse(mismatched.headlineResolves)
        XCTAssertEqual(mismatched.input.copy.headlineUnavailable, "Win chance unavailable")
    }

    func testAnUnresolvedFinalKeepsTheUnavailableWordsInsteadOfARebuiltChance() {
        // `NFLPairedHeadline9483.final` declines a final with no verdict, so the
        // final headline's owner draws nothing: the page says so and keeps the score.
        let unresolved = M(Self.page(.nfl, .final, headline: Self.headline(.final, decided: false)))
        XCTAssertFalse(unresolved.headlineResolves)
        XCTAssertEqual(unresolved.score, .actual(away: "17", home: "19", spoken: "Final: Eagles 17, Jaguars 19"))
    }

    func testAPregamePageHasNoScoreEvenWhenOneIsSupplied() {
        let base = Self.page(.nfl, .before)
        // CONSTRUCTED: only the header's score and about label differ from `base`.
        let input = FootballEventPageInput10868(
            route: base.route, phase: base.phase, teams: base.teams,
            header: FootballEventPageHeader10868(state: base.header.state,
                                                 score: .actual(away: "0", home: "0", spoken: "Eagles 0, Jaguars 0"),
                                                 aboutLabel: nil),
            headline: base.headline, history: base.history, deck: base.deck, teamSacks: base.teamSacks,
            teamFieldGoals: base.teamFieldGoals, combined: base.combined, stream: base.stream,
            stories: base.stories, copy: base.copy)
        XCTAssertNil(M(input).score)
        XCTAssertFalse(M(input).aboutAvailable(canOpen: true), "no about label, no about entry")
    }

    // MARK: Deck

    func testTheProductionDeckIsPickedOutByIdOnlyAtItsOwnPhaseAndBasis() throws {
        let final = M(Self.page(.nfl, .final))
        XCTAssertEqual(final.finish?.phase, .after)
        XCTAssertTrue(NFLFinalComparisonPresentation9483.applies(try XCTUnwrap(final.finish)),
                      "a finished card with its final draws the accepted final renderer")
        XCTAssertEqual(final.milestones.map(\.id), ["Jalen Hurts|completions"])
        XCTAssertNotNil(final.milestone("Jalen Hurts|completions"))
        XCTAssertNil(final.milestone("Somebody Else|completions"))

        // A live page handed a pregame-phase finish card and a pregame-price
        // milestone card mounts neither.
        let stale = M(Self.page(.nfl, .live, deck: Self.deck(.before)))
        XCTAssertNil(stale.finish)
        XCTAssertTrue(stale.milestones.isEmpty)
        XCTAssertFalse(stale.isMounted(.finish))
        XCTAssertFalse(stale.isMounted(.milestone("Jalen Hurts|completions")))

        // Two cards sharing one id name no single card.
        let doubled = M(Self.page(.nfl, .live, deck: Self.deck(.live) + [.milestone(Self.milestone(.pregameMark))]))
        XCTAssertNil(doubled.milestone("Jalen Hurts|completions"))
    }

    func testARouteMountsOnlyItsOwnFamilies() {
        let live = M(Self.page(.live, .live))
        XCTAssertTrue(live.isMounted(.finish))
        XCTAssertTrue(live.isMounted(.milestone("Jalen Hurts|completions")))
        XCTAssertFalse(live.isMounted(.teamSacks), "nfl-live shows player props and total/margin only")
        XCTAssertFalse(live.isMounted(.combined("D'Andre Swift|combined")))

        let teamStats = M(Self.page(.teamStats, .final))
        XCTAssertTrue(teamStats.isMounted(.teamSacks))
        XCTAssertTrue(teamStats.isMounted(.teamFieldGoals))
        XCTAssertFalse(teamStats.isMounted(.finish))
        XCTAssertFalse(teamStats.isMounted(.milestone("Jalen Hurts|completions")))

        let combined = M(Self.page(.combined, .final))
        XCTAssertTrue(combined.isMounted(.combined("D'Andre Swift|combined")))
        XCTAssertFalse(combined.isMounted(.teamFieldGoals))
        XCTAssertFalse(combined.isMounted(.finish))

        for route in [FootballRoute10868.nfl, .stories, .replay] {
            let model = M(Self.page(route, .final))
            for story in Self.allStories { XCTAssertTrue(model.isMounted(story.card), "\(route.rawValue) \(story.card)") }
        }
    }

    func testAPairedOrSplitLeafOfAnotherPhaseIsNotMounted() {
        let base = Self.page(.nfl, .live)
        let input = FootballEventPageInput10868(
            route: base.route, phase: base.phase, teams: base.teams, header: base.header, headline: base.headline,
            history: base.history, deck: base.deck,
            teamSacks: Self.paired(.final, orientation: .bars, cardID: "sacks"),
            teamFieldGoals: Self.paired(.during, orientation: .columns, cardID: "fieldGoals"),
            combined: [Self.combined(.final)], stream: base.stream, stories: base.stories, copy: base.copy)
        let model = M(input)
        XCTAssertNil(model.teamSacks)
        XCTAssertNotNil(model.teamFieldGoals)
        XCTAssertNil(model.combined("D'Andre Swift|combined"))
    }

    // MARK: Stream

    func testStoryCardsResolveOnlyExactSingleLinksToMountedCards() {
        let links = Self.allStories + [
            FootballEventPageStory10868(cardID: "twice", card: .teamSacks),
            FootballEventPageStory10868(cardID: "twice", card: .teamFieldGoals),
            FootballEventPageStory10868(cardID: "anchor", card: .history),
        ]
        let model = M(Self.page(.nfl, .final, stories: links))
        XCTAssertEqual(model.storyCard("fieldGoals"), .teamFieldGoals)
        XCTAssertEqual(model.storyCard("finish"), .finish)
        XCTAssertNil(model.storyCard("twice"), "an id two links share names no single card")
        XCTAssertNil(model.storyCard("anchor"), "the history is the anchor, never a story")
        XCTAssertNil(model.storyCard("nobody"))

        let live = M(Self.page(.live, .live, stories: links))
        XCTAssertNil(live.storyCard("fieldGoals"), "a family the route does not show is never a neighbour's slot")
        XCTAssertTrue(live.readerShows(.history))
        XCTAssertFalse(live.readerShows(.teamFieldGoals))
    }

    func testAPairedCardActionAsksTheStreamFirstThenTheExactHostCallbackAndBuildingActsOnNothing() {
        var log: [String] = []
        let input = Self.page(.nfl, .final, companion: "sacks")
        let view = P(
            input: input, cardState: NFLCardDeckState9483(),
            onAbout: { log.append("about") },
            onAllProps: { log.append("allProps") },
            onStoryIntent: { _ in log.append("stream") },
            onHistoryAction: { log.append("history:\($0)") },
            onForecastInspection: { log.append("forecast:\($0)") },
            onTeamMilestoneSelect: { card, id in log.append("select:\(card.key):\(id)") },
            onTeamMilestoneDetails: { card, id in log.append("details:\(card.key):\(id)") },
            onTeamMilestoneExpand: { card, id in log.append("expand:\(card.key):\(id)") })

        let stream = input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        func activation(_ id: String) -> StoryStreamCardActivation10868 {
            let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
            return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
                if case .interaction(_, let card) = intent { log.append("hold:\(card?.id ?? "-")") } else { log.append("other") }
            }
        }
        XCTAssertTrue(activation("fieldGoals").isAvailable)
        XCTAssertTrue(activation("sacks").isAvailable)

        // Building every leaf, in stream and reader form, acts on nothing.
        let fieldGoals = view.pairedContent(.teamFieldGoals, activation: activation("fieldGoals"))!
        let sacks = view.pairedContent(.teamSacks, activation: activation("sacks"))!
        let readerFieldGoals = view.pairedContent(.teamFieldGoals, activation: nil)!
        _ = view.headlineContent()
        _ = view.historyContent(reader: false)
        _ = view.finishContent(expanded: true)
        _ = view.milestoneContent("Jalen Hurts|completions", reader: true)
        _ = view.combinedContent("D'Andre Swift|combined", reader: false, activation: activation("combined"))
        XCTAssertEqual(log, [])

        fieldGoals.onSelect?("fg:3+")
        sacks.onDetails?("fg:Philadelphia:2+")
        fieldGoals.onExpand?("fieldGoals")
        XCTAssertEqual(log, [
            "hold:fieldGoals", "select:teamFieldGoals:fg:3+",
            "hold:sacks", "details:teamSacks:fg:Philadelphia:2+",
            "hold:fieldGoals", "expand:teamFieldGoals:fieldGoals",
        ])

        // Full size: the host's exact callback, no hold, and no expand of its own.
        log.removeAll()
        readerFieldGoals.onSelect?("fg:1+")
        XCTAssertNil(readerFieldGoals.onExpand)
        XCTAssertEqual(log, ["select:teamFieldGoals:fg:1+"])
    }

    func testWithoutCallbacksNothingPretendsToAct() {
        let view = P(input: Self.page(.nfl, .final), cardState: NFLCardDeckState9483())
        let paired = view.pairedContent(.teamFieldGoals, activation: nil)!
        XCTAssertNil(paired.onSelect)
        XCTAssertNil(paired.onDetails)
        XCTAssertNil(paired.onExpand)
        let model = M(Self.page(.nfl, .final))
        XCTAssertFalse(model.aboutAvailable(canOpen: false))
        XCTAssertFalse(model.allPropsAvailable(canOpen: false))
        XCTAssertTrue(model.allPropsAvailable(canOpen: true))
        XCTAssertNil(view.catalogueContent(), "no originals group, no catalogue content")
        XCTAssertNil(view.originalDetailsContent())
    }

    // MARK: Reader and controls

    func testTheFullSizeHistoryDropsOnlyItsExpandControl() {
        let model = M(Self.page(.nfl, .live))
        let reader = model.readerHistory
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertEqual(reader.inspect, model.input.history.inspect)
        XCTAssertEqual(reader.details, model.input.history.details)
        XCTAssertEqual(reader.notes, model.input.history.notes)
        XCTAssertEqual(reader.plotAbsence, model.input.history.plotAbsence)
        XCTAssertEqual(reader.summary, model.input.history.summary)
    }

    func testAHeadlineForecastControlOnlyRoutesToAMountedFinishCard() {
        XCTAssertTrue(M(Self.page(.nfl, .final)).forecastInspectionAvailable(canOpen: true))
        XCTAssertFalse(M(Self.page(.nfl, .final)).forecastInspectionAvailable(canOpen: false))
        // nfl-team-stats shows no total/margin card, so the control has nowhere to go.
        XCTAssertFalse(M(Self.page(.teamStats, .final)).forecastInspectionAvailable(canOpen: true))
        XCTAssertFalse(M(Self.page(.nfl, .live, deck: [])).forecastInspectionAvailable(canOpen: true))
    }

    func testCompactAndAccessibilitySizesStackAndAWideOrUnspecifiedWidthTriesSideBySideFirst() {
        XCTAssertEqual(M.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(M.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(M.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(M.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
    }

    func testThePageFitsAPhoneWidthAtStandardAndAccessibilityText() {
        for phase in [FootballEventPagePhase10868.before, .live, .final] {
            for size in [DynamicTypeSize.large, .accessibility3] {
                let view = P(input: Self.page(.nfl, phase), cardState: NFLCardDeckState9483())
                    .frame(width: 375)
                    .environment(\.horizontalSizeClass, .compact)
                let host = hostForMeasurement(view, at: size)
                let fitted = host.sizeThatFits(in: CGSize(width: 375, height: CGFloat.greatestFiniteMagnitude))
                XCTAssertLessThanOrEqual(fitted.width, 375, "\(phase) \(size): no sideways page growth")
                XCTAssertGreaterThan(fitted.height, 0)
            }
        }
    }
}
