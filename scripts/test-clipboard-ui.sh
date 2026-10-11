#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
qa_dir="$(mktemp -d)"
trap 'rm -rf -- "$qa_dir"' EXIT
mkdir -p "$qa_dir/imports/qs/Commons"
cp "$source_dir"/{UiField.qml,UiTextArea.qml,SafeEditMenu.qml,SafeEditing.js} "$qa_dir/"
# Replace only the external process adapter; exercise the real editor and JS.
cat > "$qa_dir/ClipboardReader.qml" <<'QML'
import QtQuick
Item {
  objectName: "clipboardAdapter"
  property var target
  property bool multiline: false
  property int requests: 0
  function request() { requests++ }
}
QML
cat > "$qa_dir/imports/qs/Commons/qmldir" <<'QML'
module qs.Commons
singleton Color 1.0 Color.qml
singleton Style 1.0 Style.qml
QML
cat > "$qa_dir/imports/qs/Commons/Color.qml" <<'QML'
pragma Singleton
import QtQml
QtObject {
  property var popups: ({ text: "#ffffff", background: "#202020", border: "#808080" })
  property string accent: "#88aaff"
  property string muted: "#888888"
  property string background: "#000000"
}
QML
cat > "$qa_dir/imports/qs/Commons/Style.qml" <<'QML'
pragma Singleton
import QtQml
QtObject {
  property var font: ({ family: "sans-serif", body: 14 })
  function space(value) { return value }
}
QML
# pkg-config emits compiler/linker words, intentionally split here.
# shellcheck disable=SC2046
g++ -std=c++17 -fPIC "$source_dir/tests/native/clipboard_editor.cpp" -o "$qa_dir/probe" \
  $(pkg-config --cflags --libs Qt6Quick Qt6Qml Qt6Gui Qt6QuickControls2 Qt6Test)
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME='' QT_QUICK_CONTROLS_STYLE=Basic \
  "$qa_dir/probe" "$qa_dir" "$@"
