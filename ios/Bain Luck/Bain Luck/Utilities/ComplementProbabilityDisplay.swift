import Foundation

/// Display-only reconstruction for a known two-way probability. Computing the
/// complement at the contract's scaled precision avoids `1 - 0.445` falling
/// just below the 55.5% tie. The adopted probability itself never changes.
nonisolated func renderedComplementPercents(home: Double) -> [Int?] {
    renderedDuelPercents(away: (1000 - home * 1000) / 1000, home: home)
}

/// For chart/hero values whose away side may have been locally reconstructed.
/// Independent pairs and withheld away sides retain the ordinary duel contract.
/// A complete server-rendered pair always wins as one decision.
nonisolated func complementDisplayPercents(
    away: Double?, home: Double,
    servedAway: Int? = nil, servedHome: Int? = nil
) -> [Int?] {
    if let servedAway, let servedHome { return [servedAway, servedHome] }
    guard home.isFinite, (0...1).contains(home), let away,
          away == 1 - home else {
        return renderedDuelPercents(away: away, home: home)
    }
    return renderedComplementPercents(home: home)
}
