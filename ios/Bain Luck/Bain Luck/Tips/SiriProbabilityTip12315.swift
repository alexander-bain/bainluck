import SwiftUI

/// #12315 / #13662 Item 11 — top-of-My-Stuff Siri tip matched to the
/// `Manage pins` card chrome (`Color.cardBackgroundDark`, `12pt` continuous
/// rounded rect, `1pt` hairline border), conversational phrase modeled from
/// `BainLuckShortcuts10873`, and a tap target that opens a short `Tips` sheet.
/// Goes away once dismissed or once either Siri probability shortcut runs, and
/// never renders while tips are hidden (`-contextual_tips_10876 hidden`).
///
/// iPhone and iPad only, like the contextual tips (#10876): no Mac placement
/// has been seen.
struct SiriProbabilityTip12315: View {
    static let hintAccessibilityID = "myStuffSiriTip12315"
    static let openTipsAccessibilityID = "myStuffSiriTipOpenSheet12315"
    static let headlineText = "Ask Siri about a team"
    static let examplePhraseText = "Say \"Ask Bain Luck if the Lakers will win\""

    var horizontalPadding: CGFloat? = nil
    @AppStorage(SiriProbabilityTipRule12315.dismissedKey) private var dismissed = false
    @AppStorage(SiriProbabilityTipRule12315.usedKey) private var used = false
    @State private var showingTipsSheet = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .subheadline) private var iconSlotWidth: CGFloat = 20

    init(horizontalPadding: CGFloat? = nil) {
        self.horizontalPadding = horizontalPadding
        // A `reset` launch clears the flags once per run, before they are read.
        _ = SiriProbabilityTipRule12315.launchOption
    }

    var body: some View {
        #if os(iOS)
        if SiriProbabilityTipRule12315.shows(dismissed: dismissed, used: used,
                                             option: SiriProbabilityTipRule12315.launchOption) {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    accessibilityCard
                } else {
                    standardCard
                }
            }
            .background(Color.cardBackgroundDark)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.primary.opacity(0.06), lineWidth: 1)
            )
            .padding(.horizontal, horizontalPadding ?? 16)
            .padding(.bottom, 4)
            .sheet(isPresented: $showingTipsSheet) {
                MyStuffSiriTipsSheet12315()
            }
        }
        #endif
    }

    #if os(iOS)
    private var standardCard: some View {
        HStack(spacing: 4) {
            HStack(spacing: 12) {
                waveformIcon
                VStack(alignment: .leading, spacing: 2) {
                    headlineLabel
                    examplePhraseLabel
                }
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
            }
            .padding(.leading, 16)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
            .onTapGesture {
                showingTipsSheet = true
            }

            openTipsButton
            dismissButton
                .padding(.trailing, 4)
        }
    }

    private var accessibilityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    waveformIcon
                    headlineLabel
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                dismissButton
            }
            examplePhraseLabel
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
            openTipsButton
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .onTapGesture {
            showingTipsSheet = true
        }
    }

    private var waveformIcon: some View {
        Image(systemName: "waveform")
            .font(.subheadline.weight(.medium))
            .foregroundStyle(Color.accentColor)
            .frame(width: iconSlotWidth)
            .accessibilityHidden(true)
    }

    private var headlineLabel: some View {
        Text(Self.headlineText)
            .font(.subheadline.weight(.medium))
            .foregroundStyle(.primary)
    }

    private var examplePhraseLabel: some View {
        Text(Self.examplePhraseText)
            .font(.caption)
            .foregroundStyle(.secondary)
            .accessibilityIdentifier(Self.hintAccessibilityID)
    }

    private var openTipsButton: some View {
        Button {
            showingTipsSheet = true
        } label: {
            HStack(spacing: 4) {
                Text("Tips")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 6)
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Open Tips")
        .accessibilityIdentifier(Self.openTipsAccessibilityID)
    }

    private var dismissButton: some View {
        Button {
            dismissed = true
        } label: {
            Image(systemName: "xmark")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Dismiss Siri tip")
        .accessibilityIdentifier(Self.hintAccessibilityID)
    }
    #endif
}

#if os(iOS)
/// Short Tips sheet opened from tapping the Siri card in My Stuff.
struct MyStuffSiriTipsSheet12315: View {
    @Environment(\.dismiss) private var dismiss

    static let siriPhrases: [String] = [
        "Ask Bain Luck if the Lakers will win",
        "Ask Bain Luck how the Celtics are doing",
        "Ask Bain Luck about the Bills game",
        "Ask Bain Luck who's going to win",
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    tipCard(
                        icon: "waveform",
                        title: "Ask Siri about games & teams",
                        detail: "Ask hands-free for win probability using natural phrases:"
                    ) {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(Self.siriPhrases, id: \.self) { phrase in
                                Text("\"\(phrase)\"")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(.primary)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(Color.primary.opacity(0.05))
                                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            }
                        }
                    }

                    tipCard(
                        icon: "bookmark.fill",
                        title: "Pin games and follow teams",
                        detail: "Tap the bookmark on any game or market to save it here, or follow a team to keep live and upcoming matchups at the top of My Stuff."
                    )

                    tipCard(
                        icon: "apps.iphone",
                        title: "Widgets on Home & Lock Screen",
                        detail: "Add a Bain Luck widget to keep a pinned game's win probability in view without opening the app."
                    )
                }
                .padding(16)
            }
            .navigationTitle("Tips")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                        .accessibilityIdentifier("myStuffSiriTipsSheetDone12315")
                }
            }
            .accessibilityIdentifier("myStuffSiriTipsSheet12315")
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func tipCard<Extra: View>(
        icon: String,
        title: String,
        detail: String,
        @ViewBuilder extra: () -> Extra = { EmptyView() }
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
                .accessibilityAddTraits(.isHeader)

            Text(detail)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            extra()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.cardBackgroundDark)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.primary.opacity(0.06), lineWidth: 1)
        )
    }
}
#endif

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
