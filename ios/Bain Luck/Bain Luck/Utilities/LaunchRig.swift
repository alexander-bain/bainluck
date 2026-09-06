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

    // MARK: - Photographing what is BELOW the fold

    /// Launch-argument key carrying how far down the page to scroll, in POINTS,
    /// before the camera fires.
    ///
    /// `xcrun simctl launch <sim> <bundle> -launch_scroll 1600`.
    ///
    /// The rig has photographed one viewport since #3157, and an event page is
    /// several viewports tall — so the margin maps, the half maps and the
    /// probability ladders have never been photographed at all. #3533 had to be
    /// filed with "its rendering is unverified" written into the issue for
    /// exactly this reason, and native/029–036 each shot only the hero. A defect
    /// nobody can photograph is a defect nobody can prove fixed, which is how a
    /// LOOK-driven queue runs out of things it can honestly close.
    ///
    /// Points, not "pages", because a point is what both `UIScrollView` and the
    /// device geometry are already denominated in (iPhone 17 is 402×874 points),
    /// so a number here is checkable against a screenshot without a conversion
    /// nobody can remember.
    static let scrollKey = "launch_scroll"

    /// How far the rig asked to scroll, or `nil` when it asked for nothing.
    ///
    /// Refuses zero and negatives rather than clamping them to zero: a caller
    /// that passes `-launch_scroll 0` or `-launch_scroll -100` has made a
    /// mistake, and answering "the top of the page" would hand back a shot that
    /// looks exactly like a successful un-scrolled shot. Nil is the honest
    /// answer, and the shoot script can then say so.
    static func scrollOffset(defaults: UserDefaults = .standard) -> Double? {
        guard let raw = defaults.string(forKey: scrollKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !raw.isEmpty,
            let points = Double(raw),
            points > 0,
            points.isFinite
        else { return nil }
        return points
    }

    /// How long to wait AFTER the route before scrolling.
    ///
    /// Longer than ``routeDelay`` and additional to it, because the two waits
    /// are for different things: routing waits for the app to mount, this waits
    /// for the destination screen's own network loads to land. Scrolling a page
    /// that is still three spinners tall lands on whatever happens to occupy
    /// that offset once the real content pushes it down — a shot of the wrong
    /// part of the page, which is worse than a shot of the top because it looks
    /// deliberate.
    static let scrollDelay: TimeInterval = 8.0

    /// The offset a scroll view can actually be put at, given the page it holds.
    ///
    /// Pure, and separated from the `UIScrollView` walk that uses it, because
    /// this is the half that can be wrong in a way a photograph cannot show.
    /// Asking for 4,000 points of a 1,200-point page and getting it would
    /// photograph past the end of the content: on iOS that is empty background,
    /// and empty background is indistinguishable in a PNG from "the card we were
    /// looking for is missing". The rig would then manufacture the exact finding
    /// it exists to test for.
    ///
    /// So the floor is the top and the ceiling is the last full viewport, and a
    /// caller that over-asks gets the BOTTOM of the page — a real part of it,
    /// which a reader can recognise.
    static func clampedScrollOffset(
        requested: Double,
        contentHeight: Double,
        viewportHeight: Double
    ) -> Double {
        let lastViewport = Swift.max(0, contentHeight - viewportHeight)
        return Swift.min(Swift.max(0, requested), lastViewport)
    }
}
