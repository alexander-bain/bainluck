#if os(macOS)
import AppKit
import SwiftUI

struct MenuBarView: View {
    @Environment(\.openWindow) private var openWindow
    @StateObject private var store: MacMenuBarSelectedGameStore4939
    private let enableAutoRefresh: Bool

    @MainActor
    init(
        store: MacMenuBarSelectedGameStore4939? = nil,
        enableAutoRefresh: Bool = true
    ) {
        let resolvedStore = store ?? MenuBarView.makeDefaultStore()
        _store = StateObject(wrappedValue: resolvedStore)
        self.enableAutoRefresh = enableAutoRefresh
    }

    var body: some View {
        let now = store.currentInstant
        VStack(alignment: .leading, spacing: 0) {
            if let debugBanner = store.debugFixtureBanner {
                HStack(spacing: 6) {
                    Image(systemName: "hammer.fill")
                        .font(.caption2)
                    Text(debugBanner)
                        .font(.system(size: 10, weight: .bold))
                }
                .foregroundStyle(.orange)
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .accessibilityIdentifier("mac-menubar-debug-fixture-banner")
                Divider()
            }

            contentSection(now: now)

            Divider()
            footerSection
        }
        .frame(width: 280)
        .padding(.vertical, 4)
        .task {
            guard enableAutoRefresh else { return }
            store.syncAccount(ownerID: APIClient.persistedLastKnownUserId())
            await store.refresh()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                store.syncAccount(ownerID: APIClient.persistedLastKnownUserId())
                await store.refresh()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: UserDefaults.didChangeNotification)) { _ in
            guard enableAutoRefresh else { return }
            store.syncAccount(ownerID: APIClient.persistedLastKnownUserId())
        }
    }

    @ViewBuilder
    private func contentSection(now: Date) -> some View {
        if let selected = store.selectedGame, !store.isChoosingGame {
            selectedGameSection(selected, now: now)
        } else if case .unavailable(let message) = store.phase, !store.isChoosingGame {
            unavailableSection(message: message)
        } else if store.phase == .loading && store.candidateGames.isEmpty && store.selectedGame == nil {
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                Text(store.selectedEventID != nil ? "Loading selected game…" : "Loading games…")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 68)
            .padding(.horizontal, 12)
            .accessibilityIdentifier("mac-menubar-loading")
        } else {
            pickerSection
        }
    }

    private func selectedGameSection(_ game: MacMenuBarGameSnapshot4939, now: Date) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    Text(game.sportLabel)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                        .lineLimit(1)
                    Spacer()
                    Text(game.statusBadgeText(now: now))
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(game.isLive ? .green : .secondary)
                        .lineLimit(1)
                }

                Text(game.fullMatchupTitle)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)

                HStack(spacing: 6) {
                    Text(game.awayAbbrev)
                        .font(.system(size: 12, weight: .bold))
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Text(game.awayScoreText)
                        .font(.system(size: 14, weight: .heavy, design: .rounded).monospacedDigit())
                        .frame(minWidth: 22, alignment: .trailing)

                    Text("–")
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)

                    Text(game.homeScoreText)
                        .font(.system(size: 14, weight: .heavy, design: .rounded).monospacedDigit())
                        .frame(minWidth: 22, alignment: .leading)

                    Text(game.homeAbbrev)
                        .font(.system(size: 12, weight: .bold))
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }

                HStack(spacing: 6) {
                    if let verdict = game.settledVerdictText(now: now) {
                        Text(verdict)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                    } else if let probLine = game.namedProbabilityLine(now: now) {
                        Text(probLine)
                            .font(.system(size: 11, weight: .medium).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer()
                    Text(game.freshnessSummaryText(now: now))
                        .font(.system(size: 9))
                        .foregroundStyle(game.isStaleLiveReading(now: now) ? .orange : .secondary)
                        .lineLimit(1)
                }

                if store.isShowingPersistedSnapshot {
                    Text("Saved reading \u{00B7} confirming\u{2026}")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("mac-menubar-saved-reading-status")
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(game.accessibilitySummary(now: now))
            .accessibilityIdentifier("mac-menubar-selected-game-card")

            if case .failed(let message) = store.phase {
                HStack(alignment: .center, spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                    Text("Couldn't refresh \u{00B7} showing last reading")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .help(message)
                    Spacer()
                    Button("Retry") {
                        Task { await store.refresh() }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Color.accentColor)
                    .accessibilityIdentifier("mac-menubar-retry")
                }
            }

            HStack(spacing: 8) {
                Button {
                    openSelectedGameWindow(id: game.id)
                } label: {
                    Label("Open Game Window", systemImage: "macwindow.badge.plus")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .accessibilityIdentifier("mac-menubar-open-game-window")

                Spacer()

                Button("Change") {
                    store.beginChangingGame()
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
                .accessibilityLabel("Change selected game")
                .accessibilityIdentifier("mac-menubar-change-game")

                Button("Clear") {
                    store.clearSelection()
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
                .accessibilityLabel("Clear selected game")
                .accessibilityIdentifier("mac-menubar-clear-game")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private func unavailableSection(message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.circle")
                    .foregroundStyle(.secondary)
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Button("Choose Another Game") {
                    store.beginChangingGame()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .accessibilityIdentifier("mac-menubar-choose-another")

                Button("Clear Selection") {
                    store.clearSelection()
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .accessibilityIdentifier("mac-menubar-unavailable")
    }

    @ViewBuilder
    private var pickerSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(store.selectedGame == nil ? "Choose a Game to Pin" : "Choose Another Game")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                if store.selectedGame != nil {
                    Button("Keep Current") {
                        store.cancelChangingGame()
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
                } else if store.selectedEventID != nil {
                    Button("Clear") {
                        store.clearSelection()
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)

            if case .failed(let message) = store.phase, store.candidateGames.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Retry") {
                        Task { await store.refresh() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .accessibilityIdentifier("mac-menubar-retry")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            } else if store.candidateGames.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "sportscourt")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No upcoming games available right now")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 60)
                .padding(.horizontal, 12)
            } else {
                let rows = store.candidateGames.map { MenuBarGame(snapshot: $0) }
                ForEach(rows) { game in
                    menuBarGameRow(game)
                    if game.id != rows.last?.id {
                        Divider()
                    }
                }
            }
        }
    }

    private var footerSection: some View {
        Button {
            if let url = URL(string: "bainluck://events") {
                NSWorkspace.shared.open(url)
            }
        } label: {
            HStack {
                Text("Open Bain Luck")
                    .font(.caption)
                Spacer()
                Text("⌘2")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func openSelectedGameWindow(id: Int) {
        openWindow(value: id)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    private func menuBarGameRow(_ game: MenuBarGame) -> some View {
        Button {
            store.selectGame(game.snapshot)
        } label: {
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(game.sport)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                    Spacer()
                    if let period = game.period, !period.isEmpty {
                        Text(period)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.green)
                    }
                }

                HStack(spacing: 4) {
                    Text(game.awayAbbrev)
                        .font(.system(size: 12, weight: .bold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                        .frame(minWidth: 40, maxWidth: 56, alignment: .leading)
                    Text(game.snapshot.awayScoreText)
                        .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: 24, alignment: .trailing)

                    Text("–")
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                        .fixedSize(horizontal: true, vertical: false)

                    Text(game.snapshot.homeScoreText)
                        .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: 24, alignment: .leading)
                    Text(game.homeAbbrev)
                        .font(.system(size: 12, weight: .bold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                        .frame(minWidth: 40, maxWidth: 56, alignment: .trailing)

                    Spacer(minLength: 4)

                    // #5363 — a draw-priced sport has no away number to print, and
                    // "—–68" in a 10pt monospaced pair is not a legible absence, so
                    // this row NAMES its survivor instead of holding the slot. The
                    // abbreviation is already on the row, so the name costs nothing
                    // a reader has not already read.
                    if let awayProb = game.awayProb {
                        Text("\(awayProb)–\(game.homeProb)")
                            .font(.system(size: 10, weight: .medium).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    } else {
                        Text("\(game.homeAbbrev) \(game.homeProb)")
                            .font(.system(size: 10, weight: .medium).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Select \(game.snapshot.accessibilitySummary(now: store.currentInstant))")
    }

    @MainActor
    private static func makeDefaultStore() -> MacMenuBarSelectedGameStore4939 {
        #if DEBUG
        if let fixtureName = ProcessInfo.processInfo.environment[MacMenuBarDebugFixtures4939.envKey],
           !fixtureName.isEmpty {
            return makeDebugFixtureStore(named: fixtureName)
        }
        #endif
        return MacMenuBarSelectedGameStore4939(
            dataSource: LiveMacMenuBarGameDataSource4939()
        )
    }

    #if DEBUG
    @MainActor
    private static func makeDebugFixtureStore(named name: String) -> MacMenuBarSelectedGameStore4939 {
        let game: MacMenuBarGameSnapshot4939
        switch name {
        case "soccer":
            game = MacMenuBarDebugFixtures4939.liveSoccerThreeWayGame
        case "scheduled":
            game = MacMenuBarDebugFixtures4939.scheduledMissingScoresGame
        case "final":
            game = MacMenuBarDebugFixtures4939.finalCompletedGame
        default:
            game = MacMenuBarDebugFixtures4939.liveTwoWayGame
        }
        let store = MacMenuBarSelectedGameStore4939(
            dataSource: DebugFixtureMacMenuBarDataSource4939(selected: game),
            now: { MacMenuBarDebugFixtures4939.referenceNow },
            debugFixtureBanner: "DEBUG Fixture (\(name))"
        )
        store.selectGame(game)
        return store
    }
    #endif
}

private struct LiveMacMenuBarGameDataSource4939: MacMenuBarGameDataSource4939 {
    func fetchSelectedGame(eventID: Int) async throws -> MacMenuBarGameSnapshot4939 {
        do {
            let detail = try await APIClient.shared.fetchEvent(id: eventID)
            let clock = PeriodLabel.liveStatusText(
                period: detail.espn?.period,
                gameClock: detail.espn?.gameClock
            )
            return MacMenuBarGameSnapshot4939.from(detail: detail, liveClockText: clock)
        } catch let error as APIError {
            if case .httpError(let statusCode, _) = error, statusCode == 404 || statusCode == 410 {
                throw MacMenuBarDataSourceError4939.eventUnavailable(eventID: eventID)
            }
            throw error
        }
    }

    func fetchCandidateGames() async throws -> [MacMenuBarGameSnapshot4939] {
        let myTeamsFeed = try await APIClient.shared.fetchFeed(
            limit: 10,
            myTeamsOnly: true,
            includeFutures: false
        )
        let myTeamsGames = Self.extractCandidateGames(from: myTeamsFeed)
        if !myTeamsGames.isEmpty {
            return myTeamsGames.map(\.snapshot)
        }
        let generalFeed = try await APIClient.shared.fetchFeed(
            limit: 12,
            myTeamsOnly: false,
            includeFutures: false
        )
        return Self.extractCandidateGames(from: generalFeed).map(\.snapshot)
    }

    private static func extractCandidateGames(from feed: FeedResponse) -> [MenuBarGame] {
        return feed.items.compactMap { item -> MenuBarGame? in
                guard let event = item.event,
                      (event.status == "live" || event.status == "scheduled") else { return nil }
                // #2279 — WHICH SOURCE THE PROBABILITY CAME FROM DECIDES WHETHER
                // THE SERVED PERCENTS APPLY. The guard below falls back to
                // `openingOdds`, and the served percents describe `currentOdds`
                // and nothing else, so reading them on that branch would print
                // the current pair's rounding beside the OPENING pair's
                // probability. It still sums to 100, so no sum guard could see
                // it. Recorded at the branch that knows, not inferred afterwards.
                let odds = event.currentOdds
                let fromCurrentOdds = odds?.homeProbability != nil
                guard let homeProbability = odds?.homeProbability ?? event.openingOdds?.homeProbability else { return nil }
                // #5363 — this was the family's most literal copy of the defect:
                // the away number was not even served here, it was DERIVED as
                // `1 − home` one line down. On soccer that is *away win or
                // draw*. The rule decides whether it may be printed; the row
                // above draws the withheld case by naming the home side.
                let printable = DrawPricedWinner.printablePair(
                    away: 1.0 - homeProbability,
                    home: homeProbability,
                    sport: event.sport
                )
                let awayProbability = 1.0 - homeProbability
                // UX-P114 — the menu bar prints both sides, and derives away from
                // home right above, so it had the same 101. Prefer the server's
                // card-level percents; `renderedDuelPercents` covers a cached or
                // pre-deploy payload, and the openingOdds fallback in the guard
                // above, which the server does not decide percents for.
                //
                // #2279 — BOTH SERVED OR NEITHER. This site coalesced per side,
                // and it also carried a THIRD tier — `?? Int((p * 100).rounded())`
                // — that was a fourth, unshared implementation of the same
                // rounding, reachable only when the contract rule declines to
                // answer, and `Int(_:)` TRAPS on a non-finite Double. The pair
                // rule is now the last word: if it declines, the row is dropped
                // rather than re-derived by a copy nobody tests.
                let duel = duelPercents(
                    away: awayProbability,
                    home: homeProbability,
                    servedAway: fromCurrentOdds ? odds?.awayRenderedPercent : nil,
                    servedHome: fromCurrentOdds ? odds?.homeRenderedPercent : nil
                )
                guard let awayPct = duel[0], let homePct = duel[1] else { return nil }
                // Withheld, not missing: the row still renders, on its home number.
                let printableAwayPct: Int? = printable?.away == nil ? nil : awayPct
                // #3430 — both competitors of one matchup on one menu row, in
                // the least room any surface gives them.
                let menuSides = TeamShortName.shortPair(
                    away: event.awayTeam, home: event.homeTeam,
                    awayServed: event.awayTeamData?.abbreviation,
                    homeServed: event.homeTeamData?.abbreviation,
                    sportKey: event.sport
                )
                let livePeriod = PeriodLabel.liveStatusText(
                    period: event.espn?.period, gameClock: event.espn?.gameClock)
                let snapshot = MacMenuBarGameSnapshot4939.from(
                    feedEvent: event,
                    awayAbbrev: menuSides.away,
                    homeAbbrev: menuSides.home,
                    awayWinPercent: printableAwayPct,
                    homeWinPercent: homePct,
                    liveClockText: livePeriod
                )
                return MenuBarGame(
                    id: event.id,
                    homeAbbrev: menuSides.home,
                    awayAbbrev: menuSides.away,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    homeProb: homePct,
                    awayProb: printableAwayPct,
                    // #4880 — see `PeriodLabel.liveStatusText`.
                    period: livePeriod ?? "",
                    sport: event.sportName ?? event.sport ?? "",
                    snapshot: snapshot
                )
        }
    }
}

#if DEBUG
private struct DebugFixtureMacMenuBarDataSource4939: MacMenuBarGameDataSource4939 {
    let selected: MacMenuBarGameSnapshot4939

    func fetchSelectedGame(eventID: Int) async throws -> MacMenuBarGameSnapshot4939 {
        selected
    }

    func fetchCandidateGames() async throws -> [MacMenuBarGameSnapshot4939] {
        [
            MacMenuBarDebugFixtures4939.liveTwoWayGame,
            MacMenuBarDebugFixtures4939.liveSoccerThreeWayGame,
            MacMenuBarDebugFixtures4939.scheduledMissingScoresGame,
            MacMenuBarDebugFixtures4939.finalCompletedGame,
        ]
    }
}
#endif

private struct MenuBarGame: Identifiable {
    let id: Int
    let homeAbbrev: String
    let awayAbbrev: String
    let homeScore: Int?
    let awayScore: Int?
    let homeProb: Int
    /// #5363 — nil where the sport prices a draw and the complement is withheld.
    let awayProb: Int?
    let period: String?
    let sport: String
    let snapshot: MacMenuBarGameSnapshot4939

    init(
        id: Int,
        homeAbbrev: String,
        awayAbbrev: String,
        homeScore: Int?,
        awayScore: Int?,
        homeProb: Int,
        awayProb: Int?,
        period: String?,
        sport: String,
        snapshot: MacMenuBarGameSnapshot4939
    ) {
        self.id = id
        self.homeAbbrev = homeAbbrev
        self.awayAbbrev = awayAbbrev
        self.homeScore = homeScore
        self.awayScore = awayScore
        self.homeProb = homeProb
        self.awayProb = awayProb
        self.period = period
        self.sport = sport
        self.snapshot = snapshot
    }

    init(snapshot: MacMenuBarGameSnapshot4939) {
        self.id = snapshot.id
        self.homeAbbrev = snapshot.homeAbbrev
        self.awayAbbrev = snapshot.awayAbbrev
        self.homeScore = snapshot.homeScore
        self.awayScore = snapshot.awayScore
        self.homeProb = snapshot.homeWinPercent ?? 0
        self.awayProb = snapshot.awayWinPercent
        self.period = snapshot.liveClockText
        self.sport = snapshot.sportLabel
        self.snapshot = snapshot
    }
}
#endif
