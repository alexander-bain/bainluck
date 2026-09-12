import SwiftUI

/// Status-aware event card matching the web FeedCard layout.
struct EventCardView: View {
    let event: FeedEventData
    let reason: String?
    var personalizationReasons: [String]? = nil
    var headline: String? = nil

    private var isLive: Bool { event.status == "live" }
    private var isFinished: Bool { EventState.isFinished(event.status) }
    /// live/048 + CERT-786 — the branch this card did not have.
    ///
    /// #4021 — and the CLOCK is part of the test. `suspended` is a status, not a
    /// phase: event 416569 (Ohio State @ Texas) carried it four days BEFORE
    /// kick-off, which handed a game nobody had played the settled treatment —
    /// "No result reported" where its countdown belongs. `isScheduled` below
    /// excludes `isSuspended`, so narrowing this one predicate is what hands a
    /// future-dated row back to the pregame arm it belongs in. Changed here as
    /// well as on the event page deliberately: #4002 exists because this card and
    /// that page held separate opinions about `suspended`, and fixing one of them
    /// would be the same mistake with the roles swapped.
    private var isSuspended: Bool {
        EventState.isSuspendedAndStarted(
            event.status, commenceTime: event.commenceTime?.asDate)
    }
    /// `isScheduled` was the card's default arm, and it was the only one of the
    /// three that did not actually test the status it names: anything not live
    /// and not finished was "scheduled", so a suspended match took the whole
    /// pregame treatment — a START TIME for a match already played. Narrowed to
    /// exclude the state it was mislabelling; the trailing clause is kept for
    /// nil/unknown statuses, which have no better home.
    private var isScheduled: Bool {
        !isSuspended && (event.status == "scheduled" || (!isLive && !isFinished))
    }

    /// #4915 — one reading of who won, shared with the event-page hero.
    ///
    /// The feed payload behind this card carries no `hero_settled_result`, so
    /// the scores decide here; `EventOutcome` is what makes the third answer
    /// sayable at all. `awayWon`/`homeWon` keep their names and their exact
    /// meaning — the bug was never that they were true too often, it was that
    /// on a level result they are BOTH false and the card read `!won` as "lost".
    private var outcome: EventOutcome {
        EventOutcome.resolve(
            status: event.status, homeScore: event.homeScore, awayScore: event.awayScore)
    }
    private var awayWon: Bool { outcome.won(isAway: true) }
    private var homeWon: Bool { outcome.won(isAway: false) }

    /// #2902 — these two used to fall back to the SAME grey, so every card
    /// whose sides have no brand colour (all tennis, all golf pairings, any
    /// unmapped team) drew a bar with no visible split. The palette guarantees
    /// the pair reads apart; see `ProbabilityBarPalette`.
    private var barColors: (away: Color, home: Color) {
        ProbabilityBarPalette.colors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )
    }
    private var awayColor: Color { barColors.away }
    private var homeColor: Color { barColors.home }

    #if os(macOS)
    @State private var isHovered = false
    #endif

    /// "Today 7:00 PM", "Tomorrow 3:30 PM", or "Mar 8 7:00 PM"
    private var formattedDateTimeString: String? {
        guard let dateStr = event.commenceTime, let date = dateStr.asDate else { return nil }
        let calendar = Calendar.current
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a"
        let timeStr = timeFormatter.string(from: date)

        if calendar.isDateInToday(date) {
            return "Today \(timeStr)"
        } else if calendar.isDateInTomorrow(date) {
            return "Tomorrow \(timeStr)"
        } else {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "MMM d"
            return "\(dateFormatter.string(from: date)) \(timeStr)"
        }
    }

    @ViewBuilder
    private var formattedDateTime: some View {
        if let text = formattedDateTimeString {
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    /// "Mar 5" for finished events
    private var formattedDateString: String? {
        guard let dateStr = event.commenceTime, let date = dateStr.asDate else { return nil }
        let calendar = Calendar.current
        let formatter = DateFormatter()
        if calendar.component(.year, from: date) != calendar.component(.year, from: Date()) {
            formatter.dateFormat = "MMM d, yyyy"
        } else {
            formatter.dateFormat = "MMM d"
        }
        return formatter.string(from: date)
    }

    @ViewBuilder
    private var formattedDate: some View {
        if let text = formattedDateString {
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            topBar
            teamsAndOdds
            footer
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        #if os(macOS)
        .background(isHovered ? Color.primary.opacity(0.04) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .onHover { isHovered = $0 }
        #endif
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack(spacing: 6) {
            Text(event.sportName ?? sportDisplayName(for: event.sport))
                .font(.caption)
                .foregroundStyle(.secondary)
            StatusBadge(
                status: event.status,
                commenceTime: event.commenceTime,
                gameClock: event.espn?.gameClock,
                period: event.espn?.period
            )
            if !isFinished, let ei = event.ei ?? event.pulse {
                EIBadgeView(ei: ei, size: .sm)
            }
            // #490: confidence signal (1-3 bars) — renders nothing when absent.
            SignalBarsView(tier: event.confidenceTier)
            if let badge = personalizationBadge {
                badge
            }
            if let headline, !headline.isEmpty {
                Text(headline)
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.blue.opacity(0.12))
                    .foregroundStyle(.blue)
                    .clipShape(Capsule())
            }
            Spacer()
            if let broadcast = event.espn?.broadcast?.split(separator: ",").first.map(String.init),
               !broadcast.isEmpty, isScheduled || isLive {
                HStack(spacing: 2) {
                    Image(systemName: "tv")
                        .font(.system(size: 8))
                    Text(broadcast.trimmingCharacters(in: .whitespaces))
                        .font(.caption2)
                }
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
            if isScheduled {
                // Upcoming: Show "Today 7:00 PM" or "Mar 8 7:00 PM"
                formattedDateTime
            } else if isFinished {
                // Finished: Show date only "Mar 5"
                formattedDate
            } else if isSuspended {
                // live/048: no start time, no Final — the shared summary, the
                // same string the web card prints for the same row.
                Text(EventState.suspendedSummary(away: event.awayScore, home: event.homeScore))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            PinButton(type: "event", id: event.id, compact: true)
        }
    }

    // MARK: - Personalization Badge

    private var personalizationBadge: AnyView? {
        guard let reasons = personalizationReasons, !reasons.isEmpty else { return nil }
        // Parse first matching reason from "your_team:0.80" format
        for reason in reasons {
            let key = reason.split(separator: ":").first.map(String.init) ?? reason
            switch key {
            case "your_team":
                return AnyView(badgeCapsule(text: "Your Team", color: .blue))
            case "local":
                return AnyView(badgeCapsule(text: "Local", color: .green))
            case "alma_mater":
                return AnyView(badgeCapsule(text: "Alma Mater", color: .purple))
            case "rival_losing":
                return AnyView(badgeCapsule(text: "Rival Losing", color: .orange))
            default:
                continue
            }
        }
        return nil
    }

    private func badgeCapsule(text: String, color: Color) -> some View {
        Text(text)
            .font(.caption2)
            .fontWeight(.semibold)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.12))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    // MARK: - Teams + Odds (with inline scores)

    private var teamsAndOdds: some View {
        VStack(spacing: 6) {
            teamRow(
                name: event.awayTeam,
                avatar: event.avatar(home: false),
                color: awayColor,
                record: event.awayTeamData?.record,
                score: (isLive || isFinished || isSuspended) ? event.awayScore : nil,
                won: awayWon,
                side: .away
            )

            probabilityBar

            teamRow(
                name: event.homeTeam,
                avatar: event.avatar(home: true),
                color: homeColor,
                record: event.homeTeamData?.record,
                score: (isLive || isFinished || isSuspended) ? event.homeScore : nil,
                won: homeWon,
                side: .home
            )
        }
    }

    private func teamRow(name: String, avatar: ParticipantAvatar, color: Color, record: String?, score: Int?, won: Bool, side: TeamSide) -> some View {
        HStack(spacing: 8) {
            TeamLogoView(
                url: avatar.url,
                teamName: name,
                color: color,
                size: isLive ? 28 : 24,
                sportKey: event.sport,
                isPhotograph: avatar.isPhotograph,
                // #4720 — this card stacks both rows, so each circle is resolved
                // against the other side rather than on its own.
                opponentName: side == .away ? event.homeTeam : event.awayTeam
            )
            Text(name)
                .font(.subheadline)
                .fontWeight(won ? .bold : .medium)
                // #4915 — `!won` was standing in for "lost", and on a level
                // result both sides are `!won`, so a finished draw greyed BOTH
                // teams. The draw is exempted rather than the rule rewritten:
                // a finished row we hold no score for keeps today's settled dim,
                // which is a different treatment answering a different question.
                .foregroundStyle(won ? .primary : (isFinished && outcome != .draw ? .secondary : .primary))
                .lineLimit(1)
            if let record, !isFinished {
                Text(record)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let score {
                Text("\(score)")
                    .font(isLive ? .title3.monospacedDigit() : .subheadline.monospacedDigit())
                    .fontWeight(isLive ? .bold : (won ? .bold : .regular))
                    // #4915 — same exemption, and only that: a SUSPENDED row's
                    // scores keep their dim (neither side has won anything yet),
                    // so the draw is the one arm that moves.
                    .foregroundStyle(isLive ? .primary : (won || outcome == .draw ? .primary : .secondary))
            }
            if isFinished {
                preGameOddsLabel(for: side)
            } else {
                probabilityWithMovement(for: side)
            }
        }
    }

    // MARK: - Footer

    /// Whether `EventCardView`'s footer row has anything to put in it.
    ///
    /// #4094 — `footer` is an unconditional child of the body's
    /// `VStack(spacing: 8)`, and an `HStack` holding only a `Spacer()` is not an
    /// `EmptyView`: it still takes its turn in the stack and still costs the 8pt
    /// of spacing above it. That state was already reachable — a finished card
    /// whose `reason` came back empty — but #4094 stops the backend captioning
    /// settled games with "odds shifted N% during the game", which turns the
    /// empty footer from a rare card into most of Just Happened. A strip of dead
    /// space under every settled card is the wrong way to spend that fix.
    ///
    /// Lives out here as a pure function rather than as a `private var` on the
    /// view because its whole job is to agree with the two `if` branches inside
    /// `footerRow`, and a duplicated condition that nothing can test is exactly
    /// the kind that drifts. The guard test pins both directions.
    enum EventCardFooter {
        static func hasContent(
            reason: String?,
            isLive: Bool,
            awayOpening: Double?,
            homeOpening: Double?,
            sport: String?
        ) -> Bool {
            if let reason, !reason.isEmpty { return true }
            // #5363 — a draw-priced sport draws the named single-sided caption
            // ("Opened Boca 68%"), so HOME alone is content there. Taking the
            // sport rather than a pre-computed Bool keeps this function's
            // agreement with `footerRow` decidable from the same inputs the
            // view has; the guard test pins both arms in both directions.
            guard isLive, homeOpening != nil else { return false }
            // Mirrors `footerRow`'s two branches: the "Opened X/Y" pair needs
            // BOTH sides priced, and the named single-sided caption needs the
            // rule to fire. Home alone on a two-way sport still renders
            // nothing, so it is still not content.
            return awayOpening != nil || DrawPricedWinner.sportPricesADraw(sport)
        }
    }

    @ViewBuilder
    private var footer: some View {
        if EventCardFooter.hasContent(
            reason: reason,
            isLive: isLive,
            awayOpening: event.openingOdds?.awayProbability,
            homeOpening: event.openingOdds?.homeProbability,
            sport: event.sport
        ) {
            footerRow
        }
    }

    private var footerRow: some View {
        HStack(spacing: 6) {
            if let reason, !reason.isEmpty {
                reasonBadge(reason)
            }
            Spacer()
            // UX-P166 — both sides of one question in fixed positions is a DUEL,
            // and rounding the two independently printed 101. Measured on
            // production 2026-08-29: all 24,117 events carrying an opening line
            // are complement pairs and 207 of them print 101, none 99.
            //
            // This line claimed "same rule and same helper as the `currentOdds`
            // strip" while that strip was still rounding per side (#3049) — it was
            // the only site on the card that HAD the rule. It now reads the shared
            // `openingPercents`, so the claim is true and there is one derivation
            // per odds source rather than a third copy.
            //
            // #5363 — `opening_odds` is a complement pair too
            // (`opening_away_probability or round(1 - home, 4)`), so on a
            // draw-priced sport this caption told the same lie the strip did.
            // The withheld arm is the event page's, word for word: a caption
            // that has lost one of its pair has lost the positional attribution
            // that let the other go unnamed, so it NAMES the side (#3430 —
            // via the pair, because "Tigers" is not a name when both shorten
            // to it).
            if isLive, let opened = DrawPricedWinner.printablePair(
                away: event.openingOdds?.awayProbability,
                home: event.openingOdds?.homeProbability,
                sport: event.sport) {
                if let awayOpen = opened.away {
                    Text("Opened \(formatProbability(awayOpen, renderedPercent: openingPercents[0]))/\(formatProbability(opened.home, renderedPercent: openingPercents[1]))")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                } else {
                    let named = TeamShortName.shortPair(
                        away: event.awayTeam, home: event.homeTeam
                    )
                    Text("Opened \(named.home) \(formatProbability(opened.home))")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
    }

    private func reasonBadge(_ text: String) -> some View {
        let (icon, color) = reasonStyle(text)
        return HStack(spacing: 3) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 9, weight: .semibold))
            }
            Text(text)
                .font(.caption2)
                .fontWeight(.medium)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(color.opacity(0.1))
        .clipShape(Capsule())
    }

    private func reasonStyle(_ text: String) -> (String?, Color) {
        let lower = text.lowercased()
        if lower.contains("upset") || lower.contains("underdog") {
            return ("exclamationmark.triangle.fill", .orange)
        } else if lower.contains("close") || lower.contains("tight") || lower.contains("even") {
            return ("equal.circle.fill", .blue)
        } else if lower.contains("line mov") || lower.contains("shifted") || lower.contains("odds") {
            return ("arrow.up.arrow.down", .purple)
        } else if lower.contains("starting soon") {
            return ("clock.fill", .green)
        } else if lower.contains("lead change") || lower.contains("wild") || lower.contains("exciting") {
            return ("bolt.fill", .yellow)
        }
        return (nil, .secondary)
    }

    // MARK: - Helpers

    private enum TeamSide { case home, away }

    /// The two percents the LIVE strip prints, `[away, home]`, decided once.
    ///
    /// #3049: `probabilityWithMovement(for:)` is invoked once per side and used to
    /// format that side's raw probability alone, so it structurally could not apply
    /// a pair rule. Venues quote on a half-percent grid, so `.x5` is the common case
    /// and independent half-up rounding sent both sides up: all three live US Open
    /// cards printed 101 at 15:05Z on 2026-09-04 (95/6, 61/40, 76/25) while the
    /// event page hero for the same match printed 5/95. Deriving the pair HERE, from
    /// both sides at once, is the only shape that can be right.
    ///
    /// The served pair is passed because these probabilities are `current_odds`'
    /// own — `duelPercents` takes both served values or neither, never one.
    private var livePercents: [Int?] {
        duelPercents(
            away: event.currentOdds?.awayProbability,
            home: event.currentOdds?.homeProbability,
            servedAway: event.currentOdds?.awayRenderedPercent,
            servedHome: event.currentOdds?.homeRenderedPercent
        )
    }

    /// The two percents the OPENING line prints, `[away, home]`.
    ///
    /// No served values: `current_odds.{away,home}_rendered_percent` describes
    /// `current_odds` and nothing else, and handing that rounding to another
    /// source's probability prints a mismatched pair that still sums to 100 — the
    /// one error a sum guard cannot see (`RenderedPercent.swift`).
    private var openingPercents: [Int?] {
        renderedDuelPercents(
            away: event.openingOdds?.awayProbability,
            home: event.openingOdds?.homeProbability
        )
    }

    /// #5363 — whether this card may print an AWAY probability at all.
    ///
    /// `sportPricesADraw` and not `printablePair`, deliberately, and this is the
    /// one place in the family where the difference bites. `printablePair`
    /// answers for a two-SLOT surface and returns `nil` for the whole pair when
    /// a two-way sport holds no away price — correct for the event page's hero,
    /// which draws one duel. This card draws each side in its OWN row and has
    /// always printed the home number alone when the away price was missing, so
    /// routing these two rows through the pair rule would newly blank a home
    /// number on two-way sports: a regression wearing the fix's name.
    ///
    /// The rows are already named — logo, then team, then the number — so the
    /// withheld side simply renders nothing, and nothing has to be renamed. The
    /// collapse-to-one-number surfaces are the ones that name their survivor.
    private var awayIsWithheld: Bool {
        DrawPricedWinner.sportPricesADraw(event.sport)
    }

    @ViewBuilder
    private func probabilityWithMovement(for side: TeamSide) -> some View {
        let prob: Double? = side == .home
            ? event.currentOdds?.homeProbability
            : (awayIsWithheld ? nil : event.currentOdds?.awayProbability)
        let openProb: Double? = side == .home
            ? event.openingOdds?.homeProbability
            : (awayIsWithheld ? nil : event.openingOdds?.awayProbability)
        let color = side == .home ? homeColor : awayColor

        if let prob {
            HStack(spacing: 3) {
                if isLive, let openProb {
                    let shift = prob - openProb
                    if abs(shift) > 0.02 {
                        Image(systemName: shift > 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(shift > 0 ? Color.green : Color.red)
                    }
                }
                Text(formatProbability(prob, renderedPercent: side == .home ? livePercents[1] : livePercents[0]))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(color)
            }
        }
    }

    /// Shows pre-game odds inline for completed games — dimmed, with "was" prefix for clarity
    @ViewBuilder
    private func preGameOddsLabel(for side: TeamSide) -> some View {
        let opening = event.openingOdds
        // #5363 — the settled row's pre-game number is the same complement.
        let prob: Double? = side == .home
            ? opening?.homeProbability
            : (awayIsWithheld ? nil : opening?.awayProbability)
        if let prob {
            let wasUnderdog = prob < 0.4
            let wasHeavyFavorite = prob > 0.7
            let won = (side == .home && homeWon) || (side == .away && awayWon)
            let isUpset = won && wasUnderdog

            HStack(spacing: 2) {
                Text(formatProbability(prob, renderedPercent: side == .home ? openingPercents[1] : openingPercents[0]))
                    .font(.caption)
                    .fontWeight(.semibold)
                    .monospacedDigit()
            }
            .foregroundStyle(
                isUpset ? .orange :
                (won && wasHeavyFavorite) ? .secondary :
                .secondary.opacity(0.7)
            )
        }
    }

    @ViewBuilder
    private var probabilityBar: some View {
        if isFinished {
            if let opening = event.openingOdds,
               let awayProb = opening.awayProbability,
               let homeProb = opening.homeProbability {
                ProbabilityBar(
                    awayProb: awayProb,
                    homeProb: homeProb,
                    // #5363 — the bar KEEPS its remainder, because the two
                    // segments are a partition and "not the home team" is a
                    // true quantity. What it is not is the away team, so it
                    // loses that team's colour along with its number and reads
                    // as the neutral rest of the whole. The event page settled
                    // this in #5271; the card family follows it exactly.
                    awayColor: awayIsWithheld
                        ? Color.secondary.opacity(0.25)
                        : awayColor.opacity(0.5),
                    homeColor: homeColor.opacity(0.5),
                    height: 5
                )
            }
        } else if isSuspended {
            // live/048 — no bar. It would be the last live blend on a match
            // nothing is reporting on, drawn at full width and full colour: the
            // most confident element on a card whose whole message is that
            // nobody has said anything. The settled arm above drops it for the
            // mirror-image reason.
            EmptyView()
        } else if let away = event.currentOdds?.awayProbability,
                  let home = event.currentOdds?.homeProbability {
            ProbabilityBar(
                awayProb: away,
                homeProb: home,
                // #5363 — see the settled bar above: the remainder survives, the
                // away team's colour does not.
                awayColor: awayIsWithheld ? Color.secondary.opacity(0.25) : awayColor,
                homeColor: homeColor,
                height: isLive ? 10 : 8,
                animated: isLive,
                glowing: isLive
            )
        }
    }
}
