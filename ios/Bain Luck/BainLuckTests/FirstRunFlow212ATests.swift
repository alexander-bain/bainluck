import SwiftUI
#if os(iOS)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class TraitContainer212A: UIViewController {
    private let child: UIViewController
    private let overrideTraits: UITraitCollection

    init(child: UIViewController, traits: UITraitCollection) {
        self.child = child
        self.overrideTraits = traits
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(child.view)
        setOverrideTraitCollection(overrideTraits, forChild: child)
        child.didMove(toParent: self)
    }
}
#endif

@MainActor
final class FirstRunFlow212ATests: XCTestCase {

    private var iosRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private func source(_ relativePath: String) throws -> String {
        try String(contentsOf: iosRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static let fixtureNow: Date = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: "2026-11-23T22:30:00Z")!
    }()

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func makeFeedItemsFromFixtureJSON() throws -> [FeedItem] {
        let payload = """
        {
          "items": [
            {
              "type": "event",
              "score": 80,
              "data": {
                "id": 15353145,
                "sport": "basketball_nba",
                "home_team": "Philadelphia 76ers",
                "away_team": "Portland Trail Blazers",
                "status": "scheduled",
                "commence_time": "2026-11-24T00:00:00Z",
                "home_team_data": {"abbreviation": "PHI", "primary_color": "#006BB6"},
                "away_team_data": {"abbreviation": "POR", "primary_color": "#E03A3E"},
                "current_odds": {"home_probability": 0.575, "away_probability": 0.425, "home_rendered_percent": 58, "away_rendered_percent": 42}
              }
            },
            {
              "type": "event",
              "score": 79,
              "data": {
                "id": 15352950,
                "sport": "icehockey_nhl",
                "home_team": "Winnipeg Jets",
                "away_team": "Utah Mammoth",
                "status": "scheduled",
                "commence_time": "2026-11-24T00:30:00Z",
                "home_team_data": {"abbreviation": "WPG", "primary_color": "#041E42"},
                "away_team_data": {"abbreviation": "UTA", "primary_color": "#69B3E7"},
                "current_odds": {"home_probability": 0.505, "away_probability": 0.495, "home_rendered_percent": 51, "away_rendered_percent": 49}
              }
            },
            {
              "type": "event",
              "score": 78,
              "data": {
                "id": 15353183,
                "sport": "basketball_ncaab",
                "home_team": "Michigan Wolverines",
                "away_team": "Miami Hurricanes",
                "status": "live",
                "commence_time": "2026-11-23T22:00:00Z",
                "home_team_data": {"abbreviation": "MICH", "primary_color": "#00274C"},
                "away_team_data": {"abbreviation": "MIA", "primary_color": "#F47321"},
                "current_odds": {"home_probability": 0.64, "away_probability": 0.36, "home_rendered_percent": 64, "away_rendered_percent": 36}
              }
            },
            {
              "type": "event",
              "score": 77,
              "data": {
                "id": 15353478,
                "sport": "basketball_wncaab",
                "home_team": "Grand Canyon Antelopes",
                "away_team": "High Point Panthers",
                "status": "live",
                "commence_time": "2026-11-23T21:01:00Z",
                "home_team_data": {"abbreviation": "GCU", "primary_color": "#522398"},
                "away_team_data": {"abbreviation": "HPU", "primary_color": "#330072"},
                "current_odds": {"home_probability": 0.445, "away_probability": 0.555, "home_rendered_percent": 44, "away_rendered_percent": 56}
              }
            },
            {
              "type": "futures",
              "score": 75,
              "data": {
                "id": 68948432,
                "name": "MLB Playoffs: Team to advance to 2027 World Series",
                "sport": null,
                "llm_sport_category": "baseball",
                "status": "open",
                "top_outcomes": [{"id": 1, "name": "Milwaukee Brewers", "probability": 0.28, "rendered_percent": 28, "rank": 1, "movement": 0.02}]
              }
            },
            {
              "type": "futures",
              "score": 90,
              "data": {
                "id": 999901,
                "name": "Settled Future Should Be Filtered",
                "sport": null,
                "llm_sport_category": "entertainment",
                "status": "resolved",
                "winner": "Old Winner",
                "top_outcomes": [{"id": 2, "name": "Old Winner", "probability": 0.55, "rendered_percent": 55, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 88,
              "data": {
                "id": 109517,
                "name": "Top artist on Spotify in 2026?",
                "sport": null,
                "llm_sport_category": "entertainment",
                "status": "open",
                "top_outcomes": [{"id": 20, "name": "Bad Bunny", "probability": 0.965, "rendered_percent": 97, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 87,
              "data": {
                "id": 999902,
                "name": "Extremely Unlikely Outcome Below Five",
                "sport": null,
                "llm_sport_category": "tech",
                "status": "open",
                "top_outcomes": [{"id": 21, "name": "Rare Event", "probability": 0.03, "rendered_percent": 3, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 86,
              "data": {
                "id": 70733263,
                "name": "#1 Searched Person on Google 2026?",
                "sport": null,
                "llm_sport_category": "tech",
                "status": "open",
                "top_outcomes": [{"id": 22, "name": "Lindsay Clancy", "probability": 0.36, "rendered_percent": 36, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 85,
              "data": {
                "id": 68320839,
                "name": "Will a 7.0+ earthquake occur worldwide by November 30?",
                "sport": null,
                "llm_sport_category": "weather",
                "market_type": "yes_no",
                "status": "open",
                "top_outcomes": [{"id": 23, "name": "Yes", "probability": 0.315, "rendered_percent": 32, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 84,
              "data": {
                "id": 5455924,
                "name": "Will China invade Taiwan by December 31, 2027?",
                "sport": null,
                "llm_sport_category": "geopolitics",
                "market_type": "claim",
                "status": "open",
                "top_outcomes": [{"id": 24, "name": "Yes", "probability": 0.085, "rendered_percent": 9, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 74,
              "data": {
                "id": 109618,
                "name": "Sydney Sweeney and Scooter Braun: Engaged this year?",
                "sport": null,
                "llm_sport_category": "entertainment",
                "market_type": "claim",
                "status": "open",
                "top_outcomes": [{"id": 3, "name": "Yes", "probability": 0.285, "rendered_percent": 29, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 73,
              "data": {
                "id": 57574250,
                "name": "Fed Decision in December?",
                "sport": null,
                "llm_sport_category": "economics",
                "status": "open",
                "top_outcomes": [{"id": 4, "name": "Quarter-point increase", "probability": 0.929, "rendered_percent": 93, "rank": 1, "movement": 0.04}]
              }
            },
            {
              "type": "futures",
              "score": 72,
              "data": {
                "id": 109596,
                "name": "Best AI at the end of 2026?",
                "sport": null,
                "llm_sport_category": "tech",
                "status": "open",
                "top_outcomes": [{"id": 5, "name": "Gemini", "probability": 0.817, "rendered_percent": 82, "rank": 1, "movement": null}]
              }
            },
            {
              "type": "futures",
              "score": 71,
              "data": {
                "id": 20566635,
                "name": "Will Drake perform at Coachella 2027?",
                "sport": null,
                "llm_sport_category": "entertainment",
                "market_type": "yes_no",
                "status": "open",
                "top_outcomes": [
                  {"id": 10, "name": "No", "probability": 0.83, "rendered_percent": 83, "rank": 1, "movement": null},
                  {"id": 11, "name": "Yes", "probability": 0.17, "rendered_percent": 17, "rank": 2, "movement": null}
                ]
              }
            },
            {
              "type": "futures",
              "score": 70,
              "data": {
                "id": 63828305,
                "name": "Melbourne's wettest month of 2026?",
                "sport": null,
                "llm_sport_category": "weather",
                "status": "open",
                "top_outcomes": [{"id": 6, "name": "October", "probability": 0.91, "rendered_percent": 91, "rank": 1, "movement": null}]
              }
            }
          ],
          "total": 16,
          "limit": 40,
          "offset": 0,
          "has_more": false
        }
        """
        let resp = try makeDecoder().decode(FeedResponse.self, from: Data(payload.utf8))
        return resp.items
    }

    // MARK: - Launch Guard & Copy Rules

    func testNoNotificationOrTelemetryPromptBlocksFirstLaunchAndNoLegacyGridInFlow() throws {
        let appSrc = try source("Bain Luck/Bain_LuckApp.swift")
        let cleanApp = appSrc
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertFalse(cleanApp.contains("requestPermissionAfterDelay("))
        XCTAssertTrue(cleanApp.contains("FirstRunStorageKeys212A.onboardedKey"))

        let viewSrc = try source("Bain Luck/Views/FirstRunFlowView212A.swift")
        XCTAssertFalse(viewSrc.contains("Both of these"), "Four-button grid must be gone (Alex Pt 7)")
        XCTAssertFalse(viewSrc.lowercased().contains("% complete"), "No completion percentage bar (Alex Pt 10)")
        XCTAssertFalse(viewSrc.contains("Skip for now"), "Never show two skips on Screen 2D (Fable Send-back 6)")
        XCTAssertFalse(viewSrc.contains("Skip to topics"), "Use plain Skip wording matching next screen (Fable Send-back 8)")
        XCTAssertTrue(viewSrc.contains("Skip to Discover"))
        XCTAssertTrue(viewSrc.contains("Three quick picks, then you"))
        XCTAssertTrue(viewSrc.contains("Your picks decide what Discover shows first."))
        XCTAssertTrue(viewSrc.contains("We\\u{2019}ll put these first in Discover and My Stuff."))
        XCTAssertTrue(viewSrc.contains("Tap any you\\u{2019}d check. Both or neither is fine."))

        let arrivalSrc = try source("Bain Luck/Views/SharedLinkArrivalView212A.swift")
        XCTAssertFalse(arrivalSrc.contains("kickoff & swing"), "Do not say kickoff across all sports (Fable Send-back 8)")
        XCTAssertTrue(arrivalSrc.contains("Want start & swing updates?"))

        let modelsSrc = try source("Bain Luck/Utilities/FirstRunModels212A.swift")
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertFalse(modelsSrc.contains("\"pts"))
        XCTAssertFalse(modelsSrc.contains("Moved after inflation report"), "Invented captions must be deleted (Fable Pt 2)")
        XCTAssertFalse(modelsSrc.contains("Early awards frontrunner"), "Invented captions must be deleted (Fable Pt 2)")
        XCTAssertEqual(FirstRunCard212A.shiftText(points: 4), "▲ up 4 points")
        XCTAssertEqual(FirstRunCard212A.shiftText(points: 1), "▲ up 1 point")
        XCTAssertEqual(FirstRunCard212A.shiftText(points: -6), "▼ down 6 points")
    }

    func testLivePairsRejectsSettledRejectsSportsInNonSportsSlotsAndNoFakeFallbacks() throws {
        // Offline/empty feed never invents fake cards.
        XCTAssertEqual(FirstRunPair212A.buildPairs(from: []), [])

        let items = try makeFeedItemsFromFixtureJSON()
        let pairs = FirstRunPair212A.buildPairs(from: items, arrivedHeadline: nil, now: Self.fixtureNow)
        XCTAssertEqual(pairs.count, 3)
        XCTAssertNil(pairs[0].arrivedContextPill, "Cold open with no link must show no link pill")

        for pair in pairs {
            XCTAssertTrue(pair.topCard.isSports, "Every pair top card must be a game (Fable Send-back 2): \(pair.topCard)")
            XCTAssertFalse(pair.bottomCard.isSports, "Every pair bottom card must be non-sports (Fable Send-back 2): \(pair.bottomCard)")
        }

        let allCards = pairs.flatMap { [$0.topCard, $0.bottomCard] }
        for card in allCards {
            XCTAssertTrue((5...95).contains(card.percent), "Out-of-bounds % on card \(card.id): \(card.percent)")
        }
        XCTAssertFalse(allCards.contains { $0.id == "fut-999901" }, "Settled future must never appear")
        XCTAssertFalse(allCards.contains { $0.id == "ev-15353478" }, "Women's college basketball must not lead (Fable Send-back 2)")
        XCTAssertFalse(allCards.contains { $0.id == "fut-109517" }, ">95% card must never appear")
        XCTAssertFalse(allCards.contains { $0.id == "fut-999902" }, "<5% card must never appear")
        XCTAssertFalse(allCards.contains { $0.id == "fut-70733263" }, "Criminal defendant card must be filtered")
        XCTAssertFalse(allCards.contains { $0.id == "fut-68320839" }, "Earthquake disaster card must be filtered")
        XCTAssertFalse(allCards.contains { $0.id == "fut-5455924" }, "War/invasion card must be filtered")
        XCTAssertFalse(allCards.contains { $0.id == "fut-68948432" && !$0.isSports },
                       "Baseball future with sport == nil must never leak into non-sports slots")
        XCTAssertNil(allCards.first { $0.id == "fut-109618" }?.detailLine,
                     "Absent server hook_description must stay nil, zero invented captions")
        XCTAssertNotNil(pairs[0].topCard.workedMeaningLine)

        // Fable Send-back 1: Yes/No cards must always headline Yes, never No.
        let drakeJSON = """
        {
          "id": 20566635,
          "name": "Will Drake perform at Coachella 2027?",
          "sport": null,
          "llm_sport_category": "entertainment",
          "market_type": "yes_no",
          "status": "open",
          "top_outcomes": [
            {"id": 10, "name": "No", "probability": 0.83, "rendered_percent": 83, "rank": 1, "movement": null},
            {"id": 11, "name": "Yes", "probability": 0.17, "rendered_percent": 17, "rank": 2, "movement": null}
          ]
        }
        """
        let drakeFut = try makeDecoder().decode(FeedFuturesData.self, from: Data(drakeJSON.utf8))
        let drakeResolved = try XCTUnwrap(FirstRunPair212A.resolvePrimaryOutcome(for: drakeFut))
        XCTAssertEqual(drakeResolved.percent, 17)
        XCTAssertNil(drakeResolved.outcomeName)

        // Fable Send-back 3: untrusted category pills are omitted rather than mislabeled.
        XCTAssertNil(FirstRunPair212A.trustedNonSportsPill(categoryKey: "tech", title: "#1 Searched Person on Google 2026?"))
        XCTAssertNil(FirstRunPair212A.trustedNonSportsPill(categoryKey: "weather", title: "Will a 7.0+ earthquake occur worldwide by November 30?"))
        XCTAssertNil(FirstRunPair212A.trustedNonSportsPill(categoryKey: "culture", title: "Will Elon Musk visit Mars in his lifetime?"))
        XCTAssertEqual(FirstRunPair212A.trustedNonSportsPill(categoryKey: "tech", title: "Best AI at the end of 2026?"), "TECH")
        XCTAssertEqual(FirstRunPair212A.trustedNonSportsPill(categoryKey: "entertainment", title: "Oscar Winner: Best Picture"), "AWARDS")
        XCTAssertEqual(FirstRunPair212A.trustedNonSportsPill(categoryKey: "economics", title: "Fed Decision in December?"), "ECONOMY")
    }

    // MARK: - Alex Pt 7 (Card Tap Buttons), Pt 8 (Served Examples), Pt 9 + Fable Pt 3 (Discover Next Screen)

    func testCardTapToggleNextLabelServedExamplesAndNextScreenDiscoverBoost() async throws {
        let items = try makeFeedItemsFromFixtureJSON()
        let pairs = FirstRunPair212A.buildPairs(from: items, now: Self.fixtureNow)
        let examples = FirstRunServedExamples212A.buildExamples(from: items)

        XCTAssertTrue(examples.contains { $0.kind == .city && $0.query == "Philadelphia" }, "Served pro city missing: \(examples)")
        XCTAssertTrue(examples.contains { $0.kind == .school && $0.query == "Michigan" }, "Served school missing: \(examples)")
        XCTAssertGreaterThanOrEqual(examples.filter { $0.kind == .subject }.count, 2, "Need >=2 served non-sports examples: \(examples)")
        XCTAssertLessThanOrEqual(examples.count, 5)

        let suite = "FirstRun212A.Toggle.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
        let pins = PinManager(defaults: defaults, allowLegacyGuestPins: false, gameAlertsConfig: .live)
        let auth = AuthManager()

        let vm = FirstRunViewModel212A(
            initialPairs: pairs,
            initialExamples: examples,
            defaults: defaults,
            debounceNs: 0
        )

        // Screen 0: tap card selects, tap again clears (neither selected)
        vm.toggleCard(.top, forPairIndex: 0)
        XCTAssertEqual(vm.selectedSidesForStep(0), [.top])
        vm.toggleCard(.top, forPairIndex: 0)
        XCTAssertEqual(vm.selectedSidesForStep(0), [])

        // Both cards can be selected on Pair 1 -> advance to Pair 2 -> pick non-sports Economics & Entertainment
        vm.toggleCard(.bottom, forPairIndex: 0) // entertainment
        vm.advanceFromCurrentPair(followManager: follow, pinManager: pins)
        XCTAssertEqual(vm.stepIndex, 1)

        vm.advanceFromCurrentPair(followManager: follow, pinManager: pins) // neither on pair 2
        XCTAssertEqual(vm.stepIndex, 2)

        vm.toggleCard(.top, forPairIndex: 2)
        vm.toggleCard(.bottom, forPairIndex: 2)
        vm.advanceFromCurrentPair(followManager: follow, pinManager: pins)
        XCTAssertEqual(vm.stepIndex, 3)

        // Fable Point 3 one-line change summary after pairs
        let summary = try XCTUnwrap(vm.pairChangeSummaryLine)
        XCTAssertTrue(summary.hasPrefix("More ") && summary.hasSuffix(" in your Discover."), summary)

        var dismissed = false
        vm.finish(followManager: follow, pinManager: pins, authManager: auth) { dismissed = true }
        XCTAssertTrue(dismissed)
        XCTAssertTrue(defaults.bool(forKey: FirstRunStorageKeys212A.onboardedKey))

        let prefs = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertTrue(prefs.boostedCategories.contains("entertainment"))

        // Next Discover screen literally promotes picked non-sports category ahead of unpicked categories.
        let mlbItem = try XCTUnwrap(items.first { $0.futures?.id == 68948432 })
        let entItem = try XCTUnwrap(items.first { $0.futures?.id == 109618 })
        let weatherItem = try XCTUnwrap(items.first { $0.futures?.id == 63828305 })
        let orderedPairs = [
            ("baseball", mlbItem),
            ("entertainment", entItem),
            ("weather", weatherItem),
        ]
        let promoted = FirstRunDiscoverBoost212A.promotePreferredItems(orderedPairs, preferences: prefs) { entry, p in
            FirstRunDiscoverBoost212A.itemMatches(entry.1, category: entry.0, preferences: p)
        }
        XCTAssertEqual(promoted.first?.0, "entertainment", "Next screen must put picked subject FIRST in Discover")
        XCTAssertFalse(pins.pinnedFuturesIDs.isEmpty, "Picked future markets are also saved into My Stuff")
    }

    // MARK: - 359: A Plain Sentence Box Contract & Non-Sports Oscars / Inflation Search

    func testSentenceBoxContractAndFallbackPreservesQueryAndOscarsInflationSearch() async throws {
        let decoder = makeDecoder()
        let oscarsJSON = """
        {
          "query": "Oscars",
          "teams": [],
          "event_concepts": [],
          "results": [],
          "futures_families": [
            {
              "family_key": "story:oscars",
              "label": "Oscars",
              "headline": {"id": 6173044, "name": "Oscar Winner: Best Picture", "llm_sport_category": "entertainment", "category": "entertainment", "status": "open", "top_outcomes": [{"id": 31537937, "name": "The Odyssey", "probability": 0.515}]},
              "members": []
            }
          ],
          "futures": [
            {"id": 6173044, "name": "Oscar Winner: Best Picture", "category": "entertainment", "llm_sport_category": "entertainment", "status": "open", "top_outcomes": [{"id": 31537937, "name": "The Odyssey", "probability": 0.515}]}
          ],
          "collections": [
            {"type": "collection", "id": 422536482, "slug": "roundup-oscars-best-picture", "name": "The Odyssey leads Best Picture", "text": "The Odyssey leads Best Picture", "state": "published", "revision": 1743654066, "edition": {"kind": "theme"}, "game_count": 0, "question_count": 3, "matched_event_ids": [], "destination": {"kind": "container", "slug": "roundup-oscars-best-picture", "web": "/collections/roundup-oscars-best-picture", "api": "/api/containers/roundup-oscars-best-picture"}}
          ]
        }
        """
        let oscarsResp = try decoder.decode(SearchResponse.self, from: Data(oscarsJSON.utf8))
        let oscarsSuggestions = FirstRunSuggestion212A.fromEventSearchResponse(oscarsResp, query: "Oscars")
        XCTAssertEqual(oscarsSuggestions.map(\.id), ["family:story:oscars"], "Screen 2D must list only Oscars subject, zero sets/forecasts (Fable Send-back 4)")
        XCTAssertEqual(oscarsSuggestions.first?.chipDisplayText, "Oscars \u{00B7} Awards")

        let brownDirtyJSON = """
        {
          "query": "Brown",
          "teams": [{"id": 2392, "name": "Brown Bears", "sport_key": "basketball_ncaab"}, {"id": 562, "name": "Cleveland Browns", "sport_key": "americanfootball_nfl"}],
          "event_concepts": [],
          "results": [],
          "futures_families": [
            {"family_key": "entity:brown", "label": "Brown", "headline": {"id": 13490545, "name": "Mike Brown: Out by Date", "llm_sport_category": "basketball", "category": "basketball", "status": "open"}, "members": []},
            {"family_key": "story:regional_us_elections", "label": "US Local Elections", "headline": {"id": 1, "name": "CO-03 House election: Clifton Brown vote percent", "llm_sport_category": "politics", "category": "politics", "status": "open"}, "members": []}
          ],
          "futures": [{"id": 13490545, "name": "Mike Brown: Out by Date", "category": "basketball", "llm_sport_category": "basketball", "status": "open"}],
          "collections": [{"type": "collection", "id": 1, "slug": "nfl-week-10", "name": "NFL 2026 Week 10", "text": "NFL 2026 Week 10", "state": "published", "revision": 1, "game_count": 10, "question_count": 4998, "matched_event_ids": []}]
        }
        """
        let brownDirtyResp = try decoder.decode(SearchResponse.self, from: Data(brownDirtyJSON.utf8))
        let brownDirtySugs = FirstRunSuggestion212A.fromEventSearchResponse(brownDirtyResp, query: "Brown")
        XCTAssertEqual(brownDirtySugs.map(\.id), ["team:2392", "team:562"], "Brown query must list only teams, zero Set/forecast/election collisions")

        XCTAssertFalse(FirstRunSentenceMode359A.looksLikePlainSentence("Oscars"))
        XCTAssertFalse(FirstRunSentenceMode359A.looksLikePlainSentence("inflation"))
        XCTAssertTrue(FirstRunSentenceMode359A.looksLikePlainSentence("Celtics, Spurs, and inflation"))

        // 1. Sample sentence: clear items arrive selected, Spurs arrives as 2 unselected chips.
        let suite = "FirstRun359A.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            debounceNs: 0,
            sentenceTimeoutNs: 200_000_000,
            searchLocationTeams: { _ in [] },
            searchTeamsByName: { _ in [] },
            searchGlobal: { _ in oscarsResp },
            sentenceParser: { sentence in
                try await FirstRunSentenceSampleProvider359A.parseSampleSentence(sentence)
            }
        )

        vm.searchQuery = "Boston Celtics, Oscars, Spurs, and inflation"
        await vm.performSentenceParse(query: vm.searchQuery, followManager: follow)

        guard case .chips(let chips, let selectedIds, let isSample) = vm.sentenceState else {
            return XCTFail("Expected .chips state, got \(vm.sentenceState)")
        }
        XCTAssertTrue(isSample)
        XCTAssertTrue(selectedIds.contains("team:100"))
        XCTAssertTrue(selectedIds.contains("subject:oscars"))
        XCTAssertTrue(selectedIds.contains("subject:inflation"))
        XCTAssertEqual(chips.first { $0.id == "subject:oscars" }?.suggestion.chipDisplayText, "Oscars \u{00B7} Awards")
        XCTAssertEqual(chips.first { $0.id == "subject:inflation" }?.suggestion.chipDisplayText, "Inflation \u{00B7} Economy")
        XCTAssertFalse(selectedIds.contains("team:spurs-nba"), "Ambiguous Spurs chips must arrive unselected")
        XCTAssertFalse(selectedIds.contains("team:spurs-epl"), "Ambiguous Spurs chips must arrive unselected")

        // One tap removes a clear chip.
        let celticsChip = try XCTUnwrap(chips.first { $0.id == "team:100" })
        vm.toggleSentenceChip(celticsChip, followManager: follow)
        guard case .chips(_, let afterRemove, _) = vm.sentenceState else { return XCTFail("Lost chips state") }
        XCTAssertFalse(afterRemove.contains("team:100"))

        // 2. Timeout / error keeps typed words intact & falls back to ordinary search without "nothing matched".
        let timeoutVM = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            debounceNs: 0,
            sentenceTimeoutNs: 50_000_000,
            searchLocationTeams: { _ in [] },
            searchTeamsByName: { _ in [] },
            searchGlobal: { _ in oscarsResp },
            sentenceParser: { _ in
                try await Task.sleep(nanoseconds: 500_000_000)
                return FirstRunSentenceResponse359A(chips: [], isSampleData: true)
            }
        )
        let typed = "I mostly follow Oscars and macro"
        timeoutVM.searchQuery = typed
        await timeoutVM.performSentenceParse(query: typed, followManager: follow)

        XCTAssertEqual(timeoutVM.searchQuery, typed, "Error/timeout must preserve reader's words")
        if case .couldNotRead(let msg) = timeoutVM.sentenceState {
            XCTAssertFalse(msg.lowercased().contains("nothing matched"))
        } else {
            XCTFail("Expected .couldNotRead fallback state on timeout, got \(timeoutVM.sentenceState)")
        }
        XCTAssertFalse(timeoutVM.suggestions.isEmpty, "Fallback must run ordinary search below")
    }

    func testAppClipHandoffBridgeReadsSharedContainerAndRespectsTTL() throws {
        let suite = "FirstRun212A.ClipHandoff.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let now = Date()
        let fresh = FirstRunLinkHandoffBridge212A.StoredRecord(
            headline: "Trail Blazers at 76ers",
            recordedAt: now.addingTimeInterval(-60)
        )
        defaults.set(try encoder.encode(fresh), forKey: FirstRunLinkHandoffBridge212A.storageKey)
        XCTAssertEqual(
            FirstRunLinkHandoffBridge212A.readSharedContainerHeadline(defaults: defaults, now: now),
            "Trail Blazers at 76ers"
        )
        XCTAssertEqual(
            FirstRunLinkHandoffBridge212A.bannerText(headline: "Trail Blazers at 76ers"),
            "Started from your link \u{00B7} Trail Blazers at 76ers"
        )

        let expired = FirstRunLinkHandoffBridge212A.StoredRecord(
            headline: "Stale Game",
            recordedAt: now.addingTimeInterval(-25 * 3600)
        )
        defaults.set(try encoder.encode(expired), forKey: FirstRunLinkHandoffBridge212A.storageKey)
        XCTAssertNil(FirstRunLinkHandoffBridge212A.readSharedContainerHeadline(defaults: defaults, now: now))
    }

    func testTypeaheadPreservesQueryAndResultsAfterPickAndDisambiguatesSchoolTeams() async throws {
        let decoder = makeDecoder()
        let brownTeamResultsJSON = """
        [
          {"id": 2392, "name": "Brown Bears", "location": "Providence", "sport_key": "basketball_ncaab", "logo_url": null, "abbreviation": "BRWN", "sports": []},
          {"id": 19933, "name": "Brown Bears", "location": "Providence", "sport_key": "americanfootball_ncaaf", "logo_url": null, "abbreviation": "BRWN", "sports": []},
          {"id": 2690, "name": "Brown Bears", "location": "Providence", "sport_key": "basketball_wncaab", "logo_url": null, "abbreviation": "BRWN", "sports": []}
        ]
        """
        let emptyGlobalJSON = #"{"query":"brown","teams":[],"event_concepts":[],"results":[],"futures":[]}"#
        let brownTeams = try decoder.decode([TeamSearchResult].self, from: Data(brownTeamResultsJSON.utf8))
        let brownGlobal = try decoder.decode(SearchResponse.self, from: Data(emptyGlobalJSON.utf8))

        let suite = "FirstRun212A.Brown.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            debounceNs: 0,
            searchLocationTeams: { _ in [] },
            searchTeamsByName: { _ in brownTeams },
            searchGlobal: { _ in brownGlobal }
        )

        vm.searchQuery = "brown"
        await vm.performTypeahead(query: "brown")

        XCTAssertEqual(vm.suggestions.count, 3)
        let chipTexts = vm.suggestions.map(\.chipDisplayText)
        XCTAssertEqual(Set(chipTexts).count, 3, "Every Brown Bears team must carry a distinct sport label: \(chipTexts)")
        vm.toggleSuggestion(vm.suggestions[0], followManager: follow)
        XCTAssertTrue(vm.isPicked(vm.suggestions[0]))
        XCTAssertEqual(vm.searchQuery, "brown", "Search box must NOT clear after picking one team")
        XCTAssertEqual(vm.suggestions.count, 3, "Results must stay on screen after a pick")
        vm.toggleSuggestion(vm.suggestions[1], followManager: follow)
        XCTAssertEqual(vm.pickedItems.count, 2)
    }

    // MARK: - #13517 Width & Dynamic Type Audit + 390pt & 440pt Light/Dark Captures

    #if os(iOS)
    func testNoTeamNameTruncatedOn390And440AtDefaultAndAX5AndExportSheets() async throws {
        let decoder = makeDecoder()

        // Pure Boston fixture (NO Brown rows — answers Fable Point 6)
        let bostonFallbackJSON = """
        [
          {"id": 100, "name": "Boston Celtics", "location": "Boston", "sport_key": "basketball_nba", "logo_url": null, "abbreviation": "BOS", "sports": []},
          {"id": 574, "name": "Boston Bruins", "location": "Boston", "sport_key": "icehockey_nhl", "logo_url": null, "abbreviation": "BOS", "sports": []},
          {"id": 10709, "name": "Boston Red Sox", "location": "Boston", "sport_key": "baseball_mlb", "logo_url": null, "abbreviation": "BOS", "sports": []},
          {"id": 511, "name": "New England Revolution", "location": "Boston", "sport_key": "soccer_usa_mls", "logo_url": null, "abbreviation": "NE", "sports": []},
          {"id": 15342, "name": "Boston College Eagles", "location": "Boston College", "sport_key": "americanfootball_ncaaf", "logo_url": null, "abbreviation": "BC", "sports": []},
          {"id": 2659, "name": "Boston Univ. Terriers", "location": "Boston University", "sport_key": "basketball_ncaab", "logo_url": null, "abbreviation": "BU", "sports": []}
        ]
        """
        let pureBostonTeams = try decoder.decode([TeamSearchResult].self, from: Data(bostonFallbackJSON.utf8))
        let pureBostonGlobal = try decoder.decode(
            SearchResponse.self,
            from: Data(#"{"query":"boston","teams":[],"event_concepts":[],"results":[],"futures":[]}"#.utf8)
        )

        // 1) Prove ZERO truncation (#13517) across 390pt and 440pt, Default and AX5 on pure Boston
        let matrix: [(tag: String, width: CGFloat, size: DynamicTypeSize)] = [
            ("13517-boston-390-default", 390, .large),
            ("13517-boston-390-ax5", 390, .accessibility5),
            ("13517-boston-440-default", 440, .large),
            ("13517-boston-440-ax5", 440, .accessibility5),
        ]
        for cfg in matrix {
            let suite = "FirstRun212A.13517.\(UUID().uuidString)"
            let defaults = UserDefaults(suiteName: suite)!
            defer { defaults.removePersistentDomain(forName: suite) }
            let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
            let vm = FirstRunViewModel212A(
                initialStep: 3,
                defaults: defaults,
                debounceNs: 0,
                searchLocationTeams: { _ in pureBostonTeams },
                searchTeamsByName: { _ in pureBostonTeams },
                searchGlobal: { _ in pureBostonGlobal }
            )
            vm.searchQuery = "Boston"
            await vm.performTypeahead(query: "Boston")
            vm.toggleSuggestion(vm.suggestions[0], followManager: follow) // Boston Celtics
            vm.toggleSuggestion(vm.suggestions[3], followManager: follow) // New England Revolution

            let ocr = try await renderAndOCR(
                view: FirstRunFlowView212A(viewModelForTest: vm)
                    .environment(\.followManager295A, follow),
                filename: "\(cfg.tag).png",
                width: cfg.width,
                height: cfg.size.isAccessibilitySize ? 1400 : 900,
                colorScheme: .light,
                dynamicTypeSize: cfg.size
            )
            let truncs = ocr.filter { $0.contains("…") || $0.contains("...") }
            let joined = ocr.joined(separator: " ")
            XCTAssertEqual(truncs, [], "Truncated text at \(cfg.tag): \(truncs) (all=\(ocr))")
            XCTAssertFalse(joined.contains("Brown Bears"), "Boston search must never list Brown Bears (Fable Pt 6)")
            XCTAssertTrue(joined.contains("New England") && joined.contains("Revolution"), "Missing full New England Revolution at \(cfg.tag): \(ocr)")
            XCTAssertTrue(joined.contains("Boston") && joined.contains("Celtics"), "Missing full Boston Celtics at \(cfg.tag): \(ocr)")
        }

        // 2) Export full 390pt & 440pt Light/Dark set when requested
        let env = ProcessInfo.processInfo.environment
        guard let exportDir = env["EXPORT_212A_RENDER_DIR"] ?? env["TEST_RUNNER_EXPORT_212A_RENDER_DIR"] ?? env["SIMCTL_CHILD_EXPORT_212A_RENDER_DIR"],
              !exportDir.isEmpty else {
            return
        }

        let fixDir = env["LIVE_212A_FIXTURES_DIR"] ?? env["TEST_RUNNER_LIVE_212A_FIXTURES_DIR"] ?? env["SIMCTL_CHILD_LIVE_212A_FIXTURES_DIR"] ?? ""
        func loadFixture(_ name: String) -> Data? {
            guard !fixDir.isEmpty else { return nil }
            return try? Data(contentsOf: URL(fileURLWithPath: fixDir).appendingPathComponent(name))
        }

        // Load real live feed items (or minimal test fallback if fixture env unset)
        let liveFeedItems: [FeedItem] = try {
            var items: [FeedItem] = []
            if let d1 = loadFixture("feed_discover.json"),
               let r1 = try? decoder.decode(FeedResponse.self, from: d1) {
                items.append(contentsOf: r1.items)
            }
            if let d2 = loadFixture("feed_sports.json"),
               let r2 = try? decoder.decode(FeedResponse.self, from: d2) {
                items.append(contentsOf: r2.items)
            }
            if items.isEmpty {
                items = try makeFeedItemsFromFixtureJSON()
            }
            return items
        }()
        let liveSearchSugs: [SearchSuggestionEntry212A] = {
            if let d = loadFixture("search_suggestions.json"),
               let r = try? decoder.decode(SearchSuggestionsResponse212A.self, from: d) {
                return r.suggestions
            }
            return []
        }()

        let liveColdPairs = FirstRunPair212A.buildPairs(from: liveFeedItems, arrivedHeadline: nil, now: Self.fixtureNow)
        let liveLinkPairs = FirstRunPair212A.buildPairs(from: liveFeedItems, arrivedHeadline: "Trail Blazers at 76ers", now: Self.fixtureNow)
        let liveExamples = FirstRunServedExamples212A.buildExamples(from: liveFeedItems, searchSuggestions: liveSearchSugs)
        XCTAssertEqual(liveColdPairs.count, 3)
        XCTAssertGreaterThanOrEqual(liveExamples.count, 4)

        let arrivalEvent: EventDetail = try {
            if let d = loadFixture("arrival_event.json"),
               let ev = try? decoder.decode(EventDetail.self, from: d) {
                return ev
            }
            return try decoder.decode(EventDetail.self, from: Data(#"{"id":15353145,"sport":"basketball_nba","home_team":"Philadelphia 76ers","away_team":"Portland Trail Blazers","commence_time":"2026-11-24T00:00:00Z","status":"scheduled","current_odds":{"home_probability":0.575,"away_probability":0.425,"home_rendered_percent":58,"away_rendered_percent":42}}"#.utf8))
        }()
        let arrivalHistory: EventHistoryResponse? = {
            guard let d = loadFixture("arrival_history.json") else { return nil }
            return try? decoder.decode(EventHistoryResponse.self, from: d)
        }()

        let oscarsResp = (try? loadFixture("search_oscars.json").flatMap { try? decoder.decode(SearchResponse.self, from: $0) })
            ?? pureBostonGlobal
        let inflationResp = (try? loadFixture("search_inflation.json").flatMap { try? decoder.decode(SearchResponse.self, from: $0) })
            ?? pureBostonGlobal
        let bostonLoc = (try? loadFixture("loc_boston.json").flatMap { try? decoder.decode([TeamSearchResult].self, from: $0) })
            ?? pureBostonTeams
        let bostonSearchTeams = (try? loadFixture("teams_boston.json").flatMap { try? decoder.decode([TeamSearchResult].self, from: $0) })
            ?? pureBostonTeams
        let bostonGlobal = (try? loadFixture("search_boston.json").flatMap { try? decoder.decode(SearchResponse.self, from: $0) })
            ?? pureBostonGlobal
        let brownTeams = (try? loadFixture("teams_brown.json").flatMap { try? decoder.decode([TeamSearchResult].self, from: $0) })
            ?? []
        let brownGlobal = (try? loadFixture("search_brown.json").flatMap { try? decoder.decode(SearchResponse.self, from: $0) })
            ?? pureBostonGlobal

        for width in [CGFloat(390), CGFloat(440)] {
            let wTag = Int(width)
            for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                // 01: Screen 1A Shared Link Arrival reading App Group handoff ("Started from your link · ...")
                let arrivalHeadline = "\(arrivalEvent.awayTeam) at \(arrivalEvent.homeTeam)"
                _ = try await renderAndOCR(
                    view: SharedLinkArrivalView212A(
                        event: arrivalEvent,
                        preloadedHistory: arrivalHistory,
                        arrivedHeadline: arrivalHeadline,
                        moreCards: [
                            liveLinkPairs[0].bottomCard,
                            liveLinkPairs[1].topCard,
                            liveLinkPairs[1].bottomCard,
                        ],
                        onOpenFullGame: {},
                        onOpenDiscover: {}
                    ),
                    filename: "v2-01-arrival-1a-\(suffix)-\(wTag).png",
                    width: width,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .large
                )

                // 02: Cold Open with NO link (Screen 2A)
                do {
                    let s = "FirstRun212A.Cold.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(initialPairs: liveColdPairs, initialExamples: liveExamples, initialStep: 0, defaults: d)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-02-cold-open-2a-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 03: Pair 2B with direct card tap selected (check + blue border + "Next")
                do {
                    let s = "FirstRun212A.Pair2.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(initialPairs: liveColdPairs, initialExamples: liveExamples, initialStep: 1, defaults: d)
                    vm.toggleCard(.bottom, forPairIndex: 1)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-03-pair-2b-selected-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 04: Pair 2C (two non-sports real live cards)
                do {
                    let s = "FirstRun212A.Pair3.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(initialPairs: liveColdPairs, initialExamples: liveExamples, initialStep: 2, defaults: d)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-04-pair-2c-nonsports-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 05: Failure State #1 (Live pairs failed to load — honest retry/skip, zero fake cards)
                do {
                    let s = "FirstRun212A.Fail1.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: [],
                        initialExamples: [],
                        initialStep: 0,
                        defaults: d,
                        feedLoader: { throw URLError(.notConnectedToInternet) },
                        sportsFeedLoader: { throw URLError(.notConnectedToInternet) }
                    )
                    await vm.loadLivePairsIfNeeded(forceReload: true)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-05-pairs-failure-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 06: Screen 2D Empty Box + Calm Still 5 Tappable Examples (0 picks -> Single "Skip to Discover")
                do {
                    let s = "FirstRun212A.Ex.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(initialPairs: liveColdPairs, initialExamples: liveExamples, initialStep: 3, defaults: d)
                    let ocr2d = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm)
                            .environment(\.followManager295A, f),
                        filename: "v2-06-2d-examples-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                    let joined2d = ocr2d.joined(separator: " ")
                    XCTAssertFalse(joined2d.contains("Skip for now"), "Screen 2D must never show two skips")
                    XCTAssertTrue(joined2d.contains("Skip to Discover"), "Screen 2D with 0 picks should show single Skip to Discover CTA")
                }

                // 07: Screen 2D "Oscars" (Subject only, Pair summary + Go to Discover)
                do {
                    let s = "FirstRun212A.Oscars.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: liveColdPairs,
                        initialExamples: liveExamples,
                        initialStep: 0,
                        defaults: d,
                        debounceNs: 0,
                        searchLocationTeams: { _ in [] },
                        searchTeamsByName: { _ in [] },
                        searchGlobal: { _ in oscarsResp }
                    )
                    vm.toggleCard(.bottom, forPairIndex: 0)
                    vm.advanceFromCurrentPair(followManager: f)
                    vm.advanceFromCurrentPair(followManager: f)
                    vm.advanceFromCurrentPair(followManager: f)
                    vm.searchQuery = "Oscars"
                    await vm.performTypeahead(query: "Oscars")
                    if let first = vm.suggestions.first { vm.toggleSuggestion(first, followManager: f) }
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-07-2d-oscars-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 08: Screen 2D "inflation" (Fable Pt 5)
                do {
                    let s = "FirstRun212A.Inflation.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: liveColdPairs,
                        initialExamples: liveExamples,
                        initialStep: 3,
                        defaults: d,
                        debounceNs: 0,
                        searchLocationTeams: { _ in [] },
                        searchTeamsByName: { _ in [] },
                        searchGlobal: { _ in inflationResp }
                    )
                    vm.searchQuery = "inflation"
                    await vm.performTypeahead(query: "inflation")
                    if let first = vm.suggestions.first { vm.toggleSuggestion(first, followManager: f) }
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-08-2d-inflation-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 09: Screen 2D "Boston" pure live results (Fable Pt 6 + #13517)
                do {
                    let s = "FirstRun212A.Boston.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: liveColdPairs,
                        initialExamples: liveExamples,
                        initialStep: 3,
                        defaults: d,
                        debounceNs: 0,
                        searchLocationTeams: { _ in bostonLoc },
                        searchTeamsByName: { _ in bostonSearchTeams },
                        searchGlobal: { _ in bostonGlobal }
                    )
                    vm.searchQuery = "Boston"
                    await vm.performTypeahead(query: "Boston")
                    if let first = vm.suggestions.first { vm.toggleSuggestion(first, followManager: f) }
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-09-2d-boston-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 09b: Screen 2D "Brown" distinct school sports (NCAAB / NCAAF / WNCAAB)
                do {
                    let s = "FirstRun212A.Brown.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: liveColdPairs,
                        initialExamples: liveExamples,
                        initialStep: 3,
                        defaults: d,
                        debounceNs: 0,
                        searchLocationTeams: { _ in [] },
                        searchTeamsByName: { _ in brownTeams },
                        searchGlobal: { _ in brownGlobal }
                    )
                    vm.searchQuery = "Brown"
                    await vm.performTypeahead(query: "Brown")
                    if vm.suggestions.count >= 2 {
                        vm.toggleSuggestion(vm.suggestions[0], followManager: f)
                        vm.toggleSuggestion(vm.suggestions[1], followManager: f)
                    }
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-09b-2d-brown-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 10: 359: A Sentence Waiting State
                do {
                    let s = "FirstRun212A.Wait.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(initialPairs: liveColdPairs, initialExamples: liveExamples, initialStep: 3, defaults: d)
                    vm.searchQuery = "Boston Celtics, Oscars, Spurs, and inflation"
                    vm.setSentenceStateForPreview(.waiting)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-10-359a-waiting-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 11: 359: A Sentence Chips Confirmation (Sample preview: clear selected + Spurs 2 unselected)
                do {
                    let s = "FirstRun212A.Chips.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: liveColdPairs,
                        initialExamples: liveExamples,
                        initialStep: 3,
                        defaults: d,
                        debounceNs: 0,
                        sentenceParser: { sentence in
                            try await FirstRunSentenceSampleProvider359A.parseSampleSentence(sentence)
                        }
                    )
                    vm.searchQuery = "Boston Celtics, Oscars, Spurs, and inflation"
                    await vm.performSentenceParse(query: vm.searchQuery, followManager: f)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-11-359a-chips-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 12: Failure State #2 — 359: A Could-Not-Read Fallback keeping typed text + regular search below
                do {
                    let s = "FirstRun212A.CouldNotRead.\(UUID().uuidString)"
                    let d = UserDefaults(suiteName: s)!
                    let f = FollowManager295A(defaults: d, initialSubjects: [])
                    let vm = FirstRunViewModel212A(
                        initialPairs: liveColdPairs,
                        initialExamples: liveExamples,
                        initialStep: 3,
                        defaults: d,
                        debounceNs: 0,
                        sentenceTimeoutNs: 20_000_000,
                        searchLocationTeams: { _ in [] },
                        searchTeamsByName: { _ in [] },
                        searchGlobal: { _ in oscarsResp },
                        sentenceParser: { _ in throw URLError(.timedOut) }
                    )
                    vm.searchQuery = "I mostly follow Oscars and macro"
                    await vm.performSentenceParse(query: vm.searchQuery, followManager: f)
                    _ = try await renderAndOCR(
                        view: FirstRunFlowView212A(viewModelForTest: vm).environment(\.followManager295A, f),
                        filename: "v2-12-359a-couldnotread-\(suffix)-\(wTag).png",
                        width: width,
                        height: 844,
                        colorScheme: scheme,
                        dynamicTypeSize: .large
                    )
                }

                // 13: 4A Contextual Alerts Ask (Fable Point 6 Dark "Turn on" fix)
                _ = try await renderAndOCR(
                    view: VStack {
                        Spacer()
                        GameAlertsPinPromptSheet13084(onTurnOn: {}, onNotNow: {})
                        Spacer()
                    }
                    .background(DS.surface),
                    filename: "v2-13-4a-alert-ask-\(suffix)-\(wTag).png",
                    width: width,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .large
                )
            }
        }
    }

    private func renderAndOCR<V: View>(
        view: V,
        filename: String,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) async throws -> [String] {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiCategory: UIContentSizeCategory = dynamicTypeSize.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large
        let auth = AuthManager()
        let renderDefaults = UserDefaults(suiteName: "FirstRun212A.Render.\(UUID().uuidString)")!
        let pins = PinManager(defaults: renderDefaults, serverLoad: { PinsResponse(events: [], futures: []) }, serverSync: { _, _, _ in })
        let root = view
            .frame(width: width, height: height, alignment: .topLeading)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environmentObject(NavigationCoordinator())
            .environmentObject(pins)
            .environmentObject(auth)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: uiStyle),
            UITraitCollection(preferredContentSizeCategory: uiCategory),
        ])
        let host = hostForMeasurement(root, at: dynamicTypeSize)
        let container = TraitContainer212A(child: host, traits: traits)
        container.view.backgroundColor = colorScheme == .dark ? UIColor(red: 0.059, green: 0.067, blue: 0.082, alpha: 1) : .systemGroupedBackground
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.rootViewController = container
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<8 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 40_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: container.view.bounds, format: fmt).image { _ in
            _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }

        let env = ProcessInfo.processInfo.environment
        if let outDir = env["EXPORT_212A_RENDER_DIR"] ?? env["TEST_RUNNER_EXPORT_212A_RENDER_DIR"] ?? env["SIMCTL_CHILD_EXPORT_212A_RENDER_DIR"],
           !outDir.isEmpty,
           let png = image.pngData() {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try png.write(to: dirURL.appendingPathComponent(filename))
        }

        guard let cg = image.cgImage else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
    #endif
}
