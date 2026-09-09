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

/// The crest drawn beside a gutter label's abbreviation.
///
/// WHY THIS TYPE EXISTS (#4117). The Win Probability gutter drew each team's
/// crest beside its abbreviation and the Score Differential gutter ~200pt below
/// it — same page, same two teams, same sideways-label idiom — drew the
/// abbreviations bare. #3988 had fixed the crest inside `OddsChartView`, which
/// is precisely what made its neighbour the next private rung of the ladder
/// #2977 named. The page contradicted itself within one scroll.
///
/// So the crest moves out of the chart that happened to get it first, and lives
/// beside `ChartGutterLabel` where the next gutter will find it. Copying the
/// nine lines a third time is what guarantees a third occurrence.
struct ChartGutterCrest: View {
    /// The crest's square. It is laid out along the label's RUN — `ChartGutterLabel`
    /// applies `.frame(width: run)` before rotating — so this is a length along the
    /// chart's edge, not a width across the gutter, and 14 clears the narrower
    /// (22pt) of the two gutters as comfortably as the wider one.
    static let side: CGFloat = 14

    let url: URL

    /// Which url this side should try: `teamAvatarURL`'s answer and no rung of
    /// its own (#2977).
    ///
    /// `sportKey` is passed WHOLE. `isInternationalSport` matches on the full key
    /// (`soccer_fifa_world_cup`), so a truncated "soccer" would blind the flag
    /// rung; the ladder's own comment says so and this is the fourth caller to
    /// have to honour it.
    ///
    /// The nil name is handed straight through as `""` rather than short-circuited,
    /// and that is deliberate. Bailing early on a missing name would drop a crest
    /// we were HANDED — `servedURL` is the ladder's first rung and needs no name at
    /// all — which would have been a fresh regression dressed as a guard. Both
    /// derived rungs are dictionary lookups that miss on `""`, so delegation
    /// already gives the right answer and this function keeps no rung of its own.
    static func resolvedURL(servedURL: String?, teamName: String?, sportKey: String?) -> URL? {
        teamAvatarURL(servedURL: servedURL, teamName: teamName ?? "", sportKey: sportKey)
            .flatMap(URL.init(string:))
    }

    /// The crest itself, with the loading and failure states told apart.
    ///
    /// The old code passed `placeholder: { EmptyView() }` under a fixed 14pt
    /// frame, which is #2977's second defect: `placeholder` is the FAILURE state
    /// as well as the loading one, so a 404 reserved a 14pt gap forever and left
    /// a hole beside the abbreviation. Here the two are separated —
    ///
    ///   - loading  → hold the square so the label does not jump when it arrives
    ///   - failed   → collapse entirely; the abbreviation always renders and is
    ///                the real label, so a reserved gap next to it is just a hole
    var body: some View {
        AsyncImage(url: url) { phase in
            if let image = phase.image {
                image.resizable().scaledToFit().frame(width: Self.side, height: Self.side)
            } else if phase.error != nil {
                EmptyView()
            } else {
                Color.clear.frame(width: Self.side, height: Self.side)
            }
        }
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
