import SwiftUI

// #10868 — "Chance to win": the named-field probability history that anchors
// the golf-reading and golf-journey pages before, during and after a
// tournament. Every original the owner supplies is drawn as its own solid
// run(s) against one shared horizontal domain and one owner-chosen probability range,
// keyed by full name, tint AND shape (circle, square, diamond or triangle), with a
// wrapping key that carries each original's readouts.
//
// Presentation only, extracted from the approved design: `GolfRaceChart.tsx`
// with `golfJourney.css` / `golfReadingReplay.css`, as mounted by
// `GolfReadingReplay.tsx` and `GolfJourney.tsx`; `golfSeriesIdentity.tsx`
// (the three shapes), `golfReadable.ts` (endpoint label lanes) and
// `golfEstimateLinks.ts` (dashed before-event comparisons) are visual
// references only. The prototype's evidence loader, featured-golfer ranking,
// three-golfer cap, automatic ceiling, baseline/cutoff, 30-minute
// segmentation, compressed time, point election and replay/hold state are NOT
// ported.
//
// Owner-resolved, never derived here: which originals exist, their order,
// names, tints and shapes; each original's explicitly separated runs and the
// mark style of every point; the dashed comparison links between exact point
// ids and the words that explain them; the horizontal domain (any
// owner-transformed coordinate) and every tick, round guide and unobserved
// break inside it; the explicit probability bounds and percentage ticks (zero
// remains the default lower bound); the readout
// intent and every reading's figure and provenance words; the selected
// original; every control's id, words and availability; the inspection. This
// layer never reads, parses or re-times a clock, never formats a percentage
// or a date, never picks a latest, first, nearest or leading observation,
// never ranks, sorts, caps or normalizes originals, never chooses a ceiling,
// window or compression, never extends a line to "now", to a result or to a
// 0%/100% end, and holds no phase, currentness, gap, settlement or source
// policy. A result or finish is composed elsewhere; nothing here turns one
// into a point.
//
// Drawing rules: a point is placed only when both owner domains are valid,
// its x lies inside the time domain and its probability lies inside the
// explicit probability range. Real 0 and real 1 remain values on ranges that
// include them. Anything else draws
// nothing AND breaks the run there — no clamp, no line toward an edge. A run
// also breaks where x does not advance and wherever an owner break lies
// between two points, so an unobserved break never carries a joining line. A
// run of one point is a mark. Dashed comparison links are drawn only between
// two distinct, uniquely resolving, placeable point ids of the same original,
// and only while the owner's explanation is shown; they are never inspected
// as values and never built from dates or array order.
//
// Identity: an original whose id is empty or shared keeps its name, line,
// marks and own absence words, but gets no direct endpoint label, no
// selection, no inspection ring and no observation-bound reading. A control
// hands back its owner id only when that id is nonempty and unique among all
// the input's controls and a callback exists; otherwise an informative
// control (scale, period, original) stays visible but static, and a pure
// action (more, Details, expand, inspect, previous, next) is shown static
// when a callback exists and hidden in a callback-free static view. A tap on
// the plot hands back the domain position for the owner to resolve; nothing
// is snapped. The view keeps no state, runs no animation, holds no
// subscription and moves no focus.
//
// Compositions (the owner's layout): ordinary leads with every original's
// key and readouts above the plot; focused leads with only the exact
// selected original's name, shape and readouts, the full key below;
// expanded leads with the plot, the full key below. A selection that names
// no single original shows the owner's words in every composition. An
// inspected readout is a figure only when it is bound to the very
// observation the inspection selected.
//
// Owner opt-ins, absent by default so every existing chart is unchanged: a
// focused headline readout independent of the key's (the headline shows the
// exact inspected reading; the key keeps its own intent and never borrows the
// inspection's absence words); per-original key context, such as a
// separately reported finish, shown only in the key and apart from every
// reading — never a point, domain, mark style or settlement; an
// inspection ring of one owner shape around the unchanged observation mark;
// an explicit plot absence ("No retained trades"), chosen by the owner and
// never from a point count, that shows its own wrapping words in place of
// the plot, axes, mark key and chart-only controls (expand, scale, periods,
// inspection) while the title, selected readouts, notes and Details remain —
// nothing is drawn or observation-bound under it, and no zero is shown; and
// a hidden field key for a single-original reader whose headline already
// names its original.
//
// Host binding still owed — not available at this base. GolfTournamentPresentation
// carries ranked current rows, not dated history, admitted before readings or
// selection/clock context; FuturesHistoryResponse / ProbabilityTimelineResponse
// carry per-original history whose membership and qualified segments an
// existing owner must prove; EvolutionChartView owns its own fetch and range;
// ChartProbabilityAxis9483 is paired/home-only with a 20-point minimum span
// (FIELD-HISTORY-BINDING-SOURCES.json "limits").

// MARK: - Input

/// An original's stable non-colour key, on its marks, labels and key entry.
nonisolated enum FieldHistoryShape10868: Equatable, CaseIterable {
    case circle
    case square
    case diamond
    case triangle
}

/// The owner's admitted mark style for one point (for example hollow earlier
/// estimates and a filled selected estimate). Never inferred from a value or
/// a time.
nonisolated enum FieldHistoryMarkStyle10868: Equatable {
    case filled
    case hollow
}

/// One owner-qualified observation.
nonisolated struct FieldHistoryPoint10868: Equatable {
    /// The owner's opaque, stable point identity.
    let id: String
    /// The owner's position on the shared horizontal domain. Never read as a
    /// clock here.
    let x: Double
    /// Inside the owner's probability range. Anything else is not placed and breaks the run.
    let probability: Double
    let style: FieldHistoryMarkStyle10868
}

/// One explicitly separated run of observations. Two runs are never joined.
nonisolated struct FieldHistoryRun10868: Equatable {
    let id: String
    /// In the owner's order.
    let points: [FieldHistoryPoint10868]
}

/// An owner-supplied dashed comparison between two sparse estimates of the
/// same original. It establishes no history between them.
nonisolated struct FieldHistoryComparisonLink10868: Equatable {
    let id: String
    let fromPointID: String
    let toPointID: String
}

/// One reading slot's content, in the owner's words.
nonisolated enum FieldHistoryReading10868: Equatable {
    /// A figure for one exact observation of this original, bound by id.
    case observation(pointID: String, figure: String, provenance: String)
    /// A figure the owner admitted independently of the drawn points (for
    /// example a before-event estimate outside the visible window). Not a
    /// drawn point.
    case independent(figure: String, provenance: String)
    /// No reading, with its own reason ("No captured history").
    case absent(words: String)
}

/// One owner action: its id, visible words, optional fuller spoken words and
/// whether it is available now.
nonisolated struct FieldHistoryAction10868: Equatable {
    let id: String
    let label: String
    let spokenLabel: String?
    let isAvailable: Bool
}

/// The owner's context for one original's key entry ("Result" · "Gold", a
/// separately reported finish). Words only: never a reading, a point, a
/// domain, a mark style or a settlement, and never derived here.
nonisolated struct FieldHistoryKeyContext10868: Equatable {
    let label: String
    let words: String
    /// Fuller spoken words ("Reported finish: Gold"); label and words otherwise.
    let spoken: String?
}

/// One original's history.
nonisolated struct FieldHistorySeries10868: Equatable {
    /// The owner's opaque, stable original identity.
    let id: String
    /// The full name, shown and spoken verbatim.
    let name: String
    let shape: FieldHistoryShape10868
    /// The owner's stable tint for the line, marks, label and key.
    let tint: Color
    let runs: [FieldHistoryRun10868]
    let links: [FieldHistoryComparisonLink10868]
    /// The exact point a direct endpoint label is attached to. No label when
    /// absent or unresolved; never the last point by default.
    let labelPointID: String?
    let before: FieldHistoryReading10868
    /// Shown only when the readout intent asks for a recorded slot, or, in
    /// the inspected intent, only when bound to the exact inspected point.
    let recorded: FieldHistoryReading10868
    /// The owner's words when nothing of this original is drawn.
    let absentWords: String?
    /// The owner's action that chooses this original.
    let choose: FieldHistoryAction10868?
    /// Shown in this original's key entry only, apart from its readouts.
    var keyContext: FieldHistoryKeyContext10868? = nil
}

/// The owner's horizontal plot domain.
nonisolated struct FieldHistoryDomain10868: Equatable {
    let lower: Double
    let upper: Double

    var isValid: Bool { lower.isFinite && upper.isFinite && upper > lower }

    func contains(_ x: Double) -> Bool {
        isValid && x.isFinite && x >= lower && x <= upper
    }
}

/// One owner axis tick: a value on its axis and its words, line by line.
nonisolated struct FieldHistoryTick10868: Equatable {
    /// A probability on the vertical axis, or a domain value on the
    /// horizontal axis.
    let value: Double
    /// Verbatim ("5%"; or "Oct 8" then "R1").
    let lines: [String]
}

/// One owner guide on the shared clock ("R1"). Context only: never proof of
/// a tee time or a round start.
nonisolated struct FieldHistoryGuide10868: Equatable {
    let id: String
    let x: Double
    let label: String
}

/// One explicit unobserved break on the domain, with its mark ("//").
nonisolated struct FieldHistoryBreak10868: Equatable {
    let id: String
    let lower: Double
    let upper: Double
    let mark: String

    var isValid: Bool { lower.isFinite && upper.isFinite && upper > lower }
}

/// The owner's display intent for each original's readout.
nonisolated enum FieldHistoryReadoutIntent10868: Equatable {
    /// One slot: the original's `before` reading (a single dated estimate).
    case singleBefore(label: String)
    /// Two equal slots: `before`, then the separately labelled `recorded`.
    case beforeAndRecorded(beforeLabel: String, recordedLabel: String)
    /// Two equal slots: `before`, then the original's reading at the exact
    /// inspected observation. The second is a figure only when `recorded`
    /// is an observation reading of that same exact, placeable point;
    /// otherwise the inspection's own absence words or the unbound words.
    case beforeAndInspected(beforeLabel: String, inspectedLabel: String)
}

/// The owner's readout for the focused headline alone ("Inspected before race
/// day"); the key keeps `readout`. The inspected slot follows the
/// `beforeAndInspected` binding rule exactly.
nonisolated struct FieldHistorySelectedReadout10868: Equatable {
    /// Supplied: the original's own `before` reading leads, then the inspected
    /// slot. Absent: the inspected slot alone.
    let beforeLabel: String?
    let inspectedLabel: String
}

/// The owner's explicit statement that this reader has no plot ("No retained
/// trades"). Composition only: never chosen from a point count, never a zero.
nonisolated struct FieldHistoryPlotAbsence10868: Equatable {
    let title: String
    /// "This original Yes outcome has no traded history in this capture."
    let words: String?
}

/// The owner's composition of this one chart. Not a variant.
nonisolated enum FieldHistoryLayout10868: Equatable, CaseIterable {
    /// Probability first: every original's key and readouts above the plot.
    case cohortAbove
    /// The exact selected original's readouts above the plot; the full key
    /// below.
    case focused
    /// The plot first; the full key below.
    case expanded
}

/// The owner's words for each mark style, shown only when that style is drawn.
nonisolated struct FieldHistoryMarkKey10868: Equatable {
    let hollow: String?
    let filled: String?
}

/// The owner's selected original.
nonisolated enum FieldHistoryOriginalSelection10868: Equatable {
    case none
    /// By exact id; its own words when that id does not name exactly one
    /// original. Never the first neighbour.
    case series(id: String, missingWords: String)
    /// The selected original is unavailable or withdrawn, in the owner's words.
    case unavailable(words: String)
}

nonisolated struct FieldHistoryWindowChoice10868: Equatable {
    let action: FieldHistoryAction10868
    let isSelected: Bool
}

/// The owner's period/window choices ("Before", "R1", "Week").
nonisolated struct FieldHistoryWindows10868: Equatable {
    let groupLabel: String
    let choices: [FieldHistoryWindowChoice10868]
}

/// One original at the owner's inspected position.
nonisolated enum FieldHistorySelection10868: Equatable {
    /// The exact point the owner selected, and its spoken words ("2.4%").
    case point(id: String, spoken: String)
    /// No observation there, in the owner's words ("Not recorded").
    case absent(words: String)
}

/// One ordered, discrete inspection choice the owner offers.
nonisolated struct FieldHistoryInspectionChoice10868: Equatable {
    let id: String
    /// Visible words, line by line ("Oct 6" then "6:08 AM").
    let lines: [String]
    /// Spoken words.
    let spoken: String
    let isSelected: Bool
}

nonisolated enum FieldHistoryChoicePresentation10868: Equatable {
    /// One button per choice (sparse estimates).
    case buttons(groupLabel: String)
    /// A native discrete slider handing back the exact choice.
    case slider(label: String)
}

/// The host's held inspection, drawn exactly as supplied.
nonisolated struct FieldHistoryInspection10868: Equatable {
    /// The cursor's domain position. Not drawn when absent or outside.
    let x: Double?
    /// "Recorded Oct 9, 8:46 PM".
    let caption: String
    /// By original id.
    let selections: [String: FieldHistorySelection10868]
    let choices: [FieldHistoryInspectionChoice10868]
    let choicePresentation: FieldHistoryChoicePresentation10868
    /// "Only exact captured observations are shown."
    let note: String?
}

nonisolated struct FieldHistoryInput10868: Equatable {
    /// "Chance to win".
    let title: String
    /// "Recorded · Week".
    let caption: String?
    /// In the owner's order, every one drawn. No implicit cap.
    let series: [FieldHistorySeries10868]
    let selection: FieldHistoryOriginalSelection10868
    let domain: FieldHistoryDomain10868
    /// The owner's top of the probability axis, finite in (0, 1].
    let ceiling: Double
    /// Owner percentage ticks inside the probability range.
    let yTicks: [FieldHistoryTick10868]
    /// Owner calendar ticks inside the domain.
    let xTicks: [FieldHistoryTick10868]
    let guides: [FieldHistoryGuide10868]
    let breaks: [FieldHistoryBreak10868]
    let readout: FieldHistoryReadoutIntent10868
    let markKey: FieldHistoryMarkKey10868
    /// Shown, and required, for dashed comparison links to be drawn.
    let comparisonExplanation: String?
    /// Source, clock, granularity, time-zone and break words, verbatim.
    let notes: [String]
    /// The owner's complete spoken description of the plot.
    let summary: String
    /// The owner's plot height in points. Never shrunk here.
    let plotHeight: CGFloat
    /// Shown in place of a figure whose observation id does not bind.
    let unboundReadingWords: String
    /// Shown over the plot when it cannot draw numeric marks.
    let plotUnavailableWords: String?
    let windows: FieldHistoryWindows10868?
    /// "Auto scale · 0–10%" / "Full scale · 0–100%".
    let scale: FieldHistoryAction10868?
    /// Opens the host's chooser.
    let moreOriginals: FieldHistoryAction10868?
    let details: FieldHistoryAction10868?
    let expand: FieldHistoryAction10868?
    /// "Inspect history" or "Done inspecting".
    let inspect: FieldHistoryAction10868?
    let previous: FieldHistoryAction10868?
    let next: FieldHistoryAction10868?
    let inspection: FieldHistoryInspection10868?
    /// The owner's composition; probability first unless told otherwise.
    var layout: FieldHistoryLayout10868 = .cohortAbove
    /// Explicit owner crop, for example 0.35...0.7 before a match. The existing
    /// zero-based field chart remains the default. No range is elected here.
    var probabilityLowerBound: Double = 0
    /// Visible owner explanation, e.g. "Zoomed probability range · 35–70%".
    /// Required for a nonzero lower bound; no hidden crop is drawn.
    var probabilityRangeExplanation: String? = nil
    /// The focused headline's own readout. Absent: the key's slots, as before.
    var selectedReadout: FieldHistorySelectedReadout10868? = nil
    /// The inspection ring's shape, for example a circle around every
    /// original. Absent: each original's own shape.
    var inspectionRingShape: FieldHistoryShape10868? = nil
    /// Shown in place of the plot and its chart-only controls. Absent: the
    /// plot, as before, whatever the points.
    var plotAbsence: FieldHistoryPlotAbsence10868? = nil
    /// False only for a reader whose headline already names its single
    /// original. Selection words and the headline stay.
    var showsKey: Bool = true
}

// MARK: - Derived values

/// A reading as the key shows it.
nonisolated enum FieldHistoryReadingDisplay10868: Equatable {
    case figure(String, provenance: String)
    case words(String)
}

/// One readout slot: the owner's label and what it shows.
nonisolated struct FieldHistoryReadoutSlot10868: Equatable {
    let label: String
    let display: FieldHistoryReadingDisplay10868
}

/// One block of readouts placed above or below the plot.
nonisolated enum FieldHistoryReadoutBlock10868: Hashable {
    /// The owner's words for a selection that names no single original.
    case selectionWords
    /// The selected original alone, or the owner's words for its absence.
    case selectedSummary
    /// Every original's key entry.
    case key
}

/// What the focused composition shows above the plot.
nonisolated enum FieldHistorySelectedSummary10868: Equatable {
    /// No original is selected.
    case none
    /// The owner's words: missing, withdrawn, unknown or ambiguous.
    case words(String)
    /// The exact selected original and the same slots its key entry shows.
    case original(FieldHistorySeries10868, slots: [FieldHistoryReadoutSlot10868])
}

/// How a control is presented.
nonisolated enum FieldHistoryControlState10868: Equatable {
    case hidden
    /// Visible words, no action.
    case shownStatic
    /// A button handing back this exact id.
    case live(id: String)
}

/// Where one direct endpoint label should sit, as fractions of the plot's
/// drawing frame.
nonisolated struct FieldHistoryLabelTarget10868: Equatable {
    let xFraction: Double
    let yFraction: Double
}

/// Where one axis or guide label sits along its axis, and which lane it was
/// moved to so it touches no other label.
nonisolated struct FieldHistoryLabelSlot10868: Equatable {
    let start: CGFloat
    let lane: Int
}

/// One leader from an endpoint mark to its direct label.
nonisolated struct FieldHistoryLeaderGeometry10868: Equatable {
    let frame: CGRect
    /// True when the label end is higher than the point end.
    let rising: Bool
}

/// Fixed spacing rules of the measured plot.
nonisolated struct FieldHistoryPlotMetrics10868: Equatable {
    var labelGap: CGFloat = 6
    var axisGap: CGFloat = 6
    var laneSpacing: CGFloat = 4
    /// Between the plot's right edge and the direct-label column.
    var leaderGap: CGFloat = 14
    /// Between stacked direct labels.
    var directLabelGap: CGFloat = 4
    /// The label column never takes more of the width beside the gutter.
    var maximumLabelColumnFraction: CGFloat = 0.36
    /// The plot keeps at least this width when labels are direct.
    var minimumPlotWidth: CGFloat = 140
}

/// The measured plot: the drawing frame, every label's frame and the total
/// height. `directLabels` and `leaders` are empty when names live only in
/// the key.
nonisolated struct FieldHistoryPlotArrangement10868: Equatable {
    let plot: CGRect
    let yLabels: [CGRect]
    let xLabels: [CGRect]
    let guideLabels: [CGRect]
    let directLabels: [CGRect]
    let leaders: [FieldHistoryLeaderGeometry10868]
    let yColumns: Int
    let xRows: Int
    let guideRows: Int
    let height: CGFloat

    var usesDirectLabels: Bool { !directLabels.isEmpty }
}

// MARK: - Geometry

/// Pure rules the view draws from. Unit-tested without rendering.
nonisolated enum FieldHistoryGeometry10868 {
    /// Used only when the owner's height is not a usable size.
    static let referencePlotHeight: CGFloat = 240

    static func plotHeight(_ owner: CGFloat) -> CGFloat {
        owner.isFinite && owner > 0 ? owner : referencePlotHeight
    }

    static func isValidCeiling(_ ceiling: Double) -> Bool {
        ceiling.isFinite && ceiling > 0 && ceiling <= 1
    }

    static func isValidProbabilityRange(lower: Double, ceiling: Double) -> Bool {
        isValidCeiling(ceiling) && lower.isFinite && lower >= 0 && lower < ceiling
    }

    static func probabilityRangeExplanation(_ input: FieldHistoryInput10868) -> String? {
        guard let words = input.probabilityRangeExplanation, words.contains(where: { !$0.isWhitespace }) else { return nil }
        return words
    }

    /// Numeric marks are drawn only on a valid time and probability range,
    /// and never under the owner's explicit plot absence.
    static func isDrawable(_ input: FieldHistoryInput10868) -> Bool {
        showsPlot(input)
            && input.domain.isValid && isValidProbabilityRange(lower: input.probabilityLowerBound, ceiling: input.ceiling)
            && (input.probabilityLowerBound == 0 || probabilityRangeExplanation(input) != nil)
    }

    static func isPlaceable(_ point: FieldHistoryPoint10868,
                            domain: FieldHistoryDomain10868,
                            ceiling: Double,
                            lower: Double = 0) -> Bool {
        isValidProbabilityRange(lower: lower, ceiling: ceiling)
            && domain.contains(point.x)
            && point.probability.isFinite
            && point.probability >= lower
            && point.probability <= ceiling
    }

    static func isPlaceable(_ point: FieldHistoryPoint10868, in input: FieldHistoryInput10868) -> Bool {
        isDrawable(input) && isPlaceable(point, domain: input.domain, ceiling: input.ceiling, lower: input.probabilityLowerBound)
    }

    /// Whether an owner break lies between two consecutive x positions.
    static func breakSeparates(_ lower: Double, _ upper: Double, breaks: [FieldHistoryBreak10868]) -> Bool {
        breaks.contains { $0.isValid && $0.lower < upper && $0.upper > lower }
    }

    /// The drawn runs of one owner run: maximal stretches of consecutive
    /// placeable points whose x advances and that no break separates.
    static func drawnRuns(_ run: FieldHistoryRun10868,
                          in input: FieldHistoryInput10868) -> [[FieldHistoryPoint10868]] {
        var runs: [[FieldHistoryPoint10868]] = []
        var current: [FieldHistoryPoint10868] = []
        for point in run.points {
            guard isPlaceable(point, in: input) else {
                if !current.isEmpty { runs.append(current) }
                current = []
                continue
            }
            if let last = current.last,
               !(point.x > last.x) || breakSeparates(last.x, point.x, breaks: input.breaks) {
                runs.append(current)
                current = []
            }
            current.append(point)
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }

    /// Every solid line of an original: drawn runs of two or more points,
    /// run by run. Never joined across owner runs.
    static func lines(_ series: FieldHistorySeries10868,
                      in input: FieldHistoryInput10868) -> [[FieldHistoryPoint10868]] {
        series.runs.flatMap { drawnRuns($0, in: input) }.filter { $0.count >= 2 }
    }

    /// Every mark of an original: each placeable point, in the owner's order.
    static func marks(_ series: FieldHistorySeries10868,
                      in input: FieldHistoryInput10868) -> [FieldHistoryPoint10868] {
        series.runs.flatMap(\.points).filter { isPlaceable($0, in: input) }
    }

    /// The single point of this original with a nonempty id, or nothing.
    static func uniquePoint(_ id: String, in series: FieldHistorySeries10868) -> FieldHistoryPoint10868? {
        guard !id.isEmpty else { return nil }
        let matches = series.runs.flatMap(\.points).filter { $0.id == id }
        return matches.count == 1 ? matches.first : nil
    }

    /// The original's own absence words, only when nothing of it is drawn.
    static func absentWords(_ series: FieldHistorySeries10868, in input: FieldHistoryInput10868) -> String? {
        marks(series, in: input).isEmpty ? series.absentWords : nil
    }

    // MARK: Comparison links

    /// The explanation counts only with at least one visible character.
    static func showsComparisonExplanation(_ input: FieldHistoryInput10868) -> Bool {
        guard let words = input.comparisonExplanation else { return false }
        return words.contains { !$0.isWhitespace }
    }

    /// A link's endpoints: two distinct ids, each naming exactly one placeable
    /// point of this original, while the explanation is shown. Otherwise none.
    static func linkEndpoints(_ link: FieldHistoryComparisonLink10868,
                              of series: FieldHistorySeries10868,
                              in input: FieldHistoryInput10868) -> (FieldHistoryPoint10868, FieldHistoryPoint10868)? {
        guard showsComparisonExplanation(input), link.fromPointID != link.toPointID,
              let from = uniquePoint(link.fromPointID, in: series),
              let to = uniquePoint(link.toPointID, in: series),
              isPlaceable(from, in: input), isPlaceable(to, in: input) else { return nil }
        return (from, to)
    }

    static func comparisonLinks(_ series: FieldHistorySeries10868,
                                in input: FieldHistoryInput10868) -> [(FieldHistoryPoint10868, FieldHistoryPoint10868)] {
        series.links.compactMap { linkEndpoints($0, of: series, in: input) }
    }

    static func drawsComparisonLink(_ input: FieldHistoryInput10868) -> Bool {
        input.series.contains { !comparisonLinks($0, in: input).isEmpty }
    }

    /// The dashed-link key's words, verbatim, only while a link is drawn.
    static func comparisonKeyWords(_ input: FieldHistoryInput10868) -> String? {
        drawsComparisonLink(input) ? input.comparisonExplanation : nil
    }

    /// A mark-style key entry appears only when a mark of that style is drawn.
    static func drawsStyle(_ style: FieldHistoryMarkStyle10868, in input: FieldHistoryInput10868) -> Bool {
        input.series.contains { marks($0, in: input).contains { $0.style == style } }
    }

    // MARK: Identity and selection

    /// Whether this original's id can name it alone: nonempty, and exactly
    /// one supplied original carries it. Nothing is renamed or dropped.
    static func isExactlyIdentified(_ series: FieldHistorySeries10868,
                                    in input: FieldHistoryInput10868) -> Bool {
        !series.id.isEmpty && input.series.filter { $0.id == series.id }.count == 1
    }

    /// The point a direct label is attached to: the owner's exact, placeable
    /// label point of an exactly identified original.
    static func labelAnchor(_ series: FieldHistorySeries10868,
                            in input: FieldHistoryInput10868) -> FieldHistoryPoint10868? {
        guard isExactlyIdentified(series, in: input), let id = series.labelPointID,
              let point = uniquePoint(id, in: series), isPlaceable(point, in: input) else { return nil }
        return point
    }

    /// Originals with a direct label, in the owner's order.
    static func labelledSeries(_ input: FieldHistoryInput10868) -> [(FieldHistorySeries10868, FieldHistoryPoint10868)] {
        input.series.compactMap { series in labelAnchor(series, in: input).map { (series, $0) } }
    }

    static func labelTarget(_ point: FieldHistoryPoint10868,
                            in input: FieldHistoryInput10868) -> FieldHistoryLabelTarget10868 {
        FieldHistoryLabelTarget10868(xFraction: fraction(point.x, in: input.domain),
                                     yFraction: probabilityFraction(point.probability, lower: input.probabilityLowerBound, ceiling: input.ceiling))
    }

    /// Whether this original is the owner's selected one.
    static func isSelected(_ series: FieldHistorySeries10868, in input: FieldHistoryInput10868) -> Bool {
        guard case .series(let id, _) = input.selection else { return false }
        return series.id == id && isExactlyIdentified(series, in: input)
    }

    /// The owner's words when the selection names no single original, or is
    /// unavailable. Never a neighbour's name.
    static func selectionWords(_ input: FieldHistoryInput10868) -> String? {
        switch input.selection {
        case .none:
            return nil
        case .unavailable(let words):
            return words
        case .series(let id, let missingWords):
            return input.series.contains(where: { $0.id == id && isExactlyIdentified($0, in: input) })
                ? nil : missingWords
        }
    }

    /// The focused headline: the exact selected original with its resolved
    /// slots, or the owner's absence words. Never a neighbour.
    static func selectedSummary(_ input: FieldHistoryInput10868) -> FieldHistorySelectedSummary10868 {
        if let words = selectionWords(input) { return .words(words) }
        guard let series = input.series.first(where: { isSelected($0, in: input) }) else { return .none }
        return .original(series, slots: selectedSlots(series, in: input))
    }

    /// The focused headline's slots: the owner's own selected readout when
    /// supplied, otherwise the same slots the key shows.
    static func selectedSlots(_ series: FieldHistorySeries10868,
                              in input: FieldHistoryInput10868) -> [FieldHistoryReadoutSlot10868] {
        guard let readout = input.selectedReadout else { return readoutSlots(series, in: input) }
        let inspected = FieldHistoryReadoutSlot10868(label: readout.inspectedLabel,
                                                     display: inspectedDisplay(series, in: input))
        guard let beforeLabel = readout.beforeLabel else { return [inspected] }
        return [FieldHistoryReadoutSlot10868(label: beforeLabel, display: display(series.before, of: series, in: input)),
                inspected]
    }

    // MARK: Compositions

    static func blocksAbovePlot(_ input: FieldHistoryInput10868) -> [FieldHistoryReadoutBlock10868] {
        switch input.layout {
        case .cohortAbove: return keyVisibility([.selectionWords, .key], in: input)
        case .focused: return [.selectedSummary]
        case .expanded: return []
        }
    }

    static func blocksBelowPlot(_ input: FieldHistoryInput10868) -> [FieldHistoryReadoutBlock10868] {
        switch input.layout {
        case .cohortAbove: return []
        case .focused: return keyVisibility([.key], in: input)
        case .expanded: return keyVisibility([.selectionWords, .key], in: input)
        }
    }

    /// Drops only the field key when the owner hides it.
    static func keyVisibility(_ blocks: [FieldHistoryReadoutBlock10868],
                              in input: FieldHistoryInput10868) -> [FieldHistoryReadoutBlock10868] {
        input.showsKey ? blocks : blocks.filter { $0 != .key }
    }

    // MARK: Explicit absence

    /// The owner's explicit plot absence, exactly as supplied.
    static func plotAbsence(_ input: FieldHistoryInput10868) -> FieldHistoryPlotAbsence10868? {
        input.plotAbsence
    }

    static func showsPlot(_ input: FieldHistoryInput10868) -> Bool {
        plotAbsence(input) == nil
    }

    /// The absence explanation, only with visible words.
    static func absenceWords(_ absence: FieldHistoryPlotAbsence10868) -> String? {
        guard let words = absence.words, words.contains(where: { !$0.isWhitespace }) else { return nil }
        return words
    }

    /// A chart-only control (expand, scale, period, inspect, previous, next):
    /// hidden under an explicit absence, otherwise exactly `controlState`.
    static func chartControlState(_ action: FieldHistoryAction10868?,
                                  informative: Bool,
                                  hasCallback: Bool,
                                  in input: FieldHistoryInput10868) -> FieldHistoryControlState10868 {
        showsPlot(input) ? controlState(action, informative: informative, hasCallback: hasCallback, in: input) : .hidden
    }

    static func shownWindows(_ input: FieldHistoryInput10868) -> FieldHistoryWindows10868? {
        showsPlot(input) ? input.windows : nil
    }

    static func shownInspection(_ input: FieldHistoryInput10868) -> FieldHistoryInspection10868? {
        showsPlot(input) ? input.inspection : nil
    }

    // MARK: Readouts

    static func display(_ reading: FieldHistoryReading10868,
                        of series: FieldHistorySeries10868,
                        in input: FieldHistoryInput10868) -> FieldHistoryReadingDisplay10868 {
        switch reading {
        case .observation(let pointID, let figure, let provenance):
            guard showsPlot(input), isExactlyIdentified(series, in: input),
                  let point = uniquePoint(pointID, in: series),
                  point.probability.isFinite, point.probability >= 0, point.probability <= 1 else {
                return .words(input.unboundReadingWords)
            }
            return .figure(figure, provenance: provenance)
        case .independent(let figure, let provenance):
            return .figure(figure, provenance: provenance)
        case .absent(let words):
            return .words(words)
        }
    }

    /// The original's reading at the inspection: a figure only for an
    /// observation reading of the exact, unique, placeable inspected point;
    /// the inspection's own absence words; otherwise the unbound words.
    /// Never an independent reading, a neighbour or another observation.
    static func inspectedDisplay(_ series: FieldHistorySeries10868,
                                 in input: FieldHistoryInput10868) -> FieldHistoryReadingDisplay10868 {
        if let words = inspectedAbsentWords(series, in: input) { return .words(words) }
        guard let point = inspectedPoint(series, in: input),
              case .observation(let pointID, let figure, let provenance) = series.recorded,
              pointID == point.id else {
            return .words(input.unboundReadingWords)
        }
        return .figure(figure, provenance: provenance)
    }

    /// The slots the key shows for one original, in the owner's intent.
    static func readoutSlots(_ series: FieldHistorySeries10868,
                             in input: FieldHistoryInput10868) -> [FieldHistoryReadoutSlot10868] {
        switch input.readout {
        case .singleBefore(let label):
            return [FieldHistoryReadoutSlot10868(label: label, display: display(series.before, of: series, in: input))]
        case .beforeAndRecorded(let beforeLabel, let recordedLabel):
            return [
                FieldHistoryReadoutSlot10868(label: beforeLabel, display: display(series.before, of: series, in: input)),
                FieldHistoryReadoutSlot10868(label: recordedLabel, display: display(series.recorded, of: series, in: input)),
            ]
        case .beforeAndInspected(let beforeLabel, let inspectedLabel):
            return [
                FieldHistoryReadoutSlot10868(label: beforeLabel, display: display(series.before, of: series, in: input)),
                FieldHistoryReadoutSlot10868(label: inspectedLabel, display: inspectedDisplay(series, in: input)),
            ]
        }
    }

    // MARK: Controls

    /// Every owner action in the input, in one id space.
    static func actions(_ input: FieldHistoryInput10868) -> [FieldHistoryAction10868] {
        var all: [FieldHistoryAction10868] = (input.windows?.choices ?? []).map(\.action)
        all += [input.scale, input.moreOriginals, input.details, input.expand,
                input.inspect, input.previous, input.next].compactMap { $0 }
        all += input.series.compactMap(\.choose)
        return all
    }

    /// The id an action hands back: nonempty and unique among all actions.
    static func liveID(_ action: FieldHistoryAction10868, in input: FieldHistoryInput10868) -> String? {
        guard !action.id.isEmpty, actions(input).filter({ $0.id == action.id }).count == 1 else { return nil }
        return action.id
    }

    static func controlState(_ action: FieldHistoryAction10868?,
                             informative: Bool,
                             hasCallback: Bool,
                             in input: FieldHistoryInput10868) -> FieldHistoryControlState10868 {
        guard let action else { return .hidden }
        if hasCallback, let id = liveID(action, in: input) { return .live(id: id) }
        return hasCallback || informative ? .shownStatic : .hidden
    }

    /// Choosing an original also needs that original to be exactly identified.
    static func chooseState(_ series: FieldHistorySeries10868,
                            hasCallback: Bool,
                            in input: FieldHistoryInput10868) -> FieldHistoryControlState10868 {
        let state = controlState(series.choose, informative: true, hasCallback: hasCallback, in: input)
        if case .live = state, !isExactlyIdentified(series, in: input) { return .shownStatic }
        return state
    }

    /// Previous/next for VoiceOver adjustment: live and available only.
    static func adjustableID(_ action: FieldHistoryAction10868?,
                             hasCallback: Bool,
                             in input: FieldHistoryInput10868) -> String? {
        guard let action, action.isAvailable,
              case .live(let id) = controlState(action, informative: false, hasCallback: hasCallback, in: input)
        else { return nil }
        return id
    }

    // MARK: Inspection

    static func cursor(_ input: FieldHistoryInput10868) -> Double? {
        guard let x = input.inspection?.x, input.domain.contains(x) else { return nil }
        return x
    }

    /// The ring of an exactly identified original: its exact, placeable
    /// selected point, or nothing. Never the nearest, never a neighbour.
    static func inspectedPoint(_ series: FieldHistorySeries10868,
                               in input: FieldHistoryInput10868) -> FieldHistoryPoint10868? {
        guard isExactlyIdentified(series, in: input),
              case .point(let id, _)? = input.inspection?.selections[series.id],
              let point = uniquePoint(id, in: series), isPlaceable(point, in: input) else { return nil }
        return point
    }

    static func inspectedAbsentWords(_ series: FieldHistorySeries10868,
                                     in input: FieldHistoryInput10868) -> String? {
        guard isExactlyIdentified(series, in: input),
              case .absent(let words)? = shownInspection(input)?.selections[series.id] else { return nil }
        return words
    }

    /// The words under a key name: own absence first, then inspected
    /// absence — unless the inspected slot already carries it, or the
    /// headline's own selected readout does.
    static func keyNote(_ series: FieldHistorySeries10868, in input: FieldHistoryInput10868) -> String? {
        if let words = absentWords(series, in: input) { return words }
        if case .beforeAndInspected = input.readout { return nil }
        if input.selectedReadout != nil { return nil }
        return inspectedAbsentWords(series, in: input)
    }

    /// The owner's key context, only with visible words.
    static func keyContext(_ series: FieldHistorySeries10868) -> FieldHistoryKeyContext10868? {
        guard let context = series.keyContext, context.words.contains(where: { !$0.isWhitespace }) else { return nil }
        return context
    }

    static func spokenKeyContext(_ context: FieldHistoryKeyContext10868) -> String {
        context.spoken ?? "\(context.label): \(context.words)"
    }

    /// The ring's shape: the owner's when supplied, otherwise the original's own.
    static func inspectionRingShape(_ series: FieldHistorySeries10868,
                                    in input: FieldHistoryInput10868) -> FieldHistoryShape10868 {
        input.inspectionRingShape ?? series.shape
    }

    /// A choice hands back its id only when nonempty and unique among choices.
    static func liveChoiceID(_ choice: FieldHistoryInspectionChoice10868,
                             among choices: [FieldHistoryInspectionChoice10868]) -> String? {
        guard !choice.id.isEmpty, choices.filter({ $0.id == choice.id }).count == 1 else { return nil }
        return choice.id
    }

    /// The slider's position: offered only with two or more choices and
    /// exactly one owner-selected choice. No default to the first.
    static func sliderIndex(_ choices: [FieldHistoryInspectionChoice10868]) -> Int? {
        guard choices.count >= 2 else { return nil }
        let selected = choices.indices.filter { choices[$0].isSelected }
        return selected.count == 1 ? selected[0] : nil
    }

    /// The id a slider position hands back: a different, live choice.
    static func sliderChoiceID(at rawIndex: Double,
                               choices: [FieldHistoryInspectionChoice10868]) -> String? {
        guard rawIndex.isFinite, let current = sliderIndex(choices) else { return nil }
        let index = Int(rawIndex.rounded())
        guard choices.indices.contains(index), index != current else { return nil }
        return liveChoiceID(choices[index], among: choices)
    }

    // MARK: Spoken

    /// The plot's accessibility value: the inspection caption, each exactly
    /// identified original's owner words there, then undrawn originals' own
    /// absence words. Nothing is borrowed between originals.
    static func spokenValue(_ input: FieldHistoryInput10868) -> String {
        var parts: [String] = []
        if let inspection = input.inspection {
            parts.append(inspection.caption)
            for series in input.series {
                if inspectedPoint(series, in: input) != nil,
                   case .point(_, let spoken)? = inspection.selections[series.id] {
                    parts.append("\(series.name): \(spoken)")
                } else if let words = inspectedAbsentWords(series, in: input) {
                    parts.append("\(series.name): \(words)")
                }
            }
        }
        for series in input.series {
            if let words = absentWords(series, in: input) {
                parts.append("\(series.name): \(words)")
            }
        }
        return parts.joined(separator: "; ")
    }

    static func spokenSlot(_ slot: FieldHistoryReadoutSlot10868) -> String {
        switch slot.display {
        case .figure(let figure, let provenance):
            return "\(slot.label) \(figure), \(provenance)"
        case .words(let words):
            return "\(slot.label): \(words)"
        }
    }

    // MARK: Coordinates

    /// The frame marks may be centred in: the plot inset by the largest mark,
    /// so a mark at either probability boundary is never cut.
    static func drawingRect(in size: CGSize, inset: CGFloat) -> CGRect {
        CGRect(x: inset, y: inset,
               width: max(0, size.width - 2 * inset),
               height: max(0, size.height - 2 * inset))
    }

    static func fraction(_ x: Double, in domain: FieldHistoryDomain10868) -> Double {
        (x - domain.lower) / (domain.upper - domain.lower)
    }

    static func xPosition(_ x: Double, domain: FieldHistoryDomain10868, in rect: CGRect) -> CGFloat {
        rect.minX + CGFloat(fraction(x, in: domain)) * rect.width
    }

    /// Placement inside an already validated owner range. The original
    /// probability remains unchanged; all y consumers share this coordinate.
    static func probabilityFraction(_ probability: Double, lower: Double = 0, ceiling: Double) -> Double {
        (probability - lower) / (ceiling - lower)
    }

    static func yPosition(_ probability: Double, ceiling: Double, lower: Double = 0, in rect: CGRect) -> CGFloat {
        rect.maxY - CGFloat(probabilityFraction(probability, lower: lower, ceiling: ceiling)) * rect.height
    }

    static func position(_ point: FieldHistoryPoint10868,
                         in input: FieldHistoryInput10868,
                         rect: CGRect) -> CGPoint {
        CGPoint(x: xPosition(point.x, domain: input.domain, in: rect),
                y: yPosition(point.probability, ceiling: input.ceiling, lower: input.probabilityLowerBound, in: rect))
    }

    /// The domain position under a horizontal plot coordinate, for the host to
    /// resolve. Nothing outside the drawing frame or an invalid domain.
    static func domainValue(atX location: CGFloat,
                            domain: FieldHistoryDomain10868,
                            in rect: CGRect) -> Double? {
        guard domain.isValid, location.isFinite, rect.width > 0,
              location >= rect.minX, location <= rect.maxX else { return nil }
        return domain.lower + Double((location - rect.minX) / rect.width) * (domain.upper - domain.lower)
    }

    /// A break's band, clipped to the domain, as domain values.
    static func visibleBreak(_ item: FieldHistoryBreak10868,
                             domain: FieldHistoryDomain10868) -> ClosedRange<Double>? {
        guard domain.isValid, item.isValid else { return nil }
        let lower = max(item.lower, domain.lower), upper = min(item.upper, domain.upper)
        return lower < upper ? lower...upper : nil
    }

    // MARK: Ticks, guides and break marks

    static func placedYTicks(_ input: FieldHistoryInput10868) -> [FieldHistoryTick10868] {
        guard isDrawable(input) else { return [] }
        return input.yTicks.filter { $0.value.isFinite && $0.value >= input.probabilityLowerBound && $0.value <= input.ceiling }
    }

    static func placedXTicks(_ input: FieldHistoryInput10868) -> [FieldHistoryTick10868] {
        guard isDrawable(input) else { return [] }
        return input.xTicks.filter { input.domain.contains($0.value) }
    }

    static func placedGuides(_ input: FieldHistoryInput10868) -> [FieldHistoryGuide10868] {
        guard isDrawable(input) else { return [] }
        return input.guides.filter { input.domain.contains($0.x) }
    }

    /// Each visible break's mark, as a label at the band's middle.
    static func breakMarks(_ input: FieldHistoryInput10868) -> [FieldHistoryTick10868] {
        guard isDrawable(input) else { return [] }
        return input.breaks.compactMap { item in
            visibleBreak(item, domain: input.domain).map {
                FieldHistoryTick10868(value: ($0.lowerBound + $0.upperBound) / 2, lines: [item.mark])
            }
        }
    }

    // MARK: Mark paths

    /// One mark in its original's shape, `radius` from its centre (the
    /// square's half-side is 0.85× and the diamond's half-diagonal 1.2×, as
    /// approved).
    static func markPath(_ shape: FieldHistoryShape10868, at center: CGPoint, radius: CGFloat) -> Path {
        switch shape {
        case .circle:
            return Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius,
                                          width: radius * 2, height: radius * 2))
        case .square:
            let half = radius * 0.85
            return Path(CGRect(x: center.x - half, y: center.y - half, width: half * 2, height: half * 2))
        case .diamond:
            let r = radius * 1.2
            var path = Path()
            path.move(to: CGPoint(x: center.x, y: center.y - r))
            path.addLine(to: CGPoint(x: center.x + r, y: center.y))
            path.addLine(to: CGPoint(x: center.x, y: center.y + r))
            path.addLine(to: CGPoint(x: center.x - r, y: center.y))
            path.closeSubpath()
            return path
        case .triangle:
            // The same upright identity is used for the line's observations,
            // inspection ring and named key. Keep the approved proportions.
            var path = Path()
            path.move(to: CGPoint(x: center.x, y: center.y - radius * 1.25))
            path.addLine(to: CGPoint(x: center.x + radius * 1.1, y: center.y + radius))
            path.addLine(to: CGPoint(x: center.x - radius * 1.1, y: center.y + radius))
            path.closeSubpath()
            return path
        }
    }

    // MARK: Label lanes

    /// Places labels along one axis: each centred on `centers`, slid inward
    /// to stay inside `extent`, and moved to the first lane where it keeps
    /// `gap` clear of every label already there. Nothing is dropped.
    static func labelSlots(centers: [CGFloat], lengths: [CGFloat],
                           extent: CGFloat, gap: CGFloat) -> [FieldHistoryLabelSlot10868] {
        let extent = max(0, extent.isFinite ? extent : 0)
        let gap = max(0, gap)
        var lanes: [[ClosedRange<CGFloat>]] = []
        var slots: [FieldHistoryLabelSlot10868] = []
        for (center, rawLength) in zip(centers, lengths) {
            let length = min(max(0, rawLength.isFinite ? rawLength : 0), extent)
            let middle = center.isFinite ? center : 0
            let start = min(max(0, middle - length / 2), extent - length)
            let clearance = (start - gap)...(start + length + gap)
            let lane = lanes.firstIndex { taken in !taken.contains { $0.overlaps(clearance) } } ?? lanes.count
            if lane == lanes.count { lanes.append([]) }
            lanes[lane].append(start...(start + length))
            slots.append(FieldHistoryLabelSlot10868(start: start, lane: lane))
        }
        return slots
    }

    /// Direct endpoint labels stacked in the order of their points: each as
    /// close to centred on its point as the others allow, none overlapping,
    /// all inside `extent`. Nil when they cannot all fit at full size — the
    /// names then live only in the key.
    static func directLabelTops(centers: [CGFloat], heights: [CGFloat],
                                extent: CGFloat, gap: CGFloat) -> [CGFloat]? {
        let count = min(centers.count, heights.count)
        guard count > 0 else { return [] }
        let centers = Array(centers.prefix(count)), heights = Array(heights.prefix(count))
        guard extent.isFinite, extent > 0, gap.isFinite, gap >= 0,
              centers.allSatisfy(\.isFinite), heights.allSatisfy({ $0.isFinite && $0 >= 0 }) else { return nil }
        let total = heights.reduce(0, +) + gap * CGFloat(count - 1)
        guard total <= extent else { return nil }
        let order = centers.indices.sorted { centers[$0] < centers[$1] || (centers[$0] == centers[$1] && $0 < $1) }
        var tops = Array(repeating: CGFloat(0), count: count)
        var nextTop: CGFloat = 0
        for index in order {
            let desired = min(max(0, centers[index] - heights[index] / 2), extent - heights[index])
            tops[index] = max(nextTop, desired)
            nextTop = tops[index] + heights[index] + gap
        }
        var limit = extent
        for index in order.reversed() {
            tops[index] = min(tops[index], limit - heights[index])
            limit = tops[index] - gap
        }
        return tops
    }

    // MARK: Arrangement

    /// The whole measured plot at one width. Percentage labels take a gutter
    /// as wide as they measure; guide labels sit in a band above the plot and
    /// calendar/break labels in rows below (an extra lane only if two would
    /// touch). Direct labels take a column right of the plot only when every
    /// labelled name fits there at full size beside its point, the column
    /// stays within its share of the width and the plot keeps its minimum
    /// width; otherwise the plot takes the whole width and the key carries
    /// the names. The plot always keeps the owner's height.
    static func plotArrangement(width rawWidth: CGFloat, plotHeight owner: CGFloat,
                                inset: CGFloat, markClearance: CGFloat,
                                yFractions: [Double], ySizes: [CGSize],
                                xFractions: [Double], xSizes: [CGSize],
                                guideFractions: [Double], guideSizes: [CGSize],
                                labelTargets: [FieldHistoryLabelTarget10868], labelNaturalSizes: [CGSize],
                                labelHeights: (CGFloat) -> [CGFloat],
                                metrics m: FieldHistoryPlotMetrics10868 = FieldHistoryPlotMetrics10868())
        -> FieldHistoryPlotArrangement10868 {
        let width = max(0, rawWidth.isFinite ? rawWidth : 0)
        let height = plotHeight(owner)
        let ySpan = max(0, height - 2 * inset)

        // Percentage gutter.
        let yCount = min(yFractions.count, ySizes.count)
        let ySizes = Array(ySizes.prefix(yCount))
        let yCenters = yFractions.prefix(yCount).map { inset + CGFloat(1 - $0) * ySpan }
        let ySlots = labelSlots(centers: Array(yCenters), lengths: ySizes.map(\.height), extent: height, gap: 2)
        let columns = (ySlots.map(\.lane).max() ?? -1) + 1
        var columnWidths = Array(repeating: CGFloat(0), count: columns)
        for (slot, size) in zip(ySlots, ySizes) {
            columnWidths[slot.lane] = max(columnWidths[slot.lane], size.width)
        }
        let gutter = min(width, columns == 0 ? 0 : columnWidths.reduce(0, +) + CGFloat(columns) * m.labelGap)
        let available = max(0, width - gutter)

        // Direct labels, all or none.
        let labelCount = min(labelTargets.count, labelNaturalSizes.count)
        var labelColumn: CGFloat = 0
        var labelTops: [CGFloat] = []
        var labelSizes: [CGFloat] = []
        if labelCount > 0 {
            let natural = labelNaturalSizes.prefix(labelCount)
                .map { $0.width.isFinite ? max(0, $0.width) : 0 }.max() ?? 0
            let candidate = min(natural, (available * m.maximumLabelColumnFraction).rounded(.down))
            let heights = candidate > 0 ? labelHeights(candidate) : []
            if candidate > 0, available - m.leaderGap - candidate >= m.minimumPlotWidth, heights.count >= labelCount {
                let centers = labelTargets.prefix(labelCount).map { inset + CGFloat(1 - $0.yFraction) * ySpan }
                if let tops = directLabelTops(centers: Array(centers), heights: Array(heights.prefix(labelCount)),
                                              extent: height, gap: m.directLabelGap) {
                    labelColumn = candidate
                    labelTops = tops
                    labelSizes = Array(heights.prefix(labelCount))
                }
            }
        }
        let plotWidth = labelColumn > 0 ? available - m.leaderGap - labelColumn : available
        let xSpan = max(0, plotWidth - 2 * inset)

        // Guide band above the plot.
        let guideCount = min(guideFractions.count, guideSizes.count)
        let guideSizes = Array(guideSizes.prefix(guideCount))
        let guideCenters = zip(guideFractions.prefix(guideCount), guideSizes).map { fraction, size in
            inset + CGFloat(fraction) * xSpan + 3 + size.width / 2
        }
        let guideSlots = labelSlots(centers: guideCenters, lengths: guideSizes.map(\.width),
                                    extent: plotWidth, gap: m.labelGap)
        let guideRows = (guideSlots.map(\.lane).max() ?? -1) + 1
        var guideRowHeights = Array(repeating: CGFloat(0), count: guideRows)
        for (slot, size) in zip(guideSlots, guideSizes) {
            guideRowHeights[slot.lane] = max(guideRowHeights[slot.lane], size.height)
        }
        var guideRowTops: [CGFloat] = []
        var bandCursor: CGFloat = 0
        for row in 0..<guideRows {
            guideRowTops.append(bandCursor)
            bandCursor += guideRowHeights[row] + m.laneSpacing
        }
        let band = guideRows == 0 ? 0 : bandCursor - m.laneSpacing + m.axisGap

        let plot = CGRect(x: gutter, y: band, width: plotWidth, height: height)
        var trailingEdges: [CGFloat] = []
        var edge = gutter - m.labelGap
        for lane in 0..<columns {
            trailingEdges.append(edge)
            edge -= columnWidths[lane] + m.labelGap
        }
        let yFrames = zip(ySlots, ySizes).map { slot, size in
            CGRect(x: trailingEdges[slot.lane] - size.width, y: band + slot.start,
                   width: size.width, height: size.height)
        }
        let guideFrames = zip(guideSlots, guideSizes).map { slot, size in
            CGRect(x: plot.minX + slot.start, y: guideRowTops[slot.lane],
                   width: min(size.width, plotWidth), height: size.height)
        }

        // Calendar and break-mark rows below the plot.
        let xCount = min(xFractions.count, xSizes.count)
        let xSizes = Array(xSizes.prefix(xCount))
        let xCenters = xFractions.prefix(xCount).map { plot.minX + inset + CGFloat($0) * xSpan }
        let xSlots = labelSlots(centers: Array(xCenters), lengths: xSizes.map(\.width), extent: width, gap: m.labelGap)
        let xRows = (xSlots.map(\.lane).max() ?? -1) + 1
        var xRowHeights = Array(repeating: CGFloat(0), count: xRows)
        for (slot, size) in zip(xSlots, xSizes) {
            xRowHeights[slot.lane] = max(xRowHeights[slot.lane], size.height)
        }
        var xRowTops: [CGFloat] = []
        var top = plot.maxY + m.axisGap
        for row in 0..<xRows {
            xRowTops.append(top)
            top += xRowHeights[row] + m.laneSpacing
        }
        let xFrames = zip(xSlots, xSizes).map { slot, size in
            CGRect(x: slot.start, y: xRowTops[slot.lane], width: min(size.width, width), height: size.height)
        }

        // Direct label frames and their leaders.
        var labelFrames: [CGRect] = []
        var leaders: [FieldHistoryLeaderGeometry10868] = []
        if labelColumn > 0 {
            for index in 0..<labelCount {
                let frame = CGRect(x: plot.maxX + m.leaderGap, y: band + labelTops[index],
                                   width: labelColumn, height: labelSizes[index])
                let target = labelTargets[index]
                let start = CGPoint(x: plot.minX + inset + CGFloat(target.xFraction) * xSpan + markClearance,
                                    y: plot.minY + inset + CGFloat(1 - target.yFraction) * ySpan)
                let end = CGPoint(x: frame.minX - 2, y: frame.midY)
                labelFrames.append(frame)
                leaders.append(FieldHistoryLeaderGeometry10868(
                    frame: CGRect(x: min(start.x, end.x), y: min(start.y, end.y),
                                  width: abs(end.x - start.x), height: abs(end.y - start.y)),
                    rising: end.y < start.y
                ))
            }
        }

        return FieldHistoryPlotArrangement10868(
            plot: plot,
            yLabels: yFrames,
            xLabels: xFrames,
            guideLabels: guideFrames,
            directLabels: labelFrames,
            leaders: leaders,
            yColumns: columns,
            xRows: xRows,
            guideRows: guideRows,
            height: xRows == 0 ? plot.maxY : top - m.laneSpacing
        )
    }

    /// Key columns: equal columns of at least `minimum`, one column at
    /// accessibility sizes. Never more columns than entries.
    static func keyColumns(width: CGFloat, minimum: CGFloat, spacing: CGFloat,
                           count: Int, singleColumn: Bool) -> Int {
        guard count > 0 else { return 1 }
        guard !singleColumn, width.isFinite, minimum.isFinite, minimum > 0 else { return 1 }
        let fit = Int(((width + spacing) / (minimum + spacing)).rounded(.down))
        return max(1, min(count, fit))
    }
}

// MARK: - Layouts

/// Subviews, in order: the plot canvas; one label per placed percentage tick;
/// one per calendar tick and break mark; one per guide; one direct label per
/// labelled original; then two leaders per labelled original (falling, then
/// rising). Frames come from ``FieldHistoryGeometry10868/plotArrangement``.
/// A direct label or leader that is not used is given no size, so nothing of
/// it draws.
struct FieldHistoryPlotLayout10868: Layout {
    let yFractions: [Double]
    let xFractions: [Double]
    let guideFractions: [Double]
    let labelTargets: [FieldHistoryLabelTarget10868]
    let plotHeight: CGFloat
    let inset: CGFloat
    let markClearance: CGFloat

    private struct Counts {
        let y: Int, x: Int, guides: Int, labels: Int
        var yBase: Int { 1 }
        var xBase: Int { yBase + y }
        var guideBase: Int { xBase + x }
        var labelBase: Int { guideBase + guides }
        var leaderBase: Int { labelBase + labels }
    }

    private func counts(_ subviews: Subviews) -> Counts {
        var remaining = max(0, subviews.count - 1)
        let y = min(yFractions.count, remaining); remaining -= y
        let x = min(xFractions.count, remaining); remaining -= x
        let guides = min(guideFractions.count, remaining); remaining -= guides
        let labels = min(labelTargets.count, remaining / 3)
        return Counts(y: y, x: x, guides: guides, labels: labels)
    }

    private func arrangement(width: CGFloat, subviews: Subviews) -> FieldHistoryPlotArrangement10868 {
        let c = counts(subviews)
        func size(_ index: Int) -> CGSize {
            let ideal = subviews[index].sizeThatFits(.unspecified)
            guard ideal.width > width else { return ideal }
            return subviews[index].sizeThatFits(ProposedViewSize(width: width, height: nil))
        }
        return FieldHistoryGeometry10868.plotArrangement(
            width: width,
            plotHeight: plotHeight,
            inset: inset,
            markClearance: markClearance,
            yFractions: Array(yFractions.prefix(c.y)),
            ySizes: (0..<c.y).map { size(c.yBase + $0) },
            xFractions: Array(xFractions.prefix(c.x)),
            xSizes: (0..<c.x).map { size(c.xBase + $0) },
            guideFractions: Array(guideFractions.prefix(c.guides)),
            guideSizes: (0..<c.guides).map { size(c.guideBase + $0) },
            labelTargets: Array(labelTargets.prefix(c.labels)),
            labelNaturalSizes: (0..<c.labels).map { subviews[c.labelBase + $0].sizeThatFits(.unspecified) },
            labelHeights: { column in
                (0..<c.labels).map {
                    subviews[c.labelBase + $0].sizeThatFits(ProposedViewSize(width: column, height: nil)).height
                }
            }
        )
    }

    private static func width(_ proposal: ProposedViewSize) -> CGFloat {
        guard let width = proposal.width, width.isFinite else { return 0 }
        return width
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = Self.width(proposal)
        return CGSize(width: width, height: arrangement(width: width, subviews: subviews).height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let c = counts(subviews)
        let a = arrangement(width: bounds.width, subviews: subviews)
        func place(_ index: Int, _ frame: CGRect) {
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                  proposal: ProposedViewSize(frame.size))
        }
        func collapse(_ index: Int) {
            subviews[index].place(at: bounds.origin, proposal: .zero)
        }
        place(0, a.plot)
        for (offset, frame) in a.yLabels.enumerated() { place(c.yBase + offset, frame) }
        for (offset, frame) in a.xLabels.enumerated() { place(c.xBase + offset, frame) }
        for (offset, frame) in a.guideLabels.enumerated() { place(c.guideBase + offset, frame) }
        for index in 0..<c.labels {
            let falling = c.leaderBase + 2 * index, rising = falling + 1
            if a.usesDirectLabels, index < a.directLabels.count, index < a.leaders.count {
                place(c.labelBase + index, a.directLabels[index])
                let leader = a.leaders[index]
                place(leader.rising ? rising : falling, leader.frame)
                collapse(leader.rising ? falling : rising)
            } else {
                collapse(c.labelBase + index)
                collapse(falling)
                collapse(rising)
            }
        }
        for index in (c.leaderBase + 2 * c.labels)..<subviews.count { collapse(index) }
    }
}

/// Equal key columns; each row as tall as its tallest entry.
struct FieldHistoryKeyGridLayout10868: Layout {
    let minimumColumnWidth: CGFloat
    let singleColumn: Bool
    var spacing: CGFloat = 10

    private func columns(_ width: CGFloat, count: Int) -> Int {
        FieldHistoryGeometry10868.keyColumns(width: width, minimum: minimumColumnWidth, spacing: spacing,
                                             count: count, singleColumn: singleColumn)
    }

    private func rows(width: CGFloat, subviews: Subviews) -> (columnWidth: CGFloat, heights: [CGFloat], columns: Int) {
        let columns = columns(width, count: subviews.count)
        let columnWidth = max(0, (width - spacing * CGFloat(columns - 1)) / CGFloat(columns))
        var heights: [CGFloat] = []
        var index = 0
        while index < subviews.count {
            let row = subviews[index..<min(subviews.count, index + columns)]
            heights.append(row.map { $0.sizeThatFits(ProposedViewSize(width: columnWidth, height: nil)).height }.max() ?? 0)
            index += columns
        }
        return (columnWidth, heights, columns)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? 0
        let r = rows(width: width, subviews: subviews)
        let height = r.heights.reduce(0, +) + spacing * CGFloat(max(0, r.heights.count - 1))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let r = rows(width: bounds.width, subviews: subviews)
        var y = bounds.minY
        for (row, height) in r.heights.enumerated() {
            for column in 0..<r.columns {
                let index = row * r.columns + column
                guard index < subviews.count else { break }
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(column) * (r.columnWidth + spacing), y: y),
                    proposal: ProposedViewSize(width: r.columnWidth, height: height)
                )
            }
            y += height + spacing
        }
    }
}

// MARK: - View

struct FieldProbabilityHistoryPresentation10868: View {
    let input: FieldHistoryInput10868
    /// Hands back the exact id of the owner action the reader chose.
    var onAction: ((String) -> Void)? = nil
    /// Hands back the exact id of the inspection choice the reader chose.
    var onInspectionChoice: ((String) -> Void)? = nil
    /// Reports the domain position under a tap for the host to resolve.
    var onPlotPosition: ((Double) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    /// A plain mark's radius; the inspected ring is twice this.
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 3.5
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .subheadline) private var keyColumnWidth: CGFloat = 150

    private var inset: CGFloat { markRadius * 2 + 1.5 }
    private var drawable: Bool { FieldHistoryGeometry10868.isDrawable(input) }
    private var yTicks: [FieldHistoryTick10868] { FieldHistoryGeometry10868.placedYTicks(input) }
    /// Calendar ticks, then break marks: one row band under the plot.
    private var xLabels: [FieldHistoryTick10868] {
        FieldHistoryGeometry10868.placedXTicks(input) + FieldHistoryGeometry10868.breakMarks(input)
    }
    private var guides: [FieldHistoryGuide10868] { FieldHistoryGeometry10868.placedGuides(input) }
    private var labelled: [(FieldHistorySeries10868, FieldHistoryPoint10868)] {
        FieldHistoryGeometry10868.labelledSeries(input)
    }

    private func state(_ action: FieldHistoryAction10868?, informative: Bool) -> FieldHistoryControlState10868 {
        FieldHistoryGeometry10868.controlState(action, informative: informative,
                                               hasCallback: onAction != nil, in: input)
    }

    private func chartState(_ action: FieldHistoryAction10868?, informative: Bool) -> FieldHistoryControlState10868 {
        FieldHistoryGeometry10868.chartControlState(action, informative: informative,
                                                    hasCallback: onAction != nil, in: input)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            headerControls
            windowLine
            readoutBlocks(FieldHistoryGeometry10868.blocksAbovePlot(input))
            if let absence = FieldHistoryGeometry10868.plotAbsence(input) {
                FieldHistoryPlotAbsenceView10868(absence: absence)
            } else {
                if let explanation = FieldHistoryGeometry10868.probabilityRangeExplanation(input) {
                    Text(explanation)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                plot
            }
            readoutBlocks(FieldHistoryGeometry10868.blocksBelowPlot(input))
            markKey
            inspectionBlock
            ForEach(Array(input.notes.enumerated()), id: \.offset) { _, note in
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            FieldHistoryActionButton10868(action: input.details, state: state(input.details, informative: false),
                                          minHeight: controlSize, style: .text, onAction: onAction)
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.title)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let caption = input.caption {
                    Text(caption)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            FieldHistoryActionButton10868(action: input.expand, state: chartState(input.expand, informative: false),
                                          minHeight: controlSize,
                                          style: .icon("arrow.up.left.and.arrow.down.right"), onAction: onAction)
        }
    }

    @ViewBuilder
    private var headerControls: some View {
        let scale = chartState(input.scale, informative: true)
        let more = state(input.moreOriginals, informative: false)
        if scale != .hidden || more != .hidden {
            FlowLayout(spacing: 8) {
                FieldHistoryActionButton10868(action: input.scale, state: scale, minHeight: controlSize,
                                              style: .chip(selected: false), onAction: onAction)
                FieldHistoryActionButton10868(action: input.moreOriginals, state: more, minHeight: controlSize,
                                              style: .chip(selected: false), onAction: onAction)
            }
        }
    }

    @ViewBuilder
    private var windowLine: some View {
        if let windows = FieldHistoryGeometry10868.shownWindows(input), !windows.choices.isEmpty {
            FlowLayout(spacing: 6) {
                ForEach(Array(windows.choices.enumerated()), id: \.offset) { _, choice in
                    FieldHistoryActionButton10868(action: choice.action,
                                                  state: state(choice.action, informative: true),
                                                  minHeight: controlSize,
                                                  style: .chip(selected: choice.isSelected), onAction: onAction)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(windows.groupLabel)
        }
    }

    // MARK: Plot

    private var plot: some View {
        FieldHistoryPlotLayout10868(
            yFractions: yTicks.map { FieldHistoryGeometry10868.probabilityFraction($0.value, lower: input.probabilityLowerBound, ceiling: input.ceiling) },
            xFractions: xLabels.map { FieldHistoryGeometry10868.fraction($0.value, in: input.domain) },
            guideFractions: guides.map { FieldHistoryGeometry10868.fraction($0.x, in: input.domain) },
            labelTargets: labelled.map { FieldHistoryGeometry10868.labelTarget($0.1, in: input) },
            plotHeight: FieldHistoryGeometry10868.plotHeight(input.plotHeight),
            inset: inset,
            markClearance: markRadius * 1.6
        ) {
            canvas
            ForEach(Array(yTicks.enumerated()), id: \.offset) { _, tick in
                FieldHistoryTickLabel10868(lines: tick.lines, alignment: .trailing)
            }
            ForEach(Array(xLabels.enumerated()), id: \.offset) { _, tick in
                FieldHistoryTickLabel10868(lines: tick.lines, alignment: .center)
            }
            ForEach(Array(guides.enumerated()), id: \.offset) { _, guide in
                FieldHistoryTickLabel10868(lines: [guide.label], alignment: .leading)
            }
            ForEach(Array(labelled.enumerated()), id: \.offset) { _, item in
                FieldHistoryDirectLabel10868(name: item.0.name)
            }
            ForEach(Array(labelled.enumerated()), id: \.offset) { _, item in
                FieldHistoryLeaderShape10868(rising: false).stroke(item.0.tint, lineWidth: 1)
                FieldHistoryLeaderShape10868(rising: true).stroke(item.0.tint, lineWidth: 1)
            }
        }
        .overlay {
            if !drawable, let words = input.plotUnavailableWords {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 12)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.summary)
        .accessibilityValue(FieldHistoryGeometry10868.spokenValue(input))
        .accessibilityAddTraits(.isImage)
        .modifier(FieldHistoryAdjustable10868(
            previous: FieldHistoryGeometry10868.adjustableID(input.previous, hasCallback: onAction != nil, in: input),
            next: FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: onAction != nil, in: input),
            onAction: onAction
        ))
    }

    private var canvas: some View {
        GeometryReader { proxy in
            let drawing = Canvas { context, size in
                draw(in: &context, size: size)
            }
            if let onPlotPosition {
                drawing
                    .contentShape(Rectangle())
                    .onTapGesture(coordinateSpace: .local) { location in
                        let rect = FieldHistoryGeometry10868.drawingRect(in: proxy.size, inset: inset)
                        if let value = FieldHistoryGeometry10868.domainValue(
                            atX: location.x, domain: input.domain, in: rect
                        ) {
                            onPlotPosition(value)
                        }
                    }
            } else {
                drawing.allowsHitTesting(false)
            }
        }
    }

    private func draw(in context: inout GraphicsContext, size: CGSize) {
        guard drawable else { return }
        let rect = FieldHistoryGeometry10868.drawingRect(in: size, inset: inset)
        let domain = input.domain

        for item in input.breaks {
            guard let band = FieldHistoryGeometry10868.visibleBreak(item, domain: domain) else { continue }
            let left = FieldHistoryGeometry10868.xPosition(band.lowerBound, domain: domain, in: rect)
            let right = FieldHistoryGeometry10868.xPosition(band.upperBound, domain: domain, in: rect)
            context.fill(Path(CGRect(x: left, y: 0, width: right - left, height: size.height)),
                         with: .color(DS.trackBg))
        }

        for tick in yTicks {
            let y = FieldHistoryGeometry10868.yPosition(tick.value, ceiling: input.ceiling, lower: input.probabilityLowerBound, in: rect)
            var grid = Path()
            grid.move(to: CGPoint(x: 0, y: y))
            grid.addLine(to: CGPoint(x: size.width, y: y))
            context.stroke(grid, with: .color(DS.border), lineWidth: 1)
        }

        for guide in guides {
            let x = FieldHistoryGeometry10868.xPosition(guide.x, domain: domain, in: rect)
            var line = Path()
            line.move(to: CGPoint(x: x, y: 0))
            line.addLine(to: CGPoint(x: x, y: size.height))
            context.stroke(line, with: .color(DS.textMuted), style: StrokeStyle(lineWidth: 1, dash: [2, 5]))
        }

        if let x = FieldHistoryGeometry10868.cursor(input) {
            let cx = FieldHistoryGeometry10868.xPosition(x, domain: domain, in: rect)
            var cursor = Path()
            cursor.move(to: CGPoint(x: cx, y: 0))
            cursor.addLine(to: CGPoint(x: cx, y: size.height))
            context.stroke(cursor, with: .color(DS.textPrimary), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
        }

        let dashed = StrokeStyle(lineWidth: 1.8, lineCap: .round, dash: [3, 5])
        for series in input.series {
            for (from, to) in FieldHistoryGeometry10868.comparisonLinks(series, in: input) {
                var path = Path()
                path.move(to: FieldHistoryGeometry10868.position(from, in: input, rect: rect))
                path.addLine(to: FieldHistoryGeometry10868.position(to, in: input, rect: rect))
                context.stroke(path, with: .color(series.tint.opacity(0.65)), style: dashed)
            }
        }

        let solid = StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round)
        for series in input.series {
            for run in FieldHistoryGeometry10868.lines(series, in: input) {
                var path = Path()
                path.addLines(run.map { FieldHistoryGeometry10868.position($0, in: input, rect: rect) })
                context.stroke(path, with: .color(series.tint), style: solid)
            }
        }

        for series in input.series {
            for point in FieldHistoryGeometry10868.marks(series, in: input) {
                let center = FieldHistoryGeometry10868.position(point, in: input, rect: rect)
                let mark = FieldHistoryGeometry10868.markPath(series.shape, at: center, radius: markRadius)
                switch point.style {
                case .hollow:
                    context.fill(mark, with: .color(DS.cardBg))
                    context.stroke(mark, with: .color(series.tint), lineWidth: 1.5)
                case .filled:
                    context.fill(mark, with: .color(series.tint))
                }
            }
        }

        for series in input.series {
            guard let point = FieldHistoryGeometry10868.inspectedPoint(series, in: input) else { continue }
            let center = FieldHistoryGeometry10868.position(point, in: input, rect: rect)
            let ring = FieldHistoryGeometry10868.markPath(FieldHistoryGeometry10868.inspectionRingShape(series, in: input),
                                                          at: center, radius: markRadius * 2)
            context.stroke(ring, with: .color(series.tint), lineWidth: 2)
        }
    }

    // MARK: Readouts

    private func readoutBlocks(_ blocks: [FieldHistoryReadoutBlock10868]) -> some View {
        ForEach(blocks, id: \.self) { block in
            switch block {
            case .selectionWords:
                if let words = FieldHistoryGeometry10868.selectionWords(input) {
                    selectionText(words)
                }
            case .selectedSummary:
                selectedSummary
            case .key:
                key
            }
        }
    }

    private func selectionText(_ words: String) -> some View {
        Text(words)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var selectedSummary: some View {
        switch FieldHistoryGeometry10868.selectedSummary(input) {
        case .none:
            EmptyView()
        case .words(let words):
            selectionText(words)
        case .original(let series, let slots):
            FieldHistoryOriginalReadout10868(
                series: series,
                note: FieldHistoryGeometry10868.keyNote(series, in: input),
                slots: slots,
                stacksSlots: dynamicTypeSize.isAccessibilitySize,
                prominent: true,
                markRadius: markRadius
            )
            .accessibilityElement(children: .combine)
        }
    }

    private var key: some View {
        FieldHistoryKeyGridLayout10868(minimumColumnWidth: keyColumnWidth,
                                       singleColumn: dynamicTypeSize.isAccessibilitySize) {
            ForEach(Array(input.series.enumerated()), id: \.offset) { _, series in
                FieldHistoryKeyEntry10868(
                    series: series,
                    note: FieldHistoryGeometry10868.keyNote(series, in: input),
                    slots: FieldHistoryGeometry10868.readoutSlots(series, in: input),
                    context: FieldHistoryGeometry10868.keyContext(series),
                    isSelected: FieldHistoryGeometry10868.isSelected(series, in: input),
                    chooseState: FieldHistoryGeometry10868.chooseState(series, hasCallback: onAction != nil, in: input),
                    stacksSlots: dynamicTypeSize.isAccessibilitySize,
                    markRadius: markRadius,
                    onAction: onAction
                )
            }
        }
    }

    @ViewBuilder
    private var markKey: some View {
        let hollow = input.markKey.hollow.flatMap { FieldHistoryGeometry10868.drawsStyle(.hollow, in: input) ? $0 : nil }
        let filled = input.markKey.filled.flatMap { FieldHistoryGeometry10868.drawsStyle(.filled, in: input) ? $0 : nil }
        let links = FieldHistoryGeometry10868.comparisonKeyWords(input)
        if hollow != nil || filled != nil || links != nil {
            FlowLayout(spacing: 12) {
                if let hollow {
                    FieldHistoryGlyphEntry10868(glyph: .hollowMark, words: hollow, markRadius: markRadius)
                }
                if let filled {
                    FieldHistoryGlyphEntry10868(glyph: .filledMark, words: filled, markRadius: markRadius)
                }
                if let links {
                    FieldHistoryGlyphEntry10868(glyph: .dashedLink, words: links, markRadius: markRadius)
                }
            }
        }
    }

    // MARK: Inspection

    @ViewBuilder
    private var inspectionBlock: some View {
        let inspect = chartState(input.inspect, informative: false)
        let previous = chartState(input.previous, informative: false)
        let next = chartState(input.next, informative: false)
        if let inspection = FieldHistoryGeometry10868.shownInspection(input) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .center, spacing: 8) {
                    Text(inspection.caption)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    FieldHistoryActionButton10868(action: input.inspect, state: inspect, minHeight: controlSize,
                                                  style: .text, onAction: onAction)
                }
                choiceControls(inspection, previous: previous, next: next)
                if let note = inspection.note {
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(12)
            .background(RoundedRectangle(cornerRadius: 12).fill(DS.surface))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 1))
        } else {
            if previous != .hidden || next != .hidden {
                stepRow(previous: previous, next: next) { Spacer(minLength: 0) }
            }
            FieldHistoryActionButton10868(action: input.inspect, state: inspect, minHeight: controlSize,
                                          style: .text, onAction: onAction)
        }
    }

    @ViewBuilder
    private func choiceControls(_ inspection: FieldHistoryInspection10868,
                                previous: FieldHistoryControlState10868,
                                next: FieldHistoryControlState10868) -> some View {
        let choices = inspection.choices
        switch inspection.choicePresentation {
        case .slider(let label):
            if let index = FieldHistoryGeometry10868.sliderIndex(choices), let onInspectionChoice {
                stepRow(previous: previous, next: next) {
                    Slider(
                        value: Binding(
                            get: { Double(index) },
                            set: { value in
                                if let id = FieldHistoryGeometry10868.sliderChoiceID(at: value, choices: choices) {
                                    onInspectionChoice(id)
                                }
                            }
                        ),
                        in: 0...Double(choices.count - 1),
                        step: 1
                    )
                    .frame(minHeight: controlSize)
                    .accessibilityLabel(label)
                    .accessibilityValue(choices[index].spoken)
                }
            } else if previous != .hidden || next != .hidden {
                stepRow(previous: previous, next: next) { Spacer(minLength: 0) }
            }
        case .buttons(let groupLabel):
            if !choices.isEmpty {
                FlowLayout(spacing: 8) {
                    ForEach(Array(choices.enumerated()), id: \.offset) { _, choice in
                        FieldHistoryChoiceButton10868(
                            choice: choice,
                            minHeight: controlSize,
                            action: onInspectionChoice.flatMap { send in
                                FieldHistoryGeometry10868.liveChoiceID(choice, among: choices)
                                    .map { id -> () -> Void in { send(id) } }
                            }
                        )
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(groupLabel)
            }
            if previous != .hidden || next != .hidden {
                stepRow(previous: previous, next: next) { Spacer(minLength: 0) }
            }
        }
    }

    private func stepRow<Middle: View>(previous: FieldHistoryControlState10868,
                                       next: FieldHistoryControlState10868,
                                       @ViewBuilder middle: () -> Middle) -> some View {
        HStack(alignment: .center, spacing: 10) {
            FieldHistoryActionButton10868(action: input.previous, state: previous, minHeight: controlSize,
                                          style: .icon("chevron.left"), onAction: onAction)
            middle()
                .frame(maxWidth: .infinity)
            FieldHistoryActionButton10868(action: input.next, state: next, minHeight: controlSize,
                                          style: .icon("chevron.right"), onAction: onAction)
        }
    }
}

// MARK: - Private views

/// One tick or guide's words, line by line. Wraps only when offered less
/// than its whole width.
private struct FieldHistoryTickLabel10868: View {
    let lines: [String]
    let alignment: HorizontalAlignment

    var body: some View {
        VStack(alignment: alignment, spacing: 0) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(alignment == .trailing ? .trailing : alignment == .center ? .center : .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityHidden(true)
    }
}

/// A direct endpoint label: the full name, wrapping by words inside the
/// width it is given. Given no size it draws nothing.
private struct FieldHistoryDirectLabel10868: View {
    let name: String

    var body: some View {
        Text(name)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .topLeading)
            .clipped()
            .accessibilityHidden(true)
    }
}

/// A straight leader across its frame: corner to corner, falling or rising.
struct FieldHistoryLeaderShape10868: Shape {
    let rising: Bool

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rising ? rect.maxY : rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rising ? rect.minY : rect.maxY))
        return path
    }
}

/// An original's identity glyph: a short solid line through its mark.
private struct FieldHistoryIdentityGlyph10868: View {
    let shape: FieldHistoryShape10868
    let tint: Color
    let markRadius: CGFloat

    var body: some View {
        Canvas { context, size in
            let middle = CGPoint(x: size.width / 2, y: size.height / 2)
            var line = Path()
            line.move(to: CGPoint(x: 0, y: middle.y))
            line.addLine(to: CGPoint(x: size.width, y: middle.y))
            context.stroke(line, with: .color(tint), lineWidth: 2)
            let mark = FieldHistoryGeometry10868.markPath(shape, at: middle, radius: markRadius * 1.3)
            context.fill(mark, with: .color(tint))
        }
        .frame(width: markRadius * 7, height: markRadius * 4.5)
        .accessibilityHidden(true)
    }
}

/// One original in the key: identity glyph and full name, its own note, then
/// its readout slots at equal size, each with its own provenance, then the
/// owner's separate context.
private struct FieldHistoryKeyEntry10868: View {
    let series: FieldHistorySeries10868
    let note: String?
    let slots: [FieldHistoryReadoutSlot10868]
    let context: FieldHistoryKeyContext10868?
    let isSelected: Bool
    let chooseState: FieldHistoryControlState10868
    let stacksSlots: Bool
    let markRadius: CGFloat
    let onAction: ((String) -> Void)?

    var body: some View {
        if case .live(let id) = chooseState, let onAction, let choose = series.choose {
            Button { onAction(id) } label: { entry }
                .buttonStyle(.plain)
                .disabled(!choose.isAvailable)
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(isSelected ? .isSelected : [])
                .accessibilityHint(choose.spokenLabel ?? choose.label)
        } else {
            entry
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(isSelected ? .isSelected : [])
        }
    }

    private var entry: some View {
        VStack(alignment: .leading, spacing: 6) {
            FieldHistoryOriginalReadout10868(series: series, note: note, slots: slots, stacksSlots: stacksSlots,
                                             prominent: false, markRadius: markRadius)
            if let context {
                FieldHistoryKeyContextView10868(context: context)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 10).fill(isSelected ? DS.surface : Color.clear))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(isSelected ? DS.textSecondary : Color.clear, lineWidth: 1))
        .contentShape(Rectangle())
    }
}

/// One original's identity glyph and full name, its own note, then its
/// readout slots at equal size — in the key and in the focused headline.
private struct FieldHistoryOriginalReadout10868: View {
    let series: FieldHistorySeries10868
    let note: String?
    let slots: [FieldHistoryReadoutSlot10868]
    let stacksSlots: Bool
    /// The focused headline's larger name and figures.
    let prominent: Bool
    let markRadius: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 6) {
                FieldHistoryIdentityGlyph10868(shape: series.shape, tint: series.tint, markRadius: markRadius)
                Text(series.name)
                    .font(prominent ? Font.headline : Font.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let note {
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if stacksSlots || slots.count < 2 {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
                        FieldHistoryReadoutSlotView10868(slot: slot, prominent: prominent)
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 10) {
                    ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
                        FieldHistoryReadoutSlotView10868(slot: slot, prominent: prominent)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }
    }
}

/// One readout slot: label, figure (the same size in every slot) and its own
/// provenance; or the slot's own words.
private struct FieldHistoryReadoutSlotView10868: View {
    let slot: FieldHistoryReadoutSlot10868
    var prominent = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(slot.label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            switch slot.display {
            case .figure(let figure, let provenance):
                Text(figure)
                    .font((prominent ? Font.title2 : Font.title3).weight(.semibold).monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(provenance)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .words(let words):
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(FieldHistoryGeometry10868.spokenSlot(slot))
    }
}

/// The owner's explicit plot absence between hairlines: its title, then its
/// own words, wrapping at their natural height — never a placeholder plot.
private struct FieldHistoryPlotAbsenceView10868: View {
    let absence: FieldHistoryPlotAbsence10868

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(absence.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let words = FieldHistoryGeometry10868.absenceWords(absence) {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 14)
        .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1).accessibilityHidden(true) }
        .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1).accessibilityHidden(true) }
        .accessibilityElement(children: .combine)
    }
}

/// The owner's key context below a hairline, in secondary type with its own
/// spoken words — never a figure size, a tint or a slot.
private struct FieldHistoryKeyContextView10868: View {
    let context: FieldHistoryKeyContext10868

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Rectangle()
                .fill(DS.border)
                .frame(height: 1)
                .accessibilityHidden(true)
            Text(verbatim: "\(context.label) · \(context.words)")
                .font(.footnote.weight(.medium))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(FieldHistoryGeometry10868.spokenKeyContext(context))
    }
}

/// A mark-style or dashed-link key entry with the owner's words.
private struct FieldHistoryGlyphEntry10868: View {
    enum Glyph { case hollowMark, filledMark, dashedLink }

    let glyph: Glyph
    let words: String
    let markRadius: CGFloat

    var body: some View {
        HStack(alignment: .center, spacing: 6) {
            Canvas { context, size in
                let middle = CGPoint(x: size.width / 2, y: size.height / 2)
                switch glyph {
                case .hollowMark:
                    let mark = FieldHistoryGeometry10868.markPath(.circle, at: middle, radius: markRadius)
                    context.fill(mark, with: .color(DS.cardBg))
                    context.stroke(mark, with: .color(DS.textSecondary), lineWidth: 1.5)
                case .filledMark:
                    let mark = FieldHistoryGeometry10868.markPath(.circle, at: middle, radius: markRadius)
                    context.fill(mark, with: .color(DS.textSecondary))
                case .dashedLink:
                    var line = Path()
                    line.move(to: CGPoint(x: 0, y: middle.y))
                    line.addLine(to: CGPoint(x: size.width, y: middle.y))
                    context.stroke(line, with: .color(DS.textSecondary),
                                   style: StrokeStyle(lineWidth: 1.8, lineCap: .round, dash: [3, 5]))
                }
            }
            .frame(width: markRadius * 6, height: markRadius * 4)
            .accessibilityHidden(true)
            Text(words)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

/// One owner control in its state: a button handing back the exact id, the
/// same look without an action, or nothing.
private struct FieldHistoryActionButton10868: View {
    enum Style: Equatable {
        case chip(selected: Bool)
        case text
        case icon(String)
    }

    let action: FieldHistoryAction10868?
    let state: FieldHistoryControlState10868
    let minHeight: CGFloat
    let style: Style
    let onAction: ((String) -> Void)?

    var body: some View {
        if let action {
            switch state {
            case .hidden:
                EmptyView()
            case .live(let id):
                Button { onAction?(id) } label: { look(action) }
                    .buttonStyle(.plain)
                    .disabled(!action.isAvailable)
                    .opacity(action.isAvailable ? 1 : 0.4)
                    .accessibilityLabel(action.spokenLabel ?? action.label)
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
            case .shownStatic:
                look(action)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(action.spokenLabel ?? action.label)
                    .accessibilityAddTraits(isSelected ? [.isStaticText, .isSelected] : .isStaticText)
            }
        }
    }

    private var isSelected: Bool {
        if case .chip(let selected) = style { return selected }
        return false
    }

    @ViewBuilder
    private func look(_ action: FieldHistoryAction10868) -> some View {
        switch style {
        case .chip(let selected):
            Text(action.label)
                .font(.footnote.weight(selected ? .semibold : .regular))
                .foregroundStyle(selected ? DS.cardBg : DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 10)
                .frame(minHeight: minHeight)
                .background(RoundedRectangle(cornerRadius: 10).fill(selected ? DS.textPrimary : DS.cardBg))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(DS.border, lineWidth: 1))
                .contentShape(Rectangle())
        case .text:
            Text(action.label)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(DS.blue)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: minHeight)
                .contentShape(Rectangle())
        case .icon(let systemName):
            Image(systemName: systemName)
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .frame(minWidth: minHeight, minHeight: minHeight)
                .background(RoundedRectangle(cornerRadius: 10).fill(DS.cardBg))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(DS.border, lineWidth: 1))
                .contentShape(Rectangle())
        }
    }
}

/// One discrete inspection choice; with no action (no callback, or an id that
/// cannot name one choice) the same chip, static.
private struct FieldHistoryChoiceButton10868: View {
    let choice: FieldHistoryInspectionChoice10868
    let minHeight: CGFloat
    let action: (() -> Void)?

    var body: some View {
        if let action {
            Button(action: action) { chip }
                .buttonStyle(.plain)
                .accessibilityLabel(choice.spoken)
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        } else {
            chip
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(choice.spoken)
                .accessibilityAddTraits(choice.isSelected ? [.isStaticText, .isSelected] : .isStaticText)
        }
    }

    private var chip: some View {
        VStack(spacing: 0) {
            ForEach(Array(choice.lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.footnote)
                    .foregroundStyle(DS.textPrimary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(minHeight: minHeight)
        .background(RoundedRectangle(cornerRadius: 10).fill(choice.isSelected ? DS.surface : DS.cardBg))
        .overlay(RoundedRectangle(cornerRadius: 10)
            .stroke(choice.isSelected ? DS.textPrimary : DS.border, lineWidth: 1))
        .contentShape(Rectangle())
    }
}

/// VoiceOver's swipe up/down hands back the owner's next/previous id, only
/// while one of them is live and available.
private struct FieldHistoryAdjustable10868: ViewModifier {
    let previous: String?
    let next: String?
    let onAction: ((String) -> Void)?

    func body(content: Content) -> some View {
        if let onAction, previous != nil || next != nil {
            content.accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: if let next { onAction(next) }
                case .decrement: if let previous { onAction(previous) }
                @unknown default: break
                }
            }
        } else {
            content
        }
    }
}
