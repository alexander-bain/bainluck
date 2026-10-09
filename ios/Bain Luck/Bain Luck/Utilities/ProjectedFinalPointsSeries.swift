import Foundation

/// Recorded, same-book full-game pairs only. Never derives forecasts or uses
/// valid_until as evidence of a new observation. Matches web #10239 semantics.
nonisolated struct ProjectedFinalPointsSeries: Equatable {
    enum Basis: String { case sameBookSameCaptureFullGameSpreadAndTotal }
    enum Kind { case recorded, synthetic }
    enum Phase { case before, during, after }
    enum WithheldReason { case incomplete, invalidPoints, belowActual, contradictsMoneyline }

    struct Pair {
        let at: Date
        let home: Double?
        let away: Double?
        let homeProbability: Double?
        /// Explicit caller classification; absence of a wire field is not proof.
        let kind: Kind
    }
    struct Actual: Equatable {
        let at: Date
        let home: Double
        let away: Double
    }
    struct Input {
        let sportKey: String
        let sourceKey: String
        let basis: Basis
        let pairs: [Pair]
        let actuals: [Actual]
        /// An observed kickoff, never the scheduled commence_time.
        let kickoffAt: Date?
        /// First observed game-state lower bound; not an estimated period marker.
        let scoreObservationStartAt: Date?
        let finalAt: Date?
        var asOf: Date
        var windowStartAt: Date?
        /// Actual request cutoff. Nil ONLY for an unbounded/full-history route.
        /// Current wire does not mark cutoff restamps; reject through cutoff+2m.
        let requestCutoffAt: Date?
    }
    struct Point: Equatable {
        let at: Date
        let home: Double
        let away: Double
        let holdEnd: Date
    }
    struct Withheld: Equatable {
        let at: Date
        let reason: WithheldReason
    }

    static let maxCaptureGap: TimeInterval = 3600
    static let cutoffRestampSlack: TimeInterval = 120
    let sourceKey: String
    let sourceName: String
    let phase: Phase
    let segments: [[Point]]
    let withheld: [Withheld]
    let actualSteps: [Actual]
    let start: Date
    let end: Date
    let latest: Point
    let latestActual: Actual?
    let latestIntervalUnavailable: Bool
    let yMax: Double
    var yTicks: [Double] { Array(stride(from: 0, through: yMax, by: 7)) }

    private static func isPoints(_ value: Double) -> Bool { value.isFinite && value >= 0 }
    private static func validTime(_ date: Date) -> Bool { date.timeIntervalSince1970.isFinite }
    private static func actual(at date: Date, in steps: [Actual]) -> Actual? {
        steps.last { $0.at <= date }
    }
    private static func isRecorded(_ pair: Pair, input: Input) -> Bool {
        guard pair.kind == .recorded, validTime(pair.at) else { return false }
        if let cutoff = input.requestCutoffAt {
            guard validTime(cutoff), pair.at > cutoff.addingTimeInterval(cutoffRestampSlack) else { return false }
        }
        return true
    }

    private static func pairRefusal(_ row: Pair) -> WithheldReason? {
        guard let home = row.home, let away = row.away else { return .incomplete }
        guard isPoints(home), isPoints(away) else { return .invalidPoints }
        if let probability = row.homeProbability, probability.isFinite,
           (probability > 0.5 && home < away) || (probability < 0.5 && home > away) {
            return .contradictsMoneyline
        }
        return nil
    }

    /// Nil omits this optional experiment for unsupported or unproven inputs.
    @MainActor
    static func build(_ input: Input) -> Self? {
        guard input.sportKey == "americanfootball_nfl",
              let sourceName = SourceLabels.sportsbookName(for: input.sourceKey),
              validTime(input.asOf) else { return nil }
        let floor = input.kickoffAt ?? input.scoreObservationStartAt
        guard [floor, input.finalAt, input.windowStartAt].compactMap({ $0 }).allSatisfy(validTime) else { return nil }
        let end = min(input.finalAt ?? input.asOf, input.asOf)
        let phase: Phase = input.finalAt.map { $0 <= input.asOf } == true ? .after
            : floor.map { $0 <= input.asOf } == true ? .during : .before
        let started = floor.map { $0 <= end } == true
        let defaultStart: Date
        if started, let floor {
            defaultStart = input.pairs.filter {
                isRecorded($0, input: input) && $0.at >= floor.addingTimeInterval(-3600) && $0.at < floor
            }.map(\.at).min() ?? floor
        } else {
            // #10796: a quiet pregame market can hold real forecasts older
            // than six hours. Keep that retained history; the existing gap
            // and last-observation rules still refuse to call it current.
            let firstForecast = input.pairs.filter {
                isRecorded($0, input: input) && $0.at <= end && pairRefusal($0) == nil
            }.map(\.at).min()
            defaultStart = min(end.addingTimeInterval(-6 * 3600), firstForecast ?? end)
        }
        let start = input.windowStartAt ?? defaultStart
        guard start <= end else { return nil }
        let actuals = input.actuals.filter {
            phase != .before && floor != nil &&
            validTime($0.at) && $0.at >= (floor ?? end) && $0.at <= end &&
            isPoints($0.home) && isPoints($0.away)
        }.sorted { $0.at < $1.at }

        // Keep invalid captures in order: they break a run instead of disappearing.
        let rows = input.pairs.enumerated().filter {
            isRecorded($0.element, input: input) && $0.element.at >= start &&
            $0.element.at <= end
        }
        // Explicit final filter avoids confusing the capture and completion clocks.
        let ordered = rows.filter { row in
            input.finalAt.map { row.element.at < $0 } ?? true
        }.sorted { lhs, rhs in
            lhs.element.at == rhs.element.at ? lhs.offset < rhs.offset : lhs.element.at < rhs.element.at
        }.map(\.element)
        func reason(_ row: Pair) -> WithheldReason? {
            if let refusal = pairRefusal(row) { return refusal }
            guard let home = row.home, let away = row.away else { return .incomplete }
            if let score = actual(at: row.at, in: actuals), home < score.home || away < score.away {
                return .belowActual
            }
            return nil
        }
        var segments: [[Point]] = []
        var withheld: [Withheld] = []
        var run: [Point] = []
        func closeRun() { if !run.isEmpty { segments.append(run); run = [] } }
        for (index, row) in ordered.enumerated() {
            if let refusal = reason(row) {
                withheld.append(Withheld(at: row.at, reason: refusal))
                closeRun()
                continue
            }
            guard let home = row.home, let away = row.away else { continue }
            let next = index + 1 < ordered.count ? ordered[index + 1] : nil
            let continues = next.map { reason($0) == nil && $0.at.timeIntervalSince(row.at) <= maxCaptureGap } ?? false
            run.append(Point(at: row.at, home: home, away: away, holdEnd: continues ? next!.at : row.at))
            if !continues { closeRun() }
        }
        closeRun()
        guard let latest = segments.last?.last else { return nil }
        let unavailable = ordered.last.map { reason($0) != nil } == true || end.timeIntervalSince(latest.at) > maxCaptureGap
        let forecastHigh = segments.flatMap { $0 }.map { max($0.home, $0.away) }.max() ?? 0
        let actualHigh = actuals.map { max($0.home, $0.away) }.max() ?? 0
        let yMax = max(7, ceil((max(forecastHigh, actualHigh) + 7 / 4.0) / 7) * 7)
        return Self(sourceKey: input.sourceKey, sourceName: sourceName, phase: phase,
                    segments: segments, withheld: withheld, actualSteps: actuals,
                    start: start, end: end, latest: latest, latestActual: actual(at: end, in: actuals),
                    latestIntervalUnavailable: unavailable, yMax: yMax)
    }

    /// Freeze the original window and clip both quantities, so inspection never
    /// acquires earlier offscreen points or reveals a future score/projection.
    @MainActor
    static func at(_ date: Date, input: Input) -> Self? {
        guard validTime(date) else { return nil }
        var clipped = input
        clipped.windowStartAt = input.windowStartAt ?? build(input)?.start
        clipped.asOf = min(date, input.asOf)
        return build(clipped)
    }
}
