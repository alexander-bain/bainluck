import SwiftUI

/// Inline server-ordered stories below the retained game. The parent owns Handoff arbitration.
struct WatchDiscoverStoriesView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var discoveries: WatchDiscoveryStore
    let isActive: Bool
    @Binding var continuation: StoryContinuationDestination?
    @State private var continuationQuestion: String?
    @State private var showingContinuationHelp = false
    @State private var manualRefresh: Task<Void, Never>?

    private var visibleReadings: [WatchDiscoveryReading] {
        discoveries.visibleReadings()
    }

    private var canInteract: Bool { isActive && scenePhase == .active }

    init(isActive: Bool, continuation: Binding<StoryContinuationDestination?>) {
        self.isActive = isActive
        self._continuation = continuation
        #if DEBUG
        if let fixture = WatchUIFixture.current {
            _discoveries = StateObject(wrappedValue: fixture.makeDiscoveryStore())
            return
        }
        #endif
        _discoveries = StateObject(wrappedValue: WatchDiscoveryStore())
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Discoveries")
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("watch.discovery.heading")
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
            #if DEBUG
            if WatchUIFixture.current != nil, let continuation,
               let url = StoryContinuation.url(for: continuation) {
                Text(url.absoluteString)
                    .font(.footnote)
                    .accessibilityIdentifier("watch.discovery.continuation")
            }
            #endif
        }
        .onAppear {
            discoveries.telemetry = { outcome, ms, count in
                WatchTelemetry.shared.refreshResult(.discoveries, outcome: outcome, durationMS: ms, count: count)
            }
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
        .task(id: canInteract) {
            guard canInteract else { return }
            await discoveries.refresh()
        }
        .onChange(of: canInteract) { _, active in
            if !active {
                manualRefresh?.cancel()
                manualRefresh = nil
                discoveries.cancelRefresh()
                clearContinuation()
            }
        }
        .onChange(of: continuation) { _, destination in
            if destination == nil {
                continuationQuestion = nil
                showingContinuationHelp = false
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
                      element: canInteract ? continuation : nil) { destination, activity in
            StoryContinuation.configure(activity, destination: destination)
        }
        .alert("Continue on iPhone", isPresented: $showingContinuationHelp) {
            Button("OK", role: .cancel) { WatchTelemetry.shared.action(.dismissHelp, surface: .discoveries) }
        } message: {
            Text("\(continuationQuestion ?? "This story")\nLook for Bain Luck’s Handoff option in your iPhone’s App Switcher. Your iPhone needs a version with story Handoff support, and both devices need Handoff enabled and the same Apple Account. If it isn’t available, the story stays here.")
        }
    }

    private var discoveryRecovery: some View {
        VStack(alignment: .leading, spacing: 6) {
            if discoveries.isSavedReading && !discoveries.readings.isEmpty {
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
            .disabled(discoveries.isRefreshing || !canInteract)
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
            Button("Continue on iPhone") {
                WatchTelemetry.shared.action(.phoneContinuation, surface: .discoveries)
                continuation = .futures(reading.id)
                continuationQuestion = reading.question
                showingContinuationHelp = true
            }
            .disabled(!canInteract)
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
