import XCTest
@testable import Bain_Luck

/// Guards the Morning Digest push preference (#1159): decode defaults (no
/// silent opt-in), the view-model's optimistic-update-with-rollback path,
/// retry-after-failure, repeated-tap / in-flight (stale-response) protection,
/// and relaunch persistence of the server-stored opt-in.
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

    // MARK: - Retry after a failed save

    @MainActor
    func testRetryAfterFailureSucceedsAndClearsError() async {
        var shouldFail = true
        let vm = PreferencesViewModel(morningDigestUpdater: { enabled in
            if shouldFail { shouldFail = false; throw StubError() }
            return enabled
        })
        // First tap fails: rolls back to off, surfaces an error (the retry prompt).
        await vm.applyMorningDigest(true)
        XCTAssertFalse(vm.morningDigestEnabled)
        XCTAssertNotNil(vm.morningDigestError)
        // Tapping again (retry) succeeds: on, error cleared, not saving.
        await vm.applyMorningDigest(true)
        XCTAssertTrue(vm.morningDigestEnabled, "a retry after a failed save should take effect")
        XCTAssertNil(vm.morningDigestError, "a successful retry must clear the prior error")
        XCTAssertFalse(vm.morningDigestSaving)
    }

    // MARK: - Repeated taps / in-flight protection

    /// A single-shot gate a test can hold an in-flight save open on, then release.
    private actor Gate {
        private var continuation: CheckedContinuation<Void, Never>?
        private var released = false
        func wait() async {
            if released { return }
            await withCheckedContinuation { continuation = $0 }
        }
        func open() {
            released = true
            continuation?.resume()
            continuation = nil
        }
    }

    @MainActor
    func testStaleInFlightResponseDoesNotClobberNewerValue() async {
        // The "on" save hangs until we release it; the "off" save is instant.
        let gate = Gate()
        let vm = PreferencesViewModel(morningDigestUpdater: { enabled in
            if enabled { await gate.wait() }
            return enabled
        })

        // Tap ON: optimistic true, then blocks awaiting the server.
        let onTask = Task { await vm.applyMorningDigest(true) }
        await Task.yield()
        XCTAssertTrue(vm.morningDigestEnabled, "optimistic ON should show immediately")

        // A newer tap supersedes the in-flight one (as setMorningDigest does).
        onTask.cancel()
        await vm.applyMorningDigest(false)   // instant: optimistic + confirmed OFF
        XCTAssertFalse(vm.morningDigestEnabled)
        XCTAssertFalse(vm.morningDigestSaving)

        // Release the stale ON save; its late response must NOT flip us back on.
        await gate.open()
        _ = await onTask.value
        XCTAssertFalse(vm.morningDigestEnabled,
                       "a superseded in-flight response must not clobber the newer value")
    }

    @MainActor
    func testRepeatedTapToSameValueIsANoOp() async {
        // Reentrancy: the second tap to the same target while the first is
        // in-flight short-circuits (guard enabled != current) — one server call.
        let gate = Gate()
        var calls = 0
        let vm = PreferencesViewModel(morningDigestUpdater: { enabled in
            calls += 1
            await gate.wait()
            return enabled
        })
        let first = Task { await vm.applyMorningDigest(true) }
        await Task.yield()                    // first: optimistic true, awaiting gate
        await vm.applyMorningDigest(true)     // duplicate tap: already true -> no-op
        XCTAssertEqual(calls, 1, "a repeated tap to the same value must not issue a second save")
        await gate.open()
        _ = await first.value
        XCTAssertTrue(vm.morningDigestEnabled)
        XCTAssertFalse(vm.morningDigestSaving)
    }

    // MARK: - Relaunch persistence (server value reappears on the toggle)

    @MainActor
    func testLoadedServerValueReflectsOnRelaunch() throws {
        let json = """
        { "home_location": null, "sport_affinities": {}, "onboarding_completed": true, "favorites": [],
          "push_preferences": { "daily_challenge": true, "big_moves": true, "morning_digest": true } }
        """
        let prefs = try decoder().decode(PreferencesResponse.self, from: Data(json.utf8))
        let vm = PreferencesViewModel(morningDigestUpdater: { $0 })
        vm.apply(loaded: prefs)
        XCTAssertTrue(vm.morningDigestEnabled, "a stored opt-in must reappear enabled after relaunch")
        XCTAssertNil(vm.morningDigestError)
    }

    @MainActor
    func testLoadedWithoutPushBlockStaysOff() throws {
        // Anonymous/older-shaped payload with no push block: never a silent opt-in.
        let json = """
        { "home_location": null, "sport_affinities": {}, "onboarding_completed": false, "favorites": [] }
        """
        let prefs = try decoder().decode(PreferencesResponse.self, from: Data(json.utf8))
        let vm = PreferencesViewModel(morningDigestUpdater: { $0 })
        vm.apply(loaded: prefs)
        XCTAssertFalse(vm.morningDigestEnabled, "a missing push block must keep Morning Digest off")
    }

    @MainActor
    func testReloadClearsAStaleError() async throws {
        // A prior session left an error; a fresh load reflecting the server
        // value should clear it so the row isn't stuck showing "try again".
        let vm = PreferencesViewModel(morningDigestUpdater: { _ in throw StubError() })
        await vm.applyMorningDigest(true)
        XCTAssertNotNil(vm.morningDigestError)
        let json = """
        { "home_location": null, "sport_affinities": {}, "onboarding_completed": true, "favorites": [],
          "push_preferences": { "morning_digest": true } }
        """
        let prefs = try decoder().decode(PreferencesResponse.self, from: Data(json.utf8))
        vm.apply(loaded: prefs)
        XCTAssertNil(vm.morningDigestError, "loading fresh state should clear a stale save error")
        XCTAssertTrue(vm.morningDigestEnabled)
    }
}
