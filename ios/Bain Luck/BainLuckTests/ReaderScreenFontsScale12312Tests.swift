import XCTest

@testable import Bain_Luck

/// #12312 — Discover, My Stuff and Search, and the shared pieces their cards
/// draw, print no fixed point size a reader reads.
///
/// `.font(.system(size: 9))` is a POINT size: Larger Text grows every text
/// style around it and leaves it at 9, so at AX5 a 40 pt team name sat over a
/// 9 pt source mark and an 8 pt clock dot before "In 14h 47m". Each of those
/// sizes is now an `@ScaledMetric` seeded at its old value — exactly the old
/// size at the default text size, growing above it — so nothing moves for a
/// reader who never touched the setting (`RelatedFuturesView`'s reasoning).
///
/// A source census, like `DiscoverCardDynamicTypeTests` (#1772): what it pins
/// is that a literal size does not come back. Whether the screens read at AX5
/// is the simulator captures' job, and the stacked card's is
/// `FinishedFeedCardAccessibility11325Tests`.
final class ReaderScreenFontsScale12312Tests: XCTestCase {

    /// The files the census covers, relative to the app sources.
    private static let files = [
        "Views/DiscoverView.swift",
        "Views/MyStuffView.swift",
        "Views/SearchView.swift",
        "Components/EventCardView.swift",
        "Components/StatusBadge.swift",
        "Components/SportFilterChips.swift",
        "Components/PriceAgeMarkView.swift",
        "Components/LiquidityMarkView.swift",
    ]

    /// The literal sizes allowed to stay, by file, exact line and count.
    /// Lines inside `#if DEBUG` are not counted at all.
    ///
    /// - The Discover counts line is the UI-test rig's, drawn only under its
    ///   launch flag; no reader sees it.
    /// - My Stuff's 48 and 56 pt marks are the empty states' illustrations
    ///   (the clover, the heart, the court), not text.
    private static let allowed: [String: [String: Int]] = [
        "Views/DiscoverView.swift": [".font(.system(size: 13, weight: .bold).monospacedDigit())": 1],
        "Views/MyStuffView.swift": [".font(.system(size: 48))": 2, ".font(.system(size: 56))": 1],
    ]

    private func source(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        return try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// Every line printing a literal `.system(size: <number>`, trimmed, outside
    /// comments and `#if DEBUG` blocks, with how often it appears.
    private func literalSizes(in text: String) throws -> [String: Int] {
        let literal = try NSRegularExpression(pattern: #"\.system\(size:\s*[0-9]"#)
        var found: [String: Int] = [:]
        var debugDepth = 0, depth = 0
        for raw in text.components(separatedBy: .newlines) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("#if") {
                depth += 1
                if line == "#if DEBUG" && debugDepth == 0 { debugDepth = depth }
                continue
            }
            // A DEBUG block's `#else` is the shipping branch.
            if line.hasPrefix("#else") || line.hasPrefix("#elseif") {
                if depth == debugDepth { debugDepth = 0 }
                continue
            }
            if line.hasPrefix("#endif") {
                if depth == debugDepth { debugDepth = 0 }
                depth -= 1
                continue
            }
            if debugDepth > 0 || line.hasPrefix("//") { continue }
            if literal.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)) != nil {
                found[line, default: 0] += 1
            }
        }
        return found
    }

    func testNoReaderFacingFixedPointSizeSurvivesOnTheseScreens() throws {
        var offenders: [String] = []
        for file in Self.files {
            let found = try literalSizes(in: try source(file))
            let allowed = Self.allowed[file] ?? [:]
            for (line, count) in found.sorted(by: { $0.key < $1.key }) where count > (allowed[line] ?? 0) {
                offenders.append("\(file): \(count)× \(line)")
            }
        }
        XCTAssertTrue(offenders.isEmpty, """
            A fixed point size is back on a reader screen. It ignores Larger Text \
            entirely. Seed an @ScaledMetric(relativeTo:) at the same value instead \
            — unchanged at the default size, growing above it.

            \(offenders.joined(separator: "\n"))
            """)
    }

    /// The census is not vacuous: it sees a literal size, skips one inside
    /// `#if DEBUG` (nested blocks included) and in a comment, counts a DEBUG
    /// block's `#else` as shipping code, and counts repeats.
    func testTheCensusSeesWhatItMustAndSkipsWhatItMay() throws {
        let sample = """
            Text("a").font(.system(size: 9, weight: .bold))
            // .font(.system(size: 9))
            #if DEBUG
            Text("rig").font(.system(size: 9))
            #if os(iOS)
            Text("nested").font(.system(size: 9))
            #endif
            #else
            Text("a").font(.system(size: 9, weight: .bold))
            #endif
            #if os(iOS)
            Text("a").font(.system(size: 9, weight: .bold))
            #endif
            Text("b").font(.system(size: labelSize))
            """
        XCTAssertEqual(try literalSizes(in: sample), [#"Text("a").font(.system(size: 9, weight: .bold))"#: 3])
    }

    /// Each allowance still names a line that exists, so a removed exemption
    /// cannot linger and later excuse a new literal on another line.
    func testEveryAllowanceStillNamesALineThatExists() throws {
        for (file, lines) in Self.allowed {
            let found = try literalSizes(in: try source(file))
            for (line, count) in lines {
                XCTAssertEqual(found[line], count, "\(file): the allowance for '\(line)' no longer matches")
            }
        }
    }
}
