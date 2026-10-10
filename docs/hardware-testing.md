# Hardware testing

Only a Stream Deck MK.2 is available to the maintainer. Simulated tests cover other integrations and multi-device behavior; they cannot confirm firmware or physical USB/display behavior.

## Owner checklist

1. Record the model, firmware (if known), Omarchy version and OmaGato version.
2. Open Devices. Confirm the model and readiness status. A detected-only device must not offer controls.
3. For a deck, assign an app, a system action, a page action and a custom icon. Check the physical keys, labels, brightness and reconnect behavior.
4. With two decks, edit each independently, switch one page, reconnect and swap USB ports. Confirm that saved settings follow the deck when its driver exposes a serial.
5. If dials/touch are present, check each dial, tap, hold and swipe. Confirm a busy action does not freeze USB input.
6. Link a page to an app, focus that app, then another. Check that only decks with rules switch pages.
7. For lights/cameras/audio/Prompter, exercise only controls shown as available. Report the exact control and observed result rather than assuming a whole model is verified.
8. Check the panel at your display resolution and scaling, including setup messages, long app names and scrolling.

Attach the output of `bin/elgatoctl diagnostics` to a [GitHub issue](https://github.com/JustVicinity/omagato/issues). The generated summary excludes serials, personal paths, actions and errors. Review any extra screenshots or logs yourself before sharing them. No diagnostic data is sent automatically.

## Evidence for the current changes

- Automated: independent profiles, legacy layouts, duplicate models, app rules, touch event dispatch, selected-page previews, fast state paths, diagnostic omissions and the existing security suite.
- Physical: record the local MK.2 check in the implementation report. Do not treat the MK.2 result as validation of touch, dials or other product families.
