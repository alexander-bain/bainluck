import SwiftUI

// #10868 — "How the outlook changed": the cricket-live Changing expectations
// card. One row per original outcome contract, in the owner's order. Each row
// names its subject with the owner's directional point change beside it, then
// two equally prominent labelled chance figures — the owner's before reading
// ("Pregame") and comparison reading ("Recorded" or "Current") — then a slim
// track on the card's single common 0–100% chance scale carrying a hollow
// before mark and a filled comparison mark in the row's own shape, joined only
// when both are drawn.
//
// Every reading is its own independently admitted observation with its own
// bar boundary and provenance. Nothing here complements, inverts or normalizes
// a row, sums rows into a distribution, shares one clock across rows or treats
// separately timed readings as simultaneous: a pregame set summing to 104% is
// drawn as 48%, 47% and 9%. A missing or withheld reading keeps its labelled
// slot and the owner's words and draws no mark, connector or movement; the
// other reading of the row stays. Zero is a real place. A probability the
// scale cannot place draws no mark and says so — never clamped.
//
// Presentation only, extracted from the approved design:
// `CricketChanceShift.tsx` + `cricketMomentStream.css` (mounted by
// `CricketLive.tsx` as "Changing expectations"), with the 26-point scaled
// figure and adaptive stacking intent of the accepted
// `cricket-outlook-reading-20261026/native/CricketChanceShift.swift`. That
// reference's model, eligibility/cutoff/currentness code, change formatter,
// source loader and history/ranking pipeline are NOT ported.
//
// Every subject, shape, tint, identity, figure, provenance line, movement
// line, phase label, heading and note arrives resolved by the owner and is
// shown verbatim. This layer never formats or rounds a probability or a point
// change, never reads or converts a clock, never parses a title or ticker,
// never decides whether a reading may be called Recorded or Current, never
// sorts, filters or caps rows, and accepts no score, overs or wickets.
//
// Completed match ("Pregame expectations → result", the approved
// `CricketLifecycle.tsx` Expectations card + `cricketLifecycle.css`): only
// when the owner explicitly selects `.completed`, each original keeps its own
// pregame figure and hollow mark beside the owner-reported match outcome, and
// — separately, only if supplied — the independently admitted original
// contract grade, each with its own words and provenance. Completed mode
// ignores every comparison reading, filled mark, connector and movement, so a
// settlement-time 0% or 100% can never read as a final chance; comparison
// mode ignores every supplied finish. The mode is never inferred from which
// inputs are present, and no outcome or grade is derived from a score, a
// price, a title or the other.
//
// Selection, Details, held updates, disclosure, reader order and focus stay
// with the host: the view keeps no state, no sheet and no subscription and
// runs no animation, so reduced motion has nothing to stop. A row is a control
// only when the owner supplied both a callback and an exact, unique reference
// for it; otherwise it is static content and no tap is asked for.
//
// Host binding still owed — not available at this base. An owner must supply
// proved subject membership for the three original contracts, a canonical
// identity and Details reference per row (never a parsed ticker or title), an
// admitted pregame observation from its own history, an admitted recorded or
// current observation with currentness already applied, local-calendar
// provenance words and owner-qualified movement. CRICKET-OUTLOOK-NATIVE-
// BINDING-MAP.md names the gaps. Completed mode additionally needs the
// lifecycle admission that selects it, an independently admitted reported
// match outcome and, separately, an admitted original contract grade per
// original, each with its own source clock and owner words
// (CRICKET-FINAL-EXPECTATIONS-NATIVE-BINDING-MAP.md).

/// One admitted reading. `probability` places the mark on the 0–100% scale;
/// `text` is what the reader sees.
nonisolated struct CricketOutlookObservation10868: Equatable {
    /// 0...1. Anything else draws no mark and keeps the owner's text.
    let probability: Double
    /// The owner's whole figure ("48%", "<1%").
    let text: String
    /// Full provenance in the owner's local-calendar words, including the bar
    /// boundary and venue, never an exact trade or arrival clock.
    let detail: String
}

/// One phase reading for one row, each with its own words when absent.
nonisolated enum CricketOutlookReading10868: Equatable {
    case observed(CricketOutlookObservation10868)
    /// No admitted reading ("Unavailable").
    case unavailable(String)
    /// A reading exists but is not admitted for this slot ("Held — not
    /// current"). It carries no value, so none can be shown.
    case withheld(String)

    var observation: CricketOutlookObservation10868? {
        if case .observed(let observation) = self { return observation }
        return nil
    }

    /// The owner's words for an absent reading.
    var words: String? {
        switch self {
        case .observed: nil
        case .unavailable(let words), .withheld(let words): words
        }
    }
}

/// The owner's qualified point change, shown and spoken verbatim.
nonisolated struct CricketOutlookMovement10868: Equatable {
    /// "↓ 45 points", "No change", "↑ <0.1 points".
    let text: String
    /// "Down 45 percentage points from pregame".
    let spoken: String
}

/// A row's stable non-colour key, used for both of its marks.
nonisolated enum CricketOutlookShape10868: Equatable, CaseIterable {
    case circle
    case diamond
    case square

    var symbolName: String {
        switch self {
        case .circle: "circle"
        case .diamond: "diamond"
        case .square: "square"
        }
    }

    var filledSymbolName: String { "\(symbolName).fill" }
}

/// The owner's exact, opaque identity for one original, handed back unchanged.
nonisolated struct CricketOutlookRef10868: Hashable {
    let event: String
    let market: String
    let outcome: String
}

/// One original outcome contract.
nonisolated struct CricketOutlookRow10868: Equatable {
    /// The owner's stable row identity.
    let id: String
    /// The original's subject, in the owner's words; never truncated or shortened.
    let subject: String
    let shape: CricketOutlookShape10868
    /// The owner's stable series tint for the subject and both marks.
    let tint: Color
    /// Nil when no safe owner reference exists: the row is static.
    let ref: CricketOutlookRef10868?
    let before: CricketOutlookReading10868
    let comparison: CricketOutlookReading10868
    /// Shown only when both readings are observed.
    let movement: CricketOutlookMovement10868?
    /// The owner's completed-match words for this original. Shown only in
    /// `.completed` mode; comparison mode ignores it.
    var finish: CricketOutlookFinish10868? = nil
}

/// One owner-admitted completed-match statement, shown and spoken verbatim.
nonisolated struct CricketOutlookFinalWord10868: Equatable {
    /// "Winner", "Lost", "No draw or tie", "Won", "Void".
    let text: String
    /// The owner's optional non-colour glyph (an SF Symbol name). Decorative:
    /// `text` carries the meaning.
    let symbolName: String?
    /// Full provenance and qualification in the owner's words — whose report
    /// or which contract, and its own clock.
    let detail: String
}

/// A completed-match slot: admitted words, or the owner's words for why there
/// are none ("Not reported", "Contract result pending"). Nothing absent ever
/// becomes a loss.
nonisolated enum CricketOutlookFinalEntry10868: Equatable {
    case admitted(CricketOutlookFinalWord10868)
    case unavailable(String)

    var word: CricketOutlookFinalWord10868? {
        if case .admitted(let word) = self { return word }
        return nil
    }

    var words: String? {
        if case .unavailable(let words) = self { return words }
        return nil
    }
}

/// One original's completed-match words: the physical match outcome as
/// reported, and separately the original contract's own admitted grade. The
/// two have different sources and clocks and are never merged.
nonisolated struct CricketOutlookFinish10868: Equatable {
    /// The reported match outcome for this subject.
    let outcome: CricketOutlookFinalEntry10868
    /// The independently admitted original contract grade; nil shows no
    /// grade slot.
    let grade: CricketOutlookFinalEntry10868?
}

/// The owner's card-level words for completed mode.
nonisolated struct CricketOutlookFinalFrame10868: Equatable {
    /// Label over each original's reported outcome ("Match").
    let outcomeLabel: String
    /// Words for an original with no supplied finish ("Not reported").
    let outcomeMissing: String
    /// Label over each original's contract grade ("Original contract").
    let gradeLabel: String
    /// Reported-finish lines beneath the header, verbatim (the owner's final
    /// score line, "Final overs not reported").
    let context: [String]
}

/// Which composition the owner selected. Never inferred from the inputs.
nonisolated enum CricketOutlookMode10868: Equatable {
    /// Before reading beside comparison reading; every finish is ignored.
    case comparison
    /// Pregame beside the reported outcome and contract grade; every
    /// comparison reading, filled mark, connector and movement is ignored.
    case completed(CricketOutlookFinalFrame10868)
}

/// Where a row's marks sit, as fractions of 0...1. Nil draws no mark.
nonisolated struct CricketOutlookMarks10868: Equatable {
    /// The hollow before mark.
    let before: Double?
    /// The filled comparison mark.
    let comparison: Double?

    /// The connector between the marks, only when both are drawn.
    var segment: ClosedRange<Double>? {
        guard let before, let comparison else { return nil }
        return min(before, comparison)...max(before, comparison)
    }
}

nonisolated enum CricketOutlookSelection10868: Equatable {
    case none
    case row(CricketOutlookRow10868)
    /// The selected id does not resolve to exactly one row.
    case unavailable(String)

    var row: CricketOutlookRow10868? {
        if case .row(let row) = self { return row }
        return nil
    }
}

nonisolated enum CricketOutlookAction10868: Equatable {
    case select(CricketOutlookRef10868)
    case details(CricketOutlookRef10868)

    func perform(
        onSelect: ((CricketOutlookRef10868) -> Void)?,
        onDetails: ((CricketOutlookRef10868) -> Void)?
    ) {
        switch self {
        case .select(let ref): onSelect?(ref)
        case .details(let ref): onDetails?(ref)
        }
    }
}

nonisolated struct CricketOutlookInput10868: Equatable {
    /// "Pregame → recorded chance".
    let eyebrow: String
    /// "How the outlook changed"; nil draws none.
    let title: String?
    /// The owner's before-phase label ("Pregame").
    let beforeLabel: String
    /// The owner's comparison-phase label ("Recorded", "Current"). The owner
    /// alone decides which word its readings have earned.
    let comparisonLabel: String
    /// Every original in the owner's order — never sorted, filtered or capped.
    let rows: [CricketOutlookRow10868]
    let selectedRowID: String?
    /// The owner's notes beneath the rows, verbatim ("Changes are percentage
    /// points, not runs or wickets.").
    let notes: [String]
    /// The owner's explicit composition; comparison unless selected.
    var mode: CricketOutlookMode10868 = .comparison

    static let scaleStart = "0%"
    static let scaleEnd = "100%"
    static let scaleTitle = "Chance"
    static let scaleKey = "Scale runs from 0% to 100% chance"
    static let shapeKey = "Each outcome keeps its own shape"
    static let notDrawn = "Not drawn on the scale"
    static let selectedTag = "Selected"
    static let selectionUnavailable = "Selected outcome unavailable in this update."
    static let detailsTitle = "Details"
    static let selectHint = "Selects this outcome"

    // MARK: Identity

    private static func repeated<T: Hashable>(_ values: [T]) -> Set<T> {
        var seen = Set<T>()
        var repeated = Set<T>()
        for value in values where !seen.insert(value).inserted { repeated.insert(value) }
        return repeated
    }

    /// Row ids carried more than once. Such rows get no action and cannot be
    /// selected; every one of them stays on screen.
    var duplicateRowIDs: Set<String> { Self.repeated(rows.map(\.id)) }

    /// Owner references carried by more than one row. Such rows get no action,
    /// so no tap can reach an ambiguous subject.
    var duplicateRefs: Set<CricketOutlookRef10868> { Self.repeated(rows.compactMap(\.ref)) }

    /// The exact reference a row may hand back: present, and unique by row id
    /// and by reference.
    func actionableRef(_ row: CricketOutlookRow10868) -> CricketOutlookRef10868? {
        guard let ref = row.ref, !duplicateRowIDs.contains(row.id), !duplicateRefs.contains(ref) else { return nil }
        return ref
    }

    // MARK: Selection

    /// Exact id only. A missing or duplicated id selects nothing and no
    /// neighbour; every row stays listed.
    var selection: CricketOutlookSelection10868 {
        guard let selectedRowID else { return .none }
        let matches = rows.filter { $0.id == selectedRowID }
        guard matches.count == 1, let row = matches.first else { return .unavailable(selectedRowID) }
        return .row(row)
    }

    func isSelected(_ row: CricketOutlookRow10868) -> Bool {
        guard let selected = selection.row else { return false }
        return selected.id == row.id && !duplicateRowIDs.contains(row.id)
    }

    var selectionNotice: String? {
        if case .unavailable = selection { return Self.selectionUnavailable }
        return nil
    }

    // MARK: Actions

    func rowAction(_ row: CricketOutlookRow10868, canSelect: Bool) -> CricketOutlookAction10868? {
        guard canSelect, let ref = actionableRef(row) else { return nil }
        return .select(ref)
    }

    /// Details for the exact selected row only, when it has a safe reference.
    func detailsAction(canOpenDetails: Bool) -> CricketOutlookAction10868? {
        guard canOpenDetails, let row = selection.row, let ref = actionableRef(row) else { return nil }
        return .details(ref)
    }

    // MARK: Completed match

    /// The owner's completed-mode words, or nil in comparison mode.
    var completion: CricketOutlookFinalFrame10868? {
        if case .completed(let frame) = mode { return frame }
        return nil
    }

    var isCompleted: Bool { completion != nil }

    /// The reported match outcome slot: completed mode only. An original with
    /// no supplied finish shows the owner's missing words.
    func finalOutcome(_ row: CricketOutlookRow10868) -> CricketOutlookFinalEntry10868? {
        guard let completion else { return nil }
        return row.finish?.outcome ?? .unavailable(completion.outcomeMissing)
    }

    /// The contract grade slot: completed mode only, and only when supplied.
    func finalGrade(_ row: CricketOutlookRow10868) -> CricketOutlookFinalEntry10868? {
        guard isCompleted else { return nil }
        return row.finish?.grade
    }

    /// The reported-finish lines: completed mode only.
    var finalContext: [String] { completion?.context ?? [] }

    // MARK: Readings and marks

    /// Both readings are observed in comparison mode: only then is there a
    /// pair to move between. Completed mode has no comparison pair.
    func showsPair(_ row: CricketOutlookRow10868) -> Bool {
        !isCompleted && row.before.observation != nil && row.comparison.observation != nil
    }

    /// The owner's movement, only beside two observed readings. It is never
    /// computed here.
    func visibleMovement(_ row: CricketOutlookRow10868) -> CricketOutlookMovement10868? {
        showsPair(row) ? row.movement : nil
    }

    /// Each mark is that row's own reading; nothing is complemented,
    /// normalized or borrowed from another row, and an absent or out-of-range
    /// reading draws no mark. Completed mode draws the hollow before mark only.
    func marks(_ row: CricketOutlookRow10868) -> CricketOutlookMarks10868 {
        CricketOutlookMarks10868(
            before: row.before.observation.flatMap { CricketOutlookGeometry10868.position($0.probability) },
            comparison: isCompleted
                ? nil
                : row.comparison.observation.flatMap { CricketOutlookGeometry10868.position($0.probability) }
        )
    }

    /// The phase key beside a figure appears only when its mark is drawn.
    func showsMark(_ reading: CricketOutlookReading10868) -> Bool {
        reading.observation.flatMap { CricketOutlookGeometry10868.position($0.probability) } != nil
    }

    /// An observed figure the scale cannot place.
    func isNotDrawn(_ reading: CricketOutlookReading10868) -> Bool {
        guard let observation = reading.observation else { return false }
        return CricketOutlookGeometry10868.position(observation.probability) == nil
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, title].compactMap { $0 }).joined(separator: ". ")
    }

    /// The scale and the marks actually drawn, spoken once for the card.
    /// Completed mode draws no filled mark, so names none.
    var accessibilityKey: String? {
        guard !rows.isEmpty else { return nil }
        var parts = [Self.scaleKey, "Hollow mark: \(beforeLabel)"]
        if !isCompleted { parts.append("Filled mark: \(comparisonLabel)") }
        parts.append(Self.shapeKey)
        return parts.joined(separator: ". ")
    }

    /// Both phase readings with their provenance, the owner's movement, and
    /// the selection. Completed mode speaks the before reading, the reported
    /// outcome and any contract grade, each under its own label, and never a
    /// comparison reading or movement.
    func accessibilityRowValue(_ row: CricketOutlookRow10868) -> String {
        var parts = ["\(beforeLabel): \(Self.spoken(row.before))"]
        if let completion {
            if let outcome = finalOutcome(row) { parts.append("\(completion.outcomeLabel): \(Self.spoken(outcome))") }
            if let grade = finalGrade(row) { parts.append("\(completion.gradeLabel): \(Self.spoken(grade))") }
        } else {
            parts.append("\(comparisonLabel): \(Self.spoken(row.comparison))")
        }
        if let movement = visibleMovement(row) { parts.append(movement.spoken) }
        if isSelected(row) { parts.append(Self.selectedTag) }
        return parts.joined(separator: ". ")
    }

    var accessibilityNotes: String? {
        notes.isEmpty ? nil : notes.joined(separator: " ")
    }

    /// The reported-finish lines, completed mode only.
    var accessibilityFinalContext: String? {
        finalContext.isEmpty ? nil : finalContext.joined(separator: " ")
    }

    private static func spoken(_ reading: CricketOutlookReading10868) -> String {
        switch reading {
        case .observed(let observation):
            var parts = [observation.text, observation.detail]
            if CricketOutlookGeometry10868.position(observation.probability) == nil { parts.append(notDrawn) }
            return parts.joined(separator: ", ")
        case .unavailable(let words), .withheld(let words):
            return words
        }
    }

    private static func spoken(_ entry: CricketOutlookFinalEntry10868) -> String {
        switch entry {
        case .admitted(let word): [word.text, word.detail].joined(separator: ", ")
        case .unavailable(let words): words
        }
    }
}

nonisolated enum CricketOutlookArrangement10868: Equatable {
    /// One subview, or more than two: stacked in order.
    case single
    case sideBySide
    case stacked
}

nonisolated struct CricketOutlookColumns10868: Equatable {
    let first: CGFloat
    let second: CGFloat
}

nonisolated enum CricketOutlookGeometry10868 {
    /// A probability's place on the 0–100% scale. Zero is a place; anything
    /// non-finite or outside 0...1 is none — never clamped or guessed.
    static func position(_ probability: Double) -> Double? {
        guard probability.isFinite, probability >= 0, probability <= 1 else { return nil }
        return probability
    }

    /// A mark's x on a track of `width`, inset so a 0% or 100% mark stays whole.
    static func markX(_ position: Double, width: CGFloat, inset: CGFloat) -> CGFloat {
        let usable = max(0, width - 2 * inset)
        return inset + usable * CGFloat(position)
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
    ) -> CricketOutlookArrangement10868 {
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
    static func columns(total: CGFloat, secondIdeal: CGFloat, spacing: CGFloat, equalColumns: Bool) -> CricketOutlookColumns10868 {
        if equalColumns {
            let half = equalColumn(available: total, spacing: spacing)
            return CricketOutlookColumns10868(first: half, second: half)
        }
        let second = min(max(0, secondIdeal), max(0, total - spacing))
        return CricketOutlookColumns10868(first: max(0, total - spacing - second), second: second)
    }
}

/// Two subviews side by side while both keep their whole measured width, else
/// stacked at full width. Used for the subject/movement line and the two
/// chance figures.
struct CricketOutlookPairLayout10868: Layout {
    var spacing: CGFloat
    var equalColumns: Bool
    var forceStack: Bool

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> CricketOutlookArrangement10868 {
        guard subviews.count == 2 else { return .single }
        return CricketOutlookGeometry10868.pairArrangement(
            available: width,
            spacing: spacing,
            equalColumns: equalColumns,
            forceStack: forceStack,
            first: { subviews[0].sizeThatFits(ProposedViewSize(width: $0, height: nil)).width },
            second: { subviews[1].sizeThatFits(ProposedViewSize(width: $0, height: nil)).width }
        )
    }

    private func columns(_ total: CGFloat, _ subviews: Subviews) -> CricketOutlookColumns10868 {
        CricketOutlookGeometry10868.columns(
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
private struct CricketOutlookWrappedText10868: View {
    let text: String
    let font: Font
    let color: Color

    var body: some View {
        ZStack(alignment: .leading) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(CricketOutlookGeometry10868.words(text).enumerated()), id: \.offset) { _, word in
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

/// A row's mark in its own shape: hollow for the before reading, filled for
/// the comparison reading. Decorative — every reading is also a figure and is
/// spoken by its row.
private struct CricketOutlookGlyph10868: View {
    let shape: CricketOutlookShape10868
    let tint: Color
    let filled: Bool
    let size: CGFloat

    var body: some View {
        ZStack {
            if filled {
                Image(systemName: shape.filledSymbolName).foregroundStyle(tint)
            } else {
                Image(systemName: shape.filledSymbolName).foregroundStyle(DS.cardBg)
                Image(systemName: shape.symbolName).foregroundStyle(tint)
            }
        }
        .font(.system(size: size, weight: .bold))
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// One row's slim 0–100% track: the hollow before mark, the filled comparison
/// mark and the connector between them when both are drawn.
private struct CricketOutlookTrack10868: View {
    let marks: CricketOutlookMarks10868
    let shape: CricketOutlookShape10868
    let tint: Color
    let height: CGFloat
    let markSize: CGFloat

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let inset = markSize / 2
            let middle = geometry.size.height / 2
            ZStack(alignment: .topLeading) {
                Capsule()
                    .fill(DS.border)
                    .frame(width: width, height: 3)
                    .position(x: width / 2, y: middle)
                if let segment = marks.segment {
                    let from = CricketOutlookGeometry10868.markX(segment.lowerBound, width: width, inset: inset)
                    let to = CricketOutlookGeometry10868.markX(segment.upperBound, width: width, inset: inset)
                    Capsule()
                        .fill(tint)
                        .frame(width: max(0, to - from), height: 3)
                        .position(x: (from + to) / 2, y: middle)
                }
                if let before = marks.before {
                    CricketOutlookGlyph10868(shape: shape, tint: tint, filled: false, size: markSize)
                        .position(x: CricketOutlookGeometry10868.markX(before, width: width, inset: inset), y: middle)
                }
                if let comparison = marks.comparison {
                    CricketOutlookGlyph10868(shape: shape, tint: tint, filled: true, size: markSize * 0.7)
                        .position(x: CricketOutlookGeometry10868.markX(comparison, width: width, inset: inset), y: middle)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum CricketOutlookAccessibilityID10868 {
    static let header = "cricketOutlook10868.header"
    static let key = "cricketOutlook10868.key"
    static let notes = "cricketOutlook10868.notes"
    static let context = "cricketOutlook10868.context"
    static func row(_ rowID: String) -> String { "cricketOutlook10868.row.\(rowID)" }
    static func details(_ rowID: String) -> String { "cricketOutlook10868.details.\(rowID)" }
}

struct CricketOutlookPresentation10868: View {
    let input: CricketOutlookInput10868
    var onSelect: ((CricketOutlookRef10868) -> Void)? = nil
    var onDetails: ((CricketOutlookRef10868) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: two 26-point figures, scaled with text size.
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var missingSize: CGFloat = 17
    /// The reported outcome word beside the pregame figure.
    @ScaledMetric(relativeTo: .title3) private var outcomeSize: CGFloat = 20
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var markSize: CGFloat = 13
    @ScaledMetric(relativeTo: .caption) private var keySize: CGFloat = 10

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            finalContext
            if !input.rows.isEmpty { scale }
            ForEach(Array(input.rows.enumerated()), id: \.offset) { _, row in
                rowView(row)
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            detailsButton
            notes
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header, scale and notes

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.eyebrow)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            if let title = input.title {
                Text(title).font(.title3.bold()).foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(CricketOutlookAccessibilityID10868.header)
    }

    /// The single common scale every row's track shares.
    private var scale: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(CricketOutlookInput10868.scaleStart)
            Spacer(minLength: 8)
            Text(CricketOutlookInput10868.scaleTitle)
            Spacer(minLength: 8)
            Text(CricketOutlookInput10868.scaleEnd)
        }
        .font(.caption)
        .monospacedDigit()
        .foregroundStyle(DS.textSecondary)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityKey ?? "")
        .accessibilityIdentifier(CricketOutlookAccessibilityID10868.key)
    }

    /// Completed mode's reported-finish lines; nothing in comparison mode.
    @ViewBuilder private var finalContext: some View {
        if !input.finalContext.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.finalContext.enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityFinalContext ?? "")
            .accessibilityIdentifier(CricketOutlookAccessibilityID10868.context)
        }
    }

    @ViewBuilder private var notes: some View {
        if !input.notes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(input.notes.enumerated()), id: \.offset) { _, note in
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityNotes ?? "")
            .accessibilityIdentifier(CricketOutlookAccessibilityID10868.notes)
        }
    }

    // MARK: Rows

    private func rowView(_ row: CricketOutlookRow10868) -> some View {
        let selected = input.isSelected(row)
        let action = input.rowAction(row, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 10) {
                CricketOutlookPairLayout10868(spacing: 12, equalColumns: false, forceStack: typeSize.isAccessibilitySize) {
                    subjectLine(row, selected: selected)
                    if let movement = input.visibleMovement(row) {
                        Text(movement.text)
                            .font(.subheadline.weight(.semibold))
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                CricketOutlookPairLayout10868(spacing: 16, equalColumns: true, forceStack: typeSize.isAccessibilitySize) {
                    figure(row, reading: row.before, label: input.beforeLabel, filled: false)
                    if let completion = input.completion, let outcome = input.finalOutcome(row) {
                        finalSlot(label: completion.outcomeLabel, entry: outcome, size: outcomeSize)
                    } else {
                        figure(row, reading: row.comparison, label: input.comparisonLabel, filled: true)
                    }
                }
                if let completion = input.completion, let grade = input.finalGrade(row) {
                    finalSlot(label: completion.gradeLabel, entry: grade, size: missingSize)
                }
                CricketOutlookTrack10868(
                    marks: input.marks(row),
                    shape: row.shape,
                    tint: row.tint,
                    height: trackHeight,
                    markSize: markSize
                )
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(selected ? DS.textPrimary : Color.clear, lineWidth: 2)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(row.subject)
        .accessibilityValue(input.accessibilityRowValue(row))
        .accessibilityHint(action == nil ? "" : CricketOutlookInput10868.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(CricketOutlookAccessibilityID10868.row(row.id))
    }

    /// The subject in its series tint beside its shape; selection is an
    /// outline plus a named tag, never colour alone.
    private func subjectLine(_ row: CricketOutlookRow10868, selected: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: row.shape.filledSymbolName)
                    .font(.caption2)
                    .foregroundStyle(row.tint)
                    .accessibilityHidden(true)
                CricketOutlookWrappedText10868(text: row.subject, font: .subheadline.bold(), color: row.tint)
            }
            if selected {
                Label(CricketOutlookInput10868.selectedTag, systemImage: "checkmark")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
            }
        }
    }

    /// One labelled phase figure at the shared size, or the owner's words in
    /// the same slot. Its provenance sits beneath it.
    private func figure(
        _ row: CricketOutlookRow10868,
        reading: CricketOutlookReading10868,
        label: String,
        filled: Bool
    ) -> some View {
        CricketOutlookFigure10868(
            shape: row.shape,
            tint: row.tint,
            reading: reading,
            label: label,
            filled: filled,
            showsKey: input.showsMark(reading),
            notDrawn: input.isNotDrawn(reading),
            chanceSize: chanceSize,
            missingSize: missingSize,
            keySize: keySize
        )
    }

    /// One labelled completed-match slot: the owner's word with its optional
    /// glyph and full provenance, or the owner's missing words. No mark, no
    /// probability and no colour carries the meaning.
    private func finalSlot(label: String, entry: CricketOutlookFinalEntry10868, size: CGFloat) -> some View {
        CricketOutlookFinalSlot10868(label: label, entry: entry, size: size, missingSize: missingSize)
    }

    // MARK: Details

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let row = input.selection.row {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("\(row.subject) · \(CricketOutlookInput10868.detailsTitle)")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(CricketOutlookAccessibilityID10868.details(row.id))
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback and a safe reference;
    /// otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: CricketOutlookAction10868?, @ViewBuilder content: () -> Content) -> some View {
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

// MARK: - Shared reading slots (outlook card and match headline)

/// One labelled phase figure at the caller's shared size, or the owner's
/// words in the same slot, with its provenance beneath. The outlook card and
/// the match headline both draw a reading through this one view.
private struct CricketOutlookFigure10868: View {
    let shape: CricketOutlookShape10868
    let tint: Color
    let reading: CricketOutlookReading10868
    let label: String
    let filled: Bool
    /// The phase key glyph beside the label.
    let showsKey: Bool
    /// The outlook card's "not drawn on the scale" line.
    let notDrawn: Bool
    let chanceSize: CGFloat
    let missingSize: CGFloat
    let keySize: CGFloat
    /// The provenance beneath an observed figure. Only the match headline's
    /// admitted secondary mode passes false; absence words always show.
    var showsDetail: Bool = true

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .center, spacing: 5) {
                if showsKey {
                    CricketOutlookGlyph10868(shape: shape, tint: tint, filled: filled, size: keySize)
                }
                CricketOutlookWrappedText10868(text: label, font: .caption, color: DS.textSecondary)
            }
            switch reading {
            case .observed(let observation):
                // The whole figure keeps its width; a narrow row stacks the
                // pair instead of squeezing or splitting a number.
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                if showsDetail {
                    CricketOutlookWrappedText10868(text: observation.detail, font: .caption2, color: DS.textSecondary)
                }
                if notDrawn {
                    CricketOutlookWrappedText10868(text: CricketOutlookInput10868.notDrawn, font: .caption2, color: DS.textSecondary)
                }
            case .unavailable(let words), .withheld(let words):
                CricketOutlookWrappedText10868(
                    text: words,
                    font: .system(size: missingSize, weight: .semibold),
                    color: DS.textSecondary
                )
            }
        }
    }
}

/// One labelled completed-match slot: the owner's word with its optional
/// glyph and full provenance, or the owner's missing words.
private struct CricketOutlookFinalSlot10868: View {
    let label: String
    let entry: CricketOutlookFinalEntry10868
    let size: CGFloat
    let missingSize: CGFloat
    /// The provenance beneath an admitted word. Only the match headline's
    /// admitted secondary mode passes false; absence words always show.
    var showsDetail: Bool = true

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            CricketOutlookWrappedText10868(text: label, font: .caption, color: DS.textSecondary)
            switch entry {
            case .admitted(let word):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if let symbolName = word.symbolName {
                        Image(systemName: symbolName)
                            .font(.system(size: size * 0.8, weight: .semibold))
                            .foregroundStyle(DS.textPrimary)
                            .accessibilityHidden(true)
                    }
                    CricketOutlookWrappedText10868(text: word.text, font: .system(size: size, weight: .bold), color: DS.textPrimary)
                }
                if showsDetail {
                    CricketOutlookWrappedText10868(text: word.detail, font: .caption2, color: DS.textSecondary)
                }
            case .unavailable(let words):
                CricketOutlookWrappedText10868(
                    text: words,
                    font: .system(size: missingSize, weight: .semibold),
                    color: DS.textSecondary
                )
            }
        }
    }
}

// MARK: - Match headline

// #10868 — the cricket-live main headline across before, during and
// completed play: the approved `CricketChanceReading.tsx` headline rows
// (`cricketReadingComparison.ts`), mounted by `CricketLive.tsx` ChanceRow +
// GameState and `CricketLifecycle.tsx` LifecycleChances + final inline, with
// `cricketLive.css` and `cricketLifecycle.css`. One named block per original
// outcome contract, in the owner's order, reusing the outlook card's rows,
// readings, shapes, tints, finish words and adaptive text:
//
// - `.before`: each original's labelled pregame figure with its hollow shape
//   key. Every supplied comparison reading, movement, finish and state is
//   ignored, on screen and spoken.
// - `.during`: the pregame figure and the owner-labelled recorded or current
//   figure at one shared scaled size, each with its own provenance or its own
//   missing words. Nothing is borrowed between the two readings or between
//   rows, and equal figures from different observations stay separate.
// - `.completed`: the pregame figure beside or above the owner-reported match
//   outcome for that subject, or the owner's words for none. Every comparison
//   reading, movement and original contract grade is ignored; the outlook
//   card and Details keep the grade.
//
// The phase is the owner's explicit choice and is never inferred from which
// inputs are present. The optional state frame (score, overs, target, final
// margin) arrives as owner words with its own provenance and is shown during
// and completed play only, verbatim: nothing here derives a scoreboard,
// wickets left, a margin, a target, a forecast, a result or a date, and a
// missing state never hides a reading, nor the reverse. Blocks sit in
// measured equal columns when every cell fits whole, else stack as named
// blocks; nothing shrinks, truncates or caps text size. No chance is
// normalized, complemented or ranked, and no row is sorted, filtered or
// capped.
//
// Static content: no sheet, subscription, polling or animation. The host
// keeps the win-history chart, disclosure, held reading, full reader, Back
// and focus. Host binding still owed — the two binding maps named above,
// plus the lifecycle admission that selects the phase and the owner's
// resolved state words.
//
// Sources and timing (the approved `T20Match.tsx` main headline: the
// `T20ChanceComparison` rows without `showDates`, the timing and rules one tap
// away in `HeadlineInfo`). The host may connect `onSourceInfo`; when the
// phase-visible content carries any non-blank provenance, the headline offers one
// info control and hands back `CricketHeadlineSourceInfo10868` — exactly the
// subjects, slots, figures, outcome words, absence words, state and
// provenance this phase shows, built through the same slot and phase gates,
// never the raw rows. Only when the owner ALSO sets `secondaryProvenance` does
// the provenance beneath each observed figure, admitted outcome and reported
// state entry leave the headline for that disclosure. A callback alone or a
// flag alone keeps every line inline. Labels, figures, outcome words, state
// entries and every unavailable or held reason stay on screen in every
// combination, and every row and the state still speak their full provenance.
// Nothing reads or classifies the owner's words. The host owns the
// disclosure, its held snapshot, dismissal, Back and return focus — still
// owed: the existing `EventDetailView` probability-details popover carries
// delivery and forecast detail only, so Native must mount this payload
// through its own disclosure path before the compact mode is integrated.

/// Which headline composition the owner selected. Never inferred.
nonisolated enum CricketHeadlinePhase10868: Equatable {
    case before
    case during
    case completed
}

/// One reading slot of an original's block.
nonisolated enum CricketHeadlineSlot10868: Equatable {
    /// The pregame figure, in every phase.
    case pregame
    /// The owner-labelled recorded or current figure, during play only.
    case comparison
    /// The reported match outcome, completed play only.
    case outcome
}

nonisolated enum CricketHeadlineCellKind10868: Equatable {
    case subject
    case reading(CricketHeadlineSlot10868)
}

/// One laid-out cell: which original (by position) and what it shows.
nonisolated struct CricketHeadlineCell10868: Equatable {
    let row: Int
    let kind: CricketHeadlineCellKind10868
}

/// One owner-resolved state statement, shown and spoken verbatim.
nonisolated struct CricketHeadlineStateEntry10868: Equatable {
    /// The owner's label for the statement (the batting side, the overs);
    /// nil draws none.
    let label: String?
    /// The owner's figure or statement, verbatim.
    let text: String
    /// The owner's spoken form of `text`.
    let spoken: String
}

/// The owner's already-resolved match state. Never parsed or derived here.
nonisolated struct CricketHeadlineStateFrame10868: Equatable {
    let entries: [CricketHeadlineStateEntry10868]
    /// Full provenance in the owner's words; nil draws none.
    let detail: String?
}

nonisolated enum CricketHeadlineState10868: Equatable {
    case reported(CricketHeadlineStateFrame10868)
    /// The owner's words for why there is none ("Score unavailable").
    case unavailable(String)
}

nonisolated struct CricketHeadlineInput10868: Equatable {
    /// The owner's explicit composition.
    let phase: CricketHeadlinePhase10868
    /// The owner's caption over the readings; nil draws none. It must not
    /// claim the rows were observed at one moment.
    let caption: String?
    /// "Pregame".
    let beforeLabel: String
    /// "Recorded" or "Current" — the owner alone decides which word its
    /// readings have earned. During play only.
    let comparisonLabel: String
    /// Label over each reported outcome ("Match"). Completed play only.
    let outcomeLabel: String
    /// Words for an original with no supplied outcome ("Not reported").
    let outcomeMissing: String
    /// Every original in the owner's order — never sorted, filtered or capped.
    let rows: [CricketOutlookRow10868]
    /// Shown during and completed play only; nil draws none.
    var state: CricketHeadlineState10868? = nil

    /// The reading slots each block shows in this phase.
    var slots: [CricketHeadlineSlot10868] {
        switch phase {
        case .before: [.pregame]
        case .during: [.pregame, .comparison]
        case .completed: [.pregame, .outcome]
        }
    }

    /// The subject cell plus one cell per slot.
    var cellsPerRow: Int { 1 + slots.count }

    /// Every cell in reading order: each original's subject, then its slots.
    var cells: [CricketHeadlineCell10868] {
        rows.indices.flatMap { index in
            [CricketHeadlineCell10868(row: index, kind: .subject)]
                + slots.map { CricketHeadlineCell10868(row: index, kind: .reading($0)) }
        }
    }

    /// The comparison reading: during play only.
    func comparison(_ row: CricketOutlookRow10868) -> CricketOutlookReading10868? {
        phase == .during ? row.comparison : nil
    }

    /// The reported outcome: completed play only, never the contract grade.
    /// An original with no supplied outcome shows the owner's missing words.
    func outcome(_ row: CricketOutlookRow10868) -> CricketOutlookFinalEntry10868? {
        guard phase == .completed else { return nil }
        return row.finish?.outcome ?? .unavailable(outcomeMissing)
    }

    /// The owner's state: during and completed play only.
    var visibleState: CricketHeadlineState10868? {
        phase == .before ? nil : state
    }

    /// A phase key glyph sits beside a figure only when a reading is shown.
    func showsKey(_ reading: CricketOutlookReading10868) -> Bool {
        reading.observation != nil
    }

    // MARK: Sources and timing

    static let sourceInfoLabel = "Sources and timing"
    static let sourceInfoSymbol = "info.circle"
    /// The info control's minimum touch target on each axis.
    static let sourceInfoTarget: CGFloat = 44

    /// Every visible slot of every original, through `slots`, `comparison`,
    /// `outcome` and `visibleState`.
    var sourceInfo: CricketHeadlineSourceInfo10868 {
        CricketHeadlineSourceInfo10868(
            phase: phase,
            caption: caption,
            subjects: rows.map { row in
                CricketHeadlineSourceSubject10868(
                    id: row.id,
                    subject: row.subject,
                    entries: slots.compactMap { sourceEntry(row, slot: $0) }
                )
            },
            state: visibleState
        )
    }

    private func sourceEntry(_ row: CricketOutlookRow10868, slot: CricketHeadlineSlot10868) -> CricketHeadlineSourceEntry10868? {
        func readingEntry(_ reading: CricketOutlookReading10868, _ label: String) -> CricketHeadlineSourceEntry10868 {
            switch reading {
            case .observed(let observation):
                CricketHeadlineSourceEntry10868(slot: slot, label: label, text: observation.text, detail: observation.detail)
            case .unavailable(let words), .withheld(let words):
                CricketHeadlineSourceEntry10868(slot: slot, label: label, text: words, detail: nil)
            }
        }
        switch slot {
        case .pregame:
            return readingEntry(row.before, beforeLabel)
        case .comparison:
            return comparison(row).map { readingEntry($0, comparisonLabel) }
        case .outcome:
            return outcome(row).map { entry -> CricketHeadlineSourceEntry10868 in
                switch entry {
                case .admitted(let word):
                    CricketHeadlineSourceEntry10868(slot: slot, label: outcomeLabel, text: word.text, detail: word.detail)
                case .unavailable(let words):
                    CricketHeadlineSourceEntry10868(slot: slot, label: outcomeLabel, text: words, detail: nil)
                }
            }
        }
    }

    /// The info control appears only for a connected host and content with
    /// provenance. Provenance leaves the headline only when the owner's
    /// explicit secondary flag meets that offered control.
    func provenancePresentation(secondary: Bool, connected: Bool) -> CricketHeadlineProvenancePresentation10868 {
        let offersInfo = connected && sourceInfo.hasProvenance
        return CricketHeadlineProvenancePresentation10868(offersInfo: offersInfo, inline: !(secondary && offersInfo))
    }

    /// The state's provenance line on screen: beneath reported entries only
    /// while inline; with no entries it qualifies nothing and stays.
    func inlineStateDetail(_ presentation: CricketHeadlineProvenancePresentation10868) -> String? {
        guard case .reported(let frame)? = visibleState else { return nil }
        return presentation.inline || frame.entries.isEmpty ? frame.detail : nil
    }

    func topRow(_ presentation: CricketHeadlineProvenancePresentation10868) -> CricketHeadlineTopRow10868 {
        switch (caption != nil, presentation.offersInfo) {
        case (true, true): .captionAndInfo
        case (true, false): .caption
        case (false, true): .info
        case (false, false): CricketHeadlineTopRow10868.none
        }
    }

    // MARK: VoiceOver

    /// Each visible slot under its own label with its own provenance or
    /// words. Never a hidden reading, movement, grade or state.
    func accessibilityRowValue(_ row: CricketOutlookRow10868) -> String {
        slots.compactMap { slot -> String? in
            switch slot {
            case .pregame:
                return "\(beforeLabel): \(Self.spoken(row.before))"
            case .comparison:
                return comparison(row).map { "\(comparisonLabel): \(Self.spoken($0))" }
            case .outcome:
                return outcome(row).map { "\(outcomeLabel): \(Self.spoken($0))" }
            }
        }
        .joined(separator: ". ")
    }

    /// The visible state's entries and provenance, or the owner's words.
    var accessibilityState: String? {
        switch visibleState {
        case .reported(let frame)?:
            let entries = frame.entries.map { entry in
                entry.label.map { "\($0): \(entry.spoken)" } ?? entry.spoken
            }
            let parts = entries + (frame.detail.map { [$0] } ?? [])
            return parts.isEmpty ? nil : parts.joined(separator: ". ")
        case .unavailable(let words)?:
            return words
        case nil:
            return nil
        }
    }

    private static func spoken(_ reading: CricketOutlookReading10868) -> String {
        switch reading {
        case .observed(let observation):
            return [observation.text, observation.detail].joined(separator: ", ")
        case .unavailable(let words), .withheld(let words):
            return words
        }
    }

    private static func spoken(_ entry: CricketOutlookFinalEntry10868) -> String {
        switch entry {
        case .admitted(let word): return [word.text, word.detail].joined(separator: ", ")
        case .unavailable(let words): return words
        }
    }
}

// MARK: Match headline — sources and timing

/// One visible slot as the headline shows it, with its full provenance.
nonisolated struct CricketHeadlineSourceEntry10868: Equatable {
    let slot: CricketHeadlineSlot10868
    /// The owner's label over the slot ("Pregame", "Recorded", "Match").
    let label: String
    /// The owner's figure or outcome word, or its words for none.
    let text: String
    /// The provenance beneath `text`, verbatim; nil when the slot shows only
    /// the owner's absence words.
    let detail: String?
}

/// One original's visible slots, in the phase's slot order.
nonisolated struct CricketHeadlineSourceSubject10868: Equatable {
    /// The owner's stable row identity.
    let id: String
    let subject: String
    let entries: [CricketHeadlineSourceEntry10868]
}

/// The complete display content the headline shows in its phase — never a
/// hidden later reading, movement, outcome, grade or state, and never a raw
/// probability or reference — handed to the host's disclosure unchanged.
nonisolated struct CricketHeadlineSourceInfo10868: Equatable {
    let phase: CricketHeadlinePhase10868
    let caption: String?
    /// Every original in the owner's order.
    let subjects: [CricketHeadlineSourceSubject10868]
    /// The visible state; nil before play or when none is supplied.
    let state: CricketHeadlineState10868?

    /// Any provenance to disclose. Absence words alone leave nothing to open,
    /// and neither does an empty or whitespace-only detail.
    var hasProvenance: Bool {
        if subjects.contains(where: { $0.entries.contains { Self.discloses($0.detail) } }) { return true }
        if case .reported(let frame)? = state { return Self.discloses(frame.detail) }
        return false
    }

    /// At least one non-whitespace character. Only tested — the payload,
    /// the visible lines and speech keep the owner's string unchanged.
    private static func discloses(_ detail: String?) -> Bool {
        detail?.contains { !$0.isWhitespace } ?? false
    }
}

/// How the headline places its provenance for one owner flag and host
/// connection.
nonisolated struct CricketHeadlineProvenancePresentation10868: Equatable {
    /// One info control, handing the host the source info.
    let offersInfo: Bool
    /// Provenance stays beneath each observed figure, admitted outcome and
    /// reported state.
    let inline: Bool
}

/// What shares the headline's top line.
nonisolated enum CricketHeadlineTopRow10868: Equatable {
    case none
    case caption
    case captionAndInfo
    /// No caption: the info control alone, trailing.
    case info
}

nonisolated enum CricketHeadlineArrangement10868: Equatable {
    /// One measured equal column per original; its cells stack inside it and
    /// each slot's band lines up across columns.
    case columns
    /// One named block per original at full width. Its two readings share a
    /// line in equal halves only when every reading of every block fits whole.
    case blocks(readingsSideBySide: Bool)
}

nonisolated enum CricketHeadlineGeometry10868 {
    /// One of `count` equal columns.
    static func column(available: CGFloat, spacing: CGFloat, count: Int) -> CGFloat {
        guard count > 0 else { return 0 }
        return max(0, (available - spacing * CGFloat(count - 1)) / CGFloat(count))
    }

    /// Columns only when every cell measured at the column width stays
    /// inside it — a whole figure and the widest word included. Otherwise
    /// named blocks, with the two readings side by side only when every one
    /// fits whole in half the width. Accessibility sizes always stack.
    /// `measure` answers cell `index`'s width for a proposed width (nil = its
    /// ideal); cell `block * cellsPerBlock` is that block's name.
    static func arrangement(
        available: CGFloat?,
        spacing: CGFloat,
        blocks: Int,
        cellsPerBlock: Int,
        forceStack: Bool,
        measure: (_ index: Int, _ proposal: CGFloat?) -> CGFloat
    ) -> CricketHeadlineArrangement10868 {
        if forceStack || blocks < 1 || cellsPerBlock < 1 { return .blocks(readingsSideBySide: false) }
        let readings = cellsPerBlock - 1
        guard let available, available.isFinite else {
            return blocks > 1 ? .columns : .blocks(readingsSideBySide: readings == 2)
        }
        func fits(_ index: Int, _ width: CGFloat) -> Bool {
            let measured = measure(index, width)
            return measured.isFinite && measured <= width + 0.5
        }
        if blocks > 1 {
            let column = Self.column(available: available, spacing: spacing, count: blocks)
            if (0..<(blocks * cellsPerBlock)).allSatisfy({ fits($0, column) }) { return .columns }
        }
        guard readings == 2 else { return .blocks(readingsSideBySide: false) }
        let half = CricketOutlookGeometry10868.equalColumn(available: available, spacing: spacing)
        let sideBySide = (0..<blocks).allSatisfy { block in
            fits(block * cellsPerBlock + 1, half) && fits(block * cellsPerBlock + 2, half)
        }
        return .blocks(readingsSideBySide: sideBySide)
    }
}

/// The headline's cells in measured equal columns or named stacked blocks.
/// Subviews arrive block by block, `cellsPerBlock` at a time, name first; a
/// count that does not divide evenly lays every cell out as its own block.
struct CricketHeadlineGridLayout10868: Layout {
    var cellsPerBlock: Int
    /// Between columns, and between the two halves of a block.
    var spacing: CGFloat
    /// Between the cells of one block.
    var rowSpacing: CGFloat
    /// Between stacked blocks.
    var blockSpacing: CGFloat
    var forceStack: Bool

    private struct Placement {
        var size: CGSize
        var cells: [CGRect]
    }

    private func perBlock(_ subviews: Subviews) -> Int {
        cellsPerBlock > 0 && subviews.count % cellsPerBlock == 0 ? cellsPerBlock : 1
    }

    private func placement(width proposed: CGFloat?, subviews: Subviews) -> Placement {
        // A non-finite proposal is laid out at the cells' ideal widths.
        let width = proposed.flatMap { $0.isFinite ? $0 : nil }
        let per = perBlock(subviews)
        let blocks = subviews.count / per
        func height(_ index: Int, _ width: CGFloat) -> CGFloat {
            subviews[index].sizeThatFits(ProposedViewSize(width: width, height: nil)).height
        }
        let widestIdeal = subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        var cells = Array(repeating: CGRect.zero, count: subviews.count)
        let arrangement = CricketHeadlineGeometry10868.arrangement(
            available: width,
            spacing: spacing,
            blocks: blocks,
            cellsPerBlock: per,
            forceStack: forceStack,
            measure: { subviews[$0].sizeThatFits(ProposedViewSize(width: $1, height: nil)).width }
        )
        var y: CGFloat = 0
        switch arrangement {
        case .columns:
            let column = width.map { CricketHeadlineGeometry10868.column(available: $0, spacing: spacing, count: blocks) } ?? widestIdeal
            let total = width ?? (column * CGFloat(blocks) + spacing * CGFloat(max(0, blocks - 1)))
            for slot in 0..<per {
                if slot > 0 { y += rowSpacing }
                let band = (0..<blocks).map { height($0 * per + slot, column) }.max() ?? 0
                for block in 0..<blocks {
                    cells[block * per + slot] = CGRect(x: CGFloat(block) * (column + spacing), y: y, width: column, height: band)
                }
                y += band
            }
            return Placement(size: CGSize(width: total, height: y), cells: cells)
        case .blocks(let readingsSideBySide):
            let total = width ?? widestIdeal
            let half = CricketOutlookGeometry10868.equalColumn(available: total, spacing: spacing)
            for block in 0..<blocks {
                if block > 0 { y += blockSpacing }
                let name = block * per
                let nameHeight = height(name, total)
                cells[name] = CGRect(x: 0, y: y, width: total, height: nameHeight)
                y += nameHeight
                if readingsSideBySide && per == 3 {
                    y += rowSpacing
                    let band = max(height(name + 1, half), height(name + 2, half))
                    cells[name + 1] = CGRect(x: 0, y: y, width: half, height: band)
                    cells[name + 2] = CGRect(x: half + spacing, y: y, width: half, height: band)
                    y += band
                } else {
                    for slot in 1..<per {
                        y += rowSpacing
                        let slotHeight = height(name + slot, total)
                        cells[name + slot] = CGRect(x: 0, y: y, width: total, height: slotHeight)
                        y += slotHeight
                    }
                }
            }
            return Placement(size: CGSize(width: total, height: y), cells: cells)
        }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        return placement(width: proposal.width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let cells = placement(width: bounds.width, subviews: subviews).cells
        for (index, subview) in subviews.enumerated() {
            let cell = cells[index]
            subview.place(
                at: CGPoint(x: bounds.minX + cell.minX, y: bounds.minY + cell.minY),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: cell.width, height: nil)
            )
        }
    }
}

/// Stable ids for the host's focus return and UI tests.
nonisolated enum CricketHeadlineAccessibilityID10868 {
    static let caption = "cricketHeadline10868.caption"
    static let state = "cricketHeadline10868.state"
    static let sourceInfo = "cricketHeadline10868.sourceInfo"
    static func row(_ rowID: String) -> String { "cricketHeadline10868.row.\(rowID)" }
}

struct CricketHeadlinePresentation10868: View {
    let input: CricketHeadlineInput10868
    /// The owner's explicit choice to present provenance as secondary. Moves
    /// nothing unless `onSourceInfo` is connected and the info control shows.
    var secondaryProvenance: Bool = false
    /// The host's sources-and-timing disclosure; nil offers no control.
    var onSourceInfo: ((CricketHeadlineSourceInfo10868) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: 26-point chance figures, scaled with text size,
    /// one size for both readings.
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var missingSize: CGFloat = 17
    /// The reported outcome word beside the pregame figure.
    @ScaledMetric(relativeTo: .title3) private var outcomeSize: CGFloat = 20
    /// The owner's state figures.
    @ScaledMetric(relativeTo: .title3) private var stateSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var keySize: CGFloat = 10

    private var provenance: CricketHeadlineProvenancePresentation10868 {
        input.provenancePresentation(secondary: secondaryProvenance, connected: onSourceInfo != nil)
    }

    /// Hands the host this phase's source info — the info control's action.
    func openSourceInfo() {
        guard provenance.offersInfo, let onSourceInfo else { return }
        onSourceInfo(input.sourceInfo)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            topRow
            if !input.rows.isEmpty {
                CricketHeadlineGridLayout10868(
                    cellsPerBlock: input.cellsPerRow,
                    spacing: 12,
                    rowSpacing: 10,
                    blockSpacing: 16,
                    forceStack: typeSize.isAccessibilitySize
                ) {
                    ForEach(Array(input.cells.enumerated()), id: \.offset) { _, cell in
                        cellView(cell)
                    }
                }
                .accessibilityElement(children: .contain)
            }
            stateView
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Caption and sources

    /// The caption, beside the one info control when it is offered; with no
    /// caption the control sits alone at the trailing edge. The caption wraps
    /// beside the control and the readings below keep their full width.
    @ViewBuilder private var topRow: some View {
        switch input.topRow(provenance) {
        case .captionAndInfo:
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                caption
                Spacer(minLength: 0)
                infoButton
            }
        case .caption:
            caption
        case .info:
            HStack {
                Spacer(minLength: 0)
                infoButton
            }
        case .none:
            EmptyView()
        }
    }

    @ViewBuilder private var caption: some View {
        if let caption = input.caption {
            CricketOutlookWrappedText10868(text: caption, font: .subheadline.weight(.semibold), color: DS.textSecondary)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(caption)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(CricketHeadlineAccessibilityID10868.caption)
        }
    }

    private var infoButton: some View {
        Button(action: openSourceInfo) {
            Image(systemName: CricketHeadlineInput10868.sourceInfoSymbol)
                .font(.body)
                .foregroundStyle(DS.blue)
                .frame(minWidth: CricketHeadlineInput10868.sourceInfoTarget, minHeight: CricketHeadlineInput10868.sourceInfoTarget)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(CricketHeadlineInput10868.sourceInfoLabel)
        .accessibilityIdentifier(CricketHeadlineAccessibilityID10868.sourceInfo)
    }

    // MARK: Cells

    /// The subject cell speaks the whole block, in the owner's row order; the
    /// reading cells are its visible parts.
    @ViewBuilder private func cellView(_ cell: CricketHeadlineCell10868) -> some View {
        let row = input.rows[cell.row]
        switch cell.kind {
        case .subject:
            subject(row)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(row.subject)
                .accessibilityValue(input.accessibilityRowValue(row))
                .accessibilitySortPriority(Double(input.rows.count - cell.row))
                .accessibilityIdentifier(CricketHeadlineAccessibilityID10868.row(row.id))
        case .reading(let slot):
            reading(row, slot: slot)
                .accessibilityHidden(true)
        }
    }

    /// The subject in its series tint beside its shape.
    private func subject(_ row: CricketOutlookRow10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: row.shape.filledSymbolName)
                .font(.caption2)
                .foregroundStyle(row.tint)
                .accessibilityHidden(true)
            CricketOutlookWrappedText10868(text: row.subject, font: .subheadline.bold(), color: row.tint)
        }
    }

    @ViewBuilder private func reading(_ row: CricketOutlookRow10868, slot: CricketHeadlineSlot10868) -> some View {
        switch slot {
        case .pregame:
            figure(row, row.before, label: input.beforeLabel, filled: false)
        case .comparison:
            if let comparison = input.comparison(row) {
                figure(row, comparison, label: input.comparisonLabel, filled: true)
            }
        case .outcome:
            if let outcome = input.outcome(row) {
                CricketOutlookFinalSlot10868(
                    label: input.outcomeLabel,
                    entry: outcome,
                    size: outcomeSize,
                    missingSize: missingSize,
                    showsDetail: provenance.inline
                )
            }
        }
    }

    private func figure(_ row: CricketOutlookRow10868, _ reading: CricketOutlookReading10868, label: String, filled: Bool) -> some View {
        CricketOutlookFigure10868(
            shape: row.shape,
            tint: row.tint,
            reading: reading,
            label: label,
            filled: filled,
            showsKey: input.showsKey(reading),
            notDrawn: false,
            chanceSize: chanceSize,
            missingSize: missingSize,
            keySize: keySize,
            showsDetail: provenance.inline
        )
    }

    // MARK: State

    @ViewBuilder private var stateView: some View {
        switch input.visibleState {
        case .reported(let frame)?:
            VStack(alignment: .leading, spacing: 6) {
                if !frame.entries.isEmpty {
                    CricketHeadlineGridLayout10868(
                        cellsPerBlock: 1,
                        spacing: 20,
                        rowSpacing: 0,
                        blockSpacing: 10,
                        forceStack: typeSize.isAccessibilitySize
                    ) {
                        ForEach(Array(frame.entries.enumerated()), id: \.offset) { _, entry in
                            VStack(alignment: .leading, spacing: 4) {
                                if let label = entry.label {
                                    CricketOutlookWrappedText10868(text: label, font: .caption, color: DS.textSecondary)
                                }
                                CricketOutlookWrappedText10868(
                                    text: entry.text,
                                    font: .system(size: stateSize, weight: .bold).monospacedDigit(),
                                    color: DS.textPrimary
                                )
                            }
                        }
                    }
                }
                if let detail = input.inlineStateDetail(provenance) {
                    CricketOutlookWrappedText10868(text: detail, font: .caption2, color: DS.textSecondary)
                }
            }
            .padding(.top, 10)
            .overlay(alignment: .top) {
                Rectangle().fill(DS.border).frame(height: 1)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityState ?? "")
            .accessibilityIdentifier(CricketHeadlineAccessibilityID10868.state)
        case .unavailable(let words)?:
            CricketOutlookWrappedText10868(text: words, font: .subheadline, color: DS.textSecondary)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(words)
                .accessibilityIdentifier(CricketHeadlineAccessibilityID10868.state)
        case nil:
            EmptyView()
        }
    }
}

// MARK: - Pregame story card

// #10868 — the T20 "Pregame outlook" story card before the first ball: the
// approved `T20Match.tsx` BeforeCard + `t20Match.css`, mounted in the story
// stream and the full-size reader only before play. A clear eyebrow and
// title, then one named row per original outcome contract in the owner's
// order: the subject beside its large owner-formatted pregame figure, an
// independent filled rail on the same 0–100% chance scale, and the owner's
// explicit pregame label with that reading's full provenance or absence
// words. No comparison slot, connector, movement or result grammar.
//
// Reuses the outlook card's rows, readings, observations, shapes, tints,
// adaptive text and measured pair layout, and the headline's explicit phase.
// Only `.before` shows the card; `.during` and `.completed` draw and speak
// nothing at all. Within it only each row's own before reading is reachable:
// every comparison reading, movement, finish, grade, score or target a row
// carries is ignored, on screen and spoken. The phase is never inferred from
// which inputs are present.
//
// Each rail is that row's own reading and nothing else: never complemented,
// normalized, summed or ranked, and no draw row is added — an independently
// traded 78% and 23% stay 78% and 23%. A valid 0 is an empty rail beside its
// 0% figure; a valid 1 fills it. An unavailable or held reading shows the
// owner's words and no rail, never a 0% guess; a figure the scale cannot
// place keeps its words, draws no rail and says so — never clamped. The
// shared `ProbabilityBar` is one paired segmented track and `DSProbabilityBar`
// floors every fill at 2 points, so a small local rail draws the fill;
// neither shared primitive is used or changed.
//
// Static content: no selector, play or update control, Details action,
// state, subscription, timer, ranking or animation, and no identity is read
// from a row's reference. The host keeps stream order, held updates,
// full-size opening, the reader, the original catalogue, Back and focus.
// Host binding still owed — T20-BEFORE-STORY-NATIVE-BINDING-MAP.md: proved
// original membership, an independently admitted pregame reading per
// original with its local-calendar words, and the phase admission that
// selects `.before`.

nonisolated struct CricketPregameStoryInput10868: Equatable {
    /// The owner's explicit phase. Only `.before` shows the card.
    let phase: CricketHeadlinePhase10868
    /// "Before the first ball".
    let eyebrow: String
    /// The owner's title; nil draws none.
    let title: String?
    /// The owner's explicit pregame label under each rail ("Pregame chance
    /// to win").
    let beforeLabel: String
    /// Every original in the owner's order — never sorted, filtered or capped.
    let rows: [CricketOutlookRow10868]
    /// The owner's notes beneath the rows, verbatim.
    let notes: [String]

    /// Before play only; during and completed play show nothing.
    var isVisible: Bool { phase == .before }

    /// Every original before play, none otherwise.
    var visibleRows: [CricketOutlookRow10868] { isVisible ? rows : [] }

    var visibleNotes: [String] { isVisible ? notes : [] }

    /// The row's own before reading, before play only. No other reading a
    /// row carries is reachable from this card.
    func reading(_ row: CricketOutlookRow10868) -> CricketOutlookReading10868? {
        isVisible ? row.before : nil
    }

    /// The rail's fill, 0...1: an observed before reading the scale can
    /// place. Nil draws no rail.
    func fill(_ row: CricketOutlookRow10868) -> Double? {
        reading(row)?.observation.flatMap { CricketOutlookGeometry10868.position($0.probability) }
    }

    /// An observed figure the scale cannot place: its words stay, no rail.
    func isNotDrawn(_ row: CricketOutlookRow10868) -> Bool {
        guard let observation = reading(row)?.observation else { return false }
        return CricketOutlookGeometry10868.position(observation.probability) == nil
    }

    // MARK: VoiceOver

    var accessibilityHeader: String? {
        isVisible ? [eyebrow, title].compactMap { $0 }.joined(separator: ". ") : nil
    }

    /// The pregame label with the row's own figure and provenance, or its
    /// words. Nil outside before play.
    func accessibilityRowValue(_ row: CricketOutlookRow10868) -> String? {
        guard let reading = reading(row) else { return nil }
        switch reading {
        case .observed(let observation):
            var parts = [observation.text, observation.detail]
            if isNotDrawn(row) { parts.append(CricketOutlookInput10868.notDrawn) }
            return "\(beforeLabel): \(parts.joined(separator: ", "))"
        case .unavailable(let words), .withheld(let words):
            return "\(beforeLabel): \(words)"
        }
    }

    var accessibilityNotes: String? {
        visibleNotes.isEmpty ? nil : visibleNotes.joined(separator: " ")
    }
}

nonisolated enum CricketPregameStoryGeometry10868 {
    /// The filled width of a rail `width` wide. Zero is empty and one is
    /// full, with no minimum fill; a fraction the scale cannot place fills
    /// nothing and draws no rail — never clamped.
    static func fillWidth(_ fraction: Double, width: CGFloat) -> CGFloat? {
        guard let position = CricketOutlookGeometry10868.position(fraction) else { return nil }
        return max(0, width) * CGFloat(position)
    }
}

/// Stable ids for the host's focus return and UI tests.
nonisolated enum CricketPregameStoryAccessibilityID10868 {
    static let header = "cricketPregameStory10868.header"
    static let notes = "cricketPregameStory10868.notes"
    static func row(_ rowID: String) -> String { "cricketPregameStory10868.row.\(rowID)" }
}

/// One row's independent 0–100% rail, filled to that reading alone in the
/// row's tint. Decorative: the row speaks its label, figure and provenance.
private struct CricketPregameStoryRail10868: View {
    let fraction: Double
    let tint: Color
    let height: CGFloat

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Rectangle().fill(DS.border)
                Rectangle()
                    .fill(tint)
                    .frame(width: CricketPregameStoryGeometry10868.fillWidth(fraction, width: geometry.size.width) ?? 0)
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .accessibilityHidden(true)
    }
}

struct CricketPregameStoryPresentation10868: View {
    let input: CricketPregameStoryInput10868

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: 26-point chance figures, scaled with text size.
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 26
    @ScaledMetric(relativeTo: .body) private var missingSize: CGFloat = 17
    /// The approved 10-point rail, scaled with text size.
    @ScaledMetric(relativeTo: .caption) private var railHeight: CGFloat = 10

    var body: some View {
        if input.isVisible {
            VStack(alignment: .leading, spacing: 14) {
                header
                ForEach(Array(input.visibleRows.enumerated()), id: \.offset) { _, row in
                    rowView(row)
                }
                notes
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Header and notes

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.eyebrow)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            if let title = input.title {
                Text(title).font(.title3.bold()).foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader ?? "")
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(CricketPregameStoryAccessibilityID10868.header)
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
            .accessibilityIdentifier(CricketPregameStoryAccessibilityID10868.notes)
        }
    }

    // MARK: Rows

    /// The subject beside its figure while both keep their whole width, else
    /// stacked; then the rail when it can be drawn; then the pregame label
    /// and the reading's provenance. One element, spoken in full.
    private func rowView(_ row: CricketOutlookRow10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            CricketOutlookPairLayout10868(spacing: 12, equalColumns: false, forceStack: typeSize.isAccessibilitySize) {
                subject(row)
                figure(row)
            }
            if let fill = input.fill(row) {
                CricketPregameStoryRail10868(fraction: fill, tint: row.tint, height: railHeight)
            }
            VStack(alignment: .leading, spacing: 2) {
                CricketOutlookWrappedText10868(text: input.beforeLabel, font: .caption, color: DS.textSecondary)
                if let observation = input.reading(row)?.observation {
                    CricketOutlookWrappedText10868(text: observation.detail, font: .caption2, color: DS.textSecondary)
                    if input.isNotDrawn(row) {
                        CricketOutlookWrappedText10868(text: CricketOutlookInput10868.notDrawn, font: .caption2, color: DS.textSecondary)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(row.subject)
        .accessibilityValue(input.accessibilityRowValue(row) ?? "")
        .accessibilityIdentifier(CricketPregameStoryAccessibilityID10868.row(row.id))
    }

    /// The subject in full beside its shape; the tint marks the shape, the
    /// name reads in the primary text colour.
    private func subject(_ row: CricketOutlookRow10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: row.shape.filledSymbolName)
                .font(.caption2)
                .foregroundStyle(row.tint)
                .accessibilityHidden(true)
            CricketOutlookWrappedText10868(text: row.subject, font: .subheadline.bold(), color: DS.textPrimary)
        }
    }

    /// The owner's whole figure at the shared scaled size, or the owner's
    /// words in the same place.
    @ViewBuilder private func figure(_ row: CricketOutlookRow10868) -> some View {
        switch input.reading(row) {
        case .observed(let observation)?:
            Text(observation.text)
                .font(.system(size: chanceSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
        case .unavailable(let words)?, .withheld(let words)?:
            CricketOutlookWrappedText10868(
                text: words,
                font: .system(size: missingSize, weight: .semibold),
                color: DS.textSecondary
            )
        case nil:
            EmptyView()
        }
    }
}
