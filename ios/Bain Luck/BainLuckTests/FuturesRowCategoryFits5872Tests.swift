import XCTest
import SwiftUI
@testable import Bain_Luck

/// #5872 (second half) — the futures browse row clipped the one word a reader
/// navigates by.
///
/// Photographed on production 2026-09-13, iPhone 17,
/// `artifacts-native-020/n143-before-futures.png`: the category chip in
/// `FuturesBrowseMarketRow`'s header drew **`Te…`** for "Tennis", **`Cric…`**
/// for "Cricket" and **`Table T…`** for "Table Tennis" — while 28pt of that
/// same row sat empty between the resolution date and the pin.
///
/// TWO CAUSES, BOTH MEASURED, because the first fix I shot did nothing:
///
///  1. `HStack` divides the space it has LEFT between the children it has LEFT.
///     The trailing `Spacer` is one of those children, so at the moment the
///     category was measured the spacer took half of the remainder however
///     little it needed. Dropping the SPACER's layout priority does NOT fix
///     this (shot and refuted: `n143-after-futures.png` is the same defect,
///     unchanged). Raising the CATEGORY's priority does, because that sizes it
///     against the full width before anything else bids.
///  2. `Label(_:systemImage:)` reserves a FIXED icon column wide enough for the
///     widest symbol it might be handed. Measured on those same rasters: the
///     glyphs were 30–54px wide and the title still started at x=421 in EVERY
///     row — a ~36pt column for an 18pt glyph, so ~19pt of every header was
///     dead space. Priority alone therefore only moved the clip onto the source
///     badge (`Poly…`, `n143-after-v2-futures.png`), which is worse: D91 wants
///     the sources named. Drawing the icon and title as a tight pair spends the
///     glyph's own width and no more, and buys back more than the deficit.
///
/// THE MEASURED BUDGET, from `n143-after-v3-scrolled.png` (the fix, 10:27Z).
/// The widest category on the page, "Table Tennis", drew its chip 261px wide at
/// 3x — 87pt — with the FULL 197px "Polymarket" badge and "Sep 13" beside it,
/// and still left 63px (21pt) before the pin. So a chip may be **108pt** before
/// something else in the row starts to clip.
///
/// This is a MODEL of the header, and it is only worth what it is calibrated
/// against — so ``testTheCalibrationSpecimenStillMeasuresWhatTheRasterShows``
/// pins the model's own ruler to that raster. If the rendering stack drifts,
/// that test fails and says so, rather than this budget quietly becoming
/// fiction.
@MainActor
final class FuturesRowCategoryFits5872Tests: XCTestCase {

    /// Points. Derived above from `n143-after-v3-scrolled.png`.
    private let chipBudget: CGFloat = 108

    /// What "Table Tennis" measured in that raster, in points.
    private let calibrationChipWidth: CGFloat = 87

    // MARK: - Measuring the real chip

    /// The category chip exactly as `FuturesBrowseMarketRow.header` draws it.
    private func chip(_ option: FuturesCategoryOption) -> some View {
        HStack(spacing: 4) {
            Image(systemName: option.icon)
            Text(option.title)
        }
        .font(.caption2)
        .fontWeight(.semibold)
        .lineLimit(1)
    }

    /// The chip's ideal width in POINTS, for the key the backend sends.
    ///
    /// The option is built the way the row builds it — same tag, same title
    /// rule — so this measures what a reader gets and not a paraphrase.
    private func chipWidth(forKey key: String) throws -> CGFloat {
        let option = FuturesCategoryOption(
            tag: key,
            title: sportCategoryDisplayName(key),
            group: .other,
            count: nil
        )
        let renderer = rendererForMeasurement(chip(option))
        // Points, not pixels — every number in this file is a layout width.
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.uiImage, "chip for \(key) produced no raster")
        return image.size.width
    }

    // MARK: - The budget

    /// Every category this header can draw must fit the measured budget.
    func testEveryCategoryChipFitsTheMeasuredBudget() throws {
        let keys = try categoryKeys()

        // Anti-vacuity: a scan that finds nothing passes every assertion below.
        XCTAssertGreaterThan(
            keys.count, 40,
            "only \(keys.count) category keys scanned — the maps moved and this guard is vacuous"
        )
        for known in ["entertainment", "basketball_wncaab", "soccer_germany_bundesliga", "tennis"] {
            XCTAssertTrue(keys.contains(known), "scan missed \(known) — the extraction is wrong")
        }

        var over: [(String, CGFloat)] = []
        for key in keys.sorted() {
            let w = try chipWidth(forKey: key)
            if w > chipBudget { over.append((sportCategoryDisplayName(key), w)) }
        }

        XCTAssertTrue(
            over.isEmpty,
            """
            \(over.count) category chip(s) exceed the measured \(chipBudget)pt budget \
            and will truncate mid-word in the futures browse header: \
            \(over.map { "\($0.0) \(Int($0.1))pt" }.joined(separator: ", ")). \
            Shorten the label, or re-measure the budget against a fresh raster \
            and say so in this file.
            """
        )
    }

    /// The keys photographed on production on the day of the fix, including the
    /// title-cased fallback arm that produced the widest chip of all.
    func testTheKeysPhotographedOnProductionFit() throws {
        for key in ["table_tennis", "tennis", "cricket", "hockey"] {
            let w = try chipWidth(forKey: key)
            XCTAssertLessThanOrEqual(
                w, chipBudget,
                "\(sportCategoryDisplayName(key)) measures \(Int(w))pt, over the \(chipBudget)pt budget"
            )
        }
    }

    /// 🔴 THE RULER ITSELF. `sportCategoryDisplayName` is the only reason the
    /// budget above means anything, and the fallback arm that produces "Table
    /// Tennis" is not in any map — so pin both the string and its measured
    /// width to the raster the budget came from.
    func testTheCalibrationSpecimenStillMeasuresWhatTheRasterShows() throws {
        XCTAssertEqual(sportCategoryDisplayName("table_tennis"), "Table Tennis")

        let w = try chipWidth(forKey: "table_tennis")
        XCTAssertEqual(
            w, calibrationChipWidth, accuracy: 6,
            """
            The "Table Tennis" chip measures \(Int(w))pt here but \
            \(Int(calibrationChipWidth))pt in n143-after-v3-scrolled.png. The model \
            and the raster have drifted apart, so the \(chipBudget)pt budget is no \
            longer calibrated — re-shoot the row before trusting this file.
            """
        )
    }

    // MARK: - The two causes, guarded structurally

    /// The category must be sized before the trailing spacer can bid for the
    /// same points. Without this the spacer takes half the remainder and the
    /// word truncates with the row half empty.
    func testCategoryIsSizedBeforeTheTrailingSpacer() throws {
        let header = try headerCode()
        XCTAssertFalse(header.isEmpty, "header block empty — nothing asserted")
        XCTAssertTrue(
            header.contains("Spacer("),
            "this guard is calibrated against a header with a trailing spacer; if the spacer is gone, re-derive it"
        )
        XCTAssertTrue(
            header.contains(".layoutPriority(1)"),
            """
            The category chip lost its layout priority, so the trailing spacer is \
            bidding for its width again and the category will truncate mid-word \
            ("Te…" for Tennis). See this file's header for the rasters.
            """
        )
    }

    /// `Label(_:systemImage:)` reserves a fixed icon column, which is the ~19pt
    /// this header does not have. The icon is kept; the column is not.
    func testCategoryIsNotDrawnInAFixedIconColumn() throws {
        let header = try headerCode()
        XCTAssertFalse(header.isEmpty, "header block empty — nothing asserted")
        XCTAssertFalse(
            header.contains("Label(category.title"),
            """
            The category went back to `Label(_:systemImage:)`, which reserves a \
            fixed ~36pt icon column for an 18pt glyph. Measured cost: the source \
            badge clips to "Poly…" on a "Table Tennis" row. Draw the icon and the \
            title as a tight pair instead.
            """
        )
        XCTAssertTrue(
            header.contains("Image(systemName: category.icon)")
                && header.contains("Text(category.title)"),
            "the header must still draw both the category icon and its title"
        )
    }

    // MARK: - Reading the source

    private func projectDir() -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
    }

    private func source(_ components: String...) throws -> String {
        var url = projectDir()
        for c in components { url = url.appendingPathComponent(c) }
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// 🔴 COMMENTS STRIPPED FIRST, for the reason the sibling guard gives: this
    /// fix writes `Label(` and the word `Tennis` into the comment beside the
    /// line it changed, so a scan over the whole file would assert nothing.
    private func code(_ text: String) -> String {
        text.split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
    }

    /// The header block of `FuturesBrowseMarketRow`, as CODE.
    private func headerCode() throws -> String {
        let all = code(try source("Components", "FuturesBrowseComponents.swift"))
        guard let start = all.range(of: "private var header: some View {") else {
            XCTFail("header block not found — this guard would be scanning nothing")
            return ""
        }
        let rest = all[start.upperBound...]
        guard let end = rest.range(of: "\n    }") else {
            XCTFail("header block has no end — this guard would be scanning nothing")
            return ""
        }
        return String(rest[rest.startIndex..<end.lowerBound])
    }

    /// The keys `sportCategoryDisplayName` actually consults.
    ///
    /// 🔴 SCOPED TO THREE NAMED MAPS, not to the file. The first draft of this
    /// guard scanned every `"key": "Value"` pair in `SportDisplayNames.swift`
    /// and failed on "PGA Tour Champions", "PGA Tour Americas" and "Alternate
    /// Events" — which are real strings, and unreachable here: they belong to
    /// `golfTourDisplayName`, a different function this header never calls. A
    /// population is not a grep.
    private func categoryKeys() throws -> Set<String> {
        let text = code(try source("Utilities", "SportDisplayNames.swift"))
        var out: Set<String> = []
        for declaration in [
            "private let leagueAcronyms: [String: String] = [",
            "let categoryMap: [String: String] = [",
            "let familyMap: [String: String] = [",
        ] {
            guard let start = text.range(of: declaration) else {
                XCTFail("map `\(declaration)` not found — the extraction is stale, not the table")
                continue
            }
            let rest = text[start.upperBound...]
            guard let end = rest.range(of: "]") else { continue }
            out.formUnion(keys(in: String(rest[rest.startIndex..<end.lowerBound])))
        }
        return out
    }

    private func keys(in literal: String) -> [String] {
        let pattern = #""([a-z0-9_]+)"\s*:\s*""#
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(literal.startIndex..., in: literal)
        return re.matches(in: literal, range: range).compactMap {
            Range($0.range(at: 1), in: literal).map { r in String(literal[r]) }
        }
    }
}
