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
                Text("\(game.awayScore ?? 0)")
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .frame(width: 24, alignment: .trailing)

                Text("–")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)

                Text("\(game.homeScore ?? 0)")
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .frame(width: 24, alignment: .leading)
                Text(game.homeAbbrev)
                    .font(.system(size: 12, weight: .bold))
                    .frame(width: 36, alignment: .trailing)

                Spacer()

                Text("\(game.awayProb)–\(game.homeProb)")
                    .font(.system(size: 10, weight: .medium).monospacedDigit())
                    .foregroundStyle(.secondary)
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
                // #2279 — WHICH SOURCE THE PROBABILITY CAME FROM DECIDES WHETHER
                // THE SERVED PERCENTS APPLY. The guard below falls back to
                // `openingOdds`, and the served percents describe `currentOdds`
                // and nothing else, so reading them on that branch would print
                // the current pair's rounding beside the OPENING pair's
                // probability. It still sums to 100, so no sum guard could see
                // it. Recorded at the branch that knows, not inferred afterwards.
                let odds = event.currentOdds
                let fromCurrentOdds = odds?.homeProbability != nil
                guard let homeProbability = odds?.homeProbability ?? event.openingOdds?.homeProbability else { return nil }
                let awayProbability = 1.0 - homeProbability
                // UX-P114 — the menu bar prints both sides, and derives away from
                // home right above, so it had the same 101. Prefer the server's
                // card-level percents; `renderedDuelPercents` covers a cached or
                // pre-deploy payload, and the openingOdds fallback in the guard
                // above, which the server does not decide percents for.
                //
                // #2279 — BOTH SERVED OR NEITHER. This site coalesced per side,
                // and it also carried a THIRD tier — `?? Int((p * 100).rounded())`
                // — that was a fourth, unshared implementation of the same
                // rounding, reachable only when the contract rule declines to
                // answer, and `Int(_:)` TRAPS on a non-finite Double. The pair
                // rule is now the last word: if it declines, the row is dropped
                // rather than re-derived by a copy nobody tests.
                let duel = duelPercents(
                    away: awayProbability,
                    home: homeProbability,
                    servedAway: fromCurrentOdds ? odds?.awayRenderedPercent : nil,
                    servedHome: fromCurrentOdds ? odds?.homeRenderedPercent : nil
                )
                guard let awayPct = duel[0], let homePct = duel[1] else { return nil }
                return MenuBarGame(
                    id: event.id,
                    homeAbbrev: event.homeTeamData?.abbreviation ?? TeamShortName.short(event.homeTeam),
                    awayAbbrev: event.awayTeamData?.abbreviation ?? TeamShortName.short(event.awayTeam),
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    homeProb: homePct,
                    awayProb: awayPct,
                    period: [event.espn?.period, event.espn?.gameClock].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " "),
                    sport: event.sportName ?? event.sport ?? ""
                )
            }
        } catch {}
        loading = false
    }
}

private struct MenuBarGame: Identifiable {
    let id: Int
    let homeAbbrev: String
    let awayAbbrev: String
    let homeScore: Int?
    let awayScore: Int?
    let homeProb: Int
    let awayProb: Int
    let period: String?
    let sport: String
}
#endif
