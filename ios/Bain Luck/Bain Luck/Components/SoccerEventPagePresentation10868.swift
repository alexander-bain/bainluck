import SwiftUI

// #10868 — the soccer match screen: one native presentation composed from the
// accepted leaves. Win chances lead. A fan sees, in this order: the match's
// state and date words with the about entry; home / Draw / away win chances
// as three equal named outcomes; both team names with the actual score once
// play has started; the owner's score, match-clock and projection context (or
// their honest absence); the probability history front and centre; and the
// phase's prop stories — goal milestones, both teams to score, first team to
// score and, when the owner has it, the half-by-half comparison — in the
// owner's story stream. Every story and the history open as full-size content
// made of the same Views.
//
// Presentation only, composed from the approved `LiveSoccer.tsx` /
// `liveSoccer.css` (`.sl-hero`, `.sl-kicker`, `.sl-winner-grid`,
// `.sl-scoreboard`, `.sl-warning`, `.sl-stories`) and `SoccerFinalPage.tsx` /
// `soccerFinal.css` (`.sf-hero`, `.sf-stories`, `SoccerHalfResultsCard`) as
// mounted in `Atlas.tsx`, with `StoryStream.tsx` for the stream. The
// reference's fixture loaders, replay/session state, dwell clock, ranking,
// source elections, window and scale state, catalogue, sheets and navigation
// are NOT ported. The leaves are the actual accepted Views:
//
//   • `SoccerThreeOutcomeHeadline11449` — the probability region;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `TotalMilestonePresentation10868` — goal milestones;
//   • `BothTeamsScorePresentation10868` — both teams to score;
//   • `FirstScorerComparisonPresentation10868` — first team to score;
//   • `PeriodOutcomeComparisonPresentation10868` — half by half;
//   • `StoryStreamPresentationView10868` — the controlled story stream.
//
// The only thing built here is the compact header around the headline: the
// owner's state and date words and the about entry above it, then the two
// names, the owner's score figures, and its score, clock and projection lines
// below it. Nothing here derives a phase, a state word, a score, a clock or a
// projection from another value; a pregame page shows no score even if one is
// supplied, and a projection's comparison with the actual needs play to have
// started. An unavailable clock or projection keeps the owner's own absence
// words on screen.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, reformats, copies
// or filters an observation, a name, a chance or a result. Draw and away keep
// their own missing words — never a complement of the home chance. The page
// phase is the owner's explicit soccer phase; a prop leaf whose own phase is
// not the page's is not mounted — never coerced to appear — and half by half
// is mounted only when the owner supplies it.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag. This layer wires each supplied card id to the one typed
// soccer card the owner names for it, and shows the owner's unavailable words
// for an id that names no single card this phase mounts — never a neighbour.
// A card's own select or Details action, and opening or closing its timing
// disclosure, first calls the stream's activation hook (so the owner can hold)
// and then the host's exact leaf callback or binding write; building a card or
// reading its disclosure asks for nothing. Full-size content reuses the same
// leaves with the host's exact callbacks and bindings and no activation, so
// opening a card never requests a hold by appearing.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, selection, readout, window,
// scale, inspection and other control is unchanged. It sits under the same
// three named outcomes so Draw and away unavailability stays in view.
//
// Phone stacks the anchor above the stories; a regular or unspecified size
// class (a Mac window) places them side by side while both columns keep their
// minimum widths, otherwise it stacks too, and accessibility sizes always
// stack. Every leaf keeps its own plot heights, scaled type, missing states
// and accessibility.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing
// to and from the catalogue and an original's Details, the held/received
// frame and every selection.
// This view keeps no state, runs no timer or animation, holds no subscription
// and presents no sheet or navigation of its own. Each mode below is content
// the host's existing container shows; every callback is the host's own
// closure handed to the leaf unchanged. With no callback, nothing pretends to
// act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one match snapshot, the phase, header words, score figures and their
// provenance, clock and projection words or absences, the three-outcome
// headline, the history input, each phase's prop inputs, the half-by-half
// input, the story stream and its card-to-kind map, and maps every callback
// to its existing controls.
//
// "All props" and the selected original's Details are two more content modes
// of this presenter, made of the existing original leaves:
//
//   • `OriginalMarketCatalogueView9483` — every retained original as an
//     adaptive card tile, under the compact names and score;
//   • `OriginalMarketDetailsView9483` — the held original's Details.
//
// Both take the owner's optional originals group unchanged: its admitted
// catalogue for one scope, its held selection, the selected original's
// recorded history, labels, copy and tint. Those leaves own each original's
// identity, chance slots and missing words, its separately admitted grade,
// its rules, provenance and historical last quote, and the history preview;
// nothing here re-elects, caps, sorts, filters or grades an original. A card
// tap hands the owner the leaf's exact scope and identity; a history control
// hands back the leaf's exact intent. The page's "All props" entry stays the
// owner's action. Entering either mode calls nothing: it selects nothing,
// opens no history, mounts no story stream and asks for no hold or resume.
// With no originals group, neither mode has content.
//
// Still owed: an owner that admits the originals group for the same snapshot
// as the page — all retained originals, labels that name each outcome (a
// card face shows its label and chances, not the outcome line) — and routes
// "All props", a card tap, Details and its history to the host's containers.

/// One card the page can show full size. `history` is the anchor; the others
/// are prop stories.
nonisolated enum SoccerEventPageCard10868: String, Hashable, CaseIterable {
    case history
    case goals
    case both
    case first
    case halves
}

/// What the host's container is showing, chosen by the host.
nonisolated enum SoccerEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// One card's full-size content.
    case reader(SoccerEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
}

/// The owner's explicit match phase for the whole screen. Never read from a
/// score, a clock or a result.
nonisolated enum SoccerEventPagePhase10868: Equatable {
    case before
    case live
    case final

    /// Each leaf's own name for the same phase.
    var totalPhase: TotalMilestonePhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }

    var bothPhase: BothTeamsPhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }

    var firstPhase: FirstScorerPhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }

    var periodPhase: PeriodOutcomePhase10868 {
        switch self {
        case .before: .before
        case .live: .during
        case .final: .final
        }
    }
}

nonisolated enum SoccerEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// The owner's actual score, read only once play has started.
nonisolated enum SoccerEventPageScore10868: Equatable {
    /// The owner's figures ("4", "0"), its provenance line ("Score observed
    /// Oct 12, 5:54 AM PT") and its spoken words ("Valladolid 4, Albacete 0").
    case actual(home: String, away: String, context: String?, spoken: String)
    /// The owner's words for a missing score ("Score unavailable").
    case unavailable(String)
}

/// The owner's projected-final context — a projection, never a chance.
nonisolated struct SoccerEventPageProjection10868: Equatable {
    /// "Projected final".
    let title: String
    /// The owner's projection words, or its absence ("No eligible projected final").
    let reading: SoccerSlotText11449
    /// Actual versus projection ("1.2 goals above projection"); shown once
    /// play has started. Nil draws none.
    let comparison: String?
}

/// The owner's words around the headline.
nonisolated struct SoccerEventPageHeader10868: Equatable {
    /// "LA LIGA 2 · IN PLAY", "FINAL · VALLADOLID WON".
    let state: String
    /// "Mon, Oct 12 · Kickoff 5:00 AM PT"; nil draws none.
    let date: String?
    let home: String
    let away: String
    /// Read during play and after the final only.
    let score: SoccerEventPageScore10868?
    /// The owner's match clock or its absence ("Match clock unavailable"); read
    /// during play and after the final only. Nil draws none.
    let clock: SoccerSlotText11449?
    /// Nil draws none.
    let projection: SoccerEventPageProjection10868?
    /// Spoken name of the about entry ("About this match"); nil draws none.
    let aboutLabel: String?
}

/// The owner's link from one stream card id to the typed card it shows.
nonisolated struct SoccerEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: SoccerEventPageCard10868
}

nonisolated struct SoccerEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Match stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single card this phase shows.
    let storyUnavailable: String
    /// "All props · 98"; nil draws no entry.
    let allPropsLabel: String?
}

nonisolated struct SoccerEventPageInput10868: Equatable {
    let phase: SoccerEventPagePhase10868
    let header: SoccerEventPageHeader10868
    let headline: SoccerThreeOutcomeHeadlineInput11449
    let history: FieldHistoryInput10868
    let goals: TotalMilestoneInput10868?
    let both: BothTeamsScoreInput10868?
    let first: FirstScorerComparisonInput10868?
    /// Mounted only when supplied.
    let halves: PeriodOutcomeComparisonInput10868?
    let stream: StoryStreamPresentation10868
    let stories: [SoccerEventPageStory10868]
    let copy: SoccerEventPageCopy10868
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct SoccerEventPageOriginals10868 {
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
    /// "98 retained originals · current chances withheld"; nil draws none.
    var context: String? = nil
    /// "No retained originals for this match".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum SoccerEventPageAccessibilityID10868 {
    static let page = "soccerEventPage10868.page"
    static let header = "soccerEventPage10868.header"
    static let score = "soccerEventPage10868.score"
    static let context = "soccerEventPage10868.context"
    static let about = "soccerEventPage10868.about"
    static let anchor = "soccerEventPage10868.anchor"
    static let stories = "soccerEventPage10868.stories"
    static let allProps = "soccerEventPage10868.allProps"
    static let unavailable = "soccerEventPage10868.story.unavailable"
    static let catalogue = "soccerEventPage10868.catalogue"
    static let original = "soccerEventPage10868.original"
    static func card(_ card: SoccerEventPageCard10868) -> String { "soccerEventPage10868.card.\(card.rawValue)" }
}

/// Which leaves the page mounts, resolved once per input.
nonisolated struct SoccerEventPageModel10868: Equatable {
    let input: SoccerEventPageInput10868

    init(_ input: SoccerEventPageInput10868) {
        self.input = input
    }

    // MARK: Header

    /// Nil before kickoff — a pregame page has no actual score.
    var score: SoccerEventPageScore10868? {
        input.phase == .before ? nil : input.header.score
    }

    var clock: SoccerSlotText11449? {
        input.phase == .before ? nil : input.header.clock
    }

    var projection: SoccerEventPageProjection10868? { input.header.projection }

    /// Actual versus projection needs an actual: not before kickoff.
    var projectionComparison: String? {
        input.phase == .before ? nil : Self.readable(input.header.projection?.comparison)
    }

    // MARK: Leaves — each only at its own phase

    var goals: TotalMilestoneInput10868? {
        guard let goals = input.goals, goals.phase == input.phase.totalPhase else { return nil }
        return goals
    }

    var both: BothTeamsScoreInput10868? {
        guard let both = input.both, both.phase == input.phase.bothPhase else { return nil }
        return both
    }

    var first: FirstScorerComparisonInput10868? {
        guard let first = input.first, first.phase == input.phase.firstPhase else { return nil }
        return first
    }

    var halves: PeriodOutcomeComparisonInput10868? {
        guard let halves = input.halves, halves.phase == input.phase.periodPhase else { return nil }
        return halves
    }

    func isMounted(_ card: SoccerEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .goals: goals != nil
        case .both: both != nil
        case .first: first != nil
        case .halves: halves != nil
        }
    }

    /// The typed story a stream card id names: exactly one owner link with
    /// that id, to a prop story this phase mounts. Otherwise nothing.
    func storyCard(_ cardID: String) -> SoccerEventPageCard10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let card = links.first?.card, card != .history, isMounted(card) else { return nil }
        return card
    }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: SoccerEventPageCard10868) -> Bool { isMounted(card) }

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

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries side by side, then stacks — the columns' minimum widths
    /// decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [SoccerEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

struct SoccerEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: SoccerEventPageInput10868
    var mode: SoccerEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: SoccerEventPageOriginals10868? = nil
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
    var onGoalSelect: ((String) -> Void)? = nil
    var onGoalDetails: ((String) -> Void)? = nil
    var onBothSelect: ((BothTeamsOutcomeRef10868) -> Void)? = nil
    var onBothDetails: ((BothTeamsOutcomeRef10868) -> Void)? = nil
    var onFirstSelect: ((String) -> Void)? = nil
    var onFirstDetails: ((String) -> Void)? = nil
    var onHalfSelect: ((String) -> Void)? = nil
    var onHalfDetails: ((String) -> Void)? = nil
    /// Page-owned timing disclosures. Full-size content gets them unchanged;
    /// a card in the stream gets them through `relay(_:through:)`.
    var goalTimingExpanded: Binding<Bool>? = nil
    var bothTimingExpanded: Binding<Bool>? = nil
    var firstTimingExpanded: Binding<Bool>? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .largeTitle) private var scoreSize: CGFloat = 40

    private var model: SoccerEventPageModel10868 { SoccerEventPageModel10868(input) }

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

    func headlineContent() -> SoccerThreeOutcomeHeadline11449 {
        SoccerThreeOutcomeHeadline11449(input: input.headline)
    }

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
    func goalsContent(activation: StoryStreamCardActivation10868? = nil) -> TotalMilestonePresentation10868? {
        model.goals.map {
            TotalMilestonePresentation10868(
                input: $0,
                onSelect: Self.relay(onGoalSelect, through: activation),
                onDetails: Self.relay(onGoalDetails, through: activation),
                timingExpanded: Self.relay(goalTimingExpanded, through: activation)
            )
        }
    }

    func bothContent(activation: StoryStreamCardActivation10868? = nil) -> BothTeamsScorePresentation10868? {
        model.both.map {
            BothTeamsScorePresentation10868(
                input: $0,
                onSelect: Self.relay(onBothSelect, through: activation),
                onDetails: Self.relay(onBothDetails, through: activation),
                timingExpanded: Self.relay(bothTimingExpanded, through: activation)
            )
        }
    }

    func firstContent(activation: StoryStreamCardActivation10868? = nil) -> FirstScorerComparisonPresentation10868? {
        model.first.map {
            FirstScorerComparisonPresentation10868(
                input: $0,
                onSelect: Self.relay(onFirstSelect, through: activation),
                onDetails: Self.relay(onFirstDetails, through: activation),
                timingExpanded: Self.relay(firstTimingExpanded, through: activation)
            )
        }
    }

    func halvesContent(activation: StoryStreamCardActivation10868? = nil) -> PeriodOutcomeComparisonPresentation10868? {
        model.halves.map {
            PeriodOutcomeComparisonPresentation10868(
                input: $0,
                onSelect: Self.relay(onHalfSelect, through: activation),
                onDetails: Self.relay(onHalfDetails, through: activation)
            )
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
            header
            let arrangements = SoccerEventPageModel10868.arrangements(
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
        .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.page)
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

    // MARK: Header — state and date, three outcomes, names and score, context

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(input.header.state)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                    if let date = SoccerEventPageModel10868.readable(input.header.date) {
                        Text(date)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
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
                    .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.about)
                }
            }
            headlineContent()
            scoreboard(compact: false)
            matchContext
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.header)
    }

    /// Both names, whole, with the owner's score figures between them once
    /// play has started. Accessibility sizes give each team its own line.
    @ViewBuilder private func scoreboard(compact: Bool) -> some View {
        let nameFont: Font = compact ? .headline : .title2.bold()
        let figures: (home: String, away: String)? = {
            if case .actual(let home, let away, _, _) = model.score { return (home, away) }
            return nil
        }()
        Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    teamLine(input.header.home, figure: figures?.home, font: nameFont)
                    teamLine(input.header.away, figure: figures?.away, font: nameFont)
                }
            } else {
                HStack(alignment: .center, spacing: 12) {
                    Text(input.header.home)
                        .font(nameFont)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if let figures {
                        HStack(spacing: 8) {
                            Text(figures.home)
                            Text("–").foregroundStyle(DS.textSecondary)
                            Text(figures.away)
                        }
                        .font(compact ? Font.title2.bold().monospacedDigit() : Font.system(size: scoreSize, weight: .bold).monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    }
                    Text(input.header.away)
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
        .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.score)
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

    /// The owner's spoken score, or the two names when there is none.
    private var scoreSpoken: String {
        if case .actual(_, _, _, let spoken) = model.score { return spoken }
        return "\(input.header.home), \(input.header.away)"
    }

    /// The owner's score provenance or absence, clock or absence, and
    /// projection or absence — each on its own line, nothing invented.
    @ViewBuilder private var matchContext: some View {
        let scoreLine: SoccerSlotText11449? = {
            switch model.score {
            case .actual(_, _, let context, _): SoccerEventPageModel10868.readable(context).map(SoccerSlotText11449.value)
            case .unavailable(let words): SoccerSlotText11449.unavailable(words)
            case nil: nil
            }
        }()
        let projection = model.projection
        if scoreLine != nil || model.clock != nil || projection != nil {
            VStack(alignment: .leading, spacing: 6) {
                if let scoreLine { contextLine(scoreLine) }
                if let clock = model.clock { contextLine(clock) }
                if let projection {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(projection.title)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                        contextLine(projection.reading)
                        if let comparison = model.projectionComparison {
                            Text(comparison)
                                .font(.subheadline)
                                .foregroundStyle(DS.textPrimary)
                        }
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.context)
        }
    }

    private func contextLine(_ text: SoccerSlotText11449) -> some View {
        Group {
            switch text {
            case .value(let words):
                Text(words).foregroundStyle(DS.textPrimary)
            case .unavailable(let words):
                Text(words).foregroundStyle(DS.textSecondary)
            }
        }
        .font(.subheadline)
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Anchor and stories

    private var anchor: some View {
        historyContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(SoccerEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.anchor)
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
                    .modifier(SoccerEventPageCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.stories)
    }

    /// The typed card the owner links to this stream card, with the stream's
    /// activation hook, or the owner's unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let kind = model.storyCard(card.id) {
            cardContent(kind, activation: activation)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(SoccerEventPageCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.card(kind))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(SoccerEventPageCardSurface10868())
                .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: SoccerEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .goals: goalsContent(activation: activation)
        case .both: bothContent(activation: activation)
        case .first: firstContent(activation: activation)
        case .halves: halvesContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact names and score. The history also keeps the three
    /// named outcomes. A card this phase does not show has no content.
    @ViewBuilder private func reader(_ card: SoccerEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if card == .history {
                    headlineContent()
                }
                cardContent(card, activation: nil)
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

    /// Every retained original under the compact names and score.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(SoccerEventPageAccessibilityID10868.original)
        }
    }
}

/// The reference's white card on the page surface.
private struct SoccerEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
