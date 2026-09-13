import XCTest
@testable import Bain_Luck

/// #5788 — ELEVEN BROWSE TILES PRINTED A SENTENCE FRAGMENT.
///
/// `BrowseLeagueTile` draws a bold acronym with a `caption2` expansion under it,
/// in a half-width tile, at `lineLimit(1)`. The expansions were the leagues'
/// legal names, so on production (iPhone 17, 402pt,
/// `artifacts-native-020/n138-browse-s1.png`, 2026-09-12) the grid read:
///
///     NBA     National Basket…        NFL     National Footbal…
///     MLB     Major League Ba…        NHL     National Hockey…
///     NCAAB   NCAA Men's Ba…          WNCAAB  NCAA Women's…
///     MLS     Major League So…        EPL     English Premier…
///     UCL     UEFA Champion…          WTA     Women's Tennis…
///
/// A truncated expansion is strictly worse than none: it spends the line and
/// tells the reader nothing the acronym above it did not (D102 — grey type is
/// fine where it offers value, and "National Basket…" under "NBA" offers none).
///
/// THE MEASURED BUDGET. The same screenshot is the ruler, because the three
/// tiles that were NOT truncated bound it from below and the truncated ones
/// bound it from above: "Spanish La Liga" (15 characters) fit, "NCAA Football"
/// (13) fit, "Women's NBA" (11) fit; every string of 16 or more was cut. So 15
/// is the one-line budget at the default text size, and it is a PROXY — the
/// font is proportional and XCTest cannot ask SwiftUI what fits — which is why
/// the view also wraps to two lines now. The character rule keeps the strings
/// honest; `lineLimit(2)` keeps a reader from ever meeting an ellipsis.
final class BrowseLeagueTileLabelTests: XCTestCase {

    private var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private func source(_ relative: String) throws -> String {
        try String(contentsOf: projectRoot.appendingPathComponent(relative), encoding: .utf8)
    }

    /// `allLeagues` is `private` to its file, so the corpus is read from the
    /// source rather than imported — which also means the scan is about the
    /// table a reader actually gets, not a copy of it kept in this file.
    private func subtitles() throws -> [(label: String, subtitle: String)] {
        let text = try source("Bain Luck/Views/LeaguesView.swift")
        var out: [(String, String)] = []
        for raw in text.components(separatedBy: .newlines) {
            let code = raw.components(separatedBy: "//").first ?? raw
            guard code.contains("LeagueInfo(slug:") else { continue }
            guard let label = capture(#"label: "([^"]*)""#, in: code),
                  let subtitle = capture(#"fullName: "([^"]*)""#, in: code) else { continue }
            out.append((label, subtitle))
        }
        return out
    }

    private func capture(_ pattern: String, in line: String) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern),
              let m = re.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)),
              let r = Range(m.range(at: 1), in: line) else { return nil }
        return String(line[r])
    }

    /// ANTI-VACUITY: a scan that parses nothing passes everything.
    func testTheScanFindsTheWholeLeagueTable() throws {
        let rows = try subtitles()
        XCTAssertEqual(rows.count, 16, "the league table should have 16 tiles; the scan parsed \(rows.count)")
        for expected in ["NBA", "WNCAAB", "MLS", "UCL", "WTA"] {
            XCTAssertTrue(rows.contains { $0.label == expected }, "the scan missed the \(expected) tile")
        }
    }

    /// The rule, on the population a reader meets. The ceiling is 18 rather
    /// than the measured 15 because two tiles deliberately spend a second line:
    /// under the COLLEGE header, "Men's basketball" (16) and "Women's
    /// basketball" (18) are the shortest strings that are still specific about
    /// both the sport and who plays it, and a wrapped second line is a better
    /// answer than a vaguer first one. Anything past 18 wraps to a THIRD line
    /// the tile does not allow, and would ellipsise.
    func testNoTileSubtitleExceedsTheTwoLineBudget() throws {
        let over = try subtitles().filter { $0.subtitle.count > 18 }
        XCTAssertTrue(
            over.isEmpty,
            "these subtitles exceed what two caption2 lines hold in a half-width tile, so they will ellipsise:\n"
                + over.map { "\($0.label): \"\($0.subtitle)\" (\($0.subtitle.count))" }.joined(separator: "\n")
        )
    }

    /// And the one-line budget still governs the rest: a tile that spends a
    /// second line has to be one of the two that earned it, so "over 15" does
    /// not quietly become the norm.
    func testOnlyTheTwoCollegeTilesSpendASecondLine() throws {
        let long = try subtitles().filter { $0.subtitle.count > 15 }.map(\.label).sorted()
        XCTAssertEqual(
            long, ["NCAAB", "WNCAAB"],
            "the set of tiles longer than the measured 15-character one-line budget has changed: \(long)"
        )
    }

    /// A subtitle that only repeats its own acronym has no reason to be drawn.
    /// "NBA / National Basketball Association" is the case: the reader learns
    /// nothing, and the line is the one that truncated.
    func testNoSubtitleIsJustTheAcronymSpeltOut() throws {
        for row in try subtitles() {
            let initials = row.subtitle
                .split(separator: " ")
                .compactMap { $0.first.map(String.init) }
                .joined()
                .uppercased()
            XCTAssertNotEqual(
                initials, row.label.uppercased(),
                "\(row.label)'s subtitle \"\(row.subtitle)\" is the acronym spelt out — it tells a reader nothing"
            )
        }
    }

    /// The wrap is the net under the character rule, and under every text size
    /// and canvas the character rule was measured on ONE of. If it goes back to
    /// one line, a long accessibility size truncates again with no guard firing.
    func testTheTileWrapsRatherThanTruncates() throws {
        let text = try source("Bain Luck/Views/LeaguesView.swift")
        let tile = try XCTUnwrap(
            text.range(of: "private struct BrowseLeagueTile").map { String(text[$0.lowerBound...]) },
            "BrowseLeagueTile has been renamed — re-aim this scan"
        )
        // COMMENTS STRIPPED FIRST, and the mutation sweep is why: the frame
        // mutant SURVIVED the first draft of this test, because the comment
        // this ship wrote beside the fix quotes `maxHeight: .infinity`, so the
        // assertion was satisfied by the explanation after the code was gone.
        // A guard that reads a description of the fix is not reading the fix.
        let body = tile
            .prefix(2_600)
            .components(separatedBy: .newlines)
            .map { $0.components(separatedBy: "//").first ?? $0 }
            .joined(separator: "\n")
        XCTAssertTrue(
            body.contains("Text(league.fullName)"),
            "the tile no longer draws league.fullName — re-aim this scan"
        )
        XCTAssertTrue(body.contains("lineLimit(2)"), "the subtitle is not allowed two lines")
        // And a wrapped tile must not leave its row-mate short: WNCAAB's second
        // line grew its own card and NCAAB beside it stayed at the minimum.
        XCTAssertTrue(
            body.contains("maxHeight: .infinity"),
            "the tile no longer fills its row height, so a wrapped subtitle makes the two cards in a row different sizes"
        )
        let subtitleLines = body.components(separatedBy: "Text(league.fullName)")
        XCTAssertFalse(
            (subtitleLines.last ?? "").prefix(220).contains("lineLimit(1)"),
            "the subtitle is back to one line, which is the defect"
        )
    }
}
