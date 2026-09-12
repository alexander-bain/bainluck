#!/bin/bash
# native — the unattended TestFlight path: archive → export → upload, no Xcode UI.
#
# WHY THIS EXISTS
# ---------------
# Build 7 reached TestFlight by a person driving Xcode. Everything the app has
# shipped since — the phone writing swipe/share/open rows among it — is invisible
# to Alex's phone until a build 8 exists, and nothing in this repo could make one.
# `tools/native-release-check.sh` proves the app can be ARCHIVED; it stops there.
# This carries the archive the remaining two steps.
#
# WHAT IS AND IS NOT AUTOMATED
#   archive  — no credential needed.
#   export   — no credential needed either. The two App Store distribution
#              profiles ("iOS Team Store Provisioning Profile" for the app and
#              for the widget) are installed on this machine and automatic
#              signing picks them up, so a real signed .ipa is produced offline.
#   upload   — needs an App Store Connect API key, which is Alex's to mint. The
#              script takes it from the environment and never writes it anywhere
#              tracked (standing credential rule). Absent the key the script
#              stops AT the upload step having already produced the .ipa, and
#              says so in one line.
#
# THE TRAP THIS IS BUILT AROUND (gotcha #124, inherited from native-release-check)
# ------------------------------------------------------------------------------
# `xcodebuild archive` has exited 0 with no archive on disk, in this very repo.
# So no step here is graded on `$?`: every one grades its ARTIFACT — the archive
# directory, the .app inside it, the .ipa's size and its Payload — and reads the
# exit code only as one more fact to print. Same for `altool`, whose JSON carries
# `product-errors` on a delivery that exits 0.
#
# THE SECOND TRAP: A BUILD NUMBER THAT IS NOT THE ONE YOU GRADED
# --------------------------------------------------------------
# Xcode's export step renumbers builds by default (manageAppVersionAndBuildNumber).
# The export options file turns that off and this script reads CFBundleVersion
# back OUT of the exported .ipa, so the number it reports is the number App Store
# Connect will receive, not the number we asked for.
#
# USAGE
#   tools/native-upload.sh --dry-run            # preflight only; runs no build
#   tools/native-upload.sh --archive --build 8
#   tools/native-upload.sh --export  --build 8  # archive + .ipa  (no credential)
#   tools/native-upload.sh --validate --build 8 # + App Store validation (key)
#   tools/native-upload.sh --upload  --build 8  # + TestFlight delivery   (key)
#   tools/native-upload.sh --export --reuse-archive
#
# CREDENTIALS (upload/validate only; never committed, never printed)
#   ASC_KEY_ID     App Store Connect API key id       (e.g. ABCD123456)
#   ASC_ISSUER_ID  the issuer uuid from the same page
#   ASC_KEY_PATH   path to the downloaded AuthKey_<ASC_KEY_ID>.p8
#
# EXIT
#   0  every step attempted produced a graded artifact
#   1  a step ran and its artifact is wrong or missing
#   2  the rig itself is unusable (no project, bad arguments, missing credential
#      for a mode that needs one) — nothing was built
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$REPO_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
PBXPROJ="$PROJECT/project.pbxproj"
EXPORT_OPTIONS="${NATIVE_EXPORT_OPTIONS:-$REPO_ROOT/ios/ExportOptions-AppStore.plist}"
LOG_DIR="${NATIVE_UPLOAD_LOG_DIR:-/tmp}"
ARCHIVE="${NATIVE_UPLOAD_ARCHIVE:-/tmp/BainLuck-appstore.xcarchive}"
EXPORT_DIR="${NATIVE_UPLOAD_EXPORT_DIR:-/tmp/BainLuck-appstore-export}"
ARCHIVE_LOG="$LOG_DIR/native-upload-archive.txt"
EXPORT_LOG="$LOG_DIR/native-upload-export.txt"
DELIVER_LOG="$LOG_DIR/native-upload-deliver.txt"
SCHEME="${NATIVE_UPLOAD_SCHEME:-Bain Luck}"
APP_BUNDLE_ID="com.bainluck.Bain-Luck"
WIDGET_BUNDLE_ID="com.bainluck.Bain-Luck.BainLuckWidget"
PROFILE_DIR="${NATIVE_PROFILE_DIR:-$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles}"

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
    --build)               shift; BUILD_NUMBER="${1:-}" ;;
    -h|--help)             sed -n '1,60p' "${BASH_SOURCE[0]}"; exit 0 ;;
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
# Everything checkable before a five-minute archive is checked before it. An
# export that dies on a missing distribution profile after the build is the same
# failure as one that dies before it, minus five minutes and a clear sentence.
step "preflight"

if [ ! -d "$PROJECT" ]; then
  echo "FAIL: no project at $PROJECT" >&2
  exit 2
fi
note "project : $PROJECT"

# The build number. --build is the authority; the project file is only consulted
# so a --dry-run on a machine with no argument still prints a concrete plan.
#
# That fallback is the HIGHEST CURRENT_PROJECT_VERSION in the file, not the app
# target's — the project holds two (the app's and the watch app's) and picking
# the right one means parsing pbxproj in bash, which is how a rig starts lying.
# It is labelled as the guess it is, and the two modes where being wrong costs
# something real (App Store Connect refuses a build number it has already seen,
# after the upload) refuse to run without an explicit --build.
PROJECT_BUILD=$(/usr/bin/grep -o 'CURRENT_PROJECT_VERSION = [0-9]*' "$PBXPROJ" 2>/dev/null \
  | /usr/bin/awk '{print $3}' | sort -rn | head -1)
PROJECT_BUILD=${PROJECT_BUILD:-?}
EFFECTIVE_BUILD="${BUILD_NUMBER:-$PROJECT_BUILD}"
if [ -n "$BUILD_NUMBER" ]; then
  note "build   : $EFFECTIVE_BUILD (--build)"
else
  note "build   : $EFFECTIVE_BUILD (highest in the project file — a guess)"
fi

# Signing identity. `security find-identity` lists an identity per line; the
# name is what matters, not the count, because a machine with a Development
# identity and no Distribution one passes any count-based test.
if security find-identity -v -p codesigning 2>/dev/null | /usr/bin/grep -q "Apple Distribution"; then
  note "identity: Apple Distribution present"
else
  fail=1
  echo "FAIL: no 'Apple Distribution' code-signing identity in the keychain."
  note "An App Store export cannot be signed with a Development identity."
fi

# The two App Store distribution profiles. A Store profile is the one with no
# ProvisionedDevices array — that absence IS the distinction from a Team
# (development) profile of the same bundle id, and both are installed here, so
# matching on the bundle id alone would find the wrong one and say PASS.
store_profile_for() {
  local want="$1" f name appid expiry
  for f in "$PROFILE_DIR"/*.mobileprovision; do
    [ -e "$f" ] || continue
    local xml
    xml=$(security cms -D -i "$f" 2>/dev/null) || continue
    case "$xml" in *"<key>ProvisionedDevices</key>"*) continue ;; esac
    appid=$(echo "$xml" | /usr/bin/plutil -extract Entitlements.application-identifier raw -o - - 2>/dev/null)
    [ "$appid" = "J893F72P4R.$want" ] || continue
    name=$(echo "$xml" | /usr/bin/plutil -extract Name raw -o - - 2>/dev/null)
    expiry=$(echo "$xml" | /usr/bin/plutil -extract ExpirationDate raw -o - - 2>/dev/null)
    echo "$name|$expiry"
    return 0
  done
  return 1
}

for bid in "$APP_BUNDLE_ID" "$WIDGET_BUNDLE_ID"; do
  if found=$(store_profile_for "$bid"); then
    pname=${found%%|*}
    pexp=${found##*|}
    note "profile : $bid → ${pname} (expires ${pexp})"
    # An expired profile is not a missing one: Xcode will refuse the export with
    # a message about signing, which reads like a certificate problem.
    # `plutil -extract … raw` prints a date as ISO 8601 (2027-09-11T00:19:37Z).
    # The first draft parsed `%Y-%m-%d %H:%M:%S +0000`, which never matches — so
    # `date` returned nothing, the comparison was skipped, and an expired profile
    # passed. A parse that cannot read its input must SAY so, not fall through
    # quietly into the healthy branch: that is the difference between "nothing to
    # report" and "I could not tell".
    exp_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$pexp" +%s 2>/dev/null)
    now_epoch=$(date +%s)
    if [ -z "$exp_epoch" ]; then
      fail=1
      echo "FAIL: could not read that profile's expiry date ('$pexp')."
      note "Unparsed, an expired profile would pass this check."
    elif [ "$exp_epoch" -lt "$now_epoch" ] 2>/dev/null; then
      fail=1
      echo "FAIL: that distribution profile EXPIRED on $pexp."
    fi
  else
    fail=1
    echo "FAIL: no App Store distribution profile installed for $bid"
    note "Xcode → Settings → Accounts → Download Manual Profiles, or supply an"
    note "ASC key and the export step can fetch one with -allowProvisioningUpdates."
  fi
done

# Export options. `plutil -lint` catches the malformed file; the method check
# catches the well-formed file that exports the wrong KIND of build — a
# release-testing export uploads to nothing and looks identical until it fails.
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
    if [ "$method" != "app-store-connect" ] && [ "$method" != "app-store" ]; then
      fail=1
      echo "FAIL: export method '$method' does not produce an App Store build."
    fi
    if [ "$manage" = "true" ] || [ "$manage" = "1" ]; then
      fail=1
      echo "FAIL: manageAppVersionAndBuildNumber is on — Xcode would renumber the"
      note "build during export and the number we graded is not the number shipped."
    fi
  fi
fi

# Credentials. REPORTED in every mode, REQUIRED only by the two that talk to
# Apple. Never echoed: the id is a secret's neighbour, and standing rule says a
# session holding one writes it nowhere.
CREDS_OK=1
for v in ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_PATH; do
  if [ -z "${!v:-}" ]; then CREDS_OK=0; fi
done
if [ "$CREDS_OK" = "1" ] && [ ! -f "${ASC_KEY_PATH:-}" ]; then
  CREDS_OK=0
  note "key file: ASC_KEY_PATH is set but names no file"
fi
if [ "$CREDS_OK" = "1" ]; then
  note "asc key : present (id ending ${ASC_KEY_ID: -4})"
else
  note "asc key : ABSENT — archive and export still run; upload does not"
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "PREFLIGHT: FAIL — nothing was built."
  exit 2
fi

case "$MODE" in
  validate|upload)
    if [ -z "$BUILD_NUMBER" ]; then
      echo
      echo "PREFLIGHT: FAIL — --$MODE needs an explicit --build N."
      note "App Store Connect refuses a build number it has already accepted, and"
      note "it refuses it AFTER the upload. Name the number rather than inherit a"
      note "guess from the project file (currently $PROJECT_BUILD)."
      exit 2
    fi
    if [ "$CREDS_OK" != "1" ]; then
      echo
      echo "PREFLIGHT: FAIL — --$MODE needs ASC_KEY_ID, ASC_ISSUER_ID and ASC_KEY_PATH."
      note "Mint the key at App Store Connect → Users and Access → Integrations →"
      note "App Store Connect API, role App Manager, and export the three values."
      note "Run --export meanwhile: the .ipa is produced without any credential."
      exit 2
    fi
    ;;
esac

echo
echo "PREFLIGHT: PASS"

if [ "$MODE" = "dry-run" ]; then
  echo
  echo "would run, in order:"
  echo "  xcodebuild -project '<repo>/ios/Bain Luck/Bain Luck.xcodeproj' -scheme '$SCHEME' \\"
  echo "    -destination 'generic/platform=iOS' -archivePath '$ARCHIVE' \\"
  echo "    -disableAutomaticPackageResolution CURRENT_PROJECT_VERSION=$EFFECTIVE_BUILD \\"
  echo "    OTHER_SWIFT_FLAGS='\$(inherited) -Xfrontend -disable-sandbox' archive"
  echo "  xcodebuild -exportArchive -archivePath '$ARCHIVE' \\"
  echo "    -exportOptionsPlist '$EXPORT_OPTIONS' -exportPath '$EXPORT_DIR'"
  echo "  xcrun altool --upload-app -f '$EXPORT_DIR/<app>.ipa' -t ios \\"
  echo "    --apiKey \"\$ASC_KEY_ID\" --apiIssuer \"\$ASC_ISSUER_ID\" --output-format json"
  echo
  echo "DRY RUN: PASS  (no build ran)"
  exit 0
fi

# ─── ARCHIVE ──────────────────────────────────────────────────────────────────
APP=""
if [ "$REUSE_ARCHIVE" = "1" ]; then
  step "reusing archive at $ARCHIVE"
else
  step "archiving (Release, generic/platform=iOS, build $EFFECTIVE_BUILD); log: $ARCHIVE_LOG"
  rm -rf "$ARCHIVE"
  # OTHER_SWIFT_FLAGS is NOT optional (gotcha #50): the widget's #Preview macro
  # cannot expand inside the compiler sandbox headlessly.
  # CURRENT_PROJECT_VERSION on the command line reaches EVERY target, which is
  # what we want — App Store Connect rejects a widget whose CFBundleVersion does
  # not match its host app's.
  xcodebuild \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination 'generic/platform=iOS' \
    -archivePath "$ARCHIVE" \
    -disableAutomaticPackageResolution \
    CURRENT_PROJECT_VERSION="$EFFECTIVE_BUILD" \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    archive > "$ARCHIVE_LOG" 2>&1
  echo "  xcodebuild archive exit: $?  (a fact, not the verdict)"
fi

DUMPS=$(/usr/bin/grep -c "Stack dump" "$ARCHIVE_LOG" 2>/dev/null)
DUMPS=${DUMPS:-0}
if [ "$DUMPS" -gt 0 ] 2>/dev/null; then
  fail=1
  echo "FAIL: $DUMPS swift-frontend crash(es) — the optimizer died at -O."
  /usr/bin/grep -n "While running pass\| for 'deinit'" "$ARCHIVE_LOG" | head -6 | sed 's/^/    /'
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
    a_ver=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Info.plist" 2>/dev/null || echo "?")
    a_build=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$APP/Info.plist" 2>/dev/null || echo "?")
    note "archived: $(basename "$APP")  $a_ver ($a_build)"
    if [ "$a_build" != "$EFFECTIVE_BUILD" ]; then
      fail=1
      echo "FAIL: archive carries build $a_build, not the $EFFECTIVE_BUILD asked for."
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
step "exporting App Store .ipa; log: $EXPORT_LOG"
rm -rf "$EXPORT_DIR"
xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportOptionsPlist "$EXPORT_OPTIONS" \
  -exportPath "$EXPORT_DIR" > "$EXPORT_LOG" 2>&1
echo "  xcodebuild -exportArchive exit: $?  (a fact, not the verdict)"

IPA=$(find "$EXPORT_DIR" -maxdepth 1 -name '*.ipa' 2>/dev/null | head -1)
if [ -z "$IPA" ]; then
  fail=1
  echo "FAIL: no .ipa in $EXPORT_DIR"
  /usr/bin/grep -i "error\|Provisioning\|no profile" "$EXPORT_LOG" | sort -u | head -8 | sed 's/^/    /'
else
  # Size and payload, because an .ipa can exist and be a shell: a zip with no
  # Payload/*.app is what a partially-signed export leaves behind.
  bytes=$(/usr/bin/stat -f %z "$IPA" 2>/dev/null || echo 0)
  if [ "$bytes" -lt 1000000 ] 2>/dev/null; then
    fail=1
    echo "FAIL: $IPA is only $bytes bytes — that is not an app."
  fi
  # NOT `unzip -l … | grep -q` (gotcha #54, "never pipe a gate", in its nastiest
  # form): `grep -q` exits at the FIRST match, unzip takes SIGPIPE, and under
  # `set -o pipefail` the pipeline reports failure — so the check fails on
  # exactly the archives that pass it. Measured here on the first real export:
  # a correct 12 MB .ipa with 189 matching entries was reported as containing no
  # Payload. Read the listing once, then match the string.
  ipa_listing=$(/usr/bin/unzip -l "$IPA" 2>/dev/null)
  case "$ipa_listing" in
    *"Payload/"*".app/"*) ;;
    *) fail=1; echo "FAIL: $IPA contains no Payload/*.app" ;;
  esac
  # The number that will actually reach App Store Connect, read back out of the
  # exported artifact rather than assumed from what we passed in.
  tmp_ipa_dir=$(mktemp -d)
  /usr/bin/unzip -qq -o "$IPA" 'Payload/*/Info.plist' -d "$tmp_ipa_dir" 2>/dev/null
  ipa_plist=$(find "$tmp_ipa_dir/Payload" -maxdepth 2 -name Info.plist 2>/dev/null | head -1)
  if [ -n "$ipa_plist" ]; then
    i_ver=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$ipa_plist" 2>/dev/null || echo "?")
    i_build=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$ipa_plist" 2>/dev/null || echo "?")
    note "ipa     : $(basename "$IPA")  $i_ver ($i_build)  $((bytes / 1024 / 1024)) MB"
    if [ "$i_build" != "$EFFECTIVE_BUILD" ]; then
      fail=1
      echo "FAIL: the .ipa carries build $i_build, not $EFFECTIVE_BUILD — export renumbered it."
    fi
  fi
  rm -rf "$tmp_ipa_dir"
fi

if [ "$fail" -ne 0 ]; then
  echo; echo "EXPORT: FAIL  (log: $EXPORT_LOG)"
  exit 1
fi
echo "EXPORT: PASS"
echo "  $IPA"

if [ "$MODE" = "export" ]; then
  echo
  echo "Stopped before delivery, as asked. To send this exact file:"
  echo "  tools/native-upload.sh --upload --reuse-archive --build $EFFECTIVE_BUILD"
  exit 0
fi

# ─── DELIVER ──────────────────────────────────────────────────────────────────
# altool looks for the .p8 in a fixed set of directories and takes only the key
# ID on the command line, so the file is staged (0600) rather than passed. It is
# copied to a directory altool searches; it is never copied into the repo.
KEY_HOME="$HOME/.appstoreconnect/private_keys"
mkdir -p "$KEY_HOME"
chmod 700 "$KEY_HOME"
STAGED_KEY="$KEY_HOME/AuthKey_${ASC_KEY_ID}.p8"
if [ ! -f "$STAGED_KEY" ]; then
  cp "$ASC_KEY_PATH" "$STAGED_KEY"
  chmod 600 "$STAGED_KEY"
fi

if [ "$MODE" = "validate" ]; then
  step "validating with App Store Connect; log: $DELIVER_LOG"
  ALTOOL_VERB="--validate-app"
else
  step "uploading to App Store Connect (TestFlight); log: $DELIVER_LOG"
  ALTOOL_VERB="--upload-app"
fi

xcrun altool "$ALTOOL_VERB" \
  -f "$IPA" \
  -t ios \
  --apiKey "$ASC_KEY_ID" \
  --apiIssuer "$ASC_ISSUER_ID" \
  --output-format json > "$DELIVER_LOG" 2>&1
echo "  altool exit: $?  (a fact, not the verdict)"

# altool has exited 0 on a delivery whose JSON carries product-errors, which is
# the same shape of lie as the archive that exits 0 with no archive. Grade the
# document: an error array with anything in it is a failure whatever the code,
# and a document with neither an error array nor a success message is a failure
# too — "it returned" is not "it worked" (gotcha #53).
if [ ! -s "$DELIVER_LOG" ]; then
  echo "FAIL: altool wrote nothing at all."
  exit 1
fi
if /usr/bin/grep -q '"product-errors"' "$DELIVER_LOG"; then
  echo "FAIL: App Store Connect rejected it."
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
if ! /usr/bin/grep -qi "success\|No errors" "$DELIVER_LOG"; then
  echo "FAIL: altool reported neither an error nor a success — read $DELIVER_LOG."
  exit 1
fi

echo
if [ "$MODE" = "validate" ]; then
  echo "VALIDATE: PASS — build $EFFECTIVE_BUILD would be accepted."
else
  echo "UPLOAD: PASS — build $EFFECTIVE_BUILD delivered."
  note "Processing takes ~10 minutes before it appears in TestFlight."
fi
note "log: $DELIVER_LOG"
exit 0
