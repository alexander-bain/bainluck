#if DEBUG
import XCTest

final class RectangularWidgetHostJourneyTests: XCTestCase {
    @MainActor
    func testActualRectangularWidgetShowsPublishedSavedReading() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1",
            "BAINLUCK_WATCH_UI_SHARED_PUBLICATION": "1"
        ]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        try reveal(first, in: app)
        first.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 20))
        XCTAssertTrue(probability.label.contains("San Francisco Giants") && probability.label.contains("64%"))
        try reveal(probability, in: app)
        capture(app, "Actual publisher selected named Giants 64 percent")
        print("WATCH_RECTANGULAR_PUBLISHER_SELECTED=1")
        XCUIDevice.shared.press(.home)
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        XCTAssertTrue(host.wait(for: .runningForeground, timeout: 15))
        let face = host.otherElements["Watch Face"].firstMatch
        XCTAssertTrue(face.waitForExistence(timeout: 15))
        capture(host, "Actual SE40 Watch face before editing")
        host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22)).press(forDuration: 2)
        let addFace = host.scrollViews["Add new face"].firstMatch
        for _ in 0..<16 {
            if addFace.exists && addFace.isHittable { break }
            swipeLeft(host)
        }
        XCTAssertTrue(addFace.exists && addFace.isHittable)
        addFace.tap()
        capture(host, "Actual SE40 all faces gallery")
        let dataRich = host.buttons["Data Rich"].firstMatch
        for _ in 0..<12 {
            if dataRich.exists && dataRich.isHittable && host.frame.contains(dataRich.frame) { break }
            host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.80)).press(forDuration: 0.1, thenDragTo: host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.30)), withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        XCTAssertTrue(dataRich.exists && dataRich.isHittable)
        dataRich.tap()
        let modular = host.cells["Modular"].firstMatch
        XCTAssertTrue(modular.waitForExistence(timeout: 15))
        let add = modular.buttons["Add"].firstMatch
        try reveal(add, in: host)
        XCTAssertEqual(modular.buttons.matching(identifier: "Add").count, 1)
        add.tap()
        let slot = host.buttons["Middle complication"].firstMatch
        for _ in 0..<8 {
            if slot.exists && slot.isHittable && host.frame.contains(slot.frame) { break }
            swipeLeft(host)
        }
        XCTAssertTrue(slot.exists && slot.isHittable && host.frame.contains(slot.frame))
        capture(host, "Actual Modular rectangular Middle slot")
        slot.tap()
        let choice = host.cells["AppGroupCell -- Bain Luck"].firstMatch
        let chromeBottom = host.frame.minY + host.frame.height * 0.26
        for _ in 0..<16 {
            // Gallery rows can be hittable beneath navigation chrome. Reverse
            // the scroll if the named row has moved above the relative boundary.
            let belowChrome = choice.exists && choice.frame.minY > chromeBottom
            if belowChrome && choice.isHittable && host.frame.contains(choice.frame) { break }
            let earlier = choice.exists && !belowChrome
            let start = host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.65))
            let end = host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.85 : 0.40))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(host, "Actual rectangular app gallery Bain Luck")
        XCTAssertTrue(choice.exists && choice.isHittable && host.frame.contains(choice.frame)
                      && choice.frame.minY > chromeBottom)
        choice.tap()
        let installed = host.cells["ComplicationListCell -- Your game"].firstMatch
        XCTAssertTrue(installed.waitForExistence(timeout: 15))
        try reveal(installed, in: host)
        capture(host, "Actual rectangular Your game gallery entry")
        installed.tap()
        XCUIDevice.shared.press(.home)
        XCUIDevice.shared.press(.home)
        XCTAssertTrue(host.wait(for: .runningForeground, timeout: 15))
        XCTAssertTrue(host.otherElements["Watch Face"].firstMatch.waitForExistence(timeout: 15))
        let center = host.otherElements["center"].firstMatch
        XCTAssertTrue(center.waitForExistence(timeout: 15) && center.isHittable && host.frame.contains(center.frame))
        let title = host.staticTexts["watch.complication.title"].firstMatch
        let detail = host.staticTexts["watch.complication.detail"].firstMatch
        let observed = host.staticTexts["watch.complication.observed"].firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 20), "Actual installed WidgetKit extension did not render published title")
        XCTAssertEqual(title.label, "San Francisco Giants win")
        XCTAssertEqual(detail.label, "Saved · 64% · Live")
        XCTAssertTrue(observed.label.hasPrefix("Observed ") && observed.label.count > "Observed ".count)
        let contentBounds = CGRect(origin: .zero, size: center.frame.size)
        for text in [title, detail, observed] {
            XCTAssertTrue(text.frame.width > 0 && text.frame.height > 0 && contentBounds.contains(text.frame),
                          "Actual WidgetKit text frame escapes its rectangular content bounds")
        }
        XCTAssertFalse(host.descendants(matching: .any)["watch.complication.fallback"].firstMatch.exists)
        print("WATCH_RECTANGULAR_INSTALLED_TITLE=\(title.label)")
        print("WATCH_RECTANGULAR_INSTALLED_DETAIL=\(detail.label)")
        print("WATCH_RECTANGULAR_INSTALLED_OBSERVED=\(observed.label)")
        capture(host, "Actual mounted rectangular saved reading")

    }

    @MainActor
    private func swipeLeft(_ host: XCUIApplication) {
        host.coordinate(withNormalizedOffset: CGVector(dx: 0.8, dy: 0.5))
            .press(forDuration: 0.1, thenDragTo: host.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5)), withVelocity: .slow, thenHoldForDuration: 0.4)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        for _ in 0..<32 {
            if element.isHittable && app.frame.contains(element.frame) { return }
            let earlier = element.frame.minY < app.frame.minY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.75 : 0.45))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, "Unreachable actual Widget journey element")
        XCTFail("Cannot reveal complete element: \(element.identifier)")
        throw NSError(domain: "WatchRectangularHost", code: 1)
    }

    @MainActor
    private func capture(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
        let tree = XCTAttachment(string: app.debugDescription); tree.name = name + " hierarchy"; tree.lifetime = .keepAlways; add(tree)
    }
}
#endif
