import XCTest
@testable import Bain_Luck

/// #10878 / #4940 — Command-K → type → arrows → Return on a Mac.
///
/// This target runs on iOS, so neither the Mac window nor SwiftUI focus can be
/// mounted here, and nothing below claims the field actually took focus or that
/// a key reached it. What runs here is every rule the Mac journey is built
/// from: when a window asks its Search field for focus and who drains the ask,
/// that one window's ask never reaches another, and how the picked result row
/// follows its canonical route as answers change. Two reads of `SearchView`
/// prove the shipping rows and key handling are wired to those rules. The
/// mounted journey (cold and warm Command-K, arrows, Return, Escape, VoiceOver,
/// a second window) is acceptance on a real Mac.
@MainActor
final class MacKeyboardSelection10878Tests: XCTestCase {

    // MARK: - The focus ask

    /// Cold Command-K: the ask is made before SearchView exists, so the mount
    /// drains it — once.
    func testAnAskIsAnsweredOnce() {
        var ticket = MacSearchFocusTicket10878()
        XCTAssertFalse(ticket.consume(), "nothing was asked")
        ticket.request()
        XCTAssertTrue(ticket.isPending)
        XCTAssertTrue(ticket.consume())
        XCTAssertFalse(ticket.consume(), "a second drain (mount AND change) must not focus twice")
    }

    /// Warm Command-K: the change drain is driven by `requested` moving, so it
    /// must move on every ask — even one made while an earlier ask is still
    /// undrained, which is where a plain flag would stay `true` and go silent.
    func testEveryAskMovesTheValueTheChangeDrainWatches() {
        var ticket = MacSearchFocusTicket10878()
        ticket.request()
        let first = ticket.requested
        ticket.request()
        XCTAssertNotEqual(ticket.requested, first)
        XCTAssertTrue(ticket.consume())
        XCTAssertFalse(ticket.consume(), "asks made before one drain are one focus")
        ticket.request()
        XCTAssertTrue(ticket.consume(), "an ask after a drain is a new ask")
    }

    /// Choosing Search while it is showing is the Mac menu pressed again.
    func testChoosingSearchAgainAsksForTheField() {
        let nav = macNavigation(on: .search)
        nav.selectedTab = .search
        XCTAssertTrue(nav.consumeSearchFocusRequest())
        XCTAssertFalse(nav.consumeSearchFocusRequest())
    }

    /// Arriving at Search from another tab is not an ask: a sidebar click must
    /// reopen the reader's kept place (#10903), and arrowing down the sidebar
    /// must not fall into the field.
    func testArrivingAtSearchFromAnotherTabDoesNotAsk() {
        let nav = macNavigation(on: .discover)
        nav.selectedTab = .search
        XCTAssertFalse(nav.searchFocus.isPending)
        nav.selectedTab = .myStuff
        nav.selectedTab = .myStuff
        XCTAssertFalse(nav.searchFocus.isPending, "re-choosing another tab asks nothing")
    }

    /// Cold Command-K's menu action selects Search, then asks explicitly.
    func testColdCommandKSelectsThenAsks() {
        let nav = macNavigation(on: .discover)
        nav.selectedTab = .search
        nav.requestSearchFocus()
        XCTAssertTrue(nav.consumeSearchFocusRequest())
        XCTAssertFalse(nav.consumeSearchFocusRequest())
    }

    /// The same menu action pressed while Search is showing asks twice in one
    /// turn (the repeat selection, then the explicit ask): still one focus.
    func testWarmCommandKWithTheExplicitAskIsStillOneFocus() {
        let nav = macNavigation(on: .search)
        nav.selectedTab = .search
        nav.requestSearchFocus()
        XCTAssertTrue(nav.consumeSearchFocusRequest())
        XCTAssertFalse(nav.consumeSearchFocusRequest())
    }

    /// Each Mac window has its own coordinator (#10909). An ask in one is
    /// never seen, or drained, by the other.
    func testOneWindowsAskNeverReachesAnother() {
        let first = macNavigation(on: .search)
        let second = macNavigation(on: .search)
        first.selectedTab = .search
        XCTAssertFalse(second.searchFocus.isPending)
        XCTAssertFalse(second.consumeSearchFocusRequest())
        XCTAssertTrue(first.consumeSearchFocusRequest())

        second.requestSearchFocus()
        XCTAssertFalse(first.consumeSearchFocusRequest())
        XCTAssertTrue(second.consumeSearchFocusRequest())
    }

    /// A phone never asks: re-tapping the Search tab must not raise a keyboard
    /// over the tab bar (#6446).
    func testThePhoneNeverAsks() {
        let nav = NavigationCoordinator()
        #if !os(macOS)
        XCTAssertFalse(nav.selectingSearchRequestsFocus)
        #endif
        nav.selectingSearchRequestsFocus = false
        nav.selectedTab = .search
        nav.selectedTab = .search
        XCTAssertFalse(nav.consumeSearchFocusRequest())
    }

    // MARK: - The picked row

    func testRowsAreOrderedAsDrawnWithEachDestinationOnce() {
        let order = MacKeyboardSelection10878<String>.order([["hub"], [], ["a", "b"], ["b", "c"]])
        XCTAssertEqual(order, ["hub", "a", "b", "c"])
    }

    func testDownFromTheFieldPicksTheFirstRowAndStopsAtTheLast() {
        var pick = MacKeyboardSelection10878<String>()
        let rows = ["a", "b", "c"]
        XCTAssertTrue(pick.moveDown(in: rows))
        XCTAssertEqual(pick.selected, "a")
        pick.moveDown(in: rows)
        pick.moveDown(in: rows)
        XCTAssertTrue(pick.moveDown(in: rows))
        XCTAssertEqual(pick.selected, "c", "down on the last row stays there")
    }

    /// Up from the first row hands back to the field (Return searches again);
    /// up with nothing picked is the field's own key.
    func testUpFromTheFirstRowReturnsToTheField() {
        var pick = MacKeyboardSelection10878<String>()
        let rows = ["a", "b"]
        XCTAssertFalse(pick.moveUp(in: rows), "nothing picked: the caret's key")
        pick.moveDown(in: rows)
        pick.moveDown(in: rows)
        XCTAssertTrue(pick.moveUp(in: rows))
        XCTAssertEqual(pick.selected, "a")
        XCTAssertTrue(pick.moveUp(in: rows))
        XCTAssertNil(pick.selected)
        XCTAssertNil(pick.activation(in: rows))
    }

    /// No answer, an empty answer, a degraded answer with no rows, a running
    /// search: there is nothing to move through, so the keys stay the field's
    /// and Return keeps its meaning (search / try again).
    func testWithNoRowsTheKeysStayTheFields() {
        var pick = MacKeyboardSelection10878<String>()
        XCTAssertFalse(pick.moveDown(in: []))
        XCTAssertFalse(pick.moveUp(in: []))
        XCTAssertNil(pick.selected)
        XCTAssertNil(pick.activation(in: []))
    }

    /// A replaced answer (retry, sport filter, a slower response landing) keeps
    /// the same row picked wherever it now draws, and the arrows continue from
    /// there.
    func testThePickFollowsItsRouteWhenTheAnswerChanges() {
        var pick = MacKeyboardSelection10878<Route>()
        let before: [Route] = [.eventDetail(id: 1), .eventDetail(id: 2), .futuresDetail(id: 3)]
        pick.moveDown(in: before)
        pick.moveDown(in: before)
        XCTAssertEqual(pick.selected, .eventDetail(id: 2))

        let after: [Route] = [.futuresDetail(id: 3), .eventDetail(id: 2), .futuresDetail(id: 9)]
        pick.reconcile(with: after)
        XCTAssertEqual(pick.selected, .eventDetail(id: 2))
        XCTAssertEqual(pick.activation(in: after), .eventDetail(id: 2))
        pick.moveDown(in: after)
        XCTAssertEqual(pick.selected, .futuresDetail(id: 9))
    }

    /// A row the new answer no longer draws is dropped, never swapped for
    /// whatever took its slot — Return then searches instead of opening a game
    /// the reader did not pick.
    func testAPickTheNewAnswerNoLongerDrawsIsDropped() {
        var pick = MacKeyboardSelection10878<Route>()
        let before: [Route] = [.eventDetail(id: 1), .eventDetail(id: 2)]
        pick.moveDown(in: before)
        pick.moveDown(in: before)
        let after: [Route] = [.eventDetail(id: 1), .eventDetail(id: 7)]
        pick.reconcile(with: after)
        XCTAssertNil(pick.selected)
        XCTAssertNil(pick.activation(in: after))
    }

    /// While a search runs the page draws no rows; Return must not open the
    /// picked row from the answer being replaced, and the pick survives to the
    /// answer.
    func testReturnOpensOnlyARowOnScreenNow() {
        var pick = MacKeyboardSelection10878<Route>()
        let rows: [Route] = [.teamDetail(slug: "boston-red-sox-mlb")]
        pick.moveDown(in: rows)
        XCTAssertNil(pick.activation(in: []), "spinner up: nothing drawn, nothing opened")
        XCTAssertEqual(pick.activation(in: rows), .teamDetail(slug: "boston-red-sox-mlb"))
    }

    /// Two rows with the same name are two canonical destinations. The pick is
    /// the route, so Return opens exactly the one highlighted.
    func testRowsWithTheSameNameStayDistinct() {
        var pick = MacKeyboardSelection10878<Route>()
        let rows: [Route] = [.teamDetail(slug: "carolina-panthers-nfl"), .teamDetail(slug: "florida-panthers-nhl")]
        pick.moveDown(in: rows)
        pick.moveDown(in: rows)
        XCTAssertEqual(pick.activation(in: rows), .teamDetail(slug: "florida-panthers-nhl"))
        XCTAssertFalse(pick.isSelected(.teamDetail(slug: "carolina-panthers-nfl")))
    }

    /// Escape drops a pick first; with nothing picked it reports false so the
    /// next Escape can leave the field.
    func testEscapeDropsThePickThenLetsGo() {
        var pick = MacKeyboardSelection10878<String>()
        pick.moveDown(in: ["a"])
        XCTAssertTrue(pick.clear())
        XCTAssertNil(pick.selected)
        XCTAssertFalse(pick.clear())
    }

    // MARK: - The shipping SearchView

    /// Every result row the page draws is marked with the route it opens, so
    /// the highlighted row and the row Return opens are the same destination.
    func testEveryResultRowIsMarkedWithTheRouteItOpens() throws {
        let source = try Self.appSource("Views/SearchView.swift")
        let results = try XCTUnwrap(
            Self.slice(source, from: "private func searchResults(", to: "// MARK: - Tournament Row"),
            "searchResults moved"
        )
        var opens: [String] = []
        var marks: [String] = []
        for line in results.components(separatedBy: "\n") {
            let text = line.trimmingCharacters(in: .whitespaces)
            if let route = Self.argument(of: "NavigationLink(value: ", in: text, closingBefore: ") {") {
                opens.append(Self.normalized(route))
            } else if let route = Self.argument(of: "path.append(", in: text, closingBefore: ")") {
                opens.append(Self.normalized(route))
            } else if let route = Self.argument(of: ".macKeyboardRow(", in: text, closingBefore: ", in: keyboardSelection)") {
                marks.append(Self.normalized(route))
            }
        }
        XCTAssertEqual(opens.count, 10, "result row count changed — mark any new row")
        XCTAssertEqual(marks, opens)
    }

    /// The arrows walk the sections in the order the page draws them.
    func testTheArrowOrderIsTheDrawOrder() throws {
        let source = try Self.appSource("Views/SearchView.swift")
        let drawn = try XCTUnwrap(Self.slice(source, from: "private func searchResults(", to: "// MARK: - Tournament Row"))
        let walked = try XCTUnwrap(Self.slice(source, from: "private var keyboardRoutes: [Route]", to: "private func handleEscape()"))
        let kinds = ["tournamentHub", ".route", "teamDetail", "eventDetail", "futuresDetail"]
        XCTAssertEqual(Self.firstAppearanceOrder(of: kinds, in: walked), kinds)
        XCTAssertEqual(Self.firstAppearanceOrder(of: kinds, in: drawn), kinds)
    }

    /// Keys are handled on the field, on the Mac only, with no app-wide
    /// keyboard monitor.
    func testKeyHandlingIsTheFieldsOwnAndMacOnly() throws {
        let source = try Self.appSource("Views/SearchView.swift")
        XCTAssertFalse(source.contains("addLocalMonitorForEvents"))
        XCTAssertFalse(source.contains("addGlobalMonitorForEvents"))
        var platform: [String] = []
        var keyPresses = 0
        for line in source.components(separatedBy: "\n") {
            let text = line.trimmingCharacters(in: .whitespaces)
            if text.hasPrefix("#if ") { platform.append(text) }
            if text == "#endif" { _ = platform.popLast() }
            if text.hasPrefix(".onKeyPress(") {
                keyPresses += 1
                XCTAssertEqual(platform.last, "#if os(macOS)", "\(text) runs outside the Mac")
            }
        }
        XCTAssertEqual(keyPresses, 2, "the arrows, escape")
    }

    /// An arrow held with Shift, Command, Option or Control is one of the
    /// field's editing shortcuts (⇧↓ extends the text selection), so it is
    /// handed back before it can move the pick. The single-key overload hands
    /// the handler no press to read modifiers from, so it is refused outright.
    /// Only those four are named: arrows always carry `.function` and
    /// `.numericPad` on macOS, so refusing every modifier would break plain
    /// arrows. Whether SwiftUI delivers the press to a focused field is mounted
    /// acceptance, not this read.
    func testModifiedArrowsStayTheFields() throws {
        let source = try Self.appSource("Views/SearchView.swift")
        XCTAssertFalse(source.contains(".onKeyPress(.downArrow)"), "single-key ↓ cannot see modifiers")
        XCTAssertFalse(source.contains(".onKeyPress(.upArrow)"), "single-key ↑ cannot see modifiers")
        let handler = try XCTUnwrap(
            Self.slice(source, from: ".onKeyPress(keys: [.downArrow, .upArrow], phases: [.down, .repeat]) { press in", to: ".onKeyPress(.escape)"),
            "the arrow handler no longer takes the press"
        )
        let statements = handler
            .components(separatedBy: "\n")
            .dropFirst()
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        XCTAssertEqual(
            statements.first,
            "guard press.modifiers.isDisjoint(with: Self.arrowEditingModifiers) else { return .ignored }",
            "the modifier refusal must come before anything moves the pick"
        )
        let declared = try XCTUnwrap(
            Self.argument(
                of: "private static let arrowEditingModifiers: EventModifiers = [",
                in: source.components(separatedBy: "\n")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .first { $0.hasPrefix("private static let arrowEditingModifiers") } ?? "",
                closingBefore: "]"
            ),
            "arrowEditingModifiers moved or changed shape"
        )
        XCTAssertEqual(
            Set(declared.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }),
            [".shift", ".command", ".option", ".control"]
        )
    }

    // MARK: - Helpers

    private func macNavigation(on tab: AppTab) -> NavigationCoordinator {
        let nav = NavigationCoordinator()
        nav.selectingSearchRequestsFocus = true
        nav.selectedTab = tab
        _ = nav.consumeSearchFocusRequest()
        return nav
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        return try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static func slice(_ text: String, from start: String, to end: String) -> String? {
        guard let lower = text.range(of: start),
              let upper = text.range(of: end, range: lower.upperBound..<text.endIndex) else { return nil }
        return String(text[lower.lowerBound..<upper.lowerBound])
    }

    private static func argument(of prefix: String, in line: String, closingBefore suffix: String) -> String? {
        guard line.hasPrefix(prefix), line.hasSuffix(suffix) else { return nil }
        return String(line.dropFirst(prefix.count).dropLast(suffix.count))
    }

    private static func normalized(_ route: String) -> String {
        route.hasPrefix("Route.") ? String(route.dropFirst("Route".count)) : route
    }

    private static func firstAppearanceOrder(of tokens: [String], in text: String) -> [String] {
        tokens
            .compactMap { token in text.range(of: token).map { (token, $0.lowerBound) } }
            .sorted { $0.1 < $1.1 }
            .map(\.0)
    }
}
