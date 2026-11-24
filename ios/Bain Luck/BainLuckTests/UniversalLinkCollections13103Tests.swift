import XCTest

@testable import Bain_Luck

/// #13103 — Universal Links for shared sets (`bainluck.com/collections/<slug>`)
/// open `ContainerHubView` directly when Bain Luck is installed.
@MainActor
final class UniversalLinkCollections13103Tests: XCTestCase {
    func testSharedSetUniversalLinksOpenContainerHub() async throws {
        let validURLs: [(String, String, String)] = [
            ("https://bainluck.com/collections/oscars-2027", "oscars-2027", ""),
            ("https://www.bainluck.com/collections/white-christmas-2026", "white-christmas-2026", ""),
            ("https://www.bainluck.com/collections/roundup-cfp-picture?name=CFP%20Picture", "roundup-cfp-picture", "CFP Picture"),
            ("bainluck://collections/midterms-2026", "midterms-2026", ""),
        ]

        for (raw, expectedSlug, expectedName) in validURLs {
            let nav = NavigationCoordinator()
            let url = try XCTUnwrap(URL(string: raw))
            XCTAssertTrue(nav.handleURL(url), "Expected \(raw) to open container hub")
            XCTAssertEqual(nav.selectedTab, .discover)
            try await Task.sleep(nanoseconds: 150_000_000)
            XCTAssertEqual(nav.consumeRoute(), .containerHub(slug: expectedSlug, name: expectedName))
        }
    }

    func testInvalidOrIncompleteCollectionLinksAreRejected() throws {
        let invalidURLs = [
            "https://www.bainluck.com/collections",
            "https://www.bainluck.com/collections/",
            "https://www.bainluck.com/collections/oscars-2027/extra",
            "https://www.bainluck.com/collections/Not_A_Valid_Slug!",
            "https://example.com/collections/oscars-2027",
        ]

        for raw in invalidURLs {
            let nav = NavigationCoordinator()
            let url = try XCTUnwrap(URL(string: raw))
            XCTAssertFalse(nav.handleURL(url), "Expected \(raw) to be rejected")
            XCTAssertNil(nav.consumeRoute())
        }
    }
}
