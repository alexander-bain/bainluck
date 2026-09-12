import Foundation

/// The league acronyms this app spells for itself, keyed by sport key. ONE
/// copy: both public formatters below read it, and neither keeps its own.
private let leagueAcronyms: [String: String] = [
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

/// A sport key as a league label: "baseball_mlb" → "MLB".
///
/// #5780 — the fallback used to be `key.components(separatedBy: "_").last?
/// .uppercased()`, which keeps the LAST token of a key and shouts it. Every key
/// outside the sixteen above therefore reached a reader as a fragment:
/// `tennis_atp_us_open` → **"OPEN"**, `soccer_spain_segunda_division` →
/// **"DIVISION"**, `icehockey_sweden_hockey_league` → **"LEAGUE"**. Search's
/// own event rows are the proof — six Alcaraz matches on production, five of
/// them labelled "OPEN" under a filter pill reading "ATP US Open"
/// (`artifacts-native-020/n138-BEFORE-alcaraz.png`, 2026-09-12).
///
/// Unknown keys now go to `sportCategoryDisplayName`, the shared rule #5723
/// made single-source, which answers with a sport rather than a fragment. The
/// two functions cannot recurse: the league map is consulted directly by both,
/// and the shared rule never calls back here.
func sportDisplayName(for key: String?) -> String {
    guard let key, !key.isEmpty else { return "" }
    if let name = leagueAcronyms[key] { return name }
    return sportCategoryDisplayName(key)
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

    // 2. Known league keys → acronym (NFL, NBA, MLB, ...). Read straight from
    //    the one map (#5780): this used to call `sportDisplayName(for:)`, and a
    //    second copy of the same sixteen keys decided whether it did.
    if let acronym = leagueAcronyms[key] { return acronym }

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

    // 4. Fallback: acronym-aware title casing of a raw key — never surface an
    //    underscore, and never hand back a lowercase label.
    //
    //    #5723: this arm used `properTitleCase`, which is the wrong one of this
    //    file's two acronym-aware formatters. `properTitleCase` only *repairs*
    //    acronyms inside an already-cased display string and deliberately
    //    leaves words it does not recognise untouched, so a raw key arrived
    //    here lowercase and left lowercase — "table tennis", "rugby", "other".
    //    `toTitleCaseAcronymSafe` is the one that owns the "raw lowercase key
    //    -> title" job, and says so in its own docstring. 4,351 of the 43,632
    //    categorised open futures markets reach this arm (production db-query,
    //    2026-09-12); the largest are table_tennis (2,635) and other (1,467).
    return toTitleCaseAcronymSafe(key)
}

/// The label for a sport KEY on a row that names a TEAM rather than a market —
/// search's Teams rows today.
///
/// #5780: that row shortened the key itself, `key.split("_").dropFirst()
/// .joined(" ").uppercased()`, so a reader met the raw enum with the family
/// filed off and the rest shouted: `baseball_milb` → "MILB" one line under a
/// filter pill reading "MiLB", `icehockey_sweden_hockey_league` → "SWEDEN
/// HOCKEY LEAGUE" where the server calls it "SHL", `mma_mixed_martial_arts`
/// (1,233 teams, the largest group in the table) → "MIXED MARTIAL ARTS", and
/// `tennis_atp_queens_club_champ` → "ATP QUEENS CLUB CHAMP", a truncation that
/// only ever existed to fit a database column.
///
/// The server already answers this: every row of `sports` carries a display
/// `name` ("MiLB", "SHL", "ATP Queen's Club Championships"), and the search
/// payload hands the app the ones its results touch in the same `sports` facet
/// the filter pills are built from. So the rule is: the served name when the
/// page has it, otherwise the app's own shared rule — never a shortened key.
///
/// The fallback is `sportCategoryDisplayName`, deliberately, and not a fifth
/// private formatter (#5723's whole finding was that this label had been
/// written four times). It answers coarser than the facet does —
/// `cricket_t20_blast` → "Cricket", not "T20 Blast" — and coarse is the right
/// trade here: the facet is missing exactly when no result on the page is in
/// that sport, which is when "which sport is this club?" is the reader's
/// question and the tour name is not.
func sportKeyDisplayName(_ key: String?, facets: [SportFacet]) -> String? {
    guard let key, !key.isEmpty else { return nil }
    if let served = facets.first(where: { $0.key == key })?.name,
       !served.trimmingCharacters(in: .whitespaces).isEmpty {
        // Through the house acronym repair on the way out: the server titles
        // `tennis_atp` as "Tennis Atp", and the row used to print the key's
        // last token, "ATP". Trading a correct acronym for a garbled one would
        // be a regression the pill agreement hides. `properTitleCase` only
        // REPAIRS words it recognises and leaves the rest alone, so "MiLB",
        // "SHL" and "ATP Queen's Club Championships" pass through untouched.
        return properTitleCase(served)
    }
    return sportCategoryDisplayName(key)
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

/// SF Symbol for a full sport KEY (`"tennis_atp_us_open"`, `"basketball_nba"`),
/// matched on the family prefix.
///
/// Search's filter row used to carry a hand-written list of seven families and
/// send the family token as the API's `sport` parameter — but that parameter is
/// an exact `Sport.key` match, so every one of those pills returned nothing
/// (measured 2026-09-03: `?q=lakers` → 5 NBA hits, `?q=lakers&sport=basketball`
/// → 0). The row is now built from the server's own `sports` facet, which speaks
/// exact keys, and needs an icon for a key rather than for a family.
func sportSymbolName(forSportKey key: String) -> String {
    let lowered = key.lowercased()
    let symbols: [(prefix: String, symbol: String)] = [
        ("basketball", "basketball.fill"),
        ("americanfootball", "football.fill"),
        ("baseball", "baseball.fill"),
        ("icehockey", "hockey.puck.fill"),
        ("soccer", "soccerball"),
        ("golf", "figure.golf"),
        ("tennis", "figure.tennis"),
        ("mma", "figure.boxing"),
        ("boxing", "figure.boxing"),
        ("cricket", "figure.cricket"),
        ("rugby", "figure.rugby"),
        ("motorsports", "flag.checkered"),
        ("aussierules", "figure.australian.football"),
        ("lacrosse", "figure.lacrosse"),
    ]
    for entry in symbols where lowered.hasPrefix(entry.prefix) { return entry.symbol }
    return "sportscourt"
}
