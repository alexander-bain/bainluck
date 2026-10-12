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
    private struct HeldPage {
        let cursor: String?
        let response: ContainerHubResponse
    }
    private var heldPages: [HeldPage] = []

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
            if case .loaded(let current) = state, current.response.edition?.isTheme == true,
               sameRevision(current.response, response), !response.revisionMoved {
                // Each visited window owns its server position, including failed
                // hydration. Re-read those windows so a later-page missing card
                // can recover without a membership revision or fabricated cursor.
                let visited = heldPages.dropFirst().map { ($0.cursor, $0.response.page?.limit ?? 50) }
                replacePage(response, cursor: nil)
                for (cursor, limit) in visited {
                    guard let cursor else { continue }
                    let page = try await service.loadPage(slug: slug, cursor: cursor, revision: response.revision!, limit: limit)
                    guard version == refreshVersion, admitted(ticket), !Task.isCancelled else { return }
                    try validate(page)
                    guard revisionAdmitted(page) else { return }
                    if page.state != .published { accept(page); return }
                    guard case .loaded(let now) = state, now.response.revision == response.revision else { return }
                    guard sameRevision(response, page), !page.revisionMoved else {
                        accept(page)
                        return
                    }
                    replacePage(page, cursor: cursor)
                }
            } else {
                accept(response)
            }
        } catch {
            guard version == refreshVersion, admitted(ticket), !Task.isCancelled, !isCancellation(error) else { return }
            if isMissing(error) {
                closeReads()
                context = ContainerHubReadingContext()
                heldPages = []
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
                replacePage(response, cursor: cursor)
            } else {
                accept(response)
            }
        } catch {
            guard version == pageVersion, admitted(ticket), !Task.isCancelled, !isCancellation(error) else { return }
            if isMissing(error) {
                closeReads()
                context = ContainerHubReadingContext()
                heldPages = []
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
        if response.state != .published {
            closeReads()
            heldPages = []
        } else {
            heldPages = response.edition?.isTheme == true ? [HeldPage(cursor: nil, response: response)] : []
        }
        let presentation = ContainerHubPresentation(response: response)
        context.accept(presentation)
        state = .loaded(presentation)
    }

    /// Reconstruct from the server's visited window order, never hydrated
    /// arrival order. An empty/withheld window keeps its position and can retry.
    @MainActor
    private func replacePage(_ response: ContainerHubResponse, cursor: String?) {
        if let index = heldPages.firstIndex(where: { $0.cursor == cursor }) {
            heldPages[index] = HeldPage(cursor: cursor, response: response)
        } else { heldPages.append(HeldPage(cursor: cursor, response: response)) }
        var sections: [ContainerHubSection] = []
        var seen = Set<String>()
        for page in heldPages {
            for section in page.response.sections {
                let slots = section.slots.filter { slot in
                    guard let member = slot.member else { return true }
                    return seen.insert(member.id).inserted
                }
                guard !slots.isEmpty else { continue }
                if let index = sections.firstIndex(where: { $0.sectionClass == section.sectionClass }) {
                    let joined = sections[index].slots + slots
                    sections[index] = ContainerHubSection(sectionClass: section.sectionClass, count: joined.count, slots: joined)
                } else {
                    sections.append(ContainerHubSection(sectionClass: section.sectionClass, count: slots.count, slots: slots))
                }
            }
        }
        let pages = heldPages.map(\.response)
        let combined = ContainerHubResponse(envelope: response, sections: sections,
            memberCount: pages.reduce(0) { $0 + $1.memberCount }, page: pages.last?.page,
            withheld: pages.flatMap(\.withheld), withheldCount: pages.reduce(0) { $0 + $1.withheldCount })
        let presentation = ContainerHubPresentation(response: combined)
        context.accept(presentation)
        state = .loaded(presentation)
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
