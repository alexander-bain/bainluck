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
                let title = app.staticTexts["watch.complication.title"]
                let detail = app.staticTexts["watch.complication.detail"]
                let observed = app.staticTexts["watch.complication.observed"]
                XCTAssertTrue(title.exists && detail.exists && observed.exists)
                let expectedTitle: String
                let expectedDetail: String
                switch scenario {
                case "live":
                    expectedTitle = "San Francisco Giants win"
                    expectedDetail = "Saved · 45% · Live"
                case "score":
                    expectedTitle = "Los Angeles Dodgers at San Francisco Giants"
                    expectedDetail = "Saved · Score 2–4 · Live"
                default:
                    expectedTitle = "San Francisco Giants won"
                    expectedDetail = "Saved · Final · 4–2"
                }
                XCTAssertEqual(title.label, expectedTitle)
                XCTAssertEqual(detail.label, expectedDetail)
                if scenario == "score" {
                    XCTAssertFalse(detail.label.contains("%"), "Score-only reading must not invent a probability")
                }
                let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
                XCTAssertEqual(observed.label, "Observed \(timestamp.formatted(date: .abbreviated, time: .shortened))")
                for element in [title, detail, observed] {
                    XCTAssertTrue(element.isHittable && app.frame.contains(element.frame) && panel.frame.contains(element.frame), "Content is outside the visible Watch frame")
                }
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
