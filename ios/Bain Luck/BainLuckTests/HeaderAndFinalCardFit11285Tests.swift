import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #11285 (Design, build-66 renders) — two fit corrections on the NFL page.
///
/// What these pin, and the mutation each kills:
/// - the adopted info-only control back in the 150pt verdict slot (its glyph
///   centred ~75pt inward, `nfl-upcoming-375-large-p0`) →
///   `testTheAdoptedInfoControlIsACompactTargetAtTheTrailingEdge`,
///   `testThePageSizesTheControlByWhetherItPrintsWords`
/// - the legacy worded control losing its slot → `testAWordedControlKeepsTheVerdictSlot`
/// - a final card's stat category truncated beside its actual
///   ("Receiving Yar…" at AX3, `nfl-final-393-ax3-p1`) →
///   `testAFinalCardsStatCategoryWrapsBesideItsActualOnThePage`,
///   `testAFinalCardsStatCategoryWrapsInTheReader`
@MainActor
final class HeaderAndFinalCardFit11285Tests: XCTestCase {

    // MARK: - Info control

    func testAWordedControlKeepsTheVerdictSlot() {
        XCTAssertEqual(EventDetailView.probabilityDetailsMaxWidth(at: .large, statusInDetails: false),
                       EventDetailView.verdictSlotWidth)
        XCTAssertNil(EventDetailView.probabilityDetailsMaxWidth(at: .xxLarge, statusInDetails: false),
                     "above xxLarge the worded control keeps its full-width row")
        for size in [DynamicTypeSize.large, .xxLarge, .accessibility3] {
            XCTAssertNil(EventDetailView.probabilityDetailsMaxWidth(at: size, statusInDetails: true),
                         "\(size): the info-only control reserves no verdict slot")
        }
    }

    func testThePageSizesTheControlByWhetherItPrintsWords() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        let page = try String(contentsOf: url, encoding: .utf8)
        let start = try XCTUnwrap(page.range(of: "private func probabilityDetails(confidenceTier: String?, statusInDetails: Bool = false) -> some View {"))
        let end = try XCTUnwrap(page.range(of: "// MARK: - Chart Header Bar", range: start.upperBound..<page.endIndex))
        let body = String(page[start.upperBound..<end.lowerBound]).filter { !$0.isWhitespace }
        XCTAssertTrue(body.contains(".frame(maxWidth:Self.probabilityDetailsMaxWidth(at:dynamicTypeSize,statusInDetails:statusInDetails),minHeight:44)"))
        XCTAssertTrue(body.contains(".frame(minWidth:44,alignment:statusInDetails?.trailing:.center)"))
        XCTAssertFalse(body.contains("Self.heroVerdictWidth(at:dynamicTypeSize)"),
                       "the control reads the verdict slot directly again")
    }

    /// The control's frame chain as `probabilityDetails` mounts it, at the
    /// trailing side of a row (the adopted header's `Spacer` then control).
    private func row(statusInDetails: Bool, status: LiveUpdateStatus, width: CGFloat,
                     at size: DynamicTypeSize) -> some View {
        HStack(spacing: 0) {
            Spacer(minLength: 8)
            CompactEventPriceStatusView(status: status, sequence: 0, receivedAt: nil,
                                        isDisclosure: true, statusInDetails: statusInDetails)
                .frame(maxWidth: EventDetailView.probabilityDetailsMaxWidth(at: size, statusInDetails: statusInDetails),
                       minHeight: 44)
                .frame(minWidth: 44, alignment: statusInDetails ? .trailing : .center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(width: width)
        .background(Color.white)
        .environment(\.colorScheme, .light)
    }

    /// Leftmost and rightmost columns (points) holding any non-white ink.
    private func inkSpan<V: View>(_ view: V, at size: DynamicTypeSize, name: String) throws -> ClosedRange<CGFloat> {
        let renderer = rendererForMeasurement(view, at: size)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) did not render")
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("header-fit-11285-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Header fit rendered evidence: \(url.path)")
        let cg = try XCTUnwrap(image.cgImage)
        let (w, h) = (cg.width, cg.height)
        var px = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                                          space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        var lo = Int.max, hi = Int.min
        for y in 0..<h {
            for x in 0..<w {
                let i = (y * w + x) * 4
                if min(px[i], px[i + 1], px[i + 2]) < 200 { lo = min(lo, x); hi = max(hi, x) }
            }
        }
        XCTAssertLessThanOrEqual(lo, hi, "\(name): control — the glyph drew")
        return CGFloat(lo) / 3...CGFloat(hi) / 3
    }

    func testTheAdoptedInfoControlIsACompactTargetAtTheTrailingEdge() throws {
        for width in [CGFloat(343), 361] {
            for (status, size) in [(LiveUpdateStatus.awaitingUpdate, DynamicTypeSize.large),
                                   (.live, .large), (.interrupted, .large), (.awaitingUpdate, .xLarge)] {
                let name = "info-\(Int(width))-\(status)-\(size)"
                let ink = try inkSpan(row(statusInDetails: true, status: status, width: width, at: size),
                                      at: size, name: name)
                // The glyph sits in the trailing 44pt target, at the row's edge
                // (the capsule's own 5pt inset plus the symbol's side bearing).
                XCTAssertGreaterThanOrEqual(ink.lowerBound, width - 44, "\(name): \(ink) floats inward")
                XCTAssertGreaterThanOrEqual(ink.upperBound, width - 12, "\(name): \(ink) is off the trailing edge")
            }
        }
    }

    // MARK: - Final card stat category

    // The defect lives on the PAGE: the r2 specimen mounted the real
    // EventDetailView at 393×852, AX3, over the retained Bears–Eagles response,
    // and the peeking deck card read "Receiving Yar…" beside DeVonta Smith and
    // his final 65. A standalone card in a tall window wraps with or without
    // the fix (r1's mutant survived), so these mount the same page, and the
    // reader at its own width, and read the category directly above the name.

    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        let markets: GameMarketsResponse
        init(event: EventDetail, markets: GameMarketsResponse) { self.event = event; self.markets = markets }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
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

    private func finalPage() throws -> (EventDetail, GameMarketsResponse) {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/event-14780549-game-markets-9585-bears-eagles.20260928.json")
        var markets = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        markets["status"] = "completed"
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: [
            "id": 14780549, "home_team": "Chicago Bears", "away_team": "Philadelphia Eagles",
            "sport": "americanfootball_nfl", "status": "completed", "home_score": 17, "away_score": 24,
            "commence_time": "2026-09-28T17:00:00Z", "completed_at": "2026-09-28T20:20:00Z",
        ] as [String: Any]))
        return (event, try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: markets)))
    }

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private struct Line { let text: String; let box: CGRect }

    /// The window's pixels, read by Vision; boxes in points, origin top-left.
    private func lines(_ host: UIViewController, name: String) throws -> [Line] {
        let bounds = host.view.bounds
        let image = UIGraphicsImageRenderer(bounds: bounds).image { _ in
            host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("final-card-fit-11285-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Final card fit rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { o in
            o.topCandidates(1).first.map { c in
                let b = o.boundingBox
                return Line(text: c.string, box: CGRect(x: b.minX * bounds.width, y: (1 - b.maxY) * bounds.height,
                                                        width: b.width * bounds.width, height: b.height * bounds.height))
            }
        }
    }

    /// The story card's header: the name's first line ("DeVon-" at AX5, which
    /// Vision can read together with "final"), the final figure at the card's
    /// right (top-aligned with the category, so up to ~100pt above the name;
    /// Vision may read it on the category's own line), and every line stacked
    /// directly above the name in its column — the category, however many lines
    /// it takes. Nil when this frame does not show that header whole, clear of
    /// the bar on top.
    private func header(in lines: [Line], player: String, actual: String) -> (category: String, all: String)? {
        for name in lines.filter({ $0.text.contains(player) }).sorted(by: { $0.box.minY < $1.box.minY }) {
            guard lines.contains(where: { $0.text.contains(actual) && $0.box.maxX > name.box.minX + 180
                    && $0.box.minY < name.box.maxY + 20 && $0.box.maxY > name.box.minY - 100 }) else { continue }
            // Walk up the column while the lines sit close (measured 11–21pt
            // between category lines and the name); the card's top padding
            // (34pt+ to the deck's heading) ends the category.
            var above: [Line] = []
            var edge = name.box.minY
            for line in lines.filter({ $0.box.maxY <= name.box.minY + 4 && abs($0.box.minX - name.box.minX) < 24 })
                .sorted(by: { $0.box.maxY > $1.box.maxY }) {
                guard edge - line.box.maxY < 26 else { break }
                above.insert(line, at: 0)
                edge = line.box.minY
            }
            guard let top = above.first, top.box.minY > 110 else { continue }
            return (above.map(\.text).joined(separator: " "), lines.map(\.text).joined(separator: " | "))
        }
        return nil
    }

    /// What Vision read near the player, for a failure message.
    private func near(_ lines: [Line], player: String) -> String {
        guard let name = lines.first(where: { $0.text.contains(player) }) else { return "" }
        return lines.filter { abs($0.box.midY - name.box.midY) < 160 }
            .map { "\($0.text)@\(Int($0.box.minX))-\(Int($0.box.maxX)),\(Int($0.box.minY))-\(Int($0.box.maxY))" }
            .joined(separator: " | ")
    }

    private func assertCategory(_ found: (category: String, all: String)?, _ name: String, seen: String) {
        guard let found else {
            return XCTFail("\(name): the DeVonta Smith card with its final 65 was not found; near the name: \(seen)")
        }
        XCTAssertTrue(found.category.contains("Receiving"), "\(name): category read \"\(found.category)\" — \(found.all)")
        XCTAssertTrue(found.category.contains("Yards"), "\(name): the category is truncated: \"\(found.category)\"")
        XCTAssertFalse(found.category.contains("…") || found.category.contains("..."),
                       "\(name): an ellipsis is drawn: \"\(found.category)\"")
    }

    func testAFinalCardsStatCategoryWrapsBesideItsActualOnThePage() async throws {
        let (event, markets) = try finalPage()
        // 393 is the r2 specimen; 375 the narrower control phone. Each scrolls
        // until the deck card's header is on screen whole.
        for (width, size) in [(CGFloat(393), DynamicTypeSize.accessibility3), (393, .accessibility5),
                              (375, .accessibility3)] {
            let name = "page-\(Int(width))-\(size)"
            let vm = EventDetailViewModel(eventId: event.id, client: PageClient(event: event, markets: markets),
                                          makeStreamHandle: { _ in PageHandle() })
            await vm.load()
            let view = NavigationStack { EventDetailView(eventId: event.id, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(view, at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: width < 380 ? 812 : 852)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { vm.stopRefresh(); window.isHidden = true }
            settle(host, 1.0)
            let scroller = try XCTUnwrap(Self.pageScroller(host.view), "\(name): the page scrolls")
            var found: (category: String, all: String)?
            var seen = ""
            var y: CGFloat = 0
            while found == nil, y <= 4000 {
                scroller.setContentOffset(CGPoint(x: 0, y: y), animated: false)
                settle(host, 0.4)
                let read = try lines(host, name: "\(name)-y\(Int(y))")
                found = header(in: read, player: "DeVon", actual: "65")
                let here = near(read, player: "DeVon")
                if !here.isEmpty { seen += " [y\(Int(y))] " + here }
                y += 240
            }
            assertCategory(found, name, seen: seen)
        }
    }

    func testAFinalCardsStatCategoryWrapsInTheReader() throws {
        let (_, markets) = try finalPage()
        let props = markets.playerProps ?? []
        let cards = NFLMilestoneCard9483.cards(props: props, eventStatus: "completed",
                                               commenceTime: ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!,
                                               homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles",
                                               now: ISO8601DateFormatter().date(from: "2026-09-28T21:00:00Z")!)
        let deck = cards.map { NFLEventCard9483.milestone($0) }
        let smith = try XCTUnwrap(cards.firstIndex { $0.player.contains("Smith") }, "control: the fixture's Smith card")
        XCTAssertEqual(cards[smith].actual, 65, "control: his final figure")
        XCTAssertEqual(cards[smith].stat, "Receiving Yards", "control: the specimen's category")
        // The reader's card is wider than the deck's and wrapped the category
        // even before the fix; this keeps it whole there, it does not pin the fix.
        for size in [DynamicTypeSize.accessibility3, .accessibility5] {
            let name = "reader-393-\(size)"
            let state = NFLCardDeckState9483()
            state.open(deck[smith].id)
            let reader = NFLCardReader9483(
                liveCards: deck,
                liveHeader: .init(match: "Eagles vs Bears · Final", chances: "Eagles 24 · Bears 17"),
                awayName: "Eagles", homeName: "Bears", awayColor: .teal, homeColor: .indigo,
                state: state, liveRows: NFLCardReaderHold9483.rows(for: deck, in: props))
            let host = hostForMeasurement(reader.environment(\.colorScheme, .light), at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: 393, height: 852)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            settle(host, 0.8)
            let read = try lines(host, name: name)
            assertCategory(header(in: read, player: "DeVon", actual: "65"), name, seen: near(read, player: "DeVon"))
        }
    }

    /// The page's own vertical scroller: the tallest-content one in the window.
    private static func pageScroller(_ view: UIView) -> UIScrollView? {
        var best: UIScrollView?
        func find(_ v: UIView) {
            if let s = v as? UIScrollView, s.contentSize.height > s.bounds.height + 1,
               s.contentSize.height > (best?.contentSize.height ?? 0) { best = s }
            v.subviews.forEach(find)
        }
        find(view)
        return best
    }
}
