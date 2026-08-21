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
/// The multiply happens BEFORE the rounding, in `Double`. That is load-bearing:
/// `0.565 * 100` is `56.49999999999999`, not `56.5`, so the honest answer is 56
/// in all three runtimes. Anything that "corrects" that with a decimal type
/// would print 57 and silently leave the contract.
nonisolated func renderedPercent(_ probability: Double?) -> Int? {
    guard let probability, probability.isFinite else { return nil }
    return Int((probability * 100).rounded())
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
