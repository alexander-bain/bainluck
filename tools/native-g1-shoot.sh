#!/bin/bash
# native/012 G1 (#1221) — photograph SERVED vs DRAWN with a heavily cooled profile.
#
# The G1 defect is invisible on a clean install (today's live page: server 50,
# phone 50). It only appears once the reader has swiped, so the rig SEEDS the
# interaction profile the defect needs and shoots the app's own counter.
#
# Usage: tools/native-g1-shoot.sh <label>
#
# ONE-TIME, on a simulator that was prompted before #3141 landed: the alert
# already on screen is owned by SpringBoard, and neither `install` nor
# `terminate` clears it — so the first shot after this fix still photographs a
# dialog the app is no longer raising. Erase once and it never returns:
#   xcrun simctl shutdown $SIM; xcrun simctl erase $SIM; xcrun simctl boot $SIM
set -u
SIM=76D961F0-8575-479F-ABCE-652D8A79DBF9    # iPhone 17 — PIN IT, `booted` picks the iPad
BUNDLE=com.bainluck.Bain-Luck
APP="/Users/bain/Library/Developer/Xcode/DerivedData/Bain_Luck-bkmrwhmxuqqsseeuqlyqvcavesmz/Build/Products/Debug-iphonesimulator/Bain Luck.app"
OUT=/Users/bain/bainluck-dev/native/artifacts-native-012
LABEL="${1:?label required, e.g. floor8 / floor28}"
mkdir -p "$OUT"

xcrun simctl bootstatus "$SIM" -b >/dev/null 2>&1
xcrun simctl install "$SIM" "$APP"
xcrun simctl terminate "$SIM" "$BUNDLE" >/dev/null 2>&1
sleep 1

# The 11 largest categories on the live page, each cooled to -4 (past the -3
# suppression threshold), stamped now so nothing has decayed. This is exactly
# the profile DiscoverClientFilterFloorTests pins in Swift.
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

# -suppress_notification_prompt and -bainluck_telemetry_consent are honoured ON
# MASTER (#3141): without the first, the permission alert lands 5s in and covers
# the middle of every shot below, and no amount of `simctl privacy deny` or
# erasing suppresses it. `-temp_screenshot_tab` / `-temp_screenshot_counts` were
# passed here for weeks and read by NOTHING — they exist only in the hand-patched
# scaffold (tools/native-look-scaffold-TempScreenshot.swift.txt), so the rig
# looked like it was selecting a tab and was in fact inert. Discover is the
# default tab, which is the only reason these shots were ever of the right
# screen. Patch the scaffold in if you need a tab this rig cannot reach.
xcrun simctl launch "$SIM" "$BUNDLE" \
  -suppress_notification_prompt YES -bainluck_telemetry_consent none \
  -discover_onboarded YES >/dev/null 2>&1
sleep 18
xcrun simctl io "$SIM" screenshot "$OUT/G1-$LABEL-discover.png" >/dev/null 2>&1 \
  && echo "  shot G1-$LABEL-discover.png"
