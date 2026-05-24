import SwiftUI

// MARK: - Kind Metadata

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

private let kindAccent: [String: Color] = [
    "spotify": Color(red: 0.12, green: 0.84, blue: 0.38),
    "billboard": Color(red: 0.95, green: 0.60, blue: 0.10),
    "boxoffice": Color(red: 0.20, green: 0.60, blue: 0.95),
    "rt": Color(red: 0.90, green: 0.20, blue: 0.20),
    "reality": Color(red: 0.85, green: 0.30, blue: 0.70),
    "eurovision": Color(red: 0.65, green: 0.25, blue: 0.90),
    "multi": DS.purple,
    "binary": DS.purple,
]

// MARK: - View

struct EntertainmentView: View {
    @StateObject private var viewModel = EntertainmentViewModel()
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
                ProgressView("Loading entertainment data...")
            } else if let error = viewModel.error, viewModel.data == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let data = viewModel.data {
                entertainmentContent(data)
            }
        }
        .navigationTitle("Entertainment")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "entertainment", type: "entertainment") }
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    // MARK: - Main content

    private func entertainmentContent(_ data: EntertainmentResponse) -> some View {
        ScrollView {
            VStack(spacing: 32) {
                pageHeader(data)

                if let trending = data.trending, !trending.isEmpty {
                    trendingHeroSection(trending)
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
            .frame(maxWidth: contentMaxWidth)
            .frame(maxWidth: .infinity)
        }
    }

    // MARK: - Page Header

    private func pageHeader(_ data: EntertainmentResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Live probabilities from Kalshi and Polymarket — charts, box office, reality TV, and the moments breaking the internet.")
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)

            HStack(spacing: 12) {
                Label("\(data.totalMarkets) markets", systemImage: "chart.bar")
                Label("2 sources", systemImage: "arrow.triangle.branch")
            }
            .font(.caption2)
            .foregroundStyle(DS.textMuted)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.purple.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(DS.purple.opacity(0.15), lineWidth: 0.5)
        )
        .padding(.horizontal)
    }

    // MARK: - Trending Hero Section

    private func trendingHeroSection(_ markets: [EntMarketRow]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: "Trending now")
                SectionTitle(title: "What's hot", count: markets.count)
            }
            .padding(.horizontal)

            // Lead card (first market) + stack
            if let lead = markets.first {
                NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                    heroCard(lead, isLead: true)
                }
                .buttonStyle(.plain)
            }

            ForEach(markets.dropFirst().prefix(4)) { market in
                NavigationLink(value: Route.futuresDetail(id: market.marketId)) {
                    heroCard(market, isLead: false)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func heroCard(_ m: EntMarketRow, isLead: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                // Cover art or placeholder
                coverArt(
                    imageUrl: m.imageUrl,
                    title: m.q,
                    kind: m.kind,
                    size: isLead ? 72 : 44
                )

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        kindTag(m.kind ?? "binary")
                    }

                    Text(m.q)
                        .font(.system(size: isLead ? 18 : 14, weight: .semibold))
                        .lineHeight(multiplier: 1.25)
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(isLead ? 3 : 2)

                    if let hook = m.hook {
                        Text(hook)
                            .font(.system(size: isLead ? 13 : 12))
                            .foregroundStyle(DS.textSecondary)
                            .lineLimit(2)
                    }
                }
            }

            Spacer(minLength: 0)

            // Kind-specific rendering
            heroCardBody(m, isLead: isLead)

            // Meta row: source + resolution date
            HStack(spacing: 8) {
                SourceChip(source: m.src)
                if let resolves = m.resolutionDate {
                    Text("Resolves \(formatDate(resolves))")
                        .font(.system(size: 11))
                        .foregroundStyle(DS.textMuted)
                }
            }
        }
        .padding(isLead ? 18 : 14)
        .frame(minHeight: isLead ? 240 : 0, alignment: .top)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(DS.border, lineWidth: 0.5))
        .shadow(color: .black.opacity(0.05), radius: 8, x: 0, y: 3)
        .padding(.horizontal)
    }

    @ViewBuilder
    private func heroCardBody(_ m: EntMarketRow, isLead: Bool) -> some View {
        let outcomes = m.topOutcomes
        let kind = m.kind ?? "binary"

        if kind == "spotify" && outcomes.count >= 2 {
            spotifyHeroBody(leader: outcomes[0], runnerUp: outcomes[1], isLead: isLead)
        } else if kind == "reality" && m.outcomeCount <= 2 && outcomes.count >= 2 {
            binaryHeroBody(a: outcomes[0], b: outcomes[1], isLead: isLead)
        } else if outcomes.count > 2 {
            multiHeroBody(outcomes: outcomes, isLead: isLead)
        } else {
            // Binary yes/no
            yesNoBar(yes: m.prob, no: 100 - m.prob)
        }
    }

    private func spotifyHeroBody(leader: EntOutcome, runnerUp: EntOutcome, isLead: Bool) -> some View {
        VStack(spacing: 6) {
            // Leader
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(leader.name)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(1)
                }
                Spacer()
                HStack(spacing: 6) {
                    ProbabilityNumber(value: leader.prob, size: isLead ? 28 : 20)
                    if let delta = leader.delta24h {
                        DeltaBadge(value: delta)
                    }
                }
            }

            DSProbabilityBar(
                value: leader.prob,
                height: isLead ? 8 : 6,
                color: kindAccent["spotify"]
            )

            // Runner-up
            HStack {
                Text(runnerUp.name)
                    .font(.system(size: 11))
                    .foregroundStyle(DS.textSecondary)
                    .lineLimit(1)
                Spacer()
                HStack(spacing: 6) {
                    ProbabilityNumber(value: runnerUp.prob, size: 13)
                    if let delta = runnerUp.delta24h {
                        DeltaBadge(value: delta)
                    }
                }
            }
        }
    }

    private func binaryHeroBody(a: EntOutcome, b: EntOutcome, isLead: Bool) -> some View {
        let aLeads = a.prob >= b.prob
        return VStack(spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(a.name)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(aLeads ? DS.textPrimary : DS.textMuted)
                    ProbabilityNumber(value: a.prob, size: isLead ? 24 : 18)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(b.name)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(!aLeads ? DS.textPrimary : DS.textMuted)
                    ProbabilityNumber(value: b.prob, size: isLead ? 24 : 18)
                }
            }

            GeometryReader { geo in
                HStack(spacing: 1.5) {
                    RoundedRectangle(cornerRadius: 999)
                        .fill(aLeads ? DS.purple : DS.purple.opacity(0.35))
                        .frame(width: geo.size.width * a.prob / 100)
                    RoundedRectangle(cornerRadius: 999)
                        .fill(!aLeads ? DS.purple : DS.purple.opacity(0.35))
                        .frame(width: geo.size.width * b.prob / 100)
                }
            }
            .frame(height: 6)
        }
    }

    private func multiHeroBody(outcomes: [EntOutcome], isLead: Bool) -> some View {
        VStack(spacing: 6) {
            ForEach(Array(outcomes.prefix(isLead ? 5 : 3).enumerated()), id: \.offset) { _, o in
                HStack(spacing: 8) {
                    Text(o.name)
                        .font(.system(size: 12))
                        .foregroundStyle(DS.textSecondary)
                        .lineLimit(1)
                    DSProbabilityBar(value: o.prob, height: 4)
                    ProbabilityNumber(value: o.prob, size: 12)
                }
            }
        }
    }

    // MARK: - Music Section

    private func musicSection(_ data: EntThemeMusic) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: "Music")
                SectionTitle(title: "Charts, drops & streams", count: data.count)
            }
            .padding(.horizontal)

            // Spotify race (horse-race variant)
            if let spotify = data.spotifyRace, !spotify.isEmpty {
                spotifyRaceCard(spotify)
            }

            // Billboard watch
            if let billboard = data.billboardWatch, !billboard.isEmpty {
                marketSubsection(
                    title: "Billboard",
                    emoji: "📊",
                    markets: billboard
                )
            }

            // Album drops
            if let albums = data.albumDrops, !albums.isEmpty {
                marketSubsection(
                    title: "Album Drops",
                    emoji: "💿",
                    markets: albums
                )
            }

            // Artist streaming
            if let streaming = data.artistStreaming, !streaming.isEmpty {
                marketSubsection(
                    title: "Artist Streaming",
                    emoji: "📈",
                    markets: streaming
                )
            }

            // Side markets
            if let side = data.sideMarkets, !side.isEmpty {
                marketSubsection(
                    title: "Other Music Markets",
                    emoji: "🎵",
                    markets: side
                )
            }
        }
    }

    private func spotifyRaceCard(_ markets: [EntMarketRow]) -> some View {
        let best = markets.max(by: { $0.topOutcomes.count < $1.topOutcomes.count }) ?? markets[0]
        let spotifyGreen = kindAccent["spotify"] ?? DS.emerald

        return NavigationLink(value: Route.futuresDetail(id: best.marketId)) {
            SectionCard {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 4) {
                            Text("🎧")
                                .font(.system(size: 11))
                            Text("Spotify Chart Race")
                                .font(.system(size: 11, weight: .heavy))
                                .tracking(0.5)
                                .textCase(.uppercase)
                                .foregroundStyle(spotifyGreen)
                        }
                        Text(best.q)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(DS.textPrimary)
                            .lineLimit(2)
                    }
                    Spacer()
                }
                .padding(.bottom, 10)

                // Contenders
                VStack(spacing: 0) {
                    ForEach(Array(best.topOutcomes.prefix(6).enumerated()), id: \.offset) { idx, o in
                        HStack(spacing: 10) {
                            Text("\(idx + 1)")
                                .font(.system(size: 14, weight: .bold, design: .monospaced))
                                .foregroundStyle(idx == 0 ? spotifyGreen : DS.textMuted)
                                .frame(width: 24, alignment: .trailing)
                                .monospacedDigit()

                            VStack(alignment: .leading, spacing: 1) {
                                Text(o.name)
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(DS.textPrimary)
                                    .lineLimit(1)
                            }

                            Spacer()

                            VStack(alignment: .trailing, spacing: 2) {
                                ProbabilityNumber(value: o.prob, size: 16, color: DS.textPrimary)
                                if let delta = o.delta24h, abs(delta) > 0.1 {
                                    DeltaBadge(value: delta)
                                }
                            }
                        }
                        .padding(.vertical, 8)
                        .background(idx == 0 ? spotifyGreen.opacity(0.04) : .clear)

                        // Probability track under each contender
                        DSProbabilityBar(
                            value: o.prob,
                            height: 3,
                            color: idx == 0
                                ? spotifyGreen
                                : spotifyGreen.opacity(0.35)
                        )

                        if idx < min(best.topOutcomes.count, 6) - 1 {
                            Divider()
                                .padding(.leading, 34)
                        }
                    }
                }

                // Footer
                FooterNote(
                    left: best.src.capitalized,
                    right: best.resolutionDate.map { "Resolves \(formatDate($0))" }
                )
            }
        }
        .buttonStyle(.plain)
        .padding(.horizontal)
    }

    // MARK: - Movies & TV Section

    private func moviesTVSection(_ data: EntThemeMoviesTV) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: "Movies & TV")
                SectionTitle(title: "Scores, box office & reality", count: data.count)
            }
            .padding(.horizontal)

            // RT markets
            if let rt = data.rtMarkets, !rt.isEmpty {
                marketSubsection(title: "Rotten Tomatoes", emoji: "🍅", markets: rt)
            }

            // RT threshold groups
            if let groups = data.rtGroups, !groups.isEmpty {
                thresholdGroupSection(title: "RT Score Thresholds", groups: groups)
            }

            // Box office
            if let box = data.boxOffice, !box.isEmpty {
                marketSubsection(title: "Box Office", emoji: "🎟", markets: box)
            }

            // Box office threshold groups
            if let groups = data.boxOfficeGroups, !groups.isEmpty {
                thresholdGroupSection(title: "Box Office Ranges", groups: groups)
            }

            // Reality TV
            if let reality = data.realityTv, !reality.isEmpty {
                marketSubsection(title: "Reality TV", emoji: "📺", markets: reality)
            }

            // Side markets
            if let side = data.sideMarkets, !side.isEmpty {
                marketSubsection(title: "Other Movie & TV", emoji: "🎬", markets: side)
            }
        }
    }

    // MARK: - Cultural Moments

    private func culturalSection(_ markets: [EntMarketRow]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: "Cultural moments")
                SectionTitle(title: "Pop culture feed", count: markets.count)
            }
            .padding(.horizontal)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 260, maximum: 400))],
                spacing: 12
            ) {
                ForEach(markets.prefix(12)) { m in
                    NavigationLink(value: Route.futuresDetail(id: m.marketId)) {
                        culturalCard(m)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
    }

    private func culturalCard(_ m: EntMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Tag + resolution date
            HStack {
                kindTag(m.kind ?? "binary")
                Spacer()
                if let resolves = m.resolutionDate {
                    Text("Resolves \(formatDate(resolves))")
                        .font(.system(size: 10))
                        .foregroundStyle(DS.textMuted)
                }
            }

            // Headline
            Text(m.q)
                .font(.system(size: 14, weight: .bold))
                .lineHeight(multiplier: 1.3)
                .foregroundStyle(DS.textPrimary)
                .lineLimit(3)

            if let hook = m.hook {
                Text(hook)
                    .font(.system(size: 12))
                    .foregroundStyle(DS.textSecondary)
                    .lineLimit(2)
            }

            // Body: binary yes/no or multi-outcome
            if m.outcomeCount <= 2 {
                yesNoBar(yes: m.prob, no: 100 - m.prob)
            } else {
                VStack(spacing: 5) {
                    ForEach(Array(m.topOutcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                        HStack(spacing: 8) {
                            Text(o.name)
                                .font(.system(size: 12))
                                .foregroundStyle(DS.textSecondary)
                                .lineLimit(1)
                            DSProbabilityBar(value: o.prob, height: 4)
                            ProbabilityNumber(value: o.prob, size: 12)
                        }
                    }
                }
            }

            // Footer
            HStack(spacing: 8) {
                SourceChip(source: m.src)
                Spacer()
            }
            .padding(.top, 4)
            .overlay(alignment: .top) {
                Rectangle()
                    .fill(DS.border)
                    .frame(height: 0.5)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(DS.border, lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }

    // MARK: - Tech & Culture Section

    private func techCultureSection(_ data: EntThemeTechCulture) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                SectionKicker(text: "Tech & Culture")
                SectionTitle(title: "Platform bets & social", count: data.count)
            }
            .padding(.horizontal)

            if let markets = data.markets {
                marketGrid(Array(markets.prefix(10)))
            }
        }
    }

    // MARK: - Shared: Market Subsection

    private func marketSubsection(title: String, emoji: String, markets: [EntMarketRow]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Text(emoji).font(.system(size: 12))
                Text(title)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(DS.textSecondary)
                    .textCase(.uppercase)
                    .tracking(0.5)
            }
            .padding(.horizontal)

            marketGrid(Array(markets.prefix(8)))
        }
    }

    // MARK: - Shared: Market Grid

    private func marketGrid(_ markets: [EntMarketRow]) -> some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 260, maximum: 400))],
            spacing: 12
        ) {
            ForEach(markets) { m in
                NavigationLink(value: Route.futuresDetail(id: m.marketId)) {
                    entertainmentMarketCard(m)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal)
    }

    // MARK: - Shared: Entertainment Market Card

    private func entertainmentMarketCard(_ m: EntMarketRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Cover art + question
            HStack(alignment: .top, spacing: 10) {
                if m.imageUrl != nil {
                    coverArt(
                        imageUrl: m.imageUrl,
                        title: m.q,
                        kind: m.kind,
                        size: 44
                    )
                }

                VStack(alignment: .leading, spacing: 4) {
                    kindTag(m.kind ?? "binary")

                    Text(m.q)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                        .foregroundStyle(DS.textPrimary)
                }
            }

            Spacer(minLength: 0)

            // Probability display
            if m.outcomeCount <= 2 {
                // Binary: probability bar
                HStack(spacing: 8) {
                    DSProbabilityBar(
                        value: m.prob,
                        height: 6,
                        color: DS.probColor(m.prob)
                    )
                    ProbabilityNumber(value: m.prob, size: 14)
                }
            } else {
                // Multi-outcome: top 2
                VStack(spacing: 5) {
                    ForEach(Array(m.topOutcomes.prefix(2).enumerated()), id: \.offset) { _, o in
                        HStack(spacing: 6) {
                            Text(o.name)
                                .font(.caption2)
                                .foregroundStyle(DS.textSecondary)
                                .lineLimit(1)
                            Spacer()
                            ProbabilityNumber(value: o.prob, size: 11)
                        }
                        .overlay(alignment: .bottom) {
                            GeometryReader { geo in
                                let accent = kindAccent[m.kind ?? "binary"] ?? DS.purple
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(o.prob > 50
                                          ? accent.opacity(0.18)
                                          : DS.textMuted.opacity(0.10))
                                    .frame(
                                        width: geo.size.width * o.prob / 100,
                                        height: 2
                                    )
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(height: 2)
                            .offset(y: 3)
                        }
                    }
                }
            }

            // Delta + source
            HStack(spacing: 6) {
                if let delta = m.topOutcomes.first?.delta24h, abs(delta) >= 1 {
                    DeltaBadge(value: delta)
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
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(DS.border, lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
    }

    // MARK: - Shared: Threshold Group Section

    private func thresholdGroupSection(title: String, groups: [EntThresholdGroup]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(DS.textSecondary)
                .textCase(.uppercase)
                .tracking(0.5)
                .padding(.horizontal)

            ForEach(groups) { group in
                SectionCard {
                    HStack(spacing: 10) {
                        if let imgUrl = group.imageUrl {
                            coverArt(imageUrl: imgUrl, title: group.title, kind: nil, size: 44)
                        }
                        Text(group.title)
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(DS.textPrimary)
                        Spacer()
                    }
                    .padding(.bottom, 8)

                    VStack(spacing: 6) {
                        ForEach(Array(group.thresholds.enumerated()), id: \.offset) { _, t in
                            NavigationLink(value: Route.futuresDetail(id: t.marketId)) {
                                HStack(spacing: 8) {
                                    Text(t.label)
                                        .font(.system(size: 11))
                                        .foregroundStyle(DS.textSecondary)
                                        .frame(width: 50, alignment: .leading)
                                    DSProbabilityBar(value: t.prob, height: 4)
                                    ProbabilityNumber(value: t.prob, size: 12)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    // MARK: - Shared Atoms

    private func coverArt(imageUrl: String?, title: String, kind: String?, size: CGFloat) -> some View {
        Group {
            if let urlStr = imageUrl, let url = URL(string: urlStr) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    default:
                        coverPlaceholder(title: title, kind: kind, size: size)
                    }
                }
            } else {
                coverPlaceholder(title: title, kind: kind, size: size)
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: size > 50 ? 12 : 8))
    }

    private func coverPlaceholder(title: String, kind: String?, size: CGFloat) -> some View {
        let accent = kindAccent[kind ?? "binary"] ?? DS.purple
        let initials = String(title.prefix(2)).uppercased()
        return ZStack {
            LinearGradient(
                colors: [accent.opacity(0.6), accent.opacity(0.3)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Text(initials)
                .font(.system(size: size * 0.3, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
        }
    }

    private func kindTag(_ kind: String) -> some View {
        let accent = kindAccent[kind] ?? DS.purple
        return HStack(spacing: 3) {
            Text(kindEmoji[kind] ?? "✦")
                .font(.system(size: 10))
            Text(kindLabel[kind] ?? "Market")
        }
        .font(.system(size: 9, weight: .semibold))
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(accent.opacity(0.10))
        .foregroundStyle(accent)
        .clipShape(RoundedRectangle(cornerRadius: 5))
    }

    private func yesNoBar(yes: Double, no: Double) -> some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                Text("YES \(Int(yes))%")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(DS.emerald)
                    .frame(
                        width: max(geo.size.width * yes / 100, 44),
                        alignment: .leading
                    )
                    .padding(.leading, 8)
                    .background(DS.emerald.opacity(0.10))

                Text("NO \(Int(no))%")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(DS.textSecondary)
                    .frame(
                        width: max(geo.size.width * no / 100, 44),
                        alignment: .trailing
                    )
                    .padding(.trailing, 8)
                    .background(DS.textMuted.opacity(0.06))
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
        .font(.caption2)
        .foregroundStyle(DS.textMuted)
        .padding(.horizontal)
        .padding(.bottom, 8)
    }

    // MARK: - Helpers

    private func formatDate(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate, .withDashSeparatorInDate]
        guard let date = formatter.date(from: String(iso.prefix(10))) else { return iso }
        let df = DateFormatter()
        df.dateFormat = "MMM d"
        return df.string(from: date)
    }
}

// MARK: - Line Height Modifier

private struct LineHeightModifier: ViewModifier {
    let multiplier: CGFloat

    func body(content: Content) -> some View {
        content.lineSpacing((multiplier - 1) * 14)
    }
}

private extension View {
    func lineHeight(multiplier: CGFloat) -> some View {
        modifier(LineHeightModifier(multiplier: multiplier))
    }
}
