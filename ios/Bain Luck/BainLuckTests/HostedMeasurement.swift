import SwiftUI
import UIKit

/// native/081, #4207 — the one place a test hosts a real view in order to
/// measure it.
///
/// 🔴 THE DEFECT THIS EXISTS TO MAKE UNREACHABLE. `UIHostingController` inherits
/// the **process's** content size category, so a hosted measurement resolves
/// `Font.caption` against whatever Dynamic Type the *simulator* happens to be
/// set to. Ten sites across six files did that, and none of them said so, which
/// means their verdicts were a function of the machine and not of the code:
///
///     simulator content_size = large   →  1711 tests, 44 failures
///     simulator content_size = a11y5   →  1711 tests, 46 failures
///
/// The two extra were `ChampionshipRowLayoutTests` and `CalibrationCurveWidthTests`,
/// neither of them touched by the diff under test. #4207 was filed when native/079
/// hit the first one; native/081 hit both, on a simulator left at a11y5 after
/// photographing an accessibility frame for #4284 — which is the ordinary way this
/// happens, because shooting accessibility frames is a thing this lane does daily.
///
/// A red that depends on the last screenshot somebody took is worse than a flake:
/// it accuses an innocent diff, in a module the author never opened, and it clears
/// itself when they look again. Tonight it cost a clean-HEAD control run to rule out.
///
/// ✅ SO THE SIZE IS AN ARGUMENT, NOT AN AMBIENT. Every hosted measurement passes
/// through here and pins `dynamicTypeSize` explicitly. The default is `.large`
/// (the system default) so a test that says nothing measures the ordinary case;
/// a test that wants an accessibility size asks for one, and then its verdict is
/// still a function of the code.
///
/// Guarded by `frontend/__tests__/ios/hostedMeasurementsPinDynamicType.test.ts`:
/// CI compiles no Swift, so nothing else can stop an eleventh site from being
/// written the old way.
@MainActor
func hostForMeasurement<V: View>(
    _ view: V, at size: DynamicTypeSize = .large
) -> UIHostingController<some View> {
    UIHostingController(rootView: view.environment(\.dynamicTypeSize, size))
}

/// The same rule for the suite's OTHER camera.
///
/// `ImageRenderer` inherits the ambient content size category exactly as
/// `UIHostingController` does — 16 sites across 12 files, of which one
/// (`GameSegmentTeamBadgeWidthTests`) had always pinned it, and that one is the
/// proof the pattern was known and simply not applied everywhere.
///
/// None of the other fifteen was RED at a11y5 when this was written, so this half
/// is closing an exposure rather than fixing a failure: a render-smoke test that
/// grows one assertion about a measured pixel inherits the defect silently, and
/// the next lane to meet it will spend the same clean-HEAD control run ruling out
/// their own diff.
@MainActor
func rendererForMeasurement<V: View>(
    _ view: V, at size: DynamicTypeSize = .large
) -> ImageRenderer<some View> {
    ImageRenderer(content: view.environment(\.dynamicTypeSize, size))
}
