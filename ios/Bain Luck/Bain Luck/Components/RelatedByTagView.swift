import SwiftUI

struct RelatedByTagView: View {
    private let tags: [String]
    private let excludeEventId: Int?
    private let title: String
    private let limit: Int

    @State private var items: [FeedItem] = []
    @State private var loaded = false

    init(tags: [String], excludeEventId: Int? = nil, title: String = "More Like This", limit: Int = 4) {
        self.tags = tags
        self.excludeEventId = excludeEventId
        self.title = title
        self.limit = limit
    }

    var body: some View {
        Group {
            if !filteredItems.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)

                    ForEach(filteredItems) { item in
                        if item.type == "event", let data = item.event {
                            NavigationLink(value: Route.eventDetail(id: data.id)) {
                                eventRow(data)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding()
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
        .task {
            guard !loaded, !tags.isEmpty else { return }
            do {
                let response = try await APIClient.shared.fetchFeed(limit: limit + 5, tags: tags)
                items = response.items
            } catch { }
            loaded = true
        }
    }

    private var filteredItems: [FeedItem] {
        items
            .filter { item in
                guard let eid = excludeEventId else { return true }
                if item.type == "event", let data = item.event {
                    return data.id != eid
                }
                return true
            }
            .prefix(limit)
            .map { $0 }
    }

    private func eventRow(_ data: FeedEventData) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    if data.status == "live" {
                        Circle()
                            .fill(.red)
                            .frame(width: 5, height: 5)
                    }
                    Text("\(data.awayTeam) @ \(data.homeTeam)")
                        .font(.caption)
                        .fontWeight(.medium)
                        .lineLimit(1)
                }
                if data.status == "live", let homeScore = data.homeScore, let awayScore = data.awayScore {
                    Text("\(awayScore) - \(homeScore)")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let odds = data.currentOdds,
               let homeProbability = odds.homeProbability,
               let awayProbability = odds.awayProbability {
                // UX-P114 — this row prints BOTH sides of one question separated by
                // a slash, so it is the same 101 as the Discover card's strip.
                let duelFallback = renderedDuelPercents(
                    away: awayProbability, home: homeProbability
                )
                let awayPct = odds.awayRenderedPercent ?? duelFallback[0]
                let homePct = odds.homeRenderedPercent ?? duelFallback[1]
                Text("\(formatProbability(awayProbability, renderedPercent: awayPct)) / \(formatProbability(homeProbability, renderedPercent: homePct))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.secondary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
