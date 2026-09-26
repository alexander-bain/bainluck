import XCTest
@testable import Bain_Luck

/// #8684 — a game page's AWARDS list puts each player under their own team.
///
/// `awardsByPlayer` split home from away with
/// `outcomeName.localizedCaseInsensitiveContains(TeamShortName.short(homeTeam))`.
/// An award's outcome is a PLAYER's name, which never contains "Giants", so on
/// 15318410 (LAD @ SF) every Giants player was drawn under the one
/// "Los Angeles Dodgers" header and no Giants header appeared. The server had
/// already filed each award under its side — the fix reads that list.
///
/// The fixtures are production's own rows from 15318410's `/related-futures`
/// (2026-09-26): no player name contains either team.
final class AwardsGroupedBySide8684Tests: XCTestCase {

    private func future(_ outcomeId: Int, _ player: String, _ market: String, _ prob: Double) -> RelatedFuture {
        let json = """
        {"market_id": \(outcomeId * 10), "market_name": "\(market)", "outcome_id": \(outcomeId),
         "outcome_name": "\(player)", "probability": \(prob), "display_category": "awards"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(RelatedFuture.self, from: Data(json.utf8))
    }

    private lazy var dodgers: [RelatedFuture] = [
        future(1, "Tanner Scott", "NL Reliever of the Year Winner?", 0.03),
        future(2, "Edwin Díaz", "NL Reliever of the Year Winner?", 0.01),
        future(3, "Shohei Ohtani", "MLB: 2026 NL Hank Aaron Winner", 0.021),
    ]
    private lazy var giants: [RelatedFuture] = [
        future(4, "Ryan Walker", "NL Reliever of the Year Winner?", 0.05),
        future(5, "Luis Arraez", "MLB: 2026 NL Hank Aaron Winner", 0.0015),
    ]

    func testEachPlayerSitsUnderTheSideTheServerFiledHimOn() {
        let sides = relatedFutureSides(away: dodgers, home: giants)
        let groups = awardPlayerGroups(dodgers + giants, sides: sides)

        XCTAssertEqual(groups.away.map(\.name), ["Tanner Scott", "Shohei Ohtani", "Edwin Díaz"])
        XCTAssertEqual(groups.home.map(\.name), ["Ryan Walker", "Luis Arraez"],
                       "the Giants header must exist and hold the Giants — the name test put them under the Dodgers")
    }

    func testAPlayersSideDoesNotDependOnHisNameContainingATeam() {
        // Strawman of the old rule: a name test on "Giants" finds no Giants player.
        XCTAssertFalse(giants.contains { $0.outcomeName.localizedCaseInsensitiveContains("Giants") })

        let sides = relatedFutureSides(away: dodgers, home: giants)
        for g in giants { XCTAssertEqual(sides[g.outcomeId], .home, g.outcomeName) }
        for d in dodgers { XCTAssertEqual(sides[d.outcomeId], .away, d.outcomeName) }
    }

    func testAPlayersAwardsShareOneRowStrongestFirst() {
        let giantsTwoAwards = giants + [future(6, "Ryan Walker", "NL Cy Young Winner", 0.20)]
        let sides = relatedFutureSides(away: dodgers, home: giantsTwoAwards)
        let groups = awardPlayerGroups(dodgers + giantsTwoAwards, sides: sides)

        XCTAssertEqual(groups.home.map(\.name), ["Ryan Walker", "Luis Arraez"])
        XCTAssertEqual(groups.home.first?.awards.map(\.prob), [0.20, 0.05])
    }

    func testAnOutcomeFiledOnBothSidesIsDrawnOnceUnderAway() {
        let shared = future(7, "Mookie Betts", "MLB: 2026 NL Hank Aaron Winner", 0.04)
        let sides = relatedFutureSides(away: dodgers + [shared], home: giants + [shared])
        let groups = awardPlayerGroups(dodgers + [shared] + giants + [shared], sides: sides)

        XCTAssertEqual(groups.away.filter { $0.name == "Mookie Betts" }.first?.awards.count, 1)
        XCTAssertFalse(groups.home.contains { $0.name == "Mookie Betts" })
    }
}
