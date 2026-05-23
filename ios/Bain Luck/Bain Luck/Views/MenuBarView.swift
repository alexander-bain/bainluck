#if os(macOS)
import SwiftUI

struct MenuBarView: View {
    @State private var liveGames: [MenuBarGame] = []
    @State private var loading = true

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if loading && liveGames.isEmpty {
                ProgressView()
                    .frame(width: 260, height: 60)
            } else if liveGames.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "sportscourt")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No live games from your teams")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(width: 260, height: 60)
            } else {
                ForEach(liveGames) { game in
                    menuBarGameRow(game)
                    if game.id != liveGames.last?.id {
                        Divider()
                    }
                }
            }

            Divider()
            Button {
                if let url = URL(string: "bainluck://events") {
                    NSWorkspace.shared.open(url)
                }
            } label: {
                HStack {
                    Text("Open Bain Luck")
                        .font(.caption)
                    Spacer()
                    Text("⌘1")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
        }
        .padding(.vertical, 4)
        .task {
            await loadLiveGames()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                await loadLiveGames()
            }
        }
    }

    private func menuBarGameRow(_ game: MenuBarGame) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(game.sport)
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                Spacer()
                if let period = game.period {
                    Text(period)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.green)
                }
            }

            HStack {
                Text(game.awayAbbrev)
                    .font(.system(size: 12, weight: .bold))
                    .frame(width: 36, alignment: .leading)
                Text("\(game.awayScore ?? 0)")
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .frame(width: 24, alignment: .trailing)

                Text("–")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)

                Text("\(game.homeScore ?? 0)")
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .frame(width: 24, alignment: .leading)
                Text(game.homeAbbrev)
                    .font(.system(size: 12, weight: .bold))
                    .frame(width: 36, alignment: .trailing)

                Spacer()

                Text("\(game.awayProb)–\(game.homeProb)")
                    .font(.system(size: 10, weight: .medium).monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .onTapGesture {
            if let url = URL(string: "bainluck://events/\(game.id)") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    private func loadLiveGames() async {
        do {
            let feed = try await APIClient.shared.fetchFeed(limit: 10, myTeamsOnly: true, includeFutures: false)
            liveGames = feed.items.compactMap { item -> MenuBarGame? in
                guard let event = item.event, event.status == "live",
                      let homeProbability = event.currentOdds?.homeProbability else { return nil }
                let awayProbability = 1.0 - homeProbability
                return MenuBarGame(
                    id: event.id,
                    homeAbbrev: event.homeTeamData?.abbreviation ?? String(event.homeTeam.split(separator: " ").last ?? ""),
                    awayAbbrev: event.awayTeamData?.abbreviation ?? String(event.awayTeam.split(separator: " ").last ?? ""),
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    homeProb: Int((homeProbability * 100).rounded()),
                    awayProb: Int((awayProbability * 100).rounded()),
                    period: [event.espn?.period, event.espn?.gameClock].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " "),
                    sport: event.sportName ?? event.sport ?? ""
                )
            }
        } catch {}
        loading = false
    }
}

private struct MenuBarGame: Identifiable {
    let id: Int
    let homeAbbrev: String
    let awayAbbrev: String
    let homeScore: Int?
    let awayScore: Int?
    let homeProb: Int
    let awayProb: Int
    let period: String?
    let sport: String
}
#endif
