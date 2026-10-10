# Validation of the 0.8.0 changes

## Automated

All 87 local tests pass. The existing suite plus device-profile regression tests cover legacy configuration round trips, bounded profile settings, independent decks, duplicate model detection, focus rules, page deletion, touch event dispatch and native image output, profile reset, controller update detection, selected-page previews and privacy-safe diagnostics. Local HTTP simulations continue exercising the existing security protections.

All new QML components and the main panel parse with Qt’s QML formatter. A separate Quickshell instance loads the panel against the installed Omarchy UI modules without QML errors. The desktop portal emits a duplicate application-registration warning for this temporary second shell instance; the panel still loads.

## Local device

The installed worker opens the attached Stream Deck MK.2 and reports 15 keys. USB access and required dependency versions are available. The existing app icons and empty-key backgrounds appear in the panel. Installing the changes preserves the configuration file byte for byte. These checks confirm device opening and rendering, not a manual press of every physical key.

Touch hardware, two simultaneous physical decks, lights, cameras, audio and Prompter are unavailable for physical validation. Their automated checks must not be described as real-device tests. Owners can follow [the hardware checklist](hardware-testing.md).

## State performance

Run `python scripts/benchmark-state.py` in the installed Python environment. The reproducible fixture has 16 pages with 15 empty keys, warmed caches and mocked hardware probes. Five measured repetitions after warmup produced:

| Path | Median function time | Response size |
| --- | --- | --- |
| All pages | 3.83 ms | 43,998 bytes |
| Selected page | 2.17 ms | 14,156 bytes |
| Quick status | 1.84 ms | 9,594 bytes |

These measurements exclude interpreter startup and real hardware delays and depend on the host. The behavioral tests verify the useful guarantees: quick status performs no preview rendering or hardware probes, local edits render only the selected page, and full hardware probes occur separately every thirty seconds. A complete probe already in progress can still delay a queued edit until its bounded requests finish.

## Publication

The implementation issue is [#1](https://github.com/JustVicinity/omagato/issues/1). The GitHub release is published only after the exact commit passes the configured CI checks. Marketplace promotion requires its own exact-commit validation and maintainer approval; GitHub publication alone does not update the verified marketplace snapshot.
