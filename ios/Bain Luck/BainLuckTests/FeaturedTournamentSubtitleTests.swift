import XCTest
@testable import Bain_Luck

/// The line under a featured hub's title is a claim about RIGHT NOW, and the
/// card is drawn 50 weeks a year when that claim is false.
///
/// Shot on 2026-09-16, three days after Alexander Zverev won the title:
/// Browse's first card read "US Open — Live matches, results, title odds", and
/// a search for "us open" printed the same line as its top row with the app's
/// own event rows directly beneath it, every one stamped FINAL · Sep 13. The
/// hub those cards lead to was already honest — "LIVE NOW · No match is being
/// played right now", "Settled · Alexander Zverev won the title" — so the lie
/// was one tap wide and lived entirely in the catalog.
///
/// Every test below fixes its own clock. `subtitle(asOf:)`'s default is
/// `Date()`, so an assertion that did not pass one would pass today and start
/// failing on its own the next time a tournament is on (gotcha #44).
final class FeaturedTournamentSubtitleTests: XCTestCase {

    private func at(_ iso: String) -> Date {
        guard let date = parseFlexibleDate(iso) else {
            XCTFail("test clock \(iso) does not parse")
            return .distantPast
        }
        return date
    }

    private let usOpen2026 = FeaturedTournament(
        slug: "us-open",
        title: "US Open",
        liveSubtitle: "Live matches, results, title odds",
        restingSubtitle: "Results and title odds",
        liveThrough: "2026-09-14T06:00:00+00:00",
        icon: "tennis.racket"
    )

    // MARK: - The two states

    func testAMatchdayInsideTheEditionSaysLive() {
        // 5 September 2026: the tournament is on, and the promise is true.
        XCTAssertEqual(
            usOpen2026.subtitle(asOf: at("2026-09-05T18:00:00+00:00")),
            "Live matches, results, title odds"
        )
    }

    func testTheDayTHISWASSHOTSaysResults() {
        // The specimen. 2026-09-16, three days past the final.
        XCTAssertEqual(
            usOpen2026.subtitle(asOf: at("2026-09-16T18:40:00+00:00")),
            "Results and title odds"
        )
    }

    func testTheMONTHTheOldDocstringNamedSaysResults() {
        // The shipped comment predicted its own defect in as many words —
        // "Browse will keep offering the US Open in March". It does; it just no
        // longer offers it as a live one.
        XCTAssertEqual(
            usOpen2026.subtitle(asOf: at("2027-03-11T12:00:00+00:00")),
            "Results and title odds"
        )
    }

    // MARK: - The boundary

    func testTheLastInstantOfTheWindowIsSTILLLive() {
        // Inclusive on purpose: the stored instant is the last moment a match can
        // be in progress, not the first moment it cannot.
        XCTAssertEqual(
            usOpen2026.subtitle(asOf: at("2026-09-14T06:00:00+00:00")),
            "Live matches, results, title odds"
        )
    }

    func testOneSecondPastTheWindowRests() {
        XCTAssertEqual(
            usOpen2026.subtitle(asOf: at("2026-09-14T06:00:01+00:00")),
            "Results and title odds"
        )
    }

    // MARK: - Every failure is an understatement, never a lie

    func testAHubWithNoEndDateNeverClaimsToBeLive() {
        // `liveThrough: nil` is "we do not know when this ends". The safe answer
        // to that is the resting line — a hub nobody dated must not assert a
        // state nobody can check.
        let undated = FeaturedTournament(
            slug: "the-open",
            title: "The Open Championship",
            liveSubtitle: "Live rounds and leaderboard",
            restingSubtitle: "Results and winner odds",
            icon: "figure.golf"
        )
        XCTAssertEqual(
            undated.subtitle(asOf: at("2026-07-16T12:00:00+00:00")),
            "Results and winner odds"
        )
    }

    func testAnUnparseableEndDateRestsRatherThanGoingLiveForever() {
        // A typo in the catalog must not read as "no end", which under a
        // `now <= end` test written the other way round would have meant
        // "always live".
        let typo = FeaturedTournament(
            slug: "us-open",
            title: "US Open",
            liveSubtitle: "Live matches, results, title odds",
            restingSubtitle: "Results and title odds",
            liveThrough: "the fourteenth of September",
            icon: "tennis.racket"
        )
        XCTAssertEqual(
            typo.subtitle(asOf: at("2026-09-05T18:00:00+00:00")),
            "Results and title odds"
        )
    }

    // MARK: - The shipping catalog

    func testTheShippedUSOpenCardRestsNowThatTheTitleIsWon() {
        // Reads the list Browse and Search actually draw, not a fixture — a fix
        // that lands only in the test's own copy of the catalog changes no pixel.
        guard let hub = featuredTournaments.first(where: { $0.slug == "us-open" }) else {
            return XCTFail("the US Open left the shipping catalog")
        }
        XCTAssertEqual(
            hub.subtitle(asOf: at("2026-09-16T18:40:00+00:00")),
            "Results and title odds"
        )
        // And the same entry was live during the tournament, so this is a window
        // and not a permanent removal of the live wording.
        XCTAssertEqual(
            hub.subtitle(asOf: at("2026-09-05T18:00:00+00:00")),
            "Live matches, results, title odds"
        )
    }

    func testNoShippedEntryClaimsLiveWithoutADateSayingUntilWhen() {
        // The class guard. The next hub added to the catalog gets the live
        // wording only if it also says when that wording expires; otherwise it
        // is this defect again under a different tournament's name.
        for hub in featuredTournaments where hub.liveSubtitle.localizedCaseInsensitiveContains("live") {
            XCTAssertNotNil(
                parseFlexibleDate(hub.liveThrough),
                "\(hub.slug) promises a live state with no parseable liveThrough"
            )
        }
    }

    func testNoShippedRestingLineClaimsALiveState() {
        // The resting line is what a reader sees for most of the year; a "live"
        // in it would make the window pointless.
        for hub in featuredTournaments {
            XCTAssertFalse(
                hub.restingSubtitle.localizedCaseInsensitiveContains("live"),
                "\(hub.slug)'s resting subtitle claims a live state: \"\(hub.restingSubtitle)\""
            )
        }
    }
}
