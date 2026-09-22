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

/// The MAGNITUDE of a 24-hour move, to the one precision every badge that prints
/// a move must share. Input is percentage POINTS; the caller draws the direction
/// (an arrow or a sign) and the unit, which is why this returns no sign of its own.
///
/// #6931: `probability_change_24h` had five renderers in `ios/**` and they printed
/// one number four ways. Measured on `/api/futures/114175` (2026-09-18 ~11:0xZ),
/// Ciryl Gane served `0.005`:
///
/// | surface | rule it used | printed |
/// |---|---|---|
/// | futures hero badge | `Int((m * 100).rounded())` + `%` | **↑1%** |
/// | chart participant table (`changeLabel`) | `%.1f` + `%` | **+0.5%** |
/// | All Outcomes ladder (`DeltaBadge`) | `%.1f` + `pp` | **↗0.5pp** |
/// | related-futures pill (`MovementPill`) | `%.1f%%` | **0.5%** |
/// | movers card (`MoverCardView`) | `formatProbability` | **↑<1%** |
///
/// The first three are on ONE screen at once (`artifacts-native-021/`), and the
/// biggest type carried the wrong one. The hero's integer was not merely coarse:
/// its own gate admits a move at `abs >= 0.005`, so every move in `[0.5, 1.5)`
/// points printed `1%` and the smallest move it will ever show was DOUBLED.
///
/// One decimal, because that is what the renderer standing next to it on the same
/// screen already used and was already right. The hero moves to the table's rule;
/// the table does not move to the hero's.
///
/// THE UNIT IS NOT THIS FUNCTION'S BUSINESS and deliberately does not come along.
/// `DeltaBadge`'s `pp` is the technically exact word for a probability delta and is
/// also the only `pp` in the app, on a surface shared with Entertainment and
/// Politics; `%` is what the hero, the table and the pill already say to a casual
/// fan. Unifying the WORD is a copy decision across three surfaces, filed, not
/// smuggled in behind an arithmetic fix.
func deltaPointsNumber(_ points: Double) -> String {
    String(format: "%.1f", abs(points))
}

/// The futures hero badge's whole decision — whether to draw at all, and what
/// number to draw — as one value a test can call.
///
/// It lives here rather than inside `FuturesDetailView` because a `@ViewBuilder`
/// returning `some View` cannot be asserted on: while the gate and the string sat
/// in the view, the only thing tying a test to the hero was a source scan for the
/// call, and a scan cannot tell you what the badge SAYS. #6931's first cut had
/// exactly that hole — reverting the view to its integer rounding left all four
/// behavioural tests GREEN and only the scan red, because they were exercising a
/// copy of the arithmetic that the test file had written out for itself.
///
/// The `0.005` floor is the badge's own and is unchanged by #6931. Note it is NOT
/// shared with the chart's participant table, which has no floor: a served
/// `-0.0035` is drawn there and declined here. That asymmetry predates this and is
/// pinned rather than fixed.
///
/// Returns `nil` when the badge draws nothing. The arrow carries the direction, so
/// the string is an unsigned magnitude.
func futuresHeroMoveText(_ change: Double?) -> String? {
    guard let m = change, abs(m) >= 0.005 else { return nil }
    return "\(deltaPointsNumber(m * 100))%"
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

/// The two strings ONE two-sided row prints, rounded as a single decision.
///
/// #7984. `formatProbability`'s note above says a card printing two sides of one
/// question decides both percents together — and the event page's two source
/// lists were the callers that did not. `sourceContent` derives its away side as
/// an exact complement (`1 - homeProbability`), then drew the pair through two
/// independent `formatProbability` calls, so a venue quoting on the half-percent
/// grid put BOTH sides on `.5` and half-up rounded both up. Polymarket `0.585`
/// printed `42% 59%` on event 15316315, photographed at
/// `artifacts-native-020/n293-live-wta.png`, directly under a Sportsbooks row
/// reading `3% 97%`.
///
/// Measured over 408 production events the same day: **122 of 332** source rows
/// that print a numeric pair summed to 101, on 113 distinct events, plus 6 of 557
/// bookmaker rows. Every failure is 101 and none is 99, which is the signature of
/// both sides rounding up rather than of a data fault.
///
/// 🔴 **THE STRINGS, NOT THE INTEGERS.** `EventSourceLabelColumn` sizes the
/// numeric column from the strings the rows will actually print (#4208, #5271), so
/// the sizing pass and the draw pass have to ask ONE function or the column is
/// measured against text no row draws. Returning the formatted pair — rather than
/// the two `Int`s — is what makes that impossible to get wrong at a call site.
///
/// Pairing is `renderedDuelPercents`' decision, not this function's: it is gated on
/// ``isComplementPair``, so a bookmaker pair that is not a complement (the away
/// price is SERVED there, #5271) and a row whose away side is withheld entirely on
/// a draw-priced sport both render exactly as they do today.
func duelProbabilityStrings(
    away: Double?,
    home: Double
) -> (away: String, home: String) {
    let pair = renderedDuelPercents(away: away, home: home)
    return (
        formatProbabilityOrDash(away, renderedPercent: pair[0]),
        formatProbability(home, renderedPercent: pair[1])
    )
}

/// Format a future date as a compact countdown: "2h 15m", "35m", "3d 5h".
///
/// #7019 — `now` is a parameter, and it defaults so no existing caller moves.
/// It used to be read implicitly here as `timeIntervalSinceNow`, which made the
/// result a function of a hidden input: a caller could not pass a clock, a test
/// could not vary one, and `StatusBadge` could not depend on one changing. That
/// last one is the defect — a chip whose body reads nothing that ever changes is
/// a chip SwiftUI never re-renders, so it froze at the minute the row appeared.
/// `MinuteClock` is the thing that now changes; this signature is what lets the
/// badge read it.
func formatCountdown(from date: Date, now: Date = Date()) -> String? {
    let interval = date.timeIntervalSince(now)
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
