import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9483 — **the event headline leads with the win probabilities, and the
/// opening screen keeps room for the chart.**
///
/// The design review of `5f542c7b96` (scope §1): at enlarged text the hero
/// opened on two crests, two names and two scores, the pair sat beneath them,
/// and an empty band under the delivery status pushed the chart off the
/// opening screen (Native's `nfl-live-xxxl-top.png`, `mnf-axxl-01-top.png`).
/// The text is never shrunk to buy the room; the order changes, the crests
/// become compact identity, and the transient move caption reserves one line.
@MainActor
final class TheHeadlineLeadsWithTheProbabilities9483Tests: XCTestCase {

    private final class Frames {
        var minY: [String: CGFloat] = [:]
    }

    private func tagged(_ name: String, height: CGFloat, into frames: Frames) -> some View {
        Color.clear.frame(height: height)
            .onGeometryChange(for: CGFloat.self) { $0.frame(in: .global).minY } action: {
                frames.minY[name] = $0
            }
    }

    func testTheProbabilityRowIsPlacedAboveBothTeams() throws {
        let frames = Frames()
        let host = hostForMeasurement(
            EventHeroTeamLayout {
                tagged("away", height: 80, into: frames)
                tagged("probability", height: 60, into: frames)
                tagged("home", height: 90, into: frames)
            }, at: .xxxLarge)
        host.view.frame = CGRect(x: 0, y: 0, width: 358, height: 400)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        let probability = try XCTUnwrap(frames.minY["probability"])
        let away = try XCTUnwrap(frames.minY["away"])
        let home = try XCTUnwrap(frames.minY["home"])
        XCTAssertLessThan(probability, away, "the teams lead the stacked hero again")
        XCTAssertLessThan(probability, home)
        XCTAssertEqual(away, home, accuracy: 0.5, "both teams share the row beneath")
        XCTAssertEqual(away - probability, 60 + 12, accuracy: 0.5, "the teams follow the pair directly")
    }

    func testTheRowOffsetsPutThePairFirst() {
        let offsets = EventHeroTeamLayout.rowOffsets(probabilityHeight: 60, spacing: 12)
        XCTAssertEqual(offsets.probability, 0)
        XCTAssertEqual(offsets.teams, 72)
    }

    func testStackedCrestsAreCompactAndTheRowKeepsItsCrest() {
        XCTAssertEqual(EventDetailView.heroLogoSize(stacked: false, regular: 56), 56)
        XCTAssertEqual(EventDetailView.heroLogoSize(stacked: false, regular: 80), 80, "iPad row unchanged")
        XCTAssertEqual(EventDetailView.heroLogoSize(stacked: true, regular: 56), 32)
        XCTAssertEqual(EventDetailView.heroLogoSize(stacked: true, regular: 80), 32)
    }

    private func code(_ directory: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(directory)
            .appendingPathComponent(file)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    func testBothHeroCrestsReadTheCompactSize() throws {
        let page = try code("Views", "EventDetailView.swift")
        XCTAssertTrue(page.contains("letheroLogo=Self.heroLogoSize(stacked:stacked,regular:logoSize)"))
        XCTAssertEqual(page.components(separatedBy: "size:heroLogo,").count - 1,
                       2, "a hero crest stopped compacting when the hero restacks")
        XCTAssertFalse(page.contains("size:logoSize,"), "a crest bypasses the compact size")
    }

    /// The move caption is a two-second line on the pair's short names; its
    /// reserved slot is one line, still scaled with the text.
    func testTheMoveCaptionReservesOneScaledLine() throws {
        let feedback = try code("Components", "LivePriceChangeFeedback.swift")
        XCTAssertTrue(feedback.contains("@ScaledMetric(relativeTo:.caption2)privatevarslotHeight:CGFloat=16"))
        let caption = try XCTUnwrap(feedback.range(of: "structLivePriceMovementCaption:View{"))
        let body = feedback[caption.upperBound...].prefix(1200)
        XCTAssertTrue(body.contains(".lineLimit(1).frame(height:slotHeight,alignment:.topLeading)"))
    }
}
