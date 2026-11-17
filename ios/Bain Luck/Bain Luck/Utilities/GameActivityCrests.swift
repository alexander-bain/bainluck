import Foundation
#if canImport(UIKit)
import UIKit
#endif

/// Team crests for the Live Activity (Alex, Nov 16, comparing ours with Apple
/// Sports: "team logos and big scores"). A Live Activity can't fetch an image
/// while it draws, so the app fetches both crests while the game page is open
/// and keeps them in the shared app-group folder, one file per side of each
/// game. The activity's state and the server's push payload never change; a
/// crest that isn't there draws today's look (the short name or badge).
nonisolated enum GameActivityCrests {
    static let appGroup = "group.com.bainluck.Bain-Luck"
    /// A game's crests are kept a week; older files are removed on the next fetch.
    static let keepFor: TimeInterval = 7 * 24 * 60 * 60

    static var directory: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)?
            .appendingPathComponent("GameActivityCrests", isDirectory: true)
    }

    static func file(eventID: Int, home: Bool, in directory: URL) -> URL {
        directory.appendingPathComponent("\(eventID)-\(home ? "home" : "away").png")
    }

    /// Fetch (or reuse) both crests and write them under this game's id. Uses the
    /// saved widget's loader: https only, shrunk to 144 px, cached 30 days by URL.
    static func prefetch(eventID: Int, away: URL?, home: URL?, now: Date = Date(),
                         directory: URL? = directory,
                         fetch: @escaping @Sendable (URL) async -> Data? = { await SavedWidgetLogos12466.download($0) }) async {
        guard eventID > 0, let directory, away != nil || home != nil else { return }
        let byURL = directory.appendingPathComponent("by-url", isDirectory: true)
        let pair = await SavedWidgetLogos12466.load(away: away, home: home, now: now, directory: byURL, fetch: fetch)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = pair.away { try? data.write(to: file(eventID: eventID, home: false, in: directory), options: .atomic) }
        if let data = pair.home { try? data.write(to: file(eventID: eventID, home: true, in: directory), options: .atomic) }
        prune(directory, now: now)
    }

    static func data(eventID: Int, home: Bool, directory: URL? = directory) -> Data? {
        guard eventID > 0, let directory else { return nil }
        return try? Data(contentsOf: file(eventID: eventID, home: home, in: directory))
    }

    #if canImport(UIKit)
    static func image(eventID: Int, home: Bool, directory: URL? = directory) -> UIImage? {
        data(eventID: eventID, home: home, directory: directory).flatMap(UIImage.init(data:))
    }
    #endif

    static func prune(_ directory: URL, now: Date) {
        let keys: [URLResourceKey] = [.contentModificationDateKey]
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: keys, options: [.skipsHiddenFiles]) else { return }
        for url in files where url.pathExtension == "png" {
            guard let stamp = try? url.resourceValues(forKeys: Set(keys)).contentModificationDate,
                  now.timeIntervalSince(stamp) > keepFor else { continue }
            try? FileManager.default.removeItem(at: url)
        }
    }
}

