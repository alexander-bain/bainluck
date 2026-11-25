import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Preloaded Artwork Environment Seam (tests & previews only)

private struct KitPreloadedImagesKey366B: EnvironmentKey {
    static let defaultValue: [URL: PlatformImage] = [:]
}

private struct KitNowEnvironmentKey366B: EnvironmentKey {
    static let defaultValue: Date = Date()
}

extension EnvironmentValues {
    var kitPreloadedImages366B: [URL: PlatformImage] {
        get { self[KitPreloadedImagesKey366B.self] }
        set { self[KitPreloadedImagesKey366B.self] = newValue }
    }

    var kitNow366B: Date {
        get { self[KitNowEnvironmentKey366B.self] }
        set { self[KitNowEnvironmentKey366B.self] = newValue }
    }
}

// MARK: - Mark Dispatcher

/// Renders one of the 8 shared Kit v1 marks purely from its geometric payload.
struct KitMarkView366B: View {
    let mark: KitV1Mark
    var inheritedCountdownDeadlineIso: String? = nil

    var body: some View {
        switch mark {
        case .picture(let m):
            KitPictureMarkView366B(mark: m)
        case .word(let m):
            KitWordMarkView366B(mark: m, inheritedCountdownDeadlineIso: inheritedCountdownDeadlineIso)
        case .number(let m):
            KitNumberMarkView366B(mark: m)
        case .bar(let m):
            KitBarMarkView366B(mark: m)
        case .tile(let m):
            KitTileMarkView366B(mark: m)
        case .ring(let m):
            KitRingMarkView366B(mark: m)
        case .dot(let m):
            KitDotMarkView366B(mark: m)
        case .line(let m):
            KitLineMarkView366B(mark: m)
        }
    }
}

// MARK: - Initials Fallback (`387: A`)

/// Ruling 387: A — Delegates team/org/flag badges to `TeamLogoView.badge` (`TeamShortName`)
/// and person/film/topic initials to `PairedMetricPresentation.initials` with zero custom slicing.
nonisolated enum KitInitials366B {
    private static let connectorWords: Set<String> = ["&", "and", "of", "the"]

    static func initials(for raw: String, subjectKind: String? = nil) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "?" }

        if let kind = subjectKind,
           KitPictureShape366B.resolve(forSubjectKind: kind) == .containedCrest {
            let teamBadge = TeamLogoView.badge(teamName: trimmed, opponentName: nil)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !teamBadge.isEmpty {
                return teamBadge
            }
        }

        let parts = trimmed.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        if parts.count == 1, let single = parts.first,
           (2...3).contains(single.count),
           single.contains(where: { $0.isLetter }),
           single.allSatisfy({ ($0.isLetter && $0.isUppercase) || $0.isNumber }) {
            return single
        }

        let substantive = parts.filter { !connectorWords.contains($0.lowercased()) }
        let input = substantive.count >= 2 ? substantive.joined(separator: " ") : trimmed
        let resolved = PairedMetricPresentation.initials(for: input)
        return resolved == "—" ? "?" : resolved
    }
}

/// Ruling 387: A — Circle initials badge matching sibling picture slot geometry while staying
/// invisible to VoiceOver (`.accessibilityHidden(true)`).
struct KitInitialsCircle366B: View {
    let name: String
    var subjectKind: String? = nil
    let box: CGSize

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let diameter = max(16, min(box.width, box.height))
        Circle()
            .fill(KitTones366B.elevatedBackground(for: colorScheme))
            .overlay(
                Circle()
                    .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
            )
            .overlay {
                Text(KitInitials366B.initials(for: name, subjectKind: subjectKind))
                    .font(.system(size: max(8.5, diameter * 0.38), weight: .bold))
                    .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            .frame(width: diameter, height: diameter)
            .frame(width: box.width, height: box.height)
            .accessibilityHidden(true)
    }
}

// MARK: - 1. Picture Mark (Unified Shape Rule)

/// Canonical Kit v1 picture shape rule (#13589 / Ruling 366: B):
/// - `person`: circle (aspect `.fill`, top-anchored face crop)
/// - `team` / `organization` / `flag`: contained crest (`aspectRatio(.fit)`) inside a
///   uniform `24×24` square box on every row (`32×32` at `md`) and uniform `24×24`
///   contained crest badge on every axis dot.
/// - `film`: upright `2:3` poster rectangle (`20×30` default, `24×36` at `md`, `.fill`).
/// - `topic` / fallback: uniform `24×24` rounded square (`32×32` at `md`, `.fill`).
enum KitPictureShape366B: Equatable {
    case roundPerson
    case containedCrest
    case uprightPoster
    case roundedTopic

    static func resolve(forSubjectKind kind: String) -> KitPictureShape366B {
        switch kind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "person":
            return .roundPerson
        case "team", "organization", "flag":
            return .containedCrest
        case "film":
            return .uprightPoster
        default:
            return .roundedTopic
        }
    }
}

struct KitPictureMarkView366B: View {
    let mark: KitV1PictureMark
    /// When set (e.g. elevated axis dot badges), enforces exact square box dimensions
    /// across every mark instance so crests render at identical sizes.
    var fixedSquareBox: CGFloat? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.kitPreloadedImages366B) private var preloadedImages
    @State private var loadedImage: PlatformImage?

    var pictureShape: KitPictureShape366B {
        KitPictureShape366B.resolve(forSubjectKind: mark.subjectKind)
    }

    static func boxSize(for mark: KitV1PictureMark, fixedSquareBox: CGFloat? = nil) -> CGSize {
        if let fixedSquareBox {
            return CGSize(width: fixedSquareBox, height: fixedSquareBox)
        }
        let isMd = (mark.size == .md)
        switch KitPictureShape366B.resolve(forSubjectKind: mark.subjectKind) {
        case .roundPerson:
            let side: CGFloat = isMd ? 32 : 24
            return CGSize(width: side, height: side)
        case .containedCrest:
            // Uniform box across all rows (`xs` and `sm` match at `24×24`).
            let side: CGFloat = isMd ? 32 : 24
            return CGSize(width: side, height: side)
        case .uprightPoster:
            let w: CGFloat = isMd ? 24 : 20
            return CGSize(width: w, height: w * 1.5)
        case .roundedTopic:
            let side: CGFloat = isMd ? 32 : 24
            return CGSize(width: side, height: side)
        }
    }

    var renderedBoxSize: CGSize {
        Self.boxSize(for: mark, fixedSquareBox: fixedSquareBox)
    }

    private var resolvedURL: URL? {
        guard KitV1PictureMark.isAllowedHTTPSURL(mark.url) else { return nil }
        return URL(string: mark.url.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private var activeImage: PlatformImage? {
        if let loadedImage { return loadedImage }
        if let url = resolvedURL, let preloaded = preloadedImages[url] { return preloaded }
        return nil
    }

    var body: some View {
        let box = renderedBoxSize
        let radius: CGFloat = {
            switch pictureShape {
            case .roundPerson: return box.width / 2
            case .containedCrest: return fixedSquareBox != nil ? (box.width / 2) : 6
            case .uprightPoster: return 4
            case .roundedTopic: return 6
            }
        }()

        Group {
            if let img = activeImage {
                switch pictureShape {
                case .roundPerson:
                    Image(platformImage: img)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: box.width, height: box.height, alignment: .top)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 0.75))

                case .containedCrest:
                    let needsLightBacking = colorScheme == .dark && TeamLogoView.needsDarkSurfaceBacking(img)
                    let backingFill: Color = needsLightBacking
                        ? Color.white.opacity(0.92)
                        : KitTones366B.elevatedBackground(for: colorScheme)
                    ZStack {
                        RoundedRectangle(cornerRadius: radius, style: .continuous)
                            .fill(backingFill)
                        Image(platformImage: img)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .padding(2.5)
                    }
                    .frame(width: box.width, height: box.height)
                    .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: radius, style: .continuous)
                            .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 0.75)
                    )

                case .uprightPoster:
                    Image(platformImage: img)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: box.width, height: box.height)
                        .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: radius, style: .continuous)
                                .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 0.75)
                        )

                case .roundedTopic:
                    Image(platformImage: img)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: box.width, height: box.height)
                        .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: radius, style: .continuous)
                                .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 0.75)
                        )
                }
            } else {
                fallbackBadge(box: box, radius: radius)
            }
        }
        .frame(width: box.width, height: box.height)
        .accessibilityHidden(true)
        .task(id: mark.url) {
            guard activeImage == nil, let url = resolvedURL else { return }
            loadedImage = await ImageCache.shared.image(for: url)
        }
    }

    private func fallbackBadge(box: CGSize, radius _: CGFloat) -> some View {
        KitInitialsCircle366B(name: mark.alt, subjectKind: mark.subjectKind, box: box)
    }
}

// MARK: - 2. Word Mark

struct KitWordMarkView366B: View {
    let mark: KitV1WordMark
    var inheritedCountdownDeadlineIso: String? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.kitNow366B) private var kitNow

    private var heroCountdownText: String {
        guard let deadline = mark.deadlineIso ?? inheritedCountdownDeadlineIso,
              let days = KitCountdownClock366B.daysLeft(from: deadline, now: kitNow) else {
            return mark.text
        }
        if days <= 0 {
            return "ends today"
        }
        if days == 1 {
            return "day left"
        }
        return "days left"
    }

    private var textAlignment: TextAlignment {
        switch mark.align ?? .left {
        case .left: return .leading
        case .center: return .center
        case .right: return .trailing
        }
    }

    private var frameAlignment: Alignment {
        switch mark.align ?? .left {
        case .left: return .leading
        case .center: return .center
        case .right: return .trailing
        }
    }

    var body: some View {
        let baseColor = KitTones366B.textColor(for: mark.tone, scheme: colorScheme)
        Group {
            switch mark.style ?? .row {
            case .heroLabel:
                VStack(alignment: .leading, spacing: 2) {
                    Text(heroCountdownText)
                        .font(.subheadline.weight(mark.bold == false ? .medium : .bold))
                        .foregroundStyle(baseColor)
                        .fixedSize(horizontal: false, vertical: true)
                    if let secondary = mark.secondaryText, !secondary.isEmpty {
                        Text(secondary)
                            .font(.caption)
                            .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)

            case .meta:
                VStack(alignment: (mark.align == .right) ? .trailing : ((mark.align == .center) ? .center : .leading), spacing: 1) {
                    Text(mark.text)
                        .font(.caption2.weight(mark.bold == true ? .semibold : .medium))
                        .foregroundStyle(baseColor)
                        .fixedSize(horizontal: false, vertical: true)
                    if let secondary = mark.secondaryText, !secondary.isEmpty {
                        Text(secondary)
                            .font(.caption2)
                            .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(minWidth: fixedMinWidth, maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)

            case .pill:
                Text(mark.text)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(baseColor)
                    .multilineTextAlignment(textAlignment)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .frame(maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(KitTones366B.elevatedBackground(for: colorScheme))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
                    )

            case .kicker:
                let kickerColor = mark.tone == nil
                    ? KitTones366B.brandAccent(for: colorScheme)
                    : KitTones366B.textColor(for: mark.tone, scheme: colorScheme)
                Text(mark.text.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(kickerColor)
                    .fixedSize(horizontal: false, vertical: true)

            case .rank:
                Text(mark.text)
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(KitTones366B.textColor(for: mark.tone ?? .muted, scheme: colorScheme))
                    .fixedSize(horizontal: true, vertical: false)

            case .sub, .row:
                let font: Font = (mark.style == .sub)
                    ? .caption.weight(mark.bold == true ? .semibold : .regular)
                    : .subheadline.weight(mark.bold == true ? .semibold : .regular)
                VStack(alignment: (mark.align == .right) ? .trailing : ((mark.align == .center) ? .center : .leading), spacing: 2) {
                    Text(mark.text)
                        .font(font)
                        .foregroundStyle(baseColor)
                        .multilineTextAlignment(textAlignment)
                        .fixedSize(horizontal: false, vertical: true)
                    if let secondary = mark.secondaryText, !secondary.isEmpty {
                        Text(secondary)
                            .font(.caption)
                            .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(minWidth: fixedMinWidth, maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)
            }
        }
    }

    private var fixedMinWidth: CGFloat? {
        switch mark.width {
        case .xs: return 34
        case .sm: return 68
        case .md: return 88
        case .flex, .auto, nil: return nil
        }
    }
}

// MARK: - 3. Number Mark

struct KitNumberMarkView366B: View {
    let mark: KitV1NumberMark

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.kitNow366B) private var kitNow

    private var displayedText: String {
        guard mark.unit == .days,
              let deadline = mark.deadlineIso,
              let days = KitCountdownClock366B.daysLeft(from: deadline, now: kitNow) else {
            return mark.display
        }
        return days <= 0 ? "Today" : "\(days)"
    }

    private var frameAlignment: Alignment {
        switch mark.align ?? .right {
        case .left: return .leading
        case .center: return .center
        case .right: return .trailing
        }
    }

    private var font: Font {
        switch mark.prominence ?? .primary {
        case .hero:
            return .title.weight(.heavy).monospacedDigit()
        case .primary:
            return (mark.unit == .oneInN)
                ? .subheadline.weight(.heavy).monospacedDigit()
                : .subheadline.weight(.bold).monospacedDigit()
        case .cell:
            return .footnote.weight(.bold).monospacedDigit()
        case .secondary:
            return .caption.weight(.semibold).monospacedDigit()
        }
    }

    private var minWidth: CGFloat? {
        switch mark.width {
        case .xs: return 36
        case .sm: return 42
        case .md: return 56
        case .flex, .auto, nil: return nil
        }
    }

    var body: some View {
        Text(displayedText)
            .font(font)
            .foregroundStyle(KitTones366B.textColor(for: mark.tone, scheme: colorScheme))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .frame(minWidth: minWidth, alignment: frameAlignment)
    }
}

// MARK: - 4. Bar Mark (Single, Split, Range)

struct KitBarMarkView366B: View {
    let mark: KitV1BarMark

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        switch mark.barStyle {
        case .split:
            splitBar
        case .range:
            rangeBar
        case .single:
            singleBar
        }
    }

    private var singleBar: some View {
        let clamped = min(1.0, max(0.03, mark.fill ?? 0.0))
        let fillColor = KitTones366B.barColor(
            hex: mark.fillColor?.light,
            darkHex: mark.fillColorDark ?? mark.fillColor?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        let targetWidth: CGFloat? = {
            switch mark.width {
            case .xs: return 40
            case .sm: return 56
            case .md: return 74
            case .flex, .auto, nil: return nil
            }
        }()
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(KitTones366B.trackBackground(for: colorScheme))
                Capsule()
                    .fill(fillColor)
                    .frame(width: max(4, geo.size.width * clamped))
            }
        }
        .frame(width: targetWidth, height: mark.width == .md ? 9 : 8)
        .frame(maxWidth: targetWidth == nil ? .infinity : targetWidth)
    }

    @ViewBuilder
    private var splitBar: some View {
        let segs = mark.segments ?? []
        if segs.count == 2 {
            let pair = KitTones366B.splitBarColors(
                leftHex: segs[0].color?.light,
                leftDarkHex: segs[0].colorDark ?? segs[0].color?.dark,
                rightHex: segs[1].color?.light,
                rightDarkHex: segs[1].colorDark ?? segs[1].color?.dark,
                scheme: colorScheme
            )
            GeometryReader { geo in
                let total = max(0.001, segs[0].fill + segs[1].fill)
                let leftFrac = min(0.95, max(0.05, segs[0].fill / total))
                HStack(spacing: 1) {
                    Rectangle().fill(pair.left).frame(width: max(3, (geo.size.width - 1) * leftFrac))
                    Rectangle().fill(pair.right)
                }
                .clipShape(Capsule())
            }
            .frame(height: 9)
            .frame(maxWidth: .infinity)
        } else {
            GeometryReader { geo in
                let total = max(0.001, segs.reduce(0.0) { $0 + max(0.0, $1.fill) })
                HStack(spacing: 1) {
                    ForEach(Array(segs.enumerated()), id: \.offset) { idx, seg in
                        let frac = max(0.0, seg.fill) / total
                        Rectangle()
                            .fill(KitTones366B.barColor(
                                hex: seg.color?.light,
                                darkHex: seg.colorDark ?? seg.color?.dark,
                                fallbackIndex: idx,
                                scheme: colorScheme
                            ))
                            .frame(width: max(2, geo.size.width * frac))
                    }
                }
                .clipShape(Capsule())
            }
            .frame(height: 9)
            .frame(maxWidth: .infinity)
        }
    }

    private var rangeBar: some View {
        let lo = min(1.0, max(0.0, mark.lo ?? 0.0))
        let hi = min(1.0, max(lo, mark.hi ?? lo))
        let accent = KitTones366B.barColor(
            hex: mark.fillColor?.light,
            darkHex: mark.fillColorDark ?? mark.fillColor?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        let label = mark.pctLabel ?? ""
        return VStack(alignment: .leading, spacing: 4) {
            if dynamicTypeSize.isAccessibilitySize && !label.isEmpty {
                Text(label)
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
            }
            GeometryReader { geo in
                let leftX = geo.size.width * lo
                let spanW = max(12, min(geo.size.width - leftX, geo.size.width * (hi - lo)))
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(KitTones366B.trackBackground(for: colorScheme))
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(accent.opacity(0.28))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .stroke(accent.opacity(0.90), lineWidth: 1)
                        )
                        .frame(width: spanW, height: 18)
                        .offset(x: leftX)
                    if !dynamicTypeSize.isAccessibilitySize && !label.isEmpty {
                        Text(label)
                            .font(.caption2.weight(.bold).monospacedDigit())
                            .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                            .frame(width: spanW >= 72 ? spanW : geo.size.width, height: 18)
                            .offset(x: spanW >= 72 ? leftX : 0)
                    }
                }
            }
            .frame(height: 20)
            .frame(maxWidth: .infinity)
        }
    }
}

// MARK: - 5. Tile Mark

struct KitTileMarkView366B: View {
    let mark: KitV1TileMark
    var compact: Bool = false

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let palette = KitTones366B.tilePalette(
            shade: mark.shade,
            highlightRole: mark.highlightRole,
            muted: mark.muted ?? false,
            scheme: colorScheme
        )
        let isAX = dynamicTypeSize.isAccessibilitySize
        VStack(spacing: isAX ? 3 : 2) {
            if let top = mark.topLabel, !top.isEmpty {
                Group {
                    if isAX {
                        Text(top)
                            .font(.caption2.weight(.medium))
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                    } else {
                        Text(top)
                            .font(.system(size: compact ? 9.5 : 10.5, weight: .medium))
                            .minimumScaleFactor(0.85)
                            .lineLimit(1)
                    }
                }
                .foregroundStyle(palette.secondaryForeground)
            }
            Group {
                if isAX {
                    Text(mark.centerLabel)
                        .font((compact ? Font.caption : Font.footnote).weight(.bold).monospacedDigit())
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Text(mark.centerLabel)
                        .font((compact ? Font.caption : Font.footnote).weight(.bold).monospacedDigit())
                        .minimumScaleFactor(0.85)
                        .lineLimit(1)
                }
            }
            .foregroundStyle(palette.foreground)
            if let bottom = mark.bottomLabel, !bottom.isEmpty {
                Group {
                    if isAX {
                        Text(bottom)
                            .font(.caption2.weight(.semibold).monospacedDigit())
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                    } else {
                        Text(bottom)
                            .font(.system(size: compact ? 9.5 : 10.5, weight: .semibold).monospacedDigit())
                            .minimumScaleFactor(0.8)
                            .lineLimit(1)
                    }
                }
                .foregroundStyle(palette.secondaryForeground)
            }
        }
        .padding(.horizontal, isAX ? 8 : (compact ? 2 : 6))
        .padding(.vertical, isAX ? 8 : (compact ? 5 : 6))
        .frame(minWidth: isAX ? 64 : 44, minHeight: isAX ? 44 : nil)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(palette.background)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(palette.border, lineWidth: 1)
        )
    }
}

// MARK: - 6. Ring Mark

struct KitRingMarkView366B: View {
    let mark: KitV1RingMark

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let clamped = min(1.0, max(0.0, mark.progress))
        let pct = Int((clamped * 100.0).rounded())
        let strokeColor = mark.tone == .muted
            ? KitTones366B.textColor(for: .muted, scheme: colorScheme)
            : KitTones366B.brandAccent(for: colorScheme)
        let boxSize: CGFloat = dynamicTypeSize >= .accessibility3 ? 78 : (dynamicTypeSize.isAccessibilitySize ? 58 : 30)
        ZStack {
            Circle()
                .stroke(KitTones366B.trackBackground(for: colorScheme), lineWidth: dynamicTypeSize.isAccessibilitySize ? 4 : 3)
            Circle()
                .trim(from: 0, to: clamped)
                .stroke(strokeColor, style: StrokeStyle(lineWidth: dynamicTypeSize.isAccessibilitySize ? 4 : 3, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(mark.label ?? "\(pct)%")
                .font(.caption2.weight(.bold).monospacedDigit())
                .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .frame(width: boxSize, height: boxSize)
    }
}

// MARK: - 7. Dot Mark

struct KitDotMarkView366B: View {
    let mark: KitV1DotMark

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let dotColor = KitTones366B.barColor(
            hex: mark.color?.light,
            darkHex: mark.colorDark ?? mark.color?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        Group {
            if let pic = mark.picture {
                KitPictureMarkView366B(mark: pic, fixedSquareBox: 24)
            } else {
                Circle()
                    .fill(dotColor)
                    .overlay(Circle().stroke(KitTones366B.cardBackground(for: colorScheme), lineWidth: 1.5))
                    .frame(width: 10, height: 10)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - 8. Line Mark

struct KitLineMarkView366B: View {
    let mark: KitV1LineMark

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let strokeColor = KitTones366B.barColor(
            hex: mark.color?.light,
            darkHex: mark.colorDark ?? mark.color?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        GeometryReader { geo in
            let pts = mark.points
            if pts.count >= 2 {
                let minX = pts.map(\.x).min() ?? 0
                let maxX = max(minX + 0.0001, pts.map(\.x).max() ?? 1)
                let minY = pts.map(\.y).min() ?? 0
                let maxY = max(minY + 0.0001, pts.map(\.y).max() ?? 1)
                Path { path in
                    for (idx, pt) in pts.enumerated() {
                        let px = CGFloat((pt.x - minX) / (maxX - minX)) * geo.size.width
                        let py = (1 - CGFloat((pt.y - minY) / (maxY - minY))) * geo.size.height
                        if idx == 0 {
                            path.move(to: CGPoint(x: px, y: py))
                        } else {
                            path.addLine(to: CGPoint(x: px, y: py))
                        }
                    }
                }
                .stroke(
                    strokeColor,
                    style: StrokeStyle(
                        lineWidth: 2,
                        lineCap: .round,
                        lineJoin: .round,
                        dash: mark.dashed == true ? [4, 3] : []
                    )
                )
            }
        }
        .frame(height: 36)
    }
}
