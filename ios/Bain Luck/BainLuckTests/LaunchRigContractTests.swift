import XCTest
@testable import Bain_Luck

/// #3157 — the launch arguments that let a headless rig photograph a screen
/// other than the default tab, and read G1's own number off the page.
///
/// Same guard as `NotificationPromptSuppressionTests` and for the same reason:
/// the failure this class of code actually suffers is not "wrong screen", it is
/// **silently inert**. `-temp_screenshot_tab` and `-temp_screenshot_counts` were
/// passed by `tools/native-g1-shoot.sh` for weeks and read by no Swift file, so
/// the rig appeared to be driving the app while every shot was of Discover
/// because Discover is what the app opens on. A flag with no test is
/// indistinguishable from a flag that was never wired.
final class LaunchRigContractTests: XCTestCase {

    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "LaunchRigContractTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    // MARK: - The product default is unchanged

    func testAbsentRouteOpensNothing() {
        // A real launch passes none of these keys. Every affordance must be
        // inert then, which is what keeps them test affordances rather than
        // product settings.
        XCTAssertNil(LaunchRig.route(defaults: defaults))
        XCTAssertFalse(LaunchRig.showsDebugCounts(defaults: defaults))
        XCTAssertNil(LaunchRig.scrollOffset(defaults: defaults))
    }

    func testEmptyAndWhitespaceRouteOpensNothing() {
        for blank in ["", "   ", "\n"] {
            defaults.set(blank, forKey: LaunchRig.routeKey)
            XCTAssertNil(
                LaunchRig.route(defaults: defaults),
                "a blank argument is the same as no argument, not a route to nowhere"
            )
        }
    }

    // MARK: - The rig's contract

    func testRouteReadsABainLuckDeepLink() {
        defaults.set("bainluck://search?q=US%20Open", forKey: LaunchRig.routeKey)
        XCTAssertEqual(
            LaunchRig.route(defaults: defaults)?.absoluteString,
            "bainluck://search?q=US%20Open"
        )
    }

    func testRouteReadsAUniversalLink() {
        defaults.set("https://bainluck.com/events/123", forKey: LaunchRig.routeKey)
        XCTAssertEqual(
            LaunchRig.route(defaults: defaults)?.host,
            "bainluck.com"
        )
    }

    /// The whole design premise: the rig adds no routing of its own, so whatever
    /// the app's one router can reach, the rig can shoot. If these stop being
    /// accepted here, the shoot scripts silently fall back to Discover — the
    /// exact `-temp_screenshot_tab` failure, one refactor later.
    func testEveryScreenTheRouterReachesIsAcceptedByTheRig() throws {
        let screens = [
            "bainluck://events",
            "bainluck://events/9001",
            "bainluck://search?q=Djokovic",
            "bainluck://playoffs/nba",
            "bainluck://my-stuff",
            "bainluck://calibration",
            "bainluck://weather",
            "bainluck://category/tennis",
        ]
        for screen in screens {
            defaults.set(screen, forKey: LaunchRig.routeKey)
            let url = try XCTUnwrap(
                LaunchRig.route(defaults: defaults),
                "the rig refused \(screen), so this screen cannot be photographed"
            )
            XCTAssertEqual(url.absoluteString, screen)
        }
    }

    /// A screen selector, not a URL opener. `handleURL` would refuse these
    /// anyway; refusing them here is what keeps a shipping build from carrying a
    /// launch argument that can point anywhere.
    func testForeignURLsAreRefused() {
        for foreign in ["https://example.com/events/1", "file:///etc/passwd", "not a url at all"] {
            defaults.set(foreign, forKey: LaunchRig.routeKey)
            XCTAssertNil(
                LaunchRig.route(defaults: defaults),
                "\(foreign) is not a Bain Luck screen"
            )
        }
    }

    /// `xcrun simctl launch … -launch_debug_counts YES` does not write a Bool:
    /// the argument domain parses `YES` as a string and `bool(forKey:)` is what
    /// turns it back into `true`. Asserting the string form makes this a test of
    /// the command the shoot scripts actually run.
    func testDebugCountsReadsTheLaunchArgumentStringForms() {
        for yes in ["YES", "1", "true"] {
            defaults.set(yes, forKey: LaunchRig.debugCountsKey)
            XCTAssertTrue(
                LaunchRig.showsDebugCounts(defaults: defaults),
                "simctl passes \(yes) as a string; it must still read as on"
            )
        }
        defaults.set(false, forKey: LaunchRig.debugCountsKey)
        XCTAssertFalse(LaunchRig.showsDebugCounts(defaults: defaults))
    }

    // MARK: - The key names ARE the interface

    /// Rename any of these and every script in `tools/` goes back to
    /// photographing the default tab with no counter and no error.
    func testKeyNamesAreTheOnesTheShootScriptsPass() {
        XCTAssertEqual(LaunchRig.routeKey, "launch_route")
        XCTAssertEqual(LaunchRig.debugCountsKey, "launch_debug_counts")
        XCTAssertEqual(LaunchRig.scrollKey, "launch_scroll")
    }

    // MARK: - Photographing below the fold (`--scroll`)

    /// `simctl launch … -launch_scroll 1600` writes a STRING into the argument
    /// domain, exactly as `-launch_debug_counts YES` does. Reading it with
    /// `double(forKey:)` would also work today, but reading the string form is
    /// what makes this a test of the command `tools/native-shoot.sh` runs.
    func testScrollOffsetReadsTheLaunchArgumentStringForm() {
        defaults.set("1600", forKey: LaunchRig.scrollKey)
        XCTAssertEqual(LaunchRig.scrollOffset(defaults: defaults), 1600)
    }

    /// Nil, not zero. A zero offset produces a PNG identical to an un-scrolled
    /// shot, so answering "the top" for a malformed request hands back evidence
    /// that cannot be told apart from success — the rig would quietly stop
    /// scrolling and every below-the-fold finding after that would be a shot of
    /// the hero with a scrolled label on it.
    func testAMalformedOrNonPositiveScrollIsRefusedRatherThanFlattenedToZero() {
        for bad in ["", "   ", "0", "-100", "some", "1,600", "NaN"] {
            defaults.set(bad, forKey: LaunchRig.scrollKey)
            XCTAssertNil(
                LaunchRig.scrollOffset(defaults: defaults),
                "\(bad) is not a scroll distance; answering 0 would look like a successful top-of-page shot"
            )
        }
    }

    /// The clamp is the half a photograph cannot check. Scrolling past the end
    /// of a page shows iOS's empty background, and empty background in a PNG is
    /// indistinguishable from "the card we were hunting is missing" — the rig
    /// would manufacture the finding it exists to test for.
    func testOverAskingLandsOnTheBottomOfThePageNotPastIt() {
        // A 3,000pt page in an 874pt viewport: the last full screen starts at 2,126.
        XCTAssertEqual(
            LaunchRig.clampedScrollOffset(requested: 9_000, contentHeight: 3_000, viewportHeight: 874),
            2_126
        )
    }

    func testAReachableOffsetIsPassedThroughUntouched() {
        XCTAssertEqual(
            LaunchRig.clampedScrollOffset(requested: 1_600, contentHeight: 3_000, viewportHeight: 874),
            1_600
        )
    }

    /// A page shorter than the screen has nowhere to go, and must report zero
    /// rather than a negative offset — `UIScrollView` accepts a negative
    /// `contentOffset` and rubber-bands, which photographs as a page slid down
    /// the screen under a band of blank.
    func testAPageShorterThanTheScreenCannotScrollAtAll() {
        XCTAssertEqual(
            LaunchRig.clampedScrollOffset(requested: 1_600, contentHeight: 400, viewportHeight: 874),
            0
        )
    }

    /// The two waits are additive and for different things: `routeDelay` waits
    /// for the app to mount, `scrollDelay` waits for the routed screen's own
    /// network loads. Scrolling into a page that is still spinners tall lands
    /// wherever the real content later pushes that offset to.
    func testScrollWaitsLongerThanTheRouteDoes() {
        XCTAssertGreaterThan(LaunchRig.scrollDelay, LaunchRig.routeDelay)
        XCTAssertLessThanOrEqual(LaunchRig.scrollDelay, 20.0)
    }

    /// The route is handed over after a beat, because the first frame is not a
    /// mounted app. Zero would route into a `TabView` that has not built the
    /// destination tab yet; a long wait wastes every shoot. Pinned so the value
    /// is a decision rather than a leftover.
    func testRouteDelayLeavesTheAppTimeToMount() {
        XCTAssertGreaterThanOrEqual(LaunchRig.routeDelay, 1.0)
        XCTAssertLessThanOrEqual(LaunchRig.routeDelay, 5.0)
    }
}

/// The other half of #3157: the router must still be holding the query when the
/// destination view finally mounts.
///
/// `NavigationCoordinator.handleURL` selects the Search tab and sets
/// `pendingSearchQuery` in the same tick, but a `TabView` builds SearchView
/// lazily — so on a cold open (a shared search link, a push, the rig) the value
/// has already changed by the time the view exists, and the view's `.onChange`
/// never fires. SearchView now also drains on mount. What is testable here is
/// the coordinator's side of that contract: the query must SURVIVE until
/// somebody asks for it, and must be handed out exactly once.
final class PendingSearchQuerySurvivalTests: XCTestCase {

    @MainActor
    func testDeepLinkQuerySurvivesUntilTheViewMounts() throws {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://search?q=US%20Open"))))

        XCTAssertEqual(nav.selectedTab, .search)
        // Nothing has consumed it yet — this is the window in which the tab is
        // switching and SearchView does not exist. If the coordinator cleared it
        // here, a cold-opened search link would land on an empty Search screen.
        XCTAssertEqual(nav.pendingSearchQuery, "US Open")
    }

    @MainActor
    func testTheQueryIsHandedOutExactlyOnce() throws {
        let nav = NavigationCoordinator()
        _ = nav.handleURL(try XCTUnwrap(URL(string: "bainluck://search?q=Alcaraz")))

        // SearchView drains on mount AND on change; both call the same helper.
        // The second call must come back empty or the view searches twice and
        // the second search races the first onto the same surface.
        XCTAssertEqual(nav.consumeSearchQuery(), "Alcaraz")
        XCTAssertNil(nav.consumeSearchQuery())
    }

    @MainActor
    func testAQuerylessSearchLinkStillOpensSearch() throws {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://search"))))

        XCTAssertEqual(nav.selectedTab, .search)
        XCTAssertNil(nav.pendingSearchQuery, "no query means an empty field, not an empty search")
    }
}
