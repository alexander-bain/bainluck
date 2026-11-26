import Combine
import Foundation
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "first-run-212a")

/// Drives the revised approved `212-A` first-run flow (`#11934`, `#13517`, `359: A`):
/// - Screens `2A..2C`: three live, unsettled real-card pairs where cards themselves are the
///   direct tap targets, with `"Three quick picks, then you're in."` once on Screen 1,
///   `"Your picks decide what Discover shows first."` + `"Tap any you'd check. Both or neither is fine."`,
///   and a single `"Neither, next"` / `"Next"` button.
/// - Screen `2D`: `"Any cities, schools or subjects you care about?"` + `"We'll put these first in Discover and My Stuff."`,
///   showing real served rotating examples (or still line under Reduce Motion), non-clearing single-tap search,
///   and `359: A` plain-sentence chip confirmation / waiting / could-not-read fallback states.
@MainActor
final class FirstRunViewModel212A: ObservableObject {
    typealias FeedLoader = @Sendable () async throws -> [FeedItem]
    typealias SearchSuggestionsLoader = @Sendable () async throws -> [SearchSuggestionEntry212A]
    typealias TeamSearchLoader = @Sendable (String) async throws -> [TeamSearchResult]
    typealias GlobalSearchLoader = @Sendable (String) async throws -> SearchResponse
    typealias OnboardingSubmitter = @Sendable (OnboardingSubmission) async throws -> OnboardingResponse
    typealias SentenceParserLoader = @Sendable (String) async throws -> FirstRunSentenceResponse359A

    // 0, 1, 2 = pairs 2A..2C; 3 = unified search / sentence box 2D
    @Published private(set) var stepIndex: Int = 0
    @Published private(set) var pairs: [FirstRunPair212A]
    @Published private(set) var isLoadingPairs: Bool = false
    @Published private(set) var pairsLoadFailed: Bool = false
    @Published private(set) var selectedSides: [Int: Set<FirstRunPairSide212A>] = [:]
    @Published private(set) var servedExamples: [FirstRunExamplePrompt212A] = []
    @Published private(set) var pairChangeSummaryLine: String? = nil

    // Screen 2D state
    @Published var searchQuery: String = ""
    @Published private(set) var suggestions: [FirstRunSuggestion212A] = []
    @Published private(set) var pickedItems: [FirstRunSuggestion212A] = []
    @Published private(set) var pickedMarketIds: Set<Int> = []
    @Published private(set) var boostedTerms: [String] = []
    @Published private(set) var isSearching: Bool = false
    @Published private(set) var searchCompletedOnce: Bool = false
    @Published private(set) var categoryInterests: [String: Double] = [:]
    @Published private(set) var isFinishing: Bool = false
    @Published private(set) var sentenceState: FirstRunSentenceState359A = .idle

    let totalSteps: Int = 4

    private let initialArrivedHeadline: String?
    private let discoverFeedLoader: FeedLoader
    private let sportsFeedLoader: FeedLoader
    private let searchSuggestionsLoader: SearchSuggestionsLoader?
    private let searchLocationTeams: TeamSearchLoader
    private let searchTeamsByName: TeamSearchLoader
    private let searchGlobal: GlobalSearchLoader
    private let submitOnboarding: OnboardingSubmitter
    private let sentenceParser: SentenceParserLoader?
    private let defaults: UserDefaults
    private let debounceNs: UInt64
    private let sentenceTimeoutNs: UInt64

    private var didStartInteraction = false
    private var didAttemptPairLoad = false
    private var debounceTask: Task<Void, Never>?

    init(
        arrivedHeadline: String? = nil,
        initialPairs: [FirstRunPair212A]? = nil,
        initialExamples: [FirstRunExamplePrompt212A] = [],
        initialStep: Int = 0,
        defaults: UserDefaults = .standard,
        debounceNs: UInt64 = 240_000_000,
        sentenceTimeoutNs: UInt64 = 5_000_000_000,
        feedLoader: FeedLoader? = nil,
        sportsFeedLoader: FeedLoader? = nil,
        searchSuggestionsLoader: SearchSuggestionsLoader? = nil,
        searchLocationTeams: TeamSearchLoader? = nil,
        searchTeamsByName: TeamSearchLoader? = nil,
        searchGlobal: GlobalSearchLoader? = nil,
        submitOnboarding: OnboardingSubmitter? = nil,
        sentenceParser: SentenceParserLoader? = nil
    ) {
        self.initialArrivedHeadline = arrivedHeadline
        self.pairs = initialPairs ?? []
        self.servedExamples = initialExamples
        self.stepIndex = max(0, min(3, initialStep))
        self.defaults = defaults
        self.debounceNs = debounceNs
        self.sentenceTimeoutNs = sentenceTimeoutNs
        self.discoverFeedLoader = feedLoader ?? {
            try await APIClient.shared.fetchFeed(limit: 40, cacheTTL: 0).items
        }
        self.sportsFeedLoader = sportsFeedLoader ?? {
            try await APIClient.shared.fetchFeed(limit: 20, mode: "sports", cacheTTL: 0).items
        }
        if let customSuggestions = searchSuggestionsLoader {
            self.searchSuggestionsLoader = customSuggestions
        } else if feedLoader != nil {
            self.searchSuggestionsLoader = nil
        } else {
            self.searchSuggestionsLoader = {
                (try? await APIClient.shared.fetchSearchSuggestions().suggestions) ?? []
            }
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
        self.sentenceParser = sentenceParser
    }

    var currentPair: FirstRunPair212A? {
        guard stepIndex >= 0 && stepIndex < pairs.count else { return nil }
        return pairs[stepIndex]
    }

    var isOnPairStep: Bool {
        stepIndex < 3
    }

    var isOnTypeaheadStep: Bool {
        stepIndex >= 3
    }

    func selectedSidesForStep(_ index: Int) -> Set<FirstRunPairSide212A> {
        selectedSides[index] ?? []
    }

    func selectedPairCards() -> [FirstRunCard212A] {
        var out: [FirstRunCard212A] = []
        for (idx, pair) in pairs.enumerated() {
            let sides = selectedSides[idx] ?? []
            if sides.contains(.top) { out.append(pair.topCard) }
            if sides.contains(.bottom) { out.append(pair.bottomCard) }
        }
        return out
    }

    // MARK: - Live Feed & Served Examples Load

    func loadLivePairsIfNeeded(forceReload: Bool = false) async {
        if !forceReload {
            guard !didStartInteraction else { return }
            if !pairs.isEmpty && !servedExamples.isEmpty { return }
            if didAttemptPairLoad && pairsLoadFailed { return }
        }
        didAttemptPairLoad = true
        isLoadingPairs = pairs.isEmpty
        pairsLoadFailed = false

        async let discTask: [FeedItem] = (try? await discoverFeedLoader()) ?? []
        async let sportsTask: [FeedItem] = (try? await sportsFeedLoader()) ?? []
        async let sugTask: [SearchSuggestionEntry212A] = (try? await searchSuggestionsLoader?()) ?? []

        let (discItems, sportsItems, searchSugs) = await (discTask, sportsTask, sugTask)
        let combined = discItems + sportsItems
        let builtPairs = FirstRunPair212A.buildPairs(
            from: combined,
            arrivedHeadline: initialArrivedHeadline
        )
        let builtExamples = FirstRunServedExamples212A.buildExamples(
            from: combined,
            searchSuggestions: searchSugs
        )

        if !didStartInteraction && pairs.isEmpty {
            pairs = builtPairs
            pairsLoadFailed = builtPairs.count < 3
        } else if pairs.isEmpty {
            pairsLoadFailed = true
        }
        if servedExamples.isEmpty && !builtExamples.isEmpty {
            servedExamples = builtExamples
        }
        isLoadingPairs = false
    }

    // MARK: - Step 2A..2C Card Toggle & Next

    /// Tapping a card selects or clears it immediately on the first tap (Alex Point 7).
    func toggleCard(_ side: FirstRunPairSide212A, forPairIndex index: Int) {
        guard index >= 0 && index < pairs.count else { return }
        didStartInteraction = true
        var current = selectedSides[index] ?? []
        if current.contains(side) {
            current.remove(side)
        } else {
            current.insert(side)
        }
        selectedSides[index] = current
    }

    /// Commits any tapped card(s) on the active pair screen and advances via the single CTA button.
    func advanceFromCurrentPair(
        followManager: FollowManager295A,
        pinManager: PinManager? = nil
    ) {
        guard stepIndex < 3 else { return }
        didStartInteraction = true

        if stepIndex < pairs.count {
            let pair = pairs[stepIndex]
            let chosen = selectedSides[stepIndex] ?? []
            if chosen.contains(.top) {
                boost(pair.topCard, followManager: followManager, pinManager: pinManager)
            }
            if chosen.contains(.bottom) {
                boost(pair.bottomCard, followManager: followManager, pinManager: pinManager)
            }
        }

        if stepIndex < 3 {
            stepIndex += 1
        }
        if stepIndex >= 3 {
            recomputePairChangeSummary()
        }
    }

    private func boost(
        _ card: FirstRunCard212A,
        followManager: FollowManager295A,
        pinManager: PinManager?
    ) {
        categoryInterests[card.affinityCategory] = 1.0
        if let mid = card.marketId {
            pickedMarketIds.insert(mid)
            if let pinManager, !pinManager.isPinned(type: "future", id: mid) {
                _ = pinManager.togglePin(type: "future", id: mid)
            }
        }
        for kw in card.matchKeywords where !kw.isEmpty && !boostedTerms.contains(kw) {
            boostedTerms.append(kw)
        }
        if let subject = card.followedSubject {
            let sug = FirstRunSuggestion212A(
                id: subject.id,
                name: subject.name,
                sportOrCategoryLabel: subject.sportKey.map { sportDisplayName(for: $0) }
                    ?? sportCategoryDisplayName(card.affinityCategory),
                contextLine: nil,
                logoUrl: card.logoUrl,
                primaryColorHex: card.accentHex,
                teamId: subject.teamId,
                sportKey: subject.sportKey,
                followedSubject: subject,
                affinityCategory: card.affinityCategory,
                marketId: card.marketId,
                matchKeywords: card.matchKeywords
            )
            if !pickedItems.contains(where: { $0.id == sug.id }) {
                pickedItems.append(sug)
            }
            if !followManager.isFollowing(subject) {
                _ = followManager.toggle(subject)
            }
        }
    }

    private func recomputePairChangeSummary() {
        pairChangeSummaryLine = FirstRunPreferences212A.changeSummaryLine(from: selectedPairCards())
    }

    func goBack() {
        if stepIndex > 0 {
            stepIndex -= 1
        }
    }

    /// Skips the current screen (including bypassing a failed pair load straight to Screen 2D).
    func skipCurrentStep(
        followManager: FollowManager295A,
        pinManager: PinManager? = nil,
        authManager: AuthManager,
        onDismiss: () -> Void
    ) {
        didStartInteraction = true
        if stepIndex < 3 {
            stepIndex += 1
            if stepIndex >= 3 {
                recomputePairChangeSummary()
            }
        } else {
            finish(
                followManager: followManager,
                pinManager: pinManager,
                authManager: authManager,
                onDismiss: onDismiss
            )
        }
    }

    // MARK: - Step 2D Unified Typeahead & 359: A Plain-Sentence Confirmation

    func onQueryChange(followManager: FollowManager295A? = nil) {
        debounceTask?.cancel()
        let trimmed = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else {
            suggestions = []
            isSearching = false
            searchCompletedOnce = false
            sentenceState = .idle
            return
        }

        isSearching = true
        let delay = debounceNs
        debounceTask = Task { [weak self] in
            if delay > 0 {
                try? await Task.sleep(nanoseconds: delay)
            }
            guard let self, !Task.isCancelled else { return }
            if FirstRunSentenceMode359A.isEnabledInBuild,
               self.sentenceParser != nil,
               FirstRunSentenceMode359A.looksLikePlainSentence(trimmed) {
                await self.performSentenceParse(query: trimmed, followManager: followManager)
            } else {
                self.sentenceState = .idle
                await self.performTypeahead(query: trimmed)
            }
        }
    }

    func applyExampleQuery(_ query: String) {
        searchQuery = query
        debounceTask?.cancel()
        sentenceState = .idle
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
        let prioritizedCityTeams = Self.prioritizedCityTeams(locResults, query: trimmed)
        if !prioritizedCityTeams.isEmpty {
            // City lookups lead with the city's teams (`/api/me/teams/by-location`), then name & general matches.
            combined.append(contentsOf: FirstRunSuggestion212A.fromTeamSearchResults(prioritizedCityTeams))
            combined.append(contentsOf: FirstRunSuggestion212A.fromTeamSearchResults(nameResults))
            if let globalResponse {
                combined.append(contentsOf: FirstRunSuggestion212A.fromEventSearchResponse(globalResponse, query: trimmed))
            }
        } else {
            if let globalResponse {
                combined.append(contentsOf: FirstRunSuggestion212A.fromEventSearchResponse(globalResponse, query: trimmed))
            }
            combined.append(contentsOf: FirstRunSuggestion212A.fromTeamSearchResults(nameResults))
        }

        suggestions = FirstRunSuggestion212A.mergeDeduplicating(combined)
        isSearching = false
        searchCompletedOnce = true
    }

    private static func prioritizedCityTeams(_ results: [TeamSearchResult], query: String) -> [TeamSearchResult] {
        guard !results.isEmpty else { return [] }
        let lowerQuery = query.lowercased()
        let wantsOffseasonVariant = lowerQuery.contains("preseason") || lowerQuery.contains("summer")

        func primarySportKey(for team: TeamSearchResult) -> String {
            (team.sportKey ?? team.sports?.first?.sportKey ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
        }

        func isOffseasonVariant(_ key: String) -> Bool {
            key.hasSuffix("_preseason") || key.hasSuffix("_summer_league")
        }

        let regularOnly = results.filter { !isOffseasonVariant(primarySportKey(for: $0)) }
        let base = (!wantsOffseasonVariant && !regularOnly.isEmpty) ? regularOnly : results

        func rank(for key: String) -> Int {
            switch key {
            case "americanfootball_nfl": return 0
            case "basketball_nba": return 1
            case "baseball_mlb": return 2
            case "icehockey_nhl": return 3
            case "soccer_usa_mls", "soccer_epl", "soccer_uefa_champs_league",
                 "soccer_spain_la_liga", "soccer_germany_bundesliga",
                 "soccer_italy_serie_a", "soccer_france_ligue_one",
                 "soccer_fifa_world_cup", "basketball_wnba":
                return 4
            case "americanfootball_ncaaf", "americanfootball_ncaaf_fcs": return 5
            case "basketball_ncaab", "basketball_wncaab": return 6
            default:
                return isOffseasonVariant(key) ? 99 : 7
            }
        }

        return base.enumerated().sorted { lhs, rhs in
            let lRank = rank(for: primarySportKey(for: lhs.element))
            let rRank = rank(for: primarySportKey(for: rhs.element))
            if lRank != rRank { return lRank < rRank }
            return lhs.offset < rhs.offset
        }.map(\.element)
    }

    /// Runs `359: A` plain-sentence parsing bounded by `sentenceTimeoutNs` (5s).
    /// On timeout or error, preserves `searchQuery`, displays a plain error note, and falls back
    /// cleanly to ordinary search without ever printing "nothing matched".
    func performSentenceParse(
        query: String,
        followManager: FollowManager295A? = nil
    ) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parser = sentenceParser,
              FirstRunSentenceMode359A.looksLikePlainSentence(trimmed) else {
            sentenceState = .idle
            await performTypeahead(query: trimmed)
            return
        }

        sentenceState = .waiting
        isSearching = false
        searchCompletedOnce = false
        suggestions = []

        do {
            let response = try await raceWithTimeout(nanoseconds: sentenceTimeoutNs) {
                try await parser(trimmed)
            }
            guard searchQuery.trimmingCharacters(in: .whitespacesAndNewlines) == trimmed else { return }

            guard !response.chips.isEmpty else {
                sentenceState = .couldNotRead(
                    message: "Couldn\u{2019}t match items from that note \u{2014} showing regular search instead."
                )
                await performTypeahead(query: trimmed)
                return
            }

            var selectedIds: Set<String> = []
            for chip in response.chips where chip.preselectedByDefault {
                selectedIds.insert(chip.id)
                applyPickedItem(chip.suggestion, followManager: followManager, pinManager: nil)
            }
            sentenceState = .chips(
                chips: response.chips,
                selectedIds: selectedIds,
                isSampleData: response.isSampleData
            )
        } catch {
            guard searchQuery.trimmingCharacters(in: .whitespacesAndNewlines) == trimmed else { return }
            sentenceState = .couldNotRead(
                message: "Couldn\u{2019}t read that sentence right now \u{2014} showing regular search instead."
            )
            await performTypeahead(query: trimmed)
        }
    }

    private func raceWithTimeout<T: Sendable>(
        nanoseconds: UInt64,
        operation: @escaping @Sendable () async throws -> T
    ) async throws -> T {
        try await withThrowingTaskGroup(of: T.self) { group in
            group.addTask {
                try await operation()
            }
            group.addTask {
                try await Task.sleep(nanoseconds: nanoseconds)
                throw CancellationError()
            }
            guard let first = try await group.next() else {
                throw CancellationError()
            }
            group.cancelAll()
            return first
        }
    }

    func toggleSentenceChip(
        _ chip: FirstRunSentenceChip359A,
        followManager: FollowManager295A,
        pinManager: PinManager? = nil
    ) {
        guard case .chips(let chips, var selectedIds, let isSampleData) = sentenceState else { return }
        didStartInteraction = true
        if selectedIds.contains(chip.id) {
            selectedIds.remove(chip.id)
            removePickedItem(chip.suggestion, followManager: followManager)
        } else {
            selectedIds.insert(chip.id)
            applyPickedItem(chip.suggestion, followManager: followManager, pinManager: pinManager)
        }
        sentenceState = .chips(chips: chips, selectedIds: selectedIds, isSampleData: isSampleData)
    }

    func isPicked(_ item: FirstRunSuggestion212A) -> Bool {
        pickedItems.contains { $0.id == item.id }
    }

    /// Immediate single-tap pick/unpick preserving `searchQuery` AND `suggestions`.
    func toggleSuggestion(
        _ item: FirstRunSuggestion212A,
        followManager: FollowManager295A,
        pinManager: PinManager? = nil
    ) {
        didStartInteraction = true
        if pickedItems.contains(where: { $0.id == item.id }) {
            removePickedItem(item, followManager: followManager)
        } else {
            applyPickedItem(item, followManager: followManager, pinManager: pinManager)
        }
    }

    private func applyPickedItem(
        _ item: FirstRunSuggestion212A,
        followManager: FollowManager295A?,
        pinManager: PinManager?
    ) {
        if !pickedItems.contains(where: { $0.id == item.id }) {
            pickedItems.append(item)
        }
        if let cat = item.affinityCategory, !cat.isEmpty {
            categoryInterests[cat] = 1.0
        }
        if let mid = item.marketId {
            pickedMarketIds.insert(mid)
            if let pinManager, !pinManager.isPinned(type: "future", id: mid) {
                _ = pinManager.togglePin(type: "future", id: mid)
            }
        }
        for kw in item.matchKeywords where !kw.isEmpty && !boostedTerms.contains(kw) {
            boostedTerms.append(kw)
        }
        if let subject = item.followedSubject, let followManager, !followManager.isFollowing(subject) {
            _ = followManager.toggle(subject)
        }
    }

    private func removePickedItem(
        _ item: FirstRunSuggestion212A,
        followManager: FollowManager295A
    ) {
        pickedItems.removeAll { $0.id == item.id }
        if let mid = item.marketId {
            pickedMarketIds.remove(mid)
        }
        if let subject = item.followedSubject, followManager.isFollowing(subject) {
            _ = followManager.toggle(subject)
        }
    }

    #if DEBUG
    func setSentenceStateForPreview(_ state: FirstRunSentenceState359A) {
        sentenceState = state
    }
    #endif

    // MARK: - Complete & Persist

    func finish(
        followManager: FollowManager295A,
        pinManager: PinManager? = nil,
        authManager: AuthManager,
        onDismiss: () -> Void
    ) {
        defaults.set(true, forKey: FirstRunStorageKeys212A.onboardedKey)

        if !categoryInterests.isEmpty {
            defaults.set(categoryInterests, forKey: FirstRunStorageKeys212A.localInterestsKey)
        }

        let prefs = FirstRunPreferences212A(
            boostedCategories: Array(Set(categoryInterests.filter { $0.value > 0.5 }.keys)).sorted(),
            boostedTerms: boostedTerms,
            boostedMarketIds: Array(pickedMarketIds).sorted(),
            savedAtEpoch: Date().timeIntervalSince1970
        )
        prefs.save(defaults: defaults)

        let teamRefs = pickedItems.compactMap(\.teamId).map { TeamRef(teamId: $0) }
        for item in pickedItems {
            if let subject = item.followedSubject, !followManager.isFollowing(subject) {
                _ = followManager.toggle(subject)
            }
            if let mid = item.marketId, let pinManager, !pinManager.isPinned(type: "future", id: mid) {
                _ = pinManager.togglePin(type: "future", id: mid)
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
        if defaults === UserDefaults.standard {
            AnonymousLifecycleCounts424A.shared.recordFirstRunFinished()
        }
        onDismiss()
    }
}
