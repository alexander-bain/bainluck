import Combine
import Foundation
import SwiftUI

// MARK: - Live Container & ViewModels for 364: A First-Run Checklist (#11934)

@MainActor
final class FirstRunLookupViewModel364A: ObservableObject {
    typealias SearchLoader = @Sendable (String) async throws -> SearchResponse

    @Published var query: String = ""
    @Published private(set) var results: [FirstRunLookupResult364A] = []
    @Published private(set) var isSearching: Bool = false
    @Published private(set) var hasSearched: Bool = false
    @Published private(set) var searchFailed: Bool = false

    private let searchLoader: SearchLoader
    private let debounceNs: UInt64
    private var searchTask: Task<Void, Never>?

    init(
        debounceNs: UInt64 = 240_000_000,
        searchLoader: SearchLoader? = nil
    ) {
        self.debounceNs = debounceNs
        self.searchLoader = searchLoader ?? { query in
            try await APIClient.shared.fetchSearch(query: query)
        }
    }

    func onQueryChanged(subjectArt: [String: String]) {
        searchTask?.cancel()
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else {
            results = []
            isSearching = false
            hasSearched = false
            searchFailed = false
            return
        }

        isSearching = true
        searchFailed = false
        let delay = debounceNs
        searchTask = Task { [weak self] in
            if delay > 0 {
                try? await Task.sleep(nanoseconds: delay)
            }
            guard let self, !Task.isCancelled else { return }
            await self.performLookupNow(query: trimmed, subjectArt: subjectArt)
        }
    }

    func runImmediateSearch(query rawQuery: String, subjectArt: [String: String]) {
        searchTask?.cancel()
        query = rawQuery
        let trimmed = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else {
            results = []
            isSearching = false
            hasSearched = false
            searchFailed = false
            return
        }
        isSearching = true
        searchFailed = false
        searchTask = Task { [weak self] in
            await self?.performLookupNow(query: trimmed, subjectArt: subjectArt)
        }
    }

    func performLookupNow(query rawQuery: String, subjectArt: [String: String]) async {
        let trimmed = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            results = []
            isSearching = false
            hasSearched = false
            searchFailed = false
            return
        }
        if self.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            self.query = trimmed
        }
        isSearching = true
        searchFailed = false
        do {
            let response = try await searchLoader(trimmed)
            guard self.query.trimmingCharacters(in: .whitespacesAndNewlines) == trimmed else { return }
            results = FirstRunChecklistModelsHelper364A.extractResults(from: response, subjectArt: subjectArt)
            isSearching = false
            hasSearched = true
            searchFailed = false
        } catch is CancellationError {
            return
        } catch {
            guard self.query.trimmingCharacters(in: .whitespacesAndNewlines) == trimmed else { return }
            results = []
            isSearching = false
            hasSearched = true
            searchFailed = true
        }
    }
}

private enum FirstRunChecklistModelsHelper364A {
    static func extractResults(
        from response: SearchResponse,
        subjectArt: [String: String]
    ) -> [FirstRunLookupResult364A] {
        FirstRunChecklistExtractor364A.extractLookupResults(from: response, subjectArt: subjectArt)
    }
}

@MainActor
final class FirstRunChecklistCoordinatorVM364A: ObservableObject {
    typealias FeedLoader = @Sendable () async throws -> [FeedItem]

    @Published private(set) var content: FirstRunChecklistContent364A
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var loadFailed: Bool = false

    private let discoverLoader: FeedLoader
    private let sportsLoader: FeedLoader
    private let defaults: UserDefaults
    private var didLoad = false

    init(
        initialContent: FirstRunChecklistContent364A? = nil,
        defaults: UserDefaults = .standard,
        discoverLoader: FeedLoader? = nil,
        sportsLoader: FeedLoader? = nil
    ) {
        self.defaults = defaults
        self.content = initialContent ?? FirstRunChecklistContent364A(
            lookupExamples: [],
            startWithTonight: [],
            discoverSets: [],
            rowPreviews: [:],
            subjectArtByCategory: [:]
        )
        self.discoverLoader = discoverLoader ?? {
            try await APIClient.shared.fetchFeed(limit: 40, cacheTTL: 0).items
        }
        self.sportsLoader = sportsLoader ?? {
            try await APIClient.shared.fetchFeed(limit: 40, mode: "sports", cacheTTL: 0).items
        }
    }

    func loadIfNeeded(force: Bool = false) async {
        if didLoad && !force && !content.discoverSets.isEmpty {
            return
        }
        didLoad = true
        isLoading = content.discoverSets.isEmpty
        loadFailed = false

        async let discItems: [FeedItem] = (try? await discoverLoader()) ?? []
        async let sportsItems: [FeedItem] = (try? await sportsLoader()) ?? []
        let (disc, sports) = await (discItems, sportsItems)
        let combined = disc + sports
        guard !combined.isEmpty else {
            isLoading = false
            loadFailed = content.discoverSets.isEmpty
            return
        }

        content = FirstRunChecklistExtractor364A.buildContent(from: combined, defaults: defaults)
        isLoading = false
        loadFailed = false
    }
}

private enum ChecklistSheetRoute364A: Hashable {
    case step(FirstRunChecklistRowID364A)
    case appRoute(Route)
}

/// Interactive five-row checklist container wired end-to-end across launch onboarding,
/// "Redo Onboarding" / "Edit Teams", and individual row deep-entries from `My Stuff` (`364: A`).
struct FirstRunChecklistRootView364A: View {
    var initialStep: FirstRunChecklistRowID364A? = nil
    var initialLookupQuery: String? = nil
    var arrivedHeadline: String? = nil
    var entryPoint: String = "first_launch"
    var onComplete: () -> Void = {}

    @Environment(\.followManager295A) private var followManager
    @Environment(\.firstRunChecklistStore364A) private var checklistStore

    @StateObject private var coordinatorVM: FirstRunChecklistCoordinatorVM364A
    @StateObject private var lookupVM: FirstRunLookupViewModel364A
    @StateObject private var followVM: FirstRunViewModel212A
    @StateObject private var telemetryTracker = FirstRunChecklistTelemetryTracker364A()

    init(
        initialStep: FirstRunChecklistRowID364A? = nil,
        initialLookupQuery: String? = nil,
        arrivedHeadline: String? = nil,
        entryPoint: String? = nil,
        initialContent: FirstRunChecklistContent364A? = nil,
        coordinatorVM: FirstRunChecklistCoordinatorVM364A? = nil,
        followVM: FirstRunViewModel212A? = nil,
        onComplete: @escaping () -> Void = {}
    ) {
        self.initialStep = initialStep
        self.initialLookupQuery = initialLookupQuery
        self.arrivedHeadline = arrivedHeadline
        self.entryPoint = entryPoint ?? (arrivedHeadline == nil ? "first_launch" : "shared_link")
        self.onComplete = onComplete
        _coordinatorVM = StateObject(
            wrappedValue: coordinatorVM ?? FirstRunChecklistCoordinatorVM364A(initialContent: initialContent)
        )
        _lookupVM = StateObject(wrappedValue: FirstRunLookupViewModel364A())
        _followVM = StateObject(
            wrappedValue: followVM ?? FirstRunViewModel212A(arrivedHeadline: arrivedHeadline, initialStep: 3)
        )
    }

    var body: some View {
        FirstRunChecklistRootBody364A(
            initialStep: initialStep,
            initialLookupQuery: initialLookupQuery,
            entryPoint: entryPoint,
            coordinatorVM: coordinatorVM,
            lookupVM: lookupVM,
            followVM: followVM,
            telemetryTracker: telemetryTracker,
            followManager: followManager,
            checklistStore: checklistStore,
            onComplete: onComplete
        )
    }
}

private struct FirstRunChecklistRootBody364A: View {
    let initialStep: FirstRunChecklistRowID364A?
    let initialLookupQuery: String?
    let entryPoint: String
    @ObservedObject var coordinatorVM: FirstRunChecklistCoordinatorVM364A
    @ObservedObject var lookupVM: FirstRunLookupViewModel364A
    @ObservedObject var followVM: FirstRunViewModel212A
    @ObservedObject var telemetryTracker: FirstRunChecklistTelemetryTracker364A
    @ObservedObject var followManager: FollowManager295A
    @ObservedObject var checklistStore: FirstRunChecklistStore364A
    let onComplete: () -> Void

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var pinManager: PinManager

    @State private var path: [ChecklistSheetRoute364A] = []
    @State private var draftSetSlugs: Set<String> = []
    @State private var isRequestingAlerts = false
    @State private var didApplyInitialStep = false

    var body: some View {
        let storeBinding = Binding<FirstRunChecklistState364A>(
            get: { checklistStore.state },
            set: { checklistStore.state = $0 }
        )

        NavigationStack(path: $path) {
            FirstRunChecklistView364A(
                content: coordinatorVM.content,
                state: storeBinding,
                onSkipOrFinish: finishAndDismiss,
                onOpenRow: openStep(_:)
            )
            .navigationDestination(for: ChecklistSheetRoute364A.self) { dest in
                switch dest {
                case .step(let row):
                    stepDestination(for: row)
                case .appRoute(let route):
                    RouteDestination(route: route)
                }
            }
        }
        #if os(macOS)
        .frame(minWidth: 520, idealWidth: 580, minHeight: 620, idealHeight: 720)
        #endif
        .task {
            syncStoreExternalSignals()
            telemetryTracker.recordStartIfNeeded(
                entryPoint: entryPoint,
                initialCompletedRows: checklistStore.state.completedRows,
                initialFollowedSubjects: followManager.subjects
            )
            draftSetSlugs = checklistStore.state.selectedSetSlugs
            if let initialLookupQuery, !initialLookupQuery.isEmpty {
                lookupVM.runImmediateSearch(
                    query: initialLookupQuery,
                    subjectArt: coordinatorVM.content.subjectArtByCategory
                )
            }
            if !didApplyInitialStep, let initialStep {
                didApplyInitialStep = true
                path = [.step(initialStep)]
            }
            async let loadContent: Void = coordinatorVM.loadIfNeeded()
            async let loadFollow: Void = followVM.loadLivePairsIfNeeded()
            _ = await (loadContent, loadFollow)
        }
        .onChange(of: checklistStore.state.completedRows) { _, newRows in
            telemetryTracker.syncCompletedRows(newRows)
        }
        .onReceive(checklistStore.$state) { newState in
            telemetryTracker.syncCompletedRows(newState.completedRows)
        }
        .onChange(of: followManager.subjects.count) { _, newCount in
            checklistStore.syncFollowCount(newCount, markFollowCompleted: !path.isEmpty && newCount > 0)
        }
        .onReceive(followManager.$subjects) { newSubjects in
            telemetryTracker.syncFollowedSubjects(newSubjects)
        }
        .onChange(of: authManager.isAuthenticated) { _, authed in
            checklistStore.syncAuthState(isAuthenticated: authed)
        }
        .onChange(of: lookupVM.query) { _, _ in
            lookupVM.onQueryChanged(subjectArt: coordinatorVM.content.subjectArtByCategory)
        }
        .onDisappear {
            telemetryTracker.recordFinishOrSkip(
                completedRows: checklistStore.state.completedRows,
                followedSubjects: followManager.subjects
            )
        }
    }

    @ViewBuilder
    private func stepDestination(for row: FirstRunChecklistRowID364A) -> some View {
        switch row {
        case .lookUp:
            FirstRunLookupStepView364A(
                examples: coordinatorVM.content.lookupExamples,
                query: $lookupVM.query,
                results: lookupVM.results,
                isSearching: lookupVM.isSearching,
                hasSearched: lookupVM.hasSearched,
                searchFailed: lookupVM.searchFailed,
                onTapExample: { ex in
                    lookupVM.runImmediateSearch(
                        query: ex.query,
                        subjectArt: coordinatorVM.content.subjectArtByCategory
                    )
                },
                onSelectResult: { res in
                    checklistStore.markCompleted(.lookUp)
                    if let route = res.route {
                        path.append(.appRoute(route))
                    }
                },
                onRetrySearch: {
                    Task {
                        await lookupVM.performLookupNow(
                            query: lookupVM.query,
                            subjectArt: coordinatorVM.content.subjectArtByCategory
                        )
                    }
                },
                onBack: popTopStep,
                onDone: {
                    if !lookupVM.results.isEmpty || !lookupVM.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        checklistStore.markCompleted(.lookUp)
                    }
                    popTopStep()
                }
            )

        case .follow:
            FirstRunFollowStepView364A(
                vm: followVM,
                subjectArtByCategory: coordinatorVM.content.subjectArtByCategory,
                onBack: commitFollowChangesAndPop,
                onDone: commitFollowChangesAndPop
            )

        case .exploreSets:
            FirstRunExploreSetsStepView364A(
                sets: coordinatorVM.content.discoverSets,
                selectedSlugs: $draftSetSlugs,
                isLoading: coordinatorVM.isLoading,
                loadFailed: coordinatorVM.loadFailed,
                onRetry: {
                    Task { await coordinatorVM.loadIfNeeded(force: true) }
                },
                onBack: popTopStep,
                onDone: {
                    checklistStore.setSelectedSetSlugs(draftSetSlugs, from: coordinatorVM.content.discoverSets)
                    popTopStep()
                }
            )

        case .syncDevices:
            FirstRunSignInStepView364A(
                isSignedIn: authManager.isAuthenticated,
                isSigningIn: authManager.isSigningIn,
                errorMessage: authManager.error,
                onAppleSignIn: { authManager.signInWithApple() },
                onGoogleSignIn: { authManager.signInWithGoogle() },
                onBackOrSkip: popTopStep
            )

        case .alerts:
            FirstRunAlertsStepView364A(
                previewMover: coordinatorVM.content.startWithTonight.first(where: { $0.slotLabel == "Biggest mover" }),
                previewUpcomingGame: coordinatorVM.content.startWithTonight.first(where: { $0.slotLabel == "Biggest game" }),
                alertsAlreadyOn: GameAlertsPreference13083.shared.isEnabled,
                isBusy: isRequestingAlerts,
                onTurnOnAlerts: {
                    guard !isRequestingAlerts else { return }
                    isRequestingAlerts = true
                    Task { @MainActor in
                        _ = await GameAlertsPreference13083.shared.optInAndRequestPermission()
                        checklistStore.markCompleted(.alerts)
                        isRequestingAlerts = false
                        popTopStep()
                    }
                },
                onNotNow: popTopStep,
                onBack: popTopStep,
                onDone: popTopStep
            )
        }
    }

    private func openStep(_ row: FirstRunChecklistRowID364A) {
        if row == .exploreSets {
            draftSetSlugs = checklistStore.state.selectedSetSlugs
        }
        path.append(.step(row))
    }

    private func popTopStep() {
        if !path.isEmpty {
            path.removeLast()
        } else {
            dismiss()
        }
    }

    private func commitFollowChangesAndPop() {
        let count = followManager.subjects.count
        checklistStore.syncFollowCount(count, markFollowCompleted: count > 0 || !followVM.pickedItems.isEmpty)
        telemetryTracker.syncFollowedSubjects(followManager.subjects)
        telemetryTracker.syncCompletedRows(checklistStore.state.completedRows)
        persistMergedDiscoverPreferences()
        popTopStep()
    }

    private func finishAndDismiss() {
        let wasAlreadyOnboarded = UserDefaults.standard.bool(forKey: FirstRunStorageKeys212A.onboardedKey)
        UserDefaults.standard.set(true, forKey: FirstRunStorageKeys212A.onboardedKey)
        checklistStore.syncFollowCount(followManager.subjects.count)
        persistMergedDiscoverPreferences()
        AnonymousLifecycleCounts424A.shared.recordFirstRunFinished(wasAlreadyOnboarded: wasAlreadyOnboarded)
        followVM.finish(
            followManager: followManager,
            pinManager: pinManager,
            authManager: authManager,
            onDismiss: {
                telemetryTracker.recordFinishOrSkip(
                    completedRows: checklistStore.state.completedRows,
                    followedSubjects: followManager.subjects
                )
                onComplete()
                dismiss()
            }
        )
    }

    private func persistMergedDiscoverPreferences() {
        checklistStore.setSelectedSetSlugs(
            checklistStore.state.selectedSetSlugs,
            from: coordinatorVM.content.discoverSets
        )
        var prefs = FirstRunPreferences212A.load()
        var cats = Set(prefs.boostedCategories)
        var terms = Set(prefs.boostedTerms)
        var ids = Set(prefs.boostedMarketIds)
        for item in followVM.pickedItems {
            if let cat = item.affinityCategory, !cat.isEmpty { cats.insert(cat) }
            for kw in item.matchKeywords where !kw.isEmpty { terms.insert(kw) }
            if let mid = item.marketId { ids.insert(mid) }
        }
        for subj in followManager.subjects {
            if !subj.name.isEmpty { terms.insert(subj.name) }
            if let cat = subj.affinityCategory, !cat.isEmpty { cats.insert(cat) }
            if let mid = subj.marketId { ids.insert(mid) }
        }
        prefs.boostedCategories = Array(cats).sorted()
        prefs.boostedTerms = Array(terms).sorted()
        prefs.boostedMarketIds = Array(ids).sorted()
        prefs.savedAtEpoch = Date().timeIntervalSince1970
        prefs.save()
    }

    private func syncStoreExternalSignals() {
        checklistStore.syncFollowCount(followManager.subjects.count)
        checklistStore.syncAuthState(isAuthenticated: authManager.isAuthenticated)
        checklistStore.syncAlertsState(isEnabled: GameAlertsPreference13083.shared.isEnabled)
    }
}
