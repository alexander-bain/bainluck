import XCTest
@testable import Bain_Luck

/// The US Open screen's curated questions (#3043) — "Will Sinner actually play?".
///
/// ═══ WHAT THESE GUARD, AND WHY IT IS NOT "THE SECTION RENDERS" ═══
///
/// The section is easy; the three rules inside it are not, and each one has
/// already cost the web page a shipped defect:
///
///   • **UX-P207 / Alex's standing ruling 2 — settled means settled.** The
///     register says `sinner-competes` closed on 30 August with the answer
///     "No". Kalshi is still quoting the Yes at 1%. Both facts are true; a card
///     that prints the second and drops the first tells the reader a decided
///     question is still up in the air. `testSettledQuestionPrintsTheResult…`
///     is that specimen, from the live wire.
///   • **CERT-430 — a comparison is complete or it is not presented as one.**
///     Two declared legs, one unpriced: dropping the unpriced row for having
///     nothing to rank it by turns a two-player question into a one-player
///     answer. The card must keep the row, name the hole, and refuse the
///     confident type.
///   • **CERT-411 — a card is as fresh as its OLDEST printed number.** A field
///     card that reads liveness off its leader renders three numbers in the
///     confident type when one of them is three weeks old.
///
/// Each of those is a composite: every half is locally true and the pair is a
/// lie. That is why the assertions below are mostly about what the card does
/// NOT say.
final class TournamentHubPropsTests: XCTestCase {

    // MARK: - Helpers

    private func fixture() throws -> TournamentHubPresentation {
        try TournamentHubPropsFixture.presentation()
    }

    private func row(_ key: String) throws -> TournamentHubPresentation.PropRow {
        let p = try fixture()
        return try XCTUnwrap(p.props.first { $0.id == key }, "fixture is missing \(key)")
    }

    /// A hub response carrying nothing but the given props, so a branch the live
    /// register does not happen to be in today can still be asserted.
    private func present(props: String) throws -> TournamentHubPresentation {
        let json = """
        {"slug":"us-open","title":"US Open","slate":{"matches":[]},
         "results":{"matches":[]},"boards":[],"bracket":{},"props":[\(props)]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return TournamentHubPresentation(
            response: try decoder.decode(TournamentHubResponse.self, from: Data(json.utf8)))
    }

    // MARK: - The live payload decodes, unedited

    func testProductionPropsDecode() throws {
        let response = try TournamentHubPropsFixture.decode()
        XCTAssertEqual(response.props.count, 5)
        XCTAssertEqual(
            response.props.map(\.key),
            ["sinner-competes", "usa-men-final-berth", "second-major",
             "sabalenka-title-defence", "usa-women-quarterfinal-count"],
            "the register's order is the card order — the phone does not re-curate")

        let p = try fixture()
        XCTAssertEqual(p.props.count, 5)
        XCTAssertNil(p.propsEmptyNote)
        XCTAssertNil(p.propsTrimNote, "five is under the display cap")
    }

    func testEveryQuestionKeepsItsWordsAndItsHook() throws {
        let p = try fixture()
        XCTAssertEqual(p.props[0].question, "Will Sinner actually play?")
        XCTAssertEqual(p.props[0].hook, "A withdrawal reshapes the entire men's board.")
        for row in p.props {
            XCTAssertFalse(row.question.isEmpty, "\(row.id) lost its question")
            XCTAssertFalse(
                row.question.contains("_"),
                "\(row.id) is printing a register key where the question belongs")
        }
    }

    // MARK: - UX-P207: settled means settled

    func testSettledQuestionPrintsTheResultAndNeverTheSurvivingQuote() throws {
        let row = try row("sinner-competes")

        // The whole point. The wire says probability 0.01 on an outcome named
        // "Yes"; the answer is "No".
        XCTAssertEqual(row.headline, "No")
        XCTAssertNotEqual(row.headline, "1%")
        XCTAssertTrue(row.headlineIsMuted)
        XCTAssertFalse(
            row.isLive,
            "a live QUOTE on a closed question is not a live ANSWER")

        // The last reading is kept and demoted — the market really did close at
        // 1% and deleting that loses a true fact.
        XCTAssertEqual(row.settledLine, "Settled 30 August 2026 · last reading 1%")

        // No freshness anywhere: an age chip answers "is this current?", which
        // is no longer the reader's question, and at 56 hours it answers it in a
        // way that invites the reader to wait for a new number.
        XCTAssertNil(row.freshnessNote)
        XCTAssertNil(row.answerLine, "the answer line belongs to an open question")
        XCTAssertTrue(row.outcomes.isEmpty, "an answer card's one outcome IS the headline")
    }

    func testSettledWithoutAPublishedResultSaysSoRatherThanGuessing() throws {
        let p = try present(props: """
        {"key":"k","title":"Did it happen?","settled":true,
         "answer_entity_key":"k:yes","legs":1,
         "outcomes":[{"entity_key":"k:yes","display_name":"Yes","probability":0.6,
                      "probability_is_live":true,"age_hours":0.2,"is_answer":true}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertNil(row.headline, "a closed question with no published result prints no headline")
        XCTAssertEqual(row.settledLine, "Settled · last reading 60% · result not published")
        XCTAssertFalse(row.isLive)
    }

    /// The guard the model's `settled` decode exists for.
    func testANonBooleanSettledRendersOpenRatherThanClosingEveryCard() throws {
        let p = try present(props: """
        {"key":"k","title":"Open?","settled":"yes","answer_entity_key":"k:yes","legs":1,
         "outcomes":[{"entity_key":"k:yes","display_name":"Yes","probability":0.4,
                      "probability_is_live":true,"age_hours":0.1,"is_answer":true}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertNil(row.settledLine, "`settled: \"yes\"` is not the literal `true`")
        XCTAssertEqual(row.headline, "40%")
        XCTAssertTrue(row.isLive)
    }

    // MARK: - The ordinary live answer card

    func testALiveAnswerCardPrintsItsNumberConfidently() throws {
        let row = try row("usa-men-final-berth")
        XCTAssertEqual(row.headline, "27%")
        XCTAssertFalse(row.headlineIsMuted)
        XCTAssertTrue(row.isLive)
        XCTAssertEqual(row.answerLine, "Yes")
        XCTAssertNil(row.freshnessNote, "a healthy card that keeps apologising teaches "
                     + "the reader the apology is decorative")
        XCTAssertNil(row.settledLine)
        XCTAssertNil(row.incompleteNote)
    }

    func testTheAnswerIsTheCuratedOneAndNotTheBiggestNumber() throws {
        // Two outcomes, the curated answer at 12% and its complement at 88%.
        // Headlining the leader answers a question nobody asked.
        let p = try present(props: """
        {"key":"k","title":"Will it rain?","answer_entity_key":"k:yes","legs":1,
         "outcomes":[{"entity_key":"k:no","display_name":"No","probability":0.88,
                      "probability_is_live":true,"age_hours":0.1,"is_answer":false},
                     {"entity_key":"k:yes","display_name":"Yes","probability":0.12,
                      "probability_is_live":true,"age_hours":0.1,"is_answer":true}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertEqual(row.headline, "12%")
        XCTAssertEqual(row.answerLine, "Yes")
    }

    func testAnAnswerPinnedAtTheRailLooksDecidedButIsNotCalledSettled() throws {
        let p = try present(props: """
        {"key":"k","title":"Decided?","answer_entity_key":"k:yes","legs":1,
         "outcomes":[{"entity_key":"k:yes","display_name":"Yes","probability":0.9995,
                      "probability_is_live":true,"age_hours":0.1,"is_answer":true}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertEqual(row.answerLine, "Yes · Looks decided")
        XCTAssertNil(
            row.settledLine,
            "a number at the rail is our inference; only the register may declare settlement")
    }

    // MARK: - CERT-430: a comparison is whole or it says what it is missing

    func testACompleteComparisonPrintsEveryLegAndNoHeadline() throws {
        let row = try row("second-major")
        XCTAssertNil(
            row.headline,
            "\"who wins a second major\" has no single answer — picking the leader "
            + "to fill the slot is exactly the guess this card refuses")
        XCTAssertEqual(row.outcomes.map(\.name), ["Carlos Alcaraz", "Jannik Sinner"])
        XCTAssertEqual(row.outcomes.map(\.percentText), ["47%", "1%"])
        XCTAssertTrue(row.outcomes.allSatisfy { !$0.isMuted })
        XCTAssertNil(row.incompleteNote)
        XCTAssertTrue(row.isLive)
    }

    func testAComparisonMissingALegKeepsTheRowNamesTheHoleAndIsNeverLive() throws {
        let p = try present(props: """
        {"key":"second-major","title":"Who wins a second major this year?","legs":2,
         "outcomes":[{"entity_key":"a","display_name":"Carlos Alcaraz","probability":null,
                      "observed_at":"2026-09-01T00:00:00+00:00"},
                     {"entity_key":"b","display_name":"Jannik Sinner","probability":0.555,
                      "probability_is_live":true,"age_hours":0.4}]}
        """)
        let row = try XCTUnwrap(p.props.first)

        XCTAssertEqual(
            row.outcomes.map(\.name), ["Jannik Sinner", "Carlos Alcaraz"],
            "the unquoted subject is kept, and last — burying it mid-list would "
            + "hide the admission the card exists to make")
        XCTAssertEqual(row.outcomes.map(\.percentText), ["56%", nil])
        XCTAssertEqual(row.outcomes.last?.missingText, "No number yet")
        XCTAssertFalse(
            row.isLive,
            "one fresh leg must not certify a comparison whose other leg produced nothing")
        XCTAssertTrue(row.outcomes.allSatisfy(\.isMuted))
        XCTAssertEqual(
            row.incompleteNote,
            "We have no number for Carlos Alcaraz yet, so this comparison is not complete.")
        XCTAssertNil(
            row.freshnessNote,
            "\"Last number 24 minutes ago\" beside a row that has never had one at "
            + "all answers a question the reader did not ask and hides the one they will")
    }

    func testASettledComparisonDropsTheYesBecauseThereIsNoLaterLeft() throws {
        let p = try present(props: """
        {"key":"k","title":"Who?","legs":2,"settled":true,"settled_answer":"Alcaraz",
         "outcomes":[{"entity_key":"a","display_name":"Carlos Alcaraz","probability":null},
                     {"entity_key":"b","display_name":"Jannik Sinner","probability":0.4,
                      "probability_is_live":false,"age_hours":90}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertEqual(row.headline, "Alcaraz")
        XCTAssertEqual(row.outcomes.last?.missingText, "No number")
        XCTAssertEqual(
            row.incompleteNote,
            "We have no number for Carlos Alcaraz, so this comparison is not complete "
            + "and the question has closed.")
        XCTAssertEqual(row.settledLine, "Settled · last reading")
    }

    func testAComparisonWhoseLegNeverArrivedAsARowCountsTheHoleAnyway() throws {
        let p = try present(props: """
        {"key":"k","title":"Who?","legs":3,
         "outcomes":[{"entity_key":"b","display_name":"Jannik Sinner","probability":0.4,
                      "probability_is_live":true,"age_hours":0.1}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertEqual(
            row.incompleteNote,
            "We have no number for 2 of the names in it yet, so this comparison is not complete.")
        XCTAssertFalse(row.isLive)
    }

    // MARK: - CERT-411: a card is as fresh as its oldest printed number

    func testAFieldCardRanksItsTopThreeAndNoMore() throws {
        let p = try present(props: """
        {"key":"k","title":"Who wins?","legs":1,
         "outcomes":[{"entity_key":"a","display_name":"A","probability":0.1,
                      "probability_is_live":true,"age_hours":0.1},
                     {"entity_key":"b","display_name":"B","probability":0.4,
                      "probability_is_live":true,"age_hours":0.1},
                     {"entity_key":"c","display_name":"C","probability":0.3,
                      "probability_is_live":true,"age_hours":0.1},
                     {"entity_key":"d","display_name":"D","probability":0.2,
                      "probability_is_live":true,"age_hours":0.1}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertEqual(row.outcomes.map(\.name), ["B", "C", "D"])
        XCTAssertNil(row.headline)
        XCTAssertTrue(row.isLive)
    }

    func testOneStaleRunnerUpMutesTheWholeFieldCardAndNamesIt() throws {
        let p = try present(props: """
        {"key":"k","title":"Who wins?","legs":1,
         "outcomes":[{"entity_key":"a","display_name":"Leader","probability":0.5,
                      "probability_is_live":true,"age_hours":1},
                     {"entity_key":"b","display_name":"Runner-up","probability":0.3,
                      "probability_is_live":false,"age_hours":480}]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertFalse(
            row.isLive,
            "reading liveness off the LEADER is the bug: three numbers in the "
            + "confident type when one is three weeks old")
        XCTAssertTrue(row.outcomes.allSatisfy(\.isMuted))
        XCTAssertEqual(
            row.freshnessNote, "Runner-up: Last number 20 days ago",
            "naming the old one stops the bare age reading as \"we have not "
            + "looked at any of this in three weeks\"")
    }

    func testAnUnpricedQuestionSaysItHasNoNumberRatherThanRenderingEmpty() throws {
        let p = try present(props: """
        {"key":"k","title":"Who wins?","legs":1,"outcomes":[]}
        """)
        let row = try XCTUnwrap(p.props.first)
        XCTAssertFalse(row.isLive)
        XCTAssertNil(row.headline)
        XCTAssertTrue(row.outcomes.isEmpty)
        XCTAssertEqual(row.freshnessNote, "No number yet")
    }

    // MARK: - Ages round down, and the settled date does not move by device

    func testFreshnessAgeRoundsDown() {
        typealias P = TournamentHubPresentation
        XCTAssertEqual(P.propFreshnessAge(nil), "never")
        XCTAssertEqual(P.propFreshnessAge(0.01), "1 min ago", "never zero minutes")
        XCTAssertEqual(P.propFreshnessAge(0.75), "45 min ago")
        XCTAssertEqual(P.propFreshnessAge(1.0), "1 hour ago")
        XCTAssertEqual(P.propFreshnessAge(1.9), "1 hour ago")
        XCTAssertEqual(P.propFreshnessAge(47.9), "47 hours ago")
        XCTAssertEqual(P.propFreshnessAge(48), "2 days ago")
        XCTAssertEqual(P.propFreshnessAge(191.9), "7 days ago", "8 days must never flatter to 7")
        XCTAssertEqual(P.propFreshnessAge(192), "8 days ago")
    }

    /// `2026-08-30T15:05:00+00:00` is the 29th in Honolulu. A settled date that
    /// changes with where the reader is standing is a different fact per phone.
    func testTheSettledDateIsPinnedToUTC() {
        typealias P = TournamentHubPresentation
        XCTAssertEqual(P.propSettledDate("2026-08-30T15:05:00+00:00"), "30 August 2026")
        XCTAssertEqual(P.propSettledDate("2026-08-30T01:00:00+00:00"), "30 August 2026")
        XCTAssertEqual(P.propSettledDate("2026-08-30T23:30:00.123456+00:00"), "30 August 2026")
        XCTAssertNil(P.propSettledDate(nil))
        XCTAssertNil(P.propSettledDate("not a date"))
    }

    // MARK: - D27: rows OR a sentence, never silence

    func testAPayloadWithNoPropsSaysSoInsteadOfDisappearing() throws {
        // The frozen 2026-09-03 capture cut `props`, so it is the real
        // no-props wire shape as well as the empty-section case.
        let p = TournamentHubPresentation(response: try TournamentHubProdFixture.decode())
        XCTAssertTrue(p.props.isEmpty)
        XCTAssertEqual(
            p.propsEmptyNote,
            "No curated questions on this tournament yet — they appear here as "
            + "Kalshi and Polymarket open them.")
        XCTAssertNil(p.propsTrimNote)
        XCTAssertNil(
            p.wholePayloadEmptyNote,
            "a payload with matches and boards is not empty just because it has no props")
    }

    func testARegisterThatGrowsIsTrimmedAndSaysBySoMuch() throws {
        let one = { (i: Int) in """
        {"key":"k\(i)","title":"Q\(i)","answer_entity_key":"k\(i):yes","legs":1,
         "outcomes":[{"entity_key":"k\(i):yes","display_name":"Yes","probability":0.5,
                      "probability_is_live":true,"age_hours":0.1,"is_answer":true}]}
        """ }
        let p = try present(props: (1...9).map(one).joined(separator: ","))
        XCTAssertEqual(p.props.count, TournamentHubPresentation.propsLimit)
        XCTAssertEqual(p.propsTrimNote, "Showing 6 of 9 questions")
        XCTAssertEqual(p.props.map(\.id), ["k1", "k2", "k3", "k4", "k5", "k6"])
    }
}
