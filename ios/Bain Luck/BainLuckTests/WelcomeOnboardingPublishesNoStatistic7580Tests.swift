import XCTest
@testable import Bain_Luck

/// native (#7580) — first-run onboarding publishes no measured statistic.
///
/// **What shipped.** `WelcomeView`'s "Surprisingly accurate" page closed with a
/// hardcoded caption, `"474K resolved outcomes, 5.7pp average calibration
/// error"`, unchanged since 2026-09-05 and presented from `DiscoverView` as the
/// first-launch sheet. Both halves were false against the payload we publish:
/// `total_outcomes` is 747,028 and the headline traded cohort is 449,027 (474K
/// is neither), and every real `by_source` ECE lands 0.35–2.50pp while
/// `/calibration` and `/about` both publish **0.9** — the app overstated our own
/// error ~6x on the first screen a new App Store user reads. It also contradicted
/// the three rows printed directly above it, which assert we land on the number.
///
/// **The defect is the literal, not the digits.** A figure baked into Swift can
/// never become true again on its own, and grepping for the *component* does not
/// find it — only grepping for the *figure* does. So this suite is not keyed on
/// the two wrong numbers; it is keyed on the shape of the mistake: any
/// digit-bearing copy on the onboarding carousel that is not one of the
/// deliberately illustrative examples below.
///
/// **Why deleted rather than wired to the payload.** D137 / notice 45 — an
/// accuracy score, grade, hit-rate or ECE figure appears on the accuracy page
/// only. A settled question shown with its result is a result and stays; a score
/// over many results belongs to `/calibration` alone. Deleting the caption
/// satisfies that and kills the drift permanently.
final class WelcomeOnboardingPublishesNoStatistic7580Tests: XCTestCase {

    /// The digit-bearing copy the onboarding carousel is *allowed* to carry, in
    /// source spelling. Every one of these is an illustration a reader cannot
    /// mistake for a measurement: a mock Celtics/76ers card, the "-150 / +130"
    /// line the product exists to replace, and the three schematic calibration
    /// rows ("80% → ~80%") that describe what calibration *means* rather than
    /// reporting how we scored.
    ///
    /// 🪤 Adding a number to this screen must be a deliberate edit to this set,
    /// which is the whole mechanism: the 474K caption was added without anyone
    /// having to say out loud that it was a published figure.
    private static let illustrativeLiterals: Set<String> = [
        "60%", "40%", "76ers",
        #"Not \"-150 / +130\" — just probabilities."#,
        "80%", "~80%", "20%", "~20%", "50%", "~50%",
    ]

    // MARK: - The class: no baked-in statistic anywhere on the carousel

    /// 🪤 The assertion that kills "restore the defect" and every variant of it.
    /// A census, not a substring check for the two known-wrong numbers — a
    /// caption reading "449K outcomes, 0.9pp" would be *correct today* and is
    /// exactly as unmaintainable, so it fails here too.
    func testTheCarouselCarriesNoDigitBearingCopyBeyondItsIllustrations() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)
        let digitBearing = Set(Self.stringLiterals(in: body).filter { $0.contains(where: \.isNumber) })

        XCTAssertEqual(digitBearing, Self.illustrativeLiterals,
                       "onboarding copy gained or lost a number. Added: "
                           + "\(digitBearing.subtracting(Self.illustrativeLiterals)); removed: "
                           + "\(Self.illustrativeLiterals.subtracting(digitBearing))")
    }

    /// The same rule stated as the three phrasings a measured figure actually
    /// arrives in, so a failure names the class instead of printing a set diff.
    /// These fire even if someone widens the allowlist above without reading it.
    func testNoOutcomeCountAndNoErrorFigureIsPrintedOnFirstLaunch() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertNil(Self.firstMatch(#"\d+(\.\d+)?\s*(pp\b|percentage point)"#, in: body),
                     "an error figure in percentage points is back on the onboarding screen")
        XCTAssertNil(Self.firstMatch(#"\d+(\.\d+)?\s*[KM]\b"#, in: body),
                     "a compact outcome/market count is back on the onboarding screen")
        for phrase in ["resolved outcome", "calibration error", "average error", "Brier score"] {
            XCTAssertFalse(body.localizedCaseInsensitiveContains(phrase),
                           "onboarding publishes the accuracy statistic \"\(phrase)\" — "
                               + "D137 confines that to the accuracy page")
        }
        // 🪤 Word-bounded: a bare case-insensitive "ECE" matches "piece" and
        // "December", so the substring form would red this suite on ordinary copy.
        XCTAssertNil(Self.firstMatch(#"\bECE\b"#, in: body),
                     "onboarding names the calibration-error metric")
    }

    /// 🪤 The fix is a deletion, and the cheap way to pass a deletion test is to
    /// delete more. The page still has to make its point: the schematic rows are
    /// what the screen is *for*, and they are not measurements.
    func testTheAccuracyPageStillMakesItsPointWithoutTheCaption() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertTrue(body.contains("private var accuracyPage: some View"),
                      "the accuracy page was removed rather than its caption")
        for row in ["statRow(predicted: \"80%\", actual: \"~80%\"",
                    "statRow(predicted: \"20%\", actual: \"~20%\"",
                    "statRow(predicted: \"50%\", actual: \"~50%\""] {
            XCTAssertTrue(body.contains(row), "the illustrative row \(row) was collateral")
        }
        XCTAssertTrue(body.contains("Prediction markets are among the most accurate forecasting tools ever measured."),
                      "the page's claim went with the caption")
    }

    /// 🪤 The screen has to still be reachable. A caption cannot lie on a sheet
    /// nobody presents, so "delete the sheet" would pass every scan above — and
    /// would be a different, larger change than #7580 asked for.
    func testOnboardingIsStillPresentedOnFirstLaunch() throws {
        let discover = try String(contentsOf: Self.discoverURL, encoding: .utf8)

        XCTAssertTrue(discover.contains("WelcomeView("),
                      "DiscoverView no longer presents the onboarding carousel")
        XCTAssertTrue(discover.contains("discover_onboarded"),
                      "the first-launch gate the sheet hangs on is gone")
    }

    // MARK: - Strawman

    /// The scans above are `XCTAssertFalse`/`XCTAssertNil` over a file read, so
    /// they all pass on an empty string. This is the test that says the reads
    /// found real Swift.
    func testTheSourceScanIsReadingTheFilesItThinksItIs() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)
        XCTAssertGreaterThan(body.count, 5_000, "WelcomeView.swift read back far too small")
        XCTAssertTrue(body.contains("struct WelcomeView: View"), "that is not the Swift file")
        XCTAssertTrue(body.contains("Surprisingly\\naccurate"),
                      "the page this suite is about is not in the file it read")

        let discover = try String(contentsOf: Self.discoverURL, encoding: .utf8)
        XCTAssertGreaterThan(discover.count, 20_000, "DiscoverView.swift read back far too small")

        // The literal extractor is the load-bearing part of the census: if it
        // returned nothing, the census would read as "no numbers on the screen".
        XCTAssertGreaterThan(Self.stringLiterals(in: body).count, 20,
                             "the string-literal scan found almost nothing in a file full of copy")
        XCTAssertTrue(Self.stringLiterals(in: #"let a = "x1"; let b = "y""#).contains("x1"),
                      "the extractor does not return the literals it is asked for")
        XCTAssertTrue(Self.stringLiterals(in: #"Text("a \"b\" c")"#).contains(#"a \"b\" c"#),
                      "the extractor stops at an escaped quote, so copy after one is unscanned")
    }

    // MARK: - Helpers

    /// Every double-quoted literal's inner text, in source spelling. The
    /// `\\.` alternative keeps an escaped quote from ending the match — without
    /// it the scan silently stops mid-string and everything after reads as clean.
    private static func stringLiterals(in source: String) -> [String] {
        let pattern = #""(?:[^"\\\n]|\\.)*""#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let ns = source as NSString
        return regex.matches(in: source, range: NSRange(location: 0, length: ns.length)).map {
            ns.substring(with: NSRange(location: $0.range.location + 1, length: $0.range.length - 2))
        }
    }

    private static func firstMatch(_ pattern: String, in source: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let ns = source as NSString
        guard let m = regex.firstMatch(in: source, range: NSRange(location: 0, length: ns.length))
        else { return nil }
        return ns.substring(with: m.range)
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given while
    /// `FileManager` standardises it, so prefix arithmetic between the two eats
    /// the middle out of the path. Going up the URL avoids the subtraction.
    private static var viewsDirectory: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
    }

    private static var viewURL: URL { viewsDirectory.appendingPathComponent("WelcomeView.swift") }
    private static var discoverURL: URL { viewsDirectory.appendingPathComponent("DiscoverView.swift") }
}
