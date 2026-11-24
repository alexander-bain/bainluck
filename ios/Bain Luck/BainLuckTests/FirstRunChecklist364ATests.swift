import SwiftUI
#if os(iOS)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class TraitContainer364A: UIViewController {
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
final class FirstRunChecklist364ATests: XCTestCase {

    private static let fixtureNow: Date = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: "2026-11-23T22:30:00Z")!
    }()

    private var iosRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private func source(_ relativePath: String) throws -> String {
        try String(contentsOf: iosRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func makeSampleFeedItems() throws -> [FeedItem] {
        let json = """
        {
          "items": [
            {
              "type": "event",
              "score": 90,
              "data": {
                "id": 15353145,
                "sport": "basketball_nba",
                "home_team": "Philadelphia 76ers",
                "away_team": "Portland Trail Blazers",
                "status": "scheduled",
                "commence_time": "2026-11-24T00:00:00Z",
                "home_team_data": {"abbreviation": "PHI", "primary_color": "#006BB6"},
                "away_team_data": {"abbreviation": "POR", "primary_color": "#E03A3E"},
                "prematch_odds": {"home_probability": 0.52, "away_probability": 0.48},
                "current_odds": {"home_probability": 0.58, "away_probability": 0.42, "home_rendered_percent": 58, "away_rendered_percent": 42}
              }
            },
            {
              "type": "event",
              "score": 85,
              "data": {
                "id": 15353018,
                "sport": "basketball_ncaab",
                "home_team": "San Francisco Dons",
                "away_team": "Nevada Wolf Pack",
                "status": "live",
                "commence_time": "2026-11-23T21:37:24Z",
                "home_team_data": {"abbreviation": "SF", "primary_color": "#00543C"},
                "away_team_data": {"abbreviation": "NEV", "primary_color": "#003366"},
                "prematch_odds": {"home_probability": 0.27, "away_probability": 0.73},
                "current_odds": {"home_probability": 0.60, "away_probability": 0.40, "home_rendered_percent": 60, "away_rendered_percent": 40}
              }
            },
            {
              "type": "bundle",
              "score": 84,
              "data": {
                "id": "b-odd",
                "title": "Visiting Mars in his lifetime is at 12%",
                "kind": "roundup",
                "image_url": "https://example.com/mars.jpg",
                "collection_ref": {"slug": "machinery-elon-musk-side-quests", "name": "Musk side quests"},
                "roundup": {
                  "kicker": "ODD · SIDE QUESTS",
                  "tag": "ODD",
                  "footer": "See all 6",
                  "rows": [
                    {"market_id": 108218, "label": "Visiting Mars in his lifetime", "probability": 0.12, "rendered_percent": 12}
                  ],
                  "machinery_card": {
                    "slug": "machinery-elon-musk-side-quests",
                    "form_id": "benchmark_strip",
                    "kicker": "ODD · SIDE QUESTS",
                    "title": "Musk side quests",
                    "subtitle": "Long-horizon milestones.",
                    "footer": "Open set",
                    "rows": [
                      {"market_id": 108218, "name": "Visiting Mars in his lifetime", "rendered_percent": 12},
                      {"market_id": 109412, "name": "Purchase Ryanair", "rendered_percent": 5}
                    ]
                  }
                },
                "items": [
                  {
                    "type": "futures",
                    "score": 84,
                    "data": {
                      "id": 108218,
                      "name": "Will Elon Musk visit Mars in his lifetime?",
                      "sport": null,
                      "llm_sport_category": "culture",
                      "market_type": "claim",
                      "status": "open",
                      "top_outcomes": [
                        {"id": 1, "name": "No", "probability": 0.88, "rendered_percent": 88, "rank": 1},
                        {"id": 2, "name": "Yes", "probability": 0.12, "rendered_percent": 12, "rank": 2}
                      ]
                    }
                  }
                ]
              }
            },
            {
              "type": "futures",
              "score": 83,
              "data": {
                "id": 57792807,
                "name": "NCAA Football: 2026 Heisman Award Winner",
                "sport": "americanfootball_ncaaf",
                "llm_sport_category": "sports",
                "status": "open",
                "top_outcomes": [{"id": 9, "name": "Jeremiah Smith", "probability": 0.82, "rendered_percent": 82, "rank": 1}]
              }
            },
            {
              "type": "bundle",
              "score": 83,
              "data": {
                "id": "b-oscars",
                "title": "The Odyssey leads Best Picture at 52%",
                "kind": "roundup",
                "image_url": "https://example.com/cinema.jpg",
                "collection_ref": {"slug": "machinery-oscars-best-picture", "name": "Oscars 2027 Best Picture"},
                "roundup": {
                  "kicker": "THE OSCARS · BEST PICTURE",
                  "tag": "ENTERTAINMENT",
                  "footer": "Open set",
                  "rows": [
                    {"market_id": 6173044, "label": "The Odyssey", "probability": 0.52, "rendered_percent": 52}
                  ],
                  "machinery_card": {
                    "slug": "machinery-oscars-best-picture",
                    "form_id": "paired_stage_bars",
                    "kicker": "THE OSCARS · BEST PICTURE",
                    "title": "The Odyssey leads Best Picture at 52%",
                    "footer": "Open set",
                    "rows": []
                  },
                  "paired_metric_set": {
                    "set_id": "oscars-2027-best-picture",
                    "category": "entertainment",
                    "kicker": "OSCARS 2027 · BEST PICTURE",
                    "title": "The Odyssey leads Best Picture at 52%",
                    "subtitle": "Nomination vs win odds.",
                    "stage_1_label": "Nom",
                    "stage_2_label": "Win",
                    "stage_1_market": "Oscar nominees: Best Picture",
                    "stage_2_market": "Oscar Winner: Best Picture",
                    "entries": [
                      {
                        "subject_key": "film:odyssey",
                        "subject": "The Odyssey",
                        "detail": "Christopher Nolan",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.94,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.52,
                        "stage_2_rendered_percent": 52
                      }
                    ]
                  }
                },
                "items": [
                  {
                    "type": "futures",
                    "score": 83,
                    "data": {
                      "id": 6173044,
                      "name": "Oscar Winner: Best Picture",
                      "sport": null,
                      "llm_sport_category": "entertainment",
                      "status": "open",
                      "image_url": "https://example.com/cinema.jpg",
                      "top_outcomes": [{"id": 10, "name": "The Odyssey", "probability": 0.52, "rendered_percent": 52, "rank": 1}]
                    }
                  }
                ]
              }
            },
            {
              "type": "bundle",
              "score": 82,
              "data": {
                "id": "b-bond",
                "title": "Next James Bond film",
                "kind": "roundup",
                "image_url": "https://example.com/bond.jpg",
                "collection_ref": {"slug": "machinery-next-james-bond", "name": "Next James Bond"},
                "roundup": {
                  "kicker": "ENTERTAINMENT · JAMES BOND",
                  "tag": "ENTERTAINMENT",
                  "footer": "Open set",
                  "rows": [
                    {"market_id": 108237, "label": "James Bond Theme · Raye", "probability": 0.42, "rendered_percent": 42}
                  ],
                  "machinery_card": {
                    "slug": "machinery-next-james-bond",
                    "form_id": "sibling_fields_grid",
                    "kicker": "ENTERTAINMENT · JAMES BOND",
                    "title": "Raye leads James Bond Theme at 42%",
                    "footer": "Open set",
                    "rows": [
                      {"market_id": 108237, "name": "James Bond Theme · Raye", "rendered_percent": 42},
                      {"market_id": 108263, "name": "Bond girl · Margaret Qualley", "rendered_percent": 31}
                    ]
                  }
                },
                "items": []
              }
            },
            {
              "type": "bundle",
              "score": 81,
              "data": {
                "id": "b-champs",
                "title": "Heisman & NBA MVP",
                "kind": "roundup",
                "collection_ref": {"slug": "machinery-big-championships-2027", "name": "Big championships"},
                "roundup": {
                  "kicker": "SPORTS · CHAMPIONSHIPS",
                  "tag": "SPORTS",
                  "footer": "Open set",
                  "rows": [
                    {"market_id": 57792807, "label": "Jeremiah Smith · Heisman", "probability": 0.82, "rendered_percent": 82}
                  ],
                  "machinery_card": {
                    "slug": "machinery-big-championships-2027",
                    "form_id": "benchmark_strip",
                    "kicker": "SPORTS · CHAMPIONSHIPS",
                    "title": "Jeremiah Smith leads Heisman at 82%",
                    "footer": "Open set",
                    "rows": [
                      {"market_id": 57792807, "name": "Jeremiah Smith · Heisman", "rendered_percent": 82},
                      {"market_id": 66031970, "name": "Victor Wembanyama · MVP", "rendered_percent": 51}
                    ]
                  }
                },
                "items": []
              }
            },
            {
              "type": "bundle",
              "score": 80,
              "data": {
                "id": "theme:story:middle_east_conflict:10228658",
                "title": "Middle East Conflict",
                "kind": "theme",
                "items": [
                  {
                    "type": "futures",
                    "score": 80,
                    "data": {
                      "id": 10228658,
                      "name": "Prime Minister of Israel after the 2026 election?",
                      "sport": null,
                      "llm_sport_category": "politics",
                      "status": "open",
                      "top_outcomes": [{"id": 21, "name": "Gadi Eizenkot", "probability": 0.50, "rendered_percent": 50, "rank": 1}]
                    }
                  }
                ]
              }
            },
            {
              "type": "bundle",
              "score": 80,
              "data": {
                "id": "b-over95",
                "title": "Bad Bunny at 97%",
                "kind": "roundup",
                "collection_ref": {"slug": "machinery-2026-summed-up", "name": "2026 summed up"},
                "roundup": {
                  "kicker": "ENTERTAINMENT",
                  "tag": "ENTERTAINMENT",
                  "footer": "Open set",
                  "rows": [{"market_id": 109517, "label": "Bad Bunny", "probability": 0.97, "rendered_percent": 97}],
                  "machinery_card": {
                    "slug": "machinery-2026-summed-up",
                    "form_id": "benchmark_strip",
                    "kicker": "ENTERTAINMENT",
                    "title": "Bad Bunny leads at 97%",
                    "footer": "Open set",
                    "rows": [{"market_id": 109517, "name": "Bad Bunny", "rendered_percent": 97}]
                  }
                },
                "items": []
              }
            },
            {
              "type": "futures",
              "score": 79,
              "data": {
                "id": 113364,
                "name": "Next French Presidential Election",
                "sport": null,
                "llm_sport_category": "politics",
                "status": "open",
                "top_outcomes": [{"id": 20, "name": "Marine Le Pen", "probability": 0.46, "rendered_percent": 46, "rank": 1}]
              }
            }
          ],
          "total": 8,
          "limit": 40,
          "offset": 0,
          "has_more": false
        }
        """
        return try makeDecoder().decode(FeedResponse.self, from: Data(json.utf8)).items
    }

    func testChecklistStateTransitionsAndRowOrdering() {
        var state = FirstRunChecklistState364A.untouched
        XCTAssertEqual(FirstRunChecklistRowID364A.allCases.map(\.title), [
            "Look anything up",
            "Follow what you care about",
            "See what the world expects",
            "Keep it on all your devices",
            "Get a heads-up",
        ])
        XCTAssertFalse(state.isSyncLitUp, "Row 4 starts dim before any follow or set pick")
        XCTAssertTrue(state.showsInMyStuff)
        XCTAssertEqual(state.progressText, "0 of 5 done")

        state.followedCount = 1
        state.completedRows.insert(.follow)
        XCTAssertTrue(state.isSyncLitUp, "Row 4 must light up once reader follows or picks something")
        XCTAssertEqual(state.savedCount, 1)
        XCTAssertEqual(state.progressText, "1 of 5 done")

        var setOnlyState = FirstRunChecklistState364A.untouched
        setOnlyState.selectedSetSlugs.insert("machinery-oscars-best-picture")
        XCTAssertTrue(setOnlyState.isSyncLitUp)
        XCTAssertEqual(setOnlyState.savedCount, 1)

        state.dismissedFromMyStuff = true
        XCTAssertFalse(state.showsInMyStuff)
        XCTAssertFalse(FirstRunChecklistState364A.allDone.showsInMyStuff)
    }

    func testLiveExtractionObeysYesSideRangeGrimAndLookupContracts() throws {
        let items = try makeSampleFeedItems()
        let content = FirstRunChecklistExtractor364A.buildContent(from: items, now: Self.fixtureNow)

        XCTAssertEqual(content.lookupExamples.count, 3)
        XCTAssertEqual(content.lookupExamples.map(\.kind), [.game, .award, .election])
        let gameExample = try XCTUnwrap(content.lookupExamples.first { $0.kind == .game })
        XCTAssertEqual(gameExample.title, "San Francisco tonight", "Point 3: Row 1 chip skips rankedGames[0] reserved for Biggest game")
        let awardExample = try XCTUnwrap(content.lookupExamples.first { $0.kind == .award })
        XCTAssertEqual(awardExample.id, "lookup-award-6173044", "Non-sports award (Oscars) preferred and concisely titled")
        XCTAssertEqual(awardExample.title, "The Odyssey \u{00B7} Oscars", "Fix a: award chip names top outcome with contest")
        let electionExample = try XCTUnwrap(content.lookupExamples.first { $0.kind == .election })
        XCTAssertEqual(electionExample.id, "lookup-election-113364", "Conflict bundles must never supply Row 1 election example")
        XCTAssertEqual(electionExample.title, "Marine Le Pen \u{00B7} French Election", "Fix a: election chip names candidate with race")
        XCTAssertNil(content.syncRowPreview?.imageUrl, "Row 4 starts without an unrelated teaser thumbnail before any pick")
        for row in FirstRunChecklistRowID364A.allCases {
            XCTAssertNil(content.rowPreviews[row]?.percentText, "Fix a: never render a bare floating percent beside checklist row \(row)")
        }
        XCTAssertFalse((content.setsRowPreview?.subtitle ?? "").contains("tap sets"), "Point 6: remove internal 'tap sets' copy")
        for ex in content.lookupExamples {
            XCTAssertTrue((5...95).contains(ex.percent), "Out-of-bounds % on lookup example \(ex)")
        }

        XCTAssertEqual(content.startWithTonight.count, 3)
        XCTAssertEqual(content.startWithTonight.map(\.slotLabel), ["Biggest game", "Biggest mover", "Odd one"])
        let biggestGame = try XCTUnwrap(content.startWithTonight.first { $0.slotLabel == "Biggest game" })
        XCTAssertEqual(biggestGame.subtitle, "NBA", "Point 6: middle line shows league only, without repeating team")
        let row1Sub = content.lookupRowPreview?.subtitle ?? ""
        XCTAssertFalse(row1Sub.contains(gameExample.title), "Point 7: Row 1 subtitle must not duplicate chip 1 (\(row1Sub))")
        let oddCard = try XCTUnwrap(content.startWithTonight.first { $0.slotLabel == "Odd one" })
        XCTAssertEqual(oddCard.percent, 12, "Yes/No odd card must show Yes side (12%), never No (88%)")
        XCTAssertEqual(oddCard.title, "Elon Musk visits Mars in his lifetime", "Point 5: declarative odd-one statement")
        XCTAssertFalse(oddCard.title.contains("?"), "Point 5: no question mark on odd-one statement")
        XCTAssertTrue(oddCard.subtitle.isEmpty, "Point 5: no stray Yes subtitle under odd-one")
        XCTAssertTrue(oddCard.subjectLabel.isEmpty, "Point 5: no duplicate Yes label on odd-one card")
        for card in content.startWithTonight {
            XCTAssertTrue((5...95).contains(card.percent))
            if card.slotLabel != "Odd one" {
                XCTAssertFalse(card.subjectLabel.isEmpty)
            }
            if let delta = card.deltaText {
                XCTAssertFalse(delta.contains("pts"))
                XCTAssertTrue(
                    delta.contains("since pregame") || delta.contains("since your last visit"),
                    "Fix b: delta copy must name its window (\(delta))"
                )
            }
        }

        XCTAssertEqual(content.discoverSets.count, 4)
        XCTAssertFalse(content.discoverSets.contains { $0.slug == "machinery-2026-summed-up" }, ">95% sets must be excluded")
        let forms = Set(content.discoverSets.map { $0.machineryCard.formId })
        XCTAssertTrue(forms.contains(.pairedStageBars))
        XCTAssertTrue(forms.contains(.siblingFieldsGrid))
        XCTAssertTrue(forms.contains(.benchmarkStrip))
        XCTAssertEqual(content.subjectArtByCategory["awards"], "https://example.com/cinema.jpg")
    }

    func testOpeningOddsNeverServesAsUnwindowedDeltaBaselineFixB() throws {
        let json = """
        {
          "items": [
            {
              "type": "event",
              "score": 90,
              "data": {
                "id": 999001,
                "sport": "basketball_nba",
                "home_team": "Los Angeles Lakers",
                "away_team": "LA Clippers",
                "status": "live",
                "commence_time": "2026-11-23T22:00:00Z",
                "opening_odds": {"home_probability": 0.35, "away_probability": 0.65},
                "current_odds": {"home_probability": 0.87, "away_probability": 0.13, "home_rendered_percent": 87, "away_rendered_percent": 13}
              }
            }
          ],
          "total": 1, "limit": 10, "offset": 0, "has_more": false
        }
        """
        let suite = "Checklist364A.OpeningBaseline.\(UUID().uuidString)"
        let def = UserDefaults(suiteName: suite)!
        defer { def.removePersistentDomain(forName: suite) }

        let items = try makeDecoder().decode(FeedResponse.self, from: Data(json.utf8)).items
        let contentNoBaseline = FirstRunChecklistExtractor364A.buildContent(from: items, defaults: def, now: Self.fixtureNow)
        XCTAssertNil(contentNoBaseline.startWithTonight.first?.deltaText, "Fix b: opening_odds without prematch/last-visit never emits delta")

        // Now record a real last-visit reading
        MyStuffVisitLedger295A.recordObservedReadings(["event:999001": 0.72], defaults: def)
        MyStuffVisitLedger295A.rotateSessionIfNeeded(defaults: def)
        let contentLastVisit = FirstRunChecklistExtractor364A.buildContent(from: items, defaults: def, now: Self.fixtureNow)
        let delta = try XCTUnwrap(contentLastVisit.startWithTonight.first?.deltaText)
        XCTAssertTrue(delta.contains("since your last visit"), "Recorded last-visit reading supplies explicit window: \(delta)")
    }

    func testChecklistStorePersistenceNonSportsFollowAndFiveRowsEndToEnd() async throws {
        let suite = "Checklist364A.Store.\(UUID().uuidString)"
        let def = UserDefaults(suiteName: suite)!
        defer { def.removePersistentDomain(forName: suite) }

        // 1. Persisted store state + set picks -> FirstRunPreferences212A Discover boost
        let store1 = FirstRunChecklistStore364A(defaults: def)
        XCTAssertEqual(store1.state, .untouched)
        let items = try makeSampleFeedItems()
        let content = FirstRunChecklistExtractor364A.buildContent(from: items, defaults: def, now: Self.fixtureNow)
        let oscarSlug = try XCTUnwrap(content.discoverSets.first { $0.category.contains("OSCARS") }?.slug)
        store1.setSelectedSetSlugs([oscarSlug], from: content.discoverSets)
        store1.markCompleted(.lookUp)

        let store2 = FirstRunChecklistStore364A(defaults: def)
        XCTAssertTrue(store2.state.completedRows.contains(.lookUp))
        XCTAssertTrue(store2.state.completedRows.contains(.exploreSets))
        XCTAssertTrue(store2.state.isSyncLitUp)
        XCTAssertEqual(store2.state.progressText, "2 of 5 done")
        let prefs = FirstRunPreferences212A.load(defaults: def)
        XCTAssertTrue(prefs.boostedCategories.contains("entertainment"), "Set pick must persist into Discover boost preferences")

        // Dismiss persists in My Stuff
        store2.dismissFromMyStuff()
        let store3 = FirstRunChecklistStore364A(defaults: def)
        XCTAssertFalse(store3.state.showsInMyStuff)

        // 2. Non-sports subject following + route resolution
        let followMgr = FollowManager295A(defaults: def, initialSubjects: [])
        let oscarSubject = FollowedSubject295A.subject(
            slug: "story:oscars",
            name: "Oscars",
            affinityCategory: "entertainment",
            marketId: 6173044
        )
        XCTAssertTrue(followMgr.toggle(oscarSubject))
        XCTAssertEqual(oscarSubject.route, .futuresDetail(id: 6173044))
        let categorySubject = FollowedSubject295A.subject(slug: "economy", name: "Fed & Rates", affinityCategory: "economics")
        XCTAssertEqual(categorySubject.route, .economics)

        // Re-loaded FollowManager preserves non-sports follow
        let reloadedFollowMgr = FollowManager295A(defaults: def)
        XCTAssertTrue(reloadedFollowMgr.isFollowing(oscarSubject))

        // SearchResponse topical families carry followable non-sports FollowedSubject
        let famJSON = #"{"query":"Oscars","teams":[],"event_concepts":[],"results":[],"futures_families":[{"family_key":"story:oscars","label":"Oscars","headline":{"id":6173044,"name":"Oscar Winner: Best Picture","llm_sport_category":"entertainment","category":"entertainment","status":"open","top_outcomes":[{"id":10,"name":"One Battle After Another","probability":0.51,"rendered_percent":51,"rank":1}]},"members":[]}],"futures":[]}"#
        let famResp = try makeDecoder().decode(SearchResponse.self, from: Data(famJSON.utf8))
        let followSuggestions = FirstRunSuggestion212A.fromEventSearchResponse(famResp, query: "Oscars")
        let oscarSug = try XCTUnwrap(followSuggestions.first { $0.id == "family:story:oscars" })
        XCTAssertNotNil(oscarSug.followedSubject, "Row 2 non-sports subjects must be directly followable in FollowManager295A")

        // 3. Row 1 lookup VM live search mapping
        let lookupVM = FirstRunLookupViewModel364A(debounceNs: 0) { _ in famResp }
        await lookupVM.performLookupNow(query: "Oscars", subjectArt: content.subjectArtByCategory)
        XCTAssertEqual(lookupVM.results.count, 1)
        XCTAssertEqual(lookupVM.results.first?.subjectLabel, "One Battle After Another")
        XCTAssertEqual(lookupVM.results.first?.percent, 51)
        XCTAssertEqual(lookupVM.results.first?.route, .futuresDetail(id: 6173044))
        XCTAssertFalse(lookupVM.results.first?.subtitle.contains("Live served") ?? true)

        // 4. Row 5 Not Now never flips enabled; Turn On opts in cleanly
        let alertsPref = GameAlertsPreference13083(defaults: def)
        XCTAssertFalse(alertsPref.isEnabled)
        _ = await alertsPref.optInAndRequestPermission(requestPermission: { .authorized })
        XCTAssertTrue(alertsPref.isEnabled)
    }

    func testSourceGuardsRespectDecision364AAndSixFableFixes() throws {
        let viewSrc = try source("Bain Luck/Views/FirstRunChecklistView364A.swift")
        let rootSrc = try source("Bain Luck/Views/FirstRunChecklistRootView364A.swift")
        let modelsSrc = try source("Bain Luck/Utilities/FirstRunChecklistModels364A.swift")
        let sentenceSrc = try source("Bain Luck/Utilities/FirstRunSentenceBox359A.swift")
        let signInSrc = try source("Bain Luck/Views/EarnedSignInCard212A.swift")

        XCTAssertTrue(modelsSrc.contains("Probability is the very guide of life."))
        XCTAssertTrue(modelsSrc.contains("Joseph Butler, 1736"))
        XCTAssertTrue(rootSrc.contains("FirstRunChecklistRootView364A"))
        XCTAssertFalse(viewSrc.contains("Your picks decide what Discover shows first"))
        XCTAssertFalse(viewSrc.lowercased().contains("want to personalis"))
        XCTAssertFalse(viewSrc.lowercased().contains("want to personaliz"))
        XCTAssertFalse(viewSrc.contains("Skip for now"))

        // Point 4 (2026-11-24 Fable): one word "follow" (never pins, saved, Add/Added, Save & back)
        XCTAssertTrue(signInSrc.contains("Keep what you follow on iPad, the web and a new phone"))
        XCTAssertFalse(signInSrc.lowercased().contains("your pins"))
        XCTAssertTrue(viewSrc.contains("everything you follow lives in My Stuff."))
        XCTAssertFalse(viewSrc.contains("all saved in My Stuff"))
        XCTAssertFalse(viewSrc.contains("Save & back"))
        XCTAssertFalse(viewSrc.contains("? \"Added\" : \"Add\""))
        XCTAssertFalse(viewSrc.contains("savedCount)) saved"))
        XCTAssertTrue(viewSrc.contains("savedCount)) followed"))
        XCTAssertTrue(viewSrc.contains("picked ? \"Following\" : \"Follow\""))
        XCTAssertTrue(viewSrc.contains("dynamicTypeSize < .accessibility4"))

        // Fix c: zero lab words
        XCTAssertFalse(viewSrc.contains("Live served"))
        XCTAssertFalse(viewSrc.contains("Sample preview"))
        XCTAssertFalse(viewSrc.contains("waiting on server address"))
        XCTAssertFalse(viewSrc.contains("LIVE EXAMPLE"))
        XCTAssertFalse(sentenceSrc.contains("Sample preview"))
        XCTAssertFalse(sentenceSrc.contains("waiting on server address"))

        // Fix d: lookup examples hidden when query is non-empty
        XCTAssertTrue(viewSrc.contains("trimmedQuery.isEmpty"))

        // Fix f: small copy fixes + Fable #13593 review guards
        XCTAssertTrue(viewSrc.contains("or just type what you like"))
        XCTAssertFalse(viewSrc.contains("or a plain note"))
        XCTAssertTrue(viewSrc.contains("We\\u{2019}ll ask before any alert"))
        XCTAssertFalse(viewSrc.contains("prompt appears only after you tap Turn on"))
        XCTAssertFalse(FirstRunSentenceMode359A.isEnabledInBuild, "Point 1: sentence box stays off in build until Alex rules")
        XCTAssertTrue(sentenceSrc.contains("static let isEnabledInBuild: Bool = false"))
        XCTAssertFalse(modelsSrc.contains("\"Open forecast\""))
        XCTAssertFalse(modelsSrc.contains("tap sets"))
    }

    func testSentenceBoxOffInBuildUsesPlainTypeaheadInstead() async throws {
        XCTAssertFalse(FirstRunSentenceMode359A.isEnabledInBuild)
        let suite = "Checklist364A.SentenceOff.\(UUID().uuidString)"
        let def = UserDefaults(suiteName: suite)!
        defer { def.removePersistentDomain(forName: suite) }

        final class SentenceSpy: @unchecked Sendable {
            var called = false
        }
        let famJSON = #"{"query":"Boston Celtics, Oscars","teams":[],"event_concepts":[],"results":[],"futures_families":[{"family_key":"story:oscars","label":"Oscars","headline":{"id":6173044,"name":"Oscar Winner: Best Picture","llm_sport_category":"entertainment","category":"entertainment","status":"open"},"members":[]}],"futures":[]}"#
        let teamsJSON = #"[{"id":100,"name":"Boston Celtics","location":"Boston","sport_key":"basketball_nba","logo_url":null,"abbreviation":"BOS","sports":[]}]"#
        let decodedResp = try makeDecoder().decode(SearchResponse.self, from: Data(famJSON.utf8))
        let teams = try makeDecoder().decode([TeamSearchResult].self, from: Data(teamsJSON.utf8))
        let spy = SentenceSpy()
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: def,
            debounceNs: 0,
            searchLocationTeams: { _ in [] },
            searchTeamsByName: { _ in teams },
            searchGlobal: { _ in decodedResp },
            sentenceParser: { s in
                spy.called = true
                return try await FirstRunSentenceSampleProvider359A.parseSampleSentence(s)
            }
        )
        let followMgr = FollowManager295A(defaults: def, initialSubjects: [])
        vm.searchQuery = "Boston Celtics, Oscars, Spurs, and inflation"
        vm.onQueryChange(followManager: followMgr)
        try await Task.sleep(nanoseconds: 120_000_000)

        XCTAssertFalse(spy.called, "Sentence parser must stay dark while isEnabledInBuild == false")
        if case .idle = vm.sentenceState {
            // Expected while sentence box is gated off in the build.
        } else {
            XCTFail("Expected sentenceState == .idle, got \(vm.sentenceState)")
        }
        XCTAssertFalse(vm.suggestions.isEmpty, "Plain lookup continues serving suggestions")
    }

    func testMyStuffNeverPlacesFinishedGameUnderNextForYou() async throws {
        let suite = "Checklist364A.NoFinalNext.\(UUID().uuidString)"
        let def = UserDefaults(suiteName: suite)!
        defer { def.removePersistentDomain(forName: suite) }

        let finishedJSON = #"{"id":14780582,"sport":"americanfootball_nfl","sport_name":"NFL","home_team":"Washington Commanders","away_team":"Cincinnati Bengals","status":"completed","commence_time":"2026-11-23T18:00:00Z","home_score":22,"away_score":20}"#
        let upcomingJSON = #"{"id":15353145,"sport":"basketball_nba","sport_name":"NBA","home_team":"Philadelphia 76ers","away_team":"Portland Trail Blazers","status":"scheduled","commence_time":"2026-11-24T00:00:00Z"}"#
        let finishedEvent = try makeDecoder().decode(FeedEventData.self, from: Data(finishedJSON.utf8))
        let upcomingEvent = try makeDecoder().decode(FeedEventData.self, from: Data(upcomingJSON.utf8))
        XCTAssertEqual(EventState.section(of: finishedEvent), .finished)
        XCTAssertEqual(EventState.section(of: upcomingEvent), .upcoming)

        // 1. Preloaded snapshot path must strip finished events from nextEvents into movedEntries.
        var snap = MyStuffLandingViewModel295A.PreloadedSnapshot()
        snap.nextEvents = [(event: finishedEvent, awayVerified: true), (event: upcomingEvent, awayVerified: true)]
        let preloadedVM = MyStuffLandingViewModel295A(defaults: def, preloaded: snap)
        XCTAssertEqual(preloadedVM.nextEvents.map(\.event.id), [15353145])
        XCTAssertTrue(preloadedVM.movedEntries.contains(where: { $0.id == "moved-final-14780582" }))

        // 2. Refresh hydration path (including non-sports .subject) must never put finished games in nextEvents.
        let emptyFeed = try makeDecoder().decode(FeedResponse.self, from: Data(#"{"items":[],"total":0,"limit":12,"offset":0,"has_more":false}"#.utf8))
        let liveVM = MyStuffLandingViewModel295A(
            defaults: def,
            subjectHydrator: { _ in
                [MyStuffLandingViewModel295A.HydratedSubjectPack(events: [(finishedEvent, true), (upcomingEvent, true)], markets: [])]
            },
            discoverFetcher: { emptyFeed }
        )
        await liveVM.refresh(
            followedSubjects: [FollowedSubject295A.subject(slug: "story:oscars", name: "Oscars", affinityCategory: "entertainment")],
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil
        )
        XCTAssertEqual(liveVM.nextEvents.map(\.event.id), [15353145])
        XCTAssertTrue(liveVM.movedEntries.contains(where: { $0.id == "moved-final-14780582" }))
    }

    func testStartWithTonightShowsAllThreeCardsWhenPregameMoverExists() throws {
        let items = try makeSampleFeedItems()
        let content = FirstRunChecklistExtractor364A.buildContent(from: items, now: Self.fixtureNow)
        XCTAssertEqual(content.startWithTonight.map(\.slotLabel), ["Biggest game", "Biggest mover", "Odd one"])
        XCTAssertEqual(content.startWithTonight.first(where: { $0.slotLabel == "Biggest mover" })?.deltaText, "▲ up 33 points since pregame")
    }

    func testAwayFavoriteUsesAwayTeamCrestOnRows1_2_5AndBiggestGame() throws {
        let json = """
        {
          "items": [
            {
              "type": "event",
              "score": 95,
              "data": {
                "id": 9101,
                "sport": "americanfootball_nfl",
                "home_team": "Cleveland Browns",
                "away_team": "Baltimore Ravens",
                "status": "scheduled",
                "commence_time": "2026-11-24T00:00:00Z",
                "home_team_data": {"abbreviation": "CLE", "primary_color": "#311D00", "logo_small": "https://example.com/cle.png"},
                "away_team_data": {"abbreviation": "BAL", "primary_color": "#241773", "logo_small": "https://example.com/bal.png"},
                "current_odds": {"home_probability": 0.34, "away_probability": 0.66, "home_rendered_percent": 34, "away_rendered_percent": 66}
              }
            },
            {
              "type": "event",
              "score": 94,
              "data": {
                "id": 9102,
                "sport": "basketball_nba",
                "home_team": "Charlotte Hornets",
                "away_team": "Boston Celtics",
                "status": "scheduled",
                "commence_time": "2026-11-24T00:15:00Z",
                "home_team_data": {"abbreviation": "CHA", "primary_color": "#00788C", "logo_small": "https://example.com/cha.png"},
                "away_team_data": {"abbreviation": "BOS", "primary_color": "#007A33", "logo_small": "https://example.com/bos.png"},
                "current_odds": {"home_probability": 0.28, "away_probability": 0.72, "home_rendered_percent": 28, "away_rendered_percent": 72}
              }
            },
            {
              "type": "event",
              "score": 93,
              "data": {
                "id": 9103,
                "sport": "basketball_nba",
                "home_team": "Detroit Pistons",
                "away_team": "Milwaukee Bucks",
                "status": "scheduled",
                "commence_time": "2026-11-24T00:30:00Z",
                "home_team_data": {"abbreviation": "DET", "primary_color": "#C8102E", "logo_small": "https://example.com/det.png"},
                "away_team_data": {"abbreviation": "MIL", "primary_color": "#00471B", "logo_small": "https://example.com/mil.png"},
                "current_odds": {"home_probability": 0.41, "away_probability": 0.59, "home_rendered_percent": 41, "away_rendered_percent": 59}
              }
            },
            {
              "type": "event",
              "score": 92,
              "data": {
                "id": 9104,
                "sport": "basketball_ncaab",
                "home_team": "Oklahoma Sooners",
                "away_team": "Pittsburgh Panthers",
                "status": "scheduled",
                "commence_time": "2026-11-24T01:00:00Z",
                "home_team_data": {"abbreviation": "OU", "primary_color": "#841617", "logo_small": "https://example.com/ou.png"},
                "away_team_data": {"abbreviation": "PITT", "primary_color": "#003594", "logo_small": "https://example.com/pitt.png"},
                "current_odds": {"home_probability": 0.44, "away_probability": 0.56, "home_rendered_percent": 44, "away_rendered_percent": 56}
              }
            },
            {
              "type": "event",
              "score": 91,
              "data": {
                "id": 9105,
                "sport": "icehockey_nhl",
                "home_team": "Buffalo Sabres",
                "away_team": "Boston Bruins",
                "status": "scheduled",
                "commence_time": "2026-11-24T01:30:00Z",
                "home_team_data": {"abbreviation": "BUF", "primary_color": "#003087", "logo_small": "https://example.com/buf.png"},
                "away_team_data": {"abbreviation": "BOS", "primary_color": "#FFB81C", "logo_small": "https://example.com/bruins.png"},
                "current_odds": {"home_probability": 0.38, "away_probability": 0.62, "home_rendered_percent": 38, "away_rendered_percent": 62}
              }
            }
          ],
          "total": 5, "limit": 10, "offset": 0, "has_more": false
        }
        """
        let items = try makeDecoder().decode(FeedResponse.self, from: Data(json.utf8)).items
        let content = FirstRunChecklistExtractor364A.buildContent(from: items, now: Self.fixtureNow)

        let biggest = try XCTUnwrap(content.startWithTonight.first { $0.slotLabel == "Biggest game" })
        XCTAssertEqual(biggest.subjectLabel, "Ravens")
        XCTAssertEqual(biggest.subtitle, "NFL")
        XCTAssertEqual(biggest.imageUrl, "https://example.com/bal.png")

        let gameChip = try XCTUnwrap(content.lookupExamples.first { $0.kind == .game })
        XCTAssertEqual(gameChip.title, "Celtics tonight")
        XCTAssertEqual(gameChip.imageUrl, "https://example.com/bos.png")

        XCTAssertEqual(content.followRowPreview?.subtitle.hasPrefix("Bucks tonight 59%"), true)
        XCTAssertEqual(content.followRowPreview?.imageUrl, "https://example.com/mil.png")

        XCTAssertEqual(content.alertsRowPreview?.subtitle.hasPrefix("Bruins tonight 62%"), true)
        XCTAssertEqual(content.alertsRowPreview?.imageUrl, "https://example.com/bruins.png")

        XCTAssertEqual(content.lookupRowPreview?.subtitle, "No account \u{00B7} Pittsburgh tonight 56%")
        XCTAssertEqual(content.lookupRowPreview?.imageUrl, "https://example.com/pitt.png")
        XCTAssertFalse((content.lookupRowPreview?.subtitle ?? "").contains(gameChip.title))

        let searchResp = try makeDecoder().decode(SearchResponse.self, from: Data("""
        {
          "query": "Pittsburgh",
          "teams": [],
          "event_concepts": [],
          "futures": [],
          "results": [
            {
              "id": 9104,
              "sport": "basketball_ncaab",
              "home_team": "Oklahoma Sooners",
              "away_team": "Pittsburgh Panthers",
              "status": "scheduled",
              "commence_time": "2026-11-24T01:00:00Z",
              "home_team_data": {"abbreviation": "OU", "primary_color": "#841617", "logo_small": "https://example.com/ou.png"},
              "away_team_data": {"abbreviation": "PITT", "primary_color": "#003594", "logo_small": "https://example.com/pitt.png"},
              "current_odds": {"home_probability": 0.44, "away_probability": 0.56, "home_rendered_percent": 44, "away_rendered_percent": 56}
            }
          ]
        }
        """.utf8))
        let searchRows = FirstRunChecklistExtractor364A.extractLookupResults(from: searchResp, now: Self.fixtureNow)
        XCTAssertEqual(searchRows.first?.subjectLabel, "Pittsburgh")
        XCTAssertEqual(searchRows.first?.imageUrl, "https://example.com/pitt.png")
    }

    func testBostonTypeaheadLeadsWithCityTeamsIncludingPatriotsAndRevolution() async throws {
        let suite = "Checklist364A.Boston.\(UUID().uuidString)"
        let def = UserDefaults(suiteName: suite)!
        defer { def.removePersistentDomain(forName: suite) }

        let byLocationJSON = """
        [
          {"id":574,"name":"Boston Bruins","location":"Boston","sport_key":"icehockey_nhl","logo_url":null,"abbreviation":"BOS","sports":[]},
          {"id":14547,"name":"Boston Cannons","location":"Boston","sport_key":"lacrosse_pll","logo_url":null,"abbreviation":"BOS","sports":[]},
          {"id":100,"name":"Boston Celtics","location":"Boston","sport_key":"basketball_nba","logo_url":null,"abbreviation":"BOS","sports":[]},
          {"id":10709,"name":"Boston Red Sox","location":"Boston","sport_key":"baseball_mlb","logo_url":null,"abbreviation":"BOS","sports":[]},
          {"id":1203,"name":"Boston College Eagles","location":"Boston College","sport_key":"basketball_ncaab","logo_url":null,"abbreviation":"BC","sports":[]},
          {"id":19359,"name":"Boston Bruins","location":null,"sport_key":"icehockey_nhl_preseason","logo_url":null,"abbreviation":"BOS","sports":[]},
          {"id":11,"name":"New England Patriots","location":"New England","sport_key":"americanfootball_nfl","logo_url":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png","abbreviation":"NE","sports":[]},
          {"id":20,"name":"New England Revolution","location":"New England Revolution","sport_key":"soccer_usa_mls","logo_url":"https://a.espncdn.com/i/teamlogos/soccer/500/189.png","abbreviation":"NE","sports":[]}
        ]
        """
        let byNameJSON = """
        [
          {"id":574,"name":"Boston Bruins","location":"Boston","sport_key":"icehockey_nhl","logo_url":null,"abbreviation":"BOS","sports":[]},
          {"id":100,"name":"Boston Celtics","location":"Boston","sport_key":"basketball_nba","logo_url":null,"abbreviation":"BOS","sports":[]}
        ]
        """
        let emptySearch = try makeDecoder().decode(SearchResponse.self, from: Data(#"{"query":"Boston","teams":[],"event_concepts":[],"results":[],"futures":[]}"#.utf8))
        let locTeams = try makeDecoder().decode([TeamSearchResult].self, from: Data(byLocationJSON.utf8))
        let nameTeams = try makeDecoder().decode([TeamSearchResult].self, from: Data(byNameJSON.utf8))

        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: def,
            debounceNs: 0,
            searchLocationTeams: { _ in locTeams },
            searchTeamsByName: { _ in nameTeams },
            searchGlobal: { _ in emptySearch },
            sentenceParser: nil
        )
        vm.searchQuery = "Boston"
        await vm.performTypeahead(query: "Boston")

        let topFiveNames = Array(vm.suggestions.prefix(5).map(\.name))
        XCTAssertEqual(topFiveNames, [
            "New England Patriots",
            "Boston Celtics",
            "Boston Red Sox",
            "Boston Bruins",
            "New England Revolution",
        ])
        XCTAssertFalse(vm.suggestions.contains { $0.teamId == 19359 }, "Preseason duplicates must not clog city lookup results")
    }

    func testMyStuffRefreshNeverAddsUnfollowedDiscoverEventToNextForYou() async throws {
        let suite = "Checklist364A.OnlyFollowedNext.\(UUID().uuidString)"
        let def = UserDefaults(suiteName: suite)!
        defer { def.removePersistentDomain(forName: suite) }

        let celticsUpcomingJSON = """
        {"id":15359901,"sport":"basketball_nba","sport_name":"NBA","home_team":"Boston Celtics","away_team":"Toronto Raptors","status":"scheduled","commence_time":"2026-11-25T00:30:00Z","current_odds":{"home_probability":0.71,"away_probability":0.29,"home_rendered_percent":71,"away_rendered_percent":29}}
        """
        let unfollowedFeedJSON = """
        {"items":[{"type":"event","score":95,"data":{"id":15359999,"sport":"icehockey_nhl","sport_name":"NHL","home_team":"Edmonton Oilers","away_team":"Vegas Golden Knights","status":"scheduled","commence_time":"2026-11-25T02:00:00Z","current_odds":{"home_probability":0.55,"away_probability":0.45,"home_rendered_percent":55,"away_rendered_percent":45}}}],"total":1,"limit":12,"offset":0,"has_more":false}
        """
        let celticsEvent = try makeDecoder().decode(FeedEventData.self, from: Data(celticsUpcomingJSON.utf8))
        let unfollowedDiscover = try makeDecoder().decode(FeedResponse.self, from: Data(unfollowedFeedJSON.utf8))

        let vm = MyStuffLandingViewModel295A(
            defaults: def,
            subjectHydrator: { subjects in
                XCTAssertEqual(subjects.map(\.name), ["Boston Celtics"])
                return [MyStuffLandingViewModel295A.HydratedSubjectPack(events: [(celticsEvent, true)], markets: [])]
            },
            discoverFetcher: { unfollowedDiscover }
        )
        await vm.refresh(
            followedSubjects: [FollowedSubject295A.team(slug: "100", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba")],
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil
        )
        XCTAssertEqual(vm.nextEvents.map(\.event.id), [15359901])
        XCTAssertFalse(vm.nextEvents.contains { $0.event.id == 15359999 }, "Unfollowed Discover game must never appear under Next for you")
    }

    #if os(iOS)
    func testRender364ASheetAndOCR() async throws {
        let env = ProcessInfo.processInfo.environment
        let exportDir = env["EXPORT_364A_RENDER_DIR"] ?? env["TEST_RUNNER_EXPORT_364A_RENDER_DIR"] ?? env["SIMCTL_CHILD_EXPORT_364A_RENDER_DIR"] ?? ""
        let fixDir = env["LIVE_212A_FIXTURES_DIR"] ?? env["TEST_RUNNER_LIVE_212A_FIXTURES_DIR"] ?? env["SIMCTL_CHILD_LIVE_212A_FIXTURES_DIR"] ?? ""
        let imgCacheDir = env["IMG_CACHE_364A_DIR"] ?? env["TEST_RUNNER_364A_IMG_CACHE_DIR"] ?? env["SIMCTL_CHILD_IMG_CACHE_364A_DIR"] ?? ""

        let decoder = makeDecoder()
        func loadFixture(_ name: String) -> Data? {
            guard !fixDir.isEmpty else { return nil }
            return try? Data(contentsOf: URL(fileURLWithPath: fixDir).appendingPathComponent(name))
        }

        var feedItems: [FeedItem] = []
        if let d1 = loadFixture("feed_discover.json"),
           let r1 = try? decoder.decode(FeedResponse.self, from: d1) {
            feedItems.append(contentsOf: r1.items)
        }
        if let d2 = loadFixture("feed_sports.json"),
           let r2 = try? decoder.decode(FeedResponse.self, from: d2) {
            feedItems.append(contentsOf: r2.items)
        }
        if feedItems.isEmpty {
            feedItems = try makeSampleFeedItems()
        }

        let content = FirstRunChecklistExtractor364A.buildContent(from: feedItems, now: Self.fixtureNow)
        XCTAssertGreaterThanOrEqual(content.discoverSets.count, 4, "Need 4-6 sets in real forms")

        var preloaded: [String: PairedPlatformImage] = [:]
        if !imgCacheDir.isEmpty {
            let mapPath = URL(fileURLWithPath: imgCacheDir).appendingPathComponent("index.json")
            if let mapData = try? Data(contentsOf: mapPath),
               let mapping = try? JSONDecoder().decode([String: String].self, from: mapData) {
                for (remoteURL, fileName) in mapping {
                    let imgURL = URL(fileURLWithPath: imgCacheDir).appendingPathComponent(fileName)
                    if let img = UIImage(contentsOfFile: imgURL.path) {
                        preloaded[remoteURL] = img
                    }
                }
            }
        }

        // Default fast assertion even when sheet export is off (390pt Light untouched screen)
        let widthsToRender: [CGFloat] = exportDir.isEmpty ? [390] : [390, 440]
        let schemesToRender: [(ColorScheme, String)] = exportDir.isEmpty
            ? [(.light, "light")]
            : [(.light, "light"), (.dark, "dark")]

        let celticsSampleJSON = """
        {"id":15359901,"sport":"basketball_nba","sport_name":"NBA","home_team":"Boston Celtics","away_team":"Toronto Raptors","status":"scheduled","commence_time":"2026-11-25T00:30:00Z","home_team_data":{"abbreviation":"BOS","primary_color":"#007A33","logo_small":"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/bos.png"},"away_team_data":{"abbreviation":"TOR","primary_color":"#CE1141","logo_small":"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/tor.png"},"current_odds":{"home_probability":0.71,"away_probability":0.29,"home_rendered_percent":71,"away_rendered_percent":29}}
        """
        let liveCelticsSample: FeedEventData = {
            if let fromFeed = feedItems.compactMap(\.event).first(where: {
                EventState.section(of: $0) == .upcoming
                    && ($0.homeTeam.localizedCaseInsensitiveContains("Boston Celtics")
                        || $0.awayTeam.localizedCaseInsensitiveContains("Boston Celtics"))
            }) {
                return fromFeed
            }
            return try! decoder.decode(FeedEventData.self, from: Data(celticsSampleJSON.utf8))
        }()
        let fallbackSearchJSON = #"{"query":"Oscars","teams":[],"event_concepts":[],"results":[],"futures_families":[{"family_key":"story:oscars","label":"Oscars","headline":{"id":6173044,"name":"Oscar Winner: Best Picture","llm_sport_category":"entertainment","category":"entertainment","status":"open"},"members":[]},{"family_key":"story:macro_rates","label":"Fed & Rates","headline":{"id":57574250,"name":"Fed & Rates","llm_sport_category":"economics","category":"economics","status":"open"},"members":[]}],"futures":[]}"#
        let fallbackSearch = try decoder.decode(SearchResponse.self, from: Data(fallbackSearchJSON.utf8))
        let mergedSearchResp: SearchResponse = {
            if let dO = loadFixture("search_oscars.json"),
               let dI = loadFixture("search_inflation.json"),
               var objO = (try? JSONSerialization.jsonObject(with: dO)) as? [String: Any],
               let objI = (try? JSONSerialization.jsonObject(with: dI)) as? [String: Any] {
                let famO = (objO["futures_families"] as? [Any]) ?? []
                let famI = (objI["futures_families"] as? [Any]) ?? []
                let futO = (objO["futures"] as? [Any]) ?? []
                let futI = (objI["futures"] as? [Any]) ?? []
                objO["futures_families"] = famO + famI
                objO["futures"] = futO + futI
                if let merged = try? JSONSerialization.data(withJSONObject: objO),
                   let decoded = try? decoder.decode(SearchResponse.self, from: merged) {
                    return decoded
                }
            }
            return loadFixture("search_oscars.json").flatMap { try? decoder.decode(SearchResponse.self, from: $0) } ?? fallbackSearch
        }()
        let emptyResp = try decoder.decode(SearchResponse.self, from: Data(#"{"query":"","teams":[],"event_concepts":[],"results":[],"futures":[]}"#.utf8))
        let emptyFeedResp = try decoder.decode(FeedResponse.self, from: Data(#"{"items":[],"total":0,"limit":12,"offset":0,"has_more":false}"#.utf8))

        let fallbackBoston = try decoder.decode([TeamSearchResult].self, from: Data("""
        [
          {"id":574,"name":"Boston Bruins","location":"Boston","sport_key":"icehockey_nhl","logo_url":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/bos.png","abbreviation":"BOS","sports":[]},
          {"id":100,"name":"Boston Celtics","location":"Boston","sport_key":"basketball_nba","logo_url":"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/bos.png","abbreviation":"BOS","sports":[]},
          {"id":10709,"name":"Boston Red Sox","location":"Boston","sport_key":"baseball_mlb","logo_url":"https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bos.png","abbreviation":"BOS","sports":[]},
          {"id":11,"name":"New England Patriots","location":"New England","sport_key":"americanfootball_nfl","logo_url":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png","abbreviation":"NE","sports":[]},
          {"id":20,"name":"New England Revolution","location":"New England Revolution","sport_key":"soccer_usa_mls","logo_url":"https://a.espncdn.com/i/teamlogos/soccer/500/189.png","abbreviation":"NE","sports":[]}
        ]
        """.utf8))
        let bostonLocationTeams = loadFixture("teams_boston_by_location.json").flatMap { try? decoder.decode([TeamSearchResult].self, from: $0) }
            ?? fallbackBoston
        let bostonOrBrownTeams = loadFixture("teams_boston.json").flatMap { try? decoder.decode([TeamSearchResult].self, from: $0) }
            ?? loadFixture("teams_brown.json").flatMap { try? decoder.decode([TeamSearchResult].self, from: $0) }
            ?? fallbackBoston
        _ = emptyResp

        for width in widthsToRender {
            let wTag = Int(width)
            for (scheme, sTag) in schemesToRender {
                // 01: First screen untouched
                let ocr01 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.untouched),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-01-untouched-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
                XCTAssertFalse(ocr01.joined(separator: " ").contains("..."))
                XCTAssertTrue(ocr01.joined(separator: " ").contains("Butler"))

                guard !exportDir.isEmpty else { continue }

                // 02: One row done (Sync row lights up)
                let oneDone = FirstRunChecklistState364A(
                    completedRows: [.follow],
                    selectedSetSlugs: [],
                    followedCount: 1,
                    dismissedFromMyStuff: false
                )
                _ = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(oneDone),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-02-one-done-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )

                // 03: All five done
                let ocr03 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.allDone),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-03-all-five-done-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
                let joined03 = ocr03.joined(separator: " ")
                XCTAssertTrue(joined03.contains("Start anywhere"))
                XCTAssertTrue(joined03.contains("5 of 5 done"))

                // 04: Checklist at top of My Stuff ("2 of 5 done")
                let suiteMS = "Checklist364A.MyStuff.\(UUID().uuidString)"
                let defMS = UserDefaults(suiteName: suiteMS)!
                defer { defMS.removePersistentDomain(forName: suiteMS) }
                let twoDone = FirstRunChecklistState364A(
                    completedRows: [.lookUp, .follow],
                    selectedSetSlugs: [],
                    followedCount: 2,
                    dismissedFromMyStuff: false
                )
                var snap = MyStuffLandingViewModel295A.PreloadedSnapshot()
                snap.nextEvents = [(event: liveCelticsSample, awayVerified: true)]
                let landingVM = MyStuffLandingViewModel295A(
                    defaults: defMS,
                    preloaded: snap,
                    subjectHydrator: { _ in [] },
                    discoverFetcher: { emptyFeedResp }
                )
                let msFollow = FollowManager295A(defaults: defMS, initialSubjects: [
                    FollowedSubject295A.team(slug: "100", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba")
                ])
                let ocr04 = try await renderAndOCR(
                    view: MyStuffWithChecklistPreview364A(
                        state: .constant(twoDone),
                        landingVM: landingVM
                    )
                    .environment(\.followManager295A, msFollow),
                    filename: "364a-04-my-stuff-checklist-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
                XCTAssertFalse(ocr04.joined(separator: " ").contains("Final"), "Point 2: Next for you must never contain a finished game")

                // 05: Row 1 step ("Look anything up" — real Oscars search results, no duplicated examples)
                let oscarSearchResp = loadFixture("search_oscars.json").flatMap { try? decoder.decode(SearchResponse.self, from: $0) } ?? fallbackSearch
                let lookupResults = FirstRunChecklistExtractor364A.extractLookupResults(
                    from: oscarSearchResp,
                    subjectArt: content.subjectArtByCategory,
                    now: Self.fixtureNow
                )
                let ocr05 = try await renderAndOCR(
                    view: FirstRunLookupStepView364A(
                        examples: content.lookupExamples,
                        query: .constant("Oscars"),
                        results: lookupResults,
                        hasSearched: true
                    ),
                    filename: "364a-05-row1-lookup-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
                let joined05 = ocr05.joined(separator: " ")
                XCTAssertFalse(joined05.contains("Try tonight"), "Fix d: examples must hide once query is non-empty")
                XCTAssertFalse(joined05.contains("Live served"), "Fix c: never show Live served")
                XCTAssertFalse(joined05.contains("Docu-"), "Point 2: Oscars title must not break inside a word: \(joined05)")
                XCTAssertFalse(joined05.contains("Entertain-"), "Point 2: Subtitle must not break inside a word: \(joined05)")

                // 06: Row 2 step ("Follow what you care about" — logos + subject pictures, sentence box OFF)
                let suiteFollow = "Checklist364A.Follow.\(UUID().uuidString)"
                let defFollow = UserDefaults(suiteName: suiteFollow)!
                defer { defFollow.removePersistentDomain(forName: suiteFollow) }
                let followMgr = FollowManager295A(defaults: defFollow, initialSubjects: [])
                let followVM = FirstRunViewModel212A(
                    initialStep: 3,
                    defaults: defFollow,
                    debounceNs: 0,
                    searchLocationTeams: { _ in bostonLocationTeams },
                    searchTeamsByName: { _ in bostonOrBrownTeams },
                    searchGlobal: { _ in mergedSearchResp },
                    sentenceParser: nil
                )
                followVM.searchQuery = "Boston"
                await followVM.performTypeahead(query: followVM.searchQuery)
                if let boston = followVM.suggestions.first(where: { $0.name.lowercased().contains("boston") }) {
                    followVM.toggleSuggestion(boston, followManager: followMgr)
                }
                if let oscar = followVM.suggestions.first(where: { $0.name.lowercased().contains("oscar") }) {
                    followVM.toggleSuggestion(oscar, followManager: followMgr)
                }
                let ocr06 = try await renderAndOCR(
                    view: FirstRunFollowStepView364A(
                        vm: followVM,
                        subjectArtByCategory: content.subjectArtByCategory
                    )
                    .environment(\.followManager295A, followMgr),
                    filename: "364a-06-row2-follow-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
                let joined06 = ocr06.joined(separator: " ")
                XCTAssertFalse(joined06.contains("Sample preview"))
                XCTAssertFalse(joined06.contains("or a plain note"))
                XCTAssertFalse(joined06.contains("Confirm your picks"), "Point 1: sentence box stays off until Alex rules")
                XCTAssertTrue(joined06.contains("everything you follow lives in My Stuff"))
                XCTAssertTrue(joined06.contains("Patriots"), "Point 3: Patriots must appear near the top on Boston lookup: \(joined06)")
                XCTAssertTrue(joined06.contains("Revolution"), "Point 3: Revolution must appear near the top on Boston lookup: \(joined06)")
                XCTAssertFalse(joined06.contains("Added"), "Point 4: never show Added pill")

                // 07: Row 3 step ("See what the world expects" — real sets)
                let selectedSlugs = Set(content.discoverSets.prefix(1).map(\.slug))
                _ = try await renderAndOCR(
                    view: FirstRunExploreSetsStepView364A(
                        sets: content.discoverSets,
                        selectedSlugs: .constant(selectedSlugs)
                    ),
                    filename: "364a-07-row3-sets-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 1560,
                    colorScheme: scheme
                )

                // 08: Row 4 step (Sign in)
                _ = try await renderAndOCR(
                    view: FirstRunSignInStepView364A(),
                    filename: "364a-08-row4-signin-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )

                // 09: Row 5 step (Get a heads-up)
                let previewMover = content.startWithTonight.first(where: { $0.slotLabel == "Biggest mover" })
                    ?? content.startWithTonight.first
                let ocr09 = try await renderAndOCR(
                    view: FirstRunAlertsStepView364A(previewMover: previewMover),
                    filename: "364a-09-row5-alerts-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
                let joined09 = ocr09.joined(separator: " ")
                XCTAssertFalse(joined09.contains("LIVE EXAMPLE"))
                XCTAssertTrue(
                    joined09.contains("since pregame") || joined09.contains("since your last visit"),
                    "Fix b: Row 5 mover copy must name window (\(joined09))"
                )
                XCTAssertTrue(joined09.contains("ask before any alert"))

                // 10: What a person sees if they tap nothing and leave
                _ = try await renderAndOCR(
                    view: FirstRunLeaveToDiscoverPreview364A(sets: content.discoverSets),
                    filename: "364a-10-tap-nothing-discover-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )
            }
        }

        if !exportDir.isEmpty {
            let suiteAX = "Checklist364A.AX.\(UUID().uuidString)"
            let defAX = UserDefaults(suiteName: suiteAX)!
            defer { defAX.removePersistentDomain(forName: suiteAX) }
            let axFollow = FollowManager295A(defaults: defAX, initialSubjects: [
                FollowedSubject295A.team(slug: "100", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba")
            ])
            var snapAX = MyStuffLandingViewModel295A.PreloadedSnapshot()
            snapAX.nextEvents = [(event: liveCelticsSample, awayVerified: true)]
            let landingVMAX = MyStuffLandingViewModel295A(
                defaults: defAX,
                preloaded: snapAX,
                subjectHydrator: { _ in [] },
                discoverFetcher: { emptyFeedResp }
            )
            let twoDoneAX = FirstRunChecklistState364A(
                completedRows: [.lookUp, .follow],
                selectedSetSlugs: [],
                followedCount: 2,
                dismissedFromMyStuff: false
            )

            for (scheme, sTag) in schemesToRender {
                // Accessibility Extra-Large (AX3 at 390pt)
                let ocrAX01 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.untouched),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-11-ax3-untouched-\(sTag)-390.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 390,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility3,
                    sizeClass: .compact
                )
                let joinedAX01 = ocrAX01.joined(separator: " ")
                XCTAssertTrue(joinedAX01.contains("Look anything"), "AX3 OCR missing Look anything: \(joinedAX01)")
                XCTAssertTrue(joinedAX01.contains("Butler"), "Point 8: AX3 still keeps Butler quote: \(joinedAX01)")

                let ocrAX4 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.untouched),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-11b-ax4-untouched-\(sTag)-390.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 390,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility4,
                    sizeClass: .compact
                )
                XCTAssertFalse(ocrAX4.joined(separator: " ").contains("Butler"), "Point 8: omit Butler quote at AX4")

                let ocrAX12 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.allDone),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-12-ax3-all-done-\(sTag)-390.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 390,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility3,
                    sizeClass: .compact
                )
                let joinedAX12 = ocrAX12.joined(separator: " ")
                XCTAssertFalse(joinedAX12.contains("Bain Lu..."), "AX3 All-Done must not truncate Bain Luck wordmark: \(joinedAX12)")
                XCTAssertFalse(joinedAX12.contains("or..."), "AX3 search field placeholder must not truncate: \(joinedAX12)")
                XCTAssertTrue(joinedAX12.contains("Bain Luck"))
                XCTAssertTrue(joinedAX12.contains("5 of 5 done"))

                // Largest Accessibility Size (AX5 at 390pt)
                let ocrAX16 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.untouched),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-16-ax5-untouched-\(sTag)-390.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 390,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility5,
                    sizeClass: .compact
                )
                let joinedAX16 = ocrAX16.joined(separator: " ")
                XCTAssertTrue(joinedAX16.contains("Start") && joinedAX16.contains("anywhere"), "AX5 must not clip Start anywhere: \(joinedAX16)")
                XCTAssertTrue(joinedAX16.contains("Look") && joinedAX16.contains("anything up"), "AX5 missing Look anything up: \(joinedAX16)")
                XCTAssertFalse(joinedAX16.contains("Butler"), "Point 8: omit Butler quote at AX5")
                XCTAssertFalse(joinedAX16.contains("Bain..."), "AX5 0/5 must not truncate Bain Luck wordmark: \(joinedAX16)")
                XCTAssertTrue(joinedAX16.contains("Bain Luck"))

                let ocrAX17 = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.allDone),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-17-ax5-all-done-\(sTag)-390.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 390,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility5,
                    sizeClass: .compact
                )
                let joinedAX17 = ocrAX17.joined(separator: " ")
                XCTAssertFalse(joinedAX17.contains("Butler"), "Point 8: omit Butler quote at AX5")
                XCTAssertFalse(joinedAX17.contains("Bain Lu..."), "AX5 All-Done must not truncate Bain Luck wordmark: \(joinedAX17)")
                XCTAssertFalse(joinedAX17.contains("tonigh..."), "AX5 row subtitle must wrap cleanly rather than truncate: \(joinedAX17)")
                XCTAssertTrue(joinedAX17.contains("Bain Luck"))
                XCTAssertTrue(joinedAX17.contains("5 of 5 done"))

                // iPad regular-width (820x1024)
                _ = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.untouched),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-13-ipad-untouched-\(sTag)-820.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 820,
                    height: 1024,
                    colorScheme: scheme,
                    dynamicTypeSize: .large,
                    sizeClass: .regular
                )

                _ = try await renderAndOCR(
                    view: FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.allDone),
                        inlineSearchQuery: .constant("")
                    ),
                    filename: "364a-14-ipad-all-done-\(sTag)-820.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 820,
                    height: 1024,
                    colorScheme: scheme,
                    dynamicTypeSize: .large,
                    sizeClass: .regular
                )

                _ = try await renderAndOCR(
                    view: MyStuffWithChecklistPreview364A(
                        state: .constant(twoDoneAX),
                        landingVM: landingVMAX
                    )
                    .environment(\.followManager295A, axFollow),
                    filename: "364a-15-ipad-my-stuff-\(sTag)-820.png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: 820,
                    height: 1024,
                    colorScheme: scheme,
                    dynamicTypeSize: .large,
                    sizeClass: .regular
                )
            }
        }
    }

    private func renderAndOCR<V: View>(
        view: V,
        filename: String,
        exportDir: String,
        preloaded: [String: PairedPlatformImage],
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize = .large,
        sizeClass: UserInterfaceSizeClass = .compact
    ) async throws -> [String] {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiSizeClass: UIUserInterfaceSizeClass = sizeClass == .regular ? .regular : .compact
        let uiCategory: UIContentSizeCategory = switch dynamicTypeSize {
        case .accessibility5: .accessibilityExtraExtraExtraLarge
        case .accessibility4: .accessibilityExtraExtraLarge
        case .accessibility3: .accessibilityExtraLarge
        default: .large
        }
        let auth = AuthManager()
        let suite = "Checklist364A.Render.\(UUID().uuidString)"
        let renderDefaults = UserDefaults(suiteName: suite)!
        defer { renderDefaults.removePersistentDomain(forName: suite) }
        let pins = PinManager(defaults: renderDefaults, serverLoad: { PinsResponse(events: [], futures: []) }, serverSync: { _, _, _ in })

        let root = view
            .frame(width: width, height: height, alignment: .topLeading)
            .environment(\.horizontalSizeClass, sizeClass)
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.machineryPreloadedImages12288, preloaded)
            .environmentObject(NavigationCoordinator())
            .environmentObject(pins)
            .environmentObject(auth)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: uiSizeClass),
            UITraitCollection(userInterfaceStyle: uiStyle),
            UITraitCollection(preferredContentSizeCategory: uiCategory),
        ])
        let host = hostForMeasurement(root, at: dynamicTypeSize)
        let container = TraitContainer364A(child: host, traits: traits)
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
            try? await Task.sleep(nanoseconds: 35_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: container.view.bounds, format: fmt).image { _ in
            _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }

        if !exportDir.isEmpty, let png = image.pngData() {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
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

    /// Opt-in live-network end-to-end verification on simulator (`RUN_LIVE_364A_E2E=1`)
    /// exercising `FirstRunChecklistRootView364A`, `FirstRunChecklistCoordinatorVM364A`,
    /// `FirstRunLookupViewModel364A`, `FirstRunViewModel212A`, `FirstRunChecklistStore364A`,
    /// `FollowManager295A`, `MyStuffLandingViewModel295A`, and `GameAlertsPreference13083`
    /// against live `https://api.bainluck.com`.
    func testLiveNetworkEndToEndFiveRowsWhenEnabled() async throws {
        guard ProcessInfo.processInfo.environment["RUN_LIVE_364A_E2E"] == "1" else {
            return
        }

        let suiteName = "Checklist364A.LiveE2E.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store = FirstRunChecklistStore364A(defaults: defaults)
        let followManager = FollowManager295A(defaults: defaults)
        let pinManager = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )
        let auth = AuthManager()

        // Host live root view briefly so SwiftUI `.task` / environment wiring executes end-to-end.
        let rootView = FirstRunChecklistRootView364A()
            .frame(width: 390, height: 844)
            .environment(\.followManager295A, followManager)
            .environment(\.firstRunChecklistStore364A, store)
            .environmentObject(auth)
            .environmentObject(pinManager)
            .environmentObject(NavigationCoordinator())

        let host = hostForMeasurement(rootView, at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        // 1. Live coordinator feed load from https://api.bainluck.com
        let coordinatorVM = FirstRunChecklistCoordinatorVM364A(defaults: defaults)
        await coordinatorVM.loadIfNeeded(force: true)
        XCTAssertFalse(coordinatorVM.loadFailed, "Live feed load failed on api.bainluck.com")
        XCTAssertGreaterThanOrEqual(coordinatorVM.content.discoverSets.count, 4)
        XCTAssertEqual(coordinatorVM.content.lookupExamples.count, 3)
        XCTAssertFalse(coordinatorVM.content.startWithTonight.isEmpty)

        // 2. Row 1: Live lookup ("Oscars") -> non-empty results with subjectLabel + percent
        let lookupVM = FirstRunLookupViewModel364A(debounceNs: 0)
        lookupVM.runImmediateSearch(query: "Oscars", subjectArt: coordinatorVM.content.subjectArtByCategory)
        for _ in 0..<40 where lookupVM.isSearching || !lookupVM.hasSearched {
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertTrue(lookupVM.hasSearched)
        XCTAssertFalse(lookupVM.searchFailed)
        XCTAssertFalse(lookupVM.results.isEmpty, "Expected live Oscars results from api.bainluck.com")
        XCTAssertTrue(lookupVM.results.allSatisfy { $0.percent > 0 && $0.percent < 100 && !$0.subjectLabel.isEmpty })
        store.markCompleted(.lookUp)

        // 3. Row 2: Live non-sports subject + FollowManager295A + MyStuffLandingViewModel295A hydration
        let firstSet = try XCTUnwrap(coordinatorVM.content.discoverSets.first)
        let nonSportsSubject = FollowedSubject295A.subject(
            slug: firstSet.slug,
            name: firstSet.bundleTitle,
            affinityCategory: firstSet.category.lowercased(),
            marketId: nil,
            logoUrl: firstSet.imageUrl,
            primaryColor: nil,
            searchQuery: firstSet.bundleTitle
        )
        _ = followManager.toggle(nonSportsSubject)
        let followVM = FirstRunViewModel212A(initialStep: 3, defaults: defaults)
        await followVM.performTypeahead(query: "Boston Celtics")
        if let firstTeam = followVM.suggestions.first {
            followVM.toggleSuggestion(firstTeam, followManager: followManager, pinManager: pinManager)
        }
        store.syncFollowCount(followManager.subjects.count, markFollowCompleted: true)

        let landingVM = MyStuffLandingViewModel295A(defaults: defaults)
        await landingVM.refresh(
            followedSubjects: followManager.subjects,
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil
        )
        XCTAssertFalse(landingVM.discoverItems.isEmpty, "MyStuff Discover fallback must populate from live API")

        // 4. Row 3: Select live Discover set -> persists into FirstRunPreferences212A
        store.setSelectedSetSlugs([firstSet.slug], from: coordinatorVM.content.discoverSets)
        let reloadedStore = FirstRunChecklistStore364A(defaults: defaults)
        XCTAssertTrue(reloadedStore.state.selectedSetSlugs.contains(firstSet.slug))
        XCTAssertEqual(reloadedStore.state.completedRows, [.lookUp, .follow, .exploreSets])

        // 5. Rows 4 & 5: Sync + Alerts completion -> 5 of 5 persisted + GameAlertsPreference13083 state readable
        _ = GameAlertsPreference13083.shared.isEnabled
        reloadedStore.markCompleted(.syncDevices)
        reloadedStore.markCompleted(.alerts)
        let finalReload = FirstRunChecklistStore364A(defaults: defaults)
        XCTAssertEqual(finalReload.state.completedCount, 5)
        XCTAssertEqual(finalReload.state.progressText, "5 of 5 done")
        XCTAssertEqual("Getting started · \(finalReload.state.progressText)", "Getting started · 5 of 5 done")
    }
    #endif
}
