import QtQuick
import QtQuick.Controls
import qs.Commons
import "SafeEditing.js" as Editing

TextField {
  id: field
  // Permanent, including while focused: protects Qt's automatic canPaste probe.
  readOnly: true
  maximumLength: 4096
  selectByMouse: true
  persistentSelection: true
  cursorVisible: activeFocus
  property bool internalEdit: false
  onTextChanged: if (!internalEdit) { editHistory = []; redoHistory = [] }
  property var editHistory: []
  property var redoHistory: []
  property string inputError: ""
  ToolTip.visible: activeFocus && inputError.length > 0
  ToolTip.text: inputError === "clipboard_too_large" ? qsTr("Text exceeds this field's limit.") : qsTr("Clipboard could not be read safely. Try a smaller text selection.")
  ToolTip.timeout: 4000
  function insertSafeText(value) { Editing.replace(field, value, false) }
  function requestPaste() { clipboard.request() }
  Keys.priority: Keys.BeforeItem
  Keys.onPressed: function(event) { Editing.key(field, event, false) }
  ClipboardReader { id: clipboard; target: field }
  SafeEditMenu { editor: field }

  implicitHeight: Style.space(38)
  color: Color.popups.text
  placeholderTextColor: Color.muted
  selectionColor: Color.accent
  selectedTextColor: Color.background
  font.family: Style.font.family
  font.pixelSize: Style.font.body
  leftPadding: Style.space(10)
  rightPadding: Style.space(10)
  background: Rectangle {
    radius: 8
    color: Color.popups.background
    border.width: field.activeFocus ? 2 : 1
    border.color: field.activeFocus ? Color.accent : Color.popups.border
  }
}
