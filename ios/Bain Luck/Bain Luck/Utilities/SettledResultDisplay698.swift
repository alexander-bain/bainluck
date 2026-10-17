import Foundation

/// #698 — what a settled Market Details row may SAY about its own result.
///
/// The native twin of web's `frontend/lib/settledResultDisplay.ts` and of the
/// server's `backend/app/utils/settlement_display.py`. Read those for the long
/// WHY; the short version:
///
/// `/futures/62134744` (*Marchi vs. Lokoli: Match O/U 21.5*, Polymarket,
/// resolved) serves both legs as `probability 0.5, is_winner false,
/// resolution_source "clob_authoritative"`. `OutcomeVerdict` reads only the
/// grade and the source, so both rows printed **Lost** over a 50/50 last price
/// that says nothing was decided. Whether that match voided is UNKNOWN; this
/// file does not decide it. It stops the page asserting a result the row does
/// not support.
///
/// ## The contract, and the fallback for an older server
///
/// A resolved Polymarket detail payload serves `settlement_display` on every
/// row. When present it is the answer: `won` / `lost` are results, and every
/// other verdict — `unknown`, a word this build does not know, a missing or
/// malformed value — is unknown. So a new server word can only make the row say
/// LESS.
///
/// When ABSENT on a market the server would have targeted, the app is reading
/// an older server, and the same rule runs here on the SERVED values,
/// conservatively: only an exact `1 + true` / `0 + false` with a source in the
/// tier-3 set (`OutcomeVerdict.authoritativeResolutionSources`, a SUBSET of the
/// server's registry) is a result; anything else is unknown. A subset plus the
/// same terminal rule means the fallback can say less than the server, never
/// more (Root's counterexample: `1 / true / "unrecognized_future_source"` must
/// read unknown).
///
/// Every other market — other sources, open boards — returns nil here and keeps
/// every contract it had (#4788, #6082, #10066, #10964).
///
/// Kept free of SwiftUI so the decision is unit-testable.
nonisolated enum SettledResultDisplay698 {
    /// The markets whose detail rows the server targets.
    static let targetedSources: Set<String> = ["polymarket"]

    /// The row's effective settled result.
    enum Certainty: Equatable, Sendable {
        case won
        case lost
        case unknown
    }

    static func isTargeted(marketSource: String?, marketStatus: String?) -> Bool {
        guard marketStatus == "resolved", let marketSource else { return false }
        return targetedSources.contains(marketSource)
    }

    /// The served contract when present; the fallback on a targeted market;
    /// otherwise nil, meaning "use the legacy rule unchanged".
    static func certainty(
        _ outcome: FuturesOutcome,
        marketSource: String?,
        marketStatus: String?
    ) -> Certainty? {
        guard marketStatus == "resolved" else { return nil }
        if let served = outcome.settlementDisplay {
            switch served.verdict {
            case "won": return .won
            case "lost": return .lost
            default: return .unknown
            }
        }
        guard isTargeted(marketSource: marketSource, marketStatus: marketStatus) else { return nil }
        return fallback(
            probability: outcome.probability,
            isWinner: outcome.isWinner,
            resolutionSource: outcome.resolutionSource
        )
    }

    /// The absent-contract fallback on the SERVED values. A non-empty source
    /// string is not enough: it must be in the tier-3 set.
    static func fallback(probability: Double?, isWinner: Bool?, resolutionSource: String?) -> Certainty {
        guard resolutionSource != OutcomeVerdict.retractedResolutionSource,
              OutcomeVerdict.isAuthoritative(resolutionSource),
              let probability, probability.isFinite else { return .unknown }
        if probability == 1, isWinner == true { return .won }
        if probability == 0, isWinner == false { return .lost }
        return .unknown
    }

    /// Whole-board certainty for the hero: `.all` when every row's result is
    /// unknown, `.some` when at least one is, nil otherwise. A field whose every
    /// row definitely lost is NOT unknown — an independent field can settle
    /// with no affirmative winner.
    enum Board: Equatable, Sendable {
        case all
        case some
    }

    static func board(_ market: FuturesMarketDetail) -> Board? {
        guard !market.outcomes.isEmpty else { return nil }
        let unknown = market.outcomes.filter {
            certainty($0, marketSource: market.source, marketStatus: market.status) == .unknown
        }.count
        if unknown == 0 { return nil }
        return unknown == market.outcomes.count ? .all : .some
    }

    /// Is this row's result unknown on this market?
    static func isUnknown(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Bool {
        certainty(outcome, marketSource: market.source, marketStatus: market.status) == .unknown
    }

    /// May the hero crown this outcome with a Winner badge? An unknown row
    /// never is, whatever its `is_winner` says (a midrange `true` is not a
    /// champion). Untargeted markets keep `is_winner == true`.
    static func heroWearsWinnerBadge(_ outcome: FuturesOutcome, in market: FuturesMarketDetail) -> Bool {
        switch certainty(outcome, marketSource: market.source, marketStatus: market.status) {
        case .won: return true
        case .lost, .unknown: return false
        case nil: return outcome.isWinner == true
        }
    }
}

/// `settlement_display` on one `/api/futures/{id}` outcome. Both fields are
/// read leniently: a missing or non-string value decodes to nil and is read as
/// unknown, so an unexpected shape can never fail the response or invent a
/// result.
nonisolated struct SettlementDisplay698: Decodable, Equatable, Sendable {
    let verdict: String?
    let basis: String?

    init(verdict: String?, basis: String?) {
        self.verdict = verdict
        self.basis = basis
    }

    private enum CodingKeys: String, CodingKey {
        case verdict, basis
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        verdict = try? container.decodeIfPresent(String.self, forKey: .verdict)
        basis = try? container.decodeIfPresent(String.self, forKey: .basis)
    }
}
