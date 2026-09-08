import SwiftUI

/// #3865 — a scrolling page whose content sits in the MIDDLE of the viewport
/// when it is shorter than one, and scrolls normally when it is taller.
///
/// A bare `ScrollView { VStack { … } }` pins its content to the top and leaves
/// whatever is left over as white below it. That is invisible on a page that
/// fills the screen and glaring on one that does not: the Daily Challenge
/// question is 338pt of an 874pt phone and 310pt of a 1,210pt iPad, so 38% and
/// 65% of those two screens respectively were empty *below* the answer buttons
/// while nothing was above them.
///
/// The horizontal half is the idiom already in `PoliticsView`, `WeatherView`,
/// `EconomicsView` and `EntertainmentView` — cap the width, then re-expand to
/// centre it. The vertical half is the `minHeight` line, and the reason it is
/// `minHeight:` and not `height:` is the whole safety of this view: a fixed
/// height would clip content taller than the viewport (large Dynamic Type on a
/// small phone) into an unscrollable box. `minHeight` centres the short case
/// and gets out of the way of the tall one.
///
/// Guarded by ``CenteredPageContentTests``, which renders both cases.
struct CenteredPageContent<Content: View>: View {

    /// The widest the content may draw. Pass `.infinity` for no cap.
    let maxContentWidth: CGFloat

    @ViewBuilder var content: Content

    init(maxContentWidth: CGFloat = .infinity, @ViewBuilder content: () -> Content) {
        self.maxContentWidth = maxContentWidth
        self.content = content()
    }

    var body: some View {
        GeometryReader { geo in
            ScrollView {
                content
                    .frame(maxWidth: maxContentWidth)
                    .frame(
                        maxWidth: .infinity,
                        minHeight: geo.size.height,
                        alignment: .center
                    )
            }
        }
    }
}
