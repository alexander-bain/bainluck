import Foundation

func sportDisplayName(for key: String?) -> String {
    guard let key else { return "" }
    let map: [String: String] = [
        "americanfootball_nfl": "NFL",
        "americanfootball_ncaaf": "NCAAF",
        "basketball_nba": "NBA",
        "basketball_ncaab": "NCAAB",
        "basketball_wncaab": "WNCAAB",
        "basketball_wnba": "WNBA",
        "icehockey_nhl": "NHL",
        "baseball_mlb": "MLB",
        "soccer_epl": "EPL",
        "soccer_spain_la_liga": "La Liga",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_italy_serie_a": "Serie A",
        "soccer_france_ligue_one": "Ligue 1",
        "soccer_usa_mls": "MLS",
        "soccer_uefa_champs_league": "UCL",
        "mma_mixed_martial_arts": "MMA",
    ]
    return map[key] ?? key.components(separatedBy: "_").last?.uppercased() ?? key
}

/// Maps a raw sport-key OR llm_sport_category value to a human category label
/// for Discover card badges. NEVER leaks a raw underscore enum such as
/// "AMERICANFOOTBALL_OTHER" (the taxonomy ruling applies to native too —
/// Queue #238). Handles league keys ("americanfootball_nfl" → "NFL"), the
/// "_other" fallback keys ("americanfootball_other" → "Football"), and plain
/// Discover categories ("politics" → "Politics").
func sportCategoryDisplayName(_ raw: String?) -> String {
    guard let raw, !raw.isEmpty else { return "Market" }
    let key = raw.lowercased()

    // 1. Non-sport Discover categories (llm_sport_category values).
    let categoryMap: [String: String] = [
        "politics": "Politics", "geopolitics": "Geopolitics",
        "economics": "Economics", "tech": "Tech", "culture": "Culture",
        "entertainment": "Entertainment", "weather": "Weather",
        "health": "Health", "crypto": "Crypto", "sports": "Sports",
        "olympics": "Olympics",
    ]
    if let c = categoryMap[key] { return c }

    // 2. Known league keys → acronym (NFL, NBA, MLB, ...).
    let leagueKeys: Set<String> = [
        "americanfootball_nfl", "americanfootball_ncaaf",
        "basketball_nba", "basketball_ncaab", "basketball_wncaab",
        "basketball_wnba", "icehockey_nhl", "baseball_mlb",
        "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
        "soccer_italy_serie_a", "soccer_france_ligue_one", "soccer_usa_mls",
        "soccer_uefa_champs_league", "mma_mixed_martial_arts",
    ]
    if leagueKeys.contains(key) { return sportDisplayName(for: key) }

    // 3. Sport family (handles "_other" and bare sport families).
    let family = key.contains("_") ? String(key.split(separator: "_").first ?? "") : key
    let familyMap: [String: String] = [
        "americanfootball": "Football", "football": "Football",
        "basketball": "Basketball", "baseball": "Baseball",
        "icehockey": "Hockey", "hockey": "Hockey", "soccer": "Soccer",
        "golf": "Golf", "tennis": "Tennis", "mma": "MMA", "boxing": "Boxing",
        "cricket": "Cricket", "motorsports": "Motorsports",
        "rugbyleague": "Rugby", "rugbyunion": "Rugby", "esports": "Esports",
    ]
    if let f = familyMap[family] { return f }

    // 4. Fallback: acronym-aware title casing — never surface underscores.
    return properTitleCase(key.replacingOccurrences(of: "_", with: " "))
}

/// Maps a raw golf-tour key (as sent by the backend) to a presentable tour
/// name. Backend values arrive lower-cased with underscores (e.g.
/// "korn_ferry", "dp_world") or as short codes (e.g. "kft", "euro"). Without
/// this map they leak to users as "KORN_FERRY".
func golfTourDisplayName(for key: String?) -> String {
    guard let key, !key.isEmpty else { return "" }
    let normalized = key.lowercased()
    let map: [String: String] = [
        "pga": "PGA Tour",
        "pga_tour": "PGA Tour",
        "korn_ferry": "Korn Ferry Tour",
        "kft": "Korn Ferry Tour",
        "lpga": "LPGA Tour",
        "dp_world": "DP World Tour",
        "dpworld": "DP World Tour",
        "european": "DP World Tour",
        "euro": "DP World Tour",
        "liv": "LIV Golf",
        "champions": "PGA Tour Champions",
        "pga_champions": "PGA Tour Champions",
        "opp": "PGA Tour Americas",
        "americas": "PGA Tour Americas",
        "alt": "Alternate Events",
        "major": "Majors",
        "majors": "Majors",
        "other": "Other Events",
    ]
    if let name = map[normalized] { return name }
    // Fall back to acronym-aware title casing of the raw key so we never
    // surface "KORN_FERRY" to a user.
    return properTitleCase(normalized.replacingOccurrences(of: "_", with: " "))
}

/// Whether a sport key represents an international competition.
func isInternationalSport(_ sportKey: String?) -> Bool {
    guard let key = sportKey?.lowercased() else { return false }
    let patterns = [
        "world_cup",
        "olympics",
        "euros",
        "nations_league",
        "copa_america",
        "asian_cup",
        "africa_cup",
        "international",
    ]
    return patterns.contains(where: { key.contains($0) })
}
