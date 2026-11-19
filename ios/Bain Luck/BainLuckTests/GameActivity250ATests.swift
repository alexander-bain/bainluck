import Foundation
import XCTest
@testable import Bain_Luck

final class GameActivity250ATests: XCTestCase {
    private let observedAt = Date(timeIntervalSince1970: 1_763_600_000)

    func testEventDetailDecodesPresentOnlyScoreSourceUnavailable() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let unavailableJSON = Data("""
        {
          "id": 15350957,
          "sport": "tennis_atp",
          "home_team": "Tristan Boyer",
          "away_team": "Genaro Alberto Olivieri",
          "status": "live",
          "hero_probability": 0.624,
          "hero_probability_away": 0.376,
          "hero_probability_observed_at": "2001-10-15T23:00:00Z",
          "score_source_unavailable": true
        }
        """.utf8)
        let unavailable = try decoder.decode(EventDetail.self, from: unavailableJSON)
        XCTAssertEqual(unavailable.scoreSourceUnavailable, true)

        let coveredJSON = Data("""
        {
          "id": 15350958,
          "sport": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "New York Knicks",
          "status": "live",
          "home_score": 88,
          "away_score": 84
        }
        """.utf8)
        let covered = try decoder.decode(EventDetail.self, from: coveredJSON)
        XCTAssertNil(covered.scoreSourceUnavailable)
    }

    @MainActor
    func testLiveActivityReadingCarriesScoreSourceUnavailableOnlyWhenLiveAndScoreless() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let raw = Data("""
        {
          "id": 15350957,
          "sport": "tennis_atp",
          "home_team": "Tristan Boyer",
          "away_team": "Genaro Alberto Olivieri",
          "status": "live",
          "hero_probability": 0.624,
          "hero_probability_away": 0.376,
          "hero_probability_observed_at": "2001-10-15T23:00:00Z",
          "score_source_unavailable": true
        }
        """.utf8)
        let detail = try decoder.decode(EventDetail.self, from: raw)
        let snap = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: detail, now: observedAt))
        XCTAssertEqual(snap.scoreSourceUnavailable, true)
        XCTAssertNil(snap.homeScore)
        XCTAssertNil(snap.awayScore)

        // If scores arrive later, scoreSourceUnavailable is stripped.
        var withScores = detail
        withScores.homeScore = 1
        withScores.awayScore = 0
        let scoredSnap = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: withScores, now: observedAt))
        XCTAssertNil(scoredSnap.scoreSourceUnavailable)
    }

    func testSnapshotCodableRoundTripAndBackwardCompatibility() throws {
        let liveUnavailable = try XCTUnwrap(GameActivitySnapshot(
            eventID: 15350957,
            homeTeam: "Tristan Boyer",
            awayTeam: "Genaro Alberto Olivieri",
            lifecycle: .live,
            homeScore: nil,
            awayScore: nil,
            homeProbability: 0.624,
            awayProbability: 0.376,
            sport: "tennis_atp",
            scoreObservedAt: nil,
            probabilityObservedAt: observedAt,
            scoreSourceUnavailable: true
        ))
        let encoded = try JSONEncoder().encode(liveUnavailable)
        let decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: encoded)
        XCTAssertEqual(decoded.scoreSourceUnavailable, true)

        // Older server payload without scoreSourceUnavailable still decodes with nil.
        let legacyJSON = Data("""
        {
          "eventID": 15350958,
          "homeTeam": "Boston Celtics",
          "awayTeam": "New York Knicks",
          "lifecycle": "live",
          "homeScore": 88,
          "awayScore": 84,
          "homeRenderedPercent": 64
        }
        """.utf8)
        let legacy = try JSONDecoder().decode(GameActivitySnapshot.self, from: legacyJSON)
        XCTAssertNil(legacy.scoreSourceUnavailable)

        // Final match never retains scoreSourceUnavailable.
        let finalSnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 15350957,
            homeTeam: "Tristan Boyer",
            awayTeam: "Genaro Alberto Olivieri",
            lifecycle: .final,
            homeScore: nil,
            awayScore: nil,
            scoreSourceUnavailable: true
        ))
        XCTAssertNil(finalSnap.scoreSourceUnavailable)
    }
}
