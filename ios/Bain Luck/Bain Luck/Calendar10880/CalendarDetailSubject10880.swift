import Foundation

extension EventDetail {
    /// #10880 — the event page's calendar subject, read only from fields
    /// `/api/events/{id}` serves. The same rule as a card's
    /// (``CalendarEntry10880``); only the source of the fields differs.
    var calendarSubject10880: CalendarSubject10880 {
        CalendarSubject10880(
            eventID: id,
            awayName: awayTeam,
            homeName: homeTeam,
            sportKey: sport,
            start: commenceTime?.asDate,
            startIsTbd: startIsTbd == true,
            startIsFromSchedule: startIsFromSchedule == true,
            status: status,
            venueClosedNoWinner: venueClosedNoWinner == true
        )
    }
}
