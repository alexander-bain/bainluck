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
                    } else {
                        marqueeEmpty
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

    /// Explicit, stable marquee empty state. L2-200: previously the marquee area
    /// simply vanished when no item was renderable (no `if-let` else), leaving the
    /// primary story slot blank. Reuses the established empty-card pattern
    /// (`emptyTeams`) — factual copy, no new visual language.
    private var marqueeEmpty: some View {
        Text("No top story right now")
            .font(.system(size: 12))
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
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

// The marquee/my-teams value types (`WatchTopStory`, `WatchProbSplit`,
// `WatchStoryBadge`, `WatchTeamGame`) live in `WatchMarquee.swift` alongside the
// pure selection logic (L2-200).

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
            topStory = WatchMarquee.marquee(from: feed.items)
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
                    myGames = WatchMarquee.teamGames(from: myFeed.items)
                }
            } catch {
                logger.error("My-teams load failed: \(error.localizedDescription)")
            }
        } else {
            myGames = []
        }
    }

    // MARK: Feed → story selection
    //
    // The pure marquee/my-teams selection (`WatchMarquee.marquee`/`teamGames`)
    // and its value types live in `WatchMarquee.swift` (Foundation + SwiftUI only)
    // so they compile into the iOS test bundle and are exercised directly (L2-200,
    // mirroring `WatchGuessPool`). This view model just calls them from `load()`.
}
