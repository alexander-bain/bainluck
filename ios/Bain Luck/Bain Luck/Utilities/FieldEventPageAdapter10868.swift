import SwiftUI

/// #10868 — THE FIELD SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE, THE
/// CONTENDER WORDS, THE CATALOGUE, THE DISPLAYED CONTENDERS AND THE
/// NAMED-CHANCE HEADLINE.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on a championship field page (cricket,
/// rugby, darts, chess) the headline names each displayed team or player with
/// that contender's own win chance and its own clock — or that slot's honest
/// words — and a settled field never reads a 0% or 100% as a chance.
///
/// A championship field is served as ONE futures market (`/api/futures/{id}`,
/// `FuturesMarketDetail`): the winner market, one outcome per contender.
/// Everything below reads that one body and decides nothing the app does not
/// already decide; each slot is the output of the authority that owns it:
///
///   - phase           the market's own `status`: `"resolved"` is the final; any
///                     other status is before. Nothing in a futures body says a
///                     tournament has STARTED: on every retained field body
///                     `commence_time` is at or after `resolution_date` (IPL
///                     2027-06-20 vs 2027-06-06, PDC 2027-01-22 vs 2027-01-08,
///                     chess 2026-10-29 vs 2026-10-22, rugby equal), so
///                     `FuturesStartDate.shown` refuses all of them. `.during` is
///                     never produced, and no word says "pre-event" about an open
///                     market: a reading is labelled by what it is, a recorded
///                     probability with its own clock.
///   - what one row    `RacingFieldPageAdapter10868.reading` — the accepted racing
///     says           adapter's one composition of the production rules, reused,
///                     not copied: `FuturesDetailRowValue.of` (the Market Details
///                     row rule: `SettledResultDisplay698` then `OutcomeVerdict`,
///                     so an `ungradeable_result` retraction stays a price), the
///                     page's whole-percent decision `futuresDetailRenderedPercents`
///                     through `formatProbability`, and
///                     `SourceAge.isStale(_, after: SourceAge.futuresStaleAfter)`
///                     on the outcome's own `last_updated`. A stale, undated or
///                     resolved-market price is never the headline's chance.
///   - sport words     `sportCategoryDisplayName(llm_sport_category)` — the app's
///                     one category label ("Cricket", "Darts", "Rugby", "Chess").
///   - contender noun  "team" / "player" from the served `llm_sport_category`
///                     and the served market `category` (`"championship"`) only,
///                     for the categories a retained body proves; anything else
///                     is "contender". Never parsed from a name.
///   - venue words     `SourceLabels.label(for:)`; an unnamed venue stays unnamed.
///   - the cohort      the host's held ids; else the reader's chosen contender
///                     first, then the production chart's default — outcomes in
///                     served order (`EvolutionChartView` `prefix(3)`) — to three.
///   - the choice      held by its exact served identity (venue key, market id,
///                     outcome id) — never a name, a rank or a position. While an
///                     update omits it, it keeps the first display position as an
///                     unavailable slot (the chooser's own unresolved-identity
///                     contract): no other contender is promoted into it, no figure
///                     of it is kept, and the served contenders keep their own
///                     positions, key shapes and colours. When it is served again
///                     it resolves again, unchanged. Another market's choice is
///                     never this market's, however its outcome id coincides.
///   - key and tint    by display position: the chart palette
///                     (`EvolutionOutcomeColour.markHex`) and the headline key
///                     shapes, so a headline key always matches its chart line.
///
/// Never here: a start, a score, a standing, a placing or a progress (the state
/// slot is nil; `finishes` is empty, so the final's placing slot says "Final
/// placing unavailable"); a pre-event reading at the final (no start reaches
/// the app to elect one); a compact name; a normalized, summed or complemented
/// chance. Each is a named dependency in the return.
enum FieldEventPageAdapter10868 {
    typealias Racing = RacingFieldPageAdapter10868

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        /// The reader's own calendar, time zone and locale; clock words are said in it.
        let calendar: Calendar
        let locale: Locale
        /// The host's held cohort, by served outcome id, in its order. Nil: the
        /// chosen contender, then the production chart's default.
        let cohort: [Int]?
        /// The contender the reader chose in the field card, by exact identity.
        let chosen: Choice?

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current,
             cohort: [Int]? = nil, chosen: Choice? = nil) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
            self.cohort = cohort
            self.chosen = chosen
        }

        /// The racing adapter's host, for its one row rule and clock words.
        var racing: Racing.Host {
            Racing.Host(now: now, calendar: calendar, locale: locale, cohort: nil)
        }

        /// The golf adapter's host, for the futures chart's axis and clock words.
        var golf: GolfFieldPageAdapter10868.Host {
            GolfFieldPageAdapter10868.Host(now: now, calendar: calendar, locale: locale)
        }
    }

    /// The reader's choice, held by the exact served identity it was made on.
    /// No name, no figure and no scope: the scope says the phase, and a choice
    /// outlives a phase change.
    struct Choice: Hashable {
        let source: String
        let marketID: String
        let outcomeID: String
    }

    /// What one contender is called on this page.
    struct Contender: Equatable {
        let singular: String
        let plural: String
        /// The singular opening a sentence.
        let title: String

        static let team = Contender(singular: "team", plural: "teams", title: "Team")
        static let player = Contender(singular: "player", plural: "players", title: "Player")
        static let contender = Contender(singular: "contender", plural: "contenders", title: "Contender")
    }

    /// Served `llm_sport_category` values whose retained championship field
    /// body is a field of teams (2027 IPL Champion, 2027 Men's Rugby World Cup
    /// Winner). Deliberately only the proven ones: a `championship` market of a
    /// team sport is not always a field of teams — the retained Kalshi "Series
    /// Exact Score: Chicago WS vs Houston" (baseball, `championship`, mutually
    /// exclusive) has outcomes like "CWS wins 2-0" — so anything unproven is a
    /// "contender".
    static let teamSports: Set<String> = ["cricket", "rugby"]

    /// The same for fields of individual players (PDC World Championship
    /// Winner, U.S. Women's Chess Championship Winner).
    static let playerSports: Set<String> = ["darts", "chess"]

    /// The served market category of a winner field.
    static let championshipCategory = "championship"

    /// The fixed words; the approved racing copy where it applies.
    enum Words {
        static let winChance = "Win chance"
        static let recordedWin = "Recorded win"
        static let preEventWin = "Pre-event win"
        /// One word for any unavailable current reading: a stale, unpriced or
        /// settled row is UNAVAILABLE as a chance — it may well have been
        /// recorded, and the history beside it can show that it was.
        static let winChanceUnavailable = "Win chance unavailable"
        static let noRecent = "No recent probability"
        /// A graded row: a result, never a chance.
        static let settledNoChance = "Settled · no current chance"
        /// At the final: no start reaches the app to elect a pre-event reading
        /// from. The readings exist (the history shows them); which one was
        /// pre-event is what is unavailable.
        static let noPreEvent = "Pre-event chance unavailable"
        static let finalPlacing = "Final placing"
        static let finalPlacingUnavailable = "Final placing unavailable"
        static let recordedEyebrow = "Recorded probabilities"
        static let settledEyebrow = "Settled market"
        static let beforeGraphic = "Recorded win chances"
        static let finalGraphic = "Pre-event win chances and final placings"
        static let aboutLabel = "About these chances"
        static let aboutHint = "Opens how these chances are recorded"
        static let aboutTitle = "How these chances are recorded"
        static let resultTitle = "Result"
        static let resultUnknown = "Result unknown"
        static let resultUnavailable = "Result unavailable"
        static let historySeparately = "History shown in the chart"
        static let browseStatus = "Chance to win"
        static let readerBefore = "Recorded win chances"
        static let readerFinal = "Settled market"
        static let unattributed = "unattributed"

        static func empty(_ contender: Contender) -> String { "No \(contender.plural) in this update" }
        static func unavailable(_ contender: Contender) -> String { "\(contender.title) unavailable in this update" }
        /// The held choice while this update does not serve it.
        static func chosenUnavailable(_ contender: Contender) -> String {
            "Chosen \(contender.singular) unavailable in this update"
        }
        static func openHint(_ contender: Contender) -> String { "Opens this \(contender.singular)’s win history" }
    }

    /// The production chart's default selection size (`EvolutionChartView`).
    static let defaultCohortSize = 3

    // MARK: - Phase

    /// The market's own state. Never read from a price, a clock or a name.
    static func phase(_ market: FuturesMarketDetail) -> FieldOutlookPhase10868 {
        Racing.phase(market)
    }

    static func phaseWord(_ phase: FieldOutlookPhase10868) -> String {
        Racing.phaseWord(phase)
    }

    // MARK: - Words from served fields

    /// "team" / "player" for a served championship field of a known sport;
    /// otherwise "contender".
    static func contender(_ market: FuturesMarketDetail) -> Contender {
        guard market.category?.lowercased() == championshipCategory,
              let sport = market.llmSportCategory?.lowercased() else { return .contender }
        if teamSports.contains(sport) { return .team }
        if playerSports.contains(sport) { return .player }
        return .contender
    }

    /// The app's one category label, or nil without a served category.
    static func sportWords(_ market: FuturesMarketDetail) -> String? {
        guard let category = market.llmSportCategory, !category.isEmpty else { return nil }
        return sportCategoryDisplayName(category)
    }

    // MARK: - Identity

    /// One owner scope per market and phase.
    static func scope(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> String {
        "field:\(market.id):\(phaseWord(phase)):contenders"
    }

    /// The venue half of an identity key: the served source key, or
    /// `unattributed`. A key only — a venue is named to the reader through
    /// `SourceLabels` (#4135), never through this.
    static func venueKey(_ market: FuturesMarketDetail) -> String {
        Racing.venueKey(market)
    }

    /// `(scope, source, market id, outcome id)` from the served ids. Never a
    /// name, a rank or a position.
    static func ref(_ outcome: FuturesOutcome, in market: FuturesMarketDetail,
                    scope: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: venueKey(market),
                                     marketID: String(market.id), outcomeID: String(outcome.id))
    }

    /// Exactly one served outcome with this id, or nil.
    static func outcome(_ id: Int, in market: FuturesMarketDetail) -> FuturesOutcome? {
        let matches = market.outcomes.filter { $0.id == id }
        return matches.count == 1 ? matches[0] : nil
    }

    // MARK: - The reader's choice

    /// The choice a field-card ref names: only this market's (same venue key and
    /// market id) and only an outcome this update serves exactly once.
    static func choice(_ ref: FieldChooserOriginalRef10868, in market: FuturesMarketDetail) -> Choice? {
        guard ref.marketID == String(market.id), ref.source == venueKey(market),
              let id = Int(ref.outcomeID), outcome(id, in: market) != nil
        else { return nil }
        return Choice(source: ref.source, marketID: ref.marketID, outcomeID: ref.outcomeID)
    }

    /// The host's choice when it was made on THIS market. Another market's
    /// choice is not carried onto this one, however its outcome id coincides.
    static func heldChoice(_ market: FuturesMarketDetail, host: Host) -> Choice? {
        guard let chosen = host.chosen, chosen.marketID == String(market.id), chosen.source == venueKey(market)
        else { return nil }
        return chosen
    }

    /// The served outcome this market's held choice names in this update, or nil.
    static func chosenOutcome(_ market: FuturesMarketDetail, host: Host) -> FuturesOutcome? {
        guard let choice = heldChoice(market, host: host), let id = Int(choice.outcomeID) else { return nil }
        return outcome(id, in: market)
    }

    /// This market's held choice while this update does not serve it exactly
    /// once. It stays the choice — shown unavailable, never replaced.
    static func missingChoice(_ market: FuturesMarketDetail, host: Host) -> Choice? {
        guard let choice = heldChoice(market, host: host), chosenOutcome(market, host: host) == nil else { return nil }
        return choice
    }

    /// The choice's exact identity in a scope: it resolves while the choice is
    /// served and is unavailable while an update omits it.
    static func ref(_ choice: Choice, scope: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: choice.source,
                                     marketID: choice.marketID, outcomeID: choice.outcomeID)
    }

    // MARK: - The cohort

    /// The displayed contenders by display position.
    struct Cohort {
        /// This market's held choice while this update omits it: display
        /// position 0, unavailable. Nil otherwise.
        let missing: Choice?
        /// The served contenders shown, in display order after any held position.
        let served: [FuturesOutcome]

        /// The display position of `served[index]`: after the held position, so
        /// each served contender keeps its key shape and colour across an omission.
        func position(_ index: Int) -> Int {
            index + (missing == nil ? 0 : 1)
        }

        /// The display position of a served outcome, or nil when it is not shown.
        func position(of outcome: FuturesOutcome) -> Int? {
            served.firstIndex { $0.id == outcome.id }.map { position($0) }
        }
    }

    /// The host's held ids, each kept once and only while it names exactly one
    /// served outcome. Without them: this market's held choice first — served,
    /// or holding position 0 as unavailable while omitted — then served order,
    /// to three.
    static func cohort(_ market: FuturesMarketDetail, host: Host) -> Cohort {
        if let held = host.cohort { return Cohort(missing: nil, served: Racing.cohort(market, held: held)) }
        let missing = missingChoice(market, host: host)
        var ids: [Int] = []
        if let chosen = chosenOutcome(market, host: host) { ids.append(chosen.id) }
        let room = defaultCohortSize - (missing == nil ? 0 : 1)
        for served in market.outcomes where ids.count < room && !ids.contains(served.id) {
            if outcome(served.id, in: market) != nil { ids.append(served.id) }
        }
        return Cohort(missing: missing, served: ids.compactMap { outcome($0, in: market) })
    }

    /// The chart's colour for a display position.
    static func tint(_ position: Int) -> Color {
        Racing.tint(position)
    }

    /// The headline key for a display position; part two draws the same shape.
    static func keyShape(_ position: Int) -> FieldHeadlineKeyShape10868 {
        Racing.keyShape(position)
    }

    // MARK: - What one row says now

    static func reading(_ outcome: FuturesOutcome, in market: FuturesMarketDetail, host: Host) -> Racing.Reading {
        Racing.reading(outcome, in: market, host: host.racing)
    }

    // MARK: - The catalogue

    /// The one plan reading for an original in this phase. At the final no
    /// pre-event reading can be elected (no start reaches the app).
    static func beforeReading(_ outcome: FuturesOutcome, in market: FuturesMarketDetail,
                              phase: FieldOutlookPhase10868, host: Host) -> FieldChooserReading10868 {
        guard phase == .before else {
            return FieldChooserReading10868(label: Words.preEventWin, value: .missing(Words.noPreEvent))
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
        case .chance, .stale, .unpriced: words = Words.resultUnavailable
        }
        return FieldChooserResult10868(title: Words.resultTitle, words: words)
    }

    /// Every served outcome once, in served order. A displayed contender
    /// carries its chart colour; the rest keep the default.
    static func catalogue(_ market: FuturesMarketDetail, cohort: Cohort,
                          phase: FieldOutlookPhase10868, host: Host) -> [FieldChooserOriginal10868] {
        let scope = Self.scope(market, phase: phase)
        return market.outcomes.map { outcome in
            let accent: Color? = cohort.position(of: outcome).map(tint)
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
        let shown = cohort(market, host: host)
        var slots: [FieldHeadlineSlot10868] = []
        if let missing = shown.missing {
            // The held choice, omitted by this update: its exact identity, which
            // the catalogue cannot resolve, so the slot shows the unavailable
            // words and no figure. No name is held, so none is shown.
            slots.append(FieldHeadlineSlot10868(ref: ref(missing, scope: scope), name: "",
                                                compactName: nil, keyShape: keyShape(0)))
        }
        for (index, outcome) in shown.served.enumerated() {
            slots.append(FieldHeadlineSlot10868(ref: ref(outcome, in: market, scope: scope), name: outcome.name,
                                                compactName: nil, keyShape: keyShape(shown.position(index))))
        }
        let contender = Self.contender(market)
        return FieldHeadlineInput10868(
            scope: scope,
            catalogue: catalogue(market, cohort: shown, phase: phase, host: host),
            displayed: slots,
            pairs: shown.served.map { pair($0, in: market, phase: phase, host: host) },
            finishes: [],
            state: nil,
            phase: phase,
            copy: headlineCopy(market, phase: phase, compact: compact),
            // Every served slot resolves by construction, so the only slot that can
            // be unavailable while a choice is omitted is that choice.
            unavailableWords: shown.missing == nil ? Words.unavailable(contender) : Words.chosenUnavailable(contender),
            // No start reaches the app, so no reading is a qualified pre-event
            // baseline: the keys stay neutral and recorded, like the chart's marks
            // (Design-approved package-34 amendment, 5e6d8c05).
            keyTreatment: .neutralRecorded)
    }

    /// The owner's one association per displayed contender: the raw value
    /// behind the plan's own reading, only while that reading is a figure. No
    /// later observation: nothing proves a reading was taken during play.
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
        let contender = Self.contender(market)
        let stage = phase == .final ? Words.settledEyebrow : Words.recordedEyebrow
        let eyebrow: String = sportWords(market).map { "\($0) · \(stage)" } ?? stage
        return FieldHeadlineCopy10868(
            eyebrow: compact ? nil : eyebrow,
            title: compact ? nil : market.name,
            graphicLabel: phase == .final ? Words.finalGraphic : Words.beforeGraphic,
            beforeLabel: phase == .final ? Words.preEventWin : Words.winChance,
            recordedLabel: Words.recordedWin,
            beforeUnavailable: phase == .final ? Words.noPreEvent : Words.winChanceUnavailable,
            recordedUnavailable: Words.noRecent,
            finishLabel: Words.finalPlacing,
            finishUnavailable: Words.finalPlacingUnavailable,
            empty: Words.empty(contender),
            aboutLabel: Words.aboutLabel,
            aboutHint: Words.aboutHint,
            openHint: Words.openHint(contender))
    }

    // MARK: - Reader heading and About

    /// The market's own name and what the page is reading.
    static func readerHeader(_ market: FuturesMarketDetail) -> FieldEventPageReaderHeader10868 {
        FieldEventPageReaderHeader10868(title: market.name,
                                        state: phase(market) == .final ? Words.readerFinal : Words.readerBefore)
    }

    /// How this page reads the field, in the owner's words. The stale bound is
    /// said from `SourceAge.futuresStaleAfter` itself.
    static func about(_ market: FuturesMarketDetail) -> FieldEventPageAbout10868 {
        let contender = Self.contender(market)
        let venue = SourceLabels.label(for: market.source)
        let own = venue.map { "own \($0) probability" } ?? "own probability"
        let hours = Int(SourceAge.futuresStaleAfter / 3600)
        var paragraphs = [
            "Each \(contender.singular)’s chance is that \(contender.singular)’s \(own) in “\(market.name)”, shown with the time it was last recorded. The chances are independent: they are not adjusted to add up to 100%.",
            "Start times, scores and standings are unavailable here, so readings are not split into before and during play, and no score or placing is shown.",
            "A reading not updated in the last \(hours) hours is not shown as a current chance; its last recorded value stays in that original’s Details.",
        ]
        if phase(market) == .final {
            let settler = venue.map { "\($0)’s settlement" } ?? "the venue’s settlement"
            paragraphs.append("Results come only from \(settler) of each original. A settled 0% or 100% is a result, not a chance, and is never shown on the chart.")
        }
        return FieldEventPageAbout10868(title: Words.aboutTitle, paragraphs: paragraphs)
    }

    // MARK: - Words

    static func clockWords(_ date: Date, host: Host) -> String {
        Racing.clockWords(date, host: host.racing)
    }
}
