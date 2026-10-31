import SwiftUI

// #10868 — the squash match screen (`squash-match`): one native presentation
// composed from the accepted shared leaves, plus one compact actual-game leaf
// defined here. The two players' independently traded chances lead at equal
// prominence, each with its own dated meaning. A fan sees, in this order: the
// match headline (the owner's eyebrow, title and About entry; each named
// player's readings for the phase — before play the owner's early recorded
// trade or its absence words, during play that reading beside a recorded
// chance, after the match the owner's pre-match reminder or its "comparison
// unavailable" words beside the separately reported result — and the owner's
// match state), the owner's expectation caution in readable type, and the tall
// shared probability history with its source entry; then, during and after
// play, the actual games — paired point bars per game on one owner point
// scale, each game's reported winner and cumulative games, the separate final
// match score, the total points and the reported duration, all labelled as
// actual facts and never as chances; then the two original winner markets with
// the held original's Details and the "All props" entry. The history and the
// games open as full-size content made of the same Views; "All props", the held
// original's Details, the match About, the source details and the match report
// are further content modes.
//
// Presentation only, composed from the approved `SquashMatch.tsx`,
// `SquashChanceReadout.tsx`, `SquashHistoryPlot.tsx` and `squashMatch.css`,
// with the readable native composition (`SquashViews.swift`) as a visual and
// semantic reference only. The reference's fixture loader and evidence helper
// (`squashMatchEvidence.ts`) — ticker and event allowlists, admission, scalar
// parsing, score validation, baseline election, the compressed clock, exact
// minute lookup — and `ChanceText`, `ArchiveMatchClock`, its "Every game. Two
// points apart." rule, its phase picker, reader card and session state, "Aa
// Larger", sheets, dialogs and focus restoration are NOT ported. The leaves are
// the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named players;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor: the owner's
//     runs, explicit breaks with their marks, axis captions, readouts bound to
//     their exact observations, windows, inspection and previous/next;
//   • `SquashGameScoresPresentation10868` (below) — the actual games. No
//     existing leaf draws actual per-game points for two players, and a
//     probability or threshold card is never bent into points;
//   • `OriginalMarketChooserView9483` — the two winner markets and the held
//     original's Details, on the page;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the held original's Details as content modes.
//
// The reference ranks no story stream (its full-size reader holds only the
// history and the games), so no stream is mounted. Nothing else is drawn here
// beyond arrangement, card surfaces, the owner's notice, caution, entry and
// text words and the compact reader heading.
//
// The page's phase is the owner's explicit `SquashEventPagePhase10868`, never
// read from a schedule, a market close, a settlement, a quote, a game count or
// a result. A leaf is mounted only when its own phase is the page's: a headline
// from another phase shows the owner's unavailable words, and the games are
// mounted during and after play only — never before, so no later game score,
// total, duration or result reaches the page or its speech, whatever the owner
// supplies. Before play the headline reads only each player's before reading.
// The two players' chances are independent: this layer never complements,
// normalizes or sums them, treats a missing value as zero, elects a baseline,
// turns a sparse early trade into a pre-match expectation, turns the result or
// a settlement into a 0/100 quote or a history point, reads a contract's grade
// from the match, or guesses a start, a game end or a link between a game score
// and a probability jump. The probability inspection and the actual match
// context are separate inputs: inspecting an earlier chance never changes a
// game, a total or the duration, and the full-size games ignore the inspection.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a result, a window, a break or a word. A future
// owner with a qualified pre-match baseline supplies it as the headline's and
// the history's before readings, where it stays prominent and apart from the
// recorded or inspected chances and from the reported result.
//
// The owner may pass an interaction hook, so it can hold its received frame
// before an action lands. On the page — the headline's open and About, the
// anchor history's actions, inspection choices and plot taps, the source
// entry, the games' expand and report, an original choice and the All props
// entry — and in the catalogue and Details content — an original's selection
// and a Details history intent — the action calls that hook once and then the
// owner's exact callback with its exact value. Without a callback there is no
// control and no hook call; without a hook every callback is the owner's own.
// Building or reading the view calls nothing. Full-size history and games, and
// the About, source and report content, keep the exact callbacks: their host
// already holds the frame while they are open.
//
// The full-size history is the same history input in its expanded layout,
// without its expand control, at the owner's reader plot height when supplied;
// every series, run, break, selection, readout, window, inspection and control
// is unchanged. The full-size games are the same games input without the
// expand control.
//
// Phone stacks the headline above the history, then the games and the
// originals. A regular or unspecified size class (a Mac window) places the
// headline beside the history while both keep their minimum widths, otherwise
// it stacks too; accessibility sizes always stack.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing to
// and from every content mode, the held original, the held inspection and
// window, the held/received frame, live subscriptions and every genuine update.
// This view keeps no state, runs no timer or animation, holds no subscription
// and presents no sheet or navigation of its own.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one match snapshot, the phase; the two players' canonical original
// membership and their dated readings (an unqualified early trade labelled as
// such, a qualified baseline only when one exists); the history's runs, the
// compressed coordinate with its explicit breaks and axis words; the actual
// game rows with each reported winner, cumulative games, total points and
// reported duration from an independent score report; the original catalogue
// with each original's own result; the About, source and report words with
// any link; and maps every callback to its existing controls. No production
// squash score channel exists in the app's models at this base.

/// The owner's explicit phase for the whole screen.
nonisolated enum SquashEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// What the host's container is showing, chosen by the host.
nonisolated enum SquashEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// The history's full-size content.
    case fullHistory
    /// The actual games' full-size content.
    case fullGames
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match About.
    case about
    /// The owner's history and source details.
    case source
    /// The owner's match report.
    case report
}

nonisolated enum SquashEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Actual games

/// One player of the actual games, with a stable tint and a non-colour key.
nonisolated struct SquashGamePlayer10868: Equatable {
    /// The owner's opaque, stable identity; a game's winner names it.
    let id: String
    /// The owner's name, shown whole and spoken.
    let name: String
    /// The same shape the history draws for this player.
    let shape: FieldHistoryShape10868
    let tint: Color
}

/// One player's actual points in one game.
nonisolated enum SquashGamePoints10868: Equatable {
    /// The owner's figure ("11") and the number that places the bar.
    case reported(text: String, value: Double)
    /// Not reported — the owner's words, never zero and never a bar.
    case unknown(String)

    var figure: String? {
        if case .reported(let text, _) = self { return text }
        return nil
    }

    var value: Double? {
        if case .reported(_, let value) = self { return value }
        return nil
    }

    var unknownWords: String? {
        if case .unknown(let words) = self { return words }
        return nil
    }
}

/// One actual game, in the owner's order.
nonisolated struct SquashGameRow10868: Equatable {
    /// The owner's opaque, stable identity. Empty is no identity.
    let id: String
    /// "Game 1".
    let label: String
    /// The first player's points.
    let first: SquashGamePoints10868
    /// The second player's points.
    let second: SquashGamePoints10868
    /// The owner's reported game winner, by player id. Nil, or an id naming
    /// no single player, draws no winner mark. Never read from the points.
    let winnerID: String?
    /// The owner's winner words for this game, or its absence words.
    let winnerWords: String
    /// The owner's cumulative games after this game ("1–0"); nil draws none.
    let games: String?
    /// The spoken form ("Games 1 to 0"); nil speaks `games`.
    let gamesSpoken: String?
}

/// One owner-labelled actual fact — a figure and the owner's label saying
/// what it counts and that it is not a win probability. Never a chance.
nonisolated struct SquashGameFact10868: Equatable {
    let value: String
    let label: String
    let spoken: String
}

/// The owner's one zero-based point scale every game's bars share.
nonisolated struct SquashGameScale10868: Equatable {
    /// The top of every bar, in points. Never a universal constant.
    let ceiling: Double
    /// The scale in words ("Bars share one 0–12 point scale"); nil draws none.
    let words: String?

    var isValid: Bool { ceiling.isFinite && ceiling > 0 }
}

nonisolated struct SquashGameScoresInput10868: Equatable {
    /// The owner's explicit phase. Before play nothing is drawn or spoken.
    let phase: SquashEventPagePhase10868
    /// "How the match was won"; nil draws none.
    let eyebrow: String?
    /// The owner's heading, never computed here.
    let title: String
    /// "Actual points".
    let keyLabel: String
    let first: SquashGamePlayer10868
    let second: SquashGamePlayer10868
    /// Every game the owner admitted for the phase, in its order — never
    /// sorted, filtered, capped or completed here.
    let rows: [SquashGameRow10868]
    let scale: SquashGameScale10868
    /// The owner's words when a reported figure cannot be placed on the scale.
    let notDrawn: String
    /// Shown when no game is admitted ("No games reported yet").
    let empty: String
    /// The final match score, apart from each game's cumulative games. At the
    /// final only.
    let match: SquashGameFact10868?
    /// The total points (during play the owner's running total). During and
    /// after play.
    let totalPoints: SquashGameFact10868?
    /// The reported match duration. At the final only.
    let duration: SquashGameFact10868?
    /// Verbatim lines, during and after play.
    let notes: [String]
    /// "Match report"; drawn only with the host's callback.
    let reportLabel: String?
    /// The expand control's spoken name; drawn only with the host's callback.
    let expandLabel: String

    // MARK: Phase gating

    var isShown: Bool { phase != .before }

    var visibleRows: [SquashGameRow10868] { isShown ? rows : [] }

    var visibleMatch: SquashGameFact10868? { phase == .final ? match : nil }

    var visibleTotalPoints: SquashGameFact10868? { isShown ? totalPoints : nil }

    var visibleDuration: SquashGameFact10868? { phase == .final ? duration : nil }

    var visibleNotes: [String] { isShown ? notes : [] }

    var visibleScaleWords: String? { isShown ? SquashEventPageModel10868.readable(scale.words) : nil }

    // MARK: Identity

    /// Two nonempty, distinct player ids; otherwise no game names a winner.
    var hasDistinctPlayers: Bool {
        SquashEventPageModel10868.readable(first.id) != nil && SquashEventPageModel10868.readable(second.id) != nil
            && first.id != second.id
    }

    /// The owner's reported winner of a game: the one player its id names.
    func winner(_ row: SquashGameRow10868) -> SquashGamePlayer10868? {
        guard isShown, hasDistinctPlayers, let id = row.winnerID else { return nil }
        if id == first.id { return first }
        if id == second.id { return second }
        return nil
    }

    // MARK: Geometry

    /// A reported figure's bar height as a fraction of the shared scale. Nil
    /// for unknown points, an invalid scale, or a value that is negative,
    /// non-finite or beyond the ceiling — never clamped.
    func barFraction(_ points: SquashGamePoints10868) -> Double? {
        guard isShown, scale.isValid, let value = points.value, value.isFinite, value >= 0, value <= scale.ceiling else {
            return nil
        }
        return value / scale.ceiling
    }

    /// A reported figure that cannot be placed keeps its figure and says so.
    func showsNotDrawn(_ points: SquashGamePoints10868) -> Bool {
        guard isShown, points.value != nil else { return false }
        return barFraction(points) == nil
    }

    func rowShowsNotDrawn(_ row: SquashGameRow10868) -> Bool {
        showsNotDrawn(row.first) || showsNotDrawn(row.second)
    }

    /// A unique row keeps its id-based identifier; an empty or repeated id
    /// adds its position so two tiles never share one.
    func accessibilityID(at index: Int) -> String? {
        guard visibleRows.indices.contains(index) else { return nil }
        let id = visibleRows[index].id
        let base = SquashGameScoresAccessibilityID10868.game(id)
        let repeated = visibleRows.filter { $0.id == id }.count > 1
        return id.isEmpty || repeated ? "\(base).\(index)" : base
    }

    // MARK: VoiceOver

    var accessibilityHeader: String? {
        guard isShown else { return nil }
        return Self.joined([eyebrow ?? "", title])
    }

    /// The key: the points label and both players' names.
    var accessibilityKey: String? {
        guard isShown else { return nil }
        return Self.joined([keyLabel, first.name, second.name])
    }

    /// One game in reading order: each player's points or words, a figure
    /// that could not be placed, the reported winner, then the cumulative
    /// games. Empty before play.
    func accessibilityRow(_ row: SquashGameRow10868) -> String {
        guard isShown else { return "" }
        var parts = [Self.spoken(row.first, player: first), Self.spoken(row.second, player: second)]
        if rowShowsNotDrawn(row) { parts.append(notDrawn) }
        parts.append(row.winnerWords)
        if let games = row.gamesSpoken ?? row.games { parts.append(games) }
        return Self.joined(parts)
    }

    private static func spoken(_ points: SquashGamePoints10868, player: SquashGamePlayer10868) -> String {
        switch points {
        case .reported(let text, _): "\(player.name) \(text)"
        case .unknown(let words): "\(player.name): \(words)"
        }
    }

    /// Owner words joined in order; an empty line adds no pause.
    static func joined(_ parts: [String]) -> String {
        parts.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.joined(separator: ". ")
    }
}

nonisolated enum SquashGameScoresGeometry10868 {
    /// A bar's height for a placed fraction; nil for a fraction or height
    /// that cannot be drawn.
    static func barHeight(_ fraction: Double, maxHeight: CGFloat) -> CGFloat? {
        guard fraction.isFinite, fraction >= 0, fraction <= 1, maxHeight.isFinite, maxHeight > 0 else { return nil }
        return maxHeight * CGFloat(fraction)
    }

    /// Game tiles per line: as many as fit while every tile keeps its whole
    /// measured width, at most one line of every game; accessibility sizes at
    /// most two. At least one. Nothing shrinks or truncates.
    static func columns(
        count: Int,
        available: CGFloat?,
        spacing: CGFloat,
        accessibilitySize: Bool,
        measure: (Int, CGFloat?) -> CGFloat
    ) -> Int {
        guard count > 1 else { return 1 }
        let cap = accessibilitySize ? min(2, count) : count
        guard let available, available.isFinite, available > 0 else { return cap }
        var columns = cap
        while columns > 1 {
            let width = (available - spacing * CGFloat(columns - 1)) / CGFloat(columns)
            if width > 0, (0..<count).allSatisfy({ measure($0, width) <= width + 0.5 }) {
                return columns
            }
            columns -= 1
        }
        return 1
    }

    /// Tile positions per line, in the owner's order; nothing is dropped.
    static func lines(count: Int, columns: Int) -> [[Int]] {
        guard count > 0 else { return [] }
        let step = max(1, columns)
        return stride(from: 0, to: count, by: step).map { start in
            Array(start..<min(start + step, count))
        }
    }

    /// The SF Symbol for a player's non-colour key.
    static func symbol(_ shape: FieldHistoryShape10868) -> String {
        switch shape {
        case .circle: "circle.fill"
        case .square: "square.fill"
        case .diamond: "diamond.fill"
        case .triangle: "triangle.fill"
        }
    }
}

/// The game tiles in lines of as many as fit whole; tiles in a line share
/// its height and grow with the text.
struct SquashGameTileGrid10868: Layout {
    var spacing: CGFloat
    var accessibilitySize: Bool

    private func columnCount(_ width: CGFloat?, _ subviews: Subviews) -> Int {
        SquashGameScoresGeometry10868.columns(
            count: subviews.count,
            available: width,
            spacing: spacing,
            accessibilitySize: accessibilitySize,
            measure: { index, proposal in
                subviews[index].sizeThatFits(ProposedViewSize(width: proposal, height: nil)).width
            }
        )
    }

    private func columnWidth(_ total: CGFloat, columns: Int) -> CGFloat {
        guard columns > 1 else { return total }
        return max(0, (total - spacing * CGFloat(columns - 1)) / CGFloat(columns))
    }

    private func lineHeight(_ line: [Int], width: CGFloat, subviews: Subviews) -> CGFloat {
        var height: CGFloat = 0
        for index in line {
            height = max(height, subviews[index].sizeThatFits(ProposedViewSize(width: width, height: nil)).height)
        }
        return height
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let columns = columnCount(proposal.width, subviews)
        let total: CGFloat
        if let width = proposal.width, width.isFinite {
            total = width
        } else {
            var widest: CGFloat = 0
            for subview in subviews { widest = max(widest, subview.sizeThatFits(.unspecified).width) }
            total = widest * CGFloat(columns) + spacing * CGFloat(columns - 1)
        }
        let width = columnWidth(total, columns: columns)
        var height: CGFloat = 0
        for (index, line) in SquashGameScoresGeometry10868.lines(count: subviews.count, columns: columns).enumerated() {
            height += lineHeight(line, width: width, subviews: subviews) + (index > 0 ? spacing : 0)
        }
        return CGSize(width: total, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let columns = columnCount(bounds.width, subviews)
        let width = columnWidth(bounds.width, columns: columns)
        var y = bounds.minY
        for line in SquashGameScoresGeometry10868.lines(count: subviews.count, columns: columns) {
            let height = lineHeight(line, width: width, subviews: subviews)
            for (column, index) in line.enumerated() {
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(column) * (width + spacing), y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: width, height: height)
                )
            }
            y += height + spacing
        }
    }
}

/// Stable ids for the host's focus return and UI tests.
nonisolated enum SquashGameScoresAccessibilityID10868 {
    static let header = "squashGames10868.header"
    static let expand = "squashGames10868.expand"
    static let key = "squashGames10868.key"
    static let empty = "squashGames10868.empty"
    static let match = "squashGames10868.match"
    static let facts = "squashGames10868.facts"
    static let notes = "squashGames10868.notes"
    static let report = "squashGames10868.report"
    static func game(_ id: String) -> String { "squashGames10868.game.\(id)" }
}

/// The actual games: dense paired point bars per game on the owner's one
/// scale, both numeric points, each game's reported winner and cumulative
/// games, then the separate final match score, total points and reported
/// duration. Actual facts only — never a chance. Keeps no state.
struct SquashGameScoresPresentation10868: View {
    let input: SquashGameScoresInput10868
    /// Opens the host's full-size games; nil draws no control.
    var onExpand: (() -> Void)? = nil
    /// Opens the host's match report; nil draws no control.
    var onReport: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference's 92-point bar scale, growing with text size.
    @ScaledMetric(relativeTo: .caption) private var barMaxHeight: CGFloat = 92
    @ScaledMetric(relativeTo: .caption) private var barWidth: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var winnerRule: CGFloat = 3
    @ScaledMetric(relativeTo: .title) private var factSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// The report control's words, only with readable words and a callback.
    var reportLabel: String? {
        guard onReport != nil else { return nil }
        return SquashEventPageModel10868.readable(input.reportLabel)
    }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 16) {
                header
                key
                if input.visibleRows.isEmpty {
                    Text(input.empty)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.empty)
                } else {
                    SquashGameTileGrid10868(spacing: 10, accessibilitySize: typeSize.isAccessibilitySize) {
                        ForEach(Array(input.visibleRows.enumerated()), id: \.offset) { index, row in
                            tile(row, index: index)
                        }
                    }
                }
                notes
                if let match = input.visibleMatch {
                    fact(match)
                        .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.match)
                }
                facts
                if let words = input.visibleScaleWords {
                    Text(words)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                reportButton
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Header and key

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = SquashEventPageModel10868.readable(input.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                }
                Text(input.title)
                    .font(.title3.bold())
                    .foregroundStyle(DS.textPrimary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityHeader ?? "")
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.header)
            if let onExpand {
                Button(action: onExpand) {
                    Image(systemName: "arrow.up.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.expandLabel)
                .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.expand)
            }
        }
    }

    private var key: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
        return layout {
            Text(input.keyLabel)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
            playerKey(input.first)
            playerKey(input.second)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityKey ?? "")
        .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.key)
    }

    /// The player's shape in its tint beside the whole name in primary text.
    private func playerKey(_ player: SquashGamePlayer10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: SquashGameScoresGeometry10868.symbol(player.shape))
                .font(.caption2)
                .foregroundStyle(player.tint)
            Text(player.name)
                .font(.subheadline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Games

    /// One game: its label, both players' points over their bars, the
    /// cumulative games with the winner's key, any absence or not-drawn
    /// words, and the winner's rule. One element, spoken in full.
    private func tile(_ row: SquashGameRow10868, index: Int) -> some View {
        VStack(spacing: 8) {
            Text(row.label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .bottom, spacing: 6) {
                bar(row.first, player: input.first)
                bar(row.second, player: input.second)
            }
            .frame(minHeight: barMaxHeight, alignment: .bottom)
            if let games = SquashEventPageModel10868.readable(row.games) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    if let winner = input.winner(row) {
                        Image(systemName: SquashGameScoresGeometry10868.symbol(winner.shape))
                            .font(.caption2)
                            .foregroundStyle(winner.tint)
                    }
                    Text(games)
                        .font(.headline)
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            ForEach(Array([row.first.unknownWords, row.second.unknownWords].compactMap { $0 }.enumerated()),
                    id: \.offset) { _, words in
                Text(words)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if input.rowShowsNotDrawn(row) {
                Text(input.notDrawn)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let winner = input.winner(row) {
                Rectangle()
                    .fill(winner.tint)
                    .frame(height: winnerRule)
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(row.label)
        .accessibilityValue(input.accessibilityRow(row))
        .accessibilityIdentifier(input.accessibilityID(at: index) ?? "")
    }

    /// One player's figure over its bar on the shared scale; a figure that
    /// cannot be placed keeps its words and draws no bar; unknown points draw
    /// neither. Decorative: the tile speaks.
    private func bar(_ points: SquashGamePoints10868, player: SquashGamePlayer10868) -> some View {
        VStack(spacing: 4) {
            if let figure = points.figure {
                Text(figure)
                    .font(.caption.bold())
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            }
            if let fraction = input.barFraction(points),
               let height = SquashGameScoresGeometry10868.barHeight(fraction, maxHeight: barMaxHeight) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(player.tint)
                    .frame(width: barWidth, height: height)
            } else {
                Color.clear.frame(width: barWidth, height: 0)
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Facts, notes and report

    @ViewBuilder private var notes: some View {
        if !input.visibleNotes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.visibleNotes.enumerated()), id: \.offset) { _, note in
                    Text(note)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.notes)
        }
    }

    /// Total points and reported duration side by side where both fit whole,
    /// else stacked.
    @ViewBuilder private var facts: some View {
        let shown = [input.visibleTotalPoints, input.visibleDuration].compactMap { $0 }
        if !shown.isEmpty {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 24) {
                    ForEach(Array(shown.enumerated()), id: \.offset) { _, item in fact(item) }
                }
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(shown.enumerated()), id: \.offset) { _, item in fact(item) }
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.facts)
        }
    }

    /// The owner's value large, its actual-fact label beneath. Spoken whole.
    private func fact(_ item: SquashGameFact10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(item.value)
                .font(.system(size: factSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Text(item.label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(item.spoken)
    }

    @ViewBuilder private var reportButton: some View {
        if let label = reportLabel, let onReport {
            Button(action: onReport) {
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
                .frame(minHeight: controlSize)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(SquashGameScoresAccessibilityID10868.report)
        }
    }
}

// MARK: - Page input

/// The owner's one-line match words above full-size content.
nonisolated struct SquashEventPageReaderHeader10868: Equatable {
    /// The owner's players and phase words.
    let title: String
    /// The owner's event and round words; nil draws none.
    let state: String?
}

/// The owner's caution about the pre-match expectation, in readable type —
/// never a footnote. Words only: never a reading, a baseline or a forecast.
nonisolated struct SquashEventPageExpectation10868: Equatable {
    /// "No reliable pre-match estimate", "Pre-match comparison unavailable".
    let title: String
    /// The owner's reason; nil draws none.
    let reason: String?
}

/// One titled section of owner text, verbatim.
nonisolated struct SquashEventPageSection10868: Equatable {
    let title: String?
    let paragraphs: [String]
}

/// An owner link inside a text mode: its id is handed back unchanged.
nonisolated struct SquashEventPageLink10868: Equatable {
    let id: String
    let label: String
}

/// The owner's About, source details or match report, verbatim.
nonisolated struct SquashEventPageText10868: Equatable {
    let title: String
    let sections: [SquashEventPageSection10868]
    /// Drawn only with readable words, a nonempty id and the host's callback.
    var link: SquashEventPageLink10868? = nil
}

nonisolated struct SquashEventPageCopy10868: Equatable {
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// "History & source details"; nil draws no entry.
    var sourceLabel: String? = nil
    /// "All 2 original markets"; nil draws no entry.
    var allPropsLabel: String? = nil
}

nonisolated struct SquashEventPageInput10868: Equatable {
    let phase: SquashEventPagePhase10868
    let reader: SquashEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    /// The owner's status words under the headline; nil draws none.
    var notice: String? = nil
    /// The owner's expectation caution; nil draws none.
    var expectation: SquashEventPageExpectation10868? = nil
    /// The probability history with the owner's own inspection — separate
    /// from the actual games.
    let history: FieldHistoryInput10868
    /// The owner's plot height for the full-size history; nil keeps the page's.
    var readerPlotHeight: CGFloat? = nil
    /// The actual games, during and after play only.
    var games: SquashGameScoresInput10868? = nil
    /// Opened by the headline's About control; nil: no control.
    var about: SquashEventPageText10868? = nil
    /// Opened by the source entry; nil: no entry.
    var source: SquashEventPageText10868? = nil
    /// Opened by the games' report control; nil: no control.
    var report: SquashEventPageText10868? = nil
    let copy: SquashEventPageCopy10868
}

/// The owner's two winner originals behind the chooser, "All props" and the
/// Details mode. Every field reaches the existing leaves unchanged.
struct SquashEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The held original's admitted recorded history, for the Details mode
    /// only; nil keeps its summary-only Details.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's choice label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "Original markets".
    let heading: String
    /// "2 retained originals"; nil draws none.
    var context: String? = nil
    /// "No retained originals for this match".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum SquashEventPageAccessibilityID10868 {
    static let page = "squashEventPage10868.page"
    static let hero = "squashEventPage10868.hero"
    static let headlineUnavailable = "squashEventPage10868.headline.unavailable"
    static let notice = "squashEventPage10868.notice"
    static let expectation = "squashEventPage10868.expectation"
    static let anchor = "squashEventPage10868.anchor"
    static let sourceEntry = "squashEventPage10868.sourceEntry"
    static let games = "squashEventPage10868.games"
    static let originals = "squashEventPage10868.originals"
    static let allProps = "squashEventPage10868.allProps"
    static let readerHeader = "squashEventPage10868.readerHeader"
    static let readerAbout = "squashEventPage10868.readerHeader.about"
    static let fullHistory = "squashEventPage10868.fullHistory"
    static let fullGames = "squashEventPage10868.fullGames"
    static let catalogue = "squashEventPage10868.catalogue"
    static let original = "squashEventPage10868.original"
    static let about = "squashEventPage10868.about"
    static let source = "squashEventPage10868.source"
    static let report = "squashEventPage10868.report"
    static let link = "squashEventPage10868.link"
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct SquashEventPageModel10868: Equatable {
    let input: SquashEventPageInput10868

    init(_ input: SquashEventPageInput10868) {
        self.input = input
    }

    /// The headline's own name for the page's phase.
    static func headlinePhase(_ phase: SquashEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    /// The actual games at the page's own phase, during and after play only.
    var games: SquashGameScoresInput10868? {
        guard let games = input.games, games.phase == input.phase, games.isShown else { return nil }
        return games
    }

    /// The owner's caution, when it carries readable words.
    var expectation: SquashEventPageExpectation10868? {
        guard let expectation = input.expectation, Self.readable(expectation.title) != nil else { return nil }
        return expectation
    }

    var notice: String? { Self.readable(input.notice) }

    /// Full-size content exists for the history always, and for the games
    /// when this phase shows them.
    func readerShows(_ mode: SquashEventPageMode10868) -> Bool {
        switch mode {
        case .fullHistory: true
        case .fullGames: games != nil
        default: false
        }
    }

    /// The anchor's full-size content: the same history in its expanded
    /// layout, without an expand control inside the reader, at the owner's
    /// reader height when supplied. Every other field is the owner's.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: input.readerPlotHeight ?? history.plotHeight,
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

    // MARK: Text modes and entries

    static func hasWords(_ section: SquashEventPageSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    /// Owner text, when it carries readable words.
    static func readableText(_ text: SquashEventPageText10868?) -> SquashEventPageText10868? {
        guard let text, readable(text.title) != nil || text.sections.contains(where: hasWords) else { return nil }
        return text
    }

    var about: SquashEventPageText10868? { Self.readableText(input.about) }

    var source: SquashEventPageText10868? { Self.readableText(input.source) }

    var report: SquashEventPageText10868? { Self.readableText(input.report) }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// The source entry: readable details, the owner's entry words and a callback.
    func sourceAvailable(canOpen: Bool) -> Bool {
        canOpen && source != nil && Self.readable(input.copy.sourceLabel) != nil
    }

    /// The games' report control: a readable report and a callback; the games
    /// leaf adds its own label rule.
    func reportAvailable(canOpen: Bool) -> Bool {
        canOpen && report != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    /// Whether `mode`'s compact heading shows the About entry: full-size
    /// history and games only — the page has the headline's own control.
    func aboutEntry(mode: SquashEventPageMode10868, canOpen: Bool) -> Bool {
        guard mode == .fullHistory || mode == .fullGames,
              Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    /// A text mode's link: a nonempty id and readable words with a callback.
    static func link(_ text: SquashEventPageText10868, canOpen: Bool) -> SquashEventPageLink10868? {
        guard canOpen, let link = text.link, readable(link.id) != nil, readable(link.label) != nil else { return nil }
        return link
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries the headline beside the history, then stacks — their
    /// minimum widths decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [SquashEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Text content

/// The owner's About, source details or match report in its own words, with
/// its link only when the host can open it. Acts on nothing else.
struct SquashEventPageTextContent10868: View {
    let text: SquashEventPageText10868
    /// Hands back the link's exact id.
    var onLink: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var link: SquashEventPageLink10868? { SquashEventPageModel10868.link(text, canOpen: onLink != nil) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = SquashEventPageModel10868.readable(text.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(text.sections.enumerated()), id: \.offset) { _, section in
                if SquashEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = SquashEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = SquashEventPageModel10868.readable(paragraph) {
                                Text(words)
                                    .font(.body)
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                    }
                }
            }
            if let link, let onLink {
                Button {
                    onLink(link.id)
                } label: {
                    HStack(spacing: 8) {
                        Text(link.label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(SquashEventPageAccessibilityID10868.link)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Page view

struct SquashEventPagePresentation10868: View {
    let input: SquashEventPageInput10868
    var mode: SquashEventPageMode10868 = .page
    /// The page's chooser and the catalogue and Details modes' content; nil:
    /// none of them has any.
    var originals: SquashEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// Opens the host's container on the owner's source details.
    var onSource: (() -> Void)? = nil
    /// Opens the host's container on the owner's match report.
    var onReport: (() -> Void)? = nil
    /// A text mode's link id, for the host to open.
    var onLink: ((String) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A chooser or catalogue original's exact selection, for the host to hold
    /// and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// A headline player's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    /// The history's owner action ids (expand, windows, inspect, previous, next).
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the games' full-size content.
    var onGamesExpand: (() -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback, so the owner can hold its frame. Never called by
    /// building the view or by full-size or text content.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: SquashEventPageModel10868 { SquashEventPageModel10868(input) }

    // MARK: Holds

    /// A page, catalogue or Details action, after the owner's interaction
    /// hook. No host callback: no action and no hook call. No hook: the exact
    /// callback.
    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return { value in
            interaction()
            action(value)
        }
    }

    /// The same for an action without a value.
    static func heldAction(_ action: (() -> Void)?, by interaction: (() -> Void)?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return {
            interaction()
            action()
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .fullHistory: fullHistoryMode
            case .fullGames: fullGamesMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: textMode(aboutContent(), id: SquashEventPageAccessibilityID10868.about)
            case .source: textMode(sourceContent(), id: SquashEventPageAccessibilityID10868.source)
            case .report: textMode(reportContent(), id: SquashEventPageAccessibilityID10868.report)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's About opener; nil without readable About text or without a
    /// callback, so no About control is drawn.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The host's report opener; nil without a readable report or a callback.
    func reportOpener() -> (() -> Void)? {
        guard model.reportAvailable(canOpen: onReport != nil), let onReport else { return nil }
        return onReport
    }

    /// The match headline, at the page's phase only. Its open and About pass
    /// the interaction hook first.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0, onAbout: Self.heldAction(aboutOpener(), by: onInteraction),
                                                onOpen: Self.held(onHeadlineOpen, by: onInteraction))
        }
    }

    /// The anchor passes the interaction hook first; the full-size history
    /// keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The actual games, during and after play. On the page the expand and
    /// report controls pass the hook first; full size there is no expand and
    /// the report keeps its exact callback. Never reads the inspection.
    func gamesContent(reader: Bool) -> SquashGameScoresPresentation10868? {
        model.games.map {
            SquashGameScoresPresentation10868(
                input: $0,
                onExpand: reader ? nil : Self.heldAction(onGamesExpand, by: onInteraction),
                onReport: Self.heldAction(reportOpener(), by: reader ? nil : onInteraction)
            )
        }
    }

    /// The existing chooser and held Details on the page, with the owner's
    /// originals exactly as admitted, its select callback after the hook.
    func chooserContent() -> OriginalMarketChooserView9483? {
        originals.map {
            OriginalMarketChooserView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing catalogue with the owner's originals, exactly as admitted,
    /// and its select callback after the interaction hook.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing Details for the owner's held selection, with its optional
    /// recorded history and its history callback after the interaction hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// The owner's About — content the host already holds, so no hook.
    func aboutContent() -> SquashEventPageTextContent10868? {
        model.about.map { SquashEventPageTextContent10868(text: $0, onLink: onLink) }
    }

    func sourceContent() -> SquashEventPageTextContent10868? {
        model.source.map { SquashEventPageTextContent10868(text: $0, onLink: onLink) }
    }

    func reportContent() -> SquashEventPageTextContent10868? {
        model.report.map { SquashEventPageTextContent10868(text: $0, onLink: onLink) }
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    /// The page's source entry, after the interaction hook.
    func openSource() {
        guard model.sourceAvailable(canOpen: onSource != nil) else { return }
        Self.heldAction(onSource, by: onInteraction)?()
    }

    /// The page's All props entry, after the interaction hook.
    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        Self.heldAction(onAllProps, by: onInteraction)?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            if let games = gamesContent(reader: false) {
                games
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(SquashEventPageCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(SquashEventPageAccessibilityID10868.games)
            }
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(SquashEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both fit
    /// at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = SquashEventPageModel10868.arrangements(
                sizeClass: sizeClass,
                accessibilitySize: typeSize.isAccessibilitySize
            )
            if arrangements == [.stacked] {
                heroStacked
            } else {
                ViewThatFits(in: .horizontal) {
                    heroSideBySide
                    heroStacked
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(SquashEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(SquashEventPageAccessibilityID10868.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 24) {
            headlineSection
            anchor
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 32) {
            headlineSection
                .frame(minWidth: headlineMinWidth, maxWidth: headlineMaxWidth, alignment: .topLeading)
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    /// The headline, or the owner's words when its phase is not the page's,
    /// then the owner's status words and expectation caution.
    private var headlineSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let headline = headlineContent() {
                headline
            } else {
                Text(input.copy.headlineUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(SquashEventPageAccessibilityID10868.headlineUnavailable)
            }
            if let notice = model.notice {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(SquashEventPageAccessibilityID10868.notice)
            }
            if let expectation = model.expectation {
                expectationView(expectation)
            }
        }
    }

    /// The owner's caution in readable, primary type: a heading and its reason.
    private func expectationView(_ expectation: SquashEventPageExpectation10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(expectation.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
            if let reason = SquashEventPageModel10868.readable(expectation.reason) {
                Text(reason)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(SquashEventPageAccessibilityID10868.expectation)
    }

    /// The history, then the source entry when the owner names one.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 12) {
            historyContent(reader: false)
            if model.sourceAvailable(canOpen: onSource != nil), let label = input.copy.sourceLabel {
                entry(label, action: openSource, id: SquashEventPageAccessibilityID10868.sourceEntry)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(SquashEventPageAccessibilityID10868.anchor)
    }

    /// The two winner originals with the held original's Details, then the
    /// All props entry when the owner names one.
    @ViewBuilder private var originalsPanel: some View {
        let allProps = model.allPropsAvailable(canOpen: onAllProps != nil)
        if chooserContent() != nil || allProps {
            VStack(alignment: .leading, spacing: 16) {
                if let chooser = chooserContent() {
                    chooser
                }
                if allProps, let label = input.copy.allPropsLabel {
                    entry(label, action: openAllProps, id: SquashEventPageAccessibilityID10868.allProps)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(SquashEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SquashEventPageAccessibilityID10868.originals)
        }
    }

    private func entry(_ label: String, action: @escaping () -> Void, id: String) -> some View {
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
            .frame(minHeight: controlSize)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    // MARK: Full-size content

    /// The same history input, full size, under the compact match words.
    private var fullHistoryMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            historyContent(reader: true)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(SquashEventPageAccessibilityID10868.fullHistory)
    }

    /// The same games input, full size, under the compact match words. None
    /// when this phase shows no games.
    @ViewBuilder private var fullGamesMode: some View {
        if let games = gamesContent(reader: true) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                games
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SquashEventPageAccessibilityID10868.fullGames)
        }
    }

    /// The owner's one-line match words and, in full-size content, the About
    /// entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = SquashEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                Button(action: openReaderAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(SquashEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(SquashEventPageAccessibilityID10868.readerHeader)
    }

    // MARK: All props, Details and text

    /// The owner's admitted originals under the compact match words.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(SquashEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(SquashEventPageAccessibilityID10868.original)
        }
    }

    /// The owner's text under the compact match words; none without readable text.
    @ViewBuilder private func textMode(_ content: SquashEventPageTextContent10868?, id: String) -> some View {
        if let content {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(id)
        }
    }
}

/// The reference's white card on the page surface.
private struct SquashEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
