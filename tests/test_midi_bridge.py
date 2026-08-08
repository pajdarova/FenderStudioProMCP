"""Unit tests for MidiBridge — runs without real MIDI hardware by mocking rtmidi."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from studio_pro_mcp.midi_bridge import MidiBridge, MidiBridgeError


@pytest.fixture()
def bridge():
    with (
        patch("studio_pro_mcp.midi_bridge.rtmidi.MidiOut") as mock_out_cls,
        patch("studio_pro_mcp.midi_bridge.rtmidi.MidiIn") as mock_in_cls,
    ):
        mock_out = MagicMock()
        mock_out.get_ports.return_value = ["TestPort"]
        mock_out_cls.return_value = mock_out
        mock_in = MagicMock()
        mock_in.get_ports.return_value = ["TestPort"]
        mock_in_cls.return_value = mock_in
        b = MidiBridge(port_name="TestPort", message_delay=0)
        b.open()
        yield b, mock_out


def sent_messages(mock_out: MagicMock) -> list[list[int]]:
    return [call.args[0] for call in mock_out.send_message.call_args_list]


class TestTransport:
    def test_play_sends_note_94(self, bridge):
        b, midi = bridge
        b.play()
        msgs = sent_messages(midi)
        notes = [m[1] for m in msgs if m[0] == 0x90]
        assert 94 in notes

    def test_stop_sends_note_93(self, bridge):
        b, midi = bridge
        b.stop()
        msgs = sent_messages(midi)
        notes = [m[1] for m in msgs if m[0] == 0x90]
        assert 93 in notes

    def test_record_sends_note_95(self, bridge):
        b, midi = bridge
        b.record()
        msgs = sent_messages(midi)
        notes = [m[1] for m in msgs if m[0] == 0x90]
        assert 95 in notes

    def test_toggle_loop_sends_note_86(self, bridge):
        b, midi = bridge
        b.toggle_loop()
        msgs = sent_messages(midi)
        notes = [m[1] for m in msgs if m[0] == 0x90]
        assert 86 in notes

    def test_save_sends_note_0x50(self, bridge):
        """UTILITIES: SAVE per the Emagic Logic Control MIDI Implementation spec."""
        b, midi = bridge
        b.save()
        msgs = sent_messages(midi)
        notes = [m[1] for m in msgs if m[0] == 0x90]
        assert 0x50 in notes

    def test_undo_sends_note_0x51(self, bridge):
        """UTILITIES: UNDO per the Emagic Logic Control MIDI Implementation spec."""
        b, midi = bridge
        b.undo()
        notes = [m[1] for m in sent_messages(midi) if m[0] == 0x90]
        assert 0x51 in notes

    def test_redo_holds_shift_while_pressing_undo(self, bridge):
        """Logic Control has no dedicated Redo ID: SHIFT (0x46) held + UNDO (0x51) pressed."""
        b, midi = bridge
        b.redo()
        msgs = sent_messages(midi)
        note_on_notes = [m[1] for m in msgs if m[0] == 0x90 and m[2] > 0]
        note_off_notes = [m[1] for m in msgs if m[0] == 0x90 and m[2] == 0]
        assert 0x46 in note_on_notes  # SHIFT pressed
        assert 0x51 in note_on_notes  # UNDO pressed
        assert 0x46 in note_off_notes  # SHIFT released
        # SHIFT must go down before UNDO and come up after it
        shift_on_idx = next(i for i, m in enumerate(msgs) if m[1] == 0x46 and m[2] > 0)
        undo_on_idx = next(i for i, m in enumerate(msgs) if m[1] == 0x51 and m[2] > 0)
        shift_off_idx = next(i for i, m in enumerate(msgs) if m[1] == 0x46 and m[2] == 0)
        assert shift_on_idx < undo_on_idx < shift_off_idx


class TestMixerFader:
    def test_fader_channel_0_uses_pitch_bend_ch1(self, bridge):
        b, midi = bridge
        b.set_fader(0, 50)
        msgs = sent_messages(midi)
        pb_msgs = [m for m in msgs if m[0] == 0xE0]  # pitch bend ch 1 (0-indexed 0)
        assert len(pb_msgs) == 1

    def test_fader_master_uses_pitch_bend_ch9(self, bridge):
        b, midi = bridge
        b.set_fader("master", 75)
        msgs = sent_messages(midi)
        pb_msgs = [m for m in msgs if m[0] == 0xE8]  # pitch bend ch 9 (0-indexed 8)
        assert len(pb_msgs) == 1

    def test_fader_level_100_maps_to_max_pb(self, bridge):
        b, midi = bridge
        b.set_fader(0, 100)
        msgs = sent_messages(midi)
        pb = [m for m in msgs if m[0] == 0xE0][0]
        pb_value = pb[1] | (pb[2] << 7)
        assert pb_value == 16383

    def test_fader_level_0_maps_to_zero_pb(self, bridge):
        b, midi = bridge
        b.set_fader(0, 0)
        msgs = sent_messages(midi)
        pb = [m for m in msgs if m[0] == 0xE0][0]
        pb_value = pb[1] | (pb[2] << 7)
        assert pb_value == 0

    def test_fader_clamps_level(self, bridge):
        b, midi = bridge
        b.set_fader(0, 200)  # should clamp to 100
        state = b.get_assumed_state()
        assert state["fader_levels"][0] == 100.0

    def test_invalid_channel_raises(self, bridge):
        b, _ = bridge
        with pytest.raises(ValueError):
            b.set_fader(9, 50)


class TestMidiInFeedback:
    def test_pitch_bend_updates_channel_fader_level(self, bridge):
        b, _ = bridge
        # channel 2 (0-indexed), full-scale pitch bend (0x7F, 0x7F -> 16383)
        b._on_midi_in(([0xE2, 0x7F, 0x7F], 0.0))
        assert b.get_assumed_state()["fader_levels"][2] == pytest.approx(100.0)

    def test_pitch_bend_zero_maps_to_zero_level(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0xE0, 0x00, 0x00], 0.0))
        assert b.get_assumed_state()["fader_levels"][0] == pytest.approx(0.0)

    def test_pitch_bend_master_channel_maps_to_master_key(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0xE8, 0x00, 0x40], 0.0))  # channel 8 (0-indexed) = master
        assert "master" in b.get_assumed_state()["fader_levels"]
        assert 0 not in b.get_assumed_state()["fader_levels"]

    def test_confirmed_feedback_overrides_optimistic_send(self, bridge):
        b, _ = bridge
        b.set_fader(0, 100)
        assert b.get_assumed_state()["fader_levels"][0] == pytest.approx(100.0)
        b._on_midi_in(([0xE0, 0x00, 0x00], 0.0))  # DAW reports it's actually at 0
        assert b.get_assumed_state()["fader_levels"][0] == pytest.approx(0.0)

    def test_non_pitch_bend_message_ignored(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0x90, 60, 127], 0.0))  # note-on, not pitch bend
        assert b.get_assumed_state()["fader_levels"] == {}

    def test_short_message_ignored(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0xE0], 0.0))
        assert b.get_assumed_state()["fader_levels"] == {}


class TestChannelMetering:
    def test_enable_channel_meter_sends_sysex(self, bridge):
        b, midi = bridge
        b.enable_channel_meter(2)
        msgs = sent_messages(midi)
        sysex = [m for m in msgs if m[0] == 0xF0]
        assert len(sysex) == 1
        assert sysex[0] == [0xF0, 0x00, 0x00, 0x66, 0x14, 0x20, 2, 0x4, 0xF7]

    def test_enable_channel_meter_mode_bits(self, bridge):
        b, midi = bridge
        b.enable_channel_meter(0, level=True, peak_hold=True, signal_present=True)
        sysex = [m for m in sent_messages(midi) if m[0] == 0xF0][0]
        assert sysex[-2] == 0x7  # mm = 0b111

    def test_channel_pressure_updates_meter_level(self, bridge):
        b, _ = bridge
        # channel 3, level nibble 0xC (100%): high nibble = 3, low nibble = 0xC
        b._on_midi_in(([0xD0, (3 << 4) | 0xC], 0.0))
        assert b.get_assumed_state()["meter_levels"][3] == pytest.approx(100.0)

    def test_channel_pressure_zero_level(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0xD0, (1 << 4) | 0x0], 0.0))
        assert b.get_assumed_state()["meter_levels"][1] == pytest.approx(0.0)

    def test_channel_pressure_set_overload(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0xD0, (5 << 4) | 0xE], 0.0))
        assert b.get_assumed_state()["meter_overload"][5] is True

    def test_channel_pressure_clear_overload(self, bridge):
        b, _ = bridge
        b._on_midi_in(([0xD0, (5 << 4) | 0xE], 0.0))
        b._on_midi_in(([0xD0, (5 << 4) | 0xF], 0.0))
        assert b.get_assumed_state()["meter_overload"][5] is False


class TestMixerButtons:
    def test_toggle_mute_toggles_state(self, bridge):
        b, midi = bridge
        b.toggle_mute(0)
        assert b.get_assumed_state()["mute"][0] is True
        b.toggle_mute(0)
        assert b.get_assumed_state()["mute"][0] is False

    def test_toggle_solo_toggles_state(self, bridge):
        b, midi = bridge
        b.toggle_solo(2)
        assert b.get_assumed_state()["solo"][2] is True

    def test_toggle_rec_arm_toggles_state(self, bridge):
        b, midi = bridge
        b.toggle_rec_arm(3)
        assert b.get_assumed_state()["rec_arm"][3] is True

    def test_mute_sends_correct_note(self, bridge):
        b, midi = bridge
        b.toggle_mute(0)
        notes = [m[1] for m in sent_messages(midi) if m[0] == 0x90]
        assert 16 in notes  # _NOTE_MUTE_BASE + 0

    def test_solo_sends_correct_note(self, bridge):
        b, midi = bridge
        b.toggle_solo(1)
        notes = [m[1] for m in sent_messages(midi) if m[0] == 0x90]
        assert 9 in notes  # _NOTE_SOLO_BASE + 1

    def test_invalid_strip_raises(self, bridge):
        b, _ = bridge
        with pytest.raises(ValueError):
            b.toggle_mute(8)


class TestMixerPan:
    def test_pan_right_sends_positive_cc(self, bridge):
        b, midi = bridge
        b.set_pan(0, 10)
        msgs = sent_messages(midi)
        cc_msgs = [m for m in msgs if m[0] == 0xB0 and m[1] == 16]  # CC 16 = VPot 1
        assert len(cc_msgs) == 1
        assert cc_msgs[0][2] == 10  # positive pan = raw value

    def test_pan_zero_sends_zero_cc(self, bridge):
        b, midi = bridge
        b.set_pan(0, 0)
        msgs = sent_messages(midi)
        cc_msgs = [m for m in msgs if m[0] == 0xB0 and m[1] == 16]
        assert cc_msgs[0][2] == 0

    def test_pan_clamps(self, bridge):
        b, _ = bridge
        b.set_pan(0, 100)  # should clamp to 63


class TestLifecycle:
    def test_send_before_open_raises(self):
        with patch("studio_pro_mcp.midi_bridge.rtmidi.MidiOut"):
            b = MidiBridge(port_name="X", message_delay=0)
            with pytest.raises(MidiBridgeError):
                b.play()

    def test_close_cleans_up(self, bridge):
        b, midi = bridge
        b.close()
        midi.close_port.assert_called_once()
