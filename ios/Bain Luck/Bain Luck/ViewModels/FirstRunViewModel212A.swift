import Combine
import Foundation
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "first-run-212a")

/// Drives the approved 212-A first-run flow (#11934, #13517):
/// - Three quick two-card pair choices (`2A`, `2B`, `2C`) mixing sports and non-sports real cards,
/// - Followed by unified `"Any cities, schools or subjects you care about?"` typeahead (`2D`),
/// - Zero launch-time notification asks, immediate single-tap selection feedback,
///   non-clearing multi-pick typeahead, distinct multi-sport school labels, and Skip on every screen.
@MainActor
final class FirstRunViewModel212A: ObservableObject {
    typealias FeedLoader = @Sendable () async throws -> [FeedItem]
    typealias TeamSearchLoader = @Sendable (String) async throws -> [TeamSearchResult]
    typealias GlobalSearchLoader = @Sendable (String) async throws -> SearchResponse
    typealias OnboardingSubmitter = @Sendable (OnboardingSubmission) async throws -> OnboardingResponse

    // 0, 1, 2 = pairs 2A..2C; 3 = unified typeahead 2D
    @Published private(set) var stepIndex: Int = 0
    @Published private(set) var pairs: [FirstRunPair212A]
    @Published private(set) var selectedChoices: [Int: FirstRunChoice212A] = [:]

    // Screen 2D state
    @Published var searchQuery: String = ""
    @Published private(set) var suggestions: [FirstRunSuggestion212A] = []
    @Published private(set) var pickedItems: [FirstRunSuggestion212A] = []
    @Published private(set) var isSearching: Bool = false
    @Published private(set) var searchCompletedOnce: Bool = false
    @Published private(set) var categoryInterests: [String: Double] = [:]
    @Published private(set) var isFinishing: Bool = false

    let totalSteps: Int = 4

    private let feedLoader: FeedLoader
    private let searchLocationTeams: TeamSearchLoader
    private let searchTeamsByName: TeamSearchLoader
    private let searchGlobal: GlobalSearchLoader
    private let submitOnboarding: OnboardingSubmitter
    private let defaults: UserDefaults
    private let debounceNs: UInt64
    private let autoAdvanceDelayNs: UInt64

    private var didStartInteraction = false
    private var debounceTask: Task<Void, Never>?
    private var advanceTask: Task<Void, Never>?

    init(
        arrivedHeadline: String? = nil,
        initialPairs: [FirstRunPair212A]? = nil,
        initialStep: Int = 0,
        defaults: UserDefaults = .standard,
        debounceNs: UInt64 = 240_000_000,
        autoAdvanceDelayNs: UInt64 = 220_000_000,
        feedLoader: FeedLoader? = nil,
        searchLocationTeams: TeamSearchLoader? = nil,
        searchTeamsByName: TeamSearchLoader? = nil,
        searchGlobal: GlobalSearchLoader? = nil,
        submitOnboarding: OnboardingSubmitter? = nil
    ) {
        self.pairs = initialPairs ?? FirstRunPair212A.buildPairs(from: [], arrivedHeadline: arrivedHeadline)
        self.stepIndex = max(0, min(3, initialStep))
        self.defaults = defaults
        self.debounceNs = debounceNs
        self.autoAdvanceDelayNs = autoAdvanceDelayNs
        self.feedLoader = feedLoader ?? {
            try await APIClient.shared.fetchFeed(limit: 40).items
        }
        self.searchLocationTeams = searchLocationTeams ?? { query in
            try await APIClient.shared.searchTeamsByLocation(query: query)
        }
        self.searchTeamsByName = searchTeamsByName ?? { query in
            try await APIClient.shared.searchTeams(query: query)
        }
        self.searchGlobal = searchGlobal ?? { query in
            try await APIClient.shared.fetchSearch(query: query)
        }
        self.submitOnboarding = submitOnboarding ?? { submission in
            try await APIClient.shared.submitOnboarding(submission)
        }
    }

    var currentPair: FirstRunPair212A? {
        guard stepIndex >= 0 && stepIndex < pairs.count else { return nil }
        return pairs[stepIndex]
    }

    var isOnTypeaheadStep: Bool {
        stepIndex >= 3
    }

    // MARK: - Feed Load

    func loadLivePairsIfNeeded(arrivedHeadline: String? = nil) async {
        guard !didStartInteraction else { return }
        do {
            let items = try await feedLoader()
            guard !didStartInteraction, !items.isEmpty else { return }
            let livePairs = FirstRunPair212A.buildPairs(from: items, arrivedHeadline: arrivedHeadline)
            if livePairs.count == 3 {
                pairs = livePairs
            }
        } catch {
            // Silently retain curated real-market defaults when offline.
            logger.debug("First-run live feed prefetch fell back to defaults: \(error.localizedDescription)")
        }
    }

    // MARK: - Step 2A-2C Pair Selection

    /// Records the tap immediately so visual state updates synchronously on the first tap,
    /// tunes local category interests, follows any chosen subject, and advances smoothly.
    func selectChoice(
        _ choice: FirstRunChoice212A,
        forPairIndex pairIndex: Int,
        followManager: FollowManager295A
    ) {
        guard pairIndex >= 0 && pairIndex < pairs.count else { return }
        didStartInteraction = true
        selectedChoices[pairIndex] = choice

        let pair = pairs[pairIndex]
        switch choice {
        case .top:
            boost(pair.topCard, followManager: followManager)
        case .bottom:
            boost(pair.bottomCard, followManager: followManager)
        case .both:
            boost(pair.topCard, followManager: followManager)
            boost(pair.bottomCard, followManager: followManager)
        case .neither:
            if !pair.topCard.isSports {
                categoryInterests[pair.topCard.affinityCategory] = max(0.0, (categoryInterests[pair.topCard.affinityCategory] ?? 0.3) - 0.2)
            }
            if !pair.bottomCard.isSports {
                categoryInterests[pair.bottomCard.affinityCategory] = max(0.0, (categoryInterests[pair.bottomCard.affinityCategory] ?? 0.3) - 0.2)
            }
        }

        advanceTask?.cancel()
        if autoAdvanceDelayNs == 0 {
            if stepIndex < 3 && stepIndex == pairIndex {
                stepIndex += 1
            }
        } else {
            let delay = autoAdvanceDelayNs
            advanceTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: delay)
                guard let self, !Task.isCancelled else { return }
                if self.stepIndex < 3 && self.stepIndex == pairIndex {
                    self.stepIndex += 1
                }
            }
        }
    }

    private func boost(_ card: FirstRunCard212A, followManager: FollowManager295A) {
        categoryInterests[card.affinityCategory] = 1.0
        if let subject = card.followedSubject {
            let sug = FirstRunSuggestion212A(
                id: subject.id,
                name: subject.name,
                sportOrCategoryLabel: subject.sportKey.map { sportDisplayName(for: $0) } ?? sportCategoryDisplayName(card.affinityCategory),
                contextLine: nil,
                logoUrl: card.logoUrl,
                primaryColorHex: card.accentHex,
                teamId: subject.teamId,
                sportKey: subject.sportKey,
                followedSubject: subject,
                affinityCategory: card.affinityCategory
            )
            if !pickedItems.contains(where: { $0.id == sug.id }) {
                pickedItems.append(sug)
            }
            if !followManager.isFollowing(subject) {
                _ = followManager.toggle(subject)
            }
        }
    }

    func goBack() {
        advanceTask?.cancel()
        if stepIndex > 0 {
            stepIndex -= 1
        }
    }

    /// Skips the current pair screen or completes the whole flow from the last step.
    func skipCurrentStep(
        followManager: FollowManager295A,
        authManager: AuthManager,
        onDismiss: () -> Void
    ) {
        didStartInteraction = true
        advanceTask?.cancel()
        if stepIndex < 3 {
            stepIndex += 1
        } else {
            finish(followManager: followManager, authManager: authManager, onDismiss: onDismiss)
        }
    }

    // MARK: - Step 2D Unified Typeahead

    func onQueryChange() {
        debounceTask?.cancel()
        let trimmed = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else {
            suggestions = []
            isSearching = false
            searchCompletedOnce = false
            return
        }
        isSearching = true
        let delay = debounceNs
        debounceTask = Task { [weak self] in
            if delay > 0 {
                try? await Task.sleep(nanoseconds: delay)
            }
            guard let self, !Task.isCancelled else { return }
            await self.performTypeahead(query: trimmed)
        }
    }

    func applyPopularQuery(_ query: String) {
        searchQuery = query
        debounceTask?.cancel()
        Task { [weak self] in
            await self?.performTypeahead(query: query)
        }
    }

    func performTypeahead(query: String) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else {
            suggestions = []
            isSearching = false
            searchCompletedOnce = false
            return
        }
        isSearching = true

        async let locTask: [TeamSearchResult] = (try? await searchLocationTeams(trimmed)) ?? []
        async let nameTask: [TeamSearchResult] = (try? await searchTeamsByName(trimmed)) ?? []
        async let globalTask: SearchResponse? = try? await searchGlobal(trimmed)

        let (locResults, nameResults, globalResponse) = await (locTask, nameTask, globalTask)
        guard searchQuery.trimmingCharacters(in: .whitespacesAndNewlines) == trimmed else { return }

        var combined: [FirstRunSuggestion212A] = []
        // Put global SearchResponse teams & non-sports sets + direct name matches ahead of broad city lists
        // so typing "Celtics" or "Oscars" or "Boston" surfaces exact clubs & non-sports subjects immediately.
        if let globalResponse {
            combined.append(contentsOf: FirstRunSuggestion212A.fromEventSearchResponse(globalResponse, query: trimmed))
        }
        combined.append(contentsOf: FirstRunSuggestion212A.fromTeamSearchResults(nameResults))
        combined.append(contentsOf: FirstRunSuggestion212A.fromTeamSearchResults(locResults))

        // Match curated subjects even when global search was unavailable/offline.
        let lower = trimmed.lowercased()
        for topic in FirstRunSuggestion212A.subjectDirectory
        where topic.keywords.contains(where: { $0.contains(lower) || lower.contains($0) }) {
            combined.append(topic.suggestion)
        }

        suggestions = FirstRunSuggestion212A.mergeDeduplicating(combined)
        isSearching = false
        searchCompletedOnce = true
    }

    func isPicked(_ item: FirstRunSuggestion212A) -> Bool {
        pickedItems.contains { $0.id == item.id }
    }

    /// Immediate single-tap pick/unpick.
    /// Deliberately preserves `searchQuery` AND `suggestions` so results stay on screen
    /// and picking a second team/school/subject takes one tap without clearing the search box.
    func toggleSuggestion(
        _ item: FirstRunSuggestion212A,
        followManager: FollowManager295A
    ) {
        didStartInteraction = true
        if let idx = pickedItems.firstIndex(where: { $0.id == item.id }) {
            pickedItems.remove(at: idx)
            if let subject = item.followedSubject, followManager.isFollowing(subject) {
                _ = followManager.toggle(subject)
            }
        } else {
            pickedItems.append(item)
            if let cat = item.affinityCategory {
                categoryInterests[cat] = 1.0
            }
            if let subject = item.followedSubject, !followManager.isFollowing(subject) {
                _ = followManager.toggle(subject)
            }
        }
    }

    // MARK: - Complete & Persist

    func finish(
        followManager: FollowManager295A,
        authManager: AuthManager,
        onDismiss: () -> Void
    ) {
        defaults.set(true, forKey: FirstRunStorageKeys212A.onboardedKey)
        if !categoryInterests.isEmpty {
            defaults.set(categoryInterests, forKey: FirstRunStorageKeys212A.localInterestsKey)
        }

        let teamRefs = pickedItems.compactMap(\.teamId).map { TeamRef(teamId: $0) }
        for item in pickedItems {
            if let subject = item.followedSubject, !followManager.isFollowing(subject) {
                _ = followManager.toggle(subject)
            }
        }

        if authManager.isAuthenticated && (!teamRefs.isEmpty || !categoryInterests.isEmpty) {
            isFinishing = true
            let submission = OnboardingSubmission(
                homeLocation: nil,
                localTeams: [],
                followTeams: teamRefs,
                almaMaterTeams: [],
                rivalTeams: [],
                sportAffinities: categoryInterests,
                rawInputs: ["212a_picks": pickedItems.map(\.chipDisplayText)]
            )
            let submit = submitOnboarding
            Task { [weak authManager] in
                _ = try? await submit(submission)
                await authManager?.refreshProfile()
            }
            isFinishing = false
        }
        onDismiss()
    }
}
