import SwiftUI
#if canImport(CoreSpotlight)
import CoreSpotlight
import UniformTypeIdentifiers
#endif

// MARK: - The system index

#if canImport(CoreSpotlight)
/// #10874 — `CSSearchableIndex.default()`, written only with
/// `SpotlightIndexItem10874`s: a title, a description (carrying a game's day),
/// keywords and an expiry. No thumbnail, no rating, no price, no start clock.
final class SpotlightSystemIndexClient10874: SpotlightIndexClient10874 {
    private let index = CSSearchableIndex.default()

    static func makeIfAvailable() -> SpotlightSystemIndexClient10874? {
        CSSearchableIndex.isIndexingAvailable() ? SpotlightSystemIndexClient10874() : nil
    }

    func index(_ items: [SpotlightIndexItem10874]) async throws {
        try await index.indexSearchableItems(items.map(Self.searchableItem))
    }

    func delete(identifiers: [String]) async throws {
        try await index.deleteSearchableItems(withIdentifiers: identifiers)
    }

    func deleteDomain(_ domain: String) async throws {
        try await index.deleteSearchableItems(withDomainIdentifiers: [domain])
    }

    static func searchableItem(_ item: SpotlightIndexItem10874) -> CSSearchableItem {
        let attributes = CSSearchableItemAttributeSet(contentType: .content)
        attributes.title = item.title
        attributes.contentDescription = item.detail.isEmpty ? nil : item.detail
        attributes.keywords = item.keywords
        let searchable = CSSearchableItem(uniqueIdentifier: item.identifier, domainIdentifier: item.domain,
                                          attributeSet: attributes)
        searchable.expirationDate = item.expiration
        return searchable
    }
}
#else
final class SpotlightSystemIndexClient10874 {
    static func makeIfAvailable() -> SpotlightIndexClient10874? { nil }
}
#endif

// MARK: - Lifecycle hooks

extension View {
    /// The app root: the signed-in account, the pins of the account the pin
    /// store is bound to, and a tapped Spotlight result. Inert off iPhone/iPad.
    func spotlight10874(userID: String?, pins: PinManager, navigation: NavigationCoordinator) -> some View {
        modifier(SpotlightRoot10874(userID: userID, pins: pins, navigation: navigation))
    }

    /// A detail page: `subject` is non-nil only once the page shows THIS
    /// game's or market's own loaded content.
    func spotlightViewed10874(_ subject: SpotlightSubject10874?) -> some View {
        modifier(SpotlightViewed10874(subject: subject))
    }

    /// My Stuff: the saved pins it has described from their detail payloads.
    func spotlightSavedContent10874(_ model: SavedPinContentViewModel, pins: PinManager) -> some View {
        modifier(SpotlightSavedContent10874(model: model, pins: pins))
    }
}

private struct SpotlightRoot10874: ViewModifier {
    let userID: String?
    @ObservedObject var pins: PinManager
    let navigation: NavigationCoordinator
    @Environment(\.scenePhase) private var scenePhase
    @State private var launched = false

    func body(content: Content) -> some View {
        #if os(iOS) && canImport(CoreSpotlight)
        content
            .task(id: userID) {
                let index = SpotlightIndex10874.shared
                index.bind(userID: userID, delay: launched ? 0 : SpotlightIndex10874.launchDelay)
                launched = true
                index.savedChanged(pins.savedPins, pinUserID: pins.boundUserID)
            }
            .onChange(of: pins.savedPins) { _, saved in
                SpotlightIndex10874.shared.savedChanged(saved, pinUserID: pins.boundUserID)
            }
            .onChange(of: pins.identityGeneration) { _, _ in
                SpotlightIndex10874.shared.savedChanged(pins.savedPins, pinUserID: pins.boundUserID)
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { SpotlightIndex10874.shared.refresh() }
            }
            // Cold and warm launch alike: the exact canonical page through the
            // same router as a Universal Link, queued like one.
            .onContinueUserActivity(CSSearchableItemActionType) { activity in
                guard let url = SpotlightActivation10874.url(
                    activityType: activity.activityType, actionType: CSSearchableItemActionType,
                    identifier: activity.userInfo?[CSSearchableItemActivityIdentifier]) else { return }
                _ = navigation.handleURL(url)
            }
        #else
        content
        #endif
    }
}

private struct SpotlightViewed10874: ViewModifier {
    let subject: SpotlightSubject10874?
    @Environment(\.scenePhase) private var scenePhase

    private struct Key: Equatable {
        let subject: SpotlightSubject10874?
        let active: Bool
    }

    func body(content: Content) -> some View {
        content.task(id: Key(subject: subject, active: scenePhase == .active)) {
            guard SpotlightIndex10874.isEnabledOnThisPlatform, let subject, scenePhase == .active else { return }
            try? await Task.sleep(for: .seconds(SpotlightIndexPlan10874.viewDwell))
            guard !Task.isCancelled else { return }
            SpotlightIndex10874.shared.recordViewed(subject)
        }
    }
}

private struct SpotlightSavedContent10874: ViewModifier {
    @ObservedObject var model: SavedPinContentViewModel
    @ObservedObject var pins: PinManager

    func body(content: Content) -> some View {
        content.onReceive(model.$content) { content in
            guard SpotlightIndex10874.isEnabledOnThisPlatform else { return }
            SpotlightIndex10874.shared.learnSaved(Self.answers(content), pinUserID: pins.boundUserID)
        }
    }

    /// The same fields the detail pages pass, read from the same payloads. A
    /// failed read says nothing and is left out.
    static func answers(_ content: [SavedPin: SavedPinContent])
        -> [StoryContinuationDestination: SpotlightSavedAnswer10874] {
        var answers: [StoryContinuationDestination: SpotlightSavedAnswer10874] = [:]
        for (pin, answer) in content {
            guard let destination = SpotlightIndex10874.destination(pin) else { continue }
            switch answer {
            case .event(let e) where pin.type == "event":
                if let subject = SpotlightSubject10874.game(id: e.id, away: e.awayTeam, home: e.homeTeam,
                                                            sportKey: e.sport, commenceTime: e.commenceTime) {
                    answers[destination] = .described(subject)
                }
            case .market(let f) where pin.type == "future":
                if let subject = SpotlightSubject10874.market(id: f.id, name: f.name,
                                                              category: f.llmSportCategory ?? f.sport) {
                    answers[destination] = .described(subject)
                }
            case .unavailable:
                answers[destination] = .gone
            default:
                continue
            }
        }
        return answers
    }
}
