import XCTest
@testable import Bain_Luck

/// #6667 / #6444 — **a UFC card on Discover opens that fight card.**
///
/// Alex, physical phone, 2026-09-16: tapping a UFC card opened UFC-the-sport.
/// #6667 was filed believing the phone had nothing to call. It does:
/// `GET /api/event/{key}` is the endpoint the web's `/event/<domain>/<slug>`
/// page reads, and it answers JSON. The fixture below is that answer, byte for
/// byte, for the card Alex's own cached feed was carrying.
///
/// ## What these fixtures are, honestly
///
/// | file | what it is |
/// |---|---|
/// | `event-ufc-26sep19.20260917.json` | PRODUCTION, raw bytes, 2026-09-17 14:35Z, sha256 `b4393676…` |
/// | `event-ufc-404.20260917.json` | PRODUCTION, the 404 body for `event:ufc:26sep15` |
/// | `feed-concept-ufc-26sep19.HISTORICAL-20260916.json` | ONE item cut from a feed response saved 2026-09-16 (a day older than the page fixture — times differ, and that is the age showing) |
/// | `event-ufc-settled.SYNTHETIC.json` | **hand-made** from the production card; no settled card was obtainable |
/// | `event-ufc-events-only.SYNTHETIC.json` | **hand-made** to `_build_events_envelope`'s shape; invented fighters |
///
/// A synthetic fixture pins what THIS code does with a shape. It is not
/// evidence that production serves that shape.
final class AUFCCardOpensThatFightCard6667Tests: XCTestCase {

    // MARK: - Harness

    private static var testsDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    }

    private static func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: testsDir.appendingPathComponent("Fixtures").appendingPathComponent(name))
    }

    /// The app's own strategy (`APIClient.init`). Naming the fields IS the
    /// decode, so a test that decoded differently would prove nothing.
    private static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func card(_ name: String) throws -> ConceptCardPresentation {
        ConceptCardPresentation(
            response: try decoder.decode(EventConceptResponse.self, from: fixture(name)))
    }

    /// Same decode, from a literal body. For the labelled adversarial shapes —
    /// an unfought bout quoted 0.98, a graded underdog, an unrecognised
    /// `source` — that the production capture cannot supply and that a file in
    /// `Fixtures/` would only make harder to read beside its assertion.
    private static func card(json: String) throws -> ConceptCardPresentation {
        ConceptCardPresentation(
            response: try decoder.decode(EventConceptResponse.self, from: Data(json.utf8)))
    }

    /// Code only — comments stripped, so a doc comment that NAMES the old
    /// behaviour to explain why it is gone cannot satisfy or fail a scan.
    private static func code(of relativePath: String) throws -> String {
        let url = testsDir.deletingLastPathComponent().appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    // MARK: - Key encoding

    func testTheCanonicalKeyRoundTrips() {
        let key = ConceptKey("event:ufc:26sep19")
        XCTAssertEqual(key?.domain, "ufc")
        XCTAssertEqual(key?.slug, "26sep19")
        XCTAssertEqual(key?.canonical, "event:ufc:26sep19")
    }

    func testTheRequestPathPercentEncodesTheColonsLikeWebDoes() {
        XCTAssertEqual(ConceptKey("event:ufc:26sep19")?.apiPath, "/api/event/event%3Aufc%3A26sep19")
    }

    /// A slug is server-authored text. If one ever carries a `/`, `?` or `#`,
    /// the path must still be ONE segment addressed at the event route.
    func testASlugCannotBecomeADifferentURL() throws {
        let path = try XCTUnwrap(ConceptKey("event:ufc:a/b?c#d e")?.apiPath)
        XCTAssertEqual(path, "/api/event/event%3Aufc%3Aa%2Fb%3Fc%23d%20e")
        let url = try XCTUnwrap(URLComponents(string: "https://api.bainluck.com" + path))
        XCTAssertNil(url.query)
        XCTAssertNil(url.fragment)
    }

    func testTheWebsPrettySlugIsCarriedWhole() {
        // `event.slug` on the wire is "331-van-vs-pantoja-26sep19"; the server
        // resolves it to the same card by its date token.
        XCTAssertEqual(
            ConceptKey(domain: "ufc", slug: "331-van-vs-pantoja-26sep19")?.canonical,
            "event:ufc:331-van-vs-pantoja-26sep19")
    }

    func testTheDomainIsCaseFoldedAndTheSlugIsNot() {
        let key = ConceptKey("event:UFC:26Sep19")
        XCTAssertEqual(key?.domain, "ufc")
        XCTAssertEqual(key?.slug, "26Sep19")
    }

    /// Web reads a bare slug as golf. The phone refuses to guess.
    func testAKeyThePhoneCannotReadIsNotAKey() {
        for raw in ["", "   ", "26sep19", "event:", "event:ufc:", "event::26sep19", ":"] {
            XCTAssertNil(ConceptKey(raw), "'\(raw)' parsed as a concept key")
        }
        XCTAssertNil(ConceptKey(nil))
    }

    // MARK: - Card identity and navigation

    /// The feed item as the phone received it → the route the tap appends.
    func testTheFeedsOwnKeyIsTheKeyThatOpens() throws {
        struct Item: Decodable { let data: FeedConceptData }
        let item = try Self.decoder.decode(
            Item.self, from: Self.fixture("feed-concept-ufc-26sep19.HISTORICAL-20260916.json"))

        let route = ConceptCardRouting.destination(
            key: item.data.key, name: item.data.name, domain: item.data.domain)

        XCTAssertEqual(route, .conceptCard(key: "event:ufc:26sep19", name: "331: Van vs Pantoja"))
    }

    func testAUFCCardNeverOpensTheGenericSportPageWhenItKnowsItsKey() {
        let route = ConceptCardRouting.destination(key: "event:ufc:26sep19", name: "x", domain: "ufc")
        if case .sportCategory = route { XCTFail("a keyed UFC card opened the sport category — #6667") }
    }

    /// The card's page answers for the card's key: same card on both sides.
    func testThePageIsTheCardTheFeedNamed() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        XCTAssertEqual(card.key, "event:ufc:26sep19")
        XCTAssertEqual(card.name, "331: Van vs Pantoja")
        XCTAssertEqual(card.domain, "ufc")
        XCTAssertEqual(card.status, "upcoming")
    }

    /// Everything that is not a fight card keeps the destination it had.
    func testOtherConceptsAreUntouched() {
        XCTAssertEqual(
            ConceptCardRouting.destination(key: "event:golf:2026-masters", name: "Masters", domain: "golf"),
            .golfCategory)
        XCTAssertEqual(
            ConceptCardRouting.destination(key: "event:f1:british-grand-prix", name: "British GP", domain: "f1"),
            .sportCategory(key: "f1", name: properTitleCase("f1")))
        XCTAssertEqual(
            ConceptCardRouting.destination(key: "event:boxing:26oct10", name: "A vs B", domain: "boxing"),
            .sportCategory(key: "boxing", name: properTitleCase("boxing")),
            "boxing is the same adapter, and is deliberately not claimed until someone has looked at one")
    }

    /// A UFC card whose key cannot be read falls back to the category — better
    /// the generic page than a screen that can only say it failed (#1471's rule).
    func testAnUnreadableKeyFallsBackToTheCategory() {
        XCTAssertEqual(
            ConceptCardRouting.destination(key: "", name: "x", domain: "ufc"),
            .sportCategory(key: "ufc", name: properTitleCase("ufc")))
        XCTAssertNil(ConceptCardRouting.destination(key: "", name: "x", domain: nil))
    }

    // MARK: - Bouts

    func testEveryFightOnTheCardIsARowAndThePropIsNot() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        XCTAssertEqual(card.bouts.count, 12, "the wire carries 12 fights + 1 prop")
        XCTAssertFalse(card.bouts.contains { $0.title.contains("Round 3") })
    }

    /// The wire is ascending with the main event LAST; the phone leads with it.
    func testTheMainEventIsFirstAndIsTheOnlyOneMarked() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        XCTAssertEqual(card.bouts.first?.title, "331: Van vs Pantoja")
        XCTAssertEqual(card.bouts.first?.isMainEvent, true)
        XCTAssertEqual(card.bouts.filter(\.isMainEvent).count, 1)
        XCTAssertEqual(card.bouts.last?.title, "331: Aswell vs Yoo")
    }

    func testEachBoutCarriesBothFightersFavouriteFirstAtTheServedPrice() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        for bout in card.bouts {
            XCTAssertEqual(bout.fighters.count, 2, bout.title)
            XCTAssertGreaterThanOrEqual(
                bout.fighters[0].probability ?? -1, bout.fighters[1].probability ?? -1, bout.title)
        }
        let main = try XCTUnwrap(card.bouts.first)
        XCTAssertEqual(main.fighters.map(\.name), ["Joshua van", "Alexandre Pantoja"])
        XCTAssertEqual(main.fighters.map(\.probability), [0.565, 0.435])
    }

    /// Two-sided prices here are independent binaries and need not sum to 1
    /// (Gandra 0.815 + Diaz 0.175). The row prints what was served; it does
    /// not print a complement the server never sent.
    func testPricesAreNotComplemented() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        let bout = try XCTUnwrap(card.bouts.first { $0.title == "331: Gandra vs Diaz" })
        XCTAssertEqual(bout.fighters.map(\.probability), [0.815, 0.175])
    }

    func testBoutIdentityIsUniqueAndStable() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        XCTAssertEqual(Set(card.bouts.map(\.id)).count, card.bouts.count)
        XCTAssertEqual(card.bouts.first?.id, "60306288")
    }

    // MARK: - Bout navigation

    /// Venue-listed card: `market_id` is a futures market → the futures screen.
    /// (`GET /api/futures/60306288` measured 200 on 2026-09-17, and its
    /// `event_concept_key` points back at this card.)
    func testAVenueListedBoutOpensItsMarket() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        let main = try XCTUnwrap(card.bouts.first)
        XCTAssertEqual(main.target, .market(id: 60306288))
        XCTAssertEqual(ConceptCardRouting.route(for: main.target), .futuresDetail(id: 60306288))
    }

    /// Events-only card: the SAME field holds an Event primary key. Sending it
    /// to the futures screen would open an unrelated market or a 404.
    func testAnEventsOnlyBoutOpensItsEventAndNeverAMarket() throws {
        let card = try Self.card("event-ufc-events-only.SYNTHETIC.json")
        for bout in card.bouts {
            guard case .event(let id) = bout.target else {
                return XCTFail("\(bout.title): an events-table id was routed as \(bout.target)")
            }
            XCTAssertEqual(ConceptCardRouting.route(for: bout.target), .eventDetail(id: id))
        }
    }

    func testABoutWithNoIdIsNotALink() throws {
        let json = #"{"event":{"key":"event:ufc:x"},"children":[{"market_name":"A vs B","kind":"fight","outcomes":[{"name":"A","probability":0.6},{"name":"B","probability":0.4}]}]}"#
        let card = ConceptCardPresentation(
            response: try Self.decoder.decode(EventConceptResponse.self, from: Data(json.utf8)))
        XCTAssertEqual(card.bouts.first?.target, ConceptBoutRow.Target.none)
        XCTAssertNil(ConceptCardRouting.route(for: .none))
    }

    // MARK: - Missing prices

    func testAnUnpricedBoutKeepsBothNamesAndInventsNoNumber() throws {
        let card = try Self.card("event-ufc-events-only.SYNTHETIC.json")
        let bout = try XCTUnwrap(card.bouts.first { $0.title == "Cy Charlie vs Dee Delta" })
        XCTAssertEqual(bout.fighters.map(\.name), ["Cy Charlie", "Dee Delta"])
        XCTAssertEqual(bout.fighters.map(\.probability), [nil, nil])
        XCTAssertFalse(bout.isSettled)
    }

    /// No market id names the main event on an events-only card; the server's
    /// order does (last on the wire).
    func testAnEventsOnlyCardStillLeadsWithItsMainEvent() throws {
        let card = try Self.card("event-ufc-events-only.SYNTHETIC.json")
        XCTAssertEqual(card.bouts.first?.title, "Alan Alpha vs Bo Bravo")
        XCTAssertEqual(card.bouts.filter(\.isMainEvent).map(\.title), ["Alan Alpha vs Bo Bravo"])
    }

    // MARK: - Settled results

    /// A PRICE IS NOT A RESULT — this bout's 0.98 is the last number the market
    /// printed, and the payload carries no grade. The previous revision asserted
    /// `main.winner == "Joshua van"` here; the assertion, not the fixture, was
    /// the defect. Kept pointing at the same fixture so the change of verdict on
    /// identical bytes is visible in one diff.
    func testASettledBoutNamesNobodyWhenOnlyThePriceIsDecisive() throws {
        let card = try Self.card("event-ufc-settled.SYNTHETIC.json")
        XCTAssertEqual(card.status, "settled")
        let main = try XCTUnwrap(card.bouts.first)
        XCTAssertTrue(main.isSettled, "the card is over — the row still says Final")
        XCTAssertNil(
            main.winner,
            "0.98 is the last price, not a grade: the upset is exactly the case this would libel")
    }

    /// Settled by ASSIGNMENT with a price that never converged: the payload has
    /// no winner field, so the row says Final and names nobody.
    func testASettledBoutWithNoDecisivePriceNamesNobody() throws {
        let card = try Self.card("event-ufc-settled.SYNTHETIC.json")
        let bout = try XCTUnwrap(card.bouts.first { $0.title == "331: Shahbazyan vs Ferreira" })
        XCTAssertTrue(bout.isSettled)
        XCTAssertNil(bout.winner, "0.62 is a favourite, not a result")
    }

    /// The case web gets wrong: settled, both prices null. "Top-sorted" is just
    /// whoever was listed first.
    ///
    /// Inline rather than on the events-only fixture, which used to carry this
    /// bout as `settled: true` on an `upcoming` card. That payload is one the
    /// server cannot emit: with both prices null `price_converged` is false, so
    /// the only term left in `settled = price_converged OR card_settled` is the
    /// card's — and the card said it had not started. The fixture is now a
    /// coherent upcoming card and the settled case says `settled` where it means
    /// it.
    func testASettledBoutWithNoPricesNamesNobody() throws {
        let json = """
        {"event": {"key": "event:ufc:26oct03", "domain": "ufc", "status": "settled"},
         "children": [{"market_id": 9100002, "market_name": "Ed Echo vs Flo Foxtrot",
                       "source": "events", "kind": "fight", "settled": true,
                       "outcomes": [{"name": "Ed Echo", "probability": null},
                                    {"name": "Flo Foxtrot", "probability": null}]}]}
        """
        let card = try Self.card(json: json)
        let bout = try XCTUnwrap(card.bouts.first)
        XCTAssertTrue(bout.isSettled)
        XCTAssertNil(bout.winner)
    }

    /// ADVERSARIAL — the case the removed winner-floor got wrong, and the reason
    /// it is removed rather than tuned.
    ///
    /// `child.settled` is NOT "this bout happened": the producer ORs an assigned
    /// card state with a price inference. EXECUTED against the repo's own
    /// `backend/app/utils/event_combat.py` on 2026-09-17 —
    /// `fight_child_settled(0.98, card_settled=False) == True`. So this payload,
    /// an UPCOMING card whose favourite is quoted 0.98, is exactly what the
    /// server sends, and the old rule crowned a fighter who had not walked out.
    func testAnUpcomingCardNeverNamesAWinnerHoweverShortThePrice() throws {
        let json = """
        {"event": {"key": "event:ufc:26sep19", "domain": "ufc", "status": "upcoming"},
         "children": [{"market_id": 1, "market_name": "Alpha vs Bravo", "source": "kalshi",
                       "kind": "fight", "settled": true,
                       "outcomes": [{"name": "Alpha", "probability": 0.98},
                                    {"name": "Bravo", "probability": 0.02}]}]}
        """
        let card = try Self.card(json: json)
        let bout = try XCTUnwrap(card.bouts.first)
        XCTAssertEqual(card.status, "upcoming")
        XCTAssertNil(bout.winner, "the fight has not happened; 0.98 is a price")
        XCTAssertEqual(bout.fighters.first?.probability, 0.98, "and the price is still shown")

        // The half of that sentence the model could not keep on its own. The
        // view's price branch is `if bout.isSettled { … } else { price }`, so
        // while this row read settled the reader saw "Final" over two bare names
        // and NO price — on a fight nobody had walked out to. Asserting the
        // probability is CARRIED proves the model; asserting it is REACHABLE is
        // this line. See `ConceptCardPresentation.boutIsDecided`.
        XCTAssertFalse(
            bout.isSettled,
            "an upcoming card's converged price must not draw the bout as Final")
    }

    /// The other side of that rule, so it is a rule and not a switch: once the
    /// card's ASSIGNED status says it is under way, the price term decides again
    /// exactly as it did before. An early bout that really finishes mid-card
    /// still reads Final.
    func testALiveCardsConvergedBoutIsStillDrawnAsDecided() throws {
        let json = """
        {"event": {"key": "event:ufc:26sep19", "domain": "ufc", "status": "live"},
         "children": [{"market_id": 1, "market_name": "Alpha vs Bravo", "source": "kalshi",
                       "kind": "fight", "settled": true,
                       "outcomes": [{"name": "Alpha", "probability": 0.99},
                                    {"name": "Bravo", "probability": 0.01}]}]}
        """
        let bout = try XCTUnwrap(Self.card(json: json).bouts.first)
        XCTAssertTrue(bout.isSettled, "the card is under way — a converged bout has been fought")
        XCTAssertNil(bout.winner, "still no grade, so still nobody named")
    }

    /// The rule itself, over every status the combat adapter assigns plus the
    /// two shapes a payload can arrive missing it. Pinned directly so a later
    /// reader can see which way each case falls without decoding a card.
    func testOnlyAnUpcomingCardSuppressesThePriceInferredFinal() {
        typealias P = ConceptCardPresentation
        for status in ["upcoming", "UPCOMING", " upcoming "] {
            XCTAssertFalse(
                P.boutIsDecided(childSettled: true, cardStatus: status),
                "\(status.debugDescription): the card has not started")
        }
        for status in ["live", "settled"] {
            XCTAssertTrue(
                P.boutIsDecided(childSettled: true, cardStatus: status),
                "\(status): unchanged from before this rule")
        }
        // Unknown/absent stays permissive: this rule removes a false Final, it
        // does not take a real one away from a payload it cannot read.
        XCTAssertTrue(P.boutIsDecided(childSettled: true, cardStatus: nil))
        XCTAssertTrue(P.boutIsDecided(childSettled: true, cardStatus: "postponed"))
        // And it never MANUFACTURES one.
        for status in ["settled", "live", "upcoming", nil] {
            XCTAssertFalse(P.boutIsDecided(childSettled: false, cardStatus: status))
            XCTAssertFalse(P.boutIsDecided(childSettled: nil, cardStatus: status))
        }
    }

    /// The other half: an AUTHORITATIVE grade is honoured, both spellings. This
    /// is what keeps the nil above from being vacuous — the reader is not simply
    /// unreachable.
    func testAGradedWinnerIsNamed() throws {
        let graded = """
        {"event": {"key": "event:ufc:x", "status": "settled"},
         "children": [{"market_id": 1, "market_name": "A vs B", "source": "kalshi",
                       "kind": "fight", "settled": true, "graded_winner": "Bravo",
                       "outcomes": [{"name": "Alpha", "probability": 0.98},
                                    {"name": "Bravo", "probability": 0.02}]}]}
        """
        let won = """
        {"event": {"key": "event:ufc:x", "status": "settled"},
         "children": [{"market_id": 1, "market_name": "A vs B", "source": "kalshi",
                       "kind": "fight", "settled": true,
                       "outcomes": [{"name": "Alpha", "probability": 0.98, "won": false},
                                    {"name": "Bravo", "probability": 0.02, "won": true}]}]}
        """
        for (label, body) in [("graded_winner", graded), ("outcomes[].won", won)] {
            let card = try Self.card(json: body)
            XCTAssertEqual(
                card.bouts.first?.winner, "Bravo",
                "\(label): the underdog was GRADED the winner — the grade outranks the price")
        }
    }

    /// `market_id` holds two id spaces and `source` is the only discriminator, so
    /// an unrecognised source must refuse rather than open a stranger's page.
    func testAnUnknownSourceRefusesRatherThanGuessingAnIdSpace() throws {
        func target(source: String?) throws -> ConceptBoutRow.Target {
            let src = source.map { "\"\($0)\"" } ?? "null"
            let json = """
            {"event": {"key": "event:ufc:x"},
             "children": [{"market_id": 60306288, "market_name": "A vs B", "source": \(src),
                           "kind": "fight", "outcomes": [{"name": "A", "probability": 0.5}]}]}
            """
            let card = try Self.card(json: json)
            return try XCTUnwrap(card.bouts.first).target
        }
        XCTAssertEqual(try target(source: "kalshi"), .market(id: 60306288))
        XCTAssertEqual(try target(source: "polymarket"), .market(id: 60306288))
        XCTAssertEqual(try target(source: "events"), .event(id: 60306288))
        // The whole point: neither producer emits these, so nothing is known
        // about which id space the number belongs to.
        XCTAssertEqual(try target(source: nil), ConceptBoutRow.Target.none, "absent source is not a futures id")
        XCTAssertEqual(try target(source: "concept"), ConceptBoutRow.Target.none, "an unseen third writer")
        XCTAssertEqual(try target(source: "Events"), ConceptBoutRow.Target.none, "the match is exact, not fuzzy")
    }

    func testAnUnsettledBoutNeverCarriesAWinner() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        XCTAssertTrue(card.bouts.allSatisfy { $0.winner == nil && !$0.isSettled })
    }

    // MARK: - Unavailable content

    /// The production 404 body is not a card, and must fail to decode as one
    /// rather than decode as an empty card.
    func testA404BodyIsNotAnEmptyCard() throws {
        XCTAssertThrowsError(
            try Self.decoder.decode(EventConceptResponse.self, from: Self.fixture("event-ufc-404.20260917.json")))
    }

    func testA404IsGoneAndNothingElseIs() {
        XCTAssertEqual(ConceptCardFailure.classify(httpStatus: 404, hasLoadedScreen: false), .gone)
        XCTAssertEqual(
            ConceptCardFailure.classify(httpStatus: 404, hasLoadedScreen: true), .gone,
            "a refused card must not keep showing prices the server no longer stands behind (#6733)")
        for status in [nil, 500, 502, 503, 429, 401] as [Int?] {
            XCTAssertEqual(ConceptCardFailure.classify(httpStatus: status, hasLoadedScreen: false), .retryable)
            XCTAssertEqual(ConceptCardFailure.classify(httpStatus: status, hasLoadedScreen: true), .keepShowing)
        }
    }

    func testOneMalformedBoutDoesNotBlankTheCard() throws {
        let json = #"{"event":{"key":"event:ufc:x","name":"X"},"children":[{"market_id":"not-a-number","kind":"fight"},{"market_id":7,"market_name":"A vs B","kind":"fight","outcomes":[{"name":"A","probability":0.6},{"name":"B","probability":0.4}]}]}"#
        let card = ConceptCardPresentation(
            response: try Self.decoder.decode(EventConceptResponse.self, from: Data(json.utf8)))
        XCTAssertEqual(card.bouts.map(\.title), ["A vs B"])
    }

    func testACardWithNoChildrenStillOpens() throws {
        let json = #"{"event":{"key":"event:ufc:x","name":"X","status":"upcoming"}}"#
        let card = ConceptCardPresentation(
            response: try Self.decoder.decode(EventConceptResponse.self, from: Data(json.utf8)))
        XCTAssertEqual(card.name, "X")
        XCTAssertTrue(card.bouts.isEmpty)
    }

    // MARK: - The wiring (source scans — they pin text, not behaviour)

    func testTheCardAsksTheRoutingRuleAndNoLongerHardcodesTheCategory() throws {
        let code = try Self.code(of: "Bain Luck/Components/DiscoverConceptCard.swift")
        XCTAssertTrue(code.contains("ConceptCardRouting.destination("))
        XCTAssertFalse(
            code.contains("Route.sportCategory("),
            "the concept card is appending the sport category itself again — that line IS #6667")
    }

    /// The guard for the CLASS, not just the instance: no price threshold decides
    /// a result in the client, ever. A floor is a one-line "convenience" to
    /// re-add and it reads as harmless right up until it libels the loser of an
    /// upset, so the thing that stops it is a scan, not a memory.
    ///
    /// NOT vacuous, and the comment-stripping in `code(of:)` is what makes it
    /// honest: `ConceptCardModels.swift` mentions `0.97` four times — all of them
    /// in the doc comments that explain why the constant is gone — and zero times
    /// in code. Strip nothing and this assertion could never fail.
    func testNoPriceThresholdEverDecidesAResultInTheClient() throws {
        let models = try Self.code(of: "Bain Luck/Models/ConceptCardModels.swift")
        XCTAssertFalse(models.contains("winnerFloor"), "the winner floor is back")
        XCTAssertFalse(models.contains("0.97"), "a convergence constant is back in the client")
        XCTAssertTrue(
            models.contains("$0.won == true"),
            "the winner must come from the server's grade, not a number")
    }

    func testTheRouteTableBuildsTheScreenFromTheKey() throws {
        let code = try Self.code(of: "Bain Luck/Views/Route.swift")
        XCTAssertTrue(code.contains("case .conceptCard(let key, let name): ConceptCardView(key: key"))
    }

    func testTheClientAsksTheEndpointTheWebPageReads() throws {
        let code = try Self.code(of: "Bain Luck/Services/APIClient.swift")
        XCTAssertTrue(code.contains("func fetchEventConcept(key: String)"))
        XCTAssertTrue(code.contains("fetch(parsed.apiPath"))
        let models = try Self.code(of: "Bain Luck/Models/ConceptCardModels.swift")
        XCTAssertTrue(models.contains("\"/api/event/\\(encoded)\""))
    }

    /// Return-to-feed: the card pushes a VALUE onto Discover's own path, which
    /// is the mechanism every other Discover card uses and the one
    /// `AReaderCanOpenACardAndComeBackTests` walks. A sheet, a tab switch or a
    /// second NavigationStack here is what would lose the reader's place.
    func testTheTapPushesOntoDiscoversOwnStackAndBoutsAreValueLinks() throws {
        let card = try Self.code(of: "Bain Luck/Components/DiscoverConceptCard.swift")
        XCTAssertTrue(card.contains("navigationPath.append(route)"))
        let view = try Self.code(of: "Bain Luck/Views/ConceptCardView.swift")
        XCTAssertTrue(view.contains("NavigationLink(value: route)"))
        for forbidden in ["NavigationStack", ".sheet(", ".fullScreenCover(", "selectedTab"] {
            XCTAssertFalse(view.contains(forbidden), "ConceptCardView contains \(forbidden)")
        }
    }

    func testTheUnavailableScreenOffersNoRetry() throws {
        let view = try Self.code(of: "Bain Luck/Views/ConceptCardView.swift")
        let start = try XCTUnwrap(view.range(of: "var unavailableState"))
        let end = try XCTUnwrap(view.range(of: "func errorState"))
        XCTAssertFalse(view[start.upperBound..<end.lowerBound].contains("Retry"))
        XCTAssertTrue(view[end.upperBound...].contains("Button(\"Retry\")"))
    }

    // MARK: - Needs the app (compiled only where SwiftUI exists)

    #if canImport(SwiftUI)
    func testAFailureBecomesTheRightScreen() {
        typealias VM = ConceptCardViewModel
        let gone = APIError.httpError(statusCode: 404, body: nil)
        let down = APIError.httpError(statusCode: 503, body: nil)
        XCTAssertEqual(VM.state(after: gone, current: .loading), .unavailable)
        if case .error = VM.state(after: down, current: .loading) {} else { XCTFail("503 over nothing must offer Retry") }
    }

    @MainActor
    func testTheWebsEventURLOpensTheFightCard() {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(URL(string: "bainluck://event/ufc/26sep19")!))
        XCTAssertTrue(nav.handleURL(URL(string: "https://bainluck.com/event/ufc/331-van-vs-pantoja-26sep19")!))
        XCTAssertFalse(nav.handleURL(URL(string: "bainluck://event/golf/2026-masters")!), "not a fight card; unclaimed, as before")
        XCTAssertFalse(nav.handleURL(URL(string: "bainluck://event/ufc")!))
    }
    #endif
}
