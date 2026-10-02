import Combine
import SwiftUI
import WatchKit

struct WatchLiveView: View {
    @StateObject private var vm = WatchLiveViewModel()

    var body: some View {
        ScrollView {
            if vm.loading && vm.games.isEmpty {
                VStack(spacing: 10) {
                    ProgressView()
                        .scaleEffect(1.3)
                    Text("Loading...")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)
            } else if let error = vm.error, vm.games.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.title3)
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load(force: true) } }
                        .font(.system(size: 13, weight: .semibold))
                }
                .padding(.top, 20)
            } else if vm.games.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "sportscourt")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No live games")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)
            } else {
                LazyVStack(spacing: 8) {
                    ForEach(vm.games) { game in
                        liveGameCard(game)
                    }
                    // #1739 — re-read every second from the shown data's fetch
                    // time, so the line counts up and names a failed refresh.
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        if let line = vm.list.refresh.ageLine(now: context.date) {
                            Text(line)
                                .font(.system(size: 9))
                                .foregroundStyle(.tertiary)
                                .frame(maxWidth: .infinity)
                                .padding(.top, 4)
                        }
                    }
                }
                .padding(.horizontal, 4)
            }
        }
        .navigationTitle("Live")
        .task { await vm.load() }
        .task(id: "auto-refresh") {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                await vm.load()
            }
        }
    }

    private func liveGameCard(_ game: WatchLiveGame) -> some View {
        VStack(spacing: 4) {
            HStack {
                Text(game.sportLabel)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                Spacer()
                if let clock = game.gameClock {
                    Text(clock)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.green)
                }
            }

            HStack(spacing: 0) {
                VStack(spacing: 2) {
                    Text(game.awayAbbrev)
                        .font(.system(size: 15, weight: .bold))
                        .minimumScaleFactor(0.7)
                        .lineLimit(1)
                    if let score = game.awayScore {
                        Text("\(score)")
                            .font(.system(size: 24, weight: .heavy, design: .rounded))
                    }
                    Text("\(game.awayProb)%")
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .foregroundStyle(Color(hex: game.awayColor ?? "#888"))
                }
                .frame(maxWidth: .infinity)

                Text("vs")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)

                VStack(spacing: 2) {
                    Text(game.homeAbbrev)
                        .font(.system(size: 15, weight: .bold))
                        .minimumScaleFactor(0.7)
                        .lineLimit(1)
                    if let score = game.homeScore {
                        Text("\(score)")
                            .font(.system(size: 24, weight: .heavy, design: .rounded))
                    }
                    Text("\(game.homeProb)%")
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .foregroundStyle(Color(hex: game.homeColor ?? "#888"))
                }
                .frame(maxWidth: .infinity)
            }

            GeometryReader { geo in
                HStack(spacing: 1) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.awayColor ?? "#888"))
                        .frame(width: geo.size.width * CGFloat(game.awayProb) / 100)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.homeColor ?? "#888"))
                }
            }
            .frame(height: 4)
        }
        .padding(8)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// `WatchLiveGame` and the refresh rule live in `WatchRefreshState.swift` (#1739).

@MainActor
final class WatchLiveViewModel: ObservableObject {
    @Published private(set) var list = WatchLiveList()
    @Published var loading = true
    @Published var error: String?

    var games: [WatchLiveGame] { list.games }

    func load(force: Bool = false) async {
        if games.isEmpty { loading = true }
        error = nil
        defer { loading = false }

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 8, forceRefresh: force)
            let fetchedAt = await WatchAPIClient.shared.lastFetchTime ?? Date()
            // #1739 — replaces the list, with nothing when nothing is live.
            list.apply(feed.items, fetchedAt: fetchedAt)
            WKInterfaceDevice.current().play(.click)
        } catch {
            list.applyFailure()
            if games.isEmpty {
                self.error = "Couldn't load"
            }
        }
    }
}

extension Color {
    init(hex: String) {
        let h = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var rgb: UInt64 = 0
        Scanner(string: h).scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
