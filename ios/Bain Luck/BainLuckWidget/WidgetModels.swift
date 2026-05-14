import Foundation
import WidgetKit

// MARK: - Timeline Entry

struct BainLuckWidgetEntry: TimelineEntry {
    let date: Date
    let liveGames: [WidgetGame]
    let discoverItems: [WidgetDiscoverItem]

    static var placeholder: BainLuckWidgetEntry {
        BainLuckWidgetEntry(
            date: Date(),
            liveGames: [
                WidgetGame(
                    id: 1,
                    homeTeam: "Boston Celtics",
                    awayTeam: "Los Angeles Lakers",
                    homeAbbrev: "BOS",
                    awayAbbrev: "LAL",
                    homeScore: 87,
                    awayScore: 82,
                    homeProb: 72,
                    awayProb: 28,
                    period: "Q3 4:32",
                    sport: "NBA",
                    homeColor: "#007A33",
                    awayColor: "#552583"
                ),
                WidgetGame(
                    id: 2,
                    homeTeam: "New York Yankees",
                    awayTeam: "Houston Astros",
                    homeAbbrev: "NYY",
                    awayAbbrev: "HOU",
                    homeScore: 3,
                    awayScore: 2,
                    homeProb: 61,
                    awayProb: 39,
                    period: "Bot 6",
                    sport: "MLB",
                    homeColor: "#003087",
                    awayColor: "#EB6E1F"
                ),
                WidgetGame(
                    id: 3,
                    homeTeam: "Edmonton Oilers",
                    awayTeam: "Florida Panthers",
                    homeAbbrev: "EDM",
                    awayAbbrev: "FLA",
                    homeScore: 2,
                    awayScore: 1,
                    homeProb: 58,
                    awayProb: 42,
                    period: "2nd 8:15",
                    sport: "NHL",
                    homeColor: "#FF4C00",
                    awayColor: "#041E42"
                ),
            ],
            discoverItems: [
                WidgetDiscoverItem(
                    id: 100,
                    name: "2026 NBA Champion",
                    category: "NBA",
                    leader: "Celtics",
                    probability: 32,
                    movement: 3,
                    hookDescription: nil,
                    headline: nil
                ),
                WidgetDiscoverItem(
                    id: 101,
                    name: "Next President",
                    category: "Politics",
                    leader: "Candidate A",
                    probability: 45,
                    movement: -2,
                    hookDescription: nil,
                    headline: nil
                ),
            ]
        )
    }
}

// MARK: - Widget Data Models

struct WidgetGame: Identifiable {
    let id: Int
    let homeTeam: String
    let awayTeam: String
    let homeAbbrev: String
    let awayAbbrev: String
    let homeScore: Int?
    let awayScore: Int?
    let homeProb: Int
    let awayProb: Int
    let period: String
    let sport: String
    let homeColor: String?
    let awayColor: String?
}

struct WidgetDiscoverItem: Identifiable {
    let id: Int
    let name: String
    let category: String
    let leader: String
    let probability: Int
    let movement: Int?
    let hookDescription: String?
    let headline: String?
}
