import Foundation

/// Quote delivery is independent of the sports phase. The server decides
/// whether this event has an eligible open contract (including its time window)
/// and may refuse with 409/503; the existing polling plan remains the fallback.
/// Final/closed events stay on their settlement path in this release.
nonisolated enum EventPriceStreaming {
    static func isEligible(_ status: String?) -> Bool {
        status == "scheduled" || status == "live" || status == "suspended"
    }
}
