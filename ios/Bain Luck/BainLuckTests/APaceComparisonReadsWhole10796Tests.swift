import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #10796 — the projected-scoring card's comparison, "Pace projects −28.9 vs
/// pre-game expectation.", on the retained 15195971 event (pre-game 236.5,
/// pace 207.6). At AX5 on both phones build 81 printed "−28." over "9" and broke
/// "projects" and "expectation" into fragments (Design build-81 addendum,
/// `375-ax5-scroll26.png`, `393-ax5-scroll19.png`).
///
/// The line is hosted in a window at the strip's width, photographed and read
/// with Vision, like ``AForecastFigureIsReadWhole9483Tests``. The rig is checked
/// against the defect: the old three-text row, drawn on the same rig, must NOT
/// read the number whole.
@MainActor
final class APaceComparisonReadsWhole10796Tests: XCTestCase {

    /// The strip's content width: the screen less the page's 16pt margins, the
    /// card's 14pt padding and the strip's own 12pt, each side.
    private static let strip393: CGFloat = 393 - 32 - 28 - 24
    private static let strip375: CGFloat = 375 - 32 - 28 - 24

    private static let specimen = PaceComparison.make(pregameTotal: 236.5, paceTotal: 207.6, unit: "points")!

    // MARK: - The words

    func testTheSpecimenPrintsItsNumberAsItAlwaysHas() {
        XCTAssertEqual(Self.specimen.signedValue, "-28.9")
        XCTAssertEqual(Self.specimen.spokenLabel,
                       "Pace projects 28.9 fewer points than the pre-game expectation.")
    }

    func testAPaceAboveThePregameTotalReadsMore() throws {
        let ahead = try XCTUnwrap(PaceComparison.make(pregameTotal: 45.5, paceTotal: 53, unit: "points"))
        XCTAssertEqual(ahead.signedValue, "+7.5")
        XCTAssertEqual(ahead.spokenLabel, "Pace projects 7.5 more points than the pre-game expectation.")
    }

    func testTheSportsOwnNounIsSpoken() throws {
        let games = try XCTUnwrap(PaceComparison.make(pregameTotal: 22.5, paceTotal: 25, unit: "games"))
        XCTAssertEqual(games.spokenLabel, "Pace projects 2.5 more games than the pre-game expectation.")
        let scoring = try XCTUnwrap(PaceComparison.make(pregameTotal: 22.5, paceTotal: 20, unit: "scoring"))
        XCTAssertEqual(scoring.spokenLabel, "Pace projects 2.5 below the pre-game expectation.")
    }

    /// #6290 — no served opening, no comparison; and none inside half a unit.
    func testNoOpeningOrAPaceOnTheLineDrawsNoComparison() {
        XCTAssertNil(PaceComparison.make(pregameTotal: nil, paceTotal: 207.6, unit: "points"))
        XCTAssertNil(PaceComparison.make(pregameTotal: 236.5, paceTotal: 236.0, unit: "points"))
        XCTAssertNil(PaceComparison.make(pregameTotal: 236.5, paceTotal: 237.0, unit: "points"))
        XCTAssertNotNil(PaceComparison.make(pregameTotal: 236.5, paceTotal: 237.1, unit: "points"))
    }

    // MARK: - Rig

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func read<V: View>(_ view: V, width: CGFloat, height: CGFloat,
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
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("pace-comparison-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Pace comparison rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    /// Some read line holds the whole number, digits and decimal together.
    private func readsTheNumberWhole(_ lines: [String]) -> Bool {
        lines.contains { $0.contains("28.9") }
    }

    /// Every word of the sentence reads whole on some line, and in order.
    private func readsTheSentenceInOrder(_ lines: [String]) -> Bool {
        let tokens = lines.flatMap { $0.split(separator: " ").map(String.init) }
        let words = ["Pace", "projects", "vs", "pre-game", "expectation."]
        var at = tokens.startIndex
        for word in words {
            guard let found = tokens[at...].firstIndex(of: word) else { return false }
            at = tokens.index(after: found)
        }
        return true
    }

    // MARK: - Drawn

    func testTheComparisonReadsWholeAtEverySizeOnBothPhones() throws {
        for (width, phone) in [(Self.strip393, "393"), (Self.strip375, "375")] {
            for (size, label, height) in [(DynamicTypeSize.large, "large", CGFloat(200)),
                                          (.accessibility5, "ax5", 700)] {
                let name = "\(phone)-\(label)"
                let lines = try read(PaceComparisonLine(comparison: Self.specimen, color: .purple),
                                     width: width, height: height, at: size, name: name)
                XCTAssertTrue(readsTheNumberWhole(lines), "\(name): -28.9 is not one token: \(lines)")
                XCTAssertTrue(readsTheSentenceInOrder(lines), "\(name): the sentence is broken: \(lines)")
            }
        }
    }

    /// At the default size the reading stays one compact line.
    func testTheDefaultSizeStaysOneLine() throws {
        for (width, phone) in [(Self.strip393, "393"), (Self.strip375, "375")] {
            let lines = try read(PaceComparisonLine(comparison: Self.specimen, color: .purple),
                                 width: width, height: 200, at: .large, name: "\(phone)-large-oneline")
            XCTAssertTrue(lines.contains { $0.contains("Pace projects") && $0.contains("28.9") && $0.contains("expectation") },
                          "\(phone): the default reading is not one line: \(lines)")
        }
    }

    /// The rig can see the defect: the row build 81 drew — three texts in one
    /// `HStack(spacing: 4)` — read at AX5 on a 375 does NOT hold the number whole.
    func testControlTheOldRowSplitsTheNumberAtAX5() throws {
        let lines = try read(OldRow(value: Self.specimen.signedValue),
                             width: Self.strip375, height: 700, at: .accessibility5, name: "control-old-row-375-ax5")
        XCTAssertFalse(readsTheNumberWhole(lines) && readsTheSentenceInOrder(lines),
                       "control: the pre-repair row reads whole, so this rig cannot see the split: \(lines)")
    }

    private struct OldRow: View {
        let value: String
        var body: some View {
            HStack(spacing: 4) {
                Text("Pace projects").font(.caption2).foregroundStyle(.secondary)
                Text(value).font(.caption2.monospacedDigit().weight(.semibold)).foregroundStyle(.purple)
                Text("vs pre-game expectation.").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}
