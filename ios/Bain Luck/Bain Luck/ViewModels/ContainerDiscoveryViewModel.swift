import Combine
import Foundation

/// Optional Browse entries never replace or delay the ordinary league grid.
/// Refresh revalidates publication and cannot resurrect an older response.
final class ContainerDiscoveryViewModel: ObservableObject {
    @Published private(set) var entries: [ContainerDiscoveryEntry] = []
    @Published private(set) var failedLeagues: [ContainerDiscoveryLeague] = []
    private let service: any ContainerDiscoveryLoading
    private var requestVersion = 0

    init(service: any ContainerDiscoveryLoading = ContainerDiscoveryService()) {
        self.service = service
    }

    private nonisolated enum Read: Sendable {
        case available(ContainerDiscoveryLeague, [ContainerDiscoveryEntry])
        case failed(ContainerDiscoveryLeague)
    }

    @MainActor
    func load(asOf now: Date = Date()) async {
        requestVersion += 1
        let version = requestVersion
        // A prior published list is not evidence it is still available.
        entries = []
        failedLeagues = []
        let service = service
        let results = await withTaskGroup(of: Read.self, returning: [Read].self) { group in
            for league in ContainerDiscoveryLeague.allCases {
                let request = ContainerDiscoveryRequest(league: league, season: league.season(asOf: now))
                group.addTask {
                    do {
                        let response = try await service.load(request)
                        return .available(league, request.entries(in: response))
                    } catch {
                        // An optional-section failure is held internally, never
                        // presented as proof that no collection exists.
                        return .failed(league)
                    }
                }
            }
            var results: [Read] = []
            for await result in group { results.append(result) }
            return results
        }
        guard version == requestVersion, !Task.isCancelled else { return }
        // Stable league order; preserve the producer's relevance order within it.
        for league in ContainerDiscoveryLeague.allCases {
            for result in results {
                switch result {
                case .available(let readLeague, let cards) where readLeague == league:
                    entries.append(contentsOf: cards)
                case .failed(let readLeague) where readLeague == league:
                    failedLeagues.append(league)
                default: break
                }
            }
        }
    }
}
