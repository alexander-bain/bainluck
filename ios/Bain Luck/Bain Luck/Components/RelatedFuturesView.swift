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
    // Prefer backend display_category when available
    if let cat = f.displayCategory, let tier = categoryToTier[cat] {
        return tier
    }
    // Fallback to regex-based detection
    let name = f.marketName
    if isStatProp(name) { return 6 }
    if isGameMarket(name) { return 5 }
    if isAwardMarket(name) { return 3 }
    if isNotChampionship(name) { return 4 }
    if let tier = f.marketTier, tier >= 1, tier <= 5 { return tier }
    return 5
}

private func isStatProp(_ name: String) -> Bool {
    let patterns = [
        ":\\s*(points|assists|rebounds|steals|blocks|three\\s*pointers?|3-?pointers?|turnovers|strikeouts|hits|runs|home\\s*runs|goals|saves|sacks|passing\\s*yards|rushing\\s*yards|receiving\\s*yards|touchdowns|completions|interceptions|aces|double\\s*doubles?|triple\\s*doubles?)",
        "\\bat\\b.*:\\s*\\w",
    ]
    return patterns.contains { name.range(of: $0, options: [.regularExpression, .caseInsensitive]) != nil }
}

private func isGameMarket(_ name: String) -> Bool {
    let patterns = ["\\bvs\\.?\\s", "\\s\u{2013}\\s", "more\\s+markets$", "moneyline$", "\\bgame\\s+\\d"]
    return patterns.contains { name.range(of: $0, options: [.regularExpression, .caseInsensitive]) != nil }
}

private func isAwardMarket(_ name: String) -> Bool {
    let patterns = [
        "\\bmvp\\b", "\\bgolden\\s+boot\\b", "\\bgolden\\s+glove\\b", "cy\\s*young",
        "\\bnewcomer\\b|\\brookie\\b", "player\\s+of\\s+(the\\s+)?year", "\\bballon\\b",
        "\\bbest\\s+(actor|actress|picture|director|supporting)\\b",
        "\\bleader\\b", "\\bper\\s+game\\b", "\\bclutch\\b", "\\bfinals\\s+mvp\\b",
        "\\b[ew]cf\\s+mvp\\b", "\\bmost\\s+improved\\b", "\\bsixth\\s+man\\b", "\\b6th\\s+man\\b",
        "\\ball[- ]?star\\s+mvp\\b", "\\bscoring\\s+(leader|title|champion)",
        "\\bhome\\s+run\\s+(leader|king)", "\\bcover\\s+of\\b", "\\b2k\\b",
    ]
    return patterns.contains { name.range(of: $0, options: [.regularExpression, .caseInsensitive]) != nil }
}

private func isNotChampionship(_ name: String) -> Bool {
    let patterns = [
        "\\bwin\\s+total", "\\bover/under\\b", "\\bregular\\s+season\\s+wins",
        "\\bcover\\s+of\\b", "\\b2k\\b", "\\bplayoff\\s+appearance", "\\bmake\\s+playoffs",
        "\\bplayoff\\s*berth", "\\bto\\s+make\\b", "\\bseeding\\b", "\\bseed\\b",
        "\\bover\\s+\\d", "\\bunder\\s+\\d", "\\bexact\\s+wins",
    ]
    return patterns.contains { name.range(of: $0, options: [.regularExpression, .caseInsensitive]) != nil }
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

// MARK: - View

struct RelatedFuturesView: View {
    let eventId: Int
    var awayTeamColor: Color = .gray
    var homeTeamColor: Color = .gray
    var awayTeam: String = ""
    var homeTeam: String = ""
    var sportKey: String? = nil
    @StateObject private var vm: RelatedFuturesViewModel
    @State private var expanded = false

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

    // MARK: - Content

    @ViewBuilder
    private func content(_ rf: RelatedFuturesResponse) -> some View {
        let awayFutures = rf.awayTeamFutures ?? []
        let homeFutures = rf.homeTeamFutures ?? []
        let totalCount = awayFutures.count + homeFutures.count

        if totalCount > 0 {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                HStack(spacing: 6) {
                    Image(systemName: "chart.bar.xaxis.ascending")
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                    Text("Bigger Picture")
                        .font(.headline)
                        .fontWeight(.semibold)
                    Spacer()
                    Text("\(totalCount)")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }

                // AI Summary
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

                // Away team futures
                if !awayFutures.isEmpty {
                    teamSection(
                        teamName: rf.awayTeam,
                        futures: awayFutures,
                        teamColor: awayTeamColor,
                        allFutures: awayFutures + homeFutures,
                        boxScore: rf.boxScore,
                        eventStatus: rf.eventStatus,
                        gamePeriod: rf.gamePeriod,
                        gameClock: rf.gameClock
                    )
                }

                // Home team futures
                if !homeFutures.isEmpty {
                    teamSection(
                        teamName: rf.homeTeam,
                        futures: homeFutures,
                        teamColor: homeTeamColor,
                        allFutures: awayFutures + homeFutures,
                        boxScore: rf.boxScore,
                        eventStatus: rf.eventStatus,
                        gamePeriod: rf.gamePeriod,
                        gameClock: rf.gameClock
                    )
                }

                // Expand/collapse
                if totalCount > 6 && !expanded {
                    Button {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            expanded = true
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text("See all \(totalCount) futures")
                                .font(.subheadline)
                                .fontWeight(.medium)
                            Image(systemName: "chevron.down")
                                .font(.system(size: 10, weight: .semibold))
                        }
                        .foregroundStyle(.blue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    // MARK: - Team Section

    private func teamSection(teamName: String, futures: [RelatedFuture], teamColor: Color, allFutures: [RelatedFuture], boxScore: [String: [String: Double]]? = nil, eventStatus: String? = nil, gamePeriod: Int? = nil, gameClock: String? = nil) -> some View {
        let tiered = Dictionary(grouping: futures) { effectiveTier($0) }
        let championships = (tiered[1] ?? []) + (tiered[2] ?? [])
        let awards = (tiered[3] ?? []) + (tiered[4] ?? [])
        let games = tiered[5] ?? []
        let statProps = tiered[6] ?? []
        let trades = tiered[7] ?? []
        let novelty = tiered[8] ?? []

        let displayLimit = expanded ? 999 : 6
        var shown = 0

        return VStack(alignment: .leading, spacing: 12) {
            // Team header
            HStack(spacing: 6) {
                Circle()
                    .fill(teamColor)
                    .frame(width: 8, height: 8)
                Text(teamName)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
            }

            // Championships
            if !championships.isEmpty && shown < displayLimit {
                let items = Array(championships.prefix(displayLimit - shown))
                ForEach(items) { future in
                    ChampionshipCard(future: future, teamColor: teamColor)
                }
                let _ = (shown += items.count)
            }

            // Awards
            if !awards.isEmpty && shown < displayLimit {
                let items = Array(awards.prefix(displayLimit - shown))
                sectionLabel(icon: "star.fill", title: "Awards")
                ForEach(items) { future in
                    AwardCard(future: future, teamColor: teamColor)
                }
                let _ = (shown += items.count)
            }

            // Game grid
            if !games.isEmpty && shown < displayLimit {
                let items = Array(games.prefix(displayLimit - shown))
                sectionLabel(icon: "calendar", title: "Upcoming Games")
                GameGrid(futures: items, teamColor: teamColor, teamName: teamName)
                let _ = (shown += items.count)
            }

            // Stat props
            if !statProps.isEmpty && shown < displayLimit {
                let items = Array(statProps.prefix(displayLimit - shown))
                StatPropsSection(
                    futures: items,
                    teamColor: teamColor,
                    boxScore: boxScore,
                    eventStatus: eventStatus,
                    gamePeriod: gamePeriod,
                    gameClock: gameClock,
                    sportKey: sportKey
                )
                let _ = (shown += items.count)
            }

            // Trade Watch
            if !trades.isEmpty && shown < displayLimit {
                let items = Array(trades.prefix(min(5, displayLimit - shown)))
                sectionLabel(icon: "arrow.left.arrow.right", title: "Trade Watch")
                ForEach(items) { future in
                    compactFutureRow(future: future, teamColor: teamColor)
                }
                let _ = (shown += items.count)
            }

            // Fun Markets
            if !novelty.isEmpty && shown < displayLimit {
                let items = Array(novelty.prefix(min(3, displayLimit - shown)))
                sectionLabel(icon: "sparkles", title: "Fun Markets")
                ForEach(items) { future in
                    compactFutureRow(future: future, teamColor: teamColor)
                }
                let _ = (shown += items.count)
            }
        }
    }

    // Compact row for trade watch / fun markets
    private func compactFutureRow(future: RelatedFuture, teamColor: Color) -> some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            HStack(spacing: 8) {
                Text(future.cleanLabel ?? future.marketName)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer()
                if let prob = future.probability {
                    Text(formatProbability(prob))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                        .foregroundStyle(teamColor)
                }
                SourceBadge(source: future.source)
            }
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Section Label

    private func sectionLabel(icon: String, title: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 10))
            Text(title)
                .font(.caption)
                .fontWeight(.semibold)
                .textCase(.uppercase)
                .tracking(0.5)
        }
        .foregroundStyle(.secondary)
        .padding(.top, 4)
    }
}

// MARK: - Championship Hero Card

private struct ChampionshipCard: View {
    let future: RelatedFuture
    let teamColor: Color

    var body: some View {
        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
            VStack(alignment: .leading, spacing: 10) {
                // Header: tier label + source
                HStack {
                    HStack(spacing: 4) {
                        Text("\u{1F3C6}")
                            .font(.system(size: 10))
                        Text((future.marketTier ?? 0) <= 1 ? "CHAMPIONSHIP" : "CONFERENCE")
                            .font(.system(size: 10, weight: .semibold))
                            .tracking(0.8)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    SourceBadge(source: future.source)
                }

                // Market name (prefer clean label from backend)
                Text(future.cleanLabel ?? future.marketName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                // Big probability + movement + rank
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text(formatProbability(future.probability ?? 0))
                                .font(.system(size: 28, weight: .bold, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(teamColor)
                            MovementPill(change: future.probabilityChange24h)
                        }
                        if let odds = future.americanOdds {
                            Text(formatOdds(odds))
                                .font(.caption2.monospaced())
                                .foregroundStyle(.secondary)
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
    var gamePeriod: Int? = nil
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
                    Text((isLive && hasBoxScore) ? "Live Player Stats" : isFinished && hasBoxScore ? "Player Results" : "Player Stats")
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

    @State private var image: UIImage?
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
                Image(uiImage: image)
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

private func computeGameProgress(sport: String?, period: Int?, clock: String?) -> Double? {
    guard let period = period, period > 0 else { return nil }

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
