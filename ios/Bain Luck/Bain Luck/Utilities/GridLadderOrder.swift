import Foundation

/// Where a championship grid's ladder order is decided.
///
/// **Why this is a type and not two closures inside the view.** The number beside
/// each ladder card is a rank a reader believes — "Seattle are the 17th likeliest" —
/// and until #6286 it was not a decision anybody had made. Two things produced it,
/// and both were invisible from the view:
///
/// 1. `LeagueGridViewModel.visibleTeams` built the unfiltered list with
///    `groupedTeams.values.flatMap`. `groupedTeams` is a `[String: [GridTeam]]`, and
///    **Swift seeds Dictionary hashing per process**, so the sequence handed to the
///    sort was in a different order on every cold launch of the app.
/// 2. The comparator was `pa > pb` with no tiebreak, so every tied team's position
///    was whatever fell out of `sorted(by:)` — which is not documented as stable.
///
/// Ties are not the edge case here, they are most of the page: on 2026-09-14 the MLB
/// grid served **8 of 30 clubs at exactly `0.001`** championship probability and 5
/// more at exactly `0.0005`, so probability alone cannot order 13 of the 30 rows.
/// Two cold launches of build 10 one minute apart, reading one cached payload,
/// rendered rank 17 as Seattle and then as Pittsburgh.
///
/// So the comparator here is a **total order**: probability, then the position the
/// server already published the team in, then the name. Given one payload it has
/// exactly one answer, and that answer is the server's own ranking — which is also
/// what the American League / National League filters show, so switching filters no
/// longer reshuffles teams that did not move.
nonisolated enum GridLadderOrder {

    /// The championship column key — the widest-net milestone (highest column `order`).
    static func championshipColumnKey(_ columns: [GridColumn]) -> String? {
        columns.max(by: { $0.order < $1.order })?.key
    }

    /// The teams a filter admits.
    ///
    /// Unfiltered, this is the server's published list. It used to be
    /// `groupedTeams.values.flatMap` — the same SET of teams in a per-process-random
    /// ORDER. `grid.teams` carries every team the grouping does, in one fixed
    /// sequence, so there was never anything to buy by reassembling it. The grouped
    /// union survives only as a fallback for a payload that sends groups and no flat
    /// list, and it walks the keys in sorted order for the same reason.
    static func visibleTeams(
        in grid: ChampionshipGridResponse,
        conferenceFilter: String?
    ) -> [GridTeam] {
        if let filter = conferenceFilter {
            if let grouped = grid.groupedTeams {
                return grouped[filter] ?? []
            }
            return grid.teams.filter { $0.conference == filter }
        }
        if grid.teams.isEmpty, let grouped = grid.groupedTeams {
            return grouped.keys.sorted().flatMap { grouped[$0] ?? [] }
        }
        return grid.teams
    }

    /// `teams` ranked by championship probability, descending, with a total order.
    ///
    /// A team with no championship cell sinks below one that has a zero, which is the
    /// existing behaviour and deliberate: "we do not carry a number for them" is not
    /// the same claim as "their chance is nil".
    static func ranked(
        _ teams: [GridTeam],
        serverTeams: [GridTeam],
        columns: [GridColumn]
    ) -> [GridTeam] {
        let key = championshipColumnKey(columns)
        var publishedPosition: [String: Int] = [:]
        for (index, team) in serverTeams.enumerated() where publishedPosition[team.name] == nil {
            publishedPosition[team.name] = index
        }
        return teams.sorted { a, b in
            let pa = key.flatMap { a.cells[$0]?.mergedProbability } ?? -1
            let pb = key.flatMap { b.cells[$0]?.mergedProbability } ?? -1
            if pa != pb { return pa > pb }
            // A team the server did not list sorts after every team it did, rather
            // than sharing position 0 with the leader.
            let ia = publishedPosition[a.name] ?? Int.max
            let ib = publishedPosition[b.name] ?? Int.max
            if ia != ib { return ia < ib }
            return a.name < b.name
        }
    }
}
