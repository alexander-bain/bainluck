import SwiftUI

// #10868 — the economics EARNINGS page: a binary market on whether a company's
// reported diluted earnings per share is strictly greater than a threshold
// fixed when the contract was created. A fan sees the dated pre-report chance
// to beat that threshold beside the company's reported actual — two different
// units, each with its own date and phase — and, once admitted, the market's
// separately admitted contract result; the recorded probability journey as the
// anchor; the actual against the fixed threshold on an honest dollar axis from
// zero with the baseline chance beside it; and the original record, its rules
// and its sources.
//
// Presentation only, from the approved earnings composition (visual and
// semantic reference only). Its evidence loader, pre-report observation rule,
// gap rule, phase rehearsal controls, probability, money and clock formatting,
// difference arithmetic, catalogue eligibility and sheets are NOT ported. All of
// that is the owner's input.
//
// Why a new composition: every existing page headline pairs probabilities with
// sporting scores, phases and race state (the field headline, the match pages,
// the chance-to-result story); none pairs a chance with a per-share money
// actual, and no existing actual-versus-expectation leaf keeps money units —
// the handicap card counts sporting units, the chance-to-result bar is a
// probability. The page reuses everything else.
//
// What is mounted, unchanged:
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, on a copy that
//     changes only its readout (the esports page's baseline collapse, which
//     shows one slot only when the inspected observation is the exact one the
//     pre-report reading is bound to), its height (the finite, never-shorter
//     full-size height from `RugbyMatchEventPageModel10868.readerPlotHeight`)
//     and its expand control (`RugbyMatchEventPageModel10868.presentationCopy`).
//     Its points, runs, breaks, hollow marks, ticks and inspection are the owner's.
//   • `RugbyMatchEventPageSectionsContent10868` — compact Info and the owner's
//     source documents, with exact link and source callbacks.
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     the original, its Details, rules, older quote and side history, carried
//     in `FieldEventPageOriginals10868`.
//   • `StoryStreamPresentationView10868` — the story stream; a card's own
//     actions request the stream's interaction first.
//   • `FieldEventPageReaderHeader10868` and the field page's hold helpers and
//     arrangement rule.
//
// Built here, because nothing existing draws it: the paired headline
// (`EarningsHeadlinePresentation10868`) and the earnings-against-threshold
// card (`EarningsComparisonPresentation10868`), each a pure model over the
// owner's words, plus the page composition.
//
// Phase admission: the owner hands one bundle carrying its own phase. Every
// surface and every action — headline, card, history, Info, sources,
// catalogue, Details, side history, stream and reader steps — reads that one
// bundle, and only while its phase is exactly the page's. Otherwise each
// surface shows the owner's unavailable words with no content and no callback;
// Back stays. No phase is forced, defaulted or coerced, and a fact the bundle
// carries for a later phase is never shown in an earlier one.
//
// Truth: every figure, date, label and word is the owner's, verbatim. A dated
// chance is shown only with a readable id, figure and date and a placement
// inside 0…1; the company's actual is known by its readable id, figure and
// date alone, and its dollar placement decides only whether its bar is drawn
// (off the axis: the owner's off-axis words, never clamped or rescaled).
// Otherwise the owner's unavailable words — never a zero, a neighbour or the
// other unit. The chance is a probability and stays on the
// 0–100% history; the actual and the threshold are money and stay on the
// dollar axis; the difference between them is the owner's money words, never
// a probability movement, and the threshold is fixed, never a projection. The
// contract result is independent of the company's actual and is never
// inferred from it. This layer never formats, never computes a difference, a
// placement or a baseline, never elects an observation, never settles, never
// adds a point, a complement, an endpoint or a smoothed line to the history,
// and never reads a schedule or a close as the company's publication.
//
// Actions: on the page, an action outside the stream calls the owner's
// interaction hook once, then the exact callback with its exact value; a story
// card's own action requests the stream's interaction instead (that request
// is the hold). The catalogue, Details, Info and source content are held the
// same way. Full-size content, its steps and Back keep the exact callbacks
// with no hold. Without a callback there is no control; building or laying
// out calls nothing.
//
// Layout: phone stacks the headline above the history, then the stories; a
// regular or unspecified width places the headline beside the history while
// each keeps its minimum width; accessibility sizes always stack. Words wrap
// and grow with Dynamic Type; every action is at least 44pt.
//
// The host owns the scroll, sheets, navigation, focus, swipe, the held
// selections and inspection, arrivals and every update. This view keeps no
// state, runs no timer or animation, holds no subscription and presents
// nothing of its own.

// MARK: - Phase, cards and dated readings

/// The owner's admitted phase of the page and of a bundle.
nonisolated enum EarningsEventPagePhase10868: String, Hashable, CaseIterable {
    /// Before the company's report: the dated chance and the fixed threshold.
    case beforeReport
    /// The company has reported; the contract result is withheld.
    case companyReport
    /// The market's separately admitted result is shown as well.
    case settled
}

/// The page's full-size cards.
nonisolated enum EarningsEventPageCard10868: String, Hashable, CaseIterable {
    /// The recorded probability journey.
    case history
    /// The actual against the fixed threshold.
    case earnings
}

/// One owner reading with its own identity, figure and date. The placement is
/// the reading's position on its own axis (a probability on 0–100%, or a
/// fraction of the owner's dollar axis) — geometry the owner computed.
nonisolated struct EarningsDatedReading10868: Equatable {
    let id: String
    /// Formatted by the owner, shown verbatim.
    let figure: String
    /// The reading's own full date in the owner's local words.
    let date: String
    let placement: Double
}

/// A reading as a surface shows it.
nonisolated enum EarningsReadingDisplay10868: Equatable {
    case value(figure: String, date: String)
    /// The owner's words for a missing or unreadable reading.
    case unavailable(String)
}

/// The owner's fixed contract threshold, in the owner's words. Not a reading:
/// never dated, never moving.
nonisolated struct EarningsThreshold10868: Equatable {
    let label: String
    let figure: String
    /// The contract's comparison rule, verbatim.
    let rule: String
}

/// The market's separately admitted contract result.
nonisolated struct EarningsResult10868: Equatable {
    let words: String
    /// Where the result comes from; nil stays unsaid.
    let provenance: String?
}

nonisolated enum EarningsResultDisplay10868: Equatable {
    case result(words: String, provenance: String?)
    case unavailable(String)
}

/// The owner's money words for the actual's distance from the threshold.
nonisolated struct EarningsDelta10868: Equatable {
    let label: String
    let figure: String
}

/// The rules every dated reading and result follows, on every surface.
nonisolated enum EarningsReadingRule10868 {
    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// A finite position inside its axis; real 0 and real 1 included.
    static func isPlacement(_ value: Double) -> Bool {
        value.isFinite && value >= 0 && value <= 1
    }

    /// Known: a readable id, figure and date. Says nothing about drawing.
    static func isKnown(_ reading: EarningsDatedReading10868?) -> Bool {
        guard let reading else { return false }
        return readable(reading.id) != nil && readable(reading.figure) != nil && readable(reading.date) != nil
    }

    /// A probability reading: known AND placed inside 0…1. Otherwise unknown.
    static func isShown(_ reading: EarningsDatedReading10868?) -> Bool {
        guard let reading else { return false }
        return isKnown(reading) && isPlacement(reading.placement)
    }

    /// A probability reading as shown: the 0…1 rule applies.
    static func display(_ reading: EarningsDatedReading10868?, unavailable: String) -> EarningsReadingDisplay10868 {
        guard let reading, isShown(reading) else { return .unavailable(unavailable) }
        return .value(figure: reading.figure, date: reading.date)
    }

    /// A money reading as shown: known by its own id, figure and date alone.
    /// Its axis placement only decides whether a bar is drawn, never whether
    /// the reported figure is known.
    static func known(_ reading: EarningsDatedReading10868?, unavailable: String) -> EarningsReadingDisplay10868 {
        guard let reading, isKnown(reading) else { return .unavailable(unavailable) }
        return .value(figure: reading.figure, date: reading.date)
    }

    /// The result with readable words; its provenance only when readable.
    static func result(_ result: EarningsResult10868?, unavailable: String) -> EarningsResultDisplay10868 {
        guard let result, let words = readable(result.words) else { return .unavailable(unavailable) }
        return .result(words: words, provenance: readable(result.provenance))
    }
}

// MARK: - Paired headline

/// The owner's headline: the pre-report chance beside the company's actual,
/// each in its own unit with its own date, and the contract result once
/// admitted. These are evidence roles, never sporting score labels.
nonisolated struct EarningsHeadlineInput10868: Equatable {
    let eyebrow: String?
    let title: String
    /// The bundle's phase statement in the owner's words.
    let phaseWords: String
    let chanceLabel: String
    /// What the chance is a chance of, in the owner's words.
    let chanceSubject: String
    /// The owner's dated pre-report observation.
    let chance: EarningsDatedReading10868?
    let threshold: EarningsThreshold10868
    let actualLabel: String
    /// The actual's unit in the owner's words.
    let actualUnit: String
    /// The owner's money words relating the actual to the threshold; shown
    /// only beside a shown actual.
    let actualRelation: String?
    /// The company's reported actual, dated by its own publication.
    let actual: EarningsDatedReading10868?
    /// Shown in the company-report phase where the result is withheld.
    let settlementWithheld: String
    let resultLabel: String
    let result: EarningsResult10868?
    let resultUnavailable: String
    /// Settled only: the owner's reminder that the pre-report chance stands.
    let reminder: String?
    let readingUnavailable: String
    let aboutLabel: String
    let aboutHint: String?
}

/// One part of the headline, in the order it mounts.
nonisolated enum EarningsHeadlinePart10868: Hashable, CaseIterable {
    case eyebrow
    case title
    case phase
    case chance
    /// Before the report: the fixed threshold.
    case threshold
    case actual
    /// The company-report phase's withheld-settlement words.
    case settlement
    case result
    case reminder
}

/// What the headline shows at one phase. Later facts never reach an earlier phase.
nonisolated struct EarningsHeadlineModel10868: Equatable {
    let phase: EarningsEventPagePhase10868
    let input: EarningsHeadlineInput10868

    init(phase: EarningsEventPagePhase10868, input: EarningsHeadlineInput10868) {
        self.phase = phase
        self.input = input
    }

    static func parts(_ phase: EarningsEventPagePhase10868) -> [EarningsHeadlinePart10868] {
        switch phase {
        case .beforeReport: return [.eyebrow, .title, .phase, .chance, .threshold]
        case .companyReport: return [.eyebrow, .title, .phase, .chance, .actual, .settlement]
        case .settled: return [.eyebrow, .title, .phase, .chance, .actual, .result, .reminder]
        }
    }

    var parts: [EarningsHeadlinePart10868] { Self.parts(phase) }

    /// The pre-report chance, in every phase — kept as recorded.
    var chance: EarningsReadingDisplay10868 {
        EarningsReadingRule10868.display(input.chance, unavailable: input.readingUnavailable)
    }

    /// The actual, only after the report — known by its own id, figure and
    /// date, independent of any axis.
    var actual: EarningsReadingDisplay10868? {
        guard phase != .beforeReport else { return nil }
        return EarningsReadingRule10868.known(input.actual, unavailable: input.readingUnavailable)
    }

    /// The relation, only beside a shown actual.
    var relation: String? {
        guard case .value? = actual else { return nil }
        return EarningsReadingRule10868.readable(input.actualRelation)
    }

    /// The contract result, only once settled.
    var result: EarningsResultDisplay10868? {
        guard phase == .settled else { return nil }
        return EarningsReadingRule10868.result(input.result, unavailable: input.resultUnavailable)
    }

    /// Every word one part draws, in order; nothing for a part this phase does not mount.
    func words(_ part: EarningsHeadlinePart10868) -> [String] {
        guard parts.contains(part) else { return [] }
        switch part {
        case .eyebrow:
            return [EarningsReadingRule10868.readable(input.eyebrow)].compactMap { $0 }
        case .title:
            return [EarningsReadingRule10868.readable(input.title)].compactMap { $0 }
        case .phase:
            return [EarningsReadingRule10868.readable(input.phaseWords)].compactMap { $0 }
        case .chance:
            switch chance {
            case .value(let figure, let date): return [input.chanceLabel, figure, input.chanceSubject, date]
            case .unavailable(let words): return [input.chanceLabel, words, input.chanceSubject]
            }
        case .threshold:
            return [input.threshold.label, input.threshold.figure, input.threshold.rule]
        case .actual:
            switch actual {
            case .value(let figure, let date)?:
                return [input.actualLabel, figure, input.actualUnit] + [relation].compactMap { $0 } + [date]
            case .unavailable(let words)?:
                return [input.actualLabel, words, input.actualUnit]
            case nil:
                return []
            }
        case .settlement:
            return [input.settlementWithheld]
        case .result:
            switch result {
            case .result(let words, let provenance)?: return [input.resultLabel, words] + [provenance].compactMap { $0 }
            case .unavailable(let words)?: return [input.resultLabel, words]
            case nil: return []
            }
        case .reminder:
            return [EarningsReadingRule10868.readable(input.reminder)].compactMap { $0 }
        }
    }

    var words: [String] { parts.flatMap { words($0) } }

    var spokenChance: String {
        switch chance {
        case .value(let figure, let date): return "\(input.chanceLabel): \(figure) \(input.chanceSubject), \(date)"
        case .unavailable(let words): return "\(input.chanceLabel): \(words)"
        }
    }

    var spokenActual: String? {
        switch actual {
        case .value(let figure, let date)?:
            let pieces = [figure, input.actualUnit] + [relation].compactMap { $0 } + [date]
            return "\(input.actualLabel): \(pieces.joined(separator: ", "))"
        case .unavailable(let words)?:
            return "\(input.actualLabel): \(words)"
        case nil:
            return nil
        }
    }

    var spokenResult: String? {
        switch result {
        case .result(let words, let provenance)?:
            return "\(input.resultLabel): \(([words] + [provenance].compactMap { $0 }).joined(separator: ", "))"
        case .unavailable(let words)?:
            return "\(input.resultLabel): \(words)"
        case nil:
            return nil
        }
    }
}

// MARK: - Earnings against the fixed threshold

/// One owner tick on the dollar axis.
nonisolated struct EarningsAxisTick10868: Equatable {
    /// The owner's position on the axis, 0…1.
    let placement: Double
    let label: String
}

/// The owner's dollar axis. Drawn only from exactly zero to a finite upper
/// bound; positions on it are the owner's placements.
nonisolated struct EarningsAxis10868: Equatable {
    let lower: Double
    let upper: Double
    let ticks: [EarningsAxisTick10868]
    /// The axis words, verbatim.
    let words: String
    /// Shown with the axis when a known actual or the threshold has no
    /// position on it. Nothing is clamped or rescaled.
    let offAxis: String
    /// Shown in place of the bar when the axis cannot be drawn.
    let unavailable: String
}

/// The owner's earnings card: the actual against the fixed threshold, with
/// the dated pre-report chance beside the bar — never on it.
nonisolated struct EarningsComparisonInput10868: Equatable {
    let eyebrow: String?
    let baselineLabel: String
    let baselineSubject: String
    let baseline: EarningsDatedReading10868?
    /// The owner's title for this phase.
    let title: String
    let threshold: EarningsThreshold10868
    /// The threshold's position on the dollar axis, from the owner.
    let thresholdPlacement: Double
    let actualLabel: String
    /// The company's reported actual; its placement is on the dollar axis.
    let actual: EarningsDatedReading10868?
    let delta: EarningsDelta10868?
    /// The actual's unit and period in the owner's words.
    let unit: String
    let axis: EarningsAxis10868
    /// The bar's complete spoken description, from the owner.
    let summary: String
    let caption: String?
    let settlementWithheld: String
    let resultLabel: String
    let result: EarningsResult10868?
    let resultUnavailable: String
    let readingUnavailable: String
}

/// One part of the earnings card, in the order it mounts.
nonisolated enum EarningsComparisonPart10868: Hashable, CaseIterable {
    case eyebrow
    case baseline
    case title
    /// Before the report the threshold; after it the actual and its difference.
    case figures
    case unit
    /// The dollar axis, its ticks, the threshold marker and the actual bar.
    case bar
    /// After the report: the threshold beside the actual's bar.
    case threshold
    case caption
    case settlement
    case result
}

/// The one filled extent the bar draws from zero.
nonisolated enum EarningsBarExtent10868: Equatable {
    /// Before the report: a muted extent to the fixed threshold — the number to beat.
    case threshold(Double)
    /// After the report: the known actual's extent to its own placement.
    case actual(Double)
}

/// Pure placement rules of the dollar axis.
nonisolated enum EarningsComparisonGeometry10868 {
    /// From exactly zero to a finite, larger upper bound.
    static func isValid(_ axis: EarningsAxis10868) -> Bool {
        axis.lower == 0 && axis.upper.isFinite && axis.upper > axis.lower
    }

    /// A placement's horizontal position across a finite width. Never clamped.
    static func x(_ placement: Double, width: CGFloat) -> CGFloat? {
        guard EarningsReadingRule10868.isPlacement(placement), width.isFinite, width > 0 else { return nil }
        return width * CGFloat(placement)
    }
}

/// What the earnings card shows at one phase.
nonisolated struct EarningsComparisonModel10868: Equatable {
    let phase: EarningsEventPagePhase10868
    let input: EarningsComparisonInput10868

    init(phase: EarningsEventPagePhase10868, input: EarningsComparisonInput10868) {
        self.phase = phase
        self.input = input
    }

    static func parts(_ phase: EarningsEventPagePhase10868) -> [EarningsComparisonPart10868] {
        switch phase {
        case .beforeReport: return [.eyebrow, .baseline, .title, .figures, .unit, .bar, .caption]
        case .companyReport: return [.eyebrow, .baseline, .title, .figures, .unit, .bar, .threshold, .caption, .settlement]
        case .settled: return [.eyebrow, .baseline, .title, .figures, .unit, .bar, .threshold, .caption, .result]
        }
    }

    var parts: [EarningsComparisonPart10868] { Self.parts(phase) }

    var baseline: EarningsReadingDisplay10868 {
        EarningsReadingRule10868.display(input.baseline, unavailable: input.readingUnavailable)
    }

    /// The actual, only after the report — known by its own id, figure and
    /// date, whether or not the bar can draw it.
    var actual: EarningsReadingDisplay10868? {
        guard phase != .beforeReport else { return nil }
        return EarningsReadingRule10868.known(input.actual, unavailable: input.readingUnavailable)
    }

    /// The owner's difference words, only beside a shown actual.
    var delta: EarningsDelta10868? {
        guard case .value? = actual, let delta = input.delta,
              EarningsReadingRule10868.readable(delta.label) != nil,
              EarningsReadingRule10868.readable(delta.figure) != nil else { return nil }
        return delta
    }

    var result: EarningsResultDisplay10868? {
        guard phase == .settled else { return nil }
        return EarningsReadingRule10868.result(input.result, unavailable: input.resultUnavailable)
    }

    var isDrawable: Bool { EarningsComparisonGeometry10868.isValid(input.axis) }

    /// The owner's ticks that sit on the axis with words, in the owner's order.
    var ticks: [EarningsAxisTick10868] {
        guard isDrawable else { return [] }
        return input.axis.ticks.filter {
            EarningsReadingRule10868.isPlacement($0.placement) && EarningsReadingRule10868.readable($0.label) != nil
        }
    }

    var thresholdPlacement: Double? {
        guard isDrawable, EarningsReadingRule10868.isPlacement(input.thresholdPlacement) else { return nil }
        return input.thresholdPlacement
    }

    /// The actual's bar end: a known actual after the report whose own
    /// placement sits on a drawable axis. Never clamped.
    var actualPlacement: Double? {
        guard isDrawable, case .value? = actual, let reading = input.actual,
              EarningsReadingRule10868.isPlacement(reading.placement) else { return nil }
        return reading.placement
    }

    /// The bar's filled extent from zero: the threshold's before the report,
    /// the actual's after it — each only at its own validated placement.
    var barExtent: EarningsBarExtent10868? {
        switch phase {
        case .beforeReport: return thresholdPlacement.map { .threshold($0) }
        case .companyReport, .settled: return actualPlacement.map { .actual($0) }
        }
    }

    /// The owner's off-axis words, while the axis draws but the known actual
    /// or the threshold has no position on it.
    var offAxis: String? {
        guard isDrawable else { return nil }
        let actualOff: Bool
        if case .value? = actual { actualOff = actualPlacement == nil } else { actualOff = false }
        guard actualOff || thresholdPlacement == nil else { return nil }
        return EarningsReadingRule10868.readable(input.axis.offAxis)
    }

    var barSpoken: String {
        guard isDrawable else { return input.axis.unavailable }
        return ([input.summary] + [offAxis].compactMap { $0 }).joined(separator: " ")
    }

    func words(_ part: EarningsComparisonPart10868) -> [String] {
        guard parts.contains(part) else { return [] }
        switch part {
        case .eyebrow:
            return [EarningsReadingRule10868.readable(input.eyebrow)].compactMap { $0 }
        case .baseline:
            switch baseline {
            case .value(let figure, let date): return [input.baselineLabel, input.baselineSubject, figure, date]
            case .unavailable(let words): return [input.baselineLabel, input.baselineSubject, words]
            }
        case .title:
            return [EarningsReadingRule10868.readable(input.title)].compactMap { $0 }
        case .figures:
            switch actual {
            case nil:
                return [input.threshold.label, input.threshold.figure]
            case .value(let figure, let date)?:
                return [input.actualLabel, figure, date] + (delta.map { [$0.label, $0.figure] } ?? [])
            case .unavailable(let words)?:
                return [input.actualLabel, words]
            }
        case .unit:
            return [EarningsReadingRule10868.readable(input.unit)].compactMap { $0 }
        case .bar:
            guard isDrawable else { return [input.axis.unavailable] }
            return ticks.map(\.label) + [EarningsReadingRule10868.readable(input.axis.words), offAxis].compactMap { $0 }
        case .threshold:
            return [input.threshold.label, input.threshold.figure, input.threshold.rule]
        case .caption:
            return [EarningsReadingRule10868.readable(input.caption)].compactMap { $0 }
        case .settlement:
            return [input.settlementWithheld]
        case .result:
            switch result {
            case .result(let words, let provenance)?: return [input.resultLabel, words] + [provenance].compactMap { $0 }
            case .unavailable(let words)?: return [input.resultLabel, words]
            case nil: return []
            }
        }
    }

    var words: [String] { parts.flatMap { words($0) } }

    var spokenBaseline: String {
        switch baseline {
        case .value(let figure, let date): return "\(input.baselineLabel), \(input.baselineSubject): \(figure), \(date)"
        case .unavailable(let words): return "\(input.baselineLabel), \(input.baselineSubject): \(words)"
        }
    }

    var spokenActual: String? {
        switch actual {
        case .value(let figure, let date)?: return "\(input.actualLabel): \(figure), \(date)"
        case .unavailable(let words)?: return "\(input.actualLabel): \(words)"
        case nil: return nil
        }
    }
}

// MARK: - Info control

/// The owner's About control: never smaller than 44pt at any text size, and
/// growing with larger text. It runs exactly the action it is given.
struct EarningsInfoControl10868: View {
    let label: String
    let hint: String?
    let action: () -> Void

    @ScaledMetric(relativeTo: .body) private var scaledTarget: CGFloat = 44

    static let minimumTarget: CGFloat = 44

    /// The hit frame for a scaled metric: floored at 44pt, larger as text grows.
    static func targetSize(_ scaled: CGFloat) -> CGFloat {
        guard scaled.isFinite else { return minimumTarget }
        return max(minimumTarget, scaled)
    }

    var body: some View {
        Button(action: action) {
            Image(systemName: "info.circle")
                .font(.title3)
                .foregroundStyle(DS.textPrimary)
                .frame(minWidth: Self.targetSize(scaledTarget), minHeight: Self.targetSize(scaledTarget))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityHint(hint ?? "")
    }
}

// MARK: - Headline view

/// The paired headline: the chance first and prominent, the other unit in its
/// own slot beside it, each with its own date. Static text plus the About
/// control while a callback exists.
struct EarningsHeadlinePresentation10868: View {
    let model: EarningsHeadlineModel10868
    /// The owner's About; nil draws no control.
    var onAbout: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .largeTitle) private var chanceSize: CGFloat = 40
    @ScaledMetric(relativeTo: .title) private var otherSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var slotMinWidth: CGFloat = 150

    private typealias ID = EarningsEventPageAccessibilityID10868

    private var input: EarningsHeadlineInput10868 { model.input }

    /// The About control's action: a callback and readable words, else none.
    var aboutAction: (() -> Void)? {
        guard EarningsReadingRule10868.readable(input.aboutLabel) != nil else { return nil }
        return onAbout
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(model.words(.eyebrow), id: \.self) { eyebrow in
                        Text(eyebrow)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                    }
                    ForEach(model.words(.title), id: \.self) { title in
                        Text(title)
                            .font(.title2.weight(.bold))
                            .foregroundStyle(DS.textPrimary)
                            .accessibilityAddTraits(.isHeader)
                    }
                    ForEach(model.words(.phase), id: \.self) { phase in
                        Text(phase)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if let action = aboutAction {
                    EarningsInfoControl10868(label: input.aboutLabel, hint: input.aboutHint, action: action)
                        .accessibilityIdentifier(ID.headlineAbout)
                }
            }
            pair
            ForEach(model.words(.settlement), id: \.self) { words in
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(ID.headlineSettlement)
            }
            if let spoken = model.spokenResult {
                resultRow
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(spoken)
                    .accessibilityIdentifier(ID.headlineResult)
            }
            ForEach(model.words(.reminder), id: \.self) { reminder in
                Text(reminder)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Slots

    @ViewBuilder private var pair: some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 12) {
                chanceSlot
                otherSlot
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 12) {
                    chanceSlot.frame(minWidth: slotMinWidth, alignment: .topLeading)
                    otherSlot.frame(minWidth: slotMinWidth, alignment: .topLeading)
                }
                VStack(alignment: .leading, spacing: 12) {
                    chanceSlot
                    otherSlot
                }
            }
        }
    }

    private var chanceSlot: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.chanceLabel)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            switch model.chance {
            case .value(let figure, let date):
                Text(figure)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                Text(input.chanceSubject)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
                Text(date)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
            case .unavailable(let words):
                Text(words)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                Text(input.chanceSubject)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spokenChance)
        .accessibilityIdentifier(ID.chance)
    }

    /// Before the report the fixed threshold; after it the company's actual.
    @ViewBuilder private var otherSlot: some View {
        if model.parts.contains(.threshold) {
            thresholdSlot
        } else if model.parts.contains(.actual) {
            actualSlot
        }
    }

    private var thresholdSlot: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.threshold.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            Text(input.threshold.figure)
                .font(.system(size: otherSize, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
            Text(input.threshold.rule)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(ID.headlineThreshold)
    }

    private var actualSlot: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(model.words(.actual).enumerated()), id: \.offset) { index, words in
                Text(words)
                    .font(actualFont(index))
                    .foregroundStyle(index == 1 ? DS.textPrimary : DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spokenActual ?? "")
        .accessibilityIdentifier(ID.actual)
    }

    /// The label, then the figure (or the owner's unavailable words), then the unit, relation and date.
    private func actualFont(_ index: Int) -> Font {
        switch index {
        case 0:
            return .subheadline.weight(.semibold)
        case 1:
            if case .value? = model.actual { return .system(size: otherSize, weight: .semibold) }
            return .title3.weight(.semibold)
        default:
            return .footnote
        }
    }

    private var resultRow: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(model.words(.result).enumerated()), id: \.offset) { index, words in
                Text(words)
                    .font(index == 1 ? .body.weight(.semibold) : .footnote)
                    .foregroundStyle(index == 1 ? DS.textPrimary : DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Earnings card view

/// The earnings card: the baseline chance beside the bar, the owner's title,
/// the figures in money, and the actual's bar against the dashed fixed
/// threshold on the owner's dollar axis from zero. Static; it acts on nothing.
struct EarningsComparisonPresentation10868: View {
    let model: EarningsComparisonModel10868

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title2) private var baselineSize: CGFloat = 24
    @ScaledMetric(relativeTo: .body) private var barHeight: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var tickLength: CGFloat = 5

    private typealias ID = EarningsEventPageAccessibilityID10868
    private typealias Geometry = EarningsComparisonGeometry10868

    private var input: EarningsComparisonInput10868 { model.input }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(model.parts, id: \.self) { part in
                partView(part)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func partView(_ part: EarningsComparisonPart10868) -> some View {
        switch part {
        case .eyebrow:
            lines(model.words(.eyebrow), font: .caption.weight(.semibold), color: DS.textSecondary)
        case .baseline:
            baselineRow
        case .title:
            lines(model.words(.title), font: .title3.weight(.semibold), color: DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
        case .figures:
            figures
        case .unit:
            lines(model.words(.unit), font: .footnote, color: DS.textSecondary)
        case .bar:
            bar
        case .threshold:
            thresholdRow
        case .caption:
            lines(model.words(.caption), font: .subheadline, color: DS.textSecondary)
        case .settlement:
            lines(model.words(.settlement), font: .subheadline.weight(.semibold), color: DS.textSecondary)
                .accessibilityIdentifier(ID.cardSettlement)
        case .result:
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(model.words(.result).enumerated()), id: \.offset) { index, words in
                    Text(words)
                        .font(index == 1 ? .body.weight(.semibold) : .footnote)
                        .foregroundStyle(index == 1 ? DS.textPrimary : DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(ID.cardResult)
        }
    }

    private func lines(_ words: [String], font: Font, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(words.enumerated()), id: \.offset) { _, line in
                Text(line).font(font).foregroundStyle(color)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Baseline and figures

    private var baselineRow: some View {
        let labels = VStack(alignment: .leading, spacing: 2) {
            Text(input.baselineLabel).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
            Text(input.baselineSubject).font(.footnote).foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        let reading = VStack(alignment: .trailing, spacing: 2) {
            switch model.baseline {
            case .value(let figure, let date):
                Text(figure)
                    .font(.system(size: baselineSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                Text(date).font(.footnote).foregroundStyle(DS.textSecondary)
            case .unavailable(let words):
                Text(words).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        return Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) {
                    labels
                    reading
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) {
                        labels.frame(maxWidth: .infinity, alignment: .leading)
                        reading
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        labels
                        reading
                    }
                }
            }
        }
        .padding(12)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spokenBaseline)
        .accessibilityIdentifier(ID.baseline)
    }

    private var figures: some View {
        VStack(alignment: .leading, spacing: 4) {
            switch model.actual {
            case nil:
                Text(input.threshold.label).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
                Text(input.threshold.figure)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
            case .value(let figure, let date)?:
                Text(input.actualLabel).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
                Text(figure)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                Text(date).font(.footnote).foregroundStyle(DS.textSecondary)
                if let delta = model.delta {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(delta.label).font(.subheadline).foregroundStyle(DS.textSecondary)
                        Text(delta.figure).font(.subheadline.weight(.semibold)).monospacedDigit().foregroundStyle(DS.textPrimary)
                    }
                }
            case .unavailable(let words)?:
                Text(input.actualLabel).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
                Text(words).font(.title3.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(ID.figures)
    }

    private var thresholdRow: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(input.threshold.label).font(.subheadline).foregroundStyle(DS.textSecondary)
                Text(input.threshold.figure).font(.subheadline.weight(.semibold)).monospacedDigit().foregroundStyle(DS.textPrimary)
            }
            Text(input.threshold.rule).font(.footnote).foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(ID.cardThreshold)
    }

    // MARK: Dollar bar

    @ViewBuilder private var bar: some View {
        if model.isDrawable {
            VStack(alignment: .leading, spacing: 4) {
                GeometryReader { proxy in
                    barGraphic(width: proxy.size.width)
                }
                .frame(height: barHeight + tickLength + 8)
                EarningsAxisTickLayout10868(placements: model.ticks.map(\.placement)) {
                    ForEach(Array(model.ticks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.label).font(.caption).monospacedDigit().foregroundStyle(DS.textSecondary)
                    }
                }
                lines([EarningsReadingRule10868.readable(input.axis.words), model.offAxis].compactMap { $0 },
                      font: .caption, color: DS.textSecondary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.barSpoken)
            .accessibilityIdentifier(ID.bar)
        } else {
            Text(input.axis.unavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(ID.bar)
        }
    }

    /// The track from zero, the one filled extent (muted to the threshold
    /// before the report, the actual after it), the dashed threshold at its
    /// own placement and the tick marks. Nothing is clamped.
    private func barGraphic(width: CGFloat) -> some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(DS.surface)
                .frame(width: max(0, width), height: barHeight)
                .offset(y: 4)
            switch model.barExtent {
            case .threshold(let end)?:
                if let extent = Geometry.x(end, width: width) {
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(DS.border)
                        .frame(width: extent, height: barHeight)
                        .offset(y: 4)
                }
            case .actual(let end)?:
                if let extent = Geometry.x(end, width: width) {
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(DS.blue)
                        .frame(width: extent, height: barHeight)
                        .offset(y: 4)
                }
            case nil:
                EmptyView()
            }
            Path { path in
                for tick in model.ticks {
                    guard let position = Geometry.x(tick.placement, width: width) else { continue }
                    path.move(to: CGPoint(x: position, y: barHeight + 4))
                    path.addLine(to: CGPoint(x: position, y: barHeight + 4 + tickLength))
                }
            }
            .stroke(DS.border, lineWidth: 1)
            if let placement = model.thresholdPlacement, let position = Geometry.x(placement, width: width) {
                Path { path in
                    path.move(to: CGPoint(x: position, y: 0))
                    path.addLine(to: CGPoint(x: position, y: barHeight + 8))
                }
                .stroke(DS.textPrimary, style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
            }
        }
        .frame(width: max(0, width), alignment: .topLeading)
    }
}

/// Places each tick label centred on its own placement, kept inside the
/// width; labels that would touch move to a further row. Labels only: the
/// tick marks themselves stay at their exact placements.
struct EarningsAxisTickLayout10868: Layout {
    let placements: [Double]
    var gap: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let width = Self.usableWidth(proposal.width, sizes: sizes, gap: gap)
        return CGSize(width: width, height: Self.plan(width: width, sizes: sizes, placements: placements, gap: gap).height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let arranged = Self.plan(width: bounds.width, sizes: sizes, placements: placements, gap: gap)
        for (index, subview) in subviews.enumerated() where index < arranged.origins.count {
            let origin = arranged.origins[index]
            subview.place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y),
                          anchor: .topLeading, proposal: .unspecified)
        }
    }

    static func usableWidth(_ proposed: CGFloat?, sizes: [CGSize], gap: CGFloat) -> CGFloat {
        if let proposed, proposed.isFinite, proposed > 0 { return proposed }
        return sizes.reduce(0) { $0 + $1.width + gap }
    }

    /// Each label's origin and the total height, rows stacked by first fit.
    static func plan(width: CGFloat, sizes: [CGSize], placements: [Double],
                     gap: CGFloat) -> (origins: [CGPoint], height: CGFloat) {
        var occupied: [[ClosedRange<CGFloat>]] = []
        var rowHeights: [CGFloat] = []
        var columns: [(x: CGFloat, row: Int)] = []
        let extent = width.isFinite ? max(0, width) : 0
        let pad = gap.isFinite ? max(0, gap) : 0
        for (index, size) in sizes.enumerated() {
            let labelWidth = size.width.isFinite ? max(0, size.width) : 0
            let labelHeight = size.height.isFinite ? max(0, size.height) : 0
            let fraction = index < placements.count && EarningsReadingRule10868.isPlacement(placements[index]) ? placements[index] : 0
            let centre = extent * CGFloat(fraction)
            let left = min(max(0, centre - labelWidth / 2), max(0, extent - labelWidth))
            let span = (left - pad)...(left + labelWidth + pad)
            var row = 0
            while row < occupied.count && occupied[row].contains(where: { $0.overlaps(span) }) {
                row += 1
            }
            if row == occupied.count {
                occupied.append([])
                rowHeights.append(0)
            }
            occupied[row].append(left...(left + labelWidth))
            rowHeights[row] = max(rowHeights[row], labelHeight)
            columns.append((x: left, row: row))
        }
        var tops: [CGFloat] = []
        var top: CGFloat = 0
        for height in rowHeights {
            tops.append(top)
            top += height + pad / 2
        }
        let origins = columns.map { CGPoint(x: $0.x, y: tops[$0.row]) }
        return (origins, rowHeights.isEmpty ? 0 : top - pad / 2)
    }
}

// MARK: - Page input

/// A full-size reader step.
nonisolated enum EarningsReaderStep10868: String, Hashable, CaseIterable {
    case previous
    case next
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct EarningsEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: EarningsEventPageCard10868
    /// The owner's words for why this story is here; nil draws none.
    var reason: String? = nil
}

/// One stop in the owner's full-size reader order, with its full name.
nonisolated struct EarningsReaderStop10868: Equatable {
    let card: EarningsEventPageCard10868
    let name: String
}

/// The bundle's own words for the page around its leaves.
nonisolated struct EarningsEventPageBundleCopy10868: Equatable {
    /// Spoken name of the stories group.
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story.
    let storyUnavailable: String
    /// Shown full size for a card the owner's reader order does not list once.
    let readerUnavailable: String
    /// Shown in source mode when the id names no single source.
    let sourceUnavailable: String
    /// The control that opens a source document from Info.
    let sourceLabel: String
    /// The earnings card's entry to the held original's Details; nil draws none.
    let detailsLabel: String?
    /// The entry to every original; nil draws none.
    let allPropsLabel: String?
    let previousLabel: String
    let nextLabel: String
}

/// Everything one admitted phase shows. Every surface and every action reads
/// this one bundle, and only while its phase is the page's.
struct EarningsEventPageBundle10868 {
    let phase: EarningsEventPagePhase10868
    let headline: EarningsHeadlineInput10868
    let comparison: EarningsComparisonInput10868
    let history: FieldHistoryInput10868
    /// The compact words above full-size, catalogue, Details, Info and source content.
    let reader: FieldEventPageReaderHeader10868
    /// Opened by the About controls; nil: no control.
    let about: RugbyMatchEventPageAbout10868?
    /// Every source document Info may open, by exact id.
    let sources: [RugbyMatchEventPageSource10868]
    let stream: StoryStreamPresentation10868
    let stories: [EarningsEventPageStory10868]
    /// The owner's full-size order for Previous and Next.
    let readerOrder: [EarningsReaderStop10868]
    let copy: EarningsEventPageBundleCopy10868
    /// The original, its Details and side history; nil: none.
    var originals: FieldEventPageOriginals10868? = nil
}

/// The page's own words, independent of any bundle.
nonisolated struct EarningsEventPageCopy10868: Equatable {
    /// Shown on every surface while the bundle's phase is not the page's.
    let phaseUnavailable: String
    let backLabel: String
}

struct EarningsEventPageInput10868 {
    /// The page's admitted phase.
    let phase: EarningsEventPagePhase10868
    let bundle: EarningsEventPageBundle10868
    let copy: EarningsEventPageCopy10868
    /// The owner's full-size plot height; used only when finite, positive and taller.
    var readerPlotHeight: CGFloat? = nil
}

/// What the host's container is showing, chosen by the host.
nonisolated enum EarningsEventPageMode10868: Equatable {
    case page
    case reader(EarningsEventPageCard10868)
    case catalogue
    case original
    case about
    /// One owner source document, by exact id.
    case source(String)
}

nonisolated enum EarningsEventPageAccessibilityID10868 {
    static let page = "earnings10868.page"
    static let hero = "earnings10868.hero"
    static let headline = "earnings10868.headline"
    static let headlineAbout = "earnings10868.headline.about"
    static let chance = "earnings10868.headline.chance"
    static let headlineThreshold = "earnings10868.headline.threshold"
    static let actual = "earnings10868.headline.actual"
    static let headlineSettlement = "earnings10868.headline.settlement"
    static let headlineResult = "earnings10868.headline.result"
    static let anchor = "earnings10868.anchor"
    static let stories = "earnings10868.stories"
    static let storyUnavailable = "earnings10868.story.unavailable"
    static let baseline = "earnings10868.earnings.baseline"
    static let figures = "earnings10868.earnings.figures"
    static let bar = "earnings10868.earnings.bar"
    static let cardThreshold = "earnings10868.earnings.threshold"
    static let cardSettlement = "earnings10868.earnings.settlement"
    static let cardResult = "earnings10868.earnings.result"
    static let details = "earnings10868.earnings.details"
    static let allProps = "earnings10868.allProps"
    static let phaseUnavailable = "earnings10868.phaseUnavailable"
    static let back = "earnings10868.back"
    static let readerHeader = "earnings10868.readerHeader"
    static let readerAbout = "earnings10868.readerHeader.about"
    static let readerUnavailable = "earnings10868.reader.unavailable"
    static let catalogue = "earnings10868.catalogue"
    static let original = "earnings10868.original"
    static let about = "earnings10868.about"
    static let source = "earnings10868.source"
    static let sourceUnavailable = "earnings10868.source.unavailable"
    static func card(_ card: EarningsEventPageCard10868) -> String { "earnings10868.card.\(card.rawValue)" }
    static func step(_ step: EarningsReaderStep10868) -> String { "earnings10868.step.\(step.rawValue)" }
}

// MARK: - Page model

/// What the page mounts, resolved from the one admitted bundle.
struct EarningsEventPageModel10868 {
    let input: EarningsEventPageInput10868

    init(_ input: EarningsEventPageInput10868) {
        self.input = input
    }

    /// The owner's bundle, only at the page's own phase — never coerced.
    var bundle: EarningsEventPageBundle10868? {
        input.bundle.phase == input.phase ? input.bundle : nil
    }

    var headline: EarningsHeadlineModel10868? {
        bundle.map { EarningsHeadlineModel10868(phase: $0.phase, input: $0.headline) }
    }

    var comparison: EarningsComparisonModel10868? {
        bundle.map { EarningsComparisonModel10868(phase: $0.phase, input: $0.comparison) }
    }

    /// The history the page or full size draws: the owner's, with the
    /// pre-report pair collapsed only when the inspected observation is the
    /// exact one the pre-report reading is bound to, and only its height and
    /// expand control changed. Full size is never shorter.
    func history(reader: Bool) -> FieldHistoryInput10868? {
        guard let bundle else { return nil }
        let owned = EsportsEventPageModel10868.baselineCopy(bundle.history)
        return RugbyMatchEventPageModel10868.presentationCopy(
            owned,
            plotHeight: reader
                ? RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: owned.plotHeight)
                : owned.plotHeight,
            expand: reader ? nil : owned.expand,
            showsKey: owned.showsKey)
    }

    /// The one story a stream card id names; several, even identical, are none.
    func story(_ cardID: String) -> EarningsEventPageStory10868? {
        guard let bundle else { return nil }
        let matches = bundle.stories.filter { $0.cardID == cardID }
        return matches.count == 1 ? matches[0] : nil
    }

    // MARK: Reader order

    /// A card's place in the owner's order: listed exactly once with a readable name.
    private func position(_ card: EarningsEventPageCard10868) -> Int? {
        guard let bundle else { return nil }
        let indices = bundle.readerOrder.indices.filter { bundle.readerOrder[$0].card == card }
        guard indices.count == 1, EarningsReadingRule10868.readable(bundle.readerOrder[indices[0]].name) != nil else { return nil }
        return indices[0]
    }

    func readerShows(_ card: EarningsEventPageCard10868) -> Bool {
        position(card) != nil
    }

    /// The owner's exact neighbour — never the enum's order, never a duplicate.
    func neighbour(_ step: EarningsReaderStep10868, of card: EarningsEventPageCard10868) -> EarningsReaderStop10868? {
        guard let bundle, let index = position(card) else { return nil }
        let target = step == .previous ? index - 1 : index + 1
        guard bundle.readerOrder.indices.contains(target) else { return nil }
        let stop = bundle.readerOrder[target]
        return position(stop.card) == target ? stop : nil
    }

    /// The step's spoken words: its label and the neighbour's full name.
    func stepSpoken(_ step: EarningsReaderStep10868, from card: EarningsEventPageCard10868) -> String? {
        guard let bundle, let stop = neighbour(step, of: card) else { return nil }
        let label = step == .previous ? bundle.copy.previousLabel : bundle.copy.nextLabel
        return "\(label), \(stop.name)"
    }

    // MARK: Info, sources and originals

    var about: RugbyMatchEventPageAbout10868? {
        guard let about = bundle?.about,
              RugbyMatchEventPageModel10868.readable(about.title) != nil
                || about.sections.contains(where: { RugbyMatchEventPageModel10868.hasWords($0) })
        else { return nil }
        return about
    }

    /// Ids naming exactly one owner source.
    var sourceIDs: Set<String> {
        guard let bundle else { return [] }
        let ids = bundle.sources.map(\.id)
        return Set(ids.filter { id in
            EarningsReadingRule10868.readable(id) != nil && ids.filter { $0 == id }.count == 1
        })
    }

    func source(_ id: String) -> RugbyMatchEventPageSource10868? {
        guard let bundle, sourceIDs.contains(id) else { return nil }
        return bundle.sources.first { $0.id == id }
    }

    var originals: FieldEventPageOriginals10868? { bundle?.originals }

    /// The held original, only when it resolves exactly in its own scope.
    var heldOriginal: OriginalMarketDetails9483.Selection? {
        guard let originals, let selection = originals.selection,
              OriginalMarketDetails9483.original(in: originals.catalogue, selection: selection) != nil else { return nil }
        return selection
    }
}

// MARK: - Page view

struct EarningsEventPagePresentation10868: View {
    typealias Model = EarningsEventPageModel10868
    typealias Card = EarningsEventPageCard10868
    typealias ID = EarningsEventPageAccessibilityID10868
    typealias Stream = StoryStreamPresentation10868

    let input: EarningsEventPageInput10868
    var mode: EarningsEventPageMode10868 = .page
    /// Opens the host's container on the owner's Info.
    var onAbout: (() -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// The held original's exact selection, for the host's Details.
    var onOpenOriginal: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onAllProps: (() -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// The owner's exact neighbouring card, from a full-size step.
    var onReaderStep: ((Card) -> Void)? = nil
    var onBack: (() -> Void)? = nil
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// A section's exact external link, for the host to open.
    var onLink: ((RugbyMatchEventPageLink10868) -> Void)? = nil
    /// A source document's exact id, for the host to open.
    var onSource: ((String) -> Void)? = nil
    /// Called once before a page, catalogue, Details, Info or source action reaches its owner.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 440
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420

    static let minimumTarget: CGFloat = 44

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

    /// The same for an action without a value.
    func placedAction(_ action: (() -> Void)?, at place: Place) -> (() -> Void)? {
        switch place {
        case .page:
            return FieldEventPagePresentation10868.heldAction(action, by: onInteraction)
        case .stream(let activation):
            guard let action else { return nil }
            return {
                activation.request()
                action()
            }
        case .reader:
            return action
        }
    }

    // MARK: Actions — each exactly what its control runs

    /// The About controls: only for the admitted bundle's Info with words.
    func aboutAction(at place: Place) -> (() -> Void)? {
        guard let bundle = model.bundle, model.about != nil,
              EarningsReadingRule10868.readable(bundle.headline.aboutLabel) != nil else { return nil }
        return placedAction(onAbout, at: place)
    }

    /// The earnings card's Details entry: the held original's exact selection.
    func detailsAction(at place: Place) -> (() -> Void)? {
        guard let bundle = model.bundle, EarningsReadingRule10868.readable(bundle.copy.detailsLabel) != nil,
              let selection = model.heldOriginal, let open = placed(onOpenOriginal, at: place) else { return nil }
        return { open(selection) }
    }

    func allPropsAction() -> (() -> Void)? {
        guard let bundle = model.bundle, bundle.originals != nil,
              EarningsReadingRule10868.readable(bundle.copy.allPropsLabel) != nil else { return nil }
        return placedAction(onAllProps, at: .page)
    }

    /// The stream shell's own intents, exactly, for the admitted bundle only.
    func storyIntent() -> ((Stream.Intent) -> Void)? {
        guard model.bundle != nil else { return nil }
        return onStoryIntent
    }

    /// Previous or Next from a full-size card: the owner's exact neighbour.
    func stepAction(_ step: EarningsReaderStep10868, from card: Card) -> (() -> Void)? {
        guard let stop = model.neighbour(step, of: card), let onReaderStep else { return nil }
        let target = stop.card
        return { onReaderStep(target) }
    }

    /// Back: exact, in every mode, whatever the bundle.
    func backAction() -> (() -> Void)? {
        guard EarningsReadingRule10868.readable(input.copy.backLabel) != nil else { return nil }
        return onBack
    }

    // MARK: Content — nil for a refused bundle

    func headlineContent() -> EarningsHeadlinePresentation10868? {
        model.headline.map { EarningsHeadlinePresentation10868(model: $0, onAbout: aboutAction(at: .page)) }
    }

    func comparisonContent() -> EarningsComparisonPresentation10868? {
        model.comparison.map { EarningsComparisonPresentation10868(model: $0) }
    }

    /// The history on the page (held) or full size (exact).
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868? {
        historyContent(at: reader ? .reader : .page, reader: reader)
    }

    /// The history as `place` reaches its actions — a story card relays through the stream.
    func historyContent(at place: Place, reader: Bool) -> FieldProbabilityHistoryPresentation10868? {
        guard let shown = model.history(reader: reader) else { return nil }
        return FieldProbabilityHistoryPresentation10868(
            input: shown,
            onAction: placed(onHistoryAction, at: place),
            onInspectionChoice: placed(onHistoryInspectionChoice, at: place),
            onPlotPosition: placed(onHistoryPlotPosition, at: place))
    }

    func aboutContent() -> RugbyMatchEventPageSectionsContent10868? {
        guard let bundle = model.bundle, let about = model.about else { return nil }
        return RugbyMatchEventPageSectionsContent10868(
            title: about.title, sections: about.sections, sourceIDs: model.sourceIDs,
            sourceLabel: bundle.copy.sourceLabel,
            onLink: placed(onLink, at: .page), onSource: placed(onSource, at: .page))
    }

    func sourceContent(_ id: String) -> RugbyMatchEventPageSectionsContent10868? {
        guard let bundle = model.bundle, let source = model.source(id) else { return nil }
        return RugbyMatchEventPageSectionsContent10868(
            title: source.title, sections: source.sections, sourceIDs: [],
            sourceLabel: bundle.copy.sourceLabel, onLink: placed(onLink, at: .page), onSource: nil)
    }

    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        model.originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: placed(onOriginalSelect, at: .page))
        }
    }

    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        model.originals.map {
            OriginalMarketDetailsView9483(catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                                          recorded: $0.recorded, onHistory: placed(onOriginalHistory, at: .page))
        }
    }

    // MARK: Words

    /// Every word the earnings card reaches at `place`: the card's words and,
    /// while it acts, the Details entry. Nothing for a refused bundle.
    func earningsWords(at place: Place) -> [String] {
        guard let bundle = model.bundle, let card = model.comparison else { return [] }
        return card.words + (detailsAction(at: place) == nil ? [] : [bundle.copy.detailsLabel].compactMap { $0 })
    }

    // MARK: Body

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            case .source(let id): sourceMode(id)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private static func isReader(_ place: Place) -> Bool {
        if case .reader = place { return true }
        return false
    }

    // MARK: Page

    @ViewBuilder private var page: some View {
        if model.bundle != nil {
            VStack(alignment: .leading, spacing: 20) {
                hero
                stories
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.page)
        } else {
            unavailable
        }
    }

    /// The owner's words for a refused bundle: no content, no callback.
    private var unavailable: some View {
        Text(input.copy.phaseUnavailable)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .modifier(EarningsCardSurface10868())
            .accessibilityIdentifier(ID.phaseUnavailable)
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

    @ViewBuilder private var headlineCard: some View {
        if let headline = headlineContent() {
            headline
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(EarningsCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(ID.headline)
        }
    }

    @ViewBuilder private var anchorCard: some View {
        if let history = historyContent(reader: false) {
            history
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(EarningsCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(ID.anchor)
        }
    }

    @ViewBuilder private var stories: some View {
        if let bundle = model.bundle {
            VStack(alignment: .leading, spacing: 16) {
                StoryStreamPresentationView10868(bundle.stream, onIntent: storyIntent()) { card, activation in
                    storyCell(card, activation)
                }
                if let action = allPropsAction(), let label = EarningsReadingRule10868.readable(bundle.copy.allPropsLabel) {
                    entryButton(label, inCard: false, action: action)
                        .accessibilityIdentifier(ID.allProps)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(bundle.copy.storiesLabel)
            .accessibilityIdentifier(ID.stories)
        }
    }

    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let story = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = EarningsReadingRule10868.readable(story.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardBody(story.card, at: .stream(activation))
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(EarningsCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(ID.card(story.card))
        } else if let bundle = model.bundle {
            Text(bundle.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(EarningsCardSurface10868())
                .accessibilityIdentifier(ID.storyUnavailable)
        }
    }

    /// A card's body — the same on the page, in the stream and full size.
    @ViewBuilder private func cardBody(_ card: Card, at place: Place) -> some View {
        switch card {
        case .history:
            if let history = historyContent(at: place, reader: Self.isReader(place)) {
                history
            }
        case .earnings:
            earningsCard(at: place)
        }
    }

    @ViewBuilder private func earningsCard(at place: Place) -> some View {
        if let bundle = model.bundle, let content = comparisonContent() {
            VStack(alignment: .leading, spacing: 12) {
                content
                if let action = detailsAction(at: place), let label = EarningsReadingRule10868.readable(bundle.copy.detailsLabel) {
                    entryButton(label, inCard: true, action: action)
                        .accessibilityIdentifier(ID.details)
                }
            }
        }
    }

    private func entryButton(_ label: String, inCard: Bool, action: @escaping () -> Void) -> some View {
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
            .padding(.horizontal, inCard ? 12 : 16)
            .frame(minHeight: Self.minimumTarget)
            .background(inCard ? DS.surface : DS.cardBg, in: RoundedRectangle(cornerRadius: inCard ? 12 : 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: inCard ? 12 : 20, style: .continuous)
                .stroke(inCard ? Color.clear : DS.border, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: Full size and the other modes

    @ViewBuilder private var backButton: some View {
        if let action = backAction() {
            Button(action: action) {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.left")
                        .accessibilityHidden(true)
                    Text(input.copy.backLabel)
                        .font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(DS.blue)
                .frame(minWidth: Self.minimumTarget, minHeight: Self.minimumTarget, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(ID.back)
        }
    }

    private func compactHeader(_ bundle: EarningsEventPageBundle10868) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(bundle.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = EarningsReadingRule10868.readable(bundle.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if case .reader = mode, let action = aboutAction(at: .reader) {
                EarningsInfoControl10868(label: bundle.headline.aboutLabel, hint: bundle.headline.aboutHint, action: action)
                    .accessibilityIdentifier(ID.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.readerHeader)
    }

    private func ownerWords(_ words: String, id: String) -> some View {
        Text(words)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier(id)
    }

    @ViewBuilder private func reader(_ card: Card) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            backButton
            if let bundle = model.bundle {
                compactHeader(bundle)
                if model.readerShows(card) {
                    cardBody(card, at: .reader)
                    steps(from: card)
                } else {
                    ownerWords(bundle.copy.readerUnavailable, id: ID.readerUnavailable)
                }
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.card(card))
    }

    @ViewBuilder private func steps(from card: Card) -> some View {
        let previous = stepAction(.previous, from: card)
        let next = stepAction(.next, from: card)
        if previous != nil || next != nil {
            let row = Group {
                if let previous {
                    stepButton(.previous, from: card, action: previous)
                }
                if let next {
                    stepButton(.next, from: card, action: next)
                }
            }
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) { row }
            } else {
                HStack(spacing: 12) { row }
            }
        }
    }

    private func stepButton(_ step: EarningsReaderStep10868, from card: Card, action: @escaping () -> Void) -> some View {
        let copy = model.bundle?.copy
        let label = (step == .previous ? copy?.previousLabel : copy?.nextLabel) ?? ""
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
        .accessibilityLabel(model.stepSpoken(step, from: card) ?? label)
        .accessibilityIdentifier(ID.step(step))
    }

    @ViewBuilder private var catalogueMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            backButton
            if let bundle = model.bundle {
                compactHeader(bundle)
                if let catalogue = catalogueContent() {
                    catalogue
                }
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.catalogue)
    }

    @ViewBuilder private var originalMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            backButton
            if model.bundle != nil {
                if let details = originalDetailsContent() {
                    details
                }
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.original)
    }

    @ViewBuilder private var aboutMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            backButton
            if let bundle = model.bundle {
                compactHeader(bundle)
                if let content = aboutContent() {
                    content
                }
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.about)
    }

    @ViewBuilder private func sourceMode(_ id: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            backButton
            if let bundle = model.bundle {
                compactHeader(bundle)
                if let content = sourceContent(id) {
                    content
                } else {
                    ownerWords(bundle.copy.sourceUnavailable, id: ID.sourceUnavailable)
                }
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.source)
    }
}

/// The page's white card on the page surface.
private struct EarningsCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
