import Foundation

/// The opening a Market Details row may print as "from N%".
///
/// #8313. `bainluck://futures/13795456` "Iran leadership change by December 31?"
/// (Polymarket), served 2026-10-17 15:45Z:
///
///     No   probability 0.885   opening_probability 0.31   opening_american_odds -223
///     Yes  probability 0.115   opening_probability 0.31   opening_american_odds +223
///
/// −223 is 0.6905: No's own opening odds sit on the COMPLEMENT of its opening
/// probability, so 0.31 is Yes's price stored on No (the pre-#137 decomposed
/// Polymarket writer). The row printed "No … from 31%". Yes's 0.31 agrees with its
/// own +223 and keeps its caption.
///
/// Web's rule, mirrored with the same numbers (`openingIsTheOtherSidesPrice` +
/// `readableOpeningProbability` in `frontend/lib/futuresDetailDisplay.ts`, PRs
/// #11173/#11178): withhold only the complement signature — the odds say
/// 1 − opening and not the opening. A plain mismatch is not read (several writers
/// stamp honest openings beside stale odds). Within 1 pt of 50% the two readings
/// overlap and nothing is withheld. Absent, non-finite or impossible odds
/// (|odds| < 100) and an opening outside (0, 1) keep today's behaviour.
///
/// Withheld means the same as a missing opening: nothing printed. Nothing is
/// substituted (not the converted odds, not 1 − opening). Per leg, never paired.
/// The served value stays wrong; the write/serve repair is #8313's own scope.
nonisolated enum FuturesReadableOpening8313 {
    /// Integer odds move an implied probability by at most 50/(|odds|+100)²,
    /// 0.00125 at ±100. Web measured the largest honest gap at 0.00055.
    static let roundingTolerance = 0.005

    static func of(_ outcome: FuturesOutcome) -> Double? {
        of(opening: outcome.openingProbability, openingAmericanOdds: outcome.openingAmericanOdds)
    }

    static func of(opening: Double?, openingAmericanOdds: Int?) -> Double? {
        isTheOtherSidesPrice(opening: opening, openingAmericanOdds: openingAmericanOdds) ? nil : opening
    }

    static func isTheOtherSidesPrice(opening: Double?, openingAmericanOdds: Int?) -> Bool {
        guard let open = opening, let odds = openingAmericanOdds else { return false }
        guard open.isFinite, open > 0, open < 1 else { return false }
        guard abs(odds) >= 100 else { return false }
        // `utils/odds_math.american_to_probability`, mirrored (D1: the app never
        // shows odds, so it has no odds helper).
        let o = Double(odds)
        let implied = o > 0 ? 100 / (o + 100) : -o / (-o + 100)
        return abs(1 - 2 * open) > 2 * roundingTolerance
            && abs(implied - open) > roundingTolerance
            && abs(implied - (1 - open)) <= roundingTolerance
    }
}
