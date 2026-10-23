import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #9483 / #10236 — two words the 15195971 render (Nuggets @ Thunder, Q3) cut
/// off, read back off the drawn pixels:
///
/// * the margin map's summary tiles printed "OKC by abo…" at XXXL and "DEN…" /
///   "OK…" at AX5 (`frames/393-xxxl-scroll6.png`, Root + Design 2026-10-23);
/// * a live prop cell too old to be current printed "No upda…" at the default
///   size (`finding-393-default-no-upda-truncated.png`);
/// * at AX5 the props grid's player column printed "Chet Holmg…" / "Isaiah
///   Harten…" (`frames/393-ax5-scroll13.png`), and the winning-margin card's
///   label printed "Pregame proje…" (`frames/393-ax5-scroll4.png`; Design R3
///   disposition 2026-10-23).
///
/// Each is hosted in a window at a phone's width, photographed, and read with
/// Vision. The rig is checked against the defect it exists to catch: the old
/// fixed tile row, drawn on the same rig, must NOT read whole.
@MainActor
final class AForecastFigureIsReadWhole9483Tests: XCTestCase {

    /// The map card's content width: the screen minus the page's 16pt margins
    /// and the card's 14pt padding, each side.
    private static let cardContent393: CGFloat = 393 - 32 - 28
    private static let cardContent375: CGFloat = 375 - 32 - 28

    /// The specimen's live tiles, in its own words.
    private static let specimenTiles: [MarketMapSummaryTiles.Tile] = [
        .init(id: "actual", label: "ACTUAL", value: "DEN by 3", accent: .green),
        .init(id: "proj", label: MarketMapView.liveProjectionTileLabel, value: "OKC by about 2", accent: .black),
    ]

    // MARK: - Rig

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    /// The view drawn in a window at `width`, at `size`, read line by line.
    private func read<V: View>(_ view: V, width: CGFloat, height: CGFloat = 700,
                               at size: DynamicTypeSize, name: String) throws -> [String] {
        let host = hostForMeasurement(
            view.frame(width: width, alignment: .leading)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(Color.white)
                .environment(\.colorScheme, .light),
            at: size)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: height))
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        host.view.frame = window.bounds
        settle(host, 0.3)
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("figure-read-whole-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Figure read whole rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func isCut(_ line: String) -> Bool {
        line.contains("…") || line.contains("...")
    }

    // MARK: - The margin map's tiles

    private func assertTilesReadWhole(_ lines: [String], _ name: String, line: UInt = #line) {
        let text = lines.joined(separator: " ")
        for words in ["ACTUAL", "SPORTSBOOK", "PROJECTION", "DEN by 3", "OKC by about 2"] {
            XCTAssertTrue(text.contains(words), "\(name): \"\(words)\" is not read whole: \(lines)", line: line)
        }
        XCTAssertFalse(lines.contains(where: isCut), "\(name): a tile is cut off: \(lines)", line: line)
    }

    func testTheTilesReadWholeAtEverySizeOnBothPhones() throws {
        for (width, phone) in [(Self.cardContent393, "393"), (Self.cardContent375, "375")] {
            for (size, label) in [(DynamicTypeSize.large, "large"), (.xxxLarge, "xxxl"), (.accessibility5, "ax5")] {
                let name = "tiles-\(phone)-\(label)"
                let lines = try read(MarketMapSummaryTiles(tiles: Self.specimenTiles),
                                     width: width, at: size, name: name)
                assertTilesReadWhole(lines, name)
            }
        }
    }

    /// The rig can see the defect: the row the map drew before #9483's repair —
    /// two equal tiles, each value held to one line — read at XXXL on the
    /// specimen's phone is NOT whole.
    func testControlTheOldFixedRowIsCutAtXXXL() throws {
        let lines = try read(OldFixedRow(tiles: Self.specimenTiles),
                             width: Self.cardContent393, at: .xxxLarge, name: "control-old-row-393-xxxl")
        let text = lines.joined(separator: " ")
        XCTAssertFalse(text.contains("OKC by about 2"),
                       "control: the pre-repair row reads whole, so this rig cannot see a cut: \(lines)")
    }

    private struct OldFixedRow: View {
        let tiles: [MarketMapSummaryTiles.Tile]
        var body: some View {
            HStack(spacing: 8) {
                ForEach(tiles) { tile in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(tile.label).font(.caption2.weight(.heavy)).tracking(0.5)
                        Text(tile.value).font(.subheadline.weight(.black)).lineLimit(1)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    // MARK: - The stale prop cell

    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10236-during-matrix.route.json")

    /// An hour after the route body's quotes (observed 07:08Z): every cell is
    /// past the 30-minute bar.
    private static let staleNow = "2026-10-03T08:09:00Z".asDate!

    func testAStaleCellReadsNoUpdateWholeAtTheDefaultSize() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let props = try XCTUnwrap(try decoder.decode(
            GameMarketsResponse.self, from: Data(contentsOf: Self.fixtureURL)).duringPlayerProps)
        let row = try XCTUnwrap(props.rows.first)
        XCTAssertEqual(EventPropsMatrixLayout.cellText(row, now: Self.staleNow),
                       EventPropsMatrixLayout.staleCellText, "control: the cells are stale at this clock")
        for (width, phone) in [(CGFloat(393 - 32), "393"), (CGFloat(375 - 32), "375")] {
            let name = "stale-cell-\(phone)-large"
            let lines = try read(EventPropsMatrixView(props: props, displayAsOf: Self.staleNow),
                                 width: width, at: .large, name: name)
            // The legend reads "No update: …" on one line; a cell is the two
            // words alone, on one line or wrapped onto two.
            let cells = lines.filter {
                let t = $0.trimmingCharacters(in: .whitespaces)
                return t == "No update" || t == "update"
            }
            XCTAssertFalse(cells.isEmpty, "\(name): no cell reads \"No update\" whole: \(lines)")
            XCTAssertFalse(lines.contains { isCut($0) && $0.contains("upd") },
                           "\(name): a cell is cut off: \(lines)")
        }
    }

    // MARK: - Player names at accessibility sizes

    /// The specimen's names, written over the fixture's two grid players:
    /// "Hartenstein" alone is wider at AX5 than any column that leaves room
    /// for a cell, and "Gilgeous-Alexander" is wider than the card.
    private static let specimenNames = [
        "Aaron Judge": "Isaiah Hartenstein",
        "Juan Soto": "Shai Gilgeous-Alexander",
    ]

    /// Every word of `name` appears whole on some read line — a surname broken
    /// mid-word ("Harten" / "stein") or cut ("Harten…") does not.
    private func isReadWhole(_ name: String, in lines: [String]) -> Bool {
        let tokens = Set(lines.flatMap {
            $0.split(whereSeparator: { $0 == " " || $0 == "-" }).map(String.init)
        })
        return name.split(whereSeparator: { $0 == " " || $0 == "-" }).allSatisfy { tokens.contains(String($0)) }
    }

    func testEveryPlayerNameReadsWholeAtAccessibilitySizes() throws {
        var body = try String(contentsOf: Self.fixtureURL, encoding: .utf8)
        for (fixture, specimen) in Self.specimenNames {
            XCTAssertTrue(body.contains(fixture), "control: the fixture names \(fixture)")
            body = body.replacingOccurrences(of: fixture, with: specimen)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let props = try XCTUnwrap(try decoder.decode(
            GameMarketsResponse.self, from: Data(body.utf8)).duringPlayerProps)
        for (width, phone) in [(CGFloat(393 - 32), "393"), (CGFloat(375 - 32), "375")] {
            for (size, label) in [(DynamicTypeSize.accessibility3, "ax3"), (.accessibility5, "ax5")] {
                let name = "names-\(phone)-\(label)"
                let lines = try read(EventPropsMatrixView(props: props, displayAsOf: Self.staleNow),
                                     width: width, height: 2400, at: size, name: name)
                for specimen in Self.specimenNames.values {
                    XCTAssertTrue(isReadWhole(specimen, in: lines), "\(name): \"\(specimen)\" is not read whole: \(lines)")
                }
                XCTAssertFalse(lines.contains(where: isCut), "\(name): a line is cut off: \(lines)")
                // The cells are still there beneath the names. Vision reads
                // side-by-side cells as one line ("update update"); the legend
                // reads "update:".
                XCTAssertTrue(lines.contains { $0.split(separator: " ").contains("update") },
                              "\(name): no cell reads \"No update\": \(lines)")
            }
        }
    }

    /// The rig can see the defect: the player column the grid drew before this
    /// repair — two lines in a 150pt column — read at AX5 is NOT whole.
    func testControlTheOldPlayerColumnIsCutAtAX5() throws {
        let lines = try read(OldPlayerColumn(name: "Isaiah Hartenstein"),
                             width: 393 - 32, at: .accessibility5, name: "control-old-names-393-ax5")
        XCTAssertFalse(isReadWhole("Isaiah Hartenstein", in: lines),
                       "control: the pre-repair column reads whole, so this rig cannot see a cut: \(lines)")
    }

    private struct OldPlayerColumn: View {
        let name: String
        @ScaledMetric(relativeTo: .subheadline) private var rowHeight: CGFloat = 46
        @ScaledMetric(relativeTo: .subheadline) private var nameWidth: CGFloat = 112
        var body: some View {
            Text(name)
                .font(.subheadline)
                .lineLimit(2)
                .minimumScaleFactor(0.85)
                .frame(width: min(nameWidth, 150), height: rowHeight, alignment: .leading)
        }
    }

    // MARK: - The winning-margin card's figure labels

    /// The specimen's card mid-game: Nuggets up 3, the pregame projection
    /// Thunder by 8 (`frames/393-ax5-scroll4.png`).
    private static var specimenMarginCard: NBALadderCard9483 {
        let detail = NBALadderCard9483.Detail(label: "Thunder by 8+", marketName: "Thunder winning margin",
                                              source: nil, quoted: nil, observedAt: nil,
                                              baseline: 0.5, baselineObservedAt: nil, result: nil)
        let point = NBALadderCard9483.Point(optionKey: "o:1", x: 7.5, label: "Thunder by 8+", side: .home,
                                            chance: 0.5, now: nil, observedAt: nil, result: nil, detail: detail)
        return NBALadderCard9483(family: .margin, phase: .during, points: [point],
                                 actual: -3, forecast: 8, awayShort: "Nuggets", homeShort: "Thunder")
    }

    func testTheMarginFigureLabelsReadWholeAtEverySize() throws {
        // The deck's card content: its ~310pt card on a 393 phone less 17pt
        // padding each side, and the same on a 375.
        for (width, phone) in [(CGFloat(276), "393"), (CGFloat(258), "375")] {
            // Each canvas just holds the card: Vision misses small type on a
            // canvas many times taller than its text.
            for (size, label, height) in [(DynamicTypeSize.large, "large", CGFloat(700)), (.xxxLarge, "xxxl", 900),
                                          (.accessibility3, "ax3", 1800), (.accessibility5, "ax5", 2400)] {
                let name = "margin-figures-\(phone)-\(label)"
                let lines = try read(NBALadderCardView9483(card: Self.specimenMarginCard, awayColor: .blue,
                                                           homeColor: .orange, state: NFLCardDeckState9483()),
                                     width: width, height: height, at: size, name: name)
                for words in ["So far", "Pregame projection"] {
                    XCTAssertTrue(isReadWhole(words, in: lines), "\(name): \"\(words)\" is not read whole: \(lines)")
                }
                XCTAssertFalse(lines.contains { isCut($0) && ($0.contains("Preg") || $0.contains("proj")) },
                               "\(name): the label is cut off: \(lines)")
            }
        }
    }
}
