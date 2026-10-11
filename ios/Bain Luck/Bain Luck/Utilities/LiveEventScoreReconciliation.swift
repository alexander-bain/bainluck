import Foundation

/// #10866 — a delayed detail must not roll a held live score backward while
/// Live Activity correctly keeps the newer observation. Order observations,
/// not score values: a newer official downward correction is authoritative.
nonisolated enum LiveEventScoreReconciliation {
    static func keepingNewerHeldScore(_ polled: EventDetail, held: EventDetail?) -> EventDetail {
        guard let held, held.id > 0, held.id == polled.id,
              held.status == "live", polled.status == "live",
              let sport = held.sport, !sport.isEmpty, sport == polled.sport,
              held.homeTeam == polled.homeTeam, held.awayTeam == polled.awayTeam,
              let source = held.scoreSource,
              !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              source == polled.scoreSource,
              let heldHome = held.homeScore, heldHome >= 0,
              let heldAway = held.awayScore, heldAway >= 0,
              let polledHome = polled.homeScore, polledHome >= 0,
              let polledAway = polled.awayScore, polledAway >= 0,
              let heldAt = held.scoreObservedAt?.asDate,
              let polledAt = polled.scoreObservedAt?.asDate,
              heldAt.timeIntervalSince1970.isFinite,
              polledAt.timeIntervalSince1970.isFinite,
              polledAt < heldAt else { return polled }

        var kept = polled
        kept.homeScore = heldHome
        kept.awayScore = heldAway
        kept.scoreSource = held.scoreSource
        kept.scoreObservedAt = held.scoreObservedAt
        return kept
    }
}
