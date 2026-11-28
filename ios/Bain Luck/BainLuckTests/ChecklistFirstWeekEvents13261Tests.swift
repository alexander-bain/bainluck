import SwiftUI
import XCTest
@testable import Bain_Luck
#if canImport(UIKit)
import UIKit
#endif

/// `#13261` + `417: C` — First-run checklist sends first-week setup funnel events
/// (`onboarding_start`, each `onboarding_step`, `follow_team`, and `onboarding_complete` /
/// `onboarding_skip`) at most once per sitting, held on-device under `417: C` until `"Allow"`.
@MainActor
final class ChecklistFirstWeekEvents13261Tests: XCTestCase {
    private final class SpySink: TelemetrySink {
        var analyticsEnabled: [Bool] = []
        var crashlyticsEnabled: [Bool] = []
        var resetCount = 0

        func setAnalyticsCollectionEnabled(_ enabled: Bool) { analyticsEnabled.append(enabled) }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { crashlyticsEnabled.append(enabled) }
        func resetAnalyticsData() { resetCount += 1 }
    }

    private static let checklistEventNames: Set<String> = [
        "onboarding_start",
        "onboarding_step",
        "follow_team",
        "onboarding_complete",
        "onboarding_skip",
    ]

    private var sink: SpySink!
    private var captured: [(name: String, params: [String: Any])] = []
    private var isolatedDefaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        sink = SpySink()
        captured = []
        suiteName = "ChecklistFirstWeekEvents13261Tests.\(UUID().uuidString)"
        isolatedDefaults = UserDefaults(suiteName: suiteName)
        isolatedDefaults.removePersistentDomain(forName: suiteName)

        HeldAnalyticsQueue417C.shared.resetForTests()
        AnonymousLifecycleCounts424A.shared.resetForTests()
        TelemetryConsent.shared.resetForTests(sink: sink)
        TelemetryConsent.shared.initialize()
        AnalyticsService.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params ?? [:]))
        }
    }

    override func tearDown() {
        AnalyticsService.eventEmitterForTests = nil
        TelemetryConsent.shared.resetForTests(sink: FirebaseTelemetrySink())
        HeldAnalyticsQueue417C.shared.resetForTests()
        AnonymousLifecycleCounts424A.shared.resetForTests()
        isolatedDefaults.removePersistentDomain(forName: suiteName)
        isolatedDefaults = nil
        sink = nil
        super.tearDown()
    }

    private var heldChecklistEvents: [HeldAnalyticsEvent417C] {
        HeldAnalyticsQueue417C.shared.snapshot().filter {
            Self.checklistEventNames.contains($0.name)
        }
    }

    private var capturedChecklistEvents: [(name: String, params: [String: Any])] {
        captured.filter { Self.checklistEventNames.contains($0.name) }
    }

    private func makeOfflineChecklistFixture(
        entryPoint: String = "first_launch",
        initialStep: FirstRunChecklistRowID364A? = nil,
        initialRows: Set<FirstRunChecklistRowID364A> = [],
        initialSubjects: [FollowedSubject295A] = []
    ) -> (
        window: UIWindow,
        store: FirstRunChecklistStore364A,
        followManager: FollowManager295A
    ) {
        let store = FirstRunChecklistStore364A(defaults: isolatedDefaults)
        if !initialRows.isEmpty {
            store.state = FirstRunChecklistState364A(
                completedRows: initialRows,
                selectedSetSlugs: [],
                followedCount: initialSubjects.count,
                dismissedFromMyStuff: false
            )
        }
        let followManager = FollowManager295A(defaults: isolatedDefaults, initialSubjects: initialSubjects)
        let pinManager = PinManager(
            defaults: isolatedDefaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )
        let authManager = AuthManager()
        let content = FirstRunChecklistContent364A(
            lookupExamples: [],
            startWithTonight: [],
            discoverSets: [],
            rowPreviews: [:],
            subjectArtByCategory: [:]
        )
        let coordinatorVM = FirstRunChecklistCoordinatorVM364A(
            initialContent: content,
            defaults: isolatedDefaults,
            discoverLoader: { [] },
            sportsLoader: { [] }
        )
        let followVM = FirstRunViewModel212A(
            initialPairs: [],
            initialStep: 3,
            defaults: isolatedDefaults,
            feedLoader: { [] },
            sportsFeedLoader: { [] },
            submitOnboarding: { _ in OnboardingResponse(status: "ok", onboardingCompleted: true) }
        )
        let rootView = FirstRunChecklistRootView364A(
            initialStep: initialStep,
            arrivedHeadline: nil,
            entryPoint: entryPoint,
            initialContent: content,
            coordinatorVM: coordinatorVM,
            followVM: followVM
        )
        .frame(width: 390, height: 844)
        .environment(\.followManager295A, followManager)
        .environment(\.firstRunChecklistStore364A, store)
        .environmentObject(authManager)
        .environmentObject(pinManager)
        .environmentObject(NavigationCoordinator())

        let host = hostForMeasurement(rootView, at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        return (window, store, followManager)
    }

    private func pumpRunLoop(iterations: Int = 6) async {
        for _ in 0..<iterations {
            RunLoop.main.run(until: Date().addingTimeInterval(0.02))
            await Task.yield()
            try? await Task.sleep(nanoseconds: 20_000_000)
        }
    }

    private func waitUntilChecklistHeld(_ predicate: ([HeldAnalyticsEvent417C]) -> Bool) async {
        for _ in 0..<60 {
            if predicate(heldChecklistEvents) {
                return
            }
            RunLoop.main.run(until: Date().addingTimeInterval(0.02))
            await Task.yield()
            try? await Task.sleep(nanoseconds: 25_000_000)
        }
    }

    private func unmount(_ window: UIWindow) async {
        window.isHidden = true
        window.rootViewController = nil
        await pumpRunLoop()
    }

    func testHostedChecklistQueuesEveryEventOnceUnder417CAndSendsOnlyAfterAllow() async throws {
        XCTAssertTrue(TelemetryConsent.shared.needsChoice)
        let (window, store, followManager) = makeOfflineChecklistFixture(entryPoint: "first_launch")
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_start" }) }
        XCTAssertTrue(captured.isEmpty, "Zero events may emit before Allow")
        XCTAssertEqual(heldChecklistEvents.map(\.name), ["onboarding_start"])

        // Follow a team, unfollow & re-follow the same team, plus follow a non-team subject.
        let celtics = FollowedSubject295A.team(
            slug: "boston-celtics",
            teamId: 2,
            name: "Boston Celtics",
            sportKey: "basketball_nba"
        )
        let oscars = FollowedSubject295A.subject(
            slug: "oscars-best-picture",
            name: "Oscars Best Picture",
            affinityCategory: "entertainment"
        )
        _ = followManager.toggle(celtics)
        _ = followManager.toggle(oscars)
        _ = followManager.toggle(celtics) // unfollow
        _ = followManager.toggle(celtics) // refollow same team in same sitting -> no duplicate follow_team
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "follow_team" }) }

        // Complete all five checklist rows (including duplicate markCompleted calls).
        for row in FirstRunChecklistRowID364A.allCases {
            store.markCompleted(row)
            store.markCompleted(row)
        }
        await waitUntilChecklistHeld {
            $0.filter { $0.name == "onboarding_step" }.count == 5
        }

        // Close completed checklist -> triggers .onDisappear -> onboarding_complete once.
        await unmount(window)
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_complete" }) }

        XCTAssertTrue(captured.isEmpty, "Nothing leaves the phone before the usage-stats yes")
        XCTAssertFalse(sink.analyticsEnabled.contains(true))

        let held = heldChecklistEvents
        XCTAssertEqual(
            held.map(\.name),
            [
                "onboarding_start",
                "follow_team",
                "onboarding_step",
                "onboarding_step",
                "onboarding_step",
                "onboarding_step",
                "onboarding_step",
                "onboarding_complete",
            ]
        )

        // Grant usage-stats permission -> all held events flush strictly once in order with occurred_at_epoch.
        TelemetryConsent.shared.set(.analytics)
        let emitted = capturedChecklistEvents
        XCTAssertEqual(
            emitted.map(\.name),
            [
                "onboarding_start",
                "follow_team",
                "onboarding_step",
                "onboarding_step",
                "onboarding_step",
                "onboarding_step",
                "onboarding_step",
                "onboarding_complete",
            ]
        )
        XCTAssertEqual(emitted[0].params["entry_point"] as? String, "first_launch")
        XCTAssertEqual(emitted[1].params["action"] as? String, "follow")
        XCTAssertEqual(emitted[1].params["sport"] as? String, "basketball_nba")
        XCTAssertEqual(emitted[1].params["relation_type"] as? String, "follow")
        XCTAssertEqual(emitted[1].params["surface"] as? String, "onboarding")
        let steps = emitted.filter { $0.name == "onboarding_step" }
        XCTAssertEqual(
            steps.map { $0.params["step_name"] as? String ?? "" },
            ["look_up", "follow", "explore_sets", "sync_devices", "alerts"]
        )
        XCTAssertEqual(steps.map { $0.params["step"] as? Int ?? -1 }, [1, 2, 3, 4, 5])
        XCTAssertEqual(emitted.last?.params["teams_count"] as? Int, 1)
        for entry in emitted {
            XCTAssertNotNil(entry.params["occurred_at_epoch"])
        }

        // Second flush sends nothing more.
        let countAfterFirstFlush = captured.count
        AnalyticsService.flushHeldEventsIfConsented()
        XCTAssertEqual(captured.count, countAfterFirstFlush)
        XCTAssertTrue(HeldAnalyticsQueue417C.shared.snapshot().isEmpty)
    }

    func testHostedUnfinishedChecklistQueuesSkipOnceAndSendsAfterAllow() async throws {
        let (window, store, _) = makeOfflineChecklistFixture(
            entryPoint: "my_stuff_banner",
            initialStep: .lookUp
        )
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_start" }) }
        store.markCompleted(.lookUp)
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_step" }) }
        await unmount(window)
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_skip" }) }

        XCTAssertTrue(captured.isEmpty)
        let held = heldChecklistEvents
        XCTAssertEqual(held.map(\.name), ["onboarding_start", "onboarding_step", "onboarding_skip"])

        TelemetryConsent.shared.set(.analytics)
        let emitted = capturedChecklistEvents
        XCTAssertEqual(emitted.map(\.name), ["onboarding_start", "onboarding_step", "onboarding_skip"])
        XCTAssertEqual(emitted[0].params["entry_point"] as? String, "my_stuff_banner")
        XCTAssertEqual(emitted[1].params["step"] as? Int, 1)
        XCTAssertEqual(emitted[1].params["step_name"] as? String, "look_up")
        XCTAssertEqual(emitted[2].params["last_step_completed"] as? Int, 1)
        XCTAssertEqual(emitted[2].params["last_step_name"] as? String, "look_up")
    }

    func testDecliningConsentDeletesHeldChecklistEventsAndNeverSendsThem() async throws {
        let (window, store, _) = makeOfflineChecklistFixture(entryPoint: "preferences")
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_start" }) }
        store.markCompleted(.lookUp)
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_step" }) }
        await unmount(window)
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_skip" }) }

        XCTAssertEqual(
            heldChecklistEvents.map(\.name),
            ["onboarding_start", "onboarding_step", "onboarding_skip"]
        )
        TelemetryConsent.shared.set(.none)
        XCTAssertTrue(captured.isEmpty)
        XCTAssertTrue(HeldAnalyticsQueue417C.shared.snapshot().isEmpty)

        // Later opting in sends zero pre-refusal checklist events.
        TelemetryConsent.shared.set(.analytics)
        XCTAssertTrue(capturedChecklistEvents.isEmpty)
    }

    func testReopenedChecklistDoesNotReemitPreviouslyDoneRowsOrTeams() async throws {
        let preFollowed = FollowedSubject295A.team(
            slug: "new-england-patriots",
            teamId: 9,
            name: "New England Patriots",
            sportKey: "americanfootball_nfl"
        )
        let (window, store, followManager) = makeOfflineChecklistFixture(
            entryPoint: "preferences",
            initialRows: [.lookUp, .follow],
            initialSubjects: [preFollowed]
        )
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_start" }) }
        store.markCompleted(.exploreSets)
        let bruins = FollowedSubject295A.team(
            slug: "boston-bruins",
            teamId: 12,
            name: "Boston Bruins",
            sportKey: "icehockey_nhl"
        )
        _ = followManager.toggle(bruins)
        await waitUntilChecklistHeld {
            $0.contains(where: { $0.name == "onboarding_step" })
                && $0.contains(where: { $0.name == "follow_team" })
        }
        await unmount(window)
        await waitUntilChecklistHeld { $0.contains(where: { $0.name == "onboarding_skip" }) }

        TelemetryConsent.shared.set(.analytics)
        let emitted = capturedChecklistEvents
        XCTAssertEqual(
            emitted.map(\.name),
            ["onboarding_start", "onboarding_step", "follow_team", "onboarding_skip"]
        )
        XCTAssertEqual(emitted[0].params["entry_point"] as? String, "preferences")
        XCTAssertEqual(emitted[1].params["step_name"] as? String, "explore_sets")
        XCTAssertEqual(emitted[2].params["sport"] as? String, "icehockey_nhl")
        XCTAssertEqual(emitted[3].params["last_step_completed"] as? Int, 3)
        XCTAssertEqual(emitted[3].params["last_step_name"] as? String, "explore_sets")
    }

    func testEntryPointPreservedInSanitizeAndPassedByAllChecklistCallers() throws {
        let sanitized = try XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "onboarding_start",
                parameters: [
                    "entry_point": "first_launch",
                    "email": "reader@example.com",
                ]
            )
        )
        XCTAssertEqual(sanitized["entry_point"] as? String, "first_launch")
        XCTAssertNil(sanitized["email"])

        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views")
        let discover = try String(contentsOf: root.appendingPathComponent("DiscoverView.swift"), encoding: .utf8)
        let myStuff = try String(contentsOf: root.appendingPathComponent("MyStuffView.swift"), encoding: .utf8)
        let prefs = try String(contentsOf: root.appendingPathComponent("PreferencesView.swift"), encoding: .utf8)
        XCTAssertTrue(discover.contains("entryPoint: arrivedHeadline == nil ? \"first_launch\" : \"shared_link\""))
        XCTAssertTrue(myStuff.contains("entryPoint: \"my_stuff_banner\""))
        XCTAssertTrue(myStuff.contains("OnboardingView(entryPoint: \"my_stuff\")"))
        XCTAssertTrue(prefs.contains("OnboardingView(entryPoint: \"preferences\")"))
    }
}
