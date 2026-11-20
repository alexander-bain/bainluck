import SwiftUI
import WidgetKit

// #12466 — the saved widget's look, Matchup (look A; Alex, Tue Nov 10: "A is
// the best today"): both teams' colours meeting on a diagonal, crests on white
// discs, both chances large, a white bar. The other three looks offered beside it
// (Clean, Scoreboard, Favorite) are not kept; a reader's own choice of look is a
// later item.
//
// Every look draws only what the reading says (`SavedWidgetReading10875`):
// its figures, verdicts, status and clock. The bar draws `reading.shares`,
// which exists only where figures are printed, so a result never gets a bar.
// The "As of" clock stays on every price.

/// Which look one widget draws. `today` is the text layout every message
/// (nothing saved, offline, removed…) keeps; a reading draws `matchup`.
nonisolated enum SavedWidgetLook12466: String, CaseIterable, Sendable {
    case today, matchup

    /// What every build draws over a reading.
    static let shipping: SavedWidgetLook12466 = .matchup
}

// MARK: - What every look reads

/// The reading plus the art, in the shape the looks draw.
struct SavedLookModel12466 {
    let reading: SavedWidgetReading10875
    let entry: SavedItemWidgetEntry10875

    var art: SavedWidgetArt12466? { entry.art }

    /// A two-sided game with its art.
    var isGame: Bool { art != nil && reading.rows.count == 2 }
    var away: SavedWidgetReading10875.Row { reading.rows[0] }
    var home: SavedWidgetReading10875.Row { reading.rows[1] }

    /// The looks draw a priced game, a finished game with its verdicts, and a
    /// priced or settled market. Anything else (no chance to show, no result
    /// recorded, a venue's own sentence) is said plainly in the look's colours.
    var drawsFull: Bool {
        switch reading.phase {
        case .current, .lastRecorded, .openingLine:
            return reading.shares != nil
        case .result:
            return isGame ? reading.rows.allSatisfy { $0.verdict != nil } : reading.headline != nil
        case .noResult, .unavailable:
            return false
        }
    }

    /// The price's own clock ("As of 3:42 PM", "Last recorded …", "Opening
    /// line"), or nil on a result.
    var clock: String? { SavedClock10875.caption(reading, entry: entry) }

    /// The bottom line: the clock where there is one, otherwise the status.
    var footer: String {
        if let clock { return clock }
        // #12466 (Fable, Nov 11): on a finished game the big numbers ARE the
        // score, so the footer says "Final" instead of "Final · 23–6" again.
        if isGame, reading.status.hasPrefix("Final"), reading.rows.allSatisfy({ $0.figure != nil }) {
            return "Final"
        }
        return reading.status
    }

    /// Whether the status needs its own line beside the clock. A result's
    /// status IS its footer.
    var statusLine: String? { clock == nil ? nil : reading.status }

    /// Which side the headline names: the chosen side, else the favourite,
    /// else home on a draw-priced sport.
    var headlineIsHome: Bool {
        guard isGame, let headline = reading.headline else { return true }
        return headline.label != away.label
    }

    /// The share of the bar that belongs to the headline's side.
    var headlineShare: Double? {
        switch reading.shares {
        case .game(let away?, let home)?:
            let total = away + home
            guard total > 0 else { return nil }
            return headlineIsHome ? home / total : away / total
        case .game(nil, let home)?:
            return headlineIsHome ? home : nil
        case .outcome(let chance)?:
            return chance
        case nil:
            return nil
        }
    }

    /// The bar's two colours on a surface, away first. A market's single fill
    /// is the app's emerald.
    func barColors(surfaceLuminance: Double) -> (away: Color, home: Color) {
        guard let art else { return (SavedLookInk12466.track, SavedLookInk12466.emerald) }
        let hexes = art.barHexes(surfaceLuminance: surfaceLuminance)
        return (Color(hex: hexes.away), Color(hex: hexes.home))
    }

    func logo(isHome: Bool) -> Data? { isHome ? entry.logos.home : entry.logos.away }
    func side(isHome: Bool) -> SavedWidgetArt12466.Side? { isHome ? art?.home : art?.away }
    func row(isHome: Bool) -> SavedWidgetReading10875.Row { isHome ? home : away }
}

enum SavedLookInk12466 {
    static let emerald = Color(hex: "#10B981")
    static let emeraldHex = "#10B981"
    static let track = Color.primary.opacity(0.12)
}

// MARK: - Pieces

/// A team's crest on a white disc. Without a crest, its short name on its own
/// colour: never a blank circle.
struct SavedLogoChip12466: View {
    let png: Data?
    let short: String
    let colorHex: String
    var size: CGFloat = 32
    @Environment(\.widgetRenderingMode) private var mode

    var body: some View {
        ZStack {
            if let image = SavedWidgetLogos12466.image(png) {
                Circle().fill(mode == .fullColor ? Color.white : Color.white.opacity(0.18))
                crest(image).padding(size * 0.15)
            } else {
                Circle().fill(mode == .fullColor ? Color(hex: colorHex) : Color.white.opacity(0.18))
                Text(short)
                    .font(.system(size: size * 0.32, weight: .heavy, design: .rounded))
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                    .foregroundStyle(mode == .fullColor ? Color(hex: SavedWidgetArt12466.ink(on: colorHex)) : Color.primary)
                    .padding(size * 0.12)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    @ViewBuilder private func crest(_ image: CGImage) -> some View {
        let crest = Image(decorative: image, scale: 1)
        if #available(iOS 18.0, macOS 15.0, *) {
            crest.resizable().interpolation(.high).widgetAccentedRenderingMode(.desaturated).scaledToFit()
        } else {
            crest.resizable().interpolation(.high).scaledToFit()
        }
    }
}

/// The chance bar. A game: away on the left, home on the right, in their
/// colours; on a draw-priced game the left part is the rest, in the track's
/// grey. A market: the outcome's chance filled from the left. Where the
/// system takes the colours away (tinted, clear, the Lock Screen), the side
/// the widget leads with is the bright one.
struct SavedChanceBar12466: View {
    let shares: SavedWidgetReading10875.Shares
    let awayColor: Color
    let homeColor: Color
    var height: CGFloat = 8
    var track: Color = SavedLookInk12466.track
    /// Whether the side the widget leads with is home (`headlineIsHome`).
    var leadsHome: Bool = true
    @Environment(\.widgetRenderingMode) private var mode

    var body: some View {
        GeometryReader { geo in
            let widths = SavedWidgetArt12466.barWidths(shares, total: geo.size.width)
            switch shares {
            case .game(let away, _):
                let plain = mode != .fullColor
                let homeBright = leadsHome || away == nil
                HStack(spacing: 2) {
                    Capsule()
                        .fill(away == nil ? track : (plain ? Color.primary.opacity(homeBright ? 0.4 : 1) : awayColor))
                        .frame(width: widths.first)
                        .widgetAccentable(plain && !homeBright)
                    Capsule()
                        .fill(plain ? Color.primary.opacity(homeBright ? 1 : 0.4) : homeColor)
                        .frame(width: widths.second)
                        .widgetAccentable(plain && homeBright)
                }
            case .outcome:
                ZStack(alignment: .leading) {
                    Capsule().fill(track)
                    Capsule()
                        .fill(mode == .fullColor ? homeColor : Color.primary)
                        .frame(width: widths.second)
                        .widgetAccentable()
                }
            }
        }
        .frame(height: height)
        .accessibilityHidden(true)
    }
}

/// One side's value: its figure (a chance, or a final score) with its verdict
/// beneath where the game is settled. A side with nothing printed shows "—".
struct SavedSideValue12466: View {
    let row: SavedWidgetReading10875.Row
    var size: CGFloat
    var alignment: HorizontalAlignment = .leading

    var body: some View {
        VStack(alignment: alignment, spacing: 0) {
            if let figure = row.figure {
                Text(figure)
                    .font(HeadlineStyleTable199.now(.widget, scaledSize: size))
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            } else if row.verdict == nil {
                Text("—")
                    .font(HeadlineStyleTable199.secondNumbers(.widget, scaledSize: size * 0.7))
                    .opacity(0.5)
                    .accessibilityLabel("No number")
            }
            if let verdict = row.verdict {
                // #12466 (Fable, Nov 11): "LOST" is quieter than "WON", not faint:
                // at 0.6 it disappeared on the Vikings' purple at small size.
                Text(verdict)
                    .font(HeadlineStyleTable199.headers(.widget, scaledSize: max(11, size * 0.4)))
                    .textCase(.uppercase)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .opacity(row.emphasized ? 1 : 0.85)
            }
        }
    }
}

/// What a look says when it has no full drawing for the reading: the subject,
/// what there is to say, and the status, in the look's ink.
struct SavedLookPlain12466: View {
    let model: SavedLookModel12466

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.reading.subject)
                .font(.footnote.weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 0)
            if let headline = model.reading.headline, let said = headline.verdict ?? headline.figure {
                Text(said)
                    .font(.system(size: 20, weight: .bold, design: .rounded))
                    .lineLimit(2)
                    .minimumScaleFactor(0.6)
            } else {
                Text(model.reading.phase == .noResult ? "No result recorded" : "No chance to show")
                    .font(.subheadline.weight(.semibold))
                    .opacity(0.8)
            }
            Text(model.footer)
                .font(.caption2)
                .opacity(0.75)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .padding(.trailing, model.entry.isRefreshable12305 ? 24 : 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

// MARK: - The look, chosen

/// The Home Screen drawing for a non-`today` look.
struct SavedLookView12466: View {
    let look: SavedWidgetLook12466
    let model: SavedLookModel12466
    let family: WidgetFamily

    var body: some View {
        switch look {
        case .matchup: SavedMatchupLook12466(model: model, family: family)
        case .today: EmptyView()
        }
    }

    /// The text colour the refresh button and plain text take on this look's
    /// background.
    static func ink(
        _ look: SavedWidgetLook12466,
        model: SavedLookModel12466?,
        colorScheme: ColorScheme = .light
    ) -> Color? {
        switch look {
        case .today: return nil
        case .matchup:
            if let model, model.isGame, model.drawsFull {
                return colorScheme == .dark ? Color(hex: "#9CA3AF") : Color(hex: "#6B7280")
            }
            return .white
        }
    }
}

/// Each look's container background.
struct SavedLookBackground12466: View {
    let look: SavedWidgetLook12466
    let model: SavedLookModel12466?
    @Environment(\.colorScheme) private var colorScheme

    static let darkCardHex = "#1C1C1E"

    var body: some View {
        switch look {
        case .today:
            Rectangle().fill(.fill.tertiary)
        case .matchup:
            if let model, model.isGame, model.drawsFull {
                colorScheme == .dark ? Color(hex: Self.darkCardHex) : Color.white
            } else if let model, let art = model.art {
                let fills = art.fillHexes()
                ZStack {
                    Color(hex: fills.away)
                    SavedSlant12466().fill(Color(hex: fills.home))
                    LinearGradient(colors: [.black.opacity(0), .black.opacity(0.38)],
                                   startPoint: .center, endPoint: .bottom)
                }
            } else {
                LinearGradient(colors: [SavedLookInk12466.emerald, Color(hex: SavedWidgetArt12466.shaded(SavedLookInk12466.emeraldHex, by: 0.45))],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
            }
        }
    }
}

/// The home side's part of the matchup fill: a slanted edge, so the two
/// colours meet on a diagonal.
struct SavedSlant12466: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX + rect.width * 0.58, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.42, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

// MARK: - A · Matchup (183-A compact headline size family for priced/settled games)

struct SavedMatchupLook12466: View {
    let model: SavedLookModel12466
    let family: WidgetFamily
    @Environment(\.widgetRenderingMode) private var mode
    @Environment(\.colorScheme) private var colorScheme

    private var surfaceLuminance: Double {
        colorScheme == .dark
            ? SavedWidgetArt12466.darkSurfaceLuminance
            : SavedWidgetArt12466.lightSurfaceLuminance
    }

    var body: some View {
        if !model.drawsFull {
            SavedLookPlain12466(model: model)
                .foregroundStyle(.white)
        } else if model.isGame, let art = model.art {
            let headlineModel = SavedGameHeadlineWidgetModel12616.build(
                reading: model.reading,
                art: art,
                clockFooter: model.footer,
                isOffline: model.entry.isOffline,
                clearsRefreshTrailing: model.entry.isRefreshable12305,
                surfaceLuminance: surfaceLuminance,
                now: model.entry.date
            )
            SavedGameHeadlineWidgetView12616(
                model: headlineModel,
                size: family == .systemMedium ? .medium : .small,
                awayLogo: model.logo(isHome: false),
                homeLogo: model.logo(isHome: true),
                fullColor: mode == .fullColor
            ) {
                bar
            }
        } else {
            SavedMarketLook12466(model: model, family: family, inkOnFill: true,
                                 barTrack: Color.black.opacity(0.25), barFill: .white)
                .foregroundStyle(.white)
        }
    }

    @ViewBuilder private var bar: some View {
        if let shares = model.reading.shares {
            let colors = model.barColors(surfaceLuminance: surfaceLuminance)
            let track = colorScheme == .dark ? Color.white.opacity(0.14) : Color(hex: "#E5E7EB")
            SavedChanceBar12466(shares: shares, awayColor: colors.away, homeColor: colors.home,
                                height: 5, track: track, leadsHome: model.headlineIsHome)
        }
    }
}

// MARK: - A market, in a look's colours

struct SavedMarketLook12466: View {
    let model: SavedLookModel12466
    let family: WidgetFamily
    let inkOnFill: Bool
    let barTrack: Color
    let barFill: Color

    var body: some View {
        // #13161: wrap market headline and leading outcome name cleanly without "…"
        // across both default and .xxxLarge Dynamic Type in systemSmall and systemMedium.
        ViewThatFits(in: .vertical) {
            marketCard(subjectSize: nil, outcomeSize: HeadlineStyleTable199.nameBaseSize(.widget),
                       valueSize: family == .systemMedium ? 32 : 28, barHeight: 7, footerSize: nil, spacing: 4)
            marketCard(subjectSize: family == .systemMedium ? 13 : 11.5, outcomeSize: 12,
                       valueSize: family == .systemMedium ? 28 : 24, barHeight: 6, footerSize: 10, spacing: 3)
            marketCard(subjectSize: 10.5, outcomeSize: 10.5,
                       valueSize: family == .systemMedium ? 24 : 20, barHeight: 5, footerSize: 9.5, spacing: 2)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private func marketCard(
        subjectSize: CGFloat?,
        outcomeSize: CGFloat,
        valueSize: CGFloat,
        barHeight: CGFloat,
        footerSize: CGFloat?,
        spacing: CGFloat
    ) -> some View {
        VStack(alignment: .leading, spacing: spacing) {
            subjectView(size: subjectSize)
            Spacer(minLength: 0)
            if let headline = model.reading.headline {
                // Beside the number where the outcome's name fits whole on one line,
                // otherwise wrapped whole above it: never "Choosin' Texas - Ella La…".
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .lastTextBaseline) {
                        outcomeName(headline.label, size: outcomeSize, singleLine: true)
                        Spacer(minLength: 4)
                        value(headline, size: valueSize)
                    }
                    VStack(alignment: .leading, spacing: 0) {
                        outcomeName(headline.label, size: outcomeSize, singleLine: false)
                        value(headline, size: valueSize)
                    }
                }
            }
            if let shares = model.reading.shares {
                SavedChanceBar12466(shares: shares, awayColor: barTrack, homeColor: barFill,
                                    height: barHeight, track: barTrack)
            }
            footerView(size: footerSize)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func subjectView(size: CGFloat?) -> some View {
        let base = Text(model.reading.subject)
            .lineLimit(nil)
            .fixedSize(horizontal: false, vertical: true)
        if let size {
            base.font(HeadlineStyleTable199.names(.widget, scaledSize: size))
        } else {
            base.font((family == .systemMedium ? Font.subheadline : .caption).weight(.semibold))
        }
    }

    @ViewBuilder private func footerView(size: CGFloat?) -> some View {
        let base = Text(model.footer)
            .opacity(inkOnFill ? 0.8 : 0.6)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .padding(.trailing, model.entry.isRefreshable12305 ? 24 : 0)
        if let size {
            base.font(HeadlineStyleTable199.quietText(.widget, scaledSize: size))
        } else {
            base.font(.caption2)
        }
    }
}

extension SavedMarketLook12466 {
    func outcomeName(_ name: String, size: CGFloat, singleLine: Bool) -> some View {
        Text(name)
            .font(HeadlineStyleTable199.names(.widget, scaledSize: size))
            .lineLimit(singleLine ? 1 : nil)
            .fixedSize(horizontal: singleLine, vertical: true)
            .opacity(0.85)
    }

    func value(_ headline: SavedWidgetReading10875.Row, size: CGFloat) -> some View {
        Text(headline.verdict ?? headline.figure ?? "—")
            .font(HeadlineStyleTable199.now(.widget, scaledSize: size))
            .lineLimit(1)
            .minimumScaleFactor(0.5)
            .fixedSize(horizontal: true, vertical: false)
    }
}

// MARK: - The Lock Screen, for every new look

#if os(iOS)
/// The rectangle: the matchup, a bar between the two chances, and the clock.
/// A result keeps today's fitted drawing (`SavedRectangular10875`).
/// Saved markets wrap both headline and leading outcome cleanly without "…" (#13160).
struct SavedLockRectangle12466: View {
    let model: SavedLookModel12466

    var body: some View {
        if model.isGame {
            gameBody
        } else {
            marketBody
        }
    }

    private var gameBody: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(model.reading.shortSubject)
                .font(.headline)
                .lineLimit(1)
                .widgetAccentable()
            if let shares = model.reading.shares {
                HStack(spacing: 5) {
                    if model.away.figure != nil {
                        Text(model.away.figure ?? "").font(.caption.weight(.semibold).monospacedDigit())
                    } else if let headline = model.reading.headline {
                        Text(headline.shortLabel)
                            .font(.caption.weight(.semibold))
                            .lineLimit(1)
                    }
                    SavedChanceBar12466(shares: shares, awayColor: .primary.opacity(0.35), homeColor: .primary,
                                        height: 6, track: .primary.opacity(0.25), leadsHome: model.headlineIsHome)
                    Text(model.home.figure ?? "—")
                        .font(.caption.weight(.semibold).monospacedDigit())
                }
            }
            Text(model.footer)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var marketBody: some View {
        ViewThatFits(in: .vertical) {
            marketLockTier(subjectSize: 11.5, outcomeSize: 10.5, figureSize: 11.5, footerSize: 9.5, spacing: 1.5)
            marketLockTier(subjectSize: 10, outcomeSize: 9.5, figureSize: 10.5, footerSize: 8.5, spacing: 1)
            marketLockTier(subjectSize: 9, outcomeSize: 8.5, figureSize: 9.5, footerSize: 8, spacing: 0.5)
            marketLockTier(subjectSize: 8, outcomeSize: 8, figureSize: 9, footerSize: 7.5, spacing: 0.5)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func marketLockTier(
        subjectSize: CGFloat,
        outcomeSize: CGFloat,
        figureSize: CGFloat,
        footerSize: CGFloat,
        spacing: CGFloat
    ) -> some View {
        VStack(alignment: .leading, spacing: spacing) {
            Text(model.reading.shortSubject)
                .font(HeadlineStyleTable199.names(.widget, scaledSize: subjectSize))
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
                .widgetAccentable()
            if let headline = model.reading.headline {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(headline.label)
                        .font(HeadlineStyleTable199.names(.widget, scaledSize: outcomeSize))
                        .foregroundStyle(.secondary)
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 2)
                    Text(headline.verdict ?? headline.figure ?? "—")
                        .font(HeadlineStyleTable199.secondNumbers(.widget, prominent: true, scaledSize: figureSize))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
            Text(model.footer)
                .font(HeadlineStyleTable199.quietText(.widget, scaledSize: footerSize))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The circle: the headline side's chance as a ring, its figure inside and
/// its short name beneath.
struct SavedLockCircle12466: View {
    let model: SavedLookModel12466

    var body: some View {
        if let share = model.headlineShare, let headline = model.reading.headline, let figure = headline.figure {
            Gauge(value: min(max(share, 0), 1)) {
                Text(model.isGame ? headline.shortLabel : "")
            } currentValueLabel: {
                Text(figure).monospacedDigit().minimumScaleFactor(0.5)
            }
            .gaugeStyle(.accessoryCircular)
            .widgetAccentable()
        } else {
            SavedCircular10875(reading: model.reading)
        }
    }
}

/// An empty circle says what to do, not a bare bookmark.
struct SavedLockCircleMessage12466: View {
    let content: SavedWidgetContent10875

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            Text(Self.words(content))
                .font(.system(size: 11, weight: .semibold))
                .multilineTextAlignment(.center)
                .lineLimit(3)
                .minimumScaleFactor(0.7)
                .padding(6)
        }
    }

    static func words(_ content: SavedWidgetContent10875) -> String {
        switch content {
        case .notConfigured: return "Edit to choose"
        case .openApp: return "Open Bain Luck"
        case .otherAccount: return "Other account"
        case .removed: return "No longer saved"
        case .gone: return "No longer listed"
        case .unreachable: return "Offline"
        case .detail: return ""
        }
    }
}
#endif
