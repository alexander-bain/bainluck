import SwiftUI

/// #12307 — Bain Luck's App Clip: a bainluck.com game or market link opens its
/// page without installing the app, with Apple's offer to get the full app.
///
/// The invocation arrives as a web-browsing user activity (a tapped link, a QR
/// code, Safari's banner). The clip reads one public detail, the saved widget's
/// (`ClipLoader12307`), and refreshes it every minute while it's open.
@main
struct BainLuckClipApp: App {
    @State private var model = ClipModel12307()

    var body: some Scene {
        WindowGroup {
            ClipPageView12307(model: model)
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    model.open(activity.webpageURL)
                }
        }
    }
}

@Observable
final class ClipModel12307 {
    private(set) var subject: SavedWidgetSubject10875?
    private(set) var load: ClipLoad12307 = .loading
    /// The last refresh failed while an earlier answer is still on screen.
    private(set) var lastUpdateFailed = false
    private(set) var invoked = false

    /// How long the clip waits for an invocation before saying it has no page.
    static let invocationWait: Duration = .seconds(3)
    static let refreshEvery: Duration = .seconds(60)

    func open(_ url: URL?) {
        invoked = true
        let next = ClipInvocation12307.subject(from: url)
        guard next != subject || load == .loading || load == .unsupported else { return }
        subject = next
        load = next == nil ? .unsupported : .loading
        lastUpdateFailed = false
    }

    /// Called when no invocation has arrived in `invocationWait`.
    func noInvocation() {
        #if DEBUG
        // Xcode's `_XCAppClipURL` is normally delivered as the user activity; a
        // simulator launch from the command line may only carry it in the
        // environment.
        if let raw = ProcessInfo.processInfo.environment["_XCAppClipURL"] {
            open(URL(string: raw))
            return
        }
        #endif
        if !invoked { load = .unsupported }
    }

    func refresh() async {
        guard let subject else { return }
        let next = await ClipLoader12307.load(subject, fetch: ClipLoader12307.productionFetch)
        guard subject == self.subject else { return }
        // A failed refresh keeps the page it had; the reading goes on ageing on
        // its own clock, and the page says it couldn't update.
        if next == .unreachable, case .detail = load {
            lastUpdateFailed = true
            return
        }
        load = next
        lastUpdateFailed = false
    }
}
