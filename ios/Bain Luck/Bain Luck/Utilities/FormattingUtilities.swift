import Foundation

/// The percentage string native prints for a probability. See
/// `contracts/rendered_percent.json`, `printed_cases` — the band is contract
/// rows now, not two hand-picked thresholds, and both runtimes are driven
/// through every row of them.
///
/// `renderedPercent` overrides the INTEGER, not the rule.
///
/// UX-P114: a card printing two sides of one question decides both percents
/// together, or the two independently-correct numbers sum to 101 (see
/// `renderedDuelPercents` and `contracts/rendered_percent.json`). Callers that
/// hold the server's card-level integer pass it here instead of rounding again.
///
/// The `<1%` / `>99%` guards still run on the PROBABILITY, because they are a
/// claim about the value rather than about which arithmetic produced the integer.
///
/// ** THE BAND IS DERIVED FROM THE ROUNDING RESULT, NOT FROM A THRESHOLD. **
/// This read `if pct < 1 { "<1%" }` / `if pct > 99 { ">99%" }`, and web's
/// `formatProbabilityPercent` — the same decision, written from the same
/// ruling — reads `rounded <= 0 && prob > 0` / `rounded >= 100 && prob < 1`.
/// They are not the same function, and UX-P192 found the four places they
/// disagree by trying to print one weather number the same way twice:
///
///   * `0.005` printed `<1%` here and `1%` on web — and 0.005 is not a corner
///     case on `/weather`, it is where four live temperature buckets sat.
///   * `0.994` printed `>99%` here and `99%` on web.
///   * an exact `0` printed `<1%`, asserting that something impossible is
///     merely unlikely — the precise inverse of the error UX-P046 exists to
///     prevent, and the one direction a formatter must never invent.
///   * an exact `1` printed `>99%`, taking certainty away from a settled market
///     ("settled means settled", Alex).
///
/// The threshold form also could not survive a non-finite input: `Int(nan)`
/// traps in Swift, so the guard below is a crash the old shape was one bad
/// payload away from.
func formatProbability(_ value: Double, renderedPercent: Int? = nil) -> String {
    guard value.isFinite else { return "—" }

    let rounded = renderedPercent ?? Int((value * 100).rounded())

    // Strictly inside the interval, but rounding would claim a boundary.
    if rounded <= 0 && value > 0 { return "<1%" }
    if rounded >= 100 && value < 1 { return ">99%" }

    return "\(rounded)%"
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
