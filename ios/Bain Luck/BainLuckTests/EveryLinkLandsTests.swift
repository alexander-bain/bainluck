import XCTest
@testable import Bain_Luck

/// native/020 PR-B — a link into the app opens the thing it names.
///
/// `NavigationCoordinator.handleURL` returning `false` is silent: the app is
/// already open, the reader is already looking at Discover, and nothing marks
/// the difference between "this link took me somewhere" and "this link did
/// nothing and the app happened to launch on its default tab". So the failures
/// here are the kind that survive for months.
///
/// Two of them did. `bainluck://events` with no id — handed out by
/// `LiveGamesWidget` in five places and by `MenuBarView` — fell out of the
/// switch, so tapping a widget listing three live games opened Discover. And
/// there was no `tournaments` case at all, so the US Open hub was unreachable
/// by link while the US Open was being played, even though `Route.tournamentHub`
/// exists and both Browse and Search push it.
final class EveryLinkLandsTests: XCTestCase {

    // MARK: - A link to the collection, not to a row

    @MainActor
    func testBareEventsLinkOpensTheSportsFeed() throws {
        let nav = NavigationCoordinator()
        nav.selectedTab = .myStuff   // start somewhere else, so .feed proves the move

        XCTAssertTrue(
            nav.handleURL(try XCTUnwrap(URL(string: "bainluck://events"))),
            "the live-games widget's own tap-through URL must be a link the app accepts"
        )
        XCTAssertEqual(nav.selectedTab, .feed)
        XCTAssertNil(nav.pendingRoute, "a link to the list pushes nothing on top of the list")
    }

    @MainActor
    func testEventsLinkWithAnIdStillOpensThatEvent() throws {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://events/15304209"))))
        XCTAssertEqual(nav.selectedTab, .feed)
        // `navigate(to:tab:)` publishes the route one runloop hop later.
        let pushed = expectation(description: "route published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { pushed.fulfill() }
        wait(for: [pushed], timeout: 1.0)
        XCTAssertEqual(nav.consumeRoute(), .eventDetail(id: 15304209))
    }

    @MainActor
    func testBareFuturesLinkOpensTheFuturesList() throws {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://futures"))))
        XCTAssertEqual(nav.selectedTab, .feed)
    }

    // MARK: - The tournament hub

    @MainActor
    func testTournamentLinkOpensTheHub() throws {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "bainluck://tournaments/us-open"))))

        // Browse, not the feed: Browse is where the hub is reached by hand and
        // the tab that was wired to receive a pushed route for it (#2998).
        XCTAssertEqual(nav.selectedTab, .leagues)

        let pushed = expectation(description: "route published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { pushed.fulfill() }
        wait(for: [pushed], timeout: 1.0)
        XCTAssertEqual(nav.consumeRoute(), .tournamentHub(slug: "us-open", name: "US Open"))
    }

    @MainActor
    func testTournamentUniversalLinkOpensTheHub() throws {
        // The shape a shared bainluck.com link has. The AASA does not claim this
        // path yet (filed separately — `frontend/public/.well-known/` is not this
        // lane's file), but `onContinueUserActivity` routes through the same
        // method, so the app is ready for it the day it does.
        let nav = NavigationCoordinator()
        XCTAssertTrue(
            nav.handleURL(try XCTUnwrap(URL(string: "https://bainluck.com/tournaments/us-open")))
        )
        XCTAssertEqual(nav.selectedTab, .leagues)
    }

    @MainActor
    func testTournamentLinkPrefersAnExplicitName() throws {
        let nav = NavigationCoordinator()
        _ = nav.handleURL(try XCTUnwrap(URL(string: "bainluck://tournaments/roland-garros?name=French%20Open")))

        let pushed = expectation(description: "route published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { pushed.fulfill() }
        wait(for: [pushed], timeout: 1.0)
        XCTAssertEqual(nav.consumeRoute(), .tournamentHub(slug: "roland-garros", name: "French Open"))
    }

    // MARK: - Naming a hub from a slug

    func testCatalogOwnsTheNameItKnows() {
        XCTAssertEqual(tournamentDisplayName(forSlug: "us-open"), "US Open")
    }

    /// The reason this is not `.capitalized`: a slug the catalog has not heard
    /// of would render "Us Open" in the title bar — #1938's defect, one screen
    /// over. The shared acronym-safe caser already knows "US".
    func testAnUnknownSlugIsStillTitledSafely() {
        XCTAssertEqual(tournamentDisplayName(forSlug: "us-amateur", in: []), "US Amateur")
        XCTAssertEqual(tournamentDisplayName(forSlug: "french-open", in: []), "French Open")
        XCTAssertEqual(tournamentDisplayName(forSlug: "pga-championship", in: []), "PGA Championship")
    }

    // MARK: - The census: every link the app hands out is a link it accepts

    /// Walks the shipping sources — the app AND the widget extension — for
    /// `bainluck://…` literals and asserts the router accepts each one.
    ///
    /// This is the guard for the class, not for the two instances. The widget is
    /// where it matters most: a widget URL is authored in a target that cannot
    /// import the router, is never exercised by any other test, and fails by
    /// opening the wrong screen rather than by crashing.
    @MainActor
    func testEveryDeepLinkTheAppHandsOutIsAccepted() throws {
        let literals = try deepLinkLiterals()

        // Anti-vacuity, by containment rather than by count: a census that reads
        // the wrong tree passes an "all accepted" assertion trivially, and a
        // count floor rots the moment a link is added or removed. These three
        // shapes are the ones the widget extension itself authors — a target no
        // other test in this suite touches — so their presence proves the walk
        // reached past the app sources.
        for required in ["bainluck://events", "bainluck://events/1", "bainluck://futures/1"] {
            XCTAssertTrue(
                literals.contains(required),
                "the census did not find \(required); it is reading the wrong tree, not passing"
            )
        }

        var refused: [String] = []
        for literal in literals.sorted() {
            let nav = NavigationCoordinator()
            guard let url = URL(string: literal) else {
                refused.append("\(literal) (not a URL)")
                continue
            }
            if !nav.handleURL(url) { refused.append(literal) }
        }

        XCTAssertEqual(
            refused, [],
            "these links are handed to readers by the app's own widgets and menus, "
            + "and the router drops them — the app opens on its default tab and says nothing"
        )
    }

    /// Every distinct `bainluck://…` literal in the shipping sources, with any
    /// string interpolation replaced by a concrete id so the result is a URL.
    private func deepLinkLiterals() throws -> Set<String> {
        let here = URL(fileURLWithPath: #filePath)
        let projectRoot = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)

        guard let walker = FileManager.default.enumerator(
            at: projectRoot,
            includingPropertiesForKeys: nil
        ) else {
            XCTFail("could not walk the project — the census is not running")
            return []
        }

        // Anchored on the opening quote so this reads STRING LITERALS, not
        // prose: several files discuss `bainluck://events` in a comment, and a
        // comment is not a link anybody can tap. The capture group is the URL
        // between the quotes.
        let pattern = try NSRegularExpression(pattern: #""(bainluck://[^"]*)""#)
        var found: Set<String> = []

        for case let url as URL in walker
        where url.pathExtension == "swift" && !url.path.contains("BainLuckTests") {
            let text = try String(contentsOf: url, encoding: .utf8)
            let range = NSRange(text.startIndex..., in: text)
            for match in pattern.matches(in: text, range: range) {
                guard let r = Range(match.range(at: 1), in: text) else { continue }
                var literal = String(text[r])
                // `\(item.id)` becomes `1`: the census is about which ROUTES
                // exist, not which ids do.
                while let open = literal.range(of: #"\("#),
                      let close = literal.range(of: ")", range: open.upperBound..<literal.endIndex) {
                    literal.replaceSubrange(open.lowerBound..<close.upperBound, with: "1")
                }
                found.insert(literal)
            }
        }
        return found
    }
}
