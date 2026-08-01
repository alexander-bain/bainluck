import XCTest
@testable import Bain_Luck

/// L2-226 — the `…24h` / `…7d` decode class.
///
/// `.convertFromSnakeCase` capitalises each underscore-separated component after
/// the first, and `"24h".capitalized == "24H"` because a digit is not a cased
/// character — ICU title-cases the `h` as the word's first letter. So the
/// backend's `probability_change_24h` arrives as the key `probabilityChange24H`
/// and matched no property spelled `probabilityChange24h`. Every such field on
/// every native surface decoded as `nil` on every response, forever, silently.
///
/// L2-225 found and fixed one instance (`FeedTournamentGolfer.movement24h`).
/// This suite pins the whole class: one table-driven case per affected model
/// family, plus the strategy-level proof and the already-correct control.
final class NumericSuffixDecodeTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    // MARK: - The strategy itself (the root cause, pinned)

    /// If this ever starts failing, Foundation changed the conversion and every
    /// explicit `…24H` / `…7D` CodingKey raw value in the Models layer is now
    /// wrong. That is the signal to re-derive them, not to patch a call site.
    func testConvertFromSnakeCaseUppercasesTheLetterAfterADigit() throws {
        struct Probe: Decodable {
            let converted: [String]
            struct AnyKey: CodingKey {
                var stringValue: String
                var intValue: Int?
                init?(stringValue: String) { self.stringValue = stringValue }
                init?(intValue: Int) { nil }
            }
            init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: AnyKey.self)
                converted = c.allKeys.map(\.stringValue).sorted()
            }
        }
        let json = """
        {"trend_24h":1,"rank_change_24h":1,"probability_change_24h":1,
         "change_7d":1,"volume_24h":1,"delta_24h":1,"movement_24h":1,
         "opening_probability":1}
        """
        let probe = try decoder().decode(Probe.self, from: Data(json.utf8))
        XCTAssertEqual(probe.converted, [
            "change7D", "delta24H", "movement24H", "openingProbability",
            "probabilityChange24H", "rankChange24H", "trend24H", "volume24H",
        ], "the digit-suffix conversion is the whole reason this file exists")
    }

    // MARK: - Control: a model that was already spelled correctly

    /// `LeagueGridModels` has always used `trend24H`/`change24H`, which is why the
    /// grid's movement numbers worked while every other surface's did not. It is
    /// the control: if the class were something other than the suffix spelling,
    /// this would be broken too.
    func testLeagueGridControlStillDecodes() throws {
        let cell = try decoder().decode(GridCell.self, from: Data("""
        {"merged_probability": 0.42, "trend_24h": 0.031}
        """.utf8))
        XCTAssertEqual(cell.trend24H, 0.031)

        let mover = try decoder().decode(GridMover.self, from: Data("""
        {"name": "Dodgers", "column": "champion", "change_24h": -0.02, "direction": "down"}
        """.utf8))
        XCTAssertEqual(mover.change24H, -0.02)
    }

    // MARK: - Table-driven: every affected family

    /// The shared value table. Each family is exercised against all of it.
    private enum ValueCase: String, CaseIterable {
        case positive, zero, negative, null, missing, wrongType

        /// The JSON fragment for a `Double` field named `key` (or "" for missing).
        func fragment(_ key: String) -> String {
            switch self {
            case .positive: return "\"\(key)\": 0.031"
            case .zero: return "\"\(key)\": 0"
            case .negative: return "\"\(key)\": -0.042"
            case .null: return "\"\(key)\": null"
            case .missing: return ""
            case .wrongType: return "\"\(key)\": \"up a lot\""
            }
        }

        func intFragment(_ key: String) -> String {
            switch self {
            case .positive: return "\"\(key)\": 3"
            case .zero: return "\"\(key)\": 0"
            case .negative: return "\"\(key)\": -2"
            case .null: return "\"\(key)\": null"
            case .missing: return ""
            case .wrongType: return "\"\(key)\": \"three\""
            }
        }

        var expectedDouble: Double? {
            switch self {
            case .positive: return 0.031
            case .zero: return 0
            case .negative: return -0.042
            case .null, .missing, .wrongType: return nil
            }
        }

        var expectedInt: Int? {
            switch self {
            case .positive: return 3
            case .zero: return 0
            case .negative: return -2
            case .null, .missing, .wrongType: return nil
            }
        }
    }

    /// Decode `T` once per value case and assert the extracted field matches.
    /// `body` builds the JSON object around the injected fragment.
    private func assertDoubleField<T: Decodable>(
        _ type: T.Type,
        key: String,
        json: (String) -> String,
        extract: (T) -> Double?,
        label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        for value in ValueCase.allCases {
            let payload = json(value.fragment(key))
            do {
                let decoded = try decoder().decode(T.self, from: Data(payload.utf8))
                XCTAssertEqual(
                    extract(decoded), value.expectedDouble,
                    "\(label) [\(value.rawValue)]", file: file, line: line)
            } catch {
                XCTFail("\(label) [\(value.rawValue)] threw \(error) — a malformed "
                        + "or absent \(key) must degrade to nil, never fail the item",
                        file: file, line: line)
            }
        }
    }

    private func assertIntField<T: Decodable>(
        _ type: T.Type,
        key: String,
        json: (String) -> String,
        extract: (T) -> Int?,
        label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        for value in ValueCase.allCases {
            let payload = json(value.intFragment(key))
            do {
                let decoded = try decoder().decode(T.self, from: Data(payload.utf8))
                XCTAssertEqual(
                    extract(decoded), value.expectedInt,
                    "\(label) [\(value.rawValue)]", file: file, line: line)
            } catch {
                XCTFail("\(label) [\(value.rawValue)] threw \(error)",
                        file: file, line: line)
            }
        }
    }

    // MARK: FuturesModels

    func testProgressionStageTrend24h() {
        assertDoubleField(
            ProgressionStageData.self, key: "trend_24h",
            json: { #"{"key": "champion", "label": "Title", "probability": 0.2\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.trend24h, label: "ProgressionStageData.trend24h")
    }

    func testFuturesOutcomeProbabilityAndRankChange() {
        assertDoubleField(
            FuturesOutcome.self, key: "probability_change_24h",
            json: { #"{"id": 1, "name": "Dodgers", "probability": 0.2\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.probabilityChange24h, label: "FuturesOutcome.probabilityChange24h")
        assertIntField(
            FuturesOutcome.self, key: "rank_change_24h",
            json: { #"{"id": 1, "name": "Dodgers", "probability": 0.2\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.rankChange24h, label: "FuturesOutcome.rankChange24h")
    }

    func testSeriesMarketOutcomeProbabilityChange() {
        assertDoubleField(
            SeriesMarketOutcome.self, key: "probability_change_24h",
            json: { #"{"outcome_id": 9, "name": "Yes", "probability": 0.5\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.probabilityChange24h, label: "SeriesMarketOutcome.probabilityChange24h")
    }

    func testRelatedFutureProbabilityChange() {
        assertDoubleField(
            RelatedFuture.self, key: "probability_change_24h",
            json: {
                #"""
                {"market_id": 1, "market_name": "AL Pennant", "outcome_id": 2,
                 "outcome_name": "Yankees", "probability": 0.18\#($0.isEmpty ? "" : ", " + $0)}
                """#
            },
            extract: \.probabilityChange24h, label: "RelatedFuture.probabilityChange24h")
    }

    func testTeamFutureItemProbabilityChange() {
        assertDoubleField(
            TeamFutureItem.self, key: "probability_change_24h",
            json: {
                #"""
                {"outcome_id": 2, "outcome_name": "Yankees", "market_id": 1,
                 "market_name": "AL Pennant", "probability": 0.18\#($0.isEmpty ? "" : ", " + $0)}
                """#
            },
            extract: \.probabilityChange24h, label: "TeamFutureItem.probabilityChange24h")
    }

    func testTimelineOutcomeMetaProbabilityChange() {
        assertDoubleField(
            TimelineOutcomeMeta.self, key: "probability_change_24h",
            json: { #"{"id": 4, "name": "Scheffler", "current_probability": 0.6\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.probabilityChange24h, label: "TimelineOutcomeMeta.probabilityChange24h")
    }

    // MARK: SearchModels

    func testFuturesMoverProbabilityAndRankChange() {
        let base = #"{"outcome_id": 7, "name": "Chiefs", "market_id": 3, "current_probability": 0.22"#
        assertDoubleField(
            FuturesMover.self, key: "probability_change_24h",
            json: { base + ($0.isEmpty ? "" : ", " + $0) + "}" },
            extract: \.probabilityChange24h, label: "FuturesMover.probabilityChange24h")
        assertIntField(
            FuturesMover.self, key: "rank_change_24h",
            json: { base + ($0.isEmpty ? "" : ", " + $0) + "}" },
            extract: \.rankChange24h, label: "FuturesMover.rankChange24h")
    }

    // MARK: CategoryModels

    func testPoliticsCandidateChange7d() {
        assertDoubleField(
            PoliticsCandidate.self, key: "change_7d",
            json: { #"{"name": "A. Candidate", "party": "D", "merged": 0.55\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.change7d, label: "PoliticsCandidate.change7d")
    }

    func testEntMarketRowVolume24h() {
        assertIntField(
            EntMarketRow.self, key: "volume_24h",
            json: {
                #"""
                {"q": "Will X win?", "prob": 0.3, "src": "kalshi", "market_id": 8,
                 "top_outcomes": [], "outcome_count": 0\#($0.isEmpty ? "" : ", " + $0)}
                """#
            },
            extract: \.volume24h, label: "EntMarketRow.volume24h")
    }

    func testEntOutcomeDelta24h() {
        assertDoubleField(
            EntOutcome.self, key: "delta_24h",
            json: { #"{"name": "Nominee", "prob": 0.4\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.delta24h, label: "EntOutcome.delta24h")
    }

    // MARK: DiscoverLabelingModels

    func testDiscoverLabelingOutcomeProbabilityChange() {
        assertDoubleField(
            DiscoverLabelingOutcome.self, key: "probability_change_24h",
            json: { #"{"name": "Yes", "probability": 0.4\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.probabilityChange24h, label: "DiscoverLabelingOutcome.probabilityChange24h")
    }

    // MARK: GolfModels

    func testGolfGolferMovement24h() {
        assertDoubleField(
            GolfGolferData.self, key: "movement_24h",
            json: { #"{"name": "Rory McIlroy", "probability": 0.14, "rank": 2\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.movement24h, label: "GolfGolferData.movement24h")
    }

    func testGolfMoverMovement24h() {
        assertDoubleField(
            GolfMoverData.self, key: "movement_24h",
            json: { #"{"name": "Rory McIlroy", "probability": 0.14\#($0.isEmpty ? "" : ", " + $0)}"# },
            extract: \.movement24h, label: "GolfMoverData.movement24h")
    }

    // MARK: - Poison-sibling containment

    /// One item's malformed `…24h` value must not erase the healthy items around
    /// it. This is the failure that matters in production: a single bad number in
    /// a 50-outcome market would otherwise blank the entire list.
    func testOneMalformedMovementDoesNotEraseHealthySiblings() throws {
        let json = """
        [
          {"id": 1, "name": "Good First",  "probability": 0.5, "probability_change_24h": 0.02},
          {"id": 2, "name": "Poison Mid",  "probability": 0.3, "probability_change_24h": {"nested": true}},
          {"id": 3, "name": "Good Last",   "probability": 0.2, "probability_change_24h": -0.01}
        ]
        """
        let outcomes = try decoder().decode([FuturesOutcome].self, from: Data(json.utf8))
        XCTAssertEqual(outcomes.count, 3, "no item may be dropped")
        XCTAssertEqual(outcomes[0].probabilityChange24h, 0.02)
        XCTAssertNil(outcomes[1].probabilityChange24h, "the poison value degrades to nil")
        XCTAssertEqual(outcomes[1].name, "Poison Mid", "the rest of the poisoned item survives")
        XCTAssertEqual(outcomes[2].probabilityChange24h, -0.01, "the sibling after the poison survives")
    }

    /// Same containment for the first and last positions, where an index-sensitive
    /// bug would hide.
    func testPoisonAtFirstAndLastPositions() throws {
        for poisoned in [0, 2] {
            let values = (0..<3).map { $0 == poisoned ? "\"bad\"" : "0.05" }
            let json = "[" + (0..<3).map {
                #"{"name": "g\#($0)", "probability": 0.1, "movement_24h": \#(values[$0])}"#
            }.joined(separator: ",") + "]"
            let golfers = try decoder().decode([GolfGolferData].self, from: Data(json.utf8))
            XCTAssertEqual(golfers.count, 3, "poison at index \(poisoned) dropped items")
            for i in 0..<3 {
                XCTAssertEqual(
                    golfers[i].movement24h, i == poisoned ? nil : 0.05,
                    "index \(i) with poison at \(poisoned)")
            }
        }
    }

    // MARK: - Round-trip identity (the one type with an encode path)

    /// `DiscoverLabelingOutcome` rides inside `DiscoverLabelingCardSnapshot` to
    /// `POST /api/admin/judgments`. `.convertToSnakeCase` is NOT the inverse of
    /// `.convertFromSnakeCase` for these keys, so the assertion that matters is
    /// not "the encoded key equals the backend's key" (the backend stores
    /// `top_outcomes` opaquely and reads no inner key) — it is that a value
    /// survives encode → decode unchanged.
    func testLabelingOutcomeRoundTripsThroughTheClientEncoder() throws {
        let original = DiscoverLabelingOutcome(
            name: "Yes", probability: 0.62, currentProbability: 0.62,
            probabilityChange24h: 0.037)

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let bytes = try encoder.encode(original)

        let back = try decoder().decode(DiscoverLabelingOutcome.self, from: bytes)
        XCTAssertEqual(back.probabilityChange24h, 0.037)
        XCTAssertEqual(back.name, "Yes")
        XCTAssertEqual(back.currentProbability, 0.62)
    }

    func testLabelingOutcomeRoundTripsNilWithoutInventingAValue() throws {
        let original = DiscoverLabelingOutcome(
            name: "No", probability: 0.38, currentProbability: nil,
            probabilityChange24h: nil)
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let back = try decoder().decode(
            DiscoverLabelingOutcome.self, from: try encoder.encode(original))
        XCTAssertNil(back.probabilityChange24h)
        XCTAssertNil(back.currentProbability)
    }
}
