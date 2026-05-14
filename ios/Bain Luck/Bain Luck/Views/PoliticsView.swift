import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "politics")

// MARK: - ViewModel

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

// MARK: - Constants

private let partyColor: [String: Color] = [
    "R": Color(red: 0.863, green: 0.149, blue: 0.149),
    "D": Color(red: 0.145, green: 0.388, blue: 0.922),
    "I": Color(red: 0.55, green: 0.35, blue: 0.78),
]

private let themeEmoji: [String: String] = [
    "presidential": "🏛", "congressional": "🏤", "gubernatorial": "🗺",
    "policy": "📜", "scotus": "⚖", "international": "🌍", "other": "📊",
]

private let themeLabel: [String: String] = [
    "presidential": "Presidential 2028", "congressional": "Congressional",
    "gubernatorial": "Gubernatorial", "policy": "Policy & Legislation",
    "scotus": "Supreme Court", "international": "International", "other": "Other",
]

// MARK: - View

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
        .onAppear { AnalyticsService.trackScreen(name: "politics", type: "politics") }
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private func politicsContent(_ data: PoliticsResponse) -> some View {
        ScrollView {
            VStack(spacing: 24) {
                pageHeader(data)

                if let pres = data.themes.presidential, pres.candidates.count > 0 {
                    presHeroSection(pres)
                }

                if let cong = data.themes.congressional, cong.count > 0 {
                    congressionalSection(cong)
                }

                if let cs = data.crossSource, !cs.isEmpty {
                    crossSourceSection(cs)
                }

                themeSection("gubernatorial", data.themes.gubernatorial)
                themeSection("policy", data.themes.policy)
                themeSection("scotus", data.themes.scotus)
                themeSection("international", data.themes.international)
                themeSection("other", data.themes.other)

                footer(data)
            }
            .padding(.vertical)
        }
    }

    // MARK: - Page header

    private func pageHeader(_ data: PoliticsResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Probabilities for races, policy, and power across U.S. and global politics.")
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
                    partyColor["D"]!.opacity(0.06),
                    partyColor["R"]!.opacity(0.06)
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
                            partyColor["D"]!.opacity(0.15),
                            partyColor["R"]!.opacity(0.15)
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    ),
                    lineWidth: 0.5
                )
        )
        .padding(.horizontal)
    }

    // MARK: - Presidential hero (bar-race)

    private func presHeroSection(_ pres: PoliticsPresidential) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🏛", title: "Presidential 2028", count: pres.count)

            VStack(alignment: .leading, spacing: 8) {
                if let q = pres.headlineQ {
                    Text(q).font(.subheadline).fontWeight(.semibold)
                }

                if pres.hasDualSource == true {
                    HStack(spacing: 8) {
                        sourceChip("Kalshi", color: .green)
                        sourceChip("Polymarket", color: .blue)
                    }
                }

                ForEach(Array(pres.candidates.prefix(10).enumerated()), id: \.element.id) { idx, c in
                    candidateRow(c, rank: idx + 1)
                }

                if pres.candidates.count > 10 {
                    Text("+\(pres.candidates.count - 10) more candidates")
                        .font(.caption2).foregroundStyle(.tertiary)
                }
            }
            .padding(16)
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
            .padding(.horizontal)

            if let side = pres.sideMarkets, !side.isEmpty {
                Text("Related markets").font(.caption).fontWeight(.semibold).foregroundStyle(.secondary)
                    .padding(.horizontal)
                marketGrid(side)
            }
        }
    }

    private func candidateRow(_ c: PoliticsCandidate, rank: Int) -> some View {
        let pColor = partyColor[c.party] ?? .gray
        return VStack(spacing: 0) {
            HStack(spacing: 8) {
                Text("\(rank)")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundColor(pColor.opacity(0.6))
                    .frame(width: 18, alignment: .trailing)

                Text(c.party)
                    .font(.system(size: 10, weight: .heavy))
                    .foregroundColor(.white)
                    .frame(width: 22, height: 22)
                    .background(pColor)
                    .clipShape(RoundedRectangle(cornerRadius: 5))
                    .shadow(color: pColor.opacity(0.3), radius: 2, x: 0, y: 1)

                Text(c.name)
                    .font(.subheadline).fontWeight(.medium)
                    .lineLimit(1)

                Spacer()

                if let change = c.change7d, abs(change) > 0.1 {
                    HStack(spacing: 2) {
                        Image(systemName: change > 0 ? "arrow.up.right" : "arrow.down.right")
                            .font(.system(size: 8, weight: .bold))
                        Text("\(abs(change), specifier: "%.1f")%")
                            .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    }
                    .foregroundColor(change > 0 ? .green : .red)
                    .padding(.horizontal, 5).padding(.vertical, 2)
                    .background((change > 0 ? Color.green : Color.red).opacity(0.08), in: Capsule())
                }

                Text("\(c.merged, specifier: "%.1f")%")
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundColor(rank <= 3 ? .primary : .secondary)
            }

            // Probability bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.barTrack.opacity(0.15))
                        .frame(height: 4)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(
                            LinearGradient(
                                colors: [pColor.opacity(0.5), pColor],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: max(geo.size.width * c.merged / 100, 4), height: 4)
                }
            }
            .frame(height: 4)
            .padding(.leading, 50)
            .padding(.top, 4)
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 6)
        .background(rank <= 3 ? pColor.opacity(0.03) : .clear)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Congressional

    private func congressionalSection(_ cong: PoliticsCongressional) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "🏤", title: "Congressional", count: cong.count)

            if let cc = cong.chamberControl {
                HStack(spacing: 10) {
                    if let senate = cc.senate {
                        chamberCard("Senate", probs: senate)
                    }
                    if let house = cc.house {
                        chamberCard("House", probs: house)
                    }
                }
                .padding(.horizontal)
            }

            if let map = cong.senateMap, !map.isEmpty {
                senateMapGrid(map)
            }

            if let markets = cong.markets, !markets.isEmpty {
                marketGrid(markets)
            }
        }
    }

    private func chamberCard(_ chamber: String, probs: ChamberControl) -> some View {
        let gopLeads = probs.gop >= probs.dem
        return VStack(alignment: .leading, spacing: 8) {
            Text("\(chamber) control")
                .font(.caption2).fontWeight(.semibold).foregroundStyle(.secondary)
                .textCase(.uppercase)

            HStack(spacing: 6) {
                Text("\(Int(probs.gop))%")
                    .font(.title2).fontWeight(.bold).monospacedDigit()
                    .foregroundColor(gopLeads ? partyColor["R"] : .secondary)
                Text("R").font(.caption).foregroundStyle(.secondary)
                Text("vs").font(.caption2).foregroundStyle(.tertiary)
                Text("\(Int(probs.dem))%")
                    .font(.title2).fontWeight(.bold).monospacedDigit()
                    .foregroundColor(!gopLeads ? partyColor["D"] : .secondary)
                Text("D").font(.caption).foregroundStyle(.secondary)
            }

            GeometryReader { geo in
                HStack(spacing: 1.5) {
                    RoundedRectangle(cornerRadius: 99)
                        .fill(partyColor["R"]!)
                        .frame(width: geo.size.width * probs.gop / 100)
                    RoundedRectangle(cornerRadius: 99)
                        .fill(partyColor["D"]!)
                        .frame(width: geo.size.width * probs.dem / 100)
                }
            }
            .frame(height: 6)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }

    // MARK: - Senate map

    private static let stateGrid: [[String]] = [
        ["", "", "", "", "", "", "", "", "", "", "AK"],
        ["", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "ME", ""],
        ["WA", "", "MT", "ND", "MN", "WI", "", "MI", "", "VT", "NH"],
        ["OR", "ID", "WY", "SD", "IA", "IL", "IN", "OH", "PA", "NY", "MA"],
        ["CA", "NV", "UT", "CO", "NE", "MO", "KY", "WV", "VA", "NJ", "CT"],
        ["", "AZ", "NM", "KS", "AR", "TN", "NC", "SC", "MD", "DE", "RI"],
        ["HI", "", "", "OK", "LA", "MS", "AL", "GA", "", "", ""],
        ["", "", "", "TX", "", "", "", "FL", "", "", ""],
    ]

    private func senateMapGrid(_ map: [String: Double]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Senate races by state")
                .font(.caption).fontWeight(.bold).textCase(.uppercase)
                .foregroundStyle(.secondary)
                .padding(.horizontal)

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 11), spacing: 2) {
                ForEach(Array(Self.stateGrid.enumerated()), id: \.offset) { _, row in
                    ForEach(Array(row.enumerated()), id: \.offset) { _, st in
                        if st.isEmpty {
                            Color.clear.frame(height: 24)
                        } else {
                            let prob = map[st]
                            Text(st)
                                .font(.system(size: 8, weight: .bold, design: .monospaced))
                                .frame(maxWidth: .infinity)
                                .frame(height: 26)
                                .background(stateColor(prob))
                                .foregroundColor(prob != nil ? .white : .secondary.opacity(0.4))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                                .shadow(color: prob != nil ? stateColor(prob).opacity(0.3) : .clear, radius: 1, x: 0, y: 1)
                        }
                    }
                }
            }
            .padding(.horizontal)

            HStack(spacing: 16) {
                legendDot(color: Color(red: 0.863, green: 0.149, blue: 0.149).opacity(0.8), label: "R likely")
                legendDot(color: Color.gray.opacity(0.35), label: "Toss-up")
                legendDot(color: Color(red: 0.145, green: 0.388, blue: 0.922).opacity(0.8), label: "D likely")
            }
            .font(.caption2).foregroundStyle(.secondary)
            .frame(maxWidth: .infinity)
            .padding(.horizontal)
        }
    }

    private func stateColor(_ prob: Double?) -> Color {
        guard let p = prob else { return Color.secondary.opacity(0.06) }
        if p >= 50 {
            let t = (p - 50) / 50
            return Color(red: 0.145, green: 0.388, blue: 0.922).opacity(0.25 + t * 0.65)
        }
        let t = (50 - p) / 50
        return Color(red: 0.863, green: 0.149, blue: 0.149).opacity(0.25 + t * 0.65)
    }

    private func legendDot(color: Color, label: String) -> some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 3).fill(color).frame(width: 12, height: 12)
            Text(label).fontWeight(.medium)
        }
    }

    // MARK: - Cross-source spotlight

    private func crossSourceSection(_ matches: [CrossSourceMatch]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "⇄", title: "Cross-source spotlight", count: nil)

            ForEach(matches.prefix(4)) { match in
                crossSourceCard(match)
            }
        }
    }

    private func crossSourceCard(_ m: CrossSourceMatch) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(m.q).font(.subheadline).fontWeight(.semibold).lineLimit(2)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    sourceChip("Kalshi", color: .green)
                    Text("\(m.kalshi, specifier: "%.1f")%")
                        .font(.title3).fontWeight(.bold).monospacedDigit()
                        .foregroundColor(m.kalshi >= m.poly ? .primary : .secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(alignment: .leading, spacing: 4) {
                    sourceChip("Polymarket", color: .blue)
                    Text("\(m.poly, specifier: "%.1f")%")
                        .font(.title3).fontWeight(.bold).monospacedDigit()
                        .foregroundColor(m.poly >= m.kalshi ? .primary : .secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if m.delta > 2 {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.left.and.right")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.orange)
                    Text("Disagree by")
                    Text("\(m.delta, specifier: "%.1f")pp")
                        .fontWeight(.bold)
                        .foregroundColor(.orange)
                }
                .font(.caption2).foregroundStyle(.secondary)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Color.orange.opacity(0.06), in: Capsule())
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
        .padding(.horizontal)
    }

    // MARK: - Generic sections

    private func themeSection(_ key: String, _ theme: PoliticsSimple?) -> some View {
        Group {
            if let theme, theme.count > 0, let markets = theme.markets, !markets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    sectionHeader(emoji: themeEmoji[key] ?? "📊", title: themeLabel[key] ?? key, count: theme.count)
                    marketGrid(markets)
                }
            }
        }
    }

    // MARK: - Shared components

    private func sectionHeader(emoji: String, title: String, count: Int?) -> some View {
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
        VStack(alignment: .leading, spacing: 8) {
            Text(m.q)
                .font(.caption).fontWeight(.semibold)
                .lineLimit(2).foregroundStyle(.primary)

            VStack(spacing: 5) {
                ForEach(Array(m.topOutcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                    HStack(spacing: 6) {
                        Text(o.name).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                        Spacer()
                        Text("\(Int(o.prob))%")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(o.prob > 50 ? .primary : .secondary)
                    }
                    .overlay(alignment: .bottom) {
                        GeometryReader { geo in
                            RoundedRectangle(cornerRadius: 2)
                                .fill(o.prob > 50
                                      ? Color.primary.opacity(0.08)
                                      : Color.secondary.opacity(0.06))
                                .frame(width: geo.size.width * o.prob / 100, height: 2)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(height: 2)
                        .offset(y: 3)
                    }
                }
            }

            if m.outcomeCount > 3 {
                Text("+\(m.outcomeCount - 3) more")
                    .font(.caption2).foregroundStyle(.tertiary)
            }

            sourceChip(m.src, color: m.src == "kalshi" ? .green : .blue)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
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

    private func footer(_ data: PoliticsResponse) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "info.circle")
                .font(.system(size: 10))
            Text("Data from Kalshi & Polymarket · Not political advice")
        }
        .font(.caption2).foregroundStyle(.tertiary)
        .padding(.horizontal)
        .padding(.bottom, 8)
    }
}
