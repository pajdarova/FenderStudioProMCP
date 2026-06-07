# Phase 2 — UCNET Protocol Reverse Engineering

## Overview

Phase 2 replaces the blind MCU command bus with a full bidirectional integration based
on PreSonus's **UCNET** protocol — the same protocol used by PreSonus UC Surface,
PreSonus Studio One Remote, and QMix-UC. This gives the MCP server read access to
project state (track names, plugin parameters, send levels, tempo, markers, etc.) and
allows precise parameter control beyond MCU's 8-channel strip limit.

> **Status**: Research / planning phase. No code yet. This document captures findings
> from initial network analysis and community research.

---

## What Is UCNET?

UCNET is a proprietary UDP/TCP application protocol developed by PreSonus for
bidirectional DAW control. It powers:

- **PreSonus UC Surface** (StudioLive mixer control)
- **Studio One Remote** (iOS/Android DAW remote)
- **QMix-UC** (personal monitor mixing)

All communicate with a **UCNET daemon** that Studio One runs on port **54321** (UDP
discovery) and **52327** (TCP session). The app discovers the host via a UDP broadcast,
then opens a TCP session and exchanges length-prefixed binary frames.

---

## Protocol Overview (Preliminary)

### Discovery

```
Client → Broadcast UDP :54321
  Payload: "ucnet_discover\0"

Host → Unicast UDP :54321
  Payload: JSON blob with {name, version, host_id, tcp_port}
```

### Session Establishment

```
Client → TCP connect host:52327
Client → Send: LOGIN frame (client name, capabilities)
Host   → ACK + full state snapshot (all tracks, sends, inserts, transport state)
```

### Frame Format

```
 0        1        2        3
 ├────────┴────────┴────────┴────────┤
 │         payload_length (uint32 LE) │  4 bytes
 ├────────────────────────────────────┤
 │         message_type  (uint16 LE)  │  2 bytes
 ├────────────────────────────────────┤
 │         payload  (variable)        │  payload_length − 2 bytes
 └────────────────────────────────────┘
```

Payload encoding varies by message type:
- **0x0001** — Handshake / Hello
- **0x0010** — Parameter update (path + float32 value)
- **0x0011** — Parameter update (path + int32 value)
- **0x0012** — Parameter update (path + string value)
- **0x0020** — Subscribe to parameter tree subtree
- **0x0030** — Transport command
- **0x0040** — Full state snapshot chunk
- **0x00FF** — Keepalive / ping

Parameter paths use a dotted-string address space reminiscent of OSC:
```
/transport/tempo          → float32
/transport/isPlaying      → int32 (bool)
/transport/positionBars   → string "4.2.1.0"
/mixer/channel[3]/fader   → float32 (0.0 – 1.0)
/mixer/channel[3]/mute    → int32 (bool)
/mixer/channel[3]/name    → string
/mixer/channel[3]/insert[0]/bypass → int32 (bool)
```

> **Caveat**: The above paths are inferred from traffic captures and may use different
> names in the actual implementation. Full path mapping requires systematic fuzzing.

---

## Reverse Engineering Approach

### Step 1 — Traffic Capture

1. Run Studio One and UC Surface on the same machine or on a local network with
   Wireshark/tcpdump capturing loopback or LAN traffic.
2. Filter: `tcp.port == 52327 || udp.port == 54321`
3. Export as PCAP for offline analysis.

### Step 2 — Frame Dissection

```python
# Skeleton Wireshark dissector (Lua)
ucnet_proto = Proto("ucnet", "UCNET Protocol")
local f_len  = ProtoField.uint32("ucnet.len",  "Length",  base.DEC)
local f_type = ProtoField.uint16("ucnet.type", "MsgType", base.HEX)
ucnet_proto.fields = { f_len, f_type }

function ucnet_proto.dissector(buf, pinfo, tree)
    local t = tree:add(ucnet_proto, buf())
    t:add_le(f_len,  buf(0,4))
    t:add_le(f_type, buf(4,2))
end
DissectorTable.get("tcp.port"):add(52327, ucnet_proto)
```

### Step 3 — Parameter Mapping

Write a fuzzer that:
1. Connects to UCNET TCP port.
2. Subscribes to the full parameter tree (`/`).
3. Records the initial snapshot to a JSON file.
4. Triggers UI actions in Studio One and records the resulting parameter update frames.

This produces a ground-truth mapping from UI action → parameter path → value type.

### Step 4 — Client Implementation

Implement a Python asyncio UCNET client (`ucnet_client.py`):
- UDP discovery
- TCP session with keepalive
- Subscribe / receive state updates
- Send parameter write commands
- Expose a clean Python API matching the MCP tool signatures

### Step 5 — MCP Integration

Replace `MidiBridge` calls in tool handlers with `UCNETClient` calls. Because UCNET
provides state readback, tools can return actual current values rather than
optimistic "assumed" states.

---

## Known Community Resources

- **PreSonus Developer Program**: PreSonus has historically offered an NDA developer
  program that provides official UCNET documentation. Worth applying.
- **OpenStageControl**: Community threads on integrating with Studio One mention the
  UCNET TCP port.
- **packet-presonus**: An abandoned GitHub project with partial Wireshark dissectors
  for StudioLive UCNET (not Studio One specific, but same wire format).
- **studio-one-remote APK**: Decompiling the Android APK may reveal the Java-side
  framing code.

---

## Risk Factors

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Protocol changes between Studio One versions | Medium | Version-pin in connection handshake; test matrix |
| PreSonus legal action (ToS reverse-engineering clause) | Low | Review EULA; use for personal/non-commercial tooling |
| Encryption added to future versions | Low | Phase 1 MCU bridge remains functional |
| Path names completely wrong | High (initial) | Systematic capture + fuzzing corrects this |

---

## Phase 2 Target Tools (Beyond Phase 1)

| Tool | Requires UCNET |
|------|---------------|
| `get_transport_state` → `{tempo, position, isPlaying, isRecording}` | Yes |
| `get_track_list` → list of `{id, name, color, type}` | Yes |
| `get_plugin_parameters` `(track, insert_index)` | Yes |
| `set_plugin_parameter` `(track, insert, param, value)` | Yes |
| `get_send_level` `(track, send_index)` | Yes |
| `set_send_level` `(track, send_index, level)` | Yes |
| `get_markers` | Yes |
| `navigate_to_marker` `(marker_id)` | Yes |
| `get_automation_data` `(track, param, time_range)` | Yes |
| `write_automation_point` | Yes |
