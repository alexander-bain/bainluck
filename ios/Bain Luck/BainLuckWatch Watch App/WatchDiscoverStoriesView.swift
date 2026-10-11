import SwiftUI

/// Server-ordered discoveries alongside the retained game; no new selection owner.
struct WatchDiscoverStoriesView: View {
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ObservedObject var selected: WatchSelectedGameStore
    @StateObject private var discoveries: WatchDiscoveryStore
    let close: () -> Void
    @State private var continuation: StoryContinuationDestination?
    @State private var continuationQuestion: String?
    @State private var showingContinuationHelp = false
    @State private var manualRefresh: Task<Void, Never>?
    @State private var showingNFLWeeks = false
    @State private var showingMLBPostseason = false
    @State private var showingAwards = false
    @State private var questionDestination: WatchQuestionDetailDestination?

    private var visibleReadings: [WatchDiscoveryReading] {
        discoveries.visibleReadings(hasSelectedGame: selected.selectedEventID != nil)
    }

    init(selected: WatchSelectedGameStore, close: @escaping () -> Void) {
        self.selected = selected
        self.close = close
        #if DEBUG
        if let fixture = WatchUIFixture.current {
            _discoveries = StateObject(wrappedValue: fixture.makeDiscoveryStore())
            return
        }
        #endif
        _discoveries = StateObject(wrappedValue: WatchDiscoveryStore())
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if dynamicTypeSize.isAccessibilitySize {
                    Text("Discoveries")
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("watch.discovery.heading")
                }
                if selected.selectedEventID != nil {
                    selectedSummary
                    if !visibleReadings.isEmpty {
                        Divider()
                            .accessibilityIdentifier("watch.discovery.separator.selected")
                    }
                }
                if visibleReadings.isEmpty {
                    discoveryRecovery
                }
                ForEach(visibleReadings) { reading in
                    if reading.id != visibleReadings.first?.id {
                        Divider()
                            .accessibilityIdentifier("watch.discovery.separator.before.\(reading.id)")
                    }
                    storyCard(reading)
                }
                if !visibleReadings.isEmpty {
                    discoveryRecovery
                }
                Button("Browse NFL weeks") { showingNFLWeeks = true }
                    .disabled(scenePhase != .active)
                    .accessibilityIdentifier("watch.discovery.browse-nfl")
                Button("Browse MLB postseason") { showingMLBPostseason = true }
                    .disabled(scenePhase != .active)
                    .accessibilityIdentifier("watch.discovery.browse-mlb")
                Button("Browse awards") { showingAwards = true }
                    .disabled(scenePhase != .active)
                    .accessibilityIdentifier("watch.discovery.browse-awards")
                #if DEBUG
                if WatchUIFixture.current != nil, let continuation,
                   let url = StoryContinuation.url(for: continuation) {
                    Text(url.absoluteString)
                        .font(.footnote)
                        .accessibilityIdentifier("watch.discovery.continuation")
                }
                #endif
            }
            .padding(.horizontal, 6)
        }
        .sheet(item: $questionDestination) { destination in
            WatchQuestionDetailView(destination: destination, close: { questionDestination = nil })
        }
        .sheet(isPresented: $showingAwards) {
            WatchAwardsView(close: { showingAwards = false })
        }
        .sheet(isPresented: $showingMLBPostseason) {
            WatchMLBCollectionView(selected: selected,
                close: { showingMLBPostseason = false },
                selectedGame: { showingMLBPostseason = false; close() })
        }
        .sheet(isPresented: $showingNFLWeeks) {
            WatchNFLCollectionView(selected: selected,
                close: { showingNFLWeeks = false },
                selectedGame: { showingNFLWeeks = false; close() })
        }
        .onAppear {
            discoveries.telemetry = { outcome, ms, count in
                WatchTelemetry.shared.refreshResult(.discoveries, outcome: outcome, durationMS: ms, count: count)
            }
            WatchTelemetry.shared.screen(.discoveries)
            WatchTelemetry.shared.reading(.discoveries, fetchedAt: discoveries.fetchedAt,
                                          saved: discoveries.isSavedReading, count: visibleReadings.count)
        }
        .onChange(of: discoveries.fetchedAt) { _, _ in
            WatchTelemetry.shared.reading(.discoveries, fetchedAt: discoveries.fetchedAt, saved: discoveries.isSavedReading, count: visibleReadings.count)
        }
        .onChange(of: discoveries.isSavedReading) { _, _ in
            WatchTelemetry.shared.reading(.discoveries, fetchedAt: discoveries.fetchedAt,
                                          saved: discoveries.isSavedReading, count: visibleReadings.count)
        }
        .accessibilityIdentifier("watch.discovery.list")
        .navigationTitle(dynamicTypeSize.isAccessibilitySize ? "" : "Discoveries")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button(selected.selectedEventID == nil ? "Games" : "Your game") {
                    WatchTelemetry.shared.action(.close, surface: .discoveries)
                    close()
                }
                    .accessibilityLabel(selected.selectedEventID == nil ? "Back to choosing a game" : "Your game")
                    .accessibilityIdentifier("watch.discovery.close")
            }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await discoveries.refresh()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                manualRefresh?.cancel()
                manualRefresh = nil
                discoveries.cancelRefresh()
                clearContinuation()
            }
        }
        .onDisappear {
            manualRefresh?.cancel()
            manualRefresh = nil
            discoveries.cancelRefresh()
            clearContinuation()
        }
        .onChange(of: visibleReadings.map(\.id)) { _, ids in
            if case .some(.futures(let id)) = continuation, !ids.contains(id) {
                clearContinuation()
            }
        }
        .userActivity(StoryContinuation.activityType,
                      element: scenePhase == .active ? continuation : nil) { destination, activity in
            StoryContinuation.configure(activity, destination: destination)
        }
        .alert("Continue on iPhone", isPresented: $showingContinuationHelp) {
            Button("OK", role: .cancel) { WatchTelemetry.shared.action(.dismissHelp, surface: .discoveries) }
        } message: {
            Text("\(continuationQuestion ?? "This story")\nLook for Bain Luck’s Handoff option in your iPhone’s App Switcher. Your iPhone needs a version with story Handoff support, and both devices need Handoff enabled and the same Apple Account. If it isn’t available, the story stays here.")
        }
        .onOpenURL { url in
            if WatchLaunchRoute.accepts(url) { close() }
        }
    }

    private var discoveryRecovery: some View {
        VStack(alignment: .leading, spacing: 6) {
            if discoveries.isSavedReading {
                Text("Saved stories · refresh to confirm")
                    .font(.footnote).foregroundStyle(.secondary)
                    .accessibilityIdentifier("watch.discovery.saved")
            }
            if let error = discoveries.errorMessage {
                Text(error).font(.footnote).foregroundStyle(.secondary)
                    .accessibilityIdentifier("watch.discovery.error")
                if !discoveries.readings.isEmpty {
                    Text("Showing the last received stories.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            if discoveries.readings.isEmpty {
                if discoveries.isRefreshing {
                    ProgressView("Loading discoveries")
                } else if discoveries.errorMessage == nil {
                    Text("No discoveries right now")
                        .font(.headline)
                    Text("Refresh to try again.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Button(discoveries.isRefreshing ? "Refreshing…" : "Refresh discoveries") {
                WatchTelemetry.shared.action(.refresh, surface: .discoveries)
                manualRefresh?.cancel()
                manualRefresh = Task { await discoveries.refresh() }
            }
            .disabled(discoveries.isRefreshing || scenePhase != .active)
            .accessibilityIdentifier("watch.discovery.refresh")
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("watch.discovery.recovery")
    }

    private func clearContinuation() {
        continuation = nil
        continuationQuestion = nil
        showingContinuationHelp = false
    }

    private var selectedSummary: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Your game").font(.headline)
            if let game = selected.game {
                Text("\(game.awayTeam) at \(game.homeTeam)")
                    .font(.headline).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.discovery.selected-matchup")
                if selected.isRestoredReading {
                    Text("Saved reading · refresh to confirm")
                        .font(.footnote).foregroundStyle(.orange)
                }
                Text(game.stateLabel).font(.subheadline.bold())
                if game.showsForecast {
                    Text(game.homeProbabilityText.map { "\(game.homeTeam) win · \($0)" }
                         ?? "Win probability unavailable")
                        .font(.body.bold()).fixedSize(horizontal: false, vertical: true)
                } else if game.isFinal, let away = game.awayScore, let home = game.homeScore {
                    Text("Final · \(game.awayTeam) \(away), \(game.homeTeam) \(home)")
                        .font(.body.bold()).fixedSize(horizontal: false, vertical: true)
                } else {
                    Text(game.isClosed ? "Final result unverified" : "Final score unavailable")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                TimelineView(.periodic(from: .now, by: 15)) { context in
                    let observed = game.showsForecast ? game.probabilityObservedAt : game.scoreObservedAt
                    let age = WatchObservationAge(observedAt: observed, now: context.date)
                    Text(age.compactText.map { "Observed \($0)" } ?? "Observation time unavailable")
                        .font(.footnote).foregroundStyle(.secondary)
                        .accessibilityLabel(age.spokenText.map { "Observed \($0)" } ?? "Observation time unavailable")
                    if game.isLive && age.isStale {
                        Text("Stale reading · waiting for a newer observation")
                            .font(.footnote).foregroundStyle(.orange)
                    }
                }
                if let error = selected.errorMessage {
                    Text(error).font(.footnote).foregroundStyle(.orange)
                }
            } else {
                Text("Selected game unavailable").font(.body.bold())
                Text("Your selection is retained.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Button("Back to your game") {
                WatchTelemetry.shared.action(.close, surface: .discoveries)
                close()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("watch.discovery.selected")
    }

    private func storyCard(_ reading: WatchDiscoveryReading) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(reading.question)
                .font(.headline).fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.discovery.question.\(reading.id)")
            TimelineView(.periodic(from: .now, by: 15)) { context in
                let display = WatchDiscoveryCardPresentation(reading: reading, now: context.date)
                if let result = display.result {
                    Text(result).font(.body.bold()).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.discovery.result.\(reading.id)")
                } else if let outcome = display.outcome, let probability = display.probability {
                    Text("\(outcome) · \(probability)").font(.title3.bold())
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel("\(outcome), reported probability \(probability)")
                        .accessibilityIdentifier("watch.discovery.probability.\(reading.id)")
                } else {
                    Text("Probability unavailable").font(.footnote).foregroundStyle(.secondary)
                }
                Text(display.observation).font(.footnote).foregroundStyle(.secondary)
                    .accessibilityLabel(display.spokenObservation)
                    .accessibilityValue(display.observationValue)
                    .accessibilityIdentifier("watch.discovery.age.\(reading.id)")
            }
            Button("Read full question") {
                questionDestination = WatchQuestionDetailDestination(id: reading.id, question: reading.question)
            }
            .disabled(scenePhase != .active)
            .accessibilityIdentifier("watch.discovery.read-question.\(reading.id)")
            Button("Continue on iPhone") {
                WatchTelemetry.shared.action(.phoneContinuation, surface: .discoveries)
                continuation = .futures(reading.id)
                continuationQuestion = reading.question
                showingContinuationHelp = true
            }
            .disabled(scenePhase != .active)
            .accessibilityLabel("Continue \(reading.question) on iPhone")
            .accessibilityIdentifier("watch.discovery.continue.\(reading.id)")
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("watch.discovery.card.\(reading.id)")
        .onAppear { WatchTelemetry.shared.content(.discoveries) }
    }
}
