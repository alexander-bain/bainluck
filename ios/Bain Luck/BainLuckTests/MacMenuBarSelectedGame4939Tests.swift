import XCTest
#if os(macOS)
import AppKit
import SwiftUI
#endif
@testable import Bain_Luck

/// #4939 (M1 under #4931) — Check one explicitly selected game's score, state,
/// named win probability, settlement result, and producer observation age from
/// the Mac menu bar, then open that exact game with one click.
///
/// Tests the pure model, persistence/lifecycle store, single-flight refresh,
/// account-switch clearing, error/unavailable handling, and the shipping
/// `MenuBarView.swift` source contracts. Interactive desktop menu-bar rendering,
/// sleep/wake, and VoiceOver navigation remain mounted Mac acceptance.
@MainActor
final class MacMenuBarSelectedGame4939Tests: XCTestCase {
    private var suiteName: String!
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        suiteName = "MacMenuBarSelectedGame4939Tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
        defaults.removePersistentDomain(forName: suiteName)
    }

    override func tearDown() {
        if let suiteName {
            defaults?.removePersistentDomain(forName: suiteName)
        }
        defaults = nil
        suiteName = nil
        super.tearDown()
    }

    // MARK: - 1. Explicit Selection, Restart Persistence, Change & Clear

    func testSelectGamePersistsAcrossRestartAndRestoresSavedReading() async {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let celticsKnicks = Self.makeLiveTwoWaySnapshot(id: 15340001, awayScore: 84, homeScore: 79)
        let refreshed = Self.makeLiveTwoWaySnapshot(id: 15340001, awayScore: 87, homeScore: 81)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [15340001: refreshed],
            candidates: [celticsKnicks]
        )

        let firstStore = MacMenuBarSelectedGameStore4939(
            dataSource: dataSource,
            defaults: defaults,
            now: { now }
        )
        firstStore.selectGame(celticsKnicks)
        await firstStore.refresh()

        XCTAssertEqual(firstStore.selectedEventID, 15340001)
        XCTAssertEqual(firstStore.selectedGame?.awayScore, 87)
        XCTAssertEqual(firstStore.selectedGame?.homeScore, 81)
        XCTAssertFalse(firstStore.isShowingPersistedSnapshot)

        // Simulate app restart with a new store reading the same UserDefaults.
        let restartedStore = MacMenuBarSelectedGameStore4939(
            dataSource: dataSource,
            defaults: defaults,
            now: { now }
        )
        XCTAssertEqual(restartedStore.selectedEventID, 15340001)
        XCTAssertEqual(restartedStore.selectedGame?.awayScore, 87)
        XCTAssertTrue(
            restartedStore.isShowingPersistedSnapshot,
            "cold start before network confirmation must mark the restored reading as a saved snapshot"
        )

        await restartedStore.refresh()
        XCTAssertFalse(restartedStore.isShowingPersistedSnapshot)
        XCTAssertEqual(restartedStore.phase, .loaded)
    }

    func testFinalResultRemainsUntilChangedOrCleared() async {
        let now = ISO8601Stamp.date("2026-10-22T23:00:00Z")!
        let liveGame = Self.makeLiveTwoWaySnapshot(id: 15330459, awayScore: 1, homeScore: 3)
        let finalGame = MacMenuBarGameSnapshot4939(
            id: 15330459,
            sportKey: "baseball_mlb",
            sportLabel: "MLB",
            awayTeam: "Milwaukee Brewers",
            homeTeam: "Los Angeles Dodgers",
            awayAbbrev: "Brewers",
            homeAbbrev: "Dodgers",
            status: "completed",
            commenceTime: "2026-10-15T20:00:00Z",
            startIsTbd: false,
            awayScore: 1,
            homeScore: 5,
            liveClockText: nil,
            awayWinPercent: 18,
            homeWinPercent: 82,
            winnerMarketPricesADraw: false,
            heroSettledResult: "home",
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: nil,
            scoreObservedAt: "2026-10-15T23:10:00Z",
            probabilityObservedAt: "2026-10-15T23:10:00Z"
        )
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [15330459: finalGame],
            candidates: []
        )
        let store = MacMenuBarSelectedGameStore4939(
            dataSource: dataSource,
            defaults: defaults,
            now: { now }
        )
        store.selectGame(liveGame)
        await store.refresh()

        XCTAssertEqual(store.selectedEventID, 15330459)
        XCTAssertEqual(store.selectedGame?.statusBadgeText(now: now), "FINAL")
        XCTAssertEqual(store.selectedGame?.settledVerdictText(now: now), "Dodgers won")
        XCTAssertNil(
            store.selectedGame?.namedProbabilityLine(now: now),
            "settled games must not print a live win probability forecast"
        )
    }

    func testBeginAndCancelChangePreservesSelectedGame() async {
        let celtics = Self.makeLiveTwoWaySnapshot(id: 15340001, awayScore: 84, homeScore: 79)
        let lakers = Self.makeLiveTwoWaySnapshot(id: 15340002, awayScore: 52, homeScore: 55)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [15340001: celtics, 15340002: lakers],
            candidates: [celtics, lakers]
        )
        let store = MacMenuBarSelectedGameStore4939(dataSource: dataSource, defaults: defaults)
        store.selectGame(celtics)
        await store.refresh()

        store.beginChangingGame()
        XCTAssertTrue(store.isChoosingGame)
        XCTAssertEqual(store.selectedGame?.id, 15340001)

        store.cancelChangingGame()
        XCTAssertFalse(store.isChoosingGame)
        XCTAssertEqual(store.selectedGame?.id, 15340001)
    }

    func testClearSelectionRemovesPersistedStateAndLoadsCandidates() async {
        let celtics = Self.makeLiveTwoWaySnapshot(id: 15340001, awayScore: 84, homeScore: 79)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [15340001: celtics],
            candidates: [celtics]
        )
        let store = MacMenuBarSelectedGameStore4939(dataSource: dataSource, defaults: defaults)
        store.selectGame(celtics)
        await store.refresh()

        store.clearSelection()
        await store.refresh()

        XCTAssertNil(store.selectedEventID)
        XCTAssertNil(store.selectedGame)
        XCTAssertNil(defaults.object(forKey: MacMenuBarSelectedGameStore4939.selectedEventIDKey))
        XCTAssertNil(defaults.data(forKey: MacMenuBarSelectedGameStore4939.selectedSnapshotKey))
        XCTAssertEqual(store.candidateGames.map(\.id), [15340001])
    }

    // MARK: - 2. Account Switch / Sign-Out Scoping

    func testAccountSwitchClearsPreviousUsersPersistedSelection() async {
        let celtics = Self.makeLiveTwoWaySnapshot(id: 15340001, awayScore: 84, homeScore: 79)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [15340001: celtics],
            candidates: [celtics]
        )
        let store = MacMenuBarSelectedGameStore4939(dataSource: dataSource, defaults: defaults)
        store.syncAccount(ownerID: "42")
        store.selectGame(celtics)
        await store.refresh()
        XCTAssertEqual(store.selectedEventID, 15340001)

        // Same user does not clear selection.
        store.syncAccount(ownerID: "42")
        XCTAssertEqual(store.selectedEventID, 15340001)

        // Sign-out or switching to another user clears the previous user's selection.
        store.syncAccount(ownerID: nil)
        XCTAssertNil(store.selectedEventID)
        XCTAssertNil(store.selectedGame)
    }

    // MARK: - 3. Honest Score, State, Named Probability & Settlement Truth

    func testMissingScoreNeverRendersAsZero() {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let scheduledNilScore = MacMenuBarGameSnapshot4939(
            id: 15340010,
            sportKey: "baseball_mlb",
            sportLabel: "MLB",
            awayTeam: "Los Angeles Dodgers",
            homeTeam: "New York Yankees",
            awayAbbrev: "Dodgers",
            homeAbbrev: "Yankees",
            status: "scheduled",
            commenceTime: "2026-10-23T00:08:00Z",
            startIsTbd: false,
            awayScore: nil,
            homeScore: nil,
            liveClockText: nil,
            awayWinPercent: 54,
            homeWinPercent: 46,
            winnerMarketPricesADraw: false,
            heroSettledResult: nil,
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: nil,
            scoreObservedAt: nil,
            probabilityObservedAt: "2026-10-22T19:55:00Z"
        )
        XCTAssertEqual(scheduledNilScore.awayScoreText, "—")
        XCTAssertEqual(scheduledNilScore.homeScoreText, "—")
        XCTAssertFalse(scheduledNilScore.hasBothScores)
        XCTAssertTrue(scheduledNilScore.accessibilitySummary(now: now).contains("Score not yet reported"))

        let realZeroScore = Self.makeLiveTwoWaySnapshot(id: 15340011, awayScore: 0, homeScore: 0)
        XCTAssertEqual(realZeroScore.awayScoreText, "0")
        XCTAssertEqual(realZeroScore.homeScoreText, "0")
        XCTAssertTrue(realZeroScore.hasBothScores)
    }

    func testTwoWayGameRendersBothNamedWinProbabilitiesAndSumsTo100() {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let odds = CurrentOdds(
            capturedAt: "2026-10-22T19:59:00Z",
            homeProbability: 0.495,
            awayProbability: 0.505,
            homeRenderedPercent: 49,
            awayRenderedPercent: 51,
            spread: nil,
            homeSpread: nil,
            overUnder: nil,
            projectedHomeScore: nil,
            projectedAwayScore: nil,
            bookmakerCount: 6
        )
        let resolved = MacMenuBarGameSnapshot4939.resolvePrintedPercentages(
            sportKey: "basketball_nba",
            currentOdds: odds,
            heroProbability: nil,
            openingOdds: nil
        )
        XCTAssertEqual(resolved.awayPercent, 51)
        XCTAssertEqual(resolved.homePercent, 49)
        XCTAssertFalse(resolved.pricesADraw)

        let game = Self.makeLiveTwoWaySnapshot(
            id: 15340012,
            awayScore: 102,
            homeScore: 99,
            awayWinPercent: resolved.awayPercent,
            homeWinPercent: resolved.homePercent
        )
        XCTAssertEqual(game.namedProbabilityLine(now: now), "Celtics 51% · Knicks 49%")
    }

    func testThreeWaySoccerGameWithholdsAwayComplementAndNamesHomeSideOnly() {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let odds = CurrentOdds(
            capturedAt: "2026-10-22T19:59:00Z",
            homeProbability: 0.48,
            awayProbability: 0.52,
            homeRenderedPercent: 48,
            awayRenderedPercent: 52,
            spread: nil,
            homeSpread: nil,
            overUnder: nil,
            projectedHomeScore: nil,
            projectedAwayScore: nil,
            bookmakerCount: 4
        )
        let resolved = MacMenuBarGameSnapshot4939.resolvePrintedPercentages(
            sportKey: "soccer_epl",
            currentOdds: odds,
            heroProbability: nil,
            openingOdds: nil
        )
        XCTAssertNil(
            resolved.awayPercent,
            "a draw-priced sport must withhold the away complement (1 - home includes the draw)"
        )
        XCTAssertEqual(resolved.homePercent, 48)
        XCTAssertTrue(resolved.pricesADraw)

        let soccerGame = MacMenuBarGameSnapshot4939(
            id: 15304603,
            sportKey: "soccer_epl",
            sportLabel: "EPL",
            awayTeam: "Arsenal FC",
            homeTeam: "Liverpool FC",
            awayAbbrev: "Arsenal FC",
            homeAbbrev: "Liverpool FC",
            status: "live",
            commenceTime: "2026-10-22T19:00:00Z",
            startIsTbd: false,
            awayScore: 1,
            homeScore: 1,
            liveClockText: "67'",
            awayWinPercent: resolved.awayPercent,
            homeWinPercent: resolved.homePercent,
            winnerMarketPricesADraw: resolved.pricesADraw,
            heroSettledResult: nil,
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: nil,
            scoreObservedAt: "2026-10-22T19:59:00Z",
            probabilityObservedAt: "2026-10-22T19:59:00Z"
        )
        XCTAssertEqual(soccerGame.namedProbabilityLine(now: now), "Liverpool FC 48% win")
    }

    func testVenueSettledResultRendersVerbatimWithoutParsing() {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let settledTennis = MacMenuBarGameSnapshot4939(
            id: 15310639,
            sportKey: "tennis_wta",
            sportLabel: "WTA",
            awayTeam: "Aryna Sabalenka",
            homeTeam: "Iga Swiatek",
            awayAbbrev: "Sabalenka",
            homeAbbrev: "Swiatek",
            status: "scheduled",
            commenceTime: "2026-10-20T16:00:00Z",
            startIsTbd: false,
            awayScore: nil,
            homeScore: nil,
            liveClockText: nil,
            awayWinPercent: 55,
            homeWinPercent: 45,
            winnerMarketPricesADraw: false,
            heroSettledResult: nil,
            venueSettled: true,
            venueSettledResult: "Aryna Sabalenka wins 2-0",
            venueClosedNoWinner: nil,
            scoreObservedAt: nil,
            probabilityObservedAt: "2026-10-20T18:00:00Z"
        )
        XCTAssertEqual(settledTennis.statusBadgeText(now: now), "Settled")
        XCTAssertEqual(settledTennis.settledVerdictText(now: now), "Aryna Sabalenka wins 2-0")
        XCTAssertNil(settledTennis.namedProbabilityLine(now: now))
    }

    // MARK: - 4. Honest Producer Observation Age & Staleness

    func testFreshnessUsesProducerObservedAtAndMarksLiveReadingsStaleAfterTwoMinutes() {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let freshLive = Self.makeLiveTwoWaySnapshot(
            id: 15340020,
            awayScore: 40,
            homeScore: 42,
            scoreObservedAt: "2026-10-22T19:59:20Z",
            probabilityObservedAt: "2026-10-22T19:59:10Z"
        )
        XCTAssertFalse(freshLive.isStaleLiveReading(now: now))
        XCTAssertEqual(freshLive.freshnessSummaryText(now: now), "Updated just now")

        let staleLive = Self.makeLiveTwoWaySnapshot(
            id: 15340021,
            awayScore: 40,
            homeScore: 42,
            scoreObservedAt: "2026-10-22T19:54:00Z",
            probabilityObservedAt: "2026-10-22T19:59:30Z"
        )
        // Uses oldestStamp across score + probability on live games so a 6m-old score
        // is never masked by a 30s-old price.
        XCTAssertTrue(staleLive.isStaleLiveReading(now: now))
        XCTAssertEqual(staleLive.freshnessSummaryText(now: now), "Stale · updated 6m ago")
    }

    func testMissingObservedAtStatesUpdateTimeUnavailableInsteadOfJustNow() {
        let now = ISO8601Stamp.date("2026-10-22T20:00:00Z")!
        let undated = Self.makeLiveTwoWaySnapshot(
            id: 15340022,
            awayScore: 14,
            homeScore: 10,
            scoreObservedAt: nil,
            probabilityObservedAt: nil
        )
        XCTAssertFalse(undated.isStaleLiveReading(now: now))
        XCTAssertEqual(undated.freshnessSummaryText(now: now), "Update time unavailable")
    }

    // MARK: - 5. Unavailable/Removed, Error Retention & Single-Flight Refresh

    func testUnavailableEventClearsSnapshotAndEntersUnavailablePhase() async {
        let celtics = Self.makeLiveTwoWaySnapshot(id: 15340030, awayScore: 84, homeScore: 79)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [:],
            candidates: [],
            selectedError: .eventUnavailable(eventID: 15340030)
        )
        let store = MacMenuBarSelectedGameStore4939(dataSource: dataSource, defaults: defaults)
        store.selectGame(celtics)
        await store.refresh()

        XCTAssertNil(store.selectedGame)
        XCTAssertEqual(store.phase, .unavailable("Selected game is no longer available."))
    }

    func testRefreshErrorRetainsLastGoodReadingForOfflineResilience() async {
        let celtics = Self.makeLiveTwoWaySnapshot(id: 15340031, awayScore: 84, homeScore: 79)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [:],
            candidates: [],
            selectedError: .message("No connection. Check your network and try again.")
        )
        let store = MacMenuBarSelectedGameStore4939(dataSource: dataSource, defaults: defaults)
        store.selectGame(celtics)
        await store.refresh()

        XCTAssertEqual(
            store.selectedGame?.id,
            15340031,
            "a transient refresh failure must keep the last-good selected game visible"
        )
        XCTAssertEqual(store.phase, .failed("No connection. Check your network and try again."))
    }

    func testConcurrentRefreshesCoalesceIntoSinglePerGameFetch() async {
        let celtics = Self.makeLiveTwoWaySnapshot(id: 15340032, awayScore: 84, homeScore: 79)
        let dataSource = MockMacMenuBarDataSource4939(
            selectedByID: [15340032: celtics],
            candidates: [celtics],
            delayNanoseconds: 40_000_000
        )
        defaults.set(15340032, forKey: MacMenuBarSelectedGameStore4939.selectedEventIDKey)
        let store = MacMenuBarSelectedGameStore4939(dataSource: dataSource, defaults: defaults)

        async let first: Void = store.refresh()
        async let second: Void = store.refresh()
        _ = await (first, second)

        XCTAssertEqual(
            dataSource.selectedFetchCount,
            1,
            "concurrent refresh calls must coalesce onto the in-flight request rather than duplicating per-game work"
        )
    }

    // MARK: - 6. Shipping MenuBarView Source Contracts

    func testMenuBarViewIsMacOnlyAndNeverCoalescesMissingScoreToZero() throws {
        let source = try Self.appSource("Views/MenuBarView.swift")
        let trimmed = source.trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertTrue(trimmed.hasPrefix("#if os(macOS)"))
        XCTAssertTrue(trimmed.hasSuffix("#endif"))
        XCTAssertFalse(
            source.contains("awayScore ?? 0"),
            "MenuBarView must never turn a nil awayScore into 0"
        )
        XCTAssertFalse(
            source.contains("homeScore ?? 0"),
            "MenuBarView must never turn a nil homeScore into 0"
        )
        XCTAssertTrue(source.contains("game.awayScoreText"))
        XCTAssertTrue(source.contains("game.homeScoreText"))
        XCTAssertTrue(source.contains("game.snapshot.awayScoreText"))
        XCTAssertTrue(source.contains("game.snapshot.homeScoreText"))
    }

    func testMenuBarViewWiresExplicitSelectionOpenWindowChangeClearAndRetry() throws {
        let source = try Self.appSource("Views/MenuBarView.swift")
        XCTAssertTrue(source.contains("@Environment(\\.openWindow) private var openWindow"))
        XCTAssertTrue(source.contains("openWindow(value: id)"))
        XCTAssertTrue(source.contains("store.selectGame(game.snapshot)"))
        XCTAssertTrue(source.contains("store.beginChangingGame()"))
        XCTAssertTrue(source.contains("store.clearSelection()"))
        XCTAssertTrue(source.contains("store.syncAccount(ownerID: APIClient.persistedLastKnownUserId())"))
        XCTAssertTrue(source.contains("mac-menubar-selected-game-card"))
        XCTAssertTrue(source.contains("mac-menubar-open-game-window"))
        XCTAssertTrue(source.contains("mac-menubar-change-game"))
        XCTAssertTrue(source.contains("mac-menubar-clear-game"))
        XCTAssertTrue(source.contains("mac-menubar-retry"))
    }

    #if os(macOS)
    func testMenuBarViewOffscreenRenderedStatesProduceNonEmptyBitmaps() async throws {
        let fixedNow = try XCTUnwrap(ISO8601Stamp.date("2026-10-22T20:00:00Z"))
        let liveNBA = Self.makeLiveTwoWaySnapshot(id: 501, awayScore: 102, homeScore: 98)
        let staleSoccer = MacMenuBarGameSnapshot4939(
            id: 502,
            sportKey: "soccer_epl",
            sportLabel: "EPL",
            awayTeam: "Arsenal FC",
            homeTeam: "Liverpool FC",
            awayAbbrev: "Arsenal FC",
            homeAbbrev: "Liverpool FC",
            status: "live",
            commenceTime: "2026-10-22T19:00:00Z",
            startIsTbd: false,
            awayScore: 1,
            homeScore: 1,
            liveClockText: "67'",
            awayWinPercent: nil,
            homeWinPercent: 48,
            winnerMarketPricesADraw: true,
            heroSettledResult: nil,
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: nil,
            scoreObservedAt: "2026-10-22T19:45:00Z",
            probabilityObservedAt: "2026-10-22T19:45:00Z"
        )
        let scheduledMissingScores = MacMenuBarDebugFixtures4939.scheduledMissingScoresGame
        let finalCompleted = MacMenuBarDebugFixtures4939.finalCompletedGame

        // 1. Live 2-way NBA game selected
        let liveStore = MacMenuBarSelectedGameStore4939(
            dataSource: MockMacMenuBarDataSource4939(selectedByID: [501: liveNBA], candidates: [liveNBA]),
            defaults: defaults,
            now: { fixedNow }
        )
        liveStore.selectGame(liveNBA)
        await liveStore.refresh()

        // 2. Live 3-way soccer game with stale source
        let soccerDefaults = UserDefaults(suiteName: "\(suiteName!).soccer")!
        soccerDefaults.removePersistentDomain(forName: "\(suiteName!).soccer")
        let soccerStore = MacMenuBarSelectedGameStore4939(
            dataSource: MockMacMenuBarDataSource4939(selectedByID: [502: staleSoccer], candidates: [staleSoccer]),
            defaults: soccerDefaults,
            now: { fixedNow }
        )
        soccerStore.selectGame(staleSoccer)
        await soccerStore.refresh()

        // 3. Scheduled game with missing scores ("—")
        let schedDefaults = UserDefaults(suiteName: "\(suiteName!).sched")!
        schedDefaults.removePersistentDomain(forName: "\(suiteName!).sched")
        let schedStore = MacMenuBarSelectedGameStore4939(
            dataSource: MockMacMenuBarDataSource4939(
                selectedByID: [scheduledMissingScores.id: scheduledMissingScores],
                candidates: [scheduledMissingScores]
            ),
            defaults: schedDefaults,
            now: { fixedNow }
        )
        schedStore.selectGame(scheduledMissingScores)
        await schedStore.refresh()

        // 4. Settled final game
        let finalDefaults = UserDefaults(suiteName: "\(suiteName!).final")!
        finalDefaults.removePersistentDomain(forName: "\(suiteName!).final")
        let finalStore = MacMenuBarSelectedGameStore4939(
            dataSource: MockMacMenuBarDataSource4939(
                selectedByID: [finalCompleted.id: finalCompleted],
                candidates: [finalCompleted]
            ),
            defaults: finalDefaults,
            now: { fixedNow }
        )
        finalStore.selectGame(finalCompleted)
        await finalStore.refresh()

        // 5. Unavailable 404 state
        let unavailDefaults = UserDefaults(suiteName: "\(suiteName!).unavail")!
        unavailDefaults.removePersistentDomain(forName: "\(suiteName!).unavail")
        unavailDefaults.set(999, forKey: MacMenuBarSelectedGameStore4939.selectedEventIDKey)
        let unavailStore = MacMenuBarSelectedGameStore4939(
            dataSource: MockMacMenuBarDataSource4939(selectedByID: [:], candidates: [liveNBA]),
            defaults: unavailDefaults,
            now: { fixedNow }
        )
        await unavailStore.refresh()

        // 6. Transient error retaining last-good reading
        let errorDefaults = UserDefaults(suiteName: "\(suiteName!).error")!
        errorDefaults.removePersistentDomain(forName: "\(suiteName!).error")
        let errorDS = MockMacMenuBarDataSource4939(selectedByID: [501: liveNBA], candidates: [liveNBA])
        let errorStore = MacMenuBarSelectedGameStore4939(
            dataSource: errorDS,
            defaults: errorDefaults,
            now: { fixedNow }
        )
        errorStore.selectGame(liveNBA)
        await errorStore.refresh()
        errorDS.selectedError = .message("Timed out reaching /api/events/501")
        await errorStore.refresh()

        // 7. Picker list with candidates
        let pickerDefaults = UserDefaults(suiteName: "\(suiteName!).picker")!
        pickerDefaults.removePersistentDomain(forName: "\(suiteName!).picker")
        let pickerStore = MacMenuBarSelectedGameStore4939(
            dataSource: MockMacMenuBarDataSource4939(
                selectedByID: [:],
                candidates: [liveNBA, staleSoccer, scheduledMissingScores]
            ),
            defaults: pickerDefaults,
            now: { fixedNow }
        )
        await pickerStore.refresh()

        let states: [(name: String, store: MacMenuBarSelectedGameStore4939)] = [
            ("01-selected-live-nba", liveStore),
            ("02-selected-soccer-3way-stale", soccerStore),
            ("03-selected-scheduled-missing-scores", schedStore),
            ("04-selected-settled-final", finalStore),
            ("05-selected-unavailable-404", unavailStore),
            ("06-selected-transient-error-retained", errorStore),
            ("07-picker-candidates", pickerStore),
        ]

        let outputDir = ProcessInfo.processInfo.environment["MENUBAR_4939_SNAPSHOT_DIR"]
        if let outputDir {
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: outputDir),
                withIntermediateDirectories: true
            )
        }

        for (name, stateStore) in states {
            let rootView = MenuBarView(store: stateStore, enableAutoRefresh: false)
                .background(Color(nsColor: .windowBackgroundColor))
                .environment(\.colorScheme, .light)
            let renderer = rendererForMeasurement(rootView)
            renderer.scale = 2.0
            let cgImage = try XCTUnwrap(renderer.cgImage, "Failed to render \(name)")
            XCTAssertEqual(cgImage.width, 560, "Rendered width at 2x scale should be 560px for \(name)")
            XCTAssertGreaterThan(cgImage.height, 140, "Rendered height at 2x scale should exceed 140px for \(name)")

            if let outputDir {
                let rep = NSBitmapImageRep(cgImage: cgImage)
                let pngData = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
                let url = URL(fileURLWithPath: outputDir).appendingPathComponent("\(name).png")
                try pngData.write(to: url)
            }
        }
    }
    #endif

    // MARK: - Test Helpers

    private static func makeLiveTwoWaySnapshot(
        id: Int,
        awayScore: Int?,
        homeScore: Int?,
        awayWinPercent: Int? = 64,
        homeWinPercent: Int? = 36,
        scoreObservedAt: String? = "2026-10-22T19:59:30Z",
        probabilityObservedAt: String? = "2026-10-22T19:59:30Z"
    ) -> MacMenuBarGameSnapshot4939 {
        MacMenuBarGameSnapshot4939(
            id: id,
            sportKey: "basketball_nba",
            sportLabel: "NBA",
            awayTeam: "Boston Celtics",
            homeTeam: "New York Knicks",
            awayAbbrev: "Celtics",
            homeAbbrev: "Knicks",
            status: "live",
            commenceTime: "2026-10-22T19:00:00Z",
            startIsTbd: false,
            awayScore: awayScore,
            homeScore: homeScore,
            liveClockText: "Q3 4:12",
            awayWinPercent: awayWinPercent,
            homeWinPercent: homeWinPercent,
            winnerMarketPricesADraw: false,
            heroSettledResult: nil,
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: nil,
            scoreObservedAt: scoreObservedAt,
            probabilityObservedAt: probabilityObservedAt
        )
    }

    private static func appSource(_ relativePath: String, file: StaticString = #filePath) throws -> String {
        let testFile = URL(fileURLWithPath: "\(file)")
        let iosRoot = testFile.deletingLastPathComponent().deletingLastPathComponent()
        let url = iosRoot.appendingPathComponent("Bain Luck").appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}

@MainActor
private final class MockMacMenuBarDataSource4939: MacMenuBarGameDataSource4939, @unchecked Sendable {
    var selectedByID: [Int: MacMenuBarGameSnapshot4939]
    var candidates: [MacMenuBarGameSnapshot4939]
    var selectedError: MacMenuBarDataSourceError4939?
    var delayNanoseconds: UInt64
    private(set) var selectedFetchCount = 0
    private(set) var candidateFetchCount = 0

    init(
        selectedByID: [Int: MacMenuBarGameSnapshot4939],
        candidates: [MacMenuBarGameSnapshot4939],
        selectedError: MacMenuBarDataSourceError4939? = nil,
        delayNanoseconds: UInt64 = 0
    ) {
        self.selectedByID = selectedByID
        self.candidates = candidates
        self.selectedError = selectedError
        self.delayNanoseconds = delayNanoseconds
    }

    func fetchSelectedGame(eventID: Int) async throws -> MacMenuBarGameSnapshot4939 {
        selectedFetchCount += 1
        if delayNanoseconds > 0 {
            try? await Task.sleep(nanoseconds: delayNanoseconds)
        }
        if let selectedError {
            throw selectedError
        }
        guard let snapshot = selectedByID[eventID] else {
            throw MacMenuBarDataSourceError4939.eventUnavailable(eventID: eventID)
        }
        return snapshot
    }

    func fetchCandidateGames() async throws -> [MacMenuBarGameSnapshot4939] {
        candidateFetchCount += 1
        if delayNanoseconds > 0 {
            try? await Task.sleep(nanoseconds: delayNanoseconds)
        }
        if let selectedError {
            throw selectedError
        }
        return candidates
    }
}
