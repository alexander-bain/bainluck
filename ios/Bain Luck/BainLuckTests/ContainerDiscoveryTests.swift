import Foundation
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

private nonisolated enum ContainerDiscoveryFixture {
    static func decode(mutate: ((inout [String: Any]) -> Void)? = nil) throws -> ContainerDiscoveryResponse {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("ContainerHubFixtures/browse_mlb.json")
        let envelope = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        var object = envelope["response"] as! [String: Any]
        mutate?(&object)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ContainerDiscoveryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    static func changeCard(_ object: inout [String: Any], _ change: (inout [String: Any]) -> Void) {
        var cards = object["collections"] as! [[String: Any]]
        change(&cards[0])
        object["collections"] = cards
    }

    static func nfl() throws -> ContainerDiscoveryResponse {
        try decode { object in
            changeCard(&object) { card in
                card["slug"] = "nfl-2026-week-5"
                card["name"] = "NFL 2026 · Week 5"
                card["text"] = "NFL 2026 · Week 5"
                card["edition"] = ["kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 5]
                card["destination"] = ["kind": "container", "slug": "nfl-2026-week-5", "api": "/api/containers/nfl-2026-week-5"]
            }
        }
    }

    static let empty = try! decode { $0["collections"] = [] }
    static let now = ISO8601DateFormatter().date(from: "2026-09-30T12:00:00Z")!
}

final class ContainerDiscoveryContractTests: XCTestCase {
    private let request = ContainerDiscoveryRequest(league: .mlb, season: 2026)

    @MainActor
    func testBankedProducerNamesCountsAndDestinationReachExistingHub() throws {
        let response = try ContainerDiscoveryFixture.decode()
        let entry = try XCTUnwrap(request.entries(in: response).first)
        XCTAssertEqual(entry.collection.name, "MLB 2026 · Postseason")
        XCTAssertEqual(entry.subtitle, "9 games · 6 questions")
        XCTAssertEqual(entry.collection.revision, 2)
        XCTAssertEqual(entry.route, .containerHub(slug: "mlb-2026-postseason", name: "MLB 2026 · Postseason"))
    }

    func testAbsentNullAndEmptyOptionalListHideSection() throws {
        for response in [
            try ContainerDiscoveryFixture.decode { $0.removeValue(forKey: "collections") },
            try ContainerDiscoveryFixture.decode { $0["collections"] = NSNull() },
            ContainerDiscoveryFixture.empty,
        ] {
            XCTAssertTrue(request.entries(in: response).isEmpty)
        }
    }

    func testMalformedAndNewCardCannotEraseHealthySibling() throws {
        let response = try ContainerDiscoveryFixture.decode { object in
            var cards = object["collections"] as! [[String: Any]]
            cards.insert(["type": "future_type", "name": "Unsupported"], at: 0)
            cards.append(["type": "collection", "id": "bad"])
            object["collections"] = cards
        }
        XCTAssertEqual(request.entries(in: response).map(\.id), ["mlb-2026-postseason"])
    }

    func testUnpublishedRevokedAndUnknownStateCannotBeOffered() throws {
        for state in ["unpublished", "withdrawn", "revoked", "new_state"] {
            let response = try ContainerDiscoveryFixture.decode { object in
                ContainerDiscoveryFixture.changeCard(&object) { $0["state"] = state }
            }
            XCTAssertTrue(request.entries(in: response).isEmpty, state)
        }
    }

    func testWrongEditionSeasonAndAPIDestinationCannotBeOffered() throws {
        let mutations: [(inout [String: Any]) -> Void] = [
            { $0["edition"] = ["kind": "nfl_week", "league": "nfl", "season": 2026] },
            { $0["edition"] = ["kind": "mlb_postseason", "league": "mlb", "season": 2025] },
            { $0["slug"] = "mlb-2025-postseason" },
            { $0["destination"] = ["kind": "container", "slug": "mlb-2026-postseason", "api": "https://other.example/api/containers/mlb-2026-postseason"] },
            { $0["destination"] = ["kind": "container", "slug": "nfl-2026-week-5", "api": "/api/containers/nfl-2026-week-5"] },
            { $0["revision"] = 0 },
            { $0["name"] = "  " },
        ]
        for mutation in mutations {
            let response = try ContainerDiscoveryFixture.decode { object in
                ContainerDiscoveryFixture.changeCard(&object, mutation)
            }
            XCTAssertTrue(request.entries(in: response).isEmpty)
        }
    }

    func testEmptyNegativeCountsAndDuplicateCardsDoNotDecorateBrowse() throws {
        for counts in [(0, 0), (-1, 6), (9, -1)] {
            let response = try ContainerDiscoveryFixture.decode { object in
                ContainerDiscoveryFixture.changeCard(&object) { $0["game_count"] = counts.0; $0["question_count"] = counts.1 }
            }
            XCTAssertTrue(request.entries(in: response).isEmpty)
        }
        let duplicated = try ContainerDiscoveryFixture.decode { object in
            let cards = object["collections"] as! [[String: Any]]
            object["collections"] = cards + cards
        }
        XCTAssertEqual(request.entries(in: duplicated).count, 1)
    }

    func testCountsUseSuppliedInventoryAndSingularLabels() throws {
        let response = try ContainerDiscoveryFixture.decode { object in
            ContainerDiscoveryFixture.changeCard(&object) { $0["game_count"] = 0; $0["question_count"] = 1 }
        }
        XCTAssertEqual(request.entries(in: response).first?.subtitle, "1 question")
    }

    func testNFLStageWeekAndSlugMustRoundTripWithoutGuessing() throws {
        let nfl = ContainerDiscoveryRequest(league: .nfl, season: 2026)
        XCTAssertEqual(nfl.entries(in: try ContainerDiscoveryFixture.nfl()).map(\.id), ["nfl-2026-week-5"])
        XCTAssertTrue(request.entries(in: try ContainerDiscoveryFixture.nfl()).isEmpty)
        // A matching destination cannot legitimize a conflicting stage.
        let wrong = try ContainerDiscoveryFixture.decode { object in
            ContainerDiscoveryFixture.changeCard(&object) { card in
                card["edition"] = ["kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Post Season", "week": 5]
                card["slug"] = "nfl-2026-week-5"
                card["destination"] = ["kind": "container", "slug": "nfl-2026-week-5", "api": "/api/containers/nfl-2026-week-5"]
            }
        }
        XCTAssertTrue(nfl.entries(in: wrong).isEmpty)
    }

    func testRequestsFollowExistingUTCSeasonConventionAcrossYearBoundary() throws {
        let formatter = ISO8601DateFormatter()
        for (stamp, nfl, mlb) in [
            ("2026-09-30T12:00:00Z", 2026, 2026),
            ("2027-01-01T00:00:00Z", 2026, 2027),
            ("2027-02-28T23:59:59Z", 2026, 2027),
            ("2027-03-01T00:00:00Z", 2027, 2027),
            ("2026-11-01T00:00:00Z", 2026, 2027),
        ] {
            let now = try XCTUnwrap(formatter.date(from: stamp))
            XCTAssertEqual(ContainerDiscoveryLeague.nfl.season(asOf: now), nfl)
            XCTAssertEqual(ContainerDiscoveryLeague.mlb.season(asOf: now), mlb)
        }
        XCTAssertEqual(request.query, ["league": "mlb", "season": "2026", "limit": "20"])
    }

    func testBrowseWiringLeavesTheLeagueCatalogAndRouteReceiverIntact() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let leagues = try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/LeaguesView.swift"), encoding: .utf8)
        XCTAssertTrue(leagues.contains("BrowseCollectionsView()"))
        XCTAssertTrue(leagues.contains("leagueSections"))
        XCTAssertTrue(leagues.contains(".navigationDestination(for: Route.self)"))
        XCTAssertTrue(leagues.contains("path.append(route)"))
        let view = try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/BrowseCollectionsView.swift"), encoding: .utf8)
        XCTAssertTrue(view.contains("if !vm.entries.isEmpty"))
        XCTAssertTrue(view.contains("NavigationLink(value: entry.route)"))
        XCTAssertTrue(view.contains("Text(entry.collection.name)"))
        XCTAssertTrue(view.contains("Text(entry.subtitle)"))
    }
}

private actor ContainerDiscoveryScriptedService: ContainerDiscoveryLoading {
    enum Result: Sendable { case response(ContainerDiscoveryResponse), failure }
    private var script: [ContainerDiscoveryLeague: [Result]]
    private(set) var requests: [ContainerDiscoveryRequest] = []
    init(_ script: [ContainerDiscoveryLeague: [Result]]) { self.script = script }
    func load(_ request: ContainerDiscoveryRequest) async throws -> ContainerDiscoveryResponse {
        requests.append(request)
        guard var results = script[request.league], !results.isEmpty else {
            throw APIError.httpError(statusCode: 404, body: nil)
        }
        let result = results.removeFirst()
        script[request.league] = results
        switch result {
        case .response(let response): return response
        case .failure: throw APIError.httpError(statusCode: 503, body: nil)
        }
    }
}

private actor ContainerDiscoveryDeferredService: ContainerDiscoveryLoading {
    private var pending: [(ContainerDiscoveryRequest, CheckedContinuation<ContainerDiscoveryResponse, Error>?)] = []
    private let signals: [Int: XCTestExpectation]
    private var stopped = false
    init(signals: [Int: XCTestExpectation]) { self.signals = signals }
    func load(_ request: ContainerDiscoveryRequest) async throws -> ContainerDiscoveryResponse {
        try await withCheckedThrowingContinuation { continuation in
            guard !stopped else {
                continuation.resume(throwing: CancellationError())
                return
            }
            pending.append((request, continuation))
            signals[pending.count]?.fulfill()
        }
    }
    func finish(from start: Int, through end: Int, mlb: ContainerDiscoveryResponse) {
        guard pending.count >= end else { return }
        for index in start..<end {
            let (request, continuation) = pending[index]
            pending[index].1 = nil
            continuation?.resume(returning: request.league == .mlb ? mlb : ContainerDiscoveryFixture.empty)
        }
    }
    func stop() {
        stopped = true
        for index in pending.indices {
            let continuation = pending[index].1
            pending[index].1 = nil
            continuation?.resume(throwing: CancellationError())
        }
    }
}

final class ContainerDiscoveryViewModelTests: XCTestCase {
    @MainActor
    func testOneMissingLeagueDoesNotHideTheOtherAndReturnRefreshRemovesRevokedList() async throws {
        let mlb = try ContainerDiscoveryFixture.decode()
        let service = ContainerDiscoveryScriptedService([
            .nfl: [.failure, .response(ContainerDiscoveryFixture.empty)],
            .mlb: [.response(mlb), .response(ContainerDiscoveryFixture.empty)],
        ])
        let vm = ContainerDiscoveryViewModel(service: service)
        await vm.load(asOf: ContainerDiscoveryFixture.now)
        XCTAssertEqual(vm.entries.map(\.id), ["mlb-2026-postseason"])
        XCTAssertEqual(vm.failedLeagues, [.nfl])
        await vm.load(asOf: ContainerDiscoveryFixture.now)
        XCTAssertTrue(vm.entries.isEmpty)
        XCTAssertTrue(vm.failedLeagues.isEmpty)
        let requests = await service.requests
        XCTAssertEqual(requests.count, 4)
        XCTAssertTrue(requests.allSatisfy { $0.season == 2026 })
    }

    @MainActor
    func testOlderPublishedReadCannotUndoNewerEmptyRead() async throws {
        let firstStarted = expectation(description: "both first requests started")
        let secondStarted = expectation(description: "both second requests started")
        let service = ContainerDiscoveryDeferredService(signals: [2: firstStarted, 4: secondStarted])
        let vm = ContainerDiscoveryViewModel(service: service)
        let older = Task { await vm.load(asOf: ContainerDiscoveryFixture.now) }
        await fulfillment(of: [firstStarted], timeout: 2)
        let newer = Task { await vm.load(asOf: ContainerDiscoveryFixture.now) }
        await fulfillment(of: [secondStarted], timeout: 2)
        await service.finish(from: 2, through: 4, mlb: ContainerDiscoveryFixture.empty)
        // Drain on a failed signal too, so a timeout never strands fake reads.
        await service.finish(from: 0, through: 2, mlb: try ContainerDiscoveryFixture.decode())
        await service.stop()
        await newer.value
        await older.value
        XCTAssertTrue(vm.entries.isEmpty)
        XCTAssertTrue(vm.failedLeagues.isEmpty)
    }
}

/// #9989 — build 33 decoded both published NFL weeks and drew neither: the
/// section's `.task` sat on a `Group` that is empty until the first read lands,
/// so the first read never started. This runs the real view, on screen, with no
/// entries, and asks only whether a read begins.
final class BrowseCollectionsViewStartsItsFirstRead9989Tests: XCTestCase {
    @MainActor
    func testTheFirstReadStartsWhileTheSectionHasNoEntries() async throws {
        let started = expectation(description: "a discovery read started")
        let service = ContainerDiscoveryDeferredService(signals: [1: started])
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow()
        window.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        // Hosted the way Browse hosts it: a sibling inside a stack. As a root view
        // an empty `Group` still carries its modifiers, so a bare host is vacuous.
        let browse = ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                Text("Browse")
                BrowseCollectionsView(service: service)
                Text("Leagues")
            }
        }
        window.rootViewController = hostForMeasurement(browse)
        window.makeKeyAndVisible()
        await fulfillment(of: [started], timeout: 3)
        await service.stop()
        window.isHidden = true
        window.rootViewController = nil
    }
}
