import UIKit
import XCTest

/// #12982 — Explicit, named dispositions for iPhone tests that fail at random on
/// GitHub's single-core virtualized `xcode-27` runners (Part A) or assert pre-Direction-199
/// / pre-#12639 source shapes superseded by unified components (Part B).
enum TestSuiteDisposition12982 {
    static var isGitHubHostedRunner: Bool {
        let env = ProcessInfo.processInfo.environment
        return env["GITHUB_ACTIONS"] == "true" || env["CI"] == "true"
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
            throw XCTSkip("#12982 set aside on hosted runner (\(testName)): \(reason)")
        }
        if !hasForegroundActiveWindowScene {
            throw XCTSkip("#12982 set aside without foreground-active UIWindowScene (\(testName)): \(reason)")
        }
    }

    static func skipIfHostedRunner(_ testName: String, reason: String) throws {
        if isGitHubHostedRunner {
            throw XCTSkip("#12982 set aside on hosted runner (\(testName)): \(reason)")
        }
    }

    static func skipSuperseded(_ testName: String, by replacement: String) throws {
        throw XCTSkip("#12982 superseded (\(testName)): \(replacement)")
    }
}
