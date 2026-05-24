import SwiftUI

// MARK: - Constants

private let politicsBlue = Color(red: 0.23, green: 0.51, blue: 0.96).opacity(0.6)

private let partyColor: [String: Color] = [
    "R": Color(red: 0.863, green: 0.149, blue: 0.149),
    "D": Color(red: 0.145, green: 0.388, blue: 0.922),
    "I": Color(red: 0.55, green: 0.35, blue: 0.78),
]

private let themeEmoji: [String: String] = [
    "presidential": "🏛", "congressional": "🏤", "gubernatorial": "🗺",
    "policy": "📜", "scotus": "⚖️", "international": "🌍", "other": "📊",
]

private let themeLabel: [String: String] = [
    "presidential": "Presidential 2028", "congressional": "Congressional",
    "gubernatorial": "Gubernatorial", "policy": "Policy & Legislation",
    "scotus": "Supreme Court", "international": "International", "other": "Other",
]

private let filterTabs = ["All", "Congress", "Courts", "Campaign", "World", "Tech", "Money"]

// MARK: - View

struct PoliticsView: View {
    @StateObject private var viewModel = PoliticsViewModel()
    @State private var selectedTab = "All"
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var contentMaxWidth: CGFloat {
        #if os(macOS)
        return 900
        #else
        return sizeClass == .regular ? 900 : .infinity
        #endif
    }

    var body: some View {
        Group {
            if viewModel.loading {
                ProgressView("Loading politics data...")
            } else if let error = viewModel.error, viewModel.data == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let data = viewModel.data {
                politicsContent(data)
            }
        }
        .navigationTitle("Politics")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "politics", type: "politics") }
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    // MARK: - Main content

    private func politicsContent(_ data: PoliticsResponse) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 32) {
                pageHeader(data)

                // Presidential hero
                if let pres = data.themes.presidential, !pres.candidates.isEmpty {
                    presidentalHeroSection(pres)
                }

                // Top stories grid (all markets flattened)
                topStoriesSection(data)

                // Congress + chamber control
                if let cong = data.themes.congressional, cong.count > 0 {
                    congressSection(cong)
                }

                // Cross-source spotlight
                if let cs = data.crossSource, !cs.isEmpty {
                    crossSourceSection(cs)
                }

                // Theme sections
                themeSection("gubernatorial", data.themes.gubernatorial)
                themeSection("policy", data.themes.policy)
                themeSection("scotus", data.themes.scotus)
                themeSection("international", data.themes.international)
                themeSection("other", data.themes.other)

                footerNote(data)
            }
            .padding(.vertical)
            .frame(maxWidth: contentMaxWidth)
            .frame(maxWidth: .infinity)
        }
    }

    // MARK: - Page header

    private func pageHeader(_ data: PoliticsResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionKicker(text: "Politics")

            Text("Today in politics")
                .font(.system(size: 32, weight: .bold))
                .tracking(-0.5)
                .foregroundStyle(DS.textPrimary)

            Text("Races, bills, and stories ranked by movement. Probability over opinion.")
                .font(.system(size: 14))
                .foregroundStyle(DS.textSecondary)

            HStack(spacing: 12) {
                Label("\(data.totalMarkets) markets", systemImage: "chart.bar")
                Label("2 sources", systemImage: "arrow.triangle.branch")
            }
            .font(.caption2)
            .foregroundStyle(DS.textMuted)
            .padding(.top, 2)
        }
        .padding(.horizontal)
    }

    // MARK: - Presidential hero

    private func presidentalHeroSection(_ pres: PoliticsPresidential) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                SectionKicker(text: "Headline race")
                Spacer()
            }
            .padding(.horizontal)

            SectionTitle(
                title: pres.headlineQ ?? "Presidential 2028",
                count: pres.count,
                action: "Detail"
            )
            .padding(.horizontal)

            // Dual-source indicator
            if pres.hasDualSource == true {
                HStack(spacing: 8) {
                    SourceChip(source: "kalshi")
                    SourceChip(source: "polymarket")
                }
                .padding(.horizontal)
            }

            // Candidate leaderboard card
            SectionCard {
                VStack(spacing: 0) {
                    ForEach(Array(pres.candidates.prefix(10).enumerated()), id: \.element.id) { idx, candidate in
                        candidateRow(candidate, rank: idx + 1)

                        if idx < min(pres.candidates.count, 10) - 1 {
                            Divider()
                                .foregroundStyle(DS.border)
                        }
                    }
                }

                if pres.candidates.count > 10 {
                    Text("+\(pres.candidates.count - 10) more candidates")
                        .font(.caption2)
                        .foregroundStyle(DS.textMuted)
                        .padding(.top, 8)
                }

                FooterNote(
                    left: "Updated \(pres.candidates.first?.change7d != nil ? "live" : "recently")",
                    right: "\(pres.count) markets"
                )
            }
            .overlay(alignment: .top) {
                Rectangle()
                    .fill(politicsBlue)
                    .frame(height: 2)
                    .clipShape(UnevenRoundedRectangle(topLeadingRadius: 16, topTrailingRadius: 16))
            }
            .padding(.horizontal)

            // Side markets
            if let side = pres.sideMarkets, !side.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Related markets")
                        .font(.system(size: 11, weight: .semibold))
                        .textCase(.uppercase)
                        .tracking(0.5)
                        .foregroundStyle(DS.textMuted)
                        .padding(.horizontal)

                    marketGrid(side)
                }
            }
        }
    }

    private func candidateRow(_ c: PoliticsCandidate, rank: Int) -> some View {
        let pColor = partyColor[c.party] ?? Color.gray
        let isLeader = rank == 1

        return HStack(spacing: 8) {
            // Rank number
            Text("\(rank)")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(DS.textMuted)
                .frame(width: 18, alignment: .trailing)

            // Party badge
            Text(c.party)
                .font(.system(size: 9, weight: .heavy))
                .foregroundColor(.white)
                .frame(width: 20, height: 20)
                .background(pColor)
                .clipShape(RoundedRectangle(cornerRadius: 4))

            // Name
            Text(c.name)
                .font(.system(size: 12.5, weight: isLeader ? .medium : .regular))
                .foregroundStyle(isLeader ? DS.textPrimary : DS.textSecondary)
                .lineLimit(1)

            Spacer()

            // Delta
            if let change = c.change7d, abs(change) > 0.1 {
                DeltaBadge(value: change)
            }

            // Probability
            Text("\(Int(c.merged.rounded()))%")
                .font(.system(size: 13, weight: .bold, design: .monospaced))
                .monospacedDigit()
                .foregroundStyle(isLeader ? DS.textPrimary : DS.textMuted)
                .frame(minWidth: 36, alignment: .trailing)
        }
        .padding(.vertical, 7)
    }

    // MARK: - Top stories (filter tabs + market grid)

    private func topStoriesSection(_ data: PoliticsResponse) -> some View {
        let allMarkets = collectAllMarkets(data)
        let filtered = filterMarkets(allMarkets, tab: selectedTab)

        return VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "Top stories", action: "See all")
                .padding(.horizontal)

            filterTabsBar

            marketGrid(filtered.isEmpty ? Array(allMarkets.prefix(6)) : Array(filtered.prefix(6)))
        }
    }

    private var filterTabsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(filterTabs, id: \.self) { tab in
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            selectedTab = tab
                        }
                    } label: {
                        Text(tab)
                            .font(.system(size: 12, weight: .medium))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .foregroundStyle(
                                selectedTab == tab ? Color.white : DS.textSecondary
                            )
                            .background(
                                selectedTab == tab
                                    ? Capsule().fill(DS.textPrimary)
                                    : Capsule().fill(DS.trackBg)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
    }

    /// Collect all markets from every theme into a flat array for filtering.
    private func collectAllMarkets(_ data: PoliticsResponse) -> [CategoryMarketRow] {
        var all: [CategoryMarketRow] = []
        if let pres = data.themes.presidential {
            if let side = pres.sideMarkets { all.append(contentsOf: side) }
        }
        if let cong = data.themes.congressional, let m = cong.markets { all.append(contentsOf: m) }
        if let g = data.themes.gubernatorial, let m = g.markets { all.append(contentsOf: m) }
        if let p = data.themes.policy, let m = p.markets { all.append(contentsOf: m) }
        if let s = data.themes.scotus, let m = s.markets { all.append(contentsOf: m) }
        if let i = data.themes.international, let m = i.markets { all.append(contentsOf: m) }
        if let o = data.themes.other, let m = o.markets { all.append(contentsOf: m) }
        return all
    }

    /// Filter markets by the selected tab keyword against question text.
    private func filterMarkets(_ markets: [CategoryMarketRow], tab: String) -> [CategoryMarketRow] {
        guard tab != "All" else { return markets }
        let keyword = tab.lowercased()
        return markets.filter { m in
            m.q.lowercased().contains(keyword)
        }
    }

    // MARK: - Congress

    private func congressSection(_ cong: PoliticsCongressional) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionKicker(text: "Congress")
                .padding(.horizontal)

            SectionTitle(title: "Congress", count: cong.count, action: "Tracker")
                .padding(.horizontal)

            // Chamber control cards
            if let cc = cong.chamberControl {
                #if os(iOS)
                let layout = UIDevice.current.userInterfaceIdiom == .pad
                    ? AnyLayout(HStackLayout(spacing: 12))
                    : AnyLayout(VStackLayout(spacing: 12))
                #else
                let layout = AnyLayout(HStackLayout(spacing: 12))
                #endif

                layout {
                    if let senate = cc.senate {
                        chamberControlCard("Senate", probs: senate)
                    }
                    if let house = cc.house {
                        chamberControlCard("House", probs: house)
                    }
                }
                .padding(.horizontal)
            }

            // Senate map
            if let map = cong.senateMap, !map.isEmpty {
                senateMapGrid(map)
            }

            // Congressional markets
            if let markets = cong.markets, !markets.isEmpty {
                marketGrid(markets)
            }
        }
    }

    private func chamberControlCard(_ chamber: String, probs: ChamberControl) -> some View {
        let gopLeads = probs.gop >= probs.dem

        return SectionCard {
            VStack(alignment: .leading, spacing: 10) {
                Text("\(chamber) control")
                    .font(.system(size: 11, weight: .semibold))
                    .textCase(.uppercase)
                    .tracking(0.5)
                    .foregroundStyle(DS.textMuted)

                HStack(spacing: 6) {
                    HStack(spacing: 4) {
                        Rectangle()
                            .fill(partyColor["R"]!)
                            .frame(width: 8, height: 8)
                            .clipShape(RoundedRectangle(cornerRadius: 2))
                        Text("GOP")
                            .font(.system(size: 11))
                            .foregroundStyle(DS.textSecondary)
                        Text("\(Int(probs.gop))%")
                            .font(.system(size: 20, weight: .bold, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(gopLeads ? DS.textPrimary : DS.textMuted)
                    }

                    Spacer()

                    HStack(spacing: 4) {
                        Text("\(Int(probs.dem))%")
                            .font(.system(size: 20, weight: .bold, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(!gopLeads ? DS.textPrimary : DS.textMuted)
                        Text("DEM")
                            .font(.system(size: 11))
                            .foregroundStyle(DS.textSecondary)
                        Rectangle()
                            .fill(partyColor["D"]!)
                            .frame(width: 8, height: 8)
                            .clipShape(RoundedRectangle(cornerRadius: 2))
                    }
                }

                // Two-segment probability bar
                GeometryReader { geo in
                    HStack(spacing: 1.5) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(partyColor["R"]!)
                            .opacity(gopLeads ? 1.0 : 0.4)
                            .frame(width: geo.size.width * probs.gop / 100)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(partyColor["D"]!)
                            .opacity(!gopLeads ? 1.0 : 0.4)
                    }
                }
                .frame(height: 6)
            }
        }
        .overlay(alignment: .top) {
            Rectangle()
                .fill(politicsBlue)
                .frame(height: 2)
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 16, topTrailingRadius: 16))
        }
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
                .font(.system(size: 11, weight: .semibold))
                .textCase(.uppercase)
                .tracking(0.5)
                .foregroundStyle(DS.textMuted)
                .padding(.horizontal)

            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 11),
                spacing: 2
            ) {
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
                                .foregroundColor(prob != nil ? .white : DS.textMuted.opacity(0.4))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                        }
                    }
                }
            }
            .padding(.horizontal)

            HStack(spacing: 16) {
                legendDot(color: partyColor["R"]!.opacity(0.8), label: "R likely")
                legendDot(color: DS.textMuted.opacity(0.35), label: "Toss-up")
                legendDot(color: partyColor["D"]!.opacity(0.8), label: "D likely")
            }
            .font(.caption2)
            .foregroundStyle(DS.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.horizontal)
        }
    }

    private func stateColor(_ prob: Double?) -> Color {
        guard let p = prob else { return DS.textMuted.opacity(0.06) }
        if p >= 50 {
            let t = (p - 50) / 50
            return partyColor["D"]!.opacity(0.25 + t * 0.65)
        }
        let t = (50 - p) / 50
        return partyColor["R"]!.opacity(0.25 + t * 0.65)
    }

    private func legendDot(color: Color, label: String) -> some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 3).fill(color).frame(width: 12, height: 12)
            Text(label).fontWeight(.medium)
        }
    }

    // MARK: - Cross-source spotlight

    private func crossSourceSection(_ matches: [CrossSourceMatch]) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionKicker(text: "Cross-source")
                .padding(.horizontal)

            SectionTitle(title: "Source disagreements", count: matches.count)
                .padding(.horizontal)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 280, maximum: 400))],
                spacing: 12
            ) {
                ForEach(matches.prefix(4)) { match in
                    crossSourceCard(match)
                }
            }
            .padding(.horizontal)
        }
    }

    private func crossSourceCard(_ m: CrossSourceMatch) -> some View {
        SectionCard {
            VStack(alignment: .leading, spacing: 10) {
                Text(m.q)
                    .font(.system(size: 14, weight: .semibold))
                    .lineLimit(2)
                    .foregroundStyle(DS.textPrimary)

                HStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        SourceChip(source: "kalshi")
                        Text("\(Int(m.kalshi.rounded()))%")
                            .font(.system(size: 20, weight: .bold, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(
                                m.kalshi >= m.poly ? DS.textPrimary : DS.textMuted
                            )
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    VStack(alignment: .leading, spacing: 4) {
                        SourceChip(source: "polymarket")
                        Text("\(Int(m.poly.rounded()))%")
                            .font(.system(size: 20, weight: .bold, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(
                                m.poly >= m.kalshi ? DS.textPrimary : DS.textMuted
                            )
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                if m.delta > 2 {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.left.and.right")
                            .font(.system(size: 9, weight: .bold))
                        Text("Disagree by")
                        Text(String(format: "%.1fpp", m.delta))
                            .fontWeight(.bold)
                    }
                    .font(.system(size: 11))
                    .foregroundStyle(DS.amber)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(DS.amber.opacity(0.08))
                    .clipShape(Capsule())
                }
            }
        }
    }

    // MARK: - Generic theme sections

    private func themeSection(_ key: String, _ theme: PoliticsSimple?) -> some View {
        Group {
            if let theme, theme.count > 0, let markets = theme.markets, !markets.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    SectionKicker(text: themeEmoji[key] ?? "📊")
                        .padding(.horizontal)

                    SectionTitle(
                        title: themeLabel[key] ?? key.capitalized,
                        count: theme.count
                    )
                    .padding(.horizontal)

                    marketGrid(markets)
                }
            }
        }
    }

    // MARK: - Shared market grid + card (using DS components)

    private func marketGrid(_ markets: [CategoryMarketRow]) -> some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 280, maximum: 400))],
            spacing: 12
        ) {
            ForEach(markets) { market in
                NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                    politicsMarketCard(market)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal)
    }

    private func politicsMarketCard(_ m: CategoryMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Question text
            Text(m.q)
                .font(.system(size: 13, weight: .semibold))
                .lineLimit(2)
                .foregroundStyle(DS.textPrimary)
                .multilineTextAlignment(.leading)

            // Outcome rows
            VStack(spacing: 5) {
                ForEach(Array(m.topOutcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                    HStack(spacing: 6) {
                        Text(o.name)
                            .font(.system(size: 11))
                            .lineLimit(1)
                            .foregroundStyle(DS.textSecondary)
                        Spacer()
                        Text("\(Int(o.prob))%")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(
                                o.prob > 50 ? DS.textPrimary : DS.textMuted
                            )
                    }
                }
            }

            // Probability bar for the lead outcome
            if let lead = m.topOutcomes.first {
                DSProbabilityBar(
                    value: lead.prob,
                    height: 5,
                    color: DS.probColor(lead.prob)
                )
            }

            // Bottom row: overflow count + source
            HStack(spacing: 6) {
                if m.outcomeCount > 3 {
                    Text("+\(m.outcomeCount - 3) more")
                        .font(.system(size: 10))
                        .foregroundStyle(DS.textMuted)
                }
                Spacer()
                SourceChip(source: m.src)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(minHeight: 110)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(DS.border, lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }

    // MARK: - Footer

    private func footerNote(_ data: PoliticsResponse) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "info.circle")
                .font(.system(size: 10))
            Text("Data from Kalshi & Polymarket. Not political advice.")
        }
        .font(.caption2)
        .foregroundStyle(DS.textMuted)
        .frame(maxWidth: .infinity)
        .padding(.horizontal)
        .padding(.bottom, 8)
    }
}
