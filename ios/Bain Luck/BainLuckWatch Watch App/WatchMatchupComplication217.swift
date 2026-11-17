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
//           (direction 209); 3 hours after the final the slot gives way to the
//           launcher until the app publishes the next game
//
// Fable, 5:16 AM Nov 17 (v2 accepted): the small line says whose number it is in words,
// because a tinted face has no colour and two teams can share one:
// "LAC · Sun 5:20 PM", "BAL · Q3 4:12", "DET pregame · Final".
//
// It never prints "Saved" or "Stale", and never anything older than the game
// it describes: a reading that can't be shown honestly falls back to the
// launcher, not to an old number.

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
