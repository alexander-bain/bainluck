import SwiftUI

/// Renders the Bain Luck clover mark (`BainLuckMark`, original artwork supplied by Alex:
/// clover and its shadow on a clear background, decision 390: A) unaltered (#13633).
struct BainLuckMarkView: View {
    var size: CGFloat

    var body: some View {
        Image("BainLuckMark")
            .resizable()
            .interpolation(.high)
            .aspectRatio(1, contentMode: .fit)
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}
