import SwiftUI

private nonisolated struct WatchDiscoverGameTransport: WatchGamePickerTransport {
    func fetchGames() async throws -> WatchGamePickerBatch {
        let feed = try await WatchAPIClient.shared.fetchFeed(limit: 30, forceRefresh: true)
        return WatchGamePickerBatch(feed: feed)
    }
}

/// A deliberately small Watch surface: select one real game and keep it through final.
struct WatchSelectedGameView: View {
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @StateObject private var store: WatchSelectedGameStore
    @StateObject private var picker: WatchGamePickerStore
    @State private var choosingGame = false
    @State private var showingHandoffHelp = false
    @State private var showingDiscoveries = false
    #if DEBUG
    @State private var launcherOpenCount = 0
    #endif
    @State private var refreshGeneration = 0
    @State private var gamesRefreshGeneration = 0

    init() {
        #if DEBUG
        if let fixture = WatchUIFixture.current {
            _store = StateObject(wrappedValue: WatchUpdatingUIFixture.enabled
                ? WatchUpdatingUIFixture.makeStore(fixture: fixture) : fixture.makeStore())
            _picker = StateObject(wrappedValue: WatchGamePickerStore(transport: fixture))
            return
        }
        #endif
        _store = StateObject(wrappedValue: WatchSelectedGameStore(publish: WatchComplicationPublisher.publish))
        _picker = StateObject(wrappedValue: WatchGamePickerStore(transport: WatchDiscoverGameTransport()))
    }

    private var refreshKey: String { "\(scenePhase)-\(choosingGame)-\(showingDiscoveries)-\(refreshGeneration)-\(store.selectedEventID ?? 0)" }

    private var telemetrySurface: WatchTelemetrySurface {
        showingDiscoveries ? .discoveries : (choosingGame || store.selectedEventID == nil ? .picker : .game)
    }

    private var continuationEventID: Int? {
        guard scenePhase == .active, !choosingGame, !showingDiscoveries else { return nil }
        return store.game?.id
    }

    var body: some View {
        ScrollViewReader { scroll in
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Color.clear.frame(height: 0).id("watch.game.top").accessibilityHidden(true)
                if let game = store.game {
                    selectedGame(game)
                        .onAppear {
                            WatchTelemetry.shared.content(.game)
                            WatchTelemetry.shared.reading(.game, fetchedAt: store.fetchedAt, saved: store.isRestoredReading, count: 1)
                        }
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
                        WatchTelemetry.shared.action(.refresh, surface: .game)
                        store.allowManualRetry()
                        refreshGeneration += 1
                    }
                    .disabled(store.isRefreshing || scenePhase != .active)
                    if store.game != nil {
                        Button("Continue on iPhone") {
                            WatchTelemetry.shared.action(.phoneContinuation, surface: .game)
                            showingHandoffHelp = true
                        }
                            .accessibilityIdentifier("watch.continue-on-phone")
                    }
                    Button("Choose another game") {
                        WatchTelemetry.shared.action(.chooseGame, surface: .game)
                        choosingGame = true
                    }
                        .accessibilityIdentifier("watch.choose-another")
                    Button("Clear selected game") {
                        WatchTelemetry.shared.action(.clearGame, surface: .game)
                        choosingGame = false
                        showingHandoffHelp = false
                        store.clearSelection()
                    }
                    .accessibilityIdentifier("watch.clear-selection")
                }
                Button("Discoveries") {
                    WatchTelemetry.shared.action(.discoveries, surface: telemetrySurface)
                    showingDiscoveries = true
                }
                    .accessibilityIdentifier("watch.discoveries-entry")
                NavigationLink("Diagnostics") { WatchDiagnosticsView().dynamicTypeSize(dynamicTypeSize) }
                    .accessibilityIdentifier("watch.diagnostics")
                #if DEBUG
                if WatchUIFixture.current?.launchReceipt == true {
                    Text("Launcher opens: \(launcherOpenCount)")
                        .font(.footnote)
                        .accessibilityIdentifier("watch.launch-receipt")
                    Text(WatchUIFixture.processID).font(.footnote)
                        .accessibilityIdentifier("watch.launch-process")
                }
                #endif
            }
            .padding(.horizontal, 6)
        }
        .onOpenURL { url in
            guard WatchLaunchRoute.accepts(url) else { return }
            WatchTelemetry.shared.action(.complicationOpen, surface: telemetrySurface)
            #if DEBUG
            launcherOpenCount += 1
            #endif
            // Warm launch must reveal the retained choice, not a picker/help overlay.
            // Existing foreground refresh rules still own all network scheduling.
            choosingGame = false
            showingHandoffHelp = false
            showingDiscoveries = false
            scroll.scrollTo("watch.game.top", anchor: .top)
        }
        .onAppear {
            store.telemetry = { outcome, ms, count in
                WatchTelemetry.shared.refreshResult(.game, outcome: outcome, durationMS: ms, count: count)
            }
            picker.telemetry = { outcome, ms, count in
                WatchTelemetry.shared.refreshResult(.picker, outcome: outcome, durationMS: ms, count: count)
            }
            WatchTelemetry.shared.screen(telemetrySurface)
        }
        .onChange(of: telemetrySurface) { _, surface in WatchTelemetry.shared.screen(surface) }
        .onChange(of: store.fetchedAt) { _, _ in
            if store.game != nil { WatchTelemetry.shared.reading(.game, fetchedAt: store.fetchedAt, saved: store.isRestoredReading, count: 1) }
        }
        .onChange(of: store.isRestoredReading) { _, _ in
            if store.game != nil {
                WatchTelemetry.shared.reading(.game, fetchedAt: store.fetchedAt, saved: store.isRestoredReading, count: 1)
            }
        }
        .navigationTitle("Your game")
        .userActivity(GameContinuation.activityType, element: continuationEventID) { id, activity in
            GameContinuation.configure(activity, eventID: id)
        }
        .alert("Continue on iPhone", isPresented: $showingHandoffHelp) {
            Button("OK", role: .cancel) { WatchTelemetry.shared.action(.dismissHelp, surface: .game) }
        } message: {
            Text("Look for Bain Luck’s Handoff option in your iPhone’s App Switcher. Your iPhone needs a Bain Luck version with Watch Handoff support. Both devices need Handoff enabled and the same Apple Account. If it isn’t available, your game stays selected here.")
        }
        .task(id: refreshKey) {
            guard scenePhase == .active, !choosingGame, !showingDiscoveries else { return }
            if store.selectedEventID == nil {
                await picker.refresh()
                return
            }
            await store.runForegroundRefresh()
        }
        .sheet(isPresented: $showingDiscoveries) {
            NavigationStack {
                WatchDiscoverStoriesView(selected: store) { showingDiscoveries = false }
            }
            #if DEBUG
            .transformEnvironment(\.dynamicTypeSize) { size in
                // Match the established picker sheet's layout-stress fixture.
                if WatchUIFixture.current != nil,
                   ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_LARGE_TEXT"] == "1" {
                    size = dynamicTypeSize
                }
            }
            #endif
        }
        .sheet(isPresented: $choosingGame) {
            NavigationStack {
                ScrollView { gamePicker.padding(.horizontal, 6) }
                    .navigationTitle("Choose a game")
                    .toolbar {
                        if store.selectedEventID != nil {
                            ToolbarItem(placement: .cancellationAction) {
                                Button("Your game") {
                                    WatchTelemetry.shared.action(.close, surface: .picker)
                                    choosingGame = false
                                }
                                    .accessibilityLabel("Back to your game")
                                    .accessibilityIdentifier("watch.picker-cancel")
                            }
                        }
                    }
                    .task(id: "\(scenePhase)-\(gamesRefreshGeneration)") {
                        guard scenePhase == .active else { return }
                        await picker.refresh()
                    }
            }
            #if DEBUG
            .transformEnvironment(\.dynamicTypeSize) { size in
                // The injected layout-stress category does not cross watchOS
                // sheet presentation automatically. Extend fixtures only.
                if WatchUIFixture.current != nil,
                   ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_LARGE_TEXT"] == "1" {
                    size = dynamicTypeSize
                }
            }
            #endif
        }
        .onChange(of: store.selectedEventID) { _, _ in
            // A new choice must reveal its identity, not inherit the old game's scroll.
            scroll.scrollTo("watch.game.top", anchor: .top)
        }
        .onChange(of: choosingGame) { wasChoosing, isChoosing in
            if wasChoosing && !isChoosing && store.selectedEventID != nil {
                // Returning from the picker reveals the retained game's identity.
                scroll.scrollTo("watch.game.top", anchor: .top)
            }
        }
        .onChange(of: showingDiscoveries) { wasShowing, isShowing in
            if wasShowing && !isShowing {
                scroll.scrollTo("watch.game.top", anchor: .top)
            }
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
            if store.isRefreshing {
                Text("Updating…")
                    .font(.footnote).foregroundStyle(.secondary)
                    .accessibilityIdentifier("watch.game-updating")
            }
            flexibleRow {
                Text(game.stateLabel)
                    .font(.subheadline.bold())
                if game.isLive, let clock = game.liveClockText {
                    Text(clock).font(.footnote)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(stateAccessibilityLabel(game))
            .accessibilityIdentifier("watch.game-state")
            #if DEBUG
            .accessibilityValue(WatchUpdatingUIFixture.enabled
                ? "\(dynamicTypeSize)|\(game.id)|\(game.scoreObservedAt?.timeIntervalSince1970.description ?? "nil")|\(game.probabilityObservedAt?.timeIntervalSince1970.description ?? "nil")"
                : (WatchUIFixture.current == nil ? "" : String(describing: dynamicTypeSize)))
            #endif
            if game.isClosed {
                Text("Last reported score · final result unverified")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            scoreRow(team: game.awayTeam, score: game.awayScore)
                .accessibilityIdentifier("watch.away-score")
            scoreRow(team: game.homeTeam, score: game.homeScore)
                .accessibilityIdentifier("watch.home-score")
            if game.isFinal && (game.homeScore == nil || game.awayScore == nil) {
                Text("Final score unavailable")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if !game.isLive && game.showsForecast, let start = game.commenceTime {
                Text(start, format: .dateTime.month().day().hour().minute())
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if game.showsForecast {
                if let probabilityText = game.homeProbabilityText {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(game.homeTeam) win").font(.footnote)
                        Text(probabilityText)
                            .font(.title2.bold()).monospacedDigit()
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityIdentifier("watch.home-probability")
                    .accessibilityLabel("\(game.homeTeam) win probability, \(probabilityText)")
                } else {
                    Text("Win probability unavailable")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            TimelineView(.periodic(from: .now, by: 15)) { context in
                observationText(game, now: context.date)
                if game.showsForecast && game.homeProbability != nil {
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
        let state = game.stateLabel
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
            WatchPickerHeading()
            if picker.isLoading && picker.games.isEmpty {
                ProgressView("Loading games")
            } else if let error = picker.errorMessage {
                Text(error).font(.footnote).foregroundStyle(.orange)
                    .accessibilityIdentifier("watch.picker-error")
                if !picker.games.isEmpty {
                    Text("Showing the previously received list.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            } else if picker.games.isEmpty {
                Text(picker.omittedGameCount > 0 ? "Game details are unavailable. Refresh to try again." : "No games available in Discover right now.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if !picker.games.isEmpty {
                Text("Games from Discover · not the full schedule")
                    .font(.footnote).foregroundStyle(.secondary)
                if picker.omittedGameCount > 0 {
                    Text("Some games have unavailable details.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            ForEach(picker.games) { game in
                let isSelected = game.id == store.selectedEventID
                Button {
                    WatchTelemetry.shared.action(store.selectedEventID == game.id ? .reselectGame : .selectGame, surface: .picker)
                    store.select(eventID: game.id)
                    choosingGame = false
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("\(game.awayTeam ?? "Away team") at \(game.homeTeam ?? "Home team")")
                            .fixedSize(horizontal: false, vertical: true)
                        Text(WatchSelectedGame.stateLabel(for: game.status))
                            .font(.footnote).foregroundStyle(.secondary)
                        if isSelected {
                            Label("Your game", systemImage: "checkmark")
                                .font(.footnote)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityHidden(true)
                        }
                    }
                }
                .accessibilityLabel("\(game.awayTeam ?? "Away team") at \(game.homeTeam ?? "Home team"). \(WatchSelectedGame.stateLabel(for: game.status))" + (isSelected ? ". Your game" : ""))
                .accessibilityAddTraits(isSelected ? .isSelected : [])
                .accessibilityIdentifier("watch.pick.\(game.id)")
                .onAppear { WatchTelemetry.shared.content(.picker) }
            }
            Button("Refresh games") {
                WatchTelemetry.shared.action(.refresh, surface: .picker)
                if choosingGame { gamesRefreshGeneration += 1 }
                else { refreshGeneration += 1 }
            }
                .disabled(picker.isLoading || scenePhase != .active)
        }
    }

}

private struct WatchPickerHeading: View {
    #if DEBUG
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    #endif

    var body: some View {
        Text("Choose your game")
            .font(.headline)
            .accessibilityIdentifier("watch.picker-heading")
            #if DEBUG
            // Read the heading's own environment, including a presented sheet.
            .accessibilityValue(WatchUIFixture.current == nil ? "" : String(describing: dynamicTypeSize))
            #endif
    }
}
