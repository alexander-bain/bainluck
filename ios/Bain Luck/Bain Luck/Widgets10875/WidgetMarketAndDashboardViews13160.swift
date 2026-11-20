import Foundation
import SwiftUI

/// Shared widget subviews for saved-market Home/Lock Screen widgets (#13160, #13161)
/// and LiveGamesWidget Medium/Large dashboards (#13162), compiled into both `Bain Luck`
/// (for direct XCTest rendering + Vision OCR) and `BainLuckWidget`.
struct SavedMarketWidgetHeaderAndOutcome13161: View {
    let subject: String
    let isMediumFamily: Bool
    let headline: SavedWidgetReading10875.Row?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var subjectFontSize: CGFloat {
        let grows = dynamicTypeSize >= .xLarge
        if isMediumFamily {
            return grows ? 15.5 : 14.5
        }
        return grows ? 12.5 : 12.0
    }

    private var outcomeFontSize: CGFloat {
        let grows = dynamicTypeSize >= .xLarge
        if isMediumFamily {
            return grows ? 15.0 : 14.0
        }
        return grows ? 13.0 : 12.5
    }

    private var numberFontSize: CGFloat {
        isMediumFamily ? 30 : 24
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isMediumFamily ? 4 : 2) {
            Text(subject)
                .font(.system(size: subjectFontSize, weight: .semibold))
                .multilineTextAlignment(.leading)
                .lineLimit(isMediumFamily ? 2 : 3)
                .minimumScaleFactor(0.72)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            if let headline {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .lastTextBaseline, spacing: 6) {
                        outcomeName(headline.label, lineLimit: 1)
                            .fixedSize(horizontal: true, vertical: false)
                        Spacer(minLength: 4)
                        value(headline)
                            .fixedSize(horizontal: true, vertical: true)
                    }
                    VStack(alignment: .leading, spacing: 1) {
                        outcomeName(headline.label, lineLimit: 2)
                            .minimumScaleFactor(0.75)
                            .fixedSize(horizontal: false, vertical: true)
                        value(headline)
                            .fixedSize(horizontal: true, vertical: true)
                    }
                }
            }
        }
    }

    private func outcomeName(_ name: String, lineLimit: Int) -> some View {
        Text(name)
            .font(HeadlineStyleTable199.names(.widget, scaledSize: outcomeFontSize))
            .multilineTextAlignment(.leading)
            .lineLimit(lineLimit)
            .opacity(0.88)
    }

    private func value(_ row: SavedWidgetReading10875.Row) -> some View {
        Text(row.verdict ?? row.figure ?? "—")
            .font(HeadlineStyleTable199.now(.widget, scaledSize: numberFontSize))
            .lineLimit(1)
            .minimumScaleFactor(0.8)
    }
}

/// Lock Screen `.accessoryRectangular` (`157×66 pt`) layout for a saved market (#13160).
struct SavedMarketLockRectangleView13160: View {
    let shortSubject: String
    let headline: SavedWidgetReading10875.Row?
    let footer: String

    var body: some View {
        ViewThatFits(in: .vertical) {
            VStack(alignment: .leading, spacing: 1.5) {
                subjectView(fontSize: 10.5)
                outcomeRow(outcomeFontSize: 10.5, figureFontSize: 13.5, inlineFooter: false)
                footerLine
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            VStack(alignment: .leading, spacing: 1) {
                subjectView(fontSize: 10)
                outcomeRow(outcomeFontSize: 10, figureFontSize: 13, inlineFooter: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func subjectView(fontSize: CGFloat) -> some View {
        Text(shortSubject)
            .font(.system(size: fontSize, weight: .semibold))
            .multilineTextAlignment(.leading)
            .lineLimit(2)
            .minimumScaleFactor(0.68)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func outcomeRow(outcomeFontSize: CGFloat, figureFontSize: CGFloat, inlineFooter: Bool) -> some View {
        if let headline {
            HStack(alignment: inlineFooter ? .center : .firstTextBaseline, spacing: 4) {
                Text(headline.label)
                    .font(.system(size: outcomeFontSize, weight: .medium))
                    .multilineTextAlignment(.leading)
                    .lineLimit(2)
                    .minimumScaleFactor(0.70)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                if inlineFooter {
                    VStack(alignment: .trailing, spacing: 0) {
                        Text(headline.verdict ?? headline.figure ?? "—")
                            .font(.system(size: figureFontSize, weight: .bold).monospacedDigit())
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                        Text(footer)
                            .font(.system(size: 8.5))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.68)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                } else {
                    Text(headline.verdict ?? headline.figure ?? "—")
                        .font(.system(size: figureFontSize, weight: .bold).monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
        }
    }

    private var footerLine: some View {
        Text(footer)
            .font(.system(size: 9))
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .minimumScaleFactor(0.72)
    }
}

// MARK: - LiveGamesWidget Medium & Large Dashboard Shared Models & Views (#13162)

nonisolated struct WidgetDashboardGameRow13162: Identifiable, Equatable, Sendable {
    let id: Int
    let awayAbbrev: String
    let homeAbbrev: String
    let awayScore: Int?
    let homeScore: Int?
    let awayProb: Int?
    let homeProb: Int
    let period: String
    let sport: String
    let awayColorHex: String?
    let homeColorHex: String?
    let awayDarkColorHex: String?
    let homeDarkColorHex: String?

    func resolvedAwayColorHex(for colorScheme: ColorScheme) -> String {
        if colorScheme == .dark {
            return awayDarkColorHex
                ?? TeamTextContrast.usableOnDarkSurface(primaryHex: awayColorHex)
                ?? "#8E8E93"
        }
        return awayColorHex ?? "#666666"
    }

    func resolvedHomeColorHex(for colorScheme: ColorScheme) -> String {
        if colorScheme == .dark {
            return homeDarkColorHex
                ?? TeamTextContrast.usableOnDarkSurface(primaryHex: homeColorHex)
                ?? "#0A84FF"
        }
        return homeColorHex ?? "#0A84FF"
    }

    var awayIsLeading: Bool {
        guard let awayProb else { return false }
        return awayProb > homeProb
    }

    var homeIsLeading: Bool {
        guard let awayProb else { return false }
        return homeProb > awayProb
    }
}

nonisolated struct WidgetDashboardMarketRow13162: Identifiable, Equatable, Sendable {
    let id: Int
    let name: String
    let category: String
    let leader: String
    let probability: Int
    let movement: Int?
}

struct MediumDashboardContentView13162: View {
    let liveGames: [WidgetDashboardGameRow13162]
    let discoverItems: [WidgetDashboardMarketRow13162]
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        HStack(spacing: 10) {
            if !liveGames.isEmpty {
                liveGamesColumn
                    .frame(maxWidth: .infinity)
            }
            if !liveGames.isEmpty && !discoverItems.isEmpty {
                Divider()
                    .padding(.vertical, 6)
            }
            if !discoverItems.isEmpty {
                discoverColumn
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(12)
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
            .padding(.bottom, 5)

            ForEach(Array(liveGames.prefix(3).enumerated()), id: \.element.id) { index, game in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3)
                }
                compactGameRow(game)
            }

            Spacer(minLength: 0)
        }
    }

    private func compactGameRow(_ game: WidgetDashboardGameRow13162) -> some View {
        Link(destination: URL(string: "bainluck://events/\(game.id)")!) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(game.period.isEmpty ? game.sport.uppercased() : "\(game.sport.uppercased()) · \(game.period)")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(game.period.isEmpty ? Color.secondary : Color.green)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Spacer(minLength: 4)
                    Text(game.awayProb.map { "\($0)%–\(game.homeProb)%" }
                         ?? "\(game.homeAbbrev) \(game.homeProb)%")
                        .font(.system(size: 8, weight: .medium, design: .rounded).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }

                HStack(spacing: 4) {
                    Circle()
                        .fill(Color(hex: game.resolvedAwayColorHex(for: colorScheme)))
                        .frame(width: 5, height: 5)
                    Text(game.awayAbbrev)
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Spacer(minLength: 2)
                    Text("\(game.awayScore ?? 0)")
                        .font(.system(size: 11.5, weight: .heavy, design: .rounded).monospacedDigit())
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    Text("–")
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                        .fixedSize()

                    Text("\(game.homeScore ?? 0)")
                        .font(.system(size: 11.5, weight: .heavy, design: .rounded).monospacedDigit())
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Spacer(minLength: 2)
                    Text(game.homeAbbrev)
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Circle()
                        .fill(Color(hex: game.resolvedHomeColorHex(for: colorScheme)))
                        .frame(width: 5, height: 5)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var discoverColumn: some View {
        let maxItems = liveGames.isEmpty ? 3 : 2
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 8))
                    .foregroundStyle(.secondary)
                Text("DISCOVER")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.bottom, 5)

            ForEach(Array(discoverItems.prefix(maxItems).enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3)
                }
                compactDiscoverRow(item)
            }

            Spacer(minLength: 0)
        }
    }

    private func compactDiscoverRow(_ item: WidgetDashboardMarketRow13162) -> some View {
        Link(destination: URL(string: "bainluck://futures/\(item.id)")!) {
            VStack(alignment: .leading, spacing: 1.5) {
                Text(item.category.uppercased())
                    .font(.system(size: 7.5, weight: .bold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                HStack(alignment: .top, spacing: 4) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.leader)
                            .font(.system(size: 10.5, weight: .semibold))
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(2)
                            .minimumScaleFactor(0.72)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(item.name)
                            .font(.system(size: 8.5))
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(2)
                            .minimumScaleFactor(0.68)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    VStack(alignment: .trailing, spacing: 1) {
                        Text("\(item.probability)%")
                            .font(.system(size: 12.5, weight: .heavy, design: .rounded).monospacedDigit())
                            .foregroundStyle(.primary)
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
        .buttonStyle(.plain)
    }
}

struct LargeDashboardContentView13162: View {
    let liveGames: [WidgetDashboardGameRow13162]
    let discoverItems: [WidgetDashboardMarketRow13162]
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !liveGames.isEmpty {
                liveGamesSection
            }
            if !liveGames.isEmpty && !discoverItems.isEmpty {
                Divider()
                    .padding(.vertical, 6)
            }
            if !discoverItems.isEmpty {
                discoverSection
            }
            Spacer(minLength: 0)
        }
        .padding(14)
    }

    private var liveGamesSection: some View {
        let maxGames = discoverItems.isEmpty ? 5 : 3
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "circle.fill")
                    .font(.system(size: 5))
                    .foregroundStyle(.green)
                Text("LIVE GAMES")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.green)
                Spacer()
                Text("\(liveGames.count) game\(liveGames.count == 1 ? "" : "s")")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .padding(.bottom, 6)

            ForEach(Array(liveGames.prefix(maxGames).enumerated()), id: \.element.id) { index, game in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3)
                }
                largeGameRow(game)
            }
        }
    }

    private func largeGameRow(_ game: WidgetDashboardGameRow13162) -> some View {
        Link(destination: URL(string: "bainluck://events/\(game.id)")!) {
            HStack(spacing: 8) {
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.resolvedAwayColorHex(for: colorScheme)))
                        .frame(width: 4, height: 24)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(game.awayAbbrev)
                            .font(.system(size: 12.5, weight: game.awayIsLeading ? .bold : .medium))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                        Text(game.awayProb.map { "\($0)%" } ?? "")
                            .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .frame(minWidth: 38, alignment: .leading)
                }

                HStack(spacing: 4) {
                    Text("\(game.awayScore ?? 0)")
                        .font(.system(size: 15, weight: .heavy, design: .rounded).monospacedDigit())
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: 24, alignment: .trailing)
                    Text("–")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .fixedSize()
                    Text("\(game.homeScore ?? 0)")
                        .font(.system(size: 15, weight: .heavy, design: .rounded).monospacedDigit())
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: 24, alignment: .leading)
                }

                HStack(spacing: 6) {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(game.homeAbbrev)
                            .font(.system(size: 12.5, weight: game.homeIsLeading ? .bold : .medium))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                        Text("\(game.homeProb)%")
                            .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .frame(minWidth: 38, alignment: .trailing)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: game.resolvedHomeColorHex(for: colorScheme)))
                        .frame(width: 4, height: 24)
                }

                Spacer(minLength: 4)

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
                            .minimumScaleFactor(0.75)
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var discoverSection: some View {
        let maxMarkets = liveGames.isEmpty ? 5 : 3
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                Text("TRENDING")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.bottom, 6)

            ForEach(Array(discoverItems.prefix(maxMarkets).enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                        .padding(.vertical, 3.5)
                }
                largeDiscoverRow(item)
            }
        }
    }

    private func largeDiscoverRow(_ item: WidgetDashboardMarketRow13162) -> some View {
        Link(destination: URL(string: "bainluck://futures/\(item.id)")!) {
            HStack(spacing: 8) {
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
                        .font(.system(size: 11.5, weight: .semibold))
                        .foregroundStyle(.primary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                        .minimumScaleFactor(0.75)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(item.name)
                        .font(.system(size: 9.5))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                        .minimumScaleFactor(0.72)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(alignment: .trailing, spacing: 1) {
                    Text("\(item.probability)%")
                        .font(.system(size: 14, weight: .heavy, design: .rounded).monospacedDigit())
                        .foregroundStyle(.primary)
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
        .buttonStyle(.plain)
    }
}
