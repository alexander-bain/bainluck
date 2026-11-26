import Foundation

/// Item 4 (#13551) — Deterministic VoiceOver spoken sentences for Kit v1 cards across all 4 layouts:
/// - Expands `%` to `" percent"` everywhere.
/// - Names the row/mark, what it is, the number with `" percent"`, and its place (`"k of n"`).
/// - Axis names both ends of the scale and states where each mark sits.
/// - Calendar reads the date, name, number (`" percent"`), and place (`"k of n"`).
/// - Never includes picture `"image"` traits; big headline (`commonHeadline`) reads first (`sortPriority = 10`).
nonisolated enum KitAccessibilitySpeech366B {

    /// Replaces `%` with `" percent"` cleanly while collapsing extra spaces.
    static func expandPercent(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return "" }
        s = s.replacingOccurrences(of: " %", with: "%")
        s = s.replacingOccurrences(of: "%", with: " percent")
        while s.contains("  ") {
            s = s.replacingOccurrences(of: "  ", with: " ")
        }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func cardHeadlineSpeech(spec: KitV1CardSpec) -> String {
        let primary = spec.commonHeadline?.trimmingCharacters(in: .whitespacesAndNewlines)
        let kicker = spec.kicker?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let primary, !primary.isEmpty {
            return expandPercent(primary)
        }
        return expandPercent(kicker ?? "")
    }

    static func footerSpeech(spec: KitV1CardSpec) -> String {
        let parts = [spec.disclosure, spec.footnote]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .map(expandPercent)
        if !parts.isEmpty {
            return parts.joined(separator: ", ") + "."
        }
        return "Open set."
    }

    // MARK: - Stack Row Speech

    static func stackRowSpeech(
        item: KitV1StackItem,
        index: Int,
        total: Int,
        spec: KitV1CardSpec,
        now: Date = Date()
    ) -> String {
        var names: [String] = []
        var details: [String] = []
        var numbers: [String] = []

        collectMarks(
            item.marks + (item.subMarks ?? []),
            now: now,
            inheritedDeadline: headerDeadlineIso(in: spec),
            names: &names,
            details: &details,
            numbers: &numbers
        )

        if names.isEmpty, let firstPic = item.marks.compactMap({ mark -> String? in
            if case .picture(let p) = mark { return p.alt }
            return nil
        }).first {
            names.append(expandPercent(firstPic))
        }

        let context = topicContext(for: spec)
        if details.isEmpty, let context {
            details.append(context)
        }

        return formatSentence(
            names: names,
            details: details,
            numbers: numbers,
            place: "\(index + 1) of \(max(1, total))"
        )
    }

    // MARK: - Grid Row & Cell Speech

    static func gridRowSpeech(
        row: KitV1GridRow,
        gridBody: KitV1GridBody,
        index: Int,
        total: Int,
        spec: KitV1CardSpec
    ) -> String {
        var names: [String] = []
        var details: [String] = []
        var numbers: [String] = []

        collectMarks(row.leading, names: &names, details: &details, numbers: &numbers)

        let colLookup = Dictionary(uniqueKeysWithValues: gridBody.columns.map { ($0.key, $0.label) })
        let orderedCells = gridBody.columns.compactMap { col -> (String, KitV1GridCell)? in
            guard let cell = row.cells.first(where: { $0.columnKey == col.key }) else { return nil }
            return (col.label, cell)
        }
        let pairs = orderedCells.isEmpty
            ? row.cells.map { (colLookup[$0.columnKey] ?? "", $0) }
            : orderedCells

        for (colLabel, cell) in pairs {
            var cNames: [String] = []
            var cDetails: [String] = []
            var cNumbers: [String] = []
            collectMarks(cell.marks, names: &cNames, details: &cDetails, numbers: &cNumbers)
            let cellParts = (cNumbers + cDetails + cNames)
                .map { expandPercent($0) }
                .filter { !$0.isEmpty }
            if !cellParts.isEmpty {
                let prefix = expandPercent(colLabel)
                if prefix.isEmpty {
                    numbers.append(cellParts.joined(separator: " "))
                } else {
                    numbers.append("\(prefix) \(cellParts.joined(separator: " "))")
                }
            }
        }

        if details.isEmpty, let context = topicContext(for: spec) {
            details.append(context)
        }

        return formatSentence(
            names: names,
            details: details,
            numbers: numbers,
            place: "\(index + 1) of \(max(1, total))"
        )
    }

    static func gridCellSpeech(
        row: KitV1GridRow,
        cell: KitV1GridCell,
        columnLabel: String,
        index: Int,
        total: Int,
        spec: KitV1CardSpec
    ) -> String {
        var names: [String] = []
        var details: [String] = []
        var numbers: [String] = []

        collectMarks(row.leading, names: &names, details: &details, numbers: &numbers)
        let expandedCol = expandPercent(columnLabel)
        let hasColumnLabel = !expandedCol.isEmpty
        if hasColumnLabel {
            details.insert(expandedCol, at: 0)
        }
        collectMarks(cell.marks, names: &names, details: &details, numbers: &numbers)

        let detailsWithoutColCount = hasColumnLabel ? details.count - 1 : details.count
        if detailsWithoutColCount <= 0, let context = topicContext(for: spec), !context.isEmpty {
            details.append(context)
        }

        return formatSentence(
            names: names,
            details: details,
            numbers: numbers,
            place: "\(index + 1) of \(max(1, total))"
        )
    }

    // MARK: - Axis Speech

    static func axisScaleSpeech(axisBody: KitV1AxisBody) -> String {
        let ticks = axisBody.scale.ticks
        let startLabel = ticks.first.map { expandPercent($0.label) } ?? formatAxisPosition(axisBody.scale.min, scale: axisBody.scale)
        let endLabel = ticks.last.map { expandPercent($0.label) } ?? formatAxisPosition(axisBody.scale.max, scale: axisBody.scale)
        var base = "Scale from \(startLabel) to \(endLabel)"
        if let band = axisBody.highlightBand {
            let lo = formatAxisPosition(band.lo, scale: axisBody.scale)
            let hi = formatAxisPosition(band.hi, scale: axisBody.scale)
            base += ", highlighted band \(expandPercent(band.label)) from \(lo) to \(hi)"
        }
        return base + "."
    }

    static func axisDotSpeech(
        dot: KitV1DotMark,
        axisBody: KitV1AxisBody,
        index: Int,
        total: Int,
        spec: KitV1CardSpec
    ) -> String {
        let rawLabel = dot.label.trimmingCharacters(in: .whitespacesAndNewlines)
        let namePart = rawLabel.isEmpty
            ? (dot.picture.map { expandPercent($0.alt) } ?? "Marker")
            : expandPercent(rawLabel)
        let position = formatAxisPosition(dot.x, scale: axisBody.scale)
        var whatItIs = topicContext(for: spec) ?? "axis marker"
        if let band = axisBody.highlightBand, dot.x >= band.lo && dot.x <= band.hi {
            whatItIs += " inside \(expandPercent(band.label))"
        }
        let sitting = "sits at \(position)"
        return "\(namePart), \(whatItIs), \(sitting), \(index + 1) of \(max(1, total))."
    }

    static func axisSeriesSpeech(
        series: KitV1AxisSeries,
        axisBody: KitV1AxisBody,
        index: Int,
        total: Int,
        spec: KitV1CardSpec
    ) -> String {
        var names: [String] = []
        var details: [String] = []
        var numbers: [String] = []
        var positions: [String] = []

        if let leading = series.leading {
            collectMarks(leading, names: &names, details: &details, numbers: &numbers)
        }
        for mark in series.marks {
            switch mark {
            case .bar(let bar):
                if bar.barStyle == .range {
                    let span = axisBody.scale.max - axisBody.scale.min
                    let lo = bar.lo.map { formatAxisPosition(axisBody.scale.min + $0 * span, scale: axisBody.scale) }
                    let hi = bar.hi.map { formatAxisPosition(axisBody.scale.min + $0 * span, scale: axisBody.scale) }
                    if let lo, let hi {
                        positions.append("sits between \(lo) and \(hi)")
                    }
                    if let pct = bar.pctLabel, !pct.isEmpty {
                        numbers.append(expandPercent(pct))
                    }
                } else {
                    collectMarks([mark], names: &names, details: &details, numbers: &numbers)
                }
            case .line(let line):
                if let first = line.points.first, let last = line.points.last {
                    let p1 = formatAxisPosition(first.y, scale: axisBody.scale)
                    let p2 = formatAxisPosition(last.y, scale: axisBody.scale)
                    positions.append("runs from \(p1) to \(p2)")
                }
            case .dot(let dot):
                positions.append("sits at \(formatAxisPosition(dot.x, scale: axisBody.scale))")
                let lbl = expandPercent(dot.label)
                if !lbl.isEmpty { numbers.append(lbl) }
            default:
                collectMarks([mark], names: &names, details: &details, numbers: &numbers)
            }
        }

        if details.isEmpty, let ctx = topicContext(for: spec) {
            details.append(ctx)
        }
        if positions.isEmpty, let first = numbers.first {
            positions.append("at \(first)")
        }

        let head = names.isEmpty ? (series.id) : names.joined(separator: ", ")
        let clauses = [head]
            + details
            + positions
            + numbers
            + ["\(index + 1) of \(max(1, total))"]
        return deduplicateConsecutive(clauses).joined(separator: ", ") + "."
    }

    // MARK: - Calendar Day Speech

    static func calendarDaySpeech(
        day: KitV1CalendarDay,
        calendarBody: KitV1CalendarBody,
        spec: KitV1CardSpec,
        index: Int,
        total: Int
    ) -> String {
        var tileDates: [String] = []
        var names: [String] = []
        var details: [String] = []
        var numbers: [String] = []

        for mark in day.marks {
            if case .tile(let tile) = mark {
                let top = tile.topLabel?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let center = tile.centerLabel.trimmingCharacters(in: .whitespacesAndNewlines)
                let dateText = [top, center].filter { !$0.isEmpty }.joined(separator: " ")
                if !dateText.isEmpty { tileDates.append(expandPercent(dateText)) }
                if let bottom = tile.bottomLabel?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !bottom.isEmpty {
                    numbers.append(expandPercent(bottom))
                }
                if tile.highlightRole == .dayPeak {
                    details.append("peak day")
                }
            } else {
                collectMarks([mark], names: &names, details: &details, numbers: &numbers)
            }
        }

        let dateLabel = tileDates.isEmpty ? expandPercent(day.dateKey) : tileDates.joined(separator: " ")

        // Subject / name from calendar header marks or card title
        if names.isEmpty, let headerWords = calendarBody.headerMarks?.compactMap({ mark -> String? in
            if case .word(let w) = mark, w.style != .kicker { return expandPercent(w.text) }
            return nil
        }), !headerWords.isEmpty {
            names.append(contentsOf: headerWords)
        }
        if names.isEmpty, let headline = topicContext(for: spec) {
            names.append(headline)
        }

        if let pct = day.dailyPct, numbers.allSatisfy({ !$0.contains("percent") }) {
            let rounded = Int((pct * 100.0).rounded())
            numbers.insert("\(rounded) percent", at: 0)
        }

        let place = "\(index + 1) of \(max(1, total))"
        let parts = ([dateLabel] + names + details + numbers + [place]).filter { !$0.isEmpty }
        return deduplicateConsecutive(parts).joined(separator: ", ") + "."
    }

    // MARK: - Internals

    private static func headerDeadlineIso(in spec: KitV1CardSpec) -> String? {
        guard case .stack(let stack) = spec.body,
              let headers = stack.headerMarks else {
            return nil
        }
        return headers.compactMap { mark in
            if case .number(let n) = mark, n.unit == .days { return n.deadlineIso }
            return nil
        }.first
    }

    private static func topicContext(for spec: KitV1CardSpec) -> String? {
        if let headline = spec.commonHeadline?.trimmingCharacters(in: .whitespacesAndNewlines),
           !headline.isEmpty {
            return expandPercent(headline)
        }
        if let kicker = spec.kicker?.trimmingCharacters(in: .whitespacesAndNewlines),
           !kicker.isEmpty {
            return expandPercent(kicker)
        }
        return nil
    }

    private static func collectMarks(
        _ marks: [KitV1Mark],
        now: Date = Date(),
        inheritedDeadline: String? = nil,
        names: inout [String],
        details: inout [String],
        numbers: inout [String]
    ) {
        for mark in marks {
            switch mark {
            case .picture:
                // Pictures never announce as "image".
                break
            case .word(let w):
                if w.style == .rank { continue }
                let text: String = {
                    if w.style == .heroLabel,
                       let deadline = w.deadlineIso ?? inheritedDeadline,
                       let days = KitCountdownClock366B.daysLeft(from: deadline, now: now) {
                        if days <= 0 { return "ends today" }
                        return days == 1 ? "day left" : "days left"
                    }
                    return w.text
                }()
                let expanded = expandPercent(text)
                if !expanded.isEmpty {
                    if w.style == .sub || w.style == .meta || w.style == .pill || w.style == .heroLabel {
                        details.append(expanded)
                    } else {
                        names.append(expanded)
                    }
                }
                if let sec = w.secondaryText?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !sec.isEmpty {
                    details.append(expandPercent(sec))
                }
            case .number(let n):
                if n.unit == .days,
                   let deadline = n.deadlineIso,
                   let days = KitCountdownClock366B.daysLeft(from: deadline, now: now) {
                    numbers.append(days <= 0 ? "Today" : "\(days)")
                } else {
                    let expanded = expandPercent(n.display)
                    if !expanded.isEmpty { numbers.append(expanded) }
                }
            case .tile(let t):
                let parts = [t.topLabel, t.centerLabel, t.bottomLabel]
                    .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
                    .map(expandPercent)
                if !parts.isEmpty { numbers.append(parts.joined(separator: " ")) }
            case .ring(let r):
                let raw = r.label ?? "\(Int((min(1, max(0, r.progress)) * 100).rounded()))%"
                numbers.append(expandPercent(raw))
            case .bar(let b):
                if b.barStyle == .split, let segs = b.segments, segs.count == 2 {
                    let leftLbl = segs[0].label.map(expandPercent) ?? "\(Int((segs[0].fill * 100).rounded())) percent"
                    let rightLbl = segs[1].label.map(expandPercent) ?? "\(Int((segs[1].fill * 100).rounded())) percent"
                    numbers.append("\(leftLbl) versus \(rightLbl)")
                } else if b.barStyle == .range, let pct = b.pctLabel, !pct.isEmpty {
                    numbers.append(expandPercent(pct))
                }
            case .dot(let d):
                let lbl = expandPercent(d.label)
                if !lbl.isEmpty { numbers.append(lbl) }
            case .line:
                break
            }
        }
    }

    private static func formatAxisPosition(_ value: Double, scale: KitV1AxisScale) -> String {
        let ticksLookPercent = scale.unit == "%" || scale.ticks.contains { $0.label.contains("%") }
        let formattedNumber: (Double) -> String = { v in
            abs(v.rounded() - v) < 0.05 ? "\(Int(v.rounded()))" : String(format: "%.1f", v)
        }
        if ticksLookPercent {
            let scaled = (abs(value) <= 1.0 && scale.max <= 1.0) ? value * 100.0 : value
            return "\(formattedNumber(scaled)) percent"
        }
        let ticksLookDollarM = scale.unit == "$M" || scale.ticks.contains { $0.label.hasPrefix("$") && $0.label.hasSuffix("M") }
        if ticksLookDollarM {
            return "$\(formattedNumber(value))M"
        }
        let unit = scale.unit.trimmingCharacters(in: .whitespacesAndNewlines)
        if !unit.isEmpty {
            return "\(formattedNumber(value))\(unit)"
        }
        return formattedNumber(value)
    }

    private static func formatSentence(
        names: [String],
        details: [String],
        numbers: [String],
        place: String
    ) -> String {
        let parts = deduplicateConsecutive(names + details + numbers + [place])
            .filter { !$0.isEmpty }
        return parts.joined(separator: ", ") + "."
    }

    private static func deduplicateConsecutive(_ parts: [String]) -> [String] {
        var out: [String] = []
        for p in parts {
            let norm = p.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !norm.isEmpty else { continue }
            if out.last?.caseInsensitiveCompare(norm) != .orderedSame {
                out.append(norm)
            }
        }
        return out
    }
}
