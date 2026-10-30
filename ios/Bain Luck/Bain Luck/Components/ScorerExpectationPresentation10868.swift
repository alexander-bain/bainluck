import SwiftUI

// #10868 — "Who found the net?": the anytime-scorer card across a match's
// lifecycle. Rings come first and always show the PREGAME chance of scoring at
// least once. Beside each ring sits the player's actual goal count once play has
// started ("goals so far" live, "final goals" after the final). The selected
// player's full comparison sits below the rings: pregame vs recorded in-game
// chance during play, pregame chance vs final goals after it.
//
// Presentation only, extracted from the approved design
// (hockey-readable-card-composition-20261026 `HockeyScoring.swift` /
// `HockeyLiveGoalsCards.swift`; goal-scorer-comparison-20261025 and
// final-scorer-comparison-20261025 frames). The ring-first order is the approved
// one; a top selected-summary layout was tried and rejected at 375pt.
//
// Every figure, unit, date, source, missing qualifier, sporting state and
// result arrives resolved by the owner and is shown verbatim. This layer never
// formats, rounds, ranks, filters, caps or joins players, never reads a clock,
// cache, subscription or admission rule, never copies one reading into another,
// never turns a market settlement, a reached state or a probability into a goal
// count, and never draws a reached state as 100%. Unknown is never zero.
//
// Selection, timing disclosure, Details and the full player list stay with the
// host: the view keeps no selected state, no sheet, no focus and no
// subscription. With no callback, content is shown without a button and no tap
// is asked for. First-scorer, totals and points/assists are separate cards.
//
// Host binding still owed — not available at this base. The backend During stat
// table excludes goals (`backend/app/utils/event_props_matrix.py`) and the After
// actual contract admits only hits/home runs
// (`backend/app/utils/prop_expectation_actual.py` `AFTER_STAT_BOX_KEYS`), so the
// generic `DuringPropComparison` / `AfterPropActual` fields are not a hockey
// scorer binding. An owner must supply, per player:
//   • the exact original anytime-scorer prop id, name, team text and colour,
//   • an admitted pregame observation (raw value, formatted figure, full
//     time/source) or its own missing words,
//   • during play, an admitted recorded observation or its own
//     unavailable / stale / reached words, with currentness already applied,
//   • an independently identified, clocked actual goal count or its own
//     unknown words, and after the final an optional contract-result line.
// None of these may be synthesized from replay data, name joins, settlement or
// another prop (an anytime chance is never a first-scorer chance).

/// One admitted reading. `probability` drives ring geometry only; `text` is what
/// the reader sees.
nonisolated struct ScorerObservation10868: Equatable {
    let probability: Double
    let text: String
    /// Full time and source for VoiceOver ("recorded Oct 3, 4:57 PM PT · Kalshi").
    let accessibilityDetail: String
}

/// The owner's in-game state for one player, with currentness already applied.
nonisolated enum ScorerCurrent10868: Equatable {
    /// An admitted, current recorded observation.
    case recorded(ScorerObservation10868)
    /// No recorded reading ("No in-game reading").
    case unavailable(String)
    /// A reading exists but is no longer current ("No update since goal").
    case stale(String)
    /// The player has scored ("Scored") — a sporting state, never a 100% chance
    /// and never a market settlement.
    case reached(String)
}

/// An independently admitted goal count, already formatted by the owner.
nonisolated struct ScorerGoalCount10868: Equatable {
    /// Raw count for the decorative pips only; nil draws no pips.
    let value: Int?
    /// The whole figure ("2").
    let text: String
    /// "goal so far", "goals so far", "Final goals".
    let unit: String
    /// Observation context for VoiceOver ("3rd period, 14:34 left · ESPN").
    let accessibilityDetail: String?
}

/// Actual goals. `unknown` is distinct from a real zero count.
nonisolated enum ScorerActual10868: Equatable {
    case count(ScorerGoalCount10868)
    /// The owner's words ("Final count unavailable").
    case unknown(String)
}

/// One player. Each reading carries its own missing words, so a missing
/// pregame chance is never explained by the in-game state or vice versa.
/// `current` is read only during play, `actual` only during play and after the
/// final, `result` only after the final.
nonisolated struct ScorerRow10868: Equatable {
    /// Opaque original-prop identity, passed back to the owner exactly.
    let id: String
    let name: String
    /// "Minnesota", "Team unavailable"; nil draws no team line.
    let team: String?
    let color: Color
    let pregame: ScorerObservation10868?
    let pregameMissing: String
    let current: ScorerCurrent10868
    let actual: ScorerActual10868
    /// The owner's contract result ("1+ goals outcome · Lost"). Missing is not a loss.
    let result: String?
}

nonisolated enum ScorerPhase10868: Equatable {
    case before
    case during
    case final
}

/// The owner's timing disclosure for one player. Shown only while that exact
/// player is the resolved selection.
nonisolated struct ScorerTiming10868: Equatable {
    let playerID: String
    /// "Max Shabanov · probability timing".
    let title: String
    let lines: [String]
}

nonisolated enum ScorerSelection10868: Equatable {
    case none
    /// The selected player is one tile in the overview.
    case overview(ScorerRow10868)
    /// The selected player is not in the overview; shown once below it.
    case outside(ScorerRow10868)
    /// No row carries the selected id.
    case missing(String)
    /// More than one overview tile carries the selected id.
    case duplicate(String)

    var row: ScorerRow10868? {
        switch self {
        case .overview(let row), .outside(let row): row
        case .none, .missing, .duplicate: nil
        }
    }
}

nonisolated enum ScorerReading10868: Equatable {
    case value(ScorerObservation10868)
    case missing(String)
    case reached(String)

    var text: String {
        switch self {
        case .value(let observation): observation.text
        case .missing(let text), .reached(let text): text
        }
    }
}

nonisolated enum ScorerAction10868: Equatable {
    case select(String)
    case details(String)

    func perform(onSelect: ((String) -> Void)?, onDetails: ((String) -> Void)?) {
        switch self {
        case .select(let id): onSelect?(id)
        case .details(let id): onDetails?(id)
        }
    }
}

nonisolated enum ScorerTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(ScorerTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(ScorerTiming10868)
}

nonisolated struct ScorerExpectationInput10868: Equatable {
    let phase: ScorerPhase10868
    /// "Who found the net?"
    let title: String
    /// "Kalshi · player goals".
    let context: String?
    /// Admitted rows in the owner's order — never sorted, filtered or capped here.
    let overview: [ScorerRow10868]
    /// The owner's exact selection.
    let selectedID: String?
    /// The selected player's row when it is not in the overview (a zero or
    /// unknown-count player). Read only when `selectedID` is absent from the overview.
    let selectedRow: ScorerRow10868?
    /// The owner's availability line ("30 recorded zero goals · 2 goal totals unavailable").
    let summary: String?
    let timing: ScorerTiming10868?

    static let pregameTitle = "Pregame"
    static let recordedTitle = "Recorded in-game"
    static let finalGoalsTitle = "Final goals"
    static let selectionUnavailable = "Selected player unavailable."

    var showsActual: Bool { phase != .before }

    /// Names what the ring and the count measure in this phase.
    var legend: String {
        switch phase {
        case .before: "Rings: pregame chance of scoring at least once"
        case .during: "Rings: pregame scoring chance · counts: goals so far"
        case .final: "Rings: pregame scoring chance · counts: final goals"
        }
    }

    /// Above the selected comparison; the final pairs a chance with a count, not two chances.
    var comparisonHeading: String {
        phase == .final ? "Pregame chance and final goals" : "Chance to score at least once"
    }

    /// Asks for a tap only when one does something.
    func instruction(canSelect: Bool) -> String? {
        canSelect && !overview.isEmpty ? "Choose a player to compare." : nil
    }

    /// Exact id only. A missing or duplicated id gets no substitute player.
    var selection: ScorerSelection10868 {
        guard let selectedID else { return .none }
        let matches = overview.filter { $0.id == selectedID }
        switch matches.count {
        case 1: return .overview(matches[0])
        case 0:
            if let selectedRow, selectedRow.id == selectedID { return .outside(selectedRow) }
            return .missing(selectedID)
        default: return .duplicate(selectedID)
        }
    }

    func isSelected(_ row: ScorerRow10868) -> Bool {
        if case .overview(let selected) = selection { return selected.id == row.id }
        return false
    }

    var outsideRow: ScorerRow10868? {
        if case .outside(let row) = selection { return row }
        return nil
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: Self.selectionUnavailable
        case .none, .overview, .outside: nil
        }
    }

    func pregameReading(_ row: ScorerRow10868) -> ScorerReading10868 {
        row.pregame.map { .value($0) } ?? .missing(row.pregameMissing)
    }

    /// During play only.
    func currentReading(_ row: ScorerRow10868) -> ScorerReading10868? {
        guard phase == .during else { return nil }
        switch row.current {
        case .recorded(let observation): return .value(observation)
        case .unavailable(let text), .stale(let text): return .missing(text)
        case .reached(let text): return .reached(text)
        }
    }

    /// The filled in-game key appears only beside an admitted recorded observation.
    func showsCurrentMark(_ row: ScorerRow10868) -> Bool {
        if case .value? = currentReading(row) { return true }
        return false
    }

    /// Nil before play — no actual column, and never an invented zero.
    func actualReading(_ row: ScorerRow10868) -> ScorerActual10868? {
        showsActual ? row.actual : nil
    }

    func pipCount(_ row: ScorerRow10868) -> Int? {
        guard case .count(let count)? = actualReading(row) else { return nil }
        return ScorerGeometry10868.pipCount(count.value)
    }

    func resultLine(_ row: ScorerRow10868) -> String? {
        phase == .final ? row.result : nil
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> ScorerTimingPresentation10868? {
        guard let timing, let selected = selection.row, selected.id == timing.playerID else { return nil }
        return hasBinding ? .disclosure(timing) : .expanded(timing)
    }

    func tileAction(_ row: ScorerRow10868, canSelect: Bool) -> ScorerAction10868? {
        canSelect ? .select(row.id) : nil
    }

    func detailsAction(canOpenDetails: Bool) -> ScorerAction10868? {
        guard canOpenDetails, let row = selection.row else { return nil }
        return .details(row.id)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([context, title].compactMap { $0 }).joined(separator: ". ")
    }

    func accessibilityLabel(for row: ScorerRow10868) -> String {
        ([row.name, row.team].compactMap { $0 }).joined(separator: ", ")
    }

    /// A tile: pregame chance and, once play has started, actual goals.
    func accessibilityValue(for row: ScorerRow10868) -> String {
        var parts = [Self.spoken(pregameReading(row), title: "Pregame chance")]
        if let actual = actualReading(row) { parts.append(Self.spoken(actual)) }
        return parts.joined(separator: "; ")
    }

    /// The selected comparison, which carries the in-game reading a tile does not.
    func accessibilityComparison(for row: ScorerRow10868) -> String {
        var parts = [Self.spoken(pregameReading(row), title: Self.pregameTitle)]
        if let current = currentReading(row) { parts.append(Self.spoken(current, title: Self.recordedTitle)) }
        if let actual = actualReading(row) { parts.append(Self.spoken(actual)) }
        if let result = resultLine(row) { parts.append(result) }
        return parts.joined(separator: "; ")
    }

    private static func spoken(_ reading: ScorerReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text), .reached(let text): "\(title): \(text)"
        }
    }

    private static func spoken(_ actual: ScorerActual10868) -> String {
        switch actual {
        case .count(let count):
            (["\(count.text) \(count.unit)", count.accessibilityDetail].compactMap { $0 }).joined(separator: ", ")
        case .unknown(let text):
            text
        }
    }
}

nonisolated enum ScorerTileArrangement10868: Hashable {
    /// Ring and count beside each other.
    case sideBySide
    /// Ring above count.
    case stacked
}

nonisolated struct ScorerGridPlan10868: Hashable {
    let columns: Int
    let arrangement: ScorerTileArrangement10868
}

nonisolated enum ScorerGeometry10868 {
    /// Beyond this a row of pips stops reading as a count; the figure carries it.
    static let maxPips = 6

    /// The ring's arc. Nil for anything outside 0...1 — bad input draws no arc,
    /// never a clipped or normalized one. A real zero is 0.
    static func ringFraction(_ probability: Double) -> Double? {
        guard probability.isFinite, probability >= 0, probability <= 1 else { return nil }
        return probability
    }

    /// Clear space from the ring's frame edge to its interior: half the 5pt
    /// stroke (it straddles the edge) plus a 2pt gap before the figure.
    static let ringInset: CGFloat = 4.5

    /// The ring's diameter for a figure of this measured size. The compact
    /// minimum while the figure's whole box fits inside the ring (its diagonal
    /// within the interior); otherwise just wide enough that it does. Only the
    /// ring grows — the figure is never shrunk, clipped or wrapped.
    static func ringSide(minimum: CGFloat, figure: CGSize, inset: CGFloat = ringInset) -> CGFloat {
        let diagonal = (figure.width * figure.width + figure.height * figure.height).squareRoot()
        let needed = (diagonal + 2 * inset).rounded(.up)
        guard needed.isFinite else { return minimum }
        return max(minimum, needed)
    }

    /// Decorative pips. Nil for a missing, negative or oversized count — never a
    /// synthesized zero. A real zero is 0 (no pips, figure "0").
    static func pipCount(_ value: Int?) -> Int? {
        guard let value, value >= 0, value <= maxPips else { return nil }
        return value
    }

    /// Widest first. Two columns while readable; one column at accessibility
    /// sizes or when two do not fit. Nothing shrinks to fit.
    static func plans(isAccessibilitySize: Bool) -> [ScorerGridPlan10868] {
        let columns = isAccessibilitySize ? [1] : [2, 1]
        return columns.flatMap { count in
            [ScorerGridPlan10868(columns: count, arrangement: .sideBySide),
             ScorerGridPlan10868(columns: count, arrangement: .stacked)]
        }
    }

    static func groups<Item>(_ items: [Item], columns: Int) -> [[Item]] {
        guard columns > 0 else { return [items] }
        return stride(from: 0, to: items.count, by: columns).map {
            Array(items[$0..<min($0 + columns, items.count)])
        }
    }
}

/// The pregame ring sized to its figure. Two subviews: the ring, then the
/// owner's figure. The square it reports is what the tile, the side-by-side /
/// stacked fallback and the column plan measure, so a long or qualified figure
/// ("≥99.5%") claims its real space instead of the ring's.
struct ScorerRingLayout10868: Layout {
    let minimumSide: CGFloat

    private func side(_ subviews: Subviews) -> CGFloat {
        ScorerGeometry10868.ringSide(minimum: minimumSide, figure: subviews[1].sizeThatFits(.unspecified))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 2 else { return .zero }
        let side = side(subviews)
        return CGSize(width: side, height: side)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let side = side(subviews)
        let center = CGPoint(x: bounds.midX, y: bounds.midY)
        subviews[0].place(at: center, anchor: .center, proposal: ProposedViewSize(width: side, height: side))
        subviews[1].place(at: center, anchor: .center, proposal: .unspecified)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum ScorerAccessibilityID10868 {
    static func tile(_ id: String) -> String { "scorer10868.tile.\(id)" }
    static func outside(_ id: String) -> String { "scorer10868.outside.\(id)" }
    static func comparison(_ id: String) -> String { "scorer10868.comparison.\(id)" }
    static func details(_ id: String) -> String { "scorer10868.details.\(id)" }
}

struct ScorerExpectationPresentation10868: View {
    let input: ScorerExpectationInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title3) private var countSize: CGFloat = 27
    @ScaledMetric(relativeTo: .title3) private var ringSize: CGFloat = 64
    @ScaledMetric(relativeTo: .title3) private var ringFigureSize: CGFloat = 20
    @ScaledMetric(relativeTo: .caption) private var pipSize: CGFloat = 7

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            Text(input.legend)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let instruction = input.instruction(canSelect: canSelect) {
                Text(instruction)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !input.overview.isEmpty {
                // Two columns, then one; ring and count side by side, then stacked.
                ViewThatFits(in: .horizontal) {
                    ForEach(ScorerGeometry10868.plans(isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { plan in
                        grid(plan)
                    }
                }
            }
            if let row = input.outsideRow {
                ViewThatFits(in: .horizontal) {
                    tile(row, arrangement: .sideBySide, id: ScorerAccessibilityID10868.outside(row.id))
                    tile(row, arrangement: .stacked, id: ScorerAccessibilityID10868.outside(row.id))
                }
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let row = input.selection.row {
                comparison(row)
                detailsButton(row)
            }
            timing
            if let summary = input.summary {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let context = input.context {
                Text(context).font(.caption).foregroundStyle(DS.textSecondary)
            }
            Text(input.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
    }

    // MARK: Overview

    private func grid(_ plan: ScorerGridPlan10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(ScorerGeometry10868.groups(input.overview, columns: plan.columns).enumerated()), id: \.offset) { _, group in
                HStack(alignment: .top, spacing: 8) {
                    ForEach(Array(group.enumerated()), id: \.offset) { _, row in
                        tile(row, arrangement: plan.arrangement, id: ScorerAccessibilityID10868.tile(row.id))
                    }
                    // A short last row keeps its tiles at full column width.
                    ForEach(group.count..<plan.columns, id: \.self) { _ in
                        Color.clear.frame(maxWidth: .infinity, maxHeight: 0)
                    }
                }
            }
        }
    }

    private func tile(_ row: ScorerRow10868, arrangement: ScorerTileArrangement10868, id: String) -> some View {
        let selected = input.isSelected(row) || input.outsideRow?.id == row.id
        let action = input.tileAction(row, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.name)
                        .font(.subheadline.weight(.semibold))
                        .underline(selected)
                        .foregroundStyle(DS.textPrimary)
                    if let team = row.team {
                        Text(team).font(.caption).foregroundStyle(DS.textSecondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                switch arrangement {
                case .sideBySide:
                    HStack(alignment: .center, spacing: 10) {
                        ring(row)
                        if input.showsActual {
                            Spacer(minLength: 0)
                            count(row)
                        }
                    }
                case .stacked:
                    VStack(alignment: .leading, spacing: 10) {
                        ring(row)
                        if input.showsActual { count(row) }
                    }
                }
            }
            .padding(11)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(selected ? DS.blue.opacity(0.06) : DS.surface, in: RoundedRectangle(cornerRadius: 13))
            .overlay(
                RoundedRectangle(cornerRadius: 13)
                    .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilityLabel(for: row))
        .accessibilityValue(input.accessibilityValue(for: row))
        .accessibilityHint(action == nil ? "" : "Selects this player’s comparison")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(id)
    }

    /// The pregame chance. A malformed value keeps the owner's figure with no arc;
    /// a missing one shows the owner's words, never an empty ring or 0%.
    /// An ordinary figure sits in the compact ring; one too wide for its
    /// interior widens the ring just enough, and the tile reserves that extent.
    private func ring(_ row: ScorerRow10868) -> some View {
        VStack(alignment: .center, spacing: 5) {
            switch input.pregameReading(row) {
            case .value(let observation):
                ScorerRingLayout10868(minimumSide: ringSize) {
                    ZStack {
                        Circle().stroke(DS.trackBg, lineWidth: 5)
                        if let fraction = ScorerGeometry10868.ringFraction(observation.probability) {
                            Circle()
                                .trim(from: 0, to: fraction)
                                .stroke(row.color, style: StrokeStyle(lineWidth: 5, lineCap: .butt))
                                .rotationEffect(.degrees(-90))
                        }
                    }
                    Text(observation.text)
                        .font(.system(size: ringFigureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                }
                .padding(3)
            case .missing(let text), .reached(let text):
                Text(text)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(minWidth: ringSize, minHeight: ringSize)
            }
            Text(ScorerExpectationInput10868.pregameTitle).font(.caption).foregroundStyle(DS.textSecondary)
        }
        .accessibilityHidden(true)
    }

    /// Actual goals: the owner's whole figure and unit; unknown is a dash plus
    /// the owner's words, never "0".
    @ViewBuilder private func count(_ row: ScorerRow10868) -> some View {
        if let actual = input.actualReading(row) {
            VStack(alignment: .center, spacing: 4) {
                switch actual {
                case .count(let count):
                    Text(count.text)
                        .font(.system(size: countSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    Text(count.unit)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let pips = input.pipCount(row), pips > 0 {
                        HStack(spacing: 3) {
                            ForEach(0..<pips, id: \.self) { _ in
                                Circle().fill(DS.textPrimary).frame(width: pipSize, height: pipSize)
                            }
                        }
                    }
                case .unknown(let text):
                    Text("—")
                        .font(.system(size: countSize, weight: .bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    Text(text)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .multilineTextAlignment(.center)
            .accessibilityHidden(true)
        }
    }

    // MARK: Selected comparison

    private func comparison(_ row: ScorerRow10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()
            VStack(alignment: .leading, spacing: 2) {
                Text(row.name).font(.title3.bold()).foregroundStyle(DS.textPrimary)
                if let team = row.team {
                    Text(team).font(.subheadline).foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            if input.phase == .during, let actual = input.actualReading(row) {
                comparisonActual(actual)
            }
            Text(input.comparisonHeading)
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 14) { comparisonValues(row) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 14) { comparisonValues(row) }
                    VStack(alignment: .leading, spacing: 14) { comparisonValues(row) }
                }
            }
            if let result = input.resultLine(row) {
                Text(result)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityLabel(for: row))
        .accessibilityValue(input.accessibilityComparison(for: row))
        .accessibilityIdentifier(ScorerAccessibilityID10868.comparison(row.id))
    }

    @ViewBuilder private func comparisonValues(_ row: ScorerRow10868) -> some View {
        comparisonValue(input.pregameReading(row), title: ScorerExpectationInput10868.pregameTitle, mark: .hollow)
        switch input.phase {
        case .before:
            EmptyView()
        case .during:
            if let current = input.currentReading(row) {
                comparisonValue(
                    current,
                    title: ScorerExpectationInput10868.recordedTitle,
                    mark: input.showsCurrentMark(row) ? .filled : nil
                )
            }
        case .final:
            if let actual = input.actualReading(row) {
                finalGoals(actual)
            }
        }
    }

    private enum KeyMark { case hollow, filled }

    private func comparisonValue(_ reading: ScorerReading10868, title: String, mark: KeyMark?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                if let mark { keyMark(mark) }
                Text(title).font(.caption).foregroundStyle(DS.textSecondary)
            }
            switch reading {
            case .value(let observation):
                // The whole figure keeps its width, so a narrow row stacks the
                // pair instead of squeezing or splitting a number.
                Text(observation.text)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            case .reached(let text):
                Label(text, systemImage: "checkmark")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.emeraldDark)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Final goals at the same scaled size as the pregame chance.
    private func finalGoals(_ actual: ScorerActual10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(ScorerExpectationInput10868.finalGoalsTitle).font(.caption).foregroundStyle(DS.textSecondary)
            switch actual {
            case .count(let count):
                Text(count.text)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
            case .unknown(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Goals so far beside the selected player's name during play.
    private func comparisonActual(_ actual: ScorerActual10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            switch actual {
            case .count(let count):
                Text(count.text)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                Text(count.unit).font(.subheadline).foregroundStyle(DS.textSecondary)
            case .unknown(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            Circle().fill(DS.cardBg).overlay(Circle().stroke(DS.textSecondary, lineWidth: 2)).frame(width: 9, height: 9)
        case .filled:
            Circle().fill(DS.textSecondary).frame(width: 9, height: 9)
        }
    }

    // MARK: Details and timing

    @ViewBuilder private func detailsButton(_ row: ScorerRow10868) -> some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails) {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("\(row.name) · original prop & times")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(ScorerAccessibilityID10868.details(row.id))
        }
    }

    @ViewBuilder private var timing: some View {
        switch input.timingPresentation(hasBinding: timingExpanded != nil) {
        case .disclosure(let content)?:
            if let timingExpanded {
                DisclosureGroup(isExpanded: timingExpanded) {
                    timingLines(content)
                } label: {
                    Text(content.title)
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44, alignment: .leading)
                }
            }
        case .expanded(let content)?:
            VStack(alignment: .leading, spacing: 6) {
                Text(content.title).font(.footnote.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                timingLines(content)
            }
        case nil:
            EmptyView()
        }
    }

    private func timingLines(_ content: ScorerTiming10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(content.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback; otherwise the same
    /// content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: ScorerAction10868?, @ViewBuilder content: () -> Content) -> some View {
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
