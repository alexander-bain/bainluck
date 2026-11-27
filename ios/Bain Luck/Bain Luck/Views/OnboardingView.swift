import SwiftUI

/// Entry point retained for `"Redo Onboarding"` and `"Edit Teams"` flows across Preferences
/// and My Stuff. Delegates directly to `FirstRunChecklistRootView364A` (`364: A`, `#11934`).
struct OnboardingView: View {
    var entryPoint: String = "settings"

    /// #13504 — retained chip minimum-width sizing helper tested by `ThreeWayLiveStreamGuard13509Tests`.
    static func selectedChipMinimumWidth(regularWidth: Bool) -> CGFloat {
        regularWidth ? 240 : 140
    }

    var body: some View {
        FirstRunChecklistRootView364A(arrivedHeadline: nil, entryPoint: entryPoint)
    }
}
