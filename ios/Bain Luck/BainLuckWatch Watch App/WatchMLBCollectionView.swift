import SwiftUI

struct WatchMLBCollectionView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var browser = WatchMLBCollectionStore()
    @ObservedObject var selected: WatchSelectedGameStore
    let close: () -> Void
    let selectedGame: () -> Void
    @State private var action: Task<Void, Never>?
    @State private var question: WatchQuestionDetailDestination?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let collection = browser.collection {
                    Text(collection.name).font(.headline).fixedSize(horizontal: false, vertical: true)
                    if let membership = browser.membership {
                        switch membership.availability {
                        case .unavailable:
                            Text("This collection is no longer available.")
                        case .empty:
                            Text("No available entries in this collection.")
                        case .published:
                            Text("\(membership.games.count) \(membership.games.count == 1 ? "game" : "games") available on Watch")
                                .font(.footnote)
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
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(game.away).accessibilityLabel("Away: \(game.away)")
                                        Text("at").font(.footnote)
                                        Text(game.home).accessibilityLabel("Home: \(game.home)")
                                        Text(game.stateText).font(.footnote)
                                        if let context = game.startContext { Text(context).font(.footnote) }
                                        if let date = game.scheduledStart {
                                            Text(date, format: .dateTime.year().month().day().hour().minute()).font(.footnote)
                                        }
                                    }
                                    .fixedSize(horizontal: false, vertical: true)
                                }
                                .disabled(browser.isLoading || scenePhase != .active)
                                .accessibilityIdentifier("watch.mlb.game.\(game.id)")
                            }
                            if membership.games.isEmpty { Text("No available games in this collection.") }
                            if !membership.questions.isEmpty {
                                Text("Questions").font(.headline).accessibilityAddTraits(.isHeader)
                                ForEach(membership.questions) { item in
                                    Button(item.name) {
                                        start {
                                            await browser.openQuestion(item.id,
                                                isActive: { scenePhase == .active },
                                                open: { current in
                                                    question = .init(id: current.id, question: current.name)
                                                })
                                        }
                                    }
                                    .disabled(browser.isLoading || scenePhase != .active)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(minHeight: 44)
                                    .accessibilityIdentifier("watch.mlb.question.\(item.id)")
                                }
                            }
                            if !membership.children.isEmpty {
                                Text("Related collections").font(.headline)
                                ForEach(membership.children) { child in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(child.name)
                                        Text("Not available to open on Watch").font(.footnote)
                                    }
                                    .fixedSize(horizontal: false, vertical: true)
                                    .accessibilityElement(children: .combine)
                                }
                            }
                            if membership.hasOtherEntries {
                                Text("Some collection entries aren't shown in this Watch list.").font(.footnote)
                            }
                        }
                    }
                    Button("All available MLB postseason collections") { start { await browser.browse() } }
                        .disabled(browser.isLoading || scenePhase != .active)
                } else {
                    ForEach(browser.collections) { collection in
                        Button(collection.name) { start { await browser.open(collection) } }
                            .disabled(browser.isLoading || scenePhase != .active)
                            .accessibilityIdentifier("watch.mlb.collection.\(collection.id)")
                    }
                    if !browser.isLoading && browser.errorMessage == nil && browser.collections.isEmpty {
                        Text("No available MLB postseason collections right now.")
                    }
                }
                if browser.isLoading { ProgressView("Loading MLB postseason") }
                if let error = browser.errorMessage { Text(error).font(.footnote) }
                Button("Refresh") { start { await browser.refresh() } }
                    .disabled(browser.isLoading || scenePhase != .active)
                    .accessibilityIdentifier("watch.mlb.refresh")
                Button("Back to Discoveries", action: close)
            }.padding(.horizontal, 6)
        }
        .accessibilityIdentifier("watch.mlb.browser")
        .sheet(item: $question) { destination in
            WatchQuestionDetailView(destination: destination, close: { question = nil },
                originLabel: "From your postseason collection", backLabel: "Back to postseason")
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await browser.refresh()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { action?.cancel(); browser.cancel(); question = nil }
        }
        .onDisappear { action?.cancel(); browser.cancel() }
    }
    private func start(_ operation: @escaping @MainActor () async -> Void) {
        action?.cancel()
        action = Task { await operation() }
    }
}
