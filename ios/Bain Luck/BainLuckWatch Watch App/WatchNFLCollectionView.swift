import SwiftUI

struct WatchNFLCollectionView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var browser = WatchNFLCollectionStore()
    @ObservedObject var selected: WatchSelectedGameStore
    let close: () -> Void
    let selectedGame: () -> Void
    @State private var action: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let week = browser.week {
                    Text(week.name).font(.headline).fixedSize(horizontal: false, vertical: true)
                    if let membership = browser.membership {
                        if !membership.published {
                            Text("This collection is no longer available.")
                        } else {
                            Text(WatchNFLGamePresentation.availableGamesText(membership)).font(.footnote)
                            ForEach(membership.games) { game in
                                Button {
                                    start {
                                        await browser.selectGame(game.id,
                                            isActive: { scenePhase == .active },
                                            select: { id in
                                                WatchTelemetry.shared.action(.selectGame, surface: .picker)
                                                selected.select(eventID: id)
                                                selectedGame()
                                            })
                                    }
                                } label: {
                                    WatchNFLGameRow(game: game)
                                }
                                .disabled(browser.isLoading || scenePhase != .active)
                                .accessibilityIdentifier("watch.nfl.game.\(game.id)")
                            }
                            if membership.games.isEmpty { Text("No available games in this collection.") }
                            if membership.hasOtherEntries {
                                Text("Some collection entries aren't shown in this Watch list.").font(.footnote)
                            }
                        }
                    }
                    Button("All available NFL weeks") { start { await browser.browse() } }
                        .disabled(browser.isLoading || scenePhase != .active)
                } else {
                    ForEach(browser.weeks) { week in
                        Button(week.name) { start { await browser.open(week) } }
                            .disabled(browser.isLoading || scenePhase != .active)
                            .accessibilityIdentifier("watch.nfl.week.\(week.id)")
                    }
                    if !browser.isLoading && browser.errorMessage == nil && browser.weeks.isEmpty {
                        Text("No available NFL weeks right now.")
                    }
                }
                if browser.isLoading { ProgressView("Loading NFL weeks") }
                if let error = browser.errorMessage { Text(error).font(.footnote) }
                Button("Refresh") { start { await browser.refresh() } }
                    .disabled(browser.isLoading || scenePhase != .active)
                    .accessibilityIdentifier("watch.nfl.refresh")
                Button("Back to Discoveries", action: close)
            }.padding(.horizontal, 6)
        }
        .accessibilityIdentifier("watch.nfl.browser")
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await browser.refresh()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { action?.cancel(); browser.cancel() }
        }
        .onDisappear { action?.cancel(); browser.cancel() }
    }
    private func start(_ operation: @escaping @MainActor () async -> Void) {
        action?.cancel()
        action = Task { await operation() }
    }
}

/// Full names wrap before scores; no abbreviations, winner styling or rank.
private struct WatchNFLGameRow: View {
    let game: WatchNFLGame
    var body: some View {
        let reading = WatchNFLGamePresentation(game: game, now: Date())
        VStack(alignment: .leading, spacing: 6) {
            Text(reading.stateText).font(.footnote)
            team(reading.awayName, score: reading.awayScore, role: "Away")
            team(reading.homeName, score: reading.homeScore, role: "Home")
            if let observed = reading.scoreObservedAt {
                Text("Score observed \(observed.formatted(date: .abbreviated, time: .shortened))")
                    .font(.footnote)
                    .accessibilityLabel("Score observed \(observed.formatted(date: .complete, time: .complete))")
            } else if let context = reading.scoreContext {
                Text(context).font(.footnote)
            }
            if let chance = reading.chanceText { Text(chance).font(.footnote) }
            if let context = reading.chanceContext { Text(context).font(.footnote) }
            if let date = reading.scheduledStart, let label = reading.startLabel {
                Text(label).font(.footnote)
                Text(date, format: .dateTime.month().day().hour().minute()).font(.footnote)
            }
            if let missing = reading.startMissingText { Text(missing).font(.footnote) }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }
    private func team(_ name: String, score: String?, role: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(name).fixedSize(horizontal: false, vertical: true)
                .layoutPriority(1).accessibilityLabel("\(role): \(name)")
            if let score {
                Spacer(minLength: 0)
                Text(score).monospacedDigit().font(.headline)
                    .accessibilityLabel(score == "—" ? "Score unavailable" : "Score \(score)")
            }
        }
    }
}
