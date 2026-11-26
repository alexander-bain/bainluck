import XCTest
@testable import Bain_Luck

/// 1.0.8 Item 4 — Transient container hub fetch retry (350 ms single retry on
/// non-404, non-cancellation errors). Also notes #10090 already shares in-flight
/// event history reads on `APIClient`.
final class ContainerHubTransientRetry108Tests: XCTestCase {

    private actor ScriptedHubService108: ContainerHubLoading {
        enum Outcome: Sendable {
            case ok(ContainerHubResponse)
            case http(Int)
            case error(Error)
        }

        private var outcomes: [Outcome]
        private(set) var calls = 0

        init(_ outcomes: [Outcome]) {
            self.outcomes = outcomes
        }

        func load(slug: String) async throws -> ContainerHubResponse {
            calls += 1
            guard !outcomes.isEmpty else {
                throw APIError.httpError(statusCode: 500, body: nil)
            }
            switch outcomes.removeFirst() {
            case .ok(let response):
                return response
            case .http(let code):
                throw APIError.httpError(statusCode: code, body: nil)
            case .error(let err):
                throw err
            }
        }
    }

    private actor SleepingHubService108: ContainerHubLoading {
        private(set) var calls = 0
        private var enteredContinuation: CheckedContinuation<Void, Never>?

        func load(slug: String) async throws -> ContainerHubResponse {
            calls += 1
            enteredContinuation?.resume()
            enteredContinuation = nil
            throw URLError(.timedOut)
        }
    }

    @MainActor
    func testTransientErrorRecoversOnSingleRetryWithoutShowingError() async throws {
        let response = try ContainerHubFixture.decode()
        let service = ScriptedHubService108([.http(503), .ok(response)])
        let vm = ContainerHubViewModel(
            slug: response.slug,
            service: service,
            retryDelayNanoseconds: 0
        )

        await vm.load()
        let calls = await service.calls
        XCTAssertEqual(calls, 2)
        guard case .loaded(let presentation) = vm.state else {
            return XCTFail("Expected hub to recover on single retry")
        }
        XCTAssertEqual(presentation.response.slug, response.slug)
    }

    @MainActor
    func testPermanent404DoesNotRetryAndPersistentFailureStopsAfterOneRetry() async throws {
        let response = try ContainerHubFixture.decode()
        let missingService = ScriptedHubService108([.http(404), .ok(response)])
        let missingVM = ContainerHubViewModel(
            slug: response.slug,
            service: missingService,
            retryDelayNanoseconds: 0
        )
        await missingVM.load()
        let missingCalls = await missingService.calls
        XCTAssertEqual(missingCalls, 1, "404 unavailable must not retry")
        guard case .unavailable = missingVM.state else {
            return XCTFail("Expected .unavailable on 404")
        }

        let failingService = ScriptedHubService108([.http(502), .http(503), .ok(response)])
        let failingVM = ContainerHubViewModel(
            slug: response.slug,
            service: failingService,
            retryDelayNanoseconds: 0
        )
        await failingVM.load()
        let failingCalls = await failingService.calls
        XCTAssertEqual(failingCalls, 2, "must cap at 1 retry")
        guard case .error = failingVM.state else {
            return XCTFail("Expected .error after retry exhaustion")
        }
    }

    @MainActor
    func testCancelledTaskAbortsBeforeRetryExecutes() async throws {
        let response = try ContainerHubFixture.decode()
        let service = ScriptedHubService108([.error(CancellationError()), .ok(response)])
        let vm = ContainerHubViewModel(
            slug: response.slug,
            service: service,
            retryDelayNanoseconds: 50_000_000
        )
        await vm.load()
        let calls = await service.calls
        XCTAssertEqual(calls, 1, "cancellation must never retry")

        // Cancellation during backoff sleep also skips second network call.
        let slowService = ScriptedHubService108([.http(503), .ok(response)])
        let slowVM = ContainerHubViewModel(
            slug: response.slug,
            service: slowService,
            retryDelayNanoseconds: 500_000_000
        )
        let task = Task { await slowVM.load() }
        try await Task.sleep(nanoseconds: 50_000_000)
        task.cancel()
        await task.value
        let slowCalls = await slowService.calls
        XCTAssertEqual(slowCalls, 1)
    }
}
