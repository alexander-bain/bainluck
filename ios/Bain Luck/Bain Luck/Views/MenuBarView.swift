#if os(macOS)
import SwiftUI

struct MenuBarView: View {
    @State private var liveGames: [MenuBarGame] = []
    @State private var loading = true

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if loading && liveGames.isEmpty {
                ProgressView()
                    .frame(width: 260, height: 60)
            } else if liveGames.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "sportscourt")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No upcoming games from your teams")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(width: 260, height: 60)
            } else {
                ForEach(liveGames) { game in
                    menuBarGameRow(game)
                    if game.id != liveGames.last?.id {
                        Divider()
                    }
                }
            }

            Divider()
            Button {
                if let url = URL(string: "bainluck://events") {
                    NSWorkspace.shared.open(url)
                }
            } label: {
                HStack {
                    Text("Open Bain Luck")
                        .font(.caption)
                    Spacer()
                    Text("⌘1")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
        }
        .padding(.vertical, 4)
        .task {
            await loadLiveGames()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                await loadLiveGames()
            }
        }
    }

    private func menuBarGameRow(_ game: MenuBarGame) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(game.sport)
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                Spacer()
                if let period = game.period {
                    Text(period)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.green)
                }
            }

            HStack {
                Text(game.awayAbbrev)
                    .font(.system(size: 12, weight: .bold))
                    .frame(width: 36, alignment: .leading)
                Text(game.awayScore.map(String.init) ?? "—")
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .frame(width: 24, alignment: .trailing)

                Text("–")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)

                Text(game.homeScore.map(String.init) ?? "—")
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .frame(width: 24, alignment: .leading)
                Text(game.homeAbbrev)
                    .font(.system(size: 12, weight: .bold))
                    .frame(width: 36, alignment: .trailing)

                Spacer()

                // #5363 — a draw-priced sport has no away number to print, and
                // "—–68" in a 10pt monospaced pair is not a legible absence, so
                // this row NAMES its survivor instead of holding the slot. The
                // abbreviation is already on the row, so the name costs nothing
                // a reader has not already read.
                if let homeProb = game.homeProb {
                    let chance = game.awayProb.map { "\($0)–\(homeProb)" }
                        ?? "\(game.homeAbbrev) \(homeProb)"
                    Text(chance)
                        .font(.system(size: 10, weight: .medium).monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .onTapGesture {
            if let url = URL(string: "bainluck://events/\(game.id)") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    private func loadLiveGames() async {
        do {
            let feed = try await APIClient.shared.fetchFeed(limit: 10, myTeamsOnly: true, includeFutures: false)
            liveGames = feed.items.compactMap { item -> MenuBarGame? in
                guard let event = item.event,
                      (event.status == "live" || event.status == "scheduled") else { return nil }
                let chance = Self.currentChancePercents(
                    odds: event.currentOdds,
                    heroSource: event.heroProbabilitySource,
                    sport: event.sport
                )
                // #3430 — both competitors of one matchup on one menu row, in
                // the least room any surface gives them.
                let menuSides = TeamShortName.shortPair(
                    away: event.awayTeam, home: event.homeTeam,
                    awayServed: event.awayTeamData?.abbreviation,
                    homeServed: event.homeTeamData?.abbreviation,
                    sportKey: event.sport
                )
                return MenuBarGame(
                    id: event.id,
                    homeAbbrev: menuSides.home,
                    awayAbbrev: menuSides.away,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    homeProb: chance.home,
                    awayProb: chance.away,
                    // #4880 — see `PeriodLabel.liveStatusText`.
                    period: PeriodLabel.liveStatusText(
                        period: event.espn?.period, gameClock: event.espn?.gameClock) ?? "",
                    sport: event.sportName ?? event.sport ?? ""
                )
            }
        } catch {}
        loading = false
    }

    /// A score row can survive a missing current chance or an older opening-only payload.
    static func currentChancePercents(
        odds: CurrentOdds?, heroSource: String?, sport: String?
    ) -> (home: Int?, away: Int?) {
        guard heroSource != OpeningLineHero.openingSource,
              let odds, let home = odds.homeProbability, (0...1).contains(home) else {
            return (nil, nil)
        }
        let away = 1 - home
        let printable = DrawPricedWinner.printablePair(away: away, home: home, sport: sport)
        let duel = duelPercents(
            away: away,
            home: home,
            servedAway: odds.awayRenderedPercent,
            servedHome: odds.homeRenderedPercent
        )
        let awayPct = duel[0]
        let homePct = duel[1]
        return (homePct, printable?.away == nil ? nil : awayPct)
    }
}

private struct MenuBarGame: Identifiable {
    let id: Int
    let homeAbbrev: String
    let awayAbbrev: String
    let homeScore: Int?
    let awayScore: Int?
    let homeProb: Int?
    /// #5363 — nil where the sport prices a draw and the complement is withheld.
    let awayProb: Int?
    let period: String?
    let sport: String
}
#endif
