import Combine
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10878 — the Mac main window.
///
/// `MainTabView` used to pick its root from the size class alone, so a Mac window
/// got the phone tab bar or the iPad split depending on what the environment
/// reported. It now asks `MacMainWindow10878.root`, which gives the Mac its own
/// sidebar window and leaves iPhone and iPad on exactly the rule they had.
///
/// This target runs on iOS, so the macOS view itself cannot be mounted here.
/// What runs here is every rule that view is built from — the root choice, the
/// sidebar's places, selection against the real `NavigationCoordinator`, and the
/// window/column sizes — plus one read of `MainTabView` proving the shipping
/// body routes through that rule. Mac renders, keyboard/VoiceOver and the
/// second-window check are separate acceptance on a real Mac.
///
/// Recorded window sizes (sidebar at its ideal 220pt):
/// - narrow 800 × 600 (minimum): detail 580pt; with the widest sidebar 520pt
/// - normal 1200 × 800 (the app's default): detail 980pt, uncapped
/// - wide 1680 × 1000: detail 1460pt, centred column capped at 1100pt
@MainActor
final class MacMainWindow10878Tests: XCTestCase {

    // MARK: - Root choice

    func testPhoneAndIPadKeepTheirSizeClassRule() {
        XCTAssertEqual(MacMainWindow10878.root(isMac: false, sizeClass: .regular), .iPadSplit)
        XCTAssertEqual(MacMainWindow10878.root(isMac: false, sizeClass: .compact), .phoneTabs)
        XCTAssertEqual(MacMainWindow10878.root(isMac: false, sizeClass: nil), .phoneTabs)
    }

    func testTheMacGetsItsOwnWindowWhateverSizeClassItReports() {
        for sizeClass: UserInterfaceSizeClass? in [.regular, .compact, nil] {
            XCTAssertEqual(MacMainWindow10878.root(isMac: true, sizeClass: sizeClass), .macWindow)
        }
    }

    /// The iOS app is never routed to the Mac window: on this host the rule's
    /// platform input is false, so the two assertions above are the whole
    /// iPhone/iPad behaviour.
    func testThisIOSHostIsNotTreatedAsAMac() {
        XCTAssertFalse(MacMainWindow10878.runsOnMac)
    }

    /// The runtime checks above only protect the app if `MainTabView` asks the
    /// rule. Its body must route through it, mount the Mac window on the Mac
    /// arm, and keep both existing layouts on theirs.
    func testMainTabViewRoutesThroughTheRule() throws {
        let source = try Self.appSource("Views/MainTabView.swift")
        let body = try XCTUnwrap(Self.slice(source, from: "var body: some View {", to: "// MARK: - iPhone"))

        XCTAssertTrue(body.contains(
            "switch MacMainWindow10878.root(isMac: MacMainWindow10878.runsOnMac, sizeClass: sizeClass)"
        ), "MainTabView no longer chooses its root through MacMainWindow10878.root")
        let macArm = try XCTUnwrap(Self.slice(body, from: "case .macWindow:", to: "case .iPadSplit:"))
        XCTAssertTrue(macArm.contains("MacMainWindowView()"), "the Mac arm does not mount the Mac window")
        XCTAssertTrue(body.contains("case .iPadSplit:\n            iPadLayout"))
        XCTAssertTrue(body.contains("case .phoneTabs:\n            iPhoneLayout"))
        // The old direct size-class branch is gone, so nothing bypasses the rule.
        XCTAssertFalse(body.contains("if sizeClass == .regular"))
    }

    // MARK: - Sidebar

    func testTheSidebarHasThePhonesFivePlacesInOrder() {
        XCTAssertEqual(
            MacMainWindow10878.destinations.map(\.tab),
            [.discover, .feed, .leagues, .search, .myStuff]
        )
        XCTAssertEqual(
            MacMainWindow10878.destinations.map(\.title),
            ["Discover", "Sports", "Browse", "Search", "My Stuff"]
        )
        XCTAssertEqual(MacMainWindow10878.quickLinks.map(\.tab), [.preferences, .calibration])
        XCTAssertEqual(MacMainWindow10878.quickLinks.map(\.title), ["Preferences", CalibrationView.readerTitle])
    }

    /// #10877: no sidebar label calls content a "question".
    func testNoSidebarLabelSaysQuestion() {
        for item in MacMainWindow10878.destinations + MacMainWindow10878.quickLinks {
            XCTAssertFalse(item.title.lowercased().contains("question"), item.title)
        }
    }

    /// Every tab the app has is either a sidebar place or a declared
    /// detail-only destination — a new `AppTab` fails here until someone
    /// decides where the Mac shows it.
    func testEveryTabIsPlacedOrDeclaredDetailOnly() {
        let all = Set((0..<64).compactMap(AppTab.init(rawValue:)))
        XCTAssertEqual(all.count, 12, "AppTab gained or lost a case; place it in the Mac sidebar or detailOnlyTabs")

        let sidebar = (MacMainWindow10878.destinations + MacMainWindow10878.quickLinks).map(\.tab)
        XCTAssertEqual(Set(sidebar).count, sidebar.count, "a tab appears twice in the sidebar")
        XCTAssertTrue(Set(sidebar).isDisjoint(with: MacMainWindow10878.detailOnlyTabs))
        XCTAssertEqual(Set(sidebar).union(MacMainWindow10878.detailOnlyTabs), all)
    }

    /// Every supported link lands on a sidebar place, so the Mac sidebar always
    /// highlights where the link took the reader.
    func testEveryDeepLinkLandsOnAPlaceTheSidebarHighlights() throws {
        let links = [
            "bainluck://events/15327331", "bainluck://events", "bainluck://futures/9413479",
            "bainluck://futures", "bainluck://search?q=red%20sox", "bainluck://tournaments/us-open",
            "bainluck://golf/the-masters", "bainluck://playoffs/wnba", "bainluck://team/boston-red-sox-mlb",
            "bainluck://my-stuff", "bainluck://preferences", "bainluck://weather",
            "bainluck://calibration", "bainluck://about", "https://bainluck.com/events/15327331",
        ]
        let places = Set(MacMainWindow10878.destinations.map(\.tab))
        for link in links {
            let coordinator = NavigationCoordinator()
            coordinator.selectedTab = .myStuff
            XCTAssertTrue(coordinator.handleURL(try XCTUnwrap(URL(string: link))), "\(link) is not routed")
            XCTAssertTrue(places.contains(coordinator.selectedTab), "\(link) selected \(coordinator.selectedTab)")
        }
    }

    func testSelectingASidebarRowMovesTheWindow() async {
        let coordinator = NavigationCoordinator()
        coordinator.selectedTab = .discover

        MacMainWindow10878.applySelection(.search, to: coordinator)
        await Self.drainMainQueue()
        XCTAssertEqual(coordinator.selectedTab, .search)

        MacMainWindow10878.applySelection(.calibration, to: coordinator)
        await Self.drainMainQueue()
        XCTAssertEqual(coordinator.selectedTab, .calibration)
    }

    /// Clicking empty sidebar space deselects the list; the reader stays put.
    func testDeselectingKeepsTheReaderWhereTheyAre() async {
        let coordinator = NavigationCoordinator()
        coordinator.selectedTab = .myStuff

        MacMainWindow10878.applySelection(nil, to: coordinator)
        await Self.drainMainQueue()
        XCTAssertEqual(coordinator.selectedTab, .myStuff)
    }

    func testTheLiveBadgeUsesThePhonesWords() throws {
        XCTAssertNil(MacMainWindow10878.liveBadge(count: 0))
        XCTAssertNil(MacMainWindow10878.liveBadge(count: -1))
        XCTAssertEqual(MacMainWindow10878.liveBadge(count: 3), "3 live")
        // The phone tab bar's own string, so the two cannot drift.
        let tabView = try Self.appSource("Views/MainTabView.swift")
        XCTAssertTrue(tabView.contains("\"\\(navCoordinator.liveGameCount) live\""))
    }

    // MARK: - Window and column sizes

    func testSidebarWidthsAreOrdered() {
        XCTAssertLessThanOrEqual(MacMainWindow10878.sidebarMinWidth, MacMainWindow10878.sidebarIdealWidth)
        XCTAssertLessThanOrEqual(MacMainWindow10878.sidebarIdealWidth, MacMainWindow10878.sidebarMaxWidth)
    }

    /// At the narrowest window with the widest sidebar, the detail column is
    /// still a width the iPad's wide layouts already serve — the window stops
    /// shrinking before text has to.
    func testTheNarrowestWindowStillFitsTheWideLayouts() {
        let detail = MacMainWindow10878.minimumWindowSize.width - MacMainWindow10878.sidebarMaxWidth
        XCTAssertGreaterThanOrEqual(detail, MacMainWindow10878.narrowestRegularDetailWidth)
    }

    /// A normal laptop window is untouched by the cap; a wide desktop window
    /// gets a centred column; Discover's own 800pt Mac cap is never squeezed.
    func testTheReadableCapOnlyBitesOnWideWindows() {
        let cap = MacMainWindow10878.readableContentWidth
        let ideal = MacMainWindow10878.sidebarIdealWidth
        XCTAssertLessThanOrEqual(1200 - ideal, cap, "a normal 1200pt window would be capped")
        XCTAssertGreaterThan(1680 - ideal, cap, "a wide 1680pt window would stretch edge to edge")
        XCTAssertGreaterThanOrEqual(cap, 800, "the column would squeeze Discover's own Mac width")
    }

    /// The app opens its main window at 1200 × 800; that must not be smaller
    /// than the minimum this window declares.
    func testTheDefaultWindowIsAtLeastTheMinimum() throws {
        let app = try Self.appSource("Bain_LuckApp.swift")
        XCTAssertTrue(app.contains(".defaultSize(width: 1200, height: 800)"), "the main window's default size moved")
        XCTAssertLessThanOrEqual(MacMainWindow10878.minimumWindowSize.width, 1200)
        XCTAssertLessThanOrEqual(MacMainWindow10878.minimumWindowSize.height, 800)
    }

    func testTheDetailUsesTheWideLayoutFamily() {
        XCTAssertEqual(MacMainWindow10878.detailSizeClass, .regular)
    }

    // MARK: - Helpers

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

    /// `applySelection` defers its write with `DispatchQueue.main.async`; a
    /// block enqueued after it runs after it.
    private static func drainMainQueue() async {
        await withCheckedContinuation { continuation in
            DispatchQueue.main.async { continuation.resume() }
        }
    }
}

/// #10878 correction — the Mac window keeps a reader's place on Discover, Search
/// and My Stuff while it mounts only one screen at a time.
///
/// The window used to drop each screen's state on every sidebar switch: the
/// screens own their view models and navigation paths, and the window's detail
/// switch unmounts whatever is not selected. `MacReadingState10878` now holds
/// that state above the mount and the screens adopt it when they mount again.
///
/// Covered here: the store and the place (identity resets, keep/release), the
/// scroll keeper's two decisions, and the REAL `SearchView` mounted, unmounted
/// and remounted the way the window does it — keeping its query and results,
/// and still stopping its work when it leaves. The scroll keeper's AppKit half
/// runs only on a Mac; it is proved there, not here.
@MainActor
final class MacReadingPlace10878Tests: XCTestCase {

    // MARK: - One reader's places

    func testTheSameReaderGetsTheSamePlacesBack() {
        let state = MacReadingState10878()
        let first = state.places(for: "reader-1")
        first.search.path.append(Route.about)
        let again = state.places(for: "reader-1")
        XCTAssertTrue(first === again)
        XCTAssertEqual(again.generation, first.generation)
        XCTAssertEqual(again.search.path.count, 1)
    }

    func testAGuestStaysTheSameGuest() {
        let state = MacReadingState10878()
        let guest = state.places(for: nil)
        XCTAssertTrue(state.places(for: nil) === guest)
    }

    /// An account change discards everything kept for the previous account —
    /// including screens that were offscreen when it changed, which cannot see
    /// the change themselves.
    func testAnAccountChangeDiscardsEveryKeptPlace() {
        let state = MacReadingState10878()
        let first = state.places(for: "reader-1")
        _ = first.search.models(orMake: { SearchViewModel() })
        first.search.path.append(Route.about)
        first.discover.revealedCount = 60
        first.myStuff.scrollPlace = MacScrollPlace(offset: 900, row: 3, offsetInRow: 40)

        let next = state.places(for: "reader-2")
        XCTAssertFalse(next === first)
        XCTAssertNotEqual(next.generation, first.generation, "the window rebuilds the screen on view")
        XCTAssertNil(next.search.models)
        XCTAssertTrue(next.search.path.isEmpty)
        XCTAssertNil(next.discover.revealedCount)
        XCTAssertEqual(next.myStuff.scrollPlace, MacScrollPlace())
    }

    /// Signing out and signing back in are both changes, and coming back to the
    /// first account does not bring its old places back.
    func testSigningOutAndBackInStartsFresh() {
        let state = MacReadingState10878()
        let signedIn = state.places(for: "reader-1")
        signedIn.search.path.append(Route.about)
        let guest = state.places(for: nil)
        XCTAssertFalse(guest === signedIn)
        XCTAssertTrue(guest.search.path.isEmpty)
        let back = state.places(for: "reader-1")
        XCTAssertFalse(back === signedIn)
        XCTAssertFalse(back === guest)
        XCTAssertTrue(back.search.path.isEmpty)
        XCTAssertEqual(Set([signedIn.generation, guest.generation, back.generation]).count, 3)
    }

    /// Two windows each own a store, so they never share a place.
    func testTwoWindowsKeepSeparatePlaces() {
        let a = MacReadingState10878(), b = MacReadingState10878()
        a.places(for: "reader-1").search.path.append(Route.about)
        XCTAssertTrue(b.places(for: "reader-1").search.path.isEmpty)
    }

    // MARK: - A screen's place

    func testAPlaceMakesItsModelsOnceAndKeepsThem() {
        let place = MacReadingPlace<SearchViewModel>()
        var made = 0
        let first = place.models(orMake: { made += 1; return SearchViewModel() })
        let second = place.models(orMake: { made += 1; return SearchViewModel() })
        XCTAssertTrue(first === second)
        XCTAssertEqual(made, 1)
    }

    /// Discover's first load can still be running when the reader leaves (it
    /// outlives the screen on purpose, #10399 / #10094). Coming back joins it:
    /// no second load starts beside it, and both waits end when it does.
    func testComingBackMidLoadJoinsTheLoadAlreadyRunning() async {
        let place = MacReadingPlace<SearchViewModel>()
        let gate = LoadGate()
        let started = Tally()
        let first = Task { await place.runInitialLoad { started.count += 1; await gate.wait() } }
        await gate.waitUntilWaiting()
        let returned = Task { await place.runInitialLoad { started.count += 1; await gate.wait() } }
        await Task.yield(); await Task.yield()
        XCTAssertEqual(started.count, 1, "coming back started a second load beside the first")
        gate.open()
        await first.value
        await returned.value
        XCTAssertEqual(started.count, 1)

        // Control: once it has finished, a later first load runs.
        await place.runInitialLoad { started.count += 1 }
        XCTAssertEqual(started.count, 2)
    }

    /// Leaving tears down the screen's appearance task; the first load it
    /// started must not be cancelled with it.
    func testLeavingDoesNotCancelTheFirstLoad() async {
        let place = MacReadingPlace<SearchViewModel>()
        let gate = LoadGate()
        let cancelled = Tally()
        let finished = Tally()
        let appearance = Task {
            await place.runInitialLoad {
                await gate.wait()
                if Task.isCancelled { cancelled.count += 1 }
                finished.count += 1
            }
        }
        await gate.waitUntilWaiting()
        appearance.cancel()   // the reader left
        gate.open()
        await appearance.value
        XCTAssertEqual(finished.count, 1, "control: the load ran to the end")
        XCTAssertEqual(cancelled.count, 0, "leaving cancelled the first load")
    }

    /// Discover's appearance task goes through the place on the Mac, and leaves
    /// a model that is running its cold-start recovery to it. (Wiring: the
    /// joining itself is proved above; Discover cannot be mounted in this
    /// target without a live sign-in manager.)
    func testDiscoverJoinsTheKeptLoadInsteadOfStartingAnother() throws {
        let source = try Self.appSource("Views/DiscoverView.swift")
        XCTAssertTrue(source.contains("if !vm.isRecovering { await macPlace.runInitialLoad(initialLoad) }"))
        XCTAssertTrue(source.contains("} else {\n                    await initialLoad()\n                }"),
                      "the iPhone/iPad path no longer runs its first load directly")
        XCTAssertFalse(source.contains("releaseModels"), "Discover lets its model go while its load can still run")
    }

    /// The window hands each reading screen its place, keyed on the account,
    /// and keeps one store per window. (Wiring only: the mounted tests below
    /// and the Mac runtime check prove the places are actually used.)
    func testTheMacWindowHandsEachReadingScreenItsPlace() throws {
        let source = try Self.appSource("Views/MacMainWindowView.swift")
        XCTAssertTrue(source.contains("@State private var readingState = MacReadingState10878()"))
        XCTAssertTrue(source.contains("readingState.places(for: authManager.activeFeedUserId)"))
        XCTAssertTrue(source.contains(".id(places.generation)"))
        for call in ["DiscoverView(macPlace: places.discover)",
                     "SearchView(macPlace: places.search)",
                     "MyStuffView(macPlace: places.myStuff)"] {
            XCTAssertTrue(source.contains(call), "the Mac window no longer passes \(call)")
        }
        // Every other caller keeps today's screens, with no place.
        let tabs = try Self.appSource("Views/MainTabView.swift")
        XCTAssertFalse(tabs.contains("macPlace"))
        for call in ["DiscoverView()", "SearchView()", "MyStuffView()"] {
            XCTAssertTrue(tabs.contains(call), "\(call) left the iPhone/iPad layouts")
        }
    }

    // MARK: - The scroll keeper's decisions

    /// A scroll view being torn down reports offset 0 over an empty document.
    /// Recording it would erase the reader's place on the way out (measured on
    /// macOS 26: every List leave reported exactly that).
    func testATornDownScrollViewNeverOverwritesThePlace() {
        XCTAssertFalse(MacReadingOffset10878.shouldRecord(documentHeight: 0, visibleHeight: 700, restorePending: false))
        XCTAssertFalse(MacReadingOffset10878.shouldRecord(documentHeight: 700, visibleHeight: 700, restorePending: false))
        XCTAssertTrue(MacReadingOffset10878.shouldRecord(documentHeight: 701, visibleHeight: 700, restorePending: false))
    }

    func testNothingIsRecordedOverAPendingRestore() {
        XCTAssertFalse(MacReadingOffset10878.shouldRecord(documentHeight: 10_000, visibleHeight: 700, restorePending: true))
    }

    func testRestoreWaitsForLazyContentThenGoesAsFarAsItCan() {
        typealias R = MacReadingOffset10878
        XCTAssertEqual(R.restore(saved: 4000, documentHeight: 10_000, visibleHeight: 700, attempts: 0), .scroll(to: 4000))
        XCTAssertEqual(R.restore(saved: 4000, documentHeight: 4700, visibleHeight: 700, attempts: 0), .scroll(to: 4000))
        XCTAssertEqual(R.restore(saved: 4000, documentHeight: 3000, visibleHeight: 700, attempts: 0), .wait)
        XCTAssertEqual(R.restore(saved: 4000, documentHeight: 3000, visibleHeight: 700, attempts: R.maxAttempts - 1), .wait)
        XCTAssertEqual(R.restore(saved: 4000, documentHeight: 3000, visibleHeight: 700, attempts: R.maxAttempts), .scroll(to: 2300))
        XCTAssertEqual(R.restore(saved: 4000, documentHeight: 500, visibleHeight: 700, attempts: R.maxAttempts), .nothing)
    }

    /// A List returns to the row the reader was on, wherever that row is laid
    /// out after the remount, plus how far into it they were. With no row (a
    /// ScrollView) or no table to ask, the plain offset is used.
    func testAListReturnsToTheRowNotThePixel() {
        let inRow = MacScrollPlace(offset: 4014, row: 143, offsetInRow: 10)
        XCTAssertEqual(inRow.target(rowTop: 4004), 4014)
        XCTAssertEqual(inRow.target(rowTop: 3990), 4000, "the row moved; the reader goes with it")
        XCTAssertEqual(inRow.target(rowTop: nil), 4014)
        XCTAssertEqual(MacScrollPlace(offset: 4000).target(rowTop: 3990), 4000)
        XCTAssertEqual(MacScrollPlace(offset: 5, row: 0, offsetInRow: -20).target(rowTop: 0), 0)
    }

    func testNoSavedOffsetMeansNoScroll() {
        XCTAssertEqual(MacReadingOffset10878.restore(saved: 0, documentHeight: 10_000, visibleHeight: 700, attempts: 0), .nothing)
    }

    // MARK: - A pending restore and the reader

    /// Control: nobody touches the scroll view while lazy content grows, and the
    /// restore still lands on the saved place once the content can hold it.
    func testAPassiveRestoreWaitsThroughGrowthAndLands() {
        var restoring = MacScrollRestore10878()
        let ticket = restoring.begin(MacScrollPlace(offset: 4000))
        for height: CGFloat in [1500, 3000, 4500] {
            XCTAssertEqual(restoring.step(ticket: ticket, rowTop: nil, documentHeight: height, visibleHeight: 700), .wait)
            XCTAssertTrue(restoring.isPending, "layout alone never ends a restore")
            XCTAssertFalse(MacReadingOffset10878.shouldRecord(documentHeight: height, visibleHeight: 700, restorePending: restoring.isPending),
                           "a layout pass is not recorded as the reader's place")
        }
        XCTAssertEqual(restoring.step(ticket: ticket, rowTop: nil, documentHeight: 6000, visibleHeight: 700), .scroll(to: 4000))
        XCTAssertTrue(restoring.isPending, "still pending while the keeper moves, so the move is not recorded")
        XCTAssertTrue(restoring.end())
        XCTAssertNil(restoring.step(ticket: ticket, rowTop: nil, documentHeight: 6000, visibleHeight: 700), "a landed restore never scrolls again")
    }

    /// The review's case (#10903, P2): the restore is still waiting for content
    /// when the reader scrolls. Their scroll is recorded, and the retry already
    /// queued under the old restore does nothing once the content has grown —
    /// no jump back to the old place.
    func testAReaderScrollDuringAPendingRestoreWinsOverTheQueuedRetry() {
        var restoring = MacScrollRestore10878()
        let ticket = restoring.begin(MacScrollPlace(offset: 4000))
        XCTAssertEqual(restoring.step(ticket: ticket, rowTop: nil, documentHeight: 1500, visibleHeight: 700), .wait,
                       "control — the restore is waiting, so a retry is queued")

        XCTAssertTrue(restoring.end(), "the reader's scroll ends the waiting restore")
        XCTAssertTrue(MacReadingOffset10878.shouldRecord(documentHeight: 1500, visibleHeight: 700, restorePending: restoring.isPending),
                      "the reader's scroll is recorded")

        XCTAssertNil(restoring.step(ticket: ticket, rowTop: nil, documentHeight: 10_000, visibleHeight: 700),
                     "the queued retry would have pulled the reader back to 4000")
        XCTAssertFalse(restoring.end(), "a second scroll finds nothing waiting")
    }

    /// Leave and return while a restore waits: the new visit restores the place
    /// recorded since, and retries queued during the earlier visit neither move
    /// the reader nor use up the new restore's patience.
    func testRetriesFromAnEarlierVisitCannotTouchTheNewRestore() {
        var restoring = MacScrollRestore10878()
        let first = restoring.begin(MacScrollPlace(offset: 4000))
        XCTAssertEqual(restoring.step(ticket: first, rowTop: nil, documentHeight: 1500, visibleHeight: 700), .wait)
        restoring.end()                                        // left the window
        let second = restoring.begin(MacScrollPlace(offset: 3000))   // back, with a newer place
        XCTAssertNotEqual(first, second)

        for _ in 0...MacReadingOffset10878.maxAttempts {
            XCTAssertNil(restoring.step(ticket: first, rowTop: nil, documentHeight: 1500, visibleHeight: 700))
        }
        XCTAssertEqual(restoring.step(ticket: second, rowTop: nil, documentHeight: 1500, visibleHeight: 700), .wait,
                       "stale retries spent the new restore's attempts and it gave up early")
        XCTAssertEqual(restoring.step(ticket: second, rowTop: nil, documentHeight: 5000, visibleHeight: 700), .scroll(to: 3000))
    }

    /// A restore that begins over one still waiting starts with its own full
    /// patience, not the old one's spent attempts.
    func testANewRestoreReplacesOneStillWaiting() {
        var restoring = MacScrollRestore10878()
        let old = restoring.begin(MacScrollPlace(offset: 4000))
        for _ in 0..<MacReadingOffset10878.maxAttempts {
            XCTAssertEqual(restoring.step(ticket: old, rowTop: nil, documentHeight: 1500, visibleHeight: 700), .wait)
        }
        let new = restoring.begin(MacScrollPlace(offset: 3000))
        XCTAssertEqual(restoring.step(ticket: new, rowTop: nil, documentHeight: 1500, visibleHeight: 700), .wait)
        XCTAssertNil(restoring.step(ticket: old, rowTop: nil, documentHeight: 10_000, visibleHeight: 700))
    }

    /// The row anchor still decides where a List restore lands.
    func testAPendingListRestoreLandsOnItsRow() {
        var restoring = MacScrollRestore10878()
        let ticket = restoring.begin(MacScrollPlace(offset: 4014, row: 143, offsetInRow: 10))
        XCTAssertEqual(restoring.step(ticket: ticket, rowTop: 3990, documentHeight: 10_000, visibleHeight: 700), .scroll(to: 4000))
    }

    /// A screen with no saved place ends its restore on the first pass, so
    /// recording starts at once.
    func testANothingRestoreEndsAtOnce() {
        var restoring = MacScrollRestore10878()
        let ticket = restoring.begin(MacScrollPlace())
        XCTAssertEqual(restoring.step(ticket: ticket, rowTop: nil, documentHeight: 10_000, visibleHeight: 700), .nothing)
        XCTAssertFalse(restoring.isPending)
    }

    // MARK: - Mounted: the real Search screen

    /// Leave Search for another screen and come back: the query and the results
    /// are still there, because the screen remounted on the kept model.
    func testSearchKeepsItsQueryAndResultsAcrossALeaveAndReturn() async throws {
        let place = MacReadingState10878().places(for: "reader-1").search
        let answer = try Self.searchAnswer("patriots")
        let model = place.models(orMake: { SearchViewModel(searchFetch: { _, _ in answer }) })
        let host = MountHost { SearchView(macPlace: place).environmentObject(NavigationCoordinator()) }
        defer { host.close() }

        await host.mount(true)
        model.query = "patriots"
        await model.search()
        XCTAssertEqual(model.results?.query, "patriots", "control: the search answered")

        await host.settle()
        XCTAssertEqual(host.textFieldValues(), ["patriots"], "control: the field shows the query")

        await host.mount(false)   // to another screen
        XCTAssertEqual(host.textFieldValues(), [], "control: the screen really left")
        await host.mount(true)    // and back

        // Read from the REMOUNTED screen, not from the test's own reference.
        XCTAssertEqual(host.textFieldValues(), ["patriots"], "the returned screen lost the query")
        XCTAssertTrue(place.models === model)
        XCTAssertEqual(model.results?.query, "patriots")
    }

    /// The detail the reader had open is open again when they come back, and
    /// with no detail kept the screen opens on its own root. (The path a reader
    /// builds by tapping is written back by the same `onChange` on all three
    /// screens; the Mac runtime check walks that by hand.)
    func testSearchReopensTheDetailTheReaderHadOpen() async throws {
        let place = MacReadingState10878().places(for: "reader-1").search
        let answer = try Self.searchAnswer("patriots")
        let model = place.models(orMake: { SearchViewModel(searchFetch: { _, _ in answer }) })
        model.query = "patriots"
        let host = MountHost { SearchView(macPlace: place).environmentObject(NavigationCoordinator()) }
        defer { host.close() }

        place.path.append(Route.about)
        await host.mount(true)
        XCTAssertEqual(host.textFieldValues(), [], "the kept detail did not reopen over the results")
        await host.mount(false)

        place.path = NavigationPath()
        await host.mount(true)
        XCTAssertEqual(host.textFieldValues(), ["patriots"], "control: with no detail kept, the root shows")
    }

    /// Keeping the model must not keep its work: leaving still runs the screen's
    /// own `onDisappear`, which stops the search in flight, so an answer that
    /// lands after the reader left is not published. Run twice — the second
    /// leave is from the REMOUNTED screen, which proves that screen holds the
    /// kept model (its `onDisappear` acts on it).
    func testLeavingSearchStillStopsTheKeptModelsWork() async throws {
        let place = MacReadingState10878().places(for: "reader-1").search
        let gate = SearchGate()
        let model = place.models(orMake: { SearchViewModel(searchFetch: { query, _ in try await gate.answer(for: query) }) })
        let host = MountHost { SearchView(macPlace: place).environmentObject(NavigationCoordinator()) }
        defer { host.close() }
        let answer = try Self.searchAnswer("patriots")

        await host.mount(true)
        model.query = "patriots"
        for round in ["first mount", "remount"] {
            let search = Task { await model.search() }
            await gate.waitForRequest()
            XCTAssertTrue(model.loading, "\(round): control — the search is in flight")
            await host.mount(false)
            XCTAssertFalse(model.loading, "\(round): leaving did not stop the search")
            gate.release(with: answer)
            await search.value
            XCTAssertNil(model.results, "\(round): an answer that landed after the reader left was published")
            XCTAssertEqual(model.query, "patriots", "\(round): what they typed is kept")
            await host.mount(true)
        }

        // Control: on screen, the same late answer does publish.
        let search = Task { await model.search() }
        await gate.waitForRequest()
        gate.release(with: answer)
        await search.value
        XCTAssertEqual(model.results?.query, "patriots")
    }

    #if os(macOS)
    // MARK: - Mounted on a Mac: the scroll keeper

    /// The keeper's AppKit half, on both containers the reading screens use:
    /// Search's results and My Stuff's feed are Lists, Discover is a lazy
    /// ScrollView. Scroll, leave, return — the reader is where they were.
    /// Compiled only on macOS (this target runs on iOS today).
    func testTheMacKeeperPutsTheReaderBackInAListAndAScrollView() async throws {
        for useList in [true, false] {
            let kind = useList ? "List" : "ScrollView"
            let place = MacReadingPlace<SearchViewModel>()
            let host = MountHost { KeeperScreen(useList: useList, place: place) }
            defer { host.close() }

            await host.mount(true)
            let scroll = try XCTUnwrap(host.largestScrollView(), "\(kind): no scroll view")
            scroll.contentView.scroll(to: NSPoint(x: 0, y: 4000))
            scroll.reflectScrolledClipView(scroll.contentView)
            await host.settle()
            // Where the reader actually is: a List's clip view may move the
            // request a little.
            let reading = scroll.contentView.bounds.origin.y
            XCTAssertGreaterThan(reading, 3000, "\(kind): control — the scroll happened")
            XCTAssertEqual(place.scrollPlace.offset, reading, accuracy: 1, "\(kind): the keeper did not record the offset")
            XCTAssertEqual(place.scrollPlace.row != nil, useList, "\(kind): a List is anchored by row, a ScrollView by offset")

            for trip in 1...2 {
                await host.mount(false)
                XCTAssertEqual(place.scrollPlace.offset, reading, accuracy: 1, "\(kind) trip \(trip): leaving overwrote the reader's place")
                await host.mount(true)

                let returned = try XCTUnwrap(host.largestScrollView(), "\(kind): no scroll view after return")
                XCTAssertFalse(returned === scroll, "\(kind): control — the screen really remounted")
                // Exactly where they were, on every trip — no creep.
                XCTAssertEqual(returned.contentView.bounds.origin.y, reading, accuracy: 1, "\(kind) trip \(trip): the reader was not put back")
            }
        }
    }

    /// The review's case, mounted: a restore is waiting for lazy content to
    /// grow, and the reader scrolls before it can land. Their scroll wins — the
    /// content then grows well past the old place and nothing pulls them back.
    /// The control is the same mount with no scroll, where the restore still
    /// lands. The scroll is announced the way AppKit announces a trackpad or
    /// scroller scroll (`willStartLiveScroll`); a real wheel and trackpad on a
    /// Mac stay in the interactive acceptance.
    func testAReaderWhoScrollsDuringAPendingRestoreStaysWhereTheyScrolled() async throws {
        for useList in [true, false] {
            for readerScrolls in [false, true] {
                let kind = "\(useList ? "List" : "ScrollView"), \(readerScrolls ? "reader scrolls" : "control")"
                let place = MacReadingPlace<SearchViewModel>()
                place.scrollPlace = useList ? MacScrollPlace(offset: 4000, row: 120, offsetInRow: 10) : MacScrollPlace(offset: 4000)
                let rows = GrowingRows(count: 60)
                let host = MountHost { GrowingKeeperScreen(useList: useList, rows: rows, place: place) }
                defer { host.close() }

                await host.mount(true)
                let scroll = try XCTUnwrap(host.largestScrollView(), "\(kind): no scroll view")
                XCTAssertLessThanOrEqual(scroll.contentView.bounds.origin.y, 1, "\(kind): control — the restore is still waiting for content")

                if readerScrolls {
                    NotificationCenter.default.post(name: NSScrollView.willStartLiveScrollNotification, object: scroll)
                    scroll.contentView.scroll(to: NSPoint(x: 0, y: 600))
                    scroll.reflectScrolledClipView(scroll.contentView)
                    NotificationCenter.default.post(name: NSScrollView.didEndLiveScrollNotification, object: scroll)
                    await host.settle()
                }
                let reading = scroll.contentView.bounds.origin.y

                rows.count = 400
                // Past every retry the restore had left.
                for _ in 0..<5 { await host.settle() }
                XCTAssertGreaterThan(scroll.documentView?.frame.height ?? 0, 6000, "\(kind): control — the content grew past the old place")
                let now = scroll.contentView.bounds.origin.y

                if readerScrolls {
                    XCTAssertGreaterThan(reading, 300, "\(kind): control — the reader's scroll happened")
                    XCTAssertEqual(now, reading, accuracy: 1, "\(kind): a queued retry pulled the reader back")
                    XCTAssertEqual(place.scrollPlace.offset, reading, accuracy: 1, "\(kind): the reader's scroll was not recorded")
                } else {
                    let landing: CGFloat
                    if useList, let table = scroll.documentView as? NSTableView {
                        landing = table.rect(ofRow: 120).minY + 10
                    } else {
                        landing = 4000
                    }
                    XCTAssertEqual(now, landing, accuracy: 1, "\(kind): the restore did not land once the content could hold it")
                }
            }
        }
    }

    /// A screen with nothing kept opens at the top.
    func testTheMacKeeperLeavesAFreshScreenAtTheTop() async throws {
        let place = MacReadingPlace<SearchViewModel>()
        let host = MountHost { KeeperScreen(useList: true, place: place) }
        defer { host.close() }
        await host.mount(true)
        let scroll = try XCTUnwrap(host.largestScrollView())
        XCTAssertLessThanOrEqual(scroll.contentView.bounds.origin.y, 1)
    }
    #endif

    // MARK: - Helpers

    private static func searchAnswer(_ query: String) throws -> SearchResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchResponse.self, from: Data(#"{"query":"\#(query)","results":[],"futures":[]}"#.utf8))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        return try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }
}

@MainActor
private final class Tally {
    var count = 0
}

/// A first load that holds until the test opens it.
@MainActor
private final class LoadGate {
    private var waiters: [CheckedContinuation<Void, Never>] = []
    private var isOpen = false

    func wait() async {
        guard !isOpen else { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func waitUntilWaiting() async {
        while waiters.isEmpty { await Task.yield() }
    }

    func open() {
        isOpen = true
        let resuming = waiters
        waiters = []
        resuming.forEach { $0.resume() }
    }
}

/// A search transport that holds each request until the test answers it.
@MainActor
private final class SearchGate {
    private var waiting: CheckedContinuation<SearchResponse, Error>?

    func answer(for query: String) async throws -> SearchResponse {
        try await withCheckedThrowingContinuation { waiting = $0 }
    }

    func waitForRequest() async {
        while waiting == nil { await Task.yield() }
    }

    func release(with response: SearchResponse) {
        let continuation = waiting
        waiting = nil
        continuation?.resume(returning: response)
    }
}

/// Mounts a screen the way the Mac window's detail switch does: one hosting
/// view whose content is either the screen or nothing.
@MainActor
private final class MountHost {
    private final class Switch: ObservableObject {
        @Published var mounted = false
    }

    private struct Conditional<Screen: View>: View {
        @ObservedObject var toggle: Switch
        let screen: () -> Screen
        var body: some View {
            if toggle.mounted { screen() } else { Color.clear }
        }
    }

    private let toggle = Switch()
    #if os(macOS)
    private let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1000, height: 800),
                                  styleMask: [.titled], backing: .buffered, defer: false)
    #else
    /// Scene-backed, like the other hosted rigs that read what the page draws
    /// (`EventPublicationCaller4974Tests.MountedPage`): a `UIWindow(frame:)`
    /// belongs to no window scene, so nothing in it is on screen. Made by the
    /// first `mount`, which can wait for the host app's scene.
    private var window: UIWindow?
    private var previousKeyWindow: UIWindow?
    private var rootController: UIViewController?
    private var sceneMissing = false
    #endif

    init<Screen: View>(_ screen: @escaping () -> Screen) {
        let root = Conditional(toggle: toggle, screen: screen)
        #if os(macOS)
        window.contentView = NSHostingView(rootView: root)
        window.orderFrontRegardless()
        #else
        rootController = hostForMeasurement(root)
        #endif
    }

    func mount(_ mounted: Bool) async {
        #if !os(macOS)
        await attachToActiveScene()
        #endif
        toggle.mounted = mounted
        await settle()
    }

    #if !os(macOS)
    /// Shows the hosting controller in a window of the foreground-active scene,
    /// waiting for the host app to activate as the sibling rigs do. With no
    /// such scene the test FAILS here, by name — it is never skipped and the
    /// screen is never mounted scene-less.
    private func attachToActiveScene() async {
        guard window == nil, !sceneMissing else { return }
        let deadline = CACurrentMediaTime() + 10
        func activeScene() -> UIWindowScene? {
            UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive }
        }
        while activeScene() == nil && CACurrentMediaTime() < deadline {
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        guard let scene = activeScene() else {
            let sceneStates = UIApplication.shared.connectedScenes.map {
                "\(type(of: $0)):\($0.activationState.rawValue)"
            }.sorted().joined(separator: ", ")
            XCTFail("MountHost requires a foreground-active window scene; connected scenes: \(sceneStates)")
            sceneMissing = true
            return
        }
        previousKeyWindow = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene)
        window.frame = CGRect(x: 0, y: 0, width: 1000, height: 800)
        window.rootViewController = rootController
        window.makeKeyAndVisible()
        self.window = window
    }
    #endif

    /// Lets SwiftUI apply a change and run appear/disappear.
    func settle() async {
        for _ in 0..<10 {
            try? await Task.sleep(nanoseconds: 30_000_000)
        }
    }

    /// What every text field in the window holds — the Search field is the only
    /// one these screens draw, so this reads what the MOUNTED screen shows.
    func textFieldValues() -> [String] {
        #if os(macOS)
        guard let root = window.contentView else { return [] }
        return Self.descendants(of: root).compactMap { ($0 as? NSTextField).flatMap { $0.isEditable ? $0.stringValue : nil } }
        #else
        guard let window else { return [] }
        return Self.descendants(of: window).compactMap { ($0 as? UITextField)?.text }
        #endif
    }

    #if os(macOS)
    /// The tallest scroll view in the window: the screen's own, not the window
    /// chrome's.
    func largestScrollView() -> NSScrollView? {
        guard let root = window.contentView else { return nil }
        return Self.descendants(of: root).compactMap { $0 as? NSScrollView }
            .max { ($0.documentView?.frame.height ?? 0) < ($1.documentView?.frame.height ?? 0) }
    }

    private static func descendants(of view: NSView) -> [NSView] {
        [view] + view.subviews.flatMap { descendants(of: $0) }
    }
    #else
    private static func descendants(of view: UIView) -> [UIView] {
        [view] + view.subviews.flatMap { descendants(of: $0) }
    }
    #endif

    func close() {
        toggle.mounted = false
        #if os(macOS)
        window.orderOut(nil)
        #else
        window?.isHidden = true
        previousKeyWindow?.makeKey()
        #endif
    }
}

#if os(macOS)
/// A long List or lazy ScrollView carrying the real `macReadingOffset` keeper —
/// the two containers the reading screens put it on.
private struct KeeperScreen: View {
    let useList: Bool
    let place: MacReadingPlace<SearchViewModel>

    var body: some View {
        if useList {
            List(0..<400, id: \.self) { Text("row \($0)").frame(height: 30) }
                .macReadingOffset(place)
        } else {
            ScrollView {
                LazyVStack { ForEach(0..<400, id: \.self) { Text("row \($0)").frame(height: 30) } }
            }
            .macReadingOffset(place)
        }
    }
}

/// Rows a test adds while the screen is mounted, standing in for lazy content
/// that arrives after the screen appears.
private final class GrowingRows: ObservableObject {
    @Published var count: Int
    init(count: Int) { self.count = count }
}

/// `KeeperScreen` whose row count the test grows while a restore waits.
private struct GrowingKeeperScreen: View {
    let useList: Bool
    @ObservedObject var rows: GrowingRows
    let place: MacReadingPlace<SearchViewModel>

    var body: some View {
        if useList {
            List(0..<rows.count, id: \.self) { Text("row \($0)").frame(height: 30) }
                .macReadingOffset(place)
        } else {
            ScrollView {
                LazyVStack { ForEach(0..<rows.count, id: \.self) { Text("row \($0)").frame(height: 30) } }
            }
            .macReadingOffset(place)
        }
    }
}
#endif
