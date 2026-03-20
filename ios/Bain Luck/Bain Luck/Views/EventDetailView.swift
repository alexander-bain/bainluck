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
        Group {
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
                            chartHeaderBar(event)
                            OddsChartView(eventId: event.id, teamColors: teamColors(event),
                                         commenceTime: event.commenceTime, status: event.status,
                                         homeTeamName: event.homeTeam.name,
                                         awayTeamName: event.awayTeam.name,
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
                        }
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        if let ei = event.ei ?? event.pulse { eiSection(ei) }
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
                        bookmakerSection(event)
                    }
                    .padding(.horizontal)
                    .padding(.bottom)
                    .frame(maxWidth: contentMaxWidth)
                    .frame(maxWidth: .infinity)
                }
            }
        }
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

    // MARK: - Team Colors

    private func teamColors(_ event: EventDetail) -> (away: Color, home: Color) {
        let away = Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280")
        let home = Color(hex: event.homeTeamData?.primaryColor ?? "#6b7280")
        return (away, home)
    }

    // MARK: - Chart Header Bar

    private func chartHeaderBar(_ event: EventDetail) -> some View {
        let colors = teamColors(event)
        let hasScore = (isLive || isFinished) && event.homeScore != nil && event.awayScore != nil
        let homeShort = event.homeTeam.split(separator: " ").last.map(String.init) ?? event.homeTeam
        let awayShort = event.awayTeam.split(separator: " ").last.map(String.init) ?? event.awayTeam
        let homeCity = event.homeTeam.split(separator: " ").dropLast().joined(separator: " ")
        let awayCity = event.awayTeam.split(separator: " ").dropLast().joined(separator: " ")

        return HStack {
            HStack(spacing: 16) {
                // Away team
                HStack(spacing: 8) {
                    TeamLogoView(
                        url: event.awayTeamData?.logoSmall,
                        teamName: event.awayTeam,
                        color: colors.away,
                        size: 28
                    )
                    VStack(alignment: .leading, spacing: 0) {
                        Text(awayCity.isEmpty ? awayShort : awayCity)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if hasScore {
                            Text("\(event.awayScore ?? 0)")
                                .font(.title3)
                                .fontWeight(.bold)
                                .monospacedDigit()
                        } else {
                            Text(awayShort)
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                    }
                }

                // Status
                if isLive {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(Color.green)
                            .frame(width: 5, height: 5)
                        Text("LIVE")
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .foregroundStyle(.green)
                    }
                } else if isFinished {
                    Text("FINAL")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                } else {
                    Text(formatChartTime(event.commenceTime ?? ""))
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                }

                // Home team
                HStack(spacing: 8) {
                    VStack(alignment: .trailing, spacing: 0) {
                        Text(homeCity.isEmpty ? homeShort : homeCity)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if hasScore {
                            Text("\(event.homeScore ?? 0)")
                                .font(.title3)
                                .fontWeight(.bold)
                                .monospacedDigit()
                        } else {
                            Text(homeShort)
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                    }
                    TeamLogoView(
                        url: event.homeTeamData?.logoSmall,
                        teamName: event.homeTeam,
                        color: colors.home,
                        size: 28
                    )
                }
            }

            Spacer()

            // Date + broadcast
            VStack(alignment: .trailing, spacing: 2) {
                Text(formatChartDate(event.commenceTime ?? ""))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let broadcast = event.espn?.broadcast {
                    Text(broadcast)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private func formatChartTime(_ dateString: String) -> String {
        guard let date = dateString.asDate else { return "" }
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: date)
    }

    private func formatChartDate(_ dateString: String) -> String {
        guard let date = dateString.asDate else { return "" }
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter.string(from: date)
    }

    // MARK: - Hero Section

    private func heroSection(_ event: EventDetail) -> some View {
        let colors = teamColors(event)

        return VStack(spacing: 12) {
            // Top row: sport + status + EI
            HStack {
                if let sport = event.sport {
                    Text(sportDisplayName(for: sport))
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.white.opacity(0.7))
                }
                Spacer()
                heroStatusBadge(event)
                Spacer()
                if let ei = event.ei ?? event.pulse {
                    EIBadgeView(ei: ei, size: .md)
                }
            }

            // Teams + score
            HStack(spacing: 0) {
                // Away team
                VStack(spacing: 6) {
                    TeamLogoView(
                        url: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                        teamName: event.awayTeam,
                        color: colors.away,
                        size: logoSize
                    )
                    Text(event.awayTeam)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.white)
                    if let record = event.awayTeamData?.record {
                        Text(record).font(.caption2).foregroundStyle(.white.opacity(0.5))
                    }
                }
                .frame(maxWidth: .infinity)

                // Score / vs
                VStack(spacing: 4) {
                    if isLive || isFinished {
                        HStack(spacing: 12) {
                            Text("\(event.awayScore ?? 0)")
                                .font(.system(size: scoreFontSize, weight: .bold, design: .rounded).monospacedDigit())
                                .foregroundStyle(winnerColor(isAway: true, event: event))
                            Text("-")
                                .font(.title2)
                                .foregroundStyle(.white.opacity(0.4))
                            Text("\(event.homeScore ?? 0)")
                                .font(.system(size: scoreFontSize, weight: .bold, design: .rounded).monospacedDigit())
                                .foregroundStyle(winnerColor(isAway: false, event: event))
                        }
                        if let clock = event.espn?.gameClock, isLive {
                            Text(clock).font(.caption2).foregroundStyle(.white.opacity(0.5))
                        }
                        if let period = event.espn?.period, isLive {
                            Text(period).font(.caption2).foregroundStyle(.white.opacity(0.5))
                        }
                    } else {
                        Text("vs")
                            .font(.title2)
                            .fontWeight(.medium)
                            .foregroundStyle(.white.opacity(0.4))
                        if let ct = countdownText {
                            Text("In \(ct)")
                                .font(.caption)
                                .fontWeight(.medium)
                                .foregroundStyle(.blue)
                        }
                    }
                }
                .fixedSize(horizontal: true, vertical: false)

                // Home team
                VStack(spacing: 6) {
                    TeamLogoView(
                        url: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                        teamName: event.homeTeam,
                        color: colors.home,
                        size: logoSize
                    )
                    Text(event.homeTeam)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.white)
                    if let record = event.homeTeamData?.record {
                        Text(record).font(.caption2).foregroundStyle(.white.opacity(0.5))
                    }
                }
                .frame(maxWidth: .infinity)
            }

            // Probability section
            heroProbability(event, colors: colors)

            // Game context strip (broadcast, time, venue)
            heroContextStrip(event)

            // Data freshness strip
            freshnessStrip(event)
        }
        .padding()
        .background(
            LinearGradient(
                colors: [
                    colors.away.opacity(0.15),
                    Color.heroDarkBackground,
                    colors.home.opacity(0.15),
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

    // MARK: - Hero Probability

    /// For live games, cross-check current_odds against the latest valid history point.
    /// If they diverge >5%, trust the history data (catches stale bookmaker issues).
    /// Mirrors the web frontend logic in events/[id]/page.tsx.
    private func resolvedLiveProbability(_ event: EventDetail) -> (away: Double, home: Double, label: String)? {
        var awayProb = event.currentOdds?.awayProbability
        var homeProb = event.currentOdds?.homeProbability
        var label = "Live Win Probability"

        if let historyPoints = vm.history?.history,
           let latestValid = historyPoints.last(where: { $0.homeProbability != nil }) {
            let historyHome = latestValid.homeProbability!
            // If current odds are missing OR diverge >5% from history, trust history
            if homeProb == nil || abs(historyHome - (homeProb ?? 0)) > 0.05 {
                homeProb = historyHome
                awayProb = latestValid.awayProbability ?? (1.0 - historyHome)
                if let count = latestValid.bookmakerCount, count > 0 {
                    label = "Live · \(count) sportsbook\(count != 1 ? "s" : "")"
                }
            }
        }

        guard let away = awayProb, let home = homeProb else { return nil }
        return (away, home, label)
    }

    private func heroProbability(_ event: EventDetail, colors: (away: Color, home: Color)) -> some View {
        VStack(spacing: 6) {
            if isFinished {
                // Completed: show pre-game odds prominently (fallback to current if no opening)
                let awayProb = event.openingOdds?.awayProbability ?? event.currentOdds?.awayProbability
                let homeProb = event.openingOdds?.homeProbability ?? event.currentOdds?.homeProbability
                let label = event.openingOdds?.homeProbability != nil ? "Pre-game Odds" : "Win Probability"

                if let awayProb, let homeProb {
                    HStack {
                        Text(formatProbability(awayProb))
                            .font(.title3).fontWeight(.bold).monospacedDigit()
                            .foregroundStyle(colors.away)
                        Spacer()
                        Text(label)
                            .font(.caption2).fontWeight(.medium)
                            .foregroundStyle(.white.opacity(0.5))
                        Spacer()
                        Text(formatProbability(homeProb))
                            .font(.title3).fontWeight(.bold).monospacedDigit()
                            .foregroundStyle(colors.home)
                    }
                    ProbabilityBar(
                        awayProb: awayProb, homeProb: homeProb,
                        awayColor: colors.away.opacity(0.7),
                        homeColor: colors.home.opacity(0.7),
                        height: 12
                    )
                }
            } else if isLive, let resolved = resolvedLiveProbability(event) {
                // Live: show cross-checked odds (history-verified to catch stale bookmaker data)
                HStack {
                    Text(formatProbability(resolved.away))
                        .font(.title3).fontWeight(.bold).monospacedDigit()
                        .foregroundStyle(colors.away)
                    Spacer()
                    Text(resolved.label)
                        .font(.caption2).fontWeight(.medium)
                        .foregroundStyle(.white.opacity(0.5))
                    Spacer()
                    Text(formatProbability(resolved.home))
                        .font(.title3).fontWeight(.bold).monospacedDigit()
                        .foregroundStyle(colors.home)
                }
                ProbabilityBar(
                    awayProb: resolved.away, homeProb: resolved.home,
                    awayColor: colors.away, homeColor: colors.home,
                    height: 14, animated: true, glowing: true
                )

                // Show opening odds as secondary reference
                if let opening = event.openingOdds,
                   let awayOpen = opening.awayProbability,
                   let homeOpen = opening.homeProbability {
                    HStack {
                        Text(formatProbability(awayOpen))
                            .font(.caption2).foregroundStyle(.white.opacity(0.5))
                        Spacer()
                        Text("Opened")
                            .font(.caption2).foregroundStyle(.white.opacity(0.35))
                        Spacer()
                        Text(formatProbability(homeOpen))
                            .font(.caption2).foregroundStyle(.white.opacity(0.5))
                    }
                }
            } else {
                // Scheduled (or live before history loads): show current odds
                if let odds = event.currentOdds,
                   let away = odds.awayProbability,
                   let home = odds.homeProbability {
                    HStack {
                        Text(formatProbability(away))
                            .font(.title3).fontWeight(.bold).monospacedDigit()
                            .foregroundStyle(colors.away)
                        Spacer()
                        Text("Win Probability")
                            .font(.caption2).fontWeight(.medium)
                            .foregroundStyle(.white.opacity(0.5))
                        Spacer()
                        Text(formatProbability(home))
                            .font(.title3).fontWeight(.bold).monospacedDigit()
                            .foregroundStyle(colors.home)
                    }
                    ProbabilityBar(
                        awayProb: away, homeProb: home,
                        awayColor: colors.away, homeColor: colors.home,
                        height: 14, animated: true, glowing: isLive
                    )
                }

                // Show opening odds as secondary reference for live games
                if isLive,
                   let opening = event.openingOdds,
                   let awayOpen = opening.awayProbability,
                   let homeOpen = opening.homeProbability {
                    HStack {
                        Text(formatProbability(awayOpen))
                            .font(.caption2).foregroundStyle(.white.opacity(0.5))
                        Spacer()
                        Text("Opened")
                            .font(.caption2).foregroundStyle(.white.opacity(0.35))
                        Spacer()
                        Text(formatProbability(homeOpen))
                            .font(.caption2).foregroundStyle(.white.opacity(0.5))
                    }
                }
            }
        }
    }

    // MARK: - Hero Context Strip

    @ViewBuilder
    private func heroContextStrip(_ event: EventDetail) -> some View {
        let hasInfo = event.espn?.broadcast != nil || event.commenceTime != nil
        if hasInfo {
            HStack(spacing: 8) {
                if let broadcast = event.espn?.broadcast {
                    HStack(spacing: 4) {
                        Image(systemName: "tv")
                            .font(.system(size: 9))
                        Text(broadcast)
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    .foregroundStyle(.white.opacity(0.7))
                }
                if let ct = event.commenceTime, let date = ct.asDate {
                    let isLive = event.status == "live"
                    let isCompleted = event.status == "completed" || event.status == "closed"
                    HStack(spacing: 4) {
                        Image(systemName: isCompleted ? "calendar" : "clock")
                            .font(.system(size: 9))
                        if isLive {
                            // Live: show game clock from ESPN if available
                            if let clock = event.espn?.gameClock {
                                Text(clock)
                                    .font(.caption2)
                            }
                        } else if isCompleted {
                            // Completed: show date
                            Text(date, format: .dateTime.weekday(.abbreviated).month(.abbreviated).day())
                                .font(.caption2)
                        } else {
                            // Scheduled: show day + time
                            Text(date, format: .dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute())
                                .font(.caption2)
                        }
                    }
                    .foregroundStyle(.white.opacity(0.6))
                }
            }
        }
    }

    // MARK: - Data Freshness Strip

    private func freshnessStrip(_ event: EventDetail) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                if let captured = event.currentOdds?.capturedAt,
                   let date = captured.asDate {
                    let elapsed = Int(-date.timeIntervalSinceNow)
                    let text = elapsed < 60 ? "Just now" : elapsed < 3600 ? "\(elapsed / 60)m ago" : "\(elapsed / 3600)h ago"
                    freshnessChip(icon: "clock", text: text)
                }
                divergenceBadge(event)
            }
        }
    }

    private func freshnessChip(icon: String, text: String) -> some View {
        HStack(spacing: 3) {
            Image(systemName: icon)
                .font(.system(size: 9))
            Text(text)
                .font(.caption2)
        }
        .foregroundStyle(.white.opacity(0.6))
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(.white.opacity(0.08))
        .clipShape(Capsule())
    }

    // MARK: - Divergence Badge

    @ViewBuilder
    private func divergenceBadge(_ event: EventDetail) -> some View {
        if let sources = event.winProbabilitySources,
           let consensus = event.currentOdds?.homeProbability {
            let marketSources = sources.filter { $0.key == "kalshi" || $0.key == "polymarket" }
            if let (_, source) = marketSources.first, let marketProb = source.value {
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

    // MARK: - EI Section

    private func eiSection(_ ei: EIData) -> some View {
        VStack(spacing: 8) {
            EIBadgeView(ei: ei, size: .lg)
            if let meta = ei.metadata {
                HStack(spacing: 16) {
                    metadataItem(title: "Raw EI", value: meta.rawEi.map { String(format: "%.2f", $0) } ?? "-")
                    metadataItem(title: "Lead Changes", value: meta.leadChanges.map { "\($0)" } ?? "-")
                    metadataItem(title: "Comeback", value: meta.comebackFactor.map { formatProbability($0) } ?? "-")
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
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

    // MARK: - Bookmakers (Probabilities)

    @ViewBuilder
    private func bookmakerSection(_ event: EventDetail) -> some View {
        if let bookmakers = event.bookmakerOdds, !bookmakers.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Image(systemName: "book.closed")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    Text("Sportsbook Odds")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Spacer()
                    Text("\(min(bookmakers.count, 10))")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }

                let colors = teamColors(event)
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
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
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
        guard isFinished else { return .white }
        let away = event.awayScore ?? 0
        let home = event.homeScore ?? 0
        if isAway {
            return away > home ? .white : .white.opacity(0.4)
        } else {
            return home > away ? .white : .white.opacity(0.4)
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
