# Device and feature matrix

OmaGato aims to make Elgato hardware useful from one Omarchy panel. **Only Stream Deck MK.2 has been checked here with physical hardware.** Every other path below is based on documented protocols, Linux device interfaces, and software integration; it needs field reports from owners. A device appearing in the overview means it was detected, not that every vendor feature works.

The physical MK.2 check predates the 0.7.1 security changes. Those changes were validated with automated tests and local HTTP simulations; no physical-device validation was performed for this security release. Hardware checks are optional follow-up for compatibility, not a prerequisite for retaining the security protections.

| Family | Implemented in OmaGato | Hardware test status and current gaps |
| --- | --- | --- |
| Stream Deck Mini, standard, MK.2, XL, Neo, Plus, Plus XL, Pedal, and HID compatible models | Physical keys, icons, actions, pages, brightness; basic dial actions where the Python driver exposes dials | MK.2 tested. Other variants untested. Touch strips, smart profiles, and proprietary Marketplace actions are not implemented. Driver recognition varies by model. |
| Key Light, Key Light Air, Neo, Mini, Ring Light | Local network discovery/manual address, power, brightness, temperature, identify, rename, group controls where the device's API supports them | No light physically tested. Availability depends on the local Elgato light API; specific model ranges may differ. |
| Light Strip and Light Strip Pro | Discovery and shared light controls where exposed by the light API | Untested; RGB effects and custom scenes are not implemented. |
| Facecam, Cam Link, Game Capture with V4L2 | Live camera preview; editable V4L2 controls reported by the driver, including menus and defaults | Untested. Camera Hub firmware, presets, and proprietary effects are not implemented. Capture recording remains with the user's recording app. |
| Wave microphones and XLR interfaces | PipeWire volume/mute; optional OpenXLR hardware controls and mixer levels, shown only when OpenXLR advertises the capability | OpenXLR integration tested with mocked API responses, not physical audio hardware. Advanced routing, plugin chains, and profile editing remain in OpenXLR itself. |
| Prompter and Prompter XL | Script editor, display and window mirroring, scroll, chapter and flip actions; Hyprland monitor detection | No physical Prompter tested. A working DisplayLink display is required. Camera mirror and automatic meeting integration are not implemented. |
| Stream Deck Studio, Galleon 100 SD, and unknown Elgato USB products | USB discovery and model display; controls only if a supported Linux driver exposes them | Physical controls have not been verified. |

Implementation gaps are tracked here so contributors can focus on them. Please include a model name, USB product ID (if applicable), firmware, and observed behavior in an issue; do not include private tokens, personal file paths, or camera images.
