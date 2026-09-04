import SwiftUI

/// The marker a live page shows in place of a refresh countdown while the push
/// stream is delivering.
///
/// It replaces a ring rather than sitting beside one: the two make opposite
/// claims. A countdown says "a request is scheduled for N seconds from now",
/// and while `streamDelivering` is true the event view model has stood that
/// request down entirely (#2687), so there is nothing to count to. Showing both
/// would be the C43 defect wearing a green dot.
///
/// Deliberately not animated. A pulse on a page that already carries a LIVE
/// chip and a moving number is decoration, and a repeating animation is one
/// more thing to keep running while a match is on.
struct LivePushDot: View {
    var diameter: CGFloat = 22

    var body: some View {
        ZStack {
            Circle()
                .fill(Color(hex: "#10B981").opacity(0.14))
            Circle()
                .fill(Color(hex: "#10B981"))
                .frame(width: diameter * 0.32, height: diameter * 0.32)
        }
        .frame(width: diameter, height: diameter)
        .accessibilityLabel("Updating live")
    }
}
