import AppIntents
import SwiftUI

/// #12315 — one hint in My Stuff that Bain Luck answers Siri: Apple's own tip
/// for "Get Probability", which shows the shortcut's first phrase ("Get a
/// probability from Bain Luck"). It goes away for good once the reader closes
/// it or has run the shortcut, and never shows while tips are hidden for a
/// test run (`-contextual_tips_10876 hidden`).
///
/// iPhone and iPad only, like the contextual tips (#10876): no Mac placement
/// has been seen.
struct SiriProbabilityTip12315: View {
    @AppStorage(SiriProbabilityTipRule12315.dismissedKey) private var dismissed = false
    @AppStorage(SiriProbabilityTipRule12315.usedKey) private var used = false

    init() {
        // A `reset` launch clears the flags once per run, before they are read.
        _ = SiriProbabilityTipRule12315.launchOption
    }

    var body: some View {
        #if os(iOS)
        if SiriProbabilityTipRule12315.shows(dismissed: dismissed, used: used,
                                             option: SiriProbabilityTipRule12315.launchOption) {
            SiriTipView(intent: GetProbabilityIntent10873(),
                        isVisible: Binding(get: { true }, set: { if !$0 { dismissed = true } }))
                .padding(.horizontal)
                .padding(.bottom, 8)
                .accessibilityIdentifier("myStuffSiriTip12315")
        }
        #endif
    }
}

/// When the hint shows, as plain values.
nonisolated enum SiriProbabilityTipRule12315 {
    static let dismissedKey = "siri_tip_12315_dismissed"
    static let usedKey = "siri_tip_12315_used"

    static func shows(dismissed: Bool, used: Bool, option: ContextualTipLaunchOption10876) -> Bool {
        option != .hidden && !dismissed && !used
    }

    /// The tips launch option, read once per run.
    static let launchOption = apply(ContextualTipLaunchOption10876.read(), to: .standard)

    /// `reset` clears both flags, so a test starts as a reader who has never
    /// seen the hint.
    static func apply(_ option: ContextualTipLaunchOption10876,
                      to defaults: UserDefaults) -> ContextualTipLaunchOption10876 {
        if option == .reset {
            defaults.removeObject(forKey: dismissedKey)
            defaults.removeObject(forKey: usedKey)
        }
        return option
    }

    /// The reader has run "Get Probability", from Siri, Shortcuts or the hint.
    static func markUsed(_ defaults: UserDefaults = .standard) {
        defaults.set(true, forKey: usedKey)
    }
}
