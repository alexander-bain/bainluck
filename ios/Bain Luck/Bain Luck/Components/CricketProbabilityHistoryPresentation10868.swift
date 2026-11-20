import SwiftUI

// #10868 — "Win probability": the cricket-live probability journey. Every
// original outcome contract the owner supplies is drawn as its own solid line
// on one common 0–100% chance scale, keyed by name, tint AND shape (circle,
// diamond, square), with hollow marks for the owner's explicitly admitted
// pregame observations and filled marks for every other observation.
//
// Every series is an independent original. Nothing here complements, inverts,
// stacks or normalizes a series, sums series into a distribution or lines up
// separately timed observations as one moment: a pregame set of 48%, 47% and
// 9% (104%) is drawn as exactly those three marks.
//
// Presentation only, extracted from the approved design: `CricketLive.tsx`
// `CricketHistory` + `cricketLive.css` (302 pt standard plot, solid lines,
// hollow pregame marks, 0/50/100% scale, two-line calendar ticks, ‹ › steps)
// as mounted by `CricketLifecycle.tsx` before and after play, with
// `HistoryTeamMark.tsx` for the three shapes. The prototype's model, clock,
// data loader, cutoff, trade admission, five-minute rule, replay windows,
// latest-observation default, domain padding and formatters are NOT ported.
//
// Owner-resolved, never derived here: which series exist and their order; the
// segments each series is drawn in (a gap between two segments is never
// bridged); which point is a pregame observation (never inferred from an
// equal price, an equal time, a scheduled start or array position); the plot
// domain; every axis tick and its words; the source/calendar context; the
// selected position, the exact selected point of each series and its words;
// the spoken summary. This layer never reads or converts a clock, never
// formats a percentage or a date, never picks the latest observation, never
// samples, caps or reorders series or points, never extends a line to "now",
// to a settlement or to a 0%/100% end, and holds no phase, currentness, gap,
// loading or settlement policy.
//
// Drawing rules: a point is placed only when its x lies inside the owner's
// domain and its probability is a finite value in 0...1. Real 0% is a value.
// Anything else draws nothing AND breaks the path there, so no line runs
// through, toward or clipped against a point that cannot be placed — the
// visible window never shows an interpolated value. A path also breaks where
// x does not advance. A run of one point is a mark with no line.
//
// Inspection is the host's: the dashed cursor, each series' emphasised mark
// and the caption are drawn only as supplied, by exact unique point id. A
// selection is attributed to a series only when that series' id is nonempty
// and names exactly one series of the input; two series sharing an id, or an
// empty id, keep their lines, marks, names and own absence words but draw,
// speak and note no inspection. A series whose id does not resolve, or that
// the owner marks absent, draws no selected mark and borrows nothing from a
// neighbour or another series. Previous/next/expand and window choices hand
// back the owner's actions only when both the action and a callback exist; a
// window choice whose id is empty or shared stays visible but static, so no
// action is sent for it. A tap on the plot reports the
// domain position under the finger for the host to resolve; nothing is
// snapped here. The view keeps no state, runs no animation and holds no
// subscription, and passive updates move no focus.
//
// Match-progress guides (T20 `T20Match.tsx` History + `t20Match.css`): an
// optional marker context, beside the unchanged input, carries the owner's
// phase and admitted markers — each a domain position in the plot's own unit,
// an emphasis (the labelled innings-report guide, or a subtle score-report
// guide), an optional visible label, complete spoken words and, for a marker
// the owner holds without a time, its absence words. Before play nothing of
// the context is drawn, shown or spoken, whatever later markers are supplied.
// During and after, only markers whose position lies inside the domain are
// drawn, as dashed verticals beneath the lines; their labels sit in measured
// rows above the plot, and the band grows instead of shrinking the plot. A
// guide never adds, moves or joins an observation, never rescales a chance,
// and never takes a tap: it is drawn in the plot's own Canvas, so the
// position callback and held inspection are exactly as before. This layer
// never parses a clock, score or over count, never chooses a nearest report,
// never infers an innings boundary or a finish, and never adds a marker. A
// report's publication time is the owner's word for what it is; it is never
// presented here as a ball, a trade, a finish or an app arrival.
//
// Host binding still owed — not available at this base. EventHistoryResponse
// carries paired home/away channels, not three independent originals, and
// OddsChartView/EvolutionChartView own their own fetch/selection/policy; an
// owner must supply proved original membership, qualified segmented
// observations, admitted pregame identity, domain and local-calendar words
// (CRICKET-HISTORY-BINDING-SOURCES.json "limits").

// MARK: - Input

/// A series' stable non-colour key, used on its line marks and in the key.
nonisolated enum CricketHistoryShape10868: Equatable, CaseIterable {
    case circle
    case diamond
    case square
}

/// One owner-admitted observation.
nonisolated struct CricketHistoryPoint10868: Equatable {
    /// The owner's opaque, stable point identity.
    let id: String
    /// The owner's position on the plot's horizontal domain (for example
    /// seconds since an epoch). Never read as a clock here.
    let x: Double
    /// 0...1. Anything else is not placed and breaks the path.
    let probability: Double
    /// True only for the owner's explicitly admitted pregame observation:
    /// drawn hollow.
    let isPregame: Bool
}

/// One explicitly separated stretch of observations. Two segments are never
/// joined, whatever their values or times.
nonisolated struct CricketHistorySegment10868: Equatable {
    let id: String
    /// In the owner's order.
    let points: [CricketHistoryPoint10868]
}

/// One original outcome contract's journey.
nonisolated struct CricketHistorySeries10868: Equatable {
    /// The owner's opaque, stable series identity.
    let id: String
    /// The full name, shown and spoken verbatim.
    let name: String
    let shape: CricketHistoryShape10868
    /// The owner's stable series tint for the line, marks and key.
    let tint: Color
    let segments: [CricketHistorySegment10868]
    /// The owner's words when this series has no placeable observation
    /// ("No recorded trades"). Shown beside the name only then.
    let absentWords: String?
}

/// The owner's horizontal plot domain.
nonisolated struct CricketHistoryDomain10868: Equatable {
    let lower: Double
    let upper: Double

    var isValid: Bool { lower.isFinite && upper.isFinite && upper > lower }

    func contains(_ x: Double) -> Bool {
        isValid && x.isFinite && x >= lower && x <= upper
    }
}

/// One owner axis tick: a value on its axis and its words, line by line.
nonisolated struct CricketHistoryTick10868: Equatable {
    /// A probability (0...1) on the vertical axis, or a domain value on the
    /// horizontal axis.
    let value: Double
    /// Verbatim ("50%"; or "Oct 13" then "4:11 AM").
    let lines: [String]
}

/// One series at the owner's inspected position.
nonisolated enum CricketHistorySelection10868: Equatable {
    /// The exact point the owner selected, and its spoken words ("64%").
    case point(id: String, spoken: String)
    /// No observation for this series there, in the owner's words
    /// ("Not recorded"). Shown and spoken; nothing is borrowed.
    case absent(words: String)
}

/// The host's held inspection, drawn exactly as supplied.
nonisolated struct CricketHistoryInspection10868: Equatable {
    /// The cursor's domain position. Not drawn when absent or outside the
    /// domain.
    let x: Double?
    /// The owner's caption ("Selected · Oct 13, 4:11 AM").
    let caption: String
    /// By series id. A series with no entry shows and speaks nothing extra.
    let selections: [String: CricketHistorySelection10868]
}

/// An owner action: its full spoken name and whether it is available now.
nonisolated struct CricketHistoryControl10868: Equatable {
    let label: String
    let isAvailable: Bool
}

/// One owner window choice ("Match", "Day 5").
nonisolated struct CricketHistoryWindowChoice10868: Equatable {
    let id: String
    let label: String
    let isSelected: Bool
}

/// The owner's window line under the plot.
nonisolated enum CricketHistoryWindow10868: Equatable {
    /// Words only ("Hourly history").
    case caption(String)
    /// A named group of choices, handed back by id.
    case choices(groupLabel: String, choices: [CricketHistoryWindowChoice10868])
}

nonisolated struct CricketHistoryInput10868: Equatable {
    /// "Win probability".
    let title: String
    /// In the owner's order, every one drawn. No implicit three-series cap.
    let series: [CricketHistorySeries10868]
    let domain: CricketHistoryDomain10868
    /// Owner percentage ticks (0...1), drawn with a gridline each.
    let yTicks: [CricketHistoryTick10868]
    /// Owner local-calendar ticks inside the domain.
    let xTicks: [CricketHistoryTick10868]
    /// Full source and calendar context in the owner's words, including the
    /// reader's local time zone.
    let context: String?
    /// The word beside the hollow key mark ("Pregame"). Shown only when a
    /// pregame observation is drawn.
    let pregameKey: String?
    /// The owner's complete spoken description of the plot.
    let summary: String
    /// The owner's plot height in points (about 302 standard; taller in
    /// full-size, wide and accessibility contexts). Never shrunk here.
    let plotHeight: CGFloat
    let window: CricketHistoryWindow10868?
    let inspection: CricketHistoryInspection10868?
    let previous: CricketHistoryControl10868?
    let next: CricketHistoryControl10868?
    let expand: CricketHistoryControl10868?
}

/// The owner's match phase for the marker context.
nonisolated enum CricketHistoryMarkerPhase10868: Equatable {
    /// Nothing of the context is drawn, shown or spoken.
    case before
    case during
    case completed
}

/// How a guide is drawn: the neutral labelled innings-report guide, or a
/// subtle score-report guide.
nonisolated enum CricketHistoryMarkerEmphasis10868: Equatable {
    case prominent
    case subtle
}

/// One owner-admitted match-progress marker.
nonisolated struct CricketHistoryMarker10868: Equatable {
    /// The owner's opaque, stable marker identity.
    let id: String
    /// The owner's position in the plot domain's unit. Nil when the owner
    /// holds this marker without a time. Never read as a clock here.
    let x: Double?
    let emphasis: CricketHistoryMarkerEmphasis10868
    /// The visible words above the guide ("Innings report"). Nil when the
    /// owner explicitly shows no label; the meaning then lives in the key and
    /// the spoken words.
    let label: String?
    /// The owner's complete spoken description, including its timing words.
    let spoken: String
    /// The owner's words for a marker it holds without a time. Shown and
    /// spoken only then; no position is invented for it.
    let absentWords: String?
}

/// The owner's marker context, beside the history input.
nonisolated struct CricketHistoryMarkerContext10868: Equatable {
    let phase: CricketHistoryMarkerPhase10868
    /// In the owner's order.
    let markers: [CricketHistoryMarker10868]
    /// The neutral key words naming what the guides actually are ("Score-report
    /// publication times; not exact ball times").
    let key: String?
}

// MARK: - Geometry

/// Where one axis label sits along its axis, and which row (horizontal axis)
/// or column (vertical axis) it was moved to so it touches no other label.
nonisolated struct CricketHistoryLabelSlot10868: Equatable {
    let start: CGFloat
    let lane: Int
}

/// The measured plot: the drawing frame, every axis label's frame and the
/// total height.
nonisolated struct CricketHistoryPlotArrangement10868: Equatable {
    let plot: CGRect
    let yLabels: [CGRect]
    let xLabels: [CGRect]
    let yColumns: Int
    let xRows: Int
    let height: CGFloat

    var frames: [CGRect] { [plot] + yLabels + xLabels }
}

/// The measured plot with the owner's marker labels in a band above it.
nonisolated struct CricketHistoryMarkedArrangement10868: Equatable {
    /// The plot arrangement, moved down by the band; its height is the total.
    let base: CricketHistoryPlotArrangement10868
    let markerLabels: [CGRect]
    let markerRows: Int
    let band: CGFloat

    var frames: [CGRect] { base.frames + markerLabels }
}

/// Pure rules the view draws from. Unit-tested without rendering.
nonisolated enum CricketHistoryGeometry10868 {
    /// The approved standard plot height, used only when the owner's height
    /// is not a usable size.
    static let referencePlotHeight: CGFloat = 302

    static func plotHeight(_ owner: CGFloat) -> CGFloat {
        owner.isFinite && owner > 0 ? owner : referencePlotHeight
    }

    static func isPlaceable(_ point: CricketHistoryPoint10868, in domain: CricketHistoryDomain10868) -> Bool {
        domain.contains(point.x)
            && point.probability.isFinite
            && point.probability >= 0
            && point.probability <= 1
    }

    /// The drawn runs of one segment: maximal stretches of consecutive
    /// placeable points whose x advances. An unplaceable point ends a run and
    /// starts no line; so does an x that does not advance.
    static func runs(_ segment: CricketHistorySegment10868,
                     in domain: CricketHistoryDomain10868) -> [[CricketHistoryPoint10868]] {
        var runs: [[CricketHistoryPoint10868]] = []
        var current: [CricketHistoryPoint10868] = []
        for point in segment.points {
            guard isPlaceable(point, in: domain) else {
                if !current.isEmpty { runs.append(current) }
                current = []
                continue
            }
            if let last = current.last, !(point.x > last.x) {
                runs.append(current)
                current = []
            }
            current.append(point)
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }

    /// Every line of a series: its runs of two or more points, segment by
    /// segment. Never joined across segments.
    static func lines(_ series: CricketHistorySeries10868,
                      in domain: CricketHistoryDomain10868) -> [[CricketHistoryPoint10868]] {
        series.segments.flatMap { runs($0, in: domain) }.filter { $0.count >= 2 }
    }

    /// Every mark of a series: each placeable point, in the owner's order.
    static func marks(_ series: CricketHistorySeries10868,
                      in domain: CricketHistoryDomain10868) -> [CricketHistoryPoint10868] {
        series.segments.flatMap(\.points).filter { isPlaceable($0, in: domain) }
    }

    static func hasPlacedPoint(_ series: CricketHistorySeries10868, in domain: CricketHistoryDomain10868) -> Bool {
        !marks(series, in: domain).isEmpty
    }

    /// The hollow key entry appears only when a hollow mark is drawn.
    static func showsPregameKey(_ input: CricketHistoryInput10868) -> Bool {
        input.pregameKey != nil
            && input.series.contains { marks($0, in: input.domain).contains(where: \.isPregame) }
    }

    /// The series' own absence words, only when nothing of it is drawn.
    static func absentWords(_ series: CricketHistorySeries10868, in domain: CricketHistoryDomain10868) -> String? {
        hasPlacedPoint(series, in: domain) ? nil : series.absentWords
    }

    // MARK: Coordinates

    /// The frame marks may be centred in: the plot inset by the largest mark,
    /// so a real 0% or 100% mark is never cut.
    static func drawingRect(in size: CGSize, inset: CGFloat) -> CGRect {
        CGRect(x: inset, y: inset,
               width: max(0, size.width - 2 * inset),
               height: max(0, size.height - 2 * inset))
    }

    static func fraction(_ x: Double, in domain: CricketHistoryDomain10868) -> Double {
        (x - domain.lower) / (domain.upper - domain.lower)
    }

    static func position(_ point: CricketHistoryPoint10868,
                         domain: CricketHistoryDomain10868,
                         in rect: CGRect) -> CGPoint {
        CGPoint(x: xPosition(point.x, domain: domain, in: rect), y: yPosition(point.probability, in: rect))
    }

    static func xPosition(_ x: Double, domain: CricketHistoryDomain10868, in rect: CGRect) -> CGFloat {
        rect.minX + CGFloat(fraction(x, in: domain)) * rect.width
    }

    static func yPosition(_ probability: Double, in rect: CGRect) -> CGFloat {
        rect.maxY - CGFloat(probability) * rect.height
    }

    /// The domain position under a horizontal plot coordinate, for the host to
    /// resolve. Nothing outside the drawing frame or an invalid domain.
    static func domainValue(atX location: CGFloat,
                            domain: CricketHistoryDomain10868,
                            in rect: CGRect) -> Double? {
        guard domain.isValid, location.isFinite, rect.width > 0,
              location >= rect.minX, location <= rect.maxX else { return nil }
        return domain.lower + Double((location - rect.minX) / rect.width) * (domain.upper - domain.lower)
    }

    // MARK: Ticks

    static func placedYTicks(_ ticks: [CricketHistoryTick10868]) -> [CricketHistoryTick10868] {
        ticks.filter { $0.value.isFinite && $0.value >= 0 && $0.value <= 1 }
    }

    static func placedXTicks(_ ticks: [CricketHistoryTick10868],
                             domain: CricketHistoryDomain10868) -> [CricketHistoryTick10868] {
        ticks.filter { domain.contains($0.value) }
    }

    // MARK: Inspection

    /// The owner's cursor, only when it lies inside the domain.
    static func cursor(_ inspection: CricketHistoryInspection10868?,
                       domain: CricketHistoryDomain10868) -> Double? {
        guard let x = inspection?.x, domain.contains(x) else { return nil }
        return x
    }

    /// The owner's selected point of a series: exactly one placeable point
    /// with the owner's id, or nothing. Never the nearest, never a neighbour.
    static func selectedPoint(_ series: CricketHistorySeries10868,
                              inspection: CricketHistoryInspection10868?,
                              domain: CricketHistoryDomain10868) -> CricketHistoryPoint10868? {
        guard case .point(let id, _)? = inspection?.selections[series.id] else { return nil }
        let matches = series.segments.flatMap(\.points).filter { $0.id == id }
        guard matches.count == 1, let match = matches.first, isPlaceable(match, in: domain) else { return nil }
        return match
    }

    /// The owner's absence words for a series at the inspected position.
    static func selectionAbsentWords(_ series: CricketHistorySeries10868,
                                     inspection: CricketHistoryInspection10868?) -> String? {
        guard case .absent(let words)? = inspection?.selections[series.id] else { return nil }
        return words
    }

    /// Whether an inspection keyed by this series' id can name this series
    /// alone: the id is nonempty and exactly one supplied series carries it.
    /// Nothing is renamed, deduplicated or dropped; an ambiguous series is
    /// still drawn and keyed, it just receives no inspection.
    static func isExactlyIdentified(_ series: CricketHistorySeries10868,
                                    in input: CricketHistoryInput10868) -> Bool {
        !series.id.isEmpty && input.series.filter { $0.id == series.id }.count == 1
    }

    /// The selected point the view rings and speaks: the series' exact
    /// selected point, only for an exactly identified series.
    static func inspectedPoint(_ series: CricketHistorySeries10868,
                               in input: CricketHistoryInput10868) -> CricketHistoryPoint10868? {
        guard isExactlyIdentified(series, in: input) else { return nil }
        return selectedPoint(series, inspection: input.inspection, domain: input.domain)
    }

    /// The inspected absence words the view notes and speaks, only for an
    /// exactly identified series.
    static func inspectedAbsentWords(_ series: CricketHistorySeries10868,
                                     in input: CricketHistoryInput10868) -> String? {
        guard isExactlyIdentified(series, in: input) else { return nil }
        return selectionAbsentWords(series, inspection: input.inspection)
    }

    /// The words beside a series' key name: its own absence words when
    /// nothing of it is drawn, otherwise the inspected absence words.
    static func keyNote(_ series: CricketHistorySeries10868, in input: CricketHistoryInput10868) -> String? {
        absentWords(series, in: input.domain) ?? inspectedAbsentWords(series, in: input)
    }

    // MARK: Controls

    /// An owner action is offered only when a callback can carry it.
    static func offered(_ control: CricketHistoryControl10868?, hasCallback: Bool) -> CricketHistoryControl10868? {
        hasCallback ? control : nil
    }

    static func offeredChoices(_ window: CricketHistoryWindow10868?,
                               hasCallback: Bool) -> [CricketHistoryWindowChoice10868] {
        guard hasCallback, case .choices(_, let choices)? = window else { return [] }
        return choices
    }

    /// The id a window choice hands back: only a nonempty id that names
    /// exactly one of the supplied choices. Otherwise nil, and the choice is
    /// shown static with its label, place and selected look.
    static func windowChoiceAction(_ choice: CricketHistoryWindowChoice10868,
                                   among choices: [CricketHistoryWindowChoice10868]) -> String? {
        guard !choice.id.isEmpty, choices.filter({ $0.id == choice.id }).count == 1 else { return nil }
        return choice.id
    }

    // MARK: Spoken

    /// The plot's accessibility value: the inspection caption, each exactly
    /// identified series' owner words there, then each undrawn series'
    /// absence words — names first, nothing borrowed between series.
    static func spokenValue(_ input: CricketHistoryInput10868) -> String {
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
            if let words = absentWords(series, in: input.domain) {
                parts.append("\(series.name): \(words)")
            }
        }
        return parts.joined(separator: "; ")
    }

    // MARK: Mark paths

    /// One mark in its series' shape, `radius` from its centre (the diamond's
    /// half-diagonal is 1.2× and the square's half-side 0.8×, as approved).
    static func markPath(_ shape: CricketHistoryShape10868, at center: CGPoint, radius: CGFloat) -> Path {
        switch shape {
        case .circle:
            return Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius,
                                          width: radius * 2, height: radius * 2))
        case .diamond:
            let r = radius * 1.2
            var path = Path()
            path.move(to: CGPoint(x: center.x, y: center.y - r))
            path.addLine(to: CGPoint(x: center.x + r, y: center.y))
            path.addLine(to: CGPoint(x: center.x, y: center.y + r))
            path.addLine(to: CGPoint(x: center.x - r, y: center.y))
            path.closeSubpath()
            return path
        case .square:
            let half = radius * 0.8
            return Path(CGRect(x: center.x - half, y: center.y - half, width: half * 2, height: half * 2))
        }
    }

    // MARK: Axis labels

    /// Places labels along one axis: each centred on its tick, slid inward to
    /// stay inside `extent`, and moved to the first lane where it keeps `gap`
    /// clear of every label already there. Nothing is dropped or shortened.
    static func labelSlots(centers: [CGFloat], lengths: [CGFloat],
                           extent: CGFloat, gap: CGFloat) -> [CricketHistoryLabelSlot10868] {
        let extent = max(0, extent.isFinite ? extent : 0)
        let gap = max(0, gap)
        var lanes: [[ClosedRange<CGFloat>]] = []
        var slots: [CricketHistoryLabelSlot10868] = []
        for (center, rawLength) in zip(centers, lengths) {
            let length = min(max(0, rawLength.isFinite ? rawLength : 0), extent)
            let middle = center.isFinite ? center : 0
            let start = min(max(0, middle - length / 2), extent - length)
            let clearance = (start - gap)...(start + length + gap)
            let lane = lanes.firstIndex { taken in !taken.contains { $0.overlaps(clearance) } } ?? lanes.count
            if lane == lanes.count { lanes.append([]) }
            lanes[lane].append(start...(start + length))
            slots.append(CricketHistoryLabelSlot10868(start: start, lane: lane))
        }
        return slots
    }

    /// The whole measured plot at one width. Percentage labels take a gutter
    /// as wide as they measure (an extra column only if two would touch);
    /// calendar labels sit under their ticks (an extra row only if two would
    /// touch). The plot keeps the owner's height.
    static func plotArrangement(width rawWidth: CGFloat, plotHeight: CGFloat, inset: CGFloat,
                                yValues: [Double], ySizes: [CGSize],
                                xFractions: [Double], xSizes: [CGSize],
                                labelGap: CGFloat, axisGap: CGFloat,
                                laneSpacing: CGFloat) -> CricketHistoryPlotArrangement10868 {
        let width = max(0, rawWidth.isFinite ? rawWidth : 0)
        let height = Self.plotHeight(plotHeight)
        let yCount = min(yValues.count, ySizes.count)
        let xCount = min(xFractions.count, xSizes.count)
        let ySizes = Array(ySizes.prefix(yCount))
        let xSizes = Array(xSizes.prefix(xCount))

        let ySpan = max(0, height - 2 * inset)
        let yCenters = yValues.prefix(yCount).map { inset + CGFloat(1 - $0) * ySpan }
        let ySlots = labelSlots(centers: Array(yCenters), lengths: ySizes.map(\.height), extent: height, gap: 2)
        let columns = (ySlots.map(\.lane).max() ?? -1) + 1
        var columnWidths = Array(repeating: CGFloat(0), count: columns)
        for (slot, size) in zip(ySlots, ySizes) {
            columnWidths[slot.lane] = max(columnWidths[slot.lane], size.width)
        }
        let gutter = columns == 0 ? 0 : columnWidths.reduce(0, +) + CGFloat(columns) * labelGap
        var trailingEdges: [CGFloat] = []
        var edge = gutter - labelGap
        for lane in 0..<columns {
            trailingEdges.append(edge)
            edge -= columnWidths[lane] + labelGap
        }
        let yFrames = zip(ySlots, ySizes).map { slot, size in
            CGRect(x: trailingEdges[slot.lane] - size.width, y: slot.start, width: size.width, height: size.height)
        }

        let plotWidth = max(0, width - gutter)
        let plot = CGRect(x: min(gutter, width), y: 0, width: plotWidth, height: height)
        let xSpan = max(0, plotWidth - 2 * inset)
        let xCenters = xFractions.prefix(xCount).map { plot.minX + inset + CGFloat($0) * xSpan }
        let xSlots = labelSlots(centers: Array(xCenters), lengths: xSizes.map(\.width), extent: width, gap: labelGap)
        let rows = (xSlots.map(\.lane).max() ?? -1) + 1
        var rowHeights = Array(repeating: CGFloat(0), count: rows)
        for (slot, size) in zip(xSlots, xSizes) {
            rowHeights[slot.lane] = max(rowHeights[slot.lane], size.height)
        }
        var rowTops: [CGFloat] = []
        var top = height + axisGap
        for row in 0..<rows {
            rowTops.append(top)
            top += rowHeights[row] + laneSpacing
        }
        let xFrames = zip(xSlots, xSizes).map { slot, size in
            CGRect(x: slot.start, y: rowTops[slot.lane], width: min(size.width, width), height: size.height)
        }
        return CricketHistoryPlotArrangement10868(
            plot: plot,
            yLabels: yFrames,
            xLabels: xFrames,
            yColumns: columns,
            xRows: rows,
            height: rows == 0 ? height : top - laneSpacing
        )
    }

    // MARK: Markers

    /// The held cursor's dash and the guides' dash, kept apart so a guide is
    /// never read as the held inspection.
    static let cursorDash: [CGFloat] = [3, 3]
    static let markerDash: [CGFloat] = [3, 4]

    /// The markers drawn: none before play; otherwise each supplied marker
    /// whose position lies inside the domain, in the owner's order.
    static func visibleMarkers(_ context: CricketHistoryMarkerContext10868?,
                               domain: CricketHistoryDomain10868) -> [CricketHistoryMarker10868] {
        guard let context, context.phase != .before else { return [] }
        return context.markers.filter { marker in marker.x.map { domain.contains($0) } ?? false }
    }

    /// The drawn markers that carry visible words, in the owner's order.
    static func labelledMarkers(_ context: CricketHistoryMarkerContext10868?,
                                domain: CricketHistoryDomain10868) -> [CricketHistoryMarker10868] {
        visibleMarkers(context, domain: domain).filter { !($0.label ?? "").isEmpty }
    }

    /// The owner's absence words of markers held without a time; none before
    /// play. A marker whose position is outside the domain or not finite is
    /// neither drawn nor described.
    static func unavailableMarkerWords(_ context: CricketHistoryMarkerContext10868?) -> [String] {
        guard let context, context.phase != .before else { return [] }
        return context.markers.compactMap { marker in
            guard marker.x == nil, let words = marker.absentWords, !words.isEmpty else { return nil }
            return words
        }
    }

    /// The marker line in the key: the owner's key words while a guide is
    /// drawn, then the absence words of markers held without a time.
    static func markerKeyWords(_ context: CricketHistoryMarkerContext10868?,
                               domain: CricketHistoryDomain10868) -> String? {
        var parts: [String] = []
        if !visibleMarkers(context, domain: domain).isEmpty, let key = context?.key, !key.isEmpty {
            parts.append(key)
        }
        parts += unavailableMarkerWords(context)
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// The plot's accessibility label: the owner's summary, then — only for
    /// what is drawn or held without a time — the key words, each drawn
    /// marker's spoken words and each absence, in the owner's order.
    static func spokenLabel(summary: String,
                            markers context: CricketHistoryMarkerContext10868?,
                            domain: CricketHistoryDomain10868) -> String {
        let visible = visibleMarkers(context, domain: domain)
        var parts = [summary]
        if !visible.isEmpty, let key = context?.key { parts.append(key) }
        parts += visible.map(\.spoken)
        parts += unavailableMarkerWords(context)
        return parts.filter { !$0.isEmpty }.joined(separator: " ")
    }

    /// The plot arrangement with marker labels in rows above the plot: each
    /// label centred over its guide, slid inward to stay whole, and moved to
    /// a further row only when it would touch another. Row 0 sits nearest the
    /// plot. The plot keeps the owner's height; the band adds to the total.
    /// With no labels this is exactly ``plotArrangement``.
    static func markedPlotArrangement(width rawWidth: CGFloat, plotHeight: CGFloat, inset: CGFloat,
                                      yValues: [Double], ySizes: [CGSize],
                                      xFractions: [Double], xSizes: [CGSize],
                                      markerFractions: [Double], markerSizes: [CGSize],
                                      labelGap: CGFloat, axisGap: CGFloat,
                                      laneSpacing: CGFloat, markerGap: CGFloat) -> CricketHistoryMarkedArrangement10868 {
        let base = plotArrangement(width: rawWidth, plotHeight: plotHeight, inset: inset,
                                   yValues: yValues, ySizes: ySizes, xFractions: xFractions, xSizes: xSizes,
                                   labelGap: labelGap, axisGap: axisGap, laneSpacing: laneSpacing)
        let width = max(0, rawWidth.isFinite ? rawWidth : 0)
        let count = min(markerFractions.count, markerSizes.count)
        let sizes = Array(markerSizes.prefix(count))
        let xSpan = max(0, base.plot.width - 2 * inset)
        let centers = markerFractions.prefix(count).map { base.plot.minX + inset + CGFloat($0) * xSpan }
        let slots = labelSlots(centers: Array(centers), lengths: sizes.map(\.width), extent: width, gap: labelGap)
        let rows = (slots.map(\.lane).max() ?? -1) + 1
        var rowHeights = Array(repeating: CGFloat(0), count: rows)
        for (slot, size) in zip(slots, sizes) {
            rowHeights[slot.lane] = max(rowHeights[slot.lane], size.height)
        }
        let band = rows == 0 ? 0 : rowHeights.reduce(0, +) + CGFloat(rows - 1) * laneSpacing + markerGap
        var rowTops: [CGFloat] = []
        var bottom = band - markerGap
        for row in 0..<rows {
            bottom -= rowHeights[row]
            rowTops.append(bottom)
            bottom -= laneSpacing
        }
        let labels = zip(slots, sizes).map { slot, size in
            CGRect(x: slot.start, y: rowTops[slot.lane], width: min(size.width, width), height: size.height)
        }
        func moved(_ frame: CGRect) -> CGRect { frame.offsetBy(dx: 0, dy: band) }
        return CricketHistoryMarkedArrangement10868(
            base: CricketHistoryPlotArrangement10868(
                plot: moved(base.plot),
                yLabels: base.yLabels.map(moved),
                xLabels: base.xLabels.map(moved),
                yColumns: base.yColumns,
                xRows: base.xRows,
                height: base.height + band
            ),
            markerLabels: labels,
            markerRows: rows,
            band: band
        )
    }
}

// MARK: - Layout

/// Subviews: the plot, then one label per placed percentage tick, then one
/// per placed calendar tick, then one per labelled marker, in that order.
/// Frames come from ``CricketHistoryGeometry10868/markedPlotArrangement``. A
/// label wider than the whole width is measured at that width and wraps; none
/// is truncated.
struct CricketHistoryPlotLayout10868: Layout {
    let yValues: [Double]
    /// Each calendar tick as a fraction of the domain.
    let xFractions: [Double]
    let plotHeight: CGFloat
    let inset: CGFloat
    /// Each labelled marker as a fraction of the domain.
    var markerFractions: [Double] = []
    var labelGap: CGFloat = 6
    var axisGap: CGFloat = 6
    var laneSpacing: CGFloat = 4
    var markerGap: CGFloat = 4

    private func arrangement(width: CGFloat, subviews: Subviews) -> CricketHistoryMarkedArrangement10868 {
        let labels = max(0, subviews.count - 1)
        let yCount = min(yValues.count, labels)
        let xCount = min(xFractions.count, labels - yCount)
        let markerCount = min(markerFractions.count, labels - yCount - xCount)
        func size(_ index: Int) -> CGSize {
            let ideal = subviews[index].sizeThatFits(.unspecified)
            guard ideal.width > width else { return ideal }
            return subviews[index].sizeThatFits(ProposedViewSize(width: width, height: nil))
        }
        return CricketHistoryGeometry10868.markedPlotArrangement(
            width: width,
            plotHeight: plotHeight,
            inset: inset,
            yValues: Array(yValues.prefix(yCount)),
            ySizes: (0..<yCount).map { size(1 + $0) },
            xFractions: Array(xFractions.prefix(xCount)),
            xSizes: (0..<xCount).map { size(1 + yCount + $0) },
            markerFractions: Array(markerFractions.prefix(markerCount)),
            markerSizes: (0..<markerCount).map { size(1 + yCount + xCount + $0) },
            labelGap: labelGap,
            axisGap: axisGap,
            laneSpacing: laneSpacing,
            markerGap: markerGap
        )
    }

    private static func width(_ proposal: ProposedViewSize) -> CGFloat {
        guard let width = proposal.width, width.isFinite else { return 0 }
        return width
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = Self.width(proposal)
        return CGSize(width: width, height: arrangement(width: width, subviews: subviews).base.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = arrangement(width: bounds.width, subviews: subviews).frames
        for (index, frame) in frames.enumerated() where index < subviews.count {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                proposal: ProposedViewSize(frame.size)
            )
        }
    }
}

// MARK: - View

struct CricketProbabilityHistoryPresentation10868: View {
    let input: CricketHistoryInput10868
    /// The owner's match-progress guides. Nil draws exactly the history alone.
    var markers: CricketHistoryMarkerContext10868? = nil
    var onPrevious: (() -> Void)? = nil
    var onNext: (() -> Void)? = nil
    var onExpand: (() -> Void)? = nil
    var onWindowChoice: ((String) -> Void)? = nil
    /// Reports the domain position under a tap for the host to resolve.
    var onPlotPosition: ((Double) -> Void)? = nil

    /// A plain mark's radius; the selected ring is twice this.
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 3.5
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var inset: CGFloat { markRadius * 2 + 1.5 }
    private var plotHeight: CGFloat { CricketHistoryGeometry10868.plotHeight(input.plotHeight) }
    private var yTicks: [CricketHistoryTick10868] { CricketHistoryGeometry10868.placedYTicks(input.yTicks) }
    private var xTicks: [CricketHistoryTick10868] {
        CricketHistoryGeometry10868.placedXTicks(input.xTicks, domain: input.domain)
    }
    private var labelledMarkers: [CricketHistoryMarker10868] {
        CricketHistoryGeometry10868.labelledMarkers(markers, domain: input.domain)
    }
    private var previous: CricketHistoryControl10868? {
        CricketHistoryGeometry10868.offered(input.previous, hasCallback: onPrevious != nil)
    }
    private var next: CricketHistoryControl10868? {
        CricketHistoryGeometry10868.offered(input.next, hasCallback: onNext != nil)
    }
    private var expand: CricketHistoryControl10868? {
        CricketHistoryGeometry10868.offered(input.expand, hasCallback: onExpand != nil)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            plot
            key
            if let context = input.context {
                Text(context)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            windowLine
            inspectionLine
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center, spacing: 8) {
            Text(input.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityAddTraits(.isHeader)
            if let expand, let onExpand {
                CricketHistoryStepButton10868(
                    systemName: "arrow.up.left.and.arrow.down.right",
                    control: expand,
                    size: controlSize,
                    action: onExpand
                )
            }
        }
    }

    // MARK: Plot

    private var plot: some View {
        CricketHistoryPlotLayout10868(
            yValues: yTicks.map(\.value),
            xFractions: xTicks.map { CricketHistoryGeometry10868.fraction($0.value, in: input.domain) },
            plotHeight: plotHeight,
            inset: inset,
            markerFractions: labelledMarkers.compactMap { marker in
                marker.x.map { CricketHistoryGeometry10868.fraction($0, in: input.domain) }
            }
        ) {
            canvas
            ForEach(Array(yTicks.enumerated()), id: \.offset) { _, tick in
                CricketHistoryTickLabel10868(lines: tick.lines, alignment: .trailing)
            }
            ForEach(Array(xTicks.enumerated()), id: \.offset) { _, tick in
                CricketHistoryTickLabel10868(lines: tick.lines, alignment: .center)
            }
            ForEach(Array(labelledMarkers.enumerated()), id: \.offset) { _, marker in
                CricketHistoryMarkerLabel10868(text: marker.label ?? "")
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(CricketHistoryGeometry10868.spokenLabel(
            summary: input.summary, markers: markers, domain: input.domain))
        .accessibilityValue(CricketHistoryGeometry10868.spokenValue(input))
        .accessibilityAddTraits(.isImage)
        .modifier(CricketHistoryAdjustable10868(
            previous: previous?.isAvailable == true ? onPrevious : nil,
            next: next?.isAvailable == true ? onNext : nil
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
                        let rect = CricketHistoryGeometry10868.drawingRect(in: proxy.size, inset: inset)
                        if let value = CricketHistoryGeometry10868.domainValue(
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
        let rect = CricketHistoryGeometry10868.drawingRect(in: size, inset: inset)
        let domain = input.domain

        for tick in yTicks {
            let y = CricketHistoryGeometry10868.yPosition(tick.value, in: rect)
            var grid = Path()
            grid.move(to: CGPoint(x: 0, y: y))
            grid.addLine(to: CGPoint(x: size.width, y: y))
            context.stroke(grid, with: .color(DS.border), lineWidth: 1)
        }

        for marker in CricketHistoryGeometry10868.visibleMarkers(markers, domain: domain) {
            guard let x = marker.x else { continue }
            let gx = CricketHistoryGeometry10868.xPosition(x, domain: domain, in: rect)
            var guide = Path()
            guide.move(to: CGPoint(x: gx, y: 0))
            guide.addLine(to: CGPoint(x: gx, y: size.height))
            let tint = marker.emphasis == .prominent ? DS.textMuted : DS.border
            context.stroke(guide, with: .color(tint),
                           style: StrokeStyle(lineWidth: 1, dash: CricketHistoryGeometry10868.markerDash))
        }

        if let x = CricketHistoryGeometry10868.cursor(input.inspection, domain: domain) {
            let cx = CricketHistoryGeometry10868.xPosition(x, domain: domain, in: rect)
            var cursor = Path()
            cursor.move(to: CGPoint(x: cx, y: 0))
            cursor.addLine(to: CGPoint(x: cx, y: size.height))
            context.stroke(cursor, with: .color(DS.textSecondary),
                           style: StrokeStyle(lineWidth: 1, dash: CricketHistoryGeometry10868.cursorDash))
        }

        let line = StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round)
        for series in input.series {
            for run in CricketHistoryGeometry10868.lines(series, in: domain) {
                var path = Path()
                path.addLines(run.map { CricketHistoryGeometry10868.position($0, domain: domain, in: rect) })
                context.stroke(path, with: .color(series.tint), style: line)
            }
        }

        for series in input.series {
            for point in CricketHistoryGeometry10868.marks(series, in: domain) {
                let center = CricketHistoryGeometry10868.position(point, domain: domain, in: rect)
                let mark = CricketHistoryGeometry10868.markPath(series.shape, at: center, radius: markRadius)
                if point.isPregame {
                    context.fill(mark, with: .color(DS.cardBg))
                    context.stroke(mark, with: .color(series.tint), lineWidth: 1.5)
                } else {
                    context.fill(mark, with: .color(series.tint))
                }
            }
        }

        for series in input.series {
            guard let point = CricketHistoryGeometry10868.inspectedPoint(series, in: input) else { continue }
            let center = CricketHistoryGeometry10868.position(point, domain: domain, in: rect)
            let ring = CricketHistoryGeometry10868.markPath(series.shape, at: center, radius: markRadius * 2)
            context.stroke(ring, with: .color(series.tint), lineWidth: 2)
        }
    }

    // MARK: Key

    private var key: some View {
        FlowLayout(spacing: 12) {
            ForEach(Array(input.series.enumerated()), id: \.offset) { _, series in
                CricketHistoryKeyEntry10868(
                    shape: series.shape,
                    tint: series.tint,
                    hollow: false,
                    name: series.name,
                    note: CricketHistoryGeometry10868.keyNote(series, in: input),
                    markRadius: markRadius
                )
            }
            if CricketHistoryGeometry10868.showsPregameKey(input), let pregame = input.pregameKey {
                CricketHistoryKeyEntry10868(
                    shape: .circle,
                    tint: DS.textSecondary,
                    hollow: true,
                    name: pregame,
                    note: nil,
                    markRadius: markRadius
                )
            }
            if let words = CricketHistoryGeometry10868.markerKeyWords(markers, domain: input.domain) {
                CricketHistoryMarkerKeyEntry10868(
                    words: words,
                    showsGuide: !CricketHistoryGeometry10868.visibleMarkers(markers, domain: input.domain).isEmpty,
                    markRadius: markRadius
                )
            }
        }
    }

    // MARK: Window and inspection

    @ViewBuilder
    private var windowLine: some View {
        let choices = CricketHistoryGeometry10868.offeredChoices(input.window, hasCallback: onWindowChoice != nil)
        switch input.window {
        case .caption(let words)?:
            Text(words)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .choices(let groupLabel, _)?:
            if !choices.isEmpty, let onWindowChoice {
                FlowLayout(spacing: 6) {
                    ForEach(Array(choices.enumerated()), id: \.offset) { _, choice in
                        CricketHistoryWindowButton10868(
                            choice: choice,
                            minHeight: controlSize,
                            action: CricketHistoryGeometry10868.windowChoiceAction(choice, among: choices)
                                .map { id -> () -> Void in { onWindowChoice(id) } }
                        )
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(groupLabel)
            }
        case nil:
            EmptyView()
        }
    }

    @ViewBuilder
    private var inspectionLine: some View {
        let caption = input.inspection?.caption
        if previous != nil || next != nil {
            HStack(alignment: .center, spacing: 10) {
                if let previous, let onPrevious {
                    CricketHistoryStepButton10868(systemName: "chevron.left", control: previous,
                                                  size: controlSize, action: onPrevious)
                }
                Group {
                    if let caption {
                        CricketHistoryCaption10868(text: caption)
                    } else {
                        Color.clear.frame(height: 1)
                    }
                }
                .frame(maxWidth: .infinity)
                if let next, let onNext {
                    CricketHistoryStepButton10868(systemName: "chevron.right", control: next,
                                                  size: controlSize, action: onNext)
                }
            }
        } else if let caption {
            CricketHistoryCaption10868(text: caption)
        }
    }
}

// MARK: - Private views

/// One tick's words, line by line. Each line keeps its whole width unless the
/// layout offers less than the whole plot, when it wraps.
private struct CricketHistoryTickLabel10868: View {
    let lines: [String]
    let alignment: HorizontalAlignment

    var body: some View {
        VStack(alignment: alignment, spacing: 0) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(alignment == .trailing ? .trailing : .center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityHidden(true)
    }
}

/// A marker's visible words above its guide. Wraps only when the layout
/// offers less than the whole plot; never truncated. Its meaning is spoken by
/// the plot, and it takes no taps.
private struct CricketHistoryMarkerLabel10868: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

/// The marker key entry: a short dashed upright, only while a guide is drawn,
/// then the owner's key and absence words.
private struct CricketHistoryMarkerKeyEntry10868: View {
    let words: String
    let showsGuide: Bool
    let markRadius: CGFloat

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            if showsGuide {
                Canvas { context, size in
                    var guide = Path()
                    guide.move(to: CGPoint(x: size.width / 2, y: 0))
                    guide.addLine(to: CGPoint(x: size.width / 2, y: size.height))
                    context.stroke(guide, with: .color(DS.textMuted),
                                   style: StrokeStyle(lineWidth: 1, dash: CricketHistoryGeometry10868.markerDash))
                }
                .frame(width: markRadius * 2, height: markRadius * 4.5)
                .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + markRadius }
                .accessibilityHidden(true)
            }
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

/// A key entry: a short solid line through the series' mark, then its full
/// name and, only when supplied, the owner's absence words.
private struct CricketHistoryKeyEntry10868: View {
    let shape: CricketHistoryShape10868
    let tint: Color
    let hollow: Bool
    let name: String
    let note: String?
    let markRadius: CGFloat

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Canvas { context, size in
                let middle = CGPoint(x: size.width / 2, y: size.height / 2)
                if !hollow {
                    var line = Path()
                    line.move(to: CGPoint(x: 0, y: middle.y))
                    line.addLine(to: CGPoint(x: size.width, y: middle.y))
                    context.stroke(line, with: .color(tint), lineWidth: 2)
                }
                let mark = CricketHistoryGeometry10868.markPath(shape, at: middle, radius: markRadius)
                if hollow {
                    context.fill(mark, with: .color(DS.cardBg))
                    context.stroke(mark, with: .color(tint), lineWidth: 1.5)
                } else {
                    context.fill(mark, with: .color(tint))
                }
            }
            .frame(width: markRadius * 6.5, height: markRadius * 4.5)
            .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + markRadius }
            .accessibilityHidden(true)
            Text(note.map { "\(name) · \($0)" } ?? name)
                .font(.subheadline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The owner's inspection caption.
private struct CricketHistoryCaption10868: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(DS.textSecondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// A 44 pt (scaled) bordered icon button carrying one owner action; dimmed and
/// inert while the owner marks it unavailable.
private struct CricketHistoryStepButton10868: View {
    let systemName: String
    let control: CricketHistoryControl10868
    let size: CGFloat
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .frame(minWidth: size, minHeight: size)
                .background(RoundedRectangle(cornerRadius: 10).fill(DS.cardBg))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(DS.border, lineWidth: 1))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!control.isAvailable)
        .opacity(control.isAvailable ? 1 : 0.4)
        .accessibilityLabel(control.label)
    }
}

/// One window choice; the selected one is filled and carries the selected
/// trait. With no action (an id that cannot name one owner action) it is the
/// same chip, static: no button, nothing to send.
private struct CricketHistoryWindowButton10868: View {
    let choice: CricketHistoryWindowChoice10868
    let minHeight: CGFloat
    let action: (() -> Void)?

    var body: some View {
        if let action {
            Button(action: action) { chip }
                .buttonStyle(.plain)
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        } else {
            chip
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        }
    }

    private var chip: some View {
        Text(choice.label)
            .font(.footnote)
            .foregroundStyle(choice.isSelected ? DS.cardBg : DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 10)
            .frame(minHeight: minHeight)
            .background(RoundedRectangle(cornerRadius: 10).fill(choice.isSelected ? DS.textPrimary : DS.cardBg))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(DS.border, lineWidth: 1))
            .contentShape(Rectangle())
    }
}

/// VoiceOver's swipe up/down hands back the owner's next/previous action, only
/// while one of them is available; otherwise the plot is not adjustable.
private struct CricketHistoryAdjustable10868: ViewModifier {
    let previous: (() -> Void)?
    let next: (() -> Void)?

    func body(content: Content) -> some View {
        if previous != nil || next != nil {
            content.accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: next?()
                case .decrement: previous?()
                @unknown default: break
                }
            }
        } else {
            content
        }
    }
}
