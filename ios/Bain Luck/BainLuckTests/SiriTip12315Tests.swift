import XCTest
@testable import Bain_Luck

/// #12315 — the Siri hint in My Stuff hides for good once closed or used.
/// (The Spotlight half went live separately as #12479, with its own tests in
/// SpotlightAbbreviations12315Tests.)
@MainActor
final class SiriTip12315Tests: XCTestCase {
    // MARK: - The Siri hint

    func testTheHintHidesOnceClosedOnceUsedAndWhileTipsAreHidden() {
        XCTAssertTrue(SiriProbabilityTipRule12315.shows(dismissed: false, used: false, option: .normal))
        XCTAssertTrue(SiriProbabilityTipRule12315.shows(dismissed: false, used: false, option: .reset))
        XCTAssertFalse(SiriProbabilityTipRule12315.shows(dismissed: true, used: false, option: .normal))
        XCTAssertFalse(SiriProbabilityTipRule12315.shows(dismissed: false, used: true, option: .normal))
        XCTAssertFalse(SiriProbabilityTipRule12315.shows(dismissed: false, used: false, option: .hidden))
    }

    func testOnlyAResetLaunchBringsTheHintBack() throws {
        let suite = "SiriTip12315Tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        SiriProbabilityTipRule12315.markUsed(defaults)
        defaults.set(true, forKey: SiriProbabilityTipRule12315.dismissedKey)
        for option in [ContextualTipLaunchOption10876.normal, .hidden] {
            XCTAssertEqual(SiriProbabilityTipRule12315.apply(option, to: defaults), option)
            XCTAssertTrue(defaults.bool(forKey: SiriProbabilityTipRule12315.usedKey), "\(option) forgot a use")
            XCTAssertTrue(defaults.bool(forKey: SiriProbabilityTipRule12315.dismissedKey), "\(option) forgot a close")
        }
        XCTAssertEqual(SiriProbabilityTipRule12315.apply(.reset, to: defaults), .reset)
        XCTAssertFalse(defaults.bool(forKey: SiriProbabilityTipRule12315.usedKey))
        XCTAssertFalse(defaults.bool(forKey: SiriProbabilityTipRule12315.dismissedKey))
    }

    /// Running either Siri probability shortcut counts as having learned it,
    /// whatever the answer. `perform()` reads the network, so the call is held
    /// by its source.
    func testSiriShortcutsMarkTheHintUsedBeforeAnswering() throws {
        let intentsSource = try String(contentsOf: Self.appDir.appendingPathComponent("Intents/BainLuckIntents10873.swift"),
                                       encoding: .utf8)
        let getProb = try XCTUnwrap(intentsSource.range(of: "struct GetProbabilityIntent10873"))
        let getProbPerform = try XCTUnwrap(intentsSource.range(of: "func perform()", range: getProb.upperBound..<intentsSource.endIndex))
        let getProbAnswer = try XCTUnwrap(intentsSource.range(of: "try await answer(now:", range: getProbPerform.upperBound..<intentsSource.endIndex))
        XCTAssertTrue(intentsSource[getProbPerform.upperBound..<getProbAnswer.lowerBound].contains("SiriProbabilityTipRule12315.markUsed()"),
                      "Get Probability no longer marks the Siri hint used")

        let teamSource = try String(contentsOf: Self.appDir.appendingPathComponent("Intents/TeamGame208B.swift"),
                                    encoding: .utf8)
        let teamIntent = try XCTUnwrap(teamSource.range(of: "struct TeamChanceIntent208B"))
        let teamPerform = try XCTUnwrap(teamSource.range(of: "func perform()", range: teamIntent.upperBound..<teamSource.endIndex))
        let teamAnswer = try XCTUnwrap(teamSource.range(of: "await answer(now:", range: teamPerform.upperBound..<teamSource.endIndex))
        XCTAssertTrue(teamSource[teamPerform.upperBound..<teamAnswer.lowerBound].contains("SiriProbabilityTipRule12315.markUsed()"),
                      "Ask About a Team no longer marks the Siri hint used")
    }

    /// #12461 — the hint must advertise a non-parameterized phrase registered in
    /// `BainLuckShortcuts10873` ("Ask Bain Luck about a game"), never the removed
    /// "Get a probability from Bain Luck" and never a parameterized shortcut whose
    /// `SiriTipView` renders raw `${team}` template syntax.
    func testTheHintUsesARegisteredNonParameterizedShortcutPhrase() throws {
        let tipSource = try String(contentsOf: Self.appDir.appendingPathComponent("Tips/SiriProbabilityTip12315.swift"),
                                   encoding: .utf8)
        XCTAssertTrue(tipSource.contains("SiriTipView(intent: GetProbabilityIntent10873()"),
                      "The Siri hint must point to GetProbabilityIntent10873 so SiriTipView renders a plain-English phrase")
        XCTAssertFalse(tipSource.contains("Get a probability from Bain Luck"),
                       "The removed phrase must not appear in the Siri hint source")

        let intentsSource = try String(contentsOf: Self.appDir.appendingPathComponent("Intents/BainLuckIntents10873.swift"),
                                       encoding: .utf8)
        let shortcuts = try XCTUnwrap(intentsSource.range(of: "struct BainLuckShortcuts10873"))
        let shortcutsBody = intentsSource[shortcuts.lowerBound...]
        XCTAssertTrue(shortcutsBody.contains("intent: GetProbabilityIntent10873()"),
                      "GetProbabilityIntent10873 must be registered in BainLuckShortcuts10873")
        XCTAssertTrue(shortcutsBody.contains("Ask \\(.applicationName) about a game"),
                      "Expected registered non-parameterized phrase in BainLuckShortcuts10873")
    }

    private static var appDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }
}
