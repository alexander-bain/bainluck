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
