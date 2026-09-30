import SwiftUI

/// ESPN-style game play card: floating over the page chart's plot under a finger
/// (#9517), and above the fullscreen chart's plot (#925).
/// Updates as the user scrubs across the chart, showing:
/// - Score (team-colored)
/// - Period and clock
/// - Scoring play description (when hovering over one)
/// - Win probability (when between scoring plays)
struct GamePlayCardView: View {
    /// The scrubbed moment. The page builds this card without one; the chart,
    /// which owns the scrub, supplies it where it places the card (#8651).
    var selectedPoint: GamePlayPoint? = nil
    let homeTeam: String
    let awayTeam: String
    var homeTeamColor: Color = .primary
    var awayTeamColor: Color = .primary
    var homeTeamLogo: String?
    var awayTeamLogo: String?
    /// Most recent chart point (shown when not scrubbing)
    var lastPoint: GamePlayPoint?
    /// #9185 — both sides' chances print on EVERY moment, a scoring play
    /// included. The fullscreen chart sets it: it covers the page hero, so a
    /// scoring play's description in place of the numbers left the reader with
    /// no number anywhere on screen.
    var pinsProbabilities = false
    /// #9015 — the game is over. A line's settled end (exactly 0 or 1) is then
    /// the result and prints 100% / 0%, not the live `>99%` / `<1%`.
    var gameFinished = false
    /// #8651 — the card floats over the plot as the inline chart's scrub
    /// tooltip. Nothing sits beneath a floating card, so no row holds a fixed
    /// height for a plot that must not move (see the two-line box in `body`).
    var floats = false

    private var point: GamePlayPoint? {
        selectedPoint ?? lastPoint
    }

    /// #8651 — this card showing `point` as the scrubbed moment. The chart
    /// calls it with its own selection so a scrub never reaches page state.
    func showing(_ point: GamePlayPoint?) -> GamePlayCardView {
        var card = self
        card.selectedPoint = point
        return card
    }

    /// #8652 — this card resting on the chart's own last drawn point, so the
    /// unscrubbed readout prints the number the line ends on. Nil keeps the
    /// page's point (a chart with no primary line has no end to name).
    /// #9185 — this card with its probability row pinned (see `pinsProbabilities`).
    func pinningProbabilities() -> GamePlayCardView {
        var card = self
        card.pinsProbabilities = true
        return card
    }

    /// #8651 — this card floating over the plot (see `floats`).
    func floating() -> GamePlayCardView {
        var card = self
        card.floats = true
        return card
    }

    /// #9015 — this card on a game that is over (see `gameFinished`).
    func finished(_ finished: Bool) -> GamePlayCardView {
        var card = self
        card.gameFinished = finished
        return card
    }

    /// #9185 — which rows print for `point`: the probability row, the play
    /// row, or both. Off the fullscreen chart a scoring play still takes the
    /// probability row's place, as #925 laid it out.
    static func rows(for point: GamePlayPoint, pinsProbabilities: Bool) -> (probabilities: Bool, play: Bool) {
        let play = point.scoringPlay != nil
        return (pinsProbabilities || !play, play)
    }

    func resting(on point: GamePlayPoint?) -> GamePlayCardView {
        guard let point else { return self }
        var card = self
        card.lastPoint = point
        return card
    }

    var body: some View {
        if let point {
            // #925 — this card now sits ABOVE the plot (see `OddsChartView.readout`)
            // and is laid out in two rows so nothing has to share a line it
            // cannot fit on: the moment (state · score) first, the probabilities
            // on a full-width line under it. Alex's build-20 recording showed
            // the old single row squeezing "Cowboys 99% — Commanders 1%" into a
            // third of the width, where SwiftUI broke each NAME mid-word
            // ("Cow-/boys", "Comman-/ders"). Every name and number below is one
            // unbreakable run; when a row cannot fit it re-stacks rather than
            // hyphenate, and only the last arrangement may shrink the type.
            VStack(alignment: .leading, spacing: 4) {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .center, spacing: 10) {
                        stateLine(point)
                        scoreView(point)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        stateLine(point)
                        scoreView(point)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        stateStack(point)
                        scoreView(point)
                    }
                }

                // Play description or probability context — in a box that is
                // always TWO lines tall at the current type size (#925). This
                // row sits above the plot now, so any change in its height moves
                // the plot under the finger that is scrubbing it: measured at
                // 375pt, scrubbing onto a field goal (type line + description)
                // pushed the plot down 14pt from a one-line probability row.
                let rows = Self.rows(for: point, pinsProbabilities: pinsProbabilities)
                if floats {
                    if rows.probabilities { probabilities(point) }
                    if rows.play, let play = point.scoringPlay { playRow(play) }
                } else if pinsProbabilities {
                    // #9185 — the numbers on a line of their own, then the play
                    // (or nothing) in the same fixed two-line box, so the plot
                    // still does not move under a scrubbing finger.
                    probabilities(point)
                    ZStack(alignment: .topLeading) {
                        Text(verbatim: "X\nX")
                            .font(.caption2)
                            .hidden()
                            .accessibilityHidden(true)
                        if rows.play, let play = point.scoringPlay { playRow(play) }
                    }
                } else {
                    ZStack(alignment: .topLeading) {
                        Text(verbatim: "X\nX")
                            .font(.caption2)
                            .hidden()
                            .accessibilityHidden(true)
                        detail(point)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 4)
        }
    }

    @ViewBuilder
    private func detail(_ point: GamePlayPoint) -> some View {
        if let play = point.scoringPlay {
            playRow(play)
        } else {
            probabilities(point)
        }
    }

    @ViewBuilder
    private func playRow(_ play: ScoringPlay) -> some View {
        // One wrapping run, type first: two separate lines (type, then a
        // two-line description) made this row three lines tall.
        let description = play.description ?? play.shortText ?? ""
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Circle()
                .fill(.red)
                .frame(width: 5, height: 5)
                .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
            if let type = play.type, !type.isEmpty {
                Text("\(Text(type).foregroundStyle(.secondary)) · \(description)")
                    .font(.caption2)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
            } else {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
            }
        }
    }

    /// Both sides' chances for `point`, as one line where it fits (#925).
    @ViewBuilder
    private func probabilities(_ point: GamePlayPoint) -> some View {
        let printed = Self.printedLabels(home: point.homeProb, away: point.awayProb,
                                         gameFinished: gameFinished)
        let homeProb = printed.home
        let awayProb = printed.away
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 0) {
                probRun(homeShort, homeProb, homeTeamColor)
                if let awayProb {
                    Text(" — ")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize()
                    probRun(awayShort, awayProb, awayTeamColor)
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                probRun(homeShort, homeProb, homeTeamColor)
                if let awayProb { probRun(awayShort, awayProb, awayTeamColor) }
            }
            // Last resort (the largest accessibility sizes on the narrowest
            // phone): shrink, never hyphenate a name.
            VStack(alignment: .leading, spacing: 0) {
                probRun(homeShort, homeProb, homeTeamColor, shrinks: true)
                if let awayProb { probRun(awayShort, awayProb, awayTeamColor, shrinks: true) }
            }
        }
    }

    /// Game-state badge (period + clock), the wall-clock time of the point,
    /// and — when the state is carried from an older row — the time it was
    /// actually seen (#925). One line.
    @ViewBuilder
    private func stateLine(_ point: GamePlayPoint) -> some View {
        HStack(spacing: 6) { stateParts(point) }
    }

    /// The same three parts, stacked, for when one line cannot hold them.
    @ViewBuilder
    private func stateStack(_ point: GamePlayPoint) -> some View {
        VStack(alignment: .leading, spacing: 2) { stateParts(point) }
    }

    @ViewBuilder
    private func stateParts(_ point: GamePlayPoint) -> some View {
        if !point.timeDisplay.isEmpty {
            Text(point.timeDisplay)
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(Color.gray.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 4))
        }
        // #8651 — a floating card rides pre-game charts that span days, where a
        // bare "3:50 AM" names no day; the axis beneath it prints "Mon 1 AM".
        let wallClock = floats ? point.datedWallClockDisplay : point.wallClockDisplay
        if !wallClock.isEmpty {
            Text(wallClock)
                .font(.caption2)
                .monospacedDigit()
                .foregroundStyle(.tertiary)
                .lineLimit(1)
                .fixedSize()
        }
        if let asOf = point.stateAsOfDisplay {
            Text(asOf)
                .font(.caption2)
                .monospacedDigit()
                .foregroundStyle(.tertiary)
                .lineLimit(1)
                .fixedSize()
        }
    }

    @ViewBuilder
    private func scoreView(_ point: GamePlayPoint) -> some View {
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
            .fixedSize()
        }
    }

    /// One side's name and chance as ONE run that cannot break (#925).
    /// `shrinks` is the last-resort arrangement's permission to scale the type
    /// down instead of clipping; no arrangement may wrap inside a name.
    private func probRun(_ name: String, _ pct: String, _ color: Color, shrinks: Bool = false) -> some View {
        HStack(spacing: 0) {
            Text(name).foregroundStyle(.secondary)
            Text(" \(pct)").fontWeight(.semibold).foregroundStyle(color)
        }
            .font(.caption2)
            .lineLimit(1)
            .minimumScaleFactor(shrinks ? 0.5 : 1)
            .fixedSize(horizontal: !shrinks, vertical: false)
    }

    /// #9015 — the two whole percents this card prints for one chart moment.
    ///
    /// Each side used to be rounded on its own, so a half-cent moment printed
    /// both halves up: Oregon at USC's 02:10Z point (home 0.255) read
    /// "Trojans 26% — Ducks 75%" under a hero that said 25%. The pair goes
    /// through the same duel rule as the hero and every game card — the
    /// favourite rounded once, the other side `100 −` it. No served values:
    /// a chart point is not `current_odds` (see `duelPercents`).
    ///
    /// #5271 — the away half exists only where an away price does. On a
    /// draw-priced sport `away` is nil and the home side prints alone.
    static func printedPercents(home: Double, away: Double?) -> (home: Int, away: Int?) {
        guard let away else {
            return (renderedPercent(home) ?? 0, nil)
        }
        let pair = complementDisplayPercents(away: away, home: home)
        return (pair[1] ?? 0, pair[0])
    }

    /// #9015 — the two percents as the card prints them. `printedPercents`
    /// decides the integers; `formatProbability` keeps its `<1%` / `>99%` claim
    /// about the value, as the hero does. A bare integer printed a live 0.996
    /// as "Jaguars 100% — Patriots 0%" under a hero reading ">99%" / "<1%"
    /// (Patriots at Jaguars, 14782706, 4th quarter).
    ///
    /// A finished game's line ends on exactly 1.0 or 0.0 (14782706's last
    /// `aggregate_line` point, at `completed_at`): that is the result, beside a
    /// hero reading "Jaguars Win", and prints "100%" / "0%". A live 1.0 keeps
    /// the guard, because the live hero guards it.
    static func printedLabels(home: Double, away: Double?,
                              gameFinished: Bool = false) -> (home: String, away: String?) {
        let printed = printedPercents(home: home, away: away)
        if gameFinished, home == 0 || home == 1 {
            return ("\(printed.home)%", printed.away.map { "\($0)%" })
        }
        return (formatProbability(home, renderedPercent: printed.home),
                away.map { formatProbability($0, renderedPercent: printed.away) })
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
    /// #925 — when each of period / clock / score above was OBSERVED. On a
    /// point whose field was carried forward from an older row this is that
    /// row's time; the matching `*Approx` says the carry is a minute or more
    /// old. One date per field, never one shared date: a clock-only row
    /// refreshes the clock's age and nothing else (codex 2026-09-23). All
    /// default so every existing construction site (the resting "last point"
    /// in `EventDetailView`) is an exact observation, which is what it is.
    var periodObservedAt: Date? = nil
    var clockObservedAt: Date? = nil
    var scoreObservedAt: Date? = nil
    var periodApprox: Bool = false
    var clockApprox: Bool = false
    var scoreApprox: Bool = false

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

    /// Which halves of the badge `liveStatusText` actually printed. Decided
    /// over what is RENDERED, not what the point carries: when ESPN's period
    /// detail already spells the clock the standalone clock is dropped, and a
    /// clock the reader cannot see must not date, or mark, the badge.
    private var renderedBadgeParts: (period: String, clock: String) {
        let full = PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""
        let periodOnly = PeriodLabel.liveStatusText(period: period, gameClock: nil) ?? ""
        let clockOnly = PeriodLabel.liveStatusText(period: nil, gameClock: clock) ?? ""
        if !periodOnly.isEmpty, !clockOnly.isEmpty, full == "\(periodOnly) \(clockOnly)" {
            return (periodOnly, clockOnly)
        }
        if !clockOnly.isEmpty, full == clockOnly { return ("", clockOnly) }
        if !periodOnly.isEmpty, full == periodOnly { return (periodOnly, "") }
        return (full, "")
    }

    private var periodIsCarried: Bool { periodApprox && !renderedBadgeParts.period.isEmpty }
    private var clockIsCarried: Bool { clockApprox && !renderedBadgeParts.clock.isEmpty }

    /// "as of 7:41 PM" — the OLDEST observation among the components actually
    /// on screen that were carried here, printed only when at least one of
    /// them is a minute or more older than the point. Oldest, not per-field:
    /// it is the one choice that can never make a stale readout look fresher
    /// than it is, and the `~` on the badge says which half is old. The score
    /// joins the set only when the badge has nothing else — then the score IS
    /// the readout being dated. Nil when everything shown is fresh, or when a
    /// carried field has no date to name (the mark stays; no time is invented).
    ///
    /// Reader copy, not implementation: it names a time, not a mechanism.
    var stateAsOfDisplay: String? {
        var carried: [Date] = []
        if periodIsCarried, let d = periodObservedAt { carried.append(d) }
        if clockIsCarried, let d = clockObservedAt { carried.append(d) }
        let parts = renderedBadgeParts
        if parts.period.isEmpty, parts.clock.isEmpty, hasScore, scoreApprox, let d = scoreObservedAt {
            carried.append(d)
        }
        guard let oldest = carried.min() else { return nil }
        return "as of \(Self.asOfText(oldest, pointDate: timestamp.asDate))"
    }

    /// One clock format for both lines, so "7:44 PM" and "as of 7:41 PM" read as
    /// the same kind of time.
    static func clockText(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    /// `wallClockDisplay` with its weekday ("Sun 6:06 PM"), for the floating card.
    var datedWallClockDisplay: String {
        guard let date = timestamp.asDate else { return "" }
        return date.formatted(.dateTime.weekday(.abbreviated).hour().minute())
    }

    /// The `as of` time, carrying a day only when it needs one.
    ///
    /// A bare clock is right for the ordinary case — a state carried a few
    /// minutes inside the point's own day — and wrong the moment the two fall
    /// on different days, because `date: .omitted` renders 11:58 PM yesterday
    /// and 11:58 PM today identically. A game still going after local midnight
    /// then prints `as of 11:58 PM` directly beneath a `12:30 AM` point, and a
    /// state THIRTY-TWO MINUTES old reads as twelve hours in the FUTURE: the
    /// two lines sit one above the other in the badge, so the reader compares
    /// them whether or not we meant them to be compared.
    ///
    /// Codex found this same defect in the web half on 2026-09-23 —
    /// `carriedStateDisclosure` compared formatted `h:mm a` strings, so
    /// yesterday-20:00 and today-20:00 disclosed nothing — and corrected it
    /// there (CODEX-0007). This is the native counterpart; the native half
    /// reached it by a different route (`date: .omitted`) and had no test
    /// crossing a day boundary, because every `as of` expectation in the 925
    /// suite was built by calling `clockText`, the code under test.
    ///
    /// The date style matches the chart's own multi-day axis label
    /// (`OddsChartView.labelStyle` / `.calendarDay`), so a reader who scrubs
    /// across midnight sees the same vocabulary on the axis and in the badge.
    static func asOfText(_ observed: Date, pointDate: Date?,
                         calendar: Calendar = .current) -> String {
        guard let pointDate, !calendar.isDate(observed, inSameDayAs: pointDate) else {
            return clockText(observed)
        }
        return observed.formatted(.dateTime.month(.abbreviated).day().hour().minute())
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
        let parts = renderedBadgeParts
        // #925 — a carried half wears the same `~` the web's badge does, and
        // the `~` marks the ODD ONE OUT so the badge never carries two: the
        // clock takes it when the clock is carried ("Q4 ~1:09"); the period
        // takes it only when it is the stale half of a badge whose clock is
        // fresh, or when it is alone ("~Top 8th", baseball). One glyph, one
        // meaning — "not observed at this instant". The exact time it WAS
        // observed is `stateAsOfDisplay`.
        //
        // The join itself stays `liveStatusText`'s (#4880 guard,
        // `periodLabelSingleSource.test.ts`): the mark is placed INTO the
        // string that rule printed, never by re-joining the pair here.
        var text = PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""
        if clockIsCarried, let clockRange = text.range(of: parts.clock, options: .backwards) {
            text.replaceSubrange(clockRange, with: "~" + parts.clock)
        }
        if periodIsCarried, !clockIsCarried, !text.isEmpty {
            text = "~" + text
        }
        return text
    }
}
