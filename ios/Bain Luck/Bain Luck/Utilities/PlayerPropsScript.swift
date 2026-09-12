import CoreGraphics
import Foundation

/// THE SCRIPT's baseline on a player-prop rung: where the market opened, drawn
/// as a tick on the rung's own track.
///
/// #4577 — THE APP HAD NO BASELINE AT ALL. `GET /api/events/{id}/game-markets`
/// has served `pregame_mark` per prop since #195, and `GameMarketPlayerProp`
/// did not decode it. So every rung on the phone printed the live number alone:
/// the reader was shown where a market IS with no way to see where it STARTED,
/// which is the whole of "THE SCRIPT vs THE DIVERGENCE" (product priority 3).
///
/// THE SHAPE IS NOT A NEW DESIGN. It is Alex's ruling for The Open 2026, already
/// shipped on web and quoted from `frontend/components/event/PropsSection.tsx`:
///
/// > binary → a divergence bar: the pregame mark is a tick on the track, the
/// > current probability is the fill — the gap IS the story, visible without
/// > reading a number.
///
/// A player-prop rung is exactly that shape — a track, a fill, a percentage — so
/// the fold is one-to-one and adds no bespoke component (standing notice 35).
/// "Visible without reading a number" is also why nothing here prints a caption
/// or a second percentage: the gap carries the meaning, and a sentence
/// explaining it would be the diagnostic prose notice 34 forbids.
///
/// WHY THE WEB'S FOLD IS NOT PORTED WITH IT. Web hides mark-less rows behind
/// "More props (N)" (D111). That disclosure belongs to THE SCRIPT, whose row
/// promises a pregame number and is an empty row without one — `PropsSection`
/// says so itself: *"only THE SCRIPT promises a pregame number, so only THE
/// SCRIPT has this hole."* The app's rung promises a LIVE price and a grade; the
/// mark is additional context on top. Measured on the served payload for
/// Cubs–Pirates `15310365` (142 props, 2026-09-12, replicating this card's own
/// colon-split grouping):
///
/// | | |
/// |---|---|
/// | rungs | 141 |
/// | rungs with no pregame mark | 66 (47%) |
/// | …of those, rungs carrying a live price | **66 (all of them)** |
/// | ladders with no mark on any rung | 18 of 44 |
/// | **ladders marked on some rungs but not others** | **11** |
///
/// Folding on the mark would therefore hide 66 genuinely priced rungs and punch
/// holes in the middle of 11 cumulative 2+/3+/4+ ladders, whose progression is
/// the thing a ladder is for. So the app draws a tick where there is one and
/// nothing where there is not — the mark-less rung keeps its price, its bar and
/// its verdict, and simply makes no claim about the script.
///
/// WHY NOT FALL BACK TO ANYTHING. Two fallbacks look available and both
/// fabricate. `current` is forbidden by #4530's own measurement (median 4pt gap,
/// up to 22.5pt, on an event that had not started). `opening_over_probability`
/// looks safer and is not the app's to apply: `_resolve_pregame_mark`
/// (`routes/events.py`) ALREADY falls back to it, so a null mark beside a
/// non-null opening means the server declined — the app second-guessing that
/// would put a number on screen the server refused to vouch for. (On the
/// specimen 44 rows are in exactly that state, which is a server-side defect
/// filed separately: two "rescue" prop builders never set `pregame_mark` at all.)
enum PlayerPropsScript {

    /// Where the pregame tick sits on the track, as a fraction of its width, or
    /// `nil` when no tick is drawn.
    ///
    /// Two rows draw nothing:
    ///
    /// - **no mark.** Absent and null are one case: the server omits the key on
    ///   rows built by its rescue paths and sends an explicit null elsewhere, and
    ///   `decodeIfPresent` collapses both to `nil` — the same collapse the web's
    ///   `pregame_mark == null` makes, so the two clients agree by construction.
    /// - **a finished game.** WHAT HIT is the settled state's story and it has
    ///   its own treatment (#4959's ✓/– verdict and final value). A pregame tick
    ///   under a graded rung is history competing with a result.
    ///
    /// A live game DOES draw one: the distance between tick and fill is THE
    /// DIVERGENCE, which is the point of showing it while play is on.
    ///
    /// The clamp is not defensive dressing. A probability outside 0...1 would
    /// place the tick off its own track, and the value arrives from a network
    /// payload, so the view cannot assume the range it renders into.
    static func tickFraction(pregameMark: Double?, isFinished: Bool) -> Double? {
        guard let mark = pregameMark, !isFinished else { return nil }
        guard mark.isFinite else { return nil }
        return min(max(0, mark), 1)
    }

    /// The tick's leading offset in points, CENTRED on its fraction of the track
    /// and clamped so it cannot hang off either end.
    ///
    /// Centring matters at the extremes: a tick drawn from its fraction as a
    /// leading edge reads a full tick-width late at 0% and would overhang the
    /// track at 100%. Clamping is what keeps a 0-or-1 mark legible rather than
    /// half-drawn, and `maxOffset` is floored at 0 so a track narrower than the
    /// tick — which `GeometryReader` can hand us for one layout pass — returns a
    /// real offset instead of a negative one.
    static func tickOffset(fraction: Double, trackWidth: CGFloat, tickWidth: CGFloat) -> CGFloat {
        let maxOffset = max(0, trackWidth - tickWidth)
        let centred = trackWidth * CGFloat(fraction) - tickWidth / 2
        return min(max(0, centred), maxOffset)
    }
}
