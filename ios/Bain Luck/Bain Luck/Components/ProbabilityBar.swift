import SwiftUI

/// Team-colored segmented probability bar.
struct ProbabilityBar: View {
    let awayProb: Double
    let homeProb: Double
    var awayColor: Color = .gray
    var homeColor: Color = .gray
    var height: CGFloat = 8

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
        }
        .frame(height: height)
    }
}
