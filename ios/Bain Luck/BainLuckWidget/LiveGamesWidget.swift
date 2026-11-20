import SwiftUI
import WidgetKit

// MARK: - Small Widget: Single Best Live Game

struct SmallLiveGameView: View {
    let entry: BainLuckWidgetEntry
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if let game = entry.liveGames.first {
            let awayHex = game.resolvedAwayColor(for: colorScheme)
            let homeHex = game.resolvedHomeColor(for: colorScheme)
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
                    color: awayHex,
                    isLeading: game.awayIsLeading
                )

                // Home team row
                teamRow(
                    abbrev: game.homeAbbrev,
                    score: game.homeScore,
                    prob: game.homeProb,
                    color: homeHex,
                    isLeading: game.homeIsLeading
                )

                Spacer(minLength: 2)

                // Probability bar
                probabilityBar(
                    homeProb: game.homeProb,
                    homeColor: homeHex,
                    awayColor: awayHex,
                    awayIsWithheld: game.awayProb == nil
                )
            }
            .padding(12)
            .widgetURL(URL(string: "bainluck://events/\(game.id)"))
        } else {
            noGamesView
        }
    }

    /// `prob` is optional for #5363: a draw-priced sport has no away price, so
    /// that row keeps its crest, abbreviation and score and drops only the
    /// percentage.
    private func teamRow(abbrev: String, score: Int?, prob: Int?, color: String?, isLeading: Bool) -> some View {
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

            Text(prob.map { "\($0)%" } ?? "")
                .font(.system(size: 12, weight: .semibold, design: .rounded).monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 32, alignment: .trailing)
        }
    }

    /// #5363 — the remainder segment survives a withheld away side (it is a true
    /// quantity, "not the home team") but loses the away team's colour, which is
    /// the rule the event page set in #5271.
    private func probabilityBar(homeProb: Int, homeColor: String?, awayColor: String?, awayIsWithheld: Bool) -> some View {
        GeometryReader { geo in
            HStack(spacing: 1) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(awayIsWithheld
                          ? Color.secondary.opacity(0.25)
                          : Color(hex: awayColor ?? "#666666").opacity(0.7))
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
            MediumDashboardContentView13162(
                liveGames: entry.dashboardGames13162,
                discoverItems: entry.dashboardMarkets13162
            )
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
            LargeDashboardContentView13162(
                liveGames: entry.dashboardGames13162,
                discoverItems: entry.dashboardMarkets13162
            )
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

private extension BainLuckWidgetEntry {
    var dashboardGames13162: [WidgetDashboardGameRow13162] {
        liveGames.map { game in
            WidgetDashboardGameRow13162(
                id: game.id,
                awayAbbrev: game.awayAbbrev,
                homeAbbrev: game.homeAbbrev,
                awayScore: game.awayScore,
                homeScore: game.homeScore,
                awayProb: game.awayProb,
                homeProb: game.homeProb,
                period: game.period,
                sport: game.sport,
                awayColorHex: game.awayColor,
                homeColorHex: game.homeColor,
                awayDarkColorHex: game.awayDarkColor,
                homeDarkColorHex: game.homeDarkColor
            )
        }
    }

    var dashboardMarkets13162: [WidgetDashboardMarketRow13162] {
        discoverItems.map { item in
            WidgetDashboardMarketRow13162(
                id: item.id,
                name: item.name,
                category: item.category,
                leader: item.leader,
                probability: item.probability,
                movement: item.movement
            )
        }
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
