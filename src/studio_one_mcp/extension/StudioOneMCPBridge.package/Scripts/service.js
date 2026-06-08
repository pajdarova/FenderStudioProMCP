"use strict";

/**
 * StudioOneMCPBridge — IPC command dispatcher.
 *
 * Polls ~/Documents/StudioOneMCP/ipc/ for cmd-{id}.json files written by the
 * Python MCP server. For each command file found it:
 *   1. Reads and parses the JSON command.
 *   2. Deletes the command file (signals receipt).
 *   3. Calls Host.GUI.Commands.interpretCommand(category, name, false, attrs).
 *   4. Writes resp-{id}.json with {id, ok, error}.
 *
 * Timer strategy (tried in order):
 *   A. setInterval — standard JS; available in most Studio One versions.
 *   B. Application idle signal — via Host.Objects if setInterval is absent.
 *   C. Transport positionChanged — last resort; fires during playback only.
 *
 * Command JSON schema:
 *   {
 *     "id":          "<uuid>",        // echoed in response
 *     "category":    "Track",         // interpretCommand category
 *     "name":        "Add Audio Track (mono)",
 *     "args":        {"key": "val"},  // optional; becomes Host.Attributes pairs
 *     "transaction": "My action"      // optional; wraps in begin/endTransaction
 *   }
 *
 * Response JSON schema:
 *   { "id": "<uuid>", "ok": true|false, "error": null|"message" }
 */

(function () {
    var DOCS = Host.IO.getPath("Documents");
    var IPC_DIR = DOCS + "/StudioOneMCP/ipc/";
    var POLL_MS = 100;  // 10 polls per second

    // ------------------------------------------------------------------
    // Directory bootstrap
    // ------------------------------------------------------------------

    function ensureIpcDir() {
        try { Host.IO.createFolder(IPC_DIR); } catch (e) { /* already exists */ }
    }

    // ------------------------------------------------------------------
    // Command execution
    // ------------------------------------------------------------------

    function buildAttrs(argsObj) {
        if (!argsObj) return null;
        var pairs = [];
        for (var k in argsObj) {
            if (Object.prototype.hasOwnProperty.call(argsObj, k)) {
                pairs.push(k);
                pairs.push(String(argsObj[k]));
            }
        }
        return pairs.length ? Host.Attributes(pairs) : null;
    }

    function executeCommand(cmd) {
        var attrs = buildAttrs(cmd.args || null);

        if (cmd.transaction) {
            Host.GUI.Commands.beginTransaction(cmd.transaction);
        }
        try {
            Host.GUI.Commands.interpretCommand(cmd.category, cmd.name, false, attrs);
        } finally {
            if (cmd.transaction) {
                Host.GUI.Commands.endTransaction();
            }
        }
    }

    function writeResponse(id, ok, errMsg) {
        var payload = JSON.stringify({ id: id, ok: ok, error: errMsg || null });
        try {
            Host.IO.writeFile(IPC_DIR + "resp-" + id + ".json", payload);
        } catch (e) {
            /* nothing to do if we can't write */
        }
    }

    function processFile(filePath) {
        var raw;
        try {
            raw = Host.IO.readFile(filePath);
        } catch (e) {
            return; // file vanished between listing and read — harmless
        }

        var cmd;
        try {
            cmd = JSON.parse(raw);
        } catch (e) {
            try { Host.IO.deleteFile(filePath); } catch (_) {}
            return; // malformed JSON — discard silently
        }

        // Delete command file first to prevent double-processing
        try { Host.IO.deleteFile(filePath); } catch (_) {}

        try {
            executeCommand(cmd);
            writeResponse(cmd.id, true, null);
        } catch (e) {
            writeResponse(cmd.id, false, String(e));
        }
    }

    // ------------------------------------------------------------------
    // Poll loop
    // ------------------------------------------------------------------

    function poll() {
        try {
            var files = Host.IO.getFiles(IPC_DIR, "cmd-*.json");
            if (!files || !files.length) return;
            for (var i = 0; i < files.length; i++) {
                processFile(files[i]);
            }
        } catch (e) {
            /* swallow errors so we don't break the host */
        }
    }

    // ------------------------------------------------------------------
    // Timer bootstrap — three fallback strategies
    // ------------------------------------------------------------------

    function startTimer() {
        // Strategy A: standard JS setInterval
        if (typeof setInterval === "function") {
            setInterval(poll, POLL_MS);
            return;
        }

        // Strategy B: application idle signal
        try {
            var app = Host.Objects.getObjectByUrl("object://hostapp/application");
            if (app && app.idle && typeof app.idle.connect === "function") {
                app.idle.connect(poll);
                return;
            }
        } catch (e) { /* not available in this version */ }

        // Strategy C: transport positionChanged (fires during playback)
        try {
            var transport = Host.Objects.getObjectByUrl("object://hostapp/transport");
            if (transport && transport.positionChanged &&
                    typeof transport.positionChanged.connect === "function") {
                transport.positionChanged.connect(poll);
            }
        } catch (e) { /* not available */ }
    }

    // ------------------------------------------------------------------
    // Entry point
    // ------------------------------------------------------------------

    ensureIpcDir();
    startTimer();

}());
