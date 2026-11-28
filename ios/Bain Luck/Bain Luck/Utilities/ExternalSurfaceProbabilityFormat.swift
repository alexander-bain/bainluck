import Foundation

/// Unified probability formatting across all external Apple surfaces:
/// Home Screen widgets, Lock Screen widgets, Live Activities, Apple Watch app & complications,
/// and the App Clip shared widget reading layer.
///
/// Rules:
/// - Any open-market probability below 1% (`0 <= p < 0.01`) reads `"<1%"`.
/// - Any open-market probability above 99% (`0.99 < p <= 1`) reads `">99%"`.
/// - An open market never renders `"0%"` or `"100%"` (even from a whole-percent integer).
/// - Missing probability copy reads `"No recent probability"`.
nonisolated enum ExternalSurfaceProbabilityFormat {
    static let missingProbabilityText = "No recent probability"

    static func isSubOne(_ probability: Double?) -> Bool {
        guard let probability, probability.isFinite, probability >= 0 else { return false }
        return probability < 0.01
    }

    static func isAboveNinetyNine(_ probability: Double?) -> Bool {
        guard let probability, probability.isFinite, probability <= 1 else { return false }
        return probability > 0.99
    }

    /// Format an open-market fractional probability (`0.0 ... 1.0`), preserving server-paired
    /// `renderedPercent` inside `1 ... 99` when supplied while always guarding `< 0.01` and `> 0.99`.
    static func openProbability(_ probability: Double?, renderedPercent: Int? = nil) -> String? {
        guard let probability, probability.isFinite, probability >= 0, probability <= 1 else {
            return nil
        }
        if isSubOne(probability) { return "<1%" }
        if isAboveNinetyNine(probability) { return ">99%" }
        if let renderedPercent {
            return openWholePercent(renderedPercent)
        }
        let scaled = probability * 100.0
        return openWholePercent(Int(scaled.rounded()))
    }

    /// Format a whole-percent integer (`0 ... 100`) for an open market or pregame mark,
    /// overriding `0` / `100` (and any `subOne` / `aboveNinetyNine` / raw probability threshold)
    /// to `"<1%"` / `">99%"`.
    static func openWholePercent(
        _ percent: Int?,
        probability: Double? = nil,
        subOne: Bool = false,
        aboveNinetyNine: Bool = false
    ) -> String? {
        if subOne || isSubOne(probability) { return "<1%" }
        if aboveNinetyNine || isAboveNinetyNine(probability) { return ">99%" }
        guard let percent, (0...100).contains(percent) else { return nil }
        if percent <= 0 { return "<1%" }
        if percent >= 100 { return ">99%" }
        return "\(percent)%"
    }

    /// Value without trailing `"%"` for ultra-compact slots (`"<1"`, `">99"`, `"64"`).
    static func openCompactValue(
        _ percent: Int?,
        probability: Double? = nil,
        subOne: Bool = false,
        aboveNinetyNine: Bool = false
    ) -> String? {
        guard let formatted = openWholePercent(
            percent,
            probability: probability,
            subOne: subOne,
            aboveNinetyNine: aboveNinetyNine
        ) else {
            return nil
        }
        return formatted.hasSuffix("%") ? String(formatted.dropLast()) : formatted
    }

    /// Gauge fill share (`0.005 ... 0.995`) aligned with sub-1% and >99% labels.
    static func gaugeShare(
        _ percent: Int?,
        subOne: Bool = false,
        aboveNinetyNine: Bool = false
    ) -> Double {
        if subOne || (percent.map { $0 <= 0 } ?? false) { return 0.005 }
        if aboveNinetyNine || (percent.map { $0 >= 100 } ?? false) { return 0.995 }
        guard let percent else { return 0.5 }
        return min(max(Double(percent) / 100.0, 0.005), 0.995)
    }
}
