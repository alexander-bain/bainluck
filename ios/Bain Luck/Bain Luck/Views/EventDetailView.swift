import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "eventDetail")

// MARK: - ViewModel

final class EventDetailViewModel: ObservableObject {
    @Published var event: EventDetail?
    @Published var loading = true
    @Published var error: String?

    private var refreshTimer: Timer?
    let eventId: Int

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
        loading = event == nil
        do {
            event = try await APIClient.shared.fetchEvent(id: eventId)
            error = nil
            loading = false
            configureAutoRefresh()
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load event \(self.eventId): \(error)")
        }
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

    init(eventId: Int) {
        self.eventId = eventId
        _vm = StateObject(wrappedValue: EventDetailViewModel(eventId: eventId))
    }

    private var isLive: Bool { vm.event?.status == "live" }
    private var isFinished: Bool { vm.event?.status == "completed" || vm.event?.status == "closed" }

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
                    VStack(spacing: 20) {
                        teamHeader(event)
                        if isLive || isFinished { scoreSection(event) }
                        probabilitySection(event)
                        OddsChartView(eventId: event.id)
                        if let ei = event.ei ?? event.pulse { eiSection(ei) }
                        LineMovementView(eventId: event.id)
                        if let context = event.standingsContext { standingsSection(context) }
                        RelatedFuturesView(eventId: event.id)
                        espnSection(event)
                        bookmakerSection(event)
                    }
                    .padding()
                }
            }
        }
        .navigationTitle("Game Details")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            await vm.load()
        }
        .refreshable {
            await vm.load()
        }
        .onDisappear {
            vm.stopRefresh()
        }
    }

    // MARK: - Team Header

    private func teamHeader(_ event: EventDetail) -> some View {
        HStack(spacing: 16) {
            VStack(spacing: 4) {
                TeamLogoView(
                    url: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    teamName: event.awayTeam,
                    color: Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280"),
                    size: 40
                )
                Text(event.awayTeam)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                if let record = event.awayTeamData?.record {
                    Text(record).font(.caption2).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity)

            VStack(spacing: 2) {
                Text("@")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let sport = event.sport {
                    Text(sportDisplayName(for: sport))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                StatusBadge(status: event.status)
            }

            VStack(spacing: 4) {
                TeamLogoView(
                    url: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    teamName: event.homeTeam,
                    color: Color(hex: event.homeTeamData?.primaryColor ?? "#6b7280"),
                    size: 40
                )
                Text(event.homeTeam)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                if let record = event.homeTeamData?.record {
                    Text(record).font(.caption2).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity)
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Score

    private func scoreSection(_ event: EventDetail) -> some View {
        VStack(spacing: 4) {
            HStack {
                Text("\(event.awayScore ?? 0)")
                    .font(.system(size: 48, weight: .bold, design: .rounded).monospacedDigit())
                    .foregroundStyle(winnerColor(isAway: true, event: event))
                Spacer()
                VStack(spacing: 2) {
                    if let clock = event.espn?.gameClock, isLive {
                        Text(clock).font(.caption).foregroundStyle(.secondary)
                    }
                    if let period = event.espn?.period, isLive {
                        Text(period).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Text("\(event.homeScore ?? 0)")
                    .font(.system(size: 48, weight: .bold, design: .rounded).monospacedDigit())
                    .foregroundStyle(winnerColor(isAway: false, event: event))
            }
            .padding(.horizontal)
        }
    }

    // MARK: - Probability

    private func probabilitySection(_ event: EventDetail) -> some View {
        let awayColor = Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280")
        let homeColor = Color(hex: event.homeTeamData?.primaryColor ?? "#6b7280")

        return VStack(spacing: 8) {
            if !isFinished {
                if let odds = event.currentOdds,
                   let away = odds.awayProbability,
                   let home = odds.homeProbability {
                    HStack {
                        Text(formatProbability(away))
                            .font(.title3).fontWeight(.semibold)
                            .foregroundStyle(awayColor)
                        Spacer()
                        Text("Win Probability").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Text(formatProbability(home))
                            .font(.title3).fontWeight(.semibold)
                            .foregroundStyle(homeColor)
                    }
                    ProbabilityBar(
                        awayProb: away, homeProb: home,
                        awayColor: awayColor, homeColor: homeColor,
                        height: 10
                    )
                }
            }

            if let opening = event.openingOdds,
               let awayOpen = opening.awayProbability,
               let homeOpen = opening.homeProbability {
                VStack(spacing: 4) {
                    if isFinished {
                        ProbabilityBar(
                            awayProb: awayOpen, homeProb: homeOpen,
                            awayColor: awayColor.opacity(0.5),
                            homeColor: homeColor.opacity(0.5),
                            height: 8
                        )
                    }
                    HStack {
                        Text(formatProbability(awayOpen))
                            .font(.caption2).foregroundStyle(.secondary)
                        Spacer()
                        Text(isFinished ? "Pre-game odds" : "Opened")
                            .font(.caption2).foregroundStyle(.tertiary)
                        Spacer()
                        Text(formatProbability(homeOpen))
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - EI Section

    private func eiSection(_ ei: EIData) -> some View {
        VStack(spacing: 8) {
            HStack {
                Text("Excitement Index")
                    .font(.subheadline)
                    .fontWeight(.medium)
                Spacer()
                EIBadgeView(ei: ei, size: .md)
            }
            if let label = ei.label {
                Text(label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
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
        VStack(alignment: .leading, spacing: 6) {
            Text("Standings Context")
                .font(.subheadline)
                .fontWeight(.medium)
            if let away = context.away {
                Text(away).font(.caption).foregroundStyle(.secondary)
            }
            if let home = context.home {
                Text(home).font(.caption).foregroundStyle(.secondary)
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
            VStack(alignment: .leading, spacing: 6) {
                Text("Game Info")
                    .font(.subheadline)
                    .fontWeight(.medium)
                if let broadcast = event.espn?.broadcast {
                    HStack {
                        Image(systemName: "tv").font(.caption)
                        Text(broadcast).font(.caption)
                    }
                    .foregroundStyle(.secondary)
                }
                if let ct = event.commenceTime {
                    HStack {
                        Image(systemName: "clock").font(.caption)
                        RelativeTimeText(dateString: ct)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Bookmakers

    @ViewBuilder
    private func bookmakerSection(_ event: EventDetail) -> some View {
        if let bookmakers = event.bookmakerOdds, !bookmakers.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Sportsbook Odds")
                    .font(.subheadline)
                    .fontWeight(.medium)
                ForEach(bookmakers.prefix(10), id: \.bookmaker) { bm in
                    HStack {
                        Text(bm.bookmaker ?? "Unknown")
                            .font(.caption)
                            .frame(width: 100, alignment: .leading)
                        Spacer()
                        if let away = bm.awayMoneyline {
                            Text(formatMoneyline(away))
                                .font(.caption.monospacedDigit())
                                .frame(width: 60, alignment: .trailing)
                        }
                        if let home = bm.homeMoneyline {
                            Text(formatMoneyline(home))
                                .font(.caption.monospacedDigit())
                                .frame(width: 60, alignment: .trailing)
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

    private func formatMoneyline(_ ml: Int) -> String {
        ml > 0 ? "+\(ml)" : "\(ml)"
    }
}
