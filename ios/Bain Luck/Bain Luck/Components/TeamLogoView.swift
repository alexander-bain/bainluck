import SwiftUI

/// Async team logo image with cached loading, ESPN fallback, and colored-initial fallback.
struct TeamLogoView: View {
    let url: String?
    let teamName: String
    let color: Color
    var size: CGFloat = 28
    /// Optional sport key for ESPN logo fallback (e.g., "basketball_nba")
    var sportKey: String? = nil

    @State private var image: UIImage?
    @State private var loadFailed = false
    @State private var triedEspnFallback = false

    /// Resolve URL: primary url → ESPN fallback → nil
    private var resolvedURL: String? {
        if let url, !url.isEmpty { return url }
        return espnTeamLogoURL(for: teamName)
    }

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size, height: size)
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

    private var initialsFallback: some View {
        ZStack {
            Circle()
                .fill(color.opacity(0.2))
            Text(String(teamName.prefix(1)).uppercased())
                .font(.system(size: size * 0.45, weight: .bold))
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
