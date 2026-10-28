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
/// - the story card's name broken mid-word beside the final figure ("DeVon-"
///   at AX5, r5 page-393) → `assertIdentity` in the same two tests; the
///   default row kept beside the figure → `testTheDefaultSizeKeepsTheStoryCardRow`
/// - the Projected finish card's label cut short in the stacked layout
///   ("pregame proje…" at AX5, r9 axxxxl-8) → `testTheProjectedFinishLabelsReadWholeInTheDeck`
/// - the Projected finish card too narrow for "Commanders" on a 320pt screen
///   at AX5 even at the name's 0.8 floor (lane1 0531Z) → the 320 width in
///   both Projected finish tests
/// - the Projected finish chart's marks drawn across its team-name label
///   ("Comm▪an◻ders" at AX5, Design 06b/07b) → `testTheProjectedFinishChartsMarksClearItsTeamNames`
/// - the compact NBA page's story stream still peeking at 320pt/AX5, so its
///   Projected finish card read "Timberwo…" (Design 0610Z) →
///   `testTheNBAStreamsProjectedFinishReadsWholeNames`
/// - the "Game stories" heading broken mid-word beside its count ("Game
///   sto-ries" at 320pt/AX5, deck and stream) → `testTheGameStoriesHeadingWrapsBetweenWords`
/// - the expanded reader's match line and kicker broken mid-word at
///   320pt/AX5 ("Comman-/ders", "PROJECT-/ED", Design q1) →
///   `testTheExpandedReaderKeepsWordsWholeOnANarrowPhone`
/// - the expanded reader's live header taking ~70% of a 320pt phone at AX5,
///   leaving the card only its kicker above the footer (Design, narrow-reader
///   residual 2) → `testTheExpandedReaderLeavesTheStoryRoomOnANarrowPhone`,
///   and the headline under the kicker in every case of the test above
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

    private struct Line { let text: String; let box: CGRect; var frame: CGImage? = nil; var bounds: CGRect = .zero }

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

    private struct Header { let category: String; let name: Line; let figure: Line; let all: [Line] }

    /// The story card's header: the name's first line ("DeVon-" when it broke
    /// mid-word, which Vision can read together with "final"), the final figure
    /// at the card's right, and the category: every line in the name's column
    /// from the figure's top (the row is top-aligned; Vision may read the figure
    /// on the category's own line) down to the name. Nil when this frame does
    /// not show that header whole, clear of the bar on top.
    private func header(in lines: [Line], player: String, actual: String) -> Header? {
        for name in lines.filter({ $0.text.contains(player) }).sorted(by: { $0.box.minY < $1.box.minY }) {
            guard let figure = lines.filter({ $0.text.contains(actual) && $0.box.maxX > name.box.minX + 180
                    && $0.box.minY < name.box.maxY + 20 && $0.box.maxY > name.box.minY - 140 })
                .min(by: { $0.box.minY < $1.box.minY }) else { continue }
            let above = lines.filter { $0.box.minY >= figure.box.minY - 12 && $0.box.maxY <= name.box.minY + 4
                && abs($0.box.minX - name.box.minX) < 24 }
                .sorted { $0.box.minY < $1.box.minY }
            guard let top = above.first, top.box.minY > 110 else { continue }
            return Header(category: above.map(\.text).joined(separator: " "), name: name, figure: figure, all: lines)
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

    private func assertCategory(_ found: Header?, _ name: String, seen: String) {
        guard let found else {
            return XCTFail("\(name): the DeVonta Smith card with its final 65 was not found; near the name: \(seen)")
        }
        let all = found.all.map(\.text).joined(separator: " | ")
        XCTAssertTrue(found.category.contains("Receiving"), "\(name): category read \"\(found.category)\" — \(all)")
        XCTAssertTrue(found.category.contains("Yards"), "\(name): the category is truncated: \"\(found.category)\"")
        XCTAssertFalse(found.category.contains("…") || found.category.contains("..."),
                       "\(name): an ellipsis is drawn: \"\(found.category)\"")
    }

    /// At accessibility sizes the name takes the card's whole width under the
    /// category and figure (Design 0220Z), so its first line is a whole word,
    /// never "DeVon-". The deck card is too narrow at AX3 for "DeVonta Smith" on
    /// one line either way, and beside the figure only page-393/AX5 broke the
    /// name ("DeVon- / ta / Smith", r5), so that frame is the one that tells the
    /// reflow from the old row; the others keep the name whole. The name below
    /// the figure's top line holds in both layouts (the category's two lines
    /// push it down); it rules out an overlap, it does not pin the reflow.
    private func assertIdentity(_ found: Header?, _ name: String) {
        guard let found else { return }
        let all = found.all.map(\.text).joined(separator: " | ")
        XCTAssertTrue(found.name.text.hasPrefix("DeVonta"),
                      "\(name): the name's first line read \"\(found.name.text)\" — \(all)")
        XCTAssertFalse(found.all.contains { $0.text.contains("DeVon-") }, "\(name): the name broke mid-word — \(all)")
        XCTAssertGreaterThanOrEqual(found.name.box.minY, found.figure.box.maxY,
                                    "\(name): the name overlaps the figure's row — \(all)")
    }

    /// The real page at `width`, scrolled until the deck card's header is on
    /// screen whole; the header (nil when never found) and what was read near
    /// the name on the way.
    private func pageHeader(width: CGFloat, size: DynamicTypeSize, name: String) async throws -> (Header?, String) {
        let (event, markets) = try finalPage()
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
        var found: Header?
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
        return (found, seen)
    }

    func testAFinalCardsStatCategoryWrapsBesideItsActualOnThePage() async throws {
        // 393 is the r2 specimen; 375 the narrower control phone.
        for (width, size) in [(CGFloat(393), DynamicTypeSize.accessibility3), (393, .accessibility5),
                              (375, .accessibility3)] {
            let name = "page-\(Int(width))-\(size)"
            let (found, seen) = try await pageHeader(width: width, size: size, name: name)
            assertCategory(found, name, seen: seen)
            assertIdentity(found, name)
        }
    }

    /// Default sizes keep the existing row: the name under the category and
    /// beside the final figure, never moved under it.
    func testTheDefaultSizeKeepsTheStoryCardRow() async throws {
        let name = "page-393-large"
        let (found, seen) = try await pageHeader(width: 393, size: .large, name: name)
        assertCategory(found, name, seen: seen)
        guard let found else { return }
        let all = found.all.map(\.text).joined(separator: " | ")
        XCTAssertTrue(found.name.text.hasPrefix("DeVonta Smith"), "\(name): the name read \"\(found.name.text)\" — \(all)")
        XCTAssertLessThan(found.name.box.minY, found.figure.box.maxY,
                          "\(name): the name left the figure's row at the default size — \(all)")
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
            let found = header(in: read, player: "DeVon", actual: "65")
            assertCategory(found, name, seen: near(read, player: "DeVon"))
            assertIdentity(found, name)
        }
    }

    // MARK: - Projected finish labels

    /// The r9 specimen's card: live, 49ers (home) 29.5 pregame and 33 projected
    /// now, built through the page's own builder from a pregame and a current
    /// capture either side of the first observed game state.
    private func liveFinishCard() throws -> NFLFinishCard9483 {
        let base = Date(timeIntervalSince1970: 1_791_000_000)
        func t(_ minutes: Double) -> Date { base.addingTimeInterval(minutes * 60) }
        let card = try XCTUnwrap(NFLFinishCard9483.build(.init(
            sportKey: "americanfootball_nfl", sourceKey: "draftkings", basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [.init(at: t(-30), home: 29.5, away: 21.5, homeProbability: nil, kind: .recorded),
                    .init(at: t(30), home: 33, away: 13.5, homeProbability: nil, kind: .recorded)],
            actuals: [], kickoffAt: nil, scoreObservationStartAt: t(0), finalAt: nil,
            asOf: t(40), windowStartAt: nil, requestCutoffAt: nil)), "control: the builder deals the card")
        XCTAssertEqual(card.phase, .during, "control: live, not final")
        XCTAssertEqual(card.projectedNow?.home, 33, "control: a current projection")
        XCTAssertNil(card.final, "control: no final score")
        return card
    }

    /// A label's lines, read whole, strictly between the number it belongs to
    /// and the next line down: no ellipsis, no line drawn over either.
    private func assertLabel(_ label: ArraySlice<Line>, reads expected: String, under above: Line, over below: Line,
                             _ name: String, all: String) {
        let text = label.map(\.text).joined(separator: " ")
        XCTAssertEqual(text.filter(\.isLetter), expected.filter(\.isLetter),
                       "\(name): the label read \"\(text)\" between \"\(above.text)\" and \"\(below.text)\" — \(all)")
        guard let first = label.first, let last = label.last else { return }
        XCTAssertGreaterThanOrEqual(first.box.minY, above.box.maxY, "\(name): \"\(first.text)\" overlaps \"\(above.text)\" above")
        XCTAssertLessThanOrEqual(last.box.maxY, below.box.minY, "\(name): \"\(last.text)\" overlaps \"\(below.text)\" below")
    }

    /// r9: on the page deck at the largest size the live card's stacked layout
    /// printed "pregame proje…". Mounted as the page mounts it — the deck with
    /// a neighbouring card (so the 0.86 width) inside a vertical scroller at
    /// the page's 16pt margin — each team row reads name, number, its whole
    /// label, number, its whole label, top to bottom, then the whole legend.
    func testTheProjectedFinishLabelsReadWholeInTheDeck() throws {
        let finish = try liveFinishCard()
        let (_, markets) = try finalPage()
        let neighbour = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: markets.playerProps ?? [], eventStatus: "completed",
            commenceTime: ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!,
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles",
            now: ISO8601DateFormatter().date(from: "2026-09-28T21:00:00Z")!).first, "control: a second card")
        // The names the page passes (`nflNames`): the r9 game, WAS at SF.
        let (away, home) = TeamShortName.shortPair(away: "Washington Commanders", home: "San Francisco 49ers",
                                                   sportKey: "americanfootball_nfl")
        // 320 is a phone under Display Zoom (lane1 0531Z): there the peeking
        // card is too narrow for "Commanders" even at its 0.8 floor, so the
        // deck gives each card the whole width at accessibility sizes.
        XCTAssertEqual(NFLEventCardDeckView9483.cardWidth(288, count: 2, accessibility: true), 288)
        XCTAssertEqual(NFLEventCardDeckView9483.cardWidth(288, count: 2, accessibility: false), 288 * 0.86)
        XCTAssertEqual(NFLEventCardDeckView9483.cardWidth(343, count: 2, accessibility: true), 343 * 0.86)
        for width in [CGFloat(393), 375, 320] {
            let name = "finish-\(Int(width))-accessibility5"
            let deck = NFLEventCardDeckView9483(
                cards: [.finish(finish), .milestone(neighbour)], awayName: away, homeName: home,
                awayColor: .indigo, homeColor: .red, state: NFLCardDeckState9483())
            let view = ScrollView { deck.padding(.horizontal, 16) }.environment(\.colorScheme, .light)
            let host = hostForMeasurement(view, at: .accessibility5)
            // Tall enough to hold the whole card in one frame; the vertical
            // scroller proposes no height either way.
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2400)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            settle(host, 0.8)
            // The finish card only: the neighbour starts past its right edge.
            let cardRight = 16 + NFLEventCardDeckView9483.cardWidth(width - 32, count: 2, accessibility: true)
            let read = try tiledLines(host, name: name).filter { $0.box.minX < cardRight }
                .sorted { $0.box.minY < $1.box.minY }
            assertFinishCardReadsWhole(read, rows: [(away, "21.5", "13.5"), (home, "29.5", "33")], name)
        }
    }

    /// The live finish card's lines, top to bottom: no ellipsis; each team row
    /// reads its whole name on its own line over the pregame number, that
    /// number's whole label, the projected number and its whole label; then the
    /// whole live legend.
    private func assertFinishCardReadsWhole(_ read: [Line], rows: [(String, String, String)], _ name: String) {
        let all = read.map(\.text).joined(separator: " | ")
        XCTAssertFalse(read.contains { $0.text.contains("…") || $0.text.contains("...") },
                       "\(name): an ellipsis is drawn — \(all)")
        func index(_ text: String, after: Int) -> Int? {
            read.indices.first { $0 > after && read[$0].text.trimmingCharacters(in: .whitespaces) == text }
        }
        // Each row's two numbers, top to bottom (the axis ticks are
        // touchdowns, or twenties in basketball, never these).
        var marks: [(pregame: Int, now: Int)] = []
        for (_, pregame, now) in rows {
            guard let p = index(pregame, after: marks.last?.now ?? -1), let n = index(now, after: p) else { break }
            marks.append((p, n))
        }
        guard marks.count == rows.count,
              let legend = read.indices.first(where: { $0 > marks[1].now && read[$0].text.hasPrefix("Points") }) else {
            XCTFail("\(name): the rows' numbers and the legend did not read in order — \(all)")
            return
        }
        // A row ends at the next row's name, the last at the legend.
        let ends = [marks[1].pregame - 1, legend]
        for (i, (team, _, _)) in rows.enumerated() {
            let (p, n) = marks[i]
            guard p > 0 else { XCTFail("\(name): nothing reads over \(read[p].text) — \(all)"); continue }
            // The stacked layout: the whole name on its own line over the number.
            XCTAssertEqual(read[p - 1].text.trimmingCharacters(in: .whitespaces), team,
                           "\(name): the line over \(read[p].text) is not the whole name \(team) — \(all)")
            assertLabel(read[(p + 1)..<n], reads: "earlier forecast", under: read[p], over: read[n],
                        "\(name) \(team)", all: all)
            assertLabel(read[(n + 1)..<max(n + 1, ends[i])], reads: "projected now", under: read[n],
                        over: read[ends[i]], "\(name) \(team)", all: all)
        }
        // The live legend, whole, under the last row.
        let stop = read.indices.first { $0 > legend && read[$0].text.contains("Open") } ?? read.endIndex
        let text = read[legend..<stop].map(\.text).joined(separator: " ")
        // Letter case is folded, every letter still read: Vision read a lone
        // wrapped "now" as "noW" at 375/AX5 (A3, 2026-10-22).
        XCTAssertEqual(text.filter { $0.isLetter || $0 == "=" }.lowercased(), "pointsoutline=earlierforecastfilled=projectednow",
                       "\(name): the legend read \"\(text)\" — \(all)")
    }

    // MARK: - The compact NBA story stream

    /// A live NBA finish card through the page's own builder: Timberwolves
    /// (away) 108.5 pregame and 101 projected now, Trail Blazers (home) 112.5
    /// and 118.
    private func liveNBAFinishCard() throws -> NFLFinishCard9483 {
        let base = Date(timeIntervalSince1970: 1_791_000_000)
        func t(_ minutes: Double) -> Date { base.addingTimeInterval(minutes * 60) }
        let card = try XCTUnwrap(NFLFinishCard9483.build(.init(
            sportKey: "basketball_nba", sourceKey: "draftkings", basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [.init(at: t(-30), home: 112.5, away: 108.5, homeProbability: nil, kind: .recorded),
                    .init(at: t(30), home: 118, away: 101, homeProbability: nil, kind: .recorded)],
            actuals: [], kickoffAt: nil, scoreObservationStartAt: t(0), finalAt: nil,
            asOf: t(40), windowStartAt: nil, requestCutoffAt: nil)), "control: the builder deals the NBA card")
        XCTAssertEqual(card.phase, .during, "control: live, not final")
        XCTAssertEqual(card.projectedNow?.home, 118, "control: a current projection")
        XCTAssertNil(card.final, "control: no final score")
        return card
    }

    /// The page's NBA names (`nflNames`) for the longest names in the league.
    private func nbaNames() -> (away: String, home: String) {
        let names = TeamShortName.shortPair(away: "Minnesota Timberwolves", home: "Portland Trail Blazers",
                                            sportKey: "basketball_nba")
        XCTAssertEqual(names.away, "Timberwolves", "control: the page's short name")
        XCTAssertEqual(names.home, "Trail Blazers", "control: the page's short name")
        return names
    }

    /// The compact NBA page's deck: a live margin ladder and the finish card,
    /// as the page mounts it — the deck handed a stream page, so the stream
    /// replaces the deck's scroller — inside the page's vertical scroller at
    /// its 16pt margin. The plan puts the finish card last; the reader has
    /// swiped to it (the stream holds on it, and the shelf is scrolled there).
    private func nbaStreamHost(width: CGFloat, size: DynamicTypeSize, finish: NFLFinishCard9483,
                               names: (away: String, home: String)) -> (UIViewController, UIWindow) {
        let margin = NFLEventCard9483.ladder(NBALadderCard9483(
            family: .margin, phase: .during,
            points: [("o:m-away-3", -3.5, "\(names.away) by 4+", NBALadderCard9483.Side.away),
                     ("o:m-home-1", 1.5, "\(names.home) by 2+", .home),
                     ("o:m-home-5", 5.5, "\(names.home) by 6+", .home)].map { key, x, label, side in
                .init(optionKey: key, x: x, label: label, side: side, chance: nil, now: nil, observedAt: nil,
                      result: nil, detail: .init(label: label, marketName: label, source: "kalshi", quoted: nil,
                                                 observedAt: nil, baseline: nil, baselineObservedAt: nil,
                                                 result: nil))
            },
            actual: nil, forecast: nil, awayShort: names.away, homeShort: names.home))
        let cards: [NFLEventCard9483] = [margin, .finish(finish)]
        let state = NFLCardDeckState9483()
        let plan = NBAStoryStreamPolicy9483.plan(eventID: 11285, phase: .during, cards: cards, now: Date())
        XCTAssertEqual(plan.orderedIDs, ["margin", "finish"], "control: the stream's own order, finish last")
        state.beginNBAStream(plan)
        state.focusNBAStream(eventID: 11285, cardID: "finish", present: Set(plan.orderedIDs))
        let page = NBAStoryStreamView9483.Page(
            eventID: 11285, phase: .during, compact: true, supportsAutomaticScrollObservation: false,
            coordinateSpace: "nba-11285", signals: NBAStoryStreamView9483.Signals(), ready: true)
        let deck = NFLEventCardDeckView9483(cards: cards, awayName: names.away, homeName: names.home,
                                            awayColor: .blue, homeColor: .red, state: state, stream: page)
        let view = ScrollView { deck.padding(.horizontal, 16) }
            .coordinateSpace(name: "nba-11285")
            .environment(\.colorScheme, .light)
        let host = hostForMeasurement(view, at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2400)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        settle(host, 0.8)
        // The shelf at its end, where the last card is.
        if let shelf = Self.shelfScroller(host.view) {
            shelf.setContentOffset(CGPoint(x: shelf.contentSize.width - shelf.bounds.width, y: 0), animated: false)
            settle(host, 0.5)
        } else {
            XCTFail("control: no story shelf to scroll at \(Int(width))/\(size)")
        }
        return (host, window)
    }

    /// The story shelf: the widest-content horizontal scroller in the window.
    private static func shelfScroller(_ view: UIView) -> UIScrollView? {
        var best: UIScrollView?
        func find(_ v: UIView) {
            if let s = v as? UIScrollView, s.contentSize.width > s.bounds.width + 1,
               s.contentSize.width > (best?.contentSize.width ?? 0) { best = s }
            v.subviews.forEach(find)
        }
        find(view)
        return best
    }

    /// Design 0610Z: the compact NBA page's story stream kept the old peek at
    /// 320pt/AX5, so its Projected finish card had the 216pt the ordinary deck
    /// no longer gives and read "Timberwo…" ("Timberwolves" needs 0.70 of its
    /// size there; the floor is 0.8). Through the real stream route, at 393,
    /// 375 (which keep the peek) and 320, the finish card reads both whole
    /// names, its numbers, labels and legend.
    func testTheNBAStreamsProjectedFinishReadsWholeNames() throws {
        let finish = try liveNBAFinishCard()
        let (away, home) = nbaNames()
        for width in [CGFloat(393), 375, 320] {
            let name = "nba-stream-finish-\(Int(width))-accessibility5"
            let (host, window) = nbaStreamHost(width: width, size: .accessibility5, finish: finish,
                                               names: (away, home))
            defer { window.isHidden = true }
            // The last card ends at the shelf's trailing edge; the margin
            // ladder before it is left of its leading edge.
            let cardLeft = width - 16 - NFLEventCardDeckView9483.cardWidth(width - 32, count: 2, accessibility: true)
            let read = try tiledLines(host, name: name).filter { $0.box.minX >= cardLeft - 1 }
                .sorted { $0.box.minY < $1.box.minY }
            assertFinishCardReadsWhole(read, rows: [(away, "108.5", "101"), (home, "112.5", "118")], name)
        }
    }

    /// The ordinary deck (NFL), mounted as in the finish label test.
    private func deckHost(width: CGFloat, size: DynamicTypeSize,
                          cards: [NFLEventCard9483]) -> (UIViewController, UIWindow) {
        let deck = NFLEventCardDeckView9483(cards: cards, awayName: "Commanders", homeName: "49ers",
                                            awayColor: .indigo, homeColor: .red, state: NFLCardDeckState9483())
        let host = hostForMeasurement(ScrollView { deck.padding(.horizontal, 16) }
            .environment(\.colorScheme, .light), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2400)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        settle(host, 0.8)
        return (host, window)
    }

    /// The window's lines inside `band` (points), read by Vision at full
    /// scale. A whole 2400pt frame is downscaled: Vision then misses the
    /// heading's small grey count (a1's lesson) or misreads a glyph
    /// ("proiection" for "projection" in g1's drawn-whole frame).
    private func bandLines(_ image: UIImage, bounds: CGRect, band: CGRect) throws -> [Line] {
        let cg = try XCTUnwrap(image.cgImage)
        let scale = CGFloat(cg.width) / bounds.width
        let crop = try XCTUnwrap(cg.cropping(to: CGRect(x: band.minX * scale, y: band.minY * scale,
                                                        width: band.width * scale, height: band.height * scale)))
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.minimumTextHeight = 0
        try VNImageRequestHandler(cgImage: crop).perform([request])
        return (request.results ?? []).compactMap { o in
            o.topCandidates(1).first.map { c in
                let b = o.boundingBox
                return Line(text: c.string, box: CGRect(x: band.minX + b.minX * band.width,
                                                        y: band.minY + (1 - b.maxY) * band.height,
                                                        width: b.width * band.width, height: b.height * band.height),
                            frame: cg, bounds: bounds)
            }
        }
    }

    /// Renders the window, saves the evidence frame, returns it.
    private func frame(_ host: UIViewController, name: String) throws -> (UIImage, CGRect) {
        let bounds = host.view.bounds
        let image = UIGraphicsImageRenderer(bounds: bounds).image { _ in
            host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("final-card-fit-11285-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Final card fit rendered evidence: \(url.path)")
        return (image, bounds)
    }

    /// The top `height` points of the window.
    private func topLines(_ host: UIViewController, height: CGFloat, name: String) throws -> [Line] {
        let (image, bounds) = try frame(host, name: name)
        return try bandLines(image, bounds: bounds,
                             band: CGRect(x: 0, y: 0, width: bounds.width, height: min(height, bounds.height)))
    }

    /// The whole window in two overlapping halves, each read at full scale.
    /// Each line is kept from exactly one half, split by its centre at the
    /// middle of the overlap, which is wider than any line is tall.
    private func tiledLines(_ host: UIViewController, name: String) throws -> [Line] {
        let (image, bounds) = try frame(host, name: name)
        let mid = bounds.height / 2, overlap: CGFloat = 200
        let upper = try bandLines(image, bounds: bounds,
                                  band: CGRect(x: 0, y: 0, width: bounds.width, height: mid + overlap / 2))
        let lower = try bandLines(image, bounds: bounds,
                                  band: CGRect(x: 0, y: mid - overlap / 2, width: bounds.width,
                                               height: bounds.height - mid + overlap / 2))
        return upper.filter { $0.box.midY < mid } + lower.filter { $0.box.midY >= mid }
    }

    /// The deck's heading at the top of the frame: the lines above its count
    /// ("2 cards"), and the count.
    private func heading(_ read: [Line]) -> (title: [Line], count: Line)? {
        guard let c = read.firstIndex(where: { $0.text.trimmingCharacters(in: .whitespaces) == "2 cards" }) else {
            return nil
        }
        return (Array(read[..<c]), read[c])
    }

    /// Native 0559Z: at 320pt/AX5 the deck's heading broke its title mid-word
    /// beside the count ("Game sto-ries"), on the NFL deck and the NBA stream
    /// alike. There the title wraps between words with the count under it; at
    /// the default size, 320 and 393, the row is unchanged: the whole title
    /// with its count beside it.
    func testTheGameStoriesHeadingWrapsBetweenWords() throws {
        let (_, markets) = try finalPage()
        let neighbour = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: markets.playerProps ?? [], eventStatus: "completed",
            commenceTime: ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!,
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles",
            now: ISO8601DateFormatter().date(from: "2026-09-28T21:00:00Z")!).first, "control: a second card")
        let nfl = try liveFinishCard()
        let nba = try liveNBAFinishCard()
        let nbaTeams = nbaNames()
        for (width, size) in [(CGFloat(320), DynamicTypeSize.accessibility5), (320, .large), (393, .large)] {
            for route in ["deck", "stream"] {
                let name = "heading-\(route)-\(Int(width))-\(size)"
                let (host, window) = route == "deck"
                    ? deckHost(width: width, size: size, cards: [.finish(nfl), .milestone(neighbour)])
                    : nbaStreamHost(width: width, size: size, finish: nba, names: nbaTeams)
                defer { window.isHidden = true }
                let read = try topLines(host, height: 400, name: name).sorted { $0.box.minY < $1.box.minY }
                let all = read.prefix(8).map(\.text).joined(separator: " | ")
                guard let found = heading(read), !found.title.isEmpty else {
                    XCTFail("\(name): no title over a whole \"2 cards\" count — \(all)")
                    continue
                }
                let (title, count) = found
                // Every title line is whole words: the whole title, or one word.
                for line in title {
                    XCTAssertTrue(["Game stories", "Game", "stories"]
                        .contains(line.text.trimmingCharacters(in: .whitespaces)),
                                  "\(name): the title broke mid-word at \"\(line.text)\" — \(all)")
                }
                XCTAssertEqual(title.map(\.text).joined().filter(\.isLetter), "Gamestories",
                               "\(name): the title did not read whole over the count — \(all)")
                if size.isAccessibilitySize {
                    XCTAssertGreaterThanOrEqual(count.box.minY, title.last!.box.maxY - 1,
                                                "\(name): the count is not under the title — \(all)")
                } else {
                    // The ordinary row: one title line, the count beside it at the trailing edge.
                    XCTAssertEqual(title.count, 1, "\(name): the title wrapped — \(all)")
                    XCTAssertTrue((title[0].box.minY...title[0].box.maxY).contains(count.box.midY),
                                  "\(name): the count is not beside the title — \(all)")
                    XCTAssertGreaterThan(count.box.minX, width / 2, "\(name): the count left the trailing edge — \(all)")
                }
            }
        }
    }

    // MARK: - Projected finish chart names

    /// The window's RGBA pixels at the screen's scale.
    private struct Pixels {
        let data: [UInt8]; let width: Int; let height: Int; let scale: CGFloat

        /// The points in `rect` whose pixel passes `test` (r, g, b).
        func points(in rect: CGRect, _ test: (Int, Int, Int) -> Bool) -> [CGPoint] {
            var hits: [CGPoint] = []
            let x0 = max(0, Int(rect.minX * scale)), x1 = min(width, Int(rect.maxX * scale))
            let y0 = max(0, Int(rect.minY * scale)), y1 = min(height, Int(rect.maxY * scale))
            guard x0 < x1, y0 < y1 else { return [] }
            for y in y0..<y1 {
                for x in x0..<x1 {
                    let i = (y * width + x) * 4
                    if test(Int(data[i]), Int(data[i + 1]), Int(data[i + 2])) {
                        hits.append(CGPoint(x: CGFloat(x) / scale, y: CGFloat(y) / scale))
                    }
                }
            }
            return hits
        }

        /// A mark's colour: within 40 per channel of `rgb`.
        func points(_ rgb: (Int, Int, Int), in rect: CGRect) -> [CGPoint] {
            points(in: rect) { abs($0 - rgb.0) < 40 && abs($1 - rgb.1) < 40 && abs($2 - rgb.2) < 40 }
        }
    }

    /// The window's pixels, and Vision's lines read from the card's column
    /// only: in the whole 2400pt window the chart's small default-size names
    /// fall under Vision's minimum text height.
    private func cardFrame(_ host: UIViewController, cardRight: CGFloat, name: String) throws -> ([Line], Pixels) {
        let bounds = host.view.bounds
        let image = UIGraphicsImageRenderer(bounds: bounds).image { _ in
            host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("final-card-fit-11285-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Final card fit rendered evidence: \(url.path)")
        let cg = try XCTUnwrap(image.cgImage)
        let scale = CGFloat(cg.width) / bounds.width
        var px = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        let ctx = try XCTUnwrap(CGContext(data: &px, width: cg.width, height: cg.height, bitsPerComponent: 8,
                                          bytesPerRow: cg.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        let crop = CGRect(x: 0, y: 0, width: cardRight, height: min(bounds.height, 1200))
        let column = try XCTUnwrap(cg.cropping(to: CGRect(x: 0, y: 0, width: crop.width * scale, height: crop.height * scale)))
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.minimumTextHeight = 0
        try VNImageRequestHandler(cgImage: column).perform([request])
        let read = (request.results ?? []).compactMap { o in
            o.topCandidates(1).first.map { c in
                let b = o.boundingBox
                return Line(text: c.string, box: CGRect(x: b.minX * crop.width, y: (1 - b.maxY) * crop.height,
                                                        width: b.width * crop.width, height: b.height * crop.height))
            }
        }
        return (read.sorted { $0.box.minY < $1.box.minY },
                Pixels(data: px, width: cg.width, height: cg.height, scale: scale))
    }

    private static func rgb(_ color: Color) -> (Int, Int, Int) {
        let c = UIColor(color).resolvedColor(with: UITraitCollection(userInterfaceStyle: .light))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        c.getRed(&r, green: &g, blue: &b, alpha: &a)
        return (Int(r * 255), Int(g * 255), Int(b * 255))
    }

    /// The x centres of a team's two marks: its mark columns split at the
    /// widest gap (the outline square's centre is its span's middle).
    private static func markCentres(_ hits: [CGPoint]) -> [CGFloat] {
        let xs = Set(hits.map { ($0.x * 3).rounded() / 3 }).sorted()
        guard xs.count > 1 else { return [] }
        let split = (1..<xs.count).max { xs[$0] - xs[$0 - 1] < xs[$1] - xs[$1 - 1] }!
        return [(xs[0] + xs[split - 1]) / 2, (xs[split] + xs[xs.count - 1]) / 2]
    }

    /// Design 0521Z (06b/07b, and 08 before D3): at AX5 the chart drew its
    /// point marks across its own name label ("Comm▪an◻ders"). The chart prints
    /// each team's name at the top of the team's band; the marks must sit
    /// wholly below the name's ink, every mark still drawn, both teams on one
    /// points scale. Large text at 393, 375 and 320 (Display Zoom) is the defect; xxxLarge is where
    /// the marks first touched the name; the default size is the control that
    /// keeps its 120pt chart.
    func testTheProjectedFinishChartsMarksClearItsTeamNames() throws {
        XCTAssertEqual(NFLFinishCardView9483.chartHeight(expanded: false, nameLine: 16, axisFontSize: 12), 120,
                       "the default size keeps the deck chart's height")
        XCTAssertEqual(NFLFinishCardView9483.chartHeight(expanded: true, nameLine: 16, axisFontSize: 12), 220,
                       "the default size keeps the reader chart's height")
        let finish = try liveFinishCard()
        let (_, markets) = try finalPage()
        let neighbour = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: markets.playerProps ?? [], eventStatus: "completed",
            commenceTime: ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!,
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles",
            now: ISO8601DateFormatter().date(from: "2026-09-28T21:00:00Z")!).first, "control: a second card")
        let (away, home) = TeamShortName.shortPair(away: "Washington Commanders", home: "San Francisco 49ers",
                                                   sportKey: "americanfootball_nfl")
        let (awayColor, homeColor) = (Color.indigo, Color.red)
        for (width, size) in [(CGFloat(393), DynamicTypeSize.large), (393, .accessibility5), (375, .accessibility5),
                              (320, .accessibility5), (375, .xxxLarge)] {
            let name = "finish-chart-\(Int(width))-\(size)"
            let deck = NFLEventCardDeckView9483(
                cards: [.finish(finish), .milestone(neighbour)], awayName: away, homeName: home,
                awayColor: awayColor, homeColor: homeColor, state: NFLCardDeckState9483())
            let host = hostForMeasurement(ScrollView { deck.padding(.horizontal, 16) }
                .environment(\.colorScheme, .light), at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2400)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            settle(host, 0.8)
            let cardRight = 16 + NFLEventCardDeckView9483.cardWidth(width - 32, count: 2,
                                                                    accessibility: size.isAccessibilitySize)
            let (read, px) = try cardFrame(host, cardRight: cardRight, name: name)
            let all = read.map(\.text).joined(separator: " | ")
            func band(_ top: CGFloat, _ bottom: CGFloat) -> CGRect {
                CGRect(x: 16, y: top, width: cardRight - 16, height: bottom - top)
            }
            // A name's ink: the grey text's rows inside Vision's box (which runs
            // well below the glyphs at large sizes).
            func ink(_ label: Line) -> ClosedRange<CGFloat>? {
                let grey = px.points(in: label.box) { r, g, b in
                    abs(r - g) < 14 && abs(g - b) < 14 && (90...190).contains(r)
                }.map(\.y)
                guard let top = grey.min(), let bottom = grey.max() else { return nil }
                return top...bottom
            }
            // The chart's names sit above the rows' first number (the headline
            // names a team too, so a chart name is the first line under it that
            // starts with the name). Each found name is checked on its own: a
            // name the marks cross can read too broken to find.
            let rowsTop = read.first { $0.text.trimmingCharacters(in: .whitespaces) == "21.5" }?.box.minY ?? .infinity
            let a = read.first { $0.text.hasPrefix(String(away.prefix(3))) && $0.box.maxY < rowsTop }
            let h = read.first { $0.text.hasPrefix(String(home.prefix(3))) && $0.box.minY > (a?.box.maxY ?? .infinity)
                && $0.box.maxY < rowsTop }
            var inks: [ClosedRange<CGFloat>] = []
            for (team, label) in [(away, a), (home, h)] {
                guard let label else {
                    XCTFail("\(name): the chart's \(team) was not read — \(all)")
                    continue
                }
                XCTAssertEqual(label.text.filter { $0.isLetter || $0.isNumber }, team.filter { $0.isLetter || $0.isNumber },
                               "\(name): the chart's name read \"\(label.text)\" — \(all)")
                guard let rows = ink(label) else {
                    XCTFail("\(name): no grey ink in the chart's \"\(label.text)\" — \(all)")
                    continue
                }
                inks.append(rows)
                // No mark of either team on the name's ink rows.
                for (mark, rgb) in [(away, Self.rgb(awayColor)), (home, Self.rgb(homeColor))] {
                    let inside = px.points(rgb, in: band(rows.lowerBound, rows.upperBound + 1))
                    XCTAssertTrue(inside.isEmpty, "\(name): \(inside.count) \(mark) mark pixel(s) drawn across the chart's "
                                  + "\"\(label.text)\" (ink y \(Int(rows.lowerBound))–\(Int(rows.upperBound))), "
                                  + "first at \(inside.first.map { "\(Int($0.x)),\(Int($0.y))" } ?? "")")
                }
            }
            guard let a, let h, inks.count == 2 else { continue }
            let (aInk, hInk) = (inks[0], inks[1])
            // Each team's two marks are drawn under its name, in its band.
            let pitch = h.box.minY - a.box.minY
            let awayMarks = px.points(Self.rgb(awayColor), in: band(aInk.upperBound + 1, h.box.minY))
            let homeMarks = px.points(Self.rgb(homeColor), in: band(hInk.upperBound + 1, h.box.minY + pitch))
            let (ac, hc) = (Self.markCentres(awayMarks), Self.markCentres(homeMarks))
            guard ac.count == 2, hc.count == 2 else {
                XCTFail("\(name): the marks did not draw two per team under the names (\(ac), \(hc)) — \(all)")
                continue
            }
            // One points scale: Commanders 13.5 now / 21.5 pregame, 49ers 29.5
            // pregame / 33 now, read off the same points per unit.
            let awayScale = (ac[1] - ac[0]) / (21.5 - 13.5), homeScale = (hc[1] - hc[0]) / (33 - 29.5)
            XCTAssertEqual(awayScale, homeScale, accuracy: awayScale * 0.08,
                           "\(name): the teams' marks are on different scales (\(ac), \(hc))")
            XCTAssertEqual(hc[0] - ac[1], (29.5 - 21.5) * awayScale, accuracy: awayScale,
                           "\(name): the 49ers' pregame mark is not where one scale puts it (\(ac), \(hc))")
        }
    }

    // MARK: - The expanded reader on a narrow phone

    /// Design q1 (S2 `bfd25619e9`, 320x693 AX5): the expanded reader broke its
    /// match line "Comman-/ders at" and its card's kicker "PROJECT-/ED FINISH".
    /// There the reader gives back its own margin and the card's peek, and the
    /// type keeps its size; 375 and wider, and default sizes, are unchanged.
    /// Mounted as the page's `nflReader` mounts it: the live finish card through
    /// the page's builder, a neighbouring card, the page's short names and the
    /// rows the reader holds. The q1 header is the retained before case; the
    /// second is the shape `nflReaderHeader` prints live.
    func testTheExpandedReaderKeepsWordsWholeOnANarrowPhone() throws {
        XCTAssertEqual(NFLCardReader9483.headerMargin(width: 320, accessibility: true), 6)
        XCTAssertEqual(NFLCardReader9483.headerMargin(width: 320, accessibility: false), 18)
        XCTAssertEqual(NFLCardReader9483.headerMargin(width: 375, accessibility: true), 18)
        XCTAssertEqual(NFLCardReader9483.cardWidth(320, accessibility: true), 292)
        XCTAssertEqual(NFLCardReader9483.cardWidth(320, accessibility: false), 276)
        XCTAssertEqual(NFLCardReader9483.cardWidth(375, accessibility: true), 331)
        XCTAssertEqual(NFLCardReader9483.cardWidth(200, accessibility: false), 240, "the old floor")
        // A text-size change across the accessibility boundary resizes every
        // card at 320, so the rail must re-seat the open card; at 393 the
        // cards keep their width and the rail does not re-seat.
        let order = ["a", "b", "c"]
        XCTAssertNotEqual(NFLCardReader9483.railGeneration(width: 320, accessibility: true, order: order),
                          NFLCardReader9483.railGeneration(width: 320, accessibility: false, order: order),
                          "320: a Large-to-accessibility switch must re-seat the open card")
        XCTAssertEqual(NFLCardReader9483.railGeneration(width: 393, accessibility: true, order: order),
                       NFLCardReader9483.railGeneration(width: 393, accessibility: false, order: order),
                       "393: a text-size switch must not re-seat")

        let finish = try liveFinishCard()
        let (_, markets) = try finalPage()
        let props = markets.playerProps ?? []
        let neighbour = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props, eventStatus: "completed",
            commenceTime: ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!,
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles",
            now: ISO8601DateFormatter().date(from: "2026-09-28T21:00:00Z")!).first, "control: a second card")
        let (away, home) = TeamShortName.shortPair(away: "Washington Commanders", home: "San Francisco 49ers",
                                                   sportKey: "americanfootball_nfl")
        XCTAssertEqual(away, "Commanders", "control: the specimen's short name")
        let deck: [NFLEventCard9483] = [.finish(finish), .milestone(neighbour)]
        let q1 = NFLReaderHeader9483(match: "Commanders at 49ers · Live", chances: "Commanders 13 · 49ers 20")
        let live = NFLReaderHeader9483(match: "Commanders 13\u{2013}20 49ers · Q3 5:47",
                                       chances: "Win chances · Commanders 12% · 49ers 88%")
        for (label, header, width, height, size) in [
            ("q1", q1, CGFloat(320), CGFloat(693), DynamicTypeSize.accessibility5),
            ("live", live, 320, 693, .accessibility5),
            ("q1", q1, 393, 852, .accessibility5), ("q1", q1, 320, 693, .large),
        ] {
            let name = "reader-\(label)-\(Int(width))x\(Int(height))-\(size)"
            let state = NFLCardDeckState9483()
            state.open(deck[0].id)
            let reader = NFLCardReader9483(
                liveCards: deck, liveHeader: header, awayName: away, homeName: home,
                awayColor: .indigo, homeColor: .red,
                state: state, liveRows: NFLCardReaderHold9483.rows(for: deck, in: props))
            let host = hostForMeasurement(reader.environment(\.colorScheme, .light), at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            settle(host, 0.8)
            let read = try tiledLines(host, name: name).sorted { $0.box.minY < $1.box.minY }
            let all = read.map { "\($0.text)@\(Int($0.box.minX)),\(Int($0.box.minY))" }.joined(separator: " | ")
            XCTAssertEqual(state.openCardID, deck[0].id, "\(name): the reader left the card it was opened on")
            // No line ends in a break: "Comman-", "PROJECT-".
            XCTAssertFalse(read.contains { endsInWordBreak($0, in: read) },
                           "\(name): a word broke at a line end — \(all)")
            // The match line starts on the whole name, at the margin the rule gives.
            let match = try XCTUnwrap(read.first { $0.text.contains("Comman") }, "\(name): no match line — \(all)")
            XCTAssertTrue(match.text.hasPrefix("Commanders"), "\(name): the match line read \"\(match.text)\" — \(all)")
            let margin = NFLCardReader9483.headerMargin(width: width, accessibility: size.isAccessibilitySize)
            XCTAssertEqual(match.box.minX, margin, accuracy: 5, "\(name): the match line's margin — \(all)")
            // The card's kicker reads its whole first word, and under it the
            // card's headline starts on the leader's name ("49ers still …").
            let kicker = try XCTUnwrap(read.firstIndex { $0.text.contains("PROJECTED") },
                                       "\(name): the kicker broke — \(all)")
            // Since residual 2 the live header's chances line scrolls in its
            // band at 320/AX5, so the headline shows under the kicker there too.
            XCTAssertTrue(read[(kicker + 1)...].contains { $0.text.hasPrefix("49ers") },
                          "\(name): no headline under the kicker — \(all)")
            XCTAssertFalse(read.contains { $0.text.contains("…") || $0.text.contains("...") },
                           "\(name): an ellipsis is drawn — \(all)")
        }
    }

    /// #11285 (Design, narrow-reader residual 2) — at 320pt/AX5 the live
    /// header (the shape `nflReaderHeader` prints, as a literal) left the card
    /// only its kicker above the footer. There the chances line scrolls in a
    /// band of exactly its cap under the match line: the card has room to read,
    /// the score and state stay fixed above the band, and the chances are
    /// reached by scrolling the band, never removed. Where the rule does not
    /// apply (393/AX5, 320/Large) the chances line draws whole and no band is
    /// drawn.
    func testTheExpandedReaderLeavesTheStoryRoomOnANarrowPhone() throws {
        XCTAssertEqual(NFLCardReader9483.chancesMaxHeight(width: 320, height: 600, accessibility: true), 72)
        XCTAssertNil(NFLCardReader9483.chancesMaxHeight(width: 320, height: 600, accessibility: false))
        XCTAssertNil(NFLCardReader9483.chancesMaxHeight(width: 375, height: 700, accessibility: true))

        let finish = try liveFinishCard()
        let (_, markets) = try finalPage()
        let props = markets.playerProps ?? []
        let neighbour = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props, eventStatus: "completed",
            commenceTime: ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!,
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles",
            now: ISO8601DateFormatter().date(from: "2026-09-28T21:00:00Z")!).first, "control: a second card")
        let (away, home) = TeamShortName.shortPair(away: "Washington Commanders", home: "San Francisco 49ers",
                                                   sportKey: "americanfootball_nfl")
        let deck: [NFLEventCard9483] = [.finish(finish), .milestone(neighbour)]
        let live = NFLReaderHeader9483(match: "Commanders 13\u{2013}20 49ers · Q3 5:47",
                                       chances: "Win chances · Commanders 12% · 49ers 88%")
        for (width, height, size) in [
            (CGFloat(320), CGFloat(693), DynamicTypeSize.accessibility5),
            (393, 852, .accessibility5), (320, 693, .large),
        ] {
            let name = "reader-room-\(Int(width))x\(Int(height))-\(size)"
            let narrow = NFLCardReader9483.isNarrowAccessibility(width: width, accessibility: size.isAccessibilitySize)
            let state = NFLCardDeckState9483()
            state.open(deck[0].id)
            let reader = NFLCardReader9483(
                liveCards: deck, liveHeader: live, awayName: away, homeName: home,
                awayColor: .indigo, homeColor: .red,
                state: state, liveRows: NFLCardReaderHold9483.rows(for: deck, in: props))
            let host = hostForMeasurement(reader.environment(\.colorScheme, .light), at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            settle(host, 0.8)
            let read = try tiledLines(host, name: name).sorted { $0.box.minY < $1.box.minY }
            let all = read.map { "\($0.text)@\(Int($0.box.minX)),\(Int($0.box.minY))" }.joined(separator: " | ")
            // The score and the state stay on screen without scrolling.
            XCTAssertTrue(read.contains { $0.text.contains("13") && $0.text.contains("20") },
                          "\(name): the score left the screen — \(all)")
            XCTAssertTrue(read.contains { $0.text.contains("Q3") }, "\(name): the game state left the screen — \(all)")
            let kicker = try XCTUnwrap(read.firstIndex { $0.text.contains("PROJECTED") },
                                       "\(name): no kicker — \(all)")
            XCTAssertTrue(read[(kicker + 1)...].contains { $0.text.hasPrefix("49ers") },
                          "\(name): no headline under the kicker — \(all)")
            let band = Self.chancesBand(host.view, above: read[kicker].box.minY)
            if narrow {
                let scroller = try XCTUnwrap(band, "\(name): the chances line has no scrolling band — \(all)")
                XCTAssertFalse(read.contains { $0.text.contains("88%") },
                               "control: \(name): the band shows the whole chances line, so it banded nothing — \(all)")
                // The band is its cap: the reader's stack may not squeeze it
                // (to 0pt, the chances gone). The reader measures the safe area.
                let cap = try XCTUnwrap(NFLCardReader9483.chancesMaxHeight(
                    width: width, height: host.view.safeAreaLayoutGuide.layoutFrame.height, accessibility: true))
                XCTAssertEqual(scroller.bounds.height, cap, accuracy: 1,
                               "\(name): the band was squeezed below its cap — \(all)")
                // The score and the state sit above the band, outside it: by
                // position, not mere presence. The band's frame in its
                // superview, so its own offset cannot move the reference.
                let bandTop = try XCTUnwrap(scroller.superview).convert(scroller.frame, to: host.view).minY
                let score = try XCTUnwrap(read.first { $0.text.contains("13") && $0.text.contains("20") },
                                          "\(name): no score — \(all)")
                let gameState = try XCTUnwrap(read.first { $0.text.contains("Q3") }, "\(name): no state — \(all)")
                XCTAssertLessThanOrEqual(max(score.box.maxY, gameState.box.maxY), bandTop + 2,
                                         "\(name): the score or state sits inside the band — \(all)")
                scroller.setContentOffset(CGPoint(x: 0, y: scroller.contentSize.height - scroller.bounds.height),
                                          animated: false)
                settle(host, 0.3)
                let scrolled = try tiledLines(host, name: name + "-band-scrolled")
                XCTAssertTrue(scrolled.contains { $0.text.contains("88%") },
                              "\(name): the chances' last figure cannot be reached — "
                                + scrolled.map(\.text).joined(separator: " | "))
                let stateAfter = try XCTUnwrap(scrolled.filter { $0.text.contains("Q3") }.min { $0.box.minY < $1.box.minY },
                                               "\(name): the state left the screen")
                XCTAssertEqual(stateAfter.box.minY, gameState.box.minY, accuracy: 2,
                               "\(name): scrolling the band moved the game state")
            } else {
                XCTAssertNil(band, "\(name): a band where the rule does not apply — \(all)")
                XCTAssertTrue(read.contains { $0.text.contains("88%") }, "\(name): the chances line is not whole — \(all)")
            }
            // The story's room: from the card's kicker to the footer's count,
            // on the same first read. Before the band it was ~90pt at 320/AX5,
            // the kicker alone. Vision may drop the count's spaces ("1of2");
            // the digits and the count are still the open card's "1 of 2".
            // After the band's asserts, so an unrelated footer read cannot
            // hide a band failure.
            let count = try XCTUnwrap(read.last(where: isFooterOneOfTwo),
                                      "\(name): no footer count — \(all)")
            XCTAssertGreaterThanOrEqual(count.box.minY - read[kicker].box.minY, 160,
                                        "\(name): the card has no room to read — \(all)")
            XCTAssertEqual(state.openCardID, deck[0].id, "\(name): the reader left the card it was opened on")
        }
    }

    /// Whether `line` is a word broken with a trailing hyphen ("Comman-",
    /// "PROJECT-"), including a hyphen Vision split into a box of its own at
    /// the end of a word's row. A lone "-" with no letters on its row (the
    /// footer's 4pt page-indicator capsule at 320/Large) is not a broken word.
    private func endsInWordBreak(_ line: Line, in read: [Line]) -> Bool {
        let trimmed = line.text.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasSuffix("-") else { return false }
        if trimmed.contains(where: \.isLetter) { return true }
        return read.contains { other in
            other.text.contains(where: \.isLetter)
                && abs(other.box.midY - line.box.midY) <= max(other.box.height, line.box.height) * 0.75
                && other.box.maxX >= line.box.minX - 16 && other.box.maxX <= line.box.minX + 12
        }
    }

    /// Whether `line` is the reader's "1 of 2" footer count. Vision may drop
    /// the spaces ("1of2"), or at 320/AX5 fuse the left chevron and read the
    /// lowercase "o" as "0" ("< 10f2"). The "0" reading counts only when the
    /// centred footer ink between the chevrons is four complete glyphs ("1",
    /// "o", "f", "2") separated by word spaces on either side of "of", with
    /// the second glyph at lowercase x-height rather than digit height.
    private func isFooterOneOfTwo(_ line: Line) -> Bool {
        if line.text.range(of: #"(?<![0-9])1\s*of\s*2(?![0-9])"#, options: .regularExpression) != nil {
            return true
        }
        guard line.text.range(of: #"(?<![0-9])1\s*0\s*f\s*2(?![0-9])"#, options: .regularExpression) != nil,
              let cg = line.frame, line.bounds.width > 0 else { return false }
        let span = CGRect(x: max(line.box.minX, line.bounds.width * 0.2), y: line.box.minY,
                          width: min(line.box.maxX, line.bounds.width * 0.8) - max(line.box.minX, line.bounds.width * 0.2),
                          height: line.box.height)
        let ink = Self.inkClusters(in: span, cg: cg, bounds: line.bounds)
        guard ink.count == 4 else { return false }
        let gap01 = ink[1].minX - ink[0].maxX, gap12 = ink[2].minX - ink[1].maxX, gap23 = ink[3].minX - ink[2].maxX
        let baselineSpread = (ink.map(\.maxY).max() ?? 0) - (ink.map(\.maxY).min() ?? 0)
        return gap01 >= max(8, gap12 * 3) && gap23 >= max(8, gap12 * 3)
            && ink[0].height >= line.box.height * 0.75 && ink[2].height >= line.box.height * 0.75
            && ink[3].height >= line.box.height * 0.75 && ink[0].width < ink[3].width * 0.8
            && (0.65...0.85).contains(ink[1].height / ink[0].height)
            && ink[1].minY - ink[0].minY >= ink[0].height * 0.15
            && baselineSpread <= 2.5
    }

    private static func inkClusters(in rect: CGRect, cg: CGImage, bounds: CGRect) -> [CGRect] {
        let w = cg.width, h = cg.height, s = CGFloat(w) / bounds.width
        var rgba = [UInt8](repeating: 0, count: w * h * 4)
        let ok = rgba.withUnsafeMutableBytes { buf -> Bool in
            guard let ctx = CGContext(data: buf.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                      bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
            ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        guard ok else { return [] }
        let luma = (0..<(w * h)).map { i in
            UInt8((299 * Int(rgba[4 * i]) + 587 * Int(rgba[4 * i + 1]) + 114 * Int(rgba[4 * i + 2])) / 1000)
        }
        let x0 = max(0, Int((rect.minX * s).rounded(.down))), x1 = min(w, Int((rect.maxX * s).rounded(.up)))
        let y0 = max(0, Int((rect.minY * s).rounded(.down))), y1 = min(h, Int((rect.maxY * s).rounded(.up)))
        guard x0 < x1, y0 < y1 else { return [] }
        var clusters: [CGRect] = [], start: Int?, top = Int.max, bottom = Int.min
        for x in x0...x1 {
            var inked = false
            if x < x1 {
                for y in y0..<y1 where luma[y * w + x] < 200 { inked = true; top = min(top, y); bottom = max(bottom, y) }
            }
            if inked, start == nil { start = x }
            if !inked, let from = start {
                clusters.append(CGRect(x: CGFloat(from) / s, y: CGFloat(top) / s,
                                       width: CGFloat(x - from) / s, height: CGFloat(bottom - top + 1) / s))
                start = nil; top = .max; bottom = .min
            }
        }
        return clusters
    }

    /// The chances band: a vertical scroller with more to show that sits
    /// wholly above the card's kicker (the cards' own scrollers contain it).
    private static func chancesBand(_ view: UIView, above y: CGFloat) -> UIScrollView? {
        var found: UIScrollView?
        func find(_ v: UIView) {
            if let s = v as? UIScrollView, s.contentSize.height > s.bounds.height + 1,
               s.contentSize.width <= s.bounds.width + 1, s.convert(s.bounds, to: view).maxY <= y { found = s }
            v.subviews.forEach(find)
        }
        find(view)
        return found
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
