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
        // lane1b H1: the bookmark passes its store's real state, not a constant.
        let button = try String(contentsOf: Self.appDir.appendingPathComponent("Components/PinButton.swift"),
                                encoding: .utf8)
        XCTAssertTrue(button.contains("pinLoadState: pinManager.loadState,"),
                      "the pin tip no longer sees the pin store's load state")
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
}
