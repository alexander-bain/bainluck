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
    case dismiss
    case share
    case contextExpand
    case contextCollapse
}

private struct NativeDiscoverProfile {
    private static let storageKey = "discover_interaction_profile_native_v1"
    var categoryScores: [String: Double]

    static func load() -> NativeDiscoverProfile {
        let raw = UserDefaults.standard.dictionary(forKey: storageKey) as? [String: Double] ?? [:]
        return NativeDiscoverProfile(categoryScores: raw)
    }

    mutating func record(category: String, action: NativeDiscoverAction) {
        let key = category.lowercased()
        let weight: Double
        switch action {
        case .detailOpen: weight = 1.5
        case .dismiss: weight = -2.0
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

struct DiscoverView: View {
    @StateObject private var vm = DiscoverViewModel()
    @State private var categoryFilter = "all"
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

    private let categories: [(key: String, label: String, emoji: String)] = [
        ("all", "All", "✨"), ("sports", "Sports", "🏆"),
        ("politics", "Politics", "🏛"), ("economics", "Economics", "📈"),
        ("tech", "Tech", "💻"), ("culture", "Culture", "🎭"),
        ("weather", "Weather", "🌤"), ("geopolitics", "World", "🌍"),
    ]

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
            if let leader = f.topOutcomes?.first, (leader.probability ?? 0) >= 0.90 {
                if leader.movement == nil || abs(leader.movement ?? 0) < 0.005 { return true }
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
        case .dismiss: actionName = "dismiss"
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
        let items = vm.items.filter { !isStale($0) && !dismissed.contains(itemId($0)) }
        if categoryFilter == "all" { return items }
        if categoryFilter == "sports" { return items.filter { sportsCats.contains(itemCategory($0)) } }
        return items.filter { itemCategory($0) == categoryFilter }
    }

    private var groupedItems: [DiscoverGroupedItem] {
        var groups: [String: [FeedItem]] = [:]
        var groupOrder: [String] = []
        var result: [DiscoverGroupedItem] = []
        var usedPrefixes: Set<String> = []

        for item in filteredItems {
            if item.type == "futures", let f = item.futures {
                let name = f.name
                let prefix: String
                if let colonIdx = name.firstIndex(of: ":"), name.distance(from: name.startIndex, to: colonIdx) < 30 {
                    prefix = String(name[..<colonIdx]).trimmingCharacters(in: .whitespaces)
                } else {
                    prefix = name.split(separator: " ").prefix(3).joined(separator: " ")
                }
                if groups[prefix] == nil { groupOrder.append(prefix) }
                groups[prefix, default: []].append(item)
            }
        }

        for item in filteredItems {
            if item.type != "futures" {
                result.append(.single(item))
                continue
            }
            let name = item.futures?.name ?? ""
            let prefix: String
            if let colonIdx = name.firstIndex(of: ":"), name.distance(from: name.startIndex, to: colonIdx) < 30 {
                prefix = String(name[..<colonIdx]).trimmingCharacters(in: .whitespaces)
            } else {
                prefix = name.split(separator: " ").prefix(3).joined(separator: " ")
            }
            if usedPrefixes.contains(prefix) { continue }
            usedPrefixes.insert(prefix)
            let group = groups[prefix] ?? [item]
            if group.count >= 2 {
                result.append(.group(title: prefix, items: group))
            } else {
                result.append(.single(group[0]))
            }
        }
        return applyLocalPersonalization(result)
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
        VStack(spacing: 0) {
            // Category chips (sticky — outside ScrollView)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(categories, id: \.key) { cat in
                        Button {
                            withAnimation(.easeInOut(duration: 0.15)) { categoryFilter = cat.key }
                            AnalyticsService.trackDiscoverCategoryFilter(category: cat.key)
                        } label: {
                            HStack(spacing: 3) {
                                Text(cat.emoji)
                                    .font(.system(size: 11))
                                Text(cat.label)
                                    .font(.system(size: 12, weight: categoryFilter == cat.key ? .bold : .medium))
                            }
                            .foregroundStyle(categoryFilter == cat.key ? .white : .secondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(categoryFilter == cat.key ? Color.primary : Color.secondary.opacity(0.08))
                            .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
            .background(.background)

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
                } else if let error = vm.error {
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
                            Text("Swipe cards to dismiss")
                                .font(.caption.weight(.semibold))
                            Text("Tap any card to explore the full market")
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
                                    if isGuessSlot, item.type == "futures", let f = item.futures {
                                        SwipeToDismiss {
                                            recordInteraction(for: item, action: .dismiss)
                                            dismiss(itemId(item))
                                        } content: {
                                            NativeGuessCard(data: f, onNextQuestion: { scrollToNextGuessGrouped(proxy: proxy, after: idx, in: pageGrouped) }, onGuessCompleted: { incrementDaily() })
                                        }
                                    } else if isGuessSlot, item.type == "event", let e = item.event, e.currentOdds?.homeProbability != nil {
                                        SwipeToDismiss {
                                            recordInteraction(for: item, action: .dismiss)
                                            dismiss(itemId(item))
                                        } content: {
                                            NativeEventGuessCard(event: e, onNextQuestion: { scrollToNextGuessGrouped(proxy: proxy, after: idx, in: pageGrouped) }, onGuessCompleted: { incrementDaily() })
                                        }
                                    } else if item.type == "event", let e = item.event {
                                        SwipeToDismiss {
                                            recordInteraction(for: item, action: .dismiss)
                                            dismiss(itemId(item))
                                        } content: {
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
                                        SwipeToDismiss {
                                            recordInteraction(for: item, action: .dismiss)
                                            dismiss(itemId(item))
                                        } content: {
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
            ToolbarItem(placement: .automatic) {
                Menu {
                    let affinities = interactionProfile.topAffinities()
                    if affinities.isEmpty {
                        Text("No local tuning yet")
                    } else {
                        ForEach(affinities.indices, id: \.self) { idx in
                            let category = affinities[idx].0
                            let score = affinities[idx].1
                            Label(
                                "\(category.capitalized) \(score > 0 ? "+" : "")\(String(format: "%.1f", score))",
                                systemImage: score > 0 ? "arrow.up" : "arrow.down"
                            )
                        }
                    }
                    Divider()
                    Button(role: .destructive) {
                        AnalyticsService.trackDiscoverTuningReset(affinityCount: interactionProfile.topAffinities(limit: 20).count)
                        interactionProfile.reset()
                    } label: {
                        Label("Reset Discover Tuning", systemImage: "arrow.counterclockwise")
                    }
                } label: {
                    Label("Discover Tuning", systemImage: "slider.horizontal.3")
                }
            }
        }
        .task {
            await vm.load()
            if let r = try? await APIClient.shared.fetchResolutions() {
                resolutions = r.resolutions
            }
        }
        .refreshable {
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

    private func dismiss(_ id: String) {
        dismissed.insert(id)
        Self.saveDismissed(dismissed)
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
        if let e = item.event {
            let url = eventShareURL(e)
            if let prob = e.currentOdds?.homeProbability {
                Button {
                    let text = "\(e.homeTeam): \(Int(prob * 100))%"
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
            Button {
                recordInteraction(for: item, action: .share, source: "copy_link")
                #if os(macOS)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                #else
                UIPasteboard.general.string = url
                #endif
            } label: {
                Label("Copy Link", systemImage: "link")
            }
            ShareLink(item: URL(string: url)!) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
        } else if let f = item.futures {
            let url = futuresShareURL(f)
            if let leader = f.topOutcomes?.first, let prob = leader.probability {
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
            Button {
                recordInteraction(for: item, action: .share, source: "copy_link")
                #if os(macOS)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                #else
                UIPasteboard.general.string = url
                #endif
            } label: {
                Label("Copy Link", systemImage: "link")
            }
            ShareLink(item: URL(string: url)!) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
        }
        Divider()
        Button(role: .destructive) {
            recordInteraction(for: item, action: .dismiss, source: "context_menu")
            dismiss(itemId(item))
        } label: {
            Label("Dismiss", systemImage: "xmark")
        }
    }

    private func eventShareURL(_ event: FeedEventData) -> String {
        "https://bainluck.com/events/\(event.id)?utm_source=share&utm_medium=native&utm_campaign=card&content_type=event&item_id=\(event.id)"
    }

    private func futuresShareURL(_ market: FeedFuturesData) -> String {
        "https://bainluck.com/futures/\(market.id)?utm_source=share&utm_medium=native&utm_campaign=card&content_type=futures&item_id=\(market.id)"
    }
}

// MARK: - ViewModel

final class DiscoverViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = false
    @Published var error: String?

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
    ]

    @MainActor
    func load() async {
        loading = true
        error = nil
        do {
            let response = try await APIClient.shared.fetchFeed(limit: 200, eventPct: 0.15)
            items = Self.interleave(response.items)
        } catch {
            if items.isEmpty {
                self.error = "Couldn't load Discover. Pull to retry."
            }
        }
        loading = false
    }

    private static func interleave(_ items: [FeedItem]) -> [FeedItem] {
        let sports = items.filter { sportsCategories.contains(category(for: $0)) }
        let nonSports = items.filter { !sportsCategories.contains(category(for: $0)) }
        if nonSports.isEmpty { return items }

        var result: [FeedItem] = []
        var si = 0, ni = 0, sportsSince = 0
        while si < sports.count || ni < nonSports.count {
            if ni < nonSports.count && (sportsSince >= 4 || si >= sports.count) {
                result.append(nonSports[ni]); ni += 1; sportsSince = 0
            } else if si < sports.count {
                result.append(sports[si]); si += 1; sportsSince += 1
            } else { break }
        }
        return result
    }

    private static func category(for item: FeedItem) -> String {
        if let f = item.futures { return f.llmSportCategory?.lowercased() ?? "other" }
        if let e = item.event { return e.sport?.split(separator: "_").first.map(String.init) ?? "other" }
        return "other"
    }
}

// MARK: - Expandable Context

private struct ExpandableNativeContextText: View {
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

// MARK: - Event Card

private struct NativeEventDiscoverCard: View {
    let event: FeedEventData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil

    private var awayColor: Color {
        Color(hex: event.awayTeamData?.primaryColor ?? "#64748b")
    }

    private var homeColor: Color {
        Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
    }

    private var eyebrow: String {
        if event.status == "live" { return "LIVE" }
        if event.status == "completed" || event.status == "closed" { return "FINAL" }
        return (event.sportName ?? event.sport ?? "SPORTS").uppercased()
    }

    private var statusText: String {
        if event.status == "live" { return event.espn?.period ?? "LIVE" }
        if event.status == "completed" || event.status == "closed" {
            if let a = event.awayScore, let h = event.homeScore {
                return "F \(a)-\(h)"
            }
            return "Final"
        }
        return "vs"
    }

    private var contextText: String? {
        if let feedContext, !feedContext.isEmpty { return feedContext }
        if let label = event.highlight?.label, !label.isEmpty { return label }
        if let ei = event.ei, let score = ei.score, score >= 60, let label = ei.label {
            return "Excitement Index \(score): \(label)"
        }
        if event.status == "live" { return "Live probability is moving now" }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                HStack(spacing: 6) {
                    if event.status == "live" {
                        Circle()
                            .fill(Color.red)
                            .frame(width: 7, height: 7)
                    }
                    Text(eyebrow)
                        .font(.system(size: 10, weight: .heavy))
                        .tracking(0.8)
                }
                .foregroundStyle(event.status == "live" ? .red : .secondary)

                Spacer()

                Text(statusText)
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(event.status == "live" ? .red : .secondary)
            }

            HStack(alignment: .center, spacing: 10) {
                teamColumn(
                    name: event.awayTeam,
                    logo: event.awayTeamData?.logoSmall,
                    color: awayColor,
                    probability: event.currentOdds?.awayProbability,
                    score: event.awayScore,
                    alignment: .leading
                )

                Text("vs")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                    .frame(width: 28)

                teamColumn(
                    name: event.homeTeam,
                    logo: event.homeTeamData?.logoSmall,
                    color: homeColor,
                    probability: event.currentOdds?.homeProbability,
                    score: event.homeScore,
                    alignment: .trailing
                )
            }

            if let hp = event.currentOdds?.homeProbability, let ap = event.currentOdds?.awayProbability {
                probabilityBar(awayProbability: ap, homeProbability: hp)
            }

            if let contextText {
                ExpandableNativeContextText(
                    text: contextText,
                    expandedText: expandedContext,
                    font: .caption,
                    onExpand: onContextExpand,
                    onCollapse: onContextCollapse
                )
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.eventDetail(id: event.id))
            onOpen?()
        }
    }

    private func teamColumn(
        name: String,
        logo: String?,
        color: Color,
        probability: Double?,
        score: Int?,
        alignment: HorizontalAlignment
    ) -> some View {
        VStack(alignment: alignment, spacing: 7) {
            if let logo, let url = URL(string: logo) {
                AsyncImage(url: url) { img in img.resizable().scaledToFit() } placeholder: { EmptyView() }
                    .frame(width: 42, height: 42)
            } else {
                RoundedRectangle(cornerRadius: 10)
                    .fill(color)
                    .frame(width: 42, height: 42)
                    .overlay(
                        Text(String(name.split(separator: " ").last ?? "").prefix(3).uppercased())
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.white)
                    )
            }

            Text(name)
                .font(.subheadline.weight(.bold))
                .lineLimit(2)
                .multilineTextAlignment(alignment == .trailing ? .trailing : .leading)
                .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)

            HStack(spacing: 6) {
                if let probability {
                    Text(formatProbability(probability))
                        .font(.title3.weight(.black).monospacedDigit())
                        .foregroundStyle(color)
                }
                if let score {
                    Text("\(score)")
                        .font(.caption.weight(.heavy).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.10))
                        .clipShape(Capsule())
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func probabilityBar(awayProbability: Double, homeProbability: Double) -> some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                Rectangle()
                    .fill(awayColor)
                    .frame(width: max(3, geo.size.width * awayProbability))
                Rectangle()
                    .fill(homeColor)
                    .frame(width: max(3, geo.size.width * homeProbability))
            }
            .clipShape(Capsule())
        }
        .frame(height: 8)
        .background(Color.barTrack.opacity(0.25), in: Capsule())
    }
}

// MARK: - Category Gradients

private let categoryGradients: [String: (Color, Color)] = [
    "basketball": (Color(red: 0.49, green: 0.18, blue: 0.07), Color(red: 0.76, green: 0.25, blue: 0.05)),
    "football": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.08, green: 0.50, blue: 0.24)),
    "baseball": (Color(red: 0.50, green: 0.11, blue: 0.11), Color(red: 0.73, green: 0.11, blue: 0.11)),
    "hockey": (Color(red: 0.12, green: 0.23, blue: 0.37), Color(red: 0.15, green: 0.39, blue: 0.92)),
    "soccer": (Color(red: 0.02, green: 0.31, blue: 0.23), Color(red: 0.02, green: 0.60, blue: 0.40)),
    "golf": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.09, green: 0.40, blue: 0.20)),
    "mma": (Color(red: 0.27, green: 0.04, blue: 0.04), Color(red: 0.60, green: 0.11, blue: 0.11)),
    "economics": (Color(red: 0.18, green: 0.06, blue: 0.40), Color(red: 0.49, green: 0.23, blue: 0.93)),
    "politics": (Color(red: 0.12, green: 0.11, blue: 0.29), Color(red: 0.26, green: 0.22, blue: 0.79)),
    "tech": (Color(red: 0.03, green: 0.20, blue: 0.27), Color(red: 0.03, green: 0.57, blue: 0.70)),
    "culture": (Color(red: 0.51, green: 0.09, blue: 0.26), Color(red: 0.86, green: 0.15, blue: 0.47)),
    "weather": (Color(red: 0.05, green: 0.29, blue: 0.43), Color(red: 0.01, green: 0.52, blue: 0.78)),
    "entertainment": (Color(red: 0.44, green: 0.10, blue: 0.46), Color(red: 0.75, green: 0.15, blue: 0.83)),
    "cricket": (Color(red: 0.07, green: 0.31, blue: 0.29), Color(red: 0.08, green: 0.72, blue: 0.65)),
    "olympics": (Color(red: 0.47, green: 0.21, blue: 0.06), Color(red: 0.85, green: 0.47, blue: 0.02)),
]

private let defaultGradient: (Color, Color) = (Color(red: 0.06, green: 0.09, blue: 0.16), Color(red: 0.12, green: 0.16, blue: 0.24))

// MARK: - Futures Card

private struct NativeFuturesDiscoverCard: View {
    let data: FeedFuturesData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil

    private var gradient: (Color, Color) {
        categoryGradients[data.llmSportCategory?.lowercased() ?? ""] ?? defaultGradient
    }

    private var categoryLabel: String {
        (data.sportName ?? data.llmSportCategory ?? "Market").uppercased()
    }

    private var leader: FeedFuturesOutcome? {
        data.topOutcomes?.first
    }

    private var leaderProbability: Double {
        leader?.probability ?? 0
    }

    private var contextText: String? {
        if let feedContext, !feedContext.isEmpty { return feedContext }
        if let hook = data.hookDescription, !hook.isEmpty { return hook }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                heroBackground
                    .frame(height: 170)
                    .clipped()

                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text(categoryLabel)
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())

                        Spacer()

                        if isTrending(data) {
                            Label("Trending", systemImage: "flame.fill")
                                .font(.system(size: 9, weight: .heavy))
                                .foregroundStyle(.orange)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.black.opacity(0.24), in: Capsule())
                        }
                    }

                    Spacer(minLength: 16)

                    if let leader {
                        HStack(alignment: .bottom, spacing: 10) {
                            Text("\(Int((leaderProbability * 100).rounded()))%")
                                .font(.system(size: 52, weight: .black).monospacedDigit())
                                .minimumScaleFactor(0.76)
                                .foregroundStyle(.white)
                                .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 3)

                            MovementBadge(movement: leader.movement)
                                .padding(.bottom, 8)
                        }

                        Text(leader.name)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white.opacity(0.92))
                            .lineLimit(2)
                    }
                }
                .padding(14)
            }
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18))

            VStack(alignment: .leading, spacing: 12) {
                Text(data.name)
                    .font(.headline.weight(.bold))
                    .lineLimit(2)

                if let contextText {
                    ExpandableNativeContextText(
                        text: contextText,
                        expandedText: expandedContext ?? data.hookDescription,
                        font: .subheadline,
                        onExpand: onContextExpand,
                        onCollapse: onContextCollapse
                    )
                }

                if let outcomes = data.topOutcomes, outcomes.count > 1 {
                    VStack(spacing: 7) {
                        ForEach(Array(outcomes.prefix(3).enumerated()), id: \.element.id) { idx, outcome in
                            outcomeRow(outcome, isLeader: idx == 0)
                        }
                    }
                }

                HStack(spacing: 8) {
                    if let src = data.source {
                        Text(src.uppercased())
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.10), in: Capsule())
                    }

                    if let count = data.sourceCount, count > 1 {
                        Text("\(count) SOURCES")
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.secondary.opacity(0.10), in: Capsule())
                    }

                    Spacer()
                }
            }
            .padding(14)
        }
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.07), radius: 12, x: 0, y: 5)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.futuresDetail(id: data.id))
            onOpen?()
        }
    }

    @ViewBuilder
    private var heroBackground: some View {
        if let imageUrl = data.imageUrl, let url = URL(string: imageUrl) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                        .overlay(
                            LinearGradient(
                                colors: [.black.opacity(0.08), .black.opacity(0.78)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                default:
                    LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                }
            }
        } else {
            LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                .overlay(
                    Text(categoryEmoji(data.llmSportCategory))
                        .font(.system(size: 96))
                        .opacity(0.10)
                )
        }
    }

    private func outcomeRow(_ outcome: FeedFuturesOutcome, isLeader: Bool) -> some View {
        HStack(spacing: 8) {
            Text(outcome.name)
                .font(.caption.weight(isLeader ? .semibold : .regular))
                .lineLimit(1)
                .frame(width: 112, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.12))
                    Capsule()
                        .fill(isLeader ? Color.blue : Color.secondary.opacity(0.35))
                        .frame(width: max(3, geo.size.width * (outcome.probability ?? 0)))
                }
            }
            .frame(height: 7)

            Text("\(Int(((outcome.probability ?? 0) * 100).rounded()))%")
                .font(.caption.weight(.bold).monospacedDigit())
                .frame(width: 34, alignment: .trailing)
        }
    }

    private func categoryEmoji(_ category: String?) -> String {
        switch category?.lowercased() {
        case "politics": return "🏛"
        case "geopolitics": return "🌍"
        case "economics": return "📈"
        case "tech": return "💻"
        case "entertainment": return "🎬"
        case "culture": return "🎭"
        case "weather": return "🌤"
        case "health": return "🏥"
        default: return "🍀"
        }
    }
}

// MARK: - Daily Challenge Card

private let DAILY_GOAL = 5

private struct NativeDailyChallengeCard: View {
    let guessesToday: Int
    var onStart: (() -> Void)? = nil
    private var completed: Bool { guessesToday >= DAILY_GOAL }
    private var progress: Double { min(Double(guessesToday) / Double(DAILY_GOAL), 1.0) }

    var body: some View {
        HStack(spacing: 12) {
            Text(completed ? "🏆" : "🎯")
                .font(.system(size: 28))

            VStack(alignment: .leading, spacing: 2) {
                Text(completed ? "Daily Challenge Complete!" : "Today's Challenge")
                    .font(.subheadline.weight(.bold))
                Text(completed
                     ? "Come back tomorrow for a new challenge"
                     : "Tap Higher or Lower on \(DAILY_GOAL) cards · \(guessesToday)/\(DAILY_GOAL)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if completed {
                Image(systemName: "checkmark.circle.fill")
                    .font(.title2)
                    .foregroundStyle(.green)
            } else {
                ZStack {
                    Circle()
                        .stroke(Color.secondary.opacity(0.2), lineWidth: 3)
                    Circle()
                        .trim(from: 0, to: progress)
                        .stroke(Color.orange, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                        .animation(.easeInOut(duration: 0.5), value: progress)
                    Text("\(guessesToday)")
                        .font(.caption.weight(.bold).monospacedDigit())
                }
                .frame(width: 40, height: 40)

                Button {
                    onStart?()
                } label: {
                    Text("Play")
                        .font(.caption.weight(.heavy))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.orange, in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16)
            .stroke(completed ? Color.green.opacity(0.5) : Color.orange.opacity(0.3), lineWidth: 2))
    }
}

private struct NativeChallengeSheet: View {
    let items: [FeedItem]
    @Binding var currentIndex: Int
    @Binding var completed: Bool
    let onClose: () -> Void
    let onGuessCompleted: () -> Void
    let onComplete: () -> Void
    @State private var completionRecorded = false

    private var goal: Int {
        min(DAILY_GOAL, max(items.count, 1))
    }

    private var progress: Double {
        completed ? 1.0 : min(Double(currentIndex) / Double(goal), 1.0)
    }

    private var currentItem: FeedItem? {
        guard currentIndex < items.count else { return nil }
        return items[currentIndex]
    }

    private var isLastQuestion: Bool {
        currentIndex >= goal - 1
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Today's Challenge")
                            .font(.headline.weight(.black))
                        Text(completed ? "Set complete" : "Question \(min(currentIndex + 1, goal)) of \(goal)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Button(action: onClose) {
                        Image(systemName: "xmark")
                            .font(.caption.weight(.heavy))
                            .foregroundStyle(.secondary)
                            .frame(width: 32, height: 32)
                            .background(Color.secondary.opacity(0.10), in: Circle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal)
                .padding(.top, 16)

                ProgressView(value: progress)
                    .tint(.orange)
                    .padding(.horizontal)
                    .padding(.top, 12)
                    .padding(.bottom, 16)

                ScrollView {
                    VStack(spacing: 16) {
                        if completed {
                            VStack(spacing: 14) {
                                Text("🏆")
                                    .font(.system(size: 44))
                                Text("Challenge complete")
                                    .font(.title3.weight(.black))
                                Text("Your predictions are counted. Come back tomorrow for a fresh set.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .multilineTextAlignment(.center)
                                Button("Back to Discover", action: onClose)
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 13)
                                    .background(Color.primary, in: RoundedRectangle(cornerRadius: 14))
                            }
                            .padding(20)
                            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 20))
                        } else if let item = currentItem {
                            challengeCard(for: item)
                        } else {
                            VStack(spacing: 12) {
                                Text("No challenge cards right now")
                                    .font(.headline.weight(.bold))
                                Text("Check back after the feed refreshes.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Button("Back to Discover", action: onClose)
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 13)
                                    .background(Color.primary, in: RoundedRectangle(cornerRadius: 14))
                            }
                            .padding(20)
                            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 20))
                        }
                    }
                    .padding()
                }
            }
            .background(Color.groupedBackground.ignoresSafeArea())
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
    }

    @ViewBuilder
    private func challengeCard(for item: FeedItem) -> some View {
        let label = isLastQuestion ? "Finish" : "Next"
        if item.type == "futures", let futures = item.futures {
            NativeGuessCard(
                data: futures,
                onNextQuestion: advance,
                nextButtonLabel: label,
                onGuessCompleted: onGuessCompleted
            )
        } else if item.type == "event", let event = item.event {
            NativeEventGuessCard(
                event: event,
                onNextQuestion: advance,
                nextButtonLabel: label,
                onGuessCompleted: onGuessCompleted
            )
        }
    }

    private func advance() {
        let next = currentIndex + 1
        if next >= items.count || next >= DAILY_GOAL {
            completed = true
            if !completionRecorded {
                completionRecorded = true
                onComplete()
            }
            return
        }
        currentIndex = next
    }
}

// MARK: - Resolution Card

private struct NativeResolutionCard: View {
    let resolution: Resolution

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Text("📋")
                Text("MARKET RESOLVED")
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1)
                    .foregroundStyle(.purple)
                Spacer()
            }

            Text(resolution.marketName)
                .font(.subheadline.weight(.bold))
                .lineLimit(2)

            Text(resolution.correct ? "✓ You got it right!" : "✗ Better luck next time")
                .font(.caption.weight(.bold))
                .foregroundStyle(resolution.correct ? .green : .red)
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background((resolution.correct ? Color.green : Color.red).opacity(0.1))
                .clipShape(Capsule())

            Text("You guessed \(resolution.guess) than \(resolution.threshold)% — final: \(resolution.actual)%")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.purple.opacity(0.3), lineWidth: 2))
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
                        .lineLimit(1)
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
                        .lineLimit(1)
                    if let leader = data.topOutcomes?.first {
                        Text(leader.name)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
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

private struct NativeGuessCard: View {
    let data: FeedFuturesData
    var onNextQuestion: (() -> Void)? = nil
    var nextButtonLabel: String = "Next"
    var onGuessCompleted: (() -> Void)? = nil
    @State private var guess: String? = nil
    @State private var threshold: Int = 50
    @State private var streak: Int? = nil
    @State private var displayPct: Int = 0
    @State private var showShare = false

    private var leader: FeedFuturesOutcome? { data.topOutcomes?.first }
    private var actualPct: Int { Int(((leader?.probability ?? 0) * 100).rounded()) }
    private var correct: Bool {
        guard let g = guess else { return false }
        return g == "higher" ? actualPct > threshold : actualPct < threshold
    }

    private func submitGuess(_ g: String) {
        guess = g
        displayPct = 0
        let isCorrect = g == "higher" ? actualPct > threshold : actualPct < threshold
        withAnimation(.easeOut(duration: 0.6)) { displayPct = actualPct }
        onGuessCompleted?()
        Task {
            let request = PredictionRequest(
                marketId: data.id,
                guess: g,
                threshold: threshold,
                actualProbability: leader?.probability ?? 0,
                correct: isCorrect,
                category: data.llmSportCategory
            )
            _ = try? await APIClient.shared.submitPrediction(request)
            if let stats = try? await APIClient.shared.fetchPredictionStats() {
                streak = stats.currentStreak
            }
        }
    }

    private var shareText: String {
        let result = correct ? "Got it right" : "Missed it"
        return "\(result)! \(data.name) — \(actualPct)%. Can you beat my streak? bainluck.com/discover"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            guessHeader(category: data.llmSportCategory)

            VStack(alignment: .leading, spacing: 8) {
                Text(data.name)
                    .font(.headline.weight(.bold))
                    .lineLimit(2)

                if let leader {
                    Text(leader.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            if guess == nil {
                questionPanel(subject: leader?.name ?? "This outcome")
                guessButtons()
            } else {
                resultPanel(subject: leader?.name ?? data.name, detailRoute: .futuresDetail(id: data.id), detailLabel: "See full market")
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
            Label("What are the odds?", systemImage: "target")
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

    private func questionPanel(subject: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Is the current probability higher or lower than")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("\(threshold)%")
                    .font(.system(size: 46, weight: .black, design: .rounded).monospacedDigit())
                    .foregroundStyle(.primary)
                Text(subject)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
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

    private func resultPanel(subject: String, detailRoute: Route, detailLabel: String) -> some View {
        VStack(spacing: 12) {
            Text(correct ? "Correct" : "Not quite")
                .font(.caption.weight(.heavy))
                .foregroundStyle(correct ? .green : .red)
                .padding(.horizontal, 12)
                .padding(.vertical, 5)
                .background((correct ? Color.green : Color.red).opacity(0.12), in: Capsule())

            Text("\(displayPct)%")
                .font(.system(size: 52, weight: .black, design: .rounded).monospacedDigit())
                .contentTransition(.numericText())

            Text(subject)
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
                NavigationLink(value: detailRoute) {
                    Label(detailLabel, systemImage: "chart.xyaxis.line")
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

// MARK: - Event Guess Card

private struct NativeEventGuessCard: View {
    let event: FeedEventData
    var onNextQuestion: (() -> Void)? = nil
    var nextButtonLabel: String = "Next"
    var onGuessCompleted: (() -> Void)? = nil
    @State private var guess: String? = nil
    @State private var threshold: Int = 50
    @State private var streak: Int? = nil
    @State private var showShare = false

    private var actualPct: Int { Int(((event.currentOdds?.homeProbability ?? 0.5) * 100).rounded()) }
    private var correct: Bool {
        guard let g = guess else { return false }
        return g == "higher" ? actualPct > threshold : actualPct < threshold
    }

    private var homeColor: Color {
        Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
    }

    private var awayColor: Color {
        Color(hex: event.awayTeamData?.primaryColor ?? "#64748b")
    }

    private var shareText: String {
        let result = correct ? "Got it right" : "Missed it"
        return "\(result)! \(event.homeTeam) was \(actualPct)% to win. Can you beat my streak? bainluck.com/discover"
    }

    private func submitGuess(_ g: String) {
        guess = g
        let isCorrect = g == "higher" ? actualPct > threshold : actualPct < threshold
        onGuessCompleted?()
        Task {
            let request = PredictionRequest(
                marketId: event.id,
                guess: g,
                threshold: threshold,
                actualProbability: event.currentOdds?.homeProbability ?? 0.5,
                correct: isCorrect,
                category: event.sport?.split(separator: "_").first.map(String.init)
            )
            _ = try? await APIClient.shared.submitPrediction(request)
            if let stats = try? await APIClient.shared.fetchPredictionStats() {
                streak = stats.currentStreak
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("What are the odds?", systemImage: "target")
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(0.8)
                    .foregroundStyle(.orange)
                    .textCase(.uppercase)
                Spacer()
                Text((event.sportName ?? event.sport ?? "GAME").uppercased())
                    .font(.system(size: 9, weight: .heavy))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Color.secondary.opacity(0.10), in: Capsule())
            }

            matchupPanel()

            if guess == nil {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Is \(shortName(event.homeTeam)) to win higher or lower than")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("\(threshold)%")
                        .font(.system(size: 46, weight: .black, design: .rounded).monospacedDigit())
                        .foregroundStyle(homeColor)
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))

                HStack(spacing: 12) {
                    guessButton(label: "Higher", systemImage: "arrow.up", color: .green) {
                        submitGuess("higher")
                    }
                    guessButton(label: "Lower", systemImage: "arrow.down", color: .red) {
                        submitGuess("lower")
                    }
                }
                .buttonStyle(.plain)
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

    private func matchupPanel() -> some View {
        HStack(spacing: 10) {
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
            Text(shortName(name))
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

            Text("\(actualPct)%")
                .font(.system(size: 52, weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(homeColor)

            Text(event.homeTeam)
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
                NavigationLink(value: Route.eventDetail(id: event.id)) {
                    Label("See full game", systemImage: "chart.xyaxis.line")
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

    private func shortName(_ name: String) -> String {
        name.split(separator: " ").last.map(String.init) ?? name
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
    let onDismiss: () -> Void
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
                        Circle()
                            .fill(offset > 0 ? Color.green.opacity(0.15) : Color.red.opacity(0.15))
                            .frame(width: 64, height: 64)
                        Image(systemName: offset > 0 ? "checkmark" : "xmark")
                            .font(.title.weight(.bold))
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
                            withAnimation(.easeOut(duration: 0.2)) {
                                offset = v.translation.width > 0 ? 400 : -400
                                removing = true
                            }
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                                onDismiss()
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

private func isTrending(_ data: FeedFuturesData) -> Bool {
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
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(text, forType: .string)
            }
        }
        .padding()
        .frame(minWidth: 300)
    }
}
#endif

// MARK: - Movement Badge

private struct MovementBadge: View {
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
