import Combine
import Foundation

/// #12308 — what the Messages extension is showing, and the readings behind it.
///
/// Two things it can be asked for:
/// - the picker: the reader's saved games and markets, read from the app group
///   the saved-item widget reads (``SavedWidgetBridge10875``). Only canonical
///   ids cross; each title and number comes from the public detail endpoint,
///   exactly what a signed-out reader of the same page sees;
/// - a card a reader tapped in the thread (`.expanded` with a selected
///   message), read again from its link so it shows the current reading.
///
/// The decisions (``MessageScreen12308``, ``MessageCardReading12308``) live
/// with the card in the app's sources, where its tests reach them.
@MainActor
final class MessagesModel12308: ObservableObject {
    enum Saved: Equatable {
        case loading
        /// The app has not told this extension whose saved items these are.
        case openApp
        case empty
        case items([SavedWidgetSubject10875])
    }

    @Published private(set) var screen: MessageScreen12308 = .picker
    @Published private(set) var saved: Saved = .loading
    @Published private(set) var readings: [SavedWidgetSubject10875: MessageCardReading12308] = [:]

    private let fetch: (SavedWidgetSubject10875) async throws -> Data
    private let readBridge: () -> SavedWidgetSnapshot10875?

    init(fetch: @escaping (SavedWidgetSubject10875) async throws -> Data = MessagesFetch12308.data(for:),
         readBridge: @escaping () -> SavedWidgetSnapshot10875? = MessagesFetch12308.bridge) {
        self.fetch = fetch
        self.readBridge = readBridge
    }

    func show(_ screen: MessageScreen12308) async {
        self.screen = screen
        switch screen {
        case .picker:
            await loadSaved()
        case .card(let subject):
            await load(subject)
        }
    }

    func loadSaved() async {
        guard let snapshot = readBridge() else {
            saved = .openApp
            return
        }
        guard !snapshot.subjects.isEmpty else {
            saved = .empty
            return
        }
        saved = .items(snapshot.subjects)
        await withTaskGroup(of: Void.self) { group in
            for subject in snapshot.subjects {
                group.addTask { await self.load(subject) }
            }
        }
    }

    func load(_ subject: SavedWidgetSubject10875) async {
        if readings[subject] == nil { readings[subject] = .loading }
        let fetched: Result<Data, SavedWidgetFetchError10875>
        do {
            fetched = .success(try await fetch(subject))
        } catch let error as SavedWidgetFetchError10875 {
            fetched = .failure(error)
        } catch {
            fetched = .failure(.failed)
        }
        readings[subject] = MessageCardReading12308.after(fetched, for: subject, previous: readings[subject])
    }
}

/// The two public detail endpoints, as the saved-item widget reads them
/// (`SavedItemWidgetFetch10875` in the widget target, restated because that
/// file also carries the widget's App Intents).
nonisolated enum MessagesFetch12308 {
    static let baseURL = "https://api.bainluck.com"

    static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }()

    static func url(for subject: SavedWidgetSubject10875) -> URL? {
        switch subject.kind {
        case .game: return URL(string: "\(baseURL)/api/events/\(subject.id)")
        case .market: return URL(string: "\(baseURL)/api/futures/\(subject.id)?representation=verified_title")
        }
    }

    static func data(for subject: SavedWidgetSubject10875) async throws -> Data {
        guard let url = url(for: subject) else { throw SavedWidgetFetchError10875.failed }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(from: url)
        } catch {
            throw SavedWidgetFetchError10875.failed
        }
        guard let http = response as? HTTPURLResponse else { throw SavedWidgetFetchError10875.failed }
        // 410 is a retired fixture: gone, as the app's pin surfaces read it.
        if http.statusCode == 404 || http.statusCode == 410 { throw SavedWidgetFetchError10875.notFound }
        guard (200...299).contains(http.statusCode) else { throw SavedWidgetFetchError10875.failed }
        return data
    }

    static func bridge() -> SavedWidgetSnapshot10875? {
        SavedWidgetBridge10875.sharedDefaults.flatMap { SavedWidgetBridgeStore10875(defaults: $0).read() }
    }
}
