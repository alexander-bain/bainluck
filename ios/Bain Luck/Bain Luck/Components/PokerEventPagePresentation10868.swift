import SwiftUI

// #10868 — the poker tournament page (`poker-tournament`): a field of
// independently traded winner originals and one country original, read in an
// explicit owner role — before the final table, or final. A fan sees the
// owner's heading and archive words with a compact About control; the selected
// player's own-dated chances at one equal size above the shared win history,
// where every original trade is its own mark in the player's stable shape —
// hollow before the scheduled final table, filled later — with an outer ring
// on the inspected trade; then the owner's story stream: the starting chip
// share against the separately traded win chance, the country card and, at
// the final only, the chance-to-result card; and the entry to every original.
// Each card opens full size as the same Views with the same inputs; the player
// chooser, every original, the held original's Details with its Yes/No sides,
// one original side's full history and the About are further content modes.
//
// Presentation only, from the approved poker tournament reference (its page,
// chance reading, featured baselines, original prop and outcome plot, their
// styles) and its native comparison adoption records. Their capture loader,
// trade qualification, before-table election, inspection index arithmetic,
// selection and featured-anchor rules, identity table, chip-share division,
// ranking, percentage, money and clock formatting, return-context engine,
// focus restoration, sheets and reader memory are NOT ported. The leaves are
// the actual accepted Views and types:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor and the original
//     side's full history. The owner gives every trade its own singleton run,
//     so the shared history draws a mark per position and never a line; two
//     trades in the same second, or with identical values, stay two points with
//     two ids. Identity shapes, tints, hollow/filled phase marks, the inspection
//     ring, the key below the chart (each featured player's own earlier chance
//     and choose control), range and inspection controls are the history's own;
//   • `HistoricalChanceResultPresentation10868` — the final-only chance-to-result
//     card, its reported finish in its own panel;
//   • `FieldContenderChooserPresentation10868` — the player chooser;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     every original and the held original side's Details with its recorded
//     history, rules and provenance;
//   • `StoryStreamPresentationView10868`, the field page's hold helpers, its
//     arrangement rule, reader heading and About content, and the finite,
//     never-shorter full-size height.
//
// Why not the field or golf page: the field page's phase is pre-event,
// during or final — its "before" means before the event and its headline keys
// carry no triangle — and its stories are the field outlook and pre-event
// movement only; the golf page always mounts a finish card. Neither shows
// own-dated readouts tied to the inspected trade, a chip-share card or a
// country card. What is drawn here beyond arrangement: the equal readouts,
// the chip-share card and the country card.
//
// Roles: this page's role is the owner's explicit `PokerEventPageRole10868`,
// never read from a clock, a price or a result. Before the final table is a
// frame inside a running tournament and is never relabelled pre-tournament:
// the readouts always carry the owner's words that a pre-tournament chance is
// unavailable, and no input can supply one. Reported standings, prizes and
// the country result are shown in the final role only, apart from every
// chance; the chance-to-result card mounts only in the final role and its own
// final phase. Readouts in another role are never coerced: the anchor shows the
// owner's unavailable words instead, and the held original side's full history
// follows the same rule as one value — its readouts, history, note and reader
// actions all come from an outcome in the page's own role, or none of them do.
// The originals follow it too: the host hands them over with the role it built
// them for, and one admitted value in the page's own role drives every
// original, the held side's Details and recorded history, the side highlight
// and every side action; in another role each shows the owner's unavailable
// words and acts on nothing. No role is ever inferred from a grade, quote or date.
//
// Readouts: one inspected earlier chance before the final table; at the final,
// the before-table chance beside the inspected recorded trade, each with its
// own date. A reading counts only while its owner position names exactly one
// point of the subject's own series with the same raw value and carries its own
// date, and the inspected reading only while the history's own inspection rings
// exactly that point. The before-table reading needs a point the owner marks
// hollow (before the final table), and so does the inspected reading in the
// before-final-table role; a filled point is never relabelled before-table. The
// same exact position collapses the pair into one slot; equal values at two
// positions stay two. A missing, changed, duplicated or foreign position shows
// the owner's unavailable words — never the latest trade or a neighbour.
// Unknown is never zero.
//
// Chip card: the owner's ordered rows, each the starting chip SHARE as a filled
// bar and the separately traded before-table WIN CHANCE as an outlined bar, on
// the owner's one zero-based scale with a two-measure key. Every value and word
// is the owner's; the view never divides chip counts. Country card: the owner's
// country Yes chance, a short bar on the owner's scale and the entry to both
// original outcomes; the reported winner's country in the final role only, and
// the owner's unknown words when it is not reported. Yes and No are independent
// originals: nothing is complemented.
//
// Actions: on the page and in the chooser, catalogue, Details and sides, each
// action calls the owner's interaction hook once, then the owner's exact
// callback with its exact value. A stream card's own actions call the stream's
// activation instead. Full-size content keeps the exact callbacks with no hold.
// Without a callback there is no control and no hook call; building or reading
// the view calls nothing.
//
// Layout: a compact width or an accessibility size stacks the anchor above the
// stories; a regular or unspecified width places them side by side while both
// keep their minimum widths, otherwise stacks. The host owns the scroll,
// navigation, sheets, Back/Done, focus, held arrivals, the selected player and
// side, the cohort and its shapes, the range choice, ranking, paging and every
// update. This view keeps no state, runs no timer and presents nothing.
//
// Host binding still owed — not available at this base: an owner that admits
// the originals and their sides by exact identity, qualifies each side's trades
// into singleton runs with phase marks and position ids, elects the before-table
// reading, supplies the readout, chip, country and result inputs with their
// words, the stream, chooser and originals, and maps every callback.

/// The page's display role, chosen by the owner.
nonisolated enum PokerEventPageRole10868: Equatable {
    /// Before the final table: a frame inside the running tournament — never
    /// before the tournament.
    case beforeFinalTable
    /// After the reported finish.
    case final
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum PokerEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// Starting chip share against the separately traded win chance.
    case chips
    /// The winner's-country original.
    case country
    /// The final-only chance-to-result card.
    case result
}

/// What the host's container is showing, chosen by the host.
nonisolated enum PokerEventPageMode10868: Equatable {
    case page
    case reader(PokerEventPageCard10868)
    /// The player chooser.
    case chooser
    /// Every original.
    case catalogue
    /// The held original side's Details.
    case original
    /// The held original side's full history.
    case outcome
    case about
}

// MARK: - Readouts

/// One owner reading tied to one exact position of the subject's series.
nonisolated struct PokerChanceReading10868: Equatable {
    /// The owner's id of exactly one point in the subject's series — a position, never a clock.
    let pointID: String
    /// The raw value behind `figure`; must equal that point's own value.
    let probability: Double
    /// The owner's figure.
    let figure: String
    /// The figure's own date.
    let date: String
}

nonisolated struct PokerChanceCopy10868: Equatable {
    /// The before-table slot at the final.
    let baselineLabel: String
    /// The one inspected slot before the final table.
    let inspectedBeforeTableLabel: String
    /// An inspected hollow (before-table) trade at the final.
    let inspectedEarlierLabel: String
    /// An inspected filled (later) trade at the final.
    let recordedLabel: String
    /// One slot when the before-table and inspected positions are the same.
    let sameObservationLabel: String
    let baselineUnavailable: String
    let baselineUnavailableDetail: String
    let inspectedUnavailable: String
    let inspectedUnavailableDetail: String
    /// Always shown: there is no pre-tournament reading.
    let preTournamentUnavailable: String
    /// Label beside the owner's final result words.
    let resultLabel: String
}

nonisolated struct PokerChanceComparisonInput10868: Equatable {
    let role: PokerEventPageRole10868
    /// The subject's one series in the history it sits beside.
    let seriesID: String
    /// The owner's whole name.
    let name: String
    /// The owner's outcome meaning for this original side.
    let meaning: String
    let baseline: PokerChanceReading10868?
    let inspected: PokerChanceReading10868?
    /// The owner's reported result words for this original; final role only.
    var result: String? = nil
    let copy: PokerChanceCopy10868
}

/// One readout slot: a tied figure with its own date, or words.
nonisolated struct PokerChanceSlot10868: Equatable {
    let label: String
    /// Nil shows `words`.
    let figure: String?
    let words: String
    /// The figure's own date, or the absence detail.
    let detail: String
    let pointID: String?
}

nonisolated struct PokerChanceComparisonModel10868: Equatable {
    let input: PokerChanceComparisonInput10868
    let history: FieldHistoryInput10868

    init(_ input: PokerChanceComparisonInput10868, history: FieldHistoryInput10868) {
        self.input = input
        self.history = history
    }

    /// The subject's series, only while exactly identified.
    var series: FieldHistorySeries10868? {
        history.series.first { $0.id == input.seriesID && FieldHistoryGeometry10868.isExactlyIdentified($0, in: history) }
    }

    /// The one point a reading names, only with the same raw value, a readable
    /// figure and its own readable date.
    func tied(_ reading: PokerChanceReading10868?) -> FieldHistoryPoint10868? {
        guard let reading, let series,
              FieldOutlookGeometry10868.fraction(reading.probability, ceiling: 1) != nil,
              FieldEventPageModel10868.readable(reading.figure) != nil,
              FieldEventPageModel10868.readable(reading.date) != nil,
              let point = FieldHistoryGeometry10868.uniquePoint(reading.pointID, in: series),
              point.probability == reading.probability
        else { return nil }
        return point
    }

    /// The before-table reading: a tied point the owner marks hollow (before
    /// the final table). A filled point is never relabelled before-table.
    var baselinePoint: FieldHistoryPoint10868? {
        guard let point = tied(input.baseline), point.style == .hollow else { return nil }
        return point
    }

    /// The inspected point, only while the history's own inspection rings
    /// exactly it; before the final table, only a hollow (before-table) point.
    var inspectedPoint: FieldHistoryPoint10868? {
        guard let series, let point = tied(input.inspected),
              FieldHistoryGeometry10868.inspectedPoint(series, in: history)?.id == point.id,
              input.role == .final || point.style == .hollow
        else { return nil }
        return point
    }

    /// The same exact position at the final: one slot.
    var sameObservation: Bool {
        guard input.role == .final, let baseline = baselinePoint, let inspected = inspectedPoint else { return false }
        return baseline.id == inspected.id
    }

    var inspectedLabel: String {
        switch input.role {
        case .beforeFinalTable: return input.copy.inspectedBeforeTableLabel
        case .final: return inspectedPoint?.style == .hollow ? input.copy.inspectedEarlierLabel : input.copy.recordedLabel
        }
    }

    private func slot(_ reading: PokerChanceReading10868?, point: FieldHistoryPoint10868?, label: String,
                      words: String, detail: String) -> PokerChanceSlot10868 {
        guard let reading, let point else {
            return PokerChanceSlot10868(label: label, figure: nil, words: words, detail: detail, pointID: nil)
        }
        return PokerChanceSlot10868(label: label, figure: reading.figure, words: reading.figure, detail: reading.date, pointID: point.id)
    }

    /// Before the final table: the inspected slot. At the final: the before-table
    /// slot and the inspected slot, or one slot for the same position.
    var slots: [PokerChanceSlot10868] {
        let copy = input.copy
        let inspected = slot(input.inspected, point: inspectedPoint, label: inspectedLabel,
                             words: copy.inspectedUnavailable, detail: copy.inspectedUnavailableDetail)
        switch input.role {
        case .beforeFinalTable:
            return [inspected]
        case .final:
            if sameObservation {
                return [slot(input.inspected, point: inspectedPoint, label: copy.sameObservationLabel,
                             words: copy.inspectedUnavailable, detail: copy.inspectedUnavailableDetail)]
            }
            let baseline = slot(input.baseline, point: baselinePoint, label: copy.baselineLabel,
                                words: copy.baselineUnavailable, detail: copy.baselineUnavailableDetail)
            return [baseline, inspected]
        }
    }

    /// The owner's result words, in the final role only.
    var result: String? {
        input.role == .final ? FieldEventPageModel10868.readable(input.result) : nil
    }

    static func spoken(_ slot: PokerChanceSlot10868) -> String {
        "\(slot.label): \(slot.words), \(slot.detail)"
    }

    /// The whole readout in the owner's words.
    var spoken: String {
        var parts = [input.name, input.meaning]
        if let result { parts.append("\(input.copy.resultLabel): \(result)") }
        parts += slots.map(Self.spoken)
        parts.append(input.copy.preTournamentUnavailable)
        return parts.compactMap { FieldEventPageModel10868.readable($0) }.joined(separator: ". ")
    }

    /// Side by side while both fit whole; stacked at accessibility sizes.
    static func arrangements(accessibilitySize: Bool) -> [FieldChooserArrangement10868] {
        accessibilitySize ? [.stacked] : [.sideBySide, .stacked]
    }
}

nonisolated enum PokerAccessibilityID10868 {
    static let page = "poker10868.page"
    static let heading = "poker10868.heading"
    static let about = "poker10868.about"
    static let anchor = "poker10868.anchor"
    static let comparison = "poker10868.comparison"
    static let comparisonUnavailable = "poker10868.comparison.unavailable"
    static let originalsUnavailable = "poker10868.originals.unavailable"
    static let stories = "poker10868.stories"
    static let allProps = "poker10868.allProps"
    static let unavailable = "poker10868.story.unavailable"
    static let readerHeader = "poker10868.readerHeader"
    static let readerAbout = "poker10868.readerHeader.about"
    static let chooser = "poker10868.chooser"
    static let catalogue = "poker10868.catalogue"
    static let original = "poker10868.original"
    static let sides = "poker10868.sides"
    static let outcome = "poker10868.outcome"
    static let aboutContent = "poker10868.aboutContent"
    static let chips = "poker10868.chips"
    static let chipsPlot = "poker10868.chips.plot"
    static let chipsSelected = "poker10868.chips.selected"
    static let chipsToggle = "poker10868.chips.toggle"
    static let chipsSource = "poker10868.chips.source"
    static let country = "poker10868.country"
    static let countryEntry = "poker10868.country.entry"
    static func card(_ card: PokerEventPageCard10868) -> String { "poker10868.card.\(card.rawValue)" }
    static func chipRow(_ outcomeID: String) -> String { "poker10868.chips.row.\(outcomeID)" }
    static func side(_ label: String) -> String { "poker10868.side.\(label)" }
}

/// The equal-size readouts; static content that speaks as one element.
struct PokerChanceComparisonPresentation10868: View {
    let input: PokerChanceComparisonInput10868
    let history: FieldHistoryInput10868

    @Environment(\.dynamicTypeSize) private var typeSize
    /// Every readout figure at this one size, never shrunk.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 29
    @ScaledMetric(relativeTo: .headline) private var keySize: CGFloat = 16

    var model: PokerChanceComparisonModel10868 { PokerChanceComparisonModel10868(input, history: history) }

    var body: some View {
        let model = self.model
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                if let series = model.series {
                    Canvas { context, size in
                        let center = CGPoint(x: size.width / 2, y: size.height / 2)
                        let path = FieldHistoryGeometry10868.markPath(series.shape, at: center, radius: size.width / 2 - 2)
                        context.fill(path, with: .color(series.tint))
                    }
                    .frame(width: keySize, height: keySize)
                    .accessibilityHidden(true)
                }
                Text(input.name)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(input.meaning)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let result = model.result {
                VStack(alignment: .leading, spacing: 2) {
                    Text(input.copy.resultLabel).font(.caption).foregroundStyle(DS.textSecondary)
                    Text(result).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            let slots = model.slots
            let tint = model.series?.tint ?? DS.textPrimary
            if PokerChanceComparisonModel10868.arrangements(accessibilitySize: typeSize.isAccessibilitySize) == [.stacked] || slots.count < 2 {
                VStack(alignment: .leading, spacing: 12) { slotViews(slots, tint: tint) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 20) { slotViews(slots, tint: tint) }
                        .fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 12) { slotViews(slots, tint: tint) }
                }
            }
            Text(input.copy.preTournamentUnavailable)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spoken)
        .accessibilityIdentifier(PokerAccessibilityID10868.comparison)
    }

    @ViewBuilder private func slotViews(_ slots: [PokerChanceSlot10868], tint: Color) -> some View {
        ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
            VStack(alignment: .leading, spacing: 4) {
                Text(slot.label)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let figure = slot.figure {
                    Text(figure)
                        .font(.system(size: figureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(tint)
                        .fixedSize()
                } else {
                    Text(slot.words)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(slot.detail)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

// MARK: - Chip share against win chance

/// One owner value on the chip card's scale with its owner words. Never divided here.
nonisolated struct PokerChipMeasure10868: Equatable {
    let value: Double
    let text: String
}

/// One owner row, in the owner's order.
nonisolated struct PokerChipRow10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's row label, kept beside the unavailable words when the row does not resolve.
    let label: String
    /// The owner's starting chip share.
    let share: PokerChipMeasure10868?
    /// The owner's before-table win chance, separately traded.
    let chance: PokerChipMeasure10868?
}

/// The selected player's two measures at one equal size.
nonisolated struct PokerChipSelected10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    let name: String
    let share: PokerChipMeasure10868?
    let chance: PokerChipMeasure10868?
    /// The win chance's own date; nil draws none.
    let chanceDate: String?
    /// The owner's reported finish and prize words; final role only.
    var result: String? = nil
}

nonisolated struct PokerChipCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    /// The filled measure's key.
    let shareKey: String
    /// The outlined measure's key.
    let chanceKey: String
    /// Words under the selected figures; nil draws none.
    let measureNote: String?
    /// Required: chip share is not win chance.
    let note: String
    let graphicLabel: String
    let shareUnavailable: String
    let chanceUnavailable: String
    let offScale: String
    let resultLabel: String
    let empty: String
    let chooseHint: String?
}

nonisolated struct PokerChipCardInput10868: Equatable {
    let scope: String
    let catalogue: [FieldChooserOriginal10868]
    let rows: [PokerChipRow10868]
    let selected: PokerChipSelected10868?
    /// The owner's one zero-based scale for both measures.
    let scale: FieldOutlookScale10868
    let copy: PokerChipCopy10868
    let unavailableWords: String
    /// The owner's leading/all rows control; nil draws none.
    var toggle: FieldHistoryAction10868? = nil
    /// The owner's source entry for the selected chance; nil draws none.
    var source: FieldHistoryAction10868? = nil
}

nonisolated struct PokerChipBar10868: Equatable {
    let row: PokerChipRow10868
    let resolution: FieldChooserResolution10868
    let share: FieldOutlookChance10868
    let chance: FieldOutlookChance10868
}

/// What one row's Canvas draws: the filled share above the outlined chance.
nonisolated struct PokerChipBarPlan10868: Equatable {
    let tickXs: [CGFloat]
    let share: CGRect?
    let shareZero: CGRect?
    let chance: CGRect?
    /// The chance outline's ink bound: its own extent.
    let chanceBounds: CGRect?
    let chanceZero: CGRect?
}

nonisolated struct PokerChipCardModel10868: Equatable {
    let input: PokerChipCardInput10868
    /// The chooser's resolver.
    let field: FieldChooserModel10868

    init(_ input: PokerChipCardInput10868) {
        self.input = input
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope, intro: nil,
            featured: FieldChooserFeatured10868(title: input.copy.title, badge: nil, refs: input.rows.map(\.ref),
                                                emptyWords: input.copy.empty),
            context: nil, more: nil, browse: nil, catalogue: input.catalogue, frame: nil, selected: nil,
            unavailableWords: input.unavailableWords, chooseHint: nil))
    }

    /// One measure on the owner's scale: placed, above it, or unavailable — never zero for unknown.
    func measure(_ measure: PokerChipMeasure10868?) -> FieldOutlookChance10868 {
        guard let measure, FieldEventPageModel10868.readable(measure.text) != nil, input.scale.isValid,
              measure.value.isFinite, measure.value >= 0, measure.value <= 1 else { return .unavailable }
        guard let fraction = FieldOutlookGeometry10868.fraction(measure.value, ceiling: input.scale.ceiling) else {
            return .offScale
        }
        return .value(probability: measure.value, fraction: fraction)
    }

    /// Every row in the owner's order. A repeated or unresolved row keeps its label and borrows nothing.
    var bars: [PokerChipBar10868] {
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for row in input.rows { counts[row.ref, default: 0] += 1 }
        return input.rows.map { row in
            let resolution: FieldChooserResolution10868 = (counts[row.ref] ?? 0) > 1 ? .unavailable : field.resolve(row.ref)
            guard resolution.original != nil else {
                return PokerChipBar10868(row: row, resolution: resolution, share: .unavailable, chance: .unavailable)
            }
            return PokerChipBar10868(row: row, resolution: resolution, share: measure(row.share), chance: measure(row.chance))
        }
    }

    var ticks: [FieldOutlookPlacedTick10868] {
        guard input.scale.isValid else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldOutlookGeometry10868.fraction(tick.probability, ceiling: input.scale.ceiling)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    /// Bars only beside the owner's valid scale and words.
    var showsPlot: Bool {
        input.scale.isValid && FieldEventPageModel10868.readable(input.scale.words) != nil && !input.rows.isEmpty
    }

    /// The selected player, only while it resolves exactly.
    var selected: PokerChipSelected10868? {
        guard let selected = input.selected, field.resolve(selected.ref).original != nil else { return nil }
        return selected
    }

    func isSelected(_ bar: PokerChipBar10868) -> Bool {
        guard let selected, let ref = bar.resolution.original?.ref else { return false }
        return ref == selected.ref
    }

    /// The reported finish and prize, in the final role only.
    func result(role: PokerEventPageRole10868) -> String? {
        role == .final ? FieldEventPageModel10868.readable(selected?.result) : nil
    }

    func chooseRef(_ bar: PokerChipBar10868, canChoose: Bool) -> FieldChooserOriginalRef10868? {
        canChoose ? bar.resolution.original?.ref : nil
    }

    /// The owner's words for a measure, or its own text.
    func words(_ chance: FieldOutlookChance10868, measure: PokerChipMeasure10868?, unavailable: String) -> String {
        switch chance {
        case .value: return measure?.text ?? unavailable
        case .offScale: return [measure?.text, input.copy.offScale].compactMap { $0 }.joined(separator: " · ")
        case .unavailable: return unavailable
        }
    }

    /// A selected figure: the owner's own text for a readable value in 0...1,
    /// else the unavailable words. A figure is not a bar, so no scale applies.
    func figure(_ measure: PokerChipMeasure10868?) -> String? {
        guard let measure, FieldEventPageModel10868.readable(measure.text) != nil,
              measure.value.isFinite, measure.value >= 0, measure.value <= 1 else { return nil }
        return measure.text
    }

    func shareWords(_ bar: PokerChipBar10868) -> String {
        words(bar.share, measure: bar.row.share, unavailable: input.copy.shareUnavailable)
    }

    func chanceWords(_ bar: PokerChipBar10868) -> String {
        words(bar.chance, measure: bar.row.chance, unavailable: input.copy.chanceUnavailable)
    }

    /// A row in words: name, both labelled measures, never one as the other.
    func rowSummary(_ bar: PokerChipBar10868) -> String {
        guard let original = bar.resolution.original else {
            return [bar.row.label, input.unavailableWords].compactMap { FieldEventPageModel10868.readable($0) }.joined(separator: ". ")
        }
        return "\(original.name). \(input.copy.shareKey): \(shareWords(bar)). \(input.copy.chanceKey): \(chanceWords(bar))"
    }

    /// The owner's action, live only with a callback, availability, readable words and a distinct id.
    func live(_ action: FieldHistoryAction10868?, canAct: Bool) -> FieldHistoryAction10868? {
        guard canAct, let action, action.isAvailable, FieldEventPageModel10868.readable(action.id) != nil,
              FieldEventPageModel10868.readable(action.label) != nil,
              [input.toggle, input.source].compactMap({ $0 }).filter({ $0.id == action.id }).count == 1
        else { return nil }
        return action
    }

    /// The one drawing plan: both bars on the same inset zero-to-ceiling span as the ticks.
    static func barPlan(share: Double?, chance: Double?, ticks: [Double], in size: CGSize,
                        barHeight: CGFloat, gap: CGFloat, lineWidth: CGFloat) -> PokerChipBarPlan10868? {
        let inset = FieldExpectationsGeometry10868.inset(markDiameter: lineWidth)
        guard barHeight.isFinite, barHeight > 0, gap.isFinite, gap >= 0, lineWidth.isFinite, lineWidth > 0,
              size.height.isFinite, size.height >= 2 * barHeight + gap,
              let zero = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let ceiling = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset)
        else { return nil }
        let span = CGSize(width: ceiling - zero, height: barHeight)
        let top = FieldOutlookGeometry10868.markPlan(fraction: share, in: span, orientation: .horizontal, selected: false)
        let bottom = FieldOutlookGeometry10868.markPlan(fraction: chance, in: span, orientation: .horizontal, selected: false)
        let lower = barHeight + gap
        let chanceBar = bottom.fill?.offsetBy(dx: zero, dy: lower)
        return PokerChipBarPlan10868(
            tickXs: ([0] + ticks).compactMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) },
            share: top.fill?.offsetBy(dx: zero, dy: 0),
            shareZero: top.zeroMark?.offsetBy(dx: zero, dy: 0),
            chance: chanceBar.map { HistoricalChanceGeometry10868.outline($0, lineWidth: lineWidth) },
            chanceBounds: chanceBar,
            chanceZero: bottom.zeroMark?.offsetBy(dx: zero, dy: lower))
    }
}

struct PokerChipCardPresentation10868: View {
    let input: PokerChipCardInput10868
    let role: PokerEventPageRole10868
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onAction: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var barHeight: CGFloat = 9
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    private let lineWidth: CGFloat = 1.5

    var model: PokerChipCardModel10868 { PokerChipCardModel10868(input) }

    /// Hands the row's exact original to the host, only while it acts.
    func choose(_ bar: PokerChipBar10868) {
        guard let ref = model.chooseRef(bar, canChoose: onChoose != nil), let onChoose else { return }
        onChoose(ref)
    }

    /// Hands the owner's exact action id back, only while it acts.
    func perform(_ action: FieldHistoryAction10868?) {
        guard let live = model.live(action, canAct: onAction != nil), let onAction else { return }
        onAction(live.id)
    }

    var body: some View {
        let model = self.model
        VStack(alignment: .leading, spacing: 12) {
            if let eyebrow = FieldEventPageModel10868.readable(input.copy.eyebrow) {
                Text(eyebrow).font(.caption.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
            Text(input.copy.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let selected = model.selected { selectedFigures(selected, model: model) }
            key
            if model.showsPlot { plot(model) }
            ownerWords(input.copy.note)
            if let toggle = model.live(input.toggle, canAct: onAction != nil) {
                link(toggle, id: PokerAccessibilityID10868.chipsToggle)
            }
            if let source = model.live(input.source, canAct: onAction != nil) {
                link(source, id: PokerAccessibilityID10868.chipsSource)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.chips)
    }

    private func selectedFigures(_ selected: PokerChipSelected10868, model: PokerChipCardModel10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(selected.name)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
                : AnyLayout(HStackLayout(alignment: .top, spacing: 20))
            layout {
                figure(input.copy.chanceKey, outlined: true, value: model.figure(selected.chance),
                       unavailable: input.copy.chanceUnavailable, detail: selected.chanceDate)
                figure(input.copy.shareKey, outlined: false, value: model.figure(selected.share),
                       unavailable: input.copy.shareUnavailable, detail: nil)
            }
            if let note = FieldEventPageModel10868.readable(input.copy.measureNote) { ownerWords(note) }
            if let result = model.result(role: role) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(input.copy.resultLabel).font(.caption).foregroundStyle(DS.textSecondary)
                    Text(result).font(.headline).foregroundStyle(DS.textPrimary).fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 4)
                .accessibilityElement(children: .combine)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.chipsSelected)
    }

    /// One measure at the card's one figure size; unavailable words wrap at a smaller size.
    private func figure(_ label: String, outlined: Bool, value: String?, unavailable: String,
                        detail: String?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 5) {
                swatch(outlined: outlined)
                Text(label).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
            if let value {
                Text(value)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(outlined ? DS.blue : DS.textPrimary)
                    .fixedSize()
            } else {
                Text(unavailable)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if value != nil, let detail = FieldEventPageModel10868.readable(detail) {
                Text(detail).font(.caption2).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func swatch(outlined: Bool) -> some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(outlined ? DS.cardBg : DS.textPrimary)
            .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(outlined ? DS.blue : Color.clear, lineWidth: lineWidth))
            .frame(width: 12, height: 7)
            .accessibilityHidden(true)
    }

    /// The two-measure key, in words beside each swatch.
    private var key: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 14))
        return layout {
            HStack(spacing: 5) { swatch(outlined: false); Text(input.copy.shareKey) }
            HStack(spacing: 5) { swatch(outlined: true); Text(input.copy.chanceKey) }
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    /// The axis once above every row, each row's bars on the same full width
    /// below its name and values, so both measures of every row share one scale.
    private func plot(_ model: PokerChipCardModel10868) -> some View {
        let bars = model.bars
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 10) {
            axis(ticks)
            ForEach(Array(bars.enumerated()), id: \.offset) { _, bar in
                chipRow(bar, ticks: ticks, model: model)
            }
            Text(input.scale.words)
                .font(.caption2)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.graphicLabel)
        .accessibilityIdentifier(PokerAccessibilityID10868.chipsPlot)
    }

    /// One row: a button only while it can choose; otherwise static. Either
    /// way it speaks its name and both labelled measures.
    @ViewBuilder private func chipRow(_ bar: PokerChipBar10868, ticks: [FieldOutlookPlacedTick10868],
                                      model: PokerChipCardModel10868) -> some View {
        let content = VStack(alignment: .leading, spacing: 4) {
            if typeSize.isAccessibilitySize {
                rowLabel(bar)
                rowValues(bar, model: model)
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        rowLabel(bar).frame(maxWidth: .infinity, alignment: .leading)
                        rowValues(bar, model: model)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        rowLabel(bar)
                        rowValues(bar, model: model)
                    }
                }
            }
            rowBars(bar, ticks: ticks)
        }
        .frame(maxWidth: .infinity, minHeight: controlSize, alignment: .leading)
        .contentShape(Rectangle())
        if model.chooseRef(bar, canChoose: onChoose != nil) != nil {
            Button { choose(bar) } label: { content }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.rowSummary(bar))
                .accessibilityAddTraits(.isButton)
                .accessibilityAddTraits(model.isSelected(bar) ? .isSelected : [])
                .accessibilityHint(input.copy.chooseHint ?? "")
                .accessibilityIdentifier(PokerAccessibilityID10868.chipRow(bar.row.ref.outcomeID))
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.rowSummary(bar))
                .accessibilityAddTraits(model.isSelected(bar) ? .isSelected : [])
                .accessibilityIdentifier(PokerAccessibilityID10868.chipRow(bar.row.ref.outcomeID))
        }
    }

    private func axis(_ ticks: [FieldOutlookPlacedTick10868]) -> some View {
        FieldExpectationsAxisLayout10868(
            units: ticks.map(\.fraction),
            inset: FieldExpectationsGeometry10868.inset(markDiameter: lineWidth),
            spacing: 6
        ) {
            ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                Text(tick.label).font(.caption2).foregroundStyle(DS.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityHidden(true)
    }

    private func rowLabel(_ bar: PokerChipBar10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                if model.isSelected(bar) {
                    Image(systemName: "checkmark").font(.caption2.weight(.bold)).accessibilityHidden(true)
                }
                Text(bar.resolution.original?.name ?? bar.row.label)
                    .font(.subheadline.weight(model.isSelected(bar) ? .semibold : .regular))
                    .fixedSize(horizontal: false, vertical: true)
            }
            if bar.resolution.original == nil {
                Text(input.unavailableWords).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .foregroundStyle(DS.textPrimary)
    }

    private func rowBars(_ bar: PokerChipBar10868, ticks: [FieldOutlookPlacedTick10868]) -> some View {
        let height = 2 * barHeight + 4
        return Canvas { context, size in
            guard let plan = PokerChipCardModel10868.barPlan(
                share: bar.share.fraction, chance: bar.chance.fraction, ticks: ticks.map(\.fraction),
                in: size, barHeight: barHeight, gap: 4, lineWidth: lineWidth) else { return }
            for x in plan.tickXs {
                var line = Path()
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(DS.border), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
            }
            if let share = plan.share { context.fill(Path(roundedRect: share, cornerRadius: 2), with: .color(DS.textPrimary)) }
            if let zero = plan.shareZero { context.fill(Path(zero), with: .color(DS.textPrimary)) }
            if let chance = plan.chance, let bounds = plan.chanceBounds {
                context.drawLayer { layer in
                    layer.clip(to: Path(bounds))
                    layer.fill(Path(bounds), with: .color(DS.cardBg))
                    layer.stroke(Path(roundedRect: chance, cornerRadius: 2), with: .color(DS.blue), lineWidth: lineWidth)
                }
            }
            if let zero = plan.chanceZero { context.fill(Path(zero), with: .color(DS.blue)) }
        }
        .frame(minWidth: 96, maxWidth: .infinity, minHeight: height, maxHeight: height)
        .accessibilityHidden(true)
    }

    /// Both measures in the owner's words, each beside its own key swatch.
    private func rowValues(_ bar: PokerChipBar10868, model: PokerChipCardModel10868) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            HStack(spacing: 4) { swatch(outlined: false); Text(model.shareWords(bar)).foregroundStyle(DS.textPrimary) }
            HStack(spacing: 4) { swatch(outlined: true); Text(model.chanceWords(bar)).foregroundStyle(DS.blue) }
        }
        .font(.caption.monospacedDigit())
        .fixedSize(horizontal: !typeSize.isAccessibilitySize, vertical: true)
    }

    private func link(_ action: FieldHistoryAction10868, id: String) -> some View {
        Button { perform(action) } label: {
            Text(action.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.blue)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: controlSize, alignment: .leading)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(action.spokenLabel ?? action.label)
        .accessibilityIdentifier(id)
    }

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Winner's country

nonisolated struct PokerCountryActual10868: Equatable {
    let label: String
    let words: String
    let detail: String?
}

nonisolated struct PokerCountryCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    let graphicLabel: String
    let chanceUnplaced: String
    let offScale: String
    /// Required: an unreported country stays unknown in the final role.
    let actualUnknown: String
    let actualLabel: String
    let note: String?
    /// The entry to both original outcomes; nil draws none.
    let entryLabel: String?
    let entryHint: String?
}

nonisolated struct PokerCountryCardInput10868: Equatable {
    let scope: String
    let catalogue: [FieldChooserOriginal10868]
    /// The country original's Yes side.
    let ref: FieldChooserOriginalRef10868
    /// The owner's labelled before-table Yes reading, or its absence words.
    let reading: FieldChooserReading10868
    /// The raw value behind `reading`, for the bar; nil draws none.
    let probability: Double?
    /// The reported winner's country; read in the final role only.
    let actual: PokerCountryActual10868?
    let scale: FieldOutlookScale10868
    let copy: PokerCountryCopy10868
    let unavailableWords: String
}

nonisolated struct PokerCountryCardModel10868: Equatable {
    let input: PokerCountryCardInput10868
    let field: FieldChooserModel10868

    init(_ input: PokerCountryCardInput10868) {
        self.input = input
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope, intro: nil,
            featured: FieldChooserFeatured10868(title: input.copy.title, badge: nil, refs: [input.ref], emptyWords: input.unavailableWords),
            context: nil, more: nil, browse: nil, catalogue: input.catalogue, frame: nil, selected: nil,
            unavailableWords: input.unavailableWords, chooseHint: nil))
    }

    var original: FieldChooserOriginal10868? { field.resolve(input.ref).original }

    /// The owner's reading while the original resolves; its own absence words as they are.
    var reading: FieldChooserReading10868? { original == nil ? nil : input.reading }

    /// The bar: only with a recorded reading and a raw probability on a valid scale.
    var chance: FieldOutlookChance10868 {
        guard original != nil, case .recorded = input.reading.value, let probability = input.probability,
              input.scale.isValid, probability.isFinite, probability >= 0, probability <= 1 else { return .unavailable }
        guard let fraction = FieldOutlookGeometry10868.fraction(probability, ceiling: input.scale.ceiling) else { return .offScale }
        return .value(probability: probability, fraction: fraction)
    }

    var ticks: [FieldOutlookPlacedTick10868] {
        guard input.scale.isValid else { return [] }
        return input.scale.ticks.compactMap { tick in
            FieldOutlookGeometry10868.fraction(tick.probability, ceiling: input.scale.ceiling)
                .map { FieldOutlookPlacedTick10868(label: tick.label, fraction: $0) }
        }
    }

    /// The reported country in the final role, or the owner's unknown words; nothing before.
    func actual(role: PokerEventPageRole10868) -> PokerCountryActual10868? {
        guard role == .final else { return nil }
        if let actual = input.actual, FieldEventPageModel10868.readable(actual.words) != nil { return actual }
        return PokerCountryActual10868(label: input.copy.actualLabel, words: input.copy.actualUnknown, detail: nil)
    }

    func entryRef(canOpen: Bool) -> FieldChooserOriginalRef10868? {
        guard canOpen, FieldEventPageModel10868.readable(input.copy.entryLabel) != nil else { return nil }
        return original?.ref
    }

    func barWords() -> String? {
        switch chance {
        case .value: return nil
        case .offScale: return input.copy.offScale
        case .unavailable: return input.copy.chanceUnplaced
        }
    }

    func summary(role: PokerEventPageRole10868) -> String {
        var parts: [String?] = [input.copy.eyebrow, input.copy.title]
        if let reading { parts.append(FieldChooserModel10868.spoken(reading)) } else { parts.append(input.unavailableWords) }
        if let reported = actual(role: role) { parts += [reported.label, reported.words, reported.detail] }
        return parts.compactMap { FieldEventPageModel10868.readable($0) }.joined(separator: ". ")
    }
}

struct PokerCountryCardPresentation10868: View {
    let input: PokerCountryCardInput10868
    let role: PokerEventPageRole10868
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil

    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 29
    @ScaledMetric(relativeTo: .caption) private var barHeight: CGFloat = 13
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @Environment(\.dynamicTypeSize) private var typeSize

    var model: PokerCountryCardModel10868 { PokerCountryCardModel10868(input) }

    func open() {
        guard let ref = model.entryRef(canOpen: onOpenOriginal != nil), let onOpenOriginal else { return }
        onOpenOriginal(ref)
    }

    var body: some View {
        let model = self.model
        VStack(alignment: .leading, spacing: 12) {
            if let eyebrow = FieldEventPageModel10868.readable(input.copy.eyebrow) {
                Text(eyebrow).font(.caption.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
            Text(input.copy.title)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 12))
                : AnyLayout(HStackLayout(alignment: .top, spacing: 24))
            layout {
                readingBlock(model)
                if let actual = model.actual(role: role) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(actual.label).font(.caption).foregroundStyle(DS.textSecondary)
                        Text(actual.words).font(.system(size: figureSize, weight: .bold)).foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        if let detail = FieldEventPageModel10868.readable(actual.detail) {
                            Text(detail).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            bar(model)
            if let note = FieldEventPageModel10868.readable(input.copy.note) {
                Text(note).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
            if model.entryRef(canOpen: onOpenOriginal != nil) != nil, let label = input.copy.entryLabel {
                Button(action: open) {
                    Text(label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, minHeight: controlSize, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint(input.copy.entryHint ?? "")
                .accessibilityIdentifier(PokerAccessibilityID10868.countryEntry)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.country)
    }

    @ViewBuilder private func readingBlock(_ model: PokerCountryCardModel10868) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            if let reading = model.reading {
                Text(reading.label).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                switch reading.value {
                case .recorded(let text, let detail):
                    Text(text).font(.system(size: figureSize, weight: .bold)).monospacedDigit().foregroundStyle(DS.blue).fixedSize()
                    Text(detail).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                case .missing(let words):
                    Text(words).font(.title3.weight(.semibold)).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(input.unavailableWords).font(.subheadline).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func bar(_ model: PokerCountryCardModel10868) -> some View {
        let ticks = model.ticks
        return VStack(alignment: .leading, spacing: 4) {
            Canvas { context, size in
                guard let plan = PokerChipCardModel10868.barPlan(
                    share: model.chance.fraction, chance: nil, ticks: ticks.map(\.fraction),
                    in: CGSize(width: size.width, height: 2 * barHeight), barHeight: barHeight, gap: 0, lineWidth: 1.5)
                else { return }
                for x in plan.tickXs {
                    var line = Path()
                    line.move(to: CGPoint(x: x, y: 0))
                    line.addLine(to: CGPoint(x: x, y: barHeight))
                    context.stroke(line, with: .color(DS.border), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                }
                if let fill = plan.share { context.fill(Path(roundedRect: fill, cornerRadius: barHeight / 2), with: .color(DS.blue)) }
                if let zero = plan.shareZero { context.fill(Path(zero), with: .color(DS.blue)) }
            }
            .frame(height: barHeight)
            if !ticks.isEmpty {
                FieldExpectationsAxisLayout10868(units: ticks.map(\.fraction),
                                                 inset: FieldExpectationsGeometry10868.inset(markDiameter: 1.5), spacing: 6) {
                    ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.label).font(.caption2).foregroundStyle(DS.textSecondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let words = model.barWords() {
                Text(words).font(.caption).foregroundStyle(DS.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(input.copy.graphicLabel)
        .accessibilityValue(model.summary(role: role))
    }
}

// MARK: - Original sides and the side's full history

/// One independent original side the owner offers. Never a complement.
/// Main-actor, like the shared Details selection it carries.
struct PokerOriginalSide10868: Equatable {
    let label: String
    /// The owner's meaning for this side.
    let meaning: String
    let selection: OriginalMarketDetails9483.Selection
}

struct PokerOriginalSides10868: Equatable {
    /// Spoken name of the side control.
    let label: String
    let sides: [PokerOriginalSide10868]
}

/// The host's originals with the owner role they were built for. Main-actor,
/// like the shared originals it carries.
struct PokerEventPageOriginals10868 {
    let role: PokerEventPageRole10868
    let originals: FieldEventPageOriginals10868
}

/// The held original side's full history: the same readouts and shared history.
nonisolated struct PokerOutcomeReaderInput10868: Equatable {
    let comparison: PokerChanceComparisonInput10868
    let history: FieldHistoryInput10868
    var readerPlotHeight: CGFloat? = nil
    /// The owner's words under the plot; nil draws none.
    let note: String?
}

// MARK: - Page

nonisolated struct PokerEventPageCopy10868: Equatable {
    let eyebrow: String?
    let title: String
    let context: String?
    /// The owner's lifecycle words; nil draws none.
    let status: String?
    let aboutLabel: String?
    let aboutHint: String?
    /// Shown instead of readouts whose role is not the page's.
    let comparisonUnavailable: String
    /// Shown instead of originals whose role is not the page's, or none.
    let originalsUnavailable: String
    let storiesLabel: String
    let storyUnavailable: String
    let allPropsLabel: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct PokerEventPageStory10868: Equatable {
    let cardID: String
    let card: PokerEventPageCard10868
    var reason: String? = nil
}

nonisolated struct PokerEventPageInput10868: Equatable {
    let role: PokerEventPageRole10868
    let copy: PokerEventPageCopy10868
    let reader: FieldEventPageReaderHeader10868
    let comparison: PokerChanceComparisonInput10868
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; used only when finite, positive and taller.
    var readerPlotHeight: CGFloat? = nil
    let chips: PokerChipCardInput10868?
    let country: PokerCountryCardInput10868?
    /// The chance-to-result card; mounted in the final role and its own final phase only.
    let result: HistoricalChanceInput10868?
    let stream: StoryStreamPresentation10868
    let stories: [PokerEventPageStory10868]
    let chooser: FieldChooserInput10868?
    let about: FieldEventPageAbout10868?
}

nonisolated struct PokerEventPageModel10868: Equatable {
    let input: PokerEventPageInput10868

    init(_ input: PokerEventPageInput10868) {
        self.input = input
    }

    /// The readouts, only in the page's own role — never coerced.
    var comparison: PokerChanceComparisonInput10868? {
        input.comparison.role == input.role ? input.comparison : nil
    }

    /// The owner's history with only its height and expand control changed.
    static func presented(_ history: FieldHistoryInput10868, plotHeight: CGFloat,
                          expand: FieldHistoryAction10868?) -> FieldHistoryInput10868 {
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
            plotAbsence: history.plotAbsence, showsKey: history.showsKey)
    }

    /// The page keeps the history's own height; full size is never shorter and
    /// only a finite, positive owner height enlarges it.
    func history(reader: Bool) -> FieldHistoryInput10868 {
        let history = input.history
        guard reader else { return history }
        return Self.presented(history,
                              plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight),
                              expand: nil)
    }

    /// The final-only chance-to-result card.
    var result: HistoricalChanceInput10868? {
        guard input.role == .final, let result = input.result, result.phase == .final else { return nil }
        return result
    }

    func isMounted(_ card: PokerEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .chips: input.chips != nil
        case .country: input.country != nil
        case .result: result != nil
        }
    }

    /// The owner's link a stream card id names: exactly one, to a mounted story.
    func story(_ cardID: String) -> PokerEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func readerShows(_ card: PokerEventPageCard10868) -> Bool { isMounted(card) }

    var about: FieldEventPageAbout10868? {
        guard let about = input.about,
              FieldEventPageModel10868.readable(about.title) != nil
                || about.paragraphs.contains(where: { FieldEventPageModel10868.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && FieldEventPageModel10868.readable(input.copy.aboutLabel) != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && FieldEventPageModel10868.readable(input.copy.allPropsLabel) != nil
    }

    /// The held original side's full history, only in the page's own role —
    /// never coerced and never borrowing the page's own subject. The one
    /// value the whole outcome mode reads: its readouts, history, note and
    /// every reader action.
    func outcome(_ outcome: PokerOutcomeReaderInput10868?) -> PokerOutcomeReaderInput10868? {
        guard let outcome, outcome.comparison.role == input.role else { return nil }
        return outcome
    }

    /// The outcome reader's history at full size, by the same height rule.
    static func outcomeHistory(_ outcome: PokerOutcomeReaderInput10868) -> FieldHistoryInput10868 {
        presented(outcome.history,
                  plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight(outcome.readerPlotHeight, history: outcome.history.plotHeight),
                  expand: nil)
    }
}

struct PokerEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: PokerEventPageInput10868
    var mode: PokerEventPageMode10868 = .page
    /// Every original and the held original side's Details, with their owner
    /// role; nil: neither.
    var originals: PokerEventPageOriginals10868? = nil
    /// The owner's independent Yes/No sides of the held original; nil draws none.
    var sides: PokerOriginalSides10868? = nil
    /// The held original side's full history; nil: none.
    var outcome: PokerOutcomeReaderInput10868? = nil
    var onAbout: (() -> Void)? = nil
    var onAllProps: (() -> Void)? = nil
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    var onOutcomeAction: ((String) -> Void)? = nil
    var onOutcomeInspectionChoice: ((String) -> Void)? = nil
    var onOutcomePlotPosition: ((Double) -> Void)? = nil
    /// Choosing a player, from the chip card or the chooser.
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onChooserControl: ((FieldChooserControl10868) -> Void)? = nil
    /// An exact original from a card, for the host's Details.
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// A card's own owner action id (the chip card's rows control and source entry).
    var onCardAction: ((String) -> Void)? = nil
    var onResultOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onResultDetails: (() -> Void)? = nil
    /// Called once before a page, chooser, catalogue, Details or side action reaches its owner.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: PokerEventPageModel10868 { PokerEventPageModel10868(input) }

    private func held<Value>(_ action: ((Value) -> Void)?) -> ((Value) -> Void)? {
        FieldEventPagePresentation10868.held(action, by: onInteraction)
    }

    /// A card's own no-value action, after the stream's activation when in the stream.
    static func relayAction(_ action: (() -> Void)?, through activation: StoryStreamCardActivation10868?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return {
            activation.request()
            action()
        }
    }

    // MARK: Leaves

    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    func comparisonContent(reader: Bool) -> PokerChanceComparisonPresentation10868? {
        model.comparison.map { PokerChanceComparisonPresentation10868(input: $0, history: model.history(reader: reader)) }
    }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: model.history(reader: reader),
            onAction: FieldEventPagePresentation10868.held(onHistoryAction, by: interaction),
            onInspectionChoice: FieldEventPagePresentation10868.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: FieldEventPagePresentation10868.held(onHistoryPlotPosition, by: interaction))
    }

    func chipsContent(activation: StoryStreamCardActivation10868? = nil) -> PokerChipCardPresentation10868? {
        input.chips.map {
            PokerChipCardPresentation10868(
                input: $0, role: input.role,
                onChoose: FieldEventPagePresentation10868.relay(onChoose, through: activation),
                onAction: FieldEventPagePresentation10868.relay(onCardAction, through: activation))
        }
    }

    func countryContent(activation: StoryStreamCardActivation10868? = nil) -> PokerCountryCardPresentation10868? {
        input.country.map {
            PokerCountryCardPresentation10868(
                input: $0, role: input.role,
                onOpenOriginal: FieldEventPagePresentation10868.relay(onOpenOriginal, through: activation))
        }
    }

    func resultContent(activation: StoryStreamCardActivation10868? = nil) -> HistoricalChanceResultPresentation10868? {
        model.result.map {
            HistoricalChanceResultPresentation10868(
                input: $0,
                onOpen: FieldEventPagePresentation10868.relay(onResultOpen, through: activation),
                onExpand: nil,
                onDetails: Self.relayAction(onResultDetails, through: activation))
        }
    }

    func chooserContent() -> FieldContenderChooserPresentation10868? {
        input.chooser.map {
            FieldContenderChooserPresentation10868(input: $0, onChoose: held(onChoose), onControl: held(onChooserControl))
        }
    }

    /// The one originals value every catalogue, Details, recorded-history and
    /// side consumer reads: only in the page's own role, never coerced.
    var admittedOriginals: FieldEventPageOriginals10868? {
        guard let originals, originals.role == input.role else { return nil }
        return originals.originals
    }

    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        admittedOriginals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: held(onOriginalSelect))
        }
    }

    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        admittedOriginals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: held(onOriginalHistory))
        }
    }

    /// A side acts only while it resolves exactly in the owner's catalogue.
    static func sideSelection(_ side: PokerOriginalSide10868, in originals: FieldEventPageOriginals10868?,
                              canSelect: Bool) -> OriginalMarketDetails9483.Selection? {
        guard canSelect, OriginalMarketDetails9483.original(in: originals?.catalogue, selection: side.selection) != nil
        else { return nil }
        return side.selection
    }

    /// The exact side a side control hands back, after the hook, only while it acts.
    func sideAction(_ side: PokerOriginalSide10868) -> (() -> Void)? {
        guard let selection = Self.sideSelection(side, in: admittedOriginals, canSelect: onOriginalSelect != nil),
              let action = held(onOriginalSelect) else { return nil }
        return { action(selection) }
    }

    /// The one outcome the whole outcome mode reads: role-matching, else none.
    var admittedOutcome: PokerOutcomeReaderInput10868? { model.outcome(outcome) }

    func outcomeComparisonContent() -> PokerChanceComparisonPresentation10868? {
        admittedOutcome.map {
            PokerChanceComparisonPresentation10868(input: $0.comparison, history: PokerEventPageModel10868.outcomeHistory($0))
        }
    }

    /// Full size: the exact callbacks, no hold. None without an admitted outcome.
    func outcomeHistoryContent() -> FieldProbabilityHistoryPresentation10868? {
        admittedOutcome.map {
            FieldProbabilityHistoryPresentation10868(
                input: PokerEventPageModel10868.outcomeHistory($0),
                onAction: onOutcomeAction, onInspectionChoice: onOutcomeInspectionChoice,
                onPlotPosition: onOutcomePlotPosition)
        }
    }

    /// The admitted outcome's own note, when readable.
    func outcomeNote() -> String? {
        FieldEventPageModel10868.readable(admittedOutcome?.note)
    }

    func aboutContent() -> FieldEventPageAboutContent10868? {
        model.about.map { FieldEventPageAboutContent10868(about: $0) }
    }

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
            case .chooser: chooserMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .outcome: outcomeMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            heading
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
        .accessibilityIdentifier(PokerAccessibilityID10868.page)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            stories
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            stories
                .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var heading: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = FieldEventPageModel10868.readable(input.copy.eyebrow) {
                    Text(eyebrow).font(.caption.weight(.semibold)).foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(input.copy.title)
                    .font(.title.bold())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let context = FieldEventPageModel10868.readable(input.copy.context) {
                    Text(context).font(.footnote).foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let status = FieldEventPageModel10868.readable(input.copy.status) {
                    Text(status).font(.footnote.weight(.semibold)).foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutAvailable(canOpen: onAbout != nil) {
                aboutButton(action: openPageAbout, id: PokerAccessibilityID10868.about)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.heading)
    }

    /// The readouts above the history, in one card, inline and full size.
    @ViewBuilder private func anchorContent(reader: Bool) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            if let comparison = comparisonContent(reader: reader) {
                comparison
            } else {
                Text(input.copy.comparisonUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(PokerAccessibilityID10868.comparisonUnavailable)
            }
            historyContent(reader: reader)
        }
    }

    private var anchor: some View {
        anchorContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(PokerCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PokerAccessibilityID10868.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
                Button(action: openAllProps) {
                    HStack(spacing: 8) {
                        Text(label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "chevron.right").font(.body.weight(.semibold)).accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .padding(.horizontal, 16)
                    .frame(minHeight: controlSize)
                    .modifier(PokerCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(PokerAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(PokerAccessibilityID10868.stories)
    }

    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = FieldEventPageModel10868.readable(link.reason) {
                    Text(reason).font(.subheadline).foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(PokerCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PokerAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(PokerCardSurface10868())
                .accessibilityIdentifier(PokerAccessibilityID10868.unavailable)
        }
    }

    @ViewBuilder private func cardContent(_ card: PokerEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: anchorContent(reader: true)
        case .chips: chipsContent(activation: activation)
        case .country: countryContent(activation: activation)
        case .result: resultContent(activation: activation)
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
        .accessibilityLabel(input.copy.aboutLabel ?? "")
        .accessibilityHint(input.copy.aboutHint ?? "")
        .accessibilityIdentifier(id)
    }

    // MARK: Full size and content modes

    @ViewBuilder private func reader(_ card: PokerEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                cardContent(card, activation: nil)
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
                    Text(state).font(.subheadline).foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if case .reader = mode, model.aboutAvailable(canOpen: onAbout != nil) {
                aboutButton(action: openAbout, id: PokerAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var chooserMode: some View {
        if let chooser = chooserContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                chooser
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PokerAccessibilityID10868.chooser)
        }
    }

    /// The admitted originals only; otherwise the owner's unavailable words, no action.
    private var catalogueMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            compactHeader
            if let catalogue = catalogueContent() {
                catalogue
            } else {
                originalsUnavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.catalogue)
    }

    /// The admitted held side's Details and its sides only; otherwise the
    /// owner's unavailable words with no side control.
    private var originalMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let details = originalDetailsContent() {
                if let sides, !sides.sides.isEmpty { sideControl(sides) }
                details
            } else {
                compactHeader
                originalsUnavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.original)
    }

    private var originalsUnavailable: some View {
        Text(input.copy.originalsUnavailable)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier(PokerAccessibilityID10868.originalsUnavailable)
    }

    /// A side is highlighted only as the admitted held selection.
    func isHighlighted(_ side: PokerOriginalSide10868) -> Bool {
        admittedOriginals?.selection == side.selection
    }

    private func sideControl(_ sides: PokerOriginalSides10868) -> some View {
        HStack(spacing: 8) {
            ForEach(Array(sides.sides.enumerated()), id: \.offset) { _, side in
                let selected = isHighlighted(side)
                let content = VStack(spacing: 2) {
                    Text(side.label).font(.subheadline.weight(selected ? .semibold : .regular))
                    Text(side.meaning).font(.caption2).foregroundStyle(DS.textSecondary)
                        .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(selected ? DS.blue : DS.textPrimary)
                .padding(.horizontal, 10)
                .frame(maxWidth: .infinity, minHeight: controlSize)
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(selected ? DS.blue : DS.border, lineWidth: selected ? 2 : 1))
                .contentShape(Rectangle())
                Group {
                    if let action = sideAction(side) {
                        Button(action: action) { content }.buttonStyle(.plain)
                    } else {
                        content.accessibilityElement(children: .combine)
                    }
                }
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier(PokerAccessibilityID10868.side(side.label))
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(sides.label)
        .accessibilityIdentifier(PokerAccessibilityID10868.sides)
    }

    /// The admitted outcome only; otherwise the owner's unavailable words with
    /// no outcome content and no action.
    @ViewBuilder private var outcomeMode: some View {
        VStack(alignment: .leading, spacing: 14) {
            compactHeader
            if let comparison = outcomeComparisonContent(), let history = outcomeHistoryContent() {
                comparison
                history
                if let note = outcomeNote() {
                    Text(note).font(.caption).foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(input.copy.comparisonUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(PokerAccessibilityID10868.comparisonUnavailable)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PokerAccessibilityID10868.outcome)
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PokerAccessibilityID10868.aboutContent)
        }
    }
}

/// The reference's white card on the page surface.
private struct PokerCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
