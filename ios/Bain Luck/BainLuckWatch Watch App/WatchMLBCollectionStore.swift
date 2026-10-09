import Combine
import Foundation

/// A separate ephemeral browser. Never changes the v1 futures snapshot schema.
final class WatchMLBCollectionStore: ObservableObject {
    @Published private(set) var collections: [WatchMLBCollection] = []
    @Published private(set) var collection: WatchMLBCollection?
    @Published private(set) var membership: WatchMLBMembership?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    private let transport: any WatchMLBCollectionTransport
    private let season: Int
    private var revision = 0
    private var publishedRevisions: [String: Int] = [:]

    init(transport: any WatchMLBCollectionTransport = WatchMLBCollectionAPIClient(), now: Date = Date()) {
        self.transport = transport
        season = WatchMLBCollectionDecoder.season(asOf: now)
    }
    @MainActor func cancel() {
        revision += 1
        isLoading = false
        // Membership cannot remain actionable after the surface becomes inactive.
        membership = nil
        collections = []
    }
    @MainActor func browse() async {
        guard !Task.isCancelled else { return }
        collection = nil
        membership = nil
        await refresh()
    }
    @MainActor func open(_ selected: WatchMLBCollection) async {
        guard !Task.isCancelled, selected.isValid(season: season) else { return }
        collection = selected
        membership = nil
        await refresh()
    }
    @MainActor func refresh() async {
        guard !Task.isCancelled else { return }
        revision += 1
        let stamp = revision
        let requestedCollection = collection
        let lastPublishedRevision = requestedCollection.flatMap { publishedRevisions[$0.slug] }
        isLoading = true
        errorMessage = nil
        membership = nil
        collections = []
        do {
            if let requestedCollection {
                let result = try await transport.membership(collection: requestedCollection)
                try Task.checkCancellation()
                guard stamp == revision else { return }
                if let lastPublishedRevision, let incomingRevision = result.revision,
                   incomingRevision < lastPublishedRevision { throw WatchMLBCollectionError.invalid }
                if let accepted = result.revision {
                    publishedRevisions[requestedCollection.slug] = accepted
                }
                membership = result
            } else {
                let result = try await transport.collections(season: season)
                try Task.checkCancellation()
                guard stamp == revision else { return }
                collections = result
            }
            isLoading = false
        } catch {
            finish(error, stamp: stamp)
        }
    }
    /// A tap validates current published membership once before changing selection.
    @MainActor func validateGame(_ id: Int) async -> Int? {
        guard !isLoading, let collection,
              let tapped = membership?.games.first(where: { $0.id == id }) else { return nil }
        let expectedRevision = revision + 1
        await refresh()
        guard revision == expectedRevision, !Task.isCancelled, !isLoading, errorMessage == nil,
              self.collection == collection, membership?.published == true else { return nil }
        guard membership?.games.contains(where: { $0.id == id }) == true else {
            // Only the current successful validation can explain a missing member.
            // Retain the tapped names, never its old score or chance.
            errorMessage = "\(tapped.away) at \(tapped.home) is no longer available in this collection. Choose another game or refresh."
            return nil
        }
        return id
    }
    /// Keep the final validation guard and selection effect in one MainActor turn.
    /// A test can observe this exact production seam without loading SwiftUI.
    @MainActor @discardableResult
    func selectGame(_ id: Int, isActive: () -> Bool, select: (Int) -> Void) async -> Bool {
        guard isActive(), !Task.isCancelled else { return false }
        let expectedRevision = revision + 1
        guard let validatedID = await validateGame(id),
              revision == expectedRevision,
              isActive(), !Task.isCancelled else { return false }
        select(validatedID)
        return true
    }
    @MainActor private func finish(_ error: Error, stamp: Int) {
        guard stamp == revision else { return }
        isLoading = false
        if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
        if let error = error as? URLError, [.notConnectedToInternet, .networkConnectionLost].contains(error.code) {
            errorMessage = "Offline. Try again."
        } else if (error as? URLError)?.code == .timedOut {
            errorMessage = "Connection timed out. Try again."
        } else {
            errorMessage = "Couldn't read MLB postseason collections. Try again."
        }
    }
}
