import XCTest
import SwiftUI
@testable import Bain_Luck

/// #5908 — two text defects native/144 found on the first phone walk of the
/// themed pages, filed and fixed together because they are the same kind of
/// thing on adjacent surfaces.
final class ThemedPageTypography5908Tests: XCTestCase {

    // MARK: - The weather card stops hyphenating a brand name

    /// THE SPECIMEN: `artifacts-native-144/weather-2.png`, Featured row 3, 11:13Z.
    /// The source mark read
    ///
    ///     Polymar-
    ///     ket
    ///
    /// because the row squeezes two `Label`s into roughly 120 points and SwiftUI
    /// wrapped — and hyphenated — both of them. A wrapped date is a date. A
    /// hyphenated brand is not the brand (D91: the mark reads as sourcing).
    ///
    /// This measures the real label rather than asserting a modifier is present in
    /// the source, and it pins Dynamic Type through `rendererForMeasurement` so the
    /// verdict is a function of the code and not of whatever the simulator was last
    /// left at.
    @MainActor
    func testTheSourceMarkNeverBreaksTheBrandAcrossTwoLines() throws {
        let free = try heightOfSourceMark(constrainedTo: nil)
        let squeezed = try heightOfSourceMark(constrainedTo: 60)

        XCTAssertEqual(squeezed, free, accuracy: 0.5,
                       "the brand wrapped: it is taller inside the row than on its own")
    }

    /// The control, and the reason the assertion above is worth anything: the SAME
    /// measurement, on the SAME label without the fix, DOES grow when the row
    /// squeezes it. Without this the test would pass on any label that happens to
    /// be short, and would keep passing if the fix were deleted and the string
    /// shortened instead.
    @MainActor
    func testTheMeasurementCanActuallySeeTheDefect() throws {
        let free = try heightOfSourceMark(constrainedTo: nil, fixed: false)
        let squeezed = try heightOfSourceMark(constrainedTo: 60, fixed: false)

        XCTAssertGreaterThan(squeezed, free + 0.5,
                             "the unfixed label did NOT wrap at 60pt — re-derive the budget "
                             + "from a fresh raster before trusting the test above")
    }

    /// Kalshi is the other mark the same row draws, and it is the shorter one, so
    /// a fix that only fitted the long name would still be right for it. Pinned so
    /// nobody "simplifies" the rule into a special case for one brand.
    @MainActor
    func testTheShorterBrandIsMeasuredTheSameWay() throws {
        let free = try heightOfSourceMark("Kalshi", constrainedTo: nil)
        let squeezed = try heightOfSourceMark("Kalshi", constrainedTo: 60)

        XCTAssertEqual(squeezed, free, accuracy: 0.5)
    }

    /// Both spellings arrive from `item.src.capitalized`, so the strings the row
    /// can actually draw are the ones the census found on the wire.
    func testTheSourceKeysCapitaliseToTheBrandNames() {
        XCTAssertEqual("polymarket".capitalized, "Polymarket")
        XCTAssertEqual("kalshi".capitalized, "Kalshi")
    }

    /// The measurements above prove the RULE draws on one line. They build their
    /// own label, so nothing in them notices if the card stops using it — the
    /// mutant "delete `.lineLimit(1)` from WeatherView" survived every one of them
    /// before this test existed. So: the card's own source, anchored on the line
    /// the specimen came from, asserted positively as well as negatively.
    func testTheWeatherCardsOwnSourceMarkCarriesTheRule() throws {
        let card = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/WeatherView.swift")
        let source = try String(contentsOf: card, encoding: .utf8)

        let mark = "Label(item.src.capitalized, systemImage: \"chart.bar.fill\")"
        let start = try XCTUnwrap(source.range(of: mark),
                                  "WeatherView no longer draws the mark this scan aims at — re-aim it")
        // The modifiers belong to THIS label, so read only as far as the next one.
        let next = try XCTUnwrap(source.range(of: "Label(\"Closes", range: start.upperBound ..< source.endIndex))
        let chain = String(source[start.upperBound ..< next.lowerBound])

        XCTAssertTrue(chain.contains(".lineLimit(1)"),
                      "the brand may wrap again (#5908)")
        XCTAssertTrue(chain.contains(".fixedSize(horizontal: true"),
                      "the brand may be compressed by the row again (#5908)")
    }

    @MainActor
    private func heightOfSourceMark(
        _ name: String = "Polymarket",
        constrainedTo width: CGFloat?,
        fixed: Bool = true
    ) throws -> CGFloat {
        let mark = Label(name, systemImage: "chart.bar.fill")
            .font(.caption2)
            .lineLimit(fixed ? 1 : nil)
            .fixedSize(horizontal: fixed, vertical: false)

        let content = AnyView(
            width.map { AnyView(mark.frame(width: $0, alignment: .leading)) } ?? AnyView(mark)
        )
        let renderer = rendererForMeasurement(content)
        renderer.scale = 1
        return try XCTUnwrap(renderer.uiImage?.size.height)
    }

    // MARK: - No page ships a typewriter double hyphen

    /// THE SPECIMEN: `artifacts-native-144/economics-2.png` — the economics blurb
    /// read "Rates, inflation, jobs, GDP **--** no odds, just percentages."
    ///
    /// A source scan, so it is worth exactly what its population is worth — and
    /// the population is the reason this test exists rather than a one-line edit.
    /// A hand grep for `Text("…--…")` found ONE occurrence, the specimen. Walking
    /// every Swift file found a SECOND, `HeatMapCardView.swift:241`, in a
    /// `#Preview` fixture the hand pattern could not see.
    ///
    /// That second one is compiled out of release and is not reader copy, and the
    /// scan deliberately does NOT carve it out: an exemption is a place for the
    /// third one to hide, and the cost of complying is one character. It asserts it
    /// found files, because a scan over an empty population is a green that means
    /// nothing.
    func testNoAppCopyShipsADoubleHyphenWhereADashBelongs() throws {
        let app = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")

        var scanned = 0
        var offenders: [String] = []

        let walker = try XCTUnwrap(FileManager.default.enumerator(
            at: app, includingPropertiesForKeys: nil))

        for case let url as URL in walker where url.pathExtension == "swift" {
            let source = try String(contentsOf: url, encoding: .utf8)
            scanned += 1
            for (n, line) in source.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
                // Only string literals, and only a dash-shaped `--`: a Swift
                // decrement, a comment rule and a `--flag` are not reader copy.
                guard line.contains("\"") , line.contains(" -- ") else { continue }
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                guard !trimmed.hasPrefix("//"), !trimmed.hasPrefix("///") else { continue }
                offenders.append("\(url.lastPathComponent):\(n + 1)")
            }
        }

        XCTAssertGreaterThan(scanned, 100, "the scan read almost nothing — re-aim it")
        XCTAssertEqual(offenders, [], "reader copy ships `--` where an em dash belongs (#5908)")
    }

    /// And the one string the specimen names, pinned by value so the scan above is
    /// not the only thing standing between the page and a reprise.
    func testTheEconomicsBlurbCarriesAnEmDash() throws {
        let page = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EconomicsView.swift")
        let source = try String(contentsOf: page, encoding: .utf8)

        XCTAssertTrue(source.contains("jobs, GDP \\u{2014} no odds"),
                      "the economics blurb no longer carries the em dash this fixed (#5908)")
        XCTAssertFalse(source.contains("jobs, GDP -- no odds"))
    }
}
