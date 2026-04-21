import SwiftUI
import Combine

// MARK: - Masters Live Leaderboard (Ultra-Low-Data)

struct MastersLiveView: View {
    @StateObject private var vm = MastersLiveViewModel()

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                loadingView
            case .noEvent:
                noEventView
            case .live:
                leaderboardView
            case .error(let message):
                errorView(message)
            }
        }
        .navigationTitle("Live Leaderboard")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
    }

    // MARK: - Loading

    private var loadingView: some View {
        VStack(spacing: 8) {
            ForEach(0..<10, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.systemGray6))
                    .frame(height: 28)
            }
        }
        .padding()
    }

    // MARK: - No Event

    private var noEventView: some View {
        VStack(spacing: 8) {
            Text("No Tournament In Play")
                .font(.headline)
            Text("Check back when the tournament starts.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
    }

    // MARK: - Error

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 8) {
            Text("Error")
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button("Retry") { Task { await vm.load() } }
                .font(.subheadline)
                .fontWeight(.medium)
        }
        .padding()
    }

    // MARK: - Leaderboard

    private var leaderboardView: some View {
        List {
            // Header section
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(vm.eventName)
                                .font(.headline)
                            Text(vm.roundLabel)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        liveBadge
                    }
                    if let updated = vm.lastUpdatedDisplay {
                        Text("Updated \(updated)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }

            // Leaderboard rows
            Section {
                // Column headers
                leaderboardHeader

                ForEach(Array(vm.players.prefix(30).enumerated()), id: \.element.id) { _, player in
                    leaderboardRow(player)
                }
            } footer: {
                Text("Position and probability changes are since the start of \(vm.roundLabel) play today. Auto-refreshes every 60 seconds.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .listStyle(.plain)
        .refreshable { await vm.load() }
    }

    private var liveBadge: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(Color.red)
                .frame(width: 7, height: 7)
            Text("LIVE")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.red)
        }
    }

    private var leaderboardHeader: some View {
        HStack(spacing: 0) {
            Text("Pos")
                .frame(width: 32, alignment: .leading)
            Text("Player")
                .frame(maxWidth: .infinity, alignment: .leading)
            Text("Score")
                .frame(width: 44, alignment: .trailing)
            Text("Thru")
                .frame(width: 36, alignment: .trailing)
            Text("Win%")
                .frame(width: 52, alignment: .trailing)
        }
        .font(.system(size: 10, weight: .semibold))
        .foregroundStyle(.secondary)
        .textCase(.uppercase)
        .padding(.vertical, 2)
    }

    private func leaderboardRow(_ player: GolfLeaderboardPlayer) -> some View {
        HStack(spacing: 0) {
            Text(player.position)
                .frame(width: 32, alignment: .leading)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
                .monospacedDigit()

            Text(player.name)
                .frame(maxWidth: .infinity, alignment: .leading)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(1)

            Text(player.score)
                .frame(width: 44, alignment: .trailing)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(scoreColor(player.totalScoreRaw))
                .monospacedDigit()

            Text(player.thru)
                .frame(width: 36, alignment: .trailing)
                .font(.caption)
                .foregroundStyle(.tertiary)
                .monospacedDigit()

            Text(String(format: "%.1f%%", player.winProb))
                .frame(width: 52, alignment: .trailing)
                .font(.caption)
                .fontWeight(.bold)
                .monospacedDigit()
        }
        .padding(.vertical, 1)
    }

    private func scoreColor(_ raw: Int?) -> Color {
        guard let raw else { return .primary }
        if raw < 0 { return .red }
        if raw > 0 { return .primary }
        return .primary
    }
}

// MARK: - ViewModel

final class MastersLiveViewModel: ObservableObject {
    enum State {
        case loading
        case noEvent
        case live
        case error(String)
    }

    @Published var state: State = .loading
    @Published var players: [GolfLeaderboardPlayer] = []
    @Published var eventName: String = ""
    @Published var roundLabel: String = ""
    @Published var lastUpdatedDisplay: String?

    private var refreshTimer: Timer?

    private static let roundNames: [Int: String] = [
        1: "Round 1",
        2: "Round 2",
        3: "Round 3",
        4: "Round 4",
    ]

    @MainActor
    func load() async {
        do {
            let response = try await APIClient.shared.fetchGolfLeaderboard()

            if response.status == "no_event" {
                state = .noEvent
                return
            }

            eventName = response.eventName ?? "Tournament"
            players = response.players
            roundLabel = Self.roundNames[response.currentRound ?? 0] ?? "Round \(response.currentRound ?? 0)"

            if let updated = response.lastUpdated {
                lastUpdatedDisplay = formatUpdateTime(updated)
            }

            state = .live
            startAutoRefresh()
        } catch {
            state = .error(error.localizedDescription)
        }
    }

    private func startAutoRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { await self?.load() }
        }
    }

    deinit {
        refreshTimer?.invalidate()
    }

    private func formatUpdateTime(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: iso) ?? ISO8601DateFormatter().date(from: iso) else {
            return iso
        }
        let display = DateFormatter()
        display.dateFormat = "h:mm a"
        display.timeZone = .current
        return display.string(from: date)
    }
}
