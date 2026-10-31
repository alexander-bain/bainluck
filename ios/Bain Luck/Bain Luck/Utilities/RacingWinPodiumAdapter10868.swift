import SwiftUI

/// #10868 — THE RACING SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE WIN AND
/// PODIUM COMPARISON CARD.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: a race fan compares a driver's own Win
/// chance and own Podium chance on the approved visual card
/// (`FieldWinPodiumPresentation10868`), each market's own price with its own
/// clock — never added together, never borrowed from the other market or
/// another driver — and after the race each market's own result.
///
/// It builds `FieldPodiumInput10868` from two market bodies the host already
/// holds (`FuturesMarketDetail`): the race's driver-winner market (the page's
/// own) and its driver-podium market, plus THE ADOPTING OWNER'S JOIN between
/// them (`Join`). It decides nothing the app does not already decide:
///
///   - which pair    a driver's winner outcome and the podium outcome the
///                   OWNER'S JOIN names for that winner outcome. Nothing here
///                   matches a driver across the two markets by name, rank or
///                   position: they are separate markets with separate ids
///                   (`63989371` / `63989361` for Singapore) and the only common
///                   key in either body is the outcome name, which is not an
///                   identity. The join also names the two market ids it was
///                   built for, so it is never applied to another pair of
///                   markets. A join entry is kept only while it is unambiguous:
///                   its winner outcome is served exactly once, and no other
///                   winner outcome claims the same podium outcome (a podium
///                   outcome claimed twice pairs neither driver).
///   - roster order  the winner market's served order (the production chart's
///                   order, not a ranking); every kept pair is reachable by
///                   Previous / Next. The reference's podium-chance sort and its
///                   five-row window are not ported.
///   - the window    part one's displayed drivers (`RacingFieldPageAdapter10868.cohort`:
///                   the host's held cohort, else the first three served), so the
///                   card's rows are the headline's and the chart's drivers. A
///                   displayed driver the join does not pair keeps its row with
///                   the card's pairing-unavailable words and no mark.
///   - selection     the host's held pair id, unchanged — an id this update does
///                   not carry stays held and says the driver is unavailable,
///                   with nothing else selected in its place; with none held, the
///                   first displayed pair (the chart's first line).
///   - each side     part one's row rule on THAT side's own market
///                   (`RacingFieldPageAdapter10868.beforeReading` / `reading`):
///                   its own status, price, whole-percent decision, clock, venue
///                   and `SourceAge.futuresStaleAfter` currentness. A stale,
///                   undated, unpriced or settled side shows its own words; only a
///                   recent dated price is a figure and a mark. The raw price is
///                   the one behind that figure: never normalized, summed,
///                   complemented or made monotone (a podium chance below the same
///                   driver's win chance stays as served).
///   - results       at the final only, `RacingFieldPageAdapter10868.result` on
///                   each side's own market: the venue's own grade, "Result
///                   unknown" for a #698 unknown, "Not yet confirmed" for a market
///                   not graded — never a Lost from a missing grade, a price or
///                   the other market.
///   - phase         the page's (the winner market's own status). Nothing in a
///                   futures body says a race has started, so `.during` is never
///                   produced, and at the final no start clock elects a pre-race
///                   reading: both sides say "Pre-race chance unavailable".
///
/// Never here: a physical finish or classification (`finishes` is empty, so the
/// final's finish slot says "Finish unavailable"); a live state, lap or gap; a
/// baseline or pre-race election; a compact surname (never parsed from a name).
///
/// OWED, NOT MANUFACTURED (named in the return):
///   - the podium market body: no production owner fetches the race's podium
///     market beside its winner market (`FuturesDetailView` holds one body).
///   - the join: no production identity links a winner outcome to the same
///     driver's podium outcome. The adopting owner supplies it from a served
///     participant identity; until then the card is absent and earns no route
///     readiness.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum RacingWinPodiumAdapter10868 {
    typealias Page = RacingFieldPageAdapter10868

    /// The adopting owner's join between one race's two markets.
    struct Join: Equatable {
        /// The driver-winner market this join was built for.
        let winnerMarketID: Int
        /// The driver-podium market this join was built for.
        let podiumMarketID: Int
        /// Winner-market outcome id → podium-market outcome id for the same driver.
        let outcomes: [Int: Int]

        init(winnerMarketID: Int, podiumMarketID: Int, outcomes: [Int: Int]) {
            self.winnerMarketID = winnerMarketID
            self.podiumMarketID = podiumMarketID
            self.outcomes = outcomes
        }
    }

    /// The race's podium market the host already holds, with the owner's join.
    struct Podium {
        let market: FuturesMarketDetail
        let join: Join

        init(market: FuturesMarketDetail, join: Join) {
            self.market = market
            self.join = join
        }
    }

    /// The card's input and its About, for the page.
    struct Card: Equatable {
        let input: FieldPodiumInput10868
        let about: RacingEventPageAbout10868
    }

    /// One kept pair: the winner outcome and the podium outcome id the join names.
    struct Joined: Equatable {
        let winner: FuturesOutcome
        let podiumOutcomeID: Int
    }

    /// The fixed words. Approved card copy where it applies; plain availability
    /// words everywhere else.
    enum Words {
        static let title = "Win and podium chances"
        static let explanation = "A podium means finishing in the top three. Win and podium are separate markets, each with its own time."
        static let recordedContext = "Recorded chances · each keeps its own time"
        static let finalContext = "Each result comes from its own market"
        static let winLabel = "Win"
        static let podiumLabel = "Finish top 3"
        static let recordedLabel = "Recorded chance"
        static let preRaceLabel = "Pre-race"
        static let podiumChance = "Podium chance"
        static let preRacePodium = "Pre-race podium"
        static let pairUnavailable = "Driver pairing unavailable in this update"
        static let chanceUnavailable = "Chance unavailable in this update"
        static let chooseDriver = "Choose a driver"
        static let outsideWindow = "Selected driver is outside this group"
        static let previous = "Previous driver"
        static let next = "Next driver"
        static let chooseHint = "Shows this driver’s two chances"
        static let originalHint = "Opens this exact original"
        static let aboutLabel = "How to read this comparison"
        static let aboutHint = "Opens how these two chances are recorded"
        static let scale = "0–100% · each mark is its own market’s chance"
        static let noRecentScale = "No recent chance to place on the scale"
        static let noPreRaceScale = "Pre-race chances unavailable"
        static let winnerStatus = Page.Words.browseStatus
        static let podiumStatus = "Podium finish"
        /// The chart draws the winner market only.
        static let podiumHistory = "Podium history unavailable"
        static let cardName = title
    }

    /// The 0–100% ticks, labelled by the chart axis's own words.
    static let scaleTicks: [Double] = [0, 0.5, 1]

    /// The approved card's two market colours (`racingPodiumPaths.css`:
    /// `--series-home` for Win, `--series-away` for Podium). Shape (circle /
    /// square) and the visible key carry the meaning without colour.
    static let winTint = Color(hex: "#254DD9")
    static let podiumTint = Color(hex: "#057A70")

    // MARK: - The card

    /// The card for the page at `host.now`, or nil when the host holds no podium
    /// market, the join was built for other markets, or it pairs no driver.
    /// `selected` is the host's held pair id, passed through unchanged.
    static func card(race: FuturesMarketDetail, podium: Podium?, selected: String?, host: Page.Host) -> Card? {
        guard let podium, let kept = joined(race: race, podium: podium), !kept.isEmpty else { return nil }
        let phase = Page.phase(race)
        let scope = Self.scope(race, phase: phase)
        let pairs = kept.map { pair($0, race: race, podium: podium.market, scope: scope) }
        let pairByWinner = Dictionary(uniqueKeysWithValues: zip(kept.map(\.winner.id), pairs))

        let shown = Page.cohort(race, held: host.cohort)
        let displayed = shown.map { outcome in
            FieldPodiumSlot10868(pairID: pairByWinner[outcome.id]?.id ?? unpairedID(outcome, scope: scope),
                                 name: outcome.name, compactName: nil)
        }
        let firstPair: String? = displayed.first { slot in pairs.contains { $0.id == slot.pairID } }?.pairID
        let selectedID: String? = selected ?? firstPair
        let index: Int? = selectedID.flatMap { id in pairs.firstIndex { $0.id == id } }
        let previousID: String? = index.flatMap { $0 > 0 ? pairs[$0 - 1].id : nil }
        let nextID: String? = index.flatMap { $0 + 1 < pairs.count ? pairs[$0 + 1].id : nil }
        let heldMissing = selected != nil && index == nil

        var catalogue: [FieldChooserOriginal10868] = []
        var chances: [FieldOutlookBeforeChance10868] = []
        for (market, side) in [(race, Side.win), (podium.market, Side.podium)] {
            for outcome in market.outcomes {
                let built = original(outcome, in: market, side: side, phase: phase, scope: scope, host: host)
                catalogue.append(built.original)
                if let chance = built.chance { chances.append(chance) }
            }
        }

        let input = FieldPodiumInput10868(
            scope: scope,
            catalogue: catalogue,
            pairs: pairs,
            displayed: displayed,
            selectedID: selectedID,
            previousID: previousID,
            nextID: nextID,
            chances: chances,
            finishes: [],
            scale: scale(placed: !chances.isEmpty, phase: phase),
            phase: phase,
            winTint: winTint,
            podiumTint: podiumTint,
            copy: copy(phase: phase, heldMissing: heldMissing))
        return Card(input: input, about: about(race: race, podium: podium.market))
    }

    /// One owner scope per race market and phase.
    static func scope(_ race: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> String {
        "racing:\(race.id):\(Page.phaseWord(phase)):win-podium"
    }

    // MARK: - The join

    /// The join's unambiguous entries, in the winner market's served order. Nil
    /// when the join names other markets, or the podium market is the race's own.
    static func joined(race: FuturesMarketDetail, podium: Podium) -> [Joined]? {
        let join = podium.join
        guard join.winnerMarketID == race.id, join.podiumMarketID == podium.market.id,
              podium.market.id != race.id else { return nil }
        var claims: [Int: Int] = [:]
        for target in join.outcomes.values { claims[target, default: 0] += 1 }
        var served: [Int: Int] = [:]
        for outcome in race.outcomes { served[outcome.id, default: 0] += 1 }
        return race.outcomes.compactMap { outcome in
            guard served[outcome.id] == 1, let target = join.outcomes[outcome.id], claims[target] == 1 else { return nil }
            return Joined(winner: outcome, podiumOutcomeID: target)
        }
    }

    /// The pair's exact identity: both sides' venue, market and outcome ids. A
    /// held pair never transfers to another market or another join.
    static func pairID(_ joined: Joined, race: FuturesMarketDetail, podium: FuturesMarketDetail) -> String {
        "\(Page.venueKey(race))|\(race.id)|\(joined.winner.id)+\(Page.venueKey(podium))|\(podium.id)|\(joined.podiumOutcomeID)"
    }

    /// A displayed driver the join does not pair: an id no pair carries, so the
    /// card keeps the row with its pairing-unavailable words.
    static func unpairedID(_ outcome: FuturesOutcome, scope: String) -> String {
        "\(scope)|unpaired|\(outcome.id)"
    }

    static func pair(_ joined: Joined, race: FuturesMarketDetail, podium: FuturesMarketDetail,
                     scope: String) -> FieldPodiumPair10868 {
        FieldPodiumPair10868(
            id: pairID(joined, race: race, podium: podium),
            name: joined.winner.name,
            win: Page.ref(joined.winner, in: race, scope: scope),
            podium: FieldChooserOriginalRef10868(scope: scope, source: Page.venueKey(podium),
                                                 marketID: String(podium.id),
                                                 outcomeID: String(joined.podiumOutcomeID)))
    }

    // MARK: - One original

    enum Side {
        case win
        case podium
    }

    /// One served outcome of either market as the card's canonical original, and
    /// the raw price behind its figure while that figure is a recent chance.
    static func original(_ outcome: FuturesOutcome, in market: FuturesMarketDetail, side: Side,
                         phase: FieldOutlookPhase10868, scope: String,
                         host: Page.Host) -> (original: FieldChooserOriginal10868, chance: FieldOutlookBeforeChance10868?) {
        let reading = sideReading(outcome, in: market, side: side, phase: phase, host: host)
        let ref = Page.ref(outcome, in: market, scope: scope)
        let original = FieldChooserOriginal10868(
            ref: ref,
            name: outcome.name,
            plan: .single(reading),
            preview: FieldChooserPreview10868(history: nil,
                                              absence: side == .win ? Page.Words.historySeparately : Words.podiumHistory),
            movement: nil,
            clock: nil,
            result: Page.result(outcome, in: market, phase: phase, host: host),
            browseStatus: side == .win ? Words.winnerStatus : Words.podiumStatus)
        var chance: FieldOutlookBeforeChance10868?
        if phase == .before, case .recorded = reading.value,
           case .chance(let probability, _, _) = Page.reading(outcome, in: market, host: host) {
            chance = FieldOutlookBeforeChance10868(ref: ref, probability: probability, reading: reading)
        }
        return (original, chance)
    }

    /// Part one's reading for this phase, on this side's own market, under this
    /// side's own label. The value is part one's, unchanged.
    static func sideReading(_ outcome: FuturesOutcome, in market: FuturesMarketDetail, side: Side,
                            phase: FieldOutlookPhase10868, host: Page.Host) -> FieldChooserReading10868 {
        let reading = Page.beforeReading(outcome, in: market, phase: phase, host: host)
        guard side == .podium else { return reading }
        return FieldChooserReading10868(label: phase == .before ? Words.podiumChance : Words.preRacePodium,
                                        value: reading.value)
    }

    // MARK: - Scale and words

    /// A scale is offered only while at least one chance can be placed on it;
    /// otherwise every row keeps its two readings as words, with no empty track.
    static func scale(placed: Bool, phase: FieldOutlookPhase10868) -> FieldOutlookScale10868 {
        guard placed else {
            return FieldOutlookScale10868(ceiling: 1, ticks: [],
                                          words: phase == .final ? Words.noPreRaceScale : Words.noRecentScale)
        }
        let ticks = scaleTicks.map { FieldOutlookTick10868(probability: $0, label: OddsChartView.axisLabel(for: $0)) }
        return FieldOutlookScale10868(ceiling: 1, ticks: ticks, words: Words.scale)
    }

    static func copy(phase: FieldOutlookPhase10868, heldMissing: Bool) -> FieldPodiumCopy10868 {
        let final = phase == .final
        return FieldPodiumCopy10868(
            title: Words.title,
            explanation: Words.explanation,
            beforeContext: Words.recordedContext,
            duringContext: Words.recordedContext,
            finalContext: Words.finalContext,
            winLabel: Words.winLabel,
            podiumLabel: Words.podiumLabel,
            beforeLabel: final ? Words.preRaceLabel : Words.recordedLabel,
            pairUnavailable: Words.pairUnavailable,
            chanceUnavailable: final ? Page.Words.noPreRace : Words.chanceUnavailable,
            noSelection: heldMissing ? Page.Words.unavailable : Words.chooseDriver,
            outsideWindow: Words.outsideWindow,
            finishLabel: Page.Words.actualFinish,
            finishUnavailable: Page.Words.finishUnavailable,
            resultLabel: Page.Words.resultTitle,
            resultUnknown: Page.Words.resultUnknown,
            previousLabel: Words.previous,
            nextLabel: Words.next,
            chooseHint: Words.chooseHint,
            originalHint: Words.originalHint,
            aboutLabel: Words.aboutLabel,
            aboutHint: Words.aboutHint)
    }

    /// How to read the comparison, in plain words. Each market and venue is
    /// named from its own body; the stale bound is said from
    /// `SourceAge.futuresStaleAfter` itself.
    static func about(race: FuturesMarketDetail, podium: FuturesMarketDetail) -> RacingEventPageAbout10868 {
        func own(_ market: FuturesMarketDetail) -> String {
            SourceLabels.label(for: market.source).map { "own \($0) probability" } ?? "own probability"
        }
        let hours = Int(SourceAge.futuresStaleAfter / 3600)
        var paragraphs = [
            "The win chance is each driver’s \(own(race)) in “\(race.name)”. The podium chance is that driver’s \(own(podium)) in “\(podium.name)”. A podium means finishing in the top three.",
            "They are two separate markets, each recorded at its own time. They are never added together or adjusted to match, and the line between a driver’s two marks is only a visual comparison.",
            "A reading not updated in the last \(hours) hours is not shown as a current chance; its last recorded value stays in that original’s Details. The race start time is unavailable here, so no reading is shown as a pre-race chance.",
        ]
        if Page.phase(race) == .final {
            paragraphs.append("Results come only from each market’s own settlement. A settled 0% or 100% is a result, not a chance, and finishing positions are unavailable here.")
        }
        return RacingEventPageAbout10868(title: Words.aboutLabel, paragraphs: paragraphs)
    }
}
