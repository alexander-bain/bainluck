import SwiftUI
import Combine
import os
#if canImport(UIKit)
import UIKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "feed")

// MARK: - ViewModel

final class FeedViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var groupedItems: [GroupedFeedItem] = []
    @Published var total = 0
    @Published var loading = true
    @Published var error: String?
    @Published var liveCount = 0

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
            // Fetch both feeds in parallel
            async let feedTask = APIClient.shared.fetchFeed()
            async let groupedTask = APIClient.shared.fetchGroupedFeed(limit: 20)
            
            let feed = try await feedTask
            items = feed.items
            total = feed.total
            
            // Grouped feed is optional — don't fail if it errors
            if let grouped = try? await groupedTask {
                groupedItems = grouped.feed
                logger.info("Grouped feed loaded: \(grouped.feed.count) items")
            }
            
            error = nil
            loading = false
            liveCount = liveNow.count
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

    // MARK: - Filtered accessors

    func filteredItems(for categoryID: String) -> [FeedItem] {
        guard categoryID != "all" else { return items }
        guard let category = sportCategories.first(where: { $0.id == categoryID }) else { return items }
        return items.filter { category.matches($0) }
    }

    func filteredLiveNow(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter { $0.event?.status == "live" }
    }

    func filteredJustHappened(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter {
            let s = $0.event?.status
            return s == "completed" || s == "closed"
        }
    }

    func filteredUpcoming(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter {
            guard $0.type == "event" else { return false }
            let s = $0.event?.status
            return s == "scheduled" || s == nil
        }
    }

    func filteredTopMarkets(for categoryID: String) -> [FeedItem] {
        filteredItems(for: categoryID).filter { $0.type == "futures" }
    }
}

// MARK: - View

struct FeedView: View {
    @StateObject private var vm = FeedViewModel()
    @State private var path = NavigationPath()
    @State private var selectedCategory: String = "all"
    @State private var landscapeColumns = false
    @State private var hoveredItemId: String?
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @EnvironmentObject var pinManager: PinManager
    @Environment(\.horizontalSizeClass) private var sizeClass
    #if os(macOS)
    @Environment(\.openWindow) private var openWindow
    #endif

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if vm.loading {
                    SkeletonFeedView()
                } else if let error = vm.error, vm.items.isEmpty {
                    VStack(spacing: 16) {
                        Spacer()
                        Image(systemName: "wifi.exclamationmark")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary.opacity(0.5))
                        Text("Couldn't Load Feed")
                            .font(.title3)
                            .fontWeight(.semibold)
                        Text(error)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                        Button("Try Again") {
                            Task { await vm.load() }
                        }
                        .buttonStyle(.borderedProminent)
                        Spacer()
                    }
                    .padding(.horizontal, 40)
                } else {
                    feedList
                }
            }
            .navigationTitle("🍀 Bain Luck")
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                case .eiRankings:
                    EIRankingsView()
                case .preferences:
                    PreferencesView()
                case .sportCategory(let key, let name):
                    SportCategoryView(categoryKey: key, categoryName: name)
                case .leagueGrid(let slug):
                    LeagueGridView(slug: slug)
                case .golfCategory:
                    GolfCategoryView()
                case .golfLeaderboard:
                    MastersLiveView()
                case .golfTournament(_, let name):
                    SportCategoryView(categoryKey: "golf", categoryName: name)
                case .futuresList:
                    FuturesListView()
                case .teamDetail(_):
                    Text("Team")
                case .predictionStats:
                    PredictionStatsView()
                }
            }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "feed", type: "feed")
            updateLandscapeColumns()
        }
        .task {
            await vm.load()
        }
        .onDisappear {
            vm.stopRefresh()
        }
        #if os(iOS)
        .onReceive(NotificationCenter.default.publisher(for: UIDevice.orientationDidChangeNotification)) { _ in
            updateLandscapeColumns()
        }
        #endif
        .onChange(of: vm.liveCount) { _, count in
            navCoordinator.liveGameCount = count
        }
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
            if navCoordinator.selectedTab == .feed,
               let route = navCoordinator.consumeRoute() {
                path.append(route)
            }
        }
    }

    // MARK: - Feed List

    // MARK: - iPad Grid

    private var iPadGridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 340), spacing: 12)]
    }

    private func updateLandscapeColumns() {
        guard sizeClass == .regular else { return }
        #if os(iOS)
        let bounds = UIScreen.main.bounds
        landscapeColumns = bounds.width > bounds.height
        #else
        landscapeColumns = true
        #endif
    }

    private var pinnedItems: [FeedItem] {
        vm.filteredItems(for: selectedCategory).filter { item in
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
            // Category chips — navigate to sport category pages
            Section {
                SportFilterChips(selectedCategory: $selectedCategory) { category in
                    path.append(Route.sportCategory(key: category.id, name: category.name))
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }

            if !pinnedItems.isEmpty {
                feedSection(title: "Pinned", systemImage: "bookmark.fill", imageColor: .orange, items: pinnedItems)
            }

            let live = vm.filteredLiveNow(for: selectedCategory)
            if !live.isEmpty {
                feedSection(title: "Live Now", systemImage: "circle.fill", imageColor: .red, items: live)
            }

            let happened = vm.filteredJustHappened(for: selectedCategory)
            if !happened.isEmpty {
                feedSection(title: "Just Happened", systemImage: "clock.arrow.circlepath", imageColor: .secondary, items: happened)
            }

            let up = vm.filteredUpcoming(for: selectedCategory)
            if !up.isEmpty {
                feedSection(title: "Upcoming", systemImage: "calendar", imageColor: .blue, items: up)
            }

            let markets = vm.filteredTopMarkets(for: selectedCategory)
            if !markets.isEmpty {
                feedSection(title: "Top Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: markets)
            }

            // Grouped futures (player props, playoff progressions)
            if !vm.groupedItems.isEmpty {
                groupedFuturesSection
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
        }
    }

    // MARK: - Section Builder

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            if sizeClass == .regular {
                // iPad: multi-column grid with context menu for pin
                LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                    ForEach(items) { item in
                        gridCard(item)
                    }
                }
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
            } else {
                ForEach(items) { item in
                    feedRow(item)
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            pinSwipeButton(item)
                        }
                }
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

    // MARK: - Grouped Futures Section

    private var groupedFuturesSection: some View {
        Section {
            if sizeClass == .regular {
                LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                    ForEach(vm.groupedItems) { item in
                        groupedRow(item)
                            .padding(12)
                            .background(Color.cardBackgroundDark)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                }
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
            } else {
                ForEach(vm.groupedItems) { item in
                    groupedRow(item)
                }
            }
        } header: {
            HStack(spacing: 6) {
                Label("Player Props", systemImage: "person.fill")
                    .foregroundStyle(.green)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .textCase(nil)
                Text("\(vm.groupedItems.count)")
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

    @ViewBuilder
    private func groupedRow(_ item: GroupedFeedItem) -> some View {
        if item.type == "stat_prop", let playerName = item.playerName, let statCategory = item.statCategory, let lines = item.lines {
            PlayerStatCardView(
                playerName: playerName,
                statCategory: statCategory,
                lines: lines,
                espnPlayerId: item.espnPlayerId,
                sportKey: item.sportKey,
                eventMatchup: item.eventMatchup,
                eventTime: item.eventTime
            )
        } else if item.type == "playoff_progression", let entityName = item.entityName, let stages = item.stages {
            ProgressionLadderView(
                entityName: entityName,
                stages: stages,
                logoUrl: item.logoUrl,
                teamColors: item.teamColors
            )
        }
    }

    // MARK: - Grid Card (iPad/Mac with hover + context menu)

    private func gridCard(_ item: FeedItem) -> some View {
        let isHovered = hoveredItemId == item.id
        return feedRow(item)
            .padding(12)
            .background(Color.cardBackgroundDark)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            #if os(macOS)
            .onHover { hovering in hoveredItemId = hovering ? item.id : nil }
            .scaleEffect(isHovered ? 1.015 : 1.0)
            .shadow(color: .black.opacity(isHovered ? 0.1 : 0), radius: 4)
            .animation(.easeInOut(duration: 0.15), value: hoveredItemId)
            #endif
            .contextMenu { cardContextMenu(item) }
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
            .contentShape(Rectangle())
            .buttonStyle(.plain)
        } else if item.type == "futures", let futures = item.futures {
            Button {
                path.append(Route.futuresDetail(id: futures.id))
            } label: {
                FuturesCardView(futures: futures)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
        }
    }

    // MARK: - Swipe to Pin

    @ViewBuilder
    private func pinSwipeButton(_ item: FeedItem) -> some View {
        if let pinInfo = pinInfo(for: item) {
            let isPinned = pinManager.isPinned(type: pinInfo.type, id: pinInfo.id)
            Button {
                pinManager.togglePin(type: pinInfo.type, id: pinInfo.id)
            } label: {
                Label(isPinned ? "Unpin" : "Pin", systemImage: isPinned ? "bookmark.slash" : "bookmark")
            }
            .tint(isPinned ? .gray : .orange)
        }
    }

    // MARK: - Context Menu Pin (iPad)

    @ViewBuilder
    private func cardContextMenu(_ item: FeedItem) -> some View {
        if let pinInfo = pinInfo(for: item) {
            let isPinned = pinManager.isPinned(type: pinInfo.type, id: pinInfo.id)
            Button {
                pinManager.togglePin(type: pinInfo.type, id: pinInfo.id)
            } label: {
                Label(isPinned ? "Unpin" : "Pin", systemImage: isPinned ? "bookmark.slash" : "bookmark")
            }
        }
        if let event = item.event {
            Divider()
            ShareLink(item: URL(string: "https://bainluck.com/events/\(event.id)")!) {
                Label("Share Link", systemImage: "square.and.arrow.up")
            }
            #if os(macOS)
            Button {
                openWindow(value: event.id)
            } label: {
                Label("Open in New Window", systemImage: "macwindow.badge.plus")
            }
            #endif
        } else if let futures = item.futures {
            Divider()
            ShareLink(item: URL(string: "https://bainluck.com/futures/\(futures.id)")!) {
                Label("Share Link", systemImage: "square.and.arrow.up")
            }
        }
    }

    private func pinInfo(for item: FeedItem) -> (type: String, id: Int)? {
        if item.type == "event", let event = item.event {
            return ("event", event.id)
        } else if item.type == "futures", let futures = item.futures {
            return ("future", futures.id)
        }
        return nil
    }
}
