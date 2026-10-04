import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #10236 — the During matrix MOUNTED on the actual `EventDetailView`, through
/// the ordinary `fetchGameMarkets` → `vm.gameMarkets` path, in the Player
/// Props slot, with the old card keeping only what the matrix does not draw.
///
/// FIXTURE: the same producer route-harness body as `EventPropsMatrix10236Tests`
/// (`Fixtures/game-markets-10236-during-matrix.route.json`) — the real
/// serializer's spelling on a mocked session, NOT production prices.
@MainActor
final class EventPropsMatrixMounted10236Tests: XCTestCase {
    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10236-during-matrix.route.json")

    private func specimen() throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    private static func decode(_ dict: [String: Any]) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private static func legacyProp(_ json: String) throws -> GameMarketPlayerProp {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketPlayerProp.self, from: Data(json.utf8))
    }

    // MARK: - Which legacy props the old card still draws

    func testEveryLegacyPropTheMatrixDrawsLeavesTheOldCard() throws {
        let body = try Self.decode(specimen())
        let legacy = try XCTUnwrap(body.playerProps)
        XCTAssertEqual(legacy.count, 11, "control: the route body carries its legacy rows")
        XCTAssertEqual(EventPropsMatrixLayout.untypedPlayerProps(legacy, typed: body.duringPlayerProps), [])
    }

    func testAnUntypedPropAndAnIdlessPropStayInTheOldCard() throws {
        let body = try Self.decode(specimen())
        let untyped = try Self.legacyProp(#"{"market_name":"Juan Soto: Home Runs O/U 0.5","outcome_name":"Over","threshold":0.5,"over_probability":0.2,"source":"polymarket","movement":null,"player_headshot":null,"player_team":null,"actual":null,"hit":null,"pregame_mark":null,"_market_id":900,"contributor_outcome_ids":[9001]}"#)
        let idless = try Self.legacyProp(#"{"market_name":"Aaron Judge: Hits O/U 1.5","outcome_name":"Over","threshold":1.5,"over_probability":0.5,"source":"polymarket","movement":null,"player_headshot":null,"player_team":null,"actual":null,"hit":null,"pregame_mark":null}"#)
        let kept = EventPropsMatrixLayout.untypedPlayerProps(
            (body.playerProps ?? []) + [untyped, idless], typed: body.duringPlayerProps)
        XCTAssertEqual(kept.map(\.marketName), [untyped.marketName, idless.marketName])
    }

    func testWithNoTypedPayloadTheOldCardIsExactlyAsBefore() throws {
        var dict = try specimen()
        let legacy = try XCTUnwrap(Self.decode(dict).playerProps)
        dict["during_player_props"] = NSNull()
        XCTAssertNil(try Self.decode(dict).duringPlayerProps)
        XCTAssertEqual(EventPropsMatrixLayout.untypedPlayerProps(legacy, typed: nil), legacy)
        var empty = try specimen()
        var during = try XCTUnwrap(empty["during_player_props"] as? [String: Any])
        during["rows"] = [Any]()
        empty["during_player_props"] = during
        XCTAssertEqual(EventPropsMatrixLayout.untypedPlayerProps(
            legacy, typed: try Self.decode(empty).duringPlayerProps), legacy)
    }

    // MARK: - The page mounts it once, in the Player Props slot

    private func page() throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testThePageMountsTheMatrixOnceAboveTheFilteredOldCard() throws {
        let src = try page()
        XCTAssertEqual(src.components(separatedBy: "EventPropsMatrixView(").count - 1, 1)
        XCTAssertEqual(src.components(separatedBy: "PlayerPropsCardView(").count - 1, 1)
        let matrix = try XCTUnwrap(src.range(of: "EventPropsMatrixView("))
        let filter = try XCTUnwrap(src.range(of: "EventPropsMatrixLayout.untypedPlayerProps("))
        let card = try XCTUnwrap(src.range(of: "PlayerPropsCardView("))
        let spectrum = try XCTUnwrap(src.range(of: "TotalPointsSpectrumView("))
        XCTAssertLessThan(spectrum.lowerBound, matrix.lowerBound, "the matrix sits in the Player Props slot")
        XCTAssertLessThan(matrix.lowerBound, filter.lowerBound)
        XCTAssertLessThan(filter.lowerBound, card.lowerBound, "the old card is fed only the untyped props")
        XCTAssertFalse(src.contains("let playerProps = gameMarkets.playerProps,"),
                       "the old card must not read the unfiltered list")
    }

    // MARK: - Rendered on the actual page (route-harness data, labelled)

    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        let markets: GameMarketsResponse
        init(markets: GameMarketsResponse) throws {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            event = try decoder.decode(EventDetail.self, from: Data(#"{"id":15320207,"home_team":"San Diego Padres","away_team":"New York Yankees","sport":"baseball_mlb","status":"live","home_score":2,"away_score":3,"current_odds":{"home_probability":0.42,"away_probability":0.58,"home_rendered_percent":42,"away_rendered_percent":58},"hero_probability":0.42,"hero_probability_source":"blend","win_probability_sources":{"kalshi":{"value":0.42,"updated_at":"2026-10-03T07:08:50Z"}}}"#.utf8))
            self.markets = markets
        }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { markets }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class PageHandle: LiveStreamHandle, @unchecked Sendable {
        var callbacks: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        var isConnecting = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            callbacks[event, default: []].append(handler)
        }
        func close() {}
        func open() { for handler in callbacks["open"] ?? [] { handler("") } }
    }

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func shot(_ host: UIViewController, _ name: String) throws -> UIImage {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("props-matrix-mounted-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Props matrix mounted rendered evidence (route-harness data): \(url.path)")
        return image
    }

    private func lines(_ image: UIImage) throws -> [String] {
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    /// The page's own scroll view — the one SwiftUI `ScrollView` backs onto.
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

    /// Scrolls the actual page one screen at a time, the way a reader does, and
    /// returns each frame's recognised lines; frames are saved as evidence.
    private func frames(_ host: UIViewController, _ name: String) throws -> [[String]] {
        let scroll = try XCTUnwrap(pageScroll(in: host.view), "\(name): the page has a scroll view")
        var result: [[String]] = []
        var y: CGFloat = 0, index = 0
        repeat {
            scroll.setContentOffset(CGPoint(x: 0, y: y), animated: false)
            settle(host, 0.25)
            result.append(try lines(shot(host, "\(name)-frame\(index)")))
            y += scroll.bounds.height * 0.8; index += 1
        } while y < scroll.contentSize.height && index < 30
        return result
    }

    func testTheActualPageDrawsTheHeroAndTheHitsMatrixAtPhoneAndAccessibilitySizes() async throws {
        let markets = try Self.decode(specimen())
        for (name, size) in [("page-390", DynamicTypeSize.large),
                             ("page-390-ax3", .accessibility3),
                             ("page-390-ax5", .accessibility5)] {
            let client = try PageClient(markets: markets), handle = PageHandle()
            let vm = EventDetailViewModel(eventId: 15320207, client: client, makeStreamHandle: { _ in handle })
            await vm.load(); handle.open()
            XCTAssertEqual(vm.gameMarkets?.duringPlayerProps?.rows.count, 12,
                           "control: the ordinary game-markets path adopted the typed rows")
            let page = NavigationStack { EventDetailView(eventId: 15320207, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(page, at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            let win = UIWindow(frame: host.view.frame)
            win.rootViewController = host; win.isHidden = false
            defer { vm.stopRefresh(); win.isHidden = true }
            settle(host, 0.6)
            let all = try frames(host, name)
            let hero = all[0].joined(separator: " ")
            XCTAssertTrue(hero.contains("58%") && hero.contains("42%"), "\(name): the hero leads the page: \(hero)")
            let at = try XCTUnwrap(all.firstIndex { $0.contains { $0.contains("Live Player") } },
                                   "\(name): the matrix is on the page: \(all)")
            print("Props matrix mounted (route-harness data): \(name) matrix at frame\(at)")
            let slot = all[at...].prefix(3).flatMap { $0 }
            let text = slot.joined(separator: " ")
            for word in ["Hits", "Judge", "Soto", "Tatis"] {
                XCTAssertTrue(text.contains(word), "\(name): \(word) missing: \(slot)")
            }
            let everything = all.flatMap { $0 }
            XCTAssertFalse(everything.contains { $0.trimmingCharacters(in: .whitespaces) == "Player Props" },
                           "\(name): the old card's duplicate count list is back")
            XCTAssertFalse(everything.contains { $0.contains("Unpriced prop") }, "\(name): the old card is back")
            if size == .large {
                for figure in ["1+", "2+", "3+", "4+", "48%", "24%", "15%"] {
                    XCTAssertTrue(slot.contains { $0.contains(figure) }, "\(name): \(figure) missing: \(slot)")
                }
            }
        }
    }
}
