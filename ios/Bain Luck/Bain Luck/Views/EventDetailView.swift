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
                            OddsChartView(eventId: event.id, teamColors: teamColors(event),
                                         commenceTime: event.commenceTime, status: event.status,
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
                        if let ei = event.ei ?? event.pulse { eiSection(ei) }
                        LineMovementView(eventId: event.id,
                                         homeTeam: event.homeTeam,
                                         awayTeam: event.awayTeam,
                                         eventStatus: event.status,
                                         preloadedData: vm.lineMovement)
                        if let context = event.standingsContext { standingsSection(context) }
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
            } else {
                // Live / Scheduled: show current odds prominently
                if let odds = event.currentOdds,
                   let away = odds.awayProbability,
                   let home = odds.homeProbability {
                    HStack {
                        Text(formatProbability(away))
                            .font(.title3).fontWeight(.bold).monospacedDigit()
                            .foregroundStyle(colors.away)
                        Spacer()
                        Text(isLive ? "Live Win Probability" : "Win Probability")
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
            ?? lastHist?.homeProbability.map { $0 / 100.0 }
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
