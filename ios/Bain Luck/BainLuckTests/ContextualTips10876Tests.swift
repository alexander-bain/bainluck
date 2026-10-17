import XCTest
@testable import Bain_Luck

/// #10876 — the contextual tips' transitions, without TipKit or a render.
/// Each test names the clause it would catch if that clause were deleted.
final class ContextualTips10876Tests: XCTestCase {

    // MARK: - One tip at a time

    func testTheFirstRequestIsGrantedAndASecondWaits() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), chart = UUID()
        queue.request(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        XCTAssertTrue(queue.isGranted(anchor: pin))
        XCTAssertFalse(queue.isGranted(anchor: chart), "two tips on screen at once")
    }

    func testALowerTipWaitsForAHigherControlOnScreenToDecide() {
        var queue = ContextualTipQueue10876()
        let live = UUID(), chart = UUID()
        queue.arrive(anchor: live, tip: .followLive)
        queue.arrive(anchor: chart, tip: .exploreChart)
        queue.request(anchor: chart, tip: .exploreChart)
        XCTAssertNil(queue.holder, "the chart tip won a race the live tip outranks")
        queue.request(anchor: live, tip: .followLive)
        XCTAssertTrue(queue.isGranted(anchor: live), "priority: follow live first")
    }

    func testAHigherControlThatDeclinesReleasesTheLowerTip() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), chart = UUID()
        queue.arrive(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        XCTAssertNil(queue.holder)
        queue.decline(anchor: pin)
        XCTAssertTrue(queue.isGranted(anchor: chart), "a declined tip kept holding the screen")
    }

    func testAHigherControlThatLeavesUndecidedReleasesTheLowerTip() {
        var queue = ContextualTipQueue10876()
        let live = UUID(), chart = UUID()
        queue.arrive(anchor: live, tip: .followLive)
        queue.request(anchor: chart, tip: .exploreChart)
        queue.withdraw(anchor: live)
        XCTAssertTrue(queue.isGranted(anchor: chart))
    }

    func testAHigherPriorityArrivalNeverYanksTheTipOnScreen() {
        var queue = ContextualTipQueue10876()
        let chart = UUID(), live = UUID()
        queue.request(anchor: chart, tip: .exploreChart)
        queue.arrive(anchor: live, tip: .followLive)
        queue.request(anchor: live, tip: .followLive)
        XCTAssertTrue(queue.isGranted(anchor: chart), "the grant must be sticky")
        XCTAssertFalse(queue.isGranted(anchor: live))
    }

    func testAKindAlreadyShownThisSessionCanReturnButNoOtherKindFollowsIt() {
        var queue = ContextualTipQueue10876()
        let pinOnFirstPage = UUID(), chart = UUID(), pinOnSecondPage = UUID()
        queue.request(anchor: pinOnFirstPage, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        queue.withdraw(anchor: pinOnFirstPage)
        XCTAssertNil(queue.holder, "a different tip followed the first in one session")
        queue.request(anchor: pinOnSecondPage, tip: .pin)
        XCTAssertTrue(queue.isGranted(anchor: pinOnSecondPage), "the same tip may reappear on its control")
        XCTAssertEqual(queue.sessionTip, .pin)
    }

    func testClosingTheTipOnScreenDoesNotHandTheScreenToAnotherKind() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), chart = UUID()
        queue.request(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        // The reader closes the pin tip: TipKit stops saying it should display.
        queue.decline(anchor: pin)
        XCTAssertNil(queue.holder, "one tip closed, the next popped straight up")
    }

    func testAmongWaitersOfOneKindTheEarlierRequestIsGranted() {
        var queue = ContextualTipQueue10876()
        let holder = UUID(), first = UUID(), second = UUID()
        queue.request(anchor: holder, tip: .pin)
        queue.request(anchor: first, tip: .pin)
        queue.request(anchor: second, tip: .pin)
        queue.withdraw(anchor: holder)
        XCTAssertTrue(queue.isGranted(anchor: first))
    }

    func testPriorityOrdersFollowLiveThenPinThenChart() {
        XCTAssertLessThan(ContextualTipID10876.followLive, .pin)
        XCTAssertLessThan(ContextualTipID10876.pin, .exploreChart)
        var queue = ContextualTipQueue10876()
        let live = UUID(), pin = UUID(), chart = UUID()
        queue.arrive(anchor: live, tip: .followLive)
        queue.arrive(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        queue.request(anchor: pin, tip: .pin)
        XCTAssertNil(queue.holder, "pin granted while follow live was undecided")
        queue.decline(anchor: live)
        XCTAssertTrue(queue.isGranted(anchor: pin), "pin outranks the chart")
    }

    func testARepeatedRequestFromTheSameAnchorIsOneRequest() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), other = UUID()
        queue.request(anchor: pin, tip: .pin)
        queue.request(anchor: pin, tip: .pin)
        queue.request(anchor: other, tip: .pin)
        queue.withdraw(anchor: pin)
        XCTAssertTrue(queue.isGranted(anchor: other), "a duplicate entry would have taken the grant")
        queue.withdraw(anchor: other)
        XCTAssertNil(queue.holder, "a duplicate entry survived its anchor's withdrawal")
    }

    func testAWithdrawnWaiterIsNeverGranted() {
        var queue = ContextualTipQueue10876()
        let holder = UUID(), gone = UUID()
        queue.request(anchor: holder, tip: .pin)
        queue.request(anchor: gone, tip: .pin)
        queue.withdraw(anchor: gone)
        queue.withdraw(anchor: holder)
        XCTAssertNil(queue.holder, "a control that left the screen received a tip")
    }

    // MARK: - A tip waiting on its page (case v6, D1)

    /// Native's case v6 (B, test0): R2 withdrew the pin anchor while the hero
    /// was on screen, the chart tip was granted at load as the session's kind,
    /// and the pin tip never showed after the hero left.
    func testATipWaitingOnlyOnTheHeroKeepsTheLowerTipBack() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), chart = UUID()
        queue.arrive(anchor: pin, tip: .pin)
        queue.arrive(anchor: chart, tip: .exploreChart)
        queue.park(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        XCTAssertNil(queue.holder, "the chart tip took the screen while the pin tip waited only on the hero")
        XCTAssertNil(queue.sessionTip, "the chart tip took the session while the pin tip waited only on the hero")
        queue.request(anchor: pin, tip: .pin)
        XCTAssertTrue(queue.isGranted(anchor: pin), "control: the hero left, the pin tip is granted")
        XCTAssertEqual(queue.sessionTip, .pin)
    }

    func testAParkedTipIsNeverOnScreen() {
        var queue = ContextualTipQueue10876()
        let pin = UUID()
        queue.park(anchor: pin, tip: .pin)
        XCTAssertNil(queue.holder, "a tip opened over the hero it was waiting on")
        queue.request(anchor: pin, tip: .pin)
        XCTAssertTrue(queue.isGranted(anchor: pin), "control: requesting after parking is granted")
    }

    func testAParkedTipThatDeclinesOrLeavesReleasesTheLowerTip() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), chart = UUID()
        queue.park(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        XCTAssertNil(queue.holder)
        queue.decline(anchor: pin)
        XCTAssertTrue(queue.isGranted(anchor: chart), "a parked tip TipKit stopped wanting kept holding the chart")

        var left = ContextualTipQueue10876()
        left.park(anchor: pin, tip: .pin)
        left.request(anchor: chart, tip: .exploreChart)
        left.withdraw(anchor: pin)
        XCTAssertTrue(left.isGranted(anchor: chart), "a parked tip whose page left kept holding the chart")
    }

    /// The reader scrolls the hero back under a tip on screen: it leaves, and
    /// no other kind takes the screen in its place.
    func testATipOnScreenParksWhenTheHeroReturnsAndKeepsTheSession() {
        var queue = ContextualTipQueue10876()
        let pin = UUID(), chart = UUID()
        queue.request(anchor: pin, tip: .pin)
        queue.request(anchor: chart, tip: .exploreChart)
        queue.park(anchor: pin, tip: .pin)
        XCTAssertNil(queue.holder, "the pin tip stayed open over the returning hero")
        XCTAssertEqual(queue.sessionTip, .pin)
        queue.request(anchor: pin, tip: .pin)
        XCTAssertTrue(queue.isGranted(anchor: pin), "the hero left again: the same tip returns")
    }

    /// A requesting tip held back by a higher undecided one, when the hero
    /// returns, must not be granted over it once the higher one declines.
    func testAWaitingRequestParksWhenThePageCannotShowIt() {
        var queue = ContextualTipQueue10876()
        let live = UUID(), pin = UUID(), chart = UUID()
        queue.arrive(anchor: live, tip: .followLive)
        queue.request(anchor: pin, tip: .pin)
        XCTAssertNil(queue.holder)
        queue.pageCannotShow(anchor: pin, tip: .pin)
        queue.decline(anchor: live)
        XCTAssertNil(queue.holder, "the pin tip was granted over the hero that had just come back")
        queue.pageCannotShow(anchor: chart, tip: .exploreChart)
        queue.decline(anchor: chart)
        queue.request(anchor: pin, tip: .pin)
        XCTAssertTrue(queue.isGranted(anchor: pin), "control: the hero left again")

        var onScreen = ContextualTipQueue10876()
        onScreen.request(anchor: pin, tip: .pin)
        onScreen.pageCannotShow(anchor: pin, tip: .pin)
        XCTAssertNil(onScreen.holder, "the tip on screen stayed open over the returning hero")
        onScreen.request(anchor: chart, tip: .exploreChart)
        XCTAssertNil(onScreen.holder, "another kind took the screen the pin tip left")
    }

    /// Parking does not outrank a HIGHER tip: follow live still goes first.
    func testAParkedTipHoldsBackOnlyLowerTips() {
        var queue = ContextualTipQueue10876()
        let live = UUID(), pin = UUID()
        queue.park(anchor: pin, tip: .pin)
        queue.request(anchor: live, tip: .followLive)
        XCTAssertTrue(queue.isGranted(anchor: live), "a parked pin tip held back the higher follow-live tip")
    }

    // MARK: - App-level suppression

    func testNoTipWhileTheSceneIsInactiveOrThePermissionAlertIsStillToCome() {
        let e = ContextualTipEligibility10876.self
        XCTAssertTrue(e.appCanShowTips(sceneIsActive: true, notificationPromptSettled: true), "control")
        XCTAssertFalse(e.appCanShowTips(sceneIsActive: false, notificationPromptSettled: true),
                       "a tip during a system alert or sheet")
        XCTAssertFalse(e.appCanShowTips(sceneIsActive: true, notificationPromptSettled: false),
                       "a tip that the permission alert, still to come, could land on")
    }

    func testThePermissionAlertIsSettledOnceAnsweredOrSuppressed() {
        let e = ContextualTipEligibility10876.self
        XCTAssertFalse(e.notificationPromptSettled(authorizationIsNotDetermined: true, promptSuppressed: false),
                       "undetermined and not suppressed: the alert is still coming")
        XCTAssertTrue(e.notificationPromptSettled(authorizationIsNotDetermined: false, promptSuppressed: false),
                      "answered (allowed, denied, provisional)")
        XCTAssertTrue(e.notificationPromptSettled(authorizationIsNotDetermined: true, promptSuppressed: true),
                      "the launch argument means it never comes")
    }

    func testTheAskWaitsOnThePermissionStatusNotOnAClock() throws {
        let tips = try String(contentsOf: Self.tipsSource, encoding: .utf8)
        let rules = try String(contentsOf: Self.rulesSource, encoding: .utf8)
        XCTAssertTrue(tips.contains("notificationSettings().authorizationStatus"))
        XCTAssertTrue(tips.contains("NotificationManager.shouldRequestPermission()"),
                      "the suppression launch argument is the manager's own, not a copy")
        // lane1b H1: the anchor must pass the LIVE read into the gate, not a literal.
        XCTAssertTrue(tips.contains("let promptSettled = await ContextualTips10876.notificationPromptSettled()"),
                      "the anchor no longer reads the permission status")
        XCTAssertTrue(tips.contains("notificationPromptSettled: promptSettled) else {"),
                      "the gate no longer receives the status the anchor read")
        for source in [tips, rules] {
            XCTAssertFalse(source.contains("launchGrace"), "a launch-relative grace cannot promise to follow loadPins()")
            XCTAssertFalse(source.contains("kinfo_proc"), "kernel start time includes iOS prewarm")
        }
    }

    // MARK: - Pin

    private func pinUsable(isDetailAnchor: Bool = true, isPinned: Bool = false, isSaving: Bool = false,
                           canPin: Bool = true, load: PinLoadState = .loaded, message: Bool = false) -> Bool {
        ContextualTipEligibility10876.pinUsable(
            isDetailAnchor: isDetailAnchor, isPinned: isPinned, isSaving: isSaving, canPin: canPin,
            pinLoadState: load, isShowingPinMessage: message)
    }

    func testPinIsTaughtOnlyWhereATapWouldPin() {
        XCTAssertTrue(pinUsable(), "control: every clause satisfied")
        XCTAssertFalse(pinUsable(isDetailAnchor: false), "taught on a list or card bookmark")
        XCTAssertFalse(pinUsable(isPinned: true), "taught on something already pinned")
        XCTAssertFalse(pinUsable(isSaving: true), "taught while a save is in flight")
        XCTAssertFalse(pinUsable(canPin: false), "taught at the pin limit, where a tap refuses")
        XCTAssertFalse(pinUsable(message: true), "taught over a pin message, alert or sheet")
    }

    /// `PinManager.togglePin` refuses an add on a signed-in account unless its
    /// pins are `.loaded`; `.local` is signed out, where adds always go through.
    func testPinIsTaughtInEveryLoadStateWhereAnAddGoesThroughAndNoOther() {
        XCTAssertTrue(pinUsable(load: .local), "signed out: a tap pins locally")
        XCTAssertTrue(pinUsable(load: .loaded), "signed in, pins restored")
        XCTAssertFalse(pinUsable(load: .loading), "taught while the account's pins restore")
        XCTAssertFalse(pinUsable(load: .failed),
                       "taught where the tap answers \"Refresh your saved pins\" (pin load failed)")
    }

    func testThePinLoadStateGateMirrorsTheAddRefusal() throws {
        let manager = try String(contentsOf: Self.appDir.appendingPathComponent("Services/PinManager.swift"),
                                 encoding: .utf8)
        XCTAssertTrue(manager.contains("binding.userID != nil, loadState != .loaded {"),
                      "togglePin's add refusal changed; re-derive pinStoreAcceptsAdds")
        // lane1b H1: the tip reads its store's real state, not a constant.
        let tips = try String(contentsOf: Self.tipsSource, encoding: .utf8)
        XCTAssertTrue(tips.contains("canPin: canPin(type: type), loadState: loadState,"),
                      "the pin tip no longer sees the pin store's limit or load state")
        XCTAssertTrue(tips.contains("hasPinMessage: feedback != nil, savedPinCount: savedPins.count)"))
        XCTAssertTrue(tips.contains("isPinned: isPinned(type: type, id: id), isSaving: isSaving(type: type, id: id),"))
        XCTAssertTrue(tips.contains("read: { pinManager.pinTipReading10876(type: type, id: id) })"))
    }

    // MARK: - Pin: the bookmark's wiring

    private let freeSlot = PinTipStoreReading10876(isPinned: false, isSaving: false, canPin: true,
                                                   loadState: .loaded, hasPinMessage: false, savedPinCount: 0)

    private func pinTip(_ store: PinTipStoreReading10876, localPinUIShowing: Bool = false) -> PinTipState10876 {
        ContextualTipEligibility10876.pinTip(isDetailAnchor: true, localPinUIShowing: localPinUIShowing) { store }
    }

    /// lane1b: list and card bookmarks must not read the pin store at all.
    func testACompactBookmarkNeverReadsThePinStore() throws {
        var reads = 0
        let compact = ContextualTipEligibility10876.pinTip(isDetailAnchor: false, localPinUIShowing: false) {
            reads += 1
            return freeSlot
        }
        XCTAssertEqual(compact, .off)
        XCTAssertEqual(reads, 0, "a list or card bookmark read the pin store")
        let detail = ContextualTipEligibility10876.pinTip(isDetailAnchor: true, localPinUIShowing: false) {
            reads += 1
            return freeSlot
        }
        XCTAssertEqual(detail, PinTipState10876(usable: true, learned: false), "control: a free detail bookmark")
        XCTAssertEqual(reads, 1, "a detail bookmark reads the store once")
        let button = try String(contentsOf: Self.pinButtonSource, encoding: .utf8)
        XCTAssertTrue(button.contains(".pinTip10876(isDetailAnchor: !compact, pinManager: pinManager,"),
                      "the bookmark no longer marks only its full-size form as the detail anchor")
    }

    func testThePinTipCarriesEveryStoreClauseIntoTheRule() {
        XCTAssertTrue(pinTip(freeSlot).usable, "control: every clause satisfied")
        var store = freeSlot
        store.isPinned = true
        XCTAssertFalse(pinTip(store).usable, "taught on something already pinned")
        store = freeSlot
        store.isSaving = true
        XCTAssertFalse(pinTip(store).usable, "taught while a save is in flight")
        store = freeSlot
        store.canPin = false
        XCTAssertFalse(pinTip(store).usable, "taught at the pin limit, where a tap refuses")
        store = freeSlot
        store.loadState = .failed
        XCTAssertFalse(pinTip(store).usable, "taught where the tap answers \"Refresh your saved pins\"")
        store = freeSlot
        store.hasPinMessage = true
        XCTAssertFalse(pinTip(store).usable, "taught over a pin message")
        XCTAssertFalse(pinTip(freeSlot, localPinUIShowing: true).usable,
                       "taught over the button's own limit alert or Manage pins sheet")
        XCTAssertFalse(pinTip(freeSlot).learned)
        store = freeSlot
        store.savedPinCount = 1
        XCTAssertTrue(pinTip(store).learned, "anything pinned means pinning is learned")
    }

    // MARK: - The hero no tip may cover

    func testTheHeroIsClearOnlyOnceWhollyScrolledOut() {
        let e = ContextualTipEligibility10876.self
        XCTAssertFalse(e.heroClearOfTips(heroBottom: nil), "a hero never measured opened a tip")
        XCTAssertFalse(e.heroClearOfTips(heroBottom: 420), "hero on screen")
        XCTAssertFalse(e.heroClearOfTips(heroBottom: 0.5), "half a point of hero still showed under the bar")
        XCTAssertTrue(e.heroClearOfTips(heroBottom: 0), "control: bottom edge at the top")
        XCTAssertTrue(e.heroClearOfTips(heroBottom: -300), "control: scrolled well past")
    }

    /// v7 testA frame: one swipe took the hero AND the chart off the top.
    func testATipInsideThePageNeedsTheHeroGoneAndItsOwnControlOnScreen() {
        let e = ContextualTipEligibility10876.self
        XCTAssertTrue(e.pageControlPresentable(heroClear: true, controlOnScreen: true), "control")
        XCTAssertFalse(e.pageControlPresentable(heroClear: false, controlOnScreen: true), "a tip opened over the hero")
        XCTAssertFalse(e.pageControlPresentable(heroClear: true, controlOnScreen: false),
                       "a tip opened pointing at a control scrolled off the screen")
    }

    /// The hero gates whether the page can take the tip, not whether the pin
    /// control is usable — so a pin tip waiting on the hero parks (D1).
    func testThePinTipsUsabilityHasNoHeroClause() throws {
        XCTAssertEqual(pinTip(freeSlot), PinTipState10876(usable: true, learned: false),
                       "control: a free detail bookmark is usable wherever the page is scrolled")
        let rules = Self.withoutCommentLines(try String(contentsOf: Self.rulesSource, encoding: .utf8))
        let pinTipStart = try XCTUnwrap(rules.range(of: "static func pinTip("))
        let pinTipEnd = try XCTUnwrap(rules.range(of: "static func heroClearOfTips(", range: pinTipStart.upperBound..<rules.endIndex))
        XCTAssertFalse(rules[pinTipStart.lowerBound..<pinTipEnd.lowerBound].contains("heroClear"),
                       "the hero came back into the pin control's usability")
    }

    /// The bookmark, the chart and the hero must use ONE key per page, or the
    /// gate is never clear (tip never shows) or clear for the wrong page. The
    /// hero is measured in the ScrollView's own named space (case v6, D2:
    /// the system `.scrollView` space never cleared on the market page).
    func testBothDetailPagesReportTheirHeroUnderTheBookmarksKey() throws {
        let pages: [(file: String, pin: String, hero: String)] = [
            ("Views/EventDetailView.swift", "PinButton(type: \"event\", id: eventId)",
             ".contextualTipHero10876(type: \"event\", id: eventId, scrollSpace: Self.scrollSpace)"),
            ("Views/FuturesDetailView.swift", "PinButton(type: \"future\", id: marketId)",
             ".contextualTipHero10876(type: \"future\", id: marketId, scrollSpace: Self.scrollSpace)"),
        ]
        for page in pages {
            let code = Self.withoutCommentLines(try String(contentsOf: Self.appDir.appendingPathComponent(page.file),
                                                           encoding: .utf8))
            XCTAssertEqual(code.components(separatedBy: page.pin).count - 1, 1, "\(page.file): the bookmark moved")
            XCTAssertEqual(code.components(separatedBy: page.hero).count - 1, 1,
                           "\(page.file): the hero no longer reports to the tips under the bookmark's key")
            let hero = try XCTUnwrap(code.range(of: page.hero))
            let heroSection = try XCTUnwrap(code.range(of: "heroSection(", options: .backwards,
                                                       range: code.startIndex..<hero.lowerBound))
            XCTAssertLessThan(code.distance(from: heroSection.upperBound, to: hero.lowerBound), 900,
                              "\(page.file): the reporter is not on the hero itself")
            XCTAssertEqual(code.components(separatedBy: ".coordinateSpace(name: Self.scrollSpace)").count - 1, 1,
                           "\(page.file): the ScrollView no longer carries the space the hero is measured in")
            let space = try XCTUnwrap(code.range(of: ".coordinateSpace(name: Self.scrollSpace)"))
            let scroll = try XCTUnwrap(code.range(of: "ScrollView {", options: .backwards,
                                                  range: code.startIndex..<hero.lowerBound))
            XCTAssertLessThan(scroll.upperBound, space.lowerBound, "\(page.file): the space is not on the hero's ScrollView")
        }
        let tips = Self.withoutCommentLines(try String(contentsOf: Self.tipsSource, encoding: .utf8))
        XCTAssertTrue(tips.contains("heroClearOfTips(heroBottom: proxy.frame(in: .named(scrollSpace)).maxY)"),
                      "the hero is no longer measured in its page's named scroll space")
        XCTAssertFalse(tips.contains("in: .scrollView)"), "back on the space that never cleared the market page (D2)")
        XCTAssertTrue(tips.contains(".onDisappear { ContextualTipHeroGate10876.shared.set(type: type, id: id, clear: false) }"),
                      "a page that leaves stays marked clear")
        XCTAssertTrue(tips.contains("presentable: heroes.isClear(type: type, id: id),"),
                      "the bookmark's tip no longer waits on the hero gate")
        XCTAssertEqual(tips.components(separatedBy: "heroClear: heroes.isClear(type: \"event\", id: eventId), controlOnScreen: onScreen),").count - 1, 2,
                      "the chart's or follow-live's tip no longer waits on the event page's hero and its own control (C-3a: the chart tip covered the hero at AX3)")
        XCTAssertEqual(tips.components(separatedBy: ".modifier(PageControlOnScreen10876(kind: ").count - 1, 2,
                      "the chart or Start Live Activity no longer reports whether it is on screen")
        XCTAssertTrue(tips.contains("@State private var onScreen = false"), "an unreported control reads as on screen")
        XCTAssertFalse(tips.contains("presentable: true"), "a tip opens whatever the hero is doing")
        let control = try String(contentsOf: Self.appDir.appendingPathComponent("Components/GameActivityControl.swift"),
                                 encoding: .utf8)
        XCTAssertTrue(control.contains(".followLiveTip10876(\n                                eventId: snapshot.eventID,"),
                      "Start Live Activity no longer keys its tip by its event")
        let chart = try String(contentsOf: Self.appDir.appendingPathComponent("Components/OddsChartView.swift"),
                               encoding: .utf8)
        XCTAssertTrue(chart.contains(".exploreChartTip10876(eventId: eventId, touchSurfaceInstalled: scrubSurfaces,"),
                      "the chart no longer keys its tip by its event")
    }

    /// D1's wiring: a usable control whose page cannot take the tip PARKS on
    /// TipKit's yes rather than requesting or withdrawing; a granted tip parks
    /// when the hero returns.
    func testAnAnchorWaitingOnItsPageParksInsteadOfWithdrawing() throws {
        let tips = Self.withoutCommentLines(try String(contentsOf: Self.tipsSource, encoding: .utf8))
        XCTAssertTrue(tips.contains(".task(id: Ask(wantsTip: wantsTip, presentable: presentable))"),
                      "the anchor no longer re-asks when its page becomes able to take the tip")
        XCTAssertTrue(tips.contains("if shouldDisplay && presentable {"), "a tip requests the screen over its hero")
        XCTAssertTrue(tips.contains("} else if shouldDisplay {\n                        queue.park(anchor, tip: kind)"),
                      "a tip TipKit would show, waiting on its hero, no longer parks")
        XCTAssertTrue(tips.contains("} else {\n                    queue.pageCannotShow(anchor, tip: kind)"),
                      "a tip on screen stays open when the hero comes back")
        let wantsTip = try XCTUnwrap(tips.range(of: "private var wantsTip: Bool {"))
        let wantsEnd = try XCTUnwrap(tips.range(of: "}", range: wantsTip.upperBound..<tips.endIndex))
        XCTAssertFalse(tips[wantsTip.upperBound..<wantsEnd.lowerBound].contains("presentable"),
                       "the hero went back into wantsTip, so a waiting tip withdraws again (D1)")
    }

    /// Native's combined v3 (C-3b): at AX3 the system style clipped the
    /// message's last line inside its own popover.
    func testEveryPopoverTipUsesTheStyleThatGivesItsTextFullHeight() throws {
        let tips = Self.withoutCommentLines(try String(contentsOf: Self.tipsSource, encoding: .utf8))
        XCTAssertEqual(tips.components(separatedBy: ".popoverTip(").count - 1, 1, "a second popover site appeared")
        let flat = tips.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        XCTAssertTrue(flat.contains(
            "Color.clear.popoverTip(tip, arrowEdge: arrowEdge) .tipViewStyle(ContextualTipStyle10876())"),
                      "the popover lost the tips' own style")
        let body = try XCTUnwrap(tips.range(of: "private struct ContextualTipBody10876"))
        let rest = String(tips[body.lowerBound...])
        XCTAssertTrue(rest.contains("message.font(.subheadline)"), "the style no longer draws the message")
        XCTAssertTrue(rest.contains(".fixedSize(horizontal: false, vertical: true)"),
                      "the tip's text no longer claims its full height")
        XCTAssertTrue(rest.contains("dynamicTypeSize.isAccessibilitySize"),
                      "at accessibility sizes the icon no longer leaves the text its width")
        XCTAssertTrue(rest.contains("configuration.tip.invalidate(reason: .tipClosed)"), "the close button closes nothing")
        XCTAssertTrue(rest.contains(".frame(width: 44, height: 44)"), "the close target fell under 44 pt")
        XCTAssertTrue(rest.contains(".accessibilityLabel(\"Close\")"), "VoiceOver lost the close button's name")
    }

    /// #9495 keeps any limit read out of the bookmark; the tip's read lives in
    /// Tips/. This closes the wrappers `canPin(` alone would not catch.
    func testTheBookmarkReadsNoPinLimitEvenThroughAWrapper() throws {
        let button = Self.codeOnly(try String(contentsOf: Self.pinButtonSource, encoding: .utf8))
        for name in ["canPin", "maxPinsPerType", "pinTipReading10876", "PinTipStoreReading10876", "pinUsable"] {
            XCTAssertFalse(Self.identifiers(in: button).contains(name), "PinButton reads the pin limit via \(name)")
        }
    }

    /// The limit toast exists only if every tap reaches `togglePin`. Parsed,
    /// not substring-matched: inside the `Button {` … `} label:` action the call
    /// is a statement of the action's own body, with no branch or exit before it.
    func testEveryPinTapReachesTogglePinUnconditionally() throws {
        let code = Self.codeOnly(try String(contentsOf: Self.pinButtonSource, encoding: .utf8))
        let call = "pinManager.togglePin(type: type, id: id)"
        let action = try XCTUnwrap(Self.buttonAction(in: code), "no `Button {` … `} label:` action in PinButton")
        XCTAssertEqual(action.components(separatedBy: call).count, 2, "togglePin must be called exactly once in the action")
        let before = try XCTUnwrap(action.components(separatedBy: call).first)
        for (open, close) in [("{", "}"), ("(", ")"), ("[", "]")] {
            XCTAssertEqual(before.filter { String($0) == open }.count, before.filter { String($0) == close }.count,
                           "togglePin sits inside a nested \(open)…\(close), not the action's own body")
        }
        XCTAssertEqual(before.components(separatedBy: "#if").count, before.components(separatedBy: "#endif").count,
                       "togglePin sits inside a #if … #endif, so some builds compile the tap out")
        let statementStart = before.reversed().first { $0 != " " && $0 != "\t" }
        XCTAssertTrue(statementStart == nil || statementStart == "\n" || statementStart == ";",
                      "togglePin is not its own statement (an operand of \(String(describing: statementStart)))")
        let flow: Set<String> = ["if", "guard", "return", "switch", "while", "for", "repeat", "throw", "defer",
                                 "do", "catch", "else", "case", "break", "continue", "fallthrough"]
        let found = Self.identifiers(in: before).filter(flow.contains)
        XCTAssertTrue(found.isEmpty, "control flow before togglePin: \(found)")
    }

    /// Source without its whole-line comments, for guards that must read a
    /// string literal (`codeOnly` blanks them).
    private static func withoutCommentLines(_ source: String) -> String {
        source.split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// Source with comments and string-literal contents blanked, so a guard
    /// reads code, not prose.
    private static func codeOnly(_ source: String) -> String {
        var out = ""
        var chars = Array(source)[...]
        while let c = chars.first {
            if chars.starts(with: "//") {
                while let d = chars.first, d != "\n" { chars.removeFirst(); out.append(d == "\t" ? "\t" : " ") }
            } else if chars.starts(with: "/*") {
                while !chars.isEmpty, !chars.starts(with: "*/") { out.append(chars.removeFirst() == "\n" ? "\n" : " ") }
                if !chars.isEmpty { chars.removeFirst(2); out.append("  ") }
            } else if c == "\"" {
                out.append(chars.removeFirst())
                while let d = chars.first, d != "\"", d != "\n" {
                    chars.removeFirst()
                    out.append(" ")
                    if d == "\\", !chars.isEmpty { chars.removeFirst(); out.append(" ") }
                }
                if let d = chars.first, d == "\"" { out.append(chars.removeFirst()) }
            } else {
                out.append(chars.removeFirst())
            }
        }
        return out
    }

    /// Word tokens, minus compiler directives (`#if os(iOS)` is not a branch).
    private static func identifiers(in code: String) -> [String] {
        var words: [String] = []
        var current = ""
        var directive = false
        for c in code + " " {
            if c.isLetter || c.isNumber || c == "_" {
                current.append(c)
            } else {
                if !current.isEmpty, !directive { words.append(current) }
                current = ""
                directive = c == "#"
            }
        }
        return words
    }

    /// The body of the first `Button {` closure, if its closing brace is
    /// followed by `label:`.
    private static func buttonAction(in code: String) -> String? {
        guard let start = code.range(of: "Button {") else { return nil }
        var depth = 0
        var index = code.index(before: start.upperBound)
        let bodyStart = start.upperBound
        while index < code.endIndex {
            if code[index] == "{" { depth += 1 }
            if code[index] == "}" {
                depth -= 1
                if depth == 0 {
                    let rest = code[code.index(after: index)...].drop { $0 == " " }
                    return rest.hasPrefix("label:") ? String(code[bodyStart..<index]) : nil
                }
            }
            index = code.index(after: index)
        }
        return nil
    }

    // MARK: - Pin engagement

    private let d0 = Date(timeIntervalSince1970: 1_790_000_000)

    func testOneEngagementAfterTenForegroundSeconds() {
        var dwell = PinDwell10876()
        dwell.sceneChanged(isActive: true, now: d0)
        XCTAssertFalse(dwell.donateIfDue(now: d0.addingTimeInterval(9.9)), "donated before the dwell")
        XCTAssertTrue(dwell.donateIfDue(now: d0.addingTimeInterval(10)), "control: a full dwell donates")
    }

    func testLeavingTheForegroundRestartsTheDwell() {
        var dwell = PinDwell10876()
        dwell.sceneChanged(isActive: true, now: d0)
        dwell.sceneChanged(isActive: false, now: d0.addingTimeInterval(7))
        XCTAssertNil(dwell.dueDate)
        dwell.sceneChanged(isActive: true, now: d0.addingTimeInterval(8))
        XCTAssertFalse(dwell.donateIfDue(now: d0.addingTimeInterval(12)), "7 s + 4 s counted as one dwell")
        XCTAssertTrue(dwell.donateIfDue(now: d0.addingTimeInterval(18)))
    }

    /// lane1b R3: the permission alert (or a trip to the background) took the
    /// scene inactive and back, and the old `.task(id:)` donated again.
    func testInactiveThenActiveThenTenSecondsGivesNoSecondDonation() {
        var dwell = PinDwell10876()
        dwell.sceneChanged(isActive: true, now: d0)
        XCTAssertTrue(dwell.donateIfDue(now: d0.addingTimeInterval(10)))
        dwell.sceneChanged(isActive: false, now: d0.addingTimeInterval(11))
        dwell.sceneChanged(isActive: true, now: d0.addingTimeInterval(12))
        XCTAssertNil(dwell.dueDate, "a second dwell was scheduled on the same page")
        XCTAssertFalse(dwell.donateIfDue(now: d0.addingTimeInterval(30)), "one visit counted twice")
    }

    func testARepeatedActiveSignalDoesNotRestartTheDwell() {
        var dwell = PinDwell10876()
        dwell.sceneChanged(isActive: true, now: d0)
        dwell.sceneChanged(isActive: true, now: d0.addingTimeInterval(5))
        XCTAssertTrue(dwell.donateIfDue(now: d0.addingTimeInterval(10)))
        XCTAssertFalse(dwell.donateIfDue(now: d0.addingTimeInterval(20)), "donated twice from one dwell")
    }

    func testTheEngagementModifierKeepsOneDwellPerPage() throws {
        let tips = try String(contentsOf: Self.tipsSource, encoding: .utf8)
        XCTAssertTrue(tips.contains("@State private var dwell = PinDwell10876()"))
        XCTAssertTrue(tips.contains("dwell.donateIfDue(now: Date())"), "the donation no longer passes through the dwell")
        XCTAssertTrue(tips.contains(".onDisappear { dwell.sceneChanged(isActive: false, now: Date()) }"),
                      "leaving the page must stop the clock and keep `donated`")
    }

    func testAnythingPinnedMeansPinningIsLearned() {
        XCTAssertFalse(ContextualTipEligibility10876.pinLearned(savedPinCount: 0))
        XCTAssertTrue(ContextualTipEligibility10876.pinLearned(savedPinCount: 1))
    }

    func testThePinRuleWaitsForTwoEngagedVisitsOfTenSeconds() {
        // The rule macro holds a literal; this pins the constants it mirrors.
        XCTAssertEqual(ContextualTipEligibility10876.pinEngagementsBeforeTip, 2)
        XCTAssertEqual(ContextualTipEligibility10876.pinDwell, 10)
        let source = try? String(contentsOf: Self.tipsSource, encoding: .utf8)
        XCTAssertTrue(source?.contains("#Rule(Self.engaged) { $0.donations.count >= 2 }") == true,
                      "the pin rule no longer matches pinEngagementsBeforeTip")
    }

    // MARK: - Follow live

    private func followUsable(shown: Bool = true, enabled: Bool = true, live: Bool = true,
                              busy: Bool = false, active: Int = 0, scene: Bool = true) -> Bool {
        ContextualTipEligibility10876.followLiveUsable(
            controlShown: shown, activitiesEnabled: enabled, gameIsLive: live,
            isBusy: busy, activeActivityCount: active, sceneIsActive: scene)
    }

    func testFollowLiveIsTaughtOnlyWhileStartLiveActivityIsShownAndTappable() {
        XCTAssertTrue(followUsable(), "control: every clause satisfied")
        XCTAssertFalse(followUsable(shown: false), "taught where the control is hidden (iPad, Mac, finished)")
        XCTAssertFalse(followUsable(enabled: false), "taught with Live Activities off or unsupported")
        XCTAssertFalse(followUsable(live: false), "taught on a game that is not live")
        XCTAssertFalse(followUsable(busy: true), "taught while the control is disabled")
        XCTAssertFalse(followUsable(active: 1), "taught while another game's activity disables Start")
        XCTAssertFalse(followUsable(scene: false), "taught while the app is not in front")
    }

    func testARunningLiveActivityMeansFollowingIsLearned() {
        XCTAssertFalse(ContextualTipEligibility10876.followLiveLearned(activeActivityCount: 0))
        XCTAssertTrue(ContextualTipEligibility10876.followLiveLearned(activeActivityCount: 1))
    }

    // MARK: - Explore the chart

    private let t0 = Date(timeIntervalSince1970: 1_790_000_000)

    func testTheChartTipNeedsThreeMomentsSpanningAMinute() {
        let e = ContextualTipEligibility10876.self
        XCTAssertFalse(e.chartHasUsefulData([]), "empty chart")
        XCTAssertFalse(e.chartHasUsefulData([t0, t0.addingTimeInterval(120)]), "two moments")
        XCTAssertFalse(e.chartHasUsefulData([t0, t0.addingTimeInterval(30), t0.addingTimeInterval(59)]),
                       "three moments inside a minute")
        XCTAssertFalse(e.chartHasUsefulData([t0, t0, t0, t0.addingTimeInterval(600)]),
                       "repeated instants counted as moments")
        XCTAssertTrue(e.chartHasUsefulData([t0, t0.addingTimeInterval(30), t0.addingTimeInterval(60)]))
    }

    func testTheChartTipIsNeverTaughtToVoiceOverOrWithoutTheTouchSurface() {
        let useful = [t0, t0.addingTimeInterval(60), t0.addingTimeInterval(120)]
        let e = ContextualTipEligibility10876.self
        XCTAssertTrue(e.exploreChartUsable(touchSurfaceInstalled: true, voiceOverRunning: false,
                                           primaryLineDates: useful), "control")
        XCTAssertFalse(e.exploreChartUsable(touchSurfaceInstalled: false, voiceOverRunning: false,
                                            primaryLineDates: useful), "no touch surface (raster, Mac)")
        XCTAssertFalse(e.exploreChartUsable(touchSurfaceInstalled: true, voiceOverRunning: true,
                                            primaryLineDates: useful), "a touch gesture taught to VoiceOver")
        XCTAssertFalse(e.exploreChartUsable(touchSurfaceInstalled: true, voiceOverRunning: false,
                                            primaryLineDates: [t0]), "an empty or one-point chart")
    }

    // MARK: - Test-only reset

    func testTheLaunchSwitchIsInertUnlessPassed() throws {
        let suite = "ContextualTips10876Tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let key = ContextualTipLaunchOption10876.key
        XCTAssertEqual(ContextualTipLaunchOption10876.read(defaults: defaults), .normal)
        defaults.set("reset", forKey: key)
        XCTAssertEqual(ContextualTipLaunchOption10876.read(defaults: defaults), .reset)
        defaults.set(" Hidden ", forKey: key)
        XCTAssertEqual(ContextualTipLaunchOption10876.read(defaults: defaults), .hidden)
        defaults.set("YES", forKey: key)
        XCTAssertEqual(ContextualTipLaunchOption10876.read(defaults: defaults), .normal,
                       "an unknown value must not reset anyone's tips")
    }

    func testTheResetClearsTipKitOnlyAndUITestsHideTips() throws {
        let tips = try String(contentsOf: Self.tipsSource, encoding: .utf8)
        // The reset path touches TipKit's datastore and nothing else.
        XCTAssertTrue(tips.contains("try Tips.resetDatastore()"))
        XCTAssertFalse(tips.contains("removePersistentDomain"), "the reset reached UserDefaults")
        XCTAssertFalse(tips.contains("Tips.showAllTipsForTesting"), "a test switch that bypasses the rules")
        let launch = try String(contentsOf: Self.projectDir.appendingPathComponent("BainLuckUITests/UITestLaunch.swift"),
                                encoding: .utf8)
        XCTAssertTrue(launch.contains("\"-contextual_tips_10876\", \"hidden\""),
                      "UI journeys can have a tip popover eat their taps")
    }

    // MARK: - Copy names the real controls

    func testTheTipsNameTheControlsTheyExplain() throws {
        let tips = try String(contentsOf: Self.tipsSource, encoding: .utf8)
        let control = try String(contentsOf: Self.appDir.appendingPathComponent("Components/GameActivityControl.swift"),
                                 encoding: .utf8)
        XCTAssertTrue(control.contains("compactAction(\"Start Live Activity\""), "the control was renamed")
        XCTAssertTrue(tips.contains("Text(\"Start Live Activity to keep"), "the tip no longer names the control")
        XCTAssertTrue(tips.contains("It updates while this game is open."),
                      "the tip must not promise more than the control's own update note")
        XCTAssertTrue(tips.contains("Tap the bookmark"), "the pin tip must name the bookmark it points at")
        let quoted = tips.split(separator: "\"").enumerated().filter { $0.offset % 2 == 1 }.map(\.element)
        XCTAssertFalse(quoted.contains { $0.localizedCaseInsensitiveContains("question") },
                       "\"question\" is not the product's noun (#10877)")
    }

    // MARK: - Paths

    private static var projectDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
    }
    private static var appDir: URL { projectDir.appendingPathComponent("Bain Luck") }
    private static var tipsSource: URL { appDir.appendingPathComponent("Tips/ContextualTips10876.swift") }
    private static var rulesSource: URL { appDir.appendingPathComponent("Tips/ContextualTipRules10876.swift") }
    private static var pinButtonSource: URL { appDir.appendingPathComponent("Components/PinButton.swift") }
}
