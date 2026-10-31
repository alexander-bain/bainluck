import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART FOUR: THE
/// GOLFER CHOOSER AND THE BEFORE-THE-START CONTENDERS CARD.
///
/// PILLARS: DISCOVER / TRUTH. SHIP: a fan can open the golfer chooser on any
/// golf tournament screen, see every golfer in the field — the ones in the chart,
/// more with recorded history, and the whole field — and choose any of them,
/// including a golfer with no price or history; before the start date, "Who
/// starts strongest?" compares the chart's golfers on one 0–100% scale.
///
/// It builds `FieldChooserInput10868` and `FieldOutlookInput10868` from the same
/// Winner `GolfFieldHistoryAdapter10868.Field` the chart reads:
///
///   - the catalogue  one record per served Winner outcome, in served order, each
///                    an exact identity (scope · source key · market id · outcome
///                    id) — never a name or an index. A duplicated served id
///                    resolves to nothing, in the chooser's own resolver.
///   - readings       `Field.before` / `Field.later` — the same readings the
///                    chart's key and the finish card's Win slot show — through
///                    `formatProbability` with their own clocks and
///                    `SourceLabels` names. A golfer with no price keeps the
///                    "not recorded" words and stays choosable.
///   - previews       each golfer's runs from `GolfFieldHistoryAdapter10868.runs`
///                    (the chart's own break rule and frame) on ONE chooser frame
///                    spanning every golfer's drawn observations, full 0–100%.
///                    The hollow reference is the before reading, after the start
///                    only; the emphasis is the reading the card leads with, only
///                    when it is a drawn observation.
///   - sections       "In your chart" is the host's cohort; "More with recorded
///                    history" is every other golfer with a drawn preview, in
///                    served order; "Browse" is the whole field in served order
///                    as one list. The approved last-name groups need a surname
///                    parser the reference itself rejected, so no groups are
///                    invented.
///   - results        final only, `FuturesDetailRowValue.of` Won / Lost words
///                    (`OutcomeVerdict.label`); no grade, no result line.
///   - contenders     before only: the host's chart golfers as bars of their own
///                    before chance, each tied to the very before reading its
///                    chooser card shows, on the full 0–100% scale; previous /
///                    next walk the served order.
///
/// OWED, NOT MANUFACTURED:
///   - movement ("What changed?"): no owner supplies a pre-tournament pair per
///     golfer with two tied observations, a signed scale and change words. The
///     served `movement_24h` / `probability_change_24h` is an untied server delta
///     (null on the retained DataGolf rows) and `opening_probability` is untimed,
///     so the card is absent and the page draws no movement story. Owner: golf /
///     futures endpoint.
///   - the chooser's intro and featured election ("pick one, we suggest two"): no
///     owner; the host passes its cohort.
///   - original Details: no destination; the host passes no open-original callback.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum GolfFieldChooserAdapter10868 {
    typealias Host = GolfFieldPageAdapter10868.Host
    typealias Field = GolfFieldHistoryAdapter10868.Field
    typealias History = GolfFieldHistoryAdapter10868

    /// The host's chooser disclosures.
    struct Disclosures: Equatable {
        var moreExpanded: Bool
        var browseExpanded: Bool
        var browseGroup: String?

        init(moreExpanded: Bool = false, browseExpanded: Bool = false, browseGroup: String? = nil) {
            self.moreExpanded = moreExpanded
            self.browseExpanded = browseExpanded
            self.browseGroup = browseGroup
        }
    }

    enum Words {
        static let featuredTitle = "In your chart"
        static let featuredEmpty = "No golfers in the chart yet."
        static let moreEmpty = "No other golfers have recorded history in this view."
        static let browseNote = "In the market’s order · every golfer can be chosen, with or without history."
        static let groupsLabel = "Golfer list"
        static let allGolfers = "All golfers"
        static let noGroup = "Choose the list to see every golfer."
        static let groupUnavailable = "This list is unavailable in this update."
        static let emptyGroup = "No golfers in this list."
        static let previewKey = "Same time window and scale for every golfer"
        static let referenceKey = "Dashed line: last chance before the start date"
        static let scale = "0–100% chance"
        static let recordedHistory = "Recorded history"
        static let historyAvailable = "Recorded history available"
        static let noHistoryHere = "No recorded history in this view"
        static let inFocus = "In focus"
        static let selectedUnavailable = "Selected golfer unavailable in this update"
        static let unavailable = "Golfer unavailable in this update"
        static let chooseHint = "Shows this golfer’s chances"
        static let finalResult = "Final result"

        static let contendersTitle = "Who starts strongest?"
        static let contendersNote = "Golfers in your chart · before the start date"
        static let contendersGraphic = "Chances before the start date"
        static let missingChance = "Chance not shown on this scale"
        static let offScale = "Above this scale"
        static let outsideDisplayed = "The selected golfer isn’t in your chart."
        static let previousGolfer = "Previous golfer"
        static let nextGolfer = "Next golfer"
        static let details = "Original outcomes & rules"
        static let contendersScale = "0–100% chance · each golfer’s own chance, never added up"

        static func more(_ count: Int) -> String { "More with recorded history · \(count)" }
        static func browse(_ count: Int) -> String { count == 1 ? "Browse the 1 golfer" : "Browse all \(count) golfers" }
        static func context(_ withHistory: Int, of count: Int) -> String {
            "\(withHistory) of \(count) golfers have recorded history in this view"
        }
        /// "DataGolf recorded history" from the `SourceLabels` name, else plain words.
        static func historyName(_ named: String?) -> String {
            named.map { "\($0) recorded history" } ?? recordedHistory
        }
    }

    static let moreID = "golf.chooser.more"
    static let browseID = "golf.chooser.browse"
    static let allGroupID = "golf.chooser.all"
    static let scaleTicks: [Double] = [0, 0.25, 0.5, 0.75, 1]

    // MARK: - Identity

    /// One scope per market and phase, shared by the chooser and both before cards.
    static func scope(_ field: Field) -> String {
        "golf:\(field.market.id):\(field.phase)"
    }

    static func ref(_ outcomeID: Int, field: Field) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope(field), source: GolfFieldPageAdapter10868.sourceKey(field.market),
                                     marketID: "\(field.market.id)", outcomeID: "\(outcomeID)")
    }

    /// The Winner outcome id a chooser ref names, only for this market.
    static func outcomeID(_ ref: FieldChooserOriginalRef10868, market: FuturesMarketDetail) -> Int? {
        guard ref.marketID == "\(market.id)" else { return nil }
        return Int(ref.outcomeID)
    }

    /// The host's ids in its order, each once.
    static func unique(_ ids: [Int]) -> [Int] {
        var seen: Set<Int> = []
        return ids.filter { seen.insert($0).inserted }
    }

    // MARK: - Readings

    static func beforeReading(_ field: Field, outcomeID: Int, host: Host) -> FieldChooserReading10868 {
        let missing = field.listedStart == nil ? History.Words.noStartWords : History.Words.notBeforeStart
        return FieldChooserReading10868(label: History.Words.beforeLabel,
                                        value: value(field.before(outcomeID), field: field, missing: missing, host: host))
    }

    static func laterReading(_ field: Field, outcomeID: Int, host: Host) -> FieldChooserReading10868 {
        let missing = field.listedStart == nil ? History.Words.notRecorded : History.Words.notSinceStart
        return FieldChooserReading10868(label: History.Words.latestLabel,
                                        value: value(field.later(outcomeID), field: field, missing: missing, host: host))
    }

    static func value(_ reading: History.Reading?, field: Field, missing: String, host: Host) -> FieldChooserValue10868 {
        guard let reading else { return .missing(missing) }
        return .recorded(text: History.figure(reading), detail: History.provenance(reading, market: field.market, host: host))
    }

    /// Before and final: the before reading alone. Recorded: the before reading
    /// beside the latest recorded one. A final card never reads its last price.
    static func plan(_ field: Field, outcomeID: Int, host: Host) -> FieldChooserDisplayPlan10868 {
        let before = beforeReading(field, outcomeID: outcomeID, host: host)
        guard field.phase == .recorded else { return .single(before) }
        return .comparison(before: before, later: laterReading(field, outcomeID: outcomeID, host: host))
    }

    // MARK: - Previews

    /// Every served golfer's drawn runs, once per id (a duplicated id keeps its first).
    static func runsByID(_ field: Field) -> [Int: [[History.Observation]]] {
        let cutoff = History.frameCutoff(field)
        var runs: [Int: [[History.Observation]]] = [:]
        for outcome in field.market.outcomes where runs[outcome.id] == nil {
            runs[outcome.id] = History.runs(field.entries(outcome.id) ?? [], from: cutoff)
        }
        return runs
    }

    /// One frame for every preview: every golfer's drawn observations.
    static func frame(_ field: Field, runsByID: [Int: [[History.Observation]]]) -> FieldChooserFrame10868? {
        let dates = runsByID.values.flatMap { $0.flatMap { $0.map(\.date) } }
        guard let first = dates.min(), let last = dates.max() else { return nil }
        let domain = History.frame(first, last)
        return FieldChooserFrame10868(
            start: domain.lowerBound.timeIntervalSince1970, end: domain.upperBound.timeIntervalSince1970,
            ceiling: 1, key: Words.previewKey,
            referenceKey: field.phase == .before ? nil : Words.referenceKey,
            scale: Words.scale,
            provenance: Words.historyName(GolfFieldPageAdapter10868.sourceName(field.market)))
    }

    static func preview(_ field: Field, outcomeID: Int, runs: [[History.Observation]]) -> FieldChooserPreview10868 {
        let absence = field.history == nil ? History.Words.historyUnavailable : History.Words.noHistory
        guard !runs.isEmpty else { return FieldChooserPreview10868(history: nil, absence: absence) }
        let segments: [[FieldChooserPoint10868]] = runs.map { run in
            run.map { FieldChooserPoint10868(time: $0.date.timeIntervalSince1970, probability: $0.probability) }
        }
        var gaps: [FieldChooserGap10868] = []
        for (earlier, later) in zip(runs, runs.dropFirst()) {
            guard let end = earlier.last, let start = later.first else { continue }
            gaps.append(FieldChooserGap10868(start: end.date.timeIntervalSince1970, end: start.date.timeIntervalSince1970))
        }
        let reference: Double? = field.phase == .before ? nil : field.before(outcomeID)?.probability
        let history = FieldChooserHistory10868(segments: segments, emphasis: emphasis(field, outcomeID: outcomeID, runs: runs),
                                               beforeReference: reference, gaps: gaps)
        return FieldChooserPreview10868(history: history, absence: absence)
    }

    /// The reading the card leads with, only when it is one of the drawn observations.
    static func emphasis(_ field: Field, outcomeID: Int, runs: [[History.Observation]]) -> FieldChooserPoint10868? {
        let reading = field.phase == .recorded ? field.later(outcomeID) : field.before(outcomeID)
        guard let reading, case .recorded(let stamp) = reading.kind,
              let observation = runs.joined().first(where: { $0.timestamp == stamp }) else { return nil }
        return FieldChooserPoint10868(time: observation.date.timeIntervalSince1970, probability: observation.probability)
    }

    // MARK: - The catalogue and chooser

    static func catalogue(_ field: Field, cohort: [Int], runsByID: [Int: [[History.Observation]]],
                          host: Host) -> [FieldChooserOriginal10868] {
        var positions: [Int: Int] = [:]
        for (position, golfer) in History.drawnGolfers(field, cohort: cohort).enumerated() {
            positions[golfer.id] = position
        }
        return field.market.outcomes.map { outcome -> FieldChooserOriginal10868 in
            let runs = runsByID[outcome.id] ?? []
            let status: String
            if field.history == nil {
                status = History.Words.historyUnavailable
            } else {
                status = runs.isEmpty ? Words.noHistoryHere : Words.historyAvailable
            }
            return FieldChooserOriginal10868(
                ref: ref(outcome.id, field: field),
                name: outcome.name,
                plan: plan(field, outcomeID: outcome.id, host: host),
                preview: preview(field, outcomeID: outcome.id, runs: runs),
                movement: nil,
                clock: nil,
                result: field.verdict(outcome.id).map { FieldChooserResult10868(title: Words.finalResult, words: $0.label) },
                browseStatus: status,
                accent: positions[outcome.id].map { History.tint($0) })
        }
    }

    static func chooser(_ field: Field, cohort: [Int], selected: Int?, state: Disclosures,
                        host: Host) -> FieldChooserInput10868 {
        let runs = runsByID(field)
        let all = field.market.outcomes.map { ref($0.id, field: field) }
        let loaded = field.history != nil
        let inChart = Set(cohort)
        let withHistory = field.market.outcomes.filter { !(runs[$0.id] ?? []).isEmpty }
        let moreRefs = withHistory.filter { !inChart.contains($0.id) }.map { ref($0.id, field: field) }
        let more: FieldChooserMore10868? = loaded
            ? FieldChooserMore10868(id: moreID, title: Words.more(moreRefs.count), expanded: state.moreExpanded,
                                    refs: moreRefs, emptyWords: Words.moreEmpty)
            : nil
        let browse = FieldChooserBrowse10868(
            id: browseID, title: Words.browse(all.count), expanded: state.browseExpanded,
            note: Words.browseNote, groupsLabel: Words.groupsLabel,
            groups: [FieldChooserGroup10868(id: allGroupID, label: Words.allGolfers, countText: "\(all.count)", refs: all)],
            selectedGroupID: state.browseGroup,
            noGroupWords: Words.noGroup, groupUnavailableWords: Words.groupUnavailable, emptyGroupWords: Words.emptyGroup)
        let chosen: FieldChooserSelected10868? = selected.map {
            FieldChooserSelected10868(ref: ref($0, field: field), words: Words.inFocus, unavailableWords: Words.selectedUnavailable)
        }
        return FieldChooserInput10868(
            scope: scope(field),
            intro: nil,
            featured: FieldChooserFeatured10868(title: Words.featuredTitle, badge: nil,
                                                refs: unique(cohort).map { ref($0, field: field) },
                                                emptyWords: Words.featuredEmpty),
            context: loaded ? Words.context(withHistory.count, of: all.count) : nil,
            more: more,
            browse: browse,
            catalogue: catalogue(field, cohort: cohort, runsByID: runs, host: host),
            frame: frame(field, runsByID: runs),
            selected: chosen,
            unavailableWords: Words.unavailable,
            chooseHint: Words.chooseHint)
    }

    // MARK: - Who starts strongest? (before the start date only)

    /// The host's chart golfers as bars of their own before chance, before the
    /// start date only; nil in any other phase or with no golfers in the chart.
    static func contenders(_ field: Field, chooser: FieldChooserInput10868, cohort: [Int],
                           host: Host) -> FieldOutlookInput10868? {
        guard field.phase == .before else { return nil }
        let ids = unique(cohort)
        guard !ids.isEmpty else { return nil }
        let displayed = ids.map { id -> FieldOutlookSlot10868 in
            let name = field.outcome(id)?.name ?? ""
            return FieldOutlookSlot10868(ref: ref(id, field: field), label: name, shortLabel: name)
        }
        let chances: [FieldOutlookBeforeChance10868] = ids.compactMap { id -> FieldOutlookBeforeChance10868? in
            guard let reading = field.before(id) else { return nil }
            return FieldOutlookBeforeChance10868(ref: ref(id, field: field), probability: reading.probability,
                                                 reading: beforeReading(field, outcomeID: id, host: host))
        }
        return FieldOutlookInput10868(
            scope: chooser.scope,
            catalogue: chooser.catalogue,
            selected: chooser.selected,
            displayed: displayed,
            traversal: chooser.catalogue.map(\.ref),
            chances: chances,
            scale: FieldOutlookScale10868(
                ceiling: 1,
                ticks: scaleTicks.map { FieldOutlookTick10868(probability: $0, label: OddsChartView.axisLabel(for: $0)) },
                words: Words.contendersScale),
            phase: .before,
            copy: FieldOutlookCopy10868(
                title: Words.contendersTitle, note: Words.contendersNote, graphicLabel: Words.contendersGraphic,
                missingChance: Words.missingChance, offScale: Words.offScale, outsideDisplayed: Words.outsideDisplayed,
                previousLabel: Words.previousGolfer, nextLabel: Words.nextGolfer, details: Words.details,
                detailsHint: nil, resultUnknown: GolfFieldFinishAdapter10868.Words.resultUnavailable),
            unavailableWords: Words.unavailable,
            chooseHint: Words.chooseHint)
    }
}
