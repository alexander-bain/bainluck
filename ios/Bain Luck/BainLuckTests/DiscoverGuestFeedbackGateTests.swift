import XCTest
@testable import Bain_Luck

/// #9644: run after Native hands back build/test resources. These exercise the
/// policy used at gesture commit, delayed callbacks, and preference dispatch.
@MainActor
final class DiscoverGuestFeedbackGateTests: XCTestCase {
    private typealias Gate = DiscoverGuestFeedbackGate
    private typealias Auth = Gate.AuthState

    func testUnresolvedAuthCannotBorrowTheOptimisticFeedIdentity() {
        XCTAssertEqual(Gate.authState(userId: "prior-account", isLoading: true), .resolving)
        XCTAssertEqual(Gate.authState(userId: nil, isLoading: true), .resolving)
        XCTAssertEqual(Gate.authState(userId: nil, isLoading: false), .signedOut)
        XCTAssertEqual(Gate.authState(userId: "reader", isLoading: false), .signedIn(userId: "reader"))
    }

    func testOnlyTheSameResolvedAccountCanLearn() {
        let states: [Auth] = [.resolving, .signedOut, .signedIn(userId: "a"), .signedIn(userId: "b")]
        for startedWith in states {
            for current in states {
                let expected = (startedWith == .signedIn(userId: "a") && current == .signedIn(userId: "a"))
                    || (startedWith == .signedIn(userId: "b") && current == .signedIn(userId: "b"))
                XCTAssertEqual(Gate.allowsFeedback(startedWith: startedWith, current: current), expected,
                               "feedback started as \(startedWith), ended as \(current)")
            }
        }
    }

    func testFirstGuestAttemptInvitesAndDismissalDoesNotQueueFeedback() {
        var gate = Gate()
        XCTAssertTrue(gate.requestInvitation(current: .signedOut))
        // The sheet's dismissal changes presentation only. Later swipes in the
        // same sitting stay rejected without nagging or preserving an action.
        XCTAssertFalse(gate.requestInvitation(current: .signedOut))
        XCTAssertFalse(Gate.allowsFeedback(startedWith: .signedOut, current: .signedOut))
        XCTAssertFalse(Gate.allowsFeedback(startedWith: .signedOut, current: .signedIn(userId: "reader")))
        XCTAssertTrue(Gate.allowsFeedback(startedWith: .signedIn(userId: "reader"), current: .signedIn(userId: "reader")))
    }

    func testLoadingAndSignedInDoNotConsumeTheGuestInvitation() {
        var gate = Gate()
        XCTAssertFalse(gate.requestInvitation(current: .resolving))
        XCTAssertFalse(gate.requestInvitation(current: .signedIn(userId: "reader")))
        XCTAssertFalse(gate.hasPresentedInvitation)
        XCTAssertTrue(gate.requestInvitation(current: .signedOut))
    }

    func testRejectedGestureCanSpringBackAndTheCardRemainsSwipeable() {
        let widths: [CGFloat] = [-160, 160]
        for width in widths {
            var swipe = DiscoverSwipeState()
            swipe.change(width: width, height: 4)
            XCTAssertTrue(swipe.commits(width: width))
            XCTAssertFalse(Gate.allowsFeedback(startedWith: .signedOut, current: .signedOut))
            swipe.settleAfterCommit()
            XCTAssertEqual(swipe.offset, 0)
            XCTAssertEqual(swipe.opacity, 1)
            XCTAssertFalse(swipe.axisLatched)
            swipe.change(width: width, height: 4)
            XCTAssertEqual(swipe.end(width: width), width < 0 ? .left : .right)
        }
    }

    func testScrollAndShortDragDoNotBecomeFeedbackAttempts() {
        var scroll = DiscoverSwipeState()
        scroll.change(width: 4, height: 160)
        XCTAssertFalse(scroll.commits(width: 160))
        XCTAssertEqual(scroll.end(width: 160), .none)
        var shortDrag = DiscoverSwipeState()
        shortDrag.change(width: 50, height: 4)
        XCTAssertFalse(shortDrag.commits(width: 50))
        XCTAssertEqual(shortDrag.end(width: 50), .none)
    }

    /// Deterministic actor suspension, matching the view's delayed callback and
    /// Task dispatch checks. No sleep or race-dependent test ordering.
    private func delayedFeedback(startedWith: Auth, changedTo: Auth) async -> Int {
        let parked = expectation(description: "feedback waiting for dispatch")
        var resume: CheckedContinuation<Void, Never>?
        var current = startedWith
        let feedback = Task { @MainActor in
            await withCheckedContinuation { continuation in
                resume = continuation
                parked.fulfill()
            }
            return Gate.allowsFeedback(startedWith: startedWith, current: current) ? 1 : 0
        }
        await fulfillment(of: [parked], timeout: 1)
        current = changedTo
        resume?.resume()
        return await feedback.value
    }

    func testGuestSignInBeforeDelayedDispatchNeverReplaysTheGesture() async {
        let count = await delayedFeedback(startedWith: .signedOut, changedTo: .signedIn(userId: "reader"))
        XCTAssertEqual(count, 0)
        let resolvingCount = await delayedFeedback(startedWith: .resolving, changedTo: .signedIn(userId: "reader"))
        XCTAssertEqual(resolvingCount, 0)
    }

    func testLogoutRestoreAndAccountSwitchBeforeDispatchCancelFeedback() async {
        let nextStates: [Auth] = [.signedOut, .resolving, .signedIn(userId: "other")]
        for nextState in nextStates {
            let count = await delayedFeedback(startedWith: .signedIn(userId: "reader"), changedTo: nextState)
            XCTAssertEqual(count, 0)
        }
        let count = await delayedFeedback(startedWith: .signedIn(userId: "reader"), changedTo: .signedIn(userId: "reader"))
        XCTAssertEqual(count, 1)
    }
}
