import SwiftUI
import AppKit

import Foundation

/// #12581 / 137-A — where a served probability came from, as the server says it.
///
/// The SERVER owns every part of this: which sources contributed, their order,
/// their prices and when each was observed. The app draws it and never works a
/// source out, orders one or fills one in (137-A: "don't infer a source in the
/// app"). The shape is #12581's:
///
/// ```
/// "source_mark": {
///   "state": "blend" | "single" | "settled" | "none",
///   "sources": [{"key", "name", "probability", "observed_at", "count"?}],
///   "settled": {"source", "result", "at"},
///   "method"?: "<short calculation name>"
/// }
/// ```
///
/// Every field decodes leniently (gotcha #42): one unreadable source drops that
/// source, never the prop row it rides on, and an unknown `state` reads as
/// ``State/unknown``, which draws no mark.
nonisolated struct SourceMark: Decodable, Equatable, Sendable {
    enum State: Equatable, Sendable { case blend, single, settled, none, unknown }

    nonisolated struct Source: Decodable, Equatable, Sendable {
        let key: String
        let name: String
        let probability: Double?
        /// When THIS source's price was observed (#12581), not when the row was polled.
        let observedAt: String?
        /// Sportsbooks only: how many books the line stands for.
        var count: Int? = nil
    }

    nonisolated struct Settled: Decodable, Equatable, Sendable {
        let source: String?
        let result: String?
        let at: String?
    }

    let state: State
    let sources: [Source]
    let settled: Settled?
    let method: String?

    init(state: State, sources: [Source], settled: Settled? = nil, method: String? = nil) {
        self.state = state
        self.sources = sources
        self.settled = settled
        self.method = method
    }

    private enum CodingKeys: String, CodingKey { case state, sources, settled, method }

    /// Decodes `[Source]` element by element so one bad entry drops alone.
    private struct Lenient<T: Decodable>: Decodable {
        let value: T?
        init(from decoder: Decoder) throws { value = try? T(from: decoder) }
    }

    init(from decoder: Decoder) throws {
        // Not an object at all: no mark, and the row it rides on still decodes.
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else {
            state = .unknown; sources = []; settled = nil; method = nil
            return
        }
        switch (try? c.decodeIfPresent(String.self, forKey: .state)) ?? nil {
        case "blend": state = .blend
        case "single": state = .single
        case "settled": state = .settled
        case "none": state = .none
        default: state = .unknown
        }
        sources = ((try? c.decodeIfPresent([Lenient<Source>].self, forKey: .sources)) ?? nil)?
            .compactMap(\.value) ?? []
        settled = (try? c.decodeIfPresent(Settled.self, forKey: .settled)) ?? nil
        method = (try? c.decodeIfPresent(String.self, forKey: .method)) ?? nil
    }

    /// Does this mark draw at all? Only when the sheet would have something to
    /// say: a blend or single-venue mark with at least one source, or a settled
    /// result. "none", an unknown state and an empty mark draw nothing — never
    /// an empty sheet.
    var draws: Bool {
        switch state {
        case .blend, .single: return !sources.isEmpty
        case .settled: return settled != nil || !sources.isEmpty
        case .none, .unknown: return false
        }
    }
}

import Foundation

/// #8651 — the one stamp shape the server writes, parsed by hand.
///
/// `String.asDate` sits under every chart, freshness check and reconciliation
/// on a game page, and a page body re-runs on every update the page takes in.
/// `ISO8601DateFormatter` costs ~37 µs a stamp on a Mac, and the stamps the server
/// actually sends (`2026-10-01T23:40:00+00:00`, no fraction, 16,419 of 18,032
/// on Steelers–Browns 14780550's history) missed the fractional formatter
/// first and were parsed twice. Measured on that game's two payloads, 22,984
/// stamps: 865 ms through the formatters, 0.6 ms here.
///
/// This is a FAST PATH, not a second parser. It accepts only
/// `YYYY-MM-DDTHH:MM:SS[.fraction](Z|±HH:MM)` with every field in range and
/// returns `nil` for anything else, so the caller falls through to the
/// formatters and gets exactly what it got before. For what it does accept it
/// returns the formatter's value bit for bit — including the formatter's
/// truncation of the fraction to whole milliseconds. The formatter's lenient
/// cases (Feb 29 in a common year, `24:00`, `+0000`) are deliberately NOT
/// accepted; they take the formatter path and keep its answer.
nonisolated enum ISO8601Stamp {
    static func date(_ stamp: String) -> Date? {
        var stamp = stamp
        return stamp.withUTF8 { parse($0) }
    }

    private static func parse(_ b: UnsafeBufferPointer<UInt8>) -> Date? {
        let n = b.count
        guard n >= 20,
              b[4] == UInt8(ascii: "-"), b[7] == UInt8(ascii: "-"), b[10] == UInt8(ascii: "T"),
              b[13] == UInt8(ascii: ":"), b[16] == UInt8(ascii: ":"),
              let century = twoDigits(b, 0), let yy = twoDigits(b, 2),
              let month = twoDigits(b, 5), let day = twoDigits(b, 8),
              let hour = twoDigits(b, 11), let minute = twoDigits(b, 14),
              let second = twoDigits(b, 17) else { return nil }
        let year = century * 100 + yy
        guard (1...12).contains(month), day >= 1, day <= daysIn(month: month, year: year),
              hour <= 23, minute <= 59, second <= 59 else { return nil }

        var i = 19
        var milliseconds = 0
        if b[i] == UInt8(ascii: ".") {
            i += 1
            var digits = 0
            while i < n, b[i] >= UInt8(ascii: "0"), b[i] <= UInt8(ascii: "9") {
                // The formatter keeps whole milliseconds and drops the rest.
                if digits < 3 { milliseconds = milliseconds * 10 + Int(b[i] - UInt8(ascii: "0")) }
                digits += 1
                i += 1
            }
            guard digits > 0 else { return nil }
            for _ in digits..<max(digits, 3) { milliseconds *= 10 }
        }

        guard i < n else { return nil }
        var offset = 0
        if b[i] == UInt8(ascii: "Z") {
            i += 1
        } else if b[i] == UInt8(ascii: "+") || b[i] == UInt8(ascii: "-") {
            guard i + 6 == n, b[i + 3] == UInt8(ascii: ":"),
                  let offsetHours = twoDigits(b, i + 1), let offsetMinutes = twoDigits(b, i + 4),
                  offsetHours <= 23, offsetMinutes <= 59 else { return nil }
            offset = (offsetHours * 3600 + offsetMinutes * 60) * (b[i] == UInt8(ascii: "+") ? 1 : -1)
            i += 6
        } else {
            return nil
        }
        guard i == n else { return nil }

        let seconds = daysFromCivil(year: year, month: month, day: day) * 86_400
            + hour * 3600 + minute * 60 + second - offset
        return Date(timeIntervalSince1970: Double(seconds) + Double(milliseconds) / 1000)
    }

    private static func twoDigits(_ b: UnsafeBufferPointer<UInt8>, _ i: Int) -> Int? {
        let tens = Int(b[i]) - 48, ones = Int(b[i + 1]) - 48
        guard (0...9).contains(tens), (0...9).contains(ones) else { return nil }
        return tens * 10 + ones
    }

    private static func daysIn(month: Int, year: Int) -> Int {
        switch month {
        case 2: return (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 ? 29 : 28
        case 4, 6, 9, 11: return 30
        default: return 31
        }
    }

    /// Days since 1970-01-01 in the proleptic Gregorian calendar (Howard
    /// Hinnant's `days_from_civil`).
    private static func daysFromCivil(year: Int, month: Int, day: Int) -> Int {
        let y = month <= 2 ? year - 1 : year
        let era = (y >= 0 ? y : y - 399) / 400
        let yearOfEra = y - era * 400
        let dayOfYear = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1
        let dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
        return era * 146_097 + dayOfEra - 719_468
    }
}

extension String {
    /// Parse an ISO 8601 date string into a Date.
    /// Handles both with and without fractional seconds.
    ///
    /// #8651 — the server's own shape takes `ISO8601Stamp`'s fast path (same
    /// value, ~1,000× cheaper); anything it declines gets the formatters, as
    /// before.
    var asDate: Date? {
        ISO8601Stamp.date(self)
            ?? Self.iso8601FracFormatter.date(from: self)
            ?? Self.iso8601Formatter.date(from: self)
    }

    /// The formatters alone, without the fast path — the reference
    /// `ISO8601Stamp` is tested against.
    var asDateByFormatter: Date? {
        Self.iso8601FracFormatter.date(from: self)
            ?? Self.iso8601Formatter.date(from: self)
    }

    private static let iso8601FracFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let iso8601Formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
}

// MARK: - AnyCodable (used by FeedModels + SearchModels)

nonisolated enum AnyCodable: Decodable, Sendable {
    case int(Int)
    case double(Double)
    case string(String)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Int.self) { self = .int(v) }
        else if let v = try? container.decode(Double.self) { self = .double(v) }
        else if let v = try? container.decode(String.self) { self = .string(v) }
        else if let v = try? container.decode(Bool.self) { self = .bool(v) }
        else { self = .null }
    }

    var stringValue: String {
        switch self {
        case .int(let v): return "\(v)"
        case .double(let v): return "\(v)"
        case .string(let v): return v
        case .bool(let v): return v ? "true" : "false"
        case .null: return ""
        }
    }
}

import Foundation

/// `renderedPercent` overrides the INTEGER, not the rule.
///
/// UX-P114: a card printing two sides of one question decides both percents
/// together, or the two independently-correct numbers sum to 101 (see
/// `renderedDuelPercents` and `contracts/rendered_percent.json`). Callers that
/// hold the server's card-level integer pass it here instead of rounding again.
///
/// The `<1%` / `>99%` guards still run on the PROBABILITY, because they are a
/// claim about the value rather than about which arithmetic produced the integer.
func formatProbability(_ value: Double, renderedPercent: Int? = nil) -> String {
    let pct = value * 100
    if pct < 1 || (renderedPercent == 0 && value > 0) { return "<1%" }
    if pct > 99 { return ">99%" }
    if let renderedPercent { return "\(renderedPercent)%" }
    return "\(Int(pct.rounded()))%"
}


import Foundation

/// HOW OLD IS THE PRICE BEHIND THIS NUMBER — the native half (#6343).
///
/// ═══ THE MIRROR PAIR ═══
///
/// Same arrangement `LiquidityMarkView` documents at the top of its own file,
/// and the same reason: two drawings of one signal drift.
///
///   the rungs + the bounds -> frontend/lib/sourceAge.ts
///   the chip              -> frontend/components/event/PriceAgeMark.tsx
///   the native chip       -> Components/PriceAgeMarkView.swift
///
/// ═══ WHY THIS EXISTS: THE PHONE COULD NOT SAY IT AT ALL ═══
///
/// 🔴 #6343. `price_observed_at` has been on both futures-card serializers since
/// #5752 (`routes/feed.py`), the web has drawn it since #4970, and
/// `grep -rn price_observed_at ios/` returned **0 hits** — so no native surface
/// could render an age even in principle. Measured against `/api/feed?limit=25`
/// on 2026-09-15 09:5xZ: market `171` ("Canadian Team to Win the Stanley Cup")
/// at **77.7h** and `60856903` (a PGA second-round ladder) at **59.2h** were
/// drawing prices from three and two days earlier, marked `● 3d ago` / `● 2d ago`
/// on the website and completely unmarked on the phone.
///
/// ═══ IT DRAWS NOTHING ALMOST ALL OF THE TIME, AND THAT IS THE FEATURE ═══
///
/// The bound is the cadence that SHOULD have replaced the price, and picking the
/// wrong end of it is the defect #5843 fixed on the web. In the same read above,
/// **14 of the 16** datable cards sat at 0.7h: under the 30-minute live bound all
/// sixteen would have drawn a mark within the hour and the mark would say nothing
/// about the two that matter. Under the futures bound, **2 of 16** draw — and they
/// are the two a reader should see. An age has value exactly when it is surprising.
///
/// ═══ NO SECOND VOCABULARY ON THIS PLATFORM ═══
///
/// The rungs are `formatAgeFromSeconds`' rungs, value for value. Two deliberate
/// divergences from the web, both so the PHONE reads as one product — named here
/// so a later reader does not "correct" them into a third spelling:
///
///  1. **The precise stamp is `Liquidity.preciseObservedAt`**, not a local copy of
///     web's `formatSourceStamp`. The two differ only in field order ("12 Sep,
///     3:51 AM" vs "Sep 12, 3:51 AM") and native already shipped the first one in
///     the illiquidity reveal. It is *called*, not re-implemented, so the platform
///     has exactly one precise-stamp formatter.
///  2. **The reveal stem is "Last number"**, which is what both native surfaces
///     that date a price already say (`Liquidity.reveal`, and
///     `TournamentHubPresentation`'s "Last number 45 hours ago"), rather than
///     web's "Last seen". It is also the more accurate word: we do not receive
///     trades, and the stamp is when a probability last reached us.
///
/// The SHORT rungs ("3d ago") are kept for the chip even though the tournament
/// hub spells its sentence long ("3 days ago"), and that split is the web's own:
/// a dense chip beside a source mark and a full-width prose note are different
/// registers. The hub's note is a sentence; this is a mark.
///
/// ═══ `now` IS AN ARGUMENT ═══
///
/// Gotcha #44. A guard pins "7 hours draws, 5 does not" at a fixed instant rather
/// than building stamps relative to whenever the suite happens to run.
nonisolated enum SourceAge {

    // MARK: - The two bounds

    /// Sportsbook rows and live blocks, restamped every 2 minutes by
    /// `poll_live_prediction_markets`. Mirrors web's `SOURCE_STALE_AFTER_MS`,
    /// which is itself lifted from `BookmakerTable`.
    static let liveStaleAfter: TimeInterval = 30 * 60

    /// The hourly-polled ladders. The backend's own number, not one tuned here:
    /// `utils/tournament_register.py` carries `STALE_PRICE_HOURS = 6.0` and
    /// `tasks/futures_price_refresh.py` cites it by name, so the producer and
    /// both renderers share one definition of stale rather than three.
    /// Mirrors web's `FUTURES_STALE_AFTER_MS`.
    static let futuresStaleAfter: TimeInterval = 6 * 60 * 60

    /// A named pair rather than a raw interval, for web's reason: a caller free
    /// to pass `45 * 60` is a caller free to invent a fourth definition of stale.
    enum Cadence: String, Sendable {
        case live
        case futures

        var staleAfter: TimeInterval {
            switch self {
            case .live: return SourceAge.liveStaleAfter
            case .futures: return SourceAge.futuresStaleAfter
            }
        }
    }

    // MARK: - Reading a stamp

    /// Seconds since `iso` was written, or nil when there is no readable stamp.
    ///
    /// 🔴 ABSENT IS NOT ZERO. A price we have never observed must not read as one
    /// observed a moment ago, so both absences return nil and the caller decides
    /// what to draw (which, for the mark, is nothing). `String.asDate` handles the
    /// stamp with fractional seconds and the one without — production serves both.
    static func ageSeconds(_ iso: String?, now: Date = Date()) -> TimeInterval? {
        guard let iso, let at = iso.asDate else { return nil }
        // Clamped, like web's `sourceAgeMs`: a stamp from the future is a clock
        // disagreement, not a negative age, and flooring it below would wrap.
        return max(0, now.timeIntervalSince(at))
    }

    /// "just now" / "3m ago" / "2h ago" / "yesterday" / "5d ago".
    ///
    /// Value for value with web's `formatAgeFromSeconds`, including the two rungs
    /// that are words rather than numbers. There is no seconds rung, for its
    /// reason: under a minute, "just now" is the honest reading everywhere.
    static func formatAge(seconds: TimeInterval) -> String {
        // Truncation equals floor here because `ageSeconds` clamps at zero.
        let mins = Int(seconds / 60)
        let hours = Int(seconds / 3600)
        let days = Int(seconds / 86_400)

        if mins < 1 { return "just now" }
        if mins < 60 { return "\(mins)m ago" }
        if hours < 24 { return "\(hours)h ago" }
        if days == 1 { return "yesterday" }
        return "\(days)d ago"
    }

    /// The rendered age for a stamp, or nil when it cannot be dated.
    static func format(_ iso: String?, now: Date = Date()) -> String? {
        guard let seconds = ageSeconds(iso, now: now) else { return nil }
        return formatAge(seconds: seconds)
    }


}

import SwiftUI

/// #12581 / 137-A — the source mark (Alex, Nov 3, recorded on #11920; the glyph
/// is the ⓘ ring, 139-A, Nov 11): one quiet ⓘ after a number, the same on every
/// row whatever stands behind it. A tap opens "Where this number comes from".
///
/// The decision is the initialiser (the `PriceAgeMarkView` shape): nil when the
/// served mark has nothing to say, so "does this row draw a mark?" is a value a
/// test can assert.
struct SourceMarkButton: View {
    let mark: SourceMark
    /// The number the mark follows, as the row prints it; the sheet repeats it.
    let number: Double?
    /// The font size of the number the ring follows; the ring is 0.7 of it.
    let numberSize: CGFloat

    @State private var open = false

    /// The ring's share of the number's type size (Alex's ruling: about 0.7).
    static let ringScale: CGFloat = 0.7

    init?(_ mark: SourceMark?, number: Double? = nil, numberSize: CGFloat) {
        guard let mark, mark.draws else { return nil }
        self.mark = mark
        self.number = number
        self.numberSize = numberSize
    }

    var body: some View {
        Button { open = true } label: {
            Image(systemName: "info.circle")
                .font(.system(size: numberSize * Self.ringScale))
                .foregroundStyle(Color.secondary.opacity(0.55))
                // A 44pt tap target around a ring that stays quiet.
                .frame(minWidth: 28, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Where this number comes from")
        .accessibilityIdentifier("source-mark-12581")
        .sheet(isPresented: $open) {
            SourceMarkSheet(mark: mark, number: number)
                .presentationDetents([.medium, .large])
        }
    }
}

/// The sheet: the number the reader tapped, large and whole; one row per source
/// the server listed, in its order, with the source's name, its price as a whole
/// number and how old that price is (no age when the server sent no observation
/// time); then one line of method. A settled number says "Official result" first.
struct SourceMarkSheet: View {
    let mark: SourceMark
    var number: Double? = nil
    var now: Date = Date()
    @Environment(\.dismiss) private var dismiss

    static let title = "Where this number comes from"

    /// One source as the sheet prints it.
    struct Line: Equatable {
        let name: String
        let price: String?
        let age: String?
    }

    static func lines(_ mark: SourceMark, now: Date = Date()) -> [Line] {
        mark.sources.map { source in
            Line(name: source.count.map { "\(source.name) (\($0))" } ?? source.name,
                 price: source.probability.map { formatProbability($0) },
                 age: SourceAge.format(source.observedAt, now: now))
        }
    }

    /// The tapped number, clamped like the row (`formatProbability`: "<1%" / ">99%").
    static func headline(_ number: Double?) -> String? {
        number.map { formatProbability($0) }
    }

    /// One line of method under the rows. Multi-source blends print the
    /// server's `method` when present and non-empty, else "Bain Luck blend";
    /// one-source marks name that venue ("<Venue>'s price", 145-A).
    static func method(_ mark: SourceMark) -> String? {
        switch mark.state {
        case .blend where mark.sources.count > 1:
            let served = mark.method?.trimmingCharacters(in: .whitespacesAndNewlines)
            return (served?.isEmpty == false) ? served : "Bain Luck blend"
        case .blend, .single:
            return mark.sources.first.map { "\($0.name)'s price" }
        case .settled:
            return nil
        case .none, .unknown:
            return nil
        }
    }

    /// "Official result" and the result as served, for a settled number.
    static func settledLine(_ mark: SourceMark, now: Date = Date()) -> Line? {
        guard mark.state == .settled, let settled = mark.settled else { return nil }
        return Line(name: "Official result", price: settled.result, age: SourceAge.format(settled.at, now: now))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let headline = Self.headline(number) {
                        Text(headline)
                            .font(.system(size: 44, weight: .bold))
                            .monospacedDigit()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    rows
                    if let method = Self.method(mark) {
                        Text(method).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .padding()
            }
                .navigationTitle(Self.title)
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
    }

    /// The sheet's rows, the settled line first. Plain stacks rather than a
    /// `List`, so the rows are one view a fixture render can photograph.
    var rows: some View {
        let lines = (Self.settledLine(mark, now: now).map { [$0] } ?? []) + Self.lines(mark, now: now)
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                if index > 0 { Divider() }
                row(line).padding(.vertical, 12)
            }
        }
    }

    private func row(_ line: Line) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(line.name).font(.body)
            Spacer(minLength: 8)
            if let price = line.price {
                Text(price).font(.body.weight(.semibold)).monospacedDigit()
            }
            if let age = line.age {
                Text(age).font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
        }
        .accessibilityElement(children: .combine)
    }
}




struct RoundupPreview: Decodable {
 let rows: [Row]
 let cards: [Card]
 struct Row: Decodable { let label: String; let probability: Double; let sourceMark: SourceMark }
 struct Card: Decodable { let id: Int; let name: String; let topOutcomes: [Outcome] }
 struct Outcome: Decodable { let name: String; let probability: Double; let sourceMark: SourceMark }
}
@main struct RenderRoundup {
 @MainActor static func save<V: View>(_ content: V, to path: URL) throws {
  let renderer=ImageRenderer(content:content.padding(20).frame(width:390).background(Color.white).environment(\.colorScheme,.light)); renderer.scale=2
  guard let image=renderer.nsImage,let tiff=image.tiffRepresentation,let bitmap=NSBitmapImageRep(data:tiff),let png=bitmap.representation(using:.png,properties:[:]) else { fatalError("No render") }
  try png.write(to:path)
 }
 @MainActor static func main() throws {
  let root=URL(fileURLWithPath:"/Users/bain/bainluck-dev/builder-b-receipts/20261117-roundup-source-marks")
  let decoder=JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
  let preview=try decoder.decode(RoundupPreview.self,from:Data(contentsOf:root.appendingPathComponent("preview.json")))
  let selected=preview.rows.last!
  let roundup=VStack(alignment:.leading,spacing:18) {
   Text("NFL roundup · source marks").font(.headline)
   Text("Complete historical Nov 2 fixture · 16 source markets\nLocal contract preview, 390 pt").font(.caption).foregroundStyle(.secondary)
   ForEach([false,true],id:\.self) { after in
    VStack(alignment:.leading,spacing:12) {
     Text(after ? "After" : "Before").font(.caption).foregroundStyle(.secondary)
     Text("NFL division front-runners").font(.headline)
     ForEach(Array(preview.rows.enumerated()),id:\.offset) { _,row in
      HStack(alignment:.firstTextBaseline) {
       Text(row.label).fixedSize(horizontal:false,vertical:true)
       Spacer(minLength:8)
       Text(formatProbability(row.probability)).bold().monospacedDigit()
       if after { SourceMarkButton(row.sourceMark,number:row.probability,numberSize:17) }
      }
     }
    }.padding(14).background(Color.primary.opacity(0.035)).clipShape(RoundedRectangle(cornerRadius:12))
   }
   Divider()
   Text(selected.label).font(.subheadline).bold()
   Text(SourceMarkSheet.title).font(.headline)
   Text(SourceMarkSheet.headline(selected.probability)!).font(.system(size:40,weight:.bold)).monospacedDigit()
   SourceMarkSheet(mark:selected.sourceMark,number:selected.probability).rows
   if let method=SourceMarkSheet.method(selected.sourceMark) { Text(method).font(.footnote).foregroundStyle(.secondary) }
   Text("All 16 source markets were supplied. The same four divisions and values appear before and after. Ages are absent because these inputs have no price-bound observation witness. App integration remains with Builder C.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
  }
  try save(roundup,to:root.appendingPathComponent("roundup-source-marks-fixture-390.png"))
  let members=VStack(alignment:.leading,spacing:18) {
   Text("Roundup container · all members").font(.headline)
   Text("Complete historical Nov 2 fixture\nLocal contract preview, 390 pt").font(.caption).foregroundStyle(.secondary)
   ForEach(Array(preview.cards.enumerated()),id:\.offset) { _,card in
    VStack(alignment:.leading,spacing:10) {
     Text(card.name).font(.headline).fixedSize(horizontal:false,vertical:true)
     ForEach(Array(card.topOutcomes.enumerated()),id:\.offset) { _,row in
      HStack {
       Text(row.name); Spacer(minLength:8)
       Text(formatProbability(row.probability)).bold().monospacedDigit()
       SourceMarkButton(row.sourceMark,number:row.probability,numberSize:17)
      }
     }
    }.padding(14).background(Color.primary.opacity(0.035)).clipShape(RoundedRectangle(cornerRadius:12))
   }
   Text("All four outcomes on each selected division carry their own inputs. No field or outcome was removed for this preview.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
  }
  try save(members,to:root.appendingPathComponent("roundup-container-marks-fixture-390.png"))
 }
}
