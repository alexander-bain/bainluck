import Foundation

/// What one team-page "Season Futures" row may say, from one place.
///
/// #9091 — seen on the Red Sox page (2026-09-27): the row printed only
/// `market_name`, so "Gold Glove: AL Center Field 98%" read as the TEAM's chance
/// when it is Ceddanne Rafaela's (17 of the 30 rows served for Boston name a
/// player or another subject). And "MLB: Team to make postseason 100% #1 of 30"
/// was served `is_winner: true` — a settled result drawn as a live price with a
/// rank, because the model never decoded `is_winner`.
///
/// This is the Swift half of `frontend/components/TeamFutureRow.tsx`, whose
/// three rules it mirrors: the OUTCOME is the headline and the market is the
/// caption; a graded winner is a result (`✓ Won`, no rank); and the live number
/// goes through the app's boundary formatter, never a bare round (#7710 — a
/// priced 0.004 must not print `0%`). `TeamFutureRowWebParity9091Tests` reads
/// the web file so the two cannot drift apart silently.
enum TeamFutureRowPresentation {

    struct Row: Equatable {
        /// The subject the price is about — a player, a team, a city.
        let title: String
        /// The question, e.g. "Gold Glove: AL Center Field".
        let caption: String
        /// A graded winner. Settled means settled: drawn as a result.
        let settledWon: Bool
        /// Nil when the row has no probability; the row then prints no number.
        let percent: String?
        /// "#1 of 9". Nil for a settled row — a rank is a claim about a race
        /// still being run — and nil when either half is missing.
        let rankLine: String?
    }

    /// The badge a settled row wears. Web's `✓ Won`, verbatim.
    static let wonBadge = "✓ Won"

    static func row(_ item: TeamFutureItem) -> Row {
        let settledWon = item.isWinner == true

        let percent: String?
        if let p = item.probability {
            // A graded winner prints its served value as the result it is;
            // `formatProbability` would hedge an exact 1.0 to `>99%`.
            percent = settledWon ? "\(percentNumber(p * 100))%" : formatProbability(p)
        } else {
            percent = nil
        }

        var rankLine: String?
        if !settledWon, let rank = item.rank, let total = item.totalOutcomes {
            rankLine = "#\(rank) of \(total)"
        }

        return Row(
            title: item.outcomeName,
            caption: item.marketName,
            settledWon: settledWon,
            percent: percent,
            rankLine: rankLine
        )
    }
}
