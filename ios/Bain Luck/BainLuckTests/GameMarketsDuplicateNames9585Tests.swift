import XCTest
@testable import Bain_Luck

/// #9585 — a game page whose markets repeat a display name keeps updating.
///
/// FIXTURE: `Fixtures/event-14780549-game-markets-9585-bears-eagles.20260928.json`
/// (sha256 5ec2867a…5689), the retained production `/game-markets` body for
/// Bears 27–7 Eagles: 860 player props and, in `other`, four
/// `Both teams to score / Yes / kalshi` rows from markets 62436318, 62436323,
/// 62436317 and 62436319. Keyed by name alone they collided, the first body was
/// shown and every later body was discarded whole. Later reads here are the
/// same capture with an ordering clock and contributor id added to the four
/// rows. Nothing else in it changes.
@MainActor
final class GameMarketsDuplicateNames9585Tests: XCTestCase {
    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("event-14780549-game-markets-9585-bears-eagles.20260928.json")
    private static let bttsMarkets = [62436318, 62436323, 62436317, 62436319]
    private let t0 = "2030-01-01T00:00:00.000001Z"
    private let t1 = "2030-01-01T00:00:00.000002Z"
    private let t2 = "2030-01-01T00:00:00.000003Z"

    private func decode(_ dict: [String: Any]) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func specimen() throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    /// The capture with each BTTS row bound to its own contributor (900 + i)
    /// and clock. `prices`/`clocks`/`grades` are per market; a missing entry
    /// keeps the default (captured price, `t0`, ungraded).
    private func read(prices: [Int: Double?] = [:], clocks: [Int: String] = [:],
                      grades: [Int: Bool] = [:], reversed: Bool = false) throws -> GameMarketsResponse {
        var dict = try specimen()
        var other = try XCTUnwrap(dict["other"] as? [[String: Any]])
        var bindings: [String: Int] = [:]
        var revisions: [String: String] = [:]
        for index in other.indices {
            guard let market = other[index]["_market_id"] as? Int,
                  let slot = Self.bttsMarkets.firstIndex(of: market) else { continue }
            let contributor = 900 + slot
            other[index]["contributor_outcome_ids"] = [contributor]
            other[index]["is_winner"] = grades[market].map { $0 as Any } ?? NSNull()
            if let price = prices[market] { other[index]["probability"] = price.map { $0 as Any } ?? NSNull() }
            bindings[String(contributor)] = market
            revisions[String(contributor)] = clocks[market] ?? t0
        }
        dict["other"] = reversed ? Array(other.reversed()) : other
        dict["stream_market_ids"] = Self.bttsMarkets
        dict["outcome_market_ids"] = bindings
        dict["outcome_revision_at"] = revisions
        return try decode(dict)
    }

    private func btts(_ body: GameMarketsResponse, _ market: Int) -> GameMarketOther? {
        body.other?.first { $0._marketId == market && $0.marketName == "Both teams to score" }
    }

    // 1
    func testRealSpecimenDecodesWholeAndEachRepeatedNameGetsItsOwnIdentity() throws {
        let body = try decode(try specimen())
        XCTAssertEqual(body.playerProps?.count, 860)
        let rows = GameMarketsPriceReconciliation.rows(body)
        let identity = GameMarketsPriceReconciliation.identified(rows)
        XCTAssertTrue(identity.ambiguous.isEmpty)
        XCTAssertEqual(identity.rows.count, rows.count, "no row of the capture is lost or merged")
        XCTAssertEqual(Set(identity.rows.map(\.key)).count, rows.count)
        let keys = identity.rows.filter { $0.key.hasPrefix("other:Both teams to score-Yes") }.map(\.key)
        XCTAssertEqual(Set(keys).count, 4, "\(keys)")
    }

    // 2
    func testFirstBodyFencesAndAChangedQuoteOnItsOwnAdvancingClockAdopts() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        XCTAssertEqual(fence.revisions.count, 4, "the first body initialises the fences")
        let next = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436323: 0.02], clocks: [62436323: t1]), over: held, fence: &fence)
        XCTAssertEqual(btts(next, 62436323)?.probability, 0.02)
        XCTAssertEqual(btts(next, 62436318)?.probability, 0.99)
        XCTAssertEqual(btts(next, 62436317)?.probability, 0.01)
    }

    // 3
    func testReorderedRowsKeepTheirIdentitiesAndFences() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        let shuffled = GameMarketsPriceReconciliation.adopting(try read(reversed: true), over: held, fence: &fence)
        XCTAssertEqual(btts(shuffled, 62436318)?.probability, 0.99)
        let moved = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436319: 0.03], clocks: [62436319: t1], reversed: true), over: shuffled, fence: &fence)
        XCTAssertEqual(btts(moved, 62436319)?.probability, 0.03)
        XCTAssertEqual(btts(moved, 62436323)?.probability, 0.01, "a sibling of the same name did not borrow it")
    }

    // 4
    func testAPriceChangeOnAnUnchangedClockIsRefused() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        let refused = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436323: 0.5]), over: held, fence: &fence)
        XCTAssertEqual(btts(refused, 62436323)?.probability, 0.01)
        let accepted = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436323: 0.5], clocks: [62436323: t1]), over: refused, fence: &fence)
        XCTAssertEqual(btts(accepted, 62436323)?.probability, 0.5, "the same change on its own new clock adopts")
    }

    // 5
    func testOwnContributorWithdrawalThenRestorationBehindItsOwnClock() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        let withdrawn = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436317: Optional<Double>.none], clocks: [62436317: t1]), over: held, fence: &fence)
        XCTAssertNil(btts(withdrawn, 62436317)?.probability)
        XCTAssertEqual(btts(withdrawn, 62436318)?.probability, 0.99)
        let sibling = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436317: 0.2], clocks: [62436317: t1, 62436319: t2]), over: withdrawn, fence: &fence)
        XCTAssertNil(btts(sibling, 62436317)?.probability, "a same-named sibling's clock cannot restore it")
        let restored = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436317: 0.2], clocks: [62436317: t2, 62436319: t2]), over: sibling, fence: &fence)
        XCTAssertEqual(btts(restored, 62436317)?.probability, 0.2)
    }

    // 6
    func testGradesStayOnTheirOwnMarketAndCannotChange() throws {
        let graded: [Int: Bool] = [62436318: true, 62436323: false, 62436317: false, 62436319: false]
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(try read(grades: graded), over: nil, fence: &fence)
        XCTAssertEqual(btts(held, 62436318)?.isWinner, true)
        var flipped = graded
        flipped[62436318] = false
        flipped[62436323] = true
        let refused = GameMarketsPriceReconciliation.adopting(
            try read(clocks: [62436318: t1, 62436323: t1], grades: flipped), over: held, fence: &fence)
        XCTAssertEqual(refused, held, "a grade cannot move to a same-named sibling")
        var dropped = graded
        dropped[62436318] = nil
        XCTAssertEqual(GameMarketsPriceReconciliation.adopting(
            try read(clocks: [62436318: t1], grades: dropped), over: held, fence: &fence), held)
        let quoted = GameMarketsPriceReconciliation.adopting(
            try read(prices: [62436323: 0.02], clocks: [62436323: t1], grades: graded), over: held, fence: &fence)
        XCTAssertEqual(btts(quoted, 62436323)?.probability, 0.02, "graded same-named rows do not freeze a quote")
        XCTAssertEqual(btts(quoted, 62436318)?.isWinner, true)
        XCTAssertEqual(btts(quoted, 62436323)?.isWinner, false)
        XCTAssertEqual(quoted.status, "completed")
        XCTAssertEqual(quoted.homeScore, 27)
    }

    // 7
    func testConflictingOrIdlessRowsCannotFreezeAnUnrelatedMarket() throws {
        func body(duplicate: Double, idless: Double?, spread: Double, clock: String,
                  gradedTwice: Bool = false) throws -> GameMarketsResponse {
            let dupe: (Double) -> [String: Any] = {
                ["market_name": "Both teams to score", "outcome_name": "Yes", "probability": $0,
                 "source": "kalshi", "_market_id": 41]
            }
            var other: [[String: Any]] = [dupe(duplicate), dupe(1 - duplicate), dupe(1 - duplicate),
                ["market_name": "Anytime scorer", "outcome_name": "Nobody", "probability": idless.map { $0 as Any } ?? NSNull(),
                 "source": "sportsbooks"]]
            if gradedTwice {
                other.append(["market_name": "Graded", "outcome_name": "Yes", "probability": 1, "source": "kalshi",
                              "_market_id": 43, "is_winner": true])
                other.append(["market_name": "Graded", "outcome_name": "Yes", "probability": 0, "source": "kalshi",
                              "_market_id": 43, "is_winner": false])
            } else {
                other.append(["market_name": "Graded", "outcome_name": "Yes", "probability": 1, "source": "kalshi",
                              "_market_id": 43, "is_winner": true])
            }
            return try decode(["event_id": 12, "status": "live", "stream_market_ids": [42],
                "outcome_market_ids": ["5": 42], "outcome_revision_at": ["5": clock],
                "spreads": [["market_name": "Spread", "outcome_name": "Home -3.5", "probability": spread,
                             "source": "kalshi", "_market_id": 42, "contributor_outcome_ids": [5]]],
                "other": other])
        }
        let identity = GameMarketsPriceReconciliation.identified(GameMarketsPriceReconciliation.rows(
            try body(duplicate: 0.4, idless: 0.3, spread: 0.5, clock: t0)))
        XCTAssertEqual(identity.ambiguous.count, 3, "the conflicting group is set apart whole")
        XCTAssertEqual(GameMarketsPriceReconciliation.identified(GameMarketsPriceReconciliation.rows(
            try body(duplicate: 0.5, idless: 0.3, spread: 0.5, clock: t0))).ambiguous.count, 0,
            "exact full duplicates coalesce")

        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.4, idless: 0.3, spread: 0.5, clock: t0), over: nil, fence: &fence)
        let next = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.7, idless: 0.35, spread: 0.6, clock: t1), over: held, fence: &fence)
        XCTAssertEqual(next.spreads?.first?.probability, 0.6)
        let withdrawn = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.7, idless: nil, spread: 0.65, clock: t2), over: next, fence: &fence)
        XCTAssertEqual(withdrawn.spreads?.first?.probability, 0.65)
        let back = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.7, idless: 0.3, spread: 0.7, clock: "2030-01-01T00:00:00.000004Z"),
            over: withdrawn, fence: &fence)
        XCTAssertEqual(back.spreads?.first?.probability, 0.7, "an id-less row's return cannot hold the page")
        let conflicted = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.7, idless: 0.3, spread: 0.75, clock: "2030-01-01T00:00:00.000005Z",
                     gradedTwice: true), over: back, fence: &fence)
        XCTAssertEqual(conflicted.spreads?.first?.probability, 0.75,
                       "a graded row turning ambiguous does not read as a vanished grade")
        func graded(_ body: GameMarketsResponse) -> [GameMarketOther] {
            (body.other ?? []).filter { $0.marketName == "Graded" }
        }
        XCTAssertEqual(graded(conflicted).map(\.isWinner), [true], "the verified grade is what is shown, once")
        XCTAssertEqual(graded(conflicted).map(\.probability), [1])
        XCTAssertFalse((conflicted.other ?? []).contains { $0.marketName == "Both teams to score" },
                       "a conflicting group with nothing verified behind it is withheld, not guessed")
        let clear = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.7, idless: 0.3, spread: 0.8, clock: "2030-01-01T00:00:00.000006Z"),
            over: conflicted, fence: &fence)
        XCTAssertEqual(clear.spreads?.first?.probability, 0.8, "the conflict clearing holds nothing")
        XCTAssertEqual(graded(clear).map(\.isWinner), [true])

        var first = GameMarketsPriceReconciliation.Fence()
        let firstPaint = GameMarketsPriceReconciliation.adopting(
            try body(duplicate: 0.7, idless: 0.3, spread: 0.5, clock: t0, gradedTwice: true), over: nil, fence: &first)
        XCTAssertTrue(graded(firstPaint).isEmpty, "a contradictory grade never reaches the first paint either")
        XCTAssertEqual(firstPaint.spreads?.first?.probability, 0.5)
    }

    // 8 — Codex review of 9dcdc7f0, finding 1: a row's identity cannot depend
    // on whether a same-named peer in its own market is still served.
    func testASurvivorKeepsItsIdentityWhenItsSameMarketPeerComesAndGoes() throws {
        func body(peer: Bool, survivor: Double = 0.4, grade: Bool? = nil, clocks: [Int: String],
                  spread: Double, reversed: Bool = false) throws -> GameMarketsResponse {
            func row(_ contributor: Int, _ price: Double, _ winner: Bool?) -> [String: Any] {
                ["market_name": "Both teams to score", "outcome_name": "Yes", "probability": price,
                 "source": "kalshi", "_market_id": 41, "contributor_outcome_ids": [contributor],
                 "is_winner": winner.map { $0 as Any } ?? NSNull()]
            }
            var other = [row(101, survivor, grade)]
            if peer { other.append(row(102, 0.3, nil)) }
            var bindings = ["101": 41, "5": 42]
            if peer { bindings["102"] = 41 }
            return try decode(["event_id": 12, "status": "live", "stream_market_ids": [41, 42],
                "outcome_market_ids": bindings,
                "outcome_revision_at": Dictionary(uniqueKeysWithValues: clocks.map { (String($0.key), $0.value) }),
                "spreads": [["market_name": "Spread", "outcome_name": "Home -3.5", "probability": spread,
                             "source": "kalshi", "_market_id": 42, "contributor_outcome_ids": [5]]],
                "other": reversed ? Array(other.reversed()) : other])
        }
        func survivor(_ body: GameMarketsResponse) -> GameMarketOther? {
            body.other?.first { $0.contributorOutcomeIds == [101] }
        }
        let t3 = "2030-01-01T00:00:00.000004Z"
        for grade in [nil, true] as [Bool?] {
            var fence = GameMarketsPriceReconciliation.Fence()
            let held = GameMarketsPriceReconciliation.adopting(
                try body(peer: true, grade: grade, clocks: [101: t0, 102: t0, 5: t0], spread: 0.5),
                over: nil, fence: &fence)
            let alone = GameMarketsPriceReconciliation.adopting(
                try body(peer: false, grade: grade, clocks: [101: t0, 5: t1], spread: 0.6), over: held, fence: &fence)
            XCTAssertEqual(alone.spreads?.first?.probability, 0.6, "the peer leaving freezes nothing (grade \(String(describing: grade)))")
            XCTAssertEqual(survivor(alone)?.probability, 0.4)
            XCTAssertEqual(survivor(alone)?.isWinner, grade)
            let back = GameMarketsPriceReconciliation.adopting(
                try body(peer: true, grade: grade, clocks: [101: t0, 102: t2, 5: t2], spread: 0.7, reversed: true),
                over: alone, fence: &fence)
            XCTAssertEqual(back.spreads?.first?.probability, 0.7, "the peer returning on its own clock freezes nothing")
            XCTAssertEqual(back.other?.first { $0.contributorOutcomeIds == [102] }?.probability, 0.3)
            XCTAssertEqual(survivor(back)?.isWinner, grade)
            let borrowed = GameMarketsPriceReconciliation.adopting(
                try body(peer: true, survivor: 0.9, grade: grade, clocks: [101: t0, 102: t2, 5: t3], spread: 0.8),
                over: back, fence: &fence)
            XCTAssertEqual(survivor(borrowed)?.probability, 0.4,
                           "the survivor still cannot move on its unchanged clock or borrow an unrelated one")
        }
    }

    // 9 — Codex review of 9dcdc7f0, finding 2: a conflicting group's clock
    // neither lends a same-market sibling a revision nor is spent while it is
    // hidden, and what is shown meanwhile is the verified row, once.
    func testAConflictingGroupLendsNoClockAndSpendsNoneWhileHidden() throws {
        let t3 = "2030-01-01T00:00:00.000004Z"
        func body(conflict: Bool, over: Double = 0.4, yes: Double = 0.3,
                  clocks: [Int: String], spread: Double = 0.5) throws -> GameMarketsResponse {
            func row(_ market: String, _ outcome: String, _ price: Double, _ contributor: Int) -> [String: Any] {
                ["market_name": market, "outcome_name": outcome, "probability": price, "source": "kalshi",
                 "_market_id": 41, "contributor_outcome_ids": [contributor]]
            }
            var other = [row("Total goals", "Over", over, 101), row("Both teams to score", "Yes", yes, 102)]
            if conflict { other.append(row("Both teams to score", "Yes", 0.6, 102)) }
            return try decode(["event_id": 12, "status": "live", "stream_market_ids": [41, 42],
                "outcome_market_ids": ["101": 41, "102": 41, "5": 42],
                "outcome_revision_at": Dictionary(uniqueKeysWithValues: clocks.map { (String($0.key), $0.value) }),
                "spreads": [["market_name": "Spread", "outcome_name": "Home -3.5", "probability": spread,
                             "source": "kalshi", "_market_id": 42, "contributor_outcome_ids": [5]]],
                "other": other])
        }
        func prices(_ body: GameMarketsResponse, _ market: String) -> [Double?] {
            (body.other ?? []).filter { $0.marketName == market }.map(\.probability)
        }
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, clocks: [101: t0, 102: t0, 5: t0]), over: nil, fence: &fence)
        let lent = GameMarketsPriceReconciliation.adopting(
            try body(conflict: true, over: 0.9, clocks: [101: t0, 102: t1, 5: t0]), over: held, fence: &fence)
        XCTAssertEqual(prices(lent, "Total goals"), [0.4], "a hidden group's clock cannot move its market's sibling")
        let hidden = GameMarketsPriceReconciliation.adopting(
            try body(conflict: true, clocks: [101: t0, 102: t1, 5: t2], spread: 0.6), over: lent, fence: &fence)
        XCTAssertEqual(hidden.spreads?.first?.probability, 0.6)
        XCTAssertEqual(prices(hidden, "Both teams to score"), [0.3], "the verified row is shown, once")
        let clear = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, yes: 0.6, clocks: [101: t0, 102: t1, 5: t3], spread: 0.7),
            over: hidden, fence: &fence)
        XCTAssertEqual(prices(clear, "Both teams to score"), [0.6],
                       "the clock that advanced while hidden still orders the row once it is identifiable")
        XCTAssertEqual(clear.spreads?.first?.probability, 0.7)
    }

    // 10 — Codex review of db4f063d, correction 1: an older clock seen only on
    // conflicting rows cannot refuse the body; the same regression on an id a
    // published row still carries does.
    func testAnOlderClockOnlyOnConflictingRowsCannotFreezeAnUnrelatedSpread() throws {
        func body(conflict: Bool, clocks: [Int: String], spread: Double) throws -> GameMarketsResponse {
            func row(_ market: String, _ outcome: String, _ price: Double, _ contributor: Int) -> [String: Any] {
                ["market_name": market, "outcome_name": outcome, "probability": price, "source": "kalshi",
                 "_market_id": 41, "contributor_outcome_ids": [contributor]]
            }
            var other = [row("Total goals", "Over", 0.4, 101), row("Both teams to score", "Yes", 0.3, 102)]
            if conflict { other.append(row("Both teams to score", "Yes", 0.6, 102)) }
            return try decode(["event_id": 12, "status": "live", "stream_market_ids": [41, 42],
                "outcome_market_ids": ["101": 41, "102": 41, "5": 42],
                "outcome_revision_at": Dictionary(uniqueKeysWithValues: clocks.map { (String($0.key), $0.value) }),
                "spreads": [["market_name": "Spread", "outcome_name": "Home -3.5", "probability": spread,
                             "source": "kalshi", "_market_id": 42, "contributor_outcome_ids": [5]]],
                "other": other])
        }
        func prices(_ body: GameMarketsResponse, _ market: String) -> [Double?] {
            (body.other ?? []).filter { $0.marketName == market }.map(\.probability)
        }
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, clocks: [101: t1, 102: t1, 5: t0], spread: 0.5), over: nil, fence: &fence)
        let older = GameMarketsPriceReconciliation.adopting(
            try body(conflict: true, clocks: [101: t1, 102: t0, 5: t1], spread: 0.6), over: held, fence: &fence)
        XCTAssertEqual(older.spreads?.first?.probability, 0.6, "a hidden group's older clock freezes nothing")
        XCTAssertEqual(prices(older, "Both teams to score"), [0.3], "the verified row is still what is shown")
        XCTAssertEqual(fence.revisions["102"], FuturesPriceReconciliation.observationDate(t1),
                       "the hidden fence is not moved back")
        let regressed = GameMarketsPriceReconciliation.adopting(
            try body(conflict: true, clocks: [101: t0, 102: t1, 5: t2], spread: 0.7), over: older, fence: &fence)
        XCTAssertEqual(regressed, older, "a published row's regressed clock still refuses the body")
    }

    // 11 — Codex review of db4f063d, correction 2: one conflicting leg holds
    // its whole matchup, so its sibling legs' values are unpublished too and
    // may not spend their clocks while hidden.
    func testASiblingLegHiddenWithItsMatchupSpendsNoClockAndIsAcceptedOnceClear() throws {
        func body(conflict: Bool, away: Double?, clocks: [Int: String], spread: Double) throws -> GameMarketsResponse {
            func leg(_ name: String, _ price: Double?, _ contributor: Int) -> [String: Any] {
                ["name": name, "probability": price.map { $0 as Any } ?? NSNull(), "contributor_outcome_ids": [contributor]]
            }
            var legs = [leg("Home", 0.6, 201), leg("Away", away, 202)]
            if conflict { legs.append(leg("Home", 0.9, 201)) }
            return try decode(["event_id": 12, "status": "live", "stream_market_ids": [51, 42],
                "outcome_market_ids": ["201": 51, "202": 51, "5": 42],
                "outcome_revision_at": Dictionary(uniqueKeysWithValues: clocks.map { (String($0.key), $0.value) }),
                "spreads": [["market_name": "Spread", "outcome_name": "Home -3.5", "probability": spread,
                             "source": "kalshi", "_market_id": 42, "contributor_outcome_ids": [5]]],
                "matchups": [["market_name": "Match winner", "source": "kalshi", "_market_id": 51, "outcomes": legs]]])
        }
        func away(_ body: GameMarketsResponse) -> [Double?] {
            (body.matchups?.first?.outcomes ?? []).filter { $0.name == "Away" }.map(\.probability)
        }
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, away: 0.4, clocks: [201: t0, 202: t0, 5: t0], spread: 0.5),
            over: nil, fence: &fence)
        let hidden = GameMarketsPriceReconciliation.adopting(
            try body(conflict: true, away: 0.35, clocks: [201: t0, 202: t1, 5: t1], spread: 0.6),
            over: held, fence: &fence)
        XCTAssertEqual(hidden.spreads?.first?.probability, 0.6, "an unrelated verified spread keeps updating")
        XCTAssertEqual(hidden.matchups?.first?.outcomes.map(\.probability), [0.6, 0.4],
                       "the matchup is held whole; the sibling's new quote is not published")
        XCTAssertEqual(fence.revisions["202"], FuturesPriceReconciliation.observationDate(t0),
                       "the hidden sibling's clock is not spent")
        let clear = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, away: 0.35, clocks: [201: t0, 202: t1, 5: t2], spread: 0.7),
            over: hidden, fence: &fence)
        XCTAssertEqual(away(clear), [0.35], "the conflict clearing at the same revision publishes the sibling")
        XCTAssertEqual(clear.spreads?.first?.probability, 0.7)

        // A hidden sibling that goes unpriced for one read was never shown
        // withdrawn, so it leaves no withdrawal fence behind.
        var quiet = GameMarketsPriceReconciliation.Fence()
        let shown = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, away: 0.4, clocks: [201: t0, 202: t0, 5: t0], spread: 0.5),
            over: nil, fence: &quiet)
        let gap = GameMarketsPriceReconciliation.adopting(
            try body(conflict: true, away: nil, clocks: [201: t0, 202: t0, 5: t1], spread: 0.6),
            over: shown, fence: &quiet)
        XCTAssertEqual(away(gap), [0.4])
        let back = GameMarketsPriceReconciliation.adopting(
            try body(conflict: false, away: 0.4, clocks: [201: t0, 202: t0, 5: t2], spread: 0.7),
            over: gap, fence: &quiet)
        XCTAssertEqual(back.spreads?.first?.probability, 0.7, "an unpublished withdrawal holds nothing once clear")
        XCTAssertEqual(away(back), [0.4])
    }
}
