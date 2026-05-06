import SwiftUI

struct PlayerPropsCardView: View {
    let playerProps: [GameMarketPlayerProp]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color
    let eventStatus: String?
    var boxScore: [String: [String: Double]]?

    @State private var teamFilter: String = "all"
    @State private var showAllStats: Bool = false

    private var homeAbbr: String {
        String(homeTeam.split(separator: " ").last ?? "Home")
    }
    private var awayAbbr: String {
        String(awayTeam.split(separator: " ").last ?? "Away")
    }
    private var isDone: Bool { eventStatus == "completed" || eventStatus == "closed" }
    private var isLive: Bool { eventStatus == "live" }

    private struct PlayerCard: Identifiable {
        let id: String
        let name: String
        let initials: String
        let headshotURL: URL?
        let team: String
        let teamLabel: String
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

    private var allPlayerCards: [PlayerCard] {
        var byPlayer: [String: [(prop: GameMarketPlayerProp, statType: String)]] = [:]
        for prop in playerProps {
            let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            let player = parts[0].trimmingCharacters(in: .whitespaces)
            // Use the full marketName as the stat type key to prevent mixing
            // different stat categories (e.g., "Player Hits" vs "Player RBIs")
            let statType = prop.marketName.trimmingCharacters(in: .whitespaces)
            byPlayer[player, default: []].append((prop, statType))
        }

        return byPlayer.compactMap { player, props -> PlayerCard? in
            guard !props.isEmpty else { return nil }

            let initials = player.split(separator: " ")
                .compactMap { $0.first.map(String.init) }
                .prefix(2)
                .joined()

            let headshotURL = props.compactMap({ $0.prop.playerHeadshot }).first.flatMap { URL(string: $0) }
            let apiTeam = props.first?.prop.playerTeam ?? "away"
            let teamLabel = apiTeam == "home" ? "Home" : "Away"
            let color = apiTeam == "home" ? homeColor : awayColor

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
                    rungs: rungs.sorted { $0.threshold < $1.threshold }
                )
            }
            .filter { !$0.rungs.isEmpty }
            .sorted { $0.rungs.count > $1.rungs.count }

            guard !groups.isEmpty else { return nil }

            return PlayerCard(
                id: player,
                name: player,
                initials: initials,
                headshotURL: headshotURL,
                team: apiTeam,
                teamLabel: teamLabel,
                color: color,
                statGroups: groups
            )
        }
        .sorted { $0.statGroups.map(\.rungs.count).reduce(0, +) > $1.statGroups.map(\.rungs.count).reduce(0, +) }
    }

    private var filteredCards: [PlayerCard] {
        if teamFilter == "all" { return allPlayerCards }
        return allPlayerCards.filter { $0.team == teamFilter }
    }

    private var sources: [String] {
        Array(Set(playerProps.compactMap(\.source))).sorted()
    }

    var body: some View {
        let cards = filteredCards
        if allPlayerCards.isEmpty { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 10) {
                // Header: title + source badge + controls
                HStack {
                    Text("Player Props")
                        .font(.subheadline)
                        .fontWeight(.semibold)

                    // Source badge
                    if let src = sources.first {
                        Text(src.uppercased())
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.1))
                            .clipShape(Capsule())
                    }

                    Spacer()

                    // Stat toggle
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) { showAllStats.toggle() }
                    } label: {
                        Text(showAllStats ? "Points" : "All stats")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                    }
                    .buttonStyle(.plain)
                }

                // Team filter — full width
                HStack(spacing: 0) {
                    filterButton("All", value: "all")
                        .frame(maxWidth: .infinity)
                    filterButton(homeAbbr, value: "home")
                        .frame(maxWidth: .infinity)
                    filterButton(awayAbbr, value: "away")
                        .frame(maxWidth: .infinity)
                }
                .background(Color.secondary.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))

                // Player grid — responsive columns
                let columns = [GridItem(.adaptive(minimum: 280), spacing: 10)]
                LazyVGrid(columns: columns, spacing: 10) {
                    ForEach(cards) { card in
                        playerCardView(card)
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    private func filterButton(_ label: String, value: String) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.15)) { teamFilter = value }
        } label: {
            Text(label)
                .font(.system(size: 11, weight: teamFilter == value ? .bold : .medium))
                .foregroundStyle(teamFilter == value ? .white : .secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(teamFilter == value ? Color.blue : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
    }

    private func playerCardView(_ card: PlayerCard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header: headshot + name + team label
            HStack(spacing: 8) {
                if let url = card.headshotURL {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().scaledToFill()
                        case .empty:
                            // Loading state — show subtle placeholder
                            Color(card.color.opacity(0.15))
                        case .failure:
                            // Image failed to load — fall back to initials
                            Text(card.initials)
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(.white)
                        @unknown default:
                            Text(card.initials)
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(.white)
                        }
                    }
                    .frame(width: 36, height: 36)
                    .background(card.color.opacity(0.2))
                    .clipShape(Circle())
                } else {
                    Text(card.initials)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(card.color)
                        .clipShape(Circle())
                }

                VStack(alignment: .leading, spacing: 1) {
                    Text(card.name)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .lineLimit(1)
                    Text(card.teamLabel)
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                }

                Spacer()
            }

            // Stat groups — filtered by toggle, 2-column layout
            let visibleGroups = showAllStats ? card.statGroups : card.statGroups.filter {
                $0.type.lowercased().contains("point") || $0.type.lowercased().contains("pts")
            }
            let groupsToShow = visibleGroups.isEmpty ? Array(card.statGroups.prefix(1)) : visibleGroups
            let pairs = stride(from: 0, to: groupsToShow.count, by: 2).map { i in
                (groupsToShow[i], i + 1 < groupsToShow.count ? groupsToShow[i + 1] : nil)
            }
            ForEach(pairs.indices, id: \.self) { idx in
                let pair = pairs[idx]
                HStack(alignment: .top, spacing: 10) {
                    statGroupView(pair.0, card: card)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if let second = pair.1 {
                        statGroupView(second, card: card)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        Spacer().frame(maxWidth: .infinity)
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

    /// Clean up stat type labels: strip "Player " prefix, keep just the stat name
    private func cleanStatLabel(_ raw: String) -> String {
        var s = raw
        // Strip common prefixes like "Player " or "Batter "
        for prefix in ["Player ", "Batter ", "Pitcher "] {
            if s.hasPrefix(prefix) {
                s = String(s.dropFirst(prefix.count))
            }
        }
        return s
    }

    private func statGroupView(_ group: StatGroup, card: PlayerCard) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text(cleanStatLabel(group.type).uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(.tertiary)
                Text("chance of hitting")
                    .font(.system(size: 8))
                    .foregroundStyle(.quaternary)
            }
            ForEach(Array(group.rungs.enumerated()), id: \.offset) { _, rung in
                rungRow(rung, card: card, statType: group.type)
            }
        }
    }

    private func rungRow(_ rung: Rung, card: PlayerCard, statType: String) -> some View {
        let actualValue = lookupActualValue(player: card.name, stat: statType)
        let isHit = actualValue.map { $0 >= rung.threshold } ?? false
        let showActual = (isDone || isLive) && actualValue != nil

        return HStack(spacing: 4) {
            Text("\(Int(rung.threshold))+")
                .font(.system(size: 10))
                .foregroundStyle(showActual && isHit ? card.color : .secondary)
                .fontWeight(showActual && isHit ? .bold : .regular)
                .frame(width: 22, alignment: .trailing)

            GeometryReader { geo in
                Capsule()
                    .fill(Color.secondary.opacity(0.08))
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(isDone
                                ? (isHit ? card.color.opacity(0.5) : Color.secondary.opacity(0.15))
                                : card.color.opacity(0.3))
                            .frame(width: max(4, geo.size.width * rung.probability))
                    }
            }
            .frame(height: 8)

            if isDone, actualValue != nil {
                Image(systemName: isHit ? "checkmark" : "minus")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(isHit ? .green : .secondary)
                    .frame(width: 10)
            }

            Text("\(Int((rung.probability * 100).rounded()))%")
                .font(.system(size: 10, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(.primary)
                .frame(width: 28, alignment: .trailing)
        }
    }

    private func lookupActualValue(player: String, stat: String) -> Double? {
        guard let box = boxScore else { return nil }
        let playerKey = player.lowercased()
        for (key, stats) in box {
            if key.lowercased() == playerKey || key.lowercased().contains(playerKey.split(separator: " ").last ?? "") {
                let statKey = stat.lowercased()
                if let val = stats[statKey] { return val }
                let mapping: [String: [String]] = [
                    "points": ["points", "pts"],
                    "rebounds": ["rebounds", "reb", "totalRebounds"],
                    "assists": ["assists", "ast"],
                    "steals": ["steals", "stl"],
                    "three pointers": ["threePointersMade", "3pm", "threePointers"],
                ]
                for (statName, aliases) in mapping {
                    if statKey.contains(statName) || statName.contains(statKey) {
                        for alias in aliases {
                            if let val = stats[alias] { return val }
                        }
                    }
                }
            }
        }
        return nil
    }
}
