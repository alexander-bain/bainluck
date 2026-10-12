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
    @Published private(set) var isLoadingMore = false
    @Published private(set) var refreshError: String?
    @Published private(set) var pageError: String?
    @Published private(set) var context = ContainerHubReadingContext()

    let slug: String
    private let service: any ContainerHubLoading
    private var issued = 0
    private var closedThrough = 0
    private var refreshVersion = 0
    private var pageVersion = 0
    private var highestRevision: Int?

    init(slug: String, service: any ContainerHubLoading = ContainerHubService()) {
        self.slug = slug
        self.service = service
    }

    @MainActor
    func load() async {
        issued += 1
        let ticket = issued
        refreshVersion += 1
        let version = refreshVersion
        isRefreshing = true
        refreshError = nil
        defer { if refreshVersion == version { isRefreshing = false } }
        do {
            let response = try await service.load(slug: slug)
            guard version == refreshVersion, admitted(ticket), !Task.isCancelled else { return }
            try validate(response)
            guard revisionAdmitted(response) else { return }
            var next = response
            // Returning from a later page keeps the already accepted inventory and
            // cursor. A new revision replaces it atomically, never appends to it.
            if case .loaded(let current) = state, current.response.edition?.isTheme == true,
               sameRevision(current.response, response) {
                next = merged(current.response, response, append: false)
            }
            accept(next)
        } catch {
            guard version == refreshVersion, admitted(ticket), !Task.isCancelled, !isCancellation(error) else { return }
            if isMissing(error) {
                closeReads()
                context = ContainerHubReadingContext()
                state = .unavailable
            } else if case .loaded(let current) = state, current.response.state == .published {
                // Last-good cards remain readable, explicitly marked as a failed
                // refresh. A failure is never accepted as an empty publication.
                refreshError = error.localizedDescription
            } else {
                state = .error(error.localizedDescription)
            }
        }
    }

    @MainActor
    func loadMore() async {
        guard !isLoadingMore, case .loaded(let current) = state,
              current.response.state == .published, current.response.edition?.isTheme == true,
              let revision = current.response.revision, let cursor = current.response.page?.nextCursor else { return }
        issued += 1
        let ticket = issued
        pageVersion += 1
        let version = pageVersion
        isLoadingMore = true
        pageError = nil
        defer { if pageVersion == version { isLoadingMore = false } }
        do {
            let response = try await service.loadPage(slug: slug, cursor: cursor, revision: revision, limit: current.response.page?.limit ?? 50)
            guard version == pageVersion, admitted(ticket), !Task.isCancelled else { return }
            try validate(response)
            guard revisionAdmitted(response) else { return }
            if response.state != .published {
                accept(response)
                return
            }
            guard case .loaded(let now) = state,
                  now.response.revision == revision, now.response.page?.nextCursor == cursor else { return }
            if sameRevision(now.response, response) && !response.revisionMoved {
                // Server cursors must advance. Retrying a malformed loop must not
                // silently append or offer an endless successful Load more.
                guard response.page?.nextCursor != cursor else { throw APIError.decodingError(underlying: URLError(.cannotParseResponse)) }
                accept(merged(now.response, response, append: true))
            } else {
                accept(response)
            }
        } catch {
            guard version == pageVersion, admitted(ticket), !Task.isCancelled, !isCancellation(error) else { return }
            if isMissing(error) {
                closeReads()
                context = ContainerHubReadingContext()
                state = .unavailable
            } else if case .loaded(let now) = state,
                      now.response.revision == revision, now.response.page?.nextCursor == cursor {
                pageError = error.localizedDescription
            }
        }
    }

    private func admitted(_ ticket: Int) -> Bool { ticket > closedThrough }
    private func revisionAdmitted(_ response: ContainerHubResponse) -> Bool {
        guard let revision = response.revision, let highestRevision else { return true }
        return revision >= highestRevision
    }
    private func validate(_ response: ContainerHubResponse) throws {
        guard response.slug == slug else { throw APIError.decodingError(underlying: URLError(.cannotParseResponse)) }
    }
    private func sameRevision(_ lhs: ContainerHubResponse, _ rhs: ContainerHubResponse) -> Bool {
        lhs.state == .published && rhs.state == .published && lhs.slug == rhs.slug && lhs.revision == rhs.revision
            && lhs.edition == rhs.edition && lhs.counts?.shownCount == rhs.counts?.shownCount
    }

    @MainActor
    private func closeReads() {
        closedThrough = issued
        pageVersion += 1
        isLoadingMore = false
        pageError = nil
        refreshError = nil
    }

    @MainActor
    private func accept(_ response: ContainerHubResponse) {
        if let revision = response.revision { highestRevision = max(highestRevision ?? revision, revision) }
        if response.state != .published { closeReads() }
        let presentation = ContainerHubPresentation(response: response)
        context.accept(presentation)
        state = .loaded(presentation)
    }

    /// Same-revision pages are immutable membership; fresh hydrated cards may
    /// replace old cards. Keep server order and one home for each member.
    private func merged(_ held: ContainerHubResponse, _ fresh: ContainerHubResponse, append: Bool) -> ContainerHubResponse {
        let updates = Dictionary(fresh.sections.flatMap(\.slots).compactMap { slot in slot.member.map { ($0.id, slot) } }, uniquingKeysWith: { _, last in last })
        let withheld = Set(fresh.withheld.compactMap { row in row.id.flatMap { id in row.type.map { "\($0):\(id)" } } })
        var seen = Set<String>()
        var sections = held.sections.map { section in
            let slots = section.slots.compactMap { slot -> ContainerHubMemberSlot? in
                guard let member = slot.member else { return slot }
                guard !withheld.contains(member.id), seen.insert(member.id).inserted else { return nil }
                return updates[member.id] ?? slot
            }
            return ContainerHubSection(sectionClass: section.sectionClass, count: slots.count, slots: slots)
        }
        for section in fresh.sections {
            let additions = section.slots.filter { slot in
                guard let member = slot.member else { return append }
                return seen.insert(member.id).inserted
            }
            guard !additions.isEmpty else { continue }
            if let index = sections.firstIndex(where: { $0.sectionClass == section.sectionClass }) {
                let slots = sections[index].slots + additions
                sections[index] = ContainerHubSection(sectionClass: section.sectionClass, count: slots.count, slots: slots)
            } else {
                sections.append(ContainerHubSection(sectionClass: section.sectionClass, count: additions.count, slots: additions))
            }
        }
        return ContainerHubResponse(envelope: fresh, sections: sections, memberCount: sections.reduce(0) { $0 + $1.count }, page: append ? fresh.page : held.page, previous: held)
    }

    private func isMissing(_ error: Error) -> Bool {
        if let error = error as? APIError, case .httpError(statusCode: 404, body: _) = error { return true }
        return false
    }
    private func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? APIError)?.isCancellation == true || (error as? URLError)?.code == .cancelled
    }

    @MainActor
    func opened(_ member: ContainerHubMember) { context.open(member) }

    @MainActor
    func scrolled(to memberId: String?) { context.scrollMemberId = memberId }
}
