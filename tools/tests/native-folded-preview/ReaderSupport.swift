// Standalone source-reader checks only. These small model surfaces replace
// SwiftUI/app dependencies; the XCTest file also runs against real app models
// in Native's build. They are not a model decoder or rendered-UI qualification.
import Foundation

nonisolated struct EventOdds: Decodable { var homeProbability: Double?; var awayProbability: Double?
    var homeRenderedPercent: Int?; var awayRenderedPercent: Int? }
nonisolated struct EventDetail: Decodable { let id: Int; let sport: String?; let status: String?
    var currentOdds: EventOdds?; var heroProbability: Double?; var heroProbabilityAway: Double?
    let heroProbabilitySource: String?; let blendFoldRevision: ServedFoldRevision? }
nonisolated struct AggregateLinePoint: Decodable { let timestamp: String; let homeProbability: Double }
nonisolated struct EventHistoryResponse: Decodable {
    let eventId: Int
    let status: String?
    let completedAt: String?
    let winProbHistory: [String: [WinProbHistoryPoint]]?
    let aggregateLine: [AggregateLinePoint]?
    let blendEdgePinned: Bool?
    let blendEdgeObservedAt: String?
    let blendEdgeFoldRevision: ServedFoldRevision?
    let historyFoldRevision: ServedFoldRevision?
}

nonisolated enum EventPriceStreaming {
    static func isEligible(_ status: String?) -> Bool { ["live", "scheduled", "suspended"].contains(status ?? "") }
}
nonisolated enum LiveEventPriceReconciliation {
    static func pairedFoldRevision(in event: EventDetail) -> FoldRevision? {
        guard EventPriceStreaming.isEligible(event.status), event.heroProbabilitySource == "blend",
              let p = event.heroProbability, p.isFinite, event.currentOdds?.homeProbability == p else { return nil }
        return event.blendFoldRevision?.revision
    }
}
extension String {
    nonisolated var asDate: Date? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = parser.date(from: self) { return date }
        parser.formatOptions = [.withInternetDateTime]
        return parser.date(from: self)
    }
}

nonisolated struct ScoringPlay {}
nonisolated struct ServedEvidence: Decodable { let kind: String; let coveredThrough: String? }
nonisolated struct WinProbHistoryPoint: Decodable {
    let timestamp: String; let homeProbability: Double?; let liveEdge: Bool?; let evidence: ServedEvidence?
}
nonisolated enum EventState {
    static func isFinished(_ status: String?) -> Bool { ["final", "completed", "cancelled"].contains(status ?? "") }
}
