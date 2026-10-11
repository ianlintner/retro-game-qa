"""Regression for frame-local sampling; frame numbers are emulator frames."""
from conftest import base_manifest
from rgqa.manifest import load
from rgqa.runner import Runner


def test_checkpoint_is_sampled_at_its_frame_not_at_end(write_manifest):
    doc = base_manifest()
    doc['target']['rom'] = 'probe.nes'
    doc['checkpoints'][0]['frame'] = 7
    script = Runner().build_script(load(write_manifest(doc)))
    assert 'if frame == 7 then' in script
    assert '"frame":7' in script
