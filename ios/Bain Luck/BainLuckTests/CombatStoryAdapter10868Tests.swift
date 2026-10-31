import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's adapter, part three (finish method,
/// knockout chances, fighter rounds, fight length), on the REAL served game
/// matrix in `CombatOriginalsAdapter10868Tests.mmaMarkets` (a reduced verbatim
/// subset; source path, sha256 and what was kept are written there) and the
/// real UFC 332 detail (`CombatBoutPageAdapter10868Tests.mmaDetail`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// No production owner proves which matrix question belongs to which story:
/// every served question has `subject: null` and `predicate: null`. So the
/// FIRST test pins the production state — no membership, no card — and every
/// other test hands in a CONSTRUCTED `Membership`, as an owner would, naming
/// served `question_key`s. The membership, its labels, and the duration
/// windows and round schedule are test inputs, not facts read from the body.
///
/// Every served option is a venue result (`value_state: result`) with no
/// `pregame_reading`. Other CONSTRUCTED variants, each named where used,
/// change only the keys they name: `status: live` / `completed`, one option's
/// `published` / `result`, one option's `pregame_reading`, the matrix contract.
@MainActor
final class CombatStoryAdapter10868Tests: XCTestCase {
    private typealias S = CombatStoryAdapter10868
    private typealias M = S.Membership
    private typealias Fixtures = CombatBoutPageAdapter10868Tests
    private typealias Markets = CombatOriginalsAdapter10868Tests

    private func host(_ now: String) -> S.Host {
        S.Host(now: now.asDate!, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    private func clock(_ stamp: String, _ host: S.Host) -> String {
        CombatBoutPageAdapter10868.clockWords(stamp.asDate!, host: host.words)
    }

    /// CONSTRUCTED owner proofs, naming served question keys.
    private let methods = M(methods: [
        M.Row(id: "ko", label: "KO / TKO", questionKey: "m:63786874", overviewOptionKey: "o:240262496"),
        M.Row(id: "submission", label: "Submission", questionKey: "m:63634393"),
        M.Row(id: "decision", label: "Decision or draw", questionKey: "m:63786883"),
    ])
    private let knockout = M(knockout: [
        M.Row(id: "gautier", label: "Ateba Gautier", questionKey: "m:63786875", overviewOptionKey: "o:240262498"),
        M.Row(id: "kopylov", label: "Roman Kopylov", questionKey: "m:63900810", overviewOptionKey: "o:240654996"),
    ])
    private let rounds = M(rounds: [
        M.Fighter(id: "gautier", label: "Ateba Gautier", slots: [
            M.Slot(id: "gautier-1", label: "Round 1", questionKey: "m:63786882"),
            M.Slot(id: "gautier-2", label: "Round 2", questionKey: nil),
            M.Slot(id: "gautier-3", label: "Round 3", questionKey: "m:00000000"),
        ]),
        M.Fighter(id: "kopylov", label: "Roman Kopylov", slots: [
            M.Slot(id: "kopylov-1", label: "Round 1", questionKey: "m:63900818"),
        ]),
    ])
    private let segments = [
        CombatDurationSegment10868(id: "r1", shortLabel: "R1", spokenLabel: "Round 1"),
        CombatDurationSegment10868(id: "r2", shortLabel: "R2", spokenLabel: "Round 2"),
        CombatDurationSegment10868(id: "r3", shortLabel: "R3", spokenLabel: "Round 3"),
    ]
    private var duration: M {
        M(duration: M.Schedule(segments: segments, markets: [
            M.Window(id: "distance", label: "Go the distance", questionKey: "m:63254894",
                     windows: ["o:238409896": CombatDurationWindow10868(
                        label: "Reaches the final bell", start: 3, end: 3,
                        finalBell: .included("Includes the final bell"))]),
            M.Window(id: "early", label: "Ends before Round 2", questionKey: "m:63786880",
                     windows: ["o:240262508": CombatDurationWindow10868(
                        label: "Ends in Round 1", start: 0, end: 1,
                        finalBell: .excluded("Ends before the final bell"))]),
        ]))
    }

    /// The retained matrix omits every pin and says `not_quoted`: omission proves
    /// nothing, so a missing pre-match chance is "unavailable".
    private let unrecorded = "Pre-match chance unavailable"

    // MARK: - Production today

    func testWithoutAnOwnerProvedMembershipNoStoryCardIsBuilt() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try Markets.markets()
        let reader = host(Fixtures.readAt)
        for membership in [nil, M()] as [M?] {
            XCTAssertNil(S.methods(event, markets: markets, membership: membership, host: reader))
            XCTAssertNil(S.knockout(event, markets: markets, membership: membership, host: reader))
            XCTAssertNil(S.rounds(event, markets: markets, membership: membership, host: reader))
            XCTAssertNil(S.duration(event, markets: markets, membership: membership, host: reader))
        }
        XCTAssertNotNil(S.matrix(markets), "the matrix is readable; only its membership is unproved")
    }

    func testAnUnknownContractOrAnUnservedQuestionBuildsNoCard() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let reader = host(Fixtures.readAt)
        // CONSTRUCTED: the matrix contract changed.
        var body = try Markets.object(Markets.mmaMarkets)
        var matrix = try XCTUnwrap(body["game_question_matrix"] as? [String: Any])
        matrix["contract"] = "9999.v1"
        body["game_question_matrix"] = matrix
        let foreign = try Markets.decoded(body)
        XCTAssertNil(S.matrix(foreign))
        XCTAssertNil(S.methods(event, markets: foreign, membership: methods, host: reader))
        // A proved key the body does not serve.
        let unserved = M(methods: [M.Row(id: "x", label: "KO / TKO", questionKey: "m:00000000")])
        XCTAssertNil(S.methods(event, markets: try Markets.markets(), membership: unserved, host: reader))
        XCTAssertNil(S.methods(event, markets: nil, membership: methods, host: reader))
    }

    // MARK: - Finish method, during (the retained state)

    func testDuringEverySettledOptionKeepsItsOwnWordsAndNoChanceIsBorrowed() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let card = try XCTUnwrap(S.methods(event, markets: try Markets.markets(), membership: methods, host: host(Fixtures.readAt)))
        XCTAssertEqual(card.phase, .during)
        XCTAssertEqual(card.eventID, "15318681")
        XCTAssertEqual(card.title, "How could the fight end?")
        XCTAssertEqual(card.caption, "Pre-match and in-fight chances")
        XCTAssertEqual(card.eyebrow, "Polymarket · original markets")
        XCTAssertEqual(card.methods.map(\.id), ["ko", "submission", "decision"])
        XCTAssertEqual(card.methods.map(\.question), [
            "Will the fight be won by KO or TKO?", "Will the fight be won by submission?",
            "Will the fight end in a decision or draw?",
        ])
        let ko = card.methods[0]
        XCTAssertEqual(ko.originals.map(\.label), ["Yes", "No"], "served order, served labels")
        XCTAssertEqual(ko.originals.map(\.id), ["240262496", "240262497"])
        XCTAssertEqual(ko.originals.map(\.marketID), ["63786874", "63786874"])
        XCTAssertEqual(ko.overviewOriginalID, "240262496")
        XCTAssertNil(card.methods[1].overviewOriginalID)
        for original in card.methods.flatMap(\.originals) {
            XCTAssertNil(original.before)
            XCTAssertEqual(original.beforeMissing, unrecorded)
            XCTAssertEqual(original.current, .unavailable("In-fight chance unavailable"),
                           "a venue result is never an in-fight chance")
            XCTAssertEqual(original.result, .unconfirmed("Result unconfirmed"), "no grade before the final")
        }
        XCTAssertNil(card.actual, "no production field serves the official method")
        XCTAssertNil(card.timing)
        XCTAssertEqual(card.copy, .method)
    }

    // MARK: - Finish method, final (constructed)

    func testTheFinalGradesEachSideByTheServersOwnResultAndTimingNamesItsVenue() throws {
        // CONSTRUCTED: the detail's `status: completed`.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["status": "completed"])
        let held = S.Selection(rowID: "ko", originalID: "240262496")
        let card = try XCTUnwrap(S.methods(event, markets: try Markets.markets(), membership: methods,
                                           host: host(Fixtures.readAt), selection: held))
        XCTAssertEqual(card.phase, .final)
        XCTAssertEqual(card.caption, "Pre-match chances beside each contract’s result")
        XCTAssertEqual(card.methods.map { $0.originals.map(\.result) }, [
            [.won("Won"), .lost("Lost")],
            [.won("Won"), .lost("Lost")],
            [.won("Won"), .lost("Lost")],
        ], "KO Yes, submission No and decision No are the served winners — read in served order")
        XCTAssertEqual(card.methods[1].originals.map(\.label), ["No", "Yes"])
        XCTAssertEqual(card.selectedMethodID, "ko")
        XCTAssertEqual(card.selectedOriginalID, "240262496")
        XCTAssertEqual(card.timing, CombatMethodTiming10868(
            originalID: "240262496", title: "Yes · timing",
            lines: ["Pre-match chance: Pre-match chance unavailable", "Contract result: Won · settled by Polymarket"]))
    }

    func testAHeldOriginalThatIsNotReadHasNoTiming() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let card = try XCTUnwrap(S.methods(event, markets: try Markets.markets(), membership: methods,
                                           host: host(Fixtures.readAt),
                                           selection: S.Selection(rowID: "ko", originalID: "240654996")))
        XCTAssertNil(card.timing, "an original outside this card is never borrowed")
    }

    // MARK: - The pin (constructed)

    func testFromTheStartOnThePreMatchChanceIsTheOptionsOwnPin() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let reader = host(Fixtures.readAt)
        let at = "2026-10-04T00:12:00+00:00"
        // CONSTRUCTED: option o:240262496's `pregame_reading`.
        let markets = try Markets.editingOption(question: "m:63786874", option: "o:240262496",
                                                ["pregame_reading": Markets.pin(0.41, at: at, outcome: 240262496)])
        let ko = try XCTUnwrap(S.methods(event, markets: markets, membership: methods, host: reader)).methods[0]
        XCTAssertEqual(ko.originals[0].before, CombatMethodObservation10868(
            probability: 0.41, text: "41%", timeText: S.timeWords(at.asDate!, host: reader),
            detail: "Last recorded before start · \(clock(at, reader)) · Polymarket"))
        XCTAssertNil(ko.originals[1].before, "the No side has no pin of its own and borrows none")

        // CONSTRUCTED: an exact 1 is a settlement value, never a pin.
        let settled = try Markets.editingOption(question: "m:63786874", option: "o:240262496",
                                                ["pregame_reading": Markets.pin(1, at: at, outcome: 240262496)])
        XCTAssertNil(try XCTUnwrap(S.methods(event, markets: settled, membership: methods, host: reader)).methods[0].originals[0].before)
    }

    // MARK: - In-fight (constructed)

    func testOnlyALiveRecentQuoteAfterTheStartIsAnInFightChance() throws {
        let at = "2026-10-04T00:30:00+00:00"
        // CONSTRUCTED: option o:240262496 unsettled (`result` null) and quoted 0.62 at 00:30Z.
        let markets = try Markets.editingOption(question: "m:63786874", option: "o:240262496", [
            "result": NSNull(),
            "published": ["value": 0.62, "value_state": "quoted", "basis": "quote", "source": "polymarket",
                          "observed_at": at] as [String: Any],
        ])
        // CONSTRUCTED: `status: live`, read at 00:40Z.
        let live = try Fixtures.edited(Fixtures.mmaDetail, ["status": "live"])
        let fresh = host("2026-10-04T00:40:00Z")
        let current = try XCTUnwrap(S.methods(live, markets: markets, membership: methods, host: fresh)).methods[0].originals
        XCTAssertEqual(current[0].current, .recorded(CombatMethodObservation10868(
            probability: 0.62, text: "62%", timeText: S.timeWords(at.asDate!, host: fresh),
            detail: "Recorded \(clock(at, fresh)) · Polymarket"), movement: nil))
        XCTAssertEqual(current[1].current, .unavailable("In-fight chance unavailable"), "its settled No stays a result")

        // The retained suspended state withholds the same quote.
        let suspended = try Fixtures.detail(Fixtures.mmaDetail)
        let held = try XCTUnwrap(S.methods(suspended, markets: markets, membership: methods, host: fresh)).methods[0].originals
        XCTAssertEqual(held[0].current, .withheld("In-fight chance unavailable"))

        // An hour later it is not recent.
        let late = try XCTUnwrap(S.methods(live, markets: markets, membership: methods, host: host("2026-10-04T01:30:00Z")))
        XCTAssertEqual(late.methods[0].originals[0].current, .withheld(AllMarketsCatalogView9483.noRecentPrice))
    }

    func testAQuoteFromBeforeTheStartOrWithoutAClockIsNeverAnInFightChance() throws {
        let live = try Fixtures.edited(Fixtures.mmaDetail, ["status": "live"])
        let reader = host("2026-10-04T00:25:00Z")
        // CONSTRUCTED: quoted 0.58 at 00:10Z, before the 00:20Z start.
        let early = try Markets.editingOption(question: "m:63786874", option: "o:240262496", [
            "result": NSNull(),
            "published": ["value": 0.58, "value_state": "quoted", "basis": "quote", "source": "polymarket",
                          "observed_at": "2026-10-04T00:10:00+00:00"] as [String: Any],
        ])
        XCTAssertEqual(try XCTUnwrap(S.methods(live, markets: early, membership: methods, host: reader))
            .methods[0].originals[0].current, .unavailable("In-fight chance unavailable"))
        // CONSTRUCTED: quoted 0.58 with no clock.
        let undated = try Markets.editingOption(question: "m:63786874", option: "o:240262496", [
            "result": NSNull(),
            "published": ["value": 0.58, "value_state": "quoted", "basis": "quote", "source": "polymarket",
                          "observed_at": NSNull()] as [String: Any],
        ])
        XCTAssertEqual(try XCTUnwrap(S.methods(live, markets: undated, membership: methods, host: reader))
            .methods[0].originals[0].current, .withheld(AllMarketsCatalogView9483.noRecentPrice))
    }

    // MARK: - Knockout chances

    func testTheKnockoutCardIsItsOwnInputWithItsOwnWords() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let card = try XCTUnwrap(S.knockout(event, markets: try Markets.markets(), membership: knockout, host: host(Fixtures.readAt)))
        XCTAssertEqual(card.title, "Who wins by knockout?")
        XCTAssertEqual(card.copy, S.knockoutCopy)
        XCTAssertEqual(card.methods.map(\.label), ["Ateba Gautier", "Roman Kopylov"])
        XCTAssertEqual(card.methods.map(\.question), ["Will Ateba Gautier win by KO or TKO?", "Will Roman Kopylov win by KO or TKO?"])
        XCTAssertEqual(card.methods.map(\.overviewOriginalID), ["240262498", "240654996"])
        XCTAssertEqual(card.methods[0].originals.map(\.label), ["No", "Yes"], "served order")
        XCTAssertNil(S.methods(event, markets: try Markets.markets(), membership: knockout, host: host(Fixtures.readAt)),
                     "knockout rows never become finish methods")
    }

    // MARK: - Fighter rounds

    func testEachRoundSlotSaysWhetherItHasAMarketOrWhyNot() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let card = try XCTUnwrap(S.rounds(event, markets: try Markets.markets(), membership: rounds, host: host(Fixtures.readAt)))
        XCTAssertEqual(card.title, "Which round for each fighter?")
        XCTAssertEqual(card.groups.map(\.label), ["Ateba Gautier", "Roman Kopylov"])
        let gautier = card.groups[0].slots
        XCTAssertEqual(gautier.map(\.label), ["Round 1", "Round 2", "Round 3"])
        XCTAssertEqual(gautier[0].state.market?.question, "Will Ateba Gautier win in Round 1?")
        XCTAssertEqual(gautier[1].state, .noCapturedProp("No captured prop"))
        XCTAssertEqual(gautier[2].state, .unavailable("Unavailable in this update"),
                       "a proved key this update does not serve says so; no neighbour stands in")
        XCTAssertEqual(card.groups[1].slots[0].state.market?.originals.map(\.id), ["240655012", "240655013"])
        XCTAssertTrue(card.groups.flatMap(\.slots).compactMap(\.state.market).flatMap(\.originals).allSatisfy {
            $0.before == nil && $0.current == .unavailable("In-fight chance unavailable") && $0.resultDetail == nil
        })
        XCTAssertNil(card.finish, "no production field serves the official round")
    }

    func testTheFinalGradesRoundsByTheServedResult() throws {
        // CONSTRUCTED: the detail's `status: completed`.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["status": "completed"])
        let card = try XCTUnwrap(S.rounds(event, markets: try Markets.markets(), membership: rounds, host: host(Fixtures.readAt)))
        XCTAssertEqual(card.phase, .final)
        XCTAssertEqual(card.groups[0].slots[0].state.market?.originals.map(\.result), [.won("Won"), .lost("Lost")])
        XCTAssertEqual(card.groups[1].slots[0].state.market?.originals.map(\.result), [.won("Won"), .lost("Lost")])
    }

    // MARK: - Fight length

    func testEachDurationSideCarriesOnlyItsOwnProvedWindow() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let card = try XCTUnwrap(S.duration(event, markets: try Markets.markets(), membership: duration, host: host(Fixtures.readAt)))
        XCTAssertEqual(card.title, "How long could the fight last?")
        XCTAssertEqual(card.segments, segments)
        XCTAssertEqual(card.markets.map(\.id), ["distance", "early"])
        let distance = card.markets[0].originals
        XCTAssertEqual(distance.map(\.label), ["No", "Yes"])
        XCTAssertNil(distance[0].window)
        XCTAssertEqual(distance[0].windowMissing, "Time window unavailable", "an unproved window is said, never inferred")
        XCTAssertEqual(distance[1].window?.finalBell, .included("Includes the final bell"))
        XCTAssertEqual(card.markets[1].originals[0].window?.end, 1)
        XCTAssertNil(card.observed)
        XCTAssertNil(card.finish)
    }

    func testNoScheduleOrNoServedDurationMarketIsNoCard() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let reader = host(Fixtures.readAt)
        let empty = M(duration: M.Schedule(segments: segments, markets: []))
        XCTAssertNil(S.duration(event, markets: try Markets.markets(), membership: empty, host: reader))
        let unserved = M(duration: M.Schedule(segments: segments, markets: [
            M.Window(id: "x", label: "Go the distance", questionKey: "m:00000000", windows: [:]),
        ]))
        XCTAssertNil(S.duration(event, markets: try Markets.markets(), membership: unserved, host: reader))
    }
}
