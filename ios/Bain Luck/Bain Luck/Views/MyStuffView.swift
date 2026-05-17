import Combine
import SwiftUI
import os
#if canImport(UIKit)
import UIKit
#endif

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
            async let feedTask = APIClient.shared.fetchFeed(myTeamsOnly: true, includeFutures: false)
            async let futuresTask = APIClient.shared.fetchMyTeamFutures(limit: 100)

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
    @State private var predictionStats: PredictionStats?
    @State private var path = NavigationPath()
    @State private var showOnboarding = false
    @State private var landscapeColumns = false
    @Environment(\.horizontalSizeClass) private var sizeClass
    #if os(macOS)
    @Environment(\.openWindow) private var openWindow
    #endif

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
                    ToolbarItem(placement: .confirmationAction) {
                        NavigationLink(value: Route.preferences) {
                            Image(systemName: "gearshape")
                                .font(.body)
                        }
                    }
                }
            }
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "my_stuff", type: "my_stuff")
            updateLandscapeColumns()
        }
        .task {
            predictionStats = try? await APIClient.shared.fetchPredictionStats()
        }
        #if os(iOS)
        .onReceive(NotificationCenter.default.publisher(for: UIDevice.orientationDidChangeNotification)) { _ in
            updateLandscapeColumns()
        }
        #endif
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
            if navCoordinator.selectedTab == .myStuff,
               let route = navCoordinator.consumeRoute() {
                path.append(route)
            }
        }
    }

    // MARK: - State 1: Sign In

    private var signInView: some View {
        ScrollView {
            VStack(spacing: 32) {
                VStack(spacing: 12) {
                    Text("🍀")
                        .font(.system(size: 48))
                    Text("Your Predictions,\nYour Teams")
                        .font(.largeTitle.weight(.black))
                        .multilineTextAlignment(.center)
                    Text("Sign in to unlock everything")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 40)

                VStack(spacing: 12) {
                    signInPerk(icon: "heart.fill", color: .red, title: "Follow your teams", desc: "See all your teams' probabilities, futures, and playoff paths in one place")
                    signInPerk(icon: "safari.fill", color: .blue, title: "Personalized Discover", desc: "Your feed learns what you care about and surfaces more of it")
                    signInPerk(icon: "flame.fill", color: .orange, title: "Prediction streaks", desc: "Track your Higher/Lower accuracy and streaks across devices")
                    signInPerk(icon: "chart.line.uptrend.xyaxis", color: .purple, title: "Prediction history", desc: "See your accuracy, category breakdowns, and badges")
                }
                .padding(.horizontal, 24)

                VStack(spacing: 12) {
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

                    if let error = authManager.error {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                    }
                }
                .padding(.horizontal, 40)

                Text("You can browse everything without signing in.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .padding(.bottom, 40)
            }
        }
    }

    private func signInPerk(icon: String, color: Color, title: String, desc: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 32)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                Text(desc)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
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
        #if os(iOS)
        .fullScreenCover(isPresented: $showOnboarding) {
            OnboardingView()
                .environmentObject(authManager)
        }
        #else
        .sheet(isPresented: $showOnboarding) {
            OnboardingView()
                .environmentObject(authManager)
                .frame(minWidth: 500, minHeight: 400)
        }
        #endif
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

    private var teamFeedList: some View {
        List {
            if let stats = predictionStats, stats.total > 0 {
                Section {
                    NavigationLink(value: Route.predictionStats) {
                        HStack(spacing: 16) {
                            VStack(spacing: 2) {
                                Text("\(Int(stats.accuracy * 100))%")
                                    .font(.title2.weight(.black).monospacedDigit())
                                    .foregroundStyle(stats.accuracy >= 0.6 ? .green : stats.accuracy >= 0.45 ? .primary : .red)
                                Text("Accuracy")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(width: 70)

                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 12) {
                                    Label("\(stats.total) predictions", systemImage: "target")
                                    if stats.currentStreak > 1 {
                                        Label("\(stats.currentStreak) streak", systemImage: "flame.fill")
                                            .foregroundStyle(.orange)
                                    }
                                }
                                .font(.caption.weight(.semibold))

                                if stats.bestStreak > 1 {
                                    Text("Best streak: \(stats.bestStreak)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }

                            Spacer()
                        }
                        .padding(.vertical, 4)
                    }
                } header: {
                    Label("Predictions", systemImage: "chart.bar.fill")
                }
            }

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
                feedSection(title: "Your Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: vm.topMarkets)
            }
            if let futures = vm.teamFutures, !futures.items.isEmpty {
                TeamFuturesSection(futures: futures, path: $path)
            }

            Section {
                NavigationLink(value: Route.about) {
                    Label("About Bain Luck", systemImage: "info.circle")
                }
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
                        feedRow(item)
                            .padding(12)
                            .background(Color.cardBackgroundDark)
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
                if let matched = futures.matchedOutcomes, !matched.isEmpty {
                    MyTeamFuturesCard(futures: futures, matchedOutcomes: matched)
                } else {
                    FuturesCardView(futures: futures)
                }
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
        if let event = item.event {
            if let prob = event.currentOdds?.homeProbability {
                Button {
                    let text = "\(event.homeTeam): \(Int(prob * 100))%"
                    #if os(macOS)
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                    #else
                    UIPasteboard.general.string = text
                    #endif
                } label: {
                    Label("Copy Probability", systemImage: "doc.on.doc")
                }
            }
            Divider()
            Button {
                let url = "https://bainluck.com/events/\(event.id)"
                #if os(macOS)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                #else
                UIPasteboard.general.string = url
                #endif
            } label: {
                Label("Copy Link", systemImage: "link")
            }
            ShareLink(item: URL(string: "https://bainluck.com/events/\(event.id)")!) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
            #if os(macOS)
            Button {
                openWindow(value: event.id)
            } label: {
                Label("Open in New Window", systemImage: "macwindow.badge.plus")
            }
            #endif
        } else if let futures = item.futures {
            if let leader = futures.topOutcomes?.first, let prob = leader.probability {
                Button {
                    let text = "\(leader.name): \(Int(prob * 100))%"
                    #if os(macOS)
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                    #else
                    UIPasteboard.general.string = text
                    #endif
                } label: {
                    Label("Copy Probability", systemImage: "doc.on.doc")
                }
            }
            Divider()
            Button {
                let url = "https://bainluck.com/futures/\(futures.id)"
                #if os(macOS)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                #else
                UIPasteboard.general.string = url
                #endif
            } label: {
                Label("Copy Link", systemImage: "link")
            }
            ShareLink(item: URL(string: "https://bainluck.com/futures/\(futures.id)")!) {
                Label("Share", systemImage: "square.and.arrow.up")
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

// MARK: - Cross-Source Merging + Progression Detection

/// Source display metadata.
private let sourceColors: [String: Color] = [
    "polymarket": Color.blue,
    "kalshi": Color.green,
    "odds_api": Color(white: 0.6),
]
private let sourceLabels: [String: String] = [
    "odds_api": "Sportsbooks",
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
]

/// Merged view of the same outcome across sources.
private struct MergedTeamFuture: Identifiable {
    var primary: TeamFutureItem
    var sources: [(source: String, probability: Double?, change: Double?, marketId: Int)]
    var avgProbability: Double?
    var bestChange: Double?
    var marketType: String?

    var id: String { "\(primary.matchedTeam?.id ?? 0)-\(marketType ?? "nil")-\(primary.marketId)" }
}

/// Progression stage definitions.
private let progressionStages: [String: (order: Int, label: String)] = [
    "make_playoffs": (1, "Playoffs"),
    "division_winner": (2, "Division"),
    "conference_winner": (3, "Conf Finals"),
    "championship": (4, "Champion"),
]

/// Detect market type from name (mirrors web detectMarketTypeFromName).
private func detectMarketTypeFromName(_ name: String) -> String? {
    let n = name.lowercased()
    if n.range(of: #"make.*playoffs|playoffs.*qualification|will make.*playoffs"#, options: .regularExpression) != nil {
        return "make_playoffs"
    }
    if n.range(of: #"division\s*(winner|champion|title)|\b(afc|nfc|al|nl)\s+(east|west|north|south|central)\b"#, options: .regularExpression) != nil {
        return "division_winner"
    }
    if n.range(of: #"conference\s*(winner|champion|title|finals)|\b(afc|nfc)\s+(champion|winner)\b"#, options: .regularExpression) != nil,
       n.range(of: #"seed|#\d|mvp"#, options: .regularExpression) == nil {
        return "conference_winner"
    }
    if n.range(of: #"champion(ship)?\s*(winner|20\d{2})|win.*championship|nba\s+champion|nfl\s+champion|mlb\s+champion|nhl\s+champion|world\s+series|super\s+bowl|stanley\s+cup"#, options: .regularExpression) != nil {
        return "championship"
    }
    return nil
}

/// Extract market type from canonical key (format: sport:league:type:season).
private func extractMarketType(_ key: String?) -> String? {
    guard let key else { return nil }
    let parts = key.split(separator: ":")
    return parts.count >= 3 ? String(parts[2]) : nil
}

/// Merge TeamFutureItems sharing the same market type + team.
private func mergeTeamFutures(_ items: [TeamFutureItem]) -> [MergedTeamFuture] {
    var byKey: [String: MergedTeamFuture] = [:]
    var keyOrder: [String] = []

    for item in items {
        // Name-based detection is the primary and only signal for progression
        // stage classification.  Canonical keys can be wrong — e.g., "Where
        // will Joey Bosa play in 2026-27?" may carry a championship canonical
        // key, which would misclassify a player-destination market.
        //
        // Canonical key is still used for non-progression grouping.
        let nameDetected = detectMarketTypeFromName(item.marketName)
        let keyDetected = extractMarketType(item.canonicalMarketKey)
        let detectedType = nameDetected ?? keyDetected

        // Only classify as progression if the NAME matches.
        let isProgression = nameDetected != nil && progressionStages[nameDetected!] != nil

        let groupKey: String
        if isProgression {
            groupKey = "progression:\(detectedType!):team_\(item.matchedTeam?.id ?? 0)"
        } else if let ck = item.canonicalMarketKey {
            groupKey = "\(ck)::\(item.outcomeName.lowercased().trimmingCharacters(in: .whitespaces))"
        } else {
            groupKey = "market_\(item.marketId)::\(item.outcomeName.lowercased().trimmingCharacters(in: .whitespaces))"
        }

        if byKey[groupKey] == nil {
            byKey[groupKey] = MergedTeamFuture(
                primary: item,
                sources: [],
                avgProbability: nil,
                bestChange: nil,
                // Guard: if canonical key gave a progression type but name
                // detection didn't confirm it, null it out so
                // detectPlayoffJourneys won't pick it up (e.g. "Where will
                // Joey Bosa play?" with championship canonical key).
                marketType: (!isProgression && detectedType != nil && progressionStages[detectedType!] != nil) ? nil : detectedType
            )
            keyOrder.append(groupKey)
        }

        let srcName = item.source ?? "unknown"
        if let existingIdx = byKey[groupKey]!.sources.firstIndex(where: { $0.source == srcName }) {
            // Same source already present — keep higher probability
            if let newP = item.probability,
               byKey[groupKey]!.sources[existingIdx].probability == nil
                || newP > (byKey[groupKey]!.sources[existingIdx].probability ?? 0) {
                byKey[groupKey]!.sources[existingIdx] = (
                    source: srcName,
                    probability: newP,
                    change: item.probabilityChange24h,
                    marketId: item.marketId
                )
            }
        } else {
            byKey[groupKey]!.sources.append((
                source: srcName,
                probability: item.probability,
                change: item.probabilityChange24h,
                marketId: item.marketId
            ))
        }

        // Use highest-ranked item as primary
        if let rank = item.rank,
           byKey[groupKey]!.primary.rank == nil || rank < (byKey[groupKey]!.primary.rank ?? Int.max) {
            byKey[groupKey]!.primary = item
        }
    }

    // Compute averages
    for key in keyOrder {
        guard var entry = byKey[key] else { continue }
        let probs = entry.sources.compactMap(\.probability).filter { $0 > 0 }
        entry.avgProbability = probs.isEmpty ? nil : probs.reduce(0, +) / Double(probs.count)

        var best: Double? = nil
        for s in entry.sources {
            if let c = s.change, (best == nil || abs(c) > abs(best!)) {
                best = c
            }
        }
        entry.bestChange = best
        byKey[key] = entry
    }

    return keyOrder.compactMap { byKey[$0] }
}

/// A team's playoff journey — multiple stages.
private struct PlayoffJourney: Identifiable {
    let teamId: Int
    let teamName: String
    let teamLogo: String?
    let teamColor: String?
    var stages: [(merged: MergedTeamFuture, order: Int, label: String)]
    var id: Int { teamId }
}

/// Detect playoff journeys from merged items.
private func detectPlayoffJourneys(_ merged: [MergedTeamFuture]) -> (journeys: [PlayoffJourney], remaining: [MergedTeamFuture]) {
    var teamStages: [Int: (team: TeamFutureTeam, stages: [(merged: MergedTeamFuture, order: Int, label: String)])] = [:]
    var remaining: [MergedTeamFuture] = []

    for m in merged {
        guard let mType = m.marketType, let stage = progressionStages[mType] else {
            remaining.append(m)
            continue
        }

        guard let matchedTeam = m.primary.matchedTeam else { continue }
        let teamId = matchedTeam.id
        if teamStages[teamId] == nil {
            teamStages[teamId] = (team: matchedTeam, stages: [])
        }
        teamStages[teamId]!.stages.append((merged: m, order: stage.order, label: stage.label))
    }

    var journeys: [PlayoffJourney] = []
    for (teamId, data) in teamStages {
        var sorted = data.stages
        sorted.sort { $0.order < $1.order }

        // NOTE: No monotonicity enforcement.  Division Winner is NOT a
        // prerequisite for Conference or Championship (wild card teams exist).
        // Showing actual market probabilities is more accurate than
        // artificially bumping earlier stages to match later ones.

        journeys.append(PlayoffJourney(
            teamId: teamId,
            teamName: data.team.name,
            teamLogo: data.team.logoSmall,
            teamColor: data.team.primaryColor,
            stages: sorted
        ))
    }

    // Sort by highest stage probability (championship preferred, fallback to any)
    journeys.sort { a, b in
        func bestProb(_ j: PlayoffJourney) -> Double {
            if let champ = j.stages.first(where: { $0.order == 4 })?.merged.avgProbability {
                return champ
            }
            return j.stages.last?.merged.avgProbability ?? 0
        }
        return bestProb(a) > bestProb(b)
    }

    return (journeys, remaining)
}

// MARK: - PlayoffJourneyCard (native SwiftUI)

private struct PlayoffJourneyCard: View {
    let journey: PlayoffJourney
    let onStageTap: (Int) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header: logo + name + PLAYOFFS label
            HStack(spacing: 8) {
                TeamLogoView(
                    url: journey.teamLogo,
                    teamName: journey.teamName,
                    color: Color(hex: journey.teamColor ?? "#6b7280"),
                    size: 28
                )
                Text(journey.teamName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)
                Spacer()
                Text("PLAYOFFS")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
            }

            // Stage rows
            ForEach(journey.stages, id: \.order) { stage in
                let prob = stage.merged.avgProbability ?? 0
                let achieved = prob >= 0.99

                Button {
                    onStageTap(stage.merged.primary.marketId)
                } label: {
                    HStack(spacing: 6) {
                        // Status dot
                        Circle()
                            .fill(achieved ? Color.green : Color.secondary.opacity(0.3))
                            .frame(width: 7, height: 7)

                        // Stage label
                        Text(stage.label)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        // Probability bar
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule()
                                    .fill(Color.secondary.opacity(0.15))
                                Capsule()
                                    .fill(achieved
                                          ? Color.green
                                          : Color(hex: journey.teamColor ?? "#6b7280").opacity(0.5))
                                    .frame(width: geo.size.width * min(prob, 1.0))
                            }
                        }
                        .frame(width: 40, height: 4)

                        // Probability value
                        Text(achieved ? "done" : formatProbability(prob))
                            .font(.system(.caption, design: .monospaced))
                            .fontWeight(.medium)
                            .foregroundStyle(probTextColor(prob, achieved: achieved))
                            .frame(minWidth: 34, alignment: .trailing)

                        // Source dots
                        if stage.merged.sources.count > 1 {
                            HStack(spacing: 2) {
                                ForEach(stage.merged.sources, id: \.source) { s in
                                    Circle()
                                        .fill(sourceColors[s.source] ?? .gray)
                                        .frame(width: 4, height: 4)
                                }
                            }
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(Color.cardBackgroundDark)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .leading) {
            if let c = journey.teamColor {
                UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 10, bottomTrailingRadius: 0, topTrailingRadius: 0)
                    .fill(Color(hex: c))
                    .frame(width: 3)
            }
        }
    }

    private func probTextColor(_ p: Double, achieved: Bool) -> Color {
        if achieved { return .green }
        if p >= 0.7 { return .green }
        if p >= 0.4 { return .primary }
        if p >= 0.15 { return .orange }
        return .red
    }
}

// MARK: - Your Teams' Odds Section (with merging + progression)

private struct TeamFuturesSection: View {
    let futures: TeamFuturesResponse
    @Binding var path: NavigationPath
    @State private var expanded = false

    private static let initialShow = 10

    private var processed: (journeys: [PlayoffJourney], awards: [MergedTeamFuture], other: [MergedTeamFuture]) {
        let merged = mergeTeamFutures(futures.items)
        let (journeys, remaining) = detectPlayoffJourneys(merged)

        var awards: [MergedTeamFuture] = []
        var other: [MergedTeamFuture] = []

        for m in remaining {
            let name = m.primary.marketName.lowercased()
            if name.contains("mvp") || name.contains("award")
                || name.contains("player") || name.contains("rookie")
                || name.contains("defensive") || name.contains("coach")
                || name.contains("cy young") || name.contains("heisman")
                || name.contains("improved") || name.contains("sixth man")
                || name.contains("clutch") {
                awards.append(m)
            } else {
                other.append(m)
            }
        }

        awards.sort { ($0.avgProbability ?? 0) > ($1.avgProbability ?? 0) }
        other.sort { ($0.avgProbability ?? 0) > ($1.avgProbability ?? 0) }

        return (journeys, awards, other)
    }

    var body: some View {
        let data = processed
        let allFlat = data.awards + data.other
        let displayedFlat = expanded
            ? allFlat
            : Array(allFlat.prefix(max(0, Self.initialShow - data.journeys.count)))
        let uniqueCount = data.journeys.count + allFlat.count

        Section {
            // Progression ladder cards
            if !data.journeys.isEmpty {
                ForEach(data.journeys) { journey in
                    PlayoffJourneyCard(journey: journey) { marketId in
                        path.append(Route.futuresDetail(id: marketId))
                    }
                    .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                }
            }

            // Flat items (awards + other)
            let dispAwards = displayedFlat.filter { m in data.awards.contains(where: { $0.id == m.id }) }
            let dispOther = displayedFlat.filter { m in data.other.contains(where: { $0.id == m.id }) }

            if !dispAwards.isEmpty {
                mergedGroup(label: "Awards & Players", items: dispAwards)
            }
            if !dispOther.isEmpty {
                mergedGroup(label: "Other Markets", items: dispOther, borderTop: !dispAwards.isEmpty)
            }

            if allFlat.count + data.journeys.count > Self.initialShow {
                Button {
                    withAnimation { expanded.toggle() }
                } label: {
                    Text(expanded ? "Show less" : "See all \(uniqueCount) markets →")
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
                    Text("Your Teams' Probabilities")
                } icon: {
                    Image(systemName: "target")
                }
                .foregroundStyle(.green)
                .font(.subheadline)
                .fontWeight(.semibold)
                .textCase(nil)
                Text("\(processed.journeys.count + processed.awards.count + processed.other.count)")
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
    private func mergedGroup(label: String, items: [MergedTeamFuture], borderTop: Bool = false) -> some View {
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
                    path.append(Route.futuresDetail(id: item.primary.marketId))
                } label: {
                    mergedFutureRow(item)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func mergedFutureRow(_ merged: MergedTeamFuture) -> some View {
        let isMultiSource = merged.sources.count > 1
        let displayProb = isMultiSource ? merged.avgProbability : merged.primary.probability
        let item = merged.primary

        return HStack(spacing: 10) {
            // Team logo
            TeamLogoView(
                url: item.matchedTeam?.logoSmall,
                teamName: item.matchedTeam?.name ?? "",
                color: Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280"),
                size: 28
            )

            // Name + market + source dots
            VStack(alignment: .leading, spacing: 2) {
                Text(item.outcomeName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)
                HStack(spacing: 4) {
                    Text(cleanMarketName(item.marketName))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    if isMultiSource {
                        HStack(spacing: 2) {
                            ForEach(merged.sources, id: \.source) { s in
                                Circle()
                                    .fill(sourceColors[s.source] ?? .gray)
                                    .frame(width: 4, height: 4)
                            }
                        }
                    }
                }
            }

            Spacer()

            // 24h change
            if let change = merged.bestChange, abs(change) >= 0.001 {
                let isUp = change > 0
                Text("\(isUp ? "↑" : "↓")\(String(format: "%.1f", abs(change * 100)))%")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(isUp ? .green : .red)
            }

            // Probability
            if isMultiSource {
                // Per-source probabilities
                HStack(spacing: 4) {
                    ForEach(merged.sources, id: \.source) { s in
                        if let p = s.probability {
                            Text(formatProbability(p))
                                .font(.system(.caption2, design: .monospaced))
                                .fontWeight(.semibold)
                                .foregroundStyle(sourceColors[s.source] ?? .gray)
                        } else {
                            Text("—")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            } else if let prob = displayProb {
                Text(formatProbability(prob))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280"))
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 4)
    }

    private func cleanMarketName(_ name: String) -> String {
        var result = name
        if let range = result.range(of: #"\s*Winner\s*$"#, options: .regularExpression) {
            result.removeSubrange(range)
        }
        if let range = result.range(of: #"\s*20\d{2}(-\d{2})?\s*$"#, options: .regularExpression) {
            result.removeSubrange(range)
        }
        return result.trimmingCharacters(in: .whitespaces)
    }
}

// MARK: - My Team Futures Card

/// Futures card for My Stuff that highlights the user's team outcomes instead
/// of showing the global top 3 leaders. Shows the user's team probability,
/// rank, and movement in the context of the broader market.
private struct MyTeamFuturesCard: View {
    let futures: FeedFuturesData
    let matchedOutcomes: [MatchedOutcome]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                Text(futures.llmSportCategory?.capitalized ?? "Futures")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                PinButton(type: "future", id: futures.id, compact: true)
                if let count = futures.sourceCount, count > 1 {
                    Text("\(count) sources")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                } else if let source = futures.source {
                    Text(source.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            // Market name
            Text(futures.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

            // User's matched team outcomes — shown prominently
            ForEach(matchedOutcomes) { outcome in
                HStack(spacing: 8) {
                    if let rank = outcome.rank {
                        Text("#\(rank)")
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .foregroundStyle(.blue)
                            .frame(width: 24, alignment: .trailing)
                    }
                    Text(outcome.name)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .lineLimit(1)
                    Spacer()
                    if let m = outcome.movement, abs(m) >= 0.005 {
                        HStack(spacing: 1) {
                            Image(systemName: m > 0 ? "arrow.up" : "arrow.down")
                                .font(.system(size: 8))
                            Text(formatProbability(abs(m)))
                                .font(.system(size: 9))
                        }
                        .foregroundStyle(m > 0 ? .green : .red)
                    }
                    if let prob = outcome.probability {
                        Text(formatProbability(prob))
                            .font(.subheadline)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    }
                }
                .padding(.vertical, 4)
                .padding(.horizontal, 8)
                .background(Color.blue.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            // Show the market leader for context (if different from matched)
            if let leader = futures.topOutcomes?.first,
               !matchedOutcomes.contains(where: { $0.name == leader.name }) {
                HStack(spacing: 8) {
                    Text("Leader:")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text(leader.name)
                        .font(.caption)
                        .lineLimit(1)
                    Spacer()
                    if let prob = leader.probability {
                        Text(formatProbability(prob))
                            .font(.caption)
                            .fontWeight(.semibold)
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                }
            }

            // Remaining count
            if let total = futures.outcomeCount, total > matchedOutcomes.count + 1 {
                Text("+\(total - matchedOutcomes.count) other outcomes")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }
}
