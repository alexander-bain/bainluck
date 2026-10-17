import Foundation

extension FeedEventData {
    /// #10880 — the card's calendar subject, read only from served fields. See
    /// ``CalendarEntry10880`` for what each one decides.
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
