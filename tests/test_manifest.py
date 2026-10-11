"""Unit tests for manifest loading and validation.

These tests exercise the pure-Python validation layer: no emulator is started.
They are written against rgqa.manifest, which validates structure via the JSON
Schema and then applies the cross-field rules the schema cannot express
(absolute paths, duplicate ports, unsupported capabilities, trace ordering).
"""
import json

import pytest

from rgqa import manifest as M
from conftest import base_manifest, SCHEMA


# --- schema loading ---------------------------------------------------------

def test_schema_file_exists_and_is_valid_json():
    doc = json.loads(SCHEMA.read_text())
    assert doc["$id"].endswith("test-manifest.schema.json")
    assert doc["properties"]["schema_version"]["const"] == 1


# --- happy path -------------------------------------------------------------

def test_valid_manifest_loads(write_manifest):
    p = write_manifest(base_manifest())
    m = M.load(p)
    assert m.id == "smoke"
    assert m.target.region == "ntsc"
    assert m.limits.max_frames == 120
    assert len(m.checkpoints) == 1


def test_manifest_is_immutable(write_manifest):
    m = M.load(write_manifest(base_manifest()))
    with pytest.raises(Exception):
        m.id = "other"


# --- structural rejection ---------------------------------------------------

@pytest.mark.parametrize(
    "mutation, needle",
    [
        (lambda d: d.pop("trace"), "trace"),
        (lambda d: d.update(schema_version=2), "schema_version"),
        (lambda d: d.update(id="Bad Id!"), "id"),
        (lambda d: d["target"].update(sha256="xyz"), "sha256"),
        (lambda d: d["target"].update(region="mars"), "region"),
        (lambda d: d["emulator"].update(adapter="fceux"), "adapter"),
        (lambda d: d["trace"].update(format="linear_v9"), "format"),
        (lambda d: d["trace"].update(frames=[{"frame": 0, "held": ["jump"]}]), "held"),
        (lambda d: d["limits"].update(max_frames=0), "max_frames"),
        (lambda d: d["ports"][0].update(device="zapper"), "device"),
    ],
)
def test_schema_violations_are_rejected(write_manifest, mutation, needle):
    d = base_manifest()
    mutation(d)
    p = write_manifest(d)
    with pytest.raises(M.ManifestError) as ei:
        M.load(p)
    assert needle in str(ei.value)


def test_missing_file_reports_path(tmp_path):
    with pytest.raises(M.ManifestError) as ei:
        M.load(tmp_path / "nope.json")
    assert "nope.json" in str(ei.value)


def test_invalid_json_reports_parse_error(write_manifest, tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ not json ")
    with pytest.raises(M.ManifestError) as ei:
        M.load(p)
    assert "JSON" in str(ei.value)


# --- cross-field rules the schema cannot express ----------------------------

def test_absolute_rom_path_is_rejected(write_manifest):
    d = base_manifest()
    d["target"]["rom"] = "/etc/passwd"
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "relative" in str(ei.value)


def test_rom_path_may_not_escape_the_suite_root(write_manifest):
    d = base_manifest()
    d["target"]["rom"] = "../../../../../../etc/passwd"
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "escape" in str(ei.value).lower() or "relative" in str(ei.value)


def test_duplicate_port_numbers_are_rejected(write_manifest):
    d = base_manifest()
    d["ports"] = [
        {"port": 1, "device": "nes_controller"},
        {"port": 1, "device": "nes_controller"},
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "duplicate" in str(ei.value).lower()


def test_trace_frames_must_be_strictly_increasing(write_manifest):
    d = base_manifest()
    d["trace"]["frames"] = [
        {"frame": 0, "held": []},
        {"frame": 10, "held": ["right"]},
        {"frame": 10, "held": ["right", "a"]},
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "increas" in str(ei.value).lower()


def test_trace_must_start_at_frame_zero(write_manifest):
    d = base_manifest()
    d["trace"]["frames"] = [{"frame": 5, "held": []}]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "frame 0" in str(ei.value).lower() or "start" in str(ei.value).lower()


def test_trace_anchor_beyond_max_frames_is_rejected(write_manifest):
    d = base_manifest()
    d["limits"]["max_frames"] = 30
    d["trace"]["frames"] = [{"frame": 0, "held": []}, {"frame": 100, "held": ["a"]}]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "max_frames" in str(ei.value)


def test_checkpoint_frame_beyond_max_frames_is_rejected(write_manifest):
    d = base_manifest()
    d["limits"]["max_frames"] = 30
    d["checkpoints"][0]["frame"] = 90
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "max_frames" in str(ei.value)


def test_symbol_without_symbols_from_is_rejected(write_manifest):
    d = base_manifest()
    d["checkpoints"] = [
        {"name": "x", "frame": 10, "op": "eq", "value": 1, "symbol": "pad1_held"}
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "symbols_from" in str(ei.value)


def test_symbol_without_segment_base_is_rejected(write_manifest):
    d = base_manifest()
    d["checkpoints"] = [
        {
            "name": "x",
            "frame": 10,
            "op": "eq",
            "value": 1,
            "symbol": "pad1_held",
            "symbols_from": "input-probe.lbl",
        }
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "segment_base" in str(ei.value)


def test_comparison_op_without_value_is_rejected(write_manifest):
    d = base_manifest()
    d["checkpoints"] = [
        {
            "name": "x",
            "frame": 10,
            "op": "eq",
            "span": 1,
            "address": 0x0302,
            "space": "cpu_ram",
        }
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "value" in str(ei.value)


def test_unary_op_with_value_is_rejected(write_manifest):
    d = base_manifest()
    d["checkpoints"] = [
        {
            "name": "x",
            "frame": 10,
            "op": "nonzero",
            "value": 3,
            "address": 0x0302,
            "space": "cpu_ram",
        }
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "value" in str(ei.value)


def test_two_byte_span_must_be_announced_for_symbol_assertions(write_manifest):
    """A 2-byte read only makes sense for the frame counter; a 2-byte read of a
    1-byte field is a manifest bug, so the schema requires an explicit span."""
    d = base_manifest()
    d["checkpoints"][0].pop("span")
    d["checkpoints"][0]["op"] = "gt"
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "span" in str(ei.value)


def test_screenshot_checkpoint_is_rejected_as_unsupported(write_manifest):
    """Declared capabilities must be honest: the headless adapter has no proven
    screenshot path, so a manifest asking for one fails loudly."""
    d = base_manifest()
    d["screenshot_checkpoints"] = [
        {"name": "title", "frame": 5, "baseline": "baselines/title.png"}
    ]
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "screenshot" in str(ei.value).lower()


def test_unsupported_schema_version_names_the_version(write_manifest):
    d = base_manifest()
    d["schema_version"] = 99
    with pytest.raises(M.ManifestError) as ei:
        M.load(write_manifest(d))
    assert "99" in str(ei.value)
