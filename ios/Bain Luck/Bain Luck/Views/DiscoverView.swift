import SwiftUI

struct DiscoverView: View {
    @StateObject private var vm = DiscoverViewModel()
    @State private var categoryFilter = "all"
    @State private var dismissed: Set<String> = []

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

                // Cards
                let columns = [GridItem(.adaptive(minimum: 340), spacing: 16)]
                LazyVGrid(columns: columns, spacing: 16) {
                    ForEach(Array(filteredItems.enumerated()), id: \.element.id) { idx, item in
                        let isGuess = (idx + 1) % 5 == 0 && item.type == "futures"
                        if isGuess, let f = item.futures {
                            NativeGuessCard(data: f)
                        } else if item.type == "event", let e = item.event {
                            NativeEventDiscoverCard(event: e)
                        } else if item.type == "futures", let f = item.futures {
                            NativeFuturesDiscoverCard(data: f)
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
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }
}

// MARK: - ViewModel

final class DiscoverViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = false

    @MainActor
    func load() async {
        loading = true
        do {
            let response = try await APIClient.shared.fetchFeed(limit: 200)
            items = response.items
        } catch { }
        loading = false
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

// MARK: - Futures Card

private struct NativeFuturesDiscoverCard: View {
    let data: FeedFuturesData

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: data.id)) {
            VStack(alignment: .leading, spacing: 8) {
                // Category + probability
                HStack {
                    Text(data.llmSportCategory?.uppercased() ?? "MARKET")
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(.secondary)
                        .tracking(0.5)
                    Spacer()
                    if let leader = data.topOutcomes?.first {
                        Text("\(Int(((leader.probability ?? 0) * 100).rounded()))%")
                            .font(.title2.weight(.black).monospacedDigit())
                    }
                }

                Text(data.name)
                    .font(.subheadline.weight(.bold))
                    .lineLimit(2)

                if let hook = data.hookDescription {
                    Text(hook)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                // Top outcomes
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
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Guess Card

private struct NativeGuessCard: View {
    let data: FeedFuturesData
    @State private var guess: String? = nil
    @State private var threshold: Int = 50

    private var leader: FeedFuturesOutcome? { data.topOutcomes?.first }
    private var actualPct: Int { Int(((leader?.probability ?? 0) * 100).rounded()) }
    private var correct: Bool {
        guard let g = guess else { return false }
        return g == "higher" ? actualPct > threshold : actualPct < threshold
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
                    Button { guess = "higher" } label: {
                        Text("↑ Higher")
                            .font(.caption.weight(.bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(Color.green.opacity(0.1))
                            .foregroundStyle(.green)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.green.opacity(0.3)))
                    }
                    Button { guess = "lower" } label: {
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

                    NavigationLink(value: Route.futuresDetail(id: data.id)) {
                        Text("See full market →")
                            .font(.caption)
                            .foregroundStyle(.blue)
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
