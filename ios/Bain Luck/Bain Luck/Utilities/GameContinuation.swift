import Foundation

/// A public identity-only Handoff contract, shared by the Watch sender and phone receiver.
/// Scores, probability snapshots and account credentials never cross this boundary.
nonisolated enum GameContinuation {
    static let activityType = "com.bainluck.view-game"

    static func url(eventID: Int) -> URL? {
        guard eventID > 0 else { return nil }
        return URL(string: "https://bainluck.com/events/\(eventID)")
    }

    static func eventID(from url: URL?) -> Int? {
        guard let url,
              let id = Int(url.lastPathComponent),
              let canonical = Self.url(eventID: id),
              url.absoluteString == canonical.absoluteString else { return nil }
        return id
    }

    @MainActor static func configure(_ activity: NSUserActivity, eventID: Int) {
        let destination = url(eventID: eventID)
        activity.title = "Bain Luck game"
        activity.webpageURL = destination
        activity.userInfo = nil
        activity.isEligibleForHandoff = destination != nil && activity.activityType == activityType
        activity.isEligibleForSearch = false
        activity.isEligibleForPublicIndexing = false
        #if os(iOS) || os(watchOS)
        activity.isEligibleForPrediction = false
        #endif
    }
}
