import SwiftUI

// #10868 — the golf WINNER ARCHIVE final page: a finished tournament-winner
// market read after the final round. A fan sees the tournament winner with the
// owner's actual total against par beside that golfer's own dated pre-event
// chance; the chosen golfer's recorded win-chance history as the anchor, with
// that golfer's readout (pre-event chance, the market's own result, the
// reported score, round availability and Details); and the scorecard story:
// the owner's featured golfers, each with a pre-event chance, a small plot of
// actual strokes against par per round and a separately reported total. Every
// original stays reachable through the finite golfer chooser and All props.
//
// Presentation only, from the approved final golf composition and its archive
// golfer chooser (visual and semantic references only). Their evidence loader,
// baseline cutoff, featured election and sort, ceiling ladder, segment and gap
// policy, band function, page arithmetic, probability and clock formatting,
// scale toggle state, catalogue session and sheets are NOT ported. All of that
// is the owner's input.
//
// Why a new composition: the golf page always mounts its finish card and
// requires its fixed finish slots; the pre-tournament golf page and the field
// page carry no winner hero, no actual round scores and no second, independent
// golfer selection. Nothing existing draws strokes against par.
//
// What is mounted, unchanged:
//   • `FieldPhaseHeadlinePresentation10868` — the winner hero: the owner's
//     eyebrow, title and About entry, the winner's own dated pre-event figure
//     and separately reported finish, and the owner's state words. Mounted
//     only while its own phase is the final; otherwise the owner's words.
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, on a
//     presentation copy that changes only its height (the finite, never-shorter
//     full-size height from `RugbyMatchEventPageModel10868.readerPlotHeight`)
//     and its expand control (`VolleyballFieldEventPageModel10868.presentationCopy`).
//     Its runs, gaps, hollow/filled marks, range choices and inspection are
//     the owner's.
//   • `FieldContenderChooserPresentation10868` with the pre-tournament golf
//     page's chooser hierarchy (`GolfPreTournamentChooserNavigation10868`, its
//     model and its presentation) — one chooser per selection role, each with
//     its own owner modes, bands and pages, never one button per group.
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     every original, the held original's Details and rules.
//   • `StoryStreamPresentationView10868` — the story stream; a card's own
//     actions request the stream's interaction first.
//   • `FieldEventPageAboutContent10868`, `FieldEventPageReaderHeader10868`,
//     `FieldEventPageOriginals10868`, the field page's hold helpers and
//     arrangement rule, and the qualification page's equal-column grid over
//     `OriginalMarketCatalogue9483.geometry`.
//
// Built here, because nothing existing draws them: the round-score leaf
// (`GolfRoundScorePresentation10868`) — actual strokes against par per round
// from a zero reference on the owner's one symmetric scale, over par above and
// under par below, the owner's round labels and lower-is-better words — and
// the scorecard tiles, the golfer readout and the chooser entry that compose
// it with the chooser's exact identity resolver.
//
// Truth: every figure, date, round label, score, total, result and word is
// the owner's, shown verbatim. This layer never formats a probability, a
// clock or a score, never sums rounds into a total or infers one from a rank,
// never reads a round count as a missed cut or a withdrawal, never elects a
// baseline, a featured golfer, a ceiling or a page, never sorts or ranks, and
// never turns a settlement or a result into a chance or a chart point. A
// golfer with no reported round shows the owner's words, not a zero.
//
// Selections: the history golfer and the scorecard golfer are two separate
// owner selections. Each resolves by exact identity through the chooser's own
// resolver — a missing, foreign, duplicated or withdrawn identity shows the
// owner's unavailable words, never a neighbour — and each role's chooser and
// callbacks carry its role, so acting in one never touches the other.
// Inspecting the history changes nothing in the hero or the scorecard.
//
// Actions: on the page, an action outside the stream calls the owner's
// interaction hook once, then the exact callback with its exact value; a story
// card's own action requests the stream's interaction instead (that request
// is the hold). The chooser, the catalogue and Details content are held the
// same way. Full-size content keeps the exact callbacks with no hold. Without
// a callback there is no control; building or laying out calls nothing.
//
// Layout: phone stacks the hero above the history, then the stories; a regular
// or unspecified width places the hero beside the history while both keep
// their minimum widths; accessibility sizes always stack. Scorecard tiles take
// equal columns, one at accessibility sizes. Every action is at least 44pt.
//
// The host owns the scroll, sheets, navigation, Back/Done, focus, swipe, the
// held selections, held and received frames, pausing, arrivals, ranking and
// every update. This view keeps no state, runs no timer or animation, holds no
// subscription and presents nothing of its own.

// MARK: - Round scores

/// One round's actual score, as the owner reported it.
nonisolated enum GolfRoundScoreValue10868: Equatable {
    /// Strokes relative to par: the raw value behind `text`, geometry only and
    /// never parsed from it. `text` is the owner's figure; `detail` the owner's
    /// strokes words, nil drawing none.
    case reported(relative: Double, text: String, detail: String?)
    /// Not reported, in the owner's words: never zero, a missed cut or a withdrawal.
    case unreported(words: String)
}

/// One round in the owner's order, with the owner's own label.
nonisolated struct GolfRoundScore10868: Equatable {
    let label: String
    let value: GolfRoundScoreValue10868
}

nonisolated struct GolfRoundScoreTick10868: Equatable {
    /// Strokes relative to par.
    let value: Double
    let label: String
}

/// The owner's one symmetric strokes-against-par scale for every round plot.
nonisolated struct GolfRoundScoreScale10868: Equatable {
    /// Bars run from −limit to +limit strokes around the zero reference.
    let limit: Double
    let ticks: [GolfRoundScoreTick10868]
    /// The scale's meaning, including that lower is better.
    let words: String

    var isValid: Bool { limit.isFinite && limit > 0 }
}

nonisolated struct GolfRoundScoreCopy10868: Equatable {
    /// Shown instead of a plot when the owner reports no round.
    let noRounds: String
    /// Shown for a round beyond the scale.
    let offScale: String
}

/// Where one round's bar sits on the shared scale.
nonisolated enum GolfRoundScoreBar10868: Equatable {
    /// The signed fraction of the limit, in −1...1; zero draws the zero mark.
    case value(fraction: Double)
    /// Beyond the scale: an edge mark pointing its way, no fill.
    case offScale(over: Bool)
    /// Not reported, or not placeable: nothing drawn.
    case unplaced
}

nonisolated enum GolfRoundScoreGeometry10868 {
    /// The bar for one round: the raw value as a fraction of the owner's limit.
    static func bar(_ value: GolfRoundScoreValue10868, scale: GolfRoundScoreScale10868) -> GolfRoundScoreBar10868 {
        guard scale.isValid, case .reported(let relative, _, _) = value, relative.isFinite else { return .unplaced }
        guard abs(relative) <= scale.limit else { return .offScale(over: relative > 0) }
        return .value(fraction: relative / scale.limit)
    }

    /// The zero reference: the vertical middle of the plot.
    static func zeroY(in rect: CGRect) -> CGFloat { rect.midY }

    /// A value's height on the scale; nil off the scale or on an invalid one.
    static func y(_ value: Double, scale: GolfRoundScoreScale10868, in rect: CGRect) -> CGFloat? {
        guard scale.isValid, value.isFinite, abs(value) <= scale.limit else { return nil }
        return rect.midY - CGFloat(value / scale.limit) * rect.height / 2
    }

    /// The bar's fill: from the zero line, up for a round over par and down
    /// for one under par, the exact fraction of the half height. Nil for a
    /// zero round, an off-scale round or nothing.
    static func fill(_ bar: GolfRoundScoreBar10868, in rect: CGRect) -> CGRect? {
        guard case .value(let fraction) = bar, fraction != 0, rect.height.isFinite, rect.height > 0 else { return nil }
        let height = CGFloat(abs(fraction)) * rect.height / 2
        let top = fraction > 0 ? rect.midY - height : rect.midY
        return CGRect(x: rect.minX, y: top, width: rect.width, height: height)
    }

    /// Equal columns for the rounds, in the owner's order.
    static func columns(count: Int, in rect: CGRect, spacing: CGFloat) -> [CGRect] {
        guard count > 0, rect.width.isFinite, rect.width > 0, spacing.isFinite, spacing >= 0 else { return [] }
        let width = (rect.width - spacing * CGFloat(count - 1)) / CGFloat(count)
        guard width > 0 else { return [] }
        return (0..<count).map { CGRect(x: rect.minX + CGFloat($0) * (width + spacing), y: rect.minY, width: width, height: rect.height) }
    }
}

/// Actual strokes against par per round, from a zero reference on the owner's
/// one scale. The mini plot sits in a scorecard tile; the full plot adds the
/// scale's tick labels and each round's figure and strokes words.
struct GolfRoundScorePresentation10868: View {
    enum Size: Equatable {
        case mini
        case full
    }

    let rounds: [GolfRoundScore10868]
    let scale: GolfRoundScoreScale10868
    let copy: GolfRoundScoreCopy10868
    /// The owner's whole spoken description of these rounds.
    let summary: String
    var size: Size = .mini

    @ScaledMetric(relativeTo: .caption) private var miniHeight: CGFloat = 56
    @ScaledMetric(relativeTo: .body) private var fullHeight: CGFloat = 160

    /// Whether there is anything to plot: reported rounds on a valid scale.
    static func plots(_ rounds: [GolfRoundScore10868], scale: GolfRoundScoreScale10868) -> Bool {
        scale.isValid && !rounds.isEmpty
    }

    var body: some View {
        Group {
            if Self.plots(rounds, scale: scale) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .top, spacing: 6) {
                        if size == .full { tickLabels }
                        VStack(spacing: 4) {
                            plot.frame(height: size == .full ? fullHeight : miniHeight)
                            HStack(spacing: 4) {
                                ForEach(Array(rounds.enumerated()), id: \.offset) { _, round in
                                    Text(round.label)
                                        .font(size == .full ? .footnote.weight(.semibold) : .caption)
                                        .foregroundStyle(DS.textPrimary)
                                        .frame(maxWidth: .infinity)
                                }
                            }
                        }
                    }
                    if size == .full { roundWords }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(summary)
            } else {
                Text(copy.noRounds)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var plot: some View {
        Canvas { context, canvasSize in
            let rect = CGRect(origin: .zero, size: canvasSize)
            if size == .full {
                for tick in scale.ticks {
                    if let y = GolfRoundScoreGeometry10868.y(tick.value, scale: scale, in: rect) {
                        context.stroke(Path { $0.move(to: CGPoint(x: 0, y: y)); $0.addLine(to: CGPoint(x: rect.maxX, y: y)) },
                                       with: .color(DS.border), lineWidth: 1)
                    }
                }
            }
            let zero = GolfRoundScoreGeometry10868.zeroY(in: rect)
            context.stroke(Path { $0.move(to: CGPoint(x: 0, y: zero)); $0.addLine(to: CGPoint(x: rect.maxX, y: zero)) },
                           with: .color(DS.textSecondary), lineWidth: 1)
            let columns = GolfRoundScoreGeometry10868.columns(count: rounds.count, in: rect, spacing: 4)
            for (round, column) in zip(rounds, columns) {
                let lane = column.insetBy(dx: column.width * 0.2, dy: 0)
                switch GolfRoundScoreGeometry10868.bar(round.value, scale: scale) {
                case .value(let fraction):
                    if let fill = GolfRoundScoreGeometry10868.fill(.value(fraction: fraction), in: lane) {
                        context.fill(Path(roundedRect: fill, cornerRadius: 2), with: .color(DS.blue))
                    } else {
                        context.fill(Path(CGRect(x: lane.minX, y: zero - 1.5, width: lane.width, height: 3)),
                                     with: .color(DS.textPrimary))
                    }
                case .offScale(let over):
                    let edge = over ? rect.minY : rect.maxY
                    var arrow = Path()
                    arrow.move(to: CGPoint(x: lane.midX, y: edge))
                    arrow.addLine(to: CGPoint(x: lane.minX, y: over ? edge + 8 : edge - 8))
                    arrow.addLine(to: CGPoint(x: lane.maxX, y: over ? edge + 8 : edge - 8))
                    arrow.closeSubpath()
                    context.fill(arrow, with: .color(DS.blue))
                case .unplaced:
                    break
                }
            }
        }
        .accessibilityHidden(true)
    }

    private var tickLabels: some View {
        GeometryReader { proxy in
            let rect = CGRect(origin: .zero, size: CGSize(width: proxy.size.width, height: fullHeight))
            ForEach(Array(scale.ticks.enumerated()), id: \.offset) { _, tick in
                if let y = GolfRoundScoreGeometry10868.y(tick.value, scale: scale, in: rect) {
                    Text(tick.label)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize()
                        .position(x: proxy.size.width / 2, y: y)
                }
            }
        }
        .frame(width: 30, height: fullHeight)
        .accessibilityHidden(true)
    }

    private var roundWords: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(rounds.enumerated()), id: \.offset) { _, round in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(round.label).font(.subheadline.weight(.semibold))
                    switch round.value {
                    case .reported(_, let text, let detail):
                        Text(text).font(.subheadline.monospacedDigit())
                        if let detail = FieldEventPageModel10868.readable(detail) {
                            Text(detail).font(.subheadline).foregroundStyle(DS.textSecondary)
                        }
                    case .unreported(let words):
                        Text(words).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                    if case .offScale = GolfRoundScoreGeometry10868.bar(round.value, scale: scale) {
                        Text(copy.offScale).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            Text(scale.words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(DS.textPrimary)
    }
}

// MARK: - Page input

/// One card the page can show full size.
nonisolated enum GolfWinnerArchiveCard10868: String, Hashable, CaseIterable {
    case history
    case scorecard
}

/// Which owner selection a chooser serves.
nonisolated enum GolfWinnerArchiveChooserRole10868: String, Hashable, CaseIterable {
    /// The golfer whose recorded history anchors the page.
    case history
    /// The golfer the scorecard highlights.
    case scorecard
}

/// What the host's container is showing, chosen by the host.
nonisolated enum GolfWinnerArchiveEventPageMode10868: Equatable {
    case page
    case reader(GolfWinnerArchiveCard10868)
    case chooser(GolfWinnerArchiveChooserRole10868)
    case catalogue
    case original
    case about
}

/// A choice, handed back with its role.
nonisolated struct GolfWinnerArchiveChoice10868: Equatable {
    let role: GolfWinnerArchiveChooserRole10868
    let ref: FieldChooserOriginalRef10868
}

/// A chooser control, handed back with its role.
nonisolated struct GolfWinnerArchiveChooserControl10868: Equatable {
    let role: GolfWinnerArchiveChooserRole10868
    let control: FieldChooserControl10868
}

/// One golfer's actual tournament, as the owner reported it.
nonisolated struct GolfWinnerArchiveRoundRecord10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// In the owner's order with its labels; empty when none was reported.
    let rounds: [GolfRoundScore10868]
    /// The owner's separately reported total, or its absence words.
    let total: FieldChooserReading10868
    /// The owner's round availability words; nil draws none.
    let availability: String?
    /// The owner's whole spoken description of the rounds.
    let summary: String
}

nonisolated struct GolfWinnerArchiveScorecardCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// The full card's title.
    let focusedTitle: String
    /// The full card's heading above the tiles; nil draws none.
    let featuredTitle: String?
    let caption: String?
    let legend: String?
    let note: String?
    /// Spoken name of the tiles.
    let tilesLabel: String
    /// Under a tile's pre-event figure.
    let chanceCaption: String
    /// A tile whose identity does not resolve.
    let unavailableWords: String
    let chooseHint: String?
}

nonisolated struct GolfWinnerArchiveScorecardInput10868: Equatable {
    /// The owner's featured golfers, in the owner's order. Never sorted,
    /// capped or deduplicated here.
    let featured: [FieldChooserOriginalRef10868]
    /// The owner's held scorecard golfer — independent of the history golfer.
    let selected: FieldChooserOriginalRef10868?
    let scale: GolfRoundScoreScale10868
    let roundCopy: GolfRoundScoreCopy10868
    let copy: GolfWinnerArchiveScorecardCopy10868
}

nonisolated struct GolfWinnerArchiveReadoutCopy10868: Equatable {
    /// Used when the original carries no result of its own.
    let resultLabel: String
    let resultUnavailable: String
    /// Used when no single round record resolves.
    let scoreLabel: String
    let scoreUnavailable: String
    let roundsUnavailable: String
    let detailsLabel: String
    let detailsHint: String?
    /// A held golfer whose identity does not resolve.
    let unavailableWords: String
}

/// The entry to a role's chooser.
nonisolated struct GolfWinnerArchiveChooserEntryCopy10868: Equatable {
    /// "Golfer in view".
    let caption: String
    /// The action's words; shown only with a callback.
    let action: String
    let hint: String?
}

/// One role's chooser and the owner's hierarchy for it.
nonisolated struct GolfWinnerArchiveChooser10868: Equatable {
    let chooser: FieldChooserInput10868
    /// Nil keeps the chooser's own group list.
    let navigation: GolfPreTournamentChooserNavigation10868?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct GolfWinnerArchiveStory10868: Equatable {
    let cardID: String
    let card: GolfWinnerArchiveCard10868
    var reason: String? = nil
}

nonisolated struct GolfWinnerArchiveCopy10868: Equatable {
    /// Shown in place of a headline that is not at its own final phase.
    let headlineUnavailable: String
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story.
    let storyUnavailable: String
    /// The entry to every original; nil draws none.
    let allPropsLabel: String?
    let historyEntry: GolfWinnerArchiveChooserEntryCopy10868
    let scorecardEntry: GolfWinnerArchiveChooserEntryCopy10868
}

nonisolated struct GolfWinnerArchiveEventPageInput10868: Equatable {
    let copy: GolfWinnerArchiveCopy10868
    /// The compact words above full-size, chooser, catalogue and About content.
    let reader: FieldEventPageReaderHeader10868
    /// The exact scope of every reference below.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original.
    let catalogue: [FieldChooserOriginal10868]
    let headline: FieldHeadlineInput10868
    let history: FieldHistoryInput10868
    /// The owner's held history golfer.
    let historySelection: FieldChooserOriginalRef10868?
    /// Every reported round record, one per golfer, in any order.
    let rounds: [GolfWinnerArchiveRoundRecord10868]
    let scorecard: GolfWinnerArchiveScorecardInput10868
    let readout: GolfWinnerArchiveReadoutCopy10868
    let historyChooser: GolfWinnerArchiveChooser10868?
    let scorecardChooser: GolfWinnerArchiveChooser10868?
    let stream: StoryStreamPresentation10868
    let stories: [GolfWinnerArchiveStory10868]
    let about: FieldEventPageAbout10868?
    /// The owner's full-size plot height; used only when finite, positive and taller.
    var readerPlotHeight: CGFloat? = nil
}

// MARK: - Page model

/// One golfer's readout, all from its own original and its own round record.
nonisolated struct GolfWinnerArchiveReadout10868: Equatable {
    let original: FieldChooserOriginal10868
    /// The original's own pre-event reading, with its own clock.
    let chance: FieldChooserReading10868
    let resultLabel: String
    let resultWords: String
    /// The record's reported total, or the copy's words.
    let score: FieldChooserReading10868
    let availability: String
    /// Nil when no single record resolves.
    let record: GolfWinnerArchiveRoundRecord10868?
}

nonisolated enum GolfWinnerArchiveReadoutResolution10868: Equatable {
    /// No held golfer: nothing drawn.
    case notHeld
    case shown(GolfWinnerArchiveReadout10868)
    /// The held golfer does not resolve: the owner's words.
    case unavailable(String)
}

nonisolated struct GolfWinnerArchiveTile10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// Nil when the reference does not resolve, or repeats in the featured list.
    let readout: GolfWinnerArchiveReadout10868?
    let isSelected: Bool
}

/// One part of a scorecard card, in the order the card mounts them.
nonisolated enum GolfWinnerArchiveScorecardPart10868: Hashable, CaseIterable {
    case eyebrow
    case title
    /// The held scorecard golfer's chooser entry.
    case entry
    /// The held scorecard golfer's readout: its own chance and date, the
    /// market's result, the reported score, availability and Details.
    case readout
    /// The held scorecard golfer's full round plot.
    case rounds
    case featuredTitle
    case caption
    case tiles
    case legend
    case note
}

nonisolated enum GolfWinnerArchiveAccessibilityID10868 {
    static let page = "golfWinnerArchive10868.page"
    static let hero = "golfWinnerArchive10868.hero"
    static let headlineUnavailable = "golfWinnerArchive10868.headline.unavailable"
    static let anchor = "golfWinnerArchive10868.anchor"
    static let stories = "golfWinnerArchive10868.stories"
    static let storyUnavailable = "golfWinnerArchive10868.story.unavailable"
    static let allProps = "golfWinnerArchive10868.allProps"
    static let readerHeader = "golfWinnerArchive10868.readerHeader"
    static let readerAbout = "golfWinnerArchive10868.readerHeader.about"
    static let catalogue = "golfWinnerArchive10868.catalogue"
    static let original = "golfWinnerArchive10868.original"
    static let aboutContent = "golfWinnerArchive10868.aboutContent"
    static let tiles = "golfWinnerArchive10868.scorecard.tiles"
    static func card(_ card: GolfWinnerArchiveCard10868) -> String { "golfWinnerArchive10868.card.\(card.rawValue)" }
    static func chooser(_ role: GolfWinnerArchiveChooserRole10868) -> String { "golfWinnerArchive10868.chooser.\(role.rawValue)" }
    static func entry(_ role: GolfWinnerArchiveChooserRole10868) -> String { "golfWinnerArchive10868.entry.\(role.rawValue)" }
    static func readout(_ role: GolfWinnerArchiveChooserRole10868) -> String { "golfWinnerArchive10868.readout.\(role.rawValue)" }
    static func details(_ role: GolfWinnerArchiveChooserRole10868) -> String { "golfWinnerArchive10868.readout.\(role.rawValue).details" }
    static func tile(_ outcomeID: String) -> String { "golfWinnerArchive10868.scorecard.tile.\(outcomeID)" }
}

/// What the page mounts and draws, resolved once per input.
nonisolated struct GolfWinnerArchiveEventPageModel10868: Equatable {
    let input: GolfWinnerArchiveEventPageInput10868
    /// The chooser's own resolver over the page's canonical catalogue.
    let field: FieldChooserModel10868

    init(_ input: GolfWinnerArchiveEventPageInput10868) {
        self.input = input
        // Only the resolver is read: no chooser section is drawn from it and nothing is selected.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope, intro: nil,
            featured: FieldChooserFeatured10868(title: input.scorecard.copy.title, badge: nil, refs: [],
                                                emptyWords: input.readout.unavailableWords),
            context: nil, more: nil, browse: nil, catalogue: input.catalogue, frame: nil, selected: nil,
            unavailableWords: input.readout.unavailableWords, chooseHint: nil))
    }

    // MARK: Hero and anchor

    /// The headline only at its own final phase — never coerced from another.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == .final ? input.headline : nil
    }

    /// The history the page or full size draws: the owner's input with only
    /// its height and expand control changed. Full size is never shorter, and
    /// only a finite, positive owner height enlarges it.
    func history(reader: Bool) -> FieldHistoryInput10868 {
        let history = input.history
        return VolleyballFieldEventPageModel10868.presentationCopy(
            history,
            plotHeight: reader
                ? RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight)
                : history.plotHeight,
            expand: reader ? nil : history.expand,
            showsKey: history.showsKey)
    }

    // MARK: Golfers

    /// The owner's one round record for this original; several, even identical, are none.
    func record(for ref: FieldChooserOriginalRef10868) -> GolfWinnerArchiveRoundRecord10868? {
        let matches = input.rounds.filter { $0.ref == ref }
        return matches.count == 1 ? matches[0] : nil
    }

    /// One resolved original's readout: its own pre-event reading and result,
    /// and its own record's total and availability — or the copy's words.
    func readout(for original: FieldChooserOriginal10868) -> GolfWinnerArchiveReadout10868 {
        let copy = input.readout
        let record = record(for: original.ref)
        return GolfWinnerArchiveReadout10868(
            original: original,
            chance: FieldOutlookModel10868.beforeReading(original.plan),
            resultLabel: original.result?.title ?? copy.resultLabel,
            resultWords: original.result?.words ?? copy.resultUnavailable,
            score: record?.total ?? FieldChooserReading10868(label: copy.scoreLabel, value: .missing(copy.scoreUnavailable)),
            availability: FieldEventPageModel10868.readable(record?.availability) ?? copy.roundsUnavailable,
            record: record)
    }

    func readout(_ ref: FieldChooserOriginalRef10868?) -> GolfWinnerArchiveReadoutResolution10868 {
        guard let ref else { return .notHeld }
        guard let original = field.resolve(ref).original else { return .unavailable(input.readout.unavailableWords) }
        return .shown(readout(for: original))
    }

    func selection(_ role: GolfWinnerArchiveChooserRole10868) -> FieldChooserOriginalRef10868? {
        switch role {
        case .history: input.historySelection
        case .scorecard: input.scorecard.selected
        }
    }

    func readout(role: GolfWinnerArchiveChooserRole10868) -> GolfWinnerArchiveReadoutResolution10868 {
        readout(selection(role))
    }

    /// The featured tiles in the owner's order. A reference listed more than
    /// once, or not resolving, is an unavailable tile.
    var tiles: [GolfWinnerArchiveTile10868] {
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for ref in input.scorecard.featured { counts[ref, default: 0] += 1 }
        let selected = input.scorecard.selected.flatMap { field.resolve($0).original?.ref }
        return input.scorecard.featured.map { ref in
            let original = counts[ref] == 1 ? field.resolve(ref).original : nil
            return GolfWinnerArchiveTile10868(ref: ref, readout: original.map { readout(for: $0) },
                                             isSelected: original != nil && original?.ref == selected)
        }
    }

    /// The exact original a tile chooses, only with a callback.
    func chooseAction(_ tile: GolfWinnerArchiveTile10868, canChoose: Bool) -> FieldChooserOriginalRef10868? {
        guard canChoose else { return nil }
        return tile.readout?.original.ref
    }

    // MARK: Words

    /// A readout's words in reading order — the same values its view draws.
    static func words(_ readout: GolfWinnerArchiveReadout10868) -> [String] {
        [readout.original.name] + words(readout.chance) + [readout.resultLabel, readout.resultWords]
            + words(readout.score) + [readout.availability]
    }

    static func words(_ reading: FieldChooserReading10868) -> [String] {
        switch reading.value {
        case .recorded(let text, let detail): [reading.label, text] + [FieldEventPageModel10868.readable(detail)].compactMap { $0 }
        case .missing(let words): [reading.label, words]
        }
    }

    /// A readout in VoiceOver words.
    static func spoken(_ readout: GolfWinnerArchiveReadout10868) -> String {
        ([readout.original.name, FieldChooserModel10868.spoken(readout.chance),
          "\(readout.resultLabel): \(readout.resultWords)", FieldChooserModel10868.spoken(readout.score),
          readout.availability] + [readout.record?.summary].compactMap { $0 })
            .filter { FieldEventPageModel10868.readable($0) != nil }
            .joined(separator: ". ")
    }

    /// A tile in VoiceOver words.
    func spoken(_ tile: GolfWinnerArchiveTile10868) -> String {
        tile.readout.map(Self.spoken) ?? input.scorecard.copy.unavailableWords
    }

    /// The chooser entry's golfer: the held golfer's whole name or the owner's words; nil with none held.
    func entryName(_ role: GolfWinnerArchiveChooserRole10868) -> String? {
        switch readout(role: role) {
        case .notHeld: nil
        case .shown(let readout): readout.original.name
        case .unavailable(let words): words
        }
    }

    func entryCopy(_ role: GolfWinnerArchiveChooserRole10868) -> GolfWinnerArchiveChooserEntryCopy10868 {
        role == .history ? input.copy.historyEntry : input.copy.scorecardEntry
    }

    // MARK: Stories

    /// The owner's link a stream card id names: exactly one link, to the
    /// scorecard. Otherwise nothing — never a neighbour.
    func story(_ cardID: String) -> GolfWinnerArchiveStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card == .scorecard else { return nil }
        return link
    }

    // MARK: Choosers

    func chooser(_ role: GolfWinnerArchiveChooserRole10868) -> GolfWinnerArchiveChooser10868? {
        role == .history ? input.historyChooser : input.scorecardChooser
    }

    /// The role's hierarchy on its own full chooser, while both exist.
    func chooserNavigation(_ role: GolfWinnerArchiveChooserRole10868) -> GolfPreTournamentChooserNavigationModel10868? {
        guard let chooser = chooser(role), let navigation = chooser.navigation else { return nil }
        return GolfPreTournamentChooserNavigationModel10868(navigation: navigation, chooser: chooser.chooser)
    }

    /// The chooser the shared leaf draws for a role — with a hierarchy, the
    /// pre-tournament golf page's rule: only the groups whose id is the
    /// selected group's or one of the chooser's own control ids, so selection,
    /// missing or duplicated groups and id collisions resolve exactly as from
    /// the full list and no wall of group buttons is drawn.
    func chooserPresentation(_ role: GolfWinnerArchiveChooserRole10868) -> FieldChooserInput10868? {
        guard let entry = chooser(role) else { return nil }
        let chooser = entry.chooser
        guard entry.navigation != nil, let browse = chooser.browse else { return chooser }
        let kept = Set([browse.selectedGroupID, browse.id, chooser.more?.id].compactMap { $0 })
        let shown = FieldChooserBrowse10868(
            id: browse.id, title: browse.title, expanded: browse.expanded, note: browse.note,
            groupsLabel: browse.groupsLabel, groups: browse.groups.filter { kept.contains($0.id) },
            selectedGroupID: browse.selectedGroupID, noGroupWords: browse.noGroupWords,
            groupUnavailableWords: browse.groupUnavailableWords, emptyGroupWords: browse.emptyGroupWords)
        return FieldChooserInput10868(
            scope: chooser.scope, intro: chooser.intro, featured: chooser.featured, context: chooser.context,
            more: chooser.more, browse: shown, catalogue: chooser.catalogue, frame: chooser.frame,
            selected: chooser.selected, unavailableWords: chooser.unavailableWords, chooseHint: chooser.chooseHint)
    }

    // MARK: About and entries

    var about: FieldEventPageAbout10868? {
        guard let about = input.about,
              FieldEventPageModel10868.readable(about.title) != nil
                || about.paragraphs.contains(where: { FieldEventPageModel10868.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && FieldEventPageModel10868.readable(input.headline.copy.aboutLabel) != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && FieldEventPageModel10868.readable(input.copy.allPropsLabel) != nil
    }
}

// MARK: - Page view

struct GolfWinnerArchiveEventPagePresentation10868: View {
    typealias Model = GolfWinnerArchiveEventPageModel10868
    typealias Role = GolfWinnerArchiveChooserRole10868
    typealias ID = GolfWinnerArchiveAccessibilityID10868
    typealias Stream = StoryStreamPresentation10868

    let input: GolfWinnerArchiveEventPageInput10868
    var mode: GolfWinnerArchiveEventPageMode10868 = .page
    /// Every original and the held original's Details; nil: neither.
    var originals: FieldEventPageOriginals10868? = nil
    var onAbout: (() -> Void)? = nil
    /// The hero golfer's exact open.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the host's chooser for one role.
    var onOpenChooser: ((Role) -> Void)? = nil
    /// A golfer chosen for one role, from that role's chooser or a scorecard tile.
    var onChoose: ((GolfWinnerArchiveChoice10868) -> Void)? = nil
    var onChooserControl: ((GolfWinnerArchiveChooserControl10868) -> Void)? = nil
    /// A readout's exact original, for the host's Details.
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    var onAllProps: (() -> Void)? = nil
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// Called once before a page, chooser, catalogue or Details action reaches its owner.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var tileMinWidth: CGFloat = 150

    static let minimumTarget: CGFloat = 44

    var model: Model { Model(input) }

    /// Where an action is reached: on the page outside the stream (held by the
    /// hook), inside a stream card (the stream's interaction is the hold), or
    /// in full-size content (exact).
    enum Place {
        case page
        case stream(StoryStreamCardActivation10868)
        case reader
    }

    /// An action as `place` reaches it. No callback: no action.
    func placed<Value>(_ action: ((Value) -> Void)?, at place: Place) -> ((Value) -> Void)? {
        switch place {
        case .page: return FieldEventPagePresentation10868.held(action, by: onInteraction)
        case .stream(let activation): return FieldEventPagePresentation10868.relay(action, through: activation)
        case .reader: return action
        }
    }

    // MARK: Actions — each exactly what its control runs

    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0,
                                                onAbout: FieldEventPagePresentation10868.heldAction(aboutOpener(), by: onInteraction),
                                                onOpen: placed(onHeadlineOpen, at: .page))
        }
    }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let place: Place = reader ? .reader : .page
        return FieldProbabilityHistoryPresentation10868(
            input: model.history(reader: reader),
            onAction: placed(onHistoryAction, at: place),
            onInspectionChoice: placed(onHistoryInspectionChoice, at: place),
            onPlotPosition: placed(onHistoryPlotPosition, at: place))
    }

    /// The chooser entry for a role, while a callback exists.
    func entryAction(_ role: Role, at place: Place) -> (() -> Void)? {
        guard let open = placed(onOpenChooser, at: place) else { return nil }
        return { open(role) }
    }

    /// A readout's Details, for its own resolved original only.
    func detailsAction(_ role: Role, at place: Place) -> (() -> Void)? {
        guard case .shown(let readout) = model.readout(role: role),
              let open = placed(onOpenOriginal, at: place) else { return nil }
        let ref = readout.original.ref
        return { open(ref) }
    }

    /// A scorecard tile's exact choice for the scorecard role.
    func tileAction(_ tile: GolfWinnerArchiveTile10868, at place: Place) -> (() -> Void)? {
        guard let ref = model.chooseAction(tile, canChoose: onChoose != nil),
              let choose = placed(onChoose, at: place) else { return nil }
        return { choose(GolfWinnerArchiveChoice10868(role: .scorecard, ref: ref)) }
    }

    /// The shared chooser for a role, with that role's held callbacks.
    func chooserContent(_ role: Role) -> FieldContenderChooserPresentation10868? {
        let choose: ((FieldChooserOriginalRef10868) -> Void)? = onChoose.map { choose in
            { ref in choose(GolfWinnerArchiveChoice10868(role: role, ref: ref)) }
        }
        return model.chooserPresentation(role).map {
            FieldContenderChooserPresentation10868(input: $0, onChoose: placed(choose, at: .page),
                                                   onControl: placed(roleControl(role), at: .page))
        }
    }

    func chooserNavigationContent(_ role: Role, _ part: GolfPreTournamentChooserNavigationPart10868) -> GolfPreTournamentChooserNavigationPresentation10868? {
        model.chooserNavigation(role).map {
            GolfPreTournamentChooserNavigationPresentation10868(model: $0, part: part,
                                                                 onControl: placed(roleControl(role), at: .page))
        }
    }

    private func roleControl(_ role: Role) -> ((FieldChooserControl10868) -> Void)? {
        onChooserControl.map { send in
            { control in send(GolfWinnerArchiveChooserControl10868(role: role, control: control)) }
        }
    }

    func aboutContent() -> FieldEventPageAboutContent10868? {
        model.about.map { FieldEventPageAboutContent10868(about: $0) }
    }

    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: placed(onOriginalSelect, at: .page))
        }
    }

    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                                          recorded: $0.recorded, onHistory: placed(onOriginalHistory, at: .page))
        }
    }

    func openPageAbout() {
        FieldEventPagePresentation10868.heldAction(aboutOpener(), by: onInteraction)?()
    }

    /// Full-size content's About: the exact callback.
    func openAbout() {
        aboutOpener()?()
    }

    func allPropsAction() -> (() -> Void)? {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return nil }
        return FieldEventPagePresentation10868.heldAction(onAllProps, by: onInteraction)
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .chooser(let role): chooserMode(role)
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            stories
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.page)
    }

    private var hero: some View {
        let arrangements = FieldEventPageModel10868.arrangements(sizeClass: sizeClass,
                                                                 accessibilitySize: typeSize.isAccessibilitySize)
        return Group {
            if arrangements == [.stacked] {
                heroStacked
            } else {
                ViewThatFits(in: .horizontal) {
                    heroSideBySide
                    heroStacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            headlineCard
            anchorCard
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            headlineCard
                .frame(minWidth: headlineMinWidth, maxWidth: headlineMaxWidth, alignment: .topLeading)
            anchorCard
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    private var headlineCard: some View {
        Group {
            if let headline = headlineContent() {
                headline
            } else {
                Text(input.copy.headlineUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(ID.headlineUnavailable)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(GolfWinnerArchiveCardSurface10868())
    }

    private var anchorCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            entry(.history, at: .page)
            historyContent(reader: false)
            readoutView(.history, at: .page)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(GolfWinnerArchiveCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if let action = allPropsAction(), let label = input.copy.allPropsLabel {
                Button(action: action) {
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
                    .frame(minHeight: Self.minimumTarget)
                    .modifier(GolfWinnerArchiveCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(ID.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(ID.stories)
    }

    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = FieldEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                scorecardContent(focused: false, at: .stream(activation))
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(GolfWinnerArchiveCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(GolfWinnerArchiveCardSurface10868())
                .accessibilityIdentifier(ID.storyUnavailable)
        }
    }

    // MARK: Scorecard

    /// The parts a scorecard card mounts, in order — the body draws exactly
    /// these. The compact card: the tiles, then the held scorecard golfer's
    /// chooser entry and readout; the full card first spotlights that golfer
    /// with the same readout and the full round plot, then the tiles.
    static func scorecardParts(focused: Bool) -> [GolfWinnerArchiveScorecardPart10868] {
        focused
            ? [.eyebrow, .title, .entry, .readout, .rounds, .featuredTitle, .caption, .tiles, .legend, .note]
            : [.eyebrow, .title, .caption, .tiles, .legend, .entry, .readout, .note]
    }

    /// Every word a scorecard card draws, part by part — the same values the
    /// body draws, an entry's action words only while it acts.
    func scorecardWords(focused: Bool, at place: Place) -> [String] {
        let copy = input.scorecard.copy
        return Self.scorecardParts(focused: focused).flatMap { part -> [String] in
            switch part {
            case .eyebrow: return [FieldEventPageModel10868.readable(copy.eyebrow)].compactMap { $0 }
            case .title: return [focused ? copy.focusedTitle : copy.title]
            case .entry:
                guard let name = model.entryName(.scorecard) else { return [] }
                let entry = model.entryCopy(.scorecard)
                return [entry.caption, name] + (entryAction(.scorecard, at: place) == nil ? [] : [entry.action])
            case .readout:
                switch model.readout(role: .scorecard) {
                case .notHeld: return []
                case .unavailable(let words): return [words]
                case .shown(let readout):
                    return Model.words(readout) + (detailsAction(.scorecard, at: place) == nil ? [] : [input.readout.detailsLabel])
                }
            case .rounds:
                guard case .shown(let readout) = model.readout(role: .scorecard) else { return [] }
                return GolfRoundScorePresentation10868.plots(readout.record?.rounds ?? [], scale: input.scorecard.scale)
                    ? [readout.record?.summary ?? ""] : [input.scorecard.roundCopy.noRounds]
            case .featuredTitle: return [FieldEventPageModel10868.readable(copy.featuredTitle)].compactMap { $0 }
            case .caption: return [FieldEventPageModel10868.readable(copy.caption)].compactMap { $0 }
            case .tiles: return model.tiles.map { model.spoken($0) }
            case .legend: return [FieldEventPageModel10868.readable(copy.legend)].compactMap { $0 }
            case .note: return [FieldEventPageModel10868.readable(copy.note)].compactMap { $0 }
            }
        }
    }

    private func scorecardContent(focused: Bool, at place: Place) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Self.scorecardParts(focused: focused), id: \.self) { part in
                scorecardPart(part, focused: focused, at: place)
            }
        }
    }

    @ViewBuilder private func scorecardPart(_ part: GolfWinnerArchiveScorecardPart10868, focused: Bool,
                                            at place: Place) -> some View {
        let copy = input.scorecard.copy
        switch part {
        case .eyebrow:
            if let eyebrow = FieldEventPageModel10868.readable(copy.eyebrow) {
                Text(eyebrow)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
            }
        case .title:
            Text(focused ? copy.focusedTitle : copy.title)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
        case .entry:
            entry(.scorecard, at: place)
        case .readout:
            readoutView(.scorecard, at: place)
        case .rounds:
            if case .shown(let readout) = model.readout(role: .scorecard) {
                GolfRoundScorePresentation10868(
                    rounds: readout.record?.rounds ?? [], scale: input.scorecard.scale,
                    copy: input.scorecard.roundCopy, summary: readout.record?.summary ?? "", size: .full)
            }
        case .featuredTitle:
            if let title = FieldEventPageModel10868.readable(copy.featuredTitle) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
        case .caption:
            if let caption = FieldEventPageModel10868.readable(copy.caption) {
                Text(caption)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .tiles:
            QualificationEventPageGrid10868(minimumCardWidth: tileMinWidth, spacing: 8,
                                            accessibilitySize: typeSize.isAccessibilitySize) {
                ForEach(Array(model.tiles.enumerated()), id: \.offset) { _, tile in
                    self.tile(tile, at: place)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(copy.tilesLabel)
            .accessibilityIdentifier(ID.tiles)
        case .legend:
            if let legend = FieldEventPageModel10868.readable(copy.legend) {
                Text(legend)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .note:
            if let note = FieldEventPageModel10868.readable(copy.note) {
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// One featured golfer: name, pre-event figure, mini round plot, the
    /// separately reported total and the market's own result.
    @ViewBuilder private func tile(_ tile: GolfWinnerArchiveTile10868, at place: Place) -> some View {
        let face = tileFace(tile)
        if let action = tileAction(tile, at: place) {
            Button(action: action) { face }
                .buttonStyle(.plain)
                .accessibilityLabel(model.spoken(tile))
                .accessibilityHint(input.scorecard.copy.chooseHint ?? "")
                .accessibilityAddTraits(tile.isSelected ? .isSelected : [])
                .accessibilityIdentifier(ID.tile(tile.ref.outcomeID))
        } else {
            face
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.spoken(tile))
                .accessibilityAddTraits(tile.isSelected ? .isSelected : [])
                .accessibilityIdentifier(ID.tile(tile.ref.outcomeID))
        }
    }

    private func tileFace(_ tile: GolfWinnerArchiveTile10868) -> some View {
        let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
        return VStack(alignment: .leading, spacing: 6) {
            if let readout = tile.readout {
                Text(readout.original.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Image(systemName: "circle")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.blue)
                        .accessibilityHidden(true)
                    switch readout.chance.value {
                    case .recorded(let text, _):
                        Text(text).font(.title3.weight(.bold).monospacedDigit()).foregroundStyle(DS.textPrimary)
                    case .missing(let words):
                        Text(words).font(.subheadline).foregroundStyle(DS.textPrimary)
                    }
                    Text(input.scorecard.copy.chanceCaption)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                }
                .fixedSize(horizontal: false, vertical: true)
                GolfRoundScorePresentation10868(
                    rounds: readout.record?.rounds ?? [], scale: input.scorecard.scale,
                    copy: input.scorecard.roundCopy, summary: readout.record?.summary ?? "", size: .mini)
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    scoreText(readout.score)
                    Text(readout.resultWords)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(input.scorecard.copy.unavailableWords)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: Self.minimumTarget, maxHeight: .infinity, alignment: .topLeading)
        .background(shape.fill(tile.isSelected ? DS.cardBg : DS.surface))
        .overlay(shape.strokeBorder(tile.isSelected ? DS.blue : DS.border, lineWidth: tile.isSelected ? 2 : 1))
        .contentShape(shape)
    }

    @ViewBuilder private func scoreText(_ reading: FieldChooserReading10868) -> some View {
        switch reading.value {
        case .recorded(let text, _):
            Text(text).font(.headline.monospacedDigit()).foregroundStyle(DS.textPrimary)
        case .missing(let words):
            Text(words).font(.subheadline).foregroundStyle(DS.textPrimary)
        }
    }

    // MARK: Readout and chooser entry

    /// A role's held golfer: its own readings, result, score and availability,
    /// and Details while a callback exists.
    @ViewBuilder private func readoutView(_ role: Role, at place: Place) -> some View {
        switch model.readout(role: role) {
        case .notHeld:
            EmptyView()
        case .unavailable(let words):
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(ID.readout(role))
        case .shown(let readout):
            VStack(alignment: .leading, spacing: 10) {
                Text(readout.original.name)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                let values = Group {
                    value(readout.chance)
                    words(label: readout.resultLabel, words: readout.resultWords)
                    value(readout.score)
                }
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 10) { values }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 16) { values }
                        VStack(alignment: .leading, spacing: 10) { values }
                    }
                }
                Text(readout.availability)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let action = detailsAction(role, at: place) {
                    Button(action: action) {
                        HStack(spacing: 6) {
                            Text(input.readout.detailsLabel)
                                .font(.body.weight(.semibold))
                                .fixedSize(horizontal: false, vertical: true)
                            Image(systemName: "chevron.right").accessibilityHidden(true)
                        }
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: Self.minimumTarget)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint(input.readout.detailsHint ?? "")
                    .accessibilityIdentifier(ID.details(role))
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.readout(role))
        }
    }

    /// A reading: the owner's figure with its own clock line, or its own words.
    private func value(_ reading: FieldChooserReading10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(reading.label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            switch reading.value {
            case .recorded(let text, let detail):
                Text(text)
                    .font(.title2.weight(.bold).monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                if let detail = FieldEventPageModel10868.readable(detail) {
                    Text(detail).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            case .missing(let words):
                Text(words)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }

    /// The market's own result: words, never a figure.
    private func words(label: String, words: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            Text(words)
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }

    /// The role's chooser entry: the held golfer in view and, with a callback, the action.
    @ViewBuilder private func entry(_ role: Role, at place: Place) -> some View {
        let copy = model.entryCopy(role)
        if let name = model.entryName(role) {
            let face = HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(copy.caption).font(.subheadline).foregroundStyle(DS.textSecondary)
                    Text(name).font(.body.weight(.semibold)).foregroundStyle(DS.textPrimary)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if entryAction(role, at: place) != nil {
                    HStack(spacing: 4) {
                        Text(copy.action).font(.subheadline.weight(.semibold))
                        Image(systemName: "chevron.down").accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                }
            }
            .padding(.horizontal, 12)
            .frame(minHeight: Self.minimumTarget)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            if let action = entryAction(role, at: place) {
                Button(action: action) { face.contentShape(Rectangle()) }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(copy.caption): \(name). \(copy.action)")
                    .accessibilityHint(copy.hint ?? "")
                    .accessibilityIdentifier(ID.entry(role))
            } else {
                face
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier(ID.entry(role))
            }
        }
    }

    // MARK: Full size

    @ViewBuilder private func reader(_ card: GolfWinnerArchiveCard10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            switch card {
            case .history:
                entry(.history, at: .reader)
                historyContent(reader: true)
                readoutView(.history, at: .reader)
            case .scorecard:
                scorecardContent(focused: true, at: .reader)
            }
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = FieldEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if case .reader = mode, aboutOpener() != nil {
                Button(action: openAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: Self.minimumTarget, minHeight: Self.minimumTarget)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(ID.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.readerHeader)
    }

    // MARK: Chooser, every original, Details and About

    @ViewBuilder private func chooserMode(_ role: Role) -> some View {
        if let chooser = chooserContent(role) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if let controls = chooserNavigationContent(role, .controls) {
                    controls
                }
                chooser
                if let pages = chooserNavigationContent(role, .pages) {
                    pages
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.chooser(role))
        }
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(ID.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.aboutContent)
        }
    }
}

/// The page's white card on the page surface.
private struct GolfWinnerArchiveCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
