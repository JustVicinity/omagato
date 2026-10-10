import QtQuick
import Quickshell.Io
import qs.Commons

Column {
  id: setup
  property var health: ({})
  property var words: ({})
  signal refreshRequested()
  spacing: Style.space(8)
  function t(key) { return words[key] || key.split("_").join(" ") }
  Text { text: setup.t("setup_title"); color: Color.foreground; font.family: Style.font.family; font.bold: true }
  Text {
    width: parent.width; wrapMode: Text.Wrap; color: Color.muted; font.family: Style.font.family
    text: setup.health.needs_install ? setup.t("setup_install_hint") : (setup.health.needs_restart || !setup.health.running) ? setup.t("setup_start_hint") : setup.t("setup_ready")
  }
  Text {
    visible: setup.health.usb_access === false
    width: parent.width; wrapMode: Text.Wrap; color: Color.urgent; font.family: Style.font.family
    text: setup.t("setup_usb_hint")
  }
  Text {
    width: parent.width; wrapMode: Text.Wrap; color: Color.muted; font.family: Style.font.family
    text: setup.health.tools ? setup.t("optional_tools") + ": " + Object.keys(setup.health.tools).filter(function(name) { return !setup.health.tools[name] }).join(", ") : ""
    visible: text.length > setup.t("optional_tools").length + 2
  }
  Flow {
    width: parent.width; spacing: Style.space(8)
    ActionChip { label: setup.t("setup_install"); onClicked: setup.launch("install") }
    ActionChip { label: setup.t("setup_usb"); visible: setup.health.usb_access === false; onClicked: setup.launch("usb") }
    ActionChip { label: setup.t("refresh"); onClicked: setup.refreshRequested() }
  }
  function launch(action) {
    if (terminal.running) return
    terminal.command = ["omarchy", "launch", "terminal", "bash", String(Qt.resolvedUrl("scripts/setup-terminal.sh")).replace("file://", ""), action]
    terminal.running = true
  }
  Process { id: terminal }
}
