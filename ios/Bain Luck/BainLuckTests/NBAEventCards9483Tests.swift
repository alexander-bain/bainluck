import XCTest
@testable import Bain_Luck

/// #9483 NBA slice — the winning-margin and scoring ladders read from the
/// served question matrix (design freeze v328, NBA-MAPPING.md, ACCEPTANCE.md
/// journeys 10–12), on the same two real bodies the web twin is pinned to:
///
/// - `event-15320337-game-matrix-9483-nba-final`: Clippers 104–101 Warriors,
///   final. Every option is a settled result with comparison `not_quoted` and
///   no pin.
/// - `event-15327183-game-matrix-9483-nba-pregame`: Raptors @ Knicks before
///   tip-off, every option `quoted` at 17:0x–18:3xZ with `no_pregame_pin`.
///
/// Root's selected fallback (10/15): with no admitted settled baseline the
/// final cards keep their shape and confirmed results and say the pregame
/// chance is unavailable. Fixed clocks only (gotcha #44).
///
/// What these pin, and the mutation each kills:
/// - read the terminal 0/100 or a settled price as a chance → `testTheFinalDrawsNoChanceAndSaysTheBaselineIsUnavailable`
/// - grade from the score instead of the producer → `testTheFinalTotalCarriesTheProducersVerdicts`
/// - refuse a real admitted pin, or admit an undated/unadmitted one → `testOnlyAnAdmittedDatedPinIsDrawnAfterTipOff`
/// - drop a settled option's own qualified pin (#11125) → `testASettledOptionsOwnPregameReadingIsDrawnBesideItsResult`
/// - borrow another outcome's pin, a blend's, or a 0/1 → `testAPregameReadingForAnotherOutcomeOrASettlementValueIsRefused`
/// - lose the signed direction or a team's identity → `testTheMarginIsSignedAndEachTeamKeepsItsOwnSide`
/// - borrow an option from the other side of its question → `testAnOptionOnTheOtherSideIsRefused`
/// - let half, untyped or another contract's lines in → `testOnlyTypedFullGameLinesOfTheContractEnter`
/// - resolve two prices on one line by order → `testTwoOptionsOnOneLineRefuseTheLine`
/// - print a stale or undated pregame quote as current → `testBeforeTipOffOnlyRecentQuotesAreDots`
/// - keep a quote current because the reader was open → `testAQuoteThatStopsBeingObservedLosesItsDot`
/// - draw the live quote as the pregame chance → `testDuringPlayTheLiveQuoteIsBesideThePinNeverThePin`
/// - grade a line before the final → `testNoGradeOrFinalWordsBeforeTheFinal`
/// - show a current price on a suspended game → `testASuspendedGameShowsNoCurrentPrice`
/// - reorder the deck, or leak ladders onto an NFL deck → `testTheNBADeckIsMarginTotalThenFinish`
/// - say "kickoff" or crowd basketball scores on a zero axis → `testTheProjectedFinishSpeaksBasketball`
/// - let Details read the live matrix under a held card → `testDetailsReadTheHeldCardsOption`
/// - select a neighbour when the chosen option vanishes → `testAWithdrawnOptionSelectsNothing`
/// - print "0%" or a chance beside a settled line → `testTheReadoutNamesEachNumberForWhatItIs`
@MainActor
final class NBAEventCards9483Tests: XCTestCase {

    private struct Body: Decodable {
        let homeScore: Int?
        let awayScore: Int?
        let gameQuestionMatrix: EventQuestionMatrix?
    }

    private func body(_ name: String) throws -> Body {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/\(name)")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Body.self, from: Data(contentsOf: url))
    }

    private func finalBody() throws -> Body { try body("event-15320337-game-matrix-9483-nba-final.20261015.json") }
    private func pregameBody() throws -> Body { try body("event-15327183-game-matrix-9483-nba-pregame.20261015.json") }

    private func date(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }
    private lazy var finalNow = date("2026-10-05T04:00:00Z")
    private lazy var pregameNow = date("2026-10-15T18:40:00Z")

    private func finalInput(matrix: EventQuestionMatrix? = nil, projection: (home: Double, away: Double)? = nil)
        throws -> NBALadderCard9483.Input {
        let b = try finalBody()
        return .init(matrix: matrix ?? b.gameQuestionMatrix, status: "completed",
                     commenceTime: date("2026-10-04T23:00:00Z"), homeScore: b.homeScore, awayScore: b.awayScore,
                     pregameProjection: projection, homeShort: "Clippers", awayShort: "Warriors", now: finalNow)
    }

    private func pregameInput(status: String = "scheduled", homeScore: Int? = nil, awayScore: Int? = nil,
                              now: Date? = nil, matrix: EventQuestionMatrix? = nil,
                              commenceTime: String = "2026-10-15T23:30:00Z") throws -> NBALadderCard9483.Input {
        .init(matrix: try matrix ?? pregameBody().gameQuestionMatrix, status: status,
              commenceTime: date(commenceTime), homeScore: homeScore, awayScore: awayScore,
              pregameProjection: nil, homeShort: "Knicks", awayShort: "Raptors", now: now ?? pregameNow)
    }

    /// The matrix with every option passed through `edit`.
    private func edited(_ matrix: EventQuestionMatrix?, _ edit: (inout QuestionMatrixQuestion) -> Void) throws
        -> EventQuestionMatrix {
        var m = try XCTUnwrap(matrix)
        m.questions = m.questions.map { var q = $0; edit(&q); return q }
        return m
    }

    // MARK: - Journey 10: the exact final total (15320337)

    func testTheFinalTotalCarriesTheProducersVerdicts() throws {
        let card = try XCTUnwrap(NBALadderCard9483.total(finalInput()))
        XCTAssertEqual(card.phase, .after)
        XCTAssertEqual(card.actual, 205, "the final score's sum")
        let over2065 = try XCTUnwrap(card.points.first { $0.x == 206.5 })
        XCTAssertEqual(over2065.optionKey, "o:240505185")
        XCTAssertEqual(over2065.label, "Over 206.5")
        XCTAssertEqual(over2065.result, false, "Over 206.5 is LOST")
        XCTAssertEqual(card.points.first { $0.x == 204.5 }?.result, true)
        XCTAssertEqual(card.points.map(\.x), card.points.map(\.x).sorted(), "the axis is ordered by line")
    }

    func testTheFinalDrawsNoChanceAndSaysTheBaselineIsUnavailable() throws {
        let card = try XCTUnwrap(NBALadderCard9483.total(finalInput()))
        XCTAssertTrue(card.points.allSatisfy { $0.chance == nil && $0.now == nil })
        XCTAssertEqual(card.caption, "Pregame chance unavailable for these lines")
        XCTAssertNil(card.points.first { $0.x == 206.5 }?.detail.baseline)
        XCTAssertNil(card.points.first { $0.x == 206.5 }?.detail.quoted, "a result is not a quote")
        // With nothing drawn, the card opens on the line nearest the actual 205.
        XCTAssertEqual(card.defaultIndex.map { card.points[$0].x }, 204.5)
    }

    func testOnlyAnAdmittedDatedPinIsDrawnAfterTipOff() throws {
        func pinned(_ baseline: QuestionMatrixBaseline?, state: String = "comparable") throws -> Double? {
            let matrix = try edited(finalBody().gameQuestionMatrix) { q in
                q.options = q.options.map { o in
                    guard o.optionKey == "o:240505185" else { return o }
                    var o = o
                    o.comparison = QuestionMatrixComparison(state: state, reason: nil, baseline: baseline,
                                                            latest: nil, deltaPoints: nil)
                    return o
                }
            }
            let card = try XCTUnwrap(NBALadderCard9483.total(finalInput(matrix: matrix)))
            return card.points.first { $0.x == 206.5 }?.chance
        }
        let stamp = "2026-10-04T22:58:37.402964Z"
        // The 82.5% waits for the field, not for code.
        XCTAssertEqual(try pinned(.init(probability: 0.825, observedAt: stamp, basis: "pregame_pin")), 0.825)
        XCTAssertNil(try pinned(.init(probability: 0.825, observedAt: stamp, basis: "pregame_pin"), state: "unavailable"))
        XCTAssertNil(try pinned(.init(probability: 0.825, observedAt: stamp, basis: "opening")))
        XCTAssertNil(try pinned(.init(probability: 0.825, observedAt: nil, basis: "pregame_pin")))
        XCTAssertNil(try pinned(.init(probability: 1.2, observedAt: stamp, basis: "pregame_pin")))
        let matrix = try edited(finalBody().gameQuestionMatrix) { q in
            q.options = q.options.map { o in
                guard o.optionKey == "o:240505185" else { return o }
                var o = o
                o.comparison = QuestionMatrixComparison(
                    state: "comparable", reason: nil,
                    baseline: .init(probability: 0.825, observedAt: stamp, basis: "pregame_pin"),
                    latest: nil, deltaPoints: nil)
                return o
            }
        }
        let card = try XCTUnwrap(NBALadderCard9483.total(finalInput(matrix: matrix)))
        XCTAssertEqual(card.caption, "Chance before tip-off of finishing above each line")
        XCTAssertEqual(card.points.first { $0.x == 206.5 }?.detail.baselineObservedAt, stamp)
    }

    /// The producer's own example options for `pregame_reading` (#11125 at
    /// 87d1b2f4d8, synthetic: ids echo 15320337 Over 206.5 for shape only).
    private func producerOption(_ name: String) throws -> QuestionMatrixOption {
        struct Example: Decodable { let options: [String: QuestionMatrixOption] }
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/pregame-reading-9483-producer-87d1b2f4d8.SYNTHETIC.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try XCTUnwrap(try decoder.decode(Example.self, from: Data(contentsOf: url)).options[name])
    }

    /// The final card's Over 206.5 point with that option served in its place.
    private func over2065(with option: QuestionMatrixOption) throws -> NBALadderCard9483.Point? {
        let matrix = try edited(finalBody().gameQuestionMatrix) { q in
            q.options = q.options.map { $0.optionKey == option.optionKey ? option : $0 }
        }
        return try XCTUnwrap(NBALadderCard9483.total(finalInput(matrix: matrix))).points.first { $0.x == 206.5 }
    }

    func testASettledOptionsOwnPregameReadingIsDrawnBesideItsResult() throws {
        let qualified = try producerOption("settled_lost_qualified_pin")
        let point = try XCTUnwrap(try over2065(with: qualified))
        XCTAssertEqual(point.chance, 0.825, "82.5% pregame, from the option's own stored pin")
        XCTAssertEqual(point.result, false, "and Lost, separately")
        XCTAssertEqual(point.detail.baselineObservedAt, "2026-10-02T18:00:00+00:00")
        XCTAssertNil(point.detail.quoted, "the result is still not a quote")
        for refused in ["settled_lost_no_pin", "settled_lost_pin_after_start"] {
            XCTAssertNil(try over2065(with: producerOption(refused))?.chance, refused)
        }
    }

    func testAPregameReadingForAnotherOutcomeOrASettlementValueIsRefused() throws {
        let qualified = try producerOption("settled_lost_qualified_pin")
        func with(_ reading: QuestionMatrixPregameReading?, contributors: [Int]? = [240505185]) throws -> Double? {
            var option = qualified
            option.pregameReading = reading
            option.contributorOutcomeIds = contributors
            return try over2065(with: option)?.chance
        }
        let good = try XCTUnwrap(qualified.pregameReading)
        func reading(probability: Double? = 0.825, observedAt: String? = "2026-10-02T18:00:00+00:00",
                     basis: String? = "pregame_pin", outcome: Int? = 240505185,
                     state: String = "available") -> QuestionMatrixPregameReading {
            QuestionMatrixPregameReading(state: state, reason: nil, probability: probability,
                                         observedAt: observedAt, basis: basis, outcomeId: outcome)
        }
        XCTAssertEqual(try with(good), 0.825)
        XCTAssertNil(try with(reading(outcome: 240505186)), "another outcome's pin is never borrowed")
        XCTAssertNil(try with(good, contributors: [240505185, 240505186]), "no single venue's pin for a blend")
        XCTAssertNil(try with(good, contributors: nil))
        XCTAssertNil(try with(reading(probability: 1)), "an exact 1 is a settlement value")
        XCTAssertNil(try with(reading(probability: 0)), "an exact 0 is a settlement value")
        XCTAssertNil(try with(reading(observedAt: nil)), "an undated pin")
        XCTAssertNil(try with(reading(basis: "opening")))
        XCTAssertNil(try with(reading(state: "unavailable")))
        XCTAssertNil(try with(nil), "an older server")
    }

    // MARK: - Journey 11: the signed margin

    func testTheMarginIsSignedAndEachTeamKeepsItsOwnSide() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: (home: 109.8, away: 112.5))))
        XCTAssertEqual(card.actual, 3)
        XCTAssertEqual(card.words(3), "Clippers by 3")
        XCTAssertEqual(card.forecast, -2.7)
        XCTAssertEqual(card.words(-2.7), "Warriors by 2.7")
        XCTAssertEqual(card.words(0), "Tie")
        let home = card.points.filter { $0.side == .home }
        let away = card.points.filter { $0.side == .away }
        XCTAssertFalse(home.isEmpty)
        XCTAssertFalse(away.isEmpty)
        XCTAssertTrue(home.allSatisfy { $0.x > 0 })
        XCTAssertTrue(away.allSatisfy { $0.x < 0 })
        // "Golden State wins by over 1.5 points" is Warriors by 2+, at −1.5.
        let gsw = try XCTUnwrap(card.points.first { $0.optionKey == "o:240505114" })
        XCTAssertEqual(gsw.x, -1.5)
        XCTAssertEqual(gsw.label, "Warriors by 2+")
        XCTAssertEqual(gsw.result, false)
        // Clippers by 3: over 2.5 hit, over 3.5 missed — the producer's grades.
        XCTAssertEqual(card.points.first { $0.x == 2.5 }?.result, true)
        XCTAssertEqual(card.points.first { $0.x == 3.5 }?.result, false)
    }

    func testAnOptionOnTheOtherSideIsRefused() throws {
        let flipped = try edited(finalBody().gameQuestionMatrix) { q in
            guard q.kind == "signed_handicap" else { return }
            q.options = q.options.map { var o = $0; o.side = o.side == "home" ? "away" : "home"; return o }
        }
        XCTAssertNil(NBALadderCard9483.margin(try finalInput(matrix: flipped)))
    }

    func testOnlyTypedFullGameLinesOfTheContractEnter() throws {
        let halves = try edited(finalBody().gameQuestionMatrix) { q in
            q.period = QuestionMatrixPeriod(key: "half_1", label: "1st half")
        }
        XCTAssertNil(NBALadderCard9483.margin(try finalInput(matrix: halves)))
        XCTAssertNil(NBALadderCard9483.total(try finalInput(matrix: halves)))
        let untyped = try edited(finalBody().gameQuestionMatrix) { q in
            q.typing = QuestionMatrixTyping(state: "untyped", reason: "untyped_period")
        }
        XCTAssertNil(NBALadderCard9483.total(try finalInput(matrix: untyped)))
        var other = try XCTUnwrap(try finalBody().gameQuestionMatrix)
        other = EventQuestionMatrix(contract: "10238.v2", displayScope: other.displayScope, questions: other.questions)
        XCTAssertNil(NBALadderCard9483.total(try finalInput(matrix: other)))
        XCTAssertNil(NBALadderCard9483.total(try finalInput(matrix: EventQuestionMatrix(displayScope: "game", questions: []))))
    }

    func testTwoOptionsOnOneLineRefuseTheLine() throws {
        let base = try XCTUnwrap(try finalBody().gameQuestionMatrix)
        let total = try XCTUnwrap(base.questions.first {
            $0.kind == "count_threshold" && $0.predicate?.line == 206.5 && $0.subject?.side == "game"
        })
        let twin = QuestionMatrixQuestion(questionKey: total.questionKey + "-twin", kind: total.kind, label: total.label,
                                      quantity: total.quantity, period: total.period, subject: total.subject,
                                      predicate: total.predicate, typing: total.typing, options: total.options.map { o in
                                          QuestionMatrixOption(optionKey: o.optionKey + "-twin", label: o.label, side: o.side,
                                                               published: o.published, result: o.result,
                                                               comparison: o.comparison)
                                      })
        let matrix = EventQuestionMatrix(displayScope: "game", questions: base.questions + [twin])
        let card = try XCTUnwrap(NBALadderCard9483.total(try finalInput(matrix: matrix)))
        XCTAssertNil(card.points.first { $0.x == 206.5 }, "two prices for one dot: the line is refused")
        XCTAssertNotNil(card.points.first { $0.x == 204.5 })
    }

    // MARK: - Before tip-off (15327183)

    func testBeforeTipOffOnlyRecentQuotesAreDots() throws {
        let total = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        XCTAssertEqual(total.phase, .before)
        // A quote is current only while its own clock is under 30 minutes old
        // at 18:40Z; the quiet lines last stamped at 17:01Z lose their dots.
        for point in total.points {
            let observed = try XCTUnwrap(point.detail.observedAt?.asDate)
            let recent = pregameNow.timeIntervalSince(observed) <= 30 * 60
            XCTAssertEqual(point.chance, recent ? point.detail.quoted : nil, point.label)
        }
        XCTAssertTrue(total.points.contains { $0.chance != nil })
        XCTAssertTrue(total.points.contains { $0.chance == nil })
        XCTAssertTrue(total.points.allSatisfy { $0.result == nil }, "no grade before the game")
        XCTAssertNil(total.actual, "no actual before the game")
        XCTAssertEqual(total.caption, "Pregame chance of finishing above each line")
        let margin = try XCTUnwrap(NBALadderCard9483.margin(pregameInput()))
        XCTAssertEqual(margin.points.first { $0.label == "Knicks by 6+" }?.detail.quoted, 0.5)
        // Opens on the drawn line nearest even odds.
        let drawn = margin.points.compactMap(\.chance)
        let best = drawn.map { abs($0 - 0.5) }.min()
        let opened = try XCTUnwrap(margin.defaultIndex)
        XCTAssertEqual(margin.points[opened].chance.map { abs($0 - 0.5) }, best)
    }

    func testAnAgedQuoteLosesOnlyItsNumber() throws {
        // Ageing removes only the number: lines, results and details stay.
        let total = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        let aged = total.current(at: date("2026-10-15T19:30:00Z"))
        XCTAssertEqual(aged.points.map(\.optionKey), total.points.map(\.optionKey))
        XCTAssertEqual(aged.points.map(\.detail), total.points.map(\.detail))
    }

    func testAQuoteThatStopsBeingObservedLosesItsDot() throws {
        let total = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        XCTAssertEqual(total.current(at: pregameNow), total, "nothing ages at the build clock")
        let aged = total.current(at: date("2026-10-15T19:30:00Z"))
        XCTAssertTrue(aged.points.allSatisfy { $0.chance == nil })
        // The deck and reader age through the shared card.
        XCTAssertEqual(NFLEventCard9483.ladder(total).current(at: date("2026-10-15T19:30:00Z")), .ladder(aged))
    }

    func testDuringPlayTheLiveQuoteIsBesideThePinNeverThePin() throws {
        // Status live with the quotes still recent: no pin is served, so no
        // dot — the current quote is carried as "now", separately.
        let live = try XCTUnwrap(NBALadderCard9483.total(pregameInput(status: "live", homeScore: 20, awayScore: 18)))
        XCTAssertEqual(live.phase, .during)
        XCTAssertTrue(live.points.allSatisfy { $0.chance == nil })
        XCTAssertTrue(live.points.contains { $0.now != nil })
        XCTAssertEqual(live.actual, 38)
        XCTAssertEqual(live.caption, "Pregame chance unavailable for these lines")
        // Past the quotes' validity the "now" leaves too (journey 6).
        let later = live.current(at: date("2026-10-15T23:40:00Z"))
        XCTAssertTrue(later.points.allSatisfy { $0.now == nil })
    }

    func testNoGradeOrFinalWordsBeforeTheFinal() throws {
        // The final body's options carry won/lost; on a page that is still
        // live they are not shown — a grade belongs to a finished page.
        var input = try finalInput()
        input = .init(matrix: input.matrix, status: "live", commenceTime: input.commenceTime,
                      homeScore: input.homeScore, awayScore: input.awayScore, pregameProjection: nil,
                      homeShort: input.homeShort, awayShort: input.awayShort, now: input.now)
        let card = try XCTUnwrap(NBALadderCard9483.total(input))
        XCTAssertEqual(card.phase, .during)
        XCTAssertTrue(card.points.allSatisfy { $0.result == nil })
        XCTAssertEqual(card.actual, 205, "the score so far")
    }

    /// lane1b R1 on 04bf6ddc2e: `suspended` is not proof the game began (#4021).
    /// Suspended before tip-off, the recent pregame quotes stay drawn.
    func testASuspendedGameBeforeTipOffKeepsItsPregameQuotes() throws {
        let scheduled = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        let card = try XCTUnwrap(NBALadderCard9483.total(pregameInput(status: "suspended")))
        XCTAssertEqual(card.phase, .before)
        XCTAssertTrue(card.points.contains { $0.chance != nil }, "the recent pregame quotes are drawn")
        XCTAssertEqual(card.points.map(\.chance), scheduled.points.map(\.chance))
        XCTAssertTrue(card.points.allSatisfy { $0.now == nil })
    }

    /// Suspended after tip-off with quotes still recent: in play, but no current
    /// price beside the pin. The same input as `live` does carry one.
    func testASuspendedGamePastTipOffShowsNoCurrentPrice() throws {
        let started = "2026-10-15T18:00:00Z"
        let card = try XCTUnwrap(NBALadderCard9483.total(
            pregameInput(status: "suspended", homeScore: 60, awayScore: 58, commenceTime: started)))
        XCTAssertEqual(card.phase, .during)
        XCTAssertTrue(card.points.allSatisfy { $0.now == nil && $0.chance == nil })
        XCTAssertFalse(card.points.isEmpty, "the lines stay")
        let live = try XCTUnwrap(NBALadderCard9483.total(
            pregameInput(status: "live", homeScore: 60, awayScore: 58, commenceTime: started)))
        XCTAssertEqual(live.phase, .during)
        XCTAssertTrue(live.points.contains { $0.now != nil }, "the control: live carries its current price")
    }

    // MARK: - The deck, the finish, the reader

    func testTheNBADeckIsMarginTotalThenFinish() throws {
        let margin = try XCTUnwrap(NBALadderCard9483.margin(pregameInput()))
        let total = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        let finish = NFLFinishCard9483(phase: .before, pregame: .init(away: 110, home: 114, at: nil),
                                       projectedNow: nil, final: nil, tickStep: 20, startWord: "tip-off")
        XCTAssertEqual(NFLEventCardDeck9483.cards(sportKey: "basketball_nba", finish: finish, milestones: [],
                                                  ladders: [total, margin]).map(\.id),
                       ["margin", "total", "finish"])
        XCTAssertEqual(NFLEventCardDeck9483.cards(sportKey: "americanfootball_nfl", finish: finish, milestones: [],
                                                  ladders: [total, margin]).map(\.id),
                       ["finish"], "an NFL deck never carries the NBA ladders")
        XCTAssertEqual(NFLEventCard9483.ladder(margin).title, "Winning margin")
        XCTAssertEqual(NFLEventCard9483.ladder(total).title, "Scoring expectations")
    }

    func testTheProjectedFinishSpeaksBasketball() throws {
        let base = Date(timeIntervalSince1970: 1_791_000_000)
        let input = ProjectedFinalPointsSeries.Input(
            sportKey: "basketball_nba", sourceKey: "draftkings",
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [.init(at: base.addingTimeInterval(-1800), home: 109.8, away: 112.5, homeProbability: nil, kind: .recorded)],
            actuals: [], kickoffAt: nil, scoreObservationStartAt: base, finalAt: nil,
            asOf: base.addingTimeInterval(600), windowStartAt: nil, requestCutoffAt: nil)
        let card = try XCTUnwrap(NFLFinishCard9483.build(input))
        XCTAssertEqual(card.tickStep, 20)
        XCTAssertEqual(card.startWord, "tip-off")
        XCTAssertEqual(card.headline(awayName: "Warriors", homeName: "Clippers"), "Warriors led the earlier forecast")
        XCTAssertEqual(card.withoutProjectedNow.startWord, "tip-off", "expiry keeps the sport's words")
        // Basketball's axis starts a gridline below the smallest score; the
        // football axis is unchanged and zero-based.
        XCTAssertEqual(NFLFinishCardView9483.pointDomain([109.8, 112.5], step: 20), 80...130)
        XCTAssertEqual(NFLFinishCardView9483.pointDomain([17, 24], step: 7), 0...31.5)
        XCTAssertEqual(NFLFinishCardView9483.pointDomain([3, 6], step: 7), 0...14)
    }

    func testDetailsReadTheHeldCardsOption() throws {
        let held = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        let point = try XCTUnwrap(held.points.first { $0.x == 205.5 })
        XCTAssertEqual(NFLCardReaderHold9483.ladderDetail(point.optionKey, in: [.ladder(held)]), point.detail)
        XCTAssertNil(NFLCardReaderHold9483.ladderDetail("o:missing", in: [.ladder(held)]))
        // A newer matrix moves the live card, not the held one: Refresh is offered.
        let newer = try edited(pregameBody().gameQuestionMatrix) { q in
            q.options = q.options.map { o in
                guard o.optionKey == point.optionKey else { return o }
                return QuestionMatrixOption(optionKey: o.optionKey, label: o.label, side: o.side,
                                         published: QuestionMatrixPublished(value: 0.9, valueState: "quoted",
                                                                            basis: o.published.basis,
                                                                            source: o.published.source,
                                                                            observedAt: "2026-10-15T18:39:00Z"),
                                         result: o.result, comparison: o.comparison)
            }
        }
        let live = try XCTUnwrap(NBALadderCard9483.total(pregameInput(matrix: newer)))
        let header = NFLReaderHeader9483(match: "TOR vs NYK · Pregame", chances: "")
        XCTAssertTrue(NFLCardReaderHold9483.hasUpdate(held: [.ladder(held)], heldHeader: header,
                                                      live: [.ladder(live)], liveHeader: header, now: pregameNow))
        XCTAssertEqual(NFLCardReaderHold9483.ladderDetail(point.optionKey, in: [.ladder(held)])?.quoted, point.detail.quoted)
        XCTAssertFalse(NFLCardReaderHold9483.hasUpdate(held: [.ladder(held)], heldHeader: header,
                                                       live: [.ladder(held)], liveHeader: header, now: pregameNow))
    }

    func testAWithdrawnOptionSelectsNothing() throws {
        let state = NFLCardDeckState9483()
        let card = try XCTUnwrap(NBALadderCard9483.margin(pregameInput()))
        let opened = try XCTUnwrap(state.selectedIndex(in: card))
        XCTAssertEqual(opened, card.defaultIndex)
        state.move(in: card, by: 1)
        XCTAssertEqual(state.selectedIndex(in: card), opened + 1)
        let chosen = card.points[opened + 1].optionKey
        let withdrawn = NBALadderCard9483(family: card.family, phase: card.phase,
                                          points: card.points.filter { $0.optionKey != chosen },
                                          actual: card.actual, forecast: card.forecast,
                                          awayShort: card.awayShort, homeShort: card.homeShort)
        XCTAssertNil(state.selectedIndex(in: withdrawn), "never a neighbouring line")
    }

    func testTheReadoutNamesEachNumberForWhatItIs() throws {
        let final = try XCTUnwrap(NBALadderCard9483.total(finalInput()))
        let lost = try XCTUnwrap(final.points.first { $0.x == 206.5 })
        let finalText = NBALadderCardView9483.readout(final, lost)
        XCTAssertEqual(finalText.main, "Over 206.5")
        XCTAssertEqual(finalText.sub, "Miss")
        XCTAssertFalse(finalText.main.contains("%"), "a settled line prints no chance")

        let before = try XCTUnwrap(NBALadderCard9483.total(pregameInput()))
        let stale = try XCTUnwrap(before.points.first { $0.chance == nil })
        XCTAssertEqual(NBALadderCardView9483.readout(before, stale).main, "\(stale.label) · No recent probability update")
        let priced = try XCTUnwrap(before.points.first { $0.chance != nil })
        XCTAssertEqual(NBALadderCardView9483.readout(before, priced).sub, "Pregame chance")

        let live = try XCTUnwrap(NBALadderCard9483.total(pregameInput(status: "live", homeScore: 20, awayScore: 18)))
        let quoted = try XCTUnwrap(live.points.first { $0.now != nil })
        XCTAssertEqual(NBALadderCardView9483.readout(live, quoted).main, quoted.label)
        XCTAssertEqual(NBALadderCardView9483.readout(live, quoted).sub, "now \(formatProbability(quoted.now!))")
    }

    func testTheMarginAxisIsSymmetricAndHoldsTheActualAndTheProjection() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: (home: 109.8, away: 112.5))))
        let domain = NBALadderCardView9483.domain(card)
        XCTAssertEqual(domain.lowerBound, -domain.upperBound)
        for x in card.points.map(\.x) + [3, -2.7] { XCTAssertTrue(domain.contains(x)) }
        let ticks = NBALadderCardView9483.ticks(card, domain: domain)
        XCTAssertTrue(ticks.contains(0))
        XCTAssertEqual(NBALadderCardView9483.tickText(card, 0), "Tie")
        XCTAssertEqual(NBALadderCardView9483.tickText(card, -10), "10")
        let total = try XCTUnwrap(NBALadderCard9483.total(finalInput()))
        let totalDomain = NBALadderCardView9483.domain(total)
        XCTAssertTrue(totalDomain.contains(205))
        XCTAssertGreaterThan(totalDomain.lowerBound, 150, "a total axis is not zero-based")
    }
}
