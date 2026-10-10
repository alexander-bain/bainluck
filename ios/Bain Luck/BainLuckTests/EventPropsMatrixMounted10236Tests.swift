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

    func testThePageMountsTheMatrixOnceAboveTheFilteredOldCardAheadOfTheMaps() throws {
        let src = try page()
        XCTAssertEqual(src.components(separatedBy: "EventPropsMatrixView(").count - 1, 1)
        XCTAssertEqual(src.components(separatedBy: "PlayerPropsCardView(").count - 1, 1)
        let matrix = try XCTUnwrap(src.range(of: "EventPropsMatrixView("))
        let filter = try XCTUnwrap(src.range(of: "EventPropsMatrixLayout.untypedPlayerProps("))
        let card = try XCTUnwrap(src.range(of: "PlayerPropsCardView("))
        // #9483 C2 — the questions follow the score context and lead the maps
        // and the spectrum.
        let after = try XCTUnwrap(src.range(of: "AfterPropsMatrixView("))
        let projection = try XCTUnwrap(src.range(of: "ProjectedFinalPointsChartView("))
        let maps = try XCTUnwrap(src.range(of: "MarketMapView("))
        let spectrum = try XCTUnwrap(src.range(of: "TotalPointsSpectrumView("))
        XCTAssertLessThan(projection.lowerBound, after.lowerBound, "the questions follow the score context")
        XCTAssertLessThan(after.lowerBound, matrix.lowerBound, "the After grid and During matrix are one phased mount")
        XCTAssertLessThan(matrix.lowerBound, filter.lowerBound)
        XCTAssertLessThan(filter.lowerBound, card.lowerBound, "the old card is fed only the untyped props")
        XCTAssertLessThan(card.lowerBound, maps.lowerBound, "the questions sit ahead of the maps")
        XCTAssertLessThan(maps.lowerBound, spectrum.lowerBound)
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
        try observations(XCTUnwrap(image.cgImage)).map(\.text)
    }

    /// Recognised lines with their boxes in Vision's normalised, bottom-left space.
    private func observations(_ image: CGImage, correcting: Bool = true) throws -> [(text: String, box: CGRect)] {
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        request.usesLanguageCorrection = correcting
        try VNImageRequestHandler(cgImage: image).perform([request])
        return (request.results ?? []).compactMap { o in o.topCandidates(1).first.map { ($0.string, o.boundingBox) } }
    }

    /// #10796 — the hero's probability row, in pixels: the union of the
    /// first-frame lines carrying either team's number, padded. At AX3 the
    /// whole-frame reading of the drawn "58% — 42%" came back "58 - - 42"
    /// (Root inspected the pixels: both percent signs are drawn), so the row
    /// is read again on its own, one team's half at a time.
    private func heroRow(_ image: CGImage, numbers: [String]) throws -> CGRect? {
        let w = CGFloat(image.width), h = CGFloat(image.height)
        let boxes = try observations(image).filter { line in numbers.contains { line.text.contains($0) } }
            .map { CGRect(x: $0.box.minX * w, y: (1 - $0.box.maxY) * h, width: $0.box.width * w, height: $0.box.height * h) }
            .filter { $0.minY < h / 2 }
        guard let first = boxes.first else { return nil }
        let row = boxes.dropFirst().reduce(first) { $0.union($1) }
        return row.insetBy(dx: -24, dy: -16).intersection(CGRect(x: 0, y: 0, width: w, height: h))
    }

    /// The row's left and right halves, each recognised on its own, without
    /// language correction, so a percent sign is read as drawn.
    private func heroHalves(_ image: CGImage, row: CGRect) throws -> (left: String, right: String) {
        let crop = try XCTUnwrap(image.cropping(to: row.integral))
        let half = crop.width / 2
        func read(_ x: Int, _ width: Int) throws -> String {
            let part = try XCTUnwrap(crop.cropping(to: CGRect(x: x, y: 0, width: width, height: crop.height)))
            return try observations(part, correcting: false).map(\.text).joined(separator: " ")
        }
        return (try read(0, half), try read(half, crop.width - half))
    }

    /// The same pixels with one rectangle (in pixels) painted over in the
    /// page's own background — a missing or clipped number.
    private func covering(_ image: CGImage, _ rect: CGRect) throws -> CGImage {
        let size = CGSize(width: image.width, height: image.height)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let out = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIImage(cgImage: image).draw(in: CGRect(origin: .zero, size: size))
            UIColor.white.setFill(); context.fill(rect)
        }
        return try XCTUnwrap(out.cgImage)
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
    private func frames(_ host: UIViewController, _ name: String) throws -> (lines: [[String]], first: CGImage) {
        let scroll = try XCTUnwrap(pageScroll(in: host.view), "\(name): the page has a scroll view")
        var result: [[String]] = []
        var first: CGImage?
        var y: CGFloat = 0, index = 0
        repeat {
            scroll.setContentOffset(CGPoint(x: 0, y: y), animated: false)
            settle(host, 0.25)
            let image = try shot(host, "\(name)-frame\(index)")
            if first == nil { first = image.cgImage }
            result.append(try lines(image))
            y += scroll.bounds.height * 0.8; index += 1
        } while y < scroll.contentSize.height && index < 30
        return (result, try XCTUnwrap(first))
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
            let (all, first) = try frames(host, name)
            // #10796 — the first frame's hero row, read on its own: the away
            // team's 58% on the left, the home team's 42% on the right, each
            // with its percent sign.
            let row = try XCTUnwrap(try heroRow(first, numbers: ["58", "42"]),
                                    "\(name): the hero leads the page: \(all[0])")
            let hero = try heroHalves(first, row: row)
            XCTAssertTrue(hero.left.contains("58%") && hero.right.contains("42%"),
                          "\(name): the hero leads the page: \(hero) in \(all[0])")
            // Negative controls on the same pixels: a missing number, and a
            // number whose percent sign is clipped, are both refused.
            let rightHalf = CGRect(x: row.midX, y: row.minY, width: row.width / 2, height: row.height)
            let missing = try heroHalves(covering(first, rightHalf), row: row)
            XCTAssertFalse(missing.right.contains("42%"), "\(name): a missing 42% still read: \(missing)")
            let leftSign = CGRect(x: row.minX + row.width * 0.25, y: row.minY, width: row.width * 0.25, height: row.height)
            let clipped = try heroHalves(covering(first, leftSign), row: row)
            XCTAssertFalse(clipped.left.contains("58%"), "\(name): a clipped 58% still read: \(clipped)")
            print("Hero row read (#10796): \(name) \(hero) | missing \(missing) | clipped \(clipped)")
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
