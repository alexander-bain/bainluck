import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "lineMovement")

// MARK: - ViewModel

final class LineMovementViewModel: ObservableObject {
    @Published var lineMovement: LineMovementResponse?
    @Published var loading = true
    @Published var error: String?

    let eventId: Int
    private var refreshTimer: Timer?

    init(eventId: Int, preloaded: LineMovementResponse? = nil) {
        self.eventId = eventId
        if let preloaded {
            self.lineMovement = preloaded
            self.loading = false
        }
    }

    @MainActor
    func load() async {
        guard lineMovement == nil else { return }  // Skip if preloaded
        do {
            lineMovement = try await APIClient.shared.fetchLineMovement(eventId: eventId)
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load line movement for event \(self.eventId): \(error)")
        }
    }

    func configureAutoRefresh(eventStatus: String?) {
        refreshTimer?.invalidate()
        guard eventStatus == "live" else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                do {
                    self.lineMovement = try await APIClient.shared.fetchLineMovement(eventId: self.eventId)
                } catch {
                    logger.error("Failed to refresh line movement: \(error)")
                }
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}

// MARK: - View

struct LineMovementView: View {
    let eventId: Int
    var homeTeam: String = ""
    var awayTeam: String = ""
    var eventStatus: String? = nil
    @StateObject private var vm: LineMovementViewModel

    init(eventId: Int,
         homeTeam: String = "",
         awayTeam: String = "",
         eventStatus: String? = nil,
         preloadedData: LineMovementResponse? = nil) {
        self.eventId = eventId
        self.homeTeam = homeTeam
        self.awayTeam = awayTeam
        self.eventStatus = eventStatus
        _vm = StateObject(wrappedValue: LineMovementViewModel(eventId: eventId, preloaded: preloadedData))
    }

    var body: some View {
        Group {
            if vm.loading {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding()
            } else if let lm = vm.lineMovement {
                content(lm)
            }
            // Show nothing if error or no data
        }
        .task {
            await vm.load()
            vm.configureAutoRefresh(eventStatus: eventStatus)
        }
        .onDisappear {
            vm.stopRefresh()
        }
    }

    // MARK: - Content

    @ViewBuilder
    private func content(_ lm: LineMovementResponse) -> some View {
        let hasMovements = !lm.movements.isEmpty
        let hasExplanation = lm.explanation != nil
        let hasDisagreement = (lm.disagreementData?.gap ?? 0) > 0.05

        if hasMovements || hasExplanation || hasDisagreement {
            VStack(alignment: .leading, spacing: 12) {
                // Header
                if hasMovements {
                    HStack(spacing: 6) {
                        Text("\u{1F4C8}")
                            .font(.system(size: 14))
                        Text("Why Did the Line Move?")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }
                }

                // AI Explanation
                if let explanation = lm.explanation {
                    Text(explanation)
                        .font(.subheadline)
                        .foregroundStyle(.primary)
                        .lineSpacing(2)

                    // Context quality indicator
                    if let ctx = lm.context,
                       (ctx.injuriesCount ?? 0) == 0,
                       (ctx.newsCount ?? 0) == 0,
                       ctx.hasGameState != true {
                        Text("Limited context available for this game")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }

                // Movement Cards
                if hasMovements {
                    VStack(spacing: 8) {
                        ForEach(Array(lm.movements.prefix(3).enumerated()), id: \.element.id) { _, movement in
                            movementCard(movement)
                        }
                    }
                }

                if !hasMovements && hasExplanation {
                    // No movements but has explanation (edge case)
                } else if !hasMovements {
                    Text("No significant line movements detected")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }

                // No explanation indicator
                if !hasExplanation && hasMovements {
                    Text("AI explanation unavailable")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }

                // Prediction Market Disagreement
                if hasDisagreement, let disagreement = lm.disagreementData {
                    if hasMovements || hasExplanation {
                        Divider()
                    }
                    disagreementSection(disagreement, explanation: lm.disagreementExplanation)
                }

                // Attribution
                Text("Powered by AI analysis · Not betting advice")
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Movement Card

    private func movementCard(_ movement: Movement) -> some View {
        let isTowardHome = movement.change > 0
        let beneficiary = isTowardHome ? homeTeam : awayTeam
        let magnitude = Int((abs(movement.magnitude ?? movement.change) * 100).rounded())
        let isMajor = movement.isMajor == true

        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                // Magnitude + direction
                HStack(spacing: 4) {
                    Text(isMajor ? "\u{26A1}" : "\u{2197}")
                        .font(.system(size: 11))
                    Text("\(magnitude)% swing")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(isMajor ? Color(hex: "#b45309") : .primary)
                }

                Text("toward \(beneficiary)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                Spacer()

                // Time
                if let ts = movement.timestampStart, let date = ts.asDate {
                    Text(date, format: .dateTime.hour().minute())
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            // Before → After
            if let before = movement.homeProbBefore, let after = movement.homeProbAfter {
                HStack(spacing: 4) {
                    Text("\(Int((before * 100).rounded()))% → \(Int((after * 100).rounded()))%")
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                    if !homeTeam.isEmpty {
                        Text("(\(homeTeam))")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isMajor ? Color.orange.opacity(0.08) : Color.secondary.opacity(0.06))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(isMajor ? Color.orange.opacity(0.2) : Color.secondary.opacity(0.1), lineWidth: 1)
        )
    }

    // MARK: - Disagreement Section

    private func disagreementSection(_ data: DisagreementData, explanation: String?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("\u{1F52E}")
                    .font(.system(size: 14))
                Text("Market Divergence")
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }

            if let sb = data.sportsbooks, let pm = data.predictionMarkets {
                HStack {
                    // Sportsbooks side
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Sportsbooks")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                        Text(formatProbability(sb))
                            .font(.title3)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    // Gap badge
                    VStack(spacing: 2) {
                        if let gap = data.gap {
                            let isPurple = gap > 0.10
                            Text("\(Int((gap * 100).rounded()))% gap")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .foregroundStyle(isPurple ? .purple : .blue)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background((isPurple ? Color.purple : Color.blue).opacity(0.12))
                                .clipShape(Capsule())
                        }
                        Text("vs")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }

                    // Prediction market side
                    VStack(alignment: .trailing, spacing: 2) {
                        // Try to show specific source name
                        if let sources = data.sources {
                            let sourceName = sources.keys.first { $0 != "sportsbooks" }
                            Text(sourceDisplayName(sourceName))
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        } else {
                            Text("Pred. Markets")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        Text(formatProbability(pm))
                            .font(.title3)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    }
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }

                if !homeTeam.isEmpty {
                    Text("\(homeTeam) win probability")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            if let explanation {
                Text(explanation)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineSpacing(2)
            }
        }
    }

    // MARK: - Helpers

    private func sourceDisplayName(_ source: String?) -> String {
        switch source {
        case "kalshi": return "Kalshi"
        case "polymarket": return "Polymarket"
        default: return "Pred. Markets"
        }
    }
}
