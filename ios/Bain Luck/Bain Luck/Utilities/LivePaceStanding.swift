import Foundation

/// #9708 — whether a served live pace may be drawn as a projection on this page.
///
/// `pace.projected_total` is the score so far run forward over the whole game
/// (`total_scored / fraction_elapsed`, `routes/events.py::_estimate_game_pace`),
/// so it inherits two ways of saying something false:
///
/// 1. **Scoreless.** Before anyone scores it is exactly 0 at every elapsed
///    fraction — `0` is not `nil`, so a presence-only guard drew "PACE 0" and
///    "−6.0 vs pre-game". Web withholds it (#6831); so does this.
/// 2. **An older score.** The pace rides the `/game-markets` body, the header's
///    score rides the live event. Rage shake #164 (BOS @ NYY WC G1, 15319563)
///    showed "PACE 0 · 0 scored" under a 1–0 header. A pace whose score is not
///    the scoreboard's is a projection from a game state the page no longer
///    shows, and it is withheld rather than drawn beside the header it
///    contradicts.
/// 3. **No time left to run forward.** The estimator caps elapsed time at the
///    whole game, so from the end of regulation `fraction_elapsed` is 1 and
///    `projected_total` is the tally itself. #9930 (PHI @ ATL WC G2, 15321782,
///    Top 10th at 3–3) printed "PACE 6 · 6 scored" — a total a tied game cannot
///    finish on. Web refuses on the same evidence (`>= 1`, PR #9932); a pace
///    that omits the fraction reads as it always did.
///
/// The scoreboard is the page's own (the header's numbers). When the page has no
/// scoreboard there is nothing for the pace to contradict, so rule 2 does not
/// apply.
nonisolated enum LivePaceStanding {
    /// The pace's score equals the scoreboard the page prints, or the page
    /// prints none.
    static func agrees(_ pace: GameMarketPace, scoreboardHome: Int?, scoreboardAway: Int?) -> Bool {
        guard let home = scoreboardHome, let away = scoreboardAway else { return true }
        return pace.totalScored == home + away
    }

    /// Regulation has run out: the projection divides by the whole game and
    /// repeats the score so far (#9930).
    static func clockRanOut(_ pace: GameMarketPace) -> Bool {
        guard let elapsed = pace.fractionElapsed else { return false }
        return elapsed >= 1
    }

    /// A projection with standing: served, something scored, scored at the
    /// scoreboard's score, and regulation time still left to run it over.
    static func projection(_ pace: GameMarketPace?, scoreboardHome: Int?, scoreboardAway: Int?) -> (projected: Double, scored: Int)? {
        guard let pace, let projected = pace.projectedTotal, let scored = pace.totalScored,
              scored > 0,
              !clockRanOut(pace),
              agrees(pace, scoreboardHome: scoreboardHome, scoreboardAway: scoreboardAway)
        else { return nil }
        return (projected, scored)
    }
}
