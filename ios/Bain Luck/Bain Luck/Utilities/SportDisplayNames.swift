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
