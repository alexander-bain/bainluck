import Foundation

/// #1833 — WHERE A FINISHED GAME'S SETTLEMENT LANDS ON THE TIME AXIS.
///
/// `/history` appends one synthetic settlement point to every probability
/// series of a finished game (1.0 / 0.0, `bookmaker_count: 0`) and stamps it at
/// `completed_at` floored to the minute (`routes/events.py`, "terminal
/// timestamp"). `completed_at` is when the backend LEARNED the result, not when
/// play ended: on `/events/15292394` (Real Madrid 77–78 Dubai, 2026-09-24) the
/// last real reading is 17:52Z and `completed_at` is 21:23Z, so the phone drew
/// "Since Start" from 9 AM to 2:25 PM PT with the line stopping near 11 AM and
/// the settled 100% dot — and the final-score dot, captured at the same moment
/// — standing alone three and a half hours later. Alex, 2026-09-14: scheduled
/// kickoff and capture timestamps are not automatically actual start/finish.
///
/// Both charts already END at "the last game data point, NOT completedAt"
/// (`SharedChartWindow`, `OddsChartView.gameEndDate`). The settlement point
/// defeated that rule by BEING the last data point. So the payload is confined
/// once, where the page takes it: the settlement points move to the last real
/// reading plus `lead` — the server's own rule for a game with no
/// `completed_at` ("last data point + 1 minute") — and every rule downstream
/// keeps working unchanged.
///
/// Only ever EARLIER: a settlement already within `lead` of the last reading is
/// left exactly where the server put it. Idempotent: a moved point no longer
/// sits at the settlement stamp, so a second pass finds nothing to move. The
/// result itself (who won, the final score) is never changed — only its x.
enum TerminalStamp {

    /// The gap between the last real reading and the settlement point it is
    /// moved to — the server's own no-`completed_at` lead.
    static let lead: TimeInterval = 60

    /// A score captured this close to `completed_at` is the completion capture
    /// (the final score, learned with the result), not an in-game reading.
    static let completionCaptureWindow: TimeInterval = 60

    static func confined(_ history: EventHistoryResponse) -> EventHistoryResponse {
        guard EventState.isFinished(history.status),
              let completedAt = history.completedAt?.asDate else { return history }
        let stamp = Date(timeIntervalSince1970:
            (completedAt.timeIntervalSince1970 / 60).rounded(.down) * 60)
        let captureFloor = completedAt.addingTimeInterval(-completionCaptureWindow)

        func isSettlement(_ timestamp: String, _ probability: Double?) -> Bool {
            guard let p = probability, p == 0 || p == 1 else { return false }
            return timestamp.asDate == stamp
        }

        // The last REAL reading: every drawn series, minus the settlement points
        // and the completion capture. A row with no probability draws nothing
        // (the server's period-marker guard counts values, not timestamps), so
        // it proves nothing either.
        var readings: [Date] = []
        func note(_ timestamp: String) { if let d = timestamp.asDate { readings.append(d) } }
        for p in history.history where p.homeProbability != nil
            && !isSettlement(p.timestamp, p.homeProbability) { note(p.timestamp) }
        for points in (history.bookmakerHistory ?? [:]).values {
            for p in points where p.homeProbability != nil { note(p.timestamp) }
        }
        for p in history.espnHistory ?? [] where !isSettlement(p.timestamp, p.homeProbability) {
            note(p.timestamp)
        }
        for points in (history.winProbHistory ?? [:]).values {
            for p in points where p.liveEdge != true && !isSettlement(p.timestamp, p.homeProbability) {
                note(p.timestamp)
            }
        }
        for p in history.aggregateLine ?? [] where !isSettlement(p.timestamp, p.homeProbability) {
            note(p.timestamp)
        }
        for p in history.scoreHistory ?? [] {
            if let d = p.timestamp.asDate, d < captureFloor { readings.append(d) }
        }

        guard let lastReading = readings.max() else { return history }
        let end = lastReading.addingTimeInterval(lead)
        guard stamp > end else { return history }
        let moved = formatter.string(from: end)

        var out = history
        out.history = history.history.map { p in
            var p = p
            if isSettlement(p.timestamp, p.homeProbability) { p.timestamp = moved }
            return p
        }
        out.espnHistory = history.espnHistory?.map { p in
            var p = p
            if isSettlement(p.timestamp, p.homeProbability) { p.timestamp = moved }
            return p
        }
        out.winProbHistory = history.winProbHistory?.mapValues { points in
            points.map { p in
                var p = p
                if isSettlement(p.timestamp, p.homeProbability) { p.timestamp = moved }
                return p
            }
        }
        out.aggregateLine = history.aggregateLine?.map { p in
            var p = p
            if isSettlement(p.timestamp, p.homeProbability) { p.timestamp = moved }
            return p
        }
        out.scoreHistory = history.scoreHistory?.map { p in
            var p = p
            if let d = p.timestamp.asDate, d >= captureFloor { p.timestamp = moved }
            return p
        }
        return out
    }

    private static let formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
}
