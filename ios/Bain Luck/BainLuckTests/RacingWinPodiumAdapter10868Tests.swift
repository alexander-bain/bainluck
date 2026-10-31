import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing win/podium card's retained REAL input beyond the shared
/// `RacingAdapterFixtures10868`: the pre-race Singapore Grand Prix podium market
/// with the outcomes of the four drivers the shared winner subset keeps.
///
/// REDUCED VERBATIM SUBSET, made by `/tmp/cli-10868-racing-podium/make_podium_subset.py`
/// (run `python3 -I make_podium_subset.py <design-dir> <out>`; same method as
/// `/tmp/cli-10868-racing/make_subsets.py`): each kept top-level pair and outcome
/// object is the server's bytes, asserted there as a byte-for-byte substring of
/// the source; only which outcomes are kept and the line breaks are assembled.
/// Source under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`.
@MainActor
enum RacingWinPodiumFixtures10868 {
    /// `atlas-v6/raw/field-63989361.json` (sha256 6b447d4e…1748):
    /// outcomes [242933922, 243467981, 243467982, 242025505] (source order) of 23.
    static let podiumBeforePaired = #"""
    {
    "id":63989361,
    "name":"Singapore Grand Prix: Driver Podium Finish",
    "description":null,
    "sport":null,
    "sport_name":null,
    "category":"championship",
    "llm_sport_category":"motorsports",
    "status":"open",
    "source":"polymarket",
    "external_id":"1123926",
    "market_type":"field",
    "mutually_exclusive":false,
    "commence_time":"2026-10-03T11:30:58+00:00",
    "resolution_date":"2026-10-18T12:00:00+00:00",
    "outcomes":[
    {"id":242933922,"name":"Max Verstappen","probability":0.81,"american_odds":-441,"rank":1,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.62,"opening_american_odds":-163,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:55:26.893131+00:00","price_changed_at":"2026-10-11T04:55:26.893131+00:00"},
    {"id":243467981,"name":"Charles Leclerc","probability":0.63,"american_odds":-167,"rank":2,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.47,"opening_american_odds":113,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:49:59.592455+00:00","price_changed_at":"2026-10-11T04:33:05.344973+00:00"},
    {"id":243467982,"name":"Lewis Hamilton","probability":0.6,"american_odds":-144,"rank":3,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.44,"opening_american_odds":127,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:55:35.729598+00:00","price_changed_at":"2026-10-11T04:55:35.729598+00:00"},
    {"id":242025505,"name":"Kimi Antonelli","probability":0.475,"american_odds":111,"rank":4,"rank_change_24h":null,"probability_change_24h":null,"opening_probability":0.62,"opening_american_odds":-163,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-11T04:39:05.769506+00:00","price_changed_at":"2026-10-11T04:00:13.637670+00:00"}
    ],
    "outcome_count":23,
    "lead_outcome_id":null,
    "openings_withheld":false,
    "prices_withheld":0,
    "expired_rungs_dropped":0,
    "bookmakers":["polymarket"],
    "category_tags":["motorsports"],
    "created_at":"2026-10-03T12:15:51.012496+00:00",
    "updated_at":"2026-10-11T04:07:53.654130+00:00",
    "group_id":"polymarket:1123926",
    "canonical_market_key":null,
    "hook_description":null,
    "hook_withheld":false,
    "image_url":"https://images.pexels.com/photos/29309757/pexels-photo-29309757.jpeg?auto=compress&cs=tinysrgb&h=650&w=940",
    "event_concept_key":null,
    "hub_slug":null,
    "category_page":null,
    "sport_page_key":null,
    "container_of_event_id":null
    }
    """#

    static let podiumMarket = 63989361
    static let winnerMarket = 63989371
    static let verstappenPodium = 242933922
    static let leclercPodium = 243467981
    static let hamiltonPodium = 243467982
    static let antonelliPodium = 242025505

    /// CONSTRUCTED — THE TEST HOST'S JOIN, standing in for the adopting owner's
    /// binding (no production owner serves one): each kept driver's winner
    /// outcome id → the outcome id the retained podium market serves for that
    /// same driver, read by a person off the two retained bodies.
    static let join: [Int: Int] = [
        RacingAdapterFixtures10868.verstappen: verstappenPodium,
        RacingAdapterFixtures10868.hamilton: hamiltonPodium,
        RacingAdapterFixtures10868.leclerc: leclercPodium,
        RacingAdapterFixtures10868.antonelli: antonelliPodium,
    ]

    /// A CONSTRUCTED update that omits one outcome: its whole line removed (and
    /// the trailing comma of the kept line before it when it was last), proven
    /// to have matched exactly one line.
    static func omitting(_ json: String, outcome id: Int) -> String {
        var lines = json.components(separatedBy: "\n")
        let hits = lines.indices.filter { lines[$0].hasPrefix("{\"id\":\(id),") }
        precondition(hits.count == 1, "not exactly one outcome \(id)")
        let index = hits[0]
        lines.remove(at: index)
        if lines[index].hasPrefix("]"), lines[index - 1].hasSuffix(",") {
            lines[index - 1].removeLast()
        }
        return lines.joined(separator: "\n")
    }
}

/// #10868 — the racing adapter, part five (the win and podium comparison card),
/// read through the approved leaf's own model (`FieldPodiumModel10868`), and its
/// composition into the page input and the host's pure `build`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// REAL: the retained Singapore winner and podium bodies, before the race and
/// after it (`RacingAdapterFixtures10868`, `RacingWinPodiumFixtures10868`).
/// CONSTRUCTED here, and named where used: the reader's calendar and `now`, the
/// held cohort and pair, THE TEST HOST'S JOIN (`RacingWinPodiumFixtures10868.join`),
/// and each labelled variant of a body or a join.
@MainActor
final class RacingWinPodiumAdapter10868Tests: XCTestCase {
    private typealias W = RacingWinPodiumAdapter10868
    private typealias Page = RacingFieldPageAdapter10868
    private typealias F = RacingAdapterFixtures10868
    private typealias P = RacingWinPodiumFixtures10868
    private typealias Host = RacingEventPageHost10868

    // MARK: Helpers

    private func makePodium(_ json: String = P.podiumBeforePaired, join: [Int: Int] = P.join,
                            winnerMarketID: Int = P.winnerMarket, podiumMarketID: Int = P.podiumMarket) throws -> W.Podium {
        W.Podium(market: try F.market(json),
                 join: W.Join(winnerMarketID: winnerMarketID, podiumMarketID: podiumMarketID, outcomes: join))
    }

    private func makeCard(_ race: String = F.winnerBefore, podium: W.Podium?, selected: String? = nil,
                          now: String = F.beforeCapture, cohort: [Int]? = nil) throws -> W.Card? {
        W.card(race: try F.market(race), podium: podium, selected: selected, host: F.host(now, cohort: cohort))
    }

    private func makeInput(_ race: String = F.winnerBefore, podium: W.Podium?, selected: String? = nil,
                           now: String = F.beforeCapture, cohort: [Int]? = nil) throws -> FieldPodiumInput10868 {
        try XCTUnwrap(makeCard(race, podium: podium, selected: selected, now: now, cohort: cohort)).input
    }

    private func figure(_ endpoint: FieldPodiumEndpoint10868?) -> String? {
        endpoint.flatMap { FieldChaseModel10868.figure($0.reading) }
    }

    private func words(_ endpoint: FieldPodiumEndpoint10868?) -> String? {
        endpoint.flatMap { FieldChaseModel10868.words($0.reading) }
    }

    private func pairID(_ input: FieldPodiumInput10868, _ name: String) throws -> String {
        try XCTUnwrap(input.pairs.first { $0.name == name }).id
    }

    /// The figure the podium market's own Market Details row prints for a price.
    private func detailsFigure(_ json: String, _ id: Int, _ probability: Double) throws -> String {
        formatProbability(probability, renderedPercent: futuresDetailRenderedPercents(try F.market(json).outcomes)[id])
    }

    private func clock(_ iso: String, _ host: Page.Host) -> String {
        Page.clockWords(iso.asDate!, host: host)
    }

    // MARK: Before — each side is its own market's price, with its own clock

    func testBeforeEachDriverComparesItsOwnWinAndItsOwnPodiumChanceEachWithItsOwnClock() throws {
        let host = F.host(F.beforeCapture)
        let race = try F.market(F.winnerBefore)
        let input = try makeInput(podium: try makePodium())
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.scope, "racing:63989371:before:win-podium")
        // The roster: every kept pair, in the winner market's served order.
        XCTAssertEqual(input.pairs.map(\.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc", "Kimi Antonelli"])
        XCTAssertEqual(input.pairs.map(\.win.outcomeID), ["241675151", "241675153", "241675154", "241675152"])
        XCTAssertEqual(input.pairs.map(\.podium.outcomeID), ["242933922", "243467982", "243467981", "242025505"])
        XCTAssertEqual(Set(input.pairs.map(\.win.marketID)), ["63989371"])
        XCTAssertEqual(Set(input.pairs.map(\.podium.marketID)), ["63989361"])
        XCTAssertEqual(Set(input.pairs.map(\.podium.source)), ["polymarket"])
        XCTAssertEqual(input.pairs.first?.id, "polymarket|63989371|241675151+polymarket|63989361|242933922")
        // The window is the headline's drivers; no surname is parsed.
        XCTAssertEqual(input.displayed.map(\.name), Page.headline(race, host: host).displayed.map(\.name))
        XCTAssertEqual(input.displayed.map(\.compactName), [nil, nil, nil])
        // With none held, the first displayed pair is selected; Previous / Next walk the roster.
        XCTAssertEqual(input.selectedID, input.pairs[0].id)
        XCTAssertNil(input.previousID)
        XCTAssertEqual(input.nextID, input.pairs[1].id)
        XCTAssertEqual(input.finishes, [], "no classification reaches the app")

        let model = FieldPodiumModel10868(input)
        XCTAssertTrue(model.canDraw)
        XCTAssertEqual(model.rows.map { figure($0.win) }, ["62%", "14%", "13%"])
        XCTAssertEqual(model.rows.map { figure($0.podium) }, ["81%", "60%", "63%"])
        let verstappen = try XCTUnwrap(model.rows.first)
        XCTAssertEqual(verstappen.win?.reading, .reading(FieldChooserReading10868(
            label: "Win chance", value: .recorded(text: "62%", detail: "\(clock(F.beforeStamp, host)) · Polymarket"))))
        XCTAssertEqual(verstappen.podium?.reading, .reading(FieldChooserReading10868(
            label: "Podium chance",
            value: .recorded(text: "81%", detail: "\(clock("2026-10-11T04:55:26.893131+00:00", host)) · Polymarket"))),
            "the podium side keeps its own clock, not the winner market's")
        XCTAssertEqual(verstappen.win?.chance, .value(probability: 0.6162, fraction: 0.6162))
        XCTAssertEqual(verstappen.podium?.chance, .value(probability: 0.81, fraction: 0.81))

        // Antonelli, outside the default window, through the roster: his podium figure is
        // the podium market's own Market Details figure.
        let antonelli = try XCTUnwrap(FieldPodiumModel10868(try makeInput(
            podium: try makePodium(), selected: try pairID(input, "Kimi Antonelli"))).selected)
        XCTAssertEqual(figure(antonelli.win), "7%")
        XCTAssertEqual(figure(antonelli.podium), try detailsFigure(P.podiumBeforePaired, P.antonelliPodium, 0.475))
    }

    func testEachRawPriceIsItsOwnNeverNormalizedSummedOrMadeMonotone() throws {
        let input = try makeInput(podium: try makePodium())
        let raw = Dictionary(uniqueKeysWithValues: input.chances.map { ("\($0.ref.marketID)|\($0.ref.outcomeID)", $0.probability) })
        XCTAssertEqual(raw.count, 8, "every recent side of both markets, once")
        XCTAssertEqual(raw["63989371|241675151"], 0.6162)
        XCTAssertEqual(raw["63989371|241675153"], 0.1364)
        XCTAssertEqual(raw["63989371|241675154"], 0.127)
        XCTAssertEqual(raw["63989371|241675152"], 0.0706)
        XCTAssertEqual(raw["63989361|242933922"], 0.81)
        XCTAssertEqual(raw["63989361|243467982"], 0.6)
        XCTAssertEqual(raw["63989361|243467981"], 0.63)
        XCTAssertEqual(raw["63989361|242025505"], 0.475)
        // Each chance is tied to the very reading its original shows.
        let model = FieldPodiumModel10868(input)
        for chance in input.chances {
            let original = try XCTUnwrap(input.catalogue.first { $0.ref == chance.ref })
            XCTAssertEqual(FieldOutlookModel10868.beforeReading(original.plan), chance.reading)
            XCTAssertEqual(model.outlook.chance(original), .value(probability: chance.probability, fraction: chance.probability))
        }
    }

    func testTheCatalogueHoldsEveryOriginalOfBothMarketsOnceInServedOrder() throws {
        let input = try makeInput(podium: try makePodium())
        XCTAssertEqual(input.catalogue.map(\.ref.marketID), Array(repeating: "63989371", count: 4) + Array(repeating: "63989361", count: 4))
        XCTAssertEqual(input.catalogue.map(\.ref.outcomeID), [
            "241675151", "241675153", "241675154", "241675152",
            "242933922", "243467981", "243467982", "242025505",
        ])
        XCTAssertEqual(Set(input.catalogue.map(\.ref)).count, 8)
        XCTAssertEqual(Set(input.catalogue.map(\.ref.scope)), [input.scope])
        XCTAssertEqual(input.catalogue.map(\.browseStatus), Array(repeating: "Race winner", count: 4) + Array(repeating: "Podium finish", count: 4))
        XCTAssertEqual(input.catalogue.map(\.result), Array(repeating: nil, count: 8), "no result before the final")
    }

    // MARK: Currentness — each side's own market

    func testEachSideKeepsItsOwnMarketsCurrentness() throws {
        // CONSTRUCTED reader clock: 10:30Z — 6 h 22 m after every kept winner price was
        // written, 5 h 35 m – 5 h 51 m after the kept podium prices.
        let late = try makeInput(podium: try makePodium(), now: "2026-10-11T10:30:00Z", cohort: [F.verstappen, F.antonelli])
        let rows = FieldPodiumModel10868(late).rows
        XCTAssertEqual(rows.map { figure($0.win) }, [nil, nil], "a stale win price is never a current chance")
        XCTAssertEqual(rows.map { words($0.win) }, [AllMarketsCatalogView9483.noRecentPrice, AllMarketsCatalogView9483.noRecentPrice])
        XCTAssertEqual(rows.map { $0.win?.chance }, [.unavailable, .unavailable])
        XCTAssertEqual(rows.map { figure($0.podium) },
                       ["81%", try detailsFigure(P.podiumBeforePaired, P.antonelliPodium, 0.475)],
                       "the podium market's own recent prices stay figures")
        XCTAssertEqual(Set(late.chances.map(\.ref.marketID)), ["63989361"])

        // CONSTRUCTED 10:45Z: Antonelli's podium price (04:39:05) is now past the bound;
        // Verstappen's (04:55:26) is not.
        let later = FieldPodiumModel10868(try makeInput(podium: try makePodium(), now: "2026-10-11T10:45:00Z",
                                                    cohort: [F.verstappen, F.antonelli])).rows
        XCTAssertEqual(figure(later[0].podium), "81%")
        XCTAssertNil(figure(later[1].podium))
        XCTAssertEqual(words(later[1].podium), AllMarketsCatalogView9483.noRecentPrice)
    }

    func testWithNoChanceToPlaceTheRowsKeepTheirWordsAndNoEmptyScaleIsDrawn() throws {
        // CONSTRUCTED reader clock: a day later, every kept price of both markets is stale.
        let input = try makeInput(podium: try makePodium(), now: "2026-10-12T05:00:00Z")
        XCTAssertEqual(input.chances, [])
        XCTAssertEqual(input.scale.ticks, [])
        XCTAssertEqual(input.scale.words, "No recent chance to place on the scale")
        XCTAssertFalse(FieldPodiumModel10868(input).canDraw)
    }

    // MARK: Final — each side's own result, never a chance

    func testAtTheFinalEachSideShowsItsOwnMarketsResultAndNeverASettledPrice() throws {
        let cohort = [F.verstappen, F.leclerc, F.hamilton, F.antonelli]
        let first = try makeInput(F.winnerFinal, podium: try makePodium(F.podiumFinal), now: F.finalCapture, cohort: cohort)
        let antonelliID = try pairID(first, "Kimi Antonelli")
        let input = try makeInput(F.winnerFinal, podium: try makePodium(F.podiumFinal), selected: antonelliID,
                              now: F.finalCapture, cohort: cohort)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.scope, "racing:63989371:final:win-podium")
        XCTAssertEqual(input.chances, [], "a settled 0% or 100% is never a chance")
        XCTAssertEqual(input.finishes, [])
        for original in input.catalogue {
            if case .recorded = FieldOutlookModel10868.beforeReading(original.plan).value {
                XCTFail("\(original.name) in \(original.ref.marketID) shows a settled price as a chance")
            }
        }
        let model = FieldPodiumModel10868(input)
        XCTAssertFalse(model.canDraw, "nothing to place: the rows keep their words")
        XCTAssertEqual(input.scale.words, "Pre-race chances unavailable")
        XCTAssertEqual(Set(model.rows.flatMap { [words($0.win), words($0.podium)] }), ["Pre-race chance unavailable"])
        // Each side's own market's grade: Antonelli lost the win and won the podium.
        XCTAssertEqual(model.rows.map(\.slot.name), ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton", "Kimi Antonelli"])
        XCTAssertEqual(model.rows.map { [model.result($0.win)?.words, model.result($0.podium)?.words] },
                       [["Won", "Won"], ["Lost", "Won"], ["Lost", "Lost"], ["Lost", "Won"]])
        let selected = try XCTUnwrap(model.selected)
        XCTAssertEqual(selected.pair?.name, "Kimi Antonelli")
        XCTAssertEqual(model.result(selected.win)?.title, "Prop result")
        XCTAssertEqual(model.selectedFinish, .unavailable(label: "Actual finish", words: "Finish unavailable"),
                       "no classification reaches the app; a contract result is never a finish")
        XCTAssertEqual(model.context, "Each result comes from its own market")
        XCTAssertEqual(input.copy.beforeLabel, "Pre-race")
    }

    func testAPodiumMarketNotYetGradedIsNeverALossBesideASettledWinner() throws {
        // CONSTRUCTED pairing of moments: the settled winner body with the open
        // pre-race podium body, read after the race.
        let input = try makeInput(F.winnerFinal, podium: try makePodium(), now: F.finalCapture,
                              cohort: [F.verstappen, F.antonelli])
        let model = FieldPodiumModel10868(input)
        XCTAssertEqual(model.rows.map { model.result($0.win)?.words }, ["Won", "Lost"])
        XCTAssertEqual(model.rows.map { model.result($0.podium)?.words }, ["Not yet confirmed", "Not yet confirmed"])
        XCTAssertEqual(model.rows.map { words($0.podium) }, ["Pre-race chance unavailable", "Pre-race chance unavailable"],
                       "after the race an open price is not called pre-race")
    }

    func testASettledPodiumSideBesideAnOpenWinnerIsNeverAChanceOrAResult() throws {
        // CONSTRUCTED pairing of moments: the open pre-race winner body with the
        // settled podium body.
        let input = try makeInput(podium: try makePodium(F.podiumFinal), cohort: [F.verstappen, F.hamilton])
        let model = FieldPodiumModel10868(input)
        XCTAssertEqual(model.rows.map { figure($0.win) }, ["62%", "14%"])
        XCTAssertEqual(model.rows.map { words($0.podium) }, ["Settled · no current chance", "Settled · no current chance"])
        XCTAssertEqual(model.rows.map { $0.podium?.chance }, [.unavailable, .unavailable])
        XCTAssertEqual(model.rows.map { model.result($0.podium)?.words }, [nil, nil], "results are read at the final only")
    }

    // MARK: The join — explicit, exact, never inferred

    func testWithoutAPodiumMarketOrWithAnotherMarketsJoinThereIsNoCard() throws {
        XCTAssertNil(try makeCard(podium: nil), "production today: no podium body, no join")
        // CONSTRUCTED joins built for other markets.
        XCTAssertNil(try makeCard(podium: try makePodium(winnerMarketID: 63989372)))
        XCTAssertNil(try makeCard(podium: try makePodium(podiumMarketID: 63989362)))
        // CONSTRUCTED: the race's own market handed in as its podium market.
        XCTAssertNil(try makeCard(podium: try makePodium(F.winnerBefore, podiumMarketID: P.winnerMarket)))
        // CONSTRUCTED: a join that pairs nobody this update serves.
        XCTAssertNil(try makeCard(podium: try makePodium(join: [:])))
        XCTAssertNil(try makeCard(podium: try makePodium(join: [1: P.verstappenPodium])))
    }

    func testAJoinEntryNamingAnotherMarketsOutcomeNeverBorrowsAChance() throws {
        // CONSTRUCTED join: Leclerc's entry names the WINNER market's own Leclerc id,
        // which the podium market does not serve.
        var join = P.join
        join[F.leclerc] = F.leclerc
        let input = try makeInput(podium: try makePodium(join: join))
        let model = FieldPodiumModel10868(input)
        let leclerc = try XCTUnwrap(model.rows.first { $0.slot.name == "Charles Leclerc" })
        XCTAssertNotNil(leclerc.pair, "the pair is the join's; its podium side simply does not resolve")
        XCTAssertEqual(figure(leclerc.win), "13%")
        XCTAssertEqual(leclerc.podium?.reading, .unavailable(label: "Finish top 3", words: "Chance unavailable in this update"))
        XCTAssertEqual(leclerc.podium?.chance, .unavailable)
        XCTAssertNil(leclerc.podium?.original)
        // Its neighbours keep their own.
        XCTAssertEqual(figure(model.rows[0].podium), "81%")
        XCTAssertEqual(figure(model.rows[1].podium), "60%")
    }

    func testAPodiumOutcomeClaimedByTwoDriversPairsNeither() throws {
        // CONSTRUCTED contradictory join: Hamilton and Leclerc both name Leclerc's podium outcome.
        var join = P.join
        join[F.hamilton] = P.leclercPodium
        let input = try makeInput(podium: try makePodium(join: join))
        XCTAssertEqual(input.pairs.map(\.name), ["Max Verstappen", "Kimi Antonelli"])
        let model = FieldPodiumModel10868(input)
        XCTAssertEqual(model.rows.map(\.slot.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc"])
        XCTAssertEqual(model.rows.map { $0.pair == nil }, [false, true, true])
        XCTAssertEqual(model.summary(model.rows[1]), "Lewis Hamilton. Driver pairing unavailable in this update")
        XCTAssertEqual(figure(model.rows[0].podium), "81%", "the valid neighbour keeps its pair")
    }

    func testADisplayedDriverTheJoinDoesNotPairKeepsItsRowWithNoMark() throws {
        // CONSTRUCTED join without Antonelli; CONSTRUCTED held cohort with him first.
        var join = P.join
        join[F.antonelli] = nil
        let input = try makeInput(podium: try makePodium(join: join), cohort: [F.antonelli, F.verstappen])
        let model = FieldPodiumModel10868(input)
        XCTAssertEqual(model.rows.map(\.slot.name), ["Kimi Antonelli", "Max Verstappen"])
        XCTAssertNil(model.rows[0].pair)
        XCTAssertNil(model.rows[0].win)
        XCTAssertNil(model.rows[0].podium)
        XCTAssertNil(model.rowChoice(model.rows[0], canChoose: true))
        XCTAssertEqual(input.selectedID, try pairID(input, "Max Verstappen"), "the first displayed PAIR, never an unpaired row")
    }

    // MARK: Updates — a vanished driver

    func testAPodiumUpdateThatOmitsADriverKeepsThatDriversPairWithItsOwnAbsence() throws {
        let full = try makeInput(podium: try makePodium())
        let hamiltonID = try pairID(full, "Lewis Hamilton")
        // CONSTRUCTED: the podium update omits Hamilton's outcome.
        let omitted = P.omitting(P.podiumBeforePaired, outcome: P.hamiltonPodium)
        let input = try makeInput(podium: try makePodium(omitted), selected: hamiltonID)
        let model = FieldPodiumModel10868(input)
        let selected = try XCTUnwrap(model.selected)
        XCTAssertEqual(selected.pair?.id, hamiltonID, "the held pair is still Hamilton")
        XCTAssertEqual(figure(selected.win), "14%")
        XCTAssertEqual(selected.podium?.reading, .unavailable(label: "Finish top 3", words: "Chance unavailable in this update"))
        XCTAssertEqual(input.catalogue.count, 7)
    }

    func testAPodiumOutcomeServedUnderANewIdIsNeverRepairedByName() throws {
        // CONSTRUCTED: the podium update serves Hamilton under a new outcome id; the
        // join still names the old one.
        let renamed = F.replacing(P.podiumBeforePaired, #"{"id":243467982,"#, with: #"{"id":999243467982,"#)
        let input = try makeInput(podium: try makePodium(renamed))
        let model = FieldPodiumModel10868(input)
        let hamilton = try XCTUnwrap(model.rows.first { $0.slot.name == "Lewis Hamilton" })
        XCTAssertEqual(hamilton.pair?.podium.outcomeID, "243467982")
        XCTAssertNil(hamilton.podium?.original)
        XCTAssertNil(figure(hamilton.podium), "a podium row named Lewis Hamilton is not his by name")
        XCTAssertTrue(input.catalogue.contains { $0.ref.outcomeID == "999243467982" }, "the new original stays in the catalogue")
        XCTAssertFalse(input.pairs.contains { $0.podium.outcomeID == "999243467982" })
    }

    func testAWinnerUpdateThatOmitsTheHeldDriverSelectsNoOneElse() throws {
        let full = try makeInput(podium: try makePodium())
        let leclercID = try pairID(full, "Charles Leclerc")
        // CONSTRUCTED: the winner update omits Leclerc's outcome.
        let omitted = P.omitting(F.winnerBefore, outcome: F.leclerc)
        let input = try makeInput(omitted, podium: try makePodium(), selected: leclercID)
        XCTAssertEqual(input.pairs.map(\.name), ["Max Verstappen", "Lewis Hamilton", "Kimi Antonelli"])
        XCTAssertEqual(input.selectedID, leclercID, "the held pair id is passed through unchanged")
        XCTAssertNil(input.previousID)
        XCTAssertNil(input.nextID)
        let model = FieldPodiumModel10868(input)
        XCTAssertNil(model.selected, "no other driver is selected in its place")
        XCTAssertEqual(input.copy.noSelection, "Driver unavailable in this update")
        // Served again, it is the same selection.
        let back = FieldPodiumModel10868(try makeInput(podium: try makePodium(), selected: leclercID))
        XCTAssertEqual(back.selected?.pair?.name, "Charles Leclerc")
    }

    // MARK: Selection and navigation

    func testTheHeldPairAndItsNeighboursAreExactIdsThroughTheWholeRoster() throws {
        let full = try makeInput(podium: try makePodium())
        let ids = full.pairs.map(\.id)
        let hamilton = try makeInput(podium: try makePodium(), selected: ids[1])
        XCTAssertEqual(hamilton.selectedID, ids[1])
        XCTAssertEqual(hamilton.previousID, ids[0])
        XCTAssertEqual(hamilton.nextID, ids[2])
        let model = FieldPodiumModel10868(hamilton)
        XCTAssertEqual(model.chooseID(hamilton.nextID, canChoose: true), ids[2])
        XCTAssertNil(model.chooseID(hamilton.nextID, canChoose: false))

        // Antonelli is last in the roster and outside the default window.
        let antonelli = try makeInput(podium: try makePodium(), selected: ids[3])
        XCTAssertEqual(antonelli.previousID, ids[2])
        XCTAssertNil(antonelli.nextID)
        XCTAssertTrue(FieldPodiumModel10868(antonelli).selectionOutsideWindow)
        XCTAssertEqual(antonelli.copy.outsideWindow, "Selected driver is outside this group")
        XCTAssertEqual(full.copy.noSelection, "Choose a driver")
    }

    // MARK: Copy and About

    func testTheWordsArePlainAndTheAboutNamesEachMarket() throws {
        let card = try XCTUnwrap(try makeCard(podium: try makePodium()))
        let copy = card.input.copy
        XCTAssertEqual(copy.title, "Win and podium chances")
        XCTAssertEqual(copy.winLabel, "Win")
        XCTAssertEqual(copy.podiumLabel, "Finish top 3")
        XCTAssertEqual(copy.beforeLabel, "Recorded chance", "no reading is called pre-race while the market is open")
        XCTAssertEqual(copy.beforeContext, "Recorded chances · each keeps its own time")
        XCTAssertEqual(card.input.scale.words, "0–100% · each mark is its own market’s chance")
        XCTAssertEqual(card.input.scale.ticks.map(\.label), ["0%", "50%", "100%"])
        XCTAssertEqual(card.about.title, "How to read this comparison")
        XCTAssertEqual(card.about.paragraphs.count, 3)
        XCTAssertTrue(card.about.paragraphs[0].contains("own Polymarket probability in “Singapore Grand Prix: Driver Winner”"))
        XCTAssertTrue(card.about.paragraphs[0].contains("own Polymarket probability in “Singapore Grand Prix: Driver Podium Finish”"))
        XCTAssertTrue(card.about.paragraphs[1].contains("never added together"))
        XCTAssertTrue(card.about.paragraphs[2].contains("last 6 hours"))
        let final = try XCTUnwrap(try makeCard(F.winnerFinal, podium: try makePodium(F.podiumFinal), now: F.finalCapture))
        XCTAssertEqual(final.about.paragraphs.count, 4)
        XCTAssertTrue(final.about.paragraphs[3].hasPrefix("Results come only from each market’s own settlement"))

        let all = [copy.title, copy.explanation, copy.beforeContext, copy.duringContext, copy.finalContext,
                   copy.winLabel, copy.podiumLabel, copy.beforeLabel, copy.pairUnavailable, copy.chanceUnavailable,
                   copy.noSelection, copy.outsideWindow, copy.finishLabel, copy.finishUnavailable, copy.resultLabel,
                   copy.resultUnknown, copy.previousLabel, copy.nextLabel, copy.chooseHint ?? "", copy.originalHint ?? "",
                   copy.aboutLabel, copy.aboutHint ?? "", card.input.scale.words] + card.about.paragraphs + final.about.paragraphs
        for words in all {
            for banned in ["question", "served", "admitted", "pipeline"] {
                XCTAssertFalse(words.lowercased().contains(banned), "\(banned) in “\(words)”")
            }
        }
    }

    // MARK: The page and the host

    func testThePageOffersTheCardAsItsOneManualStory() throws {
        let race = try F.market(F.winnerBefore)
        let host = F.host(F.beforeCapture)
        let card = try XCTUnwrap(W.card(race: race, podium: try makePodium(), selected: nil, host: host))
        let page = RacingPageInputAdapter10868.input(race, history: RacingHistoryAdapter10868.unavailable(race, host: host),
                                                     originalsCount: 8, stream: .init(), winPodium: card, host: host)
        XCTAssertEqual(page.winPodium, card.input)
        XCTAssertEqual(page.winPodiumAbout, card.about)
        XCTAssertEqual(page.stream.cards, [StoryStreamPresentation10868.Card(id: "winPodium", name: "Win and podium chances")])
        XCTAssertEqual(page.stream.primary, StoryStreamPresentation10868.CardRef(scope: "racing:63989371:before:stories", id: "winPodium"))
        XCTAssertNil(page.stream.companion)
        XCTAssertNil(page.stream.previous)
        XCTAssertNil(page.stream.next)
        XCTAssertNil(page.stream.playback)
        XCTAssertNil(page.stream.dwellFraction)
        XCTAssertEqual(page.stream.resolve(reduceMotion: false, actionable: true).primary?.card?.name, "Win and podium chances")
        XCTAssertEqual(page.stories, [RacingEventPageStory10868(cardID: "winPodium", card: .winPodium)])
        XCTAssertNil(page.readerChances)

        let model = RacingEventPageModel10868(page)
        XCTAssertTrue(model.isMounted(.winPodium))
        XCTAssertEqual(model.storyCard("winPodium"), .winPodium)
        XCTAssertNotNil(model.about(.winPodium))
        XCTAssertEqual(RacingPageInputAdapter10868.card(try XCTUnwrap(page.stream.primary), scope: page.stream.scope), .winPodium)
        XCTAssertNil(RacingPageInputAdapter10868.card(StoryStreamPresentation10868.CardRef(
            scope: "racing:63989371:final:stories", id: "winPodium"), scope: page.stream.scope))

        // A card built for another phase is not this page's story.
        let finalCard = try XCTUnwrap(W.card(race: try F.market(F.winnerFinal), podium: try makePodium(F.podiumFinal),
                                             selected: nil, host: F.host(F.finalCapture)))
        let mixed = RacingPageInputAdapter10868.input(race, history: RacingHistoryAdapter10868.unavailable(race, host: host),
                                                      originalsCount: 8, stream: .init(), winPodium: finalCard, host: host)
        XCTAssertNil(mixed.winPodium)
        XCTAssertNil(mixed.winPodiumAbout)
        XCTAssertEqual(mixed.stream.cards, [])
        XCTAssertEqual(mixed.stories, [])
    }

    func testTheHostBuildsTheCardOnlyFromThePodiumBodyAndTheOwnersJoin() throws {
        let race = try F.market(F.winnerBefore)
        let now = F.beforeCapture.asDate!
        let locale = Locale(identifier: "en_US")
        let without = Host.build(race: race, history: nil, now: now, calendar: F.pacific, locale: locale)
        XCTAssertNil(without.input.winPodium, "production today: the card is absent")
        XCTAssertEqual(without.input.stream.cards, [])

        let podium = try makePodium()
        let first = Host.build(race: race, history: nil, podium: podium, now: now, calendar: F.pacific, locale: locale)
        let hamiltonID = try pairID(try XCTUnwrap(first.input.winPodium), "Lewis Hamilton")
        let built = Host.build(race: race, history: nil, podium: podium, now: now,
                               reading: Host.Reading(pair: hamiltonID), calendar: F.pacific, locale: locale)
        let card = try XCTUnwrap(built.input.winPodium)
        XCTAssertEqual(card.selectedID, hamiltonID)
        XCTAssertEqual(built.input.stories.map(\.card), [.winPodium])
        // The podium market joins All props once, even when also passed as another market.
        XCTAssertEqual(built.originals.catalogue?.originals.count, 8)
        let twice = Host.build(race: race, history: nil, markets: [podium.market], podium: podium, now: now,
                               calendar: F.pacific, locale: locale)
        XCTAssertEqual(twice.originals.catalogue?.originals.count, 8)

        // Either figure names the exact original All props holds.
        let leclerc = try XCTUnwrap(card.pairs.first { $0.name == "Charles Leclerc" })
        let podiumSelection = try XCTUnwrap(RacingOriginalsAdapter10868.selection(for: leclerc.podium, in: built.originals))
        XCTAssertEqual(podiumSelection.identity, OriginalMarketDetails9483.Identity(source: "polymarket", market: "63989361", side: "243467981"))
        XCTAssertEqual(podiumSelection.scope, "racing:63989371:before:originals")
        XCTAssertEqual(OriginalMarketDetails9483.original(in: built.originals.catalogue, selection: podiumSelection)?.title,
                       "Singapore Grand Prix: Driver Podium Finish")
        let winSelection = try XCTUnwrap(RacingOriginalsAdapter10868.selection(for: leclerc.win, in: built.originals))
        XCTAssertEqual(winSelection.identity, OriginalMarketDetails9483.Identity(source: "polymarket", market: "63989371", side: "241675154"))
        // A ref naming no held original names no selection — never a neighbour.
        XCTAssertNil(RacingOriginalsAdapter10868.selection(for: FieldChooserOriginalRef10868(
            scope: card.scope, source: "polymarket", marketID: "63989361", outcomeID: "1"), in: built.originals))
    }
}
