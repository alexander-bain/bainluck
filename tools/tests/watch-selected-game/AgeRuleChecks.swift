import Foundation
import SwiftUI

/// #12316: for the same reading, the face and the Smart Stack card print the same whole number
/// of minutes (then hours, then days) at every moment. Both follow `WatchRectangularReading.wholeAge`:
/// whole units from the reading's own observation time, rounded down. The card's words are drawn
/// by watchOS from `liveAgeFormat` as time passes, so this runs that format at every second of
/// the first three hours and around each day boundary.
@MainActor func runSharedAgeRuleChecks() throws {
    guard #available(macOS 15.0, *) else { preconditionFailure("The card's age format needs macOS 15 to check") }
    typealias Unit = WatchRectangularReading.AgeUnit
    let observed = Date(timeIntervalSince1970: 1_800_000_000)
    let card = WatchRectangularReading.liveAgeFormat(observedAt: observed).locale(Locale(identifier: "en_US"))

    func unit(_ word: Substring) -> Unit? {
        if word.hasPrefix("minute") { return .minute }
        if word.hasPrefix("hour") { return .hour }
        if word.hasPrefix("day") { return .day }
        return nil
    }
    /// "0 minutes", "1 minute", "2 hours", "1 day".
    func cardAge(_ text: String) -> (Int, Unit)? {
        let parts = text.split(separator: " ")
        guard parts.count == 2, let count = Int(parts[0]), let unit = unit(parts[1]) else { return nil }
        return (count, unit)
    }
    /// "<1m ago", "1m ago", "3h ago", "2d ago".
    func faceAge(_ text: String) -> (Int, Unit)? {
        if text == "<1m ago" { return (0, .minute) }
        guard text.hasSuffix(" ago"), let last = text.dropLast(4).last, let count = Int(text.dropLast(5)) else { return nil }
        switch last {
        case "m": return (count, .minute)
        case "h": return (count, .hour)
        case "d": return (count, .day)
        default: return nil
        }
    }
    /// "less than 1 minute ago", "1 minute ago", "5 minutes ago", "1 hour ago".
    func spokenAge(_ text: String) -> (Int, Unit)? {
        if text == "less than 1 minute ago" { return (0, .minute) }
        let parts = text.split(separator: " ")
        guard parts.count == 3, parts[2] == "ago", let count = Int(parts[0]), let unit = unit(parts[1]) else { return nil }
        return (count, unit)
    }

    var moments = Array(stride(from: 0.0, through: 3 * 3600, by: 1))
    moments += [0.5, 29.999, 30, 59.999, 89.5, 90, 119.999, 149.5, 179.999, 3599.999, 5399, 5400,
                86_399, 86_399.999, 86_400, 86_401, 129_600, 172_799, 172_800, 600_000]
    for seconds in moments {
        let now = observed.addingTimeInterval(seconds)
        let rule = WatchRectangularReading.wholeAge(observedAt: observed, now: now)!
        let cardText = String(card.format(now).characters)
        let faceText = WatchRectangularReading.compactAge(observedAt: observed, now: now)!
        let spokenText = WatchRectangularReading.spokenAge(observedAt: observed, now: now)!
        precondition(cardAge(cardText).map { $0 == rule } == true,
                     "At \(seconds) s the card says \(cardText) ago but the rule says \(rule.count) \(rule.unit)")
        precondition(faceAge(faceText).map { $0 == rule } == true,
                     "At \(seconds) s the face says \(faceText) but the rule says \(rule.count) \(rule.unit)")
        precondition(spokenAge(spokenText).map { $0 == rule } == true,
                     "At \(seconds) s the spoken age is \(spokenText) but the rule says \(rule.count) \(rule.unit)")
    }
    // The moments that used to disagree, in the words a reader sees.
    for (seconds, face, cardWords) in [(45.0, "<1m ago", "0 minutes"), (95, "1m ago", "1 minute"),
                                       (165, "2m ago", "2 minutes"), (3599, "59m ago", "59 minutes"),
                                       (5399, "1h ago", "1 hour"), (86_399, "23h ago", "23 hours"),
                                       (86_400, "1d ago", "1 day")] {
        let now = observed.addingTimeInterval(seconds)
        precondition(WatchRectangularReading.compactAge(observedAt: observed, now: now) == face
                     && String(card.format(now).characters) == cardWords,
                     "At \(seconds) s: face \(face), card \(cardWords) ago")
    }
    // A future or non-finite observation has no age in either kind.
    for bad in [observed.addingTimeInterval(1), Date(timeIntervalSinceReferenceDate: .nan)] {
        precondition(WatchRectangularReading.wholeAge(observedAt: bad, now: observed) == nil
                     && WatchRectangularReading.compactAge(observedAt: bad, now: observed) == nil)
    }
    print("PASS: one age rule for the face and the Smart Stack card: whole minutes, hours and days from the reading's own time, rounded down, the same number at every second for three hours and at the day boundaries (\(moments.count) moments)")
}
