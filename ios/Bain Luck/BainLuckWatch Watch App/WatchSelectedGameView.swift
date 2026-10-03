import SwiftUI

/// A deliberately small Watch surface: select one real game and keep it through final.
struct WatchSelectedGameView: View {
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @StateObject private var store = WatchSelectedGameStore()
    @State private var availableGames: [WatchFeedEvent] = []
    @State private var isLoadingGames = false
    @State private var gamesError: String?
    @State private var choosingGame = false
    @State private var refreshGeneration = 0
    @State private var gamesRefreshGeneration = 0
    @State private var gamesRequestRevision = 0

    private var refreshKey: String { "\(scenePhase)-\(choosingGame)-\(refreshGeneration)-\(store.selectedEventID ?? 0)" }

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
            guard scenePhase == .active, !choosingGame else { return }
            if store.selectedEventID == nil {
                await loadGames()
                return
            }
            await store.runForegroundRefresh()
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
            if store.isRestoredReading {
                Text("Saved reading · refresh to confirm")
                    .font(.footnote).foregroundStyle(.orange)
                    .accessibilityHidden(true) // Included before state in the grouped label below.
            }
            flexibleRow {
                Text(game.isFinal ? "Final" : game.isLive ? "Live" : game.status?.capitalized ?? "Game state unavailable")
                    .font(.subheadline.bold())
                if game.isLive, let clock = game.liveClockText {
                    Text(clock).font(.footnote)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(stateAccessibilityLabel(game))
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
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(game.homeTeam) win").font(.footnote)
                        Text(probability, format: .percent.precision(.fractionLength(0)))
                            .font(.title2.bold()).monospacedDigit()
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(game.homeTeam) win probability, \(probability.formatted(.percent.precision(.fractionLength(0))))")
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
            if let error = store.errorMessage {
                Text(error)
                    .font(.footnote).foregroundStyle(.orange)
                Text("Showing the last received game. Refresh to try again.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    private func scoreRow(team: String, score: Int?) -> some View {
        flexibleRow {
            Text(team).font(.footnote).fixedSize(horizontal: false, vertical: true)
            if !dynamicTypeSize.isAccessibilitySize { Spacer(minLength: 2) }
            Text(score.map(String.init) ?? "—")
                .font(.title3.bold()).monospacedDigit()
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(team), \(score.map { "score \($0)" } ?? "score unavailable")")
    }

    private func stateAccessibilityLabel(_ game: WatchSelectedGame) -> String {
        let state = game.isFinal ? "Final" : game.isLive ? "Live" : game.status?.capitalized ?? "Game state unavailable"
        return [store.isRestoredReading ? "Saved reading. Refresh to confirm." : nil,
                store.errorMessage, state, game.isLive ? game.liveClockText : nil]
            .compactMap { $0 }.joined(separator: " ")
    }

    private func flexibleRow<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 3))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 6))
        return layout { content() }
    }

    private func observationText(_ game: WatchSelectedGame, now: Date) -> some View {
        observationLabel("Score", observedAt: game.scoreObservedAt, now: now, isLive: game.isLive)
    }

    private func probabilityObservationText(_ game: WatchSelectedGame, now: Date) -> some View {
        observationLabel("Probability", observedAt: game.probabilityObservedAt, now: now, isLive: game.isLive)
    }

    @ViewBuilder
    private func observationLabel(_ name: String, observedAt: Date?, now: Date, isLive: Bool) -> some View {
        let age = WatchObservationAge(observedAt: observedAt, now: now)
        if let compact = age.compactText, let spoken = age.spokenText {
            Text("\(name) observed \(compact)")
                .font(.footnote).foregroundStyle(.secondary)
                .accessibilityLabel("\(name) observed \(spoken)")
            if isLive && age.isStale {
                Text("Stale \(name.lowercased()) · waiting for a newer observation")
                    .font(.footnote).foregroundStyle(.orange)
            }
        } else {
            Text("\(name) observation time unavailable")
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
        guard !Task.isCancelled else { return }
        gamesRequestRevision += 1
        let requestRevision = gamesRequestRevision
        isLoadingGames = true
        defer {
            if gamesRequestRevision == requestRevision { isLoadingGames = false }
        }
        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 30, forceRefresh: true)
            guard !Task.isCancelled, gamesRequestRevision == requestRevision else { return }
            var seen = Set<Int>()
            availableGames = feed.items.compactMap(\.event).filter { seen.insert($0.id).inserted }
            gamesError = nil
        } catch {
            guard !Task.isCancelled, gamesRequestRevision == requestRevision else { return }
            gamesError = "Couldn't load available games. Refresh to try again."
        }
    }
}
