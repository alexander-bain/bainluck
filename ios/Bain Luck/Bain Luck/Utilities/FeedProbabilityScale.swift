import Foundation

/// The one place the feed's probability SCALE is converted for display.
///
/// Every probability and 24h movement the feed serves is a **0–1 fraction** —
/// `outcome.current_probability` passed through untouched (`routes/golf.py` →
/// `routes/feed.py`). The cards print percentage POINTS. That conversion was
/// written twice, and the two copies disagreed:
///
/// | card | probability | movement |
/// |---|---|---|
/// | `DiscoverConceptCard` | `clamped * 100` ✅ | `movement * 100`, floor 1pp ✅ |
/// | `DiscoverTournamentCard` | `probability.rounded()` ❌ | `movement`, floor 0.5 ❌ |
///
/// So the tournament card printed **`0%`** for every golf leader on Discover
/// (`Int(0.089.rounded())` is `0`; a favourite would need ≥50% to print even
/// `1%`), and its "+2.3pp today" mover line was gated at what is really 50
/// percentage points and so never fired (#2888, found mystery-shopping native/001).
/// The concept card's own header claims it reuses the tournament hero's treatment
/// "rather than inventing a second probability treatment" — it had in fact
/// silently corrected it, which is exactly how gotcha #129 reads from the inside.
///
/// This is the numeric seam only. The two cards keep their own glyphs — one says
/// `▲3`, the other `+3.0pp today` — because that is presentation, and forcing
/// them to share it would be a different (and wrong) kind of unification.
enum FeedProbabilityScale {

    /// Whole percent for display, from a 0–1 fraction.
    ///
    /// Clamped because an independent-binary field can sum past 100% (gotcha #23)
    /// and a card must not print `104%`.
    static func wholePercent(fromFraction fraction: Double) -> Int {
        let clamped = min(max(fraction, 0), 1)
        return Int((clamped * 100).rounded())
    }

    /// 24h movement in percentage POINTS, or nil when it is not worth a glance.
    ///
    /// Sub-point noise is suppressed rather than rounded to "+0", which reads as a
    /// measured non-move rather than as an absence. The 1-point floor matches the
    /// backend's own materiality gate for the tournament reason line
    /// (`abs(g["movement_24h"]) >= 0.01`), so the client never claims a move the
    /// server considered noise, nor hides one it called out.
    static func movementPoints(fromFraction fraction: Double?) -> Double? {
        guard let fraction else { return nil }
        let points = fraction * 100
        return abs(points) >= 1 ? points : nil
    }
}
