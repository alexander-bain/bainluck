import SwiftUI

// #10868 — the baseball game screen (`mlb`): one native presentation composed
// from the accepted leaves. Win chances lead. A fan sees, in this order: the
// owner's eyebrow, the game state and its own context; both teams' chances
// and runs as one aligned comparison matrix — before first pitch each team's
// win chance; during play the pregame chance, the current chance (which
// leads) and the runs so far; after the final the pregame chance reminder,
// the final runs (which lead) and the owner's result words — with the owner's
// projected-final line or its honest absence; the two-team win-probability
// history front and centre; then the owner's story stream of the phase's
// prop stories and the "All props" entry. The history and each story open as
// full-size content made of the same Views, and "All props" and the selected
// original's Details are two more content modes.
//
// Presentation only, composed from the approved Atlas `mlb` route
// (`BaseballStories`, `BaseballHomeRunComparison`, `PlayerClocks`,
// `SettlementLadder`, `AssociatedSeriesCard`, `StoryStream`, `CardFocus`) and
// the route tracker's three phases. The reference's fixture rows, ranking
// (`baseballMomentOrder`) and its reasons, story and reader session state,
// keyboard handling, sheets and focus restoration are NOT ported. The leaves
// are the actual accepted Views:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `MLBHomeRunComparison11284` — home runs, after the final;
//   • `MLBStrikeoutComparison11284` — the strikeout ladder, after the final;
//   • `TotalMilestonePresentation10868` — run milestones before and during
//     play; `MLBTotalTargetsCardView11284` — the final total against every
//     offered run line, after the final;
//   • `MLBSeriesComparison11284` — the associated series, in every phase;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the selected original's Details.
//
// The one thing built here is the comparison matrix, because the existing
// paired headlines admit only NFL and NBA (their `applies` gates) and print
// points. It is typed per phase so a slot cannot move between phases. Every
// figure, absence, column title, provenance line, result word and the
// projection line arrive resolved by the owner and are shown verbatim.
// Nothing here parses, rounds, complements, subtracts or formats a value,
// admits a forecast, or turns a final score into a quote. A matrix whose phase
// is not the page's is not drawn — the owner's unavailable words are. Wide
// widths print full names; a narrow width tries the owner's short names;
// accessibility sizes, or a width where neither grid fits, give each team a
// block of labelled values instead of shrinking text. Away is listed first,
// then home, as the app's adopted paired headline lists them.
//
// The page's phase is the owner's explicit `BaseballEventPagePhase10868`,
// never read from a raw status, an inning, a quote or a result. Home runs and
// the strikeout ladder are the final comparisons (each player's pregame chance
// beside the official final) and are mounted after the final only. The totals
// story is mounted only in its own form for the phase: run milestones before
// and during play, the final total against every offered line after it. The
// series is separate from this game and is mounted in every phase. A leaf from
// another phase is not mounted — never coerced to appear.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot, including every selection: the strikeout target, the run
// line or milestone, and the series market and outcome. This layer groups them
// and never re-elects, defaults, copies, filters or formats an observation, a
// count, a chance or a result.
//
// The strikeout target strip, the final run-line strip and the series
// selectors are their leaves' own controls and always act, so those stories
// are mounted only when the host supplies the callbacks they need (and the
// final run-line card also its Details callback, which its full-size form
// always draws); otherwise the stream cell shows the owner's unavailable words
// — never a strip that does nothing.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag. This layer wires each supplied card id to the one typed
// baseball story the owner names for it, and shows the owner's unavailable
// words for an id that names no single story this phase mounts — never a
// neighbour. A card's own select or Details action, and opening or closing the
// run milestones' timing disclosure, first calls the stream's activation hook
// (so the owner can hold) and then the host's exact leaf callback or binding
// write; building a card or reading its disclosure asks for nothing.
// Full-size content reuses the same leaves with the host's exact callbacks and
// bindings and no activation, so opening a card never requests a hold by
// appearing.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, guide, selection, readout,
// window, scale, inspection and other control is unchanged. It sits under the
// same matrix so the comparison stays in view.
//
// Phone stacks the anchor above the stories; a regular or unspecified size
// class (a Mac window) places them side by side while both columns keep their
// minimum widths, otherwise it stacks too, and accessibility sizes always
// stack. Every leaf keeps its own plot heights, scaled type, missing states and
// accessibility.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing to
// and from the catalogue and an original's Details, each story original's
// Details, the held/received frame and every selection. This view keeps no
// state, runs no timer or animation, holds no subscription and presents no
// sheet or navigation of its own. Every callback is the host's own closure
// handed to the leaf unchanged. With no callback, nothing pretends to act.
//
// Host binding: `BaseballEventPageHost10868`
// (`Utilities/BaseballEventPageHostAdapter10868.swift`) builds this input from
// the event page's own bodies; its mount into `EventDetailView` is a proposal,
// not applied.

/// One card the page can show full size. `history` is the anchor.
nonisolated enum BaseballEventPageCard10868: String, Hashable, CaseIterable {
    case history
    case homeRuns
    case strikeouts
    case totals
    case series
}

/// What the host's container is showing, chosen by the host.
nonisolated enum BaseballEventPageMode10868: Equatable {
    /// The game screen body.
    case page
    /// One card's full-size content.
    case reader(BaseballEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
}

/// The owner's explicit game phase for the whole screen. Never read from a
/// score, an inning or a result.
nonisolated enum BaseballEventPagePhase10868: Equatable {
    case before
    case live
    case final

    /// The run milestones leaf's own name for the same phase.
    var totalPhase: TotalMilestonePhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }
}

nonisolated enum BaseballEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// One matrix figure: the owner's formatted figure with its spoken words, or
/// the owner's own words for why there is none.
nonisolated enum BaseballSlot10868: Equatable {
    case value(String, spoken: String)
    case unavailable(String)

    var text: String {
        switch self {
        case .value(let text, _): text
        case .unavailable(let words): words
        }
    }

    var spoken: String {
        switch self {
        case .value(_, let spoken): spoken
        case .unavailable(let words): words
        }
    }

    var isValue: Bool {
        if case .value = self { return true }
        return false
    }
}

/// One matrix column: its title and the owner's provenance line for its
/// values ("Pre-match · Kalshi", "Recorded Oct 1, 5:15 PM · Bain Luck").
nonisolated struct BaseballColumn10868: Equatable {
    let title: String
    /// Nil draws none.
    let provenance: String?
}

nonisolated struct BaseballTeam10868: Equatable {
    /// The served name, whole.
    let name: String
    /// The owner's short name, tried only where the whole names do not fit;
    /// nil keeps the whole name.
    let short: String?
    let tint: Color
}

nonisolated struct BaseballBeforeRow10868: Equatable {
    let chance: BaseballSlot10868
}

nonisolated struct BaseballLiveRow10868: Equatable {
    let pregameChance: BaseballSlot10868
    let currentChance: BaseballSlot10868
    let runs: BaseballSlot10868
}

nonisolated struct BaseballFinalRow10868: Equatable {
    let pregameChance: BaseballSlot10868
    let finalRuns: BaseballSlot10868
    /// The owner's result words ("Won", "Lost"); nil draws none.
    let result: String?
}

nonisolated struct BaseballBeforeMatrix10868: Equatable {
    let chance: BaseballColumn10868
    let home: BaseballBeforeRow10868
    let away: BaseballBeforeRow10868
}

nonisolated struct BaseballLiveMatrix10868: Equatable {
    let pregameChance: BaseballColumn10868
    let currentChance: BaseballColumn10868
    let runs: BaseballColumn10868
    let home: BaseballLiveRow10868
    let away: BaseballLiveRow10868
}

nonisolated struct BaseballFinalMatrix10868: Equatable {
    let pregameChance: BaseballColumn10868
    let finalRuns: BaseballColumn10868
    let home: BaseballFinalRow10868
    let away: BaseballFinalRow10868
}

/// The comparison matrix, typed per phase.
nonisolated enum BaseballMatrix10868: Equatable {
    case before(BaseballBeforeMatrix10868)
    case live(BaseballLiveMatrix10868)
    case final(BaseballFinalMatrix10868)

    var phase: BaseballEventPagePhase10868 {
        switch self {
        case .before: .before
        case .live: .live
        case .final: .final
        }
    }
}

/// The owner's projected-final line — a projection, never a chance — or its
/// absence words.
nonisolated struct BaseballProjection10868: Equatable {
    /// "Projected final".
    let title: String
    let reading: BaseballSlot10868
}

nonisolated struct BaseballHeadlineInput10868: Equatable {
    /// The served league words ("MLB"); nil draws none.
    let eyebrow: String?
    /// "Before first pitch", "Middle 3rd", "Final".
    let state: String
    /// "Wed, Sep 30 · First pitch 2:00 PM", "Game state from ESPN"; nil draws none.
    let stateContext: String?
    let home: BaseballTeam10868
    let away: BaseballTeam10868
    let matrix: BaseballMatrix10868
    /// Nil draws none.
    let projection: BaseballProjection10868?
    /// Spoken name of the matrix group ("Baseball win chances and runs").
    let spokenLabel: String
}

// MARK: - The stories — each the accepted leaf's own input

/// After the final: players' saved pregame chances of a home run beside their
/// official final counts (`MLBHomeRunCard11284`, unchanged).
struct BaseballHomeRunsStory10868: Equatable {
    let card: MLBHomeRunCard11284
    let awayColor: Color
    let homeColor: Color
}

/// After the final: one pitcher's strikeout ladder (`MLBMilestoneCard11284`)
/// and the host's resolved target; nil is unselected.
struct BaseballStrikeoutsStory10868: Equatable {
    let card: MLBMilestoneCard11284
    let selectedRowID: String?
    let color: Color
}

/// After the final: every offered full-game run line (`MLBTotalsCard11284`),
/// the host's resolved line and the score tuple the page prints.
struct BaseballFinalTotals10868: Equatable {
    let card: MLBTotalsCard11284
    let selectedOptionKey: String?
    let homeName: String
    let awayName: String
    let homeColor: Color
    let awayColor: Color
    /// Nil wherever the page prints no score.
    let homeScore: Int?
    let awayScore: Int?
}

/// The run totals story, in its one form for the phase.
enum BaseballTotalsStory10868: Equatable {
    /// Before and during play: the run milestones.
    case milestones(TotalMilestoneInput10868)
    /// After the final: the final total against every offered line.
    case finalTargets(BaseballFinalTotals10868)

    /// Whether this form belongs to the page's phase.
    func belongs(to phase: BaseballEventPagePhase10868) -> Bool {
        switch self {
        case .milestones(let input): phase != .final && input.phase == phase.totalPhase
        case .finalTargets: phase == .final
        }
    }
}

/// In every phase: the associated series' own markets (`MLBSeriesCard11284`)
/// and the host's resolved market and outcome; nil is unselected.
struct BaseballSeriesStory10868: Equatable {
    let card: MLBSeriesCard11284
    let selectedQuestionKey: String?
    let selectedOptionKey: String?
    let color: Color
}

/// The owner's link from one stream card id to the typed story it shows.
nonisolated struct BaseballEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: BaseballEventPageCard10868
}

nonisolated struct BaseballEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Game stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a matrix whose phase is not the page's.
    let matrixUnavailable: String
    /// "All props · 623"; nil draws no entry.
    let allPropsLabel: String?
}

struct BaseballEventPageInput10868: Equatable {
    let phase: BaseballEventPagePhase10868
    let headline: BaseballHeadlineInput10868
    let history: FieldHistoryInput10868
    let homeRuns: BaseballHomeRunsStory10868?
    let strikeouts: BaseballStrikeoutsStory10868?
    let totals: BaseballTotalsStory10868?
    let series: BaseballSeriesStory10868?
    let stream: StoryStreamPresentation10868
    let stories: [BaseballEventPageStory10868]
    let copy: BaseballEventPageCopy10868
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct BaseballEventPageOriginals10868 {
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
    /// "623 originals"; nil draws none.
    var context: String? = nil
    /// "No original props recorded for this game".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum BaseballEventPageAccessibilityID10868 {
    static let page = "baseballEventPage10868.page"
    static let headline = "baseballEventPage10868.headline"
    static let matrix = "baseballEventPage10868.matrix"
    static let matrixUnavailable = "baseballEventPage10868.matrix.unavailable"
    static let projection = "baseballEventPage10868.projection"
    static let anchor = "baseballEventPage10868.anchor"
    static let stories = "baseballEventPage10868.stories"
    static let allProps = "baseballEventPage10868.allProps"
    static let unavailable = "baseballEventPage10868.story.unavailable"
    static let catalogue = "baseballEventPage10868.catalogue"
    static let original = "baseballEventPage10868.original"
    static func card(_ card: BaseballEventPageCard10868) -> String { "baseballEventPage10868.card.\(card.rawValue)" }
}

// MARK: - The matrix as laid out

/// One team's row, in the columns' order.
nonisolated struct BaseballMatrixRow10868: Equatable {
    let team: BaseballTeam10868
    let cells: [BaseballSlot10868]
    let result: String?
}

/// One value with its column's title, for the labelled-block arrangement.
nonisolated struct BaseballLabelledValue10868: Equatable {
    let title: String
    let slot: BaseballSlot10868
    let lead: Bool
}

/// The typed matrix as columns and rows: away first, then home.
nonisolated struct BaseballMatrixLayout10868: Equatable {
    let columns: [BaseballColumn10868]
    /// The column drawn as the lead figure, in the team's tint.
    let lead: Int
    let rows: [BaseballMatrixRow10868]

    static func of(_ headline: BaseballHeadlineInput10868) -> BaseballMatrixLayout10868 {
        switch headline.matrix {
        case .before(let m):
            return BaseballMatrixLayout10868(columns: [m.chance], lead: 0, rows: [
                BaseballMatrixRow10868(team: headline.away, cells: [m.away.chance], result: nil),
                BaseballMatrixRow10868(team: headline.home, cells: [m.home.chance], result: nil),
            ])
        case .live(let m):
            return BaseballMatrixLayout10868(columns: [m.pregameChance, m.currentChance, m.runs], lead: 1, rows: [
                BaseballMatrixRow10868(team: headline.away,
                                       cells: [m.away.pregameChance, m.away.currentChance, m.away.runs], result: nil),
                BaseballMatrixRow10868(team: headline.home,
                                       cells: [m.home.pregameChance, m.home.currentChance, m.home.runs], result: nil),
            ])
        case .final(let m):
            return BaseballMatrixLayout10868(columns: [m.pregameChance, m.finalRuns], lead: 1, rows: [
                BaseballMatrixRow10868(team: headline.away, cells: [m.away.pregameChance, m.away.finalRuns],
                                       result: m.away.result),
                BaseballMatrixRow10868(team: headline.home, cells: [m.home.pregameChance, m.home.finalRuns],
                                       result: m.home.result),
            ])
        }
    }

    /// The runs column, where the phase has one.
    var runsColumn: Int? {
        switch columns.count {
        case 3: 2
        case 2: 1
        default: nil
        }
    }

    func values(_ row: BaseballMatrixRow10868) -> [BaseballLabelledValue10868] {
        zip(columns.indices, row.cells).map { index, slot in
            BaseballLabelledValue10868(title: columns[index].title, slot: slot, lead: index == lead)
        }
    }

    /// Each column's provenance, said once under the matrix.
    var support: [String] {
        columns.compactMap { column in column.provenance.map { "\(column.title): \($0)" } }
    }

    /// Every title, value and result in words, team by team.
    var spoken: String {
        rows.map { row in
            let parts = values(row).map { "\($0.title) \($0.slot.spoken)" }
            let result = row.result.map { [$0] } ?? []
            return "\(row.team.name): \((parts + result).joined(separator: ", "))"
        }.joined(separator: ". ")
    }
}

/// Which leaves the page mounts, resolved once per input.
struct BaseballEventPageModel10868: Equatable {
    let input: BaseballEventPageInput10868

    init(_ input: BaseballEventPageInput10868) {
        self.input = input
    }

    // MARK: Headline

    /// A matrix from another phase is never drawn.
    var headlineShows: Bool { input.headline.matrix.phase == input.phase }

    var layout: BaseballMatrixLayout10868 { BaseballMatrixLayout10868.of(input.headline) }

    /// "White Sox 7 – 3 Astros" for the readers' compact heading: both runs
    /// figures exactly as the matrix prints them, only when both are values.
    var compactScore: String? {
        let layout = self.layout
        guard headlineShows, let column = layout.runsColumn, layout.rows.count == 2,
              case .value(let away, _) = layout.rows[0].cells[column],
              case .value(let home, _) = layout.rows[1].cells[column] else { return nil }
        let awayName = layout.rows[0].team.short ?? layout.rows[0].team.name
        let homeName = layout.rows[1].team.short ?? layout.rows[1].team.name
        return "\(awayName) \(away) – \(home) \(homeName)"
    }

    // MARK: Leaves — each only at its own phase

    var homeRuns: BaseballHomeRunsStory10868? {
        input.phase == .final ? input.homeRuns : nil
    }

    var strikeouts: BaseballStrikeoutsStory10868? {
        input.phase == .final ? input.strikeouts : nil
    }

    var totals: BaseballTotalsStory10868? {
        guard let totals = input.totals, totals.belongs(to: input.phase) else { return nil }
        return totals
    }

    var series: BaseballSeriesStory10868? { input.series }

    func isMounted(_ card: BaseballEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .homeRuns: homeRuns != nil
        case .strikeouts: strikeouts != nil
        case .totals: totals != nil
        case .series: series != nil
        }
    }

    /// The typed story a stream card id names: exactly one owner link with
    /// that id, to a story this phase mounts. Otherwise nothing.
    func storyCard(_ cardID: String) -> BaseballEventPageCard10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let card = links.first?.card, card != .history, isMounted(card) else { return nil }
        return card
    }

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

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries side by side, then stacks — the columns' minimum widths
    /// decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [BaseballEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

struct BaseballEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: BaseballEventPageInput10868
    var mode: BaseballEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: BaseballEventPageOriginals10868? = nil
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
    /// A home-run row's `original.id`.
    var onHomeRunDetails: ((String) -> Void)? = nil
    /// A strikeout target's `rowID`. Required for the strikeout story.
    var onStrikeoutSelect: ((String) -> Void)? = nil
    /// The selected target's `original.id`.
    var onStrikeoutDetails: ((String) -> Void)? = nil
    /// A run milestone's id or a final run line's option key — the same
    /// producer identity. Required for the final run-line story.
    var onTotalSelect: ((String) -> Void)? = nil
    /// A run milestone's Details.
    var onTotalMilestoneDetails: ((String) -> Void)? = nil
    /// The selected final run line's `original.id`. Required for the final
    /// run-line story, whose full-size form always draws its Details control.
    var onTotalLineDetails: ((String) -> Void)? = nil
    /// A series market's `questionKey`. Required for the series story.
    var onSeriesMarket: ((String) -> Void)? = nil
    /// A series tile's `(questionKey, optionKey)`. Required for the series story.
    var onSeriesOption: ((String, String) -> Void)? = nil
    /// The selected series outcome's `original.id`.
    var onSeriesDetails: ((String) -> Void)? = nil
    /// Page-owned run milestones timing disclosure. Full-size content gets it
    /// unchanged; a card in the stream gets it through `relay(_:through:)`.
    var totalTimingExpanded: Binding<Bool>? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .title) private var leadSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 22

    private var model: BaseballEventPageModel10868 { BaseballEventPageModel10868(input) }

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

    /// The same, for the series tile's two-part selection.
    static func relayPair(_ action: ((String, String) -> Void)?,
                          through activation: StoryStreamCardActivation10868?) -> ((String, String) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { first, second in
            activation.request()
            action(first, second)
        }
    }

    /// A timing disclosure is an interaction too: in the stream, opening or
    /// closing it asks the stream's activation hook first, then writes the
    /// exact new value to the owner's binding. Reading it asks for nothing.
    /// No binding: none. No activation: the owner's binding itself.
    static func relay(_ binding: Binding<Bool>?,
                      through activation: StoryStreamCardActivation10868?) -> Binding<Bool>? {
        guard let binding else { return nil }
        guard let activation else { return binding }
        return Binding(
            get: { binding.wrappedValue },
            set: { expanded in
                activation.request()
                binding.wrappedValue = expanded
            }
        )
    }

    /// Whether the host supplied every callback this story's leaf always
    /// draws as a control.
    func controlsReady(_ card: BaseballEventPageCard10868) -> Bool {
        switch card {
        case .history, .homeRuns:
            return true
        case .strikeouts:
            return onStrikeoutSelect != nil
        case .totals:
            if case .finalTargets? = model.totals { return onTotalSelect != nil && onTotalLineDetails != nil }
            return true
        case .series:
            return onSeriesMarket != nil && onSeriesOption != nil
        }
    }

    /// A story this phase mounts and the host can drive.
    func shows(_ card: BaseballEventPageCard10868) -> Bool {
        model.isMounted(card) && controlsReady(card)
    }

    /// The typed story a stream card id names, when it can be shown.
    func storyKind(_ cardID: String) -> BaseballEventPageCard10868? {
        guard let card = model.storyCard(cardID), controlsReady(card) else { return nil }
        return card
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

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: onHistoryAction,
            onInspectionChoice: onHistoryInspectionChoice,
            onPlotPosition: onHistoryPlotPosition
        )
    }

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content.
    func homeRunsContent(activation: StoryStreamCardActivation10868? = nil) -> MLBHomeRunComparison11284? {
        model.homeRuns.map {
            MLBHomeRunComparison11284(card: $0.card, awayColor: $0.awayColor, homeColor: $0.homeColor,
                                      onDetails: Self.relay(onHomeRunDetails, through: activation))
        }
    }

    func strikeoutsContent(activation: StoryStreamCardActivation10868? = nil,
                           expanded: Bool = false) -> MLBStrikeoutComparison11284? {
        guard let story = model.strikeouts,
              let select = Self.relay(onStrikeoutSelect, through: activation) else { return nil }
        return MLBStrikeoutComparison11284(
            card: story.card, selectedRowID: story.selectedRowID, color: story.color, expanded: expanded,
            onSelect: select, onDetails: Self.relay(onStrikeoutDetails, through: activation))
    }

    func totalMilestonesContent(activation: StoryStreamCardActivation10868? = nil) -> TotalMilestonePresentation10868? {
        guard case .milestones(let milestones)? = model.totals else { return nil }
        return TotalMilestonePresentation10868(
            input: milestones,
            onSelect: Self.relay(onTotalSelect, through: activation),
            onDetails: Self.relay(onTotalMilestoneDetails, through: activation),
            timingExpanded: Self.relay(totalTimingExpanded, through: activation))
    }

    func finalTotalsContent(activation: StoryStreamCardActivation10868? = nil,
                            expanded: Bool = false) -> MLBTotalTargetsCardView11284? {
        guard case .finalTargets(let totals)? = model.totals,
              let select = Self.relay(onTotalSelect, through: activation),
              let details = Self.relay(onTotalLineDetails, through: activation) else { return nil }
        return MLBTotalTargetsCardView11284(
            card: totals.card, selectedOptionKey: totals.selectedOptionKey,
            homeName: totals.homeName, awayName: totals.awayName,
            homeColor: totals.homeColor, awayColor: totals.awayColor,
            homeScore: totals.homeScore, awayScore: totals.awayScore,
            expanded: expanded, onSelect: select, onDetails: details)
    }

    func seriesContent(activation: StoryStreamCardActivation10868? = nil) -> MLBSeriesComparison11284? {
        guard let story = model.series,
              let market = Self.relay(onSeriesMarket, through: activation),
              let option = Self.relayPair(onSeriesOption, through: activation) else { return nil }
        return MLBSeriesComparison11284(
            card: story.card, selectedQuestionKey: story.selectedQuestionKey,
            selectedOptionKey: story.selectedOptionKey, color: story.color,
            onSelectMarket: market, onSelectOption: option,
            onDetails: Self.relay(onSeriesDetails, through: activation))
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

    /// The existing Details for the owner's held selection, with its recorded
    /// history and history callback.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: onOriginalHistory
            )
        }
    }

    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        onAllProps?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            headline
            let arrangements = BaseballEventPageModel10868.arrangements(
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
        .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.page)
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

    // MARK: Headline — state, matrix, projection and each column's provenance

    private var headline: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let eyebrow = BaseballEventPageModel10868.readable(input.headline.eyebrow) {
                Text(eyebrow)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DS.textSecondary)
            }
            stateLines
            matrixOrAbsence
            if let projection = input.headline.projection {
                projectionLine(projection)
            }
            if model.headlineShows {
                supportLines
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.headline)
    }

    private var stateLines: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(input.headline.state)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            if let context = BaseballEventPageModel10868.readable(input.headline.stateContext) {
                Text(context)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var matrixOrAbsence: some View {
        if model.headlineShows {
            matrixView
        } else {
            Text(input.copy.matrixUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.matrixUnavailable)
        }
    }

    /// Full names in one grid where they fit, then the short names, then one
    /// block of labelled values per team; accessibility sizes take the blocks.
    private var matrixView: some View {
        let layout = model.layout
        return Group {
            if typeSize.isAccessibilitySize {
                matrixBlocks(layout)
            } else {
                ViewThatFits(in: .horizontal) {
                    matrixGrid(layout, short: false)
                    matrixGrid(layout, short: true)
                    matrixBlocks(layout)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(input.headline.spokenLabel). \(layout.spoken)")
        .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.matrix)
    }

    private func matrixGrid(_ layout: BaseballMatrixLayout10868, short: Bool) -> some View {
        Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 14, verticalSpacing: 10) {
            GridRow {
                Color.clear
                    .gridCellUnsizedAxes([.horizontal, .vertical])
                ForEach(Array(layout.columns.enumerated()), id: \.offset) { _, column in
                    Text(column.title)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize()
                }
            }
            ForEach(Array(layout.rows.enumerated()), id: \.offset) { _, row in
                GridRow {
                    teamCell(row, short: short)
                    ForEach(Array(row.cells.enumerated()), id: \.offset) { index, cell in
                        figure(cell, lead: index == layout.lead, tint: row.team.tint)
                    }
                }
            }
        }
    }

    private func teamCell(_ row: BaseballMatrixRow10868, short: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(short ? (row.team.short ?? row.team.name) : row.team.name)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
            if let result = row.result {
                Text(result)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize()
            }
        }
    }

    private func matrixBlocks(_ layout: BaseballMatrixLayout10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array(layout.rows.enumerated()), id: \.offset) { _, row in
                VStack(alignment: .leading, spacing: 8) {
                    Text(row.team.name)
                        .font(.headline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let result = row.result {
                        Text(result)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                    }
                    ForEach(Array(layout.values(row).enumerated()), id: \.offset) { _, value in
                        labelledValue(value, tint: row.team.tint)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func labelledValue(_ value: BaseballLabelledValue10868, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value.title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            figure(value.slot, lead: value.lead, tint: tint)
        }
    }

    /// A value at the figure size (the lead in the team's tint), or the
    /// owner's absence words as legible secondary text — never a word posing
    /// as a number.
    @ViewBuilder private func figure(_ slot: BaseballSlot10868, lead: Bool, tint: Color) -> some View {
        switch slot {
        case .value(let text, _):
            Text(text)
                .font(.system(size: lead ? leadSize : figureSize, weight: .bold).monospacedDigit())
                .foregroundStyle(lead ? tint : DS.textPrimary)
                .fixedSize()
        case .unavailable(let words):
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func projectionLine(_ projection: BaseballProjection10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(projection.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            Text(projection.reading.text)
                .font(.subheadline)
                .foregroundStyle(projection.reading.isValue ? DS.textPrimary : DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.projection)
    }

    @ViewBuilder private var supportLines: some View {
        let lines = model.layout.support
        if !lines.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Anchor and stories

    private var anchor: some View {
        historyContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(BaseballEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.anchor)
    }

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
                    .modifier(BaseballEventPageCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.stories)
    }

    /// The typed story the owner links to this stream card, with the stream's
    /// activation hook, or the owner's unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let kind = storyKind(card.id) {
            cardContent(kind, activation: activation, expanded: false)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(BaseballEventPageCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.card(kind))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(BaseballEventPageCardSurface10868())
                .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: BaseballEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?,
                                          expanded: Bool) -> some View {
        switch card {
        case .history:
            historyContent(reader: true)
        case .homeRuns:
            homeRunsContent(activation: activation)
        case .strikeouts:
            strikeoutsContent(activation: activation, expanded: expanded)
        case .totals:
            if let milestones = totalMilestonesContent(activation: activation) {
                milestones
            } else {
                finalTotalsContent(activation: activation, expanded: expanded)
            }
        case .series:
            seriesContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact heading. The history also keeps the matrix. A card
    /// this phase does not show, or the host cannot drive, has no content.
    @ViewBuilder private func reader(_ card: BaseballEventPageCard10868) -> some View {
        if shows(card) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if card == .history, model.headlineShows {
                    matrixView
                }
                cardContent(card, activation: nil, expanded: true)
            }
        }
    }

    private var compactHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let score = model.compactScore {
                Text(score)
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(input.headline.state)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: All props and the selected original's Details

    /// Every retained original under the compact heading.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(BaseballEventPageAccessibilityID10868.original)
        }
    }
}

/// The reference's white card on the page surface.
private struct BaseballEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
