import SwiftUI

/// Ruling 366: B / #13551 — Layout-generic Kit v1 card view (`stack`, `grid`, `calendar`, `axis`).
///
/// Renders strictly from `spec.layout` and the 8 shared marks. Never inspects `spec.variant`.
/// Public readers cannot reach this view yet (`363: A`: blind grade required before wiring).
struct KitCardView366B: View {
    let spec: KitV1CardSpec
    var onRoute: ((KitV1Route) -> Void)? = nil
    var now: Date = Date()

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    static func supportsLayout(_ layout: KitV1Layout) -> Bool {
        switch layout {
        case .stack, .grid, .calendar, .axis:
            return true
        }
    }

    init?(spec: KitV1CardSpec, onRoute: ((KitV1Route) -> Void)? = nil, now: Date = Date()) {
        guard spec.body.isRenderable, Self.supportsLayout(spec.layout) else {
            return nil
        }
        self.spec = spec
        self.onRoute = onRoute
        self.now = now
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            cardHeader
            bodyContent
            cardFooter
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(KitTones366B.cardBackground(for: colorScheme))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
        )
        .environment(\.kitNow366B, now)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("kitV1.\(spec.layout.rawValue)Card.\(spec.id)")
    }

    @ViewBuilder
    private var bodyContent: some View {
        switch spec.body {
        case .stack(let stackBody):
            KitStackBodyView366B(
                stackBody: stackBody,
                defaultRoute: spec.route,
                onRoute: onRoute
            )
        case .grid(let gridBody):
            KitGridBodyView366B(
                gridBody: gridBody,
                defaultRoute: spec.route,
                onRoute: onRoute
            )
        case .calendar(let calendarBody):
            KitCalendarBodyView366B(calendarBody: calendarBody)
        case .axis(let axisBody):
            KitAxisBodyView366B(axisBody: axisBody)
        }
    }

    @ViewBuilder
    private var cardHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            if hasTopRow {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 2) {
                        if let kicker = spec.kicker, !kicker.isEmpty {
                            Text(kicker.uppercased())
                                .font(.caption2.weight(.bold))
                                .tracking(0.8)
                                .foregroundStyle(KitTones366B.brandAccent(for: colorScheme))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let sourceLabel = spec.sourceMark?.label, !sourceLabel.isEmpty {
                            Text(sourceLabel)
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                } else {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        if let kicker = spec.kicker, !kicker.isEmpty {
                            Text(kicker.uppercased())
                                .font(.caption2.weight(.bold))
                                .tracking(0.8)
                                .foregroundStyle(KitTones366B.brandAccent(for: colorScheme))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 4)
                        if let sourceLabel = spec.sourceMark?.label, !sourceLabel.isEmpty {
                            Text(sourceLabel)
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }
                }
            }

            if let headline = spec.commonHeadline, !headline.isEmpty {
                Text(headline)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let caption = spec.statCaption, !caption.isEmpty {
                Text(caption)
                    .font(.caption)
                    .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private var cardFooter: some View {
        if hasFooter {
            VStack(alignment: .leading, spacing: 4) {
                if let footnote = spec.footnote, !footnote.isEmpty {
                    Rectangle()
                        .fill(KitTones366B.divider(for: colorScheme))
                        .frame(height: 1)
                    Text(footnote)
                        .font(.caption2)
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let disclosure = spec.disclosure, !disclosure.isEmpty {
                    Text(disclosure)
                        .font(.caption2)
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var hasTopRow: Bool {
        !(spec.kicker ?? "").isEmpty || !(spec.sourceMark?.label ?? "").isEmpty
    }

    private var hasFooter: Bool {
        !(spec.footnote ?? "").isEmpty || !(spec.disclosure ?? "").isEmpty
    }
}

// MARK: - 1. Stack Body Layout

struct KitStackBodyView366B: View {
    let stackBody: KitV1StackBody
    let defaultRoute: KitV1Route?
    var onRoute: ((KitV1Route) -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            stackHeader

            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(stackBody.items.enumerated()), id: \.element.id) { index, item in
                    stackRow(item)
                        .padding(.top, index == 0 ? 0 : 8)
                        .padding(.bottom, index == stackBody.items.count - 1 ? 0 : 8)

                    if let divider = item.dividerAfter {
                        dashedDivider(label: divider.label)
                            .padding(.vertical, 4)
                    } else if index < stackBody.items.count - 1 {
                        Rectangle()
                            .fill(KitTones366B.divider(for: colorScheme))
                            .frame(height: 1)
                    }
                }
            }

            if let footerMarks = stackBody.footerMarks, !footerMarks.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(footerMarks.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var stackHeader: some View {
        if let headers = stackBody.headerMarks, !headers.isEmpty {
            let numberDeadlineIso: String? = headers.compactMap { mark in
                if case .number(let n) = mark, n.unit == .days {
                    return n.deadlineIso
                }
                return nil
            }.first

            switch stackBody.headerLayout ?? .banner {
            case .banner:
                Group {
                    if dynamicTypeSize.isAccessibilitySize {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(Array(headers.enumerated()), id: \.offset) { _, mark in
                                KitMarkView366B(mark: mark, inheritedCountdownDeadlineIso: numberDeadlineIso)
                            }
                        }
                    } else {
                        HStack(alignment: .center, spacing: 10) {
                            ForEach(Array(headers.enumerated()), id: \.offset) { _, mark in
                                KitMarkView366B(mark: mark, inheritedCountdownDeadlineIso: numberDeadlineIso)
                            }
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(KitTones366B.elevatedBackground(for: colorScheme))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
                )

            case .split:
                HStack(alignment: .center, spacing: 8) {
                    ForEach(Array(headers.enumerated()), id: \.offset) { idx, mark in
                        KitMarkView366B(mark: mark, inheritedCountdownDeadlineIso: numberDeadlineIso)
                        if idx < headers.count - 1 {
                            Spacer(minLength: 4)
                        }
                    }
                }

            case .none:
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private func stackRow(_ item: KitV1StackItem) -> some View {
        let targetRoute = item.route ?? defaultRoute
        let content = VStack(alignment: .leading, spacing: 4) {
            markRow(marks: item.marks)

            if let subMarks = item.subMarks, !subMarks.isEmpty {
                HStack(spacing: 8) {
                    Spacer(minLength: 0)
                    ForEach(Array(subMarks.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                    Spacer(minLength: 0)
                }
            }
        }

        if let targetRoute, let onRoute {
            Button {
                onRoute(targetRoute)
            } label: {
                content
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            content
        }
    }

    @ViewBuilder
    private func markRow(marks: [KitV1Mark]) -> some View {
        if dynamicTypeSize.isAccessibilitySize {
            accessibilityMarkStack(marks: marks)
        } else {
            HStack(alignment: .center, spacing: 8) {
                ForEach(Array(marks.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
            }
        }
    }

    @ViewBuilder
    private func accessibilityMarkStack(marks: [KitV1Mark]) -> some View {
        if let splitIndex = marks.firstIndex(where: {
            if case .bar(let b) = $0, b.barStyle == .split { return true }
            return false
        }) {
            let leftMarks = Array(marks[..<splitIndex])
            let splitBar = marks[splitIndex]
            let rightMarks = Array(marks[(splitIndex + 1)...])
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .center, spacing: 8) {
                    ForEach(Array(leftMarks.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                    Spacer(minLength: 4)
                }
                KitMarkView366B(mark: splitBar)
                HStack(alignment: .center, spacing: 8) {
                    Spacer(minLength: 4)
                    ForEach(Array(rightMarks.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        } else {
            let labelAndPictureMarks = marks.filter {
                switch $0 {
                case .picture, .word: return true
                case .number, .bar, .tile, .ring, .dot, .line: return false
                }
            }
            let metricMarks = marks.filter {
                switch $0 {
                case .picture, .word: return false
                case .number, .bar, .tile, .ring, .dot, .line: return true
                }
            }
            VStack(alignment: .leading, spacing: 6) {
                if !labelAndPictureMarks.isEmpty {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(labelAndPictureMarks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }
                }
                if !metricMarks.isEmpty {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(metricMarks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }
                }
            }
        }
    }

    private func dashedDivider(label: String?) -> some View {
        VStack(spacing: 4) {
            KitHorizontalDashedLine366B()
                .stroke(style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                .foregroundStyle(KitTones366B.divider(for: colorScheme))
                .frame(height: 1)
            if let label, !label.isEmpty {
                Text(label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                    .frame(maxWidth: .infinity, alignment: .center)
            }
        }
    }
}

// MARK: - 2. Grid Body Layout (`matrix` & `stacked_cells`)

struct KitGridBodyView366B: View {
    let gridBody: KitV1GridBody
    let defaultRoute: KitV1Route?
    var onRoute: ((KitV1Route) -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            switch gridBody.rowLayout {
            case .matrix:
                matrixBody
            case .stackedCells:
                stackedCellsBody
            }

            if let footerMarks = gridBody.footerMarks, !footerMarks.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(footerMarks.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        }
    }

    private var matrixHasLeadingRank: Bool {
        guard let first = gridBody.rows.first?.leading.first else { return false }
        if case .word(let w) = first, w.style == .rank {
            return true
        }
        return false
    }

    private var matrixColumnWidth: CGFloat {
        gridBody.columns.count <= 2 ? 64 : 46
    }

    private var matrixBody: some View {
        let hasRank = matrixHasLeadingRank
        let colWidth = matrixColumnWidth

        return VStack(alignment: .leading, spacing: 0) {
            if gridBody.showColumnHeaders && !dynamicTypeSize.isAccessibilitySize {
                HStack(alignment: .bottom, spacing: 6) {
                    if hasRank {
                        Text("#")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                            .frame(width: 16, alignment: .leading)
                    }
                    Text(gridBody.leadingLabel ?? "Item")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .frame(maxWidth: .infinity, alignment: .leading)
                    HStack(alignment: .bottom, spacing: 4) {
                        ForEach(gridBody.columns, id: \.key) { col in
                            Text(col.label)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(width: colWidth, alignment: .center)
                        }
                    }
                }
                .padding(.bottom, 6)
            }

            ForEach(Array(gridBody.rows.enumerated()), id: \.element.id) { index, row in
                Rectangle()
                    .fill(KitTones366B.divider(for: colorScheme))
                    .frame(height: 1)

                if dynamicTypeSize.isAccessibilitySize {
                    accessibleMatrixRow(row, hasRank: hasRank)
                        .padding(.top, 9)
                        .padding(.bottom, index == gridBody.rows.count - 1 ? 0 : 9)
                } else {
                    matrixRow(row, hasRank: hasRank, colWidth: colWidth)
                        .padding(.top, 7)
                        .padding(.bottom, index == gridBody.rows.count - 1 ? 0 : 7)
                }
            }
        }
    }

    private func accessibleMatrixRow(_ row: KitV1GridRow, hasRank: Bool) -> some View {
        let rankMark: KitV1Mark? = hasRank ? row.leading.first : nil
        let entityMarks: [KitV1Mark] = hasRank ? Array(row.leading.dropFirst()) : row.leading
        let cellByKey = Dictionary(uniqueKeysWithValues: row.cells.map { ($0.columnKey, $0) })

        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 6) {
                if let rankMark {
                    KitMarkView366B(mark: rankMark)
                }
                ForEach(Array(entityMarks.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            VStack(alignment: .leading, spacing: 4) {
                ForEach(gridBody.columns, id: \.key) { col in
                    if let cell = cellByKey[col.key] {
                        HStack(alignment: .center, spacing: 8) {
                            Text(col.label)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 8)
                            gridCellView(cell)
                        }
                    }
                }
            }
        }
    }

    private func matrixRow(_ row: KitV1GridRow, hasRank: Bool, colWidth: CGFloat) -> some View {
        let rankMark: KitV1Mark? = hasRank ? row.leading.first : nil
        let entityMarks: [KitV1Mark] = hasRank ? Array(row.leading.dropFirst()) : row.leading
        let cellByKey = Dictionary(uniqueKeysWithValues: row.cells.map { ($0.columnKey, $0) })

        return HStack(alignment: .center, spacing: 6) {
            if let rankMark {
                KitMarkView366B(mark: rankMark)
                    .frame(width: 16, alignment: .leading)
            }

            HStack(alignment: .center, spacing: 6) {
                ForEach(Array(entityMarks.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            HStack(alignment: .center, spacing: 4) {
                ForEach(gridBody.columns, id: \.key) { col in
                    let cell = cellByKey[col.key]
                    gridCellView(cell)
                        .frame(width: colWidth)
                }
            }
        }
    }

    private var stackedCellsBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(gridBody.rows.enumerated()), id: \.element.id) { index, row in
                if index > 0 {
                    Rectangle()
                        .fill(KitTones366B.divider(for: colorScheme))
                        .frame(height: 1)
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(row.leading.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }

                    if dynamicTypeSize.isAccessibilitySize {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(row.cells, id: \.columnKey) { cell in
                                gridCellView(cell)
                                    .frame(maxWidth: .infinity)
                            }
                        }
                    } else {
                        HStack(alignment: .top, spacing: 6) {
                            ForEach(row.cells, id: \.columnKey) { cell in
                                gridCellView(cell)
                                    .frame(maxWidth: .infinity)
                            }
                        }
                    }
                }
                .padding(.top, index == 0 ? 0 : 10)
                .padding(.bottom, index == gridBody.rows.count - 1 ? 0 : 10)
            }
        }
    }

    @ViewBuilder
    private func gridCellView(_ cell: KitV1GridCell?) -> some View {
        if let cell {
            let content = VStack(spacing: 2) {
                ForEach(Array(cell.marks.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
            }
            if let route = cell.route ?? defaultRoute, let onRoute {
                Button {
                    onRoute(route)
                } label: {
                    content.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else {
                content
            }
        }
    }
}

// MARK: - 3. Calendar Body Layout

struct KitCalendarBodyView366B: View {
    let calendarBody: KitV1CalendarBody

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let headers = calendarBody.headerMarks, !headers.isEmpty {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(headers.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }
                } else {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(headers.enumerated()), id: \.offset) { idx, mark in
                            KitMarkView366B(mark: mark)
                            if idx < headers.count - 1 {
                                Spacer(minLength: 4)
                            }
                        }
                    }
                }
            }

            if dynamicTypeSize.isAccessibilitySize {
                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: 8),
                        GridItem(.flexible(), spacing: 8)
                    ],
                    spacing: 8
                ) {
                    ForEach(calendarBody.days, id: \.dateKey) { day in
                        dayColumn(day)
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 4) {
                    ForEach(calendarBody.days, id: \.dateKey) { day in
                        dayColumn(day)
                            .frame(maxWidth: .infinity)
                    }
                }
            }

            if let footers = calendarBody.footerMarks, !footers.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(footers.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        }
    }

    private func dayColumn(_ day: KitV1CalendarDay) -> some View {
        VStack(spacing: 3) {
            ForEach(Array(day.marks.enumerated()), id: \.offset) { _, mark in
                switch mark {
                case .tile(let tile):
                    KitTileMarkView366B(mark: tile, compact: true)
                default:
                    KitMarkView366B(mark: mark)
                        .frame(maxWidth: .infinity, alignment: .center)
                }
            }
        }
    }
}

// MARK: - 4. Axis Body Layout

struct KitAxisBodyView366B: View {
    let axisBody: KitV1AxisBody

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var dots: [KitV1DotMark] {
        (axisBody.marks ?? []).compactMap {
            if case .dot(let d) = $0 { return d }
            return nil
        }
    }

    private var lines: [KitV1LineMark] {
        (axisBody.marks ?? []).compactMap {
            if case .line(let l) = $0 { return l }
            return nil
        }
    }

    private var elevatedDots: [KitV1DotMark] {
        dots.filter { $0.picture != nil && $0.yLane != nil }
    }

    private var baseDots: [KitV1DotMark] {
        dots.filter { !($0.picture != nil && $0.yLane != nil) }
    }

    private var maxLane: Int {
        Int((elevatedDots.compactMap(\.yLane).max() ?? 0).rounded())
    }

    private var trackHeight: CGFloat {
        CGFloat(maxLane + 1) * 28 + 82
    }

    private func xFraction(_ value: Double) -> CGFloat {
        let span = max(1e-6, axisBody.scale.max - axisBody.scale.min)
        let raw = (value - axisBody.scale.min) / span
        return CGFloat(min(1.0, max(0.0, raw)))
    }

    private func clampedX(_ value: Double, width: CGFloat, inset: CGFloat = 12) -> CGFloat {
        let usable = max(1, width - inset * 2)
        return inset + usable * xFraction(value)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !dots.isEmpty {
                axisPlotView
            }

            if !lines.isEmpty && dots.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                        KitLineMarkView366B(mark: line)
                    }
                    scaleTicksView
                }
            }

            if let series = axisBody.series, !series.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(series, id: \.id) { row in
                        VStack(alignment: .leading, spacing: 4) {
                            if let leading = row.leading, !leading.isEmpty {
                                HStack(alignment: .center, spacing: 8) {
                                    ForEach(Array(leading.enumerated()), id: \.offset) { _, mark in
                                        KitMarkView366B(mark: mark)
                                    }
                                }
                            }
                            if dynamicTypeSize.isAccessibilitySize {
                                VStack(alignment: .leading, spacing: 4) {
                                    ForEach(Array(row.marks.enumerated()), id: \.offset) { _, mark in
                                        KitMarkView366B(mark: mark)
                                    }
                                }
                            } else {
                                HStack(alignment: .center, spacing: 8) {
                                    ForEach(Array(row.marks.enumerated()), id: \.offset) { _, mark in
                                        KitMarkView366B(mark: mark)
                                    }
                                }
                            }
                        }
                    }

                    if dots.isEmpty && lines.isEmpty && !axisBody.scale.ticks.isEmpty {
                        Rectangle()
                            .fill(KitTones366B.divider(for: colorScheme))
                            .frame(height: 1)
                        scaleTicksView
                    }
                }
            }

            if let summaries = axisBody.summaryMarks, !summaries.isEmpty {
                Group {
                    if dynamicTypeSize.isAccessibilitySize {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(Array(summaries.enumerated()), id: \.offset) { _, mark in
                                KitMarkView366B(mark: mark)
                            }
                        }
                    } else {
                        HStack(alignment: .center, spacing: 8) {
                            ForEach(Array(summaries.enumerated()), id: \.offset) { idx, mark in
                                KitMarkView366B(mark: mark)
                                if idx < summaries.count - 1 {
                                    Spacer(minLength: 4)
                                }
                            }
                        }
                    }
                }
            }

            if let footers = axisBody.footerMarks, !footers.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(footers.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var scaleTicksView: some View {
        let ticks = axisBody.scale.ticks
        if dynamicTypeSize.isAccessibilitySize, let first = ticks.first {
            HStack(spacing: 8) {
                Text(first.label)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
                if ticks.count > 1, let last = ticks.last {
                    Spacer(minLength: 8)
                    Text(last.label)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
            }
        } else {
            HStack {
                ForEach(Array(ticks.enumerated()), id: \.offset) { idx, tick in
                    Text(tick.label)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .fixedSize(horizontal: true, vertical: false)
                    if idx < ticks.count - 1 {
                        Spacer(minLength: 4)
                    }
                }
            }
        }
    }

    private var axisPlotVisibleTicks: [(offset: Int, tick: KitV1AxisTick)] {
        let ticks = axisBody.scale.ticks
        guard dynamicTypeSize.isAccessibilitySize, ticks.count > 3 else {
            return Array(ticks.enumerated()).map { (offset: $0.offset, tick: $0.element) }
        }
        let midIndex = ticks.count / 2
        return [0, midIndex, ticks.count - 1].map { idx in
            (offset: idx, tick: ticks[idx])
        }
    }

    private var axisPlotView: some View {
        let totalH = trackHeight
        let baselineY = totalH - 24
        let ticks = axisBody.scale.ticks
        let visibleTicks = axisPlotVisibleTicks

        return GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .topLeading) {
                if let band = axisBody.highlightBand {
                    let loX = clampedX(band.lo, width: w, inset: 8)
                    let hiX = clampedX(band.hi, width: w, inset: 8)
                    let bandW = max(24, hiX - loX)
                    ZStack(alignment: .top) {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(KitTones366B.elevatedBackground(for: colorScheme).opacity(0.9))
                            .overlay(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(KitTones366B.divider(for: colorScheme), lineWidth: 1)
                            )
                        Text(band.label.uppercased())
                            .font(.caption2.weight(.semibold))
                            .tracking(0.6)
                            .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                            .dynamicTypeSize(...DynamicTypeSize.xLarge)
                            .lineLimit(1)
                            .padding(.top, 5)
                    }
                    .frame(width: bandW, height: baselineY)
                    .offset(x: loX, y: 0)
                }

                Rectangle()
                    .fill(KitTones366B.cardBorder(for: colorScheme))
                    .frame(width: max(1, w - 16), height: 1.5)
                    .offset(x: 8, y: baselineY)

                ForEach(Array(baseDots.enumerated()), id: \.offset) { idx, dot in
                    let px = clampedX(dot.x, width: w, inset: 10)
                    let py = baselineY - 7 - CGFloat(idx % 3) * 5
                    Circle()
                        .fill(KitTones366B.barColor(
                            hex: dot.color?.light,
                            darkHex: dot.colorDark ?? dot.color?.dark,
                            fallbackIndex: idx,
                            scheme: colorScheme
                        ))
                        .overlay(Circle().stroke(KitTones366B.cardBackground(for: colorScheme), lineWidth: 1.25))
                        .frame(width: 9, height: 9)
                        .position(x: px, y: py)
                        .accessibilityLabel(dot.label)
                }

                ForEach(Array(elevatedDots.enumerated()), id: \.offset) { _, dot in
                    let lane = CGFloat(max(0, Int((dot.yLane ?? 0).rounded())))
                    let px = clampedX(dot.x, width: w, inset: 16)
                    let py = baselineY - 28 - lane * 28
                    if let pic = dot.picture {
                        KitPictureMarkView366B(mark: pic, fixedSquareBox: 24)
                            .position(x: px, y: py)
                            .accessibilityLabel(dot.label)
                    }
                }

                ForEach(visibleTicks, id: \.offset) { item in
                    let idx = item.offset
                    let tick = item.tick
                    let tx: CGFloat = {
                        if idx == 0 { return 16 }
                        if idx == ticks.count - 1 { return max(16, w - 20) }
                        return clampedX(tick.x, width: w, inset: 18)
                    }()
                    Text(tick.label)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .dynamicTypeSize(...DynamicTypeSize.xLarge)
                        .fixedSize(horizontal: true, vertical: false)
                        .position(x: tx, y: totalH - 10)
                }
            }
        }
        .frame(height: totalH)
    }
}

private struct KitHorizontalDashedLine366B: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: rect.midY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        return p
    }
}
