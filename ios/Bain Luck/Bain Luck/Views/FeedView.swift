import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "feed")

// MARK: - ViewModel

final class FeedViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var total = 0
    @Published var loading = true
    @Published var error: String?

    private var refreshTimer: Timer?

    var liveNow: [FeedItem] {
        items.filter { $0.event?.status == "live" }
    }

    var justHappened: [FeedItem] {
        items.filter {
            let s = $0.event?.status
            return s == "completed" || s == "closed"
        }
    }

    var upcoming: [FeedItem] {
        items.filter {
            guard $0.type == "event" else { return false }
            let s = $0.event?.status
            return s == "scheduled" || s == nil
        }
    }

    var topMarkets: [FeedItem] {
        items.filter { $0.type == "futures" }
    }

    var hasLiveGames: Bool { !liveNow.isEmpty }

    @MainActor
    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            let feed = try await APIClient.shared.fetchFeed(limit: 200)
            items = feed.items
            total = feed.total
            error = nil
            loading = false
            logger.info("Feed loaded: \(feed.items.count) items")
            configureAutoRefresh()
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("Feed error: \(error)")
        }
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard hasLiveGames else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}

// MARK: - View

struct FeedView: View {
    @StateObject private var vm = FeedViewModel()
    @State private var path = NavigationPath()
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @EnvironmentObject var pinManager: PinManager

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if vm.loading {
                    ProgressView("Loading feed...")
                } else if let error = vm.error, vm.items.isEmpty {
                    ContentUnavailableView(
                        "Couldn't Load Feed",
                        systemImage: "wifi.exclamationmark",
                        description: Text(error)
                    )
                } else {
                    feedList
                }
            }
            .navigationTitle("Bain Luck")
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                case .eiRankings:
                    EIRankingsView()
                case .preferences:
                    EmptyView()
                }
            }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "feed", type: "feed")
        }
        .task {
            await vm.load()
        }
        .onDisappear {
            vm.stopRefresh()
        }
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
            if navCoordinator.selectedTab == .feed,
               let route = navCoordinator.consumeRoute() {
                path.append(route)
            }
        }
    }

    // MARK: - Feed List

    private var pinnedItems: [FeedItem] {
        vm.items.filter { item in
            if item.type == "event", let event = item.event {
                return pinManager.pinnedEventIDs.contains(event.id)
            } else if item.type == "futures", let futures = item.futures {
                return pinManager.pinnedFuturesIDs.contains(futures.id)
            }
            return false
        }
    }

    private var feedList: some View {
        List {
            if !pinnedItems.isEmpty {
                feedSection(title: "Pinned", systemImage: "bookmark.fill", imageColor: .orange, items: pinnedItems)
            }
            if !vm.liveNow.isEmpty {
                feedSection(title: "Live Now", systemImage: "circle.fill", imageColor: .red, items: vm.liveNow)
            }
            if !vm.justHappened.isEmpty {
                feedSection(title: "Just Happened", systemImage: "clock.arrow.circlepath", imageColor: .secondary, items: vm.justHappened)
            }
            if !vm.upcoming.isEmpty {
                feedSection(title: "Upcoming", systemImage: "calendar", imageColor: .blue, items: vm.upcoming)
            }
            if !vm.topMarkets.isEmpty {
                feedSection(title: "Top Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: vm.topMarkets)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Section Builder

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            ForEach(items) { item in
                feedRow(item)
            }
        } header: {
            HStack(spacing: 6) {
                Label(title, systemImage: systemImage)
                    .foregroundStyle(imageColor)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .textCase(nil)
                Text("\(items.count)")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    // MARK: - Row

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let event = item.event {
            Button {
                AnalyticsService.trackEventCardClick(eventId: event.id, sport: event.sport, status: event.status)
                path.append(Route.eventDetail(id: event.id))
            } label: {
                EventCardView(
                    event: event,
                    reason: item.reason,
                    personalizationReasons: item.personalizationReasons,
                    headline: item.headline
                )
            }
            .buttonStyle(.plain)
        } else if item.type == "futures", let futures = item.futures {
            Button {
                path.append(Route.futuresDetail(id: futures.id))
            } label: {
                FuturesCardView(futures: futures)
            }
            .buttonStyle(.plain)
        }
    }
}
