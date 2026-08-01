import SwiftUI

// MARK: - Terminal presentation semantics (pure, testable)

/// Which framing a tournament card is in, expressed as plain booleans so the
/// settled-means-settled contract can be asserted without rendering SwiftUI or
/// coupling a test to copy, fonts, or layout (L2-225).
///
/// The card previously made these five decisions inline against
/// `data.marquee_whathit == true`, which meant the only way to check "does a
/// finished tournament still show live movement language?" was to read the view
/// body. Two of the five were wrong when it was written down: the probability hero
/// and the runner-up strip both survived into the settled state, and the backend's
/// live `reason` prose ("… leads at 62.0% (up 2.3% today)") rendered directly under
/// the 🏁 FINAL chip.
nonisolated struct TournamentCardPresentation: Equatable {
    /// Live: the big win-probability number. Never shown once settled — the result
    /// is not a probability.
    let showsProbabilityHero: Bool
    /// Terminal: champion name + CHAMPION · WON chip (web `TournamentCard.tsx:44–48`).
    let showsChampion: Bool
    /// Live only: the "+2.3pp today" mover line.
    let showsMovementLine: Bool
    /// Live only: the runner-up probability strip.
    let showsRunnerUpStrip: Bool
    /// Live only: the backend's present-tense `reason`/context line.
    let showsFeedContext: Bool
    /// Terminal marker chip.
    let showsFinalChip: Bool

    init(data: FeedTournamentData, hasLeader: Bool, runnerUpCount: Int, hasContext: Bool) {
        let whatHit = data.marqueeWhathit == true
        showsFinalChip = whatHit
        showsProbabilityHero = hasLeader && !whatHit
        showsChampion = hasLeader && whatHit
        showsMovementLine = hasLeader && !whatHit
        showsRunnerUpStrip = !whatHit && runnerUpCount > 0
        showsFeedContext = hasContext && !whatHit
    }
}

struct NativeTournamentDiscoverCard: View {
    let data: FeedTournamentData
    let feedContext: String?
    @Binding var navigationPath: NavigationPath

    private var gradient: (Color, Color) {
        sportCategoryGradients["golf"] ?? sportDefaultGradient
    }

    /// The single place the card decides live-vs-terminal framing. Kept as a value
    /// so `TournamentCardPresentationTests` asserts the same object the body reads.
    private var presentation: TournamentCardPresentation {
        TournamentCardPresentation(
            data: data,
            hasLeader: leader != nil,
            runnerUpCount: max((data.golfers?.count ?? 0) - 1, 0),
            hasContext: !(feedContext ?? "").isEmpty
        )
    }

    private var leader: FeedTournamentGolfer? {
        data.golfers?.first
    }

    private var tourBadge: String {
        if data.isMajor == true { return "MAJOR" }
        guard let raw = data.tourLabel ?? data.tour, !raw.isEmpty else { return "GOLF" }
        // Map raw enum ("korn_ferry") to a display name, then uppercase for the
        // badge treatment ("KORN FERRY TOUR") — never leak the underscore enum.
        return golfTourDisplayName(for: raw).uppercased()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .topLeading) {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(tourBadge)
                            .font(.caption2.bold())
                            .foregroundStyle(.white.opacity(0.7))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.white.opacity(0.15))
                            .clipShape(RoundedRectangle(cornerRadius: 4))

                        if presentation.showsFinalChip {
                            Text("🏁 FINAL")
                                .font(.caption2.bold())
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.white.opacity(0.2))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                        }

                        Spacer()

                        if let venue = data.venue {
                            Text(venue)
                                .font(.caption2)
                                .foregroundStyle(.white.opacity(0.6))
                                .lineLimit(1)
                        }
                    }

                    Text(properTitleCase(data.name))
                        .font(.headline.bold())
                        .foregroundStyle(.white)
                        .lineLimit(2)

                    if let leader {
                        if presentation.showsChampion {
                            // L2-225: the hero is the CHAMPION, not a probability.
                            // L2-224 added the FINAL/WON chips but left the live
                            // "62%" as the biggest number on a finished tournament —
                            // and 62% is not what happened, it is what we thought
                            // would happen. Web has always dropped the number here
                            // and led with the name (`TournamentCard.tsx:44–48`);
                            // this now mirrors that field for field. Winner authority
                            // comes from `marquee_whathit` + the leader row, never
                            // from the probability being high.
                            VStack(alignment: .leading, spacing: 3) {
                                Text(leader.name)
                                    .font(.title3.bold())
                                    .foregroundStyle(.white)
                                    .lineLimit(2)
                                    .minimumScaleFactor(0.85)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text("CHAMPION · WON")
                                    .font(.caption2.bold())
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(.white.opacity(0.22))
                                    .clipShape(Capsule())
                            }
                        } else {
                            HStack(spacing: 8) {
                                Text("\(Int(leader.probability.rounded()))%")
                                    .font(.title.bold())
                                    .foregroundStyle(.white)

                                VStack(alignment: .leading, spacing: 1) {
                                    Text(leader.name)
                                        .font(.subheadline.bold())
                                        .foregroundStyle(.white)
                                    if presentation.showsMovementLine,
                                       let move = leader.movement24h, abs(move) >= 0.5 {
                                        // Live movement only — a settled tournament
                                        // never reaches this branch.
                                        Text(move > 0 ? "+\(String(format: "%.1f", move))pp today" : "\(String(format: "%.1f", move))pp today")
                                            .font(.caption2)
                                            .foregroundStyle(move > 0 ? .green : .red)
                                    }
                                }
                            }
                        }
                    }

                    // L2-225: the runner-up strip is a row of LIVE win probabilities.
                    // On a finished tournament those are the odds of a race that is
                    // already over, sitting directly under the champion — suppress it,
                    // exactly as web does (its tournament card renders no runner-up
                    // row in the WHAT-HIT state).
                    if presentation.showsRunnerUpStrip, let golfers = data.golfers {
                        HStack(spacing: 12) {
                            ForEach(golfers.dropFirst().prefix(3)) { golfer in
                                HStack(spacing: 3) {
                                    Text("\(Int(golfer.probability.rounded()))%")
                                        .font(.caption.bold())
                                        .foregroundStyle(.white.opacity(0.9))
                                    Text(golfer.name.components(separatedBy: " ").last ?? golfer.name)
                                        .font(.caption)
                                        .foregroundStyle(.white.opacity(0.7))
                                        .lineLimit(1)
                                }
                            }
                        }
                    }
                }
                .padding(14)
            }

            // L2-225: the feed context for a tournament is the backend's live
            // `reason` — literally "PGA Tour: Scottie Scheffler leads at 62.0% (up
            // 2.3% today)" (`routes/feed.py` `_score_golf_tournaments`). Rendering
            // present-tense "leads … up today" prose beneath a 🏁 FINAL chip is the
            // exact live-language leak this queue exists to close. Suppressed once
            // settled, matching `NativeConceptDiscoverCard`'s identical guard (and
            // web's tournament card, which renders no reason text at all).
            if presentation.showsFeedContext, let context = feedContext {
                Text(context)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.systemBackground)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.08), radius: 8, y: 4)
        .onTapGesture {
            navigationPath.append(Route.sportCategory(key: "golf", name: "Golf"))
        }
    }
}

// MARK: - Preview: the live → terminal pair, from a fixed local payload

#if DEBUG
/// L2-225: a deterministic, network-free way to see the live and terminal framings
/// of the SAME card side by side. The WHAT-HIT treatment only appears on the real
/// feed during a marquee's T+36h window, so before this the settled render could
/// only be reasoned about, never looked at. Both fixtures are decoded from the
/// backend's own `_score_golf_tournaments` payload shape (`routes/feed.py`), so the
/// preview exercises the real decode path rather than a hand-built struct.
enum TournamentLifecyclePreviewFixture {
    static func decode(marqueeWhathit: Bool, scheduleStatus: String) -> FeedTournamentData? {
        let json = """
        {
          "key": "the_open_championship", "name": "the open championship",
          "slug": "the-open", "tour": "pga", "tour_label": "PGA Tour",
          "is_major": true, "venue": "Royal Birkdale", "location": "Southport",
          "start_date": "2026-07-16T00:00:00Z", "end_date": "2026-07-19T00:00:00Z",
          "schedule_status": "\(scheduleStatus)",
          "resolution_date": "2026-07-19T00:00:00Z",
          "golfers": [
            {"name": "Scottie Scheffler", "probability": 62.0, "rank": 1, "movement_24h": 2.3},
            {"name": "Rory McIlroy", "probability": 14.5, "rank": 2, "movement_24h": -1.1},
            {"name": "Jon Rahm", "probability": 8.2, "rank": 3, "movement_24h": 0.4}
          ],
          "source_count": 2, "is_marquee": true,
          "marquee_whathit": \(marqueeWhathit)
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try? dec.decode(FeedTournamentData.self, from: Data(json.utf8))
    }
}

#Preview("Tournament — live vs settled (WHAT-HIT)") {
    ScrollView {
        VStack(spacing: 16) {
            if let live = TournamentLifecyclePreviewFixture.decode(
                marqueeWhathit: false, scheduleStatus: "in_progress") {
                // Live: hero 62%, leader name, "+2.3pp today" mover line.
                NativeTournamentDiscoverCard(
                    data: live,
                    feedContext: "Scheffler leads at 62% (up 2.3% today)",
                    navigationPath: .constant(NavigationPath()))
            }

            if let settled = TournamentLifecyclePreviewFixture.decode(
                marqueeWhathit: true, scheduleStatus: "completed") {
                // Terminal: 🏁 FINAL chip, WON chip, "Champion", and NO movement
                // line — same payload, same identity, result-first framing.
                NativeTournamentDiscoverCard(
                    data: settled,
                    feedContext: "Scheffler leads at 62% (up 2.3% today)",
                    navigationPath: .constant(NavigationPath()))
            }
        }
        .padding()
    }
}
#endif
