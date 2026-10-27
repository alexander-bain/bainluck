import Foundation

// The one `EventState` reading that needs a feed model. It lives apart from
// `EventState.swift` so that file stays Foundation-only and can join the widget
// extension (#10875), which shares the state rules rather than transcribing them
// and has no `FeedEventData`. Moved verbatim; no behaviour change.
extension EventState {
    /// The section a feed GAME card files under. #5811 — a row the venue
    /// closed with no winner is over, so it files where results file instead
    /// of under "Live & Paused". Every other row files exactly as
    /// ``section(_:)`` puts it. One function for every bucket, so the Sports
    /// tab, a category page and My Stuff cannot read one card two ways.
    ///
    /// `venueSettled: nil` because the feed model does not decode that key on
    /// native; the producer never sends both (a graded winner suppresses
    /// `venue_closed_no_winner` at the source — 15321573 on 2026-09-30).
    static func section(of event: FeedEventData?, now: Date = Date()) -> Section {
        if let event, showsVenueClosedNoWinner(
            event.status, venueSettled: nil,
            venueClosedNoWinner: event.venueClosedNoWinner,
            commenceTime: event.commenceTime?.asDate, now: now) {
            return .finished
        }
        return section(event?.status)
    }
}
