import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "eventDetail")

// MARK: - ViewModel

final class EventDetailViewModel: ObservableObject {
    @Published var event: EventDetail?
    @Published var loading = true
    @Published var error: String?
    @Published var history: EventHistoryResponse?
    @Published var lineMovement: LineMovementResponse?
    @Published var relatedFutures: RelatedFuturesResponse?

    private var refreshTimer: Timer?
    let eventId: Int

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
        loading = event == nil

        // Start secondary fetches immediately (they only need eventId)
        let historyTask = Task { try? await APIClient.shared.fetchEventHistory(id: eventId, hours: 168) }
        let lineMovementTask = Task { try? await APIClient.shared.fetchLineMovement(eventId: eventId) }
        let relatedFuturesTask = Task { try? await APIClient.shared.fetchRelatedFutures(eventId: eventId) }

        // Await primary fetch (controls loading state)
        do {
            event = try await APIClient.shared.fetchEvent(id: eventId)
            error = nil
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load event \(self.eventId): \(error)")
        }

        // Unblock the page — render with whatever secondary data is already available
        loading = false
        configureAutoRefresh()

        // Await secondary fetches (already running in parallel, may already be done)
        // These update @Published properties so child views re-render as data arrives
        history = await historyTask.value
        lineMovement = await lineMovementTask.value
        relatedFutures = await relatedFuturesTask.value
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard event?.status == "live" else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}

// MARK: - View

struct EventDetailView: View {
    let eventId: Int
    @StateObject private var vm: EventDetailViewModel
    @State private var countdownText: String?
    @State private var countdownTimer: Timer?
    @State private var selectedPlayPoint: GamePlayPoint?
    @State private var showSources = false
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
    private var contentMaxWidth: CGFloat { isIPad ? 900 : 700 }

    var body: some View {
        contentView
            .navigationTitle("Game Details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    PinButton(type: "event", id: eventId)
                }
            }
            .task {
                await vm.load()
                AnalyticsService.trackEventDetailView(eventId: eventId, sport: vm.event?.sport)
                startCountdownTimer()
            }
            .refreshable {
                await vm.load()
            }
            .onDisappear {
                vm.stopRefresh()
                countdownTimer?.invalidate()
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
                VStack(spacing: 16) {
                    heroSection(event)
                    VStack(spacing: 0) {
                        OddsChartView(eventId: event.id, teamColors: teamColors(event),
                                     commenceTime: event.commenceTime, status: event.status,
                                     homeTeamName: event.homeTeam,
                                     awayTeamName: event.awayTeam,
                                     homeTeamLogo: event.homeTeamData?.logoSmall,
                                     awayTeamLogo: event.awayTeamData?.logoSmall,
                                     homeTeamAbbrev: event.homeTeamData?.abbreviation,
                                     awayTeamAbbrev: event.awayTeamData?.abbreviation,
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
                        // Sources toggle (bookmaker odds inside chart card)
                        sourcesToggle(event)
                    }
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    // Score Differential Chart
                    if let history = vm.history, (isLive || isFinished) {
                        ScoreDifferentialChartView(
                            history: history,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            commenceTime: event.commenceTime,
                            eventStatus: event.status,
                            homeTeamColor: teamColors(event).home,
                            awayTeamColor: teamColors(event).away
                        )
                    }
                    LineMovementView(eventId: event.id,
                                     homeTeam: event.homeTeam,
                                     awayTeam: event.awayTeam,
                                     eventStatus: event.status,
                                     preloadedData: vm.lineMovement)
                    if let context = event.standingsContext { standingsSection(context) }
                    eventTagsSection(event)
                    RelatedFuturesView(
                        eventId: event.id,
                        awayTeamColor: teamColors(event).away,
                        homeTeamColor: teamColors(event).home,
                        awayTeam: event.awayTeam,
                        homeTeam: event.homeTeam,
                        sportKey: event.sport,
                        preloadedData: vm.relatedFutures
                    )
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
            // Top meta row: status badge + broadcast + date
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
                if let ct = event.commenceTime, let date = ct.asDate {
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
                        Text(record).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity)

                // Giant probabilities centered
                VStack(spacing: 4) {
                    if isFinished {
                        let awayProb = event.openingOdds?.awayProbability ?? event.currentOdds?.awayProbability
                        let homeProb = event.openingOdds?.homeProbability ?? event.currentOdds?.homeProbability
                        if let ap = awayProb, let hp = homeProb {
                            HStack(spacing: 8) {
                                Text(formatProbability(ap))
                                    .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
                                    .foregroundStyle(colors.away)
                                Text("\u{2013}")
                                    .font(.title3)
                                    .foregroundStyle(.secondary.opacity(0.4))
                                Text(formatProbability(hp))
                                    .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
                                    .foregroundStyle(colors.home)
                            }
                            Text("Pre-game Odds")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    } else if let odds = event.currentOdds,
                              let away = odds.awayProbability,
                              let home = odds.homeProbability {
                        HStack(spacing: 8) {
                            Text(formatProbability(away))
                                .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
                                .foregroundStyle(colors.away)
                            Text("\u{2013}")
                                .font(.title3)
                                .foregroundStyle(.secondary.opacity(0.4))
                            Text(formatProbability(home))
                                .font(.system(size: 36, weight: .black, design: .rounded).monospacedDigit())
                                .foregroundStyle(colors.home)
                        }
                        Text("Win Probability")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("vs")
                            .font(.title2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                    }
                    if let ct = countdownText, !isLive, !isFinished {
                        Text("In \(ct)")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundStyle(.blue)
                    }
                    // Opening odds below probability for live games
                    if isLive,
                       let opening = event.openingOdds,
                       let awayOpen = opening.awayProbability,
                       let homeOpen = opening.homeProbability {
                        HStack(spacing: 4) {
                            Text("Opened \(formatProbability(awayOpen)) \u{2013} \(formatProbability(homeOpen))")
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
                        Text(record).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity)
            }

            // EI strip (compact, inline)
            if let ei = event.ei ?? event.pulse {
                EIBadgeView(ei: ei, size: .sm)
            }

            // Divergence badge
            divergenceBadge(event)
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
            StatusBadge(status: "live")
        case "completed", "closed":
            StatusBadge(status: event.status)
        default:
            StatusBadge(status: "scheduled", commenceTime: event.commenceTime)
        }
    }

    // MARK: - Divergence Badge

    @ViewBuilder
    private func divergenceBadge(_ event: EventDetail) -> some View {
        if let sources = event.winProbabilitySources,
           let consensus = event.currentOdds?.homeProbability {
            let marketSources = sources.filter { $0.key == "kalshi" || $0.key == "polymarket" }
            if let (_, source) = marketSources.first, let marketProb = source.value?.doubleValue {
                let gap = abs(marketProb - consensus)
                if gap > 0.05 {
                    let isPurple = gap > 0.10
                    HStack(spacing: 3) {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .font(.system(size: 9))
                        Text("\(Int((gap * 100).rounded()))% divergence")
                            .font(.caption2)
                    }
                    .foregroundStyle(isPurple ? .purple : .blue)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background((isPurple ? Color.purple : Color.blue).opacity(0.15))
                    .clipShape(Capsule())
                }
            }
        }
    }


    // MARK: - Standings

    private func standingsSection(_ context: StandingsContext) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "list.number")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                Text("Standings Context")
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }
            if let away = context.away {
                HStack(spacing: 8) {
                    Circle()
                        .fill(Color(hex: vm.event?.awayTeamData?.primaryColor ?? "#6b7280"))
                        .frame(width: 6, height: 6)
                    Text(away)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if let home = context.home {
                HStack(spacing: 8) {
                    Circle()
                        .fill(Color(hex: vm.event?.homeTeamData?.primaryColor ?? "#6b7280"))
                        .frame(width: 6, height: 6)
                    Text(home)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Event Tags

    @ViewBuilder
    private func eventTagsSection(_ event: EventDetail) -> some View {
        let displayTags = (event.eventTags ?? []).filter { tag in
            let ns = tag.components(separatedBy: ":").first ?? ""
            let allowed: Set<String> = ["importance", "signal", "timing", "tier", "ei",
                                         "stakes", "narrative", "audience", "competitive_structure"]
            guard allowed.contains(ns) else { return false }
            let hidden: Set<String> = ["competitive_structure:head_to_head",
                                        "audience:local_interest", "stakes:meaningless"]
            return !hidden.contains(tag)
        }
        if !displayTags.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "tag")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    Text("Tags")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                }
                FlowLayout(spacing: 6) {
                    ForEach(displayTags, id: \.self) { tag in
                        Text(Self.tagLabel(tag))
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(Self.tagForeground(tag))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Self.tagBackground(tag))
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

    private static func tagLabel(_ tag: String) -> String {
        let labels: [String: String] = [
            "importance:championship": "Championship",
            "importance:playoff": "Playoff",
            "importance:exhibition": "Exhibition",
            "signal:upset": "Upset Alert",
            "signal:favorite_switched": "Favorite Switched",
            "signal:very_close": "Very Close",
            "signal:close_matchup": "Close Matchup",
            "signal:major_prob_swing": "Major Odds Swing",
            "timing:starting_very_soon": "Starting Very Soon",
            "timing:starting_soon": "Starting Soon",
            "stakes:elimination": "Elimination",
            "stakes:clinch": "Clinch Scenario",
            "stakes:playoff_race": "Playoff Race",
            "stakes:relegation": "Relegation",
            "stakes:promotion": "Promotion",
            "stakes:seeding": "Seeding",
            "stakes:title_defense": "Title Defense",
            "stakes:must_win": "Must Win",
            "stakes:record_chase": "Record Chase",
            "stakes:streak": "Streak",
            "narrative:rivalry": "Rivalry",
            "narrative:historic_rivalry": "Historic Rivalry",
            "narrative:revenge_game": "Revenge Game",
            "narrative:cinderella": "Cinderella Story",
            "narrative:upset_alert": "Upset Alert",
            "narrative:comeback": "Comeback",
            "narrative:legacy_moment": "Legacy Moment",
            "narrative:debut": "Debut",
            "narrative:return_from_injury": "Return from Injury",
            "narrative:farewell_tour": "Farewell Tour",
            "narrative:rematch": "Rematch",
            "narrative:david_vs_goliath": "David vs. Goliath",
            "narrative:redemption": "Redemption",
            "narrative:winning_streak": "Winning Streak",
            "narrative:losing_streak": "Losing Streak",
            "audience:national_interest": "National Interest",
            "audience:casual_friendly": "Casual Friendly",
            "audience:crossover_appeal": "Crossover Appeal",
            "audience:viral_potential": "Viral Potential",
            "audience:hardcore_only": "Hardcore Only",
            "competitive_structure:series": "Series",
            "competitive_structure:best_of_7": "Best of 7",
            "competitive_structure:bracket": "Bracket",
            "competitive_structure:knockout": "Knockout",
            "competitive_structure:group_stage": "Group Stage",
            "competitive_structure:single_elimination": "Single Elimination",
            "competitive_structure:round_robin": "Round Robin",
            "competitive_structure:field": "Field",
        ]
        if let label = labels[tag] { return label }
        // Fallback: strip namespace, capitalize, replace underscores
        let value = tag.components(separatedBy: ":").last ?? tag
        return value.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func tagForeground(_ tag: String) -> Color {
        let ns = tag.components(separatedBy: ":").first ?? ""
        switch ns {
        case "importance": return Color(hex: "#f59e0b")
        case "signal": return Color(hex: "#22c55e")
        case "timing": return Color(hex: "#3b82f6")
        case "stakes": return Color(hex: "#ef4444")
        case "narrative": return Color(hex: "#f59e0b")
        case "audience": return Color(hex: "#06b6d4")
        case "competitive_structure": return Color(hex: "#818cf8")
        default: return .secondary
        }
    }

    private static func tagBackground(_ tag: String) -> Color {
        tagForeground(tag).opacity(0.15)
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
                    if let ct = event.commenceTime {
                        HStack(spacing: 5) {
                            Image(systemName: "clock")
                                .font(.system(size: 10))
                            RelativeTimeText(dateString: ct)
                        }
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
                        // Legend items
                        HStack(spacing: 12) {
                            legendItem(color: Color(hex: event.homeTeamData?.primaryColor ?? "#10B981"), label: "BainLuck")
                            legendItem(color: .secondary.opacity(0.4), label: "Sportsbooks")
                        }
                        Spacer()
                        HStack(spacing: 4) {
                            Text("Sources")
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

                    if let ap = awayProb, let hp = homeProb {
                        ProbabilityBar(
                            awayProb: ap, homeProb: hp,
                            awayColor: colors.away,
                            homeColor: colors.home,
                            height: 6
                        )
                        .frame(maxWidth: .infinity)

                        Text(formatProbability(ap))
                            .font(.caption2.monospacedDigit())
                            .frame(width: 36, alignment: .trailing)
                        Text(formatProbability(hp))
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
        guard let ct = vm.event?.commenceTime,
              let date = ct.asDate else {
            countdownText = nil
            return
        }
        countdownText = formatCountdown(from: date)
    }
}
