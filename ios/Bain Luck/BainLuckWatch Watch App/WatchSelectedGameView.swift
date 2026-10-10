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
    @State private var showingMyStuff = false
    @ObservedObject private var myStuff = WatchMyStuffStore.shared
    #if DEBUG
    @State private var launcherOpenCount = 0
    #endif
    @State private var refreshGeneration = 0
    @State private var gamesRefreshGeneration = 0
    @State private var showingPickerDetails = false
    @State private var showingMoreActions = false

    init() {
        #if DEBUG
        if let fixture = WatchUIFixture.current {
            if let scoreFixture = WatchScoreLayoutUIFixture.current {
                _store = StateObject(wrappedValue: scoreFixture.makeStore(fixture: fixture))
                _picker = StateObject(wrappedValue: WatchGamePickerStore(transport: fixture))
                return
            }
            if WatchFirstOpenUIFixture.enabled {
                _store = StateObject(wrappedValue: WatchFirstOpenUIFixture.makeStore(fixture: fixture))
                _picker = StateObject(wrappedValue: WatchGamePickerStore(transport: WatchFirstOpenUITransport()))
                return
            }
            _store = StateObject(wrappedValue: WatchUpdatingUIFixture.enabled
                ? WatchUpdatingUIFixture.makeStore(fixture: fixture) : fixture.makeStore())
            _picker = StateObject(wrappedValue: WatchGamePickerStore(transport: fixture))
            return
        }
        #endif
        _store = StateObject(wrappedValue: WatchSelectedGameStore(publish: WatchComplicationPublisher.publish))
        _picker = StateObject(wrappedValue: WatchGamePickerStore(transport: WatchDiscoverGameTransport()))
    }

    private var refreshKey: String { "\(scenePhase)-\(choosingGame)-\(showingDiscoveries)-\(showingMyStuff)-\(refreshGeneration)-\(store.selectedEventID ?? 0)" }

    private var telemetrySurface: WatchTelemetrySurface {
        showingDiscoveries ? .discoveries : (choosingGame || store.selectedEventID == nil ? .picker : .game)
    }

    private var continuationEventID: Int? {
        guard scenePhase == .active, !choosingGame, !showingDiscoveries, !showingMyStuff else { return nil }
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
                    if let context = picker.games.first(where: { store.isSelected(eventID: $0.id) }) {
                        VStack(alignment: .leading, spacing: 4) {
                            pickerMatchup(away: context.awayTeam ?? "Away team",
                                          home: context.homeTeam ?? "Home team", metadata: context)
                            if let start = pickerScheduledStart(context) {
                                Text(start).font(.footnote).foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("watch.selection-context")
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        if store.isRefreshing {
                            ProgressView("Loading selected game")
                                .accessibilityIdentifier("watch.loading-selected-game")
                            Text("Your selection is retained while details load.")
                                .font(.footnote).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.selection-loading-explanation")
                        } else if let error = store.errorMessage {
                            Text("Reading unavailable")
                                .font(.headline)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.selection-state-heading")
                            Text(error)
                                .font(.body)
                                .fixedSize(horizontal: false, vertical: true)
                            Text("Your selection is retained. Refresh to try again.")
                                .font(.footnote).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.selection-retry-explanation")
                        } else {
                            Text("Game details have not loaded yet")
                                .font(.headline)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.selection-state-heading")
                            Text("Your selection is retained. Refresh to try again.")
                                .font(.footnote).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.selection-retry-explanation")
                        }
                    }
                } else {
                    gamePicker
                }

                if store.selectedEventID != nil {
                    Button {
                        WatchTelemetry.shared.action(.refresh, surface: .game)
                        store.allowManualRetry()
                        refreshGeneration += 1
                    } label: {
                        Label(store.isRefreshing ? "Refreshing…" : "Refresh", systemImage: "arrow.clockwise")
                            .font(.footnote.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 8)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .disabled(store.isRefreshing || scenePhase != .active)
                    Button {
                        WatchTelemetry.shared.action(.chooseGame, surface: .game)
                        choosingGame = true
                    } label: {
                        Text("Choose another game")
                            .font(.footnote.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 8)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("watch.choose-another")
                }
                Button {
                    WatchTelemetry.shared.action(.discoveries, surface: telemetrySurface)
                    showingDiscoveries = true
                } label: {
                    Text("Discoveries")
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 8)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch.discoveries-entry")
                Button { showingMyStuff = true } label: {
                    Label("My Stuff", systemImage: "bookmark")
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch.my-stuff-entry")
                Button {
                    showingMoreActions.toggle()
                } label: {
                    Label("More actions", systemImage: showingMoreActions ? "chevron.up" : "chevron.down")
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 8)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityValue(showingMoreActions ? "Expanded" : "Collapsed")
                .accessibilityIdentifier("watch.more-actions")
                if showingMoreActions {
                    if store.selectedEventID != nil {
                        if store.game != nil {
                            Button {
                                WatchTelemetry.shared.action(.phoneContinuation, surface: .game)
                                showingHandoffHelp = true
                            } label: {
                                Text("Continue on iPhone")
                                    .font(.footnote.weight(.semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                    .padding(.horizontal, 8)
                                    .frame(maxWidth: .infinity, minHeight: 44)
                                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("watch.continue-on-phone")
                        }
                    }
                    NavigationLink("Diagnostics") { WatchDiagnosticsView().dynamicTypeSize(dynamicTypeSize) }
                        .accessibilityIdentifier("watch.diagnostics")
                }
                if store.selectedEventID != nil {
                    Divider()
                    Button {
                        WatchTelemetry.shared.action(.clearGame, surface: .game)
                        choosingGame = false
                        showingHandoffHelp = false
                        store.clearSelection()
                    } label: {
                        Text("Clear selected game")
                            .font(.footnote).foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 8)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .contentShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("watch.clear-selection")
                }
                #if DEBUG
                if WatchFirstOpenUIFixture.enabled, store.selectedEventID != nil, store.game == nil {
                    Button("Deliver test detail") {
                        guard let id = store.selectedEventID else { return }
                        Task { await WatchFirstOpenUIFixture.shared.resolve(eventID: id, fail: false) }
                    }
                    .accessibilityIdentifier("watch.fixture-deliver-detail")
                    Button("Fail test detail") {
                        guard let id = store.selectedEventID else { return }
                        Task { await WatchFirstOpenUIFixture.shared.resolve(eventID: id, fail: true) }
                    }
                    .accessibilityIdentifier("watch.fixture-fail-detail")
                }
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
            showingMyStuff = false
            scroll.scrollTo("watch.game.top", anchor: .top)
        }
        .onAppear {
            myStuff.expireIfNeeded()
            myStuff.reconcileSelection(in: store)
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
        .navigationBarTitleDisplayMode(store.selectedEventID == nil ? .automatic : .inline)
        .userActivity(GameContinuation.activityType, element: continuationEventID) { id, activity in
            GameContinuation.configure(activity, eventID: id)
        }
        .alert("Continue on iPhone", isPresented: $showingHandoffHelp) {
            Button("OK", role: .cancel) { WatchTelemetry.shared.action(.dismissHelp, surface: .game) }
        } message: {
            Text("On your iPhone, swipe up from the bottom and pause midway. If it has a Home button, double-click Home.\n\nLook along the bottom for Bain Luck’s Handoff banner. Tap it if shown.\n\nBoth devices need Handoff on and the same Apple Account. The iPhone app must support Watch Handoff.\n\nIf no banner appears, your game stays selected here.")
        }
        .task(id: refreshKey) {
            guard scenePhase == .active, !choosingGame, !showingDiscoveries, !showingMyStuff else { return }
            if store.selectedEventID == nil {
                await picker.refresh()
                return
            }
            await store.runForegroundRefresh()
        }
        .onChange(of: myStuff.snapshot) { _, _ in myStuff.reconcileSelection(in: store) }
        .onChange(of: myStuff.navigationGeneration) { _, _ in myStuff.reconcileSelection(in: store) }
        .sheet(isPresented: $showingMyStuff) {
            NavigationStack {
                WatchMyStuffView(selected: store) { showingMyStuff = false }
            }
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
                    .navigationTitle("Games")
                    .toolbar {
                        if store.selectedEventID != nil {
                            ToolbarItem(placement: .cancellationAction) {
                                Button {
                                    WatchTelemetry.shared.action(.close, surface: .picker)
                                    choosingGame = false
                                } label: {
                                    Image(systemName: "chevron.backward")
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
            myStuff.reconcileSelection(in: store)
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
        let probabilityFirst = game.showsForecast && game.homeProbabilityText != nil
        let sharedLiveIdentity = usesSharedLiveIdentity(game)
        let scheduledStart = scheduledStartText(game)
        let hasReportedScore = game.homeScore != nil || game.awayScore != nil
        let showsScores = hasReportedScore || game.isLive || game.isFinal || game.isClosed
        let hasSuppliedState = game.status?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        let showsContextHeader = game.isClosed || finalOutcomeText(game) != nil || (hasSuppliedState && !store.isRestoredReading && store.errorMessage == nil)
        return TimelineView(.periodic(from: .now, by: 15)) { context in
            VStack(alignment: .leading, spacing: 6) {
                if sharedLiveIdentity {
                    sharedLiveHomeReading(game)
                } else if probabilityFirst {
                    probabilityReading(game)
                }
                if let scheduledStart {
                    Text(scheduledStart)
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("watch.scheduled-start")
                }
                if showsScores {
                    if scheduledStart == nil {
                        if showsContextHeader {
                            gameState(game)
                                .accessibilityAddTraits(.isHeader)
                        } else if !sharedLiveIdentity {
                            Text(game.isFinal ? "Final score" : "Score")
                                .font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
                                .accessibilityAddTraits(.isHeader)
                                .accessibilityIdentifier("watch.score-heading")
                        }
                    }
                    if sharedLiveIdentity {
                        sharedLiveAwayReading(game)
                    } else {
                        fullWidthScores(game)
                    }
                } else {
                    Text("\(game.awayTeam) at \(game.homeTeam)")
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.scheduled-matchup")
                }
                if let explanation = liveScoreExplanation(game) {
                    Text(explanation)
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.live-score-explanation")
                }
                if game.isFinal && (game.homeScore == nil || game.awayScore == nil) {
                    Text("Final score unavailable")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if scheduledStart == nil && !game.isLive && game.showsForecast, let start = game.commenceTime {
                    Text(start, format: .dateTime.month().day().hour().minute())
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if scheduledStart == nil && !showsScores && showsContextHeader {
                    gameState(game)
                }
                if !probabilityFirst { probabilityReading(game) }
                Divider().padding(.vertical, 4)
                if !showsContextHeader {
                    gameState(game)
                }
                if store.isRefreshing {
                    Text("Updating…")
                        .font(.footnote).foregroundStyle(.secondary)
                        .accessibilityIdentifier("watch.game-updating")
                }
                if store.isRestoredReading {
                    Text("Last saved update")
                        .font(.footnote).foregroundStyle(.secondary)
                        .accessibilityIdentifier("watch.saved-update")
                }
                if let error = store.errorMessage {
                    Text(error.hasPrefix("Offline.") ? "Connect to update" : "Unable to update. Try Refresh.")
                        .font(.footnote).foregroundStyle(.secondary)
                        .accessibilityLabel(error)
                        .accessibilityIdentifier("watch.update-explanation")
                }
                observationText(game, now: context.date)
                if game.showsForecast && game.homeProbability != nil {
                    probabilityObservationText(game, now: context.date)
                }
            }
        }
    }

    private func scheduledStartText(_ game: WatchSelectedGame) -> String? {
        // A supplied timestamp alone does not establish scheduled status.
        guard game.status?.lowercased() == "scheduled" else { return nil }
        guard let start = game.commenceTime else { return "Scheduled · time unavailable" }
        return "Scheduled " + start.formatted(.dateTime.month().day().hour().minute())
    }

    private func liveScoreExplanation(_ game: WatchSelectedGame) -> String? {
        guard game.isLive else { return nil }
        if game.awayScore == nil && game.homeScore == nil { return "Score unavailable" }
        if game.awayScore == nil || game.homeScore == nil { return "One score unavailable" }
        return nil
    }

    private func finalOutcomeText(_ game: WatchSelectedGame) -> String? {
        // Reuse the existing complication projection's final-score interpretation.
        guard game.isFinal, let home = game.homeScore, let away = game.awayScore,
              home >= 0, away >= 0 else { return nil }
        if home > away { return "Final · \(game.homeTeam) won" }
        if away > home { return "Final · \(game.awayTeam) won" }
        return "Final · scores tied"
    }

    private func gameState(_ game: WatchSelectedGame) -> some View {
        flexibleRow {
            Text(game.isClosed ? "Result not confirmed" :
                 (finalOutcomeText(game) ??
                  (game.isLive && (store.isRestoredReading || store.errorMessage != nil)
                   ? "At last update: Live" : game.stateLabel)))
                .font(.footnote).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if game.isLive, let clock = game.liveClockText {
                Text(clock).font(.footnote).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
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
    }

    @ViewBuilder
    private func probabilityReading(_ game: WatchSelectedGame) -> some View {
        if game.showsForecast {
            if let probabilityText = game.homeProbabilityText {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(game.homeTeam) win")
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if dynamicTypeSize.isAccessibilitySize {
                        Text(probabilityText).font(.title2.bold()).monospacedDigit()
                            .foregroundStyle(.cyan)
                    } else {
                        Text(probabilityText)
                            .font(.system(size: 34, weight: .bold, design: .rounded))
                            .monospacedDigit().foregroundStyle(.cyan)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityIdentifier("watch.home-probability")
                .accessibilityLabel("\(game.homeTeam) win probability, \(probabilityText)")
            } else {
                Text("\(game.homeTeam) win chance unavailable")
                    .font(.footnote).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.home-probability-unavailable")
            }
        }
    }

    private func usesSharedLiveIdentity(_ game: WatchSelectedGame) -> Bool {
        game.isLive && game.homeProbabilityText != nil
            && game.homeScore != nil && game.awayScore != nil
    }

    @ViewBuilder
    private func sharedLiveHomeReading(_ game: WatchSelectedGame) -> some View {
        if let probabilityText = game.homeProbabilityText, let score = game.homeScore {
            VStack(alignment: .leading, spacing: 2) {
                scoreTeamName(game.homeTeam, color: scoreTeamColor(game, home: true))
                    .font(.footnote.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(game.homeTeam)
                    .accessibilityIdentifier("watch.home-identity")
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 6) {
                        sharedLiveProbability(team: game.homeTeam, probability: probabilityText)
                        sharedLiveHomeScore(team: game.homeTeam, score: score)
                    }
                } else {
                    HStack(alignment: .top, spacing: 12) {
                        sharedLiveProbability(team: game.homeTeam, probability: probabilityText)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        sharedLiveHomeScore(team: game.homeTeam, score: score)
                    }
                }
            }
        }
    }

    private func sharedLiveProbability(team: String, probability: String) -> some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Win chance").font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(probability).font(.title2.bold()).monospacedDigit()
                        .foregroundStyle(.cyan)
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(probability)
                        .font(.system(size: 34, weight: .bold, design: .rounded))
                        .monospacedDigit().foregroundStyle(.cyan).fixedSize()
                    Text("Win chance").font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityIdentifier("watch.home-probability")
        .accessibilityLabel("\(team) win probability, \(probability)")
    }

    private func sharedLiveHomeScore(team: String, score: Int) -> some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 4))
        return layout {
            Text("Score").font(.footnote).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(String(score)).font(.title3.bold()).monospacedDigit()
        }
        .accessibilityElement(children: .ignore)
        .accessibilityIdentifier("watch.home-score")
        .accessibilityLabel("\(team), score \(score)")
    }

    @ViewBuilder
    private func sharedLiveAwayReading(_ game: WatchSelectedGame) -> some View {
        if let score = game.awayScore {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    scoreTeamName(game.awayTeam, color: scoreTeamColor(game, home: false))
                        .font(.footnote).fixedSize()
                    Spacer(minLength: 2)
                    Text("Score \(score)").font(.title3.bold()).monospacedDigit().fixedSize()
                }
                VStack(alignment: .leading, spacing: 3) {
                    scoreTeamName(game.awayTeam, color: scoreTeamColor(game, home: false))
                        .font(.footnote).fixedSize(horizontal: false, vertical: true)
                    Text("Score \(score)").font(.title3.bold()).monospacedDigit()
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityIdentifier("watch.away-score")
            .accessibilityLabel("\(game.awayTeam), score \(score)")
        }
    }

    private func fullWidthScores(_ game: WatchSelectedGame) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            scoreRow(team: game.awayTeam, score: game.awayScore,
                     color: scoreTeamColor(game, home: false))
                .accessibilityIdentifier("watch.away-score")
            scoreRow(team: game.homeTeam, score: game.homeScore,
                     color: scoreTeamColor(game, home: true))
                .accessibilityIdentifier("watch.home-score")
        }
    }

    private func scoreColumn(team: String, score: Int?, color: Color?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            scoreTeamName(team, color: color).font(.footnote.weight(.semibold))
                .fixedSize()
            Text(score.map(String.init) ?? "—")
                .font(.title2.bold()).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(team), \(score.map { "score \($0)" } ?? "score unavailable")")
    }

    private func scoreRow(team: String, score: Int?, color: Color?) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                scoreTeamName(team, color: color).font(.footnote).fixedSize()
                Spacer(minLength: 2)
                Text(score.map(String.init) ?? "—")
                    .font(.title3.bold()).monospacedDigit().fixedSize()
            }
            VStack(alignment: .leading, spacing: 3) {
                scoreTeamName(team, color: color).font(.footnote).fixedSize(horizontal: false, vertical: true)
                Text(score.map(String.init) ?? "—")
                    .font(.title3.bold()).monospacedDigit()
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(team), \(score.map { "score \($0)" } ?? "score unavailable")")
    }

    private func scoreTeamColor(_ game: WatchSelectedGame, home: Bool) -> Color? {
        // Reuse only already-loaded metadata for this exact displayed event.
        // A proven selection alias is not an exact metadata match here.
        guard store.selectedEventID == game.id,
              let metadata = picker.games.first(where: { $0.id == game.id }) else { return nil }
        return pickerTeamColor(home ? metadata.homeTeamData?.primaryColor : metadata.awayTeamData?.primaryColor)
    }

    @ViewBuilder
    private func scoreTeamName(_ name: String, color: Color?) -> some View {
        if let color {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Circle().fill(color)
                    .overlay(Circle().stroke(Color.white.opacity(0.45), lineWidth: 0.5))
                    .frame(width: 6, height: 6)
                    .accessibilityHidden(true)
                Text(name).fixedSize(horizontal: false, vertical: true)
            }
        } else {
            Text(name).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func stateAccessibilityLabel(_ game: WatchSelectedGame) -> String {
        if game.isClosed { return "Result not confirmed" }
        if let outcome = finalOutcomeText(game) { return outcome }
        let state = game.isLive && (store.isRestoredReading || store.errorMessage != nil)
            ? "At last update: Live" : game.stateLabel
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
            Text("\(name) as of \(compact)")
                .font(.footnote).foregroundStyle(.secondary)
                .accessibilityLabel("\(name) observed \(spoken)")
                .accessibilityValue(isLive && age.isStale ? "May be out of date" : "")
        } else {
            Text("\(name) update time unavailable")
                .font(.footnote).foregroundStyle(.secondary)
                .accessibilityLabel("\(name) observation time unavailable")
        }
    }

    private var otherPickerGames: [WatchFeedEvent] {
        // Only the provider-proven identity relation can remove a current row.
        picker.games.filter { !store.isSelected(eventID: $0.id) }
    }

    private var pickerStatus: String? {
        if picker.isLoading { return "Updating games…" }
        if let error = picker.errorMessage {
            let reason = error.hasPrefix("Offline.") ? "Offline" : "Refresh unavailable"
            return reason + (picker.games.isEmpty ? " · No list received" : " · Previous list")
        }
        if picker.games.isEmpty {
            return picker.omittedGameCount > 0 ? "Game details unavailable" : "No games in Discover right now"
        }
        if picker.omittedGameCount > 0 { return "Some games unavailable" }
        if store.selectedEventID != nil && otherPickerGames.isEmpty { return "No other games in Discover right now" }
        return nil
    }

    private var gamePicker: some View {
        VStack(alignment: .leading, spacing: 12) {
            WatchPickerHeading(hasSelection: store.selectedEventID != nil)
            if let game = store.game {
                currentPickerGame(game)
                Divider().padding(.vertical, 4)
            } else if store.selectedEventID != nil {
                Text("Your selection is retained. Its reading is unavailable.")
                    .font(.footnote).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.picker-current-unavailable")
                Divider().padding(.vertical, 4)
            }
            if store.selectedEventID != nil {
                Text("Other games").font(.headline)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("watch.picker-other-heading")
            }
            if let status = pickerStatus {
                Text(status)
                    .font(.footnote)
                    .foregroundStyle(picker.errorMessage == nil ? Color.secondary : Color.orange)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.picker-status")
            }
            if otherPickerGames.isEmpty {
                pickerRefreshButton
            }

            ForEach(otherPickerGames) { game in
                Button {
                    WatchTelemetry.shared.action(store.isSelected(eventID: game.id) ? .reselectGame : .selectGame, surface: .picker)
                    store.select(eventID: game.id)
                    choosingGame = false
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        if let preview = pickerScorePreview(game) {
                            Text(preview.visual)
                                .font(.body.bold())
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.pick-score.\(game.id)")
                            Text("Score observation time unavailable")
                                .font(.footnote).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.pick-score-time.\(game.id)")
                        } else {
                            pickerMatchup(away: game.awayTeam ?? "Away team", home: game.homeTeam ?? "Home team", metadata: game)
                        }
                        Text(WatchSelectedGame.stateLabel(for: game.status))
                            .font(.footnote).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        if game.status?.lowercased() == "scheduled",
                           let raw = game.commenceTime, let start = WatchFeedFutures.isoDate(raw) {
                            Text(start, format: .dateTime.month().day().hour().minute())
                                .font(.footnote).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("watch.pick-start.\(game.id)")
                        }
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(pickerChoiceAccessibility(game))
                .accessibilityValue(pickerScheduledStart(game).map { "Scheduled start \($0)" } ?? "")
                .accessibilityIdentifier("watch.pick.\(game.id)")
                .onAppear { WatchTelemetry.shared.content(.picker) }
            }

            if !otherPickerGames.isEmpty {
                pickerRefreshButton
            }

            Button {
                showingPickerDetails.toggle()
            } label: {
                HStack {
                    Text("About this list").font(.footnote)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    Image(systemName: showingPickerDetails ? "chevron.up" : "chevron.down")
                        .font(.footnote)
                }
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .accessibilityValue(showingPickerDetails ? "Expanded" : "Collapsed")
            .accessibilityIdentifier("watch.picker-info")
            if showingPickerDetails {
                VStack(alignment: .leading, spacing: 8) {
                    if let error = picker.errorMessage {
                        Text(error).accessibilityIdentifier("watch.picker-error")
                        if !picker.games.isEmpty { Text("Showing the previously received list.") }
                    } else if picker.games.isEmpty {
                        Text(picker.omittedGameCount > 0
                             ? "Game details are unavailable. Refresh to try again."
                             : "No games available in Discover right now.")
                    }
                    Text("Games from Discover · not the full schedule")
                    if picker.omittedGameCount > 0 {
                        Text("Some games have unavailable details.")
                    }
                    if store.selectedEventID != nil {
                        Text("Your game stays selected even when missing here.")
                            .accessibilityLabel("Your current game stays selected even when it is not in this list.")
                    }
                }
                .font(.footnote).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("watch.picker-details")
            }
        }
    }

    private var pickerRefreshButton: some View {
        Button {
            WatchTelemetry.shared.action(.refresh, surface: .picker)
            if choosingGame { gamesRefreshGeneration += 1 }
            else { refreshGeneration += 1 }
        } label: {
            Label(picker.isLoading ? "Updating games…" : "Refresh games", systemImage: "arrow.clockwise")
                .font(.footnote.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .disabled(picker.isLoading || scenePhase != .active)
        .accessibilityIdentifier("watch.picker-refresh")
    }

    private func pickerTeamColor(_ raw: String?) -> Color? {
        guard let raw else { return nil }
        let hex = raw.hasPrefix("#") ? String(raw.dropFirst()) : raw
        guard hex.count == 6, hex.allSatisfy({ $0.isHexDigit && $0.isASCII }) else { return nil }
        return Color(hex: hex)
    }

    @ViewBuilder
    private func pickerMatchup(away: String, home: String, metadata: WatchFeedEvent?) -> some View {
        let awayColor = pickerTeamColor(metadata?.awayTeamData?.primaryColor)
        let homeColor = pickerTeamColor(metadata?.homeTeamData?.primaryColor)
        if awayColor != nil || homeColor != nil {
            VStack(alignment: .leading, spacing: 2) {
                pickerTeamName(away, color: awayColor)
                pickerTeamName("at " + home, color: homeColor)
            }
        } else {
            Text("\(away) at \(home)")
                .font(.footnote.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func pickerTeamName(_ name: String, color: Color?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            if let color {
                Circle().fill(color)
                    .overlay(Circle().stroke(Color.white.opacity(0.45), lineWidth: 0.5))
                    .frame(width: 6, height: 6)
                    .accessibilityHidden(true)
            }
            Text(name).font(.footnote.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func pickerScheduledStart(_ game: WatchFeedEvent) -> String? {
        guard game.status?.lowercased() == "scheduled",
              let raw = game.commenceTime, let start = WatchFeedFutures.isoDate(raw) else { return nil }
        return start.formatted(.dateTime.month().day().hour().minute())
    }

    private func pickerScorePreview(_ game: WatchFeedEvent) -> (visual: String, spoken: String)? {
        guard game.status?.lowercased() == "live",
              let rawAway = game.awayTeam, let rawHome = game.homeTeam,
              let awayScore = game.awayScore, let homeScore = game.homeScore,
              awayScore >= 0, homeScore >= 0 else { return nil }
        let away = rawAway.trimmingCharacters(in: .whitespacesAndNewlines)
        let home = rawHome.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !away.isEmpty, !home.isEmpty else { return nil }
        // Feed rows provide no score observation clock. Do not borrow detail time.
        return ("\(away) \(awayScore)\n\(home) \(homeScore)",
                "\(away) \(awayScore). \(home) \(homeScore). Score observation time unavailable.")
    }

    private func pickerChoiceAccessibility(_ game: WatchFeedEvent) -> String {
        let state = WatchSelectedGame.stateLabel(for: game.status)
        if let preview = pickerScorePreview(game) { return "\(preview.spoken) \(state)" }
        return "\(game.awayTeam ?? "Away team") at \(game.homeTeam ?? "Home team"). \(state)"
    }

    private func currentPickerGame(_ game: WatchSelectedGame) -> some View {
        // A missing/partial list cannot erase the retained reading. When the feed
        // returns its proven alias, preserve that row's control identity.
        let rowID = picker.games.first { store.isSelected(eventID: $0.id) }?.id ?? game.id
        let now = Date()
        let observed = game.showsForecast ? game.probabilityObservedAt : game.scoreObservedAt
        let clockName = game.showsForecast ? "Probability" : "Score"
        let age = WatchObservationAge(observedAt: observed, now: now)
        let reading = currentPickerReading(game)
        let compactUnavailable = dynamicTypeSize.isAccessibilitySize && game.status == nil && game.homeProbabilityText == nil
        return Button {
            WatchTelemetry.shared.action(.reselectGame, surface: .picker)
            store.select(eventID: rowID)
            choosingGame = false
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Group {
                    if dynamicTypeSize.isAccessibilitySize && store.isRestoredReading {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text("Saved · \(game.stateLabel)").foregroundStyle(.orange)
                                Spacer(minLength: 4)
                                Text("Return").foregroundStyle(.primary)
                            }
                            .fixedSize(horizontal: true, vertical: false)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Saved · \(game.stateLabel)").foregroundStyle(.orange)
                                Label("Return", systemImage: "arrow.uturn.backward").foregroundStyle(.primary)
                            }
                            .fixedSize(horizontal: false, vertical: true)
                        }
                    } else if dynamicTypeSize.isAccessibilitySize {
                        ViewThatFits(in: .horizontal) {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text(compactUnavailable ? "State unavailable" : game.stateLabel)
                                    .fixedSize(horizontal: true, vertical: false)
                                Spacer(minLength: 4)
                                Label("Return", systemImage: "arrow.uturn.backward").foregroundStyle(.primary)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text(compactUnavailable ? "State unavailable" : game.stateLabel)
                                    .fixedSize(horizontal: true, vertical: false)
                                Spacer(minLength: 4)
                                Text("Return").foregroundStyle(.primary)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(compactUnavailable ? "State unavailable" : game.stateLabel)
                                Label("Return", systemImage: "arrow.uturn.backward").foregroundStyle(.primary)
                            }
                            .fixedSize(horizontal: false, vertical: true)
                        }
                    } else {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Label(store.isRestoredReading ? "Saved · \(game.stateLabel)" : game.stateLabel,
                                  systemImage: "checkmark")
                                .foregroundStyle(store.isRestoredReading ? Color.orange : Color.secondary)
                            Spacer(minLength: 4)
                            Label("Return", systemImage: "arrow.uturn.backward").foregroundStyle(.primary)
                        }
                    }
                }
                .font(.footnote).foregroundStyle(.secondary)
                if game.status?.lowercased() == "scheduled", let start = game.commenceTime {
                    Text(start, format: .dateTime.month().day().hour().minute())
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pick-start.\(rowID)")
                }
                if !dynamicTypeSize.isAccessibilitySize || !game.showsForecast || game.homeProbabilityText == nil {
                    pickerMatchup(away: game.awayTeam, home: game.homeTeam,
                                  metadata: picker.games.first { store.isSelected(eventID: $0.id) })
                }
                if game.showsForecast, let probability = game.homeProbabilityText {
                    Text("\(game.homeTeam) win probability")
                        .font(.footnote)
                        .fixedSize(horizontal: false, vertical: true)
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(probability).font(.title2.bold()).monospacedDigit()
                            Text(age.compactText.map {
                                $0 + (game.isLive && age.isStale ? " · stale" : "")
                            } ?? "Observation time unavailable")
                                .font(.footnote).foregroundStyle(.secondary)
                        }
                        .fixedSize(horizontal: true, vertical: false)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(probability).font(.title2.bold()).monospacedDigit()
                            Text(age.compactText.map {
                                $0 + (game.isLive && age.isStale ? " · stale" : "")
                            } ?? "Observation time unavailable")
                                .font(.footnote).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                } else {
                    Text(compactUnavailable ? "Probability unavailable" : reading).font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if dynamicTypeSize.isAccessibilitySize && game.showsForecast && game.homeProbabilityText != nil {
                    pickerMatchup(away: game.awayTeam, home: game.homeTeam,
                                  metadata: picker.games.first { store.isSelected(eventID: $0.id) })
                }
                if !game.showsForecast || game.homeProbabilityText == nil {
                    Text(age.compactText.map {
                        "\(clockName) observed \($0)" + (game.isLive && age.isStale ? " · stale" : "")
                    } ?? (compactUnavailable ? "Observation time unavailable" : "\(clockName) observation time unavailable"))
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if store.isRestoredReading {
                    Text("Refresh to confirm")
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(game.awayTeam) at \(game.homeTeam). \(game.stateLabel). Your game")
        .accessibilityValue([store.isRestoredReading ? "Saved reading. Refresh to confirm." : nil,
                             game.status?.lowercased() == "scheduled" ? game.commenceTime.map {
                                 "Scheduled start " + $0.formatted(.dateTime.month().day().hour().minute())
                             } : nil,
                             reading, age.spokenText.map { "\(clockName) observed \($0)" } ?? "\(clockName) observation time unavailable",
                             game.isLive && age.isStale ? "Stale \(clockName.lowercased())." : nil]
            .compactMap { $0 }.joined(separator: " "))
        .accessibilityAddTraits(.isSelected)
        .accessibilityIdentifier("watch.pick.\(rowID)")
        .accessibilityHint("Returns to your current game without changing the selection.")
        .onAppear { WatchTelemetry.shared.content(.picker) }
    }

    private func currentPickerReading(_ game: WatchSelectedGame) -> String {
        if game.showsForecast {
            return game.homeProbabilityText.map { "\(game.homeTeam) win probability, \($0)" }
                ?? "Win probability unavailable"
        }
        guard let away = game.awayScore, let home = game.homeScore, away >= 0, home >= 0 else {
            return game.isFinal ? "Final score unavailable" : "Last reported score unavailable"
        }
        return "\(game.isFinal ? "Final score" : "Last reported score") · \(away)–\(home)"
    }

}

private struct WatchPickerHeading: View {
    let hasSelection: Bool
    #if DEBUG
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    #endif

    var body: some View {
        Text(hasSelection ? "Current game" : "Choose your game")
            .font(.headline)
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier("watch.picker-heading")
            #if DEBUG
            // Read the heading's own environment, including a presented sheet.
            .accessibilityValue(WatchUIFixture.current == nil ? "" : String(describing: dynamicTypeSize))
            #endif
    }
}

/// Measure the complete native text before choosing a side-by-side metric.
/// A subject needing more than two lines gets the full width; no text is clipped.
private struct WatchProbabilityMetricLayout: Layout {
    let horizontalAllowed: Bool
    private let spacing: CGFloat = 8

    private struct Arrangement {
        let horizontal: Bool
        let number: CGSize
        let subject: CGSize
        let size: CGSize
    }

    private func arrangement(_ proposal: ProposedViewSize, _ subviews: Subviews) -> Arrangement {
        guard subviews.count == 2 else {
            return Arrangement(horizontal: false, number: .zero, subject: .zero, size: .zero)
        }
        let number = subviews[0].sizeThatFits(.unspecified)
        let intrinsicSubject = subviews[1].sizeThatFits(.unspecified)
        let width = proposal.width ?? max(number.width, intrinsicSubject.width)
        let remaining = max(0, width - number.width - spacing)
        let beside = subviews[1].sizeThatFits(ProposedViewSize(width: remaining, height: nil))
        let fits = horizontalAllowed && remaining > 0
            && beside.width <= remaining + 0.5
            && beside.height <= intrinsicSubject.height * 2 + 0.5
        if fits {
            return Arrangement(horizontal: true, number: number, subject: beside,
                               size: CGSize(width: width, height: max(number.height, beside.height)))
        }
        let below = subviews[1].sizeThatFits(ProposedViewSize(width: width, height: nil))
        return Arrangement(horizontal: false, number: number, subject: below,
                           size: CGSize(width: width, height: number.height + 2 + below.height))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrangement(proposal, subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let fit = arrangement(ProposedViewSize(width: bounds.width, height: nil), subviews)
        let numberY = fit.horizontal ? bounds.minY + (fit.size.height - fit.number.height) / 2 : bounds.minY
        subviews[0].place(at: CGPoint(x: bounds.minX, y: numberY), anchor: .topLeading,
                          proposal: ProposedViewSize(fit.number))
        let subjectX = fit.horizontal ? bounds.minX + fit.number.width + spacing : bounds.minX
        let subjectY = fit.horizontal ? bounds.minY + (fit.size.height - fit.subject.height) / 2
                                     : bounds.minY + fit.number.height + 2
        subviews[1].place(at: CGPoint(x: subjectX, y: subjectY), anchor: .topLeading,
                          proposal: ProposedViewSize(fit.subject))
    }
}
