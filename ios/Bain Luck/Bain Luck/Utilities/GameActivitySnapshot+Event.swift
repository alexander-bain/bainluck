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
        // #10864 — a pushed frame moves the hero to its own `p` and clock and
        // derives the away side as `1 - p` (clearing the served pair), leaving
        // the served `heroProbabilityAway` behind. That complement is the
        // frame's own value, so the frame's clock dates it too. Without this,
        // every update after the first push was sent already stale, and an
        // activity that has never been active is not shown at all.
        let pushedPair = event.currentOdds.map {
            $0.homeRenderedPercent == nil && $0.awayRenderedPercent == nil
        } == true
        let awayAgrees = away == event.heroProbabilityAway
            || (current != nil && pushedPair && home.map { away == 1 - $0 } == true)
        let matchingHeroClock = home != nil && home == hero && awayAgrees
        // #10864 — the period chip, never a clock: a Live Activity repaints only
        // when an update arrives, so "5:26" or soccer's "67'" would sit frozen.
        // The scoreboard chip ("Q4", "7th") stays true longest, and a period
        // that IS a clock is dropped.
        let chip = PeriodLabel.normalize(event.espn?.period ?? "", sport: event.sport)
        let period = chip.isEmpty || chip.contains(":") || chip.contains("'") ? nil : chip
        return GameActivitySnapshot(
            eventID: event.id, homeTeam: event.homeTeam, awayTeam: event.awayTeam,
            lifecycle: lifecycle, homeScore: event.homeScore, awayScore: event.awayScore,
            homeProbability: home, awayProbability: away,
            sport: event.sport,
            // All three values are immutable fields from the same served response.
            // An orphan clock, partial tuple or absent attribution proves no age.
            scoreObservedAt: event.homeScore.map({ $0 >= 0 }) == true
                && event.awayScore.map({ $0 >= 0 }) == true
                && event.scoreSource?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
                ? event.scoreObservedAt?.asDate : nil,
            probabilityObservedAt: matchingHeroClock ? event.heroProbabilityObservedAt?.asDate : nil,
            homeAbbreviation: event.homeTeamData?.abbreviation,
            awayAbbreviation: event.awayTeamData?.abbreviation,
            homeColorHex: event.homeTeamData?.primaryColor,
            awayColorHex: event.awayTeamData?.primaryColor,
            periodLabel: period
        )
    }
}
