#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import SwiftUI
import WidgetKit

/// Local ActivityKit content. Updates require the phone's foreground owner.
@available(iOS 18.0, *)
struct GameLiveActivity: Widget {
    var body: some WidgetConfiguration {
        GameLiveActivityBase().body.supplementalActivityFamilies([.small, .medium])
    }
}

/// #10864 — a scoreboard first: each side's colour, badge, score and chance, the
/// game's state in one pill, and the time the numbers were observed. Nothing here
/// ticks on its own; every value is what the last update carried.
@available(iOS 17.0, *)
struct GameLiveActivityBase: Widget {
    var body: ActivityConfiguration<GameActivityAttributes> {
        ActivityConfiguration(for: GameActivityAttributes.self) { context in
            if #available(iOS 18.0, *) {
                GameActivityFamilyView(reading: GameActivityReading(context))
            } else {
                GameActivityLockScreenView(reading: GameActivityReading(context))
            }
        } dynamicIsland: { context in
            let reading = GameActivityReading(context)
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    GameActivityExpandedSide(reading: reading, side: .away)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    GameActivityExpandedSide(reading: reading, side: .home)
                }
                DynamicIslandExpandedRegion(.center) {
                    GameActivityStatusPill(reading: reading)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 5) {
                        GameActivityChanceLine(reading: reading)
                        GameActivityFooter(reading: reading)
                    }
                    .padding(.horizontal, 8)
                }
            } compactLeading: {
                GameActivityCompactLeading(reading: reading)
            } compactTrailing: {
                GameActivityCompactTrailing(reading: reading)
            } minimal: {
                GameActivityMinimal(reading: reading)
            }
            .widgetURL(GameContinuation.url(eventID: context.attributes.eventID))
            .keylineTint(reading.keyline)
        }
    }
}

/// Everything the views print, decided once per update so the Lock Screen, the
/// Dynamic Island and the Smart Stack never disagree about a game.
@available(iOS 17.0, *)
private struct GameActivityReading {
    enum Side { case away, home }

    let snapshot: GameActivitySnapshot
    let eventID: Int
    /// The update names this activity's game; any other game shows nothing.
    let matches: Bool
    let isStale: Bool

    init(_ context: ActivityViewContext<GameActivityAttributes>) {
        snapshot = context.state.snapshot
        eventID = context.attributes.eventID
        matches = context.state.snapshot.eventID == context.attributes.eventID
        isStale = context.isStale
    }

    /// #199 — the page headline's three phases (`EventSportHeadlines12472`):
    /// before `Chance`, during `Score · Now`, after `Final` with the winner ticked.
    enum Phase { case before, during, after }
    var phase: Phase {
        if snapshot.lifecycle == .scheduled { return .before }
        if snapshot.isFinal { return .after }
        return .during
    }
    /// The page's word for the chance column in this phase.
    var chanceHeader: String { phase == .before ? "Chance" : "Now" }
    /// The page's green tick, only on the side the server's verdict names (a
    /// draw ticks both, as the page does). Never inferred from the scores.
    func ticked(_ side: Side) -> Bool {
        guard matches, snapshot.isFinal, let result = snapshot.result else { return false }
        switch result {
        case .draw: return true
        case .home: return side == .home
        case .away: return side == .away
        }
    }

    var showsForecast: Bool {
        matches && (snapshot.lifecycle == .live || snapshot.lifecycle == .scheduled)
    }
    var isLive: Bool { matches && !isStale && snapshot.lifecycle == .live }

    func name(_ side: Side) -> String { side == .home ? snapshot.homeTeam : snapshot.awayTeam }
    /// #199 — the short name the page headline prints ("Patriots"), by its rule.
    func shortName(_ side: Side) -> String {
        let pair = TeamShortName.shortPair(away: snapshot.awayTeam, home: snapshot.homeTeam, sportKey: snapshot.sport)
        return side == .home ? pair.home : pair.away
    }
    /// Direction 209 — after a game, each side's pregame chance ("42%"), as the
    /// page's Pregame column prints it. Nothing before or during a game.
    func pregameText(_ side: Side) -> String? {
        guard phase == .after, let away = snapshot.pregameAwayPercent,
              let home = snapshot.pregameHomePercent else { return nil }
        return "\(side == .home ? home : away)%"
    }
    var hasPregame: Bool { pregameText(.home) != nil }
    /// The side the server's verdict names as the winner (no draw), else none.
    var winner: Side? {
        guard matches, snapshot.isFinal else { return nil }
        switch snapshot.result {
        case .home: return .home
        case .away: return .away
        default: return nil
        }
    }
    /// The served badge, else the app's own badge rule for the name.
    func badge(_ side: Side) -> String {
        (side == .home ? snapshot.homeAbbreviation : snapshot.awayAbbreviation)
            ?? TeamShortName.abbreviation(name(side))
    }
    func score(_ side: Side) -> Int? {
        guard matches else { return nil }
        return side == .home ? snapshot.homeScore : snapshot.awayScore
    }
    func scoreText(_ side: Side) -> String { score(side).map(String.init) ?? "–" }

    /// Both sides' chances, or neither: one number in a two-row column would read
    /// as a duel the game is not (a priced draw leaves the away side empty).
    var pair: (away: Int, home: Int)? {
        guard showsForecast, let home = snapshot.homeRenderedPercent,
              let away = snapshot.awayRenderedPercent else { return nil }
        return (away, home)
    }
    func percent(_ side: Side) -> Int? { pair.map { side == .home ? $0.home : $0.away } }
    /// A priced draw's one honest number: the home side's chance, always named.
    var singleChance: Int? { pair == nil && showsForecast ? snapshot.homeRenderedPercent : nil }
    var singleChanceLabel: String? { singleChance == nil ? nil : snapshot.probabilityLabel }
    func percentText(_ value: Int) -> String {
        (Double(value) / 100).formatted(.percent.precision(.fractionLength(0)))
    }
    /// #199 — the page headline's "Now" for a side: its tenths (66.2%) when the
    /// reading carries them, else the whole percent the headline itself falls
    /// back to. One wording for the page, the Lock Screen and the island.
    func nowText(_ side: Side) -> String? {
        guard let value = percent(side) else { return nil }
        return snapshot.headlineNowText(home: side == .home) ?? percentText(value)
    }
    /// The side the compact views lead with: the favourite of a two-way game, else home.
    var lead: Side {
        guard let pair else { return .home }
        return pair.away > pair.home ? .away : .home
    }
    /// The other side from `lead`.
    var trail: Side { lead == .home ? .away : .home }
    /// After a final the lower score steps back, as on a scoreboard. Never a
    /// checkmark: scores alone do not settle a shootout or an aggregate tie.
    var lowerScoredSide: Side? {
        guard matches, snapshot.isFinal, let away = snapshot.awayScore,
              let home = snapshot.homeScore, away != home else { return nil }
        return away < home ? .away : .home
    }
    /// #10864 — the side the server's verdict says lost: it steps back even on a
    /// level score settled another way. Without a verdict, the scoreboard rule.
    var losingSide: Side? {
        guard matches, snapshot.isFinal else { return nil }
        switch snapshot.result {
        case .home: return .away
        case .away: return .home
        case .draw: return nil
        case nil: return lowerScoredSide
        }
    }
    func steppedBack(_ side: Side) -> Bool { isStale || losingSide == side }
    /// #10864 — "Won", "Lost" or "Draw" beside each final score, only when the
    /// server stated the verdict. The saved widget prints the same words.
    func verdict(_ side: Side) -> String? {
        guard matches, snapshot.isFinal, let result = snapshot.result else { return nil }
        switch result {
        case .draw: return "Draw"
        case .home: return side == .home ? "Won" : "Lost"
        case .away: return side == .away ? "Won" : "Lost"
        }
    }

    /// #199 / ruling 197 — the headline's own two colours
    /// (`TeamTextContrast.cardColorHexes`, as `EventDetailView.teamColors` calls
    /// it): home keeps its colour, and an away team in the same hue family takes
    /// its second colour, else slate grey. Never a second palette of our own.
    private var headlineHexes: (away: String, home: String) {
        TeamTextContrast.cardColorHexes(awayHex: snapshot.awayColorHex, homeHex: snapshot.homeColorHex,
                                        awaySecondaryHex: snapshot.awaySecondaryColorHex,
                                        checkHueFamily: true)
    }
    /// On a light surface, exactly the headline's colour. On the island's black,
    /// the same colour lifted only when it would vanish (navy on black).
    func color(_ side: Side, onDark: Bool) -> Color {
        let hex = side == .home ? headlineHexes.home : headlineHexes.away
        return onDark ? GameActivityColor.color(hex, onDark: true) : Color(hex: hex)
    }
    /// The split bar's two colours: the headline's pair, which already keeps
    /// two teams apart (rule 197), so no grey of our own.
    func barColors(onDark: Bool) -> (away: Color, home: Color) {
        (color(.away, onDark: onDark), color(.home, onDark: onDark))
    }
    var keyline: Color? { matches ? color(lead, onDark: true) : nil }

    var statusText: String {
        guard matches else { return "UNAVAILABLE" }
        let chip = snapshot.periodLabel.map { " · \($0)" } ?? ""
        switch snapshot.lifecycle {
        case .live: return "LIVE" + chip
        case .suspended: return "PAUSED" + chip
        case .final: return "FINAL"
        case .closed: return "CLOSED"
        case .scheduled: return "UPCOMING"
        case .unknown: return "STATUS UNAVAILABLE"
        }
    }
    var statusSpoken: String {
        guard matches else { return "Game reading unavailable" }
        guard snapshot.lifecycle == .live || snapshot.lifecycle == .suspended,
              let chip = snapshot.periodLabel else { return snapshot.statusLabel }
        return "\(snapshot.statusLabel), \(PeriodLabel.spoken(chip))"
    }
    var pillBackground: Color {
        guard matches, !isStale else { return Color.primary.opacity(0.12) }
        switch snapshot.lifecycle {
        case .live: return Color(red: 0.843, green: 0, blue: 0.082)  // #D70015, white text ≥ 4.5:1
        case .suspended: return .orange
        default: return Color.primary.opacity(0.12)
        }
    }
    var pillForeground: Color {
        guard matches, !isStale else { return .primary }
        switch snapshot.lifecycle {
        case .live: return .white
        case .suspended: return .black
        default: return .primary
        }
    }

    /// When the numbers were observed, never when they arrived: one time when
    /// both land in the same minute. A stale reading gives its OLDEST time and
    /// the way to refresh it (a tap opens the game, which sends a new reading).
    /// Nil after a final: a settled score carries no time beside it (Fable's
    /// 6:36 PM look on #12768), on the Lock Screen and the expanded island.
    var footer: Text? {
        guard matches else { return Text("Open Bain Luck for current details") }
        if snapshot.isFinal { return nil }
        if snapshot.lifecycle == .closed { return Text("Result unverified · tap for details") }
        let score = snapshot.scoreObservedAt
        let chance = pair != nil || singleChanceLabel != nil ? snapshot.probabilityObservedAt : nil
        if isStale {
            guard let oldest = [score, chance].compactMap({ $0 }).min() else { return Text("Tap to refresh") }
            return Text("As of \(oldest, style: .time) · tap to refresh")
        }
        switch (score, chance) {
        case let (score?, chance?) where Calendar.current.isDate(score, equalTo: chance, toGranularity: .minute):
            return Text("As of \(max(score, chance), style: .time)")
        case let (score?, chance?):
            return Text("Score \(score, style: .time) · Chance \(chance, style: .time)")
        case let (score?, nil):
            return Text("Score as of \(score, style: .time)")
        case let (nil, chance?):
            return Text("Chance as of \(chance, style: .time)")
        case (nil, nil):
            return Text("Observation time unavailable")
        }
    }

    func rowSpoken(_ side: Side) -> String {
        var parts = [name(side)]
        if phase != .before { parts.append(score(side).map { "\($0)" } ?? "score unavailable") }
        if let now = nowText(side) { parts.append("\(now) chance to win") }
        if let pregame = pregameText(side) { parts.append("\(pregame) chance before the game") }
        if let verdict = verdict(side) { parts.append(verdict) }
        return parts.joined(separator: ", ")
    }
    var chanceSpoken: String {
        guard let pair else { return singleChanceLabel ?? "Win probability unavailable" }
        return "\(name(.away)) \(nowText(.away) ?? percentText(pair.away)), \(name(.home)) \(nowText(.home) ?? percentText(pair.home)) chance to win"
    }
    /// The Dynamic Island's compact and minimal views speak the whole reading.
    var compactSpoken: String {
        guard matches else { return "Game reading unavailable" }
        var parts = [statusSpoken, "\(rowSpoken(.away)). \(rowSpoken(.home))"]
        if let single = singleChanceLabel { parts.append(single) }
        parts.append(Self.ageSpoken("Score", age: snapshot.scoreAge(at: Date())))
        if pair != nil || singleChanceLabel != nil {
            parts.append(Self.ageSpoken("Probability", age: snapshot.probabilityAge(at: Date())))
        }
        parts.append(isStale ? "Earlier reading. Open on iPhone to refresh."
                             : "Reported reading. Open on iPhone for current details.")
        return parts.joined(separator: ". ")
    }

    private static func ageSpoken(_ name: String, age: TimeInterval?) -> String {
        guard let age, age.isFinite, age >= 0 else { return "\(name) observation time unavailable" }
        if age / 60 >= Double(Int.max) { return "\(name) observed a long time ago" }
        return "\(name) observed \(Int(age / 60)) minutes ago"
    }
}

/// A served team colour, lifted when it would vanish on a dark surface (navy on
/// the Dynamic Island's black) and deepened when it would vanish on a light one.
@available(iOS 17.0, *)
private enum GameActivityColor {
    typealias RGB = (r: Double, g: Double, b: Double)

    static func rgb(_ hex: String?) -> RGB? {
        guard let hex, hex.count == 7, let value = UInt32(hex.dropFirst(), radix: 16) else { return nil }
        return (Double((value >> 16) & 0xFF) / 255, Double((value >> 8) & 0xFF) / 255, Double(value & 0xFF) / 255)
    }
    static func color(_ hex: String?, onDark: Bool) -> Color {
        guard let c = rgb(hex) else { return .gray }
        let light = luminance(c)
        if onDark, light < 0.06 { return mix(c, toward: 1, by: 0.45) }
        if !onDark, light > 0.8 { return mix(c, toward: 0, by: 0.35) }
        return Color(red: c.r, green: c.g, blue: c.b)
    }
    private static func mix(_ c: RGB, toward target: Double, by amount: Double) -> Color {
        Color(red: c.r + (target - c.r) * amount, green: c.g + (target - c.g) * amount,
              blue: c.b + (target - c.b) * amount)
    }
    private static func luminance(_ c: RGB) -> Double {
        func linear(_ x: Double) -> Double { x <= 0.03928 ? x / 12.92 : pow((x + 0.055) / 1.055, 2.4) }
        return 0.2126 * linear(c.r) + 0.7152 * linear(c.g) + 0.0722 * linear(c.b)
    }
}

@available(iOS 18.0, *)
private struct GameActivityFamilyView: View {
    @Environment(\.activityFamily) private var family
    let reading: GameActivityReading

    var body: some View {
        if family == .small {
            GameActivitySmallView(reading: reading)
        } else {
            GameActivityLockScreenView(reading: reading)
        }
    }
}

/// The Lock Screen and the banner: the full scoreboard.
@available(iOS 17.0, *)
private struct GameActivityLockScreenView: View {
    @Environment(\.colorScheme) private var scheme
    let reading: GameActivityReading

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // The state and the time the numbers were observed share one row,
            // so the card keeps room for the column labels inside the Lock
            // Screen's 160-point height.
            HStack(alignment: .center, spacing: 8) {
                GameActivityStatusPill(reading: reading)
                Spacer(minLength: 4)
                GameActivityFooter(reading: reading, alignment: .trailing)
                    .layoutPriority(-1)
            }
            if reading.matches {
                VStack(spacing: 4) {
                    if reading.matches && (reading.pair != nil || reading.phase == .after) {
                        GameActivityColumnLabels(reading: reading)
                    }
                    GameActivityTeamRow(reading: reading, side: .away)
                    GameActivityTeamRow(reading: reading, side: .home)
                }
                if let pair = reading.pair {
                    let colors = reading.barColors(onDark: scheme == .dark)
                    GameActivitySplitBar(away: colors.away, home: colors.home,
                                         awayShare: Double(pair.away) / 100)
                } else if let single = reading.singleChanceLabel {
                    Text(single)
                        .font(.subheadline.weight(.semibold))
                        .monospacedDigit()
                }
            } else {
                Text("Game reading unavailable").font(.headline)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetURL(GameContinuation.url(eventID: reading.eventID))
    }
}

@available(iOS 17.0, *)
private struct GameActivityTeamRow: View {
    @Environment(\.colorScheme) private var scheme
    let reading: GameActivityReading
    let side: GameActivityReading.Side

    var body: some View {
        HStack(spacing: 8) {
            // #199 — the page's short name, once ("Patriots"); the islands keep the badge.
            Text(reading.shortName(side))
                .font(.headline.weight(.bold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 6)
            if let pregame = reading.pregameText(side) {
                // Direction 209 — the page's after-game Pregame column, quiet.
                Text(pregame)
                    .font(HeadlineStyleTable199.secondNumbers(.lockScreen))
                    .foregroundStyle(.secondary)
                    .frame(minWidth: GameActivityColumnLabels.pregameWidth, alignment: .trailing)
            }
            if reading.phase != .before {
                Text(reading.scoreText(side))
                    .font(HeadlineStyleTable199.secondNumbers(.lockScreen, prominent: true))
                    .foregroundStyle(reading.steppedBack(side) ? .secondary : .primary)
                    .frame(minWidth: GameActivityColumnLabels.scoreWidth, alignment: .trailing)
            }
            if let now = reading.nowText(side) {
                // #199 / 200-B — "Now" is the largest thing, in the team's colour.
                Text(now)
                    .font(HeadlineStyleTable199.now(.lockScreen))
                    .foregroundStyle(reading.isStale ? AnyShapeStyle(.secondary)
                                                     : AnyShapeStyle(reading.color(side, onDark: scheme == .dark)))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .frame(minWidth: GameActivityColumnLabels.nowWidth, alignment: .trailing)
            } else if reading.phase == .after {
                // The page's after phase: the winner ticked in green, no words.
                Image(systemName: "checkmark")
                    .font(.subheadline.weight(.heavy))
                    .foregroundStyle(HeadlineStyleTable199.winnerTickInk)
                    .opacity(reading.ticked(side) ? 1 : 0)
                    .frame(width: GameActivityColumnLabels.tickWidth, alignment: .trailing)
            }
        }
        .padding(.leading, 12)
        .frame(maxWidth: .infinity, minHeight: 24, alignment: .leading)
        .overlay(alignment: .leading) {
            // Hidden from VoiceOver: the rendered activity framed the row's
            // element by this 4-point bar, so the focus box missed the row.
            Capsule()
                .fill(reading.color(side, onDark: scheme == .dark))
                .frame(width: 4, height: 24)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.rowSpoken(side))
    }
}

/// #199 — the page headline's column labels, in its words and case: "Score"
/// and "Now" (`EventSportHeadlines12472.LiveColumnHeaders`). The Lock Screen has
/// no room for "Proj.", so that column is left out rather than renamed.
@available(iOS 17.0, *)
private struct GameActivityColumnLabels: View {
    static let scoreWidth: CGFloat = 40
    static let nowWidth: CGFloat = 78
    static let tickWidth: CGFloat = 18
    static let pregameWidth: CGFloat = 64
    let reading: GameActivityReading

    var body: some View {
        HStack(spacing: 8) {
            Spacer(minLength: 0)
            switch reading.phase {
            case .before:
                Text("Chance").frame(width: Self.nowWidth, alignment: .trailing)
            case .during:
                Text("Score").frame(width: Self.scoreWidth, alignment: .trailing)
                Text("Now").frame(width: Self.nowWidth, alignment: .trailing)
            case .after:
                if reading.hasPregame {
                    Text("Pregame").frame(width: Self.pregameWidth, alignment: .trailing)
                }
                Text("Final").frame(width: Self.scoreWidth, alignment: .trailing)
                Color.clear.frame(width: Self.tickWidth, height: 1)
            }
        }
        .font(HeadlineStyleTable199.headers(.lockScreen))
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }
}

@available(iOS 17.0, *)
private struct GameActivityStatusPill: View {
    let reading: GameActivityReading

    var body: some View {
        HStack(spacing: 5) {
            if reading.isLive {
                Circle().fill(Color.white).frame(width: 6, height: 6)
            }
            Text(reading.statusText)
                .font(.caption2.weight(.bold))
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .foregroundStyle(reading.pillForeground)
        .background(reading.pillBackground, in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.statusSpoken)
    }
}

@available(iOS 17.0, *)
private struct GameActivitySplitBar: View {
    let away: Color
    let home: Color
    let awayShare: Double

    var body: some View {
        GeometryReader { geometry in
            HStack(spacing: 2) {
                Capsule().fill(away)
                    .frame(width: max(3, (geometry.size.width - 2) * min(max(awayShare, 0), 1)))
                Capsule().fill(home)
            }
        }
        .frame(height: 5)
        .accessibilityHidden(true)
    }
}

@available(iOS 17.0, *)
private struct GameActivityFooter: View {
    let reading: GameActivityReading
    var alignment: Alignment = .leading

    var body: some View {
        if let footer = reading.footer {
            footer
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
                .frame(maxWidth: .infinity, alignment: alignment)
        }
    }
}

/// The expanded Dynamic Island's sides: badge over a big score.
@available(iOS 17.0, *)
private struct GameActivityExpandedSide: View {
    let reading: GameActivityReading
    let side: GameActivityReading.Side

    var body: some View {
        VStack(alignment: side == .away ? .leading : .trailing, spacing: 0) {
            HStack(spacing: 5) {
                if side == .away { dot }
                Text(reading.badge(side)).font(.subheadline.weight(.heavy))
                if side == .home { dot }
            }
            // #199 — the score is a second number: smaller than Now below it.
            // Before the game there is no score to show.
            Text(reading.phase == .before ? " " : reading.scoreText(side))
                .font(HeadlineStyleTable199.secondNumbers(.island, prominent: true))
                .foregroundStyle(reading.steppedBack(side) ? .secondary : .primary)
        }
        .frame(maxWidth: .infinity, alignment: side == .away ? .leading : .trailing)
        .padding(.horizontal, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.rowSpoken(side))
    }

    private var dot: some View {
        Circle().fill(reading.color(side, onDark: true)).frame(width: 8, height: 8)
    }
}

/// The expanded Dynamic Island's chance: both sides on a split bar, or a priced
/// draw's one line. Nothing once the game has no forecast.
@available(iOS 17.0, *)
private struct GameActivityChanceLine: View {
    let reading: GameActivityReading

    var body: some View {
        if let pair = reading.pair {
            let colors = reading.barColors(onDark: true)
            VStack(spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(reading.nowText(.away) ?? reading.percentText(pair.away))
                        .foregroundStyle(reading.color(.away, onDark: true))
                    Spacer(minLength: 8)
                    Text(reading.chanceHeader).font(HeadlineStyleTable199.headers(.island)).foregroundStyle(.secondary)
                    Spacer(minLength: 8)
                    Text(reading.nowText(.home) ?? reading.percentText(pair.home))
                        .foregroundStyle(reading.color(.home, onDark: true))
                }
                .font(HeadlineStyleTable199.now(.island))
                GameActivitySplitBar(away: colors.away, home: colors.home, awayShare: Double(pair.away) / 100)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(reading.chanceSpoken)
        } else if let single = reading.singleChanceLabel {
            Text(single)
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .frame(maxWidth: .infinity, alignment: .leading)
        } else if let awayPregame = reading.pregameText(.away), let homePregame = reading.pregameText(.home) {
            // Direction 209 — after a game, each side's pregame chance under its
            // final score, labelled as the page labels the column.
            HStack(alignment: .firstTextBaseline) {
                Text(awayPregame)
                Spacer(minLength: 8)
                Text("Pregame").font(HeadlineStyleTable199.headers(.island))
                Spacer(minLength: 8)
                Text(homePregame)
            }
            .font(HeadlineStyleTable199.secondNumbers(.island))
            .foregroundStyle(.secondary)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Before the game: \(reading.name(.away)) \(awayPregame), \(reading.name(.home)) \(homePregame)")
        }
    }
}

/// Compact leading: the favourite's colour and badge while there is a chance to
/// show; the away side's score once the game is over.
@available(iOS 17.0, *)
private struct GameActivityCompactLeading: View {
    let reading: GameActivityReading

    var body: some View {
        Group {
            if !reading.matches {
                Text("—")
            } else if let winner = reading.winner, reading.hasPregame,
                      let won = reading.score(winner), let lost = reading.score(winner == .home ? .away : .home) {
                // Direction 209 — the winner and the score, winner's first; its
                // pregame chance follows on the trailing side.
                Text("\(reading.badge(winner)) \(won)–\(lost)")
            } else if reading.snapshot.isTerminal {
                Text("\(reading.badge(.away)) \(reading.scoreText(.away))")
                    .foregroundStyle(reading.lowerScoredSide == .away ? .secondary : .primary)
            } else if let now = reading.nowText(reading.lead) {
                // #199 — the leader and its chance now, in the headline's words.
                HStack(spacing: 4) {
                    Text(reading.badge(reading.lead))
                    Text(now)
                        .foregroundStyle(reading.isStale ? AnyShapeStyle(.secondary)
                                                         : AnyShapeStyle(reading.color(reading.lead, onDark: true)))
                }
            } else {
                HStack(spacing: 4) {
                    Circle().fill(reading.color(reading.lead, onDark: true)).frame(width: 7, height: 7)
                    Text(reading.badge(reading.lead))
                }
            }
        }
        .font(.caption.weight(.heavy))
        .monospacedDigit()
        .lineLimit(1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.compactSpoken)
    }
}

/// Compact trailing: the favourite's chance, or the home side's score once the
/// game is over, so the island reads like a scoreboard across the camera.
@available(iOS 17.0, *)
private struct GameActivityCompactTrailing: View {
    let reading: GameActivityReading

    var body: some View {
        Group {
            if !reading.matches {
                Text("—")
            } else if let winner = reading.winner, reading.hasPregame,
                      reading.score(.home) != nil, reading.score(.away) != nil,
                      let pregame = reading.pregameText(winner) {
                Text("was \(pregame)")
                    .foregroundStyle(.secondary)
            } else if reading.snapshot.isTerminal {
                Text("\(reading.scoreText(.home)) \(reading.badge(.home))")
                    .foregroundStyle(reading.lowerScoredSide == .home ? .secondary : .primary)
            } else if reading.phase == .before, let now = reading.nowText(reading.trail) {
                // #199 — before kickoff there is no score: the other side's chance,
                // in its colour, so the island carries the page's pair.
                HStack(spacing: 4) {
                    Text(now)
                        .foregroundStyle(reading.isStale ? AnyShapeStyle(.secondary)
                                                         : AnyShapeStyle(reading.color(reading.trail, onDark: true)))
                    Text(reading.badge(reading.trail))
                }
            } else if reading.pair != nil, let lead = reading.score(reading.lead),
                      let trail = reading.score(reading.lead == .home ? .away : .home) {
                // #199 — the score, the leader's first, beside its badge on the left.
                HStack(spacing: 2) {
                    if reading.isStale { Image(systemName: "clock.arrow.circlepath").imageScale(.small) }
                    Text("\(lead)–\(trail)")
                }
                .foregroundStyle(reading.isStale ? .secondary : .primary)
            } else if let value = reading.percent(reading.lead) ?? reading.singleChance {
                if reading.isStale {
                    // The last chance stays readable, dimmed behind a refresh
                    // glyph: the word "Stale" alone told the reader nothing.
                    HStack(spacing: 2) {
                        Image(systemName: "clock.arrow.circlepath").imageScale(.small)
                        Text(reading.percentText(value))
                    }
                    .foregroundStyle(.secondary)
                } else {
                    Text(reading.percentText(value))
                }
            } else if reading.snapshot.lifecycle == .suspended {
                Text("Paused")
            } else if reading.isStale {
                Image(systemName: "clock.arrow.circlepath").foregroundStyle(.secondary)
            } else {
                Text("—")
            }
        }
        .font(.caption.weight(.heavy))
        .monospacedDigit()
        .lineLimit(1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.compactSpoken)
    }
}

@available(iOS 17.0, *)
private struct GameActivityMinimal: View {
    let reading: GameActivityReading

    var body: some View {
        Group {
            if !reading.matches {
                Text("—")
            } else if reading.snapshot.isFinal {
                Image(systemName: "flag.checkered")
            } else if reading.snapshot.isTerminal {
                Image(systemName: "questionmark")
            } else if let now = reading.nowText(reading.lead) {
                Text(now)
                    .minimumScaleFactor(0.6)
                    .foregroundStyle(reading.isStale ? AnyShapeStyle(.secondary)
                                                     : AnyShapeStyle(reading.color(reading.lead, onDark: true)))
            } else if let value = reading.percent(reading.lead) ?? reading.singleChance {
                Text(reading.percentText(value))
                    .foregroundStyle(reading.isStale ? .secondary : .primary)
            } else if reading.snapshot.lifecycle == .suspended {
                Image(systemName: "pause.fill")
            } else if reading.isStale {
                Image(systemName: "clock.arrow.circlepath").foregroundStyle(.secondary)
            } else {
                Text("—")
            }
        }
        .font(.caption2.weight(.heavy))
        .monospacedDigit()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.compactSpoken)
    }
}

/// The Smart Stack on Apple Watch and CarPlay: state, the favourite's chance and
/// both scores.
@available(iOS 17.0, *)
private struct GameActivitySmallView: View {
    let reading: GameActivityReading

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                GameActivityStatusPill(reading: reading)
                Spacer(minLength: 2)
                if let value = reading.percent(reading.lead) {
                    Text("\(reading.badge(reading.lead)) \(reading.percentText(value))")
                        .font(.caption2.weight(.semibold))
                        .monospacedDigit()
                        .lineLimit(1)
                }
            }
            if reading.matches {
                HStack {
                    side(.away)
                    Spacer(minLength: 4)
                    side(.home)
                }
            } else {
                Text("Game reading unavailable").font(.caption)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetURL(GameContinuation.url(eventID: reading.eventID))
    }

    private func side(_ side: GameActivityReading.Side) -> some View {
        HStack(spacing: 4) {
            Circle().fill(reading.color(side, onDark: true)).frame(width: 6, height: 6)
            Text(reading.badge(side)).font(.caption.weight(.heavy))
            Text(reading.scoreText(side))
                .font(.headline.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(reading.steppedBack(side) ? .secondary : .primary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.rowSpoken(side))
    }
}
#endif
