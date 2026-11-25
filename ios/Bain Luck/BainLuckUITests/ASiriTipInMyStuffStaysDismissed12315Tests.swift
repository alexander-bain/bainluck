import XCTest

/// #12315 — the Siri hint in My Stuff shows to a reader who has never seen it,
/// and once closed it stays gone across a relaunch.
///
/// The launch arguments are this target's standing ones with only the tips
/// value swapped: `reset` makes the first run a reader who has never seen the
/// hint, and `normal` relaunches the same reader with tips allowed. The first
/// run is the control for the second: without it, "no hint" could mean the
/// hint never draws at all.
final class ASiriTipInMyStuffStaysDismissed12315Tests: XCTestCase {
    private let hintID = "myStuffSiriTip12315"

    private func launchToMyStuff(tips: String) -> XCUIApplication {
        var arguments = UITestLaunch.arguments
        if let key = arguments.firstIndex(of: "-contextual_tips_10876"), key + 1 < arguments.count {
            arguments[key + 1] = tips
        }
        let app = XCUIApplication()
        app.launchArguments = arguments
        XCTContext.runActivity(named: UITestLaunch.modeActivityName) { _ in }
        app.launch()
        JourneyPrecondition.tabBar(of: app).buttons["My Stuff"].tap()
        XCTAssertTrue(app.buttons["myStuffManagePins"].waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "My Stuff never appeared")
        return app
    }

    func testTheHintShowsOnceAndStaysClosedAfterARelaunch() {
        continueAfterFailure = false
        var app = launchToMyStuff(tips: "reset")
        let hint = app.staticTexts.matching(identifier: hintID).firstMatch
        XCTAssertTrue(hint.waitForExistence(timeout: 10), "a reader who has never seen the hint does not see it")
        XCTAssertTrue(hint.label.contains("Bain Luck"), "the hint does not name the app: \(hint.label)")
        XCTAssertFalse(hint.label.contains("${"), "the hint must not expose raw parameter template syntax: \(hint.label)")
        app.buttons.matching(identifier: hintID).firstMatch.tap()
        XCTAssertTrue(hint.waitForNonExistence(timeout: 5), "closing the hint left it on screen")

        app.terminate()
        app = launchToMyStuff(tips: "normal")
        XCTAssertFalse(app.staticTexts.matching(identifier: hintID).firstMatch.waitForExistence(timeout: 5),
                       "a closed hint came back after a relaunch")
    }

    func testTappingTheTipOpensTheTipsSheetAndDoneClosesIt() {
        continueAfterFailure = false
        let app = launchToMyStuff(tips: "reset")
        let openCard = app.buttons["myStuffSiriTipOpenSheet12315"].firstMatch
        XCTAssertTrue(openCard.waitForExistence(timeout: 10), "tappable Siri tip card never appeared")
        openCard.tap()

        let tipsNav = app.navigationBars["Tips"]
        XCTAssertTrue(tipsNav.waitForExistence(timeout: 10), "tapping the Siri tip did not open the Tips sheet")
        let phrasePredicate = NSPredicate(format: "label CONTAINS[c] %@", "Ask Bain Luck if the Lakers will win")
        XCTAssertTrue(app.staticTexts.containing(phrasePredicate).firstMatch.waitForExistence(timeout: 5),
                      "Tips sheet did not display the conversational Siri phrase")

        tipsNav.buttons["Done"].tap()
        XCTAssertTrue(tipsNav.waitForNonExistence(timeout: 5), "Done did not close the Tips sheet")
        XCTAssertTrue(app.staticTexts.matching(identifier: hintID).firstMatch.exists,
                      "closing Tips should keep the tip visible until dismissed")
    }
}
