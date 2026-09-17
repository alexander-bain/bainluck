import XCTest

/// #888, driven by a finger: **a reader who scrolls to the bottom of a league
/// page finds the markets that page downloaded.**
///
/// `LeagueGridSectionKeysMatchTheAPI888Tests` pins the vocabulary — every key
/// `sectionOrder` renders is one `league_futures.py` emits, and every key it
/// emits is either rendered or declared unrendered. That is a unit test about a
/// string list. It cannot say whether a reader ever *arrives* at the sections
/// those strings name, and arrival is the whole of the complaint: "league
/// buttons show only title grids, no other content."
///
/// ## Why this file exists, and why #888 lived for months
///
/// The still-photograph rig could not reach this surface. `tools/native-shoot.sh
/// --scroll N` clamps to `contentHeight - viewportHeight`, and a SwiftUI `List`
/// is lazy, so that height is only what has materialised — measured 2026-09-17,
/// `--scroll 2600` and `--scroll 11000` land on the SAME content (NBA ladder
/// ranks 14–18) and neither reaches the market sections below the 30-team
/// championship ladder. Two very different scroll values landing on the same
/// pixels is the tell that the bottom was never reached. So the bottom of this
/// page had never been photographed, and a defect that lives only there was
/// invisible to every LOOK the lane could pay.
///
/// XCUITest does not clamp: it swipes, the list materialises, and the next
/// swipe goes further. That is the only channel this lane has that can see the
/// bottom of a lazy list.
///
/// ## What it would have caught
///
/// Under the shipped defect the page rendered `series · awards ·
/// playoff_props · season_stats · novelty` against an API emitting `series ·
/// awards · props · season_stats · more_markets`. Three of the five keys
/// matched, so the page was not blank — it drew Awards and Season Stats and
/// silently dropped the rest. On NBA, measured on production 2026-09-17,
/// that is 11 markets drawn of 64 served, and 48 of the 53 missing sat in
/// `more_markets`, the classifier's DEFAULT bucket.
///
/// So the assertion is specifically on **More Markets**: it is the section the
/// defect hid, it is the biggest one on nearly every league, and a test that
/// merely found *a* section would have been green throughout the defect.
final class AReaderCanReachTheLeagueMarketSections888Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// How many swipes to spend walking down the league page.
    ///
    /// The NBA ladder is 30 self-labelled team cards at roughly a third of a
    /// screen each, and the market sections sit below all of them. Bounded
    /// rather than unbounded so a league that grows a ladder does not hang the
    /// suite: it reports how far it got instead.
    private static let swipeBudget = 90

    /// NBA, and the choice is not incidental: it is one of the three leagues
    /// (with NHL and UCL) that ux/1305 measured worst, it is in season, and it
    /// is what Alex taps in September.
    private static let route = "bainluck://playoffs/nba"

    func testTheMarketSectionsBelowTheLadderAreReachedAndDrawn() throws {
        let app = UITestLaunch.launchApp(extra: ["-launch_route", Self.route])
        _ = JourneyPrecondition.tabBar(of: app)

        // The router takes `LaunchRig.routeDelay` to act, so the page is not up
        // at launch. Waited for by its own title rather than by sleeping.
        let title = app.staticTexts.containing(
            NSPredicate(format: "label BEGINSWITH %@", "NBA Playoffs")
        ).firstMatch
        XCTAssertTrue(
            title.waitForExistence(timeout: 30),
            "The league page never opened on \(Self.route). Nothing below this line is about #888."
        )

        add(Self.shot(app, "1-top-of-the-league-page"))

        // Matched case-insensitively and by containment: a section header is a
        // `Label`, and whether the list style uppercases it is a rendering
        // decision this test has no business pinning.
        let moreMarkets = Self.header(app, "More Markets")
        let props = Self.header(app, "Props")

        // THE WALK STOPS ON HITTABILITY, NOT EXISTENCE. A lazy list puts a row
        // into the accessibility tree before it is on screen, so `exists` goes
        // true a screen early — the sibling #1472 journey measured that on
        // Discover and paid 39.6s to learn it.
        var swipes = 0
        while swipes < Self.swipeBudget, !moreMarkets.isHittable {
            app.swipeUp()
            swipes += 1
        }

        add(Self.shot(app, "2-bottom-of-the-league-page"))

        XCTAssertTrue(
            moreMarkets.isHittable,
            """
            \(swipes) swipes down the NBA league page and no "More Markets" section is on screen.

            TWO CAUSES, AND THEY NEED OPPOSITE FIXES — read /api/leagues/basketball_nba before \
            concluding either:
              * `sections.more_markets` is served and non-empty  ⇒ THIS IS #888 AGAIN. A client \
                key no longer matches an API key, `leagueData.sections[key]` is missing silently, \
                and everything behind it is gone with no empty state.
              * `sections.more_markets` is absent or empty       ⇒ a supply fact, not a defect \
                here. `more_markets` is the classifier's default return, so an empty one on an \
                in-season league is itself worth a look — but it is not this page's bug.
            """
        )

        // THE MARKETS MUST CARRY NUMBERS, NOT ZEROES. The first repaired
        // screenshot of this page had the section, had the markets, and printed
        // "0%" on every line: `/api/leagues/…` serves `probability` as a
        // FRACTION and every row prints `Int(prob)%`, so `Int(0.43) == 0`. A
        // test that stops at "the section is on screen" is green through that,
        // which is why this assertion is here and not in the unit suite alone.
        let percentages = app.staticTexts.matching(
            NSPredicate(format: "label MATCHES %@", "^[0-9]{1,3}%$")
        )
        var onScreen: [String] = []
        for index in 0..<percentages.count {
            let element = percentages.element(boundBy: index)
            if element.isHittable { onScreen.append(element.label) }
        }
        XCTAssertFalse(onScreen.isEmpty, "No probability is drawn anywhere in the visible sections.")
        XCTAssertFalse(
            onScreen.allSatisfy { $0 == "0%" },
            "Every probability on screen reads 0% (\(onScreen.count) of them). The markets arrived "
            + "and their numbers did not survive the scale: a fraction is being printed as a percent."
        )

        // The second repaired key, asserted separately so a failure names which
        // one broke. Softer on purpose: `props` carried 5 markets on NBA to
        // `more_markets`' 48, and a league can legitimately serve none.
        if !props.isHittable {
            add(XCTAttachment(string:
                "NOTE: no \"Props\" section was reached in \(swipes) swipes. NBA served 5 props "
                + "markets on 2026-09-17; an empty section is legitimate, so this is recorded "
                + "rather than failed."
            ))
        }

        // THE DEAD KEYS MUST NOT COME BACK AS LABELS. Under the defect the page
        // never printed these strings — the lookup missed and the section was
        // not built at all — so this is not a restatement of the assertion
        // above: it catches the OTHER repair anyone might reach for, which is
        // renaming the API's keys to match the client's.
        XCTAssertFalse(
            Self.header(app, "Playoff Props").exists,
            #"A section header reads "Playoff Props". That string belongs to the dead `playoff_props` key."#
        )
    }

    // MARK: - Helpers

    private static func header(_ app: XCUIApplication, _ text: String) -> XCUIElement {
        app.staticTexts.containing(
            NSPredicate(format: "label CONTAINS[c] %@", text)
        ).firstMatch
    }

    private static func shot(_ app: XCUIApplication, _ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
