# Watch package preflight (#10628, child of #10544)

Pillar: FORMATTING · TRUTH. Ship: an approved TestFlight attempt cannot silently omit or mispackage the embedded Watch app and saved complication.

Native owns the chosen artifact and distribution operations. This standalone tool reads an existing local `.xcarchive` or `.ipa` and supplied entitlement evidence. It never signs, builds, uploads, accesses accounts or reads credentials. The only subprocess is the existing archive inspector's read-only `xcrun vtool -show-build` inspection of executable platforms.

```sh
python3 tools/watch_package_preflight.py --artifact /absolute/Candidate.ipa \
  --entitlements-evidence /absolute/entitlements-evidence.json \
  --output /absolute/package-receipt.json
```

The manifest has `version: 1` and four `applications` records, one for each exact bundle ID: `com.bainluck.Bain-Luck`, `.BainLuckWidget`, `.watchkitapp`, and `.watchkitapp.SavedGlance` (each suffix appended to the phone ID). Each record contains `bundle_id`, `executable_sha256` and an `entitlements` dictionary supplied by Native from that packaged bundle. It requires `application-identifier` and `com.apple.developer.team-identifier`; Watch and SavedGlance must include `group.com.bainluck.watch` in `com.apple.security.application-groups`.

The executable hash binds the supplied record to the inspected executable bytes. **It does not authenticate the entitlement dictionary or validate the code signature.** Do not substitute source `.entitlements` files for actual packaged evidence. Native separately verifies signature validity, distribution profiles and team ownership on its release candidate.

The existing archive checker is reused for phone/Watch/SavedGlance identity, companion, launcher/Handoff registrations, versions and actual binary platforms. This wrapper adds the phone widget and final IPA path. IPA extraction rejects traversal, duplicates, symlinks, special files, encryption and oversized entries (20,000 entries, 512 MiB per entry, 2 GiB expanded total). Only Payload is normalized into temporary storage, deleted on exit. Inputs are untouched; choose receipt output outside the archive and apart from input files.

Exit 0 means `PACKAGE_AND_SUPPLIED_EVIDENCE_CONSISTENT`. Exit 1 means `UNPAID` with a reason. Neither is TestFlight readiness: signature authenticity, provisioning profiles, distribution, Apple processing, source coverage and physical installation remain `UNVERIFIED`. An unsigned artifact without supplied entitlement evidence must fail this preflight; its narrower unsigned archive check remains valid.

Run focused synthetic guards with `python3 -m unittest discover -s tools/tests -p 'test_watch_package_preflight.py'`; run the reused inspector guards separately with `test_watch_companion_archive.py`.
