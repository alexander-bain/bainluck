import SwiftUI

// #10868 — the chances of a game total reaching each milestone, across the
// match's lifecycle, as one sport-neutral profile. x is the sporting quantity
// ("total goals"), y the chance of reaching at least that milestone on a fixed
// 0–100% scale. Before play the profile holds the saved pregame chances as
// hollow marks. During play each milestone may also carry an independently
// admitted in-game chance as a filled mark on the same axes, and the count so
// far is a solid rule on the quantity axis — a count, never a probability.
// After the final the hollow pregame marks stay, the final count is the rule,
// and the selected milestone's pregame chance sits beside the owner-admitted
// contract result. When no chance can be drawn at all, the offered milestones
// sit on a quantity strip with no probability axis.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `HockeyBeforePage` totalCard,
// `HockeyLiveTotalGoals`, the equal-prominence `HockeyChancePair`,
// `HockeyTotalStoryCard` → `CatalogProbabilityCard` → `KnownTotalLadder`;
// hockey-readable-card-composition-20261026 `H439TotalGoalsCard`; the
// live-history-baselines-v295 `NativeHockeyGoalsCard`; and the pregame
// `HockeyBeforeViews.swift` totals card).
//
// Every figure, label, tick, count, clock, status, movement, comparison,
// projection, missing qualifier and result arrives resolved by the owner and
// is shown verbatim. This layer never formats, rounds, ranks, filters or joins,
// never converts a threshold to a count, never groups by unit, never reads a
// clock, cache, subscription or admission rule, never elects a baseline or
// decides whether a reading is recent, never derives a movement or a result,
// and never shows a settled 0%/100% as a chance. A reached milestone is
// performance — "Actual so far" — not settlement and not 100%. A missing
// observation draws nothing; 0% is a real observation and draws a mark at 0%.
// The axis domain comes from the owner's milestones, the visible count and
// projection, and any owner domain — never from the selection.
//
// A consumer may opt into probability stems (the soccer goal outlook): each
// drawn pregame mark also gets its own vertical stem from the 0% line up to
// that mark, on the same axes and scale, drawn behind every mark and rule.
// Stems never join, interpolate or add a milestone; a missing, invalid or
// withheld pregame chance has no stem, and a quoted 0% keeps its mark with a
// zero-length stem. The default stays the plain marks.
//
// Every original milestone also sits in a compact strip under the chart, in
// owner order and never filtered or capped: its own pregame chance, then the
// in-game state during play or the owner's result after the final, so a
// reader sees which milestones hit without opening each one. The strip wraps
// into rows by measured width and is one column at accessibility sizes.
//
// Milestone selection, timing disclosure and Details stay with the host: the
// view keeps no selected state, no sheet, no focus and no subscription. With
// no callback there is no button, no strip action and no adjustable action.
//
// Host binding still owed — not available at this base. An owner must supply,
// for one same-unit total in owner order:
//   • each milestone's exact original id, its qualified quantity coordinate
//     (the owner's threshold → count conversion) and formatted labels,
//   • an admitted pregame observation (raw value, figure, short clock, full
//     time/source) or its own missing words,
//   • during play, an independently admitted in-game observation with
//     currentness already applied, or its own unavailable / withheld /
//     reached words, and any movement or performance already formatted,
//   • the clocked count so far, then the final count, or their words,
//   • an independently admitted contract result per milestone,
//   • only where admitted, a pregame projection with its clock and comparison;
// and for the card: the copy, axis titles, ticks, any domain, the selected id,
// the timing lines, Details, Back and the held selection.

/// One admitted chance. `probability` drives geometry only; `text` is what the
/// reader sees.
nonisolated struct TotalMilestoneObservation10868: Equatable {
    let probability: Double
    let text: String
    /// The owner's short visible clock for this reading ("4:54 PM"); nil draws none.
    let timeText: String?
    /// Full time and source for VoiceOver ("Oct 3, 4:54 PM PT · Kalshi consensus").
    let accessibilityDetail: String
}

/// The owner's in-game chance for one milestone, currentness applied. Only
/// `.recorded` draws a mark.
nonisolated enum TotalMilestoneCurrent10868: Equatable {
    /// An independently admitted in-game observation, with the owner's
    /// already-formatted movement since pregame, if any.
    case recorded(TotalMilestoneObservation10868, movement: String?)
    /// No in-game reading ("No in-game reading").
    case unavailable(String)
    /// A reading exists but the owner withholds it ("No update since goal").
    case withheld(String)
    /// The count has already reached this milestone in play ("Reached").
    /// Performance, not a settlement and not 100%.
    case reached(String)
}

/// The glyph beside an admitted result's words in the strip.
nonisolated enum TotalMilestoneResultMark10868: Equatable {
    case check
    case cross
}

/// The owner-admitted contract result. There is no Bool, so an absent result
/// can never read as missed, and it is never derived from a count.
nonisolated enum TotalMilestoneResult10868: Equatable {
    /// A result worded by the milestone's own direction ("Reached", "Missed").
    case reached(String)
    case missed(String)
    /// The original contract won, whichever side it is on ("Original Under
    /// 4.5: won"). The owner admits it; it is never inferred from a count, a
    /// threshold, a name, a chance or a complementary contract's result.
    case won(String)
    /// The original contract lost, whichever side it is on.
    case lost(String)
    /// Pending, missing, ambiguous or conflicting ("Result unconfirmed").
    case unconfirmed(String)

    var text: String {
        switch self {
        case .reached(let text), .missed(let text), .won(let text), .lost(let text), .unconfirmed(let text): text
        }
    }

    var isAdmitted: Bool {
        if case .unconfirmed = self { return false }
        return true
    }

    /// A check for reached or won, a cross for missed or lost; unconfirmed has
    /// neither, so unknown never reads as either.
    var mark: TotalMilestoneResultMark10868? {
        switch self {
        case .reached, .won: .check
        case .missed, .lost: .cross
        case .unconfirmed: nil
        }
    }
}

/// One original milestone of the total, in the owner's order.
nonisolated struct TotalMilestoneRow10868: Equatable {
    /// Opaque original contract identity, passed back exactly.
    let id: String
    /// The owner's qualified quantity coordinate (6 for "Over 5.5"). Geometry
    /// only; a negative or non-finite value draws nothing but keeps the row.
    let quantity: Double
    /// The short axis label ("6+").
    let quantityLabel: String
    /// The full milestone ("6+ goals").
    let title: String
    let before: TotalMilestoneObservation10868?
    /// The owner's words for a missing pregame chance ("Unavailable").
    let beforeMissing: String
    /// Read only during play.
    let current: TotalMilestoneCurrent10868
    /// Owner-formatted performance comparison ("2 more needed",
    /// "Finished 1 short"); read during play and after the final.
    let performance: String?
    /// Read only after the final.
    let result: TotalMilestoneResult10868
}

/// An owner-admitted count of the sporting quantity.
nonisolated struct TotalMilestoneCount10868: Equatable {
    /// Coordinate for the solid rule; a negative or non-finite value draws no rule.
    let quantity: Double
    /// "4".
    let text: String
    /// "goals"; nil draws no unit.
    let unit: String?
    /// The owner's short visible clock ("3rd · 14:34 left"); nil draws none.
    let clock: String?
    /// The rule's direct label ("4 so far"); nil leaves the rule unlabelled.
    let ruleLabel: String?
    /// Full clock and source for VoiceOver.
    let accessibilityDetail: String
}

nonisolated enum TotalMilestoneActual10868: Equatable {
    case count(TotalMilestoneCount10868)
    /// "Count unavailable", "Exact final count unavailable".
    case unavailable(String)
}

/// An admitted pregame projection of the quantity — a quantity, never a chance.
nonisolated struct TotalMilestoneProjection10868: Equatable {
    let quantity: Double
    /// "Pregame projection".
    let title: String
    /// "5.8 goals".
    let text: String
    let clock: String?
    /// "5.8 projected"; nil leaves the dashed rule unlabelled.
    let ruleLabel: String?
    /// Owner-formatted comparison with the final ("0.8 goals below projection").
    let comparison: String?
    let accessibilityDetail: String
}

nonisolated enum TotalMilestonePhase10868: Equatable {
    case before
    case during
    case final
}

nonisolated struct TotalMilestoneTick10868: Equatable {
    /// Raw coordinate: a quantity on the quantity axis, a probability 0...1 on
    /// the chance axis.
    let value: Double
    /// The owner's label ("6", "50%").
    let text: String
}

/// An owner-supplied quantity range. Unioned with the milestones, the count
/// and the projection; a malformed range is ignored.
nonisolated struct TotalMilestoneDomain10868: Equatable {
    let lower: Double
    let upper: Double
}

/// The owner's timing disclosure for one milestone. Shown only while that
/// exact milestone is the resolved selection.
nonisolated struct TotalMilestoneTiming10868: Equatable {
    let milestoneID: String
    /// "6+ goals · probability timing".
    let title: String
    let lines: [String]
}

nonisolated enum TotalMilestoneSelection10868: Equatable {
    case none
    case selected(TotalMilestoneRow10868, index: Int)
    /// No milestone carries the selected id.
    case missing(String)
    /// More than one milestone carries the selected id.
    case duplicate(String)

    var milestone: TotalMilestoneRow10868? {
        if case .selected(let milestone, _) = self { return milestone }
        return nil
    }

    var index: Int? {
        if case .selected(_, let index) = self { return index }
        return nil
    }
}

nonisolated enum TotalMilestoneReading10868: Equatable {
    case value(TotalMilestoneObservation10868)
    case missing(String)
}

/// The in-game slot beside the pregame chance, during play. A reached
/// milestone stays apart from every chance state.
nonisolated enum TotalMilestoneCurrentReading10868: Equatable {
    /// The only state drawn as a filled mark.
    case chance(TotalMilestoneObservation10868)
    /// Unavailable or withheld, in the owner's words.
    case chanceStatus(String)
    /// Already reached in play, in the owner's words.
    case actual(String)

    var title: String {
        switch self {
        case .chance: TotalMilestoneInput10868.recordedTitle
        case .chanceStatus: TotalMilestoneInput10868.currentStatusTitle
        case .actual: TotalMilestoneInput10868.actualSoFarTitle
        }
    }

    var spokenTitle: String {
        switch self {
        case .chance: TotalMilestoneInput10868.spokenRecorded
        case .chanceStatus: TotalMilestoneInput10868.currentStatusTitle
        case .actual: TotalMilestoneInput10868.actualSoFarTitle
        }
    }

    var reading: TotalMilestoneReading10868 {
        switch self {
        case .chance(let observation): .value(observation)
        case .chanceStatus(let text), .actual(let text): .missing(text)
        }
    }
}

/// What sits beside the pregame chance in the selected comparison.
nonisolated enum TotalMilestoneSecondReading10868: Equatable {
    case current(TotalMilestoneCurrentReading10868)
    case result(TotalMilestoneResult10868)
}

/// The count block: its fixed title and the owner's count or words.
nonisolated struct TotalMilestoneActualPresentation10868: Equatable {
    let title: String
    let actual: TotalMilestoneActual10868
}

nonisolated enum TotalMilestoneAnnotationKind10868: Equatable {
    case selection
    case actual
    case projection
}

/// A direct label above the plot, centred on its quantity.
nonisolated struct TotalMilestoneAnnotation10868: Equatable {
    let kind: TotalMilestoneAnnotationKind10868
    let quantity: Double
    let text: String
}

nonisolated enum TotalMilestoneMarkKind10868: Equatable {
    case pregame
    case current
}

/// How the plot draws pregame chances. Existing consumers keep `.dots`.
nonisolated enum TotalMilestoneMarkStyle10868: Equatable {
    /// Marks only.
    case dots
    /// Marks plus one stem per drawn pregame mark, from the 0% line to the mark.
    case stems
}

/// The series a key under the chart names: only those actually drawn.
nonisolated struct TotalMilestoneChartKey10868: Equatable {
    /// Hollow "Pregame chance".
    let pregame: Bool
    /// Filled "Recorded in-game".
    let recorded: Bool
}

/// One original milestone in the strip, from the same phase helpers as the
/// selected comparison.
nonisolated struct TotalMilestoneStripEntry10868: Equatable {
    /// The owner's index.
    let index: Int
    let milestone: TotalMilestoneRow10868
    let pregame: TotalMilestoneReading10868
    /// Nil before play; the in-game state during; the result after the final.
    let second: TotalMilestoneSecondReading10868?
    let selected: Bool
    /// The hollow key beside the pregame figure: during play, and only for a
    /// mark the plot draws.
    let pregameMark: Bool
    /// The filled key beside the in-game figure: only for a drawn recorded mark.
    let currentMark: Bool
}

nonisolated struct TotalMilestonePlotMark10868: Equatable {
    /// The owner's index.
    let index: Int
    let kind: TotalMilestoneMarkKind10868
    let point: CGPoint
    let selected: Bool
}

/// One pregame mark's stem: the mark's own x, from its y down to the 0% line.
nonisolated struct TotalMilestonePlotStem10868: Equatable {
    /// The owner's index.
    let index: Int
    let x: CGFloat
    let markY: CGFloat
    let baselineY: CGFloat
}

/// Everything the plot draws, in its own coordinates.
nonisolated struct TotalMilestonePlotModel10868: Equatable {
    /// No chance can be drawn: offered milestones on a quantity strip, no
    /// probability axis.
    let isStrip: Bool
    /// Chance gridlines (scatter only).
    let gridlines: [CGFloat]
    /// Opt-in only, one per drawn pregame mark; drawn first, behind everything.
    let stems: [TotalMilestonePlotStem10868]
    let marks: [TotalMilestonePlotMark10868]
    /// Strip only: one short tick per offered milestone.
    let milestoneTicks: [CGFloat]
    let selectionX: CGFloat?
    let actualX: CGFloat?
    let projectionX: CGFloat?
    /// The strip's track line.
    let trackY: CGFloat
    /// Where the projection's square sits: the 0% line, or the strip's track.
    let baselineY: CGFloat
}

nonisolated enum TotalMilestoneAction10868: Equatable {
    case select(String)
    case details(String)

    func perform(onSelect: ((String) -> Void)?, onDetails: ((String) -> Void)?) {
        switch self {
        case .select(let id): onSelect?(id)
        case .details(let id): onDetails?(id)
        }
    }
}

nonisolated enum TotalMilestoneTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(TotalMilestoneTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(TotalMilestoneTiming10868)
}

nonisolated struct TotalMilestoneInput10868: Equatable {
    let phase: TotalMilestonePhase10868
    /// "TOTAL GOALS · BOTH TEAMS".
    let eyebrow: String?
    /// "Room for more goals?".
    let title: String
    /// Plain-language chance-axis title ("Chance of reaching each total").
    let chartTitle: String?
    /// Plain-language quantity-axis title ("Total goals in the game").
    let quantityAxisTitle: String?
    /// One same-unit total, in the owner's order.
    let milestones: [TotalMilestoneRow10868]
    /// The owner's exact milestone selection.
    let selectedMilestoneID: String?
    /// Read during play (count so far) and after the final (final count).
    let actual: TotalMilestoneActual10868?
    /// Read only after the final, and only where the owner admitted one.
    let projection: TotalMilestoneProjection10868?
    let quantityDomain: TotalMilestoneDomain10868?
    let quantityTicks: [TotalMilestoneTick10868]
    /// Ticks on the fixed 0...1 chance scale.
    let chanceTicks: [TotalMilestoneTick10868]
    let timing: TotalMilestoneTiming10868?
    /// Opt-in stems under the pregame marks; last and defaulted, so existing
    /// callers pass nothing and keep the plain marks.
    var markStyle: TotalMilestoneMarkStyle10868 = .dots

    static let pregameTitle = "Pregame chance"
    static let recordedTitle = "Recorded in-game"
    static let currentStatusTitle = "In-game chance"
    static let actualSoFarTitle = "Actual so far"
    static let resultTitle = "Final result"
    static let countSoFarTitle = "Count so far"
    static let finalCountTitle = "Final count"
    static let detailsTitle = "Details & recorded times"
    static let selectorTitle = "Choose milestone"
    static let noSelection = "No milestone selected"
    static let previousTitle = "Previous milestone"
    static let nextTitle = "Next milestone"
    static let milestoneUnavailable = "Selected milestone unavailable."
    static let spokenRecorded = "Recorded in-game chance"
    static let spokenMovement = "Change since pregame"
    static let spokenBefore = "Before play"
    static let spokenDuring = "During play"
    static let spokenFinal = "Final"
    static let spokenHollow = "Hollow marks are pregame chances."
    static let spokenStems = "Each stem rises from the zero line to one pregame mark; the marks are separate readings, not a curve."
    static let spokenFilled = "Filled marks are recorded in-game chances."
    static let spokenRule = "The solid rule is the count, not a chance."
    static let spokenProjection = "The dashed rule is a projection, not a chance."
    static let spokenStrip = "Offered milestones on the count scale; no chances are shown."

    // MARK: Selection

    /// Exact id only. A missing or duplicated id gets no substitute milestone.
    var selection: TotalMilestoneSelection10868 {
        guard let selectedMilestoneID else { return .none }
        let matches = milestones.indices.filter { milestones[$0].id == selectedMilestoneID }
        switch matches.count {
        case 1: return .selected(milestones[matches[0]], index: matches[0])
        case 0: return .missing(selectedMilestoneID)
        default: return .duplicate(selectedMilestoneID)
        }
    }

    func isSelected(index: Int) -> Bool {
        selection.index == index
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: Self.milestoneUnavailable
        case .none, .selected: nil
        }
    }

    // MARK: Phase visibility

    func beforeReading(_ milestone: TotalMilestoneRow10868) -> TotalMilestoneReading10868 {
        milestone.before.map { .value($0) } ?? .missing(milestone.beforeMissing)
    }

    /// The in-game slot, during play only.
    func currentReading(_ milestone: TotalMilestoneRow10868) -> TotalMilestoneCurrentReading10868? {
        guard phase == .during else { return nil }
        switch milestone.current {
        case .recorded(let observation, _): return .chance(observation)
        case .unavailable(let text), .withheld(let text): return .chanceStatus(text)
        case .reached(let text): return .actual(text)
        }
    }

    /// The owner's movement, during play and only beside a recorded reading.
    func movement(_ milestone: TotalMilestoneRow10868) -> String? {
        guard phase == .during, case .recorded(_, let movement) = milestone.current else { return nil }
        return movement
    }

    /// The owner's performance comparison, during play and after the final.
    func performance(_ milestone: TotalMilestoneRow10868) -> String? {
        phase == .before ? nil : milestone.performance
    }

    /// The contract result, after the final only.
    func result(_ milestone: TotalMilestoneRow10868) -> TotalMilestoneResult10868? {
        phase == .final ? milestone.result : nil
    }

    /// Nil before play: the selected chance stands alone.
    func secondReading(_ milestone: TotalMilestoneRow10868) -> TotalMilestoneSecondReading10868? {
        if let result = result(milestone) { return .result(result) }
        return currentReading(milestone).map { .current($0) }
    }

    /// None before play; "Count so far" during; "Final count" after.
    var actualPresentation: TotalMilestoneActualPresentation10868? {
        guard let actual else { return nil }
        switch phase {
        case .before: return nil
        case .during: return TotalMilestoneActualPresentation10868(title: Self.countSoFarTitle, actual: actual)
        case .final: return TotalMilestoneActualPresentation10868(title: Self.finalCountTitle, actual: actual)
        }
    }

    /// After the final only.
    var visibleProjection: TotalMilestoneProjection10868? {
        phase == .final ? projection : nil
    }

    /// The count's coordinate when the phase shows it and it is drawable.
    var visibleActualQuantity: Double? {
        guard actualPresentation != nil, case .count(let count)? = actual else { return nil }
        return TotalMilestoneGeometry10868.quantity(count.quantity)
    }

    var visibleProjectionQuantity: Double? {
        visibleProjection.flatMap { TotalMilestoneGeometry10868.quantity($0.quantity) }
    }

    // MARK: Marks and axes

    /// The hollow pregame mark's chance, any phase.
    func beforeFraction(_ milestone: TotalMilestoneRow10868) -> Double? {
        milestone.before.flatMap { TotalMilestoneGeometry10868.fraction($0.probability) }
    }

    /// The filled in-game mark's chance, during play and only for a recorded reading.
    func currentFraction(_ milestone: TotalMilestoneRow10868) -> Double? {
        guard case .chance(let observation)? = currentReading(milestone) else { return nil }
        return TotalMilestoneGeometry10868.fraction(observation.probability)
    }

    /// True when at least one milestone has a drawable quantity and chance in this phase.
    var hasProbabilityMarks: Bool {
        milestones.contains { milestone in
            TotalMilestoneGeometry10868.quantity(milestone.quantity) != nil
                && (beforeFraction(milestone) != nil || currentFraction(milestone) != nil)
        }
    }

    var isQuantityStrip: Bool { !hasProbabilityMarks }

    /// Every drawable milestone, the visible count and projection, and any
    /// well-formed owner range. Independent of the selection.
    var domain: TotalMilestoneDomain10868? {
        var values = milestones.compactMap { TotalMilestoneGeometry10868.quantity($0.quantity) }
        if let actual = visibleActualQuantity { values.append(actual) }
        if let projection = visibleProjectionQuantity { values.append(projection) }
        return TotalMilestoneGeometry10868.domain(values: values, owner: quantityDomain)
    }

    /// The owner's quantity ticks that fall inside the domain, in order.
    var placedQuantityTicks: [TotalMilestoneTick10868] {
        guard let domain else { return [] }
        return quantityTicks.filter { tick in
            TotalMilestoneGeometry10868.quantity(tick.value).map { $0 >= domain.lower && $0 <= domain.upper } ?? false
        }
    }

    /// The owner's chance ticks the 0...1 scale can place; none on a strip.
    var placedChanceTicks: [TotalMilestoneTick10868] {
        guard !isQuantityStrip else { return [] }
        return chanceTicks.filter { TotalMilestoneGeometry10868.fraction($0.value) != nil }
    }

    /// Direct labels above the plot: the selected milestone, the count rule
    /// and the projection rule, each only when drawable and labelled.
    var annotations: [TotalMilestoneAnnotation10868] {
        var result: [TotalMilestoneAnnotation10868] = []
        if let selected = selection.milestone, let quantity = TotalMilestoneGeometry10868.quantity(selected.quantity) {
            result.append(TotalMilestoneAnnotation10868(kind: .selection, quantity: quantity, text: selected.quantityLabel))
        }
        if let quantity = visibleActualQuantity, case .count(let count)? = actual, let label = count.ruleLabel {
            result.append(TotalMilestoneAnnotation10868(kind: .actual, quantity: quantity, text: label))
        }
        if let quantity = visibleProjectionQuantity, let label = visibleProjection?.ruleLabel {
            result.append(TotalMilestoneAnnotation10868(kind: .projection, quantity: quantity, text: label))
        }
        return result
    }

    /// The comparison carries the filled key only beside a recorded reading.
    func showsCurrentKey(_ milestone: TotalMilestoneRow10868) -> Bool {
        if case .chance? = currentReading(milestone) { return true }
        return false
    }

    /// A hollow mark is drawn: a placeable pregame chance at a drawable quantity.
    var drawsPregameMarks: Bool {
        milestones.contains { TotalMilestoneGeometry10868.quantity($0.quantity) != nil && beforeFraction($0) != nil }
    }

    /// A filled mark is drawn: a recorded in-game chance at a drawable quantity.
    var drawsCurrentMarks: Bool {
        milestones.contains { TotalMilestoneGeometry10868.quantity($0.quantity) != nil && currentFraction($0) != nil }
    }

    /// During play the comparison's pregame figure carries the hollow key.
    /// Before play and after the final it carries none, so only the selected
    /// milestone's own ringed hollow mark ties its figure to the series.
    func comparisonNamesPregame(_ milestone: TotalMilestoneRow10868) -> Bool {
        if phase == .during { return true }
        return TotalMilestoneGeometry10868.quantity(milestone.quantity) != nil && beforeFraction(milestone) != nil
    }

    /// Every drawn series, whenever the selected comparison leaves one of them
    /// unnamed — no selection, a missing or duplicated one, or a selection
    /// without that reading. Nil on a strip, and when the comparison already
    /// names everything drawn.
    var chartKey: TotalMilestoneChartKey10868? {
        let pregame = drawsPregameMarks
        let recorded = drawsCurrentMarks
        guard pregame || recorded else { return nil }
        let selected = selection.milestone
        let pregameNamed = !pregame || selected.map { comparisonNamesPregame($0) } == true
        let recordedNamed = !recorded || selected.map { showsCurrentKey($0) } == true
        if pregameNamed && recordedNamed { return nil }
        return TotalMilestoneChartKey10868(pregame: pregame, recorded: recorded)
    }

    var showsChartKey: Bool { chartKey != nil }

    /// The plot's marks and rules for this size. The quantity scale depends
    /// only on `domain`, so a selection change never moves a mark.
    func plotModel(size: CGSize, inset: CGFloat) -> TotalMilestonePlotModel10868? {
        guard let domain else { return nil }
        let strip = isQuantityStrip
        func x(_ quantity: Double) -> CGFloat? {
            TotalMilestoneGeometry10868.x(quantity, domain: domain, width: size.width, inset: inset)
        }
        let selectedIndex = selection.index
        let zeroY = strip ? nil : TotalMilestoneGeometry10868.y(0, height: size.height, inset: inset)
        var marks: [TotalMilestonePlotMark10868] = []
        var stems: [TotalMilestonePlotStem10868] = []
        var ticks: [CGFloat] = []
        for (index, milestone) in milestones.enumerated() {
            guard let px = x(milestone.quantity) else { continue }
            if strip {
                ticks.append(px)
                continue
            }
            if let fraction = beforeFraction(milestone), let py = TotalMilestoneGeometry10868.y(fraction, height: size.height, inset: inset) {
                marks.append(TotalMilestonePlotMark10868(index: index, kind: .pregame, point: CGPoint(x: px, y: py),
                                                         selected: index == selectedIndex))
                if markStyle == .stems, let zeroY {
                    stems.append(TotalMilestonePlotStem10868(index: index, x: px, markY: py, baselineY: zeroY))
                }
            }
            if let fraction = currentFraction(milestone), let py = TotalMilestoneGeometry10868.y(fraction, height: size.height, inset: inset) {
                marks.append(TotalMilestonePlotMark10868(index: index, kind: .current, point: CGPoint(x: px, y: py),
                                                         selected: index == selectedIndex))
            }
        }
        let gridlines = strip ? [] : placedChanceTicks.compactMap {
            TotalMilestoneGeometry10868.y($0.value, height: size.height, inset: inset)
        }
        return TotalMilestonePlotModel10868(
            isStrip: strip,
            gridlines: gridlines,
            stems: stems,
            marks: marks,
            milestoneTicks: ticks,
            selectionX: selection.milestone.flatMap { x($0.quantity) },
            actualX: visibleActualQuantity.flatMap { x($0) },
            projectionX: visibleProjectionQuantity.flatMap { x($0) },
            trackY: size.height / 2,
            baselineY: strip ? size.height / 2 : zeroY ?? size.height / 2
        )
    }

    // MARK: Timing and actions

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> TotalMilestoneTimingPresentation10868? {
        guard let timing, let selected = selection.milestone, selected.id == timing.milestoneID else { return nil }
        return hasBinding ? .disclosure(timing) : .expanded(timing)
    }

    /// The exact original id chosen, passed back unchanged.
    func selectAction(id: String, canSelect: Bool) -> TotalMilestoneAction10868? {
        canSelect ? .select(id) : nil
    }

    /// The adjacent original milestone in owner order, from a resolved
    /// selection only — never from a missing or duplicate one.
    func stepAction(_ offset: Int, canSelect: Bool) -> TotalMilestoneAction10868? {
        guard canSelect, let index = selection.index else { return nil }
        let target = index + offset
        guard milestones.indices.contains(target) else { return nil }
        return .select(milestones[target].id)
    }

    func detailsAction(canOpenDetails: Bool) -> TotalMilestoneAction10868? {
        guard canOpenDetails, let milestone = selection.milestone else { return nil }
        return .details(milestone.id)
    }

    // MARK: Original milestones strip

    /// Every original milestone in owner order — none filtered, ranked or
    /// capped — with the readings its phase shows.
    var stripEntries: [TotalMilestoneStripEntry10868] {
        milestones.enumerated().map { index, milestone -> TotalMilestoneStripEntry10868 in
            let drawable = TotalMilestoneGeometry10868.quantity(milestone.quantity) != nil
            return TotalMilestoneStripEntry10868(
                index: index,
                milestone: milestone,
                pregame: beforeReading(milestone),
                second: secondReading(milestone),
                selected: isSelected(index: index),
                pregameMark: phase == .during && drawable && beforeFraction(milestone) != nil,
                currentMark: drawable && currentFraction(milestone) != nil
            )
        }
    }

    /// The strip entry's exact original id, passed back unchanged — only when
    /// that id names exactly one milestone, since a duplicated id can only
    /// resolve nobody.
    func stripAction(index: Int, canSelect: Bool) -> TotalMilestoneAction10868? {
        guard milestones.indices.contains(index) else { return nil }
        let id = milestones[index].id
        guard milestones.filter({ $0.id == id }).count == 1 else { return nil }
        return selectAction(id: id, canSelect: canSelect)
    }

    /// "6+ · 5 of 9", or the milestone count when nothing is resolved.
    var positionText: String {
        if let milestone = selection.milestone, let index = selection.index {
            return "\(milestone.quantityLabel) · \(index + 1) of \(milestones.count)"
        }
        return "\(milestones.count) \(milestones.count == 1 ? "milestone" : "milestones")"
    }

    // MARK: VoiceOver

    var spokenPhase: String {
        switch phase {
        case .before: Self.spokenBefore
        case .during: Self.spokenDuring
        case .final: Self.spokenFinal
        }
    }

    var accessibilityHeader: String {
        ([eyebrow, title, spokenPhase].compactMap { $0 }).joined(separator: ". ")
    }

    func accessibilityActual(_ presentation: TotalMilestoneActualPresentation10868) -> String {
        switch presentation.actual {
        case .count(let count):
            var figure = count.text
            if let unit = count.unit { figure += " \(unit)" }
            return [figure, count.accessibilityDetail].joined(separator: ", ")
        case .unavailable(let text):
            return text
        }
    }

    func accessibilityProjection(_ projection: TotalMilestoneProjection10868) -> String {
        var parts = ["\(projection.text), \(projection.accessibilityDetail)"]
        if let comparison = projection.comparison { parts.append(comparison) }
        return parts.joined(separator: "; ")
    }

    /// Baseline, then the separately timed in-game reading or the result.
    func accessibilityComparison(for milestone: TotalMilestoneRow10868) -> String {
        var parts = [Self.spoken(beforeReading(milestone), title: Self.pregameTitle)]
        switch secondReading(milestone) {
        case .current(let current)?:
            parts.append(Self.spoken(current.reading, title: current.spokenTitle))
            if let movement = movement(milestone) { parts.append("\(Self.spokenMovement): \(movement)") }
        case .result(let result)?:
            parts.append("\(Self.resultTitle): \(result.text)")
        case nil:
            break
        }
        if let performance = performance(milestone) { parts.append(performance) }
        return parts.joined(separator: "; ")
    }

    /// What one strip entry shows: its pregame chance, then its in-game state
    /// or result.
    func accessibilityStripValue(_ entry: TotalMilestoneStripEntry10868) -> String {
        var parts = [Self.spoken(entry.pregame, title: Self.pregameTitle)]
        switch entry.second {
        case .current(let current)?:
            parts.append(Self.spoken(current.reading, title: current.spokenTitle))
        case .result(let result)?:
            parts.append("\(Self.resultTitle): \(result.text)")
        case nil:
            break
        }
        return parts.joined(separator: "; ")
    }

    var accessibilityChartLabel: String {
        var parts = [isQuantityStrip ? (quantityAxisTitle ?? title) : (chartTitle ?? title)]
        if isQuantityStrip {
            parts.append(Self.spokenStrip)
        } else {
            if drawsPregameMarks { parts.append(Self.spokenHollow) }
            if drawsPregameMarks && markStyle == .stems { parts.append(Self.spokenStems) }
            if drawsCurrentMarks { parts.append(Self.spokenFilled) }
        }
        if visibleActualQuantity != nil { parts.append(Self.spokenRule) }
        if visibleProjectionQuantity != nil { parts.append(Self.spokenProjection) }
        return parts.joined(separator: " ")
    }

    var accessibilityChartValue: String {
        if let milestone = selection.milestone {
            return "\(milestone.title). \(accessibilityComparison(for: milestone))"
        }
        return selectionNotice ?? Self.noSelection
    }

    private static func spoken(_ reading: TotalMilestoneReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text): "\(title): \(text)"
        }
    }
}

/// Label frames along one axis and the depth they use.
nonisolated struct TotalMilestoneAxisPlan10868: Equatable {
    /// In the caller's order.
    let frames: [CGRect]
    let depth: CGFloat
}

/// Every chart piece placed within the chart's bounds.
nonisolated struct TotalMilestoneChartPlan10868: Equatable {
    let plot: CGRect
    let chanceLabels: [CGRect]
    let annotations: [CGRect]
    let quantityTicks: [CGRect]
    let size: CGSize
}

nonisolated enum TotalMilestoneGeometry10868 {
    /// Room kept at each end of the plot, both axes, so an endpoint mark and
    /// its selection ring (`ringRadius` plus its stroke) stay inside.
    static let plotInset: CGFloat = 12
    static let pregameDiameter: CGFloat = 9
    static let currentDiameter: CGFloat = 8
    static let selectedPregameDiameter: CGFloat = 13
    static let selectedCurrentDiameter: CGFloat = 11
    static let ringRadius: CGFloat = 10

    /// A chance's place on the fixed 0...1 scale; nil for non-finite or
    /// out-of-range — the mark is omitted, never clamped or drawn at zero.
    static func fraction(_ value: Double) -> Double? {
        guard value.isFinite, value >= 0, value <= 1 else { return nil }
        return value
    }

    /// A drawable quantity: finite and not negative.
    static func quantity(_ value: Double) -> Double? {
        guard value.isFinite, value >= 0 else { return nil }
        return value
    }

    /// The union of the drawable values and a well-formed owner range.
    static func domain(values: [Double], owner: TotalMilestoneDomain10868?) -> TotalMilestoneDomain10868? {
        var all = values.compactMap { quantity($0) }
        if let owner, let lower = quantity(owner.lower), let upper = quantity(owner.upper), lower <= upper {
            all.append(contentsOf: [lower, upper])
        }
        guard let lower = all.min(), let upper = all.max() else { return nil }
        return TotalMilestoneDomain10868(lower: lower, upper: upper)
    }

    /// The x of a quantity inside the end insets. A one-value domain centres
    /// it. Nil outside the domain or for a degenerate width.
    static func x(_ value: Double, domain: TotalMilestoneDomain10868, width: CGFloat, inset: CGFloat) -> CGFloat? {
        guard let value = quantity(value), value >= domain.lower, value <= domain.upper,
              width.isFinite, width > 0 else { return nil }
        let span = domain.upper - domain.lower
        guard span > 0 else { return width / 2 }
        let usable = max(0, width - 2 * inset)
        return min(width, max(0, inset)) + usable * CGFloat((value - domain.lower) / span)
    }

    /// The y of a chance in a plot of this height, inside the top and bottom
    /// insets (100% at the top inset, 0% at the bottom one), so an endpoint
    /// mark and its selection ring stay inside the plot.
    static func y(_ value: Double, height: CGFloat, inset: CGFloat) -> CGFloat? {
        guard let value = fraction(value), height.isFinite, height > 0 else { return nil }
        let inset = min(max(0, inset.isFinite ? inset : 0), height / 2)
        return inset + (height - 2 * inset) * CGFloat(1 - value)
    }

    /// Lanes for labels centred on positions along one axis. Each label stays
    /// inside the axis; one that would come within `gap` of a label already on
    /// a lane moves to the next lane instead of away from its position or
    /// shrinking. A label longer than the axis gets a lane of its own at the
    /// start. Positions need not be sorted; ties keep the caller's order.
    static func lanes(centers: [CGFloat], lengths: [CGFloat], extent: CGFloat, gap: CGFloat) -> [(origin: CGFloat, lane: Int)] {
        guard centers.count == lengths.count else { return [] }
        let extent = extent.isFinite ? max(0, extent) : 0
        func clean(_ value: CGFloat) -> CGFloat { value.isFinite ? value : 0 }
        let order = centers.indices.sorted { a, b in
            clean(centers[a]) == clean(centers[b]) ? a < b : clean(centers[a]) < clean(centers[b])
        }
        var ends: [CGFloat] = []
        var result = [(origin: CGFloat, lane: Int)](repeating: (0, 0), count: centers.count)
        for i in order {
            let length = max(0, clean(lengths[i]))
            if length > extent {
                ends.append(.infinity)
                result[i] = (0, ends.count - 1)
                continue
            }
            let origin = min(max(0, clean(centers[i]) - length / 2), extent - length)
            if let lane = ends.firstIndex(where: { $0 + gap <= origin }) {
                ends[lane] = origin + length
                result[i] = (origin, lane)
            } else {
                ends.append(origin + length)
                result[i] = (origin, ends.count - 1)
            }
        }
        return result
    }

    /// Rows of labels along a horizontal axis. Lane 0 sits against the plot:
    /// at the bottom of a band above it (`growsUp`) or at the top of one below.
    static func rows(centers: [CGFloat], sizes: [CGSize], extent: CGFloat, gap: CGFloat = 6, laneGap: CGFloat = 2,
                     growsUp: Bool) -> TotalMilestoneAxisPlan10868 {
        guard centers.count == sizes.count, !sizes.isEmpty else { return TotalMilestoneAxisPlan10868(frames: [], depth: 0) }
        let placements = lanes(centers: centers, lengths: sizes.map(\.width), extent: extent, gap: gap)
        let offsets = laneOffsets(placements.map { $0.lane }, depths: sizes.map(\.height), laneGap: laneGap)
        let frames = zip(placements, sizes).map { placement, size in
            let y = growsUp
                ? offsets.total - offsets.starts[placement.lane] - size.height
                : offsets.starts[placement.lane]
            return CGRect(x: placement.origin, y: y, width: size.width, height: size.height)
        }
        return TotalMilestoneAxisPlan10868(frames: frames, depth: offsets.total)
    }

    /// Columns of labels along a vertical axis of this height. Lane 0 sits
    /// beside the plot (trailing); each label is trailing-aligned in its column.
    static func columns(fractions: [Double], sizes: [CGSize], height: CGFloat, inset: CGFloat, gap: CGFloat = 2,
                        laneGap: CGFloat = 6) -> TotalMilestoneAxisPlan10868 {
        guard fractions.count == sizes.count, !sizes.isEmpty else { return TotalMilestoneAxisPlan10868(frames: [], depth: 0) }
        let centers = fractions.map { y($0, height: height, inset: inset) ?? 0 }
        let placements = lanes(centers: centers, lengths: sizes.map(\.height), extent: height, gap: gap)
        let offsets = laneOffsets(placements.map { $0.lane }, depths: sizes.map(\.width), laneGap: laneGap)
        let frames = zip(placements, sizes).map { placement, size in
            CGRect(x: offsets.total - offsets.starts[placement.lane] - size.width, y: placement.origin,
                   width: size.width, height: size.height)
        }
        return TotalMilestoneAxisPlan10868(frames: frames, depth: offsets.total)
    }

    private static func laneOffsets(_ lanes: [Int], depths: [CGFloat], laneGap: CGFloat) -> (starts: [CGFloat], total: CGFloat) {
        let count = (lanes.max() ?? -1) + 1
        var laneDepth = [CGFloat](repeating: 0, count: count)
        for (lane, depth) in zip(lanes, depths) { laneDepth[lane] = max(laneDepth[lane], depth.isFinite ? depth : 0) }
        var starts: [CGFloat] = []
        var running: CGFloat = 0
        for depth in laneDepth {
            starts.append(running)
            running += depth + laneGap
        }
        return (starts, max(0, running - laneGap))
    }

    /// The chart: chance labels in columns at the leading edge, then a band of
    /// direct labels, the plot, and quantity tick rows, all sharing the plot's
    /// x scale. Sizes are the labels' measured sizes; a label wider than the
    /// plot should already be measured at the plot width (it wraps).
    static func chartPlan(width: CGFloat, plotHeight: CGFloat, inset: CGFloat, domain: TotalMilestoneDomain10868?,
                          chanceFractions: [Double], chanceSizes: [CGSize],
                          annotationValues: [Double], annotationSizes: [CGSize],
                          tickValues: [Double], tickSizes: [CGSize],
                          spacing: CGFloat = 6) -> TotalMilestoneChartPlan10868 {
        let width = width.isFinite ? max(0, width) : 0
        let plotHeight = plotHeight.isFinite ? max(0, plotHeight) : 0
        let column = columns(fractions: chanceFractions, sizes: chanceSizes, height: plotHeight, inset: inset)
        let leading = column.depth > 0 ? column.depth + spacing : 0
        let plotWidth = plotWidth(width: width, leading: column.depth, spacing: spacing)
        func centers(_ values: [Double]) -> [CGFloat] {
            values.map { value in domain.flatMap { x(value, domain: $0, width: plotWidth, inset: inset) } ?? 0 }
        }
        let band = rows(centers: centers(annotationValues), sizes: annotationSizes, extent: plotWidth, growsUp: true)
        let ticks = rows(centers: centers(tickValues), sizes: tickSizes, extent: plotWidth, growsUp: false)
        let plotTop = band.depth > 0 ? band.depth + spacing / 2 : 0
        let plot = CGRect(x: leading, y: plotTop, width: plotWidth, height: plotHeight)
        let tickTop = plot.maxY + (ticks.depth > 0 ? spacing / 2 : 0)
        let reach = (band.frames + ticks.frames).map { leading + $0.maxX }.max() ?? 0
        return TotalMilestoneChartPlan10868(
            plot: plot,
            chanceLabels: column.frames.map { $0.offsetBy(dx: 0, dy: plotTop) },
            annotations: band.frames.map { $0.offsetBy(dx: leading, dy: 0) },
            quantityTicks: ticks.frames.map { $0.offsetBy(dx: leading, dy: tickTop) },
            size: CGSize(width: max(width, reach), height: tickTop + ticks.depth)
        )
    }

    static func plotWidth(width: CGFloat, leading: CGFloat, spacing: CGFloat = 6) -> CGFloat {
        max(0, width - (leading > 0 ? leading + spacing : 0))
    }

    // MARK: Strip

    /// The width of each of `columns` equal cells across `width`.
    static func stripCellWidth(columns: Int, width: CGFloat, spacing: CGFloat) -> CGFloat {
        guard columns > 0, width.isFinite else { return 0 }
        return max(0, (width - CGFloat(columns - 1) * spacing) / CGFloat(columns))
    }

    /// The most equal columns, up to one per entry and `maximumColumns`, whose
    /// cells are at least `minimumCellWidth` and in which every entry `fits`
    /// whole. Otherwise one column, where the entries wrap.
    static func stripColumns(count: Int, width: CGFloat, spacing: CGFloat, minimumCellWidth: CGFloat,
                             maximumColumns: Int? = nil, fits: (CGFloat) -> Bool) -> Int {
        guard count > 0 else { return 0 }
        let cap = min(count, max(1, maximumColumns ?? count))
        var columns = cap
        while columns > 1 {
            let cell = stripCellWidth(columns: columns, width: width, spacing: spacing)
            if cell >= minimumCellWidth && fits(cell) { return columns }
            columns -= 1
        }
        return 1
    }

    /// Row-major cell frames in owner order; each row is as tall as its
    /// tallest entry, so a row's cells line up.
    static func stripFrames(columns: Int, cellWidth: CGFloat, heights: [CGFloat], spacing: CGFloat)
        -> (frames: [CGRect], size: CGSize) {
        guard columns > 0, !heights.isEmpty else { return ([], .zero) }
        var frames: [CGRect] = []
        var top: CGFloat = 0
        var start = 0
        while start < heights.count {
            let row = heights[start..<min(start + columns, heights.count)]
            let height = row.map { $0.isFinite ? max(0, $0) : 0 }.max() ?? 0
            for offset in 0..<row.count {
                frames.append(CGRect(x: CGFloat(offset) * (cellWidth + spacing), y: top, width: cellWidth, height: height))
            }
            top += height + spacing
            start += columns
        }
        let width = CGFloat(min(columns, heights.count)) * (cellWidth + spacing) - spacing
        return (frames, CGSize(width: max(0, width), height: max(0, top - spacing)))
    }
}

/// Places the original-milestone strip: equal cells in as many columns as
/// every entry fits whole at its natural width, otherwise fewer, down to one
/// column where text wraps. Nothing shrinks, truncates or hides.
struct TotalMilestoneStripLayout10868: Layout {
    let minimumCellWidth: CGFloat
    /// 1 at accessibility sizes.
    var maximumColumns: Int? = nil
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? 320
        return plan(width: width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = plan(width: bounds.width, subviews: subviews).frames
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(width: CGFloat, subviews: Subviews) -> (frames: [CGRect], size: CGSize) {
        let natural = subviews.map { $0.sizeThatFits(.unspecified).width }
        let columns = TotalMilestoneGeometry10868.stripColumns(
            count: subviews.count, width: width, spacing: spacing, minimumCellWidth: minimumCellWidth,
            maximumColumns: maximumColumns
        ) { cell in natural.allSatisfy { $0 <= cell } }
        let cell = TotalMilestoneGeometry10868.stripCellWidth(columns: columns, width: width, spacing: spacing)
        let heights = subviews.map { $0.sizeThatFits(ProposedViewSize(width: cell, height: nil)).height }
        return TotalMilestoneGeometry10868.stripFrames(columns: columns, cellWidth: cell, heights: heights, spacing: spacing)
    }
}

/// Places the chart's subviews by `TotalMilestoneGeometry10868.chartPlan`:
/// the plot, then one subview per chance tick, per annotation and per
/// quantity tick, in that order. The size it reports is the plan it places.
struct TotalMilestoneChartLayout10868: Layout {
    let domain: TotalMilestoneDomain10868?
    let chanceFractions: [Double]
    let annotationValues: [Double]
    let tickValues: [Double]
    let plotHeight: CGFloat
    var inset: CGFloat = TotalMilestoneGeometry10868.plotInset

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? 320
        return plan(width: width, subviews: subviews)?.size ?? .zero
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let plan = plan(width: bounds.width, subviews: subviews) else { return }
        let frames = [plan.plot] + plan.chanceLabels + plan.annotations + plan.quantityTicks
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(width: CGFloat, subviews: Subviews) -> TotalMilestoneChartPlan10868? {
        let c = chanceFractions.count, a = annotationValues.count, t = tickValues.count
        guard subviews.count == 1 + c + a + t else { return nil }
        let chanceSizes = (0..<c).map { subviews[1 + $0].sizeThatFits(.unspecified) }
        let column = TotalMilestoneGeometry10868.columns(fractions: chanceFractions, sizes: chanceSizes,
                                                         height: plotHeight, inset: inset)
        let plotWidth = TotalMilestoneGeometry10868.plotWidth(width: width, leading: column.depth)
        func fitted(_ index: Int) -> CGSize {
            let natural = subviews[index].sizeThatFits(.unspecified)
            guard natural.width > plotWidth else { return natural }
            return subviews[index].sizeThatFits(ProposedViewSize(width: plotWidth, height: nil))
        }
        return TotalMilestoneGeometry10868.chartPlan(
            width: width, plotHeight: plotHeight, inset: inset, domain: domain,
            chanceFractions: chanceFractions, chanceSizes: chanceSizes,
            annotationValues: annotationValues, annotationSizes: (0..<a).map { fitted(1 + c + $0) },
            tickValues: tickValues, tickSizes: (0..<t).map { fitted(1 + c + a + $0) }
        )
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum TotalMilestoneAccessibilityID10868 {
    static func comparison(_ id: String) -> String { "totalMilestone10868.comparison.\(id)" }
    static func details(_ id: String) -> String { "totalMilestone10868.details.\(id)" }
    static func option(_ id: String) -> String { "totalMilestone10868.option.\(id)" }
    static let chart = "totalMilestone10868.chart"
    static let actual = "totalMilestone10868.actual"
    static let projection = "totalMilestone10868.projection"
    static let previous = "totalMilestone10868.previous"
    static let next = "totalMilestone10868.next"
    static let selector = "totalMilestone10868.selector"
}

struct TotalMilestonePresentation10868: View {
    let input: TotalMilestoneInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 30
    @ScaledMetric(relativeTo: .title) private var countSize: CGFloat = 34
    @ScaledMetric(relativeTo: .footnote) private var plotHeight: CGFloat = 180
    @ScaledMetric(relativeTo: .footnote) private var stripHeight: CGFloat = 40
    @ScaledMetric(relativeTo: .subheadline) private var optionMinimumWidth: CGFloat = 96

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var pregameTint: Color { DS.blue }
    private var currentTint: Color { DS.emeraldDark }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            headerRow
            if let projection = input.visibleProjection {
                projectionBlock(projection)
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let milestone = input.selection.milestone {
                comparison(milestone)
            }
            if input.domain != nil {
                chartSection
            }
            if !input.milestones.isEmpty {
                milestoneStrip
                stepper
            }
            timing
            detailsButton
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header, count and projection

    @ViewBuilder private var headerRow: some View {
        let actual = input.actualPresentation
        if typeSize.isAccessibilitySize || actual == nil {
            VStack(alignment: .leading, spacing: 10) { headerParts(actual) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 12) { headerParts(actual, spaced: true) }
                VStack(alignment: .leading, spacing: 10) { headerParts(actual) }
            }
        }
    }

    @ViewBuilder private func headerParts(_ actual: TotalMilestoneActualPresentation10868?, spaced: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = input.eyebrow {
                Text(eyebrow).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            Text(input.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
        if spaced { Spacer(minLength: 0) }
        if let actual {
            actualBlock(actual)
        }
    }

    /// The count — prominent, labelled, with its own clock, and never on a
    /// probability axis.
    private func actualBlock(_ presentation: TotalMilestoneActualPresentation10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(presentation.title).font(.caption).foregroundStyle(DS.textSecondary)
            switch presentation.actual {
            case .count(let count):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(count.text)
                        .font(.system(size: countSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if let unit = count.unit {
                        Text(unit).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                }
                if let clock = count.clock {
                    Text(clock).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            case .unavailable(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .padding(.leading, 12)
        .overlay(alignment: .leading) { Rectangle().fill(DS.border).frame(width: 1) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(presentation.title)
        .accessibilityValue(input.accessibilityActual(presentation))
        .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.actual)
    }

    /// An admitted projection: a quantity with its own clock, beside — never
    /// inside — the chances.
    private func projectionBlock(_ projection: TotalMilestoneProjection10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                RoundedRectangle(cornerRadius: 1)
                    .strokeBorder(DS.textSecondary, lineWidth: 1.5)
                    .frame(width: 9, height: 9)
                    .accessibilityHidden(true)
                Text(projection.title).font(.caption).foregroundStyle(DS.textSecondary)
            }
            Text(projection.text).font(.title3.bold()).monospacedDigit().foregroundStyle(DS.textPrimary)
            if let clock = projection.clock {
                Text(clock).font(.footnote).foregroundStyle(DS.textSecondary)
            }
            if let comparison = projection.comparison {
                Text(comparison).font(.footnote.weight(.semibold)).foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(projection.title)
        .accessibilityValue(input.accessibilityProjection(projection))
        .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.projection)
    }

    // MARK: Selected comparison

    private func comparison(_ milestone: TotalMilestoneRow10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(milestone.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 14) { comparisonValues(milestone) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { comparisonValues(milestone) }
                    VStack(alignment: .leading, spacing: 14) { comparisonValues(milestone) }
                }
            }
            if let movement = input.movement(milestone) {
                Text(movement)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(currentTint)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let performance = input.performance(milestone) {
                Text(performance)
                    .font(.footnote)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(milestone.title)
        .accessibilityValue(input.accessibilityComparison(for: milestone))
        .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.comparison(milestone.id))
    }

    @ViewBuilder private func comparisonValues(_ milestone: TotalMilestoneRow10868) -> some View {
        // The hollow/filled key only when two chances can sit side by side.
        chanceValue(input.beforeReading(milestone), title: TotalMilestoneInput10868.pregameTitle,
                    mark: input.phase == .during ? .hollow : nil)
        switch input.secondReading(milestone) {
        case .current(let current)?:
            chanceValue(current.reading, title: current.title, mark: input.showsCurrentKey(milestone) ? .filled : nil)
        case .result(let result)?:
            resultValue(result)
        case nil:
            EmptyView()
        }
    }

    private enum KeyMark { case hollow, filled }

    private func chanceValue(_ reading: TotalMilestoneReading10868, title: String, mark: KeyMark?) -> some View {
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
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
                if let time = observation.timeText {
                    Text(time).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The owner's result words at the same scale as the chance — never a
    /// 0% or 100%. Unconfirmed reads as status.
    private func resultValue(_ result: TotalMilestoneResult10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(TotalMilestoneInput10868.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
            if result.isAdmitted {
                Text(result.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .foregroundStyle(DS.textPrimary)
            } else {
                Text(result.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func keyMark(_ mark: KeyMark) -> some View {
        switch mark {
        case .hollow:
            Circle().fill(DS.cardBg)
                .overlay(Circle().strokeBorder(pregameTint, lineWidth: 2))
                .frame(width: 10, height: 10)
        case .filled:
            Circle().fill(currentTint).frame(width: 10, height: 10)
        }
    }

    // MARK: Chart

    @ViewBuilder private var chartSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let chartTitle = input.chartTitle, !input.isQuantityStrip {
                Text(chartTitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityHidden(true)
            }
            adjustableChart
            if let axisTitle = input.quantityAxisTitle {
                Text(axisTitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityHidden(true)
            }
            if let key = input.chartKey {
                chartKeyView(key)
            }
        }
    }

    /// Only the drawn series. One row when it fits; a column at accessibility
    /// sizes or when it does not.
    private func chartKeyView(_ key: TotalMilestoneChartKey10868) -> some View {
        Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) { chartKeyItems(key) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 12) { chartKeyItems(key) }
                    VStack(alignment: .leading, spacing: 4) { chartKeyItems(key) }
                }
            }
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .accessibilityHidden(true)
    }

    @ViewBuilder private func chartKeyItems(_ key: TotalMilestoneChartKey10868) -> some View {
        if key.pregame {
            HStack(spacing: 5) {
                keyMark(.hollow)
                Text(TotalMilestoneInput10868.pregameTitle).fixedSize(horizontal: false, vertical: true)
            }
        }
        if key.recorded {
            HStack(spacing: 5) {
                keyMark(.filled)
                Text(TotalMilestoneInput10868.recordedTitle).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// One VoiceOver element for the chart; with a callback it is also the
    /// scrubber, stepping through the original milestones in owner order.
    @ViewBuilder private var adjustableChart: some View {
        let element = chart
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityChartLabel)
            .accessibilityValue(input.accessibilityChartValue)
            .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.chart)
        if canSelect, input.selection.index != nil {
            element.accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: perform(input.stepAction(1, canSelect: canSelect))
                case .decrement: perform(input.stepAction(-1, canSelect: canSelect))
                @unknown default: break
                }
            }
        } else {
            element
        }
    }

    private var chart: some View {
        let strip = input.isQuantityStrip
        let chanceTicks = input.placedChanceTicks
        let annotations = input.annotations
        let ticks = input.placedQuantityTicks
        return TotalMilestoneChartLayout10868(
            domain: input.domain,
            chanceFractions: chanceTicks.map(\.value),
            annotationValues: annotations.map(\.quantity),
            tickValues: ticks.map(\.value),
            plotHeight: strip ? stripHeight : plotHeight
        ) {
            plot
            ForEach(Array(chanceTicks.enumerated()), id: \.offset) { _, tick in
                Text(tick.text).font(.caption2).monospacedDigit().foregroundStyle(DS.textSecondary)
            }
            ForEach(Array(annotations.enumerated()), id: \.offset) { _, annotation in
                annotationLabel(annotation)
            }
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.text).font(.caption).monospacedDigit().foregroundStyle(DS.textSecondary)
            }
        }
    }

    @ViewBuilder private func annotationLabel(_ annotation: TotalMilestoneAnnotation10868) -> some View {
        switch annotation.kind {
        case .selection:
            HStack(spacing: 3) {
                Image(systemName: "diamond").font(.caption2.weight(.bold))
                Text(annotation.text).font(.caption.weight(.semibold))
            }
            .foregroundStyle(pregameTint)
        case .actual:
            Text(annotation.text).font(.caption.weight(.bold)).foregroundStyle(DS.textPrimary)
        case .projection:
            HStack(spacing: 3) {
                Image(systemName: "square").font(.caption2)
                Text(annotation.text).font(.caption)
            }
            .foregroundStyle(DS.textSecondary)
        }
    }

    /// Gridlines, any opted-in stems, rules and marks, from `plotModel`. A
    /// selected milestone gets a diamond ring and a larger, thicker mark,
    /// never colour alone.
    private var plot: some View {
        let input = self.input
        let pregameTint = self.pregameTint
        let currentTint = self.currentTint
        let border = DS.border
        let card = DS.cardBg
        let primary = DS.textPrimary
        let secondary = DS.textSecondary
        return Canvas { context, size in
            guard let model = input.plotModel(size: size, inset: TotalMilestoneGeometry10868.plotInset) else { return }
            func vertical(_ x: CGFloat, from top: CGFloat, to bottom: CGFloat) -> Path {
                Path { $0.move(to: CGPoint(x: x, y: top)); $0.addLine(to: CGPoint(x: x, y: bottom)) }
            }
            func diamond(_ center: CGPoint, _ r: CGFloat) -> Path {
                Path { path in
                    path.move(to: CGPoint(x: center.x, y: center.y - r))
                    path.addLine(to: CGPoint(x: center.x + r, y: center.y))
                    path.addLine(to: CGPoint(x: center.x, y: center.y + r))
                    path.addLine(to: CGPoint(x: center.x - r, y: center.y))
                    path.closeSubpath()
                }
            }
            func circle(_ center: CGPoint, _ diameter: CGFloat) -> Path {
                Path(ellipseIn: CGRect(x: center.x - diameter / 2, y: center.y - diameter / 2, width: diameter, height: diameter))
            }
            for y in model.gridlines {
                let line = Path { $0.move(to: CGPoint(x: 0, y: y)); $0.addLine(to: CGPoint(x: size.width, y: y)) }
                context.stroke(line, with: .color(border), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
            }
            // Behind every rule and mark, so neither is ever covered by a stem.
            for stem in model.stems {
                context.stroke(vertical(stem.x, from: stem.markY, to: stem.baselineY), with: .color(pregameTint.opacity(0.25)),
                               lineWidth: 2)
            }
            if model.isStrip {
                let track = Path { $0.move(to: CGPoint(x: 0, y: model.trackY)); $0.addLine(to: CGPoint(x: size.width, y: model.trackY)) }
                context.stroke(track, with: .color(border), style: StrokeStyle(lineWidth: 6, lineCap: .round))
                if let x = model.actualX {
                    let filled = Path { $0.move(to: CGPoint(x: 0, y: model.trackY)); $0.addLine(to: CGPoint(x: x, y: model.trackY)) }
                    context.stroke(filled, with: .color(primary.opacity(0.35)), style: StrokeStyle(lineWidth: 6, lineCap: .round))
                }
                for x in model.milestoneTicks {
                    context.stroke(vertical(x, from: model.trackY + 6, to: model.trackY + 12), with: .color(secondary), lineWidth: 1)
                }
            } else if let x = model.selectionX {
                context.stroke(vertical(x, from: 0, to: size.height), with: .color(pregameTint.opacity(0.3)), lineWidth: 1)
            }
            let ruleTop: CGFloat = model.isStrip ? model.trackY - 12 : 0
            let ruleBottom: CGFloat = model.isStrip ? model.trackY + 12 : size.height
            if let x = model.actualX {
                context.stroke(vertical(x, from: ruleTop, to: ruleBottom), with: .color(primary), lineWidth: 2.5)
            }
            if let x = model.projectionX {
                context.stroke(vertical(x, from: ruleTop, to: ruleBottom), with: .color(secondary),
                               style: StrokeStyle(lineWidth: 2, dash: [5, 4]))
                let square = Path(CGRect(x: x - 4, y: model.baselineY - 4, width: 8, height: 8))
                context.fill(square, with: .color(card))
                context.stroke(square, with: .color(secondary), lineWidth: 2)
            }
            if model.isStrip, let x = model.selectionX {
                let mark = diamond(CGPoint(x: x, y: model.trackY), 8)
                context.fill(mark, with: .color(card))
                context.stroke(mark, with: .color(pregameTint), lineWidth: 2)
            }
            for mark in model.marks.sorted(by: { !$0.selected && $1.selected }) {
                switch mark.kind {
                case .pregame:
                    let shape = circle(mark.point, mark.selected ? TotalMilestoneGeometry10868.selectedPregameDiameter
                                                                 : TotalMilestoneGeometry10868.pregameDiameter)
                    context.fill(shape, with: .color(card))
                    context.stroke(shape, with: .color(pregameTint), lineWidth: mark.selected ? 3 : 2)
                case .current:
                    let shape = circle(mark.point, mark.selected ? TotalMilestoneGeometry10868.selectedCurrentDiameter
                                                                 : TotalMilestoneGeometry10868.currentDiameter)
                    context.fill(shape, with: .color(currentTint))
                    if mark.selected { context.stroke(shape, with: .color(primary), lineWidth: 1.5) }
                }
                if mark.selected {
                    context.stroke(diamond(mark.point, TotalMilestoneGeometry10868.ringRadius), with: .color(primary), lineWidth: 1.5)
                }
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Selection controls

    /// Previous and next through every original milestone in owner order,
    /// from a resolved selection only. No callback, no buttons.
    private var stepper: some View {
        HStack(spacing: 8) {
            if canSelect { stepButton(-1) }
            Spacer(minLength: 0)
            Text(input.positionText)
                .font(.subheadline)
                .foregroundStyle(DS.textPrimary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            if canSelect { stepButton(1) }
        }
        .frame(minHeight: 44)
    }

    private func stepButton(_ offset: Int) -> some View {
        let action = input.stepAction(offset, canSelect: canSelect)
        return Button {
            perform(action)
        } label: {
            Image(systemName: offset < 0 ? "chevron.left" : "chevron.right")
                .font(.body.weight(.semibold))
                .foregroundStyle(action == nil ? DS.textMuted : DS.blue)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .disabled(action == nil)
        .accessibilityLabel(offset < 0 ? TotalMilestoneInput10868.previousTitle : TotalMilestoneInput10868.nextTitle)
        .accessibilityIdentifier(offset < 0 ? TotalMilestoneAccessibilityID10868.previous : TotalMilestoneAccessibilityID10868.next)
    }

    /// Every original milestone at a glance, by its owner title, with the
    /// readings its phase shows. It replaces the menu: every original is
    /// already one tap away here. Choosing one passes its exact id back; the
    /// page decides what is selected.
    @ViewBuilder private var milestoneStrip: some View {
        let strip = TotalMilestoneStripLayout10868(
            minimumCellWidth: optionMinimumWidth,
            maximumColumns: typeSize.isAccessibilitySize ? 1 : nil
        ) {
            ForEach(input.stripEntries, id: \.index) { entry in
                stripOption(entry)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.selector)
        if canSelect {
            strip.accessibilityLabel(TotalMilestoneInput10868.selectorTitle)
        } else {
            strip
        }
    }

    /// A button only when it carries an action; otherwise the same content as
    /// one plain element.
    @ViewBuilder private func stripOption(_ entry: TotalMilestoneStripEntry10868) -> some View {
        let id = entry.milestone.id
        if let action = input.stripAction(index: entry.index, canSelect: canSelect) {
            Button {
                perform(action)
            } label: {
                stripCell(entry)
            }
            .accessibilityLabel(entry.milestone.title)
            .accessibilityValue(input.accessibilityStripValue(entry))
            .accessibilityAddTraits(entry.selected ? .isSelected : [])
            .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.option(id))
        } else {
            stripCell(entry)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(entry.milestone.title)
                .accessibilityValue(input.accessibilityStripValue(entry))
                .accessibilityAddTraits(entry.selected ? .isSelected : [])
                .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.option(id))
        }
    }

    /// Title, pregame chance, then the in-game state or result. The selected
    /// one adds a diamond, the chart's selection shape, and a heavier outline
    /// — never colour alone.
    private func stripCell(_ entry: TotalMilestoneStripEntry10868) -> some View {
        let shape = RoundedRectangle(cornerRadius: 10)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if entry.selected {
                    Image(systemName: "diamond.fill")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityHidden(true)
                }
                Text(entry.milestone.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            stripReading(entry.pregame, title: TotalMilestoneInput10868.pregameTitle,
                         mark: entry.pregameMark ? .hollow : nil)
            switch entry.second {
            case .current(let current)?:
                stripReading(current.reading, title: current.title, mark: entry.currentMark ? .filled : nil)
            case .result(let result)?:
                stripResult(result)
            case nil:
                EmptyView()
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity, alignment: .topLeading)
        .background(entry.selected ? DS.cardBg : DS.surface, in: shape)
        .overlay(shape.strokeBorder(entry.selected ? DS.textPrimary : DS.border, lineWidth: entry.selected ? 2 : 1))
        .contentShape(shape)
    }

    /// The figure keeps its whole width and the phase label sits under it, so
    /// a chance never reads as a count or a result.
    private func stripReading(_ reading: TotalMilestoneReading10868, title: String, mark: KeyMark?) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            switch reading {
            case .value(let observation):
                HStack(spacing: 5) {
                    if let mark { keyMark(mark) }
                    Text(observation.text)
                        .font(.title3.bold())
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: true, vertical: false)
                }
            case .missing(let text):
                Text(text)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(title)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The owner's result words with a check or a cross; unconfirmed has
    /// neither, so unknown never reads as missed.
    private func stripResult(_ result: TotalMilestoneResult10868) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                switch result.mark {
                case .check?:
                    Image(systemName: "checkmark.circle").accessibilityHidden(true)
                case .cross?:
                    Image(systemName: "xmark.circle").accessibilityHidden(true)
                case nil:
                    EmptyView()
                }
                Text(result.text).fixedSize(horizontal: false, vertical: true)
            }
            .font(result.isAdmitted ? .subheadline.weight(.semibold) : .footnote.weight(.semibold))
            .foregroundStyle(result.isAdmitted ? DS.textPrimary : DS.textSecondary)
            Text(TotalMilestoneInput10868.resultTitle)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Timing and Details

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

    private func timingLines(_ content: TotalMilestoneTiming10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(content.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let milestone = input.selection.milestone {
            Button {
                perform(action)
            } label: {
                HStack {
                    Text(TotalMilestoneInput10868.detailsTitle)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityLabel("\(TotalMilestoneInput10868.detailsTitle), \(milestone.title)")
            .accessibilityIdentifier(TotalMilestoneAccessibilityID10868.details(milestone.id))
        }
    }

    private func perform(_ action: TotalMilestoneAction10868?) {
        action?.perform(onSelect: onSelect, onDetails: onDetails)
    }
}

// MARK: - Actual total beside the opening market line (final only)

// #10868 — after the final, the actual total beside the opening market line,
// with every original contract's own pregame chance and result. The line is a
// market threshold, never a projection: it arrives on its own channel
// (`TotalMilestoneOpeningLine10868`) and `TotalMilestoneProjection10868` is
// never read here. The selected original names its own threshold and leads
// with its pregame chance; the line stays the same whichever original is
// selected. A short quantity axis carries the line as a hollow point and the
// count as a solid rule, joined by their distance only when both are drawn.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `TennisFinal` `totals` card,
// `tennisFinal.css`, `TennisPropChance`).
//
// It reuses the profile's own readings, results, count, exact-id selection,
// strip entries, strip layout, quantity geometry, label lanes, chart layout
// and actions. It adds only local nonblank-identity guards; whole-row
// equality never decides membership. Before and during play it shows
// nothing and offers nothing, and the lifecycle profile above is unchanged.
// That suppression is not a pregame or live composition.
//
// Every figure, unit, label, clock, missing word, comparison and result
// arrives resolved by the owner and is shown verbatim. This layer never
// computes a difference, rounds, formats a date, converts a threshold to a
// coordinate, infers a result from a count, elects a baseline, complements a
// chance or reads a final quote. An unknown opening time stays the owner's
// words; neither the pregame clock nor the score clock stands in for it.
//
// Host binding still owed — not available at this base. An owner must supply:
//   • the profile input (phase, copy, originals in owner order with exact ids,
//     owner-qualified coordinates, titles naming each original's own
//     threshold, cutoff-admitted pregame observations, own results, the held
//     id, the final count, any domain, ticks and timing),
//   • the opening line's raw coordinate, figure, unit, title, direct label,
//     clock or unknown-time words, short note and spoken detail, or its
//     unavailable words,
//   • the already-formatted difference, and whether count, line, original
//     coordinates and domain share one unit on one axis,
//   • the originals' group name and any tap invitation;
// and keeps selection, timing disclosure, Details, Back and focus.

/// When the opening line was set: the owner's clock, or the owner's words
/// for an unknown time. Nothing else substitutes for it.
nonisolated enum TotalMilestoneLineTime10868: Equatable {
    /// "Oct 11, 5:30 AM PT".
    case clock(String)
    /// "Opening time unavailable".
    case unknown(String)

    var text: String {
        switch self {
        case .clock(let text), .unknown(let text): text
        }
    }
}

/// The owner's opening market line — a threshold on the quantity axis, never
/// a chance, a projection or an average.
nonisolated struct TotalMilestoneOpeningLine10868: Equatable {
    /// Raw coordinate for the hollow point; a negative or non-finite value
    /// draws nothing but keeps the words.
    let quantity: Double
    /// "22.5".
    let text: String
    /// "games"; nil draws no unit.
    let unit: String?
    /// "Opening market line".
    let title: String
    /// The point's direct label ("22.5 opening"); nil leaves it unlabelled.
    let markLabel: String?
    let time: TotalMilestoneLineTime10868
    /// One short owner line ("A market threshold, not a projected score").
    let note: String?
    /// Source and time for VoiceOver.
    let accessibilityDetail: String
}

nonisolated enum TotalMilestoneOpeningLineState10868: Equatable {
    case line(TotalMilestoneOpeningLine10868)
    /// "Opening line unavailable".
    case unavailable(String)
}

/// The owner's already-formatted difference between the count and the line.
nonisolated struct TotalMilestoneLineDifference10868: Equatable {
    /// "+13.5".
    let figure: String
    /// "games above opening line".
    let caption: String
    /// "+13.5 games above the opening line".
    let spoken: String
}

nonisolated enum TotalMilestoneLineMarkKind10868: Equatable {
    case openingLine
    case actual
}

/// A direct label above the axis, centred on its quantity.
nonisolated struct TotalMilestoneLineMarkLabel10868: Equatable {
    let kind: TotalMilestoneLineMarkKind10868
    let quantity: Double
    let text: String
}

/// The distance band's ends, left to right.
nonisolated struct TotalMilestoneLineSpan10868: Equatable {
    let lower: CGFloat
    let upper: CGFloat
}

/// Everything the axis draws, in its own coordinates.
nonisolated struct TotalMilestoneLinePlotModel10868: Equatable {
    let axisY: CGFloat
    let lineX: CGFloat?
    let actualX: CGFloat?
    let ruleTop: CGFloat
    let ruleBottom: CGFloat
    /// Only when both the line and the count are drawn.
    let distance: TotalMilestoneLineSpan10868?
}

nonisolated struct TotalMilestoneLineComparisonInput10868: Equatable {
    /// The existing profile: phase, copy, originals, held selection, count,
    /// domain, ticks and timing. Its projection is never read here.
    let profile: TotalMilestoneInput10868
    let openingLine: TotalMilestoneOpeningLineState10868
    let difference: TotalMilestoneLineDifference10868?
    /// The owner's admission that the count, the line, the originals'
    /// coordinates and the domain share one unit on one axis. Without it there
    /// is no shared axis and no difference.
    let quantitiesShareUnit: Bool
    /// "Original contracts".
    let originalsTitle: String
    /// "Choose a contract to see its pregame chance"; shown only when a
    /// displayed control can act.
    let invitation: String?

    static let spokenLine = "The hollow circle is the opening market line: a threshold, not a chance and not a projection."
    static let spokenDistance = "The band between them is the distance from the line to the count."

    /// Final only.
    var isPresented: Bool { profile.phase == .final }

    static func isBlank(_ id: String) -> Bool {
        id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    // MARK: Selection

    /// The profile's exact-id selection, after the final, with a blank held
    /// id refused. Never a neighbour, the first original or a winner.
    var selection: TotalMilestoneSelection10868 {
        guard isPresented, let id = profile.selectedMilestoneID else { return .none }
        if Self.isBlank(id) { return .missing(id) }
        return profile.selection
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: TotalMilestoneInput10868.milestoneUnavailable
        case .none, .selected: nil
        }
    }

    /// The selected original's own pregame chance, or its missing words.
    var selectedReading: TotalMilestoneReading10868? {
        selection.milestone.map { profile.beforeReading($0) }
    }

    // MARK: Count, line and difference

    /// "Final count" and the owner's count or words.
    var actualPresentation: TotalMilestoneActualPresentation10868? {
        isPresented ? profile.actualPresentation : nil
    }

    var line: TotalMilestoneOpeningLine10868? {
        guard isPresented, case .line(let line) = openingLine else { return nil }
        return line
    }

    var lineUnavailable: String? {
        guard isPresented, case .unavailable(let text) = openingLine else { return nil }
        return text
    }

    var visibleLineQuantity: Double? {
        guard quantitiesShareUnit, let line else { return nil }
        return TotalMilestoneGeometry10868.quantity(line.quantity)
    }

    var visibleActualQuantity: Double? {
        guard isPresented, quantitiesShareUnit else { return nil }
        return profile.visibleActualQuantity
    }

    /// Only while both quantities are drawn; an orphan difference never shows.
    var visibleDifference: TotalMilestoneLineDifference10868? {
        guard visibleLineQuantity != nil, visibleActualQuantity != nil else { return nil }
        return difference
    }

    // MARK: Axis

    /// The originals' coordinates, the drawn line and count, and any
    /// well-formed owner range. Independent of the selection and of any
    /// projection.
    var domain: TotalMilestoneDomain10868? {
        guard isPresented, quantitiesShareUnit else { return nil }
        var values = profile.milestones.compactMap { TotalMilestoneGeometry10868.quantity($0.quantity) }
        if let line = visibleLineQuantity { values.append(line) }
        if let actual = visibleActualQuantity { values.append(actual) }
        return TotalMilestoneGeometry10868.domain(values: values, owner: profile.quantityDomain)
    }

    var showsPlot: Bool {
        domain != nil && (visibleLineQuantity != nil || visibleActualQuantity != nil)
    }

    /// The owner's quantity ticks inside the domain, in order. The view shows
    /// as many as measured width allows.
    var placedQuantityTicks: [TotalMilestoneTick10868] {
        guard showsPlot, let domain else { return [] }
        return profile.quantityTicks.filter { tick in
            TotalMilestoneGeometry10868.quantity(tick.value).map { $0 >= domain.lower && $0 <= domain.upper } ?? false
        }
    }

    /// Direct labels: the line's, then the count rule's, each only when drawn
    /// and labelled.
    var markLabels: [TotalMilestoneLineMarkLabel10868] {
        guard showsPlot else { return [] }
        var result: [TotalMilestoneLineMarkLabel10868] = []
        if let quantity = visibleLineQuantity, let label = line?.markLabel {
            result.append(TotalMilestoneLineMarkLabel10868(kind: .openingLine, quantity: quantity, text: label))
        }
        if let quantity = visibleActualQuantity, case .count(let count)? = profile.actual, let label = count.ruleLabel {
            result.append(TotalMilestoneLineMarkLabel10868(kind: .actual, quantity: quantity, text: label))
        }
        return result
    }

    /// The axis for this size. Its scale depends only on `domain`.
    func plotModel(size: CGSize, inset: CGFloat) -> TotalMilestoneLinePlotModel10868? {
        guard showsPlot, let domain else { return nil }
        func x(_ quantity: Double?) -> CGFloat? {
            quantity.flatMap { TotalMilestoneGeometry10868.x($0, domain: domain, width: size.width, inset: inset) }
        }
        let height = size.height.isFinite ? max(0, size.height) : 0
        let axisY = height / 2
        let reach = min(14, axisY)
        let lineX = x(visibleLineQuantity)
        let actualX = x(visibleActualQuantity)
        var distance: TotalMilestoneLineSpan10868?
        if let lineX, let actualX {
            distance = TotalMilestoneLineSpan10868(lower: min(lineX, actualX), upper: max(lineX, actualX))
        }
        return TotalMilestoneLinePlotModel10868(axisY: axisY, lineX: lineX, actualX: actualX,
                                                ruleTop: axisY - reach, ruleBottom: axisY + reach, distance: distance)
    }

    // MARK: Originals and actions

    /// Every original in owner order — none filtered, ranked or capped — with
    /// its pregame chance and own result, from the profile's strip entries.
    var originals: [TotalMilestoneStripEntry10868] {
        guard isPresented else { return [] }
        let selectedIndex = selection.index
        return profile.stripEntries.map { entry in
            TotalMilestoneStripEntry10868(index: entry.index, milestone: entry.milestone, pregame: entry.pregame,
                                          second: entry.second, selected: entry.index == selectedIndex,
                                          pregameMark: false, currentMark: false)
        }
    }

    /// The profile's own strip action: the exact id when it is nonblank and
    /// names exactly one original.
    func originalAction(index: Int, canSelect: Bool) -> TotalMilestoneAction10868? {
        guard isPresented, profile.milestones.indices.contains(index),
              !Self.isBlank(profile.milestones[index].id) else { return nil }
        return profile.stripAction(index: index, canSelect: canSelect)
    }

    /// The profile's Details action, for a resolved nonblank selection only.
    func detailsAction(canOpenDetails: Bool) -> TotalMilestoneAction10868? {
        guard selection.milestone != nil else { return nil }
        return profile.detailsAction(canOpenDetails: canOpenDetails)
    }

    /// The invitation needs a displayed control that can act, not just a
    /// callback.
    func showsInvitation(canSelect: Bool, canOpenDetails: Bool) -> Bool {
        guard isPresented, invitation != nil else { return false }
        return originals.contains { originalAction(index: $0.index, canSelect: canSelect) != nil }
            || detailsAction(canOpenDetails: canOpenDetails) != nil
    }

    func timingPresentation(hasBinding: Bool) -> TotalMilestoneTimingPresentation10868? {
        guard selection.milestone != nil else { return nil }
        return profile.timingPresentation(hasBinding: hasBinding)
    }

    // MARK: VoiceOver

    static func figure(_ line: TotalMilestoneOpeningLine10868) -> String {
        line.unit.map { "\(line.text) \($0)" } ?? line.text
    }

    var accessibilityHeader: String { profile.accessibilityHeader }

    /// The selected original's pregame chance with its own clock and source.
    var accessibilitySelectedValue: String? {
        switch selectedReading {
        case .value(let observation)?:
            "\(TotalMilestoneInput10868.pregameTitle): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text)?:
            "\(TotalMilestoneInput10868.pregameTitle): \(text)"
        case nil:
            nil
        }
    }

    /// The count with its own clock, then the difference when it shows.
    var accessibilityActualValue: String? {
        guard let presentation = actualPresentation else { return nil }
        var parts = [profile.accessibilityActual(presentation)]
        if let difference = visibleDifference { parts.append(difference.spoken) }
        return parts.joined(separator: "; ")
    }

    /// The line, its detail, its own time words and its note.
    var accessibilityLineValue: String? {
        if let line {
            var parts = ["\(Self.figure(line)), \(line.accessibilityDetail)", line.time.text]
            if let note = line.note { parts.append(note) }
            return parts.joined(separator: "; ")
        }
        return lineUnavailable
    }

    var accessibilityPlotLabel: String {
        var parts = [profile.quantityAxisTitle ?? profile.title]
        if visibleLineQuantity != nil { parts.append(Self.spokenLine) }
        if visibleActualQuantity != nil { parts.append(TotalMilestoneInput10868.spokenRule) }
        if visibleLineQuantity != nil && visibleActualQuantity != nil { parts.append(Self.spokenDistance) }
        return parts.joined(separator: " ")
    }

    var accessibilityPlotValue: String {
        var parts: [String] = []
        if visibleLineQuantity != nil, let line { parts.append("\(line.title): \(Self.figure(line))") }
        if visibleActualQuantity != nil, case .count(let count)? = profile.actual {
            let figure = count.unit.map { "\(count.text) \($0)" } ?? count.text
            parts.append("\(TotalMilestoneInput10868.finalCountTitle): \(figure)")
        }
        if let difference = visibleDifference { parts.append(difference.spoken) }
        return parts.joined(separator: "; ")
    }
}

nonisolated enum TotalMilestoneLineGeometry10868 {
    /// Each tick label centred on its quantity and kept inside the axis.
    static func tickFrames(values: [Double], sizes: [CGSize], domain: TotalMilestoneDomain10868,
                           width: CGFloat, inset: CGFloat) -> [CGRect] {
        guard values.count == sizes.count else { return [] }
        let width = width.isFinite ? max(0, width) : 0
        return zip(values, sizes).map { value, size in
            let length = size.width.isFinite ? max(0, size.width) : 0
            let height = size.height.isFinite ? max(0, size.height) : 0
            let center = TotalMilestoneGeometry10868.x(value, domain: domain, width: width, inset: inset) ?? width / 2
            let origin = min(max(0, center - length / 2), max(0, width - length))
            return CGRect(x: origin, y: 0, width: length, height: height)
        }
    }

    /// Every label whole inside the axis and at least `gap` from its neighbour.
    static func ticksFit(_ frames: [CGRect], width: CGFloat, gap: CGFloat) -> Bool {
        guard frames.allSatisfy({ $0.minX >= 0 && $0.maxX <= width + 0.001 }) else { return false }
        let ordered = frames.sorted { $0.minX < $1.minX }
        for (a, b) in zip(ordered, ordered.dropFirst()) where a.maxX + gap > b.minX + 0.001 {
            return false
        }
        return true
    }

    /// The narrowest axis on which these labels fit; infinity when none does.
    static func minimumTickWidth(values: [Double], widths: [CGFloat], domain: TotalMilestoneDomain10868,
                                 inset: CGFloat, gap: CGFloat) -> CGFloat {
        guard values.count == widths.count else { return .infinity }
        guard !values.isEmpty else { return 0 }
        let sizes = widths.map { CGSize(width: $0, height: 0) }
        func fits(_ width: CGFloat) -> Bool {
            ticksFit(tickFrames(values: values, sizes: sizes, domain: domain, width: width, inset: inset), width: width, gap: gap)
        }
        var high = max(1, 2 * inset + (widths.map { $0.isFinite ? max(0, $0) : 0 }.max() ?? 0))
        while !fits(high) {
            high *= 2
            if high > 100_000 { return .infinity }
        }
        var low: CGFloat = 0
        for _ in 0..<40 {
            let middle = (low + high) / 2
            if fits(middle) { high = middle } else { low = middle }
        }
        return high
    }

    /// Strides from every tick to just the first and last, in order.
    static func tickStrides(count: Int) -> [Int] {
        count <= 1 ? (count == 1 ? [1] : []) : Array(1...(count - 1))
    }

    /// The owner's tick indices kept at this stride, always starting with the first.
    static func tickSubset(count: Int, stride step: Int) -> [Int] {
        guard count > 0, step > 0 else { return [] }
        return Array(Swift.stride(from: 0, to: count, by: step))
    }

    /// The first stride whose labels fit this width; nil shows no ticks, and
    /// the direct labels still carry the exact quantities.
    static func fittedTickStride(values: [Double], widths: [CGFloat], domain: TotalMilestoneDomain10868,
                                 width: CGFloat, inset: CGFloat, gap: CGFloat) -> Int? {
        guard values.count == widths.count else { return nil }
        return tickStrides(count: values.count).first { step in
            let kept = tickSubset(count: values.count, stride: step)
            return minimumTickWidth(values: kept.map { values[$0] }, widths: kept.map { widths[$0] },
                                    domain: domain, inset: inset, gap: gap) <= width
        }
    }
}

/// One row of quantity tick labels on the axis's x scale. Its ideal width is
/// the narrowest axis on which every label fits whole, so `ViewThatFits`
/// can step down to fewer ticks instead of shrinking or overlapping them.
struct TotalMilestoneLineTickLayout10868: Layout {
    let domain: TotalMilestoneDomain10868
    let values: [Double]
    var inset: CGFloat = TotalMilestoneGeometry10868.plotInset
    var gap: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let height = sizes.map(\.height).max() ?? 0
        guard let width = proposal.width, width.isFinite else {
            return CGSize(width: TotalMilestoneLineGeometry10868.minimumTickWidth(
                values: values, widths: sizes.map(\.width), domain: domain, inset: inset, gap: gap), height: height)
        }
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let frames = TotalMilestoneLineGeometry10868.tickFrames(values: values, sizes: sizes, domain: domain,
                                                                width: bounds.width, inset: inset)
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum TotalMilestoneLineAccessibilityID10868 {
    static func option(_ id: String) -> String { "totalMilestoneLine10868.option.\(id)" }
    static func details(_ id: String) -> String { "totalMilestoneLine10868.details.\(id)" }
    static func selected(_ id: String) -> String { "totalMilestoneLine10868.selected.\(id)" }
    static let actual = "totalMilestoneLine10868.actual"
    static let line = "totalMilestoneLine10868.line"
    static let plot = "totalMilestoneLine10868.plot"
    static let originals = "totalMilestoneLine10868.originals"
}

struct TotalMilestoneLineComparison10868: View {
    let input: TotalMilestoneLineComparisonInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 30
    @ScaledMetric(relativeTo: .largeTitle) private var countSize: CGFloat = 44
    @ScaledMetric(relativeTo: .title2) private var differenceSize: CGFloat = 24
    @ScaledMetric(relativeTo: .footnote) private var axisHeight: CGFloat = 36
    @ScaledMetric(relativeTo: .footnote) private var circleSize: CGFloat = 10
    @ScaledMetric(relativeTo: .subheadline) private var optionMinimumWidth: CGFloat = 96

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var lineTint: Color { DS.blue }

    var body: some View {
        if input.isPresented {
            VStack(alignment: .leading, spacing: 14) {
                header
                headline
                if input.showsPlot {
                    plotSection
                }
                lineBlock
                originalsSection
                timing
                detailsButton
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Header and headline

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = input.profile.eyebrow {
                Text(eyebrow).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            Text(input.profile.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
    }

    /// The selected original's chance and the count with its difference: side
    /// by side when both fit whole, otherwise and at accessibility sizes stacked.
    @ViewBuilder private var headline: some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 14) { headlineParts(spaced: false) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) { headlineParts(spaced: true) }
                VStack(alignment: .leading, spacing: 14) { headlineParts(spaced: false) }
            }
        }
    }

    @ViewBuilder private func headlineParts(spaced: Bool) -> some View {
        selectedBlock
        if spaced { Spacer(minLength: 0) }
        if let presentation = input.actualPresentation {
            actualBlock(presentation)
        }
    }

    /// The selected original by its own owner title, with its pregame chance
    /// at a prominent size and its own clock.
    @ViewBuilder private var selectedBlock: some View {
        if let milestone = input.selection.milestone, let reading = input.selectedReading {
            VStack(alignment: .leading, spacing: 4) {
                Text(TotalMilestoneInput10868.pregameTitle).font(.caption).foregroundStyle(DS.textSecondary)
                Text(milestone.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                switch reading {
                case .value(let observation):
                    Text(observation.text)
                        .font(.system(size: chanceSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if let time = observation.timeText {
                        Text(time).font(.footnote).foregroundStyle(DS.textSecondary)
                    }
                case .missing(let text):
                    Text(text)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(milestone.title)
            .accessibilityValue(input.accessibilitySelectedValue ?? "")
            .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.selected(milestone.id))
        } else if let notice = input.selectionNotice {
            Text(notice)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The count, large, with its unit and own clock, then the owner's
    /// difference only while both quantities are drawn.
    private func actualBlock(_ presentation: TotalMilestoneActualPresentation10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(presentation.title).font(.caption).foregroundStyle(DS.textSecondary)
            switch presentation.actual {
            case .count(let count):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(count.text)
                        .font(.system(size: countSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if let unit = count.unit {
                        Text(unit).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                }
                if let clock = count.clock {
                    Text(clock).font(.footnote).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
            case .unavailable(let text):
                Text(text)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let difference = input.visibleDifference {
                VStack(alignment: .leading, spacing: 2) {
                    Text(difference.figure)
                        .font(.system(size: differenceSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(lineTint)
                        .fixedSize()
                    Text(difference.caption)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(presentation.title)
        .accessibilityValue(input.accessibilityActualValue ?? "")
        .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.actual)
    }

    // MARK: Axis

    /// Direct labels in lanes above the axis, the axis, then as many quantity
    /// ticks as fit whole. One VoiceOver element.
    private var plotSection: some View {
        let labels = input.markLabels
        return VStack(alignment: .leading, spacing: 4) {
            TotalMilestoneChartLayout10868(
                domain: input.domain,
                chanceFractions: [],
                annotationValues: labels.map(\.quantity),
                tickValues: [],
                plotHeight: axisHeight
            ) {
                plot
                ForEach(Array(labels.enumerated()), id: \.offset) { _, label in
                    markLabel(label)
                }
            }
            if let domain = input.domain, !input.placedQuantityTicks.isEmpty {
                tickRow(domain)
            }
            if let axisTitle = input.profile.quantityAxisTitle {
                Text(axisTitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityPlotLabel)
        .accessibilityValue(input.accessibilityPlotValue)
        .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.plot)
    }

    @ViewBuilder private func markLabel(_ label: TotalMilestoneLineMarkLabel10868) -> some View {
        switch label.kind {
        case .openingLine:
            HStack(spacing: 3) {
                Image(systemName: "circle").font(.caption2.weight(.bold))
                Text(label.text).font(.caption.weight(.semibold))
            }
            .foregroundStyle(lineTint)
        case .actual:
            HStack(spacing: 3) {
                Rectangle().frame(width: 2.5, height: 11)
                Text(label.text).font(.caption.weight(.bold))
            }
            .foregroundStyle(DS.textPrimary)
        }
    }

    /// Every owner tick when they fit whole, otherwise every second, third…
    /// down to the first and last, otherwise none.
    private func tickRow(_ domain: TotalMilestoneDomain10868) -> some View {
        let ticks = input.placedQuantityTicks
        return ViewThatFits(in: .horizontal) {
            ForEach(TotalMilestoneLineGeometry10868.tickStrides(count: ticks.count), id: \.self) { step in
                let kept = TotalMilestoneLineGeometry10868.tickSubset(count: ticks.count, stride: step).map { ticks[$0] }
                TotalMilestoneLineTickLayout10868(domain: domain, values: kept.map(\.value)) {
                    ForEach(Array(kept.enumerated()), id: \.offset) { _, tick in
                        Text(tick.text).font(.caption).monospacedDigit().foregroundStyle(DS.textSecondary).fixedSize()
                    }
                }
            }
            Color.clear.frame(width: 0, height: 0)
        }
    }

    /// The track, the distance band, the count's solid rule and the line's
    /// hollow point — drawn last so a coincident point stays visible on the rule.
    private var plot: some View {
        let input = self.input
        let lineTint = self.lineTint
        let border = DS.border
        let card = DS.cardBg
        let primary = DS.textPrimary
        return Canvas { context, size in
            guard let model = input.plotModel(size: size, inset: TotalMilestoneGeometry10868.plotInset) else { return }
            let axis = Path { $0.move(to: CGPoint(x: 0, y: model.axisY)); $0.addLine(to: CGPoint(x: size.width, y: model.axisY)) }
            context.stroke(axis, with: .color(border), lineWidth: 2)
            if let span = model.distance {
                let band = Path {
                    $0.move(to: CGPoint(x: span.lower, y: model.axisY))
                    $0.addLine(to: CGPoint(x: span.upper, y: model.axisY))
                }
                context.stroke(band, with: .color(lineTint.opacity(0.3)), lineWidth: 4)
            }
            if let x = model.actualX {
                let rule = Path { $0.move(to: CGPoint(x: x, y: model.ruleTop)); $0.addLine(to: CGPoint(x: x, y: model.ruleBottom)) }
                context.stroke(rule, with: .color(primary), lineWidth: 3)
            }
            if let x = model.lineX {
                let point = Path(ellipseIn: CGRect(x: x - 6, y: model.axisY - 6, width: 12, height: 12))
                context.fill(point, with: .color(card))
                context.stroke(point, with: .color(lineTint), lineWidth: 2)
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Opening line

    /// The line's own figure, time words and note, with the key for both
    /// marks when they are drawn. Present whether or not the axis is.
    @ViewBuilder private var lineBlock: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let line = input.line {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if input.visibleLineQuantity != nil {
                        Circle().fill(DS.cardBg)
                            .overlay(Circle().strokeBorder(lineTint, lineWidth: 2))
                            .frame(width: circleSize, height: circleSize)
                    }
                    Text(line.title).font(.caption).foregroundStyle(DS.textSecondary)
                    Text(TotalMilestoneLineComparisonInput10868.figure(line))
                        .font(.subheadline.weight(.semibold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                }
                Text(line.time.text).font(.caption).foregroundStyle(DS.textSecondary)
                if let note = line.note {
                    Text(note).font(.caption).foregroundStyle(DS.textSecondary)
                }
            } else if let text = input.lineUnavailable {
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
            if input.visibleActualQuantity != nil {
                HStack(spacing: 6) {
                    Rectangle().fill(DS.textPrimary).frame(width: 3, height: circleSize + 4)
                    Text(TotalMilestoneInput10868.finalCountTitle).font(.caption).foregroundStyle(DS.textSecondary)
                }
                .accessibilityHidden(true)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.line?.title ?? "")
        .accessibilityValue(input.accessibilityLineValue ?? "")
        .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.line)
    }

    // MARK: Originals

    /// Every original contract in owner order, each with its own pregame
    /// chance and result, wrapping by measured width and one column at
    /// accessibility sizes.
    private var originalsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(input.originalsTitle)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if input.showsInvitation(canSelect: canSelect, canOpenDetails: canOpenDetails), let invitation = input.invitation {
                Text(invitation)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            TotalMilestoneStripLayout10868(
                minimumCellWidth: optionMinimumWidth,
                maximumColumns: typeSize.isAccessibilitySize ? 1 : nil
            ) {
                ForEach(input.originals, id: \.index) { entry in
                    originalControl(entry)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.originals)
        }
    }

    /// A button only when it carries an action; otherwise the same content as
    /// one plain element.
    @ViewBuilder private func originalControl(_ entry: TotalMilestoneStripEntry10868) -> some View {
        let id = entry.milestone.id
        if let action = input.originalAction(index: entry.index, canSelect: canSelect) {
            Button {
                perform(action)
            } label: {
                originalCell(entry)
            }
            .accessibilityLabel(entry.milestone.title)
            .accessibilityValue(input.profile.accessibilityStripValue(entry))
            .accessibilityAddTraits(entry.selected ? .isSelected : [])
            .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.option(id))
        } else {
            originalCell(entry)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(entry.milestone.title)
                .accessibilityValue(input.profile.accessibilityStripValue(entry))
                .accessibilityAddTraits(entry.selected ? .isSelected : [])
                .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.option(id))
        }
    }

    /// The original's own threshold title, its pregame chance and its result.
    /// Selection is a diamond and a heavier outline; the result is a check or
    /// cross with words — never colour alone, and never the same sign.
    private func originalCell(_ entry: TotalMilestoneStripEntry10868) -> some View {
        let shape = RoundedRectangle(cornerRadius: 10)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if entry.selected {
                    Image(systemName: "diamond.fill")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityHidden(true)
                }
                Text(entry.milestone.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 1) {
                switch entry.pregame {
                case .value(let observation):
                    Text(observation.text)
                        .font(.title3.bold())
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: true, vertical: false)
                case .missing(let text):
                    Text(text)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(TotalMilestoneInput10868.pregameTitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if case .result(let result)? = entry.second {
                VStack(alignment: .leading, spacing: 1) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        switch result.mark {
                        case .check?:
                            Image(systemName: "checkmark.circle").accessibilityHidden(true)
                        case .cross?:
                            Image(systemName: "xmark.circle").accessibilityHidden(true)
                        case nil:
                            EmptyView()
                        }
                        Text(result.text).fixedSize(horizontal: false, vertical: true)
                    }
                    .font(result.isAdmitted ? .subheadline.weight(.semibold) : .footnote.weight(.semibold))
                    .foregroundStyle(result.isAdmitted ? DS.textPrimary : DS.textSecondary)
                    Text(TotalMilestoneInput10868.resultTitle)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity, alignment: .topLeading)
        .background(entry.selected ? DS.cardBg : DS.surface, in: shape)
        .overlay(shape.strokeBorder(entry.selected ? DS.textPrimary : DS.border, lineWidth: entry.selected ? 2 : 1))
        .contentShape(shape)
    }

    // MARK: Timing and Details

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

    private func timingLines(_ content: TotalMilestoneTiming10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(content.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The exact selected original's Details, named by its own title.
    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let milestone = input.selection.milestone {
            Button {
                perform(action)
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(TotalMilestoneInput10868.detailsTitle)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(milestone.title)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityLabel("\(TotalMilestoneInput10868.detailsTitle), \(milestone.title)")
            .accessibilityIdentifier(TotalMilestoneLineAccessibilityID10868.details(milestone.id))
        }
    }

    private func perform(_ action: TotalMilestoneAction10868?) {
        action?.perform(onSelect: onSelect, onDetails: onDetails)
    }
}

// MARK: - Games so far beside each original's literal threshold (during play only)

// #10868 — during play, the count so far as a solid rule on a quantity-only
// axis, beside each original contract's own literal market threshold as a
// hollow mark, and under them one panel per original with its own pre-match
// chance, its current chance or the owner's words for its absence, and its
// own market result. A threshold is a market boundary ("Under 22.5 games"),
// never a chance, a minimum count, an average or a projected final. Marks are
// quantities; the panels' bars are chances on one fixed 0–100% scale.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `LiveTennis` kind `totals`,
// `liveTennis.css` `.lt-totals`/`.lt-total-chart`/`.lt-total-pair`/`.lt-chance`).
//
// It reuses the profile's own readings, count, exact-id selection, actions,
// timing and spoken count, the quantity geometry, label lanes, chart and tick
// layouts, and the strip's column and frame geometry. It never calls the final-only result helper; each
// panel shows its row's own owner-admitted result directly, under its own
// label, whatever the count, the threshold or the current chance. The
// profile's milestone coordinates are never read as thresholds: a threshold
// arrives only through its own association to one exact original. Before play
// and after the final it shows nothing and offers nothing, and the lifecycle
// profile above is unchanged. That suppression is not a pregame or final
// composition.
//
// Every figure, label, clock, missing word, subtotal and result arrives
// resolved by the owner and is shown verbatim. This layer never parses a
// title, rounds or converts a threshold, sums or compares subtotals, measures
// a distance to a threshold, infers a result or a winner, complements or
// normalises a chance, elects a baseline, decides currentness or reads a later
// quote. A missing chance is the owner's words, never 0%; an unplaceable
// chance keeps its figure and draws no bar; a real 0% keeps its figure and bar.
//
// Host binding still owed — not available at this base. An owner must supply:
//   • the profile input (true `.during` phase, copy, originals in owner order
//     with exact ids and titles, cutoff-admitted pre-match observations,
//     currentness-admitted current readings or their words, own results, the
//     held id, the clocked count so far, any domain, ticks and timing),
//   • one literal threshold per original it places: exact original id, raw
//     coordinate, formatted label and mark identity,
//   • any named subtotals of the count, already formatted,
//   • whether the count, the thresholds and the domain share one unit,
//   • the channel titles, key, note, originals title, invitation and the words
//     for an original that cannot be identified;
// and keeps selection, timing disclosure, Details, Back and focus.

/// A threshold mark's hollow shape, so two nearby thresholds differ by more
/// than colour.
nonisolated enum TotalMilestoneThresholdShape10868: Equatable {
    case circle
    case diamond
}

nonisolated enum TotalMilestoneThresholdTone10868: Equatable {
    case primary
    case secondary
}

/// The owner's visual identity for one threshold's mark.
nonisolated struct TotalMilestoneThresholdMark10868: Equatable {
    let shape: TotalMilestoneThresholdShape10868
    let tone: TotalMilestoneThresholdTone10868
}

/// The owner's literal market boundary for one exact original — a quantity on
/// the count axis, never a chance, a minimum count, an average or a projection.
nonisolated struct TotalMilestoneThreshold10868: Equatable {
    /// The exact original it belongs to; matched by exact id only.
    let originalID: String
    /// Raw literal coordinate (22.5 for "Under 22.5 games"). A negative or
    /// non-finite value draws nothing but keeps the original.
    let quantity: Double
    /// The mark's direct label ("22.5").
    let label: String
    let mark: TotalMilestoneThresholdMark10868
}

/// One owner subtotal of the count ("8" for "Fils"). Shown as given; never
/// summed, compared or checked against the count.
nonisolated struct TotalMilestoneSubtotal10868: Equatable {
    let text: String
    let name: String
}

/// The owner's words for this composition.
nonisolated struct TotalMilestoneThresholdWords10868: Equatable {
    /// "Pre-match chance".
    let beforeTitle: String
    /// "Current chance".
    let currentTitle: String
    /// The key beside the hollow marks ("Original market thresholds").
    let thresholdKey: String
    /// "Original Under contracts".
    let originalsTitle: String
    /// One short line ("Circles mark total-game thresholds, not projected
    /// final scores. The match is unfinished."); nil shows none.
    let note: String?
    /// Shown only when a displayed control can act.
    let invitation: String?
    /// For an original whose id is blank or repeated ("Original contract unavailable").
    let unresolved: String
    /// Names the subtotals ("Games won"); nil shows no title.
    let subtotalsTitle: String?
}

/// A threshold placed on the shared axis for one original.
nonisolated struct TotalMilestoneThresholdPlacement10868: Equatable {
    /// The original's owner index.
    let index: Int
    let threshold: TotalMilestoneThreshold10868
    let quantity: Double
    let selected: Bool
}

nonisolated enum TotalMilestoneThresholdLabelKind10868: Equatable {
    case threshold(TotalMilestoneThresholdMark10868)
    case actual
}

/// A direct label above the axis, centred on its quantity.
nonisolated struct TotalMilestoneThresholdLabel10868: Equatable {
    let kind: TotalMilestoneThresholdLabelKind10868
    let quantity: Double
    let text: String
}

nonisolated struct TotalMilestoneThresholdPlotMark10868: Equatable {
    /// The original's owner index.
    let index: Int
    let x: CGFloat
    let mark: TotalMilestoneThresholdMark10868
    let selected: Bool
}

/// Everything the axis draws, in its own coordinates.
nonisolated struct TotalMilestoneThresholdPlotModel10868: Equatable {
    let axisY: CGFloat
    let actualX: CGFloat?
    let ruleTop: CGFloat
    let ruleBottom: CGFloat
    let marks: [TotalMilestoneThresholdPlotMark10868]
}

/// One titled probability or status channel in an original's panel.
nonisolated enum TotalMilestoneThresholdChannel10868: Equatable {
    /// A figure with its own clock; it draws a bar only when its chance is
    /// placeable on 0...1.
    case chance(title: String, observation: TotalMilestoneObservation10868)
    /// The owner's words for an absent or withheld reading — never 0%.
    case status(title: String, text: String)
}

/// One original in owner order, with what its panel shows.
nonisolated struct TotalMilestoneThresholdPanel10868: Equatable {
    let index: Int
    let milestone: TotalMilestoneRow10868
    /// False for a blank or repeated id: the title and the owner's unresolved
    /// words only — no chance, result, mark or action.
    let isResolved: Bool
    /// The one association claiming this original, drawn or not.
    let threshold: TotalMilestoneThreshold10868?
    /// The mark key, only when this original's threshold is drawn.
    let mark: TotalMilestoneThresholdMark10868?
    /// Pre-match, then current; empty when unresolved.
    let channels: [TotalMilestoneThresholdChannel10868]
    /// Beside a recorded current chance only.
    let movement: String?
    /// The row's own owner-admitted result; nil when unresolved.
    let result: TotalMilestoneResult10868?
    let selected: Bool
}

nonisolated struct TotalMilestoneThresholdLiveInput10868: Equatable {
    /// The existing profile: phase, copy, originals, held selection, count so
    /// far, domain, ticks and timing. Its milestone coordinates and projection
    /// are never read here.
    let profile: TotalMilestoneInput10868
    /// Literal thresholds, each tied to one exact original.
    let thresholds: [TotalMilestoneThreshold10868]
    let subtotals: [TotalMilestoneSubtotal10868]
    /// The owner's admission that the count, the thresholds and the domain
    /// share one unit on one axis. Without it there is no shared axis.
    let quantitiesShareUnit: Bool
    let words: TotalMilestoneThresholdWords10868

    static let resultTitle = "Original market result"
    static let spokenThresholds = "Hollow marks are the original market thresholds: quantities on the count scale, not chances and not projected final scores."
    static let spokenThresholdTitle = "Market threshold"

    /// During play only.
    var isPresented: Bool { profile.phase == .during }

    // MARK: Identity

    /// A nonblank id carried by exactly one original. Whole-row equality never
    /// decides membership, so a NaN reading cannot close a real original.
    func isResolvedOriginal(index: Int) -> Bool {
        guard profile.milestones.indices.contains(index) else { return false }
        let id = profile.milestones[index].id
        guard !TotalMilestoneLineComparisonInput10868.isBlank(id) else { return false }
        return profile.milestones.filter { $0.id == id }.count == 1
    }

    /// The one association claiming a resolved original by exact id. None when
    /// no association or more than one claims it; a neighbour's never stands in.
    func threshold(forOriginalAt index: Int) -> TotalMilestoneThreshold10868? {
        guard isPresented, isResolvedOriginal(index: index) else { return nil }
        let id = profile.milestones[index].id
        let claims = thresholds.filter { $0.originalID == id }
        return claims.count == 1 ? claims[0] : nil
    }

    // MARK: Selection

    /// The profile's exact-id selection, during play, with a blank held id
    /// refused. Never a neighbour or the first original.
    var selection: TotalMilestoneSelection10868 {
        guard isPresented, let id = profile.selectedMilestoneID else { return .none }
        if TotalMilestoneLineComparisonInput10868.isBlank(id) { return .missing(id) }
        return profile.selection
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: TotalMilestoneInput10868.milestoneUnavailable
        case .none, .selected: nil
        }
    }

    // MARK: Count and subtotals

    /// "Count so far" and the owner's count or words.
    var actualPresentation: TotalMilestoneActualPresentation10868? {
        isPresented ? profile.actualPresentation : nil
    }

    var visibleSubtotals: [TotalMilestoneSubtotal10868] {
        isPresented ? subtotals : []
    }

    var visibleActualQuantity: Double? {
        guard isPresented, quantitiesShareUnit else { return nil }
        return profile.visibleActualQuantity
    }

    // MARK: Axis

    /// Every drawable threshold whose association is exact, in owner order.
    var placements: [TotalMilestoneThresholdPlacement10868] {
        guard isPresented, quantitiesShareUnit else { return [] }
        let selectedIndex = selection.index
        return profile.milestones.indices.compactMap { index in
            guard let threshold = self.threshold(forOriginalAt: index),
                  let quantity = TotalMilestoneGeometry10868.quantity(threshold.quantity) else { return nil }
            return TotalMilestoneThresholdPlacement10868(index: index, threshold: threshold, quantity: quantity,
                                                         selected: index == selectedIndex)
        }
    }

    /// The placed thresholds, the drawn count and any well-formed owner range.
    /// Never the selection, the profile's milestone coordinates or a projection.
    var domain: TotalMilestoneDomain10868? {
        guard isPresented, quantitiesShareUnit else { return nil }
        var values = placements.map(\.quantity)
        if let actual = visibleActualQuantity { values.append(actual) }
        return TotalMilestoneGeometry10868.domain(values: values, owner: profile.quantityDomain)
    }

    var showsPlot: Bool {
        domain != nil && (!placements.isEmpty || visibleActualQuantity != nil)
    }

    /// The owner's quantity ticks inside the domain, in order. The view shows
    /// as many as measured width allows.
    var placedQuantityTicks: [TotalMilestoneTick10868] {
        guard showsPlot, let domain else { return [] }
        return profile.quantityTicks.filter { tick in
            TotalMilestoneGeometry10868.quantity(tick.value).map { $0 >= domain.lower && $0 <= domain.upper } ?? false
        }
    }

    /// Direct labels: each placed threshold's, in owner order, then the count
    /// rule's when labelled. Lanes keep nearby labels whole and apart.
    var labels: [TotalMilestoneThresholdLabel10868] {
        guard showsPlot else { return [] }
        var result = placements.map {
            TotalMilestoneThresholdLabel10868(kind: .threshold($0.threshold.mark), quantity: $0.quantity, text: $0.threshold.label)
        }
        if let quantity = visibleActualQuantity, case .count(let count)? = profile.actual, let label = count.ruleLabel {
            result.append(TotalMilestoneThresholdLabel10868(kind: .actual, quantity: quantity, text: label))
        }
        return result
    }

    /// The axis for this size. Its scale depends only on `domain`.
    func plotModel(size: CGSize, inset: CGFloat) -> TotalMilestoneThresholdPlotModel10868? {
        guard showsPlot, let domain else { return nil }
        func x(_ quantity: Double) -> CGFloat? {
            TotalMilestoneGeometry10868.x(quantity, domain: domain, width: size.width, inset: inset)
        }
        let height = size.height.isFinite ? max(0, size.height) : 0
        let axisY = height / 2
        let reach = min(14, axisY)
        let marks = placements.compactMap { placement in
            x(placement.quantity).map {
                TotalMilestoneThresholdPlotMark10868(index: placement.index, x: $0, mark: placement.threshold.mark,
                                                     selected: placement.selected)
            }
        }
        return TotalMilestoneThresholdPlotModel10868(axisY: axisY, actualX: visibleActualQuantity.flatMap { x($0) },
                                                     ruleTop: axisY - reach, ruleBottom: axisY + reach, marks: marks)
    }

    var drawsThresholds: Bool { showsPlot && !placements.isEmpty }

    // MARK: Panels

    /// The pre-match channel, then the current one, each under its own title.
    func channels(_ milestone: TotalMilestoneRow10868) -> [TotalMilestoneThresholdChannel10868] {
        var result: [TotalMilestoneThresholdChannel10868]
        switch profile.beforeReading(milestone) {
        case .value(let observation): result = [.chance(title: words.beforeTitle, observation: observation)]
        case .missing(let text): result = [.status(title: words.beforeTitle, text: text)]
        }
        switch profile.currentReading(milestone) {
        case .chance(let observation)?: result.append(.chance(title: words.currentTitle, observation: observation))
        case .chanceStatus(let text)?: result.append(.status(title: words.currentTitle, text: text))
        case .actual(let text)?: result.append(.status(title: TotalMilestoneInput10868.actualSoFarTitle, text: text))
        case nil: break
        }
        return result
    }

    /// Every original in owner order — none filtered, ranked or capped.
    var panels: [TotalMilestoneThresholdPanel10868] {
        guard isPresented else { return [] }
        let selectedIndex = selection.index
        let placed = Set(placements.map(\.index))
        return profile.milestones.enumerated().map { index, milestone in
            let resolved = isResolvedOriginal(index: index)
            let threshold = self.threshold(forOriginalAt: index)
            return TotalMilestoneThresholdPanel10868(
                index: index,
                milestone: milestone,
                isResolved: resolved,
                threshold: threshold,
                mark: placed.contains(index) ? threshold?.mark : nil,
                channels: resolved ? channels(milestone) : [],
                movement: resolved ? profile.movement(milestone) : nil,
                result: resolved ? milestone.result : nil,
                selected: resolved && index == selectedIndex
            )
        }
    }

    /// A bar's filled length on the fixed 0...1 scale; nil for a chance the
    /// scale cannot place — never clamped, never drawn as zero.
    static func barWidth(_ probability: Double, track: CGFloat) -> CGFloat? {
        guard let fraction = TotalMilestoneGeometry10868.fraction(probability), track.isFinite, track > 0 else { return nil }
        return track * CGFloat(fraction)
    }

    /// Panel columns from the available width and the scaled minimum panel
    /// width alone — never from a panel's unwrapped words, so long status,
    /// condition or clock copy wraps inside the pair instead of stacking it —
    /// and one column at accessibility sizes.
    static func panelColumns(count: Int, width: CGFloat, spacing: CGFloat, minimumCellWidth: CGFloat,
                             accessibility: Bool) -> Int {
        TotalMilestoneGeometry10868.stripColumns(count: count, width: width, spacing: spacing,
                                                 minimumCellWidth: minimumCellWidth,
                                                 maximumColumns: accessibility ? 1 : nil) { _ in true }
    }

    // MARK: Actions

    /// The profile's own strip action, for a resolved original only.
    func panelAction(index: Int, canSelect: Bool) -> TotalMilestoneAction10868? {
        guard isPresented, isResolvedOriginal(index: index) else { return nil }
        return profile.stripAction(index: index, canSelect: canSelect)
    }

    /// The profile's Details action, for a resolved nonblank selection only.
    func detailsAction(canOpenDetails: Bool) -> TotalMilestoneAction10868? {
        guard selection.milestone != nil else { return nil }
        return profile.detailsAction(canOpenDetails: canOpenDetails)
    }

    /// The invitation needs a displayed control that can act, not just a callback.
    func showsInvitation(canSelect: Bool, canOpenDetails: Bool) -> Bool {
        guard isPresented, words.invitation != nil else { return false }
        return panels.contains { panelAction(index: $0.index, canSelect: canSelect) != nil }
            || detailsAction(canOpenDetails: canOpenDetails) != nil
    }

    func timingPresentation(hasBinding: Bool) -> TotalMilestoneTimingPresentation10868? {
        guard selection.milestone != nil else { return nil }
        return profile.timingPresentation(hasBinding: hasBinding)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String { profile.accessibilityHeader }

    var accessibilityActualValue: String? {
        actualPresentation.map { profile.accessibilityActual($0) }
    }

    var accessibilitySubtotals: String {
        let list = visibleSubtotals.map { "\($0.name) \($0.text)" }.joined(separator: ", ")
        return words.subtotalsTitle.map { "\($0): \(list)" } ?? list
    }

    var accessibilityPlotLabel: String {
        var parts = [profile.quantityAxisTitle ?? profile.title]
        if drawsThresholds { parts.append(Self.spokenThresholds) }
        if showsPlot && visibleActualQuantity != nil { parts.append(TotalMilestoneInput10868.spokenRule) }
        return parts.joined(separator: " ")
    }

    var accessibilityPlotValue: String {
        guard showsPlot else { return "" }
        var parts: [String] = []
        if visibleActualQuantity != nil, case .count(let count)? = profile.actual {
            let figure = count.unit.map { "\(count.text) \($0)" } ?? count.text
            parts.append("\(TotalMilestoneInput10868.countSoFarTitle): \(figure)")
        }
        for placement in placements {
            let title = profile.milestones[placement.index].title
            parts.append("\(title): \(Self.spokenThresholdTitle) \(placement.threshold.label)")
        }
        return parts.joined(separator: "; ")
    }

    /// One panel: its titled channels, movement, own result and threshold, or
    /// the owner's unresolved words alone.
    func accessibilityPanelValue(_ panel: TotalMilestoneThresholdPanel10868) -> String {
        guard panel.isResolved else { return words.unresolved }
        var parts = panel.channels.map { channel -> String in
            switch channel {
            case .chance(let title, let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
            case .status(let title, let text): "\(title): \(text)"
            }
        }
        if let movement = panel.movement { parts.append("\(TotalMilestoneInput10868.spokenMovement): \(movement)") }
        if let result = panel.result { parts.append("\(Self.resultTitle): \(result.text)") }
        if let threshold = panel.threshold { parts.append("\(Self.spokenThresholdTitle): \(threshold.label)") }
        return parts.joined(separator: "; ")
    }
}

/// Places the original panels: equal columns chosen by
/// `TotalMilestoneThresholdLiveInput10868.panelColumns`, then every panel
/// measured at that bounded cell width so its words wrap inside it. Each row is
/// as tall as its tallest panel. Nothing shrinks, truncates or hides.
struct TotalMilestoneThresholdPanelLayout10868: Layout {
    /// Scaled with the prominent figures, so enlarged text needs a wider cell.
    let minimumCellWidth: CGFloat
    /// One column at accessibility sizes.
    let accessibility: Bool
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? 320
        return plan(width: width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = plan(width: bounds.width, subviews: subviews).frames
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(width: CGFloat, subviews: Subviews) -> (frames: [CGRect], size: CGSize) {
        let columns = TotalMilestoneThresholdLiveInput10868.panelColumns(
            count: subviews.count, width: width, spacing: spacing, minimumCellWidth: minimumCellWidth,
            accessibility: accessibility)
        let cell = TotalMilestoneGeometry10868.stripCellWidth(columns: columns, width: width, spacing: spacing)
        let heights = subviews.map { $0.sizeThatFits(ProposedViewSize(width: cell, height: nil)).height }
        return TotalMilestoneGeometry10868.stripFrames(columns: columns, cellWidth: cell, heights: heights, spacing: spacing)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum TotalMilestoneThresholdLiveAccessibilityID10868 {
    static func option(_ id: String) -> String { "totalMilestoneThreshold10868.option.\(id)" }
    static func details(_ id: String) -> String { "totalMilestoneThreshold10868.details.\(id)" }
    static let actual = "totalMilestoneThreshold10868.actual"
    static let subtotals = "totalMilestoneThreshold10868.subtotals"
    static let plot = "totalMilestoneThreshold10868.plot"
    static let originals = "totalMilestoneThreshold10868.originals"
}

struct TotalMilestoneThresholdLive10868: View {
    let input: TotalMilestoneThresholdLiveInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 30
    @ScaledMetric(relativeTo: .title) private var countSize: CGFloat = 34
    @ScaledMetric(relativeTo: .footnote) private var axisHeight: CGFloat = 40
    @ScaledMetric(relativeTo: .footnote) private var glyphSize: CGFloat = 10
    @ScaledMetric(relativeTo: .footnote) private var barHeight: CGFloat = 6
    /// Tracks the prominent figures' own scale.
    @ScaledMetric(relativeTo: .title) private var panelMinimumWidth: CGFloat = 132

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        if input.isPresented {
            VStack(alignment: .leading, spacing: 14) {
                headerRow
                if !input.visibleSubtotals.isEmpty {
                    subtotalsRow
                }
                if let notice = input.selectionNotice {
                    Text(notice)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if input.showsPlot {
                    plotSection
                }
                if let note = input.words.note {
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                originalsSection
                timing
                detailsButton
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    private func tint(_ tone: TotalMilestoneThresholdTone10868) -> Color {
        switch tone {
        case .primary: DS.blue
        case .secondary: DS.purple
        }
    }

    // MARK: Header, count and subtotals

    @ViewBuilder private var headerRow: some View {
        if typeSize.isAccessibilitySize || input.actualPresentation == nil {
            VStack(alignment: .leading, spacing: 10) { headerParts(spaced: false) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 12) { headerParts(spaced: true) }
                VStack(alignment: .leading, spacing: 10) { headerParts(spaced: false) }
            }
        }
    }

    @ViewBuilder private func headerParts(spaced: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = input.profile.eyebrow {
                Text(eyebrow).font(.caption2).foregroundStyle(DS.textSecondary)
            }
            Text(input.profile.title).font(.title2.bold()).foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityHeader)
        .accessibilityAddTraits(.isHeader)
        if spaced { Spacer(minLength: 0) }
        if let presentation = input.actualPresentation {
            actualBlock(presentation)
        }
    }

    /// The count so far — prominent, labelled, with its own clock, and never on
    /// a probability scale.
    private func actualBlock(_ presentation: TotalMilestoneActualPresentation10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(presentation.title).font(.caption).foregroundStyle(DS.textSecondary)
            switch presentation.actual {
            case .count(let count):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(count.text)
                        .font(.system(size: countSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let unit = count.unit {
                        Text(unit).font(.subheadline).foregroundStyle(DS.textSecondary)
                    }
                }
                if let clock = count.clock {
                    Text(clock).font(.footnote).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
            case .unavailable(let text):
                Text(text)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(presentation.title)
        .accessibilityValue(input.accessibilityActualValue ?? "")
        .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.actual)
    }

    /// Each owner subtotal beside its own name, as given. A row when they fit,
    /// a column otherwise and at accessibility sizes.
    private var subtotalsRow: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let title = input.words.subtotalsTitle {
                Text(title).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) { subtotalItems }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 20) { subtotalItems }
                    VStack(alignment: .leading, spacing: 6) { subtotalItems }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilitySubtotals)
        .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.subtotals)
    }

    @ViewBuilder private var subtotalItems: some View {
        ForEach(Array(input.visibleSubtotals.enumerated()), id: \.offset) { _, subtotal in
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(subtotal.text).font(.title3.bold()).monospacedDigit().foregroundStyle(DS.textPrimary)
                Text(subtotal.name).font(.footnote).foregroundStyle(DS.textSecondary)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Axis

    /// Direct labels in measured lanes above the axis, the axis, as many
    /// quantity ticks as fit whole, the axis title and the key. One VoiceOver
    /// element.
    private var plotSection: some View {
        let labels = input.labels
        return VStack(alignment: .leading, spacing: 4) {
            TotalMilestoneChartLayout10868(
                domain: input.domain,
                chanceFractions: [],
                annotationValues: labels.map(\.quantity),
                tickValues: [],
                plotHeight: axisHeight
            ) {
                plot
                ForEach(Array(labels.enumerated()), id: \.offset) { _, label in
                    directLabel(label)
                }
            }
            if let domain = input.domain, !input.placedQuantityTicks.isEmpty {
                tickRow(domain)
            }
            if let axisTitle = input.profile.quantityAxisTitle {
                Text(axisTitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            plotKey
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityPlotLabel)
        .accessibilityValue(input.accessibilityPlotValue)
        .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.plot)
    }

    @ViewBuilder private func directLabel(_ label: TotalMilestoneThresholdLabel10868) -> some View {
        switch label.kind {
        case .threshold(let mark):
            HStack(spacing: 3) {
                markGlyph(mark)
                Text(label.text).font(.caption.weight(.semibold)).monospacedDigit()
            }
            .foregroundStyle(DS.textPrimary)
        case .actual:
            HStack(spacing: 3) {
                Rectangle().frame(width: 2.5, height: 11)
                Text(label.text).font(.caption.weight(.bold))
            }
            .foregroundStyle(DS.textPrimary)
        }
    }

    @ViewBuilder private func markGlyph(_ mark: TotalMilestoneThresholdMark10868) -> some View {
        let color = tint(mark.tone)
        switch mark.shape {
        case .circle:
            Circle().fill(DS.cardBg)
                .overlay(Circle().strokeBorder(color, lineWidth: 2))
                .frame(width: glyphSize, height: glyphSize)
        case .diamond:
            Rectangle().fill(DS.cardBg)
                .overlay(Rectangle().strokeBorder(color, lineWidth: 2))
                .frame(width: glyphSize * 0.72, height: glyphSize * 0.72)
                .rotationEffect(.degrees(45))
                .frame(width: glyphSize, height: glyphSize)
        }
    }

    /// Every owner tick when they fit whole, otherwise every second, third…
    /// down to the first and last, otherwise none.
    private func tickRow(_ domain: TotalMilestoneDomain10868) -> some View {
        let ticks = input.placedQuantityTicks
        return ViewThatFits(in: .horizontal) {
            ForEach(TotalMilestoneLineGeometry10868.tickStrides(count: ticks.count), id: \.self) { step in
                let kept = TotalMilestoneLineGeometry10868.tickSubset(count: ticks.count, stride: step).map { ticks[$0] }
                TotalMilestoneLineTickLayout10868(domain: domain, values: kept.map(\.value)) {
                    ForEach(Array(kept.enumerated()), id: \.offset) { _, tick in
                        Text(tick.text).font(.caption).monospacedDigit().foregroundStyle(DS.textSecondary).fixedSize()
                    }
                }
            }
            Color.clear.frame(width: 0, height: 0)
        }
    }

    /// Only the drawn series: the hollow thresholds and the count's rule.
    @ViewBuilder private var plotKey: some View {
        let thresholds = input.drawsThresholds
        let rule = input.visibleActualQuantity != nil
        if thresholds || rule {
            Group {
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) { plotKeyItems(thresholds: thresholds, rule: rule) }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 12) { plotKeyItems(thresholds: thresholds, rule: rule) }
                        VStack(alignment: .leading, spacing: 4) { plotKeyItems(thresholds: thresholds, rule: rule) }
                    }
                }
            }
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
        }
    }

    @ViewBuilder private func plotKeyItems(thresholds: Bool, rule: Bool) -> some View {
        if thresholds {
            HStack(spacing: 5) {
                Circle().strokeBorder(DS.textSecondary, lineWidth: 2).frame(width: glyphSize, height: glyphSize)
                Text(input.words.thresholdKey).fixedSize(horizontal: false, vertical: true)
            }
        }
        if rule {
            HStack(spacing: 5) {
                Rectangle().fill(DS.textPrimary).frame(width: 3, height: glyphSize + 4)
                Text(TotalMilestoneInput10868.countSoFarTitle).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The track, the count's solid rule and each threshold's hollow mark —
    /// marks last so a coincident threshold stays visible on the rule.
    private var plot: some View {
        let input = self.input
        let border = DS.border
        let card = DS.cardBg
        let primary = DS.textPrimary
        let primaryTint = DS.blue
        let secondaryTint = DS.purple
        return Canvas { context, size in
            guard let model = input.plotModel(size: size, inset: TotalMilestoneGeometry10868.plotInset) else { return }
            let axis = Path { $0.move(to: CGPoint(x: 0, y: model.axisY)); $0.addLine(to: CGPoint(x: size.width, y: model.axisY)) }
            context.stroke(axis, with: .color(border), lineWidth: 2)
            if let x = model.actualX {
                let rule = Path { $0.move(to: CGPoint(x: x, y: model.ruleTop)); $0.addLine(to: CGPoint(x: x, y: model.ruleBottom)) }
                context.stroke(rule, with: .color(primary), lineWidth: 3)
            }
            for mark in model.marks.sorted(by: { !$0.selected && $1.selected }) {
                let center = CGPoint(x: mark.x, y: model.axisY)
                let r: CGFloat = mark.selected ? 7.5 : 6
                let shape: Path
                switch mark.mark.shape {
                case .circle:
                    shape = Path(ellipseIn: CGRect(x: center.x - r, y: center.y - r, width: 2 * r, height: 2 * r))
                case .diamond:
                    shape = Path { path in
                        path.move(to: CGPoint(x: center.x, y: center.y - r))
                        path.addLine(to: CGPoint(x: center.x + r, y: center.y))
                        path.addLine(to: CGPoint(x: center.x, y: center.y + r))
                        path.addLine(to: CGPoint(x: center.x - r, y: center.y))
                        path.closeSubpath()
                    }
                }
                let color = mark.mark.tone == .primary ? primaryTint : secondaryTint
                context.fill(shape, with: .color(card))
                context.stroke(shape, with: .color(color), lineWidth: mark.selected ? 3 : 2)
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Originals

    /// Every original in owner order, each a panel of titled channels on the
    /// same 0–100% bars, in columns chosen from the width and the figures'
    /// scale (one at accessibility sizes), with words wrapping inside each panel.
    private var originalsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(input.words.originalsTitle)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if input.showsInvitation(canSelect: canSelect, canOpenDetails: canOpenDetails), let invitation = input.words.invitation {
                Text(invitation)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            TotalMilestoneThresholdPanelLayout10868(
                minimumCellWidth: panelMinimumWidth,
                accessibility: typeSize.isAccessibilitySize
            ) {
                ForEach(input.panels, id: \.index) { panel in
                    panelControl(panel)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.originals)
        }
    }

    /// A button only when it carries an action; otherwise the same content as
    /// one plain element.
    @ViewBuilder private func panelControl(_ panel: TotalMilestoneThresholdPanel10868) -> some View {
        let id = panel.milestone.id
        if let action = input.panelAction(index: panel.index, canSelect: canSelect) {
            Button {
                perform(action)
            } label: {
                panelCell(panel)
            }
            .accessibilityLabel(panel.milestone.title)
            .accessibilityValue(input.accessibilityPanelValue(panel))
            .accessibilityAddTraits(panel.selected ? .isSelected : [])
            .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.option(id))
        } else {
            panelCell(panel)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(panel.milestone.title)
                .accessibilityValue(input.accessibilityPanelValue(panel))
                .accessibilityAddTraits(panel.selected ? .isSelected : [])
                .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.option(id))
        }
    }

    /// The original's own title and drawn mark, then each titled channel with
    /// its figure, clock and bar, then its own result. Selection is a diamond
    /// and a heavier outline — never colour alone.
    private func panelCell(_ panel: TotalMilestoneThresholdPanel10868) -> some View {
        let shape = RoundedRectangle(cornerRadius: 12)
        let beforeTint = panel.mark.map { tint($0.tone) } ?? DS.blue
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                if panel.selected {
                    Image(systemName: "diamond.fill")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityHidden(true)
                }
                if let mark = panel.mark {
                    markGlyph(mark).accessibilityHidden(true)
                }
                Text(panel.milestone.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if panel.isResolved {
                ForEach(Array(panel.channels.enumerated()), id: \.offset) { position, channel in
                    channelView(channel, tint: position == 0 ? beforeTint : DS.emeraldDark)
                }
                if let movement = panel.movement {
                    Text(movement)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.emeraldDark)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let result = panel.result {
                    resultView(result)
                }
            } else {
                Text(input.words.unresolved)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity, alignment: .topLeading)
        .background(panel.selected ? DS.cardBg : DS.surface, in: shape)
        .overlay(shape.strokeBorder(panel.selected ? DS.textPrimary : DS.border, lineWidth: panel.selected ? 2 : 1))
        .contentShape(shape)
    }

    /// A channel's title, then its figure at the shared prominent size, its
    /// own clock and its bar — or the owner's words with no bar.
    @ViewBuilder private func channelView(_ channel: TotalMilestoneThresholdChannel10868, tint: Color) -> some View {
        switch channel {
        case .chance(let title, let observation):
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let time = observation.timeText {
                    Text(time).font(.footnote).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
                if TotalMilestoneGeometry10868.fraction(observation.probability) != nil {
                    bar(observation.probability, tint: tint)
                }
            }
        case .status(let title, let text):
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                Text(text)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The fixed 0–100% track with the chance's fill and an end tick, so a
    /// real 0% still shows its place.
    private func bar(_ probability: Double, tint: Color) -> some View {
        let track = DS.trackBg
        return Canvas { context, size in
            guard let fill = TotalMilestoneThresholdLiveInput10868.barWidth(probability, track: size.width) else { return }
            context.fill(Path(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: size.height / 2), with: .color(track))
            context.fill(Path(roundedRect: CGRect(x: 0, y: 0, width: fill, height: size.height), cornerRadius: size.height / 2),
                         with: .color(tint))
            let tick = min(max(0, fill - 1), max(0, size.width - 2))
            context.fill(Path(CGRect(x: tick, y: 0, width: 2, height: size.height)), with: .color(tint))
        }
        .frame(maxWidth: .infinity)
        .frame(height: barHeight)
        .accessibilityHidden(true)
    }

    /// The row's own result under its own label, with a check or cross; a
    /// pending result has neither, so unknown never reads as a loss.
    private func resultView(_ result: TotalMilestoneResult10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(TotalMilestoneThresholdLiveInput10868.resultTitle)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                switch result.mark {
                case .check?:
                    Image(systemName: "checkmark.circle").accessibilityHidden(true)
                case .cross?:
                    Image(systemName: "xmark.circle").accessibilityHidden(true)
                case nil:
                    EmptyView()
                }
                Text(result.text).fixedSize(horizontal: false, vertical: true)
            }
            .font(result.isAdmitted ? .subheadline.weight(.semibold) : .footnote.weight(.semibold))
            .foregroundStyle(result.isAdmitted ? DS.textPrimary : DS.textSecondary)
        }
    }

    // MARK: Timing and Details

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

    private func timingLines(_ content: TotalMilestoneTiming10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(content.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The exact selected original's Details, named by its own title.
    @ViewBuilder private var detailsButton: some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails), let milestone = input.selection.milestone {
            Button {
                perform(action)
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(TotalMilestoneInput10868.detailsTitle)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(milestone.title)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityLabel("\(TotalMilestoneInput10868.detailsTitle), \(milestone.title)")
            .accessibilityIdentifier(TotalMilestoneThresholdLiveAccessibilityID10868.details(milestone.id))
        }
    }

    private func perform(_ action: TotalMilestoneAction10868?) {
        action?.perform(onSelect: onSelect, onDetails: onDetails)
    }
}
