import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "economics")

// MARK: - ViewModel

final class EconomicsViewModel: ObservableObject {
    @Published var data: EconomicsResponse?
    @Published var loading = true
    @Published var error: String?

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await APIClient.shared.fetchEconomics()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Economics load failed: \(error)")
        }
    }
}

// MARK: - Constants

private let econPurple = Color(red: 0.38, green: 0.22, blue: 0.78)
private let econIndigo = Color(red: 0.25, green: 0.32, blue: 0.85)

private let themeEmoji: [String: String] = [
    "fed_side": "🏦", "inflation": "📊", "jobs": "💼",
    "recession": "📉", "markets": "📈", "energy": "⛽",
    "housing": "🏠", "trade": "🚢", "government": "🏛",
]

private let themeLabel: [String: String] = [
    "fed_side": "Fed Side Markets", "inflation": "Inflation / CPI",
    "jobs": "Jobs & Employment", "recession": "GDP & Recession",
    "markets": "Markets & Indices", "energy": "Energy",
    "housing": "Housing", "trade": "Trade & Tariffs",
    "government": "Government & Fiscal",
]

// MARK: - Theme Info

private struct ThemeInfo: Identifiable {
    let id: String
    let label: String
    let emoji: String
    let count: Int
    let markets: [EconomicsMarket]
}

// MARK: - View

struct EconomicsView: View {
    @StateObject private var vm = EconomicsViewModel()
    @State private var selectedTheme: String?

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading economics data...")
            } else if let error = vm.error, vm.data == nil {
                ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if let data = vm.data {
                economicsContent(data)
            }
        }
        .navigationTitle("Economics")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "economics", type: "economics") }
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private func economicsContent(_ data: EconomicsResponse) -> some View {
        let themes = buildThemes(data.themes)
        return ScrollView {
            VStack(spacing: 24) {
                pageHeader(data)

                if let fed = data.themes.fed, let meetings = fed.fomcMeetings, !meetings.isEmpty {
                    fomcSection(meetings)
                }

                if let inf = data.themes.inflation, let cpi = inf.cpiReleases, !cpi.isEmpty {
                    cpiSection(cpi)
                }

                ForEach(themes) { theme in
                    themeSection(theme)
                }

                footer(data)
            }
            .padding(.vertical)
        }
    }

    // MARK: - Page Header

    private func pageHeader(_ data: EconomicsResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Probabilities for Fed policy, inflation, jobs, markets, and the broader economy.")
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
                    econIndigo.opacity(0.06),
                    econPurple.opacity(0.06)
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
                            econIndigo.opacity(0.15),
                            econPurple.opacity(0.15)
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    ),
                    lineWidth: 0.5
                )
        )
        .padding(.horizontal)
    }

    // MARK: - FOMC Meetings

    private func fomcSection(_ meetings: [FOMCMeeting]) -> some View {
        let upcoming = meetings.filter { !$0.resolved }
        return VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🏦", title: "Federal Reserve", count: upcoming.count)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(upcoming) { meeting in
                        fomcCard(meeting)
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    private func fomcCard(_ meeting: FOMCMeeting) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(meeting.mo)
                    .font(.title3)
                    .fontWeight(.bold)
                Spacer()
                Text("FOMC")
                    .font(.system(size: 9, weight: .heavy))
                    .foregroundColor(econPurple)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(econPurple.opacity(0.08))
                    .clipShape(Capsule())
            }

            Text(meeting.date)
                .font(.caption)
                .foregroundStyle(.secondary)

            Divider()
                .padding(.vertical, 2)

            ForEach(Array(meeting.dist.prefix(4).enumerated()), id: \.offset) { idx, pair in
                if pair.count >= 2, let prob = pair[0].doubleValue, let rate = pair[1].stringValue, prob >= 1 {
                    HStack(spacing: 6) {
                        Text(rate)
                            .font(.caption)
                            .fontWeight(.semibold)
                            .frame(width: 50, alignment: .leading)
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule()
                                    .fill(Color.secondary.opacity(0.08))
                                Capsule()
                                    .fill(
                                        LinearGradient(
                                            colors: [econIndigo.opacity(0.4), econPurple],
                                            startPoint: .leading,
                                            endPoint: .trailing
                                        )
                                    )
                                    .frame(width: max(2, geo.size.width * min(prob / 100, 1)))
                            }
                        }
                        .frame(height: 14)
                        Text("\(Int(prob))%")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .monospacedDigit()
                            .foregroundColor(prob > 50 ? econPurple : .secondary)
                            .frame(width: 32, alignment: .trailing)
                    }
                }
            }
        }
        .padding(14)
        .frame(width: 240)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
    }

    // MARK: - CPI Releases

    private func cpiSection(_ releases: [CPIRelease]) -> some View {
        let upcoming = releases.filter { $0.upcoming == true }
        return Group {
            if !upcoming.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    sectionHeader(emoji: "📊", title: "Inflation / CPI", count: upcoming.count)

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 12) {
                            ForEach(upcoming) { release in
                                cpiCard(release)
                            }
                        }
                        .padding(.horizontal)
                    }
                }
            }
        }
    }

    private func cpiCard(_ release: CPIRelease) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(release.mo)
                    .font(.title3)
                    .fontWeight(.bold)
                Spacer()
                Text("CPI")
                    .font(.system(size: 9, weight: .heavy))
                    .foregroundColor(.orange)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.orange.opacity(0.08))
                    .clipShape(Capsule())
            }

            if let peak = release.peakIs {
                HStack(spacing: 4) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 9))
                        .foregroundColor(.orange)
                    Text("Peak: \(peak)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if let brackets = release.brackets, !brackets.isEmpty {
                Divider()
                    .padding(.vertical, 2)

                ForEach(Array(brackets.prefix(4).enumerated()), id: \.offset) { _, pair in
                    if pair.count >= 2, let prob = pair[0].doubleValue, let label = pair[1].stringValue, prob >= 1 {
                        HStack(spacing: 6) {
                            Text(label)
                                .font(.caption)
                                .fontWeight(.semibold)
                                .frame(width: 60, alignment: .leading)
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    Capsule()
                                        .fill(Color.secondary.opacity(0.08))
                                    Capsule()
                                        .fill(
                                            LinearGradient(
                                                colors: [Color.orange.opacity(0.4), Color.orange],
                                                startPoint: .leading,
                                                endPoint: .trailing
                                            )
                                        )
                                        .frame(width: max(2, geo.size.width * min(prob / 100, 1)))
                                }
                            }
                            .frame(height: 14)
                            Text("\(Int(prob))%")
                                .font(.system(size: 11, weight: .bold, design: .rounded))
                                .monospacedDigit()
                                .foregroundColor(prob > 50 ? .orange : .secondary)
                                .frame(width: 32, alignment: .trailing)
                        }
                    }
                }
            }
        }
        .padding(14)
        .frame(width: 240)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
    }

    // MARK: - Generic Theme Sections

    private func buildThemes(_ themes: EconomicsThemes) -> [ThemeInfo] {
        var result: [ThemeInfo] = []
        if let t = themes.jobs { result.append(ThemeInfo(id: "jobs", label: "Jobs & Employment", emoji: "💼", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.inflation { result.append(ThemeInfo(id: "inflation", label: "Inflation / CPI", emoji: "📊", count: t.count, markets: t.sideMarkets ?? [])) }
        if let t = themes.recession { result.append(ThemeInfo(id: "recession", label: "GDP & Recession", emoji: "📉", count: t.count, markets: t.markets ?? t.sideMarkets ?? [])) }
        if let t = themes.markets { result.append(ThemeInfo(id: "markets", label: "Markets & Indices", emoji: "📈", count: t.count, markets: t.markets ?? t.sideMarkets ?? [])) }
        if let t = themes.energy { result.append(ThemeInfo(id: "energy", label: "Energy", emoji: "⛽", count: t.count, markets: t.markets ?? t.sideMarkets ?? [])) }
        if let t = themes.housing { result.append(ThemeInfo(id: "housing", label: "Housing", emoji: "🏠", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.trade { result.append(ThemeInfo(id: "trade", label: "Trade & Tariffs", emoji: "🚢", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.government { result.append(ThemeInfo(id: "government", label: "Government & Fiscal", emoji: "🏛", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.fed { result.append(ThemeInfo(id: "fed_side", label: "Fed Side Markets", emoji: "🏦", count: t.sideMarkets?.count ?? 0, markets: t.sideMarkets ?? [])) }
        return result.filter { !$0.markets.isEmpty }
    }

    private func themeSection(_ theme: ThemeInfo) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: theme.emoji, title: theme.label, count: theme.count)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(theme.markets.prefix(8)) { market in
                    NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                        marketCard(market)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)

            if theme.markets.count > 8 {
                Text("+\(theme.markets.count - 8) more")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal)
            }
        }
    }

    // MARK: - Market Card (Discover-style)

    private func marketCard(_ market: EconomicsMarket) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(market.q)
                .font(.caption).fontWeight(.semibold)
                .lineLimit(2)
                .foregroundStyle(.primary)

            Spacer(minLength: 0)

            // Probability bar
            HStack(spacing: 6) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.secondary.opacity(0.08))
                        RoundedRectangle(cornerRadius: 3)
                            .fill(
                                LinearGradient(
                                    colors: [econIndigo.opacity(0.5), econPurple],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: max(4, geo.size.width * market.prob / 100))
                    }
                }
                .frame(height: 6)

                Text(market.prob.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(market.prob))%" : String(format: "%.1f%%", market.prob))
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundColor(market.prob > 50 ? .primary : .secondary)
            }

            HStack(spacing: 4) {
                if let delta = market.delta, abs(delta) >= 1 {
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

                Spacer()

                sourceChip(market.src, color: market.src == "kalshi" ? .green : .blue)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(minHeight: 100)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }

    // MARK: - Shared Components

    private func sectionHeader(emoji: String, title: String, count: Int?) -> some View {
        HStack {
            Text("\(emoji) \(title)")
                .font(.title3).fontWeight(.bold)
            Spacer()
            if let count {
                HStack(spacing: 2) {
                    Text("\(count)")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                    Text("markets")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.horizontal)
    }

    private func sourceChip(_ label: String, color: Color) -> some View {
        HStack(spacing: 5) {
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

    private func footer(_ data: EconomicsResponse) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "info.circle")
                .font(.system(size: 10))
            Text("Data from Kalshi & Polymarket \u{00B7} Not financial advice")
        }
        .font(.caption2).foregroundStyle(.tertiary)
        .padding(.horizontal)
        .padding(.bottom, 8)
    }
}
