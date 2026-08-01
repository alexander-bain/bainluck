import XCTest
@testable import Bain_Luck

/// L2-225 — the native "settled means settled" contract, card type by card type.
///
/// L2-191 built the Discover stale gate for futures and events and stopped there;
/// L2-224 repaired the tournament DECODE and its WHAT-HIT render. Nothing tied the
/// two together, so three different predicates answered "is this over?" three
/// different ways:
///
///  * `DiscoverView.isStaleItem` consulted 2 of the 4 futures authorities web reads,
///    and had **no tournament branch at all**;
///  * `DiscoverViewModel.futuresIsSettled` consulted 1 of the 4;
///  * `FeedFuturesData` did not decode `resolved` / `winner`, so neither predicate
///    could have consulted them.
///
/// These fixtures are built from the committed backend payload shapes
/// (`routes/feed.py` `_score_golf_tournaments` / `_score_event_concepts` / the
/// futures serialization) and pin the shared `FeedLifecycle` semantic against web's
/// `_futuresIsSettled` / `feedItemSuppressionReason` (`discover/utils.ts`).
///
/// `now` is injected everywhere so nothing straddles a real-world date boundary
/// (gotcha #44).
final class NativeLifecycleTerminalTests: XCTestCase {

    /// Fixed reference instant. All relative fixtures are expressed against it.
    private let now = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!
    private let past = "2026-07-20T00:00:00Z"      // a week before `now`
    private let recentPast = "2026-07-27T06:00:00Z" // 6h before `now`
    private let future = "2026-08-20T00:00:00Z"    // a month after `now`

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func item(_ json: String) throws -> FeedItem {
        try decoder().decode(FeedItem.self, from: Data(json.utf8))
    }

    // MARK: - Fixture builders (backend payload shapes)

    /// A futures card. Every lifecycle key is a RAW JSON literal so a caller can
    /// exercise absence (`null`), a wrong type, or a real value.
    private func futures(
        id: Int = 1,
        status: String = "\"open\"",
        resolutionDate: String = "null",
        resolved: String = "null",
        winner: String = "null",
        outcomes: String = """
        [{"id": 10, "name": "Team A", "probability": 0.55, "rank": 1, "movement": 0.02}]
        """
    ) throws -> FeedItem {
        try item("""
        {
          "type": "futures", "score": 90,
          "data": {
            "id": \(id), "name": "Who wins market \(id)?",
            "llm_sport_category": "politics", "source": "kalshi",
            "status": \(status),
            "resolution_date": \(resolutionDate),
            "resolved": \(resolved),
            "winner": \(winner),
            "top_outcomes": \(outcomes),
            "outcome_count": 1
          }
        }
        """)
    }

    /// A tournament card, matching `_score_golf_tournaments`' emitted `data`.
    private func tournament(
        key: String = "rocket_classic",
        scheduleStatus: String = "null",
        endDate: String = "null",
        marqueeWhathit: String = "false",
        golfers: String = """
        [{"name": "Scottie Scheffler", "probability": 24.5, "rank": 1, "movement_24h": 2.3}]
        """
    ) throws -> FeedItem {
        try item("""
        {
          "type": "tournament", "score": 80,
          "data": {
            "key": "\(key)", "name": "Rocket Classic", "tour": "pga",
            "tour_label": "PGA Tour", "is_major": false,
            "schedule_status": \(scheduleStatus),
            "end_date": \(endDate),
            "resolution_date": \(endDate),
            "golfers": \(golfers),
            "source_count": 2,
            "is_marquee": true,
            "marquee_whathit": \(marqueeWhathit)
          }
        }
        """)
    }

    /// A concept hub card, matching `_score_event_concepts`' emitted `data`.
    private func concept(
        status: String = "\"live\"",
        marqueeWhathit: String = "false",
        winner: String = "null"
    ) throws -> FeedItem {
        try item("""
        {
          "type": "concept", "score": 85,
          "data": {
            "key": "event:cycling:tour-de-france-2026", "name": "Tour de France 2026",
            "domain": "cycling", "status": \(status), "is_major": true,
            "fight_count": 0, "entry_count": 176,
            "is_marquee": true, "marquee_whathit": \(marqueeWhathit),
            "winner": \(winner), "result_summary": null
          }
        }
        """)
    }

    // MARK: - Futures: all four authorities (web `_futuresIsSettled` parity)

    func testFuturesOpenWithFutureResolutionIsNotStale() throws {
        XCTAssertFalse(
            DiscoverView.isStaleItem(
                try futures(resolutionDate: "\"\(future)\""), now: now))
    }

    func testFuturesTerminalStatusIsStale() throws {
        // The full web `_SETTLED_STATUSES` set, not just closed/resolved.
        for status in ["resolved", "closed", "settled", "finalized", "final"] {
            XCTAssertTrue(
                DiscoverView.isStaleItem(try futures(status: "\"\(status)\""), now: now),
                "status '\(status)' must settle a futures card")
        }
    }

    func testFuturesStatusIsCaseInsensitive() throws {
        XCTAssertTrue(
            DiscoverView.isStaleItem(try futures(status: "\"RESOLVED\""), now: now))
    }

    func testFuturesPastResolutionDateIsStale() throws {
        // The authority that actually fires in production: gotcha #33 keeps a
        // settled Kalshi market at status='open' forever.
        XCTAssertTrue(
            DiscoverView.isStaleItem(
                try futures(resolutionDate: "\"\(past)\""), now: now))
    }

    func testFuturesResolvedFlagIsStaleEvenWhenStatusIsOpen() throws {
        // Previously invisible: the model didn't decode `resolved`.
        XCTAssertTrue(
            DiscoverView.isStaleItem(
                try futures(status: "\"open\"", resolved: "true"), now: now))
    }

    func testFuturesNamedWinnerIsStaleEvenWhenStatusIsOpen() throws {
        XCTAssertTrue(
            DiscoverView.isStaleItem(
                try futures(status: "\"open\"", winner: "\"Team A\""), now: now))
    }

    func testFuturesBlankWinnerIsNotAuthority() throws {
        // A whitespace-only winner is not a graded result — never fabricate one.
        XCTAssertFalse(
            DiscoverView.isStaleItem(try futures(winner: "\"   \""), now: now))
        XCTAssertFalse(
            DiscoverView.isStaleItem(try futures(resolved: "false"), now: now))
    }

    func testFuturesProbabilityAloneNeverSettles() throws {
        // L2-214: a near-certain OPEN market is still a valid prediction.
        let nearCertain = try futures(
            resolutionDate: "\"\(future)\"",
            outcomes: """
            [{"id": 10, "name": "Team A", "probability": 0.995, "rank": 1, "movement": 0.0}]
            """)
        XCTAssertFalse(DiscoverView.isStaleItem(nearCertain, now: now))
    }

    // MARK: - Tournament: the branch that did not exist

    func testTournamentScheduleCompletedIsStale() throws {
        XCTAssertTrue(
            DiscoverView.isStaleItem(
                try tournament(scheduleStatus: "\"completed\""), now: now),
            "a completed tournament must not lead with a live leader hero")
    }

    func testTournamentLongPastEndDateIsStale() throws {
        XCTAssertTrue(
            DiscoverView.isStaleItem(try tournament(endDate: "\"\(past)\""), now: now))
    }

    func testTournamentInsideEndGraceIsNotStale() throws {
        // The client gate must never be MORE aggressive than the producer's own
        // `_filter_stale_tournaments` grace — a final round still in progress on the
        // listed end date must survive.
        XCTAssertFalse(
            DiscoverView.isStaleItem(
                try tournament(endDate: "\"\(recentPast)\""), now: now))
    }

    func testTournamentUpcomingIsNotStale() throws {
        XCTAssertFalse(
            DiscoverView.isStaleItem(
                try tournament(scheduleStatus: "\"upcoming\"", endDate: "\"\(future)\""),
                now: now))
    }

    func testTournamentMissingLifecycleFieldsIsNotStale() throws {
        // Unknown authority stays unknown and surfaces (L2-214) — the legacy payload
        // shape, before `schedule_status`/`end_date` were populated, must not vanish.
        XCTAssertFalse(DiscoverView.isStaleItem(try tournament(), now: now))
    }

    func testWhatHitTournamentSurvivesEvenWhenOver() throws {
        // The T+36h WHAT-HIT window is the ONE place a finished tournament is
        // deliberately shown — result-first (#235 Item 4 / L2-224). Gating it would
        // delete the very card the ruling asks for.
        let whatHit = try tournament(
            scheduleStatus: "\"completed\"",
            endDate: "\"\(past)\"",
            marqueeWhathit: "true")
        XCTAssertFalse(DiscoverView.isStaleItem(whatHit, now: now))
        XCTAssertNil(DiscoverViewModel.suppressionReason(whatHit))
    }

    // MARK: - Concept

    func testSettledConceptOutsideWhatHitIsStale() throws {
        XCTAssertTrue(
            DiscoverView.isStaleItem(
                try concept(status: "\"completed\"", marqueeWhathit: "false"), now: now))
    }

    func testWhatHitConceptSurvives() throws {
        let whatHit = try concept(
            status: "\"completed\"", marqueeWhathit: "true", winner: "\"Tadej Pogačar\"")
        XCTAssertFalse(DiscoverView.isStaleItem(whatHit, now: now))
        XCTAssertNil(DiscoverViewModel.suppressionReason(whatHit))
    }

    func testLiveConceptIsNotStaleButIsSuppressedAsEmptyEnvelope() throws {
        // Two independent rules, both correct: nothing about a live concept is
        // *stale*, but it carries no outcome to predict, so #1486 fails it closed —
        // exactly as web does (`feedItemSuppressionReason` → "empty_concept").
        let live = try concept(status: "\"live\"")
        XCTAssertFalse(DiscoverView.isStaleItem(live, now: now))
        XCTAssertEqual(DiscoverViewModel.suppressionReason(live), "empty_concept")
    }

    // MARK: - Suppression parity with web `_futuresIsSettled`

    func testZeroOutcomeFuturesSettledByResolvedFlagIsNotAnEmptyEnvelope() throws {
        // Web keeps this card (it carries an authoritative result); native used to
        // call it "empty_futures" because its settlement check read `status` only.
        let settled = try futures(
            status: "\"open\"", resolved: "true", winner: "\"Team A\"", outcomes: "[]")
        XCTAssertNil(DiscoverViewModel.suppressionReason(settled))
    }

    func testZeroOutcomeFuturesSettledByPastResolutionDateIsNotAnEmptyEnvelope() throws {
        let settled = try futures(resolutionDate: "\"\(past)\"", outcomes: "[]")
        XCTAssertNil(DiscoverViewModel.suppressionReason(settled))
    }

    func testZeroOutcomeOpenFuturesIsStillAnEmptyEnvelope() throws {
        let empty = try futures(resolutionDate: "\"\(future)\"", outcomes: "[]")
        XCTAssertEqual(DiscoverViewModel.suppressionReason(empty), "empty_futures")
    }

    // MARK: - Terminal fields survive tolerant decode

    func testTerminalFuturesFieldsAreDecodedNotDropped() throws {
        let decoded = try futures(
            status: "\"resolved\"",
            resolutionDate: "\"\(past)\"",
            resolved: "true",
            winner: "\"Team A\"")
        let data = try XCTUnwrap(decoded.futures)
        XCTAssertEqual(data.resolved, true)
        XCTAssertEqual(data.winner, "Team A")
        XCTAssertEqual(data.status, "resolved")
        XCTAssertEqual(data.resolutionDate, past)
    }

    func testLegacyFuturesPayloadWithoutTerminalFieldsStillDecodes() throws {
        // A payload predating `resolved`/`winner` must decode with nils, not throw.
        let legacy = try item("""
        {
          "type": "futures", "score": 40,
          "data": { "id": 7, "name": "Legacy market", "status": "open",
                    "top_outcomes": [], "outcome_count": 0 }
        }
        """)
        let data = try XCTUnwrap(legacy.futures)
        XCTAssertNil(data.resolved)
        XCTAssertNil(data.winner)
        XCTAssertFalse(DiscoverView.isStaleItem(legacy, now: now))
    }

    func testWrongTypedLifecycleFieldsDoNotFabricateSettlement() throws {
        // `resolved` as a string and `resolution_date` as a number: the whole item
        // fails to decode rather than half-decoding into a fake terminal state. It
        // is dropped by the tolerant loop, which is the honest outcome — a card that
        // cannot be trusted is not shown, and no winner is invented.
        let json = """
        {
          "items": [
            { "type": "futures", "score": 50,
              "data": { "id": 1, "name": "Bad types", "status": "open",
                        "resolved": "yes", "resolution_date": 12345,
                        "top_outcomes": [], "outcome_count": 0 } },
            { "type": "futures", "score": 50,
              "data": { "id": 2, "name": "Healthy", "status": "open",
                        "top_outcomes": [{"id": 20, "name": "A", "probability": 0.5,
                                          "rank": 1, "movement": null}],
                        "outcome_count": 1 } }
          ], "total": 2, "limit": 50, "offset": 0, "hasMore": false
        }
        """
        let response = try decoder().decode(FeedResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.items.count, 1, "the malformed sibling loses only itself")
        XCTAssertEqual(response.items.first?.futures?.id, 2)
    }

    // MARK: - Sibling containment: malformed FIRST / MIDDLE / LAST

    /// L2-224 proved this for the widget decoder; the main app's `FeedResponse` skip
    /// loop had only ever been exercised with a malformed card in the MIDDLE.
    func testOneMalformedCardNeverTakesItsSiblingsAtAnyPosition() throws {
        let healthy = """
        { "type": "futures", "score": 50,
          "data": { "id": %ID%, "name": "Healthy %ID%", "status": "open",
                    "top_outcomes": [{"id": 1, "name": "A", "probability": 0.5,
                                      "rank": 1, "movement": null}],
                    "outcome_count": 1 } }
        """
        let broken = #"{ "type": 42 }"#  // `type` is required and must be a String
        let a = healthy.replacingOccurrences(of: "%ID%", with: "1")
        let b = healthy.replacingOccurrences(of: "%ID%", with: "2")

        for (label, items) in [
            ("first", [broken, a, b]),
            ("middle", [a, broken, b]),
            ("last", [a, b, broken]),
        ] {
            let json = """
            { "items": [\(items.joined(separator: ","))],
              "total": 3, "limit": 50, "offset": 0, "hasMore": false }
            """
            let response = try decoder().decode(FeedResponse.self, from: Data(json.utf8))
            XCTAssertEqual(response.items.count, 2, "malformed-\(label) must lose only itself")
            XCTAssertEqual(response.items.map { $0.futures?.id }, [1, 2],
                           "malformed-\(label) must preserve sibling order")
        }
    }

    func testNonObjectElementsAreSkippedWithoutHanging() throws {
        let json = """
        { "items": [ null, "nope", 7, [1,2], true,
            { "type": "futures", "score": 50,
              "data": { "id": 9, "name": "Survivor", "status": "open",
                        "top_outcomes": [{"id": 1, "name": "A", "probability": 0.5,
                                          "rank": 1, "movement": null}],
                        "outcome_count": 1 } } ],
          "total": 6, "limit": 50, "offset": 0, "hasMore": false }
        """
        let response = try decoder().decode(FeedResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.items.count, 1)
        XCTAssertEqual(response.items.first?.futures?.id, 9)
    }

    // MARK: - Identity is stable across a lifecycle transition

    func testFeedItemIdentityIsStableFromLiveToTerminal() throws {
        let live = try item("""
        { "type": "event", "score": 90,
          "data": { "id": 4242, "home_team": "Celtics", "away_team": "Lakers",
                    "status": "live", "commence_time": "2026-07-27T11:00:00Z",
                    "home_score": 80, "away_score": 78 } }
        """)
        let terminal = try item("""
        { "type": "event", "score": 30,
          "data": { "id": 4242, "home_team": "Celtics", "away_team": "Lakers",
                    "status": "completed", "commence_time": "2026-07-27T11:00:00Z",
                    "home_score": 104, "away_score": 99 } }
        """)
        // Same card, updated in place — SwiftUI must diff the row, not rebuild it.
        XCTAssertEqual(live.id, terminal.id)
        XCTAssertEqual(terminal.id, "event-4242")
        // A just-finished game is not stale yet (the 8h FINAL window); the same game
        // eight hours later is.
        XCTAssertFalse(DiscoverView.isStaleItem(terminal, now: now))
        XCTAssertTrue(
            DiscoverView.isStaleItem(
                terminal,
                now: ISO8601DateFormatter().date(from: "2026-07-27T20:00:00Z")!))
    }

    func testTournamentIdentityIsStableIntoTheWhatHitWindow() throws {
        let live = try tournament(marqueeWhathit: "false")
        let whatHit = try tournament(
            scheduleStatus: "\"completed\"", marqueeWhathit: "true")
        XCTAssertEqual(live.id, whatHit.id)
        XCTAssertEqual(whatHit.id, "tournament-rocket_classic")
    }

    // MARK: - Bundles: one terminal child never takes a healthy sibling

    func testBundleDropsTerminalChildrenAndKeepsHealthyOnes() throws {
        let bundle = try item("""
        {
          "type": "bundle", "score": 70,
          "bundle": {
            "id": "story:test", "title": "A story", "kind": "theme",
            "items": [
              { "type": "futures", "score": 60,
                "data": { "id": 1, "name": "Settled", "status": "resolved",
                          "top_outcomes": [{"id": 1, "name": "A", "probability": 0.9,
                                            "rank": 1, "movement": null}],
                          "outcome_count": 1 } },
              { "type": "futures", "score": 60,
                "data": { "id": 2, "name": "Open", "status": "open",
                          "resolution_date": "\(future)",
                          "top_outcomes": [{"id": 2, "name": "B", "probability": 0.4,
                                            "rank": 1, "movement": null}],
                          "outcome_count": 1 } }
            ]
          }
        }
        """)
        let sanitized = DiscoverView.sanitizedFeedItems([bundle], now: now)
        XCTAssertEqual(sanitized.count, 1)
        XCTAssertEqual(sanitized.first?.bundle?.items.map { $0.futures?.id }, [2])
    }
}
