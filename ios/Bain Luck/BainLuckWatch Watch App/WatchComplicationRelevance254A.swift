import Foundation
#if canImport(Bain_Luck)
@testable import Bain_Luck
#endif

extension WatchComplicationSnapshot {
    /// #12316 / 254: A — map the Watch Smart Stack snapshot to its relevance state at `now`.
    func relevanceState254A(now: Date) -> GameRelevanceState254A {
        if WatchMatchupReading217.finalHasPassed(self, now: now) {
            return .other
        }
        if let rect = validatedRectangularReading(now: now) {
            switch rect.kind {
            case .liveForecast:
                return .live
            case .scheduledForecast:
                return .scheduled(commenceTime: rect.commenceTime, startIsTbd: false)
            case .finalResult:
                return .finalResult(observedAt: rect.observedAt)
            case .futureForecast:
                return .other
            }
        }
        if let circ = validatedCircularReading(now: now) {
            switch circ.kind {
            case .score:
                return .live
            case .forecast:
                return circ.stateLabel == "Live" ? .live : .other
            case .final:
                return .finalResult(observedAt: circ.observedAt)
            }
        }
        return .other
    }

    /// #12316 / 254: A — Smart Stack relevance score and duration at `now`.
    func relevanceSpec254A(now: Date) -> WidgetRelevanceSpec254A {
        WidgetRelevanceRule254A.spec(for: relevanceState254A(now: now), at: now)
    }

    /// #12316 / 254: A — future relevance-tier transition dates for the Watch Smart Stack timeline.
    func relevanceBoundaryDates254A(now: Date) -> [Date] {
        WidgetRelevanceRule254A.boundaryDates(for: relevanceState254A(now: now), now: now)
    }
}
