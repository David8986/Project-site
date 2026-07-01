# FocusGate

FocusGate is a small Android self-control app that gates TikTok, YouTube Shorts, and Instagram Reels behind a friction challenge.

## What it does

- Uses Android Accessibility to watch supported apps locally on the phone.
- Blocks TikTok packages outright.
- Detects likely Shorts/Reels screens from visible UI text.
- Optional full-app mode blocks YouTube and Instagram entirely when partial detection is too easy to slip through.
- Unlocks for 5 minutes only after a 45-second pause, a random task, exact phrase typing, and a written next action.
- Offers optional hardening for Usage Access, battery optimization, and uninstall friction.
- Runs a foreground watchdog that keeps TikTok app-level blocking reliable without forcing Instagram/YouTube app-level blocking by default.

## Challenge variety

The first task rotates across multiple generated challenge types:

- arithmetic with changing numbers
- ascending and descending sequences
- number sorting
- reversed random codes
- letter counting
- first-letter codes from random words
- odd-number sums
- alphabetic word ordering
- digit transformations
- largest-minus-smallest ranges
- total word-length counts

The exact phrase also changes every time with a random code, and the final commitment prompt rotates too.

## Battery impact

FocusGate should not add heavy battery drain. The Accessibility service is event-driven: it reacts when Android reports window or content changes in TikTok, YouTube, or Instagram, and it does not use GPS, network calls, wake locks, or a constant polling loop.

Battery use may rise a little while those apps are actively open because their feeds generate many UI events. In normal phone use, the impact should be low.

## Reliability model

WallHabit 1.3.9 uses a heavier Android setup: Accessibility, Usage Access, overlay permission, foreground service, boot receiver, battery-optimization exemption, and device-admin support.

FocusGate now mirrors the safer parts of that model:

- Accessibility listens to all event types from the target apps only.
- A foreground watchdog uses Usage Access to detect target apps even when Accessibility events are missed.
- TikTok is blocked at the app level.
- Instagram and YouTube stay usable by default; Reels and Shorts are blocked only when screen signals are detected.
- Videos opened from common messaging apps or Instagram Direct get a short shared-video allowance.
- Full-app blocking for YouTube and Instagram is available as an optional switch.
- Battery-unrestricted settings are exposed from the app setup screen.
- A boot receiver clears any old unlock window after reboot or app update.
- Optional device-admin mode adds an extra settings step before uninstalling FocusGate.

FocusGate intentionally does not request location, Bluetooth, internet, billing, ads, or broad package-query permissions.

## Build and install

1. Open this `FocusGate` folder in Android Studio.
2. Let Gradle sync.
3. Run the `app` configuration on your Android phone.
4. Open FocusGate on the phone.
5. Tap `Enable Accessibility service`.
6. In Android Settings, enable `FocusGate blocker`.
7. Return to FocusGate and use `Test the challenge`.

## Limits

Android does not let a normal app reliably block only one feature inside another app. FocusGate uses Accessibility as the practical route:

- TikTok can be blocked by package name.
- Shorts/Reels are best-effort detections based on visible screen text.
- You can bypass FocusGate by disabling its Accessibility service. If uninstall friction is off, uninstalling also bypasses it.

For stronger blocking, use full-app blocking, app pinning/family controls, or a managed/device-owner setup.
