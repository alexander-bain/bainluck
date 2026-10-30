import SwiftUI

// #10868 — "Hundredths from a medal": the Olympic 500m final card. A fan reads
// a skater's actual finishing time and reported medal or rank beside that
// skater's separately labelled gold chance before race day, then compares the
// time behind gold for the owner's visible finishers as horizontal bars on one
// shared seconds scale (shorter is faster).
//
// Presentation only, from the approved `SkatingRace.tsx` `finish` card and
// `skatingRace.css` (`.sk-finish-reading`, `.sk-gap-label`, `.sk-gap-plot`,
// selected bar treatment, larger-text variants). The reference's top-five plus
// selected group election, gap arithmetic from milliseconds, axis ceiling and
// tick rounding, medal words, baseline election and percent formatting
// (`skatingEvidence.ts`) are NOT ported. All of that arrives as owner input:
// the canonical reported-result catalogue, the selected exact result, the
// visible group in the owner's order, each result's exact time and standing
// words, its numeric gap beside the owner's own gap words, its preformatted
// earlier gold reading and optional linked gold original, the shared axis with
// its tick labels, and every label and absence word.
//
// A reported result is identified by the owner's scope and the result report's
// own id — a different namespace from the gold originals. A result reference
// that does not resolve to exactly one catalogue record in the same scope —
// missing, withdrawn, out of scope, duplicated or blank — shows the owner's
// unavailable words with no bar and no action; its neighbours keep theirs. No
// first, default or nearest result stands in for it.
//
// Actual seconds and gold chances are different subjects. The time and
// standing are shown verbatim and are never turned into a probability or a
// projected time; the gold chance is the owner's reading, verbatim, and a
// missing one stays the owner's words — never zero, never inferred from a
// medal, never normalized or complemented. A gap's seconds are used for bar
// geometry only. Every bar shares the owner's ONE axis, 0 to its upper end; no
// row is rescaled. A real zero gap draws its zero endpoint; a gap that is not
// finite, is negative or lies past the axis draws no bar, only the owner's
// words; an invalid axis draws no bars at all and every row stays listed with
// its exact time and gap words.
//
// Tick labels are measured onto the bars' inset by the shared
// `FieldExpectationsAxisLayout10868`; one that collides with a label already
// placed, or is wider than the row, is left out rather than overlapped.
//
// The bars are decorative: the selected reading and every row speak actual
// seconds, reported standing and the separately dated gold chance whole. The
// host owns the scroll, the reader, selected state, all-finishers browsing,
// results and sources, the original-history reader, Back and focus; this leaf
// keeps no state and runs no animation. With no callback, nothing pretends to
// act.
//
// Host binding still owed — not available at this base: an owner must supply
// the reported results by result-report identity, the provider gold originals
// mapped through the existing production identity path (a name, a medal or an
// index is never a link), each skater's admitted before-race-day reading with
// its own clock, the owner's visible group, gaps and axis.

/// One reported result's exact identity. Never a market id, a name or an index.
nonisolated struct TimedFinishResultRef10868: Hashable {
    /// The owner's opaque exact scope (event and held report).
    let scope: String
    /// The result report's own id.
    let resultID: String

    /// Every part present. A blank part is never an identity.
    var isComplete: Bool {
        [scope, resultID].allSatisfy { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }
}

/// The owner's time behind gold for one result. Never a chance.
nonisolated struct TimedFinishGap10868: Equatable {
    /// Seconds behind the winner, for bar geometry only.
    let seconds: Double
    /// The owner's words ("+0.78s", "Winner").
    let text: String
}

/// One canonical reported result.
nonisolated struct TimedFinishResult10868: Equatable {
    let ref: TimedFinishResultRef10868
    /// The full name; never truncated or shortened.
    let name: String
    /// "Japan"; nil draws none.
    let detail: String?
    /// The exact reported time, verbatim ("37.914").
    let time: String
    /// The owner's medal or rank words ("Bronze", "Tied 11th").
    let standing: String
    /// Nil when the owner has no gap for this result.
    let gap: TimedFinishGap10868?
    /// The skater's own earlier gold reading ("Gold chance before race day",
    /// `.recorded("78%", "Feb 14, 11:45 PM Milan · Polymarket")`) or its own
    /// absence words (`.missing("No linked gold prop")`).
    let goldChance: FieldChooserReading10868
    /// The linked gold original, handed back unchanged; nil when none is linked.
    let original: FieldChooserOriginalRef10868?
}

/// One owner tick on the gap axis.
nonisolated struct TimedFinishTick10868: Equatable {
    let seconds: Double
    /// "0.45s".
    let label: String
}

/// The owner's one gap axis for every bar on the card.
nonisolated struct TimedFinishAxis10868: Equatable {
    /// The upper end in seconds; the lower end is 0.
    let upper: Double
    let ticks: [TimedFinishTick10868]

    var isValid: Bool { upper.isFinite && upper > 0 }
}

/// The host's selected result.
nonisolated struct TimedFinishSelected10868: Equatable {
    let ref: TimedFinishResultRef10868
    /// The owner's words on the selected row ("Selected"); nil draws none.
    let words: String?
    /// Shown when the selected reference does not resolve.
    let unavailableWords: String
}

/// The owner's words for this card.
nonisolated struct TimedFinishCopy10868: Equatable {
    /// "ACTUAL RACE · SECONDS"; nil draws none.
    let eyebrow: String?
    /// "Hundredths from a medal".
    let title: String
    /// The unit beside an actual time ("s").
    let timeUnit: String
    /// Spoken before an actual time ("Actual time").
    let timeLabel: String
    /// Spoken after an actual time ("seconds").
    let timeSpokenUnit: String
    /// Spoken before a standing ("Reported").
    let standingLabel: String
    /// "Time behind gold · shorter is faster".
    let gapLabel: String
    /// Spoken name of the rows ("Actual time behind gold").
    let graphicLabel: String
    /// "Finishing times, not probabilities"; nil draws none.
    let distinction: String?
    /// A result with no gap ("Gap not reported").
    let noGap: String
    /// A gap that cannot be placed ("Not drawn on this scale").
    let offAxis: String
    /// Shown once when the axis is absent or invalid ("Times listed without the scale").
    let axisUnavailable: String
    /// No visible rows ("No reported finishers in this view").
    let empty: String
    /// "Pergher missed bronze by 0.03s"; nil draws none.
    let note: String?
    /// "Explore this skater’s gold history".
    let openOriginal: String
    let openOriginalHint: String?
    /// A selected result with no linked original ("No linked gold prop for this skater").
    let noOriginal: String
    /// Spoken hint on a row that chooses; nil none.
    let chooseHint: String?
}

nonisolated struct TimedFinishInput10868: Equatable {
    /// The exact scope every result reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every reported result, shown or not.
    let catalogue: [TimedFinishResult10868]
    let selected: TimedFinishSelected10868?
    /// The visible rows, in the owner's order. Never sorted, filtered, capped or deduplicated here.
    let group: [TimedFinishResultRef10868]
    /// Nil or invalid draws no bars.
    let axis: TimedFinishAxis10868?
    let copy: TimedFinishCopy10868
    /// A row that does not resolve ("Result unavailable in this update").
    let unavailableWords: String
}

nonisolated enum TimedFinishResolution10868: Equatable {
    case result(TimedFinishResult10868)
    case unavailable

    var result: TimedFinishResult10868? {
        if case .result(let result) = self { return result }
        return nil
    }
}

/// What a row's bar shows.
nonisolated enum TimedFinishBar10868: Equatable {
    /// The gap's exact fraction of the axis, 0...1.
    case placed(Double)
    /// The owner has no gap: the copy's words.
    case noGap
    /// Not finite, negative or past the axis: the copy's words, no bar.
    case offAxis
    /// No valid axis: no bar; the card says so once.
    case noAxis
}

nonisolated struct TimedFinishRow10868: Equatable {
    let ref: TimedFinishResultRef10868
    let resolution: TimedFinishResolution10868
    /// `.noAxis` for a row that does not resolve; it draws nothing.
    let bar: TimedFinishBar10868
}

nonisolated struct TimedFinishPlacedTick10868: Equatable {
    let fraction: Double
    let label: String
}

/// What one bar draws inside its own rect.
nonisolated struct TimedFinishBarPlan10868: Equatable {
    let zeroX: CGFloat
    let upperX: CGFloat
    /// Zero and every owner tick, as faint gridlines.
    let tickXs: [CGFloat]
    /// From zero to the gap; zero-width at a real zero.
    let bar: CGRect
    /// The gap's endpoint, centred on it — kept at a real zero.
    let endpoint: CGRect
}

nonisolated enum TimedFinishHeroArrangement10868: Equatable {
    /// Side by side while both readings keep their width, else stacked.
    case fitting
    case stacked
}

nonisolated enum TimedFinishGeometry10868 {
    /// The one drawing plan every bar Canvas uses, on the shared inset scale
    /// (`FieldFinishGeometry10868.x`). Nil for a size or fraction that cannot
    /// be drawn — never clamped.
    static func barPlan(fraction: Double, ticks: [Double], in size: CGSize, inset: CGFloat, barHeight: CGFloat, endpointDiameter: CGFloat) -> TimedFinishBarPlan10868? {
        guard size.height.isFinite, barHeight.isFinite, barHeight > 0,
              endpointDiameter.isFinite, endpointDiameter > 0,
              size.height >= max(barHeight, endpointDiameter),
              let zero = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let upper = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset),
              let end = FieldFinishGeometry10868.x(of: fraction, width: size.width, inset: inset)
        else { return nil }
        let midY = size.height / 2
        return TimedFinishBarPlan10868(
            zeroX: zero,
            upperX: upper,
            tickXs: ([0] + ticks).compactMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) },
            bar: CGRect(x: zero, y: midY - barHeight / 2, width: end - zero, height: barHeight),
            endpoint: CGRect(x: end - endpointDiameter / 2, y: midY - endpointDiameter / 2, width: endpointDiameter, height: endpointDiameter)
        )
    }

    /// At accessibility sizes, or with the gold chance shown as words, the
    /// selected reading stacks the chance under the time.
    static func heroArrangement(accessibilitySize: Bool, chanceIsWords: Bool) -> TimedFinishHeroArrangement10868 {
        accessibilitySize || chanceIsWords ? .stacked : .fitting
    }

    /// At accessibility sizes a row's gap words sit under its name, not beside it.
    static func stacksRowHeading(accessibilitySize: Bool) -> Bool {
        accessibilitySize
    }
}

/// The card's rules, resolved once per input.
nonisolated struct TimedFinishModel10868: Equatable {
    let input: TimedFinishInput10868
    /// Catalogue position of every complete, in-scope identity carried exactly once.
    private let unique: [TimedFinishResultRef10868: Int]

    init(_ input: TimedFinishInput10868) {
        self.input = input
        var counts: [TimedFinishResultRef10868: Int] = [:]
        var first: [TimedFinishResultRef10868: Int] = [:]
        for (index, record) in input.catalogue.enumerated() {
            counts[record.ref, default: 0] += 1
            if first[record.ref] == nil { first[record.ref] = index }
        }
        unique = first.filter { counts[$0.key] == 1 && $0.key.isComplete && $0.key.scope == input.scope }
    }

    // MARK: Identity

    /// Exactly one catalogue record in the same scope, or unavailable.
    func resolve(_ ref: TimedFinishResultRef10868) -> TimedFinishResolution10868 {
        guard ref.scope == input.scope, let index = unique[ref] else { return .unavailable }
        return .result(input.catalogue[index])
    }

    /// The selected record, by the same resolver as every row.
    var selectedResult: TimedFinishResult10868? {
        input.selected.flatMap { resolve($0.ref).result }
    }

    /// The owner's words when a selection exists but does not resolve.
    var selectionNotice: String? {
        guard let selected = input.selected, selectedResult == nil else { return nil }
        return selected.unavailableWords
    }

    func isSelected(_ result: TimedFinishResult10868) -> Bool {
        selectedResult?.ref == result.ref
    }

    // MARK: Axis and bars

    var visibleAxis: TimedFinishAxis10868? {
        guard let axis = input.axis, axis.isValid else { return nil }
        return axis
    }

    /// The owner's ticks that sit on the axis, in the owner's order.
    var ticks: [TimedFinishPlacedTick10868] {
        guard let axis = visibleAxis else { return [] }
        return axis.ticks.compactMap { tick in
            guard tick.seconds.isFinite, tick.seconds >= 0, tick.seconds <= axis.upper,
                  !tick.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            else { return nil }
            return TimedFinishPlacedTick10868(fraction: tick.seconds / axis.upper, label: tick.label)
        }
    }

    func bar(_ result: TimedFinishResult10868) -> TimedFinishBar10868 {
        guard let axis = visibleAxis else { return .noAxis }
        guard let gap = result.gap else { return .noGap }
        guard gap.seconds.isFinite, gap.seconds >= 0, gap.seconds <= axis.upper else { return .offAxis }
        return .placed(gap.seconds / axis.upper)
    }

    var rows: [TimedFinishRow10868] {
        input.group.map { ref in
            let resolution = resolve(ref)
            return TimedFinishRow10868(ref: ref, resolution: resolution, bar: resolution.result.map { bar($0) } ?? .noAxis)
        }
    }

    /// The gap words beside a row: the owner's gap text, or the copy's words.
    func gapWords(_ result: TimedFinishResult10868) -> String {
        switch bar(result) {
        case .noGap: input.copy.noGap
        case .offAxis: input.copy.offAxis
        case .placed, .noAxis: result.gap?.text ?? input.copy.noGap
        }
    }

    // MARK: Actions

    /// The exact catalogue identity a row hands back — only with a callback.
    func chooseAction(_ row: TimedFinishRow10868, canChoose: Bool) -> TimedFinishResultRef10868? {
        canChoose ? row.resolution.result?.ref : nil
    }

    /// The selected result's complete linked original, unchanged.
    var selectedOriginal: FieldChooserOriginalRef10868? {
        guard let original = selectedResult?.original, original.isComplete else { return nil }
        return original
    }

    func openAction(canOpen: Bool) -> FieldChooserOriginalRef10868? {
        canOpen ? selectedOriginal : nil
    }

    /// The copy's words for a resolved selection with no usable original.
    var noOriginalWords: String? {
        guard selectedResult != nil, selectedOriginal == nil else { return nil }
        return input.copy.noOriginal
    }

    // MARK: VoiceOver

    /// Actual seconds, reported standing and the separately dated gold chance.
    func spoken(_ result: TimedFinishResult10868) -> String {
        let copy = input.copy
        return [
            result.name,
            "\(copy.timeLabel): \(result.time) \(copy.timeSpokenUnit)",
            "\(copy.standingLabel): \(result.standing)",
            FieldChooserModel10868.spoken(result.goldChance)
        ].joined(separator: ". ")
    }

    var heroSummary: String? {
        selectedResult.map(spoken) ?? selectionNotice
    }

    /// A row's whole reading, so its bar may stay decorative.
    func rowSummary(_ row: TimedFinishRow10868) -> String {
        guard let result = row.resolution.result else { return input.unavailableWords }
        var parts: [String] = []
        if isSelected(result), let words = input.selected?.words { parts.append(words) }
        parts.append(spoken(result))
        parts.append(gapWords(result))
        return parts.joined(separator: ". ")
    }
}

nonisolated enum TimedFinishAccessibilityID10868 {
    static let hero = "timedFinish10868.hero"
    static let rows = "timedFinish10868.rows"
    static let openOriginal = "timedFinish10868.openOriginal"
    static func row(_ resultID: String) -> String { "timedFinish10868.row.\(resultID)" }
}

struct TimedFinishComparisonPresentation10868: View {
    let input: TimedFinishInput10868
    var onChooseResult: ((TimedFinishResultRef10868) -> Void)?
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)?
    private let model: TimedFinishModel10868

    init(
        input: TimedFinishInput10868,
        onChooseResult: ((TimedFinishResultRef10868) -> Void)? = nil,
        onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    ) {
        self.input = input
        self.onChooseResult = onChooseResult
        self.onOpenOriginal = onOpenOriginal
        self.model = TimedFinishModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .largeTitle) private var heroSize: CGFloat = 30
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 16
    @ScaledMetric(relativeTo: .caption) private var barHeight: CGFloat = 12
    @ScaledMetric(relativeTo: .caption) private var endpointDiameter: CGFloat = 10

    /// Half an endpoint and a hair, so an endpoint at zero or at the upper end stays whole.
    private var inset: CGFloat { FieldExpectationsGeometry10868.inset(markDiameter: endpointDiameter) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                if let eyebrow = input.copy.eyebrow {
                    ownerWords(eyebrow)
                }
                Text(input.copy.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            hero
            let rows = model.rows
            if rows.isEmpty {
                ownerWords(input.copy.empty)
            } else {
                ownerWords(input.copy.gapLabel)
                if model.visibleAxis == nil {
                    ownerWords(input.copy.axisUnavailable)
                } else if !model.ticks.isEmpty {
                    axis(model.ticks)
                }
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        finisher(row)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel([input.copy.graphicLabel, input.copy.distinction].compactMap { $0 }.joined(separator: ". "))
                .accessibilityIdentifier(TimedFinishAccessibilityID10868.rows)
            }
            if let note = input.copy.note {
                ownerWords(note)
            }
            originalAction
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Selected reading

    @ViewBuilder private var hero: some View {
        if let result = model.selectedResult {
            let chanceIsWords: Bool = {
                if case .missing = result.goldChance.value { return true }
                return false
            }()
            Group {
                switch TimedFinishGeometry10868.heroArrangement(accessibilitySize: typeSize.isAccessibilitySize, chanceIsWords: chanceIsWords) {
                case .stacked:
                    VStack(alignment: .leading, spacing: 12) {
                        actualReading(result)
                        chanceReading(result.goldChance)
                    }
                case .fitting:
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 16) {
                            actualReading(result)
                            chanceReading(result.goldChance)
                        }
                        VStack(alignment: .leading, spacing: 12) {
                            actualReading(result)
                            chanceReading(result.goldChance)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.heroSummary ?? "")
            .accessibilityIdentifier(TimedFinishAccessibilityID10868.hero)
        } else if let notice = model.selectionNotice {
            Text(notice)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(TimedFinishAccessibilityID10868.hero)
        }
    }

    /// Name, the exact time with its unit and the standing words.
    private func actualReading(_ result: TimedFinishResult10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ownerWords(result.name)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(result.time)
                    .font(.system(size: heroSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(input.copy.timeUnit)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
            }
            Text(result.standing)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.blue)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The gold reading's label, then its figure and clock, or its own words.
    private func chanceReading(_ reading: FieldChooserReading10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ownerWords(reading.label)
            switch reading.value {
            case .recorded(let text, let detail):
                Text(text)
                    .font(.system(size: heroSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                ownerWords(detail)
            case .missing(let words):
                Text(words)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Axis

    /// The owner's tick labels, measured onto the bars' own inset by the
    /// shared `FieldExpectationsAxisLayout10868`: a label with no room beside
    /// one already placed, or wider than the row, is left out — a mark never
    /// moves. Decorative — each row speaks.
    private func axis(_ ticks: [TimedFinishPlacedTick10868]) -> some View {
        FieldExpectationsAxisLayout10868(units: ticks.map(\.fraction), inset: inset, spacing: 6) {
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.label)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .topLeading)
                    .clipped()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityHidden(true)
    }

    // MARK: Rows

    @ViewBuilder private func finisher(_ row: TimedFinishRow10868) -> some View {
        let id = TimedFinishAccessibilityID10868.row(row.ref.resultID)
        if let result = row.resolution.result {
            let choosing = model.chooseAction(row, canChoose: onChooseResult != nil)
            let selected = model.isSelected(result)
            control(choosing) {
                VStack(alignment: .leading, spacing: 6) {
                    heading(result, selected: selected)
                    if case .placed(let fraction) = row.bar {
                        bar(fraction: fraction, selected: selected)
                    }
                }
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
                .contentShape(Rectangle())
            }
            .accessibilityLabel(result.name)
            .accessibilityValue(model.rowSummary(row))
            .accessibilityHint(choosing == nil ? "" : (input.copy.chooseHint ?? ""))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            ownerWords(input.unavailableWords)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
                .accessibilityIdentifier(id)
        }
    }

    /// The whole name with the standing and exact time, and the gap words —
    /// beside it, or under it at accessibility sizes.
    private func heading(_ result: TimedFinishResult10868, selected: Bool) -> some View {
        let layout = TimedFinishGeometry10868.stacksRowHeading(accessibilitySize: typeSize.isAccessibilitySize)
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
        return layout {
            VStack(alignment: .leading, spacing: 2) {
                Text(result.name)
                    .font(.body.weight(selected ? .bold : .semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(verbatim: "\(result.standing) · \(result.time)\(input.copy.timeUnit)")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if selected, let words = input.selected?.words {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark").font(.caption2.weight(.bold))
                        Text(words).font(.caption.weight(.semibold))
                    }
                    .foregroundStyle(DS.blue)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(model.gapWords(result))
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Gridlines at zero and each owner tick, the bar from zero and its endpoint.
    private func bar(fraction: Double, selected: Bool) -> some View {
        let gridColor = DS.border
        let fill = DS.blue.opacity(selected ? 1 : 0.45)
        let ticks = model.ticks.map(\.fraction)
        let inset = self.inset
        let height = barHeight
        let diameter = endpointDiameter
        return Canvas { context, size in
            guard let plan = TimedFinishGeometry10868.barPlan(fraction: fraction, ticks: ticks, in: size, inset: inset, barHeight: height, endpointDiameter: diameter) else { return }
            for x in plan.tickXs {
                var line = Path()
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(gridColor), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
            }
            context.fill(Path(roundedRect: plan.bar, cornerRadius: min(plan.bar.width, height) / 2), with: .color(fill))
            context.fill(Path(ellipseIn: plan.endpoint), with: .color(fill))
        }
        .frame(maxWidth: .infinity, minHeight: trackHeight, maxHeight: trackHeight)
        .accessibilityHidden(true)
    }

    // MARK: Original

    /// The selected skater's gold history — a real action only with a linked
    /// original and a callback; with no link, the copy's words, never a
    /// disabled control.
    @ViewBuilder private var originalAction: some View {
        if let original = model.openAction(canOpen: onOpenOriginal != nil), let onOpenOriginal {
            Button {
                onOpenOriginal(original)
            } label: {
                Text(input.copy.openOriginal)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.blue)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(input.copy.openOriginalHint ?? "")
            .accessibilityIdentifier(TimedFinishAccessibilityID10868.openOriginal)
        } else if let words = model.noOriginalWords {
            ownerWords(words)
        }
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func control<Content: View>(_ ref: TimedFinishResultRef10868?, @ViewBuilder content: () -> Content) -> some View {
        if let ref, let onChooseResult {
            Button {
                onChooseResult(ref)
            } label: {
                content()
            }
            .buttonStyle(.plain)
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}
