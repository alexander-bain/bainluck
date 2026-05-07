import SwiftUI
import Combine
import os
#if canImport(UIKit)
import UIKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "sportCategory")

// MARK: - ViewModel

@MainActor
final class SportCategoryViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = true
    @Published var error: String?
    @Published var loadingMore = false
    @Published var hasMore = true
    @Published var leagueMarkets: LeagueMarketsResponse?

    let categoryKey: String
    private let pageSize = 50

    init(categoryKey: String) {
        self.categoryKey = categoryKey
    }

    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            async let feedTask = APIClient.shared.fetchFeed(sport: categoryKey, limit: pageSize, offset: 0)
            async let marketsTask = loadLeagueMarkets()
            let feed = try await feedTask
            _ = await marketsTask
            items = feed.items
            hasMore = feed.hasMore
            error = nil
            loading = false
            logger.info("Category \(self.categoryKey) loaded: \(self.items.count) items")
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("Category feed error: \(error)")
        }
    }

    func loadMore() async {
        guard !loadingMore, hasMore else { return }
        loadingMore = true
        do {
            let feed = try await APIClient.shared.fetchFeed(sport: categoryKey, limit: pageSize, offset: items.count)
            items.append(contentsOf: feed.items)
            hasMore = feed.hasMore
            logger.info("Category \(self.categoryKey) loaded more: +\(feed.items.count), total \(self.items.count)")
        } catch {
            logger.error("Category load more error: \(error)")
        }
        loadingMore = false
    }

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

    private func loadLeagueMarkets() async {
        do {
            leagueMarkets = try await APIClient.shared.fetchLeagueMarkets(sportKey: categoryKey)
            logger.info("League markets for \(self.categoryKey): \(self.leagueMarkets?.totalMarkets ?? 0) total")
        } catch {
            logger.debug("League markets not available for \(self.categoryKey): \(error)")
        }
    }
}

// MARK: - View

struct SportCategoryView: View {
    let categoryKey: String
    let categoryName: String
    @StateObject private var vm: SportCategoryViewModel
    @EnvironmentObject var pinManager: PinManager
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var iPadGridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 340), spacing: 12)]
    }

    init(categoryKey: String, categoryName: String) {
        self.categoryKey = categoryKey
        self.categoryName = categoryName
        _vm = StateObject(wrappedValue: SportCategoryViewModel(categoryKey: categoryKey))
    }

    var body: some View {
        Group {
            if vm.loading {
                SkeletonFeedView()
            } else if let error = vm.error, vm.items.isEmpty {
                VStack(spacing: 16) {
                    Spacer()
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 48))
                        .foregroundStyle(.secondary.opacity(0.5))
                    Text("Couldn't Load")
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
            } else if vm.items.isEmpty {
                VStack(spacing: 16) {
                    Spacer()
                    Image(systemName: sportIcon(for: categoryKey))
                        .font(.system(size: 48))
                        .foregroundStyle(.secondary.opacity(0.5))
                    Text("No \(categoryName) Right Now")
                        .font(.title3)
                        .fontWeight(.semibold)
                    Text("Check back later for \(categoryName.lowercased()) events and futures.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Spacer()
                }
                .padding(.horizontal, 40)
            } else {
                categoryList
            }
        }
        .navigationTitle(categoryName)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear {
            AnalyticsService.trackScreen(name: "sport_category", type: "category")
        }
        .task {
            await vm.load()
        }
        .refreshable {
            await vm.load()
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
        }
    }

    private func sportIcon(for key: String) -> String {
        switch key {
        case "basketball": return "basketball.fill"
        case "football": return "football.fill"
        case "baseball": return "baseball.fill"
        case "hockey": return "hockey.puck.fill"
        case "soccer": return "soccerball"
        case "golf": return "figure.golf"
        case "tennis": return "tennis.racket"
        case "mma": return "figure.boxing"
        case "politics": return "building.columns.fill"
        case "entertainment": return "star.fill"
        case "crypto": return "bitcoinsign.circle.fill"
        default: return "sportscourt"
        }
    }

    private var categoryList: some View {
        List {
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
                feedSection(title: "Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: vm.topMarkets)
            }

            // League market sections (awards, series, playoff props)
            if let lm = vm.leagueMarkets {
                let sectionOrder = ["series", "awards", "playoff_props", "season_stats", "novelty"]
                let sectionLabels: [String: String] = [
                    "series": "Playoff Series",
                    "awards": "Awards",
                    "playoff_props": "Playoff Props",
                    "season_stats": "Season Stats",
                    "novelty": "More Markets",
                ]
                ForEach(sectionOrder, id: \.self) { key in
                    if let markets = lm.sections[key], !markets.isEmpty {
                        Section {
                            ForEach(markets.prefix(6)) { market in
                                NavigationLink(value: Route.futuresDetail(id: market.id)) {
                                    leagueMarketRow(market)
                                }
                            }
                            if markets.count > 6 {
                                Text("+\(markets.count - 6) more")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } header: {
                            Label(sectionLabels[key] ?? key, systemImage: key == "awards" ? "trophy.fill" : key == "series" ? "sportscourt.fill" : "chart.line.uptrend.xyaxis")
                        }
                    }
                }
            }

            if vm.hasMore {
                Section {
                    if vm.loadingMore {
                        HStack {
                            Spacer()
                            ProgressView()
                            Spacer()
                        }
                        .listRowBackground(Color.clear)
                    } else {
                        Color.clear
                            .frame(height: 1)
                            .onAppear {
                                Task { await vm.loadMore() }
                            }
                            .listRowBackground(Color.clear)
                    }
                }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            if sizeClass == .regular {
                LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                    ForEach(items) { item in
                        feedRow(item)
                            .padding(12)
                            .background(Color.cardBackgroundDark)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
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

    private func leagueMarketRow(_ market: LeagueMarketItem) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(market.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

            if let outcomes = market.topOutcomes, !outcomes.isEmpty {
                ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                    HStack(spacing: 4) {
                        Text(o.name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text("\(Int(o.prob))%")
                            .font(.caption)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    }
                }
            }

            HStack(spacing: 4) {
                Text(market.source)
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(market.source == "kalshi" ? Color.green.opacity(0.1) : Color.blue.opacity(0.1))
                    .clipShape(Capsule())
                if let count = market.outcomeCount, count > 3 {
                    Text("+\(count - 3) more")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Spacer()
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let event = item.event {
            NavigationLink(value: Route.eventDetail(id: event.id)) {
                EventCardView(
                    event: event,
                    reason: item.reason,
                    personalizationReasons: item.personalizationReasons,
                    headline: item.headline
                )
            }
            .buttonStyle(.plain)
        } else if item.type == "futures", let futures = item.futures {
            NavigationLink(value: Route.futuresDetail(id: futures.id)) {
                FuturesCardView(futures: futures)
            }
            .buttonStyle(.plain)
        }
    }

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

    private func pinInfo(for item: FeedItem) -> (type: String, id: Int)? {
        if item.type == "event", let event = item.event {
            return ("event", event.id)
        } else if item.type == "futures", let futures = item.futures {
            return ("future", futures.id)
        }
        return nil
    }
}
