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
                if ["score", "final"].contains(scenario) {
                    XCTAssertEqual(reading.label, try expectedNamedScoreSpeech(scenario))
                } else {
                    XCTAssertTrue(reading.label.contains(expectedTitle) && reading.label.contains(expectedDetail))
                }
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
                if ["score", "final", "away-final", "tie"].contains(scenario) {
                    XCTAssertEqual(reading.label, try expectedNamedScoreSpeech(scenario))
                } else {
                    XCTAssertTrue(reading.label.contains(expected))
                    XCTAssertEqual(reading.label.components(separatedBy: expected).count, 2,
                                   "Reading is spoken once, not duplicated on value and metadata")
                }
                XCTAssertTrue(reading.label.hasPrefix("Saved reading."))
                XCTAssertTrue(reading.label.contains("Observed "))
                if scenario == "long" {
                    XCTAssertEqual(reading.identifier, "watch.complication.rectangular.opponent",
                                   "This valid long-name fixture requires the richer canonical opponent layout")
                    XCTAssertTrue(reading.label.contains("Association Sportive de Saint-Étienne Full Canonical Name"))
                } else if scenario == "away-final" {
                    XCTAssertTrue(reading.label.contains("Los Angeles Dodgers won"))
                } else if scenario == "score" || scenario == "tie" {
                    XCTAssertTrue(reading.label.contains("Los Angeles Dodgers, score 2"))
                    XCTAssertTrue(reading.label.contains("San Francisco Giants, score " + (scenario == "tie" ? "2" : "4")))
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
    func testRectangularTypographyForecastKeepsIdentityAndMetadataInFullColor() throws {
        try checkRectangularTypographyForecast(monochrome: false)
    }

    @MainActor
    func testRectangularTypographyForecastKeepsIdentityAndMetadataWhenAccented() throws {
        try checkRectangularTypographyForecast(monochrome: true)
    }

    @MainActor
    private func checkRectangularTypographyForecast(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        // Same existing156x76 fixtures for both source comparisons. No fabricated dimensions/data.
        // The ordinary-name ship requires the named30pt candidate; compact cannot pay it.
        // The established extreme-name fixture now requires the richer canonical opponent24pt content.
        let cases = [
            ("live", "San Francisco Giants win", "watch.complication.rectangular.prominent"),
            ("long", "Association Sportive de Saint-Étienne Full Canonical Name win", "watch.complication.rectangular.opponent")
        ]
        let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
        for (scenario, expectedTitle, expectedIdentifier) in cases {
            launchRectangular(scenario, monochrome: monochrome, in: app)
            let name = "Typography forecast - " + scenario + (monochrome ? " - accented" : " - fullColor")
            captureRectangular(app, name)
            let hierarchy = XCTAttachment(string: app.debugDescription)
            hierarchy.name = name + " hierarchy"
            hierarchy.lifetime = .keepAlways
            add(hierarchy)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let reading = rectangularReading(in: app)
            XCTAssertTrue(reading.exists)
            XCTAssertEqual(reading.identifier, expectedIdentifier, "Declared comparison branch must earn its fit")
            let declaredMatchup = scenario == "long"
                ? "Club de Football Long Complete Opponent Name at Association Sportive de Saint-Étienne Full Canonical Name. " : ""
            XCTAssertEqual(reading.label, "Saved reading. " + declaredMatchup + expectedTitle + ". 45% · Live. Observed "
                + timestamp.formatted(date: .abbreviated, time: .shortened) + ". Open your game in Bain Luck.")
            XCTAssertEqual(panel.frame.width, 156, accuracy: 1)
            XCTAssertEqual(panel.frame.height, 76, accuracy: 1)
            XCTAssertGreaterThan(reading.frame.width, 0)
            XCTAssertGreaterThan(reading.frame.height, 0)
            XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.rectangular.launcher"].firstMatch.exists)
            // Original pixels must show name/compact subject,45%,Saved,Live,and complete original As of.
            // Complete AX labels cannot prove glyph visibility, color, or removal of decoration.
            app.terminate()
        }
    }

    @MainActor
    func testRectangularOpponentIdentityAndFallbacksInFullColor() throws {
        try checkRectangularOpponentIdentity(monochrome: false)
    }

    @MainActor
    func testRectangularOpponentIdentityAndFallbacksWhenAccented() throws {
        try checkRectangularOpponentIdentity(monochrome: true)
    }

    @MainActor
    private func checkRectangularOpponentIdentity(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        let home = "Association Sportive de Saint-Étienne Full Canonical Name"
        let away = "Club de Football Long Complete Opponent Name"
        let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
        // The synthetic narrow slot tests fallback honesty, not retained-reading fit.
        for (identity, requiredBranch, requiredWidth) in [
            ("provided", "watch.complication.rectangular.opponent", CGFloat(156)),
            ("missing", "watch.complication.rectangular.compact", CGFloat(156)),
            ("invalid", "watch.complication.rectangular.compact", CGFloat(156)),
            ("wide-opponent", "compact-or-launcher", CGFloat(100))
        ] {
            launchRectangular("long", monochrome: monochrome, awayIdentity: identity, in: app)
            let name = "Opponent identity - " + identity + (monochrome ? " - accented" : " - fullColor")
            captureRectangular(app, name)
            let hierarchy = XCTAttachment(string: app.debugDescription)
            hierarchy.name = name + " hierarchy"; hierarchy.lifetime = .keepAlways; add(hierarchy)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let launcher = app.descendants(matching: .any)["watch.complication.rectangular.launcher"].firstMatch
            let reading: XCUIElement
            if identity == "wide-opponent" {
                let richer = app.descendants(matching: .any)["watch.complication.rectangular.opponent"].firstMatch
                let compact = app.descendants(matching: .any)["watch.complication.rectangular.compact"].firstMatch
                XCTAssertFalse(richer.exists)
                XCTAssertFalse(app.descendants(matching: .any)["watch.complication.rectangular.prominent"].firstMatch.exists)
                XCTAssertNotEqual(compact.exists, launcher.exists, "Exactly one truthful fallback must be selected")
                reading = compact.exists ? compact : launcher
            } else {
                reading = rectangularReading(in: app)
                XCTAssertEqual(reading.identifier, requiredBranch)
                XCTAssertFalse(launcher.exists)
            }
            XCTAssertTrue(reading.exists)
            let declaredMatchup = identity == "provided" ? away + " at " + home + ". " : ""
            if identity == "wide-opponent" && reading.identifier == "watch.complication.rectangular.launcher" {
                XCTAssertEqual(reading.label, "Open your saved game in Bain Luck. " + home + " win.")
            } else {
                XCTAssertEqual(reading.label, "Saved reading. " + declaredMatchup + home + " win. 45% · Live. Observed "
                    + timestamp.formatted(date: .abbreviated, time: .shortened) + ". Open your game in Bain Luck.")
            }
            XCTAssertEqual(panel.frame.width, requiredWidth, accuracy: 1)
            XCTAssertEqual(panel.frame.height, 76, accuracy: 1)
            XCTAssertGreaterThan(reading.frame.width, 0)
            XCTAssertGreaterThan(reading.frame.height, 0)
            XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
            let syntheticLabel = app.staticTexts["watch.complication.synthetic-rectangular-slot"]
            if identity == "wide-opponent" {
                XCTAssertEqual(syntheticLabel.label, "Synthetic rectangular comparison · 100×76pt")
            } else {
                XCTAssertFalse(syntheticLabel.exists)
            }
            // Primary original-pixel review must confirm both canonical lines and all saved metadata.
            // Missing/invalid156pt readings remain strict;100pt proves only truthful fallback, not reading fit.
            app.terminate()
        }
    }

    @MainActor
    func testRectangularNamedScoreRowsFitInFullColor() throws {
        try checkRectangularNamedScoreRows(monochrome: false)
    }

    @MainActor
    func testRectangularNamedScoreRowsFitWhenAccented() throws {
        try checkRectangularNamedScoreRows(monochrome: true)
    }

    @MainActor
    private func checkRectangularNamedScoreRows(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for scenario in ["score", "final", "away-final", "tie"] {
            launchRectangular(scenario, monochrome: monochrome, in: app)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let reading = app.descendants(matching: .any)["watch.complication.rectangular.prominent"].firstMatch
            XCTAssertTrue(reading.exists, "This comparison requires the full named score rows; compact fallback cannot pay it")
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.rectangular.compact"].firstMatch.exists)
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.rectangular.launcher"].firstMatch.exists)
            XCTAssertTrue(reading.label.hasPrefix("Saved reading."))
            XCTAssertEqual(reading.label, try expectedNamedScoreSpeech(scenario))
            XCTAssertFalse(reading.label.contains("%"))
            let observed = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
            XCTAssertTrue(reading.label.contains("Observed " + observed.formatted(date: .abbreviated, time: .shortened)))
            XCTAssertTrue(reading.frame.width > 0 && reading.frame.height > 0)
            XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
            // Original pixels must independently verify each full team name next to its own score.
            captureRectangular(app, "Named score rows - " + scenario + (monochrome ? " - accented" : " - fullColor"))
            app.terminate()
        }
    }

    @MainActor
    func testSyntheticNamedScoreColumnsInFullColor() throws {
        try checkSyntheticNamedScoreColumns(monochrome: false)
    }

    @MainActor
    func testSyntheticNamedScoreColumnsWhenAccented() throws {
        try checkSyntheticNamedScoreColumns(monochrome: true)
    }

    @MainActor
    private func checkSyntheticNamedScoreColumns(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for (scenario, zeroAwayScore) in [("score", false), ("final", false),
                                         ("away-final", false), ("tie", false), ("score", true)] {
            launchRectangular(scenario, monochrome: monochrome, zeroAwayScore: zeroAwayScore,
                              syntheticNamedScores: true, in: app)
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            let reading = app.descendants(matching: .any)["watch.complication.rectangular.named-score-columns"].firstMatch
            let name = "SYNTHETIC156x120 named score columns - " + scenario
                + (zeroAwayScore ? " - literal zero" : "") + (monochrome ? " - accented" : " - fullColor")
            captureRectangular(app, name + " - NOT actual face proof")
            let hierarchy = XCTAttachment(string: app.debugDescription)
            hierarchy.name = name + " hierarchy"; hierarchy.lifetime = .keepAlways; add(hierarchy)
            XCTAssertEqual(app.staticTexts["watch.complication.synthetic-named-score-slot"].label,
                           "Synthetic named-score comparison · 156×120pt")
            XCTAssertEqual(panel.frame.width, 156, accuracy: 0.5)
            XCTAssertEqual(panel.frame.height, 120, accuracy: 0.5)
            XCTAssertTrue(reading.exists, "This labeled synthetic comparison requires complete full-name columns")
            for fallback in ["prominent", "score-columns", "compact", "launcher"] {
                XCTAssertFalse(app.descendants(matching: .any)["watch.complication.rectangular." + fallback].firstMatch.exists)
            }
            var expected = try expectedNamedScoreSpeech(scenario)
            if zeroAwayScore {
                expected = expected.replacingOccurrences(of: "Los Angeles Dodgers, score 2", with: "Los Angeles Dodgers, score 0")
            }
            XCTAssertEqual(reading.label, expected)
            XCTAssertTrue(reading.frame.width > 0 && reading.frame.height > 0)
            XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
            // Independent originals must establish name-score association and aligned score baselines.
            app.terminate()
        }
    }

    @MainActor
    func testRectangularCanonicalScoreColumnsInFullColor() throws {
        try checkRectangularCanonicalScoreColumns(monochrome: false)
    }

    @MainActor
    func testRectangularCanonicalScoreColumnsWhenAccented() throws {
        try checkRectangularCanonicalScoreColumns(monochrome: true)
    }

    @MainActor
    private func checkRectangularCanonicalScoreColumns(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for scenario in ["score", "final", "away-final", "tie"] {
            launchRectangular(scenario, monochrome: monochrome, longScoreNames: true, in: app)
            let speech = try expectedNamedScoreSpeech(scenario)
                .replacingOccurrences(of: "Los Angeles Dodgers", with: "Club de Football Long Complete Opponent Name")
                .replacingOccurrences(of: "San Francisco Giants", with: "Association Sportive de Saint-Étienne Full Canonical Name")
            try checkRequiredScoreColumns(app, expectedSpeech: speech,
                                          captureName: "Canonical score columns - " + scenario + (monochrome ? " - accented" : " - fullColor"))
            app.terminate()
        }
    }

    @MainActor
    func testRectangularCanonicalScoreColumnsPreserveLiteralZeroInFullColor() throws {
        try checkRectangularCanonicalScoreZero(monochrome: false)
    }

    @MainActor
    func testRectangularCanonicalScoreColumnsPreserveLiteralZeroWhenAccented() throws {
        try checkRectangularCanonicalScoreZero(monochrome: true)
    }

    @MainActor
    private func checkRectangularCanonicalScoreZero(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        launchRectangular("score", monochrome: monochrome, longScoreNames: true, zeroAwayScore: true, in: app)
        let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
        let speech = "Saved reading. Club de Football Long Complete Opponent Name, score 0. "
            + "Association Sportive de Saint-Étienne Full Canonical Name, score 4. Live. Observed "
            + timestamp.formatted(date: .abbreviated, time: .shortened) + ". Open your game in Bain Luck."
        try checkRequiredScoreColumns(app, expectedSpeech: speech,
                                      captureName: "Canonical score columns - literal zero" + (monochrome ? " - accented" : " - fullColor"))
    }

    @MainActor
    private func checkRequiredScoreColumns(_ app: XCUIApplication, expectedSpeech: String, captureName: String) throws {
        let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
        let reading = app.descendants(matching: .any)["watch.complication.rectangular.score-columns"].firstMatch
        captureRectangular(app, captureName)
        let hierarchy = XCTAttachment(string: app.debugDescription)
        hierarchy.name = captureName + " hierarchy"; hierarchy.lifetime = .keepAlways; add(hierarchy)
        XCTAssertTrue(reading.exists, "This comparison requires complete canonical score columns")
        for identifier in ["watch.complication.rectangular.prominent", "watch.complication.rectangular.opponent",
                           "watch.complication.rectangular.compact", "watch.complication.rectangular.launcher"] {
            XCTAssertFalse(app.descendants(matching: .any)[identifier].firstMatch.exists)
        }
        XCTAssertEqual(reading.label, expectedSpeech)
        XCTAssertFalse(reading.label.contains("%"))
        XCTAssertEqual(panel.frame.width, 156, accuracy: 1)
        XCTAssertEqual(panel.frame.height, 76, accuracy: 1)
        XCTAssertGreaterThan(reading.frame.width, 0)
        XCTAssertGreaterThan(reading.frame.height, 0)
        XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
        // Original pixels must independently verify away/home columns, actual values,
        // correct won/tie semantics, Saved/Final and the complete original timestamp.
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

    // Declared fixture expectations; never infer a branch from the rendered spoken text.
    private func expectedNamedScoreSpeech(_ scenario: String) throws -> String {
        let body: String
        switch scenario {
        case "score":
            body = "Los Angeles Dodgers, score 2. San Francisco Giants, score 4. Live."
        case "final":
            body = "Los Angeles Dodgers, score 2. San Francisco Giants won, score 4. Final."
        case "away-final":
            body = "Los Angeles Dodgers won, score 4. San Francisco Giants, score 2. Final."
        case "tie":
            body = "Los Angeles Dodgers, score 2. San Francisco Giants, score 2. Final tie."
        default:
            XCTFail("No declared named-score speech expectation for " + scenario)
            throw NSError(domain: "NamedScoreFixture", code: 1)
        }
        let observed = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
        return "Saved reading. " + body + " Observed "
            + observed.formatted(date: .abbreviated, time: .shortened) + ". Open your game in Bain Luck."
    }

    @MainActor
    private func rectangularReading(in app: XCUIApplication) -> XCUIElement {
        let namedColumns = app.descendants(matching: .any)["watch.complication.rectangular.named-score-columns"].firstMatch
        if namedColumns.exists { return namedColumns }
        let prominent = app.descendants(matching: .any)["watch.complication.rectangular.prominent"].firstMatch
        if prominent.exists { return prominent }
        let opponent = app.descendants(matching: .any)["watch.complication.rectangular.opponent"].firstMatch
        if opponent.exists { return opponent }
        let columns = app.descendants(matching: .any)["watch.complication.rectangular.score-columns"].firstMatch
        if columns.exists { return columns }
        return app.descendants(matching: .any)["watch.complication.rectangular.compact"].firstMatch
    }

    @MainActor
    private func launchRectangular(_ scenario: String, monochrome: Bool, awayIdentity: String = "provided",
                                   longScoreNames: Bool = false, zeroAwayScore: Bool = false,
                                   syntheticNamedScores: Bool = false, in app: XCUIApplication) {
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_COMPLICATION": "rectangular-\(scenario)",
            "BAINLUCK_WATCH_UI_RECTANGULAR_AWAY_IDENTITY": awayIdentity,
            "BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_NAMES": longScoreNames ? "long" : "standard",
            "BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_ZERO": zeroAwayScore ? "1" : "0",
            "BAINLUCK_WATCH_UI_NAMED_SCORE_COLUMNS_COMPARISON": syntheticNamedScores ? "1" : "0",
            "BAINLUCK_WATCH_UI_MONOCHROME": monochrome ? "1" : "0",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": monochrome ? "1" : "0"]
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["watch.complication.rendering-mode"].label,
                       monochrome ? "Rendering: accented" : "Rendering: fullColor")
        print("WATCH_UI_RECTANGULAR_RENDERING=\(monochrome ? "accented" : "fullColor") scenario=\(scenario)")
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
                if ["score", "final", "away-final", "tie"].contains(scenario) {
                    XCTAssertEqual(reading.label, try expectedNamedScoreSpeech(scenario))
                } else {
                    XCTAssertTrue(reading.label.contains("San Francisco Giants"))
                }
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
    func testSyntheticCircular64PointValuesAndIdentityFitWithoutLauncher() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for (scenario, expected) in [("live", "Saved · SF win · 45%"),
                                     ("zero", "Saved · SF win · 0%"),
                                     ("hundred", "Saved · SF win · 100%"),
                                     ("final", "Saved · SF won · Final"),
                                     ("away-final", "Saved · LA won · Final"),
                                     ("tie", "Saved · LA·SF · Final tie"),
                                     ("score", "Saved · LA·SF · Score 2–4")] {
            app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
                "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
                "BAINLUCK_WATCH_UI_COMPLICATION": "circular-" + scenario,
                "BAINLUCK_WATCH_UI_CIRCULAR_SYNTHETIC_SIZE": "64"]
            app.launch()
            XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
            XCTAssertEqual(app.staticTexts["watch.complication.synthetic-slot"].label, "Synthetic circular slot · 64pt")
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            XCTAssertEqual(panel.frame.width, 64, accuracy: 0.5)
            XCTAssertEqual(panel.frame.height, 64, accuracy: 0.5)
            let reading = app.descendants(matching: .any)["watch.complication.circular.reading"].firstMatch
            XCTAssertTrue(reading.exists, "Synthetic comparison must exercise the reading; launcher cannot pay this case")
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.circular.fallback"].firstMatch.exists)
            XCTAssertEqual(reading.value as? String, expected)
            if ["score", "final", "away-final", "tie"].contains(scenario) {
                XCTAssertEqual(reading.label, try expectedNamedScoreSpeech(scenario))
            } else {
                XCTAssertTrue(reading.label.contains("San Francisco Giants"))
            }
            let observed = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
            XCTAssertTrue(reading.label.contains("Observed " + observed.formatted(date: .abbreviated, time: .shortened)))
            XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "SYNTHETIC64 circular typography comparison - " + scenario + " - NOT actual face proof"
            capture.lifetime = .keepAlways
            add(capture)
            // Originalpixels decide visible lineorder and readability; AX alone does not.
            print("WATCH_UI_SYNTHETIC_CIRCULAR64=\(scenario),PASS")
            app.terminate()
        }
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
    func testCornerForecastFitsMeasured34PointContentSlot() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_COMPLICATION": "corner-fit"]
        app.launch()
        XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
        let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
        let reading = app.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch
        XCTAssertEqual(panel.frame.width, 34, accuracy: 0.5)
        XCTAssertEqual(panel.frame.height, 34, accuracy: 0.5)
        XCTAssertTrue(reading.exists && panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
        XCTAssertEqual(reading.value as? String, "Saved · SF win · 64%")
        XCTAssertFalse(app.descendants(matching: .any)["watch.complication.corner.fallback"].firstMatch.exists)
        let capture = XCTAttachment(screenshot: app.screenshot())
        capture.name = "Shared corner 34x34 complete forecast fit only - not curved host label"
        capture.lifetime = .keepAlways
        add(capture)
        print("WATCH_UI_CORNER_MAIN_FIT=PASS")
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
    func testCornerUnderlineKeepsCompleteValueAndIdentityInFullColor() throws {
        try checkCornerUnderline(monochrome: false)
    }

    @MainActor
    func testCornerUnderlineKeepsCompleteValueAndIdentityWhenAccented() throws {
        try checkCornerUnderline(monochrome: true)
    }

    @MainActor
    private func checkCornerUnderline(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for (scenario, value) in [("fit", "64%"), ("zero", "0%"), ("hundred", "100%")] {
            app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
                "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
                "BAINLUCK_WATCH_UI_COMPLICATION": "corner-" + scenario,
                "BAINLUCK_WATCH_UI_CORNER_INNER_SIZE": "34",
                "BAINLUCK_WATCH_UI_MONOCHROME": monochrome ? "1" : "0"]
            app.launch()
            XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
            XCTAssertEqual(app.staticTexts["watch.complication.rendering-mode"].label,
                           monochrome ? "Rendering: accented" : "Rendering: fullColor")
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            XCTAssertEqual(panel.frame.width, 34, accuracy: 0.5)
            XCTAssertEqual(panel.frame.height, 34, accuracy: 0.5)
            let reading = app.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch
            let launcher = app.descendants(matching: .any)["watch.complication.corner.fallback"].firstMatch
            if scenario == "fit" { XCTAssertTrue(reading.exists, "Existing64% complete reading must not regress to a launcher") }
            if reading.exists {
                XCTAssertFalse(launcher.exists)
                XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
                XCTAssertEqual(reading.value as? String, "Saved · SF win · " + value)
                XCTAssertTrue(reading.label.contains("Los Angeles Dodgers at San Francisco Giants"))
                XCTAssertTrue(reading.label.contains(value))
                let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
                XCTAssertTrue(reading.label.contains("Observed " + timestamp.formatted(date: .abbreviated, time: .shortened)))
            } else {
                // Complete endpoint or original honest launcher; no shrink/clipped100% earns acceptance.
                XCTAssertTrue(launcher.exists && panel.frame.contains(launcher.frame))
                XCTAssertEqual(launcher.label, "Open your selected game in Bain Luck, or choose a game")
            }
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Corner underline original34pt content - " + value + (monochrome ? " - accented" : " - fullcolor")
            capture.lifetime = .keepAlways
            add(capture)
            // Decorative fill/zero/full extent needs originalpixel review; AX is not proof.
            print("WATCH_UI_CORNER_UNDERLINE=\(scenario),accented=\(monochrome),reading=\(reading.exists),PASS")
            app.terminate()
        }
    }

    @MainActor
    func testCornerStackedPercentFitsAllEndpointsInFullColor() throws {
        try checkCornerStackedPercent(monochrome: false)
    }

    @MainActor
    func testCornerStackedPercentFitsAllEndpointsWhenAccented() throws {
        try checkCornerStackedPercent(monochrome: true)
    }

    @MainActor
    private func checkCornerStackedPercent(monochrome: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for (scenario, value) in [("zero", "0%"), ("fit", "64%"), ("hundred", "100%")] {
            app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
                "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
                "BAINLUCK_WATCH_UI_COMPLICATION": "corner-" + scenario,
                "BAINLUCK_WATCH_UI_CORNER_INNER_SIZE": "34",
                "BAINLUCK_WATCH_UI_MONOCHROME": monochrome ? "1" : "0"]
            app.launch()
            XCTAssertTrue(app.staticTexts["watch.complication.ready"].waitForExistence(timeout: 15))
            XCTAssertEqual(app.staticTexts["watch.complication.rendering-mode"].label,
                           monochrome ? "Rendering: accented" : "Rendering: fullColor")
            let panel = app.descendants(matching: .any)["watch.complication.panel"].firstMatch
            XCTAssertEqual(panel.frame.width, 34, accuracy: 0.5)
            XCTAssertEqual(panel.frame.height, 34, accuracy: 0.5)
            let reading = app.descendants(matching: .any)["watch.complication.corner.reading"].firstMatch
            XCTAssertTrue(reading.exists, "All0/64/100 must render completely; a launcher cannot pay this endpoint-fit comparison")
            XCTAssertFalse(app.descendants(matching: .any)["watch.complication.corner.fallback"].firstMatch.exists)
            XCTAssertGreaterThan(reading.frame.width, 0)
            XCTAssertGreaterThan(reading.frame.height, 0)
            XCTAssertTrue(panel.frame.contains(reading.frame) && app.frame.contains(reading.frame))
            XCTAssertEqual(reading.value as? String, "Saved · SF win · " + value)
            XCTAssertTrue(reading.label.contains("Los Angeles Dodgers at San Francisco Giants"))
            XCTAssertTrue(reading.label.contains(value))
            let timestamp = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-04T12:00:00Z"))
            XCTAssertTrue(reading.label.contains("Observed " + timestamp.formatted(date: .abbreviated, time: .shortened)))
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Stacked16pt digits and12pt percent - original34pt slot - " + value + (monochrome ? " - accented" : " - fullColor")
            capture.lifetime = .keepAlways
            add(capture)
            // Native originals prove digit/unit visibility; curved Saved/subject still needs the actual WidgetKit face.
            print("WATCH_UI_CORNER_STACKED_PERCENT=\(scenario),accented=\(monochrome),PASS")
            app.terminate()
        }
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
