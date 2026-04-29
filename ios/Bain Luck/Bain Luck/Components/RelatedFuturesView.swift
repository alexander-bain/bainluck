import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "relatedFutures")

// MARK: - ViewModel

final class RelatedFuturesViewModel: ObservableObject {
    @Published var relatedFutures: RelatedFuturesResponse?
    @Published var loading = true
    @Published var error: String?

    let eventId: Int
    private var refreshTimer: Timer?

    init(eventId: Int, preloaded: RelatedFuturesResponse? = nil) {
        self.eventId = eventId
        if let preloaded {
            self.relatedFutures = preloaded
            self.loading = false
        }
    }

    var isLive: Bool {
        relatedFutures?.eventStatus == "live"
    }

    @MainActor
    func load() async {
        guard relatedFutures == nil else {
            // Already have data (preloaded), just configure refresh
            configureAutoRefresh()
            return
        }
        loading = true
        do {
            relatedFutures = try await APIClient.shared.fetchRelatedFutures(eventId: eventId)
            error = nil
            loading = false
            configureAutoRefresh()
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load related futures for event \(self.eventId): \(error)")
        }
    }

    @MainActor
    func retryLoad() async {
        error = nil
        loading = true
        do {
            relatedFutures = try await APIClient.shared.fetchRelatedFutures(eventId: eventId)
            error = nil
            loading = false
            configureAutoRefresh()
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to retry related futures for event \(self.eventId): \(error)")
        }
    }

    @MainActor
    func refresh() async {
        do {
            relatedFutures = try await APIClient.shared.fetchRelatedFutures(eventId: eventId)
            error = nil
        } catch {
            logger.error("Failed to refresh related futures for event \(self.eventId): \(error)")
        }
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard isLive else { return }
        // Refresh every 60 seconds during live games to update box scores
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.refresh()
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}

// MARK: - Category-to-Tier Mapping (backend display_category → render tier)

private let categoryToTier: [String: Int] = [
    "playoff_path": 1,
    "conference": 2,
    "award": 3,
    "season_stat": 4,
    "game_prop": 5,
    "trade": 7,
    "novelty": 8,
    "ncaa": 4,
    "other": 5,
]

private func effectiveTier(_ f: RelatedFuture) -> Int {
    // Use backend display_category (always provided by the API)
    if let cat = f.displayCategory, let tier = categoryToTier[cat] {
        return tier
    }
    // Fallback to market_tier for edge cases
    if let tier = f.marketTier, tier >= 1, tier <= 5 { return tier }
    return 5
}

private func shortAwardLabel(_ marketName: String, cleanLabel: String? = nil) -> String {
    // Use backend clean label if available
    if let clean = cleanLabel, !clean.isEmpty {
        return clean
    }
    let n = marketName
    if n.range(of: "\\bmvp\\b|most\\s+valuable", options: [.regularExpression, .caseInsensitive]) != nil { return "MVP" }
    if n.range(of: "\\brookie\\s+of\\s+the\\s+year", options: [.regularExpression, .caseInsensitive]) != nil { return "Rookie of the Year" }
    if n.range(of: "\\bdefensive\\s+player", options: [.regularExpression, .caseInsensitive]) != nil { return "DPOY" }
    if n.range(of: "\\bmost\\s+improved", options: [.regularExpression, .caseInsensitive]) != nil { return "Most Improved" }
    if n.range(of: "\\bsixth\\s+man|\\b6th\\s+man", options: [.regularExpression, .caseInsensitive]) != nil { return "6th Man" }
    if n.range(of: "cy\\s*young", options: [.regularExpression, .caseInsensitive]) != nil { return "Cy Young" }
    if n.range(of: "\\bgolden\\s+boot", options: [.regularExpression, .caseInsensitive]) != nil { return "Golden Boot" }
    if n.range(of: "\\bgolden\\s+glove", options: [.regularExpression, .caseInsensitive]) != nil { return "Golden Glove" }
    if n.range(of: "\\bheisman", options: [.regularExpression, .caseInsensitive]) != nil { return "Heisman" }
    if n.range(of: "\\bcoach\\s+of\\s+the\\s+year", options: [.regularExpression, .caseInsensitive]) != nil { return "Coach of the Year" }
    if n.range(of: "rebounds?\\s*per\\s*game\\s*leader", options: [.regularExpression, .caseInsensitive]) != nil { return "Rebounds Leader" }
    if n.range(of: "assists?\\s*per\\s*game\\s*leader", options: [.regularExpression, .caseInsensitive]) != nil { return "Assists Leader" }
    if n.range(of: "points?\\s*per\\s*game\\s*leader|\\bscoring\\s+(leader|title|champion)", options: [.regularExpression, .caseInsensitive]) != nil { return "Scoring Leader" }
    if n.range(of: "\\bhome\\s+run\\s+(leader|king)", options: [.regularExpression, .caseInsensitive]) != nil { return "HR Leader" }
    // Strip league prefix
    let stripped = n.replacingOccurrences(of: "^(NBA|NFL|NHL|MLB|MLS|WNBA|NCAAB|NCAAF)\\s+", with: "", options: .regularExpression)
    return stripped
}

private func extractOpponent(_ marketName: String, teamName: String) -> String {
    var result = marketName
        .replacingOccurrences(of: " - More Markets", with: "", options: .caseInsensitive)
        .replacingOccurrences(of: " - Moneyline", with: "", options: .caseInsensitive)
    let teamWords = teamName.split(separator: " ")
    let shortName = teamWords.last.map(String.init) ?? teamName
    for name in [teamName, shortName] {
        let escaped = NSRegularExpression.escapedPattern(for: name)
        for sep in ["vs\\.?", "\u{2013}", "at"] {
            result = result.replacingOccurrences(of: "^\(escaped)\\s+\(sep)\\s+", with: "", options: .regularExpression)
            result = result.replacingOccurrences(of: "\\s+\(sep)\\s+\(escaped)$", with: "", options: .regularExpression)
        }
    }
    return result.trimmingCharacters(in: .whitespaces)
}

private func extractStatCategory(_ marketName: String) -> String {
    if let range = marketName.range(of: ":\\s*(.+?)$", options: .regularExpression) {
        let match = marketName[range]
        let cleaned = match.replacingOccurrences(of: "^:\\s*", with: "", options: .regularExpression)
        return cleaned.lowercased()
    }
    return "other"
}

private struct StatCategoryConfig {
    let emoji: String
    let label: String
}

private let statCategories: [String: StatCategoryConfig] = [
    "points": .init(emoji: "\u{1F3C0}", label: "Points"),
    "assists": .init(emoji: "\u{1F91D}", label: "Assists"),
    "rebounds": .init(emoji: "\u{1F4AA}", label: "Rebounds"),
    "steals": .init(emoji: "\u{1F590}", label: "Steals"),
    "blocks": .init(emoji: "\u{1F6AB}", label: "Blocks"),
    "three pointers": .init(emoji: "\u{1F3AF}", label: "3-Pointers"),
    "turnovers": .init(emoji: "\u{1F504}", label: "Turnovers"),
    "strikeouts": .init(emoji: "\u{26BE}", label: "Strikeouts"),
    "goals": .init(emoji: "\u{26BD}", label: "Goals"),
    "touchdowns": .init(emoji: "\u{1F3C8}", label: "TDs"),
    "passing yards": .init(emoji: "\u{1F3AF}", label: "Pass Yds"),
    "rushing yards": .init(emoji: "\u{1F3C3}", label: "Rush Yds"),
    "receiving yards": .init(emoji: "\u{1F4E1}", label: "Rec Yds"),
    "double doubles": .init(emoji: "\u{270C}", label: "Double-Doubles"),
    "triple doubles": .init(emoji: "\u{1F525}", label: "Triple-Doubles"),
]

private func getStatConfig(_ category: String) -> StatCategoryConfig {
    if let config = statCategories[category] { return config }
    for (key, config) in statCategories {
        if category.contains(key) || key.contains(category) { return config }
    }
    return StatCategoryConfig(emoji: "\u{1F4CA}", label: category.capitalized)
}

/// Build a readable label for game market outcomes.
/// "Paul Goldschmidt: 3+" is meaningless — include the market context.
private func gameMarketLabel(_ f: RelatedFuture) -> String {
    let outcome = f.outcomeName
    let market = f.cleanLabel ?? f.marketName

    // If the outcome already includes the team/matchup context, use it directly
    if outcome.count > 20 { return outcome }

    // Otherwise, combine: "Spread: NYY wins by 1.5+"
    // Strip the matchup prefix from the market name for brevity
    let shortMarket = market
        .replacingOccurrences(of: #"^[^:]+:\s*"#, with: "", options: .regularExpression)

    if shortMarket.isEmpty || shortMarket == market {
        return "\(outcome) (\(market))"
    }
    return "\(shortMarket): \(outcome)"
}

private func isClinched(_ f: RelatedFuture) -> Bool {
    (f.probability ?? 0) >= 0.995
}

private func isEliminated(_ f: RelatedFuture) -> Bool {
    (f.probability ?? 1) <= 0.005
}

private func settledProbabilityText(_ f: RelatedFuture) -> String {
    if isClinched(f) { return "✓" }
    if isEliminated(f) { return "<1%" }
    return formatProbability(f.probability ?? 0)
}

private func sourceLabel(_ source: String?) -> String {
    switch source {
    case "polymarket": return "Polymarket"
    case "kalshi": return "Kalshi"
    case "odds_api": return "Sportsbooks"
    default: return source?.capitalized ?? ""
    }
}

private func sourceColor(_ source: String?) -> Color {
    switch source {
    case "polymarket": return .blue
    case "kalshi": return Color(hex: "#22c55e")
    case "odds_api": return Color(hex: "#d97706")
    default: return .gray
    }
}

private func formatOdds(_ odds: Int?) -> String {
    guard let odds else { return "" }
    return odds > 0 ? "+\(odds)" : "\(odds)"
}

// MARK: - Playoff Stage Classification
// Playoff stage classification is now computed server-side in
// market_label_normalization.py:compute_playoff_stage() and returned
// as playoffStage, playoffStageType, and stageOrder fields.

private struct PlayoffStage {
    let name: String
    let probability: Double
    let order: Int
    let marketId: Int
    let source: String?
    var isDone: Bool { probability >= 0.99 }
}

private func buildPlayoffStages(_ futures: [RelatedFuture]) -> [PlayoffStage] {
    var stages: [PlayoffStage] = []
    for f in futures {
        guard let prob = f.probability else { continue }
        // Use server-computed playoff stage fields
        let name = f.playoffStage ?? f.cleanLabel ?? f.marketName
        let order = f.stageOrder ?? 3
        stages.append(PlayoffStage(name: name, probability: prob, order: order, marketId: f.marketId, source: f.source))
    }
    stages.sort { $0.order < $1.order }
    var deduped: [String: PlayoffStage] = [:]
    for s in stages {
        if let existing = deduped[s.name] {
            if s.probability > existing.probability { deduped[s.name] = s }
        } else {
            deduped[s.name] = s
        }
    }
    return deduped.values.sorted { $0.order < $1.order }
}


private func extractTradePlayer(_ marketName: String) -> String {
    // "Devin Booker's Next Team" → "Devin Booker"
    // "Jimmy Butler' Next Team" → "Jimmy Butler"
    let suffixes = ["'s Next Team", "' Next Team", "'s next destination", "' next destination"]
    let lower = marketName.lowercased()
    for suffix in suffixes {
        if let range = lower.range(of: suffix.lowercased()) {
            let player = String(marketName[marketName.startIndex..<range.lowerBound])
                .trimmingCharacters(in: .whitespaces)
            if !player.isEmpty { return player }
        }
    }
    return marketName
}

// MARK: - Categorize Futures (V6)

private struct CategorizedFutures {
    var championships: [RelatedFuture] = []
    var awards: [RelatedFuture] = []
    var statLeaders: [RelatedFuture] = []
    var seasonStats: [RelatedFuture] = []
    var games: [RelatedFuture] = []
    var statProps: [RelatedFuture] = []
    var trades: [RelatedFuture] = []
    var novelty: [RelatedFuture] = []
    var other: [RelatedFuture] = []
}

private let divisionPlayoffPattern = try! NSRegularExpression(
    pattern: "division|playoff|play[- ]?in|#1\\s+seed|best\\s+record|worst\\s+record|east\\s+winner|west\\s+winner|central\\s+winner|north\\s+winner|south\\s+winner|atlantic\\s+winner|pacific\\s+winner|\\b[NAEW][LFC]\\s+\\w+\\s+winner",
    options: .caseInsensitive
)

private let statLeaderPattern = try! NSRegularExpression(
    pattern: "leader|\\bleads?\\b|per\\s+game|batting\\s+average|earned\\s+run|home\\s+run.*leader",
    options: .caseInsensitive
)

private func isDivisionOrPlayoff(_ f: RelatedFuture) -> Bool {
    let text = f.cleanLabel ?? f.marketName
    let range = NSRange(text.startIndex..., in: text)
    return divisionPlayoffPattern.firstMatch(in: text, range: range) != nil
}

private func isStatLeader(_ f: RelatedFuture) -> Bool {
    let text = f.cleanLabel ?? f.marketName
    let range = NSRange(text.startIndex..., in: text)
    return statLeaderPattern.firstMatch(in: text, range: range) != nil
}

private func categorizeFutures(_ futures: [RelatedFuture]) -> CategorizedFutures {
    var cats = CategorizedFutures()
    for f in futures {
        let tier = effectiveTier(f)

        // Reclassify stat leader markets that backend incorrectly tags as championship
        if isStatLeader(f) && (tier == 1 || tier == 2 || f.displayCategory == "championship") {
            cats.statLeaders.append(f)
            continue
        }

        switch tier {
        case 1, 2: cats.championships.append(f)
        case 3: cats.awards.append(f)
        case 4:
            if isDivisionOrPlayoff(f) {
                cats.championships.append(f)
            } else if isStatLeader(f) {
                cats.statLeaders.append(f)
            } else {
                cats.seasonStats.append(f)
            }
        case 5: cats.games.append(f)
        case 6: cats.statProps.append(f)
        case 7: cats.trades.append(f)
        case 8: cats.novelty.append(f)
        default: cats.other.append(f)
        }
    }
    return cats
}

// MARK: - View

struct RelatedFuturesView: View {
    let eventId: Int
    var awayTeamColor: Color = .gray
    var homeTeamColor: Color = .gray
    var awayTeam: String = ""
    var homeTeam: String = ""
    var sportKey: String? = nil
    @StateObject private var vm: RelatedFuturesViewModel

    init(eventId: Int,
         awayTeamColor: Color = .gray,
         homeTeamColor: Color = .gray,
         awayTeam: String = "",
         homeTeam: String = "",
         sportKey: String? = nil,
         preloadedData: RelatedFuturesResponse? = nil) {
        self.eventId = eventId
        self.awayTeamColor = awayTeamColor
        self.homeTeamColor = homeTeamColor
        self.awayTeam = awayTeam
        self.homeTeam = homeTeam
        self.sportKey = sportKey
        _vm = StateObject(wrappedValue: RelatedFuturesViewModel(eventId: eventId, preloaded: preloadedData))
    }

    var body: some View {
        Group {
            if vm.loading {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding()
            } else if let rf = vm.relatedFutures {
                content(rf)
            } else if vm.error != nil {
                // Error state: show a subtle retry option
                Button {
                    Task { await vm.retryLoad() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                            .font(.caption)
                        Text("Tap to load related futures")
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
                }
            }
        }
        .task {
            await vm.load()
        }
        .onDisappear {
            vm.stopRefresh()
        }
    }

    // MARK: - Content (V6 Cross-Team Layout)

    @ViewBuilder
    private func content(_ rf: RelatedFuturesResponse) -> some View {
        let awayFutures = rf.awayTeamFutures ?? []
        let homeFutures = rf.homeTeamFutures ?? []
        let totalCount = awayFutures.count + homeFutures.count

        if totalCount > 0 {
            let homeCats = categorizeFutures(homeFutures)
            let awayCats = categorizeFutures(awayFutures)
            let hColor = homeTeamColor
            let aColor = awayTeamColor

            let mergedAwards = awayCats.awards + homeCats.awards
            let mergedStatLeaders = awayCats.statLeaders + homeCats.statLeaders
            let mergedNovelty = (awayCats.novelty + homeCats.novelty)
                .filter { ($0.probability ?? 0) >= 0.05 }
            let hasSections = !mergedAwards.isEmpty || !mergedStatLeaders.isEmpty
                || !homeCats.seasonStats.isEmpty || !awayCats.seasonStats.isEmpty
                || !homeCats.trades.isEmpty || !awayCats.trades.isEmpty
                || !mergedNovelty.isEmpty

            if hasSections {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 6) {
                        Image(systemName: "chart.bar.xaxis.ascending")
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                        Text("Season Futures")
                            .font(.headline)
                            .fontWeight(.semibold)
                        Spacer()
                        Text("\(totalCount)")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }

                    if let summary = rf.summary {
                        Text(summary)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                RoundedRectangle(cornerRadius: 10)
                                    .fill(Color.blue.opacity(0.06))
                            )
                    }

                    // Awards — grouped by team with mini card grid (matching web)
                    if !mergedAwards.isEmpty {
                        sectionHeader(icon: "star.fill", label: "AWARDS")
                        let homeAwards = mergedAwards.filter { teamColorForFuture($0, hColor: hColor, aColor: aColor) == hColor }
                            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }
                        let awayAwards = mergedAwards.filter { teamColorForFuture($0, hColor: hColor, aColor: aColor) == aColor }
                            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }

                        HStack(alignment: .top, spacing: 10) {
                            if !homeAwards.isEmpty {
                                awardTeamGrid(awards: homeAwards, teamColor: hColor, teamName: homeTeam)
                            }
                            if !awayAwards.isEmpty {
                                awardTeamGrid(awards: awayAwards, teamColor: aColor, teamName: awayTeam)
                            }
                        }
                    }

                    // Season Outlook (win totals, division winners minus stat leaders)
                    if !homeCats.seasonStats.isEmpty || !awayCats.seasonStats.isEmpty {
                        sectionHeader(icon: "calendar", label: "SEASON OUTLOOK")
                        HStack(alignment: .top, spacing: 8) {
                            seasonStatsColumn(
                                futures: awayCats.seasonStats,
                                teamName: awayTeam,
                                color: aColor
                            )
                            seasonStatsColumn(
                                futures: homeCats.seasonStats,
                                teamName: homeTeam,
                                color: hColor
                            )
                        }
                    }

                    // Stat Leaders (extracted from championship bucket)
                    if !mergedStatLeaders.isEmpty {
                        statLeadersSection(
                            leaders: mergedStatLeaders,
                            hColor: hColor,
                            aColor: aColor
                        )
                    }

                    // Trade Watch
                    if !homeCats.trades.isEmpty || !awayCats.trades.isEmpty {
                        TradeWatchPairView(
                            homeTrades: homeCats.trades,
                            awayTrades: awayCats.trades,
                            homeTeam: homeTeam,
                            awayTeam: awayTeam,
                            homeColor: hColor,
                            awayColor: aColor
                        )
                    }

                    // Novelty
                    if !mergedNovelty.isEmpty {
                        sectionHeader(icon: "sparkles", label: "NOVELTY & FUN")
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                ForEach(Array(mergedNovelty.enumerated()), id: \.element.id) { idx, future in
                                    NoveltyCardView(future: future, index: idx)
                                }
                            }
                        }
                    }
                }
                .padding()
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            }
        }
    }

    private func sectionHeader(icon: String, label: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 10))
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .tracking(0.8)
        }
        .foregroundStyle(.secondary)
    }

    private func teamColorForFuture(_ future: RelatedFuture, hColor: Color, aColor: Color) -> Color {
        let homeShort = homeTeam.split(separator: " ").last.map(String.init) ?? homeTeam
        return future.outcomeName.localizedCaseInsensitiveContains(homeShort) ? hColor : aColor
    }

    private func awardTeamGrid(awards: [RelatedFuture], teamColor: Color, teamName: String) -> some View {
        let columns = [GridItem(.adaptive(minimum: 130), spacing: 8)]
        return VStack(alignment: .leading, spacing: 8) {
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(awards) { future in
                    NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(shortAwardLabel(future.marketName, cleanLabel: future.cleanLabel).uppercased())
                                .font(.system(size: 10, weight: .heavy))
                                .foregroundStyle(.secondary)
                                .tracking(0.5)
                                .lineLimit(1)

                            HStack(spacing: 6) {
                                let initials = future.outcomeName.split(separator: " ")
                                    .compactMap { $0.first.map(String.init) }
                                    .prefix(2).joined()
                                if let player = future.matchedPlayer, let hs = player.headshot, let url = URL(string: hs) {
                                    AsyncImage(url: url) { phase in
                                        switch phase {
                                        case .success(let img): img.resizable().scaledToFill()
                                        default:
                                            Text(initials)
                                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                                .foregroundStyle(.white)
                                        }
                                    }
                                    .frame(width: 28, height: 28)
                                    .background(teamColor)
                                    .clipShape(Circle())
                                } else {
                                    Text(initials)
                                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                                        .foregroundStyle(.white)
                                        .frame(width: 28, height: 28)
                                        .background(teamColor)
                                        .clipShape(Circle())
                                }

                                Text(future.outcomeName)
                                    .font(.system(size: 13, weight: .medium))
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                    .foregroundStyle(.primary)
                            }

                            HStack(spacing: 6) {
                                GeometryReader { geo in
                                    Capsule()
                                        .fill(Color.secondary.opacity(0.08))
                                        .overlay(alignment: .leading) {
                                            Capsule()
                                                .fill(teamColor)
                                                .frame(width: max(2, geo.size.width * (future.probability ?? 0)))
                                        }
                                }
                                .frame(height: 6)

                                Text("\(Int(((future.probability ?? 0) * 100).rounded()))%")
                                    .font(.system(size: 11, weight: .black, design: .monospaced))
                                    .frame(width: 32, alignment: .trailing)
                            }
                        }
                        .padding(10)
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.barTrack.opacity(0.5), lineWidth: 0.5)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func statLeadersSection(leaders: [RelatedFuture], hColor: Color, aColor: Color) -> some View {
        let grouped = Dictionary(grouping: leaders) { f -> String in
            let label = (f.cleanLabel ?? f.marketName)
                .replacingOccurrences(of: #"^(MLB|NBA|NFL|NHL|MLS|WNBA)\s+"#, with: "", options: .regularExpression)
            return label
        }
        let sortedGroups = grouped.sorted { $0.value.count > $1.value.count }

        sectionHeader(icon: "trophy.fill", label: "STAT LEADERS")

        LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
            ForEach(Array(sortedGroups.prefix(8).enumerated()), id: \.offset) { _, group in
                statLeaderCard(title: group.key, players: group.value, hColor: hColor, aColor: aColor)
            }
        }

        if sortedGroups.count > 8 {
            Text("+\(sortedGroups.count - 8) more categories")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity)
        }
    }

    private func statLeaderCard(title: String, players: [RelatedFuture], hColor: Color, aColor: Color) -> some View {
        let sorted = players
            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }

        return VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 9, weight: .bold))
                .tracking(0.3)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            ForEach(Array(sorted.prefix(4).enumerated()), id: \.element.id) { _, future in
                compactAwardRow(future: future, hColor: hColor, aColor: aColor)
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(Color.secondary.opacity(0.08), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func compactAwardRow(future: RelatedFuture, hColor: Color, aColor: Color) -> some View {
        let nameParts = future.outcomeName.split(separator: " ")
        let lastName: String = nameParts.last.map(String.init) ?? future.outcomeName
        let nameColor: Color = isEliminated(future) ? Color.secondary.opacity(0.5) : .primary
        let probColor: Color = isClinched(future) ? .green : (isEliminated(future) ? Color.secondary.opacity(0.5) : teamColorForFuture(future, hColor: hColor, aColor: aColor))

        HStack(spacing: 4) {
            if let headshot = future.matchedPlayer?.headshot, let url = URL(string: headshot) {
                AsyncImage(url: url) { phase in
                    if case .success(let image) = phase {
                        image.resizable().scaledToFill()
                    } else {
                        Circle().fill(teamColorForFuture(future, hColor: hColor, aColor: aColor).opacity(0.2))
                    }
                }
                .frame(width: 16, height: 16)
                .clipShape(Circle())
            }

            Text(lastName)
                .font(.system(size: 10))
                .lineLimit(1)
                .foregroundStyle(nameColor)

            Spacer()

            Text(settledProbabilityText(future))
                .font(.system(size: 10, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(probColor)
        }
    }

    private func seasonStatsColumn(futures: [RelatedFuture], teamName: String, color: Color) -> some View {
        let shortName = teamName.split(separator: " ").last.map(String.init) ?? teamName
        var seen: Set<String> = []
        let deduped = futures
            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }
            .filter {
                let key = $0.cleanLabel ?? $0.marketName
                guard !seen.contains(key) else { return false }
                seen.insert(key)
                return true
            }

        return VStack(alignment: .leading, spacing: 2) {
            Text(shortName)
                .font(.caption2)
                .fontWeight(.bold)
                .foregroundStyle(color)
                .padding(.bottom, 2)

            ForEach(deduped.prefix(10)) { future in
                let label = (future.cleanLabel ?? future.marketName)
                    .replacingOccurrences(of: #"^(NBA|NFL|NHL|MLB|MLS|WNBA)\s+"#, with: "", options: .regularExpression)

                NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
                    HStack(spacing: 4) {
                        Text(label)
                            .font(.caption2)
                            .foregroundStyle(isEliminated(future) ? .tertiary : .secondary)
                            .lineLimit(2)
                        Spacer()
                        Text(settledProbabilityText(future))
                            .font(.caption2)
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .foregroundStyle(isClinched(future) ? .green : (isEliminated(future) ? Color.secondary.opacity(0.5) : (future.probability ?? 0) >= 0.10 ? color : .secondary))
                    }
                    .padding(.vertical, 1)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.04))
        )
    }
}

/// Pick the best championship future: must be a playoff_path or conference category.
private func bestChampionship(_ futures: [RelatedFuture]) -> RelatedFuture? {
    let validCategories: Set<String> = ["playoff_path", "conference"]
    let champOnly = futures.filter {
        if let cat = $0.displayCategory, validCategories.contains(cat) { return true }
        let name = ($0.cleanLabel ?? $0.marketName).lowercased()
        return name.contains("champion") || name.contains("world series") || name.contains("super bowl") || name.contains("stanley cup")
    }
    return champOnly.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })
}

// MARK: - V5 Section Divider

private struct SectionDividerView: View {
    let level: Int
    let label: String
    var count: Int? = nil

    var body: some View {
        HStack(spacing: 6) {
            Text("\(level)")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 18, height: 18)
                .background(Color.gray)
                .clipShape(RoundedRectangle(cornerRadius: 4))

            Text(label)
                .font(.system(size: 10, weight: .bold))
                .textCase(.uppercase)
                .tracking(0.8)
                .foregroundStyle(.secondary)

            Rectangle()
                .fill(Color.secondary.opacity(0.2))
                .frame(height: 1)

            if let count, count > 0 {
                Text("\(count) items")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.top, 8)
    }
}

// MARK: - V5 Playoff Path Pair

private struct PlayoffPathPairView: View {
    let homeFutures: [RelatedFuture]
    let awayFutures: [RelatedFuture]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        let homeStages = buildPlayoffStages(homeFutures)
        let awayStages = buildPlayoffStages(awayFutures)

        if !homeStages.isEmpty || !awayStages.isEmpty {
            HStack(alignment: .top, spacing: 8) {
                pathCard(stages: awayStages, shortName: shortTeamName(awayTeam), color: awayColor)
                pathCard(stages: homeStages, shortName: shortTeamName(homeTeam), color: homeColor)
            }
        }
    }

    private func pathCard(stages: [PlayoffStage], shortName: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(shortName)
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            if stages.isEmpty {
                Text("No playoff data")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            } else {
                ForEach(Array(stages.enumerated()), id: \.element.marketId) { _, stage in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(stage.isDone ? Color.green : (stage.probability >= 0.5 ? Color.orange : Color.gray.opacity(0.3)))
                            .frame(width: 8, height: 8)
                        Text(stage.name)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text(formatProbability(stage.probability))
                            .font(.caption2)
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .foregroundStyle(stage.isDone ? .green : color)
                        Circle()
                            .fill(sourceColor(stage.source))
                            .frame(width: 4, height: 4)
                    }
                }
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.secondary.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Color.secondary.opacity(0.08), lineWidth: 1)
        )
    }

    private func shortTeamName(_ name: String) -> String {
        name.split(separator: " ").last.map(String.init) ?? name
    }
}

// MARK: - V5 Win Totals Pair

private struct SeasonStatRowView: View {
    let future: RelatedFuture
    let teamColor: Color

    private var shortLabel: String {
        let label = future.cleanLabel ?? future.marketName
        // Strip league prefix — context is already clear from the team header
        return label
            .replacingOccurrences(of: #"^(NBA|NFL|NHL|MLB|MLS|WNBA)\s+"#, with: "", options: .regularExpression)
    }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 6) {
                Text(shortLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer()
                if let prob = future.probability {
                    Text(formatProbability(prob))
                        .font(.caption)
                        .fontWeight(.bold)
                        .monospacedDigit()
                        .foregroundStyle(prob >= 0.10 ? teamColor : .secondary)
                }
                if let rank = future.rank {
                    Text("#\(rank)")
                        .font(.system(size: 8))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 3)
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
    }
}

private struct WinTotalsPairView: View {
    let homeStats: [RelatedFuture]
    let awayStats: [RelatedFuture]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        if !homeStats.isEmpty || !awayStats.isEmpty {
            HStack(alignment: .top, spacing: 8) {
                statColumn(futures: awayStats, teamName: awayTeam, color: awayColor)
                statColumn(futures: homeStats, teamName: homeTeam, color: homeColor)
            }
        }
    }

    private func statColumn(futures: [RelatedFuture], teamName: String, color: Color) -> some View {
        let shortName = teamName.split(separator: " ").last.map(String.init) ?? teamName
        // Dedup by cleanLabel — keep highest probability per label
        var seenLabels: Set<String> = []
        let sorted = futures
            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }
            .filter {
                let key = $0.cleanLabel ?? $0.marketName
                guard !seenLabels.contains(key) else { return false }
                seenLabels.insert(key)
                return true
            }
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(color)
                    .frame(width: 14, height: 14)
                    .overlay(
                        Text(shortName.prefix(3).uppercased())
                            .font(.system(size: 5, weight: .heavy))
                            .foregroundStyle(.white)
                    )
                Text(shortName)
                    .font(.system(size: 9, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)

            Divider()

            ForEach(Array(sorted.prefix(5))) { f in
                SeasonStatRowView(future: f, teamColor: color)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.systemBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Color.secondary.opacity(0.15), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - V5 Award Compact Row

private struct AwardCompactRowView: View {
    let future: RelatedFuture
    let teamColor: Color

    private var settled: Bool { isClinched(future) || isEliminated(future) }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 8) {
                PlayerHeadshotView(
                    player: future.matchedPlayer,
                    name: future.outcomeName,
                    teamColor: teamColor,
                    size: 24
                )

                Text(future.outcomeName)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(1)
                    .foregroundStyle(isEliminated(future) ? .secondary : .primary)

                Text(shortAwardLabel(future.marketName, cleanLabel: future.cleanLabel))
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                Spacer()

                Text(settledProbabilityText(future))
                    .font(.caption)
                    .fontWeight(.bold)
                    .monospacedDigit()
                    .foregroundStyle(isClinched(future) ? .green : (isEliminated(future) ? .secondary : teamColor))

                if !settled {
                    MovementPill(change: future.probabilityChange24h)
                }
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - V5 Trade Watch Pair

private struct TradeWatchPairView: View {
    let homeTrades: [RelatedFuture]
    let awayTrades: [RelatedFuture]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                Image(systemName: "arrow.left.arrow.right")
                    .font(.system(size: 10))
                Text("TRADE WATCH")
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.8)
            }
            .foregroundStyle(.secondary)

            HStack(alignment: .top, spacing: 8) {
                tradeColumn(futures: awayTrades, teamName: awayTeam, color: awayColor)
                tradeColumn(futures: homeTrades, teamName: homeTeam, color: homeColor)
            }
        }
    }

    private func tradeColumn(futures: [RelatedFuture], teamName: String, color: Color) -> some View {
        // Dedup by player name — multiple outcomes exist per player (e.g. "Lakers" and
        // "Clippers" for the same trade market). Keep only the outcome matching this team,
        // or if none match, keep the highest probability.
        let deduped: [RelatedFuture] = {
            var byPlayer: [String: [RelatedFuture]] = [:]
            for f in futures {
                let player = extractTradePlayer(f.marketName)
                byPlayer[player, default: []].append(f)
            }
            var result: [RelatedFuture] = []
            let shortTeam = teamName.split(separator: " ").last.map(String.init) ?? teamName
            for (_, entries) in byPlayer {
                let matching = entries.first { $0.outcomeName.localizedCaseInsensitiveContains(shortTeam) }
                result.append(matching ?? entries.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })!)
            }
            return result.sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }
        }()

        return VStack(alignment: .leading, spacing: 4) {
            Text(teamName.split(separator: " ").last.map(String.init) ?? teamName)
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            if deduped.isEmpty {
                Text("None")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            } else {
                ForEach(deduped.prefix(4)) { future in
                    NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
                        HStack(spacing: 6) {
                            let playerName = extractTradePlayer(future.marketName)
                            PlayerHeadshotView(
                                player: future.matchedPlayer,
                                name: playerName,
                                teamColor: color,
                                size: 20
                            )
                            Text(playerName)
                                .font(.caption2)
                                .lineLimit(1)
                                .foregroundStyle(.primary)
                            Spacer()
                            if let prob = future.probability {
                                Text(formatProbability(prob))
                                    .font(.caption2)
                                    .fontWeight(.semibold)
                                    .monospacedDigit()
                                    .foregroundStyle(color)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.04))
        )
    }
}

// MARK: - V5 Game Markets Pair

private struct GameMarketsPairView: View {
    let homeGames: [RelatedFuture]
    let awayGames: [RelatedFuture]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        // Filter out resolved/boring markets (>90% or <10%)
        let meaningful = (awayGames + homeGames)
            .filter { ($0.probability ?? 0) > 0.10 && ($0.probability ?? 0) < 0.90 }
        // Dedup by outcome name (each outcome is a distinct line)
        var seen: Set<String> = []
        let deduped = meaningful.filter {
            let key = $0.outcomeName
            guard !seen.contains(key) else { return false }
            seen.insert(key)
            return true
        }
        let merged = deduped
            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }
            .prefix(10)

        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(merged)) { future in
                NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
                    HStack(spacing: 6) {
                        Text(gameMarketLabel(future))
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .lineLimit(2)
                        Spacer()
                        if let prob = future.probability {
                            Text(formatProbability(prob))
                                .font(.caption)
                                .fontWeight(.bold)
                                .monospacedDigit()
                                .foregroundStyle(prob > 0.5 ? homeColor : .secondary)
                        }
                        if let change = future.probabilityChange24h, abs(change) >= 0.005 {
                            Image(systemName: change > 0 ? "arrow.up" : "arrow.down")
                                .font(.system(size: 7, weight: .bold))
                                .foregroundStyle(change > 0 ? .green : .red)
                        }
                    }
                    .padding(.vertical, 4)
                    .padding(.horizontal, 8)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - V5 Novelty Card

private let noveltyGradients: [(Color, Color)] = [
    (Color.purple.opacity(0.15), Color.blue.opacity(0.08)),
    (Color.orange.opacity(0.15), Color.pink.opacity(0.08)),
    (Color.green.opacity(0.15), Color.teal.opacity(0.08)),
    (Color.blue.opacity(0.15), Color.indigo.opacity(0.08)),
    (Color.pink.opacity(0.15), Color.red.opacity(0.08)),
    (Color.teal.opacity(0.15), Color.green.opacity(0.08)),
]

private struct NoveltyCardView: View {
    let future: RelatedFuture
    let index: Int

    private var gradient: (Color, Color) {
        noveltyGradients[index % noveltyGradients.count]
    }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            VStack(alignment: .leading, spacing: 8) {
                Text(future.cleanLabel ?? future.marketName)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.primary)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer()

                HStack {
                    if let prob = future.probability {
                        Text(formatProbability(prob))
                            .font(.title3)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    }
                    Spacer()
                    SourceBadge(source: future.source)
                }
            }
            .padding(12)
            .frame(width: 180, height: 110)
            .background(
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(Color.secondary.opacity(0.1), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Championship Hero Card

private struct ChampionshipCard: View {
    let future: RelatedFuture
    let teamColor: Color
    var teamName: String = ""

    private var shortTeam: String {
        teamName.split(separator: " ").last.map(String.init) ?? teamName
    }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(shortTeam)
                        .font(.caption2)
                        .fontWeight(.bold)
                        .foregroundStyle(teamColor)
                    Spacer()
                    SourceBadge(source: future.source)
                }

                Text(future.cleanLabel ?? future.marketName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text(formatProbability(future.probability ?? 0))
                                .font(.system(size: 28, weight: .bold, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(teamColor)
                            MovementPill(change: future.probabilityChange24h)
                        }
                    }
                    Spacer()
                    if let rank = future.rank {
                        VStack(spacing: 1) {
                            Text("RANK")
                                .font(.system(size: 8, weight: .semibold))
                                .tracking(0.5)
                                .foregroundStyle(.secondary)
                            Text("#\(rank)")
                                .font(.system(size: 20, weight: .bold, design: .rounded))
                                .foregroundStyle(.primary.opacity(0.7))
                        }
                    }
                }

                // Probability bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color.secondary.opacity(0.1))
                        Capsule()
                            .fill(teamColor.opacity(0.6))
                            .frame(width: max(2, geo.size.width * min(1, (future.probability ?? 0) / 0.5)))
                    }
                }
                .frame(height: 4)
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(
                        LinearGradient(
                            colors: [teamColor.opacity(0.1), teamColor.opacity(0.03)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .strokeBorder(teamColor.opacity(0.2), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Award Card

private struct AwardCard: View {
    let future: RelatedFuture
    let teamColor: Color

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 12) {
                // Player headshot
                PlayerHeadshotView(
                    player: future.matchedPlayer,
                    name: future.outcomeName,
                    teamColor: teamColor,
                    size: 44
                )

                // Name + award label
                VStack(alignment: .leading, spacing: 3) {
                    Text(future.outcomeName)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .lineLimit(1)
                        .foregroundStyle(.primary)
                    HStack(spacing: 4) {
                        Text("\u{2B50}")
                            .font(.system(size: 9))
                        Text(shortAwardLabel(future.marketName, cleanLabel: future.cleanLabel))
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                // Probability + movement + odds
                VStack(alignment: .trailing, spacing: 2) {
                    HStack(spacing: 4) {
                        Text(formatProbability(future.probability ?? 0))
                            .font(.title3)
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .foregroundStyle(teamColor)
                        MovementPill(change: future.probabilityChange24h)
                    }
                    if let odds = future.americanOdds {
                        Text(formatOdds(odds))
                            .font(.caption2.monospaced())
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(
                        LinearGradient(
                            colors: [teamColor.opacity(0.06), .clear],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(teamColor.opacity(0.12), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Game Grid (2-col)

private struct GameGrid: View {
    let futures: [RelatedFuture]
    let teamColor: Color
    let teamName: String

    private let columns = [
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8),
    ]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 8) {
            ForEach(futures) { future in
                GameCell(future: future, teamColor: teamColor, teamName: teamName)
            }
        }
    }
}

private struct GameCell: View {
    let future: RelatedFuture
    let teamColor: Color
    let teamName: String

    private var prob: Double { future.probability ?? 0 }
    private var favored: Bool { prob > 0.5 }
    private var opponent: String { extractOpponent(future.marketName, teamName: teamName) }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            ZStack(alignment: .leading) {
                // Background fill showing probability
                GeometryReader { geo in
                    Rectangle()
                        .fill(teamColor.opacity(favored ? 0.08 : 0.03))
                        .frame(width: geo.size.width * min(1, prob))
                }

                VStack(alignment: .leading, spacing: 4) {
                    // Date
                    if let dateStr = future.resolutionDate, let date = dateStr.asDate {
                        Text(date, format: .dateTime.weekday(.abbreviated).month(.abbreviated).day())
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(.tertiary)
                    }
                    // Opponent + probability
                    HStack {
                        Text(opponent)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        HStack(spacing: 2) {
                            Text("\(Int((prob * 100).rounded()))%")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(favored ? teamColor : .secondary)
                            if let change = future.probabilityChange24h, abs(change) >= 0.005 {
                                Image(systemName: change > 0 ? "arrow.up" : "arrow.down")
                                    .font(.system(size: 7, weight: .bold))
                                    .foregroundStyle(change > 0 ? .green : .red)
                            }
                        }
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
            }
            .background(Color.secondary.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Color.secondary.opacity(0.08), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Stat Props Section

private struct StatPropsSection: View {
    let futures: [RelatedFuture]
    let teamColor: Color
    var boxScore: [String: [String: Double]]? = nil
    var eventStatus: String? = nil
    var gamePeriod: String? = nil
    var gameClock: String? = nil
    var sportKey: String? = nil

    private var isLive: Bool { eventStatus == "live" }
    private var isFinished: Bool { eventStatus == "completed" || eventStatus == "closed" }
    private var hasBoxScore: Bool { boxScore != nil && !(boxScore?.isEmpty ?? true) }

    private var meaningful: [RelatedFuture] {
        futures.filter { ($0.probability ?? 0) > 0.02 && ($0.probability ?? 0) < 0.98 }
    }

    private var gameProgressValue: Double? {
        guard isLive else { return nil }
        return computeGameProgress(sport: sportKey, period: gamePeriod, clock: gameClock)
    }

    var body: some View {
        if !meaningful.isEmpty {
            let grouped = Dictionary(grouping: meaningful) { extractStatCategory($0.marketName) }
            let sortedGroups = grouped.sorted { $0.value.count > $1.value.count }

            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 5) {
                    Image(systemName: (isLive && hasBoxScore) ? "sportscourt.fill" : "chart.bar.fill")
                        .font(.system(size: 10))
                    Text((isLive && hasBoxScore) ? "Live Game Props" : isFinished && hasBoxScore ? "Game Results" : "Game Props")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .textCase(.uppercase)
                        .tracking(0.5)
                    if isLive && hasBoxScore {
                        Circle()
                            .fill(.red)
                            .frame(width: 6, height: 6)
                    }
                }
                .foregroundStyle((isLive && hasBoxScore) ? teamColor : .secondary)

                ForEach(Array(sortedGroups.prefix(3).enumerated()), id: \.offset) { _, group in
                    let config = getStatConfig(group.key)
                    let rows = group.value.sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }

                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 4) {
                            Text(config.emoji)
                                .font(.system(size: 12))
                            Text(config.label)
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                            if !((isLive || isFinished) && hasBoxScore) {
                                Text("(\(rows.count))")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }

                        if (isLive || isFinished) && hasBoxScore {
                            // Full-width tracker rows
                            ForEach(Array(rows.prefix(4).enumerated()), id: \.element.id) { _, row in
                                StatTrackerRow(
                                    future: row,
                                    teamColor: teamColor,
                                    boxScore: boxScore!,
                                    isLive: isLive,
                                    gameProgress: gameProgressValue
                                )
                            }
                        } else {
                            // Pre-game: compact cards
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(Array(rows.prefix(4).enumerated()), id: \.element.id) { _, row in
                                        StatPropCard(future: row, teamColor: teamColor)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Live/Completed Stat Tracker Row

private struct StatTrackerRow: View {
    let future: RelatedFuture
    let teamColor: Color
    let boxScore: [String: [String: Double]]
    let isLive: Bool
    var gameProgress: Double? = nil

    private var playerName: String {
        let name = future.outcomeName
        if let idx = name.firstIndex(of: ":") {
            return String(name[..<idx]).trimmingCharacters(in: .whitespaces)
        }
        return name
    }

    private var lineText: String {
        let name = future.outcomeName
        if let idx = name.firstIndex(of: ":") {
            return String(name[name.index(after: idx)...]).trimmingCharacters(in: .whitespaces)
        }
        return ""
    }

    private var lineValue: Double? {
        guard let range = lineText.range(of: #"\d+\.?\d*"#, options: .regularExpression) else { return nil }
        return Double(lineText[range])
    }

    private var isOverBet: Bool {
        lineText.lowercased().contains("over") || lineText.hasSuffix("+")
    }

    private var statCategory: String {
        extractStatCategory(future.marketName)
    }

    private var currentValue: Double? {
        lookupBoxScore(playerName: playerName, stat: statCategory, boxScore: boxScore)
    }

    private var projected: Int? {
        guard isLive, let current = currentValue, let gp = gameProgress, gp > 0.08 else { return nil }
        return Int((current / gp).rounded())
    }

    private var hitLine: Bool? {
        guard let current = currentValue, let line = lineValue else { return nil }
        return isOverBet ? current > line : current < line
    }

    private var onPaceToHit: Bool? {
        guard let proj = projected, let line = lineValue else { return nil }
        return isOverBet ? Double(proj) > line : Double(proj) < line
    }

    var body: some View {
        HStack(spacing: 12) {
            PlayerHeadshotView(
                player: future.matchedPlayer,
                name: playerName,
                teamColor: teamColor,
                size: 44
            )

            VStack(alignment: .leading, spacing: 6) {
                // Player name
                Text(playerName)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .lineLimit(1)

                // Current value + stat + projection/result
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if let current = currentValue {
                        Text("\(Int(current))")
                            .font(.title2)
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .foregroundStyle(teamColor)
                    }

                    Text(statCategory)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Spacer()

                    if isLive {
                        // Projection
                        if let proj = projected {
                            VStack(alignment: .trailing, spacing: 1) {
                                HStack(spacing: 3) {
                                    Image(systemName: "arrow.right")
                                        .font(.system(size: 9, weight: .bold))
                                    Text("\(proj)")
                                        .font(.callout)
                                        .fontWeight(.bold)
                                        .monospacedDigit()
                                }
                                .foregroundStyle(onPaceToHit == true ? .green : .orange)
                                Text("projected")
                                    .font(.system(size: 9))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    } else {
                        // Completed: result badge
                        if let hit = hitLine {
                            HStack(spacing: 3) {
                                Image(systemName: hit ? "checkmark.circle.fill" : "xmark.circle.fill")
                                Text(hit ? "Hit" : "Missed")
                            }
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(hit ? .green : .red)
                        }
                    }
                }

                // Progress bar toward line
                if let line = lineValue {
                    let current = currentValue ?? 0
                    let maxVal = max(line * 1.5, current * 1.2, 1)
                    let barProgress = min(1.0, current / maxVal)
                    let linePosition = min(1.0, line / maxVal)

                    HStack(spacing: 8) {
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                // Track
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.secondary.opacity(0.12))
                                // Fill
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(teamColor.opacity(0.7))
                                    .frame(width: max(0, geo.size.width * barProgress))
                                // Line marker
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(Color.primary.opacity(0.4))
                                    .frame(width: 2, height: 14)
                                    .offset(x: max(0, geo.size.width * linePosition - 1))
                            }
                        }
                        .frame(height: 8)

                        // Line value + probability
                        HStack(spacing: 4) {
                            Text(lineText)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(.secondary)
                            if let prob = future.probability {
                                Text("\(Int(prob * 100))%")
                                    .font(.system(size: 10, weight: .semibold))
                                    .foregroundStyle(teamColor)
                            }
                        }
                        .fixedSize()
                    }
                }
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.secondary.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(
                    isLive ? teamColor.opacity(0.2) : Color.secondary.opacity(0.08),
                    lineWidth: 1
                )
        )
    }
}

private struct StatPropCard: View {
    let future: RelatedFuture
    let teamColor: Color

    private var parsed: (player: String?, line: String?) {
        let name = future.outcomeName
        if let colonIdx = name.firstIndex(of: ":") {
            let player = String(name[..<colonIdx]).trimmingCharacters(in: .whitespaces)
            let line = String(name[name.index(after: colonIdx)...]).trimmingCharacters(in: .whitespaces)
            return (player, line)
        }
        return (name, nil)
    }

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            VStack(spacing: 6) {
                // Player headshot
                PlayerHeadshotView(
                    player: future.matchedPlayer,
                    name: parsed.player ?? "?",
                    teamColor: teamColor,
                    size: 36
                )

                // Gauge
                StatGauge(probability: future.probability ?? 0, teamColor: teamColor, size: 48)

                // Player name
                Text(parsed.player ?? future.outcomeName)
                    .font(.caption2)
                    .fontWeight(.medium)
                    .lineLimit(1)
                    .foregroundStyle(.primary)

                // Line
                if let line = parsed.line {
                    Text(line)
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: 80)
            .padding(.vertical, 10)
            .padding(.horizontal, 6)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.secondary.opacity(0.06))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(Color.secondary.opacity(0.08), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Semi-circular Stat Gauge

private struct StatGauge: View {
    let probability: Double
    let teamColor: Color
    var size: CGFloat = 48

    private var pct: Int { Int((probability * 100).rounded()) }
    private var radius: CGFloat { (size - 6) / 2 }
    private var circumference: CGFloat { .pi * radius }
    private var offset: CGFloat { circumference * (1 - probability) }

    var body: some View {
        VStack(spacing: -2) {
            Canvas { ctx, canvasSize in
                let center = CGPoint(x: canvasSize.width / 2, y: canvasSize.height * 0.9)
                let r = radius

                // Background arc
                var bgPath = Path()
                bgPath.addArc(center: center, radius: r, startAngle: .degrees(180), endAngle: .degrees(0), clockwise: false)
                ctx.stroke(bgPath, with: .color(.secondary.opacity(0.15)), lineWidth: 4)

                // Colored arc
                let endAngle = Angle.degrees(180 + probability * 180)
                var fgPath = Path()
                fgPath.addArc(center: center, radius: r, startAngle: .degrees(180), endAngle: endAngle, clockwise: false)
                ctx.stroke(
                    fgPath,
                    with: .color(teamColor.opacity(pct >= 50 ? 0.85 : 0.5)),
                    style: StrokeStyle(lineWidth: 4, lineCap: .round)
                )
            }
            .frame(width: size, height: size * 0.5)

            Text("\(pct)%")
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(pct >= 50 ? teamColor : .secondary)
        }
    }
}

// MARK: - Movement Pill

private struct MovementPill: View {
    let change: Double?

    var body: some View {
        if let change, abs(change) >= 0.005 {
            let isUp = change > 0
            let abs = abs(change * 100)
            HStack(spacing: 1) {
                Image(systemName: isUp ? "arrow.up" : "arrow.down")
                    .font(.system(size: 7, weight: .bold))
                Text(String(format: "%.1f%%", abs))
                    .font(.system(size: 9, weight: .semibold))
            }
            .foregroundStyle(isUp ? .green : .red)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background((isUp ? Color.green : Color.red).opacity(0.12))
            .clipShape(Capsule())
        }
    }
}

// MARK: - Source Badge

private struct SourceBadge: View {
    let source: String?

    var body: some View {
        if let source, !source.isEmpty {
            Text(sourceLabel(source))
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(sourceColor(source))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(sourceColor(source).opacity(0.12))
                .clipShape(Capsule())
        }
    }
}

// MARK: - Player Headshot

private struct PlayerHeadshotView: View {
    let player: MatchedPlayer?
    let name: String
    let teamColor: Color
    var size: CGFloat = 44

    @State private var image: PlatformImage?
    @State private var loadFailed = false

    private var imageURLString: String? {
        if let headshot = player?.headshot, !headshot.isEmpty {
            return headshot
        }
        if let espnId = player?.espnId, !espnId.isEmpty {
            return "https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/\(espnId).png&w=\(Int(size * 2))&h=\(Int(size * 2))"
        }
        return nil
    }

    var body: some View {
        Group {
            if let image {
                Image(platformImage: image)
                    .resizable()
                    .scaledToFill()
            } else if loadFailed || imageURLString == nil {
                initialsView
            } else {
                initialsView  // Show initials while loading (no placeholder spinner)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .task(id: imageURLString) {
            guard let urlString = imageURLString,
                  let url = URL(string: urlString) else {
                loadFailed = true
                return
            }
            image = await ImageCache.shared.image(for: url)
            if image == nil { loadFailed = true }
        }
    }

    private var initialsView: some View {
        ZStack {
            Circle()
                .fill(teamColor.opacity(0.15))
            Text(String(name.prefix(1)))
                .font(.system(size: size * 0.35, weight: .semibold, design: .rounded))
                .foregroundStyle(teamColor)
        }
    }
}

// MARK: - Game Progress & Box Score Helpers

private func computeGameProgress(sport: String?, period: String?, clock: String?) -> Double? {
    guard let periodStr = period, let period = Int(periodStr), period > 0 else { return nil }

    let totalPeriods: Double
    let periodMinutes: Double

    let s = (sport ?? "").lowercased()
    if s.contains("ncaa") || s.contains("wncaa") {
        // College basketball: 2 halves of 20 min
        totalPeriods = 2
        periodMinutes = 20
    } else if s.contains("basketball") || s.contains("nba") || s.contains("wnba") {
        totalPeriods = 4
        periodMinutes = 12
    } else if s.contains("football") || s.contains("nfl") {
        totalPeriods = 4
        periodMinutes = 15
    } else if s.contains("hockey") || s.contains("nhl") {
        totalPeriods = 3
        periodMinutes = 20
    } else if s.contains("soccer") || s.contains("mls") || s.contains("epl") {
        totalPeriods = 2
        periodMinutes = 45
    } else if s.contains("baseball") || s.contains("mlb") {
        // Baseball: 9 innings, no clock
        totalPeriods = 9
        let progress = (Double(period) - 0.5) / totalPeriods
        return min(1.0, max(0.01, progress))
    } else {
        totalPeriods = 4
        periodMinutes = 12
    }

    // Parse clock "5:30" → 5.5 minutes remaining in period
    var remainingInPeriod = periodMinutes / 2 // default to midpoint
    if let clock = clock {
        let parts = clock.split(separator: ":")
        if parts.count == 2, let min = Double(parts[0]), let sec = Double(parts[1]) {
            remainingInPeriod = min + sec / 60.0
        } else if let sec = Double(clock) {
            remainingInPeriod = sec / 60.0
        }
    }

    let completedPeriods = Double(period - 1)
    let currentPeriodProgress = (periodMinutes - remainingInPeriod) / periodMinutes
    let totalProgress = (completedPeriods + currentPeriodProgress) / totalPeriods

    return min(1.0, max(0.01, totalProgress))
}

private func lookupBoxScore(playerName: String, stat: String, boxScore: [String: [String: Double]]) -> Double? {
    // Exact match
    if let stats = boxScore[playerName], let value = stats[stat] {
        return value
    }

    // Case-insensitive match
    let lower = playerName.lowercased()
    for (name, stats) in boxScore {
        if name.lowercased() == lower, let value = stats[stat] {
            return value
        }
    }

    // Last name match (handles "J. Tatum" vs "Jayson Tatum")
    let lastName = playerName.split(separator: " ").last.map(String.init) ?? playerName
    for (name, stats) in boxScore {
        let boxLastName = name.split(separator: " ").last.map(String.init) ?? name
        if boxLastName.lowercased() == lastName.lowercased(), let value = stats[stat] {
            return value
        }
    }

    return nil
}
