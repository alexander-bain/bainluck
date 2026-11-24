import Foundation

/// Ruling 366: B / #13551 — Version 1 Kit cross-platform contract & fail-closed decoding.
///
/// Meaning vs Cosmetic contract (Fable 11:04 PM PT / Atlas #13551 agreement):
/// - **Meaning-carrying (unknown value fails closed to `nil` -> today's standard card):**
///   `kit_version`, `layout`, `mark`, `bar_style`, `scale.scale_kind`, `row_layout`,
///   `number.unit`, adaptive `{light, dark}` `#rrggbb` colors (bare hex strings rejected),
///   HTTPS `picture.url`, non-empty `body`, and empty `refusal_reason` / `!fallback_today`.
/// - **Cosmetic (unknown value decodes to default; never triggers fallback):**
///   `variant`, `style`, `tone`, `align`, `width`, `size`, `prominence`,
///   `header_layout`, `highlight_role`, `contain`, `picture.subject_kind`.
enum KitV1Contract366B {
    static let supportedKitVersion = 1
}

private extension KeyedDecodingContainer {
    /// Decodes a cosmetic `String`-backed enum cleanly, returning `nil` on unknown string tokens
    /// instead of throwing, while still throwing if a non-string JSON type is supplied.
    func decodeCosmeticIfPresent<T: RawRepresentable>(
        _ type: T.Type,
        forKey key: Key
    ) throws -> T? where T.RawValue == String {
        guard let raw = try decodeIfPresent(String.self, forKey: key) else {
            return nil
        }
        return T(rawValue: raw)
    }
}

nonisolated enum KitV1Layout: String, Codable, CaseIterable, Equatable, Sendable {
    case stack
    case grid
    case calendar
    case axis
}

nonisolated enum KitV1MarkKind: String, Codable, CaseIterable, Equatable, Sendable {
    case picture
    case word
    case number
    case bar
    case tile
    case ring
    case dot
    case line
}

nonisolated enum KitV1Tone: String, Codable, Equatable, Sendable {
    case primary
    case secondary
    case muted
    case accent
    case warn
}

nonisolated enum KitV1Align: String, Codable, Equatable, Sendable {
    case left
    case center
    case right
}

nonisolated enum KitV1Width: String, Codable, Equatable, Sendable {
    case xs
    case sm
    case md
    case flex
    case auto
}

nonisolated struct KitV1SourceMark: Codable, Equatable, Sendable {
    let label: String
    let count: Int?
}

nonisolated struct KitV1Route: Codable, Equatable, Sendable {
    enum Kind: String, Codable, Equatable, Sendable {
        case collection
        case event
        case market
        case team
    }

    let kind: Kind
    let id: Int?
    let slug: String?
}

// MARK: - 8 Shared Mark Primitives

nonisolated struct KitV1PictureMark: Codable, Equatable, Sendable {
    enum Size: String, Codable, Equatable, Sendable {
        case xs
        case sm
        case md
    }

    let url: String
    let alt: String
    let subjectKind: String
    let size: Size?
    let contain: Bool?

    init(url: String, alt: String, subjectKind: String, size: Size? = nil, contain: Bool? = nil) {
        self.url = url
        self.alt = alt
        self.subjectKind = subjectKind
        self.size = size
        self.contain = contain
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let rawURL = try c.decode(String.self, forKey: .url)
        guard Self.isAllowedHTTPSURL(rawURL) else {
            throw DecodingError.dataCorruptedError(
                forKey: .url,
                in: c,
                debugDescription: "Kit picture URL must use https://"
            )
        }
        url = rawURL
        alt = try c.decode(String.self, forKey: .alt)
        subjectKind = try c.decodeIfPresent(String.self, forKey: .subjectKind) ?? "topic"
        size = try c.decodeCosmeticIfPresent(Size.self, forKey: .size)
        contain = try c.decodeIfPresent(Bool.self, forKey: .contain)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(url, forKey: .url)
        try c.encode(alt, forKey: .alt)
        try c.encode(subjectKind, forKey: .subjectKind)
        try c.encodeIfPresent(size, forKey: .size)
        try c.encodeIfPresent(contain, forKey: .contain)
    }

    private enum CodingKeys: String, CodingKey {
        case url, alt, subjectKind, size, contain
    }

    static func isAllowedHTTPSURL(_ raw: String) -> Bool {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("https://"),
              let parsed = URL(string: trimmed),
              parsed.scheme?.lowercased() == "https",
              parsed.host?.isEmpty == false else {
            return false
        }
        return true
    }
}

nonisolated struct KitV1WordMark: Codable, Equatable, Sendable {
    enum Style: String, Codable, Equatable, Sendable {
        case row
        case sub
        case kicker
        case pill
        case meta
        case rank
        case heroLabel = "hero_label"
    }

    let text: String
    let secondaryText: String?
    let style: Style?
    let tone: KitV1Tone?
    let align: KitV1Align?
    let width: KitV1Width?
    let bold: Bool?

    init(
        text: String,
        secondaryText: String? = nil,
        style: Style? = nil,
        tone: KitV1Tone? = nil,
        align: KitV1Align? = nil,
        width: KitV1Width? = nil,
        bold: Bool? = nil
    ) {
        self.text = text
        self.secondaryText = secondaryText
        self.style = style
        self.tone = tone
        self.align = align
        self.width = width
        self.bold = bold
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        text = try c.decode(String.self, forKey: .text)
        secondaryText = try c.decodeIfPresent(String.self, forKey: .secondaryText)
        style = try c.decodeCosmeticIfPresent(Style.self, forKey: .style)
        tone = try c.decodeCosmeticIfPresent(KitV1Tone.self, forKey: .tone)
        align = try c.decodeCosmeticIfPresent(KitV1Align.self, forKey: .align)
        width = try c.decodeCosmeticIfPresent(KitV1Width.self, forKey: .width)
        bold = try c.decodeIfPresent(Bool.self, forKey: .bold)
    }

    private enum CodingKeys: String, CodingKey {
        case text, secondaryText, style, tone, align, width, bold
    }
}

nonisolated struct KitV1NumberMark: Codable, Equatable, Sendable {
    enum Unit: String, Codable, Equatable, Sendable {
        case percent = "%"
        case days
        case oneInN = "one_in_n"
    }

    enum Prominence: String, Codable, Equatable, Sendable {
        case hero
        case primary
        case cell
        case secondary
    }

    let value: Double
    let display: String
    /// Meaning-carrying: unknown `unit` throws -> card fails closed.
    let unit: Unit?
    let tone: KitV1Tone?
    let prominence: Prominence?
    let align: KitV1Align?
    let width: KitV1Width?

    init(
        value: Double,
        display: String,
        unit: Unit? = nil,
        tone: KitV1Tone? = nil,
        prominence: Prominence? = nil,
        align: KitV1Align? = nil,
        width: KitV1Width? = nil
    ) {
        self.value = value
        self.display = display
        self.unit = unit
        self.tone = tone
        self.prominence = prominence
        self.align = align
        self.width = width
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        value = try c.decode(Double.self, forKey: .value)
        display = try c.decode(String.self, forKey: .display)
        unit = try c.decodeIfPresent(Unit.self, forKey: .unit)
        tone = try c.decodeCosmeticIfPresent(KitV1Tone.self, forKey: .tone)
        prominence = try c.decodeCosmeticIfPresent(Prominence.self, forKey: .prominence)
        align = try c.decodeCosmeticIfPresent(KitV1Align.self, forKey: .align)
        width = try c.decodeCosmeticIfPresent(KitV1Width.self, forKey: .width)
    }

    private enum CodingKeys: String, CodingKey {
        case value, display, unit, tone, prominence, align, width
    }
}

/// Meaning-carrying adaptive color pair (`{"light": "#rrggbb", "dark": "#rrggbb"}`).
/// Raw bare hex strings are rejected per Atlas `f066538361` and Fable 11:04 PM PT verdict.
nonisolated struct KitV1AdaptiveHex: Codable, Equatable, Sendable {
    let light: String
    let dark: String

    init(light: String, dark: String) {
        self.light = light
        self.dark = dark
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let lightRaw = try c.decode(String.self, forKey: .light)
        let darkRaw = try c.decode(String.self, forKey: .dark)
        guard Self.isValidHex(lightRaw) else {
            throw DecodingError.dataCorruptedError(
                forKey: .light,
                in: c,
                debugDescription: "Invalid light adaptive hex color: \(lightRaw)"
            )
        }
        guard Self.isValidHex(darkRaw) else {
            throw DecodingError.dataCorruptedError(
                forKey: .dark,
                in: c,
                debugDescription: "Invalid dark adaptive hex color: \(darkRaw)"
            )
        }
        self.light = lightRaw
        self.dark = darkRaw
    }

    static func isValidHex(_ raw: String) -> Bool {
        guard raw.count == 7, raw.hasPrefix("#") else { return false }
        return raw.dropFirst().allSatisfy(\.isHexDigit)
    }

    private enum CodingKeys: String, CodingKey {
        case light
        case dark
    }
}

nonisolated struct KitV1BarSegment: Codable, Equatable, Sendable {
    let fill: Double
    let color: KitV1AdaptiveHex?
    let colorDark: String?
    let label: String?
}

nonisolated struct KitV1BarMark: Codable, Equatable, Sendable {
    enum BarStyle: String, Codable, Equatable, Sendable {
        case single
        case split
        case range
    }

    /// Meaning-carrying: if specified, must be `single | split | range`; unknown throws.
    let barStyle: BarStyle
    let fill: Double?
    let fillColor: KitV1AdaptiveHex?
    let fillColorDark: String?
    let segments: [KitV1BarSegment]?
    let lo: Double?
    let hi: Double?
    let openLo: Bool?
    let openHi: Bool?
    let pctLabel: String?
    let width: KitV1Width?

    init(
        barStyle: BarStyle = .single,
        fill: Double? = nil,
        fillColor: KitV1AdaptiveHex? = nil,
        fillColorDark: String? = nil,
        segments: [KitV1BarSegment]? = nil,
        lo: Double? = nil,
        hi: Double? = nil,
        openLo: Bool? = nil,
        openHi: Bool? = nil,
        pctLabel: String? = nil,
        width: KitV1Width? = nil
    ) {
        self.barStyle = barStyle
        self.fill = fill
        self.fillColor = fillColor
        self.fillColorDark = fillColorDark
        self.segments = segments
        self.lo = lo
        self.hi = hi
        self.openLo = openLo
        self.openHi = openHi
        self.pctLabel = pctLabel
        self.width = width
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        barStyle = try c.decodeIfPresent(BarStyle.self, forKey: .barStyle) ?? .single
        fill = try c.decodeIfPresent(Double.self, forKey: .fill)
        fillColor = try c.decodeIfPresent(KitV1AdaptiveHex.self, forKey: .fillColor)
        fillColorDark = try c.decodeIfPresent(String.self, forKey: .fillColorDark)
        segments = try c.decodeIfPresent([KitV1BarSegment].self, forKey: .segments)
        lo = try c.decodeIfPresent(Double.self, forKey: .lo)
        hi = try c.decodeIfPresent(Double.self, forKey: .hi)
        openLo = try c.decodeIfPresent(Bool.self, forKey: .openLo)
        openHi = try c.decodeIfPresent(Bool.self, forKey: .openHi)
        pctLabel = try c.decodeIfPresent(String.self, forKey: .pctLabel)
        width = try c.decodeCosmeticIfPresent(KitV1Width.self, forKey: .width)
    }

    private enum CodingKeys: String, CodingKey {
        case barStyle, fill, fillColor, fillColorDark, segments, lo, hi, openLo, openHi, pctLabel, width
    }
}

nonisolated struct KitV1TileMark: Codable, Equatable, Sendable {
    enum HighlightRole: String, Codable, Equatable, Sendable {
        case dayPeak = "day_peak"
        case rowPeak = "row_peak"
        case columnPeak = "column_peak"
    }

    let shade: Double
    let topLabel: String?
    let centerLabel: String
    let bottomLabel: String?
    let muted: Bool?
    let highlightRole: HighlightRole?

    init(
        shade: Double,
        topLabel: String? = nil,
        centerLabel: String,
        bottomLabel: String? = nil,
        muted: Bool? = nil,
        highlightRole: HighlightRole? = nil
    ) {
        self.shade = shade
        self.topLabel = topLabel
        self.centerLabel = centerLabel
        self.bottomLabel = bottomLabel
        self.muted = muted
        self.highlightRole = highlightRole
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        shade = try c.decode(Double.self, forKey: .shade)
        topLabel = try c.decodeIfPresent(String.self, forKey: .topLabel)
        centerLabel = try c.decode(String.self, forKey: .centerLabel)
        bottomLabel = try c.decodeIfPresent(String.self, forKey: .bottomLabel)
        muted = try c.decodeIfPresent(Bool.self, forKey: .muted)
        highlightRole = try c.decodeCosmeticIfPresent(HighlightRole.self, forKey: .highlightRole)
    }

    private enum CodingKeys: String, CodingKey {
        case shade, topLabel, centerLabel, bottomLabel, muted, highlightRole
    }
}

nonisolated struct KitV1RingMark: Codable, Equatable, Sendable {
    let progress: Double
    let label: String?
    let tone: KitV1Tone?

    init(progress: Double, label: String? = nil, tone: KitV1Tone? = nil) {
        self.progress = progress
        self.label = label
        self.tone = tone
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        progress = try c.decode(Double.self, forKey: .progress)
        label = try c.decodeIfPresent(String.self, forKey: .label)
        tone = try c.decodeCosmeticIfPresent(KitV1Tone.self, forKey: .tone)
    }

    private enum CodingKeys: String, CodingKey {
        case progress, label, tone
    }
}

nonisolated struct KitV1DotMark: Codable, Equatable, Sendable {
    let x: Double
    let yLane: Double?
    let label: String
    let color: KitV1AdaptiveHex?
    let colorDark: String?
    let inBand: Bool?
    let picture: KitV1PictureMark?
}

nonisolated struct KitV1LinePoint: Codable, Equatable, Sendable {
    let x: Double
    let y: Double
    let label: String?
}

nonisolated struct KitV1LineMark: Codable, Equatable, Sendable {
    let points: [KitV1LinePoint]
    let dashed: Bool?
    let color: KitV1AdaptiveHex?
    let colorDark: String?
    let threshold: Double?
}

nonisolated enum KitV1Mark: Codable, Equatable, Sendable {
    case picture(KitV1PictureMark)
    case word(KitV1WordMark)
    case number(KitV1NumberMark)
    case bar(KitV1BarMark)
    case tile(KitV1TileMark)
    case ring(KitV1RingMark)
    case dot(KitV1DotMark)
    case line(KitV1LineMark)

    private enum DiscriminatorKey: String, CodingKey {
        case mark
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: DiscriminatorKey.self)
        let kindString = try c.decode(String.self, forKey: .mark)
        guard let kind = KitV1MarkKind(rawValue: kindString) else {
            throw DecodingError.dataCorruptedError(
                forKey: .mark,
                in: c,
                debugDescription: "Unknown kit v1 mark: \(kindString)"
            )
        }
        switch kind {
        case .picture: self = .picture(try KitV1PictureMark(from: decoder))
        case .word: self = .word(try KitV1WordMark(from: decoder))
        case .number: self = .number(try KitV1NumberMark(from: decoder))
        case .bar: self = .bar(try KitV1BarMark(from: decoder))
        case .tile: self = .tile(try KitV1TileMark(from: decoder))
        case .ring: self = .ring(try KitV1RingMark(from: decoder))
        case .dot: self = .dot(try KitV1DotMark(from: decoder))
        case .line: self = .line(try KitV1LineMark(from: decoder))
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: DiscriminatorKey.self)
        switch self {
        case .picture(let m):
            try c.encode(KitV1MarkKind.picture.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .word(let m):
            try c.encode(KitV1MarkKind.word.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .number(let m):
            try c.encode(KitV1MarkKind.number.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .bar(let m):
            try c.encode(KitV1MarkKind.bar.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .tile(let m):
            try c.encode(KitV1MarkKind.tile.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .ring(let m):
            try c.encode(KitV1MarkKind.ring.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .dot(let m):
            try c.encode(KitV1MarkKind.dot.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        case .line(let m):
            try c.encode(KitV1MarkKind.line.rawValue, forKey: .mark)
            try m.encode(to: encoder)
        }
    }

    var isRenderable: Bool {
        switch self {
        case .picture(let p):
            return KitV1PictureMark.isAllowedHTTPSURL(p.url)
        case .word(let w):
            return !w.text.isEmpty
        case .number(let n):
            return n.value.isFinite && !n.display.isEmpty
        case .bar(let b):
            switch b.barStyle {
            case .single:
                guard let f = b.fill, f.isFinite else { return false }
                return true
            case .split:
                return !(b.segments ?? []).isEmpty
            case .range:
                guard let lo = b.lo, let hi = b.hi, lo.isFinite, hi.isFinite else { return false }
                return lo <= hi
            }
        case .tile(let t):
            return t.shade.isFinite && !t.centerLabel.isEmpty
        case .ring(let r):
            return r.progress.isFinite
        case .dot(let d):
            guard d.x.isFinite else { return false }
            if let pic = d.picture, !KitV1PictureMark.isAllowedHTTPSURL(pic.url) { return false }
            return true
        case .line(let l):
            return !l.points.isEmpty
        }
    }
}

// MARK: - 4 Generic Layout Bodies

nonisolated struct KitV1StackDivider: Codable, Equatable, Sendable {
    let style: String?
    let label: String?
}

nonisolated struct KitV1StackItem: Codable, Equatable, Sendable {
    let id: String
    let sportKey: String?
    let marks: [KitV1Mark]
    let subMarks: [KitV1Mark]?
    let route: KitV1Route?
    let dividerAfter: KitV1StackDivider?
}

nonisolated struct KitV1StackBody: Codable, Equatable, Sendable {
    enum HeaderLayout: String, Codable, Equatable, Sendable {
        case banner
        case split
        case none
    }

    let singleSportKey: String?
    let headerLayout: HeaderLayout?
    let headerMarks: [KitV1Mark]?
    let items: [KitV1StackItem]
    let footerMarks: [KitV1Mark]?

    init(
        singleSportKey: String? = nil,
        headerLayout: HeaderLayout? = nil,
        headerMarks: [KitV1Mark]? = nil,
        items: [KitV1StackItem],
        footerMarks: [KitV1Mark]? = nil
    ) {
        self.singleSportKey = singleSportKey
        self.headerLayout = headerLayout
        self.headerMarks = headerMarks
        self.items = items
        self.footerMarks = footerMarks
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        singleSportKey = try c.decodeIfPresent(String.self, forKey: .singleSportKey)
        headerLayout = try c.decodeCosmeticIfPresent(HeaderLayout.self, forKey: .headerLayout)
        headerMarks = try c.decodeIfPresent([KitV1Mark].self, forKey: .headerMarks)
        items = try c.decode([KitV1StackItem].self, forKey: .items)
        footerMarks = try c.decodeIfPresent([KitV1Mark].self, forKey: .footerMarks)
    }

    private enum CodingKeys: String, CodingKey {
        case singleSportKey, headerLayout, headerMarks, items, footerMarks
    }

    var isRenderable: Bool {
        guard !items.isEmpty else { return false }
        var sportKeys: Set<String> = []
        if let rootSport = singleSportKey?.trimmingCharacters(in: .whitespacesAndNewlines),
           !rootSport.isEmpty {
            sportKeys.insert(rootSport)
        }
        for item in items {
            guard !item.marks.isEmpty,
                  item.marks.allSatisfy(\.isRenderable) else {
                return false
            }
            if let subs = item.subMarks, !subs.allSatisfy(\.isRenderable) {
                return false
            }
            if let sk = item.sportKey?.trimmingCharacters(in: .whitespacesAndNewlines), !sk.isEmpty {
                sportKeys.insert(sk)
            }
        }
        // Rule 6 — never draw a mixed-sport slate as a single-sport stack.
        if sportKeys.count > 1 { return false }
        if let headers = headerMarks, !headers.allSatisfy(\.isRenderable) { return false }
        if let footers = footerMarks, !footers.allSatisfy(\.isRenderable) { return false }
        return true
    }
}

nonisolated struct KitV1GridColumn: Codable, Equatable, Sendable {
    let key: String
    let label: String
}

nonisolated struct KitV1GridCell: Codable, Equatable, Sendable {
    let columnKey: String
    let marks: [KitV1Mark]
    let route: KitV1Route?
}

nonisolated struct KitV1GridRow: Codable, Equatable, Sendable {
    let id: String
    let leading: [KitV1Mark]
    let cells: [KitV1GridCell]
}

nonisolated struct KitV1GridBody: Codable, Equatable, Sendable {
    enum RowLayout: String, Codable, Equatable, Sendable {
        case matrix
        case stackedCells = "stacked_cells"
    }

    let leadingLabel: String?
    let showColumnHeaders: Bool
    /// Meaning-carrying: unknown `row_layout` throws -> fails closed.
    let rowLayout: RowLayout
    let columns: [KitV1GridColumn]
    let rows: [KitV1GridRow]
    let footerMarks: [KitV1Mark]?

    var isRenderable: Bool {
        guard !columns.isEmpty, !rows.isEmpty else { return false }
        for row in rows {
            guard row.leading.allSatisfy(\.isRenderable) else { return false }
            for cell in row.cells {
                guard cell.marks.allSatisfy(\.isRenderable) else { return false }
            }
        }
        if let footers = footerMarks, !footers.allSatisfy(\.isRenderable) { return false }
        return true
    }
}

nonisolated struct KitV1CalendarDay: Codable, Equatable, Sendable {
    let dateKey: String
    let dailyPct: Double?
    let marks: [KitV1Mark]
}

nonisolated struct KitV1CalendarBody: Codable, Equatable, Sendable {
    let headerMarks: [KitV1Mark]?
    let days: [KitV1CalendarDay]
    let footerMarks: [KitV1Mark]?

    var isRenderable: Bool {
        guard days.count >= 2 else { return false }
        guard days.allSatisfy({ !$0.marks.isEmpty && $0.marks.allSatisfy(\.isRenderable) }) else {
            return false
        }
        if let headers = headerMarks, !headers.allSatisfy(\.isRenderable) { return false }
        if let footers = footerMarks, !footers.allSatisfy(\.isRenderable) { return false }
        return true
    }
}

nonisolated struct KitV1AxisTick: Codable, Equatable, Sendable {
    let x: Double
    let label: String
}

nonisolated struct KitV1AxisScale: Codable, Equatable, Sendable {
    enum ScaleKind: String, Codable, Equatable, Sendable {
        case percent
        case numeric
        case time
    }

    /// Meaning-carrying: unknown `scale_kind` throws -> fails closed.
    let scaleKind: ScaleKind
    let unit: String
    let min: Double
    let max: Double
    let ticks: [KitV1AxisTick]
}

nonisolated struct KitV1AxisHighlightBand: Codable, Equatable, Sendable {
    let lo: Double
    let hi: Double
    let label: String
}

nonisolated struct KitV1AxisSeries: Codable, Equatable, Sendable {
    let id: String
    let leading: [KitV1Mark]?
    let marks: [KitV1Mark]
}

nonisolated struct KitV1AxisBody: Codable, Equatable, Sendable {
    let scale: KitV1AxisScale
    let highlightBand: KitV1AxisHighlightBand?
    let marks: [KitV1Mark]?
    let series: [KitV1AxisSeries]?
    let summaryMarks: [KitV1Mark]?
    let footerMarks: [KitV1Mark]?

    var isRenderable: Bool {
        guard scale.min.isFinite, scale.max.isFinite,
              scale.min < scale.max, !scale.ticks.isEmpty else {
            return false
        }
        let hasMarks = !(marks ?? []).isEmpty
        let hasSeries = !(series ?? []).isEmpty
        guard hasMarks || hasSeries else { return false }
        if let direct = marks, !direct.allSatisfy(\.isRenderable) { return false }
        if let series {
            for s in series {
                if let lead = s.leading, !lead.allSatisfy(\.isRenderable) { return false }
                guard !s.marks.isEmpty, s.marks.allSatisfy(\.isRenderable) else { return false }
            }
        }
        if let summary = summaryMarks, !summary.allSatisfy(\.isRenderable) { return false }
        if let footers = footerMarks, !footers.allSatisfy(\.isRenderable) { return false }
        return true
    }
}

nonisolated enum KitV1Body: Equatable, Sendable {
    case stack(KitV1StackBody)
    case grid(KitV1GridBody)
    case calendar(KitV1CalendarBody)
    case axis(KitV1AxisBody)

    var isRenderable: Bool {
        switch self {
        case .stack(let b): return b.isRenderable
        case .grid(let b): return b.isRenderable
        case .calendar(let b): return b.isRenderable
        case .axis(let b): return b.isRenderable
        }
    }
}

// MARK: - Top-Level Spec

nonisolated struct KitV1CardSpec: Decodable, Equatable, Sendable, Identifiable {
    let kitVersion: Int
    let id: String
    let layout: KitV1Layout
    /// Optional cosmetic classification hint ignored at render time (`366: B`).
    let variant: String?
    let kicker: String?
    let commonHeadline: String?
    let statCaption: String?
    let sourceMark: KitV1SourceMark?
    let route: KitV1Route?
    let footnote: String?
    let disclosure: String?
    let body: KitV1Body

    private enum CodingKeys: String, CodingKey {
        case kitVersion
        case id
        case layout
        case variant
        case kicker
        case commonHeadline
        case statCaption
        case sourceMark
        case route
        case footnote
        case disclosure
        case refusalReason
        case fallbackToday
        case body
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)

        let version = try c.decode(Int.self, forKey: .kitVersion)
        guard version == KitV1Contract366B.supportedKitVersion else {
            throw DecodingError.dataCorruptedError(
                forKey: .kitVersion,
                in: c,
                debugDescription: "Unsupported kit_version: \(version)"
            )
        }

        let cardId = (try c.decode(String.self, forKey: .id))
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cardId.isEmpty else {
            throw DecodingError.dataCorruptedError(
                forKey: .id,
                in: c,
                debugDescription: "Kit card id cannot be empty"
            )
        }

        if let refusal = try c.decodeIfPresent(String.self, forKey: .refusalReason)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !refusal.isEmpty {
            throw DecodingError.dataCorruptedError(
                forKey: .refusalReason,
                in: c,
                debugDescription: "Kit card refused: \(refusal)"
            )
        }

        if (try c.decodeIfPresent(Bool.self, forKey: .fallbackToday)) == true {
            throw DecodingError.dataCorruptedError(
                forKey: .fallbackToday,
                in: c,
                debugDescription: "Kit card requested fallback to today's standard card"
            )
        }

        let rawLayout = try c.decode(String.self, forKey: .layout)
        guard let parsedLayout = KitV1Layout(rawValue: rawLayout) else {
            throw DecodingError.dataCorruptedError(
                forKey: .layout,
                in: c,
                debugDescription: "Unknown kit v1 layout: \(rawLayout)"
            )
        }

        let parsedBody: KitV1Body
        switch parsedLayout {
        case .stack:
            parsedBody = .stack(try c.decode(KitV1StackBody.self, forKey: .body))
        case .grid:
            parsedBody = .grid(try c.decode(KitV1GridBody.self, forKey: .body))
        case .calendar:
            parsedBody = .calendar(try c.decode(KitV1CalendarBody.self, forKey: .body))
        case .axis:
            parsedBody = .axis(try c.decode(KitV1AxisBody.self, forKey: .body))
        }

        guard parsedBody.isRenderable else {
            throw DecodingError.dataCorruptedError(
                forKey: .body,
                in: c,
                debugDescription: "Kit card body failed renderability checks"
            )
        }

        self.kitVersion = version
        self.id = cardId
        self.layout = parsedLayout
        self.variant = try c.decodeIfPresent(String.self, forKey: .variant)
        self.kicker = try c.decodeIfPresent(String.self, forKey: .kicker)
        self.commonHeadline = try c.decodeIfPresent(String.self, forKey: .commonHeadline)
        self.statCaption = try c.decodeIfPresent(String.self, forKey: .statCaption)
        self.sourceMark = try c.decodeIfPresent(KitV1SourceMark.self, forKey: .sourceMark)
        self.route = try c.decodeIfPresent(KitV1Route.self, forKey: .route)
        self.footnote = try c.decodeIfPresent(String.self, forKey: .footnote)
        self.disclosure = try c.decodeIfPresent(String.self, forKey: .disclosure)
        self.body = parsedBody
    }

    /// Strict fail-closed entry point. Returns `nil` for any unsupported version/layout/mark,
    /// unknown meaning-carrying value, bare hex, non-HTTPS URL, refusal, or invalid body so the caller
    /// keeps today's standard card.
    static func parse(from data: Data) -> KitV1CardSpec? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(KitV1CardSpec.self, from: data)
    }
}
