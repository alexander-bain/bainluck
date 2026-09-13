import Foundation

/// `renderedPercent` overrides the INTEGER, not the rule.
///
/// UX-P114: a card printing two sides of one question decides both percents
/// together, or the two independently-correct numbers sum to 101 (see
/// `renderedDuelPercents` and `contracts/rendered_percent.json`). Callers that
/// hold the server's card-level integer pass it here instead of rounding again.
///
/// The `<1%` / `>99%` guards still run on the PROBABILITY, because they are a
/// claim about the value rather than about which arithmetic produced the integer.
func formatProbability(_ value: Double, renderedPercent: Int? = nil) -> String {
    let pct = value * 100
    if pct < 1 { return "<1%" }
    if pct > 99 { return ">99%" }
    if let renderedPercent { return "\(renderedPercent)%" }
    return "\(Int(pct.rounded()))%"
}

/// The NUMBER half of a printed probability, for the surfaces that draw the "%"
/// separately (#5899). Input is percentage POINTS, not a 0–1 fraction.
///
/// `formatProbability` owns the app's marker rule and ~77 call sites use it. Two
/// cannot, because they do not draw one string: `ProbabilityNumber` sets the
/// figure and the "%" as two Texts at different sizes, and the futures hero draws
/// a 52pt figure. Both interpolated `Int(pct.rounded())` and so printed **0%** for
/// an outcome the venue was still pricing — "Lowest temperature in Buenos Aires on
/// September 13?" served five outcomes at 0.0005, and the page said `0%` on the
/// hero and on `#1` while saying `<1%` on `#2`–`#5`, in one frame, with its own
/// chart table saying `0.1%`.
///
/// ONLY THE LOW END MOVES, and that asymmetry is measured rather than tidy.
/// `formatProbability` also guards the top with `>99%`, and that half deliberately
/// does NOT come along: 749,007 outcomes of RESOLVED futures markets sit above
/// 0.99 and the leader row of each is the settled winner, so `>99%` would hedge a
/// decided question across that whole population to fix nothing anybody has seen.
/// `0%` on a priced outcome is a false claim; `100%` on a resolved winner is the
/// result.
///
/// A stored exact zero keeps printing `0`, for the same reason in reverse. #5837
/// ruled a served `0.0` reads `<1%` because the golf feed quotes on a
/// three-decimal grid, so its zero was a rounding floor. Here
/// `futures_outcomes.current_probability` is `numeric` and holds `0.0005`: a zero
/// that arrives here is a measured zero, and absence is
/// `formatProbabilityOrDash`'s dash and stays so.
func percentNumber(_ percent: Double) -> String {
    if percent > 0 && percent < 1 { return "<1" }
    return "\(Int(percent.rounded()))"
}

/// The absent-value marker for a number we do not have. `ladderPercent` already
/// returns this for a nil rung; the two spellings must not drift, and
/// `MissingProbabilityRenderTests` fails if they do.
let absentProbabilityMarker = "\u{2014}"

/// A probability we do not have is not a probability of zero.
///
/// `formatProbability(x ?? 0)` renders "<1%" — a confident claim that the outcome
/// is nearly impossible — for a row whose price simply never arrived. The backend
/// serialises "no price" and "priced at exactly zero" identically as `null`, so no
/// client can tell those apart and none may pretend to.
///
/// Callers holding a genuine `Double` keep calling `formatProbability` directly;
/// this is for the ones holding an optional straight off the wire.
func formatProbabilityOrDash(_ value: Double?, renderedPercent: Int? = nil) -> String {
    guard let value else { return absentProbabilityMarker }
    return formatProbability(value, renderedPercent: renderedPercent)
}

/// Format a future date as a compact countdown: "2h 15m", "35m", "3d 5h".
func formatCountdown(from date: Date) -> String? {
    let interval = date.timeIntervalSinceNow
    guard interval > 0 else { return nil }

    let totalMinutes = Int(interval / 60)
    let days = totalMinutes / 1440
    let hours = (totalMinutes % 1440) / 60
    let minutes = totalMinutes % 60

    if days > 0 {
        return hours > 0 ? "\(days)d \(hours)h" : "\(days)d"
    } else if hours > 0 {
        return minutes > 0 ? "\(hours)h \(minutes)m" : "\(hours)h"
    } else if minutes > 0 {
        return "\(minutes)m"
    } else {
        return "<1m"
    }
}

/// Convert an American moneyline to implied probability from 0.0 to 1.0.
func moneylineToProbability(_ ml: Int) -> Double {
    if ml > 0 {
        return 100.0 / Double(ml + 100)
    } else {
        let abs = Double(abs(ml))
        return abs / (abs + 100.0)
    }
}
