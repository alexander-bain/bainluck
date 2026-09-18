import Combine
import SwiftUI

// MARK: - Affinity row layout metrics

/// The geometry of one Settings → Your Interests row, named in one place so the
/// guard test measures the row the view actually draws (#6681).
///
/// These were literals scattered through `affinityCard`, which is why nothing
/// could tell that the name label had only ~100pt to live in on the device the
/// defect was filed from. A test that re-declared them would drift from the
/// view on the first padding change and then pass forever; sharing them is what
/// makes `SettingsInterestTileNamesAreReadable6681Tests` a real check.
///
/// Not a full model of SwiftUI layout — the row is
/// `[emoji | name] Spacer() [four capsules]` inside two levels of horizontal
/// padding, and only the name is compressible. Validated against a photograph:
/// at 402pt these numbers predict exactly the three names that truncate on the
/// device, and no others.
enum AffinityRowMetrics {
    /// `VStack(spacing: 6) { … }.padding(.horizontal)` around the rows.
    /// SwiftUI's default horizontal padding is 16pt on iPhone.
    static let gridHorizontalPadding: CGFloat = 16
    /// The card's own inset, inside the grid padding.
    static let cardHorizontalPadding: CGFloat = 14
    /// `HStack(spacing:)` holding [name group, Spacer, capsules] — two gaps.
    static let rowSpacing: CGFloat = 10
    static let emojiWidth: CGFloat = 28
    static let emojiNameSpacing: CGFloat = 8
    /// Gaps between the four capsules — three of them.
    static let capsuleSpacing: CGFloat = 5
    /// Applied to each side of every capsule label.
    static let capsuleHorizontalPadding: CGFloat = 10
    static let capsuleFontSize: CGFloat = 11

    /// How far the tile name may shrink before it truncates instead.
    ///
    /// 0.65 and not the 0.85 first proposed on #6681. Measured against the real
    /// font at the three widths that matter, the scale each name NEEDS is:
    ///
    ///   | name               | 375pt | 393pt | 402pt |
    ///   |--------------------|-------|-------|-------|
    ///   | College Football   | 0.632 | 0.788 | 0.866 |
    ///   | College Basketball | 0.553 | 0.689 | 0.757 |
    ///   | Entertainment      | 0.718 | 0.894 | 0.983 |
    ///
    /// A floor of 0.85 clears College Football and Entertainment but leaves
    /// College Basketball truncated on every phone — the longest name, and the
    /// one whose neighbour two rows up shares its first eight characters. 0.65
    /// clears all three at 393pt and above with margin. 375pt (SE 3rd gen,
    /// 13 mini) keeps a named residual; see the guard test.
    static let nameMinimumScaleFactor: CGFloat = 0.65

    /// Width left for the name on a screen `width` points across, with the
    /// capsule block measured by the caller (it depends on the font).
    static func nameBudget(screenWidth: CGFloat, capsuleBlockWidth: CGFloat) -> CGFloat {
        screenWidth
            - 2 * gridHorizontalPadding
            - 2 * cardHorizontalPadding
            - emojiWidth
            - emojiNameSpacing
            - 2 * rowSpacing
            - capsuleBlockWidth
    }
}

// MARK: - Affinity button colors

private let affinityColor: [AffinityLevel: Color] = [
    .loveIt: Color(red: 0.16, green: 0.65, blue: 0.32),    // green
    .bigMoments: Color(red: 0.20, green: 0.45, blue: 0.90), // blue
    .ifWild: Color(red: 0.92, green: 0.55, blue: 0.15),     // orange
    .nah: Color(red: 0.55, green: 0.55, blue: 0.58),        // gray
]

// MARK: - Relation type display

private let relationEmoji: [String: String] = [
    "follow": "\u{2764}\u{FE0F}",      // heart
    "local": "\u{1F3E0}",              // house
    "alma_mater": "\u{1F393}",         // grad cap
    "rival": "\u{1F525}",              // fire
]

private let relationLabel: [String: String] = [
    "follow": "Following",
    "local": "Local",
    "alma_mater": "Alma Maters",
    "rival": "Rivals",
]

struct PreferencesView: View {
    @EnvironmentObject private var authManager: AuthManager
    @StateObject private var viewModel = PreferencesViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var showOnboarding = false
    @State private var showDeleteConfirmation = false
    @State private var isDeletingAccount = false
    /// Set when deletion SUCCEEDS. The reader is told in words that the
    /// account is gone before this screen goes away — a silent dismiss is
    /// indistinguishable from a tap that did nothing, and App Review has to be
    /// able to see the flow complete (#678).
    @State private var showDeletionComplete = false
    /// Set when deletion FAILS. Nil means no failure to report. This used to
    /// be swallowed: the catch reset the spinner and said nothing, so a
    /// server-side failure looked exactly like a successful no-op.
    @State private var deletionErrorMessage: String?
    /// Mirrors `TelemetryConsent` so the toggle re-renders on change. The
    /// authority remains the source of truth — this is a view cache, seeded in
    /// `onAppear`, never the thing that decides.
    @State private var analyticsConsentGranted = TelemetryConsent.shared.isGranted
    @State private var telemetryPersistence = TelemetryConsent.shared.persistence

    var body: some View {
        Group {
            if viewModel.loading {
                ProgressView("Loading preferences...")
            } else if let error = viewModel.error, viewModel.prefs == nil {
                ContentUnavailableView(
                    "Couldn't Load Preferences",
                    systemImage: "wifi.exclamationmark",
                    description: Text(error)
                )
            } else {
                preferencesContent
            }
        }
        .navigationTitle("Preferences")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            await viewModel.load()
            AnalyticsService.trackScreen(name: "preferences", type: "preferences")
        }
        #if os(iOS)
        .fullScreenCover(isPresented: $showOnboarding) {
            OnboardingView()
                .environmentObject(authManager)
        }
        #else
        .sheet(isPresented: $showOnboarding) {
            OnboardingView()
                .environmentObject(authManager)
                .frame(minWidth: 500, minHeight: 400)
        }
        #endif
        .onChange(of: showOnboarding) { _, isShowing in
            if !isShowing {
                Task { await viewModel.load() }
                Task { await authManager.refreshProfile() }
            }
        }
        // Both alerts hang off the whole screen, not off the Delete Account
        // button: deleting flips `isAuthenticated`, which removes that button
        // from the hierarchy, and an alert attached to it would go with it.
        .alert("Account Deleted", isPresented: $showDeletionComplete) {
            Button("OK") { dismiss() }
        } message: {
            Text("Your account and all associated data have been permanently deleted.")
        }
        .alert(
            "Couldn't Delete Account",
            isPresented: Binding(
                get: { deletionErrorMessage != nil },
                set: { if !$0 { deletionErrorMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) { deletionErrorMessage = nil }
        } message: {
            Text(deletionErrorMessage ?? "")
        }
    }

    // MARK: - Main Content

    private var preferencesContent: some View {
        ScrollView {
            VStack(spacing: 24) {
                accountHero
                teamsSection
                interestsSection
                notificationsSection
                privacySection
                actionsSection
            }
            .padding(.vertical)
        }
        .background(Color.groupedBackground)
        .onAppear {
            // Re-read the authority: it can have changed since this view was
            // constructed (the first-run prompt, or a previous visit).
            analyticsConsentGranted = TelemetryConsent.shared.isGranted
            telemetryPersistence = TelemetryConsent.shared.persistence
        }
    }

    // MARK: - Account Hero

    private var accountHero: some View {
        VStack(spacing: 16) {
            // Avatar
            if let photoUrl = authManager.user?.photoUrl, let url = URL(string: photoUrl) {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    accountInitialCircle(size: 72)
                }
                .frame(width: 72, height: 72)
                .clipShape(Circle())
                .overlay(
                    Circle()
                        .stroke(Color.white, lineWidth: 3)
                )
                .shadow(color: .black.opacity(0.12), radius: 8, x: 0, y: 4)
            } else {
                accountInitialCircle(size: 72)
                    .overlay(
                        Circle()
                            .stroke(Color.white, lineWidth: 3)
                    )
                    .shadow(color: .black.opacity(0.12), radius: 8, x: 0, y: 4)
            }

            // Name & email
            VStack(spacing: 4) {
                if let name = authManager.user?.displayName {
                    Text(name)
                        .font(.title3)
                        .fontWeight(.bold)
                }
                if let email = authManager.user?.email {
                    Text(email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Stats row
            HStack(spacing: 20) {
                statBadge(
                    icon: "heart.fill",
                    value: "\(viewModel.followTeams.count + viewModel.localTeams.count + viewModel.almaMaterTeams.count + viewModel.rivalTeams.count)",
                    label: "Teams"
                )
                statBadge(
                    icon: "sparkles",
                    value: "\(viewModel.sportAffinities.filter { $0.value > 0 }.count)",
                    label: "Interests"
                )
                if viewModel.prefs?.homeLocation != nil {
                    statBadge(
                        icon: "location.fill",
                        value: viewModel.prefs?.homeLocation ?? "",
                        label: "Location"
                    )
                }
            }
        }
        .padding(.vertical, 20)
        .padding(.horizontal, 16)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(
                colors: [
                    Color.accentColor.opacity(0.08),
                    Color.accentColor.opacity(0.03),
                    Color.clear
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .stroke(Color.accentColor.opacity(0.12), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.04), radius: 8, x: 0, y: 4)
        .padding(.horizontal)
    }

    private func statBadge(icon: String, value: String, label: String) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color.accentColor)
                Text(value)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .monospacedDigit()
            }
            Text(label)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.tertiary)
        }
    }

    private func accountInitialCircle(size: CGFloat) -> some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color.accentColor.opacity(0.3), Color.accentColor.opacity(0.15)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Text(String((authManager.user?.displayName ?? authManager.user?.email ?? "?").prefix(1)).uppercased())
                .font(.system(size: size * 0.4, weight: .bold))
                .foregroundStyle(Color.accentColor)
        }
        .frame(width: size, height: size)
    }

    // MARK: - Teams Section

    @ViewBuilder
    private var teamsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(
                emoji: "\u{1F3C6}", // trophy
                title: "Your Teams",
                count: viewModel.followTeams.count + viewModel.localTeams.count + viewModel.almaMaterTeams.count + viewModel.rivalTeams.count
            )

            if !viewModel.hasAnyTeams {
                emptyTeamsCard
            } else {
                VStack(spacing: 10) {
                    teamGroupCard(type: "follow", items: viewModel.followTeams)
                    teamGroupCard(type: "local", items: viewModel.localTeams)
                    teamGroupCard(type: "alma_mater", items: viewModel.almaMaterTeams)
                    teamGroupCard(type: "rival", items: viewModel.rivalTeams)
                }
                .padding(.horizontal)

                editTeamsButton
            }
        }
    }

    private var emptyTeamsCard: some View {
        VStack(spacing: 12) {
            Image(systemName: "sportscourt")
                .font(.system(size: 32))
                .foregroundStyle(.tertiary)
            Text("No teams yet")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button {
                showOnboarding = true
            } label: {
                Text("Set up your teams")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(Color.accentColor, in: Capsule())
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack.opacity(0.5), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 3)
        .padding(.horizontal)
    }

    @ViewBuilder
    private func teamGroupCard(type: String, items: [FavoriteItem]) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                // Group header
                HStack(spacing: 6) {
                    Text(relationEmoji[type] ?? "")
                        .font(.caption)
                    Text(relationLabel[type] ?? type.capitalized)
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                }
                .padding(.leading, 4)

                ForEach(items) { item in
                    teamCard(item)
                }
            }
        }
    }

    private func teamCard(_ item: FavoriteItem) -> some View {
        HStack(spacing: 12) {
            TeamLogoView(
                url: item.logoUrl,
                teamName: item.teamName,
                color: .accentColor,
                size: 36
            )

            VStack(alignment: .leading, spacing: 2) {
                Text(item.teamName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)

                if let sport = item.sportKey {
                    Text(sportDisplayName(for: sport))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer()

            Button(role: .destructive) {
                withAnimation(.easeInOut(duration: 0.25)) {
                    viewModel.removeFavorite(teamId: item.teamId, relationType: item.relationType)
                }
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary.opacity(0.5))
                    .font(.system(size: 18))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.4), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
    }

    private var editTeamsButton: some View {
        Button {
            showOnboarding = true
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "pencil.circle.fill")
                    .font(.system(size: 16))
                Text("Edit Teams")
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }
            .foregroundStyle(Color.accentColor)
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(Color.accentColor.opacity(0.08), in: Capsule())
            .overlay(Capsule().stroke(Color.accentColor.opacity(0.15), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
        .padding(.top, 4)
    }

    // MARK: - Interests Section

    private var interestsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(
                emoji: "\u{2728}", // sparkles
                title: "Your Interests",
                count: viewModel.sportAffinities.filter { $0.value > 0 }.count
            )

            // Legend
            HStack(spacing: 8) {
                ForEach(AffinityLevel.allCases, id: \.rawValue) { level in
                    legendChip(level)
                }
                Spacer()
            }
            .padding(.horizontal)

            // Sports
            VStack(spacing: 6) {
                ForEach(OnboardingSportsData.sports) { item in
                    affinityCard(item: item)
                }
            }
            .padding(.horizontal)

            // Beyond Sports sub-header
            HStack(spacing: 6) {
                Text("\u{1F30D}")
                    .font(.subheadline)
                Text("Beyond Sports")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
            }
            .padding(.horizontal)
            .padding(.top, 8)

            VStack(spacing: 6) {
                ForEach(OnboardingSportsData.beyondSports) { item in
                    affinityCard(item: item)
                }
            }
            .padding(.horizontal)
        }
    }

    private func legendChip(_ level: AffinityLevel) -> some View {
        let color = affinityColor[level] ?? .gray
        return HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(level.shortLabel)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
        }
    }

    private func affinityCard(item: SportItem) -> some View {
        let currentLevel = viewModel.affinityLevel(for: item.key)
        let isActive = currentLevel != .nah
        let activeColor = affinityColor[currentLevel] ?? .gray

        return HStack(spacing: AffinityRowMetrics.rowSpacing) {
            // Emoji + name
            HStack(spacing: AffinityRowMetrics.emojiNameSpacing) {
                Text(item.emoji)
                    .font(.title3)
                    .frame(width: AffinityRowMetrics.emojiWidth)

                // #6681 — the four capsules are `.fixedSize()` and the Spacer
                // absorbs nothing, so the name is the only thing in this row
                // that can give, and three of the 22 gave: "College Foo…",
                // "College Basketball", "Entertainm…". The name is also the
                // ONLY thing telling one row from the next — every row's
                // capsules read Love/Big/Wild/Nah — so a truncated name is a
                // row a reader cannot identify.
                //
                // A floor, not a size: `minimumScaleFactor` shrinks only the
                // labels that would otherwise truncate, so 19 of 22 are
                // untouched. Wrapping to two lines was the alternative and was
                // weighed — it keeps full size but makes 3 of 22 rows taller,
                // and the ragged rhythm costs more scanning than a slightly
                // smaller label on three rows.
                Text(item.name)
                    .font(.subheadline)
                    .fontWeight(isActive ? .semibold : .regular)
                    .foregroundStyle(isActive ? .primary : .secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(AffinityRowMetrics.nameMinimumScaleFactor)
            }

            Spacer()

            // Affinity capsules
            HStack(spacing: AffinityRowMetrics.capsuleSpacing) {
                ForEach(AffinityLevel.allCases, id: \.rawValue) { level in
                    let selected = currentLevel == level
                    let color = affinityColor[level] ?? .gray

                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            viewModel.setAffinity(item.key, level: level)
                        }
                    } label: {
                        Text(level.shortLabel)
                            .font(.system(
                                size: AffinityRowMetrics.capsuleFontSize,
                                weight: selected ? .bold : .medium
                            ))
                            .lineLimit(1)
                            .fixedSize()
                            .padding(.horizontal, AffinityRowMetrics.capsuleHorizontalPadding)
                            .padding(.vertical, 6)
                            .foregroundStyle(selected ? .white : color.opacity(0.7))
                            .background(
                                selected
                                    ? AnyShapeStyle(color)
                                    : AnyShapeStyle(color.opacity(0.08))
                            )
                            .clipShape(Capsule())
                            .overlay(
                                Capsule()
                                    .stroke(
                                        selected ? color.opacity(0.3) : color.opacity(0.12),
                                        lineWidth: selected ? 1.5 : 0.5
                                    )
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, AffinityRowMetrics.cardHorizontalPadding)
        .padding(.vertical, 10)
        .background(
            isActive
                ? AnyShapeStyle(activeColor.opacity(0.04))
                : AnyShapeStyle(Color.cardBackground)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(
                    isActive ? activeColor.opacity(0.15) : Color.barTrack.opacity(0.4),
                    lineWidth: 0.5
                )
        )
        .shadow(color: .black.opacity(isActive ? 0.04 : 0.02), radius: 4, x: 0, y: 2)
    }

    // MARK: - Actions Section

    private var actionsSection: some View {
        VStack(spacing: 10) {
            Button {
                showOnboarding = true
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "arrow.counterclockwise.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Redo Onboarding")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundStyle(.primary)
                        Text("Start fresh with team selection and interests")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.4), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
            }
            .buttonStyle(.plain)

            NavigationLink {
                AboutView()
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "info.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("About Bain Luck")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundStyle(.primary)
                        Text("What Bain Luck is, and the story behind the numbers")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.4), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
            }
            .buttonStyle(.plain)

            if authManager.isAdmin {
                NavigationLink {
                    DiscoverLabelingView()
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "tag.circle.fill")
                            .font(.system(size: 20))
                            .foregroundStyle(Color.accentColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Discover Labeling")
                                .font(.subheadline)
                                .fontWeight(.medium)
                                .foregroundStyle(.primary)
                            Text("Admin-gated review of Discover debug cards")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 14)
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.accentColor.opacity(0.12), lineWidth: 0.5))
                    .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
                }
                .buttonStyle(.plain)
            }

            #if DEBUG
            Button {
                fatalError("Crashlytics test crash")
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "ant.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(.orange)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Test Crash")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundStyle(.primary)
                        Text("Trigger a test crash for Crashlytics")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.orange.opacity(0.12), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
            }
            .buttonStyle(.plain)
            #endif

            accountActions
        }
        .padding(.horizontal)
    }

    // MARK: - Account Actions

    /// Sign Out and Delete Account. Both act on a session, so both are hidden
    /// when there is no session — a signed-out reader was previously offered a
    /// Delete Account button whose request could only ever come back 401.
    @ViewBuilder
    private var accountActions: some View {
        if authManager.isAuthenticated {
            Button {
                authManager.signOut()
                dismiss()
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "rectangle.portrait.and.arrow.right")
                        .font(.system(size: 20))
                        .foregroundStyle(.red.opacity(0.7))
                    Text("Sign Out")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.red)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.red.opacity(0.12), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
            }
            .buttonStyle(.plain)

            Button {
                showDeleteConfirmation = true
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "trash")
                        .font(.system(size: 20))
                        .foregroundStyle(.red.opacity(0.7))
                    Text("Delete Account")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.red)
                    Spacer()
                    if isDeletingAccount {
                        ProgressView()
                            .tint(.red)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.red.opacity(0.12), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
            }
            .buttonStyle(.plain)
            .disabled(isDeletingAccount)
            .confirmationDialog(
                "Delete Account",
                isPresented: $showDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete Account", role: .destructive) {
                    isDeletingAccount = true
                    deletionErrorMessage = nil
                    Task {
                        do {
                            try await authManager.deleteAccount()
                            isDeletingAccount = false
                            showDeletionComplete = true
                        } catch {
                            isDeletingAccount = false
                            deletionErrorMessage = Self.deletionFailureMessage(for: error)
                        }
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This will permanently delete your account and all your data including predictions, favorites, and preferences. This action cannot be undone.")
            }
        }
    }

    /// Turns a deletion failure into one sentence a reader can act on. Kept
    /// deliberately short and jargon-free (D102): what happened, what to do.
    static func deletionFailureMessage(for error: Error) -> String {
        if let apiError = error as? APIError {
            switch apiError {
            case .httpError(let statusCode, _) where statusCode == 401 || statusCode == 403:
                return "Your session has expired. Sign out, sign back in, and try again."
            case .networkError:
                return "No connection. Check your network and try again."
            case .httpError(let statusCode, _) where statusCode >= 500:
                return "Something went wrong on our end. Your account has not been deleted. Try again in a moment."
            default:
                break
            }
        }
        return "We couldn't delete your account. Your account has not been deleted. Try again in a moment."
    }

    // MARK: - Notifications

    /// Notification preferences. Only shown when signed in — the underlying
    /// preference is per-account and the endpoint requires authentication.
    @ViewBuilder
    private var notificationsSection: some View {
        if authManager.isAuthenticated {
            VStack(spacing: 10) {
                sectionHeader(emoji: "\u{1F514}", title: "Notifications", count: nil)
                morningDigestRow
                    .padding(.horizontal)
            }
        }
    }

    private var morningDigestSubtitle: String {
        if let error = viewModel.morningDigestError { return error }
        if viewModel.morningDigestSaving { return "Saving\u{2026}" }
        return "A daily push with the most interesting odds moves"
    }

    private var morningDigestRow: some View {
        Toggle(isOn: Binding(
            get: { viewModel.morningDigestEnabled },
            set: { viewModel.setMorningDigest($0) }
        )) {
            HStack(spacing: 10) {
                Image(systemName: "sun.horizon.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Morning Digest")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)
                    Text(morningDigestSubtitle)
                        .font(.caption2)
                        .foregroundStyle(viewModel.morningDigestError == nil ? Color.secondary.opacity(0.7) : Color.red)
                }
            }
        }
        .toggleStyle(.switch)
        .tint(Color.accentColor)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.4), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
    }

    // MARK: - Privacy

    /// Analytics consent, always visible — signed in or not (Queue 311 A3 /
    /// #1632). Deliberately NOT behind authentication like the notifications
    /// section above: telemetry is collected from anonymous users too, so
    /// gating the control on sign-in would leave exactly the people with no
    /// account unable to revoke.
    private var privacySection: some View {
        VStack(spacing: 10) {
            sectionHeader(emoji: "\u{1F512}", title: "Privacy", count: nil)
            analyticsConsentRow
                .padding(.horizontal)
        }
    }

    private var analyticsConsentSubtitle: String {
        switch telemetryPersistence {
        case .unavailable:
            // The choice is in force now but will not survive a relaunch. Say
            // so rather than claiming it was saved.
            return "In effect for now \u{2014} this device wouldn\u{2019}t save the choice"
        case .unknown, .saved:
            return analyticsConsentGranted
                ? "Anonymous usage stats help us find what\u{2019}s broken"
                : "Off \u{2014} no usage analytics or crash reports are sent"
        }
    }

    private var analyticsConsentRow: some View {
        Toggle(isOn: Binding(
            get: { analyticsConsentGranted },
            set: { granted in
                telemetryPersistence = TelemetryConsent.shared.set(granted ? .analytics : .none)
                analyticsConsentGranted = TelemetryConsent.shared.isGranted
            }
        )) {
            HStack(spacing: 10) {
                Image(systemName: "chart.bar.doc.horizontal")
                    .font(.system(size: 20))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Share usage analytics")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)
                    Text(analyticsConsentSubtitle)
                        .font(.caption2)
                        .foregroundStyle(
                            telemetryPersistence == .unavailable
                                ? Color.orange
                                : Color.secondary.opacity(0.7)
                        )
                }
            }
        }
        .toggleStyle(.switch)
        .tint(Color.accentColor)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.4), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.03), radius: 4, x: 0, y: 2)
    }

    // MARK: - Shared Components

    private func sectionHeader(emoji: String, title: String, count: Int?) -> some View {
        HStack {
            Text("\(emoji) \(title)")
                .font(.title3).fontWeight(.bold)
            Spacer()
            if let count, count > 0 {
                HStack(spacing: 2) {
                    Text("\(count)")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                    Text(count == 1 ? "item" : "items")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.horizontal)
    }
}
