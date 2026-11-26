import SwiftUI

/// #13013 (`246: A` + `256: B`) — Pure ordering and shelf-admission rules for the
/// Sports tab's four-block `"All"` structure:
/// 1. `Live Now`
/// 2. `Upcoming` (games starting within 6 hours first in server-ranked order, then later upcoming games)
/// 3. `Just Happened` (recent finals)
/// 4. One short horizontal `Futures` shelf (`FuturesCardView`, `FeedTournamentData`, and `playoff_progression` ladders),
///    never taking Seat 1 on a game night and leading `"All"` only on a quiet day with no live games
///    and nothing starting within 6 hours.
enum SportsFuturesShelf13013 {
    nonisolated static let maxCompactShelfCards = 8
    nonisolated static let imminentWindowSeconds: TimeInterval = 6 * 3600

    nonisolated enum ShelfCard: Identifiable {
        case futures(FeedItem, FeedFuturesData)
        case tournament(FeedItem, FeedTournamentData)
        case playoffLadder(GroupedFeedItem)

        var id: String {
            switch self {
            case .futures(_, let f): return "futures:\(f.id)"
            case .tournament(_, let t): return "tournament:\(t.key)"
            case .playoffLadder(let g): return "ladder:\(g.id)"
            }
        }

        var feedItem: FeedItem? {
            switch self {
            case .futures(let item, _), .tournament(let item, _):
                return item
            case .playoffLadder:
                return nil
            }
        }
    }

    nonisolated static func partitionUpcoming(
        _ upcoming: [FeedItem],
        now: Date
    ) -> (withinSixHours: [FeedItem], later: [FeedItem]) {
        var withinSixHours: [FeedItem] = []
        var later: [FeedItem] = []
        for item in upcoming {
            if let start = item.event?.commenceTime?.asDate,
               start.timeIntervalSince(now) <= imminentWindowSeconds {
                withinSixHours.append(item)
            } else {
                later.append(item)
            }
        }
        return (withinSixHours, later)
    }

    nonisolated static func orderedUpcoming(_ upcoming: [FeedItem], now: Date) -> [FeedItem] {
        let parts = partitionUpcoming(upcoming, now: now)
        return parts.withinSixHours + parts.later
    }

    /// `256: B` — Futures lead `"All"` ONLY on a quiet day with no live games and
    /// nothing starting within 6 hours; on any game night they sit in Block 4 at the end.
    nonisolated static func shelfLeads(
        live: [FeedItem],
        upcoming: [FeedItem],
        now: Date
    ) -> Bool {
        guard live.isEmpty else { return false }
        return partitionUpcoming(upcoming, now: now).withinSixHours.isEmpty
    }

    nonisolated static func shelfCards(
        from items: [FeedItem],
        groupedItems: [GroupedFeedItem],
        for categoryID: String,
        limit: Int? = maxCompactShelfCards
    ) -> [ShelfCard] {
        let selectedCategory = sportCategories.first { $0.id == categoryID }
        var seen = Set<String>()
        var result: [ShelfCard] = []

        for item in items {
            if item.type == "futures", let futures = item.futures {
                if categoryID != "all", let cat = selectedCategory, !cat.matches(item) {
                    continue
                }
                let card = ShelfCard.futures(item, futures)
                if seen.insert(card.id).inserted {
                    result.append(card)
                }
            } else if item.type == "tournament", let tournament = item.tournament {
                if categoryID != "all" && categoryID != "golf" {
                    continue
                }
                let card = ShelfCard.tournament(item, tournament)
                if seen.insert(card.id).inserted {
                    result.append(card)
                }
            }
        }

        for group in groupedItems where group.type == "playoff_progression" && group.entityName != nil && group.stages != nil {
            if categoryID != "all", let cat = selectedCategory {
                let key = (group.sportKey ?? "").lowercased()
                let matchesPrefix = cat.sportPrefixes.contains { key.hasPrefix($0) }
                let matchesCategory = cat.futuresCategories.contains(key)
                if !matchesPrefix && !matchesCategory {
                    continue
                }
            }
            let card = ShelfCard.playoffLadder(group)
            if seen.insert(card.id).inserted {
                result.append(card)
            }
        }

        if let limit {
            return Array(result.prefix(limit))
        }
        return result
    }
}

/// Compact tournament card formatted to match `FuturesCardView` height on the
/// Sports tab's horizontal `Futures` shelf (`#13013`).
struct SportsShelfTournamentCardView13013: View {
    let tournament: FeedTournamentData

    private var badge: String {
        if tournament.isMajor == true { return "Major" }
        if let raw = tournament.tourLabel ?? tournament.tour, !raw.isEmpty {
            return golfTourDisplayName(for: raw)
        }
        return "Golf"
    }

    private var isSettled: Bool {
        tournament.marqueeWhathit == true
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(badge)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if !isSettled, (tournament.scheduleStatus ?? "").lowercased() == "live" {
                    Text("LIVE")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.red)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.red.opacity(0.12))
                        .clipShape(Capsule())
                }
                Spacer()
                if let count = tournament.sourceCount, count > 1 {
                    Text("\(count) sources")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            Text(tournament.name)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            if let golfers = tournament.golfers, !golfers.isEmpty {
                VStack(spacing: 4) {
                    ForEach(Array(golfers.prefix(3))) { golfer in
                        HStack(spacing: 8) {
                            Text("#\(golfer.rank)")
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(.tertiary)
                                .frame(width: 20, alignment: .trailing)
                            Text(golfer.name)
                                .font(.caption)
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                            Spacer()
                            if isSettled && golfer.rank == 1 {
                                Text("Won")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(HeadlineStyleTable199.winnerTickInk)
                            } else {
                                Text(formatProbability(golfer.probability, renderedPercent: golfer.renderedPercent))
                                    .font(.caption.weight(.semibold).monospacedDigit())
                                    .foregroundStyle(.primary)
                            }
                        }
                    }
                }
            }
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }
}
