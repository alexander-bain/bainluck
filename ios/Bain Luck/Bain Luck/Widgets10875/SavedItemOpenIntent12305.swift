#if os(iOS)
import AppIntents
import Foundation

/// #12305 — what pressing "My game" does. It opens the app, so the system runs
/// `perform()` in the app's process, and it lands through the same door as
/// Siri's "Open Game or Market" (`IntentRouteHandoff10873`), which refuses
/// anything but a game, market or My Stuff link.
///
/// The app and the widget both compile this file (and the door): a control's
/// app-opening action must be known to both. A system `OpenURLIntent` in its
/// place ran and opened nothing, from the extension or as the action itself.
struct OpenSavedItemIntent12305: AppIntent {
    static let title: LocalizedStringResource = "Open Saved Game or Market"
    static let openAppWhenRun: Bool = true
    /// Only the control runs it. Shortcuts already offers "Open Game or Market".
    static let isDiscoverable = false

    @available(iOS 26.0, *)
    static var supportedModes: IntentModes { .foreground }

    @Parameter(title: "Link")
    var link: URL

    init() {}

    init(link: URL) {
        self.link = link
    }

    @MainActor
    func perform() async throws -> some IntentResult {
        IntentRouteHandoff10873.shared.post(link)
        return .result()
    }
}
#endif
