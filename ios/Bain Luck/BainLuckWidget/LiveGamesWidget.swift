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
    @Environment(\.colorScheme) private var colorScheme

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
                        .padding(.horizontal, 6)
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
                HStack(spacing: 4) {
                    Text(game.sport.uppercased())
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    if !game.period.isEmpty {
                        Text(game.period)
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(.green)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    Spacer(minLength: 2)
                    // #5363 + #13162: keep probability pair on one uncut line ("93-7"), never wrapping onto "-7".
                    Text(game.awayProb.map { "\($0)-\(game.homeProb)" }
                         ?? "\(game.homeAbbrev) \(game.homeProb)")
                        .font(.system(size: 9, weight: .medium, design: .rounded).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }

                HStack(spacing: 3) {
                    // Team color dot
                    Circle()
                        .fill(Color(hex: game.resolvedAwayColor(for: colorScheme) ?? "#666666"))
                        .frame(width: 6, height: 6)
                    Text(game.awayAbbrev)
                        .font(.system(size: 11, weight: .medium))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text("\(game.awayScore ?? 0)")
                        .font(.system(size: 11, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    Text("-")
                        .font(.system(size: 8))
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    Text("\(game.homeScore ?? 0)")
                        .font(.system(size: 11, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text(game.homeAbbrev)
                        .font(.system(size: 11, weight: .medium))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Circle()
                        .fill(Color(hex: game.resolvedHomeColor(for: colorScheme) ?? "#0A84FF"))
                        .frame(width: 6, height: 6)

                    Spacer(minLength: 0)
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
                    .lineLimit(1)
                Spacer()
            }
            .padding(.bottom, 6)

            // #13162: show as many Discover rows as fit whole with wrapped headlines (never "…").
            ViewThatFits(in: .vertical) {
                compactDiscoverList(count: 3, leaderSize: 10.5, nameSize: 9)
                compactDiscoverList(count: 2, leaderSize: 10.5, nameSize: 9)
                compactDiscoverList(count: 1, leaderSize: 10.5, nameSize: 9)
                compactDiscoverList(count: 1, leaderSize: 9.5, nameSize: 8.5)
            }

            Spacer(minLength: 0)
        }
    }

    private func compactDiscoverList(count: Int, leaderSize: CGFloat, nameSize: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(entry.discoverItems.prefix(count).enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3)
                }
                compactDiscoverRow(item, leaderSize: leaderSize, nameSize: nameSize)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func compactDiscoverRow(_ item: WidgetDiscoverItem, leaderSize: CGFloat, nameSize: CGFloat) -> some View {
        Link(destination: URL(string: "bainluck://futures/\(item.id)")!) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.category.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                HStack(alignment: .top, spacing: 4) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.leader)
                            .font(.system(size: leaderSize, weight: .semibold))
                            .multilineTextAlignment(.leading)
                            .lineLimit(nil)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(item.name)
                            .font(.system(size: nameSize))
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(nil)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 4)

                    VStack(alignment: .trailing, spacing: 1) {
                        Text("\(item.probability)%")
                            .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)

                        if let movement = item.movement, movement != 0 {
                            Text("\(movement > 0 ? "+" : "")\(movement)")
                                .font(.system(size: 8, weight: .semibold, design: .rounded))
                                .foregroundStyle(movement > 0 ? .green : .red)
                                .lineLimit(1)
                                .fixedSize(horizontal: true, vertical: false)
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
    @Environment(\.colorScheme) private var colorScheme

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
                        .fill(Color(hex: game.resolvedAwayColor(for: colorScheme) ?? "#666666"))
                        .frame(width: 4, height: 24)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(game.awayAbbrev)
                            .font(.system(size: 13, weight: game.awayIsLeading ? .bold : .medium))
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                        // #5363 — withheld on a draw-priced sport.
                        Text(game.awayProb.map { "\($0)%" } ?? "")
                            .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .frame(minWidth: 38, alignment: .leading)
                }

                // Score (#13162: never cap width below two/three heavy digits)
                HStack(spacing: 4) {
                    Text("\(game.awayScore ?? 0)")
                        .font(.system(size: 15, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: 24, alignment: .trailing)
                    Text("-")
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text("\(game.homeScore ?? 0)")
                        .font(.system(size: 15, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: 24, alignment: .leading)
                }

                // Home team
                HStack(spacing: 6) {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(game.homeAbbrev)
                            .font(.system(size: 13, weight: game.homeIsLeading ? .bold : .medium))
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                        Text("\(game.homeProb)%")
                            .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .frame(minWidth: 38, alignment: .trailing)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.resolvedHomeColor(for: colorScheme) ?? "#0A84FF"))
                        .frame(width: 4, height: 24)
                }

                Spacer(minLength: 4)

                // Sport + period
                VStack(alignment: .trailing, spacing: 2) {
                    Text(game.sport.uppercased())
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    if !game.period.isEmpty {
                        Text(game.period)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.green)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
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
                    .lineLimit(1)
                Spacer()
            }
            .padding(.bottom, 8)

            // #13162: show as many Trending rows as fit whole with wrapped market headlines (never "…").
            ViewThatFits(in: .vertical) {
                largeDiscoverList(count: 5)
                largeDiscoverList(count: 4)
                largeDiscoverList(count: 3)
                largeDiscoverList(count: 2)
                largeDiscoverList(count: 1)
            }
        }
    }

    private func largeDiscoverList(count: Int) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(entry.discoverItems.prefix(count).enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 4)
                }
                largeDiscoverRow(item)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func largeDiscoverRow(_ item: WidgetDiscoverItem) -> some View {
        Link(destination: URL(string: "bainluck://futures/\(item.id)")!) {
            HStack(alignment: .top, spacing: 8) {
                // Category pill
                Text(item.category.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.6), in: Capsule())

                VStack(alignment: .leading, spacing: 1) {
                    Text(item.leader)
                        .font(.system(size: 12, weight: .semibold))
                        .multilineTextAlignment(.leading)
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(item.name)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 4)

                VStack(alignment: .trailing, spacing: 1) {
                    Text("\(item.probability)%")
                        .font(.system(size: 14, weight: .heavy, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    if let movement = item.movement, movement != 0 {
                        Text("\(movement > 0 ? "+" : "")\(movement)")
                            .font(.system(size: 9, weight: .semibold, design: .rounded))
                            .foregroundStyle(movement > 0 ? .green : .red)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
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
