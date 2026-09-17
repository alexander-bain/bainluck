import XCTest

/// Telling "the tap path is broken" from "there was nothing to tap".
///
/// A tap-driven journey test has two ways to not-pass and they mean opposite
/// things. If the feed is empty, a navigation test that reports FAIL is blaming
/// navigation for a data outage; if it reports PASS it is reporting a journey it
/// never walked. Either way the next reader is misled, and the second way is
/// worse because it is silent.
///
/// So the two are separated by construction:
///
///   * the thing under test — the gesture, the push, the pop — is an
///     `XCTAssert`, and a miss is a hard red;
///   * the thing the test needs in order to start — a card on screen, a search
///     result to open — is an `XCTSkip` naming what was missing.
///
/// A skip is not a pass. `xcodebuild` counts it separately and
/// `tools/native-uitest.sh` prints the count, so a run that skipped its way to
/// green cannot be read as a run that walked the journey.
///
/// Check 5 is the deliberate exception and it is the reason this file does not
/// simply skip everywhere: "Discover opens with real cards" IS the check, so an
/// empty feed there is a FAILURE, not a precondition.
enum JourneyPrecondition {

    /// Wait for the app to reach its tab bar, or fail — this one is never a skip.
    ///
    /// Reaching `MainTabView` at all is a property of the app and not of the
    /// data behind it, so there is no outage that excuses it.
    @discardableResult
    static func tabBar(of app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let tabBar = app.tabBars.firstMatch
        XCTAssertTrue(
            tabBar.waitForExistence(timeout: UITestLaunch.launchTimeout),
            "No tab bar \(UITestLaunch.launchTimeout)s after launch — the app never reached MainTabView.",
            file: file, line: line
        )
        return tabBar
    }

    /// Switch to a tab and wait for it to be selected — or fail naming the tab.
    ///
    /// Two rig facts are built in, both measured on 2026-09-14:
    ///
    ///   * `XCUIElement.waitForSelected` (an `XCTNSPredicateExpectation`) missed
    ///     a selection that a plain re-resolve-and-read loop saw immediately, so
    ///     this polls by re-resolving the button each time. Every read is a
    ///     fresh query rather than a re-evaluation of a snapshot.
    ///   * a tap on a tab button occasionally logs `Computed hit point {-1, -1}`
    ///     and lands nowhere, while the app is still mounting its first tab. ONE
    ///     retry covers it. The retry is bounded and counted on purpose: taps
    ///     landing is the premise `CanThisRigTapAtAllTests` exists to assert, and
    ///     a helper that retried forever would quietly hide the day it stops
    ///     being true.
    @discardableResult
    static func openTab(
        _ name: String,
        in app: XCUIApplication,
        file: StaticString = #filePath,
        line: UInt = #line
    ) -> XCUIElement {
        let tabBar = Self.tabBar(of: app, file: file, line: line)
        XCTAssertTrue(
            tabBar.buttons[name].waitForExistence(timeout: 10),
            "No '\(name)' tab. Tabs are Discover/Sports/Browse/Search/My Stuff (MainTabView).",
            file: file, line: line
        )

        for attempt in 1...2 {
            tabBar.buttons[name].tap()
            let deadline = Date().addingTimeInterval(UITestLaunch.contentTimeout / 2)
            while Date() < deadline {
                if tabBar.buttons[name].isSelected { return tabBar }
                Thread.sleep(forTimeInterval: 0.5)
            }
            if attempt == 1 {
                XCTContext.runActivity(named: "retrying the '\(name)' tab tap") { _ in }
            }
        }

        XCTFail(
            "The '\(name)' tab did not become selected after two taps, over \(UITestLaunch.contentTimeout)s.",
            file: file, line: line
        )
        return tabBar
    }

    /// Wait for a query's match count to stop moving, then answer it.
    ///
    /// A feed that is still laying out will accept a gesture and drop it. The
    /// first draft of the swipe test swiped 1.2 seconds after the first card
    /// appeared and the card ignored it; the same swipe seven seconds later
    /// dismissed it every time. That is a rig defect and it reads exactly like
    /// #1773 — a card that silently ignores a swipe — which is the defect the
    /// test exists to catch, so the two must not be confusable.
    @discardableResult
    static func settle(_ query: XCUIElementQuery, timeout: TimeInterval = 20) -> Int {
        var last = -1
        var stableReads = 0
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let now = query.count
            stableReads = (now == last) ? stableReads + 1 : 0
            last = now
            if stableReads >= 2 { return now }
            Thread.sleep(forTimeInterval: 0.75)
        }
        return last
    }

    /// Every Discover card on screen, of any kind.
    ///
    /// `discover-card` is set by `SwipeToDismiss`, which wraps all four card
    /// views, so this counts what the reader can actually see and swipe. Use it
    /// for anything that needs A CARD; use `firstEventCard` only where the
    /// journey needs the card to be a GAME.
    static func cards(in app: XCUIApplication) -> XCUIElementQuery {
        app.descendants(matching: .any).matching(identifier: "discover-card")
    }

    /// The first Discover card of any kind, or a SKIP saying the feed was empty.
    ///
    /// Distinct from `firstEventCard` on purpose, and the distinction is
    /// measured: at 10:25Z on 2026-09-17 the live feed's first 50 items held
    /// **2 events and 48 futures/bundle/tournament cards**. A journey that only
    /// needs something to swipe should not be unrunnable for the hours of the
    /// day when the slate is quiet — that is a property of the fixture list, not
    /// of the app.
    static func firstCard(in app: XCUIApplication) throws -> XCUIElement {
        let card = Self.cards(in: app).firstMatch
        guard card.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            throw XCTSkip(
                "NOT WALKED: Discover drew no card of any kind within \(UITestLaunch.contentTimeout)s, "
                + "so there was nothing to touch. This says nothing about navigation — if the feed is "
                + "really empty it is check 5 failing, so read that test's result, not this skip."
            )
        }
        return card
    }

    // MARK: - The floating tab bar, which draws OVER the scroll content

    /// The floating tab bar's rect, or `.null` if this platform has none.
    ///
    /// iPad draws a `NavigationSplitView` and has no tab bar, so `.null` is a
    /// real answer and every caller below treats it as "nothing is in the way".
    static func tabBarRect(_ app: XCUIApplication) -> CGRect {
        let bar = app.tabBars.firstMatch
        return bar.exists ? bar.frame : .null
    }

    /// The part of the window a finger can actually land in: inside the window,
    /// and above the floating tab bar.
    static func reachableBand(_ app: XCUIApplication) -> CGRect {
        let window = app.frame
        let bar = Self.tabBarRect(app)
        let bottom = bar.isNull ? window.maxY : min(window.maxY, bar.minY)
        return CGRect(
            x: window.minX, y: window.minY,
            width: window.width, height: max(0, bottom - window.minY)
        )
    }

    /// Could a reader actually put a finger on this element right now?
    ///
    /// ⚠️ **`waitForExistence` AND `isHittable` BETWEEN THEM DO NOT ANSWER THIS,
    /// AND THE GAP HAS NOW COST TWO TESTS.** A lazy list MATERIALISES rows past
    /// the fold, so an element well below the window is in the tree and reports
    /// a frame; and MainTabView's tab bar FLOATS over the scroll content, so an
    /// element in the bottom 83pt is covered by a tab button. Measured
    /// 2026-09-17 on iPhone 17 Pro, window 402×874:
    ///
    ///     window   = (0,   0, 402, 874)
    ///     tabBar   = (0, 791, 402,  83)   → reachable band ends at y 791
    ///     age chip = (79.7, 902.3, 58.7, 28)  → BELOW THE WINDOW ENTIRELY
    ///
    /// Two different failures wear one face. `AReaderCanScrollPastTheChartTests`
    /// hit the tab-bar half (a drag posed at `chart.midY` swept the tab bar and
    /// was read as a navigation defect). The price-age chip hunt hit the
    /// off-screen half: it returned the first chip the tree reported, 28pt below
    /// the window, then asserted a reader could tap it and reported "a reader
    /// cannot open the precise stamp at all". The chip was fine; it was one
    /// scroll away.
    ///
    /// The whole frame must be in the band, not just its centre: a chip half
    /// under the tab bar is one a reader stabs at and misses.
    static func isReachable(_ element: XCUIElement, in app: XCUIApplication) -> Bool {
        Self.reachableBand(app).contains(element.frame)
    }

    /// How far the content must rise for `element` to sit inside the band, or 0
    /// if it already does.
    static func liftNeeded(for element: XCUIElement, in app: XCUIApplication) -> CGFloat {
        max(0, element.frame.maxY - Self.reachableBand(app).maxY)
    }

    /// Lift the scrolling content by `distance` points, without a flick.
    ///
    /// `swipeUp()` moves roughly a whole screen and carries momentum, which is
    /// the wrong instrument for "raise this one element clear of the tab bar" —
    /// it routinely carries the specimen off the TOP of the window instead, and
    /// the hunt then reports the chip as absent. A slow press before the drag
    /// suppresses the inertia so the content moves by the distance asked for.
    ///
    /// Absolute window coordinates rather than an element-relative offset: the
    /// normalized form is what produced off-screen destinations in the chart
    /// tests.
    static func liftContent(_ app: XCUIApplication, by distance: CGFloat) {
        let window = app.frame
        // Start in the middle of the window — clear of the tab bar at the bottom
        // and of the navigation bar at the top — and never drag past either.
        let startY = window.midY
        let travel = max(40, min(distance, startY - window.minY - 80))
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: window.midX, dy: startY))
        let finish = origin.withOffset(CGVector(dx: window.midX, dy: startY - travel))
        start.press(forDuration: 0.25, thenDragTo: finish)
    }

    /// The first Discover event card, or a SKIP saying the feed had none.
    ///
    /// `discover-card-event` is set on the card's tap target
    /// (`NativeEventDiscoverCard.tapTargetIdentifier`). Matching on the
    /// identifier rather than on any text inside the card is what keeps a
    /// copy-formatting ship from reddening a navigation test.
    static func firstEventCard(in app: XCUIApplication) throws -> XCUIElement {
        let card = app.descendants(matching: .any)
            .matching(identifier: "discover-card-event")
            .firstMatch
        guard card.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            throw XCTSkip(
                "NOT WALKED: no Discover event card within \(UITestLaunch.contentTimeout)s, so there was nothing to tap. "
                + "This says nothing about navigation. If it is not a transient outage it is check 5 failing — read that test's result, not this skip."
            )
        }
        return card
    }
}
