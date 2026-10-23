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
        /// A graded winner, or a club the grid says has won the question
        /// (#11493). Settled means settled: drawn as a result.
        let settledWon: Bool
        /// #11493 — the grid says the club is out of this question. Drawn as
        /// ``outBadge`` with no number and no rank, never as `<1%`.
        var out: Bool = false
        /// Nil when the row has no probability; the row then prints no number.
        let percent: String?
        /// "#1 of 9". Nil for a settled row — a rank is a claim about a race
        /// still being run — and nil when either half is missing.
        let rankLine: String?
    }

    /// The badge a settled row wears. Web's `✓ Won`, verbatim.
    static let wonBadge = "✓ Won"

    /// #11493 — the badge an eliminated row wears, in place of its number.
    static let outBadge = "Out"

    static func row(_ item: TeamFutureItem) -> Row {
        let graded = item.isWinner == true
        let verdict = graded ? nil : item.gridVerdict
        let settledWon = graded || verdict == .won
        let out = verdict == .eliminated

        let percent: String?
        if verdict != nil {
            // #11493 — the price under a grid verdict is the venue's residual
            // quote (0.001 for a club already out), not a chance. The grid draws
            // ✓/✕ with no number; so does this row.
            percent = nil
        } else if let p = item.probability {
            // A graded winner prints its served value as the result it is;
            // `formatProbability` would hedge an exact 1.0 to `>99%`.
            percent = settledWon ? "\(percentNumber(p * 100))%" : formatProbability(p)
        } else {
            percent = nil
        }

        var rankLine: String?
        if !settledWon, !out, let rank = item.rank, let total = item.totalOutcomes {
            rankLine = "#\(rank) of \(total)"
        }

        return Row(
            title: item.outcomeName,
            caption: item.marketName,
            settledWon: settledWon,
            out: out,
            percent: percent,
            rankLine: rankLine
        )
    }
}

/// What one team-page "Championship Path" step prints in place of its number.
///
/// #11493 — the step stays on the page when the grid says the club is out: it
/// is the title question answered, and dropping it would let the Season Futures
/// list below draw the same market's 0.001 again (``TeamDivisionRace/
/// seasonFutures(_:championshipPath:race:sportKey:)`` hides a futures row only
/// behind a path step that answers it).
enum ChampionshipPathPresentation {

    enum Value: Equatable {
        /// The grid says the club is out — ``TeamFutureRowPresentation/outBadge``.
        case out
        /// The grid says the club won — ``TeamFutureRowPresentation/wonBadge``.
        case won
        /// A live number.
        case percent(String)
        /// Nothing to print.
        case none
    }

    static func value(_ entry: ChampionshipPathEntry) -> Value {
        switch entry.gridVerdict {
        case .eliminated: return .out
        case .won: return .won
        case nil:
            guard let p = entry.probability else { return .none }
            return .percent("\(Int(round(p * 100)))%")
        }
    }
}
