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
        GameMarketOther(
            marketName: market,
            outcomeName: outcome,
            probability: p,
            source: "kalshi",
            // #4970 — these suites are about the SCORING RACE filter, not the
            // price age, so every row here is undatable and `ageDecision`
            // stays silent over them.
            observedAt: nil
        )
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
        let view = SpecialEventMarketsView(markets: rows, eventStatus: nil, commenceTime: nil)
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

    // MARK: - The repair, as the browser keeps it (#10830)
    //
    // CERT-2620's repair was a per-category "Show N more". #10830 replaced the
    // category cap with the event page's market browser: every card is a row,
    // a family shows a bounded window that grows a page at a time, and a search
    // crosses families. These tests hold the same promise — every race is
    // reachable — against the seam the body now browses (`browseRows`) and the
    // browser's own rule (`MarketBrowserLogic`).

    private func browse(_ rows: [GameMarketOther]) -> [SpecialEventMarketsView.BrowseRow] {
        let view = SpecialEventMarketsView(markets: rows, eventStatus: nil, commenceTime: nil)
        return SpecialEventMarketsView.browseRows(view.categories)
    }

    /// The indices a reader sees after tapping `family`, with `query` typed,
    /// before any "Show more".
    private func firstWindow(
        _ rows: [SpecialEventMarketsView.BrowseRow], family: String?, query: String = ""
    ) -> [String] {
        MarketBrowserLogic.matchingIndices(
            groupNames: rows.map(\.family),
            searchTexts: rows.map(SpecialEventMarketsView.searchText),
            query: query,
            selected: family
        )
        .prefix(MarketBrowserLogic.pageSize)
        .map { rows[$0].item.name }
    }

    /// Nothing is capped away: every card of every category is a browser row.
    func testEveryCardOfEveryCategoryIsABrowseRow() throws {
        let view = SpecialEventMarketsView(markets: wire, eventStatus: nil, commenceTime: nil)
        let rows = SpecialEventMarketsView.browseRows(view.categories)

        XCTAssertEqual(rows.count, view.categories.reduce(0) { $0 + $1.items.count })
        XCTAssertEqual(rows.first { $0.item.name == Self.race7 }?.family, Self.otherMarkets)
    }

    /// THE NAMED GUARD: the measured card is on screen once its family is
    /// chosen — card 10 of 11 sits inside the first window of 12.
    func testRaceTo7IsReachablePastFiveCardCategoryCap() throws {
        let window = firstWindow(browse(wire), family: Self.otherMarkets)

        XCTAssertTrue(
            window.contains(Self.race7),
            "the market #5133 exists to surface is still unreachable on native"
        )
    }

    /// And by search from wherever the reader is: the field ignores families.
    func testASearchFindsRaceTo7FromTheFirstFamily() throws {
        let rows = browse(wire)
        let found = firstWindow(rows, family: rows.first?.family, query: "race to 7")

        XCTAssertEqual(found, [Self.race7])
    }

    /// Every one of the six families, not just the two-row race: the old cap
    /// hid all six, and a repair that rescued one would still lose the rest.
    func testAllSixRacesAreReachable() throws {
        let rows = browse(wire)
        let races = rows.map(\.item.name).filter { SpecialEventMarketsView.isScoringRaceMarket($0) }
        XCTAssertEqual(races.count, 6)

        let window = Set(firstWindow(rows, family: Self.otherMarkets))
        for race in races {
            XCTAssertTrue(window.contains(race), "\(race) is still unreachable")
        }
    }

    // MARK: - The window still does its job

    /// The other direction: a long family is bounded, never eleven-plus stacked
    /// cards at once, and "Show more" walks it to the end a page at a time.
    func testALongFamilyIsWindowedAndWalksToTheEnd() {
        let long = (1...30).map { row("Market \($0)", "Yes", 0.4) }
        let rows = browse(long)
        XCTAssertEqual(rows.count, 30)
        XCTAssertEqual(firstWindow(rows, family: Self.otherMarkets).count, MarketBrowserLogic.pageSize)

        var limit = MarketBrowserLogic.pageSize
        var steps = 0
        while limit < rows.count {
            limit = MarketBrowserLogic.nextLimit(current: limit, matchCount: rows.count)
            steps += 1
        }
        XCTAssertGreaterThanOrEqual(limit, rows.count)
        XCTAssertEqual(steps, 2, "30 rows in pages of 12 is three windows")
    }

    // MARK: - The two halves of #5133 compose

    /// CERT-2617's half and CERT-2620's half in one call, on the morning's LIVE
    /// prices: the two-row race must clear hero suppression AND be browsable.
    func testTheExemptionAndTheDisclosureComposeOnTheLiveSpecimen() throws {
        let live = wire.map { r -> GameMarketOther in
            guard r.marketName == Self.race7 else { return r }
            let p = r.outcomeName.hasPrefix("Detroit") ? 0.56 : 0.44
            return row(r.marketName, r.outcomeName, p)
        }

        let cat = try otherMarketsCategory(live)
        XCTAssertTrue(cat.items.map(\.name).contains(Self.race7), "hero suppression took it again")
        XCTAssertTrue(firstWindow(browse(live), family: Self.otherMarkets).contains(Self.race7),
                      "the browser window took it instead")

        // …and the hero's own question is still not in this section.
        XCTAssertFalse(
            cat.items.map(\.name).contains("New Orleans vs Detroit Winner"),
            "the match winner leaked into the game questions"
        )
    }
}
