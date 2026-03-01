import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "relatedFutures")

// MARK: - ViewModel

final class RelatedFuturesViewModel: ObservableObject {
    @Published var relatedFutures: RelatedFuturesResponse?
    @Published var loading = true
    @Published var error: String?

    let eventId: Int

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
        do {
            relatedFutures = try await APIClient.shared.fetchRelatedFutures(eventId: eventId)
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load related futures for event \(self.eventId): \(error)")
        }
    }
}

// MARK: - View

struct RelatedFuturesView: View {
    let eventId: Int
    @StateObject private var vm: RelatedFuturesViewModel
    @State private var expanded = false

    private let collapsedLimit = 4

    init(eventId: Int) {
        self.eventId = eventId
        _vm = StateObject(wrappedValue: RelatedFuturesViewModel(eventId: eventId))
    }

    var body: some View {
        Group {
            if vm.loading {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding()
            } else if let rf = vm.relatedFutures {
                content(rf)
            }
        }
        .task {
            await vm.load()
        }
    }

    // MARK: - Content

    @ViewBuilder
    private func content(_ rf: RelatedFuturesResponse) -> some View {
        let awayFutures = rf.awayTeamFutures ?? []
        let homeFutures = rf.homeTeamFutures ?? []
        let totalCount = awayFutures.count + homeFutures.count

        if totalCount > 0 {
            VStack(alignment: .leading, spacing: 12) {
                Text("Bigger Picture")
                    .font(.subheadline)
                    .fontWeight(.medium)

                if let summary = rf.summary {
                    Text(summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .italic()
                }

                if !awayFutures.isEmpty {
                    teamFuturesSection(
                        teamName: rf.awayTeam,
                        futures: awayFutures
                    )
                }

                if !homeFutures.isEmpty {
                    teamFuturesSection(
                        teamName: rf.homeTeam,
                        futures: homeFutures
                    )
                }

                if totalCount > collapsedLimit {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            expanded.toggle()
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(expanded ? "Show less" : "See all \(totalCount) futures")
                                .font(.caption)
                                .fontWeight(.medium)
                            Image(systemName: expanded ? "chevron.up" : "chevron.down")
                                .font(.system(size: 10))
                        }
                        .foregroundStyle(.blue)
                        .frame(maxWidth: .infinity)
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Team Futures Section

    private func teamFuturesSection(teamName: String, futures: [RelatedFuture]) -> some View {
        let grouped = groupByTier(futures)
        let displayFutures = expanded ? futures : Array(futures.prefix(collapsedLimit))

        return VStack(alignment: .leading, spacing: 8) {
            Text(teamName)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            // Championship/Conference (tier 1-2)
            let championships = grouped.filter { $0.key <= 2 }.flatMap { $0.value }
            if !championships.isEmpty {
                tierHeader(icon: "trophy.fill", title: "Championship Odds")
                ForEach(limitedFutures(championships, from: displayFutures)) { future in
                    championshipRow(future)
                }
            }

            // Awards (tier 3-4)
            let awards = grouped.filter { $0.key == 3 || $0.key == 4 }.flatMap { $0.value }
            if !awards.isEmpty {
                tierHeader(icon: "star.fill", title: "Awards")
                ForEach(limitedFutures(awards, from: displayFutures)) { future in
                    awardRow(future)
                }
            }

            // Other (tier 5+)
            let other = grouped.filter { $0.key >= 5 || $0.key == 0 }.flatMap { $0.value }
            if !other.isEmpty {
                tierHeader(icon: "calendar", title: "Upcoming Games")
                ForEach(limitedFutures(other, from: displayFutures)) { future in
                    compactRow(future)
                }
            }
        }
    }

    // MARK: - Tier Header

    private func tierHeader(icon: String, title: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 10))
            Text(title)
                .font(.caption)
                .fontWeight(.semibold)
        }
        .foregroundStyle(.secondary)
        .padding(.top, 4)
    }

    /// Filters a category's futures to only include those in the display set
    private func limitedFutures(_ categoryFutures: [RelatedFuture], from displayFutures: [RelatedFuture]) -> [RelatedFuture] {
        let displayIds = Set(displayFutures.map(\.id))
        return categoryFutures.filter { displayIds.contains($0.id) }
    }

    private func groupByTier(_ futures: [RelatedFuture]) -> [Int: [RelatedFuture]] {
        Dictionary(grouping: futures) { $0.marketTier ?? 0 }
    }

    // MARK: - Championship Row

    private func championshipRow(_ future: RelatedFuture) -> some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(future.outcomeName)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .lineLimit(1)
                    Text(future.marketName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                changeIndicator(future)

                if let prob = future.probability {
                    Text(formatProbability(prob))
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Award Row

    private func awardRow(_ future: RelatedFuture) -> some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 8) {
                playerHeadshot(future.matchedPlayer)

                VStack(alignment: .leading, spacing: 2) {
                    Text(future.outcomeName)
                        .font(.caption)
                        .fontWeight(.medium)
                        .lineLimit(1)
                    Text(future.marketName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                changeIndicator(future)

                if let prob = future.probability {
                    Text(formatProbability(prob))
                        .font(.caption)
                        .fontWeight(.medium)
                        .monospacedDigit()
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Compact Row

    private func compactRow(_ future: RelatedFuture) -> some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(future.outcomeName)
                        .font(.caption)
                        .lineLimit(1)
                    Text(future.marketName)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }

                Spacer()

                if let prob = future.probability {
                    Text(formatProbability(prob))
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Change Indicator

    @ViewBuilder
    private func changeIndicator(_ future: RelatedFuture) -> some View {
        if let change = future.probabilityChange24h, abs(change) >= 0.005 {
            HStack(spacing: 1) {
                Image(systemName: change > 0 ? "arrow.up" : "arrow.down")
                    .font(.system(size: 8))
                Text(formatProbability(abs(change)))
                    .font(.caption2)
            }
            .foregroundStyle(change > 0 ? .green : .red)
        }
    }

    // MARK: - Player Headshot

    private func playerHeadshot(_ player: MatchedPlayer?) -> some View {
        Group {
            if let headshot = player?.headshot, let url = URL(string: headshot) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    default:
                        initialCircle(player?.name)
                    }
                }
            } else {
                initialCircle(player?.name)
            }
        }
        .frame(width: 28, height: 28)
        .clipShape(Circle())
    }

    private func initialCircle(_ name: String?) -> some View {
        ZStack {
            Circle()
                .fill(Color.blue.opacity(0.2))
            Text(String(name?.prefix(1) ?? "?"))
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundStyle(.blue)
        }
    }
}
