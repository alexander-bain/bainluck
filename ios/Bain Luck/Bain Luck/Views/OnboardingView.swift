import SwiftUI

/// Entry point retained for `"Redo Onboarding"` and `"Edit Teams"` flows across Preferences
/// and My Stuff. Delegates directly to `FirstRunFlowView212A` (`212-A`, `#11934`), retiring
/// the old 5-step sports questionnaire and narrow 140pt team chips (`#13517`).
struct OnboardingView: View {
    var body: some View {
        FirstRunFlowView212A(arrivedHeadline: nil)
    }
}
