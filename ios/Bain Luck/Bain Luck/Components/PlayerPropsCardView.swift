import SwiftUI

struct PlayerPropsCardView: View {
    let playerProps: [GameMarketPlayerProp]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color
    let eventStatus: String?

    private struct PlayerCard: Identifiable {
        let id: String
        let name: String
        let initials: String
        let team: String
        let color: Color
        let statGroups: [StatGroup]
    }

    private struct StatGroup: Identifiable {
        let id: String
        let type: String
        let rungs: [Rung]
    }

    private struct Rung {
        let threshold: Double
        let probability: Double
        let movement: Double?
    }

    private var playerCards: [PlayerCard] {
        // Group by player name
        var byPlayer: [String: [(prop: GameMarketPlayerProp, statType: String)]] = [:]
        for prop in playerProps {
            let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            let player = parts[0].trimmingCharacters(in: .whitespaces)
            let marketParts = prop.marketName.split(separator: ":")
            let statType = marketParts.count >= 2
                ? marketParts.last!.trimmingCharacters(in: .whitespaces)
                : "Props"
            byPlayer[player, default: []].append((prop, statType))
        }

        return byPlayer.compactMap { player, props -> PlayerCard? in
            guard !props.isEmpty else { return nil }

            let initials = player.split(separator: " ")
                .compactMap { $0.first.map(String.init) }
                .prefix(2)
                .joined()

            let homeShort = homeTeam.split(separator: " ").last.map(String.init) ?? homeTeam
            let isHome = props.first?.prop.outcomeName.localizedCaseInsensitiveContains(homeShort) ?? false
            let team = isHome ? "home" : "away"
            let color = isHome ? homeColor : awayColor

            // Group by stat type
            var statGroups: [String: [Rung]] = [:]
            for (prop, statType) in props {
                let rung = Rung(
                    threshold: prop.threshold ?? 0,
                    probability: prop.overProbability ?? 0,
                    movement: prop.movement
                )
                statGroups[statType, default: []].append(rung)
            }

            let groups = statGroups.map { type, rungs in
                StatGroup(
                    id: "\(player)-\(type)",
                    type: type,
                    rungs: rungs
                        .filter { $0.probability > 0.05 && $0.probability < 0.95 }
                        .sorted { $0.threshold < $1.threshold }
                )
            }
            .filter { !$0.rungs.isEmpty }
            .sorted { $0.rungs.count > $1.rungs.count }

            guard !groups.isEmpty else { return nil }

            return PlayerCard(
                id: player,
                name: player,
                initials: initials,
                team: team,
                color: color,
                statGroups: groups
            )
        }
        .sorted { $0.statGroups.map(\.rungs.count).reduce(0, +) > $1.statGroups.map(\.rungs.count).reduce(0, +) }
    }

    var body: some View {
        let cards = playerCards
        if cards.isEmpty { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 8) {
                Text("Player Props")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                let columns = [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)]
                LazyVGrid(columns: columns, spacing: 8) {
                    ForEach(cards.prefix(12)) { card in
                        playerCardView(card)
                    }
                }

                if cards.count > 12 {
                    Text("+\(cards.count - 12) more players")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    private func playerCardView(_ card: PlayerCard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header: initials + name
            HStack(spacing: 6) {
                Text(card.initials)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 24, height: 24)
                    .background(card.color)
                    .clipShape(Circle())

                Text(card.name.split(separator: " ").last.map(String.init) ?? card.name)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .lineLimit(1)

                Spacer()
            }

            // Stat groups
            ForEach(card.statGroups.prefix(3)) { group in
                VStack(alignment: .leading, spacing: 3) {
                    Text(group.type.uppercased())
                        .font(.system(size: 8, weight: .bold))
                        .tracking(0.5)
                        .foregroundStyle(.tertiary)

                    ForEach(Array(group.rungs.prefix(4).enumerated()), id: \.offset) { _, rung in
                        HStack(spacing: 4) {
                            Text("\(Int(rung.threshold))+")
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                                .frame(width: 22, alignment: .trailing)

                            GeometryReader { geo in
                                Capsule()
                                    .fill(card.color.opacity(0.3))
                                    .frame(width: max(4, geo.size.width * rung.probability))
                            }
                            .frame(height: 6)

                            Text("\(Int((rung.probability * 100).rounded()))%")
                                .font(.system(size: 10, weight: .semibold))
                                .monospacedDigit()
                                .foregroundStyle(.primary)
                                .frame(width: 28, alignment: .trailing)
                        }
                    }
                }
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.secondary.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Color.secondary.opacity(0.08), lineWidth: 1)
        )
    }
}
