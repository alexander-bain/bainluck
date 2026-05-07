import SwiftUI
import os

private let logger = Logger(subsystem: "com.bainluck", category: "politics")

final class PoliticsViewModel: ObservableObject {
    @Published var data: PoliticsResponse?
    @Published var loading = true
    @Published var error: String?

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await APIClient.shared.fetchPolitics()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Politics load failed: \(error)")
        }
    }
}

struct PoliticsView: View {
    @StateObject private var vm = PoliticsViewModel()

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading politics data...")
            } else if let error = vm.error, vm.data == nil {
                ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if let data = vm.data {
                politicsContent(data)
            }
        }
        .navigationTitle("Politics")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private func politicsContent(_ data: PoliticsResponse) -> some View {
        ScrollView {
            VStack(spacing: 20) {
                HStack {
                    Text("\(data.totalMarkets) markets")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("·")
                        .foregroundStyle(.secondary)
                    Text("Kalshi \(data.bySource.kalshi)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("·")
                        .foregroundStyle(.secondary)
                    Text("Polymarket \(data.bySource.polymarket)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal)

                if let pres = data.themes.presidential, pres.count > 0 {
                    presidentialSection(pres)
                }

                themeSection("Congressional", data.themes.congressional)
                themeSection("Gubernatorial", data.themes.gubernatorial)
                themeSection("Policy & Legislation", data.themes.policy)
                themeSection("Supreme Court", data.themes.scotus)
                themeSection("International", data.themes.international)
                themeSection("Other", data.themes.other)
            }
            .padding(.vertical)
        }
    }

    private func presidentialSection(_ pres: PoliticsPresidential) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Presidential 2028")
                    .font(.headline).fontWeight(.bold)
                Spacer()
                Text("\(pres.count) active")
                    .font(.caption2)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.1))
                    .clipShape(Capsule())
            }
            .padding(.horizontal)

            if let headline = pres.headline {
                VStack(alignment: .leading, spacing: 6) {
                    Text(headline.q).font(.subheadline).fontWeight(.semibold)
                    ForEach(Array(headline.candidates.prefix(6).enumerated()), id: \.offset) { idx, c in
                        HStack(spacing: 8) {
                            Text("\(idx + 1)")
                                .font(.caption2).foregroundStyle(.secondary)
                                .frame(width: 16)
                            Text(c.name).font(.caption).lineLimit(1)
                            Spacer()
                            Text("\(Int(c.prob))%")
                                .font(.caption).fontWeight(.bold).monospacedDigit()
                        }
                    }
                    Text("\(headline.outcomeCount) candidates · \(headline.src)")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                .padding(12)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.secondary.opacity(0.1)))
                .padding(.horizontal)
            }

            if let side = pres.sideMarkets, !side.isEmpty {
                marketGrid(side)
            }
        }
    }

    private func themeSection(_ title: String, _ theme: PoliticsSimple?) -> some View {
        Group {
            if let theme, theme.count > 0, let markets = theme.markets, !markets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(title).font(.headline).fontWeight(.bold)
                        Spacer()
                        Text("\(theme.count) active")
                            .font(.caption2)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.1))
                            .clipShape(Capsule())
                    }
                    .padding(.horizontal)

                    marketGrid(markets)
                }
            }
        }
    }

    private func marketGrid(_ markets: [CategoryMarketRow]) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            ForEach(markets) { market in
                NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                    marketCard(market)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal)
    }

    private func marketCard(_ m: CategoryMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(m.q)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .foregroundStyle(.primary)

            ForEach(Array(m.topOutcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                HStack(spacing: 4) {
                    Text(o.name).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                    Spacer()
                    Text("\(Int(o.prob))%")
                        .font(.caption2).fontWeight(.bold).monospacedDigit()
                        .foregroundStyle(o.prob > 50 ? .primary : .secondary)
                }
            }

            if m.outcomeCount > 3 {
                Text("+\(m.outcomeCount - 3) more")
                    .font(.caption2).foregroundStyle(.tertiary)
            }

            Text(m.src)
                .font(.caption2)
                .padding(.horizontal, 5).padding(.vertical, 1)
                .background(Color.secondary.opacity(0.08))
                .clipShape(Capsule())
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.1)))
    }
}
