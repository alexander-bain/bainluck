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
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text("\(game.away) at \(game.home)")
                                        Text(WatchSelectedGame.stateLabel(for: game.status)).font(.footnote)
                                        if let raw = game.scheduledStart, let date = WatchFeedFutures.isoDate(raw) {
                                            Text(date, format: .dateTime.month().day().hour().minute()).font(.footnote)
                                        }
                                    }.fixedSize(horizontal: false, vertical: true)
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
