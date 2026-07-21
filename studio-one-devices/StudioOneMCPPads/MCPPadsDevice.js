// SHELVED 2026-06-10 — see MCPPadsComponent.js for status.
include_file("resource://com.presonus.musicdevices/sdk/midiprotocol.js");
include_file("resource://com.presonus.musicdevices/sdk/controlsurfacedevice.js");

class MCPPadsDevice extends PreSonus.ControlSurfaceDevice {
    onInit(hostDevice) {
        super.onInit(hostDevice);
    }
}

function createMCPPadsDeviceInstance() {
    return new MCPPadsDevice();
}
