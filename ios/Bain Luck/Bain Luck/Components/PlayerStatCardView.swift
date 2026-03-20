import SwiftUI

/// Compact grouped display for player prop markets — matches web PlayerStatCard.
struct PlayerStatCardView: View {
    let playerName: String
    let statCategory: String
    let lines: [StatPropLine]
    var headshotUrl: String? = nil
    var espnPlayerId: String? = nil
    var sportKey: String? = nil
    var eventMatchup: String? = nil
    var eventTime: String? = nil
    var onLineClick: ((StatPropLine) -> Void)? = nil

    private var sortedLines: [StatPropLine] {
        lines.sorted { $0.thresholdValue < $1.thresholdValue }.prefix(4).map { $0 }
    }
    
    private var parsedEventTime: Date? {
        guard let eventTime else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: eventTime) ?? ISO8601DateFormatter().date(from: eventTime)
    }

    private var statInfo: (abbr: String, full: String) {
        statLabels[statCategory.lowercased()] ?? (statCategory.uppercased().prefix(4).description, statCategory.capitalized)
    }

    private var eventTimeStr: String? {
        guard let date = parsedEventTime else { return nil }
        let calendar = Calendar.current
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a"
        let time = timeFormatter.string(from: date)
        if calendar.isDateInToday(date) {
            return time
        } else {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "MMM d"
            return "\(dateFormatter.string(from: date)) \(time)"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header: Avatar + stat name prominent, player name secondary
            HStack(spacing: 10) {
                PlayerAvatarView(
                    playerName: playerName,
                    headshotUrl: headshotUrl,
                    espnPlayerId: espnPlayerId,
                    sportKey: sportKey,
                    size: 32
                )

                VStack(alignment: .leading, spacing: 1) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(statInfo.full)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundStyle(.primary)
                        Text(statInfo.abbr)
                            .font(.system(size: 10, weight: .medium, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                    Text(playerName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
            }

            // Event context
            if eventMatchup != nil || eventTimeStr != nil {
                Divider()
                    .padding(.vertical, 2)
                HStack(spacing: 4) {
                    if let matchup = eventMatchup {
                        Text(matchup)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.primary.opacity(0.8))
                    }
                    if eventMatchup != nil && eventTimeStr != nil {
                        Text("·")
                            .font(.caption2)
                            .foregroundStyle(.secondary.opacity(0.5))
                    }
                    if let time = eventTimeStr {
                        Text(time)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            // Lines as simple rows
            VStack(spacing: 4) {
                ForEach(Array(sortedLines.enumerated()), id: \.element.id) { index, line in
                    Button {
                        onLineClick?(line)
                    } label: {
                        HStack(spacing: 6) {
                            // Rank indicator
                            Text("\(index + 1)")
                                .font(.system(size: 10, weight: index == 0 ? .bold : .regular))
                                .foregroundStyle(index == 0 ? .orange : .secondary)
                                .frame(width: 16, height: 16)
                                .background(index == 0 ? .orange.opacity(0.15) : .clear)
                                .clipShape(RoundedRectangle(cornerRadius: 3))

                            // Threshold
                            Text("\(line.thresholdValue)+")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(minWidth: 24, alignment: .leading)

                            // Mini probability bar
                            GeometryReader { geo in
                                let prob = line.probability
                                Capsule()
                                    .fill(Color.secondary.opacity(0.2))
                                    .frame(height: 4)
                                    .overlay(alignment: .leading) {
                                        Capsule()
                                            .fill(Color.secondary.opacity(index == 0 ? 0.6 : 0.3))
                                            .frame(width: geo.size.width * prob, height: 4)
                                    }
                            }
                            .frame(width: 48, height: 4)

                            // Probability text
                            Text(formatProbability(line.probability))
                                .font(.system(size: 12, weight: .medium, design: .monospaced))
                                .foregroundStyle(probColor(line.probability))
                                .frame(minWidth: 32, alignment: .trailing)
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 3)
                        .background(Color.cardBackgroundDark.opacity(0.3))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(12)
        .background(Color.cardBackgroundDark)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func probColor(_ prob: Double) -> Color {
        if prob >= 0.7 { return .green }
        if prob >= 0.4 { return .primary }
        if prob >= 0.15 { return .orange }
        return .red
    }
}

// MARK: - Player Avatar with ESPN fallback

struct PlayerAvatarView: View {
    let playerName: String
    var headshotUrl: String? = nil
    var espnPlayerId: String? = nil
    var sportKey: String? = nil
    var size: CGFloat = 28

    @State private var image: UIImage?
    @State private var loadFailed = false

    private var resolvedURL: String? {
        if let url = headshotUrl, !url.isEmpty { return url }
        if let espnId = espnPlayerId {
            return espnHeadshotURL(playerId: espnId, sportKey: sportKey)
        }
        return nil
    }

    private var initials: String {
        playerName.split(separator: " ")
            .compactMap { $0.first }
            .map(String.init)
            .joined()
            .prefix(2)
            .uppercased()
    }

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: size, height: size)
                    .clipShape(Circle())
            } else if loadFailed || resolvedURL == nil {
                initialsFallback
            } else {
                Circle()
                    .fill(Color.blue.opacity(0.15))
                    .frame(width: size, height: size)
            }
        }
        .task(id: resolvedURL) {
            guard let urlStr = resolvedURL, let url = URL(string: urlStr) else {
                loadFailed = true
                return
            }
            image = await ImageCache.shared.image(for: url)
            if image == nil { loadFailed = true }
        }
    }

    private var initialsFallback: some View {
        ZStack {
            Circle()
                .fill(Color.blue.opacity(0.2))
            Text(initials)
                .font(.system(size: size * 0.38, weight: .semibold))
                .foregroundStyle(.blue)
        }
        .frame(width: size, height: size)
    }
}

// MARK: - ESPN Headshot URL Helper

func espnHeadshotURL(playerId: String, sportKey: String?) -> String {
    let sport = sportKeyToESPNHeadshotSport(sportKey)
    return "https://a.espncdn.com/combiner/i?img=/i/headshots/\(sport)/players/full/\(playerId).png&w=96&h=70&cb=1"
}

func sportKeyToESPNHeadshotSport(_ sportKey: String?) -> String {
    guard let key = sportKey?.lowercased() else { return "nba" }
    if key.contains("nba") || key.contains("wnba") { return "nba" }
    if key.contains("nfl") || key.contains("football") { return "nfl" }
    if key.contains("mlb") || key.contains("baseball") { return "mlb" }
    if key.contains("nhl") || key.contains("hockey") { return "nhl" }
    if key.contains("ncaa") && key.contains("basket") { return "mens-college-basketball" }
    if key.contains("ncaa") && key.contains("football") { return "college-football" }
    if key.contains("mls") || key.contains("soccer") { return "soccer" }
    return "nba"
}

// MARK: - Stat Labels

private let statLabels: [String: (abbr: String, full: String)] = [
    "points": ("PTS", "Points"),
    "rebounds": ("REB", "Rebounds"),
    "assists": ("AST", "Assists"),
    "steals": ("STL", "Steals"),
    "blocks": ("BLK", "Blocks"),
    "threes": ("3PM", "3-Pointers Made"),
    "strikeouts": ("K", "Strikeouts"),
    "hits": ("H", "Hits"),
    "home_runs": ("HR", "Home Runs"),
    "rbis": ("RBI", "RBIs"),
    "goals": ("G", "Goals"),
    "touchdowns": ("TD", "Touchdowns"),
    "passing_yards": ("PASS", "Passing Yards"),
    "rushing_yards": ("RUSH", "Rushing Yards"),
]
