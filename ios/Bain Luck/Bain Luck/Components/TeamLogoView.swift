import SwiftUI

/// Async team logo image with cached loading, ESPN fallback, flag fallback, and colored-initial fallback.
struct TeamLogoView: View {
    let url: String?
    let teamName: String
    let color: Color
    var size: CGFloat = 28
    /// Optional sport key for ESPN logo fallback (e.g., "basketball_nba")
    var sportKey: String? = nil
    /// Whether `url` is a PHOTOGRAPH OF A PERSON rather than a crest or a flag
    /// (#2919 native half). A crest is transparent art that must be shown whole,
    /// so it fits; a portrait head-and-shoulders shot fitted into a square slot
    /// becomes a letterboxed sliver, so it fills and is cropped square. Defaults
    /// to false, which is every existing call site unchanged.
    var isPhotograph: Bool = false
    /// The OTHER competitor of this matchup, where the caller draws both circles
    /// at once (#4720). Supplying it is what lets the badge grow off a word the
    /// two sides share — see `badge(teamName:opponentName:)`. Defaults to nil,
    /// which is every one-circle surface unchanged.
    var opponentName: String? = nil

    @State private var image: PlatformImage?
    @State private var loadFailed = false
    @State private var triedEspnFallback = false

    /// Resolve URL: primary url → flag (international) → ESPN fallback → nil.
    ///
    /// #2977: these rungs moved to `TeamAvatarLadder` unchanged, so the Discover
    /// hero and the guess card climb the same ones instead of each stopping at the
    /// first. This view is where the ladder came from; its behaviour is identical.
    private var resolvedURL: String? {
        teamAvatarURL(servedURL: url, teamName: teamName, sportKey: sportKey)
    }

    var body: some View {
        Group {
            if let image {
                if isPhotograph {
                    Image(platformImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: size, height: size)
                        .clipShape(RoundedRectangle(cornerRadius: size * 0.22, style: .continuous))
                } else {
                    Image(platformImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: size, height: size)
                }
            } else if loadFailed && triedEspnFallback {
                initialsFallback
            } else if resolvedURL == nil {
                initialsFallback
            } else {
                Circle()
                    .fill(color.opacity(0.15))
                    .frame(width: size, height: size)
            }
        }
        .task(id: resolvedURL) {
            guard let urlStr = resolvedURL, let imageURL = URL(string: urlStr) else {
                loadFailed = true
                triedEspnFallback = true
                return
            }
            image = await ImageCache.shared.image(for: imageURL)
            if image == nil {
                // If primary URL failed, try ESPN fallback
                if !triedEspnFallback, url != nil, let espnURL = espnTeamLogoURL(for: teamName),
                   let espnImageURL = URL(string: espnURL) {
                    triedEspnFallback = true
                    image = await ImageCache.shared.image(for: espnImageURL)
                }
                if image == nil {
                    loadFailed = true
                    triedEspnFallback = true
                }
            }
        }
    }

    /// The letters this circle falls back to when no logo, flag or portrait
    /// exists.
    ///
    /// #4720. This view drew `String(teamName.prefix(1))` — ONE character of the
    /// RAW name, never routed through `TeamShortName`. It was a fourth hand-rolled
    /// spelling of the shorten-a-name rule on this target, the class #3374 removed
    /// and `teamShortNameSingleSource.test.ts` exists to discover; it was not
    /// discovered because that guard looked for re-implementations of the LAST-WORD
    /// rule and this one is a first-character rule. The guard now looks for both.
    ///
    /// Measured over the COMPLETE population of distinct (away, home) name pairs on
    /// events in the last 45 days — 24,066 pairs, 14,025 distinct names, pulled in
    /// hash chunks past the 1,000-row cap and reconciled against its own `COUNT(*)`
    /// (2026-09-10) — one character is not a name:
    ///
    ///     both circles draw the SAME glyph   2,238 pairs (9.3%)  ->  67 (0.3%)
    ///     first glyph is not even a LETTER      42 names         ->  28
    ///     name opens with a club designator    716 names, 657 of which move off it
    ///
    /// "1. FC Heidenheim 1846" drew **`1`**, "FC Schalke 04" drew **`F`**, and the
    /// doubles pair "Behar / Romboli" drew **`B`** on the event hero — a page whose
    /// job is to tell two competitors apart (#3430's complaint, one component over).
    /// They now draw `HEI`, `SCH` and `BEH`.
    ///
    /// WHY THE OPPONENT IS AN ARGUMENT. `abbreviation` alone judges one name in
    /// isolation, and #3430's whole finding is that the failure is collision INSIDE
    /// one matchup: on the same population the solo rule leaves 120 colliding pairs
    /// and, worse, BREAKS 75 that discriminate today — "Clemson Tigers v LSU Tigers"
    /// draws `C`/`L` now and would draw `TIG`/`TIG`. Handing in the other side routes
    /// through `abbreviationPair`, whose growth repairs exactly that: 120 -> 67
    /// collisions and 75 -> 31 broken. The 31 that remain are esports sides whose
    /// distinctive token is the word "Esports" ("DMG Esports" v "Volda E-Sport" ->
    /// `ESP`/`ESP`); that is a pre-existing weakness of `abbreviationPair` which the
    /// Discover card already draws today, so this view adopting the same rule makes
    /// the app agree with itself rather than introducing it. Filed as #4756.
    ///
    /// Static, and not a `private var` on the view, so the suite can run the
    /// PRODUCTION path rather than a paraphrase of it — `@testable import` does not
    /// reach `private`, and a rule restated in a test is the second copy this file
    /// was just cured of.
    static func badge(teamName: String, opponentName: String?) -> String {
        guard let opponentName, !opponentName.isEmpty, opponentName != teamName else {
            return TeamShortName.abbreviation(teamName)
        }
        return TeamShortName.abbreviationPair(away: teamName, home: opponentName).away
    }

    private var initialsFallback: some View {
        ZStack {
            Circle()
                .fill(color.opacity(0.2))
            // Three glyphs where one used to sit, at every size this view is drawn
            // (18 on a leaderboard row, 80 on the iPad hero). The width frame is the
            // chord the circle can actually hold, so `minimumScaleFactor` shrinks a
            // wide trio to fit instead of truncating it to "BE…" — a badge that
            // ellipsises is worse than the letter it replaced.
            Text(Self.badge(teamName: teamName, opponentName: opponentName))
                .font(.system(size: size * 0.40, weight: .bold))
                .lineLimit(1)
                .minimumScaleFactor(0.45)
                .frame(width: size * 0.82)
                .foregroundStyle(color)
        }
        .frame(width: size, height: size)
    }
}

// MARK: - ESPN Team Logo Lookup

/// Known ESPN team IDs for major North American teams.
private let espnTeamIDs: [String: (id: String, sport: String)] = [
    // NBA
    "atlanta hawks": ("1", "nba"),
    "boston celtics": ("2", "nba"),
    "brooklyn nets": ("17", "nba"),
    "charlotte hornets": ("30", "nba"),
    "chicago bulls": ("4", "nba"),
    "cleveland cavaliers": ("5", "nba"),
    "dallas mavericks": ("6", "nba"),
    "denver nuggets": ("7", "nba"),
    "detroit pistons": ("8", "nba"),
    "golden state warriors": ("9", "nba"),
    "houston rockets": ("10", "nba"),
    "indiana pacers": ("11", "nba"),
    "los angeles clippers": ("12", "nba"),
    "los angeles lakers": ("13", "nba"),
    "memphis grizzlies": ("29", "nba"),
    "miami heat": ("14", "nba"),
    "milwaukee bucks": ("15", "nba"),
    "minnesota timberwolves": ("16", "nba"),
    "new orleans pelicans": ("3", "nba"),
    "new york knicks": ("18", "nba"),
    "oklahoma city thunder": ("25", "nba"),
    "orlando magic": ("19", "nba"),
    "philadelphia 76ers": ("20", "nba"),
    "phoenix suns": ("21", "nba"),
    "portland trail blazers": ("22", "nba"),
    "sacramento kings": ("23", "nba"),
    "san antonio spurs": ("24", "nba"),
    "toronto raptors": ("28", "nba"),
    "utah jazz": ("26", "nba"),
    "washington wizards": ("27", "nba"),
    // NFL
    "arizona cardinals": ("22", "nfl"),
    "atlanta falcons": ("1", "nfl"),
    "baltimore ravens": ("33", "nfl"),
    "buffalo bills": ("2", "nfl"),
    "carolina panthers": ("29", "nfl"),
    "chicago bears": ("3", "nfl"),
    "cincinnati bengals": ("4", "nfl"),
    "cleveland browns": ("5", "nfl"),
    "dallas cowboys": ("6", "nfl"),
    "denver broncos": ("7", "nfl"),
    "detroit lions": ("8", "nfl"),
    "green bay packers": ("9", "nfl"),
    "houston texans": ("34", "nfl"),
    "indianapolis colts": ("11", "nfl"),
    "jacksonville jaguars": ("30", "nfl"),
    "kansas city chiefs": ("12", "nfl"),
    "las vegas raiders": ("13", "nfl"),
    "los angeles chargers": ("24", "nfl"),
    "los angeles rams": ("14", "nfl"),
    "miami dolphins": ("15", "nfl"),
    "minnesota vikings": ("16", "nfl"),
    "new england patriots": ("17", "nfl"),
    "new orleans saints": ("18", "nfl"),
    "new york giants": ("19", "nfl"),
    "new york jets": ("20", "nfl"),
    "philadelphia eagles": ("21", "nfl"),
    "pittsburgh steelers": ("23", "nfl"),
    "san francisco 49ers": ("25", "nfl"),
    "seattle seahawks": ("26", "nfl"),
    "tampa bay buccaneers": ("27", "nfl"),
    "tennessee titans": ("10", "nfl"),
    "washington commanders": ("28", "nfl"),
    // MLB
    "arizona diamondbacks": ("29", "mlb"),
    "atlanta braves": ("15", "mlb"),
    // The A's dropped the city. `teams.name` now serves "Athletics", which matched
    // nothing, so both the Sports row and the Discover hero drew a letter "A" for
    // a club ESPN still publishes at the same id (verified 200, 40x40 PNG,
    // 2026-09-08). Photographed on the Sports row in
    // `artifacts-native-067/AFTER-sports-tab.png`; the Oakland spelling stays for
    // rows that still carry it.
    "athletics": ("11", "mlb"),
    "baltimore orioles": ("1", "mlb"),
    "boston red sox": ("2", "mlb"),
    "chicago cubs": ("16", "mlb"),
    "chicago white sox": ("4", "mlb"),
    "cincinnati reds": ("17", "mlb"),
    "cleveland guardians": ("5", "mlb"),
    "colorado rockies": ("27", "mlb"),
    "detroit tigers": ("6", "mlb"),
    "houston astros": ("18", "mlb"),
    "kansas city royals": ("7", "mlb"),
    "los angeles angels": ("3", "mlb"),
    "los angeles dodgers": ("19", "mlb"),
    "miami marlins": ("28", "mlb"),
    "milwaukee brewers": ("8", "mlb"),
    "minnesota twins": ("9", "mlb"),
    "new york mets": ("21", "mlb"),
    "new york yankees": ("10", "mlb"),
    "oakland athletics": ("11", "mlb"),
    "philadelphia phillies": ("22", "mlb"),
    "pittsburgh pirates": ("23", "mlb"),
    "san diego padres": ("25", "mlb"),
    "san francisco giants": ("26", "mlb"),
    "seattle mariners": ("12", "mlb"),
    "st. louis cardinals": ("24", "mlb"),
    "tampa bay rays": ("30", "mlb"),
    "texas rangers": ("13", "mlb"),
    "toronto blue jays": ("14", "mlb"),
    "washington nationals": ("20", "mlb"),
    // NHL
    "anaheim ducks": ("25", "nhl"),
    "boston bruins": ("1", "nhl"),
    "buffalo sabres": ("2", "nhl"),
    "calgary flames": ("20", "nhl"),
    "carolina hurricanes": ("7", "nhl"),
    "chicago blackhawks": ("4", "nhl"),
    "colorado avalanche": ("17", "nhl"),
    "columbus blue jackets": ("29", "nhl"),
    "dallas stars": ("9", "nhl"),
    "detroit red wings": ("5", "nhl"),
    "edmonton oilers": ("22", "nhl"),
    "florida panthers": ("13", "nhl"),
    "los angeles kings": ("26", "nhl"),
    "minnesota wild": ("30", "nhl"),
    "montreal canadiens": ("8", "nhl"),
    "nashville predators": ("18", "nhl"),
    "new jersey devils": ("1", "nhl"),
    "new york islanders": ("2", "nhl"),
    "new york rangers": ("3", "nhl"),
    "ottawa senators": ("9", "nhl"),
    "philadelphia flyers": ("4", "nhl"),
    "pittsburgh penguins": ("5", "nhl"),
    "san jose sharks": ("28", "nhl"),
    "seattle kraken": ("55", "nhl"),
    "st. louis blues": ("19", "nhl"),
    "tampa bay lightning": ("14", "nhl"),
    "toronto maple leafs": ("10", "nhl"),
    "utah hockey club": ("56", "nhl"),
    "vancouver canucks": ("23", "nhl"),
    "vegas golden knights": ("54", "nhl"),
    "washington capitals": ("15", "nhl"),
    "winnipeg jets": ("52", "nhl"),
]

/// Returns ESPN team logo URL for a given team name, or nil if not found.
func espnTeamLogoURL(for teamName: String) -> String? {
    let key = teamName.lowercased().trimmingCharacters(in: .whitespaces)
    guard let entry = espnTeamIDs[key] else { return nil }
    return "https://a.espncdn.com/combiner/i?img=/i/teamlogos/\(entry.sport)/500/\(entry.id).png&w=40&h=40&transparent=true"
}
