import XCTest
@testable import Bain_Luck

/// #9387 — the Native consumer of `?representation=verified_title`: decoding,
/// the labels a response earns, the chart's one-retry agreement policy, and the
/// reconciliation clock that must not refuse a newer verified answer.
///
/// Every fixture below is a REAL-ROUTE response: `get_futures_market` /
/// `get_probability_timeline` from server PR #10216 at exact
/// `358c040443753e9654b0bea3f5747154916de794`, run offline over that PR's own
/// retained trio fixtures (`tests/test_futures_verified_title_9387.py`: Odds
/// 86832, Kalshi 40533, Polymarket 129037, `NOW` 2026-10-02 16:20Z) and
/// serialized with FastAPI's `jsonable_encoder`. No production read, no provider
/// request. The ids are fixture ids only; nothing in the app selects by them.
@MainActor
final class VerifiedTitleConsumer9387Tests: XCTestCase {
    // MARK: - Helpers

    static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    static func detail(_ json: String) throws -> FuturesMarketDetail {
        try decoder().decode(FuturesMarketDetail.self, from: Data(json.utf8))
    }

    static func timeline(_ json: String) throws -> ProbabilityTimelineResponse {
        try decoder().decode(ProbabilityTimelineResponse.self, from: Data(json.utf8))
    }

    /// The fixture with one edit applied to its JSON object.
    static func edited(_ json: String, _ edit: (inout [String: Any]) -> Void) throws -> String {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        edit(&object)
        return String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
    }

    /// Edits the outcome named `name` inside `outcomes`.
    static func editOutcome(_ object: inout [String: Any], _ name: String,
                            _ edit: (inout [String: Any]) -> Void) {
        var outcomes = object["outcomes"] as? [[String: Any]] ?? []
        for index in outcomes.indices where outcomes[index]["name"] as? String == name {
            edit(&outcomes[index])
        }
        object["outcomes"] = outcomes
    }

    private typealias F = VerifiedTitle9387Fixtures
    private let buffalo = 1_309_486


    // MARK: - Decoding (gate 6)

    func testTheServersVerifiedDetailDecodesEveryNewFieldWithItsType() throws {
        let market = try Self.detail(F.detailVerified)
        XCTAssertEqual(market.representation, "verified_title")
        XCTAssertEqual(market.effectiveRepresentation, .verifiedTitle)
        XCTAssertEqual(market.questionIdentity?.competition, "NFL")
        XCTAssertEqual(market.questionIdentity?.edition, "2027", "edition is a STRING even when it is a year")
        XCTAssertEqual(market.questionIdentity?.question, "league_championship_winner")
        XCTAssertEqual(market.contributingSources, ["odds_api", "kalshi", "polymarket"])
        let bills = try XCTUnwrap(market.outcomes.first { $0.id == buffalo })
        XCTAssertEqual(bills.probability, 0.13)
        XCTAssertEqual(bills.contributingSources, ["odds_api", "kalshi", "polymarket"])
        XCTAssertEqual(bills.observedAt, "2026-10-02T07:54:47.255493+00:00")
        XCTAssertEqual(bills.aggregationRule, "weighted_median")
        // Provenance stays the requested row's.
        XCTAssertEqual(market.source, "odds_api")
        XCTAssertEqual(market.bookmakers?.count, 8)
    }

    func testAVerifiedRowCarriesNoOpeningOrMovementFromAnotherEstimator() throws {
        let market = try Self.detail(F.detailVerified)
        for outcome in market.outcomes {
            XCTAssertNil(outcome.openingProbability, outcome.name)
            XCTAssertNil(outcome.probabilityChange24h, outcome.name)
            XCTAssertNil(outcome.rankChange24h, outcome.name)
        }
        // Control: the default body of the same board DOES carry an opening —
        // so the nil above is the server's refusal, not a fixture that never had one.
        let source = try Self.detail(F.detailDefault)
        XCTAssertNotNil(source.outcomes.first { $0.id == buffalo }?.openingProbability)
    }

    func testIdsNamesAndOrderAreTheRequestedRowsInBothModes() throws {
        let verified = try Self.detail(F.detailVerified)
        let source = try Self.detail(F.detailDefault)
        XCTAssertEqual(verified.outcomes.map(\.id), source.outcomes.map(\.id))
        XCTAssertEqual(verified.outcomes.map(\.name), source.outcomes.map(\.name))
    }

    func testTheServersVerifiedTimelineDecodesItsHistoryBasisAndCurrentColumn() throws {
        let response = try Self.timeline(F.timelineVerified)
        XCTAssertEqual(response.effectiveRepresentation, .verifiedTitle)
        XCTAssertEqual(response.historyBasis?.kind, "single_source")
        XCTAssertEqual(response.historyBasis?.source, "odds_api")
        XCTAssertEqual(response.historyBasis?.marketId, 86832, "market_id is an Int")
        XCTAssertEqual(response.questionIdentity?.edition, "2027")
        let bills = try XCTUnwrap(response.outcomes.first { $0.id == buffalo })
        XCTAssertEqual(bills.currentProbability, 0.13)
        XCTAssertEqual(bills.contributingSources, ["odds_api", "kalshi", "polymarket"])
        XCTAssertEqual(bills.aggregationRule, "weighted_median")
        XCTAssertNil(bills.probabilityChange24h)
    }

    /// Gate 3: every metadata name is its history key, byte for byte, and the
    /// list keeps the source's own order — so `top`, the default three lines and
    /// the positional percents all point at the same rows in both modes.
    func testEveryChartNameIsItsHistoryKeyAndTheOrderIsTheSources() throws {
        let verified = try Self.timeline(F.timelineVerified)
        let source = try Self.timeline(F.timelineDefault)
        let keys = Set(verified.timeline.flatMap { $0.outcomes.keys })
        for meta in verified.outcomes {
            XCTAssertTrue(keys.contains(meta.name), "\(meta.name) has no history line")
        }
        XCTAssertEqual(verified.outcomes.map(\.name), source.outcomes.map(\.name))
        XCTAssertEqual(verified.outcomes.map(\.id), source.outcomes.map(\.id))
        XCTAssertEqual(Array(verified.outcomes.prefix(3).map(\.name)),
                       Array(source.outcomes.prefix(3).map(\.name)), "the default three lines")
        // History is the source's own, untouched by the opt-in.
        XCTAssertEqual(verified.timeline.map(\.timestamp), source.timeline.map(\.timestamp))
        XCTAssertEqual(verified.timeline.map(\.outcomes), source.timeline.map(\.outcomes))
        XCTAssertEqual(verified.coverageHours, source.coverageHours)
        XCTAssertEqual(verified.bucketSeconds, source.bucketSeconds)
    }

    func testDefaultAndPreFeatureBodiesStillDecodeAsSource() throws {
        let market = try Self.detail(F.detailDefault)
        XCTAssertNil(market.representation)
        XCTAssertEqual(market.effectiveRepresentation, .source)
        XCTAssertNil(market.contributingSources)
        XCTAssertNil(market.outcomes.first?.contributingSources)
        let response = try Self.timeline(F.timelineDefault)
        XCTAssertEqual(response.effectiveRepresentation, .source)
        XCTAssertNil(response.historyBasis)
        // A body from before #9387 existed at all.
        let old = try Self.detail(#"{"id":7,"name":"Old","outcomes":[{"id":1,"name":"X","probability":0.4}]}"#)
        XCTAssertEqual(old.effectiveRepresentation, .source)
        XCTAssertNil(old.outcomes[0].observedAt)
    }

    func testAnIneligibleBoardAnswersInSourceMode() throws {
        let market = try Self.detail(F.detailFallback)
        XCTAssertEqual(market.effectiveRepresentation, .source)
        XCTAssertEqual(market.representationFallback, "not_a_title_question")
        XCTAssertNil(market.questionIdentity)
        let response = try Self.timeline(F.timelineFallback)
        XCTAssertEqual(response.effectiveRepresentation, .source)
        XCTAssertEqual(response.historyBasis?.source, "kalshi", "the basis is stamped in source mode too")
    }

    func testMalformedOptionalFieldsDecodeToNilAndNeverFailThePage() throws {
        let json = try Self.edited(F.detailVerified) { object in
            object["representation"] = 7
            object["question_identity"] = ["competition": "NFL", "edition": 2027, "question": NSNull()]
            object["contributing_sources"] = "kalshi"
            Self.editOutcome(&object, "Buffalo Bills") { row in
                row["contributing_sources"] = [1, 2]
                row["observed_at"] = 12
                row["aggregation_rule"] = ["rule": "x"]
            }
        }
        let market = try Self.detail(json)
        XCTAssertNil(market.representation)
        XCTAssertEqual(market.effectiveRepresentation, .source, "an unreadable mode is not verified")
        XCTAssertEqual(market.questionIdentity?.competition, "NFL")
        XCTAssertNil(market.questionIdentity?.edition, "a numeric edition is malformed")
        XCTAssertNil(market.contributingSources)
        let bills = try XCTUnwrap(market.outcomes.first { $0.id == buffalo })
        XCTAssertNil(bills.contributingSources)
        XCTAssertNil(bills.observedAt)
        XCTAssertNil(bills.aggregationRule)
        XCTAssertEqual(bills.probability, 0.13, "the rest of the row survives")

        let timeline = try Self.timeline(try Self.edited(F.timelineVerified) { object in
            object["history_basis"] = ["kind": "single_source", "source": "odds_api", "market_id": "86832"]
        })
        XCTAssertEqual(timeline.historyBasis?.source, "odds_api")
        XCTAssertNil(timeline.historyBasis?.marketId, "a string market_id is malformed")
        XCTAssertNil(try Self.timeline(try Self.edited(F.timelineVerified) { $0["history_basis"] = [1] }).historyBasis)
    }

    func testAnUnknownRepresentationValueIsSource() {
        XCTAssertEqual(FuturesRepresentation.effective("blended"), .source)
        XCTAssertEqual(FuturesRepresentation.effective(nil), .source)
        XCTAssertEqual(FuturesRepresentation.effective("verified_title"), .verifiedTitle)
    }

    // MARK: - Hero and metadata labels

    private func verified(heroSources: [String], union: [String]) throws -> FuturesMarketDetail {
        try Self.detail(try Self.edited(F.detailVerified) { object in
            object["contributing_sources"] = union
            Self.editOutcome(&object, "Buffalo Bills") { $0["contributing_sources"] = heroSources }
        })
    }

    func testTheHeroNamesItsOwnOutcomesContributorsNotTheMarketUnion() throws {
        let market = try verified(heroSources: ["kalshi"], union: ["odds_api", "kalshi", "polymarket"])
        let hero = futuresDetailHeroOutcome(market)
        XCTAssertEqual(hero?.id, buffalo)
        XCTAssertEqual(VerifiedTitlePresentation.heroContributors(market, hero: hero), ["kalshi"])
        XCTAssertEqual(VerifiedTitlePresentation.heroSourcePill(market, hero: hero), "Kalshi",
                       "one actual contributor is one source, never a blend")
        XCTAssertEqual(VerifiedTitlePresentation.marketContributors(market), ["odds_api", "kalshi", "polymarket"])
    }

    func testAThreeVenueHeroNamesEachVenue() throws {
        let market = try Self.detail(F.detailVerified)
        let hero = futuresDetailHeroOutcome(market)
        XCTAssertEqual(VerifiedTitlePresentation.heroSourcePill(market, hero: hero),
                       "Sportsbooks · Kalshi · Polymarket")
    }

    func testAnUnknownContributorKeyKeepsTheSourceHeader() throws {
        let market = try verified(heroSources: ["kalshi", "betfair"], union: ["kalshi", "betfair"])
        let hero = futuresDetailHeroOutcome(market)
        XCTAssertNil(VerifiedTitlePresentation.heroContributors(market, hero: hero))
        XCTAssertNil(VerifiedTitlePresentation.marketContributors(market))
        XCTAssertEqual(VerifiedTitlePresentation.heroSourcePill(market, hero: hero), "Sportsbooks",
                       "the source-mode header, never an invented label")
        let empty = try verified(heroSources: [], union: [])
        XCTAssertEqual(VerifiedTitlePresentation.heroSourcePill(empty, hero: futuresDetailHeroOutcome(empty)),
                       "Sportsbooks")
    }

    func testSourceModeHeaderIsUnchanged() throws {
        for json in [F.detailDefault, F.detailFallback] {
            let market = try Self.detail(json)
            let hero = futuresDetailHeroOutcome(market)
            XCTAssertNil(VerifiedTitlePresentation.heroContributors(market, hero: hero))
            XCTAssertEqual(VerifiedTitlePresentation.heroSourcePill(market, hero: hero),
                           SourceLabels.label(for: market.source))
            XCTAssertFalse(VerifiedTitlePresentation.shareOmitsQuote(market))
        }
        XCTAssertTrue(VerifiedTitlePresentation.shareOmitsQuote(try Self.detail(F.detailVerified)))
    }

    // MARK: - Chart labels

    func testTheHistoryLabelComesFromTheResponsesOwnBasis() {
        func basis(_ kind: String?, _ source: String?) -> TimelineHistoryBasis {
            TimelineHistoryBasis(kind: kind, source: source, marketId: 1)
        }
        XCTAssertEqual(VerifiedTitlePresentation.historyLabel(basis("single_source", "odds_api")), "Sportsbooks history")
        XCTAssertEqual(VerifiedTitlePresentation.historyLabel(basis("single_source", "kalshi")), "Kalshi history")
        XCTAssertEqual(VerifiedTitlePresentation.historyLabel(basis("single_source", "polymarket")), "Polymarket history")
        XCTAssertNil(VerifiedTitlePresentation.historyLabel(basis("single_source", "mystery")))
        XCTAssertNil(VerifiedTitlePresentation.historyLabel(basis("blend", "odds_api")), "never a blended history")
        XCTAssertNil(VerifiedTitlePresentation.historyLabel(nil))
    }

    func testTheCaptionSaysCurrentBlendOnlyWhileARowReallyBlends() throws {
        let verified = try Self.timeline(F.timelineVerified)
        let detail = try Self.detail(F.detailVerified)
        let expected = VerifiedTitleChartExpectation(market: detail, hero: futuresDetailHeroOutcome(detail))
        XCTAssertEqual(VerifiedTitlePresentation.chartCaption(
            verified, expected: expected, displayed: verified.outcomes, withholdsCurrent: false),
            "Sportsbooks history · Prob: all sources now")
        XCTAssertEqual(VerifiedTitlePresentation.chartCaption(
            verified, expected: expected,
            displayed: VerifiedTitleChartPolicy.withholdingCurrent(verified.outcomes), withholdsCurrent: true),
            "Sportsbooks history", "withheld current numbers earn no blend label")
        let single = try Self.timeline(try Self.edited(F.timelineVerified) { object in
            var outcomes = object["outcomes"] as? [[String: Any]] ?? []
            for i in outcomes.indices { outcomes[i]["contributing_sources"] = ["kalshi"] }
            object["outcomes"] = outcomes
        })
        XCTAssertEqual(VerifiedTitlePresentation.chartCaption(
            single, expected: expected, displayed: single.outcomes, withholdsCurrent: false),
            "Sportsbooks history", "one contributor is not a blend")
    }

    func testSourceModeChartsEarnNoCaption() throws {
        let fallback = try Self.timeline(F.timelineFallback)
        let source = try Self.timeline(F.timelineDefault)
        let sourceDetail = try Self.detail(F.detailFallback)
        let expected = VerifiedTitleChartExpectation(market: sourceDetail, hero: futuresDetailHeroOutcome(sourceDetail))
        XCTAssertNil(VerifiedTitlePresentation.chartCaption(
            fallback, expected: expected, displayed: fallback.outcomes, withholdsCurrent: false))
        XCTAssertNil(VerifiedTitlePresentation.chartCaption(
            fallback, expected: nil, displayed: fallback.outcomes, withholdsCurrent: false))
        XCTAssertNil(VerifiedTitlePresentation.chartCaption(
            source, expected: nil, displayed: source.outcomes, withholdsCurrent: false))
    }

    func testAPersistentMismatchKeepsTheHistoryLabelOnASourceResponse() throws {
        // Detail verified, chart answered in source mode: the lines keep their
        // own label, the current column is withheld.
        let fallbackShaped = try Self.timeline(try Self.edited(F.timelineVerified) { object in
            object["representation"] = "source"
            object["question_identity"] = NSNull()
        })
        let detail = try Self.detail(F.detailVerified)
        let expected = VerifiedTitleChartExpectation(market: detail, hero: futuresDetailHeroOutcome(detail))
        XCTAssertEqual(VerifiedTitlePresentation.chartCaption(
            fallbackShaped, expected: expected,
            displayed: VerifiedTitleChartPolicy.withholdingCurrent(fallbackShaped.outcomes), withholdsCurrent: true),
            "Sportsbooks history")
    }

    // MARK: - Agreement policy (gate 5)

    private func generation(_ expectation: VerifiedTitleChartExpectation?, token: Int = 0,
                            range: String = "week") -> VerifiedTitleChartPolicy.Generation {
        .init(refreshToken: token, range: range, expectation: expectation)
    }

    private func verifiedExpectation(value: Double = 0.13,
                                     sources: [String] = ["odds_api", "kalshi", "polymarket"]) -> VerifiedTitleChartExpectation {
        VerifiedTitleChartExpectation(representation: .verifiedTitle, heroOutcomeId: buffalo,
                                      heroProbability: value, heroContributors: sources)
    }

    func testAnAgreeingChartIsDrawnWithItsCurrentColumn() throws {
        var policy = VerifiedTitleChartPolicy()
        let response = try Self.timeline(F.timelineVerified)
        XCTAssertEqual(policy.step(response, generation: generation(verifiedExpectation())),
                       .adopt(withholdsCurrent: false))
    }

    func testTheFrozenTrioAgreesAcrossDetailAndChart() throws {
        // Gate 4: same frozen input, the detail's hero and the chart's current
        // column agree on value, id and contributors.
        let detail = try Self.detail(F.detailVerified)
        let expected = VerifiedTitleChartExpectation(market: detail, hero: futuresDetailHeroOutcome(detail))
        XCTAssertTrue(expected.agrees(with: try Self.timeline(F.timelineVerified)))
        for outcome in detail.outcomes {
            let meta = try Self.timeline(F.timelineVerified).outcomes.first { $0.id == outcome.id }
            XCTAssertEqual(meta?.currentProbability, outcome.probability, outcome.name)
            XCTAssertEqual(meta?.contributingSources, outcome.contributingSources, outcome.name)
        }
    }

    func testAModeMismatchRefetchesOnceThenWithholdsTheCurrentColumn() throws {
        var policy = VerifiedTitleChartPolicy()
        let source = try Self.timeline(F.timelineFallback)
        let g = generation(verifiedExpectation())
        XCTAssertEqual(policy.step(source, generation: g), .refetch)
        XCTAssertEqual(policy.step(source, generation: g), .adopt(withholdsCurrent: true))
    }

    func testASameModeNewerValueRefetchesOnceAndAdoptsTheAgreeingAnswer() throws {
        // Detail already moved to 0.14 (a sibling venue moved); the chart's first
        // read still says 0.13. One refetch, which agrees.
        var policy = VerifiedTitleChartPolicy()
        let g = generation(verifiedExpectation(value: 0.14))
        XCTAssertEqual(policy.step(try Self.timeline(F.timelineVerified), generation: g), .refetch)
        let newer = try Self.timeline(try Self.edited(F.timelineVerified) { object in
            Self.editOutcome(&object, "Buffalo Bills") { $0["current_probability"] = 0.14 }
        })
        XCTAssertEqual(policy.step(newer, generation: g), .adopt(withholdsCurrent: false))
    }

    func testAContributorDisagreementAloneCountsAsAMismatch() throws {
        var policy = VerifiedTitleChartPolicy()
        let g = generation(verifiedExpectation(sources: ["odds_api", "kalshi"]))
        XCTAssertEqual(policy.step(try Self.timeline(F.timelineVerified), generation: g), .refetch)
    }

    func testAPersistentMismatchNeverLoops() throws {
        var policy = VerifiedTitleChartPolicy()
        let g = generation(verifiedExpectation(value: 0.5))
        let response = try Self.timeline(F.timelineVerified)
        let steps = (0..<5).map { _ in policy.step(response, generation: g) }
        XCTAssertEqual(steps, [.refetch] + Array(repeating: .adopt(withholdsCurrent: true), count: 4))
    }

    func testEachDetailOrRangeGenerationGetsItsOwnSingleRetry() throws {
        var policy = VerifiedTitleChartPolicy()
        let response = try Self.timeline(F.timelineVerified)
        let stale = verifiedExpectation(value: 0.5)
        XCTAssertEqual(policy.step(response, generation: generation(stale)), .refetch)
        XCTAssertEqual(policy.step(response, generation: generation(stale)), .adopt(withholdsCurrent: true))
        XCTAssertEqual(policy.step(response, generation: generation(stale, range: "day")), .refetch, "range switch")
        XCTAssertEqual(policy.step(response, generation: generation(stale, token: 1, range: "day")), .refetch, "detail refresh")
        XCTAssertEqual(policy.step(response, generation: generation(verifiedExpectation(), token: 1, range: "day")),
                       .adopt(withholdsCurrent: false), "new hero reading that agrees")
    }

    func testAChartWithNoExpectationIsTheUnchangedSourceChart() throws {
        var policy = VerifiedTitleChartPolicy()
        for json in [F.timelineVerified, F.timelineDefault, F.timelineFallback] {
            XCTAssertEqual(policy.step(try Self.timeline(json), generation: generation(nil)),
                           .adopt(withholdsCurrent: false))
        }
    }

    func testASourceDetailAgreesWithASourceChartWithoutComparingNumbers() throws {
        let detail = try Self.detail(F.detailFallback)
        let expected = VerifiedTitleChartExpectation(market: detail, hero: futuresDetailHeroOutcome(detail))
        XCTAssertTrue(expected.agrees(with: try Self.timeline(F.timelineFallback)))
        XCTAssertFalse(expected.agrees(with: try Self.timeline(F.timelineVerified)), "source detail, verified chart")
    }

    func testWithholdingKeepsNamesIdsOrderAndTeamDataAndBlanksOnlyTheCurrentColumn() throws {
        // Seed a 24h move on every row: the served trio nulls it, and a withheld
        // column must blank a move that IS there, not one that never was.
        let response = try Self.timeline(try Self.edited(F.timelineVerified) { object in
            var outcomes = object["outcomes"] as? [[String: Any]] ?? []
            for i in outcomes.indices { outcomes[i]["probability_change_24h"] = 0.02 }
            object["outcomes"] = outcomes
        })
        XCTAssertTrue(response.outcomes.allSatisfy { $0.probabilityChange24h == 0.02 })
        let withheld = VerifiedTitleChartPolicy.withholdingCurrent(response.outcomes)
        XCTAssertEqual(withheld.map(\.name), response.outcomes.map(\.name))
        XCTAssertEqual(withheld.map(\.id), response.outcomes.map(\.id))
        XCTAssertEqual(withheld.map(\.teamId), response.outcomes.map(\.teamId))
        XCTAssertTrue(withheld.allSatisfy { $0.currentProbability == nil })
        XCTAssertTrue(withheld.allSatisfy { $0.probabilityChange24h == nil })
        XCTAssertTrue(withheld.allSatisfy { $0.contributingSources == nil })
        XCTAssertFalse(withheld.contains(where: VerifiedTitlePresentation.isCurrentBlend))
    }

    // MARK: - Reconciliation clock (item 6)

    /// The catching case. The requested origin's clock (`last_updated`) and the
    /// oldest observation (`observed_at`) are both unchanged; an eligible sibling
    /// venue moved, so the blended value moved. The newer verified body is adopted.
    func testASiblingOnlyMoveIsAdoptedThoughTheOriginClockStoodStill() throws {
        let held = try Self.detail(F.detailVerified)
        let incoming = try Self.detail(try Self.edited(F.detailVerified) { object in
            Self.editOutcome(&object, "Buffalo Bills") { $0["probability"] = 0.14 }
        })
        XCTAssertEqual(held.outcomes.first { $0.id == buffalo }?.lastUpdated,
                       incoming.outcomes.first { $0.id == buffalo }?.lastUpdated)
        let accepted = FuturesPriceReconciliation.adopting(incoming, over: held)
        XCTAssertEqual(accepted.outcomes.first { $0.id == buffalo }?.probability, 0.14)
    }

    /// Control for the case above: the very same pair in SOURCE mode is still
    /// refused by the per-outcome clock, so the protection the verified branch
    /// steps around is real and is still guarding every source board.
    func testTheSamePairInSourceModeIsStillRefusedByItsClock() throws {
        let strip: (inout [String: Any]) -> Void = { object in
            object.removeValue(forKey: "representation")
        }
        let held = try Self.detail(try Self.edited(F.detailVerified, strip))
        let incoming = try Self.detail(try Self.edited(F.detailVerified) { object in
            strip(&object)
            Self.editOutcome(&object, "Buffalo Bills") { $0["probability"] = 0.14 }
        })
        let accepted = FuturesPriceReconciliation.adopting(incoming, over: held)
        XCTAssertEqual(accepted.outcomes.first { $0.id == buffalo }?.probability, 0.13)
    }

    func testAnEstimatorTransitionIsAdoptedWholeNeverSpliced() throws {
        let verified = try Self.detail(F.detailVerified)
        let source = try Self.detail(F.detailDefault)
        let toSource = FuturesPriceReconciliation.adopting(source, over: verified)
        XCTAssertEqual(toSource.effectiveRepresentation, .source)
        XCTAssertEqual(toSource.outcomes.map(\.probability), source.outcomes.map(\.probability))
        XCTAssertTrue(toSource.outcomes.allSatisfy { $0.contributingSources == nil },
                      "no stale verified quote inside a source-labelled body")
        let toVerified = FuturesPriceReconciliation.adopting(verified, over: source)
        XCTAssertEqual(toVerified.effectiveRepresentation, .verifiedTitle)
        XCTAssertEqual(toVerified.outcomes.map(\.probability), verified.outcomes.map(\.probability))
    }

    func testASettledBoardIsNotReopenedByAVerifiedBody() throws {
        let settled = try Self.detail(try Self.edited(F.detailDefault) { object in
            object["status"] = "resolved"
            Self.editOutcome(&object, "Buffalo Bills") { $0["is_winner"] = true }
        })
        let reopened = FuturesPriceReconciliation.adopting(try Self.detail(F.detailVerified), over: settled)
        XCTAssertEqual(reopened.status, "resolved")
        XCTAssertEqual(reopened.outcomes.first { $0.id == buffalo }?.isWinner, true)
    }
}

/// Real-route responses; see the class comment for exactly how they were made.
nonisolated enum VerifiedTitle9387Fixtures {
    static let detailVerified = #"""
{"bookmakers":["BetMGM","BetRivers","Caesars","DraftKings","FanDuel","Fanatics","bet365","BetOnline.ag"],
 "canonical_market_key":"football::championship:2027",
 "category":"championship",
 "category_page":null,
 "category_tags":["football"],
 "commence_time":null,
 "container_of_event_id":null,
 "contributing_sources":["odds_api","kalshi","polymarket"],
 "created_at":null,
 "description":null,
 "event_concept_key":null,
 "expired_rungs_dropped":0,
 "external_id":"americanfootball_nfl_super_bowl_winner",
 "group_id":null,
 "hook_description":null,
 "hook_withheld":false,
 "hub_slug":null,
 "id":86832,
 "image_url":null,
 "lead_outcome_id":null,
 "llm_sport_category":"football",
 "market_type":null,
 "mutually_exclusive":true,
 "name":"NFL Super Bowl Winner",
 "openings_withheld":false,
 "outcome_count":7,
 "outcomes":[
  {"aggregation_rule":"weighted_median","american_odds":669,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309486,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Buffalo Bills","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.13,"probability_change_24h":null,"rank":1,"rank_change_24h":null,"resolution_source":null},
  {"aggregation_rule":"weighted_median","american_odds":852,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309485,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Los Angeles Rams","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.105,"probability_change_24h":null,"rank":2,"rank_change_24h":null,"resolution_source":null},
  {"aggregation_rule":"weighted_median","american_odds":1056,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309494,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"San Francisco 49ers","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.0865,"probability_change_24h":null,"rank":3,"rank_change_24h":null,"resolution_source":null},
  {"aggregation_rule":"weighted_median","american_odds":1076,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309490,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Kansas City Chiefs","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.085,"probability_change_24h":null,"rank":4,"rank_change_24h":null,"resolution_source":null},
  {"aggregation_rule":"weighted_median","american_odds":3233,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309499,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Los Angeles Chargers","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.03,"probability_change_24h":null,"rank":5,"rank_change_24h":null,"resolution_source":null},
  {"aggregation_rule":"weighted_median","american_odds":4900,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309501,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"New York Giants","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.02,"probability_change_24h":null,"rank":6,"rank_change_24h":null,"resolution_source":null},
  {"aggregation_rule":"weighted_median","american_odds":6567,"contributing_sources":["odds_api","kalshi","polymarket"],"id":1309502,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"New York Jets","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_american_odds":null,"opening_probability":null,"price_changed_at":null,"probability":0.015,"probability_change_24h":null,"rank":7,"rank_change_24h":null,"resolution_source":null}
 ],
 "prices_withheld":0,
 "question_identity":{"competition":"NFL","edition":"2027","question":"league_championship_winner"},
 "representation":"verified_title",
 "resolution_date":null,
 "source":"odds_api",
 "sport":null,
 "sport_name":null,
 "sport_page_key":null,
 "status":"open",
 "updated_at":null}
"""#

    static let detailDefault = #"""
{"bookmakers":["BetMGM","BetRivers","Caesars","DraftKings","FanDuel","Fanatics","bet365","BetOnline.ag"],
 "canonical_market_key":"football::championship:2027",
 "category":"championship",
 "category_page":null,
 "category_tags":["football"],
 "commence_time":null,
 "container_of_event_id":null,
 "created_at":null,
 "description":null,
 "event_concept_key":null,
 "expired_rungs_dropped":0,
 "external_id":"americanfootball_nfl_super_bowl_winner",
 "group_id":null,
 "hook_description":null,
 "hook_withheld":false,
 "hub_slug":null,
 "id":86832,
 "image_url":null,
 "lead_outcome_id":null,
 "llm_sport_category":"football",
 "market_type":null,
 "mutually_exclusive":true,
 "name":"NFL Super Bowl Winner",
 "openings_withheld":false,
 "outcome_count":7,
 "outcomes":[
  {"american_odds":786,"id":1309486,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Buffalo Bills","opening_american_odds":null,"opening_probability":0.0564565,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.112913,"probability_change_24h":null,"rank":1,"rank_change_24h":null,"resolution_source":null},
  {"american_odds":831,"id":1309485,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Los Angeles Rams","opening_american_odds":null,"opening_probability":0.0536805,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.107361,"probability_change_24h":null,"rank":2,"rank_change_24h":null,"resolution_source":null},
  {"american_odds":1095,"id":1309494,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"San Francisco 49ers","opening_american_odds":null,"opening_probability":0.0418505,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.083701,"probability_change_24h":null,"rank":3,"rank_change_24h":null,"resolution_source":null},
  {"american_odds":1150,"id":1309490,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Kansas City Chiefs","opening_american_odds":null,"opening_probability":0.04,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.08,"probability_change_24h":null,"rank":4,"rank_change_24h":null,"resolution_source":null},
  {"american_odds":3233,"id":1309499,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"Los Angeles Chargers","opening_american_odds":null,"opening_probability":0.015,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.03,"probability_change_24h":null,"rank":5,"rank_change_24h":null,"resolution_source":null},
  {"american_odds":4900,"id":1309501,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"New York Giants","opening_american_odds":null,"opening_probability":0.01,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.02,"probability_change_24h":null,"rank":6,"rank_change_24h":null,"resolution_source":null},
  {"american_odds":6567,"id":1309502,"is_winner":null,"last_updated":"2026-10-02T12:36:27.740202+00:00","name":"New York Jets","opening_american_odds":null,"opening_probability":0.0075,"price_changed_at":"2026-10-02T12:36:27.740202+00:00","probability":0.015,"probability_change_24h":null,"rank":7,"rank_change_24h":null,"resolution_source":null}
 ],
 "prices_withheld":0,
 "resolution_date":null,
 "source":"odds_api",
 "sport":null,
 "sport_name":null,
 "sport_page_key":null,
 "status":"open",
 "updated_at":null}
"""#

    static let detailFallback = #"""
{"bookmakers":[],
 "canonical_market_key":"football::championship:2027",
 "category":"championship",
 "category_page":null,
 "category_tags":["football"],
 "commence_time":null,
 "container_of_event_id":null,
 "created_at":null,
 "description":null,
 "event_concept_key":null,
 "expired_rungs_dropped":0,
 "external_id":"KXNFLMVP-27",
 "group_id":null,
 "hook_description":null,
 "hook_withheld":false,
 "hub_slug":null,
 "id":900001,
 "image_url":null,
 "lead_outcome_id":null,
 "llm_sport_category":"football",
 "market_type":null,
 "mutually_exclusive":true,
 "name":"2027 Pro Football MVP",
 "openings_withheld":false,
 "outcome_count":1,
 "outcomes":[
  {"american_odds":233,"id":900011,"is_winner":null,"last_updated":"2026-10-02T07:54:47.255493+00:00","name":"Josh Allen","opening_american_odds":null,"opening_probability":null,"price_changed_at":"2026-10-02T07:54:47.255493+00:00","probability":0.3,"probability_change_24h":null,"rank":1,"rank_change_24h":null,"resolution_source":null}
 ],
 "prices_withheld":0,
 "question_identity":null,
 "representation":"source",
 "representation_fallback":"not_a_title_question",
 "resolution_date":"2027-02-10T00:00:00+00:00",
 "source":"kalshi",
 "sport":null,
 "sport_name":null,
 "sport_page_key":null,
 "status":"open",
 "updated_at":null}
"""#

    static let timelineVerified = #"""
{"actual_hours":168,
 "bucket_seconds":3600,
 "contributing_sources":["odds_api","kalshi","polymarket"],
 "coverage_end":"2026-10-02T15:00:00+00:00",
 "coverage_hours":4.0,
 "coverage_start":"2026-10-02T11:00:00+00:00",
 "history_basis":{"kind":"single_source","market_id":86832,"source":"odds_api"},
 "hours":168,
 "market_id":86832,
 "market_name":"NFL Super Bowl Winner",
 "observation_times":3,
 "outcomes":[
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.13,"id":1309486,"name":"Buffalo Bills","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null},
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.105,"id":1309485,"name":"Los Angeles Rams","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null},
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.0865,"id":1309494,"name":"San Francisco 49ers","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null},
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.085,"id":1309490,"name":"Kansas City Chiefs","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null},
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.03,"id":1309499,"name":"Los Angeles Chargers","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null},
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.02,"id":1309501,"name":"New York Giants","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null},
  {"aggregation_rule":"weighted_median","contributing_sources":["odds_api","kalshi","polymarket"],"current_probability":0.015,"id":1309502,"name":"New York Jets","observed_at":"2026-10-02T07:54:47.255493+00:00","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null}
 ],
 "question_identity":{"competition":"NFL","edition":"2027","question":"league_championship_winner"},
 "representation":"verified_title",
 "source":"odds_api",
 "sport_category":"football",
 "timeline":[
  {"outcomes":{"Buffalo Bills":0.101622,"Kansas City Chiefs":0.072,"Los Angeles Chargers":0.027,"Los Angeles Rams":0.096625,"New York Giants":0.018,"New York Jets":0.0135,"San Francisco 49ers":0.075331},"timestamp":"2026-10-02T11:00:00+00:00"},
  {"outcomes":{"Buffalo Bills":0.107267,"Kansas City Chiefs":0.076,"Los Angeles Chargers":0.0285,"Los Angeles Rams":0.101993,"New York Giants":0.019,"New York Jets":0.01425,"San Francisco 49ers":0.079516},"timestamp":"2026-10-02T13:00:00+00:00"},
  {"outcomes":{"Buffalo Bills":0.112913,"Kansas City Chiefs":0.08,"Los Angeles Chargers":0.03,"Los Angeles Rams":0.107361,"New York Giants":0.02,"New York Jets":0.015,"San Francisco 49ers":0.083701},"timestamp":"2026-10-02T15:00:00+00:00"}
 ],
 "top":10}
"""#

    static let timelineDefault = #"""
{"actual_hours":168,
 "bucket_seconds":3600,
 "coverage_end":"2026-10-02T15:00:00+00:00",
 "coverage_hours":4.0,
 "coverage_start":"2026-10-02T11:00:00+00:00",
 "hours":168,
 "market_id":86832,
 "market_name":"NFL Super Bowl Winner",
 "observation_times":3,
 "outcomes":[
  {"current_probability":0.112913,"id":1309486,"name":"Buffalo Bills","opening_probability":0.0564565,"probability_change_24h":null,"rank":null,"team_id":null},
  {"current_probability":0.107361,"id":1309485,"name":"Los Angeles Rams","opening_probability":0.0536805,"probability_change_24h":null,"rank":null,"team_id":null},
  {"current_probability":0.083701,"id":1309494,"name":"San Francisco 49ers","opening_probability":0.0418505,"probability_change_24h":null,"rank":null,"team_id":null},
  {"current_probability":0.08,"id":1309490,"name":"Kansas City Chiefs","opening_probability":0.04,"probability_change_24h":null,"rank":null,"team_id":null},
  {"current_probability":0.03,"id":1309499,"name":"Los Angeles Chargers","opening_probability":0.015,"probability_change_24h":null,"rank":null,"team_id":null},
  {"current_probability":0.02,"id":1309501,"name":"New York Giants","opening_probability":0.01,"probability_change_24h":null,"rank":null,"team_id":null},
  {"current_probability":0.015,"id":1309502,"name":"New York Jets","opening_probability":0.0075,"probability_change_24h":null,"rank":null,"team_id":null}
 ],
 "source":"odds_api",
 "sport_category":"football",
 "timeline":[
  {"outcomes":{"Buffalo Bills":0.101622,"Kansas City Chiefs":0.072,"Los Angeles Chargers":0.027,"Los Angeles Rams":0.096625,"New York Giants":0.018,"New York Jets":0.0135,"San Francisco 49ers":0.075331},"timestamp":"2026-10-02T11:00:00+00:00"},
  {"outcomes":{"Buffalo Bills":0.107267,"Kansas City Chiefs":0.076,"Los Angeles Chargers":0.0285,"Los Angeles Rams":0.101993,"New York Giants":0.019,"New York Jets":0.01425,"San Francisco 49ers":0.079516},"timestamp":"2026-10-02T13:00:00+00:00"},
  {"outcomes":{"Buffalo Bills":0.112913,"Kansas City Chiefs":0.08,"Los Angeles Chargers":0.03,"Los Angeles Rams":0.107361,"New York Giants":0.02,"New York Jets":0.015,"San Francisco 49ers":0.083701},"timestamp":"2026-10-02T15:00:00+00:00"}
 ],
 "top":10}
"""#

    static let timelineFallback = #"""
{"actual_hours":168,
 "bucket_seconds":3600,
 "coverage_end":"2026-10-02T15:00:00+00:00",
 "coverage_hours":4.0,
 "coverage_start":"2026-10-02T11:00:00+00:00",
 "history_basis":{"kind":"single_source","market_id":900001,"source":"kalshi"},
 "hours":168,
 "market_id":900001,
 "market_name":"2027 Pro Football MVP",
 "observation_times":3,
 "outcomes":[
  {"current_probability":0.3,"id":900011,"name":"Josh Allen","opening_probability":null,"probability_change_24h":null,"rank":null,"team_id":null}
 ],
 "question_identity":null,
 "representation":"source",
 "representation_fallback":"not_a_title_question",
 "source":"kalshi",
 "sport_category":"football",
 "timeline":[
  {"outcomes":{"Josh Allen":0.27},"timestamp":"2026-10-02T11:00:00+00:00"},
  {"outcomes":{"Josh Allen":0.285},"timestamp":"2026-10-02T13:00:00+00:00"},
  {"outcomes":{"Josh Allen":0.3},"timestamp":"2026-10-02T15:00:00+00:00"}
 ],
 "top":10}
"""#
}
