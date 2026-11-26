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
    @Environment(\.discoverCardLikeAction420D) private var likeAction

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
            if let likeAction {
                DiscoverCardActionBar420D(actions: likeAction, topDivider: true, horizontalPadding: 0, verticalPadding: 4)
            }
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
                spec: spec,
                stackBody: stackBody,
                defaultRoute: spec.route,
                onRoute: onRoute
            )
            .accessibilitySortPriority(4)
        case .grid(let gridBody):
            KitGridBodyView366B(
                spec: spec,
                gridBody: gridBody,
                defaultRoute: spec.route,
                onRoute: onRoute
            )
            .accessibilitySortPriority(4)
        case .calendar(let calendarBody):
            KitCalendarBodyView366B(
                spec: spec,
                calendarBody: calendarBody,
                defaultRoute: spec.route,
                onRoute: onRoute
            )
            .accessibilitySortPriority(4)
        case .axis(let axisBody):
            KitAxisBodyView366B(
                spec: spec,
                axisBody: axisBody,
                defaultRoute: spec.route,
                onRoute: onRoute
            )
            .accessibilitySortPriority(4)
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
                    .accessibilityElement(children: .combine)
                    .accessibilitySortPriority(6)
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
                    .accessibilityElement(children: .combine)
                    .accessibilitySortPriority(6)
                }
            }

            if let headline = spec.commonHeadline, !headline.isEmpty {
                Text(headline)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityLabel(KitAccessibilitySpeech366B.cardHeadlineSpeech(spec: spec))
                    .accessibilitySortPriority(10)
            }

            if let caption = spec.statCaption, !caption.isEmpty {
                Text(caption)
                    .font(.caption)
                    .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel(KitAccessibilitySpeech366B.expandPercent(caption))
                    .accessibilitySortPriority(5)
            }
        }
    }

    @ViewBuilder
    private var cardFooter: some View {
        let footerContent = VStack(alignment: .leading, spacing: 4) {
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
                    .font(.caption2.weight(spec.route != nil ? .semibold : .regular))
                    .foregroundStyle(
                        spec.route != nil
                            ? KitTones366B.brandAccent(for: colorScheme)
                            : KitTones366B.textColor(for: .muted, scheme: colorScheme)
                    )
                    .fixedSize(horizontal: false, vertical: true)
            } else if spec.route != nil && onRoute != nil && (spec.footnote ?? "").isEmpty {
                Text("Open set")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(KitTones366B.brandAccent(for: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }

        if let route = spec.route, let onRoute {
            Button {
                onRoute(route)
            } label: {
                footerContent
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(KitAccessibilitySpeech366B.footerSpeech(spec: spec))
            .accessibilitySortPriority(2)
            .accessibilityIdentifier("kitV1.footerButton")
        } else if hasFooter {
            footerContent
                .accessibilityElement(children: .combine)
                .accessibilityLabel(KitAccessibilitySpeech366B.footerSpeech(spec: spec))
                .accessibilitySortPriority(2)
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
    let spec: KitV1CardSpec
    let stackBody: KitV1StackBody
    let defaultRoute: KitV1Route?
    var onRoute: ((KitV1Route) -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.kitNow366B) private var kitNow

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            stackHeader

            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(stackBody.items.enumerated()), id: \.element.id) { index, item in
                    stackRow(item, index: index, total: stackBody.items.count)
                        .padding(.top, index == 0 ? 0 : 6)
                        .padding(.bottom, index == stackBody.items.count - 1 ? 0 : 6)

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
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(headers.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark, inheritedCountdownDeadlineIso: numberDeadlineIso)
                        }
                    }
                } else {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(headers.enumerated()), id: \.offset) { idx, mark in
                            KitMarkView366B(mark: mark, inheritedCountdownDeadlineIso: numberDeadlineIso)
                            if idx < headers.count - 1 {
                                Spacer(minLength: 4)
                            }
                        }
                    }
                }

            case .none:
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private func stackRow(_ item: KitV1StackItem, index: Int, total: Int) -> some View {
        let targetRoute = item.route ?? defaultRoute
        let speech = KitAccessibilitySpeech366B.stackRowSpeech(
            item: item,
            index: index,
            total: total,
            spec: spec,
            now: kitNow
        )
        let content = VStack(alignment: .leading, spacing: 4) {
            markRow(marks: item.marks)

            if let subMarks = item.subMarks, !subMarks.isEmpty {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(subMarks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }
                } else {
                    HStack(spacing: 8) {
                        Spacer(minLength: 0)
                        ForEach(Array(subMarks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                        Spacer(minLength: 0)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)

        if let targetRoute, let onRoute {
            Button {
                onRoute(targetRoute)
            } label: {
                content
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(speech)
            .accessibilityIdentifier("kitV1.stackRow.\(item.id)")
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(speech)
                .accessibilityIdentifier("kitV1.stackRow.\(item.id)")
        }
    }

    private func isLeadingMetaOrRank(_ mark: KitV1Mark) -> Bool {
        guard case .word(let w) = mark else { return false }
        return w.style == .rank || w.style == .meta
    }

    private func isSplitBarRow(_ marks: [KitV1Mark]) -> Bool {
        marks.contains {
            if case .bar(let b) = $0 { return b.barStyle == .split }
            return false
        }
    }

    /// Ruling 387: A — Reference picture mark from sibling rows so a row without a verified picture
    /// draws its initials in a matching circle without altering pictureless cards (`388: A`).
    private var siblingLeadingPicture: KitV1PictureMark? {
        for item in stackBody.items where !isSplitBarRow(item.marks) {
            let afterPrefix = item.marks.drop(while: isLeadingMetaOrRank)
            if case .picture(let pic) = afterPrefix.first {
                return pic
            }
        }
        return nil
    }

    private func leadingInitialsName(for marks: [KitV1Mark]) -> String? {
        guard siblingLeadingPicture != nil, !isSplitBarRow(marks) else { return nil }
        let hasPicture = marks.contains {
            if case .picture = $0 { return true }
            return false
        }
        guard !hasPicture else { return nil }
        let afterPrefix = marks.drop(while: isLeadingMetaOrRank)
        for mark in afterPrefix {
            if case .word(let w) = mark {
                let trimmed = w.text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { return trimmed }
            }
        }
        return nil
    }

    @ViewBuilder
    private func markRow(marks: [KitV1Mark]) -> some View {
        let prefixCount = marks.prefix(while: isLeadingMetaOrRank).count
        let leadingPrefix = Array(marks.prefix(prefixCount))
        let rest = Array(marks.dropFirst(prefixCount))
        let initialsName = leadingInitialsName(for: marks)
        let refPicture = siblingLeadingPicture

        if dynamicTypeSize.isAccessibilitySize {
            accessibilityMarkStack(
                marks: marks,
                leadingPrefix: leadingPrefix,
                rest: rest,
                initialsName: initialsName,
                referencePicture: refPicture
            )
        } else {
            HStack(alignment: .center, spacing: 8) {
                ForEach(Array(leadingPrefix.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
                if let refPicture, let initialsName {
                    KitInitialsCircle366B(
                        name: initialsName,
                        subjectKind: refPicture.subjectKind,
                        box: KitPictureMarkView366B.boxSize(for: refPicture)
                    )
                }
                ForEach(Array(rest.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
            }
        }
    }

    @ViewBuilder
    private func accessibilityMarkStack(
        marks: [KitV1Mark],
        leadingPrefix: [KitV1Mark],
        rest: [KitV1Mark],
        initialsName: String?,
        referencePicture: KitV1PictureMark?
    ) -> some View {
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
            let isLabelOrPic: (KitV1Mark) -> Bool = {
                switch $0 {
                case .picture, .word: return true
                case .number, .bar, .tile, .ring, .dot, .line: return false
                }
            }
            let prefixLabelMarks = leadingPrefix.filter(isLabelOrPic)
            let restLabelMarks = rest.filter(isLabelOrPic)
            let metricMarks = marks.filter { !isLabelOrPic($0) }
            VStack(alignment: .leading, spacing: 6) {
                if !prefixLabelMarks.isEmpty || !restLabelMarks.isEmpty || initialsName != nil {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(prefixLabelMarks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                        if let referencePicture, let initialsName {
                            KitInitialsCircle366B(
                                name: initialsName,
                                subjectKind: referencePicture.subjectKind,
                                box: KitPictureMarkView366B.boxSize(for: referencePicture)
                            )
                        }
                        ForEach(Array(restLabelMarks.enumerated()), id: \.offset) { _, mark in
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
    let spec: KitV1CardSpec
    let gridBody: KitV1GridBody
    let defaultRoute: KitV1Route?
    var onRoute: ((KitV1Route) -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

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
        if horizontalSizeClass == .regular {
            return gridBody.columns.count <= 2 ? 84 : 60
        }
        return gridBody.columns.count <= 2 ? 72 : 52
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
                                .minimumScaleFactor(0.85)
                                .allowsTightening(true)
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
                    accessibleMatrixRow(row, hasRank: hasRank, rowIndex: index)
                        .padding(.top, 9)
                        .padding(.bottom, index == gridBody.rows.count - 1 ? 0 : 9)
                } else {
                    matrixRow(row, hasRank: hasRank, colWidth: colWidth, rowIndex: index)
                        .padding(.top, 6)
                        .padding(.bottom, index == gridBody.rows.count - 1 ? 0 : 6)
                }
            }
        }
    }

    private var siblingLeadingPicture: KitV1PictureMark? {
        let hasRank = matrixHasLeadingRank
        for row in gridBody.rows {
            let entityMarks = hasRank ? Array(row.leading.dropFirst()) : row.leading
            for mark in entityMarks {
                if case .picture(let pic) = mark {
                    return pic
                }
            }
        }
        return nil
    }

    private func rowLeadingView(_ row: KitV1GridRow, hasRank: Bool, rowIndex: Int) -> some View {
        let rankMark: KitV1Mark? = hasRank ? row.leading.first : nil
        let entityMarks: [KitV1Mark] = hasRank ? Array(row.leading.dropFirst()) : row.leading
        let missingLeadingPicture: KitV1PictureMark? = {
            let hasPic = entityMarks.contains {
                if case .picture = $0 { return true }
                return false
            }
            guard !hasPic else { return nil }
            return siblingLeadingPicture
        }()
        let leadingInitialsName: String? = entityMarks.compactMap { mark -> String? in
            guard case .word(let w) = mark else { return nil }
            let trimmed = w.text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }.first
        let rowSpeech = KitAccessibilitySpeech366B.gridRowSpeech(
            row: row,
            gridBody: gridBody,
            index: rowIndex,
            total: gridBody.rows.count,
            spec: spec
        )
        let rowRoute = row.cells.compactMap(\.route).first ?? defaultRoute

        let body = HStack(alignment: .center, spacing: 6) {
            if let rankMark {
                KitMarkView366B(mark: rankMark)
                    .frame(width: dynamicTypeSize.isAccessibilitySize ? nil : 16, alignment: .leading)
            }
            if let missingLeadingPicture, let leadingInitialsName {
                KitInitialsCircle366B(
                    name: leadingInitialsName,
                    subjectKind: missingLeadingPicture.subjectKind,
                    box: KitPictureMarkView366B.boxSize(for: missingLeadingPicture)
                )
            }
            ForEach(Array(entityMarks.enumerated()), id: \.offset) { _, mark in
                KitMarkView366B(mark: mark)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)

        return Group {
            if let rowRoute, let onRoute {
                Button {
                    onRoute(rowRoute)
                } label: {
                    body.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(rowSpeech)
                .accessibilityIdentifier("kitV1.gridRow.\(row.id)")
            } else {
                body
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(rowSpeech)
                    .accessibilityIdentifier("kitV1.gridRow.\(row.id)")
            }
        }
    }

    private func accessibleMatrixRow(_ row: KitV1GridRow, hasRank: Bool, rowIndex: Int) -> some View {
        let cellByKey = Dictionary(uniqueKeysWithValues: row.cells.map { ($0.columnKey, $0) })

        return VStack(alignment: .leading, spacing: 6) {
            rowLeadingView(row, hasRank: hasRank, rowIndex: rowIndex)

            VStack(alignment: .leading, spacing: 6) {
                ForEach(gridBody.columns, id: \.key) { col in
                    if let cell = cellByKey[col.key] {
                        accessibleGridCellRow(cell: cell, row: row, columnLabel: col.label, rowIndex: rowIndex)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func accessibleGridCellRow(
        cell: KitV1GridCell,
        row: KitV1GridRow,
        columnLabel: String,
        rowIndex: Int
    ) -> some View {
        let speech = KitAccessibilitySpeech366B.gridCellSpeech(
            row: row,
            cell: cell,
            columnLabel: columnLabel,
            index: rowIndex,
            total: gridBody.rows.count,
            spec: spec
        )
        let rowContent = Group {
            if dynamicTypeSize >= .accessibility3 {
                VStack(alignment: .leading, spacing: 4) {
                    Text(columnLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                        .fixedSize(horizontal: false, vertical: true)
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(cell.marks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }
                }
            } else {
                HStack(alignment: .center, spacing: 8) {
                    Text(columnLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    VStack(spacing: 2) {
                        ForEach(Array(cell.marks.enumerated()), id: \.offset) { _, mark in
                            KitMarkView366B(mark: mark)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)

        if let route = cell.route ?? defaultRoute, let onRoute {
            Button {
                onRoute(route)
            } label: {
                rowContent.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(speech)
        } else {
            rowContent
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(speech)
        }
    }

    private func matrixRow(_ row: KitV1GridRow, hasRank: Bool, colWidth: CGFloat, rowIndex: Int) -> some View {
        let cellByKey = Dictionary(uniqueKeysWithValues: row.cells.map { ($0.columnKey, $0) })

        return HStack(alignment: .center, spacing: 6) {
            rowLeadingView(row, hasRank: hasRank, rowIndex: rowIndex)

            HStack(alignment: .center, spacing: 4) {
                ForEach(gridBody.columns, id: \.key) { col in
                    let cell = cellByKey[col.key]
                    gridCellView(cell, row: row, columnLabel: col.label, rowIndex: rowIndex)
                        .frame(width: colWidth)
                        .frame(minHeight: 44)
                }
            }
        }
    }

    private var stackedCellsBody: some View {
        let colLookup = Dictionary(uniqueKeysWithValues: gridBody.columns.map { ($0.key, $0.label) })
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(gridBody.rows.enumerated()), id: \.element.id) { index, row in
                if index > 0 {
                    Rectangle()
                        .fill(KitTones366B.divider(for: colorScheme))
                        .frame(height: 1)
                }

                VStack(alignment: .leading, spacing: 8) {
                    rowLeadingView(row, hasRank: false, rowIndex: index)

                    if dynamicTypeSize.isAccessibilitySize {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(row.cells, id: \.columnKey) { cell in
                                let lbl = colLookup[cell.columnKey] ?? ""
                                gridCellView(cell, row: row, columnLabel: lbl, rowIndex: index)
                                    .frame(maxWidth: .infinity, minHeight: 44)
                            }
                        }
                    } else {
                        HStack(alignment: .top, spacing: 6) {
                            ForEach(row.cells, id: \.columnKey) { cell in
                                let lbl = colLookup[cell.columnKey] ?? ""
                                gridCellView(cell, row: row, columnLabel: lbl, rowIndex: index)
                                    .frame(maxWidth: .infinity, minHeight: 44)
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
    private func gridCellView(
        _ cell: KitV1GridCell?,
        row: KitV1GridRow,
        columnLabel: String,
        rowIndex: Int
    ) -> some View {
        if let cell {
            let speech = KitAccessibilitySpeech366B.gridCellSpeech(
                row: row,
                cell: cell,
                columnLabel: columnLabel,
                index: rowIndex,
                total: gridBody.rows.count,
                spec: spec
            )
            let content = VStack(spacing: 2) {
                ForEach(Array(cell.marks.enumerated()), id: \.offset) { _, mark in
                    KitMarkView366B(mark: mark)
                }
            }
            .frame(minWidth: 44, minHeight: 44)

            if let route = cell.route ?? defaultRoute, let onRoute {
                Button {
                    onRoute(route)
                } label: {
                    content.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(speech)
                .accessibilityIdentifier("kitV1.gridCell.\(row.id).\(cell.columnKey)")
            } else {
                content
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(speech)
            }
        }
    }
}

// MARK: - 3. Calendar Body Layout

struct KitCalendarBodyView366B: View {
    let spec: KitV1CardSpec
    let calendarBody: KitV1CalendarBody
    let defaultRoute: KitV1Route?
    var onRoute: ((KitV1Route) -> Void)? = nil

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

            if dynamicTypeSize >= .accessibility4 {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(calendarBody.days.enumerated()), id: \.element.dateKey) { idx, day in
                        dayCell(day, index: idx)
                    }
                }
            } else if dynamicTypeSize.isAccessibilitySize {
                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: 8),
                        GridItem(.flexible(), spacing: 8)
                    ],
                    spacing: 8
                ) {
                    ForEach(Array(calendarBody.days.enumerated()), id: \.element.dateKey) { idx, day in
                        dayCell(day, index: idx)
                    }
                }
            } else if calendarBody.days.count > 6 {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 52), spacing: 6)],
                    spacing: 6
                ) {
                    ForEach(Array(calendarBody.days.enumerated()), id: \.element.dateKey) { idx, day in
                        dayCell(day, index: idx)
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 4) {
                    ForEach(Array(calendarBody.days.enumerated()), id: \.element.dateKey) { idx, day in
                        dayCell(day, index: idx)
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

    @ViewBuilder
    private func dayCell(_ day: KitV1CalendarDay, index: Int) -> some View {
        let speech = KitAccessibilitySpeech366B.calendarDaySpeech(
            day: day,
            calendarBody: calendarBody,
            spec: spec,
            index: index,
            total: calendarBody.days.count
        )
        let content = dayColumn(day)
            .frame(minWidth: 44, maxWidth: .infinity, minHeight: 44)

        if let route = defaultRoute, let onRoute {
            Button {
                onRoute(route)
            } label: {
                content.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(speech)
            .accessibilityIdentifier("kitV1.calendarDay.\(day.dateKey)")
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(speech)
                .accessibilityIdentifier("kitV1.calendarDay.\(day.dateKey)")
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
    let spec: KitV1CardSpec
    let axisBody: KitV1AxisBody
    let defaultRoute: KitV1Route?
    var onRoute: ((KitV1Route) -> Void)? = nil

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

    private var elevatedDotsWithIndex: [(index: Int, dot: KitV1DotMark)] {
        dots.enumerated().compactMap { idx, dot in
            (dot.picture != nil && dot.yLane != nil) ? (idx, dot) : nil
        }
    }

    private var baseDotsWithIndex: [(index: Int, dot: KitV1DotMark)] {
        dots.enumerated().compactMap { idx, dot in
            !(dot.picture != nil && dot.yLane != nil) ? (idx, dot) : nil
        }
    }

    private var maxLane: Int {
        Int((elevatedDotsWithIndex.compactMap { $0.dot.yLane }.max() ?? 0).rounded())
    }

    private var trackHeight: CGFloat {
        CGFloat(maxLane + 1) * 40 + 74
    }

    private var visibleFooterMarks: [KitV1Mark] {
        let footers = axisBody.footerMarks ?? []
        guard !elevatedDotsWithIndex.isEmpty else { return footers }
        return footers.filter { mark in
            if case .word(let w) = mark, w.style == .pill {
                return false
            }
            return true
        }
    }

    private var lowEndBaseDots: [KitV1DotMark] {
        let threshold = axisBody.highlightBand?.lo ?? axisBody.scale.min
        return baseDotsWithIndex
            .map(\.dot)
            .filter { $0.x <= threshold }
            .sorted { a, b in
                if a.x != b.x { return a.x < b.x }
                return Self.entityName(from: a) < Self.entityName(from: b)
            }
    }

    private var highEndBaseDots: [KitV1DotMark] {
        let threshold = axisBody.highlightBand?.hi ?? axisBody.scale.max
        return baseDotsWithIndex
            .map(\.dot)
            .filter { $0.x >= threshold }
            .sorted { a, b in
                if a.x != b.x { return a.x > b.x }
                return Self.entityName(from: a) < Self.entityName(from: b)
            }
    }

    private var sortedElevatedDots: [(index: Int, dot: KitV1DotMark)] {
        elevatedDotsWithIndex.sorted { a, b in
            if a.dot.x != b.dot.x { return a.dot.x > b.dot.x }
            return Self.entityName(from: a.dot) < Self.entityName(from: b.dot)
        }
    }

    static func entityName(from dot: KitV1DotMark) -> String {
        let raw = dot.label.trimmingCharacters(in: .whitespacesAndNewlines)
        if let colon = raw.firstIndex(of: ":") {
            let prefix = raw[..<colon].trimmingCharacters(in: .whitespacesAndNewlines)
            if !prefix.isEmpty { return prefix }
        }
        if !raw.isEmpty { return raw }
        let alt = dot.picture?.alt.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return alt.isEmpty ? "Marker" : alt
    }

    static func formatEndNamesLine(_ names: [String], maxChars: Int = 46) -> String {
        var unique: [String] = []
        var seen = Set<String>()
        for raw in names {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, !seen.contains(trimmed) else { continue }
            seen.insert(trimmed)
            unique.append(trimmed)
        }
        guard !unique.isEmpty else { return "" }
        let full = unique.joined(separator: ", ")
        if full.count <= maxChars {
            return full
        }

        var chosen: [String] = []
        for (idx, name) in unique.enumerated() {
            let candidateList = chosen + [name]
            let remaining = unique.count - candidateList.count
            let suffix = remaining > 0 ? " +\(remaining)" : ""
            let candidate = candidateList.joined(separator: ", ") + suffix
            if idx == 0 || candidate.count <= maxChars {
                chosen.append(name)
            } else {
                break
            }
        }
        let remaining = unique.count - chosen.count
        return remaining > 0
            ? chosen.joined(separator: ", ") + " +\(remaining)"
            : chosen.joined(separator: ", ")
    }

    private func compactDotValue(_ dot: KitV1DotMark) -> String {
        let scale = axisBody.scale
        let isPercent = scale.scaleKind == .percent
            || scale.unit == "%"
            || scale.ticks.contains { $0.label.contains("%") }
        let scaled: Double = {
            if isPercent, scale.max <= 1.0, abs(dot.x) <= 1.0 {
                return dot.x * 100.0
            }
            return dot.x
        }()
        if isPercent {
            if scaled > 0 && scaled < 1.0 {
                return "<1%"
            }
            return "\(Int(scaled.rounded()))%"
        }
        let formatted = abs(scaled.rounded() - scaled) < 0.05
            ? "\(Int(scaled.rounded()))"
            : String(format: "%.1f", scaled)
        let unit = scale.unit.trimmingCharacters(in: .whitespacesAndNewlines)
        return unit.isEmpty ? formatted : "\(formatted)\(unit)"
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
                if dynamicTypeSize.isAccessibilitySize && !axisBody.scale.ticks.isEmpty {
                    scaleTicksView
                }
            }

            if !elevatedDotsWithIndex.isEmpty && dynamicTypeSize.isAccessibilitySize {
                accessibleBubbleTeamsList
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
                    ForEach(Array(series.enumerated()), id: \.element.id) { idx, row in
                        axisSeriesRow(row, index: idx, total: series.count)
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
                axisEndSummariesView(summaries: summaries)
            }

            if !visibleFooterMarks.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(visibleFooterMarks.enumerated()), id: \.offset) { _, mark in
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var accessibleBubbleTeamsList: some View {
        let sorted = sortedElevatedDots
        VStack(alignment: .leading, spacing: 0) {
            if let bandLabel = axisBody.highlightBand?.label.trimmingCharacters(in: .whitespacesAndNewlines),
               !bandLabel.isEmpty {
                Text(bandLabel.uppercased())
                    .font(.caption.weight(.bold))
                    .tracking(0.6)
                    .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
            }
            ForEach(sorted, id: \.index) { item in
                Rectangle()
                    .fill(KitTones366B.divider(for: colorScheme))
                    .frame(height: 1)

                accessibleBubbleRow(item: item)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(KitTones366B.elevatedBackground(for: colorScheme))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func accessibleBubbleRow(item: (index: Int, dot: KitV1DotMark)) -> some View {
        let dot = item.dot
        let name = Self.entityName(from: dot)
        let value = compactDotValue(dot)
        let speech = KitAccessibilitySpeech366B.axisDotSpeech(
            dot: dot,
            axisBody: axisBody,
            index: item.index,
            total: dots.count,
            spec: spec
        )
        let rowContent = Group {
            if dynamicTypeSize >= .accessibility3 {
                (Text(name) + Text("  ") + Text(value).bold().monospacedDigit())
                    .font(.footnote)
                    .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(name)
                        .font(.footnote)
                        .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Text(value)
                        .font(.footnote.weight(.bold).monospacedDigit())
                        .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)

        if let route = defaultRoute, let onRoute {
            Button {
                onRoute(route)
            } label: {
                rowContent.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(speech)
            .accessibilityIdentifier("kitV1.axisBubbleRow.\(item.index)")
        } else {
            rowContent
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(speech)
                .accessibilityIdentifier("kitV1.axisBubbleRow.\(item.index)")
        }
    }

    @ViewBuilder
    private func axisEndSummariesView(summaries: [KitV1Mark]) -> some View {
        let shouldShowEndNames = !elevatedDotsWithIndex.isEmpty
            && !baseDotsWithIndex.isEmpty
            && axisBody.highlightBand != nil

        if shouldShowEndNames {
            let endNamesByIndex: [[String]] = [
                lowEndBaseDots.map { Self.entityName(from: $0) },
                highEndBaseDots.map { Self.entityName(from: $0) }
            ]
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(summaries.enumerated()), id: \.offset) { idx, mark in
                    if case .word(let w) = mark {
                        let serverProvidesNames = !(w.secondaryText ?? "")
                            .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            || w.text.contains(",")
                            || w.text.contains("·")
                        let endNames = idx < endNamesByIndex.count ? endNamesByIndex[idx] : []
                        let derivedLine = serverProvidesNames ? "" : Self.formatEndNamesLine(endNames)

                        if serverProvidesNames {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(w.text)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                                    .fixedSize(horizontal: false, vertical: true)
                                if let sec = w.secondaryText, !sec.isEmpty {
                                    Text(sec)
                                        .font(.caption2)
                                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityElement(children: .combine)
                            .accessibilityLabel(KitAccessibilitySpeech366B.expandPercent(
                                [w.text, w.secondaryText].compactMap { $0 }.joined(separator: ", ")
                            ))
                        } else {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(w.text)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                                    .fixedSize(horizontal: false, vertical: true)
                                if !derivedLine.isEmpty {
                                    Text(derivedLine)
                                        .font(.caption2)
                                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityElement(children: .combine)
                            .accessibilityLabel(KitAccessibilitySpeech366B.expandPercent(
                                derivedLine.isEmpty ? w.text : "\(w.text), \(derivedLine)"
                            ))
                        }
                    } else {
                        KitMarkView366B(mark: mark)
                    }
                }
            }
        } else if dynamicTypeSize.isAccessibilitySize {
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

    @ViewBuilder
    private func axisSeriesRow(_ row: KitV1AxisSeries, index: Int, total: Int) -> some View {
        let speech = KitAccessibilitySpeech366B.axisSeriesSpeech(
            series: row,
            axisBody: axisBody,
            index: index,
            total: total,
            spec: spec
        )
        let content = VStack(alignment: .leading, spacing: 4) {
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
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)

        if let route = defaultRoute, let onRoute {
            Button {
                onRoute(route)
            } label: {
                content.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(speech)
            .accessibilityIdentifier("kitV1.axisSeries.\(row.id)")
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(speech)
                .accessibilityIdentifier("kitV1.axisSeries.\(row.id)")
        }
    }

    @ViewBuilder
    private var scaleTicksView: some View {
        let ticks = axisBody.scale.ticks
        Group {
            if dynamicTypeSize.isAccessibilitySize, let first = ticks.first {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(first.label)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                        .fixedSize(horizontal: false, vertical: true)
                    if ticks.count > 1, let last = ticks.last {
                        Spacer(minLength: 8)
                        Text(last.label)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                            .multilineTextAlignment(.trailing)
                            .fixedSize(horizontal: false, vertical: true)
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
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(KitAccessibilitySpeech366B.axisScaleSpeech(axisBody: axisBody))
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
        let showInlineTicks = !dynamicTypeSize.isAccessibilitySize
        let totalH = showInlineTicks ? trackHeight : max(80, trackHeight - 18)
        let baselineY = showInlineTicks ? totalH - 26 : totalH - 8
        let ticks = axisBody.scale.ticks
        let visibleTicks = axisPlotVisibleTicks
        let scaleSpeech = KitAccessibilitySpeech366B.axisScaleSpeech(axisBody: axisBody)

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
                    .accessibilityHidden(true)
                }

                Rectangle()
                    .fill(KitTones366B.cardBorder(for: colorScheme))
                    .frame(width: max(1, w - 16), height: 1.5)
                    .offset(x: 8, y: baselineY)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(scaleSpeech)
                    .accessibilityHidden(dynamicTypeSize.isAccessibilitySize)

                ForEach(baseDotsWithIndex, id: \.index) { item in
                    let idx = item.index
                    let dot = item.dot
                    let px = clampedX(dot.x, width: w, inset: 10)
                    let py = baselineY - 7 - CGFloat(idx % 3) * 5
                    let speech = KitAccessibilitySpeech366B.axisDotSpeech(
                        dot: dot,
                        axisBody: axisBody,
                        index: idx,
                        total: dots.count,
                        spec: spec
                    )
                    let marker = Circle()
                        .fill(KitTones366B.barColor(
                            hex: dot.color?.light,
                            darkHex: dot.colorDark ?? dot.color?.dark,
                            fallbackIndex: idx,
                            scheme: colorScheme
                        ))
                        .overlay(Circle().stroke(KitTones366B.cardBackground(for: colorScheme), lineWidth: 1.25))
                        .frame(width: 9, height: 9)
                        .frame(width: 46, height: 46)
                        .contentShape(Rectangle())

                    if let route = defaultRoute, let onRoute {
                        Button {
                            onRoute(route)
                        } label: {
                            marker
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(speech)
                        .accessibilityIdentifier("kitV1.axisDot.\(idx)")
                        .position(x: px, y: py)
                    } else {
                        marker
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel(speech)
                            .accessibilityIdentifier("kitV1.axisDot.\(idx)")
                            .position(x: px, y: py)
                    }
                }

                ForEach(elevatedDotsWithIndex, id: \.index) { item in
                    let idx = item.index
                    let dot = item.dot
                    let lane = CGFloat(max(0, Int((dot.yLane ?? 0).rounded())))
                    let px = clampedX(dot.x, width: w, inset: 16)
                    let py = baselineY - 26 - lane * 40
                    let speech = KitAccessibilitySpeech366B.axisDotSpeech(
                        dot: dot,
                        axisBody: axisBody,
                        index: idx,
                        total: dots.count,
                        spec: spec
                    )
                    if let pic = dot.picture {
                        let marker = VStack(spacing: 1) {
                            KitPictureMarkView366B(mark: pic, fixedSquareBox: 24)
                            Text(compactDotValue(dot))
                                .font(.system(size: 10, weight: .bold).monospacedDigit())
                                .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                                .dynamicTypeSize(...DynamicTypeSize.large)
                                .lineLimit(1)
                                .fixedSize()
                        }
                        .frame(width: 46, height: 46)
                        .contentShape(Rectangle())
                        if let route = defaultRoute, let onRoute {
                            Button {
                                onRoute(route)
                            } label: {
                                marker
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(speech)
                            .accessibilityIdentifier("kitV1.axisDot.\(idx)")
                            .accessibilityHidden(dynamicTypeSize.isAccessibilitySize)
                            .position(x: px, y: py)
                        } else {
                            marker
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel(speech)
                                .accessibilityIdentifier("kitV1.axisDot.\(idx)")
                                .accessibilityHidden(dynamicTypeSize.isAccessibilitySize)
                                .position(x: px, y: py)
                        }
                    }
                }

                if showInlineTicks {
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
                            .accessibilityHidden(true)
                    }
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
