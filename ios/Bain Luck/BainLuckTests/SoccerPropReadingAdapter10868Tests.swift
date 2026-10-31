import XCTest
@testable import Bain_Luck

/// #10868 — the soccer prop readings, part three: one original outcome's
/// pre-match chance, in-play chance and result, on the RETAINED REAL
/// `/game-markets` bodies (`SoccerRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// Expected figures are `formatProbability` of the served value and expected
/// clocks are the adapter's own words for the served instant.
@MainActor
final class SoccerPropReadingAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias R = SoccerPropReadingAdapter10868
    private typealias A = SoccerMatchPageAdapter10868

    private func clock(_ stamp: String, _ now: Date) -> String {
        A.clockWords(stamp.asDate!, host: F.propHost(now).words)
    }

    private func leg(_ market: Int, _ id: String, in body: String) throws -> R.Leg {
        try XCTUnwrap(R.legs(market, in: try F.markets(body)).first { $0.id == id })
    }

    // MARK: - Legs

    func testAnAdmittedMarketIsEveryServedRowOfThatIdInServedOrder() throws {
        let markets = try F.markets(F.liveMarkets)
        let both = R.legs(64353426, in: markets)
        XCTAssertEqual(both.map(\.id), ["242143190", "242143189"])
        XCTAssertEqual(both.map(\.label), ["No", "Yes"])
        XCTAssertTrue(both.allSatisfy { $0.clockIsOwn && $0.option != nil })

        let total = R.legs(64353423, in: markets)
        XCTAssertEqual(total.map(\.id), ["242143183"])
        XCTAssertEqual(total.first?.threshold, 2.5)
        // A `totals` row: its clock can be a sibling's.
        XCTAssertEqual(total.first?.clockIsOwn, false)
        XCTAssertTrue(R.legs(99_999_999, in: markets).isEmpty)
    }

    // MARK: - During play

    func testDuringPlayAnOwnClockedRecentQuoteIsTheCurrentChance() throws {
        let event = try F.detail(F.liveDetail)
        let host = F.propHost(F.liveNow)
        let no = try leg(64353426, "242143190", in: F.liveMarkets)

        guard case .recorded(let reading) = R.current(no, event: event, host: host) else {
            return XCTFail("Both teams to score: No is own-clocked and recent")
        }
        XCTAssertEqual(reading.probability, 0.505)
        XCTAssertEqual(reading.text, formatProbability(0.505))
        XCTAssertEqual(reading.detail,
                       "\(R.Words.recorded) \(clock("2026-10-12T12:54:58.549918+00:00", F.liveNow)) · Polymarket")
    }

    /// The served O/U 2.5 Over reads 15% on a recent clock — but that clock is
    /// capped to a sibling's, so it is never the current chance.
    func testDuringPlayATotalsRowQuoteIsWithheldBecauseItsClockMayBeASiblings() throws {
        let event = try F.detail(F.liveDetail)
        let over = try leg(64353423, "242143183", in: F.liveMarkets)
        XCTAssertEqual(R.quoted(over, event: event, host: F.propHost(F.liveNow)), 0.15)
        XCTAssertEqual(R.current(over, event: event, host: F.propHost(F.liveNow)), .withheld(R.Words.noRecentUpdate))
    }

    func testDuringPlayAQuoteOlderThanThirtyMinutesIsNoRecentUpdate() throws {
        let event = try F.detail(F.liveDetail)
        // First team to score: Albacete, observed 12:25:47 — just over 30 minutes before now.
        let albacete = try leg(63178217, "244237964", in: F.liveMarkets)
        XCTAssertEqual(R.current(albacete, event: event, host: F.propHost(F.liveNow)),
                       .withheld(R.Words.noRecentUpdate))
    }

    func testOnceStartedThePreMatchChanceIsTheStoredPinForTheSameOutcome() throws {
        let event = try F.detail(F.liveDetail)
        let yes = try leg(64353426, "242143189", in: F.liveMarkets)

        guard case .value(let reading) = R.pregame(yes, event: event, host: F.propHost(F.liveNow)) else {
            return XCTFail("the matrix serves a pregame_pin baseline for this option")
        }
        // `comparison.baseline` (basis `pregame_pin`) 0.55, observed 11:47:12 —
        // never the 0.49 current quote.
        XCTAssertEqual(reading.probability, 0.55)
        XCTAssertEqual(reading.detail,
                       "\(R.Words.savedBeforeStart) \(clock("2026-10-12T11:47:12.295868+00:00", F.liveNow)) · Polymarket")
    }

    func testAPinObservedAtOrAfterTheListedStartIsNotAPreMatchChance() throws {
        let yes = try leg(64353426, "242143189", in: F.liveMarkets)
        let start = try XCTUnwrap("2026-10-12T11:47:12.295868+00:00".asDate)
        XCTAssertNil(R.pin(yes.option, start: start))
        XCTAssertNotNil(R.pin(yes.option, start: start.addingTimeInterval(1)))
    }

    // MARK: - Period rows (Design, wave-1 review 2026-10-31)

    /// The reader words for a period's dated recorded quote, spelled out.
    private func periodQuote(_ value: Double, _ stamp: String) -> String {
        "In-play chance unavailable · \(formatProbability(value)) recorded \(clock(stamp, F.liveNow)) · Polymarket"
    }

    /// The REAL row: the retained live body's first-half result, home outcome
    /// (market 63178219, outcome 242338171), quoted 99.9% at 12:54:07 — its own
    /// clock, after kickoff, two minutes before `now` — once the half is over.
    /// Every full-match check passes, so only the period rule refuses it: no
    /// decoded field proves this half is still being played (its matrix
    /// question's lifecycle is the venue's `open`; its period is untyped).
    func testDuringPlayTheRetainedFirstHalfResultAt99Point9IsADatedQuoteNotTheCurrentChance() throws {
        let event = try F.detail(F.liveDetail)
        let host = F.propHost(F.liveNow)
        let home = try leg(63178219, "242338171", in: F.liveMarkets)

        guard case .recorded = R.current(home, event: event, host: host) else {
            return XCTFail("the full-match rules alone admit this quote; the period rule is what refuses it")
        }
        XCTAssertEqual(R.periodCurrent(home, event: event, host: host),
                       .withheld(periodQuote(0.999, "2026-10-12T12:54:07.360375+00:00")))
        XCTAssertEqual(R.result(home), .unconfirmed(R.Words.resultUnavailable))

        let questions = try F.markets(F.liveMarkets).gameQuestionMatrix?.questions ?? []
        let question = try XCTUnwrap(questions.first { $0.questionKey == "m:63178219" })
        XCTAssertEqual(question.lifecycle?.state, "open")
        XCTAssertNil(question.period)
    }

    /// CONSTRUCTED: the live body with the first-half result rows carrying the
    /// grades the final body serves for the same outcome ids. A graded period
    /// row shows its grade and no chance.
    func testDuringPlayAGradedPeriodRowShowsItsGradeAndNoChance() throws {
        let body = try F.graded(F.liveMarkets, [242338171: true, 242338170: false])
        let event = try F.detail(F.liveDetail)
        let home = try leg(63178219, "242338171", in: body)
        let draw = try leg(63178219, "242338170", in: body)

        XCTAssertEqual(R.result(home), .won(OutcomeVerdict.won.label))
        XCTAssertEqual(R.result(draw), .lost(OutcomeVerdict.lost.label))
        XCTAssertEqual(R.periodCurrent(home, event: event, host: F.propHost(F.liveNow)),
                       .unavailable(R.Words.settledNoChance))
    }

    /// CONSTRUCTED `now`: the same REAL row forty minutes later. Stale or
    /// recent, the quote stays a dated recorded quote on its own clock.
    func testAStalePeriodQuoteKeepsItsOwnDateAndIsStillNotCurrent() throws {
        let event = try F.detail(F.liveDetail)
        let home = try leg(63178219, "242338171", in: F.liveMarkets)
        let later = F.propHost(F.liveLaterNow)

        XCTAssertEqual(R.current(home, event: event, host: later), .withheld(R.Words.noRecentUpdate))
        XCTAssertEqual(R.periodCurrent(home, event: event, host: later),
                       .withheld(periodQuote(0.999, "2026-10-12T12:54:07.360375+00:00")))
        XCTAssertEqual(R.result(home), .unconfirmed(R.Words.resultUnavailable))
    }

    /// A period row with no price of its own has no quote to keep. REAL: the
    /// served first-half O/U 0.5 Under row (64353427, `period_markets`), which
    /// carries only its Over twin's price. CONSTRUCTED: the first-half home row
    /// with only its `probability` set to null.
    func testAPeriodRowWithNoPriceSaysTheInPlayChanceIsUnavailable() throws {
        let event = try F.detail(F.liveDetail)
        let host = F.propHost(F.liveNow)
        let under = try leg(64353427, "242143192", in: F.liveMarkets)
        XCTAssertEqual(R.periodCurrent(under, event: event, host: host), .unavailable(R.Words.inPlayUnavailable))

        let body = try F.editedRow(F.liveMarkets, outcomeID: 242338171, setting: ["probability": NSNull()])
        let unpriced = try leg(63178219, "242338171", in: body)
        XCTAssertEqual(R.periodCurrent(unpriced, event: event, host: host), .unavailable(R.Words.inPlayUnavailable))
    }

    /// CONSTRUCTED: the first-half home row with only its `observed_at` set to
    /// null. An undated quote cannot be a dated recorded quote.
    func testAnUndatedPeriodQuoteIsNoRecentUpdateAndShowsNoFigure() throws {
        let body = try F.editedRow(F.liveMarkets, outcomeID: 242338171, setting: ["observed_at": NSNull()])
        let undated = try leg(63178219, "242338171", in: body)
        XCTAssertEqual(R.periodCurrent(undated, event: try F.detail(F.liveDetail), host: F.propHost(F.liveNow)),
                       .withheld(R.Words.noRecentUpdate))
    }

    // MARK: - Before kickoff

    func testBeforeKickoffAnOwnClockedRecentQuoteIsThePreMatchChance() throws {
        let event = try F.detail(F.hullDetail)
        let yes = try leg(63390540, "238847205", in: F.hullMarkets)
        guard case .value(let reading) = R.pregame(yes, event: event, host: F.propHost(F.hullNow)) else {
            return XCTFail("Hull–Everton Both teams to score: Yes is 20 minutes old")
        }
        XCTAssertEqual(reading.probability, 0.535)
        XCTAssertEqual(reading.detail,
                       "\(R.Words.recorded) \(clock("2026-10-11T04:37:08.994633+00:00", F.hullNow)) · Polymarket")
    }

    func testBeforeKickoffAnOldQuoteOrASiblingClockedRowHasNoPreMatchChance() throws {
        let event = try F.detail(F.hullDetail)
        let host = F.propHost(F.hullNow)
        // First team to score, observed 23:32 the night before: 5 h 25 min old.
        let everton = try leg(62939466, "238846913", in: F.hullMarkets)
        XCTAssertEqual(R.pregame(everton, event: event, host: host), .missing(R.Words.noRecentUpdate))
        // The O/U 4.5 Under row (`totals`, sibling-capped clock).
        let under = try leg(63390538, "238847202", in: F.hullMarkets)
        XCTAssertEqual(R.pregame(under, event: event, host: host), .missing(R.Words.noRecentUpdate))
    }

    // MARK: - After the final

    func testAfterTheFinalTheResultIsTheVenuesSettlementAndNoChanceIsShown() throws {
        let event = try F.detail(F.finalDetail)
        let host = F.propHost(F.finalNow)
        let no = try leg(64353426, "242143190", in: F.finalMarkets)
        let yes = try leg(64353426, "242143189", in: F.finalMarkets)

        XCTAssertEqual(R.result(no), .won(OutcomeVerdict.won.label))
        XCTAssertEqual(R.result(yes), .lost(OutcomeVerdict.lost.label))
        XCTAssertEqual(R.current(no, event: event, host: host), .unavailable(R.Words.settledNoChance))
        // The retained final body serves no stored pin for this option, and its
        // comparison says only `not_quoted` — no statement that none was
        // recorded — so the pre-match chance is unavailable, not "not recorded".
        XCTAssertEqual(no.option?.comparison?.reason, "not_quoted")
        XCTAssertEqual(R.pregame(no, event: event, host: host), .missing(R.Words.preMatchUnavailable))
    }

    /// CONSTRUCTED: the final Yes leg (served `is_winner: false`) carrying the No
    /// option's matrix grade (`won`). Two grades that disagree confirm neither.
    func testAMatrixGradeThatDisagreesLeavesTheResultUnconfirmed() throws {
        let yes = try leg(64353426, "242143189", in: F.finalMarkets)
        let no = try leg(64353426, "242143190", in: F.finalMarkets)
        let crossed = R.Leg(marketID: yes.marketID, id: yes.id, label: yes.label, row: yes.row,
                            contributors: yes.contributors, isWinner: yes.isWinner,
                            resolutionSource: yes.resolutionSource, threshold: yes.threshold,
                            clockIsOwn: yes.clockIsOwn, option: no.option)
        XCTAssertEqual(R.result(crossed), .unconfirmed(R.Words.resultUnavailable))
    }

    /// During play nothing is settled: the result is unconfirmed, never a loss.
    func testAnOpenOutcomeIsNeverALoss() throws {
        let yes = try leg(64353426, "242143189", in: F.liveMarkets)
        XCTAssertEqual(R.result(yes), .unconfirmed(R.Words.resultUnavailable))
    }

    // MARK: - The pin is the production helper's (Design, baseline-admission review)

    /// REAL: the live Yes option's `pregame_pin` comparison baseline. Soccer's
    /// pin is exactly the production helper's, with soccer's start qualifier.
    func testTheStartedPinIsTheProductionHelpersPinKeptOnlyBeforeTheStart() throws {
        let option = try XCTUnwrap(try leg(64353426, "242143189", in: F.liveMarkets).option)
        let helper = try XCTUnwrap(NBALadderCard9483.pin(option))
        let start = try XCTUnwrap(try F.detail(F.liveDetail).commenceTime?.asDate)
        let soccer = try XCTUnwrap(R.pin(option, start: start))
        XCTAssertEqual(soccer.probability, helper.probability)
        XCTAssertEqual(soccer.observedAt, helper.at.asDate)
    }

    /// The CONSTRUCTED `pregame_reading` the controls below give an option:
    /// available, basis `pregame_pin`, naming `outcome`, 0.45 at `stamp`.
    private func reading(outcome: Int, basis: String = "pregame_pin",
                         stamp: String = "2026-10-12T11:50:00+00:00") -> [String: Any] {
        ["state": "available", "reason": NSNull(), "probability": 0.45, "observed_at": stamp,
         "basis": basis, "outcome_id": outcome]
    }

    /// CONSTRUCTED: the final body's settled No option (served comparison
    /// `not_quoted`, no `pregame_reading`) with only `pregame_reading` set.
    private func finalNo(with pregame: [String: Any]) throws -> R.Leg {
        let body = try F.editedOption(F.finalMarkets, question: "m:64353426", option: "o:242143190",
                                      setting: ["pregame_reading": pregame])
        return try leg(64353426, "242143190", in: body)
    }

    /// Positive control: a reading of this option's one contributor, basis
    /// `pregame_pin`, before the start, is the pre-match chance — through the
    /// helper's own reading branch.
    func testOnceStartedAPregameReadingOfThisOutcomeIsThePreMatchChance() throws {
        let event = try F.detail(F.finalDetail)
        let host = F.propHost(F.finalNow)
        let no = try finalNo(with: reading(outcome: 242143190))
        XCTAssertNotNil(NBALadderCard9483.pin(try XCTUnwrap(no.option)))
        XCTAssertEqual(R.pregame(no, event: event, host: host), .value(R.observation(
            0.45, at: "2026-10-12T11:50:00+00:00".asDate!, lead: R.Words.savedBeforeStart,
            venue: SourceLabels.label(for: "polymarket"), host: host)))
    }

    /// CONTROL, wrong basis: the same reading with only `basis` changed.
    func testAPregameReadingOfAnotherBasisIsNoPin() throws {
        let no = try finalNo(with: reading(outcome: 242143190, basis: "opening_line"))
        XCTAssertNil(NBALadderCard9483.pin(try XCTUnwrap(no.option)))
        XCTAssertEqual(R.pregame(no, event: try F.detail(F.finalDetail), host: F.propHost(F.finalNow)),
                       .missing(R.Words.preMatchUnavailable))
    }

    /// CONTROL, wrong outcome: the same reading naming the Yes outcome.
    func testAPregameReadingOfAnotherOutcomeIsNeverBorrowed() throws {
        let no = try finalNo(with: reading(outcome: 242143189))
        XCTAssertNil(NBALadderCard9483.pin(try XCTUnwrap(no.option)))
        XCTAssertEqual(R.pregame(no, event: try F.detail(F.finalDetail), host: F.propHost(F.finalNow)),
                       .missing(R.Words.preMatchUnavailable))
    }

    /// CONTROL, the start qualifier: the same reading observed five minutes
    /// after kickoff. The helper returns it; soccer keeps only pins before the
    /// listed start.
    func testAPinTheHelperReturnsButObservedAfterKickoffIsNotAPreMatchChance() throws {
        let no = try finalNo(with: reading(outcome: 242143190, stamp: "2026-10-12T12:05:00+00:00"))
        XCTAssertNotNil(NBALadderCard9483.pin(try XCTUnwrap(no.option)))
        XCTAssertNil(R.pin(no.option, start: try F.detail(F.finalDetail).commenceTime?.asDate))
        XCTAssertEqual(R.pregame(no, event: try F.detail(F.finalDetail), host: F.propHost(F.finalNow)),
                       .missing(R.Words.preMatchUnavailable))
    }

    /// CONTROL, precedence: the live Yes option (REAL comparison baseline 0.55
    /// at 11:47:12) with only a `pregame_reading` of 0.45 added. The helper's
    /// precedence — the comparison baseline first — decides, as on every page.
    func testWhenBothAreServedTheHelpersPrecedenceDecides() throws {
        let body = try F.editedOption(F.liveMarkets, question: "m:64353426", option: "o:242143189",
                                      setting: ["pregame_reading": reading(outcome: 242143189,
                                                                          stamp: "2026-10-12T11:30:00+00:00")])
        let yes = try leg(64353426, "242143189", in: body)
        let option = try XCTUnwrap(yes.option)
        XCTAssertEqual(NBALadderCard9483.pin(option)?.probability, 0.55)
        guard case .value(let shown) = R.pregame(yes, event: try F.detail(F.liveDetail), host: F.propHost(F.liveNow)) else {
            return XCTFail("the comparison baseline is the pin")
        }
        XCTAssertEqual(shown.probability, 0.55)
        XCTAssertEqual(shown.detail,
                       "\(R.Words.savedBeforeStart) \(clock("2026-10-12T11:47:12.295868+00:00", F.liveNow)) · Polymarket")
    }

    // MARK: - The matrix contract and scope

    /// CONTROL, unknown contract: the live body with only the matrix `contract`
    /// changed. No option metadata is read — no pin, no side, no grade — and
    /// every served row is still a leg with its own identity.
    func testAnUnknownMatrixContractReadsNoMetadataAndKeepsEveryRow() throws {
        let body = try F.editedMatrix(F.liveMarkets, setting: ["contract": "10238.v2"])
        let real = R.legs(64353426, in: try F.markets(F.liveMarkets))
        let legs = R.legs(64353426, in: try F.markets(body))
        XCTAssertEqual(legs.map(\.id), real.map(\.id))
        XCTAssertEqual(legs.map(\.label), real.map(\.label))
        XCTAssertTrue(legs.allSatisfy { $0.option == nil })
        let yes = try leg(64353426, "242143189", in: body)
        XCTAssertEqual(R.pregame(yes, event: try F.detail(F.liveDetail), host: F.propHost(F.liveNow)),
                       .missing(R.Words.preMatchUnavailable))
        // No side metadata: the half-by-half card has nothing to place.
        XCTAssertNil(SoccerHalvesAdapter10868.input(try F.detail(F.liveDetail), markets: try F.markets(body),
                                                    admitted: F.liveAdmission.halves, host: F.propHost(F.liveNow)))
        // After the final the result is the venue's own settlement alone.
        let finalBody = try F.editedMatrix(F.finalMarkets, setting: ["contract": "10238.v2"])
        let no = try leg(64353426, "242143190", in: finalBody)
        XCTAssertNil(no.option)
        XCTAssertEqual(R.result(no), .won(OutcomeVerdict.won.label))
    }

    /// CONTROL, foreign scope: only `display_scope` changed to `series`. An
    /// absent display scope (served null) is still the game's.
    func testAMatrixOfAnotherDisplayScopeReadsNoMetadata() throws {
        let series = try F.editedMatrix(F.liveMarkets, setting: ["display_scope": "series"])
        XCTAssertTrue(R.legs(64353426, in: try F.markets(series)).allSatisfy { $0.option == nil })
        XCTAssertEqual(R.pregame(try leg(64353426, "242143189", in: series), event: try F.detail(F.liveDetail),
                                 host: F.propHost(F.liveNow)),
                       .missing(R.Words.preMatchUnavailable))
        let unscoped = try F.editedMatrix(F.liveMarkets, setting: ["display_scope": NSNull()])
        XCTAssertEqual(R.pin(try leg(64353426, "242143189", in: unscoped).option,
                             start: try F.detail(F.liveDetail).commenceTime?.asDate)?.probability, 0.55)
    }

    // MARK: - "Not recorded" only on the producer's own word

    /// CONSTRUCTED live variant: the Hull detail with only `status` changed to
    /// `live`. Its first-team option says `no_pregame_pin` — the known
    /// producer's statement — so "not recorded". The same option with only
    /// `comparison` served null says nothing: "unavailable".
    func testNotRecordedOnlyWhereTheProducerSaysNoPinWasRecorded() throws {
        let event = try F.detail(try F.edited(F.hullDetail, setting: ["status": "live"]))
        let host = F.propHost(F.hullNow)
        let everton = try leg(62939466, "238846913", in: F.hullMarkets)
        XCTAssertEqual(everton.option?.comparison?.reason, R.noPregamePinReason)
        XCTAssertEqual(R.pregame(everton, event: event, host: host), .missing(R.Words.preMatchNotRecorded))

        let silent = try F.editedOption(F.hullMarkets, question: "m:62939466", option: "o:238846913",
                                        setting: ["comparison": NSNull()])
        XCTAssertEqual(R.pregame(try leg(62939466, "238846913", in: silent), event: event, host: host),
                       .missing(R.Words.preMatchUnavailable))
        // An unsupported matrix carries no statement either.
        let unsupported = try F.editedMatrix(F.hullMarkets, setting: ["contract": "10238.v2"])
        XCTAssertEqual(R.pregame(try leg(62939466, "238846913", in: unsupported), event: event, host: host),
                       .missing(R.Words.preMatchUnavailable))
    }

    // MARK: - The score the stories share

    func testTheGoalsAreTheProducersScoreDatedByItsOwnClock() throws {
        let live = try F.detail(F.liveDetail)
        let goals = try XCTUnwrap(R.goals(live))
        XCTAssertEqual(goals.total, 4)
        XCTAssertEqual(R.goalsClock(goals, final: false, host: F.propHost(F.liveNow)),
                       "Observed \(A.timeWords("2026-10-12T12:54:19.676980+00:00".asDate!, host: F.propHost(F.liveNow).words))")
        let final = try XCTUnwrap(R.goals(try F.detail(F.finalDetail)))
        XCTAssertEqual(final.total, 5)
        XCTAssertEqual(R.goalsClock(final, final: true, host: F.propHost(F.finalNow)), A.Words.final)
        XCTAssertNil(R.goals(try F.detail(F.hullDetail)))
    }
}

/// CONSTRUCTED matrix edits for the soccer baseline-admission controls.
extension SoccerRetained10868 {
    /// A served `/game-markets` body with keys replaced on the ONE matrix
    /// option whose `option_key` is `option`, in the ONE question whose
    /// `question_key` is `question`: CONSTRUCTED. `NSNull()` serves null. Every
    /// other option, question and key stays as served; a missing one fails.
    static func editedOption(_ json: String, question: String, option: String,
                             setting: [String: Any]) throws -> String {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        var matrix = try XCTUnwrap(object["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let q = try XCTUnwrap(questions.firstIndex { ($0["question_key"] as? String) == question })
        var options = try XCTUnwrap(questions[q]["options"] as? [[String: Any]])
        let o = try XCTUnwrap(options.firstIndex { ($0["option_key"] as? String) == option })
        for (key, value) in setting { options[o][key] = value }
        questions[q]["options"] = options
        matrix["questions"] = questions
        object["game_question_matrix"] = matrix
        return String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
    }

    /// A served body with top-level keys of its `game_question_matrix`
    /// replaced (`contract`, `display_scope`): CONSTRUCTED.
    static func editedMatrix(_ json: String, setting: [String: Any]) throws -> String {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        var matrix = try XCTUnwrap(object["game_question_matrix"] as? [String: Any])
        for (key, value) in setting { matrix[key] = value }
        object["game_question_matrix"] = matrix
        return String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
    }
}
