import XCTest
import SwiftUI
@testable import Bain_Luck

/// #7174 — the Accuracy surface's second statistic is an equal-weighted MEAN, and
/// it was headed `MCE`.
///
/// The contradiction was visible without knowing any of this: production on
/// 2026-09-19 printed Polymarket at `ECE 2.7pp` beside `MCE 2.6pp`, and a maximum
/// of a set of errors cannot sit below a mean of the same errors. Web renamed the
/// column to `Bucket` the same day (#7178); this is the iOS twin, and the two
/// surfaces are supposed to print the same digits under the same word (#894).
///
/// 🪤 WHAT THESE TESTS DELIBERATELY DO NOT DO: assert that the word "maximum"
/// is absent. calibration/2611 wrote that guard first and it RED-LIT THE FIX,
/// because the honest way to withhold a claim in English is to negate it in
/// front of the reader ("A mean, not a maximum") — #4113's trap, reproduced by
/// writing the obvious guard. What is graded here is what the label ASSERTS,
/// measured as arithmetic and as ink.
///
/// 🪤 AND NOT A FIT CLAIM. The header got longer, so the numeric block got wider
/// and the label column got narrower. Whether every source name still draws is
/// carried by the 390pt screenshots on the PR, exactly as `#3954` ruled: the
/// arithmetic model that could have answered it was measured wrong by ~21pt in
/// the safe-looking direction, and a guard that mispredicts is worse than none.
/// What is asserted below is the part arithmetic CAN own — that the width model
/// and the view are measuring the same word.
@MainActor
final class TheBucketColumnIsAMeanNotAMaximum7174Tests: XCTestCase {

    // MARK: - The arithmetic that made the old header false

    /// A cohort shaped like the specimen on the issue: one busy bucket carrying a
    /// wide error, two thin ones that are nearly perfect.
    ///
    /// n-weighted, the busy bucket dominates (ECE ≈ 3.9pp). Equal-weighted, the two
    /// thin buckets pull it down (1.7pp). So the second number sits BELOW the first
    /// — which is the ordinary behaviour of these two means, and impossible for a
    /// maximum. Built through `aggregate` rather than by constructing `AggBucket`s,
    /// so the production rounding is in the path.
    private static let contradictionPayload = """
    {
      "population_version": "\(CalibrationRenderSmokeTests.renderableVersion)",
      "buckets": [
        {"bucket_idx": 1, "source": "polymarket", "category": "politics", "price_moved": true,
         "n": 10000, "winners": 1400, "avg_prob": 0.10, "sum_prob": 1000.0,
         "sum_sq_err": 160.0, "ci_lower": 0.13, "ci_upper": 0.15},
        {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": true,
         "n": 100, "winners": 50, "avg_prob": 0.50, "sum_prob": 50.0,
         "sum_sq_err": 25.0, "ci_lower": 0.40, "ci_upper": 0.60},
        {"bucket_idx": 9, "source": "polymarket", "category": "politics", "price_moved": true,
         "n": 100, "winners": 91, "avg_prob": 0.90, "sum_prob": 90.0,
         "sum_sq_err": 9.0, "ci_lower": 0.84, "ci_upper": 0.95}
      ],
      "total_markets": 3, "total_outcomes": 10200, "total_winners": 1541,
      "generated_at": "2026-09-19T04:00:00+00:00"
    }
    """

    private func aggregated(_ json: String) throws -> [CalibrationMath.AggBucket] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(CalibrationData.self, from: Data(json.utf8))
        return CalibrationMath.aggregate(data.buckets)
    }

    /// The number under this column is bounded by the MEAN of the bucket errors,
    /// never by the worst of them.
    ///
    /// This is the whole defect in one assertion. If a later change makes `mce()`
    /// an actual maximum, this fails and the label has to be revisited with it —
    /// which is the coupling the old code did not have, and the reason the two
    /// drifted for as long as they did.
    func testTheBucketNumberIsAMeanAndSitsBelowTheWorstBucket() throws {
        let agg = try aggregated(Self.contradictionPayload)
        let errors = agg.map { abs($0.error) }
        let worst = try XCTUnwrap(errors.max())
        let mean = errors.reduce(0, +) / Double(errors.count)

        XCTAssertEqual(CalibrationMath.mce(agg), mean, accuracy: 0.0001,
                       "the Bucket column is not the equal-weighted mean of the bucket errors")
        XCTAssertLessThan(
            CalibrationMath.mce(agg), worst,
            "the Bucket figure came out at the worst bucket's \(worst)pp \u{2014} if this "
            + "value really is a maximum now, the header that calls it a per-bucket average "
            + "is the thing that is wrong")
    }

    /// The specimen behaviour itself: this column can read BELOW the ECE beside it.
    ///
    /// That pair is what a reader sees, and under the old header it was an
    /// arithmetic impossibility printed as a fact. Asserted on the cohort figures
    /// the view actually draws, not on the raw math, so a change to which cohort
    /// the surface leads with is in scope.
    func testTheColumnCanReadBelowTheECEBesideIt() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(
            CalibrationData.self, from: Data(Self.contradictionPayload.utf8))
        let model = CalibrationViewModel(preloaded: data)

        XCTAssertLessThan(
            model.cohortMCE, model.cohortECE,
            "the fixture no longer reproduces the specimen (ECE "
            + "\(model.cohortECE)pp, Bucket \(model.cohortMCE)pp) \u{2014} it exists to hold "
            + "the pair that the word MCE contradicted, and a fixture that does not "
            + "reproduce it proves nothing about the rename")
    }

    // MARK: - The word, and the width it costs

    /// The rename tracks web, because the two surfaces publish the same figure and
    /// #894 exists so they do not describe it differently.
    func testTheHeaderIsTheWordWebShipped() {
        XCTAssertEqual(CalibrationSourceTableGeometry.Header.bucket, "Bucket")
    }

    /// The width model must measure the word the table DRAWS.
    ///
    /// Before this ship, `numericWidths` spelled `"MCE"` and the view spelled
    /// `Text("MCE")` — two literals, no connection. The second half of this test is
    /// what makes the first half worth having: the old word measures STRICTLY
    /// NARROWER, so a view that drew `Bucket` over a column still sized for `MCE`
    /// would clip the header, and clip it at the leading edge because the column is
    /// trailing-aligned. That failure prints a plausible word, not damage.
    func testTheWidthModelMeasuresTheWordTheTableDraws() {
        let values = ["2.6", "17.3", "\u{2014}"]
        let sized = CalibrationSourceTableGeometry.numericWidths(
            n: ["437,910"], ece: ["2.7"], mce: values, brier: ["0.248"])

        XCTAssertEqual(
            sized.mce,
            CalibrationSourceTableGeometry.columnWidth(
                header: CalibrationSourceTableGeometry.Header.bucket, values: values),
            accuracy: 0.001,
            "the column is not sized against the header constant the view draws")

        let asTheOldWord = CalibrationSourceTableGeometry.columnWidth(
            header: "MCE", values: values)
        XCTAssertGreaterThan(
            sized.mce, asTheOldWord,
            "`Bucket` measured no wider than `MCE` (\(sized.mce)pt vs \(asTheOldWord)pt), so "
            + "this test cannot tell the two apart and the drift it is meant to catch would "
            + "pass")
    }

    /// The Category Breakdown table's last column is still a literal, and a literal
    /// cannot notice that the word above it grew.
    ///
    /// 46pt held `MCE`. It is 52 now because `Bucket` is longer; this asserts the
    /// literal against measured ink rather than against the eye that picked it.
    func testTheCategoryTablesLastColumnClearsItsHeader() {
        let ink = CalibrationSourceTableGeometry.textWidth(
            CalibrationSourceTableGeometry.Header.bucket, font: .header)
        XCTAssertGreaterThanOrEqual(
            CalibrationSourceTableGeometry.categoryBucketColumnWidth, ink,
            "the Category Breakdown column is "
            + "\(CalibrationSourceTableGeometry.categoryBucketColumnWidth)pt and the word "
            + "\(CalibrationSourceTableGeometry.Header.bucket) draws \(ink)pt \u{2014} a "
            + "trailing-aligned header wider than its box loses its first characters")
    }

    // MARK: - The half no value assertion can reach

    /// BOTH tables draw the header from the constant, asserted by SCANNING THE
    /// SOURCE.
    ///
    /// 🔴 This is here because the mutation run said so. `Text("MCE")` put back at
    /// either call site, with the width model still sizing `Bucket`, SURVIVED every
    /// other test in this file: the headers are drawn inside a `@ViewBuilder`
    /// returning an opaque type, so no behavioural assertion in a pure suite can
    /// read the string that reaches the screen. The constants above make the two
    /// spellings share one definition; nothing except this test makes the view
    /// USE it, and a constant nobody reads is decoration.
    ///
    /// It scans for the absence of a hard-coded header rather than for the
    /// presence of the constant, because the failure being guarded is a literal
    /// creeping back in — and a test that only checked the constant was mentioned
    /// would pass on a file that mentioned it once and drew a literal twice.
    /// Comments are stripped first: this file's own prose says `MCE` repeatedly,
    /// on purpose, and a raw substring scan would read that as the defect.
    func testBothTablesDrawTheHeaderFromTheConstant() throws {
        let source = Self.codeText(of: "Bain Luck/Views/CalibrationView.swift")
        XCTAssertFalse(source.isEmpty,
                       "CalibrationView.swift could not be read; this test proves nothing.")

        XCTAssertFalse(
            source.contains("\"MCE\""),
            "a hard-coded \"MCE\" header is back in the view. The width model sizes this "
            + "column for \(CalibrationSourceTableGeometry.Header.bucket), so the reader "
            + "gets the false word in a tidy-looking box, and every value test in this "
            + "file still passes")

        let drawn = source.components(separatedBy: "header.bucket").count - 1
            + source.components(separatedBy: "Header.bucket").count - 1
        XCTAssertGreaterThanOrEqual(
            drawn, 2,
            "the Source Comparison and Category Breakdown headers are both supposed to "
            + "draw from the constant; found \(drawn) reference(s). One of the two tables "
            + "has gone back to spelling its own header")
    }

    /// The repo's `ios/Bain Luck` directory, from this file's own path. Same
    /// resolution as the other source-scanning suites, deliberately identical so
    /// two scans of one file cannot read different files.
    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    private static func codeText(of relativePath: String) -> String {
        let source = (try? String(
            contentsOf: projectDirectory.appendingPathComponent(relativePath), encoding: .utf8
        )) ?? ""
        return source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { stripComment(String($0)) }
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
            .joined(separator: "\n")
    }

    /// String-aware: a naive `range(of: "//")` cuts every line holding a URL
    /// literal, and it would also cut a trailing comment off a line of real code
    /// and leave the code — which is the direction that matters here.
    private static func stripComment(_ line: String) -> String {
        var inString = false
        var previous: Character? = nil
        let characters = Array(line)
        var index = 0
        while index < characters.count {
            let c = characters[index]
            if c == "\"" && previous != "\\" { inString.toggle() }
            if !inString, c == "/", index + 1 < characters.count, characters[index + 1] == "/" {
                return String(characters[..<index])
            }
            previous = c
            index += 1
        }
        return line
    }

    /// Dynamic Type moves that ink, and the literal does not move with it.
    ///
    /// Recorded rather than asserted as a pass: this column was already a literal
    /// before #7174 and sizing the whole Category table is #3954's unfinished half,
    /// not this ship. What this test refuses to allow is the literal being wrong at
    /// the DEFAULT size, which is the size the screenshots are taken at.
    func testTheCategoryColumnIsKnownToBeALiteralThatDynamicTypeOutgrows() {
        let atLarge = CalibrationSourceTableGeometry.textWidth(
            CalibrationSourceTableGeometry.Header.bucket, font: .header, typeSize: .large)
        let atAccessibility = CalibrationSourceTableGeometry.textWidth(
            CalibrationSourceTableGeometry.Header.bucket, font: .header,
            typeSize: .accessibility3)
        XCTAssertGreaterThan(
            atAccessibility, atLarge,
            "the header ink did not grow with Dynamic Type, so this test is not measuring "
            + "what it claims to measure")
    }
}
