import QtQuick
import QtQuick.Controls
import qs.Commons

ComboBox {
  id: select
  implicitHeight: Style.space(38)
  font.family: Style.font.family
  font.pixelSize: Style.font.body
  palette.base: Color.popups.background
  palette.text: Color.popups.text
  palette.button: Color.popups.background
  palette.buttonText: Color.popups.text
  palette.highlight: Color.accent
  palette.highlightedText: Color.background
  background: Rectangle {
    radius: 8
    color: Color.popups.background
    border.width: select.activeFocus ? 2 : 1
    border.color: select.activeFocus ? Color.accent : Color.popups.border
  }
}
