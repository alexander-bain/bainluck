#if DEBUG
import XCTest

final class WidgetTapJourneyTests: XCTestCase {
    @MainActor
    func testColdActualWidgetTapRetainsOfflineReading() throws {
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
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        app.buttons["watch.pick.101"].tap()
        let baseline = try recordWidgetWarmBaseline(in: app)
        XCUIDevice.shared.press(.home)
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let widget = try mountLauncherOnFreshSiriModularFace(in: host)
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launchEnvironment["BAINLUCK_WATCH_UI_SEED_URL"] = "1"
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.url-fixture-ready"].waitForExistence(timeout: 15))
        app.terminate()
        XCTAssertEqual(app.state, .notRunning)
        XCTAssertTrue(host.wait(for: .runningForeground, timeout: 15))
        XCTAssertTrue(widget.waitForExistence(timeout: 15) && widget.isHittable)
        widgetWarmCapture(host, name: "Actual cold Widget tap from terminated app")
        widget.tap()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 45))
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        try widgetWarmWait(NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"),
            on: state, timeout: 15, message: "Actual cold Widget tap must restore an honestly offline saved reading", app: app)
        let receipt = app.staticTexts["watch.launch-receipt"]
        try widgetWarmWait(NSPredicate(format: "label == %@", "Launcher opens: 1"),
            on: receipt, timeout: 15, message: "Actual cold Widget tap must deliver exactly one route", app: app)
        let process = app.staticTexts["watch.launch-process"]
        XCTAssertTrue(process.waitForExistence(timeout: 15))
        XCTAssertNotNil(UUID(uuidString: process.label))
        XCTAssertNotEqual(process.label, baseline.processUUID)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, baseline.namedReading)
        try widgetWarmReveal(state, in: app)
        widgetWarmCapture(app, name: "Actual cold Widget tap honest saved offline qualifier")
        try widgetWarmReveal(probability, in: app)
        widgetWarmCapture(app, name: "Actual cold Widget tap retained complete named64 reading")
        print("WATCH_UI_ACTUAL_WIDGET_COLD=PASS")
    }

    @MainActor
    func testColdActualWidgetTapOffersPickerWithoutSelection() throws {
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
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        XCUIDevice.shared.press(.home)
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let widget = try mountLauncherOnFreshSiriModularFace(in: host)
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_SEED_URL"] = "1"
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.url-fixture-ready"].waitForExistence(timeout: 15))
        app.terminate()
        XCTAssertEqual(app.state, .notRunning)
        XCTAssertTrue(host.wait(for: .runningForeground, timeout: 15))
        XCTAssertTrue(widget.waitForExistence(timeout: 15) && widget.isHittable && host.frame.contains(widget.frame))
        widgetWarmCapture(host, name: "Actual cold Widget launcher with no saved selection")
        widget.tap()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 45))
        let choice = app.buttons["watch.pick.101"]
        XCTAssertTrue(choice.waitForExistence(timeout: 20), "Actual cold Widget tap without selection must offer the picker")
        let receipt = app.staticTexts["watch.launch-receipt"]
        try widgetWarmWait(NSPredicate(format: "label == %@", "Launcher opens: 1"),
            on: receipt, timeout: 15, message: "Actual empty Widget tap must deliver exactly one route", app: app)
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        try widgetWarmReveal(choice, in: app)
        widgetWarmCapture(app, name: "Actual cold empty Widget tap offers named game choices")
        print("WATCH_UI_ACTUAL_WIDGET_EMPTY=PASS")
    }

    @MainActor
    func testFreshConfiguredFaceIsActiveBeforeActualLauncherTap() throws {
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
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        app.buttons["watch.pick.101"].tap()
        let baseline = try recordWidgetWarmBaseline(in: app)
        let change = app.buttons["watch.choose-another"]
        try widgetWarmReveal(change, in: app)
        change.tap()
        let picker = try assertWidgetWarmPickerIsPresented(in: app)
        XCUIDevice.shared.press(.home)
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let widget = try mountLauncherOnFreshSiriModularFace(in: host)
        XCTAssertFalse(host.otherElements["Face Library View"].firstMatch.exists)
        XCTAssertTrue(host.otherElements["Watch Face"].firstMatch.isHittable)
        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: widget, app: app,
            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "fresh face activation")
        print("WATCH_UI_FRESH_FACE_ACTIVATION=PASS")
    }

    @MainActor
    func testActualCornerSavedReadingAndTap() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        let originalObservation = Date().addingTimeInterval(-120)
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1",
            "BAINLUCK_WATCH_UI_SHARED_PUBLICATION": "1", "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY": "1",
            "BAINLUCK_WATCH_UI_FIXED_OBSERVATION": ISO8601DateFormatter().string(from: originalObservation)
        ]
        defer { app.terminate() }
        app.launch()
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        app.buttons["watch.pick.101"].tap()
        let baseline = try recordWidgetWarmBaseline(in: app)
        let change = app.buttons["watch.choose-another"]
        try widgetWarmReveal(change, in: app)
        change.tap()
        let picker = try assertWidgetWarmPickerIsPresented(in: app)
        XCUIDevice.shared.press(.home)
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let reading = try mountSavedCornerOnFreshExactographFace(in: host)
        XCTAssertEqual(reading.value as? String, "Saved · SF win · 64%")
        XCTAssertTrue(reading.label.contains("San Francisco Giants") && reading.label.contains("Los Angeles Dodgers") && reading.label.contains("64%"))
        XCTAssertTrue(reading.label.contains("Observed \(originalObservation.formatted(date: .abbreviated, time: .shortened))"))
        // This must be the separate rendered label, not the reading's synthesized
        // accessible value. Missing/ignored/truncated label is an unpaid feature.
        let curvedLabel = host.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Saved · SF win")).firstMatch
        try freshFaceRequire(curvedLabel.waitForExistence(timeout: 15)
                             && curvedLabel.frame.width > 0 && curvedLabel.frame.height > 0
                             && host.frame.contains(curvedLabel.frame),
                             "Actual corner lacks complete rendered Saved + named win label", host: host)
        freshFaceCapture(host, name: "Actual configured Infograph corner 64 percent and full Saved SF win curve")
        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: reading, app: app,
            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "saved Infograph corner forecast")
        print("WATCH_UI_ACTUAL_CORNER_SAVED=PASS")
    }

    @MainActor
    func testActualCircularSavedReadingAndTap() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1",
            "BAINLUCK_WATCH_UI_SHARED_PUBLICATION": "1",
            "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY": "1"
        ]
        defer { app.terminate() }
        app.launch()
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        app.buttons["watch.pick.101"].tap()
        let baseline = try recordWidgetWarmBaseline(in: app)
        let change = app.buttons["watch.choose-another"]
        try widgetWarmReveal(change, in: app)
        change.tap()
        let picker = try assertWidgetWarmPickerIsPresented(in: app)
        XCUIDevice.shared.press(.home)
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let widget = try mountLauncherOnFreshSiriModularFace(in: host, savedCircular: true)
        let reading = widget.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", "Saved reading.")).firstMatch
        try freshFaceRequire(reading.exists && reading.label.contains("San Francisco Giants")
                             && reading.label.contains("64%") && reading.label.contains("Observed"),
                             "Configured circular slot lacks full saved named forecast and original observation", host: host)
        XCTAssertEqual(reading.value as? String, "Saved · SF win · 64%")
        freshFaceCapture(host, name: "Actual configured circular Saved SF win 64 percent")
        try tapActualWidgetHostAndAssertWarmReturn(host: host, widget: widget, app: app,
            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "saved circular forecast")
        print("WATCH_UI_ACTUAL_CIRCULAR_SAVED=PASS")
    }

    @MainActor
    func testActualComplicationHost() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1",
            "BAINLUCK_WATCH_UI_SHARED_PUBLICATION": "1"
        ]
        defer { app.terminate() }
        app.launch()
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        app.buttons["watch.pick.101"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["watch.home-probability"].firstMatch.waitForExistence(timeout: 20))
        let baseline = try recordWidgetWarmBaseline(in: app)
        let change = app.buttons["watch.choose-another"]
        try widgetWarmReveal(change, in: app)
        change.tap()
        let picker = try assertWidgetWarmPickerIsPresented(in: app)
        XCUIDevice.shared.press(.home)
        let carousel = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let widget = try mountLauncherOnFreshSiriModularFace(in: carousel)
        try tapActualWidgetHostAndAssertWarmReturn(host: carousel, widget: widget, app: app,
            baseline: baseline, tapOrdinal: 1, dismissedOverlays: picker, phase: "picker")
        let help = app.buttons["watch.continue-on-phone"]
        try widgetWarmReveal(help, in: app)
        help.tap()
        let helpOverlay = try assertWidgetWarmHelpIsPresented(in: app)
        XCUIDevice.shared.press(.home)
        try tapActualWidgetHostAndAssertWarmReturn(host: carousel, widget: widget, app: app,
            baseline: baseline, tapOrdinal: 2, dismissedOverlays: helpOverlay, phase: "help")
        print("WATCH_UI_ACTUAL_WIDGET_WARM=PASS")

    }
}
#endif

#if DEBUG
import XCTest

// Apply-ready extension for the scratch WidgetTapJourneyTests class.
// Navigation/configuration remains in the primary's actual Watch host journey.
// This helper taps the supplied real host element exactly once. It contains no
// URL delivery, app activation, relaunch, fixture callback or fallback path.
extension WidgetTapJourneyTests {
    struct WidgetWarmBaseline {
        let processUUID: String
        let namedReading: String
        let initialRouteCount: Int
    }

    enum WidgetWarmAssertionFailure: Error {
        case missingEvidence(String)
    }

    @MainActor
    func recordWidgetWarmBaseline(in app: XCUIApplication) throws -> WidgetWarmBaseline {
        try widgetWarmRequire(app.wait(for: .runningForeground, timeout: 15),
                              "Selected app must be foreground before recording warm baseline", app: app)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        try widgetWarmRequire(probability.waitForExistence(timeout: 15),
                              "Missing named selected-game reading", app: app)
        try widgetWarmReveal(probability, in: app)
        try widgetWarmRequire(probability.label.contains("San Francisco Giants") && probability.label.contains("64%"),
                              "Baseline must be the real selected Giants fixture reading at 64%", app: app)
        widgetWarmCapture(app, name: "Actual Widget tap baseline complete named Giants 64 percent")

        let process = app.staticTexts["watch.launch-process"]
        let route = app.staticTexts["watch.launch-receipt"]
        try widgetWarmRequire(process.waitForExistence(timeout: 15) && route.waitForExistence(timeout: 15),
                              "Missing process UUID or accepted-route receipt", app: app)
        let processUUID = process.label
        try widgetWarmRequire(UUID(uuidString: processUUID) != nil,
                              "Process receipt must be a valid per-process UUID", app: app)
        let prefix = "Launcher opens: "
        try widgetWarmRequire(route.label.hasPrefix(prefix), "Malformed accepted-route receipt", app: app)
        let count = try XCTUnwrap(Int(route.label.dropFirst(prefix.count)), "Accepted-route count must be an integer")
        try widgetWarmRequire(count == 0, "Fresh selected-game baseline must have no earlier launcher delivery", app: app)
        return WidgetWarmBaseline(processUUID: processUUID, namedReading: probability.label, initialRouteCount: count)
    }

    @MainActor
    func assertWidgetWarmPickerIsPresented(in app: XCUIApplication) throws -> [XCUIElement] {
        let cancel = app.buttons["watch.picker-cancel"].firstMatch
        let alternative = app.buttons["watch.pick.202"]
        try widgetWarmRequire(cancel.waitForExistence(timeout: 15) && alternative.waitForExistence(timeout: 15),
                              "Picker must actually be open before the real host tap", app: app)
        widgetWarmCapture(app, name: "Actual Widget tap precondition picker overlay open")
        return [cancel, alternative]
    }

    @MainActor
    func assertWidgetWarmHelpIsPresented(in app: XCUIApplication) throws -> [XCUIElement] {
        let alert = app.otherElements["Continue on iPhone"].firstMatch
        try widgetWarmRequire(alert.waitForExistence(timeout: 15),
                              "Continue explanation must actually be open before the real host tap", app: app)
        widgetWarmCapture(app, name: "Actual Widget tap precondition Continue overlay open")
        return [alert]
    }

    @MainActor
    func tapActualWidgetHostAndAssertWarmReturn(
        host: XCUIApplication,
        widget: XCUIElement,
        app: XCUIApplication,
        baseline: WidgetWarmBaseline,
        tapOrdinal: Int,
        dismissedOverlays: [XCUIElement],
        phase: String
    ) throws {
        try widgetWarmRequire((1...2).contains(tapOrdinal), "Warm journey expects first or second actual tap", app: app)
        try widgetWarmRequire(!dismissedOverlays.isEmpty, "Each warm tap must verify a previously observed overlay", app: app)
        try widgetWarmRequire(host.wait(for: .runningForeground, timeout: 15),
                              "Actual Watch host must be foreground before tapping its Widget", app: app)
        try widgetWarmRequire(app.state != .notRunning,
                              "Selected app terminated before host tap; this cannot prove a warm route", app: host)
        try widgetWarmRequire(widget.waitForExistence(timeout: 15) && widget.isHittable && host.frame.contains(widget.frame),
                              "Observed real Widget host element must be fully visible and hittable", app: host)
        widgetWarmCapture(host, name: "Actual Widget host before tap - \(phase)")
        // The sole launch/delivery action in this helper. The primary supplies an
        // element identified in the real Carousel/Widget host's fresh hierarchy.
        widget.tap()

        try widgetWarmRequire(app.wait(for: .runningForeground, timeout: 45),
                              "Real host tap did not foreground the selected-game app", app: host)
        let route = app.staticTexts["watch.launch-receipt"]
        let process = app.staticTexts["watch.launch-process"]
        try widgetWarmRequire(route.waitForExistence(timeout: 15) && process.waitForExistence(timeout: 15),
                              "Real host tap returned without route/process receipts", app: app)
        let expectedCount = baseline.initialRouteCount + tapOrdinal
        try widgetWarmWait(NSPredicate(format: "label == %@", "Launcher opens: \(expectedCount)"),
                           on: route, timeout: 45, message: "Each real host tap must increment the accepted route exactly once", app: app)
        try widgetWarmRequire(process.label == baseline.processUUID,
                              "Real host tap cold-relaunched the app instead of preserving its process UUID", app: app)
        for overlay in dismissedOverlays {
            try widgetWarmWait(NSPredicate(format: "exists == false"), on: overlay, timeout: 15,
                               message: "Real host tap did not dismiss the previously observed overlay", app: app)
        }
        try widgetWarmRequire(!app.buttons["watch.picker-cancel"].firstMatch.exists && !app.otherElements["Continue on iPhone"].firstMatch.exists,
                              "The selected reading must be unobstructed by picker and Continue overlays", app: app)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        try widgetWarmRequire(probability.waitForExistence(timeout: 15),
                              "Real host tap lost the selected named probability", app: app)
        try widgetWarmRequire(probability.label == baseline.namedReading,
                              "Real host tap changed the selected named Giants 64% reading", app: app)
        try widgetWarmReveal(probability, in: app)
        widgetWarmCapture(app, name: "Actual Widget tap retained full named Giants reading - \(phase)")
        // Recheck after reveal: scrolling and timeline updates must not reset the
        // receipt, restore an overlay or introduce a different selected reading.
        try widgetWarmRequire(route.label == "Launcher opens: \(expectedCount)" && process.label == baseline.processUUID,
                              "Route/process identity changed during post-tap evidence capture", app: app)
        try widgetWarmRequire(probability.label == baseline.namedReading,
                              "Selected reading changed during post-tap evidence capture", app: app)
        try widgetWarmRequire(app.state == .runningForeground,
                              "Selected app left foreground during post-tap evidence capture", app: app)
        try widgetWarmRequire(!app.buttons["watch.picker-cancel"].firstMatch.exists
                              && !app.otherElements["Continue on iPhone"].firstMatch.exists,
                              "Picker or Continue overlay returned during post-tap evidence capture", app: app)
    }

    @MainActor
    private func widgetWarmWait(_ predicate: NSPredicate, on element: XCUIElement, timeout: TimeInterval,
                                message: String, app: XCUIApplication) throws {
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        let result = XCTWaiter.wait(for: [expectation], timeout: timeout)
        try widgetWarmRequire(result == .completed, message, app: app)
    }

    @MainActor
    private func widgetWarmRequire(_ condition: Bool, _ message: String, app: XCUIApplication) throws {
        guard condition else {
            widgetWarmCapture(app, name: "Actual Widget warm assertion failed - \(message)")
            XCTFail(message)
            throw WidgetWarmAssertionFailure.missingEvidence(message)
        }
    }

    @MainActor
    func widgetWarmReveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        try widgetWarmRequire(element.waitForExistence(timeout: 15), "Expected element absent before reveal", app: app)
        for _ in 0..<32 {
            if element.isHittable && app.frame.contains(element.frame) { return }
            let earlier = element.frame.minY < app.frame.minY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.75 : 0.45))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        try widgetWarmRequire(false, "Cannot reveal complete element: \(element.identifier), frame \(element.frame), viewport \(app.frame)", app: app)
    }

    @MainActor
    private func widgetWarmCapture(_ app: XCUIApplication, name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name
        image.lifetime = .keepAlways
        add(image)
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = name + " hierarchy"
        tree.lifetime = .keepAlways
        add(tree)
    }
}
#endif

#if DEBUG
import XCTest

// Apply-ready actual-host setup, observed in watch-widget-tap-08.log and the
// current gallery journey. No URL opening, app activation or seeded-face state.
extension WidgetTapJourneyTests {
    @MainActor
    func mountLauncherOnFreshSiriModularFace(in host: XCUIApplication, savedCircular: Bool = false) throws -> XCUIElement {
        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15), "Watch host is not foreground", host: host)
        let face = host.otherElements["Watch Face"].firstMatch
        try freshFaceRequire(face.waitForExistence(timeout: 15), "No actual Watch Face", host: host)
        // Current successful journey uses this proportional host coordinate;
        // it does not depend on the simulator's absolute pixel dimensions.
        host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22)).press(forDuration: 2)
        let addFace = host.scrollViews["Add new face"].firstMatch
        for _ in 0..<16 {
            if addFace.exists && addFace.isHittable { break }
            freshFaceSwipeLeft(in: host)
        }
        try freshFaceRequire(addFace.exists && addFace.isHittable,
                             "Fresh face chooser did not expose Add new face", host: host)
        addFace.tap()
        let newFaces = host.buttons["New Watch Faces"].firstMatch
        try freshFaceRequire(newFaces.waitForExistence(timeout: 15) && newFaces.isHittable,
                             "New Watch Faces gallery control absent", host: host)
        newFaces.tap()
        let siri = host.cells["Siri Modular"].firstMatch
        try freshFaceRequire(siri.waitForExistence(timeout: 15), "Observed Siri Modular gallery cell absent", host: host)
        // Only the observed gallery Add button is used. Refuse ambiguity or an
        // Add button outside the named card instead of choosing another face.
        let add = siri.buttons["Add"].firstMatch
        try freshFaceRequire(add.waitForExistence(timeout: 15) && siri.buttons.matching(identifier: "Add").count == 1
                             && add.isHittable && siri.frame.intersects(add.frame),
                             "Cannot attribute the visible Add control to Siri Modular", host: host)
        add.tap()
        let slot = host.buttons["Bottom Left complication"].firstMatch
        for _ in 0..<8 {
            if slot.exists && slot.isHittable && host.frame.contains(slot.frame) { break }
            freshFaceSwipeLeft(in: host)
        }
        try freshFaceRequire(slot.exists && slot.isHittable && host.frame.contains(slot.frame),
                             "Fresh face editor did not expose Bottom Left complication", host: host)
        slot.tap()
        let choice = try WatchComplicationGalleryNavigation.bainLuckAppRow(in: host) { name in
            freshFaceCapture(host, name: name)
        }
        choice.tap()
        try WatchComplicationGalleryNavigation.requireBainLuckDetail(in: host) { name in
            freshFaceCapture(host, name: name)
        }
        let installed = host.cells["ComplicationListCell -- Your game"].firstMatch
        try freshFaceRequire(installed.waitForExistence(timeout: 15) && installed.isHittable,
                             "Installed Your game complication absent or unreachable", host: host)
        freshFaceCapture(host, name: "Actual gallery selected BainLuckWatch Your game")
        installed.tap()
        XCUIDevice.shared.press(.home)
        try activateConfiguredSiriModularFace(in: host)
        let widget = host.otherElements["bottom-left"].firstMatch
        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15)
                             && widget.waitForExistence(timeout: 15) && widget.descendants(matching: .any).matching(savedCircular
                                ? NSPredicate(format: "label BEGINSWITH %@", "Saved reading.")
                                : NSPredicate(format: "label == %@", "Open your selected game in Bain Luck, or choose a game")).firstMatch.exists
                             && widget.isHittable && host.frame.contains(widget.frame),
                             "Fresh installed face has no reachable BainLuckWatch launcher", host: host)
        freshFaceCapture(host, name: "Fresh face actual mounted BainLuckWatch launcher")
        // Caller now uses the separate actual-tap warm assertions. Mounting alone
        // is never a route/retention/warm-delivery PASS.
        return widget
    }

    @MainActor
    private func mountSavedCornerOnFreshExactographFace(in host: XCUIApplication) throws -> XCUIElement {
        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15), "Corner host not foreground", host: host)
        let face = host.otherElements["Watch Face"].firstMatch
        try freshFaceRequire(face.waitForExistence(timeout: 15), "No actual corner Watch Face", host: host)
        host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22)).press(forDuration: 2)
        let addFace = host.scrollViews["Add new face"].firstMatch
        for _ in 0..<16 {
            if addFace.exists && addFace.isHittable { break }
            freshFaceSwipeLeft(in: host)
        }
        try freshFaceRequire(addFace.exists && addFace.isHittable, "Corner gallery has no Add new face", host: host)
        addFace.tap()
        let newFaces = host.buttons["New Watch Faces"].firstMatch
        try freshFaceRequire(newFaces.waitForExistence(timeout: 15) && newFaces.isHittable,
                             "Corner gallery lacks New Watch Faces", host: host)
        newFaces.tap()
        // Exactograph and its attributed Add were opened in retained run
        // 37471676420. Its preview is not acceptance: the corner runtime ID,
        // complete label and actual tap below remain mandatory.
        freshFaceCapture(host, name: "Corner observed New Watch Faces before Exactograph selection")
        let exactograph = host.cells["Exactograph"].firstMatch
        for _ in 0..<10 {
            if exactograph.exists && exactograph.isHittable { break }
            host.swipeUp()
        }
        freshFaceCapture(host, name: "Corner dependency observed fresh gallery Exactograph availability")
        try freshFaceRequire(exactograph.exists && exactograph.isHittable,
                             "CORNER_FACE_DEPENDENCY: Exactograph absent from bounded hosted gallery", host: host)
        let add = exactograph.buttons["Add"].firstMatch
        try freshFaceRequire(add.exists && add.isHittable && exactograph.buttons.matching(identifier: "Add").count == 1
                             && exactograph.frame.intersects(add.frame),
                             "Cannot attribute Add to observed Exactograph card", host: host)
        add.tap()
        // Select by the editor's observed labels; no guessed slot identifier or
        // coordinate taps. The installed corner identifier then proves family.
        var choices: [XCUIElement] = []
        for _ in 0..<8 {
            choices = host.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", "complication")).allElementsBoundByIndex.filter {
                let name = $0.label.lowercased()
                return (name.contains("top left") || name.contains("upper left")) && $0.isHittable && host.frame.contains($0.frame)
            }
            if choices.count == 1 { break }
            freshFaceSwipeLeft(in: host)
        }
        freshFaceCapture(host, name: "Corner dependency observed Exactograph editor slot labels")
        try freshFaceRequire(choices.count == 1,
                             "CORNER_FACE_DEPENDENCY: no unambiguous visible Exactograph upper-left complication", host: host)
        choices[0].tap()
        let appRow = try WatchComplicationGalleryNavigation.bainLuckAppRow(in: host) { freshFaceCapture(host, name: $0) }
        appRow.tap()
        try WatchComplicationGalleryNavigation.requireBainLuckDetail(in: host) { freshFaceCapture(host, name: $0) }
        let installed = host.cells["ComplicationListCell -- Your game"].firstMatch
        try freshFaceRequire(installed.waitForExistence(timeout: 15) && installed.isHittable,
                             "CORNER_FACE_DEPENDENCY: Your game unavailable for observed corner slot", host: host)
        freshFaceCapture(host, name: "Actual Exactograph corner gallery Bain Luck Your game")
        installed.tap()
        XCUIDevice.shared.press(.home)
        let library = host.otherElements["Face Library View"].firstMatch
        let arrived = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in library.exists || face.exists }, object: host)
        try freshFaceRequire(XCTWaiter.wait(for: [arrived], timeout: 15) == .completed,
                             "Configured Exactograph did not leave editor", host: host)
        if library.exists {
            let title = host.staticTexts["Switcher Face Title"].firstMatch
            let previews = host.scrollViews.allElementsBoundByIndex.filter { $0.label.lowercased().hasPrefix("exactograph,") && $0.isHittable }
            try freshFaceRequire(title.exists && title.label == "Exactograph" && previews.count == 1,
                                 "No unambiguous observed Exactograph activation preview", host: host)
            freshFaceCapture(host, name: "Actual configured Exactograph preview before activation")
            previews[0].tap()
        }
        let activated = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in face.exists && !library.exists }, object: host)
        try freshFaceRequire(XCTWaiter.wait(for: [activated], timeout: 15) == .completed,
                             "Configured Exactograph did not become active", host: host)
        let reading = host.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch
        try freshFaceRequire(reading.waitForExistence(timeout: 15) && reading.isHittable && host.frame.contains(reading.frame),
                             "Actual configured Exactograph has no fitting saved corner forecast", host: host)
        return reading
    }

    @MainActor
    private func activateConfiguredSiriModularFace(in host: XCUIApplication) throws {
        let library = host.otherElements["Face Library View"].firstMatch
        let face = host.otherElements["Watch Face"].firstMatch
        let arrived = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            library.exists || face.exists
        }, object: host)
        try freshFaceRequire(XCTWaiter.wait(for: [arrived], timeout: 15) == .completed,
                             "Configured face did not leave its editor", host: host)
        if library.exists {
            let title = host.staticTexts["Switcher Face Title"].firstMatch
            let previews = host.scrollViews.matching(NSPredicate(
                format: "label ==[c] %@", "siri modular, Customizable"))
            let preview = previews.firstMatch
            try freshFaceRequire(title.waitForExistence(timeout: 15) && title.label == "Siri Modular"
                                 && preview.waitForExistence(timeout: 15) && previews.count == 1 && preview.isHittable
                                 && host.frame.contains(CGPoint(x: preview.frame.midX, y: preview.frame.midY)),
                                 "Face Library has no unambiguous visible Siri Modular preview", host: host)
            freshFaceCapture(host, name: "Configured Siri Modular preview before activation")
            // Select the actual named face preview once; crown presses alone
            // can leave Carousel in its library rather than on the active face.
            preview.tap()
        }
        let activated = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            face.exists && !library.exists
        }, object: host)
        try freshFaceRequire(XCTWaiter.wait(for: [activated], timeout: 15) == .completed
                             && face.isHittable && host.wait(for: .runningForeground, timeout: 15),
                             "Configured Siri Modular face did not become active", host: host)
        freshFaceCapture(host, name: "Configured Siri Modular active Watch Face")
    }

    @MainActor
    private func freshFaceSwipeLeft(in host: XCUIApplication) {
        let start = host.coordinate(withNormalizedOffset: CGVector(dx: 0.8, dy: 0.5))
        let end = host.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5))
        start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
    }

    @MainActor
    private func freshFaceRequire(_ condition: Bool, _ message: String, host: XCUIApplication) throws {
        guard condition else {
            freshFaceCapture(host, name: "UNPAID fresh Widget face - " + message)
            XCTFail(message)
            throw NSError(domain: "WatchWidgetFreshFace", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
        }
    }

    @MainActor
    private func freshFaceCapture(_ host: XCUIApplication, name: String) {
        let screenshot = XCTAttachment(screenshot: host.screenshot())
        screenshot.name = name
        screenshot.lifetime = .keepAlways
        add(screenshot)
        let tree = XCTAttachment(string: host.debugDescription)
        tree.name = name + " hierarchy"
        tree.lifetime = .keepAlways
        add(tree)
    }
}

/// Carousel retains a selected complication's detail page and app-list position.
/// Normalize its observed page roles before searching the exact Bain Luck row.
@MainActor
enum WatchComplicationGalleryNavigation {
    static func bainLuckAppRow(in host: XCUIApplication, capture: (String) -> Void) throws -> XCUIElement {
        let appRows = host.cells.matching(NSPredicate(format: "identifier BEGINSWITH %@ OR identifier BEGINSWITH %@",
                                                     "AppGroupCell -- ", "FeaturedWidgetCell -- "))
        let details = host.cells.matching(NSPredicate(format: "identifier BEGINSWITH %@", "ComplicationListCell -- "))
        let back = host.buttons["BackButton"].firstMatch
        let detailPage = host.otherElements["ComplicationPickerDetailView"].firstMatch
        let parentPage = host.navigationBars["NTKStarbearPickerView"].firstMatch
        for _ in 0..<3 {
            guard detailPage.exists && details.firstMatch.exists && back.exists else { break }
            capture("Actual Widget gallery retained detail before Back")
            try require(back.isHittable && host.frame.contains(back.frame),
                        "Retained complication detail has no reachable Back control", capture: capture)
            back.tap()
            try require(parentPage.waitForExistence(timeout: 15),
                        "Back did not return to NTKStarbearPickerView app gallery", capture: capture)
        }
        try require(parentPage.exists && appRows.firstMatch.exists && !detailPage.exists && !back.exists,
                    "Expected NTKStarbearPickerView parent before app search", capture: capture)
        capture("Actual Widget app gallery before bounded app search")
        let choice = host.cells["AppGroupCell -- Bain Luck"].firstMatch
        let chromeBottom = host.frame.minY + host.frame.height * 0.26
        // Virtualized rows may disappear between large drags. Use the actual
        // visible alphabetical app rows to choose direction and move by at most
        // half a row, rather than sweeping past the target on a fixed schedule.
        var visits: [String: Int] = [:]
        for step in 0..<32 {
            let exists = choice.exists
            let belowChrome = exists && choice.frame.minY > chromeBottom
            if belowChrome && choice.isHittable && host.frame.contains(choice.frame) { return choice }
            let visibleApps = host.cells.matching(NSPredicate(format: "identifier BEGINSWITH %@", "AppGroupCell -- "))
                .allElementsBoundByIndex.filter { $0.frame.maxY > chromeBottom && $0.frame.minY < host.frame.maxY }
                .sorted { $0.frame.minY < $1.frame.minY }
            let earlier: Bool
            if exists {
                earlier = choice.frame.minY <= chromeBottom
            } else if let first = visibleApps.first {
                earlier = first.label.localizedCaseInsensitiveCompare("Bain Luck") == .orderedDescending
            } else {
                // Featured precedes All Apps on the observed parent page.
                earlier = false
            }
            let rowHeight = visibleApps.first?.frame.height ?? host.frame.height * 0.20
            let distance = min(host.frame.height * 0.12, max(12, rowHeight * 0.5))
            let position = visibleApps.map { "\($0.identifier):\(Int(($0.frame.minY / 4).rounded()) * 4)" }.joined(separator: "|")
            print("WATCH_GALLERY_STEP=\(step) earlier=\(earlier) targetExists=\(exists) rows=\(position)")
            if !position.isEmpty {
                visits[position, default: 0] += 1
                try require(visits[position, default: 0] <= 3,
                            "App-gallery search repeated visible rows without finding exact Bain Luck: \(position)", capture: capture)
            }
            let endY = 0.65 + (earlier ? distance : -distance) / host.frame.height
            host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.65))
                .press(forDuration: 0.1,
                       thenDragTo: host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: endY)),
                       withVelocity: .slow, thenHoldForDuration: 0.4)
            try require(parentPage.exists && !detailPage.exists && !back.exists,
                        "App-gallery search unexpectedly left NTKStarbearPickerView", capture: capture)
        }
        try require(choice.exists && choice.isHittable && host.frame.contains(choice.frame)
                    && choice.frame.minY > chromeBottom,
                    "Exact Bain Luck app row unreachable after bounded row-guided search", capture: capture)
        return choice
    }

    static func requireBainLuckDetail(in host: XCUIApplication, capture: (String) -> Void) throws {
        let detailPage = host.otherElements["ComplicationPickerDetailView"].firstMatch
        let title = host.navigationBars["Bain Luck"].firstMatch
        let game = host.cells["ComplicationListCell -- Your game"].firstMatch
        try require(detailPage.waitForExistence(timeout: 15) && title.exists && game.exists,
                    "Exact Bain Luck detail and Your game required after selecting app row", capture: capture)
        capture("Actual Bain Luck complication detail after exact app selection")
    }

    private static func require(_ condition: Bool, _ message: String, capture: (String) -> Void) throws {
        guard condition else {
            capture("UNPAID Widget gallery navigation - " + message)
            XCTFail(message)
            throw NSError(domain: "WatchComplicationGalleryNavigation", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: message])
        }
    }
}
#endif
