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

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
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
}

// MARK: - View

struct LineMovementView: View {
    let eventId: Int
    @StateObject private var vm: LineMovementViewModel

    init(eventId: Int) {
        self.eventId = eventId
        _vm = StateObject(wrappedValue: LineMovementViewModel(eventId: eventId))
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
                Text("Line Movement")
                    .font(.subheadline)
                    .fontWeight(.medium)

                if let explanation = lm.explanation {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "lightbulb.fill")
                            .font(.caption)
                            .foregroundStyle(.yellow)
                        Text(explanation)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if hasMovements {
                    ForEach(lm.movements) { movement in
                        movementRow(movement)
                    }
                } else {
                    Text("No significant line movements detected")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }

                if hasDisagreement, let disagreement = lm.disagreementData {
                    disagreementSection(disagreement, explanation: lm.disagreementExplanation)
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Movement Row

    private func movementRow(_ movement: Movement) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                // Direction arrow + magnitude
                HStack(spacing: 2) {
                    Image(systemName: movement.change > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 10, weight: .semibold))
                    Text(formatProbability(abs(movement.change)))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                }
                .foregroundStyle(movement.change > 0 ? .green : .red)

                if movement.isMajor == true {
                    Text("MAJOR")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.red)
                        .clipShape(Capsule())
                }

                Spacer()

                // Before → After
                if let before = movement.homeProbBefore, let after = movement.homeProbAfter {
                    Text("\(formatProbability(before)) → \(formatProbability(after))")
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }

            if let context = movement.context, !context.isEmpty {
                Text(context)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Disagreement Section

    private func disagreementSection(_ data: DisagreementData, explanation: String?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Divider()

            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.purple)
                Text("Source Divergence")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.purple)
            }

            if let sb = data.sportsbooks, let pm = data.predictionMarkets {
                HStack(spacing: 16) {
                    VStack(spacing: 2) {
                        Text(formatProbability(sb))
                            .font(.caption)
                            .fontWeight(.semibold)
                            .monospacedDigit()
                        Text("Sportsbooks")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    VStack(spacing: 2) {
                        Text("vs")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }

                    VStack(spacing: 2) {
                        Text(formatProbability(pm))
                            .font(.caption)
                            .fontWeight(.semibold)
                            .monospacedDigit()
                        Text("Pred. Markets")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    if let gap = data.gap {
                        Spacer()
                        Text("\(formatProbability(gap)) gap")
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.purple)
                    }
                }
            }

            if let explanation {
                Text(explanation)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }
}
