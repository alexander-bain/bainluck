import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #10238 — two runtime conditions sol-web's mount review left unpaid
/// (issuecomment-5978067028), run on the ACTUAL `EventDetailView` through the
/// ordinary `fetchGameMarkets` / `fetchRelatedFutures` → view-model path:
///
///   1. An open Series still shows when the Game beside it has NO price — no
///      hero price and every Game option unpriced. (The #10420 host only ever
///      withdrew the open option's own price.)
///   2. A Series alone does NOT silence "No prediction markets for this game";
///      a drawn Game question does. (Until now only the unit predicate
///      `gameMarketsHaveContent` covered this — the host draws the sections,
///      not the page.)
///
/// FIXTURES: the 10238 route-harness bodies (`Fixtures/*10238*.route-harness.json`),
/// relabelled and with prices withdrawn below. Synthetic page inputs — NOT
/// production data, and not a natural event.
@MainActor
final class EventQuestionMatrixPageRuntime10238Tests: XCTestCase {
    private static var fixtures: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures")
    }
    private static let eventId = 15_310_238

    private func object(_ name: String) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(
            with: Data(contentsOf: Self.fixtures.appendingPathComponent(name))) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    /// The open Series: Red Sox 70% / Yankees 29% on its winner question.
    private func openSeries() throws -> RelatedFuturesResponse {
        var dict = try object("related-futures-10238-series-matrix.route-harness.json")
        dict["event_id"] = Self.eventId
        dict["event_status"] = "scheduled"
        return try decode(RelatedFuturesResponse.self, dict)
    }

    /// Game markets with every legacy section empty. `gameMatrix` picks what
    /// sits in the Game slot: nil, one priced question, or the same question
    /// with every option's price withdrawn.
    private enum GameSlot { case none, priced, unpriced }

    private func gameMarkets(_ slot: GameSlot) throws -> GameMarketsResponse {
        var dict = try object("game-markets-10238-question-matrix.route-harness.json")
        for key in ["spreads", "totals", "team_totals", "period_markets", "player_props", "other", "matchups"] {
            dict[key] = [Any]()
        }
        dict["open_winner_quote"] = NSNull()
        dict["during_player_props"] = NSNull()
        dict["event_id"] = Self.eventId
        dict["status"] = "scheduled"
        dict["home_team"] = "Boston Red Sox"
        dict["away_team"] = "New York Yankees"
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        let questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        // The three-way period winner, relabelled for this game.
        var question = try XCTUnwrap(questions.first {
            ($0["label"] as? String)?.contains("Result after 3 quarters") == true
        })
        question["label"] = "Red Sox vs Yankees: Result after 5 innings"
        question["market_name"] = "Red Sox vs Yankees: Result after 5 innings"
        let names = ["Boston Red Sox", "Tie", "New York Yankees"]
        let values: [Double] = [0.56, 0.08, 0.36]
        var options = try XCTUnwrap(question["options"] as? [[String: Any]])
        XCTAssertEqual(options.count, 3, "control: the specimen question is three-way")
        for i in options.indices {
            options[i]["label"] = names[i]
            var published = try XCTUnwrap(options[i]["published"] as? [String: Any])
            var evidence = try XCTUnwrap(options[i]["source_evidence"] as? [[String: Any]])
            switch slot {
            case .priced, .none:
                published["value"] = values[i]
                published["value_state"] = "quoted"
                for j in evidence.indices { evidence[j]["raw_probability"] = values[i] }
            case .unpriced:
                // The server's spelling of a leg with no price (event_question_matrix.py).
                published["value"] = NSNull()
                published["value_state"] = "unpriced"
                published["basis"] = "unknown"
                for j in evidence.indices { evidence[j]["raw_probability"] = NSNull() }
            }
            options[i]["published"] = published
            options[i]["source_evidence"] = evidence
        }
        question["options"] = options
        matrix["questions"] = [question]
        dict["game_question_matrix"] = slot == .none ? NSNull() : matrix
        return try decode(GameMarketsResponse.self, dict)
    }

    // MARK: - The actual page

    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        let markets: GameMarketsResponse
        let related: RelatedFuturesResponse
        init(markets: GameMarketsResponse, related: RelatedFuturesResponse) throws {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            // No current_odds, no hero probability: the Game itself has no price.
            event = try decoder.decode(EventDetail.self, from: Data(#"{"id":15310238,"home_team":"Boston Red Sox","away_team":"New York Yankees","sport":"baseball_mlb","status":"scheduled","commence_time":"2030-10-04T23:05:00Z","event_tags":["competitive_structure:series"]}"#.utf8))
            self.markets = markets
            self.related = related
        }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { related }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { markets }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class PageHandle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var isConnecting = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() {}
    }

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func lines(_ host: UIViewController, _ name: String) throws -> [String] {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("question-matrix-page-10238-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("10238 page runtime rendered evidence (synthetic inputs): \(url.path)")
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func pageScroll(in view: UIView) -> UIScrollView? {
        var best: UIScrollView?
        func walk(_ v: UIView) {
            if let s = v as? UIScrollView, s.contentSize.height > s.bounds.height,
               s.contentSize.height > (best?.contentSize.height ?? 0) { best = s }
            v.subviews.forEach(walk)
        }
        walk(view)
        return best
    }

    /// Renders the page and returns every line a reader could scroll to.
    private func readPage(_ markets: GameMarketsResponse, _ related: RelatedFuturesResponse,
                          _ name: String, at size: DynamicTypeSize = .large) async throws -> [String] {
        let client = try PageClient(markets: markets, related: related), handle = PageHandle()
        let vm = EventDetailViewModel(eventId: Self.eventId, client: client, makeStreamHandle: { _ in handle })
        await vm.load()
        XCTAssertNotNil(vm.relatedFutures?.seriesQuestionMatrix, "\(name): control — the page adopted the Series")
        XCTAssertNotNil(vm.gameMarkets, "\(name): control — the page adopted game markets")
        XCTAssertNil(vm.event?.currentOdds, "\(name): control — the Game has no hero price")
        let page = NavigationStack { EventDetailView(eventId: Self.eventId, viewModel: vm) }
            .environmentObject(PinManager())
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
        let host = hostForMeasurement(page, at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let win = UIWindow(frame: host.view.frame)
        win.rootViewController = host; win.isHidden = false
        defer { vm.stopRefresh(); win.isHidden = true }
        settle(host, 0.6)
        var all = try lines(host, "\(name)-frame0")
        if let scroll = pageScroll(in: host.view) {
            var y = scroll.bounds.height * 0.8, index = 1
            while y < scroll.contentSize.height && index < 30 {
                scroll.setContentOffset(CGPoint(x: 0, y: y), animated: false)
                settle(host, 0.25)
                all += try lines(host, "\(name)-frame\(index)")
                y += scroll.bounds.height * 0.8; index += 1
            }
        }
        return all
    }

    private func has(_ all: [String], _ text: String) -> Bool { all.contains { $0.contains(text) } }
    /// The page's own copy for a not-yet-finished game, minus the final
    /// punctuation OCR may drop.
    private static let note = String(EventState.noGameMarketsLine(status: "scheduled").dropLast(5))

    // MARK: 1 — Series beside a Game with no price

    func testAnOpenSeriesStillShowsBesideAGameWithNoPrice() async throws {
        let markets = try gameMarkets(.unpriced)
        XCTAssertTrue(EventQuestionMatrixAdapter.rows(in: markets.gameQuestionMatrix, scope: .game)
            .flatMap(\.options).allSatisfy { $0.value == .unavailable },
                      "control: every Game option is unpriced")
        for (name, size) in [("no-game-price", DynamicTypeSize.large), ("no-game-price-ax3", .accessibility3)] {
            let all = try await readPage(markets, try openSeries(), name, at: size)
            XCTAssertTrue(has(all, "Series odds"), "\(name): the open Series vanished: \(all)")
            XCTAssertTrue(has(all, "Boston Red Sox") && has(all, "70%"), "\(name): the Series price is gone: \(all)")
            XCTAssertTrue(has(all, "29%"), "\(name): the Series' second side is gone or rewritten: \(all)")
            XCTAssertFalse(has(all, "30%"), "\(name): 70/29 was normalised: \(all)")
            XCTAssertTrue(has(all, "Game odds"), "\(name): the unpriced Game question is not drawn: \(all)")
            for withdrawn in ["56%", "36%", "8%"] {
                XCTAssertFalse(all.contains { $0.trimmingCharacters(in: .whitespaces) == withdrawn },
                               "\(name): a withdrawn Game price \(withdrawn) is on the page: \(all)")
            }
            XCTAssertFalse(has(all, "No prediction markets"),
                           "\(name): the empty note sits beside a drawn Game question: \(all)")
        }
    }

    // MARK: 2 — a Series alone does not silence the empty note

    func testASeriesAloneDoesNotSilenceTheNoGameMarketsNote() async throws {
        let all = try await readPage(try gameMarkets(.none), try openSeries(), "series-alone")
        XCTAssertTrue(has(all, Self.note), "a Series alone silenced '\(Self.note)': \(all)")
        XCTAssertTrue(has(all, "Series odds") && has(all, "70%"), "the Series is not drawn: \(all)")
        XCTAssertFalse(has(all, "Game odds"), "a Game section drew with no Game matrix: \(all)")
    }

    /// Control for 2: the same page with a priced Game question has no note,
    /// so arm 2 is reading the note and not an always-present string.
    func testAGameQuestionBesideTheSeriesSilencesTheNote() async throws {
        let all = try await readPage(try gameMarkets(.priced), try openSeries(), "game-and-series")
        XCTAssertFalse(has(all, "No prediction markets"), "the note sits beside a drawn Game question: \(all)")
        XCTAssertTrue(has(all, "Game odds") && has(all, "56%"), "control: the Game question is drawn: \(all)")
        XCTAssertTrue(has(all, "Series odds") && has(all, "70%"), "the Series is not drawn: \(all)")
    }
}
