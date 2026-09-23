import SwiftUI

/// ESPN-style game play card displayed below the odds chart.
/// Updates as the user scrubs across the chart, showing:
/// - Score (team-colored)
/// - Period and clock
/// - Scoring play description (when hovering over one)
/// - Win probability (when between scoring plays)
struct GamePlayCardView: View {
    let selectedPoint: GamePlayPoint?
    let homeTeam: String
    let awayTeam: String
    var homeTeamColor: Color = .primary
    var awayTeamColor: Color = .primary
    var homeTeamLogo: String?
    var awayTeamLogo: String?
    /// Most recent chart point (shown when not scrubbing)
    var lastPoint: GamePlayPoint?

    private var point: GamePlayPoint? {
        selectedPoint ?? lastPoint
    }

    var body: some View {
        if let point {
            VStack(spacing: 0) {
                Divider()
                    .padding(.bottom, 8)

                HStack(alignment: .top, spacing: 10) {
                    // Game-state badge (period + clock) over the wall-clock time
                    // of the scrubbed point, and — when the state is carried
                    // from an older row — the time it was actually seen (#925).
                    if !point.timeDisplay.isEmpty || !point.wallClockDisplay.isEmpty {
                        VStack(alignment: .leading, spacing: 2) {
                            if !point.timeDisplay.isEmpty {
                                Text(point.timeDisplay)
                                    .font(.caption2)
                                    .fontWeight(.medium)
                                    .foregroundStyle(.secondary)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 3)
                                    .background(Color.gray.opacity(0.15))
                                    .clipShape(RoundedRectangle(cornerRadius: 4))
                            }
                            if !point.wallClockDisplay.isEmpty {
                                Text(point.wallClockDisplay)
                                    .font(.caption2)
                                    .monospacedDigit()
                                    .foregroundStyle(.tertiary)
                                    .padding(.horizontal, 6)
                            }
                            if let asOf = point.stateAsOfDisplay {
                                Text(asOf)
                                    .font(.caption2)
                                    .monospacedDigit()
                                    .foregroundStyle(.tertiary)
                                    .padding(.horizontal, 6)
                            }
                        }
                    }

                    // Score
                    if point.hasScore {
                        HStack(spacing: 6) {
                            HStack(spacing: 3) {
                                if let url = homeTeamLogo {
                                    AsyncImage(url: URL(string: url)) { image in
                                        image.resizable().aspectRatio(contentMode: .fit)
                                    } placeholder: {
                                        EmptyView()
                                    }
                                    .frame(width: 14, height: 14)
                                }
                                Text("\(point.homeScore ?? 0)")
                                    .font(.caption)
                                    .fontWeight(.bold)
                                    .monospacedDigit()
                                    .foregroundStyle(homeTeamColor)
                            }
                            Text("-")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            HStack(spacing: 3) {
                                Text("\(point.awayScore ?? 0)")
                                    .font(.caption)
                                    .fontWeight(.bold)
                                    .monospacedDigit()
                                    .foregroundStyle(awayTeamColor)
                                if let url = awayTeamLogo {
                                    AsyncImage(url: URL(string: url)) { image in
                                        image.resizable().aspectRatio(contentMode: .fit)
                                    } placeholder: {
                                        EmptyView()
                                    }
                                    .frame(width: 14, height: 14)
                                }
                            }
                        }
                    }

                    // Play description or probability context
                    VStack(alignment: .leading, spacing: 2) {
                        if let play = point.scoringPlay {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(.red)
                                    .frame(width: 5, height: 5)
                                if let type = play.type {
                                    Text(type)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Text(play.description ?? play.shortText ?? "")
                                .font(.caption2)
                                .foregroundStyle(.primary)
                                .lineLimit(2)
                        } else {
                            let homeProb = Int((point.homeProb * 100).rounded())
                            HStack(spacing: 0) {
                                Text(homeShort)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(" \(homeProb)%")
                                    .font(.caption2)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(homeTeamColor)
                                // #5271 — the away half is drawn only where an
                                // away price exists. `awayProb` was `1 - home`
                                // at both of this point's construction sites,
                                // and on a draw-priced sport that is the away
                                // side's chances with the draw folded in.
                                if let away = point.awayProb {
                                    Text(" — ")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    Text(awayShort)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    Text(" \(Int((away * 100).rounded()))%")
                                        .font(.caption2)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(awayTeamColor)
                                }
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.top, 8)
        }
    }

    /// #3430 — both competitors of one matchup, so the pair rule decides.
    private var sides: (away: String, home: String) {
        TeamShortName.shortPair(away: awayTeam, home: homeTeam)
    }

    private var homeShort: String { sides.home }

    private var awayShort: String { sides.away }
}

// MARK: - Game Play Point

/// Data model for a single point on the chart with game context.
struct GamePlayPoint {
    let timestamp: String
    let homeProb: Double
    /// Nil where we hold no away price — a draw-priced sport, where the
    /// complement this used to be is not the away side's chances (#5271).
    let awayProb: Double?
    var homeScore: Int?
    var awayScore: Int?
    var period: String?
    var clock: String?
    var scoringPlay: ScoringPlay?
    /// #925 — when the score/period/clock above were OBSERVED. On a point whose
    /// state was carried forward from an older row this is that row's time;
    /// `stateApprox` says the carry is a minute or more old. Both default so
    /// every existing construction site (the resting "last point" in
    /// `EventDetailView`) is an exact observation, which is what it is.
    var stateObservedAt: Date? = nil
    var stateApprox: Bool = false

    var hasScore: Bool {
        homeScore != nil && awayScore != nil
    }

    /// The point's own wall-clock time — "7:44 PM" — the third thing #925 asks
    /// the readout to say beside the score and the game clock. Empty when the
    /// timestamp does not parse, which is the card's cue to draw nothing.
    var wallClockDisplay: String {
        guard let date = timestamp.asDate else { return "" }
        return Self.clockText(date)
    }

    /// "as of 7:41 PM" — the observation the carried state came from, printed
    /// only when it is older than the point (`stateApprox`), so an exact point
    /// says nothing and a stale one says exactly how stale. Nil otherwise.
    ///
    /// Reader copy, not implementation: it names a time, not a mechanism.
    var stateAsOfDisplay: String? {
        guard stateApprox, let observed = stateObservedAt,
              hasScore || !timeDisplay.isEmpty else { return nil }
        return "as of \(Self.clockText(observed))"
    }

    /// One clock format for both lines, so "7:44 PM" and "as of 7:41 PM" read as
    /// the same kind of time.
    static func clockText(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    /// The badge above the score: the period, and the clock when the clock says
    /// something the period does not.
    ///
    /// #6574. #3273 pointed this card at the shared PARSER. It kept the JOIN, and the
    /// join is the other half of the rule: `[periodStr, clock]` prints whatever
    /// two strings it is handed, side by side, and ESPN's settled row sends
    /// `period` and `game_clock` as the SAME word. Measured on the served payload
    /// for 14638896 (Broncos 10 – Chiefs 31, MNF, Final) 2026-09-16: the last
    /// `espn_history` row is `period: "Final", game_clock: "Final"`, so the badge
    /// under the win-probability chart read **"Final · Final"**.
    ///
    /// That is #4880 — soccer's `23' 23'` — in its fourth call site.
    /// ``PeriodLabel/liveStatusText(period:gameClock:)`` is the rule written for
    /// exactly this, and it is the only thing that can see the collision, because
    /// it is the only thing handed BOTH strings. The seven sites #4880 and #5057
    /// converted are pinned by name in
    /// `frontend/__tests__/ios/periodLabelSingleSource.test.ts`; this one was
    /// invisible to that file's discovery scan because the pair is RENAMED at this
    /// struct's boundary — `EventDetailView` passes `espn.gameClock` in as `clock`
    /// — and the scan's tell keys on the identifier `gameClock`. The widened tell
    /// lands with this fix, so the rename cannot hide the ninth site.
    ///
    /// The separator moves from `" · "` to the shared rule's space, which is what
    /// the hero capsule two hundred points up this same page already prints
    /// (`StatusBadge`, same helper): one vocabulary for the pair, not two.
    var timeDisplay: String {
        let text = PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""
        // #925 — a carried state wears the same `~` the web's badge does
        // ("Q4 ~1:09", "~Top 8th"): one glyph, one meaning — "not observed at
        // this instant". The exact time it WAS observed is `stateAsOfDisplay`.
        guard stateApprox, !text.isEmpty else { return text }
        return "~" + text
    }
}
