import XCTest
@testable import Bain_Luck

/// #4031: the concept card's field qualifier must read as a phrase, not as arithmetic.
///
/// The card stacks `name · probability chip · movement · field qualifier` on one
/// line. While the qualifier was a bare `of \(fieldSize)` the line rendered
///
///     Tadej Pogacar  75%  of 30
///
/// which, read aloud, is "seventy-five percent OF THIRTY" — an arithmetic claim
/// (22.5) rather than the size of the field. Web fixed its half in #3989 and
/// renders `field of 30`; this is the native half of the same defect, and the
/// noun is the whole fix.
///
/// Why these assertions live on a `static func` rather than on the rendered view:
/// the card's other helpers (`probabilityLabel`, `movementLabel`) are
/// `private func`s on the View and are therefore unreachable from
/// `@testable import` — every test that wants them can only paraphrase their
/// arithmetic, which is a test of the paraphrase. `fieldSizeLabel` takes the one
/// value that decides it and returns the string the card prints, so these run on
/// the production path.
final class ConceptFieldQualifierTests: XCTestCase {

    private func label(_ fieldSize: Int?) -> String? {
        NativeConceptDiscoverCard.fieldSizeLabel(fieldSize)
    }

    // MARK: - The defect itself

    /// The live rank-1 Discover specimen at the time of the fix:
    /// `event:cycling:vuelta-2026`, Pogacar 0.751, `field_size: 30`.
    func testThirtyRiderFieldNamesTheField() {
        XCTAssertEqual(label(30), "field of 30")
    }

    /// The F1 concept card in the same feed.
    func testTwentyTwoCarFieldNamesTheField() {
        XCTAssertEqual(label(22), "field of 22")
    }

    /// The regression this issue exists to close: whatever else changes, the
    /// qualifier must never again be a bare "of N". Asserted as a shape so a
    /// future edit that drops the noun fails here rather than on a reader's
    /// screen.
    func testQualifierIsNeverBareArithmetic() {
        for size in [3, 4, 10, 22, 30, 176] {
            guard let text = label(size) else {
                return XCTFail("a field of \(size) must print a qualifier")
            }
            XCTAssertFalse(
                text.range(of: "^of \\d+$", options: .regularExpression) != nil,
                "the qualifier read as arithmetic: \(text)"
            )
            XCTAssertTrue(text.hasPrefix("field of "), "the noun is missing: \(text)")
        }
    }

    // MARK: - The head-to-head guard, which is correct and must not move

    /// A 52% favourite in a two-way fight and a 52% favourite in a 30-rider field
    /// are different facts — but a two-way fight needs no qualifier at all, and
    /// #4031's verification note names a live UFC bout at `field_size: 2` that
    /// must keep printing nothing. The boundary is asserted on both sides so a
    /// mutant that flips `> 2` to `>= 2` (or to `> 1`) dies here.
    func testHeadToHeadPrintsNothing() {
        XCTAssertNil(label(2))
    }

    func testThreeIsTheFirstFieldWorthNaming() {
        XCTAssertEqual(label(3), "field of 3")
    }

    func testDegenerateFieldsPrintNothing() {
        XCTAssertNil(label(1))
        XCTAssertNil(label(0))
        XCTAssertNil(label(-1))
    }

    // MARK: - Absence

    /// Most concepts carry no field size; the card prints nothing rather than a
    /// placeholder.
    func testAbsentFieldSizePrintsNothing() {
        XCTAssertNil(label(nil))
    }
}
