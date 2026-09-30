import Foundation

/// #6158 — WHERE "SINCE START" OPENS ON A GAME THAT STARTED LATE.
///
/// Both event charts cut "Since Start" at `commence_time`, the SCHEDULED start.
/// On a game that began late, that draws the pre-game stretch as game time: on
/// `/events/15321836` (White Sox @ Astros, 2026-09-30) the axis opened at 2:00 PM
/// and the first Top 1st observation is 21:13:06Z (2:13 PM), so the first fifth
/// of a one-hour "Since Start" window was a flat pre-game line. #6158's
/// specimens run to 47 minutes late (MLB 15316297), where it was 60% of the
/// window. Alex, 2026-09-14: scheduled kickoff is not automatically the actual
/// start.
///
/// The web's rule, mirrored (`frontend/lib/observedPlayStart.ts`, PR #9939): the
/// cut moves to the first OBSERVED opening period, less a short lead-in —
///   * never EARLIER than the scheduled start (this only ever narrows the
///     window, and only when the evidence says play began later);
///   * never past a `notBefore` bound — the last observation that still showed
///     an earlier state, so everything cut is time we know was pre-game;
///   * otherwise `leadIn` before the first observation, so the line enters the
///     window with its pre-play value and the opening chip is not flush against
///     the axis.
///
/// It declines (`nil` ⇒ keep `commence_time`) when the earliest period anyone
/// saw is not an opening period (we started watching mid-game), when it is an
/// estimate or has no named source, or when it sits more than `maxDelay` after
/// the scheduled start.
///
/// WHY RAW PERIOD STRINGS AND NOT THE CHART'S CHIPS: the chip strip carries whole
/// innings — `Top 1st` and `Bottom 1st` both chip as `1st` — so a chip cannot
/// tell "saw first pitch" from "started watching in the bottom half". The web's
/// boundaries keep the half (`T1` / `B1`); this reads the half off the raw string.
enum ObservedPlayStart {

    /// Lead-in kept before the first observation of play (about one live poll).
    static let leadIn: TimeInterval = 2 * 60

    /// An opening boundary this far after the scheduled start is not read as a
    /// late start: a rain delay of hours is a different story, and a boundary a
    /// day out belongs to a rescheduled session. Past it, keep today's cut.
    static let maxDelay: TimeInterval = 3 * 60 * 60

    /// One period-bearing reading, from any of the three places the page reads
    /// periods: ESPN history, `win_prob_history` game states, served
    /// `period_markers`.
    struct Sighting: Equatable {
        let date: Date
        /// The reading names the game's first period (`isOpeningPeriod`).
        let isOpening: Bool
        /// A named instrument saw it. A served estimate, or a served marker with
        /// no source, is not observed.
        let isObserved: Bool
        let notBefore: Date?
    }

    /// Where "Since Start" cuts instead of `scheduled`, or `nil` to keep it.
    static func cut(scheduled: Date?, history: EventHistoryResponse?, sportKey: String?) -> Date? {
        guard let history else { return nil }
        return cut(scheduled: scheduled, sightings: sightings(in: history, sportKey: sportKey))
    }

    static func cut(scheduled: Date?, sightings: [Sighting]) -> Date? {
        guard let scheduled else { return nil }
        // Earliest wins; on a tie, the one carrying a bound (a served marker).
        guard let first = sightings.min(by: {
            $0.date != $1.date ? $0.date < $1.date : ($0.notBefore != nil && $1.notBefore == nil)
        }) else { return nil }
        guard first.isOpening, first.isObserved else { return nil }
        guard first.date.timeIntervalSince(scheduled) <= maxDelay else { return nil }

        var cut = first.date.addingTimeInterval(-leadIn)
        if let notBefore = first.notBefore, notBefore < cut { cut = notBefore }
        return cut > scheduled ? cut : nil
    }

    /// Every period-bearing reading on the payload. The synthetic live edge is
    /// skipped: it re-serves the last state at the request's own "now" (#920).
    static func sightings(in history: EventHistoryResponse, sportKey: String?) -> [Sighting] {
        var out: [Sighting] = []
        for point in history.espnHistory ?? [] {
            guard let period = point.period, let date = point.timestamp.asDate,
                  isPeriod(period, sportKey: sportKey) else { continue }
            out.append(Sighting(date: date, isOpening: isOpeningPeriod(period, sportKey: sportKey),
                                isObserved: true, notBefore: nil))
        }
        for points in (history.winProbHistory ?? [:]).values {
            for point in points where point.liveEdge != true {
                guard let gs = point.gameState, let date = point.timestamp.asDate else { continue }
                if let period = gs.period, isPeriod(period, sportKey: sportKey) {
                    out.append(Sighting(date: date, isOpening: isOpeningPeriod(period, sportKey: sportKey),
                                        isObserved: true, notBefore: nil))
                } else if let inning = gs.inning, inning > 0 {
                    // An inning with no half: play is on, but which half is not
                    // said, so it can never be the opening observation.
                    out.append(Sighting(date: date, isOpening: false, isObserved: true, notBefore: nil))
                }
            }
        }
        for marker in history.periodMarkers ?? [] {
            guard let period = marker.period, let date = marker.timestamp?.asDate,
                  isPeriod(period, sportKey: sportKey) else { continue }
            out.append(Sighting(date: date, isOpening: isOpeningPeriod(period, sportKey: sportKey),
                                isObserved: marker.isObserved, notBefore: marker.notBefore?.asDate))
        }
        return out
    }

    /// A string the chart reads as a period at all (dates, "Final" and the like
    /// normalise to nothing).
    private static func isPeriod(_ raw: String, sportKey: String?) -> Bool {
        !PeriodLabel.normalize(raw, sport: sportKey).isEmpty
    }

    /// The web's `OPENING_PERIOD_LABEL` (`Q1|P1|T1|R1|1H`). Baseball's `T1` is
    /// the TOP of the 1st: the chip label drops the half, so it is read here.
    static func isOpeningPeriod(_ raw: String, sportKey: String?) -> Bool {
        let label = PeriodLabel.normalize(raw, sport: sportKey)
        if sportKey?.hasPrefix("baseball_") == true {
            return label == "1st"
                && raw.trimmingCharacters(in: .whitespaces).lowercased().hasPrefix("top ")
        }
        return ["Q1", "P1", "1H", "R1"].contains(label)
    }
}
