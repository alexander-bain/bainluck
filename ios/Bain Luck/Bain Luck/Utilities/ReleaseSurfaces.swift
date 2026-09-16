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

    /// The Higher/Lower prediction game and everything that advertises it:
    /// Discover's "Today's Challenge" card, Discover's resolution digest
    /// ("10 predictions resolved"), and My Stuff's accuracy/streak summary.
    ///
    /// Off for the initial release. `Play` currently leads to "No challenge
    /// cards right now", and the digest and the summary are that same unfinished
    /// experience reporting on itself — so they were occupying the top of the
    /// first screen a new reader sees while promoting a dead end.
    ///
    /// Turning this back on is the whole restore: no other edit is needed.
    static let predictionsExperienceEnabled = false
}
