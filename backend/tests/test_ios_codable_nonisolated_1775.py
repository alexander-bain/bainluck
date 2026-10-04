"""CI guard: the Codable declarations Alex approved for #1775 stay `nonisolated`.

Failure class: `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` is set on the app,
widget, watch-app and complication targets. A `Codable`/`Decodable` type there
that is not marked `nonisolated` inherits MainActor isolation, and its
`init(from:)` (a nonisolated requirement) then draws a "main actor-isolated
conformance ... this is an error in the Swift 6 language mode" warning at every
decode site. Swift 6 makes those hard errors.

Scope is EXACTLY what Alex approved (2026-08-11 ruling, "final at 15
declarations"; bounded proposal approved 2026-10-03):
  * the 15 named declarations below,
  * the widget decode helper they call (`decodeTolerantWidgetItems`),
  * amendment B: the widget's two item->display mappings hop to MainActor,
    so network and decode stay off it.
This is deliberately NOT a "zero plain Codable" census. Amendment A (seven more
app declarations) and the extra test-only edits were excluded; a plain
declaration outside this list does not fail here. Widening the set needs its
own ruling and edits this file in the same change.

The project-wide MainActor default is kept (that half of the ruling is pinned
too). Do not delete a marker or a hop to make this pass.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IOS_ROOT = REPO_ROOT / "ios" / "Bain Luck"
PBXPROJ = IOS_ROOT / "Bain Luck.xcodeproj" / "project.pbxproj"
WIDGET_CLIENT = IOS_ROOT / "BainLuckWidget" / "WidgetAPIClient.swift"

# (file relative to IOS_ROOT, kind, name) — the 15 ruled declarations.
APPROVED_15 = (
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetSkipOne"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetFeedResponse"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetDiscoverFeedResponse"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetFeedItem"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetEventData"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetFuturesData"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetCurrentOdds"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetTeamData"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetESPNData"),
    ("BainLuckWidget/WidgetFeedDecoding.swift", "struct", "WidgetOutcome"),
    ("Bain Luck/Models/CommonTypes.swift", "enum", "AnyCodable"),
    ("Bain Luck/Services/DiscoverFeedCache.swift", "struct", "CacheInfo"),
    ("Bain Luck/Views/DiscoverView.swift", "struct", "NativeDiscoverDebugCard"),
    ("Bain Luck/Views/DiscoverView.swift", "struct", "NativeDiscoverDebugInteraction"),
    ("BainLuckTests/NumericSuffixDecodeTests.swift", "struct", "Probe"),
)

# The one helper the widget declarations call from their nonisolated init(from:).
APPROVED_HELPER = ("BainLuckWidget/WidgetFeedDecoding.swift", "func", "decodeTolerantWidgetItems")


def _declaration_lines(rel: str, kind: str, name: str):
    path = IOS_ROOT / rel
    assert path.is_file(), f"approved #1775 file went missing: {rel}"
    pattern = re.compile(
        rf"^[ \t]*(?P<prefix>(?:\w+[ \t]+)*){kind}[ \t]+{re.escape(name)}\b"
    )
    hits = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("//"):
            continue
        m = pattern.match(line)
        if m:
            hits.append((lineno, m.group("prefix").split(), line.strip()))
    return hits


def test_the_fifteen_approved_declarations_are_nonisolated():
    assert len(APPROVED_15) == 15
    problems = []
    for rel, kind, name in APPROVED_15:
        hits = _declaration_lines(rel, kind, name)
        if len(hits) != 1:
            problems.append(f"{rel}: expected one `{kind} {name}`, found {len(hits)}")
            continue
        lineno, prefix, text = hits[0]
        if "nonisolated" not in prefix:
            problems.append(f"{rel}:{lineno}: {text}")
    assert not problems, (
        "an approved #1775 declaration lost `nonisolated` (it would inherit the "
        "MainActor default and error under Swift 6):\n  " + "\n  ".join(problems)
    )


def test_the_widget_decode_helper_is_nonisolated():
    rel, kind, name = APPROVED_HELPER
    hits = _declaration_lines(rel, kind, name)
    assert len(hits) == 1, f"expected one `{kind} {name}` in {rel}, found {len(hits)}"
    lineno, prefix, text = hits[0]
    assert "nonisolated" in prefix, (
        f"{rel}:{lineno}: {text} — the widget declarations call this from their "
        f"nonisolated init(from:); it must stay nonisolated (#1775)"
    )


def test_widget_display_mappings_hop_to_main_actor_after_decoding():
    """Amendment B: the two item->display mappings call MainActor helpers shared
    with the phone (PeriodLabel, DrawPricedWinner, TeamShortName,
    WidgetLifecycle), so they run inside `await MainActor.run`. The fetch and the
    decode must stay OUTSIDE the hop — each decode line precedes its hop."""
    lines = WIDGET_CLIENT.read_text(encoding="utf-8").splitlines()
    hops = [i for i, line in enumerate(lines) if "MainActor.run" in line]
    assert len(hops) == 2, (
        f"expected exactly 2 `MainActor.run` hops in WidgetAPIClient.swift "
        f"(fetchLiveGames, fetchDiscoverItems), found {len(hops)}"
    )
    for hop in hops:
        assert re.search(
            r"return await MainActor\.run \{ feed\.items\.compactMap \{", lines[hop]
        ), f"WidgetAPIClient.swift:{hop + 1}: hop must wrap only the display mapping: {lines[hop].strip()}"
        preceding = lines[max(0, hop - 4):hop]
        assert any("try decoder.decode(" in p for p in preceding), (
            f"WidgetAPIClient.swift:{hop + 1}: the decode must happen before the "
            f"MainActor hop, not inside it"
        )
    text = "\n".join(lines)
    assert text.count("session.data(from:") == 2
    assert "@MainActor" not in text, "amendment B is a scoped hop, not a MainActor client"


def test_main_actor_default_still_set_on_shipped_targets():
    """#1775 keeps the project-wide default; the markers above exist because of it."""
    text = PBXPROJ.read_text(encoding="utf-8")
    count = text.count("SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor")
    assert count == 8, (
        f"expected SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor on 8 build "
        f"configurations (4 targets x Debug/Release), found {count}. #1775 "
        f"approved keeping the default; changing it needs its own ruling."
    )
