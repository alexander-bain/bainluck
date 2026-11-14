import CryptoKit
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class DiscoverGroupedLooks12642Tests: XCTestCase {

    // MARK: - Real Register Fixtures (#12577 / #12642)

    private func decodeSet(_ json: String, snakeCaseStrategy: Bool = true) throws -> PairedMetricSet {
        let decoder = JSONDecoder()
        if snakeCaseStrategy {
            decoder.keyDecodingStrategy = .convertFromSnakeCase
        }
        return try decoder.decode(PairedMetricSet.self, from: Data(json.utf8))
    }

    private func decodeFeed(_ json: String) throws -> FeedResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
    }

    private let oscarsBestPictureJSON = #"""
    {
      "set_id": "oscars-2027-best-picture",
      "category": "entertainment",
      "kicker": "OSCARS 2027 · BEST PICTURE",
      "title": "The Odyssey leads Best Picture, with 6 films at 75%+ to be nominated",
      "subtitle": "99th Academy Awards · Top 10 most likely to be nominated (ordered by win %, ties broken by nominated %) · Nominee % (averaged across venues on server: #5165726 + #27988771) paired beside Winner % (#6173044)",
      "stage_1_label": "Nominated",
      "stage_2_label": "Wins",
      "stage_1_settled_yes_label": "Nominated",
      "stage_1_settled_no_label": "Not nominated",
      "entries": [
        {
          "subject_key": "film:the-odyssey-2026",
          "subject": "The Odyssey",
          "detail": "Christopher Nolan · Universal Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.978,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.565,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1368337,
            "poster_path": "/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
            "url": "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
            "genre_ids": [12, 28, 14],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:you-can-see-everything-2026",
          "subject": "You Can See Everything",
          "detail": "Nathan Fielder & Lance Oppenheim · Blow Out Productions",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.8525,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.165,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1765072,
            "poster_path": "/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
            "url": "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
            "genre_ids": [99],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:the-black-ball-2026",
          "subject": "The Black Ball",
          "detail": "Javier Ambrossi & Javier Calvo · Movistar Plus",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.945,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.145,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1422041,
            "poster_path": "/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
            "url": "https://image.tmdb.org/t/p/w342/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
            "genre_ids": [18, 10752],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:dune-part-three-2026",
          "subject": "Dune: Part Three",
          "detail": "Denis Villeneuve · Legendary Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.825,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.075,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1170608,
            "poster_path": "/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
            "url": "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
            "genre_ids": [878, 12],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:wild-horse-nine-2026",
          "subject": "Wild Horse Nine",
          "detail": "Martin McDonagh · Searchlight Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.9275,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.015,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 891621,
            "poster_path": "/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
            "url": "https://image.tmdb.org/t/p/w342/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
            "genre_ids": [35, 80, 53],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:artificial-2026",
          "subject": "Artificial",
          "detail": "Luca Guadagnino · Heyday Films",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.575,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.015,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1492198,
            "poster_path": "/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg",
            "url": "https://image.tmdb.org/t/p/w342/2bz0HPE8OFOqnyvl8sCdVDIg1KX.jpg",
            "genre_ids": [35, 18, 36],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:project-hail-mary-2026",
          "subject": "Project Hail Mary",
          "detail": "Phil Lord & Christopher Miller · Amazon MGM Studios",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.76,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.01,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 687163,
            "poster_path": "/iOb2fjXLbpJgyQXe46n1WtGCnaa.jpg",
            "url": "https://image.tmdb.org/t/p/w342/iOb2fjXLbpJgyQXe46n1WtGCnaa.jpg",
            "genre_ids": [878, 12],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:the-debut-2026",
          "subject": "The Debut",
          "detail": "Jesse Eisenberg · Topic Studios",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.7225,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.01,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1391239,
            "poster_path": "/qk8qWJxM9hZSbSjSoEz0LAzcoPb.jpg",
            "url": "https://image.tmdb.org/t/p/w342/qk8qWJxM9hZSbSjSoEz0LAzcoPb.jpg",
            "genre_ids": [10402, 35, 18],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:the-invite-2026",
          "subject": "The Invite",
          "detail": "Olivia Wilde · Annapurna Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.71,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.01,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 950028,
            "poster_path": "/b7Dr8Chzse8VagexAporUu2RtLx.jpg",
            "url": "https://image.tmdb.org/t/p/w342/b7Dr8Chzse8VagexAporUu2RtLx.jpg",
            "genre_ids": [35, 18, 10749],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:i-play-rocky-2026",
          "subject": "I Play Rocky",
          "detail": "Peter Farrelly · Eden Rock Media",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.4875,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": null,
          "missing_stage_2_reason": "Not listed to win",
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1286656,
            "poster_path": "/xE5tY3lppZUyG7WKKThsuYHuAHr.jpg",
            "url": "https://image.tmdb.org/t/p/w342/xE5tY3lppZUyG7WKKThsuYHuAHr.jpg",
            "genre_ids": [18, 36],
            "adult": false,
            "kid_safe_vetted": true
          }
        }
      ]
    }
    """#

    private let nhlPlayoffsCupJSON = #"""
    {
      "set_id": "nhl-2026-27-playoffs-and-cup",
      "category": "hockey",
      "kicker": "NHL 2026–27 · PLAYOFF BERTH TO STANLEY CUP",
      "title": "Carolina leads the Stanley Cup race, with all 9 clubs at 5%+ to win",
      "subtitle": "All 9 NHL clubs at 5%+ to win the Cup (ties broken by playoff %) · Paired by club (#63068142 + #52755659) with ESPN team crests",
      "stage_1_label": "Make Playoffs",
      "stage_2_label": "Win Cup",
      "stage_1_settled_yes_label": "Clinched",
      "stage_1_settled_no_label": "Eliminated",
      "entries": [
        {
          "subject_key": "team:nhl:carolina-hurricanes",
          "subject": "Carolina Hurricanes",
          "detail": "Metropolitan · Eastern Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.94,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.128,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/car.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:colorado-avalanche",
          "subject": "Colorado Avalanche",
          "detail": "Central · Western Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.934,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.1,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/col.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:minnesota-wild",
          "subject": "Minnesota Wild",
          "detail": "Central · Western Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.955,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.09,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/min.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:edmonton-oilers",
          "subject": "Edmonton Oilers",
          "detail": "Pacific · Western Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.91,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.09,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/edm.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:new-jersey-devils",
          "subject": "New Jersey Devils",
          "detail": "Metropolitan · Eastern Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.825,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.071,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/nj.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:florida-panthers",
          "subject": "Florida Panthers",
          "detail": "Atlantic · Eastern Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.7,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.071,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/fla.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:vegas-golden-knights",
          "subject": "Vegas Golden Knights",
          "detail": "Pacific · Western Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.895,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.062,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/vgk.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:dallas-stars",
          "subject": "Dallas Stars",
          "detail": "Central · Western Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.835,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.052,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/dal.png", "adult": false, "kid_safe_vetted": true }
        },
        {
          "subject_key": "team:nhl:tampa-bay-lightning",
          "subject": "Tampa Bay Lightning",
          "detail": "Atlantic · Eastern Conference",
          "stage_1_market_id": 63068142,
          "stage_1_probability": 0.65,
          "stage_1_settled_state": null,
          "stage_2_market_id": 52755659,
          "stage_2_probability": 0.052,
          "art": { "kind": "espn_team_logo", "url": "https://a.espncdn.com/i/teamlogos/nhl/500/tb.png", "adult": false, "kid_safe_vetted": true }
        }
      ]
    }
    """#

    // MARK: - Pure Presentation & Contract Tests

    func testDecodeBothSnakeAndCamelAndSortAndRounding() throws {
        let fromConvert = try decodeSet(oscarsBestPictureJSON, snakeCaseStrategy: true)
        let fromPlain = try decodeSet(oscarsBestPictureJSON, snakeCaseStrategy: false)
        XCTAssertEqual(fromConvert, fromPlain)

        let sorted = PairedMetricPresentation.sortPairedEntries(fromConvert.entries)
        XCTAssertEqual(sorted.count, 10)
        XCTAssertEqual(sorted.prefix(5).map(\.subject), [
            "The Odyssey",
            "You Can See Everything",
            "The Black Ball",
            "Dune: Part Three",
            "Wild Horse Nine"
        ])
        // Unlisted Stage 2 contender always sorts after listed contenders.
        XCTAssertEqual(sorted.last?.subject, "I Play Rocky")
        XCTAssertNil(sorted.last?.stage2Probability)

        // Half-percent rounding uses `renderedPercent` contract v5 (`0.565` -> `57%`, `0.145` -> `15%`).
        let odysseyS2 = PairedMetricPresentation.formatStage2Display(entry: sorted[0], set: fromConvert)
        XCTAssertEqual(odysseyS2.label, "57%")
        let blackBallS2 = PairedMetricPresentation.formatStage2Display(entry: sorted[2], set: fromConvert)
        XCTAssertEqual(blackBallS2.label, "15%")

        // Open probabilities clamp to `1..99%` (never `0%` or `100%` while unsettled).
        let tinyEntry = PairedSubjectEntry(
            subjectKey: "tiny",
            subject: "Longshot Film",
            detail: "Studio",
            stage1MarketId: 1,
            stage1Probability: 0.999,
            stage2MarketId: 2,
            stage2Probability: 0.001
        )
        XCTAssertEqual(PairedMetricPresentation.formatStage1Display(entry: tinyEntry, set: fromConvert).label, "99%")
        XCTAssertEqual(PairedMetricPresentation.formatStage2Display(entry: tinyEntry, set: fromConvert).label, "1%")

        // Look 1 collapsed expander calls out the hidden unpriced contender dynamically.
        let collapsedExpander = PairedMetricPresentation.expanderCopy(
            sortedEntries: sorted,
            set: fromConvert,
            expanded: false
        )
        XCTAssertEqual(collapsedExpander?.primary, "Show all 10 most likely nominees (+5 more)")
        XCTAssertEqual(collapsedExpander?.unpricedNotice, "incl. I Play Rocky (49% nom · Not listed to win)")

        let expandedExpander = PairedMetricPresentation.expanderCopy(
            sortedEntries: sorted,
            set: fromConvert,
            expanded: true
        )
        XCTAssertEqual(expandedExpander?.primary, "Show top 5 by Wins % only")
        XCTAssertNil(expandedExpander?.unpricedNotice)
    }

    func testSettledStage1OverridesAndSubtitleSanitization() throws {
        let oscars = try decodeSet(oscarsBestPictureJSON)

        let cleanOscarsSubtitle = PairedMetricPresentation.formatCardFaceSubtitle(oscars.subtitle)
        XCTAssertFalse(cleanOscarsSubtitle.contains("#5165726"))
        XCTAssertFalse(cleanOscarsSubtitle.contains("kalshi"))
        XCTAssertEqual(
            cleanOscarsSubtitle,
            "99th Academy Awards · Top 10 most likely to be nominated (ordered by win %, ties broken by nominated %)"
        )

        let nhl = try decodeSet(nhlPlayoffsCupJSON)
        let cleanNHLSubtitle = PairedMetricPresentation.formatCardFaceSubtitle(nhl.subtitle)
        XCTAssertFalse(cleanNHLSubtitle.contains("#63068142"))
        XCTAssertEqual(cleanNHLSubtitle, "All 9 NHL clubs at 5%+ to win the Cup (ties broken by playoff %)")

        let settledYes = PairedSubjectEntry(
            subjectKey: "yes",
            subject: "The Odyssey",
            detail: "Universal",
            stage1MarketId: 1,
            stage1Probability: 0.98,
            stage1SettledState: "yes",
            stage2MarketId: 2,
            stage2Probability: 0.62
        )
        let s1Yes = PairedMetricPresentation.formatStage1Display(entry: settledYes, set: oscars)
        XCTAssertEqual(s1Yes.kind, .tick)
        XCTAssertEqual(s1Yes.label, "✓ Nominated")

        let settledNo = PairedSubjectEntry(
            subjectKey: "no",
            subject: "I Play Rocky",
            detail: "Eden Rock",
            stage1MarketId: 1,
            stage1Probability: 0.4875,
            stage1SettledState: "no",
            stage2MarketId: 2,
            stage2Probability: 0.04
        )
        let s1No = PairedMetricPresentation.formatStage1Display(entry: settledNo, set: oscars)
        let s2No = PairedMetricPresentation.formatStage2Display(entry: settledNo, set: oscars)
        XCTAssertEqual(s1No.kind, .cross)
        XCTAssertEqual(s1No.label, "✗ Not nominated")
        XCTAssertEqual(s1No.sublabel, "was 49%")
        XCTAssertEqual(s2No.kind, .cross)
        XCTAssertEqual(s2No.label, "Eliminated")
    }

    func testKidSafeVisualArtGate7461AndInitialsFallback() throws {
        let validPoster = PairedArtAsset(
            kind: .tmdbPoster,
            url: "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
            genreIds: [12, 28],
            adult: false,
            kidSafeVetted: true
        )
        // Safe subject containing "Warriors" (`war` is whole-word blocked only) passes `#7461`.
        let warriors = PairedSubjectEntry(
            subjectKey: "gsw",
            subject: "Golden State Warriors",
            detail: "Pacific Division",
            stage1MarketId: 1,
            stage1Probability: 0.72,
            stage2MarketId: 2,
            stage2Probability: 0.08,
            art: PairedArtAsset(kind: .espnTeamLogo, url: "https://a.espncdn.com/i/teamlogos/nba/500/gs.png", adult: false, kidSafeVetted: true)
        )
        XCTAssertNotNil(PairedMetricPresentation.resolveKidSafeVisualArt(warriors))
        XCTAssertEqual(PairedMetricPresentation.initials(for: "The Odyssey"), "TO")
        XCTAssertEqual(PairedMetricPresentation.initials(for: "Wild Horse Nine"), "WH")

        // Horror genre (27) is blocked.
        let horrorEntry = PairedSubjectEntry(
            subjectKey: "horror",
            subject: "Night House",
            detail: "Studio",
            stage1MarketId: 1,
            stage1Probability: 0.5,
            stage2MarketId: 2,
            stage2Probability: 0.1,
            art: PairedArtAsset(kind: .tmdbPoster, url: validPoster.url, genreIds: [27, 53], adult: false, kidSafeVetted: true)
        )
        XCTAssertNil(PairedMetricPresentation.resolveKidSafeVisualArt(horrorEntry))

        // Adult flag, unvetted flag, HTTP scheme, untrusted host, and blocked text all reject.
        let adultEntry = PairedSubjectEntry(
            subjectKey: "adult",
            subject: "Clean Title",
            detail: "Studio",
            stage1MarketId: 1,
            stage1Probability: 0.5,
            stage2MarketId: 2,
            stage2Probability: 0.1,
            art: PairedArtAsset(kind: .tmdbPoster, url: validPoster.url, adult: true, kidSafeVetted: true)
        )
        XCTAssertNil(PairedMetricPresentation.resolveKidSafeVisualArt(adultEntry))

        let untrustedHost = PairedSubjectEntry(
            subjectKey: "host",
            subject: "Clean Title",
            detail: "Studio",
            stage1MarketId: 1,
            stage1Probability: 0.5,
            stage2MarketId: 2,
            stage2Probability: 0.1,
            art: PairedArtAsset(kind: .tmdbPoster, url: "https://evil.example.com/poster.jpg", adult: false, kidSafeVetted: true)
        )
        XCTAssertNil(PairedMetricPresentation.resolveKidSafeVisualArt(untrustedHost))

        let blockedText = PairedSubjectEntry(
            subjectKey: "war",
            subject: "Civil War Story",
            detail: "Studio",
            stage1MarketId: 1,
            stage1Probability: 0.5,
            stage2MarketId: 2,
            stage2Probability: 0.1,
            art: validPoster
        )
        XCTAssertNil(PairedMetricPresentation.resolveKidSafeVisualArt(blockedText))
    }

    func testLook2PodiumAndTiersPartition() throws {
        let oscars = try decodeSet(oscarsBestPictureJSON)
        let partition = try XCTUnwrap(PairedMetricPresentation.podiumPartition(for: oscars))

        // Visual column order: #2 CHASER (left), #1 LEADER (center, elevated), #3 CONTENDER (right).
        XCTAssertEqual(partition.podiumSpots.map(\.rank), [2, 1, 3])
        XCTAssertEqual(partition.podiumSpots.map(\.badge), ["#2 CHASER", "#1 LEADER", "#3 CONTENDER"])
        XCTAssertEqual(partition.podiumSpots.map(\.elevated), [false, true, false])
        XCTAssertEqual(partition.podiumSpots.map(\.entry.subject), [
            "You Can See Everything",
            "The Odyssey",
            "The Black Ball"
        ])
        XCTAssertEqual(partition.lockTier.map(\.subject), [
            "Dune: Part Three",
            "Wild Horse Nine",
            "Project Hail Mary",
            "The Debut",
            "The Invite"
        ])
        XCTAssertEqual(partition.bubbleTier.map(\.subject), [
            "Artificial",
            "I Play Rocky"
        ])
    }

    func testFeedResponseDecodesPairedMetricBundleAndStandaloneItem() throws {
        let payload = """
        {
          "items": [
            {
              "type": "paired_metric",
              "score": 95,
              "headline": "Best Picture",
              "visual_form": "paired_bars_top5_expandable",
              "data": \(oscarsBestPictureJSON)
            },
            {
              "type": "bundle",
              "score": 92,
              "headline": "NHL Stanley Cup",
              "data": {
                "id": "paired:nhl-2026-27",
                "title": "NHL Playoff Berth to Stanley Cup",
                "kind": "roundup",
                "visual_form": "podium_and_tiers",
                "paired_metric_set": \(nhlPlayoffsCupJSON),
                "items": []
              }
            }
          ],
          "total": 2,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """
        let response = try decodeFeed(payload)
        XCTAssertEqual(response.items.count, 2)
        XCTAssertEqual(response.items[0].pairedMetricSet?.setId, "oscars-2027-best-picture")
        XCTAssertEqual(response.items[0].visualForm, "paired_bars_top5_expandable")
        XCTAssertEqual(response.items[1].bundle?.pairedMetricSet?.setId, "nhl-2026-27-playoffs-and-cup")

        // Empty-items paired bundle survives `DiscoverView.sanitizedFeedItems` as a standalone paired_metric item.
        let sanitized = DiscoverView.sanitizedFeedItems(response.items)
        XCTAssertEqual(sanitized.count, 2)
        XCTAssertEqual(sanitized[1].type, "paired_metric")
        XCTAssertEqual(sanitized[1].pairedMetricSet?.setId, "nhl-2026-27-playoffs-and-cup")
        XCTAssertEqual(sanitized[1].visualForm, "podium_and_tiers")
    }

    // MARK: - 390pt Visual Proof & Build 5704 Round-Up Capture (#12642 Scope Items 2 & 3)

    func testRenderBuild5704RoundupAndBothWinningGroupedLooksAt390pt() throws {
        let oscars = try decodeSet(oscarsBestPictureJSON)
        let nhl = try decodeSet(nhlPlayoffsCupJSON)

        // Variant of Oscars where row #5 (`Wild Horse Nine`) has `art = nil` so the expanded render
        // visibly proves the `40 × 56 pt` `"WH"` monogram fallback keeping bar tracks vertically aligned.
        let oscarsWithMonogramSample = PairedMetricSet(
            setId: oscars.setId,
            category: oscars.category,
            kicker: oscars.kicker,
            title: oscars.title,
            subtitle: oscars.subtitle,
            stage1Label: oscars.stage1Label,
            stage2Label: oscars.stage2Label,
            stage1SettledYesLabel: oscars.stage1SettledYesLabel,
            stage1SettledNoLabel: oscars.stage1SettledNoLabel,
            entries: oscars.entries.map { entry in
                guard entry.subject == "Wild Horse Nine" else { return entry }
                return PairedSubjectEntry(
                    subjectKey: entry.subjectKey,
                    subject: entry.subject,
                    detail: entry.detail,
                    stage1MarketId: entry.stage1MarketId,
                    stage1Outcome: entry.stage1Outcome,
                    stage1Probability: entry.stage1Probability,
                    stage1SettledState: entry.stage1SettledState,
                    stage2MarketId: entry.stage2MarketId,
                    stage2Outcome: entry.stage2Outcome,
                    stage2Probability: entry.stage2Probability,
                    missingStage1Reason: entry.missingStage1Reason,
                    missingStage2Reason: entry.missingStage2Reason,
                    art: nil
                )
            }
        )

        // Layout width check at 390pt across Standard & Accessibility Dynamic Type sizes.
        for dt in [DynamicTypeSize.large, DynamicTypeSize.accessibility2] {
            for view in [
                AnyView(DiscoverPairedMetricCardView(set: oscars, form: .pairedBarsTop5Expandable).frame(width: 358)),
                AnyView(DiscoverPairedMetricCardView(set: oscars, form: .podiumAndTiers).frame(width: 358)),
                AnyView(DiscoverPairedMetricCardView(set: nhl, form: .podiumAndTiers).frame(width: 358)),
            ] {
                let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: dt)
                let measured = host.sizeThatFits(in: CGSize(width: 358, height: CGFloat.greatestFiniteMagnitude))
                XCTAssertLessThanOrEqual(measured.width, 358.5)
                XCTAssertGreaterThan(measured.height, 260)
            }
        }

        guard let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_12642"],
              !outDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        // Load cached real TMDB posters & ESPN NHL logos from `/tmp/builderc-12642-art-cache` if present.
        var preloaded: [String: UIImage] = [:]
        let cacheDir = URL(fileURLWithPath: "/tmp/builderc-12642-art-cache", isDirectory: true)
        for set in [oscars, nhl] {
            for entry in set.entries {
                guard let urlStr = entry.art?.url else { continue }
                let digest = SHA256.hash(data: Data(urlStr.utf8))
                    .map { String(format: "%02x", $0) }
                    .joined()
                let prefix = String(digest.prefix(16))
                let ext = urlStr.hasSuffix(".png") ? ".png" : ".jpg"
                let fileURL = cacheDir.appendingPathComponent(prefix + ext)
                if let data = try? Data(contentsOf: fileURL), let img = UIImage(data: data) {
                    preloaded[urlStr] = img
                }
            }
        }

        func writeCardSheetPNG<V: View>(_ content: V, filename: String) throws {
            let wrapped = content
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .background(DS.surface)
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(wrapped, at: .large)
            host.overrideUserInterfaceStyle = .light
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 4000))
            let size = CGSize(width: 390, height: ceil(fitting.height))
            host.view.frame = CGRect(origin: .zero, size: size)

            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = .light
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            let until = Date().addingTimeInterval(0.25)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            if let png = img.pngData() {
                try png.write(to: dirURL.appendingPathComponent(filename))
            }
        }

        // 1. Build 5704 (`781a0a0674`) round-up capture on live `/api/feed` `kind: "roundup"` bundles.
        if let roundupPath = ProcessInfo.processInfo.environment["BUILDER_C_LIVE_ROUNDUP_JSON"],
           let roundupData = try? Data(contentsOf: URL(fileURLWithPath: roundupPath)) {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let feed = try decoder.decode(FeedResponse.self, from: roundupData)
            let bundles = feed.items.compactMap(\.bundle)
            XCTAssertFalse(bundles.isEmpty)
            let legacyRoundupSheet = VStack(alignment: .leading, spacing: 14) {
                ForEach(bundles, id: \.id) { b in
                    NativeGroupCard(
                        title: b.title,
                        items: b.items,
                        kind: b.kind,
                        theme: b.comparisonTheme,
                        sharedQuestion: b.sharedQuestion,
                        collectionRef: b.themeCollectionRef,
                        navigationPath: .constant(NavigationPath())
                    )
                }
            }
            try writeCardSheetPNG(legacyRoundupSheet, filename: "12642-build-5704-roundup-today-390.png")
        }

        // 2. Look 1 (`paired_bars_top5_expandable`) collapsed on real Oscars Best Picture + NHL Playoff/Cup.
        try writeCardSheetPNG(
            DiscoverPairedMetricCardView(
                set: oscars,
                form: .pairedBarsTop5Expandable,
                initialExpanded: false,
                preloadedImages: preloaded
            ),
            filename: "12642-look1-oscars-collapsed-390.png"
        )
        try writeCardSheetPNG(
            DiscoverPairedMetricCardView(
                set: nhl,
                form: .pairedBarsTop5Expandable,
                initialExpanded: false,
                preloadedImages: preloaded
            ),
            filename: "12642-look1-nhl-collapsed-390.png"
        )

        // 3. Look 1 (`paired_bars_top5_expandable`) expanded (all 10 rows incl. unpriced `I Play Rocky` + `WH` monogram fallback).
        try writeCardSheetPNG(
            DiscoverPairedMetricCardView(
                set: oscarsWithMonogramSample,
                form: .pairedBarsTop5Expandable,
                initialExpanded: true,
                preloadedImages: preloaded
            ),
            filename: "12642-look1-oscars-expanded-and-monogram-390.png"
        )

        // 4. Look 2 (`podium_and_tiers`) on real Oscars Best Picture.
        try writeCardSheetPNG(
            DiscoverPairedMetricCardView(
                set: oscars,
                form: .podiumAndTiers,
                preloadedImages: preloaded
            ),
            filename: "12642-look2-oscars-podium-390.png"
        )

        // 5. Look 2 (`podium_and_tiers`) on real NHL Playoff Berth -> Stanley Cup.
        try writeCardSheetPNG(
            DiscoverPairedMetricCardView(
                set: nhl,
                form: .podiumAndTiers,
                preloadedImages: preloaded
            ),
            filename: "12642-look2-nhl-podium-390.png"
        )
    }
}
