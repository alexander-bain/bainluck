import XCTest
@testable import Bain_Luck

/// #3141 — the launch-argument escape hatch that lets a headless rig photograph
/// the app instead of a permission dialog.
///
/// The class of defect this guards is "the rig's arguments are silently inert":
/// `tools/native-g1-shoot.sh` spent weeks passing `-temp_screenshot_tab` and
/// `-temp_screenshot_counts`, neither of which any Swift file has ever read, so
/// the rig looked like it was driving the app and was in fact doing nothing. A
/// flag with no test is indistinguishable from a flag that was never wired, so
/// the contract the rig depends on is pinned here rather than in a shell script.
final class NotificationPromptSuppressionTests: XCTestCase {

    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "NotificationPromptSuppressionTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    // MARK: - The product default is unchanged

    func testAbsentFlagStillAsks() {
        // The whole point of a test affordance is that it changes nothing for a
        // reader who never passes it. A real launch has no such key.
        XCTAssertTrue(NotificationManager.shouldRequestPermission(defaults: defaults))
    }

    func testExplicitFalseStillAsks() {
        defaults.set(false, forKey: NotificationManager.suppressPromptKey)
        XCTAssertTrue(NotificationManager.shouldRequestPermission(defaults: defaults))
    }

    // MARK: - The rig's contract

    func testFlagSuppressesTheAsk() {
        defaults.set(true, forKey: NotificationManager.suppressPromptKey)
        XCTAssertFalse(NotificationManager.shouldRequestPermission(defaults: defaults))
    }

    /// `xcrun simctl launch … -suppress_notification_prompt YES` does not write a
    /// Bool: the argument domain parses `YES` as a string, and `bool(forKey:)` is
    /// what turns it back into `true`. Asserting the string form is what makes
    /// this a test of the command the rig actually runs, rather than a test of a
    /// Bool nobody sets that way.
    func testLaunchArgumentStringFormSuppressesTheAsk() {
        for yes in ["YES", "1", "true"] {
            defaults.set(yes, forKey: NotificationManager.suppressPromptKey)
            XCTAssertFalse(
                NotificationManager.shouldRequestPermission(defaults: defaults),
                "simctl passes \(yes) as a string; it must still read as suppression"
            )
        }
    }

    /// The key is the rig's whole interface. If it is renamed, every shoot script
    /// in `tools/` silently goes back to photographing a dialog — the same
    /// failure as the inert arguments, one rename later.
    func testKeyNameIsTheOneTheShootScriptsPass() {
        XCTAssertEqual(NotificationManager.suppressPromptKey, "suppress_notification_prompt")
    }
}
