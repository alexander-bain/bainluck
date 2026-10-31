import SwiftUI

/// #10868 — THE RACING SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE, THE
/// DRIVER CATALOGUE, THE DISPLAYED DRIVERS AND THE NAMED-CHANCE HEADLINE.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `racing-live` the headline names each
/// displayed driver with that driver's own win price and its own clock — or
/// that slot's honest words — and a settled race never reads a 0% or 100% as a
/// chance.
///
/// The app holds a race as FUTURES markets, not as an event: `/api/events` serves
/// no motorsport event (`atlas-v6/raw/motorsport_f1.json` is `{"events":[],
/// "count":0}`), and a race page is `FuturesDetailView` over one market body
/// (`/api/futures/{id}`, `FuturesMarketDetail`) — here the race's driver-winner
/// market. Everything below reads that one body. It decides nothing the app does
/// not already decide; each slot is the output of the authority that owns it:
///
///   - phase           the market's own `status`: `"resolved"` is the final; any
///                     other status is before. Nothing in a futures body says a
///                     race has STARTED — `commence_time` is when the market was
///                     listed (Oct 3 for the Oct 11 Singapore race) and
///                     `resolution_date` is the venue's deadline — so `.during`
///                     is never produced. An open market's words therefore never
///                     say "pre-race": a reading is labelled by what it is, a
///                     recorded price with its own clock.
///   - what one row    `FuturesDetailRowValue.of` (the Market Details row rule:
///     says           `SettledResultDisplay698` then `OutcomeVerdict`): a graded
///                     row is a result and never a chance; a resolved market's
///                     ungraded price is a last price, never a current one.
///   - the figure      `formatProbability` with the page's own whole-percent
///                     decision, `futuresDetailRenderedPercents`, so the headline
///                     and the Market Details row can never round one price two ways.
///   - currentness     `SourceAge.isStale(_, after: SourceAge.futuresStaleAfter)`
///                     on the outcome's own `last_updated` — the backend's
///                     `STALE_PRICE_HOURS`. A stale or undated price is never the
///                     headline's chance: the slot says
///                     `AllMarketsCatalogView9483.noRecentPrice` and the quote stays
///                     in that original's Details (part three).
///   - clock words     `HockeyJourneyPageAdapter10868.clockWords`, the candidate's
///                     one reader-calendar clock formatter.
///   - venue words     `SourceLabels.label(for:)`; an unnamed venue stays unnamed.
///   - the cohort      the host's held driver ids, else the production chart's
///                     default selection — the first three outcomes in served
///                     order (`EvolutionChartView` `selectedNames = prefix(3)`).
///   - key and tint    by display position: the chart palette
///                     (`EvolutionOutcomeColour.markHex`) and one shared shape, so
///                     a headline key always matches its chart line (part two).
///
/// Never here: a race start, lap, gap, leader or progress (the state slot is nil;
/// the reader heading says race progress is unavailable); a physical finish or
/// classification (`finishes` is empty, so the final's finish slot says "Finish
/// unavailable"); a pre-race reading at the final (no start clock reaches the app
/// to elect one); a compact surname (never parsed from a name); a normalized,
/// summed or complemented chance. Each is a named dependency in the return.
enum RacingFieldPageAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        /// The reader's own calendar, time zone and locale; clock words are said in it.
        let calendar: Calendar
        let locale: Locale
        /// The host's held driver cohort, by served outcome id, in its order.
        /// Nil: the production chart's default (the first three served outcomes).
        let cohort: [Int]?

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current,
             cohort: [Int]? = nil) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
            self.cohort = cohort
        }

        /// Part one of the hockey candidate's host, for its clock words only.
        var clock: HockeyJourneyPageAdapter10868.Host {
            HockeyJourneyPageAdapter10868.Host(probabilityObservedAt: nil, now: now,
                                               calendar: calendar, locale: locale)
        }
    }

    /// The fixed words; the Design-approved racing copy where it applies.
    enum Words {
        static let winChance = "Win chance"
        static let preRaceWin = "Pre-race win"
        static let recordedWin = "Recorded win"
        /// The headline's one word for any unavailable reading (the shared headline puts it in place
        /// of a slot's own words): a stale, unpriced or settled row is UNAVAILABLE as a chance — it
        /// may well have been recorded, and the history beside it can show that it was.
        static let winChanceUnavailable = "Win chance unavailable"
        static let noRecent = "No recent probability"
        /// A graded row: a result, never a chance.
        static let settledNoChance = "Settled · no current chance"
        /// At the final: no start clock reaches the app to elect a pre-race reading from. The
        /// readings exist (the history shows them); which one was pre-race is what is unavailable.
        static let noPreRace = "Pre-race chance unavailable"
        static let actualFinish = "Actual finish"
        static let finishUnavailable = "Finish unavailable"
        static let empty = "No drivers in this update"
        static let unavailable = "Driver unavailable in this update"
        static let aboutLabel = "About this race"
        static let aboutHint = "Opens how this race was recorded"
        static let openHint = "Opens this driver's win history"
        static let beforeGraphic = "Recorded win chances"
        static let finalGraphic = "Pre-race chances and actual finishes"
        static let recordedEyebrow = "Recorded probabilities"
        static let settledEyebrow = "Settled market"
        static let resultTitle = "Prop result"
        static let resultUnknown = "Result unknown"
        static let notYetConfirmed = "Not yet confirmed"
        static let historySeparately = "History shown in the chart"
        static let browseStatus = "Race winner"
        /// The reader heading's state line: no race progress reaches the app.
        static let noRaceProgress = "Race progress unavailable"
        static let unattributed = "unattributed"
        static let aboutTitle = "How this race is recorded"
    }

    /// The production chart's default selection size (`EvolutionChartView`).
    static let defaultCohortSize = 3

    // MARK: - Phase

    /// The market's own state. Never read from a price, a clock or a name.
    static func phase(_ market: FuturesMarketDetail) -> FieldOutlookPhase10868 {
        market.status == "resolved" ? .final : .before
    }

    static func phaseWord(_ phase: FieldOutlookPhase10868) -> String {
        switch phase {
        case .before: "before"
        case .during: "during"
        case .final: "final"
        }
    }

    // MARK: - Identity

    /// One owner scope per market and phase.
    static func scope(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> String {
        "racing:\(market.id):\(phaseWord(phase)):field"
    }

    /// The venue half of an identity key: the served source key, or
    /// `unattributed`. A key only — a venue is named to the reader through
    /// `SourceLabels` (#4135), never through this.
    static func venueKey(_ market: FuturesMarketDetail) -> String {
        guard let venue = market.source, !venue.isEmpty else { return Words.unattributed }
        return venue
    }

    /// `(scope, source, market id, outcome id)` from the served ids. Never a
    /// name, a rank or a position.
    static func ref(_ outcome: FuturesOutcome, in market: FuturesMarketDetail,
                    scope: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: venueKey(market),
                                     marketID: String(market.id), outcomeID: String(outcome.id))
    }

    // MARK: - The cohort

    /// The host's held ids, each kept once and only while it names exactly one
    /// served outcome; else the first three outcomes in served order.
    static func cohort(_ market: FuturesMarketDetail, held: [Int]?) -> [FuturesOutcome] {
        guard let held else { return Array(market.outcomes.prefix(defaultCohortSize)) }
        var seen: Set<Int> = []
        var out: [FuturesOutcome] = []
        for id in held where !seen.contains(id) {
            seen.insert(id)
            let matches = market.outcomes.filter { $0.id == id }
            if matches.count == 1 { out.append(matches[0]) }
        }
        return out
    }

    /// The chart's colour for a display position.
    static func tint(_ position: Int) -> Color {
        Color(hex: EvolutionOutcomeColour.markHex(nil, index: position))
    }

    /// The headline key for a display position; part two draws the same shape.
    static func keyShape(_ position: Int) -> FieldHeadlineKeyShape10868 {
        let shapes: [FieldHeadlineKeyShape10868] = [.circle, .diamond, .square]
        return shapes[position % shapes.count]
    }

    // MARK: - What one row says now

    /// One outcome's served state at `host.now`, through the production rules.
    enum Reading: Equatable {
        /// A dated, recent price: its raw value, its figure and its clock line.
        case chance(probability: Double, text: String, detail: String)
        /// A price that is not recent, undated, or the last price of a resolved
        /// market: historical only. `detail` is nil when undated and unnamed.
        case stale(probability: Double, text: String, detail: String?)
        /// A graded row (`OutcomeVerdict`).
        case settled(OutcomeVerdict)
        /// Settled, result unknown (`SettledResultDisplay698`).
        case resultUnknown(lastRecorded: Double?)
        /// No price and no grade.
        case unpriced
    }

    static func reading(_ outcome: FuturesOutcome, in market: FuturesMarketDetail, host: Host) -> Reading {
        switch FuturesDetailRowValue.of(outcome, marketStatus: market.status, marketSource: market.source) {
        case .verdict(let verdict):
            return .settled(verdict)
        case .resultUnknown(let last):
            return .resultUnknown(lastRecorded: last)
        case .none:
            return .unpriced
        case .price(let probability):
            guard probability.isFinite, probability >= 0, probability <= 1 else { return .unpriced }
            let percents = futuresDetailRenderedPercents(market.outcomes)
            let text = formatProbability(probability, renderedPercent: percents[outcome.id])
            let date = outcome.lastUpdated?.asDate
            let line = joined([date.map { clockWords($0, host: host) }, SourceLabels.label(for: market.source)])
            let stale = SourceAge.isStale(outcome.lastUpdated, now: host.now, after: SourceAge.futuresStaleAfter)
            guard market.status != "resolved", date != nil, !stale, let detail = line else {
                return .stale(probability: probability, text: text, detail: line)
            }
            return .chance(probability: probability, text: text, detail: detail)
        }
    }

    // MARK: - The catalogue

    /// The headline's one plan reading for an original in this phase.
    static func beforeReading(_ outcome: FuturesOutcome, in market: FuturesMarketDetail,
                              phase: FieldOutlookPhase10868, host: Host) -> FieldChooserReading10868 {
        guard phase == .before else {
            return FieldChooserReading10868(label: Words.preRaceWin, value: .missing(Words.noPreRace))
        }
        let value: FieldChooserValue10868
        switch reading(outcome, in: market, host: host) {
        case .chance(_, let text, let detail):
            value = .recorded(text: text, detail: detail)
        case .stale:
            value = .missing(AllMarketsCatalogView9483.noRecentPrice)
        case .settled, .resultUnknown:
            value = .missing(Words.settledNoChance)
        case .unpriced:
            value = .missing(AllMarketsCatalogView9483.unavailablePrice)
        }
        return FieldChooserReading10868(label: Words.winChance, value: value)
    }

    /// The contract's own result words, at the final only. Unknown is not loss.
    static func result(_ outcome: FuturesOutcome, in market: FuturesMarketDetail,
                       phase: FieldOutlookPhase10868, host: Host) -> FieldChooserResult10868? {
        guard phase == .final else { return nil }
        let words: String
        switch reading(outcome, in: market, host: host) {
        case .settled(let verdict): words = verdict.label
        case .resultUnknown: words = Words.resultUnknown
        case .chance, .stale, .unpriced: words = Words.notYetConfirmed
        }
        return FieldChooserResult10868(title: Words.resultTitle, words: words)
    }

    /// Every served outcome once, in served order. A displayed driver carries
    /// its chart colour; the rest keep the default.
    static func catalogue(_ market: FuturesMarketDetail, cohort: [FuturesOutcome],
                          phase: FieldOutlookPhase10868, host: Host) -> [FieldChooserOriginal10868] {
        let scope = Self.scope(market, phase: phase)
        let positions = cohort.map(\.id)
        return market.outcomes.map { outcome in
            let accent: Color? = positions.firstIndex(of: outcome.id).map(tint)
            return FieldChooserOriginal10868(
                ref: ref(outcome, in: market, scope: scope),
                name: outcome.name,
                plan: .single(beforeReading(outcome, in: market, phase: phase, host: host)),
                preview: FieldChooserPreview10868(history: nil, absence: Words.historySeparately),
                movement: nil,
                clock: nil,
                result: result(outcome, in: market, phase: phase, host: host),
                browseStatus: Words.browseStatus,
                accent: accent)
        }
    }

    // MARK: - The headline

    static func headline(_ market: FuturesMarketDetail, host: Host, compact: Bool = false) -> FieldHeadlineInput10868 {
        let phase = Self.phase(market)
        let scope = Self.scope(market, phase: phase)
        let shown = cohort(market, held: host.cohort)
        let slots = shown.enumerated().map { position, outcome in
            FieldHeadlineSlot10868(ref: ref(outcome, in: market, scope: scope), name: outcome.name,
                                   compactName: nil, keyShape: keyShape(position))
        }
        return FieldHeadlineInput10868(
            scope: scope,
            catalogue: catalogue(market, cohort: shown, phase: phase, host: host),
            displayed: slots,
            pairs: shown.map { pair($0, in: market, phase: phase, host: host) },
            finishes: [],
            state: nil,
            phase: phase,
            copy: headlineCopy(market, phase: phase, compact: compact),
            unavailableWords: Words.unavailable,
            // No race start reaches the app, so no reading is a qualified pre-race baseline:
            // the keys stay neutral and recorded, like the chart's marks (Design 2026-10-31).
            keyTreatment: .neutralRecorded)
    }

    /// The owner's one association per displayed driver: the raw price behind
    /// the plan's own reading, only while that reading is a figure. No later
    /// observation: nothing proves a price was recorded during the race.
    static func pair(_ outcome: FuturesOutcome, in market: FuturesMarketDetail,
                     phase: FieldOutlookPhase10868, host: Host) -> FieldMovementPair10868 {
        let shown = beforeReading(outcome, in: market, phase: phase, host: host)
        var before: FieldMovementObservation10868?
        if phase == .before, case .chance(let probability, _, _) = reading(outcome, in: market, host: host) {
            before = FieldMovementObservation10868(probability: probability, reading: shown)
        }
        return FieldMovementPair10868(ref: ref(outcome, in: market, scope: scope(market, phase: phase)),
                                      before: before, later: nil, movement: nil, observation: nil)
    }

    static func headlineCopy(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868,
                             compact: Bool = false) -> FieldHeadlineCopy10868 {
        let family = market.llmSportCategory.flatMap { sportFamilyDisplayNames[$0.lowercased()] }
        let stage = phase == .final ? Words.settledEyebrow : Words.recordedEyebrow
        return FieldHeadlineCopy10868(
            eyebrow: compact ? nil : family.map { "\($0) · \(stage)" },
            title: compact ? nil : market.name,
            graphicLabel: phase == .final ? Words.finalGraphic : Words.beforeGraphic,
            beforeLabel: phase == .final ? Words.preRaceWin : Words.winChance,
            recordedLabel: Words.recordedWin,
            beforeUnavailable: phase == .final ? Words.noPreRace : Words.winChanceUnavailable,
            recordedUnavailable: Words.noRecent,
            finishLabel: Words.actualFinish,
            finishUnavailable: Words.finishUnavailable,
            empty: Words.empty,
            aboutLabel: Words.aboutLabel,
            aboutHint: Words.aboutHint,
            openHint: Words.openHint)
    }

    // MARK: - Reader heading and About

    /// The market's own name, and the honest state line: no race progress is
    /// reported anywhere the app reads.
    static func readerHeader(_ market: FuturesMarketDetail) -> RacingEventPageReaderHeader10868 {
        RacingEventPageReaderHeader10868(title: market.name, state: Words.noRaceProgress)
    }

    /// How this page reads the race, in the owner's words. The stale bound is
    /// said from `SourceAge.futuresStaleAfter` itself.
    static func raceAbout(_ market: FuturesMarketDetail) -> RacingEventPageAbout10868 {
        let venue = SourceLabels.label(for: market.source)
        let own = venue.map { "own \($0) probability" } ?? "own probability"
        let hours = Int(SourceAge.futuresStaleAfter / 3600)
        var paragraphs = [
            "Each driver's chance is that driver's \(own) in “\(market.name)”, shown with the time it was last recorded. The chances are independent: they are not adjusted to add up to 100%.",
            "The race start time, lap reports and finishing order are unavailable here, so readings are not split into pre-race and race, and no lap, gap or finishing position is shown.",
            "A reading not updated in the last \(hours) hours is not shown as a current chance; its last recorded value stays in that original's Details.",
        ]
        if phase(market) == .final {
            let settler = venue.map { "\($0)'s settlement" } ?? "the venue's settlement"
            paragraphs.append("Results come only from \(settler) of each original. A settled 0% or 100% is a result, not a chance, and is never shown on the chart.")
        }
        return RacingEventPageAbout10868(title: Words.aboutTitle, paragraphs: paragraphs)
    }

    // MARK: - Words

    static func clockWords(_ date: Date, host: Host) -> String {
        HockeyJourneyPageAdapter10868.clockWords(date, host: host.clock)
    }

    static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
