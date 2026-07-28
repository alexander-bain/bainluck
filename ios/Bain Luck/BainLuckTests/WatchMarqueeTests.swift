import XCTest

/// L2-200: guards the Watch home marquee selection.
///
/// The bug (C5 P2, `WatchHomeView.swift:349`): `marquee(from:)` tested only
/// `topLive ?? items.first` and returned nil when that single item was not
/// renderable. A leading concept/tournament (unsupported on Watch) or an event
/// without `current_odds` blanked the entire marquee even when a usable story sat
/// second or later. The fix scans ranked items for the first renderable story
/// while preserving live-event priority.
///
/// `WatchMarquee.swift` and `WatchFeedModels.swift` are pure Foundation/SwiftUI
/// (no WatchKit) and are compiled into this test bundle directly (see the
/// project's target membership), so these run without pulling WatchKit into the
/// iOS test host — mirroring `WatchGuessPoolTests`.
final class WatchMarqueeTests: XCTestCase {

    private func items(_ json: String) throws -> [WatchFeedItem] {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(WatchFeedResponse.self, from: Data(json.utf8)).items
    }

    // A concept card (no Watch-renderable probability) — unsupported on Watch.
    private let conceptItem = """
        { "type": "concept", "score": 99,
          "data": { "key": "cycling:tour-de-france-2026", "name": "Tour de France" } }
    """
    // A tournament card — also unsupported on Watch.
    private let tournamentItem = """
        { "type": "tournament", "score": 98, "data": { "slug": "the-open", "name": "The Open" } }
    """
    // A usable, non-live futures story.
    private let usableFutures = """
        { "type": "futures", "score": 60,
          "data": { "id": 7, "name": "2026 NBA Champion",
                    "top_outcomes": [ { "name": "Celtics", "probability": 0.34 } ] } }
    """
    // A usable, non-live scheduled event story.
    private let usableEvent = """
        { "type": "event", "score": 55,
          "data": { "id": 11, "home_team": "Boston Celtics", "away_team": "LA Lakers",
                    "status": "scheduled", "current_odds": { "home_probability": 0.62 } } }
    """
    // A usable LIVE event story.
    private let liveEvent = """
        { "type": "event", "score": 50,
          "data": { "id": 12, "home_team": "Miami Heat", "away_team": "NY Knicks",
                    "status": "live", "current_odds": { "home_probability": 0.48 } } }
    """
    // An event MISSING its probability (no current_odds) — not renderable.
    private let eventNoProb = """
        { "type": "event", "score": 70,
          "data": { "id": 13, "home_team": "Team A", "away_team": "Team B", "status": "scheduled" } }
    """

    // MARK: - Unsupported first item does not erase a usable later story

    func testUnsupportedFirstItemFallsThroughToUsableFutures() throws {
        let feed = try items("{ \"items\": [ \(conceptItem), \(usableFutures) ] }")
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed),
                                  "a leading concept must not blank the marquee")
        XCTAssertEqual(story.title, "2026 NBA Champion")
        XCTAssertEqual(story.bigLabel, "Celtics")
        XCTAssertEqual(story.bigNumber, 34)
    }

    func testUnsupportedTournamentFirstFallsThroughToUsableEvent() throws {
        let feed = try items("{ \"items\": [ \(tournamentItem), \(usableEvent) ] }")
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed))
        // No team-data abbreviations in the fixture → abbrev falls back to the last
        // name token ("LA Lakers" → "Lakers", "Boston Celtics" → "Celtics").
        XCTAssertEqual(story.title, "Lakers @ Celtics")
    }

    // MARK: - Event without probability is skipped for a later usable item

    func testEventWithoutProbabilitySkippedForLaterStory() throws {
        let feed = try items("{ \"items\": [ \(eventNoProb), \(usableFutures) ] }")
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed),
                                  "an odds-less event must not blank the marquee")
        XCTAssertEqual(story.title, "2026 NBA Champion")
    }

    // MARK: - Usable item second/later (multiple unsupported ahead of it)

    func testUsableItemDeepInTheFeedIsFound() throws {
        let feed = try items(
            "{ \"items\": [ \(conceptItem), \(tournamentItem), \(eventNoProb), \(usableEvent) ] }")
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed))
        XCTAssertEqual(story.title, "Lakers @ Celtics")
    }

    // MARK: - No usable story → explicit nil (stable empty state upstream)

    func testNoRenderableStoryReturnsNil() throws {
        let feed = try items(
            "{ \"items\": [ \(conceptItem), \(tournamentItem), \(eventNoProb) ] }")
        XCTAssertNil(WatchMarquee.marquee(from: feed),
                     "all-unsupported feed yields no marquee (view shows empty state)")
    }

    func testEmptyFeedReturnsNil() throws {
        let feed = try items("{ \"items\": [] }")
        XCTAssertNil(WatchMarquee.marquee(from: feed))
    }

    // MARK: - Live-event priority beats an earlier non-live usable item

    func testLiveEventTakesPriorityOverEarlierFutures() throws {
        // Futures is first in rank order, but a live event exists later — live wins.
        let feed = try items("{ \"items\": [ \(usableFutures), \(liveEvent) ] }")
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed))
        // "NY Knicks" → "Knicks", "Miami Heat" → "Heat" (last-token abbrev fallback).
        XCTAssertEqual(story.title, "Knicks @ Heat", "the live event is the marquee, not the earlier futures")
        XCTAssertEqual(story.badge, .live)
    }

    func testLiveEventWithoutOddsDoesNotBlockLaterUsableStory() throws {
        // A live event missing odds cannot render; the next usable item is used.
        let liveNoOdds = """
            { "type": "event", "score": 90,
              "data": { "id": 20, "home_team": "X", "away_team": "Y", "status": "live" } }
        """
        let feed = try items("{ \"items\": [ \(liveNoOdds), \(usableFutures) ] }")
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed))
        XCTAssertEqual(story.title, "2026 NBA Champion")
    }
}
