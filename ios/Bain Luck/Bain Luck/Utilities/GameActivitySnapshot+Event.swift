import Foundation

extension GameActivitySnapshot {
    /// Phone-only raw-status adapter delegates terminal authority to EventState.
    /// `final` is a provider alias of the canonical completed status.
    @MainActor
    private static func activityLifecycle(for status: String?) -> Lifecycle {
        let normalized = status?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let canonical = normalized == "final" ? "completed" : normalized
        if EventState.isFinished(canonical) {
            return normalized == "closed" ? .closed : .final
        }
        switch canonical {
        case "suspended": return .suspended
        case "live", "in_progress": return .live
        case "scheduled", "upcoming", "pregame": return .scheduled
        default: return .unknown
        }
    }

    @MainActor
    init?(eventID: Int, homeTeam: String, awayTeam: String, status: String?,
          homeScore: Int? = nil, awayScore: Int? = nil,
          homeProbability: Double? = nil, awayProbability: Double? = nil,
          drawProbability: Double? = nil, sport: String? = nil,
          scoreObservedAt: Date? = nil, probabilityObservedAt: Date? = nil) {
        self.init(eventID: eventID, homeTeam: homeTeam, awayTeam: awayTeam,
                  lifecycle: Self.activityLifecycle(for: status),
                  homeScore: homeScore, awayScore: awayScore,
                  homeProbability: homeProbability, awayProbability: awayProbability,
                  drawProbability: drawProbability, sport: sport,
                  scoreObservedAt: scoreObservedAt, probabilityObservedAt: probabilityObservedAt)
    }

    /// First slice follows a started game. Upcoming/opening-line pricing is not
    /// presented as a live forecast, and a phone receipt never dates a score.
    @MainActor
    static func liveActivityReading(for event: EventDetail, now: Date = Date()) -> GameActivitySnapshot? {
        let lifecycle = activityLifecycle(for: event.status)
        guard lifecycle == .live || lifecycle == .suspended || lifecycle == .final || lifecycle == .closed else {
            return nil
        }
        guard lifecycle != .suspended || EventState.isSuspendedAndStarted(
            "suspended", commenceTime: event.commenceTime?.asDate, now: now) else {
            return nil
        }
        let hero = event.heroProbability.flatMap {
            $0.isFinite && (0...1).contains($0) ? $0 : nil
        }
        let current = event.currentOdds?.homeProbability.flatMap {
            $0.isFinite && (0...1).contains($0) ? $0 : nil
        }
        // Match the phone's live headline, which receives pushed updates through
        // currentOdds. A hero timestamp can date it only when the values agree.
        let home = current ?? hero
        let away = current != nil ? event.currentOdds?.awayProbability : event.heroProbabilityAway
        let matchingHeroClock = home != nil && home == hero && away == event.heroProbabilityAway
        return GameActivitySnapshot(
            eventID: event.id, homeTeam: event.homeTeam, awayTeam: event.awayTeam,
            lifecycle: lifecycle, homeScore: event.homeScore, awayScore: event.awayScore,
            homeProbability: home, awayProbability: away,
            sport: event.sport,
            // EventDetail does not yet decode a score producer timestamp.
            scoreObservedAt: nil,
            probabilityObservedAt: matchingHeroClock ? event.heroProbabilityObservedAt?.asDate : nil
        )
    }
}
