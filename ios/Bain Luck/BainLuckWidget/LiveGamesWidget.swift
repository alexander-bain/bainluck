import SwiftUI
import WidgetKit

// MARK: - Small Widget: Single Best Live Game

struct SmallLiveGameView: View {
    let entry: BainLuckWidgetEntry

    var body: some View {
        if let game = entry.liveGames.first {
            VStack(spacing: 6) {
                // Sport + period badge
                HStack {
                    Text(game.sport.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    if !game.period.isEmpty {
                        Text(game.period)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.green)
                    }
                }

                Spacer(minLength: 2)

                // Away team row
                teamRow(
                    abbrev: game.awayAbbrev,
                    score: game.awayScore,
                    prob: game.awayProb,
                    color: game.awayColor,
                    isLeading: game.awayProb > game.homeProb
                )

                // Home team row
                teamRow(
                    abbrev: game.homeAbbrev,
                    score: game.homeScore,
                    prob: game.homeProb,
                    color: game.homeColor,
                    isLeading: game.homeProb > game.awayProb
                )

                Spacer(minLength: 2)

                // Probability bar
                probabilityBar(homeProb: game.homeProb, homeColor: game.homeColor, awayColor: game.awayColor)
            }
            .padding(12)
            .widgetURL(URL(string: "bainluck://events/\(game.id)"))
        } else {
            noGamesView
        }
    }

    private func teamRow(abbrev: String, score: Int?, prob: Int, color: String?, isLeading: Bool) -> some View {
        HStack(spacing: 6) {
            // Team color indicator
            RoundedRectangle(cornerRadius: 2)
                .fill(Color(hex: color ?? "#999999"))
                .frame(width: 4, height: 20)

            Text(abbrev)
                .font(.system(size: 14, weight: isLeading ? .bold : .medium))
                .frame(width: 36, alignment: .leading)

            Spacer()

            if let score {
                Text("\(score)")
                    .font(.system(size: 16, weight: .heavy, design: .rounded).monospacedDigit())
            }

            Text("\(prob)%")
                .font(.system(size: 12, weight: .semibold, design: .rounded).monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 32, alignment: .trailing)
        }
    }

    private func probabilityBar(homeProb: Int, homeColor: String?, awayColor: String?) -> some View {
        GeometryReader { geo in
            HStack(spacing: 1) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color(hex: awayColor ?? "#666666").opacity(0.7))
                    .frame(width: geo.size.width * CGFloat(100 - homeProb) / 100.0)
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color(hex: homeColor ?? "#0A84FF").opacity(0.7))
                    .frame(width: geo.size.width * CGFloat(homeProb) / 100.0)
            }
        }
        .frame(height: 4)
    }

    private var noGamesView: some View {
        VStack(spacing: 6) {
            Image(systemName: "sportscourt")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No Live Games")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(.secondary)
            Text("Check back later")
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .widgetURL(URL(string: "bainluck://events"))
    }
}

// MARK: - Medium Widget: Multiple Live Games + Discover Items

struct MediumLiveGamesView: View {
    let entry: BainLuckWidgetEntry

    var body: some View {
        if entry.liveGames.isEmpty && entry.discoverItems.isEmpty {
            emptyView
        } else {
            HStack(spacing: 0) {
                // Left side: live games
                if !entry.liveGames.isEmpty {
                    liveGamesColumn
                        .frame(maxWidth: .infinity)
                }

                // Divider if both sections have content
                if !entry.liveGames.isEmpty && !entry.discoverItems.isEmpty {
                    Divider()
                        .padding(.vertical, 8)
                }

                // Right side: discover items (only show if we have space)
                if !entry.discoverItems.isEmpty {
                    discoverColumn
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(12)
        }
    }

    private var liveGamesColumn: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "circle.fill")
                    .font(.system(size: 5))
                    .foregroundStyle(.green)
                Text("LIVE")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.green)
                Spacer()
            }
            .padding(.bottom, 6)

            ForEach(Array(entry.liveGames.prefix(3).enumerated()), id: \.element.id) { index, game in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3)
                }
                compactGameRow(game)
            }

            Spacer(minLength: 0)
        }
    }

    private func compactGameRow(_ game: WidgetGame) -> some View {
        Link(destination: URL(string: "bainluck://events/\(game.id)")!) {
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(game.sport.uppercased())
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    if !game.period.isEmpty {
                        Text(game.period)
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(.green)
                    }
                }

                HStack(spacing: 4) {
                    // Team color dot
                    Circle()
                        .fill(Color(hex: game.awayColor ?? "#666666"))
                        .frame(width: 6, height: 6)
                    Text(game.awayAbbrev)
                        .font(.system(size: 11, weight: .medium))
                        .frame(width: 28, alignment: .leading)
                    Text("\(game.awayScore ?? 0)")
                        .font(.system(size: 11, weight: .heavy, design: .rounded).monospacedDigit())
                        .frame(width: 16, alignment: .trailing)

                    Text("-")
                        .font(.system(size: 8))
                        .foregroundStyle(.tertiary)

                    Text("\(game.homeScore ?? 0)")
                        .font(.system(size: 11, weight: .heavy, design: .rounded).monospacedDigit())
                        .frame(width: 16, alignment: .leading)
                    Text(game.homeAbbrev)
                        .font(.system(size: 11, weight: .medium))
                        .frame(width: 28, alignment: .trailing)
                    Circle()
                        .fill(Color(hex: game.homeColor ?? "#0A84FF"))
                        .frame(width: 6, height: 6)

                    Spacer()

                    Text("\(game.awayProb)-\(game.homeProb)")
                        .font(.system(size: 9, weight: .medium, design: .rounded).monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var discoverColumn: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 8))
                    .foregroundStyle(.secondary)
                Text("DISCOVER")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.bottom, 6)

            ForEach(Array(entry.discoverItems.prefix(3).enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3)
                }
                compactDiscoverRow(item)
            }

            Spacer(minLength: 0)
        }
    }

    private func compactDiscoverRow(_ item: WidgetDiscoverItem) -> some View {
        Link(destination: URL(string: "bainluck://futures/\(item.id)")!) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.category.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.secondary)

                HStack {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.leader)
                            .font(.system(size: 11, weight: .semibold))
                            .lineLimit(1)
                        Text(item.name)
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }

                    Spacer(minLength: 4)

                    VStack(alignment: .trailing, spacing: 1) {
                        Text("\(item.probability)%")
                            .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())

                        if let movement = item.movement, movement != 0 {
                            Text("\(movement > 0 ? "+" : "")\(movement)")
                                .font(.system(size: 8, weight: .semibold, design: .rounded))
                                .foregroundStyle(movement > 0 ? .green : .red)
                        }
                    }
                }
            }
        }
    }

    private var emptyView: some View {
        HStack {
            VStack(spacing: 6) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                Text("Bain Luck")
                    .font(.system(size: 13, weight: .semibold))
                Text("No live games right now")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(12)
        .widgetURL(URL(string: "bainluck://events"))
    }
}

// MARK: - Large Widget: Full Dashboard (macOS Notification Center / Today View)

struct LargeDashboardView: View {
    let entry: BainLuckWidgetEntry

    var body: some View {
        if entry.liveGames.isEmpty && entry.discoverItems.isEmpty {
            emptyView
        } else {
            VStack(alignment: .leading, spacing: 0) {
                // Live games section
                if !entry.liveGames.isEmpty {
                    liveGamesSection
                }

                if !entry.liveGames.isEmpty && !entry.discoverItems.isEmpty {
                    Divider()
                        .padding(.vertical, 6)
                }

                // Discover section
                if !entry.discoverItems.isEmpty {
                    discoverSection
                }

                Spacer(minLength: 0)
            }
            .padding(14)
        }
    }

    private var liveGamesSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "circle.fill")
                    .font(.system(size: 5))
                    .foregroundStyle(.green)
                Text("LIVE GAMES")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.green)
                Spacer()
                Text("\(entry.liveGames.count) game\(entry.liveGames.count == 1 ? "" : "s")")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            .padding(.bottom, 8)

            ForEach(Array(entry.liveGames.prefix(5).enumerated()), id: \.element.id) { index, game in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 4)
                }
                largeGameRow(game)
            }
        }
    }

    private func largeGameRow(_ game: WidgetGame) -> some View {
        Link(destination: URL(string: "bainluck://events/\(game.id)")!) {
            HStack(spacing: 8) {
                // Away team
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.awayColor ?? "#666666"))
                        .frame(width: 4, height: 24)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(game.awayAbbrev)
                            .font(.system(size: 13, weight: game.awayProb > game.homeProb ? .bold : .medium))
                        Text("\(game.awayProb)%")
                            .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    .frame(width: 40, alignment: .leading)
                }

                // Score
                HStack(spacing: 4) {
                    Text("\(game.awayScore ?? 0)")
                        .font(.system(size: 15, weight: .heavy, design: .rounded).monospacedDigit())
                        .frame(width: 20, alignment: .trailing)
                    Text("-")
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                    Text("\(game.homeScore ?? 0)")
                        .font(.system(size: 15, weight: .heavy, design: .rounded).monospacedDigit())
                        .frame(width: 20, alignment: .leading)
                }

                // Home team
                HStack(spacing: 6) {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(game.homeAbbrev)
                            .font(.system(size: 13, weight: game.homeProb > game.awayProb ? .bold : .medium))
                        Text("\(game.homeProb)%")
                            .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    .frame(width: 40, alignment: .trailing)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.homeColor ?? "#0A84FF"))
                        .frame(width: 4, height: 24)
                }

                Spacer()

                // Sport + period
                VStack(alignment: .trailing, spacing: 2) {
                    Text(game.sport.uppercased())
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.secondary)
                    if !game.period.isEmpty {
                        Text(game.period)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.green)
                    }
                }
            }
        }
    }

    private var discoverSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                Text("TRENDING")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.bottom, 8)

            ForEach(Array(entry.discoverItems.prefix(5).enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 4)
                }
                largeDiscoverRow(item)
            }
        }
    }

    private func largeDiscoverRow(_ item: WidgetDiscoverItem) -> some View {
        Link(destination: URL(string: "bainluck://futures/\(item.id)")!) {
            HStack(spacing: 8) {
                // Category pill
                Text(item.category.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.6), in: Capsule())

                VStack(alignment: .leading, spacing: 1) {
                    Text(item.leader)
                        .font(.system(size: 12, weight: .semibold))
                        .lineLimit(1)
                    Text(item.name)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 4)

                VStack(alignment: .trailing, spacing: 1) {
                    Text("\(item.probability)%")
                        .font(.system(size: 14, weight: .heavy, design: .rounded).monospacedDigit())

                    if let movement = item.movement, movement != 0 {
                        Text("\(movement > 0 ? "+" : "")\(movement)")
                            .font(.system(size: 9, weight: .semibold, design: .rounded))
                            .foregroundStyle(movement > 0 ? .green : .red)
                    }
                }
            }
        }
    }

    private var emptyView: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("Bain Luck")
                .font(.system(size: 14, weight: .semibold))
            Text("No live games or trending markets right now")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(14)
        .widgetURL(URL(string: "bainluck://events"))
    }
}

// MARK: - Color Extension (hex string to SwiftUI Color)

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)

        let r, g, b: Double
        switch hex.count {
        case 6:
            r = Double((int >> 16) & 0xFF) / 255.0
            g = Double((int >> 8) & 0xFF) / 255.0
            b = Double(int & 0xFF) / 255.0
        default:
            r = 0.6; g = 0.6; b = 0.6
        }

        self.init(red: r, green: g, blue: b)
    }
}
