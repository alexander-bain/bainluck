import Foundation

/// The team page's Division Race and the Season Futures list it makes honest.
///
/// #9368 — seen on the Eagles page (2026-09-28, sim, master `40ef0bff89`):
/// Season Futures printed "NFC East Division Winner 68%" (Kalshi) directly above
/// "Pro Football: NFC East Champion 65%" (Polymarket), and further down the
/// Super Bowl three times (5.5% · 5.3% · 5.2%) under a Championship Path row that
/// already said 5%. One question, one row per source, a different number on each
/// — the blend is the product, and this was the sources shown raw.
///
/// The web page never drew those rows. `frontend/app/sport/[sport]/[league]/
/// team/[team]/page.tsx` does two things the phone did not:
///
///  1. It draws a **Division Race** from the league championship grid
///     (`lib/teamDivisionRace.ts`) — every club in the division, one blended
///     number per stage (division, playoffs, champion).
///  2. When a Championship Path is drawn, Season Futures skips market tiers
///     1/2/4 — the questions the path and the race already answer.
///
/// This is the Swift half of both. Doing only (2) would have deleted the
/// playoff and division numbers from the phone, because the phone had nowhere
/// else to show them; doing only (1) would have left every duplicate standing.
/// `TeamDivisionRaceWebParity9368Tests` reads the web files so the two cannot
/// drift apart silently.
enum TeamDivisionRace {

    /// One stage cell. The number exists only while the cell is live; a settled
    /// cell is a ✓ or ✕, never a number (settled means settled — #7522).
    struct Cell: Equatable {
        let probability: Double?
        let state: GridCellRenderState

        static let absent = Cell(probability: nil, state: .missing)

        init(probability: Double?, state: GridCellRenderState) {
            self.probability = probability
            self.state = state
        }

        init(_ cell: GridCell?) {
            guard let cell else { self = .absent; return }
            self.init(probability: cell.publishedProbability, state: cell.renderState)
        }

        /// A number or a result — what makes a column worth a header.
        var hasContent: Bool { probability != nil || state.isTerminal }

        /// Web's `progressionSortValue`: a clinched cell sorts as certainty; every
        /// cell with nothing live to say sinks together.
        var sortValue: Double {
            switch state {
            case .won: return 1
            case .eliminated, .missing, .unavailable: return -1
            case .live: return probability ?? -1
            }
        }

        /// What the cell prints: the grids' own glyphs and number formatter.
        var text: String {
            switch state {
            case .won: return "✓"
            case .eliminated: return "✕"
            case .live, .missing, .unavailable: return ladderPercent(probability)
            }
        }
    }

    struct Row: Identifiable, Equatable {
        var id: String { name }
        let name: String
        let isTeam: Bool
        let division: Cell
        let playoffs: Cell
        let championship: Cell
    }

    struct Race: Equatable {
        /// "NFC East" — the grid's own division label.
        let divisionLabel: String
        let season: String?
        /// Sorted by the championship column, the web default.
        let rows: [Row]
        let hasDivision: Bool
        let hasPlayoffs: Bool
        let hasChampionship: Bool
    }

    /// The grid keys for the three columns — `teamDivisionRace.ts`'s `cellOf` calls.
    static let divisionKey = "division"
    static let playoffsKey = "make_playoffs"
    static let championshipKey = "championship"

    /// Web's `buildDivisionRace`. Nil whenever the section cannot be shown
    /// honestly: no grid, the team is not in it, it has no division, or the
    /// division has fewer than two clubs.
    static func build(grid: ChampionshipGridResponse?, teamId: Int, teamName: String) -> Race? {
        guard let grid, !grid.teams.isEmpty,
              let me = findTeam(grid.teams, teamId: teamId, teamName: teamName),
              let division = me.division, !division.isEmpty
        else { return nil }

        // A division label is only unique inside its conference.
        let peers = grid.teams.filter {
            $0.division == division && (me.conference == nil || $0.conference == me.conference)
        }
        guard peers.count >= 2 else { return nil }

        let meNorm = normName(me.name)
        let rows = peers.map { t -> Row in
            let isTeam: Bool
            if let meId = me.teamId {
                isTeam = t.teamId == meId
            } else {
                isTeam = normName(t.name) == meNorm
            }
            return Row(
                name: t.name,
                isTeam: isTeam,
                division: Cell(t.cells[divisionKey]),
                playoffs: Cell(t.cells[playoffsKey]),
                championship: Cell(t.cells[championshipKey])
            )
        }

        let season = grid.season?.trimmingCharacters(in: .whitespaces)
        return Race(
            divisionLabel: division,
            season: (season?.isEmpty ?? true) ? nil : season,
            // Stable: equal values keep grid order, as the web sort does.
            rows: rows.enumerated()
                .sorted { a, b in
                    let (va, vb) = (a.element.championship.sortValue, b.element.championship.sortValue)
                    return va != vb ? va > vb : a.offset < b.offset
                }
                .map(\.element),
            hasDivision: rows.contains { $0.division.hasContent },
            hasPlayoffs: rows.contains { $0.playoffs.hasContent },
            hasChampionship: rows.contains { $0.championship.hasContent }
        )
    }

    /// Id first, then the normalized name — web's `findTeam`.
    private static func findTeam(_ teams: [GridTeam], teamId: Int, teamName: String) -> GridTeam? {
        if let byId = teams.first(where: { $0.teamId == teamId }) { return byId }
        let target = normName(teamName)
        return teams.first { normName($0.name) == target }
    }

    private static func normName(_ s: String) -> String {
        String(s.lowercased().unicodeScalars.filter {
            ("a"..."z").contains($0) || ("0"..."9").contains($0)
        }.map(Character.init))
    }

    // MARK: - Which grid

    /// `frontend/lib/gridSlug.ts`'s table, verbatim: grid slugs do not always
    /// match the sport-key suffix (soccer, college).
    static let gridSlugMap: [String: String] = [
        "soccer_usa_mls": "mls",
        "soccer_epl": "epl",
        "soccer_uefa_champs_league": "champions-league",
        "soccer_spain_la_liga": "la-liga",
        "soccer_germany_bundesliga": "bundesliga",
        "americanfootball_nfl": "nfl",
        "americanfootball_ncaaf": "ncaa-football",
        "basketball_nba": "nba",
        "basketball_ncaab": "ncaa-basketball",
        "basketball_wnba": "wnba",
        "icehockey_nhl": "nhl",
        "baseball_mlb": "mlb",
    ]

    static let seasonPhaseSuffixes = [
        "_preseason", "_postseason", "_regular_season", "_regular", "_playoffs", "_spring_training",
    ]

    /// Web's `sportKeyToGridSlug`: the table first, else the key minus its
    /// provider prefix ("baseball_kbo" → "kbo").
    static func gridSlug(sportKey: String?) -> String? {
        guard var key = sportKey, !key.isEmpty else { return nil }
        if let suffix = seasonPhaseSuffixes.first(where: { key.hasSuffix($0) }) {
            key = String(key.dropLast(suffix.count))
        }
        if let mapped = gridSlugMap[key] { return mapped }
        let rest = key.split(separator: "_", omittingEmptySubsequences: false).dropFirst()
            .joined(separator: "_")
        return rest.isEmpty ? key : rest
    }

    // MARK: - Season Futures

    /// The tiers the Championship Path (tier 1 and 2 stages) and the Division
    /// Race (tier 4: division, postseason) answer — web's `[1, 2, 4]`.
    static let pathTiers: Set<Int> = [1, 2, 4]

    /// Web's `propsAndAwards`: with a Championship Path drawn, the list is props,
    /// awards and other markets. Without one, nothing answers those questions
    /// elsewhere on the page, so the list stays whole.
    static func seasonFutures(_ futures: [TeamFutureItem], championshipPathDrawn: Bool) -> [TeamFutureItem] {
        guard championshipPathDrawn else { return futures }
        return futures.filter { !pathTiers.contains($0.marketTier ?? -1) }
    }
}
