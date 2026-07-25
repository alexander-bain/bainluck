import XCTest

/// L2-182: guards that a failed Watch guess is honest and retryable.
///
/// The bug (L2-180 half-fix): `submitGuess` scored locally and showed
/// "Correct!"/"Not quite!" the instant a button was tapped, then only set a
/// never-read `lastSaveFailed` flag if the POST threw — so a dropped request
/// looked identical to a saved one, consumed the question, and could double-submit.
///
/// These tests drive `WatchGuessViewModel` through an injected `WatchGuessBackend`
/// mock (no network, no WatchKit) covering success, failure, retry, double-tap,
/// and Next-during-request. `WatchGuessViewModel`, `WatchGuessPool`,
/// `WatchGuessBackend`, and `WatchFeedModels` are compiled into this test bundle
/// directly (see the project's target membership).
@MainActor
final class WatchGuessViewModelTests: XCTestCase {

    private struct StubError: Error {}

    // A feed with two distinct, in-band futures markets (so the deck has two
    // questions and advancing is observable). No event cards — the futures-only
    // market_id invariant is enforced by WatchGuessPool and covered separately.
    private func twoFuturesItems() throws -> [WatchFeedItem] {
        let json = """
        {
          "items": [
            { "type": "futures", "score": 80,
              "data": { "id": 200, "name": "Q1",
                        "top_outcomes": [ { "name": "Yes", "probability": 0.40 } ] } },
            { "type": "futures", "score": 70,
              "data": { "id": 201, "name": "Q2",
                        "top_outcomes": [ { "name": "No", "probability": 0.55 } ] } }
          ],
          "total": 2, "limit": 8, "offset": 0, "has_more": false
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(WatchFeedResponse.self, from: Data(json.utf8)).items
    }

    /// The graded result the VM should reveal for a given loaded question/guess.
    private func expectedCorrect(_ q: GuessQuestion, _ guess: String) -> Bool {
        guess == "higher" ? q.actualPct > q.threshold : q.actualPct < q.threshold
    }

    private func loadedVM(_ mock: MockGuessBackend) async throws -> WatchGuessViewModel {
        mock.feedItems = try twoFuturesItems()
        let vm = WatchGuessViewModel(backend: mock)
        await vm.loadQuestions()
        XCTAssertNotNil(vm.currentQuestion, "deck should load a playable question")
        return vm
    }

    // MARK: - Success reveals the graded result and can advance

    func testSuccessRevealsResultAndAdvances() async throws {
        let mock = MockGuessBackend()
        mock.streakValue = 4
        let vm = try await loadedVM(mock)
        let q = try XCTUnwrap(vm.currentQuestion)
        let firstId = q.id

        await vm.submitGuess("higher")

        XCTAssertEqual(vm.submission, .idle)
        let result = try XCTUnwrap(vm.lastResult, "a saved guess must reveal a result")
        XCTAssertEqual(result.guess, "higher")
        XCTAssertEqual(result.correct, expectedCorrect(q, "higher"))
        XCTAssertEqual(vm.streak, 4, "streak refreshes only after a confirmed save")
        XCTAssertEqual(mock.submitCount, 1)

        // Next advances to the other question and clears the result.
        vm.nextQuestion()
        XCTAssertNil(vm.lastResult)
        let next = try XCTUnwrap(vm.currentQuestion)
        XCTAssertNotEqual(next.id, firstId, "Next should advance the deck")
    }

    // MARK: - Failure is honest: no result, no advance, no streak change

    func testFailureNeverRevealsResultOrAdvances() async throws {
        let mock = MockGuessBackend()
        mock.streakValue = 9
        let vm = try await loadedVM(mock)
        // Consume the streak the load fetched so we can prove a failed submit
        // does not change it.
        let streakBefore = vm.streak
        let idBefore = try XCTUnwrap(vm.currentQuestion).id

        mock.submitShouldFail = true
        await vm.submitGuess("lower")

        XCTAssertEqual(vm.submission, .failed)
        XCTAssertNil(vm.lastResult, "a failed request must not show Correct!/Not quite!")
        XCTAssertEqual(vm.currentQuestion?.id, idBefore, "a failed guess must not consume/advance the question")
        XCTAssertEqual(vm.streak, streakBefore, "a failed guess must not touch the streak")
    }

    // MARK: - Retry after failure re-submits the same guess and succeeds

    func testRetryAfterFailureSucceeds() async throws {
        let mock = MockGuessBackend()
        let vm = try await loadedVM(mock)
        let q = try XCTUnwrap(vm.currentQuestion)

        mock.submitShouldFail = true
        await vm.submitGuess("higher")
        XCTAssertEqual(vm.submission, .failed)
        XCTAssertEqual(mock.submitCount, 1)

        // The transient failure clears; retry re-submits the SAME guess.
        mock.submitShouldFail = false
        await vm.retrySubmit()

        XCTAssertEqual(vm.submission, .idle)
        let result = try XCTUnwrap(vm.lastResult)
        XCTAssertEqual(result.guess, "higher", "retry must re-submit the same guess")
        XCTAssertEqual(result.correct, expectedCorrect(q, "higher"))
        XCTAssertEqual(mock.submitCount, 2, "retry issues exactly one more submit")
    }

    func testRetryIsNoOpWhenNotFailed() async throws {
        let mock = MockGuessBackend()
        let vm = try await loadedVM(mock)
        // Nothing submitted yet -> not in a failed state.
        await vm.retrySubmit()
        XCTAssertEqual(mock.submitCount, 0)
        XCTAssertNil(vm.lastResult)
    }

    // MARK: - Double tap while a save is in flight submits only once

    func testDoubleTapWhileSubmittingSubmitsOnce() async throws {
        let mock = MockGuessBackend()
        mock.holdSubmit = true
        let vm = try await loadedVM(mock)

        let task = Task { await vm.submitGuess("higher") }
        await mock.waitUntilSubmitEntered()
        XCTAssertEqual(vm.submission, .submitting)

        // Second tap while the first is in flight is ignored.
        await vm.submitGuess("lower")
        XCTAssertEqual(mock.submitCount, 1, "an in-flight save must block a second submission")

        mock.releaseSubmit()
        await task.value
        XCTAssertEqual(vm.submission, .idle)
        XCTAssertEqual(vm.lastResult?.guess, "higher")
    }

    // MARK: - Next while a save is in flight does not advance

    func testNextDuringRequestDoesNotAdvance() async throws {
        let mock = MockGuessBackend()
        mock.holdSubmit = true
        let vm = try await loadedVM(mock)
        let idBefore = try XCTUnwrap(vm.currentQuestion).id

        let task = Task { await vm.submitGuess("higher") }
        await mock.waitUntilSubmitEntered()
        XCTAssertEqual(vm.submission, .submitting)

        vm.nextQuestion()
        XCTAssertEqual(vm.currentQuestion?.id, idBefore, "Next must not advance while submitting")
        XCTAssertNil(vm.lastResult)

        mock.releaseSubmit()
        await task.value
    }

    // MARK: - A streak-fetch failure after a saved guess does not un-save it

    func testStreakFetchFailureDoesNotUnsaveGuess() async throws {
        let mock = MockGuessBackend()
        let vm = try await loadedVM(mock)
        mock.streakError = StubError()

        await vm.submitGuess("higher")

        XCTAssertEqual(vm.submission, .idle, "a cosmetic streak failure must not fail the guess")
        XCTAssertNotNil(vm.lastResult, "the guess persisted; the result must still show")
    }
}

// MARK: - Deterministic mock backend

/// A `@MainActor` mock so every mutation and the view model run on one actor —
/// no data races, deterministic ordering. `holdSubmit` gates `submitGuess` on a
/// continuation so in-flight state (double tap / Next-during-request) can be
/// observed and released precisely.
@MainActor
final class MockGuessBackend: WatchGuessBackend {
    var feedItems: [WatchFeedItem] = []
    var streakValue: Int? = 3
    var feedError: Error?
    var streakError: Error?
    var submitShouldFail = false

    private(set) var submitCount = 0

    var holdSubmit = false
    private var submitGate: CheckedContinuation<Void, Never>?
    private var enteredGate: CheckedContinuation<Void, Never>?
    private var submitEntered = false

    struct MockError: Error {}

    func fetchFeedItems(limit: Int, forceRefresh: Bool) async throws -> [WatchFeedItem] {
        if let feedError { throw feedError }
        return feedItems
    }

    func submitGuess(
        marketId: Int,
        guess: String,
        threshold: Int,
        actualProbability: Double,
        correct: Bool,
        category: String?
    ) async throws {
        submitCount += 1
        submitEntered = true
        enteredGate?.resume()
        enteredGate = nil
        if holdSubmit {
            await withCheckedContinuation { submitGate = $0 }
        }
        if submitShouldFail { throw MockError() }
    }

    func currentStreak() async throws -> Int? {
        if let streakError { throw streakError }
        return streakValue
    }

    /// Suspends until `submitGuess` has been entered (i.e. the save is in flight).
    func waitUntilSubmitEntered() async {
        if submitEntered { return }
        await withCheckedContinuation { enteredGate = $0 }
    }

    /// Releases a gated `submitGuess` so it can complete.
    func releaseSubmit() {
        submitGate?.resume()
        submitGate = nil
    }
}
