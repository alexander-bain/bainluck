import XCTest

/// #9989 · #9652 — **a reader can open an NFL week from Browse and get back to
/// the same spot.**
///
/// Build 33 decoded both published NFL weeks and drew neither: the Collections
/// section's load sat on a `Group` that is empty until the load lands, so it
/// never ran and Browse showed no entry at all. The hub, the game and Back were
/// fine through a deep link — the ENTRY was the broken half, and a deep-link
/// walk can never see it. So this walks in the way a reader does: the Browse tab.
///
/// SKIPS only when production publishes no collection for either league (the
/// calendar), read from the same endpoint the app reads, before the walk.
final class AReaderCanOpenAnNFLWeekFromBrowseAndComeBack9989Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testBrowseShowsAPublishedWeekAndBackReturnsToIt() throws {
        try XCTSkipUnless(Self.productionPublishesACollection(),
                          "No league publishes a collection today — nothing for Browse to show.")

        let app = UITestLaunch.launchApp()
        JourneyPrecondition.openTab("Browse", in: app)

        let entries = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH %@", "browse-collection-"))
        XCTAssertTrue(
            entries.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Production publishes a collection and Browse drew no entry for it in "
            + "\(UITestLaunch.contentTimeout)s. That is #9989: the section's first read never started."
        )
        let entry = entries.firstMatch
        let id = entry.identifier
        for _ in 0..<4 where !JourneyPrecondition.isReachable(entry, in: app) {
            JourneyPrecondition.liftContent(app, by: JourneyPrecondition.liftNeeded(for: entry, in: app) + 40)
        }
        let before = entry.frame.minY
        attach(app, "browse-before")

        entry.tap()
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "Tapped \(id) and no pushed screen with a Back button appeared.")
        XCTAssertFalse(app.navigationBars["Browse"].exists, "Tapped \(id) and Browse is still the top screen.")
        attach(app, "hub")

        back.tap()
        let again = app.descendants(matching: .any)[id]
        XCTAssertTrue(again.waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "Back from \(id) and its Browse entry is gone.")
        attach(app, "browse-after")
        XCTAssertEqual(again.frame.minY, before, accuracy: 1,
                       "Back from \(id) landed somewhere else on Browse (\(before) → \(again.frame.minY)).")
    }

    private func attach(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    /// The app's own endpoint and season rule (`ContainerDiscoveryLeague`); any
    /// read failure is NOT a skip — the walk then tells us what the app saw.
    private static func productionPublishesACollection() -> Bool {
        let year = Calendar(identifier: .gregorian).component(.year, from: Date())
        var found = false
        var failed = false
        for league in ["nfl", "mlb"] {
            let url = URL(string: "https://api.bainluck.com/api/containers/discover?league=\(league)&season=\(year)&limit=20")!
            let done = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: url) { data, response, _ in
                defer { done.signal() }
                guard (response as? HTTPURLResponse)?.statusCode == 200, let data,
                      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    failed = true
                    return
                }
                if let cards = object["collections"] as? [Any], !cards.isEmpty { found = true }
            }.resume()
            _ = done.wait(timeout: .now() + 20)
        }
        return found || failed
    }
}
