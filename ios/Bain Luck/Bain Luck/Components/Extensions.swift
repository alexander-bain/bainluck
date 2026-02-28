import SwiftUI

// MARK: - Color Hex Init

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var rgb: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }

    /// Returns a lighter version (for backgrounds).
    func lightened(_ amount: Double = 0.3) -> Color {
        // Decompose via resolved color values
        let resolved = self.resolve(in: EnvironmentValues())
        let r = Double(resolved.red)
        let g = Double(resolved.green)
        let b = Double(resolved.blue)
        return Color(
            red: min(r + amount * (1 - r), 1),
            green: min(g + amount * (1 - g), 1),
            blue: min(b + amount * (1 - b), 1)
        )
    }

    // Cross-platform system background colors (replace UIKit-only UIColor.systemGrayN)
    static let cardBackground = Color(white: 0.95).opacity(0.6)
    static let cardBackgroundDark = Color(white: 0.90).opacity(0.6)
    static let barTrack = Color(white: 0.82)
}

// MARK: - Probability Formatting

func formatProbability(_ value: Double) -> String {
    let pct = value * 100
    if pct < 1 { return "<1%" }
    if pct > 99 { return ">99%" }
    return "\(Int(pct.rounded()))%"
}

// MARK: - Sport Display Name

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
