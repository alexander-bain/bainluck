import SwiftUI
import Combine

private enum DiscoverGroupedItem: Identifiable {
    case single(FeedItem)
    case group(title: String, items: [FeedItem], kind: String? = nil, theme: String? = nil)

    var id: String {
        switch self {
        case .single(let item): return item.id
        case .group(let title, _, let kind, let theme): return "group-\(kind ?? "related")-\(theme ?? title)"
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
    private static let categoryCooldownScore = -3.0
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

    func suppresses(category: String) -> Bool {
        (categoryScores[category.lowercased()] ?? 0) <= Self.categoryCooldownScore
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
    // Soft, decaying dismiss store (#1221): id -> dismissedAt (epoch seconds).
    // Left/right swipe is a downrank input, not a permanent client-side
    // blackhole — entries expire after `dismissTTL` (matching web's 14-day
    // story-key suppression), the store is capped, and the feed floor below
    // backfills the least-recently-dismissed rather than let the visible feed
    // collapse to ~2 cards.
    @State private var dismissedAt: [String: TimeInterval] = Self.loadDismissed()

    // Never let client-side filtering (dismiss + group-collapse) shrink the
    // rendered feed below this many cards when the API returned more (#1221).
    private static let feedFloor = 8
    private static let dismissTTL: TimeInterval = 14 * 24 * 3600
    private static let dismissCap = 500
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
        if item.type == "bundle", let bundle = item.bundle {
            // Derive category from the first ELIGIBLE child, never a stale raw
            // first child (C29 P2). `filteredItems` sanitizes bundles up front, so
            // this is normally already the first child; the explicit admit keeps
            // the derivation correct for any caller that passes a raw bundle.
            if let first = Self.eligibleBundleItems(bundle).first ?? bundle.items.first {
                return itemCategory(first)
            }
        }
        if item.type == "concept", let c = item.concept {
            return c.domain?.lowercased() ?? "other"
        }
        return "golf"
    }

    /// Pure, testable staleness predicate powering the Discover stale gate
    /// (L2-191). Terminal/date/extreme rot judged per card type, independent of
    /// content: resolved/closed futures, past-resolution futures, expired FINAL
    /// games, and near-decided/extreme probabilities. `now` is injectable so
    /// tests are deterministic and don't straddle a date boundary (gotcha #44).
    static func isStaleItem(_ item: FeedItem, now: Date = Date()) -> Bool {
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
            if let rd = f.resolutionDate, let d = rd.asDate, d < now { return true }
        }
        if let e = item.event {
            if e.status == "completed" || e.status == "closed" {
                if let ct = e.commenceTime, let d = ct.asDate {
                    return now.timeIntervalSince(d) > 8 * 3600
                }
            }
        }
        return false
    }

    /// Eligible = not stale. The stale gate has NO all-stale restoration path
    /// ("settled means settled", L2-191): an all-stale input returns [] so the
    /// view falls to the graceful end state rather than resurrecting settled
    /// cards or minting a guess slot from them.
    static func eligibleItems(_ items: [FeedItem], now: Date = Date()) -> [FeedItem] {
        items.filter { !isStaleItem($0, now: now) }
    }

    /// Recursively apply the same lifecycle stale gate to an API bundle's
    /// children (C26 P1). A bundle FeedItem is itself always "eligible" — it
    /// carries no event/futures/date of its own — so without this its children
    /// bypass `isStaleItem` and a resolved/closed/past-resolution/extreme child
    /// can still render as a live probability inside `NativeGroupCard`. Returns
    /// only eligible children; an all-stale bundle yields `[]` so `groupedItems`
    /// drops it entirely ("settled means settled", no restoration path).
    static func eligibleBundleItems(_ bundle: FeedBundle, now: Date = Date()) -> [FeedItem] {
        eligibleItems(bundle.items, now: now)
    }

    /// Recursively admit bundle children through the lifecycle stale gate BEFORE
    /// any category derivation, cooldown, dismissal, personalization, interleave,
    /// or grouping step (C29 P2). Each bundle FeedItem is rebuilt to carry ONLY
    /// its eligible children — so every downstream consumer (category/cooldown/
    /// interleave/grouping/rendering/analytics) reads the first ELIGIBLE child,
    /// never a stale raw first child that could mis-categorize the bundle or steer
    /// a neighbor's cooldown/interleave slot. An all-ineligible bundle is dropped
    /// entirely here ("settled means settled" — no restoration path), so it can
    /// never suppress an adjacent card. Ordinary (non-bundle) items pass through
    /// untouched; their own stale gate runs later in `filteredItems`.
    static func sanitizedFeedItems(_ items: [FeedItem], now: Date = Date()) -> [FeedItem] {
        items.compactMap { item in
            guard item.type == "bundle", let bundle = item.bundle else { return item }
            let eligibleChildren = eligibleItems(bundle.items, now: now)
            if eligibleChildren.isEmpty { return nil }
            return item.withBundle(bundle.withItems(eligibleChildren))
        }
    }

    private func itemId(_ item: FeedItem) -> String {
        if let e = item.event { return "event-\(e.id)" }
        if let f = item.futures { return "futures-\(f.id)" }
        if let t = item.tournament { return "tournament-\(t.key)" }
        if let c = item.concept { return "concept-\(c.key)" }
        if let b = item.bundle { return "bundle-\(b.id)" }
        return UUID().uuidString
    }

    private func itemType(_ item: FeedItem) -> String {
        if item.event != nil { return "event" }
        if item.futures != nil { return "futures" }
        if item.bundle != nil { return "bundle" }
        return item.type
    }

    private func rawItemId(_ item: FeedItem) -> String {
        if let e = item.event { return String(e.id) }
        if let f = item.futures { return String(f.id) }
        if let t = item.tournament { return t.key }
        if let c = item.concept { return c.key }
        if let b = item.bundle { return b.id }
        return item.id
    }

    private func itemName(_ item: FeedItem) -> String? {
        if let e = item.event { return "\(e.awayTeam) vs \(e.homeTeam)" }
        if let f = item.futures { return f.name }
        if let t = item.tournament { return t.name }
        if let c = item.concept { return c.name }
        if let b = item.bundle { return b.title }
        return nil
    }

    private func primaryItem(_ grouped: DiscoverGroupedItem) -> FeedItem? {
        switch grouped {
        case .single(let item): return item
        case .group(_, let items, _, _): return items.first
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
        // Compose in the #1221-ruled order: stale first, dismiss-decay second,
        // floor last. Dismiss/cooldown keep graceful fallbacks; the stale gate
        // does NOT — "settled means settled" (L2-191): an all-stale payload must
        // collapse to an honest end state, never restore resolved markets.

        // 0. Sanitize bundles FIRST (C29 P2): recursively admit each bundle's
        // children through the stale gate and rebuild the bundle so every step
        // below — category derivation, dismiss, cooldown, interleave — sees only
        // eligible children and derives category from the first ELIGIBLE child.
        // All-ineligible bundles disappear here, before they can steer a
        // neighbor's cooldown/interleave slot.
        let sanitized = Self.sanitizedFeedItems(vm.items)

        // 1. Drop settled/FINAL rot (resolved futures, completed games, past
        // resolution dates) so a near-coin-flip season-series or a finished game
        // never leads the feed (Queue #238). No all-stale restoration path: if
        // every card is stale, filteredItems empties and the view renders the
        // graceful end state (L2-191 Item 2) instead of resurrecting settled
        // cards or minting a guess slot from them.
        let staleBase = Self.eligibleItems(sanitized)

        // 2. Soft, decaying dismiss (#1221): filter dismissed ids, but if that
        // would shrink the feed below `feedFloor` while more cards exist,
        // backfill the least-recently-dismissed so a heavy dismiss history can't
        // collapse the feed to ~2 cards. Never backfills stale rot — staleBase
        // already excludes it.
        let kept = staleBase.filter { dismissedAt[itemId($0)] == nil }
        let dismissBase: [FeedItem]
        if kept.count >= Self.feedFloor || kept.count == staleBase.count {
            dismissBase = kept
        } else {
            let backfill = staleBase
                .filter { dismissedAt[itemId($0)] != nil }
                .sorted { (dismissedAt[itemId($0)] ?? 0) < (dismissedAt[itemId($1)] ?? 0) }
                .prefix(Self.feedFloor - kept.count)
            dismissBase = kept + backfill
        }

        // 3. Category cooldown (soft). Fallback: keep base if it empties.
        let cooldownFiltered = dismissBase.filter { !interactionProfile.suppresses(category: itemCategory($0)) }
        return cooldownFiltered.isEmpty ? dismissBase : cooldownFiltered
    }

    private var groupedItems: [DiscoverGroupedItem] {
        var groups: [String: [FeedItem]] = [:]
        var groupTitles: [String: String] = [:]
        var result: [DiscoverGroupedItem] = []
        var usedPrefixes: Set<String> = []

        let mixedItems = interleave(filteredItems)

        for item in mixedItems {
            if item.type == "bundle" { continue }
            guard item.type == "futures", let grouping = futuresGrouping(for: item) else { continue }
            if groups[grouping.key] == nil {
                groupTitles[grouping.key] = grouping.title
            }
            groups[grouping.key, default: []].append(item)
        }

        for item in mixedItems {
            if item.type == "bundle", let bundle = item.bundle {
                // Recursively admit bundle children through the stale gate (C26
                // P1): drop settled/closed/past/extreme children before the card
                // ever sees them, and drop the whole bundle if nothing eligible
                // remains rather than rendering a stale comparison.
                let eligibleChildren = Self.eligibleBundleItems(bundle)
                if eligibleChildren.isEmpty { continue }
                result.append(.group(
                    title: bundle.title,
                    items: eligibleChildren,
                    kind: bundle.kind,
                    theme: bundle.comparisonTheme
                ))
                continue
            }
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
        return interleaveGrouped(applyLocalPersonalization(enforceGroupFloor(result)))
    }

    private func groupItemCount(_ item: DiscoverGroupedItem) -> Int {
        if case .group(_, let items, _, _) = item { return items.count }
        return 1
    }

    /// Futures group-collapse must not shrink the visible feed below `feedFloor`
    /// (#1221). When a page of many small futures groups collapses too far, expand
    /// the largest prefix/group-id groups (kind == nil — never the API's intentional
    /// comparison bundles) back into singles until the floor is met or nothing is
    /// left to expand.
    private func enforceGroupFloor(_ items: [DiscoverGroupedItem]) -> [DiscoverGroupedItem] {
        var result = items
        while result.count < Self.feedFloor {
            let expandable = result.enumerated().filter { entry in
                if case .group(_, let its, let kind, _) = entry.element {
                    return kind == nil && its.count >= 2
                }
                return false
            }
            guard let target = expandable.max(by: { groupItemCount($0.element) < groupItemCount($1.element) }) else {
                break
            }
            if case .group(_, let its, _, _) = result[target.offset] {
                result.replaceSubrange(target.offset...target.offset, with: its.map { DiscoverGroupedItem.single($0) })
            } else {
                break
            }
        }
        return result
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

    @Environment(\.horizontalSizeClass) private var sizeClass

    /// Max content width — phone-style on compact, wider on iPad/Mac
    private var contentMaxWidth: CGFloat {
        #if os(macOS)
        return 800
        #else
        return sizeClass == .regular ? 800 : .infinity
        #endif
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
        VStack(spacing: 0) {
        ScrollView {
            VStack(spacing: 0) {
                // Compute the eligible, grouped feed once per body pass — reused
                // by the card grid, pagination trigger, and the empty-eligible
                // end state below (L2-191).
                let grouped = groupedItems
                // Resolution digest — collapse N resolution notes into ONE
                // card (#902 item 8) instead of stacking up to 3 at feed top.
                if !resolutions.isEmpty {
                    NavigationLink(value: Route.predictionStats) {
                        NativeResolutionDigestCard(
                            total: resolutions.count,
                            correct: resolutions.filter { $0.correct }.count
                        )
                    }
                    .buttonStyle(.plain)
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
                } else if vm.error != nil, vm.items.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "arrow.clockwise")
                            .font(.title2)
                            .foregroundStyle(.secondary)
                        Text("Couldn't load feed")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.primary)
                        Text("Pull down to retry")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button("Retry") {
                            Task { await vm.load() }
                        }
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.blue)
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
                                .frame(minWidth: 44, minHeight: 44)
                                .contentShape(Rectangle())
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
                let pageGrouped = Array(grouped.prefix(visibleCount))
                let columns = [GridItem(.adaptive(minimum: 300), spacing: 16)]
                ScrollViewReader { proxy in
                    LazyVGrid(columns: columns, spacing: 16) {
                        ForEach(Array(pageGrouped.enumerated()), id: \.element.id) { idx, gi in
                            let isGuessSlot = (idx + 1) % 5 == 0
                            Group {
                                switch gi {
                                case .group(let title, let items, let kind, let theme):
                                    NativeGroupCard(title: title, items: items, kind: kind, theme: theme)
                                case .single(let item):
                                    if isGuessSlot, item.type == "futures", let f = item.futures,
                                       f.discoverCard?.suggestedFormat != "threshold_heatmap",
                                       f.discoverCard?.suggestedFormat != "outcome_distribution",
                                       f.discoverCard?.suggestedFormat != "cross_source_comparison",
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
                                    } else if item.type == "futures", let f = item.futures,
                                              f.discoverCard?.suggestedFormat == "threshold_heatmap",
                                              (f.discoverCard?.thresholdPoints ?? []).filter({ $0.probability != nil }).count >= 2 {
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
                                            HeatMapCardView(data: f, navigationPath: $navigationPath, onOpen: {
                                                recordInteraction(for: item, action: .detailOpen, source: "card")
                                            })
                                        }
                                        .contextMenu { discoverCardMenu(item) }
                                    } else if item.type == "futures", let f = item.futures,
                                              f.discoverCard?.suggestedFormat == "outcome_distribution",
                                              (f.discoverCard?.distributionOutcomes ?? []).filter({ $0.probability != nil }).count >= 4 {
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
                                            DistributionCardView(data: f, navigationPath: $navigationPath, onOpen: {
                                                recordInteraction(for: item, action: .detailOpen, source: "card")
                                            })
                                        }
                                        .contextMenu { discoverCardMenu(item) }
                                    } else if item.type == "futures", let f = item.futures,
                                              (f.discoverCard?.suggestedFormat == "cross_source_comparison"
                                               || (f.topOutcomes?.count ?? 0) >= 4) {
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
                                            ComparisonCardView(data: f, navigationPath: $navigationPath, onOpen: {
                                                recordInteraction(for: item, action: .detailOpen, source: "card")
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
                                    } else if item.type == "tournament", let t = item.tournament {
                                        NativeTournamentDiscoverCard(
                                            data: t,
                                            feedContext: item.contextSummary ?? item.reason ?? item.headline,
                                            navigationPath: $navigationPath
                                        )
                                    } else if item.type == "concept", let c = item.concept {
                                        // L2-179: event-concept marquee card (Tour de France,
                                        // World Cup, UFC card). Previously dropped at decode; now
                                        // rendered so the marquee finally appears on device.
                                        NativeConceptDiscoverCard(
                                            data: c,
                                            headline: item.headline,
                                            feedContext: item.contextSummary ?? item.reason ?? item.headline,
                                            navigationPath: $navigationPath,
                                            onOpen: {
                                                recordInteraction(for: item, action: .detailOpen, source: "card")
                                            }
                                        )
                                        .contextMenu { discoverCardMenu(item) }
                                    }
                                }
                            }
                            .id(gi.id)
                            .onAppear {
                                trackImpression(for: gi, rank: idx + 1)
                                if idx == pageGrouped.count - 3 && visibleCount < grouped.count {
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

                // Empty-eligible end state (L2-191 Item 2): the API returned
                // cards but every one was filtered out as settled/FINAL rot, so
                // there is nothing live to render. Honor "settled means settled"
                // — never restore stale cards to fill the space. If more pages
                // exist, keep fetching for fresh content (the card grid can't
                // drive pagination when it renders zero rows); otherwise show
                // the quiet, VoiceOver-labeled caught-up state with a refresh.
                if grouped.isEmpty, !vm.items.isEmpty {
                    if vm.error != nil {
                        // Pagination stalled or failed while cards exist but none
                        // are eligible (C26 P2): offer an explicit retry rather
                        // than an indefinite "Finding fresh markets…" spinner.
                        VStack(spacing: 16) {
                            Image(systemName: "arrow.clockwise")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                            Text("Couldn't find fresh markets")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(.primary)
                            Button("Retry") {
                                Task { await vm.loadMoreIfNeeded() }
                            }
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.blue)
                            .frame(minHeight: 44)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 60)
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("Couldn't find fresh markets")
                        .accessibilityHint("Double-tap to retry")
                    } else if vm.hasMore {
                        VStack(spacing: 12) {
                            ProgressView()
                            Text("Finding fresh markets…")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 60)
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("Finding fresh markets")
                        // Re-fire whenever a new page lands (items count grows)
                        // until fresh content appears or pagination is exhausted.
                        .task(id: vm.items.count) {
                            await vm.loadMoreIfNeeded()
                        }
                    } else {
                        VStack(spacing: 16) {
                            NativeFeedEndCard()
                            Button {
                                Task {
                                    visibleCount = 20
                                    dismissedAt.removeAll()
                                    seenImpressions.removeAll()
                                    await vm.load()
                                    if let r = try? await APIClient.shared.fetchResolutions() {
                                        resolutions = r.resolutions
                                    }
                                }
                            } label: {
                                Label("Refresh", systemImage: "arrow.clockwise")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(.blue)
                                    .frame(minHeight: 44)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Refresh feed")
                            .accessibilityHint("Checks for newly surfaced markets")
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.horizontal)
                        .padding(.vertical, 24)
                    }
                }

                // Feed footer (#902 item 9): pagination already loads more as
                // cards appear; surface a spinner while it fetches and an honest
                // end-of-feed card once the API has no more pages, instead of a
                // silent dead bottom. Only under a populated feed — the
                // empty-eligible state above owns the no-live-cards case.
                if !vm.items.isEmpty, !grouped.isEmpty {
                    if vm.loadingMore {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 24)
                    } else if !vm.hasMore {
                        NativeFeedEndCard()
                            .padding(.horizontal)
                            .padding(.bottom, 24)
                    }
                }
            }
            .frame(maxWidth: contentMaxWidth)
            .frame(maxWidth: .infinity)
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
            // Pull-to-refresh shows a full feed this session (in-memory clear);
            // the persisted, decaying store on disk is intact for the next launch.
            dismissedAt.removeAll()
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
        dismissedAt[id] = Date().timeIntervalSince1970
        Self.saveDismissed(dismissedAt)
        if visibleCount >= max(groupedItems.count - 8, 0) {
            visibleCount += 20
            Task { await vm.loadMoreIfNeeded() }
        }
        if showSwipeHint {
            withAnimation { showSwipeHint = false }
            UserDefaults.standard.set(true, forKey: "discover_swipe_hinted")
        }
    }

    private static func loadDismissed() -> [String: TimeInterval] {
        let cutoff = Date().timeIntervalSince1970 - dismissTTL
        // Live entries: drop anything past the 14-day TTL on load (#1221).
        let raw = UserDefaults.standard.dictionary(forKey: "discover_dismissed_v2") as? [String: Double] ?? [:]
        var live = raw.filter { $0.value >= cutoff }
        // One-time migration of the legacy timestamp-less Set: stamp survivors
        // "now" so they still decay out over the next 14 days instead of
        // persisting forever, then retire the old key.
        if live.isEmpty, let legacy = UserDefaults.standard.stringArray(forKey: "discover_dismissed"), !legacy.isEmpty {
            let now = Date().timeIntervalSince1970
            for id in legacy.suffix(dismissCap) { live[id] = now }
            UserDefaults.standard.removeObject(forKey: "discover_dismissed")
            UserDefaults.standard.set(live, forKey: "discover_dismissed_v2")
        }
        return live
    }

    private static func saveDismissed(_ store: [String: TimeInterval]) {
        let cutoff = Date().timeIntervalSince1970 - dismissTTL
        var live = store.filter { $0.value >= cutoff }
        if live.count > dismissCap {
            let keep = live.sorted { $0.value > $1.value }.prefix(dismissCap)
            live = Dictionary(uniqueKeysWithValues: keep.map { ($0.key, $0.value) })
        }
        UserDefaults.standard.set(live, forKey: "discover_dismissed_v2")
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
    var kind: String? = nil
    var theme: String? = nil
    @State private var expanded = false

    private var category: String {
        items.first?.futures?.llmSportCategory?.lowercased() ?? ""
    }

    private var gradient: (Color, Color) {
        sportCategoryGradients[category] ?? sportDefaultGradient
    }

    var body: some View {
        VStack(spacing: 0) {
            Button { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } } label: {
                HStack(spacing: 8) {
                    Text(title)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("\(items.count)")
                        .font(.system(size: 10, weight: .heavy).monospacedDigit())
                        .foregroundStyle(.white.opacity(0.7))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.white.opacity(0.15), in: Capsule())
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.white.opacity(0.7))
                        .rotationEffect(.degrees(expanded ? 180 : 0))
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
                .background(
                    LinearGradient(
                        colors: [gradient.0, gradient.1],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
            }
            .buttonStyle(.plain)

            if kind == "comparison" {
                NativeComparisonBundleRows(
                    items: expanded ? Array(items.prefix(6)) : Array(items.prefix(3)),
                    theme: theme
                )
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
            } else {
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
                }
            }

            if !expanded && items.count > 3 && kind == "comparison" {
                Button { withAnimation { expanded = true } } label: {
                    Text("Compare \(items.count - 3) more")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.blue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            } else if !expanded && items.count > 1 && kind != "comparison" {
                Button { withAnimation { expanded = true } } label: {
                    Text("Show \(items.count - 1) more")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.blue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            }
        }
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.05), radius: 8, x: 0, y: 3)
    }
}

private struct NativeComparisonBundleRows: View {
    let items: [FeedItem]
    let theme: String?

    var body: some View {
        VStack(spacing: 10) {
            ForEach(items, id: \.id) { item in
                if let futures = item.futures {
                    if theme == "ipo_valuation" {
                        NativeIPOComparisonRow(data: futures)
                    } else {
                        NativeThresholdComparisonRow(data: futures)
                    }
                }
            }
        }
    }
}

private struct NativeIPOComparisonRow: View {
    let data: FeedFuturesData

    private var points: [FeedDiscoverThresholdPoint] {
        (data.discoverCard?.thresholdPoints ?? [])
            .filter { $0.probability != nil }
            .sorted { ($0.value ?? 0) < ($1.value ?? 0) }
    }

    private var likely: FeedDiscoverThresholdPoint? {
        points.max { ($0.probability ?? -1) < ($1.probability ?? -1) } ?? points.first
    }

    private var highEnd: FeedDiscoverThresholdPoint? {
        points.last ?? likely
    }

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 4) {
            GridRow {
                VStack(alignment: .leading, spacing: 2) {
                    Text(compactMarketName(data.name, theme: "ipo_valuation"))
                        .font(.caption.weight(.heavy))
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)
                    Text((data.source ?? "market").uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)
                }
                comparisonSummary(title: "Likely", point: likely, emphasized: true)
                comparisonSummary(title: "High end", point: highEnd, emphasized: false)
            }
        }
    }

    private func comparisonSummary(title: String, point: FeedDiscoverThresholdPoint?, emphasized: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
            Text(point.map { compactRangeLabel($0.label) } ?? "-")
                .font(.caption2.weight(emphasized ? .heavy : .semibold))
                .foregroundStyle(emphasized ? .primary : .secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.76)
            Text("\(Int(((point?.probability ?? 0) * 100).rounded()))%")
                .font(.subheadline.weight(.black).monospacedDigit())
        }
    }
}

private struct NativeThresholdComparisonRow: View {
    let data: FeedFuturesData

    private var points: [FeedDiscoverThresholdPoint] {
        (data.discoverCard?.thresholdPoints ?? [])
            .filter { $0.probability != nil }
            .sorted { ($0.value ?? 0) < ($1.value ?? 0) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(compactMarketName(data.name, theme: data.discoverCard?.comparisonTheme))
                    .font(.caption.weight(.heavy))
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
                Spacer()
                Text((data.source ?? "market").uppercased())
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                ForEach(Array(points.prefix(3))) { point in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(compactRangeLabel(point.label))
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                        Text("\(Int(((point.probability ?? 0) * 100).rounded()))%")
                            .font(.caption.weight(.black).monospacedDigit())
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
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

private func compactMarketName(_ name: String, theme: String?) -> String {
    var compact = name.replacingOccurrences(of: "?", with: "")
    if theme == "ipo_valuation" {
        compact = compact.replacingOccurrences(of: "Closing Market Cap", with: "", options: .caseInsensitive)
        if let range = compact.range(of: "IPO", options: .caseInsensitive) {
            compact = String(compact[..<range.upperBound])
        }
    }
    return compact.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func compactRangeLabel(_ label: String) -> String {
    label
        .replacingOccurrences(of: "Above ", with: ">")
        .replacingOccurrences(of: "Below ", with: "<")
        .replacingOccurrences(of: " to ", with: "-")
        .replacingOccurrences(of: " ", with: "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

#if DEBUG
private enum NativeDiscoverPreviewFactory {
    static func feedItem(from json: String) -> FeedItem {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(FeedItem.self, from: Data(json.utf8))
    }

    static var ipoBundleItems: [FeedItem] {
        [
            feedItem(from: ipoMarketJSON(id: 101, name: "SpaceX IPO Closing Market Cap", likely: "$2.0T-$2.5T", likelyProb: 0.31, high: "Above $2.5T", highProb: 0.18)),
            feedItem(from: ipoMarketJSON(id: 102, name: "Stripe IPO Closing Market Cap", likely: "$100B-$125B", likelyProb: 0.34, high: "Above $125B", highProb: 0.16)),
            feedItem(from: ipoMarketJSON(id: 103, name: "Databricks IPO Closing Market Cap", likely: "$75B-$100B", likelyProb: 0.30, high: "Above $100B", highProb: 0.21)),
        ]
    }

    private static func ipoMarketJSON(
        id: Int,
        name: String,
        likely: String,
        likelyProb: Double,
        high: String,
        highProb: Double
    ) -> String {
        """
        {
          "type": "futures",
          "score": 98,
          "reason": "\(name)",
          "headline": "\(name)",
          "data": {
            "id": \(id),
            "name": "\(name)",
            "llm_sport_category": "tech",
            "source": "kalshi",
            "source_count": 1,
            "sources": ["kalshi"],
            "market_tier": 2,
            "status": "open",
            "top_outcomes": [
              {"id": \(id * 10 + 1), "name": "\(likely)", "probability": \(likelyProb), "rank": 1, "movement": null},
              {"id": \(id * 10 + 2), "name": "\(high)", "probability": \(highProb), "rank": 2, "movement": null},
              {"id": \(id * 10 + 3), "name": "Below \(likely)", "probability": 0.12, "rank": 3, "movement": null}
            ],
            "outcome_count": 3,
            "discover_card": {
              "suggested_format": "threshold_heatmap",
              "bundle_candidate": true,
              "comparison_theme": "ipo_valuation",
              "threshold_points": [
                {"source": "outcome", "label": "Below \(likely)", "value": 1, "unit": "$B", "direction": "below", "probability": 0.12},
                {"source": "outcome", "label": "\(likely)", "value": 2, "unit": "$B", "direction": "exact", "probability": \(likelyProb)},
                {"source": "outcome", "label": "\(high)", "value": 3, "unit": "$B", "direction": "above", "probability": \(highProb)}
              ],
              "distribution_outcomes": [],
              "remaining_outcome_count": 0,
              "qa_signals": [],
              "public_source_disagreement": false,
              "reasons": ["threshold_values", "bundle_candidate"]
            }
          }
        }
        """
    }
}

#Preview("IPO Bundle") {
    NativeGroupCard(
        title: "IPO valuation ranges",
        items: NativeDiscoverPreviewFactory.ipoBundleItems,
        kind: "comparison",
        theme: "ipo_valuation"
    )
    .padding()
    .background(Color.pageBackground)
}
#endif

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
                .frame(minHeight: 44)
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
