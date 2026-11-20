import SwiftUI

struct RelatedByTagView: View {
    private let tags: [String]
    private let excludeEventId: Int?
    private let title: String
    private let limit: Int

    @State private var items: [FeedItem] = []
    @State private var loaded = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(tags: [String], excludeEventId: Int? = nil, title: String = "More Like This", limit: Int = 4) {
        self.tags = tags
        self.excludeEventId = excludeEventId
        self.title = title
        self.limit = limit
    }

    init(preloadedItems: [FeedItem], excludeEventId: Int? = nil, title: String = "More Like This", limit: Int = 4) {
        self.tags = []
        self.excludeEventId = excludeEventId
        self.title = title
        self.limit = limit
        self._items = State(initialValue: preloadedItems)
        self._loaded = State(initialValue: true)
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
        let trailing = Self.trailingSummary(for: data)
        return Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    matchupBlock(data)
                    if let trailing {
                        Text(trailing)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    matchupBlock(data)
                    Spacer(minLength: 4)
                    if let trailing {
                        Text(trailing)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.secondary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func matchupBlock(_ data: FeedEventData) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if data.status == "live" {
                    Circle()
                        .fill(.red)
                        .frame(width: 5, height: 5)
                }
                Text("\(data.awayTeam) @ \(data.homeTeam)")
                    .font(.caption)
                    .fontWeight(.medium)
                    .multilineTextAlignment(.leading)
                    .lineLimit(nil)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if data.status == "live",
               data.scoreSourceUnavailable != true,
               let homeScore = data.homeScore,
               let awayScore = data.awayScore {
                Text("\(awayScore) - \(homeScore)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
        }
    }

    static func isFinishedEvent(_ data: FeedEventData) -> Bool {
        EventState.isFinished(data.status) || data.heroProbabilitySource == "settled"
    }

    static func trailingSummary(for data: FeedEventData) -> String? {
        if isFinishedEvent(data) {
            if data.scoreSourceUnavailable != true,
               let awayScore = data.awayScore,
               let homeScore = data.homeScore {
                return "Final · \(awayScore)–\(homeScore)"
            }
            return "Final"
        }
        // #5363 — on a draw-priced sport the away half is `1 − P(home)`,
        // i.e. *away win or draw*, and it is withheld. The SLOT survives as
        // the app's absent marker ("— / 55%") rather than collapsing to a
        // lone number: this pair sits on the same line as the "<away> @
        // <home>" title that attributes it, so keeping the position keeps
        // the attribution, and the dash says the true thing — we hold no
        // price for that side.
        if admitsTrailingProbability(data),
           let odds = data.currentOdds,
           let printable = DrawPricedWinner.printablePair(
               away: odds.awayProbability,
               home: odds.homeProbability,
               sport: data.sport) {
                let homeProbability = printable.home
                let duel = duelPercents(
                    away: printable.away ?? (1 - homeProbability),
                    home: homeProbability,
                    servedAway: odds.awayRenderedPercent,
                    servedHome: odds.homeRenderedPercent
                )
                let awayPct = duel[0]
                let homePct = duel[1]
                return "\(formatProbabilityOrDash(printable.away, renderedPercent: awayPct)) / \(formatProbability(homeProbability, renderedPercent: homePct))"
        }
        return nil
    }

    static func admitsTrailingProbability(_ data: FeedEventData) -> Bool {
        !isFinishedEvent(data)
            && data.heroProbabilitySource != OpeningLineHero.openingSource
    }
}
