import SwiftUI
import XCTest
@testable import Bain_Luck
#if canImport(UIKit)
import UIKit
#endif

/// `#13261` Rulings `417: C` (held first-session queue) & `424: A` (three anonymous
/// pre-consent counts + approved usage-stats screen disclosure sentence).
@MainActor
final class Telemetry417CAnd424ATests: XCTestCase {
    private final class SpySink: TelemetrySink {
        var analyticsEnabled: [Bool] = []
        var crashlyticsEnabled: [Bool] = []
        var resetCount = 0

        func setAnalyticsCollectionEnabled(_ enabled: Bool) { analyticsEnabled.append(enabled) }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { crashlyticsEnabled.append(enabled) }
        func resetAnalyticsData() { resetCount += 1 }
    }

    private var sink: SpySink!
    private var captured: [(name: String, params: [String: Any])] = []
    private var isolatedDefaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        sink = SpySink()
        captured = []
        suiteName = "Telemetry417CAnd424ATests.\(UUID().uuidString)"
        isolatedDefaults = UserDefaults(suiteName: suiteName)
        isolatedDefaults.removePersistentDomain(forName: suiteName)

        TelemetryConsent.shared.resetForTests(sink: sink)
        TelemetryConsent.shared.initialize()
        SessionOpenTracker13261.shared.resetForTests()
        AnalyticsService.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params ?? [:]))
        }
    }

    override func tearDown() {
        AnalyticsService.eventEmitterForTests = nil
        SessionOpenTracker13261.shared.resetForTests()
        TelemetryConsent.shared.resetForTests(sink: FirebaseTelemetrySink())
        isolatedDefaults.removePersistentDomain(forName: suiteName)
        isolatedDefaults = nil
        sink = nil
        super.tearDown()
    }

    // MARK: - 417: C (held first-session queue)

    func testNothingSentBeforeAllowThenYesSendsHeldEventsOnceInOrderWithTime() throws {
        XCTAssertTrue(TelemetryConsent.shared.needsChoice)
        XCTAssertFalse(TelemetryConsent.shared.isGranted)

        AnalyticsService.trackScreen(name: "discover", type: "discover")
        AnalyticsService.trackEventCardClick(eventId: 101, sport: "basketball_nba", status: "live")
        AnalyticsService.trackOnboardingComplete(teamsCount: 2)

        // Nothing sent before a yes.
        XCTAssertTrue(captured.isEmpty, "Zero events may emit while choice is unanswered")
        XCTAssertFalse(sink.analyticsEnabled.contains(true))
        XCTAssertEqual(HeldAnalyticsQueue417C.shared.snapshot().count, 3)

        // Answering yes flushes all held events once in exact order, each with occurred_at_epoch.
        TelemetryConsent.shared.set(.analytics)

        XCTAssertEqual(captured.map(\.name), ["screen_view", "event_card_click", "onboarding_complete"])
        for entry in captured {
            let epoch = entry.params["occurred_at_epoch"] as? Int
            XCTAssertNotNil(epoch, "Held event \(entry.name) must carry the time it happened")
            XCTAssertGreaterThan(epoch ?? 0, 1_700_000_000)
        }
        XCTAssertTrue(HeldAnalyticsQueue417C.shared.snapshot().isEmpty)

        // Repeated flush sends nothing more; new post-consent events emit normally.
        AnalyticsService.flushHeldEventsIfConsented()
        XCTAssertEqual(captured.count, 3)

        AnalyticsService.trackScreen(name: "sports", type: "sports")
        XCTAssertEqual(captured.count, 4)
        XCTAssertEqual(captured.last?.name, "screen_view")
        XCTAssertEqual(captured.last?.params["screen_name"] as? String, "sports")
        XCTAssertNil(captured.last?.params["occurred_at_epoch"], "Live post-consent events emit immediately without held marker")
    }

    func testRefusalDeletesHeldEventsAndNeverSendsThemEvenIfLaterRegranted() {
        AnalyticsService.trackScreen(name: "discover", type: "discover")
        AnalyticsService.trackOnboardingStep(step: 1, stepName: "pairs")
        XCTAssertEqual(HeldAnalyticsQueue417C.shared.snapshot().count, 2)
        XCTAssertTrue(captured.isEmpty)

        TelemetryConsent.shared.set(.none)
        XCTAssertTrue(captured.isEmpty)
        XCTAssertTrue(HeldAnalyticsQueue417C.shared.snapshot().isEmpty)

        // Events generated while declined are never queued either.
        AnalyticsService.trackScreen(name: "browse", type: "leagues")
        XCTAssertTrue(HeldAnalyticsQueue417C.shared.snapshot().isEmpty)

        // Later opting in sends zero pre-refusal held events.
        TelemetryConsent.shared.set(.analytics)
        XCTAssertTrue(captured.isEmpty)
    }

    func testQueueCapsAt200EventsDroppingOldestFirst() {
        let base = Date(timeIntervalSince1970: 1_795_600_000)
        let queue = HeldAnalyticsQueue417C(defaults: isolatedDefaults, now: { base })
        queue.recordFirstOpenIfNeeded(now: base)

        for idx in 0..<215 {
            let ok = queue.enqueue(
                event: "pin_item",
                parameters: [
                    "action": "pin",
                    "item_type": "event",
                    "item_id": "\(idx)",
                    "surface": "discover",
                ],
                now: base.addingTimeInterval(TimeInterval(idx))
            )
            XCTAssertTrue(ok)
        }

        let retained = queue.drainForFlush(now: base.addingTimeInterval(300))
        XCTAssertEqual(retained.count, HeldAnalyticsQueue417C.maxEvents)
        XCTAssertEqual(retained.count, 200)
        let ids = retained.compactMap { $0.parameters["item_id"] }.compactMap { val -> String? in
            if case .string(let s) = val { return s }
            return nil
        }
        XCTAssertEqual(ids.first, "15", "Oldest 15 events past cap 200 must be dropped")
        XCTAssertEqual(ids.last, "214")
    }

    func testQueueDeletesHeldEvents30DaysAfterFirstOpenIfUnanswered() {
        let firstOpen = Date(timeIntervalSince1970: 1_795_600_000)
        let queue = HeldAnalyticsQueue417C(defaults: isolatedDefaults, now: { firstOpen })
        queue.recordFirstOpenIfNeeded(now: firstOpen)

        XCTAssertTrue(
            queue.enqueue(
                event: "screen_view",
                parameters: ["screen_name": "discover", "page_type": "discover"],
                now: firstOpen.addingTimeInterval(60)
            )
        )

        // Just before 30 days: still retained.
        let beforeExpiry = firstOpen.addingTimeInterval(30 * 86_400 - 1)
        XCTAssertEqual(queue.snapshot(now: beforeExpiry).count, 1)

        // At 30 days from first open: expired and deleted.
        let atExpiry = firstOpen.addingTimeInterval(30 * 86_400)
        XCTAssertTrue(queue.drainForFlush(now: atExpiry).isEmpty)
        XCTAssertTrue(queue.snapshot(now: atExpiry).isEmpty)
        XCTAssertNil(isolatedDefaults.data(forKey: HeldAnalyticsQueue417C.eventsStorageKey))

        // New enqueue attempts after expiry without an answer stay dropped.
        XCTAssertFalse(
            queue.enqueue(
                event: "screen_view",
                parameters: ["screen_name": "sports", "page_type": "sports"],
                now: atExpiry.addingTimeInterval(60)
            )
        )
    }

    func testHeldQueueEnforcesAnalyticsPrivacyBoundaryBeforeWritingToStorage() throws {
        let queue = HeldAnalyticsQueue417C(defaults: isolatedDefaults)
        // Unknown events are rejected before storage.
        XCTAssertFalse(queue.enqueue(event: "rogue_unlisted_event", parameters: ["email": "a@b.com"]))
        XCTAssertTrue(queue.snapshot().isEmpty)

        // Search + dropped keys are sanitized BEFORE hitting UserDefaults.
        let rawSecretQuery = "Private Search Query alice@example.com"
        XCTAssertTrue(
            queue.enqueue(
                event: "search_result_click",
                parameters: [
                    "query": rawSecretQuery,
                    "search_term": rawSecretQuery,
                    "result_id": 999_888,
                    "result_type": "team",
                    "position": 1,
                    "email": "alice@example.com",
                    "name": "Alice Example",
                    "unexpected_key": "must_drop",
                ]
            )
        )

        let rawStoredBytes = try XCTUnwrap(isolatedDefaults.data(forKey: HeldAnalyticsQueue417C.eventsStorageKey))
        let rawStoredString = try XCTUnwrap(String(data: rawStoredBytes, encoding: .utf8))
        XCTAssertFalse(rawStoredString.contains("Private Search Query"))
        XCTAssertFalse(rawStoredString.contains("alice@example.com"))
        XCTAssertFalse(rawStoredString.contains("999888"))
        XCTAssertFalse(rawStoredString.contains("result_id"))
        XCTAssertFalse(rawStoredString.contains("unexpected_key"))
        XCTAssertFalse(rawStoredString.contains("must_drop"))
        XCTAssertTrue(rawStoredString.contains("query_hash"))
    }

    func testQueuePersistsAcrossAppRestartAndPreservesSessionOpenArrival() throws {
        let t0 = Date(timeIntervalSince1970: 1_795_600_000)
        let queueSession1 = HeldAnalyticsQueue417C(defaults: isolatedDefaults, now: { t0 })
        let tracker = SessionOpenTracker13261(
            isGranted: { TelemetryConsent.shared.isGranted },
            emitSessionOpen: { isFirst, num, entry, screen in
                AnalyticsService.trackSessionOpen(
                    isFirstSession: isFirst,
                    sessionNumber: num,
                    entryType: entry,
                    firstScreen: screen
                )
            },
            emitSharedLinkOpen: { link in
                AnalyticsService.trackSharedLinkOpen(
                    entryType: link.entryType,
                    destinationType: link.destinationType,
                    source: link.source,
                    medium: link.medium
                )
            }
        )
        tracker.recordLaunch(sessionNumber: 1)
        let arrival = try XCTUnwrap(
            FirstWeekTelemetry13261.classifyArrival(
                url: XCTUnwrap(URL(string: "https://bainluck.com/events/42?source=share&medium=copy_link")),
                destinationType: "event",
                firstScreen: "event_detail"
            )
        )
        tracker.recordArrival(arrival)
        tracker.persistPendingToHeldQueueIfUnanswered(
            needsChoice: { TelemetryConsent.shared.needsChoice },
            heldQueue: queueSession1,
            now: t0
        )

        // Simulate Session 2 relaunch reading from the same persistent store.
        let queueSession2 = HeldAnalyticsQueue417C(defaults: isolatedDefaults, now: { t0.addingTimeInterval(3600) })
        XCTAssertEqual(queueSession2.snapshot().map(\.name), ["shared_link_open", "session_open"])

        TelemetryConsent.shared.set(.analytics)
        AnalyticsService.flushHeldEventsIfConsented(queue: queueSession2)
        XCTAssertEqual(captured.map(\.name), ["shared_link_open", "session_open"])
        XCTAssertEqual(captured[0].params["occurred_at_epoch"] as? Int, Int(t0.timeIntervalSince1970))
        XCTAssertEqual(captured[1].params["is_first_session"] as? Bool, true)
        XCTAssertEqual(captured[1].params["session_number"] as? Int, 1)
    }

    // MARK: - 424: A (three isolated anonymous counts + approved sentence)

    func testAnonymousCountsSendAtMostOnceWithClosedThreeKeyPayloadAndZeroConsentEventsWhenDeclined() {
        var sentPayloads: [(payload: [String: String], url: URL)] = []
        let fixedDay = Date(timeIntervalSince1970: 1_795_651_200) // 2026-11-26 UTC
        let tracker = AnonymousLifecycleCounts424A(
            defaults: isolatedDefaults,
            now: { fixedDay },
            appVersionProvider: { "1.0.8 (internal-build)" },
            deliveryAllowed: { true },
            sender: { payload, url, completion in
                sentPayloads.append((payload, url))
                completion(true)
            }
        )

        // Declining usage-stats leaves Consent analytics completely off.
        TelemetryConsent.shared.set(.none)
        AnalyticsService.trackScreen(name: "discover", type: "discover")
        AnalyticsService.trackSearch(query: "Patriots", resultsCount: 3)
        XCTAssertTrue(captured.isEmpty)

        // 1. First open -> sends first_open once; second launch (clean) does NOT resend.
        tracker.handleAppLaunch(isDebuggerAttached: false)
        tracker.markSessionCleanBackgroundOrExit()
        tracker.handleAppLaunch(isDebuggerAttached: false)

        // 2. First-run finished -> sends once; repeated calls are no-ops.
        tracker.recordFirstRunFinished(wasAlreadyOnboarded: false)
        tracker.recordFirstRunFinished(wasAlreadyOnboarded: false)

        // 3. Unclean exit while active on same version -> next launch sends previous_session_crashed once.
        tracker.handleAppLaunch(isDebuggerAttached: false) // active foreground without clean background
        tracker.handleAppLaunch(isDebuggerAttached: false) // noticed at next launch
        // Repeated unclean exit later -> still at most once per install!
        tracker.handleAppLaunch(isDebuggerAttached: false)

        XCTAssertEqual(
            sentPayloads.map { $0.payload["event"] },
            ["first_open", "first_run_finished", "previous_session_crashed"]
        )
        for item in sentPayloads {
            XCTAssertEqual(item.url, AnonymousLifecycleCounts424A.endpointURL)
            XCTAssertEqual(Set(item.payload.keys), ["event", "app_version", "day"])
            XCTAssertEqual(item.payload["app_version"], "1.0.8")
            let day = item.payload["day"] ?? ""
            XCTAssertNotNil(day.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression))
        }
        // Consent analytics stayed completely silent the entire time.
        XCTAssertTrue(captured.isEmpty)
    }

    func testDebuggerAndVersionChangeDoNotFalseReportCrash() {
        var sentEvents: [String] = []
        let tracker = AnonymousLifecycleCounts424A(
            defaults: isolatedDefaults,
            appVersionProvider: { "1.0.8" },
            deliveryAllowed: { true },
            sender: { payload, _, completion in
                if let e = payload["event"] { sentEvents.append(e) }
                completion(true)
            }
        )

        // Launch 1 leaves session active, then debugger launch ignores crash.
        tracker.handleAppLaunch(appVersion: "1.0.8", isDebuggerAttached: false)
        tracker.handleAppLaunch(appVersion: "1.0.8", isDebuggerAttached: true)
        XCTAssertEqual(sentEvents, ["first_open"])

        // Clean background clears active flag, so next non-debugger launch does not emit crash.
        tracker.markSessionCleanBackgroundOrExit()
        tracker.handleAppLaunch(appVersion: "1.0.8", isDebuggerAttached: false)
        XCTAssertEqual(sentEvents, ["first_open"])

        // Active session from prior app version also does not attribute to new version.
        tracker.handleAppLaunch(appVersion: "1.0.9", isDebuggerAttached: false)
        XCTAssertEqual(sentEvents, ["first_open"])
    }

    func testExistingOrUpgradedInstallNeverSendsFirstOpenOrReopenedFirstRunFinished() {
        // Case A: Prior phone already completed setup before upgrading to 1.0.8.
        let suiteA = "Telemetry417C.UpgradeA.\(UUID().uuidString)"
        let defaultsA = UserDefaults(suiteName: suiteA)!
        defaultsA.removePersistentDomain(forName: suiteA)
        defer { defaultsA.removePersistentDomain(forName: suiteA) }
        defaultsA.set(true, forKey: FirstRunStorageKeys212A.onboardedKey)

        var sentA: [String] = []
        let trackerA = AnonymousLifecycleCounts424A(
            defaults: defaultsA,
            appVersionProvider: { "1.0.8" },
            deliveryAllowed: { true },
            sender: { payload, _, completion in
                if let e = payload["event"] { sentA.append(e) }
                completion(true)
            }
        )
        trackerA.handleAppLaunch(isDebuggerAttached: false)
        trackerA.recordFirstRunFinished(wasAlreadyOnboarded: true)
        XCTAssertTrue(sentA.isEmpty, "Upgraded onboarded install must never emit first_open or first_run_finished")

        // Case B: Prior phone had unanswered setup but had already launched before (sessionCount > 0)
        // or had answered the usage prompt.
        let suiteB = "Telemetry417C.UpgradeB.\(UUID().uuidString)"
        let defaultsB = UserDefaults(suiteName: suiteB)!
        defaultsB.removePersistentDomain(forName: suiteB)
        defer { defaultsB.removePersistentDomain(forName: suiteB) }
        defaultsB.set(4, forKey: AnonymousLifecycleCounts424A.sessionCountStorageName)
        defaultsB.set(ConsentLevel.none.rawValue, forKey: TelemetryConsent.storageKey)

        var sentB: [String] = []
        let trackerB = AnonymousLifecycleCounts424A(
            defaults: defaultsB,
            appVersionProvider: { "1.0.8" },
            deliveryAllowed: { true },
            sender: { payload, _, completion in
                if let e = payload["event"] { sentB.append(e) }
                completion(true)
            }
        )
        trackerB.handleAppLaunch(isDebuggerAttached: false)
        XCTAssertTrue(sentB.isEmpty, "Upgraded install with prior sessions/consent must never emit first_open")
    }

    func testFailedDeliveryRetriesNextLaunchMarksSentOnlyOn2xxAndStopsAfterMaxAttempts() {
        var nextSucceeded = false
        var deliveredEvents: [String] = []
        let tracker = AnonymousLifecycleCounts424A(
            defaults: isolatedDefaults,
            appVersionProvider: { "1.0.8" },
            deliveryAllowed: { true },
            sender: { payload, _, completion in
                if let e = payload["event"] { deliveredEvents.append(e) }
                completion(nextSucceeded)
            }
        )

        // Launch 1: 404 / offline -> attempts first_open once, does NOT mark sent.
        tracker.handleAppLaunch(isDebuggerAttached: false)
        tracker.markSessionCleanBackgroundOrExit()
        XCTAssertEqual(deliveredEvents, ["first_open"])

        // Launch 2: 200 OK -> retries first_open and marks sent permanently.
        nextSucceeded = true
        tracker.handleAppLaunch(isDebuggerAttached: false)
        tracker.markSessionCleanBackgroundOrExit()
        XCTAssertEqual(deliveredEvents, ["first_open", "first_open"])

        // Launch 3: already sent -> does NOT resend.
        tracker.handleAppLaunch(isDebuggerAttached: false)
        XCTAssertEqual(deliveredEvents, ["first_open", "first_open"])

        // Now verify bounded retry cap (3 failed attempts for first_run_finished -> stops).
        var setupAttempts = 0
        let retrySuite = "Telemetry417C.RetryCap.\(UUID().uuidString)"
        let retryDefaults = UserDefaults(suiteName: retrySuite)!
        retryDefaults.removePersistentDomain(forName: retrySuite)
        defer { retryDefaults.removePersistentDomain(forName: retrySuite) }

        let capTracker = AnonymousLifecycleCounts424A(
            defaults: retryDefaults,
            appVersionProvider: { "1.0.8" },
            deliveryAllowed: { true },
            sender: { payload, _, completion in
                if payload["event"] == "first_run_finished" {
                    setupAttempts += 1
                    completion(false)
                } else {
                    completion(true)
                }
            }
        )
        capTracker.handleAppLaunch(isDebuggerAttached: false)
        capTracker.markSessionCleanBackgroundOrExit()
        capTracker.recordFirstRunFinished(wasAlreadyOnboarded: false) // attempt 1
        capTracker.handleAppLaunch(isDebuggerAttached: false)        // attempt 2
        capTracker.markSessionCleanBackgroundOrExit()
        capTracker.handleAppLaunch(isDebuggerAttached: false)        // attempt 3
        capTracker.markSessionCleanBackgroundOrExit()
        capTracker.handleAppLaunch(isDebuggerAttached: false)        // capped: must stop
        XCTAssertEqual(setupAttempts, AnonymousLifecycleCounts424A.maxDeliveryAttempts)
    }

    func testDebugAndSimulatorNeverDeliverProductionCounts() {
        XCTAssertFalse(
            AnonymousLifecycleCounts424A.isProductionDeliveryAllowed,
            "Debug and simulator builds must never send counts to production"
        )
        var calls = 0
        let tracker = AnonymousLifecycleCounts424A(
            defaults: isolatedDefaults,
            appVersionProvider: { "1.0.8" },
            sender: { _, _, completion in
                calls += 1
                completion(true)
            }
        )
        tracker.handleAppLaunch(isDebuggerAttached: false)
        tracker.recordFirstRunFinished(wasAlreadyOnboarded: false)
        XCTAssertEqual(calls, 0)
    }

    func testApprovedPrivacyDisclosureSentenceMatchesVerbatimAcrossPromptAndPreferences() throws {
        let expected =
            "Without a yes, the app sends only three anonymous counts: that it was opened for the first time, that setup was finished, and whether it crashed. Nothing in them says who you are."
        XCTAssertEqual(AnonymousLifecycleCounts424A.privacyDisclosureSentence, expected)

        let testFile = URL(fileURLWithPath: #filePath)
        let repoRoot = testFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        let promptSrc = try String(
            contentsOf: repoRoot.appendingPathComponent("ios/Bain Luck/Bain Luck/Components/TelemetryConsentPrompt.swift"),
            encoding: .utf8
        )
        let prefsSrc = try String(
            contentsOf: repoRoot.appendingPathComponent("ios/Bain Luck/Bain Luck/Views/PreferencesView.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(promptSrc.contains("AnonymousLifecycleCounts424A.privacyDisclosureSentence"))
        XCTAssertTrue(promptSrc.contains("ScrollView"))
        XCTAssertTrue(prefsSrc.contains("AnonymousLifecycleCounts424A.privacyDisclosureSentence"))
        XCTAssertFalse(prefsSrc.contains("no usage analytics or crash reports are sent"))
    }

    #if canImport(UIKit)
    func testRenderUsageStatsAndPreferencesPrivacyEvidenceSheets() async throws {
        let outDir = FileManager.default.temporaryDirectory.appendingPathComponent("shots-13261", isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        try await renderCard(
            view: TelemetryConsentPrompt { _ in },
            name: "prompt-390-light",
            width: 390,
            height: 760,
            colorScheme: .light,
            dynamicTypeSize: .large,
            outDir: outDir
        )
        try await renderCard(
            view: TelemetryConsentPrompt { _ in },
            name: "prompt-390-dark",
            width: 390,
            height: 760,
            colorScheme: .dark,
            dynamicTypeSize: .large,
            outDir: outDir
        )
        try await renderCard(
            view: PreferencesView(),
            name: "prefs-privacy-390-light",
            width: 390,
            height: 760,
            colorScheme: .light,
            dynamicTypeSize: .large,
            outDir: outDir
        )
        try await renderCard(
            view: PreferencesView(),
            name: "prefs-privacy-390-dark",
            width: 390,
            height: 760,
            colorScheme: .dark,
            dynamicTypeSize: .large,
            outDir: outDir
        )
    }

    private func renderCard<V: View>(
        view: V,
        name: String,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        outDir: URL
    ) async throws {
        let auth = AuthManager(restoreOnInit: false)
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiCategory: UIContentSizeCategory = dynamicTypeSize == .accessibility5 ? .accessibilityExtraExtraExtraLarge : .large
        let wrapped = NavigationStack {
            view
                .frame(maxWidth: width, maxHeight: .infinity)
        }
        .environmentObject(auth)
        .environment(\.colorScheme, colorScheme)
        .environment(\.dynamicTypeSize, dynamicTypeSize)
        .frame(width: width, height: height)

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        host.view.traitOverrides.preferredContentSizeCategory = uiCategory

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 30_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let pngURL = outDir.appendingPathComponent("\(name).png")
        try XCTUnwrap(image.pngData()).write(to: pngURL)
        print("SHOT_13261_PNG:", pngURL.path)
    }
    #endif
}
