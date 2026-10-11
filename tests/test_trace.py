"""Unit tests for sparse-event -> dense per-frame trace compilation."""
import pytest

from rgqa import trace as T


def ev(frame, *held):
    class _E:
        pass

    e = _E()
    e.frame = frame
    e.held = frozenset(held)
    return e


def test_idle_before_first_event_and_holds_until_changed():
    c = T.compile_trace([ev(0), ev(3, "right")], end_frame=5)
    assert c.byte_at(0) == 0x00
    assert c.byte_at(2) == 0x00
    assert c.byte_at(3) == T.BUTTON_BITS["right"]
    assert c.byte_at(5) == T.BUTTON_BITS["right"]


def test_release_is_expressed_by_a_later_smaller_held_set():
    c = T.compile_trace([ev(0, "a", "right"), ev(4, "right"), ev(6)], end_frame=7)
    assert c.byte_at(0) == 0x01 | 0x80
    assert c.byte_at(4) == 0x80
    assert c.byte_at(6) == 0x00


def test_buttons_combine_into_one_byte():
    c = T.compile_trace([ev(0, "a", "b", "start")], end_frame=0)
    assert c.byte_at(0) == 0x01 | 0x02 | 0x08


def test_changes_lists_only_frames_that_differ_from_previous():
    c = T.compile_trace([ev(0, "right"), ev(3, "right"), ev(5)], end_frame=6)
    assert c.changes == [(0, 0x80), (5, 0x00)]


def test_buttons_at_round_trips_names():
    c = T.compile_trace([ev(0, "a", "up")], end_frame=0)
    assert c.buttons_at(0) == frozenset({"a", "up"})


def test_trace_must_start_at_frame_zero():
    with pytest.raises(T.TraceError) as ei:
        T.compile_trace([ev(1, "a")], end_frame=3)
    assert "frame 0" in str(ei.value)


def test_unknown_button_is_rejected():
    with pytest.raises(T.TraceError) as ei:
        T.compile_trace([ev(0, "turbo")], end_frame=0)
    assert "turbo" in str(ei.value)


def test_read_out_of_range_is_rejected():
    c = T.compile_trace([ev(0)], end_frame=2)
    with pytest.raises(T.TraceError):
        c.byte_at(3)


def test_end_frame_extends_table_so_late_checkpoints_have_a_value():
    c = T.compile_trace([ev(0, "a")], end_frame=100)
    assert len(c.held) == 101
    assert c.byte_at(100) == 0x01
