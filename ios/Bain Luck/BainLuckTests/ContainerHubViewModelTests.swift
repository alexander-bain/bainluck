import XCTest
@testable import Bain_Luck

private actor ContainerHubScriptedService: ContainerHubLoading {
    enum Result: Sendable {
        case response(ContainerHubResponse)
        case failure(Int)
    }
    private var script: [Result]
    private(set) var calls = 0
    init(_ script: [Result]) { self.script = script }

    func load(slug: String) async throws -> ContainerHubResponse {
        calls += 1
        guard !script.isEmpty else { throw APIError.httpError(statusCode: 500, body: nil) }
        switch script.removeFirst() {
        case .response(let r): return r
        case .failure(let code): throw APIError.httpError(statusCode: code, body: nil)
        }
    }
}

private actor ContainerHubDeferredService: ContainerHubLoading {
    private var requests: [CheckedContinuation<ContainerHubResponse, Error>] = []
    private var waiters: [(count: Int, continuation: CheckedContinuation<Void, Never>)] = []

    func load(slug: String) async throws -> ContainerHubResponse {
        try await withCheckedThrowingContinuation { continuation in
            requests.append(continuation)
            let ready = waiters.filter { $0.count <= requests.count }
            waiters.removeAll { $0.count <= requests.count }
            ready.forEach { $0.continuation.resume() }
        }
    }

    func waitForRequestCount(_ count: Int) async {
        if requests.count >= count { return }
        await withCheckedContinuation { waiters.append((count, $0)) }
    }

    func complete(_ index: Int, response: ContainerHubResponse) {
        requests[index].resume(returning: response)
    }
}

final class ContainerHubViewModelTests: XCTestCase {
    @MainActor
    func testReturningFromMemberRevalidatesWithoutResettingTheHeldHub() async throws {
        let response = try ContainerHubFixture.decode()
        let service = ContainerHubScriptedService([.response(response), .response(response)])
        let vm = ContainerHubViewModel(slug: response.slug, service: service)
        await vm.load()
        guard case .loaded(let p) = vm.state else { return XCTFail("Hub not loaded") }
        let member = try XCTUnwrap(p.members.last)
        vm.scrolled(to: member.id)
        vm.opened(member)
        await vm.load() // SwiftUI task runs again after Back.
        let calls = await service.calls
        XCTAssertEqual(calls, 2)
        XCTAssertEqual(vm.context.scrollMemberId, member.id)
        XCTAssertEqual(vm.context.selectedMemberId, member.id)
        XCTAssertEqual(vm.context.identity?.revision, 4)
    }

    @MainActor
    func testWithdrawalRefreshReplacesPublishedCardsAndReadingContext() async throws {
        let published = try ContainerHubFixture.decode()
        let withdrawn = try ContainerHubFixture.decode { $0["state"] = "withdrawn"; $0["revision"] = 5 }
        let service = ContainerHubScriptedService([.response(published), .response(withdrawn)])
        let vm = ContainerHubViewModel(slug: published.slug, service: service)
        await vm.load()
        vm.scrolled(to: "event:501")
        await vm.load()
        guard case .loaded(let p) = vm.state else { return XCTFail("Terminal read missing") }
        XCTAssertEqual(p.response.state, .withdrawn)
        XCTAssertTrue(p.members.isEmpty)
        XCTAssertNil(vm.context.scrollMemberId)
        XCTAssertEqual(vm.context.identity?.revision, 5)
    }

    @MainActor
    func test404IsUnavailableWhile503IsAnError() async throws {
        let response = try ContainerHubFixture.decode()
        let service = ContainerHubScriptedService([.response(response), .failure(404), .failure(503)])
        let vm = ContainerHubViewModel(slug: response.slug, service: service)
        await vm.load()
        await vm.load()
        guard case .unavailable = vm.state else { return XCTFail("404 must not look empty") }
        XCTAssertNil(vm.context.identity)
        await vm.load()
        guard case .error(let message) = vm.state else { return XCTFail("503 must not look empty") }
        XCTAssertFalse(message.isEmpty)
        XCTAssertFalse(vm.isRefreshing)
    }

    @MainActor
    func testResponseForDifferentSlugCannotReplaceTheRequestedEdition() async throws {
        let mlb = try ContainerHubFixture.decode("representative_mlb_postseason")
        let vm = ContainerHubViewModel(slug: "nfl-2026-week-5", service: ContainerHubScriptedService([.response(mlb)]))
        await vm.load()
        guard case .error = vm.state else { return XCTFail("Wrong edition accepted") }
        XCTAssertNil(vm.context.identity)
    }

    @MainActor
    func testOlderRequestCannotRestorePublishedMembersAfterNewerWithdrawal() async throws {
        let published = try ContainerHubFixture.decode()
        let withdrawn = try ContainerHubFixture.decode { $0["state"] = "withdrawn"; $0["revision"] = 5 }
        let service = ContainerHubDeferredService()
        let vm = ContainerHubViewModel(slug: published.slug, service: service)
        let older = Task { await vm.load() }
        await service.waitForRequestCount(1)
        let newer = Task { await vm.load() }
        await service.waitForRequestCount(2)
        await service.complete(1, response: withdrawn)
        await newer.value
        await service.complete(0, response: published)
        await older.value
        guard case .loaded(let p) = vm.state else { return XCTFail("Withdrawal missing") }
        XCTAssertEqual(p.response.state, .withdrawn)
        XCTAssertEqual(p.response.revision, 5)
        XCTAssertTrue(p.members.isEmpty)
    }
}
