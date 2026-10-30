import SwiftUI

// #10868 — "Chance → result": the shared required final-story card of the
// rugby-match page and the chance-to-result part of the afl-match page. A fan
// compares one named team's win chance before the match with one later
// recorded reading (the owner's checkpoint, "Lowest minute-end chance" on both
// approved pages: the lowest captured minute-end reading, not the lowest trade
// inside a minute): two equally readable figures, each beside its own label and
// its own clock, then two labelled zero-based bars on ONE common 0–100% scale —
// an outline bar for the earlier and a filled bar for the later — and below
// them, in a clearly separate panel, the separately reported actual final score.
//
// Presentation only, from the approved `RugbyMatch.tsx` `story` card
// (`.rg-story`, `.rg-expectation`, `.rg-track`, `.rg-winner`, larger-text
// variants) and the `AflQuarterCard.tsx` `.afl-low` chance-to-result section
// (`aflMatch.css`), as mounted inline and in the match-story reader. The
// references' baseline election (last positive-volume candle before the listed
// start), lowest minute-end election, percent and clock formatting, score
// text and winner words (`rugbyMatchEvidence.ts`, `aflBrisbaneContext.ts`) are
// NOT ported. All of that arrives as owner input: the canonical catalogue, the one
// subject with its whole name, each endpoint's separately admitted reading, the
// raw observations tied to those readings with their opaque keys, the reported
// actual tied to the same original, the explicit phase, the common scale with
// its tick labels and every label and absence word.
//
// Identity goes through the chooser's own `FieldChooserModel10868`. A subject
// that does not resolve to exactly one record in the same scope — missing,
// withdrawn, out of scope, duplicated or blank — keeps the owner's name beside
// the unavailable words, and every slot keeps its label with the copy's words:
// no figure, bar, actual or action is borrowed from another original.
//
// Each endpoint is its own subject, on the pre-event shift card's rule: its
// figure is the owner's ONE admitted reading for that exact original and
// endpoint, shown only while the owner's ONE observation for the same original
// and endpoint carries that reading (label, figure and clock line) and a raw
// value that is a probability (`FieldChaseModel10868.qualified`). The owner's
// absence words show as they are; anything else shows the copy's words with no
// figure, bar or key. The two observations are independently timed: never
// interpolated, normalized, complemented or put on a shared clock. The before
// figure is the last admitted trade before the LISTED start, not a verified
// kickoff or an opening or closing chance; the checkpoint is one dated
// historical reading (one captured minute-end value), never current and never
// a verified chance at a scoring moment. A missing endpoint keeps its labelled
// slot and the rest of the story.
//
// The actual result is a different fact. It is the owner's one reported-final
// association for the same exact original (`FieldFinishPlace10868`: label,
// whole score and source line, or the owner's absence words) plus the owner's
// outcome words, shown verbatim in its own panel and never on the probability
// scale. It is never derived from a chance, the original's contract result,
// the catalogue's result, movement or preview, or a position; "won" is never
// 100%. A missing actual keeps its panel with the copy's words and removes no
// chance; missing chances remove no actual.
//
// Each bar starts at zero and ends at its own raw value's exact fraction of the
// owner's scale (`FieldOutlookGeometry10868.markPlan`), on the same inset x as
// the ticks and the measured axis labels (`FieldFinishGeometry10868.x`,
// `FieldExpectationsAxisLayout10868`). The outline's ink is clipped to its own
// bar's extent, so a tiny chance is never drawn wider or taller than it is. A
// genuine 0% is a thin zero mark and a genuine 100% reaches the ceiling. A
// value above the ceiling draws no bar, only an edge arrow and the owner's
// off-scale words; a missing, untied or invalid value draws no bar; an invalid
// scale draws no plot at all. No line joins the two dates; the bars are a
// comparison, not a history.
//
// The phase is the owner's explicit input. Only at the final is there a card:
// before and during there are no words, artwork, result or actions, even when
// final fields ride along. The bars are decorative: the readouts speak the
// whole subject, both labelled chances with their own clocks, and the actual
// panel speaks the reported score. Each shown figure with its own key hands
// back the exact original and that key to the host's history reader; the
// full-card entry and Details hand back nothing but the tap. With no callback,
// nothing pretends to act. The host owns the reader, scroll, Done/Back, focus
// and held snapshots; this leaf keeps no state and runs no animation. The same
// content is mounted inline and in the full-size reader; only the full-card
// entry is the inline card's.
//
// Host binding still owed — not available at this base: the match-winner
// originals mapped through Native's existing production identity path (a
// provider ticker, a name or an index is never a link), the subject team, its
// admitted before-listed-start and checkpoint readings with their own clocks
// and observation keys, the reported final score with its source tied to that
// original, the phase, scale and copy.

/// Which of the subject's two compared observations.
nonisolated enum HistoricalChanceEndpointKind10868: Hashable, CaseIterable {
    /// The last admitted trade before the listed start. Not a verified kickoff,
    /// opening or closing chance.
    case before
    /// The owner's one later historical reading (on the approved pages, the
    /// lowest captured minute-end chance — a minute's close, not its
    /// intraminute low). Never current, never elected here.
    case checkpoint
}

/// The one team the card is about.
nonisolated struct HistoricalChanceSubject10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's whole name, kept beside the unavailable words when the
    /// subject does not resolve.
    let name: String
}

/// The owner's separately admitted reading for one endpoint of one original.
nonisolated struct HistoricalChanceReading10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let endpoint: HistoricalChanceEndpointKind10868
    /// "Before match", `.recorded("81%", "Mar 14, 8:08 PM GMT · Kalshi")`, or
    /// the owner's absence words.
    let reading: FieldChooserReading10868
}

/// One raw observation, tied to the reading the owner formatted from it.
nonisolated struct HistoricalChanceObservation10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let endpoint: HistoricalChanceEndpointKind10868
    let observation: FieldMovementObservation10868
    /// The owner's opaque key for this observation, handed back unchanged on
    /// open. Never read.
    let key: String
}

/// The owner's reported actual for one original. Never a chance.
nonisolated struct HistoricalChanceActual10868: Equatable {
    /// "Reported final score": `.recorded("France 48–46 England", "ESPN final
    /// header")` or the owner's absence words, tied to the exact original.
    let place: FieldFinishPlace10868
    /// The owner's outcome words ("France won"); nil draws none.
    let outcome: String?
}

/// The owner's words for this card.
nonisolated struct HistoricalChanceCopy10868: Equatable {
    /// "FRANCE’S CHANGING CHANCE"; nil draws none.
    let eyebrow: String?
    /// "A favourite. Traded at 2%. Still the winner."
    let title: String
    /// Label of a before endpoint that cannot be shown ("Before match").
    let beforeLabel: String
    /// Label of a checkpoint that cannot be shown ("Lowest minute-end chance").
    let checkpointLabel: String
    /// An endpoint not tied to this card ("Not recorded for this comparison").
    let endpointUnavailable: String
    /// "Outline: last trade before the listed start".
    let beforeKey: String
    /// "Filled: a later recorded trade".
    let checkpointKey: String
    /// Spoken name of the two chances.
    let graphicLabel: String
    /// A chance with no bar on this scale ("Not drawn on this scale").
    let chanceUnplaced: String
    /// A chance above the ceiling ("Above this scale").
    let offScale: String
    /// "ACTUAL RESULT".
    let actualTitle: String
    /// Label of an actual that cannot be shown ("Reported final score").
    let actualLabel: String
    /// "Final score not confirmed". Required: an unknown result never vanishes.
    let actualUnavailable: String
    /// "Each chance is one dated trade; the score was reported separately"; nil draws none.
    let context: String?
    /// Spoken name of the full-card entry ("Open France’s chance story full size").
    let expandLabel: String
    let expandHint: String?
    /// "How to read this story"; nil draws no Details control.
    let detailsLabel: String?
    let detailsHint: String?
    /// Spoken hint on an endpoint that opens; nil none.
    let openHint: String?
}

nonisolated struct HistoricalChanceInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original, shown or not.
    let catalogue: [FieldChooserOriginal10868]
    let subject: HistoricalChanceSubject10868
    let readings: [HistoricalChanceReading10868]
    let observations: [HistoricalChanceObservation10868]
    let actuals: [HistoricalChanceActual10868]
    /// The owner's one scale for both bars (0–100%: ceiling 1).
    let scale: FieldOutlookScale10868
    let phase: FieldOutlookPhase10868
    let copy: HistoricalChanceCopy10868
    /// A subject that does not resolve ("Team unavailable in this update").
    let unavailableWords: String
}

/// What one endpoint shows.
nonisolated struct HistoricalChanceSide10868: Equatable {
    let kind: HistoricalChanceEndpointKind10868
    /// The admitted reading while tied, its own absence words, or the copy's words.
    let endpoint: FieldMovementEndpoint10868
    /// Where the tied raw chance sits on the scale.
    let chance: FieldOutlookChance10868
    /// The tied observation's own key while its figure is shown; never the other endpoint's.
    let key: String?
}

/// What one bar Canvas draws inside its own rect.
nonisolated struct HistoricalChanceBarPlan10868: Equatable {
    /// Zero to ceiling, the whole height: the empty track.
    let track: CGRect
    /// Zero and every owner tick on the scale.
    let tickXs: [CGFloat]
    /// The checkpoint's filled bar from zero; nil draws none.
    let fill: CGRect?
    /// The rect the before bar's outline is stroked on; nil draws none.
    let outline: CGRect?
    /// The before bar's true extent from zero — the same rect a filled bar of
    /// that value would be — and the outline's ink bound: the Canvas clips the
    /// outline to it. A bar too thin or too short for the inward stroke is inked
    /// over its own extent and never past it; nothing widens a tiny chance.
    let outlineBounds: CGRect?
    /// A genuine 0%: a thin mark on the zero edge.
    let zeroMark: CGRect?
}

nonisolated enum HistoricalChanceGeometry10868 {
    /// Half the outline and a hair, so an outline bar at the ceiling stays whole:
    /// the expectations card's own inset rule.
    static func inset(lineWidth: CGFloat) -> CGFloat {
        FieldExpectationsGeometry10868.inset(markDiameter: lineWidth)
    }

    /// The one drawing plan both bar Canvases use: the outlook's horizontal
    /// mark plan between the inset zero and ceiling x — the same x as the ticks
    /// and axis labels. Nil for a size that cannot be drawn; no bar for a
    /// missing, off-scale or invalid fraction — never clamped.
    static func barPlan(
        kind: HistoricalChanceEndpointKind10868,
        fraction: Double?,
        ticks: [Double],
        in size: CGSize,
        lineWidth: CGFloat
    ) -> HistoricalChanceBarPlan10868? {
        let inset = Self.inset(lineWidth: lineWidth)
        guard lineWidth.isFinite, lineWidth > 0, size.height.isFinite, size.height > 0,
              let zero = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let ceiling = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset)
        else { return nil }
        let mark = FieldOutlookGeometry10868.markPlan(
            fraction: fraction, in: CGSize(width: ceiling - zero, height: size.height),
            orientation: .horizontal, selected: false)
        let bar = mark.fill?.offsetBy(dx: zero, dy: 0)
        return HistoricalChanceBarPlan10868(
            track: CGRect(x: zero, y: 0, width: ceiling - zero, height: size.height),
            tickXs: ([0] + ticks).compactMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) },
            fill: kind == .checkpoint ? bar : nil,
            outline: kind == .before ? bar.map { Self.outline($0, lineWidth: lineWidth) } : nil,
            outlineBounds: kind == .before ? bar : nil,
            zeroMark: mark.zeroMark?.offsetBy(dx: zero, dy: 0)
        )
    }

    /// The rect an outline is stroked on so its ink stays inside the bar's own
    /// extent. A bar too thin or too short for that is stroked on itself, and
    /// only the bar's own extent (`outlineBounds`) keeps that stroke's ink.
    static func outline(_ bar: CGRect, lineWidth: CGFloat) -> CGRect {
        let inner = bar.insetBy(dx: lineWidth / 2, dy: lineWidth / 2)
        return !inner.isNull && inner.width > 0 && inner.height > 0 ? inner : bar
    }

    /// The two chances side by side while both keep their whole width, else
    /// stacked; at accessibility sizes stacked straight away.
    static func readoutArrangements(accessibilitySize: Bool) -> [FieldChooserArrangement10868] {
        FieldChaseGeometry10868.stacksReadouts(accessibilitySize: accessibilitySize) ? [.stacked] : [.sideBySide, .stacked]
    }

    /// The outcome words beside the whole score while both fit unshrunk, else
    /// the score above the outcome; at accessibility sizes stacked straight away.
    /// With no outcome words the score stands alone.
    static func actualArrangements(accessibilitySize: Bool, hasOutcome: Bool) -> [FieldChooserArrangement10868] {
        guard hasOutcome else { return [.stacked] }
        return FieldChaseGeometry10868.stacksReadouts(accessibilitySize: accessibilitySize) ? [.stacked] : [.sideBySide, .stacked]
    }
}

/// The card's rules, resolved once per input, on the chooser's own resolver.
nonisolated struct HistoricalChanceModel10868: Equatable {
    let input: HistoricalChanceInput10868
    /// The chooser's resolver.
    let field: FieldChooserModel10868

    init(_ input: HistoricalChanceInput10868) {
        self.input = input
        // Only what the chooser's resolver reads; no chooser section is drawn
        // and nothing is selected.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope,
            intro: nil,
            featured: FieldChooserFeatured10868(
                title: input.copy.title, badge: nil,
                refs: [input.subject.ref], emptyWords: input.unavailableWords
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
    }

    /// Only at the final: before and during there are no words, artwork,
    /// result or actions.
    var isShown: Bool { input.phase == .final }

    var eyebrow: String? { isShown ? FieldMovementModel10868.readable(input.copy.eyebrow) : nil }

    var title: String? { isShown ? FieldMovementModel10868.readable(input.copy.title) : nil }

    var context: String? { isShown ? FieldMovementModel10868.readable(input.copy.context) : nil }

    // MARK: Subject

    var resolution: FieldChooserResolution10868 { isShown ? field.resolve(input.subject.ref) : .unavailable }

    var original: FieldChooserOriginal10868? { resolution.original }

    /// The resolved original's whole name, else the owner's name beside the
    /// unavailable words.
    var subjectName: String? {
        guard isShown else { return nil }
        return original?.name ?? FieldMovementModel10868.readable(input.subject.name)
    }

    /// The unavailable words, only for a subject that does not resolve.
    var subjectWords: String? { isShown && original == nil ? input.unavailableWords : nil }

    // MARK: Chances

    /// Both labelled slots at the final, in this order; each in words when it
    /// cannot be shown. Nothing before or during.
    var sides: [HistoricalChanceSide10868] {
        guard isShown else { return [] }
        guard let original else { return HistoricalChanceEndpointKind10868.allCases.map(unavailableSide) }
        return HistoricalChanceEndpointKind10868.allCases.map { side($0, for: original.ref) }
    }

    /// The owner's one admitted reading for this exact original and endpoint;
    /// several, even identical, are none.
    func admitted(_ kind: HistoricalChanceEndpointKind10868, for ref: FieldChooserOriginalRef10868) -> FieldChooserReading10868? {
        let matches = input.readings.filter { $0.ref == ref && $0.endpoint == kind }
        return matches.count == 1 ? matches[0].reading : nil
    }

    /// The owner's one observation for this exact original and endpoint;
    /// several, even identical, are none.
    func observation(_ kind: HistoricalChanceEndpointKind10868, for ref: FieldChooserOriginalRef10868) -> HistoricalChanceObservation10868? {
        let matches = input.observations.filter { $0.ref == ref && $0.endpoint == kind }
        return matches.count == 1 ? matches[0] : nil
    }

    func label(_ kind: HistoricalChanceEndpointKind10868) -> String {
        kind == .before ? input.copy.beforeLabel : input.copy.checkpointLabel
    }

    func unavailableSide(_ kind: HistoricalChanceEndpointKind10868) -> HistoricalChanceSide10868 {
        HistoricalChanceSide10868(
            kind: kind,
            endpoint: .unavailable(label: label(kind), words: input.copy.endpointUnavailable),
            chance: .unavailable,
            key: nil
        )
    }

    /// The admitted reading while its own observation is tied and qualified;
    /// the owner's absence words as they are; otherwise the copy's words.
    func side(_ kind: HistoricalChanceEndpointKind10868, for ref: FieldChooserOriginalRef10868) -> HistoricalChanceSide10868 {
        guard let reading = admitted(kind, for: ref) else { return unavailableSide(kind) }
        guard case .recorded = reading.value else {
            return HistoricalChanceSide10868(kind: kind, endpoint: .reading(reading), chance: .unavailable, key: nil)
        }
        guard let tied = observation(kind, for: ref),
              let qualified = FieldChaseModel10868.qualified(tied.observation),
              qualified.reading == reading
        else { return unavailableSide(kind) }
        return HistoricalChanceSide10868(
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

    /// The words under a slot that draws no bar.
    func barWords(_ side: HistoricalChanceSide10868) -> String? {
        switch side.chance {
        case .value: return nil
        case .offScale: return input.copy.offScale
        case .unavailable: return input.copy.chanceUnplaced
        }
    }

    // MARK: Scale

    /// The bars are drawn only beside the owner's explicit scale — a valid
    /// scale and its readable words — and while one chance is placed or above
    /// the ceiling. Never a bare plot.
    var showsPlot: Bool {
        isShown && input.scale.isValid && FieldMovementModel10868.readable(input.scale.words) != nil
            && sides.contains { $0.chance != .unavailable }
    }

    /// The owner's ticks that sit on the scale, in the owner's order.
    var ticks: [FieldOutlookPlacedTick10868] {
        guard showsPlot else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldOutlookGeometry10868.fraction(tick.probability, ceiling: input.scale.ceiling)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    // MARK: Actual

    /// The owner's one reported-actual association for this exact original;
    /// several, even identical, are none.
    func association(for ref: FieldChooserOriginalRef10868) -> HistoricalChanceActual10868? {
        let matches = input.actuals.filter { $0.place.ref == ref }
        return matches.count == 1 ? matches[0] : nil
    }

    /// The reported score as it is, the owner's absence words as they are, or —
    /// missing, duplicated, blank, foreign or for an unresolved subject — the
    /// copy's words. Never the catalogue's result; never a chance.
    var actual: FieldMovementEndpoint10868? {
        guard isShown else { return nil }
        let unavailable = FieldMovementEndpoint10868.unavailable(label: input.copy.actualLabel, words: input.copy.actualUnavailable)
        guard let original, let reading = association(for: original.ref)?.place.reading else { return unavailable }
        switch reading.value {
        case .recorded(let text, _):
            return FieldMovementModel10868.readable(text) == nil ? unavailable : .reading(reading)
        case .missing(let words):
            return FieldMovementModel10868.readable(words) == nil ? unavailable : .reading(reading)
        }
    }

    /// The owner's outcome words, only beside the same association's shown reading.
    var outcome: String? {
        guard let original, case .reading? = actual else { return nil }
        return FieldMovementModel10868.readable(association(for: original.ref)?.outcome)
    }

    // MARK: Actions

    /// The exact original and this endpoint's own key while its figure is
    /// shown — only with a callback, at the final, while this input still
    /// resolves the subject to that original and its current endpoint of that
    /// kind is exactly `side`. A side from an earlier input or a withdrawn
    /// original opens nothing. No other endpoint's key, no default.
    func openAction(_ side: HistoricalChanceSide10868, canOpen: Bool) -> FieldMovementOpen10868? {
        guard canOpen, isShown, let original,
              field.resolve(input.subject.ref) == .original(original),
              self.side(side.kind, for: original.ref) == side,
              let key = side.key, case .reading(let reading) = side.endpoint, case .recorded = reading.value
        else { return nil }
        return FieldMovementOpen10868(ref: original.ref, observation: key)
    }

    /// The owner's open hint, only on a control that acts.
    func hint(_ opening: FieldMovementOpen10868?) -> String {
        opening == nil ? "" : (input.copy.openHint ?? "")
    }

    /// The full-card entry: only with a callback, at the final, with its name.
    func showsExpand(canExpand: Bool) -> Bool {
        canExpand && isShown && FieldMovementModel10868.readable(input.copy.expandLabel) != nil
    }

    /// The owner's Details control: only with a callback, at the final, with its name.
    func detailsLabel(canShowDetails: Bool) -> String? {
        guard canShowDetails, isShown else { return nil }
        return FieldMovementModel10868.readable(input.copy.detailsLabel)
    }

    // MARK: VoiceOver

    /// One endpoint with its whole subject: the full name, then the labelled
    /// chance with its own clock, or its words.
    func endpointSummary(_ side: HistoricalChanceSide10868) -> String {
        [subjectName, FieldMovementModel10868.spoken(side.endpoint), side.chance == .offScale ? input.copy.offScale : nil]
            .compactMap { FieldMovementModel10868.readable($0) }
            .joined(separator: ". ")
    }

    /// The chances in the owner's words, so the bars may stay decorative: the
    /// full name, any unavailable words, both chances with their own clocks.
    var chancesSummary: String {
        guard isShown else { return "" }
        let spoken: [String?] = sides.map { FieldMovementModel10868.spoken($0.endpoint) }
        var parts = [subjectName, subjectWords] + spoken
        if sides.contains(where: { $0.chance == .offScale }) { parts.append(input.copy.offScale) }
        return parts.compactMap { FieldMovementModel10868.readable($0) }.joined(separator: ". ")
    }

    /// The separately reported actual: its title, the reading or words, the outcome.
    var actualSummary: String {
        guard let actual else { return "" }
        return [input.copy.actualTitle, FieldMovementModel10868.spoken(actual), outcome]
            .compactMap { FieldMovementModel10868.readable($0) }
            .joined(separator: ". ")
    }

    /// The whole card, for a static card read as one element.
    var summary: String {
        guard isShown else { return "" }
        return [eyebrow, title, chancesSummary, actualSummary, context]
            .compactMap { FieldMovementModel10868.readable($0) }
            .joined(separator: ". ")
    }
}

nonisolated enum HistoricalChanceAccessibilityID10868 {
    static let card = "historicalChance10868.card"
    static let expand = "historicalChance10868.expand"
    static let chances = "historicalChance10868.chances"
    static let plot = "historicalChance10868.plot"
    static let actual = "historicalChance10868.actual"
    static let details = "historicalChance10868.details"
    static func endpoint(_ kind: HistoricalChanceEndpointKind10868) -> String {
        "historicalChance10868.endpoint.\(kind == .before ? "before" : "checkpoint")"
    }
}

struct HistoricalChanceResultPresentation10868: View {
    let input: HistoricalChanceInput10868
    var onOpen: ((FieldMovementOpen10868) -> Void)?
    var onExpand: (() -> Void)?
    var onDetails: (() -> Void)?
    private let model: HistoricalChanceModel10868

    init(
        input: HistoricalChanceInput10868,
        onOpen: ((FieldMovementOpen10868) -> Void)? = nil,
        onExpand: (() -> Void)? = nil,
        onDetails: (() -> Void)? = nil
    ) {
        self.input = input
        self.onOpen = onOpen
        self.onExpand = onExpand
        self.onDetails = onDetails
        self.model = HistoricalChanceModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    /// Both chances at this one size; never shrunk to fit.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 26
    @ScaledMetric(relativeTo: .title2) private var scoreSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var barHeight: CGFloat = 12

    private let lineWidth: CGFloat = 2
    private var canOpen: Bool { onOpen != nil }
    private var isStatic: Bool { onOpen == nil && onExpand == nil && onDetails == nil }
    private var inset: CGFloat { HistoricalChanceGeometry10868.inset(lineWidth: lineWidth) }
    private var accent: Color { model.original?.accent ?? DS.blue }

    var body: some View {
        if model.isShown {
            let card = VStack(alignment: .leading, spacing: 12) {
                header
                subject
                readouts
                if model.showsPlot {
                    plot
                }
                actualPanel
                if let context = model.context {
                    ownerWords(context)
                }
                if let label = model.detailsLabel(canShowDetails: onDetails != nil), let onDetails {
                    Button(label) { onDetails() }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                        .accessibilityHint(input.copy.detailsHint ?? "")
                        .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.details)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)

            if isStatic {
                card
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(model.summary)
                    .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.card)
            } else {
                card
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.card)
            }
        }
    }

    // MARK: Header and subject

    /// The wrapping eyebrow and title, and the full-card entry only with a callback.
    private var header: some View {
        HStack(alignment: .top, spacing: 8) {
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
                        .accessibilityAddTraits(.isHeader)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.showsExpand(canExpand: onExpand != nil), let onExpand {
                Button {
                    onExpand()
                } label: {
                    Image(systemName: "arrow.up.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel(input.copy.expandLabel)
                .accessibilityHint(input.copy.expandHint ?? "")
                .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.expand)
            }
        }
    }

    @ViewBuilder private var subject: some View {
        if let name = model.subjectName {
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.headline)
                    .foregroundStyle(model.original == nil ? DS.textSecondary : DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let words = model.subjectWords {
                    ownerWords(words)
                }
            }
        } else if let words = model.subjectWords {
            ownerWords(words)
        }
    }

    // MARK: Readouts

    /// Both chances at the same figure size, each beside its own bar swatch,
    /// label and clock; side by side while both keep their width, else stacked.
    @ViewBuilder private var readouts: some View {
        let sides = model.sides
        let actions = sides.map { model.openAction($0, canOpen: canOpen) }
        let arrangements = HistoricalChanceGeometry10868.readoutArrangements(accessibilitySize: typeSize.isAccessibilitySize)
        let group = Group {
            if arrangements.contains(.sideBySide) {
                ViewThatFits(in: .horizontal) {
                    readoutGroup(sides, .sideBySide)
                    readoutGroup(sides, .stacked)
                }
            } else {
                readoutGroup(sides, .stacked)
            }
        }
        if actions.contains(where: { $0 != nil }) {
            group
                .accessibilityElement(children: .contain)
                .accessibilityLabel(input.copy.graphicLabel)
                .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.chances)
        } else {
            group
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.chancesSummary)
                .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.chances)
        }
    }

    private func readoutGroup(_ sides: [HistoricalChanceSide10868], _ arrangement: FieldChooserArrangement10868) -> some View {
        let layout = arrangement == .stacked
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 12))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 16))
        return layout {
            ForEach(Array(sides.enumerated()), id: \.offset) { _, side in
                readout(side)
            }
        }
    }

    @ViewBuilder
    private func readout(_ side: HistoricalChanceSide10868) -> some View {
        let opening = model.openAction(side, canOpen: canOpen)
        let content = VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .center, spacing: 6) {
                swatch(side.kind)
                Text(FieldChaseModel10868.label(side.endpoint))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let figure = FieldChaseModel10868.figure(side.endpoint) {
                Text(figure)
                    .font(.system(size: figureSize, weight: .bold))
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
            .accessibilityLabel(model.endpointSummary(side))
            .accessibilityHint(model.hint(opening))
            .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.endpoint(side.kind))
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.endpointSummary(side))
                .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.endpoint(side.kind))
        }
    }

    // MARK: Plot

    /// The owner's scale words and the outline/filled key, both labelled bars
    /// on one inset, then the measured tick labels. Decorative: the readouts
    /// speak every value.
    private var plot: some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 8) {
            Text(input.scale.words)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { barKeys }
                VStack(alignment: .leading, spacing: 4) { barKeys }
            }
            ForEach(Array(model.sides.enumerated()), id: \.offset) { _, side in
                barRow(side, ticks: ticks.map(\.fraction))
            }
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
        .accessibilityHidden(true)
        .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.plot)
    }

    @ViewBuilder private var barKeys: some View {
        barKey(.before, words: input.copy.beforeKey)
        barKey(.checkpoint, words: input.copy.checkpointKey)
    }

    private func barKey(_ kind: HistoricalChanceEndpointKind10868, words: String) -> some View {
        HStack(spacing: 6) {
            swatch(kind)
            ownerWords(words)
        }
    }

    private func barRow(_ side: HistoricalChanceSide10868, ticks: [Double]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                swatch(side.kind)
                Text(FieldChaseModel10868.label(side.endpoint))
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if case .value = side.chance {
                bar(side, ticks: ticks)
            } else if let words = model.barWords(side) {
                HStack(spacing: 6) {
                    if side.chance == .offScale {
                        Image(systemName: "arrow.right.to.line")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DS.textSecondary)
                    }
                    ownerWords(words)
                }
            }
        }
    }

    /// The empty track, zero and the owner's ticks, then the bar from zero —
    /// outlined for the earlier trade, filled for the later — all from the
    /// shared plan.
    private func bar(_ side: HistoricalChanceSide10868, ticks: [Double]) -> some View {
        let kind = side.kind
        let fraction = side.chance.fraction
        let color = accent
        let trackColor = DS.trackBg
        let tickColor = DS.border
        let ringFill = DS.cardBg
        let stroke = lineWidth
        return Canvas { context, size in
            guard let plan = HistoricalChanceGeometry10868.barPlan(
                kind: kind, fraction: fraction, ticks: ticks, in: size, lineWidth: stroke)
            else { return }
            context.fill(Path(plan.track), with: .color(trackColor))
            for x in plan.tickXs {
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: plan.track.minY))
                tick.addLine(to: CGPoint(x: x, y: plan.track.maxY))
                context.stroke(tick, with: .color(tickColor), lineWidth: 1)
            }
            if let fill = plan.fill {
                context.fill(Path(fill), with: .color(color))
            }
            if let outline = plan.outline, let bounds = plan.outlineBounds {
                var ink = context
                ink.clip(to: Path(bounds))
                ink.fill(Path(outline), with: .color(ringFill))
                ink.stroke(Path(outline), with: .color(color), lineWidth: stroke)
            }
            if let zero = plan.zeroMark {
                context.fill(Path(zero), with: .color(color))
            }
        }
        .frame(maxWidth: .infinity, minHeight: barHeight, maxHeight: barHeight)
    }

    // MARK: Actual

    /// A clearly separate panel: the title, the reading's label, the whole
    /// reported score beside or above the outcome words, and its source line.
    private var actualPanel: some View {
        let actual = model.actual
        let outcome = model.outcome
        let arrangements = HistoricalChanceGeometry10868.actualArrangements(
            accessibilitySize: typeSize.isAccessibilitySize, hasOutcome: outcome != nil)
        return VStack(alignment: .leading, spacing: 6) {
            Text(input.copy.actualTitle)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let actual {
                Text(FieldChaseModel10868.label(actual))
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let score = FieldChaseModel10868.figure(actual) {
                    if arrangements.contains(.sideBySide), let outcome {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 12) {
                                outcomeText(outcome).fixedSize()
                                Spacer(minLength: 0)
                                scoreText(score).fixedSize()
                            }
                            stackedActual(score, outcome)
                        }
                    } else {
                        stackedActual(score, outcome)
                    }
                } else if let words = FieldChaseModel10868.words(actual) {
                    Text(words)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let outcome {
                        outcomeText(outcome)
                    }
                }
                if let line = FieldChaseModel10868.detail(actual) {
                    ownerWords(line)
                }
            }
        }
        .padding(.top, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.actualSummary)
        .accessibilityIdentifier(HistoricalChanceAccessibilityID10868.actual)
    }

    private func stackedActual(_ score: String, _ outcome: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            scoreText(score).fixedSize(horizontal: false, vertical: true)
            if let outcome {
                outcomeText(outcome)
            }
        }
    }

    private func scoreText(_ score: String) -> some View {
        Text(score)
            .font(.system(size: scoreSize, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
    }

    private func outcomeText(_ outcome: String) -> some View {
        Text(outcome)
            .font(.headline)
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Shared pieces

    /// The outline or filled bar in miniature, so the meaning never rests on colour. Decorative.
    private func swatch(_ kind: HistoricalChanceEndpointKind10868) -> some View {
        let color = accent
        let ringFill = DS.cardBg
        let stroke = lineWidth
        return Canvas { context, size in
            let rect = CGRect(origin: .zero, size: size)
            if kind == .checkpoint {
                context.fill(Path(rect), with: .color(color))
            } else {
                let outline = HistoricalChanceGeometry10868.outline(rect, lineWidth: stroke)
                context.fill(Path(outline), with: .color(ringFill))
                context.stroke(Path(outline), with: .color(color), lineWidth: stroke)
            }
        }
        .frame(width: 18, height: 10)
        .accessibilityHidden(true)
    }

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}
