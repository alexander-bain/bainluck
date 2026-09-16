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
            .rotationEffect(.degrees(ChartGutter.rotationDegrees))
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

    /// The turn that puts the crest back upright inside a rotated gutter.
    ///
    /// **WHY THIS EXISTS (#6612).** The crest is composed INSIDE
    /// `ChartGutterLabel`'s content, so it was turned `-90°` along with the
    /// abbreviation beside it and drew lying on its side. Photographed on the
    /// live Cardinals–Giants game (15313231, `Bottom 9th`, 2026-09-16): the
    /// Cardinals' interlocking `StL` and the Giants' interlocking `SF` are
    /// orientation-bearing wordmarks, so on their side they are not a small logo
    /// but an illegible tangle of strokes — directly beneath a perfectly upright
    /// `STL` / `SF`. Counter-rotating the photographed pixels by `+90°` resolves
    /// both into clean marks, which is what proves the cause.
    ///
    /// **THE ROTATION IS RIGHT FOR THE TEXT AND WRONG FOR THE IMAGE**, and that
    /// is the whole of it. An abbreviation has to run along the axis; a crest
    /// means the same thing whichever way the axis runs, and a mark on its side
    /// is not a smaller mark, it is a different one. So the label keeps its turn
    /// and the crest undoes it, rather than the gutter giving up its sideways
    /// labels.
    ///
    /// **DERIVED, NEVER A SECOND LITERAL.** Writing `+90` here would be #1832's
    /// shape — two copies of one fact, free to drift, the healthy copy hiding the
    /// broken one. Negating ``ChartGutter/rotationDegrees`` — the same constant
    /// the label's own `.rotationEffect` reads — means a gutter that ever turns a
    /// different way carries its crest with it.
    ///
    /// **GEOMETRY IS UNTOUCHED, because the crest is a square.** Rotating a
    /// `side × side` frame by a quarter turn leaves an identical layout box, so
    /// #2903's careful "state the post-rotation footprint" arithmetic in
    /// `ChartGutterLabel` sees exactly the same box it saw before. This is why
    /// the fix can live on the crest instead of restructuring the gutter.
    static var counterRotationDegrees: Double { -ChartGutter.rotationDegrees }

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
        // Undo the gutter's turn so the mark stands up (#6612). Outside the
        // phase switch on purpose: all three arms are square or empty, so one
        // site cannot leave an arm behind the way three sites could.
        .rotationEffect(.degrees(Self.counterRotationDegrees))
    }
}

/// Geometry shared by every chart gutter.
enum ChartGutter {
    /// The turn that stands a gutter label on its edge, in degrees.
    ///
    /// Named rather than written twice (#6612). `ChartGutterCrest` has to undo
    /// exactly this turn to stay upright, and a second `+90` literal over there
    /// is the #1832 shape: two copies of one fact, free to drift, with the
    /// healthy copy hiding the broken one. It lives on `ChartGutter` rather than
    /// on `ChartGutterLabel` because the label is generic over its content — a
    /// static read off it needs a witness type at every call site, which is a
    /// worse invitation to write the literal than the literal was.
    static let rotationDegrees: Double = -90

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
