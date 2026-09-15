import XCTest
@testable import Bain_Luck

/// `LaunchRig.suppressesInteractionUpload` — the affordance that lets a
/// tap-driven rig swipe and open cards without writing "what people are doing"
/// rows into production.
///
/// Every other launch affordance is read-only with respect to production. The
/// tap paths are not: a swipe, a card open and a share each POST to
/// `/api/feed/interactions` under an anonymous `x-session-id`. Standing notice
/// 39 is explicit that our own robots are TAGGED, never minted, and a UI-test
/// target that taps twenty cards a night is a robot.
///
/// The failure mode this class of flag actually suffers is **silently inert** —
/// `-temp_screenshot_tab` was passed by a shoot script for weeks and read by no
/// Swift file. So the default arm is tested as hard as the on arm: a flag whose
/// off state is untested cannot tell "a reader's swipe still counts" from "the
/// flag does nothing in either direction".
final class ARigsTapsDoNotMintPersonalizationRowsTests: XCTestCase {

    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "ARigsTapsDoNotMintPersonalizationRowsTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    // MARK: - The reader's swipe is unchanged

    func testAReadersLaunchStillReportsItsInteractions() {
        // A real launch passes no launch arguments at all. Suppression must be
        // OFF then, or the flag has quietly deleted the downrank signal #1221
        // designed for every reader on the App Store.
        XCTAssertFalse(
            LaunchRig.suppressesInteractionUpload(defaults: defaults),
            "absent argument must mean a reader's swipe is reported as it always was"
        )
    }

    func testAnExplicitNoIsAlsoAReadersLaunch() {
        defaults.set(false, forKey: LaunchRig.suppressInteractionUploadKey)
        XCTAssertFalse(LaunchRig.suppressesInteractionUpload(defaults: defaults))
    }

    // MARK: - The rig's contract

    func testTheRigsLaunchSuppressesTheUpload() {
        defaults.set(true, forKey: LaunchRig.suppressInteractionUploadKey)
        XCTAssertTrue(LaunchRig.suppressesInteractionUpload(defaults: defaults))
    }

    func testTheKeyIsTheOneTheRigActuallyPasses() {
        // The argument name is the whole contract between the shell that
        // launches the app and the Swift that reads it, and a typo on either
        // side is invisible: the app runs, the flag is simply never true, and
        // the rig writes rows it believes it suppressed. Pinned literally, on
        // purpose — `BainLuckUITests/UITestLaunch.swift` and
        // `tools/native-uitest.sh` pass exactly this string.
        XCTAssertEqual(LaunchRig.suppressInteractionUploadKey, "launch_no_interaction_upload")
    }

    func testSimctlsStringFormOfYesIsReadAsTrue() {
        // `xcrun simctl launch <sim> <bundle> -launch_no_interaction_upload YES`
        // lands in UserDefaults as the STRING "YES", not a boolean, and
        // `bool(forKey:)` is what converts it. This is the form both callers
        // use, so it is the form that has to be tested — a test that only ever
        // sets a real `true` proves nothing about the launch line.
        defaults.set("YES", forKey: LaunchRig.suppressInteractionUploadKey)
        XCTAssertTrue(LaunchRig.suppressesInteractionUpload(defaults: defaults))
    }

    // MARK: - The suppressed answer is not the successful answer

    /// The CHOKE POINT itself, not just the predicate feeding it.
    ///
    /// Every test above is about `LaunchRig`. A flag that reads correctly and is
    /// wired nowhere is the #3157 failure exactly, so this calls the API method
    /// the four interaction call sites go through and requires that it answers
    /// without leaving the device.
    ///
    /// ⚠️ THIS TEST'S MUTANT IS DELIBERATELY NOT RUN. Deleting the guard in
    /// `recordDiscoverInteraction` would make this test issue a real POST to
    /// `/api/feed/interactions` on production — writing the personalization row
    /// the guard exists to prevent. A mutation check whose failure mode is the
    /// defect is not worth running, and the honest thing is to say so rather
    /// than quietly leave a gap in the mutant table.
    ///
    /// The belt-and-braces `XCTUnwrap`-style precondition below is the same
    /// concern: if the flag were somehow not set, this test itself would be the
    /// robot minting a row, so it refuses to make the call at all.
    func testTheApiMethodTheFourCallSitesShareHonoursTheFlag() async throws {
        let key = LaunchRig.suppressInteractionUploadKey
        let restore = UserDefaults.standard.object(forKey: key)
        defer {
            if let restore { UserDefaults.standard.set(restore, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }

        UserDefaults.standard.set(true, forKey: key)
        try XCTSkipUnless(
            LaunchRig.suppressesInteractionUpload(),
            "Refusing to call the endpoint: suppression did not take, so this test would itself POST a row to production."
        )

        let event = DiscoverInteractionEvent(
            action: "unlike",
            itemType: "event",
            itemId: "uitest-guard-does-not-post",
            category: "test",
            itemName: "guard test",
            score: nil,
            rank: nil,
            surface: "native",
            source: "swipe"
        )
        let response = try await APIClient.shared.recordDiscoverInteraction(event)
        XCTAssertEqual(
            response.status, StatusResponse.suppressedByLaunchRig.status,
            "The endpoint did not report the write as suppressed, so it may have made it."
        )
    }

    func testASuppressedWriteDoesNotAnswerLikeACompletedOne() {
        // `recordDiscoverInteraction` returns this instead of POSTing. If it
        // said "ok", a log of a rig run would be indistinguishable from a log of
        // a run that wrote to production — which is the one thing the reader of
        // that log is trying to find out.
        XCTAssertEqual(StatusResponse.suppressedByLaunchRig.status, "suppressed_by_launch_rig")
        XCTAssertNotEqual(StatusResponse.suppressedByLaunchRig.status, "ok")
    }
}
