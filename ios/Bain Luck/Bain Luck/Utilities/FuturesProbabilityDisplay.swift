import Foundation

/// #11616: futures search and detail use web probabilityParts' boundary rule.
/// Keep the existing field-level integer override; never round a selected subset
/// here. General Native formatProbability/percentNumber callers retain their own
/// established policies. Result labels are decided before this price formatter.
nonisolated func futuresProbabilityNumber(_ probability: Double, renderedPercent override: Int? = nil) -> String {
    guard probability.isFinite, let scalar = renderedPercent(probability) else { return "—" }
    let integer = override ?? scalar
    if integer <= 0 && probability > 0 { return "<1" }
    if integer >= 100 && probability < 1 { return ">99" }
    return String(integer)
}

nonisolated func futuresProbabilityLabel(_ probability: Double, renderedPercent: Int? = nil) -> String {
    let number = futuresProbabilityNumber(probability, renderedPercent: renderedPercent)
    return number == "—" ? number : number + "%"
}
