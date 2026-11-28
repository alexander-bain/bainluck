import SwiftUI
import WidgetKit
#if DEBUG && canImport(Bain_Luck) && !BAINLUCK_WIDGET_EXTENSION
@testable import Bain_Luck
#endif

// Direction 217 (Alex, Nov 16) + #13432 iPhone Lock Screen double-wide parity:
// Both crests, live/final score, and ONE big number in its team's colour (or
// Home / Draw / Away on 3-way soccer when all three prices are served),
// paired with the small context line naming whose number it is and the clock/age.

/// Ruling 222 (Alex: "Need this to be readable."): crests and names as large as
/// the slot allows, with the big number still the largest thing in the tile.
/// Every size is a share of the slot's height, so each Watch or Lock Screen size gets its own.
nonisolated struct WatchMatchupMetrics217: Equatable, Sendable {
    let crest: CGFloat
    let name: CGFloat
    let bigOwner: CGFloat
    let big: CGFloat
    let small: CGFloat
    let rowGap: CGFloat

    init(slotHeight h: CGFloat) {
        // Two crest rows fill the left column; the primary owner + number line
        // stays the boldest element in the tile without squeezing college short names.
        crest = (h * 0.385).rounded()
        name = (h * 0.27).rounded()
        bigOwner = (h * 0.30).rounded()
        big = (h * 0.48).rounded()
        small = (h * 0.165).rounded()
        rowGap = max(3, (h * 0.05).rounded())
    }
}

/// The Matchup look in the big rectangular slot (`accessoryRectangular`) shared by
/// Apple Watch and iPhone Lock Screen (#13432).
struct WatchMatchupComplication217: View {
    /// #13649 — at most 3% inner padding so wide crests span the white disc.
    static let crestPaddingFraction: CGFloat = 0.03

    let reading: WatchMatchupReading217
    @Environment(\.widgetRenderingMode) private var mode

    private var fullColor: Bool { mode == .fullColor }

    private var hasThreeDigitScore: Bool {
        (reading.away.score ?? 0) >= 100 || (reading.home.score ?? 0) >= 100
    }

    private var hasLongAbbreviation: Bool {
        !showsScores && max(reading.away.abbreviation.count, reading.home.abbreviation.count) >= 4
    }

    private var hasWinnerCheckmark: Bool {
        reading.stage == .after && (reading.away.isWinner || reading.home.isWinner)
    }

    var body: some View {
        GeometryReader { geo in
            let m = WatchMatchupMetrics217(slotHeight: geo.size.height)
            HStack(alignment: .center, spacing: 3) {
                Grid(alignment: .leading, horizontalSpacing: hasWinnerCheckmark ? 2.5 : 4, verticalSpacing: m.rowGap) {
                    sideRow(reading.away, m)
                    sideRow(reading.home, m)
                }
                .layoutPriority(1)
                rightColumn(m)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .center)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.accessibilityText)
        .accessibilityIdentifier("watch.complication.matchup.\(reading.stage.rawValue)")
    }

    @ViewBuilder
    private func rightColumn(_ m: WatchMatchupMetrics217) -> some View {
        VStack(alignment: .trailing, spacing: reading.threeWay == nil ? 0 : 2) {
            if let threeWay = reading.threeWay {
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    threeWayColumn(label: threeWay.homeLabel, value: threeWay.homeText, m: m)
                    threeWayColumn(label: "Draw", value: threeWay.drawText, m: m)
                    threeWayColumn(label: threeWay.awayLabel, value: threeWay.awayText, m: m)
                }
                .widgetAccentable()
            } else if reading.bigText == ExternalSurfaceProbabilityFormat.noProbabilityYetText
                || reading.bigText == ExternalSurfaceProbabilityFormat.missingProbabilityText {
                Text(reading.bigText)
                    .font(.system(size: max(10, (m.small * 1.15).rounded()), weight: .bold, design: .rounded))
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.trailing)
                    .lineLimit(2)
                    .minimumScaleFactor(0.75)
                    .allowsTightening(true)
                    .fixedSize(horizontal: false, vertical: true)
                    .widgetAccentable()
            } else {
                let ownerSize = reading.bigOwnerLabel.count >= 4 ? (m.bigOwner * 0.90).rounded() : m.bigOwner
                (Text(reading.bigOwnerLabel)
                    .font(.system(size: ownerSize, weight: .black, design: .rounded))
                 + Text(" ")
                    .font(.system(size: max(6, (ownerSize * 0.42).rounded()), weight: .black, design: .rounded))
                 + Text(reading.bigText)
                    .font(.system(size: m.big, weight: .black, design: .rounded).monospacedDigit()))
                .foregroundStyle(fullColor ? Self.color(reading.bigInkHex) : .primary)
                .lineLimit(1)
                .minimumScaleFactor(0.48)
                .allowsTightening(true)
                .widgetAccentable()
            }
            Text(reading.smallLine)
                .font(.system(size: m.small, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.55)
                .allowsTightening(true)
        }
    }

    private func threeWayColumn(label: String, value: String, m: WatchMatchupMetrics217) -> some View {
        VStack(alignment: .center, spacing: 0) {
            Text(label)
                .font(.system(size: max(8.5, (m.small * 0.88).rounded()), weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.65)
                .allowsTightening(true)
            Text(value)
                .font(.system(size: max(12, (m.name * 0.88).rounded()), weight: .heavy, design: .rounded).monospacedDigit())
                .foregroundStyle(.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .allowsTightening(true)
        }
    }

    /// Alex, Nov 17 (via Fable, 9:54 AM): after the final the tick comes BEFORE the
    /// winner's score ("✓ 35"), both scores end on one right edge, and the tick's
    /// width is kept on the loser's row too, so the two numbers line up.
    private var showsScores: Bool { reading.away.score != nil || reading.home.score != nil }

    private func sideRow(_ side: WatchMatchupReading217.Side, _ m: WatchMatchupMetrics217) -> some View {
        GridRow {
            crestDisc(side, size: m.crest)
            if hasWinnerCheckmark {
                Image(systemName: "checkmark")
                    .font(.system(size: m.name * 0.5, weight: .heavy))
                    .foregroundStyle(fullColor ? Color.green : .primary)
                    .opacity(side.isWinner ? 1 : 0)
                    .accessibilityHidden(true)
            }
            Text(side.score.map(String.init) ?? side.abbreviation)
                .font(.system(size: m.name * (hasThreeDigitScore ? 0.88 : (hasLongAbbreviation ? 0.85 : 1.0)),
                              weight: side.isWinner || reading.stage != .after ? .heavy : .semibold,
                              design: .rounded).monospacedDigit())
                .foregroundStyle(reading.stage == .after && !side.isWinner ? .secondary : .primary)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .gridColumnAlignment(showsScores ? .trailing : .leading)
        }
    }

    @ViewBuilder private func crestDisc(_ side: WatchMatchupReading217.Side, size: CGFloat) -> some View {
        ZStack {
            if let png = side.crestPNG, let cgImage = WatchMatchupCrests217.complicationCGImage(from: png) {
                Circle().fill(fullColor ? Color.white : Color.white.opacity(0.22))
                crestImage(cgImage)
                    .padding(size * Self.crestPaddingFraction)
                    .clipShape(Circle())
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

    @ViewBuilder private func crestImage(_ cgImage: CGImage) -> some View {
        let image = Image(decorative: cgImage, scale: 2.0)
        if #available(iOS 18.0, watchOS 11.0, macOS 15.0, *) {
            image.resizable().interpolation(.high).widgetAccentedRenderingMode(.desaturated).scaledToFit()
                .saturation(fullColor ? 1 : 0)
        } else {
            image.resizable().interpolation(.high).scaledToFit()
                .saturation(fullColor ? 1 : 0)
        }
    }

    static func color(_ hex: String) -> Color {
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count == 6, let value = UInt32(clean, radix: 16) else { return .gray }
        return Color(red: Double((value >> 16) & 0xFF) / 255,
                     green: Double((value >> 8) & 0xFF) / 255,
                     blue: Double(value & 0xFF) / 255)
    }
}
