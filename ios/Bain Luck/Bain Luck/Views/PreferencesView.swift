import Combine
import SwiftUI

struct PreferencesView: View {
    @EnvironmentObject var authManager: AuthManager
    @StateObject private var vm = PreferencesViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var showOnboarding = false

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading preferences...")
            } else if let error = vm.error, vm.prefs == nil {
                ContentUnavailableView(
                    "Couldn't Load Preferences",
                    systemImage: "wifi.exclamationmark",
                    description: Text(error)
                )
            } else {
                preferencesList
            }
        }
        .navigationTitle("Preferences")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            await vm.load()
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
                Task { await vm.load() }
                Task { await authManager.refreshProfile() }
            }
        }
    }

    // MARK: - Main List

    private var preferencesList: some View {
        List {
            teamsSection
            interestsSection
            accountSection
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    // MARK: - Section 1: Your Teams

    @ViewBuilder
    private var teamsSection: some View {
        Section {
            if !vm.hasAnyTeams {
                VStack(spacing: 8) {
                    Text("No teams yet")
                        .foregroundStyle(.secondary)
                    Button("Set up your teams") {
                        showOnboarding = true
                    }
                    .font(.subheadline)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
            } else {
                teamGroup(title: "Following", items: vm.followTeams)
                teamGroup(title: "Local", items: vm.localTeams)
                teamGroup(title: "Alma Maters", items: vm.almaMaterTeams)
                teamGroup(title: "Rivals", items: vm.rivalTeams)

                Button {
                    showOnboarding = true
                } label: {
                    Label("Edit Teams", systemImage: "pencil")
                }
            }
        } header: {
            Text("Your Teams")
        }
    }

    @ViewBuilder
    private func teamGroup(title: String, items: [FavoriteItem]) -> some View {
        if !items.isEmpty {
            Text(title)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
                .listRowSeparator(.hidden, edges: .top)

            ForEach(items) { item in
                teamRow(item)
            }
        }
    }

    private func teamRow(_ item: FavoriteItem) -> some View {
        HStack(spacing: 10) {
            TeamLogoView(
                url: item.logoUrl,
                teamName: item.teamName,
                color: .accentColor,
                size: 28
            )

            VStack(alignment: .leading, spacing: 1) {
                Text(item.teamName)
                    .font(.subheadline)
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
                vm.removeFavorite(teamId: item.teamId, relationType: item.relationType)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
                    .font(.body)
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Section 2: Your Interests

    private var interestsSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(OnboardingSportsData.sports) { item in
                    affinityRow(item: item)
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Beyond Sports")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                    .padding(.top, 4)

                ForEach(OnboardingSportsData.beyondSports) { item in
                    affinityRow(item: item)
                }
            }
        } header: {
            Text("Your Interests")
        }
    }

    private func affinityRow(item: SportItem) -> some View {
        HStack(spacing: 10) {
            Text(item.emoji)
                .font(.title3)
                .frame(width: 28)

            Text(item.name)
                .font(.subheadline)
                .frame(width: 90, alignment: .leading)
                .lineLimit(1)

            Spacer()

            HStack(spacing: 6) {
                ForEach(AffinityLevel.allCases, id: \.rawValue) { level in
                    let isActive = vm.affinityLevel(for: item.key) == level
                    Button {
                        vm.setAffinity(item.key, level: level)
                    } label: {
                        Text(level.shortLabel)
                            .font(.caption2)
                            .fontWeight(isActive ? .semibold : .regular)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 5)
                            .background(isActive ? Color.accentColor : Color.cardBackground)
                            .foregroundStyle(isActive ? .white : .primary)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 4)
    }

    // MARK: - Section 3: Account

    private var accountSection: some View {
        Section {
            HStack(spacing: 12) {
                if let photoUrl = authManager.user?.photoUrl, let url = URL(string: photoUrl) {
                    AsyncImage(url: url) { image in
                        image.resizable().scaledToFill()
                    } placeholder: {
                        accountInitialCircle
                    }
                    .frame(width: 44, height: 44)
                    .clipShape(Circle())
                } else {
                    accountInitialCircle
                }

                VStack(alignment: .leading, spacing: 2) {
                    if let name = authManager.user?.displayName {
                        Text(name)
                            .font(.subheadline)
                            .fontWeight(.medium)
                    }
                    if let email = authManager.user?.email {
                        Text(email)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.vertical, 4)

            Button {
                showOnboarding = true
            } label: {
                Label("Redo Onboarding", systemImage: "arrow.counterclockwise")
            }

            Button(role: .destructive) {
                authManager.signOut()
                dismiss()
            } label: {
                Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    .foregroundStyle(.red)
            }
        } header: {
            Text("Account")
        }
    }

    private var accountInitialCircle: some View {
        Circle()
            .fill(Color.accentColor.opacity(0.2))
            .frame(width: 44, height: 44)
            .overlay(
                Text(String((authManager.user?.displayName ?? authManager.user?.email ?? "?").prefix(1)).uppercased())
                    .font(.headline)
                    .foregroundStyle(Color.accentColor)
            )
    }
}
