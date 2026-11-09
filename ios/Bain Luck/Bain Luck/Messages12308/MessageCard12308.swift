import Foundation

/// #12308 — what a Bain Luck card in a Messages thread says.
///
/// The card is the saved-item widget's reading (``SavedWidgetReadingRules10875``),
/// so a game or market reads the same in a thread as on the Home Screen, with
/// the rules the detail page one tap away draws with:
/// - a finished game names its winner and never a price;
/// - a draw-priced away side is withheld, never `1 − home`;
/// - a price that has stopped being current says so.
///
/// Cards print whole numbers, as every card does (#10090 keeps tenths for the
/// event page's headline).
///
/// A shared card names every side it prices, "Bills 62% · Vikings 38%", and
/// never leaves a bare number for someone else to attribute (#4306).
///
/// The card in the thread is the reading as it was when sent, and says so: its
/// price is dated ("Win chance as of Nov 9 at 4:44 AM EST"), never "Current", because
/// nothing redraws it. Tapping it opens the item's current reading. (A live
/// layout would redraw in the thread, but Messages never tells such a card
/// which message it is drawing: on the iOS 26.5 and 27.0 simulators its
/// instance gets no conversation and no `willBecomeActive`, so it can only
/// spin.)
///
/// The message carries only the item's public link, the one Share sends
/// (`https://bainluck.com/events/<id>` or `/futures/<id>`).
nonisolated struct MessageCard12308: Equatable, Sendable {
    let subject: SavedWidgetSubject10875
    /// "Buffalo Bills vs Minnesota Vikings", or the market's name.
    let title: String
    /// "Bills 62% · Vikings 38%", "Bills won", "Yes 61%".
    let line: String
    /// The reading's standing now, for the picker and the opened card:
    /// "Starts Nov 9 at 8:15 PM · Current win chance", "Final · 24–21".
    let status: String
    /// The same standing for the card as sent, with its price dated:
    /// "Starts Nov 9 at 8:15 PM EST · Win chance as of Nov 9 at 4:44 AM EST".
    let sentStatus: String
    /// What the thread list and a notification show.
    let summary: String
    /// The current reading as one sentence, for VoiceOver.
    let spoken: String
    /// The card as sent, as one sentence: the sent message's label.
    let sentSpoken: String
    let phase: SavedWidgetReading10875.Phase
    /// The public link the message carries.
    let url: URL
}

enum MessageCardRules12308 {

    static func card(_ payload: SavedWidgetDetailPayload10875, now: Date = Date(),
                     timeZone: TimeZone = .current) -> MessageCard12308? {
        let subject: SavedWidgetSubject10875
        let reading: SavedWidgetReading10875
        let line: String
        var sentStart: String?
        switch payload {
        case .game(let event):
            subject = SavedWidgetSubject10875(kind: .game, id: event.id)
            reading = SavedWidgetReadingRules10875.game(event, side: nil, now: now)
            let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
            line = gameLine(reading, away: names.away, home: names.home)
            // The widget's start time is the reader's own clock; a friend's may
            // differ, so the sent card names its zone.
            if reading.status.hasPrefix("Starts "), event.startIsTbd != true,
               let start = SavedWidgetDetailDecoding10875.date(event.commenceTime) {
                sentStart = "Starts \(stamp(start, timeZone: timeZone))"
            }
        case .market(let market):
            subject = SavedWidgetSubject10875(kind: .market, id: market.id)
            reading = SavedWidgetReadingRules10875.market(market, outcomeID: nil, now: now)
            line = marketLine(reading)
        }
        guard let url = url(for: subject) else { return nil }
        let status = [reading.status, reading.priceCaption].compactMap { $0 }.joined(separator: " · ")
        let sent = sentStatus(reading, kind: subject.kind, now: now, timeZone: timeZone, start: sentStart)
        return MessageCard12308(
            subject: subject, title: reading.subject, line: line, status: status, sentStatus: sent,
            summary: "\(reading.subject): \(line)", spoken: reading.spoken,
            sentSpoken: "\(reading.subject): \(spokenList(line)). \(spokenList(sent, separator: ". ")).",
            phase: reading.phase, url: url)
    }

    /// Both sides, each beside its own figure. A side with no figure (the
    /// withheld away side of a draw-priced match) is left out, not filled in.
    static func gameLine(_ reading: SavedWidgetReading10875, away: String, home: String) -> String {
        let named = zip([away, home], reading.rows)
        switch reading.phase {
        case .current, .lastRecorded, .openingLine:
            let parts = named.compactMap { name, row in row.figure.map { "\(name) \($0)" } }
            return parts.isEmpty ? noNumber : parts.joined(separator: " · ")
        case .result:
            if let winner = named.first(where: { $0.1.verdict == "Won" }) { return "\(winner.0) won" }
            if reading.rows.contains(where: { $0.verdict == "Draw" }) { return "Draw" }
            // Settled at the venue: its verdict, verbatim.
            return reading.headline?.verdict ?? "Settled"
        case .noResult:
            return "No result recorded"
        case .unavailable:
            return noNumber
        }
    }

    /// The market page's hero outcome, by name.
    static func marketLine(_ reading: SavedWidgetReading10875) -> String {
        guard let row = reading.headline else { return noNumber }
        if let figure = row.figure { return "\(row.label) \(figure)" }
        switch row.verdict {
        case "Won"?: return "\(row.label) won"
        case "Lost"?: return "\(row.label) lost"
        case let verdict?: return "\(row.label): \(verdict.lowercased())"
        case nil: return noNumber
        }
    }

    /// The standing a sent card keeps. A price is dated by its own clock (or,
    /// undated, by when it was read), because the card is never redrawn; a
    /// result, a missing price or an opening line needs no date. Every time on
    /// it names its zone, because the friend reading it may live in another.
    /// `start` replaces the reading's own start time with the zoned one.
    static func sentStatus(_ reading: SavedWidgetReading10875, kind: SavedWidgetSubject10875.Kind,
                           now: Date, timeZone: TimeZone = .current, start: String? = nil) -> String {
        let chance = kind == .game ? "Win chance" : "Chance"
        let price: String?
        switch reading.phase {
        case .current:
            price = "\(chance) as of \(stamp(reading.observedAt ?? now, timeZone: timeZone))"
        case .lastRecorded:
            let caption = reading.priceCaption ?? "Last recorded \(chance.lowercased())"
            price = reading.observedAt.map { "\(caption), \(stamp($0, timeZone: timeZone))" } ?? caption
        case .openingLine:
            price = reading.priceCaption
        case .result, .noResult, .unavailable:
            price = nil
        }
        return [start ?? reading.status, price].compactMap { $0 }.joined(separator: " · ")
    }

    /// "Nov 9 at 4:44 AM EST": a sent card's time, with its zone.
    static func stamp(_ date: Date, timeZone: TimeZone = .current) -> String {
        date.formatted(Date.FormatStyle(locale: Locale(identifier: "en_US"), timeZone: timeZone)
            .month(.abbreviated).day().hour(.defaultDigits(amPM: .abbreviated)).minute()
            .timeZone(.specificName(.short)))
    }

    /// A card line as VoiceOver reads it: the separators become pauses.
    static func spokenList(_ text: String, separator: String = ", ") -> String {
        text.replacingOccurrences(of: " · ", with: separator)
    }

    static let noNumber = "No chance to show right now"

    /// The link Share sends for the same item.
    static func url(for subject: SavedWidgetSubject10875) -> URL? {
        URL(string: subject.kind == .game ? eventShareURL(subject.id) : futuresShareURL(subject.id))
    }

    /// The item a message's link names: the website's own game or market link,
    /// or the app's. Anything else is not a Bain Luck card.
    static func subject(from url: URL) -> SavedWidgetSubject10875? {
        let parts: [String]
        switch url.scheme?.lowercased() {
        case "https"?, "http"?:
            guard let host = url.host?.lowercased(), host == "bainluck.com" || host == "www.bainluck.com"
            else { return nil }
            parts = url.pathComponents.filter { $0 != "/" }
        case "bainluck"?:
            parts = [url.host].compactMap { $0 } + url.pathComponents.filter { $0 != "/" }
        default:
            return nil
        }
        guard parts.count == 2, let id = Int(parts[1]), id > 0 else { return nil }
        switch parts[0] {
        case "events": return SavedWidgetSubject10875(kind: .game, id: id)
        case "futures": return SavedWidgetSubject10875(kind: .market, id: id)
        default: return nil
        }
    }
}

/// What the extension draws.
enum MessageScreen12308: Equatable {
    /// The reader's saved games and markets, to send one.
    case picker
    /// One item's current reading, opened from a card in the thread.
    case card(SavedWidgetSubject10875)

    /// A card tapped in the thread opens that item's current reading. The app
    /// drawer, or a link that is not a Bain Luck game or market, opens the
    /// picker rather than a card for something else.
    static func screen(expanded: Bool, selected url: URL?) -> MessageScreen12308 {
        guard expanded, let subject = url.flatMap(MessageCardRules12308.subject(from:)) else { return .picker }
        return .card(subject)
    }
}

/// What one item's card shows after a read, by the saved-item widget's rules
/// (``SavedWidgetTimeline10875``): a market answered under another id is
/// refused, "not found" means the item is gone, and any other failure keeps a
/// card already drawn rather than blanking it.
enum MessageCardReading12308: Equatable {
    case loading
    case card(MessageCard12308)
    case gone
    case unreachable

    static func after(_ fetched: Result<Data, SavedWidgetFetchError10875>,
                      for subject: SavedWidgetSubject10875,
                      previous: MessageCardReading12308?,
                      now: Date = Date()) -> MessageCardReading12308 {
        switch fetched {
        case .success(let data):
            guard let payload = try? SavedWidgetDetailPayload10875.decode(data, as: subject.kind),
                  SavedWidgetTimeline10875.answers(subject, with: payload),
                  let card = MessageCardRules12308.card(payload, now: now)
            else { return kept(previous) }
            return .card(card)
        case .failure(.notFound):
            return .gone
        case .failure(.failed):
            return kept(previous)
        }
    }

    private static func kept(_ previous: MessageCardReading12308?) -> MessageCardReading12308 {
        if case .card(let card)? = previous { return .card(card) }
        return .unreachable
    }
}
