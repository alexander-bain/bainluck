import Foundation

/// Launch-argument affordances for the headless LOOK rig (#3157), in the shape
/// #3141 established for the notification prompt.
///
/// The class of defect this exists to end is "the rig's arguments are silently
/// inert". `tools/native-g1-shoot.sh` passed `-temp_screenshot_tab` and
/// `-temp_screenshot_counts` for weeks; no Swift file on master has ever read
/// either. They live only in a scaffold that has to be copied in, hooked up,
/// built, shot, deleted and grepped for residue — so the rig looked like it was
/// driving the app and was doing nothing, and every unattended shot was of
/// Discover because Discover is the default tab.
///
/// Both affordances below are pure, injectable functions over `UserDefaults`,
/// so the contract the shoot scripts depend on is a test rather than a
/// convention. Neither can change what a reader who never passes them sees.
enum LaunchRig {

    // MARK: - Driving the app to a screen

    /// Launch-argument key carrying the screen to open, as a URL.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_route "bainluck://search?q=US%20Open"`.
    static let routeKey = "launch_route"

    /// The screen the rig asked for, or `nil` when it asked for nothing.
    ///
    /// Deliberately a URL rather than a tab name: `NavigationCoordinator.handleURL`
    /// is already the app's one router, already tested, and already reaches every
    /// tab plus event detail, hubs, categories and a seeded search query. Parsing
    /// tab names here would be a second router to keep in sync with the first.
    ///
    /// Only Bain Luck's own links are accepted. That is not a security boundary —
    /// `handleURL` rejects foreign URLs anyway — it is what keeps this a screen
    /// selector rather than a general-purpose URL opener wired into a shipping
    /// build.
    static func route(defaults: UserDefaults = .standard) -> URL? {
        guard let raw = defaults.string(forKey: routeKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !raw.isEmpty,
            let url = URL(string: raw)
        else { return nil }

        if url.scheme == "bainluck" { return url }
        if url.host == "bainluck.com" || url.host == "www.bainluck.com" { return url }
        return nil
    }

    /// How long to wait before handing the route to the router.
    ///
    /// The first frame is not a mounted app: `ContentView`'s `TabView` builds
    /// only the selected tab, and Discover's own load is in flight. Routing into
    /// that window lands on a screen that is still deciding what it is. One beat
    /// is enough and is what native/019's hand-patched version used.
    static let routeDelay: TimeInterval = 2.5

    // MARK: - Photographing the count

    /// Launch-argument key that draws the served/drawn card counts over Discover.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_debug_counts YES`.
    static let debugCountsKey = "launch_debug_counts"

    /// Whether Discover should draw its own card counter.
    ///
    /// SHOWABLE-1 G1's bar is a number — "Discover shows the feed the API sends
    /// (≥28 cards)" — and a photograph of a page that merely *looks* populated
    /// does not prove it. The counter makes the gate's own number visible to the
    /// camera. Off unless asked for, so no reader ever sees it.
    static func showsDebugCounts(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: debugCountsKey)
    }
}
