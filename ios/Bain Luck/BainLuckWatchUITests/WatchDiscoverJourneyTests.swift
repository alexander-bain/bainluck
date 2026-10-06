import XCTest

final class WatchDiscoverJourneyTests: XCTestCase {
    @MainActor
    func testSelectedGameStaysFirstAndDiscoveriesSurviveOfflineRelaunch() throws {
        // Two launches plus continuation and retained-clock checks form one journey.
        // Every other case retains the harness default of 180 seconds.
        executionTimeAllowance = 300
        try savedJourney(largeText: false)
        print("WATCH_UI_DISCOVERIES_SAVED=PASS")
    }

    @MainActor
    func testDiscoveriesAtAccessibilitySizeKeepReadingAndReturnReachable() throws {
        try savedJourney(largeText: true)
        print("WATCH_UI_DISCOVERIES_LARGE=PASS")
    }

    @MainActor
    private func savedJourney(largeText: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = environment(largeText: largeText)
        app.launch()
        let pick = app.buttons["watch.pick.101"]
        XCTAssertTrue(pick.waitForExistence(timeout: 20))
        try tap(pick, in: app)
        XCTAssertTrue(element("watch.home-probability", in: app).waitForExistence(timeout: 15))
        try openDiscoveries(in: app)
        let selected = element("watch.discovery.selected", in: app)
        XCTAssertTrue(selected.waitForExistence(timeout: 15))
        XCTAssertTrue(element("watch.discovery.selected-matchup", in: app).label.contains("Giants"))
        let chance = element("watch.discovery.probability.301", in: app)
        XCTAssertTrue(chance.waitForExistence(timeout: 15))
        try reveal(chance, in: app)
        XCTAssertTrue(chance.label.contains("46%"), chance.label)
        XCTAssertFalse(element("watch.discovery.card.303", in: app).exists, "Selected game reserves the first of three slots")
        let age = element("watch.discovery.age.301", in: app)
        try reveal(age, in: app)
        let originalClock = try XCTUnwrap(age.value as? String)
        XCTAssertTrue(originalClock.contains("2026-10-05T12:00:00"), originalClock)
        if !largeText {
            try tap(app.buttons["watch.discovery.continue.301"], in: app)
            // watchOS exposes this presentation as Other, not Alert. The OK
            // button is in a sibling cell below the long help text.
            let help = app.otherElements["Continue on iPhone"].firstMatch
            XCTAssertTrue(help.waitForExistence(timeout: 10))
            let helpMessage = help.staticTexts.containing(NSPredicate(
                format: "label CONTAINS %@ AND label CONTAINS %@",
                "Will inflation fall below 3%?", "Look for Bain Luck’s Handoff option"
            )).firstMatch
            XCTAssertTrue(helpMessage.exists)
            try tap(app.buttons["OK"].firstMatch, in: app)
            let continuation = element("watch.discovery.continuation", in: app)
            XCTAssertTrue(continuation.waitForExistence(timeout: 10))
            XCTAssertEqual(continuation.label, "https://bainluck.com/futures/301")
            print("WATCH_UI_DISCOVERIES_CONTINUATION=PASS")
        }
        let result = element("watch.discovery.result.302", in: app)
        try reveal(result, in: app)
        XCTAssertTrue(result.label.contains("Yes"), result.label)
        XCTAssertFalse(element("watch.discovery.probability.302", in: app).exists)
        capture(app, "Discoveries settled result")
        XCTAssertEqual(app.buttons["watch.discovery.close"].firstMatch.label, "Your game")
        try tap(app.buttons["watch.discovery.close"].firstMatch, in: app)
        XCTAssertTrue(element("watch.home-probability", in: app).waitForExistence(timeout: 15))
        XCTAssertTrue(element("watch.home-probability", in: app).label.contains("Giants"))

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        XCTAssertTrue(element("watch.game-state", in: app).waitForExistence(timeout: 15))
        try openDiscoveries(in: app)
        XCTAssertTrue(element("watch.discovery.saved", in: app).waitForExistence(timeout: 15))
        let savedChance = element("watch.discovery.probability.301", in: app)
        try reveal(savedChance, in: app)
        XCTAssertTrue(savedChance.label.contains("46%"))
        let savedAge = element("watch.discovery.age.301", in: app)
        try reveal(savedAge, in: app)
        XCTAssertEqual(savedAge.value as? String, originalClock, "Offline restoration must preserve producer time")
        capture(app, "Discoveries saved clock retained")
        XCTAssertEqual(app.buttons["watch.discovery.close"].firstMatch.label, "Your game")
        try tap(app.buttons["watch.discovery.close"].firstMatch, in: app)
        XCTAssertTrue(element("watch.home-probability", in: app).waitForExistence(timeout: 15))
        XCTAssertTrue(element("watch.home-probability", in: app).label.contains("64%"))
        app.terminate()
    }

    @MainActor
    func testWithoutSelectionShowsThirdQuestionWithUnknownObservationAge() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = environment(largeText: false)
        app.launch()
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        try openDiscoveries(in: app)
        XCTAssertFalse(element("watch.discovery.selected", in: app).exists)
        try assertUnselectedReturnControl(in: app, screenshot: "Readable Games return control at standard size")
        let age = element("watch.discovery.age.303", in: app)
        XCTAssertTrue(age.waitForExistence(timeout: 15))
        try reveal(age, in: app)
        XCTAssertTrue(age.label.localizedCaseInsensitiveContains("unavailable"), age.label)
        capture(app, "Third discovery has unknown observation age")
        try tap(app.buttons["watch.discovery.close"].firstMatch, in: app)
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 15))
        XCTAssertFalse(element("watch.home-probability", in: app).exists)
        print("WATCH_UI_DISCOVERIES_UNSELECTED=PASS")
        print("WATCH_UI_DISCOVERIES_RETURN_STANDARD=PASS")
        app.terminate()
    }

    @MainActor
    func testUnselectedReturnControlIsReadableAtAccessibilitySize() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = environment(largeText: true)
        app.launch()
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertTrue(heading.waitForExistence(timeout: 20))
        XCTAssertEqual(heading.value as? String, "accessibility5")
        try openDiscoveries(in: app)
        XCTAssertFalse(element("watch.discovery.selected", in: app).exists)
        try assertUnselectedReturnControl(in: app, screenshot: "Readable Games return control at accessibility5")
        app.buttons["watch.discovery.close"].firstMatch.tap()
        XCTAssertTrue(heading.waitForExistence(timeout: 15))
        XCTAssertEqual(heading.value as? String, "accessibility5")
        XCTAssertTrue(app.buttons["watch.pick.101"].exists)
        XCTAssertFalse(element("watch.home-probability", in: app).exists)
        print("WATCH_UI_DISCOVERIES_RETURN_LARGE=PASS")
    }

    @MainActor
    private func assertUnselectedReturnControl(in app: XCUIApplication, screenshot: String) throws {
        let close = app.buttons["watch.discovery.close"].firstMatch
        XCTAssertTrue(close.waitForExistence(timeout: 15))
        XCTAssertEqual(close.label, "Back to choosing a game")
        XCTAssertTrue(close.isHittable)
        XCTAssertTrue(app.frame.contains(close.frame), "The complete return control must fit on screen")
        capture(app, screenshot)
    }

    private func environment(largeText: Bool) -> [String: String] {
        ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
         "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_LARGE_TEXT": largeText ? "1" : "0"]
    }

    @MainActor private func element(_ id: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[id].firstMatch
    }

    @MainActor private func openDiscoveries(in app: XCUIApplication) throws {
        try tap(app.buttons["watch.discoveries-entry"], in: app)
        XCTAssertTrue(element("watch.discovery.list", in: app).waitForExistence(timeout: 15))
    }

    @MainActor private func tap(_ item: XCUIElement, in app: XCUIApplication) throws {
        try reveal(item, in: app)
        item.tap()
    }

    @MainActor private func reveal(_ item: XCUIElement, in app: XCUIApplication) throws {
        var previousFrame: CGRect?
        var unchangedFrames = 0
        var lastFrame = CGRect.zero
        var lastAppFrame = CGRect.zero
        var reason = "Reveal exhausted its maximum of 30 scroll attempts"
        guard item.waitForExistence(timeout: 5) else {
            try failReveal(item, in: app, reason: "Target does not exist", frame: lastFrame, appFrame: lastAppFrame)
            return
        }
        for _ in 0..<30 {
            guard item.exists else { reason = "Target disappeared while revealing"; break }
            let frame = item.frame
            let appFrame = app.frame
            lastFrame = frame
            lastAppFrame = appFrame
            guard usableFrame(frame), usableFrame(appFrame) else {
                reason = "Target or application has an empty or nonfinite frame"
                break
            }
            if item.isHittable && appFrame.contains(frame) { return }
            unchangedFrames = previousFrame == frame ? unchangedFrames + 1 : 0
            guard unchangedFrames < 3 else {
                reason = "Target frame did not move after three scroll attempts"
                break
            }
            previousFrame = frame
            let earlier = frame.minY < appFrame.minY
            // A fixed 40-point drag spent most of the journey traversing saved
            // banners and preceding cards. Move toward the viewport center,
            // capped within the content area; shorten as the target approaches.
            let displacement = abs(frame.midY - (appFrame.minY + appFrame.height * 0.55))
            let distance = min(0.55, max(0.16, displacement / appFrame.height))
            let startY = earlier ? 0.25 : 0.80
            let endY = earlier ? startY + distance : startY - distance
            print("Reveal \(item.identifier): target=\(frame), drag=\(startY)→\(endY)")
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: startY))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: endY))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.3)
        }
        try failReveal(item, in: app, reason: reason, frame: lastFrame, appFrame: lastAppFrame)
    }

    private func usableFrame(_ frame: CGRect) -> Bool {
        !frame.isEmpty && !frame.isNull && !frame.isInfinite
            && [frame.origin.x, frame.origin.y, frame.width, frame.height].allSatisfy(\.isFinite)
    }

    @MainActor private func failReveal(_ item: XCUIElement, in app: XCUIApplication,
                                      reason: String, frame: CGRect, appFrame: CGRect) throws {
        let message = "Cannot reveal \(item.identifier): \(reason); target frame=\(frame); application frame=\(appFrame)"
        print(message)
        capture(app, "Unreachable discovery control")
        let hierarchy = XCTAttachment(string: app.debugDescription)
        hierarchy.name = "Unreachable discovery control hierarchy"
        hierarchy.lifetime = .keepAlways
        add(hierarchy)
        XCTFail(message)
        throw NSError(domain: "WatchDiscoveryJourney", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: message])
    }

    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
