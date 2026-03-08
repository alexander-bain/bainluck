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

    // System-adaptive colors (light + dark mode)
    static let cardBackground = Color(.secondarySystemGroupedBackground)
    static let cardBackgroundDark = Color(.tertiarySystemGroupedBackground)
    static let barTrack = Color(.separator)
    static let heroDarkBackground = Color(red: 0.035, green: 0.035, blue: 0.043) // #09090b
}

// MARK: - Probability Formatting

func formatProbability(_ value: Double) -> String {
    let pct = value * 100
    if pct < 1 { return "<1%" }
    if pct > 99 { return ">99%" }
    return "\(Int(pct.rounded()))%"
}

// MARK: - Countdown Formatting

/// Format a future date as a compact countdown: "2h 15m", "35m", "3d 5h".
func formatCountdown(from date: Date) -> String? {
    let interval = date.timeIntervalSinceNow
    guard interval > 0 else { return nil }

    let totalMinutes = Int(interval / 60)
    let days = totalMinutes / 1440
    let hours = (totalMinutes % 1440) / 60
    let minutes = totalMinutes % 60

    if days > 0 {
        return hours > 0 ? "\(days)d \(hours)h" : "\(days)d"
    } else if hours > 0 {
        return minutes > 0 ? "\(hours)h \(minutes)m" : "\(hours)h"
    } else if minutes > 0 {
        return "\(minutes)m"
    } else {
        return "<1m"
    }
}

// MARK: - Moneyline → Probability

/// Convert an American moneyline to implied probability (0.0–1.0).
func moneylineToProbability(_ ml: Int) -> Double {
    if ml > 0 {
        return 100.0 / Double(ml + 100)
    } else {
        let abs = Double(abs(ml))
        return abs / (abs + 100.0)
    }
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

// MARK: - International Flags

/// Whether a sport key represents an international competition (World Cup, Olympics, etc.).
func isInternationalSport(_ sportKey: String?) -> Bool {
    guard let key = sportKey?.lowercased() else { return false }
    let patterns = ["world_cup", "olympics", "euros", "nations_league", "copa_america",
                    "asian_cup", "africa_cup", "international"]
    return patterns.contains(where: { key.contains($0) })
}

/// Country/region name → ISO 3166-1 alpha-2 code for flagcdn.com.
private let countryCodes: [String: String] = [
    "united states": "us", "usa": "us", "america": "us",
    "canada": "ca", "mexico": "mx", "brazil": "br", "argentina": "ar",
    "colombia": "co", "chile": "cl", "uruguay": "uy", "paraguay": "py",
    "peru": "pe", "ecuador": "ec", "venezuela": "ve", "costa rica": "cr",
    "jamaica": "jm", "panama": "pa", "honduras": "hn",
    "england": "gb-eng", "united kingdom": "gb", "scotland": "gb-sct",
    "wales": "gb-wls", "france": "fr", "germany": "de", "spain": "es",
    "italy": "it", "netherlands": "nl", "holland": "nl", "belgium": "be",
    "portugal": "pt", "switzerland": "ch", "austria": "at", "sweden": "se",
    "norway": "no", "denmark": "dk", "finland": "fi", "poland": "pl",
    "croatia": "hr", "serbia": "rs", "greece": "gr", "turkey": "tr",
    "ukraine": "ua", "romania": "ro", "hungary": "hu", "ireland": "ie",
    "japan": "jp", "south korea": "kr", "korea": "kr", "china": "cn",
    "india": "in", "australia": "au", "new zealand": "nz",
    "saudi arabia": "sa", "iran": "ir", "qatar": "qa",
    "nigeria": "ng", "south africa": "za", "egypt": "eg", "ghana": "gh",
    "senegal": "sn", "cameroon": "cm", "morocco": "ma", "tunisia": "tn",
]

/// Returns a flag image URL from flagcdn.com for a country/team name, or nil if not found.
func flagURL(for name: String, width: Int = 80) -> String? {
    let key = name.lowercased().trimmingCharacters(in: .whitespaces)
    guard let code = countryCodes[key] else { return nil }
    return "https://flagcdn.com/w\(width)/\(code).png"
}

// MARK: - Flow Layout (wrapping horizontal layout)

/// A layout that arranges views horizontally, wrapping to the next line when needed.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        var height: CGFloat = 0
        for (i, row) in rows.enumerated() {
            let maxH = row.map { $0.sizeThatFits(.unspecified).height }.max() ?? 0
            height += maxH
            if i > 0 { height += spacing }
        }
        return CGSize(width: proposal.width ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        var y = bounds.minY
        for (i, row) in rows.enumerated() {
            if i > 0 { y += spacing }
            var x = bounds.minX
            let maxH = row.map { $0.sizeThatFits(.unspecified).height }.max() ?? 0
            for subview in row {
                let size = subview.sizeThatFits(.unspecified)
                subview.place(at: CGPoint(x: x, y: y + (maxH - size.height) / 2), proposal: .unspecified)
                x += size.width + spacing
            }
            y += maxH
        }
    }

    private func computeRows(proposal: ProposedViewSize, subviews: Subviews) -> [[LayoutSubviews.Element]] {
        let maxWidth = proposal.width ?? .infinity
        var rows: [[LayoutSubviews.Element]] = [[]]
        var currentWidth: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if currentWidth + size.width > maxWidth, !rows[rows.count - 1].isEmpty {
                rows.append([])
                currentWidth = 0
            }
            rows[rows.count - 1].append(subview)
            currentWidth += size.width + spacing
        }
        return rows
    }
}
