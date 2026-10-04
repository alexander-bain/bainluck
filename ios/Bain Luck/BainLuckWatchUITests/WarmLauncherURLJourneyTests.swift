#if DEBUG
import Darwin
import XCTest

final class WarmLauncherURLJourneyTests: XCTestCase {
    @MainActor
    func testWarmLauncherClosesPickerAndHelpWithoutChangingProcessOrSelection() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1"
        ]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        try reveal(first, in: app)
        first.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        let process = app.staticTexts["watch.launch-process"]
        XCTAssertTrue(process.waitForExistence(timeout: 15))
        let initialProcess = process.label
        XCTAssertNotNil(UUID(uuidString: initialProcess), "Receipt must identify the actual app process")
        let initialReading = probability.label
        let receipt = app.staticTexts["watch.launch-receipt"]
        XCTAssertTrue(receipt.waitForExistence(timeout: 15))
        XCTAssertEqual(receipt.label, "Launcher opens: 0")
        let nonce = UUID().uuidString

        let change = app.buttons["watch.choose-another"]
        XCTAssertTrue(change.waitForExistence(timeout: 15))
        try reveal(change, in: app)
        change.tap()
        let alternative = app.buttons["watch.pick.202"]
        XCTAssertTrue(alternative.waitForExistence(timeout: 15))
        try reveal(alternative, in: app)
        capture(app, name: "Warm launcher before delivery with picker open")
        print("WATCH_UI_WARM_READY=1:\(nonce)")
        fflush(stdout)
        expectation(for: NSPredicate(format: "label == %@", "Launcher opens: 1"), evaluatedWith: receipt)
        waitForExpectations(timeout: 45)
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: alternative)
        waitForExpectations(timeout: 15)
        XCTAssertEqual(process.label, initialProcess, "Warm OS delivery must preserve the app process")
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, initialReading, "Launcher must preserve the selected named Giants game")
        try reveal(probability, in: app)
        capture(app, name: "Warm launcher dismissed picker and retained named game")

        let help = app.buttons["watch.continue-on-phone"]
        XCTAssertTrue(help.waitForExistence(timeout: 15))
        try reveal(help, in: app)
        help.tap()
        let alert = app.alerts["Continue on iPhone"]
        XCTAssertTrue(alert.waitForExistence(timeout: 15))
        capture(app, name: "Warm launcher before delivery with iPhone help open")
        print("WATCH_UI_WARM_READY=2:\(nonce)")
        fflush(stdout)
        expectation(for: NSPredicate(format: "label == %@", "Launcher opens: 2"), evaluatedWith: receipt)
        waitForExpectations(timeout: 45)
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: alert)
        waitForExpectations(timeout: 15)
        XCTAssertEqual(process.label, initialProcess, "Second delivery must preserve the same process")
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, initialReading, "Help dismissal must preserve the selected named game")
        try reveal(probability, in: app)
        capture(app, name: "Warm launcher dismissed help and retained named game")
        print("WATCH_UI_LAUNCHER_WARM=PASS")
        fflush(stdout)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        for _ in 0..<24 {
            if element.isHittable && app.frame.contains(element.frame) { return }
            let earlier = element.frame.minY < app.frame.minY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.75 : 0.45))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, name: "Unreachable warm launcher reading - \(element.identifier)")
        XCTFail("Cannot bring full reading into view")
        throw NSError(domain: "WatchWarmLauncherJourney", code: 1)
    }

    @MainActor
    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
#endif
