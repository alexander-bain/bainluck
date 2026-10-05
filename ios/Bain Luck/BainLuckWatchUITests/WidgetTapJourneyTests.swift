#if DEBUG
import XCTest

final class WidgetTapJourneyTests: XCTestCase {
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
    func mountLauncherOnFreshSiriModularFace(in host: XCUIApplication) throws -> XCUIElement {
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
        let choice = host.cells["AppGroupCell -- Bain Luck"].firstMatch
        for _ in 0..<16 {
            // Avoid the observed gallery navigation chrome without hardcoding a
            // particular Watch's pixel size. Failure never substitutes a tap.
            let belowChrome = choice.exists && choice.frame.minY > host.frame.minY + host.frame.height * 0.26
            if belowChrome && choice.isHittable && host.frame.contains(choice.frame) { break }
            let earlier = choice.exists && !belowChrome
            let start = host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.65))
            let end = host.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.85 : 0.40))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        try freshFaceRequire(choice.exists && choice.isHittable && host.frame.contains(choice.frame),
                             "Installed BainLuckWatch gallery group unreachable", host: host)
        choice.tap()
        let installed = host.cells["ComplicationListCell -- Your game"].firstMatch
        try freshFaceRequire(installed.waitForExistence(timeout: 15) && installed.isHittable,
                             "Installed Your game complication absent or unreachable", host: host)
        freshFaceCapture(host, name: "Actual gallery selected BainLuckWatch Your game")
        installed.tap()
        XCUIDevice.shared.press(.home)
        XCUIDevice.shared.press(.home)
        let widget = host.otherElements["bottom-left"].firstMatch
        try freshFaceRequire(host.wait(for: .runningForeground, timeout: 15)
                             && widget.waitForExistence(timeout: 15) && widget.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Open your selected game in Bain Luck, or choose a game")).firstMatch.exists
                             && widget.isHittable && host.frame.contains(widget.frame),
                             "Fresh installed face has no reachable BainLuckWatch launcher", host: host)
        freshFaceCapture(host, name: "Fresh face actual mounted BainLuckWatch launcher")
        // Caller now uses the separate actual-tap warm assertions. Mounting alone
        // is never a route/retention/warm-delivery PASS.
        return widget
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
#endif
