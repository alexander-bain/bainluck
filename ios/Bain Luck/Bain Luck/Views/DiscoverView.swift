import SwiftUI
import Combine

struct DiscoverView: View {
    @StateObject private var vm = DiscoverViewModel()
    @State private var categoryFilter = "all"
    @State private var visibleCount = 20
    @State private var dismissed: Set<String> = Self.loadDismissed()
    @State private var scrollTarget: String? = nil
    @State private var dailyGuesses: Int = Self.loadDailyGuesses()

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

                // Daily Challenge card
                NativeDailyChallengeCard(guessesToday: dailyGuesses)
                    .padding(.horizontal)
                    .padding(.bottom, 8)

                // Cards (paginated — show `visibleCount` at a time)
                let pageItems = Array(filteredItems.prefix(visibleCount))
                let columns = [GridItem(.adaptive(minimum: 340), spacing: 16)]
                ScrollViewReader { proxy in
                    LazyVGrid(columns: columns, spacing: 16) {
                        ForEach(Array(pageItems.enumerated()), id: \.element.id) { idx, item in
                            let isGuessSlot = (idx + 1) % 2 == 0
                            let guessId = itemId(item)
                            Group {
                                if isGuessSlot, item.type == "futures", let f = item.futures {
                                    NativeGuessCard(data: f, onNextQuestion: { scrollToNextGuess(proxy: proxy, after: idx, in: pageItems) }, onGuessCompleted: { incrementDaily() })
                                } else if isGuessSlot, item.type == "event", let e = item.event, e.currentOdds?.homeProbability != nil {
                                    NativeEventGuessCard(event: e, onNextQuestion: { scrollToNextGuess(proxy: proxy, after: idx, in: pageItems) }, onGuessCompleted: { incrementDaily() })
                                } else if item.type == "event", let e = item.event {
                                    SwipeToDismiss { dismiss(guessId) } content: {
                                        NativeEventDiscoverCard(event: e)
                                    }
                                } else if item.type == "futures", let f = item.futures {
                                    SwipeToDismiss { dismiss(guessId) } content: {
                                        NativeFuturesDiscoverCard(data: f)
                                    }
                                }
                            }
                            .id(guessId)
                            .onAppear {
                                if idx == pageItems.count - 3 && visibleCount < filteredItems.count {
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
        .task { await vm.load() }
        .refreshable { await vm.load() }
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

    var body: some View {
        NavigationLink(value: Route.eventDetail(id: event.id)) {
            VStack(spacing: 0) {
                // Hero
                HStack(spacing: 16) {
                    teamColumn(name: event.awayTeam, logo: event.awayTeamData?.logoSmall,
                              color: Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280"),
                              score: event.awayScore)
                    VStack {
                        Text(event.status == "live" ? (event.espn?.period ?? "LIVE") : event.status == "completed" || event.status == "closed" ? "Final" : "vs")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    teamColumn(name: event.homeTeam, logo: event.homeTeamData?.logoSmall,
                              color: Color(hex: event.homeTeamData?.primaryColor ?? "#374151"),
                              score: event.homeScore)
                }
                .padding()

                // Probability bar
                if let hp = event.currentOdds?.homeProbability, let ap = event.currentOdds?.awayProbability {
                    HStack(spacing: 4) {
                        Text(formatProbability(ap))
                            .font(.caption2.weight(.bold))
                        GeometryReader { geo in
                            HStack(spacing: 0) {
                                Rectangle().fill(Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280"))
                                    .frame(width: geo.size.width * ap)
                                Rectangle().fill(Color(hex: event.homeTeamData?.primaryColor ?? "#374151"))
                                    .frame(width: geo.size.width * hp)
                            }
                            .clipShape(Capsule())
                        }
                        .frame(height: 6)
                        Text(formatProbability(hp))
                            .font(.caption2.weight(.bold))
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 12)
                }
            }
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    private func teamColumn(name: String, logo: String?, color: Color, score: Int?) -> some View {
        VStack(spacing: 4) {
            if let logo, let url = URL(string: logo) {
                AsyncImage(url: url) { img in img.resizable().scaledToFit() } placeholder: { EmptyView() }
                    .frame(width: 40, height: 40)
            } else {
                RoundedRectangle(cornerRadius: 8).fill(color)
                    .frame(width: 40, height: 40)
                    .overlay(Text(String(name.split(separator: " ").last ?? "")).font(.system(size: 10, weight: .bold)).foregroundStyle(.white))
            }
            Text(name.split(separator: " ").last.map(String.init) ?? name)
                .font(.caption2.weight(.semibold))
                .lineLimit(1)
            if let s = score {
                Text("\(s)").font(.title3.weight(.black).monospacedDigit())
            }
        }
        .frame(maxWidth: .infinity)
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

// MARK: - Guess Card

private struct NativeGuessCard: View {
    let data: FeedFuturesData
    var onNextQuestion: (() -> Void)? = nil
    var onGuessCompleted: (() -> Void)? = nil
    @State private var guess: String? = nil
    @State private var threshold: Int = 50
    @State private var streak: Int? = nil

    private var leader: FeedFuturesOutcome? { data.topOutcomes?.first }
    private var actualPct: Int { Int(((leader?.probability ?? 0) * 100).rounded()) }
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

                    Text("\(actualPct)%")
                        .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
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
                Text("vs")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
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

    var body: some View {
        content()
            .offset(x: offset)
            .opacity(removing ? 0 : 1.0 - abs(offset) / 300)
            .gesture(
                DragGesture()
                    .onChanged { v in offset = v.translation.width }
                    .onEnded { v in
                        if abs(v.translation.width) > 120 {
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
                    }
            )
    }
}

// MARK: - Movement Badge

private func isTrending(_ data: FeedFuturesData) -> Bool {
    guard let m = data.topOutcomes?.first?.movement else { return false }
    return abs(m) >= 0.05
}

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
