#if DEBUG
import XCTest

final class ComplicationContentJourneyTests: XCTestCase {
    @MainActor
    func testSavedLiveScoreFinalAndEmptyRectangularContent() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for scenario in ["live", "score", "final", "empty"] {
            app.launchEnvironment = [
                "BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
                "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_COMPLICATION": scenario
            ]
            app.launch()
            XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            XCTAssertTrue(panel.exists)
            if scenario == "empty" {
                let fallback = app.descendants(matching: .any)["watch.complication.fallback"].firstMatch
                XCTAssertTrue(fallback.exists)
                XCTAssertTrue(fallback.label.contains("Your game"))
                XCTAssertTrue(fallback.isHittable && app.frame.contains(fallback.frame) && panel.frame.contains(fallback.frame))
            } else {
                let reading = rectangularReading(in: app)
                XCTAssertTrue(reading.exists)
                let expectedTitle: String
                let expectedDetail: String
                switch scenario {
                case "live":
                    expectedTitle = "San Francisco Giants win"
                    expectedDetail = "45% · Live"
                case "score":
                    expectedTitle = "Los Angeles Dodgers at San Francisco Giants"
                    expectedDetail = "Score 2–4 · Live"
                default:
                    expectedTitle = "San Francisco Giants won"
                    expectedDetail = "Final · 4–2"
                }
                XCTAssertTrue(reading.label.contains(expectedTitle) && reading.label.contains(expectedDetail))
                if scenario == "score" { XCTAssertFalse(reading.label.contains("%")) }
                let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
                XCTAssertTrue(reading.label.contains("Observed \(timestamp.formatted(date: .abbreviated, time: .shortened))"))
                XCTAssertTrue(reading.isHittable && app.frame.contains(reading.frame) && panel.frame.contains(reading.frame),
                              "Complete selected rectangular reading must fit")
            }
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Shared rectangular content 156x76 - \(scenario)"
            capture.lifetime = .keepAlways
            add(capture)
            app.terminate()
        }
        print("WATCH_UI_COMPLICATION_CONTENT=PASS")
    }


    @MainActor
    func testRectangularTypedNamedValuesFitWithMonochromeRendering() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        let cases = [("live", "45% · Live"), ("low", "12% · Live"),
                     ("zero", "0% · Live"), ("hundred", "100% · Live"),
                     ("final", "Final · 4–2"), ("away-final", "Final · 4–2"),
                     ("tie", "Final · tied 2–2"), ("score", "Score 2–4 · Live"),
                     ("long", "45% · Live")]
        for monochrome in [false, true] {
            for (scenario, expected) in cases {
                launchRectangular(scenario, monochrome: monochrome, in: app)
                let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
                let reading = rectangularReading(in: app)
                XCTAssertTrue(reading.exists, "Typed valid reading must fit prominently or compactly")
                XCTAssertTrue(reading.label.contains(expected))
                XCTAssertTrue(reading.label.hasPrefix("Saved reading."))
                XCTAssertEqual(reading.label.components(separatedBy: expected).count, 2,
                               "Reading is spoken once, not duplicated on value and metadata")
                XCTAssertTrue(reading.label.contains("Observed "))
                if scenario == "long" {
                    XCTAssertEqual(reading.identifier, "watch.complication.rectangular.compact",
                                   "Long full names must select the honest canonical compact layout")
                    XCTAssertTrue(reading.label.contains("Association Sportive de Saint-Étienne Full Canonical Name"))
                } else if scenario == "away-final" {
                    XCTAssertTrue(reading.label.contains("Los Angeles Dodgers won"))
                } else if scenario == "score" || scenario == "tie" {
                    XCTAssertTrue(reading.label.contains("Los Angeles Dodgers at San Francisco Giants"))
                    XCTAssertFalse(reading.label.contains("%"))
                } else {
                    XCTAssertTrue(reading.label.contains("San Francisco Giants"))
                }
                XCTAssertTrue(reading.frame.width > 0 && reading.frame.height > 0)
                XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
                XCTAssertFalse(app.descendants(matching: .any)["watch.complication.rectangular.launcher"].firstMatch.exists)
                captureRectangular(app, "Typed rectangular \(scenario) · \(monochrome ? "monochrome accessibility5" : "standard")")
                app.terminate()
            }
        }
        print("WATCH_UI_RECTANGULAR_TYPED=PASS")
        print("WATCH_UI_RECTANGULAR_MONOCHROME=PASS")
    }

    @MainActor
    func testRectangularLegacyMismatchUnknownAndEmptyStayHonest() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for scenario in ["old", "mismatch", "unknown", "invalid", "empty"] {
            launchRectangular(scenario, monochrome: false, in: app)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            XCTAssertFalse(rectangularReading(in: app).exists)
            if ["old", "mismatch"].contains(scenario) {
                let title = app.staticTexts["watch.complication.title"]
                let detail = app.staticTexts["watch.complication.detail"]
                let observed = app.staticTexts["watch.complication.observed"]
                XCTAssertEqual(title.label, "San Francisco Giants win")
                XCTAssertEqual(detail.label, "Saved · 45% · Live")
                let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
                XCTAssertEqual(observed.label, "Observed \(timestamp.formatted(date: .abbreviated, time: .shortened))")
                for element in [title, detail, observed] {
                    XCTAssertTrue(element.exists && panel.frame.contains(element.frame) && app.frame.contains(element.frame))
                }
            } else {
                let fallback = app.descendants(matching: .any)["watch.complication.fallback"].firstMatch
                XCTAssertTrue(fallback.exists && fallback.label.contains("Your game"))
                XCTAssertTrue(panel.frame.contains(fallback.frame) && app.frame.contains(fallback.frame))
            }
            captureRectangular(app, "Honest rectangular \(scenario)")
            app.terminate()
        }
        print("WATCH_UI_RECTANGULAR_LEGACY=PASS")
    }

    @MainActor
    private func rectangularReading(in app: XCUIApplication) -> XCUIElement {
        let prominent = app.descendants(matching: .any)["watch.complication.rectangular.prominent"].firstMatch
        if prominent.exists { return prominent }
        return app.descendants(matching: .any)["watch.complication.rectangular.compact"].firstMatch
    }

    @MainActor
    private func launchRectangular(_ scenario: String, monochrome: Bool, in app: XCUIApplication) {
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_COMPLICATION": "rectangular-\(scenario)",
            "BAINLUCK_WATCH_UI_MONOCHROME": monochrome ? "1" : "0",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": monochrome ? "1" : "0"]
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
    }

    @MainActor
    private func captureRectangular(_ app: XCUIApplication, _ name: String) {
        let capture = XCTAttachment(screenshot: app.screenshot())
        capture.name = name; capture.lifetime = .keepAlways; add(capture)
    }

    @MainActor
    func testSavedCircularNamedProbabilityFinalAndScoreLayout() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for (scenario, expected) in [("live", "Saved · SF win · 45%"),
                                     ("draw", "Saved · SF win · 46%"),
                                     ("final", "Saved · SF won · Final"),
                                     ("away-final", "Saved · LA won · Final"),
                                     ("tie", "Saved · LA·SF · Final tie"),
                                     ("score", "Saved · LA·SF · Score 2–4")] {
            try launchCircular(scenario, in: app)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let reading = app.descendants(matching: .any)["watch.complication.circular.reading"].firstMatch
            let fallback = app.descendants(matching: .any)["watch.complication.circular.fallback"].firstMatch
            if fallback.exists {
                XCTAssertFalse(reading.exists, "A complete reading that cannot fit the actual circle stays an honest launcher")
            } else {
                XCTAssertTrue(reading.exists, "The supported named probability/final must fit")
                XCTAssertEqual(reading.value as? String, expected)
                XCTAssertTrue(reading.label.contains("San Francisco Giants"))
                let observed = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
                XCTAssertTrue(reading.label.contains("Observed \(observed.formatted(date: .abbreviated, time: .shortened))"))
                XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
                XCTAssertFalse(fallback.exists)
            }
            captureCircular(app, scenario: scenario)
            app.terminate()
        }
        print("WATCH_UI_CIRCULAR_CONTENT=PASS")
    }

    @MainActor
    func testCircularOldUnknownAndNonfittingReadingsStayLaunchers() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for scenario in ["old", "invalid", "long", "empty"] {
            try launchCircular(scenario, in: app)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let fallback = app.descendants(matching: .any)["watch.complication.circular.fallback"].firstMatch
            XCTAssertTrue(fallback.exists)
            XCTAssertEqual(fallback.label, "Open your selected game in Bain Luck, or choose a game")
            XCTAssertTrue(panel.frame.contains(fallback.frame) && app.frame.contains(fallback.frame))
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.circular.reading"].firstMatch.exists)
            captureCircular(app, scenario: scenario)
            app.terminate()
        }
        print("WATCH_UI_CIRCULAR_FALLBACK=PASS")
    }

    @MainActor
    func testCornerUnsupportedReadingsStayLaunchers() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for cornerScenario in ["no-label", "old", "invalid", "long", "final", "score", "empty"] {
            app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
                "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
                "BAINLUCK_WATCH_UI_COMPLICATION": "corner-\(cornerScenario)"]
            app.launch()
            XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let fallback = app.descendants(matching: .any)["watch.complication.corner.fallback"].firstMatch
            XCTAssertTrue(fallback.exists && app.frame.contains(fallback.frame) && panel.frame.contains(fallback.frame))
            XCTAssertEqual(fallback.label, "Open your selected game in Bain Luck, or choose a game")
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch.exists)
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Shared corner fallback - \(cornerScenario)"
            capture.lifetime = .keepAlways
            add(capture)
            app.terminate()
        }
        print("WATCH_UI_CORNER_FALLBACK=PASS")
    }

    @MainActor
    private func launchCircular(_ scenario: String, in app: XCUIApplication) throws {
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_COMPLICATION": "circular-\(scenario)"]
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
    }

    @MainActor
    private func captureCircular(_ app: XCUIApplication, scenario: String) {
        let capture = XCTAttachment(screenshot: app.screenshot())
        capture.name = "Shared circular content 40x40 - \(scenario)"
        capture.lifetime = .keepAlways
        add(capture)
    }

}
#endif
