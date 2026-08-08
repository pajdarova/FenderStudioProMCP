"""Unit tests for MidiBridge — runs without real MIDI hardware by mocking rtmidi."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from studio_pro_mcp.midi_bridge import MidiBridge, MidiBridgeError


@pytest.fixture()
def bridge():
    with patch("studio_pro_mcp.midi_bridge.rtmidi.MidiOut") as mock_out_cls:
        mock_out = MagicMock()
        mock_out.get_ports.return_value = ["TestPort"]
        mock_out_cls.return_value = mock_out
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

    def test_save_sends_note_98(self, bridge):
        b, midi = bridge
        b.save()
        msgs = sent_messages(midi)
        notes = [m[1] for m in msgs if m[0] == 0x90]
        assert 98 in notes

    def test_undo_sends_note_110(self, bridge):
        b, midi = bridge
        b.undo()
        notes = [m[1] for m in sent_messages(midi) if m[0] == 0x90]
        assert 110 in notes

    def test_redo_sends_note_101(self, bridge):
        b, midi = bridge
        b.redo()
        notes = [m[1] for m in sent_messages(midi) if m[0] == 0x90]
        assert 101 in notes


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
