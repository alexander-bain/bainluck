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
                        GameActivityProjectionLine(reading: reading)
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

    var showsForecast: Bool {
        matches && (snapshot.lifecycle == .live || snapshot.lifecycle == .scheduled)
    }
    var isLive: Bool { matches && !isStale && snapshot.lifecycle == .live }

    func name(_ side: Side) -> String { side == .home ? snapshot.homeTeam : snapshot.awayTeam }
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
    /// The page's admitted projected final, beside a live reading only.
    var projection: (label: String, away: Int, home: Int)? {
        guard matches, let label = snapshot.projectionLabel, let away = snapshot.projectedAwayScore,
              let home = snapshot.projectedHomeScore else { return nil }
        return (label, away, home)
    }
    /// The page's own wording: the label, then each badge glued to its number.
    var projectionText: String? {
        projection.map { "\($0.label): \(badge(.away))\u{00A0}\($0.away) · \(badge(.home))\u{00A0}\($0.home)" }
    }
    var projectionSpoken: String? {
        projection.map { "\($0.label): \(name(.away)) \($0.away), \(name(.home)) \($0.home)" }
    }
    func percentText(_ value: Int) -> String {
        (Double(value) / 100).formatted(.percent.precision(.fractionLength(0)))
    }
    /// The side the compact views lead with: the favourite of a two-way game, else home.
    var lead: Side {
        guard let pair else { return .home }
        return pair.away > pair.home ? .away : .home
    }
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

    func color(_ side: Side, onDark: Bool) -> Color {
        GameActivityColor.color(side == .home ? snapshot.homeColorHex : snapshot.awayColorHex, onDark: onDark)
    }
    /// The split bar's two colours. Two teams in the same red would read as one
    /// bar, so the trailing side goes grey when the colours are too close.
    func barColors(onDark: Bool) -> (away: Color, home: Color) {
        let close = GameActivityColor.tooClose(snapshot.awayColorHex, snapshot.homeColorHex)
        let away = color(.away, onDark: onDark), home = color(.home, onDark: onDark)
        guard close else { return (away, home) }
        return lead == .home ? (Color.gray, home) : (away, Color.gray)
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
    var footer: Text {
        guard matches else { return Text("Open Bain Luck for current details") }
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
        var parts = [name(side), score(side).map { "\($0)" } ?? "score unavailable"]
        if let value = percent(side) { parts.append("\(percentText(value)) chance to win") }
        if let verdict = verdict(side) { parts.append(verdict) }
        return parts.joined(separator: ", ")
    }
    var chanceSpoken: String {
        guard let pair else { return singleChanceLabel ?? "Win probability unavailable" }
        return "\(name(.away)) \(percentText(pair.away)), \(name(.home)) \(percentText(pair.home)) chance to win"
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
        parts.append(isStale ? "Stale reading. Open on iPhone to refresh."
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
    /// Both absent (two greys) or nearer than a quarter of the colour cube.
    static func tooClose(_ first: String?, _ second: String?) -> Bool {
        guard let a = rgb(first), let b = rgb(second) else { return first == nil && second == nil }
        return ((a.r - b.r) * (a.r - b.r) + (a.g - b.g) * (a.g - b.g) + (a.b - b.b) * (a.b - b.b)).squareRoot() < 0.25
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
            // so the card keeps room for the projection inside the Lock
            // Screen's 160-point height.
            HStack(alignment: .center, spacing: 8) {
                GameActivityStatusPill(reading: reading)
                Spacer(minLength: 4)
                GameActivityFooter(reading: reading, alignment: .trailing)
                    .layoutPriority(-1)
            }
            if reading.matches {
                VStack(spacing: 4) {
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
                GameActivityProjectionLine(reading: reading)
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
        let badge = reading.badge(side)
        let name = reading.name(side)
        HStack(spacing: 8) {
            Text(badge)
                .font(.headline.weight(.heavy))
                .frame(minWidth: 44, alignment: .leading)
            if name.caseInsensitiveCompare(badge) != .orderedSame {
                Text(name)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            Spacer(minLength: 6)
            Text(reading.scoreText(side))
                .font(.title2.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(reading.steppedBack(side) ? .secondary : .primary)
            if let value = reading.percent(side) {
                Text(reading.percentText(value))
                    .font(.subheadline.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(reading.lead == side && !reading.isStale ? .primary : .secondary)
                    .frame(minWidth: 48, alignment: .trailing)
            } else if let verdict = reading.verdict(side) {
                Text(verdict)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(reading.steppedBack(side) ? .secondary : .primary)
                    .frame(minWidth: 48, alignment: .trailing)
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
        reading.footer
            .font(.caption2)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .minimumScaleFactor(0.75)
            .frame(maxWidth: .infinity, alignment: alignment)
    }
}

/// The projected final, labeled as the page labels it and kept a step below
/// the actual score so the two are never read as one another.
@available(iOS 17.0, *)
private struct GameActivityProjectionLine: View {
    let reading: GameActivityReading

    var body: some View {
        if let text = reading.projectionText {
            Text(text)
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityLabel(reading.projectionSpoken ?? text)
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
            Text(reading.scoreText(side))
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .monospacedDigit()
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
                HStack {
                    Text("\(reading.badge(.away)) \(reading.percentText(pair.away))")
                    Spacer(minLength: 8)
                    Text("\(reading.percentText(pair.home)) \(reading.badge(.home))")
                }
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                GameActivitySplitBar(away: colors.away, home: colors.home, awayShare: Double(pair.away) / 100)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(reading.chanceSpoken)
        } else if let single = reading.singleChanceLabel {
            Text(single)
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .frame(maxWidth: .infinity, alignment: .leading)
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
            } else if reading.snapshot.isTerminal {
                Text("\(reading.badge(.away)) \(reading.scoreText(.away))")
                    .foregroundStyle(reading.lowerScoredSide == .away ? .secondary : .primary)
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
            } else if reading.snapshot.isTerminal {
                Text("\(reading.scoreText(.home)) \(reading.badge(.home))")
                    .foregroundStyle(reading.lowerScoredSide == .home ? .secondary : .primary)
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
