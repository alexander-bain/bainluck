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

    /// The ↻ sits in the widget's bottom-trailing corner. A medium widget for a
    /// finished game has no caption line, so its last row ("35 Won") was the
    /// bottom line and the ↻ was drawn over "Won" (simulator, Jets at Chiefs,
    /// Nov 9). Every bottom line keeps clear of it: the small widget's caption
    /// always, the medium's caption when it has one, otherwise its rows.
    func testNoBottomLineRunsUnderTheRefreshButton() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("BainLuckWidget/SavedItemWidget10875.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        func body(_ start: String, _ end: String) throws -> String {
            let from = try XCTUnwrap(source.range(of: start), start)
            let to = try XCTUnwrap(source.range(of: end, range: from.upperBound..<source.endIndex), end)
            return String(source[from.upperBound..<to.lowerBound])
        }
        let small = try body("struct SavedSmall10875: View {", "struct SavedMedium10875: View {")
        XCTAssertTrue(small.contains(".padding(.trailing, entry.isRefreshable12305 ? 24 : 0)"),
                      "the small widget's caption no longer keeps clear of the ↻")
        let medium = try body("struct SavedMedium10875: View {", "#if os(iOS)")
        XCTAssertTrue(medium.contains("let clearsRefresh = caption == nil && entry.isRefreshable12305"),
                      "the medium widget no longer knows when its rows are the bottom line")
        let rows = try XCTUnwrap(medium.range(of: "ForEach(Array(reading.rows.enumerated())"))
        let captionLine = try XCTUnwrap(medium.range(of: "if let caption {"))
        XCTAssertTrue(medium[rows.upperBound..<captionLine.lowerBound].contains(".padding(.trailing, clearsRefresh ? 24 : 0)"),
                      "the medium widget's rows run under the ↻ when there is no caption line")
        XCTAssertTrue(medium[captionLine.upperBound...].contains(".padding(.trailing, entry.isRefreshable12305 ? 24 : 0)"),
                      "the medium widget's caption no longer keeps clear of the ↻")
    }
}
