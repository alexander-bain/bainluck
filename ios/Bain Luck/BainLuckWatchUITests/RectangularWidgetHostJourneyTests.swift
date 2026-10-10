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
            "BAINLUCK_WATCH_UI_SHARED_PUBLICATION": "1",
            "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY": "1"
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
        try reveal(add, in: host, belowNavigationChrome: true)
        XCTAssertEqual(modular.buttons.matching(identifier: "Add").count, 1)
        capture(host, "Named Modular Add fully below navigation chrome")
        add.tap()
        let slot = host.buttons["Middle complication"].firstMatch
        // A gallery card or its Add-to-Watch preview is not the face editor.
        let editors = host.otherElements.matching(NSPredicate(format: "identifier BEGINSWITH %@", "ActiveEditMode-"))
        let namedEditors = host.scrollViews.matching(NSPredicate(format: "label ==[c] %@", "modular"))
        let library = host.otherElements["Face Library View"].firstMatch
        let editorArrived = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            editors.count == 1 && namedEditors.count == 1 && !library.exists
        }, object: host)
        XCTAssertEqual(XCTWaiter.wait(for: [editorArrived], timeout: 15), .completed,
                       "Named Modular Add did not reach its face editor")
        capture(host, "Named Modular editor before bounded page search")
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
        let reading = host.descendants(matching: .any).matching(NSPredicate(format: "identifier IN %@", [
            "watch.complication.rectangular.prominent", "watch.complication.rectangular.compact"
        ])).firstMatch
        XCTAssertTrue(reading.waitForExistence(timeout: 20), "Actual installed WidgetKit extension must render a typed fitting reading")
        XCTAssertTrue(reading.label.contains("San Francisco Giants win"))
        XCTAssertTrue(reading.label.contains("Saved"))
        XCTAssertTrue(reading.label.contains("64% · Live"))
        XCTAssertTrue(reading.label.contains("Observed "))
        let observedParts = reading.label.components(separatedBy: "Observed ")
        XCTAssertEqual(observedParts.count, 2)
        let observedTimestamp = try XCTUnwrap(observedParts.last)
            .components(separatedBy: ". Open your game")[0]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertFalse(observedTimestamp.isEmpty, "Saved reading must retain its observation timestamp")
        XCTAssertEqual(reading.label.components(separatedBy: "64% · Live").count, 2)
        // Both XCUIElement frames are in screen coordinates.
        XCTAssertTrue(reading.frame.width > 0 && reading.frame.height > 0
                      && center.frame.contains(reading.frame) && host.frame.contains(reading.frame),
                      "Actual WidgetKit complete reading frame escapes its rectangular content bounds")
        XCTAssertFalse(host.descendants(matching: .any)["watch.complication.fallback"].firstMatch.exists)
        // Preserve the prior required receipt only after actual named saved content is verified.
        print("WATCH_RECTANGULAR_INSTALLED_TITLE=San Francisco Giants win")
        print("WATCH_RECTANGULAR_INSTALLED_DETAIL=Saved · 64% · Live")
        print("WATCH_RECTANGULAR_INSTALLED_OBSERVED=\(reading.label)")
        print("WATCH_UI_RECTANGULAR_ACTUAL_TYPED=PASS")
        capture(host, "Actual mounted rectangular saved reading")

    }

    @MainActor
    func testActualRectangularLiveScoreColumnsColdTap() throws {
        try checkActualScoreColumnsColdTap(scenario: "score", homeScore: 4, awayScore: 2, final: false)
    }

    @MainActor
    func testActualRectangularHomeWinnerColumnsColdTap() throws {
        try checkActualScoreColumnsColdTap(scenario: "final", homeScore: 4, awayScore: 2, final: true)
    }

    @MainActor
    func testActualRectangularAwayWinnerColumnsColdTap() throws {
        try checkActualScoreColumnsColdTap(scenario: "away-final", homeScore: 2, awayScore: 4, final: true)
    }

    @MainActor
    func testActualRectangularTiedColumnsColdTap() throws {
        try checkActualScoreColumnsColdTap(scenario: "tie", homeScore: 2, awayScore: 2, final: true)
    }

    @MainActor
    func testActualRectangularZeroScoreColumnsColdTap() throws {
        try checkActualScoreColumnsColdTap(scenario: "zero", homeScore: 4, awayScore: 0, final: false)
    }

    @MainActor
    private func checkActualScoreColumnsColdTap(scenario: String, homeScore: Int, awayScore: Int, final: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        let home = "Association Sportive de Saint-Étienne Full Canonical Name"
        let away = "Club de Football Long Complete Opponent Name"
        let observed = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1",
            "BAINLUCK_WATCH_UI_SHARED_PUBLICATION": "1", "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY": "1",
            "BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_HOST": scenario,
            "BAINLUCK_WATCH_UI_FIXED_OBSERVATION": "2026-10-04T12:00:00Z"
        ]
        app.launch()
        let choice = app.buttons["watch.pick.101"]
        XCTAssertTrue(choice.waitForExistence(timeout: 20))
        try reveal(choice, in: app)
        choice.tap()
        let homeRow = app.descendants(matching: .any)["watch.home-score"].firstMatch
        let awayRow = app.descendants(matching: .any)["watch.away-score"].firstMatch
        XCTAssertTrue(homeRow.waitForExistence(timeout: 20) && awayRow.exists)
        XCTAssertEqual(homeRow.label, home + ", score " + String(homeScore))
        XCTAssertEqual(awayRow.label, away + ", score " + String(awayScore))
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        let priorProcess = app.staticTexts["watch.launch-process"].label
        XCTAssertNotNil(UUID(uuidString: priorProcess))
        XCTAssertEqual(app.staticTexts["watch.launch-receipt"].label, "Launcher opens: 0")
        let host = XCUIApplication(bundleIdentifier: "com.apple.Carousel")
        let center = try mountScoreFixtureOnModular(in: host)
        let reading = host.descendants(matching: .any)["watch.complication.rectangular.score-columns"].firstMatch
        XCTAssertTrue(reading.waitForExistence(timeout: 20), "Actual mounted score-columns branch is required")
        let awayWinner = final && awayScore > homeScore ? " won" : ""
        let homeWinner = final && homeScore > awayScore ? " won" : ""
        let state = final ? (homeScore == awayScore ? "Final tie" : "Final") : "Live"
        let expected = "Saved reading. " + away + awayWinner + ", score " + String(awayScore) + ". "
            + home + homeWinner + ", score " + String(homeScore) + ". " + state + ". Observed "
            + observed.formatted(date: .abbreviated, time: .shortened) + ". Open your game in Bain Luck."
        XCTAssertEqual(reading.label, expected)
        // XCUIElement frames share screen coordinates; never subtract the center origin.
        print("WATCH_SCORE_MODULAR_FRAMES host=\(host.frame) center=\(center.frame) reading=\(reading.frame)")
        capture(host, "Actual Modular score frame evidence before bounds assertion - " + scenario)
        XCTAssertGreaterThan(reading.frame.width, 0)
        XCTAssertGreaterThan(reading.frame.height, 0)
        XCTAssertTrue(host.frame.contains(center.frame))
        XCTAssertTrue(center.frame.contains(reading.frame) && host.frame.contains(reading.frame),
                      "Score reading must fit its actual center in the same screen coordinate space")
        for id in ["watch.complication.rectangular.prominent", "watch.complication.rectangular.opponent",
                   "watch.complication.rectangular.compact", "watch.complication.rectangular.launcher"] {
            XCTAssertFalse(host.descendants(matching: .any)[id].firstMatch.exists)
        }
        print("WATCH_SCORE_MODULAR_ACTUAL_SLOT=\(center.frame.size) scenario=\(scenario)")
        // No app rendering override can name the OS face appearance. Its mode is
        // explicitly UNVERIFIED until primary inspects actual face/editor evidence.
        print("WATCH_SCORE_MODULAR_APPEARANCE=UNVERIFIED")
        capture(host, "Actual Modular score columns before cold tap - " + scenario)
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launchEnvironment["BAINLUCK_WATCH_UI_SEED_URL"] = "1"
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.url-fixture-ready"].waitForExistence(timeout: 15))
        app.terminate()
        XCTAssertEqual(app.state, .notRunning)
        XCTAssertTrue(host.wait(for: .runningForeground, timeout: 15))
        XCTAssertTrue(host.otherElements["Watch Face"].firstMatch.exists)
        XCTAssertFalse(host.otherElements["Face Library View"].firstMatch.exists)
        XCTAssertEqual(host.otherElements.matching(identifier: "center").count, 1,
                       "Exactly one active center is required immediately before the real tap")
        XCTAssertTrue(center.exists && center.isHittable && host.frame.contains(center.frame))
        XCTAssertEqual(reading.label, expected)
        capture(host, "Actual Modular center cold tap target - " + scenario)
        center.tap() // The only route delivery: real OS-host center, never openURL/activate.
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 45))
        let gameState = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(gameState.waitForExistence(timeout: 15))
        let restored = XCTNSPredicateExpectation(predicate: NSPredicate(
            format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), object: gameState)
        XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 15), .completed)
        let route = app.staticTexts["watch.launch-receipt"]
        let delivered = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Launcher opens: 1"), object: route)
        XCTAssertEqual(XCTWaiter.wait(for: [delivered], timeout: 15), .completed)
        let process = app.staticTexts["watch.launch-process"].label
        XCTAssertNotNil(UUID(uuidString: process))
        XCTAssertNotEqual(process, priorProcess)
        let receiptElement = app.descendants(matching: .any)["watch.rectangular-score.store"].firstMatch
        let receiptText = try XCTUnwrap(receiptElement.value as? String)
        let data = try XCTUnwrap(receiptText.data(using: .utf8))
        let receipt = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(receipt["process_id"] as? String, process)
        XCTAssertEqual(receipt["event_id"] as? Int, 101)
        XCTAssertEqual(receipt["home_name"] as? String, home)
        XCTAssertEqual(receipt["away_name"] as? String, away)
        XCTAssertEqual(receipt["home_score"] as? Int, homeScore)
        XCTAssertEqual(receipt["away_score"] as? Int, awayScore)
        XCTAssertEqual(receipt["score_observed_at"] as? Double, observed.timeIntervalSince1970)
        XCTAssertEqual(receipt["probability_absent"] as? Bool, true)
        XCTAssertEqual(receipt["status"] as? String, final ? "completed" : "live")
        XCTAssertEqual(homeRow.label, home + ", score " + String(homeScore))
        XCTAssertEqual(awayRow.label, away + ", score " + String(awayScore))
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        for element in [gameState, awayRow, homeRow] {
            try reveal(element, in: app)
            XCTAssertTrue(element.isHittable && app.frame.contains(element.frame))
            capture(app, "Cold Modular tap retained " + element.identifier + " - " + scenario)
        }
        let age = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Score observed ")).firstMatch
        XCTAssertTrue(age.exists)
        try reveal(age, in: app)
        XCTAssertTrue(age.isHittable && app.frame.contains(age.frame))
        capture(app, "Cold Modular tap original score age - " + scenario)
        print("WATCH_SCORE_MODULAR_COLD_STORE_RECEIPT=\(receiptText)")
        print("WATCH_SCORE_MODULAR_HOST_ROUTE_CHECKS=PASS scenario=\(scenario)")
    }

    @MainActor
    private func mountScoreFixtureOnModular(in host: XCUIApplication) throws -> XCUIElement {
        XCUIDevice.shared.press(.home)
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
        try reveal(add, in: host, belowNavigationChrome: true)
        XCTAssertEqual(modular.buttons.matching(identifier: "Add").count, 1)
        capture(host, "Named Modular Add fully below navigation chrome")
        add.tap()
        let slot = host.buttons["Middle complication"].firstMatch
        // A gallery card or its Add-to-Watch preview is not the face editor.
        let editors = host.otherElements.matching(NSPredicate(format: "identifier BEGINSWITH %@", "ActiveEditMode-"))
        let namedEditors = host.scrollViews.matching(NSPredicate(format: "label ==[c] %@", "modular"))
        let library = host.otherElements["Face Library View"].firstMatch
        let editorArrived = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            editors.count == 1 && namedEditors.count == 1 && !library.exists
        }, object: host)
        XCTAssertEqual(XCTWaiter.wait(for: [editorArrived], timeout: 15), .completed,
                       "Named Modular Add did not reach its face editor")
        capture(host, "Named Modular editor before bounded page search")
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
        let centers = host.otherElements.matching(identifier: "center")
        let center = centers.firstMatch
        XCTAssertTrue(center.waitForExistence(timeout: 15))
        XCTAssertEqual(centers.count, 1, "Exactly one active Modular center is required")
        XCTAssertTrue(center.isHittable && host.frame.contains(center.frame))
        return center
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
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, belowNavigationChrome: Bool = false) throws {
        for _ in 0..<32 {
            let chromeBottom = belowNavigationChrome ? app.navigationBars.allElementsBoundByIndex
                .filter { bar in bar.exists && bar.frame.intersects(app.frame) }
                .map { $0.frame.maxY }.max() ?? app.frame.minY : app.frame.minY
            let belowChrome = !belowNavigationChrome || element.frame.minY > chromeBottom
            if element.isHittable && app.frame.contains(element.frame) && belowChrome { return }
            if belowNavigationChrome {
                print("WATCH_MODULAR_ADD_REVEAL top=\(element.frame.minY) chromeBottom=\(chromeBottom) oldVisible=\(element.isHittable && app.frame.contains(element.frame))")
            }
            let earlier = belowNavigationChrome ? element.frame.minY <= chromeBottom : element.frame.minY < app.frame.minY
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
