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
        capture(host, "Actual Watch face before rectangular editing")
        host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22)).press(forDuration: 2)
        let addFace = host.scrollViews["Add new face"].firstMatch
        for _ in 0..<16 {
            if addFace.exists && addFace.isHittable { break }
            swipeLeft(host)
        }
        XCTAssertTrue(addFace.exists && addFace.isHittable)
        addFace.tap()
        capture(host, "Actual Watch all faces gallery")
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
        let choice = try WatchComplicationGalleryNavigation.bainLuckAppRow(in: host) { name in
            capture(host, name)
        }
        capture(host, "Actual rectangular app gallery Bain Luck")
        choice.tap()
        try WatchComplicationGalleryNavigation.requireBainLuckDetail(in: host) { name in
            capture(host, name)
        }
        let installed = host.cells["ComplicationListCell -- Your game"].firstMatch
        XCTAssertTrue(installed.waitForExistence(timeout: 15))
        try reveal(installed, in: host)
        capture(host, "Actual rectangular Your game gallery entry")
        installed.tap()
        XCUIDevice.shared.press(.home)
        try activateConfiguredModularFace(in: host)
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
    private func activateConfiguredModularFace(in host: XCUIApplication) throws {
        let library = host.otherElements["Face Library View"].firstMatch
        let face = host.otherElements["Watch Face"].firstMatch
        let arrived = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            library.exists || face.exists
        }, object: host)
        XCTAssertEqual(XCTWaiter.wait(for: [arrived], timeout: 15), .completed,
                       "Configured Modular face did not leave its editor")
        if library.exists {
            let title = host.staticTexts["Switcher Face Title"].firstMatch
            let previews = host.scrollViews.matching(NSPredicate(
                format: "label ==[c] %@", "modular, Customizable"))
            let preview = previews.firstMatch
            XCTAssertTrue(title.waitForExistence(timeout: 15) && title.label == "Modular"
                          && preview.waitForExistence(timeout: 15) && previews.count == 1
                          && preview.isHittable
                          && host.frame.contains(CGPoint(x: preview.frame.midX, y: preview.frame.midY)),
                          "Face Library has no unambiguous visible Modular preview")
            capture(host, "Configured Modular preview before activation")
            // The retained hosted failure stopped in this library. Select the
            // named configured face instead of assuming a second crown press activates it.
            preview.tap()
        }
        let activated = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            face.exists && !library.exists
        }, object: host)
        XCTAssertEqual(XCTWaiter.wait(for: [activated], timeout: 15), .completed,
                       "Configured Modular face did not become active")
        XCTAssertTrue(face.isHittable)
        capture(host, "Configured Modular active Watch Face")
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
