import QtQuick
import QtMultimedia
import qs.Commons

Item {
  id: root
  property string deviceNode: ""
  property string deviceName: ""
  MediaDevices { id: mediaDevices }

  function selectedCamera() {
    var inputs = mediaDevices.videoInputs
    for (var i = 0; i < inputs.length; i++) {
      if (String(inputs[i].id).includes(deviceNode)) return inputs[i]
    }
    for (var j = 0; j < inputs.length; j++) {
      if (deviceName && String(inputs[j].description).includes(deviceName)) return inputs[j]
    }
    return mediaDevices.defaultVideoInput
  }

  Rectangle { anchors.fill: parent; radius: 9; color: Color.popups.background }
  CaptureSession {
    camera: Camera {
      id: camera
      cameraDevice: root.selectedCamera()
      active: root.visible && root.deviceNode !== ""
    }
    videoOutput: videoOutput
  }
  VideoOutput {
    id: videoOutput
    anchors.fill: parent
    fillMode: VideoOutput.PreserveAspectFit
  }
}
