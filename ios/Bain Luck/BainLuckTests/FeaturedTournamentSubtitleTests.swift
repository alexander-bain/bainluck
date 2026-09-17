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

    // MARK: - The fact behind the line (ux/1304's consumer)

    /// `isBeingPlayed(asOf:)` names the clock rule the subtitle was already
    /// applying, so a caller that needs the FACT does not compare rendered
    /// strings or re-parse `liveThrough` against its own `now`.
    ///
    /// The consumer is Browse's ordering — a featured hub leads only while its
    /// edition is being played — and this test exists because a second detector
    /// of one rule is how two surfaces come to disagree about whether a
    /// tournament is on. That is not hypothetical here: Browse's first card on
    /// 2026-09-16 was the US Open, three days after its final, while the hub it
    /// led to said "No match is being played right now".
    func testTheFactAndTheLineAgreeAtEveryClock() {
        // Sampled either side of the boundary and far outside it, including the
        // two instants the boundary tests above pin. If these two ever disagree
        // at any clock, one of them has grown its own copy of the rule.
        let clocks = [
            "2026-09-05T18:00:00+00:00",   // mid-tournament
            "2026-09-14T05:59:59+00:00",   // a second inside
            "2026-09-14T06:00:00+00:00",   // the inclusive last instant
            "2026-09-14T06:00:01+00:00",   // a second outside
            "2026-09-16T18:40:00+00:00",   // the day this was shot
            "2027-03-11T12:00:00+00:00",   // half a year later
            "2020-01-01T00:00:00+00:00",   // before the edition existed
        ]
        for clock in clocks {
            let now = at(clock)
            XCTAssertEqual(
                usOpen2026.isBeingPlayed(asOf: now),
                usOpen2026.subtitle(asOf: now) == usOpen2026.liveSubtitle,
                "at \(clock) the fact and the line disagree, so there are two clock rules now"
            )
        }
    }

    /// The boundary is the SAME boundary — inclusive — read directly off the
    /// fact rather than inferred from the string.
    func testTheFactIsInclusiveAtTheLastInstantAndFalseOneSecondLater() {
        XCTAssertTrue(usOpen2026.isBeingPlayed(asOf: at("2026-09-14T06:00:00+00:00")))
        XCTAssertFalse(usOpen2026.isBeingPlayed(asOf: at("2026-09-14T06:00:01+00:00")))
    }

    /// The fact fails to `false` on every input the subtitle understates on.
    /// A hub wrongly called finished sits lower in a list and keeps its results;
    /// a hub wrongly called live leads the tab three days after its final.
    func testTheFactUnderstatesOnAnAbsentOrUnparsableDate() {
        let undated = FeaturedTournament(
            slug: "the-open",
            title: "The Open Championship",
            liveSubtitle: "Live rounds and leaderboard",
            restingSubtitle: "Results and winner odds",
            icon: "figure.golf"
        )
        XCTAssertFalse(
            undated.isBeingPlayed(asOf: at("2026-07-16T12:00:00+00:00")),
            "a hub nobody dated asserts a state nobody can check"
        )

        let typo = FeaturedTournament(
            slug: "masters",
            title: "The Masters",
            liveSubtitle: "Live rounds and leaderboard",
            restingSubtitle: "Results and winner odds",
            liveThrough: "not a date",
            icon: "figure.golf"
        )
        XCTAssertFalse(
            typo.isBeingPlayed(asOf: at("2026-04-10T18:00:00+00:00")),
            "an unparsable window would otherwise lead Browse forever"
        )
    }

    /// Nothing shipped in the catalog claims to be being played on the day this
    /// landed — the same assertion as the resting-line scan below, taken on the
    /// fact so a future consumer of it is covered too.
    func testNoShippedHubIsBeingPlayedOnTheDayThisLanded() {
        let now = at("2026-09-16T18:40:00+00:00")
        for hub in featuredTournaments where hub.isBeingPlayed(asOf: now) {
            XCTAssertNotNil(
                hub.liveThrough,
                "\(hub.slug) reports as being played with no window saying until when"
            )
        }
        XCTAssertFalse(
            featuredTournaments.first(where: { $0.slug == "us-open" })?
                .isBeingPlayed(asOf: now) ?? false,
            "the US Open still reports as being played three days after Zverev won it"
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
