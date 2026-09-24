import SwiftUI

/// The Sources list's own width, so #4107's label column can be clamped against
/// the room the row actually has. A preference key rather than a
/// `UIScreen.main.bounds` read: gotcha #27 — Stage Manager can hand back a
/// background scene, and this file's neighbours have been walked off that API
/// deliberately.
private struct SourceRowWidthKey: PreferenceKey {
    static let defaultValue: Double = 0
    static func reduce(value: inout Double, nextValue: () -> Double) {
        value = max(value, nextValue())
    }
}

// MARK: - View

struct EventDetailView: View {
    let eventId: Int
    @StateObject private var vm: EventDetailViewModel
    @State private var selectedPlayPoint: GamePlayPoint?
    /// Closed for every reader. Starts open only when the LOOK rig asks
    /// (`-launch_expand_sections`), which is the only way this list can be
    /// photographed — the rig cannot tap a chevron. See `LaunchRig`.
    @State private var showSources = LaunchRig.expandsCollapsedSections()
    /// The width of a row in the sources disclosure, reported by the
    /// `GeometryReader` behind the whole panel, so both lists inside it can size
    /// their label column against the room the row actually has rather than a
    /// literal. `0` until the first layout pass.
    ///
    /// Measured on the PANEL and not on either list, because the two lists render
    /// under independent conditions. An event with sportsbook odds and no
    /// aggregate sources draws the books list alone — the disclosure's own toggle
    /// says "Individual Sportsbooks" for exactly that case — and if only the
    /// sources list published this, that event would leave it `0` forever. `0`
    /// means "not measured yet", which `maximumLabelWidth` deliberately treats as
    /// UNCLAMPED, so the books column would have quietly lost the bar's floor.
    @State private var sourceRowWidth: Double = 0
    /// #1833 — the narrower of the two stacked charts' inline plots, published by
    /// each (`PageAxisPlotWidthPreferenceKey`) and handed back to both, so one
    /// page draws one clock. Only this view can see both charts.
    @State private var pageAxisPlotWidth: CGFloat = 0
    private var sharedChartDomain: ClosedRange<Date>? {
        guard let event = vm.event,
              let commenceTime = event.commenceTime,
              let scheduledStart = commenceTime.asDate else { return nil }
        // #7878 D — a stored start the payload says is NOT a start (Kalshi's
        // expected resolution hour, `commence_time_is_kickoff: false`) cannot
        // open the axis either. It is the far end of the match: an axis from
        // there puts the whole contest off the left edge however the chart
        // filters its points. `nil` is the existing fallback — each chart
        // takes its own domain from what it drew.
        guard OddsChartView.sinceStartCut(
            commenceTime: scheduledStart,
            commenceTimeIsKickoff: vm.history?.commenceTimeIsKickoff
        ) != nil else { return nil }

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
        if EventState.isFinished(event.status) {
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

    /// #3978 (Alex, D93 = A) — the hero restacks at the accessibility text sizes.
    ///
    /// Read here rather than inside `heroSection` because it decides a LAYOUT and
    /// not a font: at `.accessibility1` and above the hero's three columns cannot
    /// fit side by side on any phone, and the row does not merely get tight, it
    /// overflows its parent and is CENTRED in the overflow — so the card bleeds off
    /// both edges at once and the team names collapse to `Cle m…`.
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(eventId: Int) {
        self.eventId = eventId
        _vm = StateObject(wrappedValue: EventDetailViewModel(eventId: eventId))
    }

    private var isLive: Bool { vm.event?.status == "live" }
    /// #4002 — this page kept a PRIVATE COPY of a vocabulary `EventState`
    /// already owns, and `suspended` (live/048) matched none of its arms. So
    /// the hero drew no badge, no score, a grey `Proj. 3-2` where the score
    /// belongs and a kick-off time for a match played four days earlier.
    /// `EventCardView` took that exact repair under CERT-786 and this page did
    /// not, because a copy is invisible to the fix applied to the original.
    /// Read the vocabulary; never restate it.
    private var isFinished: Bool { EventState.isFinished(vm.event?.status) }
    /// #4021 — the CLOCK is part of this test. See `EventState.isSuspendedAndStarted`.
    private var isSuspended: Bool {
        EventState.isSuspendedAndStarted(
            vm.event?.status, commenceTime: vm.event?.commenceTime?.asDate)
    }
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

    /// The title's rungs, or nil before a score exists to protect.
    private var titleRungs: EventNavTitle.Rungs? {
        guard let event = vm.event,
              let hs = event.homeScore, let as_ = event.awayScore else { return nil }
        // #4880 — this joined the raw pair with no guard at all, so the title
        // read "… • 25' 25'" on every live soccer match.
        let state = PeriodLabel.liveStatusText(
            period: event.espn?.period, gameClock: event.espn?.gameClock) ?? ""
        return EventNavTitle.rungs(
            away: event.awayTeam, home: event.homeTeam,
            awayScore: as_, homeScore: hs,
            awayServed: event.awayTeamData?.abbreviation,
            homeServed: event.homeTeamData?.abbreviation,
            state: state,
            sportKey: event.sport
        )
    }

    /// The flat title. Still what the bar shows on macOS, and on every platform
    /// it is what a pushed view's back button and VoiceOver read — so it stays
    /// the WIDEST rung, which is the whole sentence.
    private var dynamicTitle: String {
        guard let event = vm.event else { return "Game Details" }
        if let rungs = titleRungs { return (rungs.withState ?? rungs.labelled).text }
        return EventNavTitle.scoreless(
            away: event.awayTeam, home: event.homeTeam,
            awayServed: event.awayTeamData?.abbreviation,
            homeServed: event.homeTeamData?.abbreviation,
            sportKey: event.sport
        )
    }

    #if os(iOS)
    /// #4900 — the inline title, laid out rather than truncated.
    ///
    /// `ViewThatFits` walks the rungs widest-first and takes the first that the
    /// bar can actually hold; the bar measures, because no character count
    /// here can (the four photographed specimens broke between 16 and 24
    /// characters in the same bar). The floor is rendered as PARTS with the two
    /// numbers at a higher layout priority than the two names, so even a club
    /// whose three-glyph code somehow does not fit loses letters off a name and
    /// never a digit off a score — which is the defect this exists to end.
    @ViewBuilder
    private var navTitleView: some View {
        if let rungs = titleRungs {
            ViewThatFits(in: .horizontal) {
                if let full = rungs.withState {
                    Text(full.text).font(.headline).lineLimit(1)
                }
                Text(rungs.labelled.text).font(.headline).lineLimit(1)
                scoreProtectedTitle(rungs.compact)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(dynamicTitle)
        } else {
            Text(dynamicTitle).font(.headline).lineLimit(1)
        }
    }

    private func scoreProtectedTitle(_ c: EventNavTitle.Candidate) -> some View {
        HStack(spacing: 4) {
            Text(c.away).lineLimit(1).truncationMode(.tail)
            Text(c.awayScore).layoutPriority(1)
            Text("-").layoutPriority(1)
            Text(c.home).lineLimit(1).truncationMode(.tail)
            Text(c.homeScore).layoutPriority(1)
        }
        .font(.headline)
    }
    #endif

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
                #if os(iOS)
                ToolbarItem(placement: .principal) {
                    navTitleView
                }
                #endif
                // #8320 — the page's ONE freshness status, and the manual
                // refresh it has always been. Live only: no other page polls.
                if isLive {
                    ToolbarItem(placement: .cancellationAction) {
                        Button { Task { await vm.load() } } label: {
                            refreshStatus
                        }
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    HStack(spacing: 4) {
                        ShareLink(item: shareURL) {
                            Image(systemName: "square.and.arrow.up")
                                .font(.system(size: 14))
                        }
                        .recordsShareOpened {
                            ShareInstrumentation.recordShareOpened(
                                itemType: "event",
                                itemId: String(eventId),
                                itemName: vm.event.map { "\($0.awayTeam) vs \($0.homeTeam)" },
                                category: DiscoverCategory.token(forSport: vm.event?.sport),
                                surface: .eventDetail
                            )
                        }
                        PinButton(type: "event", id: eventId)
                    }
                }
            }
            .task {
                await vm.load()
                AnalyticsService.trackEventDetailView(eventId: eventId, sport: vm.event?.sport)
            }
            .refreshable {
                await vm.load()
            }
            .onDisappear {
                vm.stopRefresh()
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
                                     // #6381 — so the empty state stops saying
                                     // "yet" under a hero that says settled.
                                     venueSettled: event.venueSettled == true,
                                     homeTeamName: event.homeTeam,
                                     awayTeamName: event.awayTeam,
                                     homeTeamLogo: event.homeTeamData?.logoSmall,
                                     awayTeamLogo: event.awayTeamData?.logoSmall,
                                     homeTeamAbbrev: event.homeTeamData?.abbreviation,
                                     awayTeamAbbrev: event.awayTeamData?.abbreviation,
                                     sportKey: event.sport,
                                     refreshStreaming: vm.streamDelivering,
                                     forcedDomain: sharedChartDomain,
                                     pageAxisPlotWidth: pageAxisPlotWidth,
                                     selectedPlayPoint: $selectedPlayPoint,
                                     preloadedHistory: vm.history,
                                     // #920 — the pushed blends the hero is
                                     // already showing, so the chart's right
                                     // edge reaches the same moment it does.
                                     liveFrames: vm.liveBlend)
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

                        // #3410 — this link goes to THIS event's model breakdown,
                        // so on a game with no readings at all it promises a page
                        // that is itself empty. With the chart collapsed and
                        // `sourcesToggle` already self-hiding, it was the last
                        // thing left in the card and read as stranded.
                        if Self.hasAnyProbabilityEvidence(event: event, history: vm.history) {
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
                            sportKey: event.sport,
                            commenceTime: event.commenceTime,
                            eventStatus: event.status,
                            homeTeamColor: teamColors(event).home,
                            awayTeamColor: teamColors(event).away,
                            homeTeamAbbrev: event.homeTeamData?.abbreviation,
                            awayTeamAbbrev: event.awayTeamData?.abbreviation,
                            homeTeamLogo: event.homeTeamData?.logoSmall,
                            awayTeamLogo: event.awayTeamData?.logoSmall,
                            forcedDomain: sharedChartDomain,
                            pageAxisPlotWidth: pageAxisPlotWidth
                        )
                    }
                    // Market Maps (margin + total density curves)
                    if let gameMarkets = vm.gameMarkets {
                        // #4982 — the page is the only thing that can see both
                        // cards, so the page is what decides which one states
                        // that we do not hold the played count. Everything but
                        // the payload's presence is decided inside the chart's
                        // own predicate, so this cannot drift from what the
                        // chart above actually rendered.
                        let absenceStatedAbove = vm.history.map {
                            ScoreDifferentialChartView.statesPlayedCountAbsence(
                                history: $0,
                                sportKey: event.sport,
                                eventStatus: event.status,
                                commenceTime: event.commenceTime
                            )
                        } ?? false
                        MarketMapView(
                            gameMarkets: gameMarkets,
                            eventStatus: event.status,
                            commenceTime: event.commenceTime?.asDate,
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
                            // #6290 — the pre-game total, from `opening_odds` and
                            // never from `current_odds`. The two are the same
                            // number before the off and diverge with every score.
                            openingOverUnder: event.openingOdds?.overUnder,
                            homeScore: event.homeScore,
                            awayScore: event.awayScore,
                            absenceStatedAbove: absenceStatedAbove,
                            halfScores: halfScores(event)
                        )
                    }
                    // Total Points Spectrum (projected scoring + threshold ladder)
                    if let gameMarkets = vm.gameMarkets {
                        TotalPointsSpectrumView(
                            gameMarkets: gameMarkets,
                            eventStatus: event.status,
                            commenceTime: event.commenceTime?.asDate,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeColor: teamColors(event).home,
                            awayColor: teamColors(event).away,
                            sportKey: event.sport,
                            overUnder: event.currentOdds?.overUnder,
                            // #6290 — as on the maps above.
                            openingOverUnder: event.openingOdds?.overUnder,
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
                            commenceTime: event.commenceTime?.asDate,
                            boxScore: vm.relatedFutures?.boxScore
                        )
                    }
                    // Special Event Markets (game props, novelty, MVP)
                    if let gameMarkets = vm.gameMarkets,
                       let otherMarkets = gameMarkets.other,
                       otherMarkets.count >= 3 {
                        SpecialEventMarketsView(
                            markets: otherMarkets,
                            eventStatus: event.status,
                            commenceTime: event.commenceTime?.asDate
                        )
                    }
                    // Graceful empty state: a market-less game (e.g. an aged-out
                    // closed game whose Kalshi/odds markets have expired) has no
                    // market sections to show. Say so rather than leaving a gap or
                    // assuming a section exists (#1092).
                    if let gameMarkets = vm.gameMarkets,
                       !gameMarketsHaveContent(gameMarkets) {
                        noGameMarketsNote(status: event.status)
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
                .onPreferenceChange(PageAxisPlotWidthPreferenceKey.self) { width in
                    pageAxisPlotWidth = width
                }
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

    /// #3821 — the copy is tensed by ``EventState/noGameMarketsLine(status:)``.
    /// It takes the status rather than the sentence so the tense cannot drift
    /// from the one place native decides what "over" means, which is the same
    /// reason #3465 moved its two notes onto `SportVocab`.
    private func noGameMarketsNote(status: String?) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "chart.bar.xaxis")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(EventState.noGameMarketsLine(status: status))
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    /// #2902 — the same both-sides-one-grey fallback the Sports card had, on the
    /// hero bar of every tennis and golf event page. One palette, one contract:
    /// the pair always reads apart. See `ProbabilityBarPalette`.
    ///
    /// #7036 — and a second, independent contract: the pair also has to be
    /// visible on the page it is drawn on. Every consumer of this helper — the
    /// hero, both charts, the spectrums, the player-prop rows, the source and
    /// bookmaker tables, Championship Path, Related Futures — paints on the same
    /// white card surface, so a club whose brand colour IS white (Fulham,
    /// Tottenham, Real Madrid: 26 clubs store `#ffffff`) had its half of every
    /// one of them painted invisible. A colour under the WCAG floor is reported
    /// to the palette as **absent**, which is what makes this a floor under the
    /// existing behaviour rather than a second palette: the palette then runs
    /// its own default-and-ladder path and re-derives the #2902 pair contract on
    /// the substituted value, so flooring one side cannot collapse the two onto
    /// one colour. See `TeamTextContrast`.
    private func teamColors(_ event: EventDetail) -> (away: Color, home: Color) {
        TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )
    }

    /// #7943 — what each half was played to, for the four half maps.
    ///
    /// Read off the SAME `espn_history` the segment table above already
    /// consumes, so the two cards on this page cannot disagree about the
    /// halftime score. `HalfScores` withholds rather than guesses; `.none` is a
    /// card that draws no result, which is the behaviour every half map had
    /// before this.
    private func halfScores(_ event: EventDetail) -> HalfScores.Pair {
        guard let espnHistory = vm.history?.espnHistory else { return .none }
        let readings = espnHistory.compactMap { point -> HalfScoreReading? in
            guard let period = point.period,
                  let home = point.homeScore,
                  let away = point.awayScore,
                  let date = point.timestamp.asDate else { return nil }
            return HalfScoreReading(period: period, home: home, away: away, date: date)
        }
        return HalfScores.split(
            readings: readings,
            currentHome: event.homeScore,
            currentAway: event.awayScore,
            isDone: isFinished
        )
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

    /// Whether the hero draws the two team scores.
    ///
    /// #4002 — the gate was `(isLive || isFinished) && …`, so a SUSPENDED game
    /// drew no score even when it had one. On `15298408` (Yankees @ Padres,
    /// played 2026-09-06, `status='suspended'`, final 3–4) the navigation title
    /// one line above the hero read "Yankees 3 - Padres 4" while the hero
    /// itself printed nothing under either crest. A suspended game is the state
    /// where the score matters MOST: it is the only thing anybody got.
    static func showsScore(status: String?, away: Int?, home: Int?) -> Bool {
        guard away != nil, home != nil else { return false }
        return status == "live" || EventState.isFinished(status) || EventState.isSuspended(status)
    }

    /// Whether "where to watch" still answers a question anybody has.
    ///
    /// #4002 — the hero's broadcast chip had NO status gate, so `15298408`
    /// offered "MLB.TV, Padres.TV, YES" two days after the game was abandoned,
    /// next to a 1:10 PM start time. A broadcast listing is a promise about the
    /// future; on a game that is over or will never be resumed it is #3821's
    /// false promise worn as a chip, and Alex's standing ruling that settled
    /// means settled binds a chip as tightly as it binds a hero.
    static func showsBroadcast(status: String?, commenceTime: Date?, now: Date = Date()) -> Bool {
        !EventState.isFinished(status)
            && !EventState.isSuspendedAndStarted(status, commenceTime: commenceTime, now: now)
    }

    /// Whether the projected final score is still a projection of anything.
    ///
    /// #4002 — the gate was `!isFinished`, which asks whether the game is over
    /// and NOT whether a final can still arrive. Measured on production over
    /// the 7 days to 2026-09-08: **184 suspended games carrying a projection**
    /// against 1 live one. On every one of those the grey pair was the only
    /// numbers on a hero that carried no state label at all — a projected final
    /// for a match nobody will ever grade.
    ///
    /// #4018 — the rule moved to `EventState.canStillBeGraded`, unchanged, because
    /// the three market cards one scroll below this hero needed the same answer
    /// and were each carrying their own `isFinished` copy instead. This stays as
    /// the hero's name for it; the logic has exactly one home.
    ///
    /// #5697 AC2 — AND A PROJECTION OF THE FINAL NEEDS A GAME WHOSE STATE THE
    /// READER CAN SEE. `canStillBeGraded` asks whether a final can still arrive;
    /// it cannot ask whether the reader has anything to read the forecast
    /// against. Production specimen `15311077` (Fukuoka SoftBank Hawks v Chiba
    /// Lotte Marines, NPB), `status='live'`, both scores null, nearly two hours
    /// past its own first pitch, served a projection captured minutes earlier:
    /// the hero drew a confident `7 - 5.5` shaped exactly like a scoreline with
    /// no score anywhere on it. The number is FRESH — that was measured, not
    /// assumed — and it is still unreadable, because a projected FINAL only
    /// means something against how much game is left, and a reader who cannot
    /// see the score cannot tell the first inning from the ninth.
    ///
    /// BEFORE THE OFF THE PROJECTION IS THE HONEST THING and stays: nothing has
    /// happened yet, so the frame is known and the forecast says just what it
    /// means. It is withdrawn only once the game is underway, where a reader has
    /// started expecting a score. Notice 34 — where a number cannot be shown
    /// honestly the space is left empty rather than explained.
    ///
    /// THE PAIR, NOT A SIDE: `hasScore` is the hero's own `showsScore`, the very
    /// value the score row is drawn from one line below. The question is what is
    /// ON THE SCREEN beside the projection, not what the payload happens to
    /// carry, so a status that draws no score withholds the forecast too.
    ///
    /// Twin of the web's `projectionHasGameStateToFrame` (#5803, `ade48eb95`).
    /// It reuses `EventState.hasStarted`, whose nil-date default is TRUE where
    /// the web's is false; that boundary is unreachable — production carries 0
    /// events with a null `commence_time` (measured 2026-09-12) — and reusing
    /// the shared predicate keeps one definition of "has started" rather than
    /// growing the second one #4018 exists to prevent. It fails toward
    /// withholding, which is the safe direction here.
    static func showsProjection(
        status: String?, commenceTime: Date?, hasScore: Bool, now: Date = Date()
    ) -> Bool {
        guard EventState.canStillBeGraded(status, commenceTime: commenceTime, now: now) else {
            return false
        }
        let underway = status == "live"
            || EventState.hasStarted(commenceTime: commenceTime, now: now)
        return !underway || hasScore
    }

    private func heroSection(_ event: EventDetail) -> some View {
        let colors = teamColors(event)
        let hasScore = EventDetailView.showsScore(
            status: event.status, away: event.awayScore, home: event.homeScore)

        // #3978 (Alex, D93 = A) — ONE decision, applied to both rows of the hero.
        //
        // `AnyLayout` rather than an `if/else` over two copies of the body:
        // swapping the layout keeps the children's identity, so nothing inside
        // re-initialises when the reader changes text size, and — the reason that
        // matters here — there is exactly one copy of the hero to maintain. Two
        // copies is how the three-column version and its replacement drift apart.
        // `PoliticsView:330` already carries this idiom.
        let stacked = dynamicTypeSize.isAccessibilitySize
        let heroLayout = stacked
            ? AnyLayout(VStackLayout(spacing: 16))
            : AnyLayout(HStackLayout(spacing: 0))
        let metaLayout = stacked
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
            : AnyLayout(HStackLayout(spacing: 8))

        return VStack(spacing: 12) {
            // Top meta row: status badge + countdown + broadcast + date
            //
            // Stacks with the rest. Left as a row it is the SECOND thing that
            // bleeds: the `FINAL` chip was cut off the left edge while
            // "Sep 5 at 6:40 PM" was cut off the right, in the same frame.
            metaLayout {
                // #6544 — THE TICK IS HERE NOW, and it has to be somewhere.
                //
                // The chip derives "In 4d 12h" from `commenceTime` on every
                // render, so it only ages when something re-renders it. What did
                // that until now was a view-wide 60-second `Timer` writing a
                // `countdownText` @State — and the centre column's duplicate copy
                // was that state's ONLY reader. SwiftUI re-renders a view only
                // when the body read the value that changed, so deleting the
                // duplicate without replacing the tick would have frozen the chip
                // at whatever it said when the page appeared: a page left open
                // over lunch still reading "In 4d 12h".
                //
                // `TimelineView` puts the tick on the one view that needs it,
                // which is both smaller than the old machinery (the @State, the
                // Timer, its start and its invalidation all go) and impossible to
                // strand again — there is no second reader to lose. It is not
                // gated on `scheduled`: a minute is a long interval beside the
                // half-second refresh ring a live page already runs, and gating
                // would put the clock back in a branch.
                //
                // #7019 AMENDS THE SENTENCE ABOVE: this is no longer the only
                // thing ageing the chip. Wrapping the badge fixed the hero and
                // left the four other `StatusBadge` call sites frozen — the My
                // Stuff / Discover / Sports row, both search rows and the team
                // schedule — so the tick moved onto the badge itself, which
                // observes `MinuteClock.shared`. This wrapper is kept rather
                // than deleted because it re-renders the WHOLE hero chip chain
                // (live clock, FINAL, settled, suspended), not just the
                // scheduled arm, and `HeroSaysTheCountdownOnce6544Tests
                // .testTheChipStillTicks` pins it. Removing it would not freeze
                // the countdown today; it would quietly narrow what re-renders.
                TimelineView(.periodic(from: .now, by: 60)) { _ in
                    heroStatusBadge(event)
                }
                // A `Spacer` pushes to both ends of a ROW; in a column it is a
                // blank line that shoves the date away from the badge.
                if !stacked { Spacer() }
                if let broadcast = event.espn?.broadcast,
                   EventDetailView.showsBroadcast(
                    status: event.status, commenceTime: event.commenceTime?.asDate) {
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

            // Center: logos flanking giant probabilities — or, at accessibility
            // sizes, away above the percentage above home (D93 = A). The order is
            // the row's own order read top-to-bottom, so the hero says the same
            // sentence either way.
            heroLayout {
                // Away team logo + score
                VStack(spacing: 6) {
                    TeamLogoView(
                        url: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                        teamName: event.awayTeam,
                        color: colors.away,
                        size: logoSize,
                        // #4624 — the hero knew the sport and did not pass it,
                        // so a tennis player's circle took the compound-CLUB
                        // fork and drew their initials instead of their surname.
                        sportKey: event.sport,
                        // #4720 — the hero draws BOTH circles, so the badge is
                        // resolved against the other side and cannot print the
                        // word the two clubs share.
                        opponentName: event.homeTeam
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
                        let outcome = heroOutcome(event)
                        let homeWon = outcome == .home
                        if let drawLabel = outcome.drawLabel {
                            // #4915 — a draw IS a result, and this slot used to
                            // throw it away: the tie branch printed the bare
                            // status word in the loser's grey, so a 1–1 read as
                            // "both teams lost" beside a decisive match's bold
                            // "Munich Win". Same font as the verdict it sits in
                            // for, and `.primary` because nobody lost here.
                            Text(drawLabel)
                                .font(.title3.weight(.bold))
                                .foregroundStyle(.primary)
                        } else if outcome == .undecided {
                            // Over, and we cannot name a result — no score held
                            // for a side. The neutral status word is all we can
                            // honestly print (the `final_unresolved` state, said
                            // in the verdict slot rather than in the number).
                            Text("Final")
                                .font(.title2.weight(.bold))
                                .foregroundStyle(.secondary)
                        } else {
                            // #3430 — "Tigers Win" answered nothing on Clemson
                            // 10 – LSU 51, because both sides shorten to
                            // "Tigers". A winner's name is only a name if the
                            // LOSER could not have been called it too, so the
                            // pair decides even though one side is shown.
                            let duel = TeamShortName.shortPair(
                                away: event.awayTeam, home: event.homeTeam,
                                sportKey: event.sport
                            )
                            let winnerName = homeWon ? duel.home : duel.away
                            Text("\(winnerName) Win")
                                .font(.title3.weight(.bold))
                                .foregroundStyle(homeWon ? colors.home : colors.away)
                        }
                        // Pre-game odds as secondary context
                        if let opened = DrawPricedWinner.printablePair(
                            away: event.openingOdds?.awayProbability,
                            home: event.openingOdds?.homeProbability,
                            sport: event.sport) {
                            // #2085 — `opening_odds` is a complement pair too
                            // (`opening_away_probability or round(1 - home, 4)`),
                            // and it carries NO served percents at any deploy, so
                            // this pair is always decided locally.
                            //
                            // #5271 — which also makes it the same lie as the
                            // hero's on a draw-priced sport, and it withholds
                            // the same slot. Named here even though the verdict
                            // above it is too: this branch sits under
                            // "{Winner} Win", so nothing else in the column is
                            // carrying the subject for it.
                            if let awayOpen = opened.away {
                                let openDuel = renderedDuelPercents(
                                    away: awayOpen, home: opened.home
                                )
                                Text("Opened \(formatProbability(awayOpen, renderedPercent: openDuel[0])) – \(formatProbability(opened.home, renderedPercent: openDuel[1]))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            } else {
                                let named = TeamShortName.shortPair(
                                    away: event.awayTeam, home: event.homeTeam,
                                    sportKey: event.sport
                                )
                                Text("Opened \(named.home) \(formatProbability(opened.home))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    } else if EventState.showsVenueSettledVerdict(
                        event.status,
                        venueSettled: event.venueSettled,
                        commenceTime: event.commenceTime?.asDate) {
                        // #6381 — the slot that said **vs** over a match that
                        // was played four days ago. Placed ABOVE the price pair
                        // deliberately: a settled question's story is its
                        // answer, and the two big percentages under two crests
                        // are read as what the market thinks WILL happen. The
                        // finished branch above resolves the same way — verdict
                        // first, the pre-game number demoted to a caption.
                        if let result = event.venueSettledResult {
                            // VERBATIM, and it is an outcome NAME rather than a
                            // scoreline: "Draw 0-0" in soccer, "Aryna Sabalenka
                            // wins 2-0" in tennis (sets, not games). The
                            // producer's contract says do not parse it and the
                            // reason is that sentence — anything that split it
                            // into two numbers would publish a tennis set score
                            // as a game score.
                            // 🔴 BOUNDED, AND THE FIRST DRAFT WAS NOT — the
                            // after-shot caught it. This column is the hero's
                            // inflexible middle: the two crest columns take
                            // `.frame(maxWidth: .infinity)` and this one gets
                            // its ideal width, which for a verdict like "Sion
                            // Win" is fine and for "Brighton & Hove Albion wins
                            // 5-0" is 31 characters at 20pt. On `15310517` that
                            // pushed the whole hero card off BOTH screen edges —
                            // the away crest clipped at the left, "COV" at the
                            // right, the date cut off. The string is the
                            // venue's, its length is not ours to choose, so the
                            // slot has to accept any offered width instead.
                            Text(result)
                                .font(.title3.weight(.bold))
                                .foregroundStyle(.primary)
                                .multilineTextAlignment(.center)
                                .lineLimit(3)
                                .minimumScaleFactor(0.55)
                                .frame(maxWidth: EventDetailView.verdictSlotWidth)
                                .layoutPriority(-1)
                        } else {
                            // 370 of the issue's 426 rows are graded on props
                            // alone, so there is no score to name and inventing
                            // one from a prop is the fabricated-100% trap the
                            // producer refuses on its own side.
                            //
                            // 🔴 THE BADGE ALREADY SAID IT — caught in the
                            // after-shot, not by a test. This slot first
                            // printed `venueSettledLabel`, and the badge three
                            // points above prints the same constant, so event
                            // 15304840 (Townsend v Sabalenka, 16 prop grades,
                            // no scoreline) drew the word TWICE on one card:
                            // the chip and then the hero, stacked. That is the
                            // "two chips making one claim" shape this ship
                            // removes from Finals, reintroduced two lines
                            // down. The web half of the pair had it right in
                            // prose all along — "a settled match with NO
                            // graded score prints the badge alone".
                            //
                            // So: nothing. Not "vs" (it reads as a fixture,
                            // which is the whole defect), not "no score"
                            // (reads as 0-0), not the word again. The badge
                            // carries the state and the crests carry the
                            // matchup; an empty middle is the only thing here
                            // that says nothing false.
                            EmptyView()
                        }
                    } else if let odds = event.currentOdds,
                              let pair = DrawPricedWinner.printablePair(
                                away: odds.awayProbability,
                                home: odds.homeProbability,
                                sport: event.sport) {
                        let home = pair.home
                        let oddsFontSize: CGFloat = sizeClass == .regular ? 36 : 28
                        if let away = pair.away {
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
                        } else {
                            // #5271 — a draw-priced sport. There is one price
                            // here, it is the home side's, and the slot the
                            // other number used to fill is withheld rather
                            // than filled with `1 − home` (see
                            // `DrawPricedWinner`).
                            //
                            // NAMED, because withholding one of a pair breaks
                            // the thing that attributed the other: the two
                            // numbers were read off the crests they sat
                            // between, and a lone number centred between two
                            // crests belongs to neither. The finished branch
                            // above already names its subject this way, and
                            // takes the PAIR to do it (#3430) — "Tigers" is
                            // not a name when both sides shorten to it.
                            //
                            // Rounded here and not through `duelPercents`:
                            // that contract exists to stop a PAIR summing to
                            // 101, and its answer for one side can be
                            // `100 − other`, which is a number about a
                            // complement this branch is refusing to print.
                            let named = TeamShortName.shortPair(
                                away: event.awayTeam, home: event.homeTeam,
                                sportKey: event.sport
                            )
                            VStack(spacing: 2) {
                                Text(named.home)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(colors.home)
                                    .lineLimit(1)
                                Text(formatProbability(home))
                                    .font(.system(size: oddsFontSize, weight: .black, design: .rounded).monospacedDigit())
                                    .foregroundStyle(colors.home)
                            }
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
                        //
                        // #5271 — and that equivalence is what a draw breaks, so
                        // WHO to name is `DrawPricedWinner`'s call, not this
                        // view's: on a three-way market the points home shed are
                        // not points the away side gained, and the caption says
                        // so by naming home and keeping the sign.
                        //
                        // #3051 — and the SUBTRACTION is gone, not corrected.
                        // The delta was computed on the raw probabilities while
                        // the numbers above and below it are the rendered ones,
                        // so `95` over `Opened 91` was captioned `+3`. The
                        // caption now prints the two levels themselves
                        // ("Sabalenka 91% → 95% since open"), which is the same
                        // invariant with nothing left to round twice. Why the
                        // levels and not `pp`: `SinceOpenCaption`.
                        if let caption = SinceOpenCaption.caption(
                            away: odds.awayProbability,
                            home: odds.homeProbability,
                            servedAwayPercent: odds.awayRenderedPercent,
                            servedHomePercent: odds.homeRenderedPercent,
                            openingAway: event.openingOdds?.awayProbability,
                            openingHome: event.openingOdds?.homeProbability,
                            sport: event.sport,
                            // #3430 — #1830's whole fix was naming the team the
                            // move belongs to. A label the other side shares
                            // un-names it again, so take the pair.
                            names: TeamShortName.shortPair(
                                away: event.awayTeam, home: event.homeTeam,
                                sportKey: event.sport
                            )
                        ) {
                            Text(caption.text)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(caption.isHome ? colors.home : colors.away)
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
                        // #3313 — the MATCH primitive at GLYPH size. The bars
                        // beside it grade CONFIDENCE (how many sources, did it
                        // move at all); this grades RECENCY of movement, which
                        // nothing on the hero answered: "+2% since open" is the
                        // whole match, and the full chart is a scroll away.
                        //
                        // Gated on a delivering stream, matching the web's
                        // `streamConnected`. On the poll the hero already carries
                        // a countdown ring, and a ten-minute window refreshed
                        // every thirty seconds is three vertices — under
                        // `minimumPoints`, so it would draw nothing anyway.
                        if isLive, vm.streamDelivering, let history = vm.history {
                            LiveSparklineChart(
                                points: OddsChartView.chartPoints(from: history))
                        }
                    } else {
                        Text("vs")
                            .font(.title2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                    }
                    // Projected final score.
                    //
                    // The unit is NAMED where the scoreboard counts something
                    // else. On the live Pegula–Fernandez US Open match the hero
                    // printed a bare "Proj. 13-13" two lines under a 1–1 SET
                    // score: two numbers that read as a scoreline, in games,
                    // for a match nobody scores in games. Naming the unit is
                    // the smallest honest fix — the projection is real and
                    // useful, it was simply anonymous.
                    //
                    // #3014's SPELLED-OUT LABEL IS RETIRED HERE, not overruled.
                    // It existed for one population — live, and no score — where
                    // "Proj. 2-3" was the only pair on the hero and read as the
                    // score, so the word was spelled out to disambiguate it.
                    // #5697 AC2 withdraws the projection on exactly that
                    // population instead, which is the stronger form of the same
                    // fix: there is no longer a pair there to be misread. That
                    // left `projectionLabel` returning "Proj." for every input it
                    // could still be called with, and three tests pinning a
                    // string the app could no longer draw — a guard that passes
                    // while proving nothing. Deleted rather than left standing.
                    if let phs = event.currentOdds?.projectedHomeScore, let pas = event.currentOdds?.projectedAwayScore,
                       EventDetailView.showsProjection(
                        status: event.status, commenceTime: event.commenceTime?.asDate,
                        hasScore: hasScore) {
                        let vocab = SportVocab.forSport(event.sport)
                        let pair = "\(Int(pas.rounded()))-\(Int(phs.rounded()))"
                        Text("Proj. \(vocab.scoreboardCountsTheUnit ? pair : vocab.withUnit(pair))")
                            .font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                    }
                    // #6544 — THE COUNTDOWN USED TO BE PRINTED HERE TOO, and the
                    // two copies could not disagree: one `formatCountdown`
                    // (`FormattingUtilities.swift`), the same `commenceTime`, so
                    // the hero said "In 4d 12h" in this slot and again in the chip
                    // 250pt above it. The three conditions this arm carried —
                    // a future commence time, not live, not finished — are exactly
                    // the conditions under which `heroStatusBadge` reaches its
                    // `scheduled` arm, so there was never an arrangement where
                    // this copy was the only statement.
                    //
                    // The chip is the one that stays, on #6528's rule: the state
                    // lives in `StatusBadge`, which is what says LIVE / FINAL /
                    // Settled / "In 4d 12h" on cards, search rows and team
                    // schedules alike, and the other slot carries only what the
                    // chip cannot say. Here it carries nothing further — the meta
                    // row already holds the date and the broadcast — so this slot
                    // is simply gone rather than refilled.
                    // Opening odds below probability for live games
                    if isLive,
                       let opened = DrawPricedWinner.printablePair(
                        away: event.openingOdds?.awayProbability,
                        home: event.openingOdds?.homeProbability,
                        sport: event.sport) {
                        // #2085 — the live game's opening line, same pair rule
                        // as the settled branch above, and #5271's withholding
                        // with it.
                        HStack(spacing: 4) {
                            if let awayOpen = opened.away {
                                let openDuel = renderedDuelPercents(
                                    away: awayOpen, home: opened.home
                                )
                                Text("Opened \(formatProbability(awayOpen, renderedPercent: openDuel[0])) \u{2013} \(formatProbability(opened.home, renderedPercent: openDuel[1]))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            } else {
                                let named = TeamShortName.shortPair(
                                    away: event.awayTeam, home: event.homeTeam,
                                    sportKey: event.sport
                                )
                                Text("Opened \(named.home) \(formatProbability(opened.home))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                // THE LINE THAT CAUSED #3978, and it is only wrong in one of the
                // two arrangements. In a row, refusing to compress is right: this
                // column holds "LSU Tigers Win" and a 36pt duel, and letting SwiftUI
                // squeeze it produces `LSU Ti…` beside two logos with room to spare.
                // In a COLUMN it is the whole defect — the centre column's ideal
                // width at `.accessibility3` exceeds the phone, so a fixed size makes
                // the hero wider than its parent, which then centres it and bleeds it
                // off BOTH edges. Stacked, the column has the full width and needs no
                // exemption; `horizontal: false` is a no-op, not a second behaviour.
                .fixedSize(horizontal: !stacked, vertical: false)

                // Home team logo + score
                VStack(spacing: 6) {
                    TeamLogoView(
                        url: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                        teamName: event.homeTeam,
                        color: colors.home,
                        size: logoSize,
                        sportKey: event.sport,
                        opponentName: event.awayTeam
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

    /// The widest the hero's centre verdict may be, in points.
    ///
    /// 🔴 A CAP, NOT A LAYOUT — and it is here because `.frame(maxWidth: .infinity)`
    /// did NOT hold it. Observed on the simulator, 2026-09-15 12:59 PT: with
    /// that modifier and `lineLimit(3)`, "Brighton & Hove Albion wins 5-0"
    /// (event `15310517`) still drew on one line and still pushed the whole hero
    /// card off BOTH screen edges — the away crest clipped at the left, "COV" at
    /// the right, the date cut off. (That intermediate frame was overwritten by
    /// the next shot; the kept pair in `artifacts/native-181/` is the original
    /// **vs** and the bounded result.) The two crest columns are
    /// `.frame(maxWidth: .infinity)` siblings, so the row grants this slot its
    /// ideal width first and an infinite maximum asks for MORE room, never less.
    ///
    /// 150pt is under a third of the 402pt iPhone 17 width with both crests and
    /// their names drawn, and it is a MAXIMUM: every short verdict this slot has
    /// ever held ("Sion Win", "Draw 0-0", "87 – 13") is narrower and centres
    /// inside it unchanged, so nothing that fit before is being re-laid-out.
    static let verdictSlotWidth: CGFloat = 150

    // MARK: - Hero Status Badge

    /// #4002 — the arms are ORDERED, and `suspended` has to come before the
    /// default. The default hands `StatusBadge` the literal `"scheduled"` plus
    /// the event's own `commenceTime`; `formatCountdown` returns nil for a date
    /// in the past, so the badge fell through to `EmptyView` and a match played
    /// four days ago wore no label whatsoever. Silence read as "about to start"
    /// because everything else on the meta row — the date, the broadcast — is
    /// pregame furniture.
    @ViewBuilder
    private func heroStatusBadge(_ event: EventDetail) -> some View {
        if event.status == "live" {
            StatusBadge(status: "live", gameClock: event.espn?.gameClock, period: event.espn?.period)
        } else if EventState.isFinished(event.status) {
            // Passes `commenceTime` it does not strictly need, so that "every
            // non-literal status reaching StatusBadge carries a date" is a rule
            // with no exceptions for its guard to have to encode. See #4021.
            StatusBadge(status: event.status, commenceTime: event.commenceTime)
        } else if EventState.isSuspendedAndStarted(
            event.status, commenceTime: event.commenceTime?.asDate) {
            // #6381 — `venueSettled` is handed to BOTH remaining arms, because
            // both of them are wrong in the same way when the venue has graded
            // the row: this one claims no result was reported, and the one
            // below it shows a kick-off countdown. StatusBadge decides which
            // sentence wins; this view does not duplicate that chain.
            StatusBadge(
                status: "suspended",
                commenceTime: event.commenceTime,
                venueSettled: event.venueSettled == true)
        } else {
            StatusBadge(
                status: "scheduled",
                commenceTime: event.commenceTime,
                venueSettled: event.venueSettled == true)
        }
    }

    // MARK: - ESPN

    @ViewBuilder
    private func espnSection(_ event: EventDetail) -> some View {
        // #4002 — the broadcast chip is gated by the same rule as the hero's, or
        // the "Game Info" card re-offers "MLB.TV, Padres.TV, YES" for a game that
        // finished two days ago one scroll below the hero that stopped doing it.
        let showsBroadcast = event.espn?.broadcast != nil
            && EventDetailView.showsBroadcast(
                status: event.status, commenceTime: event.commenceTime?.asDate)
        let hasData = showsBroadcast || event.commenceTime != nil
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
                    if let broadcast = event.espn?.broadcast, showsBroadcast {
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
                            } else if isSuspended {
                                // #4002 — `isFinished` and `isLive` each had a
                                // tensed arm and `suspended` fell to the one
                                // written for a game that has not happened: on
                                // 15301312 this chip read "Sep 4 at 2:00 AM",
                                // the identical sentence it prints for a fixture
                                // next week. It DID start; the date stays
                                // because the day is the surprising part.
                                Text("Started \(date, format: .dateTime.month(.abbreviated).day()) at \(date, format: .dateTime.hour().minute())")
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



    // MARK: - Sources Toggle (v3)

    /// #3410 — is there ANY probability evidence for this event, from any angle?
    ///
    /// Deliberately generous, and deliberately not a copy of the chart's own
    /// `hasNoReadings`: this decides whether to offer a link to the model
    /// breakdown, so it errs towards offering it. A single named source, a single
    /// bookmaker quote or a single history point is enough. Only a game with none
    /// of the three loses the link — the state photographed on 15305748 and
    /// 15305758, where `win_prob_sources` is `{}` and every history array is empty.
    ///
    /// `history == nil` counts as evidence: that is the not-yet-loaded state, and
    /// a link must not flicker away and back while a page settles.
    static func hasAnyProbabilityEvidence(event: EventDetail, history: EventHistoryResponse?) -> Bool {
        if !(event.winProbabilitySources ?? [:]).isEmpty { return true }
        if !(event.bookmakerOdds ?? []).isEmpty { return true }
        guard let history else { return true }
        if !(history.history ?? []).isEmpty { return true }
        if !(history.espnHistory ?? []).isEmpty { return true }
        if !(history.winProbHistory ?? [:]).isEmpty { return true }
        if !(history.bookmakerHistory ?? [:]).isEmpty { return true }
        return false
    }

    /// The disclosure under the chart: what the blended number is made of.
    ///
    /// It used to say "Individual Sportsbooks" and list only `bookmakerOdds`, so
    /// on an event whose blend also reads Kalshi and Polymarket the app named
    /// neither — and the panel did not render at all for an event with prediction
    /// markets but no book. Alex found it on the upcoming Shelton match, where
    /// the API was serving all three legs fresh (kalshi 0.775 / polymarket 0.775 /
    /// betting 0.7525, measured 19:08Z 2026-09-03) and the page credited ten
    /// sportsbooks and nothing else.
    ///
    /// The blend stays the product — this names its inputs, it does not offer a
    /// competing number to read. Contributing sources come first (that is the
    /// question "where does 78% come from?"), the book-by-book table stays
    /// underneath as the detail it always was.
    @ViewBuilder
    private func sourcesToggle(_ event: EventDetail) -> some View {
        let sourceEntries = WinProbSourceCatalog.entries(from: event.winProbabilitySources)
        // #4284 — the NAMED rows, not the payload. Unnameable keys draw no row, so
        // asking `bookmakerOdds` here would open a disclosure onto an "INDIVIDUAL
        // SPORTSBOOKS" heading with nothing under it. The list the header promises
        // is the list this condition has to be about. #4406 widens the gap between
        // the two: priceless keys draw no row either, so a game every book skipped
        // now correctly draws no heading instead of a heading over eighteen names.
        let bookmakers = Self.namedBookmakerRows(event.bookmakerOdds ?? [])
        if !sourceEntries.isEmpty || !bookmakers.isEmpty {
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
                            Text(sourcesToggleLabel(sourceCount: sourceEntries.count))
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
                    if !sourceEntries.isEmpty {
                        sourceContent(event, entries: sourceEntries)
                    }
                    if !bookmakers.isEmpty {
                        if !sourceEntries.isEmpty { Divider().padding(.horizontal, 16) }
                        Text("Individual sportsbooks")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.tertiary)
                            .textCase(.uppercase)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 16)
                            .padding(.top, 8)
                        bookmakerContent(event)
                    }
                }
            }
            // #4107 — measured HERE, on the panel, rather than behind either
            // list. Both lists draw rows of this width, but they render under
            // independent conditions, so a measurement scoped to one of them is
            // missing on every event that draws only the other. Publishing from
            // the panel also means the width is already known when the reader
            // expands the disclosure, instead of the first frame being sized on
            // unclamped ink.
            .background(
                GeometryReader { geo in
                    Color.clear.preference(
                        key: SourceRowWidthKey.self, value: geo.size.width)
                }
            )
            .onPreferenceChange(SourceRowWidthKey.self) { width in
                sourceRowWidth = width
            }
        }
    }

    /// The collapsed label names the count so the reader can tell there is more
    /// than a book list behind the chevron without opening it.
    private func sourcesToggleLabel(sourceCount: Int) -> String {
        sourceCount > 0 ? "Sources (\(sourceCount))" : "Individual Sportsbooks"
    }

    /// #4233 — one row of either sources list, in whichever shape the model chose.
    ///
    /// Shared by `sourceContent` and `bookmakerContent` because the two lists sit
    /// in one visual table under one disclosure: a reflow that reached only one of
    /// them would put a stacked row directly above an inline one and read as a
    /// rendering fault. #4107 was found the same way — the same defect fixed in
    /// one of these two functions and not the other.
    ///
    /// The label's `lineLimit` reads `maximumLabelLines`, which is the number the
    /// model used to decide this row's shape. Both are load-bearing together with
    /// `.fixedSize` (#3966): `lineLimit` alone still truncates when a parent
    /// proposes one line's height.
    @ViewBuilder
    ///
    /// #4406 — `probabilities` is not optional here either. Both lists that call
    /// this now carry a pair on every row (`WinProbSourceCatalog.Entry` always
    /// did; `NamedBookmakerRow` does since #4406), so the two `if let`s this
    /// function used to hold could only ever draw the state the issue
    /// photographed: a label, and white space where the bar and the numbers go.
    /// #7926 — `ageMark` is the optional second line under the label, and it is
    /// nil on every caller that has no stamp to speak for. The mark goes INSIDE
    /// the label's own fixed-width column rather than beside the numbers: the
    /// column is measured from the label strings (`EventSourceLabelColumn`), so
    /// anything added on the horizontal axis would either overflow a width this
    /// row already computed or force the numbers to re-measure. The row is
    /// already free to grow DOWNWARD — the label wraps to
    /// `maximumLabelLines` under `fixedSize(horizontal: false, vertical: true)` —
    /// so a second short line costs nothing the layout has not already budgeted.
    private func sourceProbabilityRow(
        label: String,
        font: Font,
        probabilities: (away: Double?, home: Double),
        colors: (away: Color, home: Color),
        columns: EventSourceLabelColumn.Columns,
        ageMark: PriceAgeMarkView? = nil
    ) -> some View {
        let labelText = VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(font)
                .lineLimit(EventSourceLabelColumn.maximumLabelLines)
                .fixedSize(horizontal: false, vertical: true)
            ageMark
        }
        .frame(width: columns.label, alignment: .leading)

        Group {
            switch columns.layout {
            case .inline:
                HStack(spacing: EventSourceLabelColumn.interColumnSpacing) {
                    labelText
                    probabilityBarAndNumbers(probabilities, colors: colors, columns: columns)
                }
            case .stacked:
                VStack(
                    alignment: .leading,
                    spacing: EventSourceLabelColumn.stackedLineSpacing
                ) {
                    labelText
                    HStack(spacing: EventSourceLabelColumn.interColumnSpacing) {
                        probabilityBarAndNumbers(
                            probabilities, colors: colors, columns: columns)
                    }
                }
            }
        }
        .padding(.horizontal, EventSourceLabelColumn.horizontalPadding)
        .padding(.vertical, 4)
    }

    /// The bar and the two percentages — the part of the row that stays together
    /// on one line in both layouts.
    ///
    /// Read from the same model that sizes the label, so the two cannot drift:
    /// the whole defect was a layout number that stopped describing its layout.
    @ViewBuilder
    private func probabilityBarAndNumbers(
        _ probabilities: (away: Double?, home: Double),
        colors: (away: Color, home: Color),
        columns: EventSourceLabelColumn.Columns
    ) -> some View {
        // #5271 — a withheld away side still has a BAR, because the bar's two
        // segments are a partition and the remainder is a true quantity: it is
        // "this source does not have the home team winning". What it is not is
        // the away team, so it loses the away team's colour along with its
        // number and reads as the neutral rest of the whole.
        ProbabilityBar(
            awayProb: probabilities.away ?? (1 - probabilities.home),
            homeProb: probabilities.home,
            awayColor: probabilities.away == nil
                ? Color.secondary.opacity(0.25)
                : colors.away,
            homeColor: colors.home,
            height: 6
        )
        .frame(maxWidth: .infinity)

        // #7984 — the two sides of one source are ONE rounding decision. Drawn
        // independently, a venue on the half-percent grid put both on `.5` and
        // half-up rounded both up: Polymarket `0.585` printed `42% 59%` under a
        // Sportsbooks row reading `3% 97%`. The bar above is unaffected — it
        // partitions the true doubles, not the printed integers.
        let printed = duelProbabilityStrings(
            away: probabilities.away, home: probabilities.home)
        Text(printed.away)
            .font(.caption2.monospacedDigit())
            .frame(width: columns.numeric, alignment: .trailing)
        Text(printed.home)
            .font(.caption2.monospacedDigit())
            .frame(width: columns.numeric, alignment: .trailing)
    }

    /// One row per source feeding the blend: label, the same away–home pair the
    /// hero reads, and the same bar the book table uses.
    private func sourceContent(_ event: EventDetail, entries: [WinProbSourceCatalog.Entry]) -> some View {
        let colors = teamColors(event)
        // #4107 — sized against the labels THIS render draws, at THIS view's text
        // size. The old 118pt literal was correct at `.large` and nowhere else:
        // `Sportsbooks (14)` is 99.9pt at default and 142.1pt at xxxLarge, which
        // is where Alex's truncation actually came from. See
        // `EventSourceLabelColumn` for the measurements and for why
        // `.minimumScaleFactor` is gone rather than raised.
        //
        // #4208 — and the two probability columns are sized here too, in the same
        // call, because they are part of the cost the label clamps against. The
        // strings passed are the ones this list will actually print, from BOTH
        // columns: they share one width, so a `>99%` on either side binds both.
        //
        // #5271 — and the strings measured here are the ones the rows PRINT,
        // which on a draw-priced sport is an em-dash where the away percent
        // used to be. Measuring `1 - home` and then printing "—" would size
        // this column against a string no row draws.
        let printable = { (entry: WinProbSourceCatalog.Entry) in
            DrawPricedWinner.printablePair(
                away: 1 - entry.homeProbability,
                home: entry.homeProbability,
                sport: event.sport)
        }
        //
        // #7984 — and the pair is rounded as one decision here too, through the
        // same `duelProbabilityStrings` the rows draw with. Measuring the two
        // sides independently while the row prints them jointly would size this
        // column against a string no row draws, which is the #4208/#5271 trap
        // from the other direction.
        let columns = EventSourceLabelColumn.columns(
            labels: entries.map(\.label),
            values: entries.flatMap { entry -> [String] in
                let printed = duelProbabilityStrings(
                    away: printable(entry)?.away, home: entry.homeProbability)
                return [printed.away, printed.home]
            },
            availableWidth: sourceRowWidth,
            typeSize: dynamicTypeSize)
        return VStack(spacing: 0) {
            ForEach(entries) { entry in
                sourceProbabilityRow(
                    label: entry.label,
                    font: .caption.weight(.medium),
                    probabilities: (
                        away: printable(entry)?.away,
                        home: entry.homeProbability
                    ),
                    colors: colors,
                    columns: columns)
            }
        }
        .padding(.vertical, 8)
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

    /// The away–home pair a bookmaker row draws, or `nil` if the book quoted no
    /// price on this game — in which case, since #4406, there is no row.
    ///
    /// Extracted for #4208 so the width model and the row read the SAME rule. The
    /// column is sized from the strings the list prints, and a row prints numbers
    /// only when it has both sides — if this predicate and the row ever
    /// disagreed, the column would be measured against a set of strings the view
    /// does not draw, which is a width bug that no screenshot would show (the
    /// column would simply be too wide, silently). They can no longer disagree:
    /// this predicate is now what decides the row EXISTS, so every row the model
    /// measures is a row the view draws, and every row the view draws has both.
    private static func bookmakerProbabilities(
        _ bm: BookmakerOdds
    ) -> (away: Double, home: Double)? {
        guard let away = bm.awayProbability ?? bm.awayMoneyline.map({ moneylineToProbability($0) }),
              let home = bm.homeProbability ?? bm.homeMoneyline.map({ moneylineToProbability($0) })
        else { return nil }
        return (away, home)
    }

    /// One row the book table will actually draw: the brand a reader sees, and
    /// the pair it prints.
    ///
    /// #4406 — `probabilities` is NOT optional, and that is the fix rather than a
    /// tidy-up. A row is a name AND a number; a book with no number has no row.
    /// Holding the pair as optional is what let twelve of eighteen rows reach the
    /// screen as bare brands, and no ban-shaped guard can see that state because
    /// it is an OMISSION — nothing wrong is written, a number is simply absent
    /// (#4478's lesson from #2279). Making it non-optional makes the empty row
    /// unrepresentable: the compiler, not a test, is what refuses it now.
    struct NamedBookmakerRow: Identifiable {
        /// The payload key. Stable across refreshes, and never drawn.
        let id: String
        /// The brand, resolved through `SourceLabels`. Never a raw key.
        let label: String
        let probabilities: (away: Double, home: Double)
        /// When this book's price reached us — `bookmaker_odds[].captured_at`,
        /// served on every priced row. Nil only where the payload omits it.
        let capturedAt: String?

        /// #7926 — THE WHOLE AGE DECISION FOR A SPORTSBOOK ROW, in a function a
        /// test can reach rather than an expression inside a `body`. That is the
        /// arrangement `FeedFuturesData.discoverPriceAgeMark` documents one file
        /// over, and it exists for the same reason: the cadence here could
        /// silently become `.futures` — which would hold the mark back for six
        /// hours on a list restamped every two minutes, and hide exactly the rows
        /// it is built to expose — while every assertion about `SourceAge` still
        /// passed.
        ///
        /// `.live` is the bound because these rows ARE the surface
        /// `SourceAge.liveStaleAfter` names in its own comment ("Sportsbook rows
        /// and live blocks, restamped every 2 minutes by
        /// `poll_live_prediction_markets`"), and it is web's `BookmakerTable`
        /// threshold, so the two clients call the same books stale.
        func priceAgeMark(
            now: Date = Date(),
            onReveal: ((String) -> Void)? = nil
        ) -> PriceAgeMarkView? {
            PriceAgeMarkView(
                observedAt: capturedAt,
                cadence: .live,
                now: now,
                onReveal: onReveal)
        }
    }

    /// The book table's rows: named, in payload order, capped.
    ///
    /// #4284 — this list used to draw `bm.bookmaker ?? "Unknown"`, so every event
    /// page in the app printed `betonlineag`, `lowvig` and `betus` at readers
    /// while `SourceLabels` two files away already knew them as BetOnline, LowVig
    /// and BetUS. That is #4135's defect on a fifth surface, and `SourceLabels`
    /// exists precisely because the passthrough — not the key — is the bug.
    ///
    /// 🔴 THE CAP IS APPLIED AFTER THE NAMING, NOT BEFORE. Take ten and then drop
    /// the unnameable and a new key costs a *named* book its slot: the reader
    /// loses a row they could have read, to a row we would not have drawn. Name
    /// first, then take ten, and the table stays full.
    ///
    /// An unnameable key yields no row at all rather than its raw self. That is
    /// the same rule `sportsbookChips(for:)` follows, and the reason the caller
    /// must ask whether this array is empty rather than asking the payload
    /// (`bookmakerOdds` non-empty no longer implies a table).
    ///
    /// #4406 — and a PRICELESS key yields no row either, for the same reason: a
    /// section headed "Individual sportsbooks" whose rows are names with nothing
    /// beside them tells the reader nothing and reads as broken. Measured on
    /// production 2026-09-09, 45 of 180 `bookmaker_odds` rows across 11 games
    /// carried `null` on both sides — 2 of 18 on a live game, 13 of 18 on a
    /// completed one. It is a book that did not quote this game, not a settled-
    /// game artifact, and there is nothing to say about it.
    ///
    /// 🔴 SO THE PRICE FILTER RUNS BEFORE THE CAP, exactly as the naming does,
    /// and for the identical reason spelt out above. Drawn on the specimen in
    /// the issue (15307197, eighteen books in alphabetical payload order): six of
    /// the first ten quoted nothing, so cap-first drew four numbers and left
    /// LowVig, MyBookie and Rebet — three real prices, at positions 14, 15 and 16
    /// — outside the window unseen. Filtering first draws all seven. Both
    /// orderings agree on every payload of ten or fewer, so only a fixture larger
    /// than the cap can tell them apart.
    /// #7926 — AND THE ROW CARRIES ITS OWN AGE, because the reader cannot tell a
    /// live price from a pre-game one by looking at it. Measured on this event
    /// page during the 2026-09-21 NFL game `14780545` at Q3, 145 minutes after
    /// kickoff: of twelve priced books, eight were 2–18 minutes old and read
    /// 92–98%, while `betus`, `betanysports`, `lowvig` and `betonlineag` were
    /// 140–146 minutes old and read 71–73% — the opening line (the event opened
    /// 28% – 72%), never replaced. Two of the four were captured BEFORE kickoff.
    /// They drew in the same weight and the same order as the live ones, and by
    /// Q4 — with the page's own header reading "Rams 100%" — four of the seven
    /// rows still told the reader the Giants were live at 27–29%.
    ///
    /// A STALE ROW IS MARKED, NOT DROPPED, which is what web's `BookmakerTable`
    /// does and is the honest shape: this is a real price that a real book
    /// stopped moving, so it keeps its row and gains its age. Dropping it would
    /// also put this function's cap back in play for the wrong reason — the
    /// naming filter and the price filter above earn their place by never
    /// costing a reader a row they could have read (#4284, #4406), and a
    /// freshness filter would do exactly that.
    ///
    /// The cap is untouched: `capturedAt` is carried, never filtered on, so the
    /// ordering both comments above reason about is the same ordering as before.
    static func namedBookmakerRows(
        _ bookmakers: [BookmakerOdds], limit: Int = 10
    ) -> [NamedBookmakerRow] {
        bookmakers
            .compactMap { bm -> NamedBookmakerRow? in
                guard let key = bm.bookmaker,
                      let label = SourceLabels.sportsbookName(for: key),
                      let probabilities = bookmakerProbabilities(bm)
                else { return nil }
                return NamedBookmakerRow(
                    id: key,
                    label: label,
                    probabilities: probabilities,
                    capturedAt: bm.capturedAt)
            }
            .prefix(limit)
            .map { $0 }
    }

    private func bookmakerContent(_ event: EventDetail) -> some View {
        let colors = teamColors(event)
        let rows = Self.namedBookmakerRows(event.bookmakerOdds ?? [])
        // #4107 — the SAME defect as `sourceContent` above, one function down and
        // in the same visual list: a hardcoded label column that never tracked
        // Dynamic Type. This one was 90pt, which is the exact literal the Sources
        // column was raised FROM. Photographed at xxxLarge on a 375pt phone it cut
        // `betanysportsbook` and `betonlineag` to `betanysp…` / `betonline…` while
        // the two rows above them — already fixed — read in full, which is a worse
        // read than the original bug: it looks deliberate.
        //
        // Sized off the same `sourceRowWidth`, because both lists are children of
        // the same disclosure and therefore the same width. Measured `.regular`,
        // which is the face THIS list draws in.
        //
        // #4208 — as in `sourceContent`. Only rows carrying BOTH prices draw
        // numbers, so the strings measured are the ones that survive that filter;
        // measuring every bookmaker would charge the column for rows it never
        // prints.
        //
        // #4406 moved that filter UPSTREAM into `namedBookmakerRows`, so this
        // list is now every row and every row has a pair — the flatMap no longer
        // needs to skip anything. The claim above is unchanged and now trivially
        // true. The old "a list where no row has both draws no numbers at all"
        // case is gone with it: such a list has no rows, so `sourcesToggle`
        // draws no heading over it.
        //
        // #4284 — and the labels measured are the BRANDS, because the brands are
        // what the rows draw. Sizing on the keys is not conservative, it is just
        // wrong in both directions: `betonlineag` is 2 characters wider than
        // "BetOnline", `betmgm` 2 narrower than "BetMGM". The column and the row
        // read one array now, so they cannot describe different strings.
        //
        // #5271 — a book's away price is SERVED rather than derived here, so the
        // hero's complement is not what is wrong with it. What is wrong is the
        // same thing: on the Braunschweig–Dresden specimen BetMGM printed
        // `53% 47%`, a pair summing to exactly 100 on a match that can be drawn.
        // The book quotes three outcomes; the pair we store and serve is that
        // quote normalised two ways with the draw discarded (#1011), so the 53%
        // beside the away crest is not that team's chance of winning either.
        //
        // Withheld at DISPLAY time and not in `namedBookmakerRows`, so #4406's
        // rule is untouched: a row still needs both prices to exist at all, and
        // still always carries a number, because the home side always survives.
        let printable = { (row: NamedBookmakerRow) in
            DrawPricedWinner.printablePair(
                away: row.probabilities.away,
                home: row.probabilities.home,
                sport: event.sport)
        }
        //
        // #7984 — as in `sourceContent`, and #4233's rule is why it is here at
        // all: these two lists are one visual table, so a pair rule applied to
        // one of them would put a 101 directly beneath a 100. A book's away price
        // is served rather than derived, so most of these pairs are not exact
        // complements and `renderedDuelPercents` leaves them alone; 6 of 557 on
        // production were complements printing 101, and those are the ones this
        // moves.
        let columns = EventSourceLabelColumn.columns(
            labels: rows.map(\.label),
            values: rows.flatMap { row -> [String] in
                let printed = duelProbabilityStrings(
                    away: printable(row)?.away, home: row.probabilities.home)
                return [printed.away, printed.home]
            },
            availableWidth: sourceRowWidth,
            typeSize: dynamicTypeSize,
            weight: .regular)
        return VStack(spacing: 0) {
            ForEach(rows) { row in
                // #7926 — the mark is built ONCE and read twice: it decides both
                // whether the age is drawn and whether the row is dimmed, so the
                // two can never disagree about which books are stale. Asking
                // `SourceAge.isStale` again here would be a second evaluation of
                // the same rule against a second `Date()`.
                let mark = row.priceAgeMark()
                sourceProbabilityRow(
                    label: row.label,
                    font: .caption,
                    probabilities: (
                        away: printable(row)?.away,
                        home: row.probabilities.home
                    ),
                    colors: colors,
                    columns: columns,
                    ageMark: mark)
                    // Web's `BookmakerTable` draws a stale row at `opacity-60`.
                    // The same value, so a book that looks secondary on one
                    // client looks secondary on the other.
                    .opacity(mark == nil ? 1 : 0.6)
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
            // #5271 — nil on a draw-priced sport rather than the complement.
            awayProb: DrawPricedWinner.printablePair(
                away: 1.0 - homeProb, home: homeProb, sport: event.sport)?.away,
            homeScore: lastEspn?.homeScore ?? event.homeScore,
            awayScore: lastEspn?.awayScore ?? event.awayScore,
            period: lastEspn?.period,
            clock: lastEspn?.gameClock
        )
    }

    /// The hero's one reading of who won, server-first (#4915).
    private func heroOutcome(_ event: EventDetail) -> EventOutcome {
        EventOutcome.resolve(
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore,
            servedResult: event.heroSettledResult
        )
    }

    private func winnerColor(isAway: Bool, event: EventDetail) -> Color {
        guard isFinished else { return .primary }
        // #4915 — this was two strict comparisons over `?? 0`, and on a level
        // result NEITHER can be true, so the grey that means "this team lost"
        // was painted on both sides of every draw. Only the loser gets it now.
        return heroOutcome(event).isLoser(isAway: isAway) ? .secondary : .primary
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

    // MARK: - Refresh Status

    private var refreshIndicator: RefreshIndicator {
        Self.refreshIndicator(status: vm.event?.status, streamDelivering: vm.streamDelivering)
    }

    /// #8320 — ONE freshness status for the page, in the toolbar.
    ///
    /// Alex, rage shake #150 on White Sox–Royals: "overcrowded and clowny". The
    /// live page carried the same claim three times — this ring, a second ring
    /// beside the chart title, and a green "Live" dot on the chart — plus the
    /// hero's inning chip. A number counting to the next poll is the page's
    /// plumbing, not something a fan reads, so the count is gone everywhere;
    /// the poll itself (`EventRefreshPlan`) and pull-to-refresh are unchanged.
    ///
    /// The two live arms are drawn so they cannot be mistaken for each other:
    /// the green dot only while the stream is DELIVERING (not merely connected
    /// — see `EventDetailViewModel.streamDelivering`), and otherwise a plain
    /// refresh glyph, which says what the button does and nothing about how
    /// fresh the number is. Neither animates.
    @ViewBuilder
    private var refreshStatus: some View {
        switch refreshIndicator {
        case .hidden:
            EmptyView()
        case .streaming:
            LivePushDot(diameter: 22)
        case .polling:
            Image(systemName: "arrow.clockwise")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 22, height: 22)
                .accessibilityLabel("Refresh")
        }
    }

    /// A refresh status is honest ONLY when the page really refreshes — which
    /// the VM does for live events only. Scheduled/completed pages perform no
    /// periodic reload, so they carry no status at all (C43 P2).
    static func showsRefreshStatus(status: String?) -> Bool { status == "live" }

    /// What the refresh control is entitled to say.
    ///
    /// C43 allowed a countdown only when a request was actually scheduled;
    /// live push (#2687) added the stream state, because a delivering stream
    /// stands the 30-second poll down and a countdown to it froze at 0. #8320
    /// then took the countdown out of the reader's view entirely. What is left
    /// is the distinction that matters to a reader: nothing refreshes (hidden),
    /// the page is being polled (a refresh control, no promise), or updates are
    /// being pushed (say so).
    enum RefreshIndicator: Equatable {
        case hidden
        case polling
        case streaming
    }

    static func refreshIndicator(status: String?, streamDelivering: Bool) -> RefreshIndicator {
        guard showsRefreshStatus(status: status) else { return .hidden }
        return streamDelivering ? .streaming : .polling
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

    /// #3273. The team column is 44pt by the UX-P090 geometry — that width is what
    /// keeps the TOTAL column on screen, so it cannot simply grow. The old fallback
    /// handed it a whole nickname ("Buckeyes"), which SwiftUI then truncated to
    /// `Bu…`; on Alex's Ball State @ Ohio State specimen the served event carries
    /// `home_team_data: null`, so the fallback is what ran. Measured 2026-09-05:
    /// 154 of 1,008 teams across the eight sports this card draws for have no
    /// abbreviation (35% of wncaab), so this path is not an edge case.
    ///
    /// A real abbreviation is always preferred. Failing that, emit three uppercase
    /// letters, which fits the column: an intentional short form reads as an
    /// abbreviation where `Bu…` reads as a rendering fault. Both properties are
    /// `abbreviationPair`'s, so this card keeps them by delegating.
    ///
    /// #3430 — the two rows of this table are the two competitors, stacked, and
    /// the reader tells them apart by these labels alone. Clemson–LSU drew `TIG`
    /// above `TIG`, so the badges come from the pair rule, which widens both
    /// names until they separate before taking three glyphs. The served
    /// abbreviations still win — unless they collide with each other, which
    /// `teams.abbreviation` being wrong for hundreds of rows (#3353) makes real.
    private var badges: (away: String, home: String) {
        let pair = TeamShortName.abbreviationPair(
            away: awayTeam, home: homeTeam,
            awayServed: awayTeamAbbrev, homeServed: homeTeamAbbrev
        )
        return (pair.away.isEmpty ? "Away" : pair.away,
                pair.home.isEmpty ? "Home" : pair.home)
    }

    private var homeShort: String { badges.home }

    private var awayShort: String { badges.away }

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
                            // #3977 — the spacer above the team badges. It carries
                            // the same floor as the badge and declares the column
                            // leading-aligned, so two badges of unequal ink still
                            // start their dots at the same x.
                            Text("")
                                .frame(
                                    minWidth: GameSegmentTeamBadge.minimumWidthPoints,
                                    alignment: .leading)
                                .gridColumnAlignment(.leading)
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
            // UX-P090: 54 -> 44, matching the header row above. See the geometry
            // note there — the two must move together or the columns shear.
            // #3977 moved both to a FLOOR and put the badge in its own type so a
            // camera can measure it; the reasoning lives on `GameSegmentTeamBadge`.
            GameSegmentTeamBadge(team: team, color: color)

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

                let label = Self.formatPeriodLabel(rawPeriod)
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

    /// #3273. The card used to run its OWN period parser, and that parser read
    /// the GAME CLOCK: ESPN writes the clock as a PREFIX (`"14:54 - 1st Quarter"`),
    /// so taking the first number in the string headed a football card
    /// `Q14 · Q8 · Q5 · Q1 ... Q4` — thirteen columns on a four-quarter game, of
    /// which one was right by accident (`"End of 1st Quarter"` carries no clock).
    ///
    /// The parser it should have been calling already existed. #1832 deleted the
    /// duplicate period-label implementations and left `PeriodLabel.normalize` as
    /// the single source — but its ratchet
    /// (`frontend/__tests__/ios/periodLabelSingleSource.test.ts`) enumerated its
    /// consumers by NAME, and this file was never in the list, so a third copy
    /// grew here unwatched and drifted. That guard now DISCOVERS consumers instead
    /// of listing them.
    ///
    /// What is left here is the one thing genuinely local to this card: its column
    /// vocabulary. The 22pt column is sized for digits (UX-P090), so an inning is
    /// `9`, not the chart's self-explaining `9th`; and a status that is not a
    /// period at all gets no column. Anything the shared parser cannot name is
    /// dropped rather than guessed.
    ///
    /// Measured against every distinct period string in production (10,665
    /// sport/period pairs, 2026-09-05): 10,159 change, and the resulting label
    /// vocabulary is closed — football `Q1`-`Q4`; basketball `Q1`-`Q4`, `1H`,
    /// `2H`, `OT`-`4OT`; baseball `1`-`13`. No clock reading can reach a header.
    /// Note this needs no sport key: `ncaab` plays halves and `wncaab` plays
    /// quarters under the same `basketball_` prefix, so reading the noun out of
    /// the data is the only thing that can label both correctly.
    private static func formatPeriodLabel(_ rawPeriod: String) -> String {
        PeriodLabel.columnLabel(rawPeriod)
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
