import XCTest
@testable import Bain_Luck

/// native/145 — the two screens a submission candidate had never been
/// photographed on.
///
/// The LOOK rig reaches a screen exactly one way: `-launch_route <url>`, handed
/// straight to `NavigationCoordinator.handleURL` (`LaunchRig`, #3157). So a
/// screen with no case in that switch cannot be shot, and "we walked the app
/// before submitting" quietly means "we walked the parts the router knows".
///
/// Two screens were in that shadow, and neither for want of the screen:
///
///   * About — `Route.about` and `AboutView` have existed since L2-144 and are
///     reached by hand from My Stuff, Preferences and Browse. `RouteDestination`
///     has always rendered it. There was simply no `case "about"`, the same
///     shape as the `tournaments` gap that left the US Open hub unlinkable
///     during the US Open (`EveryLinkLandsTests`).
///
///   * The rage-shake bug report — triggered by a physical shake or by
///     Cmd+Shift+B on macOS. The rig can do neither: `-launch_scroll` moves a
///     scroll view, it cannot press a button or shake a phone. So the app's
///     primary feedback surface, the one App Review is most likely to open, had
///     no screenshot.
///
/// These are unit tests of the router, not of the screens — what they pin is
/// that the two URLs the shoot scripts now pass are accepted and land on the
/// right thing, so the rig's arguments cannot go silently inert in the way
/// `LaunchRig`'s own docstring was written to prevent.
final class AboutAndBugReportAreLinkableTests: XCTestCase {

    /// The router publishes `pendingRoute` one runloop hop after the tab moves
    /// (`navigate(to:tab:)`), so a route assertion has to wait for it.
    @MainActor
    private func afterTheRoutePublishes() {
        let pushed = expectation(description: "route published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { pushed.fulfill() }
        wait(for: [pushed], timeout: 1.0)
    }

    // MARK: - The control: `true` has to be capable of being `false`

    /// Proves the assertions below have teeth.
    ///
    /// Every positive test here ends in `XCTAssertTrue(nav.handleURL(...))`. If
    /// the router accepted anything with our scheme on it — a plausible way to
    /// "fix" an unroutable link — all of them would pass while both screens
    /// stayed unreachable. This is the measurement checking it can still see a
    /// refusal.
    ///
    /// The URL is assembled from a variable on purpose. `EveryLinkLandsTests`
    /// walks this whole directory for `"bainluck://…"` string literals and
    /// asserts the router accepts each one it finds; a literal here would be
    /// collected as if it were a link the app hands out, and would fail that
    /// census rather than this one.
    @MainActor
    func testTheRouterStillRefusesAScreenItDoesNotKnow() throws {
        let scheme = "bainluck"
        let nav = NavigationCoordinator()

        XCTAssertFalse(
            nav.handleURL(try XCTUnwrap(URL(string: "\(scheme)://no-such-screen"))),
            "the router accepts an unknown host — every acceptance assertion in "
            + "this file is then vacuous"
        )
    }

    // MARK: - About

    @MainActor
    func testAboutLinkOpensTheAboutScreen() throws {
        let nav = NavigationCoordinator()
        nav.selectedTab = .discover   // start elsewhere, so .myStuff proves the move

        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://about"))))

        // My Stuff is the profile hub the About row lives in, and — the part
        // that matters — a tab that consumes a pushed route. Routing to a tab
        // that only observes `pendingRoute` drops it silently (#2998).
        XCTAssertEqual(nav.selectedTab, .myStuff)

        afterTheRoutePublishes()
        XCTAssertEqual(nav.consumeRoute(), .about)
    }

    /// `https://bainluck.com/about` is a real web page, so this case claims a
    /// universal link as well as the custom scheme. That is deliberate and it is
    /// not a hijack: `AboutView` is an in-app web view of that exact URL, so a
    /// reader who taps the link in the app sees the page the link named.
    @MainActor
    func testAboutUniversalLinkOpensTheAboutScreen() throws {
        let nav = NavigationCoordinator()
        nav.selectedTab = .discover

        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "https://bainluck.com/about"))))
        XCTAssertEqual(nav.selectedTab, .myStuff)

        afterTheRoutePublishes()
        XCTAssertEqual(nav.consumeRoute(), .about)
    }

    // MARK: - The bug-report sheet

    @MainActor
    func testBugReportLinkRaisesTheReportSheet() throws {
        let nav = NavigationCoordinator()
        XCTAssertFalse(nav.showBugReport, "the flag must start down for `true` to mean anything")

        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://bug-report"))))

        // `ContentView` observes this flag, captures a screenshot and presents
        // `BugReportView`; it is the same flag the macOS Cmd+Shift+B command
        // sets, so this is the existing path rather than a second one.
        XCTAssertTrue(nav.showBugReport)
    }

    /// The sheet goes over whatever the reader was looking at, and the
    /// screenshot `ContentView` attaches is of THAT screen. A tab change here
    /// would swap the evidence out from under the report and strand the reader
    /// on a new tab when they dismissed the form.
    @MainActor
    func testBugReportLinkLeavesTheReaderWhereTheyWere() throws {
        let nav = NavigationCoordinator()
        nav.selectedTab = .leagues

        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://bug-report"))))

        XCTAssertEqual(nav.selectedTab, .leagues, "the report sheet must not move the reader")

        afterTheRoutePublishes()
        XCTAssertNil(nav.consumeRoute(), "a modal sheet pushes nothing onto the navigation stack")
    }
}
