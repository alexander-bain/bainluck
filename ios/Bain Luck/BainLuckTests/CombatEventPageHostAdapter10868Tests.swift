import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's host glue (`CombatEventPageHost10868`):
/// its pure `build` from the values the page already holds, on the REAL
/// retained bodies — the UFC 332 and boxing details
/// (`CombatBoutPageAdapter10868Tests`, byte for byte), the UFC 332 history and
/// `/game-markets` (`CombatHistoryAdapter10868Tests`,
/// `CombatOriginalsAdapter10868Tests`, reduced verbatim subsets). Source paths,
/// sha256 and what each subset kept are written in those files.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here: the reader's calendar and `now`; the interrupted delivery
/// flag; a story `Membership` (no production owner supplies one — the proposed
/// mount passes none); the held reading state. The card-Details controls below
/// also edit the retained `/game-markets` subset, each naming exactly what it
/// changes: raw `other` rows removed or duplicated by their own contributor id,
/// one matrix option's `contributor_outcome_ids` / `market_ids`, one raw row's
/// `contributor_outcome_ids`, or `totals` and `other` emptied.
@MainActor
final class CombatEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Host = CombatEventPageHost10868
    private typealias Fixtures = CombatBoutPageAdapter10868Tests
    private typealias Details = OriginalMarketDetails9483

    private func build(_ event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                       interrupted: Bool = false, membership: CombatStoryAdapter10868.Membership? = nil,
                       reading: Host.Reading = Host.Reading()) -> Host.Built {
        Host.build(event: event, history: history, markets: markets,
                   probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, deliveryInterrupted: interrupted,
                   now: Fixtures.readAt.asDate!, membership: membership, reading: reading,
                   calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    /// CONSTRUCTED owner proof, naming served question keys.
    private let membership = CombatStoryAdapter10868.Membership(
        methods: [.init(id: "ko", label: "KO / TKO", questionKey: "m:63786874")],
        knockout: [.init(id: "kopylov", label: "Roman Kopylov", questionKey: "m:63900810")])

    // MARK: - The retained bout

    func testTheRetainedBoutComposesFromItsThreeBodiesWithNoStoryStream() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let history = try CombatHistoryAdapter10868Tests.response()
        let built = build(event, history: history, markets: try CombatOriginalsAdapter10868Tests.markets())
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertEqual(built.input.history, CombatHistoryAdapter10868.history(
            history, event: event, phase: .during,
            host: CombatHistoryAdapter10868.Host(now: Fixtures.readAt.asDate!, calendar: Fixtures.pacific,
                                                 locale: Fixtures.locale)))
        XCTAssertEqual(built.input.history.series[0].runs.count, 1)
        XCTAssertEqual(built.originals.catalogue?.originals.count, 31)
        XCTAssertEqual(built.input.copy.allPropsLabel, "All 31 original props")
        XCTAssertNil(built.input.stream, "no production membership, no stories")
        XCTAssertNil(built.input.methods)
        XCTAssertNil(built.input.rounds)
        XCTAssertNil(built.input.knockout)
        XCTAssertNil(built.input.duration)
        XCTAssertNil(built.input.notice)
    }

    func testWithoutAHistoryResponseOnlyTheChartSlotIsUnavailable() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets()
        let withHistory = build(event, history: try CombatHistoryAdapter10868Tests.response(), markets: markets)
        let without = build(event, history: nil, markets: markets)
        XCTAssertEqual(without.input.history.plotAbsence?.title, "History unavailable")
        XCTAssertNil(without.input.history.expand)
        XCTAssertEqual(without.input.headline, withHistory.input.headline)
        XCTAssertEqual(without.input.about, withHistory.input.about)
        XCTAssertEqual(without.originals.catalogue, withHistory.originals.catalogue)
    }

    /// CONSTRUCTED: the retained history and markets with only `event_id`
    /// changed to a different event's id. Neither part reaches the page; the
    /// bout's own headline and About still compose, and each own-id body still counts.
    func testAnotherEventsHistoryAndMarketsNeverReachThisBout() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let own = build(event, history: try CombatHistoryAdapter10868Tests.response(),
                        markets: try CombatOriginalsAdapter10868Tests.markets())
        var markets = try CombatOriginalsAdapter10868Tests.object(CombatOriginalsAdapter10868Tests.mmaMarkets)
        markets["event_id"] = 15318682
        let foreignMarkets = try Fixtures.decoder().decode(GameMarketsResponse.self,
                                                          from: JSONSerialization.data(withJSONObject: markets))
        let foreign = build(event, history: try CombatHistoryAdapter10868Tests.response(eventId: 15318682),
                            markets: foreignMarkets)
        XCTAssertEqual(foreign.input.history, CombatHistoryAdapter10868.unavailable(event: event, phase: .during))
        XCTAssertNil(foreign.originals.catalogue)
        XCTAssertNil(foreign.input.copy.allPropsLabel)
        XCTAssertEqual(foreign.input.headline, own.input.headline)
        XCTAssertEqual(foreign.input.about, own.input.about)
        // Only the foreign part is refused: own history with foreign markets keeps the chart.
        let mixed = build(event, history: try CombatHistoryAdapter10868Tests.response(), markets: foreignMarkets)
        XCTAssertEqual(mixed.input.history, own.input.history)
        XCTAssertNil(mixed.originals.catalogue)
    }

    func testTheRetainedBoxingBoutUsesTheSameScreenWithNothingInAllProps() throws {
        let event = try Fixtures.detail(Fixtures.boxingDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets(Fixtures.boxingMarkets)
        let built = build(event, history: nil, markets: markets)
        XCTAssertTrue(Host.applies(event))
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertEqual(built.input.headline.displayed.map(\.name), ["Ryusei Matsumoto", "Russell Acosta"])
        XCTAssertNil(built.originals.catalogue)
        XCTAssertNil(built.input.copy.allPropsLabel)
        XCTAssertEqual(built.originals.emptyWords, "No retained originals for this fight")
        XCTAssertEqual(built.input.history.plotAbsence?.title, "History unavailable", "no boxing history body is retained")
    }

    // MARK: - Stories (constructed membership)

    func testAProvedMembershipOffersItsStoriesAndTheHeldStoryIsShown() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets()
        let built = build(event, history: nil, markets: markets, membership: membership,
                          reading: Host.Reading(story: .knockout))
        let stream = try XCTUnwrap(built.input.stream)
        XCTAssertEqual(stream.cards.map(\.id), ["methods", "knockout"])
        XCTAssertEqual(stream.primary?.id, "knockout")
        XCTAssertEqual(stream.scope, "combat:15318681:during")
        XCTAssertEqual(built.input.stories.map(\.card), [.methods, .knockout])
        XCTAssertNotNil(built.input.methods)
        XCTAssertNotNil(built.input.knockout)
        XCTAssertNil(built.input.rounds)
        XCTAssertNil(built.input.duration)
    }

    // MARK: - Details from a card

    func testACardsDetailsOpenOnlyTheExactCatalogueOriginal() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try CombatOriginalsAdapter10868Tests.markets(),
                          membership: membership)
        let side = try XCTUnwrap(built.input.methods?.methods.first?.originals.first)
        XCTAssertEqual(side.id, "240262496")
        XCTAssertEqual(side.marketID, "63786874")
        XCTAssertEqual(Host.detailsSelection(marketID: side.marketID, originalID: side.id, in: built.originals),
                       Details.Selection(scope: "combat:15318681:during:originals",
                                         identity: Details.Identity(source: "polymarket", market: "63786874",
                                                                    side: "240262496")))
        XCTAssertNil(Host.detailsSelection(marketID: "63786874", originalID: "240654996", in: built.originals),
                     "another market's side is never opened in its place")

        let boxing = build(try Fixtures.detail(Fixtures.boxingDetail), history: nil, markets: nil)
        XCTAssertNil(Host.detailsSelection(marketID: side.marketID, originalID: side.id, in: boxing.originals))
    }

    // MARK: - Purity

    func testBuildIsPureSoEveryChangedValueReachesTheNextPass() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets()
        let history = try CombatHistoryAdapter10868Tests.response()
        XCTAssertEqual(build(event, history: history, markets: markets).input,
                       build(event, history: history, markets: markets).input)
        let interrupted = build(event, history: history, markets: markets, interrupted: true)
        XCTAssertEqual(interrupted.input.notice, "Update interrupted · showing the last recorded chances")
        XCTAssertFalse(Host.applies(try Fixtures.edited(Fixtures.mmaDetail, ["sport": "icehockey_nhl"])))
    }

    // MARK: - A story card's Details availability (CONSTRUCTED controls)

    /// CONSTRUCTED owner proof for all four cards, naming served question keys.
    private let allFour = CombatStoryAdapter10868.Membership(
        methods: [.init(id: "ko", label: "KO / TKO", questionKey: "m:63786874")],
        knockout: [.init(id: "kopylov", label: "Roman Kopylov", questionKey: "m:63900810")],
        rounds: [.init(id: "gautier", label: "Ateba Gautier", slots: [
            .init(id: "gautier-1", label: "Round 1", questionKey: "m:63786882"),
        ])],
        duration: .init(segments: [
            CombatDurationSegment10868(id: "r1", shortLabel: "R1", spokenLabel: "Round 1"),
            CombatDurationSegment10868(id: "r2", shortLabel: "R2", spokenLabel: "Round 2"),
            CombatDurationSegment10868(id: "r3", shortLabel: "R3", spokenLabel: "Round 3"),
        ], markets: [.init(id: "distance", label: "Go the distance", questionKey: "m:63254894", windows: [:])]))

    /// The chosen originals (served ids) and a still-routed neighbour on each card.
    private enum Chosen {
        static let koYes = 240262496, koNo = 240262497            // m:63786874, other[6] / other[7]
        static let kopylovYes = 240654996, kopylovNo = 240654997  // m:63900810, other[8] / other[9]
        static let roundNo = 240262513, roundYes = 240262512      // m:63786882, other[26] / other[27]
        static let distanceYes = 238409896, distanceNo = 238409897 // m:63254894, other[25] / other[24]
    }

    private func reading(methods: Int?, knockout: Int?, rounds: Int?, duration: Int?,
                         story: CombatEventPageCard10868? = nil, readerOpen: Bool = false) -> Host.Reading {
        Host.Reading(
            story: story,
            methods: .init(rowID: methods.map { _ in "ko" }, originalID: methods.map(String.init)),
            rounds: .init(rowID: rounds.map { _ in "gautier-1" }, originalID: rounds.map(String.init)),
            knockout: .init(rowID: knockout.map { _ in "kopylov" }, originalID: knockout.map(String.init)),
            duration: .init(rowID: duration.map { _ in "distance" }, originalID: duration.map(String.init)),
            readerOpen: readerOpen)
    }

    private var chosen: Host.Reading {
        reading(methods: Chosen.koYes, knockout: Chosen.kopylovYes, rounds: Chosen.roundNo, duration: Chosen.distanceYes)
    }

    private var neighbours: Host.Reading {
        reading(methods: Chosen.koNo, knockout: Chosen.kopylovNo, rounds: Chosen.roundYes, duration: Chosen.distanceNo)
    }

    /// The retained markets subset as a JSON object, for the edits below.
    private func body() throws -> [String: Any] {
        try CombatOriginalsAdapter10868Tests.object(CombatOriginalsAdapter10868Tests.mmaMarkets)
    }

    /// CONSTRUCTED: raw `other` rows removed (and/or repeated once) by their
    /// own single contributor id. The matrix is untouched.
    private func rows(_ body: inout [String: Any], removing removed: Set<Int> = [], duplicating repeated: Set<Int> = []) throws {
        let rows = try XCTUnwrap(body["other"] as? [[String: Any]])
        var kept: [[String: Any]] = []
        for row in rows {
            let ids = (row["contributor_outcome_ids"] as? [Int]) ?? []
            if ids.count == 1, removed.contains(ids[0]) { continue }
            kept.append(row)
            if ids.count == 1, repeated.contains(ids[0]) { kept.append(row) }
        }
        body["other"] = kept
    }

    /// CONSTRUCTED: the named keys of one matrix option.
    private func option(_ body: inout [String: Any], question: String, option: String, _ setting: [String: Any]) throws {
        var matrix = try XCTUnwrap(body["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let q = try XCTUnwrap(questions.firstIndex { ($0["question_key"] as? String) == question })
        var options = try XCTUnwrap(questions[q]["options"] as? [[String: Any]])
        let o = try XCTUnwrap(options.firstIndex { ($0["option_key"] as? String) == option })
        for (key, value) in setting { options[o][key] = value }
        questions[q]["options"] = options
        matrix["questions"] = questions
        body["game_question_matrix"] = matrix
    }

    private func markets(_ body: [String: Any]) throws -> GameMarketsResponse {
        try CombatOriginalsAdapter10868Tests.decoded(body)
    }

    private func fourCards(_ built: Host.Built, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertNotNil(built.input.methods, file: file, line: line)
        XCTAssertNotNil(built.input.knockout, file: file, line: line)
        XCTAssertNotNil(built.input.rounds, file: file, line: line)
        XCTAssertNotNil(built.input.duration, file: file, line: line)
    }

    private func route(_ market: String, _ side: Int) -> Details.Selection {
        Details.Selection(scope: "combat:15318681:during:originals",
                          identity: Details.Identity(source: "polymarket", market: market, side: String(side)))
    }

    /// Each card's own selected Details ref, as its leaf would send it with a callback.
    private struct LeafRefs {
        var methods: CombatMethodOriginalRef10868?
        var rounds: CombatRoundOriginalRef10868?
        var knockout: CombatMethodOriginalRef10868?
        var duration: CombatDurationOriginalRef10868?
    }

    private func leafRefs(_ built: Host.Built) -> LeafRefs {
        let model = CombatEventPageModel10868(built.input)
        var refs = LeafRefs()
        if case .details(let ref)? = model.methods?.detailsAction(canOpenDetails: true) { refs.methods = ref }
        if case .details(let ref)? = model.rounds?.detailsAction(canOpenDetails: true) { refs.rounds = ref }
        if case .details(let ref)? = model.knockout?.detailsAction(canOpenDetails: true) { refs.knockout = ref }
        if case .details(let ref)? = model.duration?.detailsAction(canOpenDetails: true) { refs.duration = ref }
        return refs
    }

    private let noRoutes = Host.DetailsRoutes(methods: nil, rounds: nil, knockout: nil, duration: nil)

    func testTheRetainedBodyRoutesEachCardsSelectedOriginalToExactlyOneCatalogueOriginal() throws {
        // Control: the retained subset, unedited.
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(body()), membership: allFour, reading: chosen)
        fourCards(built)
        XCTAssertEqual(Host.detailsRoutes(built), Host.DetailsRoutes(
            methods: route("63786874", Chosen.koYes), rounds: route("63786882", Chosen.roundNo),
            knockout: route("63900810", Chosen.kopylovYes), duration: route("63254894", Chosen.distanceYes)))
    }

    func testAWithdrawnRawRowLeavesItsMatrixOriginalSelectedButOffersNoDetailsOnAnyCard() throws {
        // CONSTRUCTED: only the four chosen originals' raw `other` rows removed;
        // their matrix options stay.
        var edited = try body()
        try rows(&edited, removing: [Chosen.koYes, Chosen.kopylovYes, Chosen.roundNo, Chosen.distanceYes])
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(edited), membership: allFour, reading: chosen)

        fourCards(built)
        XCTAssertEqual(built.originals.catalogue?.originals.count, 27, "only the four withdrawn rows leave All props")
        let model = CombatEventPageModel10868(built.input)
        XCTAssertEqual(model.methods?.selection.original?.id, String(Chosen.koYes), "selection identity is kept")
        XCTAssertEqual(model.knockout?.selection.original?.id, String(Chosen.kopylovYes))
        XCTAssertEqual(model.rounds?.selection.original?.id, String(Chosen.roundNo))
        XCTAssertEqual(model.duration?.selection.original?.id, String(Chosen.distanceYes))
        XCTAssertEqual(model.methods?.methods.first?.originals.map(\.id), [String(Chosen.koYes), String(Chosen.koNo)],
                       "every original stays listed")
        let refs = leafRefs(built)
        XCTAssertNotNil(refs.methods, "the leaf alone would offer Details here: the dead control this guards")
        XCTAssertNotNil(refs.rounds)
        XCTAssertNotNil(refs.knockout)
        XCTAssertNotNil(refs.duration)

        XCTAssertEqual(Host.detailsRoutes(built), noRoutes)
        var opened: [Details.Selection] = []
        let callbacks = Host.detailsCallbacks(built) { opened.append($0) }
        XCTAssertNil(callbacks.methods)
        XCTAssertNil(callbacks.rounds)
        XCTAssertNil(callbacks.knockout)
        XCTAssertNil(callbacks.duration)
        XCTAssertTrue(opened.isEmpty)
    }

    func testAStillRoutedNeighbourKeepsAWorkingDetailsThatOpensExactlyItself() throws {
        // CONSTRUCTED: the same four raw rows removed; each card now holds its neighbour.
        var edited = try body()
        try rows(&edited, removing: [Chosen.koYes, Chosen.kopylovYes, Chosen.roundNo, Chosen.distanceYes])
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(edited), membership: allFour, reading: neighbours)
        fourCards(built)
        let expected = Host.DetailsRoutes(
            methods: route("63786874", Chosen.koNo), rounds: route("63786882", Chosen.roundYes),
            knockout: route("63900810", Chosen.kopylovNo), duration: route("63254894", Chosen.distanceNo))
        XCTAssertEqual(Host.detailsRoutes(built), expected)

        var opened: [Details.Selection] = []
        let callbacks = Host.detailsCallbacks(built) { opened.append($0) }
        let refs = leafRefs(built)
        callbacks.methods?(try XCTUnwrap(refs.methods))
        callbacks.rounds?(try XCTUnwrap(refs.rounds))
        callbacks.knockout?(try XCTUnwrap(refs.knockout))
        callbacks.duration?(try XCTUnwrap(refs.duration))
        XCTAssertEqual(opened, [expected.methods, expected.rounds, expected.knockout, expected.duration].compactMap { $0 })

        // The working callback never opens the withdrawn side in its place.
        opened = []
        let withdrawn = CombatMethodOriginalRef10868(eventID: "15318681", methodID: "ko", marketID: "63786874",
                                                     originalID: String(Chosen.koYes))
        callbacks.methods?(withdrawn)
        XCTAssertTrue(opened.isEmpty)
    }

    func testNoSelectionOffersNoCardDetailsAndKeepsEveryCard() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(body()), membership: allFour)
        fourCards(built)
        XCTAssertEqual(Host.detailsRoutes(built), noRoutes)
        let callbacks = Host.detailsCallbacks(built) { _ in XCTFail("nothing is selected") }
        XCTAssertNil(callbacks.methods)
        XCTAssertNil(callbacks.rounds)
        XCTAssertNil(callbacks.knockout)
        XCTAssertNil(callbacks.duration)
    }

    func testADuplicatedRawRowIsNotOneCatalogueOriginalAndOtherCardsKeepTheirs() throws {
        // CONSTRUCTED: the KO Yes raw `other` row served twice.
        var edited = try body()
        try rows(&edited, duplicating: [Chosen.koYes])
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(edited), membership: allFour, reading: chosen)
        fourCards(built)
        XCTAssertEqual(built.originals.catalogue?.originals.filter { $0.identity.side == String(Chosen.koYes) }.count, 2)
        XCTAssertEqual(Host.detailsRoutes(built), Host.DetailsRoutes(
            methods: nil, rounds: route("63786882", Chosen.roundNo),
            knockout: route("63900810", Chosen.kopylovYes), duration: route("63254894", Chosen.distanceYes)))
        XCTAssertNil(Host.detailsCallbacks(built) { _ in }.methods)
    }

    func testACompositeRefIsNeverOneProviderOriginal() throws {
        // CONSTRUCTED: option o:240262496 and its raw row both carry two
        // contributor ids, so the catalogue does hold the same composite side.
        var edited = try body()
        try option(&edited, question: "m:63786874", option: "o:240262496",
                   ["contributor_outcome_ids": [Chosen.koYes, Chosen.koNo]])
        var others = try XCTUnwrap(edited["other"] as? [[String: Any]])
        let row = try XCTUnwrap(others.firstIndex { ($0["contributor_outcome_ids"] as? [Int]) == [Chosen.koYes] })
        others[row]["contributor_outcome_ids"] = [Chosen.koYes, Chosen.koNo]
        edited["other"] = others
        let composite = "\(Chosen.koYes)+\(Chosen.koNo)"
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(edited), membership: allFour,
                          reading: Host.Reading(methods: .init(rowID: "ko", originalID: composite)))
        XCTAssertEqual(CombatEventPageModel10868(built.input).methods?.selection.original?.id, composite)
        XCTAssertTrue(built.originals.catalogue?.originals.contains { $0.identity.side == composite } ?? false)
        XCTAssertNil(Host.detailsRoutes(built).methods)
        XCTAssertNil(Host.detailsSelection(marketID: "63786874", originalID: composite, in: built.originals))

        // CONSTRUCTED: option o:240262497 names two markets.
        var twoMarkets = try body()
        try option(&twoMarkets, question: "m:63786874", option: "o:240262497", ["market_ids": [63786874, 63786875]])
        let split = build(event, history: nil, markets: try markets(twoMarkets), membership: allFour,
                          reading: Host.Reading(methods: .init(rowID: "ko", originalID: String(Chosen.koNo))))
        XCTAssertEqual(leafRefs(split).methods?.marketID, "63786874+63786875")
        XCTAssertNil(Host.detailsRoutes(split).methods)
    }

    func testARefWhoseMarketTheCatalogueDoesNotCarryForThatSideIsUnrouted() throws {
        // CONSTRUCTED: option o:240262496's `market_ids` names another served market.
        var edited = try body()
        try option(&edited, question: "m:63786874", option: "o:240262496", ["market_ids": [63900810]])
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(edited), membership: allFour, reading: chosen)
        XCTAssertEqual(leafRefs(built).methods?.marketID, "63900810")
        XCTAssertNil(Host.detailsRoutes(built).methods, "the side is never borrowed from its own market")
        XCTAssertNotNil(Host.detailsSelection(marketID: "63786874", originalID: String(Chosen.koYes), in: built.originals))
        XCTAssertEqual(Host.detailsRoutes(built).rounds, route("63786882", Chosen.roundNo))
    }

    func testAMissingCatalogueOffersNoCardDetailsWhileEveryCardAndSelectionStays() throws {
        // CONSTRUCTED: `totals` and `other` emptied; the matrix is untouched.
        var edited = try body()
        edited["totals"] = [[String: Any]]()
        edited["other"] = [[String: Any]]()
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try markets(edited), membership: allFour, reading: chosen)
        fourCards(built)
        XCTAssertNil(built.originals.catalogue)
        XCTAssertEqual(CombatEventPageModel10868(built.input).methods?.selection.original?.id, String(Chosen.koYes))
        XCTAssertEqual(Host.detailsRoutes(built), noRoutes)

        // No markets at all: no matrix, so no card and nothing to route.
        let none = build(event, history: nil, markets: nil, membership: allFour, reading: chosen)
        XCTAssertNil(none.input.methods)
        XCTAssertEqual(Host.detailsRoutes(none), noRoutes)
    }

    func testThePageAndTheFullReaderOfferTheSameDetailsAndAskForOneHoldAtMost() throws {
        // CONSTRUCTED: the KO Yes raw row removed; methods holds KO Yes (unrouted),
        // rounds holds Round 1 No (routed).
        var edited = try body()
        try rows(&edited, removing: [Chosen.koYes])
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try markets(edited)
        let pick = reading(methods: Chosen.koYes, knockout: nil, rounds: Chosen.roundNo, duration: nil, story: .rounds)
        let onPage = build(event, history: nil, markets: markets, membership: allFour, reading: pick)
        var open = pick
        open.readerOpen = true
        let inReader = build(event, history: nil, markets: markets, membership: allFour, reading: open)
        XCTAssertEqual(Host.detailsRoutes(onPage), Host.detailsRoutes(inReader))
        XCTAssertNil(Host.detailsRoutes(onPage).methods)
        XCTAssertEqual(Host.detailsRoutes(onPage).rounds, route("63786882", Chosen.roundNo))

        var log: [String] = []
        func presentation(_ built: Host.Built, _ mode: CombatEventPageMode10868) -> CombatEventPagePresentation10868 {
            let details = Host.detailsCallbacks(built) { log.append("open:\($0.identity.side)") }
            return CombatEventPagePresentation10868(
                input: built.input, mode: mode, originals: built.originals,
                onMethodDetails: details.methods, onRoundDetails: details.rounds,
                onKnockoutDetails: details.knockout, onDurationDetails: details.duration,
                onInteraction: { log.append("pageHold") })
        }
        let scope = try XCTUnwrap(onPage.input.stream?.scope)
        func activation(_ card: CombatEventPageCard10868) -> StoryStreamCardActivation10868 {
            let ref = StoryStreamPresentation10868.CardRef(scope: scope, id: card.rawValue)
            return StoryStreamCardActivation10868(card: ref, intents: [.interaction(scope: scope, card: ref)]) { _ in
                log.append("streamHold")
            }
        }

        // Page: cards sit in the stream, so a Details tap asks the stream's hold once.
        let page = presentation(onPage, .page)
        XCTAssertNil(page.methodsContent(activation: activation(.methods))?.onDetails)
        let pageRounds = try XCTUnwrap(page.roundsContent(activation: activation(.rounds)))
        let roundRef = try XCTUnwrap(leafRefs(onPage).rounds)
        try XCTUnwrap(pageRounds.onDetails)(roundRef)
        XCTAssertEqual(log, ["streamHold", "open:\(Chosen.roundNo)"])

        // Full reader: the same availability, the exact callback, no second hold.
        log = []
        XCTAssertNil(presentation(inReader, .reader(.methods)).methodsContent()?.onDetails)
        let readerRounds = try XCTUnwrap(presentation(inReader, .reader(.rounds)).roundsContent())
        try XCTUnwrap(readerRounds.onDetails)(roundRef)
        XCTAssertEqual(log, ["open:\(Chosen.roundNo)"])

        // And so neither surface draws an enabled Details for the unrouted original.
        let methodsLeaf = try XCTUnwrap(presentation(inReader, .reader(.methods)).methodsContent())
        XCTAssertNil(methodsLeaf.input.detailsAction(canOpenDetails: methodsLeaf.onDetails != nil))
    }
}
