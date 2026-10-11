from pathlib import Path
from conftest import base_manifest
from rgqa.manifest import load
from rgqa.runner import Runner


def test_ca65_absolute_labels_do_not_add_base(write_manifest):
    d = base_manifest()
    cp = d['checkpoints'][0]
    del cp['address']
    del cp['space']
    cp['symbol'] = 'frame_lo'
    cp['symbols_from'] = 'state.lbl'
    cp['segment_base'] = 0
    src = write_manifest(d)
    (src.parent/'state.lbl').write_text('al 000307 .frame_lo\n')
    script = Runner().build_script(load(src))
    assert 'emu.read(775,' in script
