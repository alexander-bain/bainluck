import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11288 — Alex, TestFlight 1.0.4 (65), 10/19: Sports "was blank while loading".
/// Two source causes: the skeleton was close to invisible (bars ~1.26:1 on a white
/// row, no words), and a successful main with nothing to render fell through to a
/// list holding only the chip row — no message, no retry — for as long as the
/// optional backfill took (up to its 10 s deadline).
///
/// These pin `FeedViewModel.tabState`: one decision for every state the tab can land
/// in, driven both as a pure table and through a real `load()` with gated fakes.
@MainActor
final class SportsTabLoadingAndEmpty11288Tests: XCTestCase {

    // MARK: - Gated fake

    private nonisolated final class Gate: @unchecked Sendable {
        private let lock = NSLock()
        private var opened = false
        private var conts: [CheckedContinuation<Void, Never>] = []

        func open() {
            let waiting: [CheckedContinuation<Void, Never>] = lock.withLock {
                opened = true
                defer { conts = [] }
                return conts
            }
            waiting.forEach { $0.resume() }
        }

        func wait() async {
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                let now: Bool = lock.withLock {
                    if opened { return true }
                    conts.append(cont)
                    return false
                }
                if now { cont.resume() }
            }
        }
    }

    private nonisolated final class Client: SportsFeedProviding, @unchecked Sendable {
        let main: Result<FeedResponse, Error>
        let backfill: FeedResponse
        let grouped: GroupedFeedResponse
        let siblingGate: Gate?

        init(main: Result<FeedResponse, Error>, backfill: FeedResponse, grouped: GroupedFeedResponse, siblingGate: Gate? = nil) {
            self.main = main
            self.backfill = backfill
            self.grouped = grouped
            self.siblingGate = siblingGate
        }

        nonisolated func fetchSportsFeed() async throws -> FeedResponse { try main.get() }

        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            if let siblingGate { await siblingGate.wait() }
            return backfill
        }

        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            if let siblingGate { await siblingGate.wait() }
            return grouped
        }
    }

    // MARK: - Fixtures

    private func feed(_ items: [String]) throws -> FeedResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let json = #"{"items":["# + items.joined(separator: ",") + #"],"total":9999,"limit":50,"offset":0,"has_more":true}"#
        return try d.decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func grouped() throws -> GroupedFeedResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(GroupedFeedResponse.self, from: Data(#"{"feed":[],"total":0,"limit":20,"offset":0}"#.utf8))
    }

    private func upcomingEvent(_ id: Int) -> String {
        #"{"type":"event","score":90,"data":{"id":\#(id),"home_team":"Home \#(id)","away_team":"Away \#(id)","status":"scheduled"}}"#
    }

    private func waitUntil(_ cond: () -> Bool, cap: Int = 5000) async {
        var n = 0
        while !cond() && n < cap { await Task.yield(); n += 1 }
    }

    private func state(_ vm: FeedViewModel) -> SportsTabState {
        vm.tabState(for: "all", pinnedAnywhere: false, pinnedInCategory: false)
    }

    // MARK: - Through a real load

    /// The issue's first named guard: main succeeded, nothing renders, the
    /// optional requests are still out → the tab is LOADING, not an empty list.
    func testEmptyMainWithSiblingsPendingStaysLoading() async throws {
        let gate = Gate()
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([])), backfill: try feed([]), grouped: try grouped(), siblingGate: gate),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        let task = Task { await vm.load() }

        await waitUntil { vm.mainAnswered }
        XCTAssertFalse(vm.loading, "the main answered, so the cold-load flag is down")
        XCTAssertTrue(vm.siblingsPending, "backfill and grouped are still out")
        XCTAssertEqual(state(vm), .loading, "an empty main with requests outstanding keeps the loading state")

        gate.open()
        await task.value
    }

    /// The issue's second named guard: every request answered and nothing to
    /// show → a message with Retry.
    func testAllAnsweredWithNothingShowsMessageAndRetry() async throws {
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([])), backfill: try feed([]), grouped: try grouped()),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await vm.load()

        XCTAssertTrue(vm.mainAnswered)
        XCTAssertFalse(vm.siblingsPending)
        XCTAssertEqual(state(vm), .nothingToShow(refreshFailed: false))
    }

    /// Control for the two above: a backfill that brings a game makes the same
    /// empty main end in content, so the loading state was waiting on real work.
    func testEmptyMainRescuedByBackfillEndsInContent() async throws {
        let gate = Gate()
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([])), backfill: try feed([upcomingEvent(7)]), grouped: try grouped(), siblingGate: gate),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        let task = Task { await vm.load() }
        await waitUntil { vm.mainAnswered }
        XCTAssertEqual(state(vm), .loading)

        gate.open()
        await task.value
        XCTAssertEqual(vm.items.map(\.id), ["event-7"])
        XCTAssertEqual(state(vm), .content)
    }

    /// Main-first regression kept: a main with a card shows it at once, while
    /// both optional requests are still gated.
    func testMainWithCardsShowsContentWithoutWaitingForSiblings() async throws {
        let gate = Gate()
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([upcomingEvent(1)])), backfill: try feed([]), grouped: try grouped(), siblingGate: gate),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        let task = Task { await vm.load() }

        await waitUntil { vm.mainAnswered }
        XCTAssertTrue(vm.siblingsPending)
        XCTAssertEqual(state(vm), .content, "first paint is gated on the main only")

        gate.open()
        await task.value
    }

    /// A sibling that never answers is given up on at the deadline; the tab then
    /// stops claiming to load and offers Retry instead of spinning forever.
    func testSiblingDeadlineEndsTheLoadingState() async throws {
        let neverOpened = Gate()
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([])), backfill: try feed([]), grouped: try grouped(), siblingGate: neverOpened),
            telemetry: nil,
            autoRefreshEnabled: false,
            siblingDeadline: 0.05
        )
        await vm.load()

        XCTAssertFalse(vm.siblingsPending, "the deadline closed the merge")
        XCTAssertEqual(state(vm), .nothingToShow(refreshFailed: false))
        neverOpened.open()
    }

    /// A quietly cancelled cold main (a superseding load is already coming) is not
    /// an answer: no "nothing to show" flash, and still no error screen.
    func testQuietlyCancelledColdMainIsNotAnEmptyAnswer() async throws {
        let vm = FeedViewModel(
            client: Client(main: .failure(CancellationError()), backfill: try feed([]), grouped: try grouped()),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await vm.load()

        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.mainAnswered)
        XCTAssertEqual(state(vm), .loading)
    }

    /// The error screen is unchanged: a real cold main failure still lands there.
    func testColdMainFailureStillShowsTheErrorScreen() async throws {
        let vm = FeedViewModel(
            client: Client(main: .failure(URLError(.timedOut)), backfill: try feed([]), grouped: try grouped()),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await vm.load()

        guard case .failed = state(vm) else {
            return XCTFail("expected the error screen, got \(state(vm))")
        }
        XCTAssertTrue(vm.mainAnswered)
    }

    func testViewDidStopClearsSiblingsPending() async throws {
        let gate = Gate()
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([])), backfill: try feed([]), grouped: try grouped(), siblingGate: gate),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        let task = Task { await vm.load() }
        await waitUntil { vm.siblingsPending }

        vm.viewDidStop()
        XCTAssertFalse(vm.siblingsPending)

        gate.open()
        await task.value
        XCTAssertFalse(vm.siblingsPending, "a stopped load's late siblings cannot re-raise it")
    }

    // MARK: - The decision table

    private func decide(
        loading: Bool = false,
        error: String? = nil,
        itemsEmpty: Bool = true,
        refreshFailed: Bool = false,
        mainAnswered: Bool = true,
        siblingsPending: Bool = false,
        showsAnything: Bool = false,
        showsInCategory: Bool = false
    ) -> SportsTabState {
        FeedViewModel.tabState(
            loading: loading, error: error, itemsEmpty: itemsEmpty, refreshFailed: refreshFailed,
            mainAnswered: mainAnswered, siblingsPending: siblingsPending,
            showsAnything: showsAnything, showsInCategory: showsInCategory
        )
    }

    func testDecisionTable() {
        XCTAssertEqual(decide(loading: true), .loading, "cold load")
        XCTAssertEqual(decide(loading: true, showsAnything: true, showsInCategory: true), .loading,
                       "the cold-load flag wins, as before")
        XCTAssertEqual(decide(error: "x"), .failed("x"), "cold failure → error screen")
        XCTAssertEqual(decide(error: "x", itemsEmpty: false, showsAnything: true, showsInCategory: true), .content,
                       "an error never replaces cards already held")
        XCTAssertEqual(decide(siblingsPending: true), .loading, "empty main, requests out")
        XCTAssertEqual(decide(mainAnswered: false), .loading, "no answer yet")
        XCTAssertEqual(decide(), .nothingToShow(refreshFailed: false), "all answered, empty")
        XCTAssertEqual(decide(itemsEmpty: false, refreshFailed: true), .nothingToShow(refreshFailed: true),
                       "held rows that draw nothing plus a failed refresh says so, not 'no games'")
        XCTAssertEqual(decide(siblingsPending: true, showsAnything: true, showsInCategory: true), .content,
                       "cards render while requests are out")
    }

    /// A selected chip with no matches is not a globally empty tab: it neither
    /// claims "no games" nor offers Retry. (Today every non-All chip opens a league
    /// page instead of filtering in place, so this is the rule for when one does.)
    func testEmptyCategoryIsDistinctFromGloballyEmpty() {
        XCTAssertEqual(decide(showsAnything: true), .nothingInCategory(stillLoading: false))
        XCTAssertEqual(decide(siblingsPending: true, showsAnything: true), .nothingInCategory(stillLoading: true))
        XCTAssertNotEqual(decide(showsAnything: true), decide())
    }

    /// Grouped props are not chip-filtered and draw a section on their own, so
    /// they alone keep the tab out of the empty state.
    func testGroupedPropsAloneCountAsContent() async throws {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let oneGroup = try d.decode(GroupedFeedResponse.self, from: Data(#"""
        {"feed":[{"type":"playoff_progression","group_key":"g0","entity_name":"Team 0","stages":[{"id":0,"label":"Round 1","probability":0.5,"status":"active"}]}],"total":1,"limit":20,"offset":0}
        """#.utf8))
        let vm = FeedViewModel(
            client: Client(main: .success(try feed([])), backfill: try feed([]), grouped: oneGroup),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await vm.load()
        XCTAssertEqual(vm.groupedItems.count, 1)
        XCTAssertEqual(state(vm), .content)
    }

    // MARK: - The placeholder itself

    func testPlaceholderIsDarkerThanTheOldBarsAndCarriesACaption() {
        XCTAssertNotEqual(Color.skeletonFill, Color.systemGray5, "the 1.26:1 bar colour is gone")
        XCTAssertLessThan(ShimmerModifier.sweepOpacity, 0.35, "the sweep no longer washes the bars out")
        XCTAssertEqual(SkeletonFeedView(caption: "Loading games…").caption, "Loading games…")
        XCTAssertNil(SkeletonFeedView().caption, "other surfaces keep their uncaptioned placeholder")
    }
}
