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
        let awardExample = try XCTUnwrap(content.lookupExamples.first { $0.kind == .award })
        XCTAssertEqual(awardExample.id, "lookup-award-6173044", "Non-sports award (Oscars) preferred and concisely titled")
        XCTAssertEqual(awardExample.title, "Oscars: Best Picture")
        let electionExample = try XCTUnwrap(content.lookupExamples.first { $0.kind == .election })
        XCTAssertEqual(electionExample.id, "lookup-election-113364", "Conflict bundles must never supply Row 1 election example")
        XCTAssertEqual(electionExample.title, "French Election")
        XCTAssertNil(content.syncRowPreview?.imageUrl, "Row 4 starts without an unrelated teaser thumbnail before any pick")
        for ex in content.lookupExamples {
            XCTAssertTrue((5...95).contains(ex.percent), "Out-of-bounds % on lookup example \(ex)")
        }

        XCTAssertEqual(content.startWithTonight.count, 3)
        XCTAssertEqual(content.startWithTonight.map(\.slotLabel), ["Biggest game", "Biggest mover", "Odd one"])
        let oddCard = try XCTUnwrap(content.startWithTonight.first { $0.slotLabel == "Odd one" })
        XCTAssertEqual(oddCard.percent, 12, "Yes/No odd card must show Yes side (12%), never No (88%)")
        for card in content.startWithTonight {
            XCTAssertTrue((5...95).contains(card.percent))
            if let delta = card.deltaText {
                XCTAssertFalse(delta.contains("pts"))
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

    func testSourceGuardsRespectDecision364AAndPreservePaused212ACode() throws {
        let viewSrc = try source("Bain Luck/Views/FirstRunChecklistView364A.swift")
        let modelsSrc = try source("Bain Luck/Utilities/FirstRunChecklistModels364A.swift")
        let pausedFlowSrc = try source("Bain Luck/Views/FirstRunFlowView212A.swift")

        XCTAssertTrue(modelsSrc.contains("Probability is the very guide of life."))
        XCTAssertTrue(modelsSrc.contains("Joseph Butler, 1736"))
        XCTAssertFalse(viewSrc.contains("Your picks decide what Discover shows first"))
        XCTAssertFalse(viewSrc.lowercased().contains("want to personalis"))
        XCTAssertFalse(viewSrc.lowercased().contains("want to personaliz"))
        XCTAssertFalse(viewSrc.contains("Skip for now"))
        XCTAssertTrue(pausedFlowSrc.contains("private func pairContent"), "Item 5: paused 2A..2C screens stay on branch")
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

        let liveEventSample = feedItems.compactMap(\.event).first(where: { $0.id == 15353145 }) ?? feedItems.compactMap(\.event).first
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

        let fallbackBoston = try decoder.decode([TeamSearchResult].self, from: Data(#"[{"id":100,"name":"Boston Celtics","location":"Boston","sport_key":"basketball_nba","logo_url":null,"abbreviation":"BOS","sports":[]}]"#.utf8))
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
                _ = try await renderAndOCR(
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
                if let liveEventSample {
                    snap.nextEvents = [(event: liveEventSample, awayVerified: true)]
                }
                let landingVM = MyStuffLandingViewModel295A(
                    defaults: defMS,
                    preloaded: snap,
                    subjectHydrator: { _ in [] },
                    discoverFetcher: { emptyFeedResp }
                )
                let msFollow = FollowManager295A(defaults: defMS, initialSubjects: [
                    FollowedSubject295A.team(slug: "100", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba")
                ])
                _ = try await renderAndOCR(
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

                // 05: Row 1 step ("Look anything up")
                let lookupResults = content.lookupExamples.map { ex in
                    FirstRunLookupResult364A(
                        id: ex.id,
                        badgeText: ex.badgeText,
                        title: ex.title,
                        subtitle: "Live served",
                        percent: ex.percent,
                        imageUrl: ex.imageUrl,
                        sfSymbol: ex.sfSymbol,
                        accentHex: "#005CC2"
                    )
                }
                _ = try await renderAndOCR(
                    view: FirstRunLookupStepView364A(
                        examples: content.lookupExamples,
                        query: .constant("Oscars"),
                        results: lookupResults
                    ),
                    filename: "364a-05-row1-lookup-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )

                // 06: Row 2 step ("Follow what you care about" — logos + subject pictures + 359: A)
                let suiteFollow = "Checklist364A.Follow.\(UUID().uuidString)"
                let defFollow = UserDefaults(suiteName: suiteFollow)!
                defer { defFollow.removePersistentDomain(forName: suiteFollow) }
                let followMgr = FollowManager295A(defaults: defFollow, initialSubjects: [])
                let followVM = FirstRunViewModel212A(
                    initialStep: 3,
                    defaults: defFollow,
                    debounceNs: 0,
                    searchLocationTeams: { _ in [] },
                    searchTeamsByName: { _ in bostonOrBrownTeams },
                    searchGlobal: { _ in mergedSearchResp },
                    sentenceParser: { s in try await FirstRunSentenceSampleProvider359A.parseSampleSentence(s) }
                )
                followVM.searchQuery = "Boston Celtics, Oscars, Spurs, and inflation"
                await followVM.performSentenceParse(query: followVM.searchQuery, followManager: followMgr)
                await followVM.performTypeahead(query: followVM.searchQuery)
                _ = try await renderAndOCR(
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
                _ = try await renderAndOCR(
                    view: FirstRunAlertsStepView364A(previewMover: previewMover),
                    filename: "364a-09-row5-alerts-\(sTag)-\(wTag).png",
                    exportDir: exportDir,
                    preloaded: preloaded,
                    width: width,
                    height: 844,
                    colorScheme: scheme
                )

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
    }

    private func renderAndOCR<V: View>(
        view: V,
        filename: String,
        exportDir: String,
        preloaded: [String: PairedPlatformImage],
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme
    ) async throws -> [String] {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let auth = AuthManager()
        let suite = "Checklist364A.Render.\(UUID().uuidString)"
        let renderDefaults = UserDefaults(suiteName: suite)!
        defer { renderDefaults.removePersistentDomain(forName: suite) }
        let pins = PinManager(defaults: renderDefaults, serverLoad: { PinsResponse(events: [], futures: []) }, serverSync: { _, _, _ in })

        let root = view
            .frame(width: width, height: height, alignment: .topLeading)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, .large)
            .environment(\.machineryPreloadedImages12288, preloaded)
            .environmentObject(NavigationCoordinator())
            .environmentObject(pins)
            .environmentObject(auth)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: uiStyle),
            UITraitCollection(preferredContentSizeCategory: .large),
        ])
        let host = hostForMeasurement(root, at: .large)
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
    #endif
}
