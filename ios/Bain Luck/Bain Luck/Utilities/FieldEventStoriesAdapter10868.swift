import SwiftUI

/// #10868 — THE FIELD SCREEN'S PRODUCTION ADAPTER, PART THREE: THE TWO FIELD
/// STORIES — THE FIELD'S RECORDED WIN CHANCES, AND HOW EACH DISPLAYED
/// CONTENDER'S CHANCE MOVED.
///
/// PILLARS: DISCOVER / TRUTH. SHIP: below the chart a fan sees every contender
/// that has a recent win chance on one 0–100% scale (and can put any of them in
/// the chart), and how each charted contender's recorded chance moved from the
/// earliest to the latest reading in its history — never a stale reading called
/// current, never a settled 0% or 100% as a chance.
///
/// THE FIELD CARD (`FieldOutlookInput10868`, "Tournament winner field" /
/// "Tournament contenders" in the route tracker) is built from part one alone:
///   - the bars        every served outcome whose part-one row reading is a
///                     recent, dated chance, in SERVED order (the market's order,
///                     not a ranking) — never sorted, capped or topped up with an
///                     unpriced contender; the count of the rest is in the note,
///                     and every original stays in All props.
///   - each value      the raw probability behind that row's own plan reading —
///                     the very reading the headline and catalogue show — so the
///                     card cannot print one contender two ways.
///   - selection       this market's held choice by its exact identity, resolved
///                     by the chooser's own resolver; previous / next walk the bars.
///                     While an update omits it, the identity is still handed
///                     over, so the chooser's unresolved-selection words say the
///                     chosen contender is unavailable — nothing else is selected
///                     in its place, and no figure of it is kept. Served again, it
///                     resolves again. Another market's choice is never handed over.
///   - scale           0–100%, golf's contender ticks
///                     (`GolfFieldChooserAdapter10868.scaleTicks`).
///   - phase           before only. A resolved market has no current chance, so
///                     there is no field card at the final (its results are in
///                     All props and the chart's key).
///
/// THE MOVEMENT CARD (`PreEventShiftInput10868`, "dated probability movement")
/// reads the same `/history` body as part two, under the same identity rule:
///   - rows            part one's served cohort — the contenders drawn in the
///                     chart — in its order, each with its display position's
///                     glyph and the chart's tint (catalogue accent). A held
///                     choice an update omits has no history row to draw here; it
///                     keeps its position, so the others keep their glyphs.
///   - endpoints       each contender's FIRST and LAST drawn observation from part
///                     two's own runs (`FieldEventHistoryAdapter10868.runs`:
///                     settlement removed, breaks kept), each with its own clock.
///                     The first is the earliest reading IN THIS HISTORY — the
///                     response is windowed by the host's `hours` — never an
///                     opening quote; the last is a recorded reading, never a
///                     current chance. A contender with one reading shows it as
///                     its latest and says the earliest is unavailable; with none,
///                     both endpoints keep the card's unavailable words.
///   - keys            each endpoint's observation key is part two's point id, so
///                     an open lands on that exact point in the chart.
///   - scale           0–100% (the approved card's common scale).
///   - phase           before and at the final (the card's own gate); the copy
///                     never says the readings were before the event — no start
///                     reaches the app.
///
/// Glyphs follow the headline keys and chart marks by display position —
/// circle, diamond, square — through the shared card's additive `square`
/// (Design 2026-10-31), so a contender carries one mark in all three places.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum FieldEventStoriesAdapter10868 {
    typealias Page = FieldEventPageAdapter10868
    typealias History = FieldEventHistoryAdapter10868

    enum Words {
        static let fieldTitle = "The field"
        static let fieldGraphic = "Recent win chances across the field"
        static let missingChance = "Chance not shown on this scale"
        static let offScale = "Above this scale"
        static let details = "Original outcome & details"
        static let inChart = "In your chart"
        static let resultUnavailable = Page.Words.resultUnavailable

        static let movementTitle = "How chances moved"
        static let movementPhaseKey = "Each mark is a recorded reading with its own time"
        static let firstKey = "Small: earliest in this history"
        static let latestKey = "Large: latest recorded"
        static let movementGraphic = "Earliest and latest recorded win chances"
        static let firstLabel = "Earliest in this history"
        static let latestLabel = "Latest recorded"
        static let endpointUnavailable = "Reading unavailable"
        /// One reading only: it is the latest, and there is no earlier one in this history.
        static let onlyOneReading = "Only one reading in this history"
        static let movementNote = "The path between the two readings is in the chart."
        static let movementScale = "0–100% win chance"

        static func fieldNote(_ shown: Int, of total: Int, _ contender: Page.Contender) -> String {
            let noun = total == 1 ? contender.singular : contender.plural
            return "\(shown) of \(total) \(noun) with a recent win chance · in the market’s order, not a ranking"
        }
        static func fieldScale(_ contender: Page.Contender) -> String {
            "0–100% win chance · each \(contender.singular)’s own chance, never added up"
        }
        static func outsideDisplayed(_ contender: Page.Contender) -> String {
            "The chosen \(contender.singular) has no recent win chance in this card."
        }
        static func previous(_ contender: Page.Contender) -> String { "Previous \(contender.singular)" }
        static func next(_ contender: Page.Contender) -> String { "Next \(contender.singular)" }
        static func detailsHint(_ contender: Page.Contender) -> String { "Opens this \(contender.singular)’s original outcome" }
        static func chooseHint(_ contender: Page.Contender) -> String { "Shows this \(contender.singular) in the chart" }
        static func chosenUnavailable(_ contender: Page.Contender) -> String {
            Page.Words.chosenUnavailable(contender)
        }
        static func openHint(_ contender: Page.Contender) -> String { "Opens this \(contender.singular)’s win history" }
    }

    /// The movement card's 0–100% ticks.
    static let movementTicks: [Double] = [0, 0.5, 1]
    /// The movement glyphs by display position: the headline key shapes.
    static let glyphs: [PreEventShiftGlyph10868] = [.circle, .diamond, .square]

    // MARK: - The field card

    /// Before only, and only with at least one recent chance to draw.
    static func field(_ market: FuturesMarketDetail, host: Page.Host) -> FieldOutlookInput10868? {
        let phase = Page.phase(market)
        guard phase == .before else { return nil }
        let scope = Page.scope(market, phase: phase)
        let contender = Page.contender(market)
        let cohort = Page.cohort(market, host: host)
        var displayed: [FieldOutlookSlot10868] = []
        var chances: [FieldOutlookBeforeChance10868] = []
        for outcome in market.outcomes {
            guard case .chance(let probability, _, _) = Page.reading(outcome, in: market, host: host) else { continue }
            let ref = Page.ref(outcome, in: market, scope: scope)
            displayed.append(FieldOutlookSlot10868(ref: ref, label: outcome.name, shortLabel: outcome.name))
            let reading = Page.beforeReading(outcome, in: market, phase: phase, host: host)
            chances.append(FieldOutlookBeforeChance10868(ref: ref, probability: probability, reading: reading))
        }
        guard !displayed.isEmpty else { return nil }
        let ticks: [FieldOutlookTick10868] = GolfFieldChooserAdapter10868.scaleTicks.map {
            FieldOutlookTick10868(probability: $0, label: OddsChartView.axisLabel(for: $0))
        }
        let copy = FieldOutlookCopy10868(
            title: Words.fieldTitle,
            note: Words.fieldNote(displayed.count, of: market.outcomes.count, contender),
            graphicLabel: Words.fieldGraphic,
            missingChance: Words.missingChance,
            offScale: Words.offScale,
            outsideDisplayed: Words.outsideDisplayed(contender),
            previousLabel: Words.previous(contender),
            nextLabel: Words.next(contender),
            details: Words.details,
            detailsHint: Words.detailsHint(contender),
            resultUnknown: Words.resultUnavailable)
        return FieldOutlookInput10868(
            scope: scope,
            catalogue: Page.catalogue(market, cohort: cohort, phase: phase, host: host),
            selected: selected(market, scope: scope, host: host),
            displayed: displayed,
            traversal: displayed.map(\.ref),
            chances: chances,
            scale: FieldOutlookScale10868(ceiling: 1, ticks: ticks, words: Words.fieldScale(contender)),
            phase: phase,
            copy: copy,
            unavailableWords: Page.Words.unavailable(contender),
            chooseHint: Words.chooseHint(contender))
    }

    /// This market's held choice by its exact identity — served or not. The
    /// chooser's resolver decides whether it resolves; unresolved, its words say so.
    static func selected(_ market: FuturesMarketDetail, scope: String, host: Page.Host) -> FieldChooserSelected10868? {
        guard let choice = Page.heldChoice(market, host: host) else { return nil }
        return FieldChooserSelected10868(ref: Page.ref(choice, scope: scope), words: Words.inChart,
                                         unavailableWords: Words.chosenUnavailable(Page.contender(market)))
    }

    // MARK: - The movement card

    /// Before and at the final, from this market's own history only, and only
    /// with at least one drawn reading among the charted contenders.
    static func movement(_ response: FuturesHistoryResponse?, market: FuturesMarketDetail,
                         host: Page.Host) -> PreEventShiftInput10868? {
        guard let response, response.marketId == market.id else { return nil }
        let phase = Page.phase(market)
        let scope = Page.scope(market, phase: phase)
        let contender = Page.contender(market)
        let cohort = Page.cohort(market, host: host)
        var slots: [PreEventShiftSlot10868] = []
        var readings: [PreEventShiftReading10868] = []
        var observations: [PreEventShiftObservation10868] = []
        for (index, outcome) in cohort.served.enumerated() {
            let ref = Page.ref(outcome, in: market, scope: scope)
            let glyph = glyphs[cohort.position(index) % glyphs.count]
            slots.append(PreEventShiftSlot10868(ref: ref, name: outcome.name, glyph: glyph))
            let drawn = History.runs(outcome, response: response, now: host.now).flatMap { $0 }
            guard let latest = drawn.last else { continue }
            let seriesID = History.seriesID(market, outcome)
            let last = endpoint(latest, kind: .latest, ref: ref, seriesID: seriesID, market: market, host: host)
            readings.append(last.reading)
            observations.append(last.observation)
            if let earliest = drawn.first, earliest.timestamp != latest.timestamp {
                let first = endpoint(earliest, kind: .first, ref: ref, seriesID: seriesID, market: market, host: host)
                readings.append(first.reading)
                observations.append(first.observation)
            } else {
                let missing = FieldChooserReading10868(label: Words.firstLabel, value: .missing(Words.onlyOneReading))
                readings.append(PreEventShiftReading10868(ref: ref, endpoint: .first, reading: missing))
            }
        }
        guard !observations.isEmpty else { return nil }
        let ticks: [FieldOutlookTick10868] = movementTicks.map {
            FieldOutlookTick10868(probability: $0, label: OddsChartView.axisLabel(for: $0))
        }
        let copy = PreEventShiftCopy10868(
            eyebrow: nil,
            title: Words.movementTitle,
            phaseKey: Words.movementPhaseKey,
            firstKey: Words.firstKey,
            latestKey: Words.latestKey,
            graphicLabel: Words.movementGraphic,
            firstLabel: Words.firstLabel,
            latestLabel: Words.latestLabel,
            endpointUnavailable: Words.endpointUnavailable,
            offScale: Words.offScale,
            note: Words.movementNote,
            openHint: Words.openHint(contender))
        return PreEventShiftInput10868(
            scope: scope,
            catalogue: Page.catalogue(market, cohort: cohort, phase: phase, host: host),
            displayed: slots,
            readings: readings,
            observations: observations,
            scale: FieldOutlookScale10868(ceiling: 1, ticks: ticks, words: Words.movementScale),
            phase: phase,
            copy: copy,
            unavailableWords: Page.Words.unavailable(contender))
    }

    /// One endpoint: the reading and the raw observation it was formatted from,
    /// tied by the same reading value, keyed by part two's point id.
    static func endpoint(_ observation: GolfFieldHistoryAdapter10868.Observation, kind: PreEventShiftEndpointKind10868,
                         ref: FieldChooserOriginalRef10868, seriesID: String, market: FuturesMarketDetail,
                         host: Page.Host) -> (reading: PreEventShiftReading10868, observation: PreEventShiftObservation10868) {
        let label = kind == .first ? Words.firstLabel : Words.latestLabel
        let detail = History.provenance(observation, market: market, host: host)
        let reading = FieldChooserReading10868(label: label,
                                               value: .recorded(text: formatProbability(observation.probability),
                                                                detail: detail))
        let raw = FieldMovementObservation10868(probability: observation.probability, reading: reading)
        return (PreEventShiftReading10868(ref: ref, endpoint: kind, reading: reading),
                PreEventShiftObservation10868(ref: ref, endpoint: kind, observation: raw,
                                              key: History.pointID(seriesID, observation)))
    }
}
