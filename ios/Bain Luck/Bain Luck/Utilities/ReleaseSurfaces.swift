import Foundation

/// Which not-yet-good surfaces the shipping build offers a reader.
///
/// One switch per surface, read by every entry point to it, so the surface is
/// hidden or shown as a WHOLE. Alex, 2026-09-15, on the phone build: "We should
/// hide the 'Today's Challenge' experience altogether until we've made it good,
/// including, obviously, the '10 predictions resolved' banner" — and, on My
/// Stuff, "We don't need the 'Predictions' row at the top of My Stuff if we're
/// pulling it out of Discover temporarily."
///
/// A flag and not a deletion, deliberately. The surfaces work; they are not
/// finished. Deleting them would make restoring one a re-implementation, and it
/// would invite deleting the DATA behind them, which is the one thing #6445
/// forbids — accounts, saved predictions and history are all preserved, and the
/// destination views stay reachable by route so nothing already linked 404s.
enum ReleaseSurfaces {

    /// The Higher/Lower prediction game and everything that advertises it.
    /// Five call sites, and the count is the point — #6445 converted the first
    /// three, and #6501 found the other two still live on build 13:
    ///
    ///   1. Discover's "Today's Challenge" card            (#6445)
    ///   2. Discover's resolution digest, "10 resolved"    (#6445)
    ///   3. My Stuff's accuracy/streak summary             (#6445)
    ///   4. My Stuff's signed-out wall — the two perk rows that SELL streaks
    ///      and history, plus the headline that led with them  (#6501)
    ///   5. Discover's "Stats" toolbar button, top-right of the FIRST screen,
    ///      linking the same `Route.predictionStats`          (#6501)
    ///
    /// Off for the initial release. `Play` currently leads to "No challenge
    /// cards right now", and the digest and the summary are that same unfinished
    /// experience reporting on itself — so they were occupying the top of the
    /// first screen a new reader sees while promoting a dead end.
    ///
    /// 🔴 THE SENTENCE THAT USED TO SIT HERE — "turning this back on is the
    /// whole restore: no other edit is needed" — WAS FALSE WHEN IT WAS WRITTEN,
    /// and it is what let 4 and 5 ship. A docstring claiming a flag covers a
    /// class is a census question about that class, not an answer to it; the
    /// unconverted call sites ARE the bug it says cannot exist. It is true now
    /// only because `PredictionsExperienceIsGatedEverywhere6501Tests` scans for
    /// a sixth — an ungated `Route.predictionStats` fails that scan.
    static let predictionsExperienceEnabled = false
}
