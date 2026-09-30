import Combine
import Foundation

final class ContainerHubViewModel: ObservableObject {
    enum State {
        case loading
        case loaded(ContainerHubPresentation)
        case unavailable
        case error(String)
    }

    @Published private(set) var state: State = .loading
    @Published private(set) var isRefreshing = false
    @Published private(set) var context = ContainerHubReadingContext()

    let slug: String
    private let service: any ContainerHubLoading
    private var requestVersion = 0

    init(slug: String, service: any ContainerHubLoading = ContainerHubService()) {
        self.slug = slug
        self.service = service
    }

    @MainActor
    func load() async {
        requestVersion += 1
        let version = requestVersion
        isRefreshing = true
        defer { if requestVersion == version { isRefreshing = false } }
        do {
            let response = try await service.load(slug: slug)
            guard requestVersion == version, !Task.isCancelled else { return }
            guard response.slug == slug else {
                state = .error("Couldn't read this collection. Try again.")
                return
            }
            let presentation = ContainerHubPresentation(response: response)
            context.accept(presentation)
            // One atomic snapshot: revision, edition, ordering and membership
            // never come from independent reads or cached generations.
            state = .loaded(presentation)
        } catch {
            guard requestVersion == version, !Task.isCancelled else { return }
            if let apiError = error as? APIError,
               case .httpError(statusCode: 404, body: _) = apiError {
                context = ContainerHubReadingContext()
                state = .unavailable
            } else {
                // A failed read is an error, not a successful empty response.
                // Previously shown members are not proof they remain published.
                state = .error(error.localizedDescription)
            }
        }
    }

    @MainActor
    func opened(_ member: ContainerHubMember) { context.open(member) }

    @MainActor
    func scrolled(to memberId: String?) { context.scrollMemberId = memberId }
}
