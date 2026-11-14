import SwiftUI

/// Status-aware event card matching the web FeedCard layout.
struct EventCardView: View {
    let event: FeedEventData
    let reason: String?
    var personalizationReasons: [String]? = nil
    var headline: String? = nil
    /// Ruling 183-A Size S (Team schedule & recent results): same crests,
    /// colours, bookmark pin, and column headers without sub-captions or bottom bar.
    var compactScheduleStyle: Bool = false
    /// True when `/api/teams/{slug}` already resolved a draw-priced sport's
    /// away probability via `_away_three_way_price` (#11541).
    var awayReadingIsServerVerified: Bool = false

    /// #11325 — selects the finished card's accessibility arm; see
    /// `FinishedCardAccessibility11325`.
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// #12616 — Atlas Column Type Spec: one tabular SF Pro digit family at three
    /// gentle optical steps (`20pt Bold` primary `Now`/`Chance`/`Final`, `17pt Semibold`
    /// live `Score` / scheduled `Projected`, `15pt Regular` `Pregame` across all states,
    /// and `10.5pt Semibold` uppercase headers), locked to `.firstTextBaseline` with an
    /// `18pt` breathing gutter after `Score` and a `10pt` pair gap between `Pregame` and `Now`.
    @ScaledMetric(relativeTo: .body) private var compactNameSize: CGFloat = 17
    @ScaledMetric(relativeTo: .caption2) private var compactHeaderSize: CGFloat = 10.5
    @ScaledMetric(relativeTo: .body) private var compactScoreSize: CGFloat = 17
    @ScaledMetric(relativeTo: .subheadline) private var compactPregameSize: CGFloat = 15
    @ScaledMetric(relativeTo: .title3) private var compactLargeSize: CGFloat = 20
    @ScaledMetric(relativeTo: .body) private var compactLiveScoreWidth: CGFloat = 44
    @ScaledMetric(relativeTo: .body) private var compactProjectedWidth: CGFloat = 78
    @ScaledMetric(relativeTo: .subheadline) private var compactPregameWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .title3) private var compactLargeChanceWidth: CGFloat = 66
    @ScaledMetric(relativeTo: .title3) private var compactLargeFinalWidth: CGFloat = 46

    private let scoreToPregameGutter: CGFloat = 18
    private let pregameToNowGap: CGFloat = 10

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
    /// #6010 — whether the per-side slot may print a LIVE reading at all.
    ///
    /// The slot used to ask `isFinished`, and a suspended row is not finished, so
    /// it took the live arm and printed `current_odds` — the stale blend CERT-792
    /// ruled off this card. The bar (`probabilityBar`), the start time and the
    /// score dim had each been given the suspended branch one at a time; the
    /// NUMBER never got it, which is the loudest element on the card still saying
    /// it. Production specimen (live/210, 2026-09-13 22:21Z), Torino v AS Roma
    /// `15297959`, suspended and scoreless: `current_odds` home **0.1525**
    /// captured **2026-09-05**, `opening_odds` home **0.2514**. Web prints 25/75
    /// in grey after ux's `18eaceac8`; this card printed **15%/85%** semibold in
    /// team colour, an eight-day-old in-play blend wearing the styling of a price.
    ///
    /// It is `canStillBeGraded` and not a fourth inline copy of the status test,
    /// because "may we print a forecast?" is the question that helper was lifted
    /// out to answer (#4018) and a blend IS a forecast. The four states fall out
    /// of it rather than being enumerated: scheduled and live can still be graded
    /// and keep the live arm untouched; finished and suspended-and-started cannot
    /// and take the pre-match one. Note the CLOCK travels with it — a suspended
    /// row dated in the future is still pregame (#4021) and still prints its
    /// current line.
    private var canStillBeGraded: Bool {
        EventState.canStillBeGraded(
            event.status, commenceTime: event.commenceTime?.asDate)
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
    ///
    /// #7036 — and reading apart from EACH OTHER is not the same guarantee as
    /// reading against the WHITE CARD. This row paints the leading side's
    /// percentage as text (`sideColor`) and both sides as thin bar segments, so
    /// a club whose stored `primary_color` is `#ffffff` rendered a card with no
    /// visible number at all — Rennes v Lyon on the Sports tab, sitting between
    /// neighbours that all showed one. Going through `TeamTextContrast` puts the
    /// WCAG floor under the same palette rather than beside it.
    ///
    /// Exposed rather than `private` because the floor's WIRING is the part no
    /// unit test of the helper can see: a revert to
    /// `ProbabilityBarPalette.colors(awayHex:homeHex:)` compiles, renders and
    /// leaves every contrast test green. A test drives this on a real payload.
    var barColorHexes: (away: String, home: String) {
        TeamTextContrast.cardColorHexes(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )
    }
    private var barColors: (away: Color, home: Color) {
        let hexes = barColorHexes
        return (Color(hex: hexes.away), Color(hex: hexes.home))
    }
    private var awayColor: Color { barColors.away }
    private var homeColor: Color { barColors.home }

    #if os(macOS)
    @State private var isHovered = false
    #endif

    /// "Today 7:00 PM", "Tomorrow 3:30 PM", or "Mar 8 7:00 PM" — or, when the
    /// venue has not announced the start (#8841), "Sep 29 · TBD" with no clock.
    private var formattedDateTimeString: String? {
        if event.startIsTbd == true {
            return RelativeTimeText.tbdText(for: event.commenceTime)
        }
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

    /// Whether the top row draws the served `headline` as a pill.
    ///
    /// #5868 — A LIVE CARD DRAWS NO HEADLINE PILL, because on a live card the
    /// server sends the SAME sentence in `headline` and in `reason`, and this
    /// card renders both: the pill up here, the grey `reasonBadge` down in
    /// `footerRow`. Photographed on production 2026-09-13 09:01Z
    /// (`artifacts-native-142/sports.png`): under Live Now, "Sangju Sangmu FC
    /// leading after starting at 45%" and "Hokkaido Nippon-Ham Fighters chance
    /// rose from 46% to 88%" each appear twice on their own card, ~40pt apart.
    /// Measured on the same payload — of 70 event items, 2 of the 3 live ones
    /// print the sentence twice and 0 of the 11 non-live ones do, because a
    /// non-live headline is a short tag ("Recent upset", "Line moving") that
    /// says something the reason does not. The pill also has no line limit, so
    /// a sentence-length headline wraps to three lines and deforms the badge
    /// row it shares with the league name, the LIVE badge and the bookmark.
    ///
    /// THIS IS THE WEB CARD'S RULE, PORTED, NOT A NEW ONE. `FeedCard.tsx:661`
    /// has gated this same pill on `!isLive` for the event card (and :1328 for
    /// the concept card) all along; iOS never got it. That gap is #4002's shape
    /// — one card holding two opinions on two platforms — so the fix is the
    /// twin's condition rather than a second rule invented here.
    ///
    /// It REMOVES the pill rather than de-duplicating it, and that is the
    /// deliberate part: the third live card in that payload (KBO, Hanwha v Kia)
    /// carries headline "Odds moved" beside reason "Virtually even", two
    /// different sentences, and this rule drops that pill too — exactly as web
    /// already does. The narrower alternative, `lib/headlineEcho.ts` (#4403),
    /// is what the FUTURES family uses on web, not the event card; adopting it
    /// here would put the two platforms back out of step on one component.
    ///
    /// Pure and out here for the reason `EventCardFooter` is: a condition
    /// spelled inline in a `ViewBuilder` is a condition no test can reach, and
    /// the guard has to be able to fail in both directions.
    enum EventCardHeadlinePill {
        static func isDrawn(headline: String?, isLive: Bool) -> Bool {
            // Ruling 182-A — game cards remove the records bubble and use a
            // capsule ONLY for live status; a real reason to care is a plain
            // grey line in `footerRow`, never a top-bar pill.
            return false
        }
    }

    /// #11325 — true only on a finished card at an accessibility text size.
    /// Every other card, Large included, keeps the single-row arms below.
    private var usesFinishedAccessibilityLayout: Bool {
        FinishedCardAccessibility11325.applies(
            isFinished: isFinished, typeSize: dynamicTypeSize)
    }

    private var leagueName: String {
        event.sportName ?? sportDisplayName(for: event.sport)
    }

    private var statusBadge: some View {
        StatusBadge(
            status: event.status,
            commenceTime: event.commenceTime,
            gameClock: event.espn?.gameClock,
            period: event.espn?.period,
            startIsTbd: event.startIsTbd == true,
            // #5811 — served on `/api/feed`, so the card can say it.
            venueClosedNoWinner: event.venueClosedNoWinner == true,
            gameCardPlain182: true,
            gameCardLeadingDot: !usesFinishedAccessibilityLayout
        )
    }

    @ViewBuilder
    private var topBar: some View {
        if usesFinishedAccessibilityLayout {
            finishedAccessibilityTopBar
        } else {
            singleRowTopBar
        }
    }

    private var singleRowTopBar: some View {
        HStack(spacing: 6) {
            Text(leagueName)
                .font(.caption)
                .foregroundStyle(.secondary)
            statusBadge
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
            if isFinished {
                // Finished: Show date once ("Nov 8") as plain text
                formattedDate
            } else if isSuspended, let detail = EventState.suspendedCardDetail(
                away: event.awayScore, home: event.homeScore, date: formattedDateString,
                authorityPeriod: event.espn?.period) {
                // live/048: no start time, no Final. The words themselves now sit
                // in the `StatusBadge` six points to the left — this slot carried
                // a verbatim second copy of them on 1,786 of 1,788 suspended rows
                // (both scores null ⇒ `suspendedSummary` IS `suspendedLabel`).
                // `suspendedCardDetail` is where that reasoning lives, along with
                // why the date arrives here and not from `formattedDateTime`.
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            PinButton(type: "event", id: event.id, compact: true)
        }
    }

    /// #11325 — the finished card's top bar at accessibility sizes.
    private var finishedAccessibilityTopBar: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(leagueName)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) {
                    statusBadge.fixedSize()
                    Spacer(minLength: 6)
                    formattedDate
                    PinButton(type: "event", id: event.id, compact: true)
                }
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        statusBadge.fixedSize()
                        Spacer(minLength: 6)
                        PinButton(type: "event", id: event.id, compact: true)
                    }
                    formattedDate
                }
            }
        }
    }

    // MARK: - Teams + Odds (161-B compact two-column card)

    private var shortTeamNames: (away: String, home: String) {
        TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
    }

    private var scheduledProjection12616: ScheduledCardProjectedFinal12616.Pair? {
        guard isScheduled else { return nil }
        return ScheduledCardProjectedFinal12616.card(event)
    }

    private var compactHeaders12616: CompactGameCard12616.ColumnHeaders {
        let hasCurrent = event.currentOdds?.homeProbability != nil
            || (!currentAwayIsWithheld && event.currentOdds?.awayProbability != nil)
        let reading = prematch
        let hasPrematch = reading?.homeProbability != nil
            || (!prematchAwayIsWithheld && reading?.awayProbability != nil)
        let hasScore = event.awayScore != nil || event.homeScore != nil
        return CompactGameCard12616.columnHeaders(
            isScheduled: isScheduled,
            isLive: isLive,
            isFinished: isFinished,
            isSuspended: isSuspended,
            hasProjectedBefore: scheduledProjection12616 != nil,
            hasCurrentChance: hasCurrent,
            hasPrematchChance: hasPrematch,
            hasScore: hasScore,
            showsLivePregameColumn: showsInlineLivePregame12616
        )
    }

    private var teamsAndOdds: some View {
        VStack(spacing: 6) {
            if !usesFinishedAccessibilityLayout && compactHeaders12616.hasAny {
                compactHeaderRow
            }

            teamRow(
                name: event.awayTeam,
                avatar: event.avatar(home: false),
                color: awayColor,
                record: event.awayTeamData?.record,
                score: (isLive || isFinished || isSuspended) ? event.awayScore : nil,
                won: awayWon,
                side: .away
            )

            if !compactScheduleStyle && usesFinishedAccessibilityLayout {
                probabilityBar
            }

            teamRow(
                name: event.homeTeam,
                avatar: event.avatar(home: true),
                color: homeColor,
                record: event.homeTeamData?.record,
                score: (isLive || isFinished || isSuspended) ? event.homeScore : nil,
                won: homeWon,
                side: .home
            )

            if !usesFinishedAccessibilityLayout,
               let drawChance = CompactGameCard12616.drawChanceText(
                event: event,
                isScheduled: isScheduled,
                isLive: isLive,
                isFinished: isFinished,
                isSuspended: isSuspended
               ) {
                compactDrawRow(drawChance: drawChance)
            }

            if !compactScheduleStyle && !usesFinishedAccessibilityLayout {
                probabilityBar
            }

            if !compactScheduleStyle, let finalForecast = finalForecast11296 {
                if usesFinishedAccessibilityLayout {
                    FinalForecastLine11296(
                        comparison: finalForecast, awayName: event.awayTeam, homeName: event.homeTeam)
                        // Under the team names, past the 24pt crest and the row's 8pt gap.
                        .padding(.leading, 32)
                } else {
                    CompactProjectedContextLine12616(
                        text: CompactGameCard12616.finalContextText(finalForecast),
                        spokenText: FinalForecastComparison11296.spokenText(
                            finalForecast, awayName: event.awayTeam, homeName: event.homeTeam),
                        accessibilityId: FinalForecastLine11296.accessibilityIdentifier
                    )
                }
            }

            if !compactScheduleStyle, isLive, !isSuspended {
                let pregameContext = showsInlineLivePregame12616 ? nil : livePregameContext12616
                if dynamicTypeSize.isAccessibilitySize {
                    if let liveProjection = liveProjectedFinal2920 {
                        LiveProjectedFinalLine2920(
                            printed: liveProjection, awayName: event.awayTeam, homeName: event.homeTeam,
                            sportKey: event.sport)
                            .padding(.leading, 32)
                    }
                    if let pregameContext {
                        CompactProjectedContextLine12616(
                            text: pregameContext.visible,
                            spokenText: pregameContext.spoken,
                            accessibilityId: "eventCard.livePregameContext"
                        )
                    }
                } else if let combinedText = CompactGameCard12616.combinedLiveContextText(
                    projected: liveProjectedFinal2920,
                    pregameClause: pregameContext?.visible
                ) {
                    let spokenParts = [
                        liveProjectedFinal2920.map {
                            LiveProjectedFinal2920.spokenText(
                                $0, awayName: event.awayTeam, homeName: event.homeTeam)
                        },
                        pregameContext?.spoken,
                    ].compactMap { $0 }
                    CompactProjectedContextLine12616(
                        text: combinedText,
                        spokenText: spokenParts.joined(separator: ". "),
                        accessibilityId: liveProjectedFinal2920 != nil
                            ? LiveProjectedFinalLine2920.accessibilityIdentifier
                            : "eventCard.livePregameContext"
                    )
                }
            }
        }
    }

    private var liveSidePregame12616: (away: String?, home: String?, draw: String?) {
        guard isLive, !isSuspended,
              !EventCardFooter.reasonStatesTheOpening(CompactGameCard12616.sanitizedReason(reason)) else {
            return (nil, nil, nil)
        }
        return CompactGameCard12616.liveSidePregameLabels(event: event, prematch: prematch)
    }

    private var showsInlineLivePregame12616: Bool {
        let labels = liveSidePregame12616
        guard labels.away != nil || labels.home != nil else { return false }
        return CompactGameCard12616.liveInlinePregameFits(
            awayShortName: shortTeamNames.away,
            homeShortName: shortTeamNames.home,
            typeSize: dynamicTypeSize
        )
    }

    private var showsMediumColumn12616: Bool {
        if isSuspended {
            return event.awayScore != nil || event.homeScore != nil
        }
        return compactHeaders12616.medium != nil
    }

    private var showsLargeColumn12616: Bool {
        if isSuspended {
            return prematch != nil
        }
        return compactHeaders12616.large != nil
    }

    private var effectiveMediumColWidth: CGFloat {
        if isScheduled {
            return min(compactProjectedWidth, 92)
        }
        if isFinished {
            return min(compactPregameWidth, 66)
        }
        return min(compactLiveScoreWidth, 52)
    }

    private var effectiveLivePregameColWidth: CGFloat {
        min(compactPregameWidth, 66)
    }

    private var effectiveLargeColWidth: CGFloat {
        if isFinished { return min(compactLargeFinalWidth, 54) }
        if isSuspended { return min(compactPregameWidth, 66) }
        return min(compactLargeChanceWidth, 76)
    }

    private var pregameColumnLeadingGap12616: CGFloat {
        showsMediumColumn12616 ? scoreToPregameGutter : 0
    }

    private var largeColumnLeadingGap12616: CGFloat {
        if showsInlineLivePregame12616 {
            return pregameToNowGap
        }
        return showsMediumColumn12616 ? scoreToPregameGutter : 0
    }

    private var compactHeaderFont12616: Font {
        .system(size: min(compactHeaderSize, 13), weight: .semibold).monospacedDigit()
    }

    private var compactHeaderRow: some View {
        let headers = compactHeaders12616
        return VStack(spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                Spacer(minLength: 0)
                if showsMediumColumn12616 {
                    Text((headers.medium ?? "").uppercased())
                        .font(compactHeaderFont12616)
                        .tracking(0.45)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .frame(width: effectiveMediumColWidth, alignment: .trailing)
                }
                if showsInlineLivePregame12616 {
                    Text((headers.pregame ?? "").uppercased())
                        .font(compactHeaderFont12616)
                        .tracking(0.45)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .frame(width: effectiveLivePregameColWidth, alignment: .trailing)
                        .padding(.leading, pregameColumnLeadingGap12616)
                }
                if showsLargeColumn12616 {
                    Text((headers.large ?? "").uppercased())
                        .font(compactHeaderFont12616)
                        .tracking(0.45)
                        .foregroundStyle(isLive || isFinished ? Color.primary.opacity(0.78) : DS.textSecondaryReadable)
                        .lineLimit(1)
                        .frame(width: effectiveLargeColWidth, alignment: .trailing)
                        .padding(.leading, largeColumnLeadingGap12616)
                }
            }
            Rectangle()
                .fill(Color.primary.opacity(0.08))
                .frame(height: 0.5)
        }
    }

    /// #2920 — on a live game, the producer's marked in-play pair beneath the two
    /// rows that print the score, and only that pair: never the bare
    /// `projected_*` keys, which can still hold the pregame reading. Nil on every
    /// other state and wherever the pair cannot be shown honestly; nil draws
    /// nothing. Internal so the suite reaches the wiring.
    var liveProjectedFinal2920: LiveProjectedFinalAdmission2920.Printed? {
        guard isLive, !isSuspended else { return nil }
        return LiveProjectedFinal2920.card(event)
    }

    /// #11296 — on a final, the sportsbooks' last pair before the scheduled
    /// start, beneath the two rows that print the result. Nil on every other
    /// state and wherever the pair cannot be shown honestly; nil draws nothing.
    /// Soccer's 90-minute forecast prints only beside the producer's served
    /// regulation final (see the helper). Internal so the suite reaches the wiring.
    var finalForecast11296: FinalForecastComparison11296.Comparison? {
        guard isFinished else { return nil }
        return FinalForecastComparison11296.resolve(
            sport: event.sport, status: event.status,
            homeScore: event.homeScore, awayScore: event.awayScore,
            actualPeriod: FinalForecastComparison11296.actualPeriod(
                sport: event.sport, servedFinalScorePeriod: event.finalScorePeriod),
            projection: event.pregameProjection)
    }

    @ViewBuilder
    private func teamRow(name: String, avatar: ParticipantAvatar, color: Color, record: String?, score: Int?, won: Bool, side: TeamSide) -> some View {
        if usesFinishedAccessibilityLayout {
            finishedAccessibilityTeamRow(
                name: name, avatar: avatar, color: color, score: score, won: won, side: side)
        } else {
            singleRowTeamRow(
                name: name, avatar: avatar, color: color, record: record, score: score, won: won, side: side)
        }
    }

    private func singleRowTeamRow(name: String, avatar: ParticipantAvatar, color: Color, record: String?, score: Int?, won: Bool, side: TeamSide) -> some View {
        let displayName = side == .away ? shortTeamNames.away : shortTeamNames.home
        return HStack(spacing: 6) {
            TeamLogoView(
                url: avatar.url,
                teamName: name,
                color: color,
                size: 28,
                sportKey: event.sport,
                isPhotograph: avatar.isPhotograph,
                // #4720 — this card stacks both rows, so each circle is resolved
                // against the other side rather than on its own.
                opponentName: side == .away ? event.homeTeam : event.awayTeam
            )
            HStack(spacing: 4) {
                let singleWord = !displayName.contains(" ")
                Text(displayName)
                    .font(.system(size: min(compactNameSize, 21), weight: isFinished ? (won ? .bold : .medium) : .semibold))
                    // #4915 — `!won` was standing in for "lost", and on a level
                    // result both sides are `!won`, so a finished draw greyed BOTH
                    // teams.
                    .foregroundStyle(won ? .primary : (isFinished && outcome != .draw ? .secondary : .primary))
                    .lineLimit(singleWord ? 1 : 2)
                    .minimumScaleFactor(singleWord ? 0.82 : 0.88)
                    .fixedSize(horizontal: false, vertical: !singleWord)
                if isFinished && won {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.primary)
                        .accessibilityHidden(true)
                }
            }
            Spacer(minLength: 8)
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                if showsMediumColumn12616 {
                    mediumSlotView(score: score, won: won, side: side)
                        .frame(width: effectiveMediumColWidth, alignment: .trailing)
                }
                if showsInlineLivePregame12616 {
                    liveInlinePregameSlotView(for: side)
                        .frame(width: effectiveLivePregameColWidth, alignment: .trailing)
                        .padding(.leading, pregameColumnLeadingGap12616)
                }
                if showsLargeColumn12616 {
                    largeSlotView(score: score, won: won, side: side)
                        .frame(width: effectiveLargeColWidth, alignment: .trailing)
                        .padding(.leading, largeColumnLeadingGap12616)
                }
            }
        }
    }

    @ViewBuilder
    private func liveInlinePregameSlotView(for side: TeamSide) -> some View {
        let label = side == .home ? liveSidePregame12616.home : liveSidePregame12616.away
        if let label {
            Text(label)
                .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                .foregroundStyle(DS.textSecondaryReadable)
                .lineLimit(1)
        }
    }

    @ViewBuilder
    private func mediumSlotView(score: Int?, won: Bool, side: TeamSide) -> some View {
        if isScheduled {
            if let pair = scheduledProjection12616 {
                let value = side == .home ? pair.home : pair.away
                Text("\(value)")
                    .font(.system(size: min(compactScoreSize, 20), weight: .medium).monospacedDigit())
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
            }
        } else if isFinished {
            settledMediumOddsLabel(for: side)
        } else if let score {
            Text("\(score)")
                .font((isLive
                    ? Font.system(size: min(compactScoreSize, 20), weight: .semibold)
                    : Font.system(size: min(compactScoreSize, 20), weight: .regular)).monospacedDigit())
                // #4915 — a SUSPENDED row's scores keep their dim; the draw is
                // the one settled arm that moves.
                .foregroundStyle(isLive ? .primary : (won || outcome == .draw ? .primary : .secondary))
                .lineLimit(1)
        }
    }

    private func settledMediumOddsLabel(for side: TeamSide) -> some View {
        preGameOddsLabel(for: side)
    }

    @ViewBuilder
    private func largeSlotView(score: Int?, won: Bool, side: TeamSide) -> some View {
        if isFinished {
            if let score {
                Text("\(score)")
                    .font(.system(size: min(compactLargeSize, 24), weight: .bold).monospacedDigit())
                    .foregroundStyle(won || outcome == .draw ? .primary : .secondary)
                    .lineLimit(1)
            }
        } else {
            chanceSlotView(for: side)
        }
    }

    @ViewBuilder
    private func chanceSlotView(for side: TeamSide) -> some View {
        if canStillBeGraded {
            probabilityWithMovement(for: side)
        } else {
            preGameOddsLabel(for: side)
        }
    }

    private func compactDrawRow(drawChance: String) -> some View {
        let drawWon = isFinished && outcome == .draw
        return HStack(spacing: 6) {
            ZStack {
                Circle()
                    .fill(Color.secondary.opacity(0.16))
                    .frame(width: 28, height: 28)
                Text("=")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            .accessibilityHidden(true)

            HStack(spacing: 4) {
                Text("Draw")
                    .font(.system(size: min(compactNameSize, 21), weight: drawWon ? .bold : .semibold))
                    .foregroundStyle(isFinished ? (drawWon ? .primary : .secondary) : .primary)
                    .lineLimit(1)
                if drawWon {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.primary)
                        .accessibilityHidden(true)
                }
            }

            Spacer(minLength: 8)

            HStack(alignment: .firstTextBaseline, spacing: 0) {
                if showsMediumColumn12616 {
                    Group {
                        if isFinished {
                            Text(drawChance)
                                .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                                .foregroundStyle(DS.textSecondaryReadable)
                                .lineLimit(1)
                        }
                    }
                    .frame(width: effectiveMediumColWidth, alignment: .trailing)
                }

                if showsInlineLivePregame12616 {
                    Group {
                        if let drawPre = liveSidePregame12616.draw {
                            Text(drawPre)
                                .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                                .foregroundStyle(DS.textSecondaryReadable)
                                .lineLimit(1)
                        }
                    }
                    .frame(width: effectiveLivePregameColWidth, alignment: .trailing)
                    .padding(.leading, pregameColumnLeadingGap12616)
                }

                if showsLargeColumn12616 {
                    Group {
                        if !isFinished {
                            Text(drawChance)
                                .font(.system(size: min(compactLargeSize, 24), weight: .bold).monospacedDigit())
                                .foregroundStyle(DS.textSecondaryReadable)
                                .lineLimit(1)
                        }
                    }
                    .frame(width: effectiveLargeColWidth, alignment: .trailing)
                    .padding(.leading, largeColumnLeadingGap12616)
                }
            }
        }
    }

    /// #11325 — one team's group on a finished card at accessibility sizes.
    ///
    /// The single row gave the name whatever the score and pre-match number
    /// left over, under `lineLimit(1)`, so at AX5 both sides read
    /// "Washingt…" / "San Fran…" and a reader could not say who played. Here
    /// the crest and the COMPLETE name share the first row and the name wraps
    /// as far as it needs; the score sits on its own line beneath, under the
    /// name, inside this team's group — so each value stays with its own side.
    /// Fonts, weights and colours are the single row's expressions, verbatim,
    /// so the two arms cannot drift. A finished card draws no record, so there
    /// is none here.
    ///
    /// Design's REVISE (2026-10-20): "17" and "24%" side by side read as one
    /// unexplained pair of numbers — FINAL says the game is over, nothing says
    /// the percent is from before it. So the pre-match number is its own block
    /// below the score, under a visible "Pregame win chance" label that wraps
    /// downward rather than squeezing the number. Same selection, rounding,
    /// withholding and colour as the single row; no number, no block.
    private func finishedAccessibilityTeamRow(name: String, avatar: ParticipantAvatar, color: Color, score: Int?, won: Bool, side: TeamSide) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .top, spacing: 8) {
                TeamLogoView(
                    url: avatar.url,
                    teamName: name,
                    color: color,
                    size: isLive ? 28 : 24,
                    sportKey: event.sport,
                    isPhotograph: avatar.isPhotograph,
                    opponentName: side == .away ? event.homeTeam : event.awayTeam
                )
                Text(name)
                    .font(.subheadline)
                    .fontWeight(won ? .bold : .medium)
                    .foregroundStyle(won ? .primary : (isFinished && outcome != .draw ? .secondary : .primary))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            VStack(alignment: .leading, spacing: 4) {
                if let score {
                    Text("\(score)")
                        .font(isLive ? .title3.monospacedDigit() : .subheadline.monospacedDigit())
                        .fontWeight(isLive ? .bold : (won ? .bold : .regular))
                        .foregroundStyle(isLive ? .primary : (won || outcome == .draw ? .primary : .secondary))
                }
                if canStillBeGraded {
                    probabilityWithMovement(for: side)
                } else {
                    preGameOddsLabel(for: side, labelled: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            // Under the name: past the 24pt crest and the row's 8pt gap, the
            // same inset `FinalForecastLine11296` takes below.
            .padding(.leading, 32)
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
            isFinished: Bool = false,
            awayOpening: Double? = nil,
            homeOpening: Double? = nil,
            sport: String? = nil
        ) -> Bool {
            // #12616 / Ruling 182-A — finished game cards never draw the reason
            // line, and records captions ("TOR 77-80 · BAL 76-81") are dropped
            // so `footerRow` draws only a real non-finished reason to care.
            guard !isFinished, let reason, !reason.isEmpty else { return false }
            guard !CompactGameCard12616.isRecordsCaption(reason) else { return false }
            return true
        }

        /// #11422 — whether the served reason already says where the game
        /// STARTED. Every live claim `feed_reasons.py` writes carries the
        /// kickoff price ("New Orleans Pelicans leading after starting at 44%",
        /// "… chance rose from 46% to 87%", "… chance fell from …"). When the
        /// reason says it, the live `pregame` label steps aside so the
        /// card never states the start twice.
        static func reasonStatesTheOpening(_ reason: String?) -> Bool {
            guard let reason, !reason.isEmpty else { return false }
            return reason.range(
                of: #"(after starting at|chance (rose|fell) from) \d+%"#,
                options: [.regularExpression, .caseInsensitive]) != nil
        }
    }

    @ViewBuilder
    private var footer: some View {
        if !compactScheduleStyle && EventCardFooter.hasContent(
            reason: reason,
            isLive: isLive,
            isFinished: isFinished,
            awayOpening: event.openingOdds?.awayProbability,
            homeOpening: event.openingOdds?.homeProbability,
            sport: event.sport
        ) {
            footerRow
        }
    }

    private var footerRow: some View {
        HStack(spacing: 6) {
            if !isFinished, let cleaned = CompactGameCard12616.sanitizedReason(reason), !cleaned.isEmpty {
                reasonBadge(cleaned)
            }
            Spacer(minLength: 0)
        }
    }

    private func reasonBadge(_ text: String) -> some View {
        // Ruling 182-A — a capsule is ONLY for live status; a real reason to
        // care is a plain readable-grey line, never a coloured icon pill.
        Text(text)
            .font(.caption)
            .foregroundStyle(DS.textSecondaryReadable)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
            .layoutPriority(1)
    }

    /// Which badge family a served reason belongs to. (#5749)
    ///
    /// 🔴 THE CLASSIFIER READS A SENTENCE THAT HAS A TEAM NAME IN IT. Every
    /// reason a card carries is a template from `feed_reasons.py` /
    /// `highlights.py` with a team or market name interpolated into it, so a
    /// bare-substring test is reading the name too:
    /// `"kentucky wildcats leading after starting at 24%".contains("wild")` was
    /// true, and that card drew the yellow "something wild is happening" bolt.
    /// Measured on production `teams`, 27 of 5,592 distinct names hijack their
    /// own card — 16 contain "wild", 11 contain "even". The Minnesota Wild
    /// claimed a lead change in every state it was ever in, and Benevento was
    /// always "virtually even". `close`, `tight`, `odds` and `upset` measured 0.
    ///
    /// Word boundaries alone are NOT the fix, and this is the part worth
    /// carrying: `\bwild\b` still matches "Minnesota Wild". The keyword has to
    /// be pinned to the words the TEMPLATE puts around it — "wild game",
    /// "close matchup" — because that is the part a name cannot forge.
    /// Boundaries are enough for `upset`/`underdog`/`odds`/`shifted`, which
    /// measured 0 team names and are not name-shaped; they are used there so the
    /// family stays legible next to the two that needed phrases.
    ///
    /// Byte-for-byte the web's `REASON_STYLES` (`frontend/components/FeedCard.tsx`,
    /// #5749 / PR #5799) — same families, same patterns, same ORDER, which is
    /// load-bearing: "Starting soon — close matchup" is a close matchup first.
    ///
    /// Split out of the view as a pure decision so the guard test can run the
    /// whole served reason corpus through it without rendering anything.
    enum ReasonBadge {
        case upset
        case even
        case movement
        case startingSoon
        case wild
        case plain

        /// Pattern → family, in the order the branches are tried.
        private static let families: [(pattern: String, family: ReasonBadge)] = [
            // "Upset result" · "Possible upset" · "Recent upset" · "Upset brewing"
            // · "Upset underway" · "Won as 24% underdog"
            (#"\bupsets?\b|\bunderdogs?\b"#, .upset),
            // "Virtually even" · "Tight game" · "Close matchup" · "Close game"
            // · "Starting soon — close matchup"
            (#"\bvirtually even\b|\btight game\b|\bclose (?:matchup|game)\b"#, .even),
            // "Big odds movement in X" · "Odds shifting in X" · "Odds flipped"
            // · "X odds shifted 12% since open" · "Shifted since Tuesday" · "Line moving"
            (#"\bline mov|\bshifted\b|\bodds\b"#, .movement),
            // "Starting soon"
            (#"\bstarting soon\b"#, .startingSoon),
            // "Wild game" — the ONLY served reason this family has; "wild" alone
            // was the hijack.
            (#"\bwild game\b|\blead change|\bexciting\b"#, .wild),
        ]

        static func family(for text: String) -> ReasonBadge {
            let lower = text.lowercased()
            for entry in families
            where lower.range(of: entry.pattern, options: .regularExpression) != nil {
                return entry.family
            }
            return .plain
        }
    }

    private func reasonStyle(_ text: String) -> (String?, Color) {
        switch ReasonBadge.family(for: text) {
        case .upset: return ("exclamationmark.triangle.fill", .orange)
        case .even: return ("equal.circle.fill", .blue)
        case .movement: return ("arrow.up.arrow.down", .purple)
        case .startingSoon: return ("clock.fill", .green)
        case .wild: return ("bolt.fill", .yellow)
        case .plain: return (nil, .secondary)
        }
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

    /// #8622 / #12616 — the pre-match reading that BOTH the finished `Pregame`
    /// column AND the live `Pregame` context line + bar notch read: the server's
    /// ladder rung (`prematch_odds`), with `opening_odds` as the fallback.
    private var prematch: PrematchReading? {
        PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
    }

    /// #12616 (161-B) — the live card's starting-chance clause in the one quiet
    /// grey context line (`"Pregame 54%–46%"`, away then home like the rows, or
    /// `"Pregame Boca 68%"` when away is a two-way soccer complement under #5363),
    /// derived from `prematch` so it always agrees with the bar's pregame notch.
    /// Steps aside when the served `reason` already states the opening (#11422).
    private var livePregameContext12616: (visible: String, spoken: String)? {
        guard isLive, !isSuspended,
              !EventCardFooter.reasonStatesTheOpening(reason),
              let reading = prematch else { return nil }
        if CompactGameCard12616.hasExplicitThreeWayPrematch(event) {
            let awayText = formatProbability(reading.awayProbability, renderedPercent: reading.percents[0])
            let homeText = formatProbability(reading.homeProbability, renderedPercent: reading.percents[1])
            return (
                visible: "Pregame \(awayText)\u{2013}\(homeText)",
                spoken: "Pregame \(event.awayTeam) \(awayText), \(event.homeTeam) \(homeText)"
            )
        }
        guard let opened = DrawPricedWinner.printablePair(
            away: reading.awayProbability,
            home: reading.homeProbability,
            sport: event.sport
        ) else { return nil }
        if let awayOpen = opened.away {
            let awayText = formatProbability(awayOpen, renderedPercent: reading.percents[0])
            let homeText = formatProbability(opened.home, renderedPercent: reading.percents[1])
            return (
                visible: "Pregame \(awayText)\u{2013}\(homeText)",
                spoken: "Pregame \(event.awayTeam) \(awayText), \(event.homeTeam) \(homeText)"
            )
        }
        let named = TeamShortName.shortPair(
            away: event.awayTeam, home: event.homeTeam,
            sportKey: event.sport
        )
        let homeText = formatProbability(opened.home)
        return (
            visible: "Pregame \(named.home) \(homeText)",
            spoken: "Pregame \(event.homeTeam) \(homeText)"
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
    /// #5363 / #12616 — whether each reading on this card may print an AWAY
    /// probability. Decided per reading (`current_odds` vs `prematch`) so a
    /// three-way pregame reading never un-withholds a two-way live complement
    /// (`1 - home`), nor vice versa on a finished card.
    private var currentAwayIsWithheld: Bool {
        !awayReadingIsServerVerified
            && DrawPricedWinner.sportPricesADraw(event.sport)
            && !CompactGameCard12616.hasExplicitThreeWayCurrent(event)
    }

    private var prematchAwayIsWithheld: Bool {
        !awayReadingIsServerVerified
            && DrawPricedWinner.sportPricesADraw(event.sport)
            && !CompactGameCard12616.hasExplicitThreeWayPrematch(event)
    }

    private var liveTenthsPair12616: (away: String?, home: String?) {
        CompactGameCard12616.liveTenthsStrings(
            away: event.currentOdds?.awayProbability,
            home: event.currentOdds?.homeProbability,
            awayIsWithheld: currentAwayIsWithheld
        )
    }

    @ViewBuilder
    private func probabilityWithMovement(for side: TeamSide) -> some View {
        let prob: Double? = side == .home
            ? event.currentOdds?.homeProbability
            : (currentAwayIsWithheld ? nil : event.currentOdds?.awayProbability)
        let color = side == .home ? homeColor : awayColor

        if let prob {
            if isLive, let tenths = (side == .home ? liveTenthsPair12616.home : liveTenthsPair12616.away) {
                Text(tenths)
                    .font(.system(size: min(compactLargeSize, 24), weight: .bold).monospacedDigit())
                    .foregroundStyle(color)
                    .lineLimit(1)
            } else {
                Text(formatProbability(prob, renderedPercent: side == .home ? livePercents[1] : livePercents[0]))
                    .font(.system(size: min(compactLargeSize, 24), weight: .bold).monospacedDigit())
                    .foregroundStyle(color)
                    .lineLimit(1)
            }
        }
    }

    /// The pre-match number, dimmed — for every row that will draw no further
    /// live reading: completed, and since #6010 suspended-and-started too.
    ///
    /// It needed no change to serve the second state, and that is worth saying
    /// once rather than rediscovering: `outcome` resolves through
    /// `EventOutcome.resolve`, which returns `.undecided` for anything
    /// `EventState.isFinished` rejects, so on a suspended row `won` is false for
    /// BOTH sides and the upset orange and the favourite's grey are both
    /// unreachable. What a suspended card gets is the plain
    /// `.secondary.opacity(0.7)` — a grey pre-match number under "No result
    /// reported", which is the treatment web settled on, and no verdict on a row
    /// that has none (#4788).
    ///
    /// `labelled` (#11325, the finished accessibility row only) stacks the same
    /// number under a "Pregame win chance" label, so it cannot be mistaken for
    /// a second score.
    ///
    /// #9483 — the finished single row says what the number is too. At default
    /// size Stuttgart's actual "1" sat beside a bare "32%", and neither FINAL
    /// nor the forecast line says that percent is from before the game. So a
    /// finished row prints "Pregame" in front of the same number, in the same
    /// caption type, held whole (`fixedSize`) so the name gives way first and
    /// the qualifier never truncates. Same selection, rounding, withholding and
    /// colour; no number, no word. A suspended row keeps its bare number under
    /// "No result reported" — nothing on it is final.
    @ViewBuilder
    private func preGameOddsLabel(for side: TeamSide, labelled: Bool = false) -> some View {
        let reading = prematch
        // #5363 — the settled row's pre-game number is gated on the pre-match reading itself.
        let prob: Double? = side == .home
            ? reading?.homeProbability
            : (prematchAwayIsWithheld ? nil : reading?.awayProbability)
        if let prob {
            let wasHeavyFavorite = prob > 0.7
            let won = (side == .home && homeWon) || (side == .away && awayWon)
            // #9490 — against the side it beat on the same reading, not a
            // fixed cut: on a three-way board 39.5% can be the favourite.
            let isUpset = won && (reading?.winnerWasUnderdog(
                homeWon: homeWon, awayWon: awayWon, pricesADraw: prematchAwayIsWithheld) ?? false)

            let text = formatProbability(prob, renderedPercent: reading?.percents[side == .home ? 1 : 0])
            if labelled {
                let number = HStack(spacing: 2) {
                    Text(text)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                }
                .foregroundStyle(
                    isUpset ? .orange :
                    (won && wasHeavyFavorite) ? .secondary :
                    .secondary.opacity(0.7)
                )
                VStack(alignment: .leading, spacing: 0) {
                    Text("Pregame win chance")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    number
                        .fixedSize()
                }
            } else if isFinished {
                Text(text)
                    .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                    .foregroundStyle(isUpset ? Color.orange : DS.textSecondaryReadable)
                    .lineLimit(1)
                    .fixedSize()
            } else {
                Text(text)
                    .font(.system(size: min(compactPregameSize, 18), weight: .regular).monospacedDigit())
                    .foregroundStyle(.secondary.opacity(0.7))
                    .lineLimit(1)
            }
        }
    }

    @ViewBuilder
    private var probabilityBar: some View {
        let reading = prematch
        let prematchThreeWayDraw = CompactGameCard12616.hasExplicitThreeWayPrematch(event)
            ? event.prematchOdds?.drawProbability
            : nil
        let currentThreeWayDraw = CompactGameCard12616.hasExplicitThreeWayCurrent(event)
            ? event.currentOdds?.drawProbability
            : nil
        let activeBarThreeWay = isFinished
            ? (prematchThreeWayDraw != nil)
            : (currentThreeWayDraw != nil)
        let notch = CompactGameCard12616.pregameBarNotch(
            prematch: reading,
            prematchDraw: prematchThreeWayDraw,
            barShowsThreeWayDraw: activeBarThreeWay,
            sportPricesADraw: DrawPricedWinner.sportPricesADraw(event.sport),
            isLive: isLive,
            isFinished: isFinished,
            isSuspended: isSuspended
        )
        if isFinished {
            if let reading {
                ProbabilityBar(
                    awayProb: reading.awayProbability,
                    homeProb: reading.homeProbability,
                    drawProb: usesFinishedAccessibilityLayout ? nil : prematchThreeWayDraw,
                    // #5363 — the bar KEEPS its remainder, because the two
                    // segments are a partition and "not the home team" is a
                    // true quantity. What it is not is the away team, so it
                    // loses that team's colour along with its number and reads
                    // as the neutral rest of the whole. The event page settled
                    // this in #5271; the card family follows it exactly.
                    awayColor: prematchAwayIsWithheld
                        ? Color.secondary.opacity(0.25)
                        : awayColor.opacity(0.65),
                    homeColor: homeColor.opacity(0.65),
                    height: usesFinishedAccessibilityLayout ? 4 : 6,
                    notchProb: usesFinishedAccessibilityLayout ? nil : notch
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
                drawProb: currentThreeWayDraw,
                // #5363 — see the settled bar above: the remainder survives, the
                // away team's colour does not.
                awayColor: currentAwayIsWithheld ? Color.secondary.opacity(0.25) : awayColor,
                homeColor: homeColor,
                height: 6,
                animated: isLive,
                glowing: isLive,
                notchProb: notch
            )
        }
    }
}

/// #11325 — when a finished game card takes its accessibility layout.
///
/// At accessibility text sizes the finished Sports card broke "FINAL" mid-word
/// and cut both team names to "Washingt…" / "San Fran…", and the finished
/// Discover card's two-line title stopped at "Washing-/ton Com…". Both cards
/// ask this one question, so they cannot disagree about which cards change:
/// a FINISHED card at an ACCESSIBILITY size. Large and below, and every
/// scheduled, live, suspended or unknown card, keep the layout they had.
enum FinishedCardAccessibility11325 {
    static func applies(isFinished: Bool, typeSize: DynamicTypeSize) -> Bool {
        isFinished && typeSize.isAccessibilitySize
    }
}
