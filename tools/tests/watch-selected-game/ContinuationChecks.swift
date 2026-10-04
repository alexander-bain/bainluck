import Foundation

@MainActor func checkWatchContinuation() {
    precondition(GameContinuation.activityType == "com.bainluck.view-game")
    for id in [1, 2, Int.max] {
        let url = GameContinuation.url(eventID: id)
        precondition(url?.absoluteString == "https://bainluck.com/events/\(id)",
                     "Continuation publishes only the canonical event URL")
        precondition(GameContinuation.eventID(from: url) == id)
    }
    for id in [0, -1, Int.min] {
        precondition(GameContinuation.url(eventID: id) == nil, "Only positive event ids can continue")
    }
    precondition(GameContinuation.eventID(from: nil) == nil)
    let malformed = [
        "https://bainluck.com/events/0", "https://bainluck.com/events/-1",
        "https://bainluck.com/events/01", "https://bainluck.com/events/+1",
        "https://bainluck.com/events/1.0", "https://bainluck.com/events/9999999999999999999999999",
        "http://bainluck.com/events/1", "https://www.bainluck.com/events/1",
        "https://api.bainluck.com/events/1", "https://BAINLUCK.com/events/1",
        "https://bainluck.com:443/events/1", "https://user:password@bainluck.com/events/1",
        "https://bainluck.com/events/1?score=2", "https://bainluck.com/events/1#score",
        "https://bainluck.com/events/1?", "https://bainluck.com/events/1#",
        "https://bainluck.com/events/1/", "https://bainluck.com/events/1/score",
        "https://bainluck.com/events//1", "https://bainluck.com/event/1",
        "https://bainluck.com/events/%31", "/events/1", "events/1",
    ]
    for raw in malformed {
        precondition(GameContinuation.eventID(from: URL(string: raw)) == nil,
                     "Noncanonical continuation URL must be rejected: \(raw)")
    }
    let activity = NSUserActivity(activityType: GameContinuation.activityType)
    activity.userInfo = ["score": 9, "auth": "old-token", "event_id": 3]
    activity.isEligibleForSearch = true
    activity.isEligibleForPublicIndexing = true
    #if os(iOS) || os(watchOS)
    activity.isEligibleForPrediction = true
    #endif
    GameContinuation.configure(activity, eventID: 2)
    precondition(activity.webpageURL?.absoluteString == "https://bainluck.com/events/2")
    precondition(activity.title == "Bain Luck game" && activity.isEligibleForHandoff)
    precondition(!activity.isEligibleForSearch && !activity.isEligibleForPublicIndexing)
    #if os(iOS) || os(watchOS)
    precondition(!activity.isEligibleForPrediction)
    #endif
    precondition(activity.userInfo?.isEmpty != false, "Continuation carries no score, auth, or custom payload")
    GameContinuation.configure(activity, eventID: 0)
    precondition(activity.webpageURL == nil && !activity.isEligibleForHandoff,
                 "An invalid selection clears the previous continuation")
    precondition(activity.userInfo?.isEmpty != false)
    GameContinuation.configure(activity, eventID: Int.max)
    precondition(activity.isEligibleForHandoff && GameContinuation.eventID(from: activity.webpageURL) == Int.max)
    GameContinuation.configure(activity, eventID: -1)
    precondition(activity.webpageURL == nil && !activity.isEligibleForHandoff && activity.userInfo?.isEmpty != false)
    print("PASS: canonical positive-id continuation routes, malformed URL rejection, Handoff-only eligibility, no score/auth payload, invalid-selection clearing")
}
