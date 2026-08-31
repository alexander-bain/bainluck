import XCTest
@testable import Bain_Luck

/// UX-P217 — a related-futures row we have no price for must not print a number.
///
/// `RelatedFuture.probability` is `Double?`, and the backend serialises BOTH
/// "no price" and "priced at exactly zero" as `null`
/// (`float(x.current_probability) if x.current_probability else None` is a
/// truthiness test, not a nil test). So `nil` on the wire means "we cannot say",
/// and the client has no way to narrow it further.
///
/// Every text site in `RelatedFuturesView` used to coerce that to `0` before
/// formatting. `formatProbability(0)` returns "<1%" — so a row whose price never
/// arrived rendered a confident claim that the outcome is nearly impossible, at
/// 28pt bold in team colour on two of the sites, undimmed (because `isEliminated`
/// is correctly false for nil). The hand-rolled `Int(p * 100)%` sites printed a
/// flat "0%" instead, which is the same lie with worse rounding.
///
/// These tests pin the FORMATTER and the one shared text helper that three of the
/// render sites call. The remaining sites are inline in SwiftUI view bodies and
/// cannot be reached from a unit test; `backend/tests/test_ios_missing_probability_render.py`
/// is the containment guard that keeps them wired to the same formatter.
final class MissingProbabilityRenderTests: XCTestCase {

    // MARK: - The formatter

    func testNilRendersTheAbsentMarkerAndNotAProbability() {
        XCTAssertEqual(formatProbabilityOrDash(nil), "\u{2014}")
        XCTAssertNotEqual(formatProbabilityOrDash(nil), "<1%",
                          "the whole defect: no price became 'nearly impossible'")
        XCTAssertNotEqual(formatProbabilityOrDash(nil), "0%")
    }

    /// The absent marker must not drift from the one the ladder already ships.
    /// This is the assertion referenced by `absentProbabilityMarker`'s doc comment.
    func testAbsentMarkerMatchesTheLadderSpelling() {
        XCTAssertEqual(formatProbabilityOrDash(nil), ladderPercent(nil))
        XCTAssertEqual(absentProbabilityMarker, ladderPercent(nil))
    }

    /// A real zero is still a real reading and must NOT become a dash. This is the
    /// control that stops the fix from swallowing genuine data — the backend
    /// currently cannot send it, but the formatter is not the place to encode that.
    func testExplicitZeroIsStillRenderedAsAProbability() {
        XCTAssertEqual(formatProbabilityOrDash(0.0), "<1%")
        XCTAssertNotEqual(formatProbabilityOrDash(0.0), absentProbabilityMarker)
    }

    /// Priced rows are untouched — the fix must be invisible to the 187,713 open
    /// outcomes that do carry a price.
    func testPricedValuesAreUnchangedFromFormatProbability() {
        for value in [0.004, 0.01, 0.1, 0.42, 0.5, 0.905, 0.99, 0.996, 1.0] {
            XCTAssertEqual(formatProbabilityOrDash(value), formatProbability(value),
                           "priced rows must format identically to before (\(value))")
        }
    }

    func testRenderedPercentOverrideStillReachesTheFormatter() {
        XCTAssertEqual(formatProbabilityOrDash(0.425, renderedPercent: 43), "43%")
        // ...and is ignored for nil, because there is nothing to override.
        XCTAssertEqual(formatProbabilityOrDash(nil, renderedPercent: 43), absentProbabilityMarker)
    }

    // MARK: - The shared render helper (3 of the 7 sites call this)

    private func future(probability: Double?) throws -> RelatedFuture {
        let prob = probability.map { "\($0)" } ?? "null"
        let json = """
        {"market_id": 1, "market_name": "AL MVP", "outcome_id": 2,
         "outcome_name": "Aaron Judge", "probability": \(prob)}
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(RelatedFuture.self, from: Data(json.utf8))
    }

    func testSettledTextForAPricelessRowIsTheMarker() throws {
        let f = try future(probability: nil)
        XCTAssertNil(f.probability, "the fixture must actually decode a null price")
        XCTAssertEqual(settledProbabilityText(f), absentProbabilityMarker)
    }

    /// A priceless row is neither clinched nor eliminated — both booleans answer
    /// "we cannot say". That is correct, and it is also exactly why the TEXT had
    /// to change: nothing upstream of the text was going to catch this row.
    func testAPricelessRowIsNeitherClinchedNorEliminated() throws {
        let f = try future(probability: nil)
        XCTAssertFalse(isClinched(f))
        XCTAssertFalse(isEliminated(f))
    }

    func testSettledTextStillGradesPricedRows() throws {
        XCTAssertEqual(settledProbabilityText(try future(probability: 0.999)), "✓")
        XCTAssertEqual(settledProbabilityText(try future(probability: 0.001)), "<1%")
        XCTAssertEqual(settledProbabilityText(try future(probability: 0.42)), "42%")
    }
}
