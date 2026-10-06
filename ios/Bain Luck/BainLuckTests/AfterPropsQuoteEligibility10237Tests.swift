import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #10237 Build 37 repair — the After grid leads with saved pregame chances.
///
/// Alex's build-37 phone (SD 3 – MIL 4) showed a Hits grid of "— Reached"
/// rows: every player was drawn although none had a saved chance, and the
/// Turang detail printed "6% 6.0%". The admitted slice (sol
/// 10237-AFTER-SAFE-SCOPE-INDEPENDENT-ADMISSION + UX design B):
///   - a player earns the main grid with one usable saved chance on a question
///     of the SELECTED stat and period (a finite 0 counts; a final count or a
///     Reached / Below mark never earns it);
///   - every other player stays reachable behind one counted disclosure, even
///     when no player of the stat has a chance;
///   - main columns come from main rows only;
///   - a missing chance reads in words, and the exact value is printed only
///     when it says more than the headline, compared as numbers;
///   - Close finds the opened question in either place.
///
/// Same fixture as ``PropExpectationActual10237Tests`` (the producer's route
/// body): Judge 1+ has no pin, Rice 1+ is pinned 0.31 and Rice 2+ 0.03.
@MainActor
final class AfterPropsQuoteEligibility10237Tests: XCTestCase {
    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10237-after.route.json")

    private let rice1 = "s:ben rice|home_runs|full_game|ge:1|over"
    private let rice2 = "s:ben rice|home_runs|full_game|ge:2|over"
    private let judge1 = "s:aaron judge|home_runs|full_game|ge:1|over"
    private let judgeHR = "s:aaron judge|home_runs|full_game"

    private func specimen() throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    private func decode(_ dict: [String: Any]) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func props(_ dict: [String: Any]) throws -> AfterPlayerProps {
        try XCTUnwrap(try decode(dict).afterPlayerProps)
    }

    /// Edits the After body in place: `body` is `after_player_props`.
    private func editing(_ dict: [String: Any], _ edit: (inout [String: Any]) throws -> Void) throws -> [String: Any] {
        var dict = dict
        var after = try XCTUnwrap(dict["after_player_props"] as? [String: Any])
        try edit(&after)
        dict["after_player_props"] = after
        return dict
    }

    private func editingQuestions(_ dict: [String: Any], _ keys: [String],
                                  _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        try editing(dict) { after in
            var rows = try XCTUnwrap(after["questions"] as? [[String: Any]])
            for key in keys {
                let index = try XCTUnwrap(rows.firstIndex { $0["question_key"] as? String == key }, key)
                edit(&rows[index])
            }
            after["questions"] = rows
        }
    }

    private func expectation(_ dict: [String: Any], _ keys: [String],
                             _ edit: @escaping (inout [String: Any]) -> Void) throws -> [String: Any] {
        try editingQuestions(dict, keys) { q in
            var e = q["expectation"] as? [String: Any] ?? [:]
            edit(&e)
            q["expectation"] = e
        }
    }

    private func unpin(_ e: inout [String: Any]) {
        e["state"] = "unavailable"; e["probability"] = NSNull(); e["basis"] = NSNull(); e["contributors"] = []
    }

    private func grid(_ props: AfterPlayerProps, _ stat: String = "home_runs") throws -> AfterPropsMatrixLayout.Grid {
        try XCTUnwrap(AfterPropsMatrixLayout.grid(props, statKey: stat))
    }

    private func open(_ key: String, _ props: AfterPlayerProps) throws -> EventPropsMatrixSelection.OpenQuestion {
        .init(try XCTUnwrap(props.questions.first { $0.questionKey == key }))
    }

    // MARK: - Eligibility

    func testAPlayerWithoutASavedChanceIsDisclosedAndKeepsEveryQuestion() throws {
        let after = try props(try specimen())
        let g = try grid(after)
        XCTAssertEqual(g.players.map(\.label), ["Ben Rice"], "only a player with a saved chance is a main row")
        XCTAssertEqual(g.withoutChance.map(\.label), ["Aaron Judge"])
        XCTAssertEqual(g.withoutChance.first?.cells[1]?.questionKey, judge1, "Judge's question is still reachable")
        XCTAssertEqual(g.withoutChance.first?.actual?.actualKey, judgeHR, "the count stays once per player")
        XCTAssertEqual(g.questionCount, 3, "every question is counted, main and disclosed")
        XCTAssertEqual(g.columns, [1, 2])
    }

    func testMainColumnsComeFromMainRowsOnly() throws {
        // Judge's unquoted question moves to 3+: no quoted player has 3+.
        let moved = try editingQuestions(try specimen(), [judge1]) {
            $0["predicate"] = ["kind": "count_at_least", "count": 3, "side": "over", "label": "3+"]
        }
        let g = try grid(try props(moved))
        XCTAssertEqual(g.columns, [1, 2], "an unquoted-only threshold draws no empty main column")
        XCTAssertEqual(g.withoutChance.first?.cells[3]?.questionKey, judge1, "the disclosed option keeps its own 3+")
        // Control: once Judge's 3+ is quoted, Judge and the column join the grid.
        let quoted = try expectation(moved, [judge1]) {
            $0["state"] = "available"; $0["probability"] = 0.12; $0["basis"] = "single_source"
        }
        let control = try grid(try props(quoted))
        XCTAssertEqual(control.columns, [1, 2, 3])
        XCTAssertEqual(control.players.map(\.label), ["Aaron Judge", "Ben Rice"], "server order, never re-ranked")
        XCTAssertTrue(control.withoutChance.isEmpty)
    }

    func testAStatWithNoSavedChanceIsStillOneCountedDisclosure() throws {
        let none = try props(try expectation(try specimen(), [rice1, rice2], unpin))
        let g = try XCTUnwrap(AfterPropsMatrixLayout.grid(none, statKey: "home_runs"),
                              "an all-unquoted stat is never 'No questions'")
        XCTAssertTrue(g.players.isEmpty)
        XCTAssertTrue(g.columns.isEmpty)
        XCTAssertEqual(g.withoutChance.map(\.label), ["Aaron Judge", "Ben Rice"], "first-appearance order kept")
        XCTAssertEqual(g.withoutChance.reduce(0) { $0 + $1.cells.count }, 3, "all three questions reachable")
        XCTAssertEqual(AfterPropsMatrixLayout.disclosureLabel(count: g.withoutChance.count, expanded: false),
                       "Show 2 players without a pregame chance")
    }

    func testAZeroAndAStaleOrPartialSavedChanceStillEarnTheRow() throws {
        let zero = try props(try expectation(try expectation(try specimen(), [rice2], unpin), [rice1]) {
            $0["probability"] = 0.0
        })
        XCTAssertEqual(try grid(zero).players.map(\.label), ["Ben Rice"], "a finite 0 is a real saved chance")

        let partial = try props(try expectation(try expectation(try specimen(), [rice2], unpin), [rice1]) {
            $0["reason"] = "partial_coverage"
            var contributors = $0["contributors"] as? [[String: Any]] ?? []
            if !contributors.isEmpty { contributors[0]["admission"] = "stale" }
            $0["contributors"] = contributors
        })
        XCTAssertEqual(try grid(partial).players.map(\.label), ["Ben Rice"],
                       "the server admitted it: stale or partial coverage does not unseat it")
    }

    func testAnInvalidOrUnavailableChanceNeverEarnsTheRow() throws {
        let cases: [(String, (inout [String: Any]) -> Void)] = [
            ("above 1", { $0["probability"] = 1.5 }),
            ("below 0", { $0["probability"] = -0.1 }),
            ("null", { $0["probability"] = NSNull() }),
            ("unavailable with a number", { $0["state"] = "unavailable" }),
            ("unknown state", { $0["state"] = "pinned_maybe" }),
        ]
        for (name, edit) in cases {
            let after = try props(try expectation(try specimen(), [rice1, rice2], edit))
            let g = try grid(after)
            XCTAssertTrue(g.players.isEmpty, "\(name): no main row")
            XCTAssertEqual(g.withoutChance.map(\.label), ["Aaron Judge", "Ben Rice"], "\(name): still reachable")
        }
    }

    func testAFinalCountOrAMarkAloneNeverEarnsTheRow() throws {
        // Judge is now final at 1 and the server says Reached: still no chance.
        let dict = try editing(try specimen()) { after in
            var actuals = try XCTUnwrap(after["actuals"] as? [[String: Any]])
            let i = try XCTUnwrap(actuals.firstIndex { $0["actual_key"] as? String == judgeHR })
            actuals[i]["state"] = "final"; actuals[i]["value"] = 1; actuals[i]["reason"] = NSNull()
            actuals[i]["source_label"] = "ESPN final statistic"
            after["actuals"] = actuals
        }
        let reached = try editingQuestions(dict, [judge1]) { $0["comparison"] = ["state": "reached", "reason": NSNull()] }
        let after = try props(reached)
        let g = try grid(after)
        XCTAssertEqual(g.withoutChance.map(\.label), ["Aaron Judge"])
        let q = try XCTUnwrap(g.withoutChance.first?.cells[1])
        XCTAssertEqual(PropExpectationActualDisplay.mark(q, actual: after.actual(for: q)), .reached,
                       "control: the mark is real, it just is not a chance")
        XCTAssertNil(PropExpectationActualDisplay.expectation(q.expectation).valueText)
    }

    func testAnotherStatsOrPeriodsChanceNeverEarnsThisStatsRow() throws {
        // Rice's only chance is moved to Hits; Home Runs keeps only his unpinned 2+.
        let hits: [String: Any] = ["stat_key": "hits", "label": "Hits", "unit_singular": "hit", "unit_plural": "hits",
                                   "period_key": "full_game", "period_label": "Game", "predicate": "count_at_least"]
        var dict = try editing(try specimen()) { after in
            after["stats"] = (after["stats"] as? [[String: Any]] ?? []) + [hits]
        }
        dict = try expectation(dict, [rice2], unpin)
        let otherStat = try editingQuestions(dict, [rice1]) {
            $0["stat_key"] = "hits"; $0["question_key"] = "s:ben rice|hits|full_game|ge:1|over"
        }
        let a = try props(otherStat)
        XCTAssertTrue(try grid(a).players.isEmpty, "a Hits chance does not earn a Home Runs row")
        XCTAssertEqual(try grid(a, "hits").players.map(\.label), ["Ben Rice"], "control: it earns the Hits row")

        // Rice's only chance is for another period of Home Runs.
        let otherPeriod = try editingQuestions(dict, [rice1]) { $0["period_key"] = "first_5_innings" }
        let b = try grid(try props(otherPeriod))
        XCTAssertTrue(b.players.isEmpty, "a first-five chance does not earn the full-game row")
        XCTAssertEqual(b.withoutChance.map(\.label), ["Aaron Judge", "Ben Rice"])
    }

    func testTheFirstStatWithASavedChanceLeadsUntilTheReaderChooses() throws {
        let hits: [String: Any] = ["stat_key": "hits", "label": "Hits", "unit_singular": "hit", "unit_plural": "hits",
                                   "period_key": "full_game", "period_label": "Game", "predicate": "count_at_least"]
        let hitsQuestion: [String: Any] = [
            "question_key": "s:aaron judge|hits|full_game|ge:1|over", "actual_key": "s:aaron judge|hits|full_game",
            "subject": ["key": "aaron judge", "label": "Aaron Judge", "kind": "player"],
            "stat_key": "hits", "period_key": "full_game",
            "predicate": ["kind": "count_at_least", "count": 1, "side": "over", "label": "1+"],
            "expectation": ["state": "unavailable", "reason": "no_admitted_pin", "probability": NSNull(), "basis": NSNull(),
                            "observed_at": NSNull(), "contributors": [], "excluded": []],
            "comparison": ["state": "unknown", "reason": NSNull()],
        ]
        // Hits comes FIRST from the server and has no chance at all.
        let dict = try editing(try specimen()) { after in
            after["stats"] = [hits] + (after["stats"] as? [[String: Any]] ?? [])
            after["questions"] = [hitsQuestion] + (after["questions"] as? [[String: Any]] ?? [])
        }
        let after = try props(dict)
        XCTAssertEqual(after.stats.first?.statKey, "hits", "control: the server's first is Hits")
        XCTAssertEqual(AfterPropsMatrixLayout.defaultStat(after), "home_runs")
        // Control: with no chance anywhere, the server's first stays first.
        let bare = try props(try expectation(dict, [rice1, rice2], unpin))
        XCTAssertEqual(AfterPropsMatrixLayout.defaultStat(bare), "hits")
    }

    func testADisclosedQuestionStillLeavesTheLegacyCard() throws {
        let page = try decode(try specimen())
        let kept = AfterPropsMatrixLayout.untypedPlayerProps(page.playerProps ?? [], typed: page.afterPlayerProps)
        XCTAssertFalse(kept.contains { ($0.contributorOutcomeIds ?? []).contains(5013) },
                       "Judge's disclosed 1+ is typed: the old card never draws it a second time")
        XCTAssertEqual(kept.compactMap(\.contributorOutcomeIds), [[5022]])
    }

    // MARK: - Close

    func testCloseFindsTheOpenedQuestionInTheGridOrTheDisclosure() throws {
        let after = try props(try specimen())
        let g = try grid(after)
        XCTAssertEqual(AfterPropsMatrixLayout.placement(of: try open(rice1, after), in: g), .main)
        XCTAssertEqual(AfterPropsMatrixLayout.placement(of: try open(judge1, after), in: g), .withoutChance)
        let ghostKey = "s:nobody|home_runs|full_game|ge:1|over"
        let ghost = try props(try editingQuestions(try specimen(), [judge1]) {
            $0["question_key"] = ghostKey
            $0["subject"] = ["key": "nobody", "label": "Nobody", "kind": "player"]
        })
        let gone = try open(ghostKey, ghost)
        XCTAssertEqual(AfterPropsMatrixLayout.placement(of: gone, in: g), .absent, "a vanished question is honest")
        // A Rice question whose chance disappears on refresh is found in the disclosure.
        let refreshed = try props(try expectation(try specimen(), [rice1, rice2], unpin))
        XCTAssertEqual(AfterPropsMatrixLayout.placement(of: try open(rice1, after), in: try grid(refreshed)),
                       .withoutChance)
    }

    func testAReorderedPayloadKeepsTheSameQuestionAndPlacement() throws {
        let original = try props(try specimen())
        let reversed = try props(try editing(try specimen()) { after in
            after["questions"] = Array((after["questions"] as? [[String: Any]] ?? []).reversed())
        })
        for key in [judge1, rice1, rice2] {
            let o = try open(key, original)
            XCTAssertEqual(AfterPropsMatrixLayout.resolve(o, in: reversed)?.questionKey, key, "detail identity")
            XCTAssertEqual(AfterPropsMatrixLayout.placement(of: o, in: try grid(reversed)),
                           AfterPropsMatrixLayout.placement(of: o, in: try grid(original)), key)
        }
        XCTAssertEqual(try grid(reversed).withoutChance.count, 1, "the disclosure count is recomputed, not held")
    }

    // MARK: - Words

    func testTheDisclosureCountsPlayers() {
        XCTAssertEqual(AfterPropsMatrixLayout.disclosureLabel(count: 1, expanded: false),
                       "Show 1 player without a pregame chance")
        XCTAssertEqual(AfterPropsMatrixLayout.disclosureLabel(count: 18, expanded: false),
                       "Show 18 players without a pregame chance")
        XCTAssertEqual(AfterPropsMatrixLayout.disclosureLabel(count: 18, expanded: true),
                       "Hide 18 players without a pregame chance")
    }

    func testAMissingChanceSaysSoInWords() throws {
        let after = try props(try specimen())
        let q = try XCTUnwrap(after.questions.first { $0.questionKey == judge1 })
        let shown = PropExpectationActualDisplay.expectation(q.expectation)
        XCTAssertNil(shown.valueText)
        XCTAssertEqual(shown.label, "No pregame chance was saved for this question.")
        XCTAssertNil(shown.label.rangeOfCharacter(from: .decimalDigits), "never a number inferred from the result")
        XCTAssertTrue(PropExpectationActualDisplay.accessibilityLabel(q, actual: after.actual(for: q),
                                                                      stat: after.stat("home_runs"))
            .contains("saved pregame chance unavailable"))
        // Control: a saved chance keeps its label.
        let rice = try XCTUnwrap(after.questions.first { $0.questionKey == rice1 })
        XCTAssertEqual(PropExpectationActualDisplay.expectation(rice.expectation).label, "Saved pregame chance")
    }

    func testTheExactValueIsShownOnlyWhenItSaysMoreThanTheHeadline() {
        func exact(_ p: Double?, state: String = "available") -> String? {
            PropExpectationActualDisplay.exactDetailText(AfterPropExpectation(
                state: state, reason: nil, probability: p, basis: "single_source", observedAt: nil,
                contributors: [], excluded: []))
        }
        // The same number twice (Turang: "6%" and "6.0%").
        XCTAssertNil(exact(0.06))
        XCTAssertNil(exact(0.01), "1% and 1.0%")
        XCTAssertNil(exact(0.99), "99% and 99.0%")
        XCTAssertNil(exact(0.5))
        // More than the headline says.
        XCTAssertEqual(exact(0.004), "0.4%", "beside <1%")
        XCTAssertEqual(exact(0), "0.0%", "a real 0 beside <1%")
        XCTAssertEqual(exact(0.0099), "1.0%", "beside <1%: the headline is a bound")
        XCTAssertEqual(exact(0.055), "5.5%", "beside a rounded 6%")
        XCTAssertEqual(exact(0.995), "99.5%", "beside >99%")
        XCTAssertEqual(exact(1), "100.0%", "beside >99%")
        // Nothing to state.
        XCTAssertNil(exact(nil))
        XCTAssertNil(exact(0.3, state: "unavailable"))
        // The headline really is the integer this compares against.
        XCTAssertEqual(formatProbability(0.06), "6%")
        XCTAssertEqual(formatProbability(0.055), "6%")
    }

    // MARK: - Rendered

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func renderedLines(_ props: AfterPlayerProps, at size: DynamicTypeSize, _ name: String) throws -> [String] {
        // Inside a ScrollView, as on the page: a fixed frame would compress the
        // card at accessibility sizes and photograph an overlap no reader sees.
        let card = ScrollView { AfterPropsMatrixView(props: props).padding() }
        let host = hostForMeasurement(card.environment(\.colorScheme, .light), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let win = UIWindow(frame: host.view.frame)
        win.rootViewController = host; win.isHidden = false
        defer { win.isHidden = true }
        settle(host, 0.4)
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("after-props-10237-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("After props 10237 rendered evidence (route-harness data): \(url.path)")
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testTheCardLeadsWithChancesAndCountsTheRestAtPhoneAndAccessibilitySizes() throws {
        let after = try props(try specimen())
        for (name, size) in [("mixed-390", DynamicTypeSize.large), ("mixed-390-ax5", .accessibility5)] {
            let lines = try renderedLines(after, at: size, name)
            let text = lines.joined(separator: " ")
            XCTAssertTrue(text.contains("Rice"), "\(name): the quoted player is a row: \(lines)")
            XCTAssertTrue(text.contains("31%"), "\(name): his saved chance leads: \(lines)")
            XCTAssertFalse(text.contains("Judge"), "\(name): the unquoted player is behind the disclosure: \(lines)")
            XCTAssertTrue(text.contains("without a pregame") || text.contains("without a"),
                          "\(name): the disclosure is on the card: \(lines)")
        }
        let none = try props(try expectation(try specimen(), [rice1, rice2], unpin))
        let lines = try renderedLines(none, at: .large, "none-390")
        let text = lines.joined(separator: " ")
        XCTAssertTrue(text.contains("Show 2 players"), "an all-unquoted stat is one counted disclosure: \(lines)")
        XCTAssertFalse(text.contains("No questions"), "\(lines)")
        XCTAssertFalse(lines.contains { $0.trimmingCharacters(in: .whitespaces) == "1+" },
                       "no empty threshold column is drawn: \(lines)")
    }
}
