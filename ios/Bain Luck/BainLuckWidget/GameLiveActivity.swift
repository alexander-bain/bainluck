#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import SwiftUI
import WidgetKit
#if DEBUG && canImport(Bain_Luck) && !BAINLUCK_WIDGET_EXTENSION
@testable import Bain_Luck
#endif

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
struct GameActivityReading {
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

    init(snapshot: GameActivitySnapshot, eventID: Int, isStale: Bool = false) {
        self.snapshot = snapshot
        self.eventID = eventID
        self.matches = snapshot.eventID == eventID
        self.isStale = isStale
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
            && snapshot.probabilityObservedAt != nil
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
        if side == .home {
            return ExternalSurfaceProbabilityFormat.openWholePercent(
                home,
                subOne: snapshot.pregameHomeSubOne == true,
                aboveNinetyNine: snapshot.pregameHomeAboveNinetyNine == true
            )
        }
        return ExternalSurfaceProbabilityFormat.openWholePercent(
            away,
            subOne: snapshot.pregameAwaySubOne == true,
            aboveNinetyNine: snapshot.pregameAwayAboveNinetyNine == true
        )
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
    /// The team's crest, fetched by the app while the game page was open
    /// (`GameActivityCrests`); nil draws today's short name or badge.
    func crest(_ side: Side) -> UIImage? {
        guard matches else { return nil }
        return GameActivityCrests.image(eventID: eventID, home: side == .home)
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

    /// #13000 (Decision 250-A) — omit the Score / Final score column completely when
    /// a live match has no score feed carrying it (`scoreSourceUnavailable == true`
    /// and no scores) or when a finished match has no recorded scores at all (never
    /// print two "–" dashes under "Final").
    var showsScore: Bool {
        guard phase != .before else { return false }
        if snapshot.homeScore == nil && snapshot.awayScore == nil {
            if phase == .during && snapshot.scoreSourceUnavailable == true { return false }
            if phase == .after { return false }
        }
        return true
    }

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
        ExternalSurfaceProbabilityFormat.openWholePercent(value)
            ?? ExternalSurfaceProbabilityFormat.missingProbabilityText
    }
    /// #395 — whole percents across every Live Activity form (Lock Screen,
    /// Dynamic Island Compact/Expanded/Minimal, and Watch Smart Stack):
    /// Live Activities receive 15s backend APNs pushes and committed snapshots,
    /// not a live DNPL stream.
    func nowText(_ side: Side) -> String? {
        guard let value = percent(side) else { return nil }
        if side == .home {
            return ExternalSurfaceProbabilityFormat.openWholePercent(
                value,
                subOne: snapshot.homeSubOne == true,
                aboveNinetyNine: snapshot.homeAboveNinetyNine == true
            )
        }
        return ExternalSurfaceProbabilityFormat.openWholePercent(
            value,
            subOne: snapshot.awaySubOne == true,
            aboveNinetyNine: snapshot.awayAboveNinetyNine == true
        )
    }
    /// #13392 / #395 — Dynamic Island Minimal shares whole-percent formatting
    /// with the rest of `GameLiveActivity`.
    func minimalNowText(_ side: Side) -> String? {
        nowText(side)
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
    /// Clock-preserving compact pill label for narrow Watch Smart Stack slots (#13659):
    /// drops `"LIVE · "` / `"PAUSED · "` while keeping the full game clock intact.
    var compactStatusText: String {
        guard matches else { return "UNAVAILABLE" }
        if (snapshot.lifecycle == .live || snapshot.lifecycle == .suspended),
           let chip = snapshot.periodLabel {
            return chip
        }
        return statusText
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

    /// Separate producer times for score and chance, never merged into a single
    /// timestamp or refresh prompt because the score can be older than the
    /// chance (#12999). Nil after a final: a settled score carries no time
    /// beside it.
    var footer: Text? {
        guard matches else { return Text("Open Bain Luck for current details") }
        if snapshot.isFinal { return nil }
        if snapshot.lifecycle == .closed { return Text("Result unverified") }
        let score = phase == .before ? nil : snapshot.scoreObservedAt
        let chance = pair != nil ? snapshot.probabilityObservedAt : nil
        switch (score, chance) {
        case let (score?, chance?):
            return Text("Score \(score, style: .time) · Chance \(chance, style: .time)")
        case let (score?, nil):
            return Text("Score \(score, style: .time)")
        case let (nil, chance?):
            return Text("Chance \(chance, style: .time)")
        case (nil, nil):
            return nil
        }
    }

    func rowSpoken(_ side: Side) -> String {
        var parts = [name(side)]
        if showsScore { parts.append(score(side).map { "\($0)" } ?? "score unavailable") }
        if let now = nowText(side) { parts.append("\(now) chance to win") }
        if let pregame = pregameText(side) { parts.append("\(pregame) chance before the game") }
        if let verdict = verdict(side) { parts.append(verdict) }
        return parts.joined(separator: ", ")
    }
    var chanceSpoken: String {
        guard let pair else { return singleChanceLabel ?? ExternalSurfaceProbabilityFormat.missingProbabilityText }
        return "\(name(.away)) \(nowText(.away) ?? percentText(pair.away)), \(name(.home)) \(nowText(.home) ?? percentText(pair.home)) chance to win"
    }
    /// The Dynamic Island's compact and minimal views speak the whole reading.
    var compactSpoken: String {
        guard matches else { return "Game reading unavailable" }
        var parts = [statusSpoken, "\(rowSpoken(.away)). \(rowSpoken(.home))"]
        if let single = singleChanceLabel { parts.append(single) }
        if showsScore {
            parts.append(Self.ageSpoken("Score", age: snapshot.scoreAge(at: Date())))
        }
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
enum GameActivityColor {
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
struct GameActivityFamilyView: View {
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

/// Shared scaled typography and column widths for the Lock Screen headline so
/// headers and numbers align at default and larger text without wrapping (#12999).
@available(iOS 17.0, *)
struct GameActivityLockMetrics {
    let nowSize: CGFloat
    let scoreProminentSize: CGFloat
    let scoreRegularSize: CGFloat
    let nameSize: CGFloat
    let headerSize: CGFloat
    let footerSize: CGFloat

    var scoreWidth: CGFloat {
        ceil(48 * (headerSize / HeadlineStyleTable199.headerBaseSize(.lockScreen)))
    }
    var pregameWidth: CGFloat {
        ceil(64 * (headerSize / HeadlineStyleTable199.headerBaseSize(.lockScreen)))
    }
    var nowWidth: CGFloat {
        ceil(78 * (nowSize / HeadlineStyleTable199.nowBaseSize(.lockScreen)))
    }
    var tickWidth: CGFloat { 18 }
}

/// The Lock Screen and the banner: one headline everywhere (#199, #12999).
@available(iOS 17.0, *)
struct GameActivityLockScreenView: View {
    @Environment(\.colorScheme) private var scheme
    @ScaledMetric(relativeTo: .title3) private var rawNowSize: CGFloat = HeadlineStyleTable199.nowBaseSize(.lockScreen)
    @ScaledMetric(relativeTo: .body) private var rawScoreProminentSize: CGFloat = HeadlineStyleTable199.secondNumberBaseSize(.lockScreen, prominent: true)
    @ScaledMetric(relativeTo: .subheadline) private var rawScoreRegularSize: CGFloat = HeadlineStyleTable199.secondNumberBaseSize(.lockScreen, prominent: false)
    @ScaledMetric(relativeTo: .subheadline) private var rawNameSize: CGFloat = HeadlineStyleTable199.nameBaseSize(.lockScreen)
    @ScaledMetric(relativeTo: .caption2) private var rawHeaderSize: CGFloat = HeadlineStyleTable199.headerBaseSize(.lockScreen)
    @ScaledMetric(relativeTo: .caption2) private var rawFooterSize: CGFloat = HeadlineStyleTable199.quietTextBaseSize(.lockScreen)
    let reading: GameActivityReading

    private var metrics: GameActivityLockMetrics {
        GameActivityLockMetrics(
            nowSize: min(rawNowSize, 26),
            scoreProminentSize: min(rawScoreProminentSize, 22),
            scoreRegularSize: min(rawScoreRegularSize, 18),
            nameSize: min(rawNameSize, 18),
            headerSize: min(rawHeaderSize, 14),
            footerSize: min(rawFooterSize, 13)
        )
    }

    var body: some View {
        let m = metrics
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .center, spacing: 8) {
                GameActivityStatusPill(reading: reading)
                Spacer(minLength: 4)
            }
            if reading.matches {
                VStack(spacing: 3) {
                    if reading.showsScore || reading.pair != nil || (reading.phase == .after && reading.hasPregame) {
                        GameActivityColumnLabels(reading: reading, metrics: m)
                    }
                    GameActivityTeamRow(reading: reading, side: .away, metrics: m)
                    GameActivityTeamRow(reading: reading, side: .home, metrics: m)
                }
                if let pair = reading.pair {
                    let colors = reading.barColors(onDark: scheme == .dark)
                    let awayShare = ExternalSurfaceProbabilityFormat.gaugeShare(
                        pair.away,
                        subOne: reading.snapshot.awaySubOne == true,
                        aboveNinetyNine: reading.snapshot.awayAboveNinetyNine == true
                    )
                    GameActivitySplitBar(away: colors.away, home: colors.home, awayShare: awayShare)
                } else if !reading.snapshot.isTerminal && reading.singleChanceLabel == nil {
                    Text(ExternalSurfaceProbabilityFormat.missingProbabilityText)
                        .font(HeadlineStyleTable199.quietText(.lockScreen, scaledSize: m.footerSize))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                GameActivityFooter(reading: reading, alignment: .leading, scaledSize: m.footerSize, allowsWrap: true)
            } else {
                Text("Game reading unavailable").font(.headline)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetURL(GameContinuation.url(eventID: reading.eventID))
    }
}

@available(iOS 17.0, *)
struct GameActivityTeamRow: View {
    @Environment(\.colorScheme) private var scheme
    let reading: GameActivityReading
    let side: GameActivityReading.Side
    let metrics: GameActivityLockMetrics

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            if let crest = reading.crest(side) {
                GameActivityCrest(image: crest, size: 24)
            }
            // #199 / 194-A — the page's short name, once (schools for college, nickname for pro).
            Text(reading.shortName(side))
                .font(HeadlineStyleTable199.names(.lockScreen, isLoser: reading.phase == .after && reading.losingSide == side, scaledSize: metrics.nameSize))
                .foregroundStyle(reading.phase == .after && reading.losingSide == side ? .secondary : .primary)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
            Spacer(minLength: 6)
            if let pregame = reading.pregameText(side) {
                // Direction 209 — the page's after-game Pregame column, quiet.
                Text(pregame)
                    .font(HeadlineStyleTable199.secondNumbers(.lockScreen, prominent: false, scaledSize: metrics.scoreRegularSize))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: metrics.pregameWidth, alignment: .trailing)
            }
            if reading.showsScore {
                let isFinalWinner = reading.phase == .after && reading.losingSide != side
                Text(reading.scoreText(side))
                    .font(HeadlineStyleTable199.secondNumbers(
                        .lockScreen,
                        prominent: isFinalWinner,
                        scaledSize: isFinalWinner ? metrics.scoreProminentSize : metrics.scoreRegularSize
                    ))
                    .foregroundStyle(reading.phase == .after && reading.losingSide == side ? .secondary : .primary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: metrics.scoreWidth, alignment: .trailing)
            }
            if let now = reading.nowText(side) {
                // #199 / 200-B / #12999 — "Now" is the largest thing, always in the team's colour.
                Text(now)
                    .font(HeadlineStyleTable199.now(.lockScreen, scaledSize: metrics.nowSize))
                    .foregroundStyle(reading.color(side, onDark: scheme == .dark))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: metrics.nowWidth, alignment: .trailing)
            } else if reading.phase == .after {
                // The page's after phase: the winner ticked in green, no words.
                Image(systemName: "checkmark")
                    .font(.subheadline.weight(.heavy))
                    .foregroundStyle(HeadlineStyleTable199.winnerTickInk)
                    .opacity(reading.ticked(side) ? 1 : 0)
                    .frame(width: metrics.tickWidth, alignment: .trailing)
            }
        }
        .padding(.leading, 10)
        .frame(maxWidth: .infinity, minHeight: 24, alignment: .leading)
        .overlay(alignment: .leading) {
            // Hidden from VoiceOver: the rendered activity framed the row's
            // element by this 4-point bar, so the focus box missed the row.
            Capsule()
                .fill(reading.color(side, onDark: scheme == .dark))
                .frame(width: 4, height: 22)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.rowSpoken(side))
    }
}

/// #199 — the page headline's column labels, in its words and case: "Score"
/// and "Now" (`EventSportHeadlines12472.LiveColumnHeaders`). Every header stays
/// on one line and never wraps or cuts (#12999).
@available(iOS 17.0, *)
struct GameActivityColumnLabels: View {
    let reading: GameActivityReading
    let metrics: GameActivityLockMetrics

    var body: some View {
        HStack(spacing: 8) {
            Spacer(minLength: 0)
            switch reading.phase {
            case .before:
                Text("Chance")
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: metrics.nowWidth, alignment: .trailing)
            case .during:
                if reading.showsScore {
                    Text("Score")
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: metrics.scoreWidth, alignment: .trailing)
                }
                if reading.pair != nil {
                    Text("Now")
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: metrics.nowWidth, alignment: .trailing)
                }
            case .after:
                if reading.hasPregame {
                    Text("Pregame")
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: metrics.pregameWidth, alignment: .trailing)
                }
                if reading.showsScore {
                    Text("Final")
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .frame(minWidth: metrics.scoreWidth, alignment: .trailing)
                }
                Color.clear.frame(width: metrics.tickWidth, height: 1)
            }
        }
        .font(HeadlineStyleTable199.headers(.lockScreen, scaledSize: metrics.headerSize))
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }
}

@available(iOS 17.0, *)
struct GameActivityStatusPill: View {
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
struct GameActivitySplitBar: View {
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

/// A team crest on a white disc so dark crests read on the Lock Screen's
/// material and the island's black.
struct GameActivityCrest: View {
    let image: UIImage
    let size: CGFloat

    var body: some View {
        Image(uiImage: image)
            .resizable()
            .interpolation(.high)
            .scaledToFit()
            .padding(size * 0.12)
            .frame(width: size, height: size)
            .background(Circle().fill(Color.white))
            .accessibilityHidden(true)
    }
}

/// The compact island's team mark: the crest when the app has it, else the badge.
struct GameActivityCrestOrBadge: View {
    let reading: GameActivityReading
    let side: GameActivityReading.Side

    var body: some View {
        if let crest = reading.crest(side) {
            GameActivityCrest(image: crest, size: 18)
        } else {
            Text(reading.badge(side))
        }
    }
}

@available(iOS 17.0, *)
struct GameActivityFooter: View {
    let reading: GameActivityReading
    var alignment: Alignment = .leading
    var scaledSize: CGFloat? = nil
    var allowsWrap: Bool = false

    var body: some View {
        if let footer = reading.footer {
            footer
                .font(HeadlineStyleTable199.quietText(.lockScreen, monospacedDigits: true, scaledSize: scaledSize))
                .foregroundStyle(.secondary)
                .lineLimit(allowsWrap ? 2 : 1)
                .minimumScaleFactor(allowsWrap ? 1.0 : 0.85)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: alignment)
        }
    }
}

/// The expanded Dynamic Island's sides: badge over score (secondary during play, prominent on final).
@available(iOS 17.0, *)
struct GameActivityExpandedSide: View {
    let reading: GameActivityReading
    let side: GameActivityReading.Side

    var body: some View {
        let isFinalWinner = reading.phase == .after && reading.losingSide != side
        VStack(alignment: side == .away ? .leading : .trailing, spacing: 1) {
            HStack(spacing: 5) {
                if let crest = reading.crest(side) {
                    if side == .home { Text(reading.badge(side)).font(.subheadline.weight(.heavy)).lineLimit(1) }
                    GameActivityCrest(image: crest, size: 22)
                    if side == .away { Text(reading.badge(side)).font(.subheadline.weight(.heavy)).lineLimit(1) }
                } else {
                    if side == .away { dot }
                    Text(reading.badge(side)).font(.subheadline.weight(.heavy)).lineLimit(1)
                    if side == .home { dot }
                }
            }
            // #199 / #12999 — live score is secondary (smaller than Now below it); final winner leads.
            // #13000 (250-A) — omit score line completely when no score feed carries this live match.
            if reading.showsScore {
                Text(reading.scoreText(side))
                    .font(HeadlineStyleTable199.secondNumbers(.island, prominent: isFinalWinner))
                    .foregroundStyle(reading.phase == .after && reading.losingSide == side ? .secondary : .primary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            } else if reading.phase == .after, let verdict = reading.verdict(side) {
                Text(verdict)
                    .font(.caption.weight(reading.ticked(side) ? .bold : .medium))
                    .foregroundStyle(reading.ticked(side) ? Color.green : .secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
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

/// The expanded Dynamic Island's chance: both sides in team colour on a split bar.
/// After a game, each side's pregame chance under its final score (direction 209).
@available(iOS 17.0, *)
struct GameActivityChanceLine: View {
    let reading: GameActivityReading

    var body: some View {
        if let pair = reading.pair {
            let colors = reading.barColors(onDark: true)
            VStack(spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(reading.nowText(.away) ?? reading.percentText(pair.away))
                        .foregroundStyle(reading.color(.away, onDark: true))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Spacer(minLength: 8)
                    Text(reading.chanceHeader)
                        .font(HeadlineStyleTable199.headers(.island))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Spacer(minLength: 8)
                    Text(reading.nowText(.home) ?? reading.percentText(pair.home))
                        .foregroundStyle(reading.color(.home, onDark: true))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
                .font(HeadlineStyleTable199.now(.island))
                let awayShare = ExternalSurfaceProbabilityFormat.gaugeShare(
                    pair.away,
                    subOne: reading.snapshot.awaySubOne == true,
                    aboveNinetyNine: reading.snapshot.awayAboveNinetyNine == true
                )
                GameActivitySplitBar(away: colors.away, home: colors.home, awayShare: awayShare)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(reading.chanceSpoken)
        } else if let awayPregame = reading.pregameText(.away), let homePregame = reading.pregameText(.home) {
            // Direction 209 — after a game, each side's pregame chance under its
            // final score, labelled as the page labels the column.
            HStack(alignment: .firstTextBaseline) {
                Text(awayPregame)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                Spacer(minLength: 8)
                Text("Pregame")
                    .font(HeadlineStyleTable199.headers(.island))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                Spacer(minLength: 8)
                Text(homePregame)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .font(HeadlineStyleTable199.secondNumbers(.island))
            .foregroundStyle(.secondary)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Before the game: \(reading.name(.away)) \(awayPregame), \(reading.name(.home)) \(homePregame)")
        } else if !reading.snapshot.isTerminal && reading.singleChanceLabel == nil {
            Text(ExternalSurfaceProbabilityFormat.missingProbabilityText)
                .font(HeadlineStyleTable199.quietText(.island))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(reading.chanceSpoken)
        }
    }
}

/// Compact leading: the favourite's colour and badge while there is a chance to
/// show; the away side's score once the game is over.
@available(iOS 17.0, *)
struct GameActivityCompactLeading: View {
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
            } else if reading.snapshot.isTerminal && !reading.showsScore {
                // #13000 (250-A) — scoreless final: never print "BOY –". Show winner + tick or "Final".
                if let winner = reading.winner {
                    HStack(spacing: 3) {
                        GameActivityCrestOrBadge(reading: reading, side: winner)
                        Image(systemName: "checkmark")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.green)
                    }
                } else {
                    Text("Final")
                }
            } else if reading.snapshot.isTerminal {
                Text("\(reading.badge(.away)) \(reading.scoreText(.away))")
                    .foregroundStyle(reading.lowerScoredSide == .away ? .secondary : .primary)
            } else if let now = reading.nowText(reading.lead) {
                // #199 / #12999 — the leader and its chance now, always in the team's colour.
                HStack(spacing: 4) {
                    GameActivityCrestOrBadge(reading: reading, side: reading.lead)
                    Text(now)
                        .foregroundStyle(reading.color(reading.lead, onDark: true))
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
        .minimumScaleFactor(0.75)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.compactSpoken)
    }
}

/// Compact trailing: the live score, a chance before kickoff, or the home
/// side's score once the game is over.
@available(iOS 17.0, *)
struct GameActivityCompactTrailing: View {
    let reading: GameActivityReading

    var body: some View {
        Group {
            if !reading.matches {
                Text("—")
            } else if let winner = reading.winner, reading.hasPregame,
                      reading.score(.home) != nil, reading.score(.away) != nil,
                      let pregame = reading.pregameText(winner) {
                Text("Pregame \(pregame)")
                    .foregroundStyle(.secondary)
            } else if reading.snapshot.isTerminal && !reading.showsScore {
                // #13000 (250-A) — scoreless final: never print "– OLI". Show pregame chance or "Final".
                if let winner = reading.winner, reading.hasPregame,
                   let pregame = reading.pregameText(winner) {
                    Text("Pregame \(pregame)")
                        .foregroundStyle(.secondary)
                } else {
                    Text("Final")
                        .foregroundStyle(.secondary)
                }
            } else if reading.snapshot.isTerminal {
                Text("\(reading.scoreText(.home)) \(reading.badge(.home))")
                    .foregroundStyle(reading.lowerScoredSide == .home ? .secondary : .primary)
            } else if !reading.showsScore, let now = reading.nowText(reading.trail) {
                // #199 / #13000 (250-A) — before kickoff or when no score feed carries a live
                // match, show the other side's chance in its colour so the island carries the pair.
                HStack(spacing: 4) {
                    Text(now)
                        .foregroundStyle(reading.color(reading.trail, onDark: true))
                    GameActivityCrestOrBadge(reading: reading, side: reading.trail)
                }
            } else if reading.pair != nil || reading.snapshot.lifecycle == .live,
                      let lead = reading.score(reading.lead),
                      let trail = reading.score(reading.trail) {
                // #199 — the score, the leader's first, beside its badge on the left.
                Text("\(lead)–\(trail)")
                    .minimumScaleFactor(0.6)
                    .foregroundStyle(.primary)
            } else if let value = reading.percent(reading.lead) ?? reading.singleChance {
                Text(reading.percentText(value))
            } else if reading.snapshot.lifecycle == .suspended {
                Text("Paused")
            } else {
                Text("—")
            }
        }
        .font(.caption.weight(.heavy))
        .monospacedDigit()
        .lineLimit(1)
        .minimumScaleFactor(0.75)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.compactSpoken)
    }
}

@available(iOS 17.0, *)
struct GameActivityMinimal: View {
    let reading: GameActivityReading

    var body: some View {
        Group {
            if !reading.matches {
                Text("—")
            } else if reading.snapshot.isFinal {
                Image(systemName: "flag.checkered")
            } else if reading.snapshot.isTerminal {
                Image(systemName: "questionmark")
            } else if let now = reading.minimalNowText(reading.lead) {
                Text(now)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .foregroundStyle(reading.color(reading.lead, onDark: true))
            } else if reading.snapshot.lifecycle == .live,
                      let home = reading.score(.home), let away = reading.score(.away) {
                Text("\(home)–\(away)")
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .foregroundStyle(.primary)
            } else if reading.snapshot.lifecycle == .suspended {
                Image(systemName: "pause.fill")
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
struct GameActivitySmallView: View {
    let reading: GameActivityReading

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 4) {
                    GameActivityStatusPill(reading: reading)
                        .fixedSize(horizontal: true, vertical: false)
                    Spacer(minLength: 2)
                    trailingChance(fontSize: nil)
                }
                HStack(spacing: 4) {
                    compactStatusPill(fontSize: nil, horizontalPadding: 7, dotSize: 6)
                    Spacer(minLength: 2)
                    trailingChance(fontSize: nil)
                }
                HStack(spacing: 4) {
                    compactStatusPill(fontSize: 10, horizontalPadding: 6, dotSize: 5)
                    Spacer(minLength: 2)
                    trailingChance(fontSize: 10)
                }
                VStack(alignment: .leading, spacing: 2) {
                    compactStatusPill(fontSize: 10, horizontalPadding: 6, dotSize: 5)
                    trailingChance(fontSize: 10)
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

    @ViewBuilder
    private func compactStatusPill(fontSize: CGFloat?, horizontalPadding: CGFloat, dotSize: CGFloat) -> some View {
        HStack(spacing: 4) {
            if reading.isLive {
                Circle().fill(Color.white).frame(width: dotSize, height: dotSize)
            }
            Text(reading.compactStatusText)
                .font(fontSize.map { .system(size: $0, weight: .bold) } ?? .caption2.weight(.bold))
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, horizontalPadding)
        .padding(.vertical, 3)
        .foregroundStyle(reading.pillForeground)
        .background(reading.pillBackground, in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.statusSpoken)
    }

    @ViewBuilder
    private func trailingChance(fontSize: CGFloat?) -> some View {
        if let now = reading.nowText(reading.lead) {
            Text("\(reading.badge(reading.lead)) \(now)")
                .font(fontSize.map { .system(size: $0, weight: .semibold) } ?? .caption2.weight(.semibold))
                .monospacedDigit()
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        } else if let single = reading.singleChance {
            let text = reading.snapshot.probabilityText ?? reading.percentText(single)
            Text("\(reading.badge(.home)) \(text)")
                .font(fontSize.map { .system(size: $0, weight: .semibold) } ?? .caption2.weight(.semibold))
                .monospacedDigit()
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
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
