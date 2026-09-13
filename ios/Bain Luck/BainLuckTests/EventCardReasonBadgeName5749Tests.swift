import XCTest
@testable import Bain_Luck

/// #5749 (iOS twin of the web fix, PR #5799) — a card's reason badge must be
/// decided by the SENTENCE THE TEMPLATE WROTE, never by the name interpolated
/// into it.
///
/// `EventCardView.reasonStyle` classified with bare `contains`, so the team name
/// styled its own card: `"kentucky wildcats leading after starting at 24%"`
/// contains "wild", and the row drew the yellow "something wild is happening"
/// bolt next to a sentence about a pre-game price. Measured on production
/// `teams`, 27 of 5,592 distinct names carry a trigger substring — 16 "wild"
/// (Minnesota Wild, Kentucky Wildcats, Deontay Wilder, Thiago Seyboth Wild …)
/// and 11 "even" (Benevento, Stevenage, every boxer named Steven). The specimen
/// names below are read from that table, not invented, because a hijack suite
/// built from names I chose would agree with whatever list I wrote.
///
/// The pattern table it was replaced with is the web's byte-for-byte, so the
/// two runtimes cannot drift on which badge a card wears.
///
/// Every test here asserts BOTH directions. A suite that only checked the
/// hijacks would pass just as well against `return .plain`, which would delete
/// the whole badge family rather than fix it — so each family is pinned on its
/// own served label, and `testTheFamilyStillStyles…` is the control the directive
/// named: `Minnesota Wild odds shifted 8% since open` KEEPS its purple arrow.
final class EventCardReasonBadgeName5749Tests: XCTestCase {

    private typealias Badge = EventCardView.ReasonBadge

    /// A name with none of the trigger substrings in it — the baseline every
    /// hijack name is compared against.
    private let neutralName = "Dallas Cowboys"

    /// Distinct `teams.name` values carrying a trigger substring, read from
    /// production 2026-09-12 (`LIKE '%wild%' OR LIKE '%even%'`). Not exhaustive
    /// — one per shape: the bare word as a whole word, the word inside a longer
    /// word, at the end of a name, and mid-token in a name that is not about
    /// wildness at all.
    private let hijackNames = [
        "Minnesota Wild",           // "wild" as its own word — \b alone does NOT save this
        "Iowa Wild",
        "Thiago Seyboth Wild",      // a US Open singles player
        "Kentucky Wildcats",        // "wild" inside a longer word
        "Northwestern Wildcats",
        "Arizona Wildcats",
        "Deontay Wilder",           // not a team, not about wildness
        "Benevento",                // "even" inside a longer word
        "Stevenage",
        "Steven Butler",
        "Gievenbeck",
        "Sekondi Eleven Wise",
    ]

    /// Served reason templates that carry a name, with `%@` where the name goes.
    /// Taken from the string literals in `feed_reasons.py` / `highlights.py`.
    private let nameCarryingTemplates = [
        "%@ leading after starting at 24%%",
        "%@ odds shifted 12%% since open",
        "%@ chance rose from 40%% to 55%%",
        "Big odds movement in %@",
        "Odds shifting in %@",
        "New favorite: %@ (62%%)",
        "New favorite in %@",
        "Resolving soon: %@ leads at 62%%",
        "%@ moved 7 points today in AL East",
        "%@ 62%% chance",
        "%@ has shifted since Sep 4",
    ]

    // MARK: - The defect

    func testATeamNamedWildDoesNotClaimAWildGame() {
        XCTAssertEqual(
            Badge.family(for: "Kentucky Wildcats leading after starting at 24%"),
            .plain,
            "the yellow bolt came from the WILDcats in the team name, not from anything wild in the sentence"
        )
        XCTAssertEqual(
            Badge.family(for: "Minnesota Wild leading after starting at 24%"),
            .plain,
            #"word boundaries are not the fix: \bwild\b matches "Minnesota Wild" too"#
        )
    }

    func testATeamNamedEvenIsNotVirtuallyEven() {
        XCTAssertEqual(
            Badge.family(for: "Benevento leading after starting at 24%"),
            .plain,
            "benEVENto is not a coin flip"
        )
        XCTAssertEqual(
            Badge.family(for: "Steven Butler leading after starting at 24%"),
            .plain,
            "every boxer named Steven was drawing the blue equals sign"
        )
    }

    /// The bare-word defect is not only about names: `Revenge game` is a served
    /// highlight label that contains "even" and drew the blue "virtually even"
    /// badge on a card whose whole point is that it is a grudge match.
    func testAServedLabelIsNotHijackedByItsOwnSpelling() {
        XCTAssertEqual(Badge.family(for: "Revenge game"), .plain)
    }

    // MARK: - The control: the family must still style its own sentences

    func testTheFamilyStillStylesTheSentenceTheTemplateWrote() {
        // The directive's control — it separates "the name stopped mattering"
        // from "the family stopped being styled".
        XCTAssertEqual(
            Badge.family(for: "Minnesota Wild odds shifted 8% since open"),
            .movement,
            "the same name, in a sentence that IS about odds, keeps its purple arrow"
        )
        XCTAssertEqual(Badge.family(for: "Wild game"), .wild, "the only served reason the wild family has")
        XCTAssertEqual(Badge.family(for: "Virtually even"), .even)
    }

    // MARK: - Every family, pinned on its own served labels
    //
    // Without these, deleting a pattern outright would pass the hijack tests.

    func testEveryServedReasonKeepsItsBadge() {
        let corpus: [(String, Badge)] = [
            // Orange — `feed_reasons.py` + `highlights.py`
            ("Upset result", .upset),
            ("Possible upset", .upset),
            ("Recent upset", .upset),
            ("Upset brewing", .upset),
            ("Upset underway", .upset),
            ("Won as 24% underdog", .upset),
            ("Dallas Cowboys leading as underdog", .upset),
            // Blue
            ("Virtually even", .even),
            ("Tight game", .even),
            ("Close matchup", .even),
            ("Close game", .even),
            // Purple
            ("Big odds movement in AL East", .movement),
            ("Odds shifting in AL East", .movement),
            ("Odds flipped", .movement),
            ("Odds moved", .movement),
            ("Odds moving faster", .movement),
            ("Odds shifting fast", .movement),
            ("Line moving", .movement),
            ("Big line movement", .movement),
            ("Shifted since Sep 4", .movement),
            ("Dallas Cowboys odds shifted 12% since open", .movement),
            // Green
            ("Starting soon", .startingSoon),
            // Yellow
            ("Wild game", .wild),
            // Plain — styled by nothing, before the fix and after it
            ("Starting in under an hour", .plain),
            ("Recently finished", .plain),
            ("Playoff game", .plain),
            ("Championship game", .plain),
            ("Coin flip", .plain),
            ("Comeback story", .plain),
            ("Rivalry game", .plain),
            ("Dallas Cowboys leading after starting at 24%", .plain),
        ]
        for (reason, expected) in corpus {
            XCTAssertEqual(Badge.family(for: reason), expected, "reason: \(reason)")
        }
    }

    /// The branch ORDER is load-bearing and is the web's: this one sentence
    /// matches two families, and it is a close matchup first.
    func testStartingSoonCloseMatchupIsStyledAsTheCloseMatchup() {
        XCTAssertEqual(Badge.family(for: "Starting soon — close matchup"), .even)
    }

    // MARK: - The invariant, over every hijack name × every template
    //
    // The web half proved "0 badge changes" by running the AST-extracted served
    // reason set through both classifiers. This is the same claim stated as a
    // property: the badge is a function of the TEMPLATE, so swapping the name
    // inside it can never change the badge.

    func testTheBadgeIsAFunctionOfTheTemplateNotTheName() {
        for template in nameCarryingTemplates {
            let expected = Badge.family(for: String(format: template, neutralName))
            for name in hijackNames {
                XCTAssertEqual(
                    Badge.family(for: String(format: template, name)),
                    expected,
                    "\(name) changed the badge on: \(String(format: template, neutralName))"
                )
            }
        }
    }

    /// …and the sweep above is only worth running if the templates it sweeps can
    /// actually carry a badge. Three of them are styled for the neutral name, so
    /// a classifier that returned `.plain` for everything would not pass it
    /// vacuously.
    func testTheSweptTemplatesAreNotAllPlain() {
        let styled = nameCarryingTemplates.filter {
            Badge.family(for: String(format: $0, neutralName)) != .plain
        }
        XCTAssertGreaterThanOrEqual(styled.count, 3, "the name-invariance sweep would be vacuous")
    }
}
