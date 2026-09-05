import XCTest
@testable import Bain_Luck

/// G2 — "the US Open exists in the app" includes being findable in Search.
///
/// Measured against production on 2026-09-05: `/api/events/search?q=US Open`
/// returns **0 events** and 0 teams, while `?q=Alcaraz` returns five matches whose
/// sport key is `tennis_atp_us_open`. Nothing in an event's searchable text says
/// "US Open", so the tournament is invisible to the query that names it. The hub
/// row is the phone's answer to that, and this file guards the matcher that
/// decides when to draw it.
final class FeaturedTournamentMatchTests: XCTestCase {

    private let catalog = [
        FeaturedTournament(
            slug: "us-open",
            title: "US Open",
            subtitle: "Live matches, results, title odds",
            icon: "tennis.racket",
            aliases: ["flushing meadows"]
        ),
        FeaturedTournament(
            slug: "the-open",
            title: "The Open Championship",
            subtitle: "Golf's oldest major",
            icon: "figure.golf"
        ),
    ]

    private func slugs(_ query: String) -> [String] {
        featuredTournaments(matching: query, in: catalog).map(\.slug)
    }

    // MARK: - The query a person actually types

    func testThePlainNameFindsTheHub() {
        XCTAssertEqual(slugs("US Open"), ["us-open"])
        XCTAssertEqual(slugs("us open"), ["us-open"])
        XCTAssertEqual(slugs("Us OPEN"), ["us-open"])
    }

    func testPunctuationAndSpacingDoNotHideTheHub() {
        // Someone typing the tournament's name properly must not be punished for it.
        XCTAssertEqual(slugs("U.S. Open"), ["us-open"])
        XCTAssertEqual(slugs("us-open"), ["us-open"])
        XCTAssertEqual(slugs("  us   open  "), ["us-open"])
    }

    func testTheNameRunTogetherAsOneWordFindsTheHub() {
        // Production returns 0 futures for "USOpen" where "US Open" returns 10, so
        // this spelling is the one the server helps with least.
        XCTAssertEqual(slugs("usopen"), ["us-open"])
        XCTAssertEqual(slugs("USOpen"), ["us-open"])
    }

    func testExtraWordsAroundTheNameStillFindTheHub() {
        XCTAssertEqual(slugs("us open tennis"), ["us-open"])
        XCTAssertEqual(slugs("the us open"), ["us-open"])
        XCTAssertEqual(slugs("us open 2026"), ["us-open"])
    }

    func testAnAliasFindsTheHub() {
        XCTAssertEqual(slugs("flushing meadows"), ["us-open"])
        XCTAssertEqual(slugs("Flushing Meadows tennis"), ["us-open"])
    }

    // MARK: - What must NOT match

    func testTheGenericHalfOfTheNameMatchesNothing() {
        // This is the whole reason the matcher requires every token. "Open" is a
        // word in four majors and in "opening weekend"; offering a tennis hub to
        // anyone who types it would make Search worse, not better.
        XCTAssertEqual(slugs("open"), [])
        XCTAssertEqual(slugs("Open"), [])
    }

    func testTheOtherGenericHalfMatchesNothing() {
        XCTAssertEqual(slugs("us"), [])
        XCTAssertEqual(slugs("US"), [])
    }

    func testAWordThatMerelyCONTAINSTheCollapsedNameMatchesNothing() {
        // The collapsed comparison is an equality, not a `contains`, precisely
        // because "housopener" contains "usopen" and names no tournament.
        XCTAssertEqual(slugs("housopener"), [])
        XCTAssertEqual(slugs("thusopened"), [])
    }

    func testAnUnrelatedQueryMatchesNothing() {
        XCTAssertEqual(slugs("Alcaraz"), [])
        XCTAssertEqual(slugs("Lakers"), [])
        XCTAssertEqual(slugs("Fed rate cut"), [])
    }

    func testAnEmptyOrPunctuationOnlyQueryMatchesNothing() {
        XCTAssertEqual(slugs(""), [])
        XCTAssertEqual(slugs("   "), [])
        XCTAssertEqual(slugs("!!!"), [])
    }

    // MARK: - Two tournaments sharing a word

    func testASharedWordDoesNotCrossMatchTheTwoTournaments() {
        // Both catalog entries contain "Open". Neither may answer for the other.
        XCTAssertEqual(slugs("The Open Championship"), ["the-open"])
        XCTAssertFalse(slugs("us open").contains("the-open"))
        XCTAssertFalse(slugs("open championship").contains("us-open"))
    }

    func testALeadingArticleIsOptional() {
        // Nobody types "the" when they search for The Open Championship, and the
        // rest of the name is still required in full — so this costs no precision.
        XCTAssertEqual(slugs("open championship"), ["the-open"])
        XCTAssertEqual(slugs("theopenchampionship"), ["the-open"])
        XCTAssertEqual(slugs("openchampionship"), ["the-open"])
        // The article alone is still not a name.
        XCTAssertEqual(slugs("the"), [])
        XCTAssertEqual(slugs("championship"), [])
    }

    // MARK: - The shipping catalog

    func testTheShippingCatalogOffersTheUSOpenHub() {
        // The default argument is the list Browse and Search both draw. If the US
        // Open ever leaves it, this says so rather than the surface going quiet.
        let live = featuredTournaments(matching: "US Open")
        XCTAssertEqual(live.map(\.slug), ["us-open"])
        XCTAssertEqual(live.first?.title, "US Open")
    }

    func testTheShippingCatalogIsNotEmpty() {
        // Search's "Tournaments" section and Browse's featured grid are both gated
        // on this list being non-empty; an empty catalog silently removes both.
        XCTAssertFalse(featuredTournaments.isEmpty)
    }

    func testEverySlugInTheShippingCatalogIsUnique() {
        // `id` is the slug and both surfaces `ForEach` over it.
        let slugs = featuredTournaments.map(\.slug)
        XCTAssertEqual(Set(slugs).count, slugs.count, "duplicate slug in the featured catalog")
    }

    func testEveryEntryInTheShippingCatalogMatchesItsOwnTitle() {
        // A catalog entry Search can never surface is a Browse-only entry wearing
        // a Search costume.
        for hub in featuredTournaments {
            XCTAssertEqual(
                featuredTournaments(matching: hub.title).map(\.slug).first,
                hub.slug,
                "\"\(hub.title)\" does not match its own title"
            )
        }
    }
}
