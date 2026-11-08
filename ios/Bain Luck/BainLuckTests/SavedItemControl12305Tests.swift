import XCTest
@testable import Bain_Luck

/// #12305 — the "My game" control opens the saved item's own page while it is
/// the reader's saved item, and My Stuff, untitled, otherwise.
@MainActor
final class SavedItemControl12305Tests: XCTestCase {
    private let scope = "account.abc123abc123"
    private let game = SavedWidgetSubject10875(kind: .game, id: 14969879)
    private let market = SavedWidgetSubject10875(kind: .market, id: 512)
    private var snapshot: SavedWidgetSnapshot10875 {
        SavedWidgetSnapshot10875(scope: scope, subjects: [game, market], pinsConfirmed: true)
    }

    private func entity(_ subject: SavedWidgetSubject10875, scope: String? = nil) -> String {
        SavedWidgetSelection10875.entityID(scope: scope ?? self.scope, subject: subject)
    }

    func testASavedItemOpensItsOwnPageUnderItsOwnTitle() {
        XCTAssertEqual(SavedWidgetControlLink12305.url(entityID: entity(game), snapshot: snapshot).absoluteString,
                       "bainluck://events/14969879")
        XCTAssertEqual(SavedWidgetControlLink12305.url(entityID: entity(market), snapshot: snapshot).absoluteString,
                       "bainluck://futures/512")
        XCTAssertEqual(SavedWidgetControlLink12305.title(entityID: entity(game), chosenTitle: "Jets at Chiefs",
                                                         snapshot: snapshot), "Jets at Chiefs")
    }

    func testAChoiceThatIsNoLongerTheReadersOpensMyStuffUntitled() {
        let cases: [(String, String?, SavedWidgetSnapshot10875?)] = [
            ("removed", entity(SavedWidgetSubject10875(kind: .game, id: 99)), snapshot),
            ("another account", entity(game, scope: "account.ffffffffffff"), snapshot),
            ("unset", nil, snapshot),
            ("saved items not loaded yet", entity(game), nil),
            ("unreadable id", "not-an-id", snapshot),
        ]
        for (name, id, snap) in cases {
            XCTAssertEqual(SavedWidgetControlLink12305.url(entityID: id, snapshot: snap),
                           SavedWidgetControlLink12305.myStuff, name)
            XCTAssertEqual(SavedWidgetControlLink12305.title(entityID: id, chosenTitle: "Jets at Chiefs", snapshot: snap),
                           "My Stuff", name)
        }
    }

    /// A press hands the link to the door ContentView routes, and the door takes
    /// every link the control can carry.
    func testAPressPostsItsLinkToTheAppsIntentDoor() async throws {
        let links = [SavedWidgetControlLink12305.url(entityID: entity(game), snapshot: snapshot),
                     SavedWidgetControlLink12305.url(entityID: entity(market), snapshot: snapshot),
                     SavedWidgetControlLink12305.myStuff]
        _ = IntentRouteHandoff10873.shared.consume()
        for link in links {
            _ = try await OpenSavedItemIntent12305(link: link).perform()
            XCTAssertEqual(IntentRouteHandoff10873.shared.consume(), link)
        }
        XCTAssertTrue(OpenSavedItemIntent12305.openAppWhenRun, "The press must run in the app, where the door is read")
    }

    /// The control's links are routes the app actually takes.
    func testTheAppRoutesBothLinks() {
        let navigation = NavigationCoordinator()
        XCTAssertTrue(navigation.handleURL(SavedWidgetControlLink12305.url(entityID: entity(game), snapshot: snapshot)))
        XCTAssertEqual(navigation.selectedTab, .feed)
        let routed = expectation(description: "the game route is published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { routed.fulfill() }
        wait(for: [routed], timeout: 2)
        guard case .eventDetail(let id) = navigation.pendingRoute else {
            return XCTFail("Expected the game page route, got \(String(describing: navigation.pendingRoute))")
        }
        XCTAssertEqual(id, 14969879)
        XCTAssertTrue(navigation.handleURL(SavedWidgetControlLink12305.myStuff))
        XCTAssertEqual(navigation.selectedTab, .myStuff)
    }
}
