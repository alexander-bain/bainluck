#!/bin/bash
# Archive, grade, export and deliver this workflow's exact source commit.
set -euo pipefail

RELEASE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_PROJECT="$RELEASE_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
RELEASE_OUT="$RUNNER_TEMP/testflight-output"
RELEASE_ARCHIVE="$RUNNER_TEMP/TestFlight.xcarchive"
RELEASE_EXPORT="$RUNNER_TEMP/testflight-export"
mkdir -p "$RELEASE_OUT"
: "${TESTFLIGHT_BUILD:?missing allocated build number}"
: "${TESTFLIGHT_VERSION:?missing marketing version}"
: "${ASC_KEY_ID:?missing API key ID}"
: "${ASC_ISSUER_ID:?missing API issuer ID}"
: "${TESTFLIGHT_KEYCHAIN:?missing distribution keychain}"

# The locked Package.resolved is authoritative. Resolving here supplies the
# fresh hosted runner with the binary dependencies the archive needs.
xcodebuild -resolvePackageDependencies -project "$RELEASE_PROJECT" -scheme 'Bain Luck' \
  -clonedSourcePackagesDirPath "$RUNNER_TEMP/testflight-spm" \
  -onlyUsePackageVersionsFromResolvedFile > "$RELEASE_OUT/packages.log" 2>&1

set +e
xcodebuild -project "$RELEASE_PROJECT" -scheme 'Bain Luck' -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$RELEASE_ARCHIVE" \
  -clonedSourcePackagesDirPath "$RUNNER_TEMP/testflight-spm" -disableAutomaticPackageResolution \
  CURRENT_PROJECT_VERSION="$TESTFLIGHT_BUILD" MARKETING_VERSION="$TESTFLIGHT_VERSION" \
  CODE_SIGN_STYLE=Automatic CODE_SIGN_IDENTITY='Apple Distribution' DEVELOPMENT_TEAM=J893F72P4R \
  OTHER_CODE_SIGN_FLAGS="--keychain $TESTFLIGHT_KEYCHAIN" \
  OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
  archive > "$RELEASE_OUT/archive.log" 2>&1
RELEASE_ARCHIVE_EXIT=$?
set -e
printf 'Archive command exit: %s\n' "$RELEASE_ARCHIVE_EXIT"
if [ "$RELEASE_ARCHIVE_EXIT" -ne 0 ]; then exit "$RELEASE_ARCHIVE_EXIT"; fi
# Existing native tooling has seen a zero exit with no actual archive.
if grep -q 'Stack dump' "$RELEASE_OUT/archive.log"; then
  echo 'Swift compiler crashed during archive'; exit 1
fi
RELEASE_APP="$(python3 "$RELEASE_ROOT/tools/testflight/release.py" bundles \
  --root "$RELEASE_ARCHIVE/Products/Applications" --version "$TESTFLIGHT_VERSION" --build "$TESTFLIGHT_BUILD")"
codesign --verify --deep --strict "$RELEASE_APP"

xcodebuild -exportArchive -archivePath "$RELEASE_ARCHIVE" \
  -exportOptionsPlist "$RELEASE_ROOT/ios/ExportOptions-AppStore.plist" \
  -exportPath "$RELEASE_EXPORT" > "$RELEASE_OUT/export.log" 2>&1
RELEASE_IPAS=("$RELEASE_EXPORT"/*.ipa)
if [ "${#RELEASE_IPAS[@]}" -ne 1 ] || [ ! -f "${RELEASE_IPAS[0]}" ]; then
  echo 'Export did not produce exactly one IPA'; exit 1
fi
RELEASE_IPA="${RELEASE_IPAS[0]}"
if [ "$(stat -f %z "$RELEASE_IPA")" -lt 1000000 ]; then
  echo 'Exported IPA is too small to contain the app'; exit 1
fi
mkdir "$RUNNER_TEMP/testflight-payload"
unzip -q "$RELEASE_IPA" -d "$RUNNER_TEMP/testflight-payload"
RELEASE_EXPORTED_APP="$(python3 "$RELEASE_ROOT/tools/testflight/release.py" bundles \
  --root "$RUNNER_TEMP/testflight-payload/Payload" --version "$TESTFLIGHT_VERSION" --build "$TESTFLIGHT_BUILD")"
codesign --verify --deep --strict "$RELEASE_EXPORTED_APP"
cp "$RELEASE_IPA" "$RELEASE_OUT/BainLuck-$TESTFLIGHT_VERSION-$TESTFLIGHT_BUILD.ipa"

xcrun altool --upload-app -f "$RELEASE_IPA" -t ios \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" \
  --output-format json > "$RELEASE_OUT/delivery.json" 2>&1
python3 "$RELEASE_ROOT/tools/testflight/release.py" delivery --log "$RELEASE_OUT/delivery.json"
python3 "$RELEASE_ROOT/tools/testflight/release.py" confirm --version "$TESTFLIGHT_VERSION" \
  --build "$TESTFLIGHT_BUILD" --source "$GITHUB_SHA" --receipt "$RELEASE_OUT/receipt.json"
