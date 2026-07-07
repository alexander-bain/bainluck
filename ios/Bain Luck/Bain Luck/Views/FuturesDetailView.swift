import SwiftUI

// MARK: - Category Gradients (shared with Discover card)

private let detailCategoryGradients: [String: (Color, Color)] = [
    "basketball": (Color(red: 0.49, green: 0.18, blue: 0.07), Color(red: 0.76, green: 0.25, blue: 0.05)),
    "football": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.08, green: 0.50, blue: 0.24)),
    "baseball": (Color(red: 0.50, green: 0.11, blue: 0.11), Color(red: 0.73, green: 0.11, blue: 0.11)),
    "hockey": (Color(red: 0.12, green: 0.23, blue: 0.37), Color(red: 0.15, green: 0.39, blue: 0.92)),
    "soccer": (Color(red: 0.02, green: 0.31, blue: 0.23), Color(red: 0.02, green: 0.60, blue: 0.40)),
    "golf": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.09, green: 0.40, blue: 0.20)),
    "mma": (Color(red: 0.27, green: 0.04, blue: 0.04), Color(red: 0.60, green: 0.11, blue: 0.11)),
    "economics": (Color(red: 0.18, green: 0.06, blue: 0.40), Color(red: 0.49, green: 0.23, blue: 0.93)),
    "politics": (Color(red: 0.12, green: 0.11, blue: 0.29), Color(red: 0.26, green: 0.22, blue: 0.79)),
    "tech": (Color(red: 0.03, green: 0.20, blue: 0.27), Color(red: 0.03, green: 0.57, blue: 0.70)),
    "culture": (Color(red: 0.51, green: 0.09, blue: 0.26), Color(red: 0.86, green: 0.15, blue: 0.47)),
    "weather": (Color(red: 0.05, green: 0.29, blue: 0.43), Color(red: 0.01, green: 0.52, blue: 0.78)),
    "entertainment": (Color(red: 0.44, green: 0.10, blue: 0.46), Color(red: 0.75, green: 0.15, blue: 0.83)),
    "cricket": (Color(red: 0.07, green: 0.31, blue: 0.29), Color(red: 0.08, green: 0.72, blue: 0.65)),
    "olympics": (Color(red: 0.47, green: 0.21, blue: 0.06), Color(red: 0.85, green: 0.47, blue: 0.02)),
]

private let detailDefaultGradient: (Color, Color) = (Color(red: 0.06, green: 0.09, blue: 0.16), Color(red: 0.12, green: 0.16, blue: 0.24))

private func detailCategoryEmoji(_ category: String?) -> String {
    switch category?.lowercased() {
    case "politics": return "🏛"
    case "geopolitics": return "🌍"
    case "economics": return "📈"
    case "tech": return "💻"
    case "entertainment": return "🎬"
    case "culture": return "🎭"
    case "weather": return "🌤"
    case "health": return "🏥"
    default: return "🍀"
    }
}

// MARK: - Sort

private enum FuturesSortField: String, CaseIterable {
    case probability = "Probability"
    case change = "24h Change"
    case name = "Name"
}

// MARK: - View

struct FuturesDetailView: View {
    private let marketId: Int
    @StateObject private var viewModel: FuturesDetailViewModel
    @State private var sortField: FuturesSortField = .probability
    @State private var sortAscending = false
    @State private var showAllOutcomes = false

    init(marketId: Int) {
        self.marketId = marketId
        _viewModel = StateObject(wrappedValue: FuturesDetailViewModel(marketId: marketId))
    }

    private var shareMessage: String {
        guard let market = viewModel.market else { return "Check this out on Bain Luck" }
        let leader = market.outcomes.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })
        if let leader, let prob = leader.probability {
            return "\(leader.name) at \(Int((prob * 100).rounded()))% — \(market.name) on Bain Luck"
        }
        return "\(market.name) on Bain Luck"
    }

    var body: some View {
        Group {
            if viewModel.loading {
                ProgressView()
            } else if let error = viewModel.error, viewModel.market == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let market = viewModel.market {
                ScrollView {
                    VStack(spacing: 0) {
                        // Hero section (matches Discover card visual quality)
                        heroSection(market)

                        VStack(spacing: 20) {
                            // Hook description (journalist-style blurb)
                            if let hook = market.hookDescription, !hook.isEmpty {
                                Text(hook)
                                    .font(.system(size: 15))
                                    .foregroundStyle(DS.textSecondary)
                                    .lineSpacing(4)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(16)
                                    .background(DS.cardBg)
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(DS.border, lineWidth: 0.5)
                                    )
                            }

                            // Market metadata (status, outcomes, dates, bookmakers)
                            metadataSection(market)

                            // Probability evolution chart
                            if market.outcomes.count >= 1 {
                                EvolutionChartView(
                                    marketId: marketId,
                                    hours: 168,
                                    tournamentStart: golfTournamentStart(market),
                                    tournamentEnd: golfTournamentEnd(market)
                                )
                            }

                            outcomesSection(market)
                        }
                        .padding()
                    }
                    #if os(macOS)
                    .frame(maxWidth: 1000)
                    #else
                    .frame(maxWidth: 700)
                    #endif
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .navigationTitle("Market Details")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                HStack(spacing: 4) {
                    ShareLink(
                        item: URL(string: futuresShareURL(marketId, style: .nativeCard)) ?? bainLuckFallbackURL,
                        subject: Text(viewModel.market?.name ?? "Bain Luck"),
                        message: Text(shareMessage)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                    }
                    PinButton(type: "future", id: marketId)
                }
            }
        }
        .task {
            await viewModel.load()
            if let market = viewModel.market {
                AnalyticsService.trackScreen(name: "futures_detail", type: "futures_detail")
                AnalyticsService.trackFuturesDetailView(marketId: marketId, category: market.category)
            }
        }
        .refreshable {
            await viewModel.load()
        }
    }

    // MARK: - Hero Section

    private func heroSection(_ market: FuturesMarketDetail) -> some View {
        let gradient = detailCategoryGradients[market.llmSportCategory?.lowercased() ?? ""] ?? detailDefaultGradient
        let leader = market.outcomes.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })
        let isResolved = market.status == "resolved"

        return ZStack(alignment: .bottomLeading) {
            // Background: image with gradient overlay, or category gradient
            heroBackground(market: market, gradient: gradient)
                .frame(height: 220)
                .clipped()

            // Overlay content
            VStack(alignment: .leading, spacing: 10) {
                // Top row: category pill + status badges
                HStack {
                    if let category = market.llmSportCategory {
                        Text(category.uppercased())
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())
                    }
                    Spacer()
                    if isResolved {
                        Text("RESOLVED")
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())
                    }
                    if let source = market.source {
                        Text(sourceLabel(source).uppercased())
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())
                    }
                }

                Spacer(minLength: 16)

                // Probability + movement
                if let leader, let prob = leader.probability {
                    HStack(alignment: .bottom, spacing: 10) {
                        Text("\(Int((prob * 100).rounded()))%")
                            .font(.system(size: 52, weight: .black).monospacedDigit())
                            .minimumScaleFactor(0.76)
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 3)

                        detailMovementBadge(leader.probabilityChange24h)
                            .padding(.bottom, 8)
                    }

                    Text(leader.name)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.white.opacity(0.92))
                        .lineLimit(3)
                        .minimumScaleFactor(0.92)
                        .fixedSize(horizontal: false, vertical: true)

                    if leader.isWinner == true {
                        Text("Winner")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(DS.emerald.opacity(0.6), in: Capsule())
                    }
                }

                // Market name — larger and bolder
                Text(market.name)
                    .font(.system(size: 22, weight: .bold))
                    .foregroundStyle(.white)
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)

                // Share button
                ShareLink(
                    item: URL(string: futuresShareURL(marketId, style: .nativeCard)) ?? bainLuckFallbackURL,
                    subject: Text(market.name),
                    message: Text(shareMessage)
                ) {
                    Label("Share", systemImage: "square.and.arrow.up")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(.white.opacity(0.20), in: Capsule())
                }
                .padding(.top, 2)
            }
            .padding(14)
        }
        .clipShape(RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private func heroBackground(market: FuturesMarketDetail, gradient: (Color, Color)) -> some View {
        if let imageUrlStr = market.imageUrl, let url = URL(string: imageUrlStr) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                        .overlay(
                            LinearGradient(
                                colors: [.black.opacity(0.08), .black.opacity(0.78)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                default:
                    LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                }
            }
        } else {
            LinearGradient(colors: [gradient.0, gradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                .overlay(
                    Text(detailCategoryEmoji(market.llmSportCategory))
                        .font(.system(size: 96))
                        .opacity(0.10)
                )
        }
    }

    @ViewBuilder
    private func detailMovementBadge(_ change: Double?) -> some View {
        if let m = change, abs(m) >= 0.005 {
            let up = m > 0
            HStack(spacing: 2) {
                Image(systemName: up ? "arrow.up" : "arrow.down")
                    .font(.system(size: 7, weight: .black))
                Text("\(abs(Int((m * 100).rounded())))%")
                    .font(.system(size: 10, weight: .bold).monospacedDigit())
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background((up ? DS.emerald : DS.danger).opacity(0.5))
            .clipShape(Capsule())
        }
    }

    private func sourceLabel(_ source: String) -> String {
        switch source {
        case "polymarket": return "Polymarket"
        case "kalshi": return "Kalshi"
        case "odds_api": return "Sportsbooks"
        default: return source.capitalized
        }
    }

    // MARK: - Metadata Section

    private func metadataSection(_ market: FuturesMarketDetail) -> some View {
        let isResolved = market.status == "resolved"

        return VStack(alignment: .leading, spacing: 12) {
            if let desc = market.description, !desc.isEmpty {
                Text(desc)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }

            // Info rows — structured vertical layout for clarity
            VStack(alignment: .leading, spacing: 8) {
                // Status row
                if let status = market.status {
                    HStack(spacing: 6) {
                        Image(systemName: "circle.fill")
                            .font(.system(size: 6))
                            .foregroundStyle(
                                isResolved ? DS.textMuted :
                                (status == "active" || status == "open") ? DS.emerald : DS.textMuted
                            )
                        Text("Status")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(status.capitalized)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(
                                isResolved ? DS.textMuted :
                                (status == "active" || status == "open") ? DS.emerald : DS.textSecondary
                            )
                    }
                }

                // Source row
                if let source = market.source {
                    HStack(spacing: 6) {
                        Image(systemName: "building.2")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Source")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        SourceChip(source: source)
                    }
                }

                // Outcomes count
                HStack(spacing: 6) {
                    Image(systemName: "list.bullet")
                        .font(.system(size: 9))
                        .foregroundStyle(DS.textMuted)
                        .frame(width: 6, alignment: .center)
                    Text("Outcomes")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(DS.textMuted)
                    Text("\(market.outcomes.count)")
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .foregroundStyle(DS.textSecondary)
                }

                // Commence time
                if let commence = market.commenceTime, let date = commence.asDate {
                    HStack(spacing: 6) {
                        Image(systemName: "calendar")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Starts")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(date, format: .dateTime.month(.abbreviated).day().year())
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textSecondary)
                    }
                }

                // Resolution date
                if let resolution = market.resolutionDate, let date = resolution.asDate {
                    HStack(spacing: 6) {
                        Image(systemName: "flag.checkered")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Resolves")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(date, format: .dateTime.month(.abbreviated).day().year())
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textSecondary)
                    }
                } else if let resolution = market.resolutionDate {
                    // Fallback: show the RelativeTimeText if asDate parsing fails
                    HStack(spacing: 6) {
                        Image(systemName: "flag.checkered")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Resolves")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        RelativeTimeText(dateString: resolution)
                    }
                }

                // Last updated
                if let updatedAt = market.updatedAt, let date = updatedAt.asDate {
                    HStack(spacing: 6) {
                        Image(systemName: "clock")
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 6, alignment: .center)
                        Text("Updated")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                        Text(date, format: .dateTime.month(.abbreviated).day().hour().minute())
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textMuted)
                    }
                }
            }

            // Bookmakers
            if let bookmakers = market.bookmakers, !bookmakers.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Divider()
                        .overlay(DS.border)
                    Text("Probabilities from \(bookmakers.count) sportsbook\(bookmakers.count != 1 ? "s" : "")")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(DS.textMuted)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(bookmakers, id: \.self) { bk in
                                Text(formatBookmaker(bk))
                                    .font(.system(size: 10, weight: .medium))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(DS.trackBg)
                                    .clipShape(Capsule())
                                    .foregroundStyle(DS.textSecondary)
                            }
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }

    // MARK: - Category Color

    private func categoryColor(_ market: FuturesMarketDetail) -> Color {
        switch market.llmSportCategory?.lowercased() {
        case "basketball": return DS.amber
        case "football": return DS.emerald
        case "baseball": return DS.danger
        case "hockey": return DS.blue
        case "soccer": return DS.emerald
        case "golf": return DS.emerald
        case "tennis": return DS.amber
        case "mma", "boxing": return DS.danger
        case "politics": return DS.purple
        case "entertainment": return Color(red: 0.75, green: 0.15, blue: 0.83)
        case "crypto": return DS.amber
        default: return DS.blue
        }
    }

    // MARK: - Outcomes

    private func outcomesSection(_ market: FuturesMarketDetail) -> some View {
        let color = categoryColor(market)
        let sorted = sortedOutcomes(market.outcomes)
        let displayed = showAllOutcomes ? sorted : Array(sorted.prefix(25))
        let hasMore = sorted.count > 25

        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "chart.bar.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(DS.textMuted)
                Text("All Outcomes")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(DS.textPrimary)
                Spacer()
                if hasMore {
                    Button(showAllOutcomes ? "Show less" : "Show all \(sorted.count)") {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showAllOutcomes.toggle()
                        }
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(DS.emerald)
                }
            }

            // Sort controls
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(FuturesSortField.allCases, id: \.self) { field in
                        sortChip(field)
                    }
                }
            }

            ForEach(Array(displayed.enumerated()), id: \.element.id) { index, outcome in
                outcomeRow(outcome, rank: index + 1, color: color, leaderId: sorted.first?.id)
                if index < displayed.count - 1 {
                    Divider()
                        .overlay(DS.border)
                }
            }

            if hasMore && !showAllOutcomes {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showAllOutcomes = true
                    }
                } label: {
                    Text("Show \(sorted.count - 25) more outcomes")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(DS.textSecondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                }
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(DS.border, lineWidth: 1)
                )
            }
        }
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }

    private func sortChip(_ field: FuturesSortField) -> some View {
        let isActive = sortField == field
        return Button {
            if sortField == field {
                sortAscending.toggle()
            } else {
                sortField = field
                sortAscending = field == .name
            }
        } label: {
            HStack(spacing: 3) {
                Text(field.rawValue)
                    .font(.system(size: 11, weight: .medium))
                if isActive {
                    Image(systemName: sortAscending ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8, weight: .bold))
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isActive ? DS.emerald.opacity(0.12) : DS.trackBg)
            .foregroundStyle(isActive ? DS.emerald : DS.textSecondary)
            .clipShape(Capsule())
        }
    }

    private func sortedOutcomes(_ outcomes: [FuturesOutcome]) -> [FuturesOutcome] {
        outcomes.sorted { a, b in
            let comparison: ComparisonResult
            switch sortField {
            case .probability:
                comparison = compareOptionalDoubles(a.probability, b.probability)
            case .change:
                comparison = compareOptionalDoubles(a.probabilityChange24h, b.probabilityChange24h)
            case .name:
                comparison = a.name.localizedCompare(b.name)
            }

            if comparison != .orderedSame {
                return sortAscending ? comparison == .orderedAscending : comparison == .orderedDescending
            }

            let nameComparison = a.name.localizedCompare(b.name)
            if nameComparison != .orderedSame {
                return nameComparison == .orderedAscending
            }
            return a.id < b.id
        }
    }

    private func compareOptionalDoubles(_ lhs: Double?, _ rhs: Double?) -> ComparisonResult {
        switch (lhs, rhs) {
        case let (lhs?, rhs?):
            if lhs < rhs { return .orderedAscending }
            if lhs > rhs { return .orderedDescending }
            return .orderedSame
        case (.some, .none):
            return .orderedDescending
        case (.none, .some):
            return .orderedAscending
        case (.none, .none):
            return .orderedSame
        }
    }

    private func outcomeRow(_ outcome: FuturesOutcome, rank: Int, color: Color, leaderId: Int?) -> some View {
        let isLeader = outcome.id == leaderId
        let probPct = (outcome.probability ?? 0) * 100

        return VStack(spacing: 6) {
            HStack(alignment: .top) {
                // Rank number
                Text("#\(rank)")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundStyle(isLeader ? DS.amber : DS.textMuted)
                    .frame(width: 30, alignment: .leading)

                // Rank change indicator
                if let rankChange = outcome.rankChange24h, rankChange != 0 {
                    HStack(spacing: 1) {
                        Image(systemName: rankChange < 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 7))
                        Text("\(abs(rankChange))")
                            .font(.system(size: 9, weight: .medium))
                    }
                    .foregroundStyle(rankChange < 0 ? DS.emerald : DS.danger)
                    .frame(width: 24, alignment: .leading)
                } else {
                    Spacer().frame(width: 24)
                }

                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(outcome.name)
                            .font(.system(size: 15, weight: isLeader ? .semibold : .medium))
                            .foregroundStyle(DS.textPrimary)
                        if outcome.isWinner == true {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(DS.emerald)
                        }
                    }

                    HStack(spacing: 8) {
                        // L2-48: American moneyline removed — probability only
                        // (no-odds thesis: "60% vs 40%", never "-150/+130").
                        // 24h movement via DeltaBadge
                        if let change = outcome.probabilityChange24h, abs(change) >= 0.005 {
                            DeltaBadge(value: change * 100)
                        }
                        if let opening = outcome.openingProbability, let current = outcome.probability {
                            let diff = current - opening
                            if abs(diff) >= 0.005 {
                                Text("from \(formatProbability(opening))")
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(DS.textMuted)
                            }
                        }
                    }
                }

                Spacer()

                // Lead probability via ProbabilityNumber
                if let prob = outcome.probability {
                    if isLeader {
                        ProbabilityNumber(value: prob * 100, size: 28, color: DS.probColor(prob * 100))
                    } else {
                        Text(formatProbability(prob))
                            .font(.system(size: 18, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.probColor(probPct))
                    }
                }
            }

            // Probability bar via DSProbabilityBar
            if outcome.probability != nil {
                DSProbabilityBar(
                    value: probPct,
                    maxValue: 100,
                    height: 5,
                    color: isLeader ? color : color.opacity(0.6)
                )
            }
        }
        .padding(.vertical, 6)
    }

    // MARK: - Golf Tournament Dates

    /// Return commence_time as tournament start for golf markets (used for round markers).
    private func golfTournamentStart(_ market: FuturesMarketDetail) -> String? {
        guard market.llmSportCategory?.lowercased() == "golf" else { return nil }
        return market.commenceTime
    }

    /// Derive tournament end from commence_time + 4 days for golf.
    /// Returns nil for non-golf markets.
    private func golfTournamentEnd(_ market: FuturesMarketDetail) -> String? {
        guard market.llmSportCategory?.lowercased() == "golf",
              let startStr = market.commenceTime,
              let startDate = startStr.asDate else { return nil }
        let endDate = Calendar.current.date(byAdding: .day, value: 4, to: startDate)
        return endDate?.ISO8601Format()
    }

    // MARK: - Bookmaker Formatting

    private func formatBookmaker(_ key: String) -> String {
        let names: [String: String] = [
            "draftkings": "DraftKings",
            "fanduel": "FanDuel",
            "betmgm": "BetMGM",
            "caesars": "Caesars",
            "pointsbet": "PointsBet",
            "betrivers": "BetRivers",
            "bovada": "Bovada",
            "pinnacle": "Pinnacle",
            "espnbet": "ESPN BET",
            "betonlineag": "BetOnline",
            "superbook": "SuperBook",
            "williamhill_us": "Caesars",
            "fliff": "Fliff",
            "hardrockbet": "Hard Rock",
        ]
        return names[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
