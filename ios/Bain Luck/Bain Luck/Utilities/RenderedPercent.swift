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
