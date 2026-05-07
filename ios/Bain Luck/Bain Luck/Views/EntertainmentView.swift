import SwiftUI
import os

private let logger = Logger(subsystem: "com.bainluck", category: "entertainment")

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

private let sectionOrder = [
    "movies", "tv_streaming", "music", "awards",
    "social_media", "celebrity", "viral", "other",
]

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
            VStack(spacing: 20) {
                HStack {
                    Text("\(data.totalMarkets) markets")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("·").foregroundStyle(.secondary)
                    Text("Kalshi \(data.bySource.kalshi)")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("·").foregroundStyle(.secondary)
                    Text("Polymarket \(data.bySource.polymarket)")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal)

                ForEach(sectionOrder, id: \.self) { key in
                    if let section = data.sections[key], !section.markets.isEmpty {
                        sectionView(section)
                    }
                }
            }
            .padding(.vertical)
        }
    }

    private func sectionView(_ section: EntertainmentSection) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(section.label).font(.headline).fontWeight(.bold)
                Spacer()
                Text("\(section.count) active")
                    .font(.caption2)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.1))
                    .clipShape(Capsule())
            }
            .padding(.horizontal)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(section.markets) { market in
                    NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                        marketCard(market)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
    }

    private func marketCard(_ m: CategoryMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(m.q)
                .font(.caption).fontWeight(.medium)
                .lineLimit(2).foregroundStyle(.primary)

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
