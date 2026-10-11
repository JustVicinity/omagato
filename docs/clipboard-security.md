# Clipboard boundary correction

## Report and cause

The [Marketplace review](https://github.com/omacom/omarchy-plugin-marketplace/issues/10977#issuecomment-6104866873) identified automatic native clipboard reads in the editable Qt controls used by OmaGato 0.8.0. The single-line `UiField` and the two raw `TextArea` controls were affected. Qt's paste-availability updates can request foreign text before any paste action. An unbounded receiver in the shared shell therefore bypasses limits applied later to actions or saved scripts.

Our original validation covered bounded Python/device/file inputs and a benign QML load. It did not put an instrumented foreign clipboard offer in front of native editors. Dependency auditing covered pinned Python packages, not Qt internals. The deterministic Marketplace baseline reported capabilities rather than proving this boundary safe. Treating those passing gates as sufficient missed this input path.

## Correction

All plugin-owned native editors remain `readOnly: true` for their entire lifetime. Guarded keyboard editing updates their text programmatically without toggling native editability. Copy and selection remain native; cut, undo, redo and explicit paste use guarded handlers. Both multiline controls now use the same boundary. Middle-button paste is swallowed and native drop insertion stays disabled.

Explicit paste runs `wl-paste` outside the shared shell. The reader collects at most 60 KiB plus one detection byte, stops after a two-second total deadline even for a trickling provider, and kills the producer process group. Only successful bounded UTF-8 text reaches QML; provider stderr is never displayed. Edits or focus/selection changes during an asynchronous read discard its result. Each editor also limits text length and retains at most sixteen undo snapshots.

Native IME composition is temporarily unavailable because the underlying Qt editor stays read-only. Unicode key events and bounded Unicode paste remain supported. This workaround protects OmaGato's own editors; it does not fix unrelated controls in the shared Omarchy shell.

## Regression evidence

`bash scripts/test-clipboard-ui.sh --baseline` reproduces unsolicited payload retrieval with native editable controls. On the locally installed Qt 6.11.2 it reports six retrievals and exits nonzero. The reviewer refers to Qt 6.12; that exact version was not locally executed.

`bash scripts/test-clipboard-ui.sh` exercises the actual guarded editor components against an instrumented foreign `QMimeData` offer and reports zero unsolicited retrievals for both. It also checks Unicode typing, deletion, undo, selection replacement and explicit paste routing while native read-only mode remains enabled. The test replaces only the Omarchy styling singletons and the subprocess adapter; it does not place an attack in the user's real desktop clipboard.

Python tests exercise the real subprocess reader with finite data, an endless stream, a silent process, a trickling process, an inherited pipe held open by a child, invalid UTF-8/NULs and unsuccessful producers. Inventory checks prevent reintroducing raw unguarded text editors elsewhere in the plugin. CI runs the native UI test alongside the Python/security suite.

The local validation run passed all 95 Python tests. A separate Quickshell load exercised the full panel. After installation, an end-to-end check used a synthetic `wl-paste` executable and confirmed that the real `ClipboardReader` → installed CLI → bounded reader path inserted Unicode text successfully. It did not read the user's clipboard. The controller service remained active and the saved configuration was unchanged (the runtime status file was refreshed).
