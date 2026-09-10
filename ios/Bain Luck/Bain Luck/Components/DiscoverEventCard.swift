import SwiftUI

// MARK: - Sport Emoji (shared)

func sportEmoji(for sport: String?) -> String {
    switch sport?.lowercased().split(separator: "_").first.map(String.init) {
    case "basketball": return "🏀"
    case "football", "americanfootball": return "🏈"
    case "baseball": return "⚾"
    case "hockey", "icehockey": return "🏒"
    case "soccer": return "⚽"
    case "golf": return "⛳"
    case "mma", "boxing": return "🥊"
    case "tennis": return "🎾"
    case "cricket": return "🏏"
    case "motorsports": return "🏎"
    case "olympics": return "🏅"
    default: return "🍀"
    }
}

// MARK: - Event Card

struct NativeEventDiscoverCard: View {
    let event: FeedEventData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil

    /// This card's slate/blue defaults are where `ProbabilityBarPalette`'s came
    /// from — it was the one card that already used a *pair* rather than one
    /// colour twice, so the palette adopts its values and Discover looks
    /// unchanged. What it gains is the collision arm: two crests that do not
    /// read apart (or one crest sitting on this card's own default) no longer
    /// produce a flat bar. #2902.
    private var barColors: (away: Color, home: Color) {
        ProbabilityBarPalette.colors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )
    }

    private var awayColor: Color { barColors.away }

    private var homeColor: Color { barColors.home }

    private var sportKey: String {
        event.sport?.split(separator: "_").first.map(String.init)?.lowercased() ?? "sports"
    }

    private var gradient: (Color, Color) {
        sportCategoryGradients[sportKey] ?? sportDefaultGradient
    }

    private var isLive: Bool {
        event.status == "live"
    }

    private var isDone: Bool {
        EventState.isFinished(event.status)
    }

    /// live/048 + CERT-786. The `statusText` default arm below is the literal
    /// string "vs" — the pregame reading — so a suspended match printed the
    /// crest strip of a game that has not started, on the app's default screen.
    /// #4021 — and the CLOCK is part of the test, for the same reason the
    /// comment above gives: the default arm is the pregame reading. Event 416569
    /// carried `status='suspended'` four days BEFORE kick-off, and without this
    /// the app's default screen would answer that with "No result reported"
    /// instead of the "vs" that is actually true. Found by the discovery scan in
    /// `eventStatusSingleSource.test.ts`, not by hand.
    private var isSuspended: Bool {
        EventState.isSuspendedAndStarted(
            event.status, commenceTime: event.commenceTime?.asDate)
    }

    private var sportLabel: String {
        sportCategoryDisplayName(event.sportName ?? event.sport).uppercased()
    }

    private var statusText: String {
        if isLive { return event.espn?.period ?? "LIVE" }
        if isDone {
            if let a = event.awayScore, let h = event.homeScore {
                return "\(a) - \(h)"
            }
            return "Final"
        }
        // live/048 — the crest strip is 50pt wide and sized for "Q3", so it
        // gets the short word and the full shared summary goes in the badge
        // below the matchup, where the reader already looks for the outcome.
        if isSuspended { return "Paused" }
        return "vs"
    }

    private var contextText: String? {
        if let feedContext, !feedContext.isEmpty { return feedContext }
        if let label = event.highlight?.label, !label.isEmpty { return label }
        if let ei = event.ei, let score = ei.score, score >= 60, let label = ei.label {
            return "Excitement Index \(score): \(label)"
        }
        if isLive { return "Live probability is moving now" }
        return nil
    }

    private var shareURL: URL {
        URL(string: eventShareURL(event.id, style: .nativeCard)) ?? bainLuckFallbackURL
    }

    private var shareMessage: String {
        // #4306 — the same `duelPercents` call the card body makes, so the
        // sentence a reader shares carries the two integers they were looking
        // at. Rounding here independently would print a share that disagrees
        // with its own card by a point.
        let duel = duelPercents(
            away: event.currentOdds?.awayProbability,
            home: event.currentOdds?.homeProbability,
            servedAway: event.currentOdds?.awayRenderedPercent,
            servedHome: event.currentOdds?.homeRenderedPercent
        )
        return eventShareMessage(
            away: event.awayTeam,
            home: event.homeTeam,
            awayPercent: duel[0],
            homePercent: duel[1]
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Hero section with gradient background
            ZStack {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .overlay(
                    // Decorative watermark at 0.08 opacity — never read, so it
                    // is deliberately NOT ramped (#1772). Scaling it would move
                    // a background glyph behind live text for no legibility
                    // gain. The census guard exempts exactly this line.
                    Text(sportEmoji(for: event.sport))
                        .font(.system(size: 96))
                        .opacity(0.08)
                )

                VStack(spacing: 0) {
                    // Top row: sport label + live badge
                    HStack {
                        Text(sportLabel)
                            .font(.caption2.weight(.heavy))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.78))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.black.opacity(0.24), in: Capsule())

                        Spacer()

                        if isLive {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(.white)
                                    .frame(width: 5, height: 5)
                                Text("LIVE")
                                    .font(.caption2.weight(.heavy))
                            }
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.red.opacity(0.85), in: Capsule())
                        } else if isDone {
                            Text("FINAL")
                                .font(.caption2.weight(.heavy))
                                .foregroundStyle(.white.opacity(0.78))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.black.opacity(0.24), in: Capsule())
                        } else if isSuspended {
                            // The corner that says FINAL or LIVE has to say
                            // something here too — leaving it empty is how the
                            // state stayed invisible (live/048).
                            Text("PAUSED")
                                .font(.caption2.weight(.heavy))
                                .foregroundStyle(.white.opacity(0.78))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.black.opacity(0.24), in: Capsule())
                        }
                    }

                    Spacer(minLength: 10)

                    // Matchup row
                    HStack(alignment: .center, spacing: 0) {
                        heroTeam(
                            label: cardSides.away, badge: cardBadges.away,
                            slot: avatarSlot(home: false),
                            color: awayColor,
                            score: event.awayScore,
                            alignment: .leading
                        )

                        VStack(spacing: 2) {
                            Text(statusText)
                                .font((isLive ? Font.caption2 : Font.footnote).weight(.heavy).monospacedDigit())
                                .foregroundStyle(.white.opacity(0.7))
                        }
                        .frame(width: 50)

                        heroTeam(
                            label: cardSides.home, badge: cardBadges.home,
                            slot: avatarSlot(home: true),
                            color: homeColor,
                            score: event.homeScore,
                            alignment: .trailing
                        )
                    }
                }
                .padding(14)
            }
            .frame(height: 160)
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18))

            // Bottom section
            VStack(alignment: .leading, spacing: 12) {
                // Team names
                Text("\(event.awayTeam) \(isDone ? "" : "@") \(event.homeTeam)")
                    .font(.headline.weight(.bold))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                // live/048 — the shared summary, in the slot the settled card
                // uses for its result. Same string the web Discover card
                // prints for the same row.
                if isSuspended {
                    Text(EventState.suspendedSummary(away: event.awayScore, home: event.homeScore))
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                // Probability bar — hidden once the game is done: a settled
                // game's "Win Probability" is stale/meaningless (the result is
                // the final score shown above), so we never surface a live-looking
                // split on a FINAL card (Queue #238 settled-state honesty).
                // live/048 — `!isSuspended` for the same honesty reason as
                // `!isDone`: the split would be the last live blend on a match
                // nothing is reporting on, drawn as a current read.
                if !isDone, !isSuspended,
                   let homeProbability = event.currentOdds?.homeProbability,
                   let awayProbability = event.currentOdds?.awayProbability {
                    // UX-P114 — these two are two sides of ONE question (the feed
                    // derives away as `1 - home`), so they are decided together or
                    // they sum to 101. Measured 2026-08-21: 34 of 414 live/upcoming
                    // events printed 101 here, always 101 and never 99. The server
                    // decides it; `renderedDuelPercents` is the fallback for a
                    // cached or pre-deploy payload, driven by the same contract
                    // table so it cannot answer differently.
                    //
                    // #2279 — BOTH SERVED OR NEITHER, and `duelPercents` is where
                    // that is decided. This site used to coalesce per side, so a
                    // payload carrying one field and not the other printed a
                    // served value beside a derived one and summed to 101 again.
                    // Both probabilities above come from `currentOdds`, so the
                    // served pair describes exactly the pair being drawn.
                    let duel = duelPercents(
                        away: awayProbability,
                        home: homeProbability,
                        servedAway: event.currentOdds?.awayRenderedPercent,
                        servedHome: event.currentOdds?.homeRenderedPercent
                    )
                    let awayPct = duel[0]
                    let homePct = duel[1]
                    VStack(spacing: 6) {
                        HStack {
                            Text(formatProbability(awayProbability, renderedPercent: awayPct))
                                .font(.title3.weight(.black).monospacedDigit())
                                .foregroundStyle(awayColor)
                            Spacer()
                            Text("Win Probability")
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formatProbability(homeProbability, renderedPercent: homePct))
                                .font(.title3.weight(.black).monospacedDigit())
                                .foregroundStyle(homeColor)
                        }
                        probabilityBar(awayProbability: awayProbability, homeProbability: homeProbability)
                    }
                }

                // Context text
                if let contextText {
                    ExpandableNativeContextText(
                        text: contextText,
                        expandedText: expandedContext,
                        font: .caption,
                        onExpand: onContextExpand,
                        onCollapse: onContextCollapse
                    )
                }

                // Footer
                HStack {
                    Spacer()

                    // #490 / L2-184: confidence signal (1-3 bars) — renders nothing
                    // when absent. Same tier map + placement as the native
                    // multi-candidate kernels (Comparison/Distribution/HeatMap).
                    SignalBarsView(tier: event.confidenceTier)

                    ShareLink(
                        item: shareURL,
                        subject: Text("\(event.awayTeam) vs \(event.homeTeam)"),
                        message: Text(shareMessage)
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.secondary)
                            .padding(8)
                            .background(Color.secondary.opacity(0.10), in: Circle())
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .contextMenu {
                        Button(action: copyShareImage) {
                            Label("Copy Image", systemImage: "doc.on.doc")
                        }

                        #if os(iOS)
                        Button(action: saveShareImage) {
                            Label("Save Image", systemImage: "square.and.arrow.down")
                        }
                        #endif
                    }
                }
            }
            .padding(14)
        }
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.07), radius: 12, x: 0, y: 5)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.eventDetail(id: event.id))
            onOpen?()
        }
    }

    /// #3430 — the card draws BOTH competitors side by side, so their labels
    /// are resolved together and handed in. Deriving each from its own name
    /// inside this function is what let the two sides print the same word.
    private var cardSides: (away: String, home: String) {
        TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam)
    }

    private var cardBadges: (away: String, home: String) {
        TeamShortName.abbreviationPair(away: event.awayTeam, home: event.homeTeam)
    }

    /// The avatar decision for one side, exposed so the suite can pin the WIRING
    /// and not merely the ladder: a correct ladder that this card does not call is
    /// invisible from the outside, which is the shape #2977 actually was.
    ///
    /// `event.sport` deliberately, NOT this view's own `sportKey` — that one is the
    /// first component only ("baseball"), and the ladder's flag rung matches on the
    /// whole key ("soccer_fifa_world_cup").
    func avatarSlot(home: Bool) -> TeamAvatarSlot {
        teamAvatarSlot(
            avatar: event.avatar(home: home),
            teamName: home ? event.homeTeam : event.awayTeam,
            sportKey: event.sport
        )
    }

    /// The consolation prize: the team's colour, wearing its abbreviation.
    private func badgeTile(badge: String, color: Color) -> some View {
        RoundedRectangle(cornerRadius: 12)
            .fill(color)
            .frame(width: 52, height: 52)
            .overlay(
                Text(badge)
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(.white)
            )
    }

    private func heroTeam(
        label: String,
        badge: String,
        slot: TeamAvatarSlot,
        color: Color,
        score: Int?,
        alignment: HorizontalAlignment
    ) -> some View {
        VStack(spacing: 6) {
            switch slot {
            case let .image(url, isPhotograph):
                AsyncImage(url: url) { phase in
                    if let img = phase.image {
                        // A crest is shown whole; a headshot fills the slot and is
                        // cropped, because a portrait scaled to FIT a square becomes a
                        // sliver (see `ParticipantAvatar.isPhotograph`).
                        img.resizable()
                            .aspectRatio(contentMode: isPhotograph ? .fill : .fit)
                            .frame(width: 52, height: 52)
                            .clipShape(RoundedRectangle(cornerRadius: isPhotograph ? 12 : 0, style: .continuous))
                    } else if phase.error != nil {
                        // A url that 404s used to leave a 52pt hole with a shadow on
                        // it: `placeholder:` is the FAILURE state as well as the
                        // loading one, so the card drew nothing at all. The tile at
                        // least names the team.
                        badgeTile(badge: badge, color: color)
                    } else {
                        // Loading: hold the space so the row does not jump.
                        Color.clear.frame(width: 52, height: 52)
                    }
                }
                .shadow(color: .black.opacity(0.3), radius: 6, x: 0, y: 2)
            case .tile:
                badgeTile(badge: badge, color: color)
                    .shadow(color: .black.opacity(0.3), radius: 6, x: 0, y: 2)
            }

            Text(label)
                .font(.caption.weight(.bold))
                .foregroundStyle(.white.opacity(0.92))
                .lineLimit(1)

            if let score, (isLive || isDone || isSuspended) {
                Text("\(score)")
                    .font(.title2.weight(.black).monospacedDigit())
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.25), radius: 4, x: 0, y: 2)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func probabilityBar(awayProbability: Double, homeProbability: Double) -> some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                Rectangle()
                    .fill(awayColor)
                    .frame(width: max(3, geo.size.width * awayProbability))
                Rectangle()
                    .fill(homeColor)
                    .frame(width: max(3, geo.size.width * homeProbability))
            }
            .clipShape(Capsule())
        }
        .frame(height: 8)
        .background(Color.barTrack.opacity(0.25), in: Capsule())
    }

    private func renderedShareImage() -> PlatformImage? {
        guard let homeProbability = event.currentOdds?.homeProbability,
              let awayProbability = event.currentOdds?.awayProbability else {
            return nil
        }
        return ShareCardRenderer.renderEventCard(
            homeTeam: event.homeTeam,
            awayTeam: event.awayTeam,
            homeProbability: homeProbability,
            awayProbability: awayProbability,
            sportName: event.sportName ?? event.sport ?? "Sports",
            homeColor: homeColor,
            awayColor: awayColor,
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore,
            // #4044 — the same reading this card's own `isSuspended` uses above.
            commenceTime: event.commenceTime?.asDate
        )
    }

    private func copyShareImage() {
        if let image = renderedShareImage() {
            ShareCardRenderer.copyImageToClipboard(image)
        }
    }

    private func saveShareImage() {
        #if os(iOS)
        if let image = renderedShareImage() {
            ShareCardRenderer.saveImageToPhotos(image)
        }
        #endif
    }
}
