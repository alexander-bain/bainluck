import SwiftUI

/// Team-colored segmented probability bar.
struct ProbabilityBar: View {
    let awayProb: Double
    let homeProb: Double
    var awayColor: Color = .gray
    var homeColor: Color = .gray
    var height: CGFloat = 8
    var animated: Bool = false
    var glowing: Bool = false

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                Rectangle()
                    .fill(awayColor)
                    .frame(width: max(geo.size.width * awayProb, 2))
                Rectangle()
                    .fill(homeColor)
                    .frame(width: max(geo.size.width * homeProb, 2))
            }
            .clipShape(Capsule())
            .shadow(color: glowing ? homeColor.opacity(0.4) : .clear, radius: glowing ? 6 : 0)
        }
        .frame(height: height)
        .animation(animated ? .easeInOut(duration: 0.5) : nil, value: awayProb)
        .animation(animated ? .easeInOut(duration: 0.5) : nil, value: homeProb)
    }
}
