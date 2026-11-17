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
    /// Above the big number: "LAC", "Now · BAL", "Pregame · DET".
    let bigLabel: String
    /// Under it: "Sun 5:20 PM", "Q3 4:12", "Final".
    let caption: String
    let accessibilityText: String

    var bigInkHex: String { bigIsHome ? home.inkHex : away.inkHex }

    /// The neutral a team colour falls back to when neither of its colours reads
    /// on black (ruling 197's grey fallback).
    static let neutralInkHex = "#9CA3AF"

    /// Ruling 197 on a black face: the primary if it reads at 3:1, else the
    /// secondary, else the neutral.
    static func ink(primary: String?, secondary: String?) -> String {
        for candidate in [primary, secondary] {
            if let hex = candidate, let l = relativeLuminance(hex), (l + 0.05) / 0.05 >= minimumRatio {
                return hex
            }
        }
        return neutralInkHex
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

/// The Matchup look in the big rectangular slot (`accessoryRectangular`).
struct WatchMatchupComplication217: View {
    let reading: WatchMatchupReading217
    @Environment(\.widgetRenderingMode) private var mode

    private var fullColor: Bool { mode == .fullColor }

    var body: some View {
        GeometryReader { geo in
            let crest = min(24, max(18, geo.size.height * 0.31))
            let big = min(38, max(28, geo.size.height * 0.45))
            HStack(alignment: .center, spacing: 6) {
                VStack(alignment: .leading, spacing: geo.size.height * 0.07) {
                    sideRow(reading.away, crest: crest)
                    sideRow(reading.home, crest: crest)
                }
                .layoutPriority(1)
                Spacer(minLength: 2)
                VStack(alignment: .trailing, spacing: 0) {
                    Text(reading.bigLabel)
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Text(reading.bigText)
                        .font(.system(size: big, weight: .black, design: .rounded).monospacedDigit())
                        .foregroundStyle(fullColor ? Self.color(reading.bigInkHex) : .primary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .widgetAccentable()
                    Text(reading.caption)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
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

    private func sideRow(_ side: WatchMatchupReading217.Side, crest: CGFloat) -> some View {
        HStack(spacing: 5) {
            crestDisc(side, size: crest)
            Text(side.score.map(String.init) ?? side.abbreviation)
                .font(.system(size: crest * 0.72, weight: side.isWinner || reading.stage != .after ? .heavy : .semibold,
                              design: .rounded).monospacedDigit())
                .foregroundStyle(reading.stage == .after && !side.isWinner ? .secondary : .primary)
                .lineLimit(1)
            if side.isWinner {
                Image(systemName: "checkmark")
                    .font(.system(size: crest * 0.42, weight: .heavy))
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
