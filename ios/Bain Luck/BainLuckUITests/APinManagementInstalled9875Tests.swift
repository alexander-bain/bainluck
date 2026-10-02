import XCTest

/// Opt-in on Native's restored signed-in simulator. All pin transport/cache
/// inputs are controlled and labelled; auth remains real. No fixture control
/// calls togglePin/presentManagement for the reader. Compile/runtime is Native's.
final class APinManagementInstalled9875Tests: XCTestCase {
    private let detailID = 15319563

    private func arm() throws {
        continueAfterFailure = false
        guard ProcessInfo.processInfo.environment["BL_PIN9875_ARMED"] == "1" else {
            throw XCTSkip("NOT ARMED: Native must name the restored-session pin-only DEBUG run")
        }
    }
    private func newSuite() -> String { "bainluck.debug.9875.\(UUID())" }
    private func launch(_ suite: String, seed: Bool, offline: Bool = false) throws -> XCUIApplication {
        let app = UITestLaunch.launchApp(extra: [
            "-launch_pin_runtime_9875", suite,
            "-launch_pin_seed_9875", seed ? "YES" : "NO",
            "-launch_pin_phase_9875", offline ? "offline" : "warm"
        ])
        let signedIn = wait {
            guard let value = try? self.receipt(app) else { return false }
            return value["real_signed_in"] as? Bool == true && !(value["real_user_id"] as? String ?? "").isEmpty
        }
        XCTAssertTrue(signedIn, "HARNESS: actual restored signed-in session required; no fake auth/guest fallback")
        let failure = try receipt(app)["failure"] as? String
        XCTAssertEqual(failure, "", "HARNESS: malformed/unseeded input must fail by name")
        XCTAssertTrue(wait { (try? self.receipt(app)["load_state"] as? String) == (offline ? "failed" : "loaded") })
        return app
    }
    private func receipt(_ app: XCUIApplication) throws -> [String: Any] {
        let elements = app.descendants(matching: .any).matching(identifier: "pin9875Receipt").allElementsBoundByIndex
        let element = try XCTUnwrap(elements.last(where: { $0.exists && $0.isHittable }) ?? elements.last)
        let value = try XCTUnwrap(element.value as? String, "HARNESS: controlled receipt absent")
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(value.utf8)) as? [String: Any])
    }
    private func saved(_ app: XCUIApplication) throws -> Set<String> {
        Set(try XCTUnwrap(receipt(app)["saved"] as? [String]))
    }
    private func wait(seconds: TimeInterval = 30, _ assertion: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(seconds)
        while Date() < end {
            if assertion() { return true }
            Thread.sleep(forTimeInterval: 0.25)
        }
        return false
    }
    private func record(_ app: XCUIApplication, _ phase: String) throws {
        let data = try JSONSerialization.data(withJSONObject: receipt(app), options: [.sortedKeys])
        print("PIN9875-RECEIPT \(phase) \(String(decoding: data, as: UTF8.self))")
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = "9875-\(phase)"
        image.lifetime = .keepAlways
        add(image)
    }
    private func reachableRemove(_ app: XCUIApplication, key: String) -> XCUIElement? {
        // Run1 drew Remove controls but never exposed removePin.<key> to the
        // query. SwiftUI can give a child the row's savedPin.<key> identifier.
        // Require BOTH exact pin identity and the removal label; never choose
        // a generic Remove button by its position or fixture-title availability.
        let predicate = NSPredicate(
            format: "(identifier == %@ OR identifier == %@) AND label BEGINSWITH %@",
            "removePin.\(key)", "savedPin.\(key)", "Remove "
        )
        for step in 0..<19 {
            let candidates = app.buttons.matching(predicate).allElementsBoundByIndex
            let top = app.navigationBars["Manage pins"].frame.maxY + 8
            let controls = app.buttons.matching(identifier: "pin9875Controls").allElementsBoundByIndex
                .last(where: { $0.exists && $0.isHittable })
            let bottom = min(app.frame.maxY - 40, controls.map { $0.frame.minY - 8 } ?? app.frame.maxY - 40)
            if let found = candidates.last(where: {
                $0.exists && $0.isHittable && $0.isEnabled && $0.frame.minY > top && $0.frame.maxY < bottom
            }) {
                return found
            }
            guard step < 18 else { break }
            let frame = candidates.last(where: { $0.exists && $0.frame.width > 0 && $0.frame.height > 0 })?.frame
            // If a lazy row is absent, sweep up, down, then up (six drags each).
            // Run1's absent-selector helper only moved toward the bottom.
            let towardTop = frame.map { $0.midY < (top + bottom) / 2 } ?? (step < 6 || step >= 12)
            let upper = (top + (bottom - top) * 0.30 - app.frame.minY) / app.frame.height
            let lower = (top + (bottom - top) * 0.75 - app.frame.minY) / app.frame.height
            let a = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: towardTop ? upper : lower))
            let b = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: towardTop ? lower : upper))
            a.press(forDuration: 0.05, thenDragTo: b)
            Thread.sleep(forTimeInterval: 0.25)
        }
        let hierarchy = XCTAttachment(string: app.debugDescription)
        hierarchy.name = "9875-unreachable-remove-\(key)"
        hierarchy.lifetime = .keepAlways
        add(hierarchy)
        return nil
    }
    private func control(_ app: XCUIApplication, _ label: String) throws {
        let buttons = app.buttons.matching(identifier: "pin9875Controls").allElementsBoundByIndex
        let menu = try XCTUnwrap(buttons.last(where: { $0.isHittable }))
        menu.tap()
        let item = app.buttons[label].firstMatch
        XCTAssertTrue(item.waitForExistence(timeout: 5), "HARNESS: driver command \(label) absent")
        item.tap()
    }
    private func manage(_ app: XCUIApplication) throws {
        JourneyPrecondition.tabBar(of: app).buttons["My Stuff"].tap()
        let button = app.buttons["myStuffManagePins"]
        XCTAssertTrue(button.waitForExistence(timeout: 30))
        button.tap()
        XCTAssertTrue(app.navigationBars["Manage pins"].waitForExistence(timeout: 10))
    }
    private func remove(_ app: XCUIApplication, _ key: String) throws {
        let button = try XCTUnwrap(reachableRemove(app, key: key), "known pin \(key) must remain individually removable")
        button.tap()
    }
    private func toolbarPin(_ app: XCUIApplication, _ label: String) -> XCUIElement {
        app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", label)).firstMatch
    }

    func testHeldRemovalSurvivesColdFailedRestoreForBothTypes() throws {
        try arm()
        for key in ["event:1", "future:101"] {
            let suite = newSuite()
            var app = try launch(suite, seed: true)
            try manage(app)
            let before = try saved(app)
            XCTAssertEqual(before.count, 12, "six of each type must be shown independently")
            try control(app, "Hold next reply")
            try remove(app, key)
            XCTAssertTrue(wait { (try? self.receipt(app)["held_sync"] as? Int) == 1 })
            XCTAssertEqual(try saved(app), before, "pending removal keeps row and capacity")
            try record(app, "held-\(key)")
            app.terminate()
            app = try launch(suite, seed: false, offline: true)
            try manage(app)
            XCTAssertEqual(try receipt(app)["seed"] as? String, "retained")
            XCTAssertEqual(try saved(app), before, "cold offline restore keeps last-confirmed IDs")
            XCTAssertTrue(app.staticTexts["Couldn't refresh your saved pins. Known pins are shown below; you can still remove them."].exists)
            XCTAssertNotNil(reachableRemove(app, key: key))
            try record(app, "cold-offline-\(key)")
            try remove(app, key)
            XCTAssertTrue(wait { (try? self.saved(app))?.contains(key) == false })
            XCTAssertEqual(try saved(app), before.subtracting([key]), "cold offline removal changes only the selected pin")
            try record(app, "cold-offline-removed-\(key)")
            app.terminate()
        }
    }

    func testLateRepliesAndMetadataCannotCrossControlledPinBindings() throws {
        try arm()
        let suite = newSuite()
        var app = try launch(suite, seed: true)
        try control(app, "Hold metadata")
        try manage(app)
        XCTAssertTrue(wait { ((try? self.receipt(app)["held_metadata"] as? Int) ?? 0) > 0 })
        try control(app, "Hold next reply")
        try remove(app, "event:1")
        XCTAssertTrue(wait { (try? self.receipt(app)["held_sync"] as? Int) == 1 })
        let generationA = try receipt(app)["generation"] as? String
        try control(app, "Hold pin refresh")
        XCTAssertTrue(wait { (try? self.receipt(app)["held_load"] as? Int) == 1 })
        XCTAssertEqual(try saved(app).count, 12, "loading cannot hide last-confirmed rows")
        try control(app, "Fixture binding B")
        XCTAssertTrue(wait { (try? self.receipt(app)["fixture_slot"] as? String) == "B" })
        try control(app, "Release reply failure")
        try control(app, "Release metadata")
        try control(app, "Release pin refresh")
        try manage(app)
        let expected = Set(["event:1", "event:201", "event:202", "event:203", "event:204", "event:205"] + (301...306).map { "future:\($0)" })
        XCTAssertTrue(wait { (try? self.saved(app)) == expected })
        XCTAssertNotEqual(try receipt(app)["generation"] as? String, generationA)
        XCTAssertEqual(try receipt(app)["feedback"] as? String, "")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Fixture A")).firstMatch.exists)
        XCTAssertEqual(try receipt(app)["calls"] as? [String], ["A:event:1:remove"], "old reply cannot replay a write under B")
        try record(app, "fixture-B-after-late-A")
        app.terminate()
        app = try launch(suite, seed: false, offline: true)
        try manage(app)
        XCTAssertEqual(try saved(app), expected)
        try record(app, "fixture-B-cold")
        // These are pin-only boundaries, not identity-provider signout/login.
        try control(app, "Fixture binding guest")
        XCTAssertTrue(wait { (try? self.saved(app))?.isEmpty == true })
        XCTAssertEqual(try receipt(app)["real_signed_in"] as? Bool, true)
        try control(app, "Fixture binding unresolved")
        XCTAssertEqual(try receipt(app)["real_signed_in"] as? Bool, true)
        XCTAssertEqual(try receipt(app)["calls"] as? [String], [])
        try record(app, "controlled-unresolved-real-session-retained")
        app.terminate()
    }

    func testLimitManageFromAlreadyOpenMyStuffStackAndSheetRemovesThenAdds() throws {
        try arm()
        for setup in ["pin9875StackedDetail", "pin9875SheetDetail"] {
            let suite = newSuite()
            var app = try launch(suite, seed: true)
            JourneyPrecondition.tabBar(of: app).buttons["My Stuff"].tap()
            let button = app.buttons[setup]
            XCTAssertTrue(button.waitForExistence(timeout: 10))
            button.tap()
            let pin = toolbarPin(app, "Pin")
            XCTAssertTrue(pin.waitForExistence(timeout: 65), "read-only existing #9495 detail must load")
            try record(app, "already-open-\(setup)")
            pin.tap()
            // Production has two existing feedback surfaces: the local alert
            // when isPresented, otherwise the root management toast. Require
            // the real reachable action on whichever surface actually appears.
            var surface = "absent"
            var reachedAction: XCUIElement?
            let reached = wait(seconds: 10) {
                let alertAction = app.alerts["Pin limit reached"].buttons["Manage pins"]
                if alertAction.exists && alertAction.isHittable && alertAction.isEnabled {
                    surface = "alert"
                    reachedAction = alertAction
                    return true
                }
                let toastAction = app.buttons["pinLimitManagePins"]
                if toastAction.exists && toastAction.isHittable && toastAction.isEnabled {
                    surface = "toast"
                    reachedAction = toastAction
                    return true
                }
                return false
            }
            print("PIN9875-LIMIT-SURFACE \(setup) \(surface)")
            if !reached {
                try record(app, "limit-action-absent-\(setup)")
                let hierarchy = XCTAttachment(string: app.debugDescription)
                hierarchy.name = "9875-limit-action-absent-\(setup)"
                hierarchy.lifetime = .keepAlways
                add(hierarchy)
            }
            XCTAssertTrue(reached, "\(setup) must show an actual reachable limit Manage action")
            let action = try XCTUnwrap(reachedAction)
            action.tap()
            XCTAssertTrue(app.navigationBars["Manage pins"].waitForExistence(timeout: 10), "Manage must open actual list in one reader action")
            XCTAssertEqual(try saved(app).filter { $0.hasPrefix("event:") }.count, 6)
            XCTAssertEqual(try saved(app).filter { $0.hasPrefix("future:") }.count, 6)
            try record(app, "limit-management-\(setup)")
            try remove(app, "event:1")
            XCTAssertTrue(wait { (try? self.saved(app).contains("event:1")) == false })
            app.navigationBars["Manage pins"].buttons["Done"].tap()
            let newPin = toolbarPin(app, "Pin")
            XCTAssertTrue(newPin.waitForExistence(timeout: 10))
            newPin.tap()
            XCTAssertTrue(toolbarPin(app, "Unpin").waitForExistence(timeout: 20), "confirmed removal must permit new pin")
            XCTAssertTrue(wait { (try? self.saved(app).contains("event:\(self.detailID)")) == true })
            try record(app, "replacement-confirmed-\(setup)")
            let expected = try saved(app)
            app.terminate()
            app = try launch(suite, seed: false, offline: true)
            try manage(app)
            XCTAssertEqual(try saved(app), expected)
            XCTAssertEqual(expected.filter { $0.hasPrefix("event:") }.count, 6)
            try record(app, "replacement-cold-\(setup)")
            app.terminate()
        }
    }
}
