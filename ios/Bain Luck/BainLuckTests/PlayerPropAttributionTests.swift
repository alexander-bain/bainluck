import XCTest
@testable import Bain_Luck

/// L2-196 / C43 — player-prop grading must join to the box score by EXACT player
/// identity and fail closed on ambiguity. The old code matched on last-name substring
/// containment and returned the first (unstable) dictionary hit, so duplicate
/// surnames, suffixes, and substrings could grade a prop with another player's line.
/// These pin the pure `PlayerPropsCardView.actualStatValue(player:stat:box:)`.
final class PlayerPropAttributionTests: XCTestCase {

    // MARK: - Exact identity resolves; aliases apply after identity

    func testExactFullNameResolves() {
        let box = ["LeBron James": ["points": 30.0]]
        XCTAssertEqual(PlayerPropsCardView.actualStatValue(player: "LeBron James", stat: "points", box: box), 30.0)
    }

    func testStatAliasAppliedAfterUniqueIdentity() {
        // "rebounds" must resolve via the alias map ("reb") — but only once the
        // player identity is unique.
        let box = ["Nikola Jokic": ["reb": 12.0]]
        XCTAssertEqual(PlayerPropsCardView.actualStatValue(player: "Nikola Jokic", stat: "rebounds", box: box), 12.0)
    }

    func testPunctuationInsensitiveExactMatch() {
        // "A.J. Brown" and "AJ Brown" are the same identity once normalized.
        let box = ["A.J. Brown": ["points": 8.0]]
        XCTAssertEqual(PlayerPropsCardView.actualStatValue(player: "AJ Brown", stat: "points", box: box), 8.0)
    }

    // MARK: - Fail closed on the exact defect class

    func testSameSurnameDoesNotCrossAttribute() {
        // Two players share the surname "Brown". Grading "Bruce Brown" must return
        // Bruce's line — never Jaylen's via last-name substring containment.
        let box = ["Jaylen Brown": ["points": 24.0], "Bruce Brown": ["points": 6.0]]
        XCTAssertEqual(PlayerPropsCardView.actualStatValue(player: "Bruce Brown", stat: "points", box: box), 6.0)
        XCTAssertEqual(PlayerPropsCardView.actualStatValue(player: "Jaylen Brown", stat: "points", box: box), 24.0)
    }

    func testSuffixIsNotCollapsedIntoBaseName() {
        // "Michael Porter" and "Michael Porter Jr." are different people. A prop for
        // the base name must NOT grade against the Jr. box row — fail closed.
        let box = ["Michael Porter Jr.": ["points": 15.0]]
        XCTAssertNil(PlayerPropsCardView.actualStatValue(player: "Michael Porter", stat: "points", box: box))
    }

    func testSurnameOnlyPropDoesNotMatch() {
        // A bare surname is not an exact identity — no grade.
        let box = ["Jaylen Brown": ["points": 24.0]]
        XCTAssertNil(PlayerPropsCardView.actualStatValue(player: "Brown", stat: "points", box: box))
    }

    func testAmbiguousNormalizationCollisionFailsClosed() {
        // Two box rows normalize to the same identity ("aj brown"). We cannot know
        // which is meant → no grade, never a guess.
        let box = ["A.J. Brown": ["points": 8.0], "AJ Brown": ["points": 19.0]]
        XCTAssertNil(PlayerPropsCardView.actualStatValue(player: "AJ Brown", stat: "points", box: box))
    }

    func testMissingPlayerReturnsNil() {
        let box = ["LeBron James": ["points": 30.0]]
        XCTAssertNil(PlayerPropsCardView.actualStatValue(player: "Anthony Davis", stat: "points", box: box))
    }

    func testEmptyBoxReturnsNil() {
        XCTAssertNil(PlayerPropsCardView.actualStatValue(player: "LeBron James", stat: "points", box: [:]))
    }

    func testUniquePlayerMissingStatReturnsNil() {
        // Identity resolves but the requested stat is genuinely absent → nil (not a
        // fabricated 0), so the rung stays ungraded.
        let box = ["LeBron James": ["points": 30.0]]
        XCTAssertNil(PlayerPropsCardView.actualStatValue(player: "LeBron James", stat: "blocks", box: box))
    }

    // MARK: - Value semantics used by push / live / completed display

    func testExactValueReturnedForPushComparison() {
        // The rung's push (actual == threshold) and hit/miss are computed by the view
        // from this value + eventStatus; the lookup itself is status-agnostic and must
        // return the precise number so a push isn't mis-graded as a hit or miss.
        let box = ["Stephen Curry": ["three pointers": 5.0]]
        XCTAssertEqual(PlayerPropsCardView.actualStatValue(player: "Stephen Curry", stat: "three pointers", box: box), 5.0)
    }

    // MARK: - Normalization unit

    func testNormalizedNameCollapsesWhitespaceAndPunctuation() {
        XCTAssertEqual(PlayerPropsCardView.normalizedPlayerName("  LeBron   James "), "lebron james")
        XCTAssertEqual(PlayerPropsCardView.normalizedPlayerName("A.J. Brown"), "aj brown")
        XCTAssertNotEqual(PlayerPropsCardView.normalizedPlayerName("Michael Porter"),
                          PlayerPropsCardView.normalizedPlayerName("Michael Porter Jr."))
    }
}
