import SwiftUI

/// A deliberately small Watch surface: select one real game and keep it through final.
struct WatchSelectedGameView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var store = WatchSelectedGameStore()
    @State private var availableGames: [WatchFeedEvent] = []
    @State private var isLoadingGames = false
    @State private var gamesError: String?
    @State private var choosingGame = false
    @State private var refreshGeneration = 0
    @State private var gamesRefreshGeneration = 0

    private var refreshKey: String { "\(scenePhase)-\(refreshGeneration)-\(store.selectedEventID ?? 0)" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let game = store.game {
                    selectedGame(game)
                } else if store.selectedEventID != nil {
                    if store.isRefreshing {
                        ProgressView("Loading selected game")
                    } else {
                        Text(store.errorMessage ?? "Selected game unavailable")
                        Text("Your selection is retained. Refresh to try again.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                } else {
                    gamePicker
                }

                if store.selectedEventID != nil {
                    Button(store.isRefreshing ? "Refreshing…" : "Refresh") {
                        refreshGeneration += 1
                    }
                    .disabled(store.isRefreshing || scenePhase != .active)
                    Button("Choose another game") { choosingGame = true }
                }
            }
            .padding(.horizontal, 6)
        }
        .navigationTitle("Your game")
        .task(id: refreshKey) {
            guard scenePhase == .active else { return }
            if store.selectedEventID == nil {
                await loadGames()
                return
            }
            while !Task.isCancelled {
                await store.refresh()
                guard !Task.isCancelled else { return }
                do { try await Task.sleep(for: .seconds(30)) }
                catch { return }
            }
        }
        .sheet(isPresented: $choosingGame) {
            ScrollView { gamePicker.padding(.horizontal, 6) }
                .navigationTitle("Choose a game")
                .task(id: "\(scenePhase)-\(gamesRefreshGeneration)") {
                    guard scenePhase == .active else { return }
                    await loadGames()
                }
        }
    }

    private func selectedGame(_ game: WatchSelectedGame) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(game.isFinal ? "Final" : game.isLive ? "Live" : game.status?.capitalized ?? "Game state unavailable")
                    .font(.subheadline.bold())
                if game.isLive, let clock = game.liveClockText {
                    Text(clock).font(.footnote)
                }
            }
            scoreRow(team: game.awayTeam, score: game.awayScore)
            scoreRow(team: game.homeTeam, score: game.homeScore)
            if game.isFinal && (game.homeScore == nil || game.awayScore == nil) {
                Text("Final score unavailable")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if !game.isLive && !game.isFinal, let start = game.commenceTime {
                Text(start, format: .dateTime.month().day().hour().minute())
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if !game.isFinal {
                if let probability = game.homeProbability, probability.isFinite,
                   (0...1).contains(probability) {
                    Text("\(game.homeTeam) win")
                        .font(.footnote)
                    Text(probability, format: .percent.precision(.fractionLength(0)))
                        .font(.title2.bold()).monospacedDigit()
                } else {
                    Text("Win probability unavailable")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            TimelineView(.periodic(from: .now, by: 15)) { context in
                observationText(game, now: context.date)
                if !game.isFinal && game.homeProbability != nil {
                    probabilityObservationText(game, now: context.date)
                }
            }
            if store.isRestoredReading {
                Text("Saved reading · refresh to confirm")
                    .font(.footnote).foregroundStyle(.orange)
            }
            if let error = store.errorMessage {
                Text(error)
                    .font(.footnote).foregroundStyle(.orange)
                Text("Showing the last received game. Refresh to try again.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    private func scoreRow(team: String, score: Int?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(team).font(.footnote).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 2)
            Text(score.map(String.init) ?? "—")
                .font(.title3.bold()).monospacedDigit()
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(team), \(score.map { "score \($0)" } ?? "score unavailable")")
    }

    @ViewBuilder
    private func observationText(_ game: WatchSelectedGame, now: Date) -> some View {
        if let age = game.observationAge(at: now) {
            let seconds = max(0, Int(age))
            let ageLabel = seconds < 60 ? "\(seconds)s ago" : "\(seconds / 60)m ago"
            Text("Score observed \(ageLabel)")
                .font(.footnote).foregroundStyle(.secondary)
            if game.isLive && age > 120 {
                Text("Stale score · waiting for a newer observation")
                    .font(.footnote).foregroundStyle(.orange)
            }
        } else {
            Text("Score observation time unavailable")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func probabilityObservationText(_ game: WatchSelectedGame, now: Date) -> some View {
        if let age = game.probabilityAge(at: now) {
            let seconds = max(0, Int(age))
            let ageLabel = seconds < 60 ? "\(seconds)s ago" : "\(seconds / 60)m ago"
            Text("Probability observed \(ageLabel)")
                .font(.footnote).foregroundStyle(.secondary)
            if game.isLive && age > 120 {
                Text("Stale probability · waiting for a newer observation")
                    .font(.footnote).foregroundStyle(.orange)
            }
        } else {
            Text("Probability observation time unavailable")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }

    private var gamePicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Choose one game to follow")
                .font(.headline)
            if isLoadingGames && availableGames.isEmpty {
                ProgressView("Loading games")
            } else if let error = gamesError {
                Text(error).font(.footnote).foregroundStyle(.orange)
            } else if availableGames.isEmpty {
                Text("No games available in Discover right now.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(availableGames) { game in
                Button {
                    store.select(eventID: game.id)
                    choosingGame = false
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("\(game.awayTeam ?? "Away team") at \(game.homeTeam ?? "Home team")")
                            .fixedSize(horizontal: false, vertical: true)
                        Text(game.isSettled ? "Final" : game.isLive ? "Live" : game.status?.capitalized ?? "State unavailable")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            Button("Refresh games") {
                if choosingGame { gamesRefreshGeneration += 1 }
                else { refreshGeneration += 1 }
            }
                .disabled(isLoadingGames || scenePhase != .active)
        }
    }

    @MainActor
    private func loadGames() async {
        isLoadingGames = true
        defer { isLoadingGames = false }
        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 30, forceRefresh: true)
            guard !Task.isCancelled else { return }
            var seen = Set<Int>()
            availableGames = feed.items.compactMap(\.event).filter { seen.insert($0.id).inserted }
            gamesError = nil
        } catch {
            guard !Task.isCancelled else { return }
            gamesError = "Couldn't load available games. Refresh to try again."
        }
    }
}
