import CoreGraphics
import SwiftUI

/// #12616 (183-A, Saturday goal item 5) — Home Screen saved-game widget (`systemSmall`
/// `158×158` and `systemMedium` `338×158`) redrawn from the compact game-page
/// headline size family:
/// - Light card surface (`#FFFFFF`), dark primary ink (`#111827`), contrast-safe team
///   chances, circular team crests with initial-monogram fallbacks.
/// - `Small` shows crests + primary numbers; `Medium` carries the aligned headline
///   columns (`PROJ. · CHANCE` before, `SCORE · PREGAME · NOW` during,
///   `PREGAME · FINAL` after — `"Pregame"` always spelled out in full).
/// - Both team names in `Medium` always render at one size (`ViewThatFits` switches
///   both rows together from short names to abbreviations rather than shrinking one).
/// - Finished games mark the winner with an emerald checkmark (`✓`), omit the
///   probability bar (`reading.shares == nil`), and call out upset wins in the footer.
enum SavedGameWidgetSize12616: Equatable, Sendable {
    case small
    case medium
}

struct SavedGameHeadlineWidgetModel12616: Equatable, Sendable {
    enum Stage: Equatable, Sendable {
        case before
        case during
        case after
    }

    struct ColumnHeaders: Equatable, Sendable {
        let leading: String?
        let pregame: String?
        let primary: String
    }

    struct SideRow: Equatable, Sendable {
        let shortName: String
        let abbreviation: String
        let crestFillHex: String
        let teamInkHex: String
        let figure: String
        let projectedText: String?
        let liveScoreText: String?
        let pregameText: String?
        let isEmphasized: Bool
        let isWinner: Bool
        let isLoser: Bool
        let isDraw: Bool
    }

    let stage: Stage
    let leagueLabel: String?
    let smallTopMeta: String
    let mediumTopMeta: String
    let smallTopTrailing: String?
    let liveBadgeText: String?
    let headers: ColumnHeaders
    let away: SideRow
    let home: SideRow
    let smallFooter: String
    let mediumFooter: String
    let footerIsEmeraldCallout: Bool
    let clearsRefreshTrailing: Bool

    static func build(
        reading: SavedWidgetReading10875,
        art: SavedWidgetArt12466,
        clockFooter: String?,
        isOffline: Bool,
        clearsRefreshTrailing: Bool,
        now: Date = Date(),
        timeZone: TimeZone = .current
    ) -> SavedGameHeadlineWidgetModel12616 {
        let stage: Stage = {
            if reading.phase == .result || art.isFinished { return .after }
            if art.isLive { return .during }
            return .before
        }()

        let lightHexes = art.barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)
        let badgeHexes = art.fillHexes()

        let awayRow = reading.rows[0]
        let homeRow = reading.rows[1]
        let awayShortName = art.awayShortName ?? awayRow.shortLabel
        let homeShortName = art.homeShortName ?? homeRow.shortLabel

        let pregame = art.pregameChances
        let hasAnyPregame = (pregame?.awayText != nil || pregame?.homeText != nil)

        let headers: ColumnHeaders = {
            switch stage {
            case .before:
                return ColumnHeaders(
                    leading: art.projectedBefore != nil ? "Proj." : nil,
                    pregame: nil,
                    primary: "Chance"
                )
            case .during:
                return ColumnHeaders(
                    leading: art.scores != nil ? "Score" : nil,
                    pregame: hasAnyPregame ? "Pregame" : nil,
                    primary: "Now"
                )
            case .after:
                return ColumnHeaders(
                    leading: nil,
                    pregame: hasAnyPregame ? "Pregame" : nil,
                    primary: "Final"
                )
            }
        }()

        func makeSideRow(isHome: Bool) -> SideRow {
            let r = isHome ? homeRow : awayRow
            let abbr = isHome ? art.home.short : art.away.short
            let shortName = isHome ? homeShortName : awayShortName
            let proj = art.projectedBefore.map { String(isHome ? $0.home : $0.away) }
            let liveScore = art.scores.map { String(isHome ? $0.home : $0.away) }
            let preText = isHome ? pregame?.homeText : pregame?.awayText
            let won = r.verdict == "Won"
            let lost = r.verdict == "Lost"
            let draw = r.verdict == "Draw"
            return SideRow(
                shortName: shortName,
                abbreviation: abbr,
                crestFillHex: isHome ? badgeHexes.home : badgeHexes.away,
                teamInkHex: isHome ? lightHexes.home : lightHexes.away,
                figure: r.figure ?? "—",
                projectedText: proj,
                liveScoreText: liveScore,
                pregameText: preText,
                isEmphasized: r.emphasized,
                isWinner: won,
                isLoser: lost,
                isDraw: draw
            )
        }

        let awaySide = makeSideRow(isHome: false)
        let homeSide = makeSideRow(isHome: true)

        let (smallTop, mediumTop): (String, String) = {
            switch stage {
            case .during:
                return (art.leagueLabel ?? "Live", art.leagueLabel ?? "")
            case .after:
                let finalWord = art.leagueLabel.map { "\($0) · Final" } ?? "Final"
                return (finalWord, finalWord)
            case .before:
                if let commence = art.commenceTime {
                    if art.startIsTbd {
                        let d = Self.shortMonthDay(commence, timeZone: timeZone)
                        let base = art.leagueLabel.map { "\($0) · \(d)" } ?? d
                        return (base, "\(base) · TBD")
                    }
                    let smallWhen = Self.compactStartText(commence, now: now, timeZone: timeZone)
                    let mediumWhen = Self.mediumStartText(commence, now: now, timeZone: timeZone)
                    return (
                        art.leagueLabel.map { "\($0) · \(smallWhen)" } ?? smallWhen,
                        art.leagueLabel.map { "\($0) · \(mediumWhen)" } ?? mediumWhen
                    )
                }
                let fallback = art.leagueLabel.map { "\($0) · \(reading.status)" } ?? reading.status
                return (fallback, fallback)
            }
        }()

        let winnerIsHome: Bool? = {
            if homeSide.isWinner { return true }
            if awaySide.isWinner { return false }
            return nil
        }()

        let winnerPregamePct: Int? = {
            guard let winnerIsHome else { return nil }
            return winnerIsHome ? pregame?.homePercent : pregame?.awayPercent
        }()
        let winnerPregameText: String? = {
            guard let winnerIsHome else { return nil }
            return winnerIsHome ? pregame?.homeText : pregame?.awayText
        }()

        let smallTopTrailing: String? = {
            guard stage == .after, let text = winnerPregameText else { return nil }
            return "Pregame \(text)"
        }()

        // Truth guard: offline, last-recorded, and opening-line readings always keep their clock caption.
        let requiresClockOverride = isOffline || reading.phase == .lastRecorded || reading.phase == .openingLine
        let fallbackClock = clockFooter ?? (stage == .after ? "Final" : reading.status)

        let smallFooter: String
        let mediumFooter: String
        let footerIsEmerald: Bool

        if requiresClockOverride {
            smallFooter = fallbackClock
            mediumFooter = fallbackClock
            footerIsEmerald = false
        } else {
            switch stage {
            case .after:
                if let winnerIsHome, let pct = winnerPregamePct, pct < 50 {
                    let winnerName = winnerIsHome ? homeSide.shortName : awaySide.shortName
                    smallFooter = "Won from \(pct)% pregame"
                    mediumFooter = "\(winnerName) won from a \(pct)% pregame chance"
                    footerIsEmerald = true
                } else {
                    smallFooter = "Final"
                    mediumFooter = "Final"
                    footerIsEmerald = false
                }
            case .during:
                let leaderIsHome = homeSide.isEmphasized || (!awaySide.isEmphasized && reading.headline?.label == homeRow.label)
                let leaderAbbr = leaderIsHome ? homeSide.abbreviation : awaySide.abbreviation
                let leaderPre = leaderIsHome ? pregame?.homeText : pregame?.awayText
                if let leaderPre {
                    smallFooter = "Pregame \(leaderAbbr) \(leaderPre)"
                } else {
                    smallFooter = ""
                }
                mediumFooter = ""
                footerIsEmerald = false
            case .before:
                if let proj = art.projectedBefore {
                    let homeFav = proj.home >= proj.away
                    let high = max(proj.away, proj.home)
                    let low = min(proj.away, proj.home)
                    let favAbbr = homeFav ? homeSide.abbreviation : awaySide.abbreviation
                    smallFooter = proj.home == proj.away
                        ? "Proj. \(proj.away)–\(proj.home)"
                        : "Proj. \(high)–\(low) \(favAbbr)"
                } else {
                    smallFooter = ""
                }
                mediumFooter = ""
                footerIsEmerald = false
            }
        }

        return SavedGameHeadlineWidgetModel12616(
            stage: stage,
            leagueLabel: art.leagueLabel,
            smallTopMeta: smallTop,
            mediumTopMeta: mediumTop,
            smallTopTrailing: smallTopTrailing,
            liveBadgeText: art.liveBadgeText,
            headers: headers,
            away: awaySide,
            home: homeSide,
            smallFooter: smallFooter,
            mediumFooter: mediumFooter,
            footerIsEmeraldCallout: footerIsEmerald,
            clearsRefreshTrailing: clearsRefreshTrailing
        )
    }

    private static func shortMonthDay(_ date: Date, timeZone: TimeZone) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        f.dateFormat = "MMM d"
        return f.string(from: date)
    }

    private static func compactStartText(_ date: Date, now: Date, timeZone: TimeZone) -> String {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = timeZone
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        let mins = cal.component(.minute, from: date)
        let hrFormat = mins == 0 ? "ha" : "h:mma"
        let diffDays = cal.dateComponents(
            [.day],
            from: cal.startOfDay(for: now),
            to: cal.startOfDay(for: date)
        ).day ?? 0
        if diffDays == 0 {
            f.dateFormat = hrFormat
            return f.string(from: date).lowercased()
        } else if diffDays > 0 && diffDays < 6 {
            f.dateFormat = "EEE \(hrFormat)"
            let raw = f.string(from: date)
            let parts = raw.split(separator: " ", maxSplits: 1).map(String.init)
            return parts.count == 2 ? "\(parts[0]) \(parts[1].lowercased())" : raw
        } else {
            f.dateFormat = "MMM d"
            return f.string(from: date)
        }
    }

    private static func mediumStartText(_ date: Date, now: Date, timeZone: TimeZone) -> String {
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
            return "Today \(f.string(from: date))"
        } else if diffDays > 0 && diffDays < 6 {
            f.dateFormat = "EEE h:mm a"
            return f.string(from: date)
        } else {
            f.dateFormat = "MMM d, h:mm a"
            return f.string(from: date)
        }
    }
}

struct SavedHeadlineCrest12616: View {
    let png: Data?
    let abbreviation: String
    let fillHex: String
    let size: CGFloat
    var fullColor: Bool = true

    var body: some View {
        ZStack {
            if let image = SavedWidgetLogos12466.image(png) {
                Circle().fill(fullColor ? Color(hex: "#F3F4F6") : Color.primary.opacity(0.14))
                Image(decorative: image, scale: 1)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .padding(size * 0.12)
            } else {
                Circle().fill(fullColor ? Color(hex: fillHex) : Color.primary.opacity(0.18))
                Text(abbreviation)
                    .font(.system(size: size * 0.34, weight: .heavy, design: .rounded))
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                    .foregroundStyle(fullColor ? Color(hex: SavedWidgetArt12466.ink(on: fillHex)) : Color.primary)
                    .padding(size * 0.1)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

private enum SavedHeadlineTokens12616 {
    static let inkPrimary = Color(hex: "#111827")
    static let inkSecondary = Color(hex: "#6B7280")
    static let inkContext = Color(hex: "#374151")
    static let liveRed = Color(hex: "#DC2626")
    static let wonEmerald = Color(hex: "#059669")

    static let mediumLeadingColWidth: CGFloat = 38
    static let mediumPregameColWidth: CGFloat = 52
    static let mediumPrimaryColWidth: CGFloat = 54
}

struct SavedGameHeadlineWidgetView12616<BarContent: View>: View {
    let model: SavedGameHeadlineWidgetModel12616
    let size: SavedGameWidgetSize12616
    let awayLogo: Data?
    let homeLogo: Data?
    var fullColor: Bool = true
    @ViewBuilder let bar: () -> BarContent

    private var inkPrimary: Color { SavedHeadlineTokens12616.inkPrimary }
    private var inkSecondary: Color { SavedHeadlineTokens12616.inkSecondary }
    private var inkContext: Color { SavedHeadlineTokens12616.inkContext }
    private var liveRed: Color { SavedHeadlineTokens12616.liveRed }
    private var wonEmerald: Color { SavedHeadlineTokens12616.wonEmerald }
    private var mediumLeadingColWidth: CGFloat { SavedHeadlineTokens12616.mediumLeadingColWidth }
    private var mediumPregameColWidth: CGFloat { SavedHeadlineTokens12616.mediumPregameColWidth }
    private var mediumPrimaryColWidth: CGFloat { SavedHeadlineTokens12616.mediumPrimaryColWidth }

    var body: some View {
        switch size {
        case .small:
            smallBody
        case .medium:
            mediumBody
        }
    }

    // MARK: - Small (158×158)

    private var smallBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            smallHeader
            Spacer(minLength: 4)
            VStack(spacing: 6) {
                smallTeamRow(model.away, logo: awayLogo)
                smallTeamRow(model.home, logo: homeLogo)
            }
            Spacer(minLength: 4)
            if model.stage != .after {
                bar()
                    .padding(.bottom, model.smallFooter.isEmpty ? 0 : 5)
                    .padding(.trailing, model.smallFooter.isEmpty && model.clearsRefreshTrailing ? 22 : 0)
            }
            if !model.smallFooter.isEmpty {
                footerText(model.smallFooter)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var smallHeader: some View {
        HStack(spacing: 4) {
            if model.stage == .during, let badge = model.liveBadgeText {
                liveCapsule(badge)
                Spacer(minLength: 2)
                if let league = model.leagueLabel {
                    Text(league)
                        .font(HeadlineStyleTable199.headers(.widget, scaledSize: 10))
                        .foregroundStyle(inkSecondary)
                        .lineLimit(1)
                }
            } else {
                Text(model.smallTopMeta)
                    .font(HeadlineStyleTable199.quietText(.widget, monospacedDigits: true, scaledSize: HeadlineStyleTable199.quietTextBaseSize(.widget)))
                    .foregroundStyle(inkSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                Spacer(minLength: 3)
                if let trailing = model.smallTopTrailing {
                    Text(trailing)
                        .font(HeadlineStyleTable199.quietText(.widget, monospacedDigits: true, scaledSize: 9.5))
                        .foregroundStyle(inkSecondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
        }
    }

    private func smallTeamRow(_ row: SavedGameHeadlineWidgetModel12616.SideRow, logo: Data?) -> some View {
        HStack(spacing: 6) {
            SavedHeadlineCrest12616(
                png: logo,
                abbreviation: row.abbreviation,
                fillHex: row.crestFillHex,
                size: 20,
                fullColor: fullColor
            )

            if model.stage == .during, let liveScore = row.liveScoreText {
                Text(liveScore)
                    .font(HeadlineStyleTable199.secondNumbers(.widget, prominent: false, scaledSize: 14.5))
                    .foregroundStyle(inkPrimary)
                    .lineLimit(1)
            } else {
                Text(row.abbreviation)
                    .font(HeadlineStyleTable199.names(.widget, isLoser: model.stage == .after && row.isLoser, scaledSize: 13))
                    .foregroundStyle(model.stage == .after && row.isLoser ? inkSecondary : inkPrimary)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            if model.stage == .after && row.isWinner {
                HStack(alignment: .firstTextBaseline, spacing: 2.5) {
                    Text(row.figure)
                        .font(HeadlineStyleTable199.secondNumbers(
                            .widget,
                            prominent: true,
                            scaledSize: HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: true)
                        ))
                        .foregroundStyle(primaryFigureColor(row))
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Text("\u{2713}")
                        .font(HeadlineStyleTable199.secondNumbers(
                            .widget,
                            prominent: true,
                            scaledSize: HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: true) * 0.82
                        ))
                        .foregroundStyle(fullColor ? wonEmerald : Color.primary)
                        .lineLimit(1)
                }
            } else {
                Text(row.figure)
                    .font(model.stage == .after
                        ? HeadlineStyleTable199.secondNumbers(
                            .widget,
                            prominent: !row.isLoser,
                            scaledSize: row.isLoser ? HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: false) : HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: true)
                        )
                        : HeadlineStyleTable199.now(.widget, scaledSize: HeadlineStyleTable199.nowBaseSize(.widget)))
                    .foregroundStyle(primaryFigureColor(row))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
        }
    }

    // MARK: - Medium (338×158)

    private var mediumBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            mediumHeader
            Spacer(minLength: 4)
            // Both team names at ONE size: full short-names if both fit whole,
            // otherwise both abbreviations — never shrinking one side on its own.
            ViewThatFits(in: .horizontal) {
                VStack(spacing: 6) {
                    mediumTeamRow(model.away, logo: awayLogo, useAbbreviation: false)
                    mediumTeamRow(model.home, logo: homeLogo, useAbbreviation: false)
                }
                VStack(spacing: 6) {
                    mediumTeamRow(model.away, logo: awayLogo, useAbbreviation: true)
                    mediumTeamRow(model.home, logo: homeLogo, useAbbreviation: true)
                }
            }
            Spacer(minLength: 4)
            if model.stage != .after {
                bar()
                    .padding(.bottom, model.mediumFooter.isEmpty ? 2 : 5)
                    .padding(.trailing, model.mediumFooter.isEmpty && model.clearsRefreshTrailing ? 22 : 0)
            }
            if !model.mediumFooter.isEmpty {
                footerText(model.mediumFooter)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var mediumHeader: some View {
        HStack(alignment: .center, spacing: 6) {
            if model.stage == .during, let badge = model.liveBadgeText {
                liveCapsule(badge)
                if !model.mediumTopMeta.isEmpty {
                    Text(model.mediumTopMeta)
                        .font(HeadlineStyleTable199.quietText(.widget, monospacedDigits: false, scaledSize: 11))
                        .foregroundStyle(inkSecondary)
                        .lineLimit(1)
                }
            } else {
                Text(model.mediumTopMeta)
                    .font(HeadlineStyleTable199.quietText(.widget, monospacedDigits: true, scaledSize: 11))
                    .foregroundStyle(inkSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }

            Spacer(minLength: 6)

            HStack(spacing: 6) {
                if let leading = model.headers.leading {
                    Text(leading)
                        .frame(width: mediumLeadingColWidth, alignment: .trailing)
                }
                if let pregame = model.headers.pregame {
                    Text(pregame)
                        .frame(width: mediumPregameColWidth, alignment: .trailing)
                }
                Text(model.headers.primary)
                    .frame(width: mediumPrimaryColWidth, alignment: .trailing)
            }
            .font(HeadlineStyleTable199.headers(.widget, scaledSize: HeadlineStyleTable199.headerBaseSize(.widget)))
            .foregroundStyle(inkSecondary)
            .lineLimit(1)
        }
    }

    private func mediumTeamRow(
        _ row: SavedGameHeadlineWidgetModel12616.SideRow,
        logo: Data?,
        useAbbreviation: Bool
    ) -> some View {
        HStack(spacing: 6) {
            SavedHeadlineCrest12616(
                png: logo,
                abbreviation: row.abbreviation,
                fillHex: row.crestFillHex,
                size: 22,
                fullColor: fullColor
            )

            HStack(spacing: 4) {
                Text(useAbbreviation ? row.abbreviation : row.shortName)
                    .font(HeadlineStyleTable199.names(
                        .widget,
                        isLoser: model.stage == .after && row.isLoser,
                        scaledSize: HeadlineStyleTable199.nameBaseSize(.widget)
                    ))
                    .foregroundStyle(model.stage == .after && row.isLoser ? inkSecondary : inkPrimary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                if row.isDraw {
                    Text("Draw")
                        .font(HeadlineStyleTable199.headers(.widget, scaledSize: 10))
                        .foregroundStyle(inkSecondary)
                }
            }

            Spacer(minLength: 6)

            HStack(spacing: 6) {
                if model.headers.leading != nil {
                    let leadingValue = model.stage == .during ? row.liveScoreText : row.projectedText
                    Text(leadingValue ?? "")
                        .font(HeadlineStyleTable199.secondNumbers(
                            .widget,
                            prominent: false,
                            scaledSize: model.stage == .during ? HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: false) : 14
                        ))
                        .foregroundStyle(model.stage == .during ? inkPrimary : inkContext)
                        .frame(width: mediumLeadingColWidth, alignment: .trailing)
                        .lineLimit(1)
                }

                if model.headers.pregame != nil {
                    Text(row.pregameText ?? "")
                        .font(HeadlineStyleTable199.secondNumbers(
                            .widget,
                            prominent: false,
                            scaledSize: HeadlineStyleTable199.pregameNumberBaseSize(.widget)
                        ))
                        .foregroundStyle(inkSecondary)
                        .frame(width: mediumPregameColWidth, alignment: .trailing)
                        .lineLimit(1)
                }

                if model.stage == .after && row.isWinner {
                    HStack(alignment: .firstTextBaseline, spacing: 2.5) {
                        Text(row.figure)
                            .font(HeadlineStyleTable199.secondNumbers(
                                .widget,
                                prominent: true,
                                scaledSize: HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: true)
                            ))
                            .foregroundStyle(primaryFigureColor(row))
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                        Text("\u{2713}")
                            .font(HeadlineStyleTable199.secondNumbers(
                                .widget,
                                prominent: true,
                                scaledSize: HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: true) * 0.82
                            ))
                            .foregroundStyle(fullColor ? wonEmerald : Color.primary)
                            .lineLimit(1)
                    }
                    .frame(width: mediumPrimaryColWidth, alignment: .trailing)
                } else {
                    Text(row.figure)
                        .font(model.stage == .after
                            ? HeadlineStyleTable199.secondNumbers(
                                .widget,
                                prominent: !row.isLoser,
                                scaledSize: row.isLoser ? HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: false) : HeadlineStyleTable199.secondNumberBaseSize(.widget, prominent: true)
                            )
                            : HeadlineStyleTable199.now(.widget, scaledSize: HeadlineStyleTable199.nowBaseSize(.widget)))
                        .foregroundStyle(primaryFigureColor(row))
                        .frame(width: mediumPrimaryColWidth, alignment: .trailing)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                }
            }
        }
    }

    // MARK: - Shared Pieces

    private func liveCapsule(_ text: String) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(Color.white)
                .frame(width: 5, height: 5)
            Text(text)
                .font(HeadlineStyleTable199.headers(.widget, scaledSize: 10).monospacedDigit())
                .foregroundStyle(Color.white)
                .lineLimit(1)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(fullColor ? liveRed : Color.primary.opacity(0.28), in: Capsule())
    }

    private func primaryFigureColor(_ row: SavedGameHeadlineWidgetModel12616.SideRow) -> Color {
        guard fullColor else {
            return model.stage == .after && row.isLoser ? Color.primary.opacity(0.7) : Color.primary
        }
        switch model.stage {
        case .after:
            return row.isLoser ? inkSecondary : inkPrimary
        case .during:
            return Color(hex: row.teamInkHex)
        case .before:
            return row.figure == "—" ? inkSecondary : Color(hex: row.teamInkHex)
        }
    }

    private func footerText(_ text: String) -> some View {
        Text(text)
            .font(model.footerIsEmeraldCallout
                ? HeadlineStyleTable199.headers(.widget, scaledSize: 10.5)
                : HeadlineStyleTable199.quietText(.widget, monospacedDigits: true, scaledSize: HeadlineStyleTable199.quietTextBaseSize(.widget)))
            .foregroundStyle(
                fullColor && model.footerIsEmeraldCallout ? wonEmerald : inkSecondary
            )
            .lineLimit(1)
            .minimumScaleFactor(0.75)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.trailing, model.clearsRefreshTrailing ? 24 : 0)
    }
}
