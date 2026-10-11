"""Shared test helpers: path anchors and a tiny manifest builder."""
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_ROM = REPO / "fixtures" / "input-probe" / "build" / "input-probe.nes"
FIXTURE_LBL = REPO / "fixtures" / "input-probe" / "build" / "input-probe.lbl"
SCHEMA = REPO / "schemas" / "test-manifest.schema.json"


def rom_sha256(path=None):
    import hashlib
    p = pathlib.Path(path or FIXTURE_ROM)
    return hashlib.sha256(p.read_bytes()).hexdigest()


def base_manifest(**overrides):
    """A minimal well-formed manifest dict; overrides patch top-level keys."""
    m = {
        "schema_version": 1,
        "id": "smoke",
        "description": "fixture smoke test",
        "target": {
            "rom": "../fixtures/input-probe/build/input-probe.nes",
            "sha256": "0" * 64,
            "region": "ntsc",
        },
        "emulator": {"adapter": "mesence", "min_version": "2.2.1", "version": "2.2.1", "binary_sha256": "0" * 64},
        "initial_state": "clean_boot",
        "ports": [{"port": 1, "device": "nes_controller"}],
        "trace": {"format": "frame_events_v1", "frames": [{"frame": 0, "held": []}]},
        "limits": {"max_frames": 120, "timeout_seconds": 30},
        "checkpoints": [
            {
                "name": "frame counter advances",
                "frame": 60,
                "op": "gt",
                "value": 10,
                "span": 2,
                "address": 0x0300,
                "space": "cpu_ram",
            }
        ],
    }
    m.update(overrides)
    return m


@pytest.fixture
def write_manifest(tmp_path):
    def _write(manifest, rel="tests/fixtures/smoke.json"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(manifest, indent=2))
        return p

    return _write
