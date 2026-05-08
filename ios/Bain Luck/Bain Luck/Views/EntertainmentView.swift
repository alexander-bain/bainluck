import SwiftUI
import os

private let logger = Logger(subsystem: "com.bainluck", category: "entertainment")

// MARK: - ViewModel

final class EntertainmentViewModel: ObservableObject {
    @Published var data: EntertainmentResponse?
    @Published var loading = true
    @Published var error: String?

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await APIClient.shared.fetchEntertainment()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Entertainment load failed: \(error)")
        }
    }
}

// MARK: - Constants

private let kindEmoji: [String: String] = [
    "spotify": "🎧", "billboard": "📊", "boxoffice": "🎬",
    "rt": "🍅", "reality": "📺", "eurovision": "🎤",
    "multi": "🌐", "binary": "✦",
]

private let kindLabel: [String: String] = [
    "spotify": "Spotify", "billboard": "Billboard", "boxoffice": "Box Office",
    "rt": "Rotten Tomatoes", "reality": "Reality TV", "eurovision": "Eurovision",
    "multi": "Market", "binary": "Market",
]

// MARK: - View

struct EntertainmentView: View {
    @StateObject private var vm = EntertainmentViewModel()

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading entertainment data...")
            } else if let error = vm.error, vm.data == nil {
                ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if let data = vm.data {
                entertainmentContent(data)
            }
        }
        .navigationTitle("Entertainment")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private func entertainmentContent(_ data: EntertainmentResponse) -> some View {
        ScrollView {
            VStack(spacing: 24) {
                pageHeader(data)

                if let trending = data.trending, !trending.isEmpty {
                    trendingSection(trending)
                }

                if let music = data.themes.music {
                    musicSection(music)
                }

                if let movies = data.themes.moviesTv {
                    moviesTVSection(movies)
                }

                if let cultural = data.culturalMoments, !cultural.isEmpty {
                    culturalSection(cultural)
                }

                if let tech = data.themes.techCulture, let markets = tech.markets, !markets.isEmpty {
                    techCultureSection(tech)
                }

                footer(data)
            }
            .padding(.vertical)
        }
    }

    // MARK: - Page header

    private func pageHeader(_ data: EntertainmentResponse) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Live probabilities from Kalshi and Polymarket — charts, box office, reality TV, and the moments breaking the internet.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            HStack(spacing: 12) {
                Label("\(data.totalMarkets) markets", systemImage: "chart.bar")
                Label("2 sources", systemImage: "arrow.triangle.branch")
            }
            .font(.caption2)
            .foregroundStyle(.tertiary)
        }
        .padding(.horizontal)
    }

    // MARK: - Trending hero

    private func trendingSection(_ markets: [EntMarketRow]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🔥", title: "Trending now")

            ForEach(markets.prefix(5)) { market in
                NavigationLink(value: Route.futuresDetail(id: market.marketId)) {
                    trendingCard(market)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func trendingCard(_ m: EntMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                tagChip(kind: m.kind ?? "binary")
                Spacer()
                if let vol = m.volume24h, vol > 0 {
                    Text("$\(vol >= 1000 ? "\(vol / 1000)k" : "\(vol)")")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
            }

            Text(m.q)
                .font(.subheadline).fontWeight(.semibold)
                .lineLimit(2)

            if let hook = m.hook {
                Text(hook)
                    .font(.caption).foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            cardBody(m)

            sourceChip(m.src)
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.secondary.opacity(0.1)))
        .padding(.horizontal)
    }

    // MARK: - Card body by kind

    @ViewBuilder
    private func cardBody(_ m: EntMarketRow) -> some View {
        let outcomes = m.topOutcomes

        if (m.kind == "spotify" || m.kind == "billboard") && outcomes.count >= 2 {
            VStack(spacing: 6) {
                outcomeRow(outcomes[0], isLeader: true)
                outcomeRow(outcomes[1], isLeader: false)
            }
        } else if m.kind == "reality" && m.outcomeCount <= 2 && outcomes.count >= 2 {
            binaryBar(a: outcomes[0], b: outcomes[1])
        } else if outcomes.count > 2 {
            VStack(spacing: 4) {
                ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                    outcomeRow(o, isLeader: false)
                }
            }
        } else {
            HStack {
                Text("\(Int(m.prob))%")
                    .font(.title2).fontWeight(.bold).monospacedDigit()
                Spacer()
                Text(m.prob >= 50 ? "Yes likely" : "No likely")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func outcomeRow(_ o: EntOutcome, isLeader: Bool) -> some View {
        HStack(spacing: 8) {
            Text(o.name)
                .font(.caption)
                .fontWeight(isLeader ? .semibold : .regular)
                .foregroundStyle(isLeader ? .primary : .secondary)
                .lineLimit(1)
            Spacer()
            if let delta = o.delta24h, abs(delta) > 0.1 {
                Text("\(delta > 0 ? "↑" : "↓")\(abs(delta), specifier: "%.1f")%")
                    .font(.system(size: 9, design: .monospaced)).fontWeight(.semibold)
                    .foregroundColor(delta > 0 ? .green : .red)
            }
            Text("\(Int(o.prob))%")
                .font(.caption).fontWeight(.bold).monospacedDigit()
        }
    }

    private func binaryBar(a: EntOutcome, b: EntOutcome) -> some View {
        VStack(spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(a.name).font(.caption2).fontWeight(.semibold)
                    Text("\(Int(a.prob))%").font(.callout).fontWeight(.bold).monospacedDigit()
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(b.name).font(.caption2).fontWeight(.semibold)
                    Text("\(Int(b.prob))%").font(.callout).fontWeight(.bold).monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
            GeometryReader { geo in
                HStack(spacing: 1.5) {
                    RoundedRectangle(cornerRadius: 99)
                        .fill(Color.accentColor)
                        .frame(width: geo.size.width * a.prob / 100)
                    RoundedRectangle(cornerRadius: 99)
                        .fill(Color.accentColor.opacity(0.3))
                        .frame(width: geo.size.width * b.prob / 100)
                }
            }
            .frame(height: 6)
        }
    }

    // MARK: - Music section

    private func musicSection(_ data: EntThemeMusic) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🎧", title: "Music", count: data.count)

            if let spotify = data.spotifyRace, !spotify.isEmpty {
                spotifyRace(spotify)
            }

            if let billboard = data.billboardWatch, !billboard.isEmpty {
                entMarketList(billboard, title: "Billboard")
            }

            if let albums = data.albumDrops, !albums.isEmpty {
                entMarketList(albums, title: "Album Drops")
            }
        }
    }

    private func spotifyRace(_ markets: [EntMarketRow]) -> some View {
        let best = markets.max(by: { $0.topOutcomes.count < $1.topOutcomes.count }) ?? markets[0]
        return VStack(alignment: .leading, spacing: 8) {
            Text("🎧 Spotify Chart Race")
                .font(.caption).fontWeight(.semibold).foregroundStyle(.green)
                .padding(.horizontal)
            Text(best.q)
                .font(.caption).fontWeight(.medium)
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(Array(best.topOutcomes.prefix(6).enumerated()), id: \.offset) { idx, o in
                    HStack(spacing: 8) {
                        Text("\(idx + 1)")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundStyle(idx == 0 ? .green : .secondary)
                            .frame(width: 20, alignment: .trailing)

                        Text(o.name)
                            .font(.caption).fontWeight(.medium)
                            .lineLimit(1)

                        Spacer()

                        if let delta = o.delta24h, abs(delta) > 0.1 {
                            Text("\(delta > 0 ? "↑" : "↓")\(abs(delta), specifier: "%.1f")%")
                                .font(.system(size: 9, design: .monospaced)).fontWeight(.semibold)
                                .foregroundColor(delta > 0 ? .green : .red)
                        }

                        Text("\(Int(o.prob))%")
                            .font(.caption).fontWeight(.bold).monospacedDigit()
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
                    if idx < min(best.topOutcomes.count, 6) - 1 {
                        Divider()
                    }
                }
            }
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.1)))
            .padding(.horizontal)
        }
    }

    // MARK: - Movies & TV section

    private func moviesTVSection(_ data: EntThemeMoviesTV) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🎬", title: "Movies & TV", count: data.count)

            if let rt = data.rtMarkets, !rt.isEmpty {
                entMarketList(rt, title: "Rotten Tomatoes")
            }

            if let box = data.boxOffice, !box.isEmpty {
                entMarketList(box, title: "Box Office")
            }

            if let reality = data.realityTv, !reality.isEmpty {
                entMarketList(reality, title: "Reality TV")
            }
        }
    }

    // MARK: - Cultural moments

    private func culturalSection(_ markets: [EntMarketRow]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🎭", title: "Cultural moments")

            ForEach(markets.prefix(10)) { m in
                NavigationLink(value: Route.futuresDetail(id: m.marketId)) {
                    momentCard(m)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func momentCard(_ m: EntMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                tagChip(kind: m.kind ?? "binary")
                Spacer()
                if let resolves = m.resolutionDate {
                    Text("Resolves \(formatDate(resolves))")
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                }
            }

            Text(m.q)
                .font(.subheadline).fontWeight(.semibold)
                .lineLimit(2)

            if let hook = m.hook {
                Text(hook).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }

            if m.outcomeCount <= 2 {
                yesNoBar(yes: m.prob, no: 100 - m.prob)
            } else {
                VStack(spacing: 4) {
                    ForEach(Array(m.topOutcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                        outcomeRow(o, isLeader: false)
                    }
                }
            }

            sourceChip(m.src)
        }
        .padding(12)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.1)))
        .padding(.horizontal)
    }

    // MARK: - Tech & Culture

    private func techCultureSection(_ data: EntThemeTechCulture) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "💻", title: "Tech & Culture", count: data.count)

            if let markets = data.markets {
                entMarketList(markets.prefix(8).map { $0 }, title: nil)
            }
        }
    }

    // MARK: - Shared components

    private func sectionHeader(emoji: String, title: String, count: Int? = nil) -> some View {
        HStack {
            Text("\(emoji) \(title)")
                .font(.headline).fontWeight(.bold)
            Spacer()
            if let count {
                Text("\(count) markets")
                    .font(.caption2)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.1))
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal)
    }

    private func entMarketList(_ markets: [EntMarketRow], title: String?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title {
                Text(title)
                    .font(.caption).fontWeight(.semibold).foregroundStyle(.secondary)
                    .padding(.horizontal)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(markets.prefix(6)) { m in
                    NavigationLink(value: Route.futuresDetail(id: m.marketId)) {
                        entMarketCard(m)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
    }

    private func entMarketCard(_ m: EntMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                tagChip(kind: m.kind ?? "binary")
                Spacer()
                if m.outcomeCount > 3 {
                    Text("+\(m.outcomeCount - 3)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
            }

            Text(m.q)
                .font(.caption).fontWeight(.medium)
                .lineLimit(2).foregroundStyle(.primary)

            ForEach(Array(m.topOutcomes.prefix(2).enumerated()), id: \.offset) { _, o in
                HStack(spacing: 4) {
                    Text(o.name).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                    Spacer()
                    Text("\(Int(o.prob))%")
                        .font(.caption2).fontWeight(.bold).monospacedDigit()
                        .foregroundStyle(o.prob > 50 ? .primary : .secondary)
                }
            }

            sourceChip(m.src)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.1)))
    }

    private func tagChip(kind: String) -> some View {
        HStack(spacing: 3) {
            Text(kindEmoji[kind] ?? "✦").font(.system(size: 10))
            Text(kindLabel[kind] ?? "Market")
        }
        .font(.system(size: 9, weight: .semibold))
        .padding(.horizontal, 5).padding(.vertical, 2)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private func sourceChip(_ label: String) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(label == "kalshi" ? Color.green : Color.blue)
                .frame(width: 5, height: 5)
            Text(label.capitalized)
        }
        .font(.system(size: 9, weight: .semibold))
        .padding(.horizontal, 5).padding(.vertical, 1)
        .background((label == "kalshi" ? Color.green : Color.blue).opacity(0.08))
        .clipShape(Capsule())
    }

    private func yesNoBar(yes: Double, no: Double) -> some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                Text("YES \(Int(yes))%")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(.green)
                    .frame(width: geo.size.width * yes / 100, alignment: .leading)
                    .padding(.leading, 8)
                    .background(Color.green.opacity(0.12))
                Text("NO \(Int(no))%")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .frame(width: geo.size.width * no / 100, alignment: .trailing)
                    .padding(.trailing, 8)
                    .background(Color.secondary.opacity(0.06))
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .frame(height: 28)
    }

    private func footer(_ data: EntertainmentResponse) -> some View {
        Text("Kalshi & Polymarket · \(data.totalMarkets) markets · Not financial advice")
            .font(.caption2).foregroundStyle(.tertiary)
            .padding(.horizontal)
    }

    private func formatDate(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate, .withDashSeparatorInDate]
        guard let date = formatter.date(from: String(iso.prefix(10))) else { return iso }
        let df = DateFormatter()
        df.dateFormat = "MMM d"
        return df.string(from: date)
    }
}
