import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART THREE: THE
/// SELECTED GOLFER'S FINISH OUTLOOK.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on `golf-outlook` (and every golf screen
/// that shows the finish card) the selected golfer's Win, Top 5, Top 10, Top 20
/// and Make cut chances are each that market's own price with its own time, a
/// missing price stays "not recorded", and after the final each finish shows the
/// result its own market was graded with — never a 100% bar, a rank or a guess.
///
/// It builds `GolfFinishExpectationInput10868` from the markets the host already
/// holds: the Winner market (the same `GolfFieldHistoryAdapter10868.Field` the
/// chart reads, so the Win slot and the chart can never read the golfer two
/// ways) and, when the host holds them, the Top 5 / Top 10 / Top 20 / Make the
/// Cut markets (`FuturesMarketDetail`, optionally with their own `/history`).
///
///   - which outcome  the Winner market's outcome id for Win; for every other
///                    finish, the outcome id the HOST's join names for that
///                    golfer in that market (`Leg.outcomes`). Nothing here
///                    matches a golfer across markets by name, rank or position —
///                    the retained India markets order Make the Cut differently
///                    from Winner, and the server's own join (`_match_key(name)`
///                    in routes/golf.py) is not an identity.
///   - readings       `Field.before` / `Field.later` in that market: its own
///                    observation or price at its own clock, the before reading
///                    strictly before the Winner market's listed start, the
///                    recorded estimate only at or after it. Each finish is its
///                    own price: nothing is compared, summed, clamped or made
///                    monotone (the tournament endpoint's Win ≤ Top 5 ≤ … clamp is
///                    not this card's input).
///   - results        final only: `FuturesDetailRowValue.of` (the Market Details
///                    rule) — Won / Lost from a grade, "Result unknown" for a
///                    #698 unknown, and "Result unavailable" for a resolved row
///                    with no grade. The retained Baycurrent Classic Winner market
///                    is resolved with no grade on any row: Michael Brennan won,
///                    his DataGolf line reached 1.0, and his Win result still
///                    reads "Result unavailable" — the grade is the only source.
///   - Make cut       a fifth slot only when the host holds a Make the Cut market;
///                    without one, exactly the original four.
///
/// OWED, NOT MANUFACTURED:
///   - the per-golfer join across finish markets: no production identity links a
///     Winner outcome to its Top 5 / Top 10 / Top 20 / Make the Cut outcomes
///     (`/history`'s leaderboard serves a `dg_id`, undecoded), and
///     `GolfTournamentDetailResponse` decodes neither `markets` nor
///     `evolution_market_id`. The host supplies the join. Owner: golf endpoint +
///     Native models.
///   - the finishing position summary ("T9 · −12"): no confirmed position source
///     keyed to this tournament and golfer; `actualSummary` is nil.
///   - Details: no destination exists, so the host passes no Details callback.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum GolfFieldFinishAdapter10868 {
    typealias Host = GolfFieldPageAdapter10868.Host
    typealias Field = GolfFieldHistoryAdapter10868.Field

    /// The five finishes, in the card's fixed order.
    enum Kind: String, CaseIterable {
        case win
        case top5
        case top10
        case top20
        case makeCut

        var name: String {
            switch self {
            case .win: "Win"
            case .top5: "Top 5"
            case .top10: "Top 10"
            case .top20: "Top 20"
            case .makeCut: "Make cut"
            }
        }
    }

    /// One finish market the host already holds, with the owner's join.
    struct Leg {
        let market: FuturesMarketDetail
        /// That market's own `/history`, when the host holds it; nil leaves its
        /// before reading to the market's own price and clock.
        let history: FuturesHistoryResponse?
        /// Winner-market outcome id → this market's outcome id for the same golfer.
        let outcomes: [Int: Int]

        init(market: FuturesMarketDetail, history: FuturesHistoryResponse? = nil, outcomes: [Int: Int]) {
            self.market = market
            self.history = history
            self.outcomes = outcomes
        }
    }

    /// The non-Win finish markets the host holds; any may be absent.
    struct Legs {
        var top5: Leg?
        var top10: Leg?
        var top20: Leg?
        var makeCut: Leg?

        init(top5: Leg? = nil, top10: Leg? = nil, top20: Leg? = nil, makeCut: Leg? = nil) {
            self.top5 = top5
            self.top10 = top10
            self.top20 = top20
            self.makeCut = makeCut
        }
    }

    enum Words {
        static let title = "Finish outlook"
        static let beforeContext = "Before the start date · each chance keeps its own time"
        static let recordedContext = "Since the start date · each chance keeps its own time"
        static let noStartContext = "Each chance keeps its own time"
        static let finalContext = "Final · each result comes from its own market"
        static let notBeforeStart = GolfFieldHistoryAdapter10868.Words.notBeforeStart
        static let notSinceStart = GolfFieldHistoryAdapter10868.Words.notSinceStart
        static let noStart = GolfFieldHistoryAdapter10868.Words.noStartWords
        static let resultUnknown = "Result unknown"
        static let resultUnavailable = "Result unavailable"

        static func unavailable(_ kind: Kind) -> String { "\(kind.name) chance unavailable" }
    }

    // MARK: - The finish card

    /// The selected golfer's finishes, or nil when the golfer is not exactly one
    /// Winner-market outcome.
    static func finish(_ winner: Field, golfer: Int, legs: Legs, tint: Color,
                       selectedFinish: String?, host: Host) -> GolfFinishExpectationInput10868? {
        guard let golferOutcome = winner.outcome(golfer) else { return nil }
        let win = slot(.win, field: winner, outcomeID: golfer, tint: tint, host: host)
        let top5 = slot(.top5, leg: legs.top5, winner: winner, golfer: golfer, tint: tint, host: host)
        let top10 = slot(.top10, leg: legs.top10, winner: winner, golfer: golfer, tint: tint, host: host)
        let top20 = slot(.top20, leg: legs.top20, winner: winner, golfer: golfer, tint: tint, host: host)
        let makeCut: GolfFinishSlot10868? = legs.makeCut.map {
            slot(.makeCut, leg: $0, winner: winner, golfer: golfer, tint: tint, host: host)
        }
        return GolfFinishExpectationInput10868(
            win: win, top5: top5, top10: top10, top20: top20,
            phase: winner.phase,
            title: Words.title,
            golferName: golferOutcome.name,
            context: context(winner),
            actualSummary: nil,
            selected: winner.phase == .recorded ? selectedFinish : nil,
            makeCut: makeCut)
    }

    static func context(_ winner: Field) -> String {
        switch winner.phase {
        case .before: return Words.beforeContext
        case .recorded: return winner.listedStart == nil ? Words.noStartContext : Words.recordedContext
        case .final: return Words.finalContext
        }
    }

    /// A non-Win finish: its market read as its own field, on the Winner
    /// market's phase, start and clock.
    static func slot(_ kind: Kind, leg: Leg?, winner: Field, golfer: Int, tint: Color,
                     host: Host) -> GolfFinishSlot10868 {
        let field = leg.map {
            Field(market: $0.market, history: $0.history, phase: winner.phase,
                  listedStart: winner.listedStart, now: winner.now)
        }
        return slot(kind, field: field, outcomeID: leg?.outcomes[golfer], tint: tint, host: host)
    }

    static func slot(_ kind: Kind, field: Field?, outcomeID: Int?, tint: Color, host: Host) -> GolfFinishSlot10868 {
        guard let field, let outcomeID, let outcome = field.outcome(outcomeID) else {
            return GolfFinishSlot10868(
                selection: "golf.finish.\(kind.rawValue).unavailable", name: kind.name, color: tint,
                before: nil, recorded: nil,
                beforeMissing: Words.unavailable(kind), recordedMissing: Words.unavailable(kind),
                actual: GolfFinishResult10868(text: Words.resultUnavailable, mark: .unknown))
        }
        let recorded: GolfFinishObservation10868? = field.phase == .recorded
            ? field.later(outcomeID).map { observation($0, market: field.market, host: host) }
            : nil
        return GolfFinishSlot10868(
            selection: selection(field.market, outcomeID: outcome.id),
            name: kind.name,
            color: tint,
            before: field.before(outcomeID).map { observation($0, market: field.market, host: host) },
            recorded: recorded,
            beforeMissing: field.listedStart == nil ? Words.noStart : Words.notBeforeStart,
            recordedMissing: Words.notSinceStart,
            actual: result(field, outcome: outcome))
    }

    static func observation(_ reading: GolfFieldHistoryAdapter10868.Reading, market: FuturesMarketDetail,
                            host: Host) -> GolfFinishObservation10868 {
        GolfFinishObservation10868(
            probability: reading.probability,
            text: GolfFieldHistoryAdapter10868.figure(reading),
            accessibilityDetail: GolfFieldHistoryAdapter10868.provenance(reading, market: market, host: host))
    }

    /// The Market Details rule's result for this row. Read only at the final.
    static func result(_ field: Field, outcome: FuturesOutcome) -> GolfFinishResult10868 {
        switch FuturesDetailRowValue.of(outcome, marketStatus: field.market.status, marketSource: field.market.source) {
        case .verdict(let verdict):
            return GolfFinishResult10868(text: verdict.label, mark: verdict == .won ? .success : .failure)
        case .resultUnknown:
            return GolfFinishResult10868(text: Words.resultUnknown, mark: .unknown)
        case .price, .none:
            return GolfFinishResult10868(text: Words.resultUnavailable, mark: .unknown)
        }
    }

    /// A stable, opaque selection id: source key, market and outcome.
    static func selection(_ market: FuturesMarketDetail, outcomeID: Int) -> String {
        "\(GolfFieldPageAdapter10868.sourceKey(market))|\(market.id)|\(outcomeID)"
    }
}
