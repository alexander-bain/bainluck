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

    /// The percent a feed card PRINTS, from a 0–1 fraction (#5837).
    ///
    /// `wholePercent` is the contract integer and does not move — the server
    /// fingerprints a graded card at exactly that resolution (`RenderedPercent`,
    /// #1933). What moves is the string beside it: interpolating the integer
    /// directly printed **`0%`** for Tom McKibbin, served at `0.004` and still in
    /// the Irish Open field, while the NCAAF card one scroll up on the same
    /// Discover screen printed `<1%`. The rounding was honest; the sentence it
    /// produced was not, because `0%` reads as "cannot happen" and `<1%` reads as
    /// "barely".
    ///
    /// So this delegates the marker to `formatProbability`, which is where the
    /// `<1%` / `>99%` rule has always lived and which the other 77 call sites in
    /// the app already use — those guards are "a claim about the value rather than
    /// about which arithmetic produced the integer", and the feed cards were the
    /// one surface making the claim without them.
    ///
    /// No clamp of its own, and that is measured rather than assumed: a first draft
    /// clamped the fraction here as well, and deleting that line changed no test
    /// and no output. `formatProbability` already guards BOTH ends on the value, so
    /// an independent-binary field summing past 100% (gotcha #23) prints `>99%` and
    /// never `104%`, and `wholePercent` still clamps the integer it returns. A
    /// clamp here would have been dead code with a guard test pinning it.
    ///
    /// One band moves beyond the reported specimen and is meant to: `0.005..<0.01`
    /// rounds to the integer `1` and is still under one percent, so it now reads
    /// `<1%` where it read `1%`. That is the marker doing its job — it is a claim
    /// about the VALUE — and it is what every other surface in the app already says
    /// about 0.6%.
    ///
    /// A wire `0.0` also prints `<1%`, deliberately. The tours quote on a
    /// three-decimal grid, so `0.000` is everything below 0.0005 and not a
    /// measured impossibility — and the card's own model takes a non-optional
    /// `Double`, so a genuinely ABSENT price never arrives here at all (that case
    /// is `formatProbabilityOrDash`'s dash, and stays that way).
    static func percentLabel(fromFraction fraction: Double) -> String {
        formatProbability(fraction, renderedPercent: wholePercent(fromFraction: fraction))
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
