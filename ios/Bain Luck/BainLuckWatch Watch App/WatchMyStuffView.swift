import Foundation
import SwiftUI

struct WatchMyStuffView: View {
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var store = WatchMyStuffStore.shared
    @ObservedObject var selected: WatchSelectedGameStore
    let close: () -> Void
    @State private var destination: WatchMyStuffSnapshot.Item?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let snapshot = store.snapshot {
                    switch snapshot.account {
                    case .signedOut:
                        Text("Sign in on your iPhone to see My Stuff here.")
                    case .connecting:
                        Text("Open Bain Luck on your iPhone to finish restoring your account.")
                    case .signedIn:
                        if store.connecting { Text("Checking with iPhone…").font(.footnote) }
                        else if !store.connected { Text("Last synced with iPhone").font(.footnote) }
                        section("Pinned", value: snapshot.pins, empty: "No pinned games or markets yet.")
                        section("Teams", value: snapshot.teams, empty: "No saved teams yet.")
                        Text("Manage pins and teams on your iPhone.").font(.footnote).foregroundStyle(.secondary)
                    }
                } else {
                    Text(store.connecting ? "Connecting to iPhone…" : "Open Bain Luck on your iPhone, then sync My Stuff.")
                    Text("Offline access expires after 24 hours without a verified phone session.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Button("Sync with iPhone") { WatchTelemetry.shared.refreshMyStuff() }
                    .disabled(store.connecting || scenePhase != .active)
                    .frame(minHeight: 44)
                Button("Back to your game", action: close).frame(minHeight: 44)
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 6)
        }
        .navigationTitle("My Stuff")
        .accessibilityIdentifier("watch.my-stuff")
        .task(id: scenePhase) {
            if scenePhase == .active { WatchTelemetry.shared.refreshMyStuff() }
        }
        .sheet(item: $destination) { item in
            NavigationStack {
                if store.contains(item) {
                    if item.kind == "future" {
                        WatchQuestionDetailView(destination: .init(id: item.targetID, question: item.title),
                            close: { destination = nil }, originLabel: "From My Stuff", backLabel: "Back to My Stuff")
                    } else if item.kind == "team" {
                        WatchMyStuffTeamView(item: item, select: { id in
                            store.select(eventID: id, from: item, in: selected)
                            destination = nil; close()
                        }, close: { destination = nil })
                    } else {
                        Text("Open this saved item in My Stuff on your iPhone.")
                        Button("Back to My Stuff") { destination = nil }
                    }
                }
            }.id(store.navigationGeneration)
        }
        .onChange(of: store.navigationGeneration) { _, _ in destination = nil }
        .onChange(of: store.snapshot) { _, _ in
            if let destination, !store.contains(destination) { self.destination = nil }
        }
    }

    private func section(_ title: String, value: WatchMyStuffSnapshot.Section, empty: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            switch value.state {
            case .loading: Text("Loading from iPhone…").font(.footnote)
            case .pending: Text("Saving on iPhone… Showing the last confirmed pins.").font(.footnote)
            case .failed: Text("Couldn't sync all changes. Showing the last confirmed items. Sync to retry.").font(.footnote)
            case .loaded:
                if value.items.isEmpty { Text(empty) }
            }
            if let time = value.syncedAt {
                (Text("Phone sync: ") + Text(time, style: .relative) + Text(" ago"))
                    .font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(value.items) { item in
                Button {
                    guard store.contains(item) else { return }
                    if item.kind == "event" {
                        store.select(eventID: item.targetID, from: item, in: selected)
                        close()
                    } else { destination = item }
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.title).font(.body)
                        if let relation = item.relationLabel { Text(relation).font(.footnote) }
                        if item.unavailable { Text("No longer listed · tap to retry").font(.footnote) }
                    }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                }
                .accessibilityIdentifier("watch.my-stuff.\(item.id)")
            }
            if value.omittedCount > 0 {
                Text("\(value.omittedCount) more on iPhone").font(.footnote)
            }
        }
    }
}

private struct WatchMyStuffTeamView: View {
    @Environment(\.scenePhase) private var scenePhase
    let item: WatchMyStuffSnapshot.Item
    let select: (Int) -> Void
    let close: () -> Void
    @State private var teamState = WatchMyStuffTeamState()
    @State private var loading = false
    @State private var refreshID = 0
    @State private var request = UUID()
    @State private var question: WatchQuestionDetailDestination?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text(teamState.page?.team.name ?? item.title).font(.headline)
                if let page = teamState.page {
                    if page.games.isEmpty { Text("No games listed for this team.") }
                    ForEach(Array(page.games.prefix(12))) { game in
                        Button("\(game.awayTeam) at \(game.homeTeam)") { select(game.id) }
                            .frame(minHeight: 44)
                    }
                    ForEach(Array(page.questions.prefix(12)), id: \.marketId) { market in
                        Button(market.marketName) {
                            question = .init(id: market.marketId, question: market.marketName)
                        }.frame(minHeight: 44)
                    }
                    if page.games.count > 12 || page.questions.count > 12 {
                        Text("More on your iPhone").font(.footnote)
                    }
                }
                if loading { ProgressView("Loading team") }
                if let error = teamState.error { Text(error) }
                Button("Refresh") { refreshID += 1 }.disabled(loading || scenePhase != .active)
                Button("Back to My Stuff", action: close)
            }.fixedSize(horizontal: false, vertical: true).padding(.horizontal, 6)
        }
        .task(id: "\(item.id):\(scenePhase):\(refreshID)") {
            guard scenePhase == .active else { return }
            let accountGeneration = WatchMyStuffStore.shared.navigationGeneration
            let token = UUID(); request = token; loading = true
            teamState.beginRefresh(); question = nil
            defer { if request == token { loading = false } }
            do {
                var urlRequest = URLRequest(url: URL(string: "https://api.bainluck.com/api/teams/\(item.targetID)")!)
                urlRequest.timeoutInterval = 15
                urlRequest.cachePolicy = .reloadIgnoringLocalCacheData
                let (data, response) = try await URLSession.shared.data(for: urlRequest)
                try Task.checkCancellation()
                guard request == token, WatchMyStuffStore.shared.navigationGeneration == accountGeneration,
                      WatchMyStuffStore.shared.contains(item) else { return }
                guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
                guard http.statusCode == 200 else {
                    teamState.fail([404, 410].contains(http.statusCode)
                        ? "This team is no longer listed. Your other saved items are still available."
                        : "Couldn't refresh this team. Try again.")
                    return
                }
                teamState.receive(data, expectedTeamID: item.targetID)
            } catch {
                guard request == token, !Task.isCancelled else { return }
                teamState.fail("Couldn't refresh this team. Try again.")
            }
        }
        .onDisappear { request = UUID(); question = nil }
        .sheet(item: $question) { value in
            WatchQuestionDetailView(destination: value, close: { question = nil },
                originLabel: "From your team", backLabel: "Back to team")
        }
    }
}
