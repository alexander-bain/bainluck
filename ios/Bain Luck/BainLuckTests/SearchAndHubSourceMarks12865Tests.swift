import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12865 — Verifies native Search (`SearchView` / `SearchEventCardAdapter183A`) and
/// Collection / Container Hub (`ContainerHubView` / `ContainerHubMember`) source marks:
///   1. `SearchEvent` and `ContainerHubMember.card` decode both `source_mark` and `away_source_mark`
///      and resolve the identical favourite attribution (`49ers · 60%`) across Search and Week 11.
///   2. When `resolve_hero` folds a suppressed twin so `hero_probability` differs from `current_odds`,
///      `SearchEventCardAdapter183A.fromSearchResult` aligns the card probability with the hero number
///      its `source_mark` explains while preserving `homeRenderedPercent` when they already match.
///   3. On a finished game with settled `source_mark` (home) and `away_source_mark` (away),
///      `EventCardView.resolvedCardSourceMark` attributes the winner (`Won`), never the home loser (`Lost`).
@MainActor
final class SearchAndHubSourceMarks12865Tests: XCTestCase {

    private struct StaticContainerHubLoader: ContainerHubLoading {
        let response: ContainerHubResponse
        nonisolated func load(slug: String) async throws -> ContainerHubResponse {
            response
        }
    }

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ data: Data) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }

    private func captureView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        fixedHeight: CGFloat = 780,
        wrapNavigation: Bool = true,
        scheme: ColorScheme = .light,
        at size: DynamicTypeSize = .large,
        settlePasses: Int = 5
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let inner: AnyView = {
            if wrapNavigation {
                return AnyView(
                    NavigationStack {
                        view
                            .toolbar(.hidden, for: .navigationBar)
                    }
                )
            }
            return AnyView(view)
        }()
        let root = inner
            .frame(width: width, height: fixedHeight, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager())

        let host = hostForMeasurement(root, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fixedHeight))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fixedHeight)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<settlePasses {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: fixedHeight), format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func sideBySide(_ light: UIImage, _ dark: UIImage) -> UIImage {
        let gap: CGFloat = 16
        let pad: CGFloat = 16
        let totalW = pad * 2 + light.size.width + gap + dark.size.width
        let totalH = pad * 2 + max(light.size.height, dark.size.height)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: fmt).image { ctx in
            UIColor(white: 0.12, alpha: 1.0).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: totalW, height: totalH))
            light.draw(in: CGRect(x: pad, y: pad, width: light.size.width, height: light.size.height))
            dark.draw(in: CGRect(x: pad + light.size.width + gap, y: pad, width: dark.size.width, height: dark.size.height))
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testSearchDecodesBothSourceMarksAndAlignsTwinFoldedHeroProbability() throws {
        let futureISO = ISO8601DateFormatter().string(from: Date().addingTimeInterval(86_400))
        let searchJSON = """
        {
          "query": "Towson",
          "results": [
            {
              "id": 15350489,
              "sport": "basketball_ncaab",
              "sport_name": "NCAAB",
              "home_team": "Towson Tigers",
              "away_team": "James Madison Dukes",
              "commence_time": "\(futureISO)",
              "status": "live",
              "home_score": 31,
              "away_score": 35,
              "hero_probability": 0.44,
              "hero_probability_away": 0.56,
              "hero_probability_source": "blend",
              "current_odds": {
                "home_probability": 0.49,
                "away_probability": 0.51,
                "home_rendered_percent": 49,
                "away_rendered_percent": 51
              },
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.42, "observed_at": null },
                  { "key": "betting", "name": "Sportsbooks", "probability": 0.49, "observed_at": null, "count": 6 }
                ],
                "method": "Bain Luck blend · weighted average of live sources"
              },
              "away_source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.58, "observed_at": null },
                  { "key": "betting", "name": "Sportsbooks", "probability": 0.51, "observed_at": null, "count": 6 }
                ],
                "method": "Bain Luck blend · weighted average of live sources"
              }
            }
          ],
          "futures": []
        }
        """

        let response = try decodeSnake(SearchResponse.self, Data(searchJSON.utf8))
        let searchEvent = try XCTUnwrap(response.results.first)
        let adapted = SearchEventCardAdapter183A.fromSearchResult(searchEvent, sportDisplayName: "NCAAB")

        XCTAssertEqual(adapted.currentOdds?.homeProbability ?? -1, 0.44, accuracy: 0.0001)
        XCTAssertEqual(adapted.currentOdds?.awayProbability ?? -1, 0.56, accuracy: 0.0001)
        XCTAssertNil(adapted.currentOdds?.homeRenderedPercent)

        let resolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adapted,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertEqual(resolved.subject, "James Madison")
        XCTAssertEqual(resolved.number ?? -1, 0.56, accuracy: 0.0001)
        XCTAssertEqual(resolved.mark.sources.map(\.key), ["polymarket", "betting"])
    }

    func testFinishedGameSettledMarkPrefersAwayWinnerOverHomeLoser() throws {
        let finishedJSON = """
        {
          "query": "Vikings",
          "results": [
            {
              "id": 14969886,
              "sport": "americanfootball_nfl",
              "sport_name": "NFL",
              "home_team": "Green Bay Packers",
              "away_team": "Minnesota Vikings",
              "commence_time": "2026-11-15T18:00:00Z",
              "status": "completed",
              "home_score": 10,
              "away_score": 30,
              "hero_probability": 0.0,
              "hero_probability_away": 1.0,
              "hero_probability_source": "settled",
              "source_mark": {
                "state": "settled",
                "sources": [],
                "settled": { "source": "espn", "result": "Lost", "at": "2026-11-15T21:00:38Z" }
              },
              "away_source_mark": {
                "state": "settled",
                "sources": [],
                "settled": { "source": "espn", "result": "Won", "at": "2026-11-15T21:00:38Z" }
              }
            }
          ],
          "futures": []
        }
        """

        let response = try decodeSnake(SearchResponse.self, Data(finishedJSON.utf8))
        let adapted = SearchEventCardAdapter183A.fromSearchResult(
            try XCTUnwrap(response.results.first),
            sportDisplayName: "NFL"
        )
        let resolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adapted,
                canStillBeGraded: false,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertEqual(resolved.subject, "Vikings")
        XCTAssertEqual(resolved.mark.settled?.result, "Won")
        XCTAssertFalse(resolved.isPregame)
        XCTAssertEqual(SourceMarkSheet.settledLine(resolved.mark)?.price, "Won")
    }

    func testContainerHubAndSearchProduceIdenticalVikings49ersSourceMark() throws {
        let cardFragment = """
        {
          "id": 14639207,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "San Francisco 49ers",
          "away_team": "Minnesota Vikings",
          "commence_time": "2099-11-23T01:20:00Z",
          "status": "scheduled",
          "hero_probability": 0.5963,
          "hero_probability_away": 0.4037,
          "hero_probability_source": "blend",
          "current_odds": {
            "home_probability": 0.5963,
            "away_probability": 0.4037,
            "projected_home_score": 24.4,
            "projected_away_score": 21.4
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.595, "observed_at": null },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.605, "observed_at": null },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.5963, "observed_at": null, "count": 12 }
            ],
            "method": "Bain Luck blend · the weighted middle of these sources"
          },
          "away_source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.405, "observed_at": null },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.395, "observed_at": null },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.4037, "observed_at": null, "count": 12 }
            ],
            "method": "Bain Luck blend · the weighted middle of these sources"
          }
        }
        """

        let searchResp = try decodeSnake(
            SearchResponse.self,
            Data(#"{"query":"Vikings","results":[\#(cardFragment)],"futures":[]}"#.utf8)
        )
        let hubResp = try decodeSnake(
            ContainerHubResponse.self,
            Data("""
            {
              "state": "published",
              "slug": "nfl-2026-week-11",
              "revision": 9,
              "edition": { "kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 11 },
              "container": { "id": 19, "name": "NFL 2026 · Week 11", "slug": "nfl-2026-week-11" },
              "children": [],
              "sections": [
                {
                  "class": "match_winner",
                  "count": 1,
                  "members": [
                    {
                      "type": "event",
                      "id": 14639207,
                      "destination": { "kind": "event", "id": 14639207, "api": "/api/events/14639207" },
                      "card": \(cardFragment),
                      "question_ids": []
                    }
                  ]
                }
              ],
              "member_count": 1,
              "withheld": [],
              "withheld_count": 0,
              "assembled": true,
              "known_classes": ["match_winner"]
            }
            """.utf8)
        )

        let searchAdapted = SearchEventCardAdapter183A.fromSearchResult(
            try XCTUnwrap(searchResp.results.first),
            sportDisplayName: "NFL"
        )
        guard case .event(let hubEvent) = try XCTUnwrap(hubResp.sections.first?.members.first?.card) else {
            return XCTFail("Expected event card on Week 11 hub")
        }

        let searchMark = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: searchAdapted,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        let hubMark = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: hubEvent,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )

        XCTAssertEqual(searchMark.subject, "49ers")
        XCTAssertEqual(hubMark.subject, "49ers")
        XCTAssertEqual(searchMark.mark, hubMark.mark)
        XCTAssertEqual(
            SourceMarkSheet.lines(hubMark.mark).map { "\($0.name)=\($0.price ?? "")" },
            ["Kalshi=60%", "Polymarket=61%", "Sportsbooks (12)=60%"]
        )
    }

    func testLiveSearchAndWeek11RendersAt390LightAndDark() throws {
        let dir = URL(fileURLWithPath: "/tmp/renders-12865", isDirectory: true)
        guard FileManager.default.fileExists(atPath: dir.path) else { return }
        let outDir = dir.appendingPathComponent("v2", isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let searchData = try Data(contentsOf: dir.appendingPathComponent("live-search-vikings.json"))
        let week11Data = try Data(contentsOf: dir.appendingPathComponent("live-week11-compact.json"))
        let searchResp = try decodeSnake(SearchResponse.self, searchData)
        let week11Resp = try decodeSnake(ContainerHubResponse.self, week11Data)

        // 1. Search results for "Vikings" (Vikings @ 49ers + Falcons @ Vikings with ⓘ marks)
        let makeSearchView = { () -> SearchView in
            let place = MacReadingPlace<SearchViewModel>()
            _ = place.models {
                let vm = SearchViewModel { _, _ in searchResp }
                vm.query = "Vikings"
                vm.results = searchResp
                return vm
            }
            return SearchView(macPlace: place)
        }
        let searchLight = captureView(makeSearchView(), fixedHeight: 820, wrapNavigation: true, scheme: .light)
        let searchDark = captureView(makeSearchView(), fixedHeight: 820, wrapNavigation: true, scheme: .dark)
        let searchOCR = try ocrLines(searchLight).joined(separator: " ")
        XCTAssertTrue(searchOCR.localizedCaseInsensitiveContains("Vikings"), "Expected Vikings in Search OCR: \(searchOCR)")
        XCTAssertTrue(searchOCR.localizedCaseInsensitiveContains("49ers"), "Expected 49ers in Search OCR: \(searchOCR)")
        try XCTUnwrap(sideBySide(searchLight, searchDark).pngData())
            .write(to: outDir.appendingPathComponent("12865-search-vikings-light-dark-390.png"))

        // 2. NFL Week 11 ContainerHubView (live compact Week 11 with ⓘ marks + "More on this game")
        let hubLight = captureView(
            ContainerHubView(
                slug: "nfl-2026-week-11",
                displayName: "NFL Week 11",
                service: StaticContainerHubLoader(response: week11Resp)
            ),
            fixedHeight: 820,
            wrapNavigation: true,
            scheme: .light,
            settlePasses: 8
        )
        let hubDark = captureView(
            ContainerHubView(
                slug: "nfl-2026-week-11",
                displayName: "NFL Week 11",
                service: StaticContainerHubLoader(response: week11Resp)
            ),
            fixedHeight: 820,
            wrapNavigation: true,
            scheme: .dark,
            settlePasses: 8
        )
        let hubOCR = try ocrLines(hubLight).joined(separator: " ")
        XCTAssertTrue(hubOCR.localizedCaseInsensitiveContains("Texans") || hubOCR.localizedCaseInsensitiveContains("Week 11"), "Expected Week 11 games in Light Hub OCR: \(hubOCR)")
        let hubDarkOCR = try ocrLines(hubDark).joined(separator: " ")
        XCTAssertTrue(hubDarkOCR.localizedCaseInsensitiveContains("Texans"), "Expected Texans readable in Dark Hub OCR: \(hubDarkOCR)")
        XCTAssertTrue(hubDarkOCR.localizedCaseInsensitiveContains("Colts"), "Expected Colts readable in Dark Hub OCR: \(hubDarkOCR)")
        try XCTUnwrap(sideBySide(hubLight, hubDark).pngData())
            .write(to: outDir.appendingPathComponent("12865-week11-hub-light-dark-390.png"))

        // 3. `Where this number comes from` sheet on Vikings @ 49ers (`14639207`) + Away-Winner settled sheet (`14969886`)
        let vikings49ers = try XCTUnwrap(searchResp.results.first(where: { $0.id == 14639207 }))
        let adapted49ers = SearchEventCardAdapter183A.fromSearchResult(vikings49ers, sportDisplayName: "NFL")
        let mark49ers = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adapted49ers,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        let sheetLight = captureView(
            SourceMarkSheet(
                mark: mark49ers.mark,
                number: mark49ers.number,
                subject: mark49ers.subject,
                isPregame: mark49ers.isPregame
            ),
            fixedHeight: 520,
            wrapNavigation: false,
            scheme: .light
        )
        let sheetDark = captureView(
            SourceMarkSheet(
                mark: mark49ers.mark,
                number: mark49ers.number,
                subject: mark49ers.subject,
                isPregame: mark49ers.isPregame
            ),
            fixedHeight: 520,
            wrapNavigation: false,
            scheme: .dark
        )
        let sheetOCR = try ocrLines(sheetLight).joined(separator: " ")
        XCTAssertTrue(sheetOCR.localizedCaseInsensitiveContains("49ers"), "Expected 49ers in sheet OCR: \(sheetOCR)")
        XCTAssertTrue(sheetOCR.localizedCaseInsensitiveContains("Kalshi"), "Expected Kalshi in sheet OCR: \(sheetOCR)")
        XCTAssertTrue(sheetOCR.localizedCaseInsensitiveContains("Polymarket"), "Expected Polymarket in sheet OCR: \(sheetOCR)")
        try XCTUnwrap(sideBySide(sheetLight, sheetDark).pngData())
            .write(to: outDir.appendingPathComponent("12865-vikings-49ers-sheet-light-dark-390.png"))

        let vikingsPackers = try XCTUnwrap(searchResp.results.first(where: { $0.id == 14969886 }))
        let adaptedPackers = SearchEventCardAdapter183A.fromSearchResult(vikingsPackers, sportDisplayName: "NFL")
        let settledMark = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adaptedPackers,
                canStillBeGraded: false,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        let settledLight = captureView(
            SourceMarkSheet(
                mark: settledMark.mark,
                number: settledMark.number,
                subject: settledMark.subject,
                isPregame: settledMark.isPregame
            ),
            fixedHeight: 420,
            wrapNavigation: false,
            scheme: .light
        )
        let settledDark = captureView(
            SourceMarkSheet(
                mark: settledMark.mark,
                number: settledMark.number,
                subject: settledMark.subject,
                isPregame: settledMark.isPregame
            ),
            fixedHeight: 420,
            wrapNavigation: false,
            scheme: .dark
        )
        let settledOCR = try ocrLines(settledLight).joined(separator: " ")
        XCTAssertTrue(settledOCR.localizedCaseInsensitiveContains("Vikings"), "Expected away winner Vikings in settled sheet OCR: \(settledOCR)")
        XCTAssertTrue(settledOCR.localizedCaseInsensitiveContains("Won"), "Expected Won in settled sheet OCR: \(settledOCR)")
        try XCTUnwrap(sideBySide(settledLight, settledDark).pngData())
            .write(to: outDir.appendingPathComponent("12865-settled-away-winner-sheet-light-dark-390.png"))
    }

    func testCompactNFLWeekHubPreservesDeferredMarketCursorAndLoadsMore() async throws {
        let initialCursor = "WzEwMSw1LHRydWUsNTAxLFs0MDEsNDAyXV0"
        let page1JSON = """
        {
          "state": "published",
          "slug": "nfl-2026-week-11",
          "revision": 5,
          "edition": { "kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 11 },
          "container": { "id": 101, "kind": "week", "name": "NFL Week 11", "slug": "nfl-2026-week-11" },
          "children": [],
          "member_count": 1,
          "withheld": [],
          "withheld_count": 0,
          "assembled": true,
          "known_classes": ["game", "prop", "futures"],
          "counts": {
            "market_count": 20,
            "selected_market_count": 12,
            "deferred_market_count": 8
          },
          "page": {
            "kind": "nfl_week_markets",
            "limit": 12,
            "next_cursor": "\(initialCursor)",
            "next_url": "/api/containers/nfl-2026-week-11?market_cursor=\(initialCursor)&market_revision=5&market_limit=24&include_children=true"
          },
          "sections": [
            {
              "class": "prop",
              "title": "Player Props",
              "count": 1,
              "members": [
                {
                  "type": "market",
                  "id": 501,
                  "destination": { "kind": "market", "id": 501, "api": "/api/futures/501" },
                  "card": {
                    "id": 501,
                    "name": "Saquon Barkley Rushing Yards",
                    "status": "open",
                    "source": "kalshi",
                    "top_outcomes": [{ "id": 1, "name": "90+ yards", "probability": 0.54 }]
                  }
                }
              ]
            }
          ]
        }
        """

        let page2JSON = """
        {
          "state": "published",
          "slug": "nfl-2026-week-11",
          "revision": 5,
          "edition": { "kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 11 },
          "container": { "id": 101, "kind": "week", "name": "NFL Week 11", "slug": "nfl-2026-week-11" },
          "children": [],
          "member_count": 1,
          "withheld": [],
          "withheld_count": 0,
          "assembled": true,
          "known_classes": ["game", "prop", "futures"],
          "counts": {
            "market_count": 20,
            "selected_market_count": 8,
            "deferred_market_count": 0
          },
          "page": {
            "kind": "nfl_week_markets",
            "limit": 50,
            "next_cursor": null,
            "next_url": null
          },
          "sections": [
            {
              "class": "prop",
              "title": "Player Props",
              "count": 1,
              "members": [
                {
                  "type": "market",
                  "id": 502,
                  "destination": { "kind": "market", "id": 502, "api": "/api/futures/502" },
                  "card": {
                    "id": 502,
                    "name": "Lamar Jackson Passing Yards",
                    "status": "open",
                    "source": "kalshi",
                    "top_outcomes": [{ "id": 2, "name": "225+ yards", "probability": 0.48 }]
                  }
                }
              ]
            }
          ]
        }
        """

        let page1 = try decodeSnake(ContainerHubResponse.self, Data(page1JSON.utf8))
        let page2 = try decodeSnake(ContainerHubResponse.self, Data(page2JSON.utf8))
        XCTAssertEqual(page1.marketCounts, ContainerHubMarketCounts(marketCount: 20, selectedMarketCount: 12, deferredMarketCount: 8))
        XCTAssertEqual(page1.page?.kind, "nfl_week_markets")
        XCTAssertEqual(page1.page?.nextCursor, initialCursor)

        final class RecordingMarketPageLoader: ContainerHubLoading, @unchecked Sendable {
            let first: ContainerHubResponse
            let second: ContainerHubResponse
            var recordedMarketCursor: String?
            var recordedRevision: Int?
            var recordedLimit: Int?
            var recordedNextUrl: String?
            var calledRegularLoadPage = false

            init(first: ContainerHubResponse, second: ContainerHubResponse) {
                self.first = first
                self.second = second
            }

            nonisolated func load(slug: String) async throws -> ContainerHubResponse { first }

            nonisolated func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse {
                calledRegularLoadPage = true
                return second
            }

            nonisolated func loadMarketPage(slug: String, cursor: String, revision: Int, limit: Int, nextUrl: String?) async throws -> ContainerHubResponse {
                recordedMarketCursor = cursor
                recordedRevision = revision
                recordedLimit = limit
                recordedNextUrl = nextUrl
                return second
            }
        }

        let loader = RecordingMarketPageLoader(first: page1, second: page2)
        let vm = ContainerHubViewModel(slug: "nfl-2026-week-11", service: loader)
        await vm.load()

        guard case .loaded(let initialPresentation) = vm.state else {
            return XCTFail("Expected loaded state")
        }
        XCTAssertEqual(initialPresentation.response.page?.nextCursor, initialCursor, "Load more markets must be offered when deferred markets exist")

        await vm.loadMore()
        XCTAssertFalse(loader.calledRegularLoadPage, "Compact week hub must use loadMarketPage (market_cursor), not theme loadPage")
        XCTAssertEqual(loader.recordedMarketCursor, initialCursor)
        XCTAssertEqual(loader.recordedRevision, 5)
        XCTAssertEqual(loader.recordedLimit, 12)
        XCTAssertEqual(
            loader.recordedNextUrl,
            "/api/containers/nfl-2026-week-11?market_cursor=\(initialCursor)&market_revision=5&market_limit=24&include_children=true"
        )

        guard case .loaded(let expandedPresentation) = vm.state else {
            return XCTFail("Expected loaded state after loadMore")
        }
        XCTAssertNil(expandedPresentation.response.page?.nextCursor)
        let allIds = expandedPresentation.sections.flatMap { $0.members.map(\.memberId) }
        XCTAssertEqual(allIds, [501, 502], "Deferred market 502 must append after initial market 501")
    }

    func testMarketContinuationRequestMatchesServerNextUrlAndFirstPageIncludeChildrenScope() throws {
        let cursor = "eyJ2IjoxLCJvd24iOmZhbHNlLCJwIjpbMCwxLDUwMV19"
        let serverNextUrl = "/api/containers/nfl-2026-week-11?market_cursor=\(cursor)&market_revision=5&market_limit=24&include_children=true"

        let fromNextUrl = try ContainerHubService.marketContinuationRequest(
            slug: "nfl-2026-week-11",
            cursor: cursor,
            revision: 5,
            limit: 4,
            nextUrl: serverNextUrl
        )
        XCTAssertEqual(fromNextUrl.path, "/api/containers/nfl-2026-week-11")
        XCTAssertEqual(fromNextUrl.query["market_cursor"], cursor)
        XCTAssertEqual(fromNextUrl.query["market_revision"], "5")
        XCTAssertEqual(fromNextUrl.query["market_limit"], "24", "Should adopt PAGE_DEFAULT from server next_url rather than PREVIEW_LIMIT")
        XCTAssertEqual(fromNextUrl.query["include_children"], "true", "Should preserve server next_url include_children=true so own=False cursor never triggers 400 cursor_scope_mismatch")

        let fallback = try ContainerHubService.marketContinuationRequest(
            slug: "nfl-2026-week-11",
            cursor: cursor,
            revision: 5,
            limit: 24,
            nextUrl: nil
        )
        XCTAssertEqual(fallback.path, "/api/containers/nfl-2026-week-11")
        XCTAssertNil(fallback.query["include_children"], "Fallback continuation must omit include_children to match fetchContainerHub(slug:)'s backend default (include_children=True)")
        XCTAssertNotEqual(fallback.query["include_children"], "false")
    }
}
