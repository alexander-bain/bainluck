import Foundation

/// Who won a finished event — asked ONCE, so no two native surfaces answer it
/// differently.
///
/// #4915 — every settled surface in the app derived the verdict inline from two
/// strict comparisons:
///
///     let homeWon = (event.homeScore ?? 0) > (event.awayScore ?? 0)
///     let awayWon = (event.awayScore ?? 0) > (event.homeScore ?? 0)
///
/// On a DRAW both of those are false, and false is the loser's answer. So a 1–1
/// Champions League match rendered as *both teams lost*: the hero greyed both
/// scores and degraded its "{Team} Win" slot to the bare word "Final", and the
/// card greyed both team names and both scores. The scoreline was right and the
/// page's own colour language contradicted it.
///
/// A draw is a RESULT — Alex's standing ruling is *settled means settled:
/// heroes show winners, cards show results* — and the missing concept, not the
/// missing string, was the bug. Two booleans cannot express three outcomes, so
/// the pair is replaced by one value that can.
///
/// ═══ THE SERVER ALREADY GRADED THIS ═══
///
/// `GET /api/events/{id}` serves `hero_settled_result` — `"home" | "away" |
/// "draw"`, minted by `backend/app/utils/settled_hero.py` and typed on the web
/// at `frontend/lib/types.ts` — and iOS decoded none of the `hero_*` family.
/// Where the server states a verdict the client uses it rather than re-deriving
/// one, which is the same rule the hero probability already follows (`settled`
/// outranks the blend, Q441/#1495).
///
/// The field is ABSENT, not null, on a game we cannot grade (`resolve_settled_hero`
/// returns nothing and the route omits the key), and the feed payload behind
/// `EventCardView` never carries it at all. Both are ordinary states, not
/// errors: `servedResult` is optional and the scores answer when it is missing.
///
/// ═══ WHY `undecided` IS NOT `draw` ═══
///
/// The load-bearing line in `resolve` is `guard home != nil, away != nil`. A
/// finished game we hold NO score for coalesces to `0 ?? 0` under the old
/// idiom, which is indistinguishable from a genuine 0–0 — so a rule that read
/// "equal scores ⇒ draw" off the coalesced pair would newly print **Draw** on
/// every scoreless settled row. `undecided` keeps those on today's neutral
/// "Final" and is a real state, never a zero (the `hero_probability` cascade's
/// `final_unresolved` says the same thing about the number).
enum EventOutcome: Equatable {
    /// The home side won.
    case home
    /// The away side won.
    case away
    /// The event is over and level. Nobody won and — the whole point — nobody
    /// lost.
    case draw
    /// Not finished, or finished with nothing that can name a result: no
    /// score held for one side, or an unrecognised verdict from the server.
    case undecided

    /// The three verdicts the server can state. Kept as strings rather than a
    /// `RawRepresentable` decode so an unrecognised value falls through to the
    /// scores instead of failing the whole event's decode — the same open-set
    /// discipline `EventState` applies to `status`.
    private static let servedHome = "home"
    private static let servedAway = "away"
    private static let servedDraw = "draw"

    /// The one derivation. `servedResult` is the authority when it is one of
    /// the three known verdicts; otherwise the scores decide.
    ///
    /// Gated on `EventState.isFinished` deliberately. The server only mints
    /// `hero_settled_result` for a finished event, so the two agree today; the
    /// guard is what keeps them agreeing if that ever stops being true, and it
    /// is the same status vocabulary every other settled treatment in the app
    /// reads (#4021: a status is not a phase).
    static func resolve(
        status: String?,
        homeScore: Int?,
        awayScore: Int?,
        servedResult: String? = nil
    ) -> EventOutcome {
        guard EventState.isFinished(status) else { return .undecided }

        switch servedResult {
        case servedHome: return .home
        case servedAway: return .away
        case servedDraw: return .draw
        default: break
        }

        guard let homeScore, let awayScore else { return .undecided }
        if homeScore > awayScore { return .home }
        if awayScore > homeScore { return .away }
        return .draw
    }

    /// Whether this side is the one that won. False on a draw for BOTH sides,
    /// which is correct and is why `isLoser` exists beside it rather than being
    /// spelled `!won`.
    func won(isAway: Bool) -> Bool {
        isAway ? self == .away : self == .home
    }

    /// Whether this side is the one that LOST — the question the loser's grey
    /// is actually asking, and the one `!won` gets wrong on a level result.
    func isLoser(isAway: Bool) -> Bool {
        switch self {
        case .home: return isAway
        case .away: return !isAway
        case .draw, .undecided: return false
        }
    }

    /// The word the hero's verdict slot prints, or `nil` when there is no
    /// verdict to state and the caller should fall back to its status label.
    ///
    /// "Draw" is the house word: the web's share meta already writes "a draw" /
    /// "drew" for this exact field (`frontend/lib/eventShareMeta.ts`), so the
    /// two clients say the same thing about the same event.
    var drawLabel: String? {
        self == .draw ? "Draw" : nil
    }
}
