// SHELVED 2026-06-10: command dispatch from this surface never fired.
// Kept for reference. The KeyboardDevice (StudioOneMCPPads.device) loads and
// Studio One generates a .surfacedata for it, but neither the JS PadSection
// command handler nor the XML <Command> bindings dispatch on incoming MIDI.
// Primary control path is keyboard automation (see repo SETUP.md / keystrokes.py).
include_file("resource://com.presonus.musicdevices/sdk/controlsurfacecomponent.js");

class MCPPadsComponent extends PreSonus.ControlSurfaceComponent {
    onInit(hostComponent) {
        super.onInit(hostComponent);
        var root = hostComponent.model.root;
        this.padSection = root.find("PadSectionElement");
        if (!this.padSection) return;
        var c = this.padSection.component;
        c.addHandlerForRole(PreSonus.PadSectionRole.kMusicInput);
        var commands = [];
        PreSonus.PadSection.addCommand(commands, 0, "Track", "Add Audio Track (stereo)");
        PreSonus.PadSection.addCommand(commands, 1, "Edit",  "Undo");
        PreSonus.PadSection.addCommand(commands, 2, "Edit",  "Redo");
        PreSonus.PadSection.addCommand(commands, 3, "Edit",  "Duplicate");
        PreSonus.PadSection.addCommand(commands, 4, "Transport", "Start");
        PreSonus.PadSection.addCommand(commands, 5, "Transport", "Stop");
        PreSonus.PadSection.addCommand(commands, 6, "Edit",  "Delete");
        PreSonus.PadSection.addCommand(commands, 7, "Track", "Duplicate");
        c.addCommandInputHandler(commands);
        c.setActiveHandler(1);
    }
}

function createMCPPadsComponentInstance() {
    return new MCPPadsComponent;
}
