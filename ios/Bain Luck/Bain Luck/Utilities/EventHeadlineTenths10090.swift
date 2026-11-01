import Foundation

/// #10090 — ONE-DECIMAL HEADLINES ON THE EVENT PAGE (ALEX-DECISIONS item 39:
/// "I'd like to see tenths of a probability point, b/c it might help to make
/// the page feel \"alive\"").
///
/// The iPhone twin of the web's `frontend/lib/tenthsOptIn.ts` digit rules, so
/// the two clients print the same tenth for one probability:
///
///   * tenths come from the adopted probability; no invented digit.
///   * a complement pair is normalised by its total and the second side is
///     DERIVED (`1000 - home`), so the pair sums to 100.0. Rounding `1 - p` on
///     its own printed 36.8 / 63.3 at p = 0.3675.
///   * the `<1` / `>99` bands stay, symmetric about the pair: 0.5 through 99.5
///     print, anything nearer a boundary takes the marker. Exact 0 / 1 print
///     plainly, as `formatProbability` does.
///
/// Event page headline and chart tip only. Cards, the scrub readout and a
/// finished line's end keep `formatProbability`'s whole numbers, and a settled
/// hero prints its verdict, not this.
nonisolated enum EventHeadlineTenths10090 {

    /// The probability in tenths of a point, rounded half up as JavaScript's
    /// `Math.round(Number((p * 1000).toFixed(6)))` does: the six-decimal step
    /// first, so 0.3675 is 367.5 and not 367.49999…
    static func tenths(_ p: Double) -> Int {
        let scaled = ((p * 1000) * 1_000_000).rounded() / 1_000_000
        return Int((scaled + 0.5).rounded(.down))
    }

    /// One side's printed string for its tenths `t` of probability `p`.
    static func text(tenths t: Int, probability p: Double) -> String {
        if p <= 0 { return "0%" }
        if p >= 1 { return "100%" }
        if t < 5 { return "<1%" }
        if t > 995 { return ">99%" }
        return "\(t / 10).\(t % 10)%"
    }

    /// The headline pair. `away` nil is a withheld side (a draw-priced sport,
    /// #5271): the home side prints alone, un-normalised, as on web.
    static func pair(home: Double, away: Double?) -> (home: String, away: String?) {
        guard let away, away.isFinite else {
            return (text(tenths: tenths(home), probability: home), nil)
        }
        let total = home + away
        guard total >= 0.99, total <= 1.01 else {
            return (text(tenths: tenths(home), probability: home),
                    text(tenths: tenths(away), probability: away))
        }
        let pHome = home / total
        let tHome = tenths(pHome)
        return (text(tenths: tHome, probability: pHome),
                text(tenths: 1000 - tHome, probability: 1 - pHome))
    }
}
