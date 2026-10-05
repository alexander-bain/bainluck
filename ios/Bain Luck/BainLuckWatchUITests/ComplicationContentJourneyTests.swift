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
}
#endif
