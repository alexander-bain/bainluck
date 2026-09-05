import SwiftUI

/// A participant's name printed sideways in the left gutter of a chart.
///
/// WHY THIS TYPE EXISTS (#2903). Every gutter label in the app was written the
/// same way:
///
///     Text(name.uppercased())
///         .lineLimit(1)
///         .fixedSize()
///         .rotationEffect(.degrees(-90))
///
/// `rotationEffect` is a render-time transform. It turns the pixels and leaves
/// the LAYOUT box at the unrotated size — so an 85pt-wide `SABALENKA` kept an
/// 85 x 13pt layout box inside a 24pt gutter while drawing a 13 x 85pt column of
/// pixels centred on that box. `.fixedSize()` made it worse by insisting on the
/// full natural width, which is what defeats truncation.
///
/// Both of #2903's symptoms are that one mistake seen from two directions:
///
///   - **Sideways, into the heading.** The layout box overflowed the gutter by
///     ~30pt on each side. SwiftUI does not clip by default, so the label drew on
///     top of the `Win Probability` / `Score Differential` heading beside it and
///     covered its first letter.
///   - **Lengthways, off the ends.** The rendered column ran ~36pt past the top
///     and bottom of the box the `VStack` had reserved, where an ancestor's frame
///     clipped it. The bottom is where a `-90°` label *starts*, so `SABALENKA`
///     lost `SAB` and drew as `ALENKA`.
///
/// The fix is to make the layout box describe the pixels, in that order:
///
///   1. Bound the label to its vertical run BEFORE rotating. Pre-rotation width
///      is post-rotation height, so this is the run — and because the bound is a
///      real width on an unfixed `Text`, a name too long for it truncates with an
///      ellipsis instead of being silently clipped to a fragment. A reader can
///      see that a name was shortened.
///   2. State the post-rotation footprint AFTER rotating, so the gutter reserves
///      the space the label actually occupies and stops overdrawing its
///      neighbours.
///
/// `ChartGutterLabelShapeTests` guards the shape: `.fixedSize()` may never again
/// sit immediately above a `.rotationEffect(.degrees(-90))`.
struct ChartGutterLabel<Content: View>: View {
    /// How far the label may run along the chart's vertical edge.
    let run: CGFloat
    /// How wide the gutter is across.
    let width: CGFloat
    private let content: () -> Content

    init(
        run: CGFloat,
        width: CGFloat = chartTeamGutterWidth,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.run = run
        self.width = width
        self.content = content
    }

    var body: some View {
        content()
            // Pre-rotation width IS the post-rotation height: bound the run here
            // so an over-long name truncates rather than clips.
            .frame(width: run)
            .rotationEffect(.degrees(-90))
            // Post-rotation footprint, stated to the layout system so the gutter
            // reserves it instead of letting the pixels spill over the heading.
            .frame(width: width, height: run)
    }
}

/// Geometry shared by every chart gutter.
enum ChartGutter {
    /// The gap left between the two labels so a long home name and a long away
    /// name cannot meet in the middle of the axis.
    static let interLabelGap: CGFloat = 16

    /// The vertical run available to EACH of a gutter's two labels.
    ///
    /// A gutter holds a home label at the top and an away label at the bottom of
    /// the chart's height, minus the padding above and below, minus the gap that
    /// keeps them apart. Splitting what remains is what makes the run a number
    /// rather than a guess — and it is why the truncation in `ChartGutterLabel`
    /// is reachable at all: without a run there is nothing to truncate against.
    static func run(chartHeight: CGFloat, verticalPadding: CGFloat) -> CGFloat {
        let usable = chartHeight - (verticalPadding * 2) - interLabelGap
        return max(0, usable / 2)
    }
}
