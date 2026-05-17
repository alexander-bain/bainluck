import Combine
import SwiftUI
import WatchKit

struct WatchLiveView: View {
    @StateObject private var vm = WatchLiveViewModel()

    var body: some View {
        ScrollView {
            if vm.loading && vm.games.isEmpty {
                ProgressView()
                    .padding(.top, 20)
            } else if let error = vm.error, vm.games.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.title3)
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load(force: true) } }
                        .font(.caption2)
                }
                .padding(.top, 20)
            } else if vm.games.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "sportscourt")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No live games")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)
            } else {
                LazyVStack(spacing: 8) {
                    ForEach(vm.games) { game in
                        liveGameCard(game)
                    }
                    if let ago = vm.lastUpdated {
                        Text(ago)
                            .font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 4)
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
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                Spacer()
                if let clock = game.gameClock {
                    Text(clock)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.green)
                }
            }

            HStack(spacing: 0) {
                VStack(spacing: 2) {
                    Text(game.awayAbbrev)
                        .font(.system(size: 12, weight: .bold))
                    if let score = game.awayScore {
                        Text("\(score)")
                            .font(.system(size: 16, weight: .heavy, design: .rounded))
                    }
                    Text("\(game.awayProb)%")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Color(hex: game.awayColor ?? "#888"))
                }
                .frame(maxWidth: .infinity)

                Text("vs")
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)

                VStack(spacing: 2) {
                    Text(game.homeAbbrev)
                        .font(.system(size: 12, weight: .bold))
                    if let score = game.homeScore {
                        Text("\(score)")
                            .font(.system(size: 16, weight: .heavy, design: .rounded))
                    }
                    Text("\(game.homeProb)%")
                        .font(.system(size: 10, weight: .semibold))
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

struct WatchLiveGame: Identifiable {
    let id: Int
    let homeAbbrev: String
    let awayAbbrev: String
    let homeProb: Int
    let awayProb: Int
    let homeScore: Int?
    let awayScore: Int?
    let homeColor: String?
    let awayColor: String?
    let gameClock: String?
    let sportLabel: String
}

@MainActor
final class WatchLiveViewModel: ObservableObject {
    @Published var games: [WatchLiveGame] = []
    @Published var loading = true
    @Published var error: String?
    @Published var lastUpdated: String?

    func load(force: Bool = false) async {
        if games.isEmpty { loading = true }
        error = nil
        defer { loading = false }

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 8, forceRefresh: force)
            let newGames = feed.items.compactMap { item -> WatchLiveGame? in
                guard let e = item.event, e.status == "live",
                      let homeProb = e.currentOdds?.homeProbability else { return nil }
                let homeTeam = e.homeTeam ?? "Home"
                let awayTeam = e.awayTeam ?? "Away"
                let awayProb = 1.0 - homeProb
                let homeAbbrev = e.homeTeamData?.abbreviation ?? String(homeTeam.split(separator: " ").last ?? "")
                let awayAbbrev = e.awayTeamData?.abbreviation ?? String(awayTeam.split(separator: " ").last ?? "")
                let clockParts = [e.espn?.period, e.espn?.gameClock].compactMap { $0 }.filter { !$0.isEmpty }
                return WatchLiveGame(
                    id: e.id,
                    homeAbbrev: homeAbbrev,
                    awayAbbrev: awayAbbrev,
                    homeProb: Int((homeProb * 100).rounded()),
                    awayProb: Int((awayProb * 100).rounded()),
                    homeScore: e.homeScore,
                    awayScore: e.awayScore,
                    homeColor: e.homeTeamData?.primaryColor,
                    awayColor: e.awayTeamData?.primaryColor,
                    gameClock: clockParts.isEmpty ? nil : clockParts.joined(separator: " "),
                    sportLabel: e.sportName ?? e.sport ?? ""
                )
            }
            if !newGames.isEmpty || games.isEmpty {
                games = newGames
            }
            if let t = await WatchAPIClient.shared.lastFetchTime {
                let ago = Int(Date().timeIntervalSince(t))
                lastUpdated = ago < 5 ? "Just now" : "\(ago)s ago"
            }
            WKInterfaceDevice.current().play(.click)
        } catch {
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
