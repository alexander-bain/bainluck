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

    /// Whether the clock agrees the event has started.
    ///
    /// A nil `commenceTime` returns TRUE. That is the deliberate default and not
    /// a shrug: `suspended` is produced by something that watched a match begin
    /// and never saw it end, so a row carrying that status and no date is far
    /// more likely to be a started game we lost the schedule for than a fixture
    /// nobody has played. The false direction matters too — defaulting to
    /// "not started" would put the #4002 hero back to a blank badge on every
    /// dateless suspended row.
    static func hasStarted(commenceTime: Date?, now: Date = Date()) -> Bool {
        guard let commenceTime else { return true }
        return commenceTime <= now
    }

    /// The suspended TREATMENT: the status **and** the clock agreeing.
    ///
    /// 🔴 #4021 — `suspended` IS A STATUS, NOT A PHASE, and the two can disagree.
    /// Event 416569 (Ohio State @ Texas, kick-off 2026-09-12) sat at
    /// `status='suspended'` four days BEFORE it was due to be played. There is
    /// exactly one such row today — measured twice, by lane1b/084 and again
    /// independently — but one is enough, because the treatment it wrongly
    /// receives is the settled one: "No result reported" over a game nobody has
    /// played, a hidden broadcast, and a time chip reading "Started" about a date
    /// in the future.
    ///
    /// lane1b named the durable shape on #4021 and it is the reason this function
    /// exists rather than a fix at one call site: *a renderer deciding "no result"
    /// from a status it does not otherwise handle, without first asking whether
    /// the game has even started.* That is the denylist shape in
    /// `docs/gotchas-reference.md` — the first unfamiliar state inherits the
    /// settled claim. Asking the clock is what stops the NEXT odd status doing it.
    ///
    /// Every surface that renders the suspended treatment reads THIS, not
    /// ``isSuspended(_:)``. `isSuspended` stays as the plain vocabulary test for
    /// callers that want the status alone (grid bucketing, section titles), where
    /// a future-dated row landing in the live section is harmless.
    static func isSuspendedAndStarted(
        _ status: String?, commenceTime: Date?, now: Date = Date()
    ) -> Bool {
        isSuspended(status) && hasStarted(commenceTime: commenceTime, now: now)
    }

    /// Whether a FINAL can still arrive for this event.
    ///
    /// #4018 — the question a forecast has to answer, and it is NOT "is the game
    /// over?". `isFinished` is false for a suspended match, so every surface that
    /// gated a projection on `!isFinished` went on offering one for a game nobody
    /// will ever grade: on `15301312` (Chunichi Dragons v Tokyo Yakult Swallows,
    /// abandoned 2026-09-04) the Runs map read **`PROJECTION 4.8`** four days
    /// later. Measured on production over the 7 days to 2026-09-08: **184
    /// suspended games carrying a projection** against 1 live one.
    ///
    /// #4002 drew exactly this distinction for the hero and PR #4016 photographed
    /// it, but it stayed a private computed property on `EventDetailView` while
    /// three market cards one scroll below kept their own `isFinished` copy. This
    /// is that helper lifted to where the vocabulary lives, so there is one answer
    /// to "can this still be graded?" rather than a fourth inline version of it.
    ///
    /// IT IS DELIBERATELY NOT `isDone`. Flipping the cards' settled flag would be
    /// the easy change and it is wrong: those branches read `homeScore`/`homeTeam`
    /// totals and label them **FINAL**, so a suspended game with a partial score
    /// would have that partial published as the result. `suspendedSummary` above
    /// calls the same number a "last score" for precisely this reason. A forecast
    /// and a result are two questions and they get two predicates.
    static func canStillBeGraded(
        _ status: String?, commenceTime: Date?, now: Date = Date()
    ) -> Bool {
        !isFinished(status)
            && !isSuspendedAndStarted(status, commenceTime: commenceTime, now: now)
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

    /// What the player-props card calls the number on each rung.
    ///
    /// #4018 / D120 — THE PROPS CARD IS THE THIRD CARD, AND IT WAS LEFT OUT ON
    /// PURPOSE UNTIL ALEX RULED. The other two cards printed a number the APP
    /// computes and labels as a forecast of the final, which is mechanically
    /// wrong once no final can arrive, so `canStillBeGraded` suppressed them.
    /// This card prints the MARKET's price for a prop — a real quote — so there
    /// is nothing false about the number and suppressing it would throw away the
    /// record. Only the CAPTION is wrong: "chance of hitting" is present tense
    /// over a game that stopped. Alex ruled option C (Thu 2026-09-10, via
    /// Fable-5): keep the numbers, change three words.
    ///
    /// It reads ``isSuspendedAndStarted`` and NOT ``isSuspended``, for #4021's
    /// reason: event 416569 sat at `status='suspended'` four days before kick-off,
    /// and captioning a fixture nobody has played "last quoted chance" is the same
    /// false settled claim one size smaller.
    ///
    /// 🔴 DELIBERATELY NOT TENSED FOR A FINISHED GAME. "chance of hitting" is
    /// present tense over a completed game too, but that is a different wording
    /// call and Alex has not made it: on a final this card draws the actual value
    /// and a ✓/– beside every rung, so the caption reads as the historical quote
    /// it is. Widening the predicate to `!canStillBeGraded` would change every
    /// settled props card in the app on a ruling that covered abandoned ones.
    static func propsChanceCaption(
        _ status: String?, commenceTime: Date?, now: Date = Date()
    ) -> String {
        isSuspendedAndStarted(status, commenceTime: commenceTime, now: now)
            ? "last quoted chance"
            : "chance of hitting"
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

    /// The line an event page prints where its market sections would have been.
    ///
    /// #3821 — THE SENTENCE IS TENSED, and it was written only for a game that
    /// had not started. On the FINAL Cardinals 10 — Rockies 8 (15305472) it read
    /// *"No prediction markets for this game YET"* under a hero saying
    /// `FINAL · Cardinals Win`, promising a market that can never arrive. That is
    /// #3465's defect exactly, one card lower on the same page: #3465 tensed the
    /// score chart's unit-mismatch note on the same question and this sentence
    /// was missed. Alex's standing ruling is that settled means settled, and it
    /// binds an empty state's copy as tightly as it binds a hero.
    ///
    /// 🔴 THE SETTLED LINE DELIBERATELY DOES NOT SAY WHY, and that is the whole
    /// of the wording decision. This empty state covers two populations that the
    /// view cannot tell apart: a game no venue ever listed, and — per
    /// `EventDetailView`'s own note on the branch (#1092) — "an aged-out closed
    /// game whose Kalshi/odds markets have expired". "No venue covered this game"
    /// is false for the second, which HAD markets that we no longer hold. So the
    /// settled reading drops the false promise and claims nothing in its place.
    /// Trading a sentence that is wrong for a sentence that is merely quiet is
    /// the trade; inventing a cause we did not measure would be a new #3821.
    ///
    /// Takes the raw status rather than a `settled` flag so the status test stays
    /// in this file. Every other reading of "is it over?" on native already comes
    /// from ``isFinished``, and a caller that computes the boolean itself is one
    /// more place the app can disagree with itself about what `closed` means.
    static func noGameMarketsLine(status: String?) -> String {
        isFinished(status)
            ? "No prediction markets for this game."
            : "No prediction markets for this game yet."
    }
}
