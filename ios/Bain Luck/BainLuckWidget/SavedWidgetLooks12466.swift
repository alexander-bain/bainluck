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
    var footer: String { clock ?? reading.status }

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
                    .font(.system(size: size, weight: .bold, design: .rounded).monospacedDigit())
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            } else if row.verdict == nil {
                Text("—")
                    .font(.system(size: size * 0.7, weight: .semibold, design: .rounded))
                    .opacity(0.5)
                    .accessibilityLabel("No number")
            }
            if let verdict = row.verdict {
                Text(verdict)
                    .font(.system(size: max(11, size * 0.4), weight: .heavy, design: .rounded))
                    .textCase(.uppercase)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .opacity(row.emphasized ? 1 : 0.6)
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
    static func ink(_ look: SavedWidgetLook12466, model: SavedLookModel12466?) -> Color? {
        switch look {
        case .today: return nil
        case .matchup: return .white
        }
    }
}

/// Each look's container background.
struct SavedLookBackground12466: View {
    let look: SavedWidgetLook12466
    let model: SavedLookModel12466?

    var body: some View {
        switch look {
        case .today:
            Rectangle().fill(.fill.tertiary)
        case .matchup:
            if let model, let art = model.art {
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

// MARK: - A · Matchup

struct SavedMatchupLook12466: View {
    let model: SavedLookModel12466
    let family: WidgetFamily

    private var fills: (away: String, home: String) {
        model.art?.fillHexes() ?? (SavedLookInk12466.emeraldHex, SavedLookInk12466.emeraldHex)
    }

    var body: some View {
        Group {
            if !model.drawsFull {
                SavedLookPlain12466(model: model)
            } else if model.isGame {
                family == .systemMedium ? AnyView(medium) : AnyView(small)
            } else {
                SavedMarketLook12466(model: model, family: family, inkOnFill: true,
                                     barTrack: Color.black.opacity(0.25), barFill: .white)
            }
        }
        .foregroundStyle(.white)
    }

    private func ink(_ isHome: Bool) -> Color {
        Color(hex: SavedWidgetArt12466.ink(on: isHome ? fills.home : fills.away))
    }

    private func chip(_ isHome: Bool, size: CGFloat) -> some View {
        SavedLogoChip12466(png: model.logo(isHome: isHome), short: model.side(isHome: isHome)?.short ?? "",
                           colorHex: isHome ? fills.home : fills.away, size: size)
    }

    @ViewBuilder private var bar: some View {
        if let shares = model.reading.shares {
            SavedChanceBar12466(shares: shares, awayColor: .white.opacity(model.headlineIsHome ? 0.55 : 1),
                                homeColor: .white.opacity(model.headlineIsHome ? 1 : 0.55),
                                height: 6, track: .black.opacity(0.25), leadsHome: model.headlineIsHome)
        }
    }

    private var small: some View {
        VStack(spacing: 0) {
            HStack {
                chip(false, size: 38)
                Spacer(minLength: 4)
                chip(true, size: 38)
            }
            Spacer(minLength: 2)
            HStack(alignment: .lastTextBaseline) {
                SavedSideValue12466(row: model.away, size: 27).foregroundStyle(ink(false))
                Spacer(minLength: 2)
                SavedSideValue12466(row: model.home, size: 27, alignment: .trailing).foregroundStyle(ink(true))
            }
            HStack {
                Text(model.away.shortLabel).foregroundStyle(ink(false).opacity(0.85))
                Spacer(minLength: 2)
                Text(model.home.shortLabel).foregroundStyle(ink(true).opacity(0.85))
            }
            .font(.caption2.weight(.heavy))
            bar.padding(.top, 5)
            Text(model.footer)
                .font(.caption2.weight(.medium))
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.trailing, model.entry.isRefreshable12305 ? 24 : 0)
                .padding(.top, 4)
        }
    }

    private var medium: some View {
        VStack(spacing: 6) {
            HStack(alignment: .center) {
                side(false)
                Spacer(minLength: 6)
                Text("vs")
                    .font(.caption.weight(.heavy))
                    .opacity(0.8)
                Spacer(minLength: 6)
                side(true)
            }
            bar
            HStack(spacing: 4) {
                if let status = model.statusLine {
                    Text(status).fontWeight(.semibold)
                    Text("·")
                }
                Text(model.footer)
                Spacer(minLength: 0)
            }
            .font(.caption2)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .padding(.trailing, model.entry.isRefreshable12305 ? 24 : 0)
        }
    }

    private func side(_ isHome: Bool) -> some View {
        let align: HorizontalAlignment = isHome ? .trailing : .leading
        return VStack(alignment: align, spacing: 3) {
            chip(isHome, size: 42)
            Text(model.row(isHome: isHome).label)
                .font(.footnote.weight(.bold))
                .lineLimit(1)
                .minimumScaleFactor(0.65)
            SavedSideValue12466(row: model.row(isHome: isHome), size: 32, alignment: align)
        }
        .foregroundStyle(ink(isHome))
        .frame(maxWidth: .infinity, alignment: isHome ? .trailing : .leading)
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
        VStack(alignment: .leading, spacing: 4) {
            Text(model.reading.subject)
                .font((family == .systemMedium ? Font.subheadline : .caption).weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 0)
            if let headline = model.reading.headline {
                // Beside the number where the outcome's name fits whole there,
                // otherwise on its own line above it: never "San Francis…".
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .lastTextBaseline) {
                        outcomeName(headline.label)
                        Spacer(minLength: 4)
                        value(headline)
                    }
                    VStack(alignment: .leading, spacing: 0) {
                        outcomeName(headline.label).minimumScaleFactor(0.7)
                        value(headline)
                    }
                }
            }
            if let shares = model.reading.shares {
                SavedChanceBar12466(shares: shares, awayColor: barTrack, homeColor: barFill, height: 7, track: barTrack)
            }
            Text(model.footer)
                .font(.caption2)
                .opacity(inkOnFill ? 0.8 : 0.6)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .padding(.trailing, model.entry.isRefreshable12305 ? 24 : 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

extension SavedMarketLook12466 {
    func outcomeName(_ name: String) -> some View {
        Text(name)
            .font(.footnote.weight(.semibold))
            .lineLimit(1)
            .opacity(0.85)
    }

    func value(_ headline: SavedWidgetReading10875.Row) -> some View {
        Text(headline.verdict ?? headline.figure ?? "—")
            .font(.system(size: family == .systemMedium ? 32 : 28, weight: .bold, design: .rounded).monospacedDigit())
            .lineLimit(1)
            .minimumScaleFactor(0.5)
    }
}

// MARK: - The Lock Screen, for every new look

#if os(iOS)
/// The rectangle: the matchup, a bar between the two chances, and the clock.
/// A result keeps today's fitted drawing (`SavedRectangular10875`).
struct SavedLockRectangle12466: View {
    let model: SavedLookModel12466

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(model.reading.shortSubject)
                .font(.headline)
                .lineLimit(1)
                .widgetAccentable()
            if let shares = model.reading.shares {
                HStack(spacing: 5) {
                    if model.isGame, model.away.figure != nil {
                        Text(model.away.figure ?? "").font(.caption.weight(.semibold).monospacedDigit())
                    } else if let headline = model.reading.headline {
                        Text(model.isGame ? headline.shortLabel : headline.label)
                            .font(.caption.weight(.semibold))
                            .lineLimit(1)
                    }
                    SavedChanceBar12466(shares: shares, awayColor: .primary.opacity(0.35), homeColor: .primary,
                                        height: 6, track: .primary.opacity(0.25), leadsHome: model.headlineIsHome)
                    Text((model.isGame ? model.home.figure : model.reading.headline?.figure) ?? "—")
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
