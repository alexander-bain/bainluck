import Foundation

/// #12316 / Ruling 254: A — shared Smart Stack relevance rule for iPhone and Apple Watch widgets.
///
/// Pure Foundation so the main app, `BainLuckWidget`, `BainLuckComplication`, and `BainLuckTests`
/// all compile and test the exact same scoring and timeline-boundary math.
nonisolated enum GameRelevanceState254A: Equatable, Sendable {
    case live
    case scheduled(commenceTime: Date?, startIsTbd: Bool)
    case finalResult(observedAt: Date?)
    case other
}

nonisolated struct WidgetRelevanceSpec254A: Equatable, Sendable {
    let score: Float
    let duration: TimeInterval

    static let zero = WidgetRelevanceSpec254A(score: 0, duration: 0)
}

nonisolated enum WidgetRelevanceRule254A {
    /// Pinned/selected game is live right now (highest Smart Stack priority).
    static let liveScore: Float = 100
    /// Pinned/selected game starts within 30 minutes.
    static let pregameScore: Float = 60
    /// General live-games widget when at least one game is live (below a reader's pinned game).
    static let liveGamesWidgetScore: Float = 40
    /// Finished game stays briefly elevated so the reader can catch the final score.
    static let recentFinalScore: Float = 25
    /// Idle, far-future, market, placeholder, or error states.
    static let idleScore: Float = 0

    static let pregameLeadWindow: TimeInterval = 30 * 60
    static let liveRelevanceDuration: TimeInterval = 2 * 3600
    /// Backstop duration if a scheduled snapshot crosses kickoff before a network refresh arrives.
    static let scheduledLiveFallbackWindow: TimeInterval = 3 * 3600
    static let finalCooldownWindow: TimeInterval = 60 * 60
    static let boundaryHorizon: TimeInterval = 7 * 24 * 3600

    /// Relevance score and duration for a single pinned/selected game widget at `now`.
    static func spec(for state: GameRelevanceState254A, at now: Date) -> WidgetRelevanceSpec254A {
        guard now.timeIntervalSinceReferenceDate.isFinite else { return .zero }
        switch state {
        case .live:
            return WidgetRelevanceSpec254A(score: liveScore, duration: liveRelevanceDuration)

        case .scheduled(let commenceTime, let startIsTbd):
            guard !startIsTbd,
                  let start = commenceTime,
                  start.timeIntervalSinceReferenceDate.isFinite else {
                return .zero
            }
            let untilStart = start.timeIntervalSince(now)
            if untilStart > pregameLeadWindow {
                return .zero
            }
            if untilStart > 0 {
                return WidgetRelevanceSpec254A(score: pregameScore, duration: untilStart)
            }
            let elapsedSinceKickoff = -untilStart
            if elapsedSinceKickoff < scheduledLiveFallbackWindow {
                return WidgetRelevanceSpec254A(
                    score: liveScore,
                    duration: scheduledLiveFallbackWindow - elapsedSinceKickoff
                )
            }
            return .zero

        case .finalResult(let observedAt):
            guard let observedAt,
                  observedAt.timeIntervalSinceReferenceDate.isFinite else {
                return .zero
            }
            let elapsed = now.timeIntervalSince(observedAt)
            guard elapsed >= 0, elapsed < finalCooldownWindow else {
                return .zero
            }
            return WidgetRelevanceSpec254A(
                score: recentFinalScore,
                duration: finalCooldownWindow - elapsed
            )

        case .other:
            return .zero
        }
    }

    /// Relevance for the general live-games widget (`BainLuckDesktopWidget`).
    /// Never promotes placeholder/redacted entries.
    static func liveGamesWidget(liveCount: Int, isPlaceholder: Bool) -> WidgetRelevanceSpec254A {
        guard !isPlaceholder, liveCount > 0 else { return .zero }
        return WidgetRelevanceSpec254A(score: liveGamesWidgetScore, duration: 15 * 60)
    }

    /// Future dates strictly after `now` (within 7 days) where the widget's relevance tier changes,
    /// so WidgetKit promotes before kickoff, at kickoff, and steps back down without waiting for a fetch.
    static func boundaryDates(for state: GameRelevanceState254A, now: Date) -> [Date] {
        guard now.timeIntervalSinceReferenceDate.isFinite else { return [] }
        let horizon = now.addingTimeInterval(boundaryHorizon)
        var candidates: [Date] = []

        switch state {
        case .scheduled(let commenceTime, let startIsTbd):
            guard !startIsTbd,
                  let start = commenceTime,
                  start.timeIntervalSinceReferenceDate.isFinite else {
                return []
            }
            candidates.append(start.addingTimeInterval(-pregameLeadWindow))
            candidates.append(start)
            candidates.append(start.addingTimeInterval(scheduledLiveFallbackWindow))

        case .finalResult(let observedAt):
            guard let observedAt,
                  observedAt.timeIntervalSinceReferenceDate.isFinite else {
                return []
            }
            candidates.append(observedAt.addingTimeInterval(finalCooldownWindow))

        case .live, .other:
            return []
        }

        return Array(Set(candidates.filter { $0 > now && $0 <= horizon })).sorted()
    }
}
