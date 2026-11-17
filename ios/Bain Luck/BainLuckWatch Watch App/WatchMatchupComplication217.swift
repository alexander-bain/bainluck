import SwiftUI
import WidgetKit

// Direction 217 (Alex, Nov 16): "Why are we wasting half the screen with this
// watch complication? … Can we have big numbers, logos, etc. and make this fun
// and easy to consume?" The big rectangular slot takes the Matchup look Alex
// chose on Nov 12 (#12641): both crests, the score, and ONE big number in its
// team's colour.
//
//   before: crests + names, the favourite's chance, the kickoff
//   during: crests + score, the leader's chance Now, the clock
//   after:  crests + final score (winner ticked), the winner's pregame chance
//           (direction 209), then the slot moves on to the next pin
//
// It never prints "Saved" or "Stale", and never anything older than the game
// it describes: a reading that can't be shown honestly falls back to the
// launcher, not to an old number.

/// Everything the Matchup slot draws, already decided. Built from the selected
/// game by `WatchMatchupReading217.make` so the view holds no rules.
nonisolated struct WatchMatchupReading217: Equatable, Sendable {
    enum Stage: String, Equatable, Sendable { case before, during, after }

    struct Side: Equatable, Sendable {
        let abbreviation: String
        /// The team's colour as drawn on the black face, already readable (ruling 197:
        /// primary, else secondary, else the slot's neutral).
        let inkHex: String
        /// The crest, PNG bytes cached in the shared container; nil draws the
        /// abbreviation on the team's colour instead, never a blank disc.
        let crestPNG: Data?
        let score: Int?
        let isWinner: Bool
    }

    let stage: Stage
    let away: Side
    let home: Side
    /// "61%". The one big number.
    let bigText: String
    /// Whose number it is, so it takes that team's colour.
    let bigIsHome: Bool
    /// The one small line under it: "Sun 5:20 PM", "Now · Q3 4:12", "Final · pregame".
    let smallLine: String
    let accessibilityText: String

    var bigInkHex: String { bigIsHome ? home.inkHex : away.inkHex }

    /// The neutral a team colour falls back to when neither of its colours reads
    /// on black (ruling 197's grey fallback).
    static let neutralInkHex = "#9CA3AF"

    /// Ruling 221 on the black face (Fable, 5:17 PM Nov 16): the primary if it reads
    /// at 3:1; else the secondary if we have one and it reads; else the primary
    /// lightened just enough to read (same hue and saturation). Never grey unless
    /// the team has no usable colour at all. The same order as Builder C's
    /// `TeamTextContrast.usableOnDarkSurface` (#12839), kept here so the
    /// complication target needs no phone files.
    static func ink(primary: String?, secondary: String?) -> String {
        if let hex = primary, readable(hex) { return normalized(hex) }
        if let hex = secondary, readable(hex) { return normalized(hex) }
        if let hex = primary, let lighter = lightened(hex) { return lighter }
        return neutralInkHex
    }

    static func readable(_ hex: String) -> Bool {
        guard let l = relativeLuminance(hex) else { return false }
        return (l + 0.05) / 0.05 >= minimumRatio
    }

    private static func normalized(_ hex: String) -> String {
        "#" + hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")).lowercased()
    }

    /// The primary with its HSL lightness raised in 1% steps until the quantized
    /// hex reads at 3:1 on black.
    static func lightened(_ hex: String) -> String? {
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count == 6, let value = UInt32(clean, radix: 16) else { return nil }
        let r = Double((value >> 16) & 0xFF) / 255, g = Double((value >> 8) & 0xFF) / 255, b = Double(value & 0xFF) / 255
        let maxC = max(r, g, b), minC = min(r, g, b), l = (maxC + minC) / 2, d = maxC - minC
        var h = 0.0, sat = 0.0
        if d > 0 {
            sat = l > 0.5 ? d / (2 - maxC - minC) : d / (maxC + minC)
            if maxC == r { h = (g - b) / d + (g < b ? 6 : 0) } else if maxC == g { h = (b - r) / d + 2 } else { h = (r - g) / d + 4 }
            h /= 6
        }
        func hue(_ p: Double, _ q: Double, _ t0: Double) -> Double {
            var t = t0
            if t < 0 { t += 1 }
            if t > 1 { t -= 1 }
            if t < 1.0 / 6 { return p + (q - p) * 6 * t }
            if t < 1.0 / 2 { return q }
            if t < 2.0 / 3 { return p + (q - p) * (2.0 / 3 - t) * 6 }
            return p
        }
        var step = l
        while step <= 1.0 {
            let q = step < 0.5 ? step * (1 + sat) : step + sat - step * sat
            let p = 2 * step - q
            let rgb = sat == 0 ? (step, step, step) : (hue(p, q, h + 1.0 / 3), hue(p, q, h), hue(p, q, h - 1.0 / 3))
            let out = String(format: "#%02x%02x%02x", Int((rgb.0 * 255).rounded()), Int((rgb.1 * 255).rounded()), Int((rgb.2 * 255).rounded()))
            if readable(out) { return out }
            step += 0.01
        }
        return nil
    }

    /// WCAG's 3:1 floor for large text, the one `TeamTextContrast` uses on the phone.
    static let minimumRatio = 3.0

    /// WCAG relative luminance of "#RRGGBB"; nil for anything else. The same
    /// formula as `TeamTextContrast.relativeLuminance`, kept here so the
    /// complication target needs no phone files.
    static func relativeLuminance(_ hex: String?) -> Double? {
        guard let hex else { return nil }
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count == 6, let value = UInt32(clean, radix: 16) else { return nil }
        func channel(_ shift: UInt32) -> Double {
            let c = Double((value >> shift) & 0xFF) / 255
            return c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }
}

/// Ruling 222 (Alex: "Need this to be readable."): crests and names as large as
/// the slot allows, with the big number still the largest thing in the tile.
/// Every size is a share of the slot's height, so each watch size gets its own.
nonisolated struct WatchMatchupMetrics217: Equatable, Sendable {
    let crest: CGFloat
    let name: CGFloat
    let big: CGFloat
    let small: CGFloat
    let rowGap: CGFloat

    init(slotHeight h: CGFloat) {
        // Two crest rows fill the left column; the big number's cap height
        // (~0.72 of its point size) stays above the crest's diameter.
        crest = (h * 0.385).rounded()
        name = (h * 0.27).rounded()
        big = (h * 0.575).rounded()
        small = (h * 0.165).rounded()
        rowGap = max(3, (h * 0.05).rounded())
    }
}

/// The Matchup look in the big rectangular slot (`accessoryRectangular`).
struct WatchMatchupComplication217: View {
    let reading: WatchMatchupReading217
    @Environment(\.widgetRenderingMode) private var mode

    private var fullColor: Bool { mode == .fullColor }

    var body: some View {
        GeometryReader { geo in
            let m = WatchMatchupMetrics217(slotHeight: geo.size.height)
            HStack(alignment: .center, spacing: 4) {
                VStack(alignment: .leading, spacing: m.rowGap) {
                    sideRow(reading.away, m)
                    sideRow(reading.home, m)
                }
                .layoutPriority(1)
                Spacer(minLength: 2)
                VStack(alignment: .trailing, spacing: 0) {
                    Text(reading.bigText)
                        .font(.system(size: m.big, weight: .black, design: .rounded).monospacedDigit())
                        .foregroundStyle(fullColor ? Self.color(reading.bigInkHex) : .primary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .widgetAccentable()
                    Text(reading.smallLine)
                        .font(.system(size: m.small, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .center)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.accessibilityText)
        .accessibilityIdentifier("watch.complication.matchup.\(reading.stage.rawValue)")
    }

    private func sideRow(_ side: WatchMatchupReading217.Side, _ m: WatchMatchupMetrics217) -> some View {
        HStack(spacing: 4) {
            crestDisc(side, size: m.crest)
            Text(side.score.map(String.init) ?? side.abbreviation)
                .font(.system(size: m.name, weight: side.isWinner || reading.stage != .after ? .heavy : .semibold,
                              design: .rounded).monospacedDigit())
                .foregroundStyle(reading.stage == .after && !side.isWinner ? .secondary : .primary)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            if side.isWinner {
                Image(systemName: "checkmark")
                    .font(.system(size: m.name * 0.5, weight: .heavy))
                    .foregroundStyle(fullColor ? Color.green : .primary)
                    .accessibilityHidden(true)
            }
        }
    }

    @ViewBuilder private func crestDisc(_ side: WatchMatchupReading217.Side, size: CGFloat) -> some View {
        ZStack {
            if let png = side.crestPNG, let image = UIImage(data: png) {
                Circle().fill(fullColor ? Color.white : Color.white.opacity(0.22))
                Image(uiImage: image).resizable().interpolation(.high).scaledToFit()
                    .padding(size * 0.14)
                    .saturation(fullColor ? 1 : 0)
            } else {
                Circle().fill(fullColor ? Self.color(side.inkHex) : Color.white.opacity(0.22))
                Text(side.abbreviation)
                    .font(.system(size: size * 0.34, weight: .heavy, design: .rounded))
                    .foregroundStyle(fullColor ? Color.black : .primary)
                    .lineLimit(1).minimumScaleFactor(0.5).padding(size * 0.1)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    static func color(_ hex: String) -> Color {
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count == 6, let value = UInt32(clean, radix: 16) else { return .gray }
        return Color(red: Double((value >> 16) & 0xFF) / 255,
                     green: Double((value >> 8) & 0xFF) / 255,
                     blue: Double(value & 0xFF) / 255)
    }
}
