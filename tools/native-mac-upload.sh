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
#   3. Both the main app AND every embedded `.appex` (`BainLuckWidget.appex`) must carry
#      boolean `true` for `com.apple.security.app-sandbox` on macOS (ITMS-90296).
#   4. Provisioning profiles on macOS use `.provisionprofile`, carry `Platform = [OSX]`,
#      have no `ProvisionedDevices`, are unexpired, and spell the identifier key
#      `Entitlements.com.apple.application-identifier`.
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
#   tools/native-mac-upload.sh --export --reuse-archive --build 81 [--expected-source-sha <sha>]
#
#   --repo PATH                archive that tree instead of the script's own
#   --allow-stale-tree         build anyway from a tree that is behind master or dirty
#   --marketing-version VER    override MARKETING_VERSION (default: 1.0.4)
#   --expected-source-sha SHA  require reused archive provenance to match SHA prefix
#
# CREDENTIALS (upload/validate only; resolved from env or ~/.claude/.env, never printed)
#   ASC_KEY_ID     App Store Connect API key id
#   ASC_ISSUER_ID  App Store Connect API issuer uuid
#   ASC_KEY_PATH   path to AuthKey_<ASC_KEY_ID>.p8
set -uo pipefail

TEAM_ID="${NATIVE_MAC_TEAM_ID:-J893F72P4R}"
APP_BUNDLE_ID="${NATIVE_MAC_APP_BUNDLE_ID:-com.bainluck.Bain-Luck}"
WIDGET_BUNDLE_ID="${NATIVE_MAC_WIDGET_BUNDLE_ID:-com.bainluck.Bain-Luck.BainLuckWidget}"
CODESIGN_BIN="${NATIVE_MAC_CODESIGN_BIN:-/usr/bin/codesign}"
XCODEBUILD_BIN="${NATIVE_MAC_XCODEBUILD_BIN:-/usr/bin/xcodebuild}"
PKGUTIL_BIN="${NATIVE_MAC_PKGUTIL_BIN:-/usr/sbin/pkgutil}"
SECURITY_BIN="${NATIVE_MAC_SECURITY_BIN:-/usr/bin/security}"
ALTOOL_RUNNER="${NATIVE_MAC_ALTOOL_RUNNER:-}"

note() { echo "  $1"; }
step() { echo; echo "==> $1"; }

# ─── PRODUCTION DECIDING FUNCTIONS (exercised directly by --self-check) ──────

# A. Parse signed entitlements plist from codesign and require boolean True for
#    `com.apple.security.app-sandbox`.
#    Outputs one of:
#      ENTITLEMENT_TRUE|<bundle>
#      ENTITLEMENT_FALSE|<bundle>|<detail>
#      ENTITLEMENT_MISSING|<bundle>|<detail>
#      ENTITLEMENT_EXTRACTION_FAILED|<bundle>|<detail>
check_bundle_sandbox_entitlement() {
  local bundle_path="$1"
  python3 - "$CODESIGN_BIN" "$bundle_path" <<'PY'
import plistlib, subprocess, sys

codesign_bin, bundle_path = sys.argv[1], sys.argv[2]
try:
    proc = subprocess.run(
        [codesign_bin, "-d", "--entitlements", ":-", bundle_path],
        capture_output=True,
    )
except OSError as exc:
    print(f"ENTITLEMENT_EXTRACTION_FAILED|{bundle_path}|failed to execute {codesign_bin}: {exc}")
    sys.exit(1)

if proc.returncode != 0:
    err = proc.stderr.decode("utf-8", "replace").strip().replace("\n", " ")
    print(f"ENTITLEMENT_EXTRACTION_FAILED|{bundle_path}|codesign exited {proc.returncode}: {err}")
    sys.exit(1)

raw = proc.stdout
if not raw or not raw.strip():
    print(f"ENTITLEMENT_EXTRACTION_FAILED|{bundle_path}|codesign produced empty entitlement output")
    sys.exit(1)

try:
    plist_obj = plistlib.loads(raw)
except Exception as exc:
    print(f"ENTITLEMENT_EXTRACTION_FAILED|{bundle_path}|malformed entitlement plist: {exc}")
    sys.exit(1)

if not isinstance(plist_obj, dict):
    print(f"ENTITLEMENT_EXTRACTION_FAILED|{bundle_path}|entitlement plist root is {type(plist_obj).__name__}, not dict")
    sys.exit(1)

key = "com.apple.security.app-sandbox"
if key not in plist_obj:
    print(f"ENTITLEMENT_MISSING|{bundle_path}|{key} key is absent from signed entitlements")
    sys.exit(1)

val = plist_obj[key]
# Note: in Python isinstance(True, int) is True, so check isinstance(val, bool) explicitly!
if isinstance(val, bool) and val is True:
    print(f"ENTITLEMENT_TRUE|{bundle_path}|{key}=true")
    sys.exit(0)

print(
    f"ENTITLEMENT_FALSE|{bundle_path}|{key} is {val!r} (type {type(val).__name__}), "
    "must be boolean True"
)
sys.exit(1)
PY
}

# Verify a macOS bundle's signature and TeamIdentifier via codesign.
check_bundle_codesign_and_team() {
  local bundle_path="$1"
  local expected_team="$2"
  local expected_bid="$3"
  python3 - "$CODESIGN_BIN" "$bundle_path" "$expected_team" "$expected_bid" <<'PY'
import subprocess, sys

codesign_bin, bundle_path, expected_team, expected_bid = sys.argv[1:5]

v_proc = subprocess.run(
    [codesign_bin, "-vvv", "--deep", "--strict", bundle_path],
    capture_output=True,
    text=True,
)
if v_proc.returncode != 0:
    detail = (v_proc.stderr or v_proc.stdout or "").strip().replace("\n", " ")
    print(f"CODESIGN_VERIFY_FAILED|{bundle_path}|codesign -vvv --deep --strict exited {v_proc.returncode}: {detail}")
    sys.exit(1)

d_proc = subprocess.run(
    [codesign_bin, "-dvvv", bundle_path],
    capture_output=True,
    text=True,
)
if d_proc.returncode != 0:
    detail = (d_proc.stderr or d_proc.stdout or "").strip().replace("\n", " ")
    print(f"CODESIGN_INSPECT_FAILED|{bundle_path}|codesign -dvvv exited {d_proc.returncode}: {detail}")
    sys.exit(1)

combined = (d_proc.stderr or "") + "\n" + (d_proc.stdout or "")
fields = {}
for line in combined.splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        fields[k.strip()] = v.strip()

ident = fields.get("Identifier", "")
team = fields.get("TeamIdentifier", "")
if ident != expected_bid:
    print(f"WRONG_CODESIGN_IDENTIFIER|{bundle_path}|codesign Identifier={ident!r}, expected {expected_bid!r}")
    sys.exit(1)
if team != expected_team:
    print(f"WRONG_TEAM_ID|{bundle_path}|codesign TeamIdentifier={team!r}, expected {expected_team!r}")
    sys.exit(1)

print(f"CODESIGN_OK|{bundle_path}|Identifier={ident} TeamIdentifier={team}")
sys.exit(0)
PY
}

# Inspect a macOS `.app` bundle (and its embedded `BainLuckWidget.appex`) inside
# either an `.xcarchive` or an expanded `.pkg` payload.
verify_macos_app_bundle() {
  local app_path="$1"
  local expected_marketing="$2"
  local expected_build="$3"
  local expected_team="$4"
  local expected_app_bid="$5"
  local expected_widget_bid="$6"

  python3 - "$app_path" "$expected_marketing" "$expected_build" "$expected_app_bid" "$expected_widget_bid" <<'PY'
import os, plistlib, sys

app_path, exp_ver, exp_build, exp_app_bid, exp_widget_bid = sys.argv[1:6]

def fail(code: str, msg: str) -> None:
    print(f"{code}|{msg}")
    sys.exit(1)

app_info_path = os.path.join(app_path, "Contents", "Info.plist")
if not os.path.isfile(app_info_path):
    fail("NOT_MACOS_APP_LAYOUT", f"missing macOS bundle Info.plist at {app_info_path}")

try:
    with open(app_info_path, "rb") as fh:
        app_info = plistlib.load(fh)
except Exception as exc:
    fail("INVALID_APP_INFO_PLIST", f"cannot parse {app_info_path}: {exc}")

dt_platform = app_info.get("DTPlatformName", "")
supported = app_info.get("CFBundleSupportedPlatforms") or []
if dt_platform != "macosx" or ("MacOSX" not in supported and dt_platform != "macosx"):
    fail(
        "WRONG_PLATFORM",
        f"app bundle platform is DTPlatformName={dt_platform!r} CFBundleSupportedPlatforms={supported!r}, expected macosx/MacOSX",
    )

exec_name = app_info.get("CFBundleExecutable") or "Bain Luck"
exec_path = os.path.join(app_path, "Contents", "MacOS", exec_name)
if not os.path.isfile(exec_path):
    fail("MISSING_MACOS_EXECUTABLE", f"missing macOS executable at {exec_path}")

app_bid = app_info.get("CFBundleIdentifier", "")
if app_bid != exp_app_bid:
    fail("WRONG_BUNDLE_ID", f"app CFBundleIdentifier={app_bid!r}, expected {exp_app_bid!r}")

app_ver = str(app_info.get("CFBundleShortVersionString", ""))
app_build = str(app_info.get("CFBundleVersion", ""))
app_minos = str(app_info.get("LSMinimumSystemVersion", "?"))
if app_ver != exp_ver or app_build != exp_build:
    fail(
        "VERSION_BUILD_MISMATCH",
        f"app carries {app_ver} ({app_build}), expected {exp_ver} ({exp_build})",
    )

widget_path = os.path.join(app_path, "Contents", "PlugIns", "BainLuckWidget.appex")
if not os.path.isdir(widget_path):
    fail("MISSING_EMBEDDED_WIDGET", f"missing required embedded widget at {widget_path}")

widget_info_path = os.path.join(widget_path, "Contents", "Info.plist")
if not os.path.isfile(widget_info_path):
    fail("MISSING_EMBEDDED_WIDGET_PLIST", f"missing widget Info.plist at {widget_info_path}")

try:
    with open(widget_info_path, "rb") as fh:
        w_info = plistlib.load(fh)
except Exception as exc:
    fail("INVALID_WIDGET_INFO_PLIST", f"cannot parse {widget_info_path}: {exc}")

w_platform = w_info.get("DTPlatformName", "")
if w_platform != "macosx":
    fail("WRONG_WIDGET_PLATFORM", f"widget DTPlatformName={w_platform!r}, expected 'macosx'")

w_bid = w_info.get("CFBundleIdentifier", "")
if w_bid != exp_widget_bid:
    fail("WRONG_BUNDLE_ID", f"widget CFBundleIdentifier={w_bid!r}, expected {exp_widget_bid!r}")

w_ver = str(w_info.get("CFBundleShortVersionString", ""))
w_build = str(w_info.get("CFBundleVersion", ""))
if w_ver != exp_ver or w_build != exp_build:
    fail(
        "VERSION_BUILD_MISMATCH",
        f"embedded widget carries {w_ver} ({w_build}), expected {exp_ver} ({exp_build})",
    )

print(
    f"BUNDLE_METADATA_OK|app={app_bid} {app_ver} ({app_build}) minOS={app_minos}; "
    f"widget={w_bid} {w_ver} ({w_build})"
)
PY
  local meta_rc=$?
  if [ "$meta_rc" -ne 0 ]; then
    return 1
  fi

  local cs_out
  if ! cs_out=$(check_bundle_codesign_and_team "$app_path" "$expected_team" "$expected_app_bid"); then
    echo "$cs_out"
    return 1
  fi

  local sb_out
  if ! sb_out=$(check_bundle_sandbox_entitlement "$app_path"); then
    echo "$sb_out"
    return 1
  fi

  # Check every embedded .appex in Contents/PlugIns (including BainLuckWidget.appex)
  local appex
  for appex in "$app_path/Contents/PlugIns"/*.appex; do
    [ -e "$appex" ] || continue
    local ex_bid="$expected_widget_bid"
    if [ "$(basename "$appex")" != "BainLuckWidget.appex" ]; then
      ex_bid=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$appex/Contents/Info.plist" 2>/dev/null || echo "")
    fi
    if ! cs_out=$(check_bundle_codesign_and_team "$appex" "$expected_team" "$ex_bid"); then
      echo "$cs_out"
      return 1
    fi
    if ! sb_out=$(check_bundle_sandbox_entitlement "$appex"); then
      echo "$sb_out"
      return 1
    fi
  done

  return 0
}

# Stamp provenance into a freshly built archive so `--reuse-archive` can report
# whether source provenance was recorded or unrecorded.
write_archive_provenance() {
  local archive_path="$1"
  local tree_sha="$2"
  local ios_tree_sha="$3"
  local marketing_ver="$4"
  local build_num="$5"
  python3 - "$archive_path/BainLuckSourceProvenance.plist" "$tree_sha" "$ios_tree_sha" "$marketing_ver" "$build_num" <<'PY'
import datetime, plistlib, sys
out_path, tree_sha, ios_sha, m_ver, b_num = sys.argv[1:6]
payload = {
    "SourceTreeSHA": tree_sha,
    "SourceIOSTreeSHA": ios_sha,
    "MarketingVersion": m_ver,
    "BuildNumber": b_num,
    "BuiltAtUTC": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
with open(out_path, "wb") as fh:
    plistlib.dump(payload, fh)
PY
}

# Verify a fresh or reused `.xcarchive` (Archive Info.plist + .app + .appex +
# codesign + entitlements + provenance check).
verify_archive_bundle() {
  local archive_path="$1"
  local expected_marketing="$2"
  local expected_build="$3"
  local expected_team="$4"
  local expected_app_bid="$5"
  local expected_widget_bid="$6"
  local is_reuse="$7"
  local expected_source_sha="${8:-}"

  if [ ! -d "$archive_path" ]; then
    echo "FAIL: no archive at $archive_path"
    return 1
  fi

  local archive_meta_out
  if ! archive_meta_out=$(python3 - "$archive_path" "$expected_marketing" "$expected_build" "$expected_team" "$expected_app_bid" "$is_reuse" "$expected_source_sha" <<'PY'
import os, plistlib, sys

archive_path, exp_ver, exp_build, exp_team, exp_app_bid, is_reuse, exp_sha = sys.argv[1:8]

info_path = os.path.join(archive_path, "Info.plist")
if not os.path.isfile(info_path):
    print(f"ARCHIVE_INFO_MISSING|missing {info_path}")
    sys.exit(1)

try:
    with open(info_path, "rb") as fh:
        info = plistlib.load(fh)
except Exception as exc:
    print(f"ARCHIVE_INFO_INVALID|cannot parse {info_path}: {exc}")
    sys.exit(1)

app_props = info.get("ApplicationProperties") or {}
if not isinstance(app_props, dict) or not app_props:
    print("ARCHIVE_NOT_APP_ARCHIVE|Info.plist is missing ApplicationProperties")
    sys.exit(1)

a_bid = app_props.get("CFBundleIdentifier", "")
a_ver = str(app_props.get("CFBundleShortVersionString", ""))
a_build = str(app_props.get("CFBundleVersion", ""))
a_team = app_props.get("SigningIdentity", "") or app_props.get("Team", "")
rel_app = app_props.get("ApplicationPath", "")

if a_bid != exp_app_bid:
    print(f"WRONG_BUNDLE_ID|archive ApplicationProperties CFBundleIdentifier={a_bid!r}, expected {exp_app_bid!r}")
    sys.exit(1)
if a_ver != exp_ver or a_build != exp_build:
    print(f"VERSION_BUILD_MISMATCH|archive ApplicationProperties carries {a_ver} ({a_build}), expected {exp_ver} ({exp_build})")
    sys.exit(1)
if a_team and exp_team not in a_team and a_team != exp_team:
    print(f"WRONG_TEAM_ID|archive ApplicationProperties Team/SigningIdentity={a_team!r} does not match {exp_team!r}")
    sys.exit(1)

prov_path = os.path.join(archive_path, "BainLuckSourceProvenance.plist")
prov_note = "UNRECORDED (binary/bundle metadata verified; archive carries no source-SHA provenance stamp — do not label exact-source from build number alone)"
if os.path.isfile(prov_path):
    try:
        with open(prov_path, "rb") as fh:
            prov = plistlib.load(fh)
        src_sha = prov.get("SourceTreeSHA", "")
        ios_sha = prov.get("SourceIOSTreeSHA", "")
        built_at = prov.get("BuiltAtUTC", "?")
        if exp_sha and not src_sha.startswith(exp_sha):
            print(f"SOURCE_SHA_MISMATCH|archive provenance SourceTreeSHA={src_sha!r} does not match expected {exp_sha!r}")
            sys.exit(1)
        prov_note = f"RECORDED commit={src_sha[:10]} ios_tree={ios_sha[:10]} built_at={built_at}"
    except Exception as exc:
        print(f"PROVENANCE_INVALID|cannot parse {prov_path}: {exc}")
        sys.exit(1)
elif exp_sha:
    print(f"SOURCE_SHA_MISSING|--expected-source-sha {exp_sha} requested, but archive has no BainLuckSourceProvenance.plist")
    sys.exit(1)

print(f"ARCHIVE_HEADER_OK|rel_app={rel_app}|provenance={prov_note}")
PY
  ); then
    echo "FAIL: $archive_meta_out"
    return 1
  fi

  local prov_summary="${archive_meta_out#*provenance=}"
  local app_path
  app_path=$(find "$archive_path/Products/Applications" -maxdepth 1 -name '*.app' 2>/dev/null | head -1)
  if [ -z "$app_path" ] || [ ! -d "$app_path" ]; then
    echo "FAIL: archive at $archive_path contains no .app under Products/Applications"
    return 1
  fi

  local bundle_out
  if ! bundle_out=$(verify_macos_app_bundle "$app_path" "$expected_marketing" "$expected_build" "$expected_team" "$expected_app_bid" "$expected_widget_bid"); then
    echo "FAIL: $bundle_out"
    return 1
  fi

  note "archived   : $(basename "$app_path")  $expected_marketing ($expected_build)  team=$expected_team  sandbox=true (app + widget)"
  note "provenance : $prov_summary"
  return 0
}

# Run `xcodebuild archive` and fail immediately if the command exits nonzero,
# even if a partial archive directory exists on disk.
run_archive_step() {
  local project="$1"
  local scheme="$2"
  local archive_path="$3"
  local effective_build="$4"
  local marketing_version="$5"
  local archive_log="$6"
  shift 6
  local spm_flags=("$@")

  rm -rf "$archive_path"
  "$XCODEBUILD_BIN" \
    -project "$project" \
    -scheme "$scheme" \
    -destination 'generic/platform=macOS' \
    -archivePath "$archive_path" \
    -disableAutomaticPackageResolution \
    ${spm_flags[@]+"${spm_flags[@]}"} \
    CURRENT_PROJECT_VERSION="$effective_build" \
    MARKETING_VERSION="$marketing_version" \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    archive > "$archive_log" 2>&1
  local rc=$?
  note "xcodebuild archive exit: $rc"
  if [ "$rc" -ne 0 ]; then
    echo "FAIL: ARCHIVE_COMMAND_FAILED — xcodebuild archive exited $rc (refusing to continue even if partial archive files exist)."
    return "$rc"
  fi
  return 0
}

# Run `xcodebuild -exportArchive` and fail immediately if the command exits
# nonzero, even if a partial `.pkg` exists on disk.
run_export_step() {
  local archive_path="$1"
  local export_options="$2"
  local export_dir="$3"
  local export_log="$4"

  rm -rf "$export_dir"
  "$XCODEBUILD_BIN" \
    -exportArchive \
    -archivePath "$archive_path" \
    -exportOptionsPlist "$export_options" \
    -exportPath "$export_dir" > "$export_log" 2>&1
  local rc=$?
  note "xcodebuild -exportArchive exit: $rc"
  if [ "$rc" -ne 0 ]; then
    echo "FAIL: EXPORT_COMMAND_FAILED — xcodebuild -exportArchive exited $rc (refusing to continue even if a partial .pkg exists)."
    return "$rc"
  fi
  return 0
}

# Verify the exported `.pkg` installer signature, team ID, expansion, and the
# packaged `.app` and embedded `BainLuckWidget.appex` inside the expanded payload.
verify_exported_pkg() {
  local pkg_path="$1"
  local expected_marketing="$2"
  local expected_build="$3"
  local expected_team="$4"
  local expected_app_bid="$5"
  local expected_widget_bid="$6"
  local min_bytes="${7:-1000000}"

  if [ -z "$pkg_path" ] || [ ! -f "$pkg_path" ]; then
    echo "FAIL: PKG_MISSING — no exported .pkg found at '${pkg_path:-<empty>}'"
    return 1
  fi

  local bytes
  bytes=$(/usr/bin/stat -f %z "$pkg_path" 2>/dev/null || echo 0)
  if [ "$bytes" -lt "$min_bytes" ] 2>/dev/null; then
    echo "FAIL: PKG_TOO_SMALL — $pkg_path is only $bytes bytes (minimum $min_bytes bytes)."
    return 1
  fi

  local sig_out sig_rc
  sig_out=$("$PKGUTIL_BIN" --check-signature "$pkg_path" 2>&1)
  sig_rc=$?
  if [ "$sig_rc" -ne 0 ]; then
    echo "FAIL: PKG_SIGNATURE_INVALID — pkgutil --check-signature exited $sig_rc on $pkg_path: $sig_out"
    return 1
  fi
  if ! printf '%s\n' "$sig_out" | /usr/bin/grep -q "$expected_team"; then
    echo "FAIL: PKG_WRONG_TEAM_ID — pkgutil --check-signature output does not contain expected team $expected_team"
    return 1
  fi

  local tmp_pkg_dir
  tmp_pkg_dir=$(mktemp -d)
  local exp_out exp_rc
  exp_out=$("$PKGUTIL_BIN" --expand-full "$pkg_path" "$tmp_pkg_dir/expanded" 2>&1)
  exp_rc=$?
  if [ "$exp_rc" -ne 0 ]; then
    rm -rf "$tmp_pkg_dir"
    echo "FAIL: PKG_EXPAND_FAILED — pkgutil --expand-full exited $exp_rc: $exp_out"
    return 1
  fi

  local pkg_app
  pkg_app=$(find "$tmp_pkg_dir/expanded" -type d -name '*.app' 2>/dev/null | head -1)
  if [ -z "$pkg_app" ] || [ ! -d "$pkg_app" ]; then
    rm -rf "$tmp_pkg_dir"
    echo "FAIL: PKG_PAYLOAD_MISSING_APP — expanded $pkg_path contains no .app bundle"
    return 1
  fi

  local bundle_out
  if ! bundle_out=$(verify_macos_app_bundle "$pkg_app" "$expected_marketing" "$expected_build" "$expected_team" "$expected_app_bid" "$expected_widget_bid"); then
    rm -rf "$tmp_pkg_dir"
    echo "FAIL: PKG_PAYLOAD_INVALID — $bundle_out"
    return 1
  fi

  rm -rf "$tmp_pkg_dir"
  note "pkg        : $(basename "$pkg_path")  $expected_marketing ($expected_build)  team=$expected_team  sandbox=true  bytes=$bytes"
  return 0
}

# Inspect installed provisioning profiles for a given bundle ID, requiring:
# - valid CMS signature/plist
# - no `ProvisionedDevices` (Store profile, not Development/AdHoc)
# - `Platform` contains `OSX` or `macOS` (rejecting iOS profiles)
# - `Entitlements.com.apple.application-identifier` == `<TEAM_ID>.<bundle_id>`
# - `ExpirationDate` is parseable and in the future relative to `now_epoch`
find_mac_store_profile() {
  local prof_dir="$1"
  local want_bid="$2"
  local expected_team="$3"
  local now_epoch="${4:-$(date +%s)}"

  python3 - "$SECURITY_BIN" "$prof_dir" "$want_bid" "$expected_team" "$now_epoch" <<'PY'
import datetime, glob, os, plistlib, subprocess, sys

sec_bin, prof_dir, want_bid, exp_team, now_s = sys.argv[1:6]
now_epoch = int(now_s)

candidates = sorted(
    glob.glob(os.path.join(prof_dir, "*.provisionprofile"))
    + glob.glob(os.path.join(prof_dir, "*.mobileprovision"))
)

rejections = []
for p in candidates:
    out = subprocess.run([sec_bin, "cms", "-D", "-i", p], capture_output=True)
    if out.returncode != 0:
        rejections.append(f"{os.path.basename(p)}: cms decode exited {out.returncode}")
        continue
    try:
        pl = plistlib.loads(out.stdout)
    except Exception as exc:
        rejections.append(f"{os.path.basename(p)}: malformed plist ({exc})")
        continue

    name = pl.get("Name") or os.path.basename(p)
    ent = pl.get("Entitlements") or {}
    appid = ent.get("com.apple.application-identifier") or ent.get("application-identifier") or ""
    if appid != f"{exp_team}.{want_bid}":
        continue

    if "ProvisionedDevices" in pl:
        rejections.append(f"{name}: DEV_PROFILE_HAS_DEVICES")
        continue

    plats = pl.get("Platform") or []
    if "OSX" not in plats and "macOS" not in plats:
        rejections.append(f"{name}: WRONG_PLATFORM ({plats!r})")
        continue

    exp = pl.get("ExpirationDate")
    exp_epoch = None
    exp_str = ""
    if isinstance(exp, datetime.datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=datetime.timezone.utc)
        exp_epoch = int(exp.timestamp())
        exp_str = exp.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(exp, str) and exp:
        try:
            dt = datetime.datetime.strptime(exp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            exp_epoch = int(dt.timestamp())
            exp_str = exp
        except ValueError:
            pass

    if exp_epoch is None:
        rejections.append(f"{name}: PROFILE_EXPIRY_UNPARSEABLE ({exp!r})")
        continue

    if exp_epoch < now_epoch:
        rejections.append(f"{name}: PROFILE_EXPIRED ({exp_str})")
        continue

    print(f"PROFILE_OK|{name}|{exp_str}")
    sys.exit(0)

if rejections:
    print("PROFILE_REJECTED|" + "; ".join(rejections))
else:
    print(f"PROFILE_MISSING|no matching MAC_APP_STORE profile for {exp_team}.{want_bid}")
sys.exit(1)
PY
}

# Check keychain identities required for macOS archive/export.
check_mac_signing_identities() {
  local mode="$1"
  local cs_ids all_ids rc_cs rc_all
  cs_ids=$("$SECURITY_BIN" find-identity -v -p codesigning 2>&1)
  rc_cs=$?
  if [ "$rc_cs" -ne 0 ]; then
    echo "IDENTITY_CHECK_FAILED|security find-identity -p codesigning exited $rc_cs"
    return 1
  fi
  if ! printf '%s\n' "$cs_ids" | /usr/bin/grep -q "Apple Distribution"; then
    echo "MISSING_APPLE_DISTRIBUTION|no 'Apple Distribution' code-signing identity in keychain"
    return 1
  fi

  all_ids=$("$SECURITY_BIN" find-identity -v 2>&1)
  rc_all=$?
  if [ "$rc_all" -ne 0 ]; then
    echo "IDENTITY_CHECK_FAILED|security find-identity exited $rc_all"
    return 1
  fi
  if printf '%s\n' "$all_ids" | /usr/bin/grep -qE "3rd Party Mac Developer Installer|Mac Installer Distribution"; then
    echo "IDENTITIES_OK|Apple Distribution + Mac Installer Distribution present"
    return 0
  fi

  if [ "$mode" = "archive" ]; then
    echo "INSTALLER_CERT_WARN_ARCHIVE_ONLY|Apple Distribution present; Mac Installer Distribution absent (archive can run, export/upload cannot)"
    return 0
  fi

  echo "MISSING_MAC_INSTALLER_CERT|no '3rd Party Mac Developer Installer' or 'Mac Installer Distribution' identity in keychain"
  return 1
}

# Validate ExportOptions-MacAppStore.plist structure and required settings.
check_export_options_plist() {
  local plist_path="$1"
  local expected_team="$2"
  local expected_app_bid="$3"
  local expected_widget_bid="$4"
  python3 - "$plist_path" "$expected_team" "$expected_app_bid" "$expected_widget_bid" <<'PY'
import os, plistlib, sys

plist_path, exp_team, exp_app_bid, exp_widget_bid = sys.argv[1:5]
if not os.path.isfile(plist_path):
    print(f"EXPORT_OPTIONS_MISSING|no export options at {plist_path}")
    sys.exit(1)

try:
    with open(plist_path, "rb") as fh:
        pl = plistlib.load(fh)
except Exception as exc:
    print(f"EXPORT_OPTIONS_MALFORMED|{plist_path} is not a valid plist: {exc}")
    sys.exit(1)

method = pl.get("method")
if method != "app-store-connect":
    print(f"EXPORT_OPTIONS_WRONG_METHOD|method={method!r}, expected 'app-store-connect'")
    sys.exit(1)

manage = pl.get("manageAppVersionAndBuildNumber")
if manage is not False:
    print(f"EXPORT_OPTIONS_WRONG_MANAGE_VERSION|manageAppVersionAndBuildNumber={manage!r}, must be boolean False")
    sys.exit(1)

team = pl.get("teamID")
if team != exp_team:
    print(f"EXPORT_OPTIONS_WRONG_TEAM|teamID={team!r}, expected {exp_team!r}")
    sys.exit(1)

style = pl.get("signingStyle", "automatic")
profs = pl.get("provisioningProfiles") or {}
if style == "manual":
    for bid in (exp_app_bid, exp_widget_bid):
        if not profs.get(bid):
            print(f"EXPORT_OPTIONS_MISSING_PROFILE_MAP|signingStyle=manual but provisioningProfiles is missing {bid}")
            sys.exit(1)

print(f"EXPORT_OPTIONS_OK|method={method} signingStyle={style} manageAppVersionAndBuildNumber=false teamID={team}")
sys.exit(0)
PY
}

# ─── BOUNDED OFFLINE --self-check (exercises actual production functions) ────
run_self_check() {
  local tmp_root
  tmp_root=$(mktemp -d)
  # Ensure cleanup on return
  trap 'rm -rf "$tmp_root"' RETURN

  local mock_bin="$tmp_root/bin"
  mkdir -p "$mock_bin"

  # 1. Mock codesign that inspects per-bundle mock files inside each fixture bundle
  cat > "$mock_bin/mock-codesign" <<'EOF'
#!/bin/bash
mode=""
ent=0
target=""
for arg in "$@"; do
  case "$arg" in
    -d) mode="d" ;;
    --entitlements) ent=1 ;;
    -vvv) mode="v" ;;
    -dvvv) mode="dv" ;;
    :-|--deep|--strict) ;;
    *) target="$arg" ;;
  esac
done
if [ "$mode" = "d" ] && [ "$ent" = "1" ]; then
  if [ -f "$target/.mock_codesign_ent_exit" ]; then
    rc=$(cat "$target/.mock_codesign_ent_exit")
    echo "mock codesign entitlement error" >&2
    exit "$rc"
  fi
  if [ -f "$target/.mock_entitlements" ]; then
    cat "$target/.mock_entitlements"
    exit 0
  fi
  exit 1
fi
if [ "$mode" = "v" ]; then
  if [ -f "$target/.mock_codesign_verify_exit" ]; then
    rc=$(cat "$target/.mock_codesign_verify_exit")
    echo "mock codesign verify failure" >&2
    exit "$rc"
  fi
  exit 0
fi
if [ "$mode" = "dv" ]; then
  if [ -f "$target/.mock_codesign_dvvv" ]; then
    cat "$target/.mock_codesign_dvvv" >&2
    exit 0
  fi
  exit 1
fi
exit 1
EOF
  chmod +x "$mock_bin/mock-codesign"

  # 2. Mock pkgutil that checks signature or copies fixture payload on --expand-full
  cat > "$mock_bin/mock-pkgutil" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "--check-signature" ]; then
  pkg="$2"
  if [ -f "${pkg}.sig_exit" ]; then
    rc=$(cat "${pkg}.sig_exit")
    cat "${pkg}.sig_out" 2>/dev/null || true
    exit "$rc"
  fi
  cat "${pkg}.sig_out" 2>/dev/null || echo "   1. 3rd Party Mac Developer Installer: Alex Bain (J893F72P4R)"
  exit 0
fi
if [ "${1:-}" = "--expand-full" ]; then
  pkg="$2"
  dest="$3"
  if [ -f "${pkg}.expand_exit" ]; then
    rc=$(cat "${pkg}.expand_exit")
    echo "mock pkgutil expand error" >&2
    exit "$rc"
  fi
  if [ -d "${pkg}.payload" ]; then
    mkdir -p "$dest"
    cp -R "${pkg}.payload/"* "$dest/"
    exit 0
  fi
  mkdir -p "$dest"
  exit 0
fi
exit 1
EOF
  chmod +x "$mock_bin/mock-pkgutil"

  # 3. Mock security that handles `cms -D -i <file>` and `find-identity`
  cat > "$mock_bin/mock-security" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "cms" ] && [ "${2:-}" = "-D" ] && [ "${3:-}" = "-i" ]; then
  cat "$4"
  exit $?
fi
if [ "${1:-}" = "find-identity" ]; then
  if [[ "$*" == *"-p codesigning"* ]]; then
    cat "${MOCK_SECURITY_CS_FILE}"
  else
    cat "${MOCK_SECURITY_ALL_FILE}"
  fi
  exit 0
fi
exit 1
EOF
  chmod +x "$mock_bin/mock-security"

  CODESIGN_BIN="$mock_bin/mock-codesign"
  PKGUTIL_BIN="$mock_bin/mock-pkgutil"
  SECURITY_BIN="$mock_bin/mock-security"

  # Helper to build a valid macOS .xcarchive fixture
  make_valid_archive() {
    local arch="$1"
    local app="$arch/Products/Applications/Bain Luck.app"
    local wid="$app/Contents/PlugIns/BainLuckWidget.appex"
    mkdir -p "$app/Contents/MacOS" "$wid/Contents/MacOS"
    echo "binary" > "$app/Contents/MacOS/Bain Luck"
    echo "widget" > "$wid/Contents/MacOS/BainLuckWidget"

    python3 - "$arch" "$app" "$wid" <<'PY'
import os, plistlib, sys
arch, app, wid = sys.argv[1:4]
with open(os.path.join(arch, "Info.plist"), "wb") as fh:
    plistlib.dump({
        "ApplicationProperties": {
            "ApplicationPath": "Applications/Bain Luck.app",
            "CFBundleIdentifier": "com.bainluck.Bain-Luck",
            "CFBundleShortVersionString": "1.0.4",
            "CFBundleVersion": "81",
            "Team": "J893F72P4R",
        }
    }, fh)
with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
    plistlib.dump({
        "CFBundleIdentifier": "com.bainluck.Bain-Luck",
        "CFBundleExecutable": "Bain Luck",
        "CFBundleShortVersionString": "1.0.4",
        "CFBundleVersion": "81",
        "DTPlatformName": "macosx",
        "CFBundleSupportedPlatforms": ["MacOSX"],
        "LSMinimumSystemVersion": "14.0",
    }, fh)
with open(os.path.join(wid, "Contents", "Info.plist"), "wb") as fh:
    plistlib.dump({
        "CFBundleIdentifier": "com.bainluck.Bain-Luck.BainLuckWidget",
        "CFBundleExecutable": "BainLuckWidget",
        "CFBundleShortVersionString": "1.0.4",
        "CFBundleVersion": "81",
        "DTPlatformName": "macosx",
        "CFBundleSupportedPlatforms": ["MacOSX"],
    }, fh)
with open(os.path.join(app, ".mock_entitlements"), "wb") as fh:
    plistlib.dump({"com.apple.security.app-sandbox": True}, fh)
with open(os.path.join(wid, ".mock_entitlements"), "wb") as fh:
    plistlib.dump({"com.apple.security.app-sandbox": True}, fh)
with open(os.path.join(app, ".mock_codesign_dvvv"), "w") as fh:
    fh.write("Identifier=com.bainluck.Bain-Luck\nTeamIdentifier=J893F72P4R\n")
with open(os.path.join(wid, ".mock_codesign_dvvv"), "w") as fh:
    fh.write("Identifier=com.bainluck.Bain-Luck.BainLuckWidget\nTeamIdentifier=J893F72P4R\n")
PY
    write_archive_provenance "$arch" "3305dcbc7036dc14200921f99a31987e3c53b737" "ab3706bf22dfb01de34b2baf8c0a32b4746318ea" "1.0.4" "81"
  }

  local out

  # ── Control 1: Sandbox entitlement true vs false/non-bool/missing/malformed/failed
  local b_sb="$tmp_root/sb_bundle.app"
  mkdir -p "$b_sb"

  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"com.apple.security.app-sandbox": True}))' "$b_sb/.mock_entitlements"
  out=$(check_bundle_sandbox_entitlement "$b_sb") || { echo "SELF-CHECK FAIL: sandbox True rejected: $out"; return 1; }
  [[ "$out" == ENTITLEMENT_TRUE* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_TRUE, got $out"; return 1; }

  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"com.apple.security.app-sandbox": False}))' "$b_sb/.mock_entitlements"
  if out=$(check_bundle_sandbox_entitlement "$b_sb"); then
    echo "SELF-CHECK FAIL: sandbox False was accepted: $out"; return 1
  fi
  [[ "$out" == ENTITLEMENT_FALSE* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_FALSE for False, got $out"; return 1; }

  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"com.apple.security.app-sandbox": 1}))' "$b_sb/.mock_entitlements"
  if out=$(check_bundle_sandbox_entitlement "$b_sb"); then
    echo "SELF-CHECK FAIL: sandbox integer 1 was accepted: $out"; return 1
  fi
  [[ "$out" == ENTITLEMENT_FALSE* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_FALSE for int 1, got $out"; return 1; }

  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"other.key": True}))' "$b_sb/.mock_entitlements"
  if out=$(check_bundle_sandbox_entitlement "$b_sb"); then
    echo "SELF-CHECK FAIL: missing sandbox key was accepted: $out"; return 1
  fi
  [[ "$out" == ENTITLEMENT_MISSING* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_MISSING, got $out"; return 1; }

  printf '<plist><broken' > "$b_sb/.mock_entitlements"
  if out=$(check_bundle_sandbox_entitlement "$b_sb"); then
    echo "SELF-CHECK FAIL: malformed plist was accepted: $out"; return 1
  fi
  [[ "$out" == ENTITLEMENT_EXTRACTION_FAILED* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_EXTRACTION_FAILED for malformed XML, got $out"; return 1; }

  echo "1" > "$b_sb/.mock_codesign_ent_exit"
  if out=$(check_bundle_sandbox_entitlement "$b_sb"); then
    echo "SELF-CHECK FAIL: nonzero codesign exit was accepted: $out"; return 1
  fi
  [[ "$out" == ENTITLEMENT_EXTRACTION_FAILED* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_EXTRACTION_FAILED for nonzero codesign, got $out"; return 1; }

  # ── Control 2: Nonzero archive/export exit with plausible partial artifact on disk
  cat > "$mock_bin/mock-xcodebuild-fail" <<'EOF'
#!/bin/bash
for i in "$@"; do
  if [ "$prev" = "-archivePath" ]; then
    mkdir -p "$i/Products/Applications/Bain Luck.app/Contents"
  fi
  if [ "$prev" = "-exportPath" ]; then
    mkdir -p "$i"
    dd if=/dev/zero of="$i/Bain Luck.pkg" bs=1024 count=10 >/dev/null 2>&1
  fi
  prev="$i"
done
exit 65
EOF
  chmod +x "$mock_bin/mock-xcodebuild-fail"
  XCODEBUILD_BIN="$mock_bin/mock-xcodebuild-fail"

  if out=$(run_archive_step "$tmp_root/Dummy.xcodeproj" "Bain Luck" "$tmp_root/partial.xcarchive" "81" "1.0.4" "$tmp_root/arch.log"); then
    echo "SELF-CHECK FAIL: nonzero xcodebuild archive succeeded despite exit 65"; return 1
  fi
  [[ "$out" == *ARCHIVE_COMMAND_FAILED* ]] || { echo "SELF-CHECK FAIL: expected ARCHIVE_COMMAND_FAILED, got $out"; return 1; }

  if out=$(run_export_step "$tmp_root/partial.xcarchive" "$tmp_root/Export.plist" "$tmp_root/partial-export" "$tmp_root/exp.log"); then
    echo "SELF-CHECK FAIL: nonzero xcodebuild -exportArchive succeeded despite exit 65"; return 1
  fi
  [[ "$out" == *EXPORT_COMMAND_FAILED* ]] || { echo "SELF-CHECK FAIL: expected EXPORT_COMMAND_FAILED, got $out"; return 1; }

  # ── Control 3 & 5: Valid archive + mutations (wrong platform, bundle ID, build, widget sandbox, team, provenance)
  local good_arch="$tmp_root/good.xcarchive"
  make_valid_archive "$good_arch"
  out=$(verify_archive_bundle "$good_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1" "3305dcbc70") || {
    echo "SELF-CHECK FAIL: valid macOS archive failed verification: $out"; return 1
  }
  [[ "$out" == *"provenance : RECORDED commit=3305dcbc70"* ]] || {
    echo "SELF-CHECK FAIL: valid archive did not report recorded provenance: $out"; return 1
  }

  # Mutation 3a: Wrong platform (iphoneos)
  local bad_plat_arch="$tmp_root/bad_plat.xcarchive"
  make_valid_archive "$bad_plat_arch"
  /usr/libexec/PlistBuddy -c "Set :DTPlatformName iphoneos" "$bad_plat_arch/Products/Applications/Bain Luck.app/Contents/Info.plist"
  if out=$(verify_archive_bundle "$bad_plat_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1"); then
    echo "SELF-CHECK FAIL: iphoneos archive was accepted as macOS: $out"; return 1
  fi
  [[ "$out" == *WRONG_PLATFORM* ]] || { echo "SELF-CHECK FAIL: expected WRONG_PLATFORM, got $out"; return 1; }

  # Mutation 3b: Wrong bundle ID
  local bad_bid_arch="$tmp_root/bad_bid.xcarchive"
  make_valid_archive "$bad_bid_arch"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.example.wrong" "$bad_bid_arch/Products/Applications/Bain Luck.app/Contents/Info.plist"
  if out=$(verify_archive_bundle "$bad_bid_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1"); then
    echo "SELF-CHECK FAIL: wrong bundle ID archive was accepted: $out"; return 1
  fi
  [[ "$out" == *WRONG_BUNDLE_ID* ]] || { echo "SELF-CHECK FAIL: expected WRONG_BUNDLE_ID, got $out"; return 1; }

  # Mutation 3c: Wrong widget build number
  local bad_wbuild_arch="$tmp_root/bad_wbuild.xcarchive"
  make_valid_archive "$bad_wbuild_arch"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion 80" "$bad_wbuild_arch/Products/Applications/Bain Luck.app/Contents/PlugIns/BainLuckWidget.appex/Contents/Info.plist"
  if out=$(verify_archive_bundle "$bad_wbuild_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1"); then
    echo "SELF-CHECK FAIL: mismatched widget build number was accepted: $out"; return 1
  fi
  [[ "$out" == *VERSION_BUILD_MISMATCH* ]] || { echo "SELF-CHECK FAIL: expected VERSION_BUILD_MISMATCH, got $out"; return 1; }

  # Mutation 3d: Embedded widget has sandbox=false
  local bad_wsb_arch="$tmp_root/bad_wsb.xcarchive"
  make_valid_archive "$bad_wsb_arch"
  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"com.apple.security.app-sandbox": False}))' \
    "$bad_wsb_arch/Products/Applications/Bain Luck.app/Contents/PlugIns/BainLuckWidget.appex/.mock_entitlements"
  if out=$(verify_archive_bundle "$bad_wsb_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1"); then
    echo "SELF-CHECK FAIL: widget with sandbox=false was accepted: $out"; return 1
  fi
  [[ "$out" == *ENTITLEMENT_FALSE* ]] || { echo "SELF-CHECK FAIL: expected ENTITLEMENT_FALSE on widget, got $out"; return 1; }

  # Mutation 3e: Wrong TeamIdentifier
  local bad_team_arch="$tmp_root/bad_team.xcarchive"
  make_valid_archive "$bad_team_arch"
  printf 'Identifier=com.bainluck.Bain-Luck\nTeamIdentifier=OTHERTEAM9\n' > "$bad_team_arch/Products/Applications/Bain Luck.app/.mock_codesign_dvvv"
  if out=$(verify_archive_bundle "$bad_team_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1"); then
    echo "SELF-CHECK FAIL: wrong TeamIdentifier was accepted: $out"; return 1
  fi
  [[ "$out" == *WRONG_TEAM_ID* ]] || { echo "SELF-CHECK FAIL: expected WRONG_TEAM_ID, got $out"; return 1; }

  # Mutation 3f: Reused archive missing provenance fails when --expected-source-sha is set,
  # and warns UNRECORDED when --expected-source-sha is omitted.
  local unrec_arch="$tmp_root/unrec.xcarchive"
  make_valid_archive "$unrec_arch"
  rm -f "$unrec_arch/BainLuckSourceProvenance.plist"
  if out=$(verify_archive_bundle "$unrec_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1" "3305dcbc70"); then
    echo "SELF-CHECK FAIL: archive without provenance passed --expected-source-sha check: $out"; return 1
  fi
  [[ "$out" == *SOURCE_SHA_MISSING* ]] || { echo "SELF-CHECK FAIL: expected SOURCE_SHA_MISSING, got $out"; return 1; }
  out=$(verify_archive_bundle "$unrec_arch" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "1" "") || {
    echo "SELF-CHECK FAIL: valid archive without provenance should pass binary checks when no SHA asserted: $out"; return 1
  }
  [[ "$out" == *"UNRECORDED"* ]] || { echo "SELF-CHECK FAIL: expected UNRECORDED provenance note, got $out"; return 1; }

  # ── Control 3g & 5b: Exported .pkg verification (valid vs bad signature / bad payload)
  local good_pkg="$tmp_root/Bain Luck.pkg"
  dd if=/dev/zero of="$good_pkg" bs=1024 count=20 >/dev/null 2>&1
  echo "   1. 3rd Party Mac Developer Installer: Alex Bain (J893F72P4R)" > "${good_pkg}.sig_out"
  mkdir -p "${good_pkg}.payload"
  cp -R "$good_arch/Products/Applications/Bain Luck.app" "${good_pkg}.payload/"

  out=$(verify_exported_pkg "$good_pkg" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" 1024) || {
    echo "SELF-CHECK FAIL: valid exported .pkg failed verification: $out"; return 1
  }

  echo "1" > "${good_pkg}.sig_exit"
  if out=$(verify_exported_pkg "$good_pkg" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" 1024); then
    echo "SELF-CHECK FAIL: .pkg with failing pkgutil --check-signature was accepted: $out"; return 1
  fi
  [[ "$out" == *PKG_SIGNATURE_INVALID* ]] || { echo "SELF-CHECK FAIL: expected PKG_SIGNATURE_INVALID, got $out"; return 1; }
  rm -f "${good_pkg}.sig_exit"

  echo "1" > "${good_pkg}.expand_exit"
  if out=$(verify_exported_pkg "$good_pkg" "1.0.4" "81" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" 1024); then
    echo "SELF-CHECK FAIL: .pkg with failing pkgutil --expand-full was accepted: $out"; return 1
  fi
  [[ "$out" == *PKG_EXPAND_FAILED* ]] || { echo "SELF-CHECK FAIL: expected PKG_EXPAND_FAILED, got $out"; return 1; }
  rm -f "${good_pkg}.expand_exit"

  # ── Control 4: Signing/profile classification (dev vs iOS vs expired vs valid OSX Store; missing installer cert)
  local prof_dir="$tmp_root/profiles"
  mkdir -p "$prof_dir"
  local fixed_now=1761220000 # 2025-10-23 UTC

  # 4a: Dev profile with ProvisionedDevices -> rejected
  python3 - "$prof_dir/01-dev.provisionprofile" <<'PY'
import plistlib, sys
open(sys.argv[1], "wb").write(plistlib.dumps({
    "Name": "Mac Team Provisioning Profile",
    "Platform": ["OSX"],
    "ProvisionedDevices": ["DEV1"],
    "ExpirationDate": "2027-09-11T00:19:37Z",
    "Entitlements": {"com.apple.application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
}))
PY
  if out=$(find_mac_store_profile "$prof_dir" "$APP_BUNDLE_ID" "J893F72P4R" "$fixed_now"); then
    echo "SELF-CHECK FAIL: dev profile with ProvisionedDevices was accepted: $out"; return 1
  fi
  [[ "$out" == *DEV_PROFILE_HAS_DEVICES* ]] || { echo "SELF-CHECK FAIL: expected DEV_PROFILE_HAS_DEVICES, got $out"; return 1; }

  # 4b: iOS Store profile -> rejected
  python3 - "$prof_dir/02-ios.mobileprovision" <<'PY'
import plistlib, sys
open(sys.argv[1], "wb").write(plistlib.dumps({
    "Name": "BainLuck App AppStore 38",
    "Platform": ["iOS"],
    "ExpirationDate": "2027-09-11T00:19:37Z",
    "Entitlements": {"application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
}))
PY
  if out=$(find_mac_store_profile "$prof_dir" "$APP_BUNDLE_ID" "J893F72P4R" "$fixed_now"); then
    echo "SELF-CHECK FAIL: iOS profile was accepted as macOS Store profile: $out"; return 1
  fi
  [[ "$out" == *WRONG_PLATFORM* ]] || { echo "SELF-CHECK FAIL: expected WRONG_PLATFORM for iOS profile, got $out"; return 1; }

  # 4c: Expired OSX Store profile -> rejected
  python3 - "$prof_dir/03-expired.provisionprofile" <<'PY'
import plistlib, sys
open(sys.argv[1], "wb").write(plistlib.dumps({
    "Name": "BainLuck Mac Expired",
    "Platform": ["OSX"],
    "ExpirationDate": "2020-01-01T00:00:00Z",
    "Entitlements": {"com.apple.application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
}))
PY
  if out=$(find_mac_store_profile "$prof_dir" "$APP_BUNDLE_ID" "J893F72P4R" "$fixed_now"); then
    echo "SELF-CHECK FAIL: expired OSX profile was accepted: $out"; return 1
  fi
  [[ "$out" == *PROFILE_EXPIRED* ]] || { echo "SELF-CHECK FAIL: expected PROFILE_EXPIRED, got $out"; return 1; }

  # 4d: Valid OSX Store profile -> accepted
  python3 - "$prof_dir/04-valid.provisionprofile" <<'PY'
import plistlib, sys
open(sys.argv[1], "wb").write(plistlib.dumps({
    "Name": "BainLuck Mac AppStore",
    "Platform": ["OSX"],
    "ExpirationDate": "2027-09-11T00:19:37Z",
    "Entitlements": {"com.apple.application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
}))
PY
  out=$(find_mac_store_profile "$prof_dir" "$APP_BUNDLE_ID" "J893F72P4R" "$fixed_now") || {
    echo "SELF-CHECK FAIL: valid OSX Store profile was rejected: $out"; return 1
  }
  [[ "$out" == "PROFILE_OK|BainLuck Mac AppStore|2027-09-11T00:19:37Z" ]] || {
    echo "SELF-CHECK FAIL: unexpected valid profile output: $out"; return 1
  }

  # 4e: Keychain identity classification (missing Mac Installer cert fails export/upload, warns archive)
  export MOCK_SECURITY_CS_FILE="$tmp_root/sec_cs.txt"
  export MOCK_SECURITY_ALL_FILE="$tmp_root/sec_all.txt"
  echo '  1) ABCD "Apple Distribution: Alex Bain (J893F72P4R)"' > "$MOCK_SECURITY_CS_FILE"
  echo '  1) ABCD "Apple Distribution: Alex Bain (J893F72P4R)"' > "$MOCK_SECURITY_ALL_FILE"

  if out=$(check_mac_signing_identities "export"); then
    echo "SELF-CHECK FAIL: missing Mac Installer cert was accepted in export mode: $out"; return 1
  fi
  [[ "$out" == *MISSING_MAC_INSTALLER_CERT* ]] || { echo "SELF-CHECK FAIL: expected MISSING_MAC_INSTALLER_CERT, got $out"; return 1; }

  out=$(check_mac_signing_identities "archive") || {
    echo "SELF-CHECK FAIL: archive mode should permit missing Mac Installer cert with warning: $out"; return 1
  }
  [[ "$out" == *INSTALLER_CERT_WARN_ARCHIVE_ONLY* ]] || { echo "SELF-CHECK FAIL: expected INSTALLER_CERT_WARN_ARCHIVE_ONLY, got $out"; return 1; }

  echo '  2) EF01 "3rd Party Mac Developer Installer: Alex Bain (J893F72P4R)"' >> "$MOCK_SECURITY_ALL_FILE"
  out=$(check_mac_signing_identities "export") || {
    echo "SELF-CHECK FAIL: valid Apple Distribution + Mac Installer cert rejected: $out"; return 1
  }
  [[ "$out" == *IDENTITIES_OK* ]] || { echo "SELF-CHECK FAIL: expected IDENTITIES_OK, got $out"; return 1; }

  # 4f: ExportOptions-MacAppStore.plist verification
  local exp_opt_bad="$tmp_root/ExportBad.plist"
  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"method": "release-testing", "manageAppVersionAndBuildNumber": False, "teamID": "J893F72P4R"}))' "$exp_opt_bad"
  if out=$(check_export_options_plist "$exp_opt_bad" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID"); then
    echo "SELF-CHECK FAIL: wrong ExportOptions method was accepted: $out"; return 1
  fi
  [[ "$out" == *EXPORT_OPTIONS_WRONG_METHOD* ]] || { echo "SELF-CHECK FAIL: expected EXPORT_OPTIONS_WRONG_METHOD, got $out"; return 1; }

  local exp_opt_good="$tmp_root/ExportGood.plist"
  python3 -c 'import plistlib,sys; open(sys.argv[1],"wb").write(plistlib.dumps({"method": "app-store-connect", "manageAppVersionAndBuildNumber": False, "teamID": "J893F72P4R", "signingStyle": "manual", "provisioningProfiles": {"com.bainluck.Bain-Luck": "BainLuck Mac App AppStore", "com.bainluck.Bain-Luck.BainLuckWidget": "BainLuck Mac Widget AppStore"}}))' "$exp_opt_good"
  out=$(check_export_options_plist "$exp_opt_good" "J893F72P4R" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID") || {
    echo "SELF-CHECK FAIL: valid ExportOptions was rejected: $out"; return 1
  }
  [[ "$out" == *EXPORT_OPTIONS_OK* ]] || { echo "SELF-CHECK FAIL: expected EXPORT_OPTIONS_OK, got $out"; return 1; }

  echo "SELF-CHECK PASS — all 5 production control groups verified (sandbox boolean true/false/missing/malformed, nonzero archive/export exit with partial artifacts, reused archive & pkg platform/bundle/version/team/provenance guards, profile/identity/ExportOptions classification, and valid representative path)"
  return 0
}

if [ "${1:-}" = "--self-check" ]; then
  run_self_check
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
PROFILE_DIR="${NATIVE_PROFILE_DIR:-$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles}"
MARKETING_VERSION="${NATIVE_MAC_MARKETING_VERSION:-1.0.4}"

MODE=""
BUILD_NUMBER=""
REUSE_ARCHIVE=0
EXPECTED_SOURCE_SHA="${NATIVE_MAC_EXPECTED_SOURCE_SHA:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|--preflight)    MODE="dry-run" ;;
    --archive)                MODE="archive" ;;
    --export)                 MODE="export" ;;
    --validate)               MODE="validate" ;;
    --upload)                 MODE="upload" ;;
    --reuse-archive)          REUSE_ARCHIVE=1 ;;
    --allow-stale-tree)       ALLOW_STALE_TREE=1 ;;
    --repo)                   shift ;;
    --build)                  shift; BUILD_NUMBER="${1:-}" ;;
    --marketing-version)      shift; MARKETING_VERSION="${1:-}" ;;
    --expected-source-sha)    shift; EXPECTED_SOURCE_SHA="${1:-}" ;;
    -h|--help)                sed -n '1,45p' "${BASH_SOURCE[0]}"; exit 0 ;;
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

# ─── PREFLIGHT ────────────────────────────────────────────────────────────────
step "preflight (macOS TestFlight)"

if [ ! -d "$PROJECT" ]; then
  echo "FAIL: no project at $PROJECT" >&2
  exit 2
fi
note "project : $PROJECT"

TREE_STALE=""
TREE_UNSURE=""
TREE_SHA=""
TREE_IOS_SHA=""
if ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  note "tree    : $REPO_ROOT  (resolved from $REPO_ROOT_SOURCE) — NOT a git repo"
  TREE_UNSURE="not a git repo"
else
  TREE_BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
  TREE_SHA=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)
  TREE_IOS_SHA=$(git -C "$REPO_ROOT" rev-parse HEAD:ios 2>/dev/null || echo "")
  note "tree    : $REPO_ROOT  (resolved from $REPO_ROOT_SOURCE)"
  note "          $TREE_BRANCH @ ${TREE_SHA:0:10}  (HEAD:ios ${TREE_IOS_SHA:0:10})"

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

# 1 & 2. Signing identities (Apple Distribution + Mac Installer Distribution)
if id_out=$(check_mac_signing_identities "$MODE"); then
  note "identity: ${id_out#*|}"
else
  fail=1
  echo "FAIL: ${id_out#*|}"
  note "macOS App Store Connect export builds a .pkg installer and requires both 'Apple Distribution' and '3rd Party Mac Developer Installer' / 'Mac Installer Distribution'."
fi

# 3. Mac App Store provisioning profiles (.provisionprofile, Platform=OSX, no ProvisionedDevices, unexpired)
for bid in "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID"; do
  if prof_out=$(find_mac_store_profile "$PROFILE_DIR" "$bid" "$TEAM_ID"); then
    rest="${prof_out#PROFILE_OK|}"
    pname="${rest%%|*}"
    pexp="${rest##*|}"
    note "profile : $bid → ${pname} (expires ${pexp})"
  else
    reason="${prof_out#*|}"
    if [ "$MODE" = "archive" ]; then
      note "profile : MISSING/REJECTED Mac App Store (.provisionprofile) for $bid ($reason; archive can run, export/upload cannot)"
    else
      fail=1
      echo "FAIL: no valid Mac App Store distribution profile (.provisionprofile, Platform=OSX) installed for $bid ($reason)"
      note "Create/download MAC_APP_STORE profiles for $APP_BUNDLE_ID and $WIDGET_BUNDLE_ID."
    fi
  fi
done

if exp_opt_out=$(check_export_options_plist "$EXPORT_OPTIONS" "$TEAM_ID" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID"); then
  note "export  : ${exp_opt_out#*|}"
else
  fail=1
  echo "FAIL: ${exp_opt_out#*|}"
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
if [ "$REUSE_ARCHIVE" = "1" ]; then
  step "reusing macOS archive at $ARCHIVE"
else
  step "archiving (Release, generic/platform=macOS, $MARKETING_VERSION ($EFFECTIVE_BUILD)); log: $ARCHIVE_LOG"
  if ! run_archive_step "$PROJECT" "$SCHEME" "$ARCHIVE" "$EFFECTIVE_BUILD" "$MARKETING_VERSION" "$ARCHIVE_LOG" ${SPM_FLAGS[@]+"${SPM_FLAGS[@]}"}; then
    echo; echo "ARCHIVE: FAIL  (log: $ARCHIVE_LOG)"
    if /usr/bin/grep -q "error: " "$ARCHIVE_LOG" 2>/dev/null; then
      /usr/bin/grep "error: " "$ARCHIVE_LOG" | sort -u | head -8 | sed 's/^/    /'
    fi
    exit 1
  fi
  if [ -n "$TREE_SHA" ] && [ -d "$ARCHIVE" ]; then
    write_archive_provenance "$ARCHIVE" "$TREE_SHA" "${TREE_IOS_SHA:-}" "$MARKETING_VERSION" "$EFFECTIVE_BUILD"
  fi
fi

if ! verify_archive_bundle "$ARCHIVE" "$MARKETING_VERSION" "$EFFECTIVE_BUILD" "$TEAM_ID" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID" "$REUSE_ARCHIVE" "$EXPECTED_SOURCE_SHA"; then
  echo; echo "ARCHIVE: FAIL  (log: $ARCHIVE_LOG)"
  exit 1
fi

echo "ARCHIVE: PASS"
[ "$MODE" = "archive" ] && exit 0

# ─── EXPORT ───────────────────────────────────────────────────────────────────
step "exporting macOS App Store .pkg; log: $EXPORT_LOG"
if ! run_export_step "$ARCHIVE" "$EXPORT_OPTIONS" "$EXPORT_DIR" "$EXPORT_LOG"; then
  echo; echo "EXPORT: FAIL  (log: $EXPORT_LOG)"
  /usr/bin/grep -i "error\|Provisioning\|no profile\|certificate\|installer" "$EXPORT_LOG" 2>/dev/null | sort -u | head -10 | sed 's/^/    /'
  exit 1
fi

PKG=$(find "$EXPORT_DIR" -maxdepth 1 -name '*.pkg' 2>/dev/null | head -1)
if ! verify_exported_pkg "$PKG" "$MARKETING_VERSION" "$EFFECTIVE_BUILD" "$TEAM_ID" "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID"; then
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
  itms_rc=$?
  echo "  iTMSTransporter exit: $itms_rc"
  if [ "$itms_rc" -ne 0 ]; then
    echo "FAIL: iTMSTransporter exited $itms_rc during $ITMS_MODE — read $DELIVER_LOG."
    /usr/bin/grep -E "ERROR|error:" "$DELIVER_LOG" 2>/dev/null | tail -8
    exit 1
  fi
  if /usr/bin/grep -qE "(uploaded|verified) successfully" "$DELIVER_LOG" 2>/dev/null; then
    echo "UPLOAD: PASS — macOS build $EFFECTIVE_BUILD delivered."
    note "log: $DELIVER_LOG"
    exit 0
  fi
  echo "FAIL: iTMSTransporter exited 0 but did not report a successful $ITMS_MODE — read $DELIVER_LOG."
  /usr/bin/grep -E "ERROR|error:" "$DELIVER_LOG" 2>/dev/null | tail -8
  exit 1
fi

xcrun altool "$ALTOOL_VERB" \
  -f "$PKG" \
  -t osx \
  --apiKey "$ASC_KEY_ID" \
  --apiIssuer "$ASC_ISSUER_ID" \
  --output-format json > "$DELIVER_LOG" 2>&1
altool_rc=$?
echo "  altool exit: $altool_rc"

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
if [ "$altool_rc" -ne 0 ]; then
  echo "FAIL: altool exited $altool_rc — read $DELIVER_LOG."
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
