import SwiftUI
import XCTest
@testable import Bain_Luck

/// #12527 — with Reduce Motion on, the common screens' animations become no
/// animation and their moving transitions become fades; with it off, nothing
/// changes.
final class ReducedMotion12527Tests: XCTestCase {

    // MARK: - The rule

    func testWithReduceMotionOffEveryAnimationIsUntouched() {
        let spring = Animation.spring(response: 0.3)
        XCTAssertEqual(ReducedMotion12527.motion(spring, reduced: false), spring)
        XCTAssertEqual(ReducedMotion12527.motion(.easeInOut(duration: 0.2), reduced: false), .easeInOut(duration: 0.2))
        let pulse = Animation.easeInOut(duration: 0.8).repeatForever(autoreverses: true)
        XCTAssertEqual(ReducedMotion12527.motion(pulse, reduced: false), pulse)
        XCTAssertNil(ReducedMotion12527.motion(nil, reduced: false), "no animation stays no animation")
    }

    func testWithReduceMotionOnNoAnimationRuns() {
        XCTAssertNil(ReducedMotion12527.motion(.spring(response: 0.3), reduced: true))
        XCTAssertNil(ReducedMotion12527.motion(.easeOut(duration: 0.6), reduced: true))
        XCTAssertNil(ReducedMotion12527.motion(.linear(duration: 1.5).repeatForever(autoreverses: false), reduced: true),
                     "a repeating shimmer stops")
        XCTAssertNil(ReducedMotion12527.motion(.default, reduced: true))
    }

    func testTheTransitionRuleIsAFadeOnlyWhenReduced() throws {
        // AnyTransition is not Equatable, so pin the rule's two arms in its source.
        let source = try Self.source("Bain Luck/Utilities/ReducedMotion12527.swift")
        XCTAssertTrue(Self.squashed(source).contains("reduced?.opacity:transition"),
                      "reduced → a fade; otherwise the transition it was given")
        XCTAssertTrue(Self.squashed(source).contains("reduced?nil:animation"))
    }

    // MARK: - The common screens go through it

    /// Discover, the game page, search, saving and the shared components they
    /// draw. A new `withAnimation`, `.animation(_:value:)` or sliding transition
    /// here has to go through the rule.
    static let commonScreens = [
        "Bain Luck/Views/DiscoverView.swift",
        "Bain Luck/Views/EventDetailView.swift",
        "Bain Luck/Views/SearchView.swift",
        "Bain Luck/Views/MyStuffView.swift",
        "Bain Luck/Views/FeedView.swift",
        "Bain Luck/Components/PlayerPropsCardView.swift",
        "Bain Luck/Components/ProbabilityBar.swift",
        "Bain Luck/Components/PinFeedbackToast.swift",
        "Bain Luck/Components/SportFilterChips.swift",
        "Bain Luck/Components/NFLCardReader9483.swift",
        "Bain Luck/Components/SkeletonView.swift",
        "Bain Luck/Components/StatusBadge.swift",
    ]

    func testNoCommonScreenAnimatesAroundTheRule() throws {
        for path in Self.commonScreens {
            let code = try Self.codeLines(path)
            for line in code {
                XCTAssertFalse(line.range(of: #"\bwithAnimation\b"#, options: .regularExpression) != nil,
                               "\(path): `withAnimation` skips Reduce Motion — use withMotion12527: \(line)")
                XCTAssertFalse(line.contains(".animation(") && line.contains("value:") && !line.contains(".animation(nil"),
                               "\(path): `.animation(_:value:)` skips Reduce Motion — use motionAnimation12527: \(line)")
                if line.contains(".transition(") && line.contains(".move(") {
                    XCTAssertTrue(line.contains("ReducedMotion12527.transition("),
                                  "\(path): a sliding transition skips Reduce Motion: \(line)")
                }
            }
        }
    }

    func testTheScreensReallyUseTheRule() throws {
        // Guards the guard: if the replacements were reverted wholesale the
        // check above would still pass on a file with no animation at all.
        var uses = 0
        for path in Self.commonScreens {
            let code = try Self.codeLines(path).joined(separator: "\n")
            uses += code.components(separatedBy: "withMotion12527").count - 1
            uses += code.components(separatedBy: "motionAnimation12527").count - 1
            uses += code.components(separatedBy: "ReducedMotion12527.transition(").count - 1
        }
        XCTAssertGreaterThanOrEqual(uses, 25, "the common screens' animations go through the rule")
    }

    func testTheLivePulseHoldsStillWhenReduced() throws {
        let badge = Self.squashed(try Self.source("Bain Luck/Components/StatusBadge.swift"))
        XCTAssertTrue(badge.contains("letpulsing=animating&&!reduceMotion"))
        XCTAssertTrue(badge.contains(".scaleEffect(pulsing?1.3:1.0)"))
        XCTAssertTrue(badge.contains(".opacity(pulsing?0.6:1.0)"))
    }

    // MARK: - Helpers

    static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }

    static func codeLines(_ relative: String) throws -> [String] {
        try source(relative).components(separatedBy: "\n")
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
    }

    static func squashed(_ text: String) -> String {
        text.filter { !$0.isWhitespace }
    }
}
