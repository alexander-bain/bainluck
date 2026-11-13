import SwiftUI

/// Team-colored segmented probability bar, with an optional neutral third segment
/// for explicit three-way draw sports and an optional pregame notch (#12616).
struct ProbabilityBar: View {
    let awayProb: Double
    let homeProb: Double
    var drawProb: Double? = nil
    var awayColor: Color = .gray
    var homeColor: Color = .gray
    var drawColor: Color = Color.secondary.opacity(0.28)
    var height: CGFloat = 8
    var animated: Bool = false
    var glowing: Bool = false
    /// #12616 (161-B) — optional away-side pregame share in `(0, 1)` drawn as a
    /// crisp notch across the bar so the reader sees where the game started
    /// against where the bar sits now.
    var notchProb: Double? = nil

    nonisolated static func normalizedShares(
        awayProb: Double,
        homeProb: Double,
        drawProb: Double? = nil
    ) -> (away: Double, home: Double, draw: Double) {
        let a = max(0, awayProb.isFinite ? awayProb : 0)
        let h = max(0, homeProb.isFinite ? homeProb : 0)
        let d: Double = {
            guard let drawProb, drawProb.isFinite, drawProb > 0 else { return 0 }
            return drawProb
        }()
        let sum = a + h + d
        guard sum > 0 else { return (0.5, 0.5, 0) }
        return (a / sum, h / sum, d / sum)
    }

    var body: some View {
        let shares = Self.normalizedShares(awayProb: awayProb, homeProb: homeProb, drawProb: drawProb)
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                HStack(spacing: 0) {
                    Rectangle()
                        .fill(awayColor)
                        .frame(width: max(geo.size.width * shares.away, 2))
                    Rectangle()
                        .fill(homeColor)
                        .frame(width: max(geo.size.width * shares.home, 2))
                    if shares.draw > 0 {
                        Rectangle()
                            .fill(drawColor)
                            .frame(width: max(geo.size.width * shares.draw, 2))
                    }
                }
                .frame(width: geo.size.width, height: height)
                .clipShape(Capsule())
                .shadow(color: glowing ? homeColor.opacity(0.4) : .clear, radius: glowing ? 6 : 0)

                if let notch = notchProb, notch.isFinite, notch > 0, notch < 1, geo.size.width > 8 {
                    let clampedX = min(max(geo.size.width * notch, 3), geo.size.width - 3)
                    ZStack {
                        RoundedRectangle(cornerRadius: 1)
                            .fill(Color.white)
                            .frame(width: 4, height: height + 2)
                        RoundedRectangle(cornerRadius: 0.75)
                            .fill(Color.primary.opacity(0.72))
                            .frame(width: 1.5, height: height + 2)
                    }
                    .position(x: clampedX, y: height / 2)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
                }
            }
        }
        .frame(height: height)
        .animation(animated ? .easeInOut(duration: 0.5) : nil, value: awayProb)
        .animation(animated ? .easeInOut(duration: 0.5) : nil, value: homeProb)
    }
}
