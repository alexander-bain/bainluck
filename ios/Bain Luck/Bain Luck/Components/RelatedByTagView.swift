import SwiftUI

struct RelatedByTagView: View {
    let tags: [String]
    let excludeEventId: Int?
    let title: String
    let limit: Int

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
                if data.status == "live", let hs = data.homeScore, let as_ = data.awayScore {
                    Text("\(as_) - \(hs)")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let odds = data.currentOdds, let hp = odds.homeProbability, let ap = odds.awayProbability {
                Text("\(formatProbability(ap)) / \(formatProbability(hp))")
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
