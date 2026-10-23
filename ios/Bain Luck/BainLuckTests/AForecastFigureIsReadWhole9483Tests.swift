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
///   size (`finding-393-default-no-upda-truncated.png`).
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
}
