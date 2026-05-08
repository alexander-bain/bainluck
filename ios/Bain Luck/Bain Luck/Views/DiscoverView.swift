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

struct DiscoverView: View {
    @StateObject private var vm = DiscoverViewModel()
    @State private var categoryFilter = "all"
    @State private var visibleCount = 20
    @State private var dismissed: Set<String> = Self.loadDismissed()
    @State private var scrollTarget: String? = nil
    @State private var dailyGuesses: Int = Self.loadDailyGuesses()
    @State private var showOnboarding = !UserDefaults.standard.bool(forKey: "discover_onboarded")
    @State private var resolutions: [Resolution] = []

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
        return result
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Category chips
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(categories, id: \.key) { cat in
                            Button {
                                withAnimation(.easeInOut(duration: 0.15)) { categoryFilter = cat.key }
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

                // Resolution cards
                ForEach(resolutions.prefix(3), id: \.marketName) { res in
                    NativeResolutionCard(resolution: res)
                        .padding(.horizontal)
                }

                // Daily Challenge card
                NativeDailyChallengeCard(guessesToday: dailyGuesses)
                    .padding(.horizontal)
                    .padding(.bottom, 8)

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
                                        NativeGuessCard(data: f, onNextQuestion: { scrollToNextGuessGrouped(proxy: proxy, after: idx, in: pageGrouped) }, onGuessCompleted: { incrementDaily() })
                                    } else if isGuessSlot, item.type == "event", let e = item.event, e.currentOdds?.homeProbability != nil {
                                        NativeEventGuessCard(event: e, onNextQuestion: { scrollToNextGuessGrouped(proxy: proxy, after: idx, in: pageGrouped) }, onGuessCompleted: { incrementDaily() })
                                    } else if item.type == "event", let e = item.event {
                                        SwipeToDismiss { dismiss(itemId(item)) } content: {
                                            NativeEventDiscoverCard(event: e)
                                        }
                                        .contextMenu { discoverCardMenu(item) }
                                    } else if item.type == "futures", let f = item.futures {
                                        SwipeToDismiss { dismiss(itemId(item)) } content: {
                                            NativeFuturesDiscoverCard(data: f)
                                        }
                                        .contextMenu { discoverCardMenu(item) }
                                    }
                                }
                            }
                            .id(gi.id)
                            .onAppear {
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
            OnboardingView()
                .onDisappear { UserDefaults.standard.set(true, forKey: "discover_onboarded") }
        }
    }

    private func scrollToNextGuess(proxy: ScrollViewProxy, after idx: Int, in items: [FeedItem]) {
        let nextGuessIdx = stride(from: idx + 1, to: items.count, by: 1).first { i in
            (i + 1) % 2 == 0
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
            (i + 1) % 2 == 0
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

    @ViewBuilder
    private func discoverCardMenu(_ item: FeedItem) -> some View {
        if let e = item.event {
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
                let url = "https://bainluck.com/events/\(e.id)"
                #if os(macOS)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                #else
                UIPasteboard.general.string = url
                #endif
            } label: {
                Label("Copy Link", systemImage: "link")
            }
            ShareLink(item: URL(string: "https://bainluck.com/events/\(e.id)")!) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
        } else if let f = item.futures {
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
                let url = "https://bainluck.com/futures/\(f.id)"
                #if os(macOS)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                #else
                UIPasteboard.general.string = url
                #endif
            } label: {
                Label("Copy Link", systemImage: "link")
            }
            ShareLink(item: URL(string: "https://bainluck.com/futures/\(f.id)")!) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
        }
        Divider()
        Button(role: .destructive) {
            dismiss(itemId(item))
        } label: {
            Label("Dismiss", systemImage: "xmark")
        }
    }
}

// MARK: - ViewModel

final class DiscoverViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = false

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
    ]

    @MainActor
    func load() async {
        loading = true
        do {
            let response = try await APIClient.shared.fetchFeed(limit: 200, eventPct: 0.15)
            items = Self.interleave(response.items)
        } catch { }
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

// MARK: - Event Card

private struct NativeEventDiscoverCard: View {
    let event: FeedEventData

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
        if let label = event.highlight?.label, !label.isEmpty { return label }
        if let ei = event.ei, let score = ei.score, score >= 60, let label = ei.label {
            return "Excitement Index \(score): \(label)"
        }
        if event.status == "live" { return "Live probability is moving now" }
        return nil
    }

    var body: some View {
        NavigationLink(value: Route.eventDetail(id: event.id)) {
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
                    Text(contextText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(14)
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
        }
        .buttonStyle(.plain)
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

    private var gradient: (Color, Color) {
        categoryGradients[data.llmSportCategory?.lowercased() ?? ""] ?? defaultGradient
    }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: data.id)) {
            VStack(alignment: .leading, spacing: 0) {
                // Hero section with gradient/image
                ZStack(alignment: .bottomLeading) {
                    if let imageUrl = data.imageUrl, let url = URL(string: imageUrl) {
                        AsyncImage(url: url) { phase in
                            switch phase {
                            case .success(let img):
                                img.resizable().scaledToFill()
                            default:
                                LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                            }
                        }
                        .frame(height: 140)
                        .clipped()
                        .overlay(LinearGradient(colors: [.clear, .black.opacity(0.7)], startPoint: .top, endPoint: .bottom))
                    } else {
                        LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                            .frame(height: 140)
                    }

                    // Overlay content
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(data.llmSportCategory?.uppercased() ?? "MARKET")
                                .font(.system(size: 9, weight: .heavy))
                                .tracking(0.8)
                                .foregroundStyle(.white.opacity(0.7))
                            if isTrending(data) {
                                Text("🔥 Trending")
                                    .font(.system(size: 9, weight: .heavy))
                                    .foregroundStyle(.orange)
                            }
                        }

                        if let leader = data.topOutcomes?.first {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text("\(Int(((leader.probability ?? 0) * 100).rounded()))%")
                                    .font(.system(size: 36, weight: .black).monospacedDigit())
                                    .foregroundStyle(.white)
                                MovementBadge(movement: leader.movement)
                            }
                            Text(leader.name)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.white.opacity(0.85))
                                .lineLimit(1)
                        }
                    }
                    .padding(12)
                }
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 16, topTrailingRadius: 16))

                // Details section
                VStack(alignment: .leading, spacing: 6) {
                    Text(data.name)
                        .font(.subheadline.weight(.bold))
                        .lineLimit(2)

                    if let hook = data.hookDescription {
                        Text(hook)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    if let outcomes = data.topOutcomes, outcomes.count > 1 {
                        ForEach(outcomes.prefix(3).indices, id: \.self) { i in
                            let o = outcomes[i]
                            HStack(spacing: 4) {
                                Text(o.name)
                                    .font(.caption2)
                                    .lineLimit(1)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                GeometryReader { geo in
                                    Capsule().fill(i == 0 ? Color.blue : Color.secondary.opacity(0.2))
                                        .frame(width: max(2, geo.size.width * (o.probability ?? 0)))
                                }
                                .frame(width: 60, height: 6)
                                Text("\(Int(((o.probability ?? 0) * 100).rounded()))%")
                                    .font(.caption2.weight(.semibold).monospacedDigit())
                                    .frame(width: 28, alignment: .trailing)
                            }
                        }
                    }

                    if let src = data.source {
                        Text(src.uppercased())
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.blue.opacity(0.1))
                            .clipShape(Capsule())
                    }
                }
                .padding(12)
            }
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Daily Challenge Card

private let DAILY_GOAL = 5

private struct NativeDailyChallengeCard: View {
    let guessesToday: Int
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
                     : "Make \(DAILY_GOAL) predictions today · \(guessesToday)/\(DAILY_GOAL)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if !completed {
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
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16)
            .stroke(completed ? Color.green.opacity(0.5) : Color.orange.opacity(0.3), lineWidth: 2))
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
        Task {
            do {
                let request = PredictionRequest(
                    marketId: data.id,
                    guess: g,
                    threshold: threshold,
                    actualProbability: leader?.probability ?? 0,
                    correct: isCorrect,
                    category: data.llmSportCategory
                )
                _ = try await APIClient.shared.submitPrediction(request)
                let stats = try await APIClient.shared.fetchPredictionStats()
                streak = stats.currentStreak
                onGuessCompleted?()
            } catch { }
        }
    }

    private var shareText: String {
        let result = correct ? "Got it right" : "Missed it"
        return "\(result)! \(data.name) — \(actualPct)%. Can you beat my streak? bainluck.com/discover"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("🎯")
                Text("WHAT ARE THE ODDS?")
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1)
                    .foregroundStyle(.orange)
                Spacer()
            }

            Text(data.name)
                .font(.subheadline.weight(.bold))
                .lineLimit(2)

            if guess == nil {
                if let leader {
                    Text("\(leader.name) — higher or lower than \(threshold)%?")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                HStack(spacing: 12) {
                    Button { submitGuess("higher") } label: {
                        Text("↑ Higher")
                            .font(.caption.weight(.bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(Color.green.opacity(0.1))
                            .foregroundStyle(.green)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.green.opacity(0.3)))
                    }
                    Button { submitGuess("lower") } label: {
                        Text("↓ Lower")
                            .font(.caption.weight(.bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(Color.red.opacity(0.1))
                            .foregroundStyle(.red)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.red.opacity(0.3)))
                    }
                }
                .buttonStyle(.plain)
            } else {
                VStack(spacing: 8) {
                    Text(correct ? "✓ Correct!" : "✗ Not quite!")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(correct ? .green : .red)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 4)
                        .background((correct ? Color.green : Color.red).opacity(0.1))
                        .clipShape(Capsule())

                    Text("\(displayPct)%")
                        .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
                        .contentTransition(.numericText())
                    if let leader { Text(leader.name).font(.caption).foregroundStyle(.secondary) }

                    if let streak, streak > 1 {
                        Text("🔥 \(streak) streak")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.orange)
                    }

                    HStack(spacing: 12) {
                        NavigationLink(value: Route.futuresDetail(id: data.id)) {
                            Text("See full market →")
                                .font(.caption)
                                .foregroundStyle(.blue)
                        }
                        Button { showShare = true } label: {
                            Label("Share", systemImage: "square.and.arrow.up")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        if let onNextQuestion {
                            Button { onNextQuestion() } label: {
                                Text("Next question →")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.orange)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .sheet(isPresented: $showShare) {
                    ShareSheet(text: shareText)
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.orange.opacity(0.3), lineWidth: 2))
        .onAppear { generateThreshold() }
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
    var onGuessCompleted: (() -> Void)? = nil
    @State private var guess: String? = nil
    @State private var threshold: Int = 50
    @State private var streak: Int? = nil

    private var actualPct: Int { Int(((event.currentOdds?.homeProbability ?? 0.5) * 100).rounded()) }
    private var correct: Bool {
        guard let g = guess else { return false }
        return g == "higher" ? actualPct > threshold : actualPct < threshold
    }

    private func submitGuess(_ g: String) {
        guess = g
        let isCorrect = g == "higher" ? actualPct > threshold : actualPct < threshold
        Task {
            do {
                let request = PredictionRequest(
                    marketId: event.id,
                    guess: g,
                    threshold: threshold,
                    actualProbability: event.currentOdds?.homeProbability ?? 0.5,
                    correct: isCorrect,
                    category: event.sport?.split(separator: "_").first.map(String.init)
                )
                _ = try await APIClient.shared.submitPrediction(request)
                let stats = try await APIClient.shared.fetchPredictionStats()
                streak = stats.currentStreak
                onGuessCompleted?()
            } catch { }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("🎯")
                Text("WHAT ARE THE ODDS?")
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1)
                    .foregroundStyle(.orange)
                Spacer()
            }

            HStack(spacing: 12) {
                teamBadge(name: event.awayTeam, logo: event.awayTeamData?.logoSmall,
                         color: Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280"))
                VStack(spacing: 2) {
                    if event.status == "live" {
                        Text(event.espn?.period ?? "LIVE")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.red)
                    } else if event.status == "completed" || event.status == "closed" {
                        Text("Final")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.secondary)
                    } else {
                        Text("vs")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let a = event.awayScore, let h = event.homeScore,
                       (event.status == "live" || event.status == "completed" || event.status == "closed") {
                        Text("\(a)-\(h)")
                            .font(.system(size: 10, weight: .bold).monospacedDigit())
                            .foregroundStyle(.primary)
                    }
                }
                teamBadge(name: event.homeTeam, logo: event.homeTeamData?.logoSmall,
                         color: Color(hex: event.homeTeamData?.primaryColor ?? "#374151"))
            }

            if guess == nil {
                Text("\(event.homeTeam.split(separator: " ").last.map(String.init) ?? event.homeTeam) to win — higher or lower than \(threshold)%?")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    Button { submitGuess("higher") } label: {
                        Text("↑ Higher")
                            .font(.caption.weight(.bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(Color.green.opacity(0.1))
                            .foregroundStyle(.green)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.green.opacity(0.3)))
                    }
                    Button { submitGuess("lower") } label: {
                        Text("↓ Lower")
                            .font(.caption.weight(.bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(Color.red.opacity(0.1))
                            .foregroundStyle(.red)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.red.opacity(0.3)))
                    }
                }
                .buttonStyle(.plain)
            } else {
                VStack(spacing: 8) {
                    Text(correct ? "✓ Correct!" : "✗ Not quite!")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(correct ? .green : .red)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 4)
                        .background((correct ? Color.green : Color.red).opacity(0.1))
                        .clipShape(Capsule())

                    Text("\(actualPct)%")
                        .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
                    Text(event.homeTeam)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if let streak, streak > 1 {
                        Text("🔥 \(streak) streak")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.orange)
                    }

                    HStack(spacing: 12) {
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            Text("See full game →")
                                .font(.caption)
                                .foregroundStyle(.blue)
                        }
                        if let onNextQuestion {
                            Button { onNextQuestion() } label: {
                                Text("Next question →")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.orange)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.orange.opacity(0.3), lineWidth: 2))
        .onAppear { generateThreshold() }
    }

    private func teamBadge(name: String, logo: String?, color: Color) -> some View {
        HStack(spacing: 6) {
            if let logo, let url = URL(string: logo) {
                AsyncImage(url: url) { img in img.resizable().scaledToFit() } placeholder: { EmptyView() }
                    .frame(width: 24, height: 24)
            } else {
                RoundedRectangle(cornerRadius: 4).fill(color)
                    .frame(width: 24, height: 24)
            }
            Text(name.split(separator: " ").last.map(String.init) ?? name)
                .font(.caption.weight(.semibold))
                .lineLimit(1)
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
