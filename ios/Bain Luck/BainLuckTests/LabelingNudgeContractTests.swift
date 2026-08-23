import XCTest
import UserNotifications
@testable import Bain_Luck

/// Native's arm of `contracts/bad_reason_chips.json` (UX-P117, #2060 items 1 + 6).
///
/// ## Why the table is inlined instead of read from the JSON
///
/// Same split `RenderedPercentContractTests` uses, for the same reason. This
/// suite runs under `scripts/ios_native_gate.sh test`, which is a LOCAL gate —
/// CI does not run xcodebuild. A Swift test that read the contract at runtime
/// would be the only thing checking Swift against it, and only on the days
/// someone ran the native gate. So:
///
/// * the RUNTIME check is here, and drives the real declarations;
/// * the DRIFT check is `frontend/__tests__/lib/badReasonChipsContract.test.ts`,
///   which runs in CI and asserts the rows below still equal the contract's.
///
/// Editing this table without editing the contract turns CI red.
///
/// CONTRACT ROWS BEGIN
private let contractChips: [(tag: String, display: String)] = [
    ("stale", "Stale"),
    ("wrong_probability", "Wrong probability"),
    ("unclear", "Confusing"),
    ("duplicate", "Duplicate"),
    ("bad_image", "Bad image"),
    ("low_stakes", "Boring"),
]
private let contractCategory = "morning_digest_admin"
private let contractAction = "label_today"
/// CONTRACT ROWS END

final class LabelingNudgeContractTests: XCTestCase {

    // MARK: - The chip row (#2060 item 1)

    /// The chips the view actually draws.
    ///
    /// `DiscoverLabelingView.badReasons` is `private`, which is correct — it is
    /// view state, not API. Mirroring it here would test a copy, so instead the
    /// assertion is on the property this test can see and the source is pinned by
    /// the CI drift check, which greps the view for these literals.
    func testChipTagsAreTheStoresCanonicalSpellings() {
        // The two that would have forked the tally if the ENGLISH had been
        // stored: "Confusing" → `unclear` (16 rows) and "Boring" → `low_stakes`
        // (6 rows). Measured on production 2026-08-21.
        let byDisplay = Dictionary(
            uniqueKeysWithValues: contractChips.map { ($0.display, $0.tag) }
        )
        XCTAssertEqual(byDisplay["Confusing"], "unclear")
        XCTAssertEqual(byDisplay["Boring"], "low_stakes")
        XCTAssertEqual(byDisplay["Bad image"], "bad_image")
    }

    func testThereAreExactlySixChipsAndTheyAreDistinct() {
        XCTAssertEqual(contractChips.count, 6)
        XCTAssertEqual(Set(contractChips.map(\.tag)).count, 6)
        XCTAssertEqual(Set(contractChips.map(\.display)).count, 6)
    }

    func testStaleLeadsBecauseItIsFortyPercentOfTheCorpus() {
        XCTAssertEqual(contractChips.first?.tag, "stale")
    }

    // MARK: - The digest nudge (#2060 item 6)

    func testNotificationIdentifiersMatchTheServer() {
        XCTAssertEqual(NotificationManager.labelingCategoryId, contractCategory)
        XCTAssertEqual(NotificationManager.labelingActionId, contractAction)
    }

    // MARK: - The routing decision (mutation M14's lesson)

    /// The admin digest carries BOTH keys, and the action must win.
    ///
    /// This replaces a source grep that asserted the action check appeared above
    /// the `url` read. Mutation M14 defanged the condition without moving a line
    /// and the grep stayed green — line order is a proxy for the decision, not
    /// the decision. So the decision was extracted and is executed here.
    func testTheActionBeatsTheDigestUrl() {
        let adminDigest: [AnyHashable: Any] = [
            "url": "/futures/123",
            "labeling_url": "/admin/labeling",
            "category": contractCategory,
        ]
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: contractAction,
                userInfo: adminDigest
            ),
            .labeling
        )
    }

    /// The other direction (gotcha #43): a plain tap on the SAME payload must
    /// still open the market. A one-directional assertion cannot tell "the action
    /// is routed correctly" from "everything routes to labelling".
    func testAPlainTapOnTheSamePayloadStillOpensTheMarket() {
        let adminDigest: [AnyHashable: Any] = [
            "url": "/futures/123",
            "labeling_url": "/admin/labeling",
            "category": contractCategory,
        ]
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: adminDigest
            ),
            .url(URL(string: "/futures/123")!)
        )
    }

    func testANonAdminDigestIsUnaffected() {
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["url": "/futures/9"]
            ),
            .url(URL(string: "/futures/9")!)
        )
    }

    func testTheLegacyIdFallbacksStillWork() {
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": "77"]
            ),
            .event(id: 77)
        )
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["market_id": "88"]
            ),
            .market(id: 88)
        )
    }

    func testAPayloadNamingNowhereRoutesNowhere() {
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: [:]
            ),
            .none
        )
    }

    /// The button only exists if the category was registered, and the category is
    /// only consulted if its identifier is the one the server puts on the payload.
    /// A mismatch is silent: the push arrives, the action is absent, and nothing
    /// anywhere reports a problem.
    func testTheCategoryIsRegisteredWithTheLabelAction() async {
        // Touch the singleton so `init` runs its registration.
        _ = NotificationManager.shared
        let categories = await UNUserNotificationCenter.current().notificationCategories()
        guard let digest = categories.first(where: { $0.identifier == contractCategory }) else {
            return XCTFail("category \(contractCategory) was never registered")
        }
        XCTAssertEqual(digest.actions.map(\.identifier), [contractAction])
        XCTAssertEqual(digest.actions.first?.title, "Label today")
        // `.foreground` is what brings the app up on the labelling screen; a
        // background action would fire the handler with nowhere to navigate.
        XCTAssertTrue(digest.actions.first?.options.contains(.foreground) ?? false)
    }
}
