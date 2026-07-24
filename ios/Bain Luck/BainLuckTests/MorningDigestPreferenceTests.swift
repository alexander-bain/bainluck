import XCTest
@testable import Bain_Luck

/// Guards the Morning Digest push preference (#1159): decode defaults (no
/// silent opt-in) and the view-model's optimistic-update-with-rollback path.
final class MorningDigestPreferenceTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private struct StubError: Error {}

    // MARK: - Decode: no default opt-in

    func testPreferencesWithoutPushBlockDefaultsMorningDigestOff() throws {
        let json = """
        { "home_location": null, "sport_affinities": {}, "onboarding_completed": true, "favorites": [] }
        """
        let prefs = try decoder().decode(PreferencesResponse.self, from: Data(json.utf8))
        XCTAssertNil(prefs.pushPreferences)
        // The view model treats a missing block as opt-in default false.
        XCTAssertEqual(prefs.pushPreferences?.morningDigest ?? false, false)
    }

    func testEmptyPushBlockDefaultsMorningDigestOffOptOutOthersOn() throws {
        let json = """
        { "home_location": null, "sport_affinities": {}, "onboarding_completed": true, "favorites": [], "push_preferences": {} }
        """
        let prefs = try decoder().decode(PreferencesResponse.self, from: Data(json.utf8))
        XCTAssertEqual(prefs.pushPreferences?.morningDigest, false, "morning_digest must never default on")
        XCTAssertEqual(prefs.pushPreferences?.dailyChallenge, true)
        XCTAssertEqual(prefs.pushPreferences?.bigMoves, true)
    }

    func testPushBlockDecodesExplicitMorningDigestOn() throws {
        let json = """
        { "home_location": null, "sport_affinities": {}, "onboarding_completed": true, "favorites": [],
          "push_preferences": { "daily_challenge": false, "big_moves": true, "morning_digest": true } }
        """
        let prefs = try decoder().decode(PreferencesResponse.self, from: Data(json.utf8))
        XCTAssertEqual(prefs.pushPreferences?.morningDigest, true)
        XCTAssertEqual(prefs.pushPreferences?.dailyChallenge, false)
    }

    // MARK: - View model: freshly constructed is off (no default opt-in)

    @MainActor
    func testFreshViewModelIsOff() {
        let vm = PreferencesViewModel(morningDigestUpdater: { $0 })
        XCTAssertFalse(vm.morningDigestEnabled)
        XCTAssertNil(vm.morningDigestError)
        XCTAssertFalse(vm.morningDigestSaving)
    }

    // MARK: - Toggle off -> on

    @MainActor
    func testTurnOnPersistsAndClearsSavingState() async {
        var requested: Bool?
        let vm = PreferencesViewModel(morningDigestUpdater: { enabled in
            requested = enabled
            return enabled
        })
        await vm.applyMorningDigest(true)
        XCTAssertEqual(requested, true, "the server call should receive the new value")
        XCTAssertTrue(vm.morningDigestEnabled)
        XCTAssertNil(vm.morningDigestError)
        XCTAssertFalse(vm.morningDigestSaving)
    }

    // MARK: - Toggle on -> off

    @MainActor
    func testTurnOffFromOn() async {
        let vm = PreferencesViewModel(morningDigestUpdater: { $0 })
        await vm.applyMorningDigest(true)
        XCTAssertTrue(vm.morningDigestEnabled)
        await vm.applyMorningDigest(false)
        XCTAssertFalse(vm.morningDigestEnabled)
        XCTAssertNil(vm.morningDigestError)
        XCTAssertFalse(vm.morningDigestSaving)
    }

    // MARK: - Request failure rolls back and surfaces an error

    @MainActor
    func testFailureRollsBackToPreviousValueAndSetsError() async {
        let vm = PreferencesViewModel(morningDigestUpdater: { _ in throw StubError() })
        // Was off; user taps on; save fails -> must revert to off.
        await vm.applyMorningDigest(true)
        XCTAssertFalse(vm.morningDigestEnabled, "failed save must roll back the optimistic flip")
        XCTAssertNotNil(vm.morningDigestError)
        XCTAssertFalse(vm.morningDigestSaving)
    }

    @MainActor
    func testServerConfirmedValueWins() async {
        // Server refuses/normalizes the request and echoes false.
        let vm = PreferencesViewModel(morningDigestUpdater: { _ in false })
        await vm.applyMorningDigest(true)
        XCTAssertFalse(vm.morningDigestEnabled, "the server-confirmed value should be authoritative")
        XCTAssertNil(vm.morningDigestError)
    }
}
