import Foundation

/// How a native surface reads an event's state — one enum, so no two screens
/// disagree about what a status MEANS.
///
/// This is the Swift half of `frontend/lib/eventState.ts` and it exists for the
/// same reason: `suspended` (live/048) landed in a vocabulary that every view
/// model and card had been reading with its own inline `== "closed"` chain. On
/// native the fall-through was worse than the web's. The three grid buckets are
/// written as three independent `filter` calls —
///
///     liveNow:       status == "live"
///     justHappened:  status == "completed" || status == "closed"
///     upcoming:      status == "scheduled" || status == nil
///
/// — and an unrecognised status matches NONE of them, so a suspended match did
/// not land in the wrong section: it landed in no section, and vanished from
/// Discover, Sports and My Stuff without leaving a gap anyone could see.
///
/// THE APPS DO NOT CRASH ON THE NEW VALUE, and that was checked rather than
/// assumed: `FeedEventData.status` is a `String?`, not a `RawRepresentable`
/// enum, so an unknown state decodes cleanly and every comparison above simply
/// returns false. That is why this ships with the web and API halves instead of
/// waiting behind a client-version gate — there is no old client to protect,
/// only an old client that shows one card fewer until it updates.
///
/// Keep in step with `frontend/lib/eventState.ts` and with `SETTLED_STATUSES`
/// in `backend/app/utils/event_completion.py`.
enum EventState {

    /// Something with standing said this event is over. Renders as Final.
    static func isFinished(_ status: String?) -> Bool {
        status == "completed" || status == "closed"
    }

    /// The clock ran out and no authority, venue settlement or score feed said
    /// the match ended. Non-terminal: it can go back to `live`, and it can be
    /// settled later by something that actually watched.
    static func isSuspended(_ status: String?) -> Bool {
        status == "suspended"
    }

    /// The short badge a suspended event wears.
    ///
    /// Deliberately NOT the bare word "Suspended": for a rain-delayed US Open
    /// match that reads right, but the same state also covers a fixture whose
    /// only source went dark, and telling a reader that match is "suspended"
    /// invents a stoppage nobody reported. What both cases share is that no
    /// result was ever reported, so that is what the badge says.
    static let suspendedLabel = "No result reported"

    /// The one line every card prints for a suspended event.
    ///
    /// Side order is AWAY-HOME, matching the web summary and every native card:
    /// the away crest is drawn first and the title reads "{away} @ {home}". A
    /// partial line (one side known, the other nil) prints the badge alone —
    /// half a score under a "last score" label is the same partial-line trap
    /// that graded the CERT-752 specimen 1.0/0.0, told smaller.
    static func suspendedSummary(away: Int?, home: Int?) -> String {
        guard let away, let home else { return suspendedLabel }
        return "\(suspendedLabel) · last score \(away)-\(home)"
    }

    /// Which grid section a status belongs to.
    ///
    /// `suspended` returns `.live` — not because the match is being played, but
    /// because the buckets answer "has this happened yet?" and the honest
    /// answer for a suspended row is the same as a live one: it started, it has
    /// not finished. The section TITLE distinguishes them (`liveSectionTitle`).
    enum Section {
        case live
        case finished
        case upcoming
    }

    static func section(_ status: String?) -> Section {
        if status == "live" || isSuspended(status) { return .live }
        if isFinished(status) { return .finished }
        return .upcoming
    }

    /// What the live section calls itself, given what landed in it. "Live Now"
    /// over a rain-delayed match is the card branch's false claim told one size
    /// larger, and the header is read first.
    static func liveSectionTitle(hasSuspended: Bool) -> String {
        hasSuspended ? "Live & Paused" : "Live Now"
    }
}
