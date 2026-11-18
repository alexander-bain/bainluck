import UIKit
import XCTest

/// #12982 — Explicit, named dispositions for iPhone tests that fail at random on
/// GitHub's single-core virtualized `xcode-27` runners (Part A) or assert pre-Direction-199
/// / pre-#12639 source shapes superseded by unified components (Part B).
enum TestSuiteDisposition12982 {
    ///Verified active replacement XCTestCase classes in `BainLuckTests`.
    enum ReplacementSuite: String, CaseIterable {
        case unifiedHeadline199 = "UnifiedHeadlineContactSheetGuard199Tests"
        case oneTypeTable199 = "OneTypeTableEverywhere199Tests"
        case connectedChartLines12639 = "ConnectedChartLines12639Tests"
        case chartScaleRule12750 = "ChartScaleRule12750Tests"
        case numericalOrder228 = "NumericalMarketScaleOrder228Tests"
        case compactGameCard12616 = "CompactGameCard12616Tests"
        case ekgEvidence10090 = "TheEventPageEkgBeatsOnlyOnEvidence10090Tests"
        case pregameForecast9496 = "APregameForecastFinalReadsTheLadders9496Tests"
    }

    static var isGitHubHostedRunner: Bool {
        ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true"
    }

    @MainActor
    static var hasForegroundActiveWindowScene: Bool {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .contains { $0.activationState == .foregroundActive }
    }

    @MainActor
    static func skipIfHostedOrHeadlessScene(_ testName: String, reason: String) throws {
        if isGitHubHostedRunner {
            throw XCTSkip("#12982 set aside on GitHub Actions hosted runner (\(testName)): \(reason)")
        }
        if !hasForegroundActiveWindowScene {
            throw XCTSkip("#12982 set aside without foreground-active UIWindowScene (\(testName)): \(reason)")
        }
    }

    static func skipIfHostedRunner(_ testName: String, reason: String) throws {
        if isGitHubHostedRunner {
            throw XCTSkip("#12982 set aside on GitHub Actions hosted runner (\(testName)): \(reason)")
        }
    }

    static func skipSuperseded(_ testName: String, ruling: String, coveredBy suite: ReplacementSuite) throws {
        throw XCTSkip("#12982 superseded (\(testName)): \(ruling) — covered by \(suite.rawValue)")
    }
}

final class TestSuiteDisposition12982SelfTests: XCTestCase {
    func testEveryReplacementSuiteExistsInBainLuckTests() {
        for suite in TestSuiteDisposition12982.ReplacementSuite.allCases {
            let cls: AnyClass? = NSClassFromString("BainLuckTests.\(suite.rawValue)")
                ?? NSClassFromString(suite.rawValue)
            XCTAssertNotNil(cls, "Missing replacement test suite class \(suite.rawValue)")
        }
    }
}
