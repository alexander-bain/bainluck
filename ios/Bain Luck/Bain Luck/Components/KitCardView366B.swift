import SwiftUI

/// Ruling 366: B / #13551 — Layout-generic Kit v1 card view (`stack`, `grid`, and in 6B `axis`/`calendar`).
///
/// Renders strictly from `spec.layout` and the 8 shared marks. Never inspects `spec.variant`.
/// Public readers cannot reach this view yet (`363: A`: blind grade required before wiring).
struct KitCardView366B: View {
    let spec: KitV1CardSpec
    var onRoute: ((KitV1Route) -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme

    /// Layouts implemented on the current milestone (`stack` and `grid`; `axis` / `calendar` arrive in 6B).
    static func supportsLayout(_ layout: KitV1Layout) -> Bool {
        switch layout {
        case .stack, .grid:
            return true
        case .calendar, .axis:
            return false
        }
    }

    init?(spec: KitV1CardSpec, onRoute: ((KitV1Route) -> Void)? = nil) {
        guard spec.body.isRenderable, Self.supportsLayout(spec.layout) else {
            return nil
        }
        self.spec = spec
        self.onRoute = onRoute
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
        case .calendar, .axis:
            EmptyView()
        }
    }

    @ViewBuilder
    private var cardHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            if hasTopRow {
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
            switch stackBody.headerLayout ?? .banner {
            case .banner:
                HStack(alignment: .center, spacing: 10) {
                    ForEach(Array(headers.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
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
                        KitMarkView366B(mark: mark)
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
        if dynamicTypeSize.isAccessibilitySize {
            return 84
        }
        return gridBody.columns.count <= 2 ? 68 : 56
    }

    private var matrixBody: some View {
        let hasRank = matrixHasLeadingRank
        let colWidth = matrixColumnWidth

        return VStack(alignment: .leading, spacing: 0) {
            if gridBody.showColumnHeaders {
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
                    ForEach(gridBody.columns, id: \.key) { col in
                        Text(col.label)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(width: colWidth, alignment: .center)
                    }
                }
                .padding(.bottom, 6)
            }

            ForEach(Array(gridBody.rows.enumerated()), id: \.element.id) { index, row in
                Rectangle()
                    .fill(KitTones366B.divider(for: colorScheme))
                    .frame(height: 1)

                matrixRow(row, hasRank: hasRank, colWidth: colWidth)
                    .padding(.top, 7)
                    .padding(.bottom, index == gridBody.rows.count - 1 ? 0 : 7)
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

            ForEach(gridBody.columns, id: \.key) { col in
                let cell = cellByKey[col.key]
                gridCellView(cell)
                    .frame(width: colWidth)
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

private struct KitHorizontalDashedLine366B: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: rect.midY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        return p
    }
}
