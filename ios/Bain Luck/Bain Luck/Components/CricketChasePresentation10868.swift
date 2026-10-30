import SwiftUI

// #10868 — "The chase": the cricket-live chase card, adaptive across before,
// during and final. During play it puts two equally prominent labelled chance
// figures — the owner's pregame reading and its recorded or current reading —
// above the batting side's actual runs toward the win target, an explicit
// target marker, the wickets as shapes and the owner's overs and report
// context. At the final it shows the independently reported innings and match
// result, then the same original pregame chance beside its independently
// admitted contract result.
//
// The actual and the chance are separate facts with separate clocks. The run
// rail is runs, not a percentage: its fill is the reported runs and its end
// mark is the win target, which is a threshold, never a projected finish. The
// rail does not grade the market, the market does not grade the match, and
// a target never yields a winner or a margin (421 − 206 = 215 is runs short
// of the target, not the 214-run victory). A failed probability leaves the
// actuals standing and a failed score leaves the probabilities standing. An
// unconfirmed or void contract result stays the owner's words and is never
// shown as a loss. Before play every score, wicket, target, current reading,
// actual finish and settlement is suppressed from the view and from every
// spoken helper even when supplied; only the pregame reading remains, and
// the owner may leave the card out entirely.
//
// Presentation only, extracted from the approved design: `CricketLive.tsx`
// ChaseCard and `CricketLifecycle.tsx` FinalChase with `cricketLive.css` and
// `cricketLifecycle.css`. The historical native `CL186ChaseView` and
// `CL186Wickets` are visual references only; their model, clocks, evidence
// loader, phase resolver, formatter, cutoff and eligibility pipeline are NOT
// ported, and neither is their `max(1, target)` axis.
//
// Every phase, subject, label, figure, run and target text, wicket state,
// overs and context line, result and provenance arrives resolved by the owner
// and is shown verbatim. This layer never formats or rounds a number, never
// computes runs needed, wickets left, overs, a margin, a projection or a
// result, never reads or converts a clock, never parses a title, name or
// ticker, never elects a baseline, complements or normalizes. The numeric run
// and target values only place the fill and the target mark; they cannot
// validate source truth.
//
// Details, held updates, disclosure, reader placement, Back and focus stay
// with the host: the view keeps no state, no sheet and no subscription and
// runs no animation, so reduced motion has nothing to stop. Details appears
// only when the owner supplied both a callback and an exact reference.
//
// Host binding still owed — not available at this base. An owner must supply
// proved batting innings, target and wicket membership from independently
// qualified cricket state (the frozen score tuple carries none), a canonical
// identity and Details reference for the original (never a parsed ticker or
// title), an admitted pregame observation, an admitted recorded or current
// observation with currentness applied, the independently admitted contract
// result and match result, and local-calendar provenance words.
// CRICKET-CHASE-NATIVE-BINDING-MAP.md names the gaps.
//
// A limited-over chase (cricket-t20) passes an optional limited-over context
// beside the input — see "Limited-over chase" below. Without it this card is
// unchanged.

nonisolated enum CricketChasePhase10868: Equatable, CaseIterable {
    /// Before play: the pregame reading only.
    case before
    /// In play: pregame and recorded/current chances above the actual chase.
    case during
    /// Finished: the actual innings and match result, then pregame beside the
    /// contract result.
    case final
}

/// One owner-formatted figure with its full provenance.
nonisolated struct CricketChaseFigure10868: Equatable {
    /// The owner's whole figure ("48%", "<1%", "Lost").
    let text: String
    /// Full provenance in the owner's local-calendar words, including the bar
    /// boundary or settlement clock and venue.
    let detail: String
}

/// One chance reading, each with its own words when absent.
nonisolated enum CricketChaseReading10868: Equatable {
    case observed(CricketChaseFigure10868)
    /// No admitted reading ("Current probability unavailable").
    case unavailable(String)
    /// A reading exists but is not admitted here ("Held — not current"). It
    /// carries no value, so nothing stale can be shown.
    case withheld(String)
}

/// The original contract's own result, admitted independently of the match.
nonisolated enum CricketChaseContractResult10868: Equatable {
    /// The owner's graded word ("Lost") with its settlement provenance.
    case graded(CricketChaseFigure10868)
    /// Not yet confirmed — the owner's words, never a loss.
    case unconfirmed(String)
    /// Voided or cancelled — the owner's words, never a loss.
    case void(String)
    case unavailable(String)
}

/// The match result, admitted independently of the target and the market.
nonisolated enum CricketChaseMatchResult10868: Equatable {
    /// The owner's match-result words with their report/confirmation provenance.
    case reported(CricketChaseFigure10868)
    case unavailable(String)
}

/// A run count or target: the owner's text, plus the real number that places
/// it on the rail.
nonisolated enum CricketChaseQuantity10868: Equatable {
    case reported(text: String, value: Double)
    /// Unknown — shown as words, never as zero.
    case unknown(String)

    var value: Double? {
        if case .reported(_, let value) = self { return value }
        return nil
    }
}

/// One wicket position, in the owner's order. Decorative: the owner's words
/// carry the meaning.
nonisolated enum CricketChaseWicket10868: Equatable, CaseIterable {
    case lost
    case remaining
    case unknown
}

/// The batting side's independently qualified actual chase state.
nonisolated struct CricketChaseState10868: Equatable {
    /// The batting side, in the owner's words.
    let battingSubject: String
    /// The owner's report label ("Day 5 · lunch"); nil draws none.
    let context: String?
    let runs: CricketChaseQuantity10868
    /// "runs scored", "all out".
    let runsCaption: String
    let target: CricketChaseQuantity10868
    /// "runs".
    let targetCaption: String
    /// The owner's ordered wicket positions; the owner owns the count. Empty
    /// draws no marks.
    let wickets: [CricketChaseWicket10868]
    /// "6 wickets left", "All ten wickets lost", "Wickets unknown".
    let wicketsText: String
    /// "64 overs played", "Final overs unknown".
    let oversText: String
    /// The score report's own provenance ("Score report published 2:11 AM
    /// PDT, Oct 13 · not the exact ball time").
    let reportDetail: String
}

nonisolated enum CricketChaseActual10868: Equatable {
    case reported(CricketChaseState10868)
    /// No qualified chase state — the owner's words.
    case unavailable(String)
}

/// The owner's exact, opaque identity for the original, handed back unchanged.
nonisolated struct CricketChaseRef10868: Hashable {
    let event: String
    let market: String
    let outcome: String
}

nonisolated enum CricketChaseAction10868: Equatable {
    case details(CricketChaseRef10868)

    func perform(onDetails: ((CricketChaseRef10868) -> Void)?) {
        switch self {
        case .details(let ref): onDetails?(ref)
        }
    }
}

/// Where the rail draws, as fractions of its width.
nonisolated struct CricketChaseRailGeometry10868: Equatable {
    /// The actual runs' fill end.
    let fill: Double
    /// The win target's end mark.
    let target: Double
}

nonisolated struct CricketChaseInput10868: Equatable {
    let phase: CricketChasePhase10868
    /// The original's subject, in the owner's words, for Details.
    let subject: String
    /// "<side> · second innings", "The chase · final". Shown in every
    /// phase, so it must be safe before play.
    let eyebrow: String
    /// The owner's in-play heading ("267 runs still needed"). Shown during
    /// play only; the final heading is the match result.
    let headline: String?
    /// "Pregame".
    let pregameLabel: String
    let pregame: CricketChaseReading10868
    /// "Recorded win chance", "Current win chance". The owner alone decides
    /// which word its reading has earned.
    let comparisonLabel: String
    /// Shown during play only.
    let comparison: CricketChaseReading10868
    /// "Final".
    let resultLabel: String
    /// Shown at the final only.
    let contractResult: CricketChaseContractResult10868
    /// Shown at the final only.
    let matchResult: CricketChaseMatchResult10868
    /// Shown during play and at the final only.
    let actual: CricketChaseActual10868
    /// Nil when no safe owner reference exists: no Details.
    let detailsRef: CricketChaseRef10868?
    /// Verbatim lines; shown during play and at the final only.
    let notes: [String]

    static let targetLabel = "Target to win"
    static let targetQualifier = "Target to win is not a projected finish"
    static let railNotDrawn = "Run progress not drawn"
    static let detailsTitle = "Details"

    // MARK: Phase gating

    var isBefore: Bool { phase == .before }

    /// During: the owner's headline. Final: the match result. Before: none.
    var visibleHeading: String? {
        switch phase {
        case .before:
            return nil
        case .during:
            return headline
        case .final:
            switch matchResult {
            case .reported(let figure): return figure.text
            case .unavailable(let words): return words
            }
        }
    }

    /// The match result's provenance, at the final only.
    var visibleHeadingDetail: String? {
        guard phase == .final, case .reported(let figure) = matchResult else { return nil }
        return figure.detail
    }

    /// The recorded/current reading, during play only — never at the final,
    /// where a settled 0% or 100% is not a chance.
    var visibleComparison: CricketChaseReading10868? {
        phase == .during ? comparison : nil
    }

    var visibleContractResult: CricketChaseContractResult10868? {
        phase == .final ? contractResult : nil
    }

    var visibleActual: CricketChaseActual10868? {
        isBefore ? nil : actual
    }

    var visibleState: CricketChaseState10868? {
        guard case .reported(let state) = visibleActual else { return nil }
        return state
    }

    var visibleActualWords: String? {
        guard case .unavailable(let words) = visibleActual else { return nil }
        return words
    }

    var visibleWickets: [CricketChaseWicket10868] {
        visibleState?.wickets ?? []
    }

    var visibleNotes: [String] {
        isBefore ? [] : notes
    }

    // MARK: Rail

    /// Nil unless the reported state's runs and target both place.
    var railGeometry: CricketChaseRailGeometry10868? {
        guard let state = visibleState else { return nil }
        return CricketChaseGeometry10868.rail(runs: state.runs.value, target: state.target.value)
    }

    /// A reported state whose runs or target cannot be drawn says so.
    var showsRailNotDrawn: Bool {
        visibleState != nil && railGeometry == nil
    }

    // MARK: Action

    /// Details for the exact owner reference only, when the owner can open it.
    func detailsAction(canOpenDetails: Bool) -> CricketChaseAction10868? {
        guard canOpenDetails, let detailsRef else { return nil }
        return .details(detailsRef)
    }

    var detailsText: String { "\(subject) · \(Self.detailsTitle)" }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, visibleHeading, visibleHeadingDetail].compactMap { $0 }).joined(separator: ". ")
    }

    /// Pregame, then recorded/current (during) or the contract result
    /// (final), each with its own provenance.
    var accessibilityChances: String {
        var parts = ["\(pregameLabel): \(Self.spoken(pregame))"]
        if let comparison = visibleComparison {
            parts.append("\(comparisonLabel): \(Self.spoken(comparison))")
        }
        if let result = visibleContractResult {
            parts.append("\(resultLabel): \(Self.spoken(result))")
        }
        return parts.joined(separator: ". ")
    }

    /// Runs versus target, the qualifier, and a rail that could not be drawn.
    var accessibilityRuns: String? {
        guard let state = visibleState else { return visibleActualWords }
        var parts = [
            "\(state.battingSubject): \(Self.spoken(state.runs, caption: state.runsCaption))",
            "\(Self.targetLabel): \(Self.spoken(state.target, caption: state.targetCaption))",
            Self.targetQualifier,
        ]
        if showsRailNotDrawn { parts.append(Self.railNotDrawn) }
        return parts.joined(separator: ". ")
    }

    var accessibilityWickets: String? {
        guard let state = visibleState else { return nil }
        return ([state.wicketsText, state.oversText, state.context].compactMap { $0 }).joined(separator: ". ")
    }

    var accessibilityReport: String? {
        visibleState?.reportDetail
    }

    var accessibilityNotes: String? {
        visibleNotes.isEmpty ? nil : visibleNotes.joined(separator: " ")
    }

    private static func spoken(_ reading: CricketChaseReading10868) -> String {
        switch reading {
        case .observed(let figure): "\(figure.text), \(figure.detail)"
        case .unavailable(let words), .withheld(let words): words
        }
    }

    private static func spoken(_ result: CricketChaseContractResult10868) -> String {
        switch result {
        case .graded(let figure): "\(figure.text), \(figure.detail)"
        case .unconfirmed(let words), .void(let words), .unavailable(let words): words
        }
    }

    private static func spoken(_ quantity: CricketChaseQuantity10868, caption: String) -> String {
        switch quantity {
        case .reported(let text, _): "\(text) \(caption)"
        case .unknown(let words): words
        }
    }
}

nonisolated enum CricketChaseArrangement10868: Equatable {
    /// One subview, or more than two: stacked in order.
    case single
    case sideBySide
    case stacked
}

nonisolated struct CricketChaseColumns10868: Equatable {
    let first: CGFloat
    let second: CGFloat
}

nonisolated enum CricketChaseGeometry10868 {
    /// The fill and target mark on one runs domain that holds both supplied
    /// numbers, so an actual at or beyond the target stays inside. Zero runs
    /// is a real fill of nothing. Missing, negative or non-finite runs, or a
    /// missing, non-positive or non-finite target, draws nothing — no axis is
    /// manufactured.
    static func rail(runs: Double?, target: Double?) -> CricketChaseRailGeometry10868? {
        guard let runs, let target, runs.isFinite, target.isFinite, runs >= 0, target > 0 else { return nil }
        let domain = max(runs, target)
        return CricketChaseRailGeometry10868(fill: runs / domain, target: target / domain)
    }

    /// A fraction's x on a rail of `width`, inset so an end mark stays whole.
    static func x(_ fraction: Double, width: CGFloat, inset: CGFloat) -> CGFloat {
        let usable = max(0, width - 2 * inset)
        return inset + usable * CGFloat(fraction)
    }

    /// The owner's words, split only at whitespace, for measuring the widest
    /// unbreakable word. Typography, not parsing: nothing is interpreted.
    static func words(_ text: String) -> [String] {
        text.split(whereSeparator: \.isWhitespace).map(String.init)
    }

    static func equalColumn(available: CGFloat, spacing: CGFloat) -> CGFloat {
        max(0, (available - spacing) / 2)
    }

    /// Side by side only when both subviews keep their whole measured width.
    /// `measure` answers a subview's width for a proposed width (nil = its
    /// ideal). Equal columns fit when each subview measured at half the width
    /// stays inside it — a whole figure and the widest word included. Unequal
    /// columns fit when both ideal widths fit on one line. Otherwise stacked;
    /// nothing shrinks or truncates to fit.
    static func pairArrangement(
        available: CGFloat?,
        spacing: CGFloat,
        equalColumns: Bool,
        forceStack: Bool,
        first: (CGFloat?) -> CGFloat,
        second: (CGFloat?) -> CGFloat
    ) -> CricketChaseArrangement10868 {
        if forceStack { return .stacked }
        guard let available, available.isFinite else { return .sideBySide }
        if equalColumns {
            let column = equalColumn(available: available, spacing: spacing)
            return first(column) <= column + 0.5 && second(column) <= column + 0.5 ? .sideBySide : .stacked
        }
        let firstIdeal = first(nil)
        let secondIdeal = second(nil)
        guard firstIdeal.isFinite, secondIdeal.isFinite else { return .stacked }
        return firstIdeal + spacing + secondIdeal <= available + 0.5 ? .sideBySide : .stacked
    }

    /// Equal halves, or the second subview at its ideal width at the trailing
    /// edge with the first taking the rest.
    static func columns(total: CGFloat, secondIdeal: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CricketChaseColumns10868 {
        if equalColumns {
            let half = equalColumn(available: total, spacing: spacing)
            return CricketChaseColumns10868(first: half, second: half)
        }
        let second = min(max(0, secondIdeal), max(0, total - spacing))
        return CricketChaseColumns10868(first: max(0, total - spacing - second), second: second)
    }
}

/// Two subviews side by side while both keep their whole measured width, else
/// stacked at full width. Used for the chance pair, runs/target and the
/// wickets/overs line.
struct CricketChasePairLayout10868: Layout {
    var spacing: CGFloat
    var equalColumns: Bool
    var forceStack: Bool

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> CricketChaseArrangement10868 {
        guard subviews.count == 2 else { return .single }
        return CricketChaseGeometry10868.pairArrangement(
            available: width,
            spacing: spacing,
            equalColumns: equalColumns,
            forceStack: forceStack,
            first: { subviews[0].sizeThatFits(ProposedViewSize(width: $0, height: nil)).width },
            second: { subviews[1].sizeThatFits(ProposedViewSize(width: $0, height: nil)).width }
        )
    }

    private func columns(_ total: CGFloat, _ subviews: Subviews) -> CricketChaseColumns10868 {
        CricketChaseGeometry10868.columns(
            total: total,
            secondIdeal: subviews[1].sizeThatFits(.unspecified).width,
            spacing: spacing,
            equalColumns: equalColumns
        )
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        switch arrangement(proposal.width, subviews) {
        case .single, .stacked:
            return stackedSize(width: proposal.width, subviews: subviews)
        case .sideBySide:
            let total = proposal.width ?? (
                subviews[0].sizeThatFits(.unspecified).width + spacing + subviews[1].sizeThatFits(.unspecified).width
            )
            let widths = columns(total, subviews)
            let height = max(
                subviews[0].sizeThatFits(ProposedViewSize(width: widths.first, height: nil)).height,
                subviews[1].sizeThatFits(ProposedViewSize(width: widths.second, height: nil)).height
            )
            return CGSize(width: total, height: height)
        }
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        switch arrangement(bounds.width, subviews) {
        case .single, .stacked:
            var y = bounds.minY
            for subview in subviews {
                let size = subview.sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
                subview.place(
                    at: CGPoint(x: bounds.minX, y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: bounds.width, height: size.height)
                )
                y += size.height + spacing
            }
        case .sideBySide:
            let widths = columns(bounds.width, subviews)
            subviews[0].place(
                at: CGPoint(x: bounds.minX, y: bounds.minY),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: widths.first, height: nil)
            )
            subviews[1].place(
                at: CGPoint(x: bounds.minX + widths.first + spacing, y: bounds.minY),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: widths.second, height: nil)
            )
        }
    }

    private func stackedSize(width: CGFloat?, subviews: Subviews) -> CGSize {
        var height: CGFloat = 0
        var widest: CGFloat = 0
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(ProposedViewSize(width: width, height: nil))
            height += size.height + (index > 0 ? spacing : 0)
            widest = max(widest, size.width)
        }
        return CGSize(width: width ?? widest, height: height)
    }
}

/// Wrapping owner text that never breaks inside a word: a hidden, zero-height
/// strut of its words makes the widest word part of the measured width, so a
/// pair stacks before any word would split.
private struct CricketChaseWrappedText10868: View {
    let text: String
    let font: Font
    let color: Color

    var body: some View {
        ZStack(alignment: .leading) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(CricketChaseGeometry10868.words(text).enumerated()), id: \.offset) { _, word in
                    Text(word).font(font).fixedSize()
                }
            }
            .frame(height: 0)
            .hidden()
            Text(text)
                .font(font)
                .foregroundStyle(color)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// The actual runs fill and the win target's dashed end mark on one runs
/// domain. Decorative — the runs, target and qualifier are words beside it.
private struct CricketChaseRail10868: View {
    let geometry: CricketChaseRailGeometry10868
    let tint: Color
    let height: CGFloat

    private let overhang: CGFloat = 5
    private let markWidth: CGFloat = 2

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let fillWidth = CricketChaseGeometry10868.x(geometry.fill, width: width, inset: 0)
            let targetX = CricketChaseGeometry10868.x(geometry.target, width: width, inset: markWidth / 2)
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(DS.border)
                    .frame(width: width, height: height)
                    .offset(y: overhang)
                RoundedRectangle(cornerRadius: 4)
                    .fill(tint)
                    .frame(width: fillWidth, height: height)
                    .offset(y: overhang)
                Path { path in
                    path.move(to: CGPoint(x: targetX, y: 0))
                    path.addLine(to: CGPoint(x: targetX, y: height + 2 * overhang))
                }
                .stroke(DS.textPrimary, style: StrokeStyle(lineWidth: markWidth, dash: [3, 2]))
            }
        }
        .frame(maxWidth: .infinity, minHeight: height + 2 * overhang, maxHeight: height + 2 * overhang)
        .accessibilityHidden(true)
    }
}

/// One wicket position: solid for remaining, hollow and struck through for
/// lost, a dashed outline with a question mark for unknown. Shape and mark
/// supplement colour.
private struct CricketChaseWicketMark10868: View {
    let state: CricketChaseWicket10868
    let tint: Color
    let height: CGFloat
    /// The struck/question glyph; the survival card's narrow tiles pass a
    /// smaller scaled size so ten marks keep their whole width.
    var glyphFont: Font = .caption2

    var body: some View {
        ZStack {
            switch state {
            case .remaining:
                RoundedRectangle(cornerRadius: 3).fill(tint)
            case .lost:
                RoundedRectangle(cornerRadius: 3).fill(DS.cardBg)
                RoundedRectangle(cornerRadius: 3).strokeBorder(DS.border, lineWidth: 1)
                Image(systemName: "line.diagonal")
                    .font(glyphFont)
                    .foregroundStyle(DS.textSecondary)
            case .unknown:
                RoundedRectangle(cornerRadius: 3)
                    .strokeBorder(DS.textMuted, style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                Image(systemName: "questionmark")
                    .font(glyphFont)
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }
}

/// A whole owner figure above its provenance. The figure keeps its width; a
/// narrow pair stacks instead of squeezing or splitting it. Shared by the
/// chase and survival cards.
private struct CricketChaseFigureView10868: View {
    let figure: CricketChaseFigure10868
    let size: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(figure.text)
                .font(.system(size: size, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
            CricketChaseWrappedText10868(text: figure.detail, font: .caption2, color: DS.textSecondary)
        }
    }
}

/// The owner's words where a value is absent or held. Shared by the chase and
/// survival cards.
private struct CricketChaseMissingText10868: View {
    let words: String
    let size: CGFloat

    var body: some View {
        CricketChaseWrappedText10868(
            text: words,
            font: .system(size: size, weight: .semibold),
            color: DS.textSecondary
        )
    }
}

/// One labelled chance slot: the owner's label, then its figure and
/// provenance or its own missing words. Shared by the chase and survival
/// cards.
private struct CricketChaseReadingSlot10868: View {
    let label: String
    let reading: CricketChaseReading10868
    let figureSize: CGFloat
    let missingSize: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            CricketChaseWrappedText10868(text: label, font: .caption, color: DS.textSecondary)
            switch reading {
            case .observed(let figure):
                CricketChaseFigureView10868(figure: figure, size: figureSize)
            case .unavailable(let words), .withheld(let words):
                CricketChaseMissingText10868(words: words, size: missingSize)
            }
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum CricketChaseAccessibilityID10868 {
    static let header = "cricketChase10868.header"
    static let chances = "cricketChase10868.chances"
    static let runs = "cricketChase10868.runs"
    static let wickets = "cricketChase10868.wickets"
    static let report = "cricketChase10868.report"
    static let notes = "cricketChase10868.notes"
    static let details = "cricketChase10868.details"
    static let task = "cricketChase10868.task"
    static let balls = "cricketChase10868.balls"
    static let rates = "cricketChase10868.rates"
}

struct CricketChasePresentation10868: View {
    let input: CricketChaseInput10868
    /// The batting side's series tint for its runs figure and fill.
    let runsTint: Color
    /// The tint of a remaining wicket.
    let wicketTint: Color
    var onDetails: ((CricketChaseRef10868) -> Void)? = nil
    /// A limited-over chase's task, legal-ball budget and scoring rates.
    /// Nil keeps the unlimited-innings card unchanged.
    var limitedOvers: CricketChaseLimitedOvers10868? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: two 26-point chance figures, scaled with text size.
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var missingSize: CGFloat = 17
    @ScaledMetric(relativeTo: .largeTitle) private var runsSize: CGFloat = 36
    @ScaledMetric(relativeTo: .title) private var targetSize: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var railHeight: CGFloat = 18
    @ScaledMetric(relativeTo: .caption) private var wicketHeight: CGFloat = 22
    /// The limited-over task pair: the card's largest figures.
    @ScaledMetric(relativeTo: .largeTitle) private var taskSize: CGFloat = 40
    @ScaledMetric(relativeTo: .caption) private var ballRailHeight: CGFloat = 10
    @ScaledMetric(relativeTo: .caption) private var rateBarHeight: CGFloat = 6

    private var canOpenDetails: Bool { onDetails != nil }
    private var stacks: Bool { typeSize.isAccessibilitySize }
    private var limited: CricketChaseLimitedOversVisible10868? {
        CricketChaseLimitedOversVisible10868(phase: input.phase, context: limitedOvers)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            switch input.phase {
            case .before:
                pregameOnly
            case .during:
                chancePair
                actualSection
            case .final:
                actualSection
                chancePair
            }
            notes
            detailsButton
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header and notes

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.eyebrow)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            if let heading = input.visibleHeading {
                Text(heading).font(.title3.bold()).foregroundStyle(DS.textPrimary)
            }
            if let detail = input.visibleHeadingDetail {
                Text(detail).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.header)
    }

    @ViewBuilder private var notes: some View {
        if !input.visibleNotes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.visibleNotes.enumerated()), id: \.offset) { _, note in
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityNotes ?? "")
            .accessibilityIdentifier(CricketChaseAccessibilityID10868.notes)
        }
    }

    // MARK: Chances

    private var pregameOnly: some View {
        readingView(input.pregame, label: input.pregameLabel)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityChances)
            .accessibilityIdentifier(CricketChaseAccessibilityID10868.chances)
    }

    /// Pregame keeps the leading slot in every phase; the trailing slot is
    /// the recorded/current reading during play and the contract result at
    /// the final, at the same size.
    private var chancePair: some View {
        CricketChasePairLayout10868(spacing: 16, equalColumns: true, forceStack: stacks) {
            readingView(input.pregame, label: input.pregameLabel)
            if let comparison = input.visibleComparison {
                readingView(comparison, label: input.comparisonLabel)
            } else if let result = input.visibleContractResult {
                contractResult(result)
            }
        }
        .padding(.top, input.phase == .final ? 16 : 0)
        .overlay(alignment: .top) {
            if input.phase == .final {
                Rectangle().fill(DS.border).frame(height: 1)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityChances)
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.chances)
    }

    private func readingView(_ reading: CricketChaseReading10868, label: String) -> some View {
        CricketChaseReadingSlot10868(label: label, reading: reading, figureSize: chanceSize, missingSize: missingSize)
    }

    private func contractResult(_ result: CricketChaseContractResult10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            CricketChaseWrappedText10868(text: input.resultLabel, font: .caption, color: DS.textSecondary)
            switch result {
            case .graded(let figure):
                figureView(figure)
            case .unconfirmed(let words), .void(let words), .unavailable(let words):
                missing(words)
            }
        }
    }

    /// The whole figure keeps its width; a narrow card stacks the pair
    /// instead of squeezing or splitting it. Its provenance sits beneath it.
    private func figureView(_ figure: CricketChaseFigure10868) -> some View {
        CricketChaseFigureView10868(figure: figure, size: chanceSize)
    }

    private func missing(_ words: String) -> some View {
        CricketChaseMissingText10868(words: words, size: missingSize)
    }

    // MARK: Actual chase

    @ViewBuilder private var actualSection: some View {
        if let limited {
            limitedSection(limited)
        } else if let state = input.visibleState {
            VStack(alignment: .leading, spacing: 12) {
                runsGroup(state)
                wicketsGroup(state)
                CricketChaseWrappedText10868(text: state.reportDetail, font: .caption2, color: DS.textSecondary)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(input.accessibilityReport ?? "")
                    .accessibilityIdentifier(CricketChaseAccessibilityID10868.report)
            }
        } else if let words = input.visibleActualWords {
            missing(words)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(input.accessibilityRuns ?? "")
                .accessibilityIdentifier(CricketChaseAccessibilityID10868.runs)
        }
    }

    private func runsGroup(_ state: CricketChaseState10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let context = state.context {
                CricketChaseWrappedText10868(text: context, font: .caption, color: DS.textSecondary)
            }
            CricketChasePairLayout10868(spacing: 16, equalColumns: false, forceStack: stacks) {
                quantityBlock(
                    label: state.battingSubject,
                    quantity: state.runs,
                    caption: state.runsCaption,
                    size: runsSize,
                    color: runsTint
                )
                quantityBlock(
                    label: CricketChaseInput10868.targetLabel,
                    quantity: state.target,
                    caption: state.targetCaption,
                    size: targetSize,
                    color: DS.textSecondary
                )
            }
            if let geometry = input.railGeometry {
                CricketChaseRail10868(geometry: geometry, tint: runsTint, height: railHeight)
            }
            if input.showsRailNotDrawn {
                CricketChaseWrappedText10868(text: CricketChaseInput10868.railNotDrawn, font: .caption, color: DS.textSecondary)
            }
            CricketChaseWrappedText10868(text: CricketChaseInput10868.targetQualifier, font: .caption, color: DS.textSecondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityRuns ?? "")
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.runs)
    }

    private func quantityBlock(
        label: String,
        quantity: CricketChaseQuantity10868,
        caption: String,
        size: CGFloat,
        color: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            CricketChaseWrappedText10868(text: label, font: .caption, color: DS.textSecondary)
            switch quantity {
            case .reported(let text, _):
                Text(text)
                    .font(.system(size: size, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(color)
                    .fixedSize()
                CricketChaseWrappedText10868(text: caption, font: .caption, color: DS.textSecondary)
            case .unknown(let words):
                missing(words)
            }
        }
    }

    private func wicketsGroup(_ state: CricketChaseState10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if !input.visibleWickets.isEmpty {
                HStack(spacing: 5) {
                    ForEach(Array(input.visibleWickets.enumerated()), id: \.offset) { _, wicket in
                        CricketChaseWicketMark10868(state: wicket, tint: wicketTint, height: wicketHeight)
                    }
                }
            }
            CricketChasePairLayout10868(spacing: 12, equalColumns: false, forceStack: stacks) {
                CricketChaseWrappedText10868(text: state.wicketsText, font: .subheadline.bold(), color: DS.textPrimary)
                CricketChaseWrappedText10868(text: state.oversText, font: .subheadline, color: DS.textSecondary)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityWickets ?? "")
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.wickets)
    }

    // MARK: Limited-over chase

    /// The task pair large, the runs and target compact above the run rail,
    /// the legal-ball rail, the rate rows, then wickets and the report. The
    /// old large runs/target pair is not repeated beside the task pair.
    private func limitedSection(_ limited: CricketChaseLimitedOversVisible10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            if let task = limited.task {
                taskGroup(task, spoken: limited.accessibilityTask)
            }
            if let state = input.visibleState {
                compactRunsGroup(state)
            } else if let words = input.visibleActualWords {
                missing(words)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(input.accessibilityRuns ?? "")
                    .accessibilityIdentifier(CricketChaseAccessibilityID10868.runs)
            }
            if let balls = limited.balls {
                ballsGroup(balls, limited: limited)
            }
            if let rates = limited.rates {
                ratesGroup(rates, limited: limited)
            }
            if let state = input.visibleState {
                wicketsGroup(state)
                CricketChaseWrappedText10868(text: state.reportDetail, font: .caption2, color: DS.textSecondary)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(input.accessibilityReport ?? "")
                    .accessibilityIdentifier(CricketChaseAccessibilityID10868.report)
            }
        }
    }

    private func taskGroup(_ task: CricketChaseTask10868, spoken: String?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            CricketChaseWrappedText10868(text: task.label, font: .caption, color: DS.textSecondary)
            switch task.reading {
            case .reported(let lead, let connective, let trail, let detail):
                CricketChasePairLayout10868(spacing: 16, equalColumns: false, forceStack: stacks) {
                    taskPart(lead, connective: nil)
                    taskPart(trail, connective: connective)
                }
                if let detail {
                    CricketChaseWrappedText10868(text: detail, font: .caption2, color: DS.textSecondary)
                }
            case .unavailable(let words):
                missing(words)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken ?? "")
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.task)
    }

    /// One side of the pair: the owner's connective leads the trailing
    /// figure on its baseline, so a stacked pair still reads in order.
    private func taskPart(_ part: CricketChaseTaskPart10868, connective: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            switch part {
            case .reported(let text, let caption):
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let connective {
                        Text(connective)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize()
                    }
                    Text(text)
                        .font(.system(size: taskSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                }
                CricketChaseWrappedText10868(text: caption, font: .subheadline, color: DS.textSecondary)
            case .unknown(let words):
                if let connective {
                    CricketChaseWrappedText10868(text: connective, font: .subheadline, color: DS.textSecondary)
                }
                missing(words)
            }
        }
    }

    /// The same runs, target, rail and qualifier as the unlimited card, at
    /// label size: the task pair above carries the large figures.
    private func compactRunsGroup(_ state: CricketChaseState10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let context = state.context {
                CricketChaseWrappedText10868(text: context, font: .caption, color: DS.textSecondary)
            }
            CricketChasePairLayout10868(spacing: 12, equalColumns: false, forceStack: stacks) {
                compactQuantity(label: state.battingSubject, quantity: state.runs, caption: state.runsCaption, color: runsTint)
                compactQuantity(
                    label: CricketChaseInput10868.targetLabel,
                    quantity: state.target,
                    caption: state.targetCaption,
                    color: DS.textPrimary
                )
            }
            if let geometry = input.railGeometry {
                CricketChaseRail10868(geometry: geometry, tint: runsTint, height: railHeight)
            }
            if input.showsRailNotDrawn {
                CricketChaseWrappedText10868(text: CricketChaseInput10868.railNotDrawn, font: .caption, color: DS.textSecondary)
            }
            CricketChaseWrappedText10868(text: CricketChaseInput10868.targetQualifier, font: .caption, color: DS.textSecondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityRuns ?? "")
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.runs)
    }

    private func compactQuantity(
        label: String,
        quantity: CricketChaseQuantity10868,
        caption: String,
        color: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            CricketChaseWrappedText10868(text: label, font: .caption, color: DS.textSecondary)
            switch quantity {
            case .reported(let text, _):
                Text(text)
                    .font(.title3.bold())
                    .monospacedDigit()
                    .foregroundStyle(color)
                    .fixedSize()
                CricketChaseWrappedText10868(text: caption, font: .caption, color: DS.textSecondary)
            case .unknown(let words):
                CricketChaseWrappedText10868(text: words, font: .subheadline.weight(.semibold), color: DS.textSecondary)
            }
        }
    }

    private func ballsGroup(_ balls: CricketChaseBalls10868, limited: CricketChaseLimitedOversVisible10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            CricketChasePairLayout10868(spacing: 12, equalColumns: false, forceStack: stacks) {
                CricketChaseWrappedText10868(text: balls.label, font: .caption, color: DS.textSecondary)
                switch balls.reading {
                case .reported(let text, _, _, _):
                    CricketChaseWrappedText10868(text: text, font: .subheadline.bold(), color: DS.textPrimary)
                case .unavailable(let words):
                    CricketChaseWrappedText10868(text: words, font: .subheadline, color: DS.textSecondary)
                }
            }
            if let fraction = limited.ballFraction {
                CricketChaseBallRail10868(fraction: fraction, height: ballRailHeight)
            }
            if limited.showsBallsNotDrawn {
                CricketChaseWrappedText10868(text: balls.notDrawn, font: .caption, color: DS.textSecondary)
            }
            if case .reported(_, _, _, let detail?) = balls.reading {
                CricketChaseWrappedText10868(text: detail, font: .caption2, color: DS.textSecondary)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(limited.accessibilityBalls ?? "")
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.balls)
    }

    /// Achieved, then required, on one shared owner ceiling: equal track
    /// widths make the two bars directly comparable.
    private func ratesGroup(_ rates: CricketChaseRates10868, limited: CricketChaseLimitedOversVisible10868) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if let achieved = rates.achieved {
                rateRow(achieved, tint: runsTint, notDrawn: rates.notDrawn, limited: limited)
            }
            if let requiredRate = rates.required {
                rateRow(requiredRate, tint: DS.textPrimary, notDrawn: rates.notDrawn, limited: limited)
            }
            if let scale = rates.scaleText {
                CricketChaseWrappedText10868(text: scale, font: .caption2, color: DS.textSecondary)
            }
            CricketChaseWrappedText10868(text: CricketChaseRates10868.qualifier, font: .caption, color: DS.textSecondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(limited.accessibilityRates ?? "")
        .accessibilityIdentifier(CricketChaseAccessibilityID10868.rates)
    }

    private func rateRow(
        _ row: CricketChaseRateRow10868,
        tint: Color,
        notDrawn: String,
        limited: CricketChaseLimitedOversVisible10868
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            CricketChasePairLayout10868(spacing: 12, equalColumns: false, forceStack: stacks) {
                CricketChaseWrappedText10868(text: row.label, font: .caption, color: DS.textSecondary)
                switch row.reading {
                case .reported(let text, _, _):
                    Text(text)
                        .font(.subheadline.bold())
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                case .unavailable(let words), .withheld(let words):
                    CricketChaseWrappedText10868(text: words, font: .subheadline, color: DS.textSecondary)
                }
            }
            if let fraction = limited.rateFraction(row) {
                CricketChaseRateBar10868(fraction: fraction, tint: tint, height: rateBarHeight)
            }
            if limited.showsRateNotDrawn(row) {
                CricketChaseWrappedText10868(text: notDrawn, font: .caption, color: DS.textSecondary)
            }
            if case .reported(_, _, let detail?) = row.reading {
                CricketChaseWrappedText10868(text: detail, font: .caption2, color: DS.textSecondary)
            }
        }
    }

    // MARK: Details

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails) {
            Button {
                action.perform(onDetails: onDetails)
            } label: {
                HStack {
                    Text(input.detailsText)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CricketChaseAccessibilityID10868.details)
        }
    }
}

// MARK: - Limited-over chase: time budget and scoring rates

// #10868 (cricket-t20) — an optional, default-nil extension of the same chase
// card for a limited-over chase. With it the card shows the owner's
// phase-appropriate task pair large ("63 runs needed from 30 balls left" in
// play, "252 runs scored with 9 balls to spare" at the final), the actual
// runs and target compactly above the existing run rail, a visually distinct
// legal-ball rail from zero to the owner's explicit limit, and the achieved
// and required scoring rates as like-for-like bars on one shared owner
// ceiling. Without it the card is the unlimited-innings (Test) card,
// unchanged: no ball limit, task pair or rate is invented for it.
//
// The context is not a field of the chase input — the input's field set is a
// tested contract — so the host passes it beside the input and the input's
// phase gates it. Before play nothing here is drawn or spoken, even when
// supplied. In play the final pair never appears; at the final the live task
// and the required rate never appear, so no remaining requirement reads as if
// play continued.
//
// Every count, figure, caption, connective, label, provenance and absence
// word arrives resolved by the owner and is shown verbatim. This layer never
// computes runs needed, balls left or to spare, overs, wickets left, a rate,
// a win threshold, a forecast or a result, never parses an overs string
// ("18.3" is 111 legal balls only because the owner says so), never assumes a
// 120- or 300-ball limit, and never formats or rounds. The ball counts and
// rates only place geometry: a count that is negative, fractional,
// non-finite or beyond a non-positive or non-finite limit, or a rate that is
// negative, non-finite or beyond the shared ceiling, draws no bar — never a
// clamped 0% or 100% — and keeps the owner's words plus its supplied
// not-drawn reason. That is geometry validation, not source admission. A rate
// is neither a projection nor a probability. A failed chance leaves these
// standing, a failed score leaves them standing, and a missing context
// invents nothing from the other side's score.
//
// Presentation only, from the approved design: `T20Match.tsx` ChaseCard with
// `t20Match.css`. Its replay evidence helper (`t20Evidence.ts`) — trade
// selection, currentness, baseline election and the ball and rate arithmetic
// — is NOT ported, and neither is its fixed `/ 120` rail or `/ 16` scale.
//
// Host binding still owed — not available at this base: typed, independently
// qualified legal-ball, task, finish and rate state with units and
// provenance through the existing cricket state owner (the frozen score tuple
// carries none). T20-CHASE-REUSE-NATIVE-BINDING-MAP.md names the gaps.

/// One side of a task pair.
nonisolated enum CricketChaseTaskPart10868: Equatable {
    /// The owner's whole figure and its caption: ("63", "runs needed"),
    /// ("9", "balls to spare").
    case reported(text: String, caption: String)
    /// Unknown — the owner's words, never zero.
    case unknown(String)
}

nonisolated enum CricketChaseTaskReading10868: Equatable {
    /// The owner's pair joined by its own connective ("from", "with"), with
    /// the pair's provenance; nil when the score report line carries it.
    case reported(
        lead: CricketChaseTaskPart10868,
        connective: String,
        trail: CricketChaseTaskPart10868,
        detail: String?
    )
    /// No admitted task — the owner's words.
    case unavailable(String)
}

/// The phase's large task pair.
nonisolated struct CricketChaseTask10868: Equatable {
    /// "Chase · 15 overs", "The chase, completed".
    let label: String
    let reading: CricketChaseTaskReading10868
}

nonisolated enum CricketChaseBallsReading10868: Equatable {
    /// The owner's words ("90 of 120"), the independently admitted legal
    /// balls used and the explicit limit that place the rail, and their
    /// provenance (nil when the score report line carries it).
    case reported(text: String, used: Double, limit: Double, detail: String?)
    /// No admitted count — the owner's words, never zero.
    case unavailable(String)
}

/// The legal-ball budget.
nonisolated struct CricketChaseBalls10868: Equatable {
    /// "Legal balls used".
    let label: String
    let reading: CricketChaseBallsReading10868
    /// The owner's reason when reported counts cannot be drawn ("Ball
    /// progress not drawn").
    let notDrawn: String
}

nonisolated enum CricketChaseRateReading10868: Equatable {
    /// The owner's figure ("12.47"), the number that places the bar, and its
    /// provenance (nil when the score report line carries it).
    case reported(text: String, value: Double, detail: String?)
    /// No admitted rate — the owner's words, never zero.
    case unavailable(String)
    /// A rate exists but is not admitted here. It carries no value.
    case withheld(String)
}

/// One labelled rate row; the label carries the unit.
nonisolated struct CricketChaseRateRow10868: Equatable {
    /// "Runs per over so far", "Needed from here, runs per over".
    let label: String
    let reading: CricketChaseRateReading10868
}

nonisolated struct CricketChaseRates10868: Equatable {
    /// One explicit, zero-based ceiling both bars share, in the rates' unit.
    let ceiling: Double
    /// The owner's words for the shared scale; nil draws none.
    let scaleText: String?
    /// The achieved rate; nil draws no row.
    let achieved: CricketChaseRateRow10868?
    /// The required rate from here, in play only — hidden at the final even
    /// when supplied. Nil draws no row.
    let required: CricketChaseRateRow10868?
    /// The owner's reason when a reported rate cannot be drawn.
    let notDrawn: String

    static let qualifier = "Scoring rates are measured in runs per over. They are not projections or chances"
}

/// The optional limited-over context, passed beside the chase input.
nonisolated struct CricketChaseLimitedOvers10868: Equatable {
    /// The live task ("63 runs needed from 30 balls left"), in play only.
    let task: CricketChaseTask10868?
    /// The completed pair ("252 runs scored with 9 balls to spare"), at the
    /// final only.
    let finish: CricketChaseTask10868?
    let balls: CricketChaseBalls10868?
    let rates: CricketChaseRates10868?
}

/// What the input's phase admits of a limited-over context. Nil before play
/// or without a context: the card is then the unlimited-innings card.
nonisolated struct CricketChaseLimitedOversVisible10868: Equatable {
    /// The live task in play; the completed pair at the final.
    let task: CricketChaseTask10868?
    let balls: CricketChaseBalls10868?
    /// Without the required row at the final; nil when no row remains.
    let rates: CricketChaseRates10868?

    init?(phase: CricketChasePhase10868, context: CricketChaseLimitedOvers10868?) {
        guard let context else { return nil }
        let requiredRow: CricketChaseRateRow10868?
        switch phase {
        case .before:
            return nil
        case .during:
            task = context.task
            requiredRow = context.rates?.required
        case .final:
            task = context.finish
            requiredRow = nil
        }
        balls = context.balls
        if let rates = context.rates, rates.achieved != nil || requiredRow != nil {
            self.rates = CricketChaseRates10868(
                ceiling: rates.ceiling,
                scaleText: rates.scaleText,
                achieved: rates.achieved,
                required: requiredRow,
                notDrawn: rates.notDrawn
            )
        } else {
            self.rates = nil
        }
    }

    // MARK: Geometry

    /// Nil unless reported counts place on the owner's limit.
    var ballFraction: Double? {
        guard case .reported(_, let used, let limit, _) = balls?.reading else { return nil }
        return CricketChaseLimitedOversGeometry10868.balls(used: used, limit: limit)
    }

    /// Reported counts that cannot be drawn say so; unavailable counts keep
    /// only their own words.
    var showsBallsNotDrawn: Bool {
        guard case .reported = balls?.reading else { return false }
        return ballFraction == nil
    }

    /// The visible rows, achieved first.
    var rateRows: [CricketChaseRateRow10868] {
        [rates?.achieved, rates?.required].compactMap { $0 }
    }

    /// Nil unless a reported rate places on the shared ceiling.
    func rateFraction(_ row: CricketChaseRateRow10868) -> Double? {
        guard let rates, case .reported(_, let value, _) = row.reading else { return nil }
        return CricketChaseLimitedOversGeometry10868.rate(value, ceiling: rates.ceiling)
    }

    func showsRateNotDrawn(_ row: CricketChaseRateRow10868) -> Bool {
        guard rates != nil, case .reported = row.reading else { return false }
        return rateFraction(row) == nil
    }

    // MARK: VoiceOver

    var accessibilityTask: String? {
        guard let task else { return nil }
        switch task.reading {
        case .reported(let lead, let connective, let trail, let detail):
            let pair = "\(task.label): \(Self.spoken(lead)) \(connective) \(Self.spoken(trail))"
            return ([pair, detail].compactMap { $0 }).joined(separator: ". ")
        case .unavailable(let words):
            return "\(task.label): \(words)"
        }
    }

    var accessibilityBalls: String? {
        guard let balls else { return nil }
        switch balls.reading {
        case .reported(let text, _, _, let detail):
            var parts = ["\(balls.label): \(text)"]
            if let detail { parts.append(detail) }
            if showsBallsNotDrawn { parts.append(balls.notDrawn) }
            return parts.joined(separator: ". ")
        case .unavailable(let words):
            return "\(balls.label): \(words)"
        }
    }

    /// Each row with its own figure and provenance or words, a bar that could
    /// not be drawn, the shared scale and the not-a-projection qualifier.
    var accessibilityRates: String? {
        guard let rates else { return nil }
        var parts: [String] = []
        for row in rateRows {
            parts.append("\(row.label): \(Self.spoken(row.reading))")
            if showsRateNotDrawn(row) { parts.append(rates.notDrawn) }
        }
        if let scale = rates.scaleText { parts.append(scale) }
        parts.append(CricketChaseRates10868.qualifier)
        return parts.joined(separator: ". ")
    }

    private static func spoken(_ part: CricketChaseTaskPart10868) -> String {
        switch part {
        case .reported(let text, let caption): "\(text) \(caption)"
        case .unknown(let words): words
        }
    }

    private static func spoken(_ reading: CricketChaseRateReading10868) -> String {
        switch reading {
        case .reported(let text, _, let detail?): "\(text), \(detail)"
        case .reported(let text, _, nil): text
        case .unavailable(let words), .withheld(let words): words
        }
    }
}

nonisolated enum CricketChaseLimitedOversGeometry10868 {
    /// Legal balls used as a fraction of the owner's explicit limit. Both
    /// are whole counts; used is from zero to the limit and the limit is
    /// positive. Anything else — including a decimal-overs value passed as a
    /// count — draws nothing, never a clamped end.
    static func balls(used: Double, limit: Double) -> Double? {
        guard used.isFinite, limit.isFinite, used >= 0, limit > 0, used <= limit,
              used.truncatingRemainder(dividingBy: 1) == 0,
              limit.truncatingRemainder(dividingBy: 1) == 0 else { return nil }
        return used / limit
    }

    /// A rate as a fraction of the one shared, zero-based ceiling. No row is
    /// scaled on its own, and a rate beyond the ceiling draws nothing.
    static func rate(_ value: Double, ceiling: Double) -> Double? {
        guard value.isFinite, ceiling.isFinite, value >= 0, ceiling > 0, value <= ceiling else { return nil }
        return value / ceiling
    }
}

/// Legal balls used from zero to the owner's limit: a neutral fill with
/// solid end marks at zero and the limit, distinct from the run rail's dashed
/// target. Decorative — the owner's words carry the counts.
private struct CricketChaseBallRail10868: View {
    let fraction: Double
    let height: CGFloat

    private let overhang: CGFloat = 3
    private let markWidth: CGFloat = 2

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let fillWidth = CricketChaseGeometry10868.x(fraction, width: width, inset: 0)
            let startX = CricketChaseGeometry10868.x(0, width: width, inset: markWidth / 2)
            let endX = CricketChaseGeometry10868.x(1, width: width, inset: markWidth / 2)
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(DS.trackBg)
                    .frame(width: width, height: height)
                    .offset(y: overhang)
                RoundedRectangle(cornerRadius: 2)
                    .fill(DS.textSecondary)
                    .frame(width: fillWidth, height: height)
                    .offset(y: overhang)
                Path { path in
                    for x in [startX, endX] {
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: height + 2 * overhang))
                    }
                }
                .stroke(DS.textPrimary, lineWidth: markWidth)
            }
        }
        .frame(maxWidth: .infinity, minHeight: height + 2 * overhang, maxHeight: height + 2 * overhang)
        .accessibilityHidden(true)
    }
}

/// One rate's bar on the shared ceiling's full-width track. Decorative.
private struct CricketChaseRateBar10868: View {
    let fraction: Double
    let tint: Color
    let height: CGFloat

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 2).fill(DS.trackBg)
                RoundedRectangle(cornerRadius: 2)
                    .fill(tint)
                    .frame(width: CricketChaseGeometry10868.x(fraction, width: width, inset: 0))
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }
}

// MARK: - Survival: "Can they hold on?"

// #10868 — the cricket-live survival card, live play only. Two equally
// prominent labelled chance figures — the owner's pregame reading and its
// separately admitted recorded or current reading — sit above the owner's
// ordered checkpoint tiles. Each tile pairs one reported score checkpoint
// (its label and overs, the wickets as shapes, the owner's wicket words and
// the report's own provenance) with a separately recorded chance for the
// same original and that reading's own bar provenance.
//
// Wickets and chances are separate facts with separate clocks. A wicket count
// never yields a chance and a chance never yields wickets: the leaf derives
// neither, never complements or normalizes, and never collapses a report
// clock into a bar clock. A failed chance leaves the tile's actuals standing
// and failed actuals leave its chance standing; a real 0% is a value. The
// headline comparison is the owner's own admitted reading, never the last
// non-empty tile. Outside live play the card draws nothing and every spoken
// helper is empty, even when later checkpoints or readings are supplied: there
// is no before or final survival variant, and the host should omit the card.
//
// Presentation only, from the approved design: `CricketLive.tsx` SurvivalCard
// with `cricketLive.css`. The historical native `CL186OutlookView` play branch
// is a visual reference only; its model, evidence loader, clock, cutoff,
// currentness and chance pipeline are NOT ported, and neither is its implicit
// "10 − wickets" arithmetic.
//
// It reuses the chase leaf's reading, figure, missing-word, wicket-mark,
// wrapped-text and pair layout UI. The chase input is unchanged: the survival
// card has its own input, so no target or runs field is faked.
//
// Every label, figure, wicket position and word, provenance line, identity
// and reference arrives resolved by the owner and is shown verbatim, in the
// owner's order, without a cap. Selection, Details, held updates, ranking,
// reader placement, Back and focus stay with the host: the view keeps no
// state, no sheet and no subscription and runs no animation.
//
// Every checkpoint reports on the same draw/tie original, so a canonical
// binding gives them one shared original reference. A tap or Details hands
// back a target pairing the owner's exact checkpoint id with that original;
// the id alone tells checkpoints apart. The leaf derives no app id, time or
// ticker and never invents a per-checkpoint outcome.
//
// Host binding still owed — not available at this base: proved membership of
// the draw/tie original, a canonical identity and optional exact reference
// per checkpoint (none is retained), admitted pregame and recorded/current
// readings, independently qualified score reports with wicket states, each
// checkpoint's separately admitted chance and bar provenance, and
// local-calendar words. CRICKET-SURVIVAL-NATIVE-BINDING-MAP.md names the gaps.

/// One reported score checkpoint's actuals, admitted independently of any
/// chance.
nonisolated struct CricketSurvivalReport10868: Equatable {
    /// The owner's ordered wicket positions; the owner owns the count. Empty
    /// draws no marks.
    let wickets: [CricketChaseWicket10868]
    /// "6 wickets left", "Wickets unknown".
    let wicketsText: String
    /// The score report's own provenance and qualifiers ("Score report
    /// published 2:11 AM PDT, Oct 13 · not the exact ball time").
    let reportDetail: String
}

nonisolated enum CricketSurvivalActual10868: Equatable {
    case reported(CricketSurvivalReport10868)
    /// No qualified report for this checkpoint — the owner's words.
    case unavailable(String)
}

/// One owner checkpoint tile.
nonisolated struct CricketSurvivalCheckpoint10868: Equatable {
    /// The owner's opaque, stable identity. Empty is no identity.
    let id: String
    /// The owner's canonical reference to the original this checkpoint
    /// reports on — shared by every checkpoint of one original; nil when none
    /// is safe. Never parsed.
    let ref: CricketChaseRef10868?
    /// The owner's full checkpoint label with its overs ("Day 5 · 64 overs").
    let label: String
    let actual: CricketSurvivalActual10868
    /// "Recorded draw / tie".
    let chanceLabel: String
    /// The separately recorded chance with its own bar provenance, or the
    /// owner's unavailable/withheld words.
    let chance: CricketChaseReading10868

    var report: CricketSurvivalReport10868? {
        guard case .reported(let report) = actual else { return nil }
        return report
    }

    var actualWords: String? {
        guard case .unavailable(let words) = actual else { return nil }
        return words
    }
}

nonisolated enum CricketSurvivalSelection10868: Equatable {
    case none
    case checkpoint(CricketSurvivalCheckpoint10868)
    /// The selected id does not resolve to exactly one visible checkpoint.
    case unavailable(String)

    var checkpoint: CricketSurvivalCheckpoint10868? {
        if case .checkpoint(let checkpoint) = self { return checkpoint }
        return nil
    }
}

/// What a tile or Details hands back: the owner's exact checkpoint id and
/// the canonical original it reports on, both unchanged. Two checkpoints of
/// one original are two targets.
nonisolated struct CricketSurvivalTarget10868: Hashable {
    let checkpointID: String
    let original: CricketChaseRef10868
}

nonisolated enum CricketSurvivalAction10868: Equatable {
    case select(CricketSurvivalTarget10868)
    case details(CricketSurvivalTarget10868)

    func perform(
        onSelect: ((CricketSurvivalTarget10868) -> Void)?,
        onDetails: ((CricketSurvivalTarget10868) -> Void)?
    ) {
        switch self {
        case .select(let target): onSelect?(target)
        case .details(let target): onDetails?(target)
        }
    }
}

nonisolated struct CricketSurvivalInput10868: Equatable {
    /// The owner's explicit lifecycle admission. The card shows during play
    /// only.
    let phase: CricketChasePhase10868
    /// The original's subject line ("Draw / tie · original market").
    let subject: String
    /// "Can they hold on?".
    let title: String
    /// "Pregame".
    let pregameLabel: String
    let pregame: CricketChaseReading10868
    /// "Recorded draw / tie chance", "Current draw / tie chance". The owner
    /// alone decides which word its reading has earned.
    let comparisonLabel: String
    /// The owner's separately admitted headline reading — never the last
    /// tile's.
    let comparison: CricketChaseReading10868
    /// The spoken name of the checkpoint group ("Reported wickets remaining
    /// and separately timed draw or tie probabilities").
    let checkpointsLabel: String
    /// Every checkpoint in the owner's order — never reordered, filtered or
    /// capped.
    let checkpoints: [CricketSurvivalCheckpoint10868]
    let selectedCheckpointID: String?
    /// Verbatim lines beneath the tiles.
    let notes: [String]

    static let selectedTag = "Selected"
    static let selectionUnavailable = "Selected checkpoint unavailable in this update."
    static let detailsTitle = "Details"
    static let selectHint = "Selects this checkpoint"

    // MARK: Lifecycle gating

    var isShown: Bool { phase == .during }

    var visiblePregame: CricketChaseReading10868? { isShown ? pregame : nil }

    var visibleComparison: CricketChaseReading10868? { isShown ? comparison : nil }

    var visibleCheckpoints: [CricketSurvivalCheckpoint10868] { isShown ? checkpoints : [] }

    var visibleNotes: [String] { isShown ? notes : [] }

    // MARK: Identity

    private static func repeated<T: Hashable>(_ values: [T]) -> Set<T> {
        var seen = Set<T>()
        var repeated = Set<T>()
        for value in values where !seen.insert(value).inserted { repeated.insert(value) }
        return repeated
    }

    /// Ids carried more than once. Such tiles get no action and cannot be
    /// selected; every one of them stays on screen.
    var duplicateCheckpointIDs: Set<String> { Self.repeated(visibleCheckpoints.map(\.id)) }

    /// The card shows one original. When the visible checkpoints carry
    /// different usable originals, no tile can be trusted to name it, so
    /// every tile is static. An absent or partial original disagrees with
    /// nothing; only its own tile is static.
    var hasInconsistentOriginals: Bool { Set(visibleCheckpoints.compactMap { Self.usable($0.ref) }).count > 1 }

    /// A supplied original with every part present; anything less is absent.
    /// Checked for emptiness only, never parsed.
    private static func usable(_ ref: CricketChaseRef10868?) -> CricketChaseRef10868? {
        guard let ref, !ref.event.isEmpty, !ref.market.isEmpty, !ref.outcome.isEmpty else { return nil }
        return ref
    }

    /// The exact target a tile may hand back: a checkpoint of this update
    /// with a non-empty id carried once and a usable original that agrees
    /// with every other tile's. A shared original is expected; the id keeps
    /// each target distinct.
    func actionTarget(_ checkpoint: CricketSurvivalCheckpoint10868) -> CricketSurvivalTarget10868? {
        guard isShown, !checkpoint.id.isEmpty, !duplicateCheckpointIDs.contains(checkpoint.id),
              visibleCheckpoints.contains(checkpoint), !hasInconsistentOriginals,
              let original = Self.usable(checkpoint.ref) else { return nil }
        return CricketSurvivalTarget10868(checkpointID: checkpoint.id, original: original)
    }

    // MARK: Selection

    /// Exact id only. A missing, empty or duplicated id selects nothing and
    /// no neighbour; every tile stays listed.
    var selection: CricketSurvivalSelection10868 {
        guard isShown, let selectedCheckpointID else { return .none }
        let matches = visibleCheckpoints.filter { $0.id == selectedCheckpointID }
        guard !selectedCheckpointID.isEmpty, matches.count == 1, let match = matches.first else {
            return .unavailable(selectedCheckpointID)
        }
        return .checkpoint(match)
    }

    func isSelected(_ checkpoint: CricketSurvivalCheckpoint10868) -> Bool {
        guard let selected = selection.checkpoint else { return false }
        return selected.id == checkpoint.id && !duplicateCheckpointIDs.contains(checkpoint.id)
    }

    var selectionNotice: String? {
        if case .unavailable = selection { return Self.selectionUnavailable }
        return nil
    }

    // MARK: Actions

    func checkpointAction(_ checkpoint: CricketSurvivalCheckpoint10868, canSelect: Bool) -> CricketSurvivalAction10868? {
        guard canSelect, let target = actionTarget(checkpoint) else { return nil }
        return .select(target)
    }

    /// Details for the exact selected checkpoint only, when it has a safe
    /// target.
    func detailsAction(canOpenDetails: Bool) -> CricketSurvivalAction10868? {
        guard canOpenDetails, let checkpoint = selection.checkpoint, let target = actionTarget(checkpoint) else { return nil }
        return .details(target)
    }

    var detailsText: String? {
        guard let checkpoint = selection.checkpoint else { return nil }
        return "\(checkpoint.label) · \(Self.detailsTitle)"
    }

    /// A unique tile keeps its id-based identifier; a repeated id adds its
    /// position so two tiles never share one.
    func accessibilityID(at index: Int) -> String? {
        guard visibleCheckpoints.indices.contains(index) else { return nil }
        let id = visibleCheckpoints[index].id
        let base = CricketSurvivalAccessibilityID10868.checkpoint(id)
        return duplicateCheckpointIDs.contains(id) ? "\(base).\(index)" : base
    }

    // MARK: VoiceOver

    var accessibilityHeader: String? {
        isShown ? [subject, title].joined(separator: ". ") : nil
    }

    /// Pregame, then the recorded/current reading, each with its own
    /// provenance.
    var accessibilityChances: String? {
        guard let pregame = visiblePregame, let comparison = visibleComparison else { return nil }
        return "\(pregameLabel): \(Self.spoken(pregame)). \(comparisonLabel): \(Self.spoken(comparison))"
    }

    /// The tile in reading order: label, actuals or their words, report
    /// provenance, then the chance with its own provenance, then selection.
    /// Empty outside live play, whatever checkpoint is supplied.
    func accessibilityCheckpoint(_ checkpoint: CricketSurvivalCheckpoint10868) -> String {
        guard isShown else { return "" }
        var parts = [checkpoint.label]
        if let report = checkpoint.report {
            parts.append(report.wicketsText)
            parts.append(report.reportDetail)
        } else if let words = checkpoint.actualWords {
            parts.append(words)
        }
        parts.append("\(checkpoint.chanceLabel): \(Self.spoken(checkpoint.chance))")
        if isSelected(checkpoint) { parts.append(Self.selectedTag) }
        return parts.joined(separator: ". ")
    }

    var accessibilityNotes: String? {
        visibleNotes.isEmpty ? nil : visibleNotes.joined(separator: " ")
    }

    private static func spoken(_ reading: CricketChaseReading10868) -> String {
        switch reading {
        case .observed(let figure): "\(figure.text), \(figure.detail)"
        case .unavailable(let words), .withheld(let words): words
        }
    }
}

nonisolated enum CricketSurvivalGeometry10868 {
    /// Two equal columns only when every tile, measured at a column's width,
    /// keeps its whole width — figures, wicket marks and the widest word
    /// included. Otherwise one column at full width. A single tile, or an
    /// accessibility size, is one column. Nothing shrinks or truncates.
    static func columns(
        available: CGFloat?,
        spacing: CGFloat,
        count: Int,
        forceSingle: Bool,
        measure: (Int, CGFloat?) -> CGFloat
    ) -> Int {
        guard count > 1, !forceSingle else { return 1 }
        guard let available, available.isFinite else { return 2 }
        let column = CricketChaseGeometry10868.equalColumn(available: available, spacing: spacing)
        for index in 0..<count where measure(index, column) > column + 0.5 {
            return 1
        }
        return 2
    }

    /// Tile positions per row, in the owner's order; nothing is dropped.
    static func rows(count: Int, columns: Int) -> [[Int]] {
        guard count > 0 else { return [] }
        let step = columns < 1 ? 1 : columns
        return stride(from: 0, to: count, by: step).map { start in
            Array(start..<min(start + step, count))
        }
    }
}

/// The checkpoint tiles in rows of two while every tile keeps its whole
/// measured width, else one per row. Tiles in a row share its height.
struct CricketSurvivalTileGrid10868: Layout {
    var spacing: CGFloat
    var forceSingle: Bool

    private func columnCount(_ width: CGFloat?, _ subviews: Subviews) -> Int {
        CricketSurvivalGeometry10868.columns(
            available: width,
            spacing: spacing,
            count: subviews.count,
            forceSingle: forceSingle,
            measure: { index, proposal in
                subviews[index].sizeThatFits(ProposedViewSize(width: proposal, height: nil)).width
            }
        )
    }

    private func columnWidth(_ total: CGFloat, columns: Int) -> CGFloat {
        columns == 2 ? CricketChaseGeometry10868.equalColumn(available: total, spacing: spacing) : total
    }

    private func rowHeight(_ row: [Int], width: CGFloat, subviews: Subviews) -> CGFloat {
        var height: CGFloat = 0
        for index in row {
            height = max(height, subviews[index].sizeThatFits(ProposedViewSize(width: width, height: nil)).height)
        }
        return height
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let columns = columnCount(proposal.width, subviews)
        let total: CGFloat
        if let width = proposal.width {
            total = width
        } else {
            var widest: CGFloat = 0
            for subview in subviews { widest = max(widest, subview.sizeThatFits(.unspecified).width) }
            total = columns == 2 ? widest * 2 + spacing : widest
        }
        let width = columnWidth(total, columns: columns)
        let rows = CricketSurvivalGeometry10868.rows(count: subviews.count, columns: columns)
        var height: CGFloat = 0
        for (index, row) in rows.enumerated() {
            height += rowHeight(row, width: width, subviews: subviews) + (index > 0 ? spacing : 0)
        }
        return CGSize(width: total, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let columns = columnCount(bounds.width, subviews)
        let width = columnWidth(bounds.width, columns: columns)
        var y = bounds.minY
        for row in CricketSurvivalGeometry10868.rows(count: subviews.count, columns: columns) {
            let height = rowHeight(row, width: width, subviews: subviews)
            for (column, index) in row.enumerated() {
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

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum CricketSurvivalAccessibilityID10868 {
    static let header = "cricketSurvival10868.header"
    static let chances = "cricketSurvival10868.chances"
    static let checkpoints = "cricketSurvival10868.checkpoints"
    static let selectionNotice = "cricketSurvival10868.selectionNotice"
    static let notes = "cricketSurvival10868.notes"
    static let details = "cricketSurvival10868.details"

    static func checkpoint(_ id: String) -> String { "cricketSurvival10868.checkpoint.\(id)" }
}

struct CricketSurvivalPresentation10868: View {
    let input: CricketSurvivalInput10868
    /// The tint of a remaining wicket.
    let wicketTint: Color
    var onSelect: ((CricketSurvivalTarget10868) -> Void)? = nil
    var onDetails: ((CricketSurvivalTarget10868) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: two 26-point headline figures and 24-point
    /// checkpoint figures, scaled with text size.
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .title2) private var checkpointChanceSize: CGFloat = 24
    @ScaledMetric(relativeTo: .body) private var missingSize: CGFloat = 17
    @ScaledMetric(relativeTo: .caption) private var wicketHeight: CGFloat = 16
    @ScaledMetric(relativeTo: .caption2) private var wicketGlyphSize: CGFloat = 7

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var stacks: Bool { typeSize.isAccessibilitySize }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 16) {
                header
                chancePair
                selectionNotice
                checkpointGrid
                notes
                detailsButton
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Header and notes

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.subject)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            Text(input.title).font(.title3.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader ?? "")
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(CricketSurvivalAccessibilityID10868.header)
    }

    @ViewBuilder private var selectionNotice: some View {
        if let notice = input.selectionNotice {
            CricketChaseWrappedText10868(text: notice, font: .footnote, color: DS.textSecondary)
                .accessibilityIdentifier(CricketSurvivalAccessibilityID10868.selectionNotice)
        }
    }

    @ViewBuilder private var notes: some View {
        if !input.visibleNotes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.visibleNotes.enumerated()), id: \.offset) { _, note in
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityNotes ?? "")
            .accessibilityIdentifier(CricketSurvivalAccessibilityID10868.notes)
        }
    }

    // MARK: Chances

    /// Pregame keeps the leading slot; the owner's recorded/current reading
    /// sits beside it at the same size.
    private var chancePair: some View {
        CricketChasePairLayout10868(spacing: 16, equalColumns: true, forceStack: stacks) {
            if let pregame = input.visiblePregame {
                CricketChaseReadingSlot10868(
                    label: input.pregameLabel, reading: pregame, figureSize: chanceSize, missingSize: missingSize
                )
            }
            if let comparison = input.visibleComparison {
                CricketChaseReadingSlot10868(
                    label: input.comparisonLabel, reading: comparison, figureSize: chanceSize, missingSize: missingSize
                )
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityChances ?? "")
        .accessibilityIdentifier(CricketSurvivalAccessibilityID10868.chances)
    }

    // MARK: Checkpoints

    @ViewBuilder private var checkpointGrid: some View {
        if !input.visibleCheckpoints.isEmpty {
            CricketSurvivalTileGrid10868(spacing: 12, forceSingle: stacks) {
                ForEach(Array(input.visibleCheckpoints.enumerated()), id: \.offset) { index, checkpoint in
                    tile(checkpoint, index: index)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.checkpointsLabel)
            .accessibilityIdentifier(CricketSurvivalAccessibilityID10868.checkpoints)
        }
    }

    private func tile(_ checkpoint: CricketSurvivalCheckpoint10868, index: Int) -> some View {
        let selected = input.isSelected(checkpoint)
        let action = input.checkpointAction(checkpoint, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 8) {
                if selected {
                    Label(CricketSurvivalInput10868.selectedTag, systemImage: "checkmark")
                        .font(.caption.bold())
                        .foregroundStyle(DS.textPrimary)
                }
                CricketChaseWrappedText10868(text: checkpoint.label, font: .caption, color: DS.textSecondary)
                actualBlock(checkpoint)
                CricketChaseReadingSlot10868(
                    label: checkpoint.chanceLabel,
                    reading: checkpoint.chance,
                    figureSize: checkpointChanceSize,
                    missingSize: missingSize
                )
            }
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
            }
            .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .accessibilityLabel(input.accessibilityCheckpoint(checkpoint))
        .accessibilityHint(action == nil ? "" : CricketSurvivalInput10868.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(input.accessibilityID(at: index) ?? "")
    }

    /// The reported wickets as shapes, the owner's words and the report's
    /// own provenance — or the owner's words when no report is admitted.
    @ViewBuilder private func actualBlock(_ checkpoint: CricketSurvivalCheckpoint10868) -> some View {
        if let report = checkpoint.report {
            if !report.wickets.isEmpty {
                HStack(spacing: 3) {
                    ForEach(Array(report.wickets.enumerated()), id: \.offset) { _, wicket in
                        CricketChaseWicketMark10868(
                            state: wicket,
                            tint: wicketTint,
                            height: wicketHeight,
                            glyphFont: .system(size: wicketGlyphSize, weight: .semibold)
                        )
                    }
                }
            }
            CricketChaseWrappedText10868(text: report.wicketsText, font: .subheadline.bold(), color: DS.textPrimary)
            CricketChaseWrappedText10868(text: report.reportDetail, font: .caption2, color: DS.textSecondary)
        } else if let words = checkpoint.actualWords {
            CricketChaseMissingText10868(words: words, size: missingSize)
        }
    }

    // MARK: Details

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let text = input.detailsText {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text(text)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CricketSurvivalAccessibilityID10868.details)
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback and a safe
    /// target; otherwise the same content as one plain accessibility
    /// element.
    @ViewBuilder
    private func control<Content: View>(_ action: CricketSurvivalAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - Expectation shift: each checkpoint against pregame

// #10868 (cricket-t20) — the expectation-shift card, during play and at the
// final. Two equally prominent labelled figures — the owner's pregame reading
// and, in play, its separately admitted recorded or current reading; at the
// final, the independently reported match result — sit above one checkpoint
// row per owner score report. Every row shares one zero-to-100% probability
// scale: a hollow mark at the pregame reading, a filled mark at that row's
// separately recorded reading and only the segment between the two. Rows are
// not joined to each other: this is not a time trace, and it has no picker.
//
// The score report and the probability are separate facts with separate
// clocks, so each row keeps the report's words and provenance apart from the
// reading's own bar provenance. The headline reading is the owner's, never
// the last row's. A missing pregame leaves every row's reading standing, and
// a missing row reading leaves the pregame mark and that row's own words —
// never 0% and never a neighbour's value. A real 0 or 1 is a value. A
// position that is non-finite or outside zero to one draws no mark and no
// segment — never a clamped end — and keeps the owner's figure and its
// supplied not-drawn words. At the final the recorded/current reading is not
// shown, the historical rows stay as supplied and no finish row or 0%/100%
// point is added; an original grade appears only when the owner supplies it,
// under its own label, and is never read from the match result. Before play
// the card draws nothing and every spoken helper is empty, even when later
// rows and results are supplied.
//
// Presentation only, from the approved design: `T20Match.tsx` ShiftCard and
// WinContext with `t20Match.css`. Its replay evidence helper (`t20Evidence.ts`)
// — quote selection, baseline election and the fixed 340-unit SVG — is NOT
// ported. `MarketChanceMovementTrack10238` (per-market automatic scale,
// matrix Details) and the survival tiles are not reused for this plot.
//
// It reuses the chase leaf's figure, reading, missing-word, wrapped-text,
// pair layout and Details primitives. The chase input is unchanged: the shift
// card has its own input. Every label, figure, score, tick word, provenance
// line, identity and reference arrives resolved by the owner and is shown
// verbatim, in the owner's order, without a cap. The positions only place
// marks; this layer never formats, rounds, subtracts, complements or
// normalizes a probability, never parses an overs or score string and never
// elects a baseline, a latest reading or a result. Held updates, row
// membership, ranking, reader placement, Back and focus stay with the host:
// the view keeps no state and no subscription and runs no animation.
//
// Host binding still owed — not available at this base: canonical original
// identity and Details reference, an independently admitted pregame reading
// and position, the admitted headline reading, each checkpoint's qualified
// score report and separately recorded reading with bar provenance, the
// reported match result and any independently admitted original result.
// T20-SHIFT-REUSE-NATIVE-BINDING-MAP.md names the gaps.

/// One checkpoint's reported score, admitted independently of any chance.
nonisolated enum CricketChaseShiftScore10868: Equatable {
    /// The owner's score words ("170/3") with the report's own provenance.
    case reported(CricketChaseFigure10868)
    /// No qualified report for this checkpoint — the owner's words.
    case unavailable(String)
}

/// One owner checkpoint row.
nonisolated struct CricketChaseShiftRow10868: Equatable {
    /// The owner's opaque, stable identity. Empty is no identity.
    let id: String
    /// The owner's checkpoint label ("13.0 overs").
    let label: String
    let score: CricketChaseShiftScore10868
    /// The separately recorded reading with its own bar provenance, or the
    /// owner's unavailable/withheld words.
    let recorded: CricketChaseReading10868
    /// The probability, zero to one, that places the filled mark; nil draws
    /// none.
    let position: Double?
}

/// One owner tick on the shared scale.
nonisolated struct CricketChaseShiftTick10868: Equatable {
    /// Zero to one.
    let value: Double
    /// "50%".
    let words: String
}

/// The one zero-to-100% probability scale every row shares.
nonisolated struct CricketChaseShiftScale10868: Equatable {
    /// "Win chance".
    let label: String
    let ticks: [CricketChaseShiftTick10868]
}

/// The segment between a row's two marks, as positions on the shared scale.
nonisolated struct CricketChaseShiftSegment10868: Equatable {
    let lower: Double
    let upper: Double
}

/// Where a label sits in its band: leading x and line.
nonisolated struct CricketChaseShiftLabelPlacement10868: Equatable {
    let x: CGFloat
    let line: Int
}

/// A label band's full plan: where each label sits, the width offered to it
/// (measured with and placed with that same offer), the size it takes at
/// that offer, each line's top and the band's height.
nonisolated struct CricketChaseShiftLabelBandPlan10868: Equatable {
    let placements: [CricketChaseShiftLabelPlacement10868]
    let offers: [CGFloat]
    let sizes: [CGSize]
    let lineOffsets: [CGFloat]
    let height: CGFloat
}

nonisolated struct CricketChaseShiftInput10868: Equatable {
    /// The owner's explicit lifecycle admission. Hidden before play.
    let phase: CricketChasePhase10868
    /// The original's subject, in the owner's words, for Details.
    let subject: String
    /// "West Indies · expectation shift".
    let eyebrow: String
    /// The owner's phase heading ("How the chase changed").
    let title: String
    /// "Pregame" — the headline slot, the hollow key and each row.
    let pregameLabel: String
    let pregame: CricketChaseReading10868
    /// The probability, zero to one, that places every hollow mark; nil
    /// draws none.
    let pregamePosition: Double?
    /// "Recorded win chance", "Current win chance". Shown during play only.
    let comparisonLabel: String
    /// The owner's separately admitted headline reading — never the last
    /// row's. Shown during play only.
    let comparison: CricketChaseReading10868
    /// "Actual result". Shown at the final only.
    let resultLabel: String
    let matchResult: CricketChaseMatchResult10868
    /// "Original result". Shown at the final only, when supplied.
    let originalResultLabel: String
    /// Nil shows no original result; never read from the match result.
    let originalResult: CricketChaseContractResult10868?
    /// "Last trade before report" — the filled key and each row's reading.
    let recordedLabel: String
    /// The spoken name of the plot ("West Indies recorded win chances
    /// versus pregame at each captured score report").
    let checkpointsLabel: String
    let scale: CricketChaseShiftScale10868
    /// Every checkpoint in the owner's order — never reordered, filtered,
    /// interpolated or capped.
    let rows: [CricketChaseShiftRow10868]
    /// The owner's words when an observed pregame cannot be placed.
    let baselineNotDrawn: String
    /// The owner's words when an observed row reading cannot be placed.
    let rowNotDrawn: String
    /// Nil when no safe owner reference exists: no Details.
    let detailsRef: CricketChaseRef10868?
    /// Verbatim lines beneath the rows.
    let notes: [String]

    static let hollowMark = "Hollow mark"
    static let filledMark = "Filled mark"
    static let detailsTitle = "Details"

    // MARK: Lifecycle gating

    var isShown: Bool { phase != .before }

    var visiblePregame: CricketChaseReading10868? { isShown ? pregame : nil }

    /// During play only — at the final a settled price is not a chance.
    var visibleComparison: CricketChaseReading10868? { phase == .during ? comparison : nil }

    var visibleMatchResult: CricketChaseMatchResult10868? { phase == .final ? matchResult : nil }

    var visibleOriginalResult: CricketChaseContractResult10868? { phase == .final ? originalResult : nil }

    var visibleRows: [CricketChaseShiftRow10868] { isShown ? rows : [] }

    var visibleTicks: [CricketChaseShiftTick10868] {
        isShown ? scale.ticks.filter { CricketChaseShiftGeometry10868.position($0.value) != nil } : []
    }

    var visibleNotes: [String] { isShown ? notes : [] }

    // MARK: Geometry

    /// The hollow mark's position: an observed pregame that places.
    var baselinePosition: Double? {
        guard isShown, case .observed = pregame else { return nil }
        return CricketChaseShiftGeometry10868.position(pregamePosition)
    }

    var showsBaselineNotDrawn: Bool {
        guard isShown, case .observed = pregame else { return false }
        return baselinePosition == nil
    }

    /// A row's filled mark: its own observed reading that places.
    func rowPosition(_ row: CricketChaseShiftRow10868) -> Double? {
        guard isShown, case .observed = row.recorded else { return nil }
        return CricketChaseShiftGeometry10868.position(row.position)
    }

    func showsRowNotDrawn(_ row: CricketChaseShiftRow10868) -> Bool {
        guard isShown, case .observed = row.recorded else { return false }
        return rowPosition(row) == nil
    }

    /// Only this row's two marks; nothing joins one row to the next.
    func rowSegment(_ row: CricketChaseShiftRow10868) -> CricketChaseShiftSegment10868? {
        CricketChaseShiftGeometry10868.segment(from: baselinePosition, to: rowPosition(row))
    }

    // MARK: Action

    /// Details for the exact owner reference only, when the owner can open it.
    func detailsAction(canOpenDetails: Bool) -> CricketChaseAction10868? {
        guard isShown, canOpenDetails, let detailsRef else { return nil }
        return .details(detailsRef)
    }

    var detailsText: String { "\(subject) · \(Self.detailsTitle)" }

    /// A unique row keeps its id-based identifier; an empty or repeated id
    /// adds its position so two rows never share one.
    func accessibilityID(at index: Int) -> String? {
        guard visibleRows.indices.contains(index) else { return nil }
        let id = visibleRows[index].id
        let base = CricketChaseShiftAccessibilityID10868.row(id)
        let repeated = visibleRows.filter { $0.id == id }.count > 1
        return id.isEmpty || repeated ? "\(base).\(index)" : base
    }

    // MARK: VoiceOver

    var accessibilityHeader: String? {
        isShown ? Self.joined([eyebrow, title]) : nil
    }

    /// Pregame, then the recorded/current reading (during) or the reported
    /// match result and any original result (final), each with its own
    /// provenance.
    var accessibilityChances: String? {
        guard let pregame = visiblePregame else { return nil }
        var parts = ["\(pregameLabel): \(Self.spoken(pregame))"]
        if let comparison = visibleComparison {
            parts.append("\(comparisonLabel): \(Self.spoken(comparison))")
        }
        if let result = visibleMatchResult {
            parts.append("\(resultLabel): \(Self.spoken(result))")
        }
        if let original = visibleOriginalResult {
            parts.append("\(originalResultLabel): \(Self.spoken(original))")
        }
        return Self.joined(parts)
    }

    /// The plot's name, the mark key, the shared scale and a pregame that
    /// could not be placed.
    var accessibilityPlot: String? {
        guard isShown else { return nil }
        var parts = [
            checkpointsLabel,
            "\(Self.hollowMark): \(pregameLabel)",
            "\(Self.filledMark): \(recordedLabel)",
        ]
        let ticks = visibleTicks.map(\.words).filter { !$0.isEmpty }
        parts.append(ticks.isEmpty ? scale.label : "\(scale.label): \(ticks.joined(separator: ", "))")
        if showsBaselineNotDrawn { parts.append(baselineNotDrawn) }
        return Self.joined(parts)
    }

    /// The row in reading order: label, score words and report provenance,
    /// the recorded reading with its own provenance or words, a mark that
    /// could not be placed, then the pregame figure or its words. Empty
    /// before play, whatever row is supplied.
    func accessibilityRow(_ row: CricketChaseShiftRow10868) -> String {
        guard isShown else { return "" }
        var parts = [row.label]
        switch row.score {
        case .reported(let figure): parts.append(Self.spoken(figure))
        case .unavailable(let words): parts.append(words)
        }
        parts.append("\(recordedLabel): \(Self.spoken(row.recorded))")
        if showsRowNotDrawn(row) { parts.append(rowNotDrawn) }
        switch pregame {
        case .observed(let figure): parts.append("\(pregameLabel): \(figure.text)")
        case .unavailable(let words), .withheld(let words): parts.append("\(pregameLabel): \(words)")
        }
        return Self.joined(parts)
    }

    var accessibilityNotes: String? {
        visibleNotes.isEmpty ? nil : visibleNotes.joined(separator: " ")
    }

    /// Owner words joined in order; an empty supplied line adds no pause.
    private static func joined(_ parts: [String]) -> String {
        parts.filter { !$0.isEmpty }.joined(separator: ". ")
    }

    private static func spoken(_ figure: CricketChaseFigure10868) -> String {
        figure.detail.isEmpty ? figure.text : "\(figure.text), \(figure.detail)"
    }

    private static func spoken(_ reading: CricketChaseReading10868) -> String {
        switch reading {
        case .observed(let figure): spoken(figure)
        case .unavailable(let words), .withheld(let words): words
        }
    }

    private static func spoken(_ result: CricketChaseMatchResult10868) -> String {
        switch result {
        case .reported(let figure): spoken(figure)
        case .unavailable(let words): words
        }
    }

    private static func spoken(_ result: CricketChaseContractResult10868) -> String {
        switch result {
        case .graded(let figure): spoken(figure)
        case .unconfirmed(let words), .void(let words), .unavailable(let words): words
        }
    }
}

nonisolated enum CricketChaseShiftGeometry10868 {
    /// A probability on the shared scale. Zero and one are real values;
    /// missing, non-finite or out-of-range positions draw nothing — never a
    /// clamped end. The scale is fixed: no row widens or narrows it.
    static func position(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value >= 0, value <= 1 else { return nil }
        return value
    }

    /// The segment between one row's two marks; nil unless both place.
    /// Equal positions are a zero-length segment, never a missing one.
    static func segment(from baseline: Double?, to recorded: Double?) -> CricketChaseShiftSegment10868? {
        guard let baseline = position(baseline), let recorded = position(recorded) else { return nil }
        return CricketChaseShiftSegment10868(lower: min(baseline, recorded), upper: max(baseline, recorded))
    }

    /// Each label centred on its mark and kept inside the band, in the
    /// owner's order, on the first line where it overlaps no label already
    /// placed. Close or end-of-scale labels move down a line instead of
    /// colliding, leaving the band or shrinking.
    static func labelPlacements(
        centers: [CGFloat],
        widths: [CGFloat],
        available: CGFloat,
        spacing: CGFloat
    ) -> [CricketChaseShiftLabelPlacement10868] {
        let count = min(centers.count, widths.count)
        var lines: [[ClosedRange<CGFloat>]] = []
        var placements: [CricketChaseShiftLabelPlacement10868] = []
        for index in 0..<count {
            let width = max(0, min(widths[index], available))
            let x = min(max(0, centers[index] - width / 2), max(0, available - width))
            let span = x...(x + width)
            var line = 0
            while line < lines.count, lines[line].contains(where: {
                span.lowerBound < $0.upperBound + spacing && $0.lowerBound < span.upperBound + spacing
            }) {
                line += 1
            }
            if line == lines.count { lines.append([]) }
            lines[line].append(span)
            placements.append(CricketChaseShiftLabelPlacement10868(x: x, line: line))
        }
        return placements
    }

    /// The plan a label band draws with. Each label is offered its natural
    /// width or the band's, whichever is smaller, and measured AT that offer,
    /// so a label wider than the band wraps between words and its taller
    /// wrapped height sets its line's height. The same offer is kept for
    /// placement. `measure(index, nil)` is the label's natural size;
    /// `measure(index, width)` its size at that width. Nil centres (no
    /// trustworthy x) lead every label.
    static func labelBand(
        count: Int,
        centers: [CGFloat]?,
        available: CGFloat,
        spacing: CGFloat,
        lineSpacing: CGFloat,
        measure: (Int, CGFloat?) -> CGSize
    ) -> CricketChaseShiftLabelBandPlan10868 {
        let band = max(0, available)
        var offers: [CGFloat] = []
        var sizes: [CGSize] = []
        for index in 0..<max(0, count) {
            let offer = max(0, min(measure(index, nil).width, band))
            let fitted = measure(index, offer)
            offers.append(offer)
            sizes.append(CGSize(width: max(0, min(fitted.width, offer)), height: max(0, fitted.height)))
        }
        let placements = labelPlacements(
            centers: centers ?? sizes.map { $0.width / 2 },
            widths: sizes.map(\.width),
            available: band,
            spacing: spacing
        )
        let lineCount = (placements.map(\.line).max() ?? -1) + 1
        var lineHeights = Array(repeating: CGFloat(0), count: lineCount)
        for (index, placement) in placements.enumerated() {
            lineHeights[placement.line] = max(lineHeights[placement.line], sizes[index].height)
        }
        var offsets: [CGFloat] = []
        var y: CGFloat = 0
        for (line, height) in lineHeights.enumerated() {
            offsets.append(y)
            y += height + (line < lineCount - 1 ? lineSpacing : 0)
        }
        return CricketChaseShiftLabelBandPlan10868(
            placements: placements, offers: offers, sizes: sizes, lineOffsets: offsets, height: y
        )
    }
}

/// Labels placed at their marks' x on the shared scale — a row's recorded
/// figure, or the tick words — growing a line rather than colliding.
struct CricketChaseShiftLabelBand10868: Layout {
    /// Each subview's position on the shared scale, in subview order.
    var fractions: [Double]
    /// The mark inset the plot uses, so labels share its x.
    var inset: CGFloat
    var spacing: CGFloat
    var lineSpacing: CGFloat

    private func plan(width: CGFloat, subviews: Subviews) -> CricketChaseShiftLabelBandPlan10868 {
        // A mismatched count has no trustworthy x: every label leads and
        // takes its own line.
        let centers = fractions.count == subviews.count
            ? fractions.map { CricketChaseGeometry10868.x($0, width: width, inset: inset) }
            : nil
        return CricketChaseShiftGeometry10868.labelBand(
            count: subviews.count, centers: centers, available: width,
            spacing: spacing, lineSpacing: lineSpacing
        ) { index, offer in
            subviews[index].sizeThatFits(offer.map { ProposedViewSize(width: $0, height: nil) } ?? .unspecified)
        }
    }

    private func bandWidth(_ proposal: ProposedViewSize, _ subviews: Subviews) -> CGFloat {
        if let width = proposal.width, width.isFinite { return width }
        let widths = subviews.map { $0.sizeThatFits(.unspecified).width }
        return widths.reduce(0, +) + spacing * CGFloat(max(0, widths.count - 1))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let total = bandWidth(proposal, subviews)
        return CGSize(width: total, height: plan(width: total, subviews: subviews).height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let planned = plan(width: bounds.width, subviews: subviews)
        for (index, placement) in planned.placements.enumerated() {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + placement.x, y: bounds.minY + planned.lineOffsets[placement.line]),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: planned.offers[index], height: nil)
            )
        }
    }
}

/// One row's track on the shared scale: tick stubs, a faint track, the
/// segment between this row's two marks, the hollow pregame mark and the
/// filled recorded mark. The hollow ring is larger than the filled dot, so
/// equal positions read as a dot inside a ring. Decorative — the row's words
/// carry the meaning.
private struct CricketChaseShiftTrack10868: View {
    let ticks: [Double]
    let baseline: Double?
    let recorded: Double?
    let segment: CricketChaseShiftSegment10868?
    let tint: Color
    let height: CGFloat
    let ringRadius: CGFloat
    let dotRadius: CGFloat
    let inset: CGFloat

    private let lineWidth: CGFloat = 2

    var body: some View {
        Canvas { context, size in
            let midY = size.height / 2
            func x(_ fraction: Double) -> CGFloat {
                CricketChaseGeometry10868.x(fraction, width: size.width, inset: inset)
            }
            var stubs = Path()
            for tick in ticks {
                stubs.move(to: CGPoint(x: x(tick), y: 0))
                stubs.addLine(to: CGPoint(x: x(tick), y: size.height))
            }
            context.stroke(stubs, with: .color(DS.border), lineWidth: 1)
            var track = Path()
            track.move(to: CGPoint(x: x(0), y: midY))
            track.addLine(to: CGPoint(x: x(1), y: midY))
            context.stroke(track, with: .color(DS.border), lineWidth: 1)
            if let segment {
                var line = Path()
                line.move(to: CGPoint(x: x(segment.lower), y: midY))
                line.addLine(to: CGPoint(x: x(segment.upper), y: midY))
                context.stroke(line, with: .color(tint), lineWidth: lineWidth)
            }
            if let baseline {
                let ring = Path(ellipseIn: CGRect(
                    x: x(baseline) - ringRadius, y: midY - ringRadius, width: 2 * ringRadius, height: 2 * ringRadius
                ))
                context.fill(ring, with: .color(DS.cardBg))
                context.stroke(ring, with: .color(tint), lineWidth: lineWidth)
            }
            if let recorded {
                let dot = Path(ellipseIn: CGRect(
                    x: x(recorded) - dotRadius, y: midY - dotRadius, width: 2 * dotRadius, height: 2 * dotRadius
                ))
                context.fill(dot, with: .color(tint))
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }
}

/// A key glyph matching the track's hollow or filled mark.
private struct CricketChaseShiftKeyMark10868: View {
    let hollow: Bool
    let tint: Color
    let radius: CGFloat

    var body: some View {
        Group {
            if hollow {
                Circle().strokeBorder(tint, lineWidth: 2)
            } else {
                Circle().fill(tint)
            }
        }
        .frame(width: 2 * radius, height: 2 * radius)
        .accessibilityHidden(true)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum CricketChaseShiftAccessibilityID10868 {
    static let header = "cricketShift10868.header"
    static let chances = "cricketShift10868.chances"
    static let plot = "cricketShift10868.plot"
    static let key = "cricketShift10868.key"
    static let notes = "cricketShift10868.notes"
    static let details = "cricketShift10868.details"

    static func row(_ id: String) -> String { "cricketShift10868.row.\(id)" }
}

struct CricketChaseShiftPresentation10868: View {
    let input: CricketChaseShiftInput10868
    /// The chasing side's series tint for both marks and the segment.
    let tint: Color
    var onDetails: ((CricketChaseRef10868) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The same two 26-point headline figures as the chase card.
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var missingSize: CGFloat = 17
    /// The approved reference: 19-point bold row figures.
    @ScaledMetric(relativeTo: .title3) private var valueSize: CGFloat = 19
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var ringRadius: CGFloat = 7
    @ScaledMetric(relativeTo: .caption) private var dotRadius: CGFloat = 5
    @ScaledMetric(relativeTo: .caption) private var keyRadius: CGFloat = 5
    /// The approved wide reference keeps the plot near 440 points.
    @ScaledMetric(relativeTo: .body) private var plotMaxWidth: CGFloat = 440

    private var canOpenDetails: Bool { onDetails != nil }
    private var stacks: Bool { typeSize.isAccessibilitySize }
    /// End marks stay whole inside the track.
    private var inset: CGFloat { ringRadius + 2 }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 16) {
                header
                chancePair
                originalResult
                plot
                notes
                detailsButton
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Header and notes

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.eyebrow)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            Text(input.title).font(.title3.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader ?? "")
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(CricketChaseShiftAccessibilityID10868.header)
    }

    @ViewBuilder private var notes: some View {
        if !input.visibleNotes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.visibleNotes.enumerated()), id: \.offset) { _, note in
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityNotes ?? "")
            .accessibilityIdentifier(CricketChaseShiftAccessibilityID10868.notes)
        }
    }

    // MARK: Headline figures

    /// Pregame keeps the leading slot; the trailing slot is the recorded or
    /// current reading in play and the reported match result at the final,
    /// at the same size.
    private var chancePair: some View {
        CricketChasePairLayout10868(spacing: 16, equalColumns: true, forceStack: stacks) {
            if let pregame = input.visiblePregame {
                CricketChaseReadingSlot10868(
                    label: input.pregameLabel, reading: pregame, figureSize: chanceSize, missingSize: missingSize
                )
            }
            if let comparison = input.visibleComparison {
                CricketChaseReadingSlot10868(
                    label: input.comparisonLabel, reading: comparison, figureSize: chanceSize, missingSize: missingSize
                )
            } else if let result = input.visibleMatchResult {
                matchResult(result)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityChances ?? "")
        .accessibilityIdentifier(CricketChaseShiftAccessibilityID10868.chances)
    }

    /// The reported result at the figure size, wrapping between words so a
    /// long result keeps every word instead of leaving the card.
    private func matchResult(_ result: CricketChaseMatchResult10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            CricketChaseWrappedText10868(text: input.resultLabel, font: .caption, color: DS.textSecondary)
            switch result {
            case .reported(let figure):
                CricketChaseWrappedText10868(
                    text: figure.text, font: .system(size: chanceSize, weight: .bold), color: DS.textPrimary
                )
                detailText(figure.detail)
            case .unavailable(let words):
                CricketChaseMissingText10868(words: words, size: missingSize)
            }
        }
    }

    /// An owner-supplied original grade, under its own label, beneath the
    /// pair. Part of the chances element's spoken text.
    @ViewBuilder private var originalResult: some View {
        if let result = input.visibleOriginalResult {
            VStack(alignment: .leading, spacing: 2) {
                CricketChaseWrappedText10868(text: input.originalResultLabel, font: .caption, color: DS.textSecondary)
                switch result {
                case .graded(let figure):
                    CricketChaseWrappedText10868(text: figure.text, font: .subheadline.bold(), color: DS.textPrimary)
                    detailText(figure.detail)
                case .unconfirmed(let words), .void(let words), .unavailable(let words):
                    CricketChaseWrappedText10868(text: words, font: .subheadline, color: DS.textSecondary)
                }
            }
            .accessibilityHidden(true)
        }
    }

    @ViewBuilder private func detailText(_ detail: String) -> some View {
        if !detail.isEmpty {
            CricketChaseWrappedText10868(text: detail, font: .caption2, color: DS.textSecondary)
        }
    }

    // MARK: Plot

    private var tickPositions: [Double] { input.visibleTicks.map(\.value) }

    @ViewBuilder private var plot: some View {
        VStack(alignment: .leading, spacing: 14) {
            key
            ForEach(Array(input.visibleRows.enumerated()), id: \.offset) { index, row in
                rowView(row)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(input.accessibilityRow(row))
                    .accessibilityIdentifier(input.accessibilityID(at: index) ?? "")
            }
            axis
        }
        .frame(maxWidth: plotMaxWidth, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.checkpointsLabel)
        .accessibilityIdentifier(CricketChaseShiftAccessibilityID10868.plot)
    }

    /// The hollow/filled key and, when the pregame cannot be placed, the
    /// owner's words. Its spoken text also names the shared scale.
    private var key: some View {
        VStack(alignment: .leading, spacing: 4) {
            FlowLayout(spacing: 16) {
                keyItem(hollow: true, label: input.pregameLabel)
                keyItem(hollow: false, label: input.recordedLabel)
            }
            if input.showsBaselineNotDrawn {
                CricketChaseWrappedText10868(text: input.baselineNotDrawn, font: .caption, color: DS.textSecondary)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityPlot ?? "")
        .accessibilityIdentifier(CricketChaseShiftAccessibilityID10868.key)
    }

    private func keyItem(hollow: Bool, label: String) -> some View {
        HStack(alignment: .center, spacing: 6) {
            CricketChaseShiftKeyMark10868(hollow: hollow, tint: tint, radius: keyRadius)
            Text(label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Label and score words, the track, the recorded figure at its mark (or
    /// the owner's words), then the report and reading provenance.
    private func rowView(_ row: CricketChaseShiftRow10868) -> some View {
        let position = input.rowPosition(row)
        return VStack(alignment: .leading, spacing: 4) {
            FlowLayout(spacing: 8) {
                Text(row.label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                switch row.score {
                case .reported(let figure):
                    Text(figure.text)
                        .font(.subheadline.bold())
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                case .unavailable(let words):
                    Text(words)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            CricketChaseShiftTrack10868(
                ticks: tickPositions,
                baseline: input.baselinePosition,
                recorded: position,
                segment: input.rowSegment(row),
                tint: tint,
                height: trackHeight,
                ringRadius: ringRadius,
                dotRadius: dotRadius,
                inset: inset
            )
            switch row.recorded {
            case .observed(let figure):
                if let position {
                    CricketChaseShiftLabelBand10868(fractions: [position], inset: inset, spacing: 8, lineSpacing: 2) {
                        valueText(figure.text)
                    }
                } else {
                    valueText(figure.text)
                    CricketChaseWrappedText10868(text: input.rowNotDrawn, font: .caption, color: DS.textSecondary)
                }
            case .unavailable(let words), .withheld(let words):
                CricketChaseMissingText10868(words: words, size: missingSize)
            }
            if case .reported(let figure) = row.score {
                detailText(figure.detail)
            }
            if case .observed(let figure) = row.recorded {
                detailText(figure.detail)
            }
        }
    }

    private func valueText(_ text: String) -> some View {
        Text(text)
            .font(.system(size: valueSize, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(tint)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// The owner's tick words at their positions on the shared scale, under
    /// the scale label. Spoken through the key.
    @ViewBuilder private var axis: some View {
        VStack(alignment: .leading, spacing: 4) {
            if !input.visibleTicks.isEmpty {
                CricketChaseShiftLabelBand10868(fractions: tickPositions, inset: inset, spacing: 8, lineSpacing: 2) {
                    ForEach(Array(input.visibleTicks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.words)
                            .font(.caption)
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            CricketChaseWrappedText10868(text: input.scale.label, font: .caption, color: DS.textSecondary)
        }
        .accessibilityHidden(true)
    }

    // MARK: Details

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails) {
            Button {
                action.perform(onDetails: onDetails)
            } label: {
                HStack {
                    Text(input.detailsText)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CricketChaseShiftAccessibilityID10868.details)
        }
    }
}
