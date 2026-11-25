import Foundation

/// #13013 / Ruling 401: B — Bands inside the Sports tab list (`Live Now`,
/// `Upcoming`, `Just Happened`), each sub-grouped by league with big leagues
/// first and chronological time order preserved inside each league.
nonisolated enum SportsBandKind401B: Sendable {
    case live
    case upcoming
    case justHappened
}

/// One league's sub-group inside a Sports tab band (`401: B`).
nonisolated struct SportsLeagueGroup401B: Identifiable, Sendable {
    let leagueKey: String
    let title: String
    let systemImage: String
    let priorityRank: Int
    let items: [FeedItem]

    var id: String { leagueKey }
}

/// Pure grouping and ordering helpers for Ruling `401: B`:
/// - Inside each band (`Live Now`, `Upcoming`, `Just Happened`), games are grouped
///   under their league heading.
/// - Leagues sort **big leagues first** using one canonical priority table, with
///   alphabetical title tie-breaking for unlisted/equal-rank leagues.
/// - Games inside each league sort in **time order**:
///   - `Live Now`: earliest scheduled start first.
///   - `Upcoming`: earliest scheduled start first (`startIsTbd` after confirmed times at the same instant).
///   - `Just Happened`: most recently completed (falling back to start time) first.
enum SportsLeagueBands401B {
    private struct LeagueSpec {
        let rank: Int
        let title: String
        let icon: String
    }

    private static let canonicalSpecs: [String: LeagueSpec] = [
        "americanfootball_nfl": LeagueSpec(rank: 0, title: "NFL", icon: "football.fill"),
        "basketball_nba": LeagueSpec(rank: 1, title: "NBA", icon: "basketball.fill"),
        "baseball_mlb": LeagueSpec(rank: 2, title: "MLB", icon: "baseball.fill"),
        "icehockey_nhl": LeagueSpec(rank: 3, title: "NHL", icon: "hockey.puck.fill"),
        "americanfootball_ncaaf": LeagueSpec(rank: 4, title: "NCAAF", icon: "football.fill"),
        "basketball_ncaab": LeagueSpec(rank: 5, title: "NCAAB", icon: "basketball.fill"),
        "basketball_wncaab": LeagueSpec(rank: 6, title: "WNCAAB", icon: "basketball.fill"),
        "basketball_wnba": LeagueSpec(rank: 7, title: "WNBA", icon: "basketball.fill"),
        "soccer_epl": LeagueSpec(rank: 8, title: "EPL", icon: "soccerball"),
        "soccer_uefa_champs_league": LeagueSpec(rank: 9, title: "UCL", icon: "soccerball"),
        "soccer_spain_la_liga": LeagueSpec(rank: 10, title: "La Liga", icon: "soccerball"),
        "soccer_italy_serie_a": LeagueSpec(rank: 11, title: "Serie A", icon: "soccerball"),
        "soccer_germany_bundesliga": LeagueSpec(rank: 12, title: "Bundesliga", icon: "soccerball"),
        "soccer_france_ligue_one": LeagueSpec(rank: 13, title: "Ligue 1", icon: "soccerball"),
        "soccer_usa_mls": LeagueSpec(rank: 14, title: "MLS", icon: "soccerball"),
        "tennis_atp": LeagueSpec(rank: 16, title: "ATP Tennis", icon: "figure.tennis"),
        "tennis_wta": LeagueSpec(rank: 17, title: "WTA Tennis", icon: "figure.tennis"),
        "tennis": LeagueSpec(rank: 18, title: "Tennis", icon: "figure.tennis"),
        "golf": LeagueSpec(rank: 19, title: "Golf", icon: "figure.golf"),
        "mma_mixed_martial_arts": LeagueSpec(rank: 20, title: "MMA", icon: "figure.boxing"),
        "boxing_boxing": LeagueSpec(rank: 21, title: "Boxing", icon: "figure.boxing"),
    ]

    nonisolated static func grouped(_ items: [FeedItem], band: SportsBandKind401B) -> [SportsLeagueGroup401B] {
        guard !items.isEmpty else { return [] }

        var buckets: [String: (meta: LeagueSpec, items: [FeedItem])] = [:]
        var orderedKeys: [String] = []

        for item in items {
            let (key, meta) = leagueMetadata(for: item)
            if buckets[key] == nil {
                buckets[key] = (meta: meta, items: [item])
                orderedKeys.append(key)
            } else {
                buckets[key]?.items.append(item)
            }
        }

        let groups = orderedKeys.compactMap { key -> SportsLeagueGroup401B? in
            guard let bucket = buckets[key] else { return nil }
            let sortedItems = sortItemsWithinLeague(bucket.items, band: band)
            return SportsLeagueGroup401B(
                leagueKey: key,
                title: bucket.meta.title,
                systemImage: bucket.meta.icon,
                priorityRank: bucket.meta.rank,
                items: sortedItems
            )
        }

        return groups.sorted { lhs, rhs in
            if lhs.priorityRank != rhs.priorityRank {
                return lhs.priorityRank < rhs.priorityRank
            }
            let cmp = lhs.title.localizedCaseInsensitiveCompare(rhs.title)
            if cmp != .orderedSame {
                return cmp == .orderedAscending
            }
            return lhs.leagueKey < rhs.leagueKey
        }
    }

    nonisolated static func orderedItems(_ items: [FeedItem], band: SportsBandKind401B) -> [FeedItem] {
        grouped(items, band: band).flatMap(\.items)
    }

    nonisolated private static func leagueMetadata(for item: FeedItem) -> (key: String, meta: LeagueSpec) {
        let rawKey = (item.event?.sport ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()

        if let spec = canonicalSpecs[rawKey] {
            return (rawKey, spec)
        }

        let explicitName = item.event?.sportName?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedTitle: String = {
            if let explicitName, !explicitName.isEmpty {
                return explicitName
            }
            let display = sportDisplayName(for: rawKey)
            return display.isEmpty ? "Sports" : display
        }()

        if rawKey.hasPrefix("soccer") {
            return (rawKey, LeagueSpec(rank: 15, title: resolvedTitle, icon: "soccerball"))
        }
        if rawKey.hasPrefix("tennis_atp") {
            let title = (explicitName?.isEmpty == false) ? explicitName! : "ATP Tennis"
            return ("tennis_atp", LeagueSpec(rank: 16, title: title, icon: "figure.tennis"))
        }
        if rawKey.hasPrefix("tennis_wta") {
            let title = (explicitName?.isEmpty == false) ? explicitName! : "WTA Tennis"
            return ("tennis_wta", LeagueSpec(rank: 17, title: title, icon: "figure.tennis"))
        }
        if rawKey.hasPrefix("tennis") {
            return (rawKey, LeagueSpec(rank: 18, title: resolvedTitle, icon: "figure.tennis"))
        }
        if rawKey.hasPrefix("golf") {
            return (rawKey, LeagueSpec(rank: 19, title: resolvedTitle, icon: "figure.golf"))
        }
        if rawKey.hasPrefix("mma") {
            return (rawKey, LeagueSpec(rank: 20, title: resolvedTitle, icon: "figure.boxing"))
        }
        if rawKey.hasPrefix("boxing") {
            return (rawKey, LeagueSpec(rank: 21, title: resolvedTitle, icon: "figure.boxing"))
        }

        let groupKey = rawKey.isEmpty ? resolvedTitle.lowercased() : rawKey
        return (groupKey, LeagueSpec(rank: 100, title: resolvedTitle, icon: iconForSportKey(rawKey)))
    }

    nonisolated private static func iconForSportKey(_ key: String) -> String {
        if key.hasPrefix("basketball") { return "basketball.fill" }
        if key.hasPrefix("americanfootball") || key.hasPrefix("football") { return "football.fill" }
        if key.hasPrefix("baseball") { return "baseball.fill" }
        if key.hasPrefix("icehockey") || key.hasPrefix("hockey") { return "hockey.puck.fill" }
        if key.hasPrefix("soccer") { return "soccerball" }
        if key.hasPrefix("tennis") { return "figure.tennis" }
        if key.hasPrefix("golf") { return "figure.golf" }
        if key.hasPrefix("mma") || key.hasPrefix("boxing") { return "figure.boxing" }
        return "sportscourt"
    }

    nonisolated private static func sortItemsWithinLeague(_ items: [FeedItem], band: SportsBandKind401B) -> [FeedItem] {
        guard items.count > 1 else { return items }
        return items.enumerated().sorted { a, b in
            let lhs = a.element
            let rhs = b.element
            switch band {
            case .live, .upcoming:
                let ld = lhs.event?.commenceTime?.asDate
                let rd = rhs.event?.commenceTime?.asDate
                switch (ld, rd) {
                case let (l?, r?):
                    if l != r { return l < r }
                case (_?, nil):
                    return true
                case (nil, _?):
                    return false
                case (nil, nil):
                    break
                }
                if band == .upcoming {
                    let ltbd = lhs.event?.startIsTbd == true
                    let rtbd = rhs.event?.startIsTbd == true
                    if ltbd != rtbd { return !ltbd }
                }
            case .justHappened:
                let ld = lhs.event?.endedAt?.asDate ?? lhs.event?.commenceTime?.asDate
                let rd = rhs.event?.endedAt?.asDate ?? rhs.event?.commenceTime?.asDate
                switch (ld, rd) {
                case let (l?, r?):
                    if l != r { return l > r }
                case (_?, nil):
                    return true
                case (nil, _?):
                    return false
                case (nil, nil):
                    break
                }
            }
            return a.offset < b.offset
        }.map(\.element)
    }
}
