import SwiftUI
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
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private func economicsContent(_ data: EconomicsResponse) -> some View {
        let themes = buildThemes(data.themes)
        return ScrollView {
            VStack(spacing: 16) {
                HStack {
                    Text("\(data.totalMarkets) markets")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal)

                if let fed = data.themes.fed, let meetings = fed.fomcMeetings, !meetings.isEmpty {
                    fomcSection(meetings)
                }

                ForEach(themes) { theme in
                    themeSection(theme)
                }
            }
            .padding(.vertical)
        }
    }

    // MARK: - FOMC Meetings

    private func fomcSection(_ meetings: [FOMCMeeting]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("🏦")
                Text("Federal Reserve")
                    .font(.headline)
                    .fontWeight(.bold)
                Text("\(meetings.count)")
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
            .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(meetings.filter { !$0.resolved }) { meeting in
                        fomcCard(meeting)
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    private func fomcCard(_ meeting: FOMCMeeting) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(meeting.mo)
                .font(.headline)
                .fontWeight(.bold)
            Text(meeting.date)
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(Array(meeting.dist.prefix(4).enumerated()), id: \.offset) { idx, pair in
                if pair.count >= 2, let prob = pair[0].doubleValue, let rate = pair[1].stringValue, prob >= 1 {
                    HStack(spacing: 6) {
                        Text(rate)
                            .font(.caption)
                            .fontWeight(.medium)
                            .frame(width: 44, alignment: .leading)
                        GeometryReader { geo in
                            Capsule()
                                .fill(Color.secondary.opacity(0.08))
                                .overlay(alignment: .leading) {
                                    Capsule()
                                        .fill(prob > 50 ? Color.blue : Color.secondary.opacity(0.3))
                                        .frame(width: max(2, geo.size.width * min(prob / 100, 1)))
                                }
                        }
                        .frame(height: 14)
                        Text("\(Int(prob))%")
                            .font(.caption2)
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .frame(width: 32, alignment: .trailing)
                    }
                }
            }
        }
        .padding(12)
        .frame(width: 220)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.secondary.opacity(0.1)))
    }

    // MARK: - Generic Theme Sections

    private func buildThemes(_ themes: EconomicsThemes) -> [ThemeInfo] {
        var result: [ThemeInfo] = []
        if let t = themes.jobs { result.append(ThemeInfo(id: "jobs", label: "Jobs & Employment", emoji: "👷", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.inflation { result.append(ThemeInfo(id: "inflation", label: "Inflation / CPI", emoji: "📊", count: t.count, markets: t.sideMarkets ?? [])) }
        if let t = themes.recession { result.append(ThemeInfo(id: "recession", label: "GDP & Recession", emoji: "📉", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.markets { result.append(ThemeInfo(id: "markets", label: "Markets & Indices", emoji: "📈", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.energy { result.append(ThemeInfo(id: "energy", label: "Energy", emoji: "⛽", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.housing { result.append(ThemeInfo(id: "housing", label: "Housing", emoji: "🏠", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.trade { result.append(ThemeInfo(id: "trade", label: "Trade & Tariffs", emoji: "🚢", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.government { result.append(ThemeInfo(id: "government", label: "Government & Fiscal", emoji: "🏛", count: t.count, markets: t.markets ?? [])) }
        if let t = themes.fed { result.append(ThemeInfo(id: "fed_side", label: "Fed Side Markets", emoji: "🏦", count: t.sideMarkets?.count ?? 0, markets: t.sideMarkets ?? [])) }
        return result.filter { !$0.markets.isEmpty }
    }

    private func themeSection(_ theme: ThemeInfo) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(theme.emoji)
                Text(theme.label)
                    .font(.headline)
                    .fontWeight(.bold)
                Text("\(theme.count)")
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
                Spacer()
            }

            ForEach(theme.markets.prefix(8)) { market in
                marketRow(market)
            }

            if theme.markets.count > 8 {
                Text("+\(theme.markets.count - 8) more")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
    }

    private func marketRow(_ market: EconomicsMarket) -> some View {
        NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(market.q)
                        .font(.subheadline)
                        .lineLimit(2)
                        .foregroundStyle(.primary)
                    Text(market.src.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Spacer()
                if let delta = market.delta, abs(delta) >= 1 {
                    Image(systemName: delta > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(delta > 0 ? .green : .red)
                }
                Text("\(market.prob)%")
                    .font(.title3)
                    .fontWeight(.black)
                    .monospacedDigit()
            }
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
    }
}
