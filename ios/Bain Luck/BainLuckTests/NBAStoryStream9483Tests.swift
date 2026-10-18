import XCTest
@testable import Bain_Luck

/// #9483 — the compact NBA story stream's policy (brief v445 + Lane1's W1–W3):
/// which card leads, the one factual sentence a led card carries, and the
/// stream's applied / pending / active / held state. Fixed clocks only
/// (gotcha #44).
///
/// Two real games (v445 "Evidence"):
/// - POSITIVE, Toronto at New York 15327183, Knicks 122–120 Raptors, total 242:
///   Over 236.5 `o:247932394` has its own pregame pin 30% at
///   2026-10-15T23:18:45.654504Z and its own Won result; the admitted margin
///   lines carry no pin. The card is built here from those packet values (the
///   pin path from the served matrix is `NBAEventCards9483Tests`' to pin).
/// - NEGATIVE, Clippers 104–101 Warriors 15320337, read through the real
///   builder from the retained final body: Over 206.5 `o:240505185` is Lost
///   with no pregame pin, so nothing ranks and no sentence is said.
///
/// What these pin, and the mutation each kills:
/// - lose the scoring-first final story, or misword it → `testTheRealPositiveLeadsWithTheScoringCardAndSaysWhy`
/// - rank or explain a line with no pin → `testTheRealNegativeKeepsTheDeliveredOrderAndSaysNothing`
/// - rank before tip-off → `testBeforeTipOffKeepsTheDeliveredOrderWithNoReasons`
/// - admit a 0/1/out-of-range pin, or refuse a real one at the edge → `testOnlyAPinStrictlyBetweenZeroAndOneRanks`
/// - rank on a number the card does not draw → `testAPinTheCardDoesNotDrawIsNoCandidate`
/// - round or epsilon the order → `testValuesSortByExactDoubles`
/// - break ties by order, numerically, or total first → `testEqualValuesBreakByOptionKeyThenMarginBeforeTotal`
/// - drop, repeat or manufacture a card; let finish lead → `testEveryCardStaysReachableOnceInAMixedDeck`
/// - keep a live reason past the card's own currentness (W2) → `testTheLiveReasonEndsExactlyWhereTheQuoteStopsBeingCurrent`
/// - explain a withdrawn, suspended or undatable quote → `testAWithdrawnOrUndatableQuoteGivesNoLiveReason`
/// - explain a result without its actual, or against it → `testAFinalSentenceNeedsTheOwnResultAndAMatchingActual`
/// - leak the private value into either sentence → `testTheSentencesNameOnlyTheirFacts`
/// - print a percent the card under the sentence does not (half-cent rounding,
///   or 0% / 100% for a strict pin the card prints as <1% / >99%) → `testTheSentencePrintsTheCardsOwnPercent`
/// - explain a ladder whose phase is not the stream's → `testALadderInAnotherPhaseGivesNoReason`
/// - let a producer update move the applied order → `testReceiveReplacesPendingAndOnlyApplyMovesTheOrder`
/// - let an old event's callback write, or carry it into the next → `testAnotherEventsPlanIsRefusedAndANewEventStartsClean`
/// - silently replace a held card that left (W1) → `testAHeldActiveCardThatLeavesKeepsItsUnavailableSlot`
/// - pick a different neighbour than the reader → `testUnheldRemovalPicksTheReadersNeighbour`
/// - stop wrapping, wrap by hand, or spin on 0/1 cards → `testAutomaticNextWrapsAndSmallCountsStayPut`
/// - hold on a card the shelf does not show → `testFocusHoldsOnlyOnAShelfCard`
/// Receiver integration with the page's `NFLCardDeckState9483` (file 3):
/// - select a neighbour, another event's or a pending card's line → `testSeeThisLineSelectsOnlyTheExactAppliedOption`
/// - carry the old event's stream or ladder selection → `testANewEventDiscardsTheOldStreamAndItsLadderSelection`
/// - show pending cards to the reader, or advance while held → `testTheReaderGetsTheAppliedOrderAndAHeldStreamDoesNotAdvance`
/// Admission through the page's own seam (native, 4bbd44ecd1; `Page.deckReady` + `admit`):
/// - begin on the half-loaded deck (the finish card alone) and park the ladders
///   as pending behind Refresh, or begin on another event's markets or without
///   the history → `testTheStreamBeginsOnlyOnceThisEventsHistoryAndMarketsHaveArrived`
/// - count the page's bars twice in the stream's viewport → `testTheUsableViewportIsThePagesSafeAreaRectangle`
/// - before the begin: drop See this line, lose the reader's hold or chosen
///   card at the begin, or show the reader another order than the shelf (N4)
///   → `testBeforeTheStreamBeginsTheShelfsActionsWorkAndTheReadersChoiceSurvivesTheBegin`
@MainActor
final class NBAStoryStream9483Tests: XCTestCase {
    private typealias Policy = NBAStoryStreamPolicy9483

    private func date(_ iso: String) -> Date { iso.asDate! }

    // MARK: - Cards

    private let pinAt = "2026-10-15T23:18:45.654504Z"
    /// A whole-second live clock, so t0 + 1800 s is exact.
    private let liveAt = "2026-10-16T01:10:00Z"
    private lazy var liveNow = date("2026-10-16T01:20:00Z")
    private lazy var finalNow = date("2026-10-16T03:00:00Z")

    private func point(_ key: String, x: Double, label: String, side: NBALadderCard9483.Side = .game,
                       pin: Double?, pinAt: String? = nil, now: Double? = nil, observedAt: String? = nil,
                       result: Bool? = nil, drawn: Double?? = .none) -> NBALadderCard9483.Point {
        let baselineAt = pin == nil ? nil : (pinAt ?? self.pinAt)
        return .init(optionKey: key, x: x, label: label, side: side, chance: drawn ?? pin, now: now,
                     observedAt: observedAt, result: result,
                     detail: .init(label: label, marketName: label, source: "kalshi", quoted: now,
                                   observedAt: observedAt, baseline: pin, baselineObservedAt: baselineAt,
                                   result: result))
    }

    private func over(_ line: Double, key: String, pin: Double?, now: Double? = nil, observedAt: String? = nil,
                      result: Bool? = nil) -> NBALadderCard9483.Point {
        point(key, x: line, label: "Over \(NBALadderCard9483.number(line))", pin: pin, now: now,
              observedAt: observedAt ?? (now == nil ? nil : liveAt), result: result)
    }

    private func ladder(_ family: NBALadderCard9483.Family, _ phase: NBALadderCard9483.Phase,
                        _ points: [NBALadderCard9483.Point], actual: Double? = nil) -> NFLEventCard9483 {
        .ladder(NBALadderCard9483(family: family, phase: phase, points: points, actual: actual, forecast: nil,
                                  awayShort: "Raptors", homeShort: "Knicks"))
    }

    private var finish: NFLEventCard9483 { .finish(NFLFinishCard9483(
        phase: .after, pregame: .init(away: 113, home: 118, at: nil), projectedNow: nil,
        final: .init(away: 120, home: 122, at: nil), tickStep: 20, startWord: "tip-off")) }

    /// 15327183 after the final, from the v445 packet's values.
    private func positiveDeck() -> [NFLEventCard9483] {
        let margin = ladder(.margin, .after, [
            point("o:m-away-3", x: -3.5, label: "Raptors by 4+", side: .away, pin: nil, result: false),
            point("o:m-home-1", x: 1.5, label: "Knicks by 2+", side: .home, pin: nil, result: true),
            point("o:m-home-3", x: 3.5, label: "Knicks by 4+", side: .home, pin: nil, result: false),
        ], actual: 2)
        let total = ladder(.total, .after, [
            over(230.5, key: "o:t-230", pin: nil, result: true),
            over(236.5, key: "o:247932394", pin: 0.30, result: true),
            over(244.5, key: "o:t-244", pin: nil, result: false),
        ], actual: 242)
        return [margin, total, finish]
    }

    // MARK: - Real games

    func testTheRealPositiveLeadsWithTheScoringCardAndSaysWhy() throws {
        let plan = Policy.plan(eventID: 15327183, phase: .after, cards: positiveDeck(), now: finalNow)
        XCTAssertEqual(plan.orderedIDs, ["total", "margin", "finish"], "scoring first; the unpinned margin keeps its place")
        XCTAssertEqual(Array(plan.reasons.keys), ["total"])
        let reason = try XCTUnwrap(plan.reasons["total"])
        XCTAssertEqual(reason.eventID, 15327183)
        XCTAssertEqual(reason.optionKey, "o:247932394")
        XCTAssertEqual(reason.phase, .after)
        XCTAssertEqual(reason.baseline, 0.30)
        XCTAssertEqual(reason.baselineObservedAt, pinAt)
        XCTAssertEqual(reason.won, true)
        XCTAssertEqual(reason.actual, 242)
        XCTAssertNil(reason.current)
        XCTAssertNil(reason.expiry, "a final reason has no live deadline")
        XCTAssertNil(plan.nearestExpiry)
        XCTAssertEqual(reason.text, "Over 236.5 points: 30% before tip-off; final total 242.")
        let at = try XCTUnwrap(SourceAge.preciseStamp(pinAt))
        XCTAssertEqual(reason.accessibilityText, "Over 236.5 points. 30% before tip-off, quoted \(at). Final total 242.")
    }

    private struct Body: Decodable {
        let homeScore: Int?
        let awayScore: Int?
        let gameQuestionMatrix: EventQuestionMatrix?
    }

    func testTheRealNegativeKeepsTheDeliveredOrderAndSaysNothing() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/event-15320337-game-matrix-9483-nba-final.20261015.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let body = try decoder.decode(Body.self, from: Data(contentsOf: url))
        let now = date("2026-10-05T04:00:00Z")
        let input = NBALadderCard9483.Input(
            matrix: body.gameQuestionMatrix, status: "completed", commenceTime: date("2026-10-04T23:00:00Z"),
            homeScore: body.homeScore, awayScore: body.awayScore, pregameProjection: nil,
            homeShort: "Clippers", awayShort: "Warriors", now: now)
        let total = try XCTUnwrap(NBALadderCard9483.total(input))
        let over2065 = try XCTUnwrap(total.points.first { $0.optionKey == "o:240505185" })
        XCTAssertEqual(over2065.result, false, "the specimen is the Lost Over 206.5")
        XCTAssertNil(over2065.detail.baseline, "with no pregame pin")
        let ladders = [NBALadderCard9483.margin(input), total].compactMap { $0 }
        let deck = NFLEventCardDeck9483.cards(sportKey: "basketball_nba", finish: nil, milestones: [], ladders: ladders)

        let plan = Policy.plan(eventID: 15320337, phase: .after, cards: deck, now: now)
        XCTAssertEqual(plan.orderedIDs, deck.map(\.id), "nothing ranks: the delivered order stands")
        XCTAssertFalse(plan.orderedIDs.contains("finish"), "no projection, no finish card manufactured")
        XCTAssertTrue(plan.reasons.isEmpty, "no pin, no sentence")
    }

    func testBeforeTipOffKeepsTheDeliveredOrderWithNoReasons() {
        let pregameNow = date("2026-10-15T23:20:00Z")
        let total = ladder(.total, .before, [
            over(230.5, key: "o:a", pin: 0.9, now: 0.9, observedAt: "2026-10-15T23:19:00Z"),
            over(236.5, key: "o:b", pin: 0.3, now: 0.3, observedAt: "2026-10-15T23:19:00Z"),
            over(244.5, key: "o:c", pin: 0.1, now: 0.1, observedAt: "2026-10-15T23:19:00Z"),
        ])
        let margin = ladder(.margin, .before, [point("o:m", x: 1.5, label: "Knicks by 2+", side: .home, pin: 0.6)])
        let plan = Policy.plan(eventID: 1, phase: .before, cards: [finish, total, margin], now: pregameNow)
        XCTAssertEqual(plan.orderedIDs, ["margin", "total", "finish"])
        XCTAssertTrue(plan.reasons.isEmpty)
    }

    // MARK: - Strict baseline

    func testOnlyAPinStrictlyBetweenZeroAndOneRanks() {
        func ranks(_ pin: Double, _ phase: NBALadderCard9483.Phase) -> Bool {
            let points = phase == .during
                ? [over(236.5, key: "o:x", pin: pin, now: 0.5)]
                : [over(236.5, key: "o:x", pin: pin, result: true)]
            let cards = [ladder(.margin, phase, [point("o:m", x: 1.5, label: "Knicks by 2+", side: .home, pin: nil)]),
                         ladder(.total, phase, points, actual: 242)]
            let plan = Policy.plan(eventID: 7, phase: phase, cards: cards, now: phase == .during ? liveNow : finalNow)
            XCTAssertEqual(Set(plan.orderedIDs), ["margin", "total"], "both cards stay reachable either way")
            return plan.reasons["total"] != nil && plan.orderedIDs.first == "total"
        }
        for phase in [NBALadderCard9483.Phase.during, .after] {
            for refused in [0.0, 1.0, -0.1, 1.1, .nan, .infinity] {
                XCTAssertFalse(ranks(refused, phase), "pin \(refused) refused in \(phase)")
            }
            for admitted in [Double.leastNonzeroMagnitude, 0.5, 1.0.nextDown] {
                XCTAssertTrue(ranks(admitted, phase), "pin \(admitted) admitted in \(phase)")
            }
        }
    }

    func testAPinTheCardDoesNotDrawIsNoCandidate() {
        let undrawn = point("o:x", x: 236.5, label: "Over 236.5", pin: 0.3, now: 0.6, observedAt: liveAt, drawn: .some(nil))
        let undated = point("o:y", x: 240.5, label: "Over 240.5", pin: 0.3, pinAt: "yesterday", now: 0.6, observedAt: liveAt)
        let plan = Policy.plan(eventID: 7, phase: .during, cards: [ladder(.total, .during, [undrawn, undated])], now: liveNow)
        XCTAssertTrue(plan.reasons.isEmpty, "a pin the card does not draw, or cannot date, says nothing")
    }

    // MARK: - Order

    func testValuesSortByExactDoubles() {
        // Both print 25% → 50%; the total's quote is one ulp higher.
        let margin = ladder(.margin, .during, [point("o:a", x: 1.5, label: "Knicks by 2+", side: .home,
                                                     pin: 0.25, now: 0.5, observedAt: liveAt)])
        let total = ladder(.total, .during, [over(236.5, key: "o:b", pin: 0.25, now: 0.5.nextUp)])
        let plan = Policy.plan(eventID: 7, phase: .during, cards: [margin, total], now: liveNow)
        XCTAssertEqual(plan.orderedIDs, ["total", "margin"])
    }

    func testEqualValuesBreakByOptionKeyThenMarginBeforeTotal() throws {
        // Within a ladder: `String <`, so "o:10" precedes "o:2".
        let within = ladder(.total, .during, [over(230.5, key: "o:2", pin: 0.25, now: 0.5),
                                              over(236.5, key: "o:10", pin: 0.75, now: 0.5)])
        let plan = Policy.plan(eventID: 7, phase: .during, cards: [within], now: liveNow)
        XCTAssertEqual(try XCTUnwrap(plan.reasons["total"]).optionKey, "o:10")

        // Across cards: the lower selected key first, whichever family.
        let marginHigh = ladder(.margin, .during, [point("o:9", x: 1.5, label: "Knicks by 2+", side: .home,
                                                         pin: 0.25, now: 0.5, observedAt: liveAt)])
        let totalLow = ladder(.total, .during, [over(236.5, key: "o:1", pin: 0.25, now: 0.5)])
        XCTAssertEqual(Policy.plan(eventID: 7, phase: .during, cards: [marginHigh, totalLow], now: liveNow).orderedIDs,
                       ["total", "margin"])

        // Same value and key: margin before total, in either input order.
        let marginSame = ladder(.margin, .during, [point("o:1", x: 1.5, label: "Knicks by 2+", side: .home,
                                                         pin: 0.25, now: 0.5, observedAt: liveAt)])
        for cards in [[marginSame, totalLow], [totalLow, marginSame]] {
            XCTAssertEqual(Policy.plan(eventID: 7, phase: .during, cards: cards, now: liveNow).orderedIDs,
                           ["margin", "total"])
        }
    }

    func testEveryCardStaysReachableOnceInAMixedDeck() {
        // A candidate whose quote has not moved still leads the unscored ladder.
        let still = ladder(.total, .during, [over(236.5, key: "o:t", pin: 0.4, now: 0.4)])
        let unscored = ladder(.margin, .during, [point("o:m", x: 1.5, label: "Knicks by 2+", side: .home, pin: nil)])
        let input = [finish, still, unscored, still]
        let plan = Policy.plan(eventID: 7, phase: .during, cards: input, now: liveNow)
        XCTAssertEqual(plan.orderedIDs, ["total", "margin", "finish"])

        // All unscored: margin → total, finish after the ladders, whatever came in.
        let unscoredTotal = ladder(.total, .during, [over(236.5, key: "o:t", pin: nil)])
        XCTAssertEqual(Policy.plan(eventID: 7, phase: .during, cards: [finish, unscoredTotal, unscored], now: liveNow)
            .orderedIDs, ["margin", "total", "finish"])
        XCTAssertEqual(Policy.plan(eventID: 7, phase: .during, cards: [], now: liveNow).orderedIDs, [])
    }

    // MARK: - Live currentness (W2)

    func testTheLiveReasonEndsExactlyWhereTheQuoteStopsBeingCurrent() throws {
        func deck(_ clock: String) -> [NFLEventCard9483] {
            [ladder(.total, .during, [over(236.5, key: "o:t", pin: 0.3, now: 0.45, observedAt: clock)])]
        }
        func currentNow(_ cards: [NFLEventCard9483], at now: Date) -> Double? {
            guard case .ladder(let card) = cards[0].current(at: now) else { return nil }
            return card.points[0].now
        }
        let t0 = date(liveAt)
        let boundary = t0.addingTimeInterval(1800)
        let atT0 = Policy.plan(eventID: 7, phase: .during, cards: deck(liveAt), now: t0)
        XCTAssertEqual(try XCTUnwrap(atT0.reasons["total"]).expiry, boundary)
        XCTAssertEqual(atT0.nearestExpiry, boundary)

        let atBoundary = Policy.plan(eventID: 7, phase: .during, cards: deck(liveAt), now: boundary)
        XCTAssertNotNil(atBoundary.reasons["total"], "present at t0 + 1800 s")
        XCTAssertEqual(currentNow(deck(liveAt), at: boundary), 0.45, "and the card still reads its quote")
        let past = boundary.addingTimeInterval(0.001)
        XCTAssertNil(Policy.plan(eventID: 7, phase: .during, cards: deck(liveAt), now: past).reasons["total"],
                     "absent at t0 + 1800 s + ε")
        XCTAssertNil(currentNow(deck(liveAt), at: past), "exactly when the card drops its quote")
        XCTAssertEqual(Policy.plan(eventID: 7, phase: .during, cards: deck(liveAt), now: past).orderedIDs, ["total"],
                       "the card stays; only its reason left")

        // A fractional clock: whatever the floating boundary does, the reason
        // and the card agree at the deadline and just past it.
        let fractional = "2026-10-16T01:10:00.654504Z"
        let expiry = try XCTUnwrap(Policy.plan(eventID: 7, phase: .during, cards: deck(fractional), now: t0)
            .reasons["total"]?.expiry)
        for instant in [expiry, expiry.addingTimeInterval(0.001)] {
            XCTAssertEqual(Policy.plan(eventID: 7, phase: .during, cards: deck(fractional), now: instant)
                .reasons["total"] != nil, currentNow(deck(fractional), at: instant) != nil)
        }
    }

    func testAWithdrawnOrUndatableQuoteGivesNoLiveReason() {
        for clock in [nil, "", "soon"] as [String?] {
            let quote = point("o:t", x: 236.5, label: "Over 236.5", pin: 0.3, now: 0.45, observedAt: clock)
            let plan = Policy.plan(eventID: 7, phase: .during, cards: [ladder(.total, .during, [quote])], now: liveNow)
            XCTAssertTrue(plan.reasons.isEmpty, "clock \(String(describing: clock))")
            XCTAssertNil(plan.nearestExpiry)
        }
        // Withdrawn or suspended: the builder serves no `now` beside the pin.
        let withdrawn = ladder(.total, .during, [over(236.5, key: "o:t", pin: 0.3, now: nil)])
        XCTAssertTrue(Policy.plan(eventID: 7, phase: .during, cards: [withdrawn], now: liveNow).reasons.isEmpty)
    }

    // MARK: - Final

    func testAFinalSentenceNeedsTheOwnResultAndAMatchingActual() throws {
        func reason(_ points: [NBALadderCard9483.Point], actual: Double?,
                    family: NBALadderCard9483.Family = .total) -> Policy.Reason? {
            Policy.plan(eventID: 7, phase: .after, cards: [ladder(family, .after, points, actual: actual)], now: finalNow)
                .reasons[family.rawValue]
        }
        XCTAssertNil(reason([over(236.5, key: "o:t", pin: 0.3, result: nil)], actual: 242), "no verdict")
        XCTAssertNil(reason([over(236.5, key: "o:t", pin: 0.3, result: true)], actual: nil), "no actual")
        XCTAssertNil(reason([over(236.5, key: "o:t", pin: 0.3, result: false)], actual: 242), "a verdict the actual contradicts")
        XCTAssertNil(reason([over(236.5, key: "o:t", pin: 0.3, result: true)], actual: 230), "a verdict the actual contradicts")

        // Margins: own signed team words, matching units, both sides.
        let away = point("o:a", x: -3.5, label: "Raptors by 4+", side: .away, pin: 0.2, result: true)
        let awayWon = try XCTUnwrap(reason([away], actual: -5, family: .margin))
        XCTAssertEqual(awayWon.text, "Raptors by 4+ points: 20% before tip-off; final margin Raptors by 5.")
        let home = point("o:h", x: 3.5, label: "Knicks by 4+", side: .home, pin: 0.6, result: false)
        XCTAssertEqual(try XCTUnwrap(reason([home], actual: 2, family: .margin)).text,
                       "Knicks by 4+ points: 60% before tip-off; final margin Knicks by 2.")
        XCTAssertEqual(try XCTUnwrap(reason([home], actual: 0, family: .margin)).text,
                       "Knicks by 4+ points: 60% before tip-off; final margin Tie.")

        // A loss at a 70% pin outranks a win at a 60% pin (0.7 against 0.4).
        let lost = over(230.5, key: "o:z", pin: 0.7, result: false)
        let won = over(236.5, key: "o:a", pin: 0.6, result: true)
        XCTAssertEqual(reason([won, lost], actual: 225)?.optionKey, "o:z",
                       "Over 236.5 'won' at 225 is a contradiction and says nothing; the consistent loss speaks")
        let consistentWon = over(220.5, key: "o:a", pin: 0.6, result: true)
        XCTAssertEqual(reason([consistentWon, lost], actual: 225)?.optionKey, "o:z")
    }

    // MARK: - No heuristic in the sentences

    func testTheSentencesNameOnlyTheirFacts() throws {
        let live = Policy.plan(eventID: 7, phase: .during,
                               cards: [ladder(.total, .during, [over(236.5, key: "o:t", pin: 0.3, now: 0.45)])],
                               now: liveNow)
        let reason = try XCTUnwrap(live.reasons["total"])
        XCTAssertEqual(reason.text, "Over 236.5 points: 30% before tip-off · 45% now.")
        let pinStamp = try XCTUnwrap(SourceAge.preciseStamp(pinAt))
        let nowStamp = try XCTUnwrap(SourceAge.preciseStamp(liveAt))
        XCTAssertEqual(reason.accessibilityText,
                       "Over 236.5 points. 30% before tip-off, quoted \(pinStamp). 45% now, quoted \(nowStamp).")

        let final = try XCTUnwrap(Policy.plan(eventID: 15327183, phase: .after, cards: positiveDeck(), now: finalNow)
            .reasons["total"])
        let cases: [(Policy.Reason, Set<String>)] = [(reason, ["236.5", "30", "45"]), (final, ["236.5", "30", "242"])]
        for (reason, facts) in cases {
            let spoken = reason.accessibilityText
                .replacingOccurrences(of: pinStamp, with: "").replacingOccurrences(of: nowStamp, with: "")
            for sentence in [reason.text, spoken] {
                let numbers = sentence.split(whereSeparator: { !$0.isNumber && $0 != "." })
                    .map { String($0).trimmingCharacters(in: CharacterSet(charactersIn: ".")) }.filter { !$0.isEmpty }
                XCTAssertEqual(Set(numbers), facts, "only the named facts are numbers: \(sentence)")
                for word in ["15", "40", "70", "difference", "swing", "moved", "surprise", "biggest", "jump",
                             "upset", "score", "question", "price", "odds", "+", "−"] {
                    XCTAssertFalse(sentence.localizedCaseInsensitiveContains(word), "\(word) in \(sentence)")
                }
            }
        }
    }

    /// R1 (Lane1b): the sentence sits under the card, so it prints the card's
    /// own `formatProbability` — never a second rounding of the same number.
    /// Kalshi half-cents are where the two arithmetics disagree, and a strict
    /// pin near 0 or 1 must not read as a settled 0% / 100%.
    func testTheSentencePrintsTheCardsOwnPercent() throws {
        func live(pin: Double, now: Double = 0.45) throws -> Policy.Reason {
            let cards = [ladder(.total, .during, [over(236.5, key: "o:t", pin: pin, now: now)])]
            return try XCTUnwrap(Policy.plan(eventID: 7, phase: .during, cards: cards, now: liveNow).reasons["total"],
                                 "pin \(pin) / now \(now) ranks")
        }
        let pinStamp = try XCTUnwrap(SourceAge.preciseStamp(pinAt))
        let nowStamp = try XCTUnwrap(SourceAge.preciseStamp(liveAt))
        for (pin, printed) in [(0.565, "56%"), (0.004, "<1%"), (0.996, ">99%")] {
            let reason = try live(pin: pin)
            XCTAssertEqual(reason.text, "Over 236.5 points: \(printed) before tip-off · 45% now.")
            XCTAssertEqual(reason.accessibilityText,
                           "Over 236.5 points. \(printed) before tip-off, quoted \(pinStamp). 45% now, quoted \(nowStamp).")
        }
        XCTAssertEqual(try live(pin: 0.3, now: 0.565).text, "Over 236.5 points: 30% before tip-off · 56% now.")
        XCTAssertTrue(try live(pin: 0.3, now: 0.565).accessibilityText.contains(" 56% now, quoted "))

        // The card's own formatter for every value the two arithmetics split on
        // (the rendered_percent half-cents and the clamps), and the strict pin's
        // admitted extremes, which the ranking test admits but never reads.
        for value in [0.145, 0.285, 0.565, 0.575, 0.004, 0.007, 0.993, 0.996,
                      Double.leastNonzeroMagnitude, 1.0.nextDown] {
            XCTAssertTrue(try live(pin: value).text.hasPrefix("Over 236.5 points: \(formatProbability(value)) before tip-off"),
                          "pin \(value)")
            XCTAssertTrue(try live(pin: 0.3, now: value).text.hasSuffix(" · \(formatProbability(value)) now."),
                          "quote \(value)")
        }
        XCTAssertEqual(try live(pin: .leastNonzeroMagnitude).text, "Over 236.5 points: <1% before tip-off · 45% now.")
        XCTAssertEqual(try live(pin: 1.0.nextDown).text, "Over 236.5 points: >99% before tip-off · 45% now.")

        let final = Policy.plan(eventID: 7, phase: .after,
                                cards: [ladder(.total, .after, [over(236.5, key: "o:t", pin: 0.004, result: true)], actual: 242)],
                                now: finalNow)
        XCTAssertEqual(try XCTUnwrap(final.reasons["total"]).text, "Over 236.5 points: <1% before tip-off; final total 242.")
    }

    /// N1: a ladder speaks only in the stream's own phase. A `.during` ladder
    /// with a moved, current quote handed to an `.after` plan says nothing.
    func testALadderInAnotherPhaseGivesNoReason() {
        let cards = [ladder(.total, .during, [over(236.5, key: "o:t", pin: 0.3, now: 0.45)])]
        XCTAssertNotNil(Policy.plan(eventID: 7, phase: .during, cards: cards, now: liveNow).reasons["total"],
                        "control: the same ladder speaks in its own phase")
        let mismatched = Policy.plan(eventID: 7, phase: .after, cards: cards, now: liveNow)
        XCTAssertTrue(mismatched.reasons.isEmpty)
        XCTAssertEqual(mismatched.orderedIDs, ["total"], "the card stays; it only has no reason")
    }

    // MARK: - State

    private func plan(_ ids: [String], event: Int = 1) -> Policy.Plan {
        Policy.Plan(eventID: event, orderedIDs: ids, reasons: [:])
    }

    func testReceiveReplacesPendingAndOnlyApplyMovesTheOrder() {
        var state = Policy.State(plan: plan(["margin", "total", "finish"]))
        XCTAssertEqual(state.appliedIDs, ["margin", "total", "finish"])
        XCTAssertEqual(state.activeID, "margin")
        XCTAssertFalse(state.held)

        XCTAssertTrue(state.receive(plan(["total", "margin", "finish"])))
        XCTAssertEqual(state.pendingIDs, ["total", "margin", "finish"])
        XCTAssertEqual(state.appliedIDs, ["margin", "total", "finish"], "pending is withheld")
        XCTAssertEqual(state.activeID, "margin", "a surviving active card stays")

        state.applyPending()
        XCTAssertEqual(state.appliedIDs, ["total", "margin", "finish"])
        XCTAssertEqual(state.activeID, "margin", "applying keeps the surviving active identity")

        // Held: receive only replaces pending; Resume applies, then releases.
        state.hold()
        XCTAssertTrue(state.receive(plan(["finish", "total", "margin"])))
        XCTAssertEqual(state.appliedIDs, ["total", "margin", "finish"])
        XCTAssertTrue(state.held)
        state.resume()
        XCTAssertEqual(state.appliedIDs, ["finish", "total", "margin"])
        XCTAssertEqual(state.activeID, "margin")
        XCTAssertFalse(state.held)
    }

    func testAnotherEventsPlanIsRefusedAndANewEventStartsClean() {
        var a = Policy.State(plan: plan(["margin", "total", "finish"], event: 1))
        a.focus("total", present: ["margin", "total", "finish"])
        a.receive(plan(["total", "margin", "finish"], event: 1))
        let before = a
        XCTAssertFalse(a.receive(plan(["finish"], event: 2)), "an old/other event's callback")
        XCTAssertEqual(a, before, "writes nothing")

        let b = Policy.State(plan: plan(["margin", "total", "finish"], event: 2))
        XCTAssertEqual(b.eventID, 2)
        XCTAssertEqual(b.appliedIDs, ["margin", "total", "finish"])
        XCTAssertEqual(b.pendingIDs, b.appliedIDs, "no A pending order")
        XCTAssertEqual(b.activeID, "margin", "no A active card")
        XCTAssertFalse(b.held, "no A hold")
    }

    func testAHeldActiveCardThatLeavesKeepsItsUnavailableSlot() {
        var state = Policy.State(plan: plan(["margin", "total", "finish"]))
        state.focus("total", present: ["margin", "total", "finish"])
        XCTAssertTrue(state.held)

        // Total leaves while held: order and active identity are untouched.
        let present: Set<String> = ["margin", "finish"]
        state.receive(plan(["finish", "margin"]))
        XCTAssertEqual(state.appliedIDs, ["margin", "total", "finish"])
        XCTAssertEqual(state.activeID, "total")
        XCTAssertEqual(state.shelf(present: present), [.card("margin"), .unavailable("total"), .card("finish")])
        XCTAssertEqual(state.shelf(present: present).filter { if case .card = $0 { return true } else { return false } }
            .map(\.id), state.appliedIDs.filter(present.contains), "the shelf's cards are exactly applied ∩ present")

        // Manual next leaves the slot for its present neighbour; the slot goes.
        var stepped = state
        stepped.next(present: present, wrap: false)
        XCTAssertEqual(stepped.activeID, "finish")
        XCTAssertEqual(stepped.shelf(present: present), [.card("margin"), .card("finish")],
                       "a non-active absent id is skipped, never a slot")
        var back = state
        back.previous(present: present)
        XCTAssertEqual(back.activeID, "margin")

        // Its explicit Refresh reconciles the slot exactly as the reader does.
        var refreshed = state
        refreshed.applyPending()
        XCTAssertEqual(refreshed.activeID, NFLCardReaderHold9483.reconciled(
            visible: "total", old: ["margin", "total", "finish"], new: ["finish", "margin"]))
        XCTAssertEqual(refreshed.activeID, "finish")
        XCTAssertEqual(refreshed.shelf(present: present), [.card("finish"), .card("margin")])
        XCTAssertTrue(refreshed.held, "Refresh cards applies order; it is not Resume")
    }

    func testUnheldRemovalPicksTheReadersNeighbour() {
        let old = ["margin", "total", "finish"]
        for (active, survivors) in [("total", ["margin", "finish"]), ("finish", ["total", "margin"]),
                                    ("margin", ["finish"]), ("total", [])] {
            var state = Policy.State(plan: plan(old))
            for _ in 0..<old.firstIndex(of: active)! { state.next(present: Set(old), wrap: false) }
            XCTAssertEqual(state.activeID, active)
            state.receive(plan(survivors))
            XCTAssertEqual(state.activeID, NFLCardReaderHold9483.reconciled(visible: active, old: old, new: survivors),
                           "\(active) removed → the reader's neighbour")
            XCTAssertEqual(state.appliedIDs, old, "receive never applies")
        }
    }

    func testAutomaticNextWrapsAndSmallCountsStayPut() {
        let ids = ["total", "margin", "finish"]
        var state = Policy.State(plan: plan(ids))
        state.next(present: Set(ids), wrap: true)
        state.next(present: Set(ids), wrap: true)
        XCTAssertEqual(state.activeID, "finish")
        var manual = state
        manual.next(present: Set(ids), wrap: false)
        XCTAssertEqual(manual.activeID, "finish", "manual next stops at the end")
        state.next(present: Set(ids), wrap: true)
        XCTAssertEqual(state.activeID, "total", "automatic last → first wraps")
        var first = state
        first.previous(present: Set(ids))
        XCTAssertEqual(first.activeID, "total", "previous never wraps")

        var one = Policy.State(plan: plan(["total"]))
        one.next(present: ["total"], wrap: true)
        XCTAssertEqual(one.activeID, "total")
        XCTAssertEqual(one.shelf(present: ["total"]), [.card("total")])

        var zero = Policy.State(plan: plan([]))
        XCTAssertNil(zero.activeID)
        zero.next(present: [], wrap: true)
        XCTAssertNil(zero.activeID)
        XCTAssertEqual(zero.shelf(present: []), [], "never 1 of 0")
    }

    func testFocusHoldsOnlyOnAShelfCard() {
        var state = Policy.State(plan: plan(["margin", "total"]))
        state.receive(plan(["margin", "total", "finish"]))
        let present: Set<String> = ["margin", "total", "finish"]
        let before = state
        state.focus("finish", present: present)
        XCTAssertEqual(state, before, "a pending card is not on the shelf")
        state.focus("ghost", present: present)
        XCTAssertEqual(state, before)
        state.focus("total", present: present)
        XCTAssertEqual(state.activeID, "total")
        XCTAssertTrue(state.held)
    }

    // MARK: - Receiver integration (file 3)

    private func liveLadders() -> (margin: NBALadderCard9483, total: NBALadderCard9483) {
        let margin = NBALadderCard9483(family: .margin, phase: .during, points: [
            point("o:m1", x: 1.5, label: "Knicks by 2+", side: .home, pin: 0.5),
            point("o:m3", x: 3.5, label: "Knicks by 4+", side: .home, pin: 0.3),
        ], actual: 2, forecast: nil, awayShort: "Raptors", homeShort: "Knicks")
        let total = NBALadderCard9483(family: .total, phase: .during, points: [
            over(230.5, key: "o:t230", pin: 0.5, now: 0.55),
            over(236.5, key: "o:t236", pin: 0.3, now: 0.6),
        ], actual: 200, forecast: nil, awayShort: "Raptors", homeShort: "Knicks")
        return (margin, total)
    }

    func testSeeThisLineSelectsOnlyTheExactAppliedOption() throws {
        let (margin, total) = liveLadders()
        let state = NFLCardDeckState9483()
        let plan = Policy.plan(eventID: 7, phase: .during, cards: [.ladder(margin), .ladder(total)], now: liveNow)
        state.beginNBAStream(plan)
        let reason = try XCTUnwrap(plan.reasons["total"])
        XCTAssertEqual(reason.optionKey, "o:t236")
        XCTAssertEqual(total.defaultIndex, 0, "the default is another line, so a refusal is visible")

        XCTAssertFalse(state.select(optionKey: reason.optionKey, in: total, eventID: 8), "another event")
        XCTAssertFalse(state.select(optionKey: "o:gone", in: total, eventID: 7), "an absent option")
        XCTAssertEqual(state.selectedIndex(in: total), 0, "refusals write nothing, never a neighbour")
        XCTAssertTrue(state.select(optionKey: reason.optionKey, in: total, eventID: 7))
        XCTAssertEqual(state.selectedIndex(in: total), 1)

        // A card that is only pending is not applied: nothing selects on it.
        let fresh = NFLCardDeckState9483()
        fresh.beginNBAStream(Policy.Plan(eventID: 7, orderedIDs: ["margin"], reasons: [:]))
        fresh.receiveNBAPlan(plan)
        XCTAssertFalse(fresh.select(optionKey: reason.optionKey, in: total, eventID: 7))
        XCTAssertEqual(fresh.selectedIndex(in: total), 0)
    }

    func testANewEventDiscardsTheOldStreamAndItsLadderSelection() throws {
        let (margin, total) = liveLadders()
        let state = NFLCardDeckState9483()
        let a = Policy.plan(eventID: 7, phase: .during, cards: [.ladder(margin), .ladder(total)], now: liveNow)
        state.beginNBAStream(a)
        XCTAssertTrue(state.select(optionKey: "o:t236", in: total, eventID: 7))
        state.holdNBAStream(eventID: 7)

        let b = Policy.Plan(eventID: 8, orderedIDs: ["margin", "total"], reasons: [:])
        state.beginNBAStream(b)
        let stream = try XCTUnwrap(state.nbaStreamState)
        XCTAssertEqual(stream, Policy.State(plan: b), "B starts unheld with B's order and nothing of A")
        XCTAssertEqual(state.selectedIndex(in: total), total.defaultIndex, "A's ladder selection is cleared")

        state.receiveNBAPlan(a)
        state.advanceNBAStream(a, present: ["margin", "total"])
        state.holdNBAStream(eventID: 7)
        XCTAssertEqual(state.nbaStreamState, Policy.State(plan: b), "A's late callbacks write nothing to B")
        XCTAssertFalse(state.select(optionKey: "o:t236", in: total, eventID: 7))
    }

    func testTheReaderGetsTheAppliedOrderAndAHeldStreamDoesNotAdvance() {
        let (margin, total) = liveLadders()
        let cards: [NFLEventCard9483] = [.ladder(margin), .ladder(total), finish]
        let state = NFLCardDeckState9483()
        XCTAssertEqual(state.appliedNBAOrder(eventID: 7, fallback: cards).map(\.id), ["margin", "total", "finish"],
                       "no stream yet: this event's own fallback")
        state.beginNBAStream(Policy.Plan(eventID: 7, orderedIDs: ["finish", "margin"], reasons: [:]))
        XCTAssertEqual(state.appliedNBAOrder(eventID: 7, fallback: cards).map(\.id), ["finish", "margin"],
                       "a present card not yet applied is withheld")
        XCTAssertEqual(state.appliedNBAOrder(eventID: 8, fallback: cards).map(\.id), ["margin", "total", "finish"],
                       "another event never reads this stream")

        state.holdNBAStream(eventID: 7)
        let held = state.nbaStreamState
        state.advanceNBAStream(Policy.Plan(eventID: 7, orderedIDs: ["total", "margin", "finish"], reasons: [:]),
                               present: ["margin", "total", "finish"])
        XCTAssertEqual(state.nbaStreamState, held, "a held stream neither applies nor advances")
        state.resumeNBAStream(eventID: 7)
        state.advanceNBAStream(Policy.Plan(eventID: 7, orderedIDs: ["total", "margin", "finish"], reasons: [:]),
                               present: ["margin", "total", "finish"])
        XCTAssertEqual(state.nbaStreamState?.appliedIDs, ["total", "margin", "finish"], "receive → apply")
        XCTAssertEqual(state.nbaStreamState?.activeID, "total", "→ next, from finish wrapping to the first")
    }

    // MARK: - Admission (native)

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func history(event: Int) throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: [
            "event_id": event, "home_team": "New York Knicks", "away_team": "Toronto Raptors", "history": [],
        ] as [String: Any]))
    }

    private func markets(event: Int) throws -> GameMarketsResponse {
        try decoder().decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: [
            "event_id": event, "home_team": "New York Knicks", "away_team": "Toronto Raptors", "status": "completed",
        ] as [String: Any]))
    }

    private let pageEvent = 15327183

    /// One input change on 15327183's page, as the view runs it: the plan
    /// `onChange` (`receiveNBAPlan`) and the inputs `onChange` (`admit`, with
    /// the page's own `deckReady`), in the order given — the guards run both,
    /// so neither leans on which of the two SwiftUI calls first.
    private func deliver(_ cards: [NFLEventCard9483], history: EventHistoryResponse?, markets: GameMarketsResponse?,
                         to state: NFLCardDeckState9483, receiveFirst: Bool) {
        let ready = NBAStoryStreamView9483.Page.deckReady(history: history, gameMarkets: markets, eventID: pageEvent)
        let key = NBAStoryStreamView9483.InputsKey(eventID: pageEvent, phase: .after, cards: cards, ready: ready)
        let plan = Policy.plan(eventID: pageEvent, phase: .after, cards: cards.map { $0.current(at: finalNow) },
                               now: finalNow)
        if receiveFirst { state.receiveNBAPlan(plan) }
        NBAStoryStreamView9483.admit(key, into: state, now: finalNow)
        if !receiveFirst { state.receiveNBAPlan(plan) }
    }

    /// 15327183's page as it loads: the history (finish card) arrives before
    /// the game markets (the ladders).
    func testTheStreamBeginsOnlyOnceThisEventsHistoryAndMarketsHaveArrived() throws {
        let full = positiveDeck()
        let history = try history(event: pageEvent)
        let ours = try markets(event: pageEvent)
        let another = try markets(event: 15320337)

        for receiveFirst in [true, false] {
            let state = NFLCardDeckState9483()
            let order = receiveFirst ? "receive first" : "admit first"
            deliver([finish], history: history, markets: nil, to: state, receiveFirst: receiveFirst)
            XCTAssertNil(state.nbaStreamState, "\(order): the finish card alone begins no stream")
            deliver(full, history: history, markets: another, to: state, receiveFirst: receiveFirst)
            XCTAssertNil(state.nbaStreamState, "\(order): another event's markets begin no stream")
            deliver(full, history: nil, markets: ours, to: state, receiveFirst: receiveFirst)
            XCTAssertNil(state.nbaStreamState, "\(order): this event's markets without the history begin none")

            deliver(full, history: history, markets: ours, to: state, receiveFirst: receiveFirst)
            let stream = try XCTUnwrap(state.nbaStreamState, "\(order): both reads in: the stream begins")
            XCTAssertEqual(stream.appliedIDs, ["total", "margin", "finish"],
                           "\(order): the whole ranked deck is applied, no Refresh")
            XCTAssertEqual(stream.pendingIDs, stream.appliedIDs, "\(order): nothing waits as pending")
            XCTAssertEqual(stream.activeID, "total", "\(order): the scoring card leads")
            XCTAssertFalse(stream.held, "\(order): nobody touched the shelf, so it is free to advance")
            XCTAssertEqual(stream.shelf(present: ["margin", "total", "finish"]),
                           [.card("total"), .card("margin"), .card("finish")], "\(order): the shelf shows all three")
            XCTAssertEqual(state.appliedNBAOrder(eventID: pageEvent, fallback: full).map(\.id),
                           ["total", "margin", "finish"], "\(order): and so does the reader")
            XCTAssertNil(state.nbaBeforeBegin, "\(order): the loading record goes at the begin")
        }
    }

    /// N4 — the markets arrive first (the ladders, in the builder's order
    /// margin → total) and the history keeps the stream from beginning. Every
    /// action the shelf offers there works, the shelf and the reader show one
    /// order, and what the reader chose survives the begin.
    func testBeforeTheStreamBeginsTheShelfsActionsWorkAndTheReadersChoiceSurvivesTheBegin() throws {
        let full = positiveDeck()
        let ladders = Array(full.prefix(2))
        XCTAssertEqual(ladders.map(\.id), ["margin", "total"], "the builder's order, not the ranked one")
        guard case .ladder(let total) = full[1] else { return XCTFail("total ladder") }
        let history = try history(event: pageEvent)
        let ours = try markets(event: pageEvent)
        let shelf = Policy.plan(eventID: pageEvent, phase: .after, cards: ladders.map { $0.current(at: finalNow) },
                                now: finalNow)
        let line = try XCTUnwrap(shelf.reasons["total"]?.optionKey)
        let lineIndex = try XCTUnwrap(total.points.firstIndex { $0.optionKey == line })
        XCTAssertEqual(lineIndex, total.defaultIndex, "15327183's packet: the card opens on the explained line")

        enum Choice: CaseIterable { case none, held, stepped, browsed, opened, sawLine }
        for receiveFirst in [true, false] {
            for choice in Choice.allCases {
                let state = NFLCardDeckState9483()
                let label = "\(receiveFirst ? "receive first" : "admit first"), \(choice)"
                deliver(ladders, history: nil, markets: ours, to: state, receiveFirst: receiveFirst)
                XCTAssertNil(state.nbaStreamState, "\(label): no history, no stream")
                XCTAssertEqual(shelf.orderedIDs, ["total", "margin"], "\(label): the shelf ranks the scoring card first")
                XCTAssertEqual(state.appliedNBAOrder(eventID: pageEvent, fallback: ladders).map(\.id), shelf.orderedIDs,
                               "\(label): the reader shows the shelf's order")

                switch choice {
                case .none: break
                case .held: state.holdNBAStream(eventID: pageEvent)
                case .stepped: state.move(in: total, by: -1)
                case .browsed: state.focusNBAStream(eventID: pageEvent, cardID: "margin", present: ["margin", "total"])
                case .opened:
                    state.openNBACard(eventID: pageEvent, cardID: "margin", present: ["margin", "total"])
                    XCTAssertEqual(state.openCardID, "margin", "\(label): Open works")
                    state.close()
                case .sawLine:
                    // The reader first stepped the card to the line below, so
                    // See this line has somewhere visible to go back to.
                    state.move(in: total, by: -1)
                    XCTAssertEqual(state.selectedIndex(in: total), lineIndex - 1, "\(label): the card's own step")
                    XCTAssertFalse(state.select(optionKey: line, in: total, eventID: 15320337), "\(label): another event")
                    XCTAssertFalse(state.select(optionKey: "o:gone", in: total, eventID: pageEvent), "\(label): no option")
                    XCTAssertEqual(state.selectedIndex(in: total), lineIndex - 1, "\(label): refusals write nothing")
                    XCTAssertTrue(state.select(optionKey: line, in: total, eventID: pageEvent),
                                  "\(label): See this line selects its line")
                    state.openNBACard(eventID: pageEvent, cardID: "total", present: ["margin", "total"])
                    XCTAssertEqual(state.openCardID, "total", "\(label): and opens its card")
                    state.close()
                }

                deliver(full, history: history, markets: ours, to: state, receiveFirst: receiveFirst)
                let stream = try XCTUnwrap(state.nbaStreamState, "\(label): both reads in: the stream begins")
                XCTAssertEqual(stream.appliedIDs, ["total", "margin", "finish"], "\(label): the whole ranked deck")
                XCTAssertEqual(stream.pendingIDs, stream.appliedIDs, "\(label): nothing pending")
                let expected: (active: String, held: Bool) = switch choice {
                case .none, .stepped: ("total", false)
                case .held: ("total", true)
                case .browsed, .opened: ("margin", true)
                case .sawLine: ("total", true)
                }
                XCTAssertEqual(stream.activeID, expected.active, "\(label): the card the reader chose stays active")
                XCTAssertEqual(stream.held, expected.held, "\(label): and the shelf stays held for them")
                XCTAssertEqual(state.selectedIndex(in: total), choice == .stepped ? lineIndex - 1 : lineIndex,
                               "\(label): the line the reader left the card on survives the begin")
                XCTAssertNil(state.nbaBeforeBegin, "\(label): the loading record goes at the begin")
            }
        }

        // A late plan from another event writes nothing once a stream runs,
        // and a new event discards the loading record.
        let running = NFLCardDeckState9483()
        deliver(full, history: history, markets: ours, to: running, receiveFirst: true)
        running.receiveNBAPlan(Policy.Plan(eventID: 15320337, orderedIDs: ["finish"], reasons: [:]))
        running.holdNBAStream(eventID: 15320337)
        running.focusNBAStream(eventID: 15320337, cardID: "finish", present: ["finish"])
        XCTAssertNil(running.nbaBeforeBegin, "another event's late callbacks write no loading record")
        XCTAssertEqual(running.nbaStreamState?.held, false, "nor touch this event's stream")
        let loading = NFLCardDeckState9483()
        deliver(ladders, history: nil, markets: ours, to: loading, receiveFirst: true)
        loading.holdNBAStream(eventID: pageEvent)
        XCTAssertNotNil(loading.nbaBeforeBegin)
        loading.resetNBAStream()
        XCTAssertNil(loading.nbaBeforeBegin, "the page's event changed: nothing of the loading record survives")
    }

    /// The page's usable viewport (file 4) is the scroll view's own frame in
    /// `scrollSpace`, from its top-left. Measured on 15327183 at 402 pt
    /// (fx402b): the reader is 402×675, and scrollSpace y 0 is screen y 116,
    /// the bar's bottom, so the viewport is screen 116…791 (the tab bar's top).
    func testTheUsableViewportIsTheScrollViewsOwnFrame() throws {
        let viewport = try XCTUnwrap(EventDetailView.usableViewport(size: CGSize(width: 402, height: 675)))
        XCTAssertEqual(viewport, CGRect(x: 0, y: 0, width: 402, height: 675))
        XCTAssertNil(EventDetailView.usableViewport(size: CGSize(width: 402, height: 0)))
        // F2 as returned (fx402b): stage −174…319. Its lower 319 of 493 (65%)
        // are on screen between the bar and the tab bar: visible.
        XCTAssertEqual(NBAStoryStreamView9483.unobscured(stage: CGRect(x: 16, y: -174, width: 346, height: 493),
                                                         viewport: viewport), true)
        // A stage at 420…913: only 255 of 493 (52%) are above the tab bar; the
        // rest is behind it or off the screen: not visible.
        XCTAssertEqual(NBAStoryStreamView9483.unobscured(stage: CGRect(x: 16, y: 420, width: 346, height: 493),
                                                         viewport: viewport), false)
    }

    /// The unavailable slot's message and Refresh (W1) sit in the part of the
    /// slot on screen. Specimens from fx402c at 402 pt (scrollSpace, viewport
    /// 0…675). The arithmetic holds for any content height; 192 here is the
    /// slot's minimum, not the measured content (106 at default text).
    func testTheUnavailableSlotsContentSitsInThePartOfTheSlotOnScreen() {
        let viewport = CGRect(x: 0, y: 0, width: 402, height: 675)
        let place = { (slot: CGRect) in
            NBAStoryStreamView9483.unavailableContentTop(slot: slot, viewport: viewport, content: 192)
        }
        // F7 as returned: Open tapped high, the stream began under the reader,
        // Back removed the card and the row shrank to 370 (−199…171). Centred
        // in the whole slot the message sat at screen 65, under the bar.
        // Centred in the visible 0…171 it would start above the slot's end, so
        // it is kept inside: 178, the band at −21…171, its middle at 75.
        XCTAssertEqual(place(CGRect(x: 16, y: -199, width: 346, height: 370)), 178)
        // F2 as returned (−174…319): centred in the visible 0…319.
        XCTAssertEqual(place(CGRect(x: 16, y: -174, width: 346, height: 493)), 237.5)
        // A slot wholly on screen: centred in the slot, as before.
        XCTAssertEqual(place(CGRect(x: 16, y: 14, width: 346, height: 494)), 151)
        // Only 175 of it on screen at the bottom: never above the slot's top.
        XCTAssertEqual(place(CGRect(x: 16, y: 500, width: 346, height: 400)), 0)
        // Unmeasured, or no part on screen: centre in the whole slot.
        XCTAssertNil(NBAStoryStreamView9483.unavailableContentTop(
            slot: CGRect(x: 16, y: -199, width: 346, height: 370), viewport: nil, content: 192))
        XCTAssertNil(place(CGRect(x: 16, y: 700, width: 346, height: 370)))
    }

    /// At large text the slot is taller than the screen, so a place decided
    /// once can go off screen when the reader scrolls. Specimens from fx402ax3
    /// at 402 pt, AccessibilityXL (scrollSpace, viewport 0…675, bars 116 and
    /// 791 on screen); the content band is 218.67 tall.
    func testAtLargeTextASettledScrollPlacesTheSlotsContentOnScreenAgain() throws {
        let viewport = CGRect(x: 0, y: 0, width: 402, height: 675)
        let content: CGFloat = 16 + 129 + 12 + 45.67 + 16
        let place = { (slot: CGRect) in
            NBAStoryStreamView9483.unavailableContentTop(slot: slot, viewport: viewport, content: content)
        }
        // As returned (−676…381): centred in the visible 0…381, the message at
        // screen 213, readable.
        let returned = CGRect(x: 16, y: -676, width: 346, height: 1057)
        let first = try XCTUnwrap(place(returned))
        XCTAssertEqual(returned.minY + first + 16 + 116, 213.17, accuracy: 0.5)
        // The reader scrolls up to the row's top (81…1138). The first place
        // now puts the message at screen 970, below the tab bar: a blank card.
        let scrolled = CGRect(x: 16, y: 81, width: 346, height: 1057)
        XCTAssertGreaterThan(scrolled.minY + first + 116, 791, "kept, the content is off screen")
        // Placed again when the scroll settles: message and Refresh both
        // inside the bars.
        let settled = try XCTUnwrap(place(scrolled))
        let bandTop = scrolled.minY + settled + 116, bandBottom = bandTop + content
        XCTAssertGreaterThanOrEqual(bandTop + 16, 116)
        XCTAssertLessThanOrEqual(bandBottom - 16, 791)
        XCTAssertEqual(bandTop + 16, 400.67, accuracy: 0.5)
    }

    /// The slot draws its content at `unavailableContentOffset` every frame
    /// (a render-time effect, iOS 17+), so the ship case needs no settle: the
    /// fx402ax3 specimen above, read mid-scroll. Once no part of the slot is on
    /// screen, the content stays at the edge nearer the screen, where it was
    /// as the slot left (no jump to the centre under the bars); centred in the
    /// whole slot only while the viewport is unmeasured; unmeasured content
    /// draws at the slot's frame alignment (0).
    func testTheSlotsDrawnOffsetFollowsTheScrollAndLeavesWithTheSlotsNearEdge() {
        let viewport = CGRect(x: 0, y: 0, width: 402, height: 675)
        let content: CGFloat = 16 + 129 + 12 + 45.67 + 16
        let offset = { (slot: CGRect, viewport: CGRect?, content: CGFloat) in
            NBAStoryStreamView9483.unavailableContentOffset(slot: slot, viewport: viewport, content: content)
        }
        // On screen: exactly the place, with no settle (81…1138 at AX3), the
        // message at screen 400.67, inside the bars.
        let scrolled = CGRect(x: 16, y: 81, width: 346, height: 1057)
        XCTAssertEqual(offset(scrolled, viewport, content),
                       NBAStoryStreamView9483.unavailableContentTop(slot: scrolled, viewport: viewport, content: content))
        XCTAssertEqual(scrolled.minY + offset(scrolled, viewport, content) + 16 + 116, 400.67, accuracy: 0.5)
        // Off screen: below, the top edge; above, the bottom edge. The same
        // place the last visible sliver gave, so nothing jumps at the edge.
        let below = CGRect(x: 16, y: 700, width: 346, height: 370)
        XCTAssertEqual(offset(below, viewport, 192), 0)
        XCTAssertEqual(offset(CGRect(x: 16, y: 674, width: 346, height: 370), viewport, 192), 0)
        let above = CGRect(x: 16, y: -400, width: 346, height: 370)
        XCTAssertEqual(offset(above, viewport, 192), 178)
        XCTAssertEqual(offset(CGRect(x: 16, y: -369, width: 346, height: 370), viewport, 192), 178)
        // The viewport unmeasured: centred in the slot, as the old `.center` frame did.
        XCTAssertEqual(offset(CGRect(x: 16, y: -199, width: 346, height: 370), nil, 192), 89)
        // Content taller than the slot never draws above its top.
        XCTAssertEqual(offset(CGRect(x: 16, y: 700, width: 346, height: 150), viewport, 192), 0)
        XCTAssertEqual(offset(CGRect(x: 16, y: -400, width: 346, height: 150), viewport, 192), 0)
        // Content not yet measured: 0, and the frame centres it.
        XCTAssertEqual(offset(below, viewport, 0), 0)
    }

    /// ux17def default fling (402 pt, viewport 0…675, bar bottom 116): the slot
    /// at −395…97 leaves a 97 pt band, screen 116…213. The measured content is
    /// the padded message and Refresh alone (16 + 18 + 12 + 44 + 16 = 106), so
    /// both draw inside the band. With the slot's minimum inside the
    /// measurement (192) the message sat under the bar. Arithmetic only: 106 is
    /// an input here; the layout measuring it is the default fling's to show.
    func testAShortBandAtDefaultTextHoldsTheMessageAndRefresh() {
        let viewport = CGRect(x: 0, y: 0, width: 402, height: 675)
        let slot = CGRect(x: 16, y: -395, width: 346, height: 492)
        let offset = NBAStoryStreamView9483.unavailableContentOffset(slot: slot, viewport: viewport, content: 106)
        XCTAssertEqual(offset, 386)
        let textTop = slot.minY + offset + 16 + 116
        XCTAssertEqual(textTop, 123)
        XCTAssertLessThanOrEqual(textTop + 18 + 12 + 44, 213)
        // The old measurement: the 192 box clamps to 300 and the stack, centred
        // in its 160, starts above the bar's bottom.
        let old = NBAStoryStreamView9483.unavailableContentOffset(slot: slot, viewport: viewport, content: 192)
        XCTAssertEqual(old, 300)
        XCTAssertLessThan(slot.minY + old + 16 + (160 - 74) / 2 + 116, 116)
    }
}

