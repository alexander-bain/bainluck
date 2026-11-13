import XCTest
@testable import Bain_Luck

/// #12671 — the About screen's "Start Exploring" button left the app.
///
/// The button is a link to `/discover` on the web page `AboutView` shows. The
/// screen hands every link it doesn't render to the system (#5914), and the
/// router had no `discover` case, so the link went to Safari: Alex, on his iPad,
/// "hilariously takes you out of the app to our website".
///
/// Two halves, tested apart: the router now knows `/discover`, and the About
/// screen asks the router before it asks Safari, for our own site only.
final class AboutStartExploringOpensDiscover12671Tests: XCTestCase {

    // MARK: - The router knows /discover

    /// The exact link the About page's button carries inside the app: the
    /// `www` host, with or without the embed flag the page was loaded with.
    @MainActor
    func testStartExploringOpensDiscover() throws {
        for literal in [
            "https://www.bainluck.com/discover",
            "https://www.bainluck.com/discover?embed=1",
            "https://bainluck.com/discover",
            "bainluck://discover",
        ] {
            let nav = NavigationCoordinator()
            nav.selectedTab = .myStuff   // About lives under My Stuff
            XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: literal))), "\(literal) is refused")
            XCTAssertEqual(nav.selectedTab, .discover, "\(literal) does not land on Discover")
            XCTAssertNil(nav.pendingRoute, "\(literal) leaves a screen queued to push over Discover")
        }
    }

    // MARK: - The About screen asks the app first, for our site only

    @MainActor
    func testOurOwnLinksGoToTheAppsRouter() throws {
        var asked: [URL] = []
        let router: (URL) -> Bool = { asked.append($0); return true }
        let discover = try XCTUnwrap(URL(string: "https://www.bainluck.com/discover"))

        XCTAssertTrue(AboutView.opensInApp(discover, router: router))
        XCTAssertEqual(asked, [discover])
    }

    /// A page the app has no screen for stays a Safari link: the router says
    /// no, so the system opens it. This is what keeps /privacy working.
    @MainActor
    func testAPageTheAppCannotShowStillGoesToSafari() throws {
        let nav = NavigationCoordinator()
        let privacy = try XCTUnwrap(URL(string: "https://www.bainluck.com/privacy"))
        XCTAssertFalse(AboutView.opensInApp(privacy, router: nav.handleURL))
    }

    /// Mail and other sites never reach the router. A venue link whose path
    /// happened to match one of our routes ("kalshi.com/events/…") must not
    /// open one of our screens.
    @MainActor
    func testMailAndOtherSitesNeverReachTheRouter() throws {
        var asked = 0
        let router: (URL) -> Bool = { _ in asked += 1; return true }
        for literal in [
            "mailto:bugs@bainluck.com",
            "https://kalshi.com/events/KXNFLGAME",
            "https://polymarket.com/discover",
            "https://bainluck.com.evil.example/discover",
        ] {
            XCTAssertFalse(AboutView.opensInApp(try XCTUnwrap(URL(string: literal)), router: router),
                           "\(literal) would open inside the app")
        }
        XCTAssertEqual(asked, 0, "a link that isn't ours reached the app's router")
    }
}
