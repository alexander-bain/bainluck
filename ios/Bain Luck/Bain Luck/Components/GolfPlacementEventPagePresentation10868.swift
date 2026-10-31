import SwiftUI

// #10868 — the golf TOP-10 PLACEMENT final page: a finished placement market
// ("finishes in the top 10, ties included") read after the final round. A fan
// sees one golfer's own dated pre-event placement chance beside that original's
// own admitted placement result; that golfer's recorded chance history as the
// anchor, with its readout (pre-event chance, result, separately reported score
// and round count, and Details); and the expectations map: every placed
// original's own pre-event chance on one common 0–100% scale, inside the result
// band its own admitted result names, so a fan can compare which expectations
// held up across the field. Every original stays reachable through the finite
// golfer chooser and All props.
//
// Presentation only, from the approved placement final composition and its
// archive golfer chooser (visual and semantic references only). Their evidence
// loader, baseline cutoff and validity rule, known-baseline sort, ceiling
// ladder, segment and gap policy, band function, page arithmetic, probability,
// score and clock formatting, map offsets and mark labels, scale toggle state,
// catalogue session and sheets are NOT ported. All of that is the owner's input.
//
// Why a new composition: the golf winner archive page requires round-score
// stories and winner semantics; the golf page always mounts its fixed finish
// slots (win and several finish ranges) and its finish card; the pre-tournament
// golf page and the field page carry no admitted result per original and no
// second, independent golfer selection. Nothing existing places pre-event
// chances inside separate result bands.
//
// What is mounted, unchanged:
//   • `FieldPhaseHeadlinePresentation10868` — the hero: the owner's eyebrow,
//     title and About entry, the owner's golfer with that original's own dated
//     pre-event figure and its separately admitted placement result, and the
//     owner's state words. Mounted only while its own phase is the final;
//     otherwise the owner's words.
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, on a
//     presentation copy that changes only its height (the finite, never-shorter
//     full-size height from `RugbyMatchEventPageModel10868.readerPlotHeight`)
//     and its expand control (`VolleyballFieldEventPageModel10868.presentationCopy`).
//     Its runs, gaps, hollow/filled marks, range choices and inspection are
//     the owner's.
//   • `FieldContenderChooserPresentation10868` with the pre-tournament golf
//     page's chooser hierarchy (`GolfPreTournamentChooserNavigation10868`, its
//     model and its presentation), carried in the golf winner archive page's
//     public `GolfWinnerArchiveChooser10868` — one chooser per selection role,
//     each with its own owner modes, bands and pages, never one button per group.
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     every original, the held original's Details and rules.
//   • `StoryStreamPresentationView10868` — the story stream; a card's own
//     actions request the stream's interaction first.
//   • `FieldEventPageAboutContent10868`, `FieldEventPageReaderHeader10868`,
//     `FieldEventPageOriginals10868` and the field page's hold helpers and
//     arrangement rule.
//
// Built here, because nothing existing draws it: the placement map leaf
// (`GolfPlacementMapPresentation10868`) — the owner's result bands, in the
// owner's order, each with its own label and known-count words; inside each,
// one mark per placed original at its own raw pre-event chance on the common
// 0–100% scale and at the owner's vertical offset, which only separates
// overlapping marks and carries no probability, rank or performance magnitude.
// The highlighted and owner-labelled marks are annotated with their golfer and
// figure in a measured lane above the marks. Composed with it: the golfer
// readout and the chooser entry, resolved through the chooser's exact identity
// resolver, and Previous/Next in the owner's reader order.
//
// Truth: every figure, date, band, count, result, score, round count and word
// is the owner's, shown verbatim. A mark is drawn only for an original that
// resolves exactly once, is listed on the map exactly once, whose raw chance is
// a probability tied to its OWN dated before reading (the outlook card's rule),
// whose band is listed exactly once with a valid span holding the offset, and
// whose own admitted result is exactly the band's. Everything else stays
// reachable but is not drawn — never a zero, a neighbour, a complement or a
// settlement. This layer never formats a probability, a clock or a score,
// never elects or normalizes a baseline, never infers a result from a chance,
// a score, a round count or a settlement price, never sorts or ranks, and never
// reads a placement as a tournament win. Independent chances stay independent.
//
// Selections: the history golfer and the map golfer are two separate owner
// selections. Each resolves by exact identity through the chooser's own
// resolver — a missing, foreign, duplicated or withdrawn identity shows the
// owner's unavailable words, never a neighbour — and each role's chooser and
// callbacks carry its role, so acting in one never touches the other. A mark
// chooses only its own canonical original: a tap chooses the drawn mark whose
// centre is uniquely closest within the target reach — the dot touched; an
// exact tie or a tap out of reach chooses nothing. Only drawn marks are
// candidates. Inspecting the history changes nothing in the hero, the map or
// a readout.
//
// Actions: on the page, an action outside the stream calls the owner's
// interaction hook once, then the exact callback with its exact value; a story
// card's own action requests the stream's interaction instead (that request
// is the hold). The chooser, the catalogue and Details content are held the
// same way. Full-size content keeps the exact callbacks with no hold. Without
// a callback there is no control; building or laying out calls nothing.
//
// Layout: phone stacks the hero above the history, then the stories; a regular
// or unspecified width places the hero beside the history and the map beside
// its readout while each keeps its minimum width; accessibility sizes always
// stack. Marks, bands and annotations grow with Dynamic Type and never
// shrink. The highlighted mark and the owner's labelled marks carry an
// annotation — the golfer's name (the owner's compact name, else the whole
// name) over the original's own figure — measured, wrapped and stacked in rows
// above the marks so none overlaps or clips; marks never move. Every action
// is at least 44pt.
//
// The host owns the scroll, sheets, navigation, Back/Done, focus, swipe, the
// held selections, held and received frames, pausing, arrivals, ranking and
// every update. This view keeps no state, runs no timer or animation, holds no
// subscription and presents nothing of its own.

// MARK: - Placement map

/// One result band of the map, in the owner's top-to-bottom order.
nonisolated struct GolfPlacementMapBand10868: Equatable {
    /// The owner's exact band id, named by each point.
    let id: String
    /// The band's whole label.
    let label: String
    /// The owner's known-count words under the label; nil draws none.
    let count: String?
    /// The exact admitted result every member's own original carries. A point
    /// whose original carries another result, or none, is not drawn here.
    let result: FieldChooserResult10868
    /// The owner's band coordinates: a member's offset lies in `lower...upper`.
    /// They only separate overlapping marks — never a probability, a rank or a score.
    let lower: Double
    let upper: Double

    var isValid: Bool { lower.isFinite && upper.isFinite && lower < upper }
}

/// One original the owner places on the map.
nonisolated struct GolfPlacementMapPoint10868: Equatable {
    /// The original's own raw pre-event chance, tied to the before reading the
    /// owner formatted from the same dated observation.
    let chance: FieldOutlookBeforeChance10868
    /// The id of the band the original's own admitted result names.
    let band: String
    /// The owner's vertical offset, in band coordinates.
    let offset: Double
    /// Annotates the mark with its golfer and figure even when it is not
    /// highlighted. The highlighted mark is always annotated.
    var labelled: Bool = false
    /// The owner's compact name for the annotation; nil or blank prints the
    /// original's whole name. Never derived here.
    var label: String? = nil
}

nonisolated struct GolfPlacementMapCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    let caption: String?
    /// Spoken name of the whole map.
    let graphicLabel: String
    /// The axis words under the map; nil draws none.
    let axis: String?
    /// The held map original resolves but has no placed mark.
    let unplaced: String
    /// Shown instead of the map when the map is not at its own final phase.
    let withheld: String
    /// The footer note; nil draws none.
    let note: String?
    let previousLabel: String
    let nextLabel: String
    /// Spoken hint on a mark or step that chooses.
    let chooseHint: String?
}

nonisolated struct GolfPlacementMapInput10868: Equatable {
    /// The map's own explicit phase. Results are drawn at the final only.
    let phase: FieldOutlookPhase10868
    let bands: [GolfPlacementMapBand10868]
    /// In the owner's order. Never sorted, capped or deduplicated here.
    let points: [GolfPlacementMapPoint10868]
    /// The owner's ticks on the common 0–100% scale, with their labels.
    let ticks: [FieldOutlookTick10868]
    /// The owner's held map original — independent of the history golfer.
    let selected: FieldChooserOriginalRef10868?
    /// The owner's reader order for Previous/Next; empty offers neither.
    let traversal: [FieldChooserOriginalRef10868]
    let copy: GolfPlacementMapCopy10868
}

/// One drawn mark.
nonisolated struct GolfPlacementMapMark10868: Equatable {
    let original: FieldChooserOriginal10868
    let point: GolfPlacementMapPoint10868
    /// The band's index in the owner's order.
    let band: Int
    /// The raw pre-event chance: the mark's place on the common 0–100% scale.
    let x: Double
    /// The offset's place inside its band: 0 at the band's foot, 1 at its head.
    let level: Double
    /// The original's own before figure, verbatim.
    let figure: String
    /// The annotation's name: the owner's compact name, else the whole name.
    let name: String
    let isSelected: Bool

    /// Annotated with its name and figure: the highlighted mark and the owner's labelled marks.
    var isAnnotated: Bool { isSelected || point.labelled }
}

/// A mark at its centre inside one band's strip.
nonisolated struct GolfPlacementMapPlacedMark10868: Equatable {
    let mark: GolfPlacementMapMark10868
    let center: CGPoint
}

/// One annotation asking for room in its band's annotation lane.
nonisolated struct GolfPlacementMapAnnotation10868: Equatable {
    /// Its mark's x on the common scale, in the lane.
    let x: CGFloat
    /// Its measured size at the lane's widest annotation.
    let size: CGSize
    /// The highlighted mark's annotation: placed first, nearest the marks.
    let required: Bool
}

/// Where every annotation of one band goes: one rect each, in input order,
/// none overlapping, all inside the lane.
nonisolated struct GolfPlacementMapLanePlan10868: Equatable {
    let rects: [CGRect]
    /// The lane's whole height, so nothing is clipped.
    let height: CGFloat
}

/// What the map draws, resolved once per input.
nonisolated struct GolfPlacementMapModel10868: Equatable {
    let input: GolfPlacementMapInput10868
    /// The chooser's own resolver over the page's canonical catalogue.
    let field: FieldChooserModel10868

    init(_ input: GolfPlacementMapInput10868, scope: String, catalogue: [FieldChooserOriginal10868],
         unavailableWords: String) {
        self.input = input
        // Only the resolver is read: no chooser section is drawn from it and nothing is selected.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: scope, intro: nil,
            featured: FieldChooserFeatured10868(title: input.copy.title, badge: nil, refs: [], emptyWords: unavailableWords),
            context: nil, more: nil, browse: nil, catalogue: catalogue, frame: nil, selected: nil,
            unavailableWords: unavailableWords, chooseHint: nil))
    }

    /// Results are drawn at the map's own final phase only — never coerced from another.
    var isFinal: Bool { input.phase == .final }

    /// The bands drawn: the owner's, in order, at the final; none otherwise.
    var bands: [GolfPlacementMapBand10868] { isFinal ? input.bands : [] }

    /// The held map original, through the same exact resolver; nil when none
    /// is held or it does not resolve.
    var selectedRef: FieldChooserOriginalRef10868? {
        input.selected.flatMap { field.resolve($0).original?.ref }
    }

    /// The original's own figure, only while the raw chance belongs to it, is a
    /// probability and is tied to its own recorded before reading. A missing
    /// before reading has no figure — never a zero.
    static func figure(_ chance: FieldOutlookBeforeChance10868, for original: FieldChooserOriginal10868) -> String? {
        guard chance.ref == original.ref,
              chance.reading == FieldOutlookModel10868.beforeReading(original.plan),
              case .recorded(let text, _) = chance.reading.value,
              chance.probability.isFinite, chance.probability >= 0, chance.probability <= 1
        else { return nil }
        return text
    }

    /// The offset's place inside a valid band, or nil outside it.
    static func level(_ offset: Double, in band: GolfPlacementMapBand10868) -> Double? {
        guard band.isValid, offset.isFinite, offset >= band.lower, offset <= band.upper else { return nil }
        return (offset - band.lower) / (band.upper - band.lower)
    }

    /// Every drawn mark, in the owner's order.
    var marks: [GolfPlacementMapMark10868] {
        guard isFinal else { return [] }
        var bandCounts: [String: Int] = [:]
        for band in input.bands { bandCounts[band.id, default: 0] += 1 }
        var pointCounts: [FieldChooserOriginalRef10868: Int] = [:]
        for point in input.points { pointCounts[point.chance.ref, default: 0] += 1 }
        let selected = selectedRef
        return input.points.compactMap { point -> GolfPlacementMapMark10868? in
            guard pointCounts[point.chance.ref] == 1,
                  let original = field.resolve(point.chance.ref).original,
                  bandCounts[point.band] == 1,
                  let index = input.bands.firstIndex(where: { $0.id == point.band }),
                  original.result == input.bands[index].result,
                  let level = Self.level(point.offset, in: input.bands[index]),
                  let figure = Self.figure(point.chance, for: original)
            else { return nil }
            return GolfPlacementMapMark10868(original: original, point: point, band: index, x: point.chance.probability,
                                             level: level, figure: figure,
                                             name: FieldEventPageModel10868.readable(point.label) ?? original.name,
                                             isSelected: original.ref == selected)
        }
    }

    func marks(inBand index: Int) -> [GolfPlacementMapMark10868] {
        marks.filter { $0.band == index }
    }

    /// The highlighted mark: the held original's own, or none.
    var highlighted: GolfPlacementMapMark10868? {
        marks.first(where: \.isSelected)
    }

    /// The words under the readout while the held original resolves but has
    /// no drawn mark, at the final.
    var notice: String? {
        guard isFinal, selectedRef != nil, highlighted == nil else { return nil }
        return input.copy.unplaced
    }

    /// The owner's ticks that sit on the common scale, in the owner's order.
    var ticks: [FieldOutlookTick10868] {
        input.ticks.filter { $0.probability.isFinite && $0.probability >= 0 && $0.probability <= 1 }
    }

    // MARK: Previous / next

    /// The original beside the held one in the owner's reader order. The held
    /// original and its neighbour must each be listed exactly once and the
    /// neighbour must resolve; otherwise none — never the next one along.
    func neighbour(_ step: FieldOutlookStep10868) -> FieldChooserOriginal10868? {
        guard let selected = selectedRef else { return nil }
        let order = input.traversal
        let positions = order.indices.filter { order[$0] == selected }
        guard positions.count == 1 else { return nil }
        let index = positions[0] + step.offset
        guard order.indices.contains(index) else { return nil }
        let ref = order[index]
        guard order.filter({ $0 == ref }).count == 1 else { return nil }
        return field.resolve(ref).original
    }

    // MARK: Words

    /// A mark in VoiceOver words: its own name, its own dated reading and its own result.
    func spoken(_ mark: GolfPlacementMapMark10868) -> String {
        var parts = [mark.original.name, FieldChooserModel10868.spoken(mark.point.chance.reading)]
        if let result = mark.original.result { parts.append("\(result.title): \(result.words)") }
        return parts.joined(separator: ". ")
    }

    /// A band in VoiceOver words: its label and the owner's count words.
    static func bandSpoken(_ band: GolfPlacementMapBand10868) -> String {
        ([band.label] + [FieldEventPageModel10868.readable(band.count)].compactMap { $0 }).joined(separator: ". ")
    }
}

/// Where marks and figures sit inside a band's strip.
nonisolated enum GolfPlacementMapGeometry10868 {
    /// The x of a raw chance on the common 0–100% scale; nil off the scale.
    static func x(_ probability: Double, in rect: CGRect) -> CGFloat? {
        guard probability.isFinite, probability >= 0, probability <= 1,
              rect.width.isFinite, rect.width >= 0 else { return nil }
        return rect.minX + rect.width * CGFloat(probability)
    }

    /// The y of a level: the band's head at the top of `rect`.
    static func y(_ level: Double, in rect: CGRect) -> CGFloat {
        rect.maxY - rect.height * CGFloat(min(max(level, 0), 1))
    }

    /// The same x across a width whose scale is inset at both ends — the
    /// strip, the annotation lane and the axis share it.
    static func x(_ probability: Double, width: CGFloat, inset: CGFloat) -> CGFloat? {
        x(probability, in: CGRect(x: inset, y: 0, width: max(0, width - 2 * inset), height: 0))
    }

    /// Where centres may go: inset by the largest mark so every mark stays inside.
    static func markArea(_ strip: CGRect, radius: CGFloat) -> CGRect {
        let vertical = radius + 2
        return CGRect(x: strip.minX + radius, y: strip.minY + vertical,
                      width: max(0, strip.width - 2 * radius), height: max(0, strip.height - 2 * vertical))
    }

    /// Each mark at its centre, in order; a mark off the scale is not placed.
    static func placed(_ marks: [GolfPlacementMapMark10868], in area: CGRect) -> [GolfPlacementMapPlacedMark10868] {
        marks.compactMap { mark in
            x(mark.x, in: area).map { GolfPlacementMapPlacedMark10868(mark: mark, center: CGPoint(x: $0, y: y(mark.level, in: area))) }
        }
    }

    /// The one drawn mark a tap chooses: of the marks whose target circle
    /// holds the location, the one whose centre is uniquely closest — the dot
    /// actually touched. Two equally close centres, or none in reach: nothing.
    /// Only drawn marks are candidates, so a missing, foreign, duplicated or
    /// unplaced original is never chosen this way.
    static func hit(_ location: CGPoint, centers: [CGPoint], radius: CGFloat) -> Int? {
        guard radius.isFinite, radius > 0, location.x.isFinite, location.y.isFinite else { return nil }
        var best: (index: Int, distance: CGFloat)?
        var tied = false
        for (index, center) in centers.enumerated() {
            let dx = center.x - location.x
            let dy = center.y - location.y
            let distance = dx * dx + dy * dy
            guard distance.isFinite, distance <= radius * radius else { continue }
            if let current = best {
                if distance < current.distance {
                    best = (index: index, distance: distance)
                    tied = false
                } else if distance == current.distance {
                    tied = true
                }
            } else {
                best = (index: index, distance: distance)
            }
        }
        return tied ? nil : best?.index
    }

    /// Where a band's annotations go, above its marks: each at its measured
    /// size, centred on its own mark's x and kept inside the lane's width.
    /// The highlighted annotation is placed first, then the owner's labelled
    /// ones in the owner's order, each in the lowest row where it overlaps no
    /// other; a crowded annotation moves up a row — never shrunk, dropped,
    /// overlapped or clipped. The lane grows to hold every row. Marks are
    /// never moved.
    static func lane(_ annotations: [GolfPlacementMapAnnotation10868], width: CGFloat,
                     spacing: CGFloat) -> GolfPlacementMapLanePlan10868 {
        guard !annotations.isEmpty else { return GolfPlacementMapLanePlan10868(rects: [], height: 0) }
        let usable = width.isFinite ? max(0, width) : 0
        let gap = spacing.isFinite ? max(0, spacing) : 0
        let spans: [(x: CGFloat, width: CGFloat, height: CGFloat)] = annotations.map { annotation in
            let w = annotation.size.width.isFinite ? min(max(0, annotation.size.width), usable) : 0
            let h = annotation.size.height.isFinite ? max(0, annotation.size.height) : 0
            let center = annotation.x.isFinite ? annotation.x : usable / 2
            return (x: min(max(center - w / 2, 0), usable - w), width: w, height: h)
        }
        let order = annotations.indices.filter { annotations[$0].required }
            + annotations.indices.filter { !annotations[$0].required }
        var rows: [[Int]] = []
        var rowOf = Array(repeating: 0, count: annotations.count)
        for index in order {
            let span = spans[index]
            var row = 0
            while row < rows.count, rows[row].contains(where: { other in
                span.x < spans[other].x + spans[other].width + gap && spans[other].x < span.x + span.width + gap
            }) {
                row += 1
            }
            if row == rows.count { rows.append([]) }
            rows[row].append(index)
            rowOf[index] = row
        }
        let heights = rows.map { row in row.map { spans[$0].height }.max() ?? 0 }
        let total = heights.reduce(0, +) + gap * CGFloat(rows.count)
        // Row 0 sits just above the marks, a gap below it; later rows stack upward.
        var bottoms: [CGFloat] = []
        var bottom = total - gap
        for height in heights {
            bottoms.append(bottom)
            bottom -= height + gap
        }
        let rects = annotations.indices.map { index in
            CGRect(x: spans[index].x, y: bottoms[rowOf[index]] - spans[index].height,
                   width: spans[index].width, height: spans[index].height)
        }
        return GolfPlacementMapLanePlan10868(rects: rects, height: total)
    }

    /// A lane plan read from the other side: rows stack downward, the first
    /// row nearest the marks.
    static func flipped(_ plan: GolfPlacementMapLanePlan10868) -> GolfPlacementMapLanePlan10868 {
        GolfPlacementMapLanePlan10868(
            rects: plan.rects.map { CGRect(x: $0.minX, y: plan.height - $0.maxY, width: $0.width, height: $0.height) },
            height: plan.height)
    }
}

/// The map leaf: the owner's result bands, the placed marks on the common
/// scale and the owner's ticks. The readout, chooser entry and steps are the
/// page's.
struct GolfPlacementMapPresentation10868: View {
    typealias Geometry = GolfPlacementMapGeometry10868
    typealias ID = GolfPlacementAccessibilityID10868

    let model: GolfPlacementMapModel10868
    /// The exact canonical original a mark chooses; nil: every mark is static.
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil

    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 6
    @ScaledMetric(relativeTo: .caption) private var selectedRadius: CGFloat = 9
    @ScaledMetric(relativeTo: .body) private var stripHeight: CGFloat = 88
    /// The widest an annotation grows before its name wraps.
    @ScaledMetric(relativeTo: .caption2) private var annotationMaxWidth: CGFloat = 132
    @ScaledMetric(relativeTo: .body) private var target: CGFloat = 44

    /// Every mark's whole tap target before Dynamic Type scaling.
    static let minimumTarget: CGFloat = 44
    /// The band surface's inner padding; the axis shares it so x lines up.
    static let bandPadding: CGFloat = 10
    /// The gap between annotation rows, and between the lowest row and the marks.
    static let laneSpacing: CGFloat = 4

    /// The exact canonical original a tap at `location` chooses in one band's
    /// strip of `strip` size, by the leaf's own geometry at the given mark
    /// radius and target: the drawn mark whose centre is uniquely closest
    /// within half the target (never less than 44pt across), or nothing.
    static func choice(at location: CGPoint, in strip: CGSize, band index: Int, model: GolfPlacementMapModel10868,
                       radius: CGFloat, target: CGFloat) -> FieldChooserOriginalRef10868? {
        let area = Geometry.markArea(CGRect(origin: .zero, size: strip), radius: radius)
        let placed = Geometry.placed(model.marks(inBand: index), in: area)
        return Geometry.hit(location, centers: placed.map(\.center), radius: max(target, minimumTarget) / 2)
            .map { placed[$0].mark.original.ref }
    }

    /// The exact original a tap at `location` chooses in one band's strip, only with a callback.
    func choice(at location: CGPoint, in strip: CGSize, band index: Int) -> FieldChooserOriginalRef10868? {
        guard onChoose != nil else { return nil }
        return Self.choice(at: location, in: strip, band: index, model: model, radius: selectedRadius, target: target)
    }

    var body: some View {
        if model.isFinal {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(model.bands.enumerated()), id: \.offset) { index, band in
                    bandView(index, band)
                }
                axis
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(model.input.copy.graphicLabel)
            .accessibilityIdentifier(ID.map)
        } else {
            Text(model.input.copy.withheld)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier(ID.mapWithheld)
        }
    }

    private func bandView(_ index: Int, _ band: GolfPlacementMapBand10868) -> some View {
        let annotated = model.marks(inBand: index).filter(\.isAnnotated)
        return VStack(alignment: .leading, spacing: 4) {
            VStack(alignment: .leading, spacing: 2) {
                Text(band.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                if let count = FieldEventPageModel10868.readable(band.count) {
                    Text(count)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
            if !annotated.isEmpty {
                GolfPlacementMapLaneLayout10868(chances: annotated.map(\.x), required: annotated.map(\.isSelected),
                                                inset: selectedRadius, maxWidth: annotationMaxWidth,
                                                spacing: Self.laneSpacing, upward: true) {
                    ForEach(Array(annotated.enumerated()), id: \.offset) { _, mark in
                        annotation(mark)
                    }
                }
                .accessibilityHidden(true)
            }
            strip(index)
                .frame(height: stripHeight)
        }
        .padding(Self.bandPadding)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(index % 2 == 0 ? DS.surface : DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(GolfPlacementMapModel10868.bandSpoken(band))
        .accessibilityIdentifier(ID.band(band.id))
    }

    /// An annotation: the golfer's name over the original's own figure, both
    /// whole; a long name wraps at the lane's widest annotation.
    private func annotation(_ mark: GolfPlacementMapMark10868) -> some View {
        VStack(spacing: 0) {
            Text(mark.name)
                .font(.caption2.weight(.semibold))
                .multilineTextAlignment(.center)
            Text(mark.figure)
                .font(.caption.weight(.bold).monospacedDigit())
        }
        .foregroundStyle(mark.isSelected ? DS.blue : DS.textPrimary)
        .fixedSize(horizontal: false, vertical: true)
    }

    private func strip(_ index: Int) -> some View {
        GeometryReader { proxy in
            let bounds = CGRect(origin: .zero, size: proxy.size)
            let area = Geometry.markArea(bounds, radius: selectedRadius)
            let placed = Geometry.placed(model.marks(inBand: index), in: area)
            let tap: ((CGPoint) -> Void)? = onChoose.map { choose in
                { location in
                    if let ref = choice(at: location, in: proxy.size, band: index) { choose(ref) }
                }
            }
            ZStack(alignment: .topLeading) {
                Path { path in
                    for tick in model.ticks {
                        if let x = Geometry.x(tick.probability, in: area) {
                            path.move(to: CGPoint(x: x, y: bounds.minY))
                            path.addLine(to: CGPoint(x: x, y: bounds.maxY))
                        }
                    }
                }
                .stroke(DS.border, lineWidth: 1)
                .accessibilityHidden(true)
                ForEach(Array(placed.enumerated()), id: \.offset) { _, entry in
                    markView(entry)
                }
            }
            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .topLeading)
            .contentShape(Rectangle())
            .modifier(GolfPlacementMapTap10868(action: tap))
        }
    }

    private func markView(_ entry: GolfPlacementMapPlacedMark10868) -> some View {
        let mark = entry.mark
        let radius = mark.isSelected ? selectedRadius : markRadius
        let ref = mark.original.ref
        let action: (() -> Void)? = onChoose.map { choose in { choose(ref) } }
        let stroke = mark.isSelected ? DS.blue : (mark.point.labelled ? DS.textPrimary : DS.textSecondary)
        return Circle()
            .fill(DS.cardBg)
            .overlay(Circle().strokeBorder(stroke, lineWidth: mark.isSelected ? 3 : (mark.point.labelled ? 2 : 1.5)))
            .frame(width: radius * 2, height: radius * 2)
            .accessibilityElement()
            .accessibilityLabel(model.spoken(mark))
            .accessibilityAddTraits(mark.isSelected ? [.isSelected] : [])
            .modifier(GolfPlacementMapMarkAction10868(action: action, hint: model.input.copy.chooseHint))
            .accessibilityIdentifier(ID.mark(ref.outcomeID))
            .position(entry.center)
    }

    /// The owner's tick labels, each measured and centred on its own x;
    /// crowded labels step down a row rather than overlap or shrink.
    private var axis: some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 4) {
            GolfPlacementMapLaneLayout10868(chances: ticks.map(\.probability), required: ticks.map { _ in false },
                                            inset: selectedRadius, maxWidth: annotationMaxWidth,
                                            spacing: Self.laneSpacing, upward: false) {
                ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                    Text(tick.label)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityHidden(true)
            if let words = FieldEventPageModel10868.readable(model.input.copy.axis) {
                Text(words)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, Self.bandPadding)
    }
}

/// Measures and places one band's annotations, or the axis's tick labels:
/// each at its measured size on its own mark's or tick's x, in rows that
/// never overlap, inside a lane tall enough for every row.
struct GolfPlacementMapLaneLayout10868: Layout {
    /// Each subview's raw chance on the common scale, in subview order.
    let chances: [Double]
    /// The subviews placed first, nearest the marks.
    let required: [Bool]
    /// The scale's inset at both ends — the strip's.
    let inset: CGFloat
    /// The widest a subview grows before it wraps.
    let maxWidth: CGFloat
    let spacing: CGFloat
    /// Rows stack upward from the marks (annotations) or downward from them (the axis).
    let upward: Bool

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? ((subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0) + 2 * inset)
        return CGSize(width: width, height: plan(width: width, subviews: subviews).height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let layout = plan(width: bounds.width, subviews: subviews)
        for index in subviews.indices where index < layout.rects.count {
            let rect = layout.rects[index]
            subviews[index].place(at: CGPoint(x: bounds.minX + rect.minX, y: bounds.minY + rect.minY), anchor: .topLeading,
                                  proposal: ProposedViewSize(width: rect.width, height: rect.height))
        }
    }

    /// Every subview measured — whole, or wrapped at the widest allowed — then placed by the lane rule.
    func plan(width: CGFloat, subviews: Subviews) -> GolfPlacementMapLanePlan10868 {
        let limit = max(1, min(maxWidth, width))
        let annotations = subviews.indices.map { index -> GolfPlacementMapAnnotation10868 in
            let ideal = subviews[index].sizeThatFits(.unspecified)
            let size = ideal.width <= limit ? ideal : subviews[index].sizeThatFits(ProposedViewSize(width: limit, height: nil))
            let chance = index < chances.count ? chances[index] : .nan
            return GolfPlacementMapAnnotation10868(
                x: GolfPlacementMapGeometry10868.x(chance, width: width, inset: inset) ?? .nan,
                size: size, required: index < required.count && required[index])
        }
        let lane = GolfPlacementMapGeometry10868.lane(annotations, width: width, spacing: spacing)
        return upward ? lane : GolfPlacementMapGeometry10868.flipped(lane)
    }
}

/// A strip's tap, only with a callback.
private struct GolfPlacementMapTap10868: ViewModifier {
    let action: ((CGPoint) -> Void)?

    @ViewBuilder func body(content: Content) -> some View {
        if let action {
            content.onTapGesture(coordinateSpace: .local) { location in action(location) }
        } else {
            content
        }
    }
}

/// A mark's VoiceOver action, only with a callback.
private struct GolfPlacementMapMarkAction10868: ViewModifier {
    let action: (() -> Void)?
    let hint: String?

    @ViewBuilder func body(content: Content) -> some View {
        if let action {
            content
                .accessibilityAddTraits(.isButton)
                .accessibilityHint(hint ?? "")
                .accessibilityAction { action() }
        } else {
            content
        }
    }
}

// MARK: - Page input

/// One card the page can show full size.
nonisolated enum GolfPlacementCard10868: String, Hashable, CaseIterable {
    case history
    case map
}

/// Which owner selection a chooser serves.
nonisolated enum GolfPlacementChooserRole10868: String, Hashable, CaseIterable {
    /// The golfer whose recorded history anchors the page.
    case history
    /// The golfer the map highlights.
    case map
}

/// What the host's container is showing, chosen by the host.
nonisolated enum GolfPlacementEventPageMode10868: Equatable {
    case page
    case reader(GolfPlacementCard10868)
    case chooser(GolfPlacementChooserRole10868)
    case catalogue
    case original
    case about
}

/// A choice, handed back with its role.
nonisolated struct GolfPlacementChoice10868: Equatable {
    let role: GolfPlacementChooserRole10868
    let ref: FieldChooserOriginalRef10868
}

/// A chooser control, handed back with its role.
nonisolated struct GolfPlacementChooserControl10868: Equatable {
    let role: GolfPlacementChooserRole10868
    let control: FieldChooserControl10868
}

/// One original's separately reported tournament facts, as the owner reported them.
nonisolated struct GolfPlacementReport10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's reported total with its own capture line, or its absence words.
    let score: FieldChooserReading10868
    /// The owner's round-count words; nil uses the copy's words.
    let rounds: String?
}

nonisolated struct GolfPlacementReadoutCopy10868: Equatable {
    /// Used when the original carries no result of its own.
    let resultLabel: String
    let resultUnavailable: String
    /// Used when no single report resolves.
    let scoreLabel: String
    let scoreUnavailable: String
    let roundsUnavailable: String
    let detailsLabel: String
    let detailsHint: String?
    /// A held golfer whose identity does not resolve.
    let unavailableWords: String
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct GolfPlacementStory10868: Equatable {
    let cardID: String
    let card: GolfPlacementCard10868
    var reason: String? = nil
}

nonisolated struct GolfPlacementCopy10868: Equatable {
    /// Shown in place of a headline that is not at its own final phase.
    let headlineUnavailable: String
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story.
    let storyUnavailable: String
    /// The entry to every original; nil draws none.
    let allPropsLabel: String?
    let historyEntry: GolfWinnerArchiveChooserEntryCopy10868
    let mapEntry: GolfWinnerArchiveChooserEntryCopy10868
}

nonisolated struct GolfPlacementEventPageInput10868: Equatable {
    let copy: GolfPlacementCopy10868
    /// The compact words above full-size, chooser, catalogue and About content.
    let reader: FieldEventPageReaderHeader10868
    /// The exact scope of every reference below.
    let scope: String
    /// The canonical catalogue, in the owner's order — every original.
    let catalogue: [FieldChooserOriginal10868]
    let headline: FieldHeadlineInput10868
    let history: FieldHistoryInput10868
    /// The owner's held history golfer.
    let historySelection: FieldChooserOriginalRef10868?
    /// Every separately reported score and round count, one per original, in any order.
    let reports: [GolfPlacementReport10868]
    let map: GolfPlacementMapInput10868
    let readout: GolfPlacementReadoutCopy10868
    let historyChooser: GolfWinnerArchiveChooser10868?
    let mapChooser: GolfWinnerArchiveChooser10868?
    let stream: StoryStreamPresentation10868
    let stories: [GolfPlacementStory10868]
    let about: FieldEventPageAbout10868?
    /// The owner's full-size plot height; used only when finite, positive and taller.
    var readerPlotHeight: CGFloat? = nil
}

// MARK: - Page model

/// One golfer's readout, all from its own original and its own report.
nonisolated struct GolfPlacementReadout10868: Equatable {
    let original: FieldChooserOriginal10868
    /// The original's own pre-event reading, with its own clock.
    let chance: FieldChooserReading10868
    let resultLabel: String
    let resultWords: String
    /// The report's score, or the copy's words.
    let score: FieldChooserReading10868
    let rounds: String
    /// Nil when no single report resolves.
    let report: GolfPlacementReport10868?
}

nonisolated enum GolfPlacementReadoutResolution10868: Equatable {
    /// No held golfer: nothing drawn.
    case notHeld
    case shown(GolfPlacementReadout10868)
    /// The held golfer does not resolve: the owner's words.
    case unavailable(String)
}

/// One part of the map card, in the order the card mounts them.
nonisolated enum GolfPlacementMapPart10868: Hashable, CaseIterable {
    case eyebrow
    case title
    case caption
    /// The bands, marks, ticks and axis words — or the withheld words.
    case plot
    /// The held map golfer's chooser entry.
    case entry
    /// The held map golfer's readout: its own chance and date, its own result,
    /// the reported score, round count and Details.
    case readout
    /// The held map golfer resolves but has no drawn mark.
    case notice
    /// Previous and Next in the owner's reader order.
    case steps
    case note
}

nonisolated enum GolfPlacementAccessibilityID10868 {
    static let page = "golfPlacement10868.page"
    static let hero = "golfPlacement10868.hero"
    static let headlineUnavailable = "golfPlacement10868.headline.unavailable"
    static let anchor = "golfPlacement10868.anchor"
    static let stories = "golfPlacement10868.stories"
    static let storyUnavailable = "golfPlacement10868.story.unavailable"
    static let allProps = "golfPlacement10868.allProps"
    static let readerHeader = "golfPlacement10868.readerHeader"
    static let readerAbout = "golfPlacement10868.readerHeader.about"
    static let catalogue = "golfPlacement10868.catalogue"
    static let original = "golfPlacement10868.original"
    static let aboutContent = "golfPlacement10868.aboutContent"
    static let map = "golfPlacement10868.map"
    static let mapWithheld = "golfPlacement10868.map.withheld"
    static let notice = "golfPlacement10868.map.notice"
    static func band(_ id: String) -> String { "golfPlacement10868.map.band.\(id)" }
    static func mark(_ outcomeID: String) -> String { "golfPlacement10868.map.mark.\(outcomeID)" }
    static func step(_ step: FieldOutlookStep10868) -> String { "golfPlacement10868.map.step.\(step == .previous ? "previous" : "next")" }
    static func card(_ card: GolfPlacementCard10868) -> String { "golfPlacement10868.card.\(card.rawValue)" }
    static func chooser(_ role: GolfPlacementChooserRole10868) -> String { "golfPlacement10868.chooser.\(role.rawValue)" }
    static func entry(_ role: GolfPlacementChooserRole10868) -> String { "golfPlacement10868.entry.\(role.rawValue)" }
    static func readout(_ role: GolfPlacementChooserRole10868) -> String { "golfPlacement10868.readout.\(role.rawValue)" }
    static func details(_ role: GolfPlacementChooserRole10868) -> String { "golfPlacement10868.readout.\(role.rawValue).details" }
}

/// What the page mounts and draws, resolved once per input.
nonisolated struct GolfPlacementEventPageModel10868: Equatable {
    let input: GolfPlacementEventPageInput10868
    /// The chooser's own resolver over the page's canonical catalogue.
    let field: FieldChooserModel10868
    let map: GolfPlacementMapModel10868

    init(_ input: GolfPlacementEventPageInput10868) {
        self.input = input
        // Only the resolver is read: no chooser section is drawn from it and nothing is selected.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope, intro: nil,
            featured: FieldChooserFeatured10868(title: input.map.copy.title, badge: nil, refs: [],
                                                emptyWords: input.readout.unavailableWords),
            context: nil, more: nil, browse: nil, catalogue: input.catalogue, frame: nil, selected: nil,
            unavailableWords: input.readout.unavailableWords, chooseHint: nil))
        map = GolfPlacementMapModel10868(input.map, scope: input.scope, catalogue: input.catalogue,
                                         unavailableWords: input.readout.unavailableWords)
    }

    // MARK: Hero and anchor

    /// The headline only at its own final phase — never coerced from another.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == .final ? input.headline : nil
    }

    /// The history the page or full size draws: the owner's input with only
    /// its height and expand control changed. Full size is never shorter, and
    /// only a finite, positive owner height enlarges it.
    func history(reader: Bool) -> FieldHistoryInput10868 {
        let history = input.history
        return VolleyballFieldEventPageModel10868.presentationCopy(
            history,
            plotHeight: reader
                ? RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight)
                : history.plotHeight,
            expand: reader ? nil : history.expand,
            showsKey: history.showsKey)
    }

    // MARK: Golfers

    /// The owner's one report for this original; several, even identical, are none.
    func report(for ref: FieldChooserOriginalRef10868) -> GolfPlacementReport10868? {
        let matches = input.reports.filter { $0.ref == ref }
        return matches.count == 1 ? matches[0] : nil
    }

    /// One resolved original's readout: its own pre-event reading and result,
    /// and its own report's score and round count — or the copy's words.
    func readout(for original: FieldChooserOriginal10868) -> GolfPlacementReadout10868 {
        let copy = input.readout
        let own = report(for: original.ref)
        return GolfPlacementReadout10868(
            original: original,
            chance: FieldOutlookModel10868.beforeReading(original.plan),
            resultLabel: original.result?.title ?? copy.resultLabel,
            resultWords: original.result?.words ?? copy.resultUnavailable,
            score: own?.score ?? FieldChooserReading10868(label: copy.scoreLabel, value: .missing(copy.scoreUnavailable)),
            rounds: FieldEventPageModel10868.readable(own?.rounds) ?? copy.roundsUnavailable,
            report: own)
    }

    func readout(_ ref: FieldChooserOriginalRef10868?) -> GolfPlacementReadoutResolution10868 {
        guard let ref else { return .notHeld }
        guard let original = field.resolve(ref).original else { return .unavailable(input.readout.unavailableWords) }
        return .shown(readout(for: original))
    }

    func selection(_ role: GolfPlacementChooserRole10868) -> FieldChooserOriginalRef10868? {
        switch role {
        case .history: input.historySelection
        case .map: input.map.selected
        }
    }

    func readout(role: GolfPlacementChooserRole10868) -> GolfPlacementReadoutResolution10868 {
        readout(selection(role))
    }

    // MARK: Words

    /// A readout's words in reading order — the same values its view draws.
    static func words(_ readout: GolfPlacementReadout10868) -> [String] {
        [readout.original.name] + GolfWinnerArchiveEventPageModel10868.words(readout.chance)
            + [readout.resultLabel, readout.resultWords]
            + GolfWinnerArchiveEventPageModel10868.words(readout.score) + [readout.rounds]
    }

    /// A readout in VoiceOver words.
    static func spoken(_ readout: GolfPlacementReadout10868) -> String {
        [readout.original.name, FieldChooserModel10868.spoken(readout.chance),
         "\(readout.resultLabel): \(readout.resultWords)", FieldChooserModel10868.spoken(readout.score),
         readout.rounds]
            .filter { FieldEventPageModel10868.readable($0) != nil }
            .joined(separator: ". ")
    }

    /// The chooser entry's golfer: the held golfer's whole name or the owner's words; nil with none held.
    func entryName(_ role: GolfPlacementChooserRole10868) -> String? {
        switch readout(role: role) {
        case .notHeld: nil
        case .shown(let readout): readout.original.name
        case .unavailable(let words): words
        }
    }

    func entryCopy(_ role: GolfPlacementChooserRole10868) -> GolfWinnerArchiveChooserEntryCopy10868 {
        role == .history ? input.copy.historyEntry : input.copy.mapEntry
    }

    // MARK: Stories

    /// The owner's link a stream card id names: exactly one link, to the map.
    /// Otherwise nothing — never a neighbour.
    func story(_ cardID: String) -> GolfPlacementStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card == .map else { return nil }
        return link
    }

    // MARK: Choosers

    func chooser(_ role: GolfPlacementChooserRole10868) -> GolfWinnerArchiveChooser10868? {
        role == .history ? input.historyChooser : input.mapChooser
    }

    /// The role's hierarchy on its own full chooser, while both exist.
    func chooserNavigation(_ role: GolfPlacementChooserRole10868) -> GolfPreTournamentChooserNavigationModel10868? {
        guard let chooser = chooser(role), let navigation = chooser.navigation else { return nil }
        return GolfPreTournamentChooserNavigationModel10868(navigation: navigation, chooser: chooser.chooser)
    }

    /// The chooser the shared leaf draws for a role — with a hierarchy, the
    /// pre-tournament golf page's rule: only the groups whose id is the
    /// selected group's or one of the chooser's own control ids, so selection,
    /// missing or duplicated groups and id collisions resolve exactly as from
    /// the full list and no wall of group buttons is drawn.
    func chooserPresentation(_ role: GolfPlacementChooserRole10868) -> FieldChooserInput10868? {
        guard let entry = chooser(role) else { return nil }
        let chooser = entry.chooser
        guard entry.navigation != nil, let browse = chooser.browse else { return chooser }
        let kept = Set([browse.selectedGroupID, browse.id, chooser.more?.id].compactMap { $0 })
        let shown = FieldChooserBrowse10868(
            id: browse.id, title: browse.title, expanded: browse.expanded, note: browse.note,
            groupsLabel: browse.groupsLabel, groups: browse.groups.filter { kept.contains($0.id) },
            selectedGroupID: browse.selectedGroupID, noGroupWords: browse.noGroupWords,
            groupUnavailableWords: browse.groupUnavailableWords, emptyGroupWords: browse.emptyGroupWords)
        return FieldChooserInput10868(
            scope: chooser.scope, intro: chooser.intro, featured: chooser.featured, context: chooser.context,
            more: chooser.more, browse: shown, catalogue: chooser.catalogue, frame: chooser.frame,
            selected: chooser.selected, unavailableWords: chooser.unavailableWords, chooseHint: chooser.chooseHint)
    }

    // MARK: About and entries

    var about: FieldEventPageAbout10868? {
        guard let about = input.about,
              FieldEventPageModel10868.readable(about.title) != nil
                || about.paragraphs.contains(where: { FieldEventPageModel10868.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && FieldEventPageModel10868.readable(input.headline.copy.aboutLabel) != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && FieldEventPageModel10868.readable(input.copy.allPropsLabel) != nil
    }
}

// MARK: - Page view

struct GolfPlacementEventPagePresentation10868: View {
    typealias Model = GolfPlacementEventPageModel10868
    typealias Role = GolfPlacementChooserRole10868
    typealias Part = GolfPlacementMapPart10868
    typealias ID = GolfPlacementAccessibilityID10868
    typealias Stream = StoryStreamPresentation10868

    let input: GolfPlacementEventPageInput10868
    var mode: GolfPlacementEventPageMode10868 = .page
    /// Every original and the held original's Details; nil: neither.
    var originals: FieldEventPageOriginals10868? = nil
    var onAbout: (() -> Void)? = nil
    /// The hero golfer's exact open.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens the host's chooser for one role.
    var onOpenChooser: ((Role) -> Void)? = nil
    /// A golfer chosen for one role: from that role's chooser, a map mark or a step.
    var onChoose: ((GolfPlacementChoice10868) -> Void)? = nil
    var onChooserControl: ((GolfPlacementChooserControl10868) -> Void)? = nil
    /// A readout's exact original, for the host's Details.
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    var onAllProps: (() -> Void)? = nil
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// Called once before a page, chooser, catalogue or Details action reaches its owner.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var mapMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var sideMinWidth: CGFloat = 260
    @ScaledMetric(relativeTo: .body) private var sideMaxWidth: CGFloat = 380

    static let minimumTarget: CGFloat = 44

    /// The map card's parts, in order — the body draws exactly these, the same
    /// on the page, in the stream and full size.
    static let headParts: [Part] = [.eyebrow, .title, .caption]
    static let graphicParts: [Part] = [.plot]
    static let sideParts: [Part] = [.entry, .readout, .notice, .steps]
    static let footParts: [Part] = [.note]
    static var mapParts: [Part] { headParts + graphicParts + sideParts + footParts }

    var model: Model { Model(input) }

    /// Where an action is reached: on the page outside the stream (held by the
    /// hook), inside a stream card (the stream's interaction is the hold), or
    /// in full-size content (exact).
    enum Place {
        case page
        case stream(StoryStreamCardActivation10868)
        case reader
    }

    /// An action as `place` reaches it. No callback: no action.
    func placed<Value>(_ action: ((Value) -> Void)?, at place: Place) -> ((Value) -> Void)? {
        switch place {
        case .page: return FieldEventPagePresentation10868.held(action, by: onInteraction)
        case .stream(let activation): return FieldEventPagePresentation10868.relay(action, through: activation)
        case .reader: return action
        }
    }

    // MARK: Actions — each exactly what its control runs

    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0,
                                                onAbout: FieldEventPagePresentation10868.heldAction(aboutOpener(), by: onInteraction),
                                                onOpen: placed(onHeadlineOpen, at: .page))
        }
    }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let place: Place = reader ? .reader : .page
        return FieldProbabilityHistoryPresentation10868(
            input: model.history(reader: reader),
            onAction: placed(onHistoryAction, at: place),
            onInspectionChoice: placed(onHistoryInspectionChoice, at: place),
            onPlotPosition: placed(onHistoryPlotPosition, at: place))
    }

    /// The map leaf, its marks choosing for the map role as `place` reaches them.
    func mapContent(at place: Place) -> GolfPlacementMapPresentation10868 {
        GolfPlacementMapPresentation10868(model: model.map, onChoose: placed(roleChoose(.map), at: place))
    }

    /// The chooser entry for a role, while a callback exists.
    func entryAction(_ role: Role, at place: Place) -> (() -> Void)? {
        guard let open = placed(onOpenChooser, at: place) else { return nil }
        return { open(role) }
    }

    /// A readout's Details, for its own resolved original only.
    func detailsAction(_ role: Role, at place: Place) -> (() -> Void)? {
        guard case .shown(let readout) = model.readout(role: role),
              let open = placed(onOpenOriginal, at: place) else { return nil }
        let ref = readout.original.ref
        return { open(ref) }
    }

    /// Previous or Next: the owner's exact neighbour for the map role, while a callback exists.
    func stepAction(_ step: FieldOutlookStep10868, at place: Place) -> (() -> Void)? {
        guard let neighbour = model.map.neighbour(step),
              let choose = placed(roleChoose(.map), at: place) else { return nil }
        let ref = neighbour.ref
        return { choose(ref) }
    }

    /// The shared chooser for a role, with that role's held callbacks.
    func chooserContent(_ role: Role) -> FieldContenderChooserPresentation10868? {
        model.chooserPresentation(role).map {
            FieldContenderChooserPresentation10868(input: $0, onChoose: placed(roleChoose(role), at: .page),
                                                   onControl: placed(roleControl(role), at: .page))
        }
    }

    func chooserNavigationContent(_ role: Role, _ part: GolfPreTournamentChooserNavigationPart10868) -> GolfPreTournamentChooserNavigationPresentation10868? {
        model.chooserNavigation(role).map {
            GolfPreTournamentChooserNavigationPresentation10868(model: $0, part: part,
                                                                 onControl: placed(roleControl(role), at: .page))
        }
    }

    private func roleChoose(_ role: Role) -> ((FieldChooserOriginalRef10868) -> Void)? {
        onChoose.map { choose in
            { ref in choose(GolfPlacementChoice10868(role: role, ref: ref)) }
        }
    }

    private func roleControl(_ role: Role) -> ((FieldChooserControl10868) -> Void)? {
        onChooserControl.map { send in
            { control in send(GolfPlacementChooserControl10868(role: role, control: control)) }
        }
    }

    func aboutContent() -> FieldEventPageAboutContent10868? {
        model.about.map { FieldEventPageAboutContent10868(about: $0) }
    }

    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: placed(onOriginalSelect, at: .page))
        }
    }

    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                                          recorded: $0.recorded, onHistory: placed(onOriginalHistory, at: .page))
        }
    }

    func openPageAbout() {
        FieldEventPagePresentation10868.heldAction(aboutOpener(), by: onInteraction)?()
    }

    /// Full-size content's About: the exact callback.
    func openAbout() {
        aboutOpener()?()
    }

    func allPropsAction() -> (() -> Void)? {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return nil }
        return FieldEventPagePresentation10868.heldAction(onAllProps, by: onInteraction)
    }

    // MARK: Words

    /// Every word the map card draws or speaks, part by part — the values the
    /// body draws (annotations and ticks included) and each mark's VoiceOver
    /// words, an action's words only while it acts.
    func mapWords(at place: Place) -> [String] {
        let copy = input.map.copy
        let map = model.map
        return Self.mapParts.flatMap { part -> [String] in
            switch part {
            case .eyebrow: return [FieldEventPageModel10868.readable(copy.eyebrow)].compactMap { $0 }
            case .title: return [copy.title]
            case .caption: return [FieldEventPageModel10868.readable(copy.caption)].compactMap { $0 }
            case .plot:
                guard map.isFinal else { return [copy.withheld] }
                return map.bands.indices.flatMap { index -> [String] in
                    let band = map.bands[index]
                    let marks = map.marks(inBand: index)
                    return [band.label] + [FieldEventPageModel10868.readable(band.count)].compactMap { $0 }
                        + marks.filter(\.isAnnotated).flatMap { [$0.name, $0.figure] }
                        + marks.map { map.spoken($0) }
                } + map.ticks.map(\.label) + [FieldEventPageModel10868.readable(copy.axis)].compactMap { $0 }
            case .entry:
                guard let name = model.entryName(.map) else { return [] }
                let entry = model.entryCopy(.map)
                return [entry.caption, name] + (entryAction(.map, at: place) == nil ? [] : [entry.action])
            case .readout:
                switch model.readout(role: .map) {
                case .notHeld: return []
                case .unavailable(let words): return [words]
                case .shown(let readout):
                    return Model.words(readout) + (detailsAction(.map, at: place) == nil ? [] : [input.readout.detailsLabel])
                }
            case .notice: return [map.notice].compactMap { $0 }
            case .steps:
                return (stepAction(.previous, at: place) == nil ? [] : [copy.previousLabel])
                    + (stepAction(.next, at: place) == nil ? [] : [copy.nextLabel])
            case .note: return [FieldEventPageModel10868.readable(copy.note)].compactMap { $0 }
            }
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .chooser(let role): chooserMode(role)
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            stories
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.page)
    }

    private var hero: some View {
        let arrangements = FieldEventPageModel10868.arrangements(sizeClass: sizeClass,
                                                                 accessibilitySize: typeSize.isAccessibilitySize)
        return Group {
            if arrangements == [.stacked] {
                heroStacked
            } else {
                ViewThatFits(in: .horizontal) {
                    heroSideBySide
                    heroStacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            headlineCard
            anchorCard
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            headlineCard
                .frame(minWidth: headlineMinWidth, maxWidth: headlineMaxWidth, alignment: .topLeading)
            anchorCard
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    private var headlineCard: some View {
        Group {
            if let headline = headlineContent() {
                headline
            } else {
                Text(input.copy.headlineUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(ID.headlineUnavailable)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(GolfPlacementCardSurface10868())
    }

    private var anchorCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            entry(.history, at: .page)
            historyContent(reader: false)
            readoutView(.history, at: .page)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(GolfPlacementCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if let action = allPropsAction(), let label = input.copy.allPropsLabel {
                Button(action: action) {
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
                    .frame(minHeight: Self.minimumTarget)
                    .modifier(GolfPlacementCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(ID.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(ID.stories)
    }

    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = FieldEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                mapCard(at: .stream(activation))
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(GolfPlacementCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(GolfPlacementCardSurface10868())
                .accessibilityIdentifier(ID.storyUnavailable)
        }
    }

    // MARK: Map card

    /// The map card: the head, then the map beside its readout where both fit
    /// (stacked on a phone and at accessibility sizes), then the note.
    private func mapCard(at place: Place) -> some View {
        let stacked = typeSize.isAccessibilitySize || sizeClass == .compact
        return VStack(alignment: .leading, spacing: 12) {
            parts(Self.headParts, at: place)
            if stacked {
                parts(Self.graphicParts + Self.sideParts, at: place)
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 20) {
                        parts(Self.graphicParts, at: place)
                            .frame(minWidth: mapMinWidth, maxWidth: .infinity, alignment: .topLeading)
                            .layoutPriority(1)
                        parts(Self.sideParts, at: place)
                            .frame(minWidth: sideMinWidth, maxWidth: sideMaxWidth, alignment: .topLeading)
                    }
                    parts(Self.graphicParts + Self.sideParts, at: place)
                }
            }
            parts(Self.footParts, at: place)
        }
    }

    private func parts(_ list: [Part], at place: Place) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(list, id: \.self) { part in
                mapPart(part, at: place)
            }
        }
    }

    @ViewBuilder private func mapPart(_ part: Part, at place: Place) -> some View {
        let copy = input.map.copy
        switch part {
        case .eyebrow:
            if let eyebrow = FieldEventPageModel10868.readable(copy.eyebrow) {
                Text(eyebrow)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .title:
            Text(copy.title)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
        case .caption:
            if let caption = FieldEventPageModel10868.readable(copy.caption) {
                Text(caption)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .plot:
            mapContent(at: place)
        case .entry:
            entry(.map, at: place)
        case .readout:
            readoutView(.map, at: place)
        case .notice:
            if let notice = model.map.notice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(ID.notice)
            }
        case .steps:
            steps(at: place)
        case .note:
            if let note = FieldEventPageModel10868.readable(copy.note) {
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private func steps(at place: Place) -> some View {
        let previous = stepAction(.previous, at: place)
        let next = stepAction(.next, at: place)
        if previous != nil || next != nil {
            let row = Group {
                if let previous {
                    stepButton(.previous, action: previous)
                }
                if let next {
                    stepButton(.next, action: next)
                }
            }
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) { row }
            } else {
                HStack(spacing: 12) { row }
            }
        }
    }

    private func stepButton(_ step: FieldOutlookStep10868, action: @escaping () -> Void) -> some View {
        let copy = input.map.copy
        let label = step == .previous ? copy.previousLabel : copy.nextLabel
        let name = model.map.neighbour(step)?.name
        return Button(action: action) {
            HStack(spacing: 6) {
                if step == .previous {
                    Image(systemName: "chevron.left").accessibilityHidden(true)
                }
                Text(label)
                    .font(.body.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                if step == .next {
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
            }
            .foregroundStyle(DS.blue)
            .padding(.horizontal, 12)
            .frame(minWidth: Self.minimumTarget, minHeight: Self.minimumTarget)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel([label, name].compactMap { $0 }.joined(separator: ", "))
        .accessibilityHint(copy.chooseHint ?? "")
        .accessibilityIdentifier(ID.step(step))
    }

    // MARK: Readout and chooser entry

    /// A role's held golfer: its own reading, result, score and round count,
    /// and Details while a callback exists.
    @ViewBuilder private func readoutView(_ role: Role, at place: Place) -> some View {
        switch model.readout(role: role) {
        case .notHeld:
            EmptyView()
        case .unavailable(let words):
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(ID.readout(role))
        case .shown(let readout):
            VStack(alignment: .leading, spacing: 10) {
                Text(readout.original.name)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                let values = Group {
                    value(readout.chance)
                    words(label: readout.resultLabel, words: readout.resultWords)
                }
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 10) { values }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 16) { values }
                        VStack(alignment: .leading, spacing: 10) { values }
                    }
                }
                value(readout.score)
                Text(readout.rounds)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let action = detailsAction(role, at: place) {
                    Button(action: action) {
                        HStack(spacing: 6) {
                            Text(input.readout.detailsLabel)
                                .font(.body.weight(.semibold))
                                .fixedSize(horizontal: false, vertical: true)
                            Image(systemName: "chevron.right").accessibilityHidden(true)
                        }
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: Self.minimumTarget)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint(input.readout.detailsHint ?? "")
                    .accessibilityIdentifier(ID.details(role))
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.readout(role))
        }
    }

    /// A reading: the owner's figure with its own clock line, or its own words.
    private func value(_ reading: FieldChooserReading10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(reading.label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            switch reading.value {
            case .recorded(let text, let detail):
                Text(text)
                    .font(.title2.weight(.bold).monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                if let detail = FieldEventPageModel10868.readable(detail) {
                    Text(detail).font(.footnote).foregroundStyle(DS.textSecondary)
                }
            case .missing(let words):
                Text(words)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }

    /// The original's own admitted result: words, never a figure.
    private func words(label: String, words: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            Text(words)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }

    /// The role's chooser entry: the held golfer in view and, with a callback, the action.
    @ViewBuilder private func entry(_ role: Role, at place: Place) -> some View {
        let copy = model.entryCopy(role)
        if let name = model.entryName(role) {
            let face = HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(copy.caption).font(.subheadline).foregroundStyle(DS.textSecondary)
                    Text(name).font(.body.weight(.semibold)).foregroundStyle(DS.textPrimary)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if entryAction(role, at: place) != nil {
                    HStack(spacing: 4) {
                        Text(copy.action).font(.subheadline.weight(.semibold))
                        Image(systemName: "chevron.down").accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                }
            }
            .padding(.horizontal, 12)
            .frame(minHeight: Self.minimumTarget)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            if let action = entryAction(role, at: place) {
                Button(action: action) { face.contentShape(Rectangle()) }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(copy.caption): \(name). \(copy.action)")
                    .accessibilityHint(copy.hint ?? "")
                    .accessibilityIdentifier(ID.entry(role))
            } else {
                face
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier(ID.entry(role))
            }
        }
    }

    // MARK: Full size

    @ViewBuilder private func reader(_ card: GolfPlacementCard10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            switch card {
            case .history:
                entry(.history, at: .reader)
                historyContent(reader: true)
                readoutView(.history, at: .reader)
            case .map:
                mapCard(at: .reader)
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
            if case .reader = mode, aboutOpener() != nil {
                Button(action: openAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: Self.minimumTarget, minHeight: Self.minimumTarget)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(ID.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.readerHeader)
    }

    // MARK: Chooser, every original, Details and About

    @ViewBuilder private func chooserMode(_ role: Role) -> some View {
        if let chooser = chooserContent(role) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if let controls = chooserNavigationContent(role, .controls) {
                    controls
                }
                chooser
                if let pages = chooserNavigationContent(role, .pages) {
                    pages
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.chooser(role))
        }
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(ID.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.aboutContent)
        }
    }
}

/// The page's white card on the page surface.
private struct GolfPlacementCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
