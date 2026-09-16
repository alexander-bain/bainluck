import XCTest
@testable import Bain_Luck

/// #6595, native half: **a market that was already certain before the first pitch
/// stops being drawn as a live price on the game in progress.**
///
/// The specimen is production, photographed by native/197 on 2026-09-16 21:27Z at
/// phone width: event `15313117` NYY @ MIN, hero `LIVE · Top 13th · 4 – 4`, and
/// ~1,500pt down the same page an Additional Markets row reading
/// `New York Yankees ▓▓▓▓▓▓▓▓ 100% · 17h ago` — a stale weekly Polymarket
/// container, `probability: 1.0`, `observed_at: 04:08:01Z`, 13.5 hours before the
/// 17:40Z first pitch.
///
/// The two controls below are not invented: both are real rows served by
/// production on the same afternoon, and each fails exactly ONE clause of the
/// predicate, so neither can be satisfied by the wrong half.
final class APreKickoffCertaintyIsNotALivePriceTests: XCTestCase {

    // The production specimen's clock, to the second.
    private static let firstPitch = "2026-09-16T17:40:00+00:00".asDate!
    private static let midThirteenth = "2026-09-16T21:27:00+00:00".asDate!

    // MARK: - The predicate

    func testTheProductionSpecimenIsFrozen() {
        XCTAssertTrue(
            PreKickoffCertainty.isFrozen(
                probability: 1.0,
                observedAt: "2026-09-16T04:08:01.948721+00:00",
                commenceTime: Self.firstPitch,
                eventStatus: "live",
                now: Self.midThirteenth
            ),
            "The row photographed on 15313117 — 1.0, observed 13.5h before first pitch, on a LIVE tied game — "
            + "is the row this predicate exists for. If it is not frozen, the page still draws a filled 100% bar over a 4–4 game."
        )
    }

    /// CONTROL 1 — fails the PRE-KICKOFF clause only.
    ///
    /// `15313117` also served `Minnesota 0.99` at 21:33Z, in the 13th, from Kalshi.
    /// That is a true live price on a team about to win, and a certainty-only rule
    /// would freeze it — deleting the bar from the most informative row on the card.
    func testAnInGameNearCertaintyIsStillALivePrice() {
        XCTAssertFalse(
            PreKickoffCertainty.isFrozen(
                probability: 0.99,
                observedAt: "2026-09-16T21:33:17.143225+00:00",
                commenceTime: Self.firstPitch,
                eventStatus: "live",
                now: Self.midThirteenth
            ),
            "A 0.99 observed DURING the game is a live price. Freezing it would strip the bar off the row that is telling the truth."
        )
    }

    /// CONTROL 2 — fails the CERTAINTY clause only.
    ///
    /// `15313184` (live tennis) served `Melo 0.585 / Braga 0.415`, both observed
    /// 20:55Z against a 21:00Z start — an honest pre-kickoff quote nobody re-polled.
    /// A staleness-only rule would freeze both legs of a coherent market.
    func testAPregameForecastNobodyRepolledIsNotFrozen() {
        let start = "2026-09-16T21:00:00+00:00".asDate!
        for probability in [0.585, 0.415] {
            XCTAssertFalse(
                PreKickoffCertainty.isFrozen(
                    probability: probability,
                    observedAt: "2026-09-16T20:55:00+00:00",
                    commenceTime: start,
                    eventStatus: "live",
                    now: "2026-09-16T21:30:00+00:00".asDate!
                ),
                "\(probability) quoted five minutes before kick-off is a FORECAST. Only a certainty stopped forecasting."
            )
        }
    }

    /// The event arm: a finished card already freezes every row, better, in one
    /// place. This predicate must not also fire there or two mechanisms own one row.
    func testAFinishedEventIsLeftToTheCardLevelTreatment() {
        for status in ["completed", "closed", "settled", "final", "resolved"] {
            XCTAssertFalse(
                PreKickoffCertainty.isFrozen(
                    probability: 1.0,
                    observedAt: "2026-09-16T04:08:01+00:00",
                    commenceTime: Self.firstPitch,
                    eventStatus: status,
                    now: Self.midThirteenth
                ),
                "`\(status)` routes through isGameFinished, which says it once for the whole card."
            )
        }
    }

    /// The clock arm: before kick-off EVERY row predates kick-off, so the clause
    /// says nothing and the predicate must stay silent rather than freeze the page.
    func testAnUnstartedEventFreezesNothing() {
        XCTAssertFalse(
            PreKickoffCertainty.isFrozen(
                probability: 1.0,
                observedAt: "2026-09-16T04:08:01+00:00",
                commenceTime: Self.firstPitch,
                eventStatus: "scheduled",
                now: "2026-09-16T12:00:00+00:00".asDate!
            ),
            "The game has not started. A certainty on an unplayed fixture is #6381's question and is not claimed here."
        )
    }

    /// A quote stamped AT the first pitch is the opening price, and an opening
    /// price is about this game.
    func testAQuoteAtFirstPitchIsNotPreKickoff() {
        XCTAssertFalse(
            PreKickoffCertainty.wasObservedBeforeKickoff(
                observedAt: "2026-09-16T17:40:00+00:00", commenceTime: Self.firstPitch
            ),
            "Strictly before. The opening quote is this game's."
        )
    }

    /// Absent is not zero and absent is not old (gotcha #53 / `SourceAge`).
    func testAnUnreadableOrAbsentStampCannotFreezeARow() {
        for stamp in [nil, "", "not-a-date"] as [String?] {
            XCTAssertFalse(
                PreKickoffCertainty.isFrozen(
                    probability: 1.0, observedAt: stamp,
                    commenceTime: Self.firstPitch, eventStatus: "live", now: Self.midThirteenth
                ),
                "A row with no readable stamp has not been shown to predate anything."
            )
        }
        XCTAssertFalse(
            PreKickoffCertainty.isFrozen(
                probability: 1.0, observedAt: "2026-09-16T04:08:01+00:00",
                commenceTime: nil, eventStatus: "live", now: Self.midThirteenth
            ),
            "With no kick-off there is no 'before kick-off' to be on the wrong side of."
        )
    }

    /// The band admits certainty and nothing wider. A 0.99 pre-kickoff favourite is
    /// a forecast the venue means; widening the epsilon to reach it would freeze
    /// every heavy favourite on every live page.
    func testTheCertaintyBandIsTightAtBothEnds() {
        XCTAssertTrue(PreKickoffCertainty.isCertainty(1.0))
        XCTAssertTrue(PreKickoffCertainty.isCertainty(0.0))
        XCTAssertTrue(PreKickoffCertainty.isCertainty(0.9999))
        XCTAssertTrue(PreKickoffCertainty.isCertainty(0.0001))
        XCTAssertFalse(PreKickoffCertainty.isCertainty(0.99))
        XCTAssertFalse(PreKickoffCertainty.isCertainty(0.01))
        XCTAssertFalse(PreKickoffCertainty.isCertainty(0.5))
    }

    // MARK: - The treatment actually reaches the card

    /// The predicate being right is half the ship. This asserts the CARD reaches
    /// it — real wire rows, the view's real grouping, the view's own clock.
    ///
    /// A card that never passes its `commenceTime` through would satisfy every
    /// predicate test above and still draw the filled 100% bar, so the decision
    /// is read off the view, on the entry the view itself built.
    func testTheCardItselfCallsTheSpecimenRowFrozen() throws {
        let view = Self.specimenCard(commenceTime: Self.firstPitch)
        let entry = try Self.yankeesEntry(in: view)

        XCTAssertTrue(
            view.isFrozen(entry),
            "The card built the row and then called it a live price. This is the 100% bar over a 4–4 game."
        )
        // The branch `outcomeRow` actually takes, not just the predicate behind
        // it: a card that asks and then ignores the answer passes the line above.
        XCTAssertEqual(
            view.treatment(for: entry), .frozenQuote,
            "The card decided the specimen row still gets a bar and a percent."
        )
    }

    /// The view-level control for the wiring: the SAME rows through a card with no
    /// kick-off are not frozen. If this passes while the test above fails, the
    /// clock is not reaching the predicate.
    func testTheSameRowIsNotFrozenWhenTheCardHasNoClock() throws {
        let view = Self.specimenCard(commenceTime: nil)
        let entry = try Self.yankeesEntry(in: view)

        XCTAssertFalse(
            view.isFrozen(entry),
            "With no kick-off there is no 'before kick-off'. A card that freezes anyway is not reading its own clock."
        )
    }

    /// The view-level control for the row arm: an in-game certainty on the SAME
    /// card, with the same clock and status, keeps its live treatment.
    func testAnInGameRowOnTheSameCardIsNotFrozen() {
        let view = Self.specimenCard(commenceTime: Self.firstPitch)
        let inGame = SpecialEventMarketsView.OutcomeEntry(
            label: "Minnesota", prob: 0.99, sourceCount: 1,
            observedAt: "2026-09-16T21:33:17.143225+00:00"
        )

        XCTAssertFalse(
            view.isFrozen(inGame),
            "A 0.99 quoted in the 13th is the truest number on the page. The card must still draw it as a price."
        )
        XCTAssertEqual(
            view.treatment(for: inGame), .livePrice,
            "The live row lost its bar. Freezing a true number is the same lie in the other direction."
        )
    }

    /// The row is DECLARED, never deleted — #2086 removed a price-band deletion
    /// from this exact card and recorded why (#2019: a blank where an honest
    /// statement belonged). Every assertion above is equally true of a fix that
    /// withholds the row, so membership is pinned against the disarmed card:
    /// same rows in, same rows out, only the treatment differs.
    func testFreezingARowDoesNotRemoveItFromTheCard() throws {
        let armed = Self.specimenCard(commenceTime: Self.firstPitch)
        let disarmed = Self.specimenCard(commenceTime: nil)

        let armedLabels = Self.allOutcomeLabels(armed)
        XCTAssertEqual(
            armedLabels, Self.allOutcomeLabels(disarmed),
            "Membership moved. This change decides a row's TREATMENT, never its existence (#2086/#2019)."
        )
        XCTAssertTrue(
            armedLabels.contains("New York Yankees"),
            "The frozen row itself must still be on the card — and this pins the fixture, so an empty card cannot pass the equality above."
        )
    }

    /// The treatment this change did NOT invent still works: on a finished event
    /// every row is frozen at the card level, including an ordinary mid-band price
    /// that no clause of ``PreKickoffCertainty`` would touch.
    func testAFinishedCardStillFreezesAnOrdinaryRow() {
        let view = SpecialEventMarketsView(
            markets: Self.specimenRows, eventStatus: "completed", commenceTime: Self.firstPitch
        )
        let ordinary = SpecialEventMarketsView.OutcomeEntry(
            label: "Minnesota", prob: 0.52, sourceCount: 1,
            observedAt: "2026-09-16T21:33:17.143225+00:00"
        )

        XCTAssertEqual(
            view.treatment(for: ordinary), .frozenQuote,
            "#2086's finished-card treatment is gone. A settled page is drawing live bars again."
        )
    }

    // MARK: - Fixture

    private static func specimenCard(commenceTime: Date?) -> SpecialEventMarketsView {
        SpecialEventMarketsView(markets: specimenRows, eventStatus: "live", commenceTime: commenceTime)
    }

    /// The settled Polymarket row, as the VIEW grouped it.
    private static func yankeesEntry(
        in view: SpecialEventMarketsView
    ) throws -> SpecialEventMarketsView.OutcomeEntry {
        let item = try XCTUnwrap(
            view.categories.flatMap(\.items).first { $0.name == "New York Yankees vs. Minnesota Twins" },
            "the specimen market is not on the card at all — the fixture or the grouping has moved"
        )
        return try XCTUnwrap(
            item.outcomes.first { $0.label == "New York Yankees" },
            "the specimen market has no 'New York Yankees' outcome row"
        )
    }

    private static func allOutcomeLabels(_ view: SpecialEventMarketsView) -> Set<String> {
        Set(view.categories.flatMap(\.items).flatMap(\.outcomes).map(\.label))
    }

    /// The production `other[]` of event 15313117, verbatim from
    /// `GET /api/events/15313117/game-markets` at 21:33Z on 2026-09-16.
    private static let specimenRows: [GameMarketOther] = decodeRows("""
    [
      {"market_name": "New York Yankees vs Minnesota", "outcome_name": "Minnesota",
       "observed_at": "2026-09-16T21:33:17.143225+00:00", "probability": 0.99, "source": "kalshi"},
      {"market_name": "New York Yankees vs Minnesota", "outcome_name": "New York Yankees",
       "observed_at": "2026-09-16T21:32:58.301582+00:00", "probability": 0.01, "source": "kalshi"},
      {"market_name": "New York Yankees vs. Minnesota Twins", "outcome_name": "New York Yankees",
       "observed_at": "2026-09-16T04:08:01.948721+00:00", "probability": 1.0, "source": "polymarket",
       "is_winner": true, "resolution_source": "api_settlement"}
    ]
    """)

    /// Decoded from the wire rather than constructed, so the fixture cannot drift
    /// away from the payload shape it claims to be quoting.
    private static func decodeRows(_ json: String) -> [GameMarketOther] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // swiftlint:disable:next force_try
        return try! decoder.decode([GameMarketOther].self, from: Data(json.utf8))
    }
}
