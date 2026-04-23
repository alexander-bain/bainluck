import SwiftUI

/// Renders game prop markets grouped by player with threshold ladders.
/// Replaces the flat list of "Paul Goldschmidt: 3+ = 94%".
struct GamePropsView: View {
    let futures: [RelatedFuture]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    private struct PlayerProps: Identifiable {
        let id: String // player name
        let player: String
        let lines: [PropLine]
        let marketType: String
    }

    private struct PropLine {
        let threshold: String
        let probability: Double
        let marketId: Int
    }

    private var playerGroups: [PlayerProps] {
        // Group by player name, keeping only interesting thresholds
        var byPlayer: [String: (lines: [PropLine], market: String)] = [:]

        for f in futures {
            let parts = f.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            let player = parts[0].trimmingCharacters(in: .whitespaces)
            let threshold = parts[1].trimmingCharacters(in: .whitespaces)
            let prob = f.probability ?? 0

            // Only interesting thresholds
            guard prob > 0.10 && prob < 0.90 else { continue }

            let market = f.cleanLabel ?? f.marketName
            let marketType = market.split(separator: ":").last.map { String($0).trimmingCharacters(in: .whitespaces) } ?? market

            var entry = byPlayer[player] ?? (lines: [], market: marketType)
            entry.lines.append(PropLine(threshold: threshold, probability: prob, marketId: f.marketId))
            entry.market = marketType
            byPlayer[player] = entry
        }

        return byPlayer
            .filter { !$0.value.lines.isEmpty }
            .map { PlayerProps(id: $0.key, player: $0.key, lines: $0.value.lines.sorted { $0.probability > $1.probability }, marketType: $0.value.market) }
            .sorted { $0.lines.count > $1.lines.count }
    }

    var body: some View {
        let groups = playerGroups
        if groups.isEmpty { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(groups.prefix(12)) { group in
                    playerRow(group)
                }
                if groups.count > 12 {
                    Text("+\(groups.count - 12) more players")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(12)
            .background(Color.secondary.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    private func playerRow(_ group: PlayerProps) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(group.player)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
                Spacer()
                Text(group.marketType)
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }

            HStack(spacing: 8) {
                ForEach(Array(group.lines.prefix(4).enumerated()), id: \.offset) { _, line in
                    VStack(spacing: 2) {
                        Text(line.threshold)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.secondary)
                        Text("\(Int((line.probability * 100).rounded()))%")
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(line.probability > 0.5 ? .primary : .secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
