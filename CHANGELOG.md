# Changelog

## 0.7.1

Security release addressing the light response memory-exhaustion report in [marketplace issue #9325](https://github.com/omacom/omarchy-plugin-marketplace/issues/9325#issuecomment-5918880140).

- Bound all device HTTP responses and enforce a hard request deadline, including DNS. Reject redirects before reading their bodies, HTTP errors and compressed responses. Connect directly to pinned device addresses.
- Prevent OpenXLR redirect token leaks and reject foreign-user TCP peers before transmitting credentials. Validate private token files and nested API response schemas.
- Bound queued actions, direct process launches and error history; preserve repeated button actions, coalesce dial turns and back off failed periodic light probes.
- Bound local files, JSON nesting and image dimensions. Read imports from one snapshot; write managed data privately and atomically. Limit SVG rendering resources.
- Guard installer/removal paths, narrow USB access to supported Stream Deck products and add user-service resource/restart limits.
- Verify pinned package hashes and add security regression tests and scheduled dependency checks.

Compatibility: light names must use `.local` or a canonical IP address; symlink managed installation paths and non-private OpenXLR token files are rejected. Existing version-1 configuration fields are retained. Configurations exceeding the new limits are rejected with an error without rewriting the file and need manual correction; there is no automatic migration. See [SECURITY.md](SECURITY.md) for limits and trust assumptions. The security changes were validated through automated tests and local HTTP simulations; no physical Elgato hardware was used for this release. Hardware checks are optional compatibility follow-up, not a prerequisite for the security fix.
