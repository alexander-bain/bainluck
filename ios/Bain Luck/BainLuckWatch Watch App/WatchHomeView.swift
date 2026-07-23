import Combine
import os.log
import SwiftUI
import WatchKit

private let logger = Logger(subsystem: "com.bainluck.watch", category: "Home")

// MARK: - The Glance (watch home)
//
// P7's top secondary surface, v1: probability-first, wrist-legible, two sections.
//   1. THE MARQUEE — the feed's top story now (live/just-settled game or the
//      leading futures market), title + THE NUMBER on one glanceable card.
//   2. MY TEAMS — next/live game per followed team with the win-prob split.
//      Auth-gated: shows a graceful signed-out prompt until the phone→watch
//      token bridge lands (see WatchAuthStore).

struct WatchHomeView: View {
    @StateObject private var vm = WatchHomeViewModel()

    var body: some View {
        ScrollView {
            if vm.loading && vm.topStory == nil {
                loadingState
            } else if let error = vm.error, vm.topStory == nil {
                errorState(error)
            } else {
                VStack(spacing: 10) {
                    if let story = vm.topStory {
                        marqueeCard(story)
                    }
                    myTeamsSection
                    if let ago = vm.lastUpdated {
                        Text(ago)
                            .font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 2)
                    }
                }
                .padding(.horizontal, 4)
            }
        }
        .navigationTitle("🍀 Bain Luck")
        .task { await vm.load() }
        .task(id: "home-refresh") {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                await vm.load(force: true)
            }
        }
    }

    // MARK: Marquee

    private func marqueeCard(_ story: WatchTopStory) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                badgeView(story.badge, clock: story.clock)
                Spacer(minLength: 2)
                if let category = story.categoryLabel {
                    Text(category)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                }
            }

            Text(story.title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.secondary)
                .lineLimit(2)

            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(story.bigLabel)
                    .font(.system(size: 17, weight: .bold))
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                Spacer(minLength: 2)
                Text("\(story.bigNumber)%")
                    .font(.system(size: 40, weight: .heavy, design: .rounded))
                    .foregroundStyle(story.accentColor)
                    .minimumScaleFactor(0.7)
                    .lineLimit(1)
            }

            if let split = story.split {
                splitBar(split)
            }

            if let headline = story.headline, !headline.isEmpty {
                Text(headline)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private func badgeView(_ badge: WatchStoryBadge, clock: String?) -> some View {
        switch badge {
        case .live:
            HStack(spacing: 4) {
                Circle().fill(.red).frame(width: 6, height: 6)
                Text(clock.map { "LIVE · \($0)" } ?? "LIVE")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.red)
            }
        case .final:
            Text("FINAL")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
        case .soon:
            Text("SOON")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.orange)
        case .none:
            Text("TOP STORY")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
        }
    }

    private func splitBar(_ split: WatchProbSplit) -> some View {
        VStack(spacing: 3) {
            GeometryReader { geo in
                HStack(spacing: 1) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: split.leftColor ?? "#888"))
                        .frame(width: max(2, geo.size.width * CGFloat(split.leftPct) / 100))
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(hex: split.rightColor ?? "#888"))
                }
            }
            .frame(height: 4)

            HStack {
                Text("\(split.leftAbbr) \(split.leftPct)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(split.rightPct) \(split.rightAbbr)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: My Teams

    private var myTeamsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("MY TEAMS")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)

            if !vm.signedIn {
                signedOutTeams
            } else if vm.myGames.isEmpty {
                emptyTeams
            } else {
                ForEach(vm.myGames) { game in
                    teamGameRow(game)
                }
            }
        }
        .padding(.top, 2)
    }

    private var signedOutTeams: some View {
        VStack(spacing: 4) {
            Image(systemName: "iphone")
                .font(.system(size: 18))
                .foregroundStyle(.secondary)
            Text("Sign in on your iPhone to follow teams")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var emptyTeams: some View {
        Text("No upcoming games for your teams")
            .font(.system(size: 11))
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(Color.white.opacity(0.05))
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func teamGameRow(_ game: WatchTeamGame) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Text(game.matchup)
                    .font(.system(size: 12, weight: .semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Spacer(minLength: 2)
                if game.live {
                    HStack(spacing: 3) {
                        Circle().fill(.red).frame(width: 5, height: 5)
                        Text(game.clock ?? "LIVE")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.red)
                    }
                } else if let when = game.startText {
                    Text(when)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            }
            splitBar(game.split)
        }
        .padding(8)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: Placeholder states

    private var loadingState: some View {
        VStack(spacing: 10) {
            ProgressView().scaleEffect(1.3)
            Text("Loading...")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.secondary)
        }
        .padding(.top, 24)
    }

    private func errorState(_ error: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "wifi.exclamationmark")
                .font(.title3)
                .foregroundStyle(.orange)
            Text(error)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
            Button("Retry") { Task { await vm.load(force: true) } }
                .font(.system(size: 13, weight: .semibold))
        }
        .padding(.top, 24)
    }
}

// MARK: - View Models / value types

enum WatchStoryBadge {
    case live, final, soon, none
}

struct WatchProbSplit {
    let leftAbbr: String
    let leftPct: Int
    let leftColor: String?
    let rightAbbr: String
    let rightPct: Int
    let rightColor: String?
}

struct WatchTopStory: Identifiable {
    let id: String
    let badge: WatchStoryBadge
    let clock: String?
    let categoryLabel: String?
    let title: String
    let bigLabel: String
    let bigNumber: Int
    let headline: String?
    let split: WatchProbSplit?

    var accentColor: Color {
        switch badge {
        case .live: return .green
        case .final: return .secondary
        default: return .blue
        }
    }
}

struct WatchTeamGame: Identifiable {
    let id: Int
    let matchup: String
    let split: WatchProbSplit
    let live: Bool
    let clock: String?
    let startText: String?
}

@MainActor
final class WatchHomeViewModel: ObservableObject {
    @Published var topStory: WatchTopStory?
    @Published var myGames: [WatchTeamGame] = []
    @Published var signedIn = WatchAuthStore.shared.isSignedIn
    @Published var loading = true
    @Published var error: String?
    @Published var lastUpdated: String?

    func load(force: Bool = false) async {
        logger.info("Home load started (force=\(force))")
        if topStory == nil { loading = true }
        error = nil
        defer { loading = false }

        signedIn = WatchAuthStore.shared.isSignedIn

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 10, forceRefresh: force)
            topStory = Self.marquee(from: feed.items)
            logger.info("Home marquee: \(self.topStory?.title ?? "none")")
            if let t = await WatchAPIClient.shared.lastFetchTime {
                let ago = Int(Date().timeIntervalSince(t))
                lastUpdated = ago < 5 ? "Just now" : "\(ago)s ago"
            }
            WKInterfaceDevice.current().play(.click)
        } catch {
            logger.error("Home load failed: \(error.localizedDescription)")
            if topStory == nil { self.error = "Couldn't load" }
        }

        // My-teams strip (auth-gated; nil response => stay signed-out/empty).
        if signedIn {
            do {
                if let myFeed = try await WatchAPIClient.shared.fetchMyTeamsFeed(limit: 6) {
                    myGames = Self.teamGames(from: myFeed.items)
                }
            } catch {
                logger.error("My-teams load failed: \(error.localizedDescription)")
            }
        } else {
            myGames = []
        }
    }

    // MARK: Marquee selection

    /// The top story is the first live game if one is near the top, else the
    /// feed's #1 ranked item (the server already pins marquee majors to the front).
    static func marquee(from items: [WatchFeedItem]) -> WatchTopStory? {
        let topLive = items.first { $0.event?.isLive == true }
        guard let item = topLive ?? items.first else { return nil }

        if let e = item.event, let home = e.currentOdds?.homeProbability {
            return eventStory(item, e, homeProb: home)
        }
        if let f = item.futures, let leader = f.topOutcomes?.first, let p = leader.probability {
            let pct = Self.pct(p)
            return WatchTopStory(
                id: item.id,
                badge: .none,
                clock: nil,
                categoryLabel: f.llmSportCategory,
                title: f.name,
                bigLabel: Self.shortName(leader.name),
                bigNumber: pct,
                headline: item.headline,
                split: nil
            )
        }
        return nil
    }

    private static func eventStory(_ item: WatchFeedItem, _ e: WatchFeedEvent, homeProb: Double) -> WatchTopStory {
        let homePct = Self.pct(homeProb)
        let awayPct = 100 - homePct
        let homeAbbr = e.homeAbbrev()
        let awayAbbr = e.awayAbbrev()
        let homeLeads = homePct >= awayPct
        let badge: WatchStoryBadge = e.isLive ? .live : (e.isSettled ? .final : .soon)

        return WatchTopStory(
            id: item.id,
            badge: badge,
            clock: e.clockText,
            categoryLabel: e.sportName ?? e.sport,
            title: "\(awayAbbr) @ \(homeAbbr)",
            bigLabel: homeLeads ? homeAbbr : awayAbbr,
            bigNumber: max(homePct, awayPct),
            headline: item.headline,
            split: WatchProbSplit(
                leftAbbr: awayAbbr, leftPct: awayPct, leftColor: e.awayTeamData?.primaryColor,
                rightAbbr: homeAbbr, rightPct: homePct, rightColor: e.homeTeamData?.primaryColor
            )
        )
    }

    // MARK: My-teams mapping

    static func teamGames(from items: [WatchFeedItem]) -> [WatchTeamGame] {
        items.compactMap { item -> WatchTeamGame? in
            guard let e = item.event, let home = e.currentOdds?.homeProbability else { return nil }
            let homePct = Self.pct(home)
            let awayPct = 100 - homePct
            let homeAbbr = e.homeAbbrev()
            let awayAbbr = e.awayAbbrev()
            return WatchTeamGame(
                id: e.id,
                matchup: "\(awayAbbr) @ \(homeAbbr)",
                split: WatchProbSplit(
                    leftAbbr: awayAbbr, leftPct: awayPct, leftColor: e.awayTeamData?.primaryColor,
                    rightAbbr: homeAbbr, rightPct: homePct, rightColor: e.homeTeamData?.primaryColor
                ),
                live: e.isLive,
                clock: e.clockText,
                startText: e.isLive ? nil : Self.startText(e.commenceTime)
            )
        }
    }

    // MARK: Helpers

    static func pct(_ p: Double) -> Int { Int((p * 100).rounded()) }

    static func shortName(_ name: String) -> String {
        name.count <= 16 ? name : String(name.prefix(15)) + "…"
    }

    /// Short "today 7:30 PM" / weekday time from an ISO8601 commence time.
    static func startText(_ iso: String?) -> String? {
        guard let iso, let date = isoFormatter.date(from: iso) ?? isoFormatterNoFraction.date(from: iso) else {
            return nil
        }
        let cal = Calendar.current
        let time = timeFormatter.string(from: date)
        if cal.isDateInToday(date) { return time }
        if cal.isDateInTomorrow(date) { return "Tmrw \(time)" }
        return "\(weekdayFormatter.string(from: date)) \(time)"
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoFormatterNoFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()
    private static let weekdayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f
    }()
}
