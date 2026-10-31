import SwiftUI

// #10868 — the football event screen: one native presentation composed from
// the accepted leaves, serving all six NFL routes (`nfl`, `nfl-live`,
// `nfl-stories`, `nfl-team-stats`, `nfl-combined`, `nfl-replay`) by the
// route's card set (`FootballRouteCardSet10868`). Win chances lead. A fan sees,
// in this order: the phase's probability comparison — before the game each
// team's win chance and projected final, during play the eight-value
// comparison, after the final each team's earlier expectation against its
// actual finish; the two-team win-probability history front and centre; the
// route's stories in the owner's story stream; then the "All props" entry.
// The history and every story open as full-size content made of the same
// Views, and "All props" and the selected original's Details are two more
// content modes.
//
// Presentation only, composed from the approved references as mounted in
// `Atlas.tsx` and `route-tracker/current-routes.json` (`Prototype.tsx`,
// `UnifiedNFLPage.tsx`, `TeamMilestonesPage.tsx`, `CombinedYardsPage.tsx`,
// `PairedReplay.tsx`). The reference's fixture loaders, phase toggle, replay
// transport, range controls, session state, ranking, sheets, catalogue search
// and focus restoration are NOT ported. The leaves are the actual accepted
// Views:
//
//   • `PregameComparisonHeadline9483`, `LiveEightValueHeadline9483`,
//     `FinalComparisonHeadline9483` — the probability anchor, one per phase;
//   • `FieldProbabilityHistoryPresentation10868` — the history;
//   • `NFLFinishCardView9483` / `NFLFinalComparisonPresentation9483` — total
//     and margin: the production projected finish, and after the final the
//     final against that forecast (the accepted mount: the final renderer
//     when it `applies`, the existing card otherwise);
//   • `NFLMilestoneCardView9483` — the production player milestone cards;
//   • `PairedMilestonePresentation10868` — team sacks (bars) and team field
//     goals (columns);
//   • `NFLMilestoneCardView9483` + `AdditiveStatSplitPresentation10868` —
//     combined yards: the combined contract's chances beside the signed split;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the selected original's Details.
//
// Nothing here decides a value. The headline inputs are the exact parameters
// each 9483 headline takes, resolved by their owners; a headline whose owner
// declines (a level or unresolved final, an opening line, a venue-settled
// verdict, a suspended game, a missing pair) draws the owner's unavailable
// words and the state line instead — never a rebuilt chance. The production
// deck (`NFLEventCardDeck9483.cards`) arrives unchanged; this layer only picks
// each card out by its own id. A card whose own phase is not the page's — a
// finish card of another phase, a milestone card on the other basis, a paired
// or split leaf of another phase — is not mounted, and neither is a card of a
// family the route does not show.
//
// The story stream is the owner's: cards, order, primary, companion, position,
// status, playback, previous/next, scope and reader-open flag. This layer wires
// each supplied card id to the one card the owner names for it, and shows the
// owner's unavailable words for an id that names no single card this route and
// phase mount — never a neighbour. A paired card's own select, Details and
// expand actions first call the stream's activation hook and then the host's
// exact callback. The production milestone card's previous/next and Details
// write the host's own `NFLCardDeckState9483` directly (that card offers no
// callback), so they do not pass through the activation hook — a recorded
// gap, not a pretend relay. Full-size content reuses the same leaves with the
// host's exact callbacks and no activation.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control. It sits under the same comparison.
//
// Phone stacks the comparison and history above the stories; a regular or
// unspecified size class places them side by side while both columns keep
// their minimum widths, otherwise it stacks too, and accessibility sizes
// always stack.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing to
// and from the catalogue and an original's Details, the milestone selection
// (`NFLCardDeckState9483`, which the existing deck and reader already share),
// the held/received frame and every selection. This view keeps no state, runs
// no timer or animation, holds no subscription and presents no sheet or
// navigation of its own. With no callback, nothing pretends to act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one game snapshot, every input below, holds the reading while updates
// arrive, ranks and advances the stream, and maps every callback to its
// existing controls. `nfl-replay`'s as-of rebuild and transport are not here.

/// The owner's explicit phase for the whole screen. Never read from a score,
/// a clock or a result.
nonisolated enum FootballEventPagePhase10868: Equatable, Sendable {
    case before
    case live
    case final

    /// The production finish card's own name for the same phase.
    var finishPhase: NFLFinishCard9483.Phase {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .after
        }
    }

    /// The paired leaf's own name for the same phase.
    var contributionPhase: PlayerContributionPhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }

    /// The split leaf's own name for the same phase.
    var splitPhase: AdditiveStatSplitPhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }

    /// The production milestone card's basis for the same phase: the current
    /// price before the game, the served pregame mark once it has started.
    var milestoneBasis: NFLMilestoneCard9483.Basis {
        self == .before ? .pregamePrice : .pregameMark
    }
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum FootballEventPageCard10868: Hashable, Sendable {
    case history
    /// Total and margin: the production projected finish.
    case finish
    /// A production player milestone card, by its own `NFLMilestoneCard9483.id`.
    case milestone(String)
    case teamSacks
    case teamFieldGoals
    /// Combined yards, by its milestone card's own `NFLMilestoneCard9483.id`.
    case combined(String)
    /// The final period winners (completed `nfl-live` only).
    case periodWinners

    /// The route family the card belongs to; the anchor belongs to none.
    var family: FootballCardFamily10868? {
        switch self {
        case .history: nil
        case .finish: .totalAndMargin
        case .milestone: .playerMilestones
        case .teamSacks, .teamFieldGoals: .teamMilestones
        case .combined: .combinedYards
        case .periodWinners: .periodWinners
        }
    }

    /// A stable key for identifiers.
    var key: String {
        switch self {
        case .history: "history"
        case .finish: "finish"
        case .milestone(let id): "milestone:\(id)"
        case .teamSacks: "teamSacks"
        case .teamFieldGoals: "teamFieldGoals"
        case .combined(let id): "combined:\(id)"
        case .periodWinners: "periodWinners"
        }
    }
}

/// What the host's container is showing, chosen by the host.
nonisolated enum FootballEventPageMode10868: Equatable, Sendable {
    /// The game screen body.
    case page
    /// One card's full-size content.
    case reader(FootballEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
}

nonisolated enum FootballEventPageArrangement10868: Equatable, Sendable {
    case stacked
    case sideBySide
}

/// Both teams as the leaves name and colour them.
nonisolated struct FootballEventPageTeams10868: Equatable {
    /// Full names, as the 9483 headlines print them ("Philadelphia Eagles").
    let away: String
    let home: String
    /// The short names the production cards print (`TeamShortName.shortPair`).
    let awayShort: String
    let homeShort: String
    /// `TeamTextContrast.cardColors`.
    let awayColor: Color
    let homeColor: Color
}

/// The host's printed projected-final integers (`projectedPair11285`).
nonisolated struct FootballPointsPair10868: Equatable, Sendable {
    let away: Int
    let home: Int
}

/// `PregameComparisonHeadline9483`'s inputs, exactly.
struct FootballPregameHeadline10868: Equatable {
    let status: String?
    let hasStarted: Bool
    let isOpeningLine: Bool
    let paired: NFLPairedHeadline9483?
    let chancePhase: EventHeadlinePhase9483?
    let projected: FootballPointsPair10868?
    /// "Projected final".
    let forecastLabel: String
    let pregameContext: String?
}

/// `LiveEightValueHeadline9483`'s inputs, exactly.
struct FootballLiveHeadline10868: Equatable {
    let status: String?
    let paired: NFLPairedHeadline9483?
    let chancePhase: EventHeadlinePhase9483?
    let baseline: PrematchReading?
    let score: NFLPairedHeadline9483.Center?
    let forecast: LivePregameComparison11296.Headline?
    /// The owner's game-state words ("13:31 · 3rd").
    let gameState: String
}

/// `FinalComparisonHeadline9483`'s inputs, exactly.
struct FootballFinalHeadline10868: Equatable {
    let status: String?
    let paired: NFLPairedHeadline9483?
    let baseline: PrematchReading?
    let score: NFLPairedHeadline9483.Center?
    let forecast: FinalForecastComparison11296.Qualified?
    /// The owner's final and date words ("Final · Sun, Oct 11").
    let finalContext: String
}

/// The phase's probability comparison: one 9483 headline's inputs.
enum FootballHeadlineArm10868: Equatable {
    case before(FootballPregameHeadline10868)
    case live(FootballLiveHeadline10868)
    case final(FootballFinalHeadline10868)

    var phase: FootballEventPagePhase10868 {
        switch self {
        case .before: .before
        case .live: .live
        case .final: .final
        }
    }
}

struct FootballEventPageHeadline10868: Equatable {
    let sportKey: String?
    let arm: FootballHeadlineArm10868
}

/// The owner's actual score, read only once play has started.
nonisolated enum FootballEventPageScore10868: Equatable, Sendable {
    /// The owner's figures ("17", "19") and spoken words ("Eagles 17, Jaguars 19").
    case actual(away: String, home: String, spoken: String)
    /// The owner's words for a missing score ("Score unavailable").
    case unavailable(String)
}

/// The owner's words around the comparison.
nonisolated struct FootballEventPageHeader10868: Equatable, Sendable {
    /// "Before game · 5:15 PM start", "13:31 · 3rd", "Suspended", "Final". Shown
    /// in full-size content, and on the page where the headline's owner declines.
    let state: String
    /// Read during play and after the final only.
    let score: FootballEventPageScore10868?
    /// Spoken name of the about entry; nil draws none.
    let aboutLabel: String?
}

/// Combined yards for one player: the combined contract's own milestone card
/// and the signed split beside it.
struct FootballCombinedStory10868: Equatable {
    let card: NFLMilestoneCard9483
    let split: AdditiveStatSplitInput10868
}

/// The owner's link from one stream card id to the card it shows.
nonisolated struct FootballEventPageStory10868: Equatable, Sendable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: FootballEventPageCard10868
}

nonisolated struct FootballEventPageCopy10868: Equatable, Sendable {
    /// Spoken name of the stories group ("Game stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single card this route and phase show.
    let storyUnavailable: String
    /// Shown in place of a comparison its owner declines ("Win chance unavailable").
    let headlineUnavailable: String
    /// "All 715 original outcomes"; nil draws no entry.
    let allPropsLabel: String?
}

struct FootballEventPageInput10868: Equatable {
    let route: FootballRoute10868
    let phase: FootballEventPagePhase10868
    let teams: FootballEventPageTeams10868
    let header: FootballEventPageHeader10868
    let headline: FootballEventPageHeadline10868
    let history: FieldHistoryInput10868
    /// The production deck, unchanged (`NFLEventCardDeck9483.cards`).
    let deck: [NFLEventCard9483]
    let teamSacks: PairedMilestoneInput10868?
    let teamFieldGoals: PairedMilestoneInput10868?
    let combined: [FootballCombinedStory10868]
    let stream: StoryStreamPresentation10868
    let stories: [FootballEventPageStory10868]
    let copy: FootballEventPageCopy10868
    /// The final period-winner card, or nil (no owner binding, or not final).
    var periodWinners: FootballPeriodWinnersInput10868? = nil
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct FootballEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The selected original's recorded history; nil keeps its Details summary.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's card label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All props".
    let heading: String
    /// "715 originals"; nil draws none.
    var context: String? = nil
    /// "No original props recorded for this game".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum FootballEventPageAccessibilityID10868 {
    static let page = "footballEventPage10868.page"
    static let header = "footballEventPage10868.header"
    static let headlineUnavailable = "footballEventPage10868.headline.unavailable"
    static let score = "footballEventPage10868.score"
    static let about = "footballEventPage10868.about"
    static let anchor = "footballEventPage10868.anchor"
    static let stories = "footballEventPage10868.stories"
    static let allProps = "footballEventPage10868.allProps"
    static let unavailable = "footballEventPage10868.story.unavailable"
    static let catalogue = "footballEventPage10868.catalogue"
    static let original = "footballEventPage10868.original"
    static func card(_ card: FootballEventPageCard10868) -> String { "footballEventPage10868.card.\(card.key)" }
}

/// Which leaves the page mounts, resolved once per input.
struct FootballEventPageModel10868: Equatable {
    let input: FootballEventPageInput10868

    init(_ input: FootballEventPageInput10868) {
        self.input = input
    }

    // MARK: Route

    var families: [FootballCardFamily10868] {
        FootballRouteCardSet10868.families(input.route, phase: input.phase)
    }

    func routeShows(_ family: FootballCardFamily10868) -> Bool {
        families.contains(family)
    }

    // MARK: Header

    /// Nil before the game — a pregame page has no actual score.
    var score: FootballEventPageScore10868? {
        input.phase == .before ? nil : input.header.score
    }

    // MARK: Headline — the phase's own owner, or its unavailable words

    /// Whether the phase's headline owner draws anything for these inputs. An
    /// arm of another phase never draws.
    var headlineResolves: Bool {
        let teams = input.teams
        let sport = input.headline.sportKey
        guard input.headline.arm.phase == input.phase else { return false }
        switch input.headline.arm {
        case .before(let h):
            return PregameComparisonHeadline9483<EmptyView>.resolve(
                sportKey: sport, status: h.status, hasStarted: h.hasStarted, isOpeningLine: h.isOpeningLine,
                paired: h.paired, chancePhase: h.chancePhase,
                projectedPair: h.projected.map { (away: $0.away, home: $0.home) },
                forecastLabel: h.forecastLabel, awayName: teams.away, homeName: teams.home,
                pregameContext: h.pregameContext, canInspect: false) != nil
        case .live(let h):
            return LiveEightValueHeadline9483<EmptyView>.resolve(
                sportKey: sport, status: h.status, paired: h.paired, chancePhase: h.chancePhase,
                baseline: h.baseline, score: h.score, forecast: h.forecast,
                awayName: teams.away, homeName: teams.home, gameState: h.gameState,
                canCompare: false, earlierAway: false, earlierHome: false) != nil
        case .final(let h):
            return FinalComparisonHeadline9483<EmptyView>.resolve(
                sportKey: sport, status: h.status, paired: h.paired, baseline: h.baseline,
                score: h.score, forecast: h.forecast, awayName: teams.away, homeName: teams.home,
                finalContext: h.finalContext, canInspect: false) != nil
        }
    }

    // MARK: Leaves — each only at its own phase and on its own route

    /// The production deck's projected finish, at the page's phase.
    var finish: NFLFinishCard9483? {
        guard routeShows(.totalAndMargin) else { return nil }
        for card in input.deck {
            if case .finish(let finish) = card, finish.phase == input.phase.finishPhase { return finish }
        }
        return nil
    }

    /// The production deck's milestone cards, in its order, on the page's basis.
    var milestones: [NFLMilestoneCard9483] {
        guard routeShows(.playerMilestones) else { return [] }
        return input.deck.compactMap { card -> NFLMilestoneCard9483? in
            guard case .milestone(let milestone) = card, milestone.basis == input.phase.milestoneBasis else { return nil }
            return milestone
        }
    }

    /// The milestone card with exactly this id, or nil (also for a duplicated id).
    func milestone(_ id: String) -> NFLMilestoneCard9483? {
        let matches = milestones.filter { $0.id == id }
        return matches.count == 1 ? matches.first : nil
    }

    var teamSacks: PairedMilestoneInput10868? {
        guard routeShows(.teamMilestones), let paired = input.teamSacks,
              paired.phase == input.phase.contributionPhase else { return nil }
        return paired
    }

    var teamFieldGoals: PairedMilestoneInput10868? {
        guard routeShows(.teamMilestones), let paired = input.teamFieldGoals,
              paired.phase == input.phase.contributionPhase else { return nil }
        return paired
    }

    /// The combined story with exactly this id, at the page's phase and basis.
    func combined(_ id: String) -> FootballCombinedStory10868? {
        guard routeShows(.combinedYards) else { return nil }
        let matches = input.combined.filter {
            $0.card.id == id && $0.card.basis == input.phase.milestoneBasis
                && $0.split.phase == input.phase.splitPhase
        }
        return matches.count == 1 ? matches.first : nil
    }

    /// The period-winner card: the route's own family, after the final only,
    /// with at least one admitted original.
    var periodWinners: FootballPeriodWinnersInput10868? {
        guard routeShows(.periodWinners), input.phase == .final, let card = input.periodWinners,
              card.hasOriginals else { return nil }
        return card
    }

    func isMounted(_ card: FootballEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .finish: finish != nil
        case .milestone(let id): milestone(id) != nil
        case .teamSacks: teamSacks != nil
        case .teamFieldGoals: teamFieldGoals != nil
        case .combined(let id): combined(id) != nil
        case .periodWinners: periodWinners != nil
        }
    }

    /// The card a stream card id names: exactly one owner link with that id,
    /// to a story this route and phase mount. Otherwise nothing.
    func storyCard(_ cardID: String) -> FootballEventPageCard10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let card = links.first?.card, card != .history, isMounted(card) else { return nil }
        return card
    }

    /// Full-size content exists for the anchor and for a story this page shows.
    func readerShows(_ card: FootballEventPageCard10868) -> Bool { isMounted(card) }

    /// The anchor's full-size content: the same history in its expanded
    /// layout, without an expand control inside the reader. Every other field
    /// is the owner's, unchanged.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: history.plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: nil, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: .expanded,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    // MARK: Page controls

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.header.aboutLabel) != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    /// A headline forecast control opens the finish card only where it is mounted.
    func forecastInspectionAvailable(canOpen: Bool) -> Bool {
        canOpen && isMounted(.finish)
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width tries side by side, then
    /// stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?,
                             accessibilitySize: Bool) -> [FootballEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

struct FootballEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: FootballEventPageInput10868
    /// The host's milestone selection, the one the existing deck and reader
    /// share (`EventDetailView.nflCards`).
    let cardState: NFLCardDeckState9483
    var mode: FootballEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: FootballEventPageOriginals10868? = nil
    /// The host presents `NFLRowDetails9483` for `cardState.detailsRowID`. Only
    /// then does full-size milestone content offer the card's Details.
    var showsMilestoneDetails: Bool = false
    var onAbout: (() -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// A headline forecast control, by `isHome`; offered only while the finish
    /// card is mounted, which is where the host routes it.
    var onForecastInspection: ((Bool) -> Void)? = nil
    /// A paired card's exact group, original or card id, with the card it came from.
    var onTeamMilestoneSelect: ((FootballEventPageCard10868, String) -> Void)? = nil
    var onTeamMilestoneDetails: ((FootballEventPageCard10868, String) -> Void)? = nil
    var onTeamMilestoneExpand: ((FootballEventPageCard10868, String) -> Void)? = nil
    var onSplitDetails: ((String) -> Void)? = nil
    /// The period-winner card's exact original to hold, its Details, and its
    /// full card (offered from the stream only).
    var onPeriodSelect: ((String) -> Void)? = nil
    var onPeriodDetails: ((String) -> Void)? = nil
    var onPeriodExpand: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: FootballEventPageModel10868 { FootballEventPageModel10868(input) }
    private var teams: FootballEventPageTeams10868 { input.teams }

    /// A card's own action, after the stream's activation hook when the card
    /// sits in the stream. No host callback: no action at all.
    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { value in
            activation.request()
            action(value)
        }
    }

    /// The host's two-argument paired callback, bound to one card.
    static func bound(_ action: ((FootballEventPageCard10868, String) -> Void)?,
                      to card: FootballEventPageCard10868) -> ((String) -> Void)? {
        guard let action else { return nil }
        return { id in action(card, id) }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .catalogue: catalogueMode
            case .original: originalMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual accepted Views, each with the host's own callbacks

    private var forecastInspection: ((Bool) -> Void)? {
        model.forecastInspectionAvailable(canOpen: onForecastInspection != nil) ? onForecastInspection : nil
    }

    /// The phase's headline, or the owner's unavailable words with the state line.
    @ViewBuilder func headlineContent() -> some View {
        if model.headlineResolves {
            switch input.headline.arm {
            case .before(let h): pregameHeadline(h)
            case .live(let h): liveHeadline(h)
            case .final(let h): finalHeadline(h)
            }
        } else {
            headlineUnavailable
        }
    }

    func pregameHeadline(_ h: FootballPregameHeadline10868) -> PregameComparisonHeadline9483<EmptyView> {
        PregameComparisonHeadline9483(
            sportKey: input.headline.sportKey, status: h.status, hasStarted: h.hasStarted,
            isOpeningLine: h.isOpeningLine, paired: h.paired, chancePhase: h.chancePhase,
            projectedPair: h.projected.map { (away: $0.away, home: $0.home) },
            forecastLabel: h.forecastLabel,
            awayName: teams.away, homeName: teams.home, awayColor: teams.awayColor, homeColor: teams.homeColor,
            pregameContext: h.pregameContext,
            identity: { _ in EmptyView() },
            onForecastInspection: forecastInspection)
    }

    func liveHeadline(_ h: FootballLiveHeadline10868) -> LiveEightValueHeadline9483<EmptyView> {
        LiveEightValueHeadline9483(
            sportKey: input.headline.sportKey, status: h.status, paired: h.paired, chancePhase: h.chancePhase,
            baseline: h.baseline, score: h.score, forecast: h.forecast,
            awayName: teams.away, homeName: teams.home, awayColor: teams.awayColor, homeColor: teams.homeColor,
            gameState: h.gameState,
            identity: { _ in EmptyView() },
            onProjectionInspection: forecastInspection)
    }

    func finalHeadline(_ h: FootballFinalHeadline10868) -> FinalComparisonHeadline9483<EmptyView> {
        FinalComparisonHeadline9483(
            sportKey: input.headline.sportKey, status: h.status, paired: h.paired, baseline: h.baseline,
            score: h.score, forecast: h.forecast,
            awayName: teams.away, homeName: teams.home, awayColor: teams.awayColor, homeColor: teams.homeColor,
            finalContext: h.finalContext,
            identity: { _ in EmptyView() },
            onForecastInspection: forecastInspection)
    }

    private var headlineUnavailable: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(input.header.state)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            scoreboard(compact: false)
            Text(input.copy.headlineUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(FootballEventPageAccessibilityID10868.headlineUnavailable)
    }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: onHistoryAction,
            onInspectionChoice: onHistoryInspectionChoice,
            onPlotPosition: onHistoryPlotPosition
        )
    }

    /// Total and margin: the final renderer where it applies, else the
    /// existing projected-finish card.
    @ViewBuilder func finishContent(expanded: Bool) -> some View {
        if let finish = model.finish {
            if NFLFinalComparisonPresentation9483.applies(finish) {
                NFLFinalComparisonPresentation9483(
                    card: finish, awayName: teams.awayShort, homeName: teams.homeShort,
                    awayColor: teams.awayColor, homeColor: teams.homeColor, expanded: expanded)
            } else {
                NFLFinishCardView9483(
                    card: finish, awayName: teams.awayShort, homeName: teams.homeShort,
                    awayColor: teams.awayColor, homeColor: teams.homeColor, expanded: expanded)
            }
        }
    }

    /// The production milestone card. Its Details exist only full size and
    /// only where the host presents them.
    func milestoneCard(_ card: NFLMilestoneCard9483, reader: Bool) -> NFLMilestoneCardView9483 {
        NFLMilestoneCardView9483(
            card: card,
            color: PlayerPropsTeam.color(for: card.side, home: teams.homeColor, away: teams.awayColor),
            state: cardState,
            expanded: reader && showsMilestoneDetails)
    }

    @ViewBuilder func milestoneContent(_ id: String, reader: Bool) -> some View {
        if let card = model.milestone(id) {
            milestoneCard(card, reader: reader)
        }
    }

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content, which also offers no expand of its own.
    func pairedContent(_ card: FootballEventPageCard10868,
                       activation: StoryStreamCardActivation10868?) -> PairedMilestonePresentation10868? {
        let paired = card == .teamSacks ? model.teamSacks : model.teamFieldGoals
        return paired.map {
            PairedMilestonePresentation10868(
                input: $0,
                onSelect: Self.relay(Self.bound(onTeamMilestoneSelect, to: card), through: activation),
                onDetails: Self.relay(Self.bound(onTeamMilestoneDetails, to: card), through: activation),
                onExpand: activation == nil
                    ? nil : Self.relay(Self.bound(onTeamMilestoneExpand, to: card), through: activation))
        }
    }

    @ViewBuilder func combinedContent(_ id: String, reader: Bool,
                                      activation: StoryStreamCardActivation10868?) -> some View {
        if let story = model.combined(id) {
            VStack(alignment: .leading, spacing: 16) {
                milestoneCard(story.card, reader: reader)
                AdditiveStatSplitPresentation10868(
                    input: story.split,
                    primaryTint: PlayerPropsTeam.color(for: story.card.side, home: teams.homeColor,
                                                       away: teams.awayColor),
                    secondaryTint: DS.textSecondary,
                    onDetails: Self.relay(onSplitDetails, through: activation))
            }
        }
    }

    /// The period-winner card with the host's callbacks, each after the
    /// stream's activation hook when it sits in the stream. Full size offers
    /// no open control of its own.
    func periodWinnersContent(activation: StoryStreamCardActivation10868?) -> FootballPeriodWinnersPresentation10868? {
        model.periodWinners.map { card in
            let expand: (() -> Void)? = activation == nil ? nil : onPeriodExpand.map { open in
                { activation?.request(); open() }
            }
            return FootballPeriodWinnersPresentation10868(
                input: card,
                onSelect: Self.relay(onPeriodSelect, through: activation),
                onDetails: Self.relay(onPeriodDetails, through: activation),
                onExpand: expand)
        }
    }

    /// The existing catalogue with the owner's originals and select callback.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: onOriginalSelect
            )
        }
    }

    /// The existing Details for the owner's held selection.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: onOriginalHistory
            )
        }
    }

    func openAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        onAbout?()
    }

    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        onAllProps?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            let arrangements = FootballEventPageModel10868.arrangements(
                sizeClass: sizeClass,
                accessibilitySize: typeSize.isAccessibilitySize
            )
            if arrangements == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    sideBySide
                    stacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(FootballEventPageAccessibilityID10868.page)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            stories
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            stories
                .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    // MARK: Anchor — the comparison above the history

    private var anchor: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            historyContent(reader: false)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(FootballEventPageCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(FootballEventPageAccessibilityID10868.anchor)
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            headlineContent()
                .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutAvailable(canOpen: onAbout != nil), let label = input.header.aboutLabel {
                Button(action: openAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(FootballEventPageAccessibilityID10868.about)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(FootballEventPageAccessibilityID10868.header)
    }

    /// Both short names, whole, with the owner's score figures between them
    /// once play has started. Accessibility sizes give each team its own line.
    @ViewBuilder private func scoreboard(compact: Bool) -> some View {
        let nameFont: Font = compact ? .headline : .title3.bold()
        let figures: (away: String, home: String)? = {
            if case .actual(let away, let home, _) = model.score { return (away, home) }
            return nil
        }()
        Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    teamLine(teams.awayShort, figure: figures?.away, font: nameFont)
                    teamLine(teams.homeShort, figure: figures?.home, font: nameFont)
                }
            } else {
                HStack(alignment: .center, spacing: 12) {
                    Text(teams.awayShort)
                        .font(nameFont)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if let figures {
                        HStack(spacing: 8) {
                            Text(figures.away)
                            Text("–").foregroundStyle(DS.textSecondary)
                            Text(figures.home)
                        }
                        .font(Font.title2.bold().monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    }
                    Text(teams.homeShort)
                        .font(nameFont)
                        .foregroundStyle(DS.textPrimary)
                        .multilineTextAlignment(.trailing)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(scoreSpoken)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(FootballEventPageAccessibilityID10868.score)
    }

    private func teamLine(_ name: String, figure: String?, font: Font) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(name)
                .font(font)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let figure {
                Text(figure)
                    .font(font.monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            }
        }
    }

    /// The owner's spoken score, its words for a missing one, or the two names.
    private var scoreSpoken: String {
        switch model.score {
        case .actual(_, _, let spoken): return spoken
        case .unavailable(let words): return "\(teams.awayShort), \(teams.homeShort). \(words)"
        case nil: return "\(teams.awayShort), \(teams.homeShort)"
        }
    }

    // MARK: Stories

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
                Button(action: openAllProps) {
                    HStack(spacing: 8) {
                        Text(label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "chevron.right")
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .padding(.horizontal, 16)
                    .frame(minHeight: controlSize)
                    .modifier(FootballEventPageCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(FootballEventPageAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(FootballEventPageAccessibilityID10868.stories)
    }

    /// The card the owner links to this stream card, with the stream's
    /// activation hook, or the owner's unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let kind = model.storyCard(card.id) {
            cardContent(kind, reader: false, activation: activation)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(FootballEventPageCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(FootballEventPageAccessibilityID10868.card(kind))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(FootballEventPageCardSurface10868())
                .accessibilityIdentifier(FootballEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: FootballEventPageCard10868, reader: Bool,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .finish: finishContent(expanded: reader)
        case .milestone(let id): milestoneContent(id, reader: reader)
        case .teamSacks, .teamFieldGoals: pairedContent(card, activation: activation)
        case .combined(let id): combinedContent(id, reader: reader, activation: activation)
        case .periodWinners: periodWinnersContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact names and score. The history also keeps the phase's
    /// comparison. A card this page does not show has no content.
    @ViewBuilder private func reader(_ card: FootballEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if card == .history {
                    headlineContent()
                }
                cardContent(card, reader: true, activation: nil)
            }
        }
    }

    private var compactHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            scoreboard(compact: true)
            Text(input.header.state)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: All props and the selected original's Details

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(FootballEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(FootballEventPageAccessibilityID10868.original)
        }
    }
}

/// The reference's white card on the page surface.
private struct FootballEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
