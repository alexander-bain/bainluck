import SwiftUI

/// Projected scoring spectrum: O/U line, pace/actual bars, and threshold ladder.
/// Mirrors the web TotalPointsSpectrum component.
struct TotalPointsSpectrumView: View {
    @ScaledMetric(relativeTo: .caption) private var thresholdColumnWidth: CGFloat = 50
    @ScaledMetric(relativeTo: .caption) private var valueColumnWidth: CGFloat = 36
    let gameMarkets: GameMarketsResponse
    let eventStatus: String?
    /// #4018 — the clock half of "can a final still arrive?"; see `MarketMapView`.
    var commenceTime: Date? = nil
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color
    var sportKey: String?
    var overUnder: Double?
    /// #6290 — `opening_odds.over_under`. See ``MarketMapView/openingOverUnder``
    /// and ``MarketMapRail/pregameLine(isLive:opening:current:)``: this card's
    /// live strip draws a bar labelled "Pre-game", and until now that bar held
    /// ``centerLine``, which mid-game is the live ladder's coin-flip rung.
    var openingOverUnder: Double? = nil
    var homeScore: Int?
    var awayScore: Int?

    /// The sport's own noun for what the total counts. Every string in this
    /// view said "points"; on a US Open match the same widget printed
    /// "Projected total points" over a 26.5 GAME line (ux/1034 B5's class).
    private var vocab: SportVocab { SportVocab.forSport(sportKey) }
    /// "points"/"games"; "scoring" where neither the markets nor the sport
    /// declare a unit and this file must not invent one.
    ///
    /// #3509 — read from the MARKETS on this widget, not from the sport alone.
    /// `vocab.unit` answers "what does tennis quote?" and "games" is the right
    /// answer to that question; it is the wrong answer for the
    /// `"… Total Sets O/U 2.5"` rung the venue files into the same bucket, which
    /// is how this widget came to print "Projected combined games: 2.5+".
    private var unit: String {
        let resolved = vocab.totalsUnit(quotedBy: thresholds.map(\.marketName))
        return resolved.isEmpty ? "scoring" : resolved
    }
    /// The scoreboard's totals, only where they count ``unit`` — for tennis the
    /// scoreboard reports sets, so no actual/pace total is stated at all.
    private var countsTheUnit: Bool { vocab.scoreboardCountsTheUnit }

    private var isLive: Bool { eventStatus == "live" }
    private var isDone: Bool { EventState.isFinished(eventStatus) }

    /// #4018 — see `EventState.canStillBeGraded`. Deliberately NOT folded into
    /// `isPre` itself: that flag ALSO picks minimal-vs-full layout in `body`, and
    /// the two uses need different answers. The projection strip is suppressed
    /// for an abandoned game; the layout choice is *steered* for one, to
    /// `fullView`, because `minimalView` is nothing BUT a pre-game forecast and
    /// gating its contents would leave a card containing only its own heading.
    /// Both call sites therefore name this flag explicitly rather than reading it
    /// through `isPre`.
    private var canStillBeGraded: Bool {
        EventState.canStillBeGraded(eventStatus, commenceTime: commenceTime)
    }
    private var isPre: Bool { !isLive && !isDone }

    /// The game-total rungs this ladder draws, ascending.
    ///
    /// #3925 item 2 — **filtered to ONE contest scope first**, because
    /// `marketType == "game_total"` is not the same question as "belongs on one
    /// axis". The photographed card pooled two families under one "combined
    /// scoring" heading: `Total Sets O/U 3.5 / 4.5` (sets, whole match) and
    /// `Set 1 Games O/U 8.5 / 9.5 / 10.5` (games, inside ONE set), so `4.5+` and
    /// `8.5+` sat next to each other as if on one scale. The rule, its
    /// fail-open, and why this is not a duplicate of the backend's #3161 filter:
    /// ``MarketMapRail/matchScopeLadderIndices(marketNames:)``.
    ///
    /// This also repairs ``unit`` for free, and that is the tell that the pool
    /// was the bug: `totalsUnit` returns `""` when the names disagree, so the
    /// card fell back to the word "scoring" precisely BECAUSE it was holding two
    /// families. One family in, and the specimen names its own noun — "sets".
    ///
    /// 🟢 The old body sorted, then walked the sorted array building `result`
    /// through an `if curProb > prevProb` whose two arms were **the same
    /// `append`**, under a comment ("Clamp to previous to enforce
    /// monotonicity") describing a clamp that was never written. It was
    /// `sorted` spelled out over twelve lines and is deleted rather than carried
    /// past a change to this very function — the next reader would otherwise
    /// take it for a monotonicity guarantee the ladder does not have.
    private var thresholds: [GameMarketOutcome] {
        let candidates = (gameMarkets.totals ?? [])
            .filter { $0.marketType == "game_total" && ($0.overProbability ?? 0) > 0 }

        return MarketMapRail
            .matchScopeLadderIndices(marketNames: candidates.map(\.marketName))
            .map { candidates[$0] }
            .sorted { ($0.threshold ?? 0) < ($1.threshold ?? 0) }
    }

    /// How many rungs the ladder draws, settled or not.
    static let ladderRowLimit = 5

    /// Pick up to ``ladderRowLimit`` representative thresholds for the ladder.
    private var ladderThresholds: [GameMarketOutcome] {
        let picks = Self.ladderIndices(
            sortedThresholds: thresholds.map { $0.threshold ?? 0 },
            finalTotal: actualTotal,
            limit: Self.ladderRowLimit
        )
        return picks.map { thresholds[$0] }
    }

    /// The threshold closest to 50% over probability — the implied O/U line.
    private var centerLine: Double? {
        guard !thresholds.isEmpty else { return nil }
        let center = thresholds.min(by: {
            abs(($0.overProbability ?? 0) - 0.5) < abs(($1.overProbability ?? 0) - 0.5)
        })
        // #3509 — the event-level `overUnder` is quoted in the SPORT's unit, so
        // it is only a legitimate fallback for a widget drawn in that unit.
        // On a bases or sets widget it is a number from another scale.
        return center?.threshold ?? (unit == vocab.unit ? overUnder : nil)
    }

    /// The number this card's strip may label "Pre-game".
    ///
    /// #6290 — ``centerLine`` is the right answer to "what is the line?" and the
    /// wrong answer to "what was the line before the off": mid-game every rung it
    /// picks from is priced on a game in progress. Photographed on event 14780544
    /// (Colts at Chiefs, `live`, 37:45 left, 2026-09-20 18:27 PT): the bar read
    /// **`PRE-GAME 55.5`** beside a pace of 53 and told the reader *"Pace projects
    /// −2.5 vs pre-game expectation"*, when the served pre-game total is `45.5`
    /// and the true sentence is +7.5. A minute earlier the same bar read `55.5`
    /// against a pace of 57 and said `+1.5`; the number a comparison is made
    /// against was itself moving.
    ///
    /// The unit gate is ``centerLine``'s own (#3509): the served opening is
    /// quoted in the SPORT's unit, so a sets or bases widget may not read it.
    private var pregameTotal: Double? {
        MarketMapRail.pregameLine(
            isLive: isLive,
            opening: unit == vocab.unit ? openingOverUnder : nil,
            current: centerLine
        )
    }

    private var sourceCount: Int {
        Set(thresholds.compactMap(\.source)).count
    }

    private var actualTotal: Int? {
        guard isDone, countsTheUnit, let h = homeScore, let a = awayScore else { return nil }
        return h + a
    }

    /// The combined score a rung may be graded against WHILE the game is on.
    ///
    /// #4907. Deliberately a separate property from ``actualTotal`` rather than a
    /// relaxation of its `isDone`: the two answer different questions and only one
    /// of them may reach the heading vocabulary (and its stated final, #9483) or
    /// ``ladderIndices(sortedThresholds:finalTotal:limit:)``. Widening
    /// `actualTotal` would have printed "Final combined goals" over a match in its
    /// 81st minute and re-windowed the ladder onto the step of a total that is
    /// still moving. Everything except the per-rung verdict stays keyed on the
    /// final, which is the only thing that can settle a card.
    ///
    /// The gates are `actualTotal`'s own, with `isLive` swapped for `isDone` —
    /// `countsTheUnit` most of all, since it is what keeps a tennis scoreboard
    /// (which counts SETS) away from a games ladder.
    private var liveTotalSoFar: Int? {
        MarketMapRail.liveGradableTotal(
            isLive: isLive,
            scoreboardCountsTheUnit: countsTheUnit,
            homeScore: homeScore,
            awayScore: awayScore
        )
    }

    // MARK: - What the totals map above has already said (#4782)

    /// The rows the full-game totals map reads — its own filter, not this
    /// card's: the halves are the ones with a `":"`.
    private var fullGameTotals: [GameMarketOutcome] {
        (gameMarkets.totals ?? []).filter { !$0.outcomeName.contains(":") }
    }

    /// The lines the totals map on this same page has already printed.
    ///
    /// Read through ``MarketMapRail/drawnFullTotalRungs(outcomeNames:thresholds:settledTotal:limit:)``,
    /// which is the composition `MarketMapView.totalMapCard` builds its own
    /// ladder from — not a second opinion about it.
    private var totalsMapRungs: [Double] {
        MarketMapRail.drawnFullTotalRungs(
            outcomeNames: fullGameTotals.map(\.outcomeName),
            thresholds: fullGameTotals.map(\.threshold),
            // #7737 — the map's own rule, called rather than restated, so this
            // card asks about the same six rungs the map drew. A different
            // fallback here would make the "already said once" suppression
            // disagree with what is on screen.
            overProbabilities: fullGameTotals.map {
                MarketMapRail.ladderWindowPrice(
                    overProbability: $0.overProbability, probability: $0.probability
                )
            },
            settledTotal: MarketMapRail.fullTotalSettledScore(
                isDone: isDone,
                scoreboardCountsTheSportUnit: countsTheUnit,
                mapUnit: vocab.totalsUnit(quotedBy: fullGameTotals.map(\.marketName)),
                sportUnit: vocab.unit,
                homeScore: gameMarkets.homeScore ?? homeScore,
                awayScore: gameMarkets.awayScore ?? awayScore
            ),
            limit: MarketMapRail.totalMapLadderLimit
        ).map(\.threshold)
    }

    /// Whether this card would take the minimal layout. Named because #4782
    /// needs the answer BEFORE `body` routes on it: the minimal layout is
    /// nothing but one line and its clearing probability, so which numbers this
    /// card is about to print depends on which layout it is about to take.
    private var wouldBeMinimal: Bool {
        thresholds.count < 5 && isPre && canStillBeGraded
    }

    /// The lines this card is about to print, exactly as the two layouts print
    /// them — `minimalView`'s single line, or `ladderView`'s rungs.
    private var printedTotals: [Double] {
        wouldBeMinimal ? [centerLine ?? 0] : ladderThresholds.map { $0.threshold ?? 0 }
    }

    /// Every line this card would print is already on the map card above it.
    private var restatesTheMap: Bool {
        MarketMapRail.totalsAreRestated(
            printing: printedTotals, alreadyShown: totalsMapRungs
        )
    }

    /// #4782 — what is left when the restated numbers go.
    ///
    /// The ladder and the minimal line are the whole of this card's overlap with
    /// the map; the projection strip is the part the map cannot say (the pace
    /// narrative). So a restating card keeps its strip and drops its rows —
    /// unless it has no strip, in which case dropping the rows would leave a
    /// heading over nothing, and #4018 already ruled on that shape: a card that
    /// is only its own heading does not draw.
    ///
    /// #9483 — a finished card has no strip any more (see ``projectionTense``),
    /// so a finished card whose every rung the map already drew goes whole.
    private var saysNothingNew: Bool {
        MarketMapRail.spectrumDrawsNothingNew(
            printing: printedTotals,
            alreadyShown: totalsMapRungs,
            isMinimalLayout: wouldBeMinimal,
            hasProjectionStrip: strip != nil
        )
    }

    var body: some View {
        if thresholds.isEmpty { EmptyView() }
        else if saysNothingNew { EmptyView() }
        // #4018 — `canStillBeGraded` GATES THE LAYOUT CHOICE, NOT JUST THE STRIP,
        // and this line is the second half of the fix. `isPre` is TRUE for an
        // abandoned game (it is neither live nor finished), so a suspended match
        // holding fewer than five rungs was routed to `minimalView` and never
        // reached the gate in `projectionStrip` at all: on the NPB specimen
        // (Eagles v Marines, started Sep 9, no result) the card went on reading
        // **`PRE-GAME LINE 5.5`** with a 99% clearance bar, under a "Projected
        // scoring" heading, for a game nobody will grade.
        //
        // The remedy is to STEER rather than to blank. `minimalView` is nothing
        // but a pre-game forecast, so suppressing its contents would leave a card
        // that is only a heading; `fullView` already draws the honest version of
        // this state — the strip suppressed, the threshold ladder kept — so an
        // ungradeable game is sent there and the reader keeps the real prices.
        else if wouldBeMinimal {
            minimalView
        } else {
            fullView
        }
    }

    // MARK: - Minimal View (few thresholds, pre-game)

    private var minimalView: some View {
        let ouLine = centerLine ?? 0
        let centerProb = thresholds.min(by: {
            abs(($0.overProbability ?? 0) - 0.5) < abs(($1.overProbability ?? 0) - 0.5)
        })?.overProbability ?? 0.5

        return VStack(alignment: .leading, spacing: 12) {
            header
            HStack(alignment: .top, spacing: 20) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("PRE-GAME LINE")
                        .font(.system(size: 9, weight: .semibold))
                        .tracking(0.5)
                        .foregroundStyle(.secondary)
                    Text(formatThreshold(ouLine))
                        .font(.system(size: 28, weight: .bold, design: .monospaced))
                    Text("combined \(unit)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Probability the total clears \(formatThreshold(ouLine))")
                        .font(.system(size: 9, weight: .semibold))
                        .tracking(0.5)
                        .foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.secondary.opacity(0.15))
                                    .frame(height: 8)
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.blue)
                                    .frame(width: geo.size.width * min(1, centerProb), height: 8)
                            }
                        }
                        .frame(height: 8)
                        // #9392 — the same clamp as the rungs below.
                        Text(MarketMapRail.rungPercentText(centerProb))
                            .font(.caption.monospacedDigit().weight(.bold))
                            .lineLimit(1)
                            .fixedSize()
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Full View

    private var fullView: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            projectionStrip
            // #4782 — the map card above owns the distribution. Where it has
            // already drawn every one of these rungs, repeating them a
            // screen-third lower in a second notation (`Over 5.5` there, `5.5+`
            // here) tells the reader nothing and reads as a different quantity.
            if !restatesTheMap { ladderView }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Header

    /// The two types the card's headings are set in, as statics for the same
    /// reason ``captionFont`` is one: #3930 widens the vocabulary both of them
    /// print, and a test that measured a *retyped* `.subheadline.semibold`
    /// would be measuring a string the card does not draw. Neither slot has a
    /// fixed frame, so what
    /// `TotalPointsSpectrumTenseTests.testTheSettledHeadingsFitWhereTheShippingOnesDo`
    /// asserts is relative: no new heading is wider than the longest one this
    /// slot already ships.
    static let sectionTitleFont = Font.subheadline.weight(.semibold)
    static let ladderTitleFont = Font.caption.weight(.semibold)

    private var header: some View {
        HStack {
            Text(MarketMapRail.spectrumSectionTitle(
                finalTotal: actualTotal, isSettled: isDone, canStillBeGraded: canStillBeGraded
            ))
                .font(Self.sectionTitleFont)
            Spacer()
            if sourceCount > 1 {
                Text("\(sourceCount) sources")
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(0.5)
                    .textCase(.uppercase)
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 4))
            }
        }
    }

    // MARK: - Projection Strip

    /// Which of the strip's tenses this page is in, or `nil` for none.
    ///
    /// #4018 — an abandoned game matches NONE of them, and that is the intended
    /// outcome: it has no pre-game expectation worth stating in the present
    /// tense, no pace, and no final. The strip is absent rather than re-worded,
    /// which is the same trade `EventState.noGameMarketsLine` makes — drop the
    /// false promise and claim nothing in its place.
    ///
    /// #4782 lifted this out of `projectionStrip`'s `if`/`else if` chain because
    /// ``saysNothingNew`` has to know whether a strip will draw BEFORE the body
    /// routes. Asking the question twice is how the two answers drift, and the
    /// cost of drift here is a card rendered as a bare heading.
    ///
    /// #9483 — there is no `final` tense. A finished card used to draw a
    /// "Final total runs / 7" tile in 28 pt over the SD 3 – MIL 4 page, a third
    /// statement of a score the hero and the runs map above it already state.
    /// The final is now said once, in the ladder's heading
    /// (``MarketMapRail/spectrumLadderTitle(finalTotal:unit:isSettled:canStillBeGraded:)``),
    /// and only when the ladder has a rung of its own to show.
    enum ProjectionTense { case pregame, live }

    /// The strip this card draws, as a rule the tests can ask.
    ///
    /// The view's own `isPre`/`isLive` are read off the same status here: not
    /// live and not finished is pre-game. A finished status returns `nil` for
    /// every other input, which is #9483.
    static func projectionTense(
        eventStatus: String?,
        canStillBeGraded: Bool,
        scoreboardCountsTheUnit: Bool,
        hasLiveProjection: Bool
    ) -> ProjectionTense? {
        let isLive = eventStatus == "live"
        let isPre = !isLive && !EventState.isFinished(eventStatus)
        if isPre, canStillBeGraded { return .pregame }
        if isLive, scoreboardCountsTheUnit, hasLiveProjection { return .live }
        return nil
    }

    /// #9708 — the served pace, only when it has standing against the header's
    /// score (``LivePaceStanding``): never a scoreless 0, never an older score.
    /// #9944 — anchored to `pregameTotal`, so the strip's PRE-GAME and PACE
    /// read one opening number, never five runs in the 1st run forward to 90.
    private var liveProjection: (projected: Double, scored: Int)? {
        LivePaceStanding.projection(gameMarkets.pace, openingTotal: pregameTotal,
                                    scoreboardHome: homeScore, scoreboardAway: awayScore)
    }

    private var strip: ProjectionTense? {
        Self.projectionTense(
            eventStatus: eventStatus,
            canStillBeGraded: canStillBeGraded,
            scoreboardCountsTheUnit: countsTheUnit,
            hasLiveProjection: liveProjection != nil
        )
    }

    @ViewBuilder
    private var projectionStrip: some View {
        // #6290 — `pregameTotal`, not `centerLine`: before the off the two are the
        // same number and the pre-game strip is unchanged; live, only a served
        // opening may be labelled "Pre-game", and there may be none. The local is
        // no longer called `ouLine`, because it is no longer the O/U line.
        let pregame = pregameTotal

        switch strip {
        case .pregame:
            preGameStrip(ouLine: pregame ?? 0)
        case .live:
            if let live = liveProjection {
                liveStrip(pregameTotal: pregame, paceTotal: live.projected, scored: live.scored)
            }
        case nil:
            EmptyView()
        }
    }

    private func preGameStrip(ouLine: Double) -> some View {
        let expected = Int(ouLine.rounded())
        let scaleMax = Double(expected) * 1.12

        return VStack(alignment: .leading, spacing: 8) {
            Text("Expected total \(unit)")
                .font(.caption)
                .fontWeight(.semibold)
            projectionBar(label: "Pre-game", value: Double(expected), scaleMax: scaleMax,
                          barColor: Color.secondary.opacity(0.55), labelColor: .primary, bold: true)
        }
        .padding(12)
        .background(Color.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    /// The strip while the game is on.
    ///
    /// #6290 — `pregameTotal` is OPTIONAL and both of its readers are gated on it,
    /// because a live card that has no served opening has no pre-game number at
    /// all: it must not label the live line "Pre-game", and it must not compare
    /// the pace against it. What is left — the pace bar, the score, the projected
    /// remainder — is every number on this strip that was ever measured rather
    /// than inferred, so the strip stays rather than being dropped whole.
    private func liveStrip(pregameTotal: Double?, paceTotal: Double, scored: Int) -> some View {
        let scaleMax = max(pregameTotal ?? 0, paceTotal) * 1.12
        let projRemaining = paceTotal - Double(scored)
        let paceColor = Color(hex: "#8B5CF6")

        return VStack(alignment: .leading, spacing: 8) {
            Text("Projected total \(unit)")
                .font(.caption)
                .fontWeight(.semibold)
            if let pregame = pregameTotal {
                projectionBar(label: "Pre-game", value: pregame, scaleMax: scaleMax,
                              barColor: Color.secondary.opacity(0.55), labelColor: .secondary, bold: false)
            }
            // Pace bar with scored portion solid
            paceBar(scored: scored, paceTotal: paceTotal, scaleMax: scaleMax, color: paceColor)
            HStack(spacing: 0) {
                Text("\(scored)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(paceColor)
                Text(" scored")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
                if projRemaining > 0 {
                    Text(" · +\(Int(projRemaining.rounded())) projected")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.leading, 68)

            if let pregame = pregameTotal, abs(paceTotal - pregame) > 0.5 {
                let diff = paceTotal - pregame
                HStack(spacing: 4) {
                    Text("Pace projects")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("\(diff > 0 ? "+" : "")\(String(format: "%.1f", diff))")
                        .font(.caption2.monospacedDigit().weight(.semibold))
                        .foregroundStyle(paceColor)
                    Text("vs pre-game expectation.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Ladder

    private var ladderView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(MarketMapRail.spectrumLadderTitle(
                finalTotal: actualTotal, unit: unit, isSettled: isDone,
                canStillBeGraded: canStillBeGraded
            ))
                .font(Self.ladderTitleFont)
                .padding(.bottom, 4)

            ForEach(Array(ladderThresholds.enumerated()), id: \.offset) { _, item in
                ladderRow(item)
            }
        }
    }

    /// #3850 — the colours the verdict badge has always used, lifted to statics
    /// so `MarketMapView.ladderResultColor` and this badge cannot drift. That
    /// function's own comment already says these two hexes are "TotalPointsSpectrumView's
    /// own, to the hex, because that view already grades a settled totals ladder
    /// on this same event page and two settled ladders in two colours is a third
    /// bug" — this is the other end of that sentence.
    static let verdictHit = Color(hex: "#10B981")
    static let verdictMiss = Color.red
    /// Nothing happened, so nothing is coloured as though it had — matching
    /// `MarketMapView.ladderResultColor`.
    static let verdictPush = Color.secondary

    static func verdictColor(_ result: MarketMapRail.TotalLadderResult) -> Color {
        switch result {
        case .over: return verdictHit
        case .under: return verdictMiss
        case .push: return verdictPush
        }
    }

    /// The type the ungraded rung's caption is set in, as statics so the test
    /// that sizes the column below cannot measure a different string to the one
    /// the card draws. `MarketMapLadderTests` had to restate its font inline
    /// because the view it measures is private, and then needed a second test to
    /// pin the two together; exposing them removes that whole failure mode.
    static let captionFont = Font.system(size: 8, weight: .semibold)
    static let captionTracking: CGFloat = 0.5

    /// How much room the ungraded rung's caption gets.
    ///
    /// #3925. **Measured, and here is the thing that measured it:**
    /// `TotalPointsSpectrumRungCaptionTests.testTheCaptionColumnHoldsBothCaptions`
    /// lays out every string ``MarketMapRail/spectrumRungCaption(finalTotal:isSettled:)``
    /// can return, in the type above, and fails if any of them wants more room
    /// than this. Run against a deliberately tiny constant it reports the answer:
    ///
    /// ```
    /// 'LAST QUOTE' 58.666666666666664 pt, 'PRE-GAME' 49.0 pt
    /// ```
    ///
    /// 🔴 **SO THE STRING SWAP ON ITS OWN WOULD HAVE SHIPPED A TRUNCATED
    /// CAPTION.** The slot was a bare `.frame(width: 52)` that nothing had ever
    /// measured. It holds `PRE-GAME` — by 3 pt — which is exactly why it never
    /// looked like part of this bug; and it is **6.7 pt too small for the word
    /// that replaces it**. `LAST QUO…`, or the whole caption dropped, would have
    /// been a worse card than the one #3925 photographed, and no test that
    /// checks the *string* could have caught it. This is #3552's class to the
    /// letter — the fix's own truncation, found only because the column was
    /// measured (`MarketMapLadderLayout.labelColumnWidth`, where
    /// `Sabalenka +5.5` was eaten out of the ladder next to this one).
    ///
    /// 64 is the 58.7 pt measurement plus a deliberate 5.3 pt. The font is a
    /// fixed `.system(size: 8)` rather than a text style, so it does not scale
    /// with Dynamic Type and the margin only has to cover a future rewording —
    /// which `testTheOldFiftyTwoPointColumnCouldNotHaveHeldTheSettledCaption`
    /// requires to stay above 4 pt.
    ///
    /// The 12 pt comes out of the bar, the only flexible element in the row,
    /// leaving it ~162 pt on the narrowest phone card. The bar is the data and
    /// the caption is its tense, so `testWideningTheCaptionDidNotCostTheBarItsDominance`
    /// holds the bar at more than twice this column.
    static let captionColumnWidth: CGFloat = 64

    /// The ungraded rung's number, as statics for the same reason as the caption
    /// above: the test that sizes its column measures THIS font.
    static let percentFont = Font.system(size: 11).monospacedDigit().weight(.semibold)

    /// How much room the ungraded rung's number gets.
    ///
    /// #9392. It was a bare `.frame(width: 32)` with no `lineLimit`, which
    /// nothing had measured — and `100%` does not fit it at 11 pt, so the live
    /// Maldives @ Kyrgyz Republic page (`15317879`, 2026-09-28) printed `100`
    /// with the `%` wrapped onto a second line. The number is now `>99%` (the
    /// app's rule), which is no narrower. `TotalsRungPrintsTheHerosClamp9392Tests
    /// .testThePercentColumnHoldsEveryRungNumber` lays out every shape
    /// `rungPercentText` returns in `percentFont` and fails if one wants more.
    static let percentColumnWidth: CGFloat = 38

    /// One rung of the ladder.
    ///
    /// #3850. A settled rung and an unsettled rung say different things, and the
    /// bug was that this row said the unsettled thing either way.
    ///
    /// 🔴 **`PRE-GAME` WAS PRINTED UNCONDITIONALLY, OVER `overProbability` — WHICH
    /// IS THE PRICE RIGHT NOW.** On a finished game that is the *settlement*
    /// price, so the card captioned a settled 99% as a pre-game forecast. On the
    /// photographed specimen (event 15305475, 11 runs) the `10.5` rung read
    /// `PRE-GAME … 99%`; it opened at **32%**. The caption named a tense
    /// explicitly, which is what makes it worse than #3823's rung, which only
    /// implied one.
    ///
    /// 🟠 **WHY NOT JUST SHOW THE RECOVERED OPENING?** The issue offered that as
    /// option (1) — every totals row carries `movement`, and
    /// `current - movement` reconstructs a sane monotone opening curve
    /// (`0.755 → 0.235` on this specimen). It is REFUSED, and not on taste:
    ///
    /// 1. **The client cannot tell a pre-game opening from a mid-game one.**
    ///    `GET /api/events/{id}/game-markets` serves `movement` and **no capture
    ///    timestamp** — measured 2026-09-07, the full key set of a totals row is
    ///    `threshold · over_probability · source · market_type · market_name ·
    ///    outcome_name · is_winner · resolution_source · movement · period`.
    ///    Server-side, `futures_outcomes.opening_captured_at` says **28** of the
    ///    566 settled totals rows that have an opening captured it **52–172
    ///    minutes AFTER first pitch**. Captioning one of those `PRE-GAME` is the
    ///    same bug wearing a fix, and from here it is undetectable.
    /// 2. **Half the population has no opening at all** — **599 of 1,165** settled
    ///    totals rows (51.4%) carry `opening_probability IS NULL`, so option (1)
    ///    has nothing to show for them and the card would go mixed-tense.
    ///
    /// So: option (2), and the same move #3823 made — a number whose tense you
    /// cannot vouch for is worse than no number. The BAR stays, exactly as #3823
    /// left its own: it draws the step (0.99 above the final, 0.01 below) and was
    /// never the thing making a false claim.
    ///
    /// 🟢 **THE PUSH COMES FREE.** The old grade was `Double(actual) >= threshold`,
    /// which calls a line the game landed exactly on a HIT when it is a push.
    /// Routing through ``MarketMapRail/totalLadderResult(threshold:finalTotal:)``
    /// — the rule #3823 already wrote, tested and documented as being for exactly
    /// this call site — fixes it without a second grader to drift out of step.
    private func ladderRow(_ item: GameMarketOutcome) -> some View {
        let prob = item.overProbability ?? 0
        let threshold = item.threshold ?? 0
        // #4907 — a rung the score has ALREADY cleared reads as hit while the game
        // is still on, instead of pricing a thing that has happened. The live
        // grade is the fallback, never an override: a finished game keeps
        // `totalLadderResult`'s three-way verdict, and `liveTotalSoFar` is nil
        // there anyway (`isLive` and `isDone` cannot both hold).
        //
        // 🔴 `item.threshold`, NOT the `threshold` above. That one defaults a
        // missing line to `0` so the row can still draw "0+", and any positive
        // score is greater than 0 — grading through it would stamp `HIT` on every
        // rung whose line failed to parse. A rung with no line is not gradeable.
        let result = actualTotal.map {
            MarketMapRail.totalLadderResult(threshold: threshold, finalTotal: $0)
        } ?? liveTotalSoFar.flatMap { soFar in
            item.threshold.flatMap {
                MarketMapRail.liveTotalLadderResult(
                    threshold: $0, scoreSoFar: soFar, marketName: item.marketName
                )
            }
        }

        return VStack(spacing: 0) {
            Divider()
            HStack(spacing: 10) {
                Text("\(formatThreshold(threshold))+")
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: thresholdColumnWidth, alignment: .leading)

                // Whether this row is captioned at all, and with which word, is
                // ``MarketMapRail/spectrumRowCaption(finalTotal:isSettled:canStillBeGraded:hasStarted:rungResult:)``
                // — all four clauses, with the reasoning for each. #4018 put the
                // `canStillBeGraded` gate here as an inline `if`; #4907 needed a
                // third clause (a row that already says `HIT` wears no tense) and
                // moved the whole decision to where it can be asserted without
                // rasterising this view. #7655 added the fourth: `PRE-GAME` over a
                // live price. The `.settled` copy question that #4018 routed to
                // Alex is recorded there too.
                //
                // `hasStarted` is the CLOCK, not the status — `isPre` would have
                // done for a well-behaved `live` row, but a `scheduled` status that
                // has not caught up with kickoff is precisely the row whose prices
                // are live while its status says otherwise.
                if let caption = MarketMapRail.spectrumRowCaption(
                    finalTotal: actualTotal,
                    isSettled: isDone,
                    canStillBeGraded: canStillBeGraded,
                    hasStarted: isLive || EventState.hasStarted(commenceTime: commenceTime),
                    rungResult: result
                ) {
                    Text(caption)
                        .font(Self.captionFont)
                        .tracking(Self.captionTracking)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .frame(width: Self.captionColumnWidth, alignment: .leading)
                }

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.secondary.opacity(0.12))
                            .frame(height: 5)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.secondary.opacity(0.5))
                            .frame(width: geo.size.width * min(1, prob), height: 5)
                    }
                }
                .frame(height: 5)

                if let result {
                    Text(MarketMapRail.totalLadderResultLabel(result))
                        .font(.system(size: 9, weight: .bold))
                        .tracking(0.3)
                        .foregroundStyle(Self.verdictColor(result))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Self.verdictColor(result).opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .frame(width: 50)
                } else {
                    // #9392 — `>99%` like the hero, on ONE line. The old bare
                    // 32 pt frame had no `lineLimit` and held neither `100%`
                    // nor `>99%` at this size: the live Maldives page printed
                    // `100` with the `%` wrapped under it.
                    Text(MarketMapRail.rungPercentText(prob))
                        .font(Self.percentFont)
                        .lineLimit(1)
                        .frame(width: Self.percentColumnWidth, alignment: .trailing)
                }
            }
            .padding(.vertical, 8)
        }
    }

    // MARK: - Reusable Bar Components

    private func projectionBar(label: String, value: Double, scaleMax: Double,
                               barColor: Color, labelColor: Color, bold: Bool) -> some View {
        HStack(spacing: 8) {
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.5)
                .foregroundStyle(labelColor)
                .frame(width: 60, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.secondary.opacity(0.12))
                        .frame(height: 7)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(barColor)
                        .frame(width: geo.size.width * min(1, value / scaleMax), height: 7)
                }
            }
            .frame(height: 7)

            Text(formatValue(value))
                .font(.caption.monospacedDigit())
                .fontWeight(bold ? .semibold : .regular)
                .foregroundStyle(labelColor)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .frame(minWidth: valueColumnWidth, alignment: .trailing)
        }
    }

    private func paceBar(scored: Int, paceTotal: Double, scaleMax: Double, color: Color) -> some View {
        HStack(spacing: 8) {
            Text("PACE")
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.5)
                .foregroundStyle(color)
                .frame(width: 60, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.secondary.opacity(0.12))
                        .frame(height: 7)
                    // Ghost bar for projected total
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color.opacity(0.25))
                        .frame(width: geo.size.width * min(1, paceTotal / scaleMax), height: 7)
                    // Solid bar for scored portion
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color)
                        .frame(width: geo.size.width * min(1, Double(scored) / scaleMax), height: 7)
                }
            }
            .frame(height: 7)

            Text(formatValue(paceTotal))
                .font(.caption.monospacedDigit().weight(.semibold))
                .foregroundStyle(color)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .frame(minWidth: valueColumnWidth, alignment: .trailing)
        }
    }

    // MARK: - Formatting Helpers

    private func formatThreshold(_ value: Double) -> String {
        value.truncatingRemainder(dividingBy: 1) == 0
            ? "\(Int(value))"
            : String(format: "%.1f", value)
    }

    private func formatValue(_ value: Double) -> String {
        value.truncatingRemainder(dividingBy: 1) == 0
            ? "\(Int(value))"
            : String(format: "%.1f", value)
    }
}

// MARK: - Which rungs the ladder draws (#3850)

extension TotalPointsSpectrumView {
    /// The indices of ``thresholds`` this card should draw, in order.
    ///
    /// #3850. Two different questions, and the answer flips entirely once the
    /// game is over — which is the whole reason this is one function rather than
    /// a `prefix` at the call site.
    ///
    /// **Unsettled (`finalTotal == nil`)** — stride the whole ladder so the five
    /// rungs span the range of lines on offer. Unchanged behaviour, moved here so
    /// the settled branch has somewhere to live beside it.
    ///
    /// **Settled** — defer to ``MarketMapRail/settledLadderWindow(sortedThresholds:finalTotal:limit:)``,
    /// the rule #3823 landed for the Runs-map ladder on this same event page.
    ///
    /// 🔴 **THE WINDOW IS NOT A COSMETIC HALF OF THIS FIX — WITHOUT IT THE FIX
    /// SHOWS NOTHING.** #3823 put it this way: the window fault "is the one that
    /// survives fixing the first". Measured on the specimen this issue was filed
    /// against — event 15305475 (Minnesota 1 — Chicago WS 10, **11 runs**), whose
    /// eleven lines run `2.5 … 12.5` — the stride picks `step = 11/5 = 2`, so
    /// indices `0,2,4,6,8` = `2.5 · 4.5 · 6.5 · 8.5 · 10.5`. Every one of those is
    /// under 11, so grading the OLD selection would have traded five identical
    /// `99%`s for five identical `HIT`s and taught the reader nothing. It never
    /// samples `11.5`, the first line the game failed to clear — the one rung that
    /// says what the total actually was. `settledLadderWindow` centres on that
    /// step, so the card reads `… 10.5 HIT · 11.5 MISS …` and **the reader gets
    /// "11" off the step without the card printing the word**.
    /// `testTheOldStrideWouldHaveShownFiveIdenticalVerdicts` is that measurement
    /// as a test, so the argument cannot quietly stop being true.
    ///
    /// - Parameters:
    ///   - sortedThresholds: the lines, ascending — `thresholds` already sorts.
    ///   - finalTotal: the score this card may grade against, or nil while the
    ///     game can still decide it. Gated by ``actualTotal``, which additionally
    ///     requires the scoreboard to count this card's own unit.
    ///   - limit: how many rungs to draw.
    static func ladderIndices(
        sortedThresholds: [Double],
        finalTotal: Int?,
        limit: Int
    ) -> [Int] {
        let count = sortedThresholds.count
        guard count > 0, limit > 0 else { return [] }
        guard count > limit else { return Array(0 ..< count) }

        if let finalTotal {
            return Array(MarketMapRail.settledLadderWindow(
                sortedThresholds: sortedThresholds,
                finalTotal: finalTotal,
                limit: limit
            ))
        }

        // The original carried a "top up with the last line if the stride ran
        // short" branch here. It is DELETED rather than moved, because past this
        // point it cannot fire: `step = floor(count/limit)` gives
        // `count/step >= limit`, so the stride yields exactly `limit` picks
        // whenever `count > limit`, which the guard above has already
        // established. `testTheStrideAlwaysFillsTheLadder` sweeps every count
        // from `limit + 1` to 40 and is the proof — dead code that looks like a
        // safety net is worse than no net, because the next reader trusts it.
        let step = max(1, count / limit)
        var picks: [Int] = []
        var i = 0
        while i < count, picks.count < limit {
            picks.append(i)
            i += step
        }
        return picks
    }
}
