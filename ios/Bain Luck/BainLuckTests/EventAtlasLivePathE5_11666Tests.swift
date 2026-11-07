import XCTest
@testable import Bain_Luck

/// #11666 Step E5 — Native Event-page Atlas live path (tenths, previews, EKG,
/// `resolveHeadlineObservedAt`, and live/final mark-grammar fidelity).
final class EventAtlasLivePathE5_11666Tests: XCTestCase {

    func testRendersTenthsOnAtlasLiveHeadlineAndKeepsComplementPairsSummingTo100() {
        let pair = EventAtlasLivePath11666.tenthsPair(home: 0.9334, away: 0.0666)
        XCTAssertEqual(pair.home, "93.3%")
        XCTAssertEqual(pair.away, "6.7%")

        let tricky = EventAtlasLivePath11666.tenthsPair(home: 0.3675, away: 0.6325)
        XCTAssertEqual(tricky.home, "36.8%")
        XCTAssertEqual(tricky.away, "63.2%")
    }

    func testOverlaysBlendPreviewsAndPreservesCurrentWinChanceViaResolveHeadlineObservedAt() throws {
        let now = try XCTUnwrap("2026-11-06T05:00:00Z".asDate)
        let committedAt = try XCTUnwrap("2026-11-06T04:15:00Z".asDate) // 45m old (> 30m stale threshold)
        let confirmedAt = try XCTUnwrap("2026-11-06T04:59:55Z".asDate) // 5s old live stream confirmation
        let previewAt = try XCTUnwrap("2026-11-06T04:59:58Z".asDate)   // 2s old one-stream preview
        let commenceTime = try XCTUnwrap("2026-11-06T03:00:00Z".asDate)

        // Without stream confirmation, a 45m-old DB write ages into .lastRecorded.
        XCTAssertEqual(
            EventHeadlinePhase9483.resolve(
                status: "live",
                commenceTime: commenceTime,
                isOpeningLine: false,
                observedAt: committedAt,
                deliveryInterrupted: false,
                now: now
            ),
            .lastRecorded
        )

        // With resolveHeadlineObservedAt, a steady price confirmed by the live
        // stream 5s ago advances the clock ahead of 45m-old acceptedPriceClock.
        let atlasObservedAt = EventAtlasLivePath11666.resolveHeadlineObservedAt(
            EventAtlasLivePath11666.HeadlineObservedAtInput(
                acceptedPriceClock: committedAt,
                confirmedAtShown: confirmedAt,
                freshestSourceStamp: committedAt,
                currentOddsCapturedAt: committedAt
            )
        )
        XCTAssertEqual(atlasObservedAt, confirmedAt)
        XCTAssertEqual(
            EventHeadlinePhase9483.resolve(
                status: "live",
                commenceTime: commenceTime,
                isOpeningLine: false,
                observedAt: atlasObservedAt,
                deliveryInterrupted: false,
                now: now
            ),
            .current
        )

        // When no price clock is adopted, resolveHeadlineObservedAt falls back
        // to freshestSourceStamp and then currentOddsCapturedAt.
        let fallbackStamp = try XCTUnwrap("2026-11-06T04:50:00Z".asDate)
        XCTAssertEqual(
            EventAtlasLivePath11666.resolveHeadlineObservedAt(
                EventAtlasLivePath11666.HeadlineObservedAtInput(
                    acceptedPriceClock: nil,
                    confirmedAtShown: confirmedAt,
                    freshestSourceStamp: fallbackStamp,
                    currentOddsCapturedAt: committedAt
                )
            ),
            fallbackStamp
        )

        // Now a one-stream preview frame arrives:
        let eventJSON = """
        {
            "id": 15342685,
            "sport": "basketball_nba",
            "away_team": "Celtics",
            "home_team": "Warriors",
            "commence_time": "2026-11-06T03:00:00Z",
            "status": "live",
            "hero_probability_source": "blend",
            "hero_probability": 0.912,
            "hero_probability_away": 0.088,
            "hero_probability_observed_at": "2026-11-06T04:15:00Z",
            "blend_fold_revision": {"15342685": 12},
            "current_odds": {
                "home_probability": 0.912,
                "away_probability": 0.088,
                "captured_at": "2026-11-06T04:15:00Z"
            }
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(EventDetail.self, from: Data(eventJSON.utf8))

        let frame = BlendPreviewFrame(
            eventId: 15342685,
            p: 0.934,
            status: "live",
            kind: .blend,
            epoch: 4,
            seq: 9,
            baseRev: 12,
            ttlMs: 15_000,
            displayObservedAt: previewAt
        )
        let nowSec = now.timeIntervalSince1970
        let previewState = BlendPreview.previewAfter(nil, frame, eventId: 15342685, now: nowSec)
        let reading = try XCTUnwrap(
            EventAtlasLivePath11666.overlaidHeadlineReading(
                event: event,
                preview: previewState,
                now: nowSec
            )
        )
        XCTAssertTrue(reading.isPreview)
        XCTAssertEqual(reading.homeProbability, 0.934, accuracy: 1e-6)
        XCTAssertEqual(reading.awayProbability ?? 0, 0.066, accuracy: 1e-6)
        XCTAssertEqual(reading.homeTenthsText, "93.4%")
        XCTAssertEqual(reading.awayTenthsText, "6.6%")
        XCTAssertEqual(reading.observedAt, previewAt)
        XCTAssertEqual(
            EventAtlasHeadlineControlRow11666.tenthsSummary(for: reading, event: event),
            "Celtics 6.6% · Warriors 93.4%"
        )

        let baseFrames = [
            LiveBlendPoint(date: try XCTUnwrap("2026-11-06T04:30:00Z".asDate), homeProbability: 0.88),
            LiveBlendPoint(date: committedAt, homeProbability: 0.912),
        ]
        let overlaidFrames = EventAtlasLivePath11666.overlaidChartFrames(
            frames: baseFrames,
            history: nil,
            preview: previewState,
            event: event,
            now: nowSec
        )
        XCTAssertEqual(overlaidFrames.count, 3)
        XCTAssertEqual(overlaidFrames.last?.date, previewAt)
        XCTAssertEqual(overlaidFrames.last?.homeProbability ?? 0, 0.934, accuracy: 1e-6)
    }

    func testBeatsEkgOnHeldLiveAtlasPageWhenConfirmationsPreviewsOrActivityArriveAndHidesOnFinal() throws {
        let now0 = try XCTUnwrap("2026-11-06T05:00:00Z".asDate)
        let t0 = EventAtlasLivePath11666.stepEkgTracker(
            .empty,
            observation: EkgTracker.Observation(
                eventId: 15342685,
                transportOpen: true,
                confirmedAt: try XCTUnwrap("2026-11-06T04:59:55Z".asDate),
                priceObservedAt: try XCTUnwrap("2026-11-06T04:59:50Z".asDate),
                activityAt: try XCTUnwrap("2026-11-06T04:59:55Z".asDate)
            ),
            now: now0
        )
        XCTAssertEqual(t0.beats, 0)

        // Stream confirms price 6s later -> beats advances to 1
        let now1 = now0.addingTimeInterval(6)
        let t1 = EventAtlasLivePath11666.stepEkgTracker(
            t0,
            observation: EkgTracker.Observation(
                eventId: 15342685,
                transportOpen: true,
                confirmedAt: try XCTUnwrap("2026-11-06T05:00:05Z".asDate),
                priceObservedAt: try XCTUnwrap("2026-11-06T04:59:50Z".asDate),
                activityAt: try XCTUnwrap("2026-11-06T05:00:05Z".asDate)
            ),
            now: now1
        )
        XCTAssertEqual(t1.beats, 1)

        // One-stream preview advances priceObservedAt 3s later -> beats advances to 2
        let now2 = now1.addingTimeInterval(3)
        let t2 = EventAtlasLivePath11666.stepEkgTracker(
            t1,
            observation: EkgTracker.Observation(
                eventId: 15342685,
                transportOpen: true,
                confirmedAt: try XCTUnwrap("2026-11-06T05:00:05Z".asDate),
                priceObservedAt: try XCTUnwrap("2026-11-06T05:00:08Z".asDate),
                activityAt: try XCTUnwrap("2026-11-06T05:00:05Z".asDate)
            ),
            now: now2
        )
        XCTAssertEqual(t2.beats, 2)

        XCTAssertTrue(
            EventAtlasLivePath11666.ekgDraws(
                eventStatus: "live",
                finished: false,
                venueSettledVerdict: false,
                isOpeningLine: false
            )
        )
        let presentation = EkgHeartbeat.present(t2, status: .live, now: now2)
        XCTAssertEqual(presentation.mode, .beating)
        XCTAssertEqual(presentation.beats, 2)

        // Once the game finishes, ekgDraws returns false:
        XCTAssertFalse(
            EventAtlasLivePath11666.ekgDraws(
                eventStatus: "completed",
                finished: true,
                venueSettledVerdict: false,
                isOpeningLine: false
            )
        )
    }

    func testMaintainsFullMarkGrammarFidelityAcrossLiveAndSettledGames() throws {
        let prematchJSON = """
        {
            "home_probability": 0.6,
            "away_probability": 0.4,
            "source": "sportsbooks"
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let prematch = try decoder.decode(PrematchOdds.self, from: Data(prematchJSON.utf8))
        let baseline = EventHeadlinePhase9483.baselineText(
            prematch: prematch,
            opening: nil,
            sport: "basketball_nba",
            awayTeam: "Boston Celtics",
            homeTeam: "Golden State Warriors"
        )
        XCTAssertEqual(baseline, "Pre-match 40% – 60%")

        let liveKey = EventAtlasChartMarkKeyModel11666(settledResult: nil, includesOpening: true)
        XCTAssertTrue(liveKey.showsOpening)
        XCTAssertEqual(liveKey.openingLabel, "Pregame")
        XCTAssertEqual(liveKey.recordedLabel, "Recorded reading")
        XCTAssertEqual(liveKey.changeLabel, "Change")
        XCTAssertFalse(liveKey.showsSettledResultWords)

        let settledBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .home,
            awayTeam: "Cincinnati Bengals",
            homeTeam: "Baltimore Ravens",
            sportKey: "americanfootball_nfl",
            prematch: prematch,
            opening: nil
        )
        XCTAssertEqual(settledBadge.winnerLabel, "Ravens Won")
        XCTAssertEqual(settledBadge.pregameMarkText, "60% pregame")

        let settledKey = EventAtlasChartMarkKeyModel11666(settledResult: .won, includesOpening: true)
        XCTAssertEqual(settledKey.settledWonWord, EventAtlasStates11666.wonWithCheck)
    }

    func testWiresResolveHeadlineObservedAtAndEkgInEventAtlasAndEventDetailView() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")

        let atlasSource = try String(
            contentsOf: root.appendingPathComponent("Components/EventAtlas11666.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(atlasSource.contains("EventAtlasLivePath11666.resolveHeadlineObservedAt("))
        XCTAssertTrue(atlasSource.contains("EventAtlasLivePath11666.overlaidHeadlineReading("))
        XCTAssertTrue(atlasSource.contains("EventAtlasLivePath11666.tenthsPair("))
        XCTAssertTrue(atlasSource.contains("EventAtlasLivePath11666.ekgDraws("))
        XCTAssertTrue(atlasSource.contains("Self.tenthsSummary(for: reading, event: event)"))

        let viewSource = try String(
            contentsOf: root.appendingPathComponent("Views/EventDetailView.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(viewSource.contains("confirmedAtShown: vm.confirmedAtCoveringShown(event)"))
        XCTAssertTrue(viewSource.contains("preview: vm.blendPreview"))
        XCTAssertTrue(viewSource.contains("ekgTracker: ekgTracker"))
        XCTAssertTrue(viewSource.contains("EventAtlasLivePath11666.stepEkgTracker("))

        let vmSource = try String(
            contentsOf: root.appendingPathComponent("ViewModels/EventDetailViewModel.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(vmSource.contains("EventAtlasLivePath11666.overlaidChartFrames("))
    }
}
