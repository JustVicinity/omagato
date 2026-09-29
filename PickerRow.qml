import QtQuick
import qs.Commons

Rectangle {
  id: root
  property string label: ""
  property string iconSource: ""
  property string glyph: "󰏗"
  signal chosen()

  implicitHeight: Style.space(42)
  radius: 7
  color: pointer.containsMouse ? Color.bar.background : "transparent"
  border.width: pointer.containsMouse ? 1 : 0
  border.color: Color.accent

  Image {
    id: appIcon
    visible: root.iconSource !== ""
    x: Style.space(9)
    anchors.verticalCenter: parent.verticalCenter
    width: Style.space(26)
    height: width
    source: root.iconSource
    fillMode: Image.PreserveAspectFit
    asynchronous: true
  }
  Text {
    visible: !appIcon.visible || appIcon.status === Image.Error
    x: Style.space(9)
    anchors.verticalCenter: parent.verticalCenter
    width: Style.space(26)
    text: root.glyph
    color: Color.accent
    font.family: Style.font.family
    font.pixelSize: Style.font.iconLarge
    horizontalAlignment: Text.AlignHCenter
  }
  Text {
    x: Style.space(44)
    anchors.verticalCenter: parent.verticalCenter
    width: parent.width - x - Style.space(10)
    text: root.label
    textFormat: Text.PlainText
    elide: Text.ElideRight
    color: Color.popups.text
    font.family: Style.font.family
    font.pixelSize: Style.font.body
  }
  MouseArea {
    id: pointer
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: root.chosen()
  }
}
