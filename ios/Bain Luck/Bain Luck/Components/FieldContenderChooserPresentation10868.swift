import SwiftUI

// #10868 — "Choose a golfer": the golf chart's golfer-chooser content. A fan
// sees the golfers already in the chart as visual cards (the owner's dated
// before-event estimate, or that estimate beside a separately labelled
// recorded reading, and a miniature history), can open more golfers with
// recorded history, and can browse the complete field by the owner's groups
// and choose ANY original in it — including one with no history at all.
//
// Presentation only, extracted from the approved design: `GolfChooser.tsx` +
// `golfChooser.css` (featured "In your chart" cards, More-with-history and
// Browse-all disclosures, band buttons, compact field rows), as mounted by
// `GolfReadingReplay.tsx` / `GolfJourney.tsx`. The reference's cohort and
// three-golfer election, last-record and baseline election, ceiling ladder,
// surname parser and compound-name table, band and rank ordering, movement
// arithmetic, time compression and gap policy (`golfChoiceEvidence.ts`,
// `golfChoicePreview.ts`) are NOT ported. All of that arrives as owner input.
//
// The owner supplies ONE canonical catalogue: each record is an exact original
// (opaque scope + source + market + outcome), its full name and its already
// admitted display plan, preview, status, movement, clock and result words.
// Featured, More and every browse group only REFER to catalogue identities; an
// original may appear in several sections and is still one record. This layer
// never sorts, filters, deduplicates or caps the catalogue or a section, never
// elects a first, default, nearest or recommended original, never builds an
// identity from a name or an index, and never formats a probability, reads a
// clock, computes movement or turns a result into a chance. A reference that
// does not resolve to exactly one record in the same scope — missing,
// withdrawn, out of scope, duplicated or blank — is shown as the owner's
// unavailable words with no action; its neighbours keep theirs.
//
// Every miniature history is drawn on the owner's ONE frame: one time domain
// and one zero-based ceiling for every preview in the chooser, before
// references included. Nothing here computes a per-row extent, compresses
// time, samples, smooths or normalizes. Points outside the frame or not
// finite break the line (no clipped interpolation toward them); the owner's
// emphasized observation is drawn exactly, never inferred from the latest
// point. The before reference is a dashed horizontal line with a common key —
// not observed history. With no drawable observation the owner's absence words
// replace the preview; a reference never stands in as a flat history.
//
// Selection, pinning, the cohort, held snapshots, expansion, the chosen group,
// the sheet, Done/Back and focus restoration stay with the host. The view
// keeps no state, no sheet, no subscription and runs no animation. Choosing a
// row hands back that exact catalogue identity; nothing is repinned here. With
// no callback the content is static — no button pretends to act.
//
// SCROLLING: the HOST owns the scroll. This leaf is plain content (no
// ScrollView) for the host's existing sheet / navigation container to scroll,
// so it never nests a competing scroll inside the tournament page's own.
//
// Host binding still owed — not available at this base. An owner must supply
// the complete original catalogue for the selected event/market by exact
// identity (a golfer name or a ranked index is not an identity), the featured,
// More and ordered group references with their labels and counts, each
// original's qualified before and separately timed recorded readings or their
// own absence words, per-original qualified history runs with explicit gaps,
// emphasis and before reference on one shared frame, independently admitted
// result words, and the selected/pinned identity. FIELD-CHOOSER-NATIVE-BINDING-
// MAP.md names the gaps.

/// An exact original, handed back unchanged on choose.
nonisolated struct FieldChooserOriginalRef10868: Hashable {
    /// The owner's opaque exact scope (event, market and held window).
    let scope: String
    let source: String
    let marketID: String
    let outcomeID: String

    /// Every part present. A blank part is never an identity.
    var isComplete: Bool {
        [scope, source, marketID, outcomeID].allSatisfy { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }
}

/// One reading's value. Real 0% is a recorded value; missing is words.
nonisolated enum FieldChooserValue10868: Equatable {
    /// The owner's whole figure ("2.6%", "0%") and that reading's own clock,
    /// source and granularity line ("Oct 6, 6:08 AM PT · DataGolf").
    case recorded(text: String, detail: String)
    /// The owner's words for an absent reading ("Not recorded before the event").
    case missing(String)
}

/// One labelled reading ("Before tournament", "Last recorded in Round 4").
nonisolated struct FieldChooserReading10868: Equatable {
    let label: String
    let value: FieldChooserValue10868
}

/// The owner's display plan for a card.
nonisolated enum FieldChooserDisplayPlan10868: Equatable {
    /// One dated before-event estimate — no second before slot.
    case single(FieldChooserReading10868)
    /// The before-event estimate and a separately labelled recorded or current
    /// reading, each with its own clock, at the same figure size.
    case comparison(before: FieldChooserReading10868, later: FieldChooserReading10868)

    var readings: [FieldChooserReading10868] {
        switch self {
        case .single(let reading): [reading]
        case .comparison(let before, let later): [before, later]
        }
    }
}

/// Result words from the existing settlement owner. Never a chance.
nonisolated struct FieldChooserResult10868: Equatable {
    /// "Final result".
    let title: String
    /// "Won", "T4".
    let words: String
}

/// One owner-qualified observation, in the frame's time units.
nonisolated struct FieldChooserPoint10868: Equatable {
    let time: Double
    /// 0...1.
    let probability: Double
}

/// A missing interval the owner marks on the time axis.
nonisolated struct FieldChooserGap10868: Equatable {
    let start: Double
    let end: Double
}

/// One original's qualified history on the shared frame.
nonisolated struct FieldChooserHistory10868: Equatable {
    /// Qualified runs in the owner's order. Runs never join each other.
    let segments: [[FieldChooserPoint10868]]
    /// The exact observation to emphasize; nil emphasizes none.
    let emphasis: FieldChooserPoint10868?
    /// The before-event estimate as a dashed reference; nil draws none.
    let beforeReference: Double?
    let gaps: [FieldChooserGap10868]
}

nonisolated struct FieldChooserPreview10868: Equatable {
    let history: FieldChooserHistory10868?
    /// Shown instead of a preview when nothing is drawable ("No captured history").
    let absence: String
}

/// One canonical catalogue record.
nonisolated struct FieldChooserOriginal10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The full name; never truncated or shortened.
    let name: String
    let plan: FieldChooserDisplayPlan10868
    let preview: FieldChooserPreview10868
    /// The owner's movement words ("Down 2.3 pts vs before tournament").
    let movement: String?
    /// The owner's clock line for the emphasized reading.
    let clock: String?
    let result: FieldChooserResult10868?
    /// The compact browse-row status ("Recorded history available").
    let browseStatus: String
    /// The chart's own colour for this original; nil uses the default.
    var accent: Color? = nil
}

/// The owner's one frame for every preview in the chooser.
nonisolated struct FieldChooserFrame10868: Equatable {
    let start: Double
    let end: Double
    /// Zero-based ceiling, 0 < ceiling <= 1.
    let ceiling: Double
    /// "Week history · same time & scale".
    let key: String
    /// "Dashed line: before tournament"; nil or blank shows no reference key
    /// and draws no dashed reference.
    let referenceKey: String?
    /// The common scale in words, shown under each preview ("0–20% chance").
    let scale: String
    /// "DataGolf-derived recorded history".
    let provenance: String

    var isValid: Bool {
        start.isFinite && end.isFinite && start < end && ceiling.isFinite && ceiling > 0 && ceiling <= 1
    }

    /// The owner's reference key, verbatim, when it carries a readable
    /// character. Nil, empty or blank: no dashed reference is drawn or keyed.
    var explainedReferenceKey: String? {
        guard let referenceKey, !referenceKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return referenceKey
    }
}

/// The host's selected original.
nonisolated struct FieldChooserSelected10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's words for its state ("Kept in view" when pinned, else "In focus").
    let words: String
    /// Shown when the selected identity does not resolve.
    let unavailableWords: String
}

nonisolated struct FieldChooserFeatured10868: Equatable {
    /// "In your chart".
    let title: String
    /// "3 maximum"; nil draws none.
    let badge: String?
    let refs: [FieldChooserOriginalRef10868]
    let emptyWords: String
}

nonisolated struct FieldChooserMore10868: Equatable {
    let id: String
    /// "More with recorded history · 10".
    let title: String
    let expanded: Bool
    let refs: [FieldChooserOriginalRef10868]
    let emptyWords: String
}

/// One owner group of the complete field, members in the owner's order.
nonisolated struct FieldChooserGroup10868: Equatable {
    let id: String
    /// "A–C".
    let label: String
    /// "18"; nil draws none.
    let countText: String?
    let refs: [FieldChooserOriginalRef10868]
}

nonisolated struct FieldChooserBrowse10868: Equatable {
    let id: String
    /// "Browse all 155 golfers" — the owner's count of the actual field.
    let title: String
    let expanded: Bool
    /// "By last name · a golfer stays selectable when history is missing."
    let note: String?
    /// Spoken name of the group buttons ("Last-name groups").
    let groupsLabel: String
    let groups: [FieldChooserGroup10868]
    let selectedGroupID: String?
    /// Shown when no group is chosen. No group is chosen here.
    let noGroupWords: String
    /// Shown when the chosen group does not resolve to exactly one.
    let groupUnavailableWords: String
    /// Shown for a resolved group with no members.
    let emptyGroupWords: String
}

nonisolated struct FieldChooserInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// "Pick one to keep. We suggest the other two."; nil draws none.
    let intro: String?
    let featured: FieldChooserFeatured10868
    /// "Week · 13 of 155 golfers have history in this view…"; nil draws none.
    let context: String?
    let more: FieldChooserMore10868?
    let browse: FieldChooserBrowse10868?
    /// The canonical catalogue, in the owner's order.
    let catalogue: [FieldChooserOriginal10868]
    /// Nil draws no previews; each card shows its absence words.
    let frame: FieldChooserFrame10868?
    let selected: FieldChooserSelected10868?
    /// A row whose reference does not resolve ("Golfer unavailable in this update").
    let unavailableWords: String
    /// Spoken hint on a choosable row ("Keeps this golfer in the chart"); nil none.
    let chooseHint: String?
}

nonisolated enum FieldChooserControl10868: Equatable {
    case toggleMore(id: String)
    case toggleBrowse(id: String)
    case chooseGroup(id: String)
}

nonisolated enum FieldChooserAction10868: Equatable {
    case choose(FieldChooserOriginalRef10868)
    case control(FieldChooserControl10868)

    func perform(
        onChoose: ((FieldChooserOriginalRef10868) -> Void)?,
        onControl: ((FieldChooserControl10868) -> Void)?
    ) {
        switch self {
        case .choose(let ref): onChoose?(ref)
        case .control(let control): onControl?(control)
        }
    }
}

nonisolated enum FieldChooserResolution10868: Equatable {
    case original(FieldChooserOriginal10868)
    case unavailable

    var original: FieldChooserOriginal10868? {
        if case .original(let original) = self { return original }
        return nil
    }
}

/// One section entry, resolved against the catalogue.
nonisolated struct FieldChooserRow10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let resolution: FieldChooserResolution10868
}

nonisolated enum FieldChooserGroupSelection10868: Equatable {
    case group(FieldChooserGroup10868)
    /// No group chosen: the owner's words.
    case notChosen(String)
    /// The chosen id resolves to zero or several groups: the owner's words.
    case unavailable(String)
}

/// A point inside the preview, 0...1 on both axes (y grows downward).
nonisolated struct FieldChooserUnitPoint10868: Equatable {
    let x: Double
    let y: Double
}

/// What one preview draws.
nonisolated struct FieldChooserPlot10868: Equatable {
    let runs: [[FieldChooserUnitPoint10868]]
    let emphasis: FieldChooserUnitPoint10868?
    /// Unit y of the dashed before reference.
    let reference: Double?
    /// Unit x of each gap marker.
    let gaps: [Double]

    var hasObservations: Bool { !runs.isEmpty || emphasis != nil }
}

nonisolated enum FieldChooserArrangement10868: Equatable {
    case sideBySide
    case stacked
}

nonisolated enum FieldChooserGeometry10868 {
    /// A point's place in the frame, or none when it is not finite or lies
    /// outside the domain or 0...ceiling — never clamped.
    static func unit(_ point: FieldChooserPoint10868, in frame: FieldChooserFrame10868) -> FieldChooserUnitPoint10868? {
        guard frame.isValid, point.time.isFinite, point.probability.isFinite,
              point.time >= frame.start, point.time <= frame.end,
              point.probability >= 0, point.probability <= frame.ceiling
        else { return nil }
        return FieldChooserUnitPoint10868(
            x: (point.time - frame.start) / (frame.end - frame.start),
            y: 1 - point.probability / frame.ceiling
        )
    }

    /// The owner's runs, each broken wherever a point cannot be placed. Order
    /// is the owner's; nothing is sorted, joined or interpolated.
    static func runs(_ segments: [[FieldChooserPoint10868]], in frame: FieldChooserFrame10868) -> [[FieldChooserUnitPoint10868]] {
        var runs: [[FieldChooserUnitPoint10868]] = []
        for segment in segments {
            var run: [FieldChooserUnitPoint10868] = []
            for point in segment {
                if let placed = unit(point, in: frame) {
                    run.append(placed)
                } else if !run.isEmpty {
                    runs.append(run)
                    run = []
                }
            }
            if !run.isEmpty { runs.append(run) }
        }
        return runs
    }

    static func referenceY(_ probability: Double, in frame: FieldChooserFrame10868) -> Double? {
        guard frame.isValid, probability.isFinite, probability >= 0, probability <= frame.ceiling else { return nil }
        return 1 - probability / frame.ceiling
    }

    static func gapX(_ gap: FieldChooserGap10868, in frame: FieldChooserFrame10868) -> Double? {
        guard frame.isValid, gap.start.isFinite, gap.end.isFinite, gap.start < gap.end,
              gap.start >= frame.start, gap.end <= frame.end
        else { return nil }
        return ((gap.start + gap.end) / 2 - frame.start) / (frame.end - frame.start)
    }

    /// The preview's marks. The dashed reference is carried only beside a
    /// readable reference key; the history itself never depends on the key.
    static func plot(_ history: FieldChooserHistory10868, in frame: FieldChooserFrame10868) -> FieldChooserPlot10868? {
        guard frame.isValid else { return nil }
        return FieldChooserPlot10868(
            runs: runs(history.segments, in: frame),
            emphasis: history.emphasis.flatMap { unit($0, in: frame) },
            reference: frame.explainedReferenceKey == nil ? nil : history.beforeReference.flatMap { referenceY($0, in: frame) },
            gaps: history.gaps.compactMap { gapX($0, in: frame) }
        )
    }

    /// A unit point in a drawing rect inset so a mark at an edge stays whole.
    static func position(_ point: FieldChooserUnitPoint10868, in size: CGSize, inset: CGFloat) -> CGPoint {
        let width = max(0, size.width - 2 * inset)
        let height = max(0, size.height - 2 * inset)
        return CGPoint(x: inset + width * CGFloat(point.x), y: inset + height * CGFloat(point.y))
    }

    /// The readings beside the preview while both keep their width: the
    /// readings at their whole measured width and the preview at its scaled
    /// minimum. Otherwise stacked. Nothing shrinks to fit.
    static func cardArrangement(
        available: CGFloat?,
        readingsWidth: CGFloat,
        previewMinimum: CGFloat,
        spacing: CGFloat,
        forceStack: Bool
    ) -> FieldChooserArrangement10868 {
        if forceStack { return .stacked }
        guard readingsWidth.isFinite, readingsWidth >= 0, previewMinimum.isFinite else { return .stacked }
        guard let available, available.isFinite else { return .sideBySide }
        return readingsWidth + spacing + previewMinimum <= available ? .sideBySide : .stacked
    }
}

/// The chooser's rules, resolved once per input.
nonisolated struct FieldChooserModel10868: Equatable {
    let input: FieldChooserInput10868
    /// Catalogue position of every identity carried exactly once.
    private let unique: [FieldChooserOriginalRef10868: Int]
    /// Control ids carried exactly once and not blank.
    private let validControlIDs: Set<String>
    let selectedRef: FieldChooserOriginalRef10868?

    init(_ input: FieldChooserInput10868) {
        self.input = input
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        var first: [FieldChooserOriginalRef10868: Int] = [:]
        for (index, record) in input.catalogue.enumerated() {
            counts[record.ref, default: 0] += 1
            if first[record.ref] == nil { first[record.ref] = index }
        }
        let resolvable = first.filter { counts[$0.key] == 1 && $0.key.isComplete && $0.key.scope == input.scope }
        unique = resolvable

        var ids = [input.more?.id, input.browse?.id].compactMap { $0 }
        ids += input.browse?.groups.map(\.id) ?? []
        var idCounts: [String: Int] = [:]
        for id in ids { idCounts[id, default: 0] += 1 }
        validControlIDs = Set(idCounts.filter {
            $0.value == 1 && !$0.key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }.keys)

        // The same resolver as every row: exactly one complete record in scope.
        selectedRef = input.selected.flatMap { selected in resolvable[selected.ref].map { input.catalogue[$0].ref } }
    }

    // MARK: Identity

    /// Exactly one catalogue record in the same scope, or unavailable.
    func resolve(_ ref: FieldChooserOriginalRef10868) -> FieldChooserResolution10868 {
        guard ref.scope == input.scope, let index = unique[ref] else { return .unavailable }
        return .original(input.catalogue[index])
    }

    func rows(_ refs: [FieldChooserOriginalRef10868]) -> [FieldChooserRow10868] {
        refs.map { FieldChooserRow10868(ref: $0, resolution: resolve($0)) }
    }

    var featuredRows: [FieldChooserRow10868] { rows(input.featured.refs) }

    /// Only while the host has More expanded.
    var moreRows: [FieldChooserRow10868] {
        guard let more = input.more, more.expanded else { return [] }
        return rows(more.refs)
    }

    // MARK: Selection

    func isSelected(_ original: FieldChooserOriginal10868) -> Bool {
        selectedRef == original.ref
    }

    func selectedWords(_ original: FieldChooserOriginal10868) -> String? {
        isSelected(original) ? input.selected?.words : nil
    }

    var selectionNotice: String? {
        guard let selected = input.selected, selectedRef == nil else { return nil }
        return selected.unavailableWords
    }

    // MARK: Browse groups

    var groupSelection: FieldChooserGroupSelection10868? {
        guard let browse = input.browse, browse.expanded else { return nil }
        guard let id = browse.selectedGroupID else { return .notChosen(browse.noGroupWords) }
        let matches = browse.groups.filter { $0.id == id }
        guard matches.count == 1, !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return .unavailable(browse.groupUnavailableWords)
        }
        return .group(matches[0])
    }

    func isSelectedGroup(_ group: FieldChooserGroup10868) -> Bool {
        if case .group(let selected) = groupSelection { return selected == group }
        return false
    }

    /// The chosen group's rows; empty when no group resolves.
    var groupRows: [FieldChooserRow10868] {
        guard case .group(let group)? = groupSelection else { return [] }
        return rows(group.refs)
    }

    // MARK: Actions

    func chooseAction(_ row: FieldChooserRow10868, canChoose: Bool) -> FieldChooserAction10868? {
        guard canChoose, let original = row.resolution.original else { return nil }
        return .choose(original.ref)
    }

    func moreAction(canControl: Bool) -> FieldChooserAction10868? {
        guard canControl, let id = input.more?.id, validControlIDs.contains(id) else { return nil }
        return .control(.toggleMore(id: id))
    }

    func browseAction(canControl: Bool) -> FieldChooserAction10868? {
        guard canControl, let id = input.browse?.id, validControlIDs.contains(id) else { return nil }
        return .control(.toggleBrowse(id: id))
    }

    func groupAction(_ group: FieldChooserGroup10868, canControl: Bool) -> FieldChooserAction10868? {
        guard canControl, validControlIDs.contains(group.id) else { return nil }
        return .control(.chooseGroup(id: group.id))
    }

    // MARK: Preview

    /// What a card's preview draws, or nil to show its absence words.
    func plot(_ original: FieldChooserOriginal10868) -> FieldChooserPlot10868? {
        guard let frame = input.frame, let history = original.preview.history,
              let plot = FieldChooserGeometry10868.plot(history, in: frame), plot.hasObservations
        else { return nil }
        return plot
    }

    /// The common key and scale words: shown only with a valid frame.
    var visibleFrame: FieldChooserFrame10868? {
        guard let frame = input.frame, frame.isValid else { return nil }
        return frame
    }

    // MARK: VoiceOver

    static func spoken(_ reading: FieldChooserReading10868) -> String {
        switch reading.value {
        case .recorded(let text, let detail): "\(reading.label): \(text), \(detail)"
        case .missing(let words): "\(reading.label): \(words)"
        }
    }

    /// A card's whole reading in the owner's words, so its preview may stay
    /// decorative: selection, every reading with its clock, movement, result
    /// and — when nothing is drawn — the absence words.
    func cardSummary(_ original: FieldChooserOriginal10868) -> String {
        var parts: [String] = []
        if let words = selectedWords(original) { parts.append(words) }
        parts += original.plan.readings.map(Self.spoken)
        if let movement = original.movement { parts.append(movement) }
        if let clock = original.clock { parts.append(clock) }
        if let result = original.result { parts.append("\(result.title): \(result.words)") }
        if plot(original) == nil { parts.append(original.preview.absence) }
        return parts.joined(separator: ". ")
    }

    func browseSummary(_ original: FieldChooserOriginal10868) -> String {
        selectedWords(original) ?? original.browseStatus
    }
}

/// Readings and preview side by side while both keep their width, else stacked
/// at full width.
struct FieldChooserCardPairLayout10868: Layout {
    var spacing: CGFloat
    var previewMinimum: CGFloat
    var forceStack: Bool

    private func arrangement(_ width: CGFloat?, _ subviews: Subviews) -> FieldChooserArrangement10868 {
        guard subviews.count == 2 else { return .stacked }
        return FieldChooserGeometry10868.cardArrangement(
            available: width,
            readingsWidth: subviews[0].sizeThatFits(.unspecified).width,
            previewMinimum: previewMinimum,
            spacing: spacing,
            forceStack: forceStack
        )
    }

    private func leadingWidth(_ total: CGFloat, _ subviews: Subviews) -> CGFloat {
        min(subviews[0].sizeThatFits(.unspecified).width, max(0, total - spacing - previewMinimum))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        switch arrangement(proposal.width, subviews) {
        case .stacked:
            var height: CGFloat = 0
            var widest: CGFloat = 0
            for (index, subview) in subviews.enumerated() {
                let size = subview.sizeThatFits(ProposedViewSize(width: proposal.width, height: nil))
                height += size.height + (index > 0 ? spacing : 0)
                widest = max(widest, size.width)
            }
            return CGSize(width: proposal.width ?? widest, height: height)
        case .sideBySide:
            let total = proposal.width
                ?? subviews[0].sizeThatFits(.unspecified).width + spacing + previewMinimum
            let first = leadingWidth(total, subviews)
            let second = max(0, total - spacing - first)
            let height = max(
                subviews[0].sizeThatFits(ProposedViewSize(width: first, height: nil)).height,
                subviews[1].sizeThatFits(ProposedViewSize(width: second, height: nil)).height
            )
            return CGSize(width: total, height: height)
        }
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        switch arrangement(bounds.width, subviews) {
        case .stacked:
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
            let first = leadingWidth(bounds.width, subviews)
            let second = max(0, bounds.width - spacing - first)
            subviews[0].place(
                at: CGPoint(x: bounds.minX, y: bounds.minY),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: first, height: nil)
            )
            subviews[1].place(
                at: CGPoint(x: bounds.minX + first + spacing, y: bounds.midY),
                anchor: .leading,
                proposal: ProposedViewSize(width: second, height: nil)
            )
        }
    }
}

/// The miniature history: zero line, dashed before reference, gap markers,
/// the owner's runs and the emphasized observation. Decorative — the card's
/// control speaks every reading.
private struct FieldChooserPreviewDrawing10868: View {
    let plot: FieldChooserPlot10868
    let accent: Color
    let height: CGFloat

    var body: some View {
        let zeroColor = DS.border
        let referenceColor = DS.textSecondary
        let ringColor = DS.cardBg
        let tint = accent
        let shape = plot
        Canvas { context, size in
            let inset: CGFloat = 4
            func at(_ x: Double, _ y: Double) -> CGPoint {
                FieldChooserGeometry10868.position(FieldChooserUnitPoint10868(x: x, y: y), in: size, inset: inset)
            }
            var zero = Path()
            zero.move(to: at(0, 1))
            zero.addLine(to: at(1, 1))
            context.stroke(zero, with: .color(zeroColor), lineWidth: 1)
            if let reference = shape.reference {
                var line = Path()
                line.move(to: at(0, reference))
                line.addLine(to: at(1, reference))
                context.stroke(line, with: .color(referenceColor), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
            }
            for gap in shape.gaps {
                let base = at(gap, 1)
                var mark = Path()
                mark.move(to: CGPoint(x: base.x - 3, y: base.y + 3))
                mark.addLine(to: CGPoint(x: base.x, y: base.y - 3))
                mark.addLine(to: CGPoint(x: base.x + 3, y: base.y + 3))
                context.stroke(mark, with: .color(referenceColor), lineWidth: 1)
            }
            for run in shape.runs {
                if run.count == 1, let only = run.first {
                    let center = at(only.x, only.y)
                    context.fill(Path(ellipseIn: CGRect(x: center.x - 2, y: center.y - 2, width: 4, height: 4)), with: .color(tint))
                } else {
                    var path = Path()
                    for (index, point) in run.enumerated() {
                        if index == 0 { path.move(to: at(point.x, point.y)) } else { path.addLine(to: at(point.x, point.y)) }
                    }
                    context.stroke(path, with: .color(tint), style: StrokeStyle(lineWidth: 2, lineJoin: .round))
                }
            }
            if let emphasis = shape.emphasis {
                let center = at(emphasis.x, emphasis.y)
                context.fill(Path(ellipseIn: CGRect(x: center.x - 4, y: center.y - 4, width: 8, height: 8)), with: .color(ringColor))
                context.fill(Path(ellipseIn: CGRect(x: center.x - 3, y: center.y - 3, width: 6, height: 6)), with: .color(tint))
            }
        }
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }
}

/// The dashed swatch beside the reference key: a shape, never colour alone.
private struct FieldChooserDashSwatch10868: View {
    var body: some View {
        let color = DS.textSecondary
        Canvas { context, size in
            var line = Path()
            line.move(to: CGPoint(x: 0, y: size.height / 2))
            line.addLine(to: CGPoint(x: size.width, y: size.height / 2))
            context.stroke(line, with: .color(color), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
        }
        .frame(width: 18, height: 6)
        .accessibilityHidden(true)
    }
}

/// Stable ids so the host can return focus to the exact originating control.
nonisolated enum FieldChooserAccessibilityID10868 {
    static let key = "fieldChooser10868.key"
    static let moreToggle = "fieldChooser10868.moreToggle"
    static let browseToggle = "fieldChooser10868.browseToggle"
    static func featured(_ outcomeID: String) -> String { "fieldChooser10868.featured.\(outcomeID)" }
    static func more(_ outcomeID: String) -> String { "fieldChooser10868.more.\(outcomeID)" }
    static func browse(_ outcomeID: String) -> String { "fieldChooser10868.browse.\(outcomeID)" }
    static func group(_ groupID: String) -> String { "fieldChooser10868.group.\(groupID)" }
}

struct FieldContenderChooserPresentation10868: View {
    let input: FieldChooserInput10868
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)?
    var onControl: ((FieldChooserControl10868) -> Void)?
    private let model: FieldChooserModel10868

    init(
        input: FieldChooserInput10868,
        onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil,
        onControl: ((FieldChooserControl10868) -> Void)? = nil
    ) {
        self.input = input
        self.onChoose = onChoose
        self.onControl = onControl
        self.model = FieldChooserModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 19
    @ScaledMetric(relativeTo: .caption) private var previewHeight: CGFloat = 50
    @ScaledMetric(relativeTo: .caption) private var previewMinimum: CGFloat = 96

    private var canChoose: Bool { onChoose != nil }
    private var canControl: Bool { onControl != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let intro = input.intro {
                Text(intro)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let notice = model.selectionNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            featuredSection
            if let context = input.context {
                Text(context)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let more = input.more { moreSection(more) }
            if let browse = input.browse { browseSection(browse) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Featured

    private var featuredSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(input.featured.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: 8)
                if let badge = input.featured.badge {
                    Text(badge).font(.caption).foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            frameKey
            let rows = model.featuredRows
            if rows.isEmpty {
                ownerWords(input.featured.emptyWords)
            } else {
                cards(rows, id: FieldChooserAccessibilityID10868.featured)
            }
        }
    }

    /// The common key: what the previews show, the shared time and scale, the
    /// dashed reference and provenance — readable text, not colour.
    @ViewBuilder private var frameKey: some View {
        if let frame = model.visibleFrame {
            VStack(alignment: .leading, spacing: 4) {
                Text(frame.key)
                if let referenceKey = frame.explainedReferenceKey {
                    HStack(spacing: 6) {
                        FieldChooserDashSwatch10868()
                        Text(referenceKey)
                    }
                }
                Text(frame.provenance)
            }
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(FieldChooserAccessibilityID10868.key)
        }
    }

    // MARK: Cards

    private func cards(_ rows: [FieldChooserRow10868], id: @escaping (String) -> String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                card(row, id: id(row.ref.outcomeID))
            }
        }
    }

    @ViewBuilder private func card(_ row: FieldChooserRow10868, id: String) -> some View {
        if let original = row.resolution.original {
            let action = model.chooseAction(row, canChoose: canChoose)
            control(action) {
                cardContent(original)
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.cardSummary(original))
            .accessibilityHint(action == nil ? "" : (input.chooseHint ?? ""))
            .accessibilityAddTraits(model.isSelected(original) ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            unavailableRow
                .padding(12)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(DS.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
                .accessibilityIdentifier(id)
        }
    }

    private func cardContent(_ original: FieldChooserOriginal10868) -> some View {
        let selected = model.isSelected(original)
        return VStack(alignment: .leading, spacing: 8) {
            nameLine(original)
            FieldChooserCardPairLayout10868(
                spacing: 12,
                previewMinimum: previewMinimum,
                forceStack: typeSize.isAccessibilitySize
            ) {
                readings(original.plan)
                previewColumn(original)
            }
            readingDetails(original.plan)
            if original.movement != nil || original.clock != nil {
                VStack(alignment: .leading, spacing: 2) {
                    if let movement = original.movement {
                        Text(movement).font(.caption).foregroundStyle(DS.textPrimary)
                    }
                    if let clock = original.clock {
                        Text(clock).font(.caption2).foregroundStyle(DS.textSecondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            if let result = original.result {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(result.title).font(.caption).foregroundStyle(DS.textSecondary)
                    Text(result.words).font(.caption.weight(.semibold)).foregroundStyle(DS.textPrimary)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .background(selected ? DS.blue.opacity(0.04) : DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(selected ? DS.blue : DS.border, lineWidth: selected ? 2 : 1))
        .contentShape(Rectangle())
    }

    /// The whole name, then the owner's selected words with a checkmark —
    /// never colour alone.
    private func nameLine(_ original: FieldChooserOriginal10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(original.name)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let words = model.selectedWords(original) {
                selectedTag(words)
            }
        }
    }

    private func selectedTag(_ words: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: "checkmark").font(.caption2.weight(.bold))
            Text(words).font(.caption.weight(.semibold))
        }
        .foregroundStyle(DS.blue)
        .fixedSize(horizontal: false, vertical: true)
    }

    /// Every reading at the same figure size; labels beside figures, stacked at
    /// accessibility sizes.
    private func readings(_ plan: FieldChooserDisplayPlan10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        return VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(plan.readings.enumerated()), id: \.offset) { _, reading in
                layout {
                    Text(reading.label)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    switch reading.value {
                    case .recorded(let text, _):
                        Text(text)
                            .font(.system(size: figureSize, weight: .semibold))
                            .monospacedDigit()
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize()
                    case .missing(let words):
                        Text(words)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    @ViewBuilder private func previewColumn(_ original: FieldChooserOriginal10868) -> some View {
        if let plot = model.plot(original), let frame = model.visibleFrame {
            VStack(spacing: 2) {
                FieldChooserPreviewDrawing10868(plot: plot, accent: original.accent ?? DS.blue, height: previewHeight)
                Text(frame.scale)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity)
        } else {
            Text(original.preview.absence)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Each recorded reading's own clock, source and granularity line.
    private func readingDetails(_ plan: FieldChooserDisplayPlan10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(plan.readings.enumerated()), id: \.offset) { _, reading in
                switch reading.value {
                case .recorded(_, let detail):
                    Text("\(reading.label) · \(detail)")
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                case .missing:
                    EmptyView()
                }
            }
        }
    }

    // MARK: More

    private func moreSection(_ more: FieldChooserMore10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            disclosure(
                title: more.title,
                expanded: more.expanded,
                action: model.moreAction(canControl: canControl),
                id: FieldChooserAccessibilityID10868.moreToggle
            )
            if more.expanded {
                let rows = model.moreRows
                if rows.isEmpty {
                    ownerWords(more.emptyWords)
                } else {
                    cards(rows, id: FieldChooserAccessibilityID10868.more)
                }
            }
        }
    }

    // MARK: Browse

    private func browseSection(_ browse: FieldChooserBrowse10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            disclosure(
                title: browse.title,
                expanded: browse.expanded,
                action: model.browseAction(canControl: canControl),
                id: FieldChooserAccessibilityID10868.browseToggle
            )
            if browse.expanded {
                if let note = browse.note { ownerWords(note) }
                FlowLayout(spacing: 8) {
                    ForEach(Array(browse.groups.enumerated()), id: \.offset) { _, group in
                        groupButton(group)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(browse.groupsLabel)
                groupList(browse)
            }
        }
    }

    private func groupButton(_ group: FieldChooserGroup10868) -> some View {
        let selected = model.isSelectedGroup(group)
        return control(model.groupAction(group, canControl: canControl)) {
            HStack(spacing: 6) {
                if selected {
                    Image(systemName: "checkmark").font(.caption2.weight(.bold))
                }
                Text(group.label).font(.subheadline.weight(selected ? .semibold : .regular))
                if let count = group.countText {
                    Text(count).font(.caption).foregroundStyle(DS.textSecondary)
                }
            }
            .foregroundStyle(selected ? DS.blue : DS.textPrimary)
            .padding(.horizontal, 12)
            .frame(minWidth: 44, minHeight: 44)
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(selected ? DS.blue : DS.border, lineWidth: selected ? 2 : 1))
            .contentShape(Rectangle())
        }
        .accessibilityLabel([group.label, group.countText].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(FieldChooserAccessibilityID10868.group(group.id))
    }

    @ViewBuilder private func groupList(_ browse: FieldChooserBrowse10868) -> some View {
        switch model.groupSelection {
        case .group(let group)?:
            let rows = model.groupRows
            if rows.isEmpty {
                ownerWords(browse.emptyGroupWords)
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        browseRow(row)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(group.label)
            }
        case .notChosen(let words)?, .unavailable(let words)?:
            ownerWords(words)
        case nil:
            EmptyView()
        }
    }

    /// A compact name/status choice — no figure, no preview.
    @ViewBuilder private func browseRow(_ row: FieldChooserRow10868) -> some View {
        let id = FieldChooserAccessibilityID10868.browse(row.ref.outcomeID)
        if let original = row.resolution.original {
            let action = model.chooseAction(row, canChoose: canChoose)
            let selected = model.isSelected(original)
            control(action) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(original.name)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(selected ? DS.blue : DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let words = model.selectedWords(original) {
                        selectedTag(words)
                    } else {
                        Text(original.browseStatus)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.browseSummary(original))
            .accessibilityHint(action == nil ? "" : (input.chooseHint ?? ""))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            unavailableRow
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
                .accessibilityIdentifier(id)
        }
    }

    // MARK: Shared pieces

    /// A disclosure header. Static with no valid action: the title alone, no
    /// chevron asking for a tap.
    private func disclosure(title: String, expanded: Bool, action: FieldChooserAction10868?, id: String) -> some View {
        control(action) {
            HStack(spacing: 12) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if action != nil {
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .accessibilityHidden(true)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            .contentShape(Rectangle())
        }
        .accessibilityLabel(title)
        .accessibilityValue(action == nil ? "" : (expanded ? "Expanded" : "Collapsed"))
        .accessibilityIdentifier(id)
    }

    private var unavailableRow: some View {
        Text(input.unavailableWords)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func control<Content: View>(_ action: FieldChooserAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onChoose: onChoose, onControl: onControl)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - #10868 field outlook bars — "Before the day began"
//
// The weather-range card's before-day outlook, built on the chooser above. A fan
// compares the owner's displayed originals as compact bars on one zero-based
// probability scale, sees the selected original's own dated before reading,
// steps to the previous or next original in the owner's order, and opens that
// exact original's details. The same card is shown before, during and after
// the day; only at the final may the selected original's own admitted result
// appear, separately from its before reading.
//
// Presentation only, from the approved `WeatherRanges.tsx` `rangeCard` and
// `weatherRanges.css` (`.wr-range-chart`, `.wr-range-pick`, `.wr-comparison`,
// larger/wide variants). The reference's top-five election, field order,
// event admission, day cutoff, baseline election, probability label, colour
// identity and settlement reading are NOT ported. All of that is owner input.
//
// Identity, selection and choose go through the chooser's own
// `FieldChooserModel10868` — the same resolver, selected cue and choose action
// every chooser row uses. An original resolves only as exactly one complete
// catalogue record in the same scope; a displayed slot repeated in the
// displayed list, or one that does not resolve, keeps its owner label beside
// the unavailable words and borrows no bar, figure or action.
//
// A bar's height is the owner's RAW before chance for that exact original,
// tied to the very before reading the owner formatted from the same
// observation: the association's reading must equal the original's own before
// reading (label, figure and clock line) or the bar shows no value. Nothing
// here parses a figure, reads a preview, a later or current reading, movement,
// a clock or a result, and nothing is normalized, complemented or summed. A
// real 0% draws a zero mark; a value above the owner's ceiling draws no fill
// and the owner's off-scale words; a missing, duplicated, foreign, mismatched
// or invalid value draws nothing and the owner's unavailable words. A missing
// value never makes an original unchoosable.
//
// Every phase draws the same before-event bars and the selected original's
// before reading only (a comparison plan contributes its before reading, never
// its later one). The phase is the owner's explicit input, never inferred from
// a clock or a winner. The selected original's result words appear only at
// `.final`; with none, the owner's unknown words — unknown is never a loss.
//
// Vertical bars keep every label, figure and word whole. When they cannot fit
// the width — or at accessibility sizes — the same bars are laid out as
// labelled horizontal bars on the same scale. Nothing shrinks or truncates.
// The host owns the scroll, the catalogue, the details sheet and focus; this
// leaf keeps no state. With no callback, nothing pretends to act.
//
// Host binding still owed: WEATHER-RANGE-OUTLOOK-NATIVE-BINDING-MAP.md.

/// The owner's actual phase for the card.
nonisolated enum FieldOutlookPhase10868: Equatable {
    case before
    case during
    case final
}

/// One raw before chance, tied to the before reading formatted from the same
/// observation.
nonisolated struct FieldOutlookBeforeChance10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// 0...1, the raw value behind `reading` — never parsed from its text.
    let probability: Double
    /// The exact before reading the owner formatted from this observation.
    let reading: FieldChooserReading10868
}

/// One displayed bar, in the owner's order.
nonisolated struct FieldOutlookSlot10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's full axis label ("74-75°F"); also kept for an unavailable slot.
    let label: String
    /// The owner's compact axis label under a vertical bar ("74-75°"). Whole.
    let shortLabel: String
}

nonisolated struct FieldOutlookTick10868: Equatable {
    let probability: Double
    /// The owner's tick label ("25%").
    let label: String
}

/// The owner's one zero-based scale for every bar.
nonisolated struct FieldOutlookScale10868: Equatable {
    /// 0 < ceiling <= 1.
    let ceiling: Double
    let ticks: [FieldOutlookTick10868]
    /// The scale in words under the bars ("0–50% chance · ranges are not normalized").
    let words: String

    var isValid: Bool { ceiling.isFinite && ceiling > 0 && ceiling <= 1 }
}

/// The owner's words for this card in the actual phase.
nonisolated struct FieldOutlookCopy10868: Equatable {
    /// "Before the day began".
    let title: String
    /// "Five ranges · before Oct 16"; nil draws none.
    let note: String?
    /// Spoken name of the bar group.
    let graphicLabel: String
    /// A bar whose value cannot be placed ("Not shown on this scale").
    let missingChance: String
    /// A bar above the ceiling ("Above the 50% scale").
    let offScale: String
    /// The selected original is not among the bars.
    let outsideDisplayed: String
    let previousLabel: String
    let nextLabel: String
    /// "Original outcomes & rules".
    let details: String
    let detailsHint: String?
    /// At the final, when the selected original has no admitted result
    /// ("Result unconfirmed"). Required: unknown never vanishes, never a loss.
    let resultUnknown: String
}

nonisolated struct FieldOutlookInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    let selected: FieldChooserSelected10868?
    /// The bars, in the owner's order. Never sorted, capped or deduplicated here.
    let displayed: [FieldOutlookSlot10868]
    /// The owner's previous/next order.
    let traversal: [FieldChooserOriginalRef10868]
    let chances: [FieldOutlookBeforeChance10868]
    let scale: FieldOutlookScale10868
    let phase: FieldOutlookPhase10868
    let copy: FieldOutlookCopy10868
    /// A slot or neighbour that does not resolve ("Range unavailable in this update").
    let unavailableWords: String
    let chooseHint: String?
}

/// Where a bar's value sits on the shared scale.
nonisolated enum FieldOutlookChance10868: Equatable {
    /// The raw value and its fraction of the ceiling; 0 is a real zero mark.
    case value(probability: Double, fraction: Double)
    /// Finite and within 0...1 but above the ceiling: no fill.
    case offScale
    /// Missing, duplicated, foreign, mismatched or invalid: nothing drawn.
    case unavailable

    var fraction: Double? {
        if case .value(_, let fraction) = self { return fraction }
        return nil
    }
}

nonisolated struct FieldOutlookBar10868: Equatable {
    let slot: FieldOutlookSlot10868
    let resolution: FieldChooserResolution10868
    let chance: FieldOutlookChance10868
}

nonisolated struct FieldOutlookPlacedTick10868: Equatable {
    let label: String
    let fraction: Double
}

nonisolated enum FieldOutlookOrientation10868: Equatable {
    case vertical
    case horizontal
}

nonisolated enum FieldOutlookStep10868: Equatable {
    case previous
    case next

    var offset: Int { self == .previous ? -1 : 1 }
}

nonisolated enum FieldOutlookResultLine10868: Equatable {
    case result(FieldChooserResult10868)
    case unknown(String)
}

/// What one bar draws inside its own rect: from the leading edge when
/// horizontal, from the bottom when vertical.
nonisolated struct FieldOutlookMarkPlan10868: Equatable {
    /// The exact fraction of the rect — never widened to a minimum.
    let fill: CGRect?
    /// A real 0%: a thin mark on the zero edge.
    let zeroMark: CGRect?
    /// The selected outline, 1 pt inside the fill, only while that inset is a
    /// real rectangle. A tiny selected fill keeps its checkmark cue instead.
    let outline: CGRect?

    static let empty = FieldOutlookMarkPlan10868(fill: nil, zeroMark: nil, outline: nil)
}

nonisolated enum FieldOutlookGeometry10868 {
    /// A probability's fraction of the ceiling, or none when it is not finite
    /// or outside 0...ceiling — never clamped. Both orientations use it.
    static func fraction(_ probability: Double, ceiling: Double) -> Double? {
        guard ceiling.isFinite, ceiling > 0, ceiling <= 1,
              probability.isFinite, probability >= 0, probability <= ceiling
        else { return nil }
        return probability / ceiling
    }

    /// The one drawing plan both bar Canvases use. Nothing for a missing,
    /// invalid or off-scale fraction or a size that cannot be drawn.
    static func markPlan(
        fraction: Double?,
        in size: CGSize,
        orientation: FieldOutlookOrientation10868,
        selected: Bool
    ) -> FieldOutlookMarkPlan10868 {
        guard let fraction, fraction.isFinite, fraction >= 0, fraction <= 1,
              size.width.isFinite, size.height.isFinite, size.width > 0, size.height > 0
        else { return .empty }
        if fraction == 0 {
            let mark = orientation == .horizontal
                ? CGRect(x: 0, y: 0, width: min(3, size.width), height: size.height)
                : CGRect(x: 0, y: size.height - min(3, size.height), width: size.width, height: min(3, size.height))
            return FieldOutlookMarkPlan10868(fill: nil, zeroMark: mark, outline: nil)
        }
        let fill = orientation == .horizontal
            ? CGRect(x: 0, y: 0, width: size.width * CGFloat(fraction), height: size.height)
            : CGRect(x: 0, y: size.height - size.height * CGFloat(fraction), width: size.width, height: size.height * CGFloat(fraction))
        let inset = fill.insetBy(dx: 1, dy: 1)
        let drawable = !inset.isNull && inset.width > 0 && inset.height > 0
        return FieldOutlookMarkPlan10868(fill: fill, zeroMark: nil, outline: selected && drawable ? inset : nil)
    }

    /// The layouts to try, in order. Accessibility sizes go straight to the
    /// labelled horizontal bars; otherwise vertical bars while they fit whole.
    static func orientations(accessibilitySize: Bool) -> [FieldOutlookOrientation10868] {
        accessibilitySize ? [.horizontal] : [.vertical, .horizontal]
    }
}

/// The outlook's rules, resolved once per input, on the chooser's own model.
nonisolated struct FieldOutlookModel10868: Equatable {
    let input: FieldOutlookInput10868
    /// The chooser's resolver, selected cue and choose action.
    let field: FieldChooserModel10868
    /// Displayed identities listed more than once.
    private let repeatedDisplayed: Set<FieldChooserOriginalRef10868>

    init(_ input: FieldOutlookInput10868) {
        self.input = input
        // Only what the chooser's resolver reads; no chooser section is drawn.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope,
            intro: nil,
            featured: FieldChooserFeatured10868(
                title: input.copy.title, badge: nil,
                refs: input.displayed.map(\.ref), emptyWords: input.unavailableWords
            ),
            context: nil,
            more: nil,
            browse: nil,
            catalogue: input.catalogue,
            frame: nil,
            selected: input.selected,
            unavailableWords: input.unavailableWords,
            chooseHint: input.chooseHint
        ))
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for slot in input.displayed { counts[slot.ref, default: 0] += 1 }
        repeatedDisplayed = Set(counts.filter { $0.value > 1 }.keys)
    }

    /// A plan's before reading: the single reading, or a comparison's before.
    static func beforeReading(_ plan: FieldChooserDisplayPlan10868) -> FieldChooserReading10868 {
        switch plan {
        case .single(let reading): reading
        case .comparison(let before, _): before
        }
    }

    // MARK: Bars

    var bars: [FieldOutlookBar10868] {
        input.displayed.map { slot in
            let resolution: FieldChooserResolution10868 = repeatedDisplayed.contains(slot.ref) ? .unavailable : field.resolve(slot.ref)
            return FieldOutlookBar10868(
                slot: slot,
                resolution: resolution,
                chance: resolution.original.map(chance) ?? .unavailable
            )
        }
    }

    /// The original's own raw before chance on the shared scale.
    func chance(_ original: FieldChooserOriginal10868) -> FieldOutlookChance10868 {
        let matches = input.chances.filter { $0.ref == original.ref }
        guard matches.count == 1, let match = matches.first,
              case .recorded = match.reading.value,
              match.reading == Self.beforeReading(original.plan),
              input.scale.isValid,
              match.probability.isFinite, match.probability >= 0, match.probability <= 1
        else { return .unavailable }
        guard let fraction = FieldOutlookGeometry10868.fraction(match.probability, ceiling: input.scale.ceiling) else {
            return .offScale
        }
        return .value(probability: match.probability, fraction: fraction)
    }

    /// The owner's ticks that sit on the scale, in the owner's order.
    var ticks: [FieldOutlookPlacedTick10868] {
        guard input.scale.isValid else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldOutlookGeometry10868.fraction(tick.probability, ceiling: input.scale.ceiling)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    /// The figure printed with a bar: the original's own before figure, or its
    /// own absence words.
    func figure(_ bar: FieldOutlookBar10868) -> String? {
        guard let original = bar.resolution.original else { return nil }
        switch Self.beforeReading(original.plan).value {
        case .recorded(let text, _): return text
        case .missing(let words): return words
        }
    }

    /// The words beside a bar that draws no fill.
    func stateWords(_ bar: FieldOutlookBar10868) -> String? {
        guard let original = bar.resolution.original else { return input.unavailableWords }
        switch bar.chance {
        case .value:
            return nil
        case .offScale:
            return input.copy.offScale
        case .unavailable:
            if case .missing = Self.beforeReading(original.plan).value { return nil }
            return input.copy.missingChance
        }
    }

    func isSelected(_ bar: FieldOutlookBar10868) -> Bool {
        bar.resolution.original.map(field.isSelected) ?? false
    }

    func barAction(_ bar: FieldOutlookBar10868, canChoose: Bool) -> FieldChooserAction10868? {
        field.chooseAction(FieldChooserRow10868(ref: bar.slot.ref, resolution: bar.resolution), canChoose: canChoose)
    }

    /// The owner's choose hint, only on a control that acts.
    func hint(_ action: FieldChooserAction10868?) -> String {
        action == nil ? "" : (input.chooseHint ?? "")
    }

    /// A bar's whole reading in the owner's words, so its marks may stay decorative.
    func barSummary(_ bar: FieldOutlookBar10868) -> String {
        guard let original = bar.resolution.original else {
            return [bar.slot.label, input.unavailableWords]
                .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
                .joined(separator: ". ")
        }
        var parts: [String] = []
        if let words = field.selectedWords(original) { parts.append(words) }
        parts.append(FieldChooserModel10868.spoken(Self.beforeReading(original.plan)))
        if let words = stateWords(bar) { parts.append(words) }
        return parts.joined(separator: ". ")
    }

    // MARK: Selected original

    var selectedOriginal: FieldChooserOriginal10868? {
        field.selectedRef.flatMap { field.resolve($0).original }
    }

    var selectedReading: FieldChooserReading10868? {
        selectedOriginal.map { Self.beforeReading($0.plan) }
    }

    /// The reading's own clock and provenance line, verbatim. The label is
    /// already printed beside the figure, so it is not repeated here.
    static func detailLine(_ reading: FieldChooserReading10868) -> String? {
        if case .recorded(_, let detail) = reading.value { return detail }
        return nil
    }

    var isSelectedOutsideDisplayed: Bool {
        guard let ref = field.selectedRef else { return false }
        return !bars.contains { $0.resolution.original?.ref == ref }
    }

    /// An unresolved selection's words, else the outside-the-bars notice.
    var notice: String? {
        if let words = field.selectionNotice { return words }
        return isSelectedOutsideDisplayed ? input.copy.outsideDisplayed : nil
    }

    /// The selected original's admitted result — at the final only.
    var resultLine: FieldOutlookResultLine10868? {
        guard input.phase == .final, let original = selectedOriginal else { return nil }
        if let result = original.result { return .result(result) }
        return .unknown(input.copy.resultUnknown)
    }

    // MARK: Previous / next

    /// The original beside the selected one in the owner's order. The selected
    /// and its neighbour must each be listed exactly once and the neighbour
    /// must resolve; otherwise none — never the next one along.
    func neighbour(_ step: FieldOutlookStep10868) -> FieldChooserOriginal10868? {
        guard let selected = field.selectedRef else { return nil }
        let order = input.traversal
        let positions = order.indices.filter { order[$0] == selected }
        guard positions.count == 1 else { return nil }
        let index = positions[0] + step.offset
        guard order.indices.contains(index) else { return nil }
        let ref = order[index]
        guard order.filter({ $0 == ref }).count == 1 else { return nil }
        return field.resolve(ref).original
    }

    func stepAction(_ step: FieldOutlookStep10868, canChoose: Bool) -> FieldChooserAction10868? {
        guard let original = neighbour(step) else { return nil }
        return field.chooseAction(FieldChooserRow10868(ref: original.ref, resolution: .original(original)), canChoose: canChoose)
    }

    // MARK: Details

    /// The exact selected original to open, only with a callback.
    func detailsRef(canOpen: Bool) -> FieldChooserOriginalRef10868? {
        canOpen ? selectedOriginal?.ref : nil
    }

    var detailsSpokenLabel: String? {
        selectedOriginal.map { "\(input.copy.details), \($0.name)" }
    }
}

nonisolated enum FieldOutlookAccessibilityID10868 {
    static let bars = "fieldOutlook10868.bars"
    static let previous = "fieldOutlook10868.previous"
    static let next = "fieldOutlook10868.next"
    static let details = "fieldOutlook10868.details"
    static func bar(_ outcomeID: String) -> String { "fieldOutlook10868.bar.\(outcomeID)" }
}

struct FieldOutlookBarsPresentation10868: View {
    let input: FieldOutlookInput10868
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)?
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)?
    private let model: FieldOutlookModel10868

    init(
        input: FieldOutlookInput10868,
        onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil,
        onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    ) {
        self.input = input
        self.onChoose = onChoose
        self.onOpenOriginal = onOpenOriginal
        self.model = FieldOutlookModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var plotHeight: CGFloat = 120
    @ScaledMetric(relativeTo: .caption) private var figureRoom: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var barWidth: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 14

    private var canChoose: Bool { onChoose != nil }
    private var canOpen: Bool { onOpenOriginal != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(input.copy.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let note = input.copy.note {
                ownerWords(note)
            }
            let bars = model.bars
            if !bars.isEmpty {
                graphic(bars)
                if input.scale.isValid {
                    Text(input.scale.words)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            selectedPanel
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Bars

    @ViewBuilder private func graphic(_ bars: [FieldOutlookBar10868]) -> some View {
        Group {
            if FieldOutlookGeometry10868.orientations(accessibilitySize: typeSize.isAccessibilitySize) == [.horizontal] {
                horizontalBars(bars)
            } else {
                ViewThatFits(in: .horizontal) {
                    verticalBars(bars)
                    horizontalBars(bars)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.graphicLabel)
        .accessibilityIdentifier(FieldOutlookAccessibilityID10868.bars)
    }

    private var accentDefault: Color { DS.blue }

    private func verticalBars(_ bars: [FieldOutlookBar10868]) -> some View {
        let ticks = model.ticks
        let cell = figureRoom + plotHeight
        return HStack(alignment: .top, spacing: 0) {
            if !ticks.isEmpty {
                verticalAxis(ticks, cell: cell)
                    .padding(.trailing, 6)
            }
            ForEach(Array(bars.enumerated()), id: \.offset) { _, bar in
                verticalColumn(bar, cell: cell)
                    .background(alignment: .top) {
                        verticalGrid(ticks).frame(height: cell)
                    }
            }
        }
    }

    /// The owner's tick labels, each centred on its gridline. Decorative — the
    /// scale words below say the same.
    private func verticalAxis(_ ticks: [FieldOutlookPlacedTick10868], cell: CGFloat) -> some View {
        let room = figureRoom
        let plot = plotHeight
        return ZStack {
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.label).font(.caption2).fixedSize().hidden()
            }
        }
        .frame(height: cell, alignment: .top)
        .overlay(alignment: .topTrailing) {
            ZStack(alignment: .topTrailing) {
                ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                    Text(tick.label)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize()
                        .alignmentGuide(.top) { d in d[VerticalAlignment.center] - (room + CGFloat(1 - tick.fraction) * plot) }
                }
            }
        }
        .accessibilityHidden(true)
    }

    /// Gridlines at the owner's ticks and the zero line, on the plot rows only.
    private func verticalGrid(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
        let room = figureRoom
        let plot = plotHeight
        let color = DS.border
        let fractions: [Double] = [0] + ticks.map(\.fraction)
        return Canvas { context, size in
            for fraction in fractions {
                let y = room + CGFloat(1 - fraction) * plot
                var line = Path()
                line.move(to: CGPoint(x: 0, y: y))
                line.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(line, with: .color(color), lineWidth: 1)
            }
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder private func verticalColumn(_ bar: FieldOutlookBar10868, cell: CGFloat) -> some View {
        let id = FieldOutlookAccessibilityID10868.bar(bar.slot.ref.outcomeID)
        if let original = bar.resolution.original {
            let action = model.barAction(bar, canChoose: canChoose)
            let selected = model.isSelected(bar)
            control(action) {
                VStack(spacing: 6) {
                    verticalPlot(bar, accent: original.accent ?? accentDefault, selected: selected)
                        .frame(height: cell)
                    Text(bar.slot.shortLabel)
                        .font(.caption.weight(selected ? .semibold : .regular))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                    if selected {
                        Image(systemName: "checkmark")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DS.blue)
                    }
                }
                .padding(.horizontal, 6)
                .frame(minWidth: 44, minHeight: 44, alignment: .top)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.barSummary(bar))
            .accessibilityHint(model.hint(action))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            VStack(spacing: 6) {
                ownerWords(input.unavailableWords)
                    .fixedSize()
                    .frame(height: cell, alignment: .bottom)
                Text(bar.slot.shortLabel)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize()
            }
            .padding(.horizontal, 6)
            .frame(minWidth: 44, minHeight: 44, alignment: .top)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.barSummary(bar))
            .accessibilityIdentifier(id)
        }
    }

    /// The figure sits on its bar; an off-scale value sits above the plot with
    /// an up mark and words, never a clamped fill; nothing placeable, words only.
    @ViewBuilder private func verticalPlot(_ bar: FieldOutlookBar10868, accent: Color, selected: Bool) -> some View {
        switch bar.chance {
        case .value(_, let fraction):
            ZStack(alignment: .bottom) {
                verticalMark(fraction: fraction, accent: accent, selected: selected)
                figureText(bar)
                    .padding(.bottom, plotHeight * CGFloat(fraction) + 4)
            }
            .frame(maxHeight: .infinity, alignment: .bottom)
        case .offScale:
            VStack(spacing: 4) {
                Image(systemName: "arrow.up.to.line")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(DS.textSecondary)
                    .accessibilityHidden(true)
                figureText(bar)
                stateText(bar)
                Spacer(minLength: 0)
            }
        case .unavailable:
            VStack(spacing: 4) {
                Spacer(minLength: 0)
                figureText(bar)
                stateText(bar)
            }
        }
    }

    /// The bar on the plot rows, drawn from the shared mark plan.
    private func verticalMark(fraction: Double, accent: Color, selected: Bool) -> some View {
        let outlineColor = DS.textPrimary
        return Canvas { context, size in
            let plan = FieldOutlookGeometry10868.markPlan(fraction: fraction, in: size, orientation: .vertical, selected: selected)
            if let mark = plan.zeroMark { context.fill(Path(mark), with: .color(accent)) }
            if let fill = plan.fill { context.fill(Path(fill), with: .color(accent.opacity(selected ? 1 : 0.45))) }
            if let outline = plan.outline { context.stroke(Path(outline), with: .color(outlineColor), lineWidth: 2) }
        }
        .frame(width: barWidth, height: plotHeight)
        .accessibilityHidden(true)
    }

    private func horizontalBars(_ bars: [FieldOutlookBar10868]) -> some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(bars.enumerated()), id: \.offset) { _, bar in
                horizontalRow(bar, ticks: ticks)
            }
            if !ticks.isEmpty {
                horizontalAxis(ticks)
            }
        }
    }

    @ViewBuilder private func horizontalRow(_ bar: FieldOutlookBar10868, ticks: [FieldOutlookPlacedTick10868]) -> some View {
        let id = FieldOutlookAccessibilityID10868.bar(bar.slot.ref.outcomeID)
        let line = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        if let original = bar.resolution.original {
            let action = model.barAction(bar, canChoose: canChoose)
            let selected = model.isSelected(bar)
            control(action) {
                VStack(alignment: .leading, spacing: 4) {
                    line {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text(bar.slot.label)
                                .font(.subheadline.weight(selected ? .semibold : .regular))
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            if selected {
                                Image(systemName: "checkmark")
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(DS.blue)
                            }
                        }
                        if !typeSize.isAccessibilitySize { Spacer(minLength: 8) }
                        figureText(bar, wraps: true)
                    }
                    if model.stateWords(bar) != nil { stateText(bar, wraps: true) }
                    horizontalTrack(bar.chance, ticks: ticks, accent: original.accent ?? accentDefault, selected: selected)
                        .frame(height: trackHeight)
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.barSummary(bar))
            .accessibilityHint(model.hint(action))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if !bar.slot.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(bar.slot.label)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.unavailableWords)
            }
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(DS.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.barSummary(bar))
            .accessibilityIdentifier(id)
        }
    }

    /// One horizontal bar on the same scale: zero line, tick lines, then the
    /// shared mark plan. Off-scale and unavailable draw no fill.
    private func horizontalTrack(_ chance: FieldOutlookChance10868, ticks: [FieldOutlookPlacedTick10868], accent: Color, selected: Bool) -> some View {
        let lineColor = DS.border
        let outlineColor = DS.textPrimary
        let fractions: [Double] = [0] + ticks.map(\.fraction)
        let fraction = chance.fraction
        return Canvas { context, size in
            for tick in fractions {
                let x = size.width * CGFloat(tick)
                var line = Path()
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(lineColor), lineWidth: 1)
            }
            let plan = FieldOutlookGeometry10868.markPlan(fraction: fraction, in: size, orientation: .horizontal, selected: selected)
            if let mark = plan.zeroMark { context.fill(Path(mark), with: .color(accent)) }
            if let fill = plan.fill { context.fill(Path(fill), with: .color(accent.opacity(selected ? 1 : 0.45))) }
            if let outline = plan.outline { context.stroke(Path(outline), with: .color(outlineColor), lineWidth: 2) }
        }
        .accessibilityHidden(true)
    }

    /// The owner's tick labels under the horizontal bars, each at its place;
    /// the end labels stay inside the width. Decorative.
    private func horizontalAxis(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
        Text(ticks[0].label)
            .font(.caption2)
            .hidden()
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay {
                GeometryReader { proxy in
                    let width = proxy.size.width
                    ZStack(alignment: .leading) {
                        ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                            Text(tick.label)
                                .font(.caption2)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize()
                                .alignmentGuide(.leading) { d in
                                    let anchor = tick.fraction == 0 ? d[.leading]
                                        : tick.fraction == 1 ? d[.trailing] : d[HorizontalAlignment.center]
                                    return anchor - width * CGFloat(tick.fraction)
                                }
                        }
                    }
                    .frame(width: width, height: proxy.size.height, alignment: .leading)
                }
            }
            .accessibilityHidden(true)
    }

    /// Whole on one line in a vertical column (so an over-wide column falls
    /// back to horizontal bars); wrapping at word boundaries in a horizontal row.
    private func figureText(_ bar: FieldOutlookBar10868, wraps: Bool = false) -> some View {
        Text(model.figure(bar) ?? "")
            .font(.caption.weight(.semibold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: !wraps, vertical: true)
    }

    private func stateText(_ bar: FieldOutlookBar10868, wraps: Bool = false) -> some View {
        Text(model.stateWords(bar) ?? "")
            .font(.caption2)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: !wraps, vertical: true)
    }

    // MARK: Selected original

    @ViewBuilder private var selectedPanel: some View {
        if model.notice != nil || model.selectedOriginal != nil {
            VStack(alignment: .leading, spacing: 8) {
                if let notice = model.notice {
                    Text(notice)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let original = model.selectedOriginal {
                    HStack(alignment: .center, spacing: 8) {
                        stepButton(.previous)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(original.name)
                                .font(.headline)
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            if let words = model.field.selectedWords(original) {
                                HStack(spacing: 4) {
                                    Image(systemName: "checkmark").font(.caption2.weight(.bold))
                                    Text(words).font(.caption.weight(.semibold))
                                }
                                .foregroundStyle(DS.blue)
                                .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        stepButton(.next)
                    }
                    if let reading = model.selectedReading {
                        selectedReading(reading)
                    }
                    resultLine
                    detailsButton
                }
            }
        }
    }

    private func selectedReading(_ reading: FieldChooserReading10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        return VStack(alignment: .leading, spacing: 2) {
            layout {
                Text(reading.label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                switch reading.value {
                case .recorded(let text, _):
                    Text(text)
                        .font(.system(size: figureSize, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                case .missing(let words):
                    Text(words)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let line = FieldOutlookModel10868.detailLine(reading) {
                Text(line)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var resultLine: some View {
        switch model.resultLine {
        case .result(let result)?:
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(result.title).font(.caption).foregroundStyle(DS.textSecondary)
                Text(result.words).font(.caption.weight(.semibold)).foregroundStyle(DS.textPrimary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
        case .unknown(let words)?:
            ownerWords(words)
        case nil:
            EmptyView()
        }
    }

    /// A genuine control while choosing is possible; disabled at the owner's
    /// ends or when the neighbour cannot resolve. No callback, no control.
    @ViewBuilder private func stepButton(_ step: FieldOutlookStep10868) -> some View {
        if canChoose {
            let action = model.stepAction(step, canChoose: canChoose)
            Button {
                action?.perform(onChoose: onChoose, onControl: nil)
            } label: {
                Image(systemName: step == .previous ? "chevron.left" : "chevron.right")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(action == nil ? DS.textSecondary : DS.textPrimary)
                    .frame(minWidth: 44, minHeight: 44)
                    .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(DS.border, lineWidth: 1))
                    .contentShape(Rectangle())
            }
            .disabled(action == nil)
            .accessibilityLabel(step == .previous ? input.copy.previousLabel : input.copy.nextLabel)
            .accessibilityValue(model.neighbour(step)?.name ?? "")
            .accessibilityIdentifier(step == .previous ? FieldOutlookAccessibilityID10868.previous : FieldOutlookAccessibilityID10868.next)
        }
    }

    @ViewBuilder private var detailsButton: some View {
        if let ref = model.detailsRef(canOpen: canOpen) {
            Button {
                onOpenOriginal?(ref)
            } label: {
                HStack(spacing: 6) {
                    Text(input.copy.details)
                        .fixedSize(horizontal: false, vertical: true)
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                        .accessibilityHidden(true)
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.blue)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(model.detailsSpokenLabel ?? input.copy.details)
            .accessibilityHint(input.copy.detailsHint ?? "")
            .accessibilityIdentifier(FieldOutlookAccessibilityID10868.details)
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
    private func control<Content: View>(_ action: FieldChooserAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onChoose: onChoose, onControl: nil)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - #10868 field movement — "By noon, the outlook shifted"
//
// The weather-range card's probability-change comparison, built on the chooser
// above. A fan sees how each of the owner's displayed originals moved between
// two of its own observations — an earlier one and a later recorded one — as
// signed bars on one symmetric percentage-point scale around a clear zero axis,
// with both of that original's endpoint figures equally readable, each beside
// its own clock, and the owner's movement words. The same comparison is shown
// during and after the day; before the day there is no card at all.
//
// Presentation only, from the approved `WeatherRanges.tsx` `movementCard` and
// `weatherRanges.css` (`.wr-movement-chart`, `.wr-change-values`, larger/wide
// variants). The reference's three-original election, sort by size of change,
// noon cutoff, baseline and last-record election, scale-ceiling rounding,
// probability label, movement formatting and colour identity are NOT ported.
// All of that is owner input.
//
// Identity goes through the chooser's own `FieldChooserModel10868` — the same
// resolver every chooser row uses. An original resolves only as exactly one
// complete catalogue record in the same scope; a displayed slot repeated in the
// displayed list, or one that does not resolve, keeps its owner label beside
// the unavailable words and borrows no figure, bar, words or action.
//
// Each endpoint figure is the original's own plan reading — a comparison's
// before and later readings, a single plan's before reading — shown only while
// the owner's ONE association for that original carries the raw observation
// whose reading equals it (label, figure and clock line). An owner's absence
// words are shown as they are. Anything else shows the owner's endpoint words,
// so a later, day-end or preview reading never stands in for the recorded one;
// the other endpoint keeps its own figure. Several associations for one
// original, even identical ones, are none.
//
// The bar needs both endpoints tied, both raw values within 0...1 and the
// owner's movement words. Its place is the raw later value minus the raw before
// value on the owner's scale — nothing here parses a figure, formats a change,
// normalizes, complements or reads a preview, movement, clock or result. An
// unchanged pair (a real 0) draws a neutral zero mark; a change beyond the
// scale draws no fill, only an edge mark pointing its way and the owner's
// off-scale words; anything else draws nothing and the owner's change words.
//
// Vertical bars keep every label whole; when they cannot fit the width — or at
// accessibility sizes — the same bars are labelled horizontal bars on the same
// scale. The host owns the scroll, the details sheet and focus; this leaf keeps
// no state. Opening hands back the exact original and the owner's opaque later
// observation key unchanged. With no callback, nothing pretends to act.
//
// Host binding still owed: WEATHER-RANGE-MOVEMENT-NATIVE-BINDING-MAP.md.

/// One raw endpoint, tied to the reading the owner formatted from the same
/// observation.
nonisolated struct FieldMovementObservation10868: Equatable {
    /// 0...1, the raw value behind `reading` — never parsed from its text.
    let probability: Double
    /// The exact reading the owner formatted from this observation.
    let reading: FieldChooserReading10868
}

/// The owner's association for the two observations one original is compared on.
nonisolated struct FieldMovementPair10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The earlier observation; nil when the owner admitted none.
    let before: FieldMovementObservation10868?
    /// The later recorded observation; nil when the owner admitted none.
    let later: FieldMovementObservation10868?
    /// The owner's signed movement words ("+11.5 pp"). Printed only with a
    /// placed or off-scale change.
    let movement: String?
    /// The owner's opaque key for the later observation, handed back unchanged
    /// on open. Never read.
    let observation: String?
}

nonisolated struct FieldMovementTick10868: Equatable {
    /// Signed change in probability units (0.15 is 15 percentage points).
    let change: Double
    /// The owner's tick label ("+15 pp").
    let label: String
}

/// The owner's one symmetric signed scale for every bar.
nonisolated struct FieldMovementScale10868: Equatable {
    /// Bars run from −limit to +limit in probability units (0.15 is ±15 pp).
    /// 0 < limit <= 1.
    let limit: Double
    let ticks: [FieldMovementTick10868]
    /// The scale in words under the bars ("−15 to +15 percentage points").
    let words: String

    var isValid: Bool { limit.isFinite && limit > 0 && limit <= 1 }
}

/// The owner's words for this card in the actual phase.
nonisolated struct FieldMovementCopy10868: Equatable {
    /// "By noon, the outlook shifted".
    let title: String
    /// "Before day → captured by noon · percentage points"; nil draws none.
    let note: String?
    /// Spoken name of the bars.
    let graphicLabel: String
    /// Label of an earlier endpoint that cannot be shown ("Before the day").
    let beforeLabel: String
    /// Label of a later endpoint that cannot be shown ("Captured by noon").
    let laterLabel: String
    /// An endpoint not tied to this comparison ("Not recorded for this comparison").
    let endpointUnavailable: String
    /// No change can be placed ("Change unavailable").
    let changeUnavailable: String
    /// A change beyond the scale ("Beyond the ±15 pp scale").
    let offScale: String
    /// "Original · exact times" — shown only on a row that opens.
    let openLabel: String
    let openHint: String?
}

nonisolated struct FieldMovementInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    /// The bars, in the owner's order. Never sorted, capped or deduplicated here.
    let displayed: [FieldOutlookSlot10868]
    let pairs: [FieldMovementPair10868]
    let scale: FieldMovementScale10868
    let phase: FieldOutlookPhase10868
    let copy: FieldMovementCopy10868
    /// A slot that does not resolve ("Range unavailable in this update").
    let unavailableWords: String
}

/// What one endpoint shows.
nonisolated enum FieldMovementEndpoint10868: Equatable {
    /// The original's own reading: a tied figure, or the owner's absence words.
    case reading(FieldChooserReading10868)
    /// Not tied to this comparison: the copy's label and words, no figure.
    case unavailable(label: String, words: String)
}

/// Where a row's change sits on the shared scale.
nonisolated enum FieldMovementChange10868: Equatable {
    /// Raw later − raw before and its signed fraction of the limit; 0 is a
    /// neutral zero mark.
    case value(change: Double, fraction: Double)
    /// Beyond the limit: no fill, an edge mark pointing its way.
    case offScale(rising: Bool)
    /// Missing, duplicated, foreign, mismatched or invalid: nothing drawn.
    case unavailable

    var fraction: Double? {
        if case .value(_, let fraction) = self { return fraction }
        return nil
    }
}

nonisolated struct FieldMovementRow10868: Equatable {
    let slot: FieldOutlookSlot10868
    let resolution: FieldChooserResolution10868
    /// Nil when the slot does not resolve.
    let before: FieldMovementEndpoint10868?
    let later: FieldMovementEndpoint10868?
    let change: FieldMovementChange10868
}

/// Exactly what an open hands back.
nonisolated struct FieldMovementOpen10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The association's opaque later key, only while its later figure is shown.
    let observation: String?
}

/// What one signed bar draws inside its own rect, from the zero axis at the
/// middle: up or right when rising, down or left when falling.
nonisolated struct FieldMovementMarkPlan10868: Equatable {
    /// The exact fraction of the half-rect — never widened to a minimum.
    let fill: CGRect?
    /// An unchanged pair: a thin neutral mark across the zero axis.
    let zeroMark: CGRect?

    static let empty = FieldMovementMarkPlan10868(fill: nil, zeroMark: nil)
}

nonisolated enum FieldMovementGeometry10868 {
    /// Both endpoints and the limit are probabilities in 0...1, so storing them
    /// as binary Doubles and subtracting errs by at most one ulp of 1.0 (four
    /// half-ulps of 2⁻⁵⁴). A change past ±limit by no more than twice that is
    /// the limit itself: 0.65 − 0.5 is 0.15000000000000002 on a 0.15 scale.
    static let boundarySlack = 2 * Double.ulpOfOne

    /// A change's signed fraction of the limit, or none when it is not finite
    /// or beyond ±limit — never clamped. A change past the limit only by
    /// `boundarySlack` sits exactly on the edge. Both orientations use it.
    static func fraction(_ change: Double, limit: Double) -> Double? {
        guard limit.isFinite, limit > 0, limit <= 1, change.isFinite else { return nil }
        if abs(change) <= limit { return change / limit }
        guard abs(change) - limit <= boundarySlack else { return nil }
        return change > 0 ? 1 : -1
    }

    /// A signed fraction's place along the axis, 0...1 from the top when
    /// vertical and from the leading edge when horizontal. Zero is the middle.
    static func unit(_ fraction: Double, orientation: FieldOutlookOrientation10868) -> Double {
        orientation == .horizontal ? (1 + fraction) / 2 : (1 - fraction) / 2
    }

    /// The one drawing plan both bar Canvases use. Nothing for a missing,
    /// invalid or off-scale fraction or a size that cannot be drawn.
    static func markPlan(
        fraction: Double?,
        in size: CGSize,
        orientation: FieldOutlookOrientation10868
    ) -> FieldMovementMarkPlan10868 {
        guard let fraction, fraction.isFinite, fraction >= -1, fraction <= 1,
              size.width.isFinite, size.height.isFinite, size.width > 0, size.height > 0
        else { return .empty }
        if fraction == 0 {
            let mark = orientation == .horizontal
                ? CGRect(x: size.width / 2 - min(3, size.width) / 2, y: 0, width: min(3, size.width), height: size.height)
                : CGRect(x: 0, y: size.height / 2 - min(3, size.height) / 2, width: size.width, height: min(3, size.height))
            return FieldMovementMarkPlan10868(fill: nil, zeroMark: mark)
        }
        let magnitude = CGFloat(abs(fraction))
        if orientation == .horizontal {
            let half = size.width / 2
            let length = half * magnitude
            return FieldMovementMarkPlan10868(
                fill: CGRect(x: fraction > 0 ? half : half - length, y: 0, width: length, height: size.height),
                zeroMark: nil
            )
        }
        let half = size.height / 2
        let length = half * magnitude
        return FieldMovementMarkPlan10868(
            fill: CGRect(x: 0, y: fraction > 0 ? half - length : half, width: size.width, height: length),
            zeroMark: nil
        )
    }
}

/// The movement card's rules, resolved once per input, on the chooser's own model.
nonisolated struct FieldMovementModel10868: Equatable {
    let input: FieldMovementInput10868
    /// The chooser's resolver.
    let field: FieldChooserModel10868
    /// Displayed identities listed more than once.
    private let repeatedDisplayed: Set<FieldChooserOriginalRef10868>

    init(_ input: FieldMovementInput10868) {
        self.input = input
        // Only what the chooser's resolver reads; no chooser section is drawn
        // and nothing is selected.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope,
            intro: nil,
            featured: FieldChooserFeatured10868(
                title: input.copy.title, badge: nil,
                refs: input.displayed.map(\.ref), emptyWords: input.unavailableWords
            ),
            context: nil,
            more: nil,
            browse: nil,
            catalogue: input.catalogue,
            frame: nil,
            selected: nil,
            unavailableWords: input.unavailableWords,
            chooseHint: nil
        ))
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for slot in input.displayed { counts[slot.ref, default: 0] += 1 }
        repeatedDisplayed = Set(counts.filter { $0.value > 1 }.keys)
    }

    /// Before the day there is no card: no rows, words, artwork or actions.
    var isShown: Bool { input.phase != .before }

    /// A comparison plan's later reading; a single plan has none.
    static func laterReading(_ plan: FieldChooserDisplayPlan10868) -> FieldChooserReading10868? {
        if case .comparison(_, let later) = plan { return later }
        return nil
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    private static func isProbability(_ value: Double) -> Bool {
        value.isFinite && value >= 0 && value <= 1
    }

    // MARK: Rows

    var rows: [FieldMovementRow10868] {
        guard isShown else { return [] }
        return input.displayed.map { slot in
            let resolution: FieldChooserResolution10868 = repeatedDisplayed.contains(slot.ref) ? .unavailable : field.resolve(slot.ref)
            guard let original = resolution.original else {
                return FieldMovementRow10868(slot: slot, resolution: resolution, before: nil, later: nil, change: .unavailable)
            }
            let pair = self.pair(for: original.ref)
            return FieldMovementRow10868(
                slot: slot,
                resolution: resolution,
                before: endpoint(FieldOutlookModel10868.beforeReading(original.plan), tie: pair?.before, label: input.copy.beforeLabel),
                later: endpoint(Self.laterReading(original.plan), tie: pair?.later, label: input.copy.laterLabel),
                change: change(original.plan, pair)
            )
        }
    }

    /// The owner's one association for this original; several, even
    /// identical, are none.
    func pair(for ref: FieldChooserOriginalRef10868) -> FieldMovementPair10868? {
        let matches = input.pairs.filter { $0.ref == ref }
        return matches.count == 1 ? matches[0] : nil
    }

    /// The plan's own reading while its observation is tied; its own absence
    /// words as they are; otherwise the copy's endpoint words.
    func endpoint(_ reading: FieldChooserReading10868?, tie: FieldMovementObservation10868?, label: String) -> FieldMovementEndpoint10868 {
        let unavailable = FieldMovementEndpoint10868.unavailable(label: label, words: input.copy.endpointUnavailable)
        guard let reading else { return unavailable }
        switch reading.value {
        case .missing:
            return .reading(reading)
        case .recorded:
            return tie?.reading == reading ? .reading(reading) : unavailable
        }
    }

    /// The raw change, placed only when both endpoints are tied and valid and
    /// the owner's words exist.
    func change(_ plan: FieldChooserDisplayPlan10868, _ pair: FieldMovementPair10868?) -> FieldMovementChange10868 {
        guard case .comparison(let before, let later) = plan,
              let pair, let earlier = pair.before, let recorded = pair.later,
              case .recorded = before.value, case .recorded = later.value,
              earlier.reading == before, recorded.reading == later,
              Self.isProbability(earlier.probability), Self.isProbability(recorded.probability),
              Self.readable(pair.movement) != nil,
              input.scale.isValid
        else { return .unavailable }
        let change = recorded.probability - earlier.probability
        guard let fraction = FieldMovementGeometry10868.fraction(change, limit: input.scale.limit) else {
            return .offScale(rising: change > 0)
        }
        return .value(change: change, fraction: fraction)
    }

    /// The owner's ticks that sit on the scale, in the owner's order.
    var ticks: [FieldOutlookPlacedTick10868] {
        guard input.scale.isValid else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldMovementGeometry10868.fraction(tick.change, limit: input.scale.limit)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    // MARK: Words

    /// The owner's movement words, only beside a placed or off-scale change.
    func movementWords(_ row: FieldMovementRow10868) -> String? {
        guard let original = row.resolution.original else { return nil }
        switch row.change {
        case .value, .offScale: return Self.readable(pair(for: original.ref)?.movement)
        case .unavailable: return nil
        }
    }

    /// The words beside a row that draws no bar.
    func stateWords(_ row: FieldMovementRow10868) -> String? {
        guard row.resolution.original != nil else { return input.unavailableWords }
        switch row.change {
        case .value: return nil
        case .offScale: return input.copy.offScale
        case .unavailable: return input.copy.changeUnavailable
        }
    }

    static func spoken(_ endpoint: FieldMovementEndpoint10868) -> String {
        switch endpoint {
        case .reading(let reading): FieldChooserModel10868.spoken(reading)
        case .unavailable(let label, let words): "\(label): \(words)"
        }
    }

    /// A row's whole reading in the owner's words, so its bar may stay decorative.
    func rowSummary(_ row: FieldMovementRow10868) -> String {
        guard row.resolution.original != nil else {
            return [row.slot.label, input.unavailableWords]
                .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
                .joined(separator: ". ")
        }
        var parts = [row.before, row.later].compactMap { $0 }.map(Self.spoken)
        parts += [movementWords(row), stateWords(row)].compactMap { $0 }
        return parts.joined(separator: ". ")
    }

    /// The bars in words, one row after another in the owner's order.
    var graphicSummary: String {
        rows.map { row in
            [row.slot.label, movementWords(row) ?? stateWords(row) ?? ""]
                .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
                .joined(separator: ": ")
        }
        .filter { !$0.isEmpty }
        .joined(separator: "; ")
    }

    // MARK: Open

    /// The exact original, and its later key while that figure is shown —
    /// only with a callback.
    func openAction(_ row: FieldMovementRow10868, canOpen: Bool) -> FieldMovementOpen10868? {
        guard canOpen, let original = row.resolution.original else { return nil }
        var observation: String?
        if case .reading(let reading)? = row.later, case .recorded = reading.value {
            observation = Self.readable(pair(for: original.ref)?.observation)
        }
        return FieldMovementOpen10868(ref: original.ref, observation: observation)
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ opening: FieldMovementOpen10868?) -> String {
        opening == nil ? "" : (input.copy.openHint ?? "")
    }
}

nonisolated enum FieldMovementAccessibilityID10868 {
    static let graphic = "fieldMovement10868.graphic"
    static func row(_ outcomeID: String) -> String { "fieldMovement10868.row.\(outcomeID)" }
}

struct FieldMovementPresentation10868: View {
    let input: FieldMovementInput10868
    var onOpen: ((FieldMovementOpen10868) -> Void)?
    private let model: FieldMovementModel10868

    init(input: FieldMovementInput10868, onOpen: ((FieldMovementOpen10868) -> Void)? = nil) {
        self.input = input
        self.onOpen = onOpen
        self.model = FieldMovementModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var plotHeight: CGFloat = 140
    @ScaledMetric(relativeTo: .caption) private var barWidth: CGFloat = 32
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 16

    private var canOpen: Bool { onOpen != nil }

    var body: some View {
        if model.isShown {
            VStack(alignment: .leading, spacing: 12) {
                Text(input.copy.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let note = input.copy.note {
                    ownerWords(note)
                }
                let rows = model.rows
                if !rows.isEmpty {
                    graphic(rows)
                    if input.scale.isValid {
                        Text(input.scale.words)
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                            valueRow(row)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Bars

    @ViewBuilder private func graphic(_ rows: [FieldMovementRow10868]) -> some View {
        Group {
            if FieldOutlookGeometry10868.orientations(accessibilitySize: typeSize.isAccessibilitySize) == [.horizontal] {
                horizontalBars(rows)
            } else {
                ViewThatFits(in: .horizontal) {
                    verticalBars(rows)
                    horizontalBars(rows)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.copy.graphicLabel)
        .accessibilityValue(model.graphicSummary)
        .accessibilityIdentifier(FieldMovementAccessibilityID10868.graphic)
    }

    private var accentDefault: Color { DS.blue }

    private func accent(_ row: FieldMovementRow10868) -> Color {
        row.resolution.original?.accent ?? accentDefault
    }

    private func verticalBars(_ rows: [FieldMovementRow10868]) -> some View {
        let ticks = model.ticks
        return HStack(alignment: .top, spacing: 0) {
            if !ticks.isEmpty {
                verticalAxis(ticks)
                    .padding(.trailing, 6)
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                VStack(spacing: 6) {
                    signedBar(row.change.fraction, orientation: .vertical, accent: accent(row))
                        .frame(width: barWidth, height: plotHeight)
                        .overlay(alignment: edgeAlignment(row.change, orientation: .vertical)) {
                            edgeMark(row.change, orientation: .vertical)
                        }
                    Text(row.slot.shortLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(row.resolution.original == nil ? DS.textSecondary : DS.textPrimary)
                        .fixedSize()
                }
                .padding(.horizontal, 8)
                .frame(minWidth: 44, alignment: .top)
                .background(alignment: .top) {
                    grid(ticks, orientation: .vertical).frame(height: plotHeight)
                }
            }
        }
        .padding(.vertical, 8)
    }

    /// The owner's tick labels, each centred on its gridline. Decorative — the
    /// graphic speaks every row.
    private func verticalAxis(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
        let plot = plotHeight
        return ZStack {
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.label).font(.caption2).fixedSize().hidden()
            }
        }
        .frame(height: plot, alignment: .top)
        .overlay(alignment: .topTrailing) {
            ZStack(alignment: .topTrailing) {
                ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                    Text(tick.label)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize()
                        .alignmentGuide(.top) { d in
                            d[VerticalAlignment.center] - CGFloat(FieldMovementGeometry10868.unit(tick.fraction, orientation: .vertical)) * plot
                        }
                }
            }
        }
        .accessibilityHidden(true)
    }

    /// Gridlines at the owner's ticks and a stronger zero axis.
    private func grid(_ ticks: [FieldOutlookPlacedTick10868], orientation: FieldOutlookOrientation10868) -> some View {
        let lineColor = DS.border
        let axisColor = DS.textSecondary
        let fractions = ticks.map(\.fraction)
        return Canvas { context, size in
            func line(_ fraction: Double) -> Path {
                let unit = CGFloat(FieldMovementGeometry10868.unit(fraction, orientation: orientation))
                var path = Path()
                if orientation == .horizontal {
                    path.move(to: CGPoint(x: size.width * unit, y: 0))
                    path.addLine(to: CGPoint(x: size.width * unit, y: size.height))
                } else {
                    path.move(to: CGPoint(x: 0, y: size.height * unit))
                    path.addLine(to: CGPoint(x: size.width, y: size.height * unit))
                }
                return path
            }
            for fraction in fractions where fraction != 0 {
                context.stroke(line(fraction), with: .color(lineColor), lineWidth: 1)
            }
            context.stroke(line(0), with: .color(axisColor), lineWidth: 1.5)
        }
        .accessibilityHidden(true)
    }

    /// One signed bar from the shared mark plan. Off-scale and unavailable draw no fill.
    private func signedBar(_ fraction: Double?, orientation: FieldOutlookOrientation10868, accent: Color) -> some View {
        Canvas { context, size in
            let plan = FieldMovementGeometry10868.markPlan(fraction: fraction, in: size, orientation: orientation)
            if let mark = plan.zeroMark { context.fill(Path(mark), with: .color(accent)) }
            if let fill = plan.fill { context.fill(Path(fill), with: .color(accent)) }
        }
        .accessibilityHidden(true)
    }

    private func edgeAlignment(_ change: FieldMovementChange10868, orientation: FieldOutlookOrientation10868) -> Alignment {
        guard case .offScale(let rising) = change else { return .center }
        switch orientation {
        case .vertical: return rising ? .top : .bottom
        case .horizontal: return rising ? .trailing : .leading
        }
    }

    /// A change beyond the scale: a mark at the edge it points past, never a clamped fill.
    @ViewBuilder private func edgeMark(_ change: FieldMovementChange10868, orientation: FieldOutlookOrientation10868) -> some View {
        if case .offScale(let rising) = change {
            let symbol = orientation == .vertical
                ? (rising ? "arrow.up.to.line" : "arrow.down.to.line")
                : (rising ? "arrow.right.to.line" : "arrow.left.to.line")
            Image(systemName: symbol)
                .font(.caption2.weight(.bold))
                .foregroundStyle(DS.textSecondary)
                .accessibilityHidden(true)
        }
    }

    private func horizontalBars(_ rows: [FieldMovementRow10868]) -> some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                VStack(alignment: .leading, spacing: 4) {
                    if !row.slot.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text(row.slot.label)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(row.resolution.original == nil ? DS.textSecondary : DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    signedBar(row.change.fraction, orientation: .horizontal, accent: accent(row))
                        .frame(height: trackHeight)
                        .background { grid(ticks, orientation: .horizontal) }
                        .overlay(alignment: edgeAlignment(row.change, orientation: .horizontal)) {
                            edgeMark(row.change, orientation: .horizontal)
                        }
                }
            }
            if !ticks.isEmpty {
                horizontalAxis(ticks)
            }
        }
    }

    /// The owner's tick labels under the horizontal bars, each at its place;
    /// the end labels stay inside the width. Decorative.
    private func horizontalAxis(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
        Text(ticks[0].label)
            .font(.caption2)
            .hidden()
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay {
                GeometryReader { proxy in
                    let width = proxy.size.width
                    ZStack(alignment: .leading) {
                        ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                            Text(tick.label)
                                .font(.caption2)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize()
                                .alignmentGuide(.leading) { d in
                                    let anchor = tick.fraction <= -1 ? d[.leading]
                                        : tick.fraction >= 1 ? d[.trailing] : d[HorizontalAlignment.center]
                                    return anchor - width * CGFloat(FieldMovementGeometry10868.unit(tick.fraction, orientation: .horizontal))
                                }
                        }
                    }
                    .frame(width: width, height: proxy.size.height, alignment: .leading)
                }
            }
            .accessibilityHidden(true)
    }

    // MARK: Values

    @ViewBuilder private func valueRow(_ row: FieldMovementRow10868) -> some View {
        let id = FieldMovementAccessibilityID10868.row(row.slot.ref.outcomeID)
        if let original = row.resolution.original {
            let opening = model.openAction(row, canOpen: canOpen)
            control(opening) {
                VStack(alignment: .leading, spacing: 8) {
                    heading(row)
                    if let words = model.stateWords(row) {
                        ownerWords(words)
                    }
                    endpoints(row)
                    if opening != nil {
                        HStack(spacing: 6) {
                            Text(input.copy.openLabel)
                                .fixedSize(horizontal: false, vertical: true)
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.semibold))
                                .accessibilityHidden(true)
                        }
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.blue)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(DS.border, lineWidth: 1))
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.rowSummary(row))
            .accessibilityHint(model.hint(opening))
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if !row.slot.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(row.slot.label)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.unavailableWords)
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(DS.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.rowSummary(row))
            .accessibilityIdentifier(id)
        }
    }

    /// The range's whole label and the owner's movement words.
    private func heading(_ row: FieldMovementRow10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        return layout {
            Text(row.slot.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if !typeSize.isAccessibilitySize { Spacer(minLength: 8) }
            if let words = model.movementWords(row) {
                Text(words)
                    .font(.headline)
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Both endpoints at the same size, each with its own label and clock;
    /// stacked at accessibility sizes.
    private func endpoints(_ row: FieldMovementRow10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
        return layout {
            if let before = row.before { endpoint(before) }
            if let later = row.later { endpoint(later) }
        }
    }

    private func endpoint(_ endpoint: FieldMovementEndpoint10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            switch endpoint {
            case .reading(let reading):
                Text(reading.label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                switch reading.value {
                case .recorded(let text, _):
                    Text(text)
                        .font(.system(size: figureSize, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                case .missing(let words):
                    Text(words)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let line = FieldOutlookModel10868.detailLine(reading) {
                    Text(line)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            case .unavailable(let label, let words):
                Text(label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func control<Content: View>(_ opening: FieldMovementOpen10868?, @ViewBuilder content: () -> Content) -> some View {
        if let opening, let onOpen {
            Button {
                onOpen(opening)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - #10868 field finish — "How the race finished"
//
// The horse-racing final card, built on the outlook above. A fan sees each of
// the owner's displayed runners as two lines: the whole runner name with its
// actual reported finish ("1st finish"), then a full-width strip on ONE shared
// zero-based probability scale with a single labelled dot at that runner's own
// earlier win chance — the last eligible observation before the SCHEDULED
// start, never a verified actual start, a closing quote or a current price.
// Tapping a runner opens that exact original's history. The card exists at the
// final only; before and during the race there is no card at all.
//
// Presentation only, from the approved `HorseFinishComparison.tsx`,
// `horseFinishComparison.css` and its `HorseRacing.tsx` result mount. The
// reference's schedule and baseline election (`lastBefore`), ordinal suffixes,
// ceiling ladder (`horseFinishUpper`), place filter, name-based Other
// exclusion, sort by place and settlement reading are NOT ported. All of that
// arrives as owner input: the displayed refs in the owner's order, the
// canonical catalogue, each runner's independently admitted finish, the raw
// before chance tied to its formatted before reading, the scale and the phase.
//
// Identity, the raw chance, the selected cue and notice, and every scale state
// go through `FieldOutlookModel10868` on the chooser's own
// `FieldChooserModel10868` — the same resolver, tie and placement the outlook
// bars use. A slot repeated in the displayed list, or one that does not
// resolve, keeps the owner's name beside the unavailable words and borrows no
// finish, figure, dot or action; its neighbours keep theirs.
//
// The finish is the owner's ONE association for that exact original, shown as
// it is: a whole ordinal with its source, or the owner's absence words. It is
// never read from the original's result, its chance, its position in a list or
// any later quote, and its units never share the probability axis. Several
// associations for one original, even identical ones, or a blank one are none.
//
// The dot sits at the raw chance's exact fraction of the ceiling. A real 0% is
// a dot at zero; above the ceiling there is no dot, only an edge mark and the
// owner's off-scale words beside the runner's own figure; a missing,
// mismatched or invalid chance draws nothing. Nothing is parsed, normalized,
// complemented, summed or clamped. The figure above a dot is measured and
// centred on it while that keeps it inside the strip, else slid inward just
// enough — the dot never moves; a figure wider than the strip gets its own line.
//
// The host owns the scroll, the reader, history, Details, Back and focus; this
// leaf keeps no state. With no callback, nothing pretends to act.
//
// Host binding still owed: FIELD-FINISH-CHANCES-NATIVE-BINDING-MAP.md.

/// One owner-admitted physical finish, tied to the exact original it was
/// reported for. Never a chance.
nonisolated struct FieldFinishPlace10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// "Reported finish": the owner's whole ordinal and its source
    /// (`.recorded("1st", "Sporting Life")`) or the owner's absence words.
    let reading: FieldChooserReading10868
}

/// One displayed runner, in the owner's order.
nonisolated struct FieldFinishSlot10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's full name, kept beside the unavailable words when the slot
    /// does not resolve.
    let name: String
}

/// The owner's words for this card.
nonisolated struct FieldFinishCopy10868: Equatable {
    /// "How the race finished".
    let title: String
    /// "Before scheduled start · recorded at different times"; nil draws none.
    let context: String?
    /// "Pre-race win chance" — the strip's quantity, beside the scale words.
    let scaleLabel: String
    /// Spoken name of the rows.
    let graphicLabel: String
    /// Label of a finish that cannot be shown ("Reported finish").
    let finishLabel: String
    /// The unit word beside a reported ordinal ("finish").
    let finishUnit: String
    /// A finish not tied to this original ("Finish not confirmed for this runner").
    let finishUnavailable: String
    /// A chance that cannot be placed ("Not shown on this scale").
    let chanceUnavailable: String
    /// A chance above the ceiling ("Above the 50% scale").
    let offScale: String
    /// The selected original is not among the rows.
    let outsideDisplayed: String
    /// No displayed rows ("No finishing positions captured").
    let empty: String
    /// "5 reported finishes"; nil draws none.
    let count: String?
    /// "Tap a horse for its history" — shown only while a row opens.
    let openPrompt: String?
    let openHint: String?
}

nonisolated struct FieldFinishInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    let selected: FieldChooserSelected10868?
    /// The rows, in the owner's order. Never sorted, filtered, capped or deduplicated here.
    let displayed: [FieldFinishSlot10868]
    let finishes: [FieldFinishPlace10868]
    let chances: [FieldOutlookBeforeChance10868]
    let scale: FieldOutlookScale10868
    let phase: FieldOutlookPhase10868
    let copy: FieldFinishCopy10868
    /// A slot that does not resolve ("Runner unavailable in this update").
    let unavailableWords: String
}

nonisolated struct FieldFinishRow10868: Equatable {
    let slot: FieldFinishSlot10868
    /// The outlook's bar for the same slot: resolution and raw chance on the shared scale.
    let bar: FieldOutlookBar10868
    /// Nil when the slot does not resolve.
    let finish: FieldMovementEndpoint10868?

    var resolution: FieldChooserResolution10868 { bar.resolution }
    var chance: FieldOutlookChance10868 { bar.chance }
}

/// What one strip draws inside its own rect.
nonisolated struct FieldFinishStripPlan10868: Equatable {
    let baselineY: CGFloat
    /// The zero and ceiling ends of the scale line.
    let zeroX: CGFloat
    let ceilingX: CGFloat
    /// Zero and every owner tick on the scale.
    let tickXs: [CGFloat]
    let tickTop: CGFloat
    /// The dot, centred exactly on its value; nil draws none.
    let dot: CGRect?
}

nonisolated enum FieldFinishGeometry10868 {
    /// A fraction's x on a strip of `width`, inset so a dot at zero or at the
    /// ceiling stays whole. None when it is not finite or outside 0...1 —
    /// never clamped. Dots, ticks and axis labels all use it.
    static func x(of fraction: Double, width: CGFloat, inset: CGFloat) -> CGFloat? {
        guard fraction.isFinite, fraction >= 0, fraction <= 1,
              width.isFinite, inset.isFinite, inset >= 0, width > 2 * inset
        else { return nil }
        return inset + (width - 2 * inset) * CGFloat(fraction)
    }

    /// Where a measured label starts: centred on its mark while that keeps it
    /// inside the width, else slid inward just enough. The mark never moves.
    /// None when the label is wider than the width: it gets its own line.
    static func labelOrigin(markX: CGFloat, labelWidth: CGFloat, width: CGFloat) -> CGFloat? {
        guard markX.isFinite, labelWidth.isFinite, width.isFinite,
              width > 0, labelWidth >= 0, labelWidth <= width, markX >= 0, markX <= width
        else { return nil }
        return min(max(markX - labelWidth / 2, 0), width - labelWidth)
    }

    /// The one drawing plan every strip Canvas uses. Nil for a size that
    /// cannot be drawn; no dot for a missing, off-scale or invalid fraction.
    static func stripPlan(fraction: Double?, ticks: [Double], in size: CGSize, inset: CGFloat, dotDiameter: CGFloat) -> FieldFinishStripPlan10868? {
        guard size.height.isFinite, dotDiameter.isFinite, dotDiameter > 0, size.height >= dotDiameter,
              let zero = x(of: 0, width: size.width, inset: inset),
              let ceiling = x(of: 1, width: size.width, inset: inset)
        else { return nil }
        let baseline = size.height - dotDiameter / 2
        let dot = fraction.flatMap { x(of: $0, width: size.width, inset: inset) }.map {
            CGRect(x: $0 - dotDiameter / 2, y: baseline - dotDiameter / 2, width: dotDiameter, height: dotDiameter)
        }
        return FieldFinishStripPlan10868(
            baselineY: baseline,
            zeroX: zero,
            ceilingX: ceiling,
            tickXs: ([0] + ticks).compactMap { x(of: $0, width: size.width, inset: inset) },
            tickTop: max(0, baseline - 6),
            dot: dot
        )
    }

    /// At accessibility sizes the unit word sits under the ordinal, not beside it.
    static func stacksFinishUnit(accessibilitySize: Bool) -> Bool {
        accessibilitySize
    }
}

/// The finish card's rules, resolved once per input, on the outlook's own model.
nonisolated struct FieldFinishModel10868: Equatable {
    let input: FieldFinishInput10868
    /// The outlook's resolver, raw-chance tie, scale and selection rules.
    let outlook: FieldOutlookModel10868

    init(_ input: FieldFinishInput10868) {
        self.input = input
        // Only what the outlook's bar, chance, tick and selection rules read;
        // no stepping, details or result line is used.
        outlook = FieldOutlookModel10868(FieldOutlookInput10868(
            scope: input.scope,
            catalogue: input.catalogue,
            selected: input.selected,
            displayed: input.displayed.map { FieldOutlookSlot10868(ref: $0.ref, label: $0.name, shortLabel: $0.name) },
            traversal: [],
            chances: input.chances,
            scale: input.scale,
            phase: input.phase,
            copy: FieldOutlookCopy10868(
                title: input.copy.title,
                note: nil,
                graphicLabel: input.copy.graphicLabel,
                missingChance: input.copy.chanceUnavailable,
                offScale: input.copy.offScale,
                outsideDisplayed: input.copy.outsideDisplayed,
                previousLabel: "",
                nextLabel: "",
                details: "",
                detailsHint: nil,
                resultUnknown: ""
            ),
            unavailableWords: input.unavailableWords,
            chooseHint: nil
        ))
    }

    var field: FieldChooserModel10868 { outlook.field }

    /// Only at the final: before and during there are no rows, words, artwork or actions.
    var isShown: Bool { input.phase == .final }

    // MARK: Rows

    var rows: [FieldFinishRow10868] {
        guard isShown else { return [] }
        return zip(input.displayed, outlook.bars).map { slot, bar in
            FieldFinishRow10868(slot: slot, bar: bar, finish: bar.resolution.original.map { finish(for: $0.ref) })
        }
    }

    /// The owner's one finish association for this original, as it is; several
    /// (even identical), a blank one or none show the copy's words.
    func finish(for ref: FieldChooserOriginalRef10868) -> FieldMovementEndpoint10868 {
        let unavailable = FieldMovementEndpoint10868.unavailable(label: input.copy.finishLabel, words: input.copy.finishUnavailable)
        let matches = input.finishes.filter { $0.ref == ref }
        guard matches.count == 1 else { return unavailable }
        let reading = matches[0].reading
        switch reading.value {
        case .recorded(let text, _):
            return FieldMovementModel10868.readable(text) == nil ? unavailable : .reading(reading)
        case .missing(let words):
            return FieldMovementModel10868.readable(words) == nil ? unavailable : .reading(reading)
        }
    }

    /// A shown finish's whole ordinal; nil when the finish is words.
    static func ordinal(_ finish: FieldMovementEndpoint10868?) -> String? {
        guard case .reading(let reading)? = finish, case .recorded(let text, _) = reading.value else { return nil }
        return text
    }

    /// A finish shown as words: the owner's absence words or the copy's.
    static func finishWords(_ finish: FieldMovementEndpoint10868?) -> String? {
        switch finish {
        case .reading(let reading)?:
            if case .missing(let words) = reading.value { return words }
            return nil
        case .unavailable(_, let words)?:
            return words
        case nil:
            return nil
        }
    }

    /// The owner's ticks that sit on the scale, in the owner's order.
    var ticks: [FieldOutlookPlacedTick10868] { isShown ? outlook.ticks : [] }

    /// The runner's own before figure, or its own absence words.
    func figure(_ row: FieldFinishRow10868) -> String? { outlook.figure(row.bar) }

    /// The figure printed above a dot — only while the dot is placed.
    func dotLabel(_ row: FieldFinishRow10868) -> String? {
        guard case .value = row.chance else { return nil }
        return figure(row)
    }

    /// The words beside a strip that draws no dot.
    func stateWords(_ row: FieldFinishRow10868) -> String? { outlook.stateWords(row.bar) }

    func isSelected(_ row: FieldFinishRow10868) -> Bool { outlook.isSelected(row.bar) }

    // MARK: Open

    /// The exact original whose history a row opens — only with a callback.
    func openAction(_ row: FieldFinishRow10868, canOpen: Bool) -> FieldChooserOriginalRef10868? {
        canOpen ? row.resolution.original?.ref : nil
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ ref: FieldChooserOriginalRef10868?) -> String {
        ref == nil ? "" : (input.copy.openHint ?? "")
    }

    /// The owner's prompt, only while some row actually opens.
    func openPrompt(canOpen: Bool) -> String? {
        guard canOpen, rows.contains(where: { $0.resolution.original != nil }) else { return nil }
        return FieldMovementModel10868.readable(input.copy.openPrompt)
    }

    // MARK: Selection

    /// An unresolved selection's words, else the outside-the-rows notice.
    var notice: String? { isShown ? outlook.notice : nil }

    /// A selected original that resolves but is not among the rows: kept by
    /// identity, never replaced by a plotted neighbour.
    var selectedOutside: FieldChooserOriginal10868? {
        guard isShown, outlook.isSelectedOutsideDisplayed else { return nil }
        return outlook.selectedOriginal
    }

    func outsideAction(canOpen: Bool) -> FieldChooserOriginalRef10868? {
        canOpen ? selectedOutside?.ref : nil
    }

    // MARK: VoiceOver

    /// A row's whole reading in the owner's words, so its strip may stay decorative.
    func rowSummary(_ row: FieldFinishRow10868) -> String {
        guard let original = row.resolution.original else {
            return [row.slot.name, input.unavailableWords]
                .filter { FieldMovementModel10868.readable($0) != nil }
                .joined(separator: ". ")
        }
        var parts: [String] = []
        if let words = field.selectedWords(original) { parts.append(words) }
        if let finish = row.finish { parts.append(FieldMovementModel10868.spoken(finish)) }
        parts.append(FieldChooserModel10868.spoken(FieldOutlookModel10868.beforeReading(original.plan)))
        if let words = stateWords(row) { parts.append(words) }
        return parts.joined(separator: ". ")
    }
}

nonisolated enum FieldFinishAccessibilityID10868 {
    static let rows = "fieldFinish10868.rows"
    static let outside = "fieldFinish10868.outside"
    static func row(_ outcomeID: String) -> String { "fieldFinish10868.row.\(outcomeID)" }
}

/// The figure above, the strip below. The figure is measured and placed by
/// `FieldFinishGeometry10868.labelOrigin` against the dot's own x; wider than
/// the strip, it wraps whole on its own line.
struct FieldFinishStripLayout10868: Layout {
    var fraction: Double
    var inset: CGFloat
    var spacing: CGFloat

    private func origin(_ width: CGFloat, _ label: CGSize) -> CGFloat? {
        guard let markX = FieldFinishGeometry10868.x(of: fraction, width: width, inset: inset) else { return nil }
        return FieldFinishGeometry10868.labelOrigin(markX: markX, labelWidth: label.width, width: width)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 2 else { return .zero }
        let ideal = subviews[0].sizeThatFits(.unspecified)
        let track = subviews[1].sizeThatFits(ProposedViewSize(width: proposal.width, height: nil))
        let width = proposal.width ?? max(ideal.width, track.width)
        let label = origin(width, ideal) == nil
            ? subviews[0].sizeThatFits(ProposedViewSize(width: width, height: nil))
            : ideal
        return CGSize(width: width, height: label.height + spacing + track.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let ideal = subviews[0].sizeThatFits(.unspecified)
        let x = origin(bounds.width, ideal)
        let label = x == nil
            ? subviews[0].sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
            : ideal
        subviews[0].place(
            at: CGPoint(x: bounds.minX + (x ?? 0), y: bounds.minY),
            anchor: .topLeading,
            proposal: ProposedViewSize(width: x == nil ? bounds.width : ideal.width, height: label.height)
        )
        let track = subviews[1].sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
        subviews[1].place(
            at: CGPoint(x: bounds.minX, y: bounds.minY + label.height + spacing),
            anchor: .topLeading,
            proposal: ProposedViewSize(width: bounds.width, height: track.height)
        )
    }
}

struct FieldFinishComparisonPresentation10868: View {
    let input: FieldFinishInput10868
    var onOpenHistory: ((FieldChooserOriginalRef10868) -> Void)?
    private let model: FieldFinishModel10868

    init(input: FieldFinishInput10868, onOpenHistory: ((FieldChooserOriginalRef10868) -> Void)? = nil) {
        self.input = input
        self.onOpenHistory = onOpenHistory
        self.model = FieldFinishModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var ordinalSize: CGFloat = 23
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 18
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 16
    @ScaledMetric(relativeTo: .caption) private var dotDiameter: CGFloat = 10

    private var canOpen: Bool { onOpenHistory != nil }
    /// Half a dot and a hair, so a dot at zero or at the ceiling stays whole.
    private var inset: CGFloat { dotDiameter / 2 + 1 }

    var body: some View {
        if model.isShown {
            VStack(alignment: .leading, spacing: 10) {
                Text(input.copy.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let context = input.copy.context {
                    ownerWords(context)
                }
                if let notice = model.notice {
                    Text(notice)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                outsidePanel
                let rows = model.rows
                if rows.isEmpty {
                    ownerWords(input.copy.empty)
                } else {
                    scaleHeader
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                            runner(row)
                        }
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(input.copy.graphicLabel)
                    .accessibilityIdentifier(FieldFinishAccessibilityID10868.rows)
                    if let count = input.copy.count {
                        ownerWords(count)
                    }
                    if let prompt = model.openPrompt(canOpen: canOpen) {
                        ownerWords(prompt)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Scale

    /// The strip's quantity and the owner's scale words, then the owner's tick
    /// labels on the same inset the dots use. Decorative — each row speaks.
    @ViewBuilder private var scaleHeader: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
        layout {
            Text(input.copy.scaleLabel)
                .fixedSize(horizontal: false, vertical: true)
            if !typeSize.isAccessibilitySize { Spacer(minLength: 8) }
            if input.scale.isValid {
                Text(input.scale.words)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        let ticks = model.ticks
        if !ticks.isEmpty {
            axis(ticks)
        }
    }

    private func axis(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
        let inset = self.inset
        return Text(ticks[0].label)
            .font(.caption2)
            .hidden()
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay {
                GeometryReader { proxy in
                    let width = proxy.size.width
                    ZStack(alignment: .leading) {
                        ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                            Text(tick.label)
                                .font(.caption2)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize()
                                .alignmentGuide(.leading) { d in
                                    let markX = FieldFinishGeometry10868.x(of: tick.fraction, width: width, inset: inset) ?? 0
                                    return -(FieldFinishGeometry10868.labelOrigin(markX: markX, labelWidth: d.width, width: width) ?? 0)
                                }
                        }
                    }
                    .frame(width: width, height: proxy.size.height, alignment: .leading)
                }
            }
            .accessibilityHidden(true)
    }

    // MARK: Rows

    @ViewBuilder private func runner(_ row: FieldFinishRow10868) -> some View {
        let id = FieldFinishAccessibilityID10868.row(row.slot.ref.outcomeID)
        if let original = row.resolution.original {
            let opening = model.openAction(row, canOpen: canOpen)
            let selected = model.isSelected(row)
            control(opening) {
                VStack(alignment: .leading, spacing: 6) {
                    heading(original, finish: row.finish)
                    strip(row, original: original)
                }
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.rowSummary(row))
            .accessibilityHint(model.hint(opening))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if FieldMovementModel10868.readable(row.slot.name) != nil {
                    Text(row.slot.name)
                        .font(.body)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.unavailableWords)
            }
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.rowSummary(row))
            .accessibilityIdentifier(id)
        }
    }

    /// The whole name and the reported ordinal on one line; a finish shown as
    /// words wraps under the name instead.
    private func heading(_ original: FieldChooserOriginal10868, finish: FieldMovementEndpoint10868?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(original.name)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let words = model.field.selectedWords(original) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark").font(.caption2.weight(.bold))
                            Text(words).font(.caption.weight(.semibold))
                        }
                        .foregroundStyle(DS.blue)
                        .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let ordinal = FieldFinishModel10868.ordinal(finish) {
                    ordinalBlock(ordinal)
                }
            }
            if let words = FieldFinishModel10868.finishWords(finish) {
                ownerWords(words)
            }
        }
    }

    private func ordinalBlock(_ ordinal: String) -> some View {
        let layout = FieldFinishGeometry10868.stacksFinishUnit(accessibilitySize: typeSize.isAccessibilitySize)
            ? AnyLayout(VStackLayout(alignment: .trailing, spacing: 0))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 5))
        return layout {
            Text(ordinal)
                .font(.system(size: ordinalSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
            Text(input.copy.finishUnit)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize()
        }
    }

    /// A placed dot with its measured figure; off the scale, the runner's own
    /// figure and words beside an empty strip with an edge mark; otherwise words only.
    @ViewBuilder private func strip(_ row: FieldFinishRow10868, original: FieldChooserOriginal10868) -> some View {
        let accent = original.accent ?? DS.blue
        let ticks = model.ticks.map(\.fraction)
        switch row.chance {
        case .value(_, let fraction):
            FieldFinishStripLayout10868(fraction: fraction, inset: inset, spacing: 2) {
                Text(model.dotLabel(row) ?? "")
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                track(fraction: fraction, ticks: ticks, accent: accent)
            }
        case .offScale:
            VStack(alignment: .leading, spacing: 4) {
                track(fraction: nil, ticks: ticks, accent: accent)
                    .overlay(alignment: .trailing) {
                        Image(systemName: "arrow.right.to.line")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DS.textSecondary)
                            .accessibilityHidden(true)
                    }
                valueWords(row, original: original)
            }
        case .unavailable:
            valueWords(row, original: original)
        }
    }

    /// The scale line, zero and the owner's ticks, then the dot from the shared plan.
    private func track(fraction: Double?, ticks: [Double], accent: Color) -> some View {
        let lineColor = DS.border
        let ringFill = DS.cardBg
        let inset = self.inset
        let diameter = dotDiameter
        return Canvas { context, size in
            guard let plan = FieldFinishGeometry10868.stripPlan(fraction: fraction, ticks: ticks, in: size, inset: inset, dotDiameter: diameter) else { return }
            var line = Path()
            line.move(to: CGPoint(x: plan.zeroX, y: plan.baselineY))
            line.addLine(to: CGPoint(x: plan.ceilingX, y: plan.baselineY))
            context.stroke(line, with: .color(lineColor), lineWidth: 2)
            for x in plan.tickXs {
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: plan.tickTop))
                tick.addLine(to: CGPoint(x: x, y: plan.baselineY))
                context.stroke(tick, with: .color(lineColor), lineWidth: 1)
            }
            if let dot = plan.dot {
                context.fill(Path(ellipseIn: dot), with: .color(ringFill))
                context.stroke(Path(ellipseIn: dot.insetBy(dx: 1, dy: 1)), with: .color(accent), lineWidth: 2)
            }
        }
        .frame(maxWidth: .infinity, minHeight: trackHeight, maxHeight: trackHeight)
        .accessibilityHidden(true)
    }

    /// The runner's own figure (or absence words) and the words for a strip with no dot.
    private func valueWords(_ row: FieldFinishRow10868, original: FieldChooserOriginal10868) -> some View {
        let recorded: Bool
        if case .recorded = FieldOutlookModel10868.beforeReading(original.plan).value { recorded = true } else { recorded = false }
        return VStack(alignment: .leading, spacing: 2) {
            if let figure = model.figure(row) {
                Text(figure)
                    .font(recorded ? Font.system(size: figureSize, weight: .bold) : Font.subheadline.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(recorded ? DS.textPrimary : DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let words = model.stateWords(row) {
                ownerWords(words)
            }
        }
    }

    // MARK: Selected outside the rows

    @ViewBuilder private var outsidePanel: some View {
        if let original = model.selectedOutside {
            let opening = model.outsideAction(canOpen: canOpen)
            control(opening) {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(original.name)
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        if let words = model.field.selectedWords(original) {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark").font(.caption2.weight(.bold))
                                Text(words).font(.caption.weight(.semibold))
                            }
                            .foregroundStyle(DS.blue)
                            .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer(minLength: 8)
                    if opening != nil {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .accessibilityHidden(true)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(DS.border, lineWidth: 1))
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.field.selectedWords(original) ?? "")
            .accessibilityHint(model.hint(opening))
            .accessibilityAddTraits(.isSelected)
            .accessibilityIdentifier(FieldFinishAccessibilityID10868.outside)
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
    private func control<Content: View>(_ ref: FieldChooserOriginalRef10868?, @ViewBuilder content: () -> Content) -> some View {
        if let ref, let onOpenHistory {
            Button {
                onOpenHistory(ref)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - #10868 field chase — "Leclerc's chase"
//
// The racing-live chase card, built on the movement card above. During the
// race a fan sees how the owner's reported gap between a challenger and the
// leader changed, report by report, as points on one seconds-by-lap plot (lower
// is closer), beside the challenger's own pre-race and recorded win chances at
// the same figure size, each with its own clock. The card exists during the
// race only; before the start and at the final there is no card at all — the
// final has its own finish story.
//
// Presentation only, from the approved `RacingLive.tsx` `Chase` and
// `RaceChancePair` and `racingLive.css` (`.race-chase-gap`, `.race-chance-pair`,
// `.race-gap-plot`, larger-text variants). The reference's baseline election,
// five-minute quote eligibility, trade cleaning, stage selection, gap
// arithmetic ("5.9 seconds closer"), number, percent and clock formatting,
// driver indexing and settlement reading are NOT ported. All of that arrives as
// owner input: the canonical catalogue, the exact challenger, the qualified
// before and recorded observations tied to their formatted readings, the
// explicit phase, the owner-ordered report runs with their highlighted report,
// the axis bounds and ticks, and every headline, label and absence word.
//
// The challenger and both of its chances go through `FieldMovementModel10868`
// on the chooser's own `FieldChooserModel10868` — the same resolver and the same
// endpoint tie the movement rows use: a figure is shown only while the owner's
// ONE association for that exact original carries the raw observation whose
// reading equals the plan's reading (label, figure and clock line), and that raw
// value is a probability. A real 0% is a figure; an owner's absence words are
// shown as they are; anything else shows the copy's words ("No recent
// probability") with no number. The two chances are separately clocked
// observations: never interpolated, normalized, complemented or put on a shared
// clock, and nothing here reads a preview, movement, clock or result. A
// challenger that does not resolve borrows no chance and no action.
//
// The gap is physical and independent of chance and settlement. Each owner
// report carries a numeric lap and seconds beside its own whole formatted
// reading; a report publication time is not a lap-crossing time and is never
// aligned to a trade time. Reports are placed on ONE affine seconds/lap
// coordinate inside the owner's explicit domain, in the owner's runs and order
// — never sorted, deduplicated, interpolated or matched to the nearest report.
// A missing, invalid or out-of-domain report breaks its run instead of being
// bridged or clamped; a lone report is a point, not a line; straight segments
// join only adjacent placed reports. Only the owner's exact highlighted report
// identity, carried once, is emphasized; nothing elects a latest point.
//
// Marks, gridlines and tick labels share one inset plot rect. Tick labels are
// measured and slid inward to stay whole — a mark never moves; a lap label with
// no room beside its neighbour is left out rather than overlapped. The plot is
// drawn only while its measured labels leave a readable plot with every seconds
// label and at least one lap label; otherwise the owner's reports are listed as
// their own readings under the owner's scale words — never a bare numeric plot
// without its axes. The plot is decorative: every report with its own label, figure and clock, both chances
// with their own clocks and the current gap are spoken whole. The host owns the
// scroll, the reader, history, Details, Back and focus; this leaf keeps no
// state. With no callback, nothing pretends to act.
//
// Host binding still owed: RACING-CHASE-NATIVE-BINDING-MAP.md.

/// One owner report of the gap behind the leader, in the owner's order.
nonisolated struct FieldChaseReport10868: Equatable {
    /// The owner's opaque report identity; compared, never read.
    let id: String
    /// The reported lap, on the horizontal axis.
    let lap: Double
    /// Seconds behind the leader; nil when the report carries no gap.
    let seconds: Double?
    /// "Lap 52": the owner's whole figure and that report's own clock and
    /// source (`.recorded("9.1 sec", "Reported Oct 11, 6:30:26 AM PT · lap report")`),
    /// or the owner's absence words.
    let reading: FieldChooserReading10868
}

nonisolated struct FieldChaseTick10868: Equatable {
    /// In the axis's own units: a lap, or seconds.
    let value: Double
    /// The owner's tick label ("L52", "10s").
    let label: String
}

/// The owner's explicit plot domain: reported laps across, seconds up.
nonisolated struct FieldChaseAxis10868: Equatable {
    let lapLower: Double
    let lapUpper: Double
    let lapTicks: [FieldChaseTick10868]
    /// Zero or more: a gap is never negative.
    let secondsLower: Double
    let secondsUpper: Double
    let secondsTicks: [FieldChaseTick10868]

    var isValid: Bool {
        lapLower.isFinite && lapUpper.isFinite && lapLower < lapUpper
            && secondsLower.isFinite && secondsUpper.isFinite && secondsLower >= 0 && secondsLower < secondsUpper
    }
}

/// The owner's physical gap story for the actual moment.
nonisolated struct FieldChaseGap10868: Equatable {
    /// The owner's change words ("5.9 seconds closer", "15 seconds behind").
    let headline: String
    /// "Reported gap · lap 52": `.recorded("9.1", "Reported Oct 11, 6:30:26 AM PT · lap report")`
    /// or the owner's absence words.
    let current: FieldChooserReading10868
    /// Owner runs in the owner's order. Runs never join each other.
    let runs: [[FieldChaseReport10868]]
    /// The exact report to emphasize; nil emphasizes none.
    let highlighted: String?
    let axis: FieldChaseAxis10868
}

/// The owner's words for this card.
nonisolated struct FieldChaseCopy10868: Equatable {
    /// "Leclerc chasing Verstappen · since lap 46"; nil draws none.
    let eyebrow: String?
    /// The unit beside the current gap figure ("sec").
    let currentUnit: String
    /// No gap story for this moment ("Gap not reported in this update").
    let gapUnavailable: String
    /// Spoken name of the plot ("Reported gap behind the leader, seconds…").
    let graphicLabel: String
    /// "Gap behind the leader · smaller is closer. Only reported laps are shown."; nil draws none.
    let caption: String?
    /// A report that cannot be placed ("Not shown on this scale").
    let pointUnavailable: String
    /// Spoken beside the highlighted report ("This report"); nil none.
    let highlightWords: String?
    /// Spoken name of the two chances.
    let chancesLabel: String
    /// Label of a pre-race chance that cannot be shown ("Pre-race win").
    let beforeLabel: String
    /// Label of a recorded chance that cannot be shown ("Recorded win").
    let recordedLabel: String
    /// A pre-race chance not tied to this card ("Not recorded").
    let beforeUnavailable: String
    /// A recorded chance not tied to this card ("No recent probability").
    let recordedUnavailable: String
    /// "Leclerc's win history" — shown only on a control that opens.
    let openLabel: String
    let openHint: String?
}

nonisolated struct FieldChaseInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    /// The exact challenger and the owner's whole name for it.
    let challenger: FieldFinishSlot10868
    /// The owner's associations of raw before and recorded observations.
    let pairs: [FieldMovementPair10868]
    /// Nil when the owner has no gap story for this moment.
    let gap: FieldChaseGap10868?
    let phase: FieldOutlookPhase10868
    let copy: FieldChaseCopy10868
    /// The challenger does not resolve ("Driver unavailable in this update").
    let unavailableWords: String
}

/// A placed report, 0...1 on both axes (y grows downward: lower is closer).
nonisolated struct FieldChasePlaced10868: Equatable {
    let id: String
    let unit: FieldChooserUnitPoint10868
}

nonisolated struct FieldChasePlacedTick10868: Equatable {
    let label: String
    /// 0...1 along its axis: from the leading edge for laps, from the top for seconds.
    let unit: Double
}

/// A placed tick with its label's measured size.
nonisolated struct FieldChaseMeasuredTick10868: Equatable {
    let unit: Double
    let size: CGSize
}

/// What the chase graphic shows, as its layout decides it.
nonisolated enum FieldChaseGraphicChoice10868: Equatable {
    /// The labelled plot, this wide.
    case plot(width: CGFloat)
    /// The owner's reports as a list.
    case list
}

/// What the plot Canvas draws.
nonisolated struct FieldChasePlotPlan10868: Equatable {
    /// The marks region, right of the seconds labels and above the lap labels.
    let plot: CGRect
    let inset: CGFloat
    /// One gridline per seconds tick.
    let gridYs: [CGFloat]
    /// One per seconds tick; nil when the label is taller than the plot.
    let secondsLabels: [CGRect?]
    /// One short mark per lap tick.
    let lapMarks: [CGFloat]
    /// One per lap tick; nil when it has no room beside its neighbour.
    let lapLabels: [CGRect?]
    /// Straight segments between adjacent placed reports of a run.
    let lines: [[CGPoint]]
    /// Every placed report, a lone one included.
    let dots: [CGRect]
    /// The highlighted report's ring; nil draws none.
    let highlight: CGRect?
}

nonisolated enum FieldChaseGeometry10868 {
    /// A report's place on the owner's domain, or none when its reading is
    /// words, or its lap or seconds are missing, not finite or outside the
    /// domain — never clamped.
    static func unit(_ report: FieldChaseReport10868, axis: FieldChaseAxis10868) -> FieldChooserUnitPoint10868? {
        guard axis.isValid, case .recorded = report.reading.value, let seconds = report.seconds,
              let x = lapUnit(report.lap, axis: axis), let y = secondsUnit(seconds, axis: axis)
        else { return nil }
        return FieldChooserUnitPoint10868(x: x, y: y)
    }

    static func lapUnit(_ lap: Double, axis: FieldChaseAxis10868) -> Double? {
        guard axis.isValid, lap.isFinite, lap >= axis.lapLower, lap <= axis.lapUpper else { return nil }
        return (lap - axis.lapLower) / (axis.lapUpper - axis.lapLower)
    }

    /// From the top: the upper bound is 0, the lower bound (closest) is 1.
    static func secondsUnit(_ seconds: Double, axis: FieldChaseAxis10868) -> Double? {
        guard axis.isValid, seconds.isFinite, seconds >= axis.secondsLower, seconds <= axis.secondsUpper else { return nil }
        return 1 - (seconds - axis.secondsLower) / (axis.secondsUpper - axis.secondsLower)
    }

    /// The owner's runs, each broken wherever a report cannot be placed. Order
    /// and identities are the owner's; nothing is sorted, joined or interpolated.
    static func runs(_ groups: [[FieldChaseReport10868]], axis: FieldChaseAxis10868) -> [[FieldChasePlaced10868]] {
        var runs: [[FieldChasePlaced10868]] = []
        for group in groups {
            var run: [FieldChasePlaced10868] = []
            for report in group {
                if let placed = unit(report, axis: axis) {
                    run.append(FieldChasePlaced10868(id: report.id, unit: placed))
                } else if !run.isEmpty {
                    runs.append(run)
                    run = []
                }
            }
            if !run.isEmpty { runs.append(run) }
        }
        return runs
    }

    /// The one plan the plot Canvas draws: the seconds labels' measured width
    /// on the leading side, the lap labels' measured height below, and marks,
    /// gridlines and lap marks on one inset rect between them. Nil for a size
    /// that cannot be drawn.
    static func plotPlan(
        size: CGSize,
        runs: [[FieldChasePlaced10868]],
        highlighted: String?,
        secondsTicks: [FieldChaseMeasuredTick10868],
        lapTicks: [FieldChaseMeasuredTick10868],
        dotDiameter: CGFloat,
        spacing: CGFloat
    ) -> FieldChasePlotPlan10868? {
        let measured = (secondsTicks + lapTicks).allSatisfy {
            $0.size.width.isFinite && $0.size.height.isFinite && $0.size.width >= 0 && $0.size.height >= 0
        }
        guard measured, size.width.isFinite, size.height.isFinite, dotDiameter.isFinite, dotDiameter > 0,
              spacing.isFinite, spacing >= 0
        else { return nil }
        let gutter = secondsTicks.isEmpty ? 0 : (secondsTicks.map(\.size.width).max() ?? 0) + spacing
        let band = lapTicks.isEmpty ? 0 : (lapTicks.map(\.size.height).max() ?? 0) + spacing
        let inset = Self.inset(dotDiameter: dotDiameter)
        let plot = CGRect(x: gutter, y: 0, width: size.width - gutter, height: size.height - band)
        guard plot.width > 2 * inset, plot.height > 2 * inset else { return nil }

        func at(_ unit: FieldChooserUnitPoint10868) -> CGPoint {
            let point = FieldChooserGeometry10868.position(unit, in: plot.size, inset: inset)
            return CGPoint(x: plot.minX + point.x, y: plot.minY + point.y)
        }
        let gridYs = secondsTicks.map { at(FieldChooserUnitPoint10868(x: 0, y: $0.unit)).y }
        let secondsLabels: [CGRect?] = zip(secondsTicks, gridYs).map { tick, y in
            FieldFinishGeometry10868.labelOrigin(markX: y, labelWidth: tick.size.height, width: size.height).map {
                CGRect(x: gutter - spacing - tick.size.width, y: $0, width: tick.size.width, height: tick.size.height)
            }
        }
        let lapMarks = lapTicks.map { at(FieldChooserUnitPoint10868(x: $0.unit, y: 1)).x }
        var lapLabels: [CGRect?] = []
        var previousEnd: CGFloat?
        for (tick, x) in zip(lapTicks, lapMarks) {
            guard let origin = FieldFinishGeometry10868.labelOrigin(markX: x - plot.minX, labelWidth: tick.size.width, width: plot.width),
                  previousEnd.map({ plot.minX + origin >= $0 + spacing }) ?? true
            else {
                lapLabels.append(nil)
                continue
            }
            let label = CGRect(x: plot.minX + origin, y: plot.maxY + spacing, width: tick.size.width, height: tick.size.height)
            lapLabels.append(label)
            previousEnd = label.maxX
        }
        let points = runs.map { $0.map { at($0.unit) } }
        let dots = points.flatMap { $0 }.map {
            CGRect(x: $0.x - dotDiameter / 2, y: $0.y - dotDiameter / 2, width: dotDiameter, height: dotDiameter)
        }
        let highlight = highlighted.flatMap { id in
            zip(runs.flatMap { $0 }, dots).first { $0.0.id == id }.map { $0.1.insetBy(dx: -2, dy: -2) }
        }
        return FieldChasePlotPlan10868(
            plot: plot, inset: inset, gridYs: gridYs, secondsLabels: secondsLabels,
            lapMarks: lapMarks, lapLabels: lapLabels,
            lines: points.filter { $0.count > 1 }, dots: dots, highlight: highlight
        )
    }

    /// Room for the highlight ring, so a report on an edge stays whole.
    static func inset(dotDiameter: CGFloat) -> CGFloat {
        dotDiameter / 2 + 3
    }

    /// A plan a reader can orient by: every seconds label and at least one lap
    /// label placed. Anything less is never drawn as a bare plot.
    static func isReadable(_ plan: FieldChasePlotPlan10868) -> Bool {
        !plan.secondsLabels.isEmpty && plan.secondsLabels.allSatisfy { $0 != nil } && plan.lapLabels.contains { $0 != nil }
    }

    /// The narrowest width at which the labelled plot is readable for these
    /// measured labels and height — each lap label fits the plot on its own,
    /// so at least the first is always placed. Nil when no width can do it (no
    /// owner ticks on an axis, or labels too tall for the height): the view then
    /// lists the reports instead.
    static func labelledPlotWidth(secondsLabels: [CGSize], lapLabels: [CGSize], height: CGFloat, dotDiameter: CGFloat, spacing: CGFloat) -> CGFloat? {
        let sizes = secondsLabels + lapLabels
        guard !secondsLabels.isEmpty, !lapLabels.isEmpty,
              sizes.allSatisfy({ $0.width.isFinite && $0.height.isFinite && $0.width >= 0 && $0.height >= 0 }),
              height.isFinite, dotDiameter.isFinite, dotDiameter > 0, spacing.isFinite, spacing >= 0
        else { return nil }
        let inset = Self.inset(dotDiameter: dotDiameter)
        let gutter = (secondsLabels.map(\.width).max() ?? 0) + spacing
        let band = (lapLabels.map(\.height).max() ?? 0) + spacing
        guard height - band > 2 * inset, (secondsLabels.map(\.height).max() ?? 0) <= height else { return nil }
        return gutter + max(2 * inset, lapLabels.map(\.width).max() ?? 0) + 1
    }

    /// Whether the labelled plot is readable at this width, or the report list
    /// shows instead.
    static func showsLabelledPlot(width: CGFloat, secondsLabels: [CGSize], lapLabels: [CGSize], height: CGFloat, dotDiameter: CGFloat, spacing: CGFloat) -> Bool {
        guard let needed = labelledPlotWidth(secondsLabels: secondsLabels, lapLabels: lapLabels, height: height, dotDiameter: dotDiameter, spacing: spacing) else { return false }
        return needed <= width
    }

    /// The choice the graphic layout makes from its measured tick labels and
    /// the width it is offered: the labelled plot where it is readable, else
    /// the report list. Offered no finite width, the plot at its narrowest
    /// readable width, else the list.
    static func graphicChoice(proposedWidth: CGFloat?, secondsLabels: [CGSize], lapLabels: [CGSize], height: CGFloat, dotDiameter: CGFloat, spacing: CGFloat) -> FieldChaseGraphicChoice10868 {
        guard let width = proposedWidth, width.isFinite else {
            return labelledPlotWidth(secondsLabels: secondsLabels, lapLabels: lapLabels, height: height, dotDiameter: dotDiameter, spacing: spacing)
                .map { .plot(width: $0) } ?? .list
        }
        return showsLabelledPlot(width: width, secondsLabels: secondsLabels, lapLabels: lapLabels, height: height, dotDiameter: dotDiameter, spacing: spacing)
            ? .plot(width: width) : .list
    }

    /// The size the graphic layout reports for its choice: the plot at its
    /// width and height, or the list at its own natural size. Always finite —
    /// a measurement that is not reads as the offered finite width, else zero.
    static func graphicSize(_ choice: FieldChaseGraphicChoice10868, proposedWidth: CGFloat?, plotHeight: CGFloat, listSize: CGSize) -> CGSize {
        func finite(_ value: CGFloat, else fallback: CGFloat) -> CGFloat {
            value.isFinite && value >= 0 ? value : fallback
        }
        let offered = proposedWidth.map { finite($0, else: 0) } ?? 0
        switch choice {
        case .plot(let width):
            return CGSize(width: finite(width, else: offered), height: finite(plotHeight, else: 0))
        case .list:
            return CGSize(width: finite(listSize.width, else: offered), height: finite(listSize.height, else: 0))
        }
    }

    /// At accessibility sizes the two chances, and the gap's label and figure,
    /// stack instead of sitting side by side.
    static func stacksReadouts(accessibilitySize: Bool) -> Bool {
        accessibilitySize
    }
}

/// The chase card's rules, resolved once per input, on the movement card's own model.
nonisolated struct FieldChaseModel10868: Equatable {
    let input: FieldChaseInput10868
    /// The movement card's resolver and endpoint tie, for the one challenger.
    let movement: FieldMovementModel10868

    init(_ input: FieldChaseInput10868) {
        self.input = input
        // Only the resolver and the endpoint tie are read: no change bar,
        // movement words, observation key or scale.
        movement = FieldMovementModel10868(FieldMovementInput10868(
            scope: input.scope,
            catalogue: input.catalogue,
            displayed: [FieldOutlookSlot10868(ref: input.challenger.ref, label: input.challenger.name, shortLabel: input.challenger.name)],
            pairs: input.pairs.map {
                FieldMovementPair10868(ref: $0.ref, before: Self.qualified($0.before), later: Self.qualified($0.later), movement: nil, observation: nil)
            },
            scale: FieldMovementScale10868(limit: 1, ticks: [], words: ""),
            phase: input.phase,
            copy: FieldMovementCopy10868(
                title: input.copy.chancesLabel,
                note: nil,
                graphicLabel: input.copy.chancesLabel,
                beforeLabel: input.copy.beforeLabel,
                laterLabel: input.copy.recordedLabel,
                endpointUnavailable: input.copy.recordedUnavailable,
                changeUnavailable: "",
                offScale: "",
                openLabel: input.copy.openLabel,
                openHint: input.copy.openHint
            ),
            unavailableWords: input.unavailableWords
        ))
    }

    /// An observation whose raw value is a probability; anything else ties nothing.
    static func qualified(_ observation: FieldMovementObservation10868?) -> FieldMovementObservation10868? {
        guard let observation, FieldOutlookGeometry10868.fraction(observation.probability, ceiling: 1) != nil else { return nil }
        return observation
    }

    var field: FieldChooserModel10868 { movement.field }

    /// During the race only: before and at the final there are no words,
    /// figures, artwork or actions.
    var isShown: Bool { input.phase == .during }

    // MARK: Challenger and chances

    var row: FieldMovementRow10868? { isShown ? movement.rows.first : nil }

    var challenger: FieldChooserOriginal10868? { row?.resolution.original }

    /// The owner's name and unavailable words when the challenger does not resolve.
    var unavailable: (name: String?, words: String)? {
        guard isShown, challenger == nil else { return nil }
        return (FieldMovementModel10868.readable(input.challenger.name), input.unavailableWords)
    }

    /// The pre-race chance then the recorded chance, each tied or in words —
    /// the plan the view lays out; none when the challenger does not resolve.
    var readouts: [FieldMovementEndpoint10868] {
        guard let row, row.resolution.original != nil, let before = row.before, let later = row.later else { return [] }
        if case .unavailable(let label, _) = before {
            return [.unavailable(label: label, words: input.copy.beforeUnavailable), later]
        }
        return [before, later]
    }

    static func label(_ endpoint: FieldMovementEndpoint10868) -> String {
        switch endpoint {
        case .reading(let reading): reading.label
        case .unavailable(let label, _): label
        }
    }

    /// A tied figure; nil when the endpoint is words.
    static func figure(_ endpoint: FieldMovementEndpoint10868) -> String? {
        guard case .reading(let reading) = endpoint, case .recorded(let text, _) = reading.value else { return nil }
        return text
    }

    /// The owner's absence words or the copy's words; nil for a figure.
    static func words(_ endpoint: FieldMovementEndpoint10868) -> String? {
        switch endpoint {
        case .reading(let reading):
            if case .missing(let words) = reading.value { return words }
            return nil
        case .unavailable(_, let words):
            return words
        }
    }

    /// A tied figure's own clock and source line.
    static func detail(_ endpoint: FieldMovementEndpoint10868) -> String? {
        guard case .reading(let reading) = endpoint else { return nil }
        return FieldOutlookModel10868.detailLine(reading)
    }

    // MARK: Gap

    var gap: FieldChaseGap10868? { isShown ? input.gap : nil }

    var eyebrow: String? { isShown ? FieldMovementModel10868.readable(input.copy.eyebrow) : nil }

    var headline: String? { FieldMovementModel10868.readable(gap?.headline) }

    var current: FieldChooserReading10868? { gap?.current }

    /// The owner's words when there is no gap story; the chances stay.
    var gapWords: String? { isShown && input.gap == nil ? input.copy.gapUnavailable : nil }

    /// Every report, in the owner's order.
    var reports: [FieldChaseReport10868] { gap?.runs.flatMap { $0 } ?? [] }

    var axis: FieldChaseAxis10868? {
        guard let axis = gap?.axis, axis.isValid else { return nil }
        return axis
    }

    /// The plot is drawn only with a valid domain and some report to show.
    var showsPlot: Bool { axis != nil && !reports.isEmpty }

    var placedRuns: [[FieldChasePlaced10868]] {
        guard let gap, let axis else { return [] }
        return FieldChaseGeometry10868.runs(gap.runs, axis: axis)
    }

    /// The owner's highlighted report, only while it is carried once and placed.
    var highlightedID: String? {
        guard let id = FieldMovementModel10868.readable(gap?.highlighted), let axis else { return nil }
        let matches = reports.filter { $0.id == id }
        guard matches.count == 1, FieldChaseGeometry10868.unit(matches[0], axis: axis) != nil else { return nil }
        return id
    }

    /// The owner's ticks inside the domain, in the owner's order.
    var lapTicks: [FieldChasePlacedTick10868] {
        guard let axis else { return [] }
        return axis.lapTicks.compactMap { tick in
            FieldChaseGeometry10868.lapUnit(tick.value, axis: axis).map { FieldChasePlacedTick10868(label: tick.label, unit: $0) }
        }
    }

    var secondsTicks: [FieldChasePlacedTick10868] {
        guard let axis else { return [] }
        return axis.secondsTicks.compactMap { tick in
            FieldChaseGeometry10868.secondsUnit(tick.value, axis: axis).map { FieldChasePlacedTick10868(label: tick.label, unit: $0) }
        }
    }

    func isHighlighted(_ report: FieldChaseReport10868) -> Bool {
        highlightedID.map { $0 == report.id } ?? false
    }

    /// The words for a recorded report that cannot be placed; a report in
    /// words is already its own words.
    func pointWords(_ report: FieldChaseReport10868) -> String? {
        guard let axis, case .recorded = report.reading.value, FieldChaseGeometry10868.unit(report, axis: axis) == nil else { return nil }
        return input.copy.pointUnavailable
    }

    // MARK: Open

    /// The exact challenger whose history opens — only with a callback.
    func openAction(canOpen: Bool) -> FieldChooserOriginalRef10868? {
        canOpen ? challenger?.ref : nil
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ ref: FieldChooserOriginalRef10868?) -> String {
        ref == nil ? "" : (input.copy.openHint ?? "")
    }

    var openSpokenLabel: String? {
        challenger.map { "\(input.copy.openLabel), \($0.name)" }
    }

    // MARK: VoiceOver

    /// Both chances with their own clocks, so the figures may be read whole.
    var chanceSummary: String {
        readouts.map(FieldMovementModel10868.spoken).joined(separator: ". ")
    }

    /// The current gap with its unit and own clock.
    var gapSummary: String? {
        guard let current else { return gapWords }
        switch current.value {
        case .recorded(let text, let detail):
            return "\(current.label): \(text) \(input.copy.currentUnit), \(detail)"
        case .missing(let words):
            return "\(current.label): \(words)"
        }
    }

    /// Every report in the owner's order with its own label, figure and clock,
    /// so the plot may stay decorative.
    var graphicSummary: String {
        let highlighted = highlightedID
        return reports.map { report in
            var parts = [FieldChooserModel10868.spoken(report.reading)]
            if report.id == highlighted, let words = FieldMovementModel10868.readable(input.copy.highlightWords) { parts.append(words) }
            if let words = pointWords(report) { parts.append(words) }
            return parts.joined(separator: ". ")
        }
        .joined(separator: "; ")
    }
}

nonisolated enum FieldChaseAccessibilityID10868 {
    static let gap = "fieldChase10868.gap"
    static let chances = "fieldChase10868.chances"
    static let graphic = "fieldChase10868.graphic"
    static let open = "fieldChase10868.open"
}

/// The labelled plot or the report list, decided from the measured tick labels
/// (hidden copies of the labels the Canvas draws) and the finite width offered,
/// through `FieldChaseGeometry10868.graphicChoice`. The chosen one is placed at
/// that width — the plot at its height, the list at its natural height — and
/// the other is proposed zero, which its zero-minimum clipped frame honours.
/// Every size it reports is finite.
struct FieldChasePlotFitLayout10868: Layout {
    var height: CGFloat
    var dotDiameter: CGFloat
    var spacing: CGFloat
    /// Subviews: the plot, the report list, then this many seconds labels,
    /// then the lap labels.
    var secondsCount: Int

    private func choice(_ width: CGFloat?, _ subviews: Subviews) -> FieldChaseGraphicChoice10868 {
        let labels = subviews.dropFirst(2).map { $0.sizeThatFits(.unspecified) }
        guard subviews.count >= 2, labels.count >= secondsCount else { return .list }
        return FieldChaseGeometry10868.graphicChoice(
            proposedWidth: width, secondsLabels: Array(labels.prefix(secondsCount)), lapLabels: Array(labels.dropFirst(secondsCount)),
            height: height, dotDiameter: dotDiameter, spacing: spacing)
    }

    private func listProposal(_ width: CGFloat?) -> ProposedViewSize {
        ProposedViewSize(width: width.flatMap { $0.isFinite ? $0 : nil }, height: nil)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let choice = choice(proposal.width, subviews)
        let list = choice == .list && subviews.count >= 2 ? subviews[1].sizeThatFits(listProposal(proposal.width)) : .zero
        return FieldChaseGeometry10868.graphicSize(choice, proposedWidth: proposal.width, plotHeight: height, listSize: list)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count >= 2 else { return }
        if choice(bounds.width, subviews) == .list {
            subviews[1].place(at: bounds.origin, anchor: .topLeading, proposal: listProposal(bounds.width))
            subviews[0].place(at: bounds.origin, anchor: .topLeading, proposal: .zero)
        } else {
            subviews[0].place(at: bounds.origin, anchor: .topLeading, proposal: ProposedViewSize(width: bounds.width, height: height))
            subviews[1].place(at: bounds.origin, anchor: .topLeading, proposal: .zero)
        }
        for probe in subviews.dropFirst(2) {
            probe.place(at: bounds.origin, anchor: .topLeading, proposal: .unspecified)
        }
    }
}

struct FieldChasePresentation10868: View {
    let input: FieldChaseInput10868
    var onOpenHistory: ((FieldChooserOriginalRef10868) -> Void)?
    private let model: FieldChaseModel10868

    init(input: FieldChaseInput10868, onOpenHistory: ((FieldChooserOriginalRef10868) -> Void)? = nil) {
        self.input = input
        self.onOpenHistory = onOpenHistory
        self.model = FieldChaseModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var gapFigureSize: CGFloat = 30
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var plotHeight: CGFloat = 170
    @ScaledMetric(relativeTo: .caption) private var dotDiameter: CGFloat = 10

    private var canOpen: Bool { onOpenHistory != nil }
    private var stacks: Bool { FieldChaseGeometry10868.stacksReadouts(accessibilitySize: typeSize.isAccessibilitySize) }

    var body: some View {
        if model.isShown {
            VStack(alignment: .leading, spacing: 12) {
                if let eyebrow = model.eyebrow {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let headline = model.headline {
                    Text(headline)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                }
                gapReadout
                chances
                if model.showsPlot {
                    gapGraphic
                    if let caption = input.copy.caption {
                        ownerWords(caption)
                    }
                }
                openControl
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    private var accent: Color { model.challenger?.accent ?? DS.blue }

    // MARK: Gap

    @ViewBuilder private var gapReadout: some View {
        if let current = model.current {
            let layout = stacks
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
                : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
            VStack(alignment: .leading, spacing: 2) {
                layout {
                    Text(current.label)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if !stacks { Spacer(minLength: 8) }
                    switch current.value {
                    case .recorded(let text, _):
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text(text)
                                .font(.system(size: gapFigureSize, weight: .semibold))
                                .monospacedDigit()
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize()
                            Text(input.copy.currentUnit)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize()
                        }
                    case .missing(let words):
                        Text(words)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if let line = FieldOutlookModel10868.detailLine(current) {
                    ownerWords(line)
                }
            }
            .padding(.bottom, 10)
            .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.gapSummary ?? "")
            .accessibilityIdentifier(FieldChaseAccessibilityID10868.gap)
        } else if let words = model.gapWords {
            ownerWords(words)
                .accessibilityIdentifier(FieldChaseAccessibilityID10868.gap)
        }
    }

    // MARK: Chances

    /// The whole challenger name, then both chances at the same figure size,
    /// side by side or stacked; unresolved, the owner's words and no figure.
    @ViewBuilder private var chances: some View {
        if let original = model.challenger {
            let layout = stacks
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
                : AnyLayout(HStackLayout(alignment: .top, spacing: 16))
            VStack(alignment: .leading, spacing: 6) {
                Text(original.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                layout {
                    ForEach(Array(model.readouts.enumerated()), id: \.offset) { _, endpoint in
                        readout(endpoint)
                    }
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(original.name)
            .accessibilityValue(model.chanceSummary)
            .accessibilityIdentifier(FieldChaseAccessibilityID10868.chances)
        } else if let unavailable = model.unavailable {
            VStack(alignment: .leading, spacing: 2) {
                if let name = unavailable.name {
                    Text(name)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(unavailable.words)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel([unavailable.name, unavailable.words].compactMap { $0 }.joined(separator: ". "))
            .accessibilityIdentifier(FieldChaseAccessibilityID10868.chances)
        }
    }

    private func readout(_ endpoint: FieldMovementEndpoint10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(FieldChaseModel10868.label(endpoint))
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let figure = FieldChaseModel10868.figure(endpoint) {
                Text(figure)
                    .font(.system(size: figureSize, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(accent)
                    .fixedSize()
            }
            if let words = FieldChaseModel10868.words(endpoint) {
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let line = FieldChaseModel10868.detail(endpoint) {
                ownerWords(line)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Plot

    /// The labelled plot while its measured labels leave it readable, else the
    /// owner's reports as a list. Both speak every report.
    private var gapGraphic: some View {
        FieldChasePlotFitLayout10868(height: plotHeight, dotDiameter: dotDiameter, spacing: 6, secondsCount: model.secondsTicks.count) {
            plot
                .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .topLeading)
                .clipped()
            reportList
                .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .topLeading)
                .clipped()
            ForEach(Array((model.secondsTicks + model.lapTicks).enumerated()), id: \.offset) { _, tick in
                Text(tick.label).font(.caption2).hidden().accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.copy.graphicLabel)
        .accessibilityValue(model.graphicSummary)
        .accessibilityIdentifier(FieldChaseAccessibilityID10868.graphic)
    }

    /// Gridlines, lap marks and measured tick labels, then the owner's runs and
    /// reports, all from the one plot plan. Decorative — the element speaks
    /// every report.
    private var plot: some View {
        let gridColor = DS.border
        let labelColor = DS.textSecondary
        let ringFill = DS.cardBg
        let tint = accent
        let runs = model.placedRuns
        let highlighted = model.highlightedID
        let secondsTicks = model.secondsTicks
        let lapTicks = model.lapTicks
        let diameter = dotDiameter
        return Canvas { context, size in
            let seconds = secondsTicks.map { context.resolve(Text($0.label).font(.caption2)) }
            let laps = lapTicks.map { context.resolve(Text($0.label).font(.caption2)) }
            let measuredSeconds = zip(secondsTicks, seconds).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1.measure(in: size)) }
            let measuredLaps = zip(lapTicks, laps).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1.measure(in: size)) }
            // The fit layout only offers a width where this plan is readable;
            // anything else draws nothing rather than marks without their axes.
            guard let plan = FieldChaseGeometry10868.plotPlan(
                size: size, runs: runs, highlighted: highlighted,
                secondsTicks: measuredSeconds, lapTicks: measuredLaps, dotDiameter: diameter, spacing: 6),
                FieldChaseGeometry10868.isReadable(plan)
            else { return }
            for y in plan.gridYs {
                var line = Path()
                line.move(to: CGPoint(x: plan.plot.minX, y: y))
                line.addLine(to: CGPoint(x: plan.plot.maxX, y: y))
                context.stroke(line, with: .color(gridColor), lineWidth: 1)
            }
            for x in plan.lapMarks {
                var mark = Path()
                mark.move(to: CGPoint(x: x, y: plan.plot.maxY - 4))
                mark.addLine(to: CGPoint(x: x, y: plan.plot.maxY))
                context.stroke(mark, with: .color(gridColor), lineWidth: 1)
            }
            for (label, rect) in zip(seconds + laps, plan.secondsLabels + plan.lapLabels) {
                guard let rect else { continue }
                var text = label
                text.shading = .color(labelColor)
                context.draw(text, in: rect)
            }
            for points in plan.lines {
                var path = Path()
                for (index, point) in points.enumerated() {
                    if index == 0 { path.move(to: point) } else { path.addLine(to: point) }
                }
                context.stroke(path, with: .color(tint), style: StrokeStyle(lineWidth: 3, lineJoin: .round))
            }
            for dot in plan.dots {
                context.fill(Path(ellipseIn: dot), with: .color(ringFill))
                context.stroke(Path(ellipseIn: dot.insetBy(dx: 1, dy: 1)), with: .color(tint), lineWidth: 2)
            }
            if let ring = plan.highlight {
                context.fill(Path(ellipseIn: ring), with: .color(ringFill))
                context.fill(Path(ellipseIn: ring.insetBy(dx: 2, dy: 2)), with: .color(tint))
            }
        }
        .frame(maxWidth: .infinity, minHeight: plotHeight, maxHeight: plotHeight)
        .accessibilityHidden(true)
    }

    /// The owner's scale words, then each report in the owner's order as its own
    /// reading — label, whole figure and clock — with the highlight and
    /// unplaced words. Nothing is formatted, sorted or dropped.
    private var reportList: some View {
        VStack(alignment: .leading, spacing: 8) {
            ownerWords(input.copy.graphicLabel)
            ForEach(Array(model.reports.enumerated()), id: \.offset) { _, report in
                let layout = stacks
                    ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
                    : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
                VStack(alignment: .leading, spacing: 2) {
                    layout {
                        Text(report.reading.label)
                            .font(.caption.weight(model.isHighlighted(report) ? .semibold : .regular))
                            .foregroundStyle(model.isHighlighted(report) ? DS.textPrimary : DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        switch report.reading.value {
                        case .recorded(let text, _):
                            Text(text)
                                .font(.headline)
                                .monospacedDigit()
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        case .missing(let words):
                            Text(words)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if let line = FieldOutlookModel10868.detailLine(report.reading) {
                        ownerWords(line)
                    }
                    if model.isHighlighted(report), let words = FieldMovementModel10868.readable(input.copy.highlightWords) {
                        ownerWords(words)
                    }
                    if let words = model.pointWords(report) {
                        ownerWords(words)
                    }
                }
                .padding(.vertical, 4)
                .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Open

    @ViewBuilder private var openControl: some View {
        if let ref = model.openAction(canOpen: canOpen), let onOpenHistory {
            Button {
                onOpenHistory(ref)
            } label: {
                HStack(spacing: 6) {
                    Text(input.copy.openLabel)
                        .fixedSize(horizontal: false, vertical: true)
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                        .accessibilityHidden(true)
                }
                .font(.footnote.weight(.semibold))
                .foregroundStyle(DS.blue)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(model.openSpokenLabel ?? input.copy.openLabel)
            .accessibilityHint(model.hint(ref))
            .accessibilityIdentifier(FieldChaseAccessibilityID10868.open)
        }
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - #10868 field expectations — "How expectations shifted"
//
// The racing-live expectations card, built on the movement card above. During
// the race a fan compares each of the owner's displayed drivers as one row: the
// whole driver name and the owner's signed movement words, then that driver's
// own pre-race and recorded win chances at the same figure size, each with its
// own label and clock, then one full-width track on ONE shared zero-based
// probability scale with a hollow mark at the pre-race chance and a filled mark
// at the recorded chance. The card exists during the race only; before the
// start and at the final there is no card at all — the final has its own finish
// story.
//
// Presentation only, from the approved `RacingLive.tsx` `Expectations` and
// `RaceChancePair` and `racingLive.css` (`.race-shifts`, `.race-shift`,
// `.race-scale`, `.race-prob-track`, `.race-chance-pair`, larger-text
// variants). The reference's driver list, baseline election, five-minute quote
// eligibility, trade cleaning, stage selection, `raceDelta` arithmetic, `pp`,
// percent and clock formatting, colour order and settlement reading are NOT
// ported. All of that arrives as owner input: the canonical catalogue, the
// displayed drivers in the owner's order, the qualified before and recorded
// observations tied to their formatted readings with the owner's movement words
// and observation keys, the explicit phase, the scale and every label and
// absence word.
//
// Identity, both readings, the movement words and the open go through
// `FieldMovementModel10868` on the chooser's own `FieldChooserModel10868` — the
// same resolver, endpoint tie, admitted change and open the movement rows use.
// A figure is shown only while the owner's ONE association for that exact
// original carries the raw observation whose reading equals the plan's reading
// (label, figure and clock line), and that raw value is a probability
// (`FieldChaseModel10868.qualified`). A real 0% is a figure; an owner's absence
// words are shown as they are; anything else shows the copy's words ("No recent
// probability") with no number. Movement words are printed only while that pair
// admits its change. A displayed slot listed twice, or one that does not
// resolve, keeps the owner's name beside the unavailable words and borrows no
// figure, mark or action; its neighbours keep theirs. Every canonical original
// stays in the catalogue, shown or not.
//
// The two chances are independently timed observations: never interpolated,
// normalized, complemented, summed, synchronized or put on a shared clock, and a
// report's publication time is never a trade time. Nothing here reads a preview
// or the original's movement, clock or result.
//
// Each mark sits at its own raw value's exact fraction of the scale (the
// outlook's `FieldOutlookGeometry10868.fraction`) on the same inset x as the
// tick marks and the axis labels (`FieldFinishGeometry10868.x`), so a genuine
// 0% or 100% is a whole mark at the edge without moving. Equal values are two
// concentric marks at the same x — the filled one inside the hollow ring with a
// gap — never displaced. A value above the ceiling draws no mark, only an edge
// arrow and the owner's off-scale words beside its own figure; a missing, untied
// or invalid value draws nothing and borrows no endpoint. A connector joins the
// two marks only while both are placed: never from zero, never toward an absent
// mark, and nothing is clamped. The track is not a history: no time path and no
// result point.
//
// One axis above the rows carries the owner's measured tick labels on the same
// inset, slid inward to stay whole; a label with no room beside one already
// placed is left out, in the owner's order, and the owner's scale words always
// stay — never a bare track. The hollow and filled marks also sit beside their
// reading labels as the key, so meanings never rest on colour. The tracks are
// decorative: each row speaks its readings with their own clocks and its
// movement and state words. The host owns the scroll, the reader, history,
// Details, Back, focus and the held selection; this leaf keeps no state. With
// no callback, nothing pretends to act.
//
// Host binding still owed: RACING-EXPECTATIONS-NATIVE-BINDING-MAP.md.

/// The owner's words for this card.
nonisolated struct FieldExpectationsCopy10868: Equatable {
    /// "Pre-race → recorded chance"; nil draws none.
    let eyebrow: String?
    /// "How expectations shifted".
    let title: String
    /// "Recorded at different times".
    let context: String
    /// "Hollow = pre-race · solid = recorded"; nil draws none.
    let key: String?
    /// Spoken name of the rows.
    let graphicLabel: String
    /// Label of a pre-race chance that cannot be shown ("Pre-race win").
    let beforeLabel: String
    /// Label of a recorded chance that cannot be shown ("Recorded win").
    let recordedLabel: String
    /// A pre-race chance not tied to this card ("Not recorded").
    let beforeUnavailable: String
    /// A recorded chance not tied to this card ("No recent probability").
    let recordedUnavailable: String
    /// A chance above the ceiling ("Above this scale").
    let offScale: String
    /// "Win history" — shown only on a row that opens.
    let openLabel: String
    let openHint: String?
}

nonisolated struct FieldExpectationsInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    /// The rows, in the owner's order. Never sorted, filtered, capped or deduplicated here.
    let displayed: [FieldFinishSlot10868]
    /// The owner's associations of raw before and recorded observations, with
    /// its movement words and opaque observation keys.
    let pairs: [FieldMovementPair10868]
    /// The owner's one scale for every track (0–100%: ceiling 1).
    let scale: FieldOutlookScale10868
    let phase: FieldOutlookPhase10868
    let copy: FieldExpectationsCopy10868
    /// A slot that does not resolve ("Driver unavailable in this update").
    let unavailableWords: String
}

nonisolated struct FieldExpectationsRow10868: Equatable {
    let slot: FieldFinishSlot10868
    /// The movement card's row for the same slot: resolution, both endpoints
    /// and the admitted change.
    let movement: FieldMovementRow10868
    /// Where each shown raw chance sits on the shared scale.
    let before: FieldOutlookChance10868
    let recorded: FieldOutlookChance10868

    var resolution: FieldChooserResolution10868 { movement.resolution }
}

/// What one track Canvas draws inside its own rect.
nonisolated struct FieldExpectationsTrackPlan10868: Equatable {
    let centerY: CGFloat
    /// The zero and ceiling ends of the scale line.
    let zeroX: CGFloat
    let ceilingX: CGFloat
    /// Zero and every owner tick on the scale.
    let tickXs: [CGFloat]
    /// Between the two placed marks; nil unless both are placed apart.
    let connector: CGRect?
    /// The hollow pre-race mark; nil draws none.
    let before: CGRect?
    /// The filled recorded mark; nil draws none.
    let recorded: CGRect?
}

nonisolated enum FieldExpectationsGeometry10868 {
    /// Half a hollow mark and a hair, so a mark at zero or at the ceiling stays whole.
    static func inset(markDiameter: CGFloat) -> CGFloat {
        markDiameter / 2 + 1
    }

    /// Half the hollow mark: inside its 2 pt ring with a gap, so equal values
    /// stay two distinct concentric marks.
    static func recordedDiameter(markDiameter: CGFloat) -> CGFloat {
        markDiameter / 2
    }

    /// The one drawing plan every track Canvas uses: both marks centred on one
    /// line at their own exact x, and a connector only between two placed
    /// marks. Nil for a size that cannot be drawn; no mark for a missing,
    /// off-scale or invalid fraction — never clamped.
    static func trackPlan(
        before: Double?,
        recorded: Double?,
        ticks: [Double],
        in size: CGSize,
        markDiameter: CGFloat,
        lineWidth: CGFloat
    ) -> FieldExpectationsTrackPlan10868? {
        let inset = Self.inset(markDiameter: markDiameter)
        guard size.height.isFinite, markDiameter.isFinite, markDiameter > 0, size.height >= markDiameter,
              lineWidth.isFinite, lineWidth > 0,
              let zero = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let ceiling = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset)
        else { return nil }
        let centerY = size.height / 2
        func x(_ fraction: Double?) -> CGFloat? {
            fraction.flatMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) }
        }
        func mark(_ x: CGFloat?, diameter: CGFloat) -> CGRect? {
            x.map { CGRect(x: $0 - diameter / 2, y: centerY - diameter / 2, width: diameter, height: diameter) }
        }
        let beforeX = x(before)
        let recordedX = x(recorded)
        var connector: CGRect?
        if let start = beforeX, let end = recordedX, start != end {
            connector = CGRect(x: min(start, end), y: centerY - lineWidth / 2, width: abs(end - start), height: lineWidth)
        }
        return FieldExpectationsTrackPlan10868(
            centerY: centerY,
            zeroX: zero,
            ceilingX: ceiling,
            tickXs: ([0] + ticks).compactMap { x($0) },
            connector: connector,
            before: mark(beforeX, diameter: markDiameter),
            recorded: mark(recordedX, diameter: recordedDiameter(markDiameter: markDiameter))
        )
    }

    /// The owner's measured tick labels on the tracks' own inset x: each
    /// centred on its mark while that keeps it inside the width, else slid
    /// inward just enough. One with no room beside a label already placed is
    /// left out, in the owner's order. A mark never moves.
    static func axisLabels(_ ticks: [FieldChaseMeasuredTick10868], width: CGFloat, inset: CGFloat, spacing: CGFloat) -> [CGRect?] {
        var placed: [CGRect] = []
        return ticks.map { tick in
            guard spacing.isFinite, spacing >= 0, tick.size.height.isFinite, tick.size.height >= 0,
                  let markX = FieldFinishGeometry10868.x(of: tick.unit, width: width, inset: inset),
                  let origin = FieldFinishGeometry10868.labelOrigin(markX: markX, labelWidth: tick.size.width, width: width)
            else { return nil }
            let label = CGRect(x: origin, y: 0, width: tick.size.width, height: tick.size.height)
            guard placed.allSatisfy({ label.minX >= $0.maxX + spacing || label.maxX + spacing <= $0.minX }) else { return nil }
            placed.append(label)
            return label
        }
    }

    /// The axis row's width: the offered finite width, else every measured
    /// label side by side within the insets. Always finite.
    static func axisWidth(proposed: CGFloat?, labels: [CGSize], inset: CGFloat, spacing: CGFloat) -> CGFloat {
        if let proposed, proposed.isFinite, proposed >= 0 { return proposed }
        let widths = labels.map(\.width).filter { $0.isFinite && $0 >= 0 }
        let total = widths.reduce(0, +) + spacing * CGFloat(max(0, widths.count - 1)) + 2 * inset
        return total.isFinite && total >= 0 ? total : 0
    }

    /// As tall as the tallest placed label; zero when none is placed.
    static func axisHeight(_ labels: [CGRect?]) -> CGFloat {
        labels.compactMap { $0?.height }.filter { $0.isFinite && $0 >= 0 }.max() ?? 0
    }
}

/// The expectations card's rules, resolved once per input, on the movement card's own model.
nonisolated struct FieldExpectationsModel10868: Equatable {
    let input: FieldExpectationsInput10868
    /// The movement card's resolver, endpoint tie, admitted change and open.
    let movement: FieldMovementModel10868

    init(_ input: FieldExpectationsInput10868) {
        self.input = input
        // The movement rules on a ±100 pp limit, where every change between two
        // tied probabilities is admitted; no signed bar or tick of it is drawn.
        movement = FieldMovementModel10868(FieldMovementInput10868(
            scope: input.scope,
            catalogue: input.catalogue,
            displayed: input.displayed.map { FieldOutlookSlot10868(ref: $0.ref, label: $0.name, shortLabel: $0.name) },
            pairs: input.pairs.map {
                FieldMovementPair10868(
                    ref: $0.ref,
                    before: FieldChaseModel10868.qualified($0.before),
                    later: FieldChaseModel10868.qualified($0.later),
                    movement: $0.movement,
                    observation: $0.observation
                )
            },
            scale: FieldMovementScale10868(limit: 1, ticks: [], words: ""),
            phase: input.phase,
            copy: FieldMovementCopy10868(
                title: input.copy.title,
                note: nil,
                graphicLabel: input.copy.graphicLabel,
                beforeLabel: input.copy.beforeLabel,
                laterLabel: input.copy.recordedLabel,
                endpointUnavailable: input.copy.recordedUnavailable,
                changeUnavailable: "",
                offScale: "",
                openLabel: input.copy.openLabel,
                openHint: input.copy.openHint
            ),
            unavailableWords: input.unavailableWords
        ))
    }

    var field: FieldChooserModel10868 { movement.field }

    /// During the race only: before and at the final there are no rows, words,
    /// artwork or actions.
    var isShown: Bool { input.phase == .during }

    var eyebrow: String? { isShown ? FieldMovementModel10868.readable(input.copy.eyebrow) : nil }

    var context: String? { isShown ? FieldMovementModel10868.readable(input.copy.context) : nil }

    var key: String? { isShown ? FieldMovementModel10868.readable(input.copy.key) : nil }

    // MARK: Rows

    var rows: [FieldExpectationsRow10868] {
        guard isShown else { return [] }
        return zip(input.displayed, movement.rows).map { slot, row in
            let pair = row.resolution.original.flatMap { movement.pair(for: $0.ref) }
            return FieldExpectationsRow10868(
                slot: slot,
                movement: row,
                before: mark(row.before, tie: pair?.before),
                recorded: mark(row.later, tie: pair?.later)
            )
        }
    }

    /// A shown figure's own raw chance on the shared scale: placed, above the
    /// ceiling, or — words, untied or no valid scale — nothing.
    func mark(_ endpoint: FieldMovementEndpoint10868?, tie: FieldMovementObservation10868?) -> FieldOutlookChance10868 {
        guard case .reading(let reading)? = endpoint, case .recorded = reading.value,
              let tie, tie.reading == reading, input.scale.isValid,
              tie.probability.isFinite, tie.probability >= 0, tie.probability <= 1
        else { return .unavailable }
        guard let fraction = FieldOutlookGeometry10868.fraction(tie.probability, ceiling: input.scale.ceiling) else {
            return .offScale
        }
        return .value(probability: tie.probability, fraction: fraction)
    }

    /// The pre-race chance then the recorded chance, each tied or in words —
    /// the plan the view lays out; none when the slot does not resolve.
    func readouts(_ row: FieldExpectationsRow10868) -> [FieldMovementEndpoint10868] {
        guard row.resolution.original != nil, let before = row.movement.before, let later = row.movement.later else { return [] }
        if case .unavailable(let label, _) = before {
            return [.unavailable(label: label, words: input.copy.beforeUnavailable), later]
        }
        return [before, later]
    }

    /// The owner's movement words, only while the pair admits its change.
    func movementWords(_ row: FieldExpectationsRow10868) -> String? {
        movement.movementWords(row.movement)
    }

    /// The unavailable words for a slot that does not resolve; the owner's
    /// off-scale words beside a figure whose mark is above the ceiling.
    func stateWords(_ row: FieldExpectationsRow10868) -> String? {
        guard row.resolution.original != nil else { return input.unavailableWords }
        return row.before == .offScale || row.recorded == .offScale ? input.copy.offScale : nil
    }

    // MARK: Scale

    /// Tracks are drawn only beside the owner's explicit scale: a valid scale
    /// and its readable words. Never a bare track.
    var showsTracks: Bool {
        isShown && input.scale.isValid && FieldMovementModel10868.readable(input.scale.words) != nil
    }

    /// A row draws its track while one of its chances is placed or above the ceiling.
    func showsTrack(_ row: FieldExpectationsRow10868) -> Bool {
        guard showsTracks, row.resolution.original != nil else { return false }
        return row.before != .unavailable || row.recorded != .unavailable
    }

    /// The owner's ticks that sit on the scale, in the owner's order.
    var ticks: [FieldOutlookPlacedTick10868] {
        guard showsTracks else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldOutlookGeometry10868.fraction(tick.probability, ceiling: input.scale.ceiling)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    // MARK: Open

    /// The exact original, and its recorded observation key while that figure
    /// is shown — only with a callback.
    func openAction(_ row: FieldExpectationsRow10868, canOpen: Bool) -> FieldMovementOpen10868? {
        movement.openAction(row.movement, canOpen: canOpen)
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ opening: FieldMovementOpen10868?) -> String {
        movement.hint(opening)
    }

    // MARK: VoiceOver

    /// A row's whole reading in the owner's words, so its track may stay
    /// decorative: both chances with their own clocks, movement and state words.
    func rowSummary(_ row: FieldExpectationsRow10868) -> String {
        guard row.resolution.original != nil else {
            return [row.slot.name, input.unavailableWords]
                .filter { FieldMovementModel10868.readable($0) != nil }
                .joined(separator: ". ")
        }
        var parts = readouts(row).map(FieldMovementModel10868.spoken)
        parts += [movementWords(row), stateWords(row)].compactMap { $0 }
        return parts.joined(separator: ". ")
    }
}

nonisolated enum FieldExpectationsAccessibilityID10868 {
    static let rows = "fieldExpectations10868.rows"
    static let scale = "fieldExpectations10868.scale"
    static func row(_ outcomeID: String) -> String { "fieldExpectations10868.row.\(outcomeID)" }
}

/// The owner's tick labels on the tracks' own inset x, placed by
/// `FieldExpectationsGeometry10868.axisLabels` from their measured sizes. A
/// label left out is proposed zero, which its zero-minimum clipped frame
/// honours. Every size it reports is finite.
struct FieldExpectationsAxisLayout10868: Layout {
    /// One per label subview, in the owner's order: 0...1 along the scale.
    var units: [Double]
    var inset: CGFloat
    var spacing: CGFloat

    private func labels(_ width: CGFloat, _ subviews: Subviews) -> [CGRect?] {
        let measured = zip(units, subviews).map { FieldChaseMeasuredTick10868(unit: $0, size: $1.sizeThatFits(.unspecified)) }
        return FieldExpectationsGeometry10868.axisLabels(measured, width: width, inset: inset, spacing: spacing)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = FieldExpectationsGeometry10868.axisWidth(
            proposed: proposal.width, labels: subviews.map { $0.sizeThatFits(.unspecified) }, inset: inset, spacing: spacing)
        return CGSize(width: width, height: FieldExpectationsGeometry10868.axisHeight(labels(width, subviews)))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let placed = labels(bounds.width, subviews)
        for (index, subview) in subviews.enumerated() {
            if index < placed.count, let label = placed[index] {
                subview.place(at: CGPoint(x: bounds.minX + label.minX, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(label.size))
            } else {
                subview.place(at: bounds.origin, anchor: .topLeading, proposal: .zero)
            }
        }
    }
}

struct FieldExpectationsPresentation10868: View {
    let input: FieldExpectationsInput10868
    var onOpen: ((FieldMovementOpen10868) -> Void)?
    private let model: FieldExpectationsModel10868

    init(input: FieldExpectationsInput10868, onOpen: ((FieldMovementOpen10868) -> Void)? = nil) {
        self.input = input
        self.onOpen = onOpen
        self.model = FieldExpectationsModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 20
    @ScaledMetric(relativeTo: .caption) private var markDiameter: CGFloat = 14

    private var canOpen: Bool { onOpen != nil }
    private var stacks: Bool { FieldChaseGeometry10868.stacksReadouts(accessibilitySize: typeSize.isAccessibilitySize) }
    private var inset: CGFloat { FieldExpectationsGeometry10868.inset(markDiameter: markDiameter) }

    var body: some View {
        if model.isShown {
            VStack(alignment: .leading, spacing: 10) {
                if let eyebrow = model.eyebrow {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(input.copy.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let context = model.context {
                    ownerWords(context)
                }
                if let key = model.key {
                    ownerWords(key)
                }
                let rows = model.rows
                if model.showsTracks, rows.contains(where: model.showsTrack) {
                    scaleHeader
                }
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        driver(row)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(input.copy.graphicLabel)
                .accessibilityIdentifier(FieldExpectationsAccessibilityID10868.rows)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Scale

    /// The owner's scale words, then its measured tick labels on the inset the
    /// tracks use. The words always stay; a crowded label is left out.
    private var scaleHeader: some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 4) {
            Text(input.scale.words)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if !ticks.isEmpty {
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
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.scale.words)
        .accessibilityIdentifier(FieldExpectationsAccessibilityID10868.scale)
    }

    // MARK: Rows

    @ViewBuilder private func driver(_ row: FieldExpectationsRow10868) -> some View {
        let id = FieldExpectationsAccessibilityID10868.row(row.slot.ref.outcomeID)
        if let original = row.resolution.original {
            let accent = original.accent ?? DS.blue
            let opening = model.openAction(row, canOpen: canOpen)
            control(opening) {
                VStack(alignment: .leading, spacing: 8) {
                    heading(original, row: row)
                    readouts(row, accent: accent)
                    if model.showsTrack(row) {
                        track(row, accent: accent)
                    }
                    if let words = model.stateWords(row) {
                        ownerWords(words)
                    }
                    if opening != nil {
                        HStack(spacing: 6) {
                            Text(input.copy.openLabel)
                                .fixedSize(horizontal: false, vertical: true)
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.semibold))
                                .accessibilityHidden(true)
                        }
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(DS.blue)
                    }
                }
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.rowSummary(row))
            .accessibilityHint(model.hint(opening))
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if let name = FieldMovementModel10868.readable(row.slot.name) {
                    Text(name)
                        .font(.body)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.unavailableWords)
            }
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.rowSummary(row))
            .accessibilityIdentifier(id)
        }
    }

    /// The whole name and the owner's movement words; stacked at accessibility sizes.
    private func heading(_ original: FieldChooserOriginal10868, row: FieldExpectationsRow10868) -> some View {
        let layout = stacks
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        return layout {
            Text(original.name)
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if !stacks { Spacer(minLength: 8) }
            if let words = model.movementWords(row) {
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Both chances at the same figure size, each with its mark key, label and
    /// own clock; side by side, or stacked at accessibility sizes.
    private func readouts(_ row: FieldExpectationsRow10868, accent: Color) -> some View {
        let layout = stacks
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 16))
        return layout {
            ForEach(Array(model.readouts(row).enumerated()), id: \.offset) { index, endpoint in
                readout(endpoint, filled: index == 1, accent: accent)
            }
        }
    }

    private func readout(_ endpoint: FieldMovementEndpoint10868, filled: Bool, accent: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .center, spacing: 6) {
                markKey(filled: filled, accent: accent)
                Text(FieldChaseModel10868.label(endpoint))
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let figure = FieldChaseModel10868.figure(endpoint) {
                Text(figure)
                    .font(.system(size: figureSize, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(accent)
                    .fixedSize()
            }
            if let words = FieldChaseModel10868.words(endpoint) {
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let line = FieldChaseModel10868.detail(endpoint) {
                ownerWords(line)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The hollow or filled mark exactly as the track draws it. Decorative.
    private func markKey(filled: Bool, accent: Color) -> some View {
        let diameter = markDiameter
        let ringFill = DS.cardBg
        return Canvas { context, size in
            let ring = CGRect(x: (size.width - diameter) / 2, y: (size.height - diameter) / 2, width: diameter, height: diameter)
            if filled {
                let inner = FieldExpectationsGeometry10868.recordedDiameter(markDiameter: diameter)
                context.fill(Path(ellipseIn: ring.insetBy(dx: (diameter - inner) / 2, dy: (diameter - inner) / 2)), with: .color(accent))
            } else {
                context.fill(Path(ellipseIn: ring), with: .color(ringFill))
                context.stroke(Path(ellipseIn: ring.insetBy(dx: 1, dy: 1)), with: .color(accent), lineWidth: 2)
            }
        }
        .frame(width: diameter, height: diameter)
        .accessibilityHidden(true)
    }

    // MARK: Track

    /// The scale line, zero and the owner's ticks, the connector between two
    /// placed marks, the hollow mark and the filled mark on top — all from the
    /// shared plan. Above the ceiling, an edge arrow and no mark.
    private func track(_ row: FieldExpectationsRow10868, accent: Color) -> some View {
        let lineColor = DS.border
        let ringFill = DS.cardBg
        let diameter = markDiameter
        let ticks = model.ticks.map(\.fraction)
        let before = row.before.fraction
        let recorded = row.recorded.fraction
        let offScale = row.before == .offScale || row.recorded == .offScale
        return Canvas { context, size in
            guard let plan = FieldExpectationsGeometry10868.trackPlan(
                before: before, recorded: recorded, ticks: ticks, in: size, markDiameter: diameter, lineWidth: 3)
            else { return }
            var line = Path()
            line.move(to: CGPoint(x: plan.zeroX, y: plan.centerY))
            line.addLine(to: CGPoint(x: plan.ceilingX, y: plan.centerY))
            context.stroke(line, with: .color(lineColor), lineWidth: 2)
            for x in plan.tickXs {
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: plan.centerY - 5))
                tick.addLine(to: CGPoint(x: x, y: plan.centerY + 5))
                context.stroke(tick, with: .color(lineColor), lineWidth: 1)
            }
            if let connector = plan.connector {
                context.fill(Path(connector), with: .color(accent))
            }
            if let mark = plan.before {
                context.fill(Path(ellipseIn: mark), with: .color(ringFill))
                context.stroke(Path(ellipseIn: mark.insetBy(dx: 1, dy: 1)), with: .color(accent), lineWidth: 2)
            }
            if let mark = plan.recorded {
                context.fill(Path(ellipseIn: mark), with: .color(accent))
            }
        }
        .frame(maxWidth: .infinity, minHeight: trackHeight, maxHeight: trackHeight)
        .overlay(alignment: .trailing) {
            if offScale {
                Image(systemName: "arrow.right.to.line")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(DS.textSecondary)
                    .accessibilityHidden(true)
            }
        }
        .accessibilityHidden(true)
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func control<Content: View>(_ opening: FieldMovementOpen10868?, @ViewBuilder content: () -> Content) -> some View {
        if let opening, let onOpen {
            Button {
                onOpen(opening)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - #10868 field phase headline — "Singapore Grand Prix"
//
// The racing-live headline, built on the movement and finish cards above. In
// every phase a fan sees, for each of the owner's displayed drivers in the
// owner's order, that driver's name and probability-first figures as the
// headline's main value: before the start ONE labelled pre-race win chance;
// during the race that pre-race chance and the recorded win chance at the same
// figure size; after the race the pre-race chance kept as a prominent reminder
// beside the separately reported actual finish. Above them, one compact owner
// heading — the phase eyebrow, the event title unless the host already shows it,
// and a genuine trailing About control; below them, the owner's race state.
//
// Presentation only, from the approved `RacingLive.tsx` `Chances`, `.race-title`,
// `.race-head-grid` and `.race-state` as mounted in the page and the reader, and
// `racingLive.css` (`.race-title`, `.race-chances`, `.race-state`, the wide
// `.race-head-grid` and the larger-text variants). The reference's driver list,
// baseline and before-window election, five-minute quote eligibility, trade
// cleaning, stage selection, surname split, ordinal suffixes,
// `probabilityLabel`, reader clock, gap formatting, colour order and settlement
// reading are NOT ported. All of that
// arrives as owner input: the canonical catalogue, the displayed drivers with
// their whole names and optional compact labels, the qualified before and
// recorded observations tied to their formatted readings, the physical finish
// associations, the explicit phase, the state and every label and absence word.
//
// Identity and both chances go through `FieldMovementModel10868` on the
// chooser's own `FieldChooserModel10868` — the same resolver and endpoint tie the
// movement, chase and expectations cards use: a figure is shown only while the
// owner's ONE association for that exact original carries the raw observation
// whose reading equals the plan's reading (label, figure and clock line), and
// that raw value is a probability (`FieldChaseModel10868.qualified`). A real 0%
// is a figure; an owner's absence words are shown as they are; anything else
// shows the copy's words with no number. The finish goes through
// `FieldFinishModel10868.finish(for:)` — the same one-association rule the
// horse-racing finish card uses. A displayed slot listed twice, or one that
// does not resolve, keeps the owner's name beside the unavailable words and
// borrows no figure, finish or action; its neighbours keep theirs. Every
// canonical original stays in the catalogue, shown or not.
//
// The phase is the owner's explicit input, never inferred from a clock, a lap
// or a winner. Before the start only the before reading is read — a later
// reading riding on the plan or the association is never shown. During the race
// the recorded reading appears beside it. At the final the later reading and the
// association's later observation are not read at all — a settled 0 or 1, a
// closing quote or a contract result never becomes a headline figure — and the
// finish is the owner's physical ordinal, never read from a probability, the
// list order or the original's result. The chances are independently timed
// observations: never interpolated, normalized, complemented, summed or put on a
// shared clock; a report's publication time is never a trade time, and no
// projected finish or score is invented.
//
// The race state is the owner's independently admitted copy — figure, unit and
// two lines ("Lap 52 / 62 · Verstappen leads · Leclerc +9.1s"; "62 laps · Race
// complete · Final classification · Oct 11, 2026") — spoken whole with the
// report's own clock; nothing is computed from it. The owner's reported progress
// is drawn during and after the race only: scheduled laps are not progress.
//
// Peer columns at an equal share of the width while every whole figure fits its
// share; otherwise — and at accessibility sizes — one full-width row per driver
// (`FieldHeadlineGeometry10868.arrangement`). Within a driver the two figures
// sit side by side where they fit whole, else stacked; the whole name is shown
// where it fits on one line, else the owner's compact label, and the whole name
// is always spoken. Nothing shrinks, truncates, caps or scrolls. No source or
// clock paragraph sits under the headline: each driver speaks its readings with
// their own clocks, and the owner's About carries the rest. The host owns the
// scroll, the chart, the reader, history, Details, Back, focus and the held
// selection; this leaf keeps no state. With no callback, nothing pretends to act.
//
// Beside each name sits the same identity key the approved chart draws for that
// driver (`HistoryTeamKey`: Verstappen circle, Leclerc diamond, Hamilton
// square), so a fan can follow a driver from the headline into the chart when
// the colours are hard to tell apart. The shape is the owner's, carried on the
// slot with its original — never derived here from a name, a rank or a position
// in the list — drawn in the original's own accent, hollow before the start and
// filled after it, with the reference's proportions in one shared frame
// (`FieldHeadlineGeometry10868.keyPlan`). It is decorative: the name is spoken.
//
// Host binding still owed: FIELD-PHASE-HEADLINE-NATIVE-BINDING-MAP.md.

/// The owner's identity key for one displayed driver, matching that driver's
/// marks on the chart.
nonisolated enum FieldHeadlineKeyShape10868: Equatable, CaseIterable {
    case circle
    case diamond
    case square
}

/// One displayed driver, in the owner's order.
nonisolated struct FieldHeadlineSlot10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's whole name, kept beside the unavailable words when the slot
    /// does not resolve.
    let name: String
    /// The owner's compact visible label ("Verstappen"), shown only where the
    /// whole name does not fit on one line; nil always shows the whole name.
    /// Never derived here.
    let compactName: String?
    /// The owner's key shape for this driver's chart marks; it travels with the
    /// slot, so a reordered or changed cohort keeps each driver's own shape.
    /// Never derived here. Omitted, the ordinary circle.
    var keyShape: FieldHeadlineKeyShape10868 = .circle
}

/// The owner's reported progress, in its own units ("52" of "62" laps).
nonisolated struct FieldHeadlineProgress10868: Equatable {
    let completed: Double
    let total: Double

    var isValid: Bool {
        completed.isFinite && total.isFinite && total > 0 && completed >= 0 && completed <= total
    }
}

/// The owner's independently admitted race state for the actual moment.
nonisolated struct FieldHeadlineState10868: Equatable {
    /// The main state figure ("Lap 52", "62 laps").
    let figure: String
    /// Smaller, beside the figure ("/ 62"); nil draws none.
    let unit: String?
    /// The first state line ("Verstappen leads", "Scheduled start", "Race complete"); nil draws none.
    let caption: String?
    /// The emphasized line under it ("Leclerc +9.1s", "Oct 11, 5:00 AM PT",
    /// "Final classification · Oct 11, 2026"); nil draws none.
    let detail: String?
    /// The whole state in words with the report's own clock.
    let spoken: String
    /// Drawn during and after the race only; nil draws none.
    let progress: FieldHeadlineProgress10868?
}

/// The owner's words for the headline in the actual phase.
nonisolated struct FieldHeadlineCopy10868: Equatable {
    /// "Formula 1 · Recorded probabilities"; nil draws none.
    let eyebrow: String?
    /// "Singapore Grand Prix"; nil when the host already shows the event title.
    let title: String?
    /// Spoken name of the drivers ("Pre-race and recorded win chances").
    let graphicLabel: String
    /// Label of a pre-race chance that cannot be shown ("Pre-race win").
    let beforeLabel: String
    /// Label of a recorded chance that cannot be shown ("Recorded win").
    let recordedLabel: String
    /// A pre-race chance not tied to this headline ("Not recorded").
    let beforeUnavailable: String
    /// A recorded chance not tied to this headline ("No recent probability").
    let recordedUnavailable: String
    /// Label of a finish that cannot be shown ("Actual finish").
    let finishLabel: String
    /// A finish not tied to this original ("Finish not reported").
    let finishUnavailable: String
    /// No displayed drivers ("No drivers in this update").
    let empty: String
    /// "About this race" — the info control's spoken name; shown only with a callback.
    let aboutLabel: String
    let aboutHint: String?
    let openHint: String?
}

nonisolated struct FieldHeadlineInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    /// The drivers, in the owner's order. Never sorted, filtered, capped or deduplicated here.
    let displayed: [FieldHeadlineSlot10868]
    /// The owner's associations of raw before and recorded observations, with
    /// its opaque observation keys. Movement words are never read.
    let pairs: [FieldMovementPair10868]
    /// The owner's physical finish associations; read at the final only.
    let finishes: [FieldFinishPlace10868]
    /// Nil draws no state.
    let state: FieldHeadlineState10868?
    let phase: FieldOutlookPhase10868
    let copy: FieldHeadlineCopy10868
    /// A slot that does not resolve ("Driver unavailable in this update").
    let unavailableWords: String
}

nonisolated struct FieldHeadlineCompetitor10868: Equatable {
    let slot: FieldHeadlineSlot10868
    /// The movement card's row for the same slot: resolution and both endpoints.
    let movement: FieldMovementRow10868
    /// What the phase shows, in order: the pre-race chance; then the recorded
    /// chance during the race, or the reported finish at the final. Empty when
    /// the slot does not resolve.
    let metrics: [FieldMovementEndpoint10868]

    var resolution: FieldChooserResolution10868 { movement.resolution }
}

nonisolated enum FieldHeadlineArrangement10868: Equatable {
    /// Peer columns at an equal share of the width.
    case columns
    /// One full-width row per driver.
    case rows
}

/// What one identity key Canvas draws inside its own frame.
nonisolated struct FieldHeadlineKeyPlan10868: Equatable {
    let shape: FieldHeadlineKeyShape10868
    /// Before the start: the card colour under the accent outline. After it: the accent.
    let hollow: Bool
    /// The shape's whole extent, centred in the frame.
    let bounds: CGRect
    /// Where the hollow outline's line runs: inset so its outer edge is the
    /// shape's own edge and never leaves the frame. Nil when filled.
    let outline: CGRect?
    let lineWidth: CGFloat

    /// The shape inscribed in a rect: the circle in it, the square filling it,
    /// or the diamond on its four edge midpoints.
    static func path(_ shape: FieldHeadlineKeyShape10868, in rect: CGRect) -> Path {
        switch shape {
        case .circle:
            return Path(ellipseIn: rect)
        case .square:
            return Path(rect)
        case .diamond:
            var path = Path()
            path.move(to: CGPoint(x: rect.midX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
            path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.midY))
            path.closeSubpath()
            return path
        }
    }

    /// The whole shape: the accent when filled, the card colour when hollow.
    var fill: Path { Self.path(shape, in: bounds) }

    /// The accent outline of a hollow key; none when filled.
    var stroke: Path? { outline.map { Self.path(shape, in: $0) } }
}

nonisolated enum FieldHeadlineGeometry10868 {
    /// Each shape's extent as a multiple of the key diameter — the reference
    /// `HistoryTeamMark` proportions: a circle of radius r, a diamond reaching
    /// 1.2 r from its centre, a square of side 1.6 r.
    static func keyExtent(_ shape: FieldHeadlineKeyShape10868) -> CGFloat {
        switch shape {
        case .circle: 1
        case .diamond: 1.2
        case .square: 0.8
        }
    }

    /// The one square frame every key is drawn in, whatever its shape, so the
    /// names beside them line up; none for a diameter that cannot be drawn.
    static func keyFrameSide(diameter: CGFloat) -> CGFloat? {
        guard diameter.isFinite, diameter > 0 else { return nil }
        return diameter * (FieldHeadlineKeyShape10868.allCases.map(keyExtent).max() ?? 1)
    }

    /// The one drawing plan the key Canvas uses: the owner's shape centred in
    /// the frame at its reference extent, hollow or filled as the phase says.
    /// Nil for a diameter, line or frame that cannot hold the whole shape, or a
    /// line that would leave a hollow key no inside.
    static func keyPlan(
        _ shape: FieldHeadlineKeyShape10868,
        hollow: Bool,
        in size: CGSize,
        diameter: CGFloat,
        lineWidth: CGFloat
    ) -> FieldHeadlineKeyPlan10868? {
        guard let side = keyFrameSide(diameter: diameter), lineWidth.isFinite, lineWidth > 0,
              size.width.isFinite, size.height.isFinite, size.width >= side, size.height >= side
        else { return nil }
        let extent = diameter * keyExtent(shape)
        let bounds = CGRect(x: (size.width - extent) / 2, y: (size.height - extent) / 2, width: extent, height: extent)
        var outline: CGRect?
        if hollow {
            // A diamond's edges run at 45°, so its corners move √2 times as far as the line's half-width.
            let inset = shape == .diamond ? lineWidth / 2 * 2.squareRoot() : lineWidth / 2
            let inner = bounds.insetBy(dx: inset, dy: inset)
            guard inner.width > lineWidth else { return nil }
            outline = inner
        }
        return FieldHeadlineKeyPlan10868(shape: shape, hollow: hollow, bounds: bounds, outline: outline, lineWidth: lineWidth)
    }

    /// Each peer column's equal share of the width; none when it cannot be
    /// computed or leaves nothing.
    static func columnWidth(available: CGFloat, count: Int, spacing: CGFloat) -> CGFloat? {
        guard count > 0, available.isFinite, available >= 0, spacing.isFinite, spacing >= 0 else { return nil }
        let share = (available - spacing * CGFloat(count - 1)) / CGFloat(count)
        return share > 0 ? share : nil
    }

    /// Peer columns while every whole figure fits its column's share; else one
    /// row per driver. Accessibility sizes go straight to rows. No figure
    /// shrinks; an unmeasurable figure is never assumed to fit.
    static func arrangement(available: CGFloat, count: Int, figureWidths: [CGFloat], spacing: CGFloat, accessibilitySize: Bool) -> FieldHeadlineArrangement10868 {
        guard !accessibilitySize, figureWidths.allSatisfy({ $0.isFinite && $0 >= 0 }),
              let share = columnWidth(available: available, count: count, spacing: spacing)
        else { return .rows }
        return (figureWidths.max() ?? 0) <= share ? .columns : .rows
    }

    /// The width the headline is laid out at: the offered finite width, else
    /// every column at the widest figure. Always finite.
    static func width(proposed: CGFloat?, count: Int, figureWidths: [CGFloat], spacing: CGFloat) -> CGFloat {
        if let proposed, proposed.isFinite, proposed >= 0 { return proposed }
        let widest = figureWidths.filter { $0.isFinite && $0 >= 0 }.max() ?? 0
        let total = widest * CGFloat(max(0, count)) + spacing * CGFloat(max(0, count - 1))
        return total.isFinite && total >= 0 ? total : 0
    }
}

/// The headline's rules, resolved once per input, on the movement and finish cards' own models.
nonisolated struct FieldHeadlineModel10868: Equatable {
    let input: FieldHeadlineInput10868
    /// The movement card's resolver and endpoint tie.
    let movement: FieldMovementModel10868
    /// The finish card's one-association rule for a physical finish.
    let finish: FieldFinishModel10868

    init(_ input: FieldHeadlineInput10868) {
        self.input = input
        // Only the resolver and the endpoint tie are read: no change bar,
        // movement words or scale. The movement rules' own before-day gate is
        // its card's, not this headline's, so they are read as during; this
        // headline's phase rule decides what is shown.
        movement = FieldMovementModel10868(FieldMovementInput10868(
            scope: input.scope,
            catalogue: input.catalogue,
            displayed: input.displayed.map { FieldOutlookSlot10868(ref: $0.ref, label: $0.name, shortLabel: $0.name) },
            pairs: input.pairs.map {
                FieldMovementPair10868(
                    ref: $0.ref,
                    before: FieldChaseModel10868.qualified($0.before),
                    later: FieldChaseModel10868.qualified($0.later),
                    movement: nil,
                    observation: $0.observation
                )
            },
            scale: FieldMovementScale10868(limit: 1, ticks: [], words: ""),
            phase: .during,
            copy: FieldMovementCopy10868(
                title: input.copy.graphicLabel,
                note: nil,
                graphicLabel: input.copy.graphicLabel,
                beforeLabel: input.copy.beforeLabel,
                laterLabel: input.copy.recordedLabel,
                endpointUnavailable: input.copy.recordedUnavailable,
                changeUnavailable: "",
                offScale: "",
                openLabel: "",
                openHint: input.copy.openHint
            ),
            unavailableWords: input.unavailableWords
        ))
        // Only `finish(for:)` is read: no rows, strip, scale or selection.
        finish = FieldFinishModel10868(FieldFinishInput10868(
            scope: input.scope,
            catalogue: input.catalogue,
            selected: nil,
            displayed: [],
            finishes: input.finishes,
            chances: [],
            scale: FieldOutlookScale10868(ceiling: 1, ticks: [], words: ""),
            phase: .final,
            copy: FieldFinishCopy10868(
                title: "", context: nil, scaleLabel: "", graphicLabel: "",
                finishLabel: input.copy.finishLabel, finishUnit: "",
                finishUnavailable: input.copy.finishUnavailable,
                chanceUnavailable: "", offScale: "", outsideDisplayed: "", empty: "",
                count: nil, openPrompt: nil, openHint: nil
            ),
            unavailableWords: input.unavailableWords
        ))
    }

    var field: FieldChooserModel10868 { movement.field }

    // MARK: Heading

    var eyebrow: String? { FieldMovementModel10868.readable(input.copy.eyebrow) }

    var title: String? { FieldMovementModel10868.readable(input.copy.title) }

    /// The About control's spoken name — only with a callback and readable words.
    func aboutLabel(canAbout: Bool) -> String? {
        canAbout ? FieldMovementModel10868.readable(input.copy.aboutLabel) : nil
    }

    /// The owner's About hint, only on a control that acts.
    func aboutHint(canAbout: Bool) -> String {
        aboutLabel(canAbout: canAbout) == nil ? "" : (input.copy.aboutHint ?? "")
    }

    // MARK: Competitors

    var competitors: [FieldHeadlineCompetitor10868] {
        zip(input.displayed, movement.rows).map { slot, row in
            FieldHeadlineCompetitor10868(slot: slot, movement: row, metrics: metrics(row))
        }
    }

    /// The phase's figures, each tied or in words; none when the slot does not resolve.
    func metrics(_ row: FieldMovementRow10868) -> [FieldMovementEndpoint10868] {
        guard let original = row.resolution.original, let before = row.before, let later = row.later else { return [] }
        var earlier = before
        if case .unavailable(let label, _) = before {
            earlier = .unavailable(label: label, words: input.copy.beforeUnavailable)
        }
        switch input.phase {
        case .before: return [earlier]
        case .during: return [earlier, later]
        case .final: return [earlier, finish.finish(for: original.ref)]
        }
    }

    /// The owner's compact label where it differs from the whole name; the view
    /// shows it only where the whole name does not fit on one line.
    func compactName(_ competitor: FieldHeadlineCompetitor10868) -> String? {
        guard let original = competitor.resolution.original,
              let compact = FieldMovementModel10868.readable(competitor.slot.compactName),
              compact != original.name
        else { return nil }
        return compact
    }

    /// Every whole figure the drivers show, in order: what the arrangement measures.
    var figures: [String] {
        competitors.flatMap { $0.metrics.compactMap(FieldChaseModel10868.figure) }
    }

    // MARK: Identity key

    /// The owner's key shape for this driver, exactly as its slot carries it.
    func keyShape(_ competitor: FieldHeadlineCompetitor10868) -> FieldHeadlineKeyShape10868 {
        competitor.slot.keyShape
    }

    /// Hollow before the start, filled during and after the race — the chart's own convention.
    var keyIsHollow: Bool { input.phase == .before }

    // MARK: State

    var state: FieldHeadlineState10868? { input.state }

    /// The owner's reported progress, during and after the race only, while valid.
    var progress: FieldHeadlineProgress10868? {
        guard input.phase != .before, let progress = input.state?.progress, progress.isValid else { return nil }
        return progress
    }

    /// The owner's whole spoken state; with none readable, its visible lines.
    var stateSummary: String? {
        guard let state = input.state else { return nil }
        if let spoken = FieldMovementModel10868.readable(state.spoken) { return spoken }
        let parts = [state.figure, state.unit, state.caption, state.detail].compactMap(FieldMovementModel10868.readable)
        return parts.isEmpty ? nil : parts.joined(separator: ". ")
    }

    // MARK: Open

    /// The exact original — with its recorded observation key while that figure
    /// is shown during the race — only with a callback. Before the start and at
    /// the final no later observation is handed back.
    func openAction(_ competitor: FieldHeadlineCompetitor10868, canOpen: Bool) -> FieldMovementOpen10868? {
        guard canOpen, let original = competitor.resolution.original else { return nil }
        guard input.phase == .during else { return FieldMovementOpen10868(ref: original.ref, observation: nil) }
        return movement.openAction(competitor.movement, canOpen: true)
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ opening: FieldMovementOpen10868?) -> String {
        opening == nil ? "" : (input.copy.openHint ?? "")
    }

    // MARK: VoiceOver

    /// A driver's whole reading in the owner's words: every figure with its own
    /// label and clock or source line, or the name and unavailable words.
    func competitorSummary(_ competitor: FieldHeadlineCompetitor10868) -> String {
        guard competitor.resolution.original != nil else {
            return [competitor.slot.name, input.unavailableWords]
                .filter { FieldMovementModel10868.readable($0) != nil }
                .joined(separator: ". ")
        }
        return competitor.metrics.map(FieldMovementModel10868.spoken).joined(separator: ". ")
    }
}

nonisolated enum FieldHeadlineAccessibilityID10868 {
    static let heading = "fieldHeadline10868.heading"
    static let about = "fieldHeadline10868.about"
    static let competitors = "fieldHeadline10868.competitors"
    static let state = "fieldHeadline10868.state"
    static func competitor(_ outcomeID: String) -> String { "fieldHeadline10868.competitor.\(outcomeID)" }
}

/// The drivers as peer columns or full-width rows, decided by
/// `FieldHeadlineGeometry10868.arrangement` from the measured whole figures
/// (hidden copies of the figures the drivers draw) and the finite width it is
/// laid out at. Every size it reports is finite.
struct FieldHeadlineCompetitorsLayout10868: Layout {
    /// Subviews: this many drivers, then the figure probes.
    var count: Int
    var spacing: CGFloat
    var rowSpacing: CGFloat
    var accessibilitySize: Bool

    private func plan(_ proposed: CGFloat?, _ subviews: Subviews) -> (width: CGFloat, arrangement: FieldHeadlineArrangement10868) {
        let competitors = min(count, subviews.count)
        let figures = subviews.dropFirst(competitors).map { $0.sizeThatFits(.unspecified).width }
        let width = FieldHeadlineGeometry10868.width(proposed: proposed, count: competitors, figureWidths: figures, spacing: spacing)
        return (width, FieldHeadlineGeometry10868.arrangement(
            available: width, count: competitors, figureWidths: figures, spacing: spacing, accessibilitySize: accessibilitySize))
    }

    private func finite(_ value: CGFloat) -> CGFloat {
        value.isFinite && value >= 0 ? value : 0
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let competitors = subviews.prefix(min(count, subviews.count))
        guard !competitors.isEmpty else { return .zero }
        let (width, arrangement) = plan(proposal.width, subviews)
        switch arrangement {
        case .columns:
            let share = FieldHeadlineGeometry10868.columnWidth(available: width, count: competitors.count, spacing: spacing) ?? 0
            let height = competitors.map { finite($0.sizeThatFits(ProposedViewSize(width: share, height: nil)).height) }.max() ?? 0
            return CGSize(width: width, height: height)
        case .rows:
            let heights = competitors.map { finite($0.sizeThatFits(ProposedViewSize(width: width, height: nil)).height) }
            return CGSize(width: width, height: heights.reduce(0, +) + rowSpacing * CGFloat(heights.count - 1))
        }
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let count = min(self.count, subviews.count)
        guard count > 0 else { return }
        let arrangement = plan(bounds.width, subviews).arrangement
        switch arrangement {
        case .columns:
            let share = FieldHeadlineGeometry10868.columnWidth(available: bounds.width, count: count, spacing: spacing) ?? 0
            for index in 0..<count {
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(index) * (share + spacing), y: bounds.minY),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: share, height: nil)
                )
            }
        case .rows:
            var y = bounds.minY
            for index in 0..<count {
                let height = finite(subviews[index].sizeThatFits(ProposedViewSize(width: bounds.width, height: nil)).height)
                subviews[index].place(at: CGPoint(x: bounds.minX, y: y), anchor: .topLeading, proposal: ProposedViewSize(width: bounds.width, height: height))
                y += height + rowSpacing
            }
        }
        for probe in subviews.dropFirst(count) {
            probe.place(at: bounds.origin, anchor: .topLeading, proposal: .unspecified)
        }
    }
}

struct FieldPhaseHeadlinePresentation10868: View {
    let input: FieldHeadlineInput10868
    var onAbout: (() -> Void)?
    var onOpen: ((FieldMovementOpen10868) -> Void)?
    private let model: FieldHeadlineModel10868

    init(input: FieldHeadlineInput10868, onAbout: (() -> Void)? = nil, onOpen: ((FieldMovementOpen10868) -> Void)? = nil) {
        self.input = input
        self.onAbout = onAbout
        self.onOpen = onOpen
        self.model = FieldHeadlineModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 27
    @ScaledMetric(relativeTo: .caption) private var keyDiameter: CGFloat = 10

    private var canAbout: Bool { onAbout != nil }
    private var canOpen: Bool { onOpen != nil }
    private var stacks: Bool { FieldChaseGeometry10868.stacksReadouts(accessibilitySize: typeSize.isAccessibilitySize) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading
            let competitors = model.competitors
            if competitors.isEmpty {
                ownerWords(input.copy.empty)
            } else {
                FieldHeadlineCompetitorsLayout10868(count: competitors.count, spacing: 12, rowSpacing: 14, accessibilitySize: typeSize.isAccessibilitySize) {
                    ForEach(Array(competitors.enumerated()), id: \.offset) { _, competitor in
                        self.competitor(competitor)
                    }
                    ForEach(Array(model.figures.enumerated()), id: \.offset) { _, figure in
                        figureText(figure, accent: DS.textPrimary).hidden().accessibilityHidden(true)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(input.copy.graphicLabel)
                .accessibilityIdentifier(FieldHeadlineAccessibilityID10868.competitors)
            }
            stateRegion
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Heading

    /// The owner's phase eyebrow and title, and the About control at the trailing edge.
    @ViewBuilder private var heading: some View {
        let about = model.aboutLabel(canAbout: canAbout)
        if model.eyebrow != nil || model.title != nil || about != nil {
            HStack(alignment: .top, spacing: 10) {
                if model.eyebrow != nil || model.title != nil {
                    titles
                } else {
                    Spacer(minLength: 0)
                }
                if let about, let onAbout {
                    Button(action: onAbout) {
                        Image(systemName: "info.circle")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .accessibilityLabel(about)
                    .accessibilityHint(model.aboutHint(canAbout: canAbout))
                    .accessibilityIdentifier(FieldHeadlineAccessibilityID10868.about)
                }
            }
        }
    }

    /// The owner's phase eyebrow and title, read as one heading.
    private var titles: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = model.eyebrow {
                Text(eyebrow)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let title = model.title {
                Text(title)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(FieldHeadlineAccessibilityID10868.heading)
    }

    // MARK: Competitors

    @ViewBuilder private func competitor(_ competitor: FieldHeadlineCompetitor10868) -> some View {
        let id = FieldHeadlineAccessibilityID10868.competitor(competitor.slot.ref.outcomeID)
        if let original = competitor.resolution.original {
            let accent = original.accent ?? DS.textPrimary
            let opening = model.openAction(competitor, canOpen: canOpen)
            control(opening) {
                VStack(alignment: .leading, spacing: 8) {
                    name(original, competitor: competitor)
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 16) { metrics(competitor, accent: accent) }
                        VStack(alignment: .leading, spacing: 10) { metrics(competitor, accent: accent) }
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.competitorSummary(competitor))
            .accessibilityHint(model.hint(opening))
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if let name = FieldMovementModel10868.readable(competitor.slot.name) {
                    Text(name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.unavailableWords)
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.competitorSummary(competitor))
            .accessibilityIdentifier(id)
        }
    }

    /// The chart's own identity key in the owner's shape — hollow before the
    /// start, filled after it — and the whole name on one line where it fits,
    /// else the owner's compact label. Both wrap whole rather than truncate.
    private func name(_ original: FieldChooserOriginal10868, competitor: FieldHeadlineCompetitor10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            if let accent = original.accent {
                identityKey(model.keyShape(competitor), accent: accent, hollow: model.keyIsHollow)
            }
            if let compact = model.compactName(competitor) {
                ViewThatFits(in: .horizontal) {
                    nameText(original.name).fixedSize()
                    nameText(compact).fixedSize(horizontal: false, vertical: true)
                }
            } else {
                nameText(original.name).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func nameText(_ words: String) -> some View {
        Text(words)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DS.textPrimary)
    }

    private func identityKey(_ shape: FieldHeadlineKeyShape10868, accent: Color, hollow: Bool) -> some View {
        let diameter = keyDiameter
        let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter) ?? 0
        let ringFill = DS.cardBg
        return Canvas { context, size in
            guard let plan = FieldHeadlineGeometry10868.keyPlan(shape, hollow: hollow, in: size, diameter: diameter, lineWidth: 2) else { return }
            if let stroke = plan.stroke {
                context.fill(plan.fill, with: .color(ringFill))
                context.stroke(stroke, with: .color(accent), lineWidth: plan.lineWidth)
            } else {
                context.fill(plan.fill, with: .color(accent))
            }
        }
        .frame(width: side, height: side)
        .accessibilityHidden(true)
    }

    /// Each figure at the same size under its own label; words in its place
    /// when it cannot be shown.
    @ViewBuilder private func metrics(_ competitor: FieldHeadlineCompetitor10868, accent: Color) -> some View {
        ForEach(Array(competitor.metrics.enumerated()), id: \.offset) { _, endpoint in
            VStack(alignment: .leading, spacing: 2) {
                Text(FieldChaseModel10868.label(endpoint))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let figure = FieldChaseModel10868.figure(endpoint) {
                    figureText(figure, accent: accent)
                }
                if let words = FieldChaseModel10868.words(endpoint) {
                    Text(words)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func figureText(_ figure: String, accent: Color) -> some View {
        Text(figure)
            .font(.system(size: figureSize, weight: .semibold))
            .monospacedDigit()
            .foregroundStyle(accent)
            .fixedSize()
    }

    // MARK: State

    /// The owner's state figure and lines, side by side or stacked at
    /// accessibility sizes, then the reported progress. Spoken whole.
    @ViewBuilder private var stateRegion: some View {
        if let state = model.state {
            let layout = stacks
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                : AnyLayout(HStackLayout(alignment: .center, spacing: 18))
            VStack(alignment: .leading, spacing: 12) {
                layout {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        if let figure = FieldMovementModel10868.readable(state.figure) {
                            Text(figure)
                                .font(.system(size: figureSize, weight: .semibold))
                                .monospacedDigit()
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let unit = FieldMovementModel10868.readable(state.unit) {
                            Text(unit)
                                .font(.callout)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if !stacks { Spacer(minLength: 8) }
                    VStack(alignment: stacks ? .leading : .trailing, spacing: 2) {
                        if let caption = FieldMovementModel10868.readable(state.caption) {
                            Text(caption)
                                .font(.footnote)
                                .foregroundStyle(DS.textSecondary)
                                .multilineTextAlignment(stacks ? .leading : .trailing)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let detail = FieldMovementModel10868.readable(state.detail) {
                            Text(detail)
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .multilineTextAlignment(stacks ? .leading : .trailing)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                if let progress = model.progress {
                    ProgressView(value: progress.completed, total: progress.total)
                        .tint(DS.blue)
                        .accessibilityHidden(true)
                }
            }
            .padding(.top, 14)
            .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.stateSummary ?? "")
            .accessibilityIdentifier(FieldHeadlineAccessibilityID10868.state)
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
    private func control<Content: View>(_ opening: FieldMovementOpen10868?, @ViewBuilder content: () -> Content) -> some View {
        if let opening, let onOpen {
            Button {
                onOpen(opening)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - #10868 field win/podium comparison
// Two independent earlier market chances, not two outcomes of one partition.
// The host admits pairs, cohort/order/window, selection, observations and every
// word. No athlete matching, ranking, abbreviation, clock/freshness/settlement
// policy or formatter lives here. The original catalogue remains intact.

nonisolated struct FieldPodiumPair10868: Equatable {
    let id: String
    let name: String
    let win: FieldChooserOriginalRef10868
    let podium: FieldChooserOriginalRef10868
}

nonisolated struct FieldPodiumSlot10868: Equatable {
    let pairID: String
    let name: String
    /// Owner label only; the whole name is always spoken.
    let compactName: String?
}

nonisolated struct FieldPodiumCopy10868: Equatable {
    let title: String
    let explanation: String
    let beforeContext: String
    let duringContext: String
    let finalContext: String
    let winLabel: String
    let podiumLabel: String
    let beforeLabel: String
    let pairUnavailable: String
    let chanceUnavailable: String
    let noSelection: String
    let outsideWindow: String
    let finishLabel: String
    let finishUnavailable: String
    let resultLabel: String
    let resultUnknown: String
    let previousLabel: String
    let nextLabel: String
    let chooseHint: String?
    let originalHint: String?
    let aboutLabel: String
    let aboutHint: String?
}

nonisolated struct FieldPodiumInput10868: Equatable {
    let scope: String
    let catalogue: [FieldChooserOriginal10868]
    /// The full owner-admitted roster; never paired, sorted or capped here.
    let pairs: [FieldPodiumPair10868]
    /// A finite owner window; no implicit five-row limit.
    let displayed: [FieldPodiumSlot10868]
    let selectedID: String?
    /// Owner targets through the full roster, not just the plotted window.
    let previousID: String?
    let nextID: String?
    let chances: [FieldOutlookBeforeChance10868]
    /// Physical classification tied to each winner original, independent of grades.
    let finishes: [FieldFinishPlace10868]
    /// This comparison uses the full 0...1 axis, with owner words and ticks.
    let scale: FieldOutlookScale10868
    let phase: FieldOutlookPhase10868
    let winTint: Color
    let podiumTint: Color
    let copy: FieldPodiumCopy10868
}

nonisolated struct FieldPodiumEndpoint10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let original: FieldChooserOriginal10868?
    let chance: FieldOutlookChance10868
    let reading: FieldMovementEndpoint10868
}

nonisolated struct FieldPodiumRow10868: Equatable {
    let slot: FieldPodiumSlot10868
    let pair: FieldPodiumPair10868?
    let win: FieldPodiumEndpoint10868?
    let podium: FieldPodiumEndpoint10868?
}

nonisolated struct FieldPodiumPlotPlan10868: Equatable {
    let win: CGPoint?
    let podium: CGPoint?
    let connector: CGRect?
}

nonisolated enum FieldPodiumGeometry10868 {
    /// Missing endpoints draw nothing; a connector exists only between two
    /// actual positions. Equal values remain at exactly the same coordinate.
    static func plan(win: Double?, podium: Double?, size: CGSize,
                     inset: CGFloat, diameter: CGFloat) -> FieldPodiumPlotPlan10868? {
        guard size.width.isFinite, size.height.isFinite, diameter.isFinite, diameter > 0,
              inset.isFinite, inset >= diameter / 2, size.width > 2 * inset,
              size.height >= diameter * 1.2 else { return nil }
        func position(_ fraction: Double?) -> CGPoint? {
            fraction.flatMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) }
                .map { CGPoint(x: $0, y: size.height / 2) }
        }
        let a = position(win), b = position(podium)
        let line: CGRect?
        if let a, let b {
            line = CGRect(x: min(a.x, b.x), y: a.y - 0.5, width: abs(a.x - b.x), height: 1)
        } else { line = nil }
        return FieldPodiumPlotPlan10868(win: a, podium: b, connector: line)
    }
}

nonisolated struct FieldPodiumModel10868: Equatable {
    let input: FieldPodiumInput10868
    let outlook: FieldOutlookModel10868
    let finish: FieldFinishModel10868

    init(_ input: FieldPodiumInput10868) {
        self.input = input
        // Qualify each original's BEFORE reading on the existing full-probability
        // contract. A malformed visual scale never turns a valid quote into zero.
        let fullScale = FieldOutlookScale10868(ceiling: 1, ticks: input.scale.ticks, words: input.scale.words)
        outlook = FieldOutlookModel10868(FieldOutlookInput10868(
            scope: input.scope, catalogue: input.catalogue, selected: nil,
            displayed: [], traversal: [], chances: input.chances, scale: fullScale,
            phase: .before,
            copy: FieldOutlookCopy10868(title: input.copy.title, note: nil, graphicLabel: input.scale.words,
                missingChance: input.copy.chanceUnavailable, offScale: input.copy.chanceUnavailable,
                outsideDisplayed: input.copy.outsideWindow, previousLabel: input.copy.previousLabel,
                nextLabel: input.copy.nextLabel, details: input.copy.aboutLabel,
                detailsHint: input.copy.aboutHint, resultUnknown: input.copy.resultUnknown),
            unavailableWords: input.copy.pairUnavailable, chooseHint: input.copy.chooseHint))
        finish = FieldFinishModel10868(FieldFinishInput10868(
            scope: input.scope, catalogue: input.catalogue, selected: nil, displayed: [],
            finishes: input.finishes, chances: [], scale: fullScale, phase: .final,
            copy: FieldFinishCopy10868(title: "", context: nil, scaleLabel: "", graphicLabel: "",
                finishLabel: input.copy.finishLabel, finishUnit: "", finishUnavailable: input.copy.finishUnavailable,
                chanceUnavailable: "", offScale: "", outsideDisplayed: "", empty: "", count: nil,
                openPrompt: nil, openHint: nil), unavailableWords: input.copy.pairUnavailable))
    }

    func pair(_ id: String?) -> FieldPodiumPair10868? {
        guard let id, FieldMovementModel10868.readable(id) != nil else { return nil }
        let matches = input.pairs.filter { $0.id == id }
        guard matches.count == 1, let pair = matches.first, pair.win != pair.podium else { return nil }
        return pair
    }

    func endpoint(_ ref: FieldChooserOriginalRef10868, label: String) -> FieldPodiumEndpoint10868 {
        let original = outlook.field.resolve(ref).original
        let chance = original.map(outlook.chance) ?? .unavailable
        let shown: FieldMovementEndpoint10868
        if let original {
            let reading = FieldOutlookModel10868.beforeReading(original.plan)
            switch reading.value {
            case .missing:
                shown = .reading(reading)
            case .recorded:
                if case .value = chance { shown = .reading(reading) }
                else { shown = .unavailable(label: label, words: input.copy.chanceUnavailable) }
            }
        } else { shown = .unavailable(label: label, words: input.copy.chanceUnavailable) }
        return FieldPodiumEndpoint10868(ref: ref, original: original, chance: chance, reading: shown)
    }

    var rows: [FieldPodiumRow10868] {
        input.displayed.map { slot in
            // A repeated window reference is ambiguous, not another canonical pair.
            let unique = input.displayed.filter { $0.pairID == slot.pairID }.count == 1
            let resolved = unique ? pair(slot.pairID) : nil
            return row(slot, pair: resolved)
        }
    }

    private func row(_ slot: FieldPodiumSlot10868, pair: FieldPodiumPair10868?) -> FieldPodiumRow10868 {
        FieldPodiumRow10868(slot: slot, pair: pair,
            win: pair.map { endpoint($0.win, label: input.copy.winLabel) },
            podium: pair.map { endpoint($0.podium, label: input.copy.podiumLabel) })
    }

    var selected: FieldPodiumRow10868? {
        guard let pair = pair(input.selectedID) else { return nil }
        return row(FieldPodiumSlot10868(pairID: pair.id, name: pair.name, compactName: nil), pair: pair)
    }

    var selectionOutsideWindow: Bool {
        selected != nil && !input.displayed.contains { $0.pairID == input.selectedID }
    }

    var canDraw: Bool {
        input.scale.ceiling == 1 && FieldMovementModel10868.readable(input.scale.words) != nil
            && input.scale.ticks.filter { $0.probability == 0 && FieldMovementModel10868.readable($0.label) != nil }.count == 1
            && input.scale.ticks.filter { $0.probability == 1 && FieldMovementModel10868.readable($0.label) != nil }.count == 1
    }

    /// Place the two required endpoint labels first; optional middle labels
    /// may be omitted by the shared measured-axis layout at large text sizes.
    var ticks: [FieldOutlookPlacedTick10868] {
        guard canDraw else { return [] }
        let all = outlook.ticks
        return all.filter { $0.fraction == 0 } + all.filter { $0.fraction == 1 }
            + all.filter { $0.fraction != 0 && $0.fraction != 1 }
    }

    var context: String {
        switch input.phase {
        case .before: input.copy.beforeContext
        case .during: input.copy.duringContext
        case .final: input.copy.finalContext
        }
    }

    func chooseID(_ id: String?, canChoose: Bool) -> String? {
        guard canChoose, let pair = pair(id), pair.id != input.selectedID,
              outlook.field.resolve(pair.win).original != nil || outlook.field.resolve(pair.podium).original != nil
        else { return nil }
        return pair.id
    }

    func rowChoice(_ row: FieldPodiumRow10868, canChoose: Bool) -> String? {
        guard row.pair != nil else { return nil }
        return chooseID(row.slot.pairID, canChoose: canChoose)
    }

    func originalAction(_ endpoint: FieldPodiumEndpoint10868?, canOpen: Bool) -> FieldChooserOriginalRef10868? {
        canOpen ? endpoint?.original?.ref : nil
    }

    var selectedFinish: FieldMovementEndpoint10868? {
        guard input.phase == .final, selected != nil else { return nil }
        guard let winner = selected?.win?.original else {
            return .unavailable(label: input.copy.finishLabel, words: input.copy.finishUnavailable)
        }
        return finish.finish(for: winner.ref)
    }

    func result(_ endpoint: FieldPodiumEndpoint10868?) -> FieldChooserResult10868? {
        guard input.phase == .final, endpoint != nil else { return nil }
        if let result = endpoint?.original?.result, FieldMovementModel10868.readable(result.words) != nil { return result }
        return FieldChooserResult10868(title: input.copy.resultLabel, words: input.copy.resultUnknown)
    }

    func summary(_ row: FieldPodiumRow10868) -> String {
        guard let pair = row.pair, let win = row.win, let podium = row.podium else {
            return "\(row.slot.name). \(input.copy.pairUnavailable)"
        }
        return [pair.name, input.copy.beforeLabel,
                "\(input.copy.winLabel): \(FieldMovementModel10868.spoken(win.reading))",
                "\(input.copy.podiumLabel): \(FieldMovementModel10868.spoken(podium.reading))"].joined(separator: ". ")
    }
}

/// The approved compact comparison: named rows and two hollow market marks on
/// one axis, then the selected driver's two equally prominent own figures.
/// The host controls selection/window/reader/Details/Back; this view holds no state.
struct FieldWinPodiumPresentation10868: View {
    let input: FieldPodiumInput10868
    var onChoosePair: ((String) -> Void)?
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)?
    var onAbout: (() -> Void)?
    private let model: FieldPodiumModel10868
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 26
    @ScaledMetric(relativeTo: .caption) private var markDiameter: CGFloat = 10
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 18

    init(input: FieldPodiumInput10868, onChoosePair: ((String) -> Void)? = nil,
         onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil, onAbout: (() -> Void)? = nil) {
        self.input = input; self.onChoosePair = onChoosePair
        self.onOpenOriginal = onOpenOriginal; self.onAbout = onAbout
        model = FieldPodiumModel10868(input)
    }

    private var inset: CGFloat { markDiameter * 0.6 + 2 }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Text(input.copy.title).font(.headline).fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading).accessibilityAddTraits(.isHeader)
                if let onAbout, FieldMovementModel10868.readable(input.copy.aboutLabel) != nil {
                    Button(action: onAbout) { Image(systemName: "info.circle").frame(minWidth: 44, minHeight: 44) }
                        .accessibilityLabel(input.copy.aboutLabel).accessibilityHint(input.copy.aboutHint ?? "")
                }
            }
            Text(input.copy.explanation).font(.subheadline).foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            key
            Text(input.scale.words).font(.caption).foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if model.canDraw {
                if typeSize.isAccessibilitySize { stackedRows }
                else {
                    ViewThatFits(in: .horizontal) { gridRows; stackedRows }
                }
            } else { readableRows }
            selection
        }
        .foregroundStyle(DS.textPrimary).frame(maxWidth: .infinity, alignment: .leading).buttonStyle(.plain)
    }

    private var key: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 18))
        return layout {
            HStack(spacing: 6) { glyph(.circle, tint: input.winTint); Text(input.copy.winLabel) }
            HStack(spacing: 6) { glyph(.square, tint: input.podiumTint); Text(input.copy.podiumLabel) }
        }.font(.caption).fixedSize(horizontal: false, vertical: true)
    }

    private var gridRows: some View {
        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
            ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                GridRow { name(row, compact: true); track(row).frame(minWidth: 144) }
            }
            GridRow { Color.clear.gridCellUnsizedAxes([.horizontal, .vertical]); axis }
        }
    }

    private var stackedRows: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                VStack(alignment: .leading, spacing: 2) { name(row, compact: false); track(row) }
            }
            axis
        }
    }

    /// If a trustworthy labelled scale cannot be drawn, keep every admitted
    /// row's two readings accessible and readable without making up positions.
    private var readableRows: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(model.rows.enumerated()), id: \.offset) { _, row in
                VStack(alignment: .leading, spacing: 4) {
                    name(row, compact: false)
                    rowReadings(row)
                }
            }
        }
    }

    private func rowReadings(_ row: FieldPodiumRow10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(input.copy.winLabel): \(row.win.map { FieldChaseModel10868.figure($0.reading) ?? FieldChaseModel10868.words($0.reading) ?? input.copy.chanceUnavailable } ?? input.copy.chanceUnavailable)")
            Text("\(input.copy.podiumLabel): \(row.podium.map { FieldChaseModel10868.figure($0.reading) ?? FieldChaseModel10868.words($0.reading) ?? input.copy.chanceUnavailable } ?? input.copy.chanceUnavailable)")
        }.font(.subheadline).fixedSize(horizontal: false, vertical: true)
    }

    private func name(_ row: FieldPodiumRow10868, compact: Bool) -> some View {
        let action = model.rowChoice(row, canChoose: onChoosePair != nil)
        let text = compact ? (FieldMovementModel10868.readable(row.slot.compactName) ?? row.slot.name) : row.slot.name
        return choose(action) {
            Text(text).font(.subheadline.weight(row.slot.pairID == input.selectedID ? .semibold : .regular))
                .fixedSize(horizontal: compact, vertical: true).frame(minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(row.pair?.name ?? row.slot.name).accessibilityValue(model.summary(row))
        .accessibilityHint(action == nil ? "" : (input.copy.chooseHint ?? ""))
        .accessibilityAddTraits(row.slot.pairID == input.selectedID ? .isSelected : [])
    }

    private var axis: some View {
        FieldExpectationsAxisLayout10868(units: model.ticks.map(\.fraction), inset: inset, spacing: 6) {
            ForEach(Array(model.ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.label).font(.caption).foregroundStyle(DS.textSecondary).fixedSize()
                    .frame(minWidth: 0, minHeight: 0).clipped()
            }
        }.accessibilityHidden(true)
    }

    private func track(_ row: FieldPodiumRow10868) -> some View {
        let diameter = markDiameter, inner = inset
        return choose(model.rowChoice(row, canChoose: onChoosePair != nil)) {
          ViewThatFits(in: .horizontal) {
            Canvas { context, size in
            guard let plan = FieldPodiumGeometry10868.plan(win: row.win?.chance.fraction,
                podium: row.podium?.chance.fraction, size: size, inset: inner, diameter: diameter) else { return }
            for tick in model.ticks {
                if let x = FieldFinishGeometry10868.x(of: tick.fraction, width: size.width, inset: inner) {
                    var line = Path(); line.move(to: CGPoint(x: x, y: 0)); line.addLine(to: CGPoint(x: x, y: size.height))
                    context.stroke(line, with: .color(DS.border), lineWidth: 0.5)
                }
            }
            if let connector = plan.connector { context.fill(Path(connector), with: .color(DS.textSecondary.opacity(0.5))) }
            draw(.circle, at: plan.win, tint: input.winTint, diameter: diameter, context: context)
            draw(.square, at: plan.podium, tint: input.podiumTint, diameter: diameter, context: context)
            }
            .frame(height: max(trackHeight, markDiameter * 1.2)).frame(minWidth: 144)
            rowReadings(row)
          }
          .frame(minHeight: 44).contentShape(Rectangle())
        }.accessibilityHidden(true)
    }

    private func draw(_ shape: FieldHeadlineKeyShape10868, at point: CGPoint?, tint: Color,
                      diameter: CGFloat, context: GraphicsContext) {
        guard let point, let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter),
              let plan = FieldHeadlineGeometry10868.keyPlan(shape, hollow: true,
                in: CGSize(width: side, height: side), diameter: diameter, lineWidth: 2), let stroke = plan.stroke else { return }
        var drawing = context
        drawing.translateBy(x: point.x - side / 2, y: point.y - side / 2)
        drawing.fill(plan.fill, with: .color(DS.cardBg)); drawing.stroke(stroke, with: .color(tint), lineWidth: plan.lineWidth)
    }

    private func glyph(_ shape: FieldHeadlineKeyShape10868, tint: Color) -> some View {
        let diameter = markDiameter
        let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter) ?? 0
        return Canvas { context, size in
            draw(shape, at: CGPoint(x: size.width / 2, y: size.height / 2), tint: tint, diameter: diameter, context: context)
        }.frame(width: side, height: side).accessibilityHidden(true)
    }

    @ViewBuilder private var selection: some View {
        if let selected = model.selected, let pair = selected.pair {
            HStack(alignment: .center, spacing: 8) {
                navigation(model.chooseID(input.previousID, canChoose: onChoosePair != nil), label: input.copy.previousLabel, symbol: "chevron.left")
                VStack(spacing: 4) {
                    Text(pair.name).font(.body.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                    Text(model.context).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity)
                navigation(model.chooseID(input.nextID, canChoose: onChoosePair != nil), label: input.copy.nextLabel, symbol: "chevron.right")
            }
            if model.selectionOutsideWindow {
                Text(input.copy.outsideWindow).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 12) { metrics(selected) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { metrics(selected) }
                    VStack(alignment: .leading, spacing: 12) { metrics(selected) }
                }
            }
            if let finish = model.selectedFinish {
                VStack(alignment: .leading, spacing: 2) {
                    Text(FieldChaseModel10868.label(finish)).font(.caption).foregroundStyle(DS.textSecondary)
                    if let ordinal = FieldChaseModel10868.figure(finish) { figure(ordinal, tint: DS.textPrimary) }
                    if let words = FieldChaseModel10868.words(finish) { Text(words).font(.body).fixedSize(horizontal: false, vertical: true) }
                }.accessibilityElement(children: .ignore).accessibilityLabel(FieldMovementModel10868.spoken(finish))
            }
        } else { Text(input.copy.noSelection).font(.body).fixedSize(horizontal: false, vertical: true) }
    }

    @ViewBuilder private func metrics(_ row: FieldPodiumRow10868) -> some View {
        metric(row.win, label: input.copy.winLabel, tint: input.winTint)
        metric(row.podium, label: input.copy.podiumLabel, tint: input.podiumTint)
    }

    private func metric(_ endpoint: FieldPodiumEndpoint10868?, label: String, tint: Color) -> some View {
        let action = model.originalAction(endpoint, canOpen: onOpenOriginal != nil)
        return original(action) {
            VStack(alignment: .leading, spacing: 6) {
                Text(label).font(.caption.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                if let reading = endpoint?.reading {
                    if let value = FieldChaseModel10868.figure(reading) { figure(value, tint: tint) }
                    if let words = FieldChaseModel10868.words(reading) { Text(words).font(.body).fixedSize(horizontal: false, vertical: true) }
                }
                Text(input.copy.beforeLabel).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                if let result = model.result(endpoint) {
                    Text(result.words).font(.subheadline.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(12).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay { RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 1) }.contentShape(Rectangle())
        }
        .accessibilityLabel(label)
        .accessibilityValue([endpoint.map { FieldMovementModel10868.spoken($0.reading) }, model.result(endpoint)?.words].compactMap { $0 }.joined(separator: ". "))
        .accessibilityHint(action == nil ? "" : (input.copy.originalHint ?? ""))
    }

    private func figure(_ value: String, tint: Color) -> some View {
        Text(value).font(.system(size: figureSize, weight: .semibold)).monospacedDigit().foregroundStyle(tint).fixedSize()
    }

    @ViewBuilder private func navigation(_ id: String?, label: String, symbol: String) -> some View {
        if onChoosePair != nil {
            Button { if let id { onChoosePair?(id) } } label: { Image(systemName: symbol).frame(minWidth: 44, minHeight: 44) }
                .disabled(id == nil).accessibilityLabel(label)
        }
    }

    @ViewBuilder private func choose<Content: View>(_ id: String?, @ViewBuilder content: () -> Content) -> some View {
        if let id, let onChoosePair { Button { onChoosePair(id) } label: { content() } }
        else { content().accessibilityElement(children: .ignore) }
    }

    @ViewBuilder private func original<Content: View>(_ ref: FieldChooserOriginalRef10868?, @ViewBuilder content: () -> Content) -> some View {
        if let ref, let onOpenOriginal { Button { onOpenOriginal(ref) } label: { content() } }
        else { content().accessibilityElement(children: .ignore) }
    }
}

// MARK: - #10868 field before-chance choices — "The shape of the field"
//
// The golf outlook's field-comparison card, built on the outlook above. A fan
// sees each of the owner's displayed golfers as one card: the whole name, that
// golfer's own recorded pre-tournament win chance as a prominent figure, and a
// full-width strip on ONE shared zero-based scale — a neutral track, a coloured
// prefix up to the exact own value and a hollow endpoint there — under the
// owner's visible label for the quantity ("Chance to win · pre-tournament").
// Choosing a card hands back that exact original. The card is an earlier-chance
// choice surface: the host's anchored chart carries the current win history and
// the host's reader carries Details.
//
// Presentation only, from the approved `DataGolfOutlook.tsx` comparison card
// and `datagolfOutlook.css` (`.dg-contenders`, `.dg-contender-number`,
// `.dg-contender-label`, the wide two-column and larger-text one-column
// variants). The reference's six-leader election (`leaders`), the
// name-matched profile pairing (`capturedProfile`), finite-value filter,
// percent label and colour identity are NOT ported. All of that arrives as
// owner input: the canonical catalogue (every original of every finish, shown
// or not), the displayed golfers in the owner's order and window, the raw
// before chances tied to their formatted readings, the scale, the selection
// and every word.
//
// Identity, the raw chance, the selected cue, the notice, the choose action and
// every spoken reading go through `FieldOutlookModel10868` on the chooser's own
// `FieldChooserModel10868` — the same resolver, before-reading tie, scale
// states, `barSummary` and actions the outlook bars use. A slot repeated in the
// displayed list, or one that does not resolve, keeps the owner's label beside
// the unavailable words and borrows no figure, strip or action; its neighbours
// keep theirs. Nothing here caps, ranks, sorts, prunes, matches names or
// normalizes; the owner may display six golfers or every one.
//
// The endpoint sits at the raw chance's exact fraction of the ceiling, on the
// finish strip's inset x (`FieldFinishGeometry10868.stripPlan`), so a genuine
// 0% is a hollow endpoint at the zero end with no prefix and a genuine 100% is
// whole at the far end. Above the ceiling there is no prefix or endpoint, only
// the neutral track, an edge mark and the owner's off-scale words beside the
// golfer's own figure; a missing, duplicated, foreign, mismatched or invalid
// chance draws no strip at all and is never drawn as zero. The golfer's own
// figure or absence words always stay, verbatim — nothing is parsed or
// formatted. Only each plan's before reading is read: a later reading,
// movement, preview, clock or result riding along is never shown, in any
// phase, and the outlook's result line is not read.
//
// One column on phone; two equal columns while each keeps the natural width
// of its whole name and figure and at least the minimum; accessibility sizes
// stack in one column. Owner order reads across, then down. The owner's tick
// labels are measured onto the strips' own inset (`FieldExpectationsAxisLayout10868`)
// above each column; the owner's scale words always stay. Nothing shrinks,
// truncates, caps or scrolls. The strips are decorative: each card speaks its
// own reading with its clock and source and any state words. A selected
// original outside the displayed golfers — another golfer, or another finish of
// a shown golfer — is static context under the owner's notice: its whole name
// and the selected cue only. It draws no figure, strip, quantity label or
// action, never joins or rewrites the owner's cohort and never stands in a
// leader's place; the host's hero, chooser and reader carry its chance. The
// host owns the scroll, the chart, the reader, Details, Back, focus and the
// held selection; this leaf keeps no state. The choose prompt is shown only
// while a displayed card that resolves actually chooses; with no callback,
// nothing pretends to act.
//
// Host binding still owed: GOLF-OUTLOOK-FIELD-CHOICES binding map (Design).

/// The owner's words this card adds to the outlook's copy.
nonisolated struct FieldBeforeChoicesCopy10868: Equatable {
    /// "Six leading captured win estimates"; nil draws none.
    let eyebrow: String?
    /// "Chance to win · pre-tournament" — the strip's quantity, under every strip.
    let chanceLabel: String
    /// "Pick a golfer to explore their finish outlook." — shown only while a card chooses.
    let choosePrompt: String?
}

nonisolated struct FieldBeforeChoicesInput10868: Equatable {
    /// The outlook's input: scope, canonical catalogue, selection, displayed
    /// golfers in the owner's order, raw before chances, scale and copy. Its
    /// phase, traversal, step, details and result words are not read here.
    let outlook: FieldOutlookInput10868
    let copy: FieldBeforeChoicesCopy10868
}

nonisolated enum FieldBeforeChoicesGeometry10868 {
    /// The narrowest column a two-column plan offers each card.
    static let columnMinimum: CGFloat = 260

    /// The plans to try, widest first. Accessibility sizes stack in one column.
    static func columnCandidates(accessibilitySize: Bool) -> [Int] {
        accessibilitySize ? [1] : [2, 1]
    }

    /// The owner's items in reading order, `columns` to a line: every item
    /// once, in order; only the last line may be short. None for no columns.
    static func lines<Item>(_ items: [Item], columns: Int) -> [[Item]] {
        guard columns > 0 else { return [] }
        return stride(from: 0, to: items.count, by: columns).map { Array(items[$0..<min($0 + columns, items.count)]) }
    }

    /// The coloured prefix on the strip's line, from the zero end to the
    /// endpoint's centre. None without an endpoint, at a real zero or for a
    /// line that cannot be drawn.
    static func prefix(_ plan: FieldFinishStripPlan10868, lineWidth: CGFloat) -> CGRect? {
        guard let dot = plan.dot, lineWidth.isFinite, lineWidth > 0, dot.midX > plan.zeroX else { return nil }
        return CGRect(x: plan.zeroX, y: plan.baselineY - lineWidth / 2, width: dot.midX - plan.zeroX, height: lineWidth)
    }
}

/// The card's rules, resolved once per input, on the outlook's own model.
nonisolated struct FieldBeforeChoicesModel10868: Equatable {
    let input: FieldBeforeChoicesInput10868
    /// The outlook's resolver, raw-chance tie, scale, selection, actions and summaries.
    let outlook: FieldOutlookModel10868

    init(_ input: FieldBeforeChoicesInput10868) {
        self.input = input
        outlook = FieldOutlookModel10868(input.outlook)
    }

    var field: FieldChooserModel10868 { outlook.field }

    /// The outlook's bars for the displayed golfers, in the owner's order.
    var cards: [FieldOutlookBar10868] { outlook.bars }

    /// The golfer's own before reading is a recorded figure, not absence words.
    func isRecorded(_ card: FieldOutlookBar10868) -> Bool {
        guard let original = card.resolution.original,
              case .recorded = FieldOutlookModel10868.beforeReading(original.plan).value
        else { return false }
        return true
    }

    /// A selected original that resolves but is not among the cards, kept by
    /// its exact identity as static context. It is never a card: no chance,
    /// strip, quantity label or action, and never a displayed leader. Its
    /// outcome may not be the cards' quantity (Rory's Top 5 beside the win
    /// chances), so the host's hero, chooser and reader carry its figure.
    var selectedOutside: FieldChooserOriginal10868? {
        guard outlook.isSelectedOutsideDisplayed else { return nil }
        return outlook.selectedOriginal
    }

    /// What the outside context says beside its name: only the owner's
    /// selected words — never a figure, reading or quantity label.
    var selectedOutsideWords: String? {
        selectedOutside.flatMap { FieldMovementModel10868.readable(field.selectedWords($0)) }
    }

    // MARK: Scale

    /// The scale words and tick labels are shown only for a valid scale with
    /// readable words.
    var showsScale: Bool {
        input.outlook.scale.isValid && FieldMovementModel10868.readable(input.outlook.scale.words) != nil
    }

    var ticks: [FieldOutlookPlacedTick10868] { showsScale ? outlook.ticks : [] }

    // MARK: Choose

    /// The owner's prompt, only while a displayed card that resolves actually
    /// chooses. A selection held outside the cards never earns it.
    func choosePrompt(canChoose: Bool) -> String? {
        guard cards.contains(where: { $0.resolution.original != nil && outlook.barAction($0, canChoose: canChoose) != nil })
        else { return nil }
        return FieldMovementModel10868.readable(input.copy.choosePrompt)
    }
}

nonisolated enum FieldBeforeChoicesAccessibilityID10868 {
    static let cards = "fieldBeforeChoices10868.cards"
    static let outside = "fieldBeforeChoices10868.outside"
    static func card(_ outcomeID: String) -> String { "fieldBeforeChoices10868.card.\(outcomeID)" }
}

struct FieldBeforeChanceChoicesPresentation10868: View {
    let input: FieldBeforeChoicesInput10868
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)?
    private let model: FieldBeforeChoicesModel10868

    init(input: FieldBeforeChoicesInput10868, onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil) {
        self.input = input
        self.onChoose = onChoose
        self.model = FieldBeforeChoicesModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var dotDiameter: CGFloat = 12
    @ScaledMetric(relativeTo: .caption) private var lineWidth: CGFloat = 7

    private var canChoose: Bool { onChoose != nil }
    /// Half an endpoint and a hair, so an endpoint at zero or at the ceiling stays whole.
    private var inset: CGFloat { dotDiameter / 2 + 1 }
    private let cardPadding: CGFloat = 14

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let eyebrow = FieldMovementModel10868.readable(input.copy.eyebrow) {
                Text(eyebrow)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(input.outlook.copy.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let note = input.outlook.copy.note {
                ownerWords(note)
            }
            if let prompt = model.choosePrompt(canChoose: canChoose) {
                ownerWords(prompt)
            }
            if model.showsScale {
                ownerWords(input.outlook.scale.words)
            }
            if let notice = model.outlook.notice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let outside = model.selectedOutside {
                outsideContext(outside)
            }
            let cards = model.cards
            if !cards.isEmpty {
                arrangement(cards)
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(input.outlook.copy.graphicLabel)
                    .accessibilityIdentifier(FieldBeforeChoicesAccessibilityID10868.cards)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Arrangement

    @ViewBuilder private func arrangement(_ cards: [FieldOutlookBar10868]) -> some View {
        if FieldBeforeChoicesGeometry10868.columnCandidates(accessibilitySize: typeSize.isAccessibilitySize) == [1] {
            grid(cards, columns: 1)
        } else {
            ViewThatFits(in: .horizontal) {
                grid(cards, columns: 2)
                grid(cards, columns: 1)
            }
        }
    }

    /// The owner's order across, then down; the owner's tick labels above each
    /// column. In two columns every card keeps at least the minimum width.
    private func grid(_ cards: [FieldOutlookBar10868], columns: Int) -> some View {
        let lines = FieldBeforeChoicesGeometry10868.lines(Array(cards.enumerated()), columns: columns)
        let axes = min(columns, cards.count)
        let minimum: CGFloat? = columns > 1 ? FieldBeforeChoicesGeometry10868.columnMinimum : nil
        let ticks = model.ticks
        return Grid(alignment: .topLeading, horizontalSpacing: 10, verticalSpacing: 10) {
            if !ticks.isEmpty {
                GridRow {
                    ForEach(0..<axes, id: \.self) { _ in
                        axis(ticks)
                            .frame(minWidth: minimum, maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                GridRow {
                    ForEach(line, id: \.offset) { item in
                        card(item.element, id: FieldBeforeChoicesAccessibilityID10868.card(item.element.slot.ref.outcomeID))
                            .frame(minWidth: minimum, maxWidth: .infinity, alignment: .topLeading)
                    }
                }
            }
        }
    }

    /// The owner's tick labels, measured onto the strips' own inset inside a
    /// card. Decorative — the scale words above and every card say the same.
    private func axis(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
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
        .padding(.horizontal, cardPadding)
        .accessibilityHidden(true)
    }

    // MARK: Selected outside the cards

    /// The held selection outside the cards, as static context only: its whole
    /// name and the selected cue. No figure, strip, quantity label, hint or
    /// action — it is not one of the compared golfers.
    private func outsideContext(_ original: FieldChooserOriginal10868) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(original.name)
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let words = model.selectedOutsideWords {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark").font(.caption2.weight(.bold))
                    Text(words).font(.caption.weight(.semibold))
                }
                .foregroundStyle(DS.blue)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(original.name)
        .accessibilityValue(model.selectedOutsideWords ?? "")
        .accessibilityAddTraits(.isSelected)
        .accessibilityIdentifier(FieldBeforeChoicesAccessibilityID10868.outside)
    }

    // MARK: Cards

    @ViewBuilder private func card(_ card: FieldOutlookBar10868, id: String) -> some View {
        if let original = card.resolution.original {
            let accent = original.accent ?? DS.blue
            let action = model.outlook.barAction(card, canChoose: canChoose)
            let selected = model.outlook.isSelected(card)
            control(action) {
                VStack(alignment: .leading, spacing: 8) {
                    heading(card, original: original, accent: accent)
                    strip(card, accent: accent)
                    if let words = model.outlook.stateWords(card) {
                        ownerWords(words)
                    }
                    ownerWords(input.copy.chanceLabel)
                }
                .padding(cardPadding)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(selected ? accent : DS.border, lineWidth: selected ? 2 : 1))
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(model.outlook.barSummary(card))
            .accessibilityHint(model.outlook.hint(action))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if let label = FieldMovementModel10868.readable(card.slot.label) {
                    Text(label)
                        .font(.body)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.outlook.unavailableWords)
            }
            .padding(cardPadding)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(DS.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.outlook.barSummary(card))
            .accessibilityIdentifier(id)
        }
    }

    /// The whole name, the selected cue and the golfer's own figure on one
    /// line; stacked at accessibility sizes.
    private func heading(_ card: FieldOutlookBar10868, original: FieldChooserOriginal10868, accent: Color) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
        return layout {
            VStack(alignment: .leading, spacing: 4) {
                Text(original.name)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let words = model.field.selectedWords(original) {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark").font(.caption2.weight(.bold))
                        Text(words).font(.caption.weight(.semibold))
                    }
                    .foregroundStyle(DS.blue)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let figure = model.outlook.figure(card) {
                if model.isRecorded(card) {
                    Text(figure)
                        .font(.system(size: figureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(accent)
                        .fixedSize()
                } else {
                    Text(figure)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    /// A placed value draws the track, prefix and hollow endpoint; above the
    /// ceiling, the neutral track and an edge mark only; otherwise no strip.
    @ViewBuilder private func strip(_ card: FieldOutlookBar10868, accent: Color) -> some View {
        switch card.chance {
        case .value(_, let fraction):
            track(fraction: fraction, accent: accent)
        case .offScale:
            track(fraction: nil, accent: accent)
                .overlay(alignment: .trailing) {
                    Image(systemName: "arrow.right.to.line")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textSecondary)
                        .accessibilityHidden(true)
                }
        case .unavailable:
            EmptyView()
        }
    }

    /// The neutral track end to end, the coloured prefix and the hollow
    /// endpoint, all from the finish strip's shared plan.
    private func track(fraction: Double?, accent: Color) -> some View {
        let trackColor = DS.border
        let ringFill = DS.cardBg
        let inset = self.inset
        let diameter = dotDiameter
        let width = lineWidth
        return Canvas { context, size in
            guard let plan = FieldFinishGeometry10868.stripPlan(fraction: fraction, ticks: [], in: size, inset: inset, dotDiameter: diameter) else { return }
            var line = Path()
            line.move(to: CGPoint(x: plan.zeroX, y: plan.baselineY))
            line.addLine(to: CGPoint(x: plan.ceilingX, y: plan.baselineY))
            context.stroke(line, with: .color(trackColor), lineWidth: width)
            if let prefix = FieldBeforeChoicesGeometry10868.prefix(plan, lineWidth: width) {
                context.fill(Path(prefix), with: .color(accent))
            }
            if let dot = plan.dot {
                context.fill(Path(ellipseIn: dot), with: .color(ringFill))
                context.stroke(Path(ellipseIn: dot.insetBy(dx: 1, dy: 1)), with: .color(accent), lineWidth: 2)
            }
        }
        .frame(maxWidth: .infinity, minHeight: diameter, maxHeight: diameter)
        .accessibilityHidden(true)
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func control<Content: View>(_ action: FieldChooserAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onChoose: onChoose, onControl: nil)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}
