import SwiftUI
import WidgetKit

// #10875 — one saved game or market, chosen per widget, on the Home Screen
// (small, medium) and the iPhone Lock Screen (rectangular, circular). The
// general live-games widget is unchanged beside it.

struct SavedItemWidgetEntry10875: TimelineEntry {
    let date: Date
    let selection: SavedWidgetSelection10875?
    let content: SavedWidgetContent10875

    /// The reading at this entry's own date, when there is a detail.
    var reading: SavedWidgetReading10875? {
        guard case .detail(let payload, _) = content, let selection else { return nil }
        return SavedWidgetTimeline10875.reading(payload, selection: selection, at: date)
    }

    var isOffline: Bool {
        if case .detail(_, let offline) = content { return offline }
        return false
    }

    /// Where a tap goes: the chosen item's own detail whenever it is the
    /// reader's saved item, otherwise My Stuff, where saved items are managed.
    var url: URL? {
        switch content {
        case .detail, .unreachable:
            return selection?.subject.url
        case .notConfigured, .openApp, .otherAccount, .removed, .gone:
            return URL(string: "bainluck://my-stuff")
        }
    }
}

struct SavedItemWidgetProvider10875: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> SavedItemWidgetEntry10875 {
        // Drawn redacted by the system; never read as a number.
        SavedItemWidgetEntry10875(date: Date(), selection: nil, content: .notConfigured)
    }

    func snapshot(for configuration: SelectSavedItemIntent10875, in context: Context) async -> SavedItemWidgetEntry10875 {
        if context.isPreview && configuration.selection == nil {
            return SavedItemWidgetEntry10875(date: Date(), selection: nil, content: .notConfigured)
        }
        return await entry(for: configuration.selection, at: Date())
    }

    func timeline(for configuration: SelectSavedItemIntent10875, in context: Context) async -> Timeline<SavedItemWidgetEntry10875> {
        let now = Date()
        let selection = configuration.selection
        let first = await entry(for: selection, at: now)
        let entries = SavedWidgetTimeline10875.entryDates(first.content, selection: selection, now: now)
            .map { SavedItemWidgetEntry10875(date: $0, selection: selection, content: first.content) }
        let next = SavedWidgetTimeline10875.nextRequest(first.content, selection: selection, now: now)
        return Timeline(entries: entries, policy: .after(next))
    }

    private func entry(for selection: SavedWidgetSelection10875?, at date: Date) async -> SavedItemWidgetEntry10875 {
        let content = await SavedWidgetTimeline10875.resolve(
            selection,
            readBridge: { SavedItemWidgetFetch10875.bridge },
            fetch: { try await SavedItemWidgetFetch10875.data(for: $0) },
            cache: SavedItemWidgetFetch10875.cache)
        return SavedItemWidgetEntry10875(date: date, selection: selection, content: content)
    }
}

struct SavedItemWidget10875: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: SavedWidgetBridge10875.widgetKind,
                               intent: SelectSavedItemIntent10875.self,
                               provider: SavedItemWidgetProvider10875()) { entry in
            SavedItemWidgetView10875(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
                .widgetURL(entry.url)
        }
        .configurationDisplayName("Saved game or market")
        .description("Follow one of your saved games or markets.")
        .supportedFamilies(Self.families)
    }

    static var families: [WidgetFamily] {
        #if os(iOS)
        [.systemSmall, .systemMedium, .accessoryRectangular, .accessoryCircular]
        #else
        // Mac is paused for #10875: the desktop sizes compile, nothing is claimed.
        [.systemSmall, .systemMedium]
        #endif
    }
}

// MARK: - Views

struct SavedItemWidgetView10875: View {
    @Environment(\.widgetFamily) private var family
    let entry: SavedItemWidgetEntry10875

    var body: some View {
        Group {
            if let reading = entry.reading {
                switch family {
                #if os(iOS)
                case .accessoryCircular: SavedCircular10875(reading: reading)
                case .accessoryRectangular: SavedRectangular10875(reading: reading, entry: entry)
                #endif
                case .systemMedium: SavedMedium10875(reading: reading, entry: entry)
                default: SavedSmall10875(reading: reading, entry: entry)
                }
            } else {
                SavedMessage10875(message: SavedWidgetMessage10875(entry.content), family: family)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        guard let reading = entry.reading else { return SavedWidgetMessage10875(entry.content).spoken }
        let clock = SavedClock10875.text(reading.observedAt, relativeTo: entry.date).map { " Recorded \($0)." } ?? ""
        return reading.spoken + clock + (entry.isOffline ? " Not updated: Bain Luck couldn't be reached." : "")
    }
}

/// The observation clock, absolute so it never goes stale on a Home Screen:
/// "3:42 PM" today, "Oct 15, 3:42 PM" otherwise.
enum SavedClock10875 {
    static func text(_ date: Date?, relativeTo now: Date) -> String? {
        guard let date else { return nil }
        if Calendar.current.isDate(date, inSameDayAs: now) {
            return date.formatted(date: .omitted, time: .shortened)
        }
        return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }

    /// The caption line under a price: its phase and clock, or what is missing.
    static func caption(_ reading: SavedWidgetReading10875, entry: SavedItemWidgetEntry10875) -> String? {
        // R3: a reading with no clock (a settled game) says only "Offline",
        // never a stand-in phrase for a time it does not have.
        if entry.isOffline { return text(reading.observedAt, relativeTo: entry.date).map { "Offline · \($0)" } ?? "Offline" }
        switch reading.phase {
        case .current:
            return text(reading.observedAt, relativeTo: entry.date).map { "As of \($0)" }
        case .lastRecorded:
            return "Last recorded " + (text(reading.observedAt, relativeTo: entry.date) ?? "· time unknown")
        case .openingLine:
            return "Opening line"
        case .noResult:
            // #698: a settled row whose result is unknown names its last price
            // as last recorded, with that price's own clock when it has one.
            return reading.lastRecordedFigure.map { figure in
                "Last recorded \(figure)" + (text(reading.observedAt, relativeTo: entry.date).map { " · \($0)" } ?? "")
            }
        case .result, .unavailable:
            return nil
        }
    }
}

private struct SavedValue10875: View {
    let row: SavedWidgetReading10875.Row?
    let size: CGFloat

    var body: some View {
        if let verdict = row?.verdict {
            Text(verdict)
                .font(.system(size: size * 0.75, weight: .bold))
                .foregroundStyle(row?.emphasized == true ? Color.green : Color.secondary)
                .lineLimit(2)
                .minimumScaleFactor(0.5)
        } else if let figure = row?.figure {
            Text(figure)
                .font(.system(size: size, weight: .bold).monospacedDigit())
                .minimumScaleFactor(0.6)
        } else {
            Text("—")
                .font(.system(size: size * 0.75, weight: .semibold))
                .foregroundStyle(.secondary)
                .accessibilityLabel("No number")
        }
    }
}

struct SavedSmall10875: View {
    let reading: SavedWidgetReading10875
    let entry: SavedItemWidgetEntry10875

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(reading.subject)
                .font(.caption.weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 0)
            if let headline = reading.headline {
                Text(headline.label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                SavedValue10875(row: headline, size: 30)
            } else {
                Text(reading.phase == .noResult ? "No result recorded" : "No chance to show")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            Text(SavedClock10875.caption(reading, entry: entry) ?? reading.status)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

struct SavedMedium10875: View {
    let reading: SavedWidgetReading10875
    let entry: SavedItemWidgetEntry10875

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(reading.subject)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(2)
                Spacer(minLength: 4)
                Text(reading.status)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            ForEach(Array(reading.rows.enumerated()), id: \.offset) { _, row in
                HStack {
                    Text(row.label)
                        .font(.footnote.weight(row.emphasized ? .semibold : .regular))
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    if let figure = row.figure {
                        Text(figure).font(.footnote.weight(.semibold).monospacedDigit())
                    }
                    if let verdict = row.verdict {
                        Text(verdict)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(row.emphasized ? Color.green : Color.secondary)
                    }
                    if row.figure == nil && row.verdict == nil {
                        Text("—").font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            if let caption = SavedClock10875.caption(reading, entry: entry) {
                Text(reading.priceCaption.map { "\($0) · \(caption)" } ?? caption)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

#if os(iOS)
struct SavedRectangular10875: View {
    let reading: SavedWidgetReading10875
    let entry: SavedItemWidgetEntry10875

    var body: some View {
        if let verdict = ownLineVerdict {
            // R2: the rectangle holds three lines. A verdict that fits one
            // keeps subject / verdict / footer; one that needs two
            // ("Akita Northern Happinets wins") takes them, and the footer
            // rides the subject line instead of cutting the verdict short.
            ViewThatFits(in: .vertical) {
                VStack(alignment: .leading, spacing: 1) {
                    subjectLine
                    ownLine(verdict)
                    footerLine
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 0) {
                        // R2a: the subject wins the width. Offline, the
                        // footer is "Offline · Oct 15, 3:42 PM" and would
                        // otherwise push the game off its own line.
                        subjectLine
                            .layoutPriority(1)
                        Text(" · \(footer)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    ownLine(verdict)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        } else {
            stacked
        }
    }

    private var subjectLine: some View {
        Text(reading.shortSubject)
            .font(.headline)
            .lineLimit(1)
            .widgetAccentable()
    }

    // R1: longer than Won / Lost / Draw, so not squeezed beside the outcome
    // name; the name moves to the footer.
    private func ownLine(_ verdict: String) -> some View {
        Text(verdict)
            .font(.body.weight(.semibold))
            .lineLimit(2)
            .minimumScaleFactor(0.7)
    }

    private var footerLine: some View {
        Text(footer)
            .font(.caption2)
            .foregroundStyle(.secondary)
            .lineLimit(1)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 1) {
            subjectLine
            if let headline = reading.headline, reading.phase == .unavailable, let notice = headline.verdict {
                // The chosen outcome is gone: say that, once, on its own line.
                Text(notice).font(.body.weight(.semibold)).lineLimit(1)
            } else if let headline = reading.headline {
                HStack(spacing: 4) {
                    Text(headline.shortLabel).lineLimit(1)
                    Spacer(minLength: 2)
                    Text(headline.verdict ?? headline.figure ?? "—")
                        .font(.body.weight(.semibold).monospacedDigit())
                }
            } else {
                Text(reading.phase == .noResult ? "No result recorded" : "No chance to show").lineLimit(1)
            }
            footerLine
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var ownLineVerdict: String? { SavedLockScreenFit10875.rectangleOwnLineVerdict(reading) }

    private var footer: String {
        let caption = SavedClock10875.caption(reading, entry: entry) ?? reading.status
        return ownLineVerdict == nil ? caption : SavedLockScreenFit10875.rectangleFooter(reading, caption: caption)
    }
}

struct SavedCircular10875: View {
    let reading: SavedWidgetReading10875

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            VStack(spacing: 0) {
                // The name the number belongs to, shortest form, so the
                // percentage is never shown without its subject.
                Text(reading.headline?.shortLabel ?? reading.shortSubject)
                    .font(.system(size: 9, weight: .semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                // R1: a figure or a word of at most 7 letters, never a
                // truncated sentence ("Result unk…").
                Text(SavedLockScreenFit10875.ringValue(reading))
                    .font(.system(size: 15, weight: .bold).monospacedDigit())
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                    .widgetAccentable()
            }
            .padding(4)
        }
    }
}
#endif

struct SavedMessage10875: View {
    let message: SavedWidgetMessage10875
    let family: WidgetFamily

    var body: some View {
        switch family {
        #if os(iOS)
        case .accessoryCircular:
            ZStack {
                AccessoryWidgetBackground()
                Image(systemName: "bookmark")
                    .font(.title3)
                    .accessibilityLabel(message.title)
            }
        case .accessoryRectangular:
            VStack(alignment: .leading, spacing: 1) {
                Text(message.title).font(.headline).lineLimit(2)
                Text(message.detail).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        #endif
        default:
            VStack(alignment: .leading, spacing: 4) {
                Image(systemName: "bookmark").foregroundStyle(.secondary)
                Text(message.title).font(.footnote.weight(.semibold)).lineLimit(3)
                Text(message.detail).font(.caption2).foregroundStyle(.secondary).lineLimit(3)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}
