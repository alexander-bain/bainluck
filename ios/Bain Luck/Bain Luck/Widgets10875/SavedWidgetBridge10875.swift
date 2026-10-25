import CryptoKit
import Foundation

/// #10875 — the ONE thing the app tells the Home/Lock Screen widget: which
/// games and markets the current reader has saved, and whose saved items they
/// are.
///
/// Compiled into the app (which writes it) and the widget extension (which
/// reads it), through the app group both declare. What crosses, and only this:
///
///  - `scope`: `"guest"`, or `"account."` + a digest of the account id. It
///    tells two accounts apart without writing the id itself, a token, or
///    anything else about the account into the shared container. Account ids
///    are numeric and enumerable, so the digest separates accounts; it does not
///    hide the id from a reader of the container, which only the app and its
///    widget extension can read.
///  - `subjects`: the saved games and markets, by canonical id. No titles, no
///    prices: the widget reads those from the public detail endpoints, exactly
///    what a signed-out reader of the same page sees.
///  - `pinsConfirmed`: whether the account's server copy has answered since it
///    was bound, or this is the device's own cache of that account's pins.
///
/// A widget selection carries the scope it was chosen under. When the current
/// scope differs (sign-out, another account), the selection is reported as
/// belonging to another account and nothing about it is shown — not its title,
/// not its number. Signing back into that account restores it.
nonisolated enum SavedWidgetBridge10875 {
    /// The app group both the app and the widget extension declare in their
    /// `.entitlements`. Registering it with the developer account and the
    /// provisioning profiles is the signing gate Native pays; until it is
    /// granted, `UserDefaults(suiteName:)` still answers but nothing is shared,
    /// so the widget reads "open Bain Luck" rather than anything wrong.
    static let appGroup = "group.com.bainluck.Bain-Luck"
    static let storageKey = "bainluck.widget.savedItems.v1"
    /// The kind the app reloads when the saved set or the account changes.
    static let widgetKind = "SavedItemWidget10875"
    static let guestScope = "guest"
    /// The server's bound (`routes/user.py` `MAX_PINS_PER_TYPE`), not the
    /// device's add limit: `PinManager.loadFromServer` adopts an account's
    /// server set as it comes, so a signed-in reader can hold more than
    /// `PinManager.maxPinsPerType` of one kind. The writer never truncates; a
    /// decoded snapshot holding more of one kind than this is not one this app
    /// wrote.
    static let maxSubjectsPerKind = 25

    static func scope(userID: String?) -> String {
        guard let userID, !userID.isEmpty else { return guestScope }
        let digest = SHA256.hash(data: Data("bainluck.widget.scope.v1:\(userID)".utf8))
        return "account." + digest.prefix(12).map { String(format: "%02x", $0) }.joined()
    }

    static var sharedDefaults: UserDefaults? { UserDefaults(suiteName: appGroup) }
}

/// A saved game or market, by the id its detail page is keyed on.
nonisolated struct SavedWidgetSubject10875: Codable, Hashable, Sendable {
    enum Kind: String, Codable, Sendable {
        case game
        case market
    }

    let kind: Kind
    let id: Int

    /// From a `SavedPin`'s `type` ("event" / "future"). Anything else is not
    /// something a widget can show.
    init?(pinType: String, value: Int) {
        guard value > 0 else { return nil }
        switch pinType {
        case "event": kind = .game
        case "future": kind = .market
        default: return nil
        }
        id = value
    }

    init(kind: Kind, id: Int) {
        self.kind = kind
        self.id = id
    }

    /// The app's own routes (`NavigationCoordinator.handleURL`): the same
    /// detail a tap on the pinned card in My Stuff opens.
    var url: URL? {
        URL(string: kind == .game ? "bainluck://events/\(id)" : "bainluck://futures/\(id)")
    }

    /// "game:123" / "market:456" — the stable token inside an entity id.
    var token: String { "\(kind.rawValue):\(id)" }

    init?(token: String) {
        let parts = token.split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count == 2, let kind = Kind(rawValue: String(parts[0])),
              let id = Int(parts[1]), id > 0 else { return nil }
        self.init(kind: kind, id: id)
    }

    /// What a saved item is called before its own title has loaded, in the
    /// pin list's words (`SavedPin.fallbackTitle`).
    var fallbackTitle: String { kind == .game ? "Saved game" : "Saved market" }
}

nonisolated struct SavedWidgetSnapshot10875: Codable, Equatable, Sendable {
    static let currentVersion = 1

    let version: Int
    let scope: String
    let subjects: [SavedWidgetSubject10875]
    let pinsConfirmed: Bool

    init(scope: String, subjects: [SavedWidgetSubject10875], pinsConfirmed: Bool) {
        version = Self.currentVersion
        self.scope = scope
        var seen = Set<SavedWidgetSubject10875>()
        // Games first, then markets, each by id: the order cannot depend on a
        // Set's iteration, so an unchanged saved set never rewrites the store.
        self.subjects = subjects
            .filter { seen.insert($0).inserted }
            .sorted { $0.kind == $1.kind ? $0.id < $1.id : $0.kind == .game }
        self.pinsConfirmed = pinsConfirmed
    }

    func contains(_ subject: SavedWidgetSubject10875) -> Bool { subjects.contains(subject) }
}

/// Reads and writes the snapshot in a `UserDefaults` — the app group's in
/// production, a private suite in tests.
nonisolated struct SavedWidgetBridgeStore10875 {
    let defaults: UserDefaults

    /// `nil` when nothing usable is stored: never written, written by an
    /// incompatible version, or malformed. A reader treats all three the same
    /// way — it does not know the reader's saved items.
    func read() -> SavedWidgetSnapshot10875? {
        guard let data = defaults.data(forKey: SavedWidgetBridge10875.storageKey),
              let snapshot = try? JSONDecoder().decode(SavedWidgetSnapshot10875.self, from: data),
              snapshot.version == SavedWidgetSnapshot10875.currentVersion,
              snapshot.scope == SavedWidgetBridge10875.guestScope || snapshot.scope.hasPrefix("account."),
              snapshot.subjects.filter({ $0.kind == .game }).count <= SavedWidgetBridge10875.maxSubjectsPerKind,
              snapshot.subjects.filter({ $0.kind == .market }).count <= SavedWidgetBridge10875.maxSubjectsPerKind,
              snapshot.subjects.allSatisfy({ $0.id > 0 })
        else { return nil }
        return snapshot
    }

    /// Writes only a change. Returns whether the stored snapshot changed, which
    /// is when the app asks WidgetKit to reload.
    @discardableResult
    func write(_ snapshot: SavedWidgetSnapshot10875) -> Bool {
        guard read() != snapshot, let data = try? JSONEncoder().encode(snapshot) else { return false }
        defaults.set(data, forKey: SavedWidgetBridge10875.storageKey)
        return true
    }
}

/// Where a widget's chosen item stands against the reader's current saved set.
nonisolated enum SavedWidgetSelectionStatus10875: Equatable, Sendable {
    /// Saved by the current reader: show it.
    case saved
    /// Same reader, no longer in their saved items.
    case removed
    /// Chosen under another account, or signed out since. Show nothing about it.
    case otherAccount
    /// The app has not told the widget whose items these are yet.
    case unknown

    static func of(scope: String, subject: SavedWidgetSubject10875,
                   in snapshot: SavedWidgetSnapshot10875?) -> Self {
        guard let snapshot else { return .unknown }
        guard snapshot.scope == scope else { return .otherAccount }
        return snapshot.contains(subject) ? .saved : .removed
    }
}
