import Foundation

/// #10374 — which rows a distribution card draws, in what order, and which one
/// is the leader.
///
/// Alex, rage shake 170: "These date oriented cards should be shown in
/// chronological order because showing them out of chronological order is
/// confusing, even if that is the true descending order of the probabilities."
/// The `Next Claude Haiku (4.6+) released on...?` card read October 27 ·
/// October 12 · October 28 · October 13.
///
/// THE CARD STILL DRAWS THE SAME FOUR ROWS. Which rows survive is the served
/// (probability, leader-first) cut, exactly as before; a chronological board only
/// changes the order they are LISTED in. So the leader can never fall off the
/// card for being late in the month.
///
/// THE LEADER IS A PROBABILITY, NOT A POSITION. Row 0 was the leader only because
/// the list was probability-ordered. Once the rows are listed by date, the bold
/// label and green bar go on the highest-probability drawn row (a tie goes to the
/// row the server served first, which is its leader).
///
/// THE ORDER IS THE SERVER'S CALL. Whether a board is a date board, and which
/// year a bare `October 27` belongs to, is decided in `discover_card`
/// (`distribution_order`, `distribution_outcomes[].date`). This never parses a
/// label: an absent field — an older cached body, every non-date board — lists
/// rows exactly as served.
nonisolated enum DistributionBoardOrder {
    static let drawnRowLimit = 4

    struct ListedRow {
        let outcome: FeedDiscoverDistributionOutcome
        let isLeader: Bool
    }

    static func isChronological(_ order: String?) -> Bool {
        order == "chronological"
    }

    /// The rows to draw, in drawing order. `outcomes` is the served list (already
    /// filtered to priced rows); `order` is `discover_card.distribution_order`.
    static func listedRows(
        _ outcomes: [FeedDiscoverDistributionOutcome],
        order: String?
    ) -> [ListedRow] {
        let drawn = Array(outcomes.prefix(drawnRowLimit))
        guard !drawn.isEmpty else { return [] }

        // Highest probability among the DRAWN rows; strict `>` keeps the earliest
        // served row on a tie (Oct 27 and Oct 12 both 14% → the served leader).
        var leaderIndex = 0
        for (index, row) in drawn.enumerated()
        where (row.probability ?? 0) > (drawn[leaderIndex].probability ?? 0) {
            leaderIndex = index
        }

        var indexed = Array(drawn.enumerated())
        if isChronological(order), drawn.contains(where: { $0.date != nil }) {
            // ISO `yyyy-MM-dd` sorts as text. A row with no date (the "No release
            // by…" residual) goes last; ties and undated rows keep served order.
            indexed.sort { lhs, rhs in
                switch (lhs.element.date, rhs.element.date) {
                case let (l?, r?): return l == r ? lhs.offset < rhs.offset : l < r
                case (.some, .none): return true
                case (.none, .some): return false
                case (.none, .none): return lhs.offset < rhs.offset
                }
            }
        }
        return indexed.map { ListedRow(outcome: $0.element, isLeader: $0.offset == leaderIndex) }
    }
}
