import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class FollowAndMyStuff295ATests: XCTestCase {

    private func makeIsolatedDefaults() -> UserDefaults {
        let suiteName = "FollowAndMyStuff295ATests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeFeedItem(_ json: String) throws -> FeedItem {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func decodeTeamPage(_ json: String) throws -> TeamPageResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TeamPageResponse.self, from: Data(json.utf8))
    }

    // MARK: - 1. Follow (One Tap, No Account, Game Alerts Ask Once)

    func testFollowPersistsWithoutAccountAcrossTeamLeagueAndSet() {
        let defaults = makeIsolatedDefaults()
        let manager = FollowManager295A(defaults: defaults)

        let celtics = FollowedSubject295A.team(
            slug: "boston-celtics",
            teamId: 2,
            name: "Boston Celtics",
            sportKey: "basketball_nba"
        )
        let nba = FollowedSubject295A.league(slug: "nba", sportKey: "basketball_nba", name: "NBA")
        let oscars = FollowedSubject295A.set(slug: "oscars-2027", setKind: .container, name: "Oscars 2027")

        XCTAssertFalse(manager.hasFollows)
        XCTAssertTrue(manager.toggle(celtics))
        XCTAssertTrue(manager.isFollowing(celtics))

        XCTAssertTrue(manager.toggle(nba))
        XCTAssertTrue(manager.toggle(oscars))
        XCTAssertEqual(manager.subjects.count, 3)

        // Reload from UserDefaults with zero account signed in
        let reloaded = FollowManager295A(defaults: defaults)
        XCTAssertTrue(reloaded.isFollowing(celtics))
        XCTAssertTrue(reloaded.isFollowing(nba))
        XCTAssertTrue(reloaded.isFollowing(oscars))

        // Second tap unfollows
        XCTAssertFalse(reloaded.toggle(celtics))
        XCTAssertFalse(reloaded.isFollowing(celtics))
        XCTAssertEqual(reloaded.subjects.count, 2)
    }

    func testFollowingTeamOnGameCardMatchesTeamPageAndWithholdsIndividualSports() throws {
        let defaults = makeIsolatedDefaults()
        let manager = FollowManager295A(defaults: defaults)

        let nbaEvent = try decodeEvent("""
        {
          "id": 9001,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Boston Celtics",
          "away_team": "New York Knicks",
          "status": "scheduled",
          "commence_time": "2026-11-20T23:30:00Z",
          "home_team_data": {"team_id": 2, "slug": "boston-celtics", "primary_color": "#007A33", "abbreviation": "BOS"},
          "away_team_data": {"team_id": 18, "slug": "new-york-knicks", "primary_color": "#006BB6", "abbreviation": "NYK"}
        }
        """)

        let homeFromCard = try XCTUnwrap(FollowedSubject295A.teamFromEventSide(event: nbaEvent, isHome: true))
        let awayFromCard = try XCTUnwrap(FollowedSubject295A.teamFromEventSide(event: nbaEvent, isHome: false))
        XCTAssertEqual(homeFromCard.slug, "boston-celtics")
        XCTAssertEqual(awayFromCard.slug, "new-york-knicks")

        XCTAssertTrue(manager.toggle(homeFromCard))

        let celticsOnTeamPage = FollowedSubject295A.team(
            slug: "boston-celtics",
            teamId: 2,
            name: "Boston Celtics",
            sportKey: "basketball_nba"
        )
        XCTAssertTrue(manager.isFollowing(celticsOnTeamPage))
        XCTAssertFalse(manager.isFollowing(awayFromCard))

        let tennisMatch = try decodeEvent("""
        {
          "id": 9002,
          "sport": "tennis_atp",
          "home_team": "Jannik Sinner",
          "away_team": "Carlos Alcaraz",
          "status": "scheduled"
        }
        """)
        XCTAssertNil(FollowedSubject295A.teamFromEventSide(event: tennisMatch, isHome: true))
        XCTAssertNil(FollowedSubject295A.teamFromEventSide(event: tennisMatch, isHome: false))
    }

    func testFollowingTeamFromGameCardLandsOnMyStuffShowingTeamsNextGame() async throws {
        let defaults = makeIsolatedDefaults()
        let manager = FollowManager295A(defaults: defaults)

        let gameCardEvent = try decodeEvent("""
        {
          "id": 9003,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Miami Heat",
          "status": "scheduled",
          "commence_time": "2026-11-21T00:30:00Z",
          "away_team_data": {"team_id": 2, "slug": "boston-celtics", "primary_color": "#007A33", "abbreviation": "BOS"},
          "home_team_data": {"team_id": 14, "slug": "miami-heat", "primary_color": "#98002E", "abbreviation": "MIA"}
        }
        """)

        let cardTeams = FollowedSubject295A.eventCardTeams(for: gameCardEvent)
        let awayEntry = try XCTUnwrap(cardTeams.away)
        XCTAssertEqual(awayEntry.subject.slug, "boston-celtics")
        XCTAssertTrue(manager.toggle(awayEntry.subject))

        let nav = NavigationCoordinator()
        nav.applyLaunchLanding295A(followedCount: manager.subjects.count, pinnedCount: 0)
        XCTAssertEqual(nav.selectedTab, .myStuff)

        let emptyDiscoverDecoder = JSONDecoder()
        emptyDiscoverDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let emptyDiscover = try emptyDiscoverDecoder.decode(
            FeedResponse.self,
            from: Data(#"{"items":[],"total":0,"limit":20,"offset":0,"has_more":false}"#.utf8)
        )

        let teamPage = try makeSampleTeamPage()
        let vm = MyStuffLandingViewModel295A(
            defaults: defaults,
            subjectHydrator: { subjects in
                XCTAssertEqual(subjects.map(\.slug), ["boston-celtics"])
                var pack = MyStuffLandingViewModel295A.HydratedSubjectPack()
                for ev in teamPage.upcomingEvents {
                    let converted = SearchEventCardAdapter183A.fromTeamScheduleBrief(ev, team: teamPage.team)
                    pack.events.append((converted.feedEvent, converted.awayReadingIsServerVerified))
                }
                return [pack]
            },
            discoverFetcher: {
                emptyDiscover
            }
        )

        await vm.refresh(
            followedSubjects: manager.subjects,
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil
        )

        XCTAssertFalse(vm.loadFailed)
        XCTAssertEqual(vm.nextEvents.map { $0.event.id }, [15400201, 15400202])
        XCTAssertEqual(vm.nextEvents.first?.event.awayTeam, "Boston Celtics")
        XCTAssertEqual(vm.nextEvents.first?.event.homeTeam, "Washington Wizards")
    }

    func testGameAlertsPromptOffersOnceAndShares13083Keys() {
        let defaults = makeIsolatedDefaults()
        var permissionRequestedCount = 0
        let controller = GameAlertsPromptController295A(
            defaults: defaults,
            requestPermissionHandler: { permissionRequestedCount += 1 }
        )

        XCTAssertTrue(controller.shouldOffer)
        XCTAssertTrue(controller.offerInlineOnPage(contextId: "team-page:boston-celtics", subjectName: "Boston Celtics"))
        XCTAssertTrue(controller.showsInlineOffer(for: "team-page:boston-celtics"))

        // Declining records the choice in #13083's key and never nags on later follows or pins
        controller.declineOffer()
        XCTAssertFalse(controller.shouldOffer)
        XCTAssertTrue(defaults.bool(forKey: "bainluck.gameAlertsPinPromptHandled.13083"))
        XCTAssertFalse(defaults.bool(forKey: "bainluck.gameAlertsEnabled.13083"))
        XCTAssertFalse(controller.offerInlineOnPage(contextId: "team-page:knicks", subjectName: "New York Knicks"))
        XCTAssertFalse(controller.offerSheet(subjectName: "New York Knicks"))
        XCTAssertEqual(permissionRequestedCount, 0)

        // Fresh install where the reader taps "Turn on alerts"
        let defaults2 = makeIsolatedDefaults()
        let exp = expectation(description: "permission requested")
        let controller2 = GameAlertsPromptController295A(
            defaults: defaults2,
            requestPermissionHandler: { exp.fulfill() }
        )
        XCTAssertTrue(controller2.offerInlineOnPage(contextId: "team-page:celtics", subjectName: "Boston Celtics"))
        controller2.acceptOffer()
        wait(for: [exp], timeout: 1.0)
        XCTAssertTrue(defaults2.bool(forKey: "bainluck.gameAlertsEnabled.13083"))
        XCTAssertTrue(defaults2.bool(forKey: "bainluck.gameAlertsPinPromptHandled.13083"))
        XCTAssertFalse(controller2.shouldOffer)
    }

    // MARK: - 2. My Stuff First & Leftmost Tab Bar

    func testLaunchLandingOpensMyStuffWhenFollowedOrPinnedElseDiscover() {
        XCTAssertEqual(
            MyStuffLandingRule295A.orderedTabs,
            [.myStuff, .discover, .feed, .leagues, .search]
        )
        XCTAssertEqual(
            MacMainWindow10878.destinations.map(\.tab),
            [.myStuff, .discover, .feed, .leagues, .search]
        )

        // Nothing followed or pinned -> Discover
        let emptyNav = NavigationCoordinator()
        emptyNav.applyLaunchLanding295A(followedCount: 0, pinnedCount: 0)
        XCTAssertEqual(emptyNav.selectedTab, .discover)

        // Followed >= 1 -> My Stuff
        let followedNav = NavigationCoordinator()
        followedNav.applyLaunchLanding295A(followedCount: 1, pinnedCount: 0)
        XCTAssertEqual(followedNav.selectedTab, .myStuff)

        // Pinned >= 1 -> My Stuff
        let pinnedNav = NavigationCoordinator()
        pinnedNav.applyLaunchLanding295A(followedCount: 0, pinnedCount: 1)
        XCTAssertEqual(pinnedNav.selectedTab, .myStuff)

        // Deep link before launch landing is never overridden
        let deepLinkNav = NavigationCoordinator()
        XCTAssertTrue(deepLinkNav.handleURL(URL(string: "bainluck://events/15350936")!))
        XCTAssertEqual(deepLinkNav.selectedTab, .feed)
        deepLinkNav.applyLaunchLanding295A(followedCount: 2, pinnedCount: 1)
        XCTAssertEqual(deepLinkNav.selectedTab, .feed)
    }

    // MARK: - 3. My Stuff Worth Landing On (Order, Points, Zero Model Text)

    func testVisitLedgerFormatsMovesInPointsAndStripsModelText() throws {
        XCTAssertNil(MyStuffVisitLedger295A.formatPointMove(deltaProbability: 0.01, sinceLastVisit: true))

        let upSinceVisit = try XCTUnwrap(
            MyStuffVisitLedger295A.formatPointMove(deltaProbability: 0.064, sinceLastVisit: true)
        )
        XCTAssertEqual(upSinceVisit.points, 6)
        XCTAssertEqual(upSinceVisit.text, "Up 6 points since your last visit")
        XCTAssertFalse(upSinceVisit.text.contains("%"))

        let downToday = try XCTUnwrap(
            MyStuffVisitLedger295A.formatPointMove(deltaProbability: -0.042, sinceLastVisit: false)
        )
        XCTAssertEqual(downToday.points, 4)
        XCTAssertEqual(downToday.text, "Down 4 points today")

        let itemWithModelText = try decodeFeedItem("""
        {
          "type": "futures",
          "score": 88.0,
          "reason": "AI hook sentence that should not appear",
          "headline": "Model headline",
          "context_summary": "Model summary",
          "data": {
            "id": 777,
            "name": "NBA Championship 2027",
            "llm_sport_category": "basketball",
            "hook_description": "LLM hook description",
            "top_outcomes": [
              {"id": 1, "name": "Boston Celtics", "probability": 0.24, "rank": 1}
            ]
          }
        }
        """)

        let sanitized = MyStuffLandingViewModel295A.stripModelWrittenText([itemWithModelText], limit: 3)
        XCTAssertEqual(sanitized.count, 1)
        XCTAssertNil(sanitized[0].reason)
        XCTAssertNil(sanitized[0].headline)
        XCTAssertNil(sanitized[0].contextSummary)
        XCTAssertNil(sanitized[0].futures?.hookDescription)
    }

    func testMovedEventSummaryHonorsSinceOpeningWithheldAwayOpeningSourceAndDrawSports() throws {
        // 1. First-time reader (no prior ledger reading): opening -> current move says "since opening", never "today"
        let nbaOpeningMove = try decodeFeedItem("""
        {
          "type": "event",
          "score": 80.0,
          "data": {
            "id": 99101,
            "sport": "basketball_nba",
            "away_team": "Miami Heat",
            "home_team": "Boston Celtics",
            "status": "scheduled",
            "current_odds": {"away_probability": 0.34, "home_probability": 0.66},
            "opening_odds": {"away_probability": 0.41, "home_probability": 0.59}
          }
        }
        """).event!
        let openingSummary = try XCTUnwrap(
            MyStuffLandingViewModel295A.movedEventSummary(
                for: nbaOpeningMove,
                awayVerified: true,
                priorHomeProbability: nil
            )
        )
        XCTAssertEqual(openingSummary.points, 7)
        XCTAssertEqual(openingSummary.summary, "Celtics up 7 points since opening")
        XCTAssertFalse(openingSummary.summary.contains("today"))

        // 2. Prior visit ledger reading says "since your last visit" and attributes negative home delta to verified away side
        let awayVisitMove = try XCTUnwrap(
            MyStuffLandingViewModel295A.movedEventSummary(
                for: nbaOpeningMove,
                awayVerified: true,
                priorHomeProbability: 0.72
            )
        )
        XCTAssertEqual(awayVisitMove.points, 6)
        XCTAssertEqual(awayVisitMove.summary, "Heat up 6 points since your last visit")

        // 3. Withheld away reading (`away_probability: null`) never attributes a move to the away team
        let withheldAway = try decodeFeedItem("""
        {
          "type": "event",
          "score": 80.0,
          "data": {
            "id": 99102,
            "sport": "basketball_nba",
            "away_team": "Miami Heat",
            "home_team": "Boston Celtics",
            "status": "scheduled",
            "current_odds": {"home_probability": 0.52},
            "opening_odds": {"away_probability": 0.40, "home_probability": 0.60}
          }
        }
        """).event!
        XCTAssertNil(
            MyStuffLandingViewModel295A.movedEventSummary(
                for: withheldAway,
                awayVerified: false,
                priorHomeProbability: 0.60
            )
        )

        // 4. `hero_probability_source == "opening"` (withheld by `CompactGameCard12616.currentOddsForCard`) produces no move banner
        let openingOnlyCard = try decodeFeedItem("""
        {
          "type": "event",
          "score": 80.0,
          "data": {
            "id": 99103,
            "sport": "basketball_nba",
            "away_team": "Miami Heat",
            "home_team": "Boston Celtics",
            "status": "scheduled",
            "hero_probability_source": "opening",
            "current_odds": {"away_probability": 0.34, "home_probability": 0.66},
            "opening_odds": {"away_probability": 0.41, "home_probability": 0.59}
          }
        }
        """).event!
        XCTAssertNil(
            MyStuffLandingViewModel295A.movedEventSummary(
                for: openingOnlyCard,
                awayVerified: true,
                priorHomeProbability: 0.58
            )
        )

        // 5. Three-way / draw-capable sport (`soccer_epl`) skips moved-game attribution
        let soccerGame = try decodeFeedItem("""
        {
          "type": "event",
          "score": 80.0,
          "data": {
            "id": 99104,
            "sport": "soccer_epl",
            "away_team": "Liverpool",
            "home_team": "Arsenal",
            "status": "scheduled",
            "current_odds": {"away_probability": 0.35, "home_probability": 0.40, "draw_probability": 0.25},
            "opening_odds": {"away_probability": 0.28, "home_probability": 0.50}
          }
        }
        """).event!
        XCTAssertNil(
            MyStuffLandingViewModel295A.movedEventSummary(
                for: soccerGame,
                awayVerified: true,
                priorHomeProbability: 0.50
            )
        )
    }

    func testFailedRefreshSetsLoadFailedPreservesExistingSectionsAndExplicitIdsWinInMatches() async throws {
        // 1. Explicit teamId wins over identical team name; missing sportKey never name-matches
        let nflGiants = FollowedSubject295A.team(slug: "new-york-giants", teamId: 19, name: "Giants", sportKey: "americanfootball_nfl")
        let mlbGiants = FollowedSubject295A.team(slug: "san-francisco-giants", teamId: 26, name: "Giants", sportKey: "baseball_mlb")
        let idlessUnknownSport = FollowedSubject295A.team(slug: "999", teamId: nil, name: "Giants", sportKey: nil)
        XCTAssertFalse(nflGiants.matches(mlbGiants), "Different teamIds must never match even when names match")
        XCTAssertFalse(nflGiants.matches(idlessUnknownSport), "Subject with a teamId must not name-match an id-less subject")

        // 2. Failed network fetch surfaces `loadFailed == true` and preserves previously loaded sections
        struct SimulatedOfflineError: Error {}
        let defaults = makeIsolatedDefaults()
        let vm = MyStuffLandingViewModel295A(
            defaults: defaults,
            subjectHydrator: { _ in
                [MyStuffLandingViewModel295A.HydratedSubjectPack(events: [], markets: [], didFail: true)]
            },
            discoverFetcher: {
                throw SimulatedOfflineError()
            }
        )

        let celtics = FollowedSubject295A.team(slug: "boston-celtics", teamId: 2, name: "Boston Celtics", sportKey: "basketball_nba")
        await vm.refresh(
            followedSubjects: [celtics],
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil
        )
        XCTAssertTrue(vm.loadFailed, "Cold offline failure must set loadFailed rather than masquerading as empty data")

        // Seed existing sections, then fail a subsequent refresh -> sections remain intact!
        let sample = try makeSampleLandingSnapshot()
        vm.seedSectionsForTesting(sample)
        XCTAssertFalse(vm.liveEvents.isEmpty)
        XCTAssertFalse(vm.loadFailed)

        await vm.refresh(
            followedSubjects: [celtics],
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil
        )
        XCTAssertTrue(vm.loadFailed, "Failed refresh must set loadFailed")
        XCTAssertEqual(vm.liveEvents.count, sample.liveEvents.count, "Failed refresh must preserve existing live section")
        XCTAssertEqual(vm.nextEvents.count, sample.nextEvents.count, "Failed refresh must preserve existing next section")
    }

    // MARK: - 4. OCR + Zero-Truncation Verification (+ Optional 390 pt Render Export)

    func testRenderedMyStuffLandingAndTeamFollowHaveZeroEllipsis390() throws {
        let sampleSnapshot = try makeSampleLandingSnapshot()
        let teamPage = try makeSampleTeamPage()

        let defaultsBefore = makeIsolatedDefaults()
        let followBefore = FollowManager295A(defaults: defaultsBefore)
        let alertsBefore = GameAlertsPromptController295A(defaults: defaultsBefore, requestPermissionHandler: {})

        let defaultsAfter = makeIsolatedDefaults()
        let followAfter = FollowManager295A(defaults: defaultsAfter)
        let alertsAfter = GameAlertsPromptController295A(defaults: defaultsAfter, requestPermissionHandler: {})
        let celticsSubject = FollowedSubject295A.team(
            slug: "boston-celtics",
            teamId: 2,
            name: "Boston Celtics",
            sportKey: "basketball_nba",
            primaryColor: "#007A33"
        )
        _ = followAfter.toggle(celticsSubject)
        _ = alertsAfter.offerInlineOnPage(contextId: "team-page:boston-celtics", subjectName: "Boston Celtics")

        let pinDefaults = makeIsolatedDefaults()
        let pinManager = PinManager(defaults: pinDefaults, allowLegacyGuestPins: false)
        _ = pinManager.togglePin(type: "event", id: 15400102)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let landingImg = renderInWindow(
                width: 390,
                height: 1420,
                scheme: scheme
            ) {
                NavigationStack {
                    MyStuffLandingView295A(
                        landingVM: MyStuffLandingViewModel295A(preloaded: sampleSnapshot),
                        path: .constant(NavigationPath()),
                        onOpenDiscover: {},
                        onManagePins: {},
                        onRefresh: {}
                    )
                    .navigationTitle("My Stuff")
                    .navigationBarTitleDisplayMode(.large)
                }
                .environment(\.followManager295A, followAfter)
                .environment(\.gameAlertsPrompt295A, alertsAfter)
                .environmentObject(pinManager)
            }
            let landingOCR = recognizeText(in: landingImg)
            XCTAssertFalse(landingOCR.contains("…"), "Ellipsis found in My Stuff (\(scheme)): \(landingOCR)")
            XCTAssertTrue(landingOCR.contains("Live now"), "Missing Live now in \(landingOCR)")
            XCTAssertTrue(landingOCR.contains("Next for you"), "Missing Next for you in \(landingOCR)")
            XCTAssertTrue(landingOCR.contains("Moved since your last visit"), "Missing Moved section in \(landingOCR)")
            XCTAssertTrue(landingOCR.contains("From Discover"), "Missing From Discover in \(landingOCR)")
            XCTAssertTrue(landingOCR.contains("See all on Discover"), "Missing Discover link in \(landingOCR)")

            let beforeImg = renderInWindow(width: 390, height: 780, scheme: scheme) {
                NavigationStack {
                    TeamDetailView(slug: "boston-celtics", loadedPageForTest: teamPage)
                        .navigationBarTitleDisplayMode(.inline)
                }
                .environment(\.followManager295A, followBefore)
                .environment(\.gameAlertsPrompt295A, alertsBefore)
                .environmentObject(pinManager)
            }
            let beforeOCR = recognizeText(in: beforeImg)
            XCTAssertFalse(beforeOCR.contains("…"), "Ellipsis found on Team before Follow (\(scheme)): \(beforeOCR)")
            XCTAssertTrue(beforeOCR.contains("Follow"), "Missing Follow button in \(beforeOCR)")

            let afterImg = renderInWindow(width: 390, height: 840, scheme: scheme) {
                NavigationStack {
                    TeamDetailView(slug: "boston-celtics", loadedPageForTest: teamPage)
                        .navigationBarTitleDisplayMode(.inline)
                }
                .environment(\.followManager295A, followAfter)
                .environment(\.gameAlertsPrompt295A, alertsAfter)
                .environmentObject(pinManager)
            }
            let afterOCR = recognizeText(in: afterImg)
            XCTAssertFalse(afterOCR.contains("…"), "Ellipsis found on Team after Follow (\(scheme)): \(afterOCR)")
            XCTAssertTrue(afterOCR.contains("Following"), "Missing Following state in \(afterOCR)")
            XCTAssertTrue(afterOCR.contains("Want game alerts"), "Missing game alerts offer in \(afterOCR)")
        }

        if let outDir = ProcessInfo.processInfo.environment["BC_RENDER_DIR_295A"], !outDir.isEmpty {
            try export390Renders(
                to: URL(fileURLWithPath: outDir, isDirectory: true),
                snapshot: sampleSnapshot,
                teamPage: teamPage,
                followBefore: followBefore,
                alertsBefore: alertsBefore,
                followAfter: followAfter,
                alertsAfter: alertsAfter,
                pinManager: pinManager
            )
        }
    }

    // MARK: - Helpers

    private func export390Renders(
        to dir: URL,
        snapshot: MyStuffLandingViewModel295A.PreloadedSnapshot,
        teamPage: TeamPageResponse,
        followBefore: FollowManager295A,
        alertsBefore: GameAlertsPromptController295A,
        followAfter: FollowManager295A,
        alertsAfter: GameAlertsPromptController295A,
        pinManager: PinManager
    ) throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        var preloadedLogos: [URL: Image] = [:]
        if let logoPath = ProcessInfo.processInfo.environment["BC_CELTICS_LOGO_PATH"],
           let uiImg = UIImage(contentsOfFile: logoPath),
           let url = URL(string: "https://a.espncdn.com/i/teamlogos/nba/500/bos.png") {
            preloadedLogos[url] = Image(uiImage: uiImg)
        }

        for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            // 1. My Stuff as the landing (with bottom TabView showing My Stuff leftmost & active)
            let landingTabImg = renderInWindow(width: 390, height: 1460, scheme: scheme) {
                TabView(selection: .constant(AppTab.myStuff)) {
                    NavigationStack {
                        MyStuffLandingView295A(
                            landingVM: MyStuffLandingViewModel295A(preloaded: snapshot),
                            path: .constant(NavigationPath()),
                            onOpenDiscover: {},
                            onManagePins: {},
                            onRefresh: {}
                        )
                        .navigationTitle("My Stuff")
                        .navigationBarTitleDisplayMode(.large)
                    }
                    .tabItem { Label("My Stuff", systemImage: "person.fill") }
                    .tag(AppTab.myStuff)

                    Color.clear
                        .tabItem { Label("Discover", systemImage: "safari") }
                        .tag(AppTab.discover)

                    Color.clear
                        .tabItem { Label("Sports", systemImage: "rectangle.stack.fill") }
                        .tag(AppTab.feed)

                    Color.clear
                        .tabItem { Label("Browse", systemImage: "square.grid.2x2") }
                        .tag(AppTab.leagues)

                    Color.clear
                        .tabItem { Label("Search", systemImage: "magnifyingglass") }
                        .tag(AppTab.search)
                }
                .environment(\.followManager295A, followAfter)
                .environment(\.gameAlertsPrompt295A, alertsAfter)
                .environmentObject(pinManager)
            }
            try landingTabImg.pngData()?.write(to: dir.appendingPathComponent("295a-mystuff-landing-\(suffix)-390.png"))

            // 2. Team page BEFORE the Follow tap
            let teamBeforeImg = renderInWindow(width: 390, height: 844, scheme: scheme) {
                NavigationStack {
                    TeamDetailView(
                        slug: "boston-celtics",
                        loadedPageForTest: teamPage,
                        preloadedAvatarImagesForTest: preloadedLogos
                    )
                    .navigationBarTitleDisplayMode(.inline)
                }
                .environment(\.followManager295A, followBefore)
                .environment(\.gameAlertsPrompt295A, alertsBefore)
                .environmentObject(pinManager)
            }
            try teamBeforeImg.pngData()?.write(to: dir.appendingPathComponent("295a-team-before-follow-\(suffix)-390.png"))

            // 3. Team page AFTER the Follow tap (Following + inline game alerts ask)
            let teamAfterImg = renderInWindow(width: 390, height: 844, scheme: scheme) {
                NavigationStack {
                    TeamDetailView(
                        slug: "boston-celtics",
                        loadedPageForTest: teamPage,
                        preloadedAvatarImagesForTest: preloadedLogos
                    )
                    .navigationBarTitleDisplayMode(.inline)
                }
                .environment(\.followManager295A, followAfter)
                .environment(\.gameAlertsPrompt295A, alertsAfter)
                .environmentObject(pinManager)
            }
            try teamAfterImg.pngData()?.write(to: dir.appendingPathComponent("295a-team-after-follow-\(suffix)-390.png"))

            // 4. Tab bar at 390 pt (viewport-height 844 cropped to bottom 140 pt so the tab bar order is unmistakable)
            let viewportImg = renderInWindow(width: 390, height: 844, scheme: scheme) {
                TabView(selection: .constant(AppTab.myStuff)) {
                    NavigationStack {
                        MyStuffLandingView295A(
                            landingVM: MyStuffLandingViewModel295A(preloaded: snapshot),
                            path: .constant(NavigationPath()),
                            onOpenDiscover: {},
                            onManagePins: {},
                            onRefresh: {}
                        )
                        .navigationTitle("My Stuff")
                        .navigationBarTitleDisplayMode(.large)
                    }
                    .tabItem { Label("My Stuff", systemImage: "person.fill") }
                    .tag(AppTab.myStuff)

                    Color.clear
                        .tabItem { Label("Discover", systemImage: "safari") }
                        .tag(AppTab.discover)

                    Color.clear
                        .tabItem { Label("Sports", systemImage: "rectangle.stack.fill") }
                        .tag(AppTab.feed)
                        .badge("4 live")

                    Color.clear
                        .tabItem { Label("Browse", systemImage: "square.grid.2x2") }
                        .tag(AppTab.leagues)

                    Color.clear
                        .tabItem { Label("Search", systemImage: "magnifyingglass") }
                        .tag(AppTab.search)
                }
                .environment(\.followManager295A, followAfter)
                .environment(\.gameAlertsPrompt295A, alertsAfter)
                .environmentObject(pinManager)
            }
            let croppedBar = cropBottom(of: viewportImg, heightPoints: 120)
            try croppedBar.pngData()?.write(to: dir.appendingPathComponent("295a-tab-bar-\(suffix)-390.png"))
        }
    }

    private func cropBottom(of image: UIImage, heightPoints: CGFloat) -> UIImage {
        let scale = image.scale
        let cropPxHeight = heightPoints * scale
        let fullPxWidth = image.size.width * scale
        let fullPxHeight = image.size.height * scale
        let rect = CGRect(x: 0, y: max(0, fullPxHeight - cropPxHeight), width: fullPxWidth, height: cropPxHeight)
        guard let cg = image.cgImage?.cropping(to: rect) else { return image }
        return UIImage(cgImage: cg, scale: scale, orientation: image.imageOrientation)
    }

    private func renderInWindow<V: View>(
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        @ViewBuilder content: () -> V
    ) -> UIImage {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let root = content()
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)
            .environmentObject(NavigationCoordinator())
        let host = hostForMeasurement(root)
        host.overrideUserInterfaceStyle = style
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = rect

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: rect)
        }
        window.frame = rect
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.20)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let rendererFormat = UIGraphicsImageRendererFormat()
        rendererFormat.scale = 3.0
        rendererFormat.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: rendererFormat).image { ctx in
            let bg = (scheme == .dark)
                ? UIColor(red: 0.059, green: 0.067, blue: 0.082, alpha: 1.0)
                : UIColor.white
            bg.setFill()
            ctx.fill(host.view.bounds)
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cgImage = image.cgImage else { return "" }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try? handler.perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return lines.joined(separator: " | ")
    }

    private func makeSampleLandingSnapshot() throws -> MyStuffLandingViewModel295A.PreloadedSnapshot {
        let liveGame = try decodeEvent("""
        {
          "id": 15400101,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Cleveland Cavaliers",
          "home_team": "Boston Celtics",
          "commence_time": "2026-11-20T17:00:00Z",
          "status": "live",
          "away_score": 84,
          "home_score": 89,
          "espn": {"period": "Q3", "game_clock": "4:12"},
          "away_team_data": {"team_id": 5, "slug": "cleveland-cavaliers", "primary_color": "#860038", "abbreviation": "CLE"},
          "home_team_data": {"team_id": 2, "slug": "boston-celtics", "primary_color": "#007A33", "abbreviation": "BOS"},
          "prematch_odds": {"away_probability": 0.44, "home_probability": 0.56, "away_rendered_percent": 44, "home_rendered_percent": 56},
          "current_odds": {"away_probability": 0.312, "home_probability": 0.688, "projected_away_score": 111.0, "projected_home_score": 116.0}
        }
        """)

        let nextGame = try decodeEvent("""
        {
          "id": 15400102,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Buffalo Bills",
          "home_team": "Detroit Lions",
          "commence_time": "2026-11-22T21:25:00Z",
          "status": "scheduled",
          "away_team_data": {"team_id": 32, "slug": "buffalo-bills", "primary_color": "#00338D", "abbreviation": "BUF"},
          "home_team_data": {"team_id": 38, "slug": "detroit-lions", "primary_color": "#0076B6", "abbreviation": "DET"},
          "pregame_projection": {"away": 26, "home": 28},
          "current_odds": {"away_probability": 0.46, "home_probability": 0.54, "away_rendered_percent": 46, "home_rendered_percent": 54}
        }
        """)

        let movedMarket = MyStuffMarketItem295A(
            id: "8801:boston-celtics",
            marketId: 8801,
            marketTitle: "NBA Championship",
            outcomeLabel: "Boston Celtics",
            subjectName: "Boston Celtics",
            logoUrl: nil,
            primaryColor: "#007A33",
            probability: 0.24,
            changePoints: 5,
            movementNote: "Up 5 points since your last visit",
            sourceMark: nil
        )

        let discover1 = try decodeFeedItem("""
        {
          "type": "futures",
          "score": 92.0,
          "data": {
            "id": 9901,
            "name": "Oscars Best Picture 2027",
            "llm_sport_category": "entertainment",
            "source_count": 2,
            "top_outcomes": [
              {"id": 1, "name": "One Battle After Another", "probability": 0.31, "rank": 1},
              {"id": 2, "name": "Hamnet", "probability": 0.21, "rank": 2}
            ]
          }
        }
        """)

        let discover2 = try decodeFeedItem("""
        {
          "type": "futures",
          "score": 89.0,
          "data": {
            "id": 9902,
            "name": "Federal Reserve December Rate Decision",
            "llm_sport_category": "economics",
            "source_count": 2,
            "top_outcomes": [
              {"id": 3, "name": "Cut a quarter point", "probability": 0.68, "rank": 1},
              {"id": 4, "name": "Hold steady", "probability": 0.29, "rank": 2}
            ]
          }
        }
        """)

        return MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: [(liveGame, false)],
            nextEvents: [(nextGame, false)],
            nextMarkets: [],
            movedEntries: [
                MyStuffMovedEntry295A(
                    id: "moved-8801",
                    movementSummary: "Up 5 points since your last visit",
                    magnitudePoints: 5,
                    payload: .market(movedMarket)
                )
            ],
            discoverItems: [discover1, discover2]
        )
    }

    private func makeSampleTeamPage() throws -> TeamPageResponse {
        try decodeTeamPage("""
        {
          "team": {
            "id": 2,
            "slug": "boston-celtics",
            "name": "Boston Celtics",
            "abbreviation": "BOS",
            "location": "Boston",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#007A33",
            "secondary_color": "#BA9653",
            "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
            "logo_large": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
            "record": "12-3"
          },
          "championship_path": [
            {"tier": 1, "label": "Make Playoffs", "market_name": "Make Playoffs", "market_id": 8803, "probability": 0.96, "rank": 1},
            {"tier": 2, "label": "Eastern Conference", "market_name": "Eastern Conference", "market_id": 8802, "probability": 0.42, "rank": 1},
            {"tier": 3, "label": "NBA Champion", "market_name": "NBA Champion", "market_id": 8801, "probability": 0.24, "rank": 1}
          ],
          "upcoming_events": [
            {
              "id": 15400201,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "away_team": "Boston Celtics",
              "home_team": "Washington Wizards",
              "commence_time": "2026-11-22T00:00:00Z",
              "status": "scheduled",
              "hero_probability": 0.18,
              "hero_probability_away": 0.82
            },
            {
              "id": 15400202,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "away_team": "Minnesota Timberwolves",
              "home_team": "Boston Celtics",
              "commence_time": "2026-11-24T20:30:00Z",
              "status": "scheduled",
              "hero_probability": 0.64,
              "hero_probability_away": 0.36
            }
          ],
          "recent_events": [
            {
              "id": 15400199,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "away_team": "Cleveland Cavaliers",
              "home_team": "Boston Celtics",
              "commence_time": "2026-11-19T00:00:00Z",
              "status": "final",
              "away_score": 117,
              "home_score": 120,
              "prematch_odds": {"away_probability": 0.45, "home_probability": 0.55, "away_rendered_percent": 45, "home_rendered_percent": 55}
            }
          ],
          "futures": []
        }
        """)
    }
}
