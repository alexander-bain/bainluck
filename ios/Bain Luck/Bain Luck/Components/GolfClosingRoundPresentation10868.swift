import SwiftUI

// GolfClosingRoundPresentation10868 — #10868 golf journey, final phase: the
// closing-round card.
//
// THE GAP. The winner archive draws each golfer's own four-round scorecard and
// the placement page draws pre-event chances inside result bands. Neither draws
// the field's final rounds as one distribution on a signed strokes-against-par
// axis with a selected golfer marked in it. This file adds only that card, its
// full-size content and its chooser mount; every leaf it can reuse it mounts
// read-only (the chooser, its resolver, the before-chance tie, the field strip
// geometry, the round-score value and tick, the page hold and stream relay).
//
// OWNERSHIP. The owner supplies every row identity, full name, canonical
// correspondence (or none), round, total and placement words, each row's dot
// cell (bin and stack), the shared axis with its ticks, under/over words and
// stack ceiling, the selection, featured and windowed row ids, the earlier
// chance with its observation id and dated reading, every word and every
// callback. The view never filters, elects, ranks, bins, stacks, reformats,
// complements or settles: it places the owner's cells on the owner's axis and
// lays out the owner's words.
//
// ADMISSION. One explicit owner admission gates all content, copy and actions:
// `GolfClosingRoundModel10868.admitted` is the owner's final content in the
// final phase, else nil, and every consumer reads it. Before or during the
// final round, or without the owner's final content, the card shows only the
// owner's unavailable words and, in full-size and chooser content, Back.
//
// TRUTH. A row draws a dot only when its id is carried once, its round is
// reported, its cell's bin equals that round, the bin sits on a valid axis, the
// stack is inside the owner's ceiling and no other drawable row claims the same
// cell; any other row stays reachable through the owner's choices and window
// with its own words. An earlier chance shows only when the row's own linked
// original resolves exactly once, the owner's observation id is readable and
// the chance is the original's own before reading, recorded, with a readable
// figure and date and a raw value in 0...1; otherwise the owner's unavailable
// words. An unlinked row stays selectable with no original drawn. Actual
// performance, finish, contract grade and earlier chance are separate lines;
// nothing here projects a score or explains a change. An owner's observation
// clock is shown only as the owner's words and is never called a tee or
// finish time.
//
// ACTIONS. In compact content each action (open, featured choice, details)
// calls the owner's interaction hook once and then the exact callback; inside a
// story stream the stream's activation runs instead, never both. Full-size and
// chooser content and Back call the exact callbacks with no hook. Without a
// callback there is no control. Building or reading the view calls nothing.
//
// LAYOUT. A compact width or an accessibility size stacks the selected golfer
// above the plot; a regular or unspecified width (iPad, Mac) places them side
// by side while both keep their minimum widths. Every new control is at least
// 44 pt at every text size. The plot is decorative under one spoken summary;
// every row is reachable as its own control through the owner's window.
//
// The host owns state, scrolling, navigation, focus, reader order, held
// selections and Back. This view keeps no state, runs no timer, replay or
// animation, holds no subscription and routes nothing.

// MARK: - Input

/// The owner's dot cell for one row: its bin on the shared axis and its height
/// in that bin's column. The owner bins and stacks; the view never does.
nonisolated struct GolfClosingRoundCell10868: Hashable {
    /// Strokes relative to par on the shared axis; equal to the row's round.
    let bin: Double
    /// 0 sits on the axis; each further row in the bin one step higher.
    let stack: Int
}

/// The owner's dated earlier chance for one row's own original.
nonisolated struct GolfClosingRoundBaseline10868: Equatable {
    /// The owner's id for the observation behind the chance.
    let observationID: String
    /// The raw chance tied to the before reading formatted from it.
    let chance: FieldOutlookBeforeChance10868
}

/// One completed final round, in the owner's order.
nonisolated struct GolfClosingRoundRow10868: Equatable {
    /// The owner's opaque row identity; handed back unchanged on choose.
    let id: String
    /// The golfer's full name; never shortened.
    let name: String
    /// The owner's canonical correspondence; nil when the owner links none.
    let original: FieldChooserOriginalRef10868?
    /// The round's actual score relative to par, in the owner's words.
    let round: GolfRoundScoreValue10868
    /// The owner's total figure.
    let total: String
    /// The owner's placement figure.
    let placement: String
    /// The owner's dot cell; nil draws no dot.
    let cell: GolfClosingRoundCell10868?
    /// The owner's earlier chance for this row's own original; nil is none.
    let baseline: GolfClosingRoundBaseline10868?
}

/// The owner's one signed strokes-against-par axis for every dot.
nonisolated struct GolfClosingRoundAxis10868: Equatable {
    let lower: Double
    let upper: Double
    /// How many dots one column holds; the plot's height.
    let stackCeiling: Int
    let ticks: [GolfRoundScoreTick10868]
    /// The under-par direction in words, drawn at the lower end.
    let underWords: String
    /// The over-par direction in words, drawn at the upper end.
    let overWords: String
    /// The axis meaning in words, including that lower is better.
    let words: String

    /// Finite, increasing, with zero on the axis and room for a dot.
    var isValid: Bool {
        lower.isFinite && upper.isFinite && lower < upper && lower <= 0 && upper >= 0 && stackCeiling > 0
    }
}

/// The owner's featured row ids, in the owner's order.
nonisolated struct GolfClosingRoundChoices10868: Equatable {
    /// Above the choices; nil draws none.
    let title: String?
    let rowIDs: [String]
}

/// The owner's bounded window over the rows, with its own steps.
nonisolated struct GolfClosingRoundWindow10868: Equatable {
    let title: String
    let rowIDs: [String]
    let previous: FieldHistoryAction10868?
    let next: FieldHistoryAction10868?
}

nonisolated struct GolfClosingRoundCopy10868: Equatable {
    let eyebrow: String
    let title: String
    /// Above the plot: what one dot is.
    let plotHeading: String
    /// The owner's count words for the plot; nil draws none.
    let plotCount: String?
    /// The plot's spoken name, including how the selection is marked.
    let graphicLabel: String
    /// The key beside the selection ring.
    let selectedKey: String
    /// Spoken with a selected row.
    let selectedWords: String
    let roundLabel: String
    let totalLabel: String
    let placementLabel: String
    /// Labels the earlier-chance line when no reading is shown.
    let baselineLabel: String
    let originalLabel: String
    /// Labels the contract-grade line when no grade is shown.
    let gradeLabel: String
    /// Shown when the owner selects no row.
    let noSelection: String
    /// Shown for a selection or choice that is not exactly one row.
    let rowUnavailable: String
    /// Shown for a blank figure.
    let valueUnavailable: String
    /// Shown when the selected row has no drawable dot.
    let unplaced: String
    let baselineUnavailable: String
    /// Shown when the owner links no original.
    let unlinked: String
    /// Shown when the owner's link does not resolve to exactly one original.
    let originalUnavailable: String
    let gradeUnavailable: String
    let note: String
    let openLabel: String
    let openHint: String?
    let changeGolferLabel: String
    /// Spoken hint on a row choice; nil none.
    let chooseHint: String?
}

/// The owner's final content: drawn only through the one admission.
nonisolated struct GolfClosingRoundContent10868: Equatable {
    /// The canonical catalogue and the chooser's own sections.
    let originals: FieldChooserInput10868
    let rows: [GolfClosingRoundRow10868]
    let axis: GolfClosingRoundAxis10868
    let selectedRowID: String?
    let featured: GolfClosingRoundChoices10868
    /// Nil draws no window.
    let window: GolfClosingRoundWindow10868?
    /// The owner's score-and-source details action; nil draws none.
    let details: FieldHistoryAction10868?
    let copy: GolfClosingRoundCopy10868
}

/// What stays in every phase: Back and the owner's unavailable words.
nonisolated struct GolfClosingRoundChrome10868: Equatable {
    let backLabel: String
    let backHint: String?
    let unavailableWords: String
}

/// The owner's one final admission.
nonisolated enum GolfClosingRoundAdmission10868: Equatable {
    case withheld
    case final(GolfClosingRoundContent10868)
}

nonisolated struct GolfClosingRoundInput10868: Equatable {
    let phase: FieldOutlookPhase10868
    let admission: GolfClosingRoundAdmission10868
    let chrome: GolfClosingRoundChrome10868
}

nonisolated enum GolfClosingRoundMode10868: Equatable {
    /// The card on the page or in the stream.
    case compact
    /// The full-size reader content.
    case full
    /// The owner's chooser over the canonical catalogue.
    case chooser
}

// MARK: - Model

nonisolated enum GolfClosingRoundSelection10868: Equatable {
    case row(GolfClosingRoundRow10868)
    /// A selection that is not exactly one row.
    case unavailable
    case unselected
}

nonisolated enum GolfClosingRoundOriginalState10868: Equatable {
    case linked(FieldChooserOriginal10868)
    case unlinked
    case unavailable
}

nonisolated enum GolfClosingRoundBaselineState10868: Equatable {
    case recorded(label: String, text: String, detail: String)
    case unavailable
}

/// One choice or window entry: the owner's id and its row, nil when the id is
/// not exactly one row.
nonisolated struct GolfClosingRoundEntry10868: Equatable {
    let id: String
    let row: GolfClosingRoundRow10868?
}

/// One drawable row: its fraction along the axis and its stack.
nonisolated struct GolfClosingRoundPlacedDot10868: Equatable {
    let rowID: String
    let fraction: Double
    let stack: Int
}

nonisolated struct GolfClosingRoundDot10868: Equatable {
    let rowID: String
    let center: CGPoint
    let isSelected: Bool
}

nonisolated struct GolfClosingRoundPlacedTick10868: Equatable {
    let fraction: Double
    let label: String
}

/// One owner label beside one owner figure.
nonisolated struct GolfClosingRoundPair10868: Equatable {
    let label: String
    let value: String
}

nonisolated struct GolfClosingRoundModel10868: Equatable {
    let input: GolfClosingRoundInput10868
    /// The one admission every consumer reads: the owner's final content in
    /// the final phase, else nil.
    let admitted: GolfClosingRoundContent10868?
    /// The chooser's own resolver over the owner's catalogue.
    let originals: FieldChooserModel10868?
    /// Placed rows in the owner's order.
    let placed: [GolfClosingRoundPlacedDot10868]
    /// Row position of every readable id carried exactly once.
    private let rowIndex: [String: Int]
    /// Originals linked by exactly one row.
    private let soleLinks: Set<FieldChooserOriginalRef10868>

    init(_ input: GolfClosingRoundInput10868) {
        self.input = input
        var content: GolfClosingRoundContent10868?
        if input.phase == .final, case .final(let finalContent) = input.admission {
            content = finalContent
        }
        admitted = content
        originals = content.map { FieldChooserModel10868($0.originals) }

        let rows = content?.rows ?? []
        var idCounts: [String: Int] = [:]
        var firstIndex: [String: Int] = [:]
        var linkCounts: [FieldChooserOriginalRef10868: Int] = [:]
        for (index, row) in rows.enumerated() {
            idCounts[row.id, default: 0] += 1
            if firstIndex[row.id] == nil { firstIndex[row.id] = index }
            if let ref = row.original { linkCounts[ref, default: 0] += 1 }
        }
        let identified = firstIndex.filter { entry in
            idCounts[entry.key] == 1
                && FieldEventPageModel10868.readable(entry.key) != nil
                && FieldEventPageModel10868.readable(rows[entry.value].name) != nil
        }
        rowIndex = identified
        soleLinks = Set(linkCounts.filter { $0.value == 1 }.keys)

        var candidates: [(cell: GolfClosingRoundCell10868, dot: GolfClosingRoundPlacedDot10868)] = []
        if let axis = content?.axis {
            for row in rows where identified[row.id] != nil {
                if let cell = row.cell, let dot = Self.placement(row, axis: axis) {
                    candidates.append((cell: cell, dot: dot))
                }
            }
        }
        var cellCounts: [GolfClosingRoundCell10868: Int] = [:]
        for candidate in candidates { cellCounts[candidate.cell, default: 0] += 1 }
        placed = candidates.filter { cellCounts[$0.cell] == 1 }.map { $0.dot }
    }

    static func == (lhs: GolfClosingRoundModel10868, rhs: GolfClosingRoundModel10868) -> Bool {
        lhs.input == rhs.input
    }

    /// A row's dot on the axis, before the shared-cell check: reported round,
    /// bin equal to it, on a valid axis, inside the stack ceiling.
    static func placement(_ row: GolfClosingRoundRow10868, axis: GolfClosingRoundAxis10868) -> GolfClosingRoundPlacedDot10868? {
        guard axis.isValid, let cell = row.cell,
              case .reported(let relative, _, _) = row.round,
              relative == cell.bin,
              cell.stack >= 0, cell.stack < axis.stackCeiling,
              let unit = GolfClosingRoundGeometry10868.fraction(cell.bin, axis: axis)
        else { return nil }
        return GolfClosingRoundPlacedDot10868(rowID: row.id, fraction: unit, stack: cell.stack)
    }

    var isAdmitted: Bool { admitted != nil }

    // MARK: Identity

    /// The row carrying this id exactly once, in admitted content.
    func row(_ id: String) -> GolfClosingRoundRow10868? {
        guard let admitted, let index = rowIndex[id] else { return nil }
        return admitted.rows[index]
    }

    var selection: GolfClosingRoundSelection10868 {
        guard let admitted, let id = admitted.selectedRowID else { return .unselected }
        guard let selected = row(id) else { return .unavailable }
        return .row(selected)
    }

    var selectedRowID: String? {
        if case .row(let selected) = selection { return selected.id }
        return nil
    }

    func isPlaced(_ row: GolfClosingRoundRow10868) -> Bool {
        placed.contains { $0.rowID == row.id }
    }

    func entries(_ ids: [String]) -> [GolfClosingRoundEntry10868] {
        ids.map { GolfClosingRoundEntry10868(id: $0, row: row($0)) }
    }

    var featured: [GolfClosingRoundEntry10868] { entries(admitted?.featured.rowIDs ?? []) }
    var window: [GolfClosingRoundEntry10868] { entries(admitted?.window?.rowIDs ?? []) }

    /// The exact id handed back on choose; none for an id that is not exactly one row.
    func chooseAction(_ id: String) -> String? {
        row(id)?.id
    }

    // MARK: Original, earlier chance, grade

    func original(_ row: GolfClosingRoundRow10868) -> GolfClosingRoundOriginalState10868 {
        guard let ref = row.original else { return .unlinked }
        guard soleLinks.contains(ref), let originals, let resolved = originals.resolve(ref).original else {
            return .unavailable
        }
        return .linked(resolved)
    }

    func baseline(_ row: GolfClosingRoundRow10868) -> GolfClosingRoundBaselineState10868 {
        guard let owned = row.baseline,
              FieldEventPageModel10868.readable(owned.observationID) != nil,
              case .linked(let linked) = original(row),
              owned.chance.ref == linked.ref,
              owned.chance.reading == FieldOutlookModel10868.beforeReading(linked.plan),
              case .recorded(let text, let detail) = owned.chance.reading.value,
              let label = FieldEventPageModel10868.readable(owned.chance.reading.label),
              FieldEventPageModel10868.readable(text) != nil,
              FieldEventPageModel10868.readable(detail) != nil,
              owned.chance.probability.isFinite,
              owned.chance.probability >= 0, owned.chance.probability <= 1
        else { return .unavailable }
        return .recorded(label: label, text: text, detail: detail)
    }

    /// The linked original's own result from the settlement owner, when readable.
    func grade(_ row: GolfClosingRoundRow10868) -> FieldChooserResult10868? {
        guard case .linked(let linked) = original(row), let result = linked.result,
              FieldEventPageModel10868.readable(result.title) != nil,
              FieldEventPageModel10868.readable(result.words) != nil
        else { return nil }
        return result
    }

    // MARK: Actions

    /// An owner action drawn only when available, readable and carrying an id
    /// no other drawn owner action carries.
    func action(_ candidate: FieldHistoryAction10868?) -> FieldHistoryAction10868? {
        guard let candidate, candidate.isAvailable,
              FieldEventPageModel10868.readable(candidate.id) != nil,
              FieldEventPageModel10868.readable(candidate.label) != nil
        else { return nil }
        let all: [FieldHistoryAction10868?] = [admitted?.details, admitted?.window?.previous, admitted?.window?.next]
        let sharing = all.compactMap { $0 }.filter { $0.id == candidate.id }
        guard sharing.count == 1 else { return nil }
        return candidate
    }

    var detailsAction: FieldHistoryAction10868? { action(admitted?.details) }
    var previousAction: FieldHistoryAction10868? { action(admitted?.window?.previous) }
    var nextAction: FieldHistoryAction10868? { action(admitted?.window?.next) }

    // MARK: Words

    /// The owner's figure, or the owner's words for a blank one.
    func shown(_ figure: String) -> String {
        FieldEventPageModel10868.readable(figure) ?? (admitted?.copy.valueUnavailable ?? "")
    }

    /// The round's own figure and words, in the owner's order.
    static func roundParts(_ round: GolfRoundScoreValue10868) -> [String] {
        switch round {
        case .reported(_, let text, let detail):
            return [text] + [FieldEventPageModel10868.readable(detail)].compactMap { $0 }
        case .unreported(let words):
            return [words]
        }
    }

    /// A choice's visible figures beside the owner's labels: round, total, placement.
    func entryPairs(_ row: GolfClosingRoundRow10868) -> [GolfClosingRoundPair10868] {
        guard let copy = admitted?.copy else { return [] }
        let roundFigure: String
        switch row.round {
        case .reported(_, let text, _): roundFigure = shown(text)
        case .unreported(let words): roundFigure = words
        }
        return [
            GolfClosingRoundPair10868(label: copy.roundLabel, value: roundFigure),
            GolfClosingRoundPair10868(label: copy.totalLabel, value: shown(row.total)),
            GolfClosingRoundPair10868(label: copy.placementLabel, value: shown(row.placement)),
        ]
    }

    /// One row in words: name, selection, round, total and placement.
    func rowSummary(_ row: GolfClosingRoundRow10868) -> String {
        guard let copy = admitted?.copy else { return "" }
        var parts = [row.name]
        if row.id == selectedRowID { parts.append(copy.selectedWords) }
        parts.append("\(copy.roundLabel): " + Self.roundParts(row.round).joined(separator: ", "))
        parts.append("\(copy.totalLabel): \(shown(row.total))")
        parts.append("\(copy.placementLabel): \(shown(row.placement))")
        return parts.joined(separator: ". ")
    }

    func baselineSpoken(_ row: GolfClosingRoundRow10868) -> String {
        guard let copy = admitted?.copy else { return "" }
        switch baseline(row) {
        case .recorded(let label, let text, let detail):
            return FieldChooserModel10868.spoken(FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail)))
        case .unavailable:
            return "\(copy.baselineLabel): \(copy.baselineUnavailable)"
        }
    }

    func originalSpoken(_ row: GolfClosingRoundRow10868) -> String {
        guard let copy = admitted?.copy else { return "" }
        switch original(row) {
        case .linked(let linked): return "\(copy.originalLabel): \(linked.name)"
        case .unlinked: return "\(copy.originalLabel): \(copy.unlinked)"
        case .unavailable: return "\(copy.originalLabel): \(copy.originalUnavailable)"
        }
    }

    func gradeSpoken(_ row: GolfClosingRoundRow10868) -> String {
        guard let copy = admitted?.copy else { return "" }
        if let result = grade(row) { return "\(result.title): \(result.words)" }
        return "\(copy.gradeLabel): \(copy.gradeUnavailable)"
    }

    /// The selected golfer in words; full content adds the original and grade.
    func selectedSummary(full: Bool) -> String {
        guard let copy = admitted?.copy else { return input.chrome.unavailableWords }
        switch selection {
        case .unselected: return copy.noSelection
        case .unavailable: return copy.rowUnavailable
        case .row(let selected):
            var parts = [rowSummary(selected), baselineSpoken(selected)]
            if full { parts += [gradeSpoken(selected), originalSpoken(selected)] }
            if !isPlaced(selected) { parts.append(copy.unplaced) }
            return parts.joined(separator: ". ")
        }
    }

    /// The plot in words: its name, the axis meaning and the selected round.
    var plotSummary: String {
        guard let admitted else { return input.chrome.unavailableWords }
        var parts = [admitted.copy.graphicLabel, admitted.axis.words]
        if let count = FieldEventPageModel10868.readable(admitted.copy.plotCount) { parts.append(count) }
        if case .row(let selected) = selection { parts.append(rowSummary(selected)) }
        return parts.joined(separator: ". ")
    }
}

// MARK: - Geometry

nonisolated enum GolfClosingRoundGeometry10868 {
    /// Every new local control: 44 pt at the smallest text size, the scaled
    /// size above that. Never a raw scaled metric.
    static func target(_ scaled: CGFloat) -> CGFloat {
        scaled.isFinite ? max(44, scaled) : 44
    }

    static let fieldDiameter: CGFloat = 7
    /// The selected ring, larger than a field dot.
    static let ringDiameter: CGFloat = 11
    static let ringLine: CGFloat = 2
    /// One stack step: a field dot and a gap.
    static let pitch: CGFloat = 9

    /// Whole ring and its line at either end of the strip.
    static var inset: CGFloat {
        FieldExpectationsGeometry10868.inset(markDiameter: ringDiameter + ringLine)
    }

    /// A value's fraction along the owner's axis, or none when it is not
    /// finite or off the axis — never clamped.
    static func fraction(_ value: Double, axis: GolfClosingRoundAxis10868) -> Double? {
        guard axis.isValid, value.isFinite, value >= axis.lower, value <= axis.upper else { return nil }
        return (value - axis.lower) / (axis.upper - axis.lower)
    }

    /// The owner's ticks on the axis with readable labels, in the owner's order.
    static func ticks(_ axis: GolfClosingRoundAxis10868) -> [GolfClosingRoundPlacedTick10868] {
        axis.ticks.compactMap { tick in
            guard let label = FieldEventPageModel10868.readable(tick.label),
                  let unit = fraction(tick.value, axis: axis) else { return nil }
            return GolfClosingRoundPlacedTick10868(fraction: unit, label: label)
        }
    }

    /// The plot height that holds the owner's stack ceiling with a whole ring
    /// at the top and bottom; none for an invalid axis.
    static func height(_ axis: GolfClosingRoundAxis10868) -> CGFloat? {
        guard axis.isValid else { return nil }
        return CGFloat(axis.stackCeiling - 1) * pitch + 2 * inset
    }

    /// One dot's centre: the shared strip x for its fraction and its stack
    /// above the axis. None when it cannot be drawn whole.
    static func center(_ dot: GolfClosingRoundPlacedDot10868, in size: CGSize) -> CGPoint? {
        guard size.height.isFinite, dot.stack >= 0,
              let markX = FieldFinishGeometry10868.x(of: dot.fraction, width: size.width, inset: inset)
        else { return nil }
        let markY = size.height - inset - CGFloat(dot.stack) * pitch
        guard markY >= inset - 0.001 else { return nil }
        return CGPoint(x: markX, y: markY)
    }

    static func dots(_ placed: [GolfClosingRoundPlacedDot10868], selected: String?, in size: CGSize) -> [GolfClosingRoundDot10868] {
        placed.compactMap { dot in
            center(dot, in: size).map { GolfClosingRoundDot10868(rowID: dot.rowID, center: $0, isSelected: dot.rowID == selected) }
        }
    }

    /// The zero line's x on the same strip.
    static func zeroX(_ axis: GolfClosingRoundAxis10868, width: CGFloat) -> CGFloat? {
        guard let zero = fraction(0, axis: axis) else { return nil }
        return FieldFinishGeometry10868.x(of: zero, width: width, inset: inset)
    }
}

// MARK: - Controls

nonisolated enum GolfClosingRoundControl10868: Hashable {
    case back
    case open
    case chooser
    case choose(String)
    case action(String)
    case chooserList
}

nonisolated enum GolfClosingRoundAccessibilityID10868 {
    static let card = "golfClosingRound10868.card"
    static let plot = "golfClosingRound10868.plot"
    static let selected = "golfClosingRound10868.selected"
    static let back = "golfClosingRound10868.back"
    static let open = "golfClosingRound10868.open"
    static let chooser = "golfClosingRound10868.chooser"
    static func featured(_ id: String) -> String { "golfClosingRound10868.featured.\(id)" }
    static func window(_ id: String) -> String { "golfClosingRound10868.window.\(id)" }
    static func action(_ id: String) -> String { "golfClosingRound10868.action.\(id)" }
}

/// What each control calls in this mode, decided once from the admission.
struct GolfClosingRoundWiring10868 {
    var back: (() -> Void)? = nil
    var open: (() -> Void)? = nil
    var chooser: (() -> Void)? = nil
    var chooseRow: ((String) -> Void)? = nil
    var action: ((String) -> Void)? = nil
    var chooseOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var chooserControl: ((FieldChooserControl10868) -> Void)? = nil
}

/// The one control every new local touch area uses: at least 44 pt at every
/// text size.
struct GolfClosingRoundButton10868: View {
    let title: String
    let values: [GolfClosingRoundPair10868]
    let isSelected: Bool
    let spokenLabel: String
    let hint: String?
    let identifier: String
    let action: () -> Void

    init(title: String, values: [GolfClosingRoundPair10868] = [], isSelected: Bool = false, spokenLabel: String? = nil,
         hint: String? = nil, identifier: String, action: @escaping () -> Void) {
        self.title = title
        self.values = values
        self.isSelected = isSelected
        self.spokenLabel = spokenLabel ?? title
        self.hint = hint
        self.identifier = identifier
        self.action = action
    }

    @ScaledMetric(relativeTo: .body) private var scaledTarget: CGFloat = 44

    var target: CGFloat { GolfClosingRoundGeometry10868.target(scaledTarget) }

    private var pairViews: some View {
        ForEach(Array(values.enumerated()), id: \.offset) { _, pair in
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(pair.label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                Text(pair.value)
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
            }
        }
    }

    var body: some View {
        Button(action: action) {
            HStack(alignment: .center, spacing: 10) {
                if isSelected {
                    Circle()
                        .strokeBorder(DS.blue, lineWidth: GolfClosingRoundGeometry10868.ringLine)
                        .frame(width: GolfClosingRoundGeometry10868.ringDiameter,
                               height: GolfClosingRoundGeometry10868.ringDiameter)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    if !values.isEmpty {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 12) { pairViews }
                            VStack(alignment: .leading, spacing: 2) { pairViews }
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .frame(minWidth: target, maxWidth: .infinity, minHeight: target, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 10).fill(isSelected ? DS.blue.opacity(0.08) : DS.surface))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(spokenLabel)
        .accessibilityHint(hint ?? "")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier(identifier)
    }
}

// MARK: - Presentation

struct GolfClosingRoundPresentation10868: View {
    let input: GolfClosingRoundInput10868
    let mode: GolfClosingRoundMode10868
    /// The stream's activation when this card sits in a story stream.
    let activation: StoryStreamCardActivation10868?
    /// Opens the full-size content (compact only).
    let onOpen: (() -> Void)?
    /// Back from full-size or chooser content; stays in every phase.
    let onBack: (() -> Void)?
    /// Opens the chooser (full-size only).
    let onChooser: (() -> Void)?
    /// The exact row id of a featured or window choice.
    let onChooseRow: ((String) -> Void)?
    /// The exact original chosen in the chooser.
    let onChooseOriginal: ((FieldChooserOriginalRef10868) -> Void)?
    let onChooserControl: ((FieldChooserControl10868) -> Void)?
    /// The exact owner action id: details, window steps.
    let onAction: ((String) -> Void)?
    /// Called once before a compact page action reaches its owner.
    let onInteraction: (() -> Void)?
    let model: GolfClosingRoundModel10868

    init(
        input: GolfClosingRoundInput10868,
        mode: GolfClosingRoundMode10868 = .compact,
        activation: StoryStreamCardActivation10868? = nil,
        onOpen: (() -> Void)? = nil,
        onBack: (() -> Void)? = nil,
        onChooser: (() -> Void)? = nil,
        onChooseRow: ((String) -> Void)? = nil,
        onChooseOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil,
        onChooserControl: ((FieldChooserControl10868) -> Void)? = nil,
        onAction: ((String) -> Void)? = nil,
        onInteraction: (() -> Void)? = nil
    ) {
        self.input = input
        self.mode = mode
        self.activation = activation
        self.onOpen = onOpen
        self.onBack = onBack
        self.onChooser = onChooser
        self.onChooseRow = onChooseRow
        self.onChooseOriginal = onChooseOriginal
        self.onChooserControl = onChooserControl
        self.onAction = onAction
        self.onInteraction = onInteraction
        self.model = GolfClosingRoundModel10868(input)
    }

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .largeTitle) private var figureSize: CGFloat = 34
    @ScaledMetric(relativeTo: .body) private var selectedMinWidth: CGFloat = 280
    @ScaledMetric(relativeTo: .body) private var plotMinWidth: CGFloat = 340

    // MARK: Wiring

    /// A compact card action: the stream's activation inside a stream, else
    /// the owner's interaction hook once — never both.
    private func card<Value>(_ action: ((Value) -> Void)?) -> ((Value) -> Void)? {
        guard activation != nil else { return FieldEventPagePresentation10868.held(action, by: onInteraction) }
        return FieldEventPagePresentation10868.relay(action, through: activation)
    }

    private func cardAction(_ action: (() -> Void)?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let activation else { return FieldEventPagePresentation10868.heldAction(action, by: onInteraction) }
        return {
            activation.request()
            action()
        }
    }

    /// What every control calls. Nothing but Back before the owner's final
    /// admission; full-size and chooser content and Back are exact.
    var wiring: GolfClosingRoundWiring10868 {
        let back = mode == .compact ? nil : onBack
        guard model.isAdmitted else { return GolfClosingRoundWiring10868(back: back) }
        switch mode {
        case .compact:
            return GolfClosingRoundWiring10868(open: cardAction(onOpen), chooseRow: card(onChooseRow), action: card(onAction))
        case .full:
            return GolfClosingRoundWiring10868(back: back, chooser: onChooser, chooseRow: onChooseRow, action: onAction)
        case .chooser:
            return GolfClosingRoundWiring10868(back: back, chooseOriginal: onChooseOriginal, chooserControl: onChooserControl)
        }
    }

    func backControl() -> (() -> Void)? {
        guard FieldEventPageModel10868.readable(input.chrome.backLabel) != nil else { return nil }
        return wiring.back
    }

    func openControl() -> (() -> Void)? {
        guard let copy = model.admitted?.copy, FieldEventPageModel10868.readable(copy.openLabel) != nil else { return nil }
        return wiring.open
    }

    func chooserOpenControl() -> (() -> Void)? {
        guard let copy = model.admitted?.copy, FieldEventPageModel10868.readable(copy.changeGolferLabel) != nil else { return nil }
        return wiring.chooser
    }

    func chooseControl(_ entry: GolfClosingRoundEntry10868) -> (() -> Void)? {
        guard let id = model.chooseAction(entry.id), let choose = wiring.chooseRow else { return nil }
        return { choose(id) }
    }

    func actionControl(_ candidate: FieldHistoryAction10868?) -> (() -> Void)? {
        guard let valid = model.action(candidate), let perform = wiring.action else { return nil }
        let id = valid.id
        return { perform(id) }
    }

    /// The owner's chooser list is content in admitted chooser mode; it is a
    /// control only with a chooser callback.
    var chooserListShown: Bool {
        model.isAdmitted && mode == .chooser
    }

    /// Every control this mode draws, in drawing order — the same predicates
    /// the body draws from.
    var controls: [GolfClosingRoundControl10868] {
        var list: [GolfClosingRoundControl10868] = []
        if backControl() != nil { list.append(.back) }
        guard let content = model.admitted else { return list }
        let featured = model.featured.compactMap { entry -> GolfClosingRoundControl10868? in
            chooseControl(entry) == nil ? nil : GolfClosingRoundControl10868.choose(entry.id)
        }
        switch mode {
        case .compact:
            list += featured
            if openControl() != nil { list.append(.open) }
            if actionControl(content.details) != nil, let id = content.details?.id { list.append(.action(id)) }
        case .full:
            if chooserOpenControl() != nil { list.append(.chooser) }
            list += featured
            list += model.window.compactMap { entry -> GolfClosingRoundControl10868? in
                chooseControl(entry) == nil ? nil : GolfClosingRoundControl10868.choose(entry.id)
            }
            if actionControl(content.window?.previous) != nil, let id = content.window?.previous?.id { list.append(.action(id)) }
            if actionControl(content.window?.next) != nil, let id = content.window?.next?.id { list.append(.action(id)) }
            if actionControl(content.details) != nil, let id = content.details?.id { list.append(.action(id)) }
        case .chooser:
            if chooserListShown && (wiring.chooseOriginal != nil || wiring.chooserControl != nil) { list.append(.chooserList) }
        }
        return list
    }

    // MARK: Body

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let back = backControl() {
                GolfClosingRoundButton10868(title: input.chrome.backLabel, hint: input.chrome.backHint,
                                            identifier: GolfClosingRoundAccessibilityID10868.back, action: back)
            }
            if let content = model.admitted {
                switch mode {
                case .compact: compact(content)
                case .full: full(content)
                case .chooser: chooser(content)
                }
            } else if let words = FieldEventPageModel10868.readable(input.chrome.unavailableWords) {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(mode == .compact ? 16 : 0)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(mode == .compact ? DS.cardBg : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: mode == .compact ? 14 : 0))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(mode == .compact ? DS.border : Color.clear, lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(GolfClosingRoundAccessibilityID10868.card)
    }

    @ViewBuilder private func compact(_ content: GolfClosingRoundContent10868) -> some View {
        header(content.copy)
        arranged(content, full: false)
        note(content.copy)
        if let open = openControl() {
            GolfClosingRoundButton10868(title: content.copy.openLabel, hint: content.copy.openHint,
                                        identifier: GolfClosingRoundAccessibilityID10868.open, action: open)
        }
        ownerActionControl(content.details)
    }

    @ViewBuilder private func full(_ content: GolfClosingRoundContent10868) -> some View {
        header(content.copy)
        if let openChooser = chooserOpenControl() {
            GolfClosingRoundButton10868(title: content.copy.changeGolferLabel,
                                        identifier: GolfClosingRoundAccessibilityID10868.chooser, action: openChooser)
        }
        arranged(content, full: true)
        windowSection(content)
        note(content.copy)
        ownerActionControl(content.details)
    }

    @ViewBuilder private func chooser(_ content: GolfClosingRoundContent10868) -> some View {
        if chooserListShown {
            FieldContenderChooserPresentation10868(input: content.originals,
                                                   onChoose: wiring.chooseOriginal,
                                                   onControl: wiring.chooserControl)
        }
    }

    private func header(_ copy: GolfClosingRoundCopy10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = FieldEventPageModel10868.readable(copy.eyebrow) {
                Text(eyebrow)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(copy.title)
                .font(.title3.bold())
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
        }
    }

    private func note(_ copy: GolfClosingRoundCopy10868) -> some View {
        Text(copy.note)
            .font(.footnote)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func ownerActionControl(_ candidate: FieldHistoryAction10868?) -> some View {
        if let perform = actionControl(candidate), let valid = model.action(candidate) {
            GolfClosingRoundButton10868(title: valid.label, spokenLabel: valid.spokenLabel,
                                        identifier: GolfClosingRoundAccessibilityID10868.action(valid.id), action: perform)
        }
    }

    // MARK: Arrangement

    @ViewBuilder private func arranged(_ content: GolfClosingRoundContent10868, full: Bool) -> some View {
        let tries = FieldEventPageModel10868.arrangements(sizeClass: sizeClass,
                                                          accessibilitySize: typeSize.isAccessibilitySize)
        if tries == [.stacked] {
            stacked(content, full: full)
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 24) {
                    selectedBlock(content, full: full)
                        .frame(minWidth: selectedMinWidth, maxWidth: .infinity, alignment: .topLeading)
                    plotBlock(content)
                        .frame(minWidth: plotMinWidth, maxWidth: .infinity, alignment: .topLeading)
                        .layoutPriority(1)
                }
                stacked(content, full: full)
            }
        }
    }

    private func stacked(_ content: GolfClosingRoundContent10868, full: Bool) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            selectedBlock(content, full: full)
            plotBlock(content)
        }
    }

    // MARK: Selected golfer

    @ViewBuilder private func selectedBlock(_ content: GolfClosingRoundContent10868, full: Bool) -> some View {
        let copy = content.copy
        VStack(alignment: .leading, spacing: 10) {
            switch model.selection {
            case .unselected:
                ownerWords(copy.noSelection)
            case .unavailable:
                ownerWords(copy.rowUnavailable)
            case .row(let selected):
                Text(selected.name)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                roundLine(selected, copy: copy)
                labelled(copy.placementLabel, model.shown(selected.placement))
                labelled(copy.totalLabel, model.shown(selected.total))
                baselineLine(selected, copy: copy)
                if full {
                    gradeLine(selected, copy: copy)
                    originalLine(selected, copy: copy)
                }
                if !model.isPlaced(selected) {
                    ownerWords(copy.unplaced)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.selectedSummary(full: full))
        .accessibilityIdentifier(GolfClosingRoundAccessibilityID10868.selected)
    }

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func roundLine(_ row: GolfClosingRoundRow10868, copy: GolfClosingRoundCopy10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(copy.roundLabel)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            switch row.round {
            case .reported(_, let text, let detail):
                Text(text)
                    .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let words = FieldEventPageModel10868.readable(detail) {
                    Text(words)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            case .unreported(let words):
                ownerWords(words)
            }
        }
    }

    @ViewBuilder private func labelled(_ label: String, _ value: String, detail: String? = nil) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 2) {
                labelText(label)
                valueText(value)
                if let detail { detailText(detail) }
            }
        } else {
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    labelText(label)
                    valueText(value)
                }
                if let detail { detailText(detail) }
            }
        }
    }

    private func labelText(_ label: String) -> some View {
        Text(label)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func valueText(_ value: String) -> some View {
        Text(value)
            .font(.subheadline.weight(.semibold).monospacedDigit())
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func detailText(_ detail: String) -> some View {
        Text(detail)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func baselineLine(_ row: GolfClosingRoundRow10868, copy: GolfClosingRoundCopy10868) -> some View {
        switch model.baseline(row) {
        case .recorded(let label, let text, let detail):
            labelled(label, text, detail: detail)
        case .unavailable:
            labelled(copy.baselineLabel, copy.baselineUnavailable)
        }
    }

    @ViewBuilder private func gradeLine(_ row: GolfClosingRoundRow10868, copy: GolfClosingRoundCopy10868) -> some View {
        if let result = model.grade(row) {
            labelled(result.title, result.words)
        } else {
            labelled(copy.gradeLabel, copy.gradeUnavailable)
        }
    }

    @ViewBuilder private func originalLine(_ row: GolfClosingRoundRow10868, copy: GolfClosingRoundCopy10868) -> some View {
        switch model.original(row) {
        case .linked(let linked): labelled(copy.originalLabel, linked.name)
        case .unlinked: labelled(copy.originalLabel, copy.unlinked)
        case .unavailable: labelled(copy.originalLabel, copy.originalUnavailable)
        }
    }

    // MARK: Plot

    private func plotBlock(_ content: GolfClosingRoundContent10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            plot(content)
            featuredSection(content)
        }
    }

    private func plot(_ content: GolfClosingRoundContent10868) -> some View {
        let copy = content.copy
        let axis = content.axis
        let placedTicks = GolfClosingRoundGeometry10868.ticks(axis)
        let placed = model.placed
        let selectedID = model.selectedRowID
        return VStack(alignment: .leading, spacing: 6) {
            plotHeading(copy)
            if let plotHeight = GolfClosingRoundGeometry10868.height(axis) {
                Canvas { context, size in
                    if let zero = GolfClosingRoundGeometry10868.zeroX(axis, width: size.width) {
                        context.stroke(Path { path in
                            path.move(to: CGPoint(x: zero, y: 0))
                            path.addLine(to: CGPoint(x: zero, y: size.height))
                        }, with: .color(DS.textSecondary), lineWidth: 1)
                    }
                    context.stroke(Path { path in
                        path.move(to: CGPoint(x: 0, y: size.height - 0.5))
                        path.addLine(to: CGPoint(x: size.width, y: size.height - 0.5))
                    }, with: .color(DS.border), lineWidth: 1)
                    let drawn = GolfClosingRoundGeometry10868.dots(placed, selected: selectedID, in: size)
                    let field = GolfClosingRoundGeometry10868.fieldDiameter
                    for dot in drawn where !dot.isSelected {
                        let rect = CGRect(x: dot.center.x - field / 2, y: dot.center.y - field / 2, width: field, height: field)
                        context.fill(Path(ellipseIn: rect), with: .color(DS.textSecondary.opacity(0.45)))
                    }
                    let ring = GolfClosingRoundGeometry10868.ringDiameter
                    for dot in drawn where dot.isSelected {
                        let rect = CGRect(x: dot.center.x - ring / 2, y: dot.center.y - ring / 2, width: ring, height: ring)
                        context.fill(Path(ellipseIn: rect), with: .color(DS.cardBg))
                        context.stroke(Path(ellipseIn: rect), with: .color(DS.blue), lineWidth: GolfClosingRoundGeometry10868.ringLine)
                    }
                }
                .frame(height: plotHeight)
                FieldExpectationsAxisLayout10868(units: placedTicks.map { $0.fraction },
                                                 inset: GolfClosingRoundGeometry10868.inset,
                                                 spacing: 4) {
                    ForEach(Array(placedTicks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.label)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(DS.textSecondary)
                    }
                }
                directions(axis)
                if selectedID != nil {
                    HStack(alignment: .center, spacing: 6) {
                        Circle()
                            .strokeBorder(DS.blue, lineWidth: GolfClosingRoundGeometry10868.ringLine)
                            .frame(width: GolfClosingRoundGeometry10868.ringDiameter,
                                   height: GolfClosingRoundGeometry10868.ringDiameter)
                        Text(copy.selectedKey)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            Text(axis.words)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.plotSummary)
        .accessibilityIdentifier(GolfClosingRoundAccessibilityID10868.plot)
    }

    @ViewBuilder private func plotHeading(_ copy: GolfClosingRoundCopy10868) -> some View {
        let count = FieldEventPageModel10868.readable(copy.plotCount)
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 2) {
                detailText(copy.plotHeading)
                if let count { detailText(count) }
            }
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                detailText(copy.plotHeading)
                Spacer(minLength: 8)
                if let count { detailText(count) }
            }
        }
    }

    @ViewBuilder private func directions(_ axis: GolfClosingRoundAxis10868) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 2) {
                detailText(axis.underWords)
                detailText(axis.overWords)
            }
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                detailText(axis.underWords)
                Spacer(minLength: 8)
                detailText(axis.overWords)
                    .multilineTextAlignment(.trailing)
            }
        }
    }

    // MARK: Choices and window

    @ViewBuilder private func featuredSection(_ content: GolfClosingRoundContent10868) -> some View {
        let entries = model.featured
        if !entries.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                if let title = FieldEventPageModel10868.readable(content.featured.title) {
                    detailText(title)
                }
                ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                    entryView(entry, copy: content.copy, identifier: GolfClosingRoundAccessibilityID10868.featured(entry.id))
                }
            }
        }
    }

    @ViewBuilder private func windowSection(_ content: GolfClosingRoundContent10868) -> some View {
        if let window = content.window {
            VStack(alignment: .leading, spacing: 6) {
                Text(window.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array(model.window.enumerated()), id: \.offset) { _, entry in
                    entryView(entry, copy: content.copy, identifier: GolfClosingRoundAccessibilityID10868.window(entry.id))
                }
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 6) {
                        ownerActionControl(window.previous)
                        ownerActionControl(window.next)
                    }
                } else {
                    HStack(alignment: .top, spacing: 8) {
                        ownerActionControl(window.previous)
                        ownerActionControl(window.next)
                    }
                }
            }
        }
    }

    @ViewBuilder private func entryView(_ entry: GolfClosingRoundEntry10868, copy: GolfClosingRoundCopy10868, identifier: String) -> some View {
        if let row = entry.row, let choose = chooseControl(entry) {
            GolfClosingRoundButton10868(
                title: row.name,
                values: model.entryPairs(row),
                isSelected: row.id == model.selectedRowID,
                spokenLabel: model.rowSummary(row),
                hint: copy.chooseHint,
                identifier: identifier,
                action: choose)
        } else if let row = entry.row {
            VStack(alignment: .leading, spacing: 2) {
                valueText(row.name)
                detailText(model.shown(row.placement))
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.rowSummary(row))
        } else {
            ownerWords(copy.rowUnavailable)
        }
    }
}
