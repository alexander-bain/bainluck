import Combine
import SwiftUI

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
    }

    // MARK: - Main Content

    private var preferencesContent: some View {
        ScrollView {
            VStack(spacing: 24) {
                accountHero
                teamsSection
                interestsSection
                actionsSection
            }
            .padding(.vertical)
        }
        .background(Color.groupedBackground)
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

        return HStack(spacing: 10) {
            // Emoji + name
            HStack(spacing: 8) {
                Text(item.emoji)
                    .font(.title3)
                    .frame(width: 28)

                Text(item.name)
                    .font(.subheadline)
                    .fontWeight(isActive ? .semibold : .regular)
                    .foregroundStyle(isActive ? .primary : .secondary)
                    .lineLimit(1)
            }

            Spacer()

            // Affinity capsules
            HStack(spacing: 5) {
                ForEach(AffinityLevel.allCases, id: \.rawValue) { level in
                    let selected = currentLevel == level
                    let color = affinityColor[level] ?? .gray

                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            viewModel.setAffinity(item.key, level: level)
                        }
                    } label: {
                        Text(level.shortLabel)
                            .font(.system(size: 11, weight: selected ? .bold : .medium))
                            .lineLimit(1)
                            .fixedSize()
                            .padding(.horizontal, 10)
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
        .padding(.horizontal, 14)
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
                    Task {
                        do {
                            try await authManager.deleteAccount()
                            dismiss()
                        } catch {
                            isDeletingAccount = false
                        }
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This will permanently delete your account and all your data including predictions, favorites, and preferences. This action cannot be undone.")
            }
        }
        .padding(.horizontal)
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
