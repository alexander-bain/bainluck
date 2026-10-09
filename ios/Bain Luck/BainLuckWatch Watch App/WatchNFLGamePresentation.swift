import Foundation

/// Presentation of the exact published member card. No ranking, derived winner,
/// probability complement, detail lookup or substitute observation timestamp.
nonisolated struct WatchNFLGamePresentation: Equatable, Sendable {
    let stateText: String
    let awayName: String
    let homeName: String
    let awayScore: String?
    let homeScore: String?
    let scoreContext: String?
    let scoreObservedAt: Date?
    let chanceText: String?
    let chanceContext: String?
    let scheduledStart: Date?
    let startLabel: String?
    let startMissingText: String?

    init(game: WatchNFLGame, now: Date) {
        awayName = game.away
        homeName = game.home
        let status = game.status?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let waiting = game.startedWithoutResult == true || game.authorityNotStarted == true
        if status == "scheduled", game.authorityNotStarted == true {
            stateText = "Not started"
        } else if status == "scheduled", game.startedWithoutResult == true {
            stateText = "Awaiting game update"
        } else {
            switch status {
            case "scheduled": stateText = "Scheduled"
            case "live", "in_progress": stateText = "Live"
            case "final", "completed": stateText = "Final"
            case "closed": stateText = "Closed · result unverified"
            case "postponed": stateText = "Postponed"
            case "cancelled", "canceled": stateText = "Cancelled"
            case "suspended": stateText = "Suspended"
            default: stateText = "Game state unavailable"
            }
        }

        if status == "scheduled" {
            scheduledStart = Self.date(game.scheduledStart)
            startLabel = scheduledStart == nil ? nil : (waiting ? "Listed start" : "Scheduled start")
            startMissingText = scheduledStart != nil ? nil
                : (game.startIsTbd == true ? "Start time to be announced" : "Start time unavailable")
        } else {
            scheduledStart = nil
            startLabel = nil
            startMissingText = nil
        }

        // Scheduled/cancelled/postponed placeholders are not an in-play score.
        let showScores = !["scheduled", "cancelled", "canceled", "postponed"].contains(status ?? "")
        if showScores {
            let away = Self.score(game.awayScore), home = Self.score(game.homeScore)
            awayScore = away.map(String.init) ?? "—"
            homeScore = home.map(String.init) ?? "—"
            if away == nil && home == nil {
                scoreContext = "Score unavailable"
                scoreObservedAt = nil
            } else if let source = game.scoreSource, !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      let observed = Self.date(game.scoreObservedAt), observed <= now {
                scoreContext = "Score observed"
                scoreObservedAt = observed
            } else {
                scoreContext = "Score observation age unknown"
                scoreObservedAt = nil
            }
        } else {
            awayScore = nil
            homeScore = nil
            scoreContext = nil
            scoreObservedAt = nil
        }

        let forecastState = ["scheduled", "live", "in_progress"].contains(status ?? "") && !waiting
        let source = game.heroProbabilitySource?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if forecastState, let source, !source.isEmpty, source != "settled",
           let probability = game.heroProbability, let percent = Self.percent(probability) {
            chanceText = "\(game.home) win chance: \(percent)"
            // The retained collection card formatter does not emit the hero's
            // observation clock. current_odds.captured_at is not that clock.
            chanceContext = "Chance observation age unknown"
        } else {
            chanceText = forecastState ? "Win chance unavailable" : nil
            chanceContext = nil
        }
    }

    static func availableGamesText(_ membership: WatchNFLMembership) -> String {
        guard membership.published else { return "This collection is no longer available." }
        let count = membership.games.count
        return count == 1 ? "1 game available on Watch" : "\(count) games available on Watch"
    }

    private static func score(_ value: Int?) -> Int? {
        guard let value, value >= 0 else { return nil }
        return value
    }
    private static func percent(_ value: Double) -> String? {
        guard value.isFinite, (0...1).contains(value) else { return nil }
        if value == 0 { return "0%" }
        if value == 1 { return "100%" }
        if value < 0.01 { return "<1%" }
        if value > 0.99 { return ">99%" }
        return "\(Int((value * 100).rounded()))%"
    }
    private static func date(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }
}
