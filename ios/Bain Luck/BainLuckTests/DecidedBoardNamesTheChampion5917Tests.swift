import XCTest
@testable import Bain_Luck

/// #5917 (native arm) — THE TITLE BOARD DISAPPEARED WHEN THE DRAW WAS DECIDED.
///
/// ux/1235 found the web board printing "Elena Rybakina 99% TO WIN THE TITLE"
/// sixteen hours after she won it. This phone had the same gap and a quieter
/// symptom: `boardSection` kept only rows whose `state` is `live`, a decided
/// draw has none, so the WOMEN'S SINGLES card was simply absent from the hub.
/// Photographed on production at 15:46Z on finals day —
/// `artifacts-native-020/n147-hub-s07.png` shows the men's board followed
/// directly by LATEST RESULTS, with no women's board between them — and the
/// men's board was two hours from the same fate.
///
/// A vanished card is the worse of the two failures: the wrong number is at
/// least arguable on screen, while an absent one reads as "we never built that
/// part" (D27) and cannot be reported by a reader who does not know it should
/// be there. The champion is not a missing contender.
///
/// WHAT THE PAYLOAD SAYS AND WHAT THIS FILE MAY READ. live's half (#5917) sends
/// `board.decided = {winner_entity_key}`, moves the champion to rank 1, and
/// settles every row to `state: won` / `eliminated` with `probability: null`.
/// The client acts on THAT and never on `results.matches[]`: adjudicating the
/// state of a draw from match rows is the client deciding state, which is the
/// reason live shipped first.
///
/// The vocabulary is the web's — `Won` / `Out`, from `contenderChart.ts`'s
/// legend — so one tournament cannot be `Won` on one surface and `Champion` on
/// the other (notice 35, one card family).
final class DecidedBoardNamesTheChampion5917Tests: XCTestCase {

    // MARK: - 🔴 The decided board

    func testTheDecidedBoardIsONSCREENAtAll() throws {
        let p = decided()
        let board = try XCTUnwrap(
            p.boards.first,
            "the women's board vanished from the phone the moment Rybakina won "
            + "it — a board whose draw is decided still has everything to say")
        XCTAssertEqual(board.title, "Women's Singles")
        XCTAssertEqual(board.rows.count, 3)
    }

    func testItNamesTheChampionInsteadOfPricingHer() throws {
        let board = try XCTUnwrap(decided().boards.first)
        XCTAssertEqual(board.settledNote, "Settled · Elena Rybakina won the title.")

        let champion = try XCTUnwrap(board.rows.first)
        XCTAssertEqual(champion.name, "Elena Rybakina")
        XCTAssertEqual(champion.percentText, "Won")
    }

    func testNoRowOfADecidedBoardPrintsAProbabilityOrADash() throws {
        let board = try XCTUnwrap(decided().boards.first)
        for row in board.rows {
            XCTAssertFalse(
                row.percentText.contains("%"),
                "\(row.name) printed \(row.percentText): a probability to win a "
                + "title that has been won is the #5917 defect itself")
            XCTAssertNotEqual(
                row.percentText, absentProbabilityMarker,
                "a dash in the to-win-the-title column reads as \"we lost the "
                + "number\". We did not lose it — the question is over")
        }
        XCTAssertEqual(board.rows.map(\.percentText), ["Won", "Out", "Out"])
    }

    func testTheEndOfTheDrawIsNotReportedAsAnAbsenceOfPrices() {
        XCTAssertNil(
            decided().boardsEmptyNote,
            "\"Nobody is priced to win the title yet\" is a promise of a number "
            + "that is never coming — on the day the champion was crowned")
    }

    func testTheChampionLeadsEvenWhenTheRanksDoNot() throws {
        // A payload whose ranks still carry the order the dying prices left
        // behind. The answer outranks the standings that produced it.
        let board = try XCTUnwrap(
            presentation(
                boardJSON(
                    decided: "elena-rybakina",
                    rows: [
                        (key: "aryna-sabalenka", name: "Aryna Sabalenka",
                         state: "eliminated", rank: 1),
                        (key: "elena-rybakina", name: "Elena Rybakina",
                         state: "won", rank: 2),
                    ])
            ).boards.first)

        XCTAssertEqual(board.rows.map(\.name), ["Elena Rybakina", "Aryna Sabalenka"])
        XCTAssertEqual(board.rows.map(\.percentText), ["Won", "Out"])
    }

    func testABoardWeCannotNarrateSaysSoWithoutPrintingTheRawKey() throws {
        // An entity key that resolves to nobody. The general sentence is honest;
        // "Settled · someone-else won the title." is a robot talking.
        let board = try XCTUnwrap(
            presentation(
                boardJSON(
                    decided: "someone-else",
                    rows: [(key: "elena-rybakina", name: "Elena Rybakina",
                            state: "won", rank: 1)])
            ).boards.first)

        XCTAssertEqual(board.settledNote, "Settled · this draw is decided.")
        XCTAssertFalse(try XCTUnwrap(board.settledNote).contains("someone-else"))
    }

    func testAWonRowAloneIsEnoughToKeepTheCard() throws {
        // Half the contract: `decided` absent, the row's own state saying it.
        // The two halves are one payload's two ways of saying the same thing,
        // and the card must not vanish because only one of them arrived.
        let board = try XCTUnwrap(
            presentation(
                boardJSON(
                    decided: nil,
                    rows: [
                        (key: "elena-rybakina", name: "Elena Rybakina",
                         state: "won", rank: 1),
                        (key: "aryna-sabalenka", name: "Aryna Sabalenka",
                         state: "eliminated", rank: 2),
                    ])
            ).boards.first)

        XCTAssertEqual(board.settledNote, "Settled · Elena Rybakina won the title.")
        XCTAssertEqual(board.rows.map(\.percentText), ["Won", "Out"])
    }

    func testADecidedBoardWithNoHistoryDrawsNoChartFrame() throws {
        let board = try XCTUnwrap(decided().boards.first)
        XCTAssertNil(
            board.chart,
            "settled rows arrive with no price and no trend, so the frame would "
            + "be empty and captioned with a sentence about prices nobody is "
            + "waiting for (the web's #5934, arm 5)")
    }

    func testTheTrimNoteStopsSayingPeopleAreStillInTheDraw() throws {
        let rows = (1...8).map {
            (key: "p\($0)", name: "Player \($0)",
             state: $0 == 1 ? "won" : "eliminated", rank: $0)
        }
        let board = try XCTUnwrap(
            presentation(boardJSON(decided: "p1", rows: rows)).boards.first)

        XCTAssertEqual(board.trimNote, "Top 6 of 8 in the final standings")
    }

    // MARK: - 🟢 The live board is untouched

    func testALiveBoardStillRanksPricedContendersAndSaysNothingAboutSettlement()
        throws
    {
        let board = try XCTUnwrap(live().boards.first)

        XCTAssertNil(board.settledNote, "nothing is settled, so nothing is said")
        XCTAssertNotNil(board.chart, "the race is on and has a line to draw")
        XCTAssertEqual(board.rows.map(\.name), ["Alexander Zverev", "Ben Shelton"])
        XCTAssertEqual(board.rows.map(\.percentText), ["59%", "41%"])
    }

    func testAnEliminatedRowStillNeverTakesAPhoneRowFromALiveContender() throws {
        // The six-row budget rule this fix is easy to break: mid-tournament the
        // board carries everyone who has been knocked out, and those rows belong
        // to the web page's greyed list, not to a phone showing a live race.
        let board = try XCTUnwrap(
            presentation(
                boardJSON(
                    decided: nil,
                    rows: [
                        (key: "a", name: "A", state: "live", rank: 1),
                        (key: "b", name: "B", state: "eliminated", rank: 2),
                    ],
                    probabilities: ["a": 0.6])
            ).boards.first)

        XCTAssertEqual(board.rows.map(\.name), ["A"])
        XCTAssertNil(board.settledNote)
    }

    func testADecidedDrawWeCannotDrawAtAllStillPromisesNothing() {
        // The one case where the sentence itself is reachable on a finished
        // tournament: a decided board that carries no rows to render. "Nobody is
        // priced YET" is a promise of a number that is never coming, and an
        // empty space is the honest version of it (notice 34).
        let p = presentation(boardJSON(decided: "elena-rybakina", rows: []))
        XCTAssertTrue(p.boards.isEmpty)
        XCTAssertNil(p.boardsEmptyNote)
    }

    func testABoardWithNoRowsAtAllStillSaysTheHonestSentence() {
        let p = presentation(boardJSON(decided: nil, rows: []))
        XCTAssertTrue(p.boards.isEmpty)
        XCTAssertEqual(p.boardsEmptyNote, "Nobody is priced to win the title yet.")
    }

    // MARK: - Fixtures

    /// The women's board as production served it at 15:43Z on finals day: one
    /// `won` row, the field `eliminated`, every probability null, `decided`
    /// naming the champion. Trimmed to three rows — 44 of them prove nothing the
    /// first three do not.
    private func decided() -> TournamentHubPresentation {
        presentation(
            boardJSON(
                decided: "elena-rybakina",
                rows: [
                    (key: "elena-rybakina", name: "Elena Rybakina",
                     state: "won", rank: 1),
                    (key: "aryna-sabalenka", name: "Aryna Sabalenka",
                     state: "eliminated", rank: 2),
                    (key: "anastasia-potapova", name: "Anastasia Potapova",
                     state: "eliminated", rank: 3),
                ]))
    }

    /// The men's board the same morning: two live contenders, priced, charted.
    private func live() -> TournamentHubPresentation {
        presentation(
            boardJSON(
                label: "Men's Singles",
                draw: "mens-singles",
                decided: nil,
                rows: [
                    (key: "alexander-zverev", name: "Alexander Zverev",
                     state: "live", rank: 1),
                    (key: "ben-shelton", name: "Ben Shelton",
                     state: "live", rank: 2),
                ],
                probabilities: ["alexander-zverev": 0.585, "ben-shelton": 0.415],
                trend: true))
    }

    private func presentation(_ json: String) -> TournamentHubPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // Force-try: the literal is in this file, so a broken one is a test bug
        // and must fail loudly rather than decode into an empty board.
        let response = try! decoder.decode(
            TournamentHubResponse.self, from: Data(json.utf8))
        return TournamentHubPresentation(response: response)
    }

    private func boardJSON(
        label: String = "Women's Singles",
        draw: String = "womens-singles",
        decided: String?,
        rows: [(key: String, name: String, state: String, rank: Int)],
        probabilities: [String: Double] = [:],
        trend: Bool = false
    ) -> String {
        let boardRows = rows.map { row in
            let probability = probabilities[row.key].map { "\($0)" } ?? "null"
            let history = trend
                ? """
                , "trend": [{"date": "2026-09-11", "probability": 0.4},
                            {"date": "2026-09-12", "probability": 0.5}]
                """
                : ""
            return """
            {"entity_key": "\(row.key)", "display_name": "\(row.name)",
             "state": "\(row.state)", "rank": \(row.rank),
             "probability": \(probability)\(history)}
            """
        }.joined(separator: ", ")

        let decidedBlock = decided.map {
            """
            , "decided": {"winner_entity_key": "\($0)"}
            """
        } ?? ""

        return """
        {"slug": "us-open", "title": "US Open 2026",
         "slate": {"matches": []}, "results": {"matches": []},
         "boards": [{"draw": "\(draw)", "label": "\(label)",
                     "price_state": "dark", "rows": [\(boardRows)]\(decidedBlock)}],
         "bracket": {}, "event_links": {"by_espn": {}}, "broadcasts": []}
        """
    }
}
