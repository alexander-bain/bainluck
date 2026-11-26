import SwiftUI
import XCTest
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

/// `#13779` (`427: A`):
/// 1. Re-opening the checklist adds instead of replacing `localInterestsKey` and
///    `FirstRunPreferences212A`, and preserves prior `savedAtEpoch` when nothing new is picked.
/// 2. A fresh first-run sitting still writes initial onboarding state cleanly.
/// 3. `PreferencesView` wording matches the checklist (`427: A`).
@MainActor
final class ChecklistAdditiveAndPreferencesWording13779Tests: XCTestCase {

    private func makeDefaults(_ suffix: String = UUID().uuidString) -> UserDefaults {
        let suite = "Checklist13779.\(suffix)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        return defaults
    }

    private func makeBruinsSuggestion() -> FirstRunSuggestion212A {
        FirstRunSuggestion212A(
            id: "team:104",
            name: "Boston Bruins",
            sportOrCategoryLabel: "NHL",
            contextLine: "Boston",
            logoUrl: nil,
            primaryColorHex: nil,
            teamId: 104,
            sportKey: "icehockey_nhl",
            followedSubject: .team(
                slug: "104",
                teamId: 104,
                name: "Boston Bruins",
                sportKey: "icehockey_nhl",
                logoUrl: nil
            ),
            affinityCategory: "hockey",
            marketId: nil,
            matchKeywords: ["Boston Bruins", "Boston"]
        )
    }

    private func makePatriotsSuggestion() -> FirstRunSuggestion212A {
        FirstRunSuggestion212A(
            id: "team:101",
            name: "New England Patriots",
            sportOrCategoryLabel: "NFL",
            contextLine: "New England",
            logoUrl: nil,
            primaryColorHex: nil,
            teamId: 101,
            sportKey: "americanfootball_nfl",
            followedSubject: .team(
                slug: "101",
                teamId: 101,
                name: "New England Patriots",
                sportKey: "americanfootball_nfl",
                logoUrl: nil
            ),
            affinityCategory: "nfl",
            marketId: nil,
            matchKeywords: ["New England Patriots", "New England"]
        )
    }

    func testReopeningChecklistAddsNewTeamAndPreservesPriorLocalInterestsAndPreferences() async throws {
        let defaults = makeDefaults()
        let suiteName = "Checklist13779.Follow.\(UUID().uuidString)"
        let followDefaults = UserDefaults(suiteName: suiteName)!
        followDefaults.removePersistentDomain(forName: suiteName)
        defer { followDefaults.removePersistentDomain(forName: suiteName) }

        let priorEpoch: TimeInterval = 1_795_500_000
        defaults.set(["nfl": 0.3, "politics": 1.0], forKey: FirstRunStorageKeys212A.localInterestsKey)
        FirstRunPreferences212A(
            boostedCategories: ["nfl"],
            boostedTerms: ["New England Patriots"],
            boostedMarketIds: [1001],
            savedAtEpoch: priorEpoch
        ).save(defaults: defaults)

        let submittedExp = expectation(description: "onboarding submission sent")
        var capturedSubmissions: [OnboardingSubmission] = []

        let auth = AuthManager(restoreOnInit: false)
        auth.user = AuthUser(
            id: 1,
            email: "reader@example.com",
            displayName: "Reader",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        defer { auth.user = nil }

        let followMgr = FollowManager295A(defaults: followDefaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            submitOnboarding: { submission in
                capturedSubmissions.append(submission)
                submittedExp.fulfill()
                return OnboardingResponse(status: "ok", onboardingCompleted: true)
            }
        )

        // Pick one more team ("Boston Bruins") in this reopened sitting.
        vm.toggleSuggestion(makeBruinsSuggestion(), followManager: followMgr)
        var dismissed = false
        vm.finish(followManager: followMgr, authManager: auth) {
            dismissed = true
        }
        XCTAssertTrue(dismissed)

        await fulfillment(of: [submittedExp], timeout: 2.0)

        let interests = try XCTUnwrap(
            defaults.dictionary(forKey: FirstRunStorageKeys212A.localInterestsKey) as? [String: Double]
        )
        XCTAssertEqual(interests["nfl"], 0.3, "Must not overwrite prior category level")
        XCTAssertEqual(interests["politics"], 1.0, "Must preserve untouched category")
        XCTAssertEqual(interests["hockey"], 1.0, "Must add new category from this sitting")

        let mergedPrefs = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertEqual(mergedPrefs.boostedCategories, ["hockey", "nfl"])
        XCTAssertEqual(mergedPrefs.boostedTerms, ["Boston", "Boston Bruins", "New England Patriots"])
        XCTAssertEqual(mergedPrefs.boostedMarketIds, [1001])
        XCTAssertNotNil(mergedPrefs.savedAtEpoch)

        XCTAssertEqual(capturedSubmissions.count, 1)
        XCTAssertEqual(capturedSubmissions[0].followTeams.map(\.teamId), [104])

        // Re-opening again and tapping Finish with zero new picks must keep prior savedAtEpoch untouched.
        let frozenPrefs = FirstRunPreferences212A(
            boostedCategories: mergedPrefs.boostedCategories,
            boostedTerms: mergedPrefs.boostedTerms,
            boostedMarketIds: mergedPrefs.boostedMarketIds,
            savedAtEpoch: priorEpoch
        )
        frozenPrefs.save(defaults: defaults)

        let noopVM = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            submitOnboarding: { _ in
                XCTFail("Empty checklist sitting must not overwrite onboarding on server")
                return OnboardingResponse(status: "ok", onboardingCompleted: true)
            }
        )
        noopVM.finish(followManager: followMgr, authManager: auth) {}
        let afterNoop = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertEqual(afterNoop.boostedCategories, ["hockey", "nfl"])
        XCTAssertEqual(afterNoop.savedAtEpoch, priorEpoch)
    }

    func testFirstRunSittingStillSavesInitialPicksAndSubmitsOnboarding() async throws {
        let defaults = makeDefaults()
        let suiteName = "Checklist13779.FirstRun.\(UUID().uuidString)"
        let followDefaults = UserDefaults(suiteName: suiteName)!
        followDefaults.removePersistentDomain(forName: suiteName)
        defer { followDefaults.removePersistentDomain(forName: suiteName) }

        let submittedExp = expectation(description: "first run submitted")
        var capturedSubmissions: [OnboardingSubmission] = []

        let auth = AuthManager(restoreOnInit: false)
        auth.user = AuthUser(
            id: 2,
            email: "new@example.com",
            displayName: "New Reader",
            photoUrl: nil,
            onboardingCompleted: false,
            createdAt: nil
        )
        defer { auth.user = nil }

        let followMgr = FollowManager295A(defaults: followDefaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            submitOnboarding: { submission in
                capturedSubmissions.append(submission)
                submittedExp.fulfill()
                return OnboardingResponse(status: "ok", onboardingCompleted: true)
            }
        )

        vm.toggleSuggestion(makePatriotsSuggestion(), followManager: followMgr)
        vm.finish(followManager: followMgr, authManager: auth) {}

        await fulfillment(of: [submittedExp], timeout: 2.0)

        XCTAssertTrue(defaults.bool(forKey: FirstRunStorageKeys212A.onboardedKey))
        let interests = try XCTUnwrap(
            defaults.dictionary(forKey: FirstRunStorageKeys212A.localInterestsKey) as? [String: Double]
        )
        XCTAssertEqual(interests, ["nfl": 1.0])
        let savedPrefs = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertEqual(savedPrefs.boostedCategories, ["nfl"])
        XCTAssertEqual(savedPrefs.boostedTerms, ["New England", "New England Patriots"])
        XCTAssertNotNil(savedPrefs.savedAtEpoch)
        XCTAssertEqual(capturedSubmissions.count, 1)
        XCTAssertEqual(capturedSubmissions[0].followTeams.map(\.teamId), [101])
    }

    func testPreferencesViewCarriesChecklistMatchingWordingAndLevelsDescription427A() throws {
        let testFile = URL(fileURLWithPath: #filePath)
        let repoRoot = testFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let prefsViewURL = repoRoot
            .appendingPathComponent("ios/Bain Luck/Bain Luck/Views/PreferencesView.swift")
        let source = try String(contentsOf: prefsViewURL, encoding: .utf8)

        let requiredCopy = [
            "Open the checklist",
            "Follow teams and topics, pick sets, turn on alerts",
            "Edit what you follow",
            "Follow your teams",
            "More or less of a whole category",
        ]
        for line in requiredCopy {
            XCTAssertTrue(source.contains(line), "PreferencesView must contain 427: A copy: \(line)")
        }

        let retiredCopy = [
            "Redo Onboarding",
            "Start fresh with team selection and interests",
            "Edit Teams",
            "Set up your teams",
        ]
        for oldLine in retiredCopy {
            XCTAssertFalse(source.contains(oldLine), "PreferencesView must not contain retired copy: \(oldLine)")
        }
    }

    func testChecklistRaisesLowCategoryWithoutLoweringHighOrUntouched() async throws {
        let defaults = makeDefaults()
        let suiteName = "Checklist13779.Raise.\(UUID().uuidString)"
        let followDefaults = UserDefaults(suiteName: suiteName)!
        followDefaults.removePersistentDomain(forName: suiteName)
        defer { followDefaults.removePersistentDomain(forName: suiteName) }

        defaults.set(
            ["nba": 0.1, "nfl": 1.0, "baseball": 1.0],
            forKey: FirstRunStorageKeys212A.localInterestsKey
        )

        let auth = AuthManager(restoreOnInit: false)
        let followMgr = FollowManager295A(defaults: followDefaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            submitOnboarding: { _ in
                OnboardingResponse(status: "ok", onboardingCompleted: true)
            }
        )

        let celticsSuggestion = FirstRunSuggestion212A(
            id: "team:102",
            name: "Boston Celtics",
            sportOrCategoryLabel: "NBA",
            contextLine: "Boston",
            logoUrl: nil,
            primaryColorHex: nil,
            teamId: 102,
            sportKey: "basketball_nba",
            followedSubject: .team(
                slug: "102",
                teamId: 102,
                name: "Boston Celtics",
                sportKey: "basketball_nba",
                logoUrl: nil
            ),
            affinityCategory: "nba",
            marketId: nil,
            matchKeywords: ["Boston Celtics", "Boston"]
        )

        // Pick Celtics -> raises stored "nba" from 0.1 to 1.0 while untouched "nfl" stays 1.0.
        vm.toggleSuggestion(celticsSuggestion, followManager: followMgr)
        vm.finish(followManager: followMgr, authManager: auth) {}

        let interests = try XCTUnwrap(
            defaults.dictionary(forKey: FirstRunStorageKeys212A.localInterestsKey) as? [String: Double]
        )
        XCTAssertEqual(interests["nba"], 1.0, "Picked checklist category must raise low stored level")
        XCTAssertEqual(interests["nfl"], 1.0, "Untouched high stored level must stay high")
        XCTAssertEqual(interests["baseball"], 1.0, "Untouched high stored level must stay untouched")
    }

    #if canImport(UIKit)
    func testRenderPreferences390AndAX5LightAndDarkWordingSheets() async throws {
        let outDir = FileManager.default.temporaryDirectory.appendingPathComponent("shots-13779", isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let emptyPrefs = PreferencesResponse(
            homeLocation: "Boston",
            sportAffinities: ["nfl": 1.0, "nba": 0.3],
            onboardingCompleted: true,
            favorites: []
        )
        let populatedPrefs = PreferencesResponse(
            homeLocation: "Boston",
            sportAffinities: ["nfl": 1.0, "nba": 0.3],
            onboardingCompleted: true,
            favorites: [
                FavoriteItem(
                    teamId: 101,
                    teamName: "New England Patriots",
                    relationType: "follow",
                    sportKey: "americanfootball_nfl",
                    logoUrl: nil,
                    source: "onboarding"
                )
            ]
        )

        try await renderPreferences(
            prefs: emptyPrefs,
            name: "empty-390-light",
            colorScheme: .light,
            dynamicTypeSize: .large,
            scrollFraction: 0.08,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: emptyPrefs,
            name: "empty-390-dark",
            colorScheme: .dark,
            dynamicTypeSize: .large,
            scrollFraction: 0.08,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: emptyPrefs,
            name: "empty-ax5-light",
            colorScheme: .light,
            dynamicTypeSize: .accessibility5,
            scrollFraction: 0.03,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: populatedPrefs,
            name: "populated-mid-ax5-light",
            colorScheme: .light,
            dynamicTypeSize: .accessibility5,
            scrollFraction: 0.06,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: populatedPrefs,
            name: "populated-mid-ax5-dark",
            colorScheme: .dark,
            dynamicTypeSize: .accessibility5,
            scrollFraction: 0.06,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: populatedPrefs,
            name: "actions-390-light",
            colorScheme: .light,
            dynamicTypeSize: .large,
            scrollFraction: 0.82,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: populatedPrefs,
            name: "actions-ax5-light",
            colorScheme: .light,
            dynamicTypeSize: .accessibility5,
            scrollFraction: 0.84,
            outDir: outDir
        )
        try await renderPreferences(
            prefs: populatedPrefs,
            name: "actions-ax5-dark",
            colorScheme: .dark,
            dynamicTypeSize: .accessibility5,
            scrollFraction: 0.84,
            outDir: outDir
        )
    }

    private func renderPreferences(
        prefs: PreferencesResponse,
        name: String,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        scrollFraction: CGFloat,
        outDir: URL
    ) async throws {
        let width: CGFloat = 390
        let height: CGFloat = 844
        let auth = AuthManager(restoreOnInit: false)
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiCategory: UIContentSizeCategory = dynamicTypeSize == .accessibility5
            ? .accessibilityExtraExtraExtraLarge
            : .large

        let wrapped = NavigationStack {
            PreferencesView(loadedPrefsForTest: prefs)
                .frame(maxWidth: width, maxHeight: .infinity)
        }
        .environmentObject(auth)
        .environment(\.colorScheme, colorScheme)
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
            try? await Task.sleep(nanoseconds: 40_000_000)
        }

        if let scrollView = findScrollView(in: host.view) {
            let maxOffsetY = max(0, scrollView.contentSize.height - scrollView.bounds.height)
            let targetY = min(maxOffsetY, max(0, maxOffsetY * scrollFraction))
            scrollView.setContentOffset(CGPoint(x: 0, y: targetY), animated: false)
            for _ in 0..<4 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                try? await Task.sleep(nanoseconds: 30_000_000)
            }
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let pngURL = outDir.appendingPathComponent("\(name).png")
        try XCTUnwrap(image.pngData()).write(to: pngURL)
        print("SHOT_13779_PNG:", pngURL.path)
    }

    private func findScrollView(in root: UIView) -> UIScrollView? {
        if let scroll = root as? UIScrollView {
            return scroll
        }
        for child in root.subviews {
            if let found = findScrollView(in: child) {
                return found
            }
        }
        return nil
    }
    #endif
}
