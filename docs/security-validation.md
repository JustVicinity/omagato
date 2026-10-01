# Security fix validation, 0.7.1

This change starts from commit `73005f262ec764d5ad76f9cde3393845a6bc20fe`, the version referenced by the [marketplace finding](https://github.com/omacom/omarchy-plugin-marketplace/issues/9325#issuecomment-5918880140).

## Implemented controls

| Review finding | Implementation |
|---|---|
| S1: unbounded light bodies | Shared bounded HTTP transport, 64 KiB light and 1 MiB OpenXLR limits. Content-Length is checked but actual reads are limited independently. Empty acknowledgements work. |
| S2: redirects and token forwarding | Direct HTTP connections never follow redirects and reject them without reading their bodies. No proxy environment handling. DNS addresses are validated and pinned. OpenXLR verifies the UID of the established reverse TCP peer before sending its token. Echoed token values are redacted from response fields; endpoint error details are not reflected. |
| S3: slow requests | Each request runs in an isolated, killable Python worker. The parent kills and reaps it at a three-second deadline, including DNS and trickle responses. Four request slots, four concurrent periodic light probes and 15-second failure backoff. |
| S4: invalid shapes | Bounded, finite, depth-limited JSON parsing and explicit schemas for light state, nested OpenXLR capabilities/state/mixer, configurations and controller status. Invalid OpenXLR state becomes unavailable; CLI failures remain JSON. |
| S5: unbounded events/history | One action worker, 32-entry queue, dial coalescing, key debounce, direct child-process count and launch-rate limits. Thirty-two stored errors of at most 240 characters; journal errors at most once every 30 seconds. |
| H1: image expansion and changing files | A single bounded regular-file snapshot feeds decoding and hashing. File, dimension and pixel limits apply before decoding. SVGs render from stdin under memory/CPU/time limits. |
| H2: files/installation/supply chain | Private atomic file writes, bounded reads, symlink guards, narrowed USB rules, pinned artifact hashes, explicit index with pip configuration disabled, user-service limits, SECURITY.md and scheduled CI. |

## Local validation

Checked on Linux with Python 3.14.7, Pillow 12.3.0 and streamdeck 0.10.0 in an isolated temporary venv:

- All 70 existing and security regression tests passed: `python -m unittest discover -s tests`.
- Real local HTTP servers exercise exact/oversized/chunked bodies, wrong Content-Length, empty acknowledgements, every standard redirect status and ignored proxy environment variables.
- Redirect tests confirm zero requests at the target and no redirect-body reads. Loopback token tests use dummy credentials only; a full round trip exercises the actual subprocess worker and Linux peer check.
- Deadline tests cover a sleeping process, a stalled DNS resolver and continuous slow response bytes. The timed-out worker is confirmed gone.
- File tests cover limits, atomic symlink replacement, secret permissions, unsafe directories, installer path guards and imports whose source changes during decoding.
- Event tests verify queue capacity, dial coalescing, bounded errors, log rate and process-launch limits. Repeated key releases and dial pushes retain separate FIFO entries while the worker is busy; only dial turns are coalesced.
- Ten offline installer lifecycle tests exercise install, in-place update, removal, explicit configuration purge, unrelated units/checkouts, symlink paths and package/service failures. They copy the shipped scripts into a temporary tree, replace their home-root references with a test-only variable and stub package, systemd and Omarchy commands. The actual home, installed packages and services are untouched; these are lifecycle simulations, not a native Omarchy installation test.
- Five configuration compatibility tests cover a representative synthetic version-1 fixture with all action types, minimal legacy defaults, preservation of unknown fields and CLI updates. Malformed or newly disallowed configurations return controlled JSON errors and retain their original bytes. No real user configuration was accessed.
- Real `rsvg-convert` exercised under the renderer limits.
- Hashed, binary-only package installation passed in the temporary venv. `pip-audit 2.10.1` reported no known vulnerabilities for the two pinned dependencies on 2026-10-01.
- ShellCheck 0.11.0 and `bash -n` passed for installation/removal/USB/bootstrap scripts. Python compilation and `git diff --check` passed.
- `systemd-analyze --user verify` passed for the generated unit with ExecStart substituted by `/usr/bin/true` solely for syntax checking. No service was installed or started.

The CI matrix is configured for Python 3.11–3.14; only 3.14 was run locally. At the time of local validation, remote GitHub Actions had not run on the change. Its results are recorded separately in the repository's Actions runs. CI's optional renderer test skips when librsvg is absent; it ran locally.

## Software acceptance for the security release

The project does not have the hardware needed to validate all integrations. No physical Elgato devices or live OpenXLR instance were used for this change. Physical-device tests are not a release prerequisite for this security fix.

The release's security evidence is the software validation above: real local HTTP servers, the actual request worker, hostile response cases, process termination, file protections and bounded queues. These exercise the client-side protections without requiring an Elgato device. Device data outside the permitted schemas or limits is rejected rather than processed without bounds.

Before publishing, require passing automated checks for the final revision, including the configured CI Python matrix once the change is pushed. State explicitly that the security fix was validated in software and that physical compatibility of these changes has not been tested. Do not claim all models have been validated.

The tests establish the exercised security behavior; they do not prove that every possible vulnerability has been eliminated. Remaining uncertainty concerns actual device response variations, firmware-specific behavior and compatibility with the new limits. Device availability does not justify disabling these protections.

## Optional compatibility follow-up

When devices or community reports become available, check:

1. Stream Deck connect/reconnect, keys, command/script macros, pages, volume dials and icons.
2. Light state, power, brightness, temperature, rename and identify, including empty PUT/POST acknowledgements and model-specific response ranges.
3. OpenXLR state, controls and mixer with its normal private token file and same-UID daemon.
4. Camera/audio controls, teleprompter save/read/display and access to supported USB products.

Install/update/uninstall checks on Omarchy remain useful independently of having Elgato hardware. The service's inherited memory/task limits may also affect user-configured applications and scripts; document any needed user-unit overrides rather than asserting that those workloads were tested.

Enable GitHub private vulnerability reporting in repository settings if it is not already enabled. This setting and the actual release/marketplace response require repository-owner actions; local validation itself did not modify account settings, remote branches, issues or releases.

Configured scripts/apps still run as trusted user code. Same-UID software cannot be isolated by the TCP UID check. Light HTTP is unencrypted. These constraints are explicit in SECURITY.md; the implementation does not claim a complete sandbox or a security certification.
