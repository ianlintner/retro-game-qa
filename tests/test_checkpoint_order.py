from conftest import base_manifest
from rgqa.manifest import load
from rgqa.runner import Runner


def test_checkpoints_render_in_frame_order(write_manifest):
    doc = base_manifest()
    late = doc['checkpoints'][0]
    late['frame'] = 9
    early = dict(late, name='early', frame=2)
    doc['checkpoints'].append(early)
    script = Runner().build_script(load(write_manifest(doc)))
    assert script.index('if frame == 2 then') < script.index('if frame == 9 then')
