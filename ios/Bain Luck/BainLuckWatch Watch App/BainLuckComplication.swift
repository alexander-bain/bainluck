import WidgetKit
import SwiftUI

struct BainLuckEntry: TimelineEntry {
    let date: Date
    let streak: Int
    let topMarket: ComplicationMarket?
    let liveGame: ComplicationGame?
}

struct ComplicationMarket {
    let name: String
    let leader: String
    let probability: Int
    let movement: Int
}

struct ComplicationGame {
    let homeAbbrev: String
    let awayAbbrev: String
    let homeProb: Int
    let homeScore: Int?
    let awayScore: Int?
    let homeColor: String
    let awayColor: String
}

struct BainLuckProvider: TimelineProvider {
    func placeholder(in context: Context) -> BainLuckEntry {
        BainLuckEntry(
            date: Date(),
            streak: 5,
            topMarket: ComplicationMarket(name: "NBA Champion", leader: "Celtics", probability: 32, movement: 3),
            liveGame: nil
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (BainLuckEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BainLuckEntry>) -> Void) {
        Task {
            let entry = await fetchEntry()
            let nextUpdate = Calendar.current.date(byAdding: .minute, value: 15, to: Date())!
            completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
        }
    }

    private func fetchEntry() async -> BainLuckEntry {
        do {
            // L2-179: widen the scan. The complication picks the first live game
            // and first market; a marquee concept/tournament pinned atop the feed
            // can push both past a limit:10 window, leaving a bare placeholder
            // despite usable later stories.
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 20)

            var topMarket: ComplicationMarket?
            var liveGame: ComplicationGame?

            for item in feed.items {
                if liveGame == nil, let e = item.event, e.status == "live",
                   let prob = e.currentOdds?.homeProbability {
                    let homeTeam = e.homeTeam ?? "Home"
                    let awayTeam = e.awayTeam ?? "Away"
                    let homeAbbrev = e.homeTeamData?.abbreviation ?? String(homeTeam.split(separator: " ").last ?? "")
                    let awayAbbrev = e.awayTeamData?.abbreviation ?? String(awayTeam.split(separator: " ").last ?? "")
                    liveGame = ComplicationGame(
                        homeAbbrev: homeAbbrev,
                        awayAbbrev: awayAbbrev,
                        homeProb: Int((prob * 100).rounded()),
                        homeScore: e.homeScore,
                        awayScore: e.awayScore,
                        homeColor: e.homeTeamData?.primaryColor ?? "#0A84FF",
                        awayColor: e.awayTeamData?.primaryColor ?? "#FF453A"
                    )
                }
                // L2-225: the complication is the longest-lived surface on the
                // wrist — its timeline is cached, so a settled market picked here
                // sits on the watch face showing a live number and a movement delta.
                if topMarket == nil, let f = item.futures, !f.isSettled(),
                   let leader = f.topOutcomes?.first, let prob = leader.probability {
                    topMarket = ComplicationMarket(
                        name: f.name,
                        leader: leader.name,
                        probability: Int((prob * 100).rounded()),
                        movement: Int(((leader.movement ?? 0) * 100).rounded())
                    )
                }
                if topMarket != nil && liveGame != nil { break }
            }

            let stats = try? await WatchAPIClient.shared.fetchPredictionStats()

            return BainLuckEntry(
                date: Date(),
                streak: stats?.currentStreak ?? 0,
                topMarket: topMarket,
                liveGame: liveGame
            )
        } catch {
            return BainLuckEntry(date: Date(), streak: 0, topMarket: nil, liveGame: nil)
        }
    }
}

struct BainLuckComplicationView: View {
    let entry: BainLuckEntry
    @Environment(\.widgetFamily) var family

    var body: some View {
        switch family {
        case .accessoryCircular:
            circularView
        case .accessoryRectangular:
            rectangularView
        case .accessoryCorner:
            cornerView
        case .accessoryInline:
            inlineView
        default:
            circularView
        }
    }

    private var circularView: some View {
        ZStack {
            AccessoryWidgetBackground()
            if let game = entry.liveGame {
                VStack(spacing: 0) {
                    Text("\(game.awayAbbrev)-\(game.homeAbbrev)")
                        .font(.system(size: 9, weight: .bold))
                    Text("\(game.homeProb)%")
                        .font(.system(size: 16, weight: .heavy, design: .rounded))
                }
            } else if entry.streak > 0 {
                VStack(spacing: 0) {
                    Text("\u{1F525}")
                        .font(.system(size: 12))
                    Text("\(entry.streak)")
                        .font(.system(size: 18, weight: .heavy, design: .rounded))
                }
            } else {
                Image(systemName: "chart.bar.fill")
                    .font(.title3)
            }
        }
    }

    private var rectangularView: some View {
        HStack {
            if let game = entry.liveGame {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(game.awayAbbrev) vs \(game.homeAbbrev)")
                        .font(.system(size: 12, weight: .bold))
                    if let hs = game.homeScore, let as_ = game.awayScore {
                        Text("\(as_)-\(hs)")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Text("\(game.homeProb)%")
                    .font(.system(size: 18, weight: .heavy, design: .rounded))
            } else if let market = entry.topMarket {
                VStack(alignment: .leading, spacing: 2) {
                    Text(market.leader)
                        .font(.system(size: 12, weight: .bold))
                    Text(market.name)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
                VStack(alignment: .trailing) {
                    Text("\(market.probability)%")
                        .font(.system(size: 16, weight: .heavy, design: .rounded))
                    if market.movement != 0 {
                        Text("\(market.movement > 0 ? "+" : "")\(market.movement)")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(market.movement > 0 ? .green : .red)
                    }
                }
            } else {
                Text("Bain Luck")
                    .font(.system(size: 12, weight: .bold))
                Spacer()
                if entry.streak > 0 {
                    Text("\u{1F525} \(entry.streak)")
                        .font(.system(size: 14, weight: .bold))
                }
            }
        }
    }

    @ViewBuilder
    private var cornerView: some View {
        if let game = entry.liveGame {
            Text("\(game.homeProb)%")
                .font(.system(size: 20, weight: .heavy, design: .rounded))
                .widgetLabel("\(game.awayAbbrev) vs \(game.homeAbbrev)")
        } else if let market = entry.topMarket {
            Text("\(market.probability)%")
                .font(.system(size: 20, weight: .heavy, design: .rounded))
                .widgetLabel(market.leader)
        } else {
            Image(systemName: "chart.bar.fill")
                .widgetLabel("Bain Luck")
        }
    }

    @ViewBuilder
    private var inlineView: some View {
        if let game = entry.liveGame {
            Text("\(game.awayAbbrev) \(game.awayScore ?? 0)-\(game.homeScore ?? 0) \(game.homeAbbrev) | \(game.homeProb)%")
        } else if let market = entry.topMarket {
            Text("\(market.leader) \(market.probability)%")
        } else if entry.streak > 0 {
            Text("\u{1F525} \(entry.streak) streak")
        } else {
            Text("Bain Luck")
        }
    }
}

@main
struct BainLuckWidget: Widget {
    let kind = "BainLuckComplication"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: BainLuckProvider()) { entry in
            BainLuckComplicationView(entry: entry)
        }
        .configurationDisplayName("Bain Luck")
        .description("Live odds, game probabilities, and your guess streak.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryCorner,
            .accessoryInline,
        ])
    }
}
