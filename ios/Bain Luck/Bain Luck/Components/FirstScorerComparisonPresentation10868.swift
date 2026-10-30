import SwiftUI

// #10868 — "Who scored first?": the first-goalscorer card across a match's
// lifecycle. A directly labelled lollipop plot always shows the saved PREGAME
// first-goalscorer chances on one shared, labelled scale. Above it, the
// selected player's named comparison: the pregame chance alone before play;
// pregame vs a recorded in-game chance, or the first-scorer result once the
// owner admits it, during play (that market can resolve while the match is
// still live); pregame chance vs the first-scorer result after the final.
//
// Presentation only, extracted from the approved design
// (first-scorer-comparison-20261025 frames; hockey-readable-card-composition-
// 20261026 `HockeyScoring.swift`: the compact confirmed-winner return, the
// named chance/result comparison, the baseline lollipop plot and page-owned
// timing). The plot row keeps the native reference's shape — name and direct
// value on one line, the track below at full width — so every row's track has
// the same width and origin and the scale is shared by construction.
//
// Every figure, tick, axis bound, membership, order, date, source, missing
// qualifier and result arrives resolved by the owner and is shown verbatim.
// This layer never formats, rounds, ranks, filters, caps, normalizes or joins
// players, never reads a clock, cache, subscription or admission rule, never
// infers a first scorer from goals, never derives a movement, and never shows a
// result or a settled price as a chance. An anytime-scoring chance is never a
// first-scorer chance. A missing result is never a loss.
//
// Selection, timing disclosure, Details and the full outcome list stay with the
// host: the view keeps no selected state, no sheet, no focus and no
// subscription. With no callback, content is shown without a button and no tap
// is asked for.
//
// Host binding still owed — not available at this base. An owner must supply,
// per player of the exact first-scorer market:
//   • the exact original first-scorer prop id, name and team text,
//   • an admitted pregame first-scorer observation (raw value, formatted
//     figure, full time/source) or its own missing words,
//   • during play, an independently admitted recorded observation or its own
//     unavailable / stale words, with currentness already applied,
//   • the owner-resolved result: scored first, not first, or unconfirmed
//     (missing, pending, ambiguous or conflicting) with its words;
// and for the card: the membership and order of the plot, its axis bounds and
// formatted ticks, coverage copy, and a confirmed first scorer only when the
// owner has admitted exactly one.
//
// The same card serves other "who scores first" questions — a soccer
// first-team-to-score market with its three original outcomes (two teams and
// Neither), for one — through two optional, caller-resolved inputs; with
// neither supplied the card reads exactly as the first-goalscorer card:
//   • an outcome context: the caller's own words for the pregame chance, the
//     current chance and the result (so a team or Neither is never called a
//     player, and nobody is described as having scored first), which also
//     shows every original row's own phase reading under its track;
//   • observed scores: owner-admitted score checkpoints, each with its own
//     observation time, shown during play only. They are observations, not
//     exact goal times, and never settle, price or name a first scorer here.

/// One admitted first-scorer reading. `probability` drives plot geometry only;
/// `text` is what the reader sees.
nonisolated struct FirstScorerObservation10868: Equatable {
    let probability: Double
    let text: String
    /// Full time and source for VoiceOver ("minute ending Oct 3, 4:57 PM PT · Kalshi").
    let accessibilityDetail: String
}

/// The owner's in-game first-scorer reading for one player, currentness applied.
nonisolated enum FirstScorerCurrent10868: Equatable {
    /// An independently admitted, current recorded observation.
    case recorded(FirstScorerObservation10868)
    /// No recorded reading ("No in-game reading").
    case unavailable(String)
    /// A reading exists but is no longer current ("No update since 7:03 PM").
    case stale(String)
}

/// The owner-resolved first-scorer result. Availability is explicit: there is
/// no Bool, so an absent result can never read as "not first".
nonisolated enum FirstScorerResult10868: Equatable {
    /// "Scored first".
    case scoredFirst(String)
    /// "Not first".
    case notFirst(String)
    /// No admitted result — pending, missing, ambiguous or conflicting
    /// ("Unconfirmed", "No first goal yet").
    case unconfirmed(String)
    /// An original outcome the owner admitted as won ("Won") — for an outcome
    /// that is not a scorer, such as a team or Neither.
    case won(String)
    /// An original outcome the owner admitted as lost ("Lost").
    case lost(String)

    var text: String {
        switch self {
        case .scoredFirst(let text), .notFirst(let text), .unconfirmed(let text), .won(let text), .lost(let text): text
        }
    }

    var isAdmitted: Bool {
        if case .unconfirmed = self { return false }
        return true
    }

    /// The ✓ / ✕ beside an admitted result. Unconfirmed has none, so unknown
    /// never reads as a loss.
    var mark: FirstScorerResultMark10868? {
        switch self {
        case .scoredFirst, .won: .positive
        case .notFirst, .lost: .negative
        case .unconfirmed: nil
        }
    }
}

nonisolated enum FirstScorerResultMark10868: Equatable {
    case positive
    case negative
}

/// The caller's words for what each row's readings are, chosen explicitly by
/// the caller — never parsed from a title or a name. Supplying one also shows
/// every original row's own phase reading under its track. Without one, the
/// card keeps the first-goalscorer words and its pregame-only plot rows.
nonisolated struct FirstScorerOutcomeContext10868: Equatable {
    /// "Pre-match chance"
    let pregameTitle: String
    /// "Current chance"
    let currentTitle: String
    /// A result admitted during play ("Result").
    let liveResultTitle: String
    /// "Final result" — shown, and spoken before each result after the final.
    let finalResultTitle: String
    /// "Selected outcome unavailable."
    let selectionUnavailable: String
    /// Spoken before the pregame figure ("Pre-match chance").
    let spokenPregame: String
    /// Spoken before the current figure or its words ("Current chance").
    let spokenCurrent: String
    /// Spoken before a result admitted during play ("Result").
    let spokenResult: String
    /// "Selects this outcome’s comparison"
    let selectHint: String

    /// The first-goalscorer card's own words.
    static let firstGoalscorer = FirstScorerOutcomeContext10868(
        pregameTitle: FirstScorerComparisonInput10868.pregameTitle,
        currentTitle: FirstScorerComparisonInput10868.recordedTitle,
        liveResultTitle: FirstScorerComparisonInput10868.liveResultTitle,
        finalResultTitle: FirstScorerComparisonInput10868.finalResultTitle,
        selectionUnavailable: FirstScorerComparisonInput10868.selectionUnavailable,
        spokenPregame: FirstScorerComparisonInput10868.spokenPregame,
        spokenCurrent: FirstScorerComparisonInput10868.spokenRecorded,
        spokenResult: FirstScorerComparisonInput10868.spokenResult,
        selectHint: FirstScorerComparisonInput10868.selectPlayerHint
    )
}

/// One owner-admitted score observation. Shown verbatim: the score is never
/// computed, the time never parsed, and neither implies when a goal was scored.
nonisolated struct FirstScorerScoreObservation10868: Equatable {
    /// Opaque owner identity.
    let id: String
    /// The full score as supplied ("1–0").
    let score: String
    /// The short observation time ("5:17 AM", "Time not recorded").
    let time: String
    /// Full provenance for VoiceOver ("Valladolid 1, Albacete 0 · observed Oct
    /// 12, 5:17 AM PT").
    let accessibilityText: String
}

/// The observed scores in the owner's order and membership.
nonisolated struct FirstScorerScorePath10868: Equatable {
    /// "Observed scores"
    let title: String
    /// "Observation times, not exact goal times."
    let note: String?
    let observations: [FirstScorerScoreObservation10868]
}

/// One player of the first-scorer market. Each reading carries its own missing
/// words. `current` is read only during play; `result` during play once
/// admitted, and after the final.
nonisolated struct FirstScorerRow10868: Equatable {
    /// Opaque original first-scorer prop identity, passed back exactly.
    let id: String
    let name: String
    /// "Minnesota", "Team unavailable"; nil draws no team line.
    let team: String?
    let pregame: FirstScorerObservation10868?
    let pregameMissing: String
    let current: FirstScorerCurrent10868
    let result: FirstScorerResult10868
}

nonisolated enum FirstScorerPhase10868: Equatable {
    case before
    case during
    case final
}

nonisolated struct FirstScorerTick10868: Equatable {
    /// Raw probability, in the same units as the axis bounds.
    let value: Double
    /// The owner's label ("5%").
    let text: String
}

/// The plot's shared scale: raw bounds plus the owner's formatted ticks.
nonisolated struct FirstScorerAxis10868: Equatable {
    let lower: Double
    let upper: Double
    let ticks: [FirstScorerTick10868]

    /// A probability scale: finite, nonempty and inside 0...1. Anything else
    /// draws no marks or ticks — the bounds are never clamped or normalized.
    var isValid: Bool {
        lower.isFinite && upper.isFinite && lower >= 0 && upper <= 1 && upper > lower
    }
}

/// The owner's confirmed first scorer, supplied only when exactly one has been
/// admitted. Not checked against the rows here.
nonisolated struct FirstScorerConfirmed10868: Equatable {
    let id: String
    let name: String
    /// "First goalscorer · confirmed result".
    let caption: String
}

/// The owner's timing disclosure for one player. Shown only while that exact
/// player is the resolved selection.
nonisolated struct FirstScorerTiming10868: Equatable {
    let playerID: String
    /// "Kirill Kaprizov · probability timing".
    let title: String
    let lines: [String]
}

nonisolated enum FirstScorerSelection10868: Equatable {
    case none
    /// The selected player is one plot row.
    case overview(FirstScorerRow10868)
    /// The selected player is not in the plot; only the named comparison shows.
    case outside(FirstScorerRow10868)
    /// No row carries the selected id.
    case missing(String)
    /// More than one plot row carries the selected id.
    case duplicate(String)

    var row: FirstScorerRow10868? {
        switch self {
        case .overview(let row), .outside(let row): row
        case .none, .missing, .duplicate: nil
        }
    }
}

nonisolated enum FirstScorerReading10868: Equatable {
    case value(FirstScorerObservation10868)
    case missing(String)

    var text: String {
        switch self {
        case .value(let observation): observation.text
        case .missing(let text): text
        }
    }
}

/// What sits beside the pregame chance in the selected comparison.
nonisolated enum FirstScorerSecondReading10868: Equatable {
    /// During play, before an admitted result.
    case current(FirstScorerReading10868)
    /// An admitted result during play, or any result after the final.
    case result(FirstScorerResult10868)
}

nonisolated enum FirstScorerAction10868: Equatable {
    case select(String)
    case details(String)

    func perform(onSelect: ((String) -> Void)?, onDetails: ((String) -> Void)?) {
        switch self {
        case .select(let id): onSelect?(id)
        case .details(let id): onDetails?(id)
        }
    }
}

nonisolated enum FirstScorerTimingPresentation10868: Equatable {
    /// The page owns the expanded flag.
    case disclosure(FirstScorerTiming10868)
    /// No binding: the owner's timing content, already expanded.
    case expanded(FirstScorerTiming10868)
}

nonisolated struct FirstScorerComparisonInput10868: Equatable {
    let phase: FirstScorerPhase10868
    /// "Who scored first?"
    let title: String
    /// "Kalshi · first goalscorer".
    let context: String?
    /// The plot's rows in the owner's order — never sorted, filtered or capped here.
    let overview: [FirstScorerRow10868]
    /// The owner's exact selection.
    let selectedID: String?
    /// The selected player's row when it is not in the plot. Read only when
    /// `selectedID` is absent from the overview.
    let selectedRow: FirstScorerRow10868?
    /// "Highest captured pregame chances".
    let plotTitle: String?
    let axis: FirstScorerAxis10868
    /// "25 of 36 players have a captured pregame trade."
    let coverage: String?
    let confirmed: FirstScorerConfirmed10868?
    let timing: FirstScorerTiming10868?
    /// The caller's outcome words. Nil keeps the first-goalscorer card as it is.
    let outcome: FirstScorerOutcomeContext10868?
    /// Owner-admitted score checkpoints, shown during play only.
    let scorePath: FirstScorerScorePath10868?

    init(
        phase: FirstScorerPhase10868,
        title: String,
        context: String?,
        overview: [FirstScorerRow10868],
        selectedID: String?,
        selectedRow: FirstScorerRow10868?,
        plotTitle: String?,
        axis: FirstScorerAxis10868,
        coverage: String?,
        confirmed: FirstScorerConfirmed10868?,
        timing: FirstScorerTiming10868?,
        outcome: FirstScorerOutcomeContext10868? = nil,
        scorePath: FirstScorerScorePath10868? = nil
    ) {
        self.phase = phase
        self.title = title
        self.context = context
        self.overview = overview
        self.selectedID = selectedID
        self.selectedRow = selectedRow
        self.plotTitle = plotTitle
        self.axis = axis
        self.coverage = coverage
        self.confirmed = confirmed
        self.timing = timing
        self.outcome = outcome
        self.scorePath = scorePath
    }

    static let pregameTitle = "Pregame chance"
    static let recordedTitle = "Recorded in-game"
    static let liveResultTitle = "First-goalscorer result"
    static let finalResultTitle = "Final result"
    static let selectionUnavailable = "Selected player unavailable."
    static let spokenPregame = "Pregame first-goalscorer chance"
    static let spokenRecorded = "Recorded in-game first-goalscorer chance"
    static let spokenResult = "First-goalscorer result"
    static let selectPlayerHint = "Selects this player’s comparison"

    /// The words in use: the caller's, or the first-goalscorer card's own.
    var words: FirstScorerOutcomeContext10868 { outcome ?? .firstGoalscorer }

    /// Each plot row shows its own phase reading only when the caller chose an
    /// outcome context.
    var showsRowReadings: Bool { outcome != nil }

    /// Exact id only. A missing or duplicated id gets no substitute player.
    var selection: FirstScorerSelection10868 {
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

    func isSelected(_ row: FirstScorerRow10868) -> Bool {
        if case .overview(let selected) = selection { return selected.id == row.id }
        return false
    }

    var selectionNotice: String? {
        switch selection {
        case .missing, .duplicate: words.selectionUnavailable
        case .none, .overview, .outside: nil
        }
    }

    func pregameReading(_ row: FirstScorerRow10868) -> FirstScorerReading10868 {
        row.pregame.map { .value($0) } ?? .missing(row.pregameMissing)
    }

    /// Nil before play — no current, result or actual column. During play an
    /// admitted result replaces the in-game reading (a resolved market's price
    /// is a settlement, not a chance); otherwise the owner's in-game state.
    /// After the final, the result alone.
    func secondReading(_ row: FirstScorerRow10868) -> FirstScorerSecondReading10868? {
        switch phase {
        case .before:
            return nil
        case .during:
            if row.result.isAdmitted { return .result(row.result) }
            switch row.current {
            case .recorded(let observation): return .current(.value(observation))
            case .unavailable(let text), .stale(let text): return .current(.missing(text))
            }
        case .final:
            return .result(row.result)
        }
    }

    /// The filled in-game key appears only beside an admitted recorded observation.
    func showsCurrentMark(_ row: FirstScorerRow10868) -> Bool {
        if case .current(.value)? = secondReading(row) { return true }
        return false
    }

    var resultTitle: String {
        phase == .final ? words.finalResultTitle : words.liveResultTitle
    }

    /// Spoken before a result. With an outcome context the final announces the
    /// caller's final title, so a final reads as final; during play, and on the
    /// first-goalscorer card without a context, the spoken result title.
    var spokenResultTitle: String {
        outcome != nil && phase == .final ? words.finalResultTitle : words.spokenResult
    }

    /// A plot row's own reading under its track: nil before play and without
    /// an outcome context; otherwise the same reading the selected comparison
    /// would show for it.
    func rowReading(_ row: FirstScorerRow10868) -> FirstScorerSecondReading10868? {
        showsRowReadings ? secondReading(row) : nil
    }

    /// The observed scores, during play only. Before play every supplied later
    /// checkpoint stays hidden; after the final the card returns to the
    /// original results. An empty list shows nothing — no 0–0 is made up.
    var visibleScorePath: FirstScorerScorePath10868? {
        guard phase == .during, let scorePath, !scorePath.observations.isEmpty else { return nil }
        return scorePath
    }

    /// The confirmed-winner return appears once a result can exist, and never
    /// for the player already selected — so the winner is not named twice.
    var confirmedShortcut: FirstScorerConfirmed10868? {
        guard phase != .before, let confirmed, selectedID != confirmed.id else { return nil }
        return confirmed
    }

    /// Timing only for the exact resolved selection.
    func timingPresentation(hasBinding: Bool) -> FirstScorerTimingPresentation10868? {
        guard let timing, let selected = selection.row, selected.id == timing.playerID else { return nil }
        return hasBinding ? .disclosure(timing) : .expanded(timing)
    }

    func rowAction(_ row: FirstScorerRow10868, canSelect: Bool) -> FirstScorerAction10868? {
        canSelect ? .select(row.id) : nil
    }

    func confirmedAction(canSelect: Bool) -> FirstScorerAction10868? {
        guard canSelect, let confirmed = confirmedShortcut else { return nil }
        return .select(confirmed.id)
    }

    func detailsAction(canOpenDetails: Bool) -> FirstScorerAction10868? {
        guard canOpenDetails, let row = selection.row else { return nil }
        return .details(row.id)
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        ([context, title].compactMap { $0 }).joined(separator: ". ")
    }

    func accessibilityLabel(for row: FirstScorerRow10868) -> String {
        ([row.name, row.team].compactMap { $0 }).joined(separator: ", ")
    }

    /// A plot row: its pregame chance, then — with an outcome context — its
    /// own phase reading.
    func accessibilityValue(for row: FirstScorerRow10868) -> String {
        showsRowReadings ? accessibilityComparison(for: row) : Self.spoken(pregameReading(row), title: words.spokenPregame)
    }

    /// The selected comparison: baseline, then the separately timed in-game
    /// chance or the result.
    func accessibilityComparison(for row: FirstScorerRow10868) -> String {
        var parts = [Self.spoken(pregameReading(row), title: words.spokenPregame)]
        switch secondReading(row) {
        case .current(let reading)?: parts.append(Self.spoken(reading, title: words.spokenCurrent))
        case .result(let result)?: parts.append("\(spokenResultTitle): \(result.text)")
        case nil: break
        }
        return parts.joined(separator: "; ")
    }

    func accessibilityConfirmed(_ confirmed: FirstScorerConfirmed10868) -> String {
        "\(confirmed.caption): \(confirmed.name)"
    }

    private static func spoken(_ reading: FirstScorerReading10868, title: String) -> String {
        switch reading {
        case .value(let observation): "\(title): \(observation.text), \(observation.accessibilityDetail)"
        case .missing(let text): "\(title): \(text)"
        }
    }
}

/// A tick the axis can place: its position on the track and the owner's label.
nonisolated struct FirstScorerPlacedTick10868: Equatable {
    let fraction: Double
    let text: String
}

nonisolated enum FirstScorerGeometry10868 {
    static let markDiameter: CGFloat = 8
    static let markLineWidth: CGFloat = 2

    /// Clear space at each end of the track so a mark at either bound sits
    /// wholly inside it: half the mark plus half its stroke.
    static var trackInset: CGFloat { (markDiameter + markLineWidth) / 2 }

    /// Where a raw value sits on the axis, 0...1. Nil for an invalid axis or a
    /// non-finite or out-of-domain value — the mark is omitted, never clamped
    /// or drawn at zero.
    static func fraction(_ value: Double, axis: FirstScorerAxis10868) -> Double? {
        guard axis.isValid, value.isFinite, value >= axis.lower, value <= axis.upper else { return nil }
        return (value - axis.lower) / (axis.upper - axis.lower)
    }

    /// The x of a fraction within a track of this width, inside the end insets.
    static func x(_ fraction: Double, width: CGFloat, inset: CGFloat = trackInset) -> CGFloat? {
        let usable = width - 2 * inset
        guard usable.isFinite, usable > 0, fraction.isFinite, fraction >= 0, fraction <= 1 else { return nil }
        return inset + usable * CGFloat(fraction)
    }

    /// The ticks that can be placed, in the owner's order.
    static func visibleTicks(_ axis: FirstScorerAxis10868) -> [FirstScorerPlacedTick10868] {
        axis.ticks.compactMap { tick in
            fraction(tick.value, axis: axis).map { FirstScorerPlacedTick10868(fraction: $0, text: tick.text) }
        }
    }

    /// Where each tick label goes. A label is centred on its gridline and kept
    /// inside the plot; when it would overlap a label already placed on a row
    /// it drops to the next row rather than moving away from its gridline or
    /// shrinking. A label wider than the whole plot gets its own row at the
    /// leading edge, at the size it takes when offered the plot width (it
    /// wraps); if even that is wider, the plan's width says so instead of
    /// hiding the overflow. Every label is placed, in the owner's order, and
    /// owner ticks need not be sorted.
    ///
    /// - Parameters:
    ///   - centers: each label's gridline x, in the owner's order.
    ///   - natural: each label's one-line size.
    ///   - atWidth: each label's size when offered `width`; read only for a
    ///     label whose natural width exceeds `width`.
    static func labelPlan(centers: [CGFloat], natural: [CGSize], atWidth: [CGSize],
                          width: CGFloat, gap: CGFloat = 4, rowGap: CGFloat = 2) -> FirstScorerLabelPlan10868 {
        guard centers.count == natural.count, centers.count == atWidth.count, !centers.isEmpty else {
            return FirstScorerLabelPlan10868(placements: [], size: .zero)
        }
        let width = width.isFinite ? max(0, width) : 0
        // Left to right by gridline; ties keep the owner's order.
        let order = centers.indices.sorted { a, b in
            let ca = centers[a].isFinite ? centers[a] : 0
            let cb = centers[b].isFinite ? centers[b] : 0
            return ca == cb ? a < b : ca < cb
        }
        var rowEnds: [CGFloat] = []   // trailing edge of the last label on each row; .infinity = full
        var rowHeights: [CGFloat] = []
        var assigned = [(row: Int, x: CGFloat, size: CGSize, wrapped: Bool)](
            repeating: (0, 0, CGSize.zero, false), count: centers.count)
        for i in order {
            let label = natural[i]
            if label.width > width {
                rowEnds.append(.infinity)
                rowHeights.append(atWidth[i].height)
                assigned[i] = (rowEnds.count - 1, 0, atWidth[i], true)
                continue
            }
            let center = centers[i].isFinite ? centers[i] : 0
            let x = min(max(0, center - label.width / 2), width - label.width)
            let row: Int
            if let free = rowEnds.firstIndex(where: { $0 + gap <= x }) {
                row = free
                rowHeights[row] = max(rowHeights[row], label.height)
            } else {
                rowEnds.append(0)
                rowHeights.append(label.height)
                row = rowEnds.count - 1
            }
            rowEnds[row] = x + label.width
            assigned[i] = (row, x, label, false)
        }
        var rowTops: [CGFloat] = []
        var y: CGFloat = 0
        for height in rowHeights {
            rowTops.append(y)
            y += height + rowGap
        }
        let placements = assigned.enumerated().map { index, a in
            FirstScorerLabelPlacement10868(index: index, origin: CGPoint(x: a.x, y: rowTops[a.row]),
                                           size: a.size, row: a.row, wrapped: a.wrapped)
        }
        let extent = placements.map { $0.origin.x + $0.size.width }.max() ?? 0
        return FirstScorerLabelPlan10868(placements: placements,
                                         size: CGSize(width: max(width, extent), height: max(0, y - rowGap)))
    }

    /// Where each observed score goes: left to right in the owner's order,
    /// starting a new row when the next one would not fit whole. Nothing is
    /// shrunk, capped or dropped. One wider than the whole width takes a row
    /// of its own at the size it takes when offered the width (it wraps); if
    /// even that is wider, the plan's width says so instead of hiding it.
    ///
    /// - Parameters:
    ///   - natural: each entry's one-line size, in the owner's order.
    ///   - atWidth: each entry's size when offered `width`; read only for an
    ///     entry whose natural width exceeds `width`.
    static func flowPlan(natural: [CGSize], atWidth: [CGSize], width: CGFloat,
                         spacing: CGFloat = 8, rowSpacing: CGFloat = 8) -> FirstScorerFlowPlan10868 {
        guard natural.count == atWidth.count, !natural.isEmpty else {
            return FirstScorerFlowPlan10868(frames: [], size: .zero)
        }
        let width = width.isFinite ? max(0, width) : 0
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for (one, wrapped) in zip(natural, atWidth) {
            let size = one.width > width ? wrapped : one
            if x > 0, x + size.width > width {
                y += rowHeight + rowSpacing
                x = 0
                rowHeight = 0
            }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        let extent = frames.map(\.maxX).max() ?? 0
        return FirstScorerFlowPlan10868(frames: frames, size: CGSize(width: max(width, extent), height: y + rowHeight))
    }
}

/// Every observed score placed, in the owner's order, and the block they need.
nonisolated struct FirstScorerFlowPlan10868: Equatable {
    let frames: [CGRect]
    let size: CGSize
}

/// One tick label's place in the label block.
nonisolated struct FirstScorerLabelPlacement10868: Equatable {
    /// The owner's tick index.
    let index: Int
    /// Top-leading corner within the label block.
    let origin: CGPoint
    /// The size the label is given — its one-line size, or its size at the
    /// plot width when it is wider than the plot.
    let size: CGSize
    let row: Int
    /// Wider than the plot, so offered the plot width on a row of its own.
    let wrapped: Bool
}

/// Every tick label placed, in the owner's order, and the block they need.
nonisolated struct FirstScorerLabelPlan10868: Equatable {
    let placements: [FirstScorerLabelPlacement10868]
    /// The space actually used: every row's height, and the plot width or a
    /// wider label's extent if one is wider than even its wrapped size.
    let size: CGSize
}

/// Tick labels laid out over the track: one subview per visible tick, in order.
/// The size it reports is the plan it places, rows included.
struct FirstScorerAxisLabelsLayout10868: Layout {
    let fractions: [Double]
    var gap: CGFloat = 4
    var rowGap: CGFloat = 2

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let natural = subviews.map { $0.sizeThatFits(.unspecified) }
        let oneRow = natural.map(\.width).reduce(0, +) + gap * CGFloat(max(0, natural.count - 1))
        let width = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? oneRow
        return plan(width: width, subviews: subviews)?.size ?? CGSize(width: width, height: 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let plan = plan(width: bounds.width, subviews: subviews) else { return }
        for (subview, placement) in zip(subviews, plan.placements) {
            subview.place(at: CGPoint(x: bounds.minX + placement.origin.x, y: bounds.minY + placement.origin.y),
                          anchor: .topLeading,
                          proposal: ProposedViewSize(width: placement.size.width, height: placement.size.height))
        }
    }

    private func plan(width: CGFloat, subviews: Subviews) -> FirstScorerLabelPlan10868? {
        guard subviews.count == fractions.count, !subviews.isEmpty else { return nil }
        let natural = subviews.map { $0.sizeThatFits(.unspecified) }
        let atWidth = zip(subviews, natural).map { subview, size in
            size.width > width ? subview.sizeThatFits(ProposedViewSize(width: width, height: nil)) : size
        }
        let centers = fractions.map { FirstScorerGeometry10868.x($0, width: width) ?? 0 }
        return FirstScorerGeometry10868.labelPlan(centers: centers, natural: natural, atWidth: atWidth,
                                                  width: width, gap: gap, rowGap: rowGap)
    }
}

/// The observed scores laid out as wrapping rows: one subview per entry, in
/// order. The size it reports is the plan it places, rows included.
struct FirstScorerFlowLayout10868: Layout {
    var spacing: CGFloat = 8
    var rowSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let natural = subviews.map { $0.sizeThatFits(.unspecified) }
        let oneRow = natural.map(\.width).reduce(0, +) + spacing * CGFloat(max(0, natural.count - 1))
        let width = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? oneRow
        return plan(width: width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let plan = plan(width: bounds.width, subviews: subviews)
        for (subview, frame) in zip(subviews, plan.frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading,
                          proposal: ProposedViewSize(width: frame.width, height: frame.height))
        }
    }

    private func plan(width: CGFloat, subviews: Subviews) -> FirstScorerFlowPlan10868 {
        let natural = subviews.map { $0.sizeThatFits(.unspecified) }
        let atWidth = zip(subviews, natural).map { subview, size in
            size.width > width ? subview.sizeThatFits(ProposedViewSize(width: width, height: nil)) : size
        }
        return FirstScorerGeometry10868.flowPlan(natural: natural, atWidth: atWidth, width: width,
                                                 spacing: spacing, rowSpacing: rowSpacing)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum FirstScorerAccessibilityID10868 {
    static func row(_ id: String) -> String { "firstScorer10868.row.\(id)" }
    static func comparison(_ id: String) -> String { "firstScorer10868.comparison.\(id)" }
    static func confirmed(_ id: String) -> String { "firstScorer10868.confirmed.\(id)" }
    static func details(_ id: String) -> String { "firstScorer10868.details.\(id)" }
    static func score(_ id: String) -> String { "firstScorer10868.score.\(id)" }
}

struct FirstScorerComparisonPresentation10868: View {
    let input: FirstScorerComparisonInput10868
    var onSelect: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil
    /// Page-owned. Nil shows the owner's timing content already expanded.
    var timingExpanded: Binding<Bool>? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 30
    @ScaledMetric(relativeTo: .title3) private var resultSize: CGFloat = 22
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 28

    private var canSelect: Bool { onSelect != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if let confirmed = input.confirmedShortcut {
                confirmedReturn(confirmed)
            }
            if let notice = input.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let row = input.selection.row {
                comparison(row)
            }
            if !input.overview.isEmpty {
                plot
            }
            if let coverage = input.coverage {
                Text(coverage)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let path = input.visibleScorePath {
                scorePath(path)
            }
            timing
            if let row = input.selection.row {
                detailsButton(row)
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

    // MARK: Confirmed first scorer

    /// A compact return to the confirmed first scorer; static context when the
    /// owner gave no selection callback.
    private func confirmedReturn(_ confirmed: FirstScorerConfirmed10868) -> some View {
        let action = input.confirmedAction(canSelect: canSelect)
        return control(action) {
            HStack(alignment: .center, spacing: 14) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.title2)
                    .foregroundStyle(DS.emeraldDark)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text(confirmed.name).font(.headline).foregroundStyle(DS.textPrimary)
                    Text(confirmed.caption).font(.caption).foregroundStyle(DS.textSecondary)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilityConfirmed(confirmed))
        .accessibilityHint(action == nil ? "" : input.words.selectHint)
        .accessibilityIdentifier(FirstScorerAccessibilityID10868.confirmed(confirmed.id))
    }

    // MARK: Selected comparison

    private func comparison(_ row: FirstScorerRow10868) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.name).font(.headline).foregroundStyle(DS.textPrimary)
                if let team = row.team {
                    Text(team).font(.subheadline).foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 14) { comparisonValues(row) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { comparisonValues(row) }
                    VStack(alignment: .leading, spacing: 14) { comparisonValues(row) }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.accessibilityLabel(for: row))
        .accessibilityValue(input.accessibilityComparison(for: row))
        .accessibilityIdentifier(FirstScorerAccessibilityID10868.comparison(row.id))
    }

    @ViewBuilder private func comparisonValues(_ row: FirstScorerRow10868) -> some View {
        let second = input.secondReading(row)
        // The hollow/filled key only when two chances can sit side by side.
        chanceValue(
            input.pregameReading(row),
            title: input.words.pregameTitle,
            mark: input.phase == .during ? .hollow : nil
        )
        switch second {
        case .current(let reading)?:
            chanceValue(
                reading,
                title: input.words.currentTitle,
                mark: input.showsCurrentMark(row) ? .filled : nil
            )
        case .result(let result)?:
            resultValue(result)
        case nil:
            EmptyView()
        }
    }

    private enum KeyMark { case hollow, filled }

    private func chanceValue(_ reading: FirstScorerReading10868, title: String, mark: KeyMark?) -> some View {
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
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The owner's result words — never a 0% or 100%. Unconfirmed reads as status.
    private func resultValue(_ result: FirstScorerResult10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(input.resultTitle).font(.caption).foregroundStyle(DS.textSecondary)
            if result.isAdmitted {
                Text(result.text)
                    .font(.system(size: resultSize, weight: .bold))
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
            Circle().fill(DS.cardBg).overlay(Circle().stroke(DS.textSecondary, lineWidth: 2)).frame(width: 9, height: 9)
        case .filled:
            Circle().fill(DS.textSecondary).frame(width: 9, height: 9)
        }
    }

    // MARK: Baseline plot

    private var plot: some View {
        let ticks = FirstScorerGeometry10868.visibleTicks(input.axis)
        let fractions = ticks.map { $0.fraction }
        return VStack(alignment: .leading, spacing: 6) {
            Divider()
            if let plotTitle = input.plotTitle {
                Text(plotTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !ticks.isEmpty {
                FirstScorerAxisLabelsLayout10868(fractions: fractions) {
                    ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.text)
                            .font(.caption)
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.horizontal, 8)
                .accessibilityHidden(true)
            }
            ForEach(Array(input.overview.enumerated()), id: \.offset) { _, row in
                plotRow(row, ticks: fractions)
            }
        }
    }

    private func plotRow(_ row: FirstScorerRow10868, ticks: [Double]) -> some View {
        let selected = input.isSelected(row)
        let action = input.rowAction(row, canSelect: canSelect)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) { plotLabels(row, selected: selected) }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            plotLabels(row, selected: selected, spaced: true)
                        }
                        VStack(alignment: .leading, spacing: 4) { plotLabels(row, selected: selected) }
                    }
                }
                track(row, ticks: ticks)
                rowReading(row)
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(selected ? DS.blue.opacity(0.06) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
            // A durable leading bar marks selection without relying on colour.
            .overlay(alignment: .leading) {
                if selected {
                    Rectangle().fill(DS.textPrimary).frame(width: 3)
                }
            }
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilityLabel(for: row))
        .accessibilityValue(input.accessibilityValue(for: row))
        .accessibilityHint(action == nil ? "" : input.words.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(FirstScorerAccessibilityID10868.row(row.id))
    }

    /// Name, then the direct value at its whole intrinsic width.
    @ViewBuilder private func plotLabels(_ row: FirstScorerRow10868, selected: Bool, spaced: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(row.name)
                .font(.subheadline.weight(selected ? .semibold : .regular))
                .underline(selected)
                .foregroundStyle(DS.textPrimary)
            if let team = row.team {
                Text(team).font(.caption).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        if spaced { Spacer(minLength: 0) }
        switch input.pregameReading(row) {
        case .value(let observation):
            Text(observation.text)
                .font(.title3.bold())
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
        case .missing(let text):
            Text(text)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Gridlines at the owner's ticks, a stem from the lower bound and a hollow
    /// pregame mark. Nothing is drawn for a value the axis cannot place.
    private func track(_ row: FirstScorerRow10868, ticks: [Double]) -> some View {
        let fraction = row.pregame.flatMap { FirstScorerGeometry10868.fraction($0.probability, axis: input.axis) }
        return GeometryReader { geo in
            let width = geo.size.width
            let mid = geo.size.height / 2
            Path { path in
                for tick in ticks {
                    guard let x = FirstScorerGeometry10868.x(tick, width: width) else { continue }
                    path.move(to: CGPoint(x: x, y: 2))
                    path.addLine(to: CGPoint(x: x, y: geo.size.height - 2))
                }
            }
            .stroke(DS.border, style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
            if let fraction, let start = FirstScorerGeometry10868.x(0, width: width),
               let x = FirstScorerGeometry10868.x(fraction, width: width) {
                Path { path in
                    path.move(to: CGPoint(x: start, y: mid))
                    path.addLine(to: CGPoint(x: x, y: mid))
                }
                .stroke(DS.blue.opacity(0.5), lineWidth: 1.5)
                Circle()
                    .fill(DS.cardBg)
                    .overlay(Circle().stroke(DS.blue, lineWidth: FirstScorerGeometry10868.markLineWidth))
                    .frame(width: FirstScorerGeometry10868.markDiameter, height: FirstScorerGeometry10868.markDiameter)
                    .position(x: x, y: mid)
            }
        }
        .frame(height: trackHeight)
        .accessibilityHidden(true)
    }

    /// The row's own phase reading, under its track: a current chance or its
    /// words during play, or the owner's result. Nothing before play.
    @ViewBuilder private func rowReading(_ row: FirstScorerRow10868) -> some View {
        switch input.rowReading(row) {
        case .current(let reading)?:
            HStack(alignment: .center, spacing: 5) {
                if input.showsCurrentMark(row) { keyMark(.filled) }
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 2) { rowCurrent(reading) }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) { rowCurrent(reading) }
                        VStack(alignment: .leading, spacing: 2) { rowCurrent(reading) }
                    }
                }
            }
        case .result(let result)?:
            resultLine(result)
        case nil:
            EmptyView()
        }
    }

    @ViewBuilder private func rowCurrent(_ reading: FirstScorerReading10868) -> some View {
        Text(input.words.currentTitle)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
        switch reading {
        case .value(let observation):
            Text(observation.text)
                .font(.footnote.bold())
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
        case .missing(let text):
            Text(text)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// ✓ or ✕ and the owner's words; unconfirmed is plain secondary status.
    private func resultLine(_ result: FirstScorerResult10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            switch result.mark {
            case .positive?:
                Image(systemName: "checkmark.circle").accessibilityHidden(true)
            case .negative?:
                Image(systemName: "xmark.circle").accessibilityHidden(true)
            case nil:
                EmptyView()
            }
            Text(result.text).fixedSize(horizontal: false, vertical: true)
        }
        .font(.footnote)
        .foregroundStyle(result.mark == .positive ? DS.textPrimary : DS.textSecondary)
    }

    // MARK: Observed scores

    /// The owner's score checkpoints as a wrapping sequence. Static: it never
    /// selects, and each entry is read with its full provenance.
    private func scorePath(_ path: FirstScorerScorePath10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(path.title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            FirstScorerFlowLayout10868 {
                ForEach(Array(path.observations.enumerated()), id: \.offset) { _, observation in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(observation.score)
                            .font(.title3.bold())
                            .monospacedDigit()
                            .foregroundStyle(DS.textPrimary)
                        Text(observation.time)
                            .font(.caption)
                            .monospacedDigit()
                            .foregroundStyle(DS.textSecondary)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(DS.surface, in: RoundedRectangle(cornerRadius: 8))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(observation.accessibilityText)
                    .accessibilityIdentifier(FirstScorerAccessibilityID10868.score(observation.id))
                }
            }
            if let note = path.note {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
    }

    // MARK: Details and timing

    @ViewBuilder private func detailsButton(_ row: FirstScorerRow10868) -> some View {
        if let action = input.detailsAction(canOpenDetails: canOpenDetails) {
            Button {
                action.perform(onSelect: onSelect, onDetails: onDetails)
            } label: {
                HStack {
                    Text("\(row.name) · original prop & result")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.footnote)
                .foregroundStyle(DS.blue)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier(FirstScorerAccessibilityID10868.details(row.id))
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

    private func timingLines(_ content: FirstScorerTiming10868) -> some View {
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
    private func control<Content: View>(_ action: FirstScorerAction10868?, @ViewBuilder content: () -> Content) -> some View {
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
