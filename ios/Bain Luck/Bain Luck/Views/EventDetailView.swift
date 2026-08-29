import SwiftUI

// MARK: - View

struct EventDetailView: View {
    let eventId: Int
    @StateObject private var vm: EventDetailViewModel
    @State private var countdownText: String?
    @State private var countdownTimer: Timer?
    @State private var selectedPlayPoint: GamePlayPoint?
    @State private var showSources = false
    @State private var refreshCountdown: Int = 0
    @State private var refreshCountdownTimer: Timer?
    private var sharedChartDomain: ClosedRange<Date>? {
        guard let event = vm.event,
              let commenceTime = event.commenceTime,
              let scheduledStart = commenceTime.asDate else { return nil }

        // Use actual game start (first ESPN data point) instead of scheduled
        // time — a game that starts early/late should anchor to when it really
        // began, not when it was listed.
        //
        // #1833: but `min()` here is unbounded backwards, and in-game rows from
        // the PREVIOUS NIGHT'S game were landing on this event. On Alex's
        // 2026-08-13 Sox–Jays specimen the earliest period-bearing ESPN row was
        // 2026-08-12T23:34, so this opened the x-axis ~20 hours before first
        // pitch: a 22-hour domain for a 2.5-hour game, which is what reduced the
        // time labels to unreadable soup on a phone.
        //
        // The backend now filters those rows (app/utils/game_window.py), but a
        // chart domain must not depend on upstream cleanliness to stay legible.
        // A real early start is minutes, not hours — so accept an earlier anchor
        // only within a warm-up margin and otherwise trust the schedule.
        let earliestPlausibleStart = scheduledStart.addingTimeInterval(-2 * 60 * 60)
        let actualStart: Date
        if let espn = vm.history?.espnHistory,
           let firstEspn = espn.first(where: { $0.period != nil && !($0.period?.isEmpty ?? true) }),
           let espnDate = firstEspn.timestamp.asDate {
            let candidate = min(scheduledStart, espnDate.addingTimeInterval(-60))
            actualStart = max(candidate, earliestPlausibleStart)
        } else {
            actualStart = scheduledStart
        }

        // Build a domain only when the upper bound is at/after the lower bound.
        // A market-less / aged-out closed game can have history whose only points
        // predate the scheduled start (pre-game odds snapshot, no in-game data);
        // a "stuck live" event can have a future start. Either yields an inverted
        // ClosedRange, and `lower...upper` TRAPS when lower > upper — the crash on
        // tapping a market-less card (#1092). Return nil in that case so the child
        // charts compute their own safe domain from their data points.
        func domain(upTo end: Date) -> ClosedRange<Date>? {
            let upper = end.addingTimeInterval(30)
            return upper >= actualStart ? actualStart...upper : nil
        }

        // For completed games: use last game data point, NOT completedAt
        // (completedAt is a backend processing timestamp, often 30-45 min after game end)
        if event.status == "completed" || event.status == "closed" {
            let lastEspn = vm.history?.espnHistory?.last?.timestamp.asDate
            let lastOdds = vm.history?.history.last?.timestamp.asDate
            if let gameEnd = [lastEspn, lastOdds].compactMap({ $0 }).max(),
               let range = domain(upTo: gameEnd) {
                return range
            }
            // Fallback to completedAt only if no game data
            if let ca = vm.history?.completedAt, let end = ca.asDate,
               let range = domain(upTo: end) {
                return range
            }
            return nil
        }
        if event.status == "live" {
            let upper = Date().addingTimeInterval(60)
            return upper >= actualStart ? actualStart...upper : nil
        }
        return nil
    }
    @Environment(\.horizontalSizeClass) private var sizeClass

    init(eventId: Int) {
        self.eventId = eventId
        _vm = StateObject(wrappedValue: EventDetailViewModel(eventId: eventId))
    }

    private var isLive: Bool { vm.event?.status == "live" }
    private var isFinished: Bool { vm.event?.status == "completed" || vm.event?.status == "closed" }
    private var isScheduled: Bool { vm.event?.status == "scheduled" }

    private var isIPad: Bool { sizeClass == .regular }
    private var logoSize: CGFloat { isIPad ? 80 : 56 }
    private var scoreFontSize: CGFloat { isIPad ? 52 : 40 }
    private var contentMaxWidth: CGFloat {
        #if os(macOS)
        return 1200
        #else
        return isIPad ? 1100 : 700
        #endif
    }

    private var dynamicTitle: String {
        guard let event = vm.event else { return "Game Details" }
        let away = event.awayTeamData?.abbreviation ?? String(event.awayTeam.split(separator: " ").last ?? "")
        let home = event.homeTeamData?.abbreviation ?? String(event.homeTeam.split(separator: " ").last ?? "")
        if let hs = event.homeScore, let as_ = event.awayScore {
            let parts = [event.espn?.period, event.espn?.gameClock].compactMap { $0 }.filter { !$0.isEmpty }
            let state = parts.joined(separator: " ")
            return "\(away) \(as_) - \(home) \(hs)" + (state.isEmpty ? "" : " • \(state)")
        }
        return "\(away) vs \(home)"
    }

    private var shareURL: URL {
        URL(string: eventShareURL(eventId)) ?? bainLuckFallbackURL
    }

    var body: some View {
        contentView
            .navigationTitle(dynamicTitle)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                // Manual-refresh ring only when a real auto-refresh is running
                // (live). vm.load() stamps lastLoadedAt, so the countdown resets
                // honestly on completion.
                if isLive {
                    ToolbarItem(placement: .cancellationAction) {
                        Button { Task { await vm.load() } } label: {
                            refreshRing
                        }
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    HStack(spacing: 4) {
                        ShareLink(item: shareURL) {
                            Image(systemName: "square.and.arrow.up")
                                .font(.system(size: 14))
                        }
                        PinButton(type: "event", id: eventId)
                    }
                }
            }
            .task {
                await vm.load()
                AnalyticsService.trackEventDetailView(eventId: eventId, sport: vm.event?.sport)
                startCountdownTimer()
                startRefreshCountdown()
            }
            .refreshable {
                await vm.load()
            }
            .onDisappear {
                vm.stopRefresh()
                countdownTimer?.invalidate()
                refreshCountdownTimer?.invalidate()
            }
    }

    @ViewBuilder
    private var contentView: some View {
        if vm.loading {
            ProgressView()
        } else if let error = vm.error, vm.event == nil {
            ContentUnavailableView(
                "Error",
                systemImage: "exclamationmark.triangle",
                description: Text(error)
            )
        } else if let event = vm.event {
            ScrollView {
                VStack(spacing: 12) {
                    heroSection(event)
                    if let history = vm.history, (isLive || isFinished) {
                        GameSegmentsView(
                            history: history,
                            sportKey: event.sport,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeTeamColor: teamColors(event).home,
                            awayTeamColor: teamColors(event).away,
                            homeTeamAbbrev: event.homeTeamData?.abbreviation,
                            awayTeamAbbrev: event.awayTeamData?.abbreviation,
                            // #1831: the scoreboard's own totals, so the card can
                            // never disagree with the hero above it.
                            finalHomeScore: event.homeScore,
                            finalAwayScore: event.awayScore
                        )
                    }
                    VStack(spacing: 0) {
                        OddsChartView(eventId: event.id, teamColors: teamColors(event),
                                     commenceTime: event.commenceTime, status: event.status,
                                     homeTeamName: event.homeTeam,
                                     awayTeamName: event.awayTeam,
                                     homeTeamLogo: event.homeTeamData?.logoSmall,
                                     awayTeamLogo: event.awayTeamData?.logoSmall,
                                     homeTeamAbbrev: event.homeTeamData?.abbreviation,
                                     awayTeamAbbrev: event.awayTeamData?.abbreviation,
                                     refreshCountdown: refreshCountdown,
                                     refreshInterval: refreshInterval,
                                     forcedDomain: sharedChartDomain,
                                     selectedPlayPoint: $selectedPlayPoint,
                                     preloadedHistory: vm.history)
                        if (isLive || isFinished) && vm.history?.scoringPlays?.isEmpty == false {
                            GamePlayCardView(
                                selectedPoint: selectedPlayPoint,
                                homeTeam: event.homeTeam,
                                awayTeam: event.awayTeam,
                                homeTeamColor: teamColors(event).home,
                                awayTeamColor: teamColors(event).away,
                                homeTeamLogo: event.homeTeamData?.logoSmall,
                                awayTeamLogo: event.awayTeamData?.logoSmall,
                                lastPoint: lastPlayPoint(event: event)
                            )
                        }
                        // Bookmaker table (collapsible Sources panel)
                        sourcesToggle(event)

                        NavigationLink(value: Route.eventModels(id: event.id)) {
                            HStack {
                                Spacer()
                                HStack(spacing: 4) {
                                    Image(systemName: "function")
                                        .font(.caption2.weight(.bold))
                                    Text("View Probability Models")
                                        .font(.caption2.weight(.medium))
                                }
                                .foregroundStyle(.blue)
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 6)
                        }
                    }
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    // "Why the Line Moved" removed — content was low quality
                    // (obvious statements, minor injuries). See #745 for revamp plan.
                    // Score Differential Chart
                    if let history = vm.history, (isLive || isFinished) {
                        ScoreDifferentialChartView(
                            history: history,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            commenceTime: event.commenceTime,
                            eventStatus: event.status,
                            homeTeamColor: teamColors(event).home,
                            awayTeamColor: teamColors(event).away,
                            homeTeamAbbrev: event.homeTeamData?.abbreviation,
                            awayTeamAbbrev: event.awayTeamData?.abbreviation,
                            forcedDomain: sharedChartDomain
                        )
                    }
                    // Market Maps (margin + total density curves)
                    if let gameMarkets = vm.gameMarkets {
                        MarketMapView(
                            gameMarkets: gameMarkets,
                            eventStatus: event.status,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeAbbr: event.homeTeamData?.abbreviation,
                            awayAbbr: event.awayTeamData?.abbreviation,
                            homeColor: teamColors(event).home,
                            awayColor: teamColors(event).away,
                            sportKey: event.sport,
                            homeWinProb: event.currentOdds?.homeProbability,
                            awayWinProb: event.currentOdds?.awayProbability,
                            homeSpread: event.currentOdds?.homeSpread,
                            overUnder: event.currentOdds?.overUnder,
                            homeScore: event.homeScore,
                            awayScore: event.awayScore
                        )
                    }
                    // Total Points Spectrum (projected scoring + threshold ladder)
                    if let gameMarkets = vm.gameMarkets {
                        TotalPointsSpectrumView(
                            gameMarkets: gameMarkets,
                            eventStatus: event.status,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeColor: teamColors(event).home,
                            awayColor: teamColors(event).away,
                            overUnder: event.currentOdds?.overUnder,
                            homeScore: event.homeScore,
                            awayScore: event.awayScore
                        )
                    }
                    // Player Props (from game-markets endpoint)
                    if let gameMarkets = vm.gameMarkets,
                       let playerProps = gameMarkets.playerProps,
                       !playerProps.isEmpty {
                        PlayerPropsCardView(
                            playerProps: playerProps,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeColor: teamColors(event).home,
                            awayColor: teamColors(event).away,
                            eventStatus: event.status,
                            boxScore: vm.relatedFutures?.boxScore
                        )
                    }
                    // Special Event Markets (game props, novelty, MVP)
                    if let gameMarkets = vm.gameMarkets,
                       let otherMarkets = gameMarkets.other,
                       otherMarkets.count >= 3 {
                        SpecialEventMarketsView(
                            markets: otherMarkets,
                            eventStatus: event.status
                        )
                    }
                    // Graceful empty state: a market-less game (e.g. an aged-out
                    // closed game whose Kalshi/odds markets have expired) has no
                    // market sections to show. Say so rather than leaving a gap or
                    // assuming a section exists (#1092).
                    if let gameMarkets = vm.gameMarkets,
                       !gameMarketsHaveContent(gameMarkets) {
                        noGameMarketsNote
                    }
                    // Series Probability (playoff series context)
                    if let tags = event.eventTags,
                       (tags.contains("competitive_structure:series") || tags.contains("competitive_structure:best_of_7")),
                       let homeProb = event.currentOdds?.homeProbability {
                        SeriesProbabilityView(
                            homeWinProb: homeProb,
                            homeSeriesWins: event.espn?.seriesHomeWins ?? 0,
                            awaySeriesWins: event.espn?.seriesAwayWins ?? 0,
                            gamesToWin: tags.contains("competitive_structure:best_of_7") ? 4 : 4,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeTeamColor: teamColors(event).home,
                            awayTeamColor: teamColors(event).away
                        )
                    }
                    if let prog = vm.teamProgression {
                        ChampionshipPathView(
                            progression: prog,
                            homeTeamColor: teamColors(event).home,
                            awayTeamColor: teamColors(event).away
                        )
                    }
                    RelatedFuturesView(
                        eventId: event.id,
                        awayTeamColor: teamColors(event).away,
                        homeTeamColor: teamColors(event).home,
                        awayTeam: event.awayTeam,
                        homeTeam: event.homeTeam,
                        sportKey: event.sport,
                        preloadedData: vm.relatedFutures
                    )
                    // League page link
                    leaguePageLink(event)
                    // Related by sport tag — cross-content discovery
                    if let sport = event.sport, let cat = sportCategoryForKey(sport) {
                        RelatedByTagView(
                            tags: ["sport:\(cat.key)"],
                            excludeEventId: event.id,
                            title: "More \(cat.name)",
                            limit: 4
                        )
                    }
                    espnSection(event)
                }
                .padding(.horizontal)
                .padding(.bottom)
                .frame(maxWidth: contentMaxWidth)
                .frame(maxWidth: .infinity)
            }
        }
    }

    // MARK: - Team Colors

    /// Whether the game-markets payload has any renderable section. All arrays
    /// are optional and can arrive empty for a market-less / aged-out game.
    private func gameMarketsHaveContent(_ gm: GameMarketsResponse) -> Bool {
        !(gm.spreads ?? []).isEmpty
            || !(gm.totals ?? []).isEmpty
            || !(gm.teamTotals ?? []).isEmpty
            || !(gm.periodMarkets ?? []).isEmpty
            || !(gm.playerProps ?? []).isEmpty
            || !(gm.other ?? []).isEmpty
    }

    private var noGameMarketsNote: some View {
        HStack(spacing: 8) {
            Image(systemName: "chart.bar.xaxis")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("No prediction markets for this game yet.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func teamColors(_ event: EventDetail) -> (away: Color, home: Color) {
        let away = Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280")
        let home = Color(hex: event.homeTeamData?.primaryColor ?? "#6b7280")
        return (away, home)
    }

    // MARK: - Chart Header Bar (v2: title + freshness)

    private func chartHeaderBar(_ event: EventDetail) -> some View {
        HStack {
            Text("Win Probability")
                .font(.subheadline)
                .fontWeight(.semibold)
            if isLive {
                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 6, height: 6)
                    Text("Live")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.green)
                }
            } else if isFinished {
                HStack(spacing: 4) {
                    Circle()
                        .fill(.secondary)
                        .frame(width: 6, height: 6)
                    Text("Final")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }



    // MARK: - Hero Section (v2)

    private func heroSection(_ event: EventDetail) -> some View {
        let colors = teamColors(event)
        let hasScore = (isLive || isFinished) && event.homeScore != nil && event.awayScore != nil

        return VStack(spacing: 12) {
            // Top meta row: status badge + countdown + broadcast + date
            HStack(spacing: 8) {
                heroStatusBadge(event)
                Spacer()
                if let broadcast = event.espn?.broadcast {
                    HStack(spacing: 3) {
                        Image(systemName: "tv")
                            .font(.system(size: 8))
                        Text(broadcast)
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    .foregroundStyle(.secondary)
                }
                if let commenceTime = event.commenceTime, let date = commenceTime.asDate {
                    Text(date, format: .dateTime.month(.abbreviated).day().hour().minute())
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // Center: logos flanking giant probabilities
            HStack(spacing: 0) {
                // Away team logo + score
                VStack(spacing: 6) {
                    TeamLogoView(
                        url: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                        teamName: event.awayTeam,
                        color: colors.away,
                        size: logoSize
                    )
                    Text(event.awayTeam)
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.primary)
                    if hasScore {
                        Text("\(event.awayScore ?? 0)")
                            .font(.system(size: 20, weight: .bold, design: .rounded).monospacedDigit())
                            .foregroundStyle(winnerColor(isAway: true, event: event))
                    }
                    if let record = event.awayTeamData?.record {
                        Text(record)
                            .font(.system(size: 9))
                            .foregroundStyle(.quaternary)
                    }
                }
                .frame(maxWidth: .infinity)

                // Giant probabilities centered
                VStack(spacing: 4) {
                    if isFinished {
                        // Winner emphasis for completed games
                        let homeWon = (event.homeScore ?? 0) > (event.awayScore ?? 0)
                        let tied = event.homeScore == event.awayScore
                        if tied {
                            Text("Final")
                                .font(.title2.weight(.bold))
                                .foregroundStyle(.secondary)
                        } else {
                            let winnerName = homeWon
                                ? String(event.homeTeam.split(separator: " ").last ?? "")
                                : String(event.awayTeam.split(separator: " ").last ?? "")
                            Text("\(winnerName) Win")
                                .font(.title3.weight(.bold))
                                .foregroundStyle(homeWon ? colors.home : colors.away)
                        }
                        // Pre-game odds as secondary context
                        if let awayOpeningProbability = event.openingOdds?.awayProbability,
                           let homeOpeningProbability = event.openingOdds?.homeProbability {
                            // #2085 — `opening_odds` is a complement pair too
                            // (`opening_away_probability or round(1 - home, 4)`),
                            // and it carries NO served percents at any deploy, so
                            // this pair is always decided locally.
                            let openDuel = renderedDuelPercents(
                                away: awayOpeningProbability, home: homeOpeningProbability
                            )
                            Text("Opened \(formatProbability(awayOpeningProbability, renderedPercent: openDuel[0])) – \(formatProbability(homeOpeningProbability, renderedPercent: openDuel[1]))")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    } else if let odds = event.currentOdds,
                              let away = odds.awayProbability,
                              let home = odds.homeProbability {
                        let oddsFontSize: CGFloat = sizeClass == .regular ? 36 : 28
                        // #2085 — THE HERO PAIR. `current_odds.away_probability`
                        // is `round(1 - home, 6)` on the backend, so rounding the
                        // two sides independently printed 101 whenever
                        // `home * 100` landed on a half-percent (34 of 414
                        // scheduled/live events, measured 2026-08-21). It could
                        // print 101; it could never print 99.
                        //
                        // BOTH SERVED OR NEITHER. A served away beside a locally
                        // derived home re-opens the same 101 from the other side,
                        // and an older deploy can carry one field and not the
                        // other, so the pair falls back whole.
                        let duelFallback = renderedDuelPercents(away: away, home: home)
                        let bothServed = odds.awayRenderedPercent != nil && odds.homeRenderedPercent != nil
                        let awayPct = bothServed ? odds.awayRenderedPercent : duelFallback[0]
                        let homePct = bothServed ? odds.homeRenderedPercent : duelFallback[1]
                        HStack(spacing: 8) {
                            Text(formatProbability(away, renderedPercent: awayPct))
                                .font(.system(size: oddsFontSize, weight: .black, design: .rounded).monospacedDigit())
                                .foregroundStyle(colors.away)
                            Text("\u{2013}")
                                .font(.title3)
                                .foregroundStyle(.secondary.opacity(0.4))
                            Text(formatProbability(home, renderedPercent: homePct))
                                .font(.system(size: oddsFontSize, weight: .black, design: .rounded).monospacedDigit())
                                .foregroundStyle(colors.home)
                        }
                        // Trend indicator (change since opening).
                        //
                        // #1830. The hero above reads "away – home" ("87 – 13"),
                        // but this delta is computed on HOME and named no team.
                        // An unlabelled "-27%" under "87 – 13" attaches, for the
                        // reader, to whichever number they are tracking — the
                        // leader — so Alex read it as the Red Sox FALLING 27
                        // while they had in fact gone 60 → 87, up 27. Red on top
                        // of that made good news look like bad news.
                        //
                        // Fix: name the team the delta belongs to, and state it
                        // as that team's GAIN. Because away == 1 - home exactly,
                        // "home fell 27" and "away rose 27" are the same fact;
                        // reporting the riser means the caption is never a bare
                        // signed number and its colour always matches its subject.
                        if let openingHome = event.openingOdds?.homeProbability,
                           abs(home - openingHome) > 0.02 {
                            let homeDelta = home - openingHome
                            let homeGained = homeDelta > 0
                            let subject = homeGained
                                ? String(event.homeTeam.split(separator: " ").last ?? "")
                                : String(event.awayTeam.split(separator: " ").last ?? "")
                            let points = Int((abs(homeDelta) * 100).rounded())
                            Text("\(subject) +\(points)% since open")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(homeGained ? colors.home : colors.away)
                        }
                        // #490: hero confidence signal (1-3 bars), computed
                        // client-side from the win-prob source count + whether the
                        // line moved off open. Mirrors the web hero (lib/confidence.ts).
                        HStack(spacing: 6) {
                            Text("Win Probability")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            SignalBarsView(tier: Confidence.fromSources(
                                sourceCount: event.winProbabilitySources?.count,
                                hasMovement: event.openingOdds?.homeProbability
                                    .map { abs(home - $0) > 0.001 } ?? false
                            )?.rawValue)
                        }
                    } else {
                        Text("vs")
                            .font(.title2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                    }
                    // Projected final score
                    if let phs = event.currentOdds?.projectedHomeScore, let pas = event.currentOdds?.projectedAwayScore,
                       !isFinished {
                        Text("Proj. \(Int(pas.rounded()))-\(Int(phs.rounded()))")
                            .font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                    }
                    if let countdownText, !isLive, !isFinished {
                        Text("In \(countdownText)")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundStyle(.blue)
                    }
                    // Opening odds below probability for live games
                    if isLive,
                       let opening = event.openingOdds,
                       let awayOpen = opening.awayProbability,
                       let homeOpen = opening.homeProbability {
                        // #2085 — the live game's opening line, same pair rule
                        // as the settled branch above.
                        let openDuel = renderedDuelPercents(away: awayOpen, home: homeOpen)
                        HStack(spacing: 4) {
                            Text("Opened \(formatProbability(awayOpen, renderedPercent: openDuel[0])) \u{2013} \(formatProbability(homeOpen, renderedPercent: openDuel[1]))")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .fixedSize(horizontal: true, vertical: false)

                // Home team logo + score
                VStack(spacing: 6) {
                    TeamLogoView(
                        url: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                        teamName: event.homeTeam,
                        color: colors.home,
                        size: logoSize
                    )
                    Text(event.homeTeam)
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.primary)
                    if hasScore {
                        Text("\(event.homeScore ?? 0)")
                            .font(.system(size: 20, weight: .bold, design: .rounded).monospacedDigit())
                            .foregroundStyle(winnerColor(isAway: false, event: event))
                    }
                    if let record = event.homeTeamData?.record {
                        Text(record)
                            .font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity)
            }

        }
        .padding()
        .background(
            LinearGradient(
                colors: [
                    colors.away.opacity(0.06),
                    Color.cardBackground,
                    colors.home.opacity(0.06),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    // MARK: - Hero Status Badge

    @ViewBuilder
    private func heroStatusBadge(_ event: EventDetail) -> some View {
        switch event.status {
        case "live":
            StatusBadge(status: "live", gameClock: event.espn?.gameClock, period: event.espn?.period)
        case "completed", "closed":
            StatusBadge(status: event.status)
        default:
            StatusBadge(status: "scheduled", commenceTime: event.commenceTime)
        }
    }

    // MARK: - ESPN

    @ViewBuilder
    private func espnSection(_ event: EventDetail) -> some View {
        let hasData = event.espn?.broadcast != nil || event.commenceTime != nil
        if hasData {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Image(systemName: "info.circle")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    Text("Game Info")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                }
                HStack(spacing: 12) {
                    if let broadcast = event.espn?.broadcast {
                        HStack(spacing: 5) {
                            Image(systemName: "tv")
                                .font(.system(size: 10))
                            Text(broadcast)
                                .font(.caption)
                                .fontWeight(.medium)
                        }
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.08))
                        .clipShape(Capsule())
                    }
                    if let commenceTime = event.commenceTime, let date = commenceTime.asDate {
                        HStack(spacing: 5) {
                            Image(systemName: "clock")
                                .font(.system(size: 10))
                            if isFinished {
                                Text("Final · \(date, format: .dateTime.month(.abbreviated).day().hour().minute())")
                                    .font(.caption)
                                    .fontWeight(.medium)
                            } else if isLive {
                                Text("Started \(date, format: .dateTime.hour().minute())")
                                    .font(.caption)
                                    .fontWeight(.medium)
                            } else {
                                Text("\(date, format: .dateTime.month(.abbreviated).day()) at \(date, format: .dateTime.hour().minute())")
                                    .font(.caption)
                                    .fontWeight(.medium)
                            }
                        }
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.08))
                        .clipShape(Capsule())
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }



    // MARK: - Sources Toggle (v2)

    @ViewBuilder
    private func sourcesToggle(_ event: EventDetail) -> some View {
        if let bookmakers = event.bookmakerOdds, !bookmakers.isEmpty {
            // Legend + toggle button
            VStack(spacing: 0) {
                Divider()
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showSources.toggle()
                    }
                } label: {
                    HStack {
                        Spacer()
                        HStack(spacing: 4) {
                            Text("Individual Sportsbooks")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .foregroundStyle(.secondary)
                            Image(systemName: "chevron.down")
                                .font(.system(size: 8, weight: .bold))
                                .foregroundStyle(.secondary)
                                .rotationEffect(.degrees(showSources ? 180 : 0))
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.plain)

                if showSources {
                    Divider()
                    bookmakerContent(event)
                }
            }
        }
    }

    private func legendItem(color: Color, label: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 1)
                .fill(color)
                .frame(width: 14, height: 2)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private func bookmakerContent(_ event: EventDetail) -> some View {
        let colors = teamColors(event)
        let bookmakers = event.bookmakerOdds ?? []
        return VStack(spacing: 0) {
            ForEach(bookmakers.prefix(10), id: \.bookmaker) { bm in
                let awayProb = bm.awayProbability ?? bm.awayMoneyline.map { moneylineToProbability($0) }
                let homeProb = bm.homeProbability ?? bm.homeMoneyline.map { moneylineToProbability($0) }

                HStack(spacing: 6) {
                    Text(bm.bookmaker ?? "Unknown")
                        .font(.caption)
                        .frame(width: 90, alignment: .leading)
                        .lineLimit(1)

                    if let awayProbability = awayProb, let homeProbability = homeProb {
                        ProbabilityBar(
                            awayProb: awayProbability, homeProb: homeProbability,
                            awayColor: colors.away,
                            homeColor: colors.home,
                            height: 6
                        )
                        .frame(maxWidth: .infinity)

                        Text(formatProbability(awayProbability))
                            .font(.caption2.monospacedDigit())
                            .frame(width: 36, alignment: .trailing)
                        Text(formatProbability(homeProbability))
                            .font(.caption2.monospacedDigit())
                            .frame(width: 36, alignment: .trailing)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 4)
            }
        }
        .padding(.vertical, 8)
    }

    // MARK: - League Page Link

    private static let sportKeyToLeague: [String: (slug: String, label: String)] = [
        "basketball_nba": ("nba", "NBA"),
        "americanfootball_nfl": ("nfl", "NFL"),
        "baseball_mlb": ("mlb", "MLB"),
        "icehockey_nhl": ("nhl", "NHL"),
        "basketball_ncaab": ("ncaab", "NCAA Basketball"),
        "americanfootball_ncaaf": ("ncaaf", "NCAA Football"),
        "basketball_wnba": ("wnba", "WNBA"),
        "soccer_usa_mls": ("mls", "MLS"),
        "soccer_epl": ("epl", "EPL"),
    ]

    @ViewBuilder
    private func leaguePageLink(_ event: EventDetail) -> some View {
        if let sport = event.sport, let league = Self.sportKeyToLeague[sport] {
            NavigationLink(value: Route.leagueGrid(slug: league.slug)) {
                HStack {
                    HStack(spacing: 6) {
                        Text("🏆")
                            .font(.subheadline)
                        Text("\(league.label) Championship Grid")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                .padding()
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Sport Category Mapping

    private struct SportCategory {
        let key: String
        let name: String
    }

    private func sportCategoryForKey(_ sportKey: String) -> SportCategory? {
        let key = sportKey.lowercased()
        if key.hasPrefix("basketball_") { return SportCategory(key: "basketball", name: "Basketball") }
        if key.hasPrefix("americanfootball_") { return SportCategory(key: "football", name: "Football") }
        if key.hasPrefix("baseball_") { return SportCategory(key: "baseball", name: "Baseball") }
        if key.hasPrefix("icehockey_") { return SportCategory(key: "hockey", name: "Hockey") }
        if key.hasPrefix("soccer_") { return SportCategory(key: "soccer", name: "Soccer") }
        if key.hasPrefix("mma_") { return SportCategory(key: "mma", name: "MMA") }
        if key.hasPrefix("golf_") { return SportCategory(key: "golf", name: "Golf") }
        return nil
    }

    // MARK: - Helpers

    /// Compute the most recent game play point from history data for default card display.
    private func lastPlayPoint(event: EventDetail) -> GamePlayPoint? {
        guard let history = vm.history else { return nil }

        let espn = history.espnHistory
        let lastEspn = espn?.last

        // Get probability from the best available source
        let wpHistory = history.winProbHistory?.values.flatMap { $0 }
        let lastWp = wpHistory?.max(by: {
            ($0.timestamp.asDate ?? .distantPast) < ($1.timestamp.asDate ?? .distantPast)
        })
        let lastHist = history.history.last

        let homeProb = lastWp?.homeProbability
            ?? lastHist?.homeProbability
            ?? 0.5

        return GamePlayPoint(
            timestamp: lastEspn?.timestamp ?? lastWp?.timestamp ?? lastHist?.timestamp ?? "",
            homeProb: homeProb,
            awayProb: 1.0 - homeProb,
            homeScore: lastEspn?.homeScore ?? event.homeScore,
            awayScore: lastEspn?.awayScore ?? event.awayScore,
            period: lastEspn?.period,
            clock: lastEspn?.gameClock
        )
    }

    private func winnerColor(isAway: Bool, event: EventDetail) -> Color {
        guard isFinished else { return .primary }
        let away = event.awayScore ?? 0
        let home = event.homeScore ?? 0
        if isAway {
            return away > home ? .primary : .secondary
        } else {
            return home > away ? .primary : .secondary
        }
    }

    private func metadataItem(title: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.subheadline)
                .fontWeight(.medium)
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Countdown Timer

    private func startCountdownTimer() {
        updateCountdown()
        guard isScheduled else { return }
        countdownTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { _ in
            updateCountdown()
        }
    }

    private func updateCountdown() {
        guard let commenceTime = vm.event?.commenceTime,
              let date = commenceTime.asDate else {
            countdownText = nil
            return
        }
        countdownText = formatCountdown(from: date)
    }

    // MARK: - Refresh Countdown

    private var refreshRing: some View {
        let total = max(refreshInterval, 1)
        let progress = Double(total - refreshCountdown) / Double(total)
        let ringColor: Color = isLive ? Color(hex: "#10B981") : .secondary
        return ZStack {
            Circle().stroke(Color.secondary.opacity(0.15), lineWidth: 2)
            Circle().trim(from: 0, to: progress)
                .stroke(ringColor, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text("\(refreshCountdown)")
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundStyle(.secondary)
        }
        .frame(width: 22, height: 22)
    }

    /// Auto-refresh cadence in seconds. Only live events poll (the VM installs a
    /// 30s request timer for `status == "live"` only), so this is the live cadence.
    private var refreshInterval: Int { 30 }

    /// A refresh countdown is honest ONLY when an actual auto-refresh request is
    /// scheduled — which the VM installs for live events only. Scheduled/completed
    /// pages perform no periodic reload, so they must not show a cycling countdown
    /// that implies freshness work that never happens (C43 P2).
    static func showsRefreshCountdown(status: String?) -> Bool { status == "live" }

    /// Seconds until the next scheduled auto-refresh, derived from the LAST ACTUAL
    /// load completion (`vm.lastLoadedAt`) — never a self-resetting timer that fakes
    /// a refresh. `nil` last-load (not loaded yet) shows the full interval.
    static func refreshRemaining(lastLoadedAt: Date?, interval: Int, now: Date) -> Int {
        guard let last = lastLoadedAt else { return interval }
        let elapsed = now.timeIntervalSince(last)
        return Int(ceil(max(0, Double(interval) - elapsed)))
    }

    private func startRefreshCountdown() {
        refreshCountdownTimer?.invalidate()
        // Only live pages have a scheduled refresh to count down to.
        guard Self.showsRefreshCountdown(status: vm.event?.status) else {
            refreshCountdown = 0
            return
        }
        refreshCountdownTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
            refreshCountdown = Self.refreshRemaining(
                lastLoadedAt: vm.lastLoadedAt, interval: refreshInterval, now: Date())
        }
    }

    /// Circular countdown indicator matching web's SVG ring
    private func refreshCountdownView() -> some View {
        let progress = Double(refreshInterval - refreshCountdown) / Double(refreshInterval)
        let ringColor: Color = isLive ? Color(hex: "#10B981") : .secondary

        return HStack(spacing: 6) {
            if !isFinished {
                Text("Next update:")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            ZStack {
                Circle()
                    .stroke(Color.secondary.opacity(0.15), lineWidth: 2.5)
                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(ringColor, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.linear(duration: 0.5), value: progress)
                Text("\(refreshCountdown)")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(.primary)
            }
            .frame(width: 28, height: 28)
        }
    }
}

// MARK: - Game Segments

private struct GameSegmentsView: View {
    let history: EventHistoryResponse
    var sportKey: String?
    let homeTeam: String
    let awayTeam: String
    let homeTeamColor: Color
    let awayTeamColor: Color
    var homeTeamAbbrev: String?
    var awayTeamAbbrev: String?
    var finalHomeScore: Int?
    var finalAwayScore: Int?

    private var homeShort: String {
        homeTeamAbbrev ?? homeTeam.split(separator: " ").last.map(String.init) ?? "Home"
    }

    private var awayShort: String {
        awayTeamAbbrev ?? awayTeam.split(separator: " ").last.map(String.init) ?? "Away"
    }

    var body: some View {
        if let breakdown = SegmentBreakdown(
            history: history,
            sportKey: sportKey,
            finalHomeScore: finalHomeScore,
            finalAwayScore: finalAwayScore
        ) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Game Segments")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Spacer()
                    // Ruling 5: say what the reader is looking at. When some
                    // splits are unknown the caption must admit it, otherwise a
                    // `·` reads as a rendering glitch rather than a known gap.
                    Text(breakdown.hasUnknownSegments
                         ? "Score by period · · = not recorded"
                         : "Score by period")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                // UX-P090 — THE TOTAL COLUMN WAS OFF THE RIGHT EDGE OF EVERY IPHONE,
                // and #1831 is what put it there. Before the 1…N inning ladder this
                // row rendered only the innings the poller observed — often three —
                // so it fit. Rendering all nine (correctly) widened it past the
                // screen, and with `showsIndicators: false` there was no affordance
                // saying so: the reader saw innings 1-7 and no total, on a card
                // whose entire job is reconciling the splits with the score.
                //
                // Measured at the old geometry (54pt label + 9×28pt + 28pt total,
                // 12pt gaps, 32pt card padding) the row is 486pt against a 393pt
                // iPhone 16 and a 375pt SE — over by 93pt and 111pt.
                //
                // Retuned to 44 + 9×22 + 26 with 4pt gaps = 338pt, so a regulation
                // nine-inning game fits the NARROWEST supported phone with room
                // spare, and a 10th inning (364pt) still fits. Extras beyond that
                // scroll — and the indicator is now ON, so the overflow announces
                // itself instead of silently truncating the most important column.
                // 22pt holds a two-digit monospaced caption ("12" ≈ 14pt).
                ScrollView(.horizontal, showsIndicators: true) {
                    Grid(alignment: .trailing, horizontalSpacing: 4, verticalSpacing: 8) {
                        GridRow {
                            Text("")
                                .frame(width: 44, alignment: .leading)
                            ForEach(breakdown.segments) { segment in
                                Text(segment.label)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                    .frame(minWidth: 22)
                            }
                            Text("T")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(.primary)
                                .frame(minWidth: 26)
                                // A hairline gutter so the total reads as a separate
                                // quantity from the last inning rather than a 10th.
                                .padding(.leading, 6)
                        }

                        segmentRow(
                            team: awayShort,
                            color: awayTeamColor,
                            scores: breakdown.segments.map(\.awayScore),
                            total: breakdown.awayTotal
                        )
                        segmentRow(
                            team: homeShort,
                            color: homeTeamColor,
                            scores: breakdown.segments.map(\.homeScore),
                            total: breakdown.homeTotal
                        )
                    }
                    .padding(.vertical, 2)
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    private func segmentRow(team: String, color: Color, scores: [Int?], total: Int) -> some View {
        GridRow {
            HStack(spacing: 6) {
                Circle()
                    .fill(color)
                    .frame(width: 7, height: 7)
                Text(team)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
            }
            // UX-P090: 54 -> 44, matching the header row above. See the geometry
            // note there — the two must move together or the columns shear.
            .frame(width: 44, alignment: .leading)

            ForEach(Array(scores.enumerated()), id: \.offset) { _, score in
                // `·` for an inning we never observed. Printing `0` there would
                // assert nobody scored, which we do not know (#1831).
                Text(score.map(String.init) ?? "·")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(score == nil ? .tertiary : .secondary)
                    .frame(minWidth: 22)
            }

            Text("\(total)")
                .font(.caption.weight(.bold).monospacedDigit())
                .foregroundStyle(.primary)
                .frame(minWidth: 26)
                .padding(.leading, 6)
        }
    }
}

/// Per-segment scoring reconstructed from win-probability polling.
///
/// #1831. This card is NOT fed a line score — no upstream payload carries one
/// (`box_score_data.scoring_plays` is `[]` and there is no `linescore` key), so
/// the splits are inferred from whatever periods the pollers happened to
/// observe. On Alex's 2026-08-13 Sox–Jays specimen that was innings 2, 4 and 8
/// out of nine, and the card rendered `2 4 8` with a total of 5 beside a
/// scoreboard reading 7.
///
/// Two rules now hold, and between them the card can be sparse but never wrong:
///
/// 1. **A split is only reported when it is knowable.** Inning N's runs are
///    `cumulative(N) - cumulative(N-1)`, so both must have been observed. With a
///    gap the runs belong to the *span*, not to the inning that closed it —
///    attributing them to N is what put four Red Sox runs in the 8th. An
///    unknowable split renders `·`, never `0`.
/// 2. **The totals come from the scoreboard**, not from summing observed
///    segments, so this card cannot contradict the hero above it.
///
/// The real fix is ingesting ESPN's linescore; until then this stays honest
/// rather than complete.
private struct SegmentBreakdown {
    let segments: [GameSegment]
    let homeTotal: Int
    let awayTotal: Int
    /// True when at least one rendered segment's split could not be determined.
    let hasUnknownSegments: Bool

    init?(
        history: EventHistoryResponse,
        sportKey: String?,
        finalHomeScore: Int? = nil,
        finalAwayScore: Int? = nil
    ) {
        guard let espnHistory = history.espnHistory else { return nil }

        let cumulativeByPeriod = espnHistory
            .compactMap { point -> CumulativeSegment? in
                guard let rawPeriod = point.period,
                      let homeScore = point.homeScore,
                      let awayScore = point.awayScore,
                      let date = point.timestamp.asDate else {
                    return nil
                }

                let label = Self.formatPeriodLabel(rawPeriod, sportKey: sportKey)
                guard !label.isEmpty else { return nil }
                return CumulativeSegment(
                    label: label,
                    date: date,
                    homeScore: homeScore,
                    awayScore: awayScore
                )
            }
            .sorted { $0.date < $1.date }

        guard !cumulativeByPeriod.isEmpty else { return nil }

        var latestByLabel: [String: CumulativeSegment] = [:]
        var orderedLabels: [String] = []

        for point in cumulativeByPeriod {
            if latestByLabel[point.label] == nil {
                orderedLabels.append(point.label)
            }
            latestByLabel[point.label] = point
        }

        // Baseball gets an explicit inning LADDER (1…9, extended for extras)
        // rather than "whatever the poller saw". Every other sport keeps the
        // observed-labels behaviour unchanged — this change is scoped to the
        // sport whose card was wrong.
        let isBaseball = (sportKey?.lowercased() ?? "").hasPrefix("baseball_")
        let renderedLabels: [String]
        if isBaseball {
            let observed = orderedLabels.compactMap(Int.init)
            let lastInning = max(9, observed.max() ?? 9)
            renderedLabels = (1...lastInning).map(String.init)
        } else {
            renderedLabels = orderedLabels
        }

        var previousCumulative: (home: Int, away: Int)? = (0, 0)
        var segments: [GameSegment] = []
        var sawUnknown = false
        var lastObserved: CumulativeSegment?

        for label in renderedLabels {
            guard let point = latestByLabel[label] else {
                // Never observed. The split is unknown, and so is the split of
                // whichever segment closes the gap — reset the baseline.
                segments.append(GameSegment(label: label, homeScore: nil, awayScore: nil))
                sawUnknown = true
                previousCumulative = nil
                continue
            }

            defer {
                previousCumulative = (point.homeScore, point.awayScore)
                lastObserved = point
            }

            guard let previous = previousCumulative else {
                // Observed, but the preceding segment was not, so the runs since
                // then cannot be attributed to this one alone.
                segments.append(GameSegment(label: label, homeScore: nil, awayScore: nil))
                sawUnknown = true
                continue
            }

            let homeSegmentScore = point.homeScore - previous.home
            let awaySegmentScore = point.awayScore - previous.away
            guard homeSegmentScore >= 0, awaySegmentScore >= 0 else {
                // A cumulative score that went DOWN means these rows describe
                // two different games. Refuse the whole card rather than render
                // a negative inning.
                return nil
            }
            segments.append(
                GameSegment(label: label, homeScore: homeSegmentScore, awayScore: awaySegmentScore)
            )
        }

        // Totals: prefer the scoreboard, so this card can never disagree with
        // the hero. Fall back to the last cumulative we actually observed.
        let resolvedHome = finalHomeScore ?? lastObserved?.homeScore ?? 0
        let resolvedAway = finalAwayScore ?? lastObserved?.awayScore ?? 0

        // A ladder in which nothing is knowable is a row of dots — it tells the
        // reader nothing and occupies the space where a scoreboard should be.
        let knownSegments = segments.filter { $0.homeScore != nil }
        guard !segments.isEmpty, !knownSegments.isEmpty else { return nil }
        guard resolvedHome + resolvedAway > 0 else { return nil }

        self.segments = segments
        self.homeTotal = resolvedHome
        self.awayTotal = resolvedAway
        self.hasUnknownSegments = sawUnknown
    }

    private static func formatPeriodLabel(_ rawPeriod: String, sportKey: String?) -> String {
        let trimmed = rawPeriod.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = trimmed.lowercased()
        let sport = sportKey?.lowercased() ?? ""

        if lower == "halftime" || lower == "half time" || lower == "ht" { return "" }
        if lower.contains("pre") || lower.contains("final") { return "" }
        let number = firstNumber(in: lower)

        // Sport-specific branches first — baseball must come before the
        // generic OT check because "Bottom 3rd" contains "ot" in "Bottom".
        if sport.hasPrefix("baseball_") {
            if let number { return "\(number)" }
        } else if sport.hasPrefix("basketball_") || sport.hasPrefix("americanfootball_") {
            if lower.contains("ot") || lower.contains("overtime") {
                return number.map { "OT\($0)" } ?? "OT"
            }
            if let number { return "Q\(number)" }
        } else if sport.hasPrefix("icehockey_") {
            if lower.contains("ot") || lower.contains("overtime") {
                return number.map { "OT\($0)" } ?? "OT"
            }
            if let number { return "P\(number)" }
        } else if sport.hasPrefix("soccer_") {
            if let number { return number <= 1 ? "1H" : "2H" }
        } else {
            if lower.contains("ot") || lower.contains("overtime") {
                return number.map { "OT\($0)" } ?? "OT"
            }
        }

        if lower.hasPrefix("q"), let number { return "Q\(number)" }
        if lower.contains("quarter"), let number { return "Q\(number)" }
        if lower.contains("period"), let number { return "P\(number)" }
        if lower.contains("half"), let number { return "\(number)H" }
        if let number { return "\(number)" }
        return trimmed
    }

    private static func firstNumber(in value: String) -> Int? {
        var digits = ""
        for character in value {
            if character.isNumber {
                digits.append(character)
            } else if !digits.isEmpty {
                break
            }
        }
        return Int(digits)
    }
}

private struct GameSegment: Identifiable {
    let label: String
    /// `nil` when this segment's split was never observed — rendered `·`, never `0`.
    let homeScore: Int?
    let awayScore: Int?

    var id: String { label }
}

private struct CumulativeSegment {
    let label: String
    let date: Date
    let homeScore: Int
    let awayScore: Int
}

// MARK: - Line Movement Explainer

private struct LineMovementExplainerView: View {
    let analysis: LineMovementResponse
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    private var featuredMovements: [LineMovement] {
        Array(analysis.movements.prefix(2))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.blue)
                Text("Why the Line Moved")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
            }

            if let explanation = cleanedText(analysis.explanation) {
                Text(explanation)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let disagreement = analysis.disagreementData,
               let disagreementText = cleanedText(analysis.disagreementExplanation) {
                disagreementBlock(disagreement, text: disagreementText)
            }

            if !featuredMovements.isEmpty {
                VStack(spacing: 8) {
                    ForEach(featuredMovements, id: \.timestampStart) { movement in
                        movementRow(movement)
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func disagreementBlock(_ disagreement: LineMovementDisagreement, text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.left.and.right")
                    .font(.system(size: 11, weight: .semibold))
                Text("\(sourceName(disagreement.source)) differs by \(formatProbability(disagreement.divergence))")
                    .font(.caption.weight(.semibold))
            }
            .foregroundStyle(.orange)

            HStack(spacing: 8) {
                probabilityPill(
                    label: "Sportsbooks",
                    value: disagreement.sportsbookHomeProb,
                    color: homeColor
                )
                probabilityPill(
                    label: sourceName(disagreement.source),
                    value: disagreement.predictionMarketHomeProb,
                    color: .orange
                )
            }

            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(Color.orange.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func movementRow(_ movement: LineMovement) -> some View {
        let beneficiary = movement.change >= 0 ? homeTeam : awayTeam
        let color = movement.change >= 0 ? homeColor : awayColor

        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: movement.change >= 0 ? "arrow.up.right" : "arrow.down.left")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(color)
                .frame(width: 18, height: 18)
                .background(color.opacity(0.12))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(beneficiary)
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                    Text("+\(formatProbability(movement.magnitude))")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(color)
                    if movement.isMajor {
                        Text("Major")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.red)
                            .clipShape(Capsule())
                    }
                }

                if let context = cleanedText(movement.context) {
                    Text(context)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Text("\(formatProbability(movement.homeProbBefore)) to \(formatProbability(movement.homeProbAfter)) home win probability")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func probabilityPill(label: String, value: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Text(formatProbability(value))
                .font(.caption.monospacedDigit().weight(.bold))
                .foregroundStyle(color)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func sourceName(_ source: String) -> String {
        switch source.lowercased() {
        case "kalshi": return "Kalshi"
        case "polymarket": return "Polymarket"
        default: return source.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func cleanedText(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
