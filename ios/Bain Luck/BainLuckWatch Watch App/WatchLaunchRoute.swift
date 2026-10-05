import Foundation

/// The launcher opens the selection already owned by the app; it cannot replace it.
nonisolated enum WatchLaunchRoute {
    static let url = URL(string: "bainluck-watch://selected-game")!

    static func accepts(_ url: URL) -> Bool {
        url.absoluteString == Self.url.absoluteString
    }
}
