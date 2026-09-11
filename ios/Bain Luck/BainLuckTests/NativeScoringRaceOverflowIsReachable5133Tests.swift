import XCTest

@testable import Bain_Luck

/// #5133, CERT-2620's required repair `5133-NATIVE-SCORING-RACE-OVERFLOW-IS-REACHABLE`.
///
/// CERT-2617 granted the scoring-race exemption a token and a second opinion
/// took it back for a reason the first grade could not see: getting a market
/// PAST the hero filter is not the same as getting it in front of a reader.
/// `SpecialEventMarketsView` rendered `cat.items.prefix(5)` and then an inert
/// `Text("+N more")` — no tap target, no disclosure, nothing. Everything past
/// the fifth card in a category was unreachable.
///
/// MEASURED, and worse than the block said. The whole `other[]` array of
/// production event 14780145 (New Orleans @ Detroit), read 2026-09-11, with the
/// six scoring races moved into it exactly as the backend half of #5133 moves
/// them, groups into ELEVEN `Other Markets` cards:
///
///      1. D/ST Touchdown                6. Race to 14 Points   <- cap
///      2. 1st Detroit Touchdown         7. Race to 10 Points
///      3. 1st New Orleans Touchdown     8. Race to 21 Points
///      4. 1st Touchdown                 9. Race to 28 Points
///      5. 1st Half / Fulltime Result   10. Race to 7 Points
///                                      11. Race to 35 Points
///
/// The cap falls between card 5 and card 6, so **all six races were hidden** —
/// not just the two-row one CERT-2620 named. The ship moved them out of Player
/// Props, where they were wrong, into a place no reader could open. That is the
/// whole ship, silently zero.
///
/// The fixture below is that payload verbatim: every row of `other[]` in wire
/// order, then every race row in wire order, market names, outcome names and
/// prices untouched. (By this read the game had settled and the race prices had
/// gone to `nil`; the morning's live 0.56/0.44 on `Race to 7 Points` is the
/// fixture in `AScoringRaceStaysVisible5133Tests`, and the last test here puts
/// it back to prove the two halves of the repair compose.)
final class NativeScoringRaceOverflowIsReachable5133Tests: XCTestCase {

    private static let race7 = "New Orleans vs Detroit: Race to 7 Points"
    private static let otherMarkets = "Other Markets"

    private func row(_ market: String, _ outcome: String, _ p: Double?) -> GameMarketOther {
        GameMarketOther(marketName: market, outcomeName: outcome, probability: p, source: "kalshi")
    }

    /// `GET /api/events/14780145/game-markets`, 2026-09-11 — `other[]` verbatim,
    /// then the six race families verbatim, in wire order.
    private var wire: [GameMarketOther] {
        [
        // 86 rows
        row("New Orleans vs Detroit: 2nd Quarter Both Teams to Score", "Yes", 0.28),
        row("New Orleans vs Detroit: 3rd Quarter Both Teams to Score", "Yes", 0.24),
        row("New Orleans vs Detroit: D/ST Touchdown", "Yes", 0.235),
        row("New Orleans vs Detroit: Both Teams to Score in Every Quarter", "Yes", 0.22),
        row("New Orleans vs Detroit", "Detroit", 0.745),
        row("New Orleans vs Detroit", "New Orleans", 0.255),
        row("Saints vs. Lions", "No", 0.745),
        row("Saints vs. Lions", "Yes", 0.255),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Jahmyr Gibbs", 0.31),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Isaac TeSlaa", 0.295),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Jacob Saylors", 0.295),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Sione Vaki", 0.295),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "DET Lions D/ST", 0.275),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Brock Wright", 0.23),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Amon-Ra St. Brown", 0.17),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Sam LaPorta", 0.14),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Jameson Williams", 0.135),
        row("New Orleans vs Detroit: 1st Detroit Touchdown", "Jared Goff", 0.03),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Devaughn Vele", 0.295),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Kendre Miller", 0.295),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Noah Fant", 0.28),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Barion Brown", 0.28),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Travis Etienne Jr.", 0.225),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "NO Saints D/ST", 0.185),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Chris Olave", 0.175),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Juwan Johnson", 0.14),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Tyler Shough", 0.125),
        row("New Orleans vs Detroit: 1st New Orleans Touchdown", "Bryce Lance", 0.055),
        row("New Orleans vs Detroit: 4th Quarter Both Teams to Score", "Yes", 0.61),
        row("New Orleans vs Detroit: 1st Quarter Both Teams to Score", "Yes", 0.85),
        row("New Orleans vs Detroit: First Team to Score a TD", "Detroit scores first TD", 0.505),
        row("New Orleans vs Detroit: First Team to Score a TD", "New Orleans scores first TD", 0.36),
        row("New Orleans vs Detroit: First Team to Score a TD", "No team scores a TD", 0.01),
        row("New Orleans vs Detroit: 1st Touchdown", "DET Lions D/ST", 0.35),
        row("New Orleans vs Detroit: 1st Touchdown", "Jahmyr Gibbs", 0.215),
        row("New Orleans vs Detroit: 1st Touchdown", "Amon-Ra St. Brown", 0.105),
        row("New Orleans vs Detroit: 1st Touchdown", "Travis Etienne Jr.", 0.1),
        row("New Orleans vs Detroit: 1st Touchdown", "Sam LaPorta", 0.065),
        row("New Orleans vs Detroit: 1st Touchdown", "Juwan Johnson", 0.06),
        row("New Orleans vs Detroit: 1st Touchdown", "Sione Vaki", 0.05),
        row("New Orleans vs Detroit: 1st Touchdown", "Jacob Saylors", 0.05),
        row("New Orleans vs Detroit: 1st Touchdown", "Jameson Williams", 0.045),
        row("New Orleans vs Detroit: 1st Touchdown", "Chris Olave", 0.045),
        row("New Orleans vs Detroit: 1st Touchdown", "Isaac TeSlaa", 0.045),
        row("New Orleans vs Detroit: 1st Touchdown", "Devaughn Vele", 0.04),
        row("New Orleans vs Detroit: 1st Touchdown", "Kendre Miller", 0.03),
        row("New Orleans vs Detroit: 1st Touchdown", "Tyler Shough", 0.03),
        row("New Orleans vs Detroit: 1st Touchdown", "NO Saints D/ST", 0.03),
        row("New Orleans vs Detroit: 1st Touchdown", "Audric Estime", 0.025),
        row("New Orleans vs Detroit: 1st Touchdown", "Jared Goff", 0.02),
        row("New Orleans vs Detroit: 1st Touchdown", "Barion Brown", 0.02),
        row("New Orleans vs Detroit: 1st Touchdown", "Brock Wright", 0.015),
        row("New Orleans vs Detroit: 1st Touchdown", "Bryce Lance", 0.015),
        row("New Orleans vs Detroit: 1st Touchdown", "Noah Fant", 0.015),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "Detroit wins 1H / Detroit wins game", 0.55),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "New Orleans wins 1H / New Orleans wins game", 0.2),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "New Orleans wins 1H / Detroit wins game", 0.16),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "Detroit wins 1H / New Orleans wins game", 0.09),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "Tie 1H / New Orleans wins game", 0.07),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "Tie 1H / Detroit wins game", 0.065),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "Tie 1H / Game ends in a tie", 0.01),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "New Orleans wins 1H / Game ends in a tie", 0.01),
        row("New Orleans vs Detroit: 1st Half / Fulltime Result", "Detroit wins 1H / Game ends in a tie", 0.01),
        row("Saints vs. Lions - Player Props", "Spread -6.5", 0.535),
        row("New Orleans vs Detroit: Both Teams to Score", "14+ points", 0.785),
        row("New Orleans vs Detroit: Both Teams to Score", "21+ points", 0.415),
        row("New Orleans vs Detroit: Both Teams to Score", "28+ points", 0.145),
        row("New Orleans vs Detroit: Both Teams to Score", "35+ points", 0.045),
        row("Saints vs. Lions - Player Props", "O/U 49.5", 0.505),
        row("New Orleans vs Detroit: Race to 14 Points", "Detroit reaches 14 points first", nil),
        row("New Orleans vs Detroit: Race to 14 Points", "New Orleans reaches 14 points first", nil),
        row("New Orleans vs Detroit: Race to 14 Points", "Neither team reaches 14 points", nil),
        row("New Orleans vs Detroit: Race to 10 Points", "Detroit reaches 10 points first", nil),
        row("New Orleans vs Detroit: Race to 10 Points", "New Orleans reaches 10 points first", nil),
        row("New Orleans vs Detroit: Race to 10 Points", "Neither team reaches 10 points", nil),
        row("New Orleans vs Detroit: Race to 21 Points", "New Orleans reaches 21 points first", nil),
        row("New Orleans vs Detroit: Race to 21 Points", "Detroit reaches 21 points first", nil),
        row("New Orleans vs Detroit: Race to 21 Points", "Neither team reaches 21 points", nil),
        row("New Orleans vs Detroit: Race to 28 Points", "Detroit reaches 28 points first", nil),
        row("New Orleans vs Detroit: Race to 28 Points", "Neither team reaches 28 points", nil),
        row("New Orleans vs Detroit: Race to 28 Points", "New Orleans reaches 28 points first", nil),
        row("New Orleans vs Detroit: Race to 7 Points", "Detroit reaches 7 points first", nil),
        row("New Orleans vs Detroit: Race to 7 Points", "New Orleans reaches 7 points first", nil),
        row("New Orleans vs Detroit: Race to 35 Points", "Neither team reaches 35 points", nil),
        row("New Orleans vs Detroit: Race to 35 Points", "Detroit reaches 35 points first", nil),
        row("New Orleans vs Detroit: Race to 35 Points", "New Orleans reaches 35 points first", nil),
        ]
    }

    private func otherMarketsCategory(
        _ rows: [GameMarketOther]
    ) throws -> SpecialEventMarketsView.MarketCategory {
        let view = SpecialEventMarketsView(markets: rows, eventStatus: nil)
        let cat = view.categories.first { $0.title == Self.otherMarkets }
        return try XCTUnwrap(cat, "the payload produced no \(Self.otherMarkets) category at all")
    }

    // MARK: - The measurement this repair exists for

    /// The fixture reproduces the shape the block measured. If this fails,
    /// nothing below it means what it says — the specimen has moved and the
    /// numbers in the doc comment need re-reading off the wire, not adjusting
    /// until they pass.
    func testTheFixtureIsStillTheElevenCardSpecimen() throws {
        let cat = try otherMarketsCategory(wire)

        XCTAssertEqual(cat.items.count, 11)
        XCTAssertEqual(cat.items.map(\.name).firstIndex(of: Self.race7), 9)
    }

    // MARK: - The defect, and the repair

    /// THE BLOCK, held as a test. Card 10 of 11 is past a cap of 5.
    func testRaceTo7IsPastTheFiveCardCategoryCap() throws {
        let cat = try otherMarketsCategory(wire)

        let collapsed = SpecialEventMarketsView.displayedItems(cat.items, expanded: false)

        XCTAssertEqual(collapsed.count, SpecialEventMarketsView.itemDisplayCap)
        XCTAssertFalse(collapsed.map(\.name).contains(Self.race7))
    }

    /// THE REPAIR. The named guard: the measured card is actually displayable.
    func testRaceTo7IsReachablePastFiveCardCategoryCap() throws {
        let cat = try otherMarketsCategory(wire)

        let expanded = SpecialEventMarketsView.displayedItems(cat.items, expanded: true)

        XCTAssertTrue(
            expanded.map(\.name).contains(Self.race7),
            "the market #5133 exists to surface is still unreachable on native"
        )
        XCTAssertEqual(expanded.count, cat.items.count, "expanding must reveal ALL of them")
    }

    /// And it was never only the two-row race: the cap fell between card 5 and
    /// card 6, so every one of the six families was hidden. A repair that
    /// rescued `Race to 7` alone — by raising the cap to 10, say — would pass
    /// the test above and still lose `Race to 35`.
    func testAllSixRacesWereHiddenAndAllSixComeBack() throws {
        let cat = try otherMarketsCategory(wire)
        let races = cat.items.map(\.name).filter {
            SpecialEventMarketsView.isScoringRaceMarket($0)
        }
        XCTAssertEqual(races.count, 6)

        let collapsed = Set(SpecialEventMarketsView.displayedItems(cat.items, expanded: false).map(\.name))
        let expanded = Set(SpecialEventMarketsView.displayedItems(cat.items, expanded: true).map(\.name))

        for race in races {
            XCTAssertFalse(collapsed.contains(race), "\(race) was visible before the repair?")
            XCTAssertTrue(expanded.contains(race), "\(race) is still unreachable")
        }
    }

    // MARK: - The cap still does its job

    /// The other direction, and the reason this is a disclosure and not a
    /// deletion: closed, the category is still five cards. A repair that just
    /// removed the cap would pass every test above and hand a reader eleven
    /// stacked cards in a section called "Additional Markets".
    func testTheCategoryIsStillFiveCardsWhenClosed() throws {
        let cat = try otherMarketsCategory(wire)

        XCTAssertEqual(SpecialEventMarketsView.displayedItems(cat.items, expanded: false).count, 5)
    }

    /// A category that fits shows everything either way, and grows no control.
    func testACategoryUnderTheCapIsUnaffected() {
        let short = (1...3).map { row("Market \($0)", "Yes", 0.4) }
        let view = SpecialEventMarketsView(markets: short, eventStatus: nil)
        let cat = view.categories.first { $0.title == Self.otherMarkets }

        let items = try? XCTUnwrap(cat).items
        XCTAssertEqual(items?.count, 3)
        XCTAssertEqual(SpecialEventMarketsView.displayedItems(items ?? [], expanded: false).count, 3)
        XCTAssertEqual(SpecialEventMarketsView.displayedItems(items ?? [], expanded: true).count, 3)
    }

    // MARK: - The two halves of #5133 compose

    /// CERT-2617's half and CERT-2620's half in one call, on the morning's LIVE
    /// prices: the two-row race must clear hero suppression AND clear the cap.
    /// Either one alone leaves the reader with nothing.
    func testTheExemptionAndTheDisclosureComposeOnTheLiveSpecimen() throws {
        let live = wire.map { r -> GameMarketOther in
            guard r.marketName == Self.race7 else { return r }
            let p = r.outcomeName.hasPrefix("Detroit") ? 0.56 : 0.44
            return row(r.marketName, r.outcomeName, p)
        }

        let cat = try otherMarketsCategory(live)
        XCTAssertTrue(cat.items.map(\.name).contains(Self.race7), "hero suppression took it again")

        let expanded = SpecialEventMarketsView.displayedItems(cat.items, expanded: true)
        XCTAssertTrue(expanded.map(\.name).contains(Self.race7), "the cap took it instead")

        // …and the hero's own question is still not in this section.
        XCTAssertFalse(
            cat.items.map(\.name).contains("New Orleans vs Detroit Winner"),
            "the match winner leaked into Additional Markets"
        )
    }
}
