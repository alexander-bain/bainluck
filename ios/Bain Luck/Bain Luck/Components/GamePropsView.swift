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
        var byPlayer: [String: (lines: [PropLine], market: String)] = [:]

        for f in futures {
            let parts = f.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            let player = parts[0].trimmingCharacters(in: .whitespaces)
            let threshold = parts[1].trimmingCharacters(in: .whitespaces)
            let prob = f.probability ?? 0
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
            // Compact grid: 2 columns, each player is one compact row
            let columns = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]
            LazyVGrid(columns: columns, spacing: 6) {
                ForEach(groups.prefix(16)) { group in
                    compactPlayerCell(group)
                }
            }
            .padding(10)
            .background(Color.secondary.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    private func compactPlayerCell(_ group: PlayerProps) -> some View {
        HStack(spacing: 4) {
            Text(group.player.split(separator: " ").last.map(String.init) ?? group.player)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.primary)
                .lineLimit(1)
            Spacer(minLength: 2)
            // Show best threshold inline
            if let best = group.lines.first {
                Text(best.threshold)
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                Text("\(Int((best.probability * 100).rounded()))%")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(best.probability > 0.5 ? .primary : .secondary)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.secondary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }
}
