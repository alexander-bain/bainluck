import Foundation

extension GameActivitySnapshot {
    /// First slice follows a started game. Upcoming/opening-line pricing is not
    /// presented as a live forecast, and a phone receipt never dates a score.
    static func liveActivityReading(for event: EventDetail) -> GameActivitySnapshot? {
        let status = event.status?.lowercased()
        guard ["live", "in_progress", "suspended", "completed", "final", "closed"].contains(status ?? "") else {
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
            status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
            homeProbability: home, awayProbability: away,
            sport: event.sport,
            // EventDetail does not yet decode a score producer timestamp.
            scoreObservedAt: nil,
            probabilityObservedAt: matchingHeroClock ? event.heroProbabilityObservedAt?.asDate : nil
        )
    }
}
