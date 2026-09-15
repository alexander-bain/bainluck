import XCTest
@testable import Bain_Luck

/// #6286 — the championship grid's rank numbers shuffled between app launches.
///
/// Seen on production, build 1.0 (10), iPhone 17 simulator: two cold launches of the
/// MLB grid one minute apart, reading one cached `/api/playoffs/mlb` body, drew
/// **rank 17 as Seattle Mariners and then as Pittsburgh Pirates** (and rank 18 as the
/// Angels, then the Giants). Ranks 1–16 were identical in both — the teams above the
/// tie block have distinct probabilities.
///
/// **What these tests are worth, MEASURED and not assumed.** Restoring the pre-fix
/// comparator (`return pa > pb`, no tiebreak) fails four of the ten below — and
/// `testTiedTeamsTakeTheOrderTheServerPublished`, the one whose NAME sounds like the
/// guard, is not among them. It survives, because the fixture feeds the sort the
/// server's own order and Swift's `sort` happens to preserve the input order of equal
/// elements at this size. A test can assert the exact right thing and still be blind;
/// that one is a readable statement of the contract, not a sensor.
///
/// The sensors are `testAnyInputPermutationRanksTheSame` and
/// `testTheGroupedAndUngroupedGridsRankIdentically`, both of which vary the INPUT
/// ORDER — which is the actual defect, since `groupedTeams.values` handed the sort a
/// different sequence on every launch — plus
/// `testTheUnfilteredListIsTheServersPublishedSequence`, which kills the
/// `grouped.values.flatMap` source of that sequence outright.
///
/// The per-process randomness itself is deliberately NOT asserted directly: one test
/// process has one hash seed, so a "does the order change between calls" test could
/// only ever pass. It is closed in two ways that a test CAN see — the unfiltered list
/// stops being assembled from a dictionary at all, and the comparator becomes a total
/// order, after which the output cannot depend on the input sequence even if it were.
final class GridLadderRankIsStable6286Tests: XCTestCase {

    // MARK: - Fixture
    //
    // The shape is the real one, taken from the 2026-09-14 MLB payload: a handful of
    // distinct leaders, then a block of clubs at EXACTLY the same probability. The
    // conferences are interleaved on purpose — if ties fell back to conference
    // grouping, "American League first" would pass a fixture where all the tied teams
    // shared a conference, and say nothing.

    private static let columns: [GridColumn] = [
        GridColumn(key: "make_playoffs", label: "Make Playoffs", order: 1, sequential: true, marketId: nil),
        GridColumn(key: "championship", label: "World Series", order: 4, sequential: true, marketId: nil),
    ]

    private static func team(_ name: String, _ conference: String, _ championship: Double?) -> GridTeam {
        var cells: [String: GridCell] = [:]
        if let championship {
            cells["championship"] = GridCell(mergedProbability: championship, sources: nil, trend24H: nil)
        }
        return GridTeam(
            name: name,
            shortName: nil,
            teamId: nil,
            logoUrl: nil,
            primaryColor: nil,
            secondaryColor: nil,
            record: nil,
            conference: conference,
            division: nil,
            region: nil,
            seed: nil,
            cells: cells
        )
    }

    /// The order the API published, ties included.
    private static let serverTeams: [GridTeam] = [
        team("Dodgers", "National League", 0.3005),
        team("Brewers", "National League", 0.1565),
        team("Yankees", "American League", 0.0981),
        team("Orioles", "American League", 0.0015),
        // The tie block: one number, six clubs, both conferences.
        team("Pirates", "National League", 0.001),
        team("Mariners", "American League", 0.001),
        team("Angels", "American League", 0.001),
        team("Giants", "National League", 0.001),
        team("Tigers", "American League", 0.001),
        team("Twins", "American League", 0.001),
        // Below the tie block, and a club the grid carries no number for at all.
        team("Marlins", "National League", 0.0005),
        team("Rays", "American League", nil),
    ]

    private static func grid(grouped: Bool) -> ChampionshipGridResponse {
        var groupedTeams: [String: [GridTeam]]?
        if grouped {
            groupedTeams = Dictionary(grouping: serverTeams, by: { $0.conference ?? "Other" })
        }
        return ChampionshipGridResponse(
            league: "mlb",
            name: "MLB Playoffs 2026",
            season: "2026",
            columns: columns,
            teams: serverTeams,
            groupedTeams: groupedTeams,
            movers: [],
            teamCount: serverTeams.count,
            lastUpdated: nil,
            sourcesAvailable: [],
            championshipMarketId: nil
        )
    }

    private func rank(_ teams: [GridTeam]) -> [String] { teams.map(\.name) }

    // MARK: - The defect

    /// THE ONE THAT FAILS ON THE OLD CODE. Six clubs at exactly `0.001` come out in the
    /// order the server published them, not in whatever order they reached the sort.
    func testTiedTeamsTakeTheOrderTheServerPublished() {
        let ranked = GridLadderOrder.ranked(
            Self.serverTeams,
            serverTeams: Self.serverTeams,
            columns: Self.columns
        )
        XCTAssertEqual(
            rank(ranked),
            ["Dodgers", "Brewers", "Yankees", "Orioles",
             "Pirates", "Mariners", "Angels", "Giants", "Tigers", "Twins",
             "Marlins", "Rays"],
            "the tie block must hold the server's published order"
        )
    }

    /// The property that closes the Dictionary half: the ranking is a function of the
    /// SET of teams, not of the order they arrive in. A shuffled input — which is what
    /// `groupedTeams.values.flatMap` produced on every launch — ranks identically.
    func testAnyInputPermutationRanksTheSame() {
        let expected = rank(GridLadderOrder.ranked(
            Self.serverTeams, serverTeams: Self.serverTeams, columns: Self.columns
        ))
        // Seeded, so a failure reproduces on the same permutation rather than
        // becoming "it went red once on CI".
        var generator = SeededGenerator(seed: 0x6286)
        for attempt in 0..<50 {
            let shuffled = Self.serverTeams.shuffled(using: &generator)
            let ranked = GridLadderOrder.ranked(
                shuffled, serverTeams: Self.serverTeams, columns: Self.columns
            )
            XCTAssertEqual(rank(ranked), expected, "permutation \(attempt) ranked differently")
        }
    }

    /// The reader-visible consequence, stated in the reader's terms: the rank a team
    /// holds on the unfiltered grid does not depend on how the payload was grouped.
    func testTheGroupedAndUngroupedGridsRankIdentically() {
        let grouped = GridLadderOrder.ranked(
            GridLadderOrder.visibleTeams(in: Self.grid(grouped: true), conferenceFilter: nil),
            serverTeams: Self.serverTeams,
            columns: Self.columns
        )
        let flat = GridLadderOrder.ranked(
            GridLadderOrder.visibleTeams(in: Self.grid(grouped: false), conferenceFilter: nil),
            serverTeams: Self.serverTeams,
            columns: Self.columns
        )
        XCTAssertEqual(rank(grouped), rank(flat))
        XCTAssertEqual(rank(grouped).count, Self.serverTeams.count, "a team was lost or duplicated")
    }

    // MARK: - The order itself is still the right one

    /// The tiebreak must not have quietly become the sort. Probability still decides
    /// wherever probability can.
    func testProbabilityStillOutranksThePublishedPosition() {
        // Publish the field in the exact reverse of its probability order.
        let reversed = Array(Self.serverTeams.reversed())
        let ranked = GridLadderOrder.ranked(
            Self.serverTeams, serverTeams: reversed, columns: Self.columns
        )
        XCTAssertEqual(Array(rank(ranked).prefix(3)), ["Dodgers", "Brewers", "Yankees"])
        // ...and the tie block now follows the reversed publication.
        XCTAssertEqual(
            Array(rank(ranked).dropFirst(4).prefix(6)),
            ["Twins", "Tigers", "Giants", "Angels", "Mariners", "Pirates"]
        )
    }

    /// A club with no championship cell sinks below one carrying a real zero — "we hold
    /// no number for them" is not the same claim as "their chance is nil".
    func testATeamWithNoCellSinksBelowARealZero() {
        let withZero = Self.team("Rockies", "National League", 0.0)
        let noCell = Self.team("Rays", "American League", nil)
        let ranked = GridLadderOrder.ranked(
            [noCell, withZero], serverTeams: [noCell, withZero], columns: Self.columns
        )
        XCTAssertEqual(rank(ranked), ["Rockies", "Rays"])
    }

    /// A team the server never listed is ordered last rather than sharing the leader's
    /// position — `?? Int.max`, not `?? 0`.
    func testATeamMissingFromThePublishedListSortsLastWithinItsTie() {
        let ghost = Self.team("Ghost", "American League", 0.001)
        let ranked = GridLadderOrder.ranked(
            [ghost] + Self.serverTeams,
            serverTeams: Self.serverTeams,
            columns: Self.columns
        )
        let tieBlock = Array(rank(ranked).dropFirst(4).prefix(7))
        XCTAssertEqual(
            tieBlock,
            ["Pirates", "Mariners", "Angels", "Giants", "Tigers", "Twins", "Ghost"]
        )
    }

    // MARK: - The filters, which were never the broken half

    /// The unfiltered list is the server's published sequence, not a re-assembly of
    /// the conference buckets. This is the test that kills `grouped.values.flatMap`
    /// deterministically: a grouped union is conference-BLOCKED however its keys are
    /// walked, and the server interleaves, so the two can never coincide.
    func testTheUnfilteredListIsTheServersPublishedSequence() {
        XCTAssertEqual(
            GridLadderOrder.visibleTeams(in: Self.grid(grouped: true), conferenceFilter: nil).map(\.name),
            Self.serverTeams.map(\.name)
        )
    }

    /// ...and a payload that sends groups with no flat list still renders every team,
    /// in an order that is fixed rather than a per-launch coin flip.
    func testAGroupsOnlyPayloadStillYieldsEveryTeamInAFixedOrder() {
        let grouped = Dictionary(grouping: Self.serverTeams, by: { $0.conference ?? "Other" })
        let gridWithNoFlatList = ChampionshipGridResponse(
            league: "mlb", name: "MLB Playoffs 2026", season: "2026",
            columns: Self.columns, teams: [], groupedTeams: grouped,
            movers: [], teamCount: Self.serverTeams.count, lastUpdated: nil,
            sourcesAvailable: [], championshipMarketId: nil
        )
        let visible = GridLadderOrder.visibleTeams(in: gridWithNoFlatList, conferenceFilter: nil)
        XCTAssertEqual(Set(visible.map(\.name)), Set(Self.serverTeams.map(\.name)))
        XCTAssertEqual(visible.count, Self.serverTeams.count, "a team was lost or duplicated")
        XCTAssertEqual(
            visible.map(\.name),
            (grouped["American League"] ?? []).map(\.name) + (grouped["National League"] ?? []).map(\.name),
            "the fallback must walk the conference keys in sorted order"
        )
    }

    func testAConferenceFilterServesOnlyThatConference() {
        let al = GridLadderOrder.visibleTeams(
            in: Self.grid(grouped: true), conferenceFilter: "American League"
        )
        XCTAssertFalse(al.isEmpty)
        XCTAssertTrue(al.allSatisfy { $0.conference == "American League" })
        XCTAssertEqual(al.count, Self.serverTeams.filter { $0.conference == "American League" }.count)
    }

    /// Switching filters must not move a team relative to the others it is still shown
    /// beside — the filtered ladder is the unfiltered one with rows removed.
    func testTheFilteredLadderIsTheUnfilteredOneWithRowsRemoved() {
        let grid = Self.grid(grouped: true)
        let all = GridLadderOrder.ranked(
            GridLadderOrder.visibleTeams(in: grid, conferenceFilter: nil),
            serverTeams: grid.teams, columns: Self.columns
        )
        for conference in ["American League", "National League"] {
            let filtered = GridLadderOrder.ranked(
                GridLadderOrder.visibleTeams(in: grid, conferenceFilter: conference),
                serverTeams: grid.teams, columns: Self.columns
            )
            XCTAssertEqual(
                rank(filtered),
                rank(all).filter { name in
                    Self.serverTeams.first { $0.name == name }?.conference == conference
                },
                "\(conference) reordered teams that did not move"
            )
        }
    }

    /// The column with the highest `order` is the championship one, whatever order the
    /// columns arrive in.
    func testTheChampionshipColumnIsTheWidestNetOne() {
        XCTAssertEqual(GridLadderOrder.championshipColumnKey(Self.columns), "championship")
        XCTAssertEqual(GridLadderOrder.championshipColumnKey(Self.columns.reversed()), "championship")
        XCTAssertNil(GridLadderOrder.championshipColumnKey([]))
    }

    /// An empty grid ranks to empty rather than trapping.
    func testAnEmptyGridIsEmptyAndNotACrash() {
        XCTAssertTrue(GridLadderOrder.ranked([], serverTeams: [], columns: Self.columns).isEmpty)
        XCTAssertTrue(GridLadderOrder.ranked([], serverTeams: [], columns: []).isEmpty)
    }
}

/// A reproducible shuffle. `SystemRandomNumberGenerator` would make a failure in
/// `testAnyInputPermutationRanksTheSame` unreproducible, which for a test about
/// nondeterminism would be its own joke.
private struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) { self.state = seed &+ 0x9E37_79B9_7F4A_7C15 }

    mutating func next() -> UInt64 {
        state = state &+ 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
}
