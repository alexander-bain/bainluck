import XCTest
@testable import Bain_Luck

private actor ThemeReaderService: ContainerHubLoading {
    struct Request: Sendable { let cursor: String?; let revision: Int? }
    private var requests: [Request] = []
    private var replies: [CheckedContinuation<ContainerHubResponse, Error>] = []
    private var waiters: [(Int, CheckedContinuation<Void, Never>)] = []

    func load(slug: String) async throws -> ContainerHubResponse { try await read(cursor: nil, revision: nil) }
    func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse {
        try await read(cursor: cursor, revision: revision)
    }
    private func read(cursor: String?, revision: Int?) async throws -> ContainerHubResponse {
        try await withCheckedThrowingContinuation { continuation in
            requests.append(Request(cursor: cursor, revision: revision)); replies.append(continuation)
            let ready = waiters.filter { $0.0 <= requests.count }
            waiters.removeAll { $0.0 <= requests.count }
            ready.forEach { $0.1.resume() }
        }
    }
    func wait(_ count: Int) async {
        if requests.count >= count { return }
        await withCheckedContinuation { waiters.append((count, $0)) }
    }
    func reply(_ index: Int, _ response: ContainerHubResponse) { replies[index].resume(returning: response) }
    func fail(_ index: Int, _ error: APIError) { replies[index].resume(throwing: error) }
    func request(_ index: Int) -> Request { requests[index] }
}

final class ThemeCollectionReaderTests: XCTestCase {
    private func page(_ number: Int = 1, mutate: ((inout [String: Any]) -> Void)? = nil) throws -> ContainerHubResponse {
        try ContainerHubFixture.decode("representative_ai_page_\(number)", mutate: mutate)
    }
    @MainActor
    private func loaded(_ vm: ContainerHubViewModel, file: StaticString = #filePath, line: UInt = #line) throws -> ContainerHubPresentation {
        guard case .loaded(let p) = vm.state else { XCTFail("Expected accepted collection", file: file, line: line); throw URLError(.cannotParseResponse) }
        return p
    }
    @MainActor
    private func seed(_ vm: ContainerHubViewModel, _ service: ThemeReaderService) async throws {
        let task = Task { await vm.load() }
        await service.wait(1); await service.reply(0, try page()); await task.value
    }

    func testRealThemeShapeNeedsNoLeagueOrSeasonAndCountsFullInventory() throws {
        let ai = try page()
        XCTAssertNil(ai.edition?.league); XCTAssertNil(ai.edition?.season)
        XCTAssertEqual(ai.edition?.subject, "ai")
        let p = ContainerHubPresentation(response: ai)
        XCTAssertEqual(p.loadedCount, 1); XCTAssertEqual(p.totalCount, 2)
        XCTAssertEqual(p.countLabel, "1 of 2 markets loaded")
        XCTAssertFalse(p.isPartial, "A next page is not a missing inventory")
        XCTAssertNotNil(ai.page?.nextCursor)
        let oscars = try page { value in
            value["slug"] = "oscars-2031"
            value["edition"] = ["kind": "theme_edition", "subject": "oscars", "edition": 2031]
            var header = value["container"] as! [String: Any]; header["slug"] = "oscars-2031"; value["container"] = header
        }
        XCTAssertTrue(oscars.edition?.matches(slug: "oscars-2031") == true)
        for fixture in ["representative_nfl_week", "representative_mlb_postseason"] {
            XCTAssertNil(try ContainerHubFixture.decode(fixture).page)
        }
    }

    func testMalformedThemeCountsCursorAndIdentityFailRatherThanEmptySuccess() throws {
        XCTAssertThrowsError(try page { $0.removeValue(forKey: "counts") })
        XCTAssertThrowsError(try page { $0["page"] = ["limit": 50, "next_cursor": "../other"] })
        XCTAssertThrowsError(try page { $0["edition"] = ["kind": "theme_edition", "subject": "oscars", "edition": 2031] })
        XCTAssertThrowsError(try page { $0["counts"] = ["shown_count": 0, "eligible_count": 0, "withheld_count": [:], "inventory_complete": true] })
    }

    @MainActor
    func testLoadMoreUsesPinnedCursorAndBackKeepsLaterPageAndAnchor() async throws {
        let service = ThemeReaderService()
        let hub = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(hub, service)
        let more = Task { await hub.loadMore() }; await service.wait(2)
        let request = await service.request(1)
        XCTAssertEqual(request.revision, 7); XCTAssertEqual(request.cursor, try page().page?.nextCursor)
        await service.reply(1, try page(2)); await more.value
        let member = try XCTUnwrap(loaded(hub).members.last)
        hub.opened(member); hub.scrolled(to: member.id)
        let back = Task { await hub.load() }; await service.wait(3)
        await service.reply(2, try page()); await service.wait(4)
        await service.reply(3, try page(2)); await back.value
        XCTAssertEqual(try loaded(hub).members.map(\.memberId), [9201, 9202])
        XCTAssertNil(try loaded(hub).response.page?.nextCursor)
        XCTAssertEqual(hub.context.selectedMemberId, member.id); XCTAssertEqual(hub.context.scrollMemberId, member.id)
    }

    @MainActor
    func testRefreshAndPageCrossOrderCannotMixNewRevision() async throws {
        for pageFinishesFirst in [false, true] {
            let service = ThemeReaderService()
            let vm = ContainerHubViewModel(slug: "ai", service: service)
            try await seed(vm, service)
            let more = Task { await vm.loadMore() }; await service.wait(2)
            let refresh = Task { await vm.load() }; await service.wait(3)
            let newer = try page { $0["revision"] = 8 }
            if pageFinishesFirst { await service.reply(1, try page(2)); await more.value }
            await service.reply(2, newer); await refresh.value
            if !pageFinishesFirst { await service.reply(1, try page(2)); await more.value }
            XCTAssertEqual(try loaded(vm).response.revision, 8)
            XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201])
        }
    }

    @MainActor
    func testWithdrawalClosesOutstandingRefreshButLaterReadCanReadmit() async throws {
        let service = ThemeReaderService(), vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let more = Task { await vm.loadMore() }; await service.wait(2)
        let refresh = Task { await vm.load() }; await service.wait(3)
        let withdrawn = try page { $0["state"] = "withdrawn"; $0["revision"] = 8 }
        await service.reply(1, withdrawn); await more.value
        await service.reply(2, try page { $0["revision"] = 9 }); await refresh.value
        XCTAssertEqual(try loaded(vm).response.state, .withdrawn)
        XCTAssertTrue(try loaded(vm).members.isEmpty); XCTAssertNil(vm.context.scrollMemberId)
        let later = Task { await vm.load() }; await service.wait(4)
        await service.reply(3, try page { $0["revision"] = 9 }); await later.value
        XCTAssertEqual(try loaded(vm).response.state, .published)
        XCTAssertEqual(try loaded(vm).response.revision, 9)
    }

    @MainActor
    func testMovedRevisionPageReplacesAndDelayedLowerRevisionRefreshCannotUndoIt() async throws {
        let service = ThemeReaderService(), vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let refresh = Task { await vm.load() }; await service.wait(2)
        let more = Task { await vm.loadMore() }; await service.wait(3)
        await service.reply(2, try page { $0["revision"] = 8; $0["revision_moved"] = true }); await more.value
        await service.reply(1, try page()); await refresh.value
        XCTAssertEqual(try loaded(vm).response.revision, 8)
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201])
    }

    @MainActor
    func testTransientFailureRetainsLastGoodBut404ClosesOutstandingReads() async throws {
        let service = ThemeReaderService(), vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let refresh = Task { await vm.load() }; await service.wait(2)
        await service.fail(1, .httpError(statusCode: 503, body: nil)); await refresh.value
        XCTAssertEqual(try loaded(vm).members.count, 1); XCTAssertNotNil(vm.refreshError)
        let more = Task { await vm.loadMore() }; await service.wait(3)
        let missing = Task { await vm.load() }; await service.wait(4)
        await service.fail(3, .httpError(statusCode: 404, body: nil)); await missing.value
        await service.reply(2, try page(2)); await more.value
        guard case .unavailable = vm.state else { return XCTFail("404 cannot be revived by delayed page") }
        XCTAssertNil(vm.context.identity)
    }

    @MainActor
    func testWrongSlugAndCancelledRepliesCannotReplaceLastGood() async throws {
        let service = ThemeReaderService(), vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let wrong = Task { await vm.load() }; await service.wait(2)
        await service.reply(1, try ContainerHubFixture.decode()); await wrong.value
        XCTAssertEqual(try loaded(vm).response.slug, "ai"); XCTAssertNotNil(vm.refreshError)
        let cancelled = Task { await vm.loadMore() }; await service.wait(3); cancelled.cancel()
        await service.reply(2, try page(2)); await cancelled.value
        XCTAssertEqual(try loaded(vm).members.count, 1); XCTAssertFalse(vm.isLoadingMore)
    }
    @MainActor
    func testSameRevisionRefreshAndPageDeduplicateWithoutLosingBackContext() async throws {
        let service = ThemeReaderService()
        let vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let more = Task { await vm.loadMore() }; await service.wait(2)
        let refresh = Task { await vm.load() }; await service.wait(3)
        await service.reply(2, try page()); await refresh.value
        await service.reply(1, try page(2)); await more.value
        let first = try XCTUnwrap(loaded(vm).members.first)
        vm.opened(first); vm.scrolled(to: first.id)
        let back = Task { await vm.load() }; await service.wait(4)
        await service.reply(3, try page()); await service.wait(5)
        await service.reply(4, try page(2)); await back.value
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201, 9202])
        XCTAssertEqual(vm.context.scrollMemberId, first.id)
        XCTAssertEqual(try loaded(vm).countLabel, "2 of 2 markets loaded")
    }

    @MainActor
    func testPageTransportFailureKeepsInventoryAndOffersRetry() async throws {
        let service = ThemeReaderService()
        let vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let failed = Task { await vm.loadMore() }; await service.wait(2)
        await service.fail(1, .httpError(statusCode: 503, body: nil)); await failed.value
        XCTAssertNotNil(vm.pageError); XCTAssertFalse(vm.isLoadingMore)
        XCTAssertEqual(try loaded(vm).members.count, 1)
        let retry = Task { await vm.loadMore() }; await service.wait(3)
        await service.reply(2, try page(2)); await retry.value
        XCTAssertNil(vm.pageError); XCTAssertEqual(try loaded(vm).members.count, 2)
    }

    private func withheldPage(_ number: Int) throws -> ContainerHubResponse {
        try page(number) { value in
            let sections = value["sections"] as! [[String: Any]]
            let members = sections[0]["members"] as! [[String: Any]]
            value["sections"] = []
            value["member_count"] = 0
            value["withheld_count"] = 1
            value["withheld"] = [["type": "market", "id": members[0]["id"]!, "reason": "hydrate_failed"]]
        }
    }

    @MainActor
    func testFinalPageHydrationFailureRecoversWithoutRevisionBumpOrNextCursor() async throws {
        let service = ThemeReaderService()
        let vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let more = Task { await vm.loadMore() }; await service.wait(2)
        await service.reply(1, try withheldPage(2)); await more.value
        XCTAssertNil(try loaded(vm).response.page?.nextCursor)
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201])
        XCTAssertTrue(try loaded(vm).isPartial)
        let refresh = Task { await vm.load() }; await service.wait(3)
        await service.reply(2, try page()); await service.wait(4)
        let retry = await service.request(3)
        XCTAssertEqual(retry.cursor, try page().page?.nextCursor)
        XCTAssertEqual(retry.revision, 7)
        await service.reply(3, try page(2)); await refresh.value
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201, 9202])
        XCTAssertFalse(try loaded(vm).isPartial)
    }

    @MainActor
    func testRestoringEarlierWithheldPageKeepsServerWindowOrder() async throws {
        let service = ThemeReaderService()
        let vm = ContainerHubViewModel(slug: "ai", service: service)
        try await seed(vm, service)
        let more = Task { await vm.loadMore() }; await service.wait(2)
        await service.reply(1, try page(2)); await more.value
        let withheld = Task { await vm.load() }; await service.wait(3)
        await service.reply(2, try withheldPage(1)); await service.wait(4)
        await service.reply(3, try page(2)); await withheld.value
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9202])
        XCTAssertEqual(try loaded(vm).response.withheldCount, 1)
        XCTAssertTrue(try loaded(vm).isPartial)
        let restored = Task { await vm.load() }; await service.wait(5)
        await service.reply(4, try page()); await service.wait(6)
        await service.reply(5, try page(2)); await restored.value
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201, 9202])
        XCTAssertEqual(try loaded(vm).response.revision, 7)
    }

    @MainActor
    func testInflightWindowRecoveryCannotReplaceNewRevisionOrWithdrawal() async throws {
        for terminal in [false, true] {
            let service = ThemeReaderService()
            let vm = ContainerHubViewModel(slug: "ai", service: service)
            try await seed(vm, service)
            let more = Task { await vm.loadMore() }; await service.wait(2)
            await service.reply(1, try withheldPage(2)); await more.value
            let recovery = Task { await vm.load() }; await service.wait(3)
            await service.reply(2, try page()); await service.wait(4)
            let newer = Task { await vm.load() }; await service.wait(5)
            await service.reply(4, try page { value in
                value["revision"] = 8
                if terminal { value["state"] = "withdrawn" }
            }); await newer.value
            await service.reply(3, try page(2)); await recovery.value
            XCTAssertEqual(try loaded(vm).response.revision, 8)
            XCTAssertEqual(try loaded(vm).members.map(\.memberId), terminal ? [] : [9201])
        }
    }

    @MainActor
    func testRecoveringEarlierClassKeepsSectionOrderAcrossVisitedWindows() async throws {
        let first = try page { value in
            var sections = value["sections"] as! [[String: Any]]
            sections[0]["class"] = "title"; value["sections"] = sections
            value["page"] = ["limit": 1, "next_cursor": "WzAsOTIwMV0"]
        }
        let missing = try page { value in
            value["sections"] = []; value["member_count"] = 0
            value["withheld_count"] = 1
            value["withheld"] = [["type": "market", "id": 9201, "reason": "hydrate_failed"]]
            value["page"] = ["limit": 1, "next_cursor": "WzAsOTIwMV0"]
        }
        let service = ThemeReaderService()
        let vm = ContainerHubViewModel(slug: "ai", service: service)
        let initial = Task { await vm.load() }; await service.wait(1)
        await service.reply(0, first); await initial.value
        let more = Task { await vm.loadMore() }; await service.wait(2)
        await service.reply(1, try page(2)); await more.value
        let failure = Task { await vm.load() }; await service.wait(3)
        await service.reply(2, missing); await service.wait(4)
        await service.reply(3, try page(2)); await failure.value
        XCTAssertEqual(try loaded(vm).sections.map(\.sectionClass), ["side_question"])
        let recovery = Task { await vm.load() }; await service.wait(5)
        await service.reply(4, first); await service.wait(6)
        await service.reply(5, try page(2)); await recovery.value
        XCTAssertEqual(try loaded(vm).sections.map(\.sectionClass), ["title", "side_question"])
        XCTAssertEqual(try loaded(vm).members.map(\.memberId), [9201, 9202])
    }

}
