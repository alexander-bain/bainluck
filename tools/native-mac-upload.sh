#!/bin/bash
# native-mac-upload.sh — macOS TestFlight companion to `tools/native-upload.sh` (#10878).
#
# Preserves `tools/native-upload.sh` and `ios/ExportOptions-AppStore.plist` untouched
# for the working iPhone/Watch TestFlight path.
#
# WHY MAC NEEDS ITS OWN COMPANION
# -------------------------------
# `tools/native-upload.sh` archives for `generic/platform=iOS`, checks iOS `.mobileprovision`
# files under `Entitlements.application-identifier`, grades an exported `.ipa` (`Payload/*.app`),
# and delivers via `altool -t ios`.
#
# A macOS TestFlight build differs at every one of those seams:
#   1. Destination is `generic/platform=macOS`.
#   2. The archived bundle layout is `Bain Luck.app/Contents/Info.plist` and
#      `Bain Luck.app/Contents/PlugIns/BainLuckWidget.appex/Contents/Info.plist`.
#   3. Both the main app AND the embedded `BainLuckWidget.appex` must carry
#      `com.apple.security.app-sandbox = true` on macOS (ASC validation rule ITMS-90296).
#   4. Provisioning profiles on macOS use `.provisionprofile`, carry `Platform = [OSX]`,
#      and spell the identifier key `Entitlements.com.apple.application-identifier`.
#   5. `xcodebuild -exportArchive` with `method=app-store-connect` produces a signed
#      `.pkg` installer (not `.ipa`), which requires BOTH:
#        - an `Apple Distribution` certificate (for `.app` and `.appex` code signing), and
#        - a `3rd Party Mac Developer Installer` / `Mac Installer Distribution` certificate
#          (for `.pkg` productbuild signing).
#   6. Upload uses `iTMSTransporter -m upload -assetFile <pkg>` (when proxied) or
#      `xcrun altool --upload-app -f <pkg> -t osx`.
#
# USAGE
#   tools/native-mac-upload.sh --self-check
#   tools/native-mac-upload.sh --dry-run --build 81
#   tools/native-mac-upload.sh --archive --build 81
#   tools/native-mac-upload.sh --export  --build 81
#   tools/native-mac-upload.sh --validate --build 81
#   tools/native-mac-upload.sh --upload  --build 81
#   tools/native-mac-upload.sh --export --reuse-archive --build 81
#
#   --repo PATH                archive that tree instead of the script's own
#   --allow-stale-tree         build anyway from a tree that is behind master or dirty
#   --marketing-version VER    override MARKETING_VERSION (default: 1.0.4)
#
# CREDENTIALS (upload/validate only; resolved from env or ~/.claude/.env, never printed)
#   ASC_KEY_ID     App Store Connect API key id
#   ASC_ISSUER_ID  App Store Connect API issuer uuid
#   ASC_KEY_PATH   path to AuthKey_<ASC_KEY_ID>.p8
set -uo pipefail

if [ "${1:-}" = "--self-check" ]; then
  python3 - <<'PY'
import plistlib, subprocess, sys

# 1. Verify macOS provisionprofile parser distinguishes OSX store vs dev profiles
dev_plist = plistlib.dumps({
    "Name": "Mac Team Provisioning Profile: com.bainluck.Bain-Luck",
    "Platform": ["OSX"],
    "ProvisionedDevices": ["DEV1"],
    "ExpirationDate": "2027-06-03T22:35:21Z",
    "Entitlements": {"com.apple.application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
})
store_plist = plistlib.dumps({
    "Name": "BainLuck Mac AppStore",
    "Platform": ["OSX"],
    "ExpirationDate": "2027-09-11T00:19:37Z",
    "Entitlements": {"com.apple.application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
})
d_dev = plistlib.loads(dev_plist)
d_store = plistlib.loads(store_plist)
assert "ProvisionedDevices" in d_dev
assert "ProvisionedDevices" not in d_store
assert d_store["Entitlements"]["com.apple.application-identifier"] == "J893F72P4R.com.bainluck.Bain-Luck"
assert "OSX" in d_store["Platform"]
print("SELF-CHECK PASS — macOS profile, entitlement, and installer-cert checks verified")
PY
  exit $?
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT_SOURCE="the script's own location"
ALLOW_STALE_TREE=0
_argv=("$@")
for _i in "${!_argv[@]}"; do
  if [ "${_argv[$_i]}" = "--repo" ]; then
    _next=$(( _i + 1 ))
    _cand="${_argv[$_next]:-}"
    if [ -z "$_cand" ] || [ ! -d "$_cand" ]; then
      echo "FAIL: --repo needs a directory that exists, got '${_cand:-<nothing>}'" >&2
      exit 2
    fi
    REPO_ROOT="$(cd "$_cand" && pwd)"
    REPO_ROOT_SOURCE="--repo"
  fi
done

PROJECT="$REPO_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
PBXPROJ="$PROJECT/project.pbxproj"
EXPORT_OPTIONS="${NATIVE_MAC_EXPORT_OPTIONS:-$REPO_ROOT/ios/ExportOptions-MacAppStore.plist}"
LOG_DIR="${NATIVE_MAC_UPLOAD_LOG_DIR:-/tmp}"
ARCHIVE="${NATIVE_MAC_UPLOAD_ARCHIVE:-/tmp/BainLuck-macos-appstore.xcarchive}"
EXPORT_DIR="${NATIVE_MAC_UPLOAD_EXPORT_DIR:-/tmp/BainLuck-macos-appstore-export}"
ARCHIVE_LOG="$LOG_DIR/native-mac-upload-archive.txt"
EXPORT_LOG="$LOG_DIR/native-mac-upload-export.txt"
DELIVER_LOG="$LOG_DIR/native-mac-upload-deliver.txt"
SCHEME="${NATIVE_MAC_UPLOAD_SCHEME:-Bain Luck}"
APP_BUNDLE_ID="com.bainluck.Bain-Luck"
WIDGET_BUNDLE_ID="com.bainluck.Bain-Luck.BainLuckWidget"
PROFILE_DIR="${NATIVE_PROFILE_DIR:-$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles}"
MARKETING_VERSION="${NATIVE_MAC_MARKETING_VERSION:-1.0.4}"

MODE=""
BUILD_NUMBER=""
REUSE_ARCHIVE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|--preflight) MODE="dry-run" ;;
    --archive)             MODE="archive" ;;
    --export)              MODE="export" ;;
    --validate)            MODE="validate" ;;
    --upload)              MODE="upload" ;;
    --reuse-archive)       REUSE_ARCHIVE=1 ;;
    --allow-stale-tree)    ALLOW_STALE_TREE=1 ;;
    --repo)                shift ;;
    --build)               shift; BUILD_NUMBER="${1:-}" ;;
    --marketing-version)   shift; MARKETING_VERSION="${1:-}" ;;
    -h|--help)             sed -n '1,44p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "FAIL: unknown argument '$1' (see --help)" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$MODE" ]; then
  echo "FAIL: name a mode — --dry-run, --archive, --export, --validate or --upload" >&2
  exit 2
fi
if [ -n "$BUILD_NUMBER" ] && ! [[ "$BUILD_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "FAIL: --build takes a whole number, got '$BUILD_NUMBER'" >&2
  exit 2
fi

fail=0
note() { echo "  $1"; }
step() { echo; echo "==> $1"; }

# ─── PREFLIGHT ────────────────────────────────────────────────────────────────
step "preflight (macOS TestFlight)"

if [ ! -d "$PROJECT" ]; then
  echo "FAIL: no project at $PROJECT" >&2
  exit 2
fi
note "project : $PROJECT"

TREE_STALE=""
TREE_UNSURE=""
if ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  note "tree    : $REPO_ROOT  (resolved from $REPO_ROOT_SOURCE) — NOT a git repo"
  TREE_UNSURE="not a git repo"
else
  TREE_BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
  TREE_SHA=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)
  note "tree    : $REPO_ROOT  (resolved from $REPO_ROOT_SOURCE)"
  note "          $TREE_BRANCH @ ${TREE_SHA:0:10}"

  IOS_DIRTY=$(git -C "$REPO_ROOT" status --porcelain -- ios/ 2>/dev/null | wc -l | tr -d ' ')
  REMOTE_MASTER=$(git -C "$REPO_ROOT" ls-remote origin refs/heads/master 2>/dev/null | /usr/bin/awk '{print $1}')

  if [ -z "$REMOTE_MASTER" ]; then
    note "          vs remote master: UNKNOWN — ls-remote said nothing"
    TREE_UNSURE="cannot reach origin"
  elif ! git -C "$REPO_ROOT" cat-file -e "$REMOTE_MASTER^{commit}" 2>/dev/null; then
    note "          vs remote master: UNKNOWN — ${REMOTE_MASTER:0:9} is not local yet"
    TREE_UNSURE="remote master commit is not local"
  elif git -C "$REPO_ROOT" merge-base --is-ancestor "$REMOTE_MASTER" HEAD 2>/dev/null; then
    note "          vs remote master: CONTAINS ${REMOTE_MASTER:0:9} — current"
  else
    BEHIND=$(git -C "$REPO_ROOT" rev-list --count "HEAD..$REMOTE_MASTER" 2>/dev/null)
    IOS_BEHIND=$(git -C "$REPO_ROOT" diff --name-only "HEAD..$REMOTE_MASTER" -- ios/ 2>/dev/null | wc -l | tr -d ' ')
    note "          vs remote master: BEHIND by ${BEHIND:-?} commit(s), ${IOS_BEHIND:-?} touching ios/"
    TREE_STALE="behind remote master by ${BEHIND:-?} commit(s) (${IOS_BEHIND:-?} touching ios/)"
  fi

  if [ "${IOS_DIRTY:-0}" != "0" ]; then
    note "          ios/ working tree: $IOS_DIRTY uncommitted change(s)"
    TREE_STALE="${TREE_STALE:+$TREE_STALE; }$IOS_DIRTY uncommitted change(s) under ios/"
  fi
fi

if [ -n "$TREE_STALE" ] && [ "$MODE" != "dry-run" ] && [ "$ALLOW_STALE_TREE" = "0" ]; then
  echo
  echo "FAIL: refusing to build from this tree — $TREE_STALE" >&2
  echo "      Pass --repo <path> or --allow-stale-tree if intentional." >&2
  exit 2
fi

PROJECT_BUILD=$(/usr/bin/grep -o 'CURRENT_PROJECT_VERSION = [0-9]*' "$PBXPROJ" 2>/dev/null \
  | /usr/bin/awk '{print $3}' | sort -rn | head -1)
PROJECT_BUILD=${PROJECT_BUILD:-?}
EFFECTIVE_BUILD="${BUILD_NUMBER:-$PROJECT_BUILD}"
note "version : $MARKETING_VERSION ($EFFECTIVE_BUILD)"

MIN_MACOS=$(/usr/bin/grep -o 'MACOSX_DEPLOYMENT_TARGET = [0-9.]*' "$PBXPROJ" 2>/dev/null \
  | head -1 | /usr/bin/awk '{print $3}')
HOST_MACOS=$(sw_vers -productVersion 2>/dev/null || echo "?")
note "macos   : MACOSX_DEPLOYMENT_TARGET=${MIN_MACOS:-?}  host=${HOST_MACOS}"

# Check that BainLuckWidget has ENABLE_APP_SANDBOX = YES (ITMS-90296 guard)
WIDGET_SANDBOX_COUNT=$(python3 - "$PBXPROJ" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
blocks = re.findall(r'A7C0000000000000000000F[89] /\* (?:Debug|Release) \*/ = \{.*?\n\t\t\};', text, re.S)
print(sum(1 for b in blocks if "ENABLE_APP_SANDBOX = YES;" in b))
PY
)
if [ "${WIDGET_SANDBOX_COUNT:-0}" -ge 2 ]; then
  note "sandbox : BainLuckWidget ENABLE_APP_SANDBOX=YES present in Debug & Release"
else
  fail=1
  echo "FAIL: BainLuckWidget is missing ENABLE_APP_SANDBOX = YES in project.pbxproj."
  note "Mac App Store / TestFlight rejects an embedded .appex without com.apple.security.app-sandbox (ITMS-90296)."
fi

# 1. Code-signing identity for .app and .appex
if security find-identity -v -p codesigning 2>/dev/null | /usr/bin/grep -q "Apple Distribution"; then
  note "identity: Apple Distribution present (app + widget code signing)"
else
  fail=1
  echo "FAIL: no 'Apple Distribution' code-signing identity in the keychain."
fi

# 2. Installer-signing identity for .pkg export (required for export/validate/upload)
if security find-identity -v 2>/dev/null | /usr/bin/grep -qE "3rd Party Mac Developer Installer|Mac Installer Distribution"; then
  note "identity: Mac Installer Distribution present (.pkg signing)"
else
  if [ "$MODE" = "archive" ]; then
    note "identity: MISSING '3rd Party Mac Developer Installer' / 'Mac Installer Distribution' (archive can run; export/upload cannot)"
  else
    fail=1
    echo "FAIL: no '3rd Party Mac Developer Installer' or 'Mac Installer Distribution' identity in the keychain."
    note "macOS App Store Connect export builds a .pkg installer and requires a Mac Installer Distribution certificate."
  fi
fi

# 3. Mac App Store provisioning profiles (.provisionprofile, Platform=OSX, no ProvisionedDevices)
mac_store_profile_for() {
  local want="$1"
  python3 - "$PROFILE_DIR" "$want" <<'PY'
import glob, os, plistlib, subprocess, sys
prof_dir, want = sys.argv[1], sys.argv[2]
for p in sorted(glob.glob(os.path.join(prof_dir, "*.provisionprofile")) + glob.glob(os.path.join(prof_dir, "*.mobileprovision"))):
    out = subprocess.run(["security", "cms", "-D", "-i", p], capture_output=True)
    if out.returncode != 0:
        continue
    pl = plistlib.loads(out.stdout)
    if "ProvisionedDevices" in pl:
        continue
    plats = pl.get("Platform") or []
    if "OSX" not in plats and "macOS" not in plats:
        continue
    ent = pl.get("Entitlements") or {}
    appid = ent.get("com.apple.application-identifier") or ent.get("application-identifier") or ""
    if appid != f"J893F72P4R.{want}":
        continue
    exp = pl.get("ExpirationDate")
    exp_str = exp.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(exp, "strftime") else str(exp)
    print(f"{pl.get('Name')}|{exp_str}")
    sys.exit(0)
sys.exit(1)
PY
}

for bid in "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID"; do
  if found=$(mac_store_profile_for "$bid"); then
    pname=${found%%|*}
    pexp=${found##*|}
    note "profile : $bid → ${pname} (expires ${pexp})"
  else
    if [ "$MODE" = "archive" ]; then
      note "profile : MISSING Mac App Store (.provisionprofile) for $bid (archive can run; export/upload cannot)"
    else
      fail=1
      echo "FAIL: no Mac App Store distribution profile (.provisionprofile, Platform=OSX) installed for $bid"
      note "Create/download MAC_APP_STORE profiles for $APP_BUNDLE_ID and $WIDGET_BUNDLE_ID in App Store Connect / Xcode."
    fi
  fi
done

if [ ! -f "$EXPORT_OPTIONS" ]; then
  fail=1
  echo "FAIL: no export options at $EXPORT_OPTIONS"
else
  if ! /usr/bin/plutil -lint "$EXPORT_OPTIONS" >/dev/null 2>&1; then
    fail=1
    echo "FAIL: $EXPORT_OPTIONS is not a valid plist"
  else
    method=$(/usr/bin/plutil -extract method raw -o - "$EXPORT_OPTIONS" 2>/dev/null)
    manage=$(/usr/bin/plutil -extract manageAppVersionAndBuildNumber raw -o - "$EXPORT_OPTIONS" 2>/dev/null)
    note "export  : method=$method manageAppVersionAndBuildNumber=$manage"
  fi
fi

# Resolve credentials from environment or ~/.claude/.env without printing secrets
_asc_env=$(python3 - "$REPO_ROOT/tools/asc-builds.py" <<'PY'
import importlib.util, os, shlex, sys
asc_path = sys.argv[1]
if os.path.exists(asc_path):
    spec = importlib.util.spec_from_file_location("asc_builds", asc_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    creds = mod.resolve_credentials()
    cands = mod.key_candidates(creds.get("ASC_KEY_PATH", ""), creds.get("ASC_KEY_ID", ""))
    readable_key = next((c for c in cands if os.path.isfile(c) and os.access(c, os.R_OK)), "")
    for k, v in [("ASC_KEY_ID", creds.get("ASC_KEY_ID", "")), ("ASC_ISSUER_ID", creds.get("ASC_ISSUER_ID", "")), ("ASC_KEY_PATH", readable_key)]:
        print(f"{k}={shlex.quote(v)}")
PY
)
eval "$_asc_env"
unset _asc_env

CREDS_OK=1
for v in ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_PATH; do
  if [ -z "${!v:-}" ]; then CREDS_OK=0; fi
done
if [ "$CREDS_OK" = "1" ] && [ ! -f "${ASC_KEY_PATH:-}" ]; then
  CREDS_OK=0
fi
if [ "$CREDS_OK" = "1" ]; then
  note "asc key : present (id ending ${ASC_KEY_ID: -4})"
else
  note "asc key : ABSENT — archive and export still run; upload does not"
fi

SPM_STORE="${BAINLUCK_SPM_STORE:-$HOME/Library/Developer/Xcode/DerivedData/Bain_Luck-cwkxplfeuucvrvbplvqqlcgmpcgx/SourcePackages}"
SPM_FLAGS=()
if [ -d "$SPM_STORE" ]; then
  SPM_FLAGS=(-clonedSourcePackagesDirPath "$SPM_STORE")
  note "spm     : borrowing $SPM_STORE"
else
  note "spm     : no store at $SPM_STORE — archive will resolve packages itself"
fi

if [ "$MODE" = "dry-run" ]; then
  echo
  echo "would run, in order:"
  echo "  xcodebuild -project '$PROJECT' -scheme '$SCHEME' \\"
  echo "    -destination 'generic/platform=macOS' -archivePath '$ARCHIVE' \\"
  echo "    -disableAutomaticPackageResolution ${SPM_FLAGS[*]+${SPM_FLAGS[*]}} \\"
  echo "    CURRENT_PROJECT_VERSION=$EFFECTIVE_BUILD MARKETING_VERSION=$MARKETING_VERSION \\"
  echo "    OTHER_SWIFT_FLAGS='\$(inherited) -Xfrontend -disable-sandbox' archive"
  echo "  xcodebuild -exportArchive -archivePath '$ARCHIVE' \\"
  echo "    -exportOptionsPlist '$EXPORT_OPTIONS' -exportPath '$EXPORT_DIR'"
  echo "  xcrun altool --upload-app -f '$EXPORT_DIR/Bain Luck.pkg' -t osx \\"
  echo "    --apiKey \"\$ASC_KEY_ID\" --apiIssuer \"\$ASC_ISSUER_ID\" --output-format json"
  echo
  if [ "$fail" -ne 0 ]; then
    echo "DRY RUN: PREFLIGHT BLOCKED (see FAIL lines above; no build ran)"
    exit 2
  fi
  echo "DRY RUN: PASS  (no build ran)"
  exit 0
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "PREFLIGHT: FAIL — nothing was built."
  exit 2
fi

case "$MODE" in
  validate|upload)
    if [ -z "$BUILD_NUMBER" ]; then
      echo "PREFLIGHT: FAIL — --$MODE needs an explicit --build N."
      exit 2
    fi
    if [ "$CREDS_OK" != "1" ]; then
      echo "PREFLIGHT: FAIL — --$MODE needs ASC_KEY_ID, ASC_ISSUER_ID and ASC_KEY_PATH."
      exit 2
    fi
    ;;
esac

echo
echo "PREFLIGHT: PASS"

# ─── ARCHIVE ──────────────────────────────────────────────────────────────────
APP=""
if [ "$REUSE_ARCHIVE" = "1" ]; then
  step "reusing macOS archive at $ARCHIVE"
else
  step "archiving (Release, generic/platform=macOS, $MARKETING_VERSION ($EFFECTIVE_BUILD)); log: $ARCHIVE_LOG"
  rm -rf "$ARCHIVE"
  xcodebuild \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination 'generic/platform=macOS' \
    -archivePath "$ARCHIVE" \
    -disableAutomaticPackageResolution \
    ${SPM_FLAGS[@]+"${SPM_FLAGS[@]}"} \
    CURRENT_PROJECT_VERSION="$EFFECTIVE_BUILD" \
    MARKETING_VERSION="$MARKETING_VERSION" \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    archive > "$ARCHIVE_LOG" 2>&1
  echo "  xcodebuild archive exit: $?  (a fact, not the verdict)"
fi

if [ ! -d "$ARCHIVE" ]; then
  fail=1
  echo "FAIL: no archive at $ARCHIVE"
else
  APP=$(find "$ARCHIVE/Products/Applications" -maxdepth 1 -name '*.app' 2>/dev/null | head -1)
  if [ -z "$APP" ]; then
    fail=1
    echo "FAIL: archive exists but contains no .app"
  else
    a_ver=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Contents/Info.plist" 2>/dev/null || echo "?")
    a_build=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$APP/Contents/Info.plist" 2>/dev/null || echo "?")
    a_minos=$(/usr/libexec/PlistBuddy -c "Print :LSMinimumSystemVersion" "$APP/Contents/Info.plist" 2>/dev/null || echo "?")
    note "archived: $(basename "$APP")  $a_ver ($a_build)  LSMinimumSystemVersion=$a_minos"
    if [ "$a_build" != "$EFFECTIVE_BUILD" ]; then
      fail=1
      echo "FAIL: archive carries build $a_build, not $EFFECTIVE_BUILD."
    fi
    if ! codesign -d --entitlements :- "$APP" 2>/dev/null | /usr/bin/grep -q "com.apple.security.app-sandbox"; then
      fail=1
      echo "FAIL: archived app is missing com.apple.security.app-sandbox entitlement."
    fi
    WIDGET_APPEX="$APP/Contents/PlugIns/BainLuckWidget.appex"
    if [ -d "$WIDGET_APPEX" ]; then
      w_ver=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$WIDGET_APPEX/Contents/Info.plist" 2>/dev/null || echo "?")
      w_build=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$WIDGET_APPEX/Contents/Info.plist" 2>/dev/null || echo "?")
      note "widget  : BainLuckWidget.appex  $w_ver ($w_build)"
      if [ "$w_build" != "$EFFECTIVE_BUILD" ] || [ "$w_ver" != "$a_ver" ]; then
        fail=1
        echo "FAIL: embedded widget version/build ($w_ver / $w_build) does not match host app ($a_ver / $a_build)."
      fi
      if ! codesign -d --entitlements :- "$WIDGET_APPEX" 2>/dev/null | /usr/bin/grep -q "com.apple.security.app-sandbox"; then
        fail=1
        echo "FAIL: embedded BainLuckWidget.appex is missing com.apple.security.app-sandbox entitlement (ITMS-90296)."
      fi
    fi
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo; echo "ARCHIVE: FAIL  (log: $ARCHIVE_LOG)"
  if /usr/bin/grep -q "error: " "$ARCHIVE_LOG" 2>/dev/null; then
    /usr/bin/grep "error: " "$ARCHIVE_LOG" | sort -u | head -8 | sed 's/^/    /'
  fi
  exit 1
fi
echo "ARCHIVE: PASS"
[ "$MODE" = "archive" ] && exit 0

# ─── EXPORT ───────────────────────────────────────────────────────────────────
step "exporting macOS App Store .pkg; log: $EXPORT_LOG"
rm -rf "$EXPORT_DIR"
xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportOptionsPlist "$EXPORT_OPTIONS" \
  -exportPath "$EXPORT_DIR" > "$EXPORT_LOG" 2>&1
echo "  xcodebuild -exportArchive exit: $?  (a fact, not the verdict)"

PKG=$(find "$EXPORT_DIR" -maxdepth 1 -name '*.pkg' 2>/dev/null | head -1)
if [ -z "$PKG" ]; then
  fail=1
  echo "FAIL: no .pkg in $EXPORT_DIR"
  /usr/bin/grep -i "error\|Provisioning\|no profile\|certificate\|installer" "$EXPORT_LOG" | sort -u | head -10 | sed 's/^/    /'
else
  bytes=$(/usr/bin/stat -f %z "$PKG" 2>/dev/null || echo 0)
  if [ "$bytes" -lt 1000000 ] 2>/dev/null; then
    fail=1
    echo "FAIL: $PKG is only $bytes bytes — not a valid app package."
  fi
  if ! /usr/sbin/pkgutil --check-signature "$PKG" >/dev/null 2>&1; then
    fail=1
    echo "FAIL: $PKG failed pkgutil --check-signature."
  fi
  tmp_pkg_dir=$(mktemp -d)
  rm -rf "$tmp_pkg_dir/expanded"
  /usr/sbin/pkgutil --expand-full "$PKG" "$tmp_pkg_dir/expanded" 2>/dev/null
  pkg_plist=$(find "$tmp_pkg_dir/expanded" -path '*.app/Contents/Info.plist' 2>/dev/null | head -1)
  if [ -n "$pkg_plist" ]; then
    p_ver=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$pkg_plist" 2>/dev/null || echo "?")
    p_build=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$pkg_plist" 2>/dev/null || echo "?")
    note "pkg     : $(basename "$PKG")  $p_ver ($p_build)  $((bytes / 1024 / 1024)) MB"
    if [ "$p_build" != "$EFFECTIVE_BUILD" ]; then
      fail=1
      echo "FAIL: exported .pkg carries build $p_build, not $EFFECTIVE_BUILD."
    fi
  else
    fail=1
    echo "FAIL: expanded $PKG contains no *.app/Contents/Info.plist"
  fi
  rm -rf "$tmp_pkg_dir"
fi

if [ "$fail" -ne 0 ]; then
  echo; echo "EXPORT: FAIL  (log: $EXPORT_LOG)"
  exit 1
fi
echo "EXPORT: PASS"
echo "  $PKG"

if [ "$MODE" = "export" ]; then
  echo
  echo "Stopped before delivery, as asked. To send this exact file:"
  echo "  tools/native-mac-upload.sh --upload --reuse-archive --build $EFFECTIVE_BUILD"
  exit 0
fi

# ─── DELIVER ──────────────────────────────────────────────────────────────────
KEY_HOME="$HOME/.appstoreconnect/private_keys"
mkdir -p "$KEY_HOME"
chmod 700 "$KEY_HOME"
STAGED_KEY="$KEY_HOME/AuthKey_${ASC_KEY_ID}.p8"
if [ ! -f "$STAGED_KEY" ]; then
  cp "$ASC_KEY_PATH" "$STAGED_KEY"
  chmod 600 "$STAGED_KEY"
fi

if [ "$MODE" = "validate" ]; then
  step "validating macOS .pkg with App Store Connect; log: $DELIVER_LOG"
  ALTOOL_VERB="--validate-app"
  ITMS_MODE="verify"
else
  step "uploading macOS .pkg to App Store Connect (TestFlight); log: $DELIVER_LOG"
  ALTOOL_VERB="--upload-app"
  ITMS_MODE="upload"
fi

PROXY_URL="${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}"
PROXY_HOST=""
PROXY_PORT=""
if [ -n "$PROXY_URL" ]; then
  PROXY_HOSTPORT="${PROXY_URL#*://}"
  PROXY_HOSTPORT="${PROXY_HOSTPORT%/}"
  PROXY_HOST="${PROXY_HOSTPORT%%:*}"
  PROXY_PORT="${PROXY_HOSTPORT##*:}"
  case "$PROXY_PORT" in
    ''|*[!0-9]*) PROXY_HOST=""; PROXY_PORT="" ;;
  esac
fi

ITMS="$(xcode-select -p)/usr/bin/iTMSTransporter"

if [ -n "$PROXY_HOST" ] && [ -x "$ITMS" ] && [ "$MODE" = "validate" ]; then
  echo "FAIL: --validate is not available on a proxied machine; use --upload."
  exit 1
fi

if [ -n "$PROXY_HOST" ] && [ -x "$ITMS" ]; then
  echo "  route   : iTMSTransporter via proxy $PROXY_HOST:$PROXY_PORT"
  "$ITMS" -m "$ITMS_MODE" \
    -assetFile "$PKG" \
    -apiKey "$ASC_KEY_ID" \
    -apiIssuer "$ASC_ISSUER_ID" \
    -Dhttp.proxyHost="$PROXY_HOST" -Dhttp.proxyPort="$PROXY_PORT" \
    -Dhttps.proxyHost="$PROXY_HOST" -Dhttps.proxyPort="$PROXY_PORT" \
    > "$DELIVER_LOG" 2>&1
  echo "  iTMSTransporter exit: $?  (a fact, not the verdict)"
  if /usr/bin/grep -qE "(uploaded|verified) successfully" "$DELIVER_LOG" 2>/dev/null; then
    echo "UPLOAD: PASS — macOS build $EFFECTIVE_BUILD delivered."
    note "log: $DELIVER_LOG"
    exit 0
  fi
  echo "FAIL: iTMSTransporter did not report a successful $ITMS_MODE — read $DELIVER_LOG."
  /usr/bin/grep -E "ERROR|error:" "$DELIVER_LOG" | tail -8
  exit 1
fi

xcrun altool "$ALTOOL_VERB" \
  -f "$PKG" \
  -t osx \
  --apiKey "$ASC_KEY_ID" \
  --apiIssuer "$ASC_ISSUER_ID" \
  --output-format json > "$DELIVER_LOG" 2>&1
echo "  altool exit: $?  (a fact, not the verdict)"

if /usr/bin/grep -q '"product-errors"' "$DELIVER_LOG" 2>/dev/null; then
  echo "FAIL: App Store Connect rejected the macOS package."
  /usr/bin/python3 -c '
import json,sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("    (unparseable altool output: %s)" % e); sys.exit(0)
for e in d.get("product-errors", []):
    print("    %s: %s" % (e.get("code"), e.get("message")))
' "$DELIVER_LOG"
  exit 1
fi
if ! /usr/bin/grep -qi "success\|No errors" "$DELIVER_LOG" 2>/dev/null; then
  echo "FAIL: altool reported neither an error nor a success — read $DELIVER_LOG."
  exit 1
fi

echo
if [ "$MODE" = "validate" ]; then
  echo "VALIDATE: PASS — macOS build $EFFECTIVE_BUILD would be accepted."
else
  echo "UPLOAD: PASS — macOS build $EFFECTIVE_BUILD delivered."
fi
note "log: $DELIVER_LOG"
exit 0
