import Foundation

/// A game-market row whose number was already a CERTAINTY before this game began.
///
/// #6595's native half. The web twin of this contradiction crowns a winner
/// (`New York Yankees — Won` over a live 2nd-inning hero) and is UX's under
/// notice 41. The phone does something different and, for a reader, no better:
/// it draws the same row as a **filled bar at 100%**, which is a picture of a
/// live distribution making a claim about a game that is still being played.
///
/// Photographed on production 2026-09-16 21:27Z (native/197), iPhone 17 at phone
/// width, event `15313117` NYY @ MIN. Hero: `LIVE`, `Top 13th`, **4 – 4**.
/// Additional Markets, ~1,500pt down the same page:
///
///     New York Yankees vs. Minnesota Twins
///     New York Yankees              ▓▓▓▓▓▓▓▓  100%   · 17h ago
///
/// `GET /api/events/15313117/game-markets` → `other[]` served that row as
/// `probability: 1.0`, `observed_at: 2026-09-16T04:08:01Z` — **13.5 hours before
/// the 17:40Z first pitch** — from a stale weekly Polymarket container attached
/// to today's event. The attachment is a matching defect and is not ours (D35,
/// #2693); lane1's `7103f6d79` gates the *verdict* fields at serve time.
///
/// 🔴 THAT GATE DOES NOT REACH THIS. It nulls `is_winner` / `resolution_source`;
/// it does not withdraw the ROW, and the phone never read those two fields in the
/// first place — `GameMarketOther` decodes neither. So on iOS the served fix
/// changes nothing a reader can see, and keying this predicate on
/// `resolution_source` would tie it to a field that is about to read null on
/// exactly the specimen. It keys on what the row says about itself instead.
///
/// ## Decidable from the row alone
///
/// No ground truth is consulted and none is needed. A price of 1.0 is not a
/// forecast — it is a settlement — and a settlement recorded before the first
/// pitch cannot be a settlement OF this game. The row refutes itself.
///
/// ## Both clauses are load-bearing, and each has a live negative control
///
/// Measured against production at 21:4xZ on the same afternoon, over ten live
/// events (32 `other[]` rows). Dropping either clause would reach a row that is
/// telling the truth:
///
/// | row | certainty? | pre-kickoff? | verdict |
/// |---|---|---|---|
/// | `15313117` Yankees 1.0 @ 04:08Z | yes | yes (−13.5h) | **frozen** |
/// | `15313117` Minnesota 0.99 @ 21:33Z | ~yes | **no** (in-game) | live price — kept |
/// | `15313184` Melo 0.585 / Braga 0.415 @ 20:55Z | **no** | yes (−5m) | pregame forecast — kept |
///
/// The 0.99 row is a genuine live price on a team about to win in the 13th, and a
/// certainty-only rule would freeze it. The 0.585/0.415 pair is an honest
/// pre-kickoff quote nobody has re-polled, and a staleness-only rule would freeze
/// both legs of a coherent market. Only the conjunction names the lying row.
///
/// ## What this deliberately does NOT claim
///
/// * **Nothing is deleted.** #2086 removed a price-band DELETION from this very
///   card and recorded why: it "DELETED rather than declared, so the reader was
///   given a blank where an honest statement belonged" (#2019). This decides
///   which TREATMENT a row gets — `SpecialEventMarketsView` already has an honest
///   one for a frozen price, `SettledQuote.prefix` with no bar — never whether the
///   row exists.
/// * **Not the pregame page.** On an event that has not started, *every* row
///   predates kick-off, so the clause says nothing there and the predicate stays
///   silent by construction (``EventState/hasStarted(commenceTime:now:)``). A
///   certainty on an unplayed fixture is a real question (#6381's territory) with
///   a population nobody here has measured; it is not claimed.
/// * **Not the finished page.** A settled event already routes every row to the
///   settled treatment through `isGameFinished`, which is better — it says so once,
///   for the whole card. This is only the arm that gate cannot see.
/// * **Not a verdict.** Native has no "Won"/"Lost" treatment on this card (#3752's
///   named native gap). Freezing the row states what the number IS; it does not
///   claim who won, which on a live game is exactly the claim that must not be made.
///
/// `now` is an argument (gotcha #44).
nonisolated enum PreKickoffCertainty {

    /// How close to 0 or 1 a price has to be before it has stopped forecasting.
    ///
    /// Tight on purpose. A pre-kickoff **0.99** is a heavy favourite and a real
    /// forecast — the venue is still quoting a game it expects to be played — so
    /// the band admits only what is arithmetically indistinguishable from
    /// certainty. The production specimen serves exactly `1.0`; the epsilon is
    /// here for float round-tripping through JSON, not to widen the rule.
    static let certaintyEpsilon = 0.0005

    /// Is this number an absolute certainty rather than a forecast?
    static func isCertainty(_ probability: Double) -> Bool {
        probability >= 1.0 - certaintyEpsilon || probability <= certaintyEpsilon
    }

    /// Does this row's number belong to a time before the game it is printed on?
    ///
    /// Strictly before: a quote stamped AT the first pitch is the opening price,
    /// which is about this game.
    static func wasObservedBeforeKickoff(observedAt: String?, commenceTime: Date?) -> Bool {
        guard let commenceTime, let observedAt, let at = observedAt.asDate else { return false }
        return at < commenceTime
    }

    /// Should this row be drawn as a frozen quote instead of a live price?
    ///
    /// The event arm and the row arm are both required, and they ask different
    /// questions — the event's, whether a live distribution is the right picture
    /// at all; the row's, whether THIS number is part of it.
    static func isFrozen(
        probability: Double,
        observedAt: String?,
        commenceTime: Date?,
        eventStatus: String?,
        now: Date = Date()
    ) -> Bool {
        // A finished event already draws every row frozen, and a page that has
        // not started has no live distribution to be wrong about.
        guard !SettledQuote.isSettled(eventStatus) else { return false }
        guard EventState.hasStarted(commenceTime: commenceTime, now: now) else { return false }

        return isCertainty(probability)
            && wasObservedBeforeKickoff(observedAt: observedAt, commenceTime: commenceTime)
    }
}
