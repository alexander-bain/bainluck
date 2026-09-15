# native-175 — captured, but not attributable to a named build. Superseded by native-176.

These 33 frames (`relA-firstlaunch-*`, `relB-coldrelaunch-*`, 2026-09-15 07:43–07:45 PDT) were taken
by a session that ended before it wrote a reading. A later session (native/176) tried to attribute
them and could not:

- the app installed in the simulator at 07:35 has Mach-O UUIDs
  `D73D377D-…` (x86_64) / `88EEC4D0-…` (arm64) and is 68 424 088 bytes;
- the only `Release-iphonesimulator` product in DerivedData at that time was
  `392687F7-…` / `1B6B639B-…`, 68 610 608 bytes;
- no other `Bain Luck.app` anywhere under DerivedData is newer than 07:10.

So the binary those frames photograph is a Release-shaped build that no longer exists on disk, and
no commit can be named for it. **They are therefore not used as evidence for anything.** The
measurement was re-run on a build with a stated UUID and commit — see
`artifacts/native-176/RECEIPT-6343-acceptance-and-1459-release-startup.md`.

Kept rather than deleted because one thing in them is real and reproduced in 176: the system
notification alert sitting over a first launch (§4 of that receipt). Everything else — in
particular the ~11.5 s to first card in `relA` — is unattributed and should not be quoted.
