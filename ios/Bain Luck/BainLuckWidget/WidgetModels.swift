import Foundation
import SwiftUI
import WidgetKit
#if DEBUG && canImport(Bain_Luck) && !BAINLUCK_WIDGET_EXTENSION
@testable import Bain_Luck
#endif

// MARK: - Timeline Entry

struct BainLuckWidgetEntry: WidgetKit.TimelineEntry {
    let date: Date
    let liveGames: [WidgetGame]
    let discoverItems: [WidgetDiscoverItem]
    var isPlaceholder: Bool = false

    /// #12316 / 254: A — elevate the live-games widget in the iPhone Smart Stack
    /// when live games are underway (below a reader's own pinned-game widget), never for placeholders.
    var relevance: TimelineEntryRelevance? {
        let spec = WidgetRelevanceRule254A.liveGamesWidget(liveCount: liveGames.count, isPlaceholder: isPlaceholder)
        return TimelineEntryRelevance(score: spec.score, duration: spec.duration)
    }

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
                    awayColor: "#552583",
                    homeDarkColor: TeamTextContrast.usableOnDarkSurface(primaryHex: "#007A33"),
                    awayDarkColor: TeamTextContrast.usableOnDarkSurface(primaryHex: "#552583", secondaryHex: "#FDB927")
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
                    awayColor: "#EB6E1F",
                    homeDarkColor: TeamTextContrast.usableOnDarkSurface(primaryHex: "#003087"),
                    awayDarkColor: TeamTextContrast.usableOnDarkSurface(primaryHex: "#EB6E1F")
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
                    awayColor: "#041E42",
                    homeDarkColor: TeamTextContrast.usableOnDarkSurface(primaryHex: "#FF4C00"),
                    awayDarkColor: TeamTextContrast.usableOnDarkSurface(primaryHex: "#041E42", secondaryHex: "#C8102E")
                ),
            ],
            discoverItems: [
                WidgetDiscoverItem(
                    id: 100,
                    name: "NBA Champion",
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
            ],
            isPlaceholder: true
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
    /// #5363 — nil where the sport prices a draw, so `1 − P(home)` is *away win
    /// or draw* and there is no away price to print. Withheld, not absent.
    let awayProb: Int?
    let period: String
    let sport: String
    let homeColor: String?
    let awayColor: String?
    var homeDarkColor: String? = nil
    var awayDarkColor: String? = nil
    var homeProbability: Double? = nil
    var awayProbability: Double? = nil

    var homeProbText: String {
        ExternalSurfaceProbabilityFormat.openWholePercent(homeProb, probability: homeProbability)
            ?? ExternalSurfaceProbabilityFormat.missingProbabilityText
    }

    var awayProbText: String? {
        guard let awayProb else { return nil }
        return ExternalSurfaceProbabilityFormat.openWholePercent(awayProb, probability: awayProbability)
    }

    var compactProbHeaderText: String {
        guard let awayProb else {
            return "\(homeAbbrev) \(homeProbText)"
        }
        let awayCompact = ExternalSurfaceProbabilityFormat.openCompactValue(awayProb, probability: awayProbability)
            ?? "\(awayProb)"
        let homeCompact = ExternalSurfaceProbabilityFormat.openCompactValue(homeProb, probability: homeProbability)
            ?? "\(homeProb)"
        if awayCompact.hasPrefix("<") || awayCompact.hasPrefix(">")
            || homeCompact.hasPrefix("<") || homeCompact.hasPrefix(">") {
            return "\(awayProbText ?? awayCompact)·\(homeProbText)"
        }
        return "\(awayCompact)-\(homeCompact)"
    }

    func resolvedHomeColor(for colorScheme: ColorScheme) -> String? {
        guard colorScheme == .dark else { return homeColor }
        return homeDarkColor ?? TeamTextContrast.usableOnDarkSurface(primaryHex: homeColor)
    }

    func resolvedAwayColor(for colorScheme: ColorScheme) -> String? {
        guard colorScheme == .dark else { return awayColor }
        return awayDarkColor ?? TeamTextContrast.usableOnDarkSurface(primaryHex: awayColor)
    }

    /// #5363 — who is ahead, where that is answerable AT ALL.
    ///
    /// Both are false when the away price is withheld, and that is the honest
    /// answer rather than a convenience: with one side priced we cannot say who
    /// leads. A home side on 40% may still be behind an away side on 45% with
    /// the draw taking 15, so bolding home — the shape `homeProb > awayProb`
    /// would fall into once the complement is gone — would state a comparison
    /// no number on the widget supports.
    var awayIsLeading: Bool {
        guard let awayProb else { return false }
        return awayProb > homeProb
    }
    var homeIsLeading: Bool {
        guard let awayProb else { return false }
        return homeProb > awayProb
    }
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
    var rawProbability: Double? = nil

    var probabilityText: String {
        ExternalSurfaceProbabilityFormat.openWholePercent(probability, probability: rawProbability)
            ?? ExternalSurfaceProbabilityFormat.missingProbabilityText
    }
}
