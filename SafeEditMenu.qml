import QtQuick
import QtQuick.Controls
import "SafeEditing.js" as Editing

MouseArea {
  id: mouse
  required property var editor
  property bool multiline: false
  anchors.fill: parent
  acceptedButtons: Qt.RightButton | Qt.MiddleButton
  // Swallow native middle-button paste; right-click offers explicit safe paste.
  onPressed: function(event) { event.accepted = true }
  onClicked: function(event) {
    if (event.button === Qt.RightButton) { editor.forceActiveFocus(); menu.popup() }
  }
  Menu {
    id: menu
    MenuItem { text: qsTr("Copy"); enabled: mouse.editor.selectedText.length > 0; onTriggered: mouse.editor.copy() }
    MenuItem { text: qsTr("Cut"); enabled: mouse.editor.selectedText.length > 0; onTriggered: { mouse.editor.copy(); Editing.replace(mouse.editor, "", mouse.multiline) } }
    MenuItem { text: qsTr("Paste"); onTriggered: { mouse.editor.forceActiveFocus(); Qt.callLater(function() { mouse.editor.requestPaste() }) } }
    MenuItem { text: qsTr("Select all"); onTriggered: mouse.editor.selectAll() }
    MenuItem { text: qsTr("Undo"); enabled: mouse.editor.editHistory.length > 0; onTriggered: Editing.restore(mouse.editor, true) }
    MenuItem { text: qsTr("Redo"); enabled: mouse.editor.redoHistory.length > 0; onTriggered: Editing.restore(mouse.editor, false) }
  }
}
