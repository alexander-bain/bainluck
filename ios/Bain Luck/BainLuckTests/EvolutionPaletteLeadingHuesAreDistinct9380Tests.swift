import XCTest
@testable import Bain_Luck

/// #9380 — the Evolution chart's default lines must be colours a reader can
/// tell apart.
///
/// Every futures market whose outcomes carry no stored colour (politics,
/// economics, culture) paints outcome N in `paletteHexes[N]`, and the chart
/// selects `prefix(3)` on load. The palette used to run red, blue, indigo, so
/// *Brazil Presidential election winner?* drew Lula (#2, `#005eb8`) and Cury
/// (#3, `#1d4ed8`) as the same blue — legend dots and lines alike.
///
/// Hue is the axis that failed, so hue is what is asserted: the pinned list in
/// the #7036 file says WHICH colours; this says the order is readable, which a
/// byte pin cannot — the old list would pass any pin written against it.
final class EvolutionPaletteLeadingHuesAreDistinct9380Tests: XCTestCase {

    private typealias E = EvolutionOutcomeColour

    /// HSL hue in degrees, from a `#rrggbb` hex.
    private func hue(_ hex: String) -> Double {
        let digits = hex.dropFirst()
        let value = Int(digits, radix: 16)!
        let r = Double((value >> 16) & 0xff) / 255
        let g = Double((value >> 8) & 0xff) / 255
        let b = Double(value & 0xff) / 255
        let maxC = max(r, g, b), minC = min(r, g, b), delta = maxC - minC
        guard delta > 0 else { return 0 }
        var h: Double
        if maxC == r { h = ((g - b) / delta).truncatingRemainder(dividingBy: 6) }
        else if maxC == g { h = (b - r) / delta + 2 }
        else { h = (r - g) / delta + 4 }
        h *= 60
        return h < 0 ? h + 360 : h
    }

    private func hueDistance(_ a: String, _ b: String) -> Double {
        let d = abs(hue(a) - hue(b))
        return min(d, 360 - d)
    }

    /// The rig itself, on values whose hue is known, so a broken `hue` cannot
    /// make the real assertions pass vacuously.
    func testTheHueRulerReadsKnownColours() {
        XCTAssertEqual(hue("#ff0000"), 0, accuracy: 0.01)
        XCTAssertEqual(hue("#00ff00"), 120, accuracy: 0.01)
        XCTAssertEqual(hue("#0000ff"), 240, accuracy: 0.01)
        XCTAssertEqual(hueDistance("#ff0000", "#ff00ff"), 60, accuracy: 0.01)
        // The specimen pair: the old slots 1 and 2 are ~15° apart.
        XCTAssertLessThan(hueDistance("#005eb8", "#1d4ed8"), 16)
    }

    /// 🔴 The specimen. The default #2 and #3 lines are different hue families.
    func testTheDefaultSecondAndThirdLinesAreNotTwoBlues() {
        XCTAssertGreaterThanOrEqual(
            hueDistance(E.paletteHexes[1], E.paletteHexes[2]), 30,
            "slots 1 and 2 are the default #2/#3 lines: \(E.paletteHexes[1]) vs \(E.paletteHexes[2])")
    }

    /// Top 5 is the smallest chip the chart offers, so the first five slots are
    /// pairwise distinct — not just the default three.
    func testTheFirstFiveSlotsArePairwiseDistinctHues() {
        let lead = Array(E.paletteHexes.prefix(5))
        for i in 0..<lead.count {
            for j in (i + 1)..<lead.count {
                XCTAssertGreaterThanOrEqual(
                    hueDistance(lead[i], lead[j]), 30,
                    "slots \(i) (\(lead[i])) and \(j) (\(lead[j])) read as one colour")
            }
        }
    }

    /// A reorder, not a repaint: same ten colours, leader unchanged — so the AA
    /// floor pinned in the #7036 file still describes every slot.
    func testTheReorderAddsAndDropsNoColourAndKeepsTheRedLeader() {
        XCTAssertEqual(Set(E.paletteHexes), [
            "#c41e3a", "#005eb8", "#1d4ed8", "#0e7490", "#b91c1c",
            "#0369a1", "#92400e", "#4338ca", "#be185d", "#065f46",
        ])
        XCTAssertEqual(E.paletteHexes.count, 10)
        XCTAssertEqual(E.paletteHexes[0], "#c41e3a")
    }
}
