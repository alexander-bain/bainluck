import SwiftUI

// #10868 — the volleyball championship field page (`volleyball-field`): a
// field of independently traded team contracts whose recorded history is the
// whole story. There is no established sporting phase, no current chance and
// no result, so this page says nothing about a phase: it shows the owner's
// neutral recorded-history words, never a pre-season, live, current or
// settled value.
//
// A reader sees, in this order: the owner's title, subtitle and context words
// with a compact About control; each displayed team's dated readouts as the
// history resolves them, each figure at one scaled figure size, each readout
// highlighting its team through the history's own choose action; the named,
// shape-keyed win probability history; then the endpoint card — each
// displayed team's first and last recorded trade in the owner's window, two
// marks on one absolute scale joined by a comparison connector, each figure
// at the same scaled size with its own label and date, and the owner's change
// words — and the entry to every original. The history and the endpoint card
// open full size as the same Views with the same inputs.
//
// Presentation only, from the approved `VolleyballTournament.tsx`,
// `volleyballTournament.css`, `VolleyballMovementCard.tsx`,
// `volleyballMovement.css` and the native readable-composition and
// trade-navigation adoption records. Their capture loader, sampled-team
// election, ceiling rounding, hour list, trade-hour stepping, latest and
// at-hour selection, first/last election, change arithmetic, percentage and
// clock formatting and session state are NOT ported. The leaves are the
// actual accepted Views and types:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor: its runs, gaps,
//     scale control, any-hour inspection, earlier/later controls, highlight
//     and readout resolution (`FieldHistoryGeometry10868`);
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     every original and the held original's Details;
//   • `FieldEventPageMode10868`, `FieldEventPageCard10868`,
//     `FieldEventPageReaderHeader10868`, `FieldEventPageAbout10868`,
//     `FieldEventPageAboutContent10868`, `FieldEventPageOriginals10868` and the
//     field page's hold helpers — the accepted field page's host contract.
//
// Why not the field page itself: its page phase, its headline and its
// endpoint card all require a sporting phase (before, during or final), which
// this archive does not establish; its endpoint card draws pre-event hollow
// marks beside a mandatory phase key, at a smaller figure size and with no
// change words; and its full-size history keeps the page height. The two
// small Views here fill exactly those gaps on the shared resolvers.
//
// Readouts: every slot is `FieldHistoryGeometry10868.readoutSlots` for the
// history copy drawn beside it, with the history's own note, selection and
// choose-control state. A readout acts only while the history's own rules
// make its choose action live, and hands back that exact action id through
// the history callback; otherwise it is static. While no team carries key
// context, a presentation copy of the history hides the shared key so the
// readouts are not shown twice; that copy keeps every series, run, readout,
// inspection, mark-key word, action and plot field, and the owner's history
// input is never changed.
//
// Endpoints: a row names one history series by its exact id; a listed-twice,
// missing or shared id keeps the owner's name beside the unavailable words and
// borrows nothing. Each endpoint is the owner's ONE reading for that series and
// endpoint; it shows a figure and a mark only while it is an observation
// reading bound to one exact point of that same series inside the history's
// domain (`FieldHistoryGeometry10868.display` / `uniquePoint`). The mark sits
// at that point's own raw value on the owner's scale
// (`FieldOutlookGeometry10868.fraction`, `FieldFinishGeometry10868.x`); a value
// above the scale draws no mark, only the owner's off-scale words. The
// connector joins two placed marks only and is not a path between their
// times. The owner's change words appear only while both figures are shown;
// nothing here subtracts, rounds, normalizes or elects an endpoint. Opening an
// endpoint hands back that exact series id and point id.
//
// Heights: the page uses the history's own plot height; full size uses the
// owner's full-size height, never shorter than the page's; at accessibility
// sizes both use the owner's accessibility height when taller. Nothing
// shrinks: figures, names and endpoints reflow instead.
//
// Actions: on the page, each action calls the owner's interaction hook once,
// then the owner's exact callback with its exact value. Full-size content keeps
// the exact callbacks with no hook. Without a callback there is no control and
// no hook call; building or reading the view calls nothing.
//
// Layout: a compact width or an accessibility size stacks the hero above the
// endpoint card and the originals entry; a regular or unspecified width puts
// them side by side while both keep their minimum widths, otherwise stacks.
// The host owns the scroll, navigation, sheets, Back/Done, focus return, reader
// paging, held selection, the inspected hour, the scale choice and every
// update. This view keeps no state, runs no timer and presents nothing.
//
// Host binding still owed — not available at this base: an owner that groups
// the event's originals, admits the sampled histories with their own runs and
// keys, readouts, scale and controls, the first and last readings with their
// change words, every original with its rules, the About text, and maps every
// callback.

// MARK: - Recorded endpoints

/// Which of a series' two recorded trades in the owner's window. Neither is
/// a season-start baseline nor a current chance.
nonisolated enum VolleyballFieldEndpoint10868: Hashable, CaseIterable {
    /// The first recorded trade in the owner's window.
    case first
    /// The last recorded trade in the owner's window.
    case last
}

/// One displayed row, in the owner's order.
nonisolated struct VolleyballFieldEndpointSlot10868: Equatable {
    /// The exact history series this row names.
    let seriesID: String
    /// The owner's whole name, kept beside the unavailable words when the id
    /// does not name exactly one series.
    let name: String
}

/// The owner's one admitted reading for one endpoint of one series.
nonisolated struct VolleyballFieldEndpointReading10868: Equatable {
    let seriesID: String
    let endpoint: VolleyballFieldEndpoint10868
    /// An observation reading bound to one exact point of that series, or the
    /// owner's absence words. An independent reading is never an endpoint.
    let reading: FieldHistoryReading10868
}

/// The owner's change words for one series, never computed here.
nonisolated struct VolleyballFieldEndpointChange10868: Equatable {
    let seriesID: String
    /// The signed figure, verbatim.
    let figure: String
    /// The unit beside it; nil draws none.
    let unit: String?
    /// Fuller spoken words; nil speaks the figure and unit.
    let spoken: String?
}

nonisolated struct VolleyballFieldEndpointsCopy10868: Equatable {
    /// Small words above the title; nil draws none.
    let eyebrow: String?
    let title: String
    /// One line under the title; nil draws none.
    let intro: String?
    /// The first endpoint's label.
    let firstLabel: String
    /// The last endpoint's label.
    let lastLabel: String
    /// An endpoint with no admitted observation reading of its own.
    let endpointUnavailable: String
    /// A figure above the owner's scale.
    let offScale: String
    /// Spoken name of the rows.
    let graphicLabel: String
    /// The words under the rows; nil draws none.
    let note: String?
    /// Spoken hint on an endpoint that opens; nil none.
    let openHint: String?
    /// Spoken label of the full-size control.
    let expandLabel: String
}

nonisolated struct VolleyballFieldEndpointsInput10868: Equatable {
    /// The rows, in the owner's order. Never sorted, filtered or deduplicated here.
    let displayed: [VolleyballFieldEndpointSlot10868]
    let readings: [VolleyballFieldEndpointReading10868]
    let changes: [VolleyballFieldEndpointChange10868]
    /// The owner's one absolute scale for every row.
    let scale: FieldOutlookScale10868
    let copy: VolleyballFieldEndpointsCopy10868
    /// A row whose id names no single series.
    let unavailableWords: String
}

/// What one endpoint of a resolved row shows.
nonisolated struct VolleyballFieldEndpointSide10868: Equatable {
    let endpoint: VolleyballFieldEndpoint10868
    /// The label, then the bound figure with its own provenance, or words.
    let slot: FieldHistoryReadoutSlot10868
    /// The bound point, only while the slot shows its figure.
    let point: FieldHistoryPoint10868?
    /// Where that point's own raw value sits on the owner's scale.
    let chance: FieldOutlookChance10868
}

nonisolated struct VolleyballFieldEndpointRow10868: Equatable {
    let slot: VolleyballFieldEndpointSlot10868
    /// Nil when the row's id names no single series.
    let series: FieldHistorySeries10868?
    let first: VolleyballFieldEndpointSide10868?
    let last: VolleyballFieldEndpointSide10868?

    var sides: [VolleyballFieldEndpointSide10868] { [first, last].compactMap { $0 } }
}

/// Exactly what an endpoint hands back: the series and its exact point.
nonisolated struct VolleyballFieldEndpointOpen10868: Equatable {
    let seriesID: String
    let pointID: String
}

/// What one track draws inside its own rect.
nonisolated struct VolleyballFieldEndpointTrackPlan10868: Equatable {
    let centerY: CGFloat
    let zeroX: CGFloat
    let ceilingX: CGFloat
    let tickXs: [CGFloat]
    /// Between two placed marks only.
    let connector: CGRect?
    let first: CGPoint?
    let last: CGPoint?
}

nonisolated enum VolleyballFieldEndpointsGeometry10868 {
    /// The first mark's radius as a share of the last mark's.
    static let firstScale: CGFloat = 0.6
    /// The widest reach of any history shape, in multiples of its radius.
    static let shapeReach: CGFloat = 1.25

    /// The inset that keeps a large mark at zero or at the ceiling whole.
    static func inset(radius: CGFloat, outline: CGFloat) -> CGFloat {
        FieldExpectationsGeometry10868.inset(markDiameter: 2 * shapeReach * radius + outline)
    }

    /// The one plan every track uses: marks at their own fractions on the
    /// shared inset, a connector only between two placed marks. Nil for a size
    /// that cannot hold a mark.
    static func trackPlan(first: Double?, last: Double?, ticks: [Double], in size: CGSize,
                          radius: CGFloat, outline: CGFloat, connectorWidth: CGFloat) -> VolleyballFieldEndpointTrackPlan10868? {
        let inset = Self.inset(radius: radius, outline: outline)
        guard radius.isFinite, radius > 0, connectorWidth.isFinite, connectorWidth > 0,
              size.height.isFinite, size.height >= 2 * shapeReach * radius,
              let zero = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let ceiling = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset)
        else { return nil }
        let centerY = size.height / 2
        func x(_ fraction: Double?) -> CGFloat? {
            fraction.flatMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) }
        }
        let firstX = x(first)
        let lastX = x(last)
        var connector: CGRect?
        if let start = firstX, let end = lastX, start != end {
            connector = CGRect(x: min(start, end), y: centerY - connectorWidth / 2, width: abs(end - start), height: connectorWidth)
        }
        return VolleyballFieldEndpointTrackPlan10868(
            centerY: centerY, zeroX: zero, ceilingX: ceiling,
            tickXs: ([0] + ticks).compactMap { x($0) }, connector: connector,
            first: firstX.map { CGPoint(x: $0, y: centerY) },
            last: lastX.map { CGPoint(x: $0, y: centerY) })
    }
}

/// The endpoint card's rules, on the history's own identity and points.
nonisolated struct VolleyballFieldEndpointsModel10868: Equatable {
    let input: VolleyballFieldEndpointsInput10868
    /// The history the page shows: identities, points and domain.
    let history: FieldHistoryInput10868

    /// The one series a row names: listed once, carried by exactly one series.
    func series(_ slot: VolleyballFieldEndpointSlot10868) -> FieldHistorySeries10868? {
        guard input.displayed.filter({ $0.seriesID == slot.seriesID }).count == 1,
              let series = history.series.first(where: { $0.id == slot.seriesID }),
              FieldHistoryGeometry10868.isExactlyIdentified(series, in: history)
        else { return nil }
        return series
    }

    var rows: [VolleyballFieldEndpointRow10868] {
        input.displayed.map { slot in
            guard let series = self.series(slot) else {
                return VolleyballFieldEndpointRow10868(slot: slot, series: nil, first: nil, last: nil)
            }
            return VolleyballFieldEndpointRow10868(slot: slot, series: series,
                                                   first: side(.first, of: series), last: side(.last, of: series))
        }
    }

    func label(_ endpoint: VolleyballFieldEndpoint10868) -> String {
        endpoint == .first ? input.copy.firstLabel : input.copy.lastLabel
    }

    /// The owner's one reading for this series and endpoint; several are none.
    func reading(_ endpoint: VolleyballFieldEndpoint10868, of seriesID: String) -> FieldHistoryReading10868? {
        let matches = input.readings.filter { $0.seriesID == seriesID && $0.endpoint == endpoint }
        return matches.count == 1 ? matches[0].reading : nil
    }

    /// A figure only for an observation reading bound to one exact point of
    /// this series inside the history's domain; the owner's absence words as
    /// they are; anything else the copy's words, with no figure or mark.
    func side(_ endpoint: VolleyballFieldEndpoint10868, of series: FieldHistorySeries10868) -> VolleyballFieldEndpointSide10868 {
        let label = self.label(endpoint)
        let unavailable = VolleyballFieldEndpointSide10868(
            endpoint: endpoint, slot: FieldHistoryReadoutSlot10868(label: label, display: .words(input.copy.endpointUnavailable)),
            point: nil, chance: .unavailable)
        switch reading(endpoint, of: series.id) {
        case .absent(let words)?:
            return VolleyballFieldEndpointSide10868(
                endpoint: endpoint, slot: FieldHistoryReadoutSlot10868(label: label, display: .words(words)),
                point: nil, chance: .unavailable)
        case .observation(let pointID, let figure, let provenance)?:
            let reading = FieldHistoryReading10868.observation(pointID: pointID, figure: figure, provenance: provenance)
            guard case .figure = FieldHistoryGeometry10868.display(reading, of: series, in: history),
                  let point = FieldHistoryGeometry10868.uniquePoint(pointID, in: series),
                  history.domain.contains(point.x)
            else { return unavailable }
            return VolleyballFieldEndpointSide10868(
                endpoint: endpoint,
                slot: FieldHistoryReadoutSlot10868(label: label, display: .figure(figure, provenance: provenance)),
                point: point, chance: chance(point.probability))
        case .independent?, nil:
            return unavailable
        }
    }

    /// A bound raw value on the owner's scale: placed, or above the ceiling.
    func chance(_ probability: Double) -> FieldOutlookChance10868 {
        guard input.scale.isValid else { return .unavailable }
        guard let fraction = FieldOutlookGeometry10868.fraction(probability, ceiling: input.scale.ceiling) else {
            return .offScale
        }
        return .value(probability: probability, fraction: fraction)
    }

    /// The owner's one change entry for a resolved row, only while both of its
    /// figures are shown.
    func change(_ row: VolleyballFieldEndpointRow10868) -> VolleyballFieldEndpointChange10868? {
        guard let series = row.series, row.first?.point != nil, row.last?.point != nil else { return nil }
        let matches = input.changes.filter { $0.seriesID == series.id }
        guard matches.count == 1, FieldMovementModel10868.readable(matches[0].figure) != nil else { return nil }
        return matches[0]
    }

    static func spoken(_ change: VolleyballFieldEndpointChange10868) -> String {
        FieldMovementModel10868.readable(change.spoken)
            ?? ([change.figure] + [change.unit].compactMap(FieldMovementModel10868.readable)).joined(separator: " ")
    }

    /// The unavailable words for a row that does not resolve; the off-scale
    /// words beside a figure above the scale.
    func stateWords(_ row: VolleyballFieldEndpointRow10868) -> String? {
        guard row.series != nil else { return input.unavailableWords }
        return row.sides.contains { $0.chance == .offScale } ? input.copy.offScale : nil
    }

    /// Tracks only beside the owner's explicit, valid, worded scale.
    var showsTracks: Bool {
        input.scale.isValid && FieldMovementModel10868.readable(input.scale.words) != nil
    }

    func showsTrack(_ row: VolleyballFieldEndpointRow10868) -> Bool {
        showsTracks && row.series != nil && row.sides.contains { $0.chance != .unavailable }
    }

    var ticks: [FieldOutlookPlacedTick10868] {
        guard showsTracks else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldOutlookGeometry10868.fraction(tick.probability, ceiling: input.scale.ceiling)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    /// The exact series and point while the endpoint shows its figure, only
    /// with a callback, and only for a row and endpoint the current input still
    /// resolves to exactly that. Never another endpoint's point, never a default.
    func openAction(_ row: VolleyballFieldEndpointRow10868, _ side: VolleyballFieldEndpointSide10868,
                    canOpen: Bool) -> VolleyballFieldEndpointOpen10868? {
        guard canOpen, let series = row.series, input.displayed.contains(row.slot),
              self.series(row.slot) == series, self.side(side.endpoint, of: series) == side,
              let point = side.point
        else { return nil }
        return VolleyballFieldEndpointOpen10868(seriesID: series.id, pointID: point.id)
    }

    func hint(_ opening: VolleyballFieldEndpointOpen10868?) -> String {
        opening == nil ? "" : (input.copy.openHint ?? "")
    }

    func name(_ row: VolleyballFieldEndpointRow10868) -> String { row.series?.name ?? row.slot.name }

    /// One endpoint with its whole subject: the name, then its slot in words.
    func endpointSummary(_ row: VolleyballFieldEndpointRow10868, _ side: VolleyballFieldEndpointSide10868) -> String {
        [name(row), FieldHistoryGeometry10868.spokenSlot(side.slot)].joined(separator: ". ")
    }

    /// A row in words, so its track may stay decorative.
    func rowSummary(_ row: VolleyballFieldEndpointRow10868) -> String {
        var parts = [name(row)] + row.sides.map { FieldHistoryGeometry10868.spokenSlot($0.slot) }
        if let change = self.change(row) { parts.append(Self.spoken(change)) }
        if let words = stateWords(row) { parts.append(words) }
        return parts.filter { FieldMovementModel10868.readable($0) != nil }.joined(separator: ". ")
    }
}

nonisolated enum VolleyballFieldAccessibilityID10868 {
    static let page = "volleyballField10868.page"
    static let hero = "volleyballField10868.hero"
    static let readouts = "volleyballField10868.readouts"
    static let anchor = "volleyballField10868.anchor"
    static let endpoints = "volleyballField10868.endpoints"
    static let endpointsExpand = "volleyballField10868.endpoints.expand"
    static let allProps = "volleyballField10868.allProps"
    static let about = "volleyballField10868.about"
    static let readerHeader = "volleyballField10868.readerHeader"
    static let readerAbout = "volleyballField10868.readerHeader.about"
    static let readerUnavailable = "volleyballField10868.reader.unavailable"
    static let catalogue = "volleyballField10868.catalogue"
    static let original = "volleyballField10868.original"
    static let aboutContent = "volleyballField10868.aboutContent"
    static func endpoint(_ seriesID: String, _ endpoint: VolleyballFieldEndpoint10868) -> String {
        "volleyballField10868.endpoint.\(seriesID).\(endpoint == .first ? "first" : "last")"
    }
}

/// The endpoint card: each displayed series' first and last recorded trade.
struct VolleyballFieldEndpointsPresentation10868: View {
    let input: VolleyballFieldEndpointsInput10868
    /// The history the page shows, read for identity and points only.
    let history: FieldHistoryInput10868
    var onOpen: ((VolleyballFieldEndpointOpen10868) -> Void)? = nil
    /// The page's full-size entry; nil full size.
    var onExpand: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = VolleyballFieldEventPageModel10868.figureSize
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 5
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 30
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private let outline: CGFloat = 1.5
    var model: VolleyballFieldEndpointsModel10868 { VolleyballFieldEndpointsModel10868(input: input, history: history) }

    var body: some View {
        let model = self.model
        let rows = model.rows
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    if let eyebrow = FieldMovementModel10868.readable(input.copy.eyebrow) {
                        Text(eyebrow)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Text(input.copy.title)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let onExpand {
                    Button(action: onExpand) {
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.blue)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(input.copy.expandLabel)
                    .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.endpointsExpand)
                }
            }
            if let intro = FieldMovementModel10868.readable(input.copy.intro) {
                ownerWords(intro)
            }
            if rows.contains(where: model.showsTrack) {
                scaleHeader(model)
            }
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    rowView(row, model: model)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.graphicLabel)
            if let note = FieldMovementModel10868.readable(input.copy.note) {
                ownerWords(note)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.endpoints)
    }

    private func scaleHeader(_ model: VolleyballFieldEndpointsModel10868) -> some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 4) {
            if !ticks.isEmpty {
                FieldExpectationsAxisLayout10868(units: ticks.map(\.fraction),
                                                 inset: VolleyballFieldEndpointsGeometry10868.inset(radius: markRadius, outline: outline),
                                                 spacing: 6) {
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
            ownerWords(input.scale.words)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.scale.words)
    }

    @ViewBuilder private func rowView(_ row: VolleyballFieldEndpointRow10868, model: VolleyballFieldEndpointsModel10868) -> some View {
        if let series = row.series {
            let actions = row.sides.map { model.openAction(row, $0, canOpen: onOpen != nil) }
            let content = VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    HStack(alignment: .center, spacing: 6) {
                        glyph(series.shape, tint: series.tint)
                        Text(series.name)
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if let change = model.change(row) {
                        VStack(alignment: .trailing, spacing: 1) {
                            Text(change.figure)
                                .font(.title3.weight(.semibold))
                                .monospacedDigit()
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize()
                            if let unit = FieldMovementModel10868.readable(change.unit) {
                                ownerWords(unit)
                            }
                        }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(VolleyballFieldEndpointsModel10868.spoken(change))
                    }
                }
                endpoints(row, model: model)
                if model.showsTrack(row) {
                    track(row, series: series, model: model)
                }
                if let words = model.stateWords(row) {
                    ownerWords(words)
                }
            }
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }

            if actions.contains(where: { $0 != nil }) {
                content.accessibilityElement(children: .contain).accessibilityLabel(series.name)
            } else {
                content.accessibilityElement(children: .ignore).accessibilityLabel(model.rowSummary(row))
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
            .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.rowSummary(row))
        }
    }

    /// Both endpoints at one figure size: side by side while both fit whole,
    /// else stacked; stacked at accessibility sizes.
    @ViewBuilder private func endpoints(_ row: VolleyballFieldEndpointRow10868, model: VolleyballFieldEndpointsModel10868) -> some View {
        if VolleyballFieldEventPageModel10868.slotArrangements(accessibilitySize: typeSize.isAccessibilitySize).contains(.sideBySide) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) { sides(row, model: model) }
                VStack(alignment: .leading, spacing: 10) { sides(row, model: model) }
            }
        } else {
            VStack(alignment: .leading, spacing: 10) { sides(row, model: model) }
        }
    }

    @ViewBuilder private func sides(_ row: VolleyballFieldEndpointRow10868, model: VolleyballFieldEndpointsModel10868) -> some View {
        ForEach(Array(row.sides.enumerated()), id: \.offset) { _, side in
            endpoint(row, side, model: model)
        }
    }

    @ViewBuilder private func endpoint(_ row: VolleyballFieldEndpointRow10868, _ side: VolleyballFieldEndpointSide10868,
                                       model: VolleyballFieldEndpointsModel10868) -> some View {
        let opening = model.openAction(row, side, canOpen: onOpen != nil)
        let content = VolleyballFieldSlotView10868(slot: side.slot, figureSize: figureSize)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
            .contentShape(Rectangle())
        let id = VolleyballFieldAccessibilityID10868.endpoint(row.slot.seriesID, side.endpoint)
        if let opening, let onOpen {
            Button { onOpen(opening) } label: { content }
                .buttonStyle(.plain)
                .accessibilityLabel(model.endpointSummary(row, side))
                .accessibilityHint(model.hint(opening))
                .accessibilityIdentifier(id)
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.endpointSummary(row, side))
                .accessibilityIdentifier(id)
        }
    }

    /// The scale line and ticks, the connector between two placed marks, then
    /// the large last mark and the small first mark on top. Decorative.
    private func track(_ row: VolleyballFieldEndpointRow10868, series: FieldHistorySeries10868,
                       model: VolleyballFieldEndpointsModel10868) -> some View {
        let lineColor = DS.border
        let ring = DS.cardBg
        let tint = series.tint
        let shape = series.shape
        let radius = markRadius
        let stroke = outline
        let ticks = model.ticks.map(\.fraction)
        let first = row.first?.chance.fraction
        let last = row.last?.chance.fraction
        let offScale = row.sides.contains { $0.chance == .offScale }
        let side = max(trackHeight, 2 * VolleyballFieldEndpointsGeometry10868.shapeReach * radius + stroke)
        return Canvas { context, size in
            guard let plan = VolleyballFieldEndpointsGeometry10868.trackPlan(
                first: first, last: last, ticks: ticks, in: size, radius: radius, outline: stroke, connectorWidth: 5)
            else { return }
            var line = Path()
            line.move(to: CGPoint(x: plan.zeroX, y: plan.centerY))
            line.addLine(to: CGPoint(x: plan.ceilingX, y: plan.centerY))
            context.stroke(line, with: .color(lineColor), lineWidth: 2)
            for x in plan.tickXs {
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: plan.centerY - 4))
                tick.addLine(to: CGPoint(x: x, y: plan.centerY + 4))
                context.stroke(tick, with: .color(lineColor), lineWidth: 1)
            }
            if let connector = plan.connector {
                context.fill(Path(roundedRect: connector, cornerRadius: connector.height / 2), with: .color(tint.opacity(0.45)))
            }
            if let center = plan.last {
                context.fill(FieldHistoryGeometry10868.markPath(shape, at: center, radius: radius), with: .color(tint))
            }
            if let center = plan.first {
                let mark = FieldHistoryGeometry10868.markPath(shape, at: center, radius: radius * VolleyballFieldEndpointsGeometry10868.firstScale)
                context.stroke(mark, with: .color(ring), lineWidth: stroke * 2)
                context.fill(mark, with: .color(tint))
            }
        }
        .frame(maxWidth: .infinity, minHeight: side, maxHeight: side)
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

    private func glyph(_ shape: FieldHistoryShape10868, tint: Color) -> some View {
        VolleyballFieldGlyph10868(shape: shape, tint: tint, markRadius: markRadius * 0.7)
    }

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Readouts

/// One team in the readouts: the history's own resolution for it.
nonisolated struct VolleyballFieldReadoutEntry10868: Equatable {
    let series: FieldHistorySeries10868
    let note: String?
    let slots: [FieldHistoryReadoutSlot10868]
    let isSelected: Bool
    /// The history's own choose-control state for this series.
    let choose: FieldHistoryControlState10868
}

/// Each displayed team's readouts exactly as the history resolves them, each
/// figure at one scaled size under its own label with its own date. A readout
/// highlights its team only through the history's own live choose action.
/// Teams sit side by side while every measured figure fits an equal share,
/// else one full-width row each; accessibility sizes go straight to rows.
struct VolleyballFieldReadoutsPresentation10868: View {
    /// The history copy drawn beside it.
    let history: FieldHistoryInput10868
    /// Spoken name of the readouts.
    let label: String
    /// The history's action callback for a live choose id; nil: static.
    var onChoose: ((String) -> Void)? = nil

    static let spacing: CGFloat = 8
    static let padding: CGFloat = 8

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = VolleyballFieldEventPageModel10868.figureSize
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 3.5
    /// Two lines of a name, so figures line up in columns.
    @ScaledMetric(relativeTo: .subheadline) private var nameHeight: CGFloat = 40

    var entries: [VolleyballFieldReadoutEntry10868] {
        history.series.map {
            VolleyballFieldReadoutEntry10868(
                series: $0,
                note: FieldHistoryGeometry10868.keyNote($0, in: history),
                slots: FieldHistoryGeometry10868.readoutSlots($0, in: history),
                isSelected: FieldHistoryGeometry10868.isSelected($0, in: history),
                choose: FieldHistoryGeometry10868.chooseState($0, hasCallback: onChoose != nil, in: history))
        }
    }

    /// The live choose id a readout hands back, while its action is available.
    static func chooseID(_ entry: VolleyballFieldReadoutEntry10868) -> String? {
        guard case .live(let id) = entry.choose, entry.series.choose?.isAvailable == true else { return nil }
        return id
    }

    static func spoken(_ entry: VolleyballFieldReadoutEntry10868) -> String {
        ([entry.series.name] + [entry.note].compactMap(FieldMovementModel10868.readable)
            + entry.slots.map(FieldHistoryGeometry10868.spokenSlot))
            .joined(separator: ". ")
    }

    /// Every figure the entries draw, measured whole by hidden copies.
    static func figures(_ entries: [VolleyballFieldReadoutEntry10868]) -> [String] {
        entries.flatMap(\.slots).compactMap {
            guard case .figure(let figure, _) = $0.display else { return nil }
            return figure
        }
    }

    var body: some View {
        let entries = self.entries
        if !entries.isEmpty {
            FieldHeadlineCompetitorsLayout10868(count: entries.count, spacing: Self.spacing, rowSpacing: Self.spacing,
                                                accessibilitySize: typeSize.isAccessibilitySize) {
                ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                    entryControl(entry)
                }
                ForEach(Array(Self.figures(entries).enumerated()), id: \.offset) { _, figure in
                    VolleyballFieldSlotView10868.figureText(figure, size: figureSize)
                        .padding(Self.padding).hidden().accessibilityHidden(true)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(label)
            .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.readouts)
        }
    }

    @ViewBuilder private func entryControl(_ entry: VolleyballFieldReadoutEntry10868) -> some View {
        if case .live(let id) = entry.choose, let onChoose, let choose = entry.series.choose {
            Button { onChoose(id) } label: { entryView(entry) }
                .buttonStyle(.plain)
                .disabled(!choose.isAvailable)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Self.spoken(entry))
                .accessibilityHint(choose.spokenLabel ?? choose.label)
                .accessibilityAddTraits(entry.isSelected ? .isSelected : [])
        } else {
            entryView(entry)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Self.spoken(entry))
                .accessibilityAddTraits(entry.isSelected ? .isSelected : [])
        }
    }

    private func entryView(_ entry: VolleyballFieldReadoutEntry10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 6) {
                VolleyballFieldGlyph10868(shape: entry.series.shape, tint: entry.series.tint, markRadius: markRadius)
                Text(entry.series.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(entry.series.tint)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(minHeight: typeSize.isAccessibilitySize ? 0 : nameHeight, alignment: .topLeading)
            if let note = FieldMovementModel10868.readable(entry.note) {
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if VolleyballFieldEventPageModel10868.slotArrangements(accessibilitySize: typeSize.isAccessibilitySize).contains(.sideBySide) {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { slots(entry) }
                    VStack(alignment: .leading, spacing: 8) { slots(entry) }
                }
            } else {
                VStack(alignment: .leading, spacing: 8) { slots(entry) }
            }
        }
        .padding(Self.padding)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 10).fill(entry.isSelected ? DS.surface : Color.clear))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(entry.isSelected ? DS.textSecondary : Color.clear, lineWidth: 1))
        .contentShape(Rectangle())
    }

    @ViewBuilder private func slots(_ entry: VolleyballFieldReadoutEntry10868) -> some View {
        ForEach(Array(entry.slots.enumerated()), id: \.offset) { _, slot in
            VolleyballFieldSlotView10868(slot: slot, figureSize: figureSize)
        }
    }
}

// MARK: - Shared small leaves

/// One slot: its label, then its figure at the one scaled size with its own
/// provenance, or its words at a smaller size in the figure's height.
struct VolleyballFieldSlotView10868: View {
    let slot: FieldHistoryReadoutSlot10868
    let figureSize: CGFloat

    static func figureText(_ figure: String, size: CGFloat) -> some View {
        Text(figure)
            .font(.system(size: size, weight: .semibold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(slot.label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            switch slot.display {
            case .figure(let figure, let provenance):
                Self.figureText(figure, size: figureSize)
                Text(provenance)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .words(let words):
                Text(words)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(minHeight: figureSize * 1.2, alignment: .leading)
            }
        }
    }
}

/// The history's own identity: a short solid line through the series' mark.
struct VolleyballFieldGlyph10868: View {
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
            context.fill(FieldHistoryGeometry10868.markPath(shape, at: middle, radius: markRadius * 1.3), with: .color(tint))
        }
        .frame(width: markRadius * 7, height: markRadius * 4.5)
        .accessibilityHidden(true)
    }
}

// MARK: - Page input

/// The owner's words at the top of the page.
nonisolated struct VolleyballFieldEventPageHeader10868: Equatable {
    let title: String
    /// Nil draws none.
    let subtitle: String?
    /// The owner's neutral recorded-history words; nil draws none.
    let context: String?
    /// The owner's label for a constructed example; nil draws none.
    var notice: String? = nil
}

nonisolated struct VolleyballFieldEventPageCopy10868: Equatable {
    /// Spoken name of the readouts.
    let readoutsLabel: String
    /// The About control's spoken label.
    let aboutLabel: String
    let aboutHint: String?
    /// The entry to every original; nil draws none.
    let allPropsLabel: String?
    /// Full-size content for a card this page does not show.
    let readerUnavailable: String
}

nonisolated struct VolleyballFieldEventPageInput10868: Equatable {
    let header: VolleyballFieldEventPageHeader10868
    let reader: FieldEventPageReaderHeader10868
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; never shorter than the page's.
    var readerPlotHeight: CGFloat? = nil
    /// The owner's plot height at accessibility sizes, used when taller.
    var accessibilityPlotHeight: CGFloat? = nil
    /// The endpoint card; nil: no card.
    let endpoints: VolleyballFieldEndpointsInput10868?
    let about: FieldEventPageAbout10868?
    let copy: VolleyballFieldEventPageCopy10868
}

// MARK: - Page model

/// What the page mounts and draws, resolved once per input.
nonisolated struct VolleyballFieldEventPageModel10868: Equatable {
    let input: VolleyballFieldEventPageInput10868

    init(_ input: VolleyballFieldEventPageInput10868) {
        self.input = input
    }

    /// Every readout and endpoint figure, before Dynamic Type scaling.
    static let figureSize: CGFloat = 26

    /// Slots side by side where they fit whole, else stacked; stacked at
    /// accessibility sizes.
    static func slotArrangements(accessibilitySize: Bool) -> [FieldChooserArrangement10868] {
        FieldChaseGeometry10868.stacksReadouts(accessibilitySize: accessibilitySize) ? [.stacked] : [.sideBySide, .stacked]
    }

    /// The plot height: the page's own; full size, the owner's full-size height
    /// when taller; at accessibility sizes, the owner's accessibility height
    /// when taller. Unusable owner heights are ignored; an unusable page height
    /// is kept for the history's own fallback when nothing else is usable.
    static func plotHeight(page: CGFloat, reader owner: CGFloat?, accessibility: CGFloat?,
                           isReader: Bool, accessibilitySize: Bool) -> CGFloat {
        func usable(_ height: CGFloat?) -> CGFloat? {
            guard let height, height.isFinite, height > 0 else { return nil }
            return height
        }
        let heights = [usable(page), isReader ? usable(owner) : nil, accessibilitySize ? usable(accessibility) : nil]
        return heights.compactMap { $0 }.max() ?? page
    }

    /// Whether the readouts stand in for the shared key: while no series
    /// carries key context, the key would show only the readouts and their
    /// choose controls, which the readouts carry. Otherwise the key stays.
    var hidesSharedKey: Bool {
        input.history.series.allSatisfy { FieldHistoryGeometry10868.keyContext($0) == nil }
    }

    /// A presentation copy of the owner's history: every field exactly as
    /// supplied, with only the given height, expand control and key visibility.
    static func presentationCopy(_ history: FieldHistoryInput10868, plotHeight: CGFloat,
                                 expand: FieldHistoryAction10868?, showsKey: Bool) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: showsKey
        )
    }

    /// The history the page or full size draws, and its readouts read.
    func history(reader: Bool, accessibilitySize: Bool) -> FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(
            history,
            plotHeight: Self.plotHeight(page: history.plotHeight, reader: input.readerPlotHeight,
                                        accessibility: input.accessibilityPlotHeight,
                                        isReader: reader, accessibilitySize: accessibilitySize),
            expand: reader ? nil : history.expand,
            showsKey: hidesSharedKey ? false : history.showsKey)
    }

    func isMounted(_ card: FieldEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .movement: input.endpoints != nil
        case .field: false
        }
    }

    var about: FieldEventPageAbout10868? {
        guard let about = input.about,
              FieldEventPageModel10868.readable(about.title) != nil
                || about.paragraphs.contains(where: { FieldEventPageModel10868.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool { canOpen && about != nil }

    /// Full-size content's compact heading shows the About entry; the page has its own.
    func aboutEntry(mode: FieldEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, FieldEventPageModel10868.readable(input.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && FieldEventPageModel10868.readable(input.copy.allPropsLabel) != nil
    }
}

// MARK: - Page view

struct VolleyballFieldEventPagePresentation10868: View {
    let input: VolleyballFieldEventPageInput10868
    var mode: FieldEventPageMode10868 = .page
    /// Every original and the held original's Details; nil: neither.
    var originals: FieldEventPageOriginals10868? = nil
    var onAbout: (() -> Void)? = nil
    var onAllProps: (() -> Void)? = nil
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// Every history action id, including a readout's choose id.
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    var onEndpointOpen: ((VolleyballFieldEndpointOpen10868) -> Void)? = nil
    /// Opens the host's reader on a card.
    var onReaderOpen: ((FieldEventPageCard10868) -> Void)? = nil
    /// Called once before a page, catalogue or Details action reaches its owner.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var columnMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: VolleyballFieldEventPageModel10868 { VolleyballFieldEventPageModel10868(input) }

    private func held<Value>(_ action: ((Value) -> Void)?, reader: Bool) -> ((Value) -> Void)? {
        FieldEventPagePresentation10868.held(action, by: reader ? nil : onInteraction)
    }

    // MARK: Leaves — the actual Views with the host's own callbacks

    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The readouts over the history copy the same content draws.
    func readoutsContent(reader: Bool, accessibilitySize: Bool) -> VolleyballFieldReadoutsPresentation10868 {
        VolleyballFieldReadoutsPresentation10868(
            history: model.history(reader: reader, accessibilitySize: accessibilitySize),
            label: input.copy.readoutsLabel, onChoose: held(onHistoryAction, reader: reader))
    }

    func historyContent(reader: Bool, accessibilitySize: Bool) -> FieldProbabilityHistoryPresentation10868 {
        FieldProbabilityHistoryPresentation10868(
            input: model.history(reader: reader, accessibilitySize: accessibilitySize),
            onAction: held(onHistoryAction, reader: reader),
            onInspectionChoice: held(onHistoryInspectionChoice, reader: reader),
            onPlotPosition: held(onHistoryPlotPosition, reader: reader))
    }

    /// The same card and input full size, without its full-size entry.
    func endpointsContent(reader: Bool) -> VolleyballFieldEndpointsPresentation10868? {
        guard let endpoints = input.endpoints else { return nil }
        let expand: (() -> Void)? = onReaderOpen.map { opener in { opener(.movement) } }
        return VolleyballFieldEndpointsPresentation10868(
            input: endpoints, history: input.history,
            onOpen: held(onEndpointOpen, reader: reader),
            onExpand: reader ? nil : FieldEventPagePresentation10868.heldAction(expand, by: onInteraction))
    }

    func aboutContent() -> FieldEventPageAboutContent10868? {
        model.about.map { FieldEventPageAboutContent10868(about: $0) }
    }

    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: held(onOriginalSelect, reader: false))
        }
    }

    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: held(onOriginalHistory, reader: false))
        }
    }

    /// The page's About control, after the hook.
    func openPageAbout() {
        FieldEventPagePresentation10868.heldAction(aboutOpener(), by: onInteraction)?()
    }

    /// Full-size content's About: the exact callback.
    func openAbout() {
        aboutOpener()?()
    }

    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        FieldEventPagePresentation10868.heldAction(onAllProps, by: onInteraction)?()
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Page

    private var page: some View {
        Group {
            let arrangements = FieldEventPageModel10868.arrangements(sizeClass: sizeClass,
                                                                     accessibilitySize: typeSize.isAccessibilitySize)
            if arrangements == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    sideBySide
                    stacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.page)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            secondary
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 22) {
            hero.frame(minWidth: columnMinWidth, maxWidth: .infinity, alignment: .topLeading).layoutPriority(1)
            secondary.frame(minWidth: columnMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            readoutsContent(reader: false, accessibilitySize: typeSize.isAccessibilitySize)
            historyContent(reader: false, accessibilitySize: typeSize.isAccessibilitySize)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.anchor)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(VolleyballFieldCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.hero)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text(input.header.title)
                    .font(.title.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array([input.header.subtitle, input.header.notice].compactMap(FieldEventPageModel10868.readable).enumerated()),
                        id: \.offset) { _, words in
                    Text(words)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let context = FieldEventPageModel10868.readable(input.header.context) {
                    Text(context)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutAvailable(canOpen: onAbout != nil) {
                aboutButton(action: openPageAbout, id: VolleyballFieldAccessibilityID10868.about)
            }
        }
    }

    private var secondary: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let endpoints = endpointsContent(reader: false) {
                endpoints
                    .padding(16)
                    .modifier(VolleyballFieldCardSurface10868())
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
                Button(action: openAllProps) {
                    HStack(spacing: 8) {
                        Text(label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "chevron.right")
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .padding(.horizontal, 16)
                    .frame(minHeight: controlSize)
                    .modifier(VolleyballFieldCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.allProps)
            }
        }
    }

    private func aboutButton(action: @escaping () -> Void, id: String) -> some View {
        Button(action: action) {
            Image(systemName: "info.circle")
                .font(.title3)
                .foregroundStyle(DS.textPrimary)
                .frame(minWidth: controlSize, minHeight: controlSize)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(input.copy.aboutLabel)
        .accessibilityHint(input.copy.aboutHint ?? "")
        .accessibilityIdentifier(id)
    }

    // MARK: Full size

    /// The same Views and inputs, full size, under the compact words. A card
    /// this page does not show keeps the owner's unavailable words.
    private func reader(_ card: FieldEventPageCard10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            if model.isMounted(card) {
                switch card {
                case .history:
                    readoutsContent(reader: true, accessibilitySize: typeSize.isAccessibilitySize)
                    historyContent(reader: true, accessibilitySize: typeSize.isAccessibilitySize)
                case .movement:
                    endpointsContent(reader: true)
                case .field:
                    EmptyView()
                }
            } else {
                Text(input.copy.readerUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.readerUnavailable)
            }
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = FieldEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                aboutButton(action: openAbout, id: VolleyballFieldAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.readerHeader)
    }

    // MARK: Every original, the held original's Details and About

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(VolleyballFieldAccessibilityID10868.aboutContent)
        }
    }
}

/// The reference's white card on the page surface.
private struct VolleyballFieldCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
