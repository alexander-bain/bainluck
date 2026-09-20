import SwiftUI

/// #7036, fourth arm — the team page's own 64pt identity tile, resolved through
/// the contrast floor.
///
/// The tile is `.fill(Color(hex: primaryColor))` with
/// `.overlay(Text(abbreviation).foregroundStyle(.white))`, so the letters are
/// WHITE and the fill is the club's. That is the same judgement as a colour
/// painted as text on a white card and not a second one: the pair being weighed
/// is (white, colour) in both directions, so `(1.05)/(L + 0.05)` is the same
/// ratio and `TeamTextContrast`'s floor answers it unchanged.
///
/// **What this is reachable BY, measured rather than inferred (2026-09-20).** The
/// tile is `AsyncImage`'s `placeholder:`, so it is on screen while the crest
/// loads and stays on screen when the fetch fails — it is not the state of a
/// club that has no crest. There are no such clubs: `teams` holds **0** rows
/// with a `primary_color` and no logo url. So this is the FAILURE path, and what
/// it fixes is that for the 146 clubs under 3:1 the fallback was itself blank.
/// A fallback that exists to survive a dead image, and is invisible for one club
/// in ten, is not a fallback. Do not restate this as "Fulham's team page is
/// blank" — Fulham's crest returns 200.
///
/// `#6B7280` (4.83:1) is the fill this view already used for a team with no
/// stored colour.
enum TeamDetailTeamColour {
    static let fallbackHex = "#6B7280"

    static func logoTileHex(_ storedHex: String?) -> String {
        TeamTextContrast.textHexOnCard(storedHex, fallback: fallbackHex)
    }
}

struct TeamDetailView: View {
    let slug: String

    @State private var data: TeamPageResponse?
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        Group {
            if loading {
                ProgressView()
            } else if let error {
                ContentUnavailableView("Team Not Found", systemImage: "person.crop.circle.badge.questionmark", description: Text(error))
            } else if let data {
                teamContent(data)
            }
        }
        .onAppear { AnalyticsService.trackScreen(name: "team_\(slug)", type: "team") }
        .task { await loadTeam() }
    }

    @MainActor
    private func loadTeam() async {
        do {
            data = try await APIClient.shared.fetchTeamPage(slug: slug)
            loading = false
        } catch {
            self.error = "Could not load team"
            loading = false
        }
    }

    private func teamContent(_ data: TeamPageResponse) -> some View {
        let team = data.team
        return List {
            // Hero
            Section {
                HStack(spacing: 16) {
                    if let logo = team.logoLarge ?? team.logoSmall, let url = URL(string: logo) {
                        AsyncImage(url: url) { image in
                            image.resizable().scaledToFit()
                        } placeholder: {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color(hex: TeamDetailTeamColour.logoTileHex(team.primaryColor)))
                                // #4720 — the served abbreviation still wins; the
                                // FALLBACK was one raw character ("1" for
                                // "1. FC Heidenheim 1846") and is now the app's badge.
                                .overlay(Text(team.abbreviation ?? TeamShortName.abbreviation(team.name)).font(.title2).bold().foregroundStyle(.white))
                        }
                        .frame(width: 64, height: 64)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text(team.name).font(.title2).bold()
                        HStack(spacing: 8) {
                            if let record = team.record {
                                Text(record).font(.subheadline).foregroundStyle(.secondary)
                            }
                            if let sport = team.sportName {
                                Text(sport).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }

            // Championship Path
            if !data.championshipPath.isEmpty {
                Section("Championship Path") {
                    ForEach(data.championshipPath) { entry in
                        NavigationLink(value: Route.futuresDetail(id: entry.marketId)) {
                            HStack {
                                Text(entry.label).font(.subheadline)
                                Spacer()
                                if let prob = entry.probability {
                                    Text(formatPct(prob))
                                        .font(.subheadline).bold().monospacedDigit()
                                }
                                if let rank = entry.rank {
                                    Text("#\(rank)").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }

            // Upcoming Games
            if !data.upcomingEvents.isEmpty {
                Section("Upcoming") {
                    ForEach(data.upcomingEvents) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            gameRow(event, teamName: team.name)
                        }
                    }
                }
            }

            // Recent Games
            if !data.recentEvents.isEmpty {
                Section("Recent") {
                    ForEach(data.recentEvents) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            gameRow(event, teamName: team.name)
                        }
                    }
                }
            }

            // Futures
            if !data.futures.isEmpty {
                Section("Season Futures") {
                    ForEach(data.futures) { future in
                        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(future.marketName).font(.subheadline).lineLimit(1)
                                HStack(spacing: 6) {
                                    if let prob = future.probability {
                                        Text(formatPct(prob)).font(.caption).bold().monospacedDigit()
                                    }
                                    if let rank = future.rank, let total = future.totalOutcomes {
                                        Text("#\(rank) of \(total)").font(.caption2).foregroundStyle(.secondary)
                                    }
                                    // #4351: this one did not even shout — the team
                                    // page printed the key verbatim, `odds_api`.
                                    if let src = SourceLabels.label(for: future.source) {
                                        Text(src).font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(team.name)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    /// One row of the Upcoming or Recent rail.
    ///
    /// #6444 — every one of these drew a percentage from
    /// `event.currentOdds?.homeProbability`, and **`/api/teams/{slug}` has never
    /// served `current_odds`**: its brief carries `win_probability` and
    /// `pregame_win_probability` (see ``SearchEvent/winProbability``). So the
    /// `else if` could not bind on any row of any team page, and the whole rail
    /// drew no number — the state Alex reported, including on a game an hour
    /// from first pitch.
    ///
    /// The `DrawPricedWinner` call that lived here is gone rather than repointed,
    /// and that is deliberate. #5363's hazard was a CLIENT-SIDE `1 − P(home)` on
    /// a raw three-way book price; this route serves neither the raw price nor a
    /// home-oriented number — the server already oriented it off the two-way
    /// normalised blend (`teams.py:559`). Putting the served number through the
    /// draw guard would be asking a question about an input that is not here, and
    /// its answer would silently blank the soccer rows it was built to protect.
    private func gameRow(_ event: SearchEvent, teamName: String) -> some View {
        let isHome = TeamGameRow.isHome(event, teamName: teamName)
        let opponent = TeamGameRow.opponent(event, teamName: teamName)
        let prefix = isHome ? "vs" : "@"
        let score = TeamGameRow.score(event, teamName: teamName)
        let result = TeamGameRow.result(event, teamName: teamName)
        let price = TeamGameRow.livePrice(event)
        let expectation = TeamGameRow.expectation(event, teamName: teamName)

        return HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("\(prefix) \(opponent)").font(.subheadline).fontWeight(.medium)
                HStack(spacing: 4) {
                    // #4021 — see StatusBadge: the suspended arm is clock-gated.
                    StatusBadge(status: event.status, commenceTime: event.commenceTime)
                    if let commence = event.commenceTime {
                        RelativeTimeText(dateString: commence)
                    }
                }
                // The grade-our-call line, the web card's own words.
                if let expectation {
                    expectationLine(expectation)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                if let score {
                    // A score is drawn whenever both sides arrived; the WIN/LOSS
                    // styling is drawn only where a final may be claimed, so a
                    // suspended or live row shows the numbers without the verdict.
                    Text("\(score.team)–\(score.opp)")
                        .font(.subheadline).bold().monospacedDigit()
                        .foregroundStyle(result.map { $0.won ? Color.primary : Color.secondary } ?? Color.primary)
                }
                if let price {
                    Text(formatPct(price))
                        .font(.subheadline).bold().monospacedDigit().foregroundStyle(.blue)
                }
            }
        }
    }

    /// "we had them at 63%" / "Upset — beat 78% odds" — `TeamGameCards.tsx`'s two
    /// sentences, character for character, asserted against that file by
    /// `TeamGameRowWebParity6444Tests` rather than kept in step by hand.
    @ViewBuilder
    private func expectationLine(_ expectation: TeamGameRow.Expectation) -> some View {
        switch expectation {
        case .had(let pre):
            Text("we had them at \(formatPct(pre))")
                .font(.caption).foregroundStyle(.secondary)
        case .upset(let pre):
            Text("Upset — beat \(formatPct(1 - pre)) odds")
                .font(.caption).fontWeight(.medium).foregroundStyle(.blue)
        }
    }

    private func formatPct(_ p: Double) -> String {
        "\(Int(round(p * 100)))%"
    }
}
