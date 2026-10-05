import Foundation

/// A canonical entity identity, separate from Discover's story and grouping keys.
nonisolated enum StoryContinuationDestination: Hashable, Sendable {
    case event(Int)
    case futures(Int)
}

/// Public identity-only Handoff. The receiving phone loads its own current detail.
nonisolated enum StoryContinuation {
    static let activityType = "com.bainluck.view-story"

    static func url(for destination: StoryContinuationDestination) -> URL? {
        let path: String
        let id: Int
        switch destination {
        case .event(let value):
            path = "events"
            id = value
        case .futures(let value):
            path = "futures"
            id = value
        }
        guard id > 0 else { return nil }
        return URL(string: "https://bainluck.com/\(path)/\(id)")
    }

    static func destination(from url: URL?) -> StoryContinuationDestination? {
        guard let url, let id = Int(url.lastPathComponent), id > 0 else { return nil }
        let components = url.pathComponents.filter { $0 != "/" }
        guard components.count == 2 else { return nil }
        let destination: StoryContinuationDestination
        switch components[0] {
        case "events": destination = .event(id)
        case "futures": destination = .futures(id)
        default: return nil
        }
        guard Self.url(for: destination)?.absoluteString == url.absoluteString else { return nil }
        return destination
    }

    @MainActor static func configure(_ activity: NSUserActivity, destination: StoryContinuationDestination) {
        let url = Self.url(for: destination)
        activity.title = "Bain Luck story"
        activity.webpageURL = url
        activity.userInfo = nil
        activity.isEligibleForHandoff = url != nil && activity.activityType == activityType
        activity.isEligibleForSearch = false
        activity.isEligibleForPublicIndexing = false
        #if os(iOS) || os(watchOS)
        activity.isEligibleForPrediction = false
        #endif
    }
}
