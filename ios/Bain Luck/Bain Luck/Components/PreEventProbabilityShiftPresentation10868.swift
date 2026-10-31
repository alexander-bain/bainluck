import SwiftUI

// #10868 — "Before the race": the Olympic 500m page's required pre-event gold
// expectations card. For each of the owner's named skaters a fan compares that
// skater's own gold chance at its first captured trade with its latest captured
// trade before race day: two hollow marks on one common 0–100% scale joined by
// a connector, a small mark for the first and a larger one for the latest, each
// figure equally readable beside its own label and its own clock. Both marks are
// before race day, and the card says so in a visible key.
//
// Presentation only, from the approved `SkatingRace.tsx` `movement` card and
// `skatingRace.css` (`.sk-move-plot`, `.sk-move-picks`, larger-text variants),
// with the identity marks of `SkatingTradeMark` / `SkatingIdentityKey`. The
// reference's featured cohort, first/last trade election, race-day cutoff,
// percent and clock formatting, colour and shape assignment
// (`skatingEvidence.ts`) are NOT ported. All of that arrives as owner input:
// the canonical catalogue, the displayed skaters with their whole names and
// glyphs in the owner's order, each endpoint's separately admitted reading, the
// raw observations tied to those readings with their opaque keys, the explicit
// phase, the common scale with its tick labels and every label and absence word.
//
// Identity goes through the chooser's own `FieldChooserModel10868` — the same
// resolver every chooser row uses. A displayed slot listed twice, or one that
// does not resolve, keeps the owner's name beside the unavailable words and
// borrows no figure, mark or action; its neighbours keep theirs. Every
// canonical original stays in the catalogue, shown or not.
//
// Each endpoint is its own subject. Its figure is the owner's ONE admitted
// reading for that exact original and endpoint, shown only while the owner's
// ONE observation for the same original and endpoint carries that reading
// (label, figure and clock line) and a raw value that is a probability
// (`FieldChaseModel10868.qualified`). An owner's absence words are shown as
// they are; anything else — missing, duplicated, mismatched or invalid — shows
// the copy's words with no figure and no mark. One endpoint never lends its
// figure, mark or key to the other. A key is opaque and only ever travels with
// its own original and endpoint, so two originals may carry the same string. The two observations are independently
// timed: never interpolated, normalized, complemented, summed or put on a
// shared clock. The first captured trade is not an opening quote and the latest
// before race day is not a closing or race-start chance; nothing here calls a
// later trade current, reads a preview, or reads the original's movement,
// clock or result — this card shows no actual time, rank or grade.
//
// Each mark sits at its own raw value's exact fraction of the scale (the
// outlook's `FieldOutlookGeometry10868.fraction`) on the same inset x as the
// ticks and the measured axis labels (`FieldFinishGeometry10868.x`,
// `FieldExpectationsAxisLayout10868`), so a genuine 0% or 100% is a whole mark
// at the edge. Equal values at different clocks are two concentric hollow
// marks, the small one inside the large one with a gap — never displaced. A
// value above the ceiling draws no mark, only an edge arrow and the owner's
// off-scale words beside its own figure. A connector joins two placed marks
// only: never from zero, never toward an absent mark. It is a comparison aid,
// not a history: no path between the dates is drawn or implied.
//
// The phase is the owner's explicit input. The card is shown before race day
// and at the final; during a race there is no card at all — no live state is
// invented here. The tracks are decorative: each skater speaks the whole name,
// both labelled chances and their own clocks. Each shown figure with its own
// key hands back the exact original and that key to the host's history reader —
// only for a row and endpoint the current input still resolves to exactly that;
// with no callback, nothing pretends to act. The host owns the scroll, the
// reader, Details, history, Back, focus and held snapshots; this leaf keeps no
// state and runs no animation.
//
// Host binding still owed — not available at this base: the gold originals
// mapped through Native's existing production identity path (a provider market
// or token id, a name or an index is never a link), each skater's admitted
// first-captured and latest-before-race-day readings with their own clocks and
// observation keys, the displayed cohort with its glyphs, the scale and copy.

/// Which of an original's two pre-race-day observations.
nonisolated enum PreEventShiftEndpointKind10868: Hashable, CaseIterable {
    /// The first captured trade. Not a verified opening quote.
    case first
    /// The latest captured trade before race day. Not a closing or race-start chance.
    case latest
}

/// The owner's chart-mark shape for one skater, matching that skater's marks
/// on the main gold history. Never derived here.
nonisolated enum PreEventShiftGlyph10868: Equatable, CaseIterable {
    case circle
    case triangle
    case diamond
    /// Additive (#10868 field page, Design 2026-10-31): the third field
    /// contender's square, the same mark its headline key and history line
    /// carry. Existing owners never receive it unless they pass it.
    case square
}

/// One displayed skater, in the owner's order.
nonisolated struct PreEventShiftSlot10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's full name, kept beside the unavailable words when the slot
    /// does not resolve.
    let name: String
    let glyph: PreEventShiftGlyph10868
}

/// The owner's separately admitted reading for one endpoint of one original.
nonisolated struct PreEventShiftReading10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let endpoint: PreEventShiftEndpointKind10868
    /// "First captured", `.recorded("68%", "Feb 7, 1:20 AM Milan · Polymarket")`,
    /// or the owner's absence words.
    let reading: FieldChooserReading10868
}

/// One raw observation, tied to the reading the owner formatted from it.
nonisolated struct PreEventShiftObservation10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let endpoint: PreEventShiftEndpointKind10868
    let observation: FieldMovementObservation10868
    /// The owner's opaque key for this observation, handed back unchanged on
    /// open. Never read.
    let key: String
}

/// The owner's words for this card.
nonisolated struct PreEventShiftCopy10868: Equatable {
    /// "GOLD EXPECTATIONS"; nil draws none.
    let eyebrow: String?
    /// "Before the race".
    let title: String
    /// "Both marks: before race day". Always shown with the rows.
    let phaseKey: String
    /// "Small: first captured".
    let firstKey: String
    /// "Large: latest before race day".
    let latestKey: String
    /// Spoken name of the rows.
    let graphicLabel: String
    /// Label of a first endpoint that cannot be shown ("First captured").
    let firstLabel: String
    /// Label of a latest endpoint that cannot be shown ("Latest before race day").
    let latestLabel: String
    /// An endpoint not tied to this card ("Not recorded for this comparison").
    let endpointUnavailable: String
    /// A chance above the ceiling ("Above this scale").
    let offScale: String
    /// "Each chance keeps its own trade time"; nil draws none.
    let note: String?
    /// Spoken hint on an endpoint that opens; nil none.
    let openHint: String?
}

nonisolated struct PreEventShiftInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    /// The rows, in the owner's order. Never sorted, filtered, capped or deduplicated here.
    let displayed: [PreEventShiftSlot10868]
    let readings: [PreEventShiftReading10868]
    let observations: [PreEventShiftObservation10868]
    /// The owner's one scale for every track (0–100%: ceiling 1).
    let scale: FieldOutlookScale10868
    let phase: FieldOutlookPhase10868
    let copy: PreEventShiftCopy10868
    /// A slot that does not resolve ("Skater unavailable in this update").
    let unavailableWords: String
}

/// What one endpoint of a resolved row shows.
nonisolated struct PreEventShiftSide10868: Equatable {
    let kind: PreEventShiftEndpointKind10868
    /// The admitted reading while tied, its own absence words, or the copy's words.
    let endpoint: FieldMovementEndpoint10868
    /// Where the tied raw chance sits on the scale.
    let chance: FieldOutlookChance10868
    /// The tied observation's own key while its figure is shown; never the other endpoint's.
    let key: String?
}

nonisolated struct PreEventShiftRow10868: Equatable {
    let slot: PreEventShiftSlot10868
    let resolution: FieldChooserResolution10868
    /// Nil when the slot does not resolve.
    let first: PreEventShiftSide10868?
    let latest: PreEventShiftSide10868?

    var sides: [PreEventShiftSide10868] { [first, latest].compactMap { $0 } }
}

/// One hollow mark on a track.
nonisolated struct PreEventShiftMark10868: Equatable {
    let center: CGPoint
    /// The reference radius `r` of the glyph.
    let radius: CGFloat
}

/// What one track Canvas draws inside its own rect.
nonisolated struct PreEventShiftTrackPlan10868: Equatable {
    let centerY: CGFloat
    let zeroX: CGFloat
    let ceilingX: CGFloat
    /// Zero and every owner tick on the scale.
    let tickXs: [CGFloat]
    /// Between the two placed marks; nil unless both are placed apart.
    let connector: CGRect?
    /// The small first-captured mark; nil draws none.
    let first: PreEventShiftMark10868?
    /// The large latest-before-race-day mark; nil draws none.
    let latest: PreEventShiftMark10868?
}

nonisolated enum PreEventShiftGeometry10868 {
    /// The first mark's radius as a share of the latest's — the reference's
    /// r = 3 beside r = 6, so a concentric pair keeps a gap between the rings.
    static let firstScale: CGFloat = 0.5

    /// Each glyph's reach from its centre in multiples of r — the reference
    /// `SkatingTradeMark`: a circle of radius r, a triangle 1.1 r wide either
    /// side with its apex 1.25 r up and its base r down, a diamond 1.2 r. The
    /// square's half-side is 0.85 r, the history chart's approved square
    /// (`FieldHistoryGeometry10868.markPath`); it reaches less than the diamond,
    /// so the shared marker box and track inset are unchanged by it.
    static func reach(_ glyph: PreEventShiftGlyph10868) -> (half: CGFloat, up: CGFloat, down: CGFloat) {
        switch glyph {
        case .circle: (1, 1, 1)
        case .triangle: (1.1, 1.25, 1)
        case .diamond: (1.2, 1.2, 1.2)
        case .square: (0.85, 0.85, 0.85)
        }
    }

    /// The glyph's whole extent around a centre.
    static func bounds(_ glyph: PreEventShiftGlyph10868, center: CGPoint, radius: CGFloat) -> CGRect {
        let reach = Self.reach(glyph)
        return CGRect(
            x: center.x - reach.half * radius,
            y: center.y - reach.up * radius,
            width: 2 * reach.half * radius,
            height: (reach.up + reach.down) * radius
        )
    }

    static func path(_ glyph: PreEventShiftGlyph10868, center: CGPoint, radius: CGFloat) -> Path {
        let box = Self.bounds(glyph, center: center, radius: radius)
        switch glyph {
        case .circle:
            return Path(ellipseIn: box)
        case .triangle:
            var path = Path()
            path.move(to: CGPoint(x: center.x, y: box.minY))
            path.addLine(to: CGPoint(x: box.maxX, y: box.maxY))
            path.addLine(to: CGPoint(x: box.minX, y: box.maxY))
            path.closeSubpath()
            return path
        case .diamond:
            var path = Path()
            path.move(to: CGPoint(x: center.x, y: box.minY))
            path.addLine(to: CGPoint(x: box.maxX, y: center.y))
            path.addLine(to: CGPoint(x: center.x, y: box.maxY))
            path.addLine(to: CGPoint(x: box.minX, y: center.y))
            path.closeSubpath()
            return path
        case .square:
            return Path(box)
        }
    }

    /// The side of the one square every glyph of this radius fits in whole,
    /// outline included: the largest horizontal or vertical reach of any glyph.
    static func markExtent(radius: CGFloat, lineWidth: CGFloat) -> CGFloat {
        let reach = PreEventShiftGlyph10868.allCases.map { glyph -> CGFloat in
            let reach = Self.reach(glyph)
            return max(2 * reach.half, reach.up + reach.down)
        }.max() ?? 2
        return reach * radius + lineWidth
    }

    /// The glyph's centre so its whole reach is centred in `size` — the
    /// triangle's apex reaches further up than its base reaches down.
    static func center(_ glyph: PreEventShiftGlyph10868, in size: CGSize, radius: CGFloat) -> CGPoint {
        let reach = Self.reach(glyph)
        return CGPoint(x: size.width / 2, y: size.height / 2 + (reach.up - reach.down) * radius / 2)
    }

    /// Where a hollow glyph's ink reaches. Strokes use round joins, so no
    /// corner reaches further than half the line beyond the outline.
    static func strokedBounds(_ glyph: PreEventShiftGlyph10868, center: CGPoint, radius: CGFloat, lineWidth: CGFloat) -> CGRect {
        bounds(glyph, center: center, radius: radius).insetBy(dx: -lineWidth / 2, dy: -lineWidth / 2)
    }

    /// The outline every hollow glyph is stroked with.
    static func stroke(lineWidth: CGFloat) -> StrokeStyle {
        StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round)
    }

    /// The track and axis inset, so a large mark at zero or at the ceiling stays
    /// whole: the expectations card's own rule on the largest glyph reach.
    static func inset(radius: CGFloat, lineWidth: CGFloat) -> CGFloat {
        FieldExpectationsGeometry10868.inset(markDiameter: markExtent(radius: radius, lineWidth: lineWidth))
    }

    /// The one drawing plan every track Canvas uses: both marks centred on one
    /// line at their own exact x, on the same inset as the axis labels, and a
    /// connector only between two placed marks. Nil for a size that cannot hold
    /// the glyph; no mark for a missing, off-scale or invalid fraction — never
    /// clamped.
    static func trackPlan(
        glyph: PreEventShiftGlyph10868,
        first: Double?,
        latest: Double?,
        ticks: [Double],
        in size: CGSize,
        radius: CGFloat,
        lineWidth: CGFloat,
        connectorWidth: CGFloat
    ) -> PreEventShiftTrackPlan10868? {
        let inset = Self.inset(radius: radius, lineWidth: lineWidth)
        let reach = Self.reach(glyph)
        guard radius.isFinite, radius > 0, lineWidth.isFinite, lineWidth > 0,
              connectorWidth.isFinite, connectorWidth > 0, size.height.isFinite,
              size.height >= (reach.up + reach.down) * radius + lineWidth,
              let zero = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let ceiling = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset)
        else { return nil }
        // The glyph's own centre sits so its whole reach is centred in the rect.
        let centerY = Self.center(glyph, in: size, radius: radius).y
        func x(_ fraction: Double?) -> CGFloat? {
            fraction.flatMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) }
        }
        let firstX = x(first)
        let latestX = x(latest)
        var connector: CGRect?
        if let start = firstX, let end = latestX, start != end {
            connector = CGRect(x: min(start, end), y: centerY - connectorWidth / 2, width: abs(end - start), height: connectorWidth)
        }
        return PreEventShiftTrackPlan10868(
            centerY: centerY,
            zeroX: zero,
            ceilingX: ceiling,
            tickXs: ([0] + ticks).compactMap { x($0) },
            connector: connector,
            first: firstX.map { PreEventShiftMark10868(center: CGPoint(x: $0, y: centerY), radius: radius * firstScale) },
            latest: latestX.map { PreEventShiftMark10868(center: CGPoint(x: $0, y: centerY), radius: radius) }
        )
    }

    /// The layouts to try, in order. Accessibility sizes stack the two
    /// readings; otherwise side by side while both keep their whole width.
    static func readoutArrangements(accessibilitySize: Bool) -> [FieldChooserArrangement10868] {
        FieldChaseGeometry10868.stacksReadouts(accessibilitySize: accessibilitySize) ? [.stacked] : [.sideBySide, .stacked]
    }
}

/// The card's rules, resolved once per input, on the chooser's own resolver.
nonisolated struct PreEventShiftModel10868: Equatable {
    let input: PreEventShiftInput10868
    /// The chooser's resolver.
    let field: FieldChooserModel10868
    /// Displayed identities listed more than once.
    private let repeatedDisplayed: Set<FieldChooserOriginalRef10868>

    init(_ input: PreEventShiftInput10868) {
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

    /// Before race day and at the final. During a race there is no card: no
    /// rows, words, artwork or actions.
    var isShown: Bool { input.phase == .before || input.phase == .final }

    var eyebrow: String? { isShown ? FieldMovementModel10868.readable(input.copy.eyebrow) : nil }

    var note: String? { isShown ? FieldMovementModel10868.readable(input.copy.note) : nil }

    // MARK: Rows

    var rows: [PreEventShiftRow10868] {
        guard isShown else { return [] }
        return input.displayed.map { slot in
            let resolution: FieldChooserResolution10868 = repeatedDisplayed.contains(slot.ref) ? .unavailable : field.resolve(slot.ref)
            guard let original = resolution.original else {
                return PreEventShiftRow10868(slot: slot, resolution: resolution, first: nil, latest: nil)
            }
            return PreEventShiftRow10868(
                slot: slot,
                resolution: resolution,
                first: side(.first, for: original.ref),
                latest: side(.latest, for: original.ref)
            )
        }
    }

    /// The owner's one admitted reading for this exact original and endpoint;
    /// several, even identical, are none.
    func admitted(_ kind: PreEventShiftEndpointKind10868, for ref: FieldChooserOriginalRef10868) -> FieldChooserReading10868? {
        let matches = input.readings.filter { $0.ref == ref && $0.endpoint == kind }
        return matches.count == 1 ? matches[0].reading : nil
    }

    /// The owner's one observation for this exact original and endpoint;
    /// several, even identical, are none.
    func observation(_ kind: PreEventShiftEndpointKind10868, for ref: FieldChooserOriginalRef10868) -> PreEventShiftObservation10868? {
        let matches = input.observations.filter { $0.ref == ref && $0.endpoint == kind }
        return matches.count == 1 ? matches[0] : nil
    }

    func label(_ kind: PreEventShiftEndpointKind10868) -> String {
        kind == .first ? input.copy.firstLabel : input.copy.latestLabel
    }

    /// The admitted reading while its own observation is tied and qualified;
    /// the owner's absence words as they are; otherwise the copy's words.
    func side(_ kind: PreEventShiftEndpointKind10868, for ref: FieldChooserOriginalRef10868) -> PreEventShiftSide10868 {
        let unavailable = PreEventShiftSide10868(
            kind: kind,
            endpoint: .unavailable(label: label(kind), words: input.copy.endpointUnavailable),
            chance: .unavailable,
            key: nil
        )
        guard let reading = admitted(kind, for: ref) else { return unavailable }
        guard case .recorded = reading.value else {
            return PreEventShiftSide10868(kind: kind, endpoint: .reading(reading), chance: .unavailable, key: nil)
        }
        guard let tied = observation(kind, for: ref),
              let qualified = FieldChaseModel10868.qualified(tied.observation),
              qualified.reading == reading
        else { return unavailable }
        return PreEventShiftSide10868(
            kind: kind, endpoint: .reading(reading), chance: chance(qualified.probability),
            key: FieldMovementModel10868.readable(tied.key)
        )
    }

    /// A tied raw chance on the shared scale: placed, or above the ceiling.
    func chance(_ probability: Double) -> FieldOutlookChance10868 {
        guard input.scale.isValid else { return .unavailable }
        guard let fraction = FieldOutlookGeometry10868.fraction(probability, ceiling: input.scale.ceiling) else {
            return .offScale
        }
        return .value(probability: probability, fraction: fraction)
    }

    /// The unavailable words for a slot that does not resolve; the owner's
    /// off-scale words beside a figure whose mark is above the ceiling.
    func stateWords(_ row: PreEventShiftRow10868) -> String? {
        guard row.resolution.original != nil else { return input.unavailableWords }
        return row.sides.contains { $0.chance == .offScale } ? input.copy.offScale : nil
    }

    // MARK: Scale

    /// Tracks are drawn only beside the owner's explicit scale: a valid scale
    /// and its readable words. Never a bare track.
    var showsTracks: Bool {
        isShown && input.scale.isValid && FieldMovementModel10868.readable(input.scale.words) != nil
    }

    /// A row draws its track while one of its chances is placed or above the ceiling.
    func showsTrack(_ row: PreEventShiftRow10868) -> Bool {
        guard showsTracks, row.resolution.original != nil else { return false }
        return row.sides.contains { $0.chance != .unavailable }
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

    /// The exact original and this endpoint's own key while its figure is
    /// shown — only with a callback, while the card is shown, and only for a
    /// displayed slot that this input still resolves to the row's own original
    /// and whose current endpoint of that kind is exactly `side`. A side from
    /// another row, an earlier input or a withdrawn original opens nothing. No
    /// other endpoint's key, no default.
    func openAction(_ row: PreEventShiftRow10868, _ side: PreEventShiftSide10868, canOpen: Bool) -> FieldMovementOpen10868? {
        guard canOpen, isShown, let original = row.resolution.original,
              input.displayed.contains(row.slot), !repeatedDisplayed.contains(row.slot.ref),
              field.resolve(row.slot.ref) == .original(original),
              self.side(side.kind, for: original.ref) == side,
              let key = side.key, case .reading(let reading) = side.endpoint, case .recorded = reading.value
        else { return nil }
        return FieldMovementOpen10868(ref: original.ref, observation: key)
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ opening: FieldMovementOpen10868?) -> String {
        opening == nil ? "" : (input.copy.openHint ?? "")
    }

    // MARK: VoiceOver

    /// One endpoint with its whole subject: the skater's full name, then the
    /// labelled chance with its own clock, or its words.
    func endpointSummary(_ row: PreEventShiftRow10868, _ side: PreEventShiftSide10868) -> String {
        let name = row.resolution.original?.name ?? row.slot.name
        return [name, FieldMovementModel10868.spoken(side.endpoint)]
            .filter { FieldMovementModel10868.readable($0) != nil }
            .joined(separator: ". ")
    }

    /// A row's whole reading in the owner's words, so its track may stay
    /// decorative: the full name, both chances with their own clocks, and any
    /// state words.
    func rowSummary(_ row: PreEventShiftRow10868) -> String {
        guard let original = row.resolution.original else {
            return [row.slot.name, input.unavailableWords]
                .filter { FieldMovementModel10868.readable($0) != nil }
                .joined(separator: ". ")
        }
        var parts = [original.name]
        parts += row.sides.map { FieldMovementModel10868.spoken($0.endpoint) }
        if let words = stateWords(row) { parts.append(words) }
        return parts.joined(separator: ". ")
    }
}

nonisolated enum PreEventShiftAccessibilityID10868 {
    static let rows = "preEventShift10868.rows"
    static let scale = "preEventShift10868.scale"
    static func row(_ outcomeID: String) -> String { "preEventShift10868.row.\(outcomeID)" }
    static func endpoint(_ outcomeID: String, _ kind: PreEventShiftEndpointKind10868) -> String {
        "preEventShift10868.endpoint.\(outcomeID).\(kind == .first ? "first" : "latest")"
    }
}

struct PreEventProbabilityShiftPresentation10868: View {
    let input: PreEventShiftInput10868
    var onOpen: ((FieldMovementOpen10868) -> Void)?
    private let model: PreEventShiftModel10868

    init(input: PreEventShiftInput10868, onOpen: ((FieldMovementOpen10868) -> Void)? = nil) {
        self.input = input
        self.onOpen = onOpen
        self.model = PreEventShiftModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 24
    /// The latest mark's reference radius; the first mark is half of it.
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 7

    private let lineWidth: CGFloat = 2
    private var canOpen: Bool { onOpen != nil }
    private var inset: CGFloat { PreEventShiftGeometry10868.inset(radius: markRadius, lineWidth: lineWidth) }

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
                markKey
                let rows = model.rows
                if model.showsTracks, rows.contains(where: model.showsTrack) {
                    scaleHeader
                }
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        skater(row)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(input.copy.graphicLabel)
                .accessibilityIdentifier(PreEventShiftAccessibilityID10868.rows)
                if let note = model.note {
                    ownerWords(note)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Key and scale

    /// "Both marks: before race day", then the small and large hollow marks
    /// beside their own words, so the meaning never rests on size alone.
    private var markKey: some View {
        VStack(alignment: .leading, spacing: 4) {
            ownerWords(input.copy.phaseKey)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { sizeKeys }
                VStack(alignment: .leading, spacing: 4) { sizeKeys }
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var sizeKeys: some View {
        sizeKey(.first, words: input.copy.firstKey)
        sizeKey(.latest, words: input.copy.latestKey)
    }

    private func sizeKey(_ kind: PreEventShiftEndpointKind10868, words: String) -> some View {
        HStack(spacing: 6) {
            glyphMark(.circle, kind: kind, accent: DS.textSecondary)
            ownerWords(words)
        }
    }

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
        .accessibilityIdentifier(PreEventShiftAccessibilityID10868.scale)
    }

    // MARK: Rows

    @ViewBuilder private func skater(_ row: PreEventShiftRow10868) -> some View {
        let id = PreEventShiftAccessibilityID10868.row(row.slot.ref.outcomeID)
        if let original = row.resolution.original {
            let accent = original.accent ?? DS.blue
            let actions = row.sides.map { model.openAction(row, $0, canOpen: canOpen) }
            let content = VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .center, spacing: 6) {
                    identityKey(row.slot.glyph, accent: accent)
                    Text(original.name)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if model.showsTrack(row) {
                    track(row, accent: accent)
                }
                readouts(row, accent: accent)
                if let words = model.stateWords(row) {
                    ownerWords(words)
                }
            }
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(DS.border).frame(height: 1) }

            if actions.contains(where: { $0 != nil }) {
                content
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(original.name)
                    .accessibilityIdentifier(id)
            } else {
                content
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(model.rowSummary(row))
                    .accessibilityIdentifier(id)
            }
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

    /// Both chances at the same figure size, each beside its own hollow mark,
    /// label and clock; side by side while both keep their width, else stacked.
    @ViewBuilder
    private func readouts(_ row: PreEventShiftRow10868, accent: Color) -> some View {
        let arrangements = PreEventShiftGeometry10868.readoutArrangements(accessibilitySize: typeSize.isAccessibilitySize)
        if arrangements.contains(.sideBySide) {
            ViewThatFits(in: .horizontal) {
                readoutGroup(row, .sideBySide, accent: accent)
                readoutGroup(row, .stacked, accent: accent)
            }
        } else {
            readoutGroup(row, .stacked, accent: accent)
        }
    }

    private func readoutGroup(_ row: PreEventShiftRow10868, _ arrangement: FieldChooserArrangement10868, accent: Color) -> some View {
        let layout = arrangement == .stacked
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 16))
        return layout {
            ForEach(Array(row.sides.enumerated()), id: \.offset) { _, side in
                readout(row, side, accent: accent)
            }
        }
    }

    @ViewBuilder
    private func readout(_ row: PreEventShiftRow10868, _ side: PreEventShiftSide10868, accent: Color) -> some View {
        let opening = model.openAction(row, side, canOpen: canOpen)
        let content = VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .center, spacing: 6) {
                glyphMark(row.slot.glyph, kind: side.kind, accent: accent)
                Text(FieldChaseModel10868.label(side.endpoint))
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let figure = FieldChaseModel10868.figure(side.endpoint) {
                Text(figure)
                    .font(.system(size: figureSize, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(accent)
                    .fixedSize()
            }
            if let words = FieldChaseModel10868.words(side.endpoint) {
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let line = FieldChaseModel10868.detail(side.endpoint) {
                ownerWords(line)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
        .contentShape(Rectangle())

        if let opening, let onOpen {
            Button {
                onOpen(opening)
            } label: {
                content
            }
            .accessibilityLabel(model.endpointSummary(row, side))
            .accessibilityHint(model.hint(opening))
            .accessibilityIdentifier(PreEventShiftAccessibilityID10868.endpoint(row.slot.ref.outcomeID, side.kind))
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.endpointSummary(row, side))
                .accessibilityIdentifier(PreEventShiftAccessibilityID10868.endpoint(row.slot.ref.outcomeID, side.kind))
        }
    }

    // MARK: Marks

    /// The skater's filled identity glyph, as the main gold history keys it. Decorative.
    private func identityKey(_ glyph: PreEventShiftGlyph10868, accent: Color) -> some View {
        let radius = markRadius * 0.6
        let side = PreEventShiftGeometry10868.markExtent(radius: radius, lineWidth: lineWidth)
        return Canvas { context, size in
            let center = PreEventShiftGeometry10868.center(glyph, in: size, radius: radius)
            context.fill(PreEventShiftGeometry10868.path(glyph, center: center, radius: radius), with: .color(accent))
        }
        .frame(width: side, height: side)
        .accessibilityHidden(true)
    }

    /// The small or large hollow mark exactly as the track draws it. Decorative.
    private func glyphMark(_ glyph: PreEventShiftGlyph10868, kind: PreEventShiftEndpointKind10868, accent: Color) -> some View {
        let large = markRadius
        let radius = kind == .first ? large * PreEventShiftGeometry10868.firstScale : large
        let stroke = lineWidth
        let side = PreEventShiftGeometry10868.markExtent(radius: large, lineWidth: stroke)
        let ringFill = DS.cardBg
        return Canvas { context, size in
            let center = PreEventShiftGeometry10868.center(glyph, in: size, radius: radius)
            let path = PreEventShiftGeometry10868.path(glyph, center: center, radius: radius)
            context.fill(path, with: .color(ringFill))
            context.stroke(path, with: .color(accent), style: PreEventShiftGeometry10868.stroke(lineWidth: stroke))
        }
        .frame(width: side, height: side)
        .accessibilityHidden(true)
    }

    // MARK: Track

    /// The scale line, zero and the owner's ticks, the connector between two
    /// placed marks, then the large and the small hollow marks on top — all
    /// from the shared plan. Above the ceiling, an edge arrow and no mark.
    private func track(_ row: PreEventShiftRow10868, accent: Color) -> some View {
        let lineColor = DS.border
        let ringFill = DS.cardBg
        let radius = markRadius
        let stroke = lineWidth
        let glyph = row.slot.glyph
        let ticks = model.ticks.map(\.fraction)
        let first = row.first?.chance.fraction
        let latest = row.latest?.chance.fraction
        let offScale = row.sides.contains { $0.chance == .offScale }
        // Never shorter than the largest glyph, so a scaled mark is drawn, not dropped.
        let trackSide = max(trackHeight, PreEventShiftGeometry10868.markExtent(radius: radius, lineWidth: stroke))
        return Canvas { context, size in
            guard let plan = PreEventShiftGeometry10868.trackPlan(
                glyph: glyph, first: first, latest: latest, ticks: ticks, in: size,
                radius: radius, lineWidth: stroke, connectorWidth: 3)
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
            // The large mark first, so a concentric small mark stays visible inside it.
            for mark in [plan.latest, plan.first].compactMap({ $0 }) {
                let path = PreEventShiftGeometry10868.path(glyph, center: mark.center, radius: mark.radius)
                context.fill(path, with: .color(ringFill))
                context.stroke(path, with: .color(accent), style: PreEventShiftGeometry10868.stroke(lineWidth: stroke))
            }
        }
        .frame(maxWidth: .infinity, minHeight: trackSide, maxHeight: trackSide)
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
}
