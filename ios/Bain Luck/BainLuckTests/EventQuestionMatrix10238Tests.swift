import XCTest
@testable import Bain_Luck

/// #10238 — the Game / Series question matrix consumer: decode, column kinds,
/// published value rules, selection identity and the #9524 price fences.
///
/// FIXTURES ARE ROUTE-HARNESS BODIES FROM THE MERGED PRODUCER (#10329).
/// `tools/gen-10238-route-harness.py` drives `_build_game_markets` →
/// `_publish_game_markets` and `_build_related_futures` →
/// `_publish_related_futures` on master 5509d7a579 with the producer test's own
/// mock sessions and writes the served JSON. Shapes the route never serves on
/// that page (a malformed or unknown-kind question, a binary with an
/// identified missing leg, an unblended cross-venue pair) are edits applied to
/// the served body in the test, in the producer's own spelling.
@MainActor
final class EventQuestionMatrix10238Tests: XCTestCase {
    private static func fixture(_ name: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures").appendingPathComponent(name)
    }
    private static let gameURL = fixture("game-markets-10238-question-matrix.route-harness.json")
    private static let seriesURL = fixture("related-futures-10238-series-matrix.route-harness.json")

    private let points211 = "q:count|points|game|full_game|ge:211"
    private let homeSpread = "q:handicap|points|home|full_game|-3.5"
    private let awaySpread = "q:handicap|points|away|full_game|+3.5"
    private let t2 = "2030-01-01T00:00:00.000002Z"

    private func object(_ url: URL) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func game(_ dict: [String: Any]? = nil) throws -> GameMarketsResponse {
        try decode(GameMarketsResponse.self, dict ?? object(Self.gameURL))
    }

    private func matrix(_ dict: [String: Any]? = nil) throws -> EventQuestionMatrix {
        try XCTUnwrap(try game(dict).gameQuestionMatrix)
    }

    private func question(_ matrix: EventQuestionMatrix, _ key: String) throws -> QuestionMatrixQuestion {
        try XCTUnwrap(matrix.question(key))
    }

    /// The specimen with one game question edited in place.
    private func editing(_ key: String, revision: String? = nil,
                         _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        var dict = try object(Self.gameURL)
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == key })
        edit(&questions[index])
        matrix["questions"] = questions
        dict["game_question_matrix"] = matrix
        if let revision {
            var clocks = try XCTUnwrap(dict["outcome_revision_at"] as? [String: Any])
            for id in clocks.keys { clocks[id] = revision }
            dict["outcome_revision_at"] = clocks
        }
        return dict
    }

    /// The same option served twice with different values — a conflict.
    private func duplicatingFirstOption(of key: String, in dict: [String: Any],
                                        value: Double) throws -> [String: Any] {
        var dict = dict
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == key })
        var options = try XCTUnwrap(questions[index]["options"] as? [[String: Any]])
        var twin = options[0]
        var published = try XCTUnwrap(twin["published"] as? [String: Any])
        published["value"] = value
        twin["published"] = published
        options.append(twin)
        questions[index]["options"] = options
        matrix["questions"] = questions
        dict["game_question_matrix"] = matrix
        return dict
    }

    /// The served body with its matrix edited in place.
    private func editingMatrix(_ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        var dict = try object(Self.gameURL)
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        edit(&matrix)
        dict["game_question_matrix"] = matrix
        return dict
    }

    /// The served binary `m:106` with its `No` leg loaded but not returned —
    /// `_missing_options`' spelling, never a price.
    private func binaryWithAMissingLeg() throws -> [String: Any] {
        try editing("m:106") { question in
            question["missing_options"] = [["option_key": "o:9", "outcome_id": 9, "label": "No",
                                            "side": NSNull(), "value_state": "unpriced"]]
            question["option_counts"] = ["declared": NSNull(), "loaded": 2, "returned": 1, "missing_identified": 1]
            question["complete"] = false
        }
    }

    /// The served count question re-served as `_unblended_option` would: two
    /// venues' rows typed to one proposition the route did not blend.
    private func countAsUnblendedPair() throws -> [String: Any] {
        try editing(points211) { question in
            var options = question["options"] as? [[String: Any]] ?? []
            options[0]["option_key"] = "o:2+20"
            options[0]["contributor_outcome_ids"] = [2, 20]
            options[0]["published"] = ["value": NSNull(), "value_state": "unblended_equivalents",
                                       "basis": "unknown", "source": NSNull(), "observed_at": NSNull()]
            var evidence = options[0]["source_evidence"] as? [[String: Any]] ?? []
            evidence.append(["source": "polymarket", "market_id": 111, "outcome_id": 20, "leg_side": "over",
                             "raw_probability": 0.55, "observed_at": NSNull()])
            options[0]["source_evidence"] = evidence
            options[0]["comparison"] = ["state": "unavailable", "reason": "not_quoted", "baseline": NSNull(),
                                        "latest": NSNull(), "delta_points": NSNull()]
            question["options"] = options
        }
    }

    /// Every key under a matrix object, skipping the coverage tallies whose
    /// keys are kind and reason NAMES, not fields (`by_kind`, `untyped`).
    private func keys(_ value: Any, skipping tallies: Set<String> = ["by_kind", "untyped"]) -> Set<String> {
        if let dict = value as? [String: Any] {
            var found = Set(dict.keys)
            for (key, child) in dict where !tallies.contains(key) { found.formUnion(keys(child)) }
            return found
        }
        if let array = value as? [Any] { return array.reduce(into: Set<String>()) { $0.formUnion(keys($1)) } }
        return []
    }

    private func setFirstOption(_ question: inout [String: Any], value: Double) {
        var options = question["options"] as? [[String: Any]] ?? []
        var published = options[0]["published"] as? [String: Any] ?? [:]
        published["value"] = value
        options[0]["published"] = published
        var evidence = options[0]["source_evidence"] as? [[String: Any]] ?? []
        if !evidence.isEmpty { evidence[0]["raw_probability"] = value }
        options[0]["source_evidence"] = evidence
        question["options"] = options
    }

    // MARK: - Decode

    func testEveryServedQuestionDecodesAndAMalformedOneIsSkippedAlone() throws {
        let m = try matrix()
        XCTAssertEqual(m.contract, "10238.v1")
        XCTAssertEqual(m.displayScope, "game")
        XCTAssertEqual(m.questions.count, 8)
        XCTAssertEqual(m.droppedQuestions, 0, "the producer's own body decodes whole")
        XCTAssertEqual(m.coverage?.scope, "rows_served_by_this_response")
        XCTAssertEqual(m.coverage?.questions, 8)
        XCTAssertEqual(m.coverage?.options, 13)
        XCTAssertEqual(m.questions.first?.questionKey, points211, "server order is kept")

        let count = try question(m, points211)
        XCTAssertEqual(count.label, "211+ points")
        XCTAssertEqual(count.quantity?.plural, "points")
        XCTAssertEqual(count.period?.key, "full_game")
        XCTAssertEqual(count.subject?.side, "game")
        XCTAssertEqual(count.predicate?.relation, "ge")
        XCTAssertEqual(count.predicate?.bound, 211)
        XCTAssertEqual(count.predicate?.line, 210.5)
        let option = try XCTUnwrap(count.option("o:2"))
        XCTAssertEqual(option.contributorOutcomeIds, [2])
        XCTAssertEqual(option.published.quotedValue, 0.52, "the over axis, as the route serves the totals row")
        XCTAssertEqual(option.sourceEvidence?.first?.legSide, "under")
        XCTAssertEqual(option.sourceEvidence?.first?.rawProbability, 0.48, "the contributor's own leg, unflipped")

        let home = try question(m, homeSpread)
        XCTAssertEqual(home.complementQuestionKey, awaySpread, "the complement is the server's, never derived")
        XCTAssertEqual(try question(m, awaySpread).complementQuestionKey, homeSpread)
        XCTAssertEqual(home.label, "Boston Celtics -3.5 points")
        XCTAssertEqual(home.subject?.label, "Boston Celtics")
        XCTAssertEqual(home.predicate?.line, -3.5)

        let malformed = try editingMatrix { matrix in
            var questions = matrix["questions"] as? [[String: Any]] ?? []
            questions.append(["question_key": "m:999", "kind": "named_options", "label": "No options"])
            matrix["questions"] = questions
        }
        let skipped = try self.matrix(malformed)
        XCTAssertEqual(skipped.questions.count, 8, "every sibling survives")
        XCTAssertEqual(skipped.droppedQuestions, 1)
        XCTAssertNil(skipped.question("m:999"))
    }

    /// The producer's spelling is the contract: every key it serves under
    /// either matrix is one this decode reads or names here as ignored. A key
    /// renamed upstream fails this before it silently decodes to nil.
    func testEveryServedMatrixKeyIsOneTheDecodeReads() throws {
        let read: Set<String> = [
            "contract", "display_scope", "questions", "series_markets_count", "coverage",
            "question_key", "proposition_key", "kind", "label", "market_name", "source_array", "quantity",
            "period", "subject", "predicate", "complement_question_key", "typing", "lifecycle", "options",
            "missing_options", "option_counts", "complete", "source_totals",
            "key", "singular", "plural", "integer", "side", "relation", "bound", "line", "state", "reason",
            "market_status", "option_key", "market_ids", "contributor_outcome_ids", "published",
            "source_evidence", "result", "comparison", "value", "value_state", "basis", "source",
            "observed_at", "market_id", "outcome_id", "leg_side", "raw_probability", "evidence_kind",
            "baseline", "latest", "delta_points", "probability", "declared", "loaded", "returned",
            "missing_identified", "raw_sum", "legs", "eligible", "scope", "build_errors",
        ]
        let ignored: Set<String> = ["by_kind", "untyped"]
        let game = try XCTUnwrap(try object(Self.gameURL)["game_question_matrix"])
        let series = try XCTUnwrap(try object(Self.seriesURL)["series_question_matrix"])
        XCTAssertEqual(keys(game).union(keys(series)).subtracting(read).subtracting(ignored), [])

        let reasons: Set<String> = ["untyped_period", "untyped_unit", "untyped_subject", "untyped_predicate"]
        for body in [game, series] {
            let coverage = try XCTUnwrap((body as? [String: Any])?["coverage"] as? [String: Any])
            XCTAssertEqual(Set(try XCTUnwrap(coverage["untyped"] as? [String: Any]).keys), reasons,
                           "the served reason set is the documented one")
        }
        let served = try matrix().questions.compactMap(\.typing?.reason)
        XCTAssertEqual(served, ["untyped_predicate"])
        XCTAssertTrue(Set(served).isSubset(of: reasons))
    }

    func testAnAbsentNullOrUnreadableMatrixDecodesNilAndNeverTakesTheLegacyArraysDown() throws {
        var dict = try object(Self.gameURL)
        dict.removeValue(forKey: "game_question_matrix")
        XCTAssertNil(try game(dict).gameQuestionMatrix, "older servers omit the key")
        dict["game_question_matrix"] = NSNull()
        XCTAssertNil(try game(dict).gameQuestionMatrix)

        let brokenValues: [Any] = ["10238.v1", 7, ["questions": "not an array"]]
        for broken in brokenValues {
            dict["game_question_matrix"] = broken
            let body = try game(dict)
            XCTAssertEqual(body.totals?.first?.overProbability, 0.52, "legacy totals survive \(broken)")
            XCTAssertEqual(body.spreads?.count, 3)
            if let matrix = body.gameQuestionMatrix {
                XCTAssertTrue(matrix.questions.isEmpty, "a readable shell with unreadable questions holds none")
            }
        }
    }

    // MARK: - Kinds

    func testOnlyATypedKindEntersASpecialisedColumn() throws {
        let m = try matrix()
        XCTAssertEqual(try question(m, points211).columnKind, .countThreshold)
        XCTAssertEqual(try question(m, homeSpread).columnKind, .signedHandicap)
        XCTAssertEqual(try question(m, "m:109").columnKind, .namedOptions)

        let untyped = try question(m, "m:110")
        XCTAssertEqual(untyped.kind, "named_options", "an integer handicap line is refused, not typed")
        XCTAssertEqual(untyped.typing?.reason, "untyped_predicate")
        XCTAssertEqual(untyped.label, "Celtics at Knicks: Spread 3", "the served market name verbatim")
        XCTAssertEqual(untyped.columnKind, .namedOptions)

        let typedButUntyped = try editing("m:110") { $0["kind"] = "signed_handicap" }
        XCTAssertEqual(try question(try matrix(typedButUntyped), "m:110").columnKind, .namedOptions,
                       "a typed kind the server also marked untyped fails closed")
        let unknown = try editing("m:106") { $0["kind"] = "some_future_kind" }
        XCTAssertEqual(try question(try matrix(unknown), "m:106").columnKind, .namedOptions,
                       "a kind this build does not know keeps its served labels")
    }

    // MARK: - Published value

    func testAFiniteZeroIsAQuoteAndEveryNonQuotedStateShowsNoNumber() throws {
        let m = try matrix()
        let threeWay = try question(m, "m:108")
        XCTAssertEqual(threeWay.option("o:14")?.published.quotedValue, 0.0, "finite 0 is real (F1)")
        XCTAssertEqual(threeWay.options.map(\.side), ["home", "draw", "away"])
        XCTAssertEqual(threeWay.complete, true)

        let equivalents = try XCTUnwrap(try question(try matrix(try countAsUnblendedPair()), points211).options.first)
        XCTAssertEqual(equivalents.published.valueState, "unblended_equivalents")
        XCTAssertNil(equivalents.published.quotedValue)
        XCTAssertEqual(equivalents.sourceEvidence?.compactMap(\.rawProbability), [0.48, 0.55],
                       "every row's raw stays visible; the phone never blends")

        let edited = try editing(points211) { question in
            var options = question["options"] as? [[String: Any]] ?? []
            options[0]["published"] = ["value": 1.4, "value_state": "quoted", "basis": "published_source_display"]
            question["options"] = options
        }
        XCTAssertNil(try question(try matrix(edited), points211).options[0].published.quotedValue,
                     "an out-of-range value is no chance")

        for state in ["refused", "unpriced", "result", "unblended_equivalents", "some_future_state"] {
            let notQuoted = try editing(points211) { question in
                var options = question["options"] as? [[String: Any]] ?? []
                options[0]["published"] = ["value": 0.6, "value_state": state, "basis": "unknown"]
                question["options"] = options
            }
            XCTAssertNil(try question(try matrix(notQuoted), points211).options[0].published.quotedValue,
                         "the state decides, not the presence of a number: \(state)")
        }
    }

    func testDisplayValueAndRawEvidenceAreBothKeptAndTheServerOwnsTheSum() throws {
        let field = try question(try matrix(), "m:109")
        XCTAssertEqual(field.options.compactMap(\.published.quotedValue), [0.5392, 0.2451, 0.2157])
        XCTAssertEqual(field.options.compactMap { $0.sourceEvidence?.first?.rawProbability }, [0.55, 0.25, 0.22])
        XCTAssertEqual(field.sourceTotals?.first?.rawSum, 1.02)
        XCTAssertEqual(field.sourceTotals?.first?.legs, 3)
    }

    func testMissingLegsCarryIdentityButNoPrice() throws {
        let binary = try question(try matrix(try binaryWithAMissingLeg()), "m:106")
        XCTAssertEqual(binary.options.map(\.optionKey), ["o:8"])
        XCTAssertEqual(binary.missingOptions?.map(\.optionKey), ["o:9"])
        XCTAssertEqual(binary.missingOptions?.first?.valueState, "unpriced")
        XCTAssertEqual(binary.complete, false)
        XCTAssertEqual(binary.optionCounts?.loaded, 2)
        XCTAssertEqual(try question(try matrix(), "m:106").missingOptions, [], "as served: nothing held back")
    }

    func testATypedQuestionOffersMoreOptionsOnlyForAnIdentifiedMissingLeg() throws {
        let m = try matrix()
        for key in [homeSpread, awaySpread] {
            let spread = try question(m, key)
            XCTAssertEqual(spread.complete, false, "the market's other leg is its own question")
            XCTAssertEqual(spread.optionCounts?.missingIdentified, 0)
            XCTAssertFalse(spread.offersMoreOptions, "A4 rider, on the producer's own body: \(key)")
        }
        XCTAssertTrue(try question(try matrix(try binaryWithAMissingLeg()), "m:106").offersMoreOptions,
                      "named options, one leg identified missing")
        XCTAssertFalse(try question(m, "m:108").offersMoreOptions, "complete")
        XCTAssertFalse(try question(m, points211).offersMoreOptions, "complete unknown")

        let typedButUntyped = try editing("m:110") { $0["kind"] = "signed_handicap" }
        for (key, body) in [(points211, try object(Self.gameURL)), ("m:110", typedButUntyped)] {
            var dict = body
            var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
            var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
            let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == key })
            questions[index]["complete"] = false
            questions[index]["option_counts"] = ["loaded": 1, "returned": 1, "missing_identified": 0]
            matrix["questions"] = questions
            dict["game_question_matrix"] = matrix
            XCTAssertFalse(try question(try self.matrix(dict), key).offersMoreOptions,
                           "A4 rider: complete:false with 0 identified is no disclosure on a typed kind: \(key)")
        }

        let identified = try editing(points211) { question in
            question["complete"] = false
            question["option_counts"] = ["loaded": 2, "returned": 1, "missing_identified": 1]
            question["missing_options"] = [["option_key": "o:99001", "outcome_id": 99001,
                                            "label": "Over 210.5", "side": "over", "value_state": "unpriced"]]
        }
        XCTAssertTrue(try question(try matrix(identified), points211).offersMoreOptions)
    }

    /// #10465 — the retained specimen m:64118681 (Team Total, named options):
    /// `complete:false`, 14 loaded, 14 returned, 0 identified missing. Release
    /// 36 told the reader options were hidden; nothing was.
    private func teamTotalSpecimen(declared: Any = NSNull(), loaded: Any = 14, returned: Any = 14,
                                   missingIdentified: Any = 0, missing: [[String: Any]] = [],
                                   complete: Any = false) throws -> [String: Any] {
        try editing("m:109") { question in
            let template = (question["options"] as? [[String: Any]])?.first ?? [:]
            question["label"] = "Team Total"
            question["market_name"] = "Team Total"
            question["options"] = (1...14).map { i -> [String: Any] in
                var option = template
                option["option_key"] = "o:\(64_118_680 + i)"
                option["contributor_outcome_ids"] = [64_118_680 + i]
                option["label"] = "Over \(200 + i).5"
                return option
            }
            question["option_counts"] = ["declared": declared, "loaded": loaded,
                                         "returned": returned, "missing_identified": missingIdentified]
            question["missing_options"] = missing
            question["complete"] = complete
        }
    }

    func testIncompleteNamedOptionsOfferMoreOnlyWithMissingRowEvidence() throws {
        let specimen = try question(try matrix(try teamTotalSpecimen()), "m:109")
        XCTAssertEqual(specimen.columnKind, .namedOptions)
        XCTAssertEqual(specimen.options.count, 14)
        XCTAssertEqual(specimen.complete, false)
        XCTAssertEqual(specimen.optionCounts?.loaded, 14)
        XCTAssertEqual(specimen.optionCounts?.returned, 14)
        XCTAssertEqual(specimen.missingOptions, [])
        XCTAssertFalse(specimen.offersMoreOptions,
                       "complete:false with 14/14 and 0 missing is unknown completeness, not a hidden row")

        // Unknown is never fabricated into missing.
        for (why, body) in [
            ("declared matches", try teamTotalSpecimen(declared: 14)),
            ("every count unknown", try teamTotalSpecimen(loaded: NSNull(), returned: NSNull(), missingIdentified: NSNull())),
            ("loaded unknown", try teamTotalSpecimen(declared: 20, loaded: NSNull())),
            ("returned unknown", try teamTotalSpecimen(returned: NSNull())),
            ("counts absent", try editing("m:109") { $0["complete"] = false; $0.removeValue(forKey: "option_counts") }),
        ] {
            XCTAssertFalse(try question(try matrix(body), "m:109").offersMoreOptions, why)
        }

        // An actual missing row, by identity or by count.
        let leg: [String: Any] = ["option_key": "o:64118699", "outcome_id": 64_118_699,
                                  "label": "Over 215.5", "side": NSNull(), "value_state": "unpriced"]
        for (why, body) in [
            ("identified missing leg", try teamTotalSpecimen(loaded: 15, missingIdentified: 1, missing: [leg])),
            ("missing count only", try teamTotalSpecimen(missingIdentified: 1)),
            ("missing identity only", try teamTotalSpecimen(missing: [leg])),
            // A served truncation.
            ("declared > loaded", try teamTotalSpecimen(declared: 16)),
            ("loaded > returned", try teamTotalSpecimen(loaded: 15)),
        ] {
            XCTAssertTrue(try question(try matrix(body), "m:109").offersMoreOptions, why)
        }

        // Evidence never overrides the server's own completeness.
        XCTAssertFalse(try question(try matrix(try teamTotalSpecimen(loaded: 15, complete: true)), "m:109").offersMoreOptions,
                       "complete:true")
        XCTAssertFalse(try question(try matrix(try teamTotalSpecimen(declared: 16, complete: NSNull())), "m:109").offersMoreOptions,
                       "complete unknown")

        // A typed kind still reads truncation as no evidence (A4 rider).
        let typedTruncated = try editing(points211) { question in
            question["complete"] = false
            question["option_counts"] = ["declared": 3, "loaded": 2, "returned": 1, "missing_identified": 0]
        }
        XCTAssertFalse(try question(try matrix(typedTruncated), points211).offersMoreOptions)

        // The disclosure changes nothing else on the row the reader sees.
        let rows = EventQuestionMatrixAdapter.rows(in: try matrix(try teamTotalSpecimen()), scope: .game)
        let row = try XCTUnwrap(rows.first { $0.label == "Team Total" })
        XCTAssertFalse(row.offersMoreOptions)
        XCTAssertEqual(row.options.map(\.label), (1...14).map { "Over \(200 + $0).5" })
        XCTAssertEqual(row.options.count, specimen.options.count)
        XCTAssertEqual(row.missingOptions, [])
        let truncated = EventQuestionMatrixAdapter.rows(in: try matrix(try teamTotalSpecimen(loaded: 15)), scope: .game)
            .first { $0.label == "Team Total" }
        XCTAssertEqual(truncated?.offersMoreOptions, true)
        XCTAssertEqual(truncated?.options.map(\.label), row.options.map(\.label), "no option manufactured")
        XCTAssertEqual(truncated?.options.map(\.value), row.options.map(\.value))
    }

    // MARK: - Comparison (R5)

    func testADeltaIsShownOnlyBesideLatestWhenTheServerSaysComparable() throws {
        let m = try matrix()
        let comparison = try XCTUnwrap(try question(m, homeSpread).options[0].comparison)
        XCTAssertEqual(comparison.baseline?.basis, "pregame_pin")
        XCTAssertEqual(comparison.baseline?.probability, 0.4)
        let shown = try XCTUnwrap(comparison.shownDelta)
        XCTAssertEqual(shown.points, 14.0)
        XCTAssertEqual(shown.latest.probability, 0.54)
        XCTAssertEqual(QuestionMatrixComparison.caption, "since the saved pregame price")
        XCTAssertEqual(try question(m, points211).options[0].comparison?.reason, "leg_is_complement")
        XCTAssertNil(try question(m, points211).options[0].comparison?.shownDelta)
        XCTAssertNil(try question(m, awaySpread).options[0].comparison?.shownDelta, "no_pregame_pin")

        let noLatest = try editing(homeSpread) { question in
            var options = question["options"] as? [[String: Any]] ?? []
            var comparison = options[0]["comparison"] as? [String: Any] ?? [:]
            comparison["latest"] = NSNull()
            options[0]["comparison"] = comparison
            question["options"] = options
        }
        XCTAssertNil(try question(try matrix(noLatest), homeSpread).options[0].comparison?.shownDelta,
                     "a delta never sits beside the published value")
    }

    // MARK: - Series

    func testAFinishedGameLeavesTheOpenSeriesOpenAndAResultIsNotAQuote() throws {
        let body = try decode(RelatedFuturesResponse.self, object(Self.seriesURL))
        XCTAssertEqual(body.eventStatus, "completed")
        XCTAssertEqual(body.seriesMarkets?.count, 2, "legacy series cards decode unchanged")
        let series = try XCTUnwrap(body.seriesQuestionMatrix)
        XCTAssertEqual(series.displayScope, "series")
        XCTAssertEqual(series.droppedQuestions, 0)
        XCTAssertEqual(series.seriesMarketsCount?.returned, 2)

        let winner = try question(series, "m:900")
        XCTAssertEqual(winner.lifecycle?.state, "open")
        XCTAssertEqual(winner.options.map(\.side), ["home", "away"])
        XCTAssertEqual(winner.options.compactMap(\.published.quotedValue), [0.70, 0.29], "never 70/30")
        XCTAssertEqual(winner.sourceTotals?.first?.rawSum, 0.99)
        XCTAssertTrue(winner.options.allSatisfy { $0.comparison?.reason == "series_baseline_unsupported" })
        XCTAssertTrue(winner.options.allSatisfy { $0.published.observedAt == nil }, "U2: no Series clock")

        let exact = try question(series, "m:910")
        let lost = try XCTUnwrap(exact.option("o:911"))
        XCTAssertEqual(lost.result?.isWinner, false)
        XCTAssertEqual(lost.published.valueState, "result")
        XCTAssertNil(lost.published.quotedValue)
        XCTAssertNil(exact.option("o:912")?.result?.isWinner, "an open sibling stays open")
        XCTAssertEqual(exact.option("o:912")?.published.quotedValue, 0.35)
        let refused = try XCTUnwrap(exact.option("o:913"))
        XCTAssertEqual(refused.published.valueState, "refused")
        XCTAssertEqual(refused.sourceEvidence, [], "a refused leg leaks no raw value")
        XCTAssertEqual(exact.option("o:914")?.published.valueState, "unpriced")
        XCTAssertEqual(exact.sourceTotals, [], "no sum unless every option has a raw value")
        XCTAssertNil(exact.complete, "nothing held back, nothing proves the list whole")
        XCTAssertFalse(exact.offersMoreOptions)

        var dict = try object(Self.seriesURL)
        dict.removeValue(forKey: "series_question_matrix")
        XCTAssertNil(try decode(RelatedFuturesResponse.self, dict).seriesQuestionMatrix)
        dict["series_question_matrix"] = "garbage"
        XCTAssertNil(try decode(RelatedFuturesResponse.self, dict).seriesQuestionMatrix)
    }

    func testResultStatesMapToAGradeOnlyForWonAndLost() {
        func grade(_ state: String) -> Bool? { QuestionMatrixResult(state: state, evidenceKind: nil).isWinner }
        XCTAssertEqual(grade("won"), true)
        XCTAssertEqual(grade("lost"), false)
        XCTAssertNil(grade("void"), "reserved; decoders accept it as no grade")
        XCTAssertNil(grade("unknown"))
        XCTAssertNil(grade("open"))
    }

    // MARK: - Selection (§11, R6)

    func testASelectionResolvesByKeysAndBecomesUnavailableInsteadOfJumping() throws {
        let m = try matrix()
        let pick = QuestionMatrixSelection(scope: .game, questionKey: "m:108", optionKey: "o:14")
        guard case .available(let q, let option, .none) = pick.resolve(in: m) else { return XCTFail("available") }
        XCTAssertEqual(q.questionKey, "m:108")
        XCTAssertEqual(option.label, "Tie")

        let withSource = QuestionMatrixSelection(scope: .game, questionKey: homeSpread, optionKey: "o:3", outcomeId: 3)
        guard case .available(_, _, let evidence?) = withSource.resolve(in: m) else { return XCTFail("source") }
        XCTAssertEqual(evidence.source, "kalshi")
        XCTAssertEqual(evidence.marketId, 102)

        var gone = m
        gone.questions.removeAll { $0.questionKey == "m:108" }
        XCTAssertEqual(pick.resolve(in: gone), .unavailable(.questionGone), "never a sibling question")
        XCTAssertEqual(QuestionMatrixSelection(scope: .game, questionKey: "m:106", optionKey: "o:9")
            .resolve(in: try matrix(try binaryWithAMissingLeg())), .unavailable(.optionGone),
            "a missing leg is not selectable")
        XCTAssertEqual(QuestionMatrixSelection(scope: .game, questionKey: points211, optionKey: "o:2", outcomeId: 99)
            .resolve(in: m), .unavailable(.sourceGone), "never another source")
        XCTAssertEqual(pick.resolve(in: nil), .unavailable(.noMatrix))

        let series = try XCTUnwrap(try decode(RelatedFuturesResponse.self, object(Self.seriesURL)).seriesQuestionMatrix)
        XCTAssertEqual(QuestionMatrixSelection(scope: .game, questionKey: "m:900", optionKey: "o:901")
            .resolve(in: series), .unavailable(.wrongScope), "a Game pick is never read from the Series matrix")
    }

    func testTheTwoScopesNeverShareASectionKey() {
        XCTAssertEqual(QuestionMatrixScope.game.sectionKey("m:1"), "gameQuestions:m:1")
        XCTAssertEqual(QuestionMatrixScope.series.sectionKey("m:1"), "seriesQuestions:m:1")
        for prefix in ["props:", "duringProps:", "other:", "matchups:", "totals:"] {
            XCTAssertFalse(QuestionMatrixScope.game.sectionKey("x").hasPrefix(prefix))
            XCTAssertFalse(QuestionMatrixScope.series.sectionKey("x").hasPrefix(prefix))
        }
    }

    // MARK: - #9524 fences

    func testEveryReturnedOptionIsAFencedRowInItsOwnSection() throws {
        let rows = GameMarketsPriceReconciliation.rows(try game())
        let matrixRows = rows.filter { $0.key.hasPrefix("gameQuestions:") }
        XCTAssertEqual(matrixRows.count, 13)
        let count = try XCTUnwrap(matrixRows.first { $0.key == "gameQuestions:\(points211):o:2" })
        XCTAssertEqual(count.prices, [0.52, 0.48], "published value and the contributor's raw leg")
        XCTAssertEqual(count.contributors, ["2"])
        XCTAssertEqual(count.markets, [101])
        XCTAssertTrue(matrixRows.allSatisfy(\.priced), "every served game option is quoted")
        XCTAssertTrue(rows.contains { $0.key.hasPrefix("totals:") }, "the legacy row stays its own row")

        let pair = GameMarketsPriceReconciliation.rows(try game(try countAsUnblendedPair()))
        let refused = try XCTUnwrap(pair.first { $0.key == "gameQuestions:\(points211):o:2+20" })
        XCTAssertFalse(refused.priced, "an unblended pair publishes no price")
    }

    func testAMatrixPriceThatMovesWithoutItsClockIsHeldAndMovesWithIt() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let first = try game()
        let shown = GameMarketsPriceReconciliation.adopting(first, over: nil, fence: &fence)

        let stale = try game(try editing(points211) { setFirstOption(&$0, value: 0.65) })
        let held = GameMarketsPriceReconciliation.adopting(stale, over: shown, fence: &fence)
        XCTAssertEqual(held.gameQuestionMatrix?.question(points211)?.options[0].published.value, 0.52,
                       "a moved price with no newer clock is refused")

        let fresh = try game(try editing(points211, revision: t2) { setFirstOption(&$0, value: 0.65) })
        let next = GameMarketsPriceReconciliation.adopting(fresh, over: held, fence: &fence)
        XCTAssertEqual(next.gameQuestionMatrix?.question(points211)?.options[0].published.value, 0.65)
    }

    func testAConflictingQuestionIsHeldWholeAndItsSiblingsStillMove() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let shown = GameMarketsPriceReconciliation.adopting(try game(), over: nil, fence: &fence)

        var dict = try editing(homeSpread, revision: t2) { setFirstOption(&$0, value: 0.55) }
        dict = try duplicatingFirstOption(of: points211, in: dict, value: 0.9)
        let next = GameMarketsPriceReconciliation.adopting(try game(dict), over: shown, fence: &fence)
        let count = try XCTUnwrap(next.gameQuestionMatrix?.question(points211))
        XCTAssertEqual(count.options.map(\.published.value), [0.52], "the held verified question, never the conflict")
        XCTAssertEqual(next.gameQuestionMatrix?.question(homeSpread)?.options[0].published.value, 0.55,
                       "an unrelated question still advances")

        var cold = GameMarketsPriceReconciliation.Fence()
        let firstSight = GameMarketsPriceReconciliation.adopting(try game(dict), over: nil, fence: &cold)
        XCTAssertNil(firstSight.gameQuestionMatrix?.question(points211), "nothing verified to show: withheld")
        XCTAssertNotNil(firstSight.gameQuestionMatrix?.question(homeSpread))
    }
}
