import XCTest
@testable import Bain_Luck

/// #6444 — A TOURNAMENT THAT FINISHED ON 13 SEPTEMBER STILL LED THE BROWSE TAB.
///
/// Alex, on the phone on 16 September: "Stale US Open leads." #6600 had already
/// fixed the LINE under that card — it reads "Results and title odds" now, which
/// was the outright lie — but the card itself was still the first thing in the
/// tab, above every destination that is worth reaching in an ordinary week. A
/// card can be honest and still be in the wrong place: leading the tab is itself
/// a claim that this is the thing to look at today.
///
/// `browseFeaturedHubs(in:asOf:)` is what `featuredGrid` orders on. Two rules,
/// and the second is the one worth the tests:
///
///   1. A hub LEADS only while its edition is being played.
///   2. A hub is NEVER DROPPED. The trailing arm exists for exactly this reason:
///      the hub keeps the results and the title odds and is worth reaching all
///      year, so the repair for "it is too high" must not be "it is gone". Every
///      test below that checks placement also checks the total, because an
///      ordering rule that quietly withholds passes every assertion about where
///      things are.
///
/// The clock rule itself is native's `isBeingPlayed(asOf:)` and is not
/// re-implemented here (notice 46 pair, `FeaturedTournamentSubtitleTests` proves
/// the rule). What these tests own is the ordering built on top of it.
///
/// Every test fixes its own clock. The default is `Date()`, so an assertion that
/// did not pass one would pass today and start failing on its own the next time
/// a tournament is on (gotcha #44).
final class BrowseFeaturedHubOrder6444Tests: XCTestCase {

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

    /// A second dated hub, played in a different week, so "leading" and
    /// "trailing" can both be non-empty in one call — the state the shipping
    /// catalog of one entry cannot produce.
    private let masters2027 = FeaturedTournament(
        slug: "masters",
        title: "The Masters",
        liveSubtitle: "Live rounds and leaderboard",
        restingSubtitle: "Results and winner odds",
        liveThrough: "2027-04-12T04:00:00+00:00",
        icon: "figure.golf"
    )

    private let undated = FeaturedTournament(
        slug: "the-open",
        title: "The Open Championship",
        liveSubtitle: "Live rounds and leaderboard",
        restingSubtitle: "Results and winner odds",
        icon: "figure.golf"
    )

    // MARK: - Nothing is ever dropped

    /// The load-bearing one. Whatever the clock, the two arms together are the
    /// catalog — same hubs, same count, none twice.
    ///
    /// Without this, `leading: catalog.filter(isBeingPlayed)` with a `trailing`
    /// of `[]` passes every placement test in this file while deleting the US
    /// Open from Browse for 50 weeks of the year.
    func testEveryHubLandsInExactlyOneArmAtEveryClock() {
        let catalog = [usOpen2026, masters2027, undated]
        let clocks = [
            "2026-09-05T18:00:00+00:00",   // the US Open is on
            "2026-09-14T06:00:00+00:00",   // its inclusive last instant
            "2026-09-16T18:40:00+00:00",   // the day Alex shot the defect
            "2027-04-10T18:00:00+00:00",   // the Masters is on instead
            "2027-08-01T12:00:00+00:00",   // neither is on
            "2020-01-01T00:00:00+00:00",   // before either edition existed
        ]
        for clock in clocks {
            let hubs = browseFeaturedHubs(in: catalog, asOf: at(clock))
            let placed = hubs.leading.map(\.slug) + hubs.trailing.map(\.slug)
            XCTAssertEqual(
                placed.sorted(),
                catalog.map(\.slug).sorted(),
                "at \(clock) the grid draws a different set of hubs than the catalog holds"
            )
            XCTAssertEqual(
                Set(placed).count, placed.count,
                "at \(clock) a hub is drawn twice"
            )
        }
    }

    // MARK: - The two placements

    func testTheDayTHISWASSHOTTheFinishedHubDoesNotLead() {
        // The specimen. 2026-09-16, three days past Zverev's title.
        let hubs = browseFeaturedHubs(in: [usOpen2026], asOf: at("2026-09-16T18:40:00+00:00"))
        XCTAssertEqual(hubs.leading.map(\.slug), [], "the US Open still heads the Browse tab")
        XCTAssertEqual(hubs.trailing.map(\.slug), ["us-open"], "and it is still offered, lower down")
    }

    func testAMatchdayInsideTheEditionLeads() {
        // The window is a window, not a permanent demotion: during the
        // tournament, the hub is exactly what a person opening Browse wants.
        let hubs = browseFeaturedHubs(in: [usOpen2026], asOf: at("2026-09-05T18:00:00+00:00"))
        XCTAssertEqual(hubs.leading.map(\.slug), ["us-open"])
        XCTAssertEqual(hubs.trailing.map(\.slug), [])
    }

    func testTwoHubsSplitByTheSameClock() {
        // Both arms non-empty in one call — the arrangement that proves the
        // partition is a partition and not a switch between two whole-list
        // answers.
        let catalog = [usOpen2026, masters2027]
        let duringTheMasters = browseFeaturedHubs(in: catalog, asOf: at("2027-04-10T18:00:00+00:00"))
        XCTAssertEqual(duringTheMasters.leading.map(\.slug), ["masters"])
        XCTAssertEqual(duringTheMasters.trailing.map(\.slug), ["us-open"])
    }

    // MARK: - The boundary is the SAME boundary

    func testTheLastInstantOfTheWindowStillLeadsAndOneSecondLaterDoesNot() {
        // Read off the ordering rather than the rule, so a future ordering that
        // grows its own `now <` comparison fails here as well as in
        // `FeaturedTournamentSubtitleTests`.
        XCTAssertEqual(
            browseFeaturedHubs(in: [usOpen2026], asOf: at("2026-09-14T06:00:00+00:00")).leading.map(\.slug),
            ["us-open"]
        )
        XCTAssertEqual(
            browseFeaturedHubs(in: [usOpen2026], asOf: at("2026-09-14T06:00:01+00:00")).leading.map(\.slug),
            []
        )
    }

    // MARK: - Catalog order survives inside each arm

    func testCatalogOrderIsPreservedWithinAnArm() {
        // The hand-maintained list is the editorial order, and the clock is only
        // allowed to move a hub between the two arms — not to reshuffle the
        // hubs that stay together.
        let a = FeaturedTournament(slug: "a", title: "A", liveSubtitle: "Live A",
                                   restingSubtitle: "Results A", icon: "a")
        let b = FeaturedTournament(slug: "b", title: "B", liveSubtitle: "Live B",
                                   restingSubtitle: "Results B", icon: "b")
        let c = FeaturedTournament(slug: "c", title: "C", liveSubtitle: "Live C",
                                   restingSubtitle: "Results C", icon: "c")
        let hubs = browseFeaturedHubs(in: [a, b, c], asOf: at("2026-09-16T18:40:00+00:00"))
        XCTAssertEqual(hubs.trailing.map(\.slug), ["a", "b", "c"])
    }

    // MARK: - The understating inputs land in the safe arm

    /// `isBeingPlayed` fails to `false` on an absent, unparsable or un-bumped
    /// date. For the ordering that is the safe direction, and this test says so
    /// out loud rather than leaving it inherited: the consequence is that an
    /// UNDATED HUB CAN NEVER LEAD, including a genuinely live one nobody dated.
    ///
    /// That is the trade taken, deliberately. A hub wrongly called finished sits
    /// lower and keeps its results; a hub wrongly called live leads the tab three
    /// days after its final, which is the defect being repaired. If "leads" ever
    /// needs to be a weaker claim than "dated and in window", it changes HERE and
    /// not in the clock rule.
    func testAnUndatedOrUnparsableHubNeverLeads() {
        let typo = FeaturedTournament(
            slug: "typo",
            title: "Typo Open",
            liveSubtitle: "Live rounds and leaderboard",
            restingSubtitle: "Results and winner odds",
            liveThrough: "the fourteenth of September",
            icon: "figure.golf"
        )
        for hub in [undated, typo] {
            let hubs = browseFeaturedHubs(in: [hub], asOf: at("2026-07-16T12:00:00+00:00"))
            XCTAssertEqual(hubs.leading.map(\.slug), [], "\(hub.slug) leads on a date nobody can check")
            XCTAssertEqual(hubs.trailing.map(\.slug), [hub.slug], "\(hub.slug) was dropped instead of demoted")
        }
    }

    // MARK: - The clock it is given, and no other

    /// The partition reads the `now` it is handed and never asks for one of its
    /// own. Two consequences, both wanted:
    ///
    ///   * `featuredGrid` takes ONE `Date()` for the whole grid, so a hub cannot
    ///     lead by one clock and print its resting line by another that arrived a
    ///     microsecond later across the boundary.
    ///   * the grid does not reshuffle under the reader's thumb when a final
    ///     ends — `now` is read when the view body runs and is not observed. That
    ///     is the right behaviour for a day-scale line on a static list, but it is
    ///     inherited from SwiftUI rather than chosen, so it is asserted here.
    ///
    /// A `filter { $0.isBeingPlayed() }` that dropped the argument would pass
    /// today and fail this the moment a tournament is on; passing a clock from
    /// the tournament fortnight makes that mutant fail at any wall clock.
    func testThePartitionReadsTheClockItIsGivenAndNoOther() {
        let catalog = [usOpen2026]
        let during = browseFeaturedHubs(in: catalog, asOf: at("2026-09-05T18:00:00+00:00"))
        let after = browseFeaturedHubs(in: catalog, asOf: at("2026-09-16T18:40:00+00:00"))
        XCTAssertEqual(during.leading.map(\.slug), ["us-open"])
        XCTAssertEqual(after.leading.map(\.slug), [])

        // Same clock twice is the same answer — nothing in here is stateful.
        let repeated = browseFeaturedHubs(in: catalog, asOf: at("2026-09-05T18:00:00+00:00"))
        XCTAssertEqual(repeated.leading.map(\.slug), during.leading.map(\.slug))
    }

    // MARK: - The shipping catalog, not a fixture

    /// Reads the list Browse actually draws. A fix that lands only in this
    /// file's own fixtures changes no pixel.
    func testTheShippedCatalogPutsTheUSOpenBelowTheEvergreenCardsToday() {
        let hubs = browseFeaturedHubs(asOf: at("2026-09-16T18:40:00+00:00"))
        XCTAssertFalse(
            hubs.leading.contains(where: { $0.slug == "us-open" }),
            "the shipped US Open still leads Browse three days after Zverev won it"
        )
        XCTAssertTrue(
            hubs.trailing.contains(where: { $0.slug == "us-open" }),
            "the shipped US Open is not drawn at all — demoted into nowhere"
        )
        XCTAssertEqual(
            hubs.leading.count + hubs.trailing.count,
            featuredTournaments.count,
            "Browse draws a different number of hubs than the catalog holds"
        )
    }

    /// And the same shipped entry led during its own fortnight, so this is a
    /// window and not a permanent burial of the tennis hub.
    func testTheShippedUSOpenDidLeadDuringItsOwnFortnight() {
        let hubs = browseFeaturedHubs(asOf: at("2026-09-05T18:00:00+00:00"))
        XCTAssertTrue(hubs.leading.contains(where: { $0.slug == "us-open" }))
    }
}
