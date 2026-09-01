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
