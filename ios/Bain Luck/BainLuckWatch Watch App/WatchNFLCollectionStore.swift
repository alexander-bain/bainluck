import Combine
import Foundation

/// A separate ephemeral browser. Never changes the v1 futures snapshot schema.
final class WatchNFLCollectionStore: ObservableObject {
    @Published private(set) var weeks: [WatchNFLWeek] = []
    @Published private(set) var week: WatchNFLWeek?
    @Published private(set) var membership: WatchNFLMembership?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    private let transport: any WatchNFLCollectionTransport
    private let season: Int
    private var revision = 0
    private var publishedRevisions: [String: Int] = [:]

    init(transport: any WatchNFLCollectionTransport = WatchNFLCollectionAPIClient(), now: Date = Date()) {
        self.transport = transport
        season = WatchNFLCollectionDecoder.season(asOf: now)
    }
    @MainActor func cancel() {
        revision += 1
        isLoading = false
        // Membership cannot remain actionable after the surface becomes inactive.
        membership = nil
        weeks = []
    }
    @MainActor func browse() async {
        guard !Task.isCancelled else { return }
        week = nil
        membership = nil
        await refresh()
    }
    @MainActor func open(_ selected: WatchNFLWeek) async {
        guard !Task.isCancelled, selected.isValid(season: season) else { return }
        week = selected
        membership = nil
        await refresh()
    }
    @MainActor func refresh() async {
        guard !Task.isCancelled else { return }
        revision += 1
        let stamp = revision
        let requestedWeek = week
        let lastPublishedRevision = requestedWeek.flatMap { publishedRevisions[$0.slug] }
        isLoading = true
        errorMessage = nil
        membership = nil
        weeks = []
        do {
            if let requestedWeek {
                let result = try await transport.membership(week: requestedWeek)
                try Task.checkCancellation()
                guard stamp == revision else { return }
                if result.published, let lastPublishedRevision,
                   (result.revision ?? 0) < lastPublishedRevision { throw WatchNFLDecodeError.invalid }
                if result.published, let accepted = result.revision {
                    publishedRevisions[requestedWeek.slug] = accepted
                }
                membership = result
            } else {
                let result = try await transport.weeks(season: season)
                try Task.checkCancellation()
                guard stamp == revision else { return }
                weeks = result
            }
            isLoading = false
        } catch {
            finish(error, stamp: stamp)
        }
    }
    /// A tap validates current published membership once before changing selection.
    @MainActor func validateGame(_ id: Int) async -> Int? {
        guard !isLoading, let week,
              let tapped = membership?.games.first(where: { $0.id == id }) else { return nil }
        let expectedRevision = revision + 1
        await refresh()
        guard revision == expectedRevision, !Task.isCancelled, !isLoading, errorMessage == nil,
              self.week == week, membership?.published == true else { return nil }
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
    /// Revalidate the week membership, then perform navigation in the same actor turn.
    /// The full-question reader fetches its own probabilities, grades and clocks.
    @MainActor @discardableResult
    func openQuestion(_ id: Int, isActive: () -> Bool, open: (WatchNFLQuestion) -> Void) async -> Bool {
        guard isActive(), !Task.isCancelled, !isLoading, let week,
              membership?.published == true,
              let tapped = membership?.questions.first(where: { $0.id == id }) else { return false }
        let expectedRevision = revision + 1
        await refresh()
        guard revision == expectedRevision, !Task.isCancelled, !isLoading, errorMessage == nil,
              isActive(), self.week == week, membership?.published == true else { return false }
        guard let current = membership?.questions.first(where: { $0.id == id }) else {
            errorMessage = "\(tapped.name) is no longer available in this collection. Choose another question or refresh."
            return false
        }
        open(current)
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
            errorMessage = "Couldn't read NFL weeks. Try again."
        }
    }
}
