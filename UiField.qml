import QtQuick
import QtQuick.Controls
import qs.Commons

TextField {
  id: field
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
