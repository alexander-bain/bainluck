import Combine
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "onboarding")

@MainActor
final class OnboardingViewModel: ObservableObject {
    // MARK: - Step Navigation

    @Published var currentStep = 1
    let totalSteps = 5

    // MARK: - Step 1: Location

    @Published var locationQuery = ""
    @Published var locationResults: [TeamSearchResult] = []
    @Published var locationTeams: [SelectedTeam] = [] // all selected by default, toggleable
    @Published var locationSearching = false

    // MARK: - Step 2: Follow Teams

    @Published var followQuery = ""
    @Published var followResults: [TeamSearchResult] = []
    @Published var followTeams: [SelectedTeam] = []
    @Published var followSearching = false

    // MARK: - Step 3: Alma Maters

    @Published var schoolQuery = ""
    @Published var schoolResults: [TeamSearchResult] = []
    @Published var schoolTeams: [SelectedTeam] = []
    @Published var schoolSearching = false

    // MARK: - Step 4: Sport Affinities

    @Published var sportAffinities: [String: Double] = OnboardingSportsData.defaultAffinities

    // MARK: - Step 5: Rivals

    @Published var rivalQuery = ""
    @Published var rivalResults: [TeamSearchResult] = []
    @Published var rivalTeams: [SelectedTeam] = []
    @Published var rivalSearching = false

    // MARK: - Submission

    @Published var submitting = false
    @Published var error: String?

    // MARK: - Debounce

    private var debounceTask: Task<Void, Never>?

    // MARK: - All Selected IDs (for dedup)

    private var allSelectedIds: Set<Int> {
        var ids = Set<Int>()
        for t in locationTeams where t.selected { ids.insert(t.id) }
        for t in followTeams { ids.insert(t.id) }
        for t in schoolTeams { ids.insert(t.id) }
        for t in rivalTeams { ids.insert(t.id) }
        return ids
    }

    // MARK: - Location Search (Step 1)

    func onLocationQueryChange() {
        debounceTask?.cancel()
        let trimmed = locationQuery.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            locationResults = []
            return
        }
        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await searchByLocation(trimmed)
        }
    }

    private func searchByLocation(_ query: String) async {
        locationSearching = true
        do {
            let results = try await APIClient.shared.searchTeamsByLocation(query: query)
            guard !Task.isCancelled else { return }
            locationResults = results
            // Add all results as selected by default (if not already in list)
            let existingIds = Set(locationTeams.map(\.id))
            for result in results where !existingIds.contains(result.id) {
                locationTeams.append(SelectedTeam(
                    id: result.id,
                    name: result.name,
                    sportKey: result.sportKey,
                    logoUrl: result.logoUrl,
                    selected: true
                ))
            }
            locationSearching = false
        } catch {
            locationSearching = false
            logger.error("Location search failed: \(error)")
        }
    }

    func toggleLocationTeam(_ team: SelectedTeam) {
        if let idx = locationTeams.firstIndex(where: { $0.id == team.id }) {
            locationTeams[idx].selected.toggle()
        }
    }

    // MARK: - Follow Search (Step 2)

    func onFollowQueryChange() {
        debounceTask?.cancel()
        let trimmed = followQuery.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            followResults = []
            return
        }
        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await searchTeams(trimmed, target: .follow)
        }
    }

    func addFollowTeam(_ result: TeamSearchResult) {
        guard !followTeams.contains(where: { $0.id == result.id }) else { return }
        followTeams.append(SelectedTeam(
            id: result.id, name: result.name,
            sportKey: result.sportKey, logoUrl: result.logoUrl, selected: true
        ))
        followQuery = ""
        followResults = []
    }

    func removeFollowTeam(_ team: SelectedTeam) {
        followTeams.removeAll { $0.id == team.id }
    }

    // MARK: - School Search (Step 3)

    func onSchoolQueryChange() {
        debounceTask?.cancel()
        let trimmed = schoolQuery.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            schoolResults = []
            return
        }
        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await searchTeams(trimmed, target: .school)
        }
    }

    func addSchoolTeam(_ result: TeamSearchResult) {
        guard !schoolTeams.contains(where: { $0.id == result.id }) else { return }
        schoolTeams.append(SelectedTeam(
            id: result.id, name: result.name,
            sportKey: result.sportKey, logoUrl: result.logoUrl, selected: true
        ))
        schoolQuery = ""
        schoolResults = []
    }

    func removeSchoolTeam(_ team: SelectedTeam) {
        schoolTeams.removeAll { $0.id == team.id }
    }

    // MARK: - Rival Search (Step 5)

    func onRivalQueryChange() {
        debounceTask?.cancel()
        let trimmed = rivalQuery.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            rivalResults = []
            return
        }
        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await searchTeams(trimmed, target: .rival)
        }
    }

    func addRivalTeam(_ result: TeamSearchResult) {
        guard !rivalTeams.contains(where: { $0.id == result.id }) else { return }
        rivalTeams.append(SelectedTeam(
            id: result.id, name: result.name,
            sportKey: result.sportKey, logoUrl: result.logoUrl, selected: true
        ))
        rivalQuery = ""
        rivalResults = []
    }

    func removeRivalTeam(_ team: SelectedTeam) {
        rivalTeams.removeAll { $0.id == team.id }
    }

    // MARK: - Generic Team Search

    private enum SearchTarget { case follow, school, rival }

    private func searchTeams(_ query: String, target: SearchTarget) async {
        let setSearching: (Bool) -> Void = { searching in
            switch target {
            case .follow: self.followSearching = searching
            case .school: self.schoolSearching = searching
            case .rival: self.rivalSearching = searching
            }
        }
        setSearching(true)
        do {
            var results = try await APIClient.shared.searchTeams(query: query)
            guard !Task.isCancelled else { return }

            // Filter out already-selected teams
            let selectedIds = allSelectedIds
            results = results.filter { !selectedIds.contains($0.id) }

            // For schools, filter to college sports
            if target == .school {
                results = results.filter { result in
                    guard let key = result.sportKey else { return false }
                    let lower = key.lowercased()
                    return lower.contains("ncaa") || lower.contains("wncaab")
                }
            }

            switch target {
            case .follow: followResults = results
            case .school: schoolResults = results
            case .rival: rivalResults = results
            }
            setSearching(false)
        } catch {
            setSearching(false)
            logger.error("Team search failed: \(error)")
        }
    }

    // MARK: - Sport Affinity

    func setAffinity(_ key: String, level: AffinityLevel) {
        sportAffinities[key] = level.rawValue
    }

    func affinityLevel(for key: String) -> AffinityLevel {
        guard let value = sportAffinities[key] else { return .nah }
        return AffinityLevel.allCases.min(by: { abs($0.rawValue - value) < abs($1.rawValue - value) }) ?? .nah
    }

    // MARK: - Navigation

    func goNext() {
        if currentStep < totalSteps {
            currentStep += 1
        }
    }

    func goBack() {
        if currentStep > 1 {
            currentStep -= 1
        }
    }

    var canContinue: Bool {
        true // all steps are optional
    }

    // MARK: - Submit

    func submit() async -> Bool {
        submitting = true
        error = nil

        let submission = OnboardingSubmission(
            homeLocation: locationQuery.trimmingCharacters(in: .whitespaces).isEmpty ? nil : locationQuery.trimmingCharacters(in: .whitespaces),
            localTeams: locationTeams.filter(\.selected).map { TeamRef(teamId: $0.id) },
            followTeams: followTeams.map { TeamRef(teamId: $0.id) },
            almaMaterTeams: schoolTeams.map { TeamRef(teamId: $0.id) },
            rivalTeams: rivalTeams.map { TeamRef(teamId: $0.id) },
            sportAffinities: sportAffinities,
            rawInputs: buildRawInputs()
        )

        do {
            let response = try await APIClient.shared.submitOnboarding(submission)
            submitting = false
            logger.info("Onboarding submitted: \(response.status)")
            return response.onboardingCompleted
        } catch {
            self.error = "Failed to save. Please try again."
            submitting = false
            logger.error("Onboarding submit failed: \(error)")
            return false
        }
    }

    private func buildRawInputs() -> [String: [String]] {
        var raw: [String: [String]] = [:]
        if !locationQuery.trimmingCharacters(in: .whitespaces).isEmpty {
            raw["location"] = [locationQuery.trimmingCharacters(in: .whitespaces)]
        }
        raw["local_teams"] = locationTeams.filter(\.selected).map(\.name)
        raw["follow_teams"] = followTeams.map(\.name)
        raw["alma_mater_teams"] = schoolTeams.map(\.name)
        raw["rival_teams"] = rivalTeams.map(\.name)
        return raw
    }
}
