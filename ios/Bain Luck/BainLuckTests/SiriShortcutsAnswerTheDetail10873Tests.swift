import XCTest
@testable import Bain_Luck

/// #10873 — Siri / Shortcuts: Open My Stuff, Open a game or market, Get probability.
///
/// What these pin, in the issue's acceptance order:
///  - IDENTITY: an entity's identifier is its canonical id, round-trips, and an
///    outcome saved with one game can never answer for another.
///  - AMBIGUITY: search hands back every match with what tells two same-named
///    rows apart, and an outcome is never taken for the reader when there is
///    more than one.
///  - THE ANSWER IS THE DETAIL'S: the same branch order and the same numbers as
///    the event hero and the market page — settled answers with a result, a
///    draw-priced away side is withheld, an undated or stale price is never
///    "current", and offline is not "no data".
///  - OPEN: an intent can open only the three links the router already routes,
///    and a delivered link is cleared so a remount cannot replay it.
///
/// These are unit tests of the source. They do not show Siri registration, a
/// real phrase, or a real iPhone: Native's whole-app build and device journeys
/// own that.
@MainActor
final class SiriShortcutsAnswerTheDetail10873Tests: XCTestCase {

    // A fixed clock (gotcha #44): every stamp below is relative to this.
    private let now = ISO8601DateFormatter().date(from: "2026-10-16T18:00:00Z")!

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func event(_ fields: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data("""
        {"id":15320337,"home_team":"New York Yankees","away_team":"Boston Red Sox",\(fields)}
        """.utf8))
    }

    private func market(_ fields: String, outcomes: String) throws -> FuturesMarketDetail {
        try decoder().decode(FuturesMarketDetail.self, from: Data("""
        {"id":63856441,"name":"World Series Champion",\(fields)"outcomes":[\(outcomes)]}
        """.utf8))
    }

    private let freshStamp = "2026-10-16T17:55:00Z"  // 5 min old
    private let staleGameStamp = "2026-10-16T17:00:00Z"  // 60 min old: past the 30 min live bound
    private let staleMarketStamp = "2026-10-16T10:00:00Z"  // 8 h old: past the 6 h futures bound
    private let futureStart = "2026-10-16T23:05:00Z"
    private let pastStart = "2026-10-16T16:00:00Z"

    // MARK: - Games: the hero's branches, in the hero's order

    func testAScheduledGameWithAFreshQuoteIsTheCurrentChanceAndRoundsAsOnePair() throws {
        let e = try event("""
        "status":"scheduled","commence_time":"\(futureStart)","sport":"baseball_mlb",
        "current_odds":{"home_probability":0.345,"away_probability":0.655},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let home = ProbabilityAnswer10873.game(e, side: .home, now: now)
        let away = ProbabilityAnswer10873.game(e, side: .away, now: now)
        XCTAssertEqual(home.kind, .current)
        XCTAssertEqual(away.kind, .current)
        XCTAssertTrue(home.text.contains("current win chance"), home.text)
        XCTAssertTrue(home.text.contains("Starts"), home.text)
        // #2085: the two sides are one pair. Independently rounded they print 35 + 66 = 101.
        let shown = OpeningLineHero.resolve(e.currentOdds!, for: e)
        let pair = EventDetailView.heroPairPercents(shown, away: 0.655, home: 0.345)
        XCTAssertEqual(home.figure, formatProbability(0.345, renderedPercent: pair.home))
        XCTAssertEqual(away.figure, formatProbability(0.655, renderedPercent: pair.away))
        XCTAssertEqual(percent(home.figure) + percent(away.figure), 100)
    }

    func testServedPercentsAreUsedBothOrNeither() throws {
        let e = try event("""
        "status":"live","commence_time":"\(pastStart)","home_score":2,"away_score":3,
        "current_odds":{"home_probability":0.405,"away_probability":0.595,
                        "home_rendered_percent":40,"away_rendered_percent":60},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let home = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(home.figure, "40%")
        XCTAssertEqual(home.kind, .current)
        XCTAssertTrue(home.text.contains("Live: Boston Red Sox 3, New York Yankees 2"), home.text)
    }

    func testAStaleQuoteIsTheLastRecordedChanceNeverTheCurrentOne() throws {
        let e = try event("""
        "status":"live","commence_time":"\(pastStart)",
        "current_odds":{"home_probability":0.6,"away_probability":0.4},
        "hero_probability_observed_at":"\(staleGameStamp)"
        """)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(answer.kind, .lastRecorded)
        XCTAssertTrue(answer.text.contains("last recorded win chance, recorded"), answer.text)
        XCTAssertFalse(answer.text.contains("current"), answer.text)
    }

    func testAnUndatedQuoteIsNeverCalledCurrent() throws {
        let e = try event("""
        "status":"scheduled","commence_time":"\(futureStart)",
        "current_odds":{"home_probability":0.6,"away_probability":0.4}
        """)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(answer.kind, .lastRecorded)
        XCTAssertTrue(answer.text.contains("No time was recorded"), answer.text)
    }

    func testAnOpeningLineHeroAnswersWithTheServersPairAndSaysSo() throws {
        // #9470: the opening hero prints `hero_probability`, not `current_odds`.
        let e = try event("""
        "status":"scheduled","commence_time":"\(futureStart)",
        "current_odds":{"home_probability":0.55,"away_probability":0.45},
        "hero_probability":0.6,"hero_probability_away":0.4,"hero_probability_source":"opening",
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(answer.kind, .openingLine)
        XCTAssertEqual(answer.figure, "60%")
        XCTAssertTrue(answer.text.contains("opening line"), answer.text)
    }

    func testADrawPricedMatchWithholdsTheAwaySideInsteadOfInventingItsComplement() throws {
        let e = try decoder().decode(EventDetail.self, from: Data("""
        {"id":15310517,"home_team":"Arsenal","away_team":"Brighton & Hove Albion",
         "status":"scheduled","commence_time":"\(futureStart)","sport":"soccer_epl",
         "current_odds":{"home_probability":0.52,"away_probability":0.48},
         "hero_probability_observed_at":"\(freshStamp)"}
        """.utf8))
        let away = ProbabilityAnswer10873.game(e, side: .away, now: now)
        XCTAssertEqual(away.kind, .unavailable)
        XCTAssertNil(away.figure)
        XCTAssertFalse(away.text.contains("48%"), away.text)
        let home = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(home.figure, "52%")
        XCTAssertEqual(home.kind, .current)
    }

    func testAFinishedGameAnswersWithItsResultAndNoPrice() throws {
        let e = try event("""
        "status":"completed","commence_time":"\(pastStart)","home_score":2,"away_score":5,
        "hero_settled_result":"away",
        "current_odds":{"home_probability":0.01,"away_probability":0.99},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let home = ProbabilityAnswer10873.game(e, side: .home, now: now)
        let away = ProbabilityAnswer10873.game(e, side: .away, now: now)
        XCTAssertEqual(home.kind, .result)
        XCTAssertNil(home.figure)
        XCTAssertTrue(home.text.contains("New York Yankees lost"), home.text)
        XCTAssertTrue(home.text.contains("Boston Red Sox won"), home.text)
        XCTAssertTrue(away.text.hasPrefix("Boston Red Sox won"), away.text)
        XCTAssertTrue(away.text.contains("Boston Red Sox 5, New York Yankees 2"), away.text)
        XCTAssertFalse(home.text.contains("%"), home.text)
    }

    func testADrawIsAResultAndAFinalWithNoScoreNamesNone() throws {
        let draw = try event("""
        "status":"completed","home_score":1,"away_score":1,"hero_settled_result":"draw"
        """)
        XCTAssertEqual(ProbabilityAnswer10873.game(draw, side: .home, now: now).kind, .result)
        XCTAssertTrue(ProbabilityAnswer10873.game(draw, side: .home, now: now).text.contains("ended in a draw"))
        let unknown = try event(#""status":"closed""#)
        let answer = ProbabilityAnswer10873.game(unknown, side: .away, now: now)
        XCTAssertEqual(answer.kind, .noResult)
        XCTAssertNil(answer.figure)
    }

    func testAVenueSettledGameReadsTheVenuesVerdictVerbatimAndNoPrice() throws {
        let e = try event("""
        "status":"scheduled","commence_time":"\(pastStart)","venue_settled":true,
        "venue_settled_result":"Boston Red Sox wins 5-2",
        "current_odds":{"home_probability":0.3,"away_probability":0.7},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(answer.kind, .result)
        XCTAssertTrue(answer.text.contains("Boston Red Sox wins 5-2"), answer.text)
        XCTAssertNil(answer.figure)
    }

    func testAPostponedGameSaysSoBesideItsLastRecordedPair() throws {
        let e = try event("""
        "status":"suspended","commence_time":"\(pastStart)","espn":{"period":"Postponed"},
        "current_odds":{"home_probability":0.6,"away_probability":0.4},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(answer.kind, .lastRecorded)
        XCTAssertTrue(answer.text.hasSuffix("Game status: Postponed."), answer.text)
    }

    /// #4021: `suspended` on a row whose start is still in the future is not a
    /// stopped game. Siri must not say "Game status: Postponed." about a game
    /// nobody has started, and the entity row must not label it stopped either.
    func testASuspendedGameThatHasNotStartedIsNeverSpokenAsStopped() throws {
        let fields = """
        "status":"suspended","commence_time":"\(futureStart)","espn":{"period":"Postponed"},
        "current_odds":{"home_probability":0.6,"away_probability":0.4},
        "hero_probability_observed_at":"\(freshStamp)"
        """
        let e = try event(fields)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertFalse(answer.text.contains("Game status"), answer.text)
        XCTAssertFalse(answer.text.contains("Postponed"), answer.text)

        let detail = GameOrMarketCatalog10873.gameDetail(
            league: "MLB", status: "suspended", authorityPeriod: "Postponed",
            commenceTime: futureStart, startIsTbd: false, now: now)
        XCTAssertFalse(detail?.contains("Postponed") == true, detail ?? "nil")

        // Control: the same row once started keeps the stopped word in both places.
        let started = GameOrMarketCatalog10873.gameDetail(
            league: "MLB", status: "suspended", authorityPeriod: "Postponed",
            commenceTime: pastStart, startIsTbd: false, now: now)
        XCTAssertTrue(started?.contains("Postponed") == true, started ?? "nil")
    }

    func testAGameWithNoPairSaysItHasNoChanceToShow() throws {
        let e = try event(#""status":"scheduled","commence_time":"2026-10-16T23:05:00Z""#)
        let answer = ProbabilityAnswer10873.game(e, side: .home, now: now)
        XCTAssertEqual(answer.kind, .unavailable)
        XCTAssertNil(answer.figure)
    }

    // MARK: - Markets: the market page's row value and integers

    private let ladder = """
    {"id":1,"name":"Los Angeles Dodgers","probability":0.425,"last_updated":"2026-10-16T17:55:00Z"},
    {"id":2,"name":"New York Yankees","probability":0.335,"last_updated":"2026-10-16T17:55:00Z"},
    {"id":3,"name":"Seattle Mariners","probability":0.24,"last_updated":"2026-10-16T10:00:00Z"},
    {"id":4,"name":"Field","probability":null,"last_updated":"2026-05-12T16:16:06Z"}
    """

    func testAnOpenMarketPrintsTheMarketPagesIntegerAndItsOwnClock() throws {
        let m = try market(#""status":"open","#, outcomes: ladder)
        let fresh = ProbabilityAnswer10873.market(m, outcomeID: 1, now: now)
        XCTAssertEqual(fresh.kind, .current)
        XCTAssertEqual(fresh.figure,
                       formatProbability(0.425, renderedPercent: futuresDetailRenderedPercents(m.outcomes)[1]))
        XCTAssertTrue(fresh.text.contains("current chance as of"), fresh.text)
        let stale = ProbabilityAnswer10873.market(m, outcomeID: 3, now: now)
        XCTAssertEqual(stale.kind, .lastRecorded)
        XCTAssertTrue(stale.text.contains("last recorded chance, recorded"), stale.text)
        let priceless = ProbabilityAnswer10873.market(m, outcomeID: 4, now: now)
        XCTAssertEqual(priceless.kind, .unavailable)
        XCTAssertNil(priceless.figure)
        let missing = ProbabilityAnswer10873.market(m, outcomeID: 99, now: now)
        XCTAssertEqual(missing.kind, .unavailable)
    }

    func testAGradedMarketAnswersWonOrLostAndNeverItsLastQuote() throws {
        let m = try market(#""status":"resolved","#, outcomes: """
        {"id":1,"name":"Los Angeles Dodgers","probability":0.999,"is_winner":true,
         "resolution_source":"api_settlement","last_updated":"\(freshStamp)"},
        {"id":2,"name":"New York Yankees","probability":0.001,"is_winner":false,
         "resolution_source":"api_settlement","last_updated":"\(freshStamp)"}
        """)
        let won = ProbabilityAnswer10873.market(m, outcomeID: 1, now: now)
        let lost = ProbabilityAnswer10873.market(m, outcomeID: 2, now: now)
        XCTAssertEqual(won.kind, .result)
        XCTAssertEqual(lost.kind, .result)
        XCTAssertTrue(won.text.hasSuffix("Los Angeles Dodgers won."), won.text)
        XCTAssertTrue(lost.text.hasSuffix("New York Yankees lost."), lost.text)
        XCTAssertNil(won.figure)
        XCTAssertFalse(won.text.contains("%"), won.text)
    }

    func testAClosedButUngradedMarketIsALastRecordedPriceNotACurrentOne() throws {
        let m = try market(#""status":"resolved","#, outcomes: """
        {"id":1,"name":"Yes","probability":0.7,"last_updated":"\(freshStamp)"},
        {"id":2,"name":"No","probability":0.3,"last_updated":"\(freshStamp)"}
        """)
        let answer = ProbabilityAnswer10873.market(m, outcomeID: 1, now: now)
        XCTAssertEqual(answer.kind, .lastRecorded)
        XCTAssertTrue(answer.text.contains("has closed"), answer.text)
    }

    /// #698 composed onto master after this suite was written: a settled row the
    /// market page prints as "Result unknown" (served `settlement_display`, or a
    /// resolved Polymarket market's fallback) is answered the same way, never as
    /// Lost and never as a chance.
    func testASettledRowWhoseResultIsUnknownAnswersAsThePageDoes() throws {
        let served = try market(#""status":"resolved","#, outcomes: """
        {"id":1,"name":"Yes","probability":0.62,"is_winner":false,"resolution_source":"api_settlement",
         "settlement_display":{"verdict":"unknown","basis":null},"last_updated":"\(freshStamp)"},
        {"id":2,"name":"No","probability":null,"settlement_display":{"verdict":"unknown","basis":null},
         "last_updated":"\(freshStamp)"}
        """)
        XCTAssertEqual(FuturesDetailRowValue.of(served.outcomes[0], marketStatus: served.status, marketSource: served.source),
                       .resultUnknown(lastRecorded: 0.62))
        let priced = ProbabilityAnswer10873.market(served, outcomeID: 1, now: now)
        XCTAssertEqual(priced.kind, .noResult)
        XCTAssertNil(priced.figure)
        XCTAssertTrue(priced.text.contains("The result for Yes is not known."), priced.text)
        XCTAssertTrue(priced.text.contains("last recorded chance was "
            + formatProbability(0.62, renderedPercent: futuresDetailRenderedPercents(served.outcomes)[1])), priced.text)
        XCTAssertFalse(priced.text.contains("lost"), priced.text)
        XCTAssertFalse(priced.text.contains("current"), priced.text)
        let unpriced = ProbabilityAnswer10873.market(served, outcomeID: 2, now: now)
        XCTAssertEqual(unpriced.kind, .noResult)
        XCTAssertFalse(unpriced.text.contains("%"), unpriced.text)

        // No served contract: only the market's source decides, as on the page.
        let fallback = try market(#""status":"resolved","source":"polymarket","#, outcomes: """
        {"id":1,"name":"Yes","probability":0.4,"is_winner":false,"resolution_source":"api_settlement",
         "last_updated":"\(freshStamp)"}
        """)
        let answer = ProbabilityAnswer10873.market(fallback, outcomeID: 1, now: now)
        XCTAssertEqual(answer.kind, .noResult)
        XCTAssertFalse(answer.text.contains("lost"), answer.text)
    }

    // MARK: - Failures

    func testOfflineIsNotNoDataAndNoStatusCodeIsSpoken() {
        let offline = ProbabilityAnswer10873.failure(
            APIError.networkError(underlying: URLError(.notConnectedToInternet)), subject: "Red Sox vs Yankees")
        XCTAssertEqual(offline.kind, .offline)
        let gone = ProbabilityAnswer10873.failure(
            APIError.httpError(statusCode: 404, body: nil), subject: "Red Sox vs Yankees")
        XCTAssertEqual(gone.kind, .unavailable)
        XCTAssertTrue(gone.text.contains("no longer available"), gone.text)
        let broken = ProbabilityAnswer10873.failure(
            APIError.httpError(statusCode: 503, body: nil), subject: "Red Sox vs Yankees")
        XCTAssertEqual(broken.kind, .unavailable)
        XCTAssertFalse(broken.text.contains("503"), broken.text)
    }

    // MARK: - Identity and ambiguity

    func testAnEntityIdentifierIsItsCanonicalIdAndNothingElseParses() {
        XCTAssertEqual(GameOrMarketEntity10873.identifier(kind: .game, recordID: 15320337), "game-15320337")
        XCTAssertEqual(GameOrMarketEntity10873.reference("market-63856441")?.recordID, 63856441)
        for bad in ["game-0", "game-01", "event-5", "game-5-6", "game-", "game--5", "Game-5", "market-x"] {
            XCTAssertNil(GameOrMarketEntity10873.reference(bad), bad)
        }
        XCTAssertEqual(OutcomeEntity10873.reference("game-12-home")?.subjectID, "game-12")
        XCTAssertEqual(OutcomeEntity10873.reference("market-5-77")?.key, "77")
        for bad in ["game-12-draw", "market-5-x", "market-5-07", "game-12", "team-12-home"] {
            XCTAssertNil(OutcomeEntity10873.reference(bad), bad)
        }
    }

    func testAnOutcomeSavedWithOneGameCannotAnswerForAnother() throws {
        let options = OutcomeEntity10873.options(for: try event(#""status":"scheduled""#))
        XCTAssertEqual(options.map(\.id), ["game-15320337-away", "game-15320337-home"])
        XCTAssertEqual(options.map(\.name), ["Boston Red Sox", "New York Yankees"])
        XCTAssertNil(OutcomeChoice10873.supplied("game-999-home", among: options))
        XCTAssertEqual(OutcomeChoice10873.supplied("game-15320337-home", among: options)?.name, "New York Yankees")
    }

    func testAnOutcomeIsTakenUnaskedOnlyWhenItIsTheOnlyOne() {
        XCTAssertEqual(OutcomeChoice10873.decide(optionCount: 0), .none)
        XCTAssertEqual(OutcomeChoice10873.decide(optionCount: 1), .only)
        XCTAssertEqual(OutcomeChoice10873.decide(optionCount: 2), .ask)
        XCTAssertEqual(OutcomeChoice10873.decide(optionCount: 40), .ask)
    }

    func testMarketOutcomesAreListedInTheMarketPagesHeadlineOrder() throws {
        let m = try market(#""status":"open","#, outcomes: ladder)
        XCTAssertEqual(OutcomeEntity10873.options(for: m).map(\.key), ["1", "2", "3", "4"])
    }

    func testRepeatedMatchupsComeBackAsSeparateRowsTheReaderCanTellApart() throws {
        let response = try decoder().decode(SearchResponse.self, from: Data("""
        {"query":"red sox yankees","results":[
          {"id":101,"home_team":"New York Yankees","away_team":"Boston Red Sox","sport":"baseball_mlb",
           "status":"completed","commence_time":"2026-10-13T23:05:00Z"},
          {"id":102,"home_team":"New York Yankees","away_team":"Boston Red Sox","sport":"baseball_mlb",
           "status":"scheduled","commence_time":"2026-10-17T23:05:00Z"}],
         "futures":[
          {"id":7,"name":"AL Pennant","source":"kalshi","status":"open"},
          {"id":8,"name":"AL Pennant","source":"polymarket","status":"open"},
          {"id":9,"name":"World Series Champion","source":"kalshi","status":"resolved"}],
         "futures_families":[{"family_key":"al","label":"AL","headline":
          {"id":8,"name":"AL Pennant","source":"polymarket","status":"open"},"members":[]}]}
        """.utf8))
        let entities = GameOrMarketCatalog10873.entities(from: response)
        XCTAssertEqual(entities.map(\.id), ["game-101", "game-102", "market-8", "market-7", "market-9"])
        // Same title, different rows: the detail line is what tells them apart.
        XCTAssertEqual(entities[0].title, entities[1].title)
        XCTAssertNotEqual(entities[0].detail, entities[1].detail)
        XCTAssertTrue(entities[0].detail?.contains("Final") == true, entities[0].detail ?? "nil")
        XCTAssertEqual(entities[2].title, entities[3].title)
        XCTAssertNotEqual(entities[2].detail, entities[3].detail)
        XCTAssertTrue(entities[4].detail?.contains(EventState.venueSettledLabel) == true, entities[4].detail ?? "nil")
    }

    func testSearchIsCappedPerKind() throws {
        let rows = (1...14).map {
            #"{"id":\#($0),"home_team":"H\#($0)","away_team":"A\#($0)","status":"scheduled"}"#
        }.joined(separator: ",")
        let response = try decoder().decode(SearchResponse.self, from: Data("""
        {"query":"x","results":[\(rows)],"futures":[]}
        """.utf8))
        XCTAssertEqual(GameOrMarketCatalog10873.entities(from: response).count, GameOrMarketCatalog10873.perKindLimit)
    }

    // MARK: - Opening a screen

    func testAnIntentCanOpenOnlyTheThreeLinksTheRouterAlreadyRoutes() {
        XCTAssertTrue(IntentLinks10873.isIntentLink(IntentLinks10873.myStuff))
        XCTAssertTrue(IntentLinks10873.isIntentLink(IntentLinks10873.event(id: 5)!))
        XCTAssertTrue(IntentLinks10873.isIntentLink(IntentLinks10873.market(id: 6)!))
        XCTAssertNil(IntentLinks10873.event(id: 0))
        for bad in ["bainluck://events/5?x=1", "bainluck://events/05x", "https://bainluck.com/events/5",
                    "bainluck://team/boston-red-sox-mlb", "bainluck://bug-report", "bainluck://events",
                    "bainluck://futures/5/6", "bainluck://my-stuff/x"] {
            XCTAssertFalse(IntentLinks10873.isIntentLink(URL(string: bad)!), bad)
        }
        let handoff = IntentRouteHandoff10873()
        XCTAssertFalse(handoff.post(URL(string: "bainluck://bug-report")!))
        XCTAssertNil(handoff.pendingURL)
    }

    func testADeliveredLinkIsClearedSoARemountCannotReplayIt() {
        let handoff = IntentRouteHandoff10873()
        XCTAssertTrue(handoff.post(IntentLinks10873.event(id: 15320337)!))
        XCTAssertEqual(handoff.consume(), IntentLinks10873.event(id: 15320337))
        XCTAssertNil(handoff.consume())
        XCTAssertNil(handoff.pendingURL)
    }

    /// The warm path: the app is open when Siri posts. `ContentView` routes from
    /// `settledPosts` and calls `consume()`; that read must see the NEW link.
    func testAWarmPostIsDeliveredOnceAfterItLands() {
        let handoff = IntentRouteHandoff10873()
        var routed: [URL] = []
        let delivered = expectation(description: "warm link routed")
        let subscription = handoff.settledPosts.sink { _ in
            if let link = handoff.consume() {
                routed.append(link)
                delivered.fulfill()
            }
        }
        defer { subscription.cancel() }
        XCTAssertTrue(handoff.post(IntentLinks10873.market(id: 63856441)!))
        wait(for: [delivered], timeout: 2)
        XCTAssertEqual(routed, [IntentLinks10873.market(id: 63856441)!])
        XCTAssertNil(handoff.pendingURL)
    }

    /// The trap `settledPosts` exists for, shown on the raw publisher: it emits in
    /// `willSet`, so a synchronous read still holds the value from before the post.
    func testTheRawPublisherEmitsBeforeThePostLandsWhichIsWhyNothingReadsIt() {
        let handoff = IntentRouteHandoff10873()
        var readDuringEmission: [URL?] = []
        let subscription = handoff.$pendingURL.dropFirst().sink { _ in
            readDuringEmission.append(handoff.pendingURL)
        }
        defer { subscription.cancel() }
        handoff.post(IntentLinks10873.myStuff)
        XCTAssertEqual(readDuringEmission, [nil])
    }

    /// The cold path: posted before the window subscribes, delivered once on subscribe.
    func testAColdPostWaitingBeforeTheWindowMountsIsDeliveredOnce() {
        let handoff = IntentRouteHandoff10873()
        handoff.post(IntentLinks10873.myStuff)
        var routed: [URL] = []
        let delivered = expectation(description: "cold link routed")
        let subscription = handoff.settledPosts.sink { _ in
            if let link = handoff.consume() {
                routed.append(link)
                delivered.fulfill()
            }
        }
        defer { subscription.cancel() }
        wait(for: [delivered], timeout: 2)
        XCTAssertEqual(routed, [IntentLinks10873.myStuff])
    }

    /// Runs `ContentView`'s `.onReceive` handler, in its exact shape, on the main
    /// run loop and counts how often it fires. A cold link is posted before the
    /// subscription; a warm one after the subscription has settled.
    private func runContentViewHandler(
        cold: URL? = nil, warm: URL? = nil
    ) -> (calls: Int, routed: [URL]) {
        let handoff = IntentRouteHandoff10873()
        if let cold { XCTAssertTrue(handoff.post(cold)) }
        var calls = 0
        var routed: [URL] = []
        let subscription = handoff.settledPosts.sink { _ in
            calls += 1
            guard let link = handoff.consume() else { return }
            routed.append(link)
        }
        defer { subscription.cancel() }
        RunLoop.main.run(until: Date().addingTimeInterval(0.25))
        if let warm { XCTAssertTrue(handoff.post(warm)) }
        RunLoop.main.run(until: Date().addingTimeInterval(0.5))
        return (calls, routed)
    }

    /// The handler must go quiet. `consume()` on an empty hand-off used to assign
    /// nil anyway, `@Published` re-emitted it, and the handler ran again — a
    /// main-queue loop from first mount (~286,000 calls a second, idle).
    func testContentViewsHandlerSettlesInsteadOfSpinningTheMainQueue() {
        let idle = runContentViewHandler()
        XCTAssertLessThanOrEqual(idle.calls, 1, "idle")
        XCTAssertEqual(idle.routed, [])

        let cold = runContentViewHandler(cold: IntentLinks10873.myStuff)
        XCTAssertLessThanOrEqual(cold.calls, 3, "cold")
        XCTAssertEqual(cold.routed, [IntentLinks10873.myStuff])

        let warm = runContentViewHandler(warm: IntentLinks10873.event(id: 15320337)!)
        XCTAssertLessThanOrEqual(warm.calls, 3, "warm")
        XCTAssertEqual(warm.routed, [IntentLinks10873.event(id: 15320337)!])
    }

    func testEachLinkLandsWhereTheRouterSendsAnyOtherLinkLikeIt() {
        let nav = NavigationCoordinator()
        XCTAssertTrue(nav.handleURL(IntentLinks10873.myStuff))
        XCTAssertEqual(nav.selectedTab, .myStuff)

        XCTAssertTrue(nav.handleURL(IntentLinks10873.event(id: 15320337)!))
        XCTAssertEqual(nav.selectedTab, .feed)
        let eventRoute = expectation(description: "event route queued")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            if case .eventDetail(let id) = nav.consumeRoute(), id == 15320337 { eventRoute.fulfill() }
        }
        wait(for: [eventRoute], timeout: 2)

        XCTAssertTrue(nav.handleURL(IntentLinks10873.market(id: 63856441)!))
        let marketRoute = expectation(description: "market route queued")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            if case .futuresDetail(let id) = nav.consumeRoute(), id == 63856441 { marketRoute.fulfill() }
        }
        wait(for: [marketRoute], timeout: 2)
    }

    // MARK: - Copy

    func testNoAnswerUsesTheWordsAlexRuledOut() throws {
        // #10873 copy rule ("question" is not the product's noun) and notice 33.
        let e = try event("""
        "status":"scheduled","commence_time":"\(futureStart)",
        "current_odds":{"home_probability":0.6,"away_probability":0.4},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let m = try market(#""status":"open","#, outcomes: ladder)
        var texts = GameSide10873.allCases.map { ProbabilityAnswer10873.game(e, side: $0, now: now).text }
        texts += [1, 3, 4, 99].map { ProbabilityAnswer10873.market(m, outcomeID: $0, now: now).text }
        texts.append(ProbabilityAnswer10873.failure(URLError(.timedOut), subject: "X").text)
        for text in texts {
            let lower = text.lowercased()
            for banned in ["question", "bookmaker", " books"] {
                XCTAssertFalse(lower.contains(banned), "\(banned) in: \(text)")
            }
        }
    }

    private func percent(_ figure: String?) -> Int {
        Int(figure?.trimmingCharacters(in: CharacterSet(charactersIn: "%<>")) ?? "") ?? -1
    }
}
