import Foundation

/// What a team page's game row may claim, from one place.
///
/// #6444 — Alex, on his own team page: *"the Red Sox team page … shows the
/// team's next 5 games, but no associated probabilities, not even for the game
/// which starts in an hour. Similarly, the 'Recent' section shows no
/// probabilities."* Both halves were client-side; the server serves a number on
/// 8 of those 10 rows (see ``SearchEvent/winProbability``).
///
/// This is the Swift half of `frontend/lib/teamGames.ts`, and it exists for that
/// file's reason rather than as a tidy-up: **a score is not a result, and the
/// current probability of a settled game is not a pre-game expectation.** Both
/// rules are one `if` away from being got wrong at a render site, and the web
/// learned each of them from a shipped defect (#3791, and `RecentGameCard`'s
/// docstring). Native had neither rule, drew no number at all, and so had not
/// yet had the chance to get them wrong out loud.
///
/// Every predicate here refuses fail-closed: an unrecognised status, a
/// half-arrived score and an absent probability each print *less*, never a
/// confident wrong thing.
enum TeamGameRow {

    /// A team-relative FINAL. Minted only when something with standing said the
    /// game is over AND both scores are present — the `teamResult` contract.
    struct Result: Equatable {
        let teamScore: Int
        let oppScore: Int

        var won: Bool { teamScore > oppScore }
        var tied: Bool { teamScore == oppScore }
        /// "W" / "L" / "T", the web card's own vocabulary.
        var char: String { tied ? "T" : (won ? "W" : "L") }
    }

    /// The grade-our-call line under a finished row.
    enum Expectation: Equatable {
        /// "we had them at 63%".
        case had(Double)
        /// "Upset — beat 78% odds" — the team won from a pre-game price web
        /// treats as against them.
        case upset(Double)
    }

    /// Web's upset threshold, `TeamGameCards.tsx`: `teamWon && pre < 0.35`.
    /// `TeamGameRowWebParity6444Tests` reads that file and asserts the number
    /// rather than restating it here on trust.
    static let upsetThreshold = 0.35

    // MARK: - Orientation

    /// Which side of the row is the page's team.
    ///
    /// The served `is_home` wins. The name comparison is kept only as the
    /// fallback for a payload that omits it — it is the thing that breaks when
    /// two rails spell one club two ways, which is the class this page has been
    /// shipping all week (#6447).
    static func isHome(_ event: SearchEvent, teamName: String) -> Bool {
        event.isHome ?? (event.homeTeam == teamName)
    }

    /// The other club's name, from the payload where it states one.
    static func opponent(_ event: SearchEvent, teamName: String) -> String {
        if let served = event.opponent, !served.isEmpty { return served }
        return isHome(event, teamName: teamName) ? event.awayTeam : event.homeTeam
    }

    /// Team-relative score, whenever BOTH sides are present. Not a verdict —
    /// a suspended match carries the last score play reached, and half a score
    /// is no score at all (the partial-line trap, CERT-752).
    static func score(_ event: SearchEvent, teamName: String) -> (team: Int, opp: Int)? {
        guard let home = event.homeScore, let away = event.awayScore else { return nil }
        let home_ = isHome(event, teamName: teamName)
        return (team: home_ ? home : away, opp: home_ ? away : home)
    }

    // MARK: - What the row may claim

    /// The team-relative final, or nil when no final may be claimed.
    static func result(_ event: SearchEvent, teamName: String) -> Result? {
        guard SettledQuote.isSettled(event.status) else { return nil }
        guard let pair = score(event, teamName: teamName) else { return nil }
        return Result(teamScore: pair.team, oppScore: pair.opp)
    }

    /// The probability a row may PRINT AS A PRICE — the team-relative blend on
    /// anything not yet settled, and nothing on anything settled.
    ///
    /// 🔴 The settled refusal is the whole point of this function and is
    /// measured, not stylistic: on 2026-09-15 the team brief served 0.079 /
    /// 0.999 / 0.036 for three completed games whose own event pages served
    /// `hero_probability` 0.0 / 1.0 / 0.0 with `source: "settled"`. Printing the
    /// brief's number would put a different answer on two screens one tap apart,
    /// and the wrong one would be the smaller, more confident-looking screen.
    static func livePrice(_ event: SearchEvent) -> Double? {
        guard !SettledQuote.isSettled(event.status) else { return nil }
        return event.winProbability
    }

    /// The call we made, printed under a final we can actually state.
    ///
    /// Gated on ``result(_:teamName:)`` for `RecentGameCard`'s reason: the
    /// pre-game number stays true whatever happened, but printed beside a
    /// non-result it reads as a verdict on one, which is how the web card came
    /// to say "we had them at 40%" about a game whose score never arrived.
    static func expectation(_ event: SearchEvent, teamName: String) -> Expectation? {
        guard let result = result(event, teamName: teamName) else { return nil }
        guard let pre = event.pregameWinProbability else { return nil }
        if result.won && pre < upsetThreshold { return .upset(pre) }
        return .had(pre)
    }
}
