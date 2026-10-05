import Foundation

/// A reported reading, never a new observation inferred from fetch time.
nonisolated struct WatchDiscoveryCardPresentation {
    let outcome: String?
    let probability: String?
    let result: String?
    let observation: String
    let spokenObservation: String
    let observationValue: String

    init(reading: WatchDiscoveryReading, now: Date) {
        let name = reading.outcomeName?.trimmingCharacters(in: .whitespacesAndNewlines)
        outcome = name.flatMap { $0.isEmpty ? nil : $0 }
        if reading.isSettled {
            probability = nil
            let winner = reading.winner?.trimmingCharacters(in: .whitespacesAndNewlines)
            result = winner.flatMap { $0.isEmpty ? nil : "Result: \($0)" }
                ?? "Settled · result unavailable"
        } else {
            result = nil
            let validProbability = reading.probability.flatMap {
                $0.isFinite && (0...1).contains($0) ? $0 : nil
            }
            probability = outcome == nil ? nil : renderedPercent(validProbability).map {
                (Double($0) / 100).formatted(.percent.precision(.fractionLength(0)))
            }
        }
        let age = WatchObservationAge(observedAt: reading.observedAt, now: now)
        observation = age.compactText.map { "Observed \($0)" }
            ?? "Observation time unavailable"
        spokenObservation = age.spokenText.map { "Observed \($0)" }
            ?? "Observation time unavailable"
        observationValue = age.compactText == nil ? "unavailable"
            : reading.observedAt.map { ISO8601DateFormatter().string(from: $0) } ?? "unavailable"
    }
}
