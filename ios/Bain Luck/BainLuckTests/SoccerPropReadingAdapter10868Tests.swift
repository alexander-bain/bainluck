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
        // The retained final body serves no stored pin for this option.
        XCTAssertEqual(R.pregame(no, event: event, host: host), .missing(R.Words.preMatchNotRecorded))
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
