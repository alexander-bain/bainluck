import SwiftUI
import Combine

private enum DiscoverGroupedItem: Identifiable {
    case single(FeedItem)
    case group(title: String, items: [FeedItem])

    var id: String {
        switch self {
        case .single(let item): return item.id
        case .group(let title, _): return "group-\(title)"
        }
    }
}

private enum NativeDiscoverAction {
    case detailOpen
    case like
    case unlike
    case share
    case contextExpand
    case contextCollapse
}

private struct NativeDiscoverProfile {
    private static let storageKey = "discover_interaction_profile_native_v1"
    private var categoryScores: [String: Double]

    static func load() -> NativeDiscoverProfile {
        let raw = UserDefaults.standard.dictionary(forKey: storageKey) as? [String: Double] ?? [:]
        return NativeDiscoverProfile(categoryScores: raw)
    }

    mutating func record(category: String, action: NativeDiscoverAction) {
        let key = category.lowercased()
        let weight: Double
        switch action {
        case .detailOpen: weight = 1.5
        case .like: weight = 2.0
        case .unlike: weight = -1.0
        case .share: weight = 3.0
        case .contextExpand: weight = 0.35
        case .contextCollapse: weight = 0.0
        }
        categoryScores[key] = min(30, max(-10, (categoryScores[key] ?? 0) + weight))
        save()
    }

    func adjustment(for category: String) -> Double {
        let score = categoryScores[category.lowercased()] ?? 0
        guard abs(score) >= 2 else { return 0 }
        return min(12, max(-8, score))
    }

    func topAffinities(limit: Int = 3) -> [(String, Double)] {
        categoryScores
            .filter { abs($0.value) >= 2 }
            .sorted { abs($0.value) > abs($1.value) }
            .prefix(limit)
            .map { ($0.key, $0.value) }
    }

    mutating func reset() {
        categoryScores = [:]
        save()
    }

    private func save() {
        UserDefaults.standard.set(categoryScores, forKey: Self.storageKey)
    }
}

struct NativeDiscoverDebugCard: Codable {
    let itemType: String
    let itemId: String
    let itemName: String?
    let category: String
    let rank: Int?
    let score: Int
}

struct NativeDiscoverDebugInteraction: Codable {
    let action: String
    let itemType: String
    let itemId: String
    let itemName: String?
    let category: String
    let source: String
    let timestamp: String
}

enum NativeDiscoverDebugState {
    private static let visibleCardsKey = "discover_debug_visible_cards"
    private static let recentInteractionsKey = "discover_debug_recent_interactions"
    private static let currentCardKey = "discover_debug_current_card"
    private static let encoder = JSONEncoder()
    private static let decoder = JSONDecoder()
    private static let iso = ISO8601DateFormatter()

    static func recordVisibleCard(_ card: NativeDiscoverDebugCard) {
        var cards = visibleCards()
        cards.removeAll { $0.itemType == card.itemType && $0.itemId == card.itemId }
        cards.append(card)
        cards = Array(cards.suffix(20))
        save(cards, key: visibleCardsKey)
        save(card, key: currentCardKey)
    }

    static func recordInteraction(_ interaction: NativeDiscoverDebugInteraction) {
        var interactions = recentInteractions()
        interactions.append(interaction)
        interactions = Array(interactions.suffix(20))
        save(interactions, key: recentInteractionsKey)
    }

    static func appStateFields() -> [String: String] {
        var fields: [String: String] = [:]
        fields["discover_visible_cards"] = UserDefaults.standard.string(forKey: visibleCardsKey) ?? "[]"
        fields["discover_recent_interactions"] = UserDefaults.standard.string(forKey: recentInteractionsKey) ?? "[]"
        fields["discover_current_card"] = UserDefaults.standard.string(forKey: currentCardKey) ?? "{}"
        return fields
    }

    static func timestamp() -> String {
        iso.string(from: Date())
    }

    private static func visibleCards() -> [NativeDiscoverDebugCard] {
        guard
            let raw = UserDefaults.standard.string(forKey: visibleCardsKey),
            let data = raw.data(using: .utf8),
            let cards = try? decoder.decode([NativeDiscoverDebugCard].self, from: data)
        else { return [] }
        return cards
    }

    private static func recentInteractions() -> [NativeDiscoverDebugInteraction] {
        guard
            let raw = UserDefaults.standard.string(forKey: recentInteractionsKey),
            let data = raw.data(using: .utf8),
            let interactions = try? decoder.decode([NativeDiscoverDebugInteraction].self, from: data)
        else { return [] }
        return interactions
    }

    private static func save<T: Encodable>(_ value: T, key: String) {
        guard
            let data = try? encoder.encode(value),
            let raw = String(data: data, encoding: .utf8)
        else { return }
        UserDefaults.standard.set(raw, forKey: key)
    }
}

struct DiscoverView: View {
    @StateObject private var vm = DiscoverViewModel()
    @State private var visibleCount = 20
    @State private var dismissed: Set<String> = Self.loadDismissed()
    @State private var scrollTarget: String? = nil
    @State private var dailyGuesses: Int = Self.loadDailyGuesses()
    @State private var showOnboarding = !UserDefaults.standard.bool(forKey: "discover_onboarded")
    @State private var resolutions: [Resolution] = []
    @State private var interactionProfile = NativeDiscoverProfile.load()
    @State private var seenImpressions: Set<String> = []
    @State private var navigationPath = NavigationPath()
    @State private var showSwipeHint = !UserDefaults.standard.bool(forKey: "discover_swipe_hinted")
    @State private var showChallenge = false
    @State private var challengeIndex = 0
    @State private var challengeComplete = false

    private let sportsCats: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    private func itemCategory(_ item: FeedItem) -> String {
        if item.type == "event", let e = item.event {
            return e.sport?.split(separator: "_").first.map(String.init) ?? "sports"
        }
        if item.type == "futures", let f = item.futures {
            return f.llmSportCategory ?? "other"
        }
        return "golf"
    }

    private func isStale(_ item: FeedItem) -> Bool {
        if let f = item.futures {
            if let leader = f.topOutcomes?.first {
                let probability = leader.probability ?? 0
                if probability >= 0.98 { return true }
                if probability <= 0.02 { return true }
                if probability >= 0.90 {
                    if leader.movement == nil || abs(leader.movement ?? 0) < 0.005 { return true }
                }
            }
            if f.status == "closed" || f.status == "resolved" { return true }
            if let rd = f.resolutionDate, let d = rd.asDate, d < Date() { return true }
        }
        if let e = item.event {
            if e.status == "completed" || e.status == "closed" {
                if let ct = e.commenceTime, let d = ct.asDate {
                    return Date().timeIntervalSince(d) > 8 * 3600
                }
            }
        }
        return false
    }

    private func itemId(_ item: FeedItem) -> String {
        if let e = item.event { return "event-\(e.id)" }
        if let f = item.futures { return "futures-\(f.id)" }
        return UUID().uuidString
    }

    private func itemType(_ item: FeedItem) -> String {
        if item.event != nil { return "event" }
        if item.futures != nil { return "futures" }
        return item.type
    }

    private func rawItemId(_ item: FeedItem) -> String {
        if let e = item.event { return String(e.id) }
        if let f = item.futures { return String(f.id) }
        return item.id
    }

    private func itemName(_ item: FeedItem) -> String? {
        if let e = item.event { return "\(e.awayTeam) vs \(e.homeTeam)" }
        if let f = item.futures { return f.name }
        return nil
    }

    private func primaryItem(_ grouped: DiscoverGroupedItem) -> FeedItem? {
        switch grouped {
        case .single(let item): return item
        case .group(_, let items): return items.first
        }
    }

    private func applyLocalPersonalization(_ items: [DiscoverGroupedItem]) -> [DiscoverGroupedItem] {
        guard items.count > 6 else { return items }

        let pinnedLead = Array(items.prefix(3))
        let rest = Array(items.dropFirst(3))
        var result = pinnedLead
        let windowSize = 5

        for start in stride(from: 0, to: rest.count, by: windowSize) {
            let end = min(start + windowSize, rest.count)
            let window = Array(rest[start..<end])
            let ranked = window.enumerated().sorted { lhs, rhs in
                let leftItem = primaryItem(lhs.element)
                let rightItem = primaryItem(rhs.element)
                let leftScore = Double(leftItem?.score ?? 0) + (leftItem.map { interactionProfile.adjustment(for: itemCategory($0)) } ?? 0)
                let rightScore = Double(rightItem?.score ?? 0) + (rightItem.map { interactionProfile.adjustment(for: itemCategory($0)) } ?? 0)
                if abs(leftScore - rightScore) > 0.001 { return leftScore > rightScore }
                return lhs.offset < rhs.offset
            }.map(\.element)
            result.append(contentsOf: ranked)
        }

        return result
    }

    private func recordInteraction(for item: FeedItem, action: NativeDiscoverAction, source: String = "card") {
        interactionProfile.record(category: itemCategory(item), action: action)
        let actionName: String
        switch action {
        case .detailOpen: actionName = "open"
        case .like: actionName = "like"
        case .unlike: actionName = "unlike"
        case .share: actionName = "share"
        case .contextExpand: actionName = "context_expand"
        case .contextCollapse: actionName = "context_collapse"
        }
        AnalyticsService.trackDiscoverCardAction(
            action: actionName,
            itemId: itemId(item),
            itemType: itemType(item),
            category: itemCategory(item),
            source: source
        )
        Task {
            let event = DiscoverInteractionEvent(
                action: actionName,
                itemType: itemType(item),
                itemId: rawItemId(item),
                category: itemCategory(item),
                itemName: itemName(item),
                score: item.score,
                rank: nil,
                surface: "native",
                source: source
            )
            _ = try? await APIClient.shared.recordDiscoverInteraction(event)
        }
        NativeDiscoverDebugState.recordInteraction(
            NativeDiscoverDebugInteraction(
                action: actionName,
                itemType: itemType(item),
                itemId: rawItemId(item),
                itemName: itemName(item),
                category: itemCategory(item),
                source: source,
                timestamp: NativeDiscoverDebugState.timestamp()
            )
        )
    }

    private func recordChallengeAction(_ actionName: String) {
        AnalyticsService.trackDiscoverCardAction(
            action: actionName,
            itemId: "daily_challenge",
            itemType: "grid",
            category: "challenge",
            source: "challenge"
        )
        Task {
            let event = DiscoverInteractionEvent(
                action: actionName,
                itemType: "grid",
                itemId: "daily_challenge",
                category: "challenge",
                itemName: "Today's Challenge",
                score: 0,
                rank: nil,
                surface: "native",
                source: "challenge"
            )
            _ = try? await APIClient.shared.recordDiscoverInteraction(event)
        }
        NativeDiscoverDebugState.recordInteraction(
            NativeDiscoverDebugInteraction(
                action: actionName,
                itemType: "grid",
                itemId: "daily_challenge",
                itemName: "Today's Challenge",
                category: "challenge",
                source: "challenge",
                timestamp: NativeDiscoverDebugState.timestamp()
            )
        )
    }

    private func trackImpression(for grouped: DiscoverGroupedItem, rank: Int) {
        guard let item = primaryItem(grouped) else { return }
        let impressionKey = "\(grouped.id)-\(rank)"
        guard !seenImpressions.contains(impressionKey) else { return }
        seenImpressions.insert(impressionKey)
        AnalyticsService.trackDiscoverCardImpression(
            itemId: itemId(item),
            itemType: itemType(item),
            category: itemCategory(item),
            rank: rank,
            score: item.score
        )
        Task {
            let event = DiscoverInteractionEvent(
                action: "impression",
                itemType: itemType(item),
                itemId: rawItemId(item),
                category: itemCategory(item),
                itemName: itemName(item),
                score: item.score,
                rank: rank,
                surface: "native",
                source: "viewport"
            )
            _ = try? await APIClient.shared.recordDiscoverInteraction(event)
        }
    }

    private var filteredItems: [FeedItem] {
        vm.items.filter { !dismissed.contains(itemId($0)) }
    }

    private var groupedItems: [DiscoverGroupedItem] {
        var groups: [String: [FeedItem]] = [:]
        var groupTitles: [String: String] = [:]
        var result: [DiscoverGroupedItem] = []
        var usedPrefixes: Set<String> = []

        let mixedItems = interleave(filteredItems)

        for item in mixedItems {
            guard item.type == "futures", let grouping = futuresGrouping(for: item) else { continue }
            if groups[grouping.key] == nil {
                groupTitles[grouping.key] = grouping.title
            }
            groups[grouping.key, default: []].append(item)
        }

        for item in mixedItems {
            if item.type != "futures" {
                result.append(.single(item))
                continue
            }
            guard let grouping = futuresGrouping(for: item) else {
                result.append(.single(item))
                continue
            }
            if usedPrefixes.contains(grouping.key) { continue }
            usedPrefixes.insert(grouping.key)
            let group = groups[grouping.key] ?? [item]
            if group.count >= 2 {
                result.append(.group(title: groupTitles[grouping.key] ?? grouping.title, items: group))
            } else {
                result.append(.single(group[0]))
            }
        }
        return interleaveGrouped(applyLocalPersonalization(result))
    }

    private func futuresGrouping(for item: FeedItem) -> (key: String, title: String)? {
        guard let futures = item.futures else { return nil }
        if let groupId = futures.groupId?.trimmingCharacters(in: .whitespacesAndNewlines), !groupId.isEmpty {
            return ("group:\(groupId)", futuresGroupTitle(for: futures))
        }
        if let canonical = futures.canonicalMarketKey?.trimmingCharacters(in: .whitespacesAndNewlines), !canonical.isEmpty {
            return ("canonical:\(canonical)", futuresGroupTitle(for: futures))
        }
        let name = futures.name
        if let colonIdx = name.firstIndex(of: ":"), name.distance(from: name.startIndex, to: colonIdx) < 30 {
            let prefix = String(name[..<colonIdx]).trimmingCharacters(in: .whitespaces)
            if !prefix.isEmpty {
                return ("prefix:\(prefix.lowercased())", prefix)
            }
        }
        return nil
    }

    private func futuresGroupTitle(for futures: FeedFuturesData) -> String {
        if let colonIdx = futures.name.firstIndex(of: ":"), futures.name.distance(from: futures.name.startIndex, to: colonIdx) < 30 {
            let prefix = String(futures.name[..<colonIdx]).trimmingCharacters(in: .whitespaces)
            if !prefix.isEmpty { return prefix }
        }
        return futures.name
    }

    private func interleave(_ items: [FeedItem]) -> [FeedItem] {
        guard items.count > 2 else { return items }

        var sports = items.filter { sportsCats.contains(itemCategory($0)) }
        var nonSports = items.filter { !sportsCats.contains(itemCategory($0)) }
        guard !nonSports.isEmpty else { return items }

        var result: [FeedItem] = []
        var lastCategory = ""
        var sportsSinceNonSport = 0
        let maxSportsRun = nonSports.count >= 4 ? 2 : 3

        while !sports.isEmpty || !nonSports.isEmpty {
            if !nonSports.isEmpty && (sportsSinceNonSport >= maxSportsRun || sports.isEmpty) {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = itemCategory(item)
                continue
            }

            if !sports.isEmpty {
                if itemCategory(sports[0]) == lastCategory,
                   let swapIdx = sports.prefix(5).firstIndex(where: { itemCategory($0) != lastCategory }) {
                    sports.swapAt(0, swapIdx)
                }
                let item = sports.removeFirst()
                result.append(item)
                lastCategory = itemCategory(item)
                sportsSinceNonSport += 1
            } else if !nonSports.isEmpty {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = itemCategory(item)
            }
        }

        return result
    }

    private func groupedCategory(_ item: DiscoverGroupedItem) -> String {
        primaryItem(item).map(itemCategory) ?? "other"
    }

    private func interleaveGrouped(_ items: [DiscoverGroupedItem]) -> [DiscoverGroupedItem] {
        guard items.count > 2 else { return items }

        var sports = items.filter { sportsCats.contains(groupedCategory($0)) }
        var nonSports = items.filter { !sportsCats.contains(groupedCategory($0)) }
        guard !nonSports.isEmpty else { return items }

        var result: [DiscoverGroupedItem] = []
        var lastCategory = ""
        var sportsSinceNonSport = 0
        let maxSportsRun = nonSports.count >= 4 ? 2 : 3

        while !sports.isEmpty || !nonSports.isEmpty {
            if !nonSports.isEmpty && (sportsSinceNonSport >= maxSportsRun || sports.isEmpty) {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = groupedCategory(item)
                continue
            }

            if !sports.isEmpty {
                if groupedCategory(sports[0]) == lastCategory,
                   let swapIdx = sports.prefix(5).firstIndex(where: { groupedCategory($0) != lastCategory }) {
                    sports.swapAt(0, swapIdx)
                }
                let item = sports.removeFirst()
                result.append(item)
                lastCategory = groupedCategory(item)
                sportsSinceNonSport += 1
            } else if !nonSports.isEmpty {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = groupedCategory(item)
            }
        }

        return result
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
        VStack(spacing: 0) {
        ScrollView {
            VStack(spacing: 0) {
                // Resolution cards
                ForEach(resolutions.prefix(3), id: \.marketName) { res in
                    NativeResolutionCard(resolution: res)
                        .padding(.horizontal)
                }

                // Daily Challenge card
                NativeDailyChallengeCard(guessesToday: dailyGuesses) {
                    challengeIndex = 0
                    challengeComplete = false
                    showChallenge = true
                    recordChallengeAction("challenge_start")
                }
                    .padding(.horizontal)
                    .padding(.bottom, 8)

                if vm.loading && vm.items.isEmpty {
                    VStack(spacing: 12) {
                        ProgressView()
                        Text("Loading predictions…")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                } else if let error = vm.error, vm.items.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "wifi.slash")
                            .font(.largeTitle)
                            .foregroundStyle(.secondary)
                        Text(error)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                }

                // Swipe hint (shown once)
                if showSwipeHint {
                    HStack(spacing: 12) {
                        Image(systemName: "hand.draw.fill")
                            .font(.title3)
                            .foregroundStyle(.orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Shape your feed")
                                .font(.caption.weight(.semibold))
                            Text("Right = more like this. Left = less like this.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button {
                            withAnimation { showSwipeHint = false }
                            UserDefaults.standard.set(true, forKey: "discover_swipe_hinted")
                        } label: {
                            Image(systemName: "xmark")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(12)
                    .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal)
                    .padding(.bottom, 8)
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                // Cards (paginated — show `visibleCount` at a time)
                let pageGrouped = Array(groupedItems.prefix(visibleCount))
                let columns = [GridItem(.adaptive(minimum: 340), spacing: 16)]
                ScrollViewReader { proxy in
                    LazyVGrid(columns: columns, spacing: 16) {
                        ForEach(Array(pageGrouped.enumerated()), id: \.element.id) { idx, gi in
                            let isGuessSlot = (idx + 1) % 5 == 0
                            Group {
                                switch gi {
                                case .group(let title, let items):
                                    NativeGroupCard(title: title, items: items)
                                case .single(let item):
                                    if isGuessSlot, item.type == "futures", let f = item.futures,
                                       f.status != "closed", f.status != "resolved",
                                       let leaderProbability = f.topOutcomes?.first?.probability,
                                       leaderProbability < 0.95 {
                                        SwipeToDismiss(
                                            onSwipeLeft: {
                                                recordInteraction(for: item, action: .unlike, source: "swipe")
                                                hideForSession(itemId(item))
                                            },
                                            onSwipeRight: {
                                                recordInteraction(for: item, action: .like, source: "swipe")
                                                hideForSession(itemId(item))
                                            }
                                        ) {
                                            NativeGuessCard(data: f, onNextQuestion: { scrollToNextGuessGrouped(proxy: proxy, after: idx, in: pageGrouped) }, onGuessCompleted: { incrementDaily() })
                                        }
                                    } else if isGuessSlot, item.type == "event", let e = item.event, e.currentOdds?.homeProbability != nil,
                                              e.status != "completed", e.status != "closed" {
                                        SwipeToDismiss(
                                            onSwipeLeft: {
                                                recordInteraction(for: item, action: .unlike, source: "swipe")
                                                hideForSession(itemId(item))
                                            },
                                            onSwipeRight: {
                                                recordInteraction(for: item, action: .like, source: "swipe")
                                                hideForSession(itemId(item))
                                            }
                                        ) {
                                            NativeGuessCard(event: e, onNextQuestion: { scrollToNextGuessGrouped(proxy: proxy, after: idx, in: pageGrouped) }, onGuessCompleted: { incrementDaily() })
                                        }
                                    } else if item.type == "event", let e = item.event {
                                        SwipeToDismiss(
                                            onSwipeLeft: {
                                                recordInteraction(for: item, action: .unlike, source: "swipe")
                                                hideForSession(itemId(item))
                                            },
                                            onSwipeRight: {
                                                recordInteraction(for: item, action: .like, source: "swipe")
                                                hideForSession(itemId(item))
                                            }
                                        ) {
                                            NativeEventDiscoverCard(event: e, feedContext: item.contextSummary ?? item.reason ?? item.headline, expandedContext: item.reason ?? item.headline, navigationPath: $navigationPath, onOpen: {
                                                recordInteraction(for: item, action: .detailOpen, source: "card")
                                            }, onContextExpand: {
                                                recordInteraction(for: item, action: .contextExpand, source: "context")
                                            }, onContextCollapse: {
                                                recordInteraction(for: item, action: .contextCollapse, source: "context")
                                            })
                                        }
                                        .contextMenu { discoverCardMenu(item) }
                                    } else if item.type == "futures", let f = item.futures {
                                        SwipeToDismiss(
                                            onSwipeLeft: {
                                                recordInteraction(for: item, action: .unlike, source: "swipe")
                                                hideForSession(itemId(item))
                                            },
                                            onSwipeRight: {
                                                recordInteraction(for: item, action: .like, source: "swipe")
                                                hideForSession(itemId(item))
                                            }
                                        ) {
                                            NativeFuturesDiscoverCard(data: f, feedContext: item.contextSummary ?? item.reason ?? item.headline, expandedContext: f.hookDescription ?? item.reason ?? item.headline, navigationPath: $navigationPath, onOpen: {
                                                recordInteraction(for: item, action: .detailOpen, source: "card")
                                            }, onContextExpand: {
                                                recordInteraction(for: item, action: .contextExpand, source: "context")
                                            }, onContextCollapse: {
                                                recordInteraction(for: item, action: .contextCollapse, source: "context")
                                            })
                                        }
                                        .contextMenu { discoverCardMenu(item) }
                                    }
                                }
                            }
                            .id(gi.id)
                            .onAppear {
                                trackImpression(for: gi, rank: idx + 1)
                                if idx == pageGrouped.count - 3 && visibleCount < groupedItems.count {
                                    visibleCount += 20
                                }
                                if idx == pageGrouped.count - 5 {
                                    Task { await vm.loadMoreIfNeeded() }
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.bottom)
            }
        }
        }
        .navigationTitle("Discover")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .toolbar {
            ToolbarItem(placement: .automatic) {
                NavigationLink(value: Route.predictionStats) {
                    Label("Stats", systemImage: "chart.bar.fill")
                }
            }
        }
        .onAppear { AnalyticsService.trackScreen(name: "discover", type: "discover") }
        .task {
            if vm.items.isEmpty {
                await vm.load()
            }
            if resolutions.isEmpty {
                if let r = try? await APIClient.shared.fetchResolutions() {
                    resolutions = r.resolutions
                }
            }
        }
        .refreshable {
            visibleCount = 20
            dismissed.removeAll()
            seenImpressions.removeAll()
            await vm.load()
            if let r = try? await APIClient.shared.fetchResolutions() {
                resolutions = r.resolutions
            }
        }
        .sheet(isPresented: $showOnboarding) {
            WelcomeView()
                .onDisappear { UserDefaults.standard.set(true, forKey: "discover_onboarded") }
        }
        .sheet(isPresented: $showChallenge) {
            NativeChallengeSheet(
                items: challengeItems,
                currentIndex: $challengeIndex,
                completed: $challengeComplete,
                onClose: { showChallenge = false },
                onGuessCompleted: { incrementDaily() },
                onComplete: { recordChallengeAction("challenge_complete") }
            )
        }
        .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
    }

    private func scrollToNextGuess(proxy: ScrollViewProxy, after idx: Int, in items: [FeedItem]) {
        let nextGuessIdx = stride(from: idx + 1, to: items.count, by: 1).first { i in
            (i + 1) % 5 == 0
        }
        if let next = nextGuessIdx, next < items.count {
            let targetId = itemId(items[next])
            withAnimation(.easeInOut(duration: 0.3)) {
                proxy.scrollTo(targetId, anchor: .top)
            }
        }
    }

    private func scrollToNextGuessGrouped(proxy: ScrollViewProxy, after idx: Int, in items: [DiscoverGroupedItem]) {
        let nextIdx = stride(from: idx + 1, to: items.count, by: 1).first { i in
            (i + 1) % 5 == 0
        }
        if let next = nextIdx, next < items.count {
            withAnimation(.easeInOut(duration: 0.3)) {
                proxy.scrollTo(items[next].id, anchor: .top)
            }
        }
    }

    private func hideForSession(_ id: String) {
        dismissed.insert(id)
        Self.saveDismissed(dismissed)
        if visibleCount >= max(groupedItems.count - 8, 0) {
            visibleCount += 20
            Task { await vm.loadMoreIfNeeded() }
        }
        if showSwipeHint {
            withAnimation { showSwipeHint = false }
            UserDefaults.standard.set(true, forKey: "discover_swipe_hinted")
        }
    }

    private static func loadDismissed() -> Set<String> {
        Set(UserDefaults.standard.stringArray(forKey: "discover_dismissed") ?? [])
    }

    private static func saveDismissed(_ ids: Set<String>) {
        let recent = Array(ids.suffix(500))
        UserDefaults.standard.set(recent, forKey: "discover_dismissed")
    }

    private static func loadDailyGuesses() -> Int {
        let today = Self.todayKey()
        return UserDefaults.standard.integer(forKey: today)
    }

    private func incrementDaily() {
        let today = Self.todayKey()
        dailyGuesses += 1
        UserDefaults.standard.set(dailyGuesses, forKey: today)
    }

    private static func todayKey() -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        return "daily_guesses_\(fmt.string(from: Date()))"
    }

    private var challengeItems: [FeedItem] {
        groupedItems.compactMap { grouped in
            guard case .single(let item) = grouped else { return nil }
            if item.type == "futures", item.futures?.topOutcomes?.first?.probability != nil {
                return item
            }
            if item.type == "event", item.event?.currentOdds?.homeProbability != nil {
                return item
            }
            return nil
        }
        .prefix(DAILY_GOAL)
        .map { $0 }
    }

    @ViewBuilder
    private func discoverCardMenu(_ item: FeedItem) -> some View {
        CardContextMenu(
            item: item,
            shareURLStyle: .nativeCard,
            showsShareSectionDivider: false,
            onCopyLink: { _ in
                recordInteraction(for: item, action: .share, source: "copy_link")
            },
            onLessLikeThis: {
                recordInteraction(for: item, action: .unlike, source: "context_menu")
                hideForSession(itemId(item))
            }
        )
    }

}

// MARK: - Expandable Context

struct ExpandableNativeContextText: View {
    let text: String
    let expandedText: String?
    let font: Font
    var onExpand: (() -> Void)? = nil
    var onCollapse: (() -> Void)? = nil
    @State private var expanded = false

    private var compactText: String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var fullText: String {
        (expandedText ?? text).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canExpand: Bool {
        fullText != compactText || compactText.count > 130
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(expanded || !canExpand ? fullText : compactText)
                .font(font)
                .foregroundStyle(.secondary)
                .lineLimit(expanded ? nil : 2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)

            if canExpand {
                Button {
                    expanded.toggle()
                    if expanded {
                        onExpand?()
                    } else {
                        onCollapse?()
                    }
                } label: {
                    Text(expanded ? "Show less" : "See more")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.blue)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Group Card

private struct NativeGroupCard: View {
    let title: String
    let items: [FeedItem]
    @State private var expanded = false

    var body: some View {
        VStack(spacing: 0) {
            Button { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } } label: {
                HStack {
                    Text(title)
                        .font(.caption.weight(.bold))
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("\(items.count) markets")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .rotationEffect(.degrees(expanded ? 180 : 0))
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color.secondary.opacity(0.05))
            }
            .buttonStyle(.plain)

            if let primary = items.first, let f = primary.futures {
                NativeCompactFuturesRow(data: f)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
            }

            if expanded {
                ForEach(items.dropFirst(), id: \.id) { item in
                    if let f = item.futures {
                        Divider().padding(.horizontal, 12)
                        NativeCompactFuturesRow(data: f)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                    }
                }
            } else if items.count > 1 {
                Button { withAnimation { expanded = true } } label: {
                    Text("Show \(items.count - 1) more")
                        .font(.caption)
                        .foregroundStyle(.blue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.plain)
            }
        }
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack, lineWidth: 0.5))
    }
}

private struct NativeCompactFuturesRow: View {
    let data: FeedFuturesData

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: data.id)) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(data.name)
                        .font(.caption.weight(.semibold))
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if let leader = data.topOutcomes?.first {
                        Text(leader.name)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer()
                if let leader = data.topOutcomes?.first {
                    Text("\(Int(((leader.probability ?? 0) * 100).rounded()))%")
                        .font(.subheadline.weight(.black).monospacedDigit())
                    MovementBadge(movement: leader.movement)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Guess Card

private enum NativeGuessCardContent {
    case futures(FeedFuturesData)
    case event(FeedEventData)

    var id: Int {
        switch self {
        case .futures(let data): return data.id
        case .event(let event): return event.id
        }
    }

    var actualProbability: Double? {
        switch self {
        case .futures(let data): return data.topOutcomes?.first?.probability
        case .event(let event): return event.currentOdds?.homeProbability ?? 0.5
        }
    }

    var actualPct: Int {
        Int(((actualProbability ?? 0) * 100).rounded())
    }

    var categoryLabel: String? {
        switch self {
        case .futures(let data):
            return data.llmSportCategory
        case .event(let event):
            return event.sportName ?? event.sport ?? "GAME"
        }
    }

    var analyticsCategory: String? {
        switch self {
        case .futures(let data):
            return data.llmSportCategory
        case .event(let event):
            return event.sport?.split(separator: "_").first.map(String.init)
        }
    }

    var contentType: String {
        switch self {
        case .futures: return "futures"
        case .event: return "event"
        }
    }

    var questionPrompt: String {
        switch self {
        case .futures:
            return "Is the current probability higher or lower than"
        case .event(let event):
            return "Is \(Self.shortName(event.homeTeam)) to win higher or lower than"
        }
    }

    var questionSubject: String? {
        switch self {
        case .futures(let data):
            return data.topOutcomes?.first?.name ?? "This outcome"
        case .event:
            return nil
        }
    }

    var resultSubject: String {
        switch self {
        case .futures(let data):
            return data.topOutcomes?.first?.name ?? data.name
        case .event(let event):
            return event.homeTeam
        }
    }

    var detailRoute: Route {
        switch self {
        case .futures(let data): return .futuresDetail(id: data.id)
        case .event(let event): return .eventDetail(id: event.id)
        }
    }

    var detailLabel: String {
        switch self {
        case .futures: return "See full market"
        case .event: return "See full game"
        }
    }

    var thresholdColor: Color {
        switch self {
        case .futures:
            return .primary
        case .event(let event):
            return Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
        }
    }

    var resultColor: Color? {
        switch self {
        case .futures:
            return nil
        case .event(let event):
            return Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
        }
    }

    var animatesResult: Bool {
        switch self {
        case .futures: return true
        case .event: return false
        }
    }

    func shareText(correct: Bool) -> String {
        let result = correct ? "Got it right" : "Missed it"
        switch self {
        case .futures(let data):
            return "\(result)! \(data.name) — \(actualPct)%. Can you beat my streak? bainluck.com/discover"
        case .event(let event):
            return "\(result)! \(event.homeTeam) was \(actualPct)% to win. Can you beat my streak? bainluck.com/discover"
        }
    }

    static func shortName(_ name: String) -> String {
        name.split(separator: " ").last.map(String.init) ?? name
    }
}

struct NativeGuessCard: View {
    private let content: NativeGuessCardContent
    private var onNextQuestion: (() -> Void)? = nil
    private var nextButtonLabel: String = "Next"
    private var onGuessCompleted: (() -> Void)? = nil
    @State private var guess: String? = nil
    @State private var threshold: Int = 50
    @State private var streak: Int? = nil
    @State private var displayPct: Int = 0
    @State private var showShare = false

    init(
        data: FeedFuturesData,
        onNextQuestion: (() -> Void)? = nil,
        nextButtonLabel: String = "Next",
        onGuessCompleted: (() -> Void)? = nil
    ) {
        self.content = .futures(data)
        self.onNextQuestion = onNextQuestion
        self.nextButtonLabel = nextButtonLabel
        self.onGuessCompleted = onGuessCompleted
    }

    init(
        event: FeedEventData,
        onNextQuestion: (() -> Void)? = nil,
        nextButtonLabel: String = "Next",
        onGuessCompleted: (() -> Void)? = nil
    ) {
        self.content = .event(event)
        self.onNextQuestion = onNextQuestion
        self.nextButtonLabel = nextButtonLabel
        self.onGuessCompleted = onGuessCompleted
    }

    private var actualPct: Int { content.actualPct }

    private var correct: Bool {
        guard let g = guess else { return false }
        return g == "higher" ? actualPct > threshold : actualPct < threshold
    }

    private var shareText: String {
        content.shareText(correct: correct)
    }

    private func submitGuess(_ g: String) {
        guard let actualProbability = content.actualProbability else { return }
        guess = g
        displayPct = content.animatesResult ? 0 : actualPct
        let isCorrect = g == "higher" ? actualPct > threshold : actualPct < threshold
        if content.animatesResult {
            withAnimation(.easeOut(duration: 0.6)) { displayPct = actualPct }
        }
        onGuessCompleted?()
        AnalyticsService.trackPredictionSubmit(
            marketId: content.id,
            guess: g,
            threshold: threshold,
            actualProbability: actualProbability,
            correct: isCorrect,
            contentType: content.contentType,
            category: content.analyticsCategory
        )
        Task {
            let request = PredictionRequest(
                marketId: content.id,
                guess: g,
                threshold: threshold,
                actualProbability: actualProbability,
                correct: isCorrect,
                category: content.analyticsCategory
            )
            _ = try? await APIClient.shared.submitPrediction(request)
            if let stats = try? await APIClient.shared.fetchPredictionStats() {
                streak = stats.currentStreak
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            guessHeader(category: content.categoryLabel)

            summaryPanel()

            if guess == nil {
                questionPanel()
                guessButtons()
            } else {
                resultPanel()
                    .sheet(isPresented: $showShare) {
                        ShareSheet(text: shareText)
                    }
            }
        }
        .padding(16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.orange.opacity(0.32), lineWidth: 1.5))
        .shadow(color: .orange.opacity(0.08), radius: 12, x: 0, y: 5)
        .onAppear { generateThreshold() }
    }

    private func guessHeader(category: String?) -> some View {
        HStack {
            Label("What's the probability?", systemImage: "target")
                .font(.system(size: 11, weight: .heavy))
                .tracking(0.8)
                .foregroundStyle(.orange)
                .textCase(.uppercase)
            Spacer()
            if let category {
                Text(category.uppercased())
                    .font(.system(size: 9, weight: .heavy))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Color.secondary.opacity(0.10), in: Capsule())
            }
        }
    }

    @ViewBuilder
    private func summaryPanel() -> some View {
        switch content {
        case .futures(let data):
            VStack(alignment: .leading, spacing: 8) {
                Text(data.name)
                    .font(.headline.weight(.bold))
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let leader = data.topOutcomes?.first {
                    Text(leader.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        case .event(let event):
            matchupPanel(event: event)
        }
    }

    private func questionPanel() -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(content.questionPrompt)
                .font(.caption)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 4) {
                Text("\(threshold)%")
                    .font(.system(size: 46, weight: .black, design: .rounded).monospacedDigit())
                    .foregroundStyle(content.thresholdColor)
                if let subject = content.questionSubject {
                    Text(subject)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .lineLimit(4)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
    }

    private func guessButtons() -> some View {
        HStack(spacing: 12) {
            guessButton(label: "Higher", systemImage: "arrow.up", color: .green) {
                submitGuess("higher")
            }
            guessButton(label: "Lower", systemImage: "arrow.down", color: .red) {
                submitGuess("lower")
            }
        }
        .buttonStyle(.plain)
    }

    private func matchupPanel(event: FeedEventData) -> some View {
        let homeColor = Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
        let awayColor = Color(hex: event.awayTeamData?.primaryColor ?? "#64748b")

        return HStack(spacing: 10) {
            teamBadge(name: event.awayTeam, logo: event.awayTeamData?.logoSmall, color: awayColor)

            VStack(spacing: 4) {
                Text(event.status == "live" ? (event.espn?.period ?? "LIVE") : (event.status == "completed" || event.status == "closed" ? "FINAL" : "VS"))
                    .font(.system(size: 9, weight: .heavy))
                    .foregroundStyle(event.status == "live" ? .red : .secondary)
                if let a = event.awayScore, let h = event.homeScore,
                   (event.status == "live" || event.status == "completed" || event.status == "closed") {
                    Text("\(a)-\(h)")
                        .font(.caption.weight(.black).monospacedDigit())
                }
            }
            .frame(width: 42)

            teamBadge(name: event.homeTeam, logo: event.homeTeamData?.logoSmall, color: homeColor)
        }
    }

    private func teamBadge(name: String, logo: String?, color: Color) -> some View {
        VStack(spacing: 6) {
            if let logo, let url = URL(string: logo) {
                AsyncImage(url: url) { img in img.resizable().scaledToFit() } placeholder: { EmptyView() }
                    .frame(width: 36, height: 36)
            } else {
                RoundedRectangle(cornerRadius: 9)
                    .fill(color)
                    .frame(width: 36, height: 36)
            }
            Text(NativeGuessCardContent.shortName(name))
                .font(.caption.weight(.semibold))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }

    private func guessButton(label: String, systemImage: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(label, systemImage: systemImage)
                .font(.subheadline.weight(.heavy))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                .foregroundStyle(color)
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(color.opacity(0.28), lineWidth: 1))
        }
    }

    private func resultPanel() -> some View {
        VStack(spacing: 12) {
            Text(correct ? "Correct" : "Not quite")
                .font(.caption.weight(.heavy))
                .foregroundStyle(correct ? .green : .red)
                .padding(.horizontal, 12)
                .padding(.vertical, 5)
                .background((correct ? Color.green : Color.red).opacity(0.12), in: Capsule())

            resultProbabilityText()

            Text(content.resultSubject)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineLimit(2)

            if let streak, streak > 1 {
                Text("\(streak) correct in a row")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.orange)
            }

            HStack(spacing: 10) {
                NavigationLink(value: content.detailRoute) {
                    Label(content.detailLabel, systemImage: "chart.xyaxis.line")
                        .font(.caption.weight(.bold))
                }
                Button { showShare = true } label: {
                    Label("Share", systemImage: "square.and.arrow.up")
                        .font(.caption.weight(.bold))
                }
                .buttonStyle(.plain)
                if let onNextQuestion {
                    Button { onNextQuestion() } label: {
                        Label(nextButtonLabel, systemImage: nextButtonLabel == "Finish" ? "checkmark" : "arrow.down")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.orange)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(14)
        .background((correct ? Color.green : Color.red).opacity(0.06), in: RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder
    private func resultProbabilityText() -> some View {
        if content.animatesResult {
            Text("\(displayPct)%")
                .font(.system(size: 52, weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(content.resultColor ?? .primary)
                .contentTransition(.numericText())
        } else {
            Text("\(actualPct)%")
                .font(.system(size: 52, weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(content.resultColor ?? .primary)
        }
    }

    private func generateThreshold() {
        let actual = Double(actualPct) / 100.0
        let goHigher = Bool.random()
        let offset = 0.10 + Double.random(in: 0...0.15)
        var t = goHigher ? actual + offset : actual - offset
        t = max(0.05, min(0.95, t))
        if abs(t - actual) < 0.10 {
            t = actual > 0.5 ? actual - offset : actual + offset
            t = max(0.05, min(0.95, t))
        }
        threshold = Int((t * 100).rounded())
    }
}

// MARK: - Swipe to Dismiss

private struct SwipeToDismiss<Content: View>: View {
    let onSwipeLeft: () -> Void
    let onSwipeRight: () -> Void
    @ViewBuilder let content: () -> Content
    @State private var offset: CGFloat = 0
    @State private var removing = false
    @State private var isHorizontalDrag = false

    private var overlayOpacity: Double {
        min(abs(offset) / 150, 1.0)
    }

    var body: some View {
        content()
            .offset(x: offset)
            .opacity(removing ? 0 : 1.0 - abs(offset) / 300)
            .overlay(alignment: offset > 0 ? .leading : .trailing) {
                if isHorizontalDrag && abs(offset) > 20 {
                    ZStack {
                        Capsule()
                            .fill(offset > 0 ? Color.green.opacity(0.15) : Color.red.opacity(0.15))
                            .frame(width: offset > 0 ? 122 : 116, height: 44)
                        Text(offset > 0 ? "More like this" : "Less like this")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(offset > 0 ? .green : .red)
                    }
                    .opacity(overlayOpacity)
                    .padding(.horizontal, 24)
                }
            }
            .simultaneousGesture(
                DragGesture(minimumDistance: 20)
                    .onChanged { v in
                        if !isHorizontalDrag && offset == 0 {
                            isHorizontalDrag = abs(v.translation.width) > abs(v.translation.height)
                        }
                        if isHorizontalDrag {
                            offset = v.translation.width
                        }
                    }
                    .onEnded { v in
                        if isHorizontalDrag && abs(v.translation.width) > 120 {
                            if v.translation.width > 0 {
                                withAnimation(.easeOut(duration: 0.2)) {
                                    offset = 400
                                    removing = true
                                }
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                                    onSwipeRight()
                                }
                            } else {
                                withAnimation(.easeOut(duration: 0.2)) {
                                    offset = -400
                                    removing = true
                                }
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                                    onSwipeLeft()
                                }
                            }
                        } else {
                            withAnimation(.spring(response: 0.3)) { offset = 0 }
                        }
                        isHorizontalDrag = false
                    }
            )
    }
}

// MARK: - Movement Badge

func isTrending(_ data: FeedFuturesData) -> Bool {
    guard let m = data.topOutcomes?.first?.movement else { return false }
    return abs(m) >= 0.05
}

// MARK: - Share Sheet

#if os(iOS)
private struct ShareSheet: UIViewControllerRepresentable {
    let text: String
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [text], applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
#else
private struct ShareSheet: View {
    let text: String
    var body: some View {
        VStack(spacing: 12) {
            Text("Share your prediction")
                .font(.headline)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            Button("Copy") {
                copyToClipboard(text)
            }
        }
        .padding()
        .frame(minWidth: 300)
    }
}
#endif

// MARK: - Movement Badge

struct MovementBadge: View {
    let movement: Double?

    var body: some View {
        if let m = movement, abs(m) >= 0.01 {
            let up = m > 0
            HStack(spacing: 2) {
                Image(systemName: up ? "arrow.up" : "arrow.down")
                    .font(.system(size: 7, weight: .black))
                Text("\(abs(Int((m * 100).rounded())))%")
                    .font(.system(size: 10, weight: .bold).monospacedDigit())
            }
            .foregroundStyle(up ? .green : .red)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background((up ? Color.green : Color.red).opacity(0.15))
            .clipShape(Capsule())
        }
    }
}
