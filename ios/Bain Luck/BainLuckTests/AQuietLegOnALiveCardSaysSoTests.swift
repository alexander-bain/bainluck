import XCTest
@testable import Bain_Luck

/// #4970's native half — WHEN THE ADDITIONAL MARKETS CARD DATES ITS PRICES.
///
/// ═══ THE DEFECT, MEASURED ═══
///
/// `GameMarketOther` did not decode `observed_at`, so the phone's Additional
/// Markets card could not tell a leg quoted a minute ago from one quoted two
/// hours ago, and drew both as equal members of one distribution. Read from
/// production on 2026-09-16 at 16:5xZ, three live soccer events in one pass:
///
///   15310931 "Second Half Result"  0.9955 / 0.525 / 0.0045 = **153%**,
///                                  ages 2 / 43 / 25 minutes
///   15313067 "Halftime Result"     0.9985 / 0.80  / 0.0215 = **182%**,
///                                  ages 2 / 115 / 115 minutes
///   15307696 "First Team to Score"                         = **135%**,
///                                  ages 49 / 284 / 284 minutes
///
/// A reader on `bainluck://events/15310931` saw "Panathinaikós AO 100% / AE
/// Kifisiás 53% / Draw 0%" under a hero that said Kifisiás were under 1% to win
/// the match. The 53% was a price from 43 minutes earlier that nothing had
/// refreshed, printed as though it were current.
///
/// ═══ WHAT IS AND IS NOT BEING FIXED ═══
///
/// This suite pins WHERE THE AGE IS SAID. It does NOT renormalise the card:
/// shrinking a fresh 99.55% to make room for a 43-minute-old 52.5% would delete
/// the true number to flatter the stale one, and display normalisation belongs
/// to `normalize_display_probs` upstream (gotcha #23, #3949 / #4895).
///
/// ═══ BOTH DIRECTIONS, PER GOTCHA #43 ═══
///
/// Every case asserts what draws AND what stays silent, because the failure
/// this replaces is silence and the failure it could become is noise — web
/// measured 21 of 21 rows on a live slate past the 30-minute bar, which as
/// per-row marks is eight identical `41m ago`s down one card (notice 34).
///
/// `now` is an argument everywhere (gotcha #44): no assertion here branches on
/// when the suite happens to run.
final class AQuietLegOnALiveCardSaysSoTests: XCTestCase {

    // MARK: - Fixtures

    /// A fixed instant, and stamps built backwards from it. 2026-09-16 16:57Z.
    private let now = Date(timeIntervalSince1970: 1_789_664_220)

    private func stamp(minutesAgo: Double) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: now.addingTimeInterval(-minutesAgo * 60))
    }

    private func entry(
        _ label: String,
        _ prob: Double,
        minutesAgo: Double?
    ) -> SpecialEventMarketsView.OutcomeEntry {
        SpecialEventMarketsView.OutcomeEntry(
            label: label,
            prob: prob,
            sourceCount: 1,
            observedAt: minutesAgo.map { stamp(minutesAgo: $0) }
        )
    }

    /// Event 15310931, "AE Kifisiás vs. Panathinaikós AO - Second Half Result",
    /// verbatim: the probabilities and the leg ages as served.
    private var secondHalfResult15310931: [SpecialEventMarketsView.OutcomeEntry] {
        [
            entry("Panathinaikós AO", 0.9955, minutesAgo: 2),
            entry("AE Kifisiás", 0.525, minutesAgo: 43),
            entry("Draw", 0.0045, minutesAgo: 25),
        ]
    }

    // MARK: - The mixed card: the rows speak, the card does not

    func testTheStaleLegOfTheOneFiftyThreePercentCardDrawsItsOwnAge() {
        let decision = SpecialEventMarketsView.ageDecision(
            secondHalfResult15310931, live: true, now: now
        )

        // The 43-minute leg is past the live bound and the other two are not, so
        // no single stamp can speak for this card without lying about one of
        // them.
        XCTAssertNil(
            decision.cardStamp,
            "a card holding a 2-minute-old row and a 43-minute-old one must not "
                + "summarise them with one age"
        )
        XCTAssertTrue(
            decision.showRowAges,
            "the 53% that nothing refreshed for 43 minutes must say so on its own row"
        )
    }

    func testOnlyTheStaleRowOfThatCardCanActuallyDrawAMark() {
        // `showRowAges` opens the door; `PriceAgeMarkView`'s failable init is
        // what decides per row. Without this the suite would pass on a change
        // that marked all three.
        let marks = secondHalfResult15310931.map {
            PriceAgeMarkView(observedAt: $0.observedAt, cadence: .live, now: now)
        }
        XCTAssertNil(marks[0], "the 2-minute-old leg is inside the live cadence")
        XCTAssertEqual(marks[1]?.age, "43m ago")
        XCTAssertNil(marks[2], "the 25-minute-old leg is inside the live cadence")
    }

    // MARK: - The uniform card: the card speaks once, with the OLDEST stamp

    func testAllQuietCardSpeaksOnceAndItsRowsStaySilent() {
        // 15307696 "First Team to Score": 49 / 284 / 284 minutes.
        let card = [
            entry("Port FC", 0.55, minutesAgo: 49),
            entry("Vissel Kobe", 0.62, minutesAgo: 284),
            entry("No Goal", 0.18, minutesAgo: 284),
        ]
        let decision = SpecialEventMarketsView.ageDecision(card, live: true, now: now)

        XCTAssertFalse(
            decision.showRowAges,
            "three identical marks down one card is the noise notice 34 bans"
        )
        XCTAssertEqual(
            SourceAge.format(decision.cardStamp, now: now),
            "4h ago",
            "one stamp speaking for several rows may only claim an age all of "
                + "them have reached, so it is the OLDEST — 284 minutes, not 49"
        )
    }

    func testTheCardStampIsComparedAsTimeAndNotAsText() {
        // The offset trap web's `oldestSourceStamp` documents:
        // `…T12:00:00-04:00` is 16:00Z and sorts EARLIER as a string than
        // `…T13:00:00+00:00`, which is the genuinely older price.
        let older = "2026-09-16T13:00:00+00:00"
        let newer = "2026-09-16T12:00:00-04:00"
        XCTAssertEqual(SourceAge.oldestStamp([newer, older]), older)
        XCTAssertEqual(SourceAge.oldestStamp([older, newer]), older)
    }

    // MARK: - Silence

    func testAFreshCardSaysNothingAtAll() {
        let card = [
            entry("Panathinaikós AO", 0.9955, minutesAgo: 2),
            entry("AE Kifisiás", 0.004, minutesAgo: 1),
        ]
        let decision = SpecialEventMarketsView.ageDecision(card, live: true, now: now)
        XCTAssertNil(decision.cardStamp)
        XCTAssertFalse(decision.showRowAges)
    }

    func testAPregameCardIsNeverDatedEvenWhenEveryLegIsHoursOld() {
        // An upcoming game's markets are polled far slower than the two-minute
        // live cadence. Applying the live bound before kickoff marks every row
        // on every upcoming page, which is how a mark stops meaning anything.
        let card = [
            entry("Home", 0.6, minutesAgo: 600),
            entry("Away", 0.4, minutesAgo: 600),
        ]
        let decision = SpecialEventMarketsView.ageDecision(card, live: false, now: now)
        XCTAssertNil(decision.cardStamp)
        XCTAssertFalse(decision.showRowAges)
    }

    func testAnUndatableLegIsNotClaimedToBeStaleAndDoesNotSilenceItsCard() {
        // Absent is absent (gotcha #53): a leg we have never observed is not a
        // fresh price and not a stale one. It must not be swept into the "all
        // quiet" set — that would let the card speak an age this row never
        // reached — and it must not suppress the stale row beside it.
        let card = [
            entry("Priced and quiet", 0.5, minutesAgo: 90),
            entry("Never observed", 0.5, minutesAgo: nil),
        ]
        let decision = SpecialEventMarketsView.ageDecision(card, live: true, now: now)
        XCTAssertNil(decision.cardStamp, "one datable row cannot date the card")
        XCTAssertTrue(decision.showRowAges)
        XCTAssertNil(PriceAgeMarkView(observedAt: nil, cadence: .live, now: now))
    }

    func testAnEmptyCardIsNotDated() {
        let decision = SpecialEventMarketsView.ageDecision([], live: true, now: now)
        XCTAssertNil(decision.cardStamp)
        XCTAssertFalse(decision.showRowAges)
    }

    // MARK: - The bound is the house's, not a number tuned here

    func testTheBoundIsTheLiveCadenceAndTheEdgeIsStrict() {
        // A FRESH SIBLING IS LOAD-BEARING IN BOTH ARMS. A one-row card is
        // "every row agrees" by definition, so `showRowAges` is false on it
        // whether or not the row is stale — the assertion would pass on a
        // broken bound. The companion keeps the card in the mixed arm, where
        // `showRowAges` tracks the bound and nothing else.
        let fresh = entry("Fresh", 0.5, minutesAgo: 1)

        XCTAssertFalse(
            SpecialEventMarketsView.ageDecision(
                [fresh, entry("Exactly at the bound", 0.5, minutesAgo: 30)],
                live: true, now: now
            ).showRowAges,
            "`SourceAge.isStale` mirrors web's strict `>`; 30 minutes is not yet stale"
        )
        XCTAssertTrue(
            SpecialEventMarketsView.ageDecision(
                [fresh, entry("A minute past it", 0.5, minutesAgo: 31)],
                live: true, now: now
            ).showRowAges
        )
        XCTAssertEqual(SourceAge.Cadence.live.staleAfter, 30 * 60)
    }

    func testALoneQuietRowIsTheCardSpeakingAndNotARowMark() {
        // The one-row card is the degenerate "every row agrees" case, and it is
        // asserted rather than left to be discovered: a card of one stale row
        // must draw ONE mark in its header, not one in its header and one on
        // its row.
        let decision = SpecialEventMarketsView.ageDecision(
            [entry("Alone and quiet", 0.5, minutesAgo: 90)], live: true, now: now
        )
        XCTAssertEqual(SourceAge.format(decision.cardStamp, now: now), "1h ago")
        XCTAssertFalse(decision.showRowAges)
    }

    // MARK: - The wire contract

    func testObservedAtIsDecodedFromTheWireRowVerbatim() {
        // The whole defect was a key that never reached this model. `other[]`
        // from `GET /api/events/15310931/game-markets`, 2026-09-16, one row.
        let json = """
        {
            "market_name": "AE Kifisiás vs. Panathinaikós AO - Second Half Result",
            "outcome_name": "AE Kifisiás",
            "observed_at": "2026-09-16T16:20:34.362536+00:00",
            "probability": 0.525,
            "source": "polymarket",
            "is_winner": null,
            "resolution_source": null,
            "_market_id": 60850665
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let row = try? decoder.decode(GameMarketOther.self, from: json)

        XCTAssertEqual(row?.observedAt, "2026-09-16T16:20:34.362536+00:00")
        XCTAssertEqual(row?.probability, 0.525)
    }

    func testAnAbsentObservedAtDecodesToNilRatherThanFailingTheRow() {
        // Older cached bodies and any builder that omits the key must still
        // yield a row — a card that fails to decode is a blank section.
        let json = """
        {"market_name": "M", "outcome_name": "O", "probability": 0.5, "source": "kalshi"}
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let row = try? decoder.decode(GameMarketOther.self, from: json)
        XCTAssertNotNil(row)
        XCTAssertNil(row?.observedAt)
    }

    // MARK: - The entry carries the stamp of the number it shows

    func testTheBuiltEntryKeepsTheStampOfTheRowWhoseNumberSurvived() {
        // Two sources quoting one label are merged into one entry and only the
        // FIRST one's probability survives, so the entry must carry the FIRST
        // one's stamp — dating a number that is not on screen is the same class
        // of defect as not dating it at all.
        let view = SpecialEventMarketsView(
            markets: [
                GameMarketOther(
                    marketName: "Anytime Goalscorer",
                    outcomeName: "Player A",
                    probability: 0.31,
                    source: "polymarket",
                    observedAt: stamp(minutesAgo: 90)
                ),
                GameMarketOther(
                    marketName: "Anytime Goalscorer",
                    outcomeName: "Player A",
                    probability: 0.44,
                    source: "kalshi",
                    observedAt: stamp(minutesAgo: 1)
                ),
            ],
            eventStatus: "live"
        )
        let entries = view.categories.first?.items.first?.outcomes ?? []
        XCTAssertEqual(entries.count, 1, "one label is one row")
        XCTAssertEqual(entries.first?.prob, 0.31, "the first row's number is the one shown")
        XCTAssertEqual(
            entries.first?.observedAt,
            stamp(minutesAgo: 90),
            "so the first row's stamp is the one that dates it"
        )
    }

    // MARK: - The live predicate

    func testTheLiveTripleIsWebsTriple() {
        for status in ["live", "in_progress", "inprogress", "in progress", "halftime", "delayed", "suspended"] {
            XCTAssertFalse(SettledQuote.isPregame(status), "\(status) is in play, not pregame")
        }
        for status in ["completed", "closed", "settled", "final", "resolved"] {
            XCTAssertFalse(SettledQuote.isPregame(status), "\(status) has landed, not pregame")
        }
        // Unknown lands on pregame — the safe end, which draws no age.
        for status in ["scheduled", "postponed", "", "STATUS_WHO_KNOWS"] {
            XCTAssertTrue(SettledQuote.isPregame(status), "\(status) must read as pregame")
        }
        XCTAssertTrue(SettledQuote.isPregame(nil))
        XCTAssertFalse(SettledQuote.isPregame("LIVE"), "matching is case-insensitive, as web's is")
    }
}
