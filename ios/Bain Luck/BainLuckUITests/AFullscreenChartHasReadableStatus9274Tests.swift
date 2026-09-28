import XCTest

/// Real-network tap guard for #9274. Use a currently live event; this is an
/// opt-in journey, not an offline unit gate or an installed-device timing claim.
final class AFullscreenChartHasReadableStatus9274Tests: XCTestCase {
    func testStatusIsReadableContentAndDoneStillClosesChart() throws {
        continueAfterFailure = false
        let route = ProcessInfo.processInfo.environment["BL_FULLSCREEN_ROUTE"] ?? "bainluck://events/14780548"
        let app = UITestLaunch.launchApp(extra: ["-launch_route", route])
        let expand = app.buttons["Enter Full Screen"]
        XCTAssertTrue(expand.waitForExistence(timeout: 65), "Chart did not load")
        expand.tap()
        let done = app.buttons["Done"]
        XCTAssertTrue(done.waitForExistence(timeout: 10))
        let status = app.descendants(matching: .any).matching(identifier: "live-update-status").firstMatch
        guard status.waitForExistence(timeout: 15) else {
            throw XCTSkip("A live event with delivery status is required; supplied route did not expose one")
        }
        XCTAssertFalse(app.buttons["live-update-status"].exists,
                       "A readonly live-status sentence is not a toolbar control")
        XCTAssertGreaterThan(status.frame.width, 85, "Status is squeezed into a tiny toolbar slot")
        XCTAssertGreaterThan(status.frame.minY, done.frame.maxY,
                             "Status must sit below navigation instead of inside its circle")
        XCTAssertLessThan(status.frame.height, 90, "Status is wrapping one syllable per line")
        let name = ProcessInfo.processInfo.environment["BL_FULLSCREEN_SIZE"] ?? "default"
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("fullscreen9274")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try app.screenshot().pngRepresentation.write(to: dir.appendingPathComponent(name + ".png"))
        try app.debugDescription.write(to: dir.appendingPathComponent(name + ".txt"), atomically: true, encoding: .utf8)
        print("FULLSCREEN9274 name=\(name) status=\(status.label) frame=\(status.frame) evidence=\(dir.path)")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Win probability over time")).firstMatch.exists)
        done.tap()
        XCTAssertTrue(done.waitForNonExistence(timeout: 10))
        XCTAssertTrue(expand.waitForExistence(timeout: 10), "Done must restore the inline chart")
    }
}
