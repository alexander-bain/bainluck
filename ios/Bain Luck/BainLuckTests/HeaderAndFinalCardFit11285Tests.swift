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
            let read = try lines(host, name: name).filter { $0.box.minX < cardRight }
                .sorted { $0.box.minY < $1.box.minY }
            let all = read.map(\.text).joined(separator: " | ")
            XCTAssertFalse(read.contains { $0.text.contains("…") || $0.text.contains("...") },
                           "\(name): an ellipsis is drawn — \(all)")
            func index(_ text: String, after: Int) -> Int? {
                read.indices.first { $0 > after && read[$0].text.trimmingCharacters(in: .whitespaces) == text }
            }
            // Each row's two numbers, top to bottom (the axis ticks are
            // touchdowns, never these).
            let rows = [(away, "21.5", "13.5"), (home, "29.5", "33")]
            var marks: [(pregame: Int, now: Int)] = []
            for (_, pregame, now) in rows {
                guard let p = index(pregame, after: marks.last?.now ?? -1), let n = index(now, after: p) else { break }
                marks.append((p, n))
            }
            guard marks.count == rows.count,
                  let legend = read.indices.first(where: { $0 > marks[1].now && read[$0].text.hasPrefix("Points") }) else {
                XCTFail("\(name): the rows' numbers and the legend did not read in order — \(all)")
                continue
            }
            // A row ends at the next row's name, the last at the legend.
            let ends = [marks[1].pregame - 1, legend]
            for (i, (team, _, _)) in rows.enumerated() {
                let (p, n) = marks[i]
                // The stacked layout: the whole name on its own line over the number.
                XCTAssertEqual(read[p - 1].text.trimmingCharacters(in: .whitespaces), team,
                               "\(name): the line over \(read[p].text) is not the whole name \(team) — \(all)")
                assertLabel(read[(p + 1)..<n], reads: "pregame projection", under: read[p], over: read[n],
                            "\(name) \(team)", all: all)
                assertLabel(read[(n + 1)..<max(n + 1, ends[i])], reads: "projected now", under: read[n],
                            over: read[ends[i]], "\(name) \(team)", all: all)
            }
            // The live legend, whole, under the last row.
            let stop = read.indices.first { $0 > legend && read[$0].text.contains("Open") } ?? read.endIndex
            let text = read[legend..<stop].map(\.text).joined(separator: " ")
            XCTAssertEqual(text.filter { $0.isLetter || $0 == "=" }, "Pointsoutline=pregamefilled=projectednow",
                           "\(name): the legend read \"\(text)\" — \(all)")
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
