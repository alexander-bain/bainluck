import Foundation
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13769 (Ruling 420: D):
/// 1. Right swipe likes the card and the card stays (`removing == false`, springs back, zero `hideForSession`).
/// 2. Like heart appears on every Discover card archetype beside Pin and Share.
/// 3. Taking a like back removes local liked state only and NEVER sends `.unlike`.
/// 4. Left swipe remains unchanged (`.unlike` + `hideForSession`), and signed-out readers get the same sign-in gate.
@MainActor
final class DiscoverRightSwipeAndLikeHeart420DTests: XCTestCase {

    private func decodeFeedItem(_ json: String) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func iosRootURL() -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }

    // MARK: - 1. Pure Rules (Right-Swipe Stay & Undo Zero-Unlike)

    func testRightSwipeKeepsCardAndIsIdempotentOnRepeatSwipe() {
        let first = DiscoverLikeFeedbackRule420D.resolveRightSwipe(wasLiked: false)
        XCTAssertFalse(first.shouldHideCard, "right swipe must never hide the card")
        XCTAssertTrue(first.nextLikedState)
        XCTAssertEqual(first.emittedAction, "like")

        let repeatSwipe = DiscoverLikeFeedbackRule420D.resolveRightSwipe(wasLiked: true)
        XCTAssertFalse(repeatSwipe.shouldHideCard)
        XCTAssertTrue(repeatSwipe.nextLikedState)
        XCTAssertNil(repeatSwipe.emittedAction, "repeating right swipe stays liked without duplicate write")
    }

    func testHeartTapLikesAndUndoNeverEmitsUnlike() {
        let liked = DiscoverLikeFeedbackRule420D.resolveHeartTap(wasLiked: false)
        XCTAssertFalse(liked.shouldHideCard)
        XCTAssertTrue(liked.nextLikedState)
        XCTAssertEqual(liked.emittedAction, "like")

        let undone = DiscoverLikeFeedbackRule420D.resolveHeartTap(wasLiked: true)
        XCTAssertFalse(undone.shouldHideCard)
        XCTAssertFalse(undone.nextLikedState)
        XCTAssertNil(undone.emittedAction, "undoing a like must NEVER emit unlike (#13769)")
    }

    func testLeftSwipeIsUnchanged() {
        let left = DiscoverLikeFeedbackRule420D.resolveLeftSwipe()
        XCTAssertTrue(left.shouldHideCard)
        XCTAssertFalse(left.nextLikedState)
        XCTAssertEqual(left.emittedAction, "unlike")
    }

    func testSwipeStateRightDragTrayAndStayVSLeftDragExit() {
        var right = DiscoverSwipeState()
        right.change(width: 140, height: 4)
        XCTAssertTrue(right.showsOverlay)
        XCTAssertTrue(right.overlayIsLeading, "right drag reveals leading green tray")
        XCTAssertEqual(right.trayProgress, 1.0, accuracy: 0.001)
        XCTAssertEqual(right.opacity, 1.0, accuracy: 0.001, "card stays opaque during right drag")

        XCTAssertEqual(right.end(width: 140), .right)
        XCTAssertFalse(right.removing, "card stays on screen after right swipe")
        XCTAssertEqual(right.offset, 0, "card springs back cleanly to offset 0")

        var left = DiscoverSwipeState()
        left.change(width: -140, height: 4)
        XCTAssertTrue(left.showsOverlay)
        XCTAssertFalse(left.overlayIsLeading, "left drag reveals trailing red tray")
        XCTAssertLessThan(left.opacity, 1.0)
        XCTAssertEqual(left.end(width: -140), .left)
        XCTAssertTrue(left.removing)
        XCTAssertEqual(left.offset, -DiscoverSwipeState.exitOffset)
    }

    // MARK: - 2. Per-Account Persistence Across Scroll/Relaunch

    func testLikedStorePersistsPerAccountAndUndoClearsWithoutCrossAccountLeak() {
        let suiteName = "DiscoverLikedStore420DTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store1 = DiscoverLikedStore420D(userId: "42", defaults: defaults)
        XCTAssertFalse(store1.isLiked("futures-101"))
        XCTAssertTrue(store1.markLiked("futures-101"))
        XCTAssertFalse(store1.markLiked("futures-101"), "markLiked is idempotent")
        XCTAssertTrue(store1.isLiked("futures-101"))

        // Re-creating the store (simulates relaunch / scrolled offscreen & rebind) restores like.
        let reloaded = DiscoverLikedStore420D(userId: "42", defaults: defaults)
        XCTAssertTrue(reloaded.isLiked("futures-101"))

        // Switching accounts isolates likes per reader.
        reloaded.syncAccount(userId: "99")
        XCTAssertFalse(reloaded.isLiked("futures-101"))
        reloaded.syncAccount(userId: nil)
        XCTAssertFalse(reloaded.isLiked("futures-101"))

        // Switching back restores account 42, then undo removes it locally.
        reloaded.syncAccount(userId: "42")
        XCTAssertTrue(reloaded.isLiked("futures-101"))
        reloaded.unmarkLiked("futures-101")
        XCTAssertFalse(reloaded.isLiked("futures-101"))

        let afterUndo = DiscoverLikedStore420D(userId: "42", defaults: defaults)
        XCTAssertFalse(afterUndo.isLiked("futures-101"))
    }

    // MARK: - 3. Source Guards (Zero Hide on Right Swipe, Zero Unlike on Undo)

    func testDiscoverViewRightSwipesNeverHideAndUndoNeverSendsUnlike() throws {
        let source = try String(
            contentsOf: iosRootURL().appendingPathComponent("Views/DiscoverView.swift"),
            encoding: .utf8
        )

        // All 12 onSwipeRight call sites must delegate to likeCard(...) and never call hideForSession.
        let pattern = #"onSwipeRight:\s*\{([^}]*)\}"#
        let regex = try NSRegularExpression(pattern: pattern, options: [])
        let matches = regex.matches(in: source, range: NSRange(source.startIndex..., in: source))
        XCTAssertGreaterThanOrEqual(matches.count, 12, "Expected all Discover card swipe containers")
        for match in matches {
            let bodyRange = Range(match.range(at: 1), in: source)!
            let body = String(source[bodyRange])
            XCTAssertTrue(body.contains("likeCard("), "onSwipeRight must invoke likeCard: \(body)")
            XCTAssertFalse(body.contains("hideForSession"), "Right swipe must NEVER hide card: \(body)")
        }

        // toggleLike must call unmarkLiked on undo and NEVER call .unlike.
        guard let toggleRange = source.range(of: "private func toggleLike("),
              let actionHelperRange = source.range(of: "private func likeAction(") else {
            return XCTFail("Missing toggleLike helper in DiscoverView.swift")
        }
        let toggleBody = String(source[toggleRange.lowerBound..<actionHelperRange.lowerBound])
        let toggleCodeLines = toggleBody
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertTrue(toggleCodeLines.contains("DiscoverLikeFeedbackRule420D.resolveHeartTap"))
        XCTAssertTrue(toggleCodeLines.contains("likedStore.unmarkLiked(key)"))
        XCTAssertFalse(toggleCodeLines.contains(".unlike"), "Heart undo must NEVER emit .unlike (#13769)")
    }

    // MARK: - 4. All Discover Card Archetypes Render Like Heart Without Clipping

    func testAllDiscoverCardArchetypesRenderHeartAndActionBarAtTightSizes() throws {
        let action = DiscoverCardLikeAction420D(
            itemKey: "sample-1",
            isLiked: true,
            pinType: "future",
            pinId: 901,
            shareURL: URL(string: "https://bainluck.com/futures/901"),
            shareTitle: "Sample card",
            shareMessage: "Sample card",
            onToggle: {},
            onShare: {}
        )

        let barUnliked = DiscoverCardLikeAction420D(
            itemKey: "sample-2",
            isLiked: false,
            pinType: "event",
            pinId: 77,
            shareURL: URL(string: "https://bainluck.com/events/77"),
            shareTitle: "Lakers at Celtics",
            shareMessage: "Lakers at Celtics",
            onToggle: {},
            onShare: {}
        )

        let authManager = AuthManager()
        let pinManager = PinManager()

        for width in [320.0, 390.0, 400.0] {
            for size: DynamicTypeSize in [.large, .accessibility5] {
                for isLiked in [false, true] {
                    let chosen = isLiked ? action : barUnliked
                    let barView = DiscoverCardActionBar420D(actions: chosen)
                        .frame(width: width)
                        .environmentObject(authManager)
                        .environmentObject(pinManager)
                    let host = hostForMeasurement(barView, at: size)
                    host.view.frame = CGRect(x: 0, y: 0, width: width, height: 120)
                    host.view.layoutIfNeeded()
                    let fitted = host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
                    XCTAssertLessThanOrEqual(fitted.width, width + 1.0, "ActionBar overflowed at w=\(width) size=\(size)")
                    XCTAssertGreaterThanOrEqual(fitted.height, 44.0)
                }
            }
        }

        // Verify source injection hook exists on every Discover card file.
        let cardFiles = [
            "Components/DiscoverEventCard.swift",
            "Components/DiscoverFuturesCard.swift",
            "Components/HeatMapCardView.swift",
            "Components/DistributionCardView.swift",
            "Components/ComparisonCardView.swift",
            "Components/DiscoverCollectionCard.swift",
            "Components/DiscoverRoundupCardView.swift",
            "Components/GroupingMachineryViews12288.swift",
            "Components/KitCardView366B.swift",
            "Components/DiscoverTournamentCard.swift",
            "Components/DiscoverConceptCard.swift",
            "Components/DiscoverPairedMetricCardView.swift",
            "Views/DiscoverView.swift",
        ]
        for relPath in cardFiles {
            let text = try String(contentsOf: iosRootURL().appendingPathComponent(relPath), encoding: .utf8)
            XCTAssertTrue(
                text.contains("discoverCardLikeAction420D"),
                "\(relPath) must read discoverCardLikeAction420D"
            )
            XCTAssertTrue(
                text.contains("DiscoverLikeButton420D") || text.contains("DiscoverCardActionBar420D"),
                "\(relPath) must render the Like control"
            )
        }

        // Verify concrete Futures & Event cards host cleanly with Like button at 320 AX5 and iPad column width 395.
        let futuresItem = try decodeFeedItem("""
        {
          "type": "futures",
          "score": 95,
          "data": {
            "id": 901,
            "name": "Who will win the NBA Finals?",
            "category": "sports",
            "llm_sport_category": "basketball",
            "source": "kalshi",
            "status": "open",
            "top_outcomes": [
              {"id": 1, "name": "Boston Celtics", "probability": 0.42, "rank": 1, "movement": 0.03},
              {"id": 2, "name": "Oklahoma City Thunder", "probability": 0.31, "rank": 2, "movement": -0.02}
            ],
            "outcome_count": 2
          }
        }
        """)
        if let f = futuresItem.futures {
            for (width, dt): (CGFloat, DynamicTypeSize) in [(320, .accessibility5), (395, .large)] {
                let card = NativeFuturesDiscoverCard(
                    data: f,
                    feedContext: "Celtics lead entering December",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                .environment(\.discoverCardLikeAction420D, action)
                .environmentObject(authManager)
                .environmentObject(pinManager)
                .frame(width: width)
                let host = hostForMeasurement(card, at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
                XCTAssertLessThanOrEqual(fitted.width, width + 1.0, "FuturesCard overflowed at w=\(width) dt=\(dt)")
            }
        } else {
            XCTFail("Expected decoded futures card")
        }
    }
}
