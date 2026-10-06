import XCTest

/// Actual recovery uses the existing Refresh button, with an isolated DEBUG transport.
final class WatchDiscoverPolishTests: XCTestCase {
    @MainActor
    func testTopRefreshRecoversAndSeparatesStoriesAtStandardSize() throws {
        try recoveryJourney(largeText: false)
        print("WATCH_UI_DISCOVERIES_POLISH_STANDARD=PASS")
    }

    @MainActor
    func testTopRefreshRecoversAndSeparatesStoriesAtAccessibilitySize() throws {
        try recoveryJourney(largeText: true)
        print("WATCH_UI_DISCOVERIES_POLISH_LARGE=PASS")
    }

    @MainActor
    func testSelectedGameKeepsSummaryBeforeSeparatedStories() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = environment(largeText: false, recovery: false)
        app.launch()
        let pick = app.buttons["watch.pick.101"]
        XCTAssertTrue(pick.waitForExistence(timeout: 20))
        try tap(pick, in: app)
        XCTAssertTrue(element("watch.home-probability", in: app).waitForExistence(timeout: 15))
        try openDiscoveries(in: app)
        let refresh = app.buttons["watch.discovery.refresh"]
        XCTAssertTrue(refresh.waitForExistence(timeout: 15))
        let ready = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "enabled == true AND label == %@", "Refresh discoveries"),
            object: refresh)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        XCTAssertTrue(refresh.isHittable)
        XCTAssertTrue(app.frame.contains(refresh.frame))
        XCTAssertEqual(refresh.label, "Refresh discoveries")
        let summary = element("watch.discovery.selected", in: app)
        let question = element("watch.discovery.question.301", in: app)
        XCTAssertTrue(question.waitForExistence(timeout: 15))
        XCTAssertTrue(summary.exists)
        XCTAssertLessThan(refresh.frame.minY, summary.frame.minY)
        XCTAssertLessThan(summary.frame.minY, question.frame.minY)
        XCTAssertFalse(element("watch.discovery.card.303", in: app).exists)
        try reveal(element("watch.discovery.selected-matchup", in: app), in: app)
        capture(app, "Selected game before the story boundary")
        try reveal(question, in: app)
        capture(app, "Selected summary to first discovery separator")
        try tap(app.buttons["watch.discovery.close"], in: app)
        XCTAssertTrue(element("watch.home-probability", in: app).waitForExistence(timeout: 15))
        print("WATCH_UI_DISCOVERIES_POLISH_SELECTED=PASS")
    }

    @MainActor
    private func recoveryJourney(largeText: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = environment(largeText: largeText, recovery: true)
        app.launch()
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 20))
        if largeText {
            XCTAssertEqual(app.staticTexts["watch.picker-heading"].value as? String, "accessibility5")
        }
        try openDiscoveries(in: app)
        let error = element("watch.discovery.error", in: app)
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        XCTAssertEqual(error.label, "Offline. Try again.")
        let refresh = app.buttons["watch.discovery.refresh"]
        XCTAssertTrue(refresh.exists)
        XCTAssertEqual(refresh.label, "Refresh discoveries")
        XCTAssertTrue(refresh.isEnabled)
        XCTAssertTrue(refresh.isHittable, "Refresh must be reachable before scrolling through stories")
        XCTAssertTrue(app.frame.contains(refresh.frame), "The whole refresh control must fit")
        XCTAssertFalse(element("watch.discovery.card.301", in: app).exists)
        XCTAssertFalse(element("watch.discovery.separator.selected", in: app).exists)
        XCTAssertFalse(element("watch.discovery.separator.before.302", in: app).exists)
        if largeText {
            let heading = element("watch.discovery.heading", in: app)
            XCTAssertEqual(heading.label, "Discoveries")
            XCTAssertGreaterThanOrEqual(refresh.frame.minY, heading.frame.maxY)
        }
        capture(app, largeText ? "Top refresh and error at accessibility5" : "Top refresh and error at standard size")
        refresh.tap()
        let first = element("watch.discovery.question.301", in: app)
        XCTAssertTrue(first.waitForExistence(timeout: 15), "A real refresh tap must recover without relaunch")
        XCTAssertFalse(error.exists)
        XCTAssertLessThan(refresh.frame.minY, first.frame.minY)
        let questions = ["Will inflation fall below 3%?", "Did the mission reach orbit?",
                         "Will the central bank hold rates?"]
        let ids = [301, 302, 303]
        for (index, id) in ids.enumerated() {
            let question = element("watch.discovery.question.\(id)", in: app)
            XCTAssertEqual(question.label, questions[index])
            if index > 0 {
                XCTAssertLessThan(element("watch.discovery.question.\(ids[index - 1])", in: app).frame.minY,
                                  question.frame.minY, "Server question order must be retained")
            }
            try reveal(question, in: app)
            capture(app, "Complete discovery \(id) and preceding boundary")
            if id == 301 {
                let probability = element("watch.discovery.probability.301", in: app)
                try reveal(probability, in: app)
                XCTAssertTrue(probability.label.contains("Yes"))
                XCTAssertTrue(probability.label.contains("46%"))
            } else if id == 302 {
                let result = element("watch.discovery.result.302", in: app)
                try reveal(result, in: app)
                XCTAssertTrue(result.label.contains("Yes"))
                XCTAssertFalse(element("watch.discovery.probability.302", in: app).exists)
            } else {
                let probability = element("watch.discovery.probability.303", in: app)
                try reveal(probability, in: app)
                XCTAssertTrue(probability.label.contains("Hold"))
                XCTAssertTrue(probability.label.contains("64%"))
            }
            let age = element("watch.discovery.age.\(id)", in: app)
            try reveal(age, in: app)
            if id == 303 {
                XCTAssertTrue(age.label.localizedCaseInsensitiveContains("unavailable"))
            } else {
                XCTAssertTrue((age.value as? String ?? "").contains(
                    id == 301 ? "2026-10-05T12:00:00" : "2026-10-05T11:50:00"))
            }
            try tap(app.buttons["watch.discovery.continue.\(id)"], in: app)
            let help = app.otherElements["Continue on iPhone"].firstMatch
            XCTAssertTrue(help.waitForExistence(timeout: 10))
            XCTAssertTrue(help.staticTexts.containing(NSPredicate(
                format: "label CONTAINS %@ AND label CONTAINS %@", questions[index],
                "Look for Bain Luck’s Handoff option")).firstMatch.exists)
            try tap(app.buttons["OK"].firstMatch, in: app)
            XCTAssertEqual(element("watch.discovery.continuation", in: app).label,
                           "https://bainluck.com/futures/\(id)")
        }
        try tap(app.buttons["watch.discovery.close"], in: app)
        XCTAssertTrue(app.buttons["watch.pick.101"].waitForExistence(timeout: 15))
    }

    private func environment(largeText: Bool, recovery: Bool) -> [String: String] {
        ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
         "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_LARGE_TEXT": largeText ? "1" : "0",
         "BAINLUCK_WATCH_UI_DISCOVER_RECOVERY": recovery ? "1" : "0"]
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
        let hierarchy = XCTAttachment(string: app.debugDescription)
        hierarchy.name = name + " hierarchy"
        hierarchy.lifetime = .keepAlways
        add(hierarchy)
    }
}
