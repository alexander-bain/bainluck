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

    /// A projection with standing: served, something scored, and scored at the
    /// scoreboard's score.
    static func projection(_ pace: GameMarketPace?, scoreboardHome: Int?, scoreboardAway: Int?) -> (projected: Double, scored: Int)? {
        guard let pace, let projected = pace.projectedTotal, let scored = pace.totalScored,
              scored > 0,
              agrees(pace, scoreboardHome: scoreboardHome, scoreboardAway: scoreboardAway)
        else { return nil }
        return (projected, scored)
    }
}
