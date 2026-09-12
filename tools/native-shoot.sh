#!/bin/bash
# native/020 (#3157) — photograph ANY screen in the iPhone app, unattended.
#
# Replaces the patch-build-shoot-revert cycle that
# tools/native-look-scaffold-TempScreenshot.swift.txt required. The app reads
# `-launch_route` on master (Utilities/LaunchRig.swift, pinned by
# LaunchRigContractTests), hands it to the one router, and lands on the screen.
#
# Usage:
#   tools/native-shoot.sh <label> [route] [--counts] [--cooled] [--scroll N] [--expand]
#
#   tools/native-shoot.sh discover
#   tools/native-shoot.sh g1 '' --counts --cooled
#   tools/native-shoot.sh search 'bainluck://search?q=US%20Open'
#   tools/native-shoot.sh browse bainluck://playoffs
#   tools/native-shoot.sh event bainluck://events/9001
#   tools/native-shoot.sh maps bainluck://events/9001 --scroll 1600
#
#   --counts   draw Discover's SERVED/DRAWN card counter (SHOWABLE-1 G1's number)
#   --cooled   seed the 11-category cooled interaction profile #1221 needs to be
#              visible at all — on a clean install the defect does not appear
#   --scroll N photograph N POINTS down the page instead of the top viewport
#   --expand   open the sections that start collapsed (the event page's Sources
#              disclosure, and anything else reading LaunchRig)
#
# WHY --expand EXISTS (native/086, #4406): the app has honoured
# `-launch_expand_sections` since the flag was added — LaunchRig documents it,
# LaunchRigContractTests pins it, `EventDetailView.showSources` reads it — and no
# tool ever passed it, so every surface behind a disclosure was unphotographable
# by this rig. That is the same hole `--scroll` was built to close, one layer in:
# a shot of a closed disclosure is not a shot of what is inside it, and #4406's
# twelve numberless sportsbook rows live inside one. A LOOK that cannot open the
# section is a LOOK that reports the chevron.
#
# ONE SHOT IS ONE VIEWPORT. iPhone 17 is 402×874 points, and an event page runs
# past 3,000 — so until `--scroll` existed, the margin maps, the half maps and
# every probability ladder had never been photographed by this rig at all, and
# #3533 had to be filed with "its rendering is unverified" in the issue body.
# When you shoot a card that lives below the hero, shoot it with --scroll or say
# in your write-up that you did not see it. Over-asking is safe: the app clamps
# to the bottom of the page rather than photographing past the end of it (which
# would be a blank shot, and a blank shot reads as a missing card).
#
# Build first, and NEVER with -derivedDataPath: a fresh path forces SPM
# resolution and the sandbox cannot reach dl.google.com. The OTHER_SWIFT_FLAGS
# are NOT optional (gotcha #50): without them the build dies with three
# "external macro implementation type 'PreviewsMacros.Common' could not be
# found" errors in BainLuckWidget.swift — a #Preview macro the compiler sandbox
# refuses to expand. It looks like a widget bug and is not one; native/021 lost
# a build cycle to it because this header omitted the flag.
#   xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
#     -destination 'platform=iOS Simulator,name=iPhone 17' \
#     -disableAutomaticPackageResolution \
#     OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' build
#
# IF A SHOT COMES BACK WITH THE NOTIFICATION ALERT, ERASE AND RE-SHOOT — do not
# conclude the suppression failed. `-suppress_notification_prompt` is checked at
# the single call site (`Bain_LuckApp` → `requestPermissionAfterDelay`) and there
# is no other authorization request in the tree, but MEASURED over 8 shoots on
# 2026-09-05 the alert still surfaced twice, and once it is up it belongs to
# SpringBoard: `install` does not clear it, `terminate` does not clear it, and
# every subsequent shot photographs it. `simctl openurl`'s "Open in 'Bain Luck'?"
# confirm behaves the same way. The erase always clears it:
#   xcrun simctl shutdown $SIM; xcrun simctl erase $SIM; xcrun simctl boot $SIM
# Budget one erase per shoot session and read every PNG before believing it.
#
# ═══ WHICH BINARY GETS PHOTOGRAPHED (#5480, native/126) ═══
#
# `APP` was a hardcoded DerivedData path containing Xcode's per-machine hash. Two
# ways that produced wrong evidence, both silent:
#
#   1. On any machine whose hash differs, `install` fails — loud, survivable.
#   2. On THIS machine it always resolves, so a shoot taken before the build
#      finished (or after a build that failed) photographs the PREVIOUS binary
#      and prints `shot <path>.png` exactly as if it had worked. A LOOK is only
#      evidence if it photographed the change, and nothing said which build it
#      was. That is the same class as the gates script's wrong-tree green.
#
# So the app is resolved by glob, newest wins, and the binary's mtime is compared
# against the newest Swift source in the tree. A source newer than the binary is
# a REFUSAL, not a warning (`--allow-stale` overrides and says so in the output).
set -u
SIM="${NATIVE_SHOOT_SIM:-76D961F0-8575-479F-ABCE-652D8A79DBF9}"   # iPhone 17 — PIN IT, `booted` picks the iPad
BUNDLE=com.bainluck.Bain-Luck
OUT="${NATIVE_SHOOT_OUT:-/Users/bain/bainluck-dev/native/artifacts-native-020}"
DERIVED="${NATIVE_SHOOT_DERIVED:-$HOME/Library/Developer/Xcode/DerivedData}"

LABEL="${1:?label required, e.g. discover / search-usopen}"
ROUTE="${2:-}"
shift $(( $# > 2 ? 2 : $# ))
COUNTS=""
COOLED=""
SCROLL=""
EXPAND=""
ALLOW_STALE=""
RESOLVE_ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --counts) COUNTS=1 ;;
    --cooled) COOLED=1 ;;
    --expand) EXPAND=1 ;;
    --allow-stale) ALLOW_STALE=1 ;;
    --resolve-only) RESOLVE_ONLY=1 ;;
    --scroll)
      SCROLL="${2:?--scroll needs a point count, e.g. --scroll 1600}"
      shift
      ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

# ── RESOLVE THE APP, NEWEST WINS, AND SAY WHICH ──────────────────────────────
NCAND=0
if [ -n "${NATIVE_SHOOT_APP:-}" ]; then
  APP="$NATIVE_SHOOT_APP"
else
  APP=""
  # An ARRAY, not `ls` in a command substitution: the bundle is called
  # "Bain Luck.app" and word-splitting tears it in half, which resolves to
  # nothing and reads exactly like "you have not built yet".
  shopt -s nullglob
  CANDS=( "$DERIVED"/Bain_Luck-*/Build/Products/Debug-iphonesimulator/"Bain Luck.app" )
  shopt -u nullglob
  NCAND=${#CANDS[@]}
  newest=0
  # `${CANDS[@]+"${CANDS[@]}"}`, not `"${CANDS[@]}"`. macOS ships bash 3.2.57,
  # where expanding an EMPTY array under `set -u` is an unbound-variable error
  # and the script dies at exit 127 — gotcha #124's "the gate never ran", in
  # place of the "NO BUILT APP FOUND — build first" message written right below.
  for cand in ${CANDS[@]+"${CANDS[@]}"}; do
    m=$(stat -f %m "$cand/Bain Luck" 2>/dev/null || stat -f %m "$cand" 2>/dev/null || echo 0)
    if [ "$m" -gt "$newest" ]; then newest=$m; APP="$cand"; fi
  done
fi
if [ -z "$APP" ] || [ ! -d "$APP" ]; then
  echo "NO BUILT APP FOUND — build first." >&2
  echo "  looked under: $DERIVED/Bain_Luck-*/Build/Products/Debug-iphonesimulator/" >&2
  echo "  (override with NATIVE_SHOOT_APP=/path/to/Bain Luck.app)" >&2
  exit 1
fi
BIN="$APP/Bain Luck"
APP_MTIME=$( [ -f "$BIN" ] && stat -f %m "$BIN" 2>/dev/null || stat -f %m "$APP" 2>/dev/null || echo 0 )
echo "  app: $APP"
echo "  built: $( [ "$APP_MTIME" -gt 0 ] && date -r "$APP_MTIME" '+%Y-%m-%d %H:%M:%S' || echo UNKNOWN )"
# 28 DerivedData directories existed for this project on 2026-09-12. Picking the
# newest is the right rule, but it is a guess among many and says so.
[ "$NCAND" -gt 1 ] && echo "  (newest of $NCAND built copies under DerivedData)"

# ── IS IT OLDER THAN THE SOURCE? ─────────────────────────────────────────────
# The shoot is evidence about a change; a binary predating that change is not
# evidence, it is the previous shot taken again.
SRC_ROOT="$( ( cd "$(dirname "${BASH_SOURCE[0]}")" && git rev-parse --show-toplevel 2>/dev/null ) || true )"
[ -n "$SRC_ROOT" ] || SRC_ROOT="$(pwd)"
NEWEST_SRC=""
NEWEST_SRC_MTIME=0
if [ -d "$SRC_ROOT/ios" ]; then
  while IFS= read -r f; do
    m=$(stat -f %m "$f" 2>/dev/null || echo 0)
    if [ "$m" -gt "$NEWEST_SRC_MTIME" ]; then NEWEST_SRC_MTIME=$m; NEWEST_SRC="$f"; fi
  done < <(find "$SRC_ROOT/ios" -name '*.swift' -type f 2>/dev/null)
fi
if [ "$NEWEST_SRC_MTIME" -gt "$APP_MTIME" ] && [ "$APP_MTIME" -gt 0 ]; then
  echo "  STALE BINARY — a Swift source is NEWER than the app you are about to photograph."
  echo "    newest source: $(basename "$NEWEST_SRC")  ($(date -r "$NEWEST_SRC_MTIME" '+%Y-%m-%d %H:%M:%S'))"
  echo "    the app       : $(date -r "$APP_MTIME" '+%Y-%m-%d %H:%M:%S')"
  if [ -z "$ALLOW_STALE" ]; then
    echo "  REFUSING — a shot of the previous build is wrong evidence, and it looks identical" >&2
    echo "  to a right one. Rebuild, or pass --allow-stale if you MEANT to shoot this binary." >&2
    exit 1
  fi
  echo "  --allow-stale given: shooting it anyway. SAY SO wherever you use this PNG."
fi

[ -n "$RESOLVE_ONLY" ] && { echo "  (--resolve-only: nothing installed, nothing shot)"; exit 0; }

mkdir -p "$OUT"
xcrun simctl bootstatus "$SIM" -b >/dev/null 2>&1
xcrun simctl install "$SIM" "$APP" || { echo "install failed — build first" >&2; exit 1; }
xcrun simctl terminate "$SIM" "$BUNDLE" >/dev/null 2>&1
sleep 1

if [ -n "$COOLED" ]; then
  # The 11 largest categories on the live page, each cooled past the -3
  # suppression threshold and stamped now so nothing has decayed. Exactly the
  # profile DiscoverClientFilterFloorTests pins in Swift. Without it a clean
  # install shows no G1 defect at all (server 50, phone 50).
  CONT=$(xcrun simctl get_app_container "$SIM" "$BUNDLE" data)
  PLIST="$CONT/Library/Preferences/$BUNDLE.plist"
  NOW=$(date +%s)
  mkdir -p "$(dirname "$PLIST")"
  python3 - "$PLIST" "$NOW" <<'PY'
import plistlib, sys, os
path, now = sys.argv[1], float(sys.argv[2])
cooled = ["politics","entertainment","soccer","hockey","tech","baseball",
          "weather","motorsports","geopolitics","cycling","football"]
d = {}
if os.path.exists(path):
    with open(path,"rb") as f: d = plistlib.load(f)
d["discover_interaction_profile_native_v2"] = {c: {"score": -4.0, "at": now} for c in cooled}
d["discover_onboarded"] = True
with open(path,"wb") as f: plistlib.dump(d, f)
print("  seeded %d cooled categories" % len(cooled))
PY
fi

ARGS=(-suppress_notification_prompt YES -bainluck_telemetry_consent none -discover_onboarded YES)
[ -n "$ROUTE" ]  && ARGS+=(-launch_route "$ROUTE")
[ -n "$COUNTS" ] && ARGS+=(-launch_debug_counts YES)
[ -n "$SCROLL" ] && ARGS+=(-launch_scroll "$SCROLL")
[ -n "$EXPAND" ] && ARGS+=(-launch_expand_sections YES)

xcrun simctl launch "$SIM" "$BUNDLE" "${ARGS[@]}" >/dev/null 2>&1

# The app hands the route to the router after LaunchRig.routeDelay (2.5s), and
# the destination screen then loads. 18s covers a cold feed on a cold sim.
#
# A scroll waits LaunchRig.scrollDelay (8s) AFTER the route before it moves, so
# the camera has to wait that out too or it photographs the page pre-scroll —
# which is a shot of the top with a scrolled label on it, the worst kind of
# wrong evidence. +4s of slack for the scrolled content's own lazy loads.
sleep 18
[ -n "$SCROLL" ] && sleep 12
SHOT="$OUT/$LABEL.png"
xcrun simctl io "$SIM" screenshot "$SHOT" >/dev/null 2>&1 \
  && echo "  shot $SHOT" \
  || { echo "  screenshot FAILED" >&2; exit 1; }
