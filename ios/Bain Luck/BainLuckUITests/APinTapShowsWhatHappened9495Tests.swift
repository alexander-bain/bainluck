import XCTest

/// Real-network tap journey for #9495: on the game page, every pin tap puts a
/// visible answer on screen — under the limit and at it. Opt-in; the route
/// defaults to the build-31 specimen (Red Sox at Yankees).
///
/// Pins are seeded through the `UserDefaults` argument domain, the same channel
/// `PinManager` reads, as an old-style plist data literal of the JSON id array.
final class APinTapShowsWhatHappened9495Tests: XCTestCase {

    private var route: String {
        ProcessInfo.processInfo.environment["BL_PIN_ROUTE"] ?? "bainluck://events/15319563"
    }

    /// `[1,2,3,4,5,6]` / `[]` as JSON bytes.
    private let sixPins = "<5b312c322c332c342c352c365d>"
    private let noPins = "<5b5d>"

    func testUnderTheLimitEachTapSaysPinnedThenRemoved() throws {
        continueAfterFailure = false
        let app = UITestLaunch.launchApp(extra: ["-launch_route", route, "-bainluck_pins.guest.Events", noPins])
        let pin = toolbarPin(app, "Pin")
        XCTAssertTrue(pin.waitForExistence(timeout: 65), "game page pin did not appear")

        pin.tap()
        let pinned = text(app, "Pinned to My Stuff")
        XCTAssertTrue(pinned.waitForExistence(timeout: 20), "a pin tap produced no confirmation")
        try shoot(app, "under-limit-pinned")

        let unpin = toolbarPin(app, "Unpin")
        XCTAssertTrue(unpin.waitForExistence(timeout: 10))
        unpin.tap()
        XCTAssertTrue(text(app, "Removed from My Stuff").waitForExistence(timeout: 20),
                      "an unpin tap produced no confirmation")
        try shoot(app, "under-limit-removed")
    }

    func testAtTheLimitTheTapIsAcceptedAndExplained() throws {
        continueAfterFailure = false
        let app = UITestLaunch.launchApp(extra: ["-launch_route", route, "-bainluck_pins.guest.Events", sixPins])
        let pin = toolbarPin(app, "Pin")
        XCTAssertTrue(pin.waitForExistence(timeout: 65), "game page pin did not appear")
        XCTAssertTrue(pin.isEnabled, "at the limit the pin must still take the tap")

        pin.tap()
        let limit = text(app, "You already have 6 pinned games. Unpin one in My Stuff.")
        XCTAssertTrue(limit.waitForExistence(timeout: 5), "a tap at the limit produced nothing")
        try shoot(app, "at-limit")
        XCTAssertTrue(toolbarPin(app, "Pin").exists, "a refused pin must stay unpinned")
    }

    /// The game page's own pin. On iPad the list beside the page has pins too.
    private func toolbarPin(_ app: XCUIApplication, _ label: String) -> XCUIElement {
        app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", label)).firstMatch
    }

    private func text(_ app: XCUIApplication, _ label: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label)).firstMatch
    }

    private func shoot(_ app: XCUIApplication, _ name: String) throws {
        let size = ProcessInfo.processInfo.environment["BL_PIN_SIZE"] ?? "default"
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("pin9495")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("\(size)-\(name).png")
        try app.screenshot().pngRepresentation.write(to: file)
        print("PIN9495 shot=\(file.path)")
    }
}
