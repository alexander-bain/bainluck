import XCTest
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
}
