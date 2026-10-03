# First physical Watch trial (#4932)

PILLARS: TRUTH / FORMATTING.
SHIP: choose and reopen one honestly aged game on Alex's physical Watch.

The code remains watch-only for this development trial. The shared `BainLuckWatch`
scheme runs the Watch app directly; companion embedding is later work after
1.0.3. Source settings are automatic signing with an inherited development team,
watchOS minimum 26.0, and `WKWatchOnly=YES`. These settings do not prove account
access, device registration, provisioning, or an installable signed build.

As of October 3, a read-only device listing recognizes the Ultra 3 but reports it
unavailable. The earlier dedicated Watch simulator is now listed as shutdown;
this is an observed state, not a claim that this thread performed cleanup.

## First small step group, when Alex returns

No user action is needed for ongoing code/hosted-CI work. Wait for a safe Xcode
resource slot before opening the project for the trial.

1. Open this branch's `ios/Bain Luck/Bain Luck.xcodeproj` in Xcode. Choose
   **BainLuckWatch** in the toolbar's scheme menu. A scheme tells Xcode which app
   to build and run.
2. Inspect the adjacent run-destination menu for the physical Ultra 3 or Ultra 2.
   If it is unavailable, open **Manage Devices…** (Device Hub), select the Watch
   and read the status. Do not change a signing or security setting yet.
3. If the Watch is available, inspect the Watch app target's **Signing &
   Capabilities** status. Report the exact warning, if any. Do not click Run or
   Set Up Signing until we have checked what account/device changes it needs.

Success for this group is an available Watch destination plus a known signing
status. It is not installation. If the UI differs, use Xcode > Open Developer
Tool > Device Hub and inspect the device's status there. We will give the next
small group based on that result, rather than guessing which gate is missing.

Apple currently documents that pairing a Watch requires Developer Mode on both
its companion iPhone and the Watch, and may require trust confirmation. Enabling
Developer Mode changes device security; ask Alex explicitly before that step.
Development registration/provisioning may also be created by automatic signing;
inspect and obtain approval before account changes. No credentials go in chat.

## What the trial must eventually prove

After approved installation, use actual taps to choose a named game, verify its
canonical event against the phone/API, reopen it, test unavailable connectivity,
and inspect live/final/closed states and large text/VoiceOver. Record exact build,
device/OS and producer observation times. Store tests and seeded screenshots do
not pay these gates. Phone continuation, TestFlight and distribution packaging
remain separate later gates in #4929/#4932.

## Apple references checked October 3, 2026

- [Running your app on simulated or physical devices](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices)
- [Managing devices in Device Hub](https://developer.apple.com/documentation/xcode/managing-your-simulated-and-physical-devices-in-device-hub)
- [Enabling Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)

Recheck these instructions and actual account/device status when the trial begins.
