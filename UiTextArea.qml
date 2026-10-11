import QtQuick
import QtQuick.Controls
import qs.Commons
import "SafeEditing.js" as Editing

TextArea {
  id: field
  readOnly: true
  textFormat: TextEdit.PlainText
  selectByMouse: true
  persistentSelection: true
  cursorVisible: activeFocus
  property int maximumLength: 60000
  property bool internalEdit: false
  onTextChanged: if (!internalEdit) { editHistory = []; redoHistory = [] }
  property var editHistory: []
  property var redoHistory: []
  property string inputError: ""
  ToolTip.visible: activeFocus && inputError.length > 0
  ToolTip.text: inputError === "clipboard_too_large" ? qsTr("Text exceeds this field's limit.") : qsTr("Clipboard could not be read safely. Try a smaller text selection.")
  ToolTip.timeout: 4000
  signal userEdited()
  function insertSafeText(value) { Editing.replace(field, value, true) }
  function requestPaste() { clipboard.request() }
  Keys.priority: Keys.BeforeItem
  Keys.onPressed: function(event) { Editing.key(field, event, true) }
  ClipboardReader { id: clipboard; target: field; multiline: true }
  SafeEditMenu { editor: field; multiline: true }
  color: Color.popups.text
  selectionColor: Color.accent
  selectedTextColor: Color.background
  font.family: Style.font.family
  font.pixelSize: Style.font.body
}
