import Combine
import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var authManager: AuthManager
    @StateObject private var vm = OnboardingViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                progressBar
                    .padding(.horizontal)
                    .padding(.top, 8)

                ScrollView {
                    stepContent
                        .padding(.horizontal)
                        .padding(.top, 16)
                        .padding(.bottom, 100) // space for bottom bar
                }

                bottomBar
            }
            .navigationTitle("Get Started")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                if vm.currentStep < vm.totalSteps {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Skip") { vm.goNext() }
                            .font(.subheadline)
                    }
                }
            }
            .alert("Error", isPresented: .constant(vm.error != nil)) {
                Button("OK") { vm.error = nil }
            } message: {
                Text(vm.error ?? "")
            }
            .onAppear {
                AnalyticsService.trackScreen(name: "onboarding", type: "onboarding")
                AnalyticsService.trackOnboardingStep(step: 1, stepName: "location")
            }
        }
    }

    // MARK: - Progress Bar

    private var progressBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.secondary.opacity(0.2))
                    .frame(height: 6)

                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.accentColor)
                    .frame(width: geo.size.width * CGFloat(vm.currentStep) / CGFloat(vm.totalSteps), height: 6)
                    .animation(.easeInOut(duration: 0.3), value: vm.currentStep)
            }
        }
        .frame(height: 6)
    }

    // MARK: - Step Content

    @ViewBuilder
    private var stepContent: some View {
        switch vm.currentStep {
        case 1: locationStep
        case 2: followStep
        case 3: schoolStep
        case 4: affinityStep
        case 5: rivalStep
        default: EmptyView()
        }
    }

    // MARK: - Bottom Bar

    private var bottomBar: some View {
        VStack(spacing: 0) {
            Divider()
            HStack {
                if vm.currentStep > 1 {
                    Button {
                        vm.goBack()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "chevron.left")
                            Text("Back")
                        }
                    }
                    .buttonStyle(.bordered)
                }

                Spacer()

                if vm.currentStep < vm.totalSteps {
                    Button {
                        vm.goNext()
                    } label: {
                        HStack(spacing: 4) {
                            Text("Continue")
                            Image(systemName: "chevron.right")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Button {
                        Task {
                            let success = await vm.submit()
                            if success {
                                await authManager.refreshProfile()
                                dismiss()
                            }
                        }
                    } label: {
                        if vm.submitting {
                            ProgressView()
                                .frame(width: 80)
                        } else {
                            Text("Done")
                                .fontWeight(.semibold)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(vm.submitting)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial)
        }
    }

    // MARK: - Step 1: Location

    private var locationStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            stepHeader(
                title: "Where do you follow sports?",
                subtitle: "We'll find your local teams."
            )

            searchField(
                query: $vm.locationQuery,
                placeholder: "City or region...",
                searching: vm.locationSearching,
                onChange: { vm.onLocationQueryChange() }
            )

            if !vm.locationTeams.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                    ForEach(vm.locationTeams) { team in
                        teamChip(team: team, selected: team.selected) {
                            vm.toggleLocationTeam(team)
                        }
                    }
                }
            } else if !vm.locationQuery.isEmpty && vm.locationResults.isEmpty && !vm.locationSearching {
                Text("No teams found for this location.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)
            }
        }
    }

    // MARK: - Step 2: Follow Teams

    private var followStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            stepHeader(
                title: "Any other favorite teams?",
                subtitle: "Search for teams you want to follow."
            )

            ZStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 10) {
                    searchField(
                        query: $vm.followQuery,
                        placeholder: "Search teams...",
                        searching: vm.followSearching,
                        onChange: { vm.onFollowQueryChange() }
                    )

                    // Selected chips
                    if !vm.followTeams.isEmpty {
                        selectedChipsList(teams: vm.followTeams, onRemove: vm.removeFollowTeam)
                    }

                    Spacer().frame(height: 0)
                }

                // Dropdown results overlay
                if !vm.followResults.isEmpty {
                    searchDropdown(results: vm.followResults, onSelect: vm.addFollowTeam)
                        .padding(.top, 50)
                }
            }
        }
    }

    // MARK: - Step 3: Alma Maters

    private var schoolStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            stepHeader(
                title: "Any alma maters?",
                subtitle: "Search for your college or university."
            )

            ZStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 10) {
                    searchField(
                        query: $vm.schoolQuery,
                        placeholder: "Search schools...",
                        searching: vm.schoolSearching,
                        onChange: { vm.onSchoolQueryChange() }
                    )

                    if !vm.schoolTeams.isEmpty {
                        selectedChipsList(teams: vm.schoolTeams, onRemove: vm.removeSchoolTeam)
                    }

                    Spacer().frame(height: 0)
                }

                if !vm.schoolResults.isEmpty {
                    searchDropdown(results: vm.schoolResults, onSelect: vm.addSchoolTeam)
                        .padding(.top, 50)
                }
            }
        }
    }

    // MARK: - Step 4: Sport Affinities

    private var affinityStep: some View {
        VStack(alignment: .leading, spacing: 20) {
            stepHeader(
                title: "What do you care about?",
                subtitle: "Set your interest level for each category."
            )

            VStack(alignment: .leading, spacing: 4) {
                Text("Sports")
                    .font(.headline)
                    .padding(.bottom, 4)

                ForEach(OnboardingSportsData.sports) { item in
                    affinityRow(item: item)
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Beyond Sports")
                    .font(.headline)
                    .padding(.bottom, 4)

                ForEach(OnboardingSportsData.beyondSports) { item in
                    affinityRow(item: item)
                }
            }
        }
    }

    // MARK: - Step 5: Rivals

    private var rivalStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            stepHeader(
                title: "Any rivals?",
                subtitle: "Teams you love to hate."
            )

            ZStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 10) {
                    searchField(
                        query: $vm.rivalQuery,
                        placeholder: "Search teams...",
                        searching: vm.rivalSearching,
                        onChange: { vm.onRivalQueryChange() }
                    )

                    if !vm.rivalTeams.isEmpty {
                        selectedChipsList(teams: vm.rivalTeams, onRemove: vm.removeRivalTeam, isRival: true)
                    }

                    Spacer().frame(height: 0)
                }

                if !vm.rivalResults.isEmpty {
                    searchDropdown(results: vm.rivalResults, onSelect: vm.addRivalTeam)
                        .padding(.top, 50)
                }
            }
        }
    }

    // MARK: - Shared Components

    private func stepHeader(title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.title2)
                .fontWeight(.bold)
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.bottom, 4)
    }

    private func searchField(query: Binding<String>, placeholder: String, searching: Bool, onChange: @escaping () -> Void) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            TextField(placeholder, text: query)
                .textFieldStyle(.plain)
                .autocorrectionDisabled()
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .onChange(of: query.wrappedValue) {
                    onChange()
                }

            if searching {
                ProgressView()
                    .controlSize(.small)
            } else if !query.wrappedValue.isEmpty {
                Button {
                    query.wrappedValue = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func teamChip(team: SelectedTeam, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                TeamLogoView(
                    url: team.logoUrl,
                    teamName: team.name,
                    color: .blue,
                    size: 22
                )

                VStack(alignment: .leading, spacing: 1) {
                    Text(team.name)
                        .font(.caption)
                        .fontWeight(.medium)
                        .lineLimit(1)

                    if let sport = team.sportKey {
                        Text(sportDisplayName(for: sport))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer(minLength: 0)

                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.body)
                    .foregroundStyle(selected ? .blue : .secondary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(selected ? Color.blue.opacity(0.1) : Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(selected ? Color.blue.opacity(0.3) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func selectedChipsList(teams: [SelectedTeam], onRemove: @escaping (SelectedTeam) -> Void, isRival: Bool = false) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
            ForEach(teams) { team in
                HStack(spacing: 8) {
                    TeamLogoView(
                        url: team.logoUrl,
                        teamName: team.name,
                        color: isRival ? .red : .blue,
                        size: 22
                    )

                    Text(team.name)
                        .font(.caption)
                        .fontWeight(.medium)
                        .lineLimit(1)

                    Spacer(minLength: 0)

                    Button { onRemove(team) } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(isRival ? Color.red.opacity(0.1) : Color.blue.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
        }
    }

    private func searchDropdown(results: [TeamSearchResult], onSelect: @escaping (TeamSearchResult) -> Void) -> some View {
        VStack(spacing: 0) {
            ForEach(results.prefix(8)) { result in
                Button {
                    onSelect(result)
                } label: {
                    HStack(spacing: 10) {
                        TeamLogoView(
                            url: result.logoUrl,
                            teamName: result.name,
                            color: .blue,
                            size: 24
                        )

                        VStack(alignment: .leading, spacing: 1) {
                            Text(result.name)
                                .font(.subheadline)
                                .lineLimit(1)
                            if let sport = result.sportKey {
                                Text(sportDisplayName(for: sport))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.plain)

                if result.id != results.prefix(8).last?.id {
                    Divider().padding(.leading, 46)
                }
            }
        }
        .background(.ultraThickMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .shadow(color: .black.opacity(0.15), radius: 8, y: 4)
        .zIndex(10)
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
}
