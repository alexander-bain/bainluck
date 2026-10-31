import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket Test-match adapter, part three (the original markets and
/// their Details), on REAL served bodies decoded exactly as the app decodes them.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// - `pakistanSriLankaMarkets` — `remaining-sport-evidence-v88/raw/cricket-15327397-game-markets.json`
///   under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`,
///   BYTE FOR BYTE (sha256 c4bd6397486778514ed22b21d383bf904206ef403edc543cc4076c3bd803d019),
///   `GET /api/events/15327397/game-markets` captured 2026-10-12T13:26:17.508190Z
///   beside the detail in `CricketEventPageAdapter10868Tests`. Every section is
///   empty — as on every retained cricket `/game-markets` body.
/// - NEAREST REAL non-empty `/game-markets` body, labelled as such:
///   `HockeyJourneyContributionAdapter10868Tests.devilsKnightsMarkets` with its
///   `devilsKnightsDetail` (NHL 15338496, reduced verbatim subsets; paths and
///   sha256 values are in that file). The rules are the hockey candidate's
///   reviewed originals rules, reused; this proves the cricket scope, heading and
///   one-to-one mapping on real served rows.
@MainActor
final class CricketOriginalsAdapter10868Tests: XCTestCase {
    private typealias O = CricketOriginalsAdapter10868
    private typealias Rules = HockeyJourneyOriginalsAdapter10868

    private func host(_ now: String) -> Rules.Host {
        Rules.Host(now: now.asDate!, calendar: CricketEventPageAdapter10868Tests.pacific,
                   locale: Locale(identifier: "en_US"))
    }

    private func markets(_ json: String) throws -> GameMarketsResponse {
        try CricketEventPageAdapter10868Tests.decoder().decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    func testTheRetainedCricketMarketsAreEmptySoThePanelSaysSoInAvailabilityWords() throws {
        let hash = SHA256.hash(data: Data(Self.pakistanSriLankaMarkets.utf8)).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(hash, "c4bd6397486778514ed22b21d383bf904206ef403edc543cc4076c3bd803d019")
        let event = try CricketEventPageAdapter10868Tests.detail(CricketEventPageAdapter10868Tests.pakistanSriLanka)
        let served = try markets(Self.pakistanSriLankaMarkets)
        XCTAssertEqual(served.eventId, 15327397)
        XCTAssertEqual(served.status, "suspended")
        XCTAssertEqual(served.totals ?? [], [])
        XCTAssertEqual(served.playerProps ?? [], [])

        for held in [served, nil] as [GameMarketsResponse?] {
            let group = O.originals(event, markets: held, host: host(CricketEventPageAdapter10868Tests.capturedAt),
                                    tint: .blue)
            XCTAssertNil(group.catalogue, "no served outcome, no catalogue")
            XCTAssertEqual(group.heading, "Original markets")
            XCTAssertNil(group.context)
            XCTAssertEqual(group.emptyWords, "Original markets unavailable for this match",
                           "availability words — never a claim that no original market exists")
            XCTAssertEqual(group.labels, [:])
            XCTAssertNil(group.selection)
            XCTAssertNil(group.recorded)
        }
    }

    /// The nearest real non-empty body (NHL), read by this screen's adapter.
    func testOnTheNearestRealMarketsBodyEveryListedOutcomeIsOneOriginalInCatalogueOrder() throws {
        let event = try CricketEventPageAdapter10868Tests.detail(HockeyJourneyContributionAdapter10868Tests.devilsKnightsDetail)
        let served = try markets(HockeyJourneyContributionAdapter10868Tests.devilsKnightsMarkets)
        let reader = host("2026-10-30T20:13:55Z")
        let matched = Rules.matched(served, status: event.status, now: reader.now)
        XCTAssertFalse(matched.isEmpty)

        let group = O.originals(event, markets: served, host: reader, tint: .blue)
        let catalogue = try XCTUnwrap(group.catalogue)
        XCTAssertEqual(catalogue.scope, "cricket:15338496:before:originals")
        XCTAssertEqual(catalogue.originals.count, matched.count)
        let expected = matched.map { Rules.original($0, event: event, phase: .before, started: false, host: reader) }
        XCTAssertEqual(catalogue.originals, expected, "the reviewed rule's originals, in its order, unchanged")
        XCTAssertEqual(Set(catalogue.originals.map(\.identity)).count, catalogue.originals.count, "one identity each")
        for (match, original) in zip(matched, catalogue.originals) {
            XCTAssertEqual(group.labels[original.identity], Rules.label(match.source, event: event))
        }
        XCTAssertEqual(group.heading, matched.count == 1 ? "1 original market" : "All \(matched.count) original markets")
        XCTAssertEqual(group.context, matched.count == 1 ? "1 original market outcome" : "\(matched.count) original market outcomes")
    }

    // MARK: Retained payload (byte for byte)

    /// `remaining-sport-evidence-v88/raw/cricket-15327397-game-markets.json` · sha256 c4bd6397486778514ed22b21d383bf904206ef403edc543cc4076c3bd803d019
    private static let pakistanSriLankaMarkets = ##"""
{"event_id":15327397,"home_team":"Pakistan","away_team":"Sri Lanka","home_score":null,"away_score":null,"status":"suspended","totals":[],"player_props":[],"team_totals":[],"spreads":[],"period_markets":[],"matchups":[],"other":[],"pace":null,"props_script":[],"stream_market_ids":[],"outcome_market_ids":{},"outcome_revision_at":{},"outcome_observed_at":{},"open_winner_quote":null,"closed_winner_market_ids":[],"cache":{"generation":3,"created_at":"2026-10-12T13:26:17.886432+00:00","quality":"full","availability":"live","lifecycle_watermark":null,"quality_reasons":[],"source_status":"suspended","build_id":"v5667"}}
"""##
}
