import Foundation

/// The closed rows one half card may draw, and the score it grades them by.
///
/// #10850, the iPhone twin of web `closedHalfRows`. At halftime the server
/// stops quoting a finished half (#1588), so the 1st half cards vanished just
/// as the half had a result. Those rows now come back under
/// `closed_period_markets`, unpriced, beside the score the server evidenced.
/// The card grades every line against that score and draws no forecast.
///
/// Read strictly, and refusing rather than guessing:
/// - a half still quoting this card's type in `period_markets` keeps its
///   quoting card — a row is never in both lists, and if it were, quoting wins;
/// - the score is ONE per half, checked across every closed half row before
///   the card's own type is picked out, so a margin card and a points card can
///   never grade from two different "finals" of the same half;
/// - every row of the card says its window closed and carries no price;
/// - a total line is the row's own finite `threshold` — never a parsed title,
///   never a default — so a missing line withholds the card rather than
///   becoming an invented "Over 0". Spread lines live in their titles and are
///   not held to this.
nonisolated enum ClosedHalfMarkets {
    enum Kind: String {
        case spread = "half_spread"
        case total = "half_total"
    }

    struct Binding: Equatable {
        let rows: [GameMarketOutcome]
        let score: HalfScoreSplit
    }

    /// The closed half rows the server serves, all sharing one score.
    static let halfTypes: Set<String> = ["half_spread", "half_total", "half_winner"]

    static func binding(
        closed: [ClosedPeriodOutcome]?,
        quoting: [GameMarketOutcome]?,
        kind: Kind,
        half: String,
        periodOf: (GameMarketOutcome) -> String?
    ) -> Binding? {
        if (quoting ?? []).contains(where: { $0.marketType == kind.rawValue && periodOf($0) == half }) {
            return nil
        }
        let halfRows = (closed ?? []).filter {
            halfTypes.contains($0.row.marketType ?? "") && $0.row.period == half
        }
        var score: HalfScoreSplit?
        for r in halfRows {
            guard let s = r.periodScore, s.home >= 0, s.away >= 0 else { return nil }
            if let score, score.home != s.home || score.away != s.away { return nil }
            score = HalfScoreSplit(home: s.home, away: s.away)
        }
        let rows = halfRows.filter { $0.row.marketType == kind.rawValue }
        guard let score, !rows.isEmpty else { return nil }
        for r in rows {
            guard r.windowClosed == true, r.row.probability == nil, r.row.overProbability == nil else { return nil }
            if kind == .total {
                guard let line = r.row.threshold, line.isFinite else { return nil }
            }
        }
        return Binding(rows: rows.map(\.row), score: score)
    }
}
