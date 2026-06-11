import SwiftUI

// MARK: - Constants

private let econGreen = DS.emerald
private let econGreenDark = DS.emeraldDark
private let tickerDark = Color(red: 0.06, green: 0.09, blue: 0.16)   // #0F172A
private let tickerMuted = Color(red: 0.58, green: 0.64, blue: 0.72)  // #94A3B8

private let themeKicker: [String: String] = [
    "fed_side": "FEDERAL RESERVE",
    "inflation": "INFLATION & CONSUMER PRICES",
    "jobs": "JOBS & EMPLOYMENT",
    "recession": "GDP & RECESSION",
    "markets": "MARKETS & INDICES",
    "energy": "ENERGY & COMMODITIES",
    "housing": "HOUSING & MORTGAGES",
    "trade": "TRADE & TARIFFS",
    "government": "GOVERNMENT & FISCAL",
]

private let themeTitle: [String: String] = [
    "fed_side": "Fed Side Markets",
    "inflation": "Related Inflation Markets",
    "jobs": "Monthly reports. Weekly claims.",
    "recession": "The big macro question",
    "markets": "Daily close. Weekly range.",
    "energy": "Gas, oil, and the price at the pump",
    "housing": "Rates, prices, and the American dream",
    "trade": "The economic story of 2026",
    "government": "Shutdowns, debt, DOGE",
]

// MARK: - Theme Info

private struct ThemeInfo: Identifiable {
    let id: String
    let kicker: String
    let title: String
    let count: Int
    let markets: [EconomicsMarket]
}

// MARK: - View

struct EconomicsView: View {
    @StateObject private var viewModel = EconomicsViewModel()
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
                ProgressView("Loading economics data...")
            } else if let error = viewModel.error, viewModel.data == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let data = viewModel.data {
                economicsContent(data)
            }
        }
        .navigationTitle("Economics")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "economics", type: "economics") }
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    // MARK: - Main Content

    private func economicsContent(_ data: EconomicsResponse) -> some View {
        let themes = buildThemes(data.themes)
        return ScrollView {
            VStack(spacing: 32) {
                heroSection(data)

                if let fed = data.themes.fed, let meetings = fed.fomcMeetings, !meetings.isEmpty {
                    fedSection(meetings, sideMarkets: fed.sideMarkets ?? [])
                }

                if let inf = data.themes.inflation, let cpi = inf.cpiReleases, !cpi.isEmpty {
                    cpiSection(cpi, sideMarkets: inf.sideMarkets ?? [])
                }

                ForEach(themes) { theme in
                    themeSection(theme)
                }

                footerSection(data)
            }
            .padding(.vertical)
            .frame(maxWidth: contentMaxWidth)
            .frame(maxWidth: .infinity)
        }
        .background(DS.surface)
    }

    // MARK: - Hero Section

    private func heroSection(_ data: EconomicsResponse) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            // Live pill + count
            HStack(spacing: 10) {
                HStack(spacing: 7) {
                    Circle()
                        .fill(DS.kalshiGreen)
                        .frame(width: 8, height: 8)
                    Text("Economics markets")
                        .font(.system(size: 12, weight: .semibold))
                    Text("Live")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundStyle(Color(red: 0.02, green: 0.47, blue: 0.34))
                .padding(.horizontal, 11)
                .padding(.vertical, 4)
                .background(Color(red: 0.93, green: 0.99, blue: 0.96))
                .clipShape(Capsule())

                Text("\(data.totalMarkets) active")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(DS.textMuted)
            }
            .padding(.horizontal)

            // Headline
            VStack(alignment: .leading, spacing: 6) {
                (Text("What do markets think about ")
                    .foregroundStyle(DS.textPrimary) +
                Text("the economy")
                    .foregroundStyle(econGreen) +
                Text("?")
                    .foregroundStyle(DS.textPrimary))
                    .font(.system(size: 28, weight: .semibold))
                    .tracking(-0.5)
                    .lineSpacing(2)

                Text("Economic prediction markets translated into plain probabilities. Rates, inflation, jobs, GDP -- no odds, just percentages.")
                    .font(.system(size: 15))
                    .foregroundStyle(DS.textSecondary)
                    .lineSpacing(3)
            }
            .padding(.horizontal)

            // Ticker strip
            tickerStrip(data)
        }
    }

    private func tickerStrip(_ data: EconomicsResponse) -> some View {
        // Gather highlight markets from various themes for the ticker
        let tickerItems = gatherTickerItems(data)

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 0) {
                ForEach(Array(tickerItems.enumerated()), id: \.offset) { _, item in
                    HStack(spacing: 10) {
                        Circle()
                            .fill(item.src == "kalshi" ? DS.kalshiGreen : DS.blue)
                            .frame(width: 5, height: 5)

                        Text(item.q)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(tickerMuted)
                            .textCase(.uppercase)
                            .tracking(0.5)
                            .lineLimit(1)

                        Text(item.prob.truncatingRemainder(dividingBy: 1) == 0
                            ? "\(Int(item.prob))%"
                            : String(format: "%.1f%%", item.prob))
                            .font(.system(size: 16, weight: .bold, design: .monospaced))
                            .foregroundStyle(.white)

                        if let delta = item.delta, abs(delta) >= 0.5 {
                            HStack(spacing: 2) {
                                Text(delta > 0 ? "^" : "v")
                                    .font(.system(size: 8, weight: .bold))
                                Text(String(format: "%.1f", abs(delta)) + "pp")
                                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                            }
                            .foregroundStyle(delta > 0
                                ? Color(red: 0.29, green: 0.87, blue: 0.50)
                                : Color(red: 0.97, green: 0.44, blue: 0.44))
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 14)
                    .overlay(alignment: .trailing) {
                        Rectangle()
                            .fill(Color.white.opacity(0.08))
                            .frame(width: 1)
                    }
                }
            }
        }
        .background(tickerDark)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(alignment: .topTrailing) {
            HStack(spacing: 5) {
                Circle()
                    .fill(DS.kalshiGreen)
                    .frame(width: 5, height: 5)
                Text("LIVE")
                    .font(.system(size: 9, weight: .heavy))
                    .tracking(1)
                    .foregroundStyle(DS.kalshiGreen)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .padding(.horizontal)
    }

    private func gatherTickerItems(_ data: EconomicsResponse) -> [EconomicsMarket] {
        var items: [EconomicsMarket] = []
        // Grab a few from each theme for the ticker
        let themeArrays: [[EconomicsMarket]?] = [
            data.themes.fed?.sideMarkets,
            data.themes.inflation?.sideMarkets,
            data.themes.jobs?.markets,
            data.themes.recession?.markets ?? data.themes.recession?.sideMarkets,
            data.themes.markets?.markets ?? data.themes.markets?.sideMarkets,
            data.themes.energy?.markets ?? data.themes.energy?.sideMarkets,
        ]
        for arr in themeArrays {
            if let arr, let first = arr.first {
                items.append(first)
            }
        }
        // Pad to at least 4 if we can
        if items.count < 4 {
            if let extra = data.themes.trade?.markets {
                items.append(contentsOf: extra.prefix(2))
            }
        }
        return items
    }

    // MARK: - Fed Section

    private func fedSection(_ meetings: [FOMCMeeting], sideMarkets: [EconomicsMarket]) -> some View {
        let upcoming = meetings.filter { !$0.resolved }
        return VStack(alignment: .leading, spacing: 16) {
            // Section header
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: "Federal Reserve")
                SectionTitle(
                    title: "Rate Path",
                    count: upcoming.count
                )
                Text("Market-implied probability at every FOMC meeting")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(DS.textMuted)
            }
            .padding(.horizontal)

            // FOMC meeting cards — horizontal scroll
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(upcoming) { meeting in
                        fomcCard(meeting)
                    }
                }
                .padding(.horizontal)
            }

            // Side markets in a grid below
            if !sideMarkets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Related Fed Markets")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(DS.textSecondary)
                        .padding(.horizontal)

                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 260, maximum: 400))],
                        spacing: 12
                    ) {
                        ForEach(sideMarkets.prefix(6)) { market in
                            NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                                DSMarketCard(
                                    question: market.q,
                                    probability: market.prob,
                                    source: market.src,
                                    delta: market.delta
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    private func fomcCard(_ meeting: FOMCMeeting) -> some View {
        SectionCard {
            // Header
            HStack {
                Text(meeting.mo)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(DS.textPrimary)
                Spacer()
                Text("FOMC")
                    .font(.system(size: 9, weight: .heavy))
                    .tracking(0.5)
                    .foregroundStyle(econGreenDark)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(econGreen.opacity(0.10))
                    .clipShape(Capsule())
            }

            Text(meeting.date)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(DS.textMuted)
                .padding(.top, 2)

            Divider()
                .padding(.vertical, 6)

            // Rate distribution bars
            VStack(spacing: 6) {
                ForEach(Array(meeting.dist.prefix(5).enumerated()), id: \.offset) { _, pair in
                    if pair.count >= 2,
                       let prob = pair[0].doubleValue,
                       let rate = pair[1].stringValue,
                       prob >= 1 {
                        fomcDistRow(rate: rate, prob: prob)
                    }
                }
            }

            FooterNote(
                left: "Resolves post-FOMC",
                right: "Kalshi"
            )
        }
        #if os(macOS)
        .frame(width: 300)
        #else
        .frame(width: 260)
        #endif
    }

    private func fomcDistRow(rate: String, prob: Double) -> some View {
        HStack(spacing: 8) {
            Text(rate)
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(DS.textSecondary)
                .frame(width: 65, alignment: .leading)

            DSProbabilityBar(
                value: prob,
                height: 10,
                color: prob > 50 ? econGreen : DS.purple.opacity(0.5)
            )

            Text("\(Int(prob))%")
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundStyle(prob > 50 ? econGreen : DS.textMuted)
                .frame(width: 36, alignment: .trailing)
        }
    }

    // MARK: - CPI / Inflation Section

    private func cpiSection(_ releases: [CPIRelease], sideMarkets: [EconomicsMarket]) -> some View {
        let upcoming = releases.filter { $0.upcoming == true }
        return Group {
            if !upcoming.isEmpty {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        SectionKicker(text: "Inflation & Consumer Prices")
                        SectionTitle(
                            title: "CPI Releases",
                            count: upcoming.count
                        )
                        Text("Modal outcome per month from Kalshi bracket markets")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(DS.textMuted)
                    }
                    .padding(.horizontal)

                    // CPI release cards — horizontal scroll
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 12) {
                            ForEach(upcoming) { release in
                                cpiCard(release)
                            }
                        }
                        .padding(.horizontal)
                    }

                    // Side markets
                    if !sideMarkets.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Related Inflation Markets")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(DS.textSecondary)
                                .padding(.horizontal)

                            LazyVGrid(
                                columns: [GridItem(.adaptive(minimum: 260, maximum: 400))],
                                spacing: 12
                            ) {
                                ForEach(sideMarkets.prefix(6)) { market in
                                    NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                                        DSMarketCard(
                                            question: market.q,
                                            probability: market.prob,
                                            source: market.src,
                                            delta: market.delta
                                        )
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.horizontal)
                        }
                    }
                }
            }
        }
    }

    private func cpiCard(_ release: CPIRelease) -> some View {
        SectionCard {
            // Header
            HStack {
                Text(release.mo)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(DS.textPrimary)
                Spacer()
                if release.upcoming == true {
                    Text("NEXT")
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(0.5)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(DS.kalshiGreen)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
                Text("CPI")
                    .font(.system(size: 9, weight: .heavy))
                    .tracking(0.5)
                    .foregroundStyle(DS.amber)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(DS.amber.opacity(0.10))
                    .clipShape(Capsule())
            }

            // Peak bucket label
            if let brackets = release.brackets,
               let peakIdx = release.peakIs,
               peakIdx < brackets.count,
               let label = brackets[peakIdx][1].stringValue,
               let prob = brackets[peakIdx][0].doubleValue {
                HStack(spacing: 4) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 9))
                        .foregroundStyle(DS.amber)
                    Text("Most likely: \(label)")
                        .font(.system(size: 11))
                        .foregroundStyle(DS.textSecondary)
                    Spacer()
                    ProbabilityNumber(value: prob, size: 22)
                }
                .padding(.top, 4)
            }

            // Mini histogram bars
            if let brackets = release.brackets, !brackets.isEmpty {
                Divider()
                    .padding(.vertical, 4)

                cpiHistogram(brackets: brackets, peakIdx: release.peakIs)
            }

            FooterNote(
                left: "Resolves on release day",
                right: "Kalshi"
            )
        }
        #if os(macOS)
        .frame(width: 300)
        #else
        .frame(width: 260)
        #endif
    }

    private func cpiHistogram(brackets: [[WeatherAnyCodable]], peakIdx: Int?) -> some View {
        let maxProb = brackets.compactMap { $0.first?.doubleValue }.max() ?? 1

        return VStack(spacing: 4) {
            // Bars
            HStack(alignment: .bottom, spacing: 3) {
                ForEach(Array(brackets.enumerated()), id: \.offset) { idx, pair in
                    if let prob = pair.first?.doubleValue {
                        let isPeak = idx == peakIdx
                        let barHeight = maxProb > 0 ? max(2, CGFloat(prob / maxProb) * 50) : 2

                        VStack(spacing: 2) {
                            if isPeak {
                                Text("\(Int(prob))%")
                                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                                    .foregroundStyle(DS.textPrimary)
                            }

                            RoundedRectangle(cornerRadius: 2)
                                .fill(DS.amber.opacity(isPeak ? 1 : 0.3 + (prob / maxProb) * 0.4))
                                .frame(height: barHeight)
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
            }
            .frame(height: 70)

            // Labels
            HStack(spacing: 3) {
                ForEach(Array(brackets.enumerated()), id: \.offset) { _, pair in
                    if let label = pair.count > 1 ? pair[1].stringValue : nil {
                        Text(label)
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundStyle(DS.textMuted)
                            .frame(maxWidth: .infinity)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                    }
                }
            }
        }
    }

    // MARK: - Generic Theme Sections

    private func buildThemes(_ themes: EconomicsThemes) -> [ThemeInfo] {
        var result: [ThemeInfo] = []
        if let t = themes.jobs {
            result.append(ThemeInfo(
                id: "jobs",
                kicker: themeKicker["jobs"] ?? "JOBS",
                title: themeTitle["jobs"] ?? "Jobs",
                count: t.count,
                markets: t.markets ?? []
            ))
        }
        if let t = themes.inflation {
            result.append(ThemeInfo(
                id: "inflation",
                kicker: themeKicker["inflation"] ?? "INFLATION",
                title: themeTitle["inflation"] ?? "Inflation",
                count: t.sideMarkets?.count ?? t.count,
                markets: t.sideMarkets ?? []
            ))
        }
        if let t = themes.recession {
            result.append(ThemeInfo(
                id: "recession",
                kicker: themeKicker["recession"] ?? "RECESSION",
                title: themeTitle["recession"] ?? "Recession",
                count: t.count,
                markets: t.markets ?? t.sideMarkets ?? []
            ))
        }
        if let t = themes.markets {
            result.append(ThemeInfo(
                id: "markets",
                kicker: themeKicker["markets"] ?? "MARKETS",
                title: themeTitle["markets"] ?? "Markets",
                count: t.count,
                markets: t.markets ?? t.sideMarkets ?? []
            ))
        }
        if let t = themes.energy {
            result.append(ThemeInfo(
                id: "energy",
                kicker: themeKicker["energy"] ?? "ENERGY",
                title: themeTitle["energy"] ?? "Energy",
                count: t.count,
                markets: t.markets ?? t.sideMarkets ?? []
            ))
        }
        if let t = themes.housing {
            result.append(ThemeInfo(
                id: "housing",
                kicker: themeKicker["housing"] ?? "HOUSING",
                title: themeTitle["housing"] ?? "Housing",
                count: t.count,
                markets: t.markets ?? []
            ))
        }
        if let t = themes.trade {
            result.append(ThemeInfo(
                id: "trade",
                kicker: themeKicker["trade"] ?? "TRADE",
                title: themeTitle["trade"] ?? "Trade",
                count: t.count,
                markets: t.markets ?? []
            ))
        }
        if let t = themes.government {
            result.append(ThemeInfo(
                id: "government",
                kicker: themeKicker["government"] ?? "GOVERNMENT",
                title: themeTitle["government"] ?? "Government",
                count: t.count,
                markets: t.markets ?? []
            ))
        }
        if let t = themes.fed {
            result.append(ThemeInfo(
                id: "fed_side",
                kicker: themeKicker["fed_side"] ?? "FED",
                title: themeTitle["fed_side"] ?? "Fed Side Markets",
                count: t.sideMarkets?.count ?? 0,
                markets: t.sideMarkets ?? []
            ))
        }
        return result.filter { !$0.markets.isEmpty }
    }

    private func themeSection(_ theme: ThemeInfo) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: theme.kicker)
                SectionTitle(title: theme.title, count: theme.count)
            }
            .padding(.horizontal)

            #if os(macOS)
            let limit = 12
            #else
            let limit = 8
            #endif

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 260, maximum: 400))],
                spacing: 12
            ) {
                ForEach(Array(theme.markets.prefix(limit))) { market in
                    NavigationLink(value: Route.futuresDetail(id: market.marketId ?? 0)) {
                        DSMarketCard(
                            question: market.q,
                            probability: market.prob,
                            source: market.src,
                            delta: market.delta
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)

            if theme.markets.count > limit {
                Text("+\(theme.markets.count - limit) more")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(DS.textMuted)
                    .padding(.horizontal)
            }
        }
    }

    // MARK: - Footer

    private func footerSection(_ data: EconomicsResponse) -> some View {
        VStack(spacing: 0) {
            Rectangle()
                .fill(DS.border)
                .frame(height: 0.5)
                .padding(.horizontal)

            HStack(spacing: 6) {
                Image(systemName: "info.circle")
                    .font(.system(size: 10))
                Text("Prediction market data")
                Spacer()
                Text("Not financial advice")
            }
            .font(.system(size: 11))
            .foregroundStyle(DS.textMuted)
            .padding(.horizontal)
            .padding(.top, 14)
            .padding(.bottom, 8)
        }
    }
}
