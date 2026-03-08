import Combine
import SwiftUI
import UIKit
import os

private let logger = Logger(subsystem: "com.bainluck", category: "mystuff")

// MARK: - ViewModel

@MainActor
final class MyStuffViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var teamFutures: TeamFuturesResponse?
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

    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            async let feedTask = APIClient.shared.fetchFeed(myTeamsOnly: true)
            async let futuresTask = APIClient.shared.fetchMyTeamFutures(limit: 50)

            let feed = try await feedTask
            let futures = try? await futuresTask

            items = feed.items
            teamFutures = futures
            error = nil
            loading = false
            logger.info("My Stuff feed loaded: \(feed.items.count) items, \(futures?.items.count ?? 0) futures")
            configureAutoRefresh()
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("My Stuff feed error: \(error)")
        }
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard hasLiveGames else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
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

struct MyStuffView: View {
    @EnvironmentObject var authManager: AuthManager
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @EnvironmentObject var pinManager: PinManager
    @StateObject private var vm = MyStuffViewModel()
    @State private var path = NavigationPath()
    @State private var showOnboarding = false
    @State private var landscapeColumns = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if authManager.isLoading {
                    ProgressView()
                } else if !authManager.isAuthenticated {
                    signInView
                } else if authManager.user?.onboardingCompleted != true {
                    onboardingPromptView
                } else {
                    teamFeedView
                }
            }
            .navigationTitle("My Stuff")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .toolbar {
                if authManager.isAuthenticated && authManager.user?.onboardingCompleted == true {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        NavigationLink(value: Route.preferences) {
                            Image(systemName: "gearshape")
                                .font(.body)
                        }
                    }
                }
            }
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
                        .environmentObject(authManager)
                case .sportCategory(let key, let name):
                    SportCategoryView(categoryKey: key, categoryName: name)
                }
            }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "my_stuff", type: "my_stuff")
            updateLandscapeColumns()
        }
        .onReceive(NotificationCenter.default.publisher(for: UIDevice.orientationDidChangeNotification)) { _ in
            updateLandscapeColumns()
        }
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
            if navCoordinator.selectedTab == .myStuff,
               let route = navCoordinator.consumeRoute() {
                path.append(route)
            }
        }
    }

    // MARK: - State 1: Sign In

    private var signInView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "person.crop.circle")
                .font(.system(size: 56))
                .foregroundStyle(.secondary)

            Text("See your teams in one place")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Sign in to follow teams and get personalized odds.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            Button {
                authManager.signInWithApple()
            } label: {
                HStack {
                    Image(systemName: "apple.logo")
                    Text("Sign in with Apple")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .foregroundStyle(.white)
                .background(.black)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)

            Button {
                authManager.signInWithGoogle()
            } label: {
                HStack {
                    Image(systemName: "g.circle.fill")
                    Text("Sign in with Google")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .foregroundStyle(.white)
                .background(Color(red: 0.26, green: 0.52, blue: 0.96))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)

            if let error = authManager.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }

            Spacer()
        }
    }

    // MARK: - State 2: Onboarding Prompt

    private var onboardingPromptView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "heart.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(.blue)

            Text("Follow some teams to get started")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Tell us what you're into and we'll personalize your feed.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            if let name = authManager.user?.displayName ?? authManager.user?.email {
                Text("Signed in as \(name)")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }

            Button {
                showOnboarding = true
            } label: {
                Text("Get Started")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .foregroundStyle(.white)
                    .background(.blue)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)

            Spacer()
        }
        .fullScreenCover(isPresented: $showOnboarding) {
            OnboardingView()
                .environmentObject(authManager)
        }
    }

    // MARK: - State 3: Team Feed

    private var teamFeedView: some View {
        Group {
            if vm.loading {
                SkeletonFeedView()
            } else if let error = vm.error, vm.items.isEmpty {
                ContentUnavailableView(
                    "Couldn't Load Feed",
                    systemImage: "wifi.exclamationmark",
                    description: Text(error)
                )
            } else if vm.items.isEmpty {
                VStack(spacing: 16) {
                    Spacer()
                    Image(systemName: "sportscourt")
                        .font(.system(size: 48))
                        .foregroundStyle(.secondary.opacity(0.5))
                    Text("No Games Right Now")
                        .font(.title3)
                        .fontWeight(.semibold)
                    Text("Your teams don't have any games coming up.\nPull down to refresh.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Spacer()
                }
                .padding(.horizontal, 40)
            } else {
                teamFeedList
            }
        }
        .task {
            await vm.load()
        }
        .onDisappear {
            vm.stopRefresh()
        }
    }

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

    // MARK: - iPad Grid

    private var iPadGridColumns: [GridItem] {
        let count = landscapeColumns ? 3 : 2
        return Array(repeating: GridItem(.flexible(), spacing: 12), count: count)
    }

    private func updateLandscapeColumns() {
        guard sizeClass == .regular else { return }
        let bounds = UIScreen.main.bounds
        landscapeColumns = bounds.width > bounds.height
    }

    private var teamFeedList: some View {
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
            if let futures = vm.teamFutures, !futures.items.isEmpty {
                TeamFuturesSection(futures: futures, path: $path)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        }
    }

    // MARK: - Section Builder

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            if sizeClass == .regular {
                // iPad: multi-column grid with context menu for pin
                LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                    ForEach(items) { item in
                        feedRow(item)
                            .padding(12)
                            .background(Color(.tertiarySystemGroupedBackground))
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .contextMenu { pinContextMenu(item) }
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

    // MARK: - Row

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let event = item.event {
            Button {
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
    private func pinContextMenu(_ item: FeedItem) -> some View {
        if let pinInfo = pinInfo(for: item) {
            let isPinned = pinManager.isPinned(type: pinInfo.type, id: pinInfo.id)
            Button {
                pinManager.togglePin(type: pinInfo.type, id: pinInfo.id)
            } label: {
                Label(isPinned ? "Unpin" : "Pin", systemImage: isPinned ? "bookmark.slash" : "bookmark")
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

// MARK: - Your Teams' Odds Section

private struct TeamFuturesSection: View {
    let futures: TeamFuturesResponse
    @Binding var path: NavigationPath
    @State private var expanded = false

    private static let initialShow = 6

    private enum FutureGroup {
        case championships, awards, other
    }

    private var grouped: (championships: [TeamFutureItem], awards: [TeamFutureItem], other: [TeamFutureItem]) {
        var championships: [TeamFutureItem] = []
        var awards: [TeamFutureItem] = []
        var other: [TeamFutureItem] = []

        for item in futures.items {
            let name = item.marketName.lowercased()
            let tier = item.marketTier
            if tier == 1
                || name.contains("champion") || name.contains("winner")
                || name.contains("world series") || name.contains("super bowl")
                || name.contains("stanley cup") || name.contains("finals") {
                championships.append(item)
            } else if name.contains("mvp") || name.contains("award")
                || name.contains("player") || name.contains("rookie")
                || name.contains("defensive") || name.contains("coach")
                || name.contains("cy young") || name.contains("heisman")
                || name.contains("improved") || name.contains("sixth man")
                || name.contains("clutch") {
                awards.append(item)
            } else {
                other.append(item)
            }
        }

        return (championships, awards, other)
    }

    private var orderedItems: [TeamFutureItem] {
        grouped.championships + grouped.awards + grouped.other
    }

    private var displayed: [TeamFutureItem] {
        expanded ? orderedItems : Array(orderedItems.prefix(Self.initialShow))
    }

    var body: some View {
        Section {
            let g = grouped
            let disp = displayed

            let dispChamp = disp.filter { item in g.championships.contains(where: { $0.id == item.id }) }
            let dispAwards = disp.filter { item in g.awards.contains(where: { $0.id == item.id }) }
            let dispOther = disp.filter { item in g.other.contains(where: { $0.id == item.id }) }

            if !dispChamp.isEmpty {
                futuresGroup(label: "Championships", items: dispChamp)
            }
            if !dispAwards.isEmpty {
                futuresGroup(label: "Awards & Players", items: dispAwards)
            }
            if !dispOther.isEmpty {
                futuresGroup(label: "Other Markets", items: dispOther)
            }

            if orderedItems.count > Self.initialShow {
                Button {
                    withAnimation { expanded.toggle() }
                } label: {
                    Text(expanded ? "Show less" : "See all \(futures.totalCount) markets →")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.blue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
            }
        } header: {
            HStack(spacing: 6) {
                Label {
                    Text("Your Teams' Odds")
                } icon: {
                    Image(systemName: "target")
                }
                .foregroundStyle(.green)
                .font(.subheadline)
                .fontWeight(.semibold)
                .textCase(nil)
                Text("\(futures.totalCount)")
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
    private func futuresGroup(label: String, items: [TeamFutureItem]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .medium))
                .tracking(1.5)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 4)
                .padding(.top, 8)
                .padding(.bottom, 4)

            ForEach(items) { item in
                Button {
                    path.append(Route.futuresDetail(id: item.marketId))
                } label: {
                    teamFutureRow(item)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func teamFutureRow(_ item: TeamFutureItem) -> some View {
        HStack(spacing: 10) {
            // Team logo
            TeamLogoView(
                url: item.matchedTeam.logoSmall,
                teamName: item.matchedTeam.name,
                color: Color(hex: item.matchedTeam.primaryColor ?? "#6b7280"),
                size: 28
            )

            // Name + market
            VStack(alignment: .leading, spacing: 2) {
                Text(item.outcomeName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)
                Text(cleanMarketName(item.marketName))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            // Rank
            if let rank = item.rank {
                if let total = item.totalOutcomes {
                    Text("#\(rank)/\(total)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else {
                    Text("#\(rank)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // 24h change
            if let change = item.probabilityChange24h, abs(change) >= 0.001 {
                let isUp = change > 0
                Text("\(isUp ? "↑" : "↓")\(String(format: "%.1f", abs(change * 100)))%")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(isUp ? .green : .red)
            }

            // Probability
            if let prob = item.probability {
                Text(formatProbability(prob))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: item.matchedTeam.primaryColor ?? "#6b7280"))
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 4)
    }

    private func cleanMarketName(_ name: String) -> String {
        var result = name
        // Strip "Winner" suffix
        if let range = result.range(of: #"\s*Winner\s*$"#, options: .regularExpression) {
            result.removeSubrange(range)
        }
        // Strip year suffix
        if let range = result.range(of: #"\s*20\d{2}(-\d{2})?\s*$"#, options: .regularExpression) {
            result.removeSubrange(range)
        }
        return result.trimmingCharacters(in: .whitespaces)
    }
}
