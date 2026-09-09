import Foundation

/// The one place the app turns a backend source key into a word a reader sees.
///
/// 🔴 WHY THIS IS A NAMESPACE AND NOT A FIFTH COPY OF THE SAME SWITCH (#4135).
/// Five surfaces each carried their own `switch source` ending
/// `default: source.capitalized`, so `datagolf` — a first-class production source
/// (measured 2026-09-08: polymarket 693,368 · kalshi 294,987 · datagolf 345 ·
/// odds_api 12) — printed "Datagolf" on four of them while `LeagueGridView`'s
/// dictionary got it right. The defect that outlives the key is the passthrough
/// itself: whatever source the backend adds next reaches the screen raw, and a
/// `books` source would print "Books" on four surfaces with no code change
/// (standing notice 33).
///
/// ✅ SO THE UNKNOWN-KEY BRANCH FAILS QUIET. `label(for:)` returns nil for a key
/// the app cannot name, and every call site renders nothing rather than the raw
/// string — the same allowlist discipline `WinProbSourceCatalog` already applies
/// to `win_probability_sources`. A key the app cannot name is a key the app does
/// not print.
enum SourceLabels {
    /// Market-level sources — `futures_markets.source`.
    private static let marketSourceNames: [String: String] = [
        "odds_api": "Sportsbooks",
        "kalshi": "Kalshi",
        "polymarket": "Polymarket",
        "datagolf": "DataGolf",
    ]

    /// The reader-facing name for a market source, or nil if the app cannot name
    /// it. Callers drop the badge on nil; they never fall back to the raw key.
    static func label(for source: String?) -> String? {
        guard let source, !source.isEmpty else { return nil }
        return marketSourceNames[source]
    }

    // MARK: - Contributors (the `bookmakers` array on a futures detail payload)

    /// Outcome-level contributors that really are sportsbooks. This set, and
    /// nothing else, earns the noun "sportsbook".
    private static let sportsbookNames: [String: String] = [
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
        "lowvig": "LowVig",
        "superbook": "SuperBook",
        "williamhill_us": "Caesars",
        "fliff": "Fliff",
        "hardrockbet": "Hard Rock",
    ]

    /// Contributors that are NOT sportsbooks. DataGolf is a statistical model;
    /// counting it as a sportsbook is the TRUTH defect #4135 was filed for — the
    /// card said "Probabilities from 1 sportsbook" two lines above a chip reading
    /// "Datagolf Model", contradicting itself about where a number came from.
    private static let modelNames: [String: String] = [
        "datagolf_model": "the DataGolf model",
    ]

    /// Whether a contributor key is a sportsbook the app can name.
    static func isSportsbook(_ key: String) -> Bool {
        sportsbookNames[key] != nil
    }

    /// The named sportsbook chips for a contributor list, in payload order.
    /// Unnameable keys are dropped rather than title-cased onto the screen, and
    /// they are dropped from `attribution(for:)`'s count too, so the sentence and
    /// the chips can never disagree about how many there are.
    static func sportsbookChips(for keys: [String]) -> [String] {
        keys.compactMap { sportsbookNames[$0] }
    }

    /// The one line above the contributor chips, or nil when there is nothing the
    /// app can honestly say. The noun follows what the sources actually ARE:
    /// sportsbooks are counted, everything else is named.
    ///
    ///     ["datagolf_model"]            → "Probabilities from the DataGolf model"
    ///     ["draftkings", "fanduel"]     → "Probabilities from 2 sportsbooks"
    ///     ["datagolf_model", "fanduel"] → "Probabilities from the DataGolf model and 1 sportsbook"
    static func attribution(for keys: [String]) -> String? {
        let models = keys.compactMap { modelNames[$0] }
        let bookCount = keys.filter(isSportsbook).count

        var parts: [String] = []
        if !models.isEmpty { parts.append(models.joined(separator: ", ")) }
        if bookCount > 0 {
            parts.append("\(bookCount) sportsbook\(bookCount == 1 ? "" : "s")")
        }
        guard !parts.isEmpty else { return nil }
        return "Probabilities from " + parts.joined(separator: " and ")
    }
}
