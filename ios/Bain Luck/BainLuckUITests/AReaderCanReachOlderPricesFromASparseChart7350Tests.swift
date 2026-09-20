import XCTest

/// #7350's INTERACTION, driven by a finger: **a reader whose chosen window holds
/// one price can press a longer range and see the history that was already on
/// their phone.**
///
/// `ASparseWindowKeepsItsRangeControls7350Tests` proves the decision — when the
/// card goes sparse, what it counts, what it says. It cannot prove the way OUT
/// works, because the way out is a chip in a `@ViewBuilder` and a refetch: a bar
/// drawn but unhittable, a chip that no longer refetches, or a longer range that
/// comes back just as empty are all invisible to a pure suite and all fully
/// user-visible. On Alex's TestFlight 1.0 (16) there was no way out at all — the
/// control bar lived inside the "there is a chart" branch.
///
/// The specimen is **59165099**, *Will federal capital gains taxes be cut in
/// 2026?*: nine observations back to August 18, exactly one inside seven days.
/// It is live data, so it can densify — a market that grows a second recent price
/// stops being sparse and this journey SKIPS naming that, which is a precondition
/// miss and never a pass.
final class AReaderCanReachOlderPricesFromASparseChart7350Tests: XCTestCase {

    private static let route = "bainluck://futures/59165099"
    private static let chartIdentifier = "evolution-chart-surface"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testTheSparseCardKeepsItsChipsAndTheLongerRangeDrawsTheChart() throws {
        let app = UITestLaunch.launchApp(extra: ["-launch_route", Self.route])
        _ = JourneyPrecondition.tabBar(of: app)

        // The card's own sentence. Its stem is fixed and everything after it is
        // counted off the response, so this matches the specimen without pinning
        // a number that live data owns.
        let counted = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS[c] %@", "earlier price"))
            .firstMatch

        let chart = app.otherElements[Self.chartIdentifier]
        let week = app.buttons["7d"]
        let widest = app.buttons[EvolutionRangeVocabularyProbe.genericWidestWindow]

        // 🪤 A SKIP MUST NAME A SUPPLY FACT, NEVER SWALLOW A REGRESSION. "No counted
        // sentence" has two causes and they are opposites: the market grew a second
        // recent price (skip — this journey has no specimen today), or the card went
        // back to hiding what it holds (RED — that is the defect). They are told
        // apart by the chart: densified markets plot.
        if !counted.waitForExistence(timeout: UITestLaunch.contentTimeout) {
            guard chart.exists else {
                return XCTFail(
                    """
                    \(Self.route) drew neither a chart nor the counted sentence. That is not \
                    a missing specimen — it is the card back in the state #7350 fixed, or worse. \
                    7d=\(week.exists) widest=\(widest.exists)
                    """
                )
            }
            throw XCTSkip(
                """
                \(Self.route) is not sparse right now: it plots at 7d, so a second price has \
                landed inside the week. A supply fact, not #7350's bug.
                """
            )
        }

        // ═══ THE SHIP ═══ the chips are ON SCREEN in the state that used to hide them.
        XCTAssertTrue(
            week.exists && widest.exists,
            """
            The sparse card drew its sentence with no range controls under it — that IS \
            #7350, and it is the state Alex photographed on build 1.0 (16). \
            Sentence: "\(counted.label)"
            """
        )
        XCTAssertTrue(
            JourneyPrecondition.isReachable(widest, in: app),
            "the widest-range chip is drawn but a finger cannot reach it at \(widest.frame)"
        )
        // 🪤 MEASURED BY MUTATION: `if let hint, false { Text(hint) }` computes the
        // line and draws nothing, and every pure test stays green — the string is
        // correct, it is just not on the phone. Only a finger can tell the
        // difference, so the assertion lives here.
        XCTAssertTrue(
            app.staticTexts["Try a longer range"].exists,
            """
            The sparse card counted eight earlier prices and then said nothing about \
            reaching them. Sentence: "\(counted.label)"
            """
        )
        XCTAssertFalse(
            chart.exists,
            "one observation is not a line; the plot must not be drawn through a single price"
        )

        // ═══ THE WAY OUT ═══
        widest.tap()

        XCTAssertTrue(
            chart.waitForExistence(timeout: UITestLaunch.contentTimeout),
            """
            Pressing the widest range from the sparse state drew no chart. The eight older \
            observations are in the route's own response (actual_hours 2160 against a 168-hour \
            request), so either the chip stopped refetching or the longer window is no longer \
            reaching them.
            """
        )
        XCTAssertFalse(
            counted.exists,
            "the sparse sentence must go away once its window has a chart in it"
        )

        // And back: the chips still work in the other direction, so the reader is
        // not one-way-doored into the widest window.
        week.tap()
        XCTAssertTrue(
            app.descendants(matching: .any)
                .matching(NSPredicate(format: "label CONTAINS[c] %@", "earlier price"))
                .firstMatch
                .waitForExistence(timeout: UITestLaunch.contentTimeout),
            "returning to 7d must return to the counted sentence, not to a stale chart"
        )
    }
}

/// The UI-test target does not link the app module, so the one string this
/// journey needs from it is restated here — and pinned against the app's own
/// constant by `ASparseWindowKeepsItsRangeControls7350Tests`, so the two cannot
/// drift apart silently.
enum EvolutionRangeVocabularyProbe {
    static let genericWidestWindow = "6M"
}
