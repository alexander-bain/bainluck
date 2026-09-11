import Foundation

/// The whole percent this app prints for a probability — native's arm of
/// `contracts/rendered_percent.json` (#1933).
///
/// ## Why a one-line function has a contract behind it
///
/// The server takes a graded card's drift fingerprint at exactly this
/// resolution, so that a refused judgment is always explicable to the person who
/// was looking at the card: "the number on screen changed". If native prints 57
/// where the server fingerprinted 56, that sentence is false at precisely the
/// values where it is hardest to be right — the verdict is refused for drift
/// nobody can see, or accepted against a card that visibly moved.
///
/// Three runtimes print this number and no import spans them, so the shared unit
/// is the table in `contracts/rendered_percent.json` and each implementation is
/// driven through every row of it (ruling 021). `RenderedPercentContractTests`
/// executes this arm; the jest contract suite asserts that test's case table
/// still equals the contract, because the Swift gate does not run in CI and a
/// runtime check nobody runs is not a check.
///
/// `Double.rounded()` defaults to `.toNearestOrAwayFromZero`, which is half-up
/// over the non-negative domain probabilities live in — the same rule as
/// JavaScript's `Math.round` and as the server's `floor(x + 0.5)`, and
/// deliberately NOT Python's built-in `round`, which is banker's rounding and
/// shipped wrong once already.
///
/// The scaling happens BEFORE the rounding, in `Double`. That is load-bearing.
///
/// ## Why the scale is 1000/10 and not 100 (#3867, contract version 5)
///
/// This comment used to say the opposite: that `0.565 * 100` being
/// `56.49999999999999` made **56** "the honest answer in all three runtimes", and
/// that anything correcting it "with a decimal type would print 57 and silently
/// leave the contract". The parity worry was right and is preserved — the scaling
/// worry was not.
///
/// `* 100` is half-up on the double the wire value BECAME, not on the number it
/// SENT. The venues quote on a half-percent grid, so `.xx5` is the common case
/// here, and `* 100` lands a hair below the boundary for some of those values and
/// exactly on it for others: `0.585` printed 59 while `0.565` printed 56 — one
/// half rounding up, its neighbour down, for a reason no reader can see. Scaling
/// by 1000 first recovers the quoted decimal, so a half rounds up, always.
///
/// This is still `Double`, still the same operations as the other two runtimes,
/// so it is NOT the decimal type the old note warned about — parity was
/// re-measured, not assumed. Exactly four three-decimal wire values move: 0.145,
/// 0.285, 0.565, 0.575. And the rule changed in the CONTRACT first, which is the
/// only way this line is allowed to change.
nonisolated func renderedPercent(_ probability: Double?) -> Int? {
    guard let probability, probability.isFinite else { return nil }
    return Int((probability * 1000 / 10).rounded())
}

/// A two-outcome field is a complement pair when its members sum into this band.
///
/// 1.01 is not a new number: `card_integrity.display_scale` already uses exactly
/// it as the two-outcome "true binary" threshold. This is that constant made
/// SYMMETRIC, and the missing lower half was itself half the defect — a pair
/// summing to 0.99 printed 99 and nothing in the system considered that wrong.
private let complementMin = 0.99
private let complementMax = 1.01

nonisolated func isComplementPair(_ probabilities: [Double?]) -> Bool {
    guard probabilities.count == 2 else { return false }
    let values = probabilities.compactMap { $0 }.filter { $0.isFinite }
    guard values.count == 2 else { return false }
    let total = values[0] + values[1]
    return total >= complementMin && total <= complementMax
}

/// The whole percents this app prints for ONE CARD's served outcomes — the
/// card-level half of `contracts/rendered_percent.json` (#2060).
///
/// ## Why the scalar rule above was not enough
///
/// A surface prints a CARD, and a card has a SUM. Alex's 08-20 gold session served
/// `Los Angeles D 0.925 / Colorado 0.075`, which `renderedPercent` turns into 93
/// and 8 — both correct, and 101 together. Kalshi quotes a complement pair on a
/// HALF-CENT grid, so `p * 100` lands on `.5` for **both sides at once** and
/// half-up rounds both up. Measured on production 2026-08-21, 10,198 of 21,524
/// open two-outcome markets rendered a sum other than 100, 8,982 of them at 101.
///
/// A complement pair is normalized by its true total, index 0 is rounded ONCE, and
/// index 1 is DERIVED as `100 - index0`. Index 0 is the card's headline, so it is
/// the number that survives untouched and the derived point lands on the side
/// nobody is quoting. Everything that is not a complement pair renders exactly as
/// before — the contract table pins that direction as hard as the other.
nonisolated func renderedCardPercents(_ probabilities: [Double?]) -> [Int?] {
    guard !probabilities.isEmpty else { return [] }
    guard isComplementPair(probabilities),
          let first = probabilities[0], let second = probabilities[1] else {
        return probabilities.map { renderedPercent($0) }
    }
    let total = first + second
    guard let leader = renderedPercent(first / total) else {
        return probabilities.map { renderedPercent($0) }
    }
    return [leader, 100 - leader]
}

/// The two whole percents a GAME card prints, returned as `[away, home]` —
/// version 3 of `contracts/rendered_percent.json` (UX-P114).
///
/// ## Why the card rule above needed a positional sibling
///
/// `renderedCardPercents` assumes SERVED ORDER, where index 0 is the headline
/// because the labeling serializers sort descending first. A game card does not
/// sort: away is always drawn left and home always right, because those positions
/// carry meaning a probability ranking would destroy.
///
/// It is still the most exact complement pair in the product — `routes/feed.py`
/// derives the away side as `round(1.0 - current_home_prob, 6)` — so the defect
/// fires on a provable condition: when `home * 100` lands exactly on `.5`, both
/// sides round up and the strip prints 101. It can never print 99. Measured on
/// production 2026-08-21 over the 414 scheduled/live events in the feed's window:
/// 34 (8.2%) printed 101, including Green Bay @ Denver and Toronto FC @ Inter
/// Miami.
///
/// ## The favourite is the side that survives
///
/// A duel has no served order to inherit a headline from, so the replacement rule
/// is the one the card rule expresses: the number a reader anchors on is left
/// untouched and the derived point lands on the underdog. Always-away-first would
/// instead move the favourite half the time — on Green Bay @ Denver it prints 67
/// for a side whose own correct value is 68.
///
/// The SERVER now decides this and sends it as
/// `current_odds.{away,home}_rendered_percent`, because four surfaces draw this
/// strip. This function is the local fallback for a payload from before that field
/// existed, and it lives in the contract so the fallback cannot drift from the
/// served answer.
nonisolated func renderedDuelPercents(
    away awayProbability: Double?,
    home homeProbability: Double?
) -> [Int?] {
    let pair = [awayProbability, homeProbability]
    guard isComplementPair(pair),
          let away = awayProbability, let home = homeProbability else {
        return [renderedPercent(awayProbability), renderedPercent(homeProbability)]
    }
    if away >= home {
        return renderedCardPercents([away, home])
    }
    let flipped = renderedCardPercents([home, away])
    return [flipped[1], flipped[0]]
}

/// The two whole percents a game strip prints, choosing between the SERVED pair
/// and the local one — `[away, home]`, and the last word on both (#2279).
///
/// ## Both served values or neither
///
/// UX-P114 gave every game-card surface `current_odds.{away,home}_rendered_percent`
/// so the two sides of one question are decided ONCE, by the server. Three surfaces
/// adopted it and all three coalesced **per side**:
///
///     let awayPct = odds.awayRenderedPercent ?? duelFallback[0]
///     let homePct = odds.homeRenderedPercent ?? duelFallback[1]
///
/// A payload carrying one field and not the other therefore prints a served value
/// beside a locally derived one, and that re-opens the very 101 UX-P114 shipped to
/// close — from the other direction. On `0.505 / 0.495` the served home is 51 and a
/// naively derived away is 50. The struct's own comment
/// (`Models/CommonTypes.swift`) says these fields are optional precisely because a
/// Discover response is CACHED and this build can be installed against an older
/// deploy; a response written across a partial rollout is the case the fallback
/// exists for, and it is exactly the case the per-side form gets wrong.
///
/// So the two served values are ONE decision. Either both are present and both are
/// used, or the pair falls back WHOLE to `renderedDuelPercents`. The web arm states
/// the same rule in `lib/eventKeyStats.ts` and the event page states it inline;
/// this is the native surfaces' shared copy of it (ruling 021 — share the DECISION,
/// not the ingredient).
///
/// ## The served pair describes `current_odds` AND NOTHING ELSE
///
/// A caller whose probabilities came from somewhere else — `opening_odds`, a
/// history row, a chart point — must pass `nil` for both served values. Handing in
/// `current_odds`' rounding beside another source's probability prints a mismatched
/// pair that still sums to 100, so no sum guard can see it. `servedAway`/`servedHome`
/// are separate parameters rather than a `CurrentOdds` so that the caller has to
/// make that choice at the branch that knows the answer.
nonisolated func duelPercents(
    away awayProbability: Double?,
    home homeProbability: Double?,
    servedAway: Int?,
    servedHome: Int?
) -> [Int?] {
    if let servedAway, let servedHome {
        return [servedAway, servedHome]
    }
    return renderedDuelPercents(away: awayProbability, home: homeProbability)
}

/// The one whole percent a compact row prints beside an away-first
/// `"<away> vs <home>"` title — the FIRST-NAMED side's.
///
/// ## Why a lone number needs a rule at all
///
/// #4306: `SearchView.searchEventRow` built its title away-first — the house
/// convention, 6 of the 7 sites that build one — and then drew
/// `homeProbability` beside it with no label. A reader anchors a lone number to
/// the name they read first, so every scheduled row stated the opposite of the
/// market. Measured on production 2026-09-09, 6 of 6 US Open rows, worst case
/// "Botic van de Zandschulp vs Alexander Zverev — 86%" for a side priced at
/// 13.8%. The finished arm of that same function already renders its score
/// away-first, so one row disagreed with itself depending on whether the match
/// had started.
///
/// ## Why it returns a percent and not a probability
///
/// The number a reader compares against the event page they tap through to has
/// to be the same INTEGER that page drew, and `duelPercents` is the last word on
/// that (#2279). Rounding again here would reintroduce the off-by-one from the
/// other direction.
///
/// ## A payload with only the home side still gets a number
///
/// `away_probability` accompanied `home_probability` on 53 of 53 rows carrying
/// odds across four production search queries (2026-09-09), so this is a
/// belt-and-braces path rather than a live case. It exists because the row it
/// replaces drew a number whenever HOME was present, and a fix for a
/// wrong-sided number must not turn into a missing one: `renderedDuelPercents`
/// answers `nil` for a pair that is not a complement, which is what a
/// home-only payload is. Deriving the complement is the move the two other
/// single-sided readers already make (`MenuBarView`, `TeamDetailView`).
///
/// The derivation is here and not at the call site so that the rule and its
/// edge case are one testable thing — CI compiles no Swift (#4302), so a
/// branch that lives in a view body is a branch no gate can reach.
/// Returns the probability as well as the percent because the caller needs
/// both and must not derive either a second time: `formatProbability` runs its
/// `<1%` / `>99%` guards on the PROBABILITY (they are a claim about the value,
/// not about the rounding), so a call site holding only the integer cannot
/// format the number correctly, and a call site deriving the Double itself is a
/// second copy of the rule this function exists to hold.
nonisolated func firstNamedSideNumber(
    away awayProbability: Double?,
    home homeProbability: Double?,
    servedAway: Int?,
    servedHome: Int?
) -> (probability: Double, percent: Int)? {
    guard let away = awayProbability ?? homeProbability.map({ 1 - $0 }) else { return nil }
    guard let percent = duelPercents(
        away: away,
        home: homeProbability,
        servedAway: servedAway,
        servedHome: servedHome
    )[0] else { return nil }
    return (probability: away, percent: percent)
}

/// The same lone number, for a row that may be priced by `current_odds` OR by the
/// blend the server already computed — preferring `current_odds` when both exist.
///
/// ## Why the fallback needs a function and not an `??` at the call site
///
/// #4967: `SearchView.searchEventRow` drew a percentage only when `current_odds`
/// was present, so an unfinished row whose price the server HAD already blended
/// printed nothing at all. Measured on production 2026-09-10 across eight
/// queries: of 84 unfinished rows, 29 drew no number, and 20 of those 29 carried
/// a complete `hero_probability` / `hero_probability_away` pair the phone was
/// throwing away. The remaining 9 carry neither and must keep printing nothing
/// (#4794 — a row with no reading states no reading).
///
/// ## The served percents belong to `current_odds`, so the hero arm cannot see them
///
/// `duelPercents`' contract above is explicit that `servedAway`/`servedHome`
/// describe `current_odds` and nothing else: pairing that rounding with another
/// source's probability prints a mismatched pair that still sums to 100, which no
/// sum guard can catch. The hero arm therefore passes `nil` for both and lets
/// `renderedDuelPercents` derive. That is enforced HERE rather than trusted at the
/// call site, because the call site is a view body and CI compiles no Swift
/// (#4302) — a rule that lives in a `View` is a rule no gate can reach.
///
/// Preference order is `current_odds` first so that no row which renders correctly
/// today changes: the hero pair is strictly a fallback for rows drawing nothing.
nonisolated func firstNamedSideNumber(
    oddsAway: Double?,
    oddsHome: Double?,
    servedAway: Int?,
    servedHome: Int?,
    heroAway: Double?,
    heroHome: Double?
) -> (probability: Double, percent: Int)? {
    if let fromOdds = firstNamedSideNumber(
        away: oddsAway,
        home: oddsHome,
        servedAway: servedAway,
        servedHome: servedHome
    ) {
        return fromOdds
    }
    return firstNamedSideNumber(
        away: heroAway,
        home: heroHome,
        servedAway: nil,
        servedHome: nil
    )
}
