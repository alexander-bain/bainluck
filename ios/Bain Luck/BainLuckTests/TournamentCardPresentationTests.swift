import XCTest
@testable import Bain_Luck

/// L2-225 — the tournament card's live-vs-terminal framing, asserted on the pure
/// `TournamentCardPresentation` value the view body actually reads.
///
/// L2-224 taught the card the WHAT-HIT state but only half-dressed it: the FINAL
/// and WON chips appeared while the live 62% hero, the runner-up probability strip,
/// and the backend's present-tense `reason` line ("… leads at 62.0% (up 2.3% today)")
/// all stayed on screen underneath them. Web has always dropped the number and led
/// with the champion's name (`TournamentCard.tsx:44–48`) and renders no reason text
/// at all.
///
/// These assertions are deliberately about SEMANTICS, not copy or layout: a future
/// restyle of the champion chip must not break them, but re-introducing a live
/// probability on a finished tournament must.
final class TournamentCardPresentationTests: XCTestCase {

    private func tournament(marqueeWhathit: Bool, golfers: Int = 4) -> FeedTournamentData {
        let rows = (0..<golfers).map { i in
            """
            {"name": "Golfer \(i)", "probability": \(62 - i * 10), "rank": \(i + 1),
             "movement_24h": 2.3}
            """
        }.joined(separator: ",")
        let json = """
        {
          "key": "the_open_championship", "name": "The Open Championship",
          "tour": "pga", "tour_label": "PGA Tour", "is_major": true,
          "schedule_status": "completed", "end_date": "2026-07-19T00:00:00Z",
          "resolution_date": "2026-07-19T00:00:00Z",
          "golfers": [\(rows)], "source_count": 2,
          "is_marquee": true, "marquee_whathit": \(marqueeWhathit)
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        // swiftlint:disable:next force_try
        return try! dec.decode(FeedTournamentData.self, from: Data(json.utf8))
    }

    private func presentation(
        whatHit: Bool, golfers: Int = 4, hasContext: Bool = true
    ) -> TournamentCardPresentation {
        let data = tournament(marqueeWhathit: whatHit, golfers: golfers)
        return TournamentCardPresentation(
            data: data,
            hasLeader: golfers > 0,
            runnerUpCount: max(golfers - 1, 0),
            hasContext: hasContext
        )
    }

    // MARK: - Live framing

    func testLiveTournamentShowsProbabilityMovementRunnerUpsAndContext() {
        let p = presentation(whatHit: false)
        XCTAssertTrue(p.showsProbabilityHero)
        XCTAssertTrue(p.showsMovementLine)
        XCTAssertTrue(p.showsRunnerUpStrip)
        XCTAssertTrue(p.showsFeedContext)
        XCTAssertFalse(p.showsChampion)
        XCTAssertFalse(p.showsFinalChip)
    }

    // MARK: - Terminal framing

    func testSettledTournamentLeadsWithTheChampionNotAProbability() {
        let p = presentation(whatHit: true)
        XCTAssertTrue(p.showsChampion)
        XCTAssertTrue(p.showsFinalChip)
        XCTAssertFalse(
            p.showsProbabilityHero,
            "a finished tournament's hero is the winner, not what we thought would happen")
    }

    func testSettledTournamentSuppressesEveryLiveMovementSurface() {
        let p = presentation(whatHit: true)
        XCTAssertFalse(p.showsMovementLine, "no '+2.3pp today' on a finished tournament")
        XCTAssertFalse(
            p.showsRunnerUpStrip,
            "runner-up odds are the odds of a race that is already over")
        XCTAssertFalse(
            p.showsFeedContext,
            "the backend reason is present-tense live prose ('leads at 62.0% (up 2.3% today)')")
    }

    // MARK: - Degenerate payloads must not fabricate a result

    func testSettledTournamentWithNoGolfersClaimsNoChampion() {
        // `marquee_whathit` alone is not a winner. With no leader row there is
        // nothing to crown, and the card must say nothing rather than invent one.
        let p = presentation(whatHit: true, golfers: 0)
        XCTAssertFalse(p.showsChampion)
        XCTAssertFalse(p.showsProbabilityHero)
        XCTAssertTrue(p.showsFinalChip, "the FINAL marker is still honest")
    }

    func testLiveTournamentWithNoGolfersShowsNoHeroEither() {
        let p = presentation(whatHit: false, golfers: 0)
        XCTAssertFalse(p.showsProbabilityHero)
        XCTAssertFalse(p.showsMovementLine)
        XCTAssertFalse(p.showsRunnerUpStrip)
    }

    func testSingleGolferHasNoRunnerUpStripInEitherState() {
        XCTAssertFalse(presentation(whatHit: false, golfers: 1).showsRunnerUpStrip)
        XCTAssertFalse(presentation(whatHit: true, golfers: 1).showsRunnerUpStrip)
    }

    func testAbsentContextIsNeverRenderedRegardlessOfLifecycle() {
        XCTAssertFalse(presentation(whatHit: false, hasContext: false).showsFeedContext)
        XCTAssertFalse(presentation(whatHit: true, hasContext: false).showsFeedContext)
    }

    // MARK: - Missing lifecycle field defaults to LIVE, not settled

    func testLegacyPayloadWithoutMarqueeWhathitRendersLive() throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let legacy = try dec.decode(FeedTournamentData.self, from: Data("""
        { "key": "k", "name": "Legacy Open",
          "golfers": [{"name": "A", "probability": 30, "rank": 1, "movement_24h": 1.0}] }
        """.utf8))
        XCTAssertNil(legacy.marqueeWhathit)
        let p = TournamentCardPresentation(
            data: legacy, hasLeader: true, runnerUpCount: 0, hasContext: true)
        XCTAssertTrue(p.showsProbabilityHero, "absence of authority is not settlement")
        XCTAssertFalse(p.showsChampion)
        XCTAssertFalse(p.showsFinalChip)
    }

    // MARK: - The mover line's field actually decodes

    /// L2-225: `movement_24h` never reached the card. `.convertFromSnakeCase` turns
    /// it into the key `movement24H` (`"24h".capitalized == "24H"` — the digit is not
    /// a letter, so the `h` is treated as the word's first letter), which matched no
    /// property. The "+2.3pp today" line was structurally dead.
    func testGolferMovement24hDecodesFromTheBackendKey() throws {
        let data = tournament(marqueeWhathit: false)
        let leader = try XCTUnwrap(data.golfers?.first)
        XCTAssertEqual(leader.movement24h, 2.3,
                       "movement_24h must survive .convertFromSnakeCase")
    }

    func testMissingMovementIsStillNil() throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let golfer = try dec.decode(FeedTournamentGolfer.self, from: Data("""
        {"name": "A", "probability": 12.0, "rank": 3}
        """.utf8))
        XCTAssertNil(golfer.movement24h)
        XCTAssertEqual(golfer.name, "A")
        XCTAssertEqual(golfer.rank, 3)
    }

    // MARK: - The two rules do not contradict each other

    func testWhatHitTournamentIsRenderedAndNotGatedOut() throws {
        // The stale gate must let the WHAT-HIT card through (it is the one settled
        // tournament we deliberately show) AND the card must render it result-first.
        // These are separate code paths; a regression in either alone is invisible.
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let item = try dec.decode(FeedItem.self, from: Data("""
        { "type": "tournament", "score": 90,
          "data": { "key": "the_open_championship", "name": "The Open",
                    "schedule_status": "completed",
                    "end_date": "2026-07-19T00:00:00Z",
                    "golfers": [{"name": "Scottie Scheffler", "probability": 62,
                                 "rank": 1, "movement_24h": 2.3}],
                    "is_marquee": true, "marquee_whathit": true } }
        """.utf8))
        let now = ISO8601DateFormatter().date(from: "2026-07-20T06:00:00Z")!
        XCTAssertFalse(DiscoverView.isStaleItem(item, now: now))
        let data = try XCTUnwrap(item.tournament)
        let p = TournamentCardPresentation(
            data: data, hasLeader: true, runnerUpCount: 0, hasContext: true)
        XCTAssertTrue(p.showsChampion)
        XCTAssertFalse(p.showsProbabilityHero)
    }
}
