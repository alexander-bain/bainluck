import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part seven (the extra-innings story,
/// the approved fifth story family) and its owned leaf, on the RETAINED REAL
/// live extra-innings row of the White Sox–Astros game
/// (`BaseballRetained10868.liveExtraRow`: element 20 of
/// `atlas-v6/raw/mlb-live-20260930.json`, verbatim).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// What is real: the row's identity (market 62972332, outcome 237550051,
/// Kalshi), its `pregame_mark` 0.11, its `over_probability` 0.16 and its own
/// clock 23:04:20.681782Z, decoded from the verbatim bytes; the production
/// card built from it (`MLBExtraInningsCard11284`); and the final body, which
/// files no extra-innings row at all.
///
/// CONSTRUCTED, and named where used: the live `/game-markets` body carrying
/// the row (`liveExtraMarkets` — never the final body); every reader `now`;
/// the owner's admission (read from the row's own served values, because
/// `GameMarketOther` cannot decode them — Native's model debt); and each
/// variant row or admission, which changes only the keys it names.
@MainActor
final class BaseballExtraInningsAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias X = BaseballExtraInningsAdapter10868
    private typealias G = BaseballGamePageAdapter10868
    private typealias Admission = BaseballExtraInningsAdmission10868

    private func make(event: EventDetail? = nil, markets: GameMarketsResponse? = nil,
                       admissions: [Admission]? = nil, selected: String? = nil,
                       now: Date = F.extraNow) throws -> BaseballExtraInningsStory10868? {
        X.story(try event ?? F.liveEvent(), markets: try markets ?? F.liveExtraMarkets(),
                admissions: try admissions ?? [F.liveExtraAdmission()], selected: selected,
                host: F.milestoneHost(now))
    }

    /// CONSTRUCTED: the real admission with only the named values changed.
    private func admission(market: Int? = nil, outcomes: [Int]? = nil, source: String? = nil,
                           pregame: Double?? = nil, recorded: Double?? = nil,
                           recordedAt: String?? = nil) throws -> Admission {
        let real = try F.liveExtraAdmission()
        return Admission(marketID: market ?? real.marketID, outcomeIDs: outcomes ?? real.outcomeIDs,
                         source: source ?? real.source, pregame: pregame ?? real.pregame,
                         recorded: recorded ?? real.recorded, recordedAt: recordedAt ?? real.recordedAt)
    }

    // MARK: - The real row

    func testTheRetainedLiveRowMapsToTheProductionOutcomeAndBothOfItsOwnChances() throws {
        let row = try F.liveExtraOther()
        XCTAssertTrue(MLBExtraInningsCard11284.isExtraInnings(row), "the production filing helper files it")
        XCTAssertEqual(row._marketId, 62972332)
        XCTAssertEqual(row.contributorOutcomeIds, [237550051])
        XCTAssertEqual(row.source, "kalshi")
        XCTAssertEqual(row.observedAt, "2026-09-30T23:04:20.681782+00:00")
        XCTAssertNil(row.probability, "the production model reads no chance from this row")
        let served = try F.servedExtraRow()
        XCTAssertEqual(served.pregameMark, 0.11)
        XCTAssertEqual(served.overProbability, 0.16)
        XCTAssertEqual(served.openingOverProbability, 0.08, "a different baseline, never the pregame chance")

        let story = try XCTUnwrap(try make())
        let card = try XCTUnwrap(MLBExtraInningsCard11284.build([row], eventID: F.eventID))
        XCTAssertEqual(story.card, card, "the production card, unchanged")
        XCTAssertEqual(story.options.count, 1)
        let option = story.options[0]
        XCTAssertEqual(option.id, card.outcomes[0].original.id)
        XCTAssertEqual(option.label, "Yes")
        XCTAssertEqual(option.venue, "Kalshi")
        XCTAssertEqual(option.venueResult, .pending, "the row carries no grade")

        let host = F.milestoneHost(F.extraNow)
        let clock = G.clockWords(F.extraRecordedAt, host: host.page)
        XCTAssertEqual(option.pregame, .value(probability: 0.11, text: formatProbability(0.11),
                                              provenance: "Time not recorded",
                                              spoken: "Pregame chance 11 percent, time not recorded"))
        XCTAssertEqual(option.recorded, .value(probability: 0.16, text: formatProbability(0.16),
                                               provenance: "Recorded \(clock) · Kalshi",
                                               spoken: "Recorded in game 16 percent, recorded \(clock)"))
        XCTAssertNotEqual(option.pregame.text, formatProbability(0.08))
        XCTAssertEqual(option.change, "Up 5.0 points since pregame")
        XCTAssertEqual(story.ceiling, 0.25)
        XCTAssertEqual(story.selectedID, option.id)

        // Details: the exact original, with the admitted chances named in it.
        let fields = option.original.sections.flatMap(\.fields)
        XCTAssertEqual(option.original.id, card.outcomes[0].original.id)
        XCTAssertEqual(option.original.title, card.outcomes[0].original.title)
        XCTAssertEqual(fields.first { $0.label == "Pregame chance" }?.value,
                       "\(formatProbability(0.11)) · time not recorded, may be the opening price")
        XCTAssertEqual(fields.first { $0.label == "Recorded in game" }?.value,
                       "\(formatProbability(0.16)) · \(MLBOriginal11284.stamp("2026-09-30T23:04:20.681782+00:00"))")
        XCTAssertEqual(fields.first { $0.label == "Venue result" }?.value, "Pending")
        XCTAssertEqual(fields.first { $0.label == "Inning result" }?.value, "Unavailable")
        XCTAssertFalse(fields.contains { $0.value.contains(formatProbability(0.08)) })
    }

    func testWithoutAnAdmissionTheProductionOutcomeKeepsEachChancesOwnWords() throws {
        let story = try XCTUnwrap(try make(admissions: []))
        let option = try XCTUnwrap(story.options.first)
        XCTAssertEqual(option.pregame, .unavailable("Pregame chance unavailable"))
        XCTAssertEqual(option.recorded, .unavailable("In-game chance unavailable"))
        XCTAssertNil(option.change)
        XCTAssertEqual(option.venueResult, .pending)
        XCTAssertEqual(story.selectedID, option.id)
        XCTAssertEqual(story.ceiling, 0.25)
        let fields = option.original.sections.flatMap(\.fields)
        XCTAssertEqual(fields.first { $0.label == "Pregame chance" }?.value, "Unavailable", "the production words")
        XCTAssertNil(fields.first { $0.label == "Recorded in game" })
    }

    func testTheFinalBodyAnotherEventsMarketsOrNoMarketsMakeNoStory() throws {
        let final = try F.finalEvent()
        let finalMarkets = try F.markets()
        XCTAssertNil(try make(event: final, markets: finalMarkets, now: F.finalNow),
                     "the retained final body files no extra-innings row; the live one is never transplanted")
        XCTAssertFalse(finalMarkets.other?.contains { MLBExtraInningsCard11284.isExtraInnings($0) } ?? false)
        XCTAssertFalse(BaseballStoriesAdapter10868.finalCards(final, markets: finalMarkets, related: try F.related())
            .contains { if case .extraInnings = $0 { return true } else { return false } },
                       "no final binding is made from any other row")
        XCTAssertNil(try make(markets: F.liveExtraMarkets(eventID: 1)), "another event's markets")
        XCTAssertNil(X.story(try F.liveEvent(), markets: nil, admissions: [try F.liveExtraAdmission()],
                             selected: nil, host: F.milestoneHost(F.extraNow)))
    }

    // MARK: - Identity

    func testOnlyOneAdmissionNamingExactlyThisRowAttaches() throws {
        let foreign: [Admission] = [
            try admission(market: 62972333), try admission(outcomes: [237550052]),
            try admission(outcomes: [237550051, 237550052]), try admission(source: "polymarket"),
        ]
        for wrong in foreign {
            let option = try XCTUnwrap(try make(admissions: [wrong])?.options.first)
            XCTAssertEqual(option.pregame, .unavailable("Pregame chance unavailable"), "\(wrong)")
            XCTAssertEqual(option.recorded, .unavailable("In-game chance unavailable"), "\(wrong)")
        }
        let real = try F.liveExtraAdmission()
        let doubled = try XCTUnwrap(try make(admissions: [real, real])?.options.first)
        XCTAssertNil(doubled.pregame.probability, "two admissions for one row name no single reading")
        let mixed = try XCTUnwrap(try make(admissions: [try admission(market: 1), real])?.options.first)
        XCTAssertEqual(mixed.pregame.probability, 0.11, "a foreign admission disturbs nothing")
    }

    // MARK: - Clocks

    func testEachChanceKeepsItsOwnClockAndARecordedChanceIsOnlyAnInGameObservation() throws {
        // Before first pitch there is no in-game chance; the pregame one shows.
        let before = try XCTUnwrap(try make(event: F.beforeEvent(), now: F.beforeNow)?.options.first)
        XCTAssertEqual(before.pregame.probability, 0.11)
        XCTAssertEqual(before.recorded, .unavailable("In-game chance unavailable"))
        XCTAssertNil(before.change)

        // CONSTRUCTED recorded clocks and values on the real admission.
        let refused: [Admission] = [
            try admission(recordedAt: .some("2026-09-30T20:50:00+00:00")), // before the listed start
            try admission(recordedAt: .some(nil)),                           // undated
            try admission(recordedAt: .some("not a time")),                  // unreadable
            try admission(recorded: .some(1.0)),                             // a settlement value
            try admission(recorded: .some(0.0)),                             // a settlement value
        ]
        for wrong in refused {
            let option = try XCTUnwrap(try make(admissions: [wrong])?.options.first)
            XCTAssertEqual(option.recorded, .unavailable("In-game chance unavailable"), "\(wrong)")
            XCTAssertEqual(option.pregame.probability, 0.11, "the pregame chance stands alone")
            XCTAssertNil(option.change)
        }
        let settledPregame = try XCTUnwrap(try make(admissions: [try admission(pregame: .some(0.0))])?.options.first)
        XCTAssertEqual(settledPregame.pregame, .unavailable("Pregame chance unavailable"))

        // Read before its own clock (23:00Z): not yet recorded.
        let ahead = try XCTUnwrap(try make(now: "2026-09-30T23:00:00+00:00".asDate!)?.options.first)
        XCTAssertEqual(ahead.recorded, .unavailable("In-game chance unavailable"))

        // CONSTRUCTED: `liveEvent` with `start_is_tbd` true — no confirmed start, no in-game claim.
        let tbd = try XCTUnwrap(try make(event: F.liveEvent(["start_is_tbd": true]))?.options.first)
        XCTAssertEqual(tbd.recorded, .unavailable("In-game chance unavailable"))
    }

    func testInALaterViewTheRecordedChanceStaysHistoryAtItsOwnClock() throws {
        let now = try XCTUnwrap(try make()?.options.first)
        let later = try XCTUnwrap(try make(now: F.liveNow)?.options.first)
        XCTAssertEqual(later.recorded, now.recorded, "72 minutes on, the same reading at the same clock")
        guard case .value(_, _, let provenance, _) = later.recorded else { return XCTFail("a recorded chance") }
        XCTAssertTrue(provenance.hasPrefix("Recorded "), "recorded, never current")
    }

    // MARK: - Result

    /// The served row has no grade and the score never answers for it.
    /// CONSTRUCTED: the row with the venue's own grade added (`is_winner`
    /// true, `resolution_source` `api_settlement`).
    func testNoInningResultIsMadeUpAndTheVenueGradeIsTheProductionCardsOwn() throws {
        let plain = try XCTUnwrap(try make()?.options.first)
        XCTAssertEqual(plain.venueResult, .pending, "never read from the 7–3 score")

        let graded = try F.edited(F.liveExtraRow, setting: ["is_winner": true, "resolution_source": "api_settlement"])
        let option = try XCTUnwrap(try make(markets: F.liveExtraMarkets(rows: [graded]))?.options.first)
        XCTAssertEqual(option.venueResult, MLBVenueResult11284.venue(isWinner: true, resolutionSource: "api_settlement"))
        XCTAssertEqual(option.pregame, plain.pregame, "a grade changes no chance")
        XCTAssertEqual(option.recorded, plain.recorded)
        XCTAssertEqual(option.original.sections.flatMap(\.fields).first { $0.label == "Inning result" }?.value,
                       "Unavailable")
    }

    // MARK: - Selection

    /// CONSTRUCTED: a second outcome — the real row with only `outcome_name`
    /// "No" and `contributor_outcome_ids` [237550052] — served before it.
    func testAHeldOutcomeIsKeptAndTheDefaultIsTheFirstOutcomeWithAnAdmittedChance() throws {
        let no = try F.edited(F.liveExtraRow, setting: ["outcome_name": "No", "contributor_outcome_ids": [237550052]])
        let markets = try F.liveExtraMarkets(rows: [no, F.liveExtraRow])
        let story = try XCTUnwrap(try make(markets: markets))
        XCTAssertEqual(story.options.map(\.label), ["No", "Yes"], "the card's own order")
        XCTAssertEqual(story.selectedID, story.options[1].id, "the outcome with an admitted chance")
        XCTAssertEqual(story.options[0].pregame, .unavailable("Pregame chance unavailable"), "never borrowed")

        let held = try XCTUnwrap(try make(markets: markets, selected: story.options[0].id))
        XCTAssertEqual(held.selectedID, story.options[0].id)
        XCTAssertEqual(BaseballExtraInningsModel10868(story: held).selected?.label, "No")

        let withdrawn = try XCTUnwrap(try make(markets: markets, selected: "withdrawn-outcome"))
        XCTAssertEqual(withdrawn.selectedID, "withdrawn-outcome", "passed through, never re-elected")
        XCTAssertNil(BaseballExtraInningsModel10868(story: withdrawn).selected, "no neighbour is shown instead")

        XCTAssertTrue(BaseballExtraInningsModel10868(story: story).showsChooser(canSelect: true))
        XCTAssertFalse(BaseballExtraInningsModel10868(story: story).showsChooser(canSelect: false))
        XCTAssertFalse(BaseballExtraInningsModel10868(story: try XCTUnwrap(try self.make())).showsChooser(canSelect: true),
                       "one outcome is no choice")
    }

    // MARK: - The leaf

    func testTheLeafHandsBackOnlyExactIdentitiesAndSaysEveryPartInWords() throws {
        var log: [String] = []
        let story = try XCTUnwrap(try make())
        let option = try XCTUnwrap(story.options.first)
        let leaf = BaseballExtraInningsPresentation10868(story: story, onSelect: { log.append("select:\($0)") },
                                                         onDetails: { log.append("details:\($0)") })
        leaf.onSelect?(option.id)
        leaf.onDetails?(option.id)
        XCTAssertEqual(log, ["select:\(option.id)", "details:\(option.id)"])
        XCTAssertNil(BaseballExtraInningsPresentation10868(story: story).onSelect)
        XCTAssertNil(BaseballExtraInningsPresentation10868(story: story).onDetails)

        let model = BaseballExtraInningsModel10868(story: story)
        XCTAssertEqual(model.kicker, "Extra innings · Kalshi")
        XCTAssertEqual(model.axis.lower, "0%")
        XCTAssertEqual(model.axis.upper, "25%")
        XCTAssertEqual(model.fraction(option.pregame) ?? -1, 0.11 / 0.25, accuracy: 1e-9)
        XCTAssertEqual(model.fraction(option.recorded) ?? -1, 0.16 / 0.25, accuracy: 1e-9)
        XCTAssertNil(model.fraction(.unavailable("In-game chance unavailable")))
        let clock = G.clockWords(F.extraRecordedAt, host: F.milestoneHost(F.extraNow).page)
        XCTAssertEqual(model.spoken(option),
                       "Yes. Pregame chance 11 percent, time not recorded. "
                       + "Recorded in game 16 percent, recorded \(clock). Up 5.0 points since pregame. "
                       + "Venue result: Pending. Inning result unavailable · this is the earlier market outlook")
    }

    func testTheChangeAndTheSharedScaleFollowTheirRules() {
        func chance(_ value: Double) -> BaseballExtraInningsChance10868 {
            .value(probability: value, text: "", provenance: "", spoken: "")
        }
        XCTAssertEqual(X.change(pregame: chance(0.11), recorded: chance(0.11)), "No change since pregame")
        XCTAssertEqual(X.change(pregame: chance(0.16), recorded: chance(0.11)), "Down 5.0 points since pregame")
        XCTAssertEqual(X.change(pregame: chance(0.11), recorded: chance(0.1104)), "Up <0.1 points since pregame")
        XCTAssertNil(X.change(pregame: chance(0.11), recorded: .unavailable("In-game chance unavailable")))
        XCTAssertEqual(X.ceiling([0.11, 0.16]), 0.25)
        XCTAssertEqual(X.ceiling([0.31, nil]), 0.35, accuracy: 1e-9)
        XCTAssertEqual(X.ceiling([]), 0.25)
    }
}
