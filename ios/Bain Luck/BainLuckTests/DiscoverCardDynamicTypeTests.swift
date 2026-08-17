import XCTest

@testable import Bain_Luck

/// UX-P088 (#1772) — the Discover cards honour Dynamic Type.
///
/// The named failure is Alex's rage-shake report #143, "Too small to read",
/// filed 2026-08-11 against the Discover feed.
///
/// The cycle-79 census found two separable defects:
///
///  1. **9pt fixed labels.** `.system(size: 9)` appeared seven times across the
///     event and futures cards. Apple's own floor is 11pt, and a fixed size
///     cannot be helped by any accessibility setting the user turns on — so
///     "too small to read" was literally true and unfixable from Settings.
///  2. **A mixed-metric hero.** `DiscoverFuturesCard` froze its percentage at
///     52pt directly above a `.headline` name that scaled. Turning text size up
///     grew the name and not the numeral, tightening a bottom-aligned `HStack`
///     until `minimumScaleFactor(0.76)` compressed the string and the trailing
///     `%` read as a subscript. A card whose elements change RELATIONSHIP with a
///     user setting is worse than one that is uniformly small.
///
/// These are source-census guards rather than rendering assertions: a SwiftUI
/// view body is not reachable from XCTest here, and claiming a rendered result
/// from a passing unit test is the "rendered-green is not communicates-green"
/// trap (ruling 044). What they CAN pin is that the fixed metrics do not come
/// back — which is exactly how this regressed into a p1 in the first place.
final class DiscoverCardDynamicTypeTests: XCTestCase {

    /// Renderers the census covers, relative to the repo root.
    private static let renderers = [
        "Components/DiscoverEventCard.swift",
        "Components/DiscoverFuturesCard.swift",
        "Components/ResolutionCard.swift",
    ]

    /// The only fixed sizes allowed to survive.
    ///
    /// - `size: 96` is a decorative watermark at 0.08–0.10 opacity. It is never
    ///   read, so ramping it would move a background glyph behind live text for
    ///   no legibility gain.
    /// - `size: heroNumeralSize` IS the ramp — an `@ScaledMetric` value, not a
    ///   literal. `Font.system(size:weight:)` has no `relativeTo:` variant, so
    ///   this is the mechanism, not an exception to it.
    private static let allowedFixedSizeTokens = ["size: 96", "size: heroNumeralSize"]

    private func source(_ relativePath: String) throws -> String {
        // Walk up from this test file to the app sources, so the census reads
        // the real shipping file rather than a copy that can drift.
        let here = URL(fileURLWithPath: #filePath)
        let appRoot = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        let url = appRoot.appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testNoFixedPointSizesSurviveInTheDiscoverRenderers() throws {
        var offenders: [String] = []

        for renderer in Self.renderers {
            let text = try source(renderer)
            for (index, line) in text.components(separatedBy: .newlines).enumerated() {
                guard line.contains(".system(size:") else { continue }
                // Doc comments explaining the rule are not declarations.
                if line.trimmingCharacters(in: .whitespaces).hasPrefix("///") { continue }
                if Self.allowedFixedSizeTokens.contains(where: { line.contains($0) }) { continue }
                offenders.append("\(renderer):\(index + 1) — \(line.trimmingCharacters(in: .whitespaces))")
            }
        }

        XCTAssertTrue(
            offenders.isEmpty,
            """
            A fixed point size is back in a Discover renderer. Fixed sizes ignore \
            Dynamic Type entirely, which is what made report #143 unfixable from \
            Settings. Use a text style (.caption2/.caption/.footnote/.subheadline) \
            for anything 9–16pt, or @ScaledMetric for a display numeral.

            \(offenders.joined(separator: "\n"))
            """
        )
    }

    func testNoRendererDeclaresATypeSizeBelowApplesElevenPointFloor() throws {
        // The specific complaint. 9pt was used seven times; at default settings
        // that is below the 11pt Apple treats as the minimum legible size, and
        // no accessibility setting could raise it.
        var offenders: [String] = []
        // Match the NUMBER, not a prefix of it. A plain `contains("size: 9")`
        // also matches `size: 96` — the decorative watermark — which is how the
        // first draft of this guard failed on its own allowlist. A guard whose
        // matcher is looser than its intent reports defects that are not there,
        // and the next reader turns it off.
        let sizeLiteral = try NSRegularExpression(pattern: #"size:\s*(\d+)"#)

        for renderer in Self.renderers {
            let text = try source(renderer)
            for (index, line) in text.components(separatedBy: .newlines).enumerated() {
                guard line.contains(".system(") else { continue }
                if line.trimmingCharacters(in: .whitespaces).hasPrefix("///") { continue }
                let range = NSRange(line.startIndex..., in: line)
                for match in sizeLiteral.matches(in: line, range: range) {
                    guard let digits = Range(match.range(at: 1), in: line),
                          let points = Int(line[digits]) else { continue }
                    if points < 11 {
                        offenders.append("\(renderer):\(index + 1) — \(points)pt")
                    }
                }
            }
        }

        XCTAssertTrue(offenders.isEmpty, "sub-11pt fixed type is back at: \(offenders)")
    }

    func testTheFuturesHeroUsesAScaledMetricRatherThanAFrozenSize() throws {
        let text = try source("Components/DiscoverFuturesCard.swift")

        XCTAssertTrue(
            text.contains("@ScaledMetric(relativeTo: .largeTitle) private var heroNumeralSize"),
            "the hero numeral must ramp, or it drifts against the .headline name below it"
        )
        XCTAssertFalse(
            text.contains(".font(.system(size: 52"),
            "52pt frozen over a scaling name is the mixed-metric bug itself"
        )
    }

    func testThePercentSignIsItsOwnTextOutsideTheMonospacedDigitRun() throws {
        let text = try source("Components/DiscoverFuturesCard.swift")

        // `%` is not a digit, so inside a `monospacedDigit()` run it kept
        // proportional metrics against black-weight numerals and was the first
        // glyph to lose width under compression — the subscript `%` in the
        // report's screenshot.
        XCTAssertTrue(
            text.contains("Text(\"%\")"),
            "the percent sign must carry its own metrics, not inherit the digit run's"
        )
        XCTAssertFalse(
            text.contains("(leaderProbability * 100).rounded()))%\""),
            "the numeral and % must no longer share one interpolated string"
        )
    }
}
