import SwiftUI
import Combine
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

private let entertainmentPink = Color(red: 0.85, green: 0.15, blue: 0.55)
private let entertainmentMagenta = Color(red: 0.70, green: 0.10, blue: 0.85)

private let kindAccent: [String: Color] = [
    "spotify": Color(red: 0.12, green: 0.84, blue: 0.38),
    "billboard": Color(red: 0.95, green: 0.60, blue: 0.10),
    "boxoffice": Color(red: 0.20, green: 0.60, blue: 0.95),
    "rt": Color(red: 0.90, green: 0.20, blue: 0.20),
    "reality": Color(red: 0.85, green: 0.30, blue: 0.70),
    "eurovision": Color(red: 0.65, green: 0.25, blue: 0.90),
    "multi": entertainmentPink,
    "binary": entertainmentPink,
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
        .onAppear { AnalyticsService.trackScreen(name: "entertainment", type: "entertainment") }
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
        VStack(alignment: .leading, spacing: 8) {
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
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [
                    entertainmentPink.opacity(0.07),
                    entertainmentMagenta.opacity(0.07)
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(
                    LinearGradient(
                        colors: [
                            entertainmentPink.opacity(0.18),
                            entertainmentMagenta.opacity(0.18)
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    ),
                    lineWidth: 0.5
                )
        )
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
        VStack(alignment: .leading, spacing: 10) {
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
        .padding(16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
        .padding(.horizontal)
    }

    // MARK: - Card body by kind

    @ViewBuilder
    private func cardBody(_ m: EntMarketRow) -> some View {
        let outcomes = m.topOutcomes

        if (m.kind == "spotify" || m.kind == "billboard") && outcomes.count >= 2 {
            VStack(spacing: 6) {
                outcomeRow(outcomes[0], isLeader: true, kind: m.kind)
                outcomeRow(outcomes[1], isLeader: false, kind: m.kind)
            }
        } else if m.kind == "reality" && m.outcomeCount <= 2 && outcomes.count >= 2 {
            binaryBar(a: outcomes[0], b: outcomes[1])
        } else if outcomes.count > 2 {
            VStack(spacing: 5) {
                ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                    outcomeRow(o, isLeader: false, kind: m.kind)
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

    private func outcomeRow(_ o: EntOutcome, isLeader: Bool, kind: String? = nil) -> some View {
        HStack(spacing: 8) {
            Text(o.name)
                .font(.caption)
                .fontWeight(isLeader ? .semibold : .regular)
                .foregroundStyle(isLeader ? .primary : .secondary)
                .lineLimit(1)
            Spacer()
            if let delta = o.delta24h, abs(delta) > 0.1 {
                HStack(spacing: 2) {
                    Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                        .font(.system(size: 7, weight: .bold))
                    Text("\(abs(delta), specifier: "%.1f")%")
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                }
                .foregroundColor(delta > 0 ? .green : .red)
                .padding(.horizontal, 5).padding(.vertical, 2)
                .background((delta > 0 ? Color.green : Color.red).opacity(0.08), in: Capsule())
            }
            Text("\(Int(o.prob))%")
                .font(.caption).fontWeight(.bold).monospacedDigit()
        }
        .overlay(alignment: .bottom) {
            GeometryReader { geo in
                let accent = kindAccent[kind ?? "binary"] ?? entertainmentPink
                RoundedRectangle(cornerRadius: 2)
                    .fill(isLeader ? accent.opacity(0.25) : Color.secondary.opacity(0.10))
                    .frame(width: geo.size.width * o.prob / 100, height: 2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 2)
            .offset(y: 3)
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
                        .fill(entertainmentPink)
                        .frame(width: geo.size.width * a.prob / 100)
                    RoundedRectangle(cornerRadius: 99)
                        .fill(entertainmentPink.opacity(0.3))
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
                entMarketList(billboard, title: "📊 Billboard")
            }

            if let albums = data.albumDrops, !albums.isEmpty {
                entMarketList(albums, title: "💿 Album Drops")
            }
        }
    }

    private func spotifyRace(_ markets: [EntMarketRow]) -> some View {
        let best = markets.max(by: { $0.topOutcomes.count < $1.topOutcomes.count }) ?? markets[0]
        let spotifyGreen = Color(red: 0.12, green: 0.84, blue: 0.38)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Text("🎧")
                    .font(.system(size: 12))
                Text("Spotify Chart Race")
                    .font(.caption).fontWeight(.bold).textCase(.uppercase)
                    .foregroundStyle(spotifyGreen)
            }
            .padding(.horizontal)

            Text(best.q)
                .font(.caption).fontWeight(.medium)
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(Array(best.topOutcomes.prefix(6).enumerated()), id: \.offset) { idx, o in
                    HStack(spacing: 8) {
                        Text("\(idx + 1)")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundStyle(idx == 0 ? spotifyGreen : .secondary)
                            .frame(width: 20, alignment: .trailing)

                        Text(o.name)
                            .font(.caption).fontWeight(idx == 0 ? .semibold : .medium)
                            .lineLimit(1)

                        Spacer()

                        if let delta = o.delta24h, abs(delta) > 0.1 {
                            HStack(spacing: 2) {
                                Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                                    .font(.system(size: 7, weight: .bold))
                                Text("\(abs(delta), specifier: "%.1f")%")
                                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                            }
                            .foregroundColor(delta > 0 ? .green : .red)
                            .padding(.horizontal, 4).padding(.vertical, 1)
                            .background((delta > 0 ? Color.green : Color.red).opacity(0.08), in: Capsule())
                        }

                        Text("\(Int(o.prob))%")
                            .font(.caption).fontWeight(.bold).monospacedDigit()
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
                    .background(idx == 0 ? spotifyGreen.opacity(0.04) : .clear)
                    .overlay(alignment: .bottom) {
                        GeometryReader { geo in
                            RoundedRectangle(cornerRadius: 2)
                                .fill(spotifyGreen.opacity(idx == 0 ? 0.20 : 0.08))
                                .frame(width: geo.size.width * o.prob / 100, height: 2)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(height: 2)
                    }
                    if idx < min(best.topOutcomes.count, 6) - 1 {
                        Divider()
                    }
                }
            }
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
            .padding(.horizontal)
        }
    }

    // MARK: - Movies & TV section

    private func moviesTVSection(_ data: EntThemeMoviesTV) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🎬", title: "Movies & TV", count: data.count)

            if let rt = data.rtMarkets, !rt.isEmpty {
                entMarketList(rt, title: "🍅 Rotten Tomatoes")
            }

            if let box = data.boxOffice, !box.isEmpty {
                entMarketList(box, title: "🎟 Box Office")
            }

            if let reality = data.realityTv, !reality.isEmpty {
                entMarketList(reality, title: "📺 Reality TV")
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
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                tagChip(kind: m.kind ?? "binary")
                Spacer()
                if let resolves = m.resolutionDate {
                    HStack(spacing: 3) {
                        Image(systemName: "calendar")
                            .font(.system(size: 8))
                        Text(formatDate(resolves))
                    }
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
                VStack(spacing: 5) {
                    ForEach(Array(m.topOutcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                        outcomeRow(o, isLeader: false, kind: m.kind)
                    }
                }
            }

            sourceChip(m.src)
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.05), radius: 8, x: 0, y: 3)
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
                .font(.title3).fontWeight(.bold)
            Spacer()
            if let count {
                Text("\(count)")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                +
                Text(" markets")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal)
    }

    private func entMarketList(_ markets: [EntMarketRow], title: String?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title {
                Text(title)
                    .font(.caption).fontWeight(.bold).foregroundStyle(.secondary)
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
        VStack(alignment: .leading, spacing: 8) {
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
                .font(.caption).fontWeight(.semibold)
                .lineLimit(2).foregroundStyle(.primary)

            VStack(spacing: 5) {
                ForEach(Array(m.topOutcomes.prefix(2).enumerated()), id: \.offset) { _, o in
                    HStack(spacing: 4) {
                        Text(o.name).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                        Spacer()
                        Text("\(Int(o.prob))%")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(o.prob > 50 ? .primary : .secondary)
                    }
                    .overlay(alignment: .bottom) {
                        GeometryReader { geo in
                            let accent = kindAccent[m.kind ?? "binary"] ?? entertainmentPink
                            RoundedRectangle(cornerRadius: 2)
                                .fill(o.prob > 50
                                      ? accent.opacity(0.18)
                                      : Color.secondary.opacity(0.08))
                                .frame(width: geo.size.width * o.prob / 100, height: 2)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(height: 2)
                        .offset(y: 3)
                    }
                }
            }

            sourceChip(m.src)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }

    private func tagChip(kind: String) -> some View {
        let accent = kindAccent[kind] ?? entertainmentPink
        return HStack(spacing: 3) {
            Text(kindEmoji[kind] ?? "✦").font(.system(size: 10))
            Text(kindLabel[kind] ?? "Market")
        }
        .font(.system(size: 9, weight: .semibold))
        .padding(.horizontal, 6).padding(.vertical, 3)
        .background(accent.opacity(0.10))
        .foregroundStyle(accent)
        .clipShape(RoundedRectangle(cornerRadius: 5))
        .overlay(RoundedRectangle(cornerRadius: 5).stroke(accent.opacity(0.15), lineWidth: 0.5))
    }

    private func sourceChip(_ label: String) -> some View {
        let color: Color = label == "kalshi" ? .green : .blue
        return HStack(spacing: 5) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
                .overlay(Circle().stroke(color.opacity(0.3), lineWidth: 2))
            Text(label.capitalized)
                .foregroundStyle(.primary.opacity(0.7))
        }
        .font(.system(size: 10, weight: .semibold))
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(color.opacity(0.08))
        .clipShape(Capsule())
        .overlay(Capsule().stroke(color.opacity(0.12), lineWidth: 0.5))
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
        HStack(spacing: 6) {
            Image(systemName: "info.circle")
                .font(.system(size: 10))
            Text("Kalshi & Polymarket \u{00B7} \(data.totalMarkets) markets \u{00B7} Not financial advice")
        }
        .font(.caption2).foregroundStyle(.tertiary)
        .padding(.horizontal)
        .padding(.bottom, 8)
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
