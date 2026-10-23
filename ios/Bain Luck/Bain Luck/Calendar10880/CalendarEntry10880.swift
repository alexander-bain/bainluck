import Foundation

/// #10880 — whether a game card may offer "Add to Calendar", and what the
/// entry says when it does.
///
/// A saved calendar entry is the one thing in the app we cannot correct
/// afterwards. It lives in the reader's own calendar and is a one-time copy,
/// not a subscription. So the action appears only when every part of the
/// entry is something the event's schedule said:
///
/// - **The start came from a schedule.** `start_is_from_schedule` is served by
///   `/api/feed` (`backend/app/utils/scheduled_start.py`) and is true only when
///   ESPN, StatPal or The Odds API wrote the start. A Kalshi row's
///   `commence_time` is the expected EXPIRATION; a Polymarket-listed row's is
///   the listing stamp (gotcha #14, `event_completion.py`). An absent flag (an
///   older server, a cached payload, a saved-pin card built from the detail
///   route) hides the action. It never offers one.
/// - **The hour is announced.** `start_is_tbd` (#8841) means the day is real
///   and the clock is a placeholder. There is no date-only entry here: the
///   placeholder is an INSTANT, and turning it into a calendar day would mean
///   choosing a time zone the schedule never named.
/// - **The game is still to come.** The status is `scheduled`, the venue has not
///   closed it, and its start is strictly after `now`. Only `scheduled` counts:
///   `EventState.section` files `nil`, `postponed` and `cancelled` under
///   upcoming, and none of those is a date anyone can plan around.
/// - **Both sides are named.** "TBD vs Chiefs" is not an entry.
///
/// The entry carries no probability: a number in a static title is wrong the
/// next minute and stays wrong in the calendar. Its length is a PLANNING
/// estimate per sport and the notes say so; no schedule we read publishes an
/// end time. The start is the served instant, unchanged. The system editor
/// shows it in the reader's own time zone, and the planning length is elapsed
/// time, so a game that crosses a daylight-saving change keeps its real length.
nonisolated struct CalendarSubject10880: Sendable, Equatable {
    let eventID: Int
    let awayName: String
    let homeName: String
    let sportKey: String?
    let start: Date?
    let startIsTbd: Bool
    let startIsFromSchedule: Bool
    let status: String?
    let venueClosedNoWinner: Bool
}

/// What the system editor opens with. The reader can change every field
/// before saving, or cancel.
nonisolated struct CalendarEntryDraft10880: Sendable, Equatable {
    let title: String
    let start: Date
    /// Elapsed seconds, never a wall-clock difference.
    let planningDuration: TimeInterval
    let url: URL
    let notes: String

    var end: Date { start.addingTimeInterval(planningDuration) }
}

/// Main-actor isolated (the target default) because it builds the link with
/// `eventShareURL`, the function Share and Copy Link use, so the three cannot
/// drift apart. Every caller is a view.
enum CalendarEntry10880 {

    nonisolated enum Decision: Sendable, Equatable {
        case offer(CalendarEntryDraft10880)
        case hide(Refusal)
    }

    /// Why the action is absent. Never shown to a reader; there is no disabled
    /// item and no explanation in the menu.
    nonisolated enum Refusal: Sendable, Equatable {
        case unnamedSide
        case startNotFromSchedule
        case notScheduled(String?)
        case closedNoWinner
        case startIsTBA
        case noStart
        case alreadyStarted
    }

    static func decide(for subject: CalendarSubject10880, now: Date) -> Decision {
        let away = subject.awayName.trimmingCharacters(in: .whitespacesAndNewlines)
        let home = subject.homeName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard isNamed(away), isNamed(home) else { return .hide(.unnamedSide) }
        guard subject.startIsFromSchedule else { return .hide(.startNotFromSchedule) }
        guard subject.status == "scheduled" else { return .hide(.notScheduled(subject.status)) }
        guard !subject.venueClosedNoWinner else { return .hide(.closedNoWinner) }
        guard !subject.startIsTbd else { return .hide(.startIsTBA) }
        guard let start = subject.start else { return .hide(.noStart) }
        guard start > now else { return .hide(.alreadyStarted) }
        guard let url = URL(string: eventShareURL(subject.eventID)) else { return .hide(.noStart) }

        let duration = planningDuration(sportKey: subject.sportKey)
        return .offer(CalendarEntryDraft10880(
            title: "\(away) vs \(home)",
            start: start,
            planningDuration: duration,
            url: url,
            notes: notes(noun: noun(sportKey: subject.sportKey), url: url, duration: duration)
        ))
    }

    // MARK: - Wording

    /// The noun a fan uses for one contest in this sport (#10877).
    static func noun(sportKey: String?) -> String {
        let key = sportKey ?? ""
        if key.hasPrefix("soccer_") || key.hasPrefix("tennis_")
            || key.hasPrefix("cricket_") || key.hasPrefix("rugby") {
            return "match"
        }
        if key.hasPrefix("mma_") || key.hasPrefix("boxing_") { return "fight" }
        return "game"
    }

    /// A typical length to block out, editable in the editor. Not an end time.
    static func planningDuration(sportKey: String?) -> TimeInterval {
        let key = sportKey ?? ""
        let hour: TimeInterval = 3_600
        if key.hasPrefix("americanfootball_") { return 3.5 * hour }
        if key.hasPrefix("basketball_") || key.hasPrefix("icehockey_")
            || key.hasPrefix("tennis_") { return 2.5 * hour }
        if key.hasPrefix("soccer_") { return 2 * hour }
        return 3 * hour
    }

    static func notes(noun: String, url: URL, duration: TimeInterval) -> String {
        """
        Open on Bain Luck: \(url.absoluteString)

        Added once from Bain Luck. If the \(noun) is moved, this entry won't \
        change, so check the \(noun) on Bain Luck before it starts.

        The length (\(durationText(duration))) is a planning estimate, not the \
        scheduled end.
        """
    }

    static func durationText(_ duration: TimeInterval) -> String {
        let minutes = Int((duration / 60).rounded())
        let h = minutes / 60, m = minutes % 60
        let hours = h == 1 ? "1 hour" : "\(h) hours"
        return m == 0 ? hours : "\(hours) \(m) minutes"
    }

    private static func isNamed(_ side: String) -> Bool {
        guard !side.isEmpty else { return false }
        return !["tbd", "tba"].contains(side.lowercased())
    }
}

/// One editor at a time.
///
/// `opening` covers the hop between the tap and UIKit's presentation, when no
/// editor exists yet. A second tap in that window is refused rather than
/// stacking a second editor. `editorVanished` releases only an `open` gate.
/// The presenter calls it when the editor it presented is gone without a
/// completion call (an interactive dismissal), so the action cannot jam shut.
/// This is about one editor on screen. It knows nothing about entries the
/// reader has already saved.
nonisolated struct CalendarPresentationGate10880: Sendable, Equatable {
    enum State: Sendable, Equatable { case idle, opening, open }

    private(set) var state: State = .idle

    mutating func requestOpen() -> Bool {
        guard state == .idle else { return false }
        state = .opening
        return true
    }

    mutating func didPresent() {
        if state == .opening { state = .open }
    }

    mutating func editorVanished() {
        if state == .open { state = .idle }
    }

    mutating func didFinish() {
        state = .idle
    }
}
