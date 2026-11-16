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

    /// Running "Get Probability" counts as having learned it, whatever the
    /// answer. `perform()` reads the network, so the call is held by its source.
    func testGetProbabilityMarksTheHintUsedBeforeItAnswers() throws {
        let source = try String(contentsOf: Self.appDir.appendingPathComponent("Intents/BainLuckIntents10873.swift"),
                                encoding: .utf8)
        let intent = try XCTUnwrap(source.range(of: "struct GetProbabilityIntent10873"))
        let perform = try XCTUnwrap(source.range(of: "func perform()", range: intent.upperBound..<source.endIndex))
        let answer = try XCTUnwrap(source.range(of: "try await answer(now:", range: perform.upperBound..<source.endIndex))
        XCTAssertTrue(source[perform.upperBound..<answer.lowerBound].contains("SiriProbabilityTipRule12315.markUsed()"),
                      "Get Probability no longer marks the Siri hint used")
    }

    private static var appDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }
}
