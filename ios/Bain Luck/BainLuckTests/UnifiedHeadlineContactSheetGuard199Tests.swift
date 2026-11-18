import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Direction 199, Item 6 — Unified Headline Contact-Sheet Guard:
///
/// Draws every sport × state × size onto one `390 px` contact sheet and fails if:
/// (a) any sport/state/edge case is not rendered on the single component (`EventSportHeadlineCard12472`),
/// (b) any headline prints `"opening"`, `"opened"`, `"stale"`, `"Current win chance"`, or `"Projection before"`
///     (or `"Settled"` / `"3 venues"`),
/// (c) any alphabetic label appears twice in one headline, or
/// (d) the grey pregame line (`headline-12472-pregame-summary`) wraps to more than one line or holds anything
///     beyond the two pregame facts (`"Pregame  <Fav> <X>% · projected <A>–<B>"` and its half-omitted subsets).
@MainActor
final class UnifiedHeadlineContactSheetGuard199Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T19:15:00Z")!

    private struct Specimen {
        let title: String
        let event: EventDetail
        var liveStatusText: String? = nil
        var hasScore: Bool = false
        var numberStreams: Bool = false
        var ladderHome: Double? = nil
        var ladderAway: Double? = nil
        var gameMarkets: GameMarketsResponse? = nil
    }

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func collectVisibleLabels(in view: UIView) -> [UILabel] {
        guard !view.isHidden, view.alpha > 0.01 else { return [] }
        var found: [UILabel] = []
        if let label = view as? UILabel,
           let text = label.text?.trimmingCharacters(in: .whitespacesAndNewlines),
           !text.isEmpty {
            found.append(label)
        }
        for sub in view.subviews {
            found.append(contentsOf: collectVisibleLabels(in: sub))
        }
        return found
    }

    private func containsAccessibilityIdentifier(_ id: String, in view: UIView) -> Bool {
        if view.accessibilityIdentifier == id { return true }
        for sub in view.subviews {
            if containsAccessibilityIdentifier(id, in: sub) { return true }
        }
        return false
    }

    private func findSubtree(withIdentifier id: String, in view: UIView) -> UIView? {
        if view.accessibilityIdentifier == id { return view }
        for sub in view.subviews {
            if let hit = findSubtree(withIdentifier: id, in: sub) { return hit }
        }
        return nil
    }

    private func allVisibleTextElements(for model: EventSportHeadlines12472.Model) -> [String] {
        var elements: [String] = []
        switch model.kind.phase {
        case .before, .after:
            if let meta = model.plainMetaText, !meta.isEmpty {
                elements.append(meta)
            }
        case .during:
            if let badge = model.liveBadgeText, !badge.isEmpty {
                elements.append(badge)
                if let league = model.leagueLabel, !league.isEmpty {
                    elements.append(league)
                }
            } else if let plain = model.plainMetaText, !plain.isEmpty {
                elements.append(plain)
            }
        }
        elements.append(contentsOf: model.columns.map(\.header).filter { !$0.isEmpty })
        for row in model.rows {
            if !row.shortName.isEmpty {
                elements.append(row.shortName)
            }
            if let rec = row.record, !rec.isEmpty {
                elements.append(rec)
            }
            for cell in row.cells where !cell.isEmpty {
                elements.append(cell)
            }
        }
        if let summary = model.livePregameSummary {
            elements.append(summary.leadWord)
            elements.append(summary.bodyText)
        }
        return elements
    }

    /// Pure numeric / percent / record / dash values (e.g. `"0"`, `"6"`, `"50%"`, `"1-0"`, `"—"`)
    /// may legitimately match across two competitors; alphabetic labels (`"Score"`, `"Proj."`,
    /// `"Now"`, `"Chance"`, `"Pregame"`, `"Final"`, `"Draw"`, team names, etc.) must NEVER
    /// appear twice in one headline.
    private func isAlphabeticLabel(_ text: String) -> Bool {
        let hasLetter = text.unicodeScalars.contains { CharacterSet.letters.contains($0) }
        guard hasLetter else { return false }
        // Tennis advantage point `"Ad"` can only occur on one player at a time, so even `"Ad"` is unique.
        return true
    }

    // MARK: - Fixture Builders Across Every Sport × State + All 23 Former `nil` Cases

    private func buildAllSpecimens() throws -> [Specimen] {
        var list: [Specimen] = []

        func standardTrio(
            label: String,
            sport: String,
            league: String,
            away: String,
            home: String,
            awayPrimary: String,
            awaySecondary: String? = nil,
            homePrimary: String,
            awayRecord: String? = "6-3",
            homeRecord: String? = "7-2",
            preAwayProb: Double = 0.42,
            preHomeProb: Double = 0.58,
            liveAwayProb: Double = 0.364,
            liveHomeProb: Double = 0.636,
            awayScore: Int? = 21,
            homeScore: Int? = 24,
            projAway: Double? = 24.0,
            projHome: Double? = 28.0,
            unit: String = "points",
            period: String = "full_game",
            livePeriod: String = "3rd Quarter",
            liveClock: String = "6:12",
            awayLogo: String? = nil,
            homeLogo: String? = nil
        ) throws {
            let awaySecJSON = awaySecondary.map { ", \"secondary_color\": \"\($0)\"" } ?? ""
            let awayLogoJSON = awayLogo.map { ", \"logo_small\": \"\($0)\"" } ?? ""
            let homeLogoJSON = homeLogo.map { ", \"logo_small\": \"\($0)\"" } ?? ""
            let recAwayJSON = awayRecord.map { "\"record\": \"\($0)\"," } ?? ""
            let recHomeJSON = homeRecord.map { "\"record\": \"\($0)\"," } ?? ""
            let preProjJSON: String
            let liveProjJSON: String
            if let pA = projAway, let pH = projHome {
                preProjJSON = """
                , "projected_away_score": \(pA), "projected_home_score": \(pH)
                """
                liveProjJSON = """
                , "live_projection": {
                    "projected_home_score": \(pH),
                    "projected_away_score": \(pA),
                    "kind": "in_play",
                    "boundary": "commence_time",
                    "boundary_at": "2026-11-15T18:00:00Z",
                    "earliest_confirmed_at": "2026-11-15T19:12:00Z",
                    "latest_captured_at": "2026-11-15T19:13:00Z",
                    "source": "sportsbooks",
                    "basis": "consensus_spread_total",
                    "bookmaker_count": 4,
                    "unit": "\(unit)",
                    "period": "\(period)"
                }
                """
            } else {
                preProjJSON = ""
                liveProjJSON = ""
            }

            let pregameProjectionBlock: String = {
                guard let pA = projAway, let pH = projHome else { return "" }
                return """
                , "pregame_projection": {
                    "kind": "last_before_scheduled_start",
                    "boundary": "scheduled_start",
                    "boundary_at": "2026-11-15T18:00:00Z",
                    "earliest_captured_at": "2026-11-15T17:40:00Z",
                    "latest_captured_at": "2026-11-15T17:58:00Z",
                    "source": "sportsbooks",
                    "basis": "consensus_spread_total",
                    "bookmaker_count": 5,
                    "unit": "\(unit)",
                    "period": "\(period)",
                    "projected_home_score": \(pH - 1.0),
                    "projected_away_score": \(pA - 1.0)
                }
                """
            }()

            // 1. BEFORE
            let before = try decodeEvent("""
            {
              "id": \(1000 + list.count),
              "sport": "\(sport)",
              "league": "\(league)",
              "away_team": "\(away)",
              "home_team": "\(home)",
              "commence_time": "2026-11-16T01:20:00Z",
              "status": "scheduled",
              "away_team_data": { \(recAwayJSON) "primary_color": "\(awayPrimary)"\(awaySecJSON)\(awayLogoJSON) },
              "home_team_data": { \(recHomeJSON) "primary_color": "\(homePrimary)"\(homeLogoJSON) },
              "current_odds": {
                "away_probability": \(preAwayProb),
                "home_probability": \(preHomeProb),
                "away_rendered_percent": \(Int((preAwayProb * 100).rounded())),
                "home_rendered_percent": \(Int((preHomeProb * 100).rounded()))\(preProjJSON)
              },
              "espn": { "broadcast": "ESPN" }
            }
            """)
            list.append(Specimen(title: "\(label) · Before", event: before))

            // 2. DURING
            let scoreFields: String
            if let aS = awayScore, let hS = homeScore {
                scoreFields = "\"away_score\": \(aS), \"home_score\": \(hS),"
            } else {
                scoreFields = ""
            }
            let during = try decodeEvent("""
            {
              "id": \(1000 + list.count),
              "sport": "\(sport)",
              "league": "\(league)",
              "away_team": "\(away)",
              "home_team": "\(home)",
              "commence_time": "2026-11-15T18:00:00Z",
              "status": "live",
              \(scoreFields)
              "away_team_data": { \(recAwayJSON) "primary_color": "\(awayPrimary)"\(awaySecJSON)\(awayLogoJSON) },
              "home_team_data": { \(recHomeJSON) "primary_color": "\(homePrimary)"\(homeLogoJSON) },
              "current_odds": {
                "away_probability": \(liveAwayProb),
                "home_probability": \(liveHomeProb)\(liveProjJSON)
              },
              "prematch_odds": {
                "away_probability": \(preAwayProb),
                "home_probability": \(preHomeProb),
                "away_rendered_percent": \(Int((preAwayProb * 100).rounded())),
                "home_rendered_percent": \(Int((preHomeProb * 100).rounded()))
              }\(pregameProjectionBlock),
              "espn": { "period": "\(livePeriod)", "game_clock": "\(liveClock)" }
            }
            """)
            list.append(Specimen(
                title: "\(label) · During",
                event: during,
                liveStatusText: PeriodLabel.liveStatusText(period: livePeriod, gameClock: liveClock),
                hasScore: awayScore != nil && homeScore != nil,
                numberStreams: true,
                ladderHome: projHome,
                ladderAway: projAway
            ))

            // 3. AFTER
            let after = try decodeEvent("""
            {
              "id": \(1000 + list.count),
              "sport": "\(sport)",
              "league": "\(league)",
              "away_team": "\(away)",
              "home_team": "\(home)",
              "commence_time": "2026-11-14T20:00:00Z",
              "completed_at": "2026-11-14T23:10:00Z",
              "status": "completed",
              \(scoreFields)
              "hero_settled_result": "home",
              "away_team_data": { \(recAwayJSON) "primary_color": "\(awayPrimary)"\(awaySecJSON)\(awayLogoJSON) },
              "home_team_data": { \(recHomeJSON) "primary_color": "\(homePrimary)"\(homeLogoJSON) },
              "prematch_odds": {
                "away_probability": \(preAwayProb),
                "home_probability": \(preHomeProb),
                "away_rendered_percent": \(Int((preAwayProb * 100).rounded())),
                "home_rendered_percent": \(Int((preHomeProb * 100).rounded()))
              }
            }
            """)
            list.append(Specimen(
                title: "\(label) · After",
                event: after,
                hasScore: awayScore != nil && homeScore != nil
            ))
        }

        // Core sports × 3 states
        try standardTrio(label: "NFL", sport: "americanfootball_nfl", league: "NFL", away: "New England Patriots", home: "Detroit Lions", awayPrimary: "#002244", awaySecondary: "#C60C30", homePrimary: "#0076B6", awayScore: 17, homeScore: 24, projAway: 24, projHome: 28)
        try standardTrio(label: "NBA", sport: "basketball_nba", league: "NBA", away: "New York Knicks", home: "Boston Celtics", awayPrimary: "#006BB6", awaySecondary: "#F58426", homePrimary: "#007A33", awayScore: 84, homeScore: 91, projAway: 108, projHome: 115)
        try standardTrio(label: "NCAAF", sport: "americanfootball_ncaaf", league: "NCAAF", away: "Kansas", home: "Duke", awayPrimary: "#0051BA", awaySecondary: "#E8000D", homePrimary: "#003087", awayScore: 20, homeScore: 27, projAway: 27, projHome: 31)
        try standardTrio(label: "NCAAB", sport: "basketball_ncaab", league: "NCAAB", away: "Gonzaga", home: "Duke", awayPrimary: "#041E42", awaySecondary: "#C8102E", homePrimary: "#003087", awayScore: 62, homeScore: 66, projAway: 76, projHome: 79, livePeriod: "2nd Half", liveClock: "7:40")
        try standardTrio(label: "MLB", sport: "baseball_mlb", league: "MLB", away: "New York Yankees", home: "Los Angeles Dodgers", awayPrimary: "#0C2340", awaySecondary: "#64748B", homePrimary: "#005A9C", awayScore: 3, homeScore: 5, projAway: 4.2, projHome: 5.8, unit: "runs", period: "full_game", livePeriod: "Top 7th", liveClock: "")
        try standardTrio(label: "NHL", sport: "icehockey_nhl", league: "NHL", away: "Toronto Maple Leafs", home: "Montreal Canadiens", awayPrimary: "#00205B", homePrimary: "#AF1E2D", awayScore: 2, homeScore: 3, projAway: 2.8, projHome: 3.6, unit: "goals", period: "regulation", livePeriod: "2nd Period", liveClock: "11:05", awayLogo: "https://a.espncdn.com/i/teamlogos/nhl/500/tor.png", homeLogo: "https://a.espncdn.com/i/teamlogos/nhl/500/mtl.png")
        try standardTrio(label: "MMA", sport: "mma_mixed_martial_arts", league: "UFC", away: "Charles Oliveira", home: "Islam Makhachev", awayPrimary: "#B45309", homePrimary: "#1D4ED8", awayRecord: "34-10", homeRecord: "26-1", awayScore: nil, homeScore: nil, projAway: nil, projHome: nil, livePeriod: "R3", liveClock: "2:15")
        try standardTrio(label: "Boxing", sport: "boxing_boxing", league: "Boxing", away: "Tyson Fury", home: "Oleksandr Usyk", awayPrimary: "#0F766E", homePrimary: "#1D4ED8", awayRecord: "34-1-1", homeRecord: "22-0", awayScore: nil, homeScore: nil, projAway: nil, projHome: nil, livePeriod: "R8", liveClock: "1:40")
        try standardTrio(label: "Cricket", sport: "cricket_ipl", league: "IPL", away: "Mumbai Indians", home: "Chennai Super Kings", awayPrimary: "#004BA0", homePrimary: "#CA8A04", awayRecord: nil, homeRecord: nil, awayScore: 142, homeScore: 158, projAway: nil, projHome: nil, livePeriod: "2nd Inn", liveClock: "")
        try standardTrio(label: "Rugby", sport: "rugbyunion_six_nations", league: "Six Nations", away: "Ireland", home: "France", awayPrimary: "#166534", homePrimary: "#1D4ED8", awayRecord: nil, homeRecord: nil, awayScore: 17, homeScore: 21, projAway: nil, projHome: nil, livePeriod: "58'", liveClock: "")
        try standardTrio(label: "Esports", sport: "esports_csgo", league: "CS2", away: "Team Vitality", home: "Natus Vincere", awayPrimary: "#CA8A04", homePrimary: "#2563EB", awayRecord: nil, homeRecord: nil, awayScore: 1, homeScore: 2, projAway: nil, projHome: nil, livePeriod: "Map 3", liveClock: "")

        // Soccer 3-Way (Before, During, After Draw)
        let soccer3Before = try decodeEvent("""
        {
          "id": 2001, "sport": "soccer_epl", "league": "Premier League",
          "home_team": "Arsenal", "away_team": "Liverpool",
          "commence_time": "2026-11-16T16:30:00Z", "status": "scheduled",
          "home_team_data": { "primary_color": "#EF0107", "record": "7-2-1" },
          "away_team_data": { "primary_color": "#00B2A9", "record": "8-1-1" },
          "current_odds": { "home_probability": 0.45, "draw_probability": 0.27, "away_probability": 0.28 }
        }
        """)
        list.append(Specimen(title: "Soccer 3-Way · Before", event: soccer3Before, ladderHome: 1.7, ladderAway: 1.3))

        let soccer3During = try decodeEvent("""
        {
          "id": 2002, "sport": "soccer_epl", "league": "Premier League",
          "home_team": "Arsenal", "away_team": "Liverpool",
          "commence_time": "2026-11-15T18:00:00Z", "status": "live",
          "home_score": 1, "away_score": 1,
          "home_team_data": { "primary_color": "#EF0107" },
          "away_team_data": { "primary_color": "#00B2A9" },
          "current_odds": { "home_probability": 0.39, "draw_probability": 0.36, "away_probability": 0.25 },
          "prematch_odds": { "home_probability": 0.45, "draw_probability": 0.27, "away_probability": 0.28 },
          "espn": { "period": "2nd", "game_clock": "68'" }
        }
        """)
        list.append(Specimen(title: "Soccer 3-Way · During", event: soccer3During, liveStatusText: "68'", hasScore: true, numberStreams: true, ladderHome: 1.8, ladderAway: 1.6))

        let soccer3AfterDraw = try decodeEvent("""
        {
          "id": 2003, "sport": "soccer_epl", "league": "Premier League",
          "home_team": "Arsenal", "away_team": "Liverpool",
          "commence_time": "2026-11-14T16:30:00Z", "completed_at": "2026-11-14T18:25:00Z",
          "status": "completed", "home_score": 1, "away_score": 1,
          "hero_settled_result": "draw",
          "home_team_data": { "primary_color": "#EF0107" },
          "away_team_data": { "primary_color": "#00B2A9" },
          "prematch_odds": { "home_probability": 0.45, "draw_probability": 0.27, "away_probability": 0.28 }
        }
        """)
        list.append(Specimen(title: "Soccer 3-Way · After (Draw)", event: soccer3AfterDraw, hasScore: true))

        // Tennis (Before, During with sets + game points, During Challenger no-score, After with sets)
        let tennisBefore = try decodeEvent("""
        {
          "id": 2010, "sport": "tennis_atp_us_open", "league": "ATP",
          "away_team": "Jannik Sinner", "home_team": "Carlos Alcaraz",
          "commence_time": "2026-11-16T19:00:00Z", "status": "scheduled",
          "current_odds": { "away_probability": 0.46, "home_probability": 0.54, "away_rendered_percent": 46, "home_rendered_percent": 54 }
        }
        """)
        list.append(Specimen(title: "Tennis · Before", event: tennisBefore))

        let tennisDuring = try decodeEvent("""
        {
          "id": 2011, "sport": "tennis_atp_us_open", "league": "ATP",
          "away_team": "Jannik Sinner", "home_team": "Carlos Alcaraz",
          "commence_time": "2026-11-15T18:00:00Z", "status": "live",
          "away_score": 1, "home_score": 1,
          "box_score_data": { "away_period_scores": [6, 4, 3], "home_period_scores": [4, 6, 4] },
          "current_odds": { "away_probability": 0.412, "home_probability": 0.588 },
          "prematch_odds": { "away_probability": 0.46, "home_probability": 0.54, "away_rendered_percent": 46, "home_rendered_percent": 54 },
          "espn": { "period": "Set 3", "game_clock": "30-40" }
        }
        """)
        list.append(Specimen(title: "Tennis · During", event: tennisDuring, liveStatusText: "Set 3", hasScore: true, numberStreams: true))

        let tennisNoScoreLive = try decodeEvent("""
        {
          "id": 2012, "sport": "tennis_atp_challenger", "league": "ATP",
          "away_team": "Luca Nardi", "home_team": "Arthur Cazaux",
          "commence_time": "2026-11-15T18:00:00Z", "status": "live",
          "current_odds": { "away_probability": 0.38, "home_probability": 0.62 }
        }
        """)
        list.append(Specimen(title: "Tennis · Live No Score", event: tennisNoScoreLive, hasScore: false, numberStreams: true))

        let tennisAfter = try decodeEvent("""
        {
          "id": 2013, "sport": "tennis_atp_us_open", "league": "ATP",
          "away_team": "Jannik Sinner", "home_team": "Carlos Alcaraz",
          "commence_time": "2026-11-14T18:00:00Z", "completed_at": "2026-11-14T20:45:00Z",
          "status": "completed", "away_score": 1, "home_score": 2,
          "hero_settled_result": "home",
          "box_score_data": { "away_period_scores": [6, 4, 5], "home_period_scores": [4, 6, 7] },
          "prematch_odds": { "away_probability": 0.46, "home_probability": 0.54, "away_rendered_percent": 46, "home_rendered_percent": 54 }
        }
        """)
        list.append(Specimen(title: "Tennis · After", event: tennisAfter, hasScore: true))

        // Former `nil` fallback edge cases (opening-only quote, missing live odds, missing final scores, venue-settled, venue-closed, postponed, suspended, 2-way AET soccer, MMA draw)
        let openingOnlyBefore = try decodeEvent("""
        {
          "id": 2020, "sport": "americanfootball_nfl", "league": "NFL",
          "away_team": "Chicago Bears", "home_team": "Green Bay Packers",
          "away_team_data": { "primary_color": "#0B162A", "secondary_color": "#C83803" },
          "home_team_data": { "primary_color": "#203731", "secondary_color": "#FFB612" },
          "commence_time": "2026-11-17T18:00:00Z", "status": "scheduled",
          "current_odds": { "away_probability": 0.35, "home_probability": 0.65, "quote_kind": "opening" },
          "opening_odds": { "away_probability": 0.35, "home_probability": 0.65 }
        }
        """)
        list.append(Specimen(title: "Edge · Early Unpriced Pregame", event: openingOnlyBefore))

        let liveMissingOdds = try decodeEvent("""
        {
          "id": 2021, "sport": "basketball_nba", "league": "NBA",
          "away_team": "Miami Heat", "home_team": "Orlando Magic",
          "commence_time": "2026-11-15T18:00:00Z", "status": "live",
          "away_score": 48, "home_score": 52,
          "espn": { "period": "2", "game_clock": "3:10" }
        }
        """)
        list.append(Specimen(title: "Edge · Live Missing Odds (Empty Now Cell)", event: liveMissingOdds, liveStatusText: "Q2 3:10", hasScore: true))

        let finalMissingScores = try decodeEvent("""
        {
          "id": 2022, "sport": "icehockey_nhl", "league": "NHL",
          "away_team": "Boston Bruins", "home_team": "New York Rangers",
          "away_team_data": { "logo_small": "https://a.espncdn.com/i/teamlogos/nhl/500/bos.png" },
          "home_team_data": { "logo_small": "https://a.espncdn.com/i/teamlogos/nhl/500/nyr.png" },
          "commence_time": "2026-11-14T19:00:00Z", "status": "completed",
          "hero_settled_result": "away",
          "opening_odds": { "away_probability": 0.48, "home_probability": 0.52 }
        }
        """)
        list.append(Specimen(title: "Edge · Final Missing Scores & Pregame", event: finalMissingScores))

        let venueSettledEdge = try decodeEvent("""
        {
          "id": 2023, "sport": "soccer_uefa_champs_league", "league": "Champions League",
          "away_team": "AC Milan", "home_team": "Real Madrid",
          "commence_time": "2026-11-14T20:00:00Z", "status": "scheduled",
          "venue_settled": true, "venue_settled_result": "Settled by venue"
        }
        """)
        list.append(Specimen(title: "Edge · Graded By Venue Verdict", event: venueSettledEdge))

        let venueClosedEdge = try decodeEvent("""
        {
          "id": 2024, "sport": "tennis_wta_australian_open", "league": "WTA",
          "away_team": "Coco Gauff", "home_team": "Iga Swiatek",
          "commence_time": "2026-11-14T08:00:00Z", "status": "scheduled",
          "venue_closed_no_winner": true
        }
        """)
        list.append(Specimen(title: "Edge · Venue Closed No Winner", event: venueClosedEdge))

        let postponedEdge = try decodeEvent("""
        {
          "id": 2025, "sport": "baseball_mlb", "league": "MLB",
          "away_team": "Chicago Cubs", "home_team": "St. Louis Cardinals",
          "commence_time": "2026-11-16T18:15:00Z", "status": "postponed"
        }
        """)
        list.append(Specimen(title: "Edge · Postponed", event: postponedEdge))

        let suspendedEdge = try decodeEvent("""
        {
          "id": 2026, "sport": "soccer_usa_mls", "league": "MLS",
          "away_team": "LA Galaxy", "home_team": "Seattle Sounders",
          "commence_time": "2026-11-15T17:00:00Z", "status": "suspended",
          "away_score": 1, "home_score": 0
        }
        """)
        list.append(Specimen(title: "Edge · Suspended After Start", event: suspendedEdge, hasScore: true))

        let mmaDrawEdge = try decodeEvent("""
        {
          "id": 2027, "sport": "mma_mixed_martial_arts", "league": "UFC",
          "away_team": "Alexa Grasso", "home_team": "Valentina Shevchenko",
          "commence_time": "2026-11-14T22:00:00Z", "status": "completed",
          "hero_settled_result": "draw",
          "prematch_odds": { "away_probability": 0.44, "home_probability": 0.56, "away_rendered_percent": 44, "home_rendered_percent": 56 }
        }
        """)
        list.append(Specimen(title: "Edge · MMA Draw", event: mmaDrawEdge))

        return list
    }

    // MARK: - Guard Test + 390 px Contact Sheet Export

    func testEverySportStateAndSizeUsesOneComponentWithZeroClutterOrDuplicateLabels() throws {
        let specimens = try buildAllSpecimens()
        XCTAssertGreaterThanOrEqual(specimens.count, 48)

        let bannedSubstrings = [
            "opening",
            "opened",
            "stale",
            "current win chance",
            "projection before",
            "settled",
            "ended by venue",
            "3 venues",
        ]

        let allowedPregameRegex = try NSRegularExpression(
            pattern: #"^Pregame  (?:.+ \d+% · projected \d+–\d+|.+ \d+%|projected .*\d+–\d+)$"#
        )

        var resolvedCards: [(title: String, model: EventSportHeadlines12472.Model, colors: (away: Color, home: Color))] = []
        let probeWindow: UIWindow = {
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                return UIWindow(windowScene: scene)
            }
            return UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 852))
        }()
        probeWindow.overrideUserInterfaceStyle = .light
        probeWindow.isHidden = false
        defer {
            probeWindow.isHidden = true
            probeWindow.rootViewController = nil
        }

        for spec in specimens {
            let model = EventSportHeadlines12472.resolve(
                event: spec.event,
                awayFullName: spec.event.awayTeam,
                homeFullName: spec.event.homeTeam,
                liveStatusText: spec.liveStatusText,
                hasScore: spec.hasScore,
                numberStreams: spec.numberStreams,
                ladderHome: spec.ladderHome,
                ladderAway: spec.ladderAway,
                gameMarkets: spec.gameMarkets,
                now: fixedNow
            )

            let pairHex = TeamTextContrast.cardColorHexes(
                awayHex: spec.event.awayTeamData?.primaryColor,
                homeHex: spec.event.homeTeamData?.primaryColor,
                awaySecondaryHex: spec.event.awayTeamData?.secondaryColor,
                checkHueFamily: true
            )
            let colors = (away: Color(hex: pairHex.away), home: Color(hex: pairHex.home))
            resolvedCards.append((title: spec.title, model: model, colors: colors))

            // (a) Verify `EventDetailView.heroSection` mounts `EventSportHeadlineCard12472` unconditionally
            var mountedHeroKind: EventSportHeadlines12472.Kind? = nil
            let pageHero = EventDetailView(eventId: spec.event.id)
                .withLoadedEventForTest12278(spec.event)
                .heroSectionForTest12278(spec.event)
                .onPreferenceChange(HeadlineMountedKindPreferenceKey199.self) { mountedHeroKind = $0 }
                .environmentObject(PinManager())
                .environmentObject(NavigationCoordinator())
                .frame(width: 358)
            let heroHost = hostForMeasurement(pageHero, at: .large)
            let heroHeight = max(ceil(heroHost.sizeThatFits(in: CGSize(width: 358, height: 1000)).height), 60)
            heroHost.view.frame = CGRect(x: 0, y: 0, width: 358, height: heroHeight)
            probeWindow.frame = heroHost.view.frame
            probeWindow.rootViewController = heroHost
            heroHost.view.setNeedsLayout()
            heroHost.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.008))
            heroHost.view.layoutIfNeeded()
            XCTAssertEqual(
                mountedHeroKind,
                model.kind,
                "\(spec.title) must mount EventSportHeadlineCard12472 (\(model.kind.accessibilityIdentifier))"
            )

            // Verify at BOTH `.large` AND `.accessibility2`
            for dtSize in [DynamicTypeSize.large, DynamicTypeSize.accessibility2] {
                var mountedCardKind: EventSportHeadlines12472.Kind? = nil
                var measuredSummaryHeight: CGFloat? = nil
                let card = EventSportHeadlineCard12472(
                    model: model,
                    colors: colors,
                    ekgTracker: EkgTracker(),
                    liveUpdateStatus: .live,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: spec.numberStreams,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                .onPreferenceChange(HeadlineMountedKindPreferenceKey199.self) { mountedCardKind = $0 }
                .onPreferenceChange(LivePregameSummaryHeightPreferenceKey199.self) { measuredSummaryHeight = $0 }
                .frame(width: 358)
                .environment(\.colorScheme, .light)

                let host = hostForMeasurement(card, at: dtSize)
                let h = max(ceil(host.sizeThatFits(in: CGSize(width: 358, height: 1200)).height), 60)
                host.view.frame = CGRect(x: 0, y: 0, width: 358, height: h)
                probeWindow.frame = host.view.frame
                probeWindow.rootViewController = host
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.008))
                host.view.layoutIfNeeded()
                XCTAssertEqual(
                    mountedCardKind,
                    model.kind,
                    "[\(spec.title) @ \(dtSize)] card preference must report mounted kind"
                )

                let texts = allVisibleTextElements(for: model)
                XCTAssertGreaterThanOrEqual(
                    texts.count,
                    3,
                    "[\(spec.title)] non-vacuity check: expected >= 3 rendered text elements"
                )

                // (b) Zero banned words/phrases anywhere in rendered labels
                for text in texts {
                    let lower = text.lowercased()
                    for banned in bannedSubstrings {
                        XCTAssertFalse(
                            lower.contains(banned),
                            "[\(spec.title) @ \(dtSize)] printed banned phrase '\(banned)' in label '\(text)'"
                        )
                    }
                }

                // (c) Zero duplicate alphabetic labels inside one headline
                let alphaLabels = texts.filter { isAlphabeticLabel($0) }
                var seenAlpha = Set<String>()
                for alpha in alphaLabels {
                    XCTAssertTrue(
                        seenAlpha.insert(alpha).inserted,
                        "[\(spec.title) @ \(dtSize)] duplicate label '\(alpha)' in headline labels: \(alphaLabels)"
                    )
                }

                // (d) Live grey pregame summary line invariants
                if let summary = model.livePregameSummary {
                    let full = summary.fullText
                    let range = NSRange(full.startIndex..<full.endIndex, in: full)
                    XCTAssertNotNil(
                        allowedPregameRegex.firstMatch(in: full, options: [], range: range),
                        "[\(spec.title)] livePregameSummary '\(full)' holds content beyond the two admitted pregame facts"
                    )
                    let summaryHeight = try XCTUnwrap(
                        measuredSummaryHeight,
                        "[\(spec.title) @ \(dtSize)] livePregameSummary height preference must report"
                    )
                    XCTAssertGreaterThan(summaryHeight, 6.0)
                    let maxSingleLineHeight: CGFloat = dtSize == .large ? 24.0 : 38.0
                    XCTAssertLessThanOrEqual(
                        summaryHeight,
                        maxSingleLineHeight,
                        "[\(spec.title) @ \(dtSize)] pregame summary must never wrap past 1 line (height=\(summaryHeight))"
                    )
                } else {
                    XCTAssertNil(
                        measuredSummaryHeight,
                        "[\(spec.title)] must hide pregame summary line when both pregame facts are absent"
                    )
                }

                // (e) No header over an empty column
                for (colIdx, col) in model.columns.enumerated() {
                    let hasAnyRowValue = model.rows.contains { row in
                        let hasCell = colIdx < row.cells.count && !row.cells[colIdx].isEmpty
                        let hasTick = col.role == .finalResult && row.won == true
                        return hasCell || hasTick
                    }
                    if !hasAnyRowValue {
                        XCTAssertEqual(
                            col.header,
                            "",
                            "[\(spec.title)] empty column \(col.role) must suppress its header"
                        )
                    }
                }

                // Phase-specific structural checks
                switch model.kind.phase {
                case .during:
                    XCTAssertFalse(
                        model.columns.contains { $0.role == .pregame },
                        "[\(spec.title)] must NEVER carry a Pregame column during a game (Ruling 200-B)"
                    )
                    for r in model.rows {
                        XCTAssertNil(r.record, "[\(spec.title)] must omit team records during a game")
                    }
                case .after:
                    XCTAssertNil(model.bottomBar, "[\(spec.title)] must omit probability bar after a game")
                case .before:
                    break
                }
            }
        }

        // Render ONE 390 px contact sheet showing representative sports × states + `.accessibility2` + former `nil` cases
        let sheetIndices: [Int] = [
            0, 1, 2,       // NFL before, during, after
            3, 4, 5,       // NBA before, during, after
            6, 7, 8,       // NCAAF (Kansas-Duke Ruling 197 + 194-A) before, during, after
            12, 13, 14,    // MLB before, during, after
            15, 16, 17,    // NHL before, during, after
            33, 34, 35,    // Soccer 3-Way before, during, after (Draw)
            36, 37, 38, 39,// Tennis before, during, live no-score, after
            18, 19, 20,    // MMA before, during, after
            40, 41, 42, 43 // Former `nil` edge cases
        ]
        let selectedCards = sheetIndices.compactMap { $0 < resolvedCards.count ? resolvedCards[$0] : nil }

        let sheetClock = fixedNow
        var tileEntries: [(title: String, model: EventSportHeadlines12472.Model, colors: (away: Color, home: Color), dt: DynamicTypeSize)] =
            selectedCards.map { ($0.title, $0.model, $0.colors, .large) }
        if let nflLive = resolvedCards.first(where: { $0.model.kind == .nflDuringGame }) {
            tileEntries.append(("NFL · During (@ .accessibility2 Dynamic Type)", nflLive.model, nflLive.colors, .accessibility2))
        }

        func captureTileImage<V: View>(_ view: V, at dt: DynamicTypeSize) -> UIImage {
            let host = hostForMeasurement(
                view
                    .frame(width: 390)
                    .background(Color(uiColor: .systemGroupedBackground))
                    .ignoresSafeArea()
                    .environment(\.colorScheme, .light),
                at: dt
            )
            host.additionalSafeAreaInsets = .zero
            host.overrideUserInterfaceStyle = .light
            host.traitOverrides.preferredContentSizeCategory = UIContentSizeCategory(dt)
            let initialH = max(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 1200)).height), 40)
            probeWindow.rootViewController = host
            probeWindow.frame = CGRect(x: 0, y: 0, width: 390, height: initialH)
            host.view.frame = probeWindow.bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            let settledH = max(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 1200)).height), 40)
            probeWindow.frame = CGRect(x: 0, y: 0, width: 390, height: settledH)
            host.view.frame = probeWindow.bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
        }

        var tileImages: [UIImage] = []
        let bannerView = VStack(alignment: .leading, spacing: 2) {
            Text("Unified Headline Component · Direction 199 (390 px)")
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
        }
        .padding(.top, 12)
        .padding(.bottom, 6)
        tileImages.append(captureTileImage(bannerView, at: .large))

        var allOcrLines: [String] = []
        for entry in tileEntries {
            let tileView = VStack(alignment: .leading, spacing: 4) {
                Text(entry.title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                EventSportHeadlineCard12472(
                    model: entry.model,
                    colors: entry.colors,
                    ekgTracker: EkgTracker(),
                    liveUpdateStatus: .live,
                    displayAsOf: sheetClock,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                .padding(.horizontal, 16)
            }
            .padding(.vertical, 5)
            let img = captureTileImage(tileView, at: entry.dt)
            tileImages.append(img)

            if let cg = img.cgImage {
                let req = VNRecognizeTextRequest()
                req.recognitionLevel = .fast
                req.usesLanguageCorrection = false
                try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
                let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
                allOcrLines.append(contentsOf: lines)
                for line in lines {
                    let lower = line.lowercased()
                    for banned in bannedSubstrings {
                        XCTAssertFalse(
                            lower.contains(banned),
                            "[\(entry.title)] OCR caught banned phrase '\(banned)' in rendered line '\(line)'"
                        )
                    }
                }
            }
        }

        XCTAssertGreaterThanOrEqual(allOcrLines.count, 60, "Contact sheet OCR must read rendered headline text across all card tiles")

        func stitchVertically(_ images: [UIImage]) -> UIImage {
            let totalH = images.reduce(CGFloat(0)) { $0 + $1.size.height }
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            return UIGraphicsImageRenderer(size: CGSize(width: 390, height: totalH), format: fmt).image { ctx in
                UIColor.systemGroupedBackground.setFill()
                ctx.fill(CGRect(x: 0, y: 0, width: 390, height: totalH))
                var y: CGFloat = 0
                for img in images {
                    img.draw(in: CGRect(x: 0, y: y, width: 390, height: img.size.height))
                    y += img.size.height
                }
            }
        }

        let sheetImage = stitchVertically(tileImages)
        XCTAssertEqual(sheetImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(sheetImage.size.height, 2500)

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_199_CONTACT_SHEET_DIR"],
           !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            if let png = sheetImage.pngData() {
                try png.write(to: dirURL.appendingPathComponent("199-unified-headline-contact-sheet-390.png"))
            }
            // Also write 3 sub-sheets for local zoom inspection
            let slice1 = stitchVertically(Array(tileImages.prefix(10)))
            let slice2 = stitchVertically(Array(tileImages.dropFirst(10).prefix(10)))
            let slice3 = stitchVertically(Array(tileImages.dropFirst(20)))
            try slice1.pngData()?.write(to: dirURL.appendingPathComponent("199-slice-1-390.png"))
            try slice2.pngData()?.write(to: dirURL.appendingPathComponent("199-slice-2-390.png"))
            try slice3.pngData()?.write(to: dirURL.appendingPathComponent("199-slice-3-390.png"))
        }
    }
}
