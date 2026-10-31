import SwiftUI

// #10868 — the half-by-half card across a match's lifecycle: each named
// outcome's original pre-match chance for every period, plotted on one shared
// probability scale with the periods as categorical positions, and below it
// the selected outcome's own tile per period with its phase reading.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `SoccerHalfResultsCard.tsx` +
// `soccerHalfResults.ts`; chart intent from hockey-before-outlook-v375
// `native-halves/SoccerHalfResultsCard.swift`). Every plotted point is a
// pre-match chance for that period. A line joins one outcome's chances in
// neighbouring periods to compare the periods: it is never a time series,
// never a movement and never a before-to-current shift.
//
// Every period, outcome series, membership, order, figure, tick, axis bound,
// clock, missing word, current reading and result arrives resolved by the
// owner and is shown verbatim. Each series names its chance in each period
// explicitly through the period's identity — nothing is paired by name or by
// position. This layer never formats, rounds, ranks, sorts, normalizes or
// completes chances, never picks a winner or a favourite, never reads a clock,
// score, cache or subscription, never infers a result, and never shows a
// settled price as a chance. A missing result is never a loss, and one period
// never lends a chance, a state or a result to another.
//
// Selection, Details and focus stay with the host: the view keeps no selected
// state, no sheet and no subscription. With no callback, content is shown
// without a button and no tap is asked for.
//
// Host binding still owed — not available at this base. An owner must supply:
//   • the ordered periods (opaque identity + label) and the ordered outcome
//     series (opaque identity, label, colour and point shape),
//   • per series and period, the exact original prop identity, an admitted
//     pregame observation (raw value, formatted figure, full clock/source) or
//     its own missing words, during play an independently admitted current
//     reading or its own unavailable / stale words with currentness applied,
//     and the owner-resolved result (won, lost, or unconfirmed with words);
// and for the card: the headline and captions, the axis bounds and formatted
// ticks, the results caption for the current selection and the words below.

/// One admitted chance. `probability` drives plot geometry only; `text` is
/// what the reader sees.
nonisolated struct PeriodOutcomeObservation10868: Equatable {
    let probability: Double
    let text: String
    /// Full clock and source for VoiceOver ("pinned Oct 12, 4:47:12 AM PT · Polymarket").
    let accessibilityDetail: String
}

/// The owner's in-game reading for one original, currentness applied.
nonisolated enum PeriodOutcomeCurrent10868: Equatable {
    /// An independently admitted, current recorded observation.
    case recorded(PeriodOutcomeObservation10868)
    /// No current reading ("Current chance unavailable").
    case unavailable(String)
    /// A reading exists but is no longer current ("No update since 5:12 AM").
    case stale(String)
}

/// The owner-resolved result of one original. There is no Bool, so an absent
/// result can never read as lost.
nonisolated enum PeriodOutcomeResult10868: Equatable {
    /// "Won"
    case won(String)
    /// "Lost"
    case lost(String)
    /// No admitted result — pending, missing, ambiguous or conflicting
    /// ("Unconfirmed").
    case unconfirmed(String)

    var text: String {
        switch self {
        case .won(let text), .lost(let text), .unconfirmed(let text): text
        }
    }

    var isAdmitted: Bool {
        if case .unconfirmed = self { return false }
        return true
    }

    /// The ✓ / ✕ beside an admitted result. Unconfirmed has none, so unknown
    /// never reads as a loss.
    var mark: PeriodOutcomeResultMark10868? {
        switch self {
        case .won: .positive
        case .lost: .negative
        case .unconfirmed: nil
        }
    }
}

nonisolated enum PeriodOutcomeResultMark10868: Equatable {
    case positive
    case negative
}

/// One original prop: one outcome in one period. `periodID` is the explicit
/// association to a period — never inferred from order or label.
nonisolated struct PeriodOutcomeCell10868: Equatable {
    /// Opaque original prop identity, passed back exactly.
    let id: String
    let periodID: String
    let pregame: PeriodOutcomeObservation10868?
    /// "No pre-match chance"
    let pregameMissing: String
    /// Read only during play.
    let current: PeriodOutcomeCurrent10868
    /// Read during play once admitted, and after the final.
    let result: PeriodOutcomeResult10868
}

/// The point shape of a series, so series stay distinct without colour.
nonisolated enum PeriodOutcomeSymbol10868: Equatable {
    case circle
    case square
    case diamond
    case triangle
}

/// One named outcome across the periods (a side, or "Draw").
nonisolated struct PeriodOutcomeSeries10868: Equatable {
    /// Opaque owner identity, passed back exactly on select.
    let id: String
    let label: String
    let tint: Color
    let symbol: PeriodOutcomeSymbol10868
    /// This outcome's originals, one per period it was offered in.
    let cells: [PeriodOutcomeCell10868]
}

/// One categorical position on the plot ("First half").
nonisolated struct PeriodOutcomePeriod10868: Equatable {
    /// Opaque owner identity that cells name.
    let id: String
    let label: String
}

nonisolated enum PeriodOutcomePhase10868: Equatable {
    case before
    case during
    case final
}

nonisolated struct PeriodOutcomeTick10868: Equatable {
    /// Raw probability, in the same units as the axis bounds.
    let value: Double
    /// The owner's label ("25%").
    let text: String
}

/// The plot's shared scale: raw bounds plus the owner's formatted ticks.
nonisolated struct PeriodOutcomeAxis10868: Equatable {
    let lower: Double
    let upper: Double
    let ticks: [PeriodOutcomeTick10868]

    /// A probability scale: finite, nonempty and inside 0...1. Anything else
    /// draws no marks or ticks — the bounds are never clamped or normalized.
    var isValid: Bool {
        lower.isFinite && upper.isFinite && lower >= 0 && upper <= 1 && upper > lower
    }
}

/// The caller's words, chosen explicitly — never parsed from a label.
nonisolated struct PeriodOutcomeWords10868: Equatable {
    /// "Pre-match chance" — shown, and spoken before the pregame figure.
    let pregameTitle: String
    /// "Not started" — every period's state before play.
    let notStarted: String
    /// "Current chance" — shown, and spoken before a current reading.
    let currentTitle: String
    /// "Half result" — shown, and spoken before a result admitted during play.
    let liveResultTitle: String
    /// "Final result" — shown, and spoken before each result after the final.
    let finalResultTitle: String
    /// "Selected outcome unavailable."
    let selectionUnavailable: String
    /// "Not offered for this half" — a period this outcome has no single
    /// original for.
    let cellUnavailable: String
    /// "Shows this outcome’s chances"
    let selectHint: String
    /// "Opens the original prop"
    let detailsHint: String
}

nonisolated enum PeriodOutcomeSelection10868: Equatable {
    case none
    case selected(PeriodOutcomeSeries10868)
    /// No series carries the selected id.
    case missing(String)
    /// More than one series carries the selected id.
    case duplicate(String)

    var series: PeriodOutcomeSeries10868? {
        if case .selected(let series) = self { return series }
        return nil
    }
}

/// A series' original for one period, by exact period identity.
nonisolated enum PeriodOutcomeCellLookup10868: Equatable {
    case cell(PeriodOutcomeCell10868)
    /// The series has no original for this period.
    case absent
    /// More than one original, or a period identity used twice — nothing is chosen.
    case ambiguous

    var cell: PeriodOutcomeCell10868? {
        if case .cell(let cell) = self { return cell }
        return nil
    }
}

nonisolated enum PeriodOutcomeReading10868: Equatable {
    case value(PeriodOutcomeObservation10868)
    case missing(String)

    var text: String {
        switch self {
        case .value(let observation): observation.text
        case .missing(let text): text
        }
    }
}

/// What sits beside the pregame chance in a period tile.
nonisolated enum PeriodOutcomeSecondReading10868: Equatable {
    /// Before play.
    case notStarted(String)
    /// During play, before an admitted result.
    case current(PeriodOutcomeReading10868)
    /// An admitted result during play, or any result after the final.
    case result(PeriodOutcomeResult10868)
}

/// One plotted pregame chance.
nonisolated struct PeriodOutcomePlotPoint10868: Equatable {
    let periodIndex: Int
    /// Position on the axis, 0...1.
    let fraction: Double
}

/// A line between one series' chances in two neighbouring periods.
nonisolated struct PeriodOutcomeSegment10868: Equatable {
    let from: PeriodOutcomePlotPoint10868
    let to: PeriodOutcomePlotPoint10868
}

/// The selected series' figure for one period, shown in the band above the
/// plot and aligned to that period. `fraction` is its point's position.
nonisolated struct PeriodOutcomeAnnotation10868: Equatable {
    let periodIndex: Int
    let fraction: Double
    let text: String
}

/// How a series is drawn: the selected one strong, the others receding, or
/// all alike when nothing is selected.
nonisolated enum PeriodOutcomeEmphasis10868: Equatable {
    case selected
    case muted
    case plain

    var lineWidth: CGFloat {
        switch self {
        case .selected: 3
        case .muted: 1.5
        case .plain: 2
        }
    }

    var opacity: Double {
        switch self {
        case .selected, .plain: 1
        case .muted: 0.35
        }
    }
}

nonisolated enum PeriodOutcomeAction10868: Equatable {
    case select(String)
    case details(String)

    func perform(onSelect: ((String) -> Void)?, onDetails: ((String) -> Void)?) {
        switch self {
        case .select(let id): onSelect?(id)
        case .details(let id): onDetails?(id)
        }
    }
}

nonisolated struct PeriodOutcomeComparisonInput10868: Equatable {
    let phase: PeriodOutcomePhase10868
    /// "Half-by-half expectations"
    let eyebrow: String?
    /// "Two halves. Two sets of expectations."
    let title: String
    /// "A draw had the highest pre-match chance for the first half."
    let intro: String?
    /// The categorical positions, in the owner's order.
    let periods: [PeriodOutcomePeriod10868]
    /// The outcome series, in the owner's order — never sorted or filtered here.
    let series: [PeriodOutcomeSeries10868]
    /// The owner's exact selection.
    let selectedSeriesID: String?
    /// "Pre-match chances"
    let plotTitle: String?
    /// "0–50% scale"
    let scaleCaption: String?
    let axis: PeriodOutcomeAxis10868
    /// "Each dot is a pre-match chance for that half."
    let pointExplanation: String
    /// "Lines compare halves, not changes over time."
    let lineExplanation: String
    /// "Final results · <selected outcome>" — for the current selection.
    let resultsTitle: String?
    let words: PeriodOutcomeWords10868

    /// Exact id only. A missing or duplicated id gets no substitute series.
    var selection: PeriodOutcomeSelection10868 {
        guard let selectedSeriesID else { return .none }
        let matches = series.filter { $0.id == selectedSeriesID }
        switch matches.count {
        case 1: return .selected(matches[0])
        case 0: return .missing(selectedSeriesID)
        default: return .duplicate(selectedSeriesID)
        }
    }

    func isSelected(_ one: PeriodOutcomeSeries10868) -> Bool {
        selection.series?.id == one.id
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: words.selectionUnavailable
        case .none, .selected: nil
        }
    }

    func emphasis(for one: PeriodOutcomeSeries10868) -> PeriodOutcomeEmphasis10868 {
        guard let selected = selection.series else { return .plain }
        return selected.id == one.id ? .selected : .muted
    }

    /// The series' original for the period at `periodIndex`, matched by the
    /// period's exact identity.
    func cell(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> PeriodOutcomeCellLookup10868 {
        guard periods.indices.contains(periodIndex) else { return .absent }
        let period = periods[periodIndex]
        guard periods.filter({ $0.id == period.id }).count == 1 else { return .ambiguous }
        let matches = one.cells.filter { $0.periodID == period.id }
        switch matches.count {
        case 0: return .absent
        case 1: return .cell(matches[0])
        default: return .ambiguous
        }
    }

    /// A prop identity carried by exactly one original on the card.
    func isUniqueProp(_ id: String) -> Bool {
        series.reduce(0) { count, one in count + one.cells.filter { $0.id == id }.count } == 1
    }

    func pregameReading(_ cell: PeriodOutcomeCell10868) -> PeriodOutcomeReading10868 {
        cell.pregame.map { .value($0) } ?? .missing(cell.pregameMissing)
    }

    /// Before play, every period reads "not started" whatever later readings
    /// the owner passed. During play an admitted result replaces the current
    /// reading (a resolved market's price is a settlement, not a chance);
    /// otherwise the owner's current state. After the final, the result alone.
    func secondReading(_ cell: PeriodOutcomeCell10868) -> PeriodOutcomeSecondReading10868 {
        switch phase {
        case .before:
            return .notStarted(words.notStarted)
        case .during:
            if cell.result.isAdmitted { return .result(cell.result) }
            switch cell.current {
            case .recorded(let observation): return .current(.value(observation))
            case .unavailable(let text), .stale(let text): return .current(.missing(text))
            }
        case .final:
            return .result(cell.result)
        }
    }

    var resultTitle: String {
        phase == .final ? words.finalResultTitle : words.liveResultTitle
    }

    // MARK: Plot

    /// The series' pregame chances the axis can place, in period order. A
    /// missing, ambiguous, non-finite or out-of-scale chance is not plotted —
    /// never clamped, never drawn at zero.
    func plotPoints(for one: PeriodOutcomeSeries10868) -> [PeriodOutcomePlotPoint10868] {
        periods.indices.compactMap { index -> PeriodOutcomePlotPoint10868? in
            guard let pregame = cell(one, periodIndex: index).cell?.pregame,
                  let fraction = PeriodOutcomeGeometry10868.fraction(pregame.probability, axis: axis) else { return nil }
            return PeriodOutcomePlotPoint10868(periodIndex: index, fraction: fraction)
        }
    }

    /// Lines only between neighbouring periods that both have a plotted
    /// chance. A gap breaks the line: nothing is interpolated or skipped over.
    func segments(for one: PeriodOutcomeSeries10868) -> [PeriodOutcomeSegment10868] {
        let points = plotPoints(for: one)
        return zip(points, points.dropFirst()).compactMap { from, to in
            to.periodIndex == from.periodIndex + 1 ? PeriodOutcomeSegment10868(from: from, to: to) : nil
        }
    }

    /// The selected series' figures for its plotted points, in period order.
    var annotations: [PeriodOutcomeAnnotation10868] {
        guard let selected = selection.series else { return [] }
        return plotPoints(for: selected).compactMap { point -> PeriodOutcomeAnnotation10868? in
            guard let pregame = cell(selected, periodIndex: point.periodIndex).cell?.pregame else { return nil }
            return PeriodOutcomeAnnotation10868(periodIndex: point.periodIndex, fraction: point.fraction, text: pregame.text)
        }
    }

    /// Draw order: every other series first, the selected one on top.
    var drawOrder: [PeriodOutcomeSeries10868] {
        series.filter { !isSelected($0) } + series.filter { isSelected($0) }
    }

    // MARK: Actions

    /// No action for a series whose identity is not unique: it could not be
    /// returned unambiguously.
    func selectAction(_ one: PeriodOutcomeSeries10868, canSelect: Bool) -> PeriodOutcomeAction10868? {
        guard canSelect, series.filter({ $0.id == one.id }).count == 1 else { return nil }
        return .select(one.id)
    }

    /// The exact original's Details, only when its identity is unique.
    func detailsAction(_ cell: PeriodOutcomeCell10868, canOpenDetails: Bool) -> PeriodOutcomeAction10868? {
        guard canOpenDetails, isUniqueProp(cell.id) else { return nil }
        return .details(cell.id)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([eyebrow, title].compactMap { $0 }).joined(separator: ". ")
    }

    func accessibilityLabel(_ one: PeriodOutcomeSeries10868, period: PeriodOutcomePeriod10868) -> String {
        "\(period.label), \(one.label)"
    }

    /// One period of one outcome: its pregame chance with its own clock, then
    /// its separately labelled phase reading.
    func accessibilityValue(_ cell: PeriodOutcomeCell10868) -> String {
        var parts = [Self.spoken(pregameReading(cell), title: words.pregameTitle)]
        switch secondReading(cell) {
        case .notStarted(let text): parts.append(text)
        case .current(let reading): parts.append(Self.spoken(reading, title: words.currentTitle))
        case .result(let result): parts.append("\(resultTitle): \(result.text)")
        }
        return parts.joined(separator: "; ")
    }

    /// Every period of one outcome, in period order.
    func accessibilitySummary(_ one: PeriodOutcomeSeries10868) -> String {
        periods.indices.map { index -> String in
            let period = periods[index]
            guard let found = cell(one, periodIndex: index).cell else { return "\(period.label): \(words.cellUnavailable)" }
            return "\(period.label): \(accessibilityValue(found))"
        }
        .joined(separator: ". ")
    }

    var accessibilityPlotLabel: String {
        ([plotTitle, scaleCaption, pointExplanation, lineExplanation].compactMap { $0 }).joined(separator: ". ")
    }

    /// The selected outcome's chances; with no resolved selection, every outcome's.
    var accessibilityPlotValue: String {
        let shown = selection.series.map { [$0] } ?? series
        return shown.map { "\($0.label). \(accessibilitySummary($0))" }.joined(separator: ". ")
    }

    private static func spoken(_ reading: PeriodOutcomeReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text): "\(title): \(text)"
        }
    }
}

/// A tick the axis can place: its position on the axis and the owner's label.
nonisolated struct PeriodOutcomePlacedTick10868: Equatable {
    let fraction: Double
    let text: String
}

/// Where the periods sit across the plot and how wide their labels may be.
nonisolated struct PeriodOutcomeColumns10868: Equatable {
    /// Width reserved at the leading edge for tick labels.
    let gutter: CGFloat
    let plotWidth: CGFloat
    /// Clear space between each plot edge and the outer period centres.
    let inset: CGFloat
    /// The widest a period label or value label may be before it wraps.
    let labelWidth: CGFloat
    /// Each period's x, in the owner's order, from the plot block's leading edge.
    let centers: [CGFloat]
}

/// Every label placed and the space the plot block needs.
nonisolated struct PeriodOutcomePlotPlan10868: Equatable {
    /// Gridlines span this.
    let plotRect: CGRect
    /// From the first to the last period centre: marks are drawn in it.
    let markRect: CGRect
    let tickFrames: [CGRect]
    let periodFrames: [CGRect]
    /// Above the plot, clear of every mark and of the top tick label: value
    /// labels are placed in it. Zero height when there are none.
    let annotationBand: CGRect
    let annotationFrames: [CGRect]
    let size: CGSize
}

nonisolated enum PeriodOutcomeGeometry10868 {
    static let markDiameter: CGFloat = 9
    static let selectedMarkDiameter: CGFloat = 11
    /// Half the largest mark plus half its stroke.
    static var markRadius: CGFloat { (selectedMarkDiameter + 3) / 2 }

    /// Where a raw value sits on the axis, 0...1. Nil for an invalid axis or a
    /// non-finite or out-of-domain value — the mark is omitted, never clamped.
    static func fraction(_ value: Double, axis: PeriodOutcomeAxis10868) -> Double? {
        guard axis.isValid, value.isFinite, value >= axis.lower, value <= axis.upper else { return nil }
        return (value - axis.lower) / (axis.upper - axis.lower)
    }

    /// The ticks that can be placed, in the owner's order. A tick at a value
    /// already labelled is not labelled twice (two labels cannot share a line).
    static func visibleTicks(_ axis: PeriodOutcomeAxis10868) -> [PeriodOutcomePlacedTick10868] {
        var placed: [PeriodOutcomePlacedTick10868] = []
        for tick in axis.ticks {
            guard let position = Self.fraction(tick.value, axis: axis),
                  !placed.contains(where: { $0.fraction == position }) else { continue }
            placed.append(PeriodOutcomePlacedTick10868(fraction: position, text: tick.text))
        }
        return placed
    }

    /// A period's x within the mark rect, 0...1: one period sits in the middle.
    static func normalizedX(_ index: Int, count: Int) -> Double {
        count > 1 ? Double(index) / Double(count - 1) : 0.5
    }

    /// A plotted chance's centre in `rect`, the mark rect: first to last period
    /// centre across, top to bottom of the scale down.
    static func center(_ point: PeriodOutcomePlotPoint10868, count: Int, in rect: CGRect) -> CGPoint {
        CGPoint(x: rect.minX + rect.width * CGFloat(normalizedX(point.periodIndex, count: count)),
                y: rect.minY + rect.height * CGFloat(1 - point.fraction))
    }

    /// Labels centred on their periods, in the owner's (left-to-right) order.
    /// Each takes the first row where it clears the labels already there by
    /// the gap; one that clears none starts a row of its own.
    static func rows(centers: [CGFloat], sizes: [CGSize], gap: CGFloat) -> (rows: [Int], xs: [CGFloat], heights: [CGFloat]) {
        var rowEnds: [CGFloat] = []
        var heights: [CGFloat] = []
        var assigned: [Int] = []
        var xs: [CGFloat] = []
        for (center, size) in zip(centers, sizes) {
            let x = max(0, center - size.width / 2)
            let row: Int
            if let free = rowEnds.firstIndex(where: { $0 + gap <= x }) {
                row = free
                heights[row] = max(heights[row], size.height)
            } else {
                rowEnds.append(0)
                heights.append(size.height)
                row = rowEnds.count - 1
            }
            rowEnds[row] = x + size.width
            assigned.append(row)
            xs.append(x)
        }
        return (assigned, xs, heights)
    }

    /// Each row's top when rows stack down from `start`, and where the last ends.
    static func stack(_ heights: [CGFloat], from start: CGFloat, spacing: CGFloat = 2) -> (tops: [CGFloat], end: CGFloat) {
        var tops: [CGFloat] = []
        var y = start
        for height in heights {
            tops.append(y)
            y += height + spacing
        }
        return (tops, heights.isEmpty ? start : y - spacing)
    }

    /// The period columns. The outer periods sit far enough in from the plot
    /// edges for half of the widest period or value label plus half a gap — so
    /// each label stays whole, centred on its own period and clear of its
    /// neighbour — but never further than an equal share of the width allows;
    /// past that, labels wrap at their share less the gap.
    ///
    /// - Parameters:
    ///   - tickSizes: each tick label's one-line size.
    ///   - periodNatural: each period label's one-line size, in the owner's order.
    ///   - annotationNatural: each value label's one-line size.
    static func columns(width: CGFloat, tickSizes: [CGSize], periodNatural: [CGSize],
                        annotationNatural: [CGSize], markRadius: CGFloat = PeriodOutcomeGeometry10868.markRadius,
                        gap: CGFloat = 6) -> PeriodOutcomeColumns10868? {
        let count = periodNatural.count
        guard count > 0 else { return nil }
        let width = width.isFinite ? max(0, width) : 0
        let gutter = tickSizes.isEmpty ? 0 : (tickSizes.map(\.width).max() ?? 0) + gap
        let plotWidth = max(0, width - gutter)
        let widest = max(periodNatural.map(\.width).max() ?? 0, annotationNatural.map(\.width).max() ?? 0)
        let share = plotWidth / CGFloat(2 * count)
        let inset = min(max(markRadius, (widest + gap) / 2), share)
        let labelWidth = count == 1 ? plotWidth : max(0, 2 * inset - gap)
        let centers: [CGFloat] = (0..<count).map { index in
            count == 1
                ? gutter + plotWidth / 2
                : gutter + inset + (plotWidth - 2 * inset) * CGFloat(index) / CGFloat(count - 1)
        }
        return PeriodOutcomeColumns10868(gutter: gutter, plotWidth: plotWidth, inset: inset,
                                         labelWidth: labelWidth, centers: centers)
    }

    /// Every label's frame. Value labels sit in a band above the whole plot,
    /// centred on their periods, with room below it for the largest mark
    /// (radius and stroke) and the top tick label — so wherever the points
    /// fall, no value label covers any outcome's point or line. Tick labels sit
    /// right-aligned in the gutter on their gridlines; the plot grows taller
    /// when tick labels would otherwise touch; period labels sit centred under
    /// their periods, below the lowest tick label. Nothing is dropped, shrunk
    /// or truncated: a label arrives at its one-line size or at its size
    /// wrapped to the label width. A value or period label still too wide to
    /// clear its neighbour moves to a row of its own, still centred on its
    /// period; one wider than the whole plot widens the plan's reported size
    /// instead of being hidden.
    ///
    /// - Parameters:
    ///   - periodSizes / annotationSizes: each label's size as it will be shown.
    ///   - annotationIndices: each value label's period, in period order.
    static func plotPlan(columns: PeriodOutcomeColumns10868, tickFractions: [Double], tickSizes: [CGSize],
                         periodSizes: [CGSize], annotationIndices: [Int], annotationSizes: [CGSize],
                         baseHeight: CGFloat, markRadius: CGFloat = PeriodOutcomeGeometry10868.markRadius,
                         gap: CGFloat = 6) -> PeriodOutcomePlotPlan10868? {
        let centers = columns.centers
        let unit: (Double) -> Bool = { $0.isFinite && $0 >= 0 && $0 <= 1 }
        guard !centers.isEmpty, periodSizes.count == centers.count,
              tickFractions.count == tickSizes.count, tickFractions.allSatisfy(unit),
              annotationIndices.count == annotationSizes.count,
              annotationIndices.allSatisfy({ centers.indices.contains($0) }) else { return nil }
        let tickHeight = tickSizes.map(\.height).max() ?? 0
        let band = rows(centers: annotationIndices.map { centers[$0] }, sizes: annotationSizes, gap: gap)
        let bandRows = stack(band.heights, from: 0)
        // What reaches above the top of the scale: the largest mark, or half
        // the top tick label.
        let clearance = max(markRadius, tickHeight / 2)
        let top = annotationSizes.isEmpty ? clearance : bandRows.end + gap + clearance
        var plotHeight = baseHeight.isFinite ? max(0, baseHeight) : 0
        let sorted = tickFractions.sorted()
        for (lower, upper) in zip(sorted, sorted.dropFirst()) where upper > lower {
            plotHeight = max(plotHeight, (tickHeight + gap) / CGFloat(upper - lower))
        }
        let height = plotHeight
        let y: (Double) -> CGFloat = { top + CGFloat(1 - $0) * height }
        let tickFrames = zip(tickFractions, tickSizes).map { fraction, size in
            CGRect(x: max(0, columns.gutter - gap - size.width), y: y(fraction) - size.height / 2,
                   width: size.width, height: size.height)
        }
        let annotationFrames = annotationSizes.indices.map { index in
            CGRect(x: band.xs[index], y: bandRows.tops[band.rows[index]],
                   width: annotationSizes[index].width, height: annotationSizes[index].height)
        }
        let labelTop = top + plotHeight + clearance + gap
        let labels = rows(centers: centers, sizes: periodSizes, gap: gap)
        let labelRows = stack(labels.heights, from: labelTop)
        let periodFrames = periodSizes.indices.map { index in
            CGRect(x: labels.xs[index], y: labelRows.tops[labels.rows[index]],
                   width: periodSizes[index].width, height: periodSizes[index].height)
        }
        let first = centers[0]
        let last = centers[centers.count - 1]
        let extent = (tickFrames + periodFrames + annotationFrames).map(\.maxX).max() ?? 0
        let width = max(columns.gutter + columns.plotWidth, extent)
        return PeriodOutcomePlotPlan10868(
            plotRect: CGRect(x: columns.gutter, y: top, width: columns.plotWidth, height: plotHeight),
            markRect: CGRect(x: first, y: top, width: last - first, height: plotHeight),
            tickFrames: tickFrames,
            periodFrames: periodFrames,
            annotationBand: CGRect(x: 0, y: 0, width: width, height: bandRows.end),
            annotationFrames: annotationFrames,
            size: CGSize(width: width, height: max(labelTop, labelRows.end))
        )
    }
}

/// The plot block: tick labels, period labels, value labels, the gridlines and
/// the marks — in that subview order. The size it reports is the plan it places.
struct PeriodOutcomePlotLayout10868: Layout {
    let tickFractions: [Double]
    let periodCount: Int
    let annotations: [PeriodOutcomeAnnotation10868]
    let baseHeight: CGFloat
    var gap: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let fallback = subviews.map { $0.sizeThatFits(.unspecified).width }.reduce(0, +)
        let width = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? fallback
        return plan(width: width, subviews: subviews)?.size ?? CGSize(width: width, height: 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let plan = plan(width: bounds.width, subviews: subviews) else { return }
        let ticks = tickFractions.count
        let labels = ticks + periodCount
        var frames = plan.tickFrames + plan.periodFrames + plan.annotationFrames
        frames.append(plan.plotRect)
        frames.append(plan.markRect)
        for index in 0..<min(subviews.count, frames.count) {
            let frame = frames[index]
            // Labels are offered only their planned width, so a wrapped label
            // keeps the height it was measured at.
            let offer = index < labels + annotations.count
                ? ProposedViewSize(width: frame.width, height: nil)
                : ProposedViewSize(width: frame.width, height: frame.height)
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                  anchor: .topLeading, proposal: offer)
        }
    }

    private func plan(width: CGFloat, subviews: Subviews) -> PeriodOutcomePlotPlan10868? {
        let ticks = tickFractions.count
        let values = annotations.count
        guard periodCount > 0, subviews.count == ticks + periodCount + values + 2 else { return nil }
        let tickSizes = (0..<ticks).map { subviews[$0].sizeThatFits(.unspecified) }
        let periodNatural = (0..<periodCount).map { subviews[ticks + $0].sizeThatFits(.unspecified) }
        let valueNatural = (0..<values).map { subviews[ticks + periodCount + $0].sizeThatFits(.unspecified) }
        guard let columns = PeriodOutcomeGeometry10868.columns(width: width, tickSizes: tickSizes,
                                                              periodNatural: periodNatural,
                                                              annotationNatural: valueNatural, gap: gap) else { return nil }
        let wrapped = ProposedViewSize(width: columns.labelWidth, height: nil)
        let periodSizes = (0..<periodCount).map { index in
            periodNatural[index].width > columns.labelWidth
                ? subviews[ticks + index].sizeThatFits(wrapped) : periodNatural[index]
        }
        let valueSizes = (0..<values).map { index in
            valueNatural[index].width > columns.labelWidth
                ? subviews[ticks + periodCount + index].sizeThatFits(wrapped) : valueNatural[index]
        }
        return PeriodOutcomeGeometry10868.plotPlan(
            columns: columns,
            tickFractions: tickFractions,
            tickSizes: tickSizes,
            periodSizes: periodSizes,
            annotationIndices: annotations.map(\.periodIndex),
            annotationSizes: valueSizes,
            baseHeight: baseHeight,
            gap: gap
        )
    }
}

/// A series' point shape.
struct PeriodOutcomeSymbolShape10868: Shape {
    let symbol: PeriodOutcomeSymbol10868

    func path(in rect: CGRect) -> Path {
        var path = Path()
        switch symbol {
        case .circle:
            path.addEllipse(in: rect)
        case .square:
            path.addRect(rect.insetBy(dx: rect.width * 0.1, dy: rect.height * 0.1))
        case .diamond:
            path.move(to: CGPoint(x: rect.midX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
            path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.midY))
            path.closeSubpath()
        case .triangle:
            path.move(to: CGPoint(x: rect.midX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
            path.closeSubpath()
        }
        return path
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PeriodOutcomeAccessibilityID10868 {
    static let plot = "periodOutcome10868.plot"
    static func series(_ id: String) -> String { "periodOutcome10868.series.\(id)" }
    static func tile(_ propID: String) -> String { "periodOutcome10868.tile.\(propID)" }
}

struct PeriodOutcomeComparisonPresentation10868: View {
    let input: PeriodOutcomeComparisonInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var plotHeight: CGFloat = 170
    @ScaledMetric(relativeTo: .body) private var symbolSize: CGFloat = 10

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            if !input.series.isEmpty {
                selectors
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !input.periods.isEmpty {
                plotSection
            }
            if let selected = input.selection.series, !input.periods.isEmpty {
                tiles(selected)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = input.eyebrow {
                    Text(eyebrow).font(.caption).foregroundStyle(DS.textSecondary)
                }
                Text(input.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityHeader)
            .accessibilityAddTraits(.isHeader)
            if let intro = input.intro {
                Text(intro).font(.subheadline).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Series selectors

    /// The legend is the selector: each outcome's shape, colour and full name,
    /// wrapping as whole chips. Selection reads as weight, underline and a
    /// heavier outline, not colour alone.
    private var selectors: some View {
        FlowLayout(spacing: 8) {
            ForEach(Array(input.series.enumerated()), id: \.offset) { _, one in
                selector(one)
            }
        }
    }

    private func selector(_ one: PeriodOutcomeSeries10868) -> some View {
        let selected = input.isSelected(one)
        let action = input.selectAction(one, canSelect: canSelect)
        return control(action) {
            HStack(spacing: 6) {
                symbol(one)
                Text(one.label)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .underline(selected)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .frame(minHeight: 44)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(one.label)
        .accessibilityValue(input.accessibilitySummary(one))
        .accessibilityHint(action == nil ? "" : input.words.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(PeriodOutcomeAccessibilityID10868.series(one.id))
    }

    private func symbol(_ one: PeriodOutcomeSeries10868) -> some View {
        PeriodOutcomeSymbolShape10868(symbol: one.symbol)
            .fill(DS.cardBg)
            .overlay(PeriodOutcomeSymbolShape10868(symbol: one.symbol).stroke(one.tint, lineWidth: 2))
            .frame(width: symbolSize, height: symbolSize)
            .accessibilityHidden(true)
    }

    // MARK: Plot

    private var plotSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if input.plotTitle != nil || input.scaleCaption != nil {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        plotHeading
                    }
                    VStack(alignment: .leading, spacing: 2) { plotHeading }
                }
                .font(.caption)
                .accessibilityHidden(true)
            }
            plot
            VStack(alignment: .leading, spacing: 2) {
                Text(input.pointExplanation)
                Text(input.lineExplanation)
            }
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
        }
    }

    @ViewBuilder private var plotHeading: some View {
        if let plotTitle = input.plotTitle {
            Text(plotTitle).bold().foregroundStyle(DS.textPrimary).fixedSize(horizontal: false, vertical: true)
        }
        if input.plotTitle != nil, input.scaleCaption != nil {
            Spacer(minLength: 0)
        }
        if let scaleCaption = input.scaleCaption {
            Text(scaleCaption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var plot: some View {
        let ticks = PeriodOutcomeGeometry10868.visibleTicks(input.axis)
        let fractions = ticks.map(\.fraction)
        let annotations = input.annotations
        return PeriodOutcomePlotLayout10868(
            tickFractions: fractions,
            periodCount: input.periods.count,
            annotations: annotations,
            baseHeight: plotHeight
        ) {
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.text)
                    .font(.caption2)
                    .monospacedDigit()
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(Array(input.periods.enumerated()), id: \.offset) { _, period in
                Text(period.label)
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(Array(annotations.enumerated()), id: \.offset) { _, annotation in
                Text(annotation.text)
                    .font(.footnote.bold())
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            gridlines(fractions)
            marks
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityPlotLabel)
        .accessibilityValue(input.accessibilityPlotValue)
        .accessibilityIdentifier(PeriodOutcomeAccessibilityID10868.plot)
    }

    private func gridlines(_ fractions: [Double]) -> some View {
        GeometryReader { geo in
            Path { path in
                for fraction in fractions {
                    let y = geo.size.height * CGFloat(1 - fraction)
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: geo.size.width, y: y))
                }
            }
            .stroke(DS.border, style: StrokeStyle(lineWidth: 1, dash: [3, 5]))
        }
    }

    /// Lines then hollow points per series, the selected series drawn last.
    /// The rect spans the first to the last period centre.
    private var marks: some View {
        let count = input.periods.count
        return GeometryReader { geo in
            let rect = CGRect(origin: .zero, size: geo.size)
            ZStack(alignment: .topLeading) {
                ForEach(Array(input.drawOrder.enumerated()), id: \.offset) { _, one in
                    let emphasis = input.emphasis(for: one)
                    let tint = one.tint.opacity(emphasis.opacity)
                    Path { path in
                        for segment in input.segments(for: one) {
                            path.move(to: PeriodOutcomeGeometry10868.center(segment.from, count: count, in: rect))
                            path.addLine(to: PeriodOutcomeGeometry10868.center(segment.to, count: count, in: rect))
                        }
                    }
                    .stroke(tint, style: StrokeStyle(lineWidth: emphasis.lineWidth, lineCap: .round))
                    ForEach(Array(input.plotPoints(for: one).enumerated()), id: \.offset) { _, point in
                        let diameter = emphasis == .selected
                            ? PeriodOutcomeGeometry10868.selectedMarkDiameter
                            : PeriodOutcomeGeometry10868.markDiameter
                        PeriodOutcomeSymbolShape10868(symbol: one.symbol)
                            .fill(DS.cardBg)
                            .overlay(
                                PeriodOutcomeSymbolShape10868(symbol: one.symbol)
                                    .stroke(tint, lineWidth: emphasis == .selected ? 3 : 2)
                            )
                            .frame(width: diameter, height: diameter)
                            .position(PeriodOutcomeGeometry10868.center(point, count: count, in: rect))
                    }
                }
            }
        }
    }

    // MARK: Period tiles

    private func tiles(_ selected: PeriodOutcomeSeries10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let resultsTitle = input.resultsTitle {
                Text(resultsTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 10) { tileRow(selected) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 10) { tileRow(selected) }
                    VStack(alignment: .leading, spacing: 10) { tileRow(selected) }
                }
            }
        }
    }

    private func tileRow(_ selected: PeriodOutcomeSeries10868) -> some View {
        ForEach(Array(input.periods.enumerated()), id: \.offset) { index, period in
            tile(selected, period: period, lookup: input.cell(selected, periodIndex: index))
        }
    }

    @ViewBuilder
    private func tile(_ one: PeriodOutcomeSeries10868, period: PeriodOutcomePeriod10868,
                      lookup: PeriodOutcomeCellLookup10868) -> some View {
        if let cell = lookup.cell {
            let action = input.detailsAction(cell, canOpenDetails: canOpenDetails)
            control(action) {
                tileBody(period: period, hasAction: action != nil) {
                    pregameValue(input.pregameReading(cell))
                    secondValue(input.secondReading(cell))
                }
            }
            .accessibilityLabel(input.accessibilityLabel(one, period: period))
            .accessibilityValue(input.accessibilityValue(cell))
            .accessibilityHint(action == nil ? "" : input.words.detailsHint)
            .accessibilityIdentifier(PeriodOutcomeAccessibilityID10868.tile(cell.id))
        } else {
            tileBody(period: period, hasAction: false) {
                Text(input.words.cellUnavailable)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityLabel(one, period: period))
            .accessibilityValue(input.words.cellUnavailable)
        }
    }

    private func tileBody<Content: View>(period: PeriodOutcomePeriod10868, hasAction: Bool,
                                         @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 6) {
                Text(period.label).font(.caption).foregroundStyle(DS.textSecondary)
                content()
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            if hasAction {
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .accessibilityHidden(true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
        .contentShape(Rectangle())
    }

    private func pregameValue(_ reading: PeriodOutcomeReading10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(input.words.pregameTitle).font(.caption).foregroundStyle(DS.textSecondary)
            switch reading {
            case .value(let observation):
                figure(observation.text)
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
    }

    /// A supplied chance — pregame or current — at the one figure size, so the
    /// two compare directly. The whole figure keeps its width; a narrow row
    /// stacks the tiles instead of squeezing or splitting a number.
    private func figure(_ text: String) -> some View {
        Text(text)
            .font(.system(size: figureSize, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: true, vertical: false)
    }

    @ViewBuilder private func secondValue(_ reading: PeriodOutcomeSecondReading10868) -> some View {
        switch reading {
        case .notStarted(let text):
            Text(text).font(.footnote.weight(.semibold)).foregroundStyle(DS.textSecondary)
        case .current(let current):
            VStack(alignment: .leading, spacing: 2) {
                Text(input.words.currentTitle).font(.caption).foregroundStyle(DS.textSecondary)
                switch current {
                case .value(let observation):
                    figure(observation.text)
                case .missing(let text):
                    Text(text).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            }
        case .result(let result):
            VStack(alignment: .leading, spacing: 2) {
                Text(input.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    switch result.mark {
                    case .positive?:
                        Image(systemName: "checkmark.circle").accessibilityHidden(true)
                    case .negative?:
                        Image(systemName: "xmark.circle").accessibilityHidden(true)
                    case nil:
                        EmptyView()
                    }
                    Text(result.text)
                }
                .font(result.isAdmitted ? Font.subheadline.weight(.semibold) : Font.footnote)
                .foregroundStyle(result.mark == .positive ? DS.textPrimary : DS.textSecondary)
            }
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback and the identity is
    /// unambiguous; otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: PeriodOutcomeAction10868?, @ViewBuilder content: () -> Content) -> some View {
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

// MARK: - Final period scores beside pre-match chances

// #10868 — the final-only set card: each finished period's reported score and
// winner, and below it every outcome's own original pre-match chance for that
// period on its own 0–100% bar. Extracted from the approved design
// (totals-final-forecast-binding-20261024 `TennisSetComparison.tsx` +
// `tennisSetComparison.css`, the `sets` card of `TennisFinal.tsx`).
//
// It composes the period comparison above — the same periods, series, cells,
// observations, readings, symbols, phase and Details action — and adds only
// the owner's actual context per period and the card's words. Every score,
// unit, reported winner, provenance line and missing word arrives resolved and
// is shown verbatim. This layer never adds scores, never derives a winner from
// the scores or from an original's grade, never reads a later quote or a grade
// for this card, never parses a label, and never invents a chance, a zero or a
// complement for a period with no original. A score's capture time is
// provenance, never the period's end.
//
// Final only by default: before and during play nothing on this card is
// shown. An owner may opt in (`completedDuringPlay`) to show, during play,
// exactly the periods it admits completed — never before play, and the phase
// stays `.during`. A separate opt-in (`beforePlay`) shows, before play, only
// the periods the owner names and only their pre-match chances, under the
// owner's pregame copy; the phase stays `.before`. The period comparison
// above keeps its own lifecycle unchanged.
//
// Host binding still owed — not available at this base. An owner must supply
// the admitted comparison input (phase, ordered periods and series, exact
// originals with admitted pregame observations) and, per period, an actual
// context associated by exact period and series identity, with its own
// provenance and score-only words; and for the card, its headline, summary,
// shared pre-match heading and notes.

/// One outcome's reported score in one period ("7"), by exact series identity.
nonisolated struct PeriodOutcomeActualScore10868: Equatable {
    let seriesID: String
    let text: String
}

/// The owner's reported winner of one period — never derived from the scores
/// or from an original's grade.
nonisolated enum PeriodOutcomeActualWinner10868: Equatable {
    /// The winning series' exact identity and the owner's words ("Player A won").
    case reported(seriesID: String, text: String)
    /// No winner reported ("Winner not reported").
    case unreported(String)
}

/// A period's reported score: each outcome's score, its unit and the winner.
nonisolated struct PeriodOutcomeActualReport10868: Equatable {
    let scores: [PeriodOutcomeActualScore10868]
    /// "games"
    let unit: String
    let winner: PeriodOutcomeActualWinner10868
}

nonisolated enum PeriodOutcomeActualState10868: Equatable {
    case reported(PeriodOutcomeActualReport10868)
    /// No admitted score ("Set score unavailable"), whatever the chances say.
    case unavailable(String)
}

/// The owner-resolved actual context of one period after the final.
nonisolated struct PeriodOutcomeActualContext10868: Equatable {
    /// Opaque owner identity of this context.
    let id: String
    /// The exact period it belongs to — never inferred from order or label.
    let periodID: String
    let state: PeriodOutcomeActualState10868
    /// Score source and capture clock, spoken with the score ("Scores · score
    /// captured 10:06:47 AM PT"). A capture time, never the period's end.
    let provenance: String
    /// Shown when the period has no original at all ("No pre-match set chance
    /// recorded. Score only · no prop supplied for this set.").
    let noOriginal: String
}

/// A period's actual context, by exact period identity.
nonisolated enum PeriodOutcomeActualLookup10868: Equatable {
    case context(PeriodOutcomeActualContext10868)
    /// No context names this period.
    case absent
    /// More than one context, or an identity that is blank or used twice —
    /// nothing is chosen.
    case ambiguous

    var context: PeriodOutcomeActualContext10868? {
        if case .context(let context) = self { return context }
        return nil
    }
}

/// The card's words, chosen explicitly — never parsed from a label.
nonisolated struct PeriodOutcomeFinalScoreWords10868: Equatable {
    /// "SET WINNERS · FINAL"
    let eyebrow: String?
    /// "Two close sets decided it"
    let title: String
    /// "Player A won the match. Games were level."
    let summary: String?
    /// "Pre-match chance to win each set" — shown once above the periods.
    let pregameHeading: String
    /// "–" — between the outcomes' scores.
    let scoreSeparator: String
    /// "Actual score" — spoken before each period's score.
    let actualTitle: String
    /// "No score reported for this set" — a period with no single actual
    /// context, or one that cannot name every outcome's score.
    let actualMissing: String
    /// "Winner not reported" — a reported winner whose series is not on the card.
    let winnerUnavailable: String
    /// "Chance bars share a 0–100% scale."
    let scaleNote: String?
    /// "Tap a player for its original outcome and recorded time." — shown only
    /// when Details can be opened.
    let detailsNote: String?
}

/// One outcome's score in a period, with whether the owner reported it the winner.
nonisolated struct PeriodOutcomeScoreEntry10868: Equatable {
    let series: PeriodOutcomeSeries10868
    let text: String
    let isReportedWinner: Bool
}

nonisolated enum PeriodOutcomeScoreLine10868: Equatable {
    /// Every outcome's score in the owner's series order, and the unit.
    case reported([PeriodOutcomeScoreEntry10868], unit: String)
    /// The owner's unavailable words, or the card's missing words.
    case missing(String)
}

nonisolated enum PeriodOutcomeWinnerLine10868: Equatable {
    case reported(PeriodOutcomeSeries10868, String)
    case unavailable(String)
}

nonisolated struct PeriodOutcomeFinalScoreInput10868: Equatable {
    /// The admitted periods, series and originals. Its phase decides whether
    /// this card is shown.
    let comparison: PeriodOutcomeComparisonInput10868
    /// One actual context per period, each naming its period exactly.
    let actuals: [PeriodOutcomeActualContext10868]
    let words: PeriodOutcomeFinalScoreWords10868
    /// Off by default, so the card stays final-only. When supplied, the
    /// owner's admitted completed periods are also shown during play — never
    /// before play. A display permission, not a completion detector.
    var completedDuringPlay: PeriodOutcomeCompletedDuringPlay10868? = nil
    /// Off by default, so nothing shows before play. When supplied, the
    /// periods the owner names are shown before play with each outcome's
    /// pre-match chance only. A display permission, not a phase change.
    var beforePlay: PeriodOutcomeBeforePlay10868? = nil
    /// Nil by default: every exact original offers its Details, as before.
    /// When supplied, only the original ids the owner names offer Details;
    /// every other chance still shows, with no control. An availability
    /// permission only — it never adds an original, and an id the card does
    /// not show, or shows twice, still offers nothing.
    var detailsOriginalIDs: Set<String>? = nil

    /// Bars place a chance on this explicit probability scale only; a value on
    /// any other scale gets no fill.
    static var barAxis: PeriodOutcomeAxis10868 { PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: []) }

    /// A structural guard: an identity of only spaces cannot be returned or matched.
    static func isExact(_ id: String) -> Bool {
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// After the final; during play only with the opt-in and at least one
    /// admitted completed period on the card; before play only with the
    /// before-play opt-in and at least one named period on the card.
    var isShown: Bool { !periodIndices.isEmpty || comparison.phase == .final }

    /// After the final every period, in the owner's order — no cap and no
    /// first pick. During play, with the opt-in only, the admitted completed
    /// periods in the owner's order. Before play, with the before-play
    /// opt-in only, the named periods in the owner's order; otherwise none.
    var periodIndices: [Int] {
        switch comparison.phase {
        case .final: Array(comparison.periods.indices)
        case .during: completedPeriodIndicesDuringPlay
        case .before: periodIndicesBeforePlay
        }
    }

    /// A period identity the card can associate: nonblank and used once.
    func hasExactIdentity(periodIndex: Int) -> Bool {
        guard comparison.periods.indices.contains(periodIndex) else { return false }
        let id = comparison.periods[periodIndex].id
        return Self.isExact(id) && comparison.periods.filter { $0.id == id }.count == 1
    }

    /// A series identity the card can associate: nonblank and used once.
    func hasExactIdentity(_ one: PeriodOutcomeSeries10868) -> Bool {
        Self.isExact(one.id) && comparison.series.filter { $0.id == one.id }.count == 1
    }

    // MARK: Actual context

    /// The period's own actual context. A missing, duplicated or blank
    /// association attaches nothing, and no period borrows another's. Before
    /// play no actual context is read at all — score, winner, provenance and
    /// score-only words stay out whatever the owner passed.
    func actual(periodIndex: Int) -> PeriodOutcomeActualLookup10868 {
        guard comparison.phase != .before, periodIndices.contains(periodIndex) else { return .absent }
        guard hasExactIdentity(periodIndex: periodIndex) else { return .ambiguous }
        let periodID = comparison.periods[periodIndex].id
        let matches = actuals.filter { $0.periodID == periodID }
        switch matches.count {
        case 0:
            return .absent
        case 1:
            let context = matches[0]
            guard Self.isExact(context.id), actuals.filter({ $0.id == context.id }).count == 1 else { return .ambiguous }
            return .context(context)
        default:
            return .ambiguous
        }
    }

    /// The series the owner named as winner, when exactly one on the card carries it.
    func winnerSeries(_ winner: PeriodOutcomeActualWinner10868) -> PeriodOutcomeSeries10868? {
        guard case .reported(let seriesID, _) = winner else { return nil }
        let matches = comparison.series.filter { $0.id == seriesID }
        guard matches.count == 1, hasExactIdentity(matches[0]) else { return nil }
        return matches[0]
    }

    /// The owner's reported winner. Nil when the period has no reported score.
    func winnerLine(periodIndex: Int) -> PeriodOutcomeWinnerLine10868? {
        guard let context = actual(periodIndex: periodIndex).context,
              case .reported(let report) = context.state else { return nil }
        switch report.winner {
        case .unreported(let text):
            return .unavailable(text)
        case .reported(_, let text):
            guard let one = winnerSeries(report.winner) else { return .unavailable(words.winnerUnavailable) }
            return .reported(one, text)
        }
    }

    /// Every outcome's score by exact series identity, in series order. One
    /// missing, duplicated or unassociable score shows the missing words —
    /// never half a score.
    func scoreLine(periodIndex: Int) -> PeriodOutcomeScoreLine10868 {
        guard let context = actual(periodIndex: periodIndex).context else { return .missing(words.actualMissing) }
        switch context.state {
        case .unavailable(let text):
            return .missing(text)
        case .reported(let report):
            let winnerID = winnerSeries(report.winner)?.id
            var entries: [PeriodOutcomeScoreEntry10868] = []
            for one in comparison.series {
                let matches = report.scores.filter { $0.seriesID == one.id }
                guard hasExactIdentity(one), matches.count == 1 else { return .missing(words.actualMissing) }
                entries.append(PeriodOutcomeScoreEntry10868(series: one, text: matches[0].text,
                                                            isReportedWinner: one.id == winnerID))
            }
            return entries.isEmpty ? .missing(words.actualMissing) : .reported(entries, unit: report.unit)
        }
    }

    // MARK: Pre-match chances

    /// The series' original for the period, through the comparison's exact
    /// lookup, once the period and series identities are themselves exact.
    func chance(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> PeriodOutcomeCellLookup10868 {
        guard periodIndices.contains(periodIndex) else { return .absent }
        guard hasExactIdentity(periodIndex: periodIndex), hasExactIdentity(one) else { return .ambiguous }
        return comparison.cell(one, periodIndex: periodIndex)
    }

    /// Whether any outcome has an original — or an ambiguous one — for the period.
    func hasOriginals(periodIndex: Int) -> Bool {
        comparison.series.contains { chance($0, periodIndex: periodIndex) != .absent }
    }

    /// A period with no original keeps its score and shows the owner's words
    /// instead of chances: no cell, market, zero or complement is invented.
    func scoreOnlyText(periodIndex: Int) -> String? {
        guard periodIndices.contains(periodIndex), !hasOriginals(periodIndex: periodIndex) else { return nil }
        return actual(periodIndex: periodIndex).context?.noOriginal ?? comparison.words.cellUnavailable
    }

    /// The bar's fill, 0...1, from the pregame chance only. Nil — no fill,
    /// never clamped — for a missing, non-finite or out-of-scale value. A
    /// genuine 0 is a value.
    func barFraction(_ cell: PeriodOutcomeCell10868) -> Double? {
        cell.pregame.flatMap { PeriodOutcomeGeometry10868.fraction($0.probability, axis: Self.barAxis) }
    }

    // MARK: Actions

    /// The exact original's Details through the comparison's own helper, only
    /// for an exactly associated, nonblank identity. The helper checks
    /// uniqueness; the blank guard is this card's, and so is the owner's
    /// availability (`detailsOriginalIDs`, nil = every exact original).
    func detailsAction(_ one: PeriodOutcomeSeries10868, periodIndex: Int, canOpenDetails: Bool) -> PeriodOutcomeAction10868? {
        guard let cell = chance(one, periodIndex: periodIndex).cell, Self.isExact(cell.id) else { return nil }
        if let detailsOriginalIDs, !detailsOriginalIDs.contains(cell.id) { return nil }
        return comparison.detailsAction(cell, canOpenDetails: canOpenDetails)
    }

    /// Whether at least one shown period and series opens an original through
    /// the same action each chance uses. The callback alone is not enough: no
    /// periods, score-only periods (every chance absent) and blank, duplicated
    /// or ambiguous originals open nothing. A missing or 0% pregame chance does
    /// not close a valid original.
    func opensAnyDetails(canOpenDetails: Bool) -> Bool {
        periodIndices.contains { index in
            comparison.series.contains { detailsAction($0, periodIndex: index, canOpenDetails: canOpenDetails) != nil }
        }
    }

    /// The notes below the periods, from the copy for the phase shown. The
    /// blocks note only when a shown panel draws blocks (during play, with the
    /// opt-in); the Details note only when a shown chance actually opens Details.
    func notes(canOpenDetails: Bool) -> [String] {
        guard isShown else { return [] }
        return [
            copy.scaleNote,
            showsAnyBlocks ? completedDuringPlay?.words.blocksNote : nil,
            opensAnyDetails(canOpenDetails: canOpenDetails) ? copy.detailsNote : nil,
        ].compactMap { $0 }
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        isShown ? ([copy.eyebrow, copy.title].compactMap { $0 }).joined(separator: ". ") : ""
    }

    /// The period's winner, then its score, then the score's own provenance.
    /// Before play there is none of these to say.
    func accessibilityPeriodValue(periodIndex: Int) -> String {
        guard comparison.phase != .before, periodIndices.contains(periodIndex) else { return "" }
        var parts: [String] = []
        switch winnerLine(periodIndex: periodIndex) {
        case .reported(_, let text)?, .unavailable(let text)?:
            parts.append(text)
        case nil:
            break
        }
        switch scoreLine(periodIndex: periodIndex) {
        case .reported(let entries, let unit):
            let scores = entries.map { "\($0.series.label) \($0.text)" }.joined(separator: ", ")
            parts.append("\(words.actualTitle): \(scores) \(unit)")
            if let context = actual(periodIndex: periodIndex).context {
                parts.append(context.provenance)
            }
        case .missing(let text):
            parts.append("\(words.actualTitle): \(text)")
        }
        return parts.joined(separator: "; ")
    }

    func accessibilityChanceLabel(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> String {
        guard comparison.periods.indices.contains(periodIndex) else { return one.label }
        return comparison.accessibilityLabel(one, period: comparison.periods[periodIndex])
    }

    /// The pregame chance with its own clock and source. No later reading and
    /// no grade: those stay in the original's Details.
    func accessibilityChanceValue(_ lookup: PeriodOutcomeCellLookup10868) -> String {
        guard let cell = lookup.cell else { return comparison.words.cellUnavailable }
        switch comparison.pregameReading(cell) {
        case .value(let observation):
            return "\(comparison.words.pregameTitle): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text):
            return "\(comparison.words.pregameTitle): \(text)"
        }
    }
}

/// How a row of blocks shares its width.
nonisolated enum PeriodOutcomeFinalDistribution10868: Equatable {
    /// Equal columns, so no outcome's chance reads larger than another's.
    case equal
    /// Natural widths, the first at the leading edge and the last at the trailing.
    case spread
}

nonisolated enum PeriodOutcomeFinalArrangement10868: Equatable {
    /// Side by side, each block offered its column width.
    case row([CGFloat])
    /// One above another, each offered the whole width.
    case stacked
}

nonisolated enum PeriodOutcomeFinalGeometry10868 {
    /// Side by side only when every block fits whole at its one-line width;
    /// otherwise — and always at accessibility sizes — stacked. Nothing is
    /// shrunk or truncated to stay on one row.
    ///
    /// - Parameter idealWidths: each block's one-line width, in order.
    static func arrangement(width: CGFloat, idealWidths: [CGFloat], spacing: CGFloat,
                            distribution: PeriodOutcomeFinalDistribution10868,
                            accessibilitySize: Bool) -> PeriodOutcomeFinalArrangement10868 {
        let count = idealWidths.count
        guard !accessibilitySize, count > 1, width.isFinite, width > 0, spacing.isFinite, spacing >= 0,
              idealWidths.allSatisfy({ $0.isFinite && $0 >= 0 }) else { return .stacked }
        let available = width - spacing * CGFloat(count - 1)
        switch distribution {
        case .equal:
            let column = available / CGFloat(count)
            guard column > 0, idealWidths.allSatisfy({ $0 <= column }) else { return .stacked }
            return .row(Array(repeating: column, count: count))
        case .spread:
            guard idealWidths.reduce(0, +) <= available else { return .stacked }
            return .row(idealWidths)
        }
    }

    /// Each column's leading x in a row.
    static func origins(width: CGFloat, columns: [CGFloat], spacing: CGFloat,
                        distribution: PeriodOutcomeFinalDistribution10868) -> [CGFloat] {
        let gap: CGFloat
        switch distribution {
        case .equal:
            gap = spacing
        case .spread:
            gap = columns.count > 1 ? max(spacing, (width - columns.reduce(0, +)) / CGFloat(columns.count - 1)) : 0
        }
        var origins: [CGFloat] = []
        var x: CGFloat = 0
        for column in columns {
            origins.append(x)
            x += column + gap
        }
        return origins
    }
}

/// Blocks side by side when they all fit whole, otherwise stacked. The size
/// it reports is what it places; a block wider than the width when stacked
/// widens the reported size instead of being clipped.
struct PeriodOutcomeFinalRowLayout10868: Layout {
    let distribution: PeriodOutcomeFinalDistribution10868
    let accessibilitySize: Bool
    var spacing: CGFloat = 12

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let ideals = subviews.map { $0.sizeThatFits(.unspecified) }
        guard let width = proposal.width, width.isFinite, width > 0 else {
            let gaps = spacing * CGFloat(max(0, subviews.count - 1))
            if accessibilitySize || subviews.count < 2 {
                return CGSize(width: ideals.map(\.width).max() ?? 0, height: ideals.map(\.height).reduce(0, +) + gaps)
            }
            return CGSize(width: ideals.map(\.width).reduce(0, +) + gaps, height: ideals.map(\.height).max() ?? 0)
        }
        return plan(width: width, subviews: subviews, ideals: ideals).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let ideals = subviews.map { $0.sizeThatFits(.unspecified) }
        let frames = plan(width: bounds.width, subviews: subviews, ideals: ideals).frames
        for index in 0..<min(subviews.count, frames.count) {
            let frame = frames[index]
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                  anchor: .topLeading, proposal: ProposedViewSize(width: frame.width, height: frame.height))
        }
    }

    private func plan(width: CGFloat, subviews: Subviews, ideals: [CGSize]) -> (frames: [CGRect], size: CGSize) {
        let arrangement = PeriodOutcomeFinalGeometry10868.arrangement(
            width: width, idealWidths: ideals.map(\.width), spacing: spacing,
            distribution: distribution, accessibilitySize: accessibilitySize
        )
        switch arrangement {
        case .row(let columns):
            let xs = PeriodOutcomeFinalGeometry10868.origins(width: width, columns: columns, spacing: spacing,
                                                              distribution: distribution)
            var frames: [CGRect] = []
            for index in 0..<min(subviews.count, columns.count) {
                let height = subviews[index].sizeThatFits(ProposedViewSize(width: columns[index], height: nil)).height
                frames.append(CGRect(x: xs[index], y: 0, width: columns[index], height: height))
            }
            return (frames, CGSize(width: width, height: frames.map(\.height).max() ?? 0))
        case .stacked:
            var frames: [CGRect] = []
            var y: CGFloat = 0
            for subview in subviews {
                let size = subview.sizeThatFits(ProposedViewSize(width: width, height: nil))
                frames.append(CGRect(x: 0, y: y, width: max(width, size.width), height: size.height))
                y += size.height + spacing
            }
            return (frames, CGSize(width: frames.map(\.width).max() ?? width, height: frames.isEmpty ? 0 : y - spacing))
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PeriodOutcomeFinalScoreAccessibilityID10868 {
    static func period(_ id: String) -> String { "periodOutcomeFinal10868.period.\(id)" }
    static func chance(_ propID: String) -> String { "periodOutcomeFinal10868.chance.\(propID)" }
}

struct PeriodOutcomeFinalScorePresentation10868: View {
    let input: PeriodOutcomeFinalScoreInput10868
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var scoreSize: CGFloat = 24
    @ScaledMetric(relativeTo: .body) private var separatorSize: CGFloat = 17
    @ScaledMetric(relativeTo: .title3) private var chanceSize: CGFloat = 18
    @ScaledMetric(relativeTo: .body) private var symbolSize: CGFloat = 10
    @ScaledMetric(relativeTo: .body) private var barHeight: CGFloat = 6
    /// During play: each panel's pre-match figure and actual count, at one size.
    @ScaledMetric(relativeTo: .title2) private var panelFigureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var blockWidth: CGFloat = 12
    @ScaledMetric(relativeTo: .body) private var blockHeight: CGFloat = 17

    private var canOpenDetails: Bool { onDetails != nil }
    private var accessibilitySize: Bool { typeSize.isAccessibilitySize }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 12) {
                header
                Text(input.copy.pregameHeading)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(input.periodIndices, id: \.self) { index in
                        periodCard(index)
                    }
                }
                let notes = input.notes(canOpenDetails: canOpenDetails)
                if !notes.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(notes.enumerated()), id: \.offset) { _, note in
                            Text(note)
                        }
                    }
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = input.copy.eyebrow {
                    Text(eyebrow).font(.caption).foregroundStyle(DS.textSecondary)
                }
                Text(input.copy.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityHeader)
            .accessibilityAddTraits(.isHeader)
            if let summary = input.copy.summary {
                Text(summary).font(.subheadline).foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Period cards

    private func periodCard(_ index: Int) -> some View {
        let period = input.comparison.periods[index]
        return VStack(alignment: .leading, spacing: 10) {
            if input.showsPanels(periodIndex: index) || input.showsPanelsBeforePlay(periodIndex: index) {
                panelPeriodHeader(index, period: period)
                PeriodOutcomeFinalRowLayout10868(distribution: .equal, accessibilitySize: accessibilitySize, spacing: 10) {
                    ForEach(Array(input.comparison.series.enumerated()), id: \.offset) { _, one in
                        panel(one, periodIndex: index)
                    }
                }
            } else {
                periodHeader(index, period: period)
                if let scoreOnly = input.scoreOnlyText(periodIndex: index) {
                    Text(scoreOnly)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    PeriodOutcomeFinalRowLayout10868(distribution: .equal, accessibilitySize: accessibilitySize, spacing: 16) {
                        ForEach(Array(input.comparison.series.enumerated()), id: \.offset) { _, one in
                            chance(one, periodIndex: index)
                        }
                    }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PeriodOutcomeFinalScoreAccessibilityID10868.period(period.id))
    }

    /// The period's name and reported winner beside its score; stacked when
    /// they do not both fit whole.
    private func periodHeader(_ index: Int, period: PeriodOutcomePeriod10868) -> some View {
        PeriodOutcomeFinalRowLayout10868(distribution: .spread, accessibilitySize: accessibilitySize, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(period.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                winner(input.winnerLine(periodIndex: index))
            }
            score(input.scoreLine(periodIndex: index))
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(period.label)
        .accessibilityValue(input.accessibilityPeriodValue(periodIndex: index))
    }

    @ViewBuilder private func winner(_ line: PeriodOutcomeWinnerLine10868?) -> some View {
        switch line {
        case .reported(let one, let text)?:
            HStack(alignment: .center, spacing: 5) {
                symbol(one)
                Text(text)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .unavailable(let text)?:
            Text(text)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case nil:
            EmptyView()
        }
    }

    /// The scores at the one prominent size, whole; the unit drops below them
    /// rather than squeezing a number.
    @ViewBuilder private func score(_ line: PeriodOutcomeScoreLine10868) -> some View {
        switch line {
        case .reported(let entries, let unit):
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    figures(entries)
                    unitText(unit)
                }
                VStack(alignment: .leading, spacing: 0) {
                    figures(entries)
                    unitText(unit)
                }
            }
        case .missing(let text):
            Text(text)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func figures(_ entries: [PeriodOutcomeScoreEntry10868]) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            ForEach(Array(entries.enumerated()), id: \.offset) { offset, entry in
                if offset > 0 {
                    Text(input.words.scoreSeparator)
                        .font(.system(size: separatorSize))
                        .foregroundStyle(DS.textSecondary)
                }
                Text(entry.text)
                    .font(.system(size: scoreSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(entry.isReportedWinner ? DS.textPrimary : DS.textSecondary)
            }
        }
        .fixedSize(horizontal: true, vertical: false)
    }

    private func unitText(_ unit: String) -> some View {
        Text(unit)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Chances

    /// One outcome's pre-match chance: name and figure, then its own bar on
    /// the 0–100% scale. A button only with the callback and an exact original.
    @ViewBuilder
    private func chance(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> some View {
        let lookup = input.chance(one, periodIndex: periodIndex)
        let action = input.detailsAction(one, periodIndex: periodIndex, canOpenDetails: canOpenDetails)
        control(action) {
            VStack(alignment: .leading, spacing: 5) {
                if accessibilitySize {
                    VStack(alignment: .leading, spacing: 2) {
                        playerName(one)
                        chanceText(lookup)
                    }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            playerName(one)
                            Spacer(minLength: 0)
                            chanceText(lookup)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            playerName(one)
                            chanceText(lookup)
                        }
                    }
                }
                if let cell = lookup.cell {
                    bar(one, fraction: input.barFraction(cell))
                }
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilityChanceLabel(one, periodIndex: periodIndex))
        .accessibilityValue(input.accessibilityChanceValue(lookup))
        .accessibilityHint(action == nil ? "" : input.comparison.words.detailsHint)
        .accessibilityIdentifier(lookup.cell.map { PeriodOutcomeFinalScoreAccessibilityID10868.chance($0.id) } ?? "")
    }

    private func playerName(_ one: PeriodOutcomeSeries10868) -> some View {
        HStack(alignment: .center, spacing: 5) {
            symbol(one)
            Text(one.label)
                .font(.footnote)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func chanceText(_ lookup: PeriodOutcomeCellLookup10868) -> some View {
        if let cell = lookup.cell {
            switch input.comparison.pregameReading(cell) {
            case .value(let observation):
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
            case .missing(let text):
                Text(text)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } else {
            Text(input.comparison.words.cellUnavailable)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The outcome's own bar: a track for the whole 0–100% scale and a fill
    /// for its chance. No fill for a value the scale cannot place.
    private func bar(_ one: PeriodOutcomeSeries10868, fraction: Double?) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(DS.border)
                if let fraction {
                    Capsule().fill(one.tint).frame(width: geo.size.width * CGFloat(fraction))
                }
            }
        }
        .frame(height: barHeight)
        .accessibilityHidden(true)
    }

    private func symbol(_ one: PeriodOutcomeSeries10868) -> some View {
        PeriodOutcomeSymbolShape10868(symbol: one.symbol)
            .fill(DS.cardBg)
            .overlay(PeriodOutcomeSymbolShape10868(symbol: one.symbol).stroke(one.tint, lineWidth: 2))
            .frame(width: symbolSize, height: symbolSize)
            .accessibilityHidden(true)
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback and the original is
    /// exact; otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: PeriodOutcomeAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelect: nil, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: Completed periods during play (opt-in)

// #10868 — the live first-set card: during play, each period the owner admits
// completed shows both outcomes' own panels — name, original pre-match chance
// on its 0–100% bar, the owner's count blocks, the reported count, the
// reported period state, and that original's own result — extracted from the
// approved design (totals-final-forecast-binding-20261024 `LiveTennis.tsx`,
// `kind === 'set'`, + `liveTennis.css`).
//
// The opt-in is a display permission for context the owner supplies. It never
// decides that a period is over, never turns `.during` into `.final`, and
// never shows anything before play. Blocks are the owner's, in the owner's
// order: they show games won, never play order, and are never counted, summed
// or checked against the score. The reported period state ("Set lost") and the
// original's own result ("Result pending") are separate: neither grades,
// marks or replaces the other. No current chance, later quote or match-level
// figure enters a panel.
//
// Host binding still owed — not available at this base. An owner must supply
// the admitted completed period identities, per period and outcome the exact
// block states and state words, and the card's original-result title and
// blocks note.

/// One block of an outcome's count artwork.
nonisolated enum PeriodOutcomeCountBlock10868: Equatable {
    /// One unit won ("one game").
    case filled
    case empty
}

/// One outcome's own artwork and reported state in one period, by exact
/// period and series identity.
nonisolated struct PeriodOutcomeActualPanel10868: Equatable {
    /// Opaque owner identity of this panel.
    let id: String
    let periodID: String
    let seriesID: String
    /// The owner's blocks, in the owner's order. Never derived from the score.
    let blocks: [PeriodOutcomeCountBlock10868]
    /// "Set lost" — this outcome's reported state in the period. Never a grade.
    let state: String
}

nonisolated struct PeriodOutcomeCompletedDuringPlayWords10868: Equatable {
    /// "Original market result" — spoken before each original's own result.
    let originalResultTitle: String
    /// "Each block is one game won, not play-by-play order. Score and market
    /// settlement are separate." — shown only when a panel draws blocks.
    let blocksNote: String?
}

/// The owner's explicit permission to show completed periods during play.
nonisolated struct PeriodOutcomeCompletedDuringPlay10868: Equatable {
    /// The exact identities of the periods the owner admits completed.
    let completedPeriodIDs: [String]
    let panels: [PeriodOutcomeActualPanel10868]
    let words: PeriodOutcomeCompletedDuringPlayWords10868
}

/// An outcome's panel in a period, by exact identity.
nonisolated enum PeriodOutcomePanelLookup10868: Equatable {
    case panel(PeriodOutcomeActualPanel10868)
    /// No panel names this period and outcome.
    case absent
    /// More than one panel, or an identity that is blank or used twice —
    /// nothing is chosen.
    case ambiguous

    var panel: PeriodOutcomeActualPanel10868? {
        if case .panel(let panel) = self { return panel }
        return nil
    }
}

/// One outcome's reported count, taken from the period's score line.
nonisolated struct PeriodOutcomePanelCount10868: Equatable {
    let text: String
    let unit: String
}

/// Where each block sits when equal blocks wrap into rows, and the space
/// they take.
nonisolated struct PeriodOutcomeBlockPlan10868: Equatable {
    /// Each block's top-leading corner, in the owner's order.
    let origins: [CGPoint]
    let size: CGSize
}

nonisolated enum PeriodOutcomeBlockGeometry10868 {
    /// Blocks left to right in the owner's order, as many to a row as the
    /// width holds whole, then onto the next row — never shrunk, never
    /// dropped, at least one to a row. With no finite width, one row.
    /// Malformed sizes place nothing.
    static func plan(count: Int, block: CGSize, spacing: CGFloat, width: CGFloat?) -> PeriodOutcomeBlockPlan10868 {
        guard count > 0, block.width.isFinite, block.height.isFinite, block.width > 0, block.height >= 0,
              spacing.isFinite, spacing >= 0 else { return PeriodOutcomeBlockPlan10868(origins: [], size: .zero) }
        let step = block.width + spacing
        let perRow: Int
        if let width, width.isFinite, width > 0 {
            perRow = min(count, max(1, Int(((width + spacing) / step).rounded(.down))))
        } else {
            perRow = count
        }
        let origins = (0..<count).map { index in
            CGPoint(x: CGFloat(index % perRow) * step, y: CGFloat(index / perRow) * (block.height + spacing))
        }
        let rows = (count + perRow - 1) / perRow
        return PeriodOutcomeBlockPlan10868(
            origins: origins,
            size: CGSize(width: CGFloat(perRow) * step - spacing, height: CGFloat(rows) * (block.height + spacing) - spacing)
        )
    }
}

/// Equal blocks that wrap onto more rows rather than overflow. The size it
/// reports is the plan it places.
struct PeriodOutcomeBlockWrapLayout10868: Layout {
    let blockSize: CGSize
    var spacing: CGFloat = 3

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        PeriodOutcomeBlockGeometry10868.plan(count: subviews.count, block: blockSize, spacing: spacing, width: proposal.width).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let plan = PeriodOutcomeBlockGeometry10868.plan(count: subviews.count, block: blockSize, spacing: spacing, width: bounds.width)
        for index in 0..<min(subviews.count, plan.origins.count) {
            let origin = plan.origins[index]
            subviews[index].place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y),
                                  anchor: .topLeading, proposal: ProposedViewSize(blockSize))
        }
    }
}

extension PeriodOutcomeFinalScoreInput10868 {
    /// During play with the opt-in only: the periods whose exact, unique
    /// identity the owner lists as completed, in the owner's period order.
    var completedPeriodIndicesDuringPlay: [Int] {
        guard comparison.phase == .during, let completedDuringPlay else { return [] }
        return comparison.periods.indices.filter { index in
            hasExactIdentity(periodIndex: index)
                && completedDuringPlay.completedPeriodIDs.contains(comparison.periods[index].id)
        }
    }

    /// During play, a shown period with originals shows one panel per
    /// outcome and its score moves into the panels. A score-only period keeps
    /// the final card's score and words.
    func showsPanels(periodIndex: Int) -> Bool {
        comparison.phase == .during && periodIndices.contains(periodIndex) && scoreOnlyText(periodIndex: periodIndex) == nil
    }

    /// The outcome's own panel. A missing, duplicated, blank or mis-scoped
    /// panel attaches nothing, and no outcome borrows another's.
    func panel(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> PeriodOutcomePanelLookup10868 {
        guard showsPanels(periodIndex: periodIndex), let completedDuringPlay else { return .absent }
        guard hasExactIdentity(periodIndex: periodIndex), hasExactIdentity(one) else { return .ambiguous }
        let periodID = comparison.periods[periodIndex].id
        let panels = completedDuringPlay.panels
        let matches = panels.filter { $0.periodID == periodID && $0.seriesID == one.id }
        switch matches.count {
        case 0:
            return .absent
        case 1:
            let found = matches[0]
            guard Self.isExact(found.id), panels.filter({ $0.id == found.id }).count == 1 else { return .ambiguous }
            return .panel(found)
        default:
            return .ambiguous
        }
    }

    /// The outcome's own reported count, from the period's score line by
    /// exact series identity — never half a score, never computed.
    func panelCount(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> PeriodOutcomePanelCount10868? {
        guard showsPanels(periodIndex: periodIndex),
              case .reported(let entries, let unit) = scoreLine(periodIndex: periodIndex),
              let entry = entries.first(where: { $0.series.id == one.id }) else { return nil }
        return PeriodOutcomePanelCount10868(text: entry.text, unit: unit)
    }

    /// The owner's blocks, only beside the outcome's reported count: blocks
    /// never stand in for a missing score.
    func panelBlocks(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> [PeriodOutcomeCountBlock10868]? {
        guard let found = panel(one, periodIndex: periodIndex).panel, !found.blocks.isEmpty,
              panelCount(one, periodIndex: periodIndex) != nil else { return nil }
        return found.blocks
    }

    /// The outcome's reported state in the period, verbatim.
    func panelState(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> String? {
        panel(one, periodIndex: periodIndex).panel?.state
    }

    /// The exact original's own result, as the owner resolved it — never from
    /// the score, the reported state or the phase.
    func originalResult(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> PeriodOutcomeResult10868? {
        guard showsPanels(periodIndex: periodIndex) else { return nil }
        return chance(one, periodIndex: periodIndex).cell?.result
    }

    /// The owner's title for each original's own result — shown and spoken
    /// with it, so a pending market never reads as the set's result.
    var originalResultTitle: String? { completedDuringPlay?.words.originalResultTitle }

    /// Text shown in a panel period's header when it has no reported score.
    func panelScoreMissing(periodIndex: Int) -> String? {
        guard showsPanels(periodIndex: periodIndex), case .missing(let text) = scoreLine(periodIndex: periodIndex) else { return nil }
        return text
    }

    /// Whether any shown panel draws blocks.
    var showsAnyBlocks: Bool {
        periodIndices.contains { index in
            comparison.series.contains { panelBlocks($0, periodIndex: index) != nil }
        }
    }

    /// One panel: the pregame chance with its own clock, then the count, the
    /// reported state and the original's own result — each separately.
    func accessibilityPanelValue(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> String {
        var parts = [accessibilityChanceValue(chance(one, periodIndex: periodIndex))]
        if let count = panelCount(one, periodIndex: periodIndex) {
            parts.append("\(words.actualTitle): \(count.text) \(count.unit)")
        }
        if let state = panelState(one, periodIndex: periodIndex) {
            parts.append(state)
        }
        if let result = originalResult(one, periodIndex: periodIndex), let title = originalResultTitle {
            parts.append("\(title): \(result.text)")
        }
        return parts.joined(separator: "; ")
    }
}

extension PeriodOutcomeFinalScorePresentation10868 {
    /// A panel period's name and reported winner; its score is in the panels,
    /// or its missing words here.
    private func panelPeriodHeader(_ index: Int, period: PeriodOutcomePeriod10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(period.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            winner(input.winnerLine(periodIndex: index))
            if let missing = input.panelScoreMissing(periodIndex: index) {
                Text(missing)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(period.label)
        .accessibilityValue(input.accessibilityPeriodValue(periodIndex: index))
    }

    /// One outcome's panel. A button only with the callback and an exact
    /// original, through the same Details action as the final card.
    @ViewBuilder
    private func panel(_ one: PeriodOutcomeSeries10868, periodIndex: Int) -> some View {
        let lookup = input.chance(one, periodIndex: periodIndex)
        let action = input.detailsAction(one, periodIndex: periodIndex, canOpenDetails: canOpenDetails)
        control(action) {
            VStack(alignment: .leading, spacing: 8) {
                playerName(one)
                panelChance(lookup)
                if let cell = lookup.cell {
                    bar(one, fraction: input.barFraction(cell))
                }
                if let blocks = input.panelBlocks(one, periodIndex: periodIndex) {
                    blockRow(one, blocks: blocks)
                }
                if let count = input.panelCount(one, periodIndex: periodIndex) {
                    panelCount(count)
                }
                if let state = input.panelState(one, periodIndex: periodIndex) {
                    Text(state)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let result = input.originalResult(one, periodIndex: periodIndex), let title = input.originalResultTitle {
                    panelResult(result, title: title)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .frame(minHeight: 44)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(DS.border, lineWidth: 1))
            .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .accessibilityLabel(input.accessibilityChanceLabel(one, periodIndex: periodIndex))
        .accessibilityValue(input.accessibilityPanelValue(one, periodIndex: periodIndex))
        .accessibilityHint(action == nil ? "" : input.comparison.words.detailsHint)
        .accessibilityIdentifier(lookup.cell.map { PeriodOutcomeFinalScoreAccessibilityID10868.chance($0.id) } ?? "")
    }

    /// The pregame figure at the panel size with its label, or the owner's words.
    @ViewBuilder
    private func panelChance(_ lookup: PeriodOutcomeCellLookup10868) -> some View {
        if let cell = lookup.cell {
            VStack(alignment: .leading, spacing: 2) {
                switch input.comparison.pregameReading(cell) {
                case .value(let observation):
                    Text(observation.text)
                        .font(.system(size: panelFigureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: true, vertical: false)
                case .missing(let text):
                    Text(text)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(input.comparison.words.pregameTitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } else {
            Text(input.comparison.words.cellUnavailable)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The owner's blocks in the owner's order: filled in the outcome's tint,
    /// empty as an outline, so they differ by shape as well as colour. They
    /// wrap onto more rows rather than overflow a narrow panel.
    private func blockRow(_ one: PeriodOutcomeSeries10868, blocks: [PeriodOutcomeCountBlock10868]) -> some View {
        PeriodOutcomeBlockWrapLayout10868(blockSize: CGSize(width: blockWidth, height: blockHeight)) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                RoundedRectangle(cornerRadius: 3)
                    .fill(block == .filled ? one.tint : Color.clear)
                    .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(block == .filled ? one.tint : DS.border, lineWidth: 1))
                    .frame(width: blockWidth, height: blockHeight)
            }
        }
        .accessibilityHidden(true)
    }

    /// The count at the panel size; the unit drops below it rather than
    /// squeezing the number.
    private func panelCount(_ count: PeriodOutcomePanelCount10868) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                countFigure(count.text)
                unitText(count.unit)
            }
            VStack(alignment: .leading, spacing: 0) {
                countFigure(count.text)
                unitText(count.unit)
            }
        }
    }

    private func countFigure(_ text: String) -> some View {
        Text(text)
            .font(.system(size: panelFigureSize, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: true, vertical: false)
    }

    /// The original's own result under the owner's title, so it reads apart
    /// from the set state above it: ✓ / ✕ only beside an admitted one, so a
    /// pending result never reads as a loss.
    private func panelResult(_ result: PeriodOutcomeResult10868, title: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                switch result.mark {
                case .positive?:
                    Image(systemName: "checkmark.circle").accessibilityHidden(true)
                case .negative?:
                    Image(systemName: "xmark.circle").accessibilityHidden(true)
                case nil:
                    EmptyView()
                }
                Text(result.text)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .font(result.isAdmitted ? Font.footnote.weight(.semibold) : Font.footnote)
            .foregroundStyle(result.mark == .positive ? DS.textPrimary : DS.textSecondary)
        }
    }
}

// MARK: Named periods before play (opt-in)

// #10868 — the pregame first-set card: before play, each period the owner
// names shows both outcomes' own panels with only their original pre-match
// chance, large, on the same 0–100% bar — so both chances read together
// without selecting one. Extracted from the approved design
// (totals-final-forecast-binding-20261024 `LiveTennis.tsx` `Chance` and the
// `kind === 'set'` panels, + `liveTennis.css`), with every later channel left
// out.
//
// It reuses the panels, bars, exact period/series/original lookups, Details
// action and measured equal row above, and keeps the phase `.before`. Before
// play the card reads no actual context, no panel artwork, no count, no set
// state, no original result, no current or later reading and none of the
// card's own words: the headline, summary, pre-match heading and notes come
// only from the owner's pregame copy, verbatim. The opt-in never decides that
// play has not started and never turns `.before` into another phase.
//
// Host binding still owed — not available at this base. An owner must supply
// the exact identities of the periods to show before play and the pregame
// copy, alongside the admitted comparison input with each original's own
// pre-match observation.

/// The card's own copy for the phase it is shown in: the headline, the line
/// under it, the shared pre-match heading and the notes. Chosen and formatted
/// by the owner per phase — never parsed, reformatted or carried across phases.
nonisolated struct PeriodOutcomeCardCopy10868: Equatable {
    /// "FIRST SET · BEFORE PLAY"
    let eyebrow: String?
    /// "Who takes the first set?"
    let title: String
    /// A line under the headline, or none.
    let summary: String?
    /// "Pre-match chances" — shown once above the periods.
    let pregameHeading: String
    /// "Chance bars share a 0–100% scale."
    let scaleNote: String?
    /// "Tap a player for the original market and recorded time." — shown
    /// only when Details can be opened.
    let detailsNote: String?
}

/// The owner's explicit permission to show named periods before play.
nonisolated struct PeriodOutcomeBeforePlay10868: Equatable {
    /// The exact identities of the periods to show. Shown in the owner's
    /// period order; a blank, foreign or ambiguous identity shows nothing and
    /// no other period stands in for it.
    let periodIDs: [String]
    /// The only words the card shows before play.
    let copy: PeriodOutcomeCardCopy10868
}

extension PeriodOutcomeFinalScoreInput10868 {
    /// Before play with the opt-in only: the periods whose exact, unique
    /// identity the owner names, in the owner's period order. No cap and no
    /// first or nearest pick.
    var periodIndicesBeforePlay: [Int] {
        guard comparison.phase == .before, let beforePlay else { return [] }
        return comparison.periods.indices.filter { index in
            hasExactIdentity(periodIndex: index) && beforePlay.periodIDs.contains(comparison.periods[index].id)
        }
    }

    /// Before play, a shown period shows one panel per outcome, with its
    /// pre-match chance only. An outcome without a single original keeps its
    /// panel and says so; nothing is invented or borrowed.
    func showsPanelsBeforePlay(periodIndex: Int) -> Bool {
        comparison.phase == .before && periodIndices.contains(periodIndex)
    }

    /// The copy shown: before play, with the opt-in, only the owner's pregame
    /// copy; otherwise the card's own words, unchanged.
    var copy: PeriodOutcomeCardCopy10868 {
        if comparison.phase == .before, let beforePlay { return beforePlay.copy }
        return PeriodOutcomeCardCopy10868(eyebrow: words.eyebrow, title: words.title, summary: words.summary,
                                          pregameHeading: words.pregameHeading, scaleNote: words.scaleNote,
                                          detailsNote: words.detailsNote)
    }
}
