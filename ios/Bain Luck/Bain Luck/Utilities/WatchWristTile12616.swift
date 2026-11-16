import Foundation
import SwiftUI

/// #12616 (183-A, Saturday goal item 5) — Apple Watch wrist tile (`WatchPinnedHomeView12640`
/// game pin row and selected-game hero).
///
/// Never crams 2 rows × 3 columns onto a 41 mm wrist: names ONE side (the favored
/// side before/during, or the winner after — and home on a draw-priced sport whose
/// away price is withheld by `DrawPricedWinner`) in bold type beside a 30 pt
/// rounded primary reading, a circular team monogram badge, and one supporting line.
nonisolated struct WatchWristTileInput12616: Equatable, Sendable {
    var homeTeam: String
    var awayTeam: String
    var homeServedAbbreviation: String? = nil
    var awayServedAbbreviation: String? = nil
    var sportKey: String? = nil
    var isLive: Bool = false
    var isFinal: Bool = false
    var homeScore: Int? = nil
    var awayScore: Int? = nil
    var homeProbability: Double? = nil
    var awayProbability: Double? = nil
    var drawProbability: Double? = nil
    var prematchHomeProbability: Double? = nil
    var prematchAwayProbability: Double? = nil
    var prematchDrawProbability: Double? = nil
    var projectedHomeScore: Double? = nil
    var projectedAwayScore: Double? = nil
    var homePrimaryColor: String? = nil
    var homeSecondaryColor: String? = nil
    var awayPrimaryColor: String? = nil
    var awaySecondaryColor: String? = nil
    var commenceTime: Date? = nil
    var liveClockText: String? = nil
    var stateLabel: String = "Scheduled"
    var probabilityObservedAt: Date? = nil
    var scoreObservedAt: Date? = nil
}

struct WatchWristTileModel12616: Equatable, Sendable {
    enum Stage: Equatable, Sendable {
        case before
        case during
        case after
    }

    let stage: Stage
    let topMetaText: String
    let liveCapsuleText: String?
    let liveScoreMetaText: String?
    let showsFinalCheckmark: Bool
    let leaderName: String
    let leaderAbbreviation: String
    let heroFigureText: String
    let heroInkHex: String
    let badgeFillHex: String
    let badgeInkHex: String
    let supportingLine: String

    /// WCAG luminance of the dark Watch card surface (`#14161C`).
    static let watchSurfaceLuminance = 0.016
    private static let emeraldBrightHex = "#34D399"
    private static let darkFallbackSkyHex = "#38BDF8"

    static func build(
        _ input: WatchWristTileInput12616,
        now: Date = Date(),
        timeZone: TimeZone = .current
    ) -> WatchWristTileModel12616 {
        let abbrs = TeamShortName.abbreviationPair(
            away: input.awayTeam,
            home: input.homeTeam,
            awayServed: input.awayServedAbbreviation,
            homeServed: input.homeServedAbbreviation
        )
        let rawNames = TeamShortName.shortPair(
            away: input.awayTeam,
            home: input.homeTeam,
            sportKey: input.sportKey
        )
        let names = (
            away: wristClubName(rawNames.away, sportKey: input.sportKey),
            home: wristClubName(rawNames.home, sportKey: input.sportKey)
        )

        let badgeFills = ProbabilityBarPalette.pair(
            awayHex: input.awayPrimaryColor,
            homeHex: input.homePrimaryColor
        )

        // MARK: - After (Settled Final)
        if input.isFinal, let hs = input.homeScore, let ascore = input.awayScore {
            let pregamePair = resolvePregamePercents(input)
            if hs == ascore {
                let homeBadge = badgeFills.home
                let drawSupporting: String = {
                    if let drawPct = renderedPercent(input.prematchDrawProbability) {
                        return "Pregame Draw \(drawPct)%"
                    }
                    if let homePct = pregamePair.home {
                        return "Pregame \(abbrs.home) \(homePct)%"
                    }
                    return ""
                }()
                return WatchWristTileModel12616(
                    stage: .after,
                    topMetaText: "FINAL · DRAW",
                    liveCapsuleText: nil,
                    liveScoreMetaText: nil,
                    showsFinalCheckmark: false,
                    leaderName: "\(abbrs.away)–\(abbrs.home)",
                    leaderAbbreviation: abbrs.home,
                    heroFigureText: "\(ascore)–\(hs)",
                    heroInkHex: "#E5E7EB",
                    badgeFillHex: homeBadge,
                    badgeInkHex: badgeInk(on: homeBadge),
                    supportingLine: drawSupporting
                )
            }

            let winnerIsHome = hs > ascore
            let winnerName = winnerIsHome ? names.home : names.away
            let opponentUpper = (winnerIsHome ? names.away : names.home).uppercased()
            let preposition = winnerIsHome ? "VS" : "AT"
            let badgeFill = winnerIsHome ? badgeFills.home : badgeFills.away
            let winnerPrePct = winnerIsHome ? pregamePair.home : pregamePair.away

            let supporting: String = {
                if let pct = winnerPrePct {
                    if pct < 50 {
                        return "Won from \(pct)% pregame chance"
                    }
                    return "Pregame \(pct)%"
                }
                return ""
            }()

            return WatchWristTileModel12616(
                stage: .after,
                topMetaText: "FINAL · \(preposition) \(opponentUpper)",
                liveCapsuleText: nil,
                liveScoreMetaText: nil,
                showsFinalCheckmark: true,
                leaderName: winnerName,
                leaderAbbreviation: winnerIsHome ? abbrs.home : abbrs.away,
                heroFigureText: "\(max(hs, ascore))–\(min(hs, ascore))",
                heroInkHex: emeraldBrightHex,
                badgeFillHex: badgeFill,
                badgeInkHex: badgeInk(on: badgeFill),
                supportingLine: supporting
            )
        }

        // MARK: - Forecast Leader Resolution (Before & During)
        let resolved = resolveLeader(input)
        let leaderIsHome = resolved.isHome
        let leaderName = leaderIsHome ? names.home : names.away
        let leaderAbbr = leaderIsHome ? abbrs.home : abbrs.away
        let opponentAbbr = leaderIsHome ? abbrs.away : abbrs.home
        let badgeFill = leaderIsHome ? badgeFills.home : badgeFills.away
        let heroHex = readableDarkSurfaceHex(
            primary: leaderIsHome ? input.homePrimaryColor : input.awayPrimaryColor,
            secondary: leaderIsHome ? input.homeSecondaryColor : input.awaySecondaryColor,
            badgeFallback: badgeFill
        )
        let heroFigure = resolved.percent.map { "\($0)%" } ?? "—"

        // MARK: - During (Live)
        if input.isLive {
            let capsule = (input.liveClockText?.isEmpty == false) ? input.liveClockText! : "LIVE"
            let scoreMeta: String? = {
                guard let ascore = input.awayScore, let hs = input.homeScore else { return nil }
                return leaderIsHome
                    ? "\(abbrs.home) \(hs)–\(ascore) \(abbrs.away)"
                    : "\(abbrs.away) \(ascore)–\(hs) \(abbrs.home)"
            }()
            let topFallback = leaderIsHome ? "VS \(opponentAbbr)" : "AT \(opponentAbbr)"

            let pregamePair = resolvePregamePercents(input)
            let leaderPrePct = leaderIsHome ? pregamePair.home : pregamePair.away
            let supporting: String = {
                if let cur = resolved.percent, let pre = leaderPrePct {
                    let delta = cur - pre
                    if delta > 0 {
                        let unit = delta == 1 ? "point" : "points"
                        return "Up \(delta) \(unit) from \(pre)%"
                    } else if delta < 0 {
                        let drop = abs(delta)
                        let unit = drop == 1 ? "point" : "points"
                        return "Down \(drop) \(unit) from \(pre)%"
                    } else {
                        return "Even with \(pre)%"
                    }
                }
                if let obs = input.probabilityObservedAt, obs <= now {
                    let age = now.timeIntervalSince(obs)
                    if age > 120 {
                        return "As of \(shortClock(obs, timeZone: timeZone))"
                    }
                    let mins = Int((age / 60).rounded(.down))
                    return mins >= 1 ? "Live · \(mins)m ago" : "Live"
                }
                return "Live"
            }()

            return WatchWristTileModel12616(
                stage: .during,
                topMetaText: scoreMeta ?? topFallback,
                liveCapsuleText: capsule,
                liveScoreMetaText: scoreMeta,
                showsFinalCheckmark: false,
                leaderName: leaderName,
                leaderAbbreviation: leaderAbbr,
                heroFigureText: heroFigure,
                heroInkHex: heroHex,
                badgeFillHex: badgeFill,
                badgeInkHex: badgeInk(on: badgeFill),
                supportingLine: supporting
            )
        }

        // MARK: - Before (Scheduled)
        let whenText: String = {
            guard let start = input.commenceTime else { return input.stateLabel.uppercased() }
            if now >= start { return "OPEN TO UPDATE" }
            return upcomingWhenText(start, now: now, timeZone: timeZone).uppercased()
        }()
        let preposition = leaderIsHome ? "VS \(opponentAbbr)" : "AT \(opponentAbbr)"
        let topMeta = "\(whenText) · \(preposition)"

        let projected = resolveProjectedPair(input)
        let projClause: String? = projected.map { proj in
            let leaderScore = leaderIsHome ? proj.home : proj.away
            let oppScore = leaderIsHome ? proj.away : proj.home
            return "Proj. \(leaderScore)–\(oppScore)"
        }

        let statusWord: String = {
            if resolved.isFavored { return "Favored" }
            if resolved.isEven { return "Even matchup" }
            return "Home win chance"
        }()

        let supporting = projClause.map { "\(statusWord) · \($0)" } ?? statusWord

        return WatchWristTileModel12616(
            stage: .before,
            topMetaText: topMeta,
            liveCapsuleText: nil,
            liveScoreMetaText: nil,
            showsFinalCheckmark: false,
            leaderName: leaderName,
            leaderAbbreviation: leaderAbbr,
            heroFigureText: heroFigure,
            heroInkHex: heroHex,
            badgeFillHex: badgeFill,
            badgeInkHex: badgeInk(on: badgeFill),
            supportingLine: supporting
        )
    }

    // MARK: - Pure Helpers

    private static let soccerClubInitialismSuffixes = [
        " AFC", " CFC", " LFC", " FC", " CF", " SC"
    ]

    /// Strips trailing football-club initialisms (`"Arsenal FC"` → `"Arsenal"`,
    /// `"Liverpool FC"` → `"Liverpool"`) on soccer wrist tiles so the 41 mm card
    /// matches the short club name shown on the game page while preserving gender/
    /// reserve designators (`"Arsenal WFC"`, `"Alverca B"`) and leading prefixes
    /// (`"FC Köln"`).
    private static func wristClubName(_ label: String, sportKey: String?) -> String {
        guard TeamShortName.keepsWholeClubName(sportKey: sportKey) else { return label }
        let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines)
        let upper = trimmed.uppercased()
        for suffix in soccerClubInitialismSuffixes where upper.hasSuffix(suffix) {
            let base = String(trimmed.dropLast(suffix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            let letterCount = base.unicodeScalars.filter { CharacterSet.letters.contains($0) }.count
            if letterCount >= 3 {
                return base
            }
        }
        return trimmed
    }

    private static func resolveLeader(
        _ input: WatchWristTileInput12616
    ) -> (isHome: Bool, percent: Int?, isFavored: Bool, isEven: Bool) {
        let trimmedSport = input.sportKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let hasSport = !trimmedSport.isEmpty
        let sportPricesDraw = hasSport && DrawPricedWinner.sportPricesADraw(trimmedSport)

        // Explicit 3-way odds (genuine home, away, draw probabilities):
        if let draw = input.drawProbability,
           let h = input.homeProbability,
           let a = input.awayProbability {
            let hPct = renderedPercent(h)
            let aPct = renderedPercent(a)
            let dPct = renderedPercent(draw) ?? 0
            if let hPct, let aPct {
                let isHome = hPct >= aPct
                let leadPct = isHome ? hPct : aPct
                let oppPct = isHome ? aPct : hPct
                return (
                    isHome: isHome,
                    percent: leadPct,
                    isFavored: leadPct > oppPct && leadPct > dPct,
                    isEven: hPct == aPct
                )
            }
        }

        // Draw-priced sport without explicit draw odds (away is 1 - home complement)
        // or unclassified snapshot: always name HOME per DrawPricedWinner.headlineSide.
        if !hasSport || sportPricesDraw || input.drawProbability != nil {
            let hPct = renderedPercent(input.homeProbability)
            return (
                isHome: true,
                percent: hPct,
                isFavored: (hPct ?? 0) > 50,
                isEven: false
            )
        }

        // Standard two-way sport: duel-rounded pair when away is present, else home scalar.
        let duel = renderedDuelPercents(away: input.awayProbability, home: input.homeProbability)
        if let aPct = duel[0], let hPct = duel[1] {
            let isHome = hPct >= aPct
            let leadPct = isHome ? hPct : aPct
            return (
                isHome: isHome,
                percent: leadPct,
                isFavored: leadPct > 50,
                isEven: hPct == aPct
            )
        }

        let hPct = duel[1] ?? renderedPercent(input.homeProbability)
        return (
            isHome: true,
            percent: hPct,
            isFavored: (hPct ?? 0) > 50,
            isEven: hPct == 50
        )
    }

    private static func resolvePregamePercents(
        _ input: WatchWristTileInput12616
    ) -> (away: Int?, home: Int?) {
        let trimmedSport = input.sportKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let hasSport = !trimmedSport.isEmpty
        let sportPricesDraw = hasSport && DrawPricedWinner.sportPricesADraw(trimmedSport)

        if input.prematchDrawProbability != nil {
            return (
                away: renderedPercent(input.prematchAwayProbability),
                home: renderedPercent(input.prematchHomeProbability)
            )
        }
        if !hasSport || sportPricesDraw {
            return (
                away: nil,
                home: renderedPercent(input.prematchHomeProbability)
            )
        }
        let pair = renderedDuelPercents(
            away: input.prematchAwayProbability,
            home: input.prematchHomeProbability
        )
        return (away: pair[0], home: pair[1])
    }

    private static func resolveProjectedPair(
        _ input: WatchWristTileInput12616
    ) -> (away: Int, home: Int)? {
        let key = (input.sportKey ?? "").lowercased()
        let admitsUnit = key.hasPrefix("americanfootball_")
            || key.hasPrefix("basketball_")
            || key.hasPrefix("soccer_")
        guard admitsUnit else { return nil }
        let vocab = SportVocab.forSport(input.sportKey)
        guard vocab.sportsbookSpreadIsAMargin,
              let h = input.projectedHomeScore,
              let a = input.projectedAwayScore,
              h.isFinite, a.isFinite, h > 0, a > 0,
              let rh = Int(exactly: h.rounded()),
              let ra = Int(exactly: a.rounded()),
              rh != ra || vocab.canEndInATie
        else { return nil }
        return (away: ra, home: rh)
    }

    private static func contrast(_ hex: String?, against backgroundLuminance: Double) -> Double? {
        guard let l = TeamTextContrast.relativeLuminance(hex) else { return nil }
        return (max(l, backgroundLuminance) + 0.05) / (min(l, backgroundLuminance) + 0.05)
    }

    private static func readableDarkSurfaceHex(
        primary: String?,
        secondary: String?,
        badgeFallback: String
    ) -> String {
        for candidate in [primary, secondary, badgeFallback] {
            if let c = candidate,
               let ratio = contrast(c, against: watchSurfaceLuminance),
               ratio >= TeamTextContrast.minimumRatio {
                return c
            }
        }
        return darkFallbackSkyHex
    }

    private static func badgeInk(on hex: String) -> String {
        guard let onWhite = contrast(hex, against: 1.0),
              let onDark = contrast(hex, against: TeamTextContrast.relativeLuminance("#111827") ?? 0)
        else { return "#FFFFFF" }
        return onDark > onWhite ? "#111827" : "#FFFFFF"
    }

    private static func shortClock(_ date: Date, timeZone: TimeZone) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        f.dateFormat = "h:mm a"
        return f.string(from: date)
    }

    private static func upcomingWhenText(_ date: Date, now: Date, timeZone: TimeZone) -> String {
        let secs = date.timeIntervalSince(now)
        if secs > 0 && secs < 3600 {
            let mins = max(1, Int((secs / 60).rounded()))
            return "In \(mins)m"
        }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = timeZone
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        let diffDays = cal.dateComponents(
            [.day],
            from: cal.startOfDay(for: now),
            to: cal.startOfDay(for: date)
        ).day ?? 0
        if diffDays == 0 {
            f.dateFormat = "h:mm a"
            return f.string(from: date)
        } else if diffDays > 0 && diffDays < 6 {
            f.dateFormat = "EEE h:mm a"
            return f.string(from: date)
        } else {
            f.dateFormat = "MMM d"
            return f.string(from: date)
        }
    }
}

struct WatchWristTileView12616<LeadingAccessory: View>: View {
    let model: WatchWristTileModel12616
    var isAccessibilitySize: Bool = false
    var identifierPrefix: String? = nil
    @ViewBuilder let leadingAccessory: () -> LeadingAccessory

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            topMetaRow
            HStack(alignment: .center, spacing: 6) {
                heroRow
                    .frame(maxWidth: .infinity, alignment: .leading)
                if !isAccessibilitySize {
                    monogramBadge
                }
            }
            if !model.supportingLine.isEmpty {
                Text(model.supportingLine)
                    .font(HeadlineStyleTable199.quietText(.wristTile, monospacedDigits: true, scaledSize: HeadlineStyleTable199.quietTextBaseSize(.wristTile)))
                    .foregroundStyle(Color.white.opacity(0.68))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .modifier(OptionalIdentifier12616(id: identifierPrefix.map { "\($0).clock" }))
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Self.rgbColor("#14161C"))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.10), lineWidth: 1)
                )
        )
    }

    @ViewBuilder
    private var topMetaRow: some View {
        HStack(spacing: 4) {
            leadingAccessory()

            if let liveBadge = model.liveCapsuleText {
                HStack(spacing: 3) {
                    Circle()
                        .fill(Color.white)
                        .frame(width: 4, height: 4)
                    Text(liveBadge)
                        .font(HeadlineStyleTable199.headers(.wristTile, scaledSize: 9).monospacedDigit())
                        .foregroundStyle(Color.white)
                        .lineLimit(1)
                }
                .padding(.horizontal, 5)
                .padding(.vertical, 1.5)
                .background(Self.rgbColor("#DC2626"), in: Capsule())
                .fixedSize(horizontal: true, vertical: false)
                .modifier(OptionalIdentifier12616(
                    id: model.liveScoreMetaText != nil ? identifierPrefix.map { "\($0).header" } : nil
                ))

                Text(model.topMetaText)
                    .font(HeadlineStyleTable199.headers(.wristTile, scaledSize: 9.5).monospacedDigit())
                    .foregroundStyle(Color.white.opacity(0.78))
                    .lineLimit(1)
                    .minimumScaleFactor(0.70)
                    .layoutPriority(1)
                    .modifier(OptionalIdentifier12616(
                        id: identifierPrefix.map { model.liveScoreMetaText != nil ? "\($0).score" : "\($0).header" }
                    ))
            } else {
                if model.showsFinalCheckmark {
                    Image(systemName: "checkmark")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(Self.rgbColor("#34D399"))
                }
                Text(model.topMetaText)
                    .font(HeadlineStyleTable199.headers(.wristTile, scaledSize: HeadlineStyleTable199.headerBaseSize(.wristTile)))
                    .tracking(0.25)
                    .foregroundStyle(
                        model.showsFinalCheckmark
                            ? Self.rgbColor("#34D399")
                            : Color.white.opacity(0.68)
                    )
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
                    .modifier(OptionalIdentifier12616(id: identifierPrefix.map { "\($0).header" }))
            }
        }
    }

    @ViewBuilder
    private var heroRow: some View {
        let heroID = identifierPrefix.map {
            model.stage == .after ? "\($0).final" : "\($0).probability"
        }
        if isAccessibilitySize {
            VStack(alignment: .leading, spacing: 1) {
                Text(model.leaderName)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(Color.white)
                    .fixedSize(horizontal: false, vertical: true)
                Text(model.heroFigureText)
                    .font(.system(.title2, design: .rounded, weight: model.stage == .after ? .bold : .heavy).monospacedDigit())
                    .foregroundStyle(Self.rgbColor(model.heroInkHex))
                    .modifier(OptionalIdentifier12616(id: heroID))
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text(model.leaderName)
                        .font(HeadlineStyleTable199.names(.wristTile, scaledSize: HeadlineStyleTable199.nameBaseSize(.wristTile)))
                        .foregroundStyle(Color.white)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text(model.heroFigureText)
                        .font(heroFigureFont(size: HeadlineStyleTable199.nowBaseSize(.wristTile)))
                        .foregroundStyle(Self.rgbColor(model.heroInkHex))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .modifier(OptionalIdentifier12616(id: heroID))
                }
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text(model.leaderName)
                        .font(HeadlineStyleTable199.names(.wristTile, scaledSize: 13))
                        .foregroundStyle(Color.white)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text(model.heroFigureText)
                        .font(heroFigureFont(size: 21))
                        .foregroundStyle(Self.rgbColor(model.heroInkHex))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .modifier(OptionalIdentifier12616(id: heroID))
                }
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text(model.leaderAbbreviation)
                        .font(HeadlineStyleTable199.names(.wristTile, scaledSize: 14.5))
                        .foregroundStyle(Color.white)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text(model.heroFigureText)
                        .font(heroFigureFont(size: 24))
                        .foregroundStyle(Self.rgbColor(model.heroInkHex))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .modifier(OptionalIdentifier12616(id: heroID))
                }
            }
        }
    }

    private func heroFigureFont(size: CGFloat) -> Font {
        model.stage == .after
            ? HeadlineStyleTable199.secondNumbers(.wristTile, prominent: true, scaledSize: size)
            : HeadlineStyleTable199.now(.wristTile, scaledSize: size)
    }

    private var monogramBadge: some View {
        ZStack {
            Circle()
                .fill(Self.rgbColor(model.badgeFillHex))
            Circle()
                .strokeBorder(Color.white.opacity(0.32), lineWidth: 1.25)
            Text(model.leaderAbbreviation)
                .font(.system(size: 10.5, weight: .heavy, design: .rounded))
                .foregroundStyle(Self.rgbColor(model.badgeInkHex))
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .padding(3)
        }
        .frame(width: 32, height: 32)
        .accessibilityHidden(true)
    }

    private static func rgbColor(_ hex: String) -> Color {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else { return .white }
        return Color(
            red: Double(rgb.r) / 255.0,
            green: Double(rgb.g) / 255.0,
            blue: Double(rgb.b) / 255.0
        )
    }
}

private struct OptionalIdentifier12616: ViewModifier {
    let id: String?

    @ViewBuilder
    func body(content: Content) -> some View {
        if let id {
            content.accessibilityIdentifier(id)
        } else {
            content
        }
    }
}
