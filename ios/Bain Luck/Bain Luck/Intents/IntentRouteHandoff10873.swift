import Combine
import Foundation

/// #10873 — the one door an App Intent uses to open a screen.
///
/// An intent's `perform()` runs outside the view tree, so it cannot reach the
/// `NavigationCoordinator` the app owns as a `@StateObject`. Rather than a second
/// router, the intent hands over the same canonical link a widget, a notification
/// or a shared URL would (`bainluck://events/<id>`, `bainluck://futures/<id>`,
/// `bainluck://my-stuff`) and `ContentView` passes it to
/// `NavigationCoordinator.handleURL`. So a Siri open can only ever reach a screen
/// a real link could reach, and it lands exactly where that link lands.
///
/// Cold launch: `settledPosts` replays the current value when it is subscribed,
/// so a link posted before the window mounts is still delivered once. Warm: it
/// fires after the post completes (see `settledPosts`). `consume()` clears the
/// link, so a later remount never replays it.
///
/// Cancellation: an intent posts only after every parameter has resolved, so a
/// reader who backs out of a "Which one?" list leaves nothing here.
@MainActor
final class IntentRouteHandoff10873: ObservableObject {
    static let shared = IntentRouteHandoff10873()

    @Published private(set) var pendingURL: URL?

    /// Fires on the main queue once each post has COMPLETED. Subscribe to this,
    /// never to `$pendingURL` directly: `@Published` emits in `willSet`, so a
    /// subscriber that called `consume()` synchronously would read the value from
    /// BEFORE the post — and on an app that is already open, drop the link.
    var settledPosts: AnyPublisher<URL?, Never> {
        $pendingURL.receive(on: DispatchQueue.main).eraseToAnyPublisher()
    }

    /// Accepts only links built by `IntentLinks10873`; anything else is refused
    /// rather than routed, so this door cannot open an arbitrary URL.
    @discardableResult
    func post(_ url: URL) -> Bool {
        guard IntentLinks10873.isIntentLink(url) else { return false }
        pendingURL = url
        return true
    }

    /// Returns and clears the waiting link. With nothing waiting it assigns
    /// nothing: `@Published` emits on every assignment, nil over nil included,
    /// and `ContentView` calls this from its `settledPosts` handler — so an
    /// unconditional clear would re-trigger that handler forever, from the
    /// first mount, with no Siri use at all.
    func consume() -> URL? {
        guard let url = pendingURL else { return nil }
        pendingURL = nil
        return url
    }
}

/// The three links the intents may open. Each one is a case
/// `NavigationCoordinator.handleURL` already routes.
nonisolated enum IntentLinks10873 {
    static let myStuff = URL(string: "bainluck://my-stuff")!

    static func event(id: Int) -> URL? {
        guard id > 0 else { return nil }
        return URL(string: "bainluck://events/\(id)")
    }

    static func market(id: Int) -> URL? {
        guard id > 0 else { return nil }
        return URL(string: "bainluck://futures/\(id)")
    }

    static func isIntentLink(_ url: URL) -> Bool {
        if url == myStuff { return true }
        guard url.scheme == "bainluck",
              let host = url.host,
              host == "events" || host == "futures" else { return false }
        let parts = url.pathComponents.filter { $0 != "/" }
        guard parts.count == 1, let id = Int(parts[0]), id > 0 else { return false }
        return url.query == nil && url.fragment == nil
    }
}
